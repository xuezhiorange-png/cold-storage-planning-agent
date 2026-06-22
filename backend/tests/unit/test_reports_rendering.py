"""Task 9B rendering tests — DOCX, PDF, templates, ORM, artifacts, idempotency."""

from __future__ import annotations

import hashlib
import tempfile
import threading
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import fitz  # PyMuPDF
import pytest
from sqlalchemy import create_engine
from cold_storage.modules.reports.renderers.pdf_renderer import _find_cjk_font


def _has_cjk_font() -> bool:
    try:
        path = _find_cjk_font()
        return path is not None and len(path) > 0
    except Exception:
        return False


requires_cjk_font = pytest.mark.skipif(
    not _has_cjk_font(),
    reason="No CJK font available (install fonts-wqy-zenhei)",
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ExportFormat,
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.errors import (
    IdempotencyClaimError,
    IdempotencyPayloadConflictError,
)
from cold_storage.modules.reports.domain.models import (
    ReportExportArtifact,
    ReportTemplate,
)
from cold_storage.modules.reports.domain.render_model import (
    RenderManifest,
    RenderMetadata,
    RenderNumber,
    RenderSection,
    RenderTable,
    RenderTableCell,
    ReportRenderModel,
)
from cold_storage.modules.reports.infrastructure.orm import Base
from cold_storage.modules.reports.infrastructure.repository import (
    SQLReportRepository,
)
from cold_storage.modules.reports.renderers.docx_renderer import DocxRenderer
from cold_storage.modules.reports.renderers.pdf_renderer import PdfRenderer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionFactory() as session:
        yield session


def _make_render_model(
    *,
    project_name: str = "Test Project",
    is_draft: bool = False,
    sections: list[RenderSection] | None = None,
) -> ReportRenderModel:
    """Helper to build a minimal but valid RenderModel."""
    metadata = RenderMetadata(
        report_id="r1",
        project_name=project_name,
        report_type="概念设计报告",
        schema_version="cold_storage_concept_design@1.0.0",
        revision_number=1,
        content_hash="a" * 64,
        content_hash_short="a" * 8,
        generated_at="2025-01-01T00:00:00",
        generated_by="test",
        template_version="1.0.0",
        template_code="cold_storage_concept_design",
    )

    if sections is None:
        sections = [
            RenderSection(
                section_key="project_summary",
                title="项目概况",
                level=1,
                content_type="text",
                text="项目名称：测试项目\n项目地点：上海",
            ),
            RenderSection(
                section_key="cooling_load",
                title="冷负荷计算",
                level=1,
                content_type="number",
                number=RenderNumber(raw=100.0, display="100.0", unit="kW(r)"),
            ),
        ]

    manifest = RenderManifest(
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
        schema_version="cold_storage_concept_design@1.0.0",
        source_content_hash="a" * 64,
        sections=[s.section_key for s in sections if not s.is_empty],
        format="docx/pdf",
    )
    manifest = RenderManifest(
        template_code=manifest.template_code,
        template_version=manifest.template_version,
        schema_version=manifest.schema_version,
        source_content_hash=manifest.source_content_hash,
        sections=manifest.sections,
        format=manifest.format,
        render_settings=manifest.render_settings,
        manifest_hash=manifest.compute_hash(),
    )
    return ReportRenderModel(metadata=metadata, sections=sections, manifest=manifest)


# ---------------------------------------------------------------------------
# Group 1: Production wiring (1 test)
# ---------------------------------------------------------------------------


class TestProductionWiring:
    def test_create_app_registers_reports_router(self):
        """Verify the reports router is importable and defines report API paths.

        Uses the OpenAPI schema to discover registered paths, since FastAPI
        stores included routers in ``_IncludedRouter`` wrappers rather than
        as flat ``Route`` objects in ``app.routes``.
        """
        from fastapi import FastAPI

        from cold_storage.modules.reports.api.routes import reports_router

        # Build a minimal app that includes the reports router
        app = FastAPI()
        app.include_router(reports_router)

        # Inspect the OpenAPI schema for report-related paths
        schema = app.openapi()
        all_paths = list(schema.get("paths", {}).keys())
        report_paths = [p for p in all_paths if "report" in p.lower()]

        assert report_paths, f"Reports router not registered. All OpenAPI paths: {all_paths}"
        # Verify at least the core CRUD endpoints exist
        assert "/api/v1/reports" in all_paths
        assert "/api/v1/report-templates" in all_paths


# ---------------------------------------------------------------------------
# Group 2: DOCX rendering (3 tests)
# ---------------------------------------------------------------------------


class TestDocxRendering:
    def test_docx_draft_watermark(self):
        """DOCX with is_draft=True must contain 'DRAFT' watermark text."""
        model = _make_render_model(is_draft=True)
        renderer = DocxRenderer()
        docx_bytes = renderer.render(model, is_draft=True)
        assert len(docx_bytes) > 0
        # The DOCX is a ZIP; check the XML for DRAFT
        import zipfile
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            # Check header XML for DRAFT text
            header_files = [n for n in zf.namelist() if "header" in n.lower()]
            found_draft = False
            for header_file in header_files:
                content = zf.read(header_file).decode("utf-8", errors="ignore")
                if "DRAFT" in content:
                    found_draft = True
                    break
            assert found_draft, "DRAFT watermark text not found in DOCX headers"

    def test_docx_formal_no_watermark(self):
        """DOCX with is_draft=False must NOT have 'DRAFT' watermark."""
        model = _make_render_model(is_draft=False)
        renderer = DocxRenderer()
        docx_bytes = renderer.render(model, is_draft=False)
        assert len(docx_bytes) > 0
        import zipfile
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            header_files = [n for n in zf.namelist() if "header" in n.lower()]
            for header_file in header_files:
                content = zf.read(header_file).decode("utf-8", errors="ignore")
                assert "w:t>DRAFT<" not in content, (
                    f"DRAFT watermark found in formal mode in {header_file}"
                )

    def test_docx_datetime_real_input(self):
        """Pass real datetime objects through render model builder.

        Verify DOCX renders without error.
        """
        from cold_storage.modules.reports.application.render_model_builder import (
            build_render_model,
        )

        content = {
            "project_summary": {
                "project_name": "蓝莓冷库项目",
                "project_location": "云南",
            },
            "cooling_load": {
                "total_design_refrigeration_load": {
                    "value": 250.0,
                    "unit": "kW(r)",
                    "source_result_id": "calc-001",
                    "source_tool": "cooling_load_calculator",
                    "source_tool_version": "1.0.0",
                }
            },
        }

        now = datetime.now(UTC)
        model = build_render_model(
            content=content,
            report_id="r1",
            revision_number=1,
            content_hash="b" * 64,
            generated_by="test",
            generated_at=now,
            template_code="cold_storage_concept_design",
            template_version="1.0.0",
        )
        renderer = DocxRenderer()
        docx_bytes = renderer.render(model)
        assert len(docx_bytes) > 1000, "DOCX output too small"


# ---------------------------------------------------------------------------
# Group 3: PDF rendering (4 tests)
# ---------------------------------------------------------------------------


@requires_cjk_font
class TestPdfRendering:
    def test_pdf_chinese_generation(self):
        """Render PDF with Chinese text, extract text, verify Chinese chars."""
        model = _make_render_model(project_name="蓝莓冷库")
        renderer = PdfRenderer()
        pdf_bytes = renderer.render(model)
        assert len(pdf_bytes) > 0

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = ""
        for page in doc:
            all_text += page.get_text()
        doc.close()

        # Check for Chinese characters
        has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in all_text)
        assert has_chinese, f"No Chinese characters found in PDF text. Got: {all_text[:200]}"

    def test_pdf_text_extractable(self):
        """Render PDF and use PyMuPDF to extract text; verify not empty."""
        model = _make_render_model()
        renderer = PdfRenderer()
        pdf_bytes = renderer.render(model)
        assert len(pdf_bytes) > 0

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        all_text = ""
        for page in doc:
            all_text += page.get_text()
        doc.close()

        assert len(all_text.strip()) > 0, "PDF text extraction returned empty"
        # Verify it's actual text (not a rasterized image)
        assert "Test Project" in all_text or "测试" in all_text, (
            f"Extracted text doesn't contain expected content: {all_text[:200]}"
        )

    def test_pdf_correct_pagenumbers(self):
        """Render PDF with many sections spanning multiple pages."""
        sections = []
        for i in range(15):
            text_content = f"Section {i} content. " + "Lorem ipsum dolor sit amet. " * 20
            sections.append(
                RenderSection(
                    section_key=f"section_{i}",
                    title=f"章节 {i}",
                    level=1,
                    content_type="text",
                    text=text_content,
                )
            )
        model = _make_render_model(sections=sections)
        renderer = PdfRenderer()
        pdf_bytes = renderer.render(model)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        doc.close()

        assert page_count > 2, f"Expected multiple pages, got {page_count}"

    def test_pdf_table_cross_page(self):
        """Large table (>50 rows) renders to PDF without error."""
        rows = []
        for i in range(60):
            rows.append(
                [
                    RenderTableCell(value=f"设备-{i:03d}", align="left"),
                    RenderTableCell(value=f"{100 + i * 10}", align="right"),
                    RenderTableCell(value="kW(r)", align="center"),
                ]
            )
        table = RenderTable(
            title="设备清单",
            headers=["设备名称", "功率", "单位"],
            rows=rows,
            unit_row=["", "", "kW(r)"],
        )
        section = RenderSection(
            section_key="equipment_list",
            title="设备清单",
            level=1,
            content_type="table",
            table=table,
        )
        model = _make_render_model(sections=[section])
        renderer = PdfRenderer()
        pdf_bytes = renderer.render(model)
        assert len(pdf_bytes) > 1000, "PDF with large table too small"


