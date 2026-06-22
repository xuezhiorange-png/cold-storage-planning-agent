"""DOCX renderer — produces a .docx file from a ReportRenderModel.

Uses python-docx.  No macros, no external resource loading, no template
expressions.  Font fallback: SimSun → Times New Roman.  A4 page size.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

if TYPE_CHECKING:
    from cold_storage.modules.reports.domain.render_model import (
        RenderSection,
        RenderTable,
        ReportRenderModel,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_BODY_FONT = "SimSun"
_BODY_FONT_FALLBACK = "Times New Roman"
_HEADING_FONT = "Times New Roman"
_A4_WIDTH_PT = 21.0 * 28.3465  # A4 width in points
_A4_HEIGHT_PT = 29.7 * 28.3465  # A4 height in points
_PT_TO_CM = 0.0352778


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_cell_border(cell: Any, **kwargs: Any) -> None:
    """Set cell border on a table cell.

    Usage: ``_set_cell_border(cell, top={"sz": 6, "val": "single", "color": "000000"})``
    """
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("start", "top", "end", "bottom", "insideH", "insideV"):
        if edge in kwargs:
            attrs = kwargs[edge]
            el = OxmlElement(f"w:{edge}")
            for k, v in attrs.items():
                el.set(qn(f"w:{k}"), str(v))
            tcBorders.append(el)
    tcPr.append(tcBorders)


def _set_run_font(
    run: Any,
    *,
    font_name: str = _BODY_FONT,
    size: Pt | None = None,
    bold: bool = False,
    color: RGBColor | None = None,
) -> None:
    """Configure font on a run with CJK fallback."""
    run.font.name = font_name
    # Set East Asian font
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), _BODY_FONT)
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)

    if size is not None:
        run.font.size = size
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _add_page_number_footer(section: Any) -> None:
    """Add page number to footer."""
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Add "第 X 页" via field codes
    run1 = p.add_run("— ")
    _set_run_font(run1, size=Pt(9))

    # PAGE field
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    run_field = p.add_run()
    run_field._r.append(fldChar1)

    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = " PAGE "
    run_instr = p.add_run()
    run_instr._r.append(instrText)

    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run_end = p.add_run()
    run_end._r.append(fldChar2)

    run2 = p.add_run(" —")
    _set_run_font(run2, size=Pt(9))


def _add_header(section: Any, project_name: str, report_type: str) -> None:
    """Add project name and report type to header."""
    header = section.header
    header.is_linked_to_previous = False
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(f"{project_name} — {report_type}")
    _set_run_font(run, size=Pt(8), color=RGBColor(0x80, 0x80, 0x80))


def _add_draft_watermark(doc: Any) -> None:
    """Add DRAFT watermark to the document."""
    for section in doc.sections:
        header = section.header
        p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        run = p.add_run("DRAFT")
        _set_run_font(run, size=Pt(60), bold=True, color=RGBColor(0xC0, 0xC0, 0xC0))


# ---------------------------------------------------------------------------
# DOCX Renderer
# ---------------------------------------------------------------------------


class DocxRenderer:
    """Render a ReportRenderModel to DOCX bytes."""

    def render(self, model: ReportRenderModel, *, is_draft: bool = False) -> bytes:
        """Render the model to DOCX bytes.

        Parameters
        ----------
        model:
            The complete render model.
        is_draft:
            If True, add a DRAFT watermark.

        Returns
        -------
        bytes
            The raw .docx file content.
        """
        # P0-10: Load template manifest settings (canonical structure)
        render_settings = model.manifest.render_settings
        page_settings = render_settings.get("page", {})
        font_settings = render_settings.get("fonts", {})

        # Page size from manifest (canonical: page.width_pt/height_pt in pt)
        # Convert pt to cm for python-docx: 1 pt = 0.0353 cm
        _PT_TO_CM = 0.0352778
        page_width_cm = page_settings.get("width_pt", _A4_WIDTH_PT) * _PT_TO_CM
        page_height_cm = page_settings.get("height_pt", _A4_HEIGHT_PT) * _PT_TO_CM
        # Per-side margins (canonical: page.margin_top_pt etc.)
        margin_top_cm = (
            page_settings.get("margin_top_pt", page_settings.get("margin_pt", 56.69)) * _PT_TO_CM
        )
        margin_bottom_cm = (
            page_settings.get("margin_bottom_pt", page_settings.get("margin_pt", 56.69)) * _PT_TO_CM
        )
        margin_left_cm = (
            page_settings.get("margin_left_pt", page_settings.get("margin_pt", 56.69)) * _PT_TO_CM
        )
        margin_right_cm = (
            page_settings.get("margin_right_pt", page_settings.get("margin_pt", 56.69)) * _PT_TO_CM
        )

        doc: Any = Document()

        # ---- Page setup (from manifest or A4 defaults) ----
        for section in doc.sections:
            section.page_width = Cm(page_width_cm)
            section.page_height = Cm(page_height_cm)
            section.top_margin = Cm(margin_top_cm)
            section.bottom_margin = Cm(margin_bottom_cm)
            section.left_margin = Cm(margin_left_cm)
            section.right_margin = Cm(margin_right_cm)
            section.orientation = WD_ORIENT.PORTRAIT

        # ---- Default style ----
        style = doc.styles["Normal"]
        style.font.name = font_settings.get("body_name", _BODY_FONT)
        style.font.size = Pt(font_settings.get("body_size_pt", 10.5))
        rPr = style.element.find(qn("w:rPr"))
        if rPr is None:
            rPr = OxmlElement("w:rPr")
            style.element.append(rPr)
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.insert(0, rFonts)
        rFonts.set(qn("w:eastAsia"), _BODY_FONT)

        # ---- Heading styles (P0-10: use manifest settings) ----
        heading_sizes = {
            1: font_settings.get("heading1_size_pt", 16),
            2: font_settings.get("heading2_size_pt", 14),
            3: font_settings.get("heading3_size_pt", 12),
        }
        for level in range(1, 4):
            style_name = f"Heading {level}"
            if style_name in doc.styles:
                hs = doc.styles[style_name]
                hs.font.name = _HEADING_FONT
                hs.font.size = Pt(heading_sizes.get(level, [16, 14, 12][level - 1]))
                hs.font.bold = True
                hs.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)

        # ---- Document properties (metadata) ----
        cp = doc.core_properties
        cp.title = model.metadata.project_name or "Report"
        cp.subject = model.metadata.report_type
        cp.comments = f"Revision {model.metadata.revision_number}"
        cp.author = model.metadata.generated_by
        # Custom properties via XML
        docProps = doc.element.find(qn("w:docProps"))
        if docProps is None:
            docProps = OxmlElement("w:docProps")
            doc.element.append(docProps)

        def _add_custom_prop(name: str, value: str) -> None:
            prop = OxmlElement("w:customProp")
            prop.set(qn("w:name"), name)
            val_el = OxmlElement("w:str")
            val_el.set(qn("w:val"), value)
            prop.append(val_el)
            docProps.append(prop)

        _add_custom_prop("SourceContentHash", model.metadata.content_hash)
        _add_custom_prop("TemplateVersion", model.metadata.template_version)

        # ---- Cover page ----
        meta = model.metadata

        # Blank lines for centering
        for _ in range(6):
            doc.add_paragraph("")

        # Project name
        p_name = doc.add_paragraph()
        p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_name.add_run(meta.project_name or "项目报告")
        _set_run_font(
            run,
            font_name=_HEADING_FONT,
            size=Pt(26),
            bold=True,
            color=RGBColor(0x1F, 0x38, 0x64),
        )

        # Report type
        p_type = doc.add_paragraph()
        p_type.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_type.add_run(meta.report_type)
        _set_run_font(run, font_name=_HEADING_FONT, size=Pt(18), color=RGBColor(0x40, 0x40, 0x40))

        # Version line — P0-4: use clean ISO string, no slicing
        p_ver = doc.add_paragraph()
        p_ver.alignment = WD_ALIGN_PARAGRAPH.CENTER
        generated_at = meta.generated_at if meta.generated_at else ""
        # Extract just the date portion (first 10 chars of ISO string)
        date_display = generated_at[:10] if len(generated_at) >= 10 else generated_at
        ver_str = f"版本 {meta.revision_number}  |  {date_display}"
        run = p_ver.add_run(ver_str)
        _set_run_font(run, size=Pt(12), color=RGBColor(0x60, 0x60, 0x60))

        # ---- Document control info ----
        doc.add_page_break()

        p_title = doc.add_paragraph()
        run = p_title.add_run("文件控制信息")
        _set_run_font(run, font_name=_HEADING_FONT, size=Pt(14), bold=True)

        hash_val = meta.content_hash
        hash_display = hash_val[:16] + "…" if len(hash_val) > 16 else hash_val
        control_items = [
            ("内容哈希", hash_display),
            ("模板版本", meta.template_version),
            ("生成者", meta.generated_by),
            ("生成时间", meta.generated_at),
            ("修订号", str(meta.revision_number)),
        ]
        for label, value in control_items:
            p = doc.add_paragraph()
            run_label = p.add_run(f"{label}：")
            _set_run_font(run_label, bold=True, size=Pt(10))
            run_val = p.add_run(value)
            _set_run_font(run_val, size=Pt(10))

        doc.add_page_break()

        # ---- Sections ----
        for render_section in model.sections:
            self._render_section(doc, render_section)

        # ---- Footer with page numbers ----
        for doc_section in doc.sections:
            _add_page_number_footer(doc_section)

        # ---- Header ----
        for doc_section in doc.sections:
            _add_header(doc_section, meta.project_name, meta.report_type)

        # ---- Watermark ----
        if is_draft:
            _add_draft_watermark(doc)

        # ---- Serialize ----
        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Section rendering
    # ------------------------------------------------------------------

    def _render_section(self, doc: Any, section: RenderSection) -> None:
        """Render a single section into the document."""
        if section.is_empty:
            doc.add_heading(section.title, level=section.level)
            p = doc.add_paragraph(f"（{self._empty_reason_text(section.empty_reason)}）")
            target_run = p.runs[0] if p.runs else p.add_run("")
            _set_run_font(
                target_run,
                size=Pt(10),
                color=RGBColor(0x99, 0x99, 0x99),
            )
            return

        # Section heading
        doc.add_heading(section.title, level=section.level)

        if section.content_type == "text" and section.text:
            self._render_text_block(doc, section.text)
        elif section.content_type == "metrics" and section.metrics:
            # Render each metric as: label: display_value unit
            for metric in section.metrics:
                p = doc.add_paragraph()
                run = p.add_run(f"{metric.label}: {metric.display_value} {metric.unit}".strip())
                _set_run_font(run, size=Pt(10.5))
            # Also render primary number for backward compat
            if section.number:
                self._render_number(doc, section)
        elif section.content_type == "number" and section.number:
            self._render_number(doc, section)
        elif section.content_type == "table" and section.table:
            if section.text:
                self._render_text_block(doc, section.text)
            self._render_table(doc, section.table)
        elif section.content_type == "finding":
            if section.text:
                self._render_text_block(doc, section.text)
            if section.table:
                self._render_table(doc, section.table)

        # Render paragraphs
        if section.paragraphs:
            for para in section.paragraphs:
                p = doc.add_paragraph()
                run = p.add_run(para)
                _set_run_font(run, size=Pt(10.5))

        # Render citations as numbered footnotes
        if section.citations:
            for idx, cite in enumerate(section.citations, 1):
                cite_text = f"[{idx}] {cite.get('tool_name', '')} — {cite.get('source_id', '')}"
                p = doc.add_paragraph()
                run = p.add_run(cite_text)
                _set_run_font(run, size=Pt(9), color=RGBColor(0x60, 0x60, 0x60))

    def _render_text_block(self, doc: Any, text: str) -> None:
        """Render a text block, preserving line breaks as paragraphs."""
        for line in text.split("\n"):
            p = doc.add_paragraph()
            run = p.add_run(line)
            _set_run_font(run, size=Pt(10.5))

    def _render_number(self, doc: Any, section: RenderSection) -> None:
        """Render a number field with its value and unit."""
        num = section.number
        if num is not None:
            p = doc.add_paragraph()
            run = p.add_run(f"{num.display} {num.unit}")
            _set_run_font(run, size=Pt(11), bold=True)
        if section.text:
            self._render_text_block(doc, section.text)

    def _render_table(self, doc: Any, table: RenderTable) -> None:
        """Render a RenderTable as a Word table.

        P0-6: Adds ``<w:tblHeader>`` to header rows so they repeat on page
        breaks, and ``<w:cantSplit>`` to data rows to prevent mid-row breaks.
        """
        num_cols = len(table.headers)
        num_rows = len(table.rows) + 1  # +1 for header
        has_unit_row = table.unit_row and any(u for u in table.unit_row)
        if has_unit_row:
            num_rows += 1  # +1 for unit row

        word_table = doc.add_table(rows=num_rows, cols=num_cols)
        word_table.style = "Table Grid"

        # Header row
        for col_idx, header in enumerate(table.headers):
            cell = word_table.rows[0].cells[col_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(header)
            _set_run_font(run, size=Pt(10), bold=True)
            # Gray background for header
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            shading = OxmlElement("w:shd")
            shading.set(qn("w:val"), "clear")
            shading.set(qn("w:color"), "auto")
            shading.set(qn("w:fill"), "D9E2F3")
            tcPr.append(shading)

        # P0-6: Mark header row with <w:tblHeader> for repeating on page breaks
        header_tr = word_table.rows[0]._tr
        header_trPr = header_tr.get_or_add_trPr()
        tblHeader = OxmlElement("w:tblHeader")
        tblHeader.set(qn("w:val"), "true")
        header_trPr.append(tblHeader)

        # Unit row (if present)
        row_offset = 1
        if has_unit_row:
            for col_idx, unit in enumerate(table.unit_row):
                cell = word_table.rows[1].cells[col_idx]
                cell.text = ""
                p = cell.paragraphs[0]
                run = p.add_run(f"({unit})" if unit else "")
                _set_run_font(run, size=Pt(9), color=RGBColor(0x60, 0x60, 0x60))
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            row_offset = 2

        # Data rows
        for row_idx, row_data in enumerate(table.rows):
            # P0-6: Mark data row with <w:cantSplit> to prevent mid-row breaks
            tr = word_table.rows[row_idx + row_offset]._tr
            trPr = tr.get_or_add_trPr()
            cantSplit = OxmlElement("w:cantSplit")
            trPr.append(cantSplit)

            for col_idx, cell_data in enumerate(row_data):
                word_cell = word_table.rows[row_idx + row_offset].cells[col_idx]
                word_cell.text = ""
                p = word_cell.paragraphs[0]
                run = p.add_run(cell_data.value)
                _set_run_font(run, size=Pt(10))
                if cell_data.align == "right":
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                elif cell_data.align == "center":
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    @staticmethod
    def _empty_reason_text(reason: str) -> str:
        """Human-readable empty reason."""
        reasons = {
            "not_provided": "该部分数据未提供",
            "not_calculated": "该部分尚未计算",
        }
        return reasons.get(reason, "该部分内容不可用")
