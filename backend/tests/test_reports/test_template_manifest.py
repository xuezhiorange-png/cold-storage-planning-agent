"""Tests for TemplateManifest parsing, DOCX/PDF manifest split, and content hash.

Covers:
1. Parse manifest with tables, empty_section_behavior, placeholder_text
2. DOCX manifest has format="docx", PDF has format="pdf"
3. Content hashes are different for DOCX vs PDF manifests
4. Modify page margins → output changes
5. Modify header text → output changes
6. Modify footer text → output changes
7. Modify watermark text/size/color → output changes
8. Modify table column config → output changes
9. Modify empty_section_behavior.placeholder_text → output changes
10. After seed_default_templates, both DOCX and PDF active templates exist
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cold_storage.modules.reports.domain.render_model import (
    RenderManifest,
    ReportRenderModel,
    TemplateEmptySectionConfig,
    TemplateFontConfig,
    TemplateHeaderFooterConfig,
    TemplateManifest,
    TemplatePageConfig,
    TemplateTableConfig,
    TemplateWatermarkConfig,
    format_number,
)
from cold_storage.modules.reports.application.render_model_builder import (
    build_render_model,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = (
    Path(__file__).parent.parent.parent
    / "src"
    / "cold_storage"
    / "modules"
    / "reports"
    / "templates"
    / "cold_storage_concept_design"
    / "1.0.0"
)


@pytest.fixture()
def sample_manifest() -> dict:
    """A manifest dict with all rendering config fields."""
    return {
        "template_code": "cold_storage_concept_design",
        "version": "1.0.0",
        "format": "docx",
        "report_type": "cold_storage_concept_design",
        "schema_version": "cold_storage_concept_design@1.0.0",
        "locale": "zh-CN",
        "page": {
            "width_pt": 595.276,
            "height_pt": 841.89,
            "margin_top_pt": 56.69,
            "margin_bottom_pt": 56.69,
            "margin_left_pt": 56.69,
            "margin_right_pt": 56.69,
            "orientation": "portrait",
        },
        "fonts": {
            "body_name": "SimSun",
            "body_size_pt": 10.5,
            "heading1_size_pt": 16,
            "heading2_size_pt": 14,
            "heading3_size_pt": 12,
            "table_header_size_pt": 9.5,
            "table_body_size_pt": 9,
            "footer_size_pt": 8,
            "header_size_pt": 8,
        },
        "header": {
            "left": "",
            "center": "",
            "right": "{project_name} — {report_type}",
        },
        "footer": {"left": "", "center": "— {page_number} —", "right": ""},
        "watermark": {
            "text": "DRAFT",
            "font_size_pt": 72,
            "color": "#CCCCCC",
            "opacity": 0.3,
            "angle": 45,
        },
        "empty_section_behavior": {
            "behavior": "show_placeholder",
            "placeholder_text": {
                "not_provided": "该部分数据未提供",
                "not_calculated": "该部分尚未计算",
            },
        },
        "required_sections": [
            "project_summary",
            "cooling_load",
            "equipment_selection",
        ],
        "optional_sections": ["scheme_comparison", "investment_estimate"],
        "landscape_sections": [],
        "tables": {
            "scheme_comparison": {
                "columns": ["方案", "功率", "投资"],
                "unit_row": ["", "kW(e)", "万元"],
            }
        },
        "numbering": {"style": "decimal"},
        "quality_finding_rendering": {
            "blocker": {"color": "#CC0000", "bold": True},
        },
    }


@pytest.fixture()
def sample_content() -> dict:
    """Minimal report content for build_render_model."""
    return {
        "report_metadata": {"project_id": "test-project"},
        "project_summary": {
            "project_name": "Test Project",
            "project_location": "Shanghai",
            "description": "A test project",
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Parse manifest preserves tables, empty_section_behavior, placeholder_text
# ---------------------------------------------------------------------------


class TestManifestParsingPreservesConfig:
    """Test that from_manifest_json preserves all rendering config fields."""

    def test_empty_section_behavior_preserved(self, sample_manifest):
        tm = TemplateManifest.from_manifest_json(sample_manifest)
        assert tm.empty_section_behavior.behavior == "show_placeholder"
        assert tm.empty_section_behavior.placeholder_text["not_provided"] == "该部分数据未提供"
        assert tm.empty_section_behavior.placeholder_text["not_calculated"] == "该部分尚未计算"

    def test_tables_preserved(self, sample_manifest):
        tm = TemplateManifest.from_manifest_json(sample_manifest)
        assert "scheme_comparison" in tm.tables
        tbl = tm.tables["scheme_comparison"]
        assert isinstance(tbl, TemplateTableConfig)
        assert len(tbl.columns) == 3
        assert tbl.columns[0].key == "方案"
        assert tbl.unit_row is True

    def test_required_optional_sections_preserved(self, sample_manifest):
        tm = TemplateManifest.from_manifest_json(sample_manifest)
        assert tm.required_sections == ["project_summary", "cooling_load", "equipment_selection"]
        assert tm.optional_sections == ["scheme_comparison", "investment_estimate"]

    def test_numbering_preserved(self, sample_manifest):
        tm = TemplateManifest.from_manifest_json(sample_manifest)
        assert tm.numbering == {"style": "decimal"}

    def test_quality_finding_rendering_preserved(self, sample_manifest):
        tm = TemplateManifest.from_manifest_json(sample_manifest)
        assert tm.quality_finding_rendering["blocker"]["color"] == "#CC0000"

    def test_format_preserved(self, sample_manifest):
        tm = TemplateManifest.from_manifest_json(sample_manifest)
        assert tm.format == "docx"
        assert tm.template_code == "cold_storage_concept_design"
        assert tm.version == "1.0.0"

    def test_legacy_string_empty_section_behavior(self):
        """Legacy manifest with empty_section_behavior as a string."""
        manifest = {
            "empty_section_behavior": "show_placeholder",
            "placeholder_text": {"not_provided": "未提供", "not_calculated": "未计算"},
        }
        tm = TemplateManifest.from_manifest_json(manifest)
        assert tm.empty_section_behavior.behavior == "show_placeholder"
        assert tm.empty_section_behavior.placeholder_text["not_provided"] == "未提供"

    def test_legacy_string_columns_normalized(self):
        """Legacy tables with list-of-strings columns are normalized."""
        manifest = {
            "tables": {
                "test_table": {
                    "columns": ["Col1", "Col2", "Col3"],
                    "unit_row": ["", "kW", ""],
                }
            }
        }
        tm = TemplateManifest.from_manifest_json(manifest)
        tbl = tm.tables["test_table"]
        assert tbl.columns[0].key == "Col1"
        assert tbl.columns[0].header == "Col1"


# ---------------------------------------------------------------------------
# Test 2: DOCX/PDF format distinction
# ---------------------------------------------------------------------------


class TestDocxPdfFormatDistinction:
    """Test that DOCX and PDF manifests have correct format fields."""

    def test_docx_manifest_format(self):
        manifest_path = _TEMPLATES_DIR / "docx" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tm = TemplateManifest.from_manifest_json(manifest)
        assert tm.format == "docx"

    def test_pdf_manifest_format(self):
        manifest_path = _TEMPLATES_DIR / "pdf" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tm = TemplateManifest.from_manifest_json(manifest)
        assert tm.format == "pdf"


# ---------------------------------------------------------------------------
# Test 3: Content hashes differ for DOCX vs PDF
# ---------------------------------------------------------------------------


class TestContentHashDistinction:
    """Test that DOCX and PDF manifest content hashes are different."""

    def _compute_hash(self, manifest: dict) -> str:
        content_str = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content_str.encode()).hexdigest()

    def test_hashes_differ(self):
        docx_path = _TEMPLATES_DIR / "docx" / "manifest.json"
        pdf_path = _TEMPLATES_DIR / "pdf" / "manifest.json"
        docx_manifest = json.loads(docx_path.read_text(encoding="utf-8"))
        pdf_manifest = json.loads(pdf_path.read_text(encoding="utf-8"))
        assert self._compute_hash(docx_manifest) != self._compute_hash(pdf_manifest)

    def test_hash_matches_format_field(self):
        docx_path = _TEMPLATES_DIR / "docx" / "manifest.json"
        pdf_path = _TEMPLATES_DIR / "pdf" / "manifest.json"
        docx_manifest = json.loads(docx_path.read_text(encoding="utf-8"))
        pdf_manifest = json.loads(pdf_path.read_text(encoding="utf-8"))
        # Only format field differs
        assert docx_manifest["format"] == "docx"
        assert pdf_manifest["format"] == "pdf"


# ---------------------------------------------------------------------------
# Test 4-9: Manifest config changes affect render output
# ---------------------------------------------------------------------------


class TestManifestConfigAffectsOutput:
    """Test that manifest config changes propagate to render model output."""

    def _build_with_manifest(self, content: dict, manifest: dict) -> ReportRenderModel:
        return build_render_model(
            content=content,
            report_id="test-report",
            revision_number=1,
            content_hash="abc123",
            generated_by="test",
            generated_at="2025-01-01T00:00:00",
            template_code="cold_storage_concept_design",
            template_version="1.0.0",
            template_manifest_json=manifest,
        )

    def test_page_margins_change(self, sample_content):
        """Modify page margins → render_settings reflects new margins."""
        manifest_base = {"page": {"margin_top_pt": 56.69}}
        manifest_modified = {"page": {"margin_top_pt": 100.0}}
        rm_base = self._build_with_manifest(sample_content, manifest_base)
        rm_mod = self._build_with_manifest(sample_content, manifest_modified)
        assert rm_base.manifest.render_settings["page"]["margin_top_pt"] != rm_mod.manifest.render_settings["page"]["margin_top_pt"]
        assert rm_mod.manifest.render_settings["page"]["margin_top_pt"] == 100.0

    def test_header_text_change(self, sample_content):
        """Modify header text → render_settings reflects new header."""
        manifest1 = {"header": {"left": "Header A", "center": "", "right": ""}}
        manifest2 = {"header": {"left": "Header B", "center": "", "right": ""}}
        rm1 = self._build_with_manifest(sample_content, manifest1)
        rm2 = self._build_with_manifest(sample_content, manifest2)
        assert rm1.manifest.render_settings["header"]["left"] == "Header A"
        assert rm2.manifest.render_settings["header"]["left"] == "Header B"

    def test_footer_text_change(self, sample_content):
        """Modify footer text → render_settings reflects new footer."""
        manifest1 = {"footer": {"center": "Footer A"}}
        manifest2 = {"footer": {"center": "Footer B"}}
        rm1 = self._build_with_manifest(sample_content, manifest1)
        rm2 = self._build_with_manifest(sample_content, manifest2)
        assert rm1.manifest.render_settings["footer"]["center"] == "Footer A"
        assert rm2.manifest.render_settings["footer"]["center"] == "Footer B"

    def test_watermark_change(self, sample_content):
        """Modify watermark text/size/color → render_settings reflects changes."""
        manifest1 = {"watermark": {"text": "DRAFT", "font_size_pt": 72, "color": "#CCCCCC"}}
        manifest2 = {"watermark": {"text": "CONFIDENTIAL", "font_size_pt": 48, "color": "#FF0000"}}
        rm1 = self._build_with_manifest(sample_content, manifest1)
        rm2 = self._build_with_manifest(sample_content, manifest2)
        wm1 = rm1.manifest.render_settings["watermark"]
        wm2 = rm2.manifest.render_settings["watermark"]
        assert wm1["text"] == "DRAFT"
        assert wm2["text"] == "CONFIDENTIAL"
        assert wm2["font_size_pt"] == 48
        assert wm2["color"] == "#FF0000"

    def test_table_column_config_change(self, sample_content):
        """Modify table column config → render_settings reflects changes."""
        manifest1 = {
            "tables": {
                "scheme_comparison": {
                    "columns": [{"key": "方案", "header": "方案", "width_ratio": 0.3}],
                }
            }
        }
        manifest2 = {
            "tables": {
                "scheme_comparison": {
                    "columns": [{"key": "方案", "header": "方案名称", "width_ratio": 0.5}],
                }
            }
        }
        rm1 = self._build_with_manifest(sample_content, manifest1)
        rm2 = self._build_with_manifest(sample_content, manifest2)
        cols1 = rm1.manifest.render_settings["tables"]["scheme_comparison"]["columns"]
        cols2 = rm2.manifest.render_settings["tables"]["scheme_comparison"]["columns"]
        assert cols1[0]["width_ratio"] == 0.3
        assert cols2[0]["width_ratio"] == 0.5

    def test_placeholder_text_change(self, sample_content):
        """Modify empty_section_behavior.placeholder_text → render_settings reflects changes."""
        manifest1 = {
            "empty_section_behavior": {
                "behavior": "show_placeholder",
                "placeholder_text": {"not_provided": "该部分数据未提供"},
            }
        }
        manifest2 = {
            "empty_section_behavior": {
                "behavior": "show_placeholder",
                "placeholder_text": {"not_provided": "No data available"},
            }
        }
        rm1 = self._build_with_manifest(sample_content, manifest1)
        rm2 = self._build_with_manifest(sample_content, manifest2)
        pt1 = rm1.manifest.render_settings["empty_section_behavior"]["placeholder_text"]
        pt2 = rm2.manifest.render_settings["empty_section_behavior"]["placeholder_text"]
        assert pt1["not_provided"] == "该部分数据未提供"
        assert pt2["not_provided"] == "No data available"


# ---------------------------------------------------------------------------
# Test 10: seed_default_templates creates both DOCX and PDF templates
# ---------------------------------------------------------------------------


class TestSeedDefaultTemplates:
    """Test that seed_default_templates creates both DOCX and PDF active templates."""

    def test_seed_creates_both_formats(self):
        from cold_storage.modules.reports.infrastructure.template_seed import (
            seed_default_templates,
        )
        from cold_storage.modules.reports.infrastructure.orm import (
            Base,
            ReportTemplateRecord,
        )
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from cold_storage.modules.reports.infrastructure.repository import (
            SQLReportRepository,
        )
        from cold_storage.modules.reports.domain.enums import ExportFormat

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)

        with SessionFactory() as session:
            repo = SQLReportRepository(session)
            seed_default_templates(repo)

            # Check DOCX template exists and is active
            docx_templates = repo.list_templates(
                template_code="cold_storage_concept_design",
                format="docx",
            )
            assert len(docx_templates) >= 1
            docx_active = repo.get_active_template(
                "cold_storage_concept_design", format="docx"
            )
            assert docx_active is not None
            assert docx_active.version == "1.0.0"
            assert docx_active.format == ExportFormat.DOCX

            # Check PDF template exists and is active
            pdf_templates = repo.list_templates(
                template_code="cold_storage_concept_design",
                format="pdf",
            )
            assert len(pdf_templates) >= 1
            pdf_active = repo.get_active_template(
                "cold_storage_concept_design", format="pdf"
            )
            assert pdf_active is not None
            assert pdf_active.version == "1.0.0"
            assert pdf_active.format == ExportFormat.PDF

            # Check content hashes are set and different
            assert docx_active.template_content_hash != ""
            assert pdf_active.template_content_hash != ""
            assert docx_active.template_content_hash != pdf_active.template_content_hash

    def test_seed_is_idempotent(self):
        """Calling seed twice should not create duplicates."""
        from cold_storage.modules.reports.infrastructure.template_seed import (
            seed_default_templates,
        )
        from cold_storage.modules.reports.infrastructure.orm import (
            Base,
        )
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from cold_storage.modules.reports.infrastructure.repository import (
            SQLReportRepository,
        )

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)

        with SessionFactory() as session:
            repo = SQLReportRepository(session)
            seed_default_templates(repo)
            seed_default_templates(repo)

            docx_templates = repo.list_templates(
                template_code="cold_storage_concept_design",
                format="docx",
            )
            pdf_templates = repo.list_templates(
                template_code="cold_storage_concept_design",
                format="pdf",
            )
            assert len(docx_templates) == 1
            assert len(pdf_templates) == 1

    def test_manifest_hash_computed(self):
        """Verify that template_content_hash is computed from manifest."""
        from cold_storage.modules.reports.infrastructure.template_seed import (
            _compute_content_hash,
            _load_manifest,
        )
        from cold_storage.modules.reports.domain.enums import ExportFormat

        docx_manifest = _load_manifest(ExportFormat.DOCX)
        pdf_manifest = _load_manifest(ExportFormat.PDF)

        docx_hash = _compute_content_hash(docx_manifest)
        pdf_hash = _compute_content_hash(pdf_manifest)

        assert len(docx_hash) == 64  # SHA-256 hex
        assert len(pdf_hash) == 64
        assert docx_hash != pdf_hash
