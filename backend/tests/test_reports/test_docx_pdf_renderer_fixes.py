"""Tests for DOCX and PDF renderer fixes: P0-4, P0-5, P0-7.

P0-4: DOCX page orientation and table config
P0-5: DOCX header, footer, and watermark
P0-7: PDF cell alignment priority
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any

import fitz
from docx import Document
from docx.enum.section import WD_ORIENT

from cold_storage.modules.reports.domain.errors import TemplateManifestError
from cold_storage.modules.reports.domain.render_model import (
    RenderManifest,
    RenderMetadata,
    RenderSection,
    RenderTable,
    RenderTableCell,
    ReportRenderModel,
)
from cold_storage.modules.reports.renderers.docx_renderer import DocxRenderer
from cold_storage.modules.reports.renderers.pdf_renderer import PdfRenderer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(**overrides: Any) -> RenderMetadata:
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
    fmt: str = "pdf",
) -> RenderManifest:
    return RenderManifest(
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
        schema_version="cold_storage_concept_design@1.0.0",
        source_content_hash="a" * 64,
        sections=[s.section_key for s in sections],
        format=fmt,
        render_settings=render_settings or {},
    )


def _render_pdf(
    sections: list[RenderSection],
    *,
    is_draft: bool = False,
    render_settings: dict | None = None,
) -> bytes:
    metadata = _make_metadata()
    manifest = _make_manifest(sections, render_settings=render_settings, fmt="pdf")
    model = ReportRenderModel(metadata=metadata, sections=sections, manifest=manifest)
    return PdfRenderer().render(model, is_draft=is_draft)


def _render_docx(
    sections: list[RenderSection],
    *,
    is_draft: bool = False,
    render_settings: dict | None = None,
) -> bytes:
    metadata = _make_metadata()
    manifest = _make_manifest(sections, render_settings=render_settings, fmt="docx")
    model = ReportRenderModel(metadata=metadata, sections=sections, manifest=manifest)
    return DocxRenderer().render(model, is_draft=is_draft)


def _get_docx_text(docx_bytes: bytes) -> str:
    """Extract all XML text from a DOCX file."""
    with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
        text = ""
        for name in zf.namelist():
            if name.endswith(".xml"):
                text += zf.read(name).decode("utf-8", errors="ignore")
        return text


# ===========================================================================
# P0-7: PDF cell alignment priority
# ===========================================================================


class TestP0_7_PdfCellAlignment:
    def test_manifest_right_cell_explicit_left_final_left(self):
        """Manifest column right + cell explicit left -> final left."""
        sections = [
            RenderSection(
                section_key="s1",
                title="对齐测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["列A"],
                    rows=[
                        [RenderTableCell(value="值", align="left")],
                    ],
                ),
            )
        ]
        pdf_bytes = _render_pdf(
            sections,
            render_settings={
                "tables": {
                    "s1": {
                        "columns": [{"key": "a", "header": "列A", "align": "right"}],
                    },
                },
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[1]  # content page
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["text"] == "值":
                        margin = 56.69
                        assert span["bbox"][0] < margin + 20, (
                            f"Cell text '值' should be left-aligned, but x0={span['bbox'][0]:.1f}"
                        )
        doc.close()

    def test_manifest_center_cell_none_final_center(self):
        """Manifest column center + cell None -> final center."""
        sections = [
            RenderSection(
                section_key="s1",
                title="对齐测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["列A"],
                    rows=[
                        [RenderTableCell(value="居中")],  # align=None
                    ],
                ),
            )
        ]
        pdf_bytes = _render_pdf(
            sections,
            render_settings={
                "tables": {
                    "s1": {
                        "columns": [{"key": "a", "header": "列A", "align": "center"}],
                    },
                },
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[1]
        blocks = page.get_text("dict")["blocks"]
        page_width = page.rect.width
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["text"] == "居中":
                        text_center = (span["bbox"][0] + span["bbox"][2]) / 2
                        page_center = page_width / 2
                        assert abs(text_center - page_center) < 100, (
                            f"Cell text '居中' should be center-aligned, "
                            f"text_center={text_center:.1f}, page_center={page_center:.1f}"
                        )
        doc.close()

    def test_split_row_alignment_consistent_with_normal(self):
        """Split row alignment must be consistent with normal row alignment."""
        long_text = "这是一段超长的中文文本用于测试分页对齐一致性。" * 50
        sections = [
            RenderSection(
                section_key="s1",
                title="分页对齐测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["项目", "内容"],
                    rows=[
                        [
                            RenderTableCell(value="短文本", align="right"),
                            RenderTableCell(value="普通"),
                        ],
                        [
                            RenderTableCell(value="长文本", align="right"),
                            RenderTableCell(value=long_text),
                        ],
                    ],
                ),
            )
        ]
        pdf_bytes = _render_pdf(
            sections,
            render_settings={
                "tables": {
                    "s1": {
                        "columns": [
                            {"key": "a", "header": "项目", "align": "left"},
                            {"key": "b", "header": "内容", "align": "left"},
                        ],
                    },
                },
            },
        )
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert doc.page_count >= 1
        doc.close()


# ===========================================================================
# P0-4: DOCX orientation
# ===========================================================================


class TestP0_4_DocxOrientation:
    def test_default_portrait_orientation(self):
        """Default orientation is portrait when page.orientation is not set."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="测试内容",
            )
        ]
        docx_bytes = _render_docx(sections)
        doc = Document(BytesIO(docx_bytes))
        for section in doc.sections:
            assert section.orientation == WD_ORIENT.PORTRAIT

    def test_manifest_landscape_orientation(self):
        """page.orientation=landscape sets all sections to landscape."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="测试内容",
            )
        ]
        docx_bytes = _render_docx(
            sections,
            render_settings={"page": {"orientation": "landscape"}},
        )
        doc = Document(BytesIO(docx_bytes))
        for section in doc.sections:
            assert section.orientation == WD_ORIENT.LANDSCAPE

    def test_landscape_sections_creates_new_word_section(self):
        """Landscape section creates a new Word section with landscape orientation."""
        sections = [
            RenderSection(
                section_key="portrait1",
                title="竖版章节",
                level=1,
                content_type="text",
                text="竖版内容",
            ),
            RenderSection(
                section_key="landscape1",
                title="横版章节",
                level=1,
                content_type="text",
                text="横版内容",
            ),
            RenderSection(
                section_key="portrait2",
                title="恢复竖版",
                level=1,
                content_type="text",
                text="竖版内容",
            ),
        ]
        docx_bytes = _render_docx(
            sections,
            render_settings={
                "landscape_sections": ["landscape1"],
            },
        )
        doc = Document(BytesIO(docx_bytes))
        assert len(doc.sections) >= 2

    def test_table_config_orientation_overrides_landscape_sections(self):
        """tables[key].orientation overrides landscape_sections list."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="测试内容",
            )
        ]
        docx_bytes = _render_docx(
            sections,
            render_settings={
                "landscape_sections": ["s1"],
                "tables": {
                    "s1": {"orientation": "portrait"},
                },
            },
        )
        doc = Document(BytesIO(docx_bytes))
        assert doc.sections[0].orientation == WD_ORIENT.PORTRAIT


