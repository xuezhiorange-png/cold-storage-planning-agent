"""PDF renderer — produces a .pdf file from a ReportRenderModel.

Uses PyMuPDF (fitz).  Text is selectable (no rasterization).  A4 layout
with headers, footers, and optional DRAFT watermark.

P0-1: Metrics content type rendering.
P0-6: Real pagination with page overflow detection and table header repeat.
P0-9: Uses system CJK font for Chinese text rendering.
P0-10: Template manifest controls page size, margins, fonts, styles, etc.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import fitz  # PyMuPDF

from cold_storage.modules.reports.domain.render_model import RenderTableCell

if TYPE_CHECKING:
    from cold_storage.modules.reports.domain.render_model import (
        RenderMetadata,
        RenderSection,
        RenderTable,
        ReportRenderModel,
    )

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CJK Font Detection (P0-9)
# ---------------------------------------------------------------------------
_CJK_FONT_CANDIDATES: list[str] = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
]

_CJK_FONT_PATH: str | None = None


def _find_cjk_font() -> str:
    """Find a CJK-capable font on the system, caching the result."""
    global _CJK_FONT_PATH  # noqa: PLW0603
    if _CJK_FONT_PATH is not None:
        return _CJK_FONT_PATH

    # Check hardcoded candidates first
    for candidate in _CJK_FONT_CANDIDATES:
        if Path(candidate).is_file():
            _CJK_FONT_PATH = candidate
            return _CJK_FONT_PATH

    # Scan /usr/share/fonts for any .ttc or .ttf that might be CJK
    for font_dir in Path("/usr/share/fonts").rglob("*"):
        if font_dir.is_file() and font_dir.suffix in (".ttc", ".ttf"):
            name_lower = font_dir.name.lower()
            if any(kw in name_lower for kw in ("cjk", "wqy", "noto", "gothic", "mincho", "han")):
                _CJK_FONT_PATH = str(font_dir)
                return _CJK_FONT_PATH

    raise RuntimeError("No CJK font found. Install fonts-wqy-zenhei or similar.")


def _get_cjk_font() -> fitz.Font:
    """Return a fitz.Font object for CJK text."""
    font_path = _find_cjk_font()
    return fitz.Font(fontfile=font_path)


def _get_cjk_fontname() -> str:
    """Return the registered fontname for CJK font used with page.insert_text."""
    # We register the font on each page; use a stable name
    return "cjk_font"


# ---------------------------------------------------------------------------
# Constants (defaults — overridden by template manifest)
# ---------------------------------------------------------------------------
_PT_PER_CM = 28.3465  # 1 cm = 28.3465 pt
_A4_WIDTH_PT = 21.0 * _PT_PER_CM
_A4_HEIGHT_PT = 29.7 * _PT_PER_CM
_MARGIN_PT = 2.0 * _PT_PER_CM  # 2 cm margins

_BODY_FONT_SIZE = 10.5
_HEADING1_SIZE = 16
_HEADING2_SIZE = 14
_HEADING3_SIZE = 12
_TABLE_HEADER_SIZE = 9.5
_TABLE_BODY_SIZE = 9
_FOOTER_SIZE = 8
_HEADER_SIZE = 8

_TEXT_COLOR = (0, 0, 0)
_HEADING_COLOR = (0.122, 0.219, 0.392)  # (31, 56, 100) normalized
_GRAY_COLOR = (0.5, 0.5, 0.5)
_LIGHT_BLUE = (0.851, 0.886, 0.953)  # (217, 226, 243) normalized
_LIGHT_GRAY = (0.941, 0.941, 0.941)  # (240, 240, 240) normalized

_LINE_HEIGHT = 14  # pt between text lines
_SECTION_SPACING = 20  # pt between sections


# ---------------------------------------------------------------------------
# Template Manifest Helpers (P0-10)
# ---------------------------------------------------------------------------


def _load_manifest_settings(
    model: ReportRenderModel,
) -> dict[str, Any]:
    """Extract rendering settings from template manifest with defaults.

    Supports both legacy and canonical TemplateManifest structures.
    Canonical: page.margin_top_pt, fonts.body_size_pt, header.left/right, watermark.text
    Legacy: page.margin_pt, fonts.body_size, header.text, draft_watermark.text
    """
    render_settings = model.manifest.render_settings
    settings: dict[str, Any] = {}

    # Page settings
    page = render_settings.get("page", {})
    settings["page_width_pt"] = page.get("width_pt", _A4_WIDTH_PT)
    settings["page_height_pt"] = page.get("height_pt", _A4_HEIGHT_PT)
    # Support per-side margins (canonical) and single margin (legacy)
    settings["margin_top_pt"] = page.get("margin_top_pt", page.get("margin_pt", _MARGIN_PT))
    settings["margin_bottom_pt"] = page.get("margin_bottom_pt", page.get("margin_pt", _MARGIN_PT))
    settings["margin_left_pt"] = page.get("margin_left_pt", page.get("margin_pt", _MARGIN_PT))
    settings["margin_right_pt"] = page.get("margin_right_pt", page.get("margin_pt", _MARGIN_PT))
    settings["margin_pt"] = settings["margin_left_pt"]  # backward compat

    # Font settings (canonical: body_size_pt, heading1_size_pt)
    fonts = render_settings.get("fonts", {})
    settings["body_font_size"] = fonts.get("body_size_pt", fonts.get("body_size", _BODY_FONT_SIZE))
    settings["heading1_size"] = fonts.get(
        "heading1_size_pt", fonts.get("heading1_size", _HEADING1_SIZE)
    )
    settings["heading2_size"] = fonts.get(
        "heading2_size_pt", fonts.get("heading2_size", _HEADING2_SIZE)
    )
    settings["heading3_size"] = fonts.get(
        "heading3_size_pt", fonts.get("heading3_size", _HEADING3_SIZE)
    )
    settings["table_header_size"] = fonts.get(
        "table_header_size_pt", fonts.get("table_header_size", _TABLE_HEADER_SIZE)
    )
    settings["table_body_size"] = fonts.get(
        "table_body_size_pt", fonts.get("table_body_size", _TABLE_BODY_SIZE)
    )
    settings["footer_size"] = fonts.get("footer_size_pt", fonts.get("footer_size", _FOOTER_SIZE))
    settings["header_size"] = fonts.get("header_size_pt", fonts.get("header_size", _HEADER_SIZE))

    # Style settings
    styles = render_settings.get("styles", {})
    settings["heading_color"] = tuple(styles.get("heading_color", list(_HEADING_COLOR)))

    # Header/footer text (canonical: header.left/right/center)
    header = render_settings.get("header", {})
    footer = render_settings.get("footer", {})
    settings["header_left"] = header.get("left", "")
    settings["header_right"] = header.get("right", "")
    settings["header_center"] = header.get("center", "")
    settings["footer_left"] = footer.get("left", "")
    settings["footer_right"] = footer.get("right", "")
    settings["footer_center"] = footer.get("center", "")
    # Legacy single text
    settings["header_text"] = header.get("text", "")
    settings["footer_text"] = footer.get("text", "")

    # Draft watermark (canonical: watermark.text/font_size_pt/color/opacity/angle)
    watermark = render_settings.get("watermark", {})
    draft_wm = render_settings.get("draft_watermark", watermark)  # fallback
    settings["draft_watermark_text"] = draft_wm.get("text", "DRAFT")
    settings["draft_watermark_size"] = draft_wm.get("font_size_pt", draft_wm.get("size", 60))
    settings["draft_watermark_color"] = draft_wm.get("color", "#CCCCCC")
    settings["draft_watermark_opacity"] = draft_wm.get("opacity", 0.3)
    settings["draft_watermark_angle"] = draft_wm.get("angle", 45)

    # Empty section placeholder
    settings["placeholder_text"] = render_settings.get("placeholder_text", "该部分内容不可用")
    # P0-8: Load empty_section_behavior from manifest for per-reason placeholder text
    esb = render_settings.get("empty_section_behavior", {})
    if not isinstance(esb, dict):
        esb = {}
    # Ensure default placeholder texts are always present
    default_placeholders = {
        "not_provided": "该部分数据未提供",
        "not_calculated": "该部分尚未计算",
    }
    existing_pt = esb.get("placeholder_text", {})
    merged_pt = {**default_placeholders, **existing_pt}
    esb["placeholder_text"] = merged_pt
    settings["empty_section_behavior"] = esb

    # Table column definitions
    settings["table_columns"] = render_settings.get("tables", {}).get("columns", {})
    # Table repeat_header default (P0-7)
    settings["table_repeat_header"] = render_settings.get("tables", {}).get("repeat_header", True)
    # P0-4: Per-section table configs (keyed by section_key)
    settings["table_configs"] = render_settings.get("tables", {})

    # P0-5: Landscape orientation settings
    settings["orientation"] = render_settings.get("page", {}).get("orientation", "portrait")
    settings["landscape_sections"] = render_settings.get("landscape_sections", [])
    # Also check page.landscape_sections
    if not settings["landscape_sections"]:
        settings["landscape_sections"] = render_settings.get("page", {}).get(
            "landscape_sections", []
        )

    return settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_text(
    page: fitz.Page,
    x: float,
    y: float,
    text: str,
    *,
    fontsize: float = _BODY_FONT_SIZE,
    color: tuple[float, float, float] = _TEXT_COLOR,
    font_path: str | None = None,
    max_width: float | None = None,
) -> float:
    """Insert text on page and return the new y position.

    Handles line wrapping within the content width.
    Uses CJK font for proper Chinese character rendering (P0-9).
    """
    if max_width is None:
        max_width = _A4_WIDTH_PT - 2 * _MARGIN_PT  # content width

    font = fitz.Font(fontfile=font_path) if font_path else _get_cjk_font()
    lines = text.split("\n")
    current_y = y

    for line in lines:
        if not line:
            current_y += _LINE_HEIGHT
            continue

        # Character-level wrapping for CJK text
        current_line = ""
        for char in line:
            test = current_line + char
            text_width = font.text_length(test, fontsize=fontsize)
            if text_width > max_width and current_line:
                # Write current line
                tw = fitz.TextWriter(page.rect)
                tw.append(fitz.Point(x, current_y), current_line, font=font, fontsize=fontsize)
                tw.write_text(page, color=color)
                current_y += _LINE_HEIGHT
                current_line = char
            else:
                current_line = test

        if current_line:
            tw = fitz.TextWriter(page.rect)
            tw.append(fitz.Point(x, current_y), current_line, font=font, fontsize=fontsize)
            tw.write_text(page, color=color)
            current_y += _LINE_HEIGHT

    return current_y


def _insert_number(
    page: fitz.Page,
    x: float,
    y: float,
    display: str,
    unit: str,
    *,
    font_path: str | None = None,
) -> float:
    """Insert a bold number with unit."""
    fontsize = _BODY_FONT_SIZE + 0.5
    full_text = f"{display} {unit}"
    font = fitz.Font(fontfile=font_path) if font_path else _get_cjk_font()
    tw = fitz.TextWriter(page.rect)
    tw.append(fitz.Point(x, y), full_text, font=font, fontsize=fontsize)
    tw.write_text(page, color=_TEXT_COLOR)
    return y + _LINE_HEIGHT + 2


def _substitute_vars(text: str, meta: Any, page_num: int) -> str:
    """Substitute template variables like {project_name} in text."""
    return (
        text.replace("{project_name}", getattr(meta, "project_name", "") or "")
        .replace("{report_type}", getattr(meta, "report_type", "") or "")
        .replace("{revision_number}", str(getattr(meta, "revision_number", "")))
        .replace(
            "{generated_at}",
            (getattr(meta, "generated_at", "") or "")[:10],
        )
        .replace(
            "{content_hash_short}",
            getattr(meta, "content_hash_short", "") or "",
        )
        .replace(
            "{confidentiality}",
            getattr(meta, "confidentiality", "") or "",
        )
        .replace("{page_number}", str(page_num))
    )


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert a hex color string to normalized RGB tuple."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def _draw_header(
    page: fitz.Page,
    project_name: str,
    report_type: str,
    *,
    settings: dict[str, Any] | None = None,
    margin_left: float | None = None,
    page_width: float | None = None,
    margin_top: float | None = None,
    meta: Any = None,
    page_num: int = 1,
) -> None:
    """Draw header on page with configurable margins and sizes.

    Supports manifest-driven left/center/right header text with variable
    substitution (P0-4).  Falls back to legacy single-line header when
    all three positions are empty.
    """
    if settings is None:
        settings = {}
    if margin_left is None:
        margin_left = _MARGIN_PT
    if page_width is None:
        page_width = _A4_WIDTH_PT
    if margin_top is None:
        margin_top = _MARGIN_PT

    header_left = settings.get("header_left", "")
    header_center = settings.get("header_center", "")
    header_right = settings.get("header_right", "")

    # Legacy single-text fallback
    if not header_left and not header_center and not header_right:
        header_right = f"{project_name} — {report_type}"

    header_size = settings.get("header_size", _HEADER_SIZE)
    content_left = margin_left
    content_right = page_width - settings.get("margin_right_pt", _MARGIN_PT)
    content_width = content_right - content_left
    font = _get_cjk_font()
    y_text = margin_top + 0.5 * _PT_PER_CM

    # Left header
    if header_left:
        text = _substitute_vars(header_left, meta, page_num) if meta else header_left
        tw = fitz.TextWriter(page.rect)
        tw.append(fitz.Point(content_left, y_text), text, font=font, fontsize=header_size)
        tw.write_text(page, color=_GRAY_COLOR)

    # Center header
    if header_center:
        text = _substitute_vars(header_center, meta, page_num) if meta else header_center
        tw_width = font.text_length(text, fontsize=header_size)
        tw = fitz.TextWriter(page.rect)
        tw.append(
            fitz.Point(content_left + (content_width - tw_width) / 2, y_text),
            text,
            font=font,
            fontsize=header_size,
        )
        tw.write_text(page, color=_GRAY_COLOR)

    # Right header
    if header_right:
        text = _substitute_vars(header_right, meta, page_num) if meta else header_right
        tw_width = font.text_length(text, fontsize=header_size)
        tw = fitz.TextWriter(page.rect)
        tw.append(
            fitz.Point(content_right - tw_width, y_text),
            text,
            font=font,
            fontsize=header_size,
        )
        tw.write_text(page, color=_GRAY_COLOR)

    # Separator line
    page.draw_line(
        fitz.Point(content_left, margin_top + 1.0 * _PT_PER_CM),
        fitz.Point(content_right, margin_top + 1.0 * _PT_PER_CM),
        color=(0.8, 0.8, 0.8),
        width=0.5,
    )


def _draw_footer(
    page: fitz.Page,
    page_num: int,
    *,
    settings: dict[str, Any] | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
    margin_bottom: float | None = None,
    meta: Any = None,
) -> None:
    """Draw footer with manifest-driven left/center/right text (P0-4).

    Supports variable substitution including {page_number}.
    """
    if settings is None:
        settings = {}
    if page_width is None:
        page_width = _A4_WIDTH_PT
    if page_height is None:
        page_height = _A4_HEIGHT_PT
    if margin_bottom is None:
        margin_bottom = _MARGIN_PT

    footer_left = settings.get("footer_left", "")
    footer_center = settings.get("footer_center", "")
    footer_right = settings.get("footer_right", "")

    # Legacy fallback: if all empty, use "— {page_number} —"
    if not footer_left and not footer_center and not footer_right:
        footer_center = f"— {page_num} —"

    footer_size = settings.get("footer_size", _FOOTER_SIZE)
    content_left = settings.get("margin_left_pt", _MARGIN_PT)
    content_right = page_width - settings.get("margin_right_pt", _MARGIN_PT)
    content_width = content_right - content_left
    font = _get_cjk_font()
    y_text = page_height - margin_bottom + 0.3 * _PT_PER_CM

    # Left footer
    if footer_left:
        text = _substitute_vars(footer_left, meta, page_num) if meta else footer_left
        tw = fitz.TextWriter(page.rect)
        tw.append(fitz.Point(content_left, y_text), text, font=font, fontsize=footer_size)
        tw.write_text(page, color=_GRAY_COLOR)

    # Center footer
    if footer_center:
        text = _substitute_vars(footer_center, meta, page_num) if meta else footer_center
        tw_width = font.text_length(text, fontsize=footer_size)
        tw = fitz.TextWriter(page.rect)
        tw.append(
            fitz.Point(content_left + (content_width - tw_width) / 2, y_text),
            text,
            font=font,
            fontsize=footer_size,
        )
        tw.write_text(page, color=_GRAY_COLOR)

    # Right footer
    if footer_right:
        text = _substitute_vars(footer_right, meta, page_num) if meta else footer_right
        tw_width = font.text_length(text, fontsize=footer_size)
        tw = fitz.TextWriter(page.rect)
        tw.append(
            fitz.Point(content_right - tw_width, y_text),
            text,
            font=font,
            fontsize=footer_size,
        )
        tw.write_text(page, color=_GRAY_COLOR)


def _draw_draft_watermark(
    page: fitz.Page,
    text: str = "DRAFT",
    fontsize: float = 60,
    *,
    settings: dict[str, Any] | None = None,
) -> None:
    """Draw DRAFT watermark centered on the page.

    Supports manifest-driven color, opacity, angle (P0-6).
    Uses rotation matrix and fill_opacity for proper rendering.
    """
    import math

    wm_angle: float = 45
    wm_opacity: float = 0.3
    if settings is not None:
        text = settings.get("draft_watermark_text", text)
        fontsize = settings.get("draft_watermark_size", fontsize)
        wm_color_str = settings.get("draft_watermark_color", "#CCCCCC")
        wm_opacity = settings.get("draft_watermark_opacity", 0.3)
        wm_angle = settings.get("draft_watermark_angle", 45)
        # Validate ranges
        wm_opacity = max(0.0, min(1.0, float(wm_opacity)))
        wm_angle = float(wm_angle)
        # Convert hex color to RGB
        base_color = _hex_to_rgb(wm_color_str)
        color = base_color  # full color; opacity handled by fill_opacity param
    else:
        color = (0.8, 0.8, 0.8)

    font = _get_cjk_font()
    cx = page.rect.width / 2
    cy = page.rect.height / 2

    # P0-6: Build rotation matrix for watermark text around page center.
    # PyMuPDF morph requires matrix[4] == matrix[5] == 0, so use pure
    # rotation matrix and let the morph point handle the center offset.
    angle_rad = math.radians(wm_angle)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    # Pure rotation matrix (no translation) — morph point handles offset
    mat = fitz.Matrix(cos_a, sin_a, -sin_a, cos_a, 0, 0)

    text_width = font.text_length(text, fontsize=fontsize)
    text_x = cx - text_width / 2
    text_y = cy

    # P0-6: Use insert_text with morph=(center, rotation_matrix) for rotation
    # and fill_opacity for transparency.
    page.insert_text(
        fitz.Point(text_x, text_y),
        text,
        fontname="cjk_font",
        fontfile=_find_cjk_font(),
        fontsize=fontsize,
        color=color,
        morph=(fitz.Point(cx, cy), mat),
        fill_opacity=wm_opacity,
    )


# ---------------------------------------------------------------------------
# Context-aware text drawing (P0-6)
# ---------------------------------------------------------------------------


def _draw_wrapped_text(
    ctx: PdfRenderContext,
    text: str,
    fontsize: float,
    max_width: float,
    color: tuple[float, float, float] = _TEXT_COLOR,
) -> float:
    """Draw wrapped text with page overflow detection.

    Unlike _insert_text which draws on a single page, this function
    uses ctx.ensure_space() to create new pages when text overflows.
    Returns the new y position after all text is drawn.
    """
    font = fitz.Font(fontfile=ctx.font_path) if ctx.font_path else _get_cjk_font()
    line_height = fontsize * 1.4
    lines = text.split("\n")

    for line in lines:
        if not line:
            ctx.y += line_height
            ctx.ensure_space(line_height)
            continue
        # Character-level wrapping
        current_line = ""
        for char in line:
            test = current_line + char
            if font.text_length(test, fontsize=fontsize) > max_width and current_line:
                ctx.ensure_space(line_height)
                # Draw current_line
                tw = fitz.TextWriter(ctx.current_page.rect)
                tw.append(
                    fitz.Point(ctx.content_left, ctx.y),
                    current_line,
                    font=font,
                    fontsize=fontsize,
                )
                tw.write_text(ctx.current_page, color=color)
                ctx.y += line_height
                current_line = char
            else:
                current_line = test
        if current_line:
            ctx.ensure_space(line_height)
            tw = fitz.TextWriter(ctx.current_page.rect)
            tw.append(
                fitz.Point(ctx.content_left, ctx.y), current_line, font=font, fontsize=fontsize
            )
            tw.write_text(ctx.current_page, color=color)
            ctx.y += line_height

    return ctx.y


# ---------------------------------------------------------------------------
# Page Context (P0-1 / P0-6)
# ---------------------------------------------------------------------------


class PdfRenderContext:
    """Page state management for PDF rendering.

    Tracks the current page, Y position, and provides ensure_space()
    to automatically create new pages when content overflows.

    P0-5: Supports landscape orientation per-section.
    """

    def __init__(
        self,
        doc: fitz.Document,
        settings: dict[str, Any],
        is_draft: bool,
        metadata: RenderMetadata,
        font_path: str,
    ):
        self.doc = doc
        self.settings = settings
        self.is_draft = is_draft
        self.metadata = metadata
        self.font_path = font_path
        self._portrait_width = settings["page_width_pt"]
        self._portrait_height = settings["page_height_pt"]
        self.page_width = self._portrait_width
        self.page_height = self._portrait_height
        self.margin_top = settings["margin_top_pt"]
        self.margin_bottom = settings["margin_bottom_pt"]
        self.margin_left = settings["margin_left_pt"]
        self.margin_right = settings["margin_right_pt"]
        self.content_width = self.page_width - self.margin_left - self.margin_right
        self.content_top = self.margin_top + 1.5 * _PT_PER_CM
        self.page: fitz.Page | None = None
        self.y = 0.0
        self.page_num = 0
        # P0-5: orientation tracking
        self.orientation = settings.get("orientation", "portrait")
        self.landscape_sections = settings.get("landscape_sections", [])

    def set_orientation(self, orientation: str) -> None:
        """Switch page orientation (portrait or landscape).

        Swaps page_width/page_height and recalculates content_width/content_top.
        """
        self.orientation = orientation
        if orientation == "landscape":
            self.page_width = self._portrait_height  # swap
            self.page_height = self._portrait_width
        else:
            self.page_width = self._portrait_width
            self.page_height = self._portrait_height
        self.content_width = self.page_width - self.margin_left - self.margin_right
        self.content_top = self.margin_top + 1.5 * _PT_PER_CM

    def should_be_landscape(self, section_key: str) -> bool:
        """Check if a section should be rendered in landscape orientation."""
        # Check per-table config first
        table_configs = self.settings.get("table_configs", {})
        section_config = table_configs.get(section_key, {})
        if section_config.get("orientation") == "landscape":
            return True
        # Check landscape_sections list
        return section_key in self.landscape_sections

    def new_page(self) -> None:
        """Create new page with header, footer, watermark."""
        self.page = self.doc.new_page(width=self.page_width, height=self.page_height)
        self.page_num += 1
        self.y = self.content_top
        # Draw header (P0-4: pass meta for variable substitution)
        _draw_header(
            self.page,
            self.metadata.project_name,
            self.metadata.report_type,
            settings=self.settings,
            margin_left=self.margin_left,
            page_width=self.page_width,
            margin_top=self.margin_top,
            meta=self.metadata,
            page_num=self.page_num,
        )
        # Draw footer (P0-4: pass meta for variable substitution)
        _draw_footer(
            self.page,
            self.page_num,
            settings=self.settings,
            page_width=self.page_width,
            page_height=self.page_height,
            margin_bottom=self.margin_bottom,
            meta=self.metadata,
        )
        # Draw watermark (P0-4: pass settings for manifest-driven color/opacity)
        if self.is_draft:
            _draw_draft_watermark(
                self.page,
                text=self.settings.get("draft_watermark_text", "DRAFT"),
                fontsize=self.settings.get("draft_watermark_size", 60),
                settings=self.settings,
            )

    def ensure_space(self, required_height: float) -> bool:
        """Check if there's enough space. If not, create new page.

        Returns True if space is available.
        """
        bottom_limit = self.page_height - self.margin_bottom
        if self.y + required_height > bottom_limit:
            self.new_page()
            return True
        return True

    @property
    def content_left(self) -> float:
        """Left edge of the content area."""
        return float(self.margin_left)

    @property
    def current_page(self) -> fitz.Page:
        """Return the current page, asserting it exists."""
        assert self.page is not None, "No current page — call new_page() first"
        return self.page


# ---------------------------------------------------------------------------
# Table Drawing with Pagination (P0-6)
# ---------------------------------------------------------------------------


def _wrap_cell_text(
    text: str,
    font: fitz.Font,
    fontsize: float,
    max_width: float,
) -> list[str]:
    """Wrap text to fit within max_width, returning list of lines."""
    if not text:
        return [""]

    lines: list[str] = []
    current_line = ""
    for char in text:
        test = current_line + char
        text_width = font.text_length(test, fontsize=fontsize)
        if text_width > max_width and current_line:
            lines.append(current_line)
            current_line = char
        else:
            current_line = test
    if current_line:
        lines.append(current_line)
    return lines if lines else [""]


def _measure_row_height(
    cells: list[str],
    font: fitz.Font,
    fontsize: float,
    col_width: float,
    base_height: float,
    col_widths: list[float] | None = None,
) -> float:
    """Measure the actual height a row needs based on text wrapping.

    If col_widths is provided, use per-column widths; otherwise use col_width.
    """
    max_lines = 1
    cell_padding = 6  # left + right padding
    for ci, cell_text in enumerate(cells):
        cw = col_widths[ci] if col_widths and ci < len(col_widths) else col_width
        usable_width = cw - cell_padding
        lines = _wrap_cell_text(cell_text, font, fontsize, usable_width)
        if len(lines) > max_lines:
            max_lines = len(lines)
    return base_height * max_lines


def _draw_table(
    ctx: PdfRenderContext,
    x: float,
    y: float,
    table: RenderTable,
    max_width: float | None = None,
    *,
    section_key: str = "",
    font_path: str | None = None,
) -> float:
    """Draw a table on the page and return the new y position.

    Supports pagination: when a row won't fit on the current page, a new page
    is created. On page break the header row (and unit row if present) are redrawn.

    P0-4: Accepts section_key for per-section table configuration from manifest.
    """
    if max_width is None:
        max_width = ctx.content_width

    num_cols = len(table.headers)
    if num_cols == 0:
        return y

    # P0-4: Load per-section table config
    table_configs = ctx.settings.get("table_configs", {})
    section_config = table_configs.get(section_key, {})
    columns_config = section_config.get("columns", [])
    repeat_header = section_config.get(
        "repeat_header", ctx.settings.get("table_repeat_header", True)
    )
    show_unit_row = section_config.get("unit_row", True)

    # P0-4: Validate column count vs manifest columns_config
    if columns_config and len(columns_config) != num_cols:
        raise ValueError(
            f"columns_config count ({len(columns_config)}) != headers count "
            f"({num_cols}) for section_key={section_key!r}"
        )

    # P0-4: Compute column widths from width_ratio if available
    if columns_config and any(c.get("width_ratio", 0) for c in columns_config):
        # Validate width_ratio values: all must be positive numbers
        for ci, col_cfg in enumerate(columns_config):
            wr = col_cfg.get("width_ratio", 1.0)
            if not isinstance(wr, (int, float)) or wr <= 0:
                raise ValueError(
                    f"width_ratio for column {ci} must be a positive number, "
                    f"got {wr!r} in section_key={section_key!r}"
                )
        total_ratio = sum(c.get("width_ratio", 1.0) for c in columns_config)
        if total_ratio <= 0:
            raise ValueError(
                f"All width_ratios are zero or negative for section_key={section_key!r}"
            )
        col_widths = [(c.get("width_ratio", 1.0) / total_ratio) * max_width for c in columns_config]
    else:
        col_widths = [max_width / num_cols] * num_cols

    # P0-4: Column alignment from config (overridden by cell.align)
    col_aligns: list[str] = ["left"] * num_cols
    if columns_config and len(columns_config) == num_cols:
        for ci, col_cfg in enumerate(columns_config):
            col_aligns[ci] = col_cfg.get("align", "left")

    base_row_height = _LINE_HEIGHT + 4

    # Check if we need a unit row (P0-4: respect show_unit_row config)
    has_unit_row = show_unit_row and bool(table.unit_row and any(u for u in table.unit_row))

    font = fitz.Font(fontfile=font_path) if font_path else _get_cjk_font()
    header_font_size = ctx.settings.get("table_header_size", _TABLE_HEADER_SIZE)
    body_font_size = ctx.settings.get("table_body_size", _TABLE_BODY_SIZE)

    def _draw_row(
        row_y: float,
        cells: list[RenderTableCell],
        is_header: bool = False,
        is_unit: bool = False,
    ) -> float:
        """Draw a single row of cells, return new y after the row."""
        row_font_size = header_font_size if is_header else body_font_size
        cell_texts = [c.value for c in cells]
        row_height = _measure_row_height(
            cell_texts,
            font,
            row_font_size,
            col_widths[0],
            base_row_height,
            col_widths=col_widths,
        )

        # Background
        bg_color = _LIGHT_BLUE if is_header else _LIGHT_GRAY if is_unit else None
        if bg_color:
            rect = fitz.Rect(x, row_y, x + max_width, row_y + row_height)
            ctx.current_page.draw_rect(rect, color=None, fill=bg_color)

        # Grid lines (horizontal)
        ctx.current_page.draw_line(
            fitz.Point(x, row_y),
            fitz.Point(x + max_width, row_y),
            color=(0.7, 0.7, 0.7),
            width=0.5,
        )

        # Grid lines (vertical) and text
        cell_padding = 6  # left+right padding
        col_x = x
        for col_idx, cell in enumerate(cells):
            cell_text = cell.value
            cw = col_widths[col_idx]
            # Vertical line
            ctx.current_page.draw_line(
                fitz.Point(col_x, row_y),
                fitz.Point(col_x, row_y + row_height),
                color=(0.7, 0.7, 0.7),
                width=0.5,
            )
            # Cell text with wrapping
            usable_width = cw - cell_padding
            wrapped_lines = _wrap_cell_text(cell_text, font, row_font_size, usable_width)
            # P0-4: Cell alignment overrides column default
            alignment = (
                cell.align
                if cell.align != "left"
                else (col_aligns[col_idx] if col_idx < len(col_aligns) else "left")
            )
            for line_index, wline in enumerate(wrapped_lines):
                text_y_pos = row_y + _LINE_HEIGHT * (line_index + 1)
                wline_width = font.text_length(wline, fontsize=row_font_size)
                if alignment == "right":
                    text_x = col_x + cw - cell_padding / 2 - wline_width
                elif alignment == "center":
                    text_x = col_x + (cw - wline_width) / 2
                else:
                    text_x = col_x + 3
                tw = fitz.TextWriter(ctx.current_page.rect)
                tw.append(
                    fitz.Point(text_x, text_y_pos),
                    wline,
                    font=font,
                    fontsize=row_font_size,
                )
                tw.write_text(page=ctx.current_page, color=_TEXT_COLOR)
            col_x += cw

        # Right border
        ctx.current_page.draw_line(
            fitz.Point(x + max_width, row_y),
            fitz.Point(x + max_width, row_y + row_height),
            color=(0.7, 0.7, 0.7),
            width=0.5,
        )

        # Bottom border
        ctx.current_page.draw_line(
            fitz.Point(x, row_y + row_height),
            fitz.Point(x + max_width, row_y + row_height),
            color=(0.7, 0.7, 0.7),
            width=0.5,
        )

        return row_y + row_height

    def _draw_header_group(row_y: float) -> float:
        """Draw header + unit row as an inseparable group (P0-3)."""
        header_texts = [h for h in table.headers]
        header_height = _measure_row_height(
            header_texts,
            font,
            header_font_size,
            col_widths[0],
            base_row_height,
            col_widths=col_widths,
        )
        unit_height = 0.0
        unit_cell_texts: list[str] = []
        if has_unit_row:
            unit_cell_texts = [f"({u})" if u else "" for u in table.unit_row]
            unit_height = _measure_row_height(
                unit_cell_texts,
                font,
                body_font_size,
                col_widths[0],
                base_row_height,
                col_widths=col_widths,
            )
        # Ensure space for the entire header group (P0-3: inseparable)
        group_height = header_height + unit_height
        ctx.ensure_space(group_height)
        row_y = ctx.y  # sync after ensure_space
        # Create RenderTableCell objects with manifest column alignment
        header_cells = [
            RenderTableCell(
                value=h,
                align=col_aligns[i] if i < len(col_aligns) else "left",
            )
            for i, h in enumerate(table.headers)
        ]
        row_y = _draw_row(row_y, header_cells, is_header=True)
        if has_unit_row:
            unit_cells = [
                RenderTableCell(
                    value=f"({u})" if u else "",
                    align=col_aligns[i] if i < len(col_aligns) else "left",
                )
                for i, u in enumerate(table.unit_row)
            ]
            row_y = _draw_row(row_y, unit_cells, is_unit=True)
        return row_y

    def _draw_row_split(
        row_y: float,
        cells: list[RenderTableCell],
        is_header: bool = False,
        is_unit: bool = False,
    ) -> float:
        """Draw a row, splitting across pages if it's too tall (P0-7)."""
        row_font_size = header_font_size if is_header else body_font_size
        cell_texts = [c.value for c in cells]
        row_height = _measure_row_height(
            cell_texts,
            font,
            row_font_size,
            col_widths[0],
            base_row_height,
            col_widths=col_widths,
        )
        available = ctx.page_height - ctx.margin_bottom - row_y

        if row_height <= available:
            # Row fits on current page — use normal path
            return _draw_row(row_y, cells, is_header=is_header, is_unit=is_unit)

        # Row doesn't fit on current page. Check if it fits on a fresh page.
        fresh_available = ctx.page_height - ctx.margin_bottom - ctx.content_top
        if row_height <= fresh_available:
            # Fits on a fresh page — caller should have started a new page.
            # If we still don't have space, it means caller didn't start one.
            # Just draw normally (it will go past page boundary but caller
            # handles the page break before calling us).
            return _draw_row(row_y, cells, is_header=is_header, is_unit=is_unit)

        # Row too tall even for a fresh page — must split across pages (P0-7)
        cell_padding = 6

        # Pre-wrap all cells using per-column widths
        all_wrapped: list[list[str]] = []
        max_lines = 0
        for ci, cell in enumerate(cells):
            cw = col_widths[ci]
            usable_width = cw - cell_padding
            lines = _wrap_cell_text(cell.value, font, row_font_size, usable_width)
            all_wrapped.append(lines)
            if len(lines) > max_lines:
                max_lines = len(lines)

        # How many lines fit on current page?
        lines_per_page = max(1, int(available / _LINE_HEIGHT))
        line_idx = 0

        while line_idx < max_lines:
            chunk_lines = min(lines_per_page, max_lines - line_idx)
            chunk_height = chunk_lines * _LINE_HEIGHT + 4  # +4 for padding

            # Ensure space for this chunk
            if ctx.y + chunk_height > ctx.page_height - ctx.margin_bottom:
                ctx.new_page()
                row_y = ctx.y
                if repeat_header:
                    row_y = _draw_header_group(row_y)
                ctx.y = row_y

            # Draw chunk: background, grid, text for this line range
            # Top border
            ctx.current_page.draw_line(
                fitz.Point(x, row_y),
                fitz.Point(x + max_width, row_y),
                color=(0.7, 0.7, 0.7),
                width=0.5,
            )

            # Background
            if line_idx == 0:
                bg_color = _LIGHT_BLUE if is_header else _LIGHT_GRAY if is_unit else None
            else:
                bg_color = None  # continuation chunks have no bg
            if bg_color:
                rect = fitz.Rect(x, row_y, x + max_width, row_y + chunk_height)
                ctx.current_page.draw_rect(rect, color=None, fill=bg_color)

            # Vertical lines + text for this chunk
            col_x = x
            for col_idx, cell_lines in enumerate(all_wrapped):
                cw = col_widths[col_idx]
                ctx.current_page.draw_line(
                    fitz.Point(col_x, row_y),
                    fitz.Point(col_x, row_y + chunk_height),
                    color=(0.7, 0.7, 0.7),
                    width=0.5,
                )
                # Draw lines in this chunk
                alignment = (
                    cells[col_idx].align
                    if cells[col_idx].align != "left"
                    else (col_aligns[col_idx] if col_idx < len(col_aligns) else "left")
                )
                for li in range(line_idx, min(line_idx + chunk_lines, len(cell_lines))):
                    text_y_pos = row_y + _LINE_HEIGHT * (li - line_idx + 1)
                    wline = cell_lines[li]
                    wline_width = font.text_length(wline, fontsize=row_font_size)
                    if alignment == "right":
                        text_x = col_x + cw - cell_padding / 2 - wline_width
                    elif alignment == "center":
                        text_x = col_x + (cw - wline_width) / 2
                    else:
                        text_x = col_x + 3
                    tw = fitz.TextWriter(ctx.current_page.rect)
                    tw.append(
                        fitz.Point(text_x, text_y_pos),
                        wline,
                        font=font,
                        fontsize=row_font_size,
                    )
                    tw.write_text(page=ctx.current_page, color=_TEXT_COLOR)
                col_x += cw

            # Right border
            ctx.current_page.draw_line(
                fitz.Point(x + max_width, row_y),
                fitz.Point(x + max_width, row_y + chunk_height),
                color=(0.7, 0.7, 0.7),
                width=0.5,
            )

            # Bottom border
            ctx.current_page.draw_line(
                fitz.Point(x, row_y + chunk_height),
                fitz.Point(x + max_width, row_y + chunk_height),
                color=(0.7, 0.7, 0.7),
                width=0.5,
            )

            row_y += chunk_height
            ctx.y = row_y
            line_idx += chunk_lines

            # Recalculate available lines for next chunk (after page break)
            lines_per_page = max(
                1, int((ctx.page_height - ctx.margin_bottom - ctx.y) / _LINE_HEIGHT)
            )

        return row_y

    current_y = y

    # --- Draw header group on first page (P0-3) ---
    current_y = _draw_header_group(current_y)
    ctx.y = current_y  # sync ctx.y after header group

    # --- Draw data rows with overflow detection ---
    for row_data in table.rows:
        cells = list(row_data)  # keep full RenderTableCell objects
        cell_texts = [cell.value for cell in row_data]
        row_height = _measure_row_height(
            cell_texts,
            font,
            body_font_size,
            col_widths[0],
            base_row_height,
            col_widths=col_widths,
        )

        # Check if this row fits; if not, page break
        available = ctx.page_height - ctx.margin_bottom - current_y
        if row_height > available:
            ctx.new_page()
            current_y = ctx.y  # sync with new page Y position
            if repeat_header:
                # Redraw header group on new page
                current_y = _draw_header_group(current_y)
            ctx.y = current_y  # sync ctx.y

        # Use split-aware drawing for rows that might be too tall
        current_y = _draw_row_split(current_y, cells)
        ctx.y = current_y  # sync ctx.y after each data row (P0-3)

    return current_y + 4  # small gap after table


