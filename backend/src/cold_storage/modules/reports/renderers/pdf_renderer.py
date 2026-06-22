"""PDF renderer — produces a .pdf file from a ReportRenderModel.

Uses PyMuPDF (fitz).  Text is selectable (no rasterization).  A4 layout
with headers, footers, and optional DRAFT watermark.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import fitz  # PyMuPDF

if TYPE_CHECKING:
    from cold_storage.modules.reports.domain.render_model import (
        RenderSection,
        RenderTable,
        ReportRenderModel,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_PT_PER_CM = 28.3465  # 1 cm = 28.3465 pt
_A4_WIDTH_PT = 21.0 * _PT_PER_CM
_A4_HEIGHT_PT = 29.7 * _PT_PER_CM
_MARGIN_PT = 2.0 * _PT_PER_CM  # 2 cm margins

_CONTENT_LEFT = _MARGIN_PT
_CONTENT_RIGHT = _A4_WIDTH_PT - _MARGIN_PT
_CONTENT_WIDTH = _CONTENT_RIGHT - _CONTENT_LEFT
_CONTENT_TOP = _MARGIN_PT + 1.5 * _PT_PER_CM  # extra space for header
_CONTENT_BOTTOM = _A4_HEIGHT_PT - _MARGIN_PT - 1.0 * _PT_PER_CM  # footer space

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
    fontname: str = "tiro",
) -> float:
    """Insert text on page and return the new y position.

    Handles line wrapping within _CONTENT_WIDTH.
    """
    lines = text.split("\n")
    current_y = y

    for line in lines:
        if not line:
            current_y += _LINE_HEIGHT
            continue

        # Simple word wrapping
        words = line.split(" ")
        current_line = ""
        font = fitz.Font(fontname)
        for word in words:
            test = f"{current_line} {word}".strip() if current_line else word
            text_rect = font.text_length(test, fontsize=fontsize)
            if text_rect > _CONTENT_WIDTH and current_line:
                # Write current line
                page.insert_text(
                    fitz.Point(x, current_y),
                    current_line,
                    fontname=fontname,
                    fontsize=fontsize,
                    color=color,
                )
                current_y += _LINE_HEIGHT
                current_line = word
            else:
                current_line = test

        if current_line:
            page.insert_text(
                fitz.Point(x, current_y),
                current_line,
                fontname=fontname,
                fontsize=fontsize,
                color=color,
            )
            current_y += _LINE_HEIGHT

    return current_y


def _insert_number(
    page: fitz.Page,
    x: float,
    y: float,
    display: str,
    unit: str,
) -> float:
    """Insert a bold number with unit."""
    fontsize = _BODY_FONT_SIZE + 0.5
    full_text = f"{display} {unit}"
    page.insert_text(
        fitz.Point(x, y),
        full_text,
        fontname="tiro",
        fontsize=fontsize,
        color=_TEXT_COLOR,
    )
    return y + _LINE_HEIGHT + 2


def _draw_table(
    page: fitz.Page,
    x: float,
    y: float,
    table: RenderTable,
    max_width: float | None = None,
) -> float:
    """Draw a table on the page and return the new y position."""
    if max_width is None:
        max_width = _CONTENT_WIDTH

    num_cols = len(table.headers)
    if num_cols == 0:
        return y

    col_width = max_width / num_cols
    row_height = _LINE_HEIGHT + 4

    # Check if we need a unit row
    has_unit_row = bool(table.unit_row and any(u for u in table.unit_row))

    def _draw_row(
        row_y: float,
        cells: list[str],
        is_header: bool = False,
        is_unit: bool = False,
    ) -> float:
        """Draw a single row of cells."""
        # Background
        bg_color = _LIGHT_BLUE if is_header else _LIGHT_GRAY if is_unit else None
        if bg_color:
            rect = fitz.Rect(x, row_y, x + max_width, row_y + row_height)
            page.draw_rect(rect, color=None, fill=bg_color)

        # Grid lines (horizontal)
        page.draw_line(
            fitz.Point(x, row_y),
            fitz.Point(x + max_width, row_y),
            color=(0.7, 0.7, 0.7),
            width=0.5,
        )

        # Grid lines (vertical) and text
        for col_idx, cell_text in enumerate(cells):
            col_x = x + col_idx * col_width
            # Vertical line
            page.draw_line(
                fitz.Point(col_x, row_y),
                fitz.Point(col_x, row_y + row_height),
                color=(0.7, 0.7, 0.7),
                width=0.5,
            )
            # Cell text
            fontsize = _TABLE_HEADER_SIZE if is_header else _TABLE_BODY_SIZE
            text_x = col_x + 3
            text_y = row_y + row_height - 4
            page.insert_text(
                fitz.Point(text_x, text_y),
                cell_text,
                fontname="tiro",
                fontsize=fontsize,
                color=_TEXT_COLOR,
            )

        # Right border
        page.draw_line(
            fitz.Point(x + max_width, row_y),
            fitz.Point(x + max_width, row_y + row_height),
            color=(0.7, 0.7, 0.7),
            width=0.5,
        )

        # Bottom border
        page.draw_line(
            fitz.Point(x, row_y + row_height),
            fitz.Point(x + max_width, row_y + row_height),
            color=(0.7, 0.7, 0.7),
            width=0.5,
        )

        return row_y + row_height

    current_y = y

    # Header row
    current_y = _draw_row(current_y, table.headers, is_header=True)

    # Unit row
    if has_unit_row:
        unit_cells = [f"({u})" if u else "" for u in table.unit_row]
        current_y = _draw_row(current_y, unit_cells, is_unit=True)

    # Data rows
    for row_data in table.rows:
        cells = [cell.value for cell in row_data]
        current_y = _draw_row(current_y, cells)

    return current_y + 4  # small gap after table


def _draw_header(page: fitz.Page, project_name: str, report_type: str) -> None:
    """Draw header on page."""
    header_text = f"{project_name} — {report_type}"
    font = fitz.Font("tiro")
    text_width = font.text_length(header_text, fontsize=_HEADER_SIZE)
    page.insert_text(
        fitz.Point(_CONTENT_RIGHT - text_width, _MARGIN_PT + 0.5 * _PT_PER_CM),
        header_text,
        fontname="tiro",
        fontsize=_HEADER_SIZE,
        color=_GRAY_COLOR,
    )
    # Line under header
    page.draw_line(
        fitz.Point(_CONTENT_LEFT, _MARGIN_PT + 1.0 * _PT_PER_CM),
        fitz.Point(_CONTENT_RIGHT, _MARGIN_PT + 1.0 * _PT_PER_CM),
        color=(0.8, 0.8, 0.8),
        width=0.5,
    )


def _draw_footer(page: fitz.Page, page_num: int) -> None:
    """Draw page number in footer."""
    page_text = f"— {page_num} —"
    font = fitz.Font("tiro")
    text_width = font.text_length(page_text, fontsize=_FOOTER_SIZE)
    page.insert_text(
        fitz.Point((_A4_WIDTH_PT - text_width) / 2, _A4_HEIGHT_PT - _MARGIN_PT + 0.3 * _PT_PER_CM),
        page_text,
        fontname="tiro",
        fontsize=_FOOTER_SIZE,
        color=_GRAY_COLOR,
    )


def _draw_draft_watermark(page: fitz.Page) -> None:
    """Draw DRAFT watermark centered on the page."""
    text = "DRAFT"
    fontsize = 60
    font = fitz.Font("tiro")
    cx = _A4_WIDTH_PT / 2
    cy = _A4_HEIGHT_PT / 2
    text_width = font.text_length(text, fontsize=fontsize)
    page.insert_text(
        fitz.Point(cx - text_width / 2, cy),
        text,
        fontname="tiro",
        fontsize=fontsize,
        color=(0.8, 0.8, 0.8),
    )


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

        # ---- Cover page ----
        cover_page = doc.new_page(width=_A4_WIDTH_PT, height=_A4_HEIGHT_PT)
        self._draw_cover(cover_page, meta, is_draft=is_draft)

        # ---- Content sections ----
        for section in model.sections:
            page = doc.new_page(width=_A4_WIDTH_PT, height=_A4_HEIGHT_PT)
            self._draw_section(page, section, meta, is_draft=is_draft)

        # ---- Finalize ----
        pdf_bytes: bytes = doc.tobytes()
        doc.close()
        return bytes(pdf_bytes)

    # ------------------------------------------------------------------
    # Cover page
    # ------------------------------------------------------------------

    def _draw_cover(self, page: fitz.Page, meta: Any, *, is_draft: bool = False) -> None:
        """Draw the cover page."""
        if is_draft:
            _draw_draft_watermark(page)

        cx = _A4_WIDTH_PT / 2
        font = fitz.Font("tiro")
        y = _A4_HEIGHT_PT * 0.35

        # Project name
        name_text = meta.project_name or "项目报告"
        name_size = 26
        name_width = font.text_length(name_text, fontsize=name_size)
        page.insert_text(
            fitz.Point(cx - name_width / 2, y),
            name_text,
            fontname="tiro",
            fontsize=name_size,
            color=_HEADING_COLOR,
        )

        # Report type
        y += 40
        type_text = meta.report_type
        type_size = 18
        type_width = font.text_length(type_text, fontsize=type_size)
        page.insert_text(
            fitz.Point(cx - type_width / 2, y),
            type_text,
            fontname="tiro",
            fontsize=type_size,
            color=_GRAY_COLOR,
        )

        # Version and date
        y += 30
        ver_text = (
            f"版本 {meta.revision_number}  |  {meta.generated_at[:10] if meta.generated_at else ''}"
        )
        ver_size = 12
        ver_width = font.text_length(ver_text, fontsize=ver_size)
        page.insert_text(
            fitz.Point(cx - ver_width / 2, y),
            ver_text,
            fontname="tiro",
            fontsize=ver_size,
            color=_GRAY_COLOR,
        )

    # ------------------------------------------------------------------
    # Section rendering
    # ------------------------------------------------------------------

    def _draw_section(
        self,
        page: fitz.Page,
        section: RenderSection,
        meta: Any,
        *,
        is_draft: bool = False,
    ) -> None:
        """Draw a section on a page."""
        _draw_header(page, meta.project_name, meta.report_type)

        current_y = _CONTENT_TOP

        if is_draft:
            _draw_draft_watermark(page)

        if section.is_empty:
            heading_size = (
                _HEADING1_SIZE
                if section.level == 1
                else _HEADING2_SIZE
                if section.level == 2
                else _HEADING3_SIZE
            )
            current_y = _insert_text(
                page,
                _CONTENT_LEFT,
                current_y,
                section.title,
                fontsize=heading_size,
                color=_HEADING_COLOR,
            )
            current_y += 4
            reason_text = {
                "not_provided": "该部分数据未提供",
                "not_calculated": "该部分尚未计算",
            }.get(section.empty_reason, "该部分内容不可用")
            current_y = _insert_text(
                page,
                _CONTENT_LEFT + 10,
                current_y,
                f"（{reason_text}）",
                fontsize=_BODY_FONT_SIZE,
                color=_GRAY_COLOR,
            )
            _draw_footer(page, 1)
            return

        # Heading
        heading_size = (
            _HEADING1_SIZE
            if section.level == 1
            else _HEADING2_SIZE
            if section.level == 2
            else _HEADING3_SIZE
        )
        current_y = _insert_text(
            page,
            _CONTENT_LEFT,
            current_y,
            section.title,
            fontsize=heading_size,
            color=_HEADING_COLOR,
        )
        current_y += 6

        if section.content_type == "text" and section.text:
            current_y = _insert_text(
                page,
                _CONTENT_LEFT,
                current_y,
                section.text,
                fontsize=_BODY_FONT_SIZE,
            )
        elif section.content_type == "number" and section.number:
            num = section.number
            current_y = _insert_number(page, _CONTENT_LEFT, current_y, num.display, num.unit)
            if section.text:
                current_y = _insert_text(
                    page,
                    _CONTENT_LEFT,
                    current_y,
                    section.text,
                    fontsize=_BODY_FONT_SIZE,
                )
        elif section.content_type == "table" and section.table:
            if section.text:
                current_y = _insert_text(
                    page,
                    _CONTENT_LEFT,
                    current_y,
                    section.text,
                    fontsize=_BODY_FONT_SIZE,
                )
                current_y += 4
            current_y = _draw_table(page, _CONTENT_LEFT, current_y, section.table)
        elif section.content_type == "finding":
            if section.text:
                current_y = _insert_text(
                    page,
                    _CONTENT_LEFT,
                    current_y,
                    section.text,
                    fontsize=_BODY_FONT_SIZE,
                )
                current_y += 4
            if section.table:
                current_y = _draw_table(page, _CONTENT_LEFT, current_y, section.table)

        _draw_footer(page, 1)
