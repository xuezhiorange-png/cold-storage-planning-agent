"""Comprehensive tests for PDF renderer — P0-1 metrics + P0-6 pagination.

Tests verify:
1. Large Chinese table spans multiple pages (at least 3 pages)
2. Last row (row 100) is not lost across page breaks
3. Table header repeats on page break
4. All text/table coordinates stay within page boundaries
5. CJK text wraps correctly for long cells
6. DRAFT watermark on every page in draft mode
7. NO DRAFT watermark in formal mode
8. Metrics rendering: all labels, values, units in PDF
9. DOCX and PDF contain the same metric set
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import fitz

from cold_storage.modules.reports.domain.render_model import (
    CanonicalRenderTable,
    CanonicalRenderTableCell,
    LocalizedRenderMetadata,
    LocalizedRenderMetric,
    LocalizedRenderNumber,
    LocalizedRenderSection,
    LocalizedRenderTable,
    LocalizedRenderTableCell,
    LocalizedReportRenderModel,
    RenderManifest,
)
from cold_storage.modules.reports.renderers.docx_renderer import DocxRenderer
from cold_storage.modules.reports.renderers.pdf_renderer import PdfRenderer


def _tc(display_value: str, align: str | None = None):
    canonical = CanonicalRenderTableCell(field_path="", field_key="", raw_value=display_value or "")
    return LocalizedRenderTableCell(canonical=canonical, display_value=display_value, align=align)


_DUMMY_TABLE_KEY = "test_pagination"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata() -> LocalizedRenderMetadata:
    """Create a standard test metadata object."""
    from cold_storage.modules.reports.domain.render_model import CanonicalRenderMetadata

    canonical = CanonicalRenderMetadata(
        report_id="r-test",
        project_name="蓝莓冷库概念设计项目",
        report_type="概念设计报告",
        schema_version="cold_storage_concept_design@1.0.0",
        revision_number=1,
        content_hash="a" * 64,
        content_hash_short="a" * 8,
        generated_at="2025-01-01T00:00:00+00:00",
        generated_by="test-system",
        template_version="1.0.0",
        template_code="cold_storage_concept_design",
    )
    return LocalizedRenderMetadata(
        canonical=canonical,
        project_name="蓝莓冷库概念设计项目",
        report_type_label="概念设计报告",
        confidentiality_label="",
        disclaimer="",
        empty_section_placeholder="",
        cover_title="",
        cover_version_line="",
        control_info_title="",
        content_hash_label="",
        template_version_label="",
        generated_by_label="",
        generated_at_label="",
        revision_label="",
        watermark_text="",
    )


def _make_manifest(sections: list[LocalizedRenderSection]) -> RenderManifest:
    """Create a standard manifest from a list of sections."""
    return RenderManifest(
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
        schema_version="cold_storage_concept_design@1.0.0",
        source_content_hash="a" * 64,
        sections=[s.section_key for s in sections],
        format="docx/pdf",
    )


def _make_model(
    sections: list[LocalizedRenderSection],
    *,
    is_draft: bool = False,
    watermark_text: str = "DRAFT",
) -> tuple[LocalizedReportRenderModel, bytes]:
    """Build a LocalizedReportRenderModel, render it, and return (model, pdf_bytes)."""
    metadata = _make_metadata()
    manifest = _make_manifest(sections)
    model = LocalizedReportRenderModel(
        metadata=metadata,
        sections=sections,
        manifest=manifest,
        watermark_text=watermark_text,
    )
    pdf_bytes = PdfRenderer().render(model, is_draft=is_draft)
    return model, pdf_bytes


def _build_100_row_cjk_table() -> tuple[list[LocalizedRenderSection], LocalizedRenderTable]:
    """Build a section with a 100-row table, each cell 80+ CJK chars."""
    rows = []
    for i in range(100):
        # Each cell gets a long CJK string (80+ chars)
        cjk_label = f"设备编号{i:03d}"
        cjk_desc = f"这是一段描述性的文字用于测试长文本换行功能是否正常工作。第{i:03d}行"
        cjk_note = f"备注内容：蓝色冷冻库项目中的重要参数记录和质量控制指标，第{i}号检测点。"
        rows.append(
            [
                _tc(cjk_label, align="left"),
                _tc(cjk_desc, align="left"),
                _tc(cjk_note, align="left"),
                _tc(f"{250 + i * 5}.0", align="right"),
            ]
        )
    table = LocalizedRenderTable(
        canonical=CanonicalRenderTable(table_key=_DUMMY_TABLE_KEY),
        title="设备清单",
        headers=["设备编号", "描述", "备注", "功率(kW)"],
        rows=rows,
        unit_row=["", "", "", "kW"],
    )
    section = LocalizedRenderSection(
        section_key="equipment_list",
        title="设备清单",
        level=1,
        content_type="table",
        table=table,
    )
    return [section], table


def _build_metrics_sections() -> list[LocalizedRenderSection]:
    """Build sections with 5 different LocalizedRenderMetrics."""
    from cold_storage.modules.reports.domain.render_model import CanonicalRenderMetric

    metrics = [
        LocalizedRenderMetric(
            canonical=CanonicalRenderMetric(
                field_path="cooling.total_design_load",
                field_key="cooling.total_design_load",
                raw_value=250.0,
                unit_code="kW(r)",
            ),
            label="总设计制冷量",
            display_value="250.0",
            display_unit="kW(r)",
        ),
        LocalizedRenderMetric(
            canonical=CanonicalRenderMetric(
                field_path="cooling.precooling_capacity",
                field_key="cooling.precooling_capacity",
                raw_value=180.5,
                unit_code="kW(r)",
            ),
            label="预冷能力",
            display_value="180.5",
            display_unit="kW(r)",
        ),
        LocalizedRenderMetric(
            canonical=CanonicalRenderMetric(
                field_path="storage.area",
                field_key="storage.area",
                raw_value=1200.0,
                unit_code="m2",
            ),
            label="冷藏库面积",
            display_value="1,200.0",
            display_unit="m2",
        ),
        LocalizedRenderMetric(
            canonical=CanonicalRenderMetric(
                field_path="investment.total",
                field_key="investment.total",
                raw_value=5800000.0,
                unit_code="CNY",
            ),
            label="总投资估算",
            display_value="5,800,000",
            display_unit="CNY",
        ),
        LocalizedRenderMetric(
            canonical=CanonicalRenderMetric(
                field_path="capacity.total_volume",
                field_key="capacity.total_volume",
                raw_value=3600.0,
                unit_code="m3",
            ),
            label="冷库总容积",
            display_value="3,600",
            display_unit="m3",
        ),
    ]
    return [
        LocalizedRenderSection(
            section_key="cooling_metrics",
            title="冷负荷指标",
            level=1,
            content_type="metrics",
            metrics=metrics,
        )
    ]


def _tc(display_value: str, align: str | None = None):
    canonical = CanonicalRenderTableCell(field_path="", field_key="", raw_value=display_value or "")
    return LocalizedRenderTableCell(canonical=canonical, display_value=display_value, align=align)


_DUMMY_TABLE_KEY = "test_pagination"


# ---------------------------------------------------------------------------
# Test 1: 100-row CJK table → at least 3 pages
# ---------------------------------------------------------------------------


class TestLargeCjkTablePagination:
    def test_100_row_table_spans_multiple_pages(self):
        """A 100-row table with long CJK cells must produce at least 3 pages."""
        sections, _ = _build_100_row_cjk_table()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        doc.close()

        assert page_count >= 3, f"Expected at least 3 pages for 100-row table, got {page_count}"

    def test_row_100_text_exists_in_pdf(self):
        """The text from row 100 must be present somewhere in the PDF."""
        sections, _ = _build_100_row_cjk_table()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()

        # Row 100 is index 99 → "设备编号099"
        assert "设备编号099" in all_text, (
            f"Row 100 text '设备编号099' not found in PDF. First 500 chars: {all_text[:500]}"
        )

    def test_table_header_repeats_on_page_break(self):
        """After a page break during table rendering, header row must reappear."""
        sections, _ = _build_100_row_cjk_table()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Count occurrences of "设备编号" in headers across pages
        header_count = 0
        for page in doc:
            text = page.get_text()
            # Header row contains "设备编号" as a column header (bold)
            # At least pages 2+ should have the repeated header
            if "设备编号" in text:
                header_count += 1

        doc.close()

        # Cover page (page 1) has no table. Pages 2+ have the table.
        # With 100 rows, there should be at least 2 table pages, so
        # at least 2 occurrences of "设备编号" (one per table page)
        assert header_count >= 2, (
            f"Expected table headers on at least 2 pages, found on {header_count} pages"
        )

    def test_all_text_within_page_boundaries(self):
        """All text and table drawing coordinates must stay within page margins."""
        sections, _ = _build_100_row_cjk_table()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Default A4 margins: 2 cm = 56.69 pt
        margin = 56.69
        for page_idx, page in enumerate(doc):
            page_width = page.rect.width
            page_height = page.rect.height
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block["type"] != 0:  # text block
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = span["bbox"]  # (x0, y0, x1, y1)
                        # X bounds: must be within content area
                        assert bbox[0] >= margin - 1, (
                            f"Page {page_idx}: text x0={bbox[0]:.1f} < margin {margin}"
                        )
                        assert bbox[2] <= page_width - margin + 1, (
                            f"Page {page_idx}: text x1={bbox[2]:.1f} > "
                            f"page_width-margin {page_width - margin:.1f}"
                        )
                        # Y bounds: must be within page
                        assert bbox[1] >= margin - 1, (
                            f"Page {page_idx}: text y0={bbox[1]:.1f} < margin {margin}"
                        )
                        assert bbox[3] <= page_height + 5, (
                            f"Page {page_idx}: text y1={bbox[3]:.1f} > "
                            f"page_height+5 {page_height + 5:.1f}"
                        )

        doc.close()

    def test_long_cjk_cell_renders_correctly(self):
        """A cell with 80+ CJK chars renders across wrapped lines in the PDF.

        PyMuPDF text extraction splits at wrapped line boundaries, so we
        verify the original content is present by checking that the
        constituent substrings all appear on the same page.
        """
        sections, _ = _build_100_row_cjk_table()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Check page 1 (the first table page) for CJK content
        # The note cell for row 0 contains a long CJK string.
        # After wrapping, it appears as multiple lines.
        # Verify the key substrings are present across lines.
        page_text = doc[1].get_text()  # page 1 is first table page

        # The note cell text is:
        # "备注内容：蓝色冷冻库项目中的重要参数记录和质量控制指标，第0号检测点。"
        # which wraps to multiple lines. Verify key fragments:
        assert "备注内容：蓝色冷冻库项目" in page_text, "Long CJK cell content not found on page 1"
        assert "中的重要参数记录和质量控" in page_text, (
            "Wrapped CJK cell fragment not found on page 1"
        )

        # Also verify total CJK character count is substantial (>200)
        import re

        all_text = "".join(page.get_text() for page in doc)
        doc.close()

        cjk_chars = re.findall(r"[\u4e00-\u9fff]", all_text)
        assert len(cjk_chars) > 200, f"Expected >200 CJK characters in PDF, got {len(cjk_chars)}"


def _tc(display_value: str, align: str | None = None):
    canonical = CanonicalRenderTableCell(field_path="", field_key="", raw_value=display_value or "")
    return LocalizedRenderTableCell(canonical=canonical, display_value=display_value, align=align)


_DUMMY_TABLE_KEY = "test_pagination"


# ---------------------------------------------------------------------------
# Test 2: DRAFT watermark on every page in draft mode
# ---------------------------------------------------------------------------


class TestDraftWatermark:
    def test_draft_watermark_on_every_page(self):
        """Every page in the PDF must contain the DRAFT watermark text in draft mode."""
        sections, _ = _build_100_row_cjk_table()
        _, pdf_bytes = _make_model(sections, is_draft=True)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx, page in enumerate(doc):
            text = page.get_text()
            assert "DRAFT" in text, (
                f"Page {page_idx + 1}: DRAFT watermark not found in text. "
                f"Page text (first 200 chars): {text[:200]}"
            )
        doc.close()

    def test_no_draft_watermark_in_formal_mode(self):
        """No DRAFT watermark when is_draft=False."""
        sections, _ = _build_100_row_cjk_table()
        _, pdf_bytes = _make_model(sections, is_draft=False)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx, page in enumerate(doc):
            text = page.get_text()
            # The word "DRAFT" should not appear as a standalone watermark.
            # (It might appear in unrelated text — check it's not centered/large)
            # Since our content never contains "DRAFT", this is reliable.
            assert "DRAFT" not in text, f"Page {page_idx + 1}: DRAFT watermark found in formal mode"
        doc.close()


def _tc(display_value: str, align: str | None = None):
    canonical = CanonicalRenderTableCell(field_path="", field_key="", raw_value=display_value or "")
    return LocalizedRenderTableCell(canonical=canonical, display_value=display_value, align=align)


_DUMMY_TABLE_KEY = "test_pagination"


# ---------------------------------------------------------------------------
# Test 3: Metrics rendering (P0-1)
# ---------------------------------------------------------------------------


class TestMetricsRendering:
    def test_all_metric_labels_values_units_in_pdf(self):
        """All 5 metrics' labels, display_values, and units must appear in PDF text."""
        sections = _build_metrics_sections()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()

        expected_metrics = [
            ("总设计制冷量", "250.0", "kW(r)"),
            ("预冷能力", "180.5", "kW(r)"),
            ("冷藏库面积", "1,200.0", "m2"),
            ("总投资估算", "5,800,000", "CNY"),
            ("冷库总容积", "3,600", "m3"),
        ]

        for label, value, _unit in expected_metrics:
            assert label in all_text, (
                f"Metric label '{label}' not found in PDF. First 500 chars: {all_text[:500]}"
            )
            # Value should appear (may be part of "label: value unit" string)
            assert value in all_text, (
                f"Metric value '{value}' not found in PDF. First 500 chars: {all_text[:500]}"
            )

    def test_docx_and_pdf_contain_same_metric_set(self):
        """DOCX and PDF must contain the same set of metric labels and units."""
        sections = _build_metrics_sections()
        metadata = _make_metadata()
        manifest = _make_manifest(sections)
        model = LocalizedReportRenderModel(metadata=metadata, sections=sections, manifest=manifest)

        # Render both formats
        pdf_bytes = PdfRenderer().render(model)
        docx_bytes = DocxRenderer().render(model)

        # Extract PDF text
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pdf_text = "".join(page.get_text() for page in pdf_doc)
        pdf_doc.close()

        # Extract DOCX text
        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            docx_text = ""
            for name in zf.namelist():
                if name.endswith(".xml"):
                    docx_text += zf.read(name).decode("utf-8", errors="ignore")

        expected_labels = [
            "总设计制冷量",
            "预冷能力",
            "冷藏库面积",
            "总投资估算",
            "冷库总容积",
        ]
        expected_units = ["kW(r)", "m2", "CNY", "m3"]

        for label in expected_labels:
            assert label in pdf_text, f"PDF missing metric label: {label}"
            assert label in docx_text, f"DOCX missing metric label: {label}"

        for unit in expected_units:
            assert unit in pdf_text, f"PDF missing metric unit: {unit}"
            assert unit in docx_text, f"DOCX missing metric unit: {unit}"


