"""Idempotent template seeding for default report templates.

Creates default DOCX and PDF templates for ``cold_storage_concept_design@1.0.0``
on first run.  Safe to call repeatedly — checks for existing templates before
inserting.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from cold_storage.modules.reports.domain.enums import (
    ExportFormat,
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.models import ReportTemplate

logger = logging.getLogger(__name__)

_MANIFEST_PATH = (
    Path(__file__).parent.parent
    / "templates"
    / "cold_storage_concept_design"
    / "1.0.0"
    / "manifest.json"
)


def _load_manifest() -> dict[str, Any]:
    """Load the manifest JSON from disk."""
    if not _MANIFEST_PATH.exists():
        logger.warning("Template manifest not found at %s", _MANIFEST_PATH)
        return {}
    result: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return result


def seed_default_templates(template_repo: Any) -> None:
    """Create default DOCX and PDF templates if they do not already exist.

    Parameters
    ----------
    template_repo:
        A repository implementing ``ReportTemplateRepository`` port
        (save_template, list_templates, get_active_template, update_template,
        commit).
    """
    manifest = _load_manifest()
    if not manifest:
        logger.warning("Skipping template seed: manifest empty or missing")
        return

    template_code = manifest.get("template_code", "cold_storage_concept_design")
    version = manifest.get("version", "1.0.0")
    report_type_str = manifest.get("report_type", "cold_storage_concept_design")
    schema_version = manifest.get("schema_version", f"{report_type_str}@{version}")
    locale = manifest.get("locale", "zh-CN")

    report_type = ReportType(report_type_str)

    for fmt in (ExportFormat.DOCX, ExportFormat.PDF):
        # Check if template already exists for this code+version+format
        existing = template_repo.list_templates(template_code=template_code, fmt=fmt.value)
        already_exists = any(t.version == version for t in existing)

        if already_exists:
            logger.info(
                "Template %s@%s (%s) already exists — skipping",
                template_code,
                version,
                fmt.value,
            )
            # Ensure it's active
            active = template_repo.get_active_template(template_code, fmt.value)
            if active is None or active.version != version:
                for t in existing:
                    if t.version == version and t.status != TemplateStatus.ACTIVE:
                        from dataclasses import replace as dc_replace

                        activated = dc_replace(t, status=TemplateStatus.ACTIVE)
                        template_repo.update_template(activated)
                        template_repo.commit()
                        logger.info("Activated template %s (%s)", t.id, fmt.value)
            continue

        # Create new template
        template = ReportTemplate.create(
            template_code=template_code,
            report_type=report_type,
            format=fmt,
            version=version,
            schema_version=schema_version,
            locale=locale,
            manifest_json=manifest,
            created_by="system",
        )
        # Set to active immediately for default templates
        from dataclasses import replace as dc_replace

        template = dc_replace(template, status=TemplateStatus.ACTIVE)
        template_repo.save_template(template)
        logger.info(
            "Created default template %s@%s (%s) — id=%s",
            template_code,
            version,
            fmt.value,
            template.id,
        )

    template_repo.commit()