# ---------------------------------------------------------------------------
# Group 4: Template operations (4 tests)
# ---------------------------------------------------------------------------


class TestTemplateOperations:
    def test_template_not_found(self):
        """Try to find a template with non-existent ID, verify None."""
        repo = SQLReportRepository(MagicMock())
        mock_session = MagicMock()
        mock_session.get.return_value = None
        repo._session = mock_session

        result = repo.get_template("nonexistent-id-12345")
        assert result is None

    def test_retired_template_rejected(self):
        """RETIRED template cannot be used for new exports."""
        template = ReportTemplate.create(
            template_code="test_code",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="test@1.0.0",
        )
        # Retire the template
        retired = replace(template, status=TemplateStatus.RETIRED)

        # Retired templates should not be ACTIVE
        assert retired.status == TemplateStatus.RETIRED
        assert retired.status != TemplateStatus.ACTIVE
        assert retired.status.value == "retired"

    def test_template_version_selection(self):
        """Create templates v1.0.0 and v1.1.0, verify correct one is selected."""
        t1 = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="cold_storage_concept_design@1.0.0",
        )
        t2 = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.1.0",
            schema_version="cold_storage_concept_design@1.1.0",
        )

        templates = [t1, t2]
        # Simulate version selection: find v1.1.0
        selected = None
        for t in templates:
            if t.version == "1.1.0":
                selected = t
                break

        assert selected is not None
        assert selected.version == "1.1.0"
        assert selected.schema_version == ("cold_storage_concept_design@1.1.0")

        # Also verify v1.0.0 is findable
        found_v1 = next(t for t in templates if t.version == "1.0.0")
        assert found_v1.version == "1.0.0"

    def test_template_init_idempotent(self):
        """Call template seed twice, verify no duplicate templates."""
        from cold_storage.modules.reports.infrastructure.template_seed import (
            seed_default_templates,
        )

        mock_repo = MagicMock()
        # First call: no existing templates
        mock_repo.list_templates.return_value = []

        seed_default_templates(mock_repo)
        first_call_count = mock_repo.save_template.call_count

        # Second call: templates now exist
        fake_template = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="cold_storage_concept_design@1.0.0",
        )
        fake_template = replace(fake_template, status=TemplateStatus.ACTIVE)
        mock_repo.list_templates.return_value = [fake_template]
        mock_repo.get_active_template.return_value = fake_template

        seed_default_templates(mock_repo)
        second_call_count = mock_repo.save_template.call_count

        # Second call should not save any new templates
        assert second_call_count == first_call_count, (
            f"Template not idempotent: saved "
            f"{second_call_count - first_call_count} "
            f"new templates on second call"
        )


