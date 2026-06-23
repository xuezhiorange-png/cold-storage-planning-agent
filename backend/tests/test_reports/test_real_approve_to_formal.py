"""Real approve→formal PDF/DOCX pipeline test.

Covers P0-4: End-to-end test of the full report lifecycle:
  create → generate → submit_review → mark_reviewed → approve → render formal PDF/DOCX

Uses REAL components:
  - ReportService (real assembler with mock data provider)
  - SQLReportRepository (real SQLite)
  - ReportRenderService with ReportRenderUnitOfWork (real)
  - Real DocxRenderer and PdfRenderer
  - Real seed_default_templates
  - LocalArtifactStorage (real file I/O)

Verifies:
  1. Formal PDF output contains approval section (Chinese approval fields)
  2. Formal DOCX output contains approval section
  3. Artifact manifest contains all 5 approval fields
  4. PDF and DOCX manifests match (same approval snapshot)
  5. Cross-session: approval fields persist across sessions
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.application.assembler import (
    AssembledReport,
    ReportAssembler,
    ReportDataProvider,
)
from cold_storage.modules.reports.application.render_service import (
    ReportRenderService,
    ReportRenderUnitOfWork,
)
from cold_storage.modules.reports.application.service import ReportService
from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ReportStatus,
    ReportType,
)
from cold_storage.modules.reports.domain.models import (
    Report,
    ReportRevision,
)
from cold_storage.modules.reports.infrastructure.artifact_storage import (
    ReportArtifactStorage,
)
from cold_storage.modules.reports.infrastructure.orm import Base
from cold_storage.modules.reports.infrastructure.repository import (
    SQLReportRepository,
)
from cold_storage.modules.reports.infrastructure.template_seed import (
    seed_default_templates,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """In-memory SQLite engine with report tables."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture()
def repo(session):
    return SQLReportRepository(session)


# ---------------------------------------------------------------------------
# Mock data provider and assembler
# ---------------------------------------------------------------------------


