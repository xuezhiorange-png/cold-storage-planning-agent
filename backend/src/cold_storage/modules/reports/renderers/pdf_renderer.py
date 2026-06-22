"""PDF renderer — produces a .pdf file from a ReportRenderModel.

Uses PyMuPDF (fitz).  Text is selectable (no rasterization).  A4 layout
with headers, footers, and optional DRAFT watermark.

P0-1: Metrics content type rendering.
P0-6: Real pagination with page overflow detection and table header repeat.
P0-9: Uses system CJK font for Chinese text rendering.
P0-10: Template manifest controls page size, margins, fonts, styles, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import fitz  # PyMuPDF

if TYPE_CHECKING:
    from cold_storage.modules.reports.domain.render_model import (
        RenderSection,
        RenderTable,
        ReportRenderModel,
    )

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

    # Table column definitions
    settings["table_columns"] = render_settings.get("tables", {}).get("columns", {})

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


def _draw_header(
    page: fitz.Page,
    project_name: str,
    report_type: str,
    *,
    settings: dict[str, Any] | None = None,
    margin_left: float | None = None,
    page_width: float | None = None,
    margin_top: float | None = None,
) -> None:
    """Draw header on page with configurable margins and sizes."""
    if settings is None:
        settings = {}
    if margin_left is None:
        margin_left = _MARGIN_PT
    if page_width is None:
        page_width = _A4_WIDTH_PT
    if margin_top is None:
        margin_top = _MARGIN_PT

    header_size = settings.get("header_size", _HEADER_SIZE)
    content_left = margin_left
    content_right = page_width - settings.get("margin_right_pt", _MARGIN_PT)
    header_text = f"{project_name} — {report_type}"
    font = _get_cjk_font()
    text_width = font.text_length(header_text, fontsize=header_size)
    tw = fitz.TextWriter(page.rect)
    tw.append(
        fitz.Point(content_right - text_width, margin_top + 0.5 * _PT_PER_CM),
        header_text,
        font=font,
        fontsize=header_size,
    )
    tw.write_text(page, color=_GRAY_COLOR)
    # Line under header
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
) -> None:
    """Draw page number in footer with configurable margins and sizes."""
    if settings is None:
        settings = {}
    if page_width is None:
        page_width = _A4_WIDTH_PT
    if page_height is None:
        page_height = _A4_HEIGHT_PT
    if margin_bottom is None:
        margin_bottom = _MARGIN_PT

    footer_size = settings.get("footer_size", _FOOTER_SIZE)
    page_text = f"— {page_num} —"
    font = _get_cjk_font()
    text_width = font.text_length(page_text, fontsize=footer_size)
    tw = fitz.TextWriter(page.rect)
    tw.append(
        fitz.Point(
            (page_width - text_width) / 2,
            page_height - margin_bottom + 0.3 * _PT_PER_CM,
        ),
        page_text,
        font=font,
        fontsize=footer_size,
    )
    tw.write_text(page, color=_GRAY_COLOR)


def _draw_draft_watermark(
    page: fitz.Page,
    text: str = "DRAFT",
    fontsize: float = 60,
) -> None:
    """Draw DRAFT watermark centered on the page."""
    font = _get_cjk_font()
    cx = page.rect.width / 2
    cy = page.rect.height / 2
    text_width = font.text_length(text, fontsize=fontsize)
    tw = fitz.TextWriter(page.rect)
    tw.append(
        fitz.Point(cx - text_width / 2, cy),
        text,
        font=font,
        fontsize=fontsize,
    )
    tw.write_text(page, color=(0.8, 0.8, 0.8))


# ---------------------------------------------------------------------------
# Page Context (P0-1 / P0-6)
# ---------------------------------------------------------------------------


class PdfRenderContext:
    """Page state management for PDF rendering.

    Tracks the current page, Y position, and provides ensure_space()
    to automatically create new pages when content overflows.
    """

    def __init__(
        self,
        doc: fitz.Document,
        settings: dict[str, Any],
        is_draft: bool,
        metadata: Any,
        font_path: str,
    ):
        self.doc = doc
        self.settings = settings
        self.is_draft = is_draft
        self.metadata = metadata
        self.font_path = font_path
        self.page_width = settings["page_width_pt"]
        self.page_height = settings["page_height_pt"]
        self.margin_top = settings["margin_top_pt"]
        self.margin_bottom = settings["margin_bottom_pt"]
        self.margin_left = settings["margin_left_pt"]
        self.margin_right = settings["margin_right_pt"]
        self.content_width = self.page_width - self.margin_left - self.margin_right
        self.content_top = self.margin_top + 1.5 * _PT_PER_CM
        self.page: fitz.Page | None = None
        self.y = 0.0
        self.page_num = 0

    def new_page(self) -> None:
        """Create new page with header, footer, watermark."""
        self.page = self.doc.new_page(width=self.page_width, height=self.page_height)
        self.page_num += 1
        self.y = self.content_top
        # Draw header
        _draw_header(
            self.page,
            self.metadata.project_name,
            self.metadata.report_type,
            settings=self.settings,
            margin_left=self.margin_left,
            page_width=self.page_width,
            margin_top=self.margin_top,
        )
        # Draw footer
        _draw_footer(
            self.page,
            self.page_num,
            settings=self.settings,
            page_width=self.page_width,
            page_height=self.page_height,
            margin_bottom=self.margin_bottom,
        )
        # Draw watermark
        if self.is_draft:
            _draw_draft_watermark(
                self.page,
                text=self.settings.get("draft_watermark_text", "DRAFT"),
                fontsize=self.settings.get("draft_watermark_size", 60),
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
) -> float:
    """Measure the actual height a row needs based on text wrapping."""
    max_lines = 1
    cell_padding = 6  # left + right padding
    usable_width = col_width - cell_padding
    for cell_text in cells:
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
    font_path: str | None = None,
) -> float:
    """Draw a table on the page and return the new y position.

    Supports pagination: when a row won't fit on the current page, a new page
    is created. On page break the header row (and unit row if present) are redrawn.
    """
    if max_width is None:
        max_width = ctx.content_width

    num_cols = len(table.headers)
    if num_cols == 0:
        return y

    col_width = max_width / num_cols
    base_row_height = _LINE_HEIGHT + 4

    # Check if we need a unit row
    has_unit_row = bool(table.unit_row and any(u for u in table.unit_row))

    font = fitz.Font(fontfile=font_path) if font_path else _get_cjk_font()
    header_font_size = ctx.settings.get("table_header_size", _TABLE_HEADER_SIZE)
    body_font_size = ctx.settings.get("table_body_size", _TABLE_BODY_SIZE)

    def _draw_row(
        row_y: float,
        cells: list[str],
        is_header: bool = False,
        is_unit: bool = False,
    ) -> float:
        """Draw a single row of cells, return new y after the row."""
        row_font_size = header_font_size if is_header else body_font_size
        row_height = _measure_row_height(cells, font, row_font_size, col_width, base_row_height)

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
        for col_idx, cell_text in enumerate(cells):
            col_x = x + col_idx * col_width
            # Vertical line
            ctx.current_page.draw_line(
                fitz.Point(col_x, row_y),
                fitz.Point(col_x, row_y + row_height),
                color=(0.7, 0.7, 0.7),
                width=0.5,
            )
            # Cell text with wrapping
            text_x = col_x + 3
            text_y_pos = row_y
            usable_width = col_width - cell_padding
            wrapped_lines = _wrap_cell_text(cell_text, font, row_font_size, usable_width)
            for wline in wrapped_lines:
                text_y_pos += _LINE_HEIGHT
                tw = fitz.TextWriter(ctx.current_page.rect)
                tw.append(
                    fitz.Point(text_x, text_y_pos),
                    wline,
                    font=font,
                    fontsize=row_font_size,
                )
                tw.write_text(page=ctx.current_page, color=_TEXT_COLOR)

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

    current_y = y

    # --- Draw header row (first page) ---
    header_height = _measure_row_height(
        table.headers, font, header_font_size, col_width, base_row_height
    )
    ctx.ensure_space(header_height)
    current_y = ctx.y  # sync with context after ensure_space
    current_y = _draw_row(current_y, table.headers, is_header=True)

    # --- Draw unit row (if present, first page) ---
    if has_unit_row:
        unit_cells = [f"({u})" if u else "" for u in table.unit_row]
        unit_height = _measure_row_height(
            unit_cells, font, body_font_size, col_width, base_row_height
        )
        ctx.ensure_space(unit_height)
        current_y = ctx.y  # sync with context after ensure_space
        current_y = _draw_row(current_y, unit_cells, is_unit=True)

    # --- Draw data rows with overflow detection ---
    for row_data in table.rows:
        cells = [cell.value for cell in row_data]
        row_height = _measure_row_height(cells, font, body_font_size, col_width, base_row_height)

        # Check if this row fits; if not, page break
        if current_y + row_height > ctx.page_height - ctx.margin_bottom:
            ctx.new_page()
            current_y = ctx.y  # sync with new page Y position
            # Redraw header row on new page
            current_y = _draw_row(current_y, table.headers, is_header=True)
            # Redraw unit row on new page if present
            if has_unit_row:
                unit_cells = [f"({u})" if u else "" for u in table.unit_row]
                current_y = _draw_row(current_y, unit_cells, is_unit=True)

        current_y = _draw_row(current_y, cells)

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
            # Start each section on a new page
            ctx.new_page()
            self._draw_section(ctx, section)

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
            _draw_draft_watermark(page, text=draft_wm_text, fontsize=draft_wm_size)

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
    def _draw_section(
        self,
        ctx: PdfRenderContext,
        section: RenderSection,
    ) -> None:
        """Draw a section on the current page."""
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
            reason_text = {
                "not_provided": "该部分数据未提供",
                "not_calculated": "该部分尚未计算",
            }.get(
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
            ctx.y = _insert_text(
                ctx.current_page,
                content_left,
                ctx.y,
                section.text,
                fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                font_path=ctx.font_path,
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
                ctx.y = _insert_text(
                    ctx.current_page,
                    content_left,
                    ctx.y,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    font_path=ctx.font_path,
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
                ctx.y = _insert_text(
                    ctx.current_page,
                    content_left,
                    ctx.y,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    font_path=ctx.font_path,
                    max_width=content_width,
                )

        elif section.content_type == "table" and section.table:
            if section.text:
                ctx.ensure_space(_LINE_HEIGHT + 4)
                ctx.y = _insert_text(
                    ctx.current_page,
                    content_left,
                    ctx.y,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    font_path=ctx.font_path,
                    max_width=content_width,
                )
                ctx.y += 4
            ctx.y = _draw_table(
                ctx,
                content_left,
                ctx.y,
                section.table,
                max_width=content_width,
                font_path=ctx.font_path,
            )

        elif section.content_type == "finding":
            if section.text:
                ctx.ensure_space(_LINE_HEIGHT + 4)
                ctx.y = _insert_text(
                    ctx.current_page,
                    content_left,
                    ctx.y,
                    section.text,
                    fontsize=settings.get("body_font_size", _BODY_FONT_SIZE),
                    font_path=ctx.font_path,
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
                    font_path=ctx.font_path,
                )