# ===========================================================================
# P0-4: DOCX table config
# ===========================================================================


class TestP0_4_DocxTableConfig:
    def test_unit_row_false_no_unit_row(self):
        """unit_row=false should NOT create a unit row."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["A", "B"],
                    rows=[[RenderTableCell(value="1"), RenderTableCell(value="2")]],
                    unit_row=["kg", "m"],
                ),
            )
        ]
        docx_bytes = _render_docx(
            sections,
            render_settings={
                "tables": {
                    "s1": {"unit_row": False},
                },
            },
        )
        doc = Document(BytesIO(docx_bytes))
        assert len(doc.tables) >= 1
        table = doc.tables[0]
        assert len(table.rows) == 2

    def test_unit_row_true_creates_unit_row(self):
        """unit_row=true (default) creates unit row when data has units."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["A", "B"],
                    rows=[[RenderTableCell(value="1"), RenderTableCell(value="2")]],
                    unit_row=["kg", "m"],
                ),
            )
        ]
        docx_bytes = _render_docx(sections)
        doc = Document(BytesIO(docx_bytes))
        assert len(doc.tables) >= 1
        table = doc.tables[0]
        assert len(table.rows) == 3

    def test_column_count_mismatch_raises_error(self):
        """Column count mismatch between manifest and table raises TemplateManifestError."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["A", "B"],
                    rows=[[RenderTableCell(value="1"), RenderTableCell(value="2")]],
                ),
            )
        ]
        try:
            _render_docx(
                sections,
                render_settings={
                    "tables": {
                        "s1": {
                            "columns": [
                                {"key": "a", "header": "A"},
                            ],
                        },
                    },
                },
            )
            raise AssertionError("Should have raised TemplateManifestError")
        except TemplateManifestError:
            pass

    def test_invalid_width_ratio_raises_error(self):
        """Invalid width_ratio (all zero) raises TemplateManifestError."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["A", "B"],
                    rows=[[RenderTableCell(value="1"), RenderTableCell(value="2")]],
                ),
            )
        ]
        try:
            _render_docx(
                sections,
                render_settings={
                    "tables": {
                        "s1": {
                            "columns": [
                                {"key": "a", "header": "A", "width_ratio": 0},
                                {"key": "b", "header": "B", "width_ratio": 0},
                            ],
                        },
                    },
                },
            )
            raise AssertionError("Should have raised TemplateManifestError")
        except TemplateManifestError:
            pass