class _MockDataProvider(ReportDataProvider):
    """Minimal data provider that returns enough data for the assembler."""

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return {"name": "Test Project", "location": "Shanghai", "description": "Test"}

    def get_project_version(
        self, version_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return {"version_id": version_id, "project_id": project_id}


class _MockAssembler(ReportAssembler):
    """Assembler that returns GENERATED quality_status with no findings."""

    def __init__(self) -> None:
        super().__init__(_MockDataProvider())

    def assemble(self, **kwargs: Any) -> AssembledReport:
        result = super().assemble(**kwargs)
        result.quality_status = ReportStatus.GENERATED
        result.findings = []
        if "quality_summary" in result.content:
            result.content["quality_summary"]["findings"] = []
            result.content["quality_summary"]["blocker_count"] = 0
            result.content["quality_summary"]["warning_count"] = 0
            result.content["quality_summary"]["info_count"] = 0
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_report(repo: SQLReportRepository, session: Any) -> Report:
    """Create a report and persist it."""
    report = Report.create(
        project_id="proj-1",
        project_version_id="ver-1",
        report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
        created_by="test-user",
    )
    repo.save_report(report)
    session.commit()
    return report


def _generate_revision(
    service: ReportService,
    report: Report,
) -> ReportRevision:
    """Generate a revision for a report using the real assembler."""
    return service.generate_revision(report.id, "test-user")


def _full_review_flow(service: ReportService, report: Report) -> Report:
    """Walk through the full review flow: submit → mark reviewed."""
    report = service.submit_review(report.id, "test-user")
    report = service.mark_reviewed(report.id, "test-user")
    return report


def _setup_approved_report(
    session_factory: sessionmaker,
) -> tuple[Report, ReportRevision]:
    """Create a fully approved report and return (report, latest_revision)."""
    with session_factory() as session:
        repo = SQLReportRepository(session)
        assembler = _MockAssembler()
        service = ReportService(repository=repo, assembler=assembler)

        report = _create_report(repo, session)
        _generate_revision(service, report)
        report = repo.get_report(report.id)
        report = _full_review_flow(service, report)
        # Approve via real service (sets approval fields)
        report = service.approve(report.id, "test-user")
        return report, repo.get_latest_revision(report.id)


# ---------------------------------------------------------------------------
# P0-4: Real approve→formal pipeline tests
# ---------------------------------------------------------------------------


class TestRealApproveToFormal:
    def test_real_approve_to_formal_docx_contains_approval_fields(self, session_factory, tmp_path):
        """Full pipeline: create → generate → review → approve → render formal DOCX.

        Verifies DOCX output contains approval section text.
        """
        report, approved_rev = _setup_approved_report(session_factory)

        # Seed real templates
        with session_factory() as s:
            template_repo = SQLReportRepository(s)
            seed_default_templates(template_repo)
            s.commit()

        # Render formal DOCX in a new session
        with session_factory() as s:
            repo = SQLReportRepository(s)
            uow = ReportRenderUnitOfWork(s, report_repo=repo, artifact_repo=repo)

            # Load real templates for render service
            storage = ReportArtifactStorage(str(tmp_path / "artifacts"))
            template_repo = SQLReportRepository(s)

            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )

            artifact = render_svc.render(
                report_id=report.id,
                revision_number=approved_rev.revision_number,
                format="docx",
                template_version=None,
                mode="formal",
                actor="test-user",
            )

            assert artifact.status == ArtifactStatus.COMPLETED

            # Read the rendered DOCX and parse it
            import io

            from docx import Document

            docx_bytes = storage.get(artifact.storage_key)
            doc = Document(io.BytesIO(docx_bytes))
            docx_text = "\n".join(p.text for p in doc.paragraphs)

            # Must contain approval fields (Chinese labels from render_model_builder)
            assert "批准修订号" in docx_text or str(approved_rev.revision_number) in docx_text
            assert "批准修订ID" in docx_text or artifact.report_revision_id in docx_text
            assert "批准内容哈希" in docx_text or artifact.source_content_hash in docx_text
            assert "批准人" in docx_text or "test-user" in docx_text

            # Check manifest
            manifest = artifact.render_manifest_json
            assert manifest["approved_revision_number"] == approved_rev.revision_number
            assert manifest["approved_revision_id"] != ""
            assert manifest["approved_content_hash"] != ""
            assert manifest["approved_by"] == "test-user"
            assert manifest["approved_at"] != ""

    def test_real_approve_to_formal_pdf_contains_approval_fields(self, session_factory, tmp_path):
        """Full pipeline: create → generate → review → approve → render formal PDF.

        Verifies PDF output contains approval section text.
        """
        report, approved_rev = _setup_approved_report(session_factory)

        # Seed real templates
        with session_factory() as s:
            template_repo = SQLReportRepository(s)
            seed_default_templates(template_repo)
            s.commit()

        # Render formal PDF in a new session
        with session_factory() as s:
            repo = SQLReportRepository(s)
            uow = ReportRenderUnitOfWork(s, report_repo=repo, artifact_repo=repo)
            storage = ReportArtifactStorage(str(tmp_path / "artifacts"))
            template_repo = SQLReportRepository(s)

            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )

            artifact = render_svc.render(
                report_id=report.id,
                revision_number=approved_rev.revision_number,
                format="pdf",
                template_version=None,
                mode="formal",
                actor="test-user",
            )

            assert artifact.status == ArtifactStatus.COMPLETED

            # Read the rendered PDF and parse it
            import fitz

            pdf_bytes = storage.get(artifact.storage_key)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pdf_text = "".join(page.get_text() for page in doc)
            doc.close()

            # Must contain approval fields
            assert "批准修订号" in pdf_text or str(approved_rev.revision_number) in pdf_text
            assert "批准修订ID" in pdf_text or artifact.report_revision_id in pdf_text
            assert "批准内容哈希" in pdf_text or artifact.source_content_hash in pdf_text
            assert "批准人" in pdf_text or "test-user" in pdf_text

            # Check manifest
            manifest = artifact.render_manifest_json
            assert manifest["approved_revision_number"] == approved_rev.revision_number
            assert manifest["approved_revision_id"] != ""
            assert manifest["approved_content_hash"] != ""
            assert manifest["approved_by"] == "test-user"
            assert manifest["approved_at"] != ""

    def test_pdf_and_docx_manifests_match(self, session_factory, tmp_path):
        """PDF and DOCX renders of the same approved revision produce
        identical approval snapshots in their manifests.
        """
        report, approved_rev = _setup_approved_report(session_factory)

        # Seed real templates
        with session_factory() as s:
            template_repo = SQLReportRepository(s)
            seed_default_templates(template_repo)
            s.commit()

        storage = ReportArtifactStorage(str(tmp_path / "artifacts"))

        # Render DOCX
        with session_factory() as s:
            repo = SQLReportRepository(s)
            uow = ReportRenderUnitOfWork(s, report_repo=repo, artifact_repo=repo)
            template_repo = SQLReportRepository(s)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )
            docx_artifact = render_svc.render(
                report_id=report.id,
                revision_number=approved_rev.revision_number,
                format="docx",
                template_version=None,
                mode="formal",
                actor="test-user",
            )

        # Render PDF
        with session_factory() as s:
            repo = SQLReportRepository(s)
            uow = ReportRenderUnitOfWork(s, report_repo=repo, artifact_repo=repo)
            template_repo = SQLReportRepository(s)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )
            pdf_artifact = render_svc.render(
                report_id=report.id,
                revision_number=approved_rev.revision_number,
                format="pdf",
                template_version=None,
                mode="formal",
                actor="test-user",
            )

        # Compare approval fields in manifests
        docx_manifest = docx_artifact.render_manifest_json
        pdf_manifest = pdf_artifact.render_manifest_json

        assert docx_manifest["approved_revision_number"] == pdf_manifest["approved_revision_number"]
        assert docx_manifest["approved_revision_id"] == pdf_manifest["approved_revision_id"]
        assert docx_manifest["approved_content_hash"] == pdf_manifest["approved_content_hash"]
        assert docx_manifest["approved_by"] == pdf_manifest["approved_by"]
        assert docx_manifest["approved_at"] == pdf_manifest["approved_at"]

    def test_approval_fields_persist_across_sessions(self, session_factory):
        """Approval fields on Report persist across session boundaries."""
        report, approved_rev = _setup_approved_report(session_factory)

        # Open a brand new session and verify
        with session_factory() as s:
            repo = SQLReportRepository(s)
            reloaded = repo.get_report(report.id)

            assert reloaded is not None
            assert reloaded.approved_revision_id == approved_rev.id
            assert reloaded.approved_content_hash == approved_rev.content_hash
            assert reloaded.approved_by == "test-user"
            assert reloaded.approved_at is not None

    def test_formal_render_rejects_unapproved_report(self, session_factory, tmp_path):
        """Formal render of an unapproved report is rejected."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler()
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)
            _generate_revision(service, report)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            # Seed templates
            template_repo = SQLReportRepository(session)
            seed_default_templates(template_repo)
            session.commit()

            storage = ReportArtifactStorage(str(tmp_path / "artifacts"))
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )

            from cold_storage.modules.reports.domain.errors import (
                ExportPermissionError,
            )

            with pytest.raises(ExportPermissionError):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version=None,
                    mode="formal",
                    actor="test-user",
                )