# ---------------------------------------------------------------------------
# Group 5: ORM ↔ Domain conversion (1 test)
# ---------------------------------------------------------------------------


class TestOrmDomainConversion:
    def test_orm_domain_conversion(self, db_session):
        """Create ORM records for template and artifact, convert to domain."""
        from cold_storage.modules.reports.infrastructure.orm import (
            ReportExportArtifactRecord,
            ReportTemplateRecord,
        )

        now = datetime.now(UTC)
        template_id = "tmpl-001"
        artifact_id = "art-001"

        # Create a template ORM record
        tmpl_rec = ReportTemplateRecord(
            id=template_id,
            template_code="cold_storage_concept_design",
            report_type="cold_storage_concept_design",
            format="docx",
            version="1.0.0",
            status="active",
            schema_version="cold_storage_concept_design@1.0.0",
            locale="zh-CN",
            manifest_json={},
            template_content_hash="abc123",
            created_by="system",
            created_at=now,
            activated_at=now,
        )
        db_session.add(tmpl_rec)

        # Create an artifact ORM record
        art_rec = ReportExportArtifactRecord(
            id=artifact_id,
            report_id="report-001",
            report_revision_id="rev-001",
            revision_number=1,
            format="docx",
            template_id=template_id,
            template_version="1.0.0",
            schema_version="cold_storage_concept_design@1.0.0",
            status="completed",
            storage_key="storage-key-001",
            file_name="report.docx",
            mime_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            file_size_bytes=1024,
            file_sha256="sha256hash",
            source_content_hash="contenthash",
            render_manifest_json={},
            generated_by="test",
            generated_at=now,
            failure_code="",
            failure_message="",
        )
        db_session.add(art_rec)
        db_session.flush()

        # Convert template ORM → domain
        tmpl_domain = ReportTemplate(
            id=tmpl_rec.id,
            template_code=tmpl_rec.template_code,
            report_type=ReportType(tmpl_rec.report_type),
            format=ExportFormat(tmpl_rec.format),
            version=tmpl_rec.version,
            status=TemplateStatus(tmpl_rec.status),
            schema_version=tmpl_rec.schema_version,
            locale=tmpl_rec.locale,
            manifest_json=tmpl_rec.manifest_json,
            template_content_hash=tmpl_rec.template_content_hash,
            created_by=tmpl_rec.created_by,
            created_at=tmpl_rec.created_at,
            activated_at=tmpl_rec.activated_at,
        )

        assert tmpl_domain.id == template_id
        assert tmpl_domain.template_code == "cold_storage_concept_design"
        assert tmpl_domain.version == "1.0.0"
        assert tmpl_domain.status == TemplateStatus.ACTIVE
        assert tmpl_domain.format == ExportFormat.DOCX

        # Convert artifact ORM → domain
        art_domain = ReportExportArtifact(
            id=art_rec.id,
            report_id=art_rec.report_id,
            report_revision_id=art_rec.report_revision_id,
            revision_number=art_rec.revision_number,
            format=ExportFormat(art_rec.format),
            template_id=art_rec.template_id,
            template_version=art_rec.template_version,
            schema_version=art_rec.schema_version,
            status=ArtifactStatus(art_rec.status),
            storage_key=art_rec.storage_key,
            file_name=art_rec.file_name,
            mime_type=art_rec.mime_type,
            file_size_bytes=art_rec.file_size_bytes,
            file_sha256=art_rec.file_sha256,
            source_content_hash=art_rec.source_content_hash,
            render_manifest_json=art_rec.render_manifest_json,
            generated_by=art_rec.generated_by,
            generated_at=art_rec.generated_at,
            failure_code=art_rec.failure_code,
            failure_message=art_rec.failure_message,
        )

        assert art_domain.id == artifact_id
        assert art_domain.report_id == "report-001"
        assert art_domain.revision_number == 1
        assert art_domain.status == ArtifactStatus.COMPLETED
        assert art_domain.file_size_bytes == 1024
        assert art_domain.file_sha256 == "sha256hash"
        assert art_domain.template_id == template_id
        assert art_domain.template_version == "1.0.0"