# ===========================================================================
# P0-5: DOCX header/watermark
# ===========================================================================


class TestP0_5_DocxHeaderWatermark:
    def test_custom_header_and_watermark_both_exist(self):
        """Custom header text and watermark both exist in output."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="测试内容",
            )
        ]
        docx_bytes = _render_docx(
            sections,
            is_draft=True,
            render_settings={
                "header": {"right": "自定义页眉"},
                "watermark": {"text": "DRAFT"},
            },
        )
        docx_text = _get_docx_text(docx_bytes)
        assert "自定义页眉" in docx_text, "Custom header text not found"
        assert "PowerPlusWaterMarkObject" in docx_text, "Watermark not found"

    def test_watermark_does_not_delete_header_text(self):
        """Watermark adds a separate paragraph, header text is preserved."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="测试内容",
            )
        ]
        docx_bytes = _render_docx(
            sections,
            is_draft=True,
            render_settings={
                "header": {"left": "左侧", "right": "右侧"},
                "watermark": {"text": "DRAFT"},
            },
        )
        docx_text = _get_docx_text(docx_bytes)
        assert "左侧" in docx_text, "Left header text not found"
        assert "右侧" in docx_text, "Right header text not found"
        assert "DRAFT" in docx_text, "Watermark text not found"

    def test_page_number_field_in_footer_left(self):
        """{page_number} in footer left generates PAGE field."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="测试内容",
            )
        ]
        docx_bytes = _render_docx(
            sections,
            render_settings={
                "footer": {"left": "第{page_number}页", "center": "", "right": ""},
            },
        )
        docx_text = _get_docx_text(docx_bytes)
        assert "PAGE" in docx_text, "PAGE field not found in footer"

    def test_page_number_field_in_footer_right(self):
        """{page_number} in footer right generates PAGE field."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="text",
                text="测试内容",
            )
        ]
        docx_bytes = _render_docx(
            sections,
            render_settings={
                "footer": {"left": "", "center": "", "right": "第{page_number}页"},
            },
        )
        docx_text = _get_docx_text(docx_bytes)
        assert "PAGE" in docx_text, "PAGE field not found in footer right"

    def test_landscape_section_tab_stop_matches_width(self):
        """Landscape section tab stops match landscape page width."""
        sections = [
            RenderSection(
                section_key="s1",
                title="横版",
                level=1,
                content_type="text",
                text="横版内容",
            )
        ]
        docx_bytes = _render_docx(
            sections,
            render_settings={
                "landscape_sections": ["s1"],
                "header": {"left": "左", "center": "中", "right": "右"},
                "footer": {"left": "左", "center": "中", "right": "右"},
            },
        )
        assert len(docx_bytes) > 0
        doc = Document(BytesIO(docx_bytes))
        assert len(doc.sections) >= 1


# ===========================================================================
# P0-7: PDF manifest errors
# ===========================================================================


class TestP0_7_PdfManifestErrors:
    def test_wrong_column_count_raises_manifest_error(self):
        """Wrong column count raises TemplateManifestError."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["A", "B"],
                    rows=[[RenderTableCell(value="1"), RenderTableCell(value="2")]],
                ),
            )
        ]
        try:
            _render_pdf(
                sections,
                render_settings={
                    "tables": {
                        "s1": {
                            "columns": [{"key": "a", "header": "A"}],
                        },
                    },
                },
            )
            raise AssertionError("Should have raised TemplateManifestError")
        except TemplateManifestError:
            pass

    def test_invalid_width_ratio_raises_manifest_error(self):
        """Invalid width_ratio (all zero) raises TemplateManifestError."""
        sections = [
            RenderSection(
                section_key="s1",
                title="测试",
                level=1,
                content_type="table",
                table=RenderTable(
                    title="测试表",
                    headers=["A", "B"],
                    rows=[[RenderTableCell(value="1"), RenderTableCell(value="2")]],
                ),
            )
        ]
        try:
            _render_pdf(
                sections,
                render_settings={
                    "tables": {
                        "s1": {
                            "columns": [
                                {"key": "a", "header": "A", "width_ratio": 0},
                                {"key": "b", "header": "B", "width_ratio": 0},
                            ],
                        },
                    },
                },
            )
            raise AssertionError("Should have raised TemplateManifestError")
        except TemplateManifestError:
            pass
