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
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.models import ReportTemplate

logger = logging.getLogger(__name__)

_MANIFEST_DIR = Path(__file__).parent.parent / "templates" / "cold_storage_concept_design" / "1.0.0"


def _load_manifest(fmt: ExportFormat) -> dict[str, Any]:
    """Load format-specific manifest JSON from disk.

    Looks for ``<manifest_dir>/<fmt>/manifest.json`` first, falling back to
    the legacy single ``manifest.json`` if the format-specific file is missing.
    """
    manifest_path = _MANIFEST_DIR / fmt.value / "manifest.json"
    if not manifest_path.exists():
        # Fallback to legacy single manifest
        legacy = _MANIFEST_DIR / "manifest.json"
        if legacy.exists():
            data: dict[str, Any] = json.loads(legacy.read_text(encoding="utf-8"))
            return data
        logger.warning("Template manifest not found at %s", manifest_path)
        return {}
    result: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return result


def _compute_content_hash(manifest: dict[str, Any]) -> str:
    """Compute SHA-256 content hash of manifest dict."""
    content_str = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content_str.encode()).hexdigest()


def seed_default_templates(template_repo: ReportTemplateRepositoryPort) -> None:
    """Create default DOCX and PDF templates if they do not already exist.

    Parameters
    ----------
    template_repo:
        A repository implementing ``ReportTemplateRepository`` port
        (save_template, list_templates, get_active_template, update_template,
        commit).
    """
    for fmt in (ExportFormat.DOCX, ExportFormat.PDF):
        manifest = _load_manifest(fmt)
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
        locale = manifest.get("locale", "zh-CN")

        report_type = ReportType(report_type_str)

        # Check if template already exists for this code+version+format
        existing = template_repo.list_templates(template_code=template_code, format=fmt)
        already_exists = any(t.version == version for t in existing)

        if already_exists:
            logger.info(
                "Template %s@%s (%s) already exists — skipping",
                template_code,
                version,
                fmt.value,
            )
            # Ensure it's active
            active = template_repo.get_active_template(template_code, format=fmt)
            if active is None or active.version != version:
                for t in existing:
                    if t.version == version and t.status != TemplateStatus.ACTIVE:
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
            locale=locale,
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