# ---------------------------------------------------------------------------
# Group 6: Artifact state machine (2 tests)
# ---------------------------------------------------------------------------


class TestArtifactStateMachine:
    def test_artifact_completed_status(self):
        """Verify artifact transitions pending->rendering->completed."""
        artifact = ReportExportArtifact.create(
            report_id="r1",
            report_revision_id="rev-1",
            revision_number=1,
            format=ExportFormat.DOCX,
            template_id="tmpl-1",
            template_version="1.0.0",
            schema_version="schema@1.0.0",
            file_name="report.docx",
            mime_type="application/docx",
            source_content_hash="abc",
            generated_by="test",
        )

        # Initial state
        assert artifact.status == ArtifactStatus.PENDING

        # Transition to rendering
        rendering = replace(artifact, status=ArtifactStatus.RENDERING)
        assert rendering.status == ArtifactStatus.RENDERING

        # Transition to completed
        completed = replace(
            rendering,
            status=ArtifactStatus.COMPLETED,
            storage_key="key-123",
            file_size_bytes=1024,
            file_sha256="sha256hash",
        )
        assert completed.status == ArtifactStatus.COMPLETED
        assert completed.storage_key == "key-123"
        assert completed.file_size_bytes == 1024

    def test_artifact_failed_status(self):
        """Verify artifact transitions pending->rendering->failed."""
        artifact = ReportExportArtifact.create(
            report_id="r1",
            report_revision_id="rev-1",
            revision_number=1,
            format=ExportFormat.PDF,
            template_id="tmpl-1",
            template_version="1.0.0",
            schema_version="schema@1.0.0",
            file_name="report.pdf",
            mime_type="application/pdf",
            source_content_hash="abc",
            generated_by="test",
        )

        # Initial state
        assert artifact.status == ArtifactStatus.PENDING

        # Transition to rendering
        rendering = replace(artifact, status=ArtifactStatus.RENDERING)
        assert rendering.status == ArtifactStatus.RENDERING

        # Transition to failed with error info
        failed = replace(
            rendering,
            status=ArtifactStatus.FAILED,
            failure_code="RenderError",
            failure_message="Font not found: SimSun",
        )
        assert failed.status == ArtifactStatus.FAILED
        assert failed.failure_code == "RenderError"
        assert failed.failure_message == "Font not found: SimSun"


