"""Shared deterministic render view model.

Maps ReportRevision JSON to a format-neutral structure consumed by
DOCXRenderer and PDFRenderer.  No engineering computation, no ORM access.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RenderNumber:
    """A number with its raw value, display string, and unit."""

    raw: Any  # original value from content_json (str | int | float)
    display: str  # formatted for rendering (e.g. "180.0")
    unit: str  # e.g. "kW(r)"
    field_path: str = ""


@dataclass(frozen=True)
class RenderTableCell:
    """A single table cell with value and optional unit."""

    value: str
    unit: str = ""
    align: str = "left"  # left | right | center


@dataclass(frozen=True)
class RenderTable:
    """A table with headers and rows."""

    title: str
    headers: list[str]
    rows: list[list[RenderTableCell]]
    unit_row: list[str] = field(default_factory=list)  # unit per column


@dataclass(frozen=True)
class RenderSection:
    """A single chapter/section in the render model."""

    section_key: str
    title: str
    level: int  # 1=chapter, 2=section, 3=subsection
    content_type: str  # text | table | number | finding | empty
    text: str = ""
    number: RenderNumber | None = None
    table: RenderTable | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    is_empty: bool = False
    empty_reason: str = ""  # "not_provided" | "not_calculated"


@dataclass(frozen=True)
class RenderMetadata:
    """Document-level metadata for headers/footers/covers."""

    report_id: str
    project_name: str
    report_type: str
    schema_version: str
    revision_number: int
    content_hash: str
    content_hash_short: str  # first 8 chars
    generated_at: str
    generated_by: str
    template_version: str
    template_code: str
    locale: str = "zh-CN"
    confidentiality: str = "内部文件"


@dataclass(frozen=True)
class RenderManifest:
    """Render manifest recording what was rendered and how."""

    template_code: str
    template_version: str
    schema_version: str
    source_content_hash: str
    sections: list[str]
    format: str
    render_settings: dict[str, Any] = field(default_factory=dict)
    manifest_hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "template_code": self.template_code,
            "template_version": self.template_version,
            "schema_version": self.schema_version,
            "source_content_hash": self.source_content_hash,
            "sections": self.sections,
            "format": self.format,
            "render_settings": self.render_settings,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ReportRenderModel:
    """Complete render model for a report revision.

    DOCX and PDF renderers both consume this model.
    """

    metadata: RenderMetadata
    sections: list[RenderSection]
    manifest: RenderManifest


# -----------------------------------------------------------------------
# Number formatting rules (centralized, not in templates)
# -----------------------------------------------------------------------

_NUMBER_FORMAT_RULES: dict[str, dict[str, Any]] = {
    "kW(r)": {"decimals": 1, "thousands_sep": False},
    "kW(e)": {"decimals": 1, "thousands_sep": False},
    "kW(th)": {"decimals": 1, "thousands_sep": False},
    "kWh": {"decimals": 0, "thousands_sep": True},
    "CNY": {"decimals": 0, "thousands_sep": True},
    "kg": {"decimals": 0, "thousands_sep": True},
    "m2": {"decimals": 1, "thousands_sep": False},
    "count": {"decimals": 0, "thousands_sep": False},
    "": {"decimals": 2, "thousands_sep": False},
}


def format_number(value: Any, unit: str = "") -> str:
    """Format a number for display without modifying the raw value."""
    if value is None or value == "":
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    rules = _NUMBER_FORMAT_RULES.get(unit, _NUMBER_FORMAT_RULES[""])
    decimals = rules["decimals"]
    use_sep = rules["thousands_sep"]
    formatted = f"{num:,.{decimals}f}" if use_sep else f"{num:.{decimals}f}"
    return formatted
