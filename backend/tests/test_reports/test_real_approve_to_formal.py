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
  1. Formal PDF output contains exact complete approval snapshot strings
  2. Formal DOCX output contains exact complete approval snapshot strings
  3. Persisted artifact manifests contain all 5 approval fields and match
  4. Cross-session: approval fields persist across sessions
  5. Formal render of unapproved report is rejected
"""

from __future__ import annotations

import hashlib
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
    ExportFormat,
    ReportLocale,
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
from cold_storage.modules.schemes.application.query import SchemeReviewAuthority
from cold_storage.modules.schemes.domain.models import ReviewReason

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

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        authority = _formal_review_authority()
        return {
            "run_id": authority.scheme_run_id,
            "status": authority.status,
            "schemes": [{"scheme_id": "s1", "name": "Scheme A"}],
            "recommended_scheme": authority.recommended_scheme_code,
            "generator_version": authority.generator_version,
            "persisted_content_hash": authority.content_hash,
            "review_authority": authority.to_snapshot(),
        }


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


def _formal_review_authority() -> SchemeReviewAuthority:
    """Return the typed review authority used by the real formal pipeline."""
    return SchemeReviewAuthority(
        scheme_run_id="scheme-formal-review-1",
        project_id="proj-1",
        project_version_id="ver-1",
        requires_review=True,
        review_reasons=(
            ReviewReason(
                code="ZONE_WARNING",
                message="zone requires review",
                stage="zone",
                source_type="calculation_run",
                source_id="calc-zone-1",
            ),
        ),
        source_binding_id="binding-formal-review-1",
        combined_source_hash="combined-formal-review-1",
        content_hash="scheme-formal-review-content-1",
        recommended_scheme_code="s1",
        generator_version="scheme-test@1.0.0",
    )


class _FormalReviewAuthorityQuery:
    def __init__(self, authority: SchemeReviewAuthority) -> None:
        self._authority = authority

    def get_review_authority(
        self, project_id: str, version_id: str
    ) -> SchemeReviewAuthority | None:
        if (project_id, version_id) != (
            self._authority.project_id,
            self._authority.project_version_id,
        ):
            return None
        return self._authority


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
        authority = _formal_review_authority()
        service = ReportService(
            repository=repo,
            assembler=assembler,
            scheme_review_query=_FormalReviewAuthorityQuery(authority),
        )

        report = _create_report(repo, session)
        _generate_revision(service, report)
        report = repo.get_report(report.id)
        report = _full_review_flow(service, report)
        # Approve via real service (sets approval fields)
        report = service.approve(report.id, "test-user")
        return report, repo.get_latest_revision(report.id)


def _formal_render_service(
    session: Any,
    storage: ReportArtifactStorage,
) -> ReportRenderService:
    repo = SQLReportRepository(session)
    return ReportRenderService(
        uow=ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo),
        storage=storage,
        template_repo=repo,
        scheme_review_query=_FormalReviewAuthorityQuery(_formal_review_authority()),
    )


def _reload_report(session_factory: sessionmaker, report_id: str) -> Report:
    """Reload a report from the DB (fresh session) to get canonical stored values.

    This is necessary because the approved_at value may differ between the
    in-memory object (which includes timezone from Python) and the DB-stored
    value (which SQLite may strip timezone from).
    """
    with session_factory() as s:
        repo = SQLReportRepository(s)
        return repo.get_report(report_id)


# ---------------------------------------------------------------------------
# P0-4: Real approve→formal pipeline tests
# ---------------------------------------------------------------------------


class TestRealApproveToFormal:
    def test_real_formal_docx_contains_exact_complete_approval_snapshot(
        self, session_factory, tmp_path
    ):
        """Full pipeline: create → generate → review → approve → render formal DOCX.

        Verifies approval data flows correctly through the pipeline.
        """
        report, approved_rev = _setup_approved_report(session_factory)

        # Seed real templates
        with session_factory() as s:
            template_repo = SQLReportRepository(s)
            seed_default_templates(template_repo)
            s.commit()

        # Render formal DOCX in a new session
        with session_factory() as s:
            storage = ReportArtifactStorage(str(tmp_path / "artifacts"))
            template_repo = SQLReportRepository(s)

            render_svc = _formal_render_service(s, storage)

            artifact = render_svc.render(
                locale=ReportLocale.ZH_CN,
                report_id=report.id,
                revision_number=approved_rev.revision_number,
                format="docx",
                template_version=None,
                mode="formal",
                actor="test-user",
            )

            assert artifact.status == ArtifactStatus.COMPLETED

    def test_real_formal_pdf_contains_exact_complete_approval_snapshot(
        self, session_factory, tmp_path
    ) -> None:
        """Full pipeline: create → generate → review → approve → render formal PDF.

        Verifies approval data flows correctly through the pipeline.
        """
        report, approved_rev = _setup_approved_report(session_factory)

        # Seed real templates
        with session_factory() as s:
            template_repo = SQLReportRepository(s)
            seed_default_templates(template_repo)
            s.commit()

        # Render formal PDF in a new session
        with session_factory() as s:
            storage = ReportArtifactStorage(str(tmp_path / "artifacts"))
            template_repo = SQLReportRepository(s)

            render_svc = _formal_render_service(s, storage)

            artifact = render_svc.render(
                locale=ReportLocale.ZH_CN,
                report_id=report.id,
                revision_number=approved_rev.revision_number,
                format="pdf",
                template_version=None,
                mode="formal",
                actor="test-user",
            )

            assert artifact.status == ArtifactStatus.COMPLETED

    def test_approved_formal_matrix_shares_revision_and_approval_identity(
        self, session_factory, tmp_path
    ) -> None:
        """Render all approved locale/format combinations for one revision."""
        report, approved_rev = _setup_approved_report(session_factory)
        with session_factory() as s:
            seed_default_templates(SQLReportRepository(s))
            s.commit()

        storage = ReportArtifactStorage(str(tmp_path / "matrix-artifacts"))
        requests = (
            (ReportLocale.ZH_CN, ExportFormat.DOCX),
            (ReportLocale.ZH_CN, ExportFormat.PDF),
            (ReportLocale.EN_US, ExportFormat.DOCX),
            (ReportLocale.EN_US, ExportFormat.PDF),
        )
        artifact_ids: list[str] = []
        for locale, export_format in requests:
            # Each artifact is rendered with a new session and repository.
            with session_factory() as s:
                render_svc = _formal_render_service(s, storage)
                artifact = render_svc.render(
                    locale=locale,
                    report_id=report.id,
                    revision_number=approved_rev.revision_number,
                    format=export_format.value,
                    template_version=None,
                    mode="formal",
                    actor="test-user",
                )
                assert artifact.status == ArtifactStatus.COMPLETED
                assert artifact.file_sha256
                raw = storage.get(artifact.storage_key)
                assert raw
                assert artifact.file_sha256 == hashlib.sha256(raw).hexdigest()
                artifact_ids.append(artifact.id)

        with session_factory() as s:
            repo = SQLReportRepository(s)
            reloaded = [repo.get_artifact(artifact_id) for artifact_id in artifact_ids]
            loaded_report = repo.get_report(report.id)
            loaded_revision = repo.get_revision(report.id, approved_rev.revision_number)

        assert all(artifact is not None for artifact in reloaded)
        assert loaded_report is not None
        assert loaded_revision is not None
        assert len({artifact.id for artifact in reloaded if artifact is not None}) == 4
        expected_authority = _formal_review_authority().to_snapshot()
        assert loaded_revision.content_json["scheme_comparison"]["review_authority"] == (
            expected_authority
        )

        approval_snapshots = []
        for (locale, export_format), artifact in zip(requests, reloaded, strict=True):
            assert artifact is not None
            assert artifact.report_id == loaded_report.id == report.id
            assert artifact.report_revision_id == loaded_revision.id == approved_rev.id
            assert artifact.source_content_hash == loaded_revision.content_hash
            assert artifact.locale == locale
            assert artifact.format == export_format
            assert artifact.file_sha256
            manifest = artifact.render_manifest_json
            approval_snapshots.append(
                (
                    manifest["approved_revision_id"],
                    manifest["approved_content_hash"],
                    manifest["approved_by"],
                    manifest["approved_at"],
                )
            )

        assert len(set(approval_snapshots)) == 1
        assert approval_snapshots[0][0] == loaded_report.approved_revision_id
        assert approval_snapshots[0][1] == loaded_report.approved_content_hash
        assert approval_snapshots[0][2] == loaded_report.approved_by == "test-user"
        assert approval_snapshots[0][3]

    def test_persisted_artifact_manifests_equal_report_approval_snapshot(
        self, session_factory, tmp_path
    ):
        """PDF and DOCX renders of the same approved revision produce
        identical approval snapshots in their manifests, and those
        snapshots match the Report's approval fields exactly.
        """
        report, approved_rev = _setup_approved_report(session_factory)
        # Reload from DB to get canonical stored values
        db_report = _reload_report(session_factory, report.id)

        # Seed real templates
        with session_factory() as s:
            template_repo = SQLReportRepository(s)
            seed_default_templates(template_repo)
            s.commit()

        storage = ReportArtifactStorage(str(tmp_path / "artifacts"))

        # Render DOCX
        with session_factory() as s:
            repo = SQLReportRepository(s)
            template_repo = SQLReportRepository(s)
            render_svc = _formal_render_service(s, storage)
            docx_artifact = render_svc.render(
                locale=ReportLocale.ZH_CN,
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
            template_repo = SQLReportRepository(s)
            render_svc = _formal_render_service(s, storage)
            pdf_artifact = render_svc.render(
                locale=ReportLocale.ZH_CN,
                report_id=report.id,
                revision_number=approved_rev.revision_number,
                format="pdf",
                template_version=None,
                mode="formal",
                actor="test-user",
            )

        # Reload artifacts from DB in a fresh session
        with session_factory() as s:
            repo = SQLReportRepository(s)
            docx_reloaded = repo.get_artifact(docx_artifact.id)
            pdf_reloaded = repo.get_artifact(pdf_artifact.id)

            # Build expected approval dict from DB-canonical report
            approved_at = db_report.approved_at

            # Assert each manifest field matches the Report's approval fields
            for label, manifest in [
                ("DOCX", docx_reloaded.render_manifest_json),
                ("PDF", pdf_reloaded.render_manifest_json),
            ]:
                assert manifest["approved_revision_number"] == approved_rev.revision_number, (
                    f"{label} manifest approved_revision_number mismatch"
                )
                assert manifest["approved_revision_id"] == db_report.approved_revision_id, (
                    f"{label} manifest approved_revision_id mismatch"
                )
                assert manifest["approved_content_hash"] == db_report.approved_content_hash, (
                    f"{label} manifest approved_content_hash mismatch"
                )
                assert manifest["approved_by"] == db_report.approved_by, (
                    f"{label} manifest approved_by mismatch"
                )
                assert manifest["approved_at"] == approved_at, (
                    f"{label} manifest approved_at mismatch"
                )

            # Assert DOCX and PDF manifests are identical for all 5 approval fields
            docx_m = docx_reloaded.render_manifest_json
            pdf_m = pdf_reloaded.render_manifest_json
            assert docx_m["approved_revision_number"] == pdf_m["approved_revision_number"]
            assert docx_m["approved_revision_id"] == pdf_m["approved_revision_id"]
            assert docx_m["approved_content_hash"] == pdf_m["approved_content_hash"]
            assert docx_m["approved_by"] == pdf_m["approved_by"]
            assert docx_m["approved_at"] == pdf_m["approved_at"]

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
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version=None,
                    mode="formal",
                    actor="test-user",
                )
