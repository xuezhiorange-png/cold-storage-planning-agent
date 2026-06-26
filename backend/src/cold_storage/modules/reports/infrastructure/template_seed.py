"""Idempotent template seeding for default report templates.

Creates default DOCX and PDF templates for ``cold_storage_concept_design@1.0.0``
on first run.  Safe to call repeatedly — checks for existing templates before
inserting.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from cold_storage.modules.reports.application.render_service import ReportTemplateRepositoryPort
from cold_storage.modules.reports.domain.enums import (
    ExportFormat,
    ReportLocale,
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.models import ReportTemplate

logger = logging.getLogger(__name__)

_MANIFEST_DIR = Path(__file__).parent.parent / "templates" / "cold_storage_concept_design" / "1.0.0"


def _load_manifest(
    fmt: ExportFormat,
    locale: str = "zh-CN",
    *,
    allow_legacy_fallback: bool = False,
) -> dict[str, Any]:
    """Load format-specific manifest JSON from disk.

    Looks for ``<manifest_dir>/<locale>/<fmt>/manifest.json`` first,
    then ``<manifest_dir>/<fmt>/manifest.json`` (legacy format-specific),
    then ``<manifest_dir>/manifest.json`` (legacy single manifest).

    When *allow_legacy_fallback* is ``False`` (default), raises
    ``FileNotFoundError`` if the locale-specific path does not exist.
    When ``True``, falls back to legacy paths for backward compatibility.
    """
    locale_path = _MANIFEST_DIR / locale / fmt.value / "manifest.json"

    if not allow_legacy_fallback:
        if not locale_path.exists():
            raise FileNotFoundError(
                f"Locale-specific manifest not found: {locale_path}. "
                f"Expected manifest at {locale_path} for locale={locale!r} "
                f"and format={fmt.value!r}."
            )
        result: dict[str, Any] = json.loads(locale_path.read_text(encoding="utf-8"))
        return result

    # allow_legacy_fallback=True: try locale-specific, then legacy paths
    if locale_path.exists():
        result = json.loads(locale_path.read_text(encoding="utf-8"))
        return result

    # Fallback to legacy format-specific path
    manifest_path = _MANIFEST_DIR / fmt.value / "manifest.json"
    if manifest_path.exists():
        result2: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        return result2

    # Fallback to legacy single manifest
    legacy = _MANIFEST_DIR / "manifest.json"
    if legacy.exists():
        result3: dict[str, Any] = json.loads(legacy.read_text(encoding="utf-8"))
        return result3

    logger.warning("Template manifest not found at %s", locale_path)
    return {}


def _compute_content_hash(manifest: dict[str, Any]) -> str:
    """Compute SHA-256 content hash of manifest dict."""
    content_str = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content_str.encode()).hexdigest()


def seed_default_templates(template_repo: ReportTemplateRepositoryPort) -> None:
    """Create default DOCX and PDF templates for all supported locales.

    Seeds templates for both zh-CN and en-US locales.  Each locale gets
    its own DOCX and PDF templates with locale-specific manifests.

    Parameters
    ----------
    template_repo:
        A repository implementing ``ReportTemplateRepository`` port
        (save_template, list_templates, get_active_template, update_template,
        commit).
    """
    from cold_storage.modules.reports.domain.enums import ReportLocale

    for locale in ReportLocale:
        _seed_locale_templates(template_repo, locale.value)


def _seed_locale_templates(template_repo: ReportTemplateRepositoryPort, locale: str) -> None:
    """Seed templates for a single locale."""
    from cold_storage.modules.reports.domain.enums import ReportLocale as _RL

    for fmt in (ExportFormat.DOCX, ExportFormat.PDF):
        manifest = _load_manifest(fmt, locale=locale, allow_legacy_fallback=True)
        if not manifest:
            logger.warning(
                "Skipping template seed for %s: manifest empty or missing",
                fmt.value,
            )
            continue

        template_code = manifest.get("template_code", "cold_storage_concept_design")
        version = manifest.get("version", "1.0.0")
        report_type_str = manifest.get("report_type", "cold_storage_concept_design")
        schema_version = manifest.get("schema_version", f"{report_type_str}@{version}")
        manifest_locale = manifest.get("locale", locale)

        report_type = ReportType(report_type_str)

        # Check if template already exists for this code+version+format+locale
        existing = template_repo.list_templates(template_code=template_code, format=fmt)
        already_exists = any(t.version == version and t.locale == manifest_locale for t in existing)

        if already_exists:
            logger.info(
                "Template %s@%s (%s) already exists — skipping",
                template_code,
                version,
                fmt.value,
            )
            # P0-8: Ensure it's active — deactivate all others first, then activate target
            active = template_repo.get_active_template(
                template_code, format=fmt, locale=_RL(manifest_locale)
            )
            if active is None or active.version != version:
                for t in existing:
                    if t.version == version and t.status != TemplateStatus.ACTIVE:
                        # P0-8: Deactivate existing active templates for same code+format+locale
                        if hasattr(template_repo, "deactivate_templates"):
                            template_repo.deactivate_templates(
                                template_code, fmt.value, locale=_RL(locale)
                            )
                        else:
                            # Fallback: deactivate any active template
                            current_active = template_repo.get_active_template(
                                template_code, format=fmt, locale=_RL(locale)
                            )
                            if current_active is not None:
                                from dataclasses import replace as dc_replace

                                deactivated = dc_replace(
                                    current_active, status=TemplateStatus.DRAFT
                                )
                                template_repo.update_template(deactivated)

                        from dataclasses import replace as dc_replace

                        activated = dc_replace(t, status=TemplateStatus.ACTIVE)
                        template_repo.update_template(activated)
                        template_repo.commit()
                        logger.info("Activated template %s (%s)", t.id, fmt.value)
            continue

        # Compute content hash from manifest
        template_content_hash = _compute_content_hash(manifest)

        # Create new template
        template = ReportTemplate.create(
            template_code=template_code,
            report_type=report_type,
            format=fmt,
            version=version,
            schema_version=schema_version,
            locale=ReportLocale(locale),
            manifest_json=manifest,
            template_content_hash=template_content_hash,
            created_by="system",
        )
        # Set to active immediately for default templates
        from dataclasses import replace as dc_replace

        template = dc_replace(template, status=TemplateStatus.ACTIVE)
        template_repo.save_template(template)
        logger.info(
            "Created default template %s@%s (%s) — id=%s, content_hash=%s",
            template_code,
            version,
            fmt.value,
            template.id,
            template_content_hash[:12],
        )

    template_repo.commit()