# ---------------------------------------------------------------------------
# PDF Renderer
# ---------------------------------------------------------------------------


class PdfRenderer:
    """Render a ReportRenderModel to PDF bytes."""

    def render(self, model: ReportRenderModel, *, is_draft: bool = False) -> bytes:
        """Render the model to PDF bytes.

        Parameters
        ----------
        model:
            The complete render model.
        is_draft:
            If True, add a DRAFT watermark.

        Returns
        -------
        bytes
            The raw .pdf file content.
        """
        # P0-10: Load template manifest settings
        settings = _load_manifest_settings(model)

        # Get CJK font path for all text
        font_path = _find_cjk_font()

        doc = fitz.open()

        # ---- PDF metadata ----
        meta = model.metadata
        doc.set_metadata(
            {
                "title": meta.project_name or "Report",
                "subject": meta.report_type,
                "author": meta.generated_by,
                "keywords": (
                    f"revision={meta.revision_number}"
                    f";hash={meta.content_hash_short}"
                    f";template={meta.template_version}"
                ),
                "creator": "Cold Storage Planning Agent",
            }
        )

        # ---- Render context ----
        ctx = PdfRenderContext(
            doc=doc,
            settings=settings,
            is_draft=is_draft,
            metadata=meta,
            font_path=font_path,
        )

        # ---- Cover page ----
        cover_page = doc.new_page(
            width=settings["page_width_pt"], height=settings["page_height_pt"]
        )
        self._draw_cover(
            cover_page,
            meta,
            settings=settings,
            is_draft=is_draft,
            font_path=font_path,
        )

        # ---- Content sections ----
        for section in model.sections:
            # P0-3: Resolve orientation BEFORE creating the page
            orientation = self._resolve_orientation(section, ctx)
            ctx.set_orientation(orientation)
            ctx.new_page()
            self._draw_section_content(ctx, section)

        # ---- Finalize ----
        pdf_bytes: bytes = doc.tobytes()
        doc.close()
        return bytes(pdf_bytes)

    # ------------------------------------------------------------------
    # Cover page
    # ------------------------------------------------------------------
    def _draw_cover(
        self,
        page: fitz.Page,
        meta: Any,
        *,
        settings: dict[str, Any],
        is_draft: bool = False,
        font_path: str | None = None,
    ) -> None:
        """Draw the cover page."""
        draft_wm_text = settings.get("draft_watermark_text", "DRAFT")
        draft_wm_size = settings.get("draft_watermark_size", 60)
        if is_draft:
            _draw_draft_watermark(
                page, text=draft_wm_text, fontsize=draft_wm_size, settings=settings
            )

        page_width = settings["page_width_pt"]
        page_height = settings["page_height_pt"]
        cx = page_width / 2

        font = _get_cjk_font()
        y = page_height * 0.35

        # Project name
        name_text = meta.project_name or "项目报告"
        name_size = 26
        name_width = font.text_length(name_text, fontsize=name_size)
        tw = fitz.TextWriter(page.rect)
        tw.append(
            fitz.Point(cx - name_width / 2, y),
            name_text,
            font=font,
            fontsize=name_size,
        )
        tw.write_text(page, color=_HEADING_COLOR)

        # Report type
        y += 40
        type_text = meta.report_type
        type_size = 18
        type_width = font.text_length(type_text, fontsize=type_size)
        tw2 = fitz.TextWriter(page.rect)
        tw2.append(
            fitz.Point(cx - type_width / 2, y),
            type_text,
            font=font,
            fontsize=type_size,
        )
        tw2.write_text(page, color=_GRAY_COLOR)

        # Version and date — P0-4: use clean ISO string, no slicing
        y += 30
        generated_at = meta.generated_at if meta.generated_at else ""
        # Extract just the date portion (first 10 chars of ISO string)
        date_display = generated_at[:10] if len(generated_at) >= 10 else generated_at
        ver_text = f"版本 {meta.revision_number}  |  {date_display}"
        ver_size = 12
        ver_width = font.text_length(ver_text, fontsize=ver_size)
        tw3 = fitz.TextWriter(page.rect)
        tw3.append(
            fitz.Point(cx - ver_width / 2, y),
            ver_text,
            font=font,
            fontsize=ver_size,
        )
        tw3.write_text(page, color=_GRAY_COLOR)

    # ------------------------------------------------------------------
    # Section rendering
    # ------------------------------------------------------------------
    def _draw_section_content(
        self,
        ctx: PdfRenderContext,
        section: RenderSection,
    ) -> None:
        """Draw section CONTENT on the current page (no page creation).

        Orientation and page creation are handled by the caller (render()).
        """
        content_left = ctx.content_left
        content_width = ctx.content_width
        settings = ctx.settings

        # Heading
        heading_sizes = {
            1: settings.get("heading1_size", _HEADING1_SIZE),
            2: settings.get("heading2_size", _HEADING2_SIZE),
            3: settings.get("heading3_size", _HEADING3_SIZE),
        }

        if section.is_empty:
            heading_size = heading_sizes.get(section.level, _HEADING1_SIZE)
            ctx.ensure_space(_LINE_HEIGHT + _LINE_HEIGHT + 10)
            ctx.y = _insert_text(
                ctx.current_page,
                content_left,
                ctx.y,
                section.title,
                fontsize=heading_size,
                color=_HEADING_COLOR,
                font_path=ctx.font_path,
                max_width=content_width,
            )
            ctx.y += 4
            # P0-4: Read placeholder text from manifest empty_section_behavior
            empty_behavior = settings.get("empty_section_behavior", {})
            placeholder_texts = empty_behavior.get("placeholder_text", {})
            reason_text = placeholder_texts.get(
                section.empty_reason,
                settings.get("placeholder_text", "该部分内容不可用"),
            )
            ctx.y = _insert_text(
                ctx.current_page,
                content_left + 10,
                ctx.y,
                f"（{reason_text}）",
                fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                color=_GRAY_COLOR,
                font_path=ctx.font_path,
                max_width=content_width,
            )
            return

        # Heading
        heading_size = heading_sizes.get(section.level, _HEADING1_SIZE)
        ctx.ensure_space(_LINE_HEIGHT + 6)
        ctx.y = _insert_text(
            ctx.current_page,
            content_left,
            ctx.y,
            section.title,
            fontsize=heading_size,
            color=_HEADING_COLOR,
            font_path=ctx.font_path,
            max_width=content_width,
        )
        ctx.y += 6

        if section.content_type == "text" and section.text:
            # P0-6: Use context-aware text drawing for long text pagination
            ctx.y = _draw_wrapped_text(
                ctx,
                section.text,
                fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                max_width=content_width,
            )

        elif section.content_type == "metrics" and section.metrics:
            # P0-1: Render each metric as: label: display_value unit
            for metric in section.metrics:
                label_text = f"{metric.label}: {metric.display_value}"
                if metric.unit and metric.unit not in metric.display_value:
                    label_text += f" {metric.unit}"
                ctx.ensure_space(_LINE_HEIGHT + 4)
                ctx.y = _insert_text(
                    ctx.current_page,
                    content_left,
                    ctx.y,
                    label_text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    font_path=ctx.font_path,
                    max_width=content_width,
                )
            # Backward compat: also render primary number
            if section.number:
                ctx.ensure_space(_LINE_HEIGHT + 4)
                ctx.y = _insert_number(
                    ctx.current_page,
                    content_left,
                    ctx.y,
                    section.number.display,
                    section.number.unit,
                    font_path=ctx.font_path,
                )
            if section.text:
                ctx.y = _draw_wrapped_text(
                    ctx,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    max_width=content_width,
                )

        elif section.content_type == "number" and section.number:
            num = section.number
            ctx.ensure_space(_LINE_HEIGHT + 4)
            ctx.y = _insert_number(
                ctx.current_page,
                content_left,
                ctx.y,
                num.display,
                num.unit,
                font_path=ctx.font_path,
            )
            if section.text:
                ctx.y = _draw_wrapped_text(
                    ctx,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    max_width=content_width,
                )

        elif section.content_type == "table" and section.table:
            if section.text:
                ctx.ensure_space(_LINE_HEIGHT + 4)
                ctx.y = _draw_wrapped_text(
                    ctx,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    max_width=content_width,
                )
                ctx.y += 4
            ctx.y = _draw_table(
                ctx,
                content_left,
                ctx.y,
                section.table,
                max_width=content_width,
                section_key=section.section_key,
                font_path=ctx.font_path,
            )

        elif section.content_type == "finding":
            if section.text:
                ctx.ensure_space(_LINE_HEIGHT + 4)
                ctx.y = _draw_wrapped_text(
                    ctx,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    max_width=content_width,
                )
                ctx.y += 4
            if section.table:
                ctx.y = _draw_table(
                    ctx,
                    content_left,
                    ctx.y,
                    section.table,
                    max_width=content_width,
                    section_key=section.section_key,
                    font_path=ctx.font_path,
                )

        # P0-8: Render paragraphs (approval text, etc.)
        if section.paragraphs:
            for para_text in section.paragraphs:
                ctx.ensure_space(_LINE_HEIGHT + 4)
                ctx.y = _draw_wrapped_text(
                    ctx,
                    para_text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    max_width=content_width,
                )
                ctx.y += 2

    # ------------------------------------------------------------------
    # Orientation resolution (P0-3)
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_orientation(
        section: RenderSection,
        ctx: PdfRenderContext,
    ) -> str:
        """Determine the orientation for a section.

        Checks table_configs[key].orientation first, then landscape_sections list.
        """
        # Check per-table config first
        table_configs = ctx.settings.get("table_configs", {})
        section_config = table_configs.get(section.section_key, {})
        table_orientation: str = section_config.get("orientation", "")
        if table_orientation in ("landscape", "portrait"):
            return table_orientation
        # Check landscape_sections list
        if section.section_key in ctx.landscape_sections:
            return "landscape"
        # Default to context's current orientation (usually portrait)
        return str(ctx.orientation)