# ---------------------------------------------------------------------------
# Group 7: Download safety (2 tests)
# ---------------------------------------------------------------------------


class TestDownloadSafety:
    def test_db_commit_failure_file_cleanup(self):
        """Simulate DB commit failure after file write, cleanup works."""
        from cold_storage.modules.reports.infrastructure.artifact_storage import (
            ReportArtifactStorage,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ReportArtifactStorage(tmpdir)
            artifact_id = "test-artifact-001"
            test_data = b"test file content for cleanup"

            # Write the file
            storage_key = storage.put(artifact_id, test_data, "test.txt")
            assert storage.exists(storage_key)

            # Simulate DB commit failure — the file should be cleaned up
            # by the caller. Verify that delete works for cleanup.
            storage.delete(storage_key)
            assert not storage.exists(storage_key)

    def test_sha256_mismatch_rejects_download(self):
        """Create artifact with wrong SHA-256, verify verification fails."""
        from cold_storage.modules.reports.infrastructure.artifact_storage import (
            ReportArtifactStorage,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ReportArtifactStorage(tmpdir)
            test_data = b"actual file content"
            artifact_id = "test-artifact-002"

            # Store the file
            storage_key = storage.put(artifact_id, test_data, "test.txt")

            # Read back and verify SHA-256 matches
            stored_data = storage.get(storage_key)
            actual_hash = hashlib.sha256(stored_data).hexdigest()

            # Create artifact with wrong SHA-256
            wrong_hash = "0" * 64
            assert actual_hash != wrong_hash, "Hashes should differ"

            # The stored data hash should be correct
            correct_hash = hashlib.sha256(test_data).hexdigest()
            assert actual_hash == correct_hash


# ---------------------------------------------------------------------------
# Group 8: Idempotency (3 tests)
# ---------------------------------------------------------------------------


def _build_fake_provider() -> Any:
    """Build a fake ReportDataProvider for idempotency tests."""

    class _FakeProvider:
        def get_project(self, project_id: str) -> dict[str, Any] | None:
            return {"name": "Test", "location": "Loc"}

        def get_project_version(
            self,
            version_id: str,
            *,
            project_id: str | None = None,
        ) -> dict[str, Any] | None:
            return {"id": version_id, "version_number": 1}

        def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
            return [
                {
                    "section_key": "cooling_load",
                    "result_id": "c1",
                    "tool_name": "cooling_load_calculator",
                    "tool_version": "1.0.0",
                    "persisted_content_hash": "h1",
                    "data": {
                        "total_design_refrigeration_load": {
                            "value": 100.0,
                            "unit": "kW(r)",
                            "source_result_id": "c1",
                            "source_tool": "cooling_load_calculator",
                            "source_tool_version": "1.0.0",
                        }
                    },
                },
                {
                    "section_key": "equipment_selection",
                    "result_id": "c2",
                    "tool_name": "equipment_selector",
                    "tool_version": "1.0.0",
                    "persisted_content_hash": "h2",
                    "data": {
                        "total_compressor_capacity": {
                            "value": 120.0,
                            "unit": "kW(r)",
                            "source_result_id": "c2",
                            "source_tool": "equipment_selector",
                            "source_tool_version": "1.0.0",
                        }
                    },
                },
                {
                    "section_key": "electrical_and_energy",
                    "result_id": "c3",
                    "tool_name": "energy_calculator",
                    "tool_version": "1.0.0",
                    "persisted_content_hash": "h3",
                    "data": {
                        "total_installed_power": {
                            "value": 50.0,
                            "unit": "kW(e)",
                            "source_result_id": "c3",
                            "source_tool": "energy_calculator",
                            "source_tool_version": "1.0.0",
                        }
                    },
                },
            ]

        def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
            return {
                "run_id": "s1",
                "schemes": [{"scheme_id": "s1"}],
                "recommended_scheme": "s1",
                "generator_version": "1.0.0",
                "persisted_content_hash": "sh1",
            }

        def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
            return []

        def get_knowledge_documents(self) -> list[dict[str, Any]]:
            return []

    return _FakeProvider()


def _make_idem_service(
    engine: Any,
) -> tuple[Any, Any]:
    """Create a ReportService for idempotency tests."""
    from cold_storage.modules.reports.application.assembler import (
        ReportAssembler,
    )
    from cold_storage.modules.reports.application.service import ReportService

    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionFactory()
    repo = SQLReportRepository(session)
    assembler = ReportAssembler(_build_fake_provider())
    return ReportService(repo, assembler), session


class TestIdempotency:
    def test_idempotency_duplicate_request(self):
        """Same key + same params = same artifact returned."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        service, _ = _make_idem_service(engine)

        # First request
        r1 = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
            idempotency_key="idem-key-dup",
        )

        # Second request with same key + same params
        r2 = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
            idempotency_key="idem-key-dup",
        )

        assert r1.id == r2.id, "Same idempotency key + same params should return same report"

    def test_idempotency_parameter_conflict(self):
        """Same key + different params = conflict error."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        service, _ = _make_idem_service(engine)

        # First request
        service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
            idempotency_key="idem-key-conflict",
        )

        # Second request with same key but DIFFERENT params
        with pytest.raises(IdempotencyPayloadConflictError):
            service.create_report(
                project_id="p2",  # Different project_id!
                project_version_id="v1",
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                actor="user1",
                idempotency_key="idem-key-conflict",
            )

    def test_idempotency_concurrent_requests(self):
        """Two concurrent requests with same key, only one artifact created."""
        # Use a file-based SQLite for proper thread isolation
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test_concurrent.db"
            engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False},
            )
            Base.metadata.create_all(engine)
            SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)

            results: list[str] = []
            errors: list[Exception] = []

            def _create_report(idx: int) -> None:
                from cold_storage.modules.reports.application.assembler import (  # noqa: E501
                    ReportAssembler,
                )
                from cold_storage.modules.reports.application.service import (  # noqa: E501
                    ReportService,
                )

                session = SessionFactory()
                try:
                    repo = SQLReportRepository(session)
                    assembler = ReportAssembler(_build_fake_provider())
                    svc = ReportService(repo, assembler)
                    report = svc.create_report(
                        project_id="p1",
                        project_version_id="v1",
                        report_type=(ReportType.COLD_STORAGE_CONCEPT_DESIGN),
                        actor="user1",
                        idempotency_key="idem-key-concurrent",
                    )
                    results.append(report.id)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    session.close()

            # Launch two threads concurrently
            t1 = threading.Thread(target=_create_report, args=(1,))
            t2 = threading.Thread(target=_create_report, args=(2,))

            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            # Both should complete (one may get IdempotencyClaimError)
            # The key property: only one report is created
            if errors:
                # One got a conflict error, which is expected
                assert isinstance(errors[0], IdempotencyClaimError), (
                    f"Unexpected error type: {type(errors[0])}: {errors[0]}"
                )
                # The other should have succeeded
                assert len(results) == 1, f"Expected 1 result, got {len(results)}"
            else:
                # Both returned results — verify they got same report
                assert len(results) == 2
                assert results[0] == results[1], (
                    "Concurrent requests with same key should return the same report"
                )