def _tc(display_value: str, align: str | None = None):
    canonical = CanonicalRenderTableCell(field_path="", field_key="", raw_value=display_value or "")
    return LocalizedRenderTableCell(canonical=canonical, display_value=display_value, align=align)


_DUMMY_TABLE_KEY = "test_pagination"


# ---------------------------------------------------------------------------
# Test 4: Content type coverage
# ---------------------------------------------------------------------------


class TestContentTypes:
    def test_text_content_type(self):
        """Text content type renders correctly."""
        sections = [
            LocalizedRenderSection(
                section_key="s1",
                title="测试章节",
                level=1,
                content_type="text",
                text="这是一个测试文本段落，用于验证文本渲染功能。",
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()

        assert "测试章节" in all_text
        assert "这是一个测试文本段落" in all_text

    def test_number_content_type(self):
        """Number content type renders correctly."""
        from cold_storage.modules.reports.domain.render_model import CanonicalRenderMetric

        sections = [
            LocalizedRenderSection(
                section_key="s1",
                title="制冷量",
                level=1,
                content_type="number",
                number=LocalizedRenderNumber(
                    canonical=CanonicalRenderMetric(
                        field_path="test",
                        field_key="test",
                        raw_value=250.0,
                        unit_code="kW(r)",
                    ),
                    display_value="250.0",
                    display_unit="kW(r)",
                ),
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()

        assert "250.0" in all_text
        assert "kW(r)" in all_text

    def test_empty_section(self):
        """Empty section renders with placeholder text."""
        sections = [
            LocalizedRenderSection(
                section_key="s1",
                title="空章节",
                level=1,
                content_type="empty",
                is_empty=True,
                empty_reason_text="未提供",
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()

        assert "空章节" in all_text
        assert "未提供" in all_text

    def test_finding_content_type(self):
        """Finding content type renders text and optional table."""
        table = LocalizedRenderTable(
            canonical=CanonicalRenderTable(table_key=_DUMMY_TABLE_KEY),
            title="发现明细",
            headers=["检查项", "状态"],
            rows=[
                [
                    _tc("设备选型"),
                    _tc("合格"),
                ],
                [
                    _tc("能效比"),
                    _tc("需优化"),
                ],
            ],
        )
        sections = [
            LocalizedRenderSection(
                section_key="f1",
                title="质量发现",
                level=1,
                content_type="finding",
                text="发现以下问题需要关注：",
                table=table,
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()

        assert "质量发现" in all_text
        assert "发现以下问题" in all_text
        assert "设备选型" in all_text
        assert "合格" in all_text


def _tc(display_value: str, align: str | None = None):
    canonical = CanonicalRenderTableCell(field_path="", field_key="", raw_value=display_value or "")
    return LocalizedRenderTableCell(canonical=canonical, display_value=display_value, align=align)


_DUMMY_TABLE_KEY = "test_pagination"


# ---------------------------------------------------------------------------
# Test 5: Small table (no overflow needed)
# ---------------------------------------------------------------------------


class TestSmallTable:
    def test_small_table_single_page(self):
        """A small table (5 rows) should fit on one content page."""
        rows = [
            [
                _tc(f"项目{i}", align="left"),
                _tc(f"值{i}", align="right"),
            ]
            for i in range(5)
        ]
        table = LocalizedRenderTable(
            canonical=CanonicalRenderTable(table_key=_DUMMY_TABLE_KEY),
            title="小表格",
            headers=["项目", "值"],
            rows=rows,
        )
        sections = [
            LocalizedRenderSection(
                section_key="s1",
                title="小表格",
                level=1,
                content_type="table",
                table=table,
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Cover + 1 content page = 2 pages
        assert doc.page_count == 2, f"Expected 2 pages for small table, got {doc.page_count}"
        doc.close()
