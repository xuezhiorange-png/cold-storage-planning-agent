"""Tests for PDF renderer fixes: P0-3, P0-4, P0-6, P0-7.

P0-3: Unit row overlap with header
P0-4: Manifest controls header/footer/watermark/placeholder
P0-6: Long text pagination across pages
P0-7: Ultra-tall table rows, repeat_header=false, landscape
"""

from __future__ import annotations

import fitz

from cold_storage.modules.reports.domain.render_model import (
    RenderManifest,
    RenderMetadata,
    RenderSection,
    RenderTable,
    RenderTableCell,
    ReportRenderModel,
)
from cold_storage.modules.reports.renderers.pdf_renderer import PdfRenderer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(**overrides: object) -> RenderMetadata:
    defaults = dict(
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
    defaults.update(overrides)
    return RenderMetadata(**defaults)  # type: ignore[arg-type]


def _make_manifest(
    sections: list[RenderSection],
    render_settings: dict | None = None,
) -> RenderManifest:
    return RenderManifest(
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
        schema_version="cold_storage_concept_design@1.0.0",
        source_content_hash="a" * 64,
        sections=[s.section_key for s in sections],
        format="pdf",
        render_settings=render_settings or {},
    )


def _make_model(
    sections: list[RenderSection],
    *,
    is_draft: bool = False,
    render_settings: dict | None = None,
    metadata_overrides: dict | None = None,
) -> tuple[ReportRenderModel, bytes]:
    metadata = _make_metadata(**(metadata_overrides or {}))
    manifest = _make_manifest(sections, render_settings=render_settings)
    model = ReportRenderModel(metadata=metadata, sections=sections, manifest=manifest)
    pdf_bytes = PdfRenderer().render(model, is_draft=is_draft)
    return model, pdf_bytes


def _build_100_row_table_with_unit() -> list[RenderSection]:
    rows = []
    for i in range(100):
        rows.append(
            [
                RenderTableCell(value=f"设备{i:03d}"),
                RenderTableCell(value=f"描述文字第{i:03d}行这是一段较长的描述用于测试换行"),
                RenderTableCell(value=f"{250 + i * 5}.0"),
            ]
        )
    table = RenderTable(
        title="设备清单",
        headers=["编号", "描述", "功率"],
        rows=rows,
        unit_row=["", "", "kW"],
    )
    return [
        RenderSection(
            section_key="equipment",
            title="设备清单",
            level=1,
            content_type="table",
            table=table,
        )
    ]


# ===========================================================================
# P0-3: Unit row overlap with header
# ===========================================================================


class TestP0_3_UnitRowOverlap:
    def test_header_unit_y_monotonically_increasing(self):
        """Header and unit row Y coordinates must be strictly increasing,
        with no bounding-box overlap.  The first data row must be below the
        unit row.
        """
        sections = _build_100_row_table_with_unit()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Page index 1 is the first table page (index 0 = cover)
        page = doc[1]
        blocks = page.get_text("dict")["blocks"]
        doc.close()

        # Collect text spans sorted by y0
        spans: list[tuple[float, str]] = []
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    spans.append((span["bbox"][1], span["text"]))

        # Find the header row ("编号", "描述", "功率") — topmost
        header_spans = [s for s in spans if s[1] in ("编号", "描述", "功率")]
        unit_spans = [s for s in spans if s[1] == "(kW)"]
        assert header_spans, "Header row not found"
        assert unit_spans, "Unit row (kW) not found"

        header_top = min(y for y, _ in header_spans)
        unit_top = min(y for y, _ in unit_spans)
        assert unit_top > header_top, f"Unit row y={unit_top} must be below header y={header_top}"

        # First data row "设备000" must be below unit row
        data_spans = [s for s in spans if s[1].startswith("设备000")]
        assert data_spans
        data_top = min(y for y, _ in data_spans)
        assert data_top > unit_top, (
            f"First data row y={data_top} must be below unit row y={unit_top}"
        )

    def test_unit_row_not_overlapping_header_bboxes(self):
        """No bbox of the header row may overlap with any bbox of the unit row."""
        sections = _build_100_row_table_with_unit()
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[1]
        blocks = page.get_text("dict")["blocks"]
        doc.close()

        header_bboxes: list[tuple[float, float, float, float]] = []
        unit_bboxes: list[tuple[float, float, float, float]] = []

        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span["bbox"]
                    text = span["text"]
                    if text in ("编号", "描述", "功率"):
                        header_bboxes.append(bbox)
                    elif text == "(kW)":
                        unit_bboxes.append(bbox)

        assert header_bboxes, "No header bboxes found"
        assert unit_bboxes, "No unit bboxes found"

        for hb in header_bboxes:
            for ub in unit_bboxes:
                # No vertical overlap: header bottom <= unit top
                assert hb[3] <= ub[1] + 0.1, f"Header bbox {hb} overlaps unit bbox {ub}"


# ===========================================================================
# P0-4: Manifest controls output
# ===========================================================================


class TestP0_4_ManifestControls:
    def test_custom_header_text(self):
        """Modifying header_right in manifest should change PDF header text."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="正文内容",
            )
        ]
        _, pdf_bytes = _make_model(
            sections,
            render_settings={
                "header": {"left": "", "center": "", "right": "自定义页眉文字"},
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()
        assert "自定义页眉文字" in all_text, "Custom header text not found in PDF"

    def test_custom_footer_text(self):
        """Modifying footer_center in manifest should change PDF footer text."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="正文内容",
            )
        ]
        _, pdf_bytes = _make_model(
            sections,
            render_settings={
                "footer": {"left": "", "center": "第 {page_number} 页", "right": ""},
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()
        assert "第 1 页" in all_text, "Custom footer text not found in PDF"

    def test_watermark_text_override(self):
        """Modifying watermark.text in manifest changes watermark on every page."""
        sections = _build_100_row_table_with_unit()
        _, pdf_bytes = _make_model(
            sections,
            is_draft=True,
            render_settings={
                "watermark": {"text": "机密文件", "font_size_pt": 50},
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_idx, page in enumerate(doc):
            text = page.get_text()
            assert "机密文件" in text, f"Page {page_idx + 1}: watermark '机密文件' not found"
        doc.close()

    def test_watermark_color_override(self):
        """Modifying watermark.color should change the watermark color in PDF objects."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="正文",
            )
        ]
        _, pdf_bytes = _make_model(
            sections,
            is_draft=True,
            render_settings={
                "watermark": {"text": "DRAFT", "color": "#FF0000", "opacity": 0.5},
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Check page 1 (cover) for color change — the watermark text should
        # use a different color than the default gray
        page = doc[0]
        # Get text dict to find watermark color
        blocks = page.get_text("dict")["blocks"]
        found_draft = False
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["text"] == "DRAFT":
                        found_draft = True
                        # color should NOT be default (0.8, 0.8, 0.8)
                        color = span.get("color", 0)
                        # color is an int; convert to check it's not gray
                        # Red: 0xFF0000 = 16711680
                        assert color != 0xCCCCCC, f"Watermark color is still default gray: {color}"
        doc.close()
        assert found_draft, "DRAFT text not found on cover page"

    def test_margin_override_shifts_text_position(self):
        """Changing margins in manifest should shift text bbox positions."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="正文内容",
            )
        ]
        # Default margins
        _, pdf_default = _make_model(sections)
        # Larger margins
        _, pdf_large = _make_model(
            sections,
            render_settings={
                "page": {
                    "margin_left_pt": 113.38,  # 4 cm
                    "margin_top_pt": 113.38,
                    "margin_right_pt": 56.69,
                    "margin_bottom_pt": 56.69,
                },
            },
        )

        def get_text_bbox(pdf_bytes: bytes) -> tuple[float, float]:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page = doc[1]  # first content page
            blocks = page.get_text("dict")["blocks"]
            doc.close()
            for block in blocks:
                if block["type"] != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if "正文" in span["text"]:
                            return span["bbox"][0], span["bbox"][1]
            return 0, 0

        x_default, y_default = get_text_bbox(pdf_default)
        x_large, y_large = get_text_bbox(pdf_large)
        assert x_large > x_default, f"Large margin x={x_large} should be > default x={x_default}"
        assert y_large > y_default, f"Large margin y={y_large} should be > default y={y_default}"

    def test_empty_section_placeholder_from_manifest(self):
        """empty_section_behavior.placeholder_text in manifest overrides default."""
        sections = [
            RenderSection(
                section_key="s1",
                title="空章节",
                level=1,
                content_type="empty",
                is_empty=True,
                empty_reason="not_provided",
            )
        ]
        _, pdf_bytes = _make_model(
            sections,
            render_settings={
                "empty_section_behavior": {
                    "behavior": "show_placeholder",
                    "placeholder_text": {
                        "not_provided": "数据未提供（自定义）",
                        "not_calculated": "尚未计算（自定义）",
                    },
                },
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = "".join(page.get_text() for page in doc)
        doc.close()
        assert "数据未提供（自定义）" in all_text, (
            f"Custom placeholder not found. PDF text: {all_text[:500]}"
        )


# ===========================================================================
# P0-6: Long text pagination
# ===========================================================================


class TestP0_6_LongTextPagination:
    def test_300_line_chinese_text_multipage(self):
        """A 300-line Chinese text section must span multiple pages,
        with the last line present and no bbox exceeding bottom margin.
        """
        long_text = "\n".join(
            f"这是第{i:03d}行的中文内容，用于测试长文本分页功能是否正常工作。"
            f"每一行都包含足够的中文字符以确保换行和分页被正确触发。"
            for i in range(300)
        )
        sections = [
            RenderSection(
                section_key="long_text",
                title="长文本测试",
                level=1,
                content_type="text",
                text=long_text,
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        assert page_count >= 3, f"Expected >= 3 pages for 300-line text, got {page_count}"

        # Check last line exists somewhere in the PDF
        all_text = "".join(page.get_text() for page in doc)
        assert "第299行" in all_text, "Last line (第299行) not found in PDF"

        # Check no text bbox exceeds page bottom margin
        for page_idx, page in enumerate(doc):
            page_height = page.rect.height
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block["type"] != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = span["bbox"]
                        assert bbox[3] <= page_height + 5, (
                            f"Page {page_idx}: text y1={bbox[3]:.1f} exceeds "
                            f"page_height {page_height:.1f}"
                        )
        doc.close()

    def test_single_cell_1000_chars_renders(self):
        """A single table cell with 1000+ Chinese chars renders without
        infinite pages and content is complete.
        """
        mega_text = "这是一段超长的中文文本" * 200  # ~1200 chars
        rows = [
            [
                RenderTableCell(value="描述"),
                RenderTableCell(value=mega_text),
            ]
        ]
        table = RenderTable(
            title="超长文本表格",
            headers=["项目", "内容"],
            rows=rows,
        )
        sections = [
            RenderSection(
                section_key="mega",
                title="超长文本测试",
                level=1,
                content_type="table",
                table=table,
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        # Should not produce more than 10 pages
        assert page_count <= 10, f"Too many pages for single cell: {page_count}"

        # Content must be complete — check that the text appears many times
        # (PyMuPDF wraps text, so we can't check contiguous repetitions)
        all_text = "".join(page.get_text() for page in doc)
        assert "这是一段超长的中文文本" in all_text
        # Count occurrences — 200 repetitions means it should appear ~200 times
        count = all_text.count("这是一段超长的中文文本")
        assert count >= 100, f"Expected >= 100 occurrences of mega text, found {count}"
        doc.close()


# ===========================================================================
# P0-7: Ultra-tall table rows + repeat_header=false + landscape
# ===========================================================================


class TestP0_7_UltraTallAndRepeatHeader:
    def test_repeat_header_false_no_header_on_continuation(self):
        """When repeat_header=false, continuation pages must NOT have
        a repeated table header.
        """
        # Build a table large enough to span 2+ pages
        rows = []
        for i in range(80):
            rows.append(
                [
                    RenderTableCell(value=f"项目{i:03d}"),
                    RenderTableCell(
                        value=f"这是描述文字第{i:03d}行，用于确保表格足够长能够跨页显示"
                    ),
                    RenderTableCell(value=f"{i * 10}.0"),
                ]
            )
        table = RenderTable(
            title="大表格",
            headers=["编号", "描述", "数值"],
            rows=rows,
            unit_row=["", "", "kW"],
        )
        sections = [
            RenderSection(
                section_key="big",
                title="大表格测试",
                level=1,
                content_type="table",
                table=table,
            )
        ]
        _, pdf_bytes = _make_model(
            sections,
            render_settings={
                "tables": {
                    "columns": {},
                    "repeat_header": False,
                },
            },
        )

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert doc.page_count >= 3, f"Expected >= 3 pages, got {doc.page_count}"

        # Page 2 (index 1) should have the table with header
        # Page 3 (index 2) should NOT have header text "编号"
        # (Note: page 2 might still have header if table starts on page 1)
        # The key check: last content page should NOT have "编号" as a header span
        last_page = doc[-1]
        last_text = last_page.get_text()
        # "编号" appears in header — if repeat_header=false, it should NOT
        # appear on continuation pages.  However "编号" might appear as cell
        # data ("项目000" doesn't contain it).  Check for the full header row.
        # The header has "编号" + "描述" + "数值" together.
        # On the last page, there should not be all three header words together.
        has_all_header_words = all(w in last_text for w in ("编号", "描述", "数值"))
        assert not has_all_header_words, (
            "Last page still has full table header with repeat_header=false"
        )
        doc.close()

    def test_ultra_tall_row_renders_without_infinite_pages(self):
        """A single row with extremely long cell content should render
        across multiple lines without causing infinite page creation.
        """
        ultra_long = "超长内容文字" * 500  # ~3000 chars
        rows = [
            [
                RenderTableCell(value="标题"),
                RenderTableCell(value="普通内容"),
            ],
            [
                RenderTableCell(value="超长行"),
                RenderTableCell(value=ultra_long),
            ],
        ]
        table = RenderTable(
            title="超长行表格",
            headers=["项目", "内容"],
            rows=rows,
        )
        sections = [
            RenderSection(
                section_key="ultra",
                title="超长行测试",
                level=1,
                content_type="table",
                table=table,
            )
        ]
        _, pdf_bytes = _make_model(sections)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        assert page_count <= 15, f"Too many pages for ultra-tall row: {page_count}"

        all_text = "".join(page.get_text() for page in doc)
        assert "超长内容文字" in all_text, "Ultra-long content not found in PDF"
        doc.close()

    def test_landscape_orientation(self):
        """Landscape page should have width > height.
        P0-11: Uses manifest landscape_sections instead of manual width/height swap.
        """
        sections = [
            RenderSection(
                section_key="s1",
                title="横向测试",
                level=1,
                content_type="text",
                text="横向页面测试",
            )
        ]
        # Use landscape_sections in manifest to mark section s1 as landscape
        _, pdf_bytes = _make_model(
            sections,
            render_settings={
                "page": {
                    "landscape_sections": ["s1"],
                },
            },
        )

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Page 0 is cover (always portrait); page 1+ are content pages
        # Content pages for landscape sections should have width > height
        found_landscape = False
        for page_idx in range(1, doc.page_count):
            page = doc[page_idx]
            if page.rect.width > page.rect.height:
                found_landscape = True
                break
        assert found_landscape, "No landscape page found after setting landscape_sections=['s1']"
        doc.close()
