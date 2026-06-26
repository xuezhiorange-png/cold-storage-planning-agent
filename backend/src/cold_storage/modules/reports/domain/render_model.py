"""Shared deterministic render view model.

Maps ReportRevision JSON to a format-neutral structure consumed by
DOCXRenderer and PDFRenderer.  No engineering computation, no ORM access.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from cold_storage.modules.reports.domain.enums import ReportLocale
from cold_storage.modules.reports.domain.models import ApprovalSnapshot

# -----------------------------------------------------------------------
# Type aliases (P0-9)
# -----------------------------------------------------------------------
JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, Any]  # for truly dynamic JSON blobs

# -----------------------------------------------------------------------
# Canonical Template Manifest Models (P0-5)
# -----------------------------------------------------------------------

_PT_PER_CM = 28.3465
_A4_WIDTH_PT = 21.0 * _PT_PER_CM
_A4_HEIGHT_PT = 29.7 * _PT_PER_CM
_A4_MARGIN_PT = 2.0 * _PT_PER_CM


class TemplateEmptySectionConfig(BaseModel):
    """Configuration for empty section rendering behavior."""

    behavior: str = "show_placeholder"  # show_placeholder | hide
    placeholder_text: dict[str, str] = Field(
        default_factory=lambda: {
            "not_provided": "",  # renderer localizes via catalog
            "not_calculated": "",
        }
    )


class TemplateTableColumnConfig(BaseModel):
    """Configuration for a single table column."""

    key: str
    header: str = ""
    width_ratio: float = 0.0
    align: str = "left"


class TemplateTableConfig(BaseModel):
    """Configuration for a specific table in the template."""

    columns: list[TemplateTableColumnConfig] = Field(default_factory=list)
    repeat_header: bool = True
    unit_row: bool = True
    orientation: str = "portrait"


class TemplatePageConfig(BaseModel):
    """Page size and margin configuration in points."""

    width_pt: float = _A4_WIDTH_PT
    height_pt: float = _A4_HEIGHT_PT
    margin_top_pt: float = _A4_MARGIN_PT
    margin_bottom_pt: float = _A4_MARGIN_PT
    margin_left_pt: float = _A4_MARGIN_PT
    margin_right_pt: float = _A4_MARGIN_PT
    orientation: str = "portrait"  # portrait | landscape


class TemplateFontConfig(BaseModel):
    """Font configuration for the template."""

    body_name: str = "SimSun"
    body_size_pt: float = 10.5
    heading1_size_pt: float = 16
    heading2_size_pt: float = 14
    heading3_size_pt: float = 12
    table_header_size_pt: float = 9.5
    table_body_size_pt: float = 9
    footer_size_pt: float = 8
    header_size_pt: float = 8


class TemplateHeaderFooterConfig(BaseModel):
    """Header or footer configuration with left/center/right text."""

    left: str = ""
    right: str = ""
    center: str = ""


class TemplateWatermarkConfig(BaseModel):
    """Watermark configuration."""

    text: str = ""
    font_size_pt: float = 72
    color: str = "#CCCCCC"
    opacity: float = 0.3
    angle: float = 45


class TemplateManifest(BaseModel):
    """Canonical template manifest parsed from template manifest_json.

    Provides a single source of truth for template rendering configuration.
    Renderers read from this model's ``model_dump()`` output.
    """

    page: TemplatePageConfig = Field(default_factory=TemplatePageConfig)
    fonts: TemplateFontConfig = Field(default_factory=TemplateFontConfig)
    header: TemplateHeaderFooterConfig = Field(default_factory=TemplateHeaderFooterConfig)
    footer: TemplateHeaderFooterConfig = Field(default_factory=TemplateHeaderFooterConfig)
    watermark: TemplateWatermarkConfig = Field(default_factory=TemplateWatermarkConfig)
    locale: ReportLocale = ReportLocale.ZH_CN
    format: str = "docx"  # "docx" or "pdf"
    template_code: str = "cold_storage_concept_design"
    version: str = "1.0.0"
    report_type: str = "cold_storage_concept_design"
    schema_version: str = "1.0.0"
    empty_section_behavior: TemplateEmptySectionConfig = Field(
        default_factory=TemplateEmptySectionConfig
    )
    tables: dict[str, TemplateTableConfig] = Field(default_factory=dict)
    required_sections: list[str] = Field(default_factory=list)
    optional_sections: list[str] = Field(default_factory=list)
    landscape_sections: list[str] = Field(default_factory=list)
    numbering: JsonObject = Field(default_factory=dict)
    quality_finding_rendering: JsonObject = Field(default_factory=dict)

    @classmethod
    def from_manifest_json(cls, manifest_json: JsonObject | None) -> TemplateManifest:
        """Parse a raw template manifest_json dict into a canonical TemplateManifest.

        Handles legacy field names (mm margins, styles.* font sizes, etc.)
        by normalizing to the canonical pt-based structure.
        """
        if not manifest_json:
            return cls()

        data = dict(manifest_json)

        # --- Normalize page config ---
        raw_page = dict(data.get("page", {}))
        page: JsonObject = {}

        # Accept width_pt/height_pt or compute from A4
        page["width_pt"] = raw_page.get("width_pt", _A4_WIDTH_PT)
        page["height_pt"] = raw_page.get("height_pt", _A4_HEIGHT_PT)
        page["orientation"] = raw_page.get("orientation", "portrait")

        # Accept margin_top_pt or convert from mm
        _MM_TO_PT = 2.83465
        for side in ("top", "bottom", "left", "right"):
            pt_key = f"margin_{side}_pt"
            mm_key = f"margin_{side}_mm"
            if pt_key in raw_page:
                page[pt_key] = raw_page[pt_key]
            elif mm_key in raw_page:
                page[pt_key] = raw_page[mm_key] * _MM_TO_PT

        # Preserve landscape_sections from page config
        page["landscape_sections"] = raw_page.get("landscape_sections", [])
        data["page"] = page

        # --- Normalize font config ---
        # Accept fonts.* or styles.* (legacy)
        raw_fonts = dict(data.get("fonts", {}))
        raw_styles = dict(data.get("styles", {}))

        fonts: JsonObject = {}
        # body font name
        fonts["body_name"] = raw_fonts.get("body_name") or raw_styles.get("body_font", "SimSun")
        # body size
        fonts["body_size_pt"] = raw_fonts.get("body_size_pt") or raw_styles.get(
            "body_size_pt", 10.5
        )
        # heading sizes
        for level in (1, 2, 3):
            pt_key = f"heading{level}_size_pt"
            fonts[pt_key] = raw_fonts.get(pt_key) or raw_styles.get(pt_key, [16, 14, 12][level - 1])
        # table sizes
        fonts["table_header_size_pt"] = raw_fonts.get("table_header_size_pt", 9.5)
        fonts["table_body_size_pt"] = raw_fonts.get("table_body_size_pt", 9)
        # header/footer sizes
        fonts["footer_size_pt"] = raw_fonts.get("footer_size_pt", 8)
        fonts["header_size_pt"] = raw_fonts.get("header_size_pt", 8)

        data["fonts"] = fonts

        # --- Normalize header/footer ---
        # Already in left/center/right format
        data["header"] = dict(data.get("header", {}))
        data["footer"] = dict(data.get("footer", {}))

        # --- Normalize watermark ---
        # Accept watermark.* or draft_watermark.* (legacy)
        raw_wm = dict(data.get("watermark", {}))
        raw_draft = dict(data.get("draft_watermark", {}))
        if not raw_wm and raw_draft:
            raw_wm = raw_draft

        watermark: dict[str, Any] = {}
        watermark["text"] = raw_wm.get("text", "")
        watermark["font_size_pt"] = raw_wm.get("font_size_pt", raw_wm.get("size", 72))
        watermark["color"] = raw_wm.get("color", "#CCCCCC")
        watermark["opacity"] = raw_wm.get("opacity", 0.3)
        watermark["angle"] = raw_wm.get("angle", 45)

        data["watermark"] = watermark

        # --- Normalize empty_section_behavior ---
        # Accept string or dict format
        raw_esb = data.get("empty_section_behavior")
        raw_pt = data.get("placeholder_text")
        if isinstance(raw_esb, str):
            esb_dict: dict[str, Any] = {"behavior": raw_esb}
        elif isinstance(raw_esb, dict):
            esb_dict = dict(raw_esb)
        else:
            esb_dict = {"behavior": "show_placeholder"}
        if isinstance(raw_pt, dict):
            esb_dict["placeholder_text"] = raw_pt
        data["empty_section_behavior"] = esb_dict

        # --- Normalize tables ---
        raw_tables = data.get("tables", {})
        norm_tables: dict[str, Any] = {}
        for tname, tval in raw_tables.items():
            if isinstance(tval, dict):
                # Convert legacy list-of-strings columns to structured format
                raw_cols = tval.get("columns", [])
                if raw_cols and isinstance(raw_cols[0], str):
                    cols = [{"key": c, "header": c} for c in raw_cols]
                else:
                    cols = raw_cols
                norm_tables[tname] = {
                    "columns": cols,
                    "repeat_header": tval.get("repeat_header", True),
                    "unit_row": tval.get("unit_row", True),
                    "orientation": tval.get("orientation", "portrait"),
                }
                # Handle unit_row as list (legacy) or bool (canonical)
                if isinstance(tval.get("unit_row"), list):
                    norm_tables[tname]["unit_row"] = True
        data["tables"] = norm_tables

        # --- Remove legacy keys that have been normalized or are no longer needed ---
        for key in (
            "styles",
            "draft_watermark",
            "placeholder_text",
            "status",
        ):
            data.pop(key, None)

        # Preserve identity fields
        if "report_type" in manifest_json:
            data["report_type"] = manifest_json["report_type"]
        if "schema_version" in manifest_json:
            data["schema_version"] = manifest_json["schema_version"]

        return cls.model_validate(data)


@dataclass(frozen=True)
class CanonicalRenderMetric:
    """Stable canonical metric — no display/locale text."""

    field_path: str
    field_key: str  # stable key like "cooling_load.total"
    raw_value: Decimal | int  # tightened from Any
    unit_code: str  # stable code like "kW(r)"
    source_id: str = ""
    source_tool: str = ""
    source_tool_version: str = ""
    source_content_hash: str = ""


@dataclass(frozen=True)
class LocalizedRenderMetric:
    """Localized metric for renderer consumption."""

    canonical: CanonicalRenderMetric
    label: str  # localized field label
    display_value: str  # formatted number string
    display_unit: str  # localized unit label


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


# -----------------------------------------------------------------------
# Canonical / Localized model types (two-stage pipeline)
# -----------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalRenderMetadata:
    """Locale-free document metadata."""

    report_id: str
    report_type: str  # stable enum value, NOT translated
    schema_version: str
    revision_number: int
    content_hash: str
    content_hash_short: str
    generated_at: str
    generated_by: str
    template_version: str
    template_code: str
    project_name: str = ""


@dataclass(frozen=True)
class LocalizedRenderMetadata:
    """Locale-specific document metadata for renderer."""

    canonical: CanonicalRenderMetadata
    project_name: str  # may be empty, not translated
    report_type_label: str  # localized report type label
    confidentiality_label: str  # e.g. "机密文件 — 仅供内部使用"
    disclaimer: str  # localized disclaimer text
    empty_section_placeholder: str  # default empty section text
    # Cover page text
    cover_title: str  # project name or fallback title
    cover_version_line: str  # e.g. "版本 1  |  2025-01-01"
    # Document control info labels
    control_info_title: str  # "文件控制信息" / "Document Control"
    content_hash_label: str  # "内容哈希" / "Content Hash"
    template_version_label: str  # "模板版本" / "Template Version"
    generated_by_label: str  # "生成者" / "Generated By"
    generated_at_label: str  # "生成时间" / "Generated At"
    revision_label: str  # "修订号" / "Revision"
    # Watermark
    watermark_text: str  # locale-specific watermark text ("草稿" / "DRAFT")


@dataclass(frozen=True)
class LocalizedRenderNumber:
    """Localized number for rendering."""

    canonical: CanonicalRenderMetric  # reuse as it has raw_value + unit_code
    display_value: str
    display_unit: str


@dataclass(frozen=True)
class LocalizedRenderTableCell:
    """Localized table cell."""

    canonical: CanonicalRenderTableCell
    display_value: str = ""
    display_unit: str = ""
    align: str | None = None


@dataclass(frozen=True)
class LocalizedRenderTable:
    """Localized table for rendering."""

    canonical: CanonicalRenderTable
    title: str = ""
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[LocalizedRenderTableCell, ...], ...] = ()
    unit_row: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalizedRisk:
    """Localized risk entry for rendering."""

    canonical: CanonicalRisk
    severity_label: str
    mitigation_label: str


@dataclass(frozen=True)
class LocalizedFinding:
    """Localized finding for rendering."""

    canonical: CanonicalFinding
    severity_label: str
    section_label: str


@dataclass(frozen=True)
class LocalizedMissingInformation:
    """Localized missing information entry."""

    canonical: CanonicalMissingInformation
    impact_label: str


@dataclass(frozen=True)
class LocalizedCitation:
    """Localized citation entry."""

    canonical: CanonicalCitation
    section_label: str
    source_type_label: str


@dataclass(frozen=True)
class LocalizedRenderSection:
    """Locale-specific section for renderer."""

    section_key: str
    title: str
    level: int
    content_type: str
    text: str = ""
    number: LocalizedRenderNumber | None = None
    table: LocalizedRenderTable | None = None
    findings: tuple[LocalizedFinding, ...] = ()
    is_empty: bool = False
    empty_reason_text: str = ""
    metrics: tuple[LocalizedRenderMetric, ...] = ()
    paragraphs: tuple[str, ...] = ()
    citations: tuple[LocalizedCitation, ...] = ()
    risks: tuple[LocalizedRisk, ...] = ()
    missing_information: tuple[LocalizedMissingInformation, ...] = ()
    canonical: CanonicalRenderSection | None = None


# -----------------------------------------------------------------------
# True canonical types for locale-free data (Task 9C)
# -----------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalFinding:
    """Locale-free quality finding."""

    code: str
    severity_code: str
    message: str
    section_key: str = ""
    field_path: str = ""


@dataclass(frozen=True)
class CanonicalRisk:
    """Locale-free risk entry."""

    description: str
    severity_code: str
    mitigation: str = ""


@dataclass(frozen=True)
class CanonicalCitation:
    """Locale-free citation / source reference."""

    section_key: str
    source_type_code: str
    source_id: str
    tool_name: str
    content_hash: str = ""


@dataclass(frozen=True)
class CanonicalMissingInformation:
    """Locale-free missing information entry."""

    description: str
    impact_code: str
    field_path: str = ""


@dataclass(frozen=True)
class CanonicalRenderTableCell:
    """Locale-free table cell."""

    field_path: str
    field_key: str
    raw_value: Decimal | int | str | None
    unit_code: str = ""
    align_code: str | None = None
    source_id: str = ""
    source_tool: str = ""
    source_tool_version: str = ""
    source_content_hash: str = ""
    run_id: str = ""
    # Run-level provenance fallback fields (from section data)
    generator_version: str = ""
    scheme_evaluator: str = ""
    persisted_content_hash: str = ""


@dataclass(frozen=True)
class CanonicalRenderTable:
    """Locale-free table."""

    table_key: str
    column_keys: tuple[str, ...] = ()
    rows: tuple[tuple[CanonicalRenderTableCell, ...], ...] = ()
    unit_codes: tuple[str, ...] = ()
    title_key: str = ""


@dataclass(frozen=True)
class CanonicalRenderSection:
    """Locale-free section — no translated display text."""

    section_key: str
    level: int
    content_type_code: str  # "text" | "metrics" | "number" | "table" | "finding" | "empty"
    text_fields: dict[str, str] = field(default_factory=dict)
    number: CanonicalRenderMetric | None = None
    table: CanonicalRenderTable | None = None
    metrics: tuple[CanonicalRenderMetric, ...] = ()
    findings: tuple[CanonicalFinding, ...] = ()
    risks: tuple[CanonicalRisk, ...] = ()
    citations: tuple[CanonicalCitation, ...] = ()
    missing_information: tuple[CanonicalMissingInformation, ...] = ()
    approval_snapshot: ApprovalSnapshot | None = None
    empty_reason_code: str = ""
    paragraphs: tuple[str, ...] = ()
    # title for renderer compatibility (same as section_key in canonical)
    title: str = ""
    recommended_scheme_code: str = ""


@dataclass(frozen=True)
class CanonicalReportRenderModel:
    """Locale-free render model — contains only canonical data."""

    metadata: CanonicalRenderMetadata
    sections: tuple[CanonicalRenderSection, ...]
    manifest: RenderManifest
    approval_snapshot: ApprovalSnapshot | None = None


@dataclass(frozen=True)
class LocalizedReportRenderModel:
    """Locale-specific render model consumed by DOCX/PDF renderers."""

    metadata: LocalizedRenderMetadata
    sections: tuple[LocalizedRenderSection, ...]
    manifest: RenderManifest
    disclaimer: str = ""
    watermark_text: str = ""
    # Cover page / document control localized labels (from ReportRenderModel)
    cover_version_line: str = ""
    control_info_title: str = ""
    content_hash_label: str = ""
    template_version_label: str = ""
    generated_by_label: str = ""
    generated_at_label: str = ""
    revision_label: str = ""


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
        return "\u2014"
    try:
        from decimal import Decimal

        num = Decimal(str(value))
    except (TypeError, ValueError):
        return str(value)
    rules = _NUMBER_FORMAT_RULES.get(unit, _NUMBER_FORMAT_RULES[""])
    decimals = rules["decimals"]
    use_sep = rules["thousands_sep"]
    if use_sep:
        int_part = int(num)
        frac_part = abs(num) - abs(int_part)
        int_str = f"{int_part:,}"
        if decimals > 0:
            frac_str = f"{frac_part:.{decimals}f}"[1:]  # skip "0."
            formatted = f"{int_str}{frac_str}"
        else:
            formatted = int_str
    else:
        formatted = f"{num:.{decimals}f}"
    return formatted
