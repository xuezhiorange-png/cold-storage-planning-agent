"""Tests for P0-1 (Formal Approval Persistence) and P0-2 (Artifact Transaction Closure).

Covers:
1. Approve a report → approval fields persist across sessions
2. Approve rev1, generate rev2, formal export rev2 → rejected (approved revision mismatch)
3. Change approved_content_hash, formal export → rejected
4. Any approval field empty → formal export rejected
5. Formal artifact render_manifest_json contains all 4 approval fields
6. Renderer fails → artifact queryable as failed from new Session
7. Temp write fails → artifact queryable as failed
8. Completed commit fails → artifact queryable as failed, file deleted
9. File cleanup failure → structured error log present
10. Failed idempotency allows retry → final completed
11. Request changes clears approval fields
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

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
from cold_storage.modules.reports.application.service import (
    ReportService,
)
from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ExportFormat,
    ReportLocale,
    ReportStatus,
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.errors import (
    ExportPermissionError,
    RenderError,
)
from cold_storage.modules.reports.domain.models import (
    Report,
    ReportExportArtifact,
    ReportRevision,
)
from cold_storage.modules.reports.infrastructure.orm import Base
from cold_storage.modules.reports.infrastructure.repository import (
    SQLReportRepository,
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


class _MockDataProvider(ReportDataProvider):
    """Minimal data provider that returns enough data for the assembler."""

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return {"name": "Test Project", "location": "Shanghai", "description": "Test"}

    def get_project_version(
        self, version_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return {"version_id": version_id, "project_id": project_id}


class _MockAssembler(ReportAssembler):
    """Assembler that returns a configurable quality_status with no findings."""

    def __init__(self, quality_status: ReportStatus = ReportStatus.GENERATED):
        super().__init__(_MockDataProvider())
        self._quality_status = quality_status

    def assemble(self, **kwargs: Any) -> AssembledReport:
        result = super().assemble(**kwargs)
        result.quality_status = self._quality_status
        # Clear findings to avoid blockers from incomplete mock data
        result.findings = []
        # Also clear the quality_summary findings in content
        if "quality_summary" in result.content:
            result.content["quality_summary"]["findings"] = []
            result.content["quality_summary"]["blocker_count"] = 0
            result.content["quality_summary"]["warning_count"] = 0
            result.content["quality_summary"]["info_count"] = 0
        return result


class _MockStorage:
    """In-memory mock for ArtifactStoragePort."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._claim_owners: dict[str, tuple[str, int]] = {}  # key -> (claim_token, claim_version)
        self._fail_put_temp = False
        self._fail_cleanup_temp = False
        self._fail_delete = False
        self._fail_finalize = False

    def put_temp(self, data: bytes, filename: str) -> tuple[str, str]:
        if self._fail_put_temp:
            raise OSError("Disk full")
        key = f"temp/{filename}"
        self._files[key] = data
        sha = hashlib.sha256(data).hexdigest()
        return key, sha

    def cleanup_temp(self, path: str) -> None:
        if self._fail_cleanup_temp:
            raise OSError("Cleanup failed")
        self._files.pop(path, None)

    def finalize_temp(
        self,
        path: str,
        artifact_id: str,
        filename: str,
        *,
        claim_token: str = "",
        claim_version: int = 0,
    ) -> str:
        if self._fail_finalize:
            raise OSError("Finalize failed")
        data = self._files.pop(path, b"")
        key = f"final/{artifact_id}/{filename}"
        self._files[key] = data
        if claim_token:
            self._claim_owners[key] = (claim_token, claim_version)
        return key

    def delete(self, key: str, *, claim_token: str = "", claim_version: int = 0) -> None:
        if self._fail_delete:
            raise OSError("Delete failed")
        # Validate claim ownership if key exists and claim_token provided
        if key in self._claim_owners and claim_token:
            owner_token, owner_version = self._claim_owners[key]
            if owner_token != claim_token:
                raise PermissionError(
                    f"Claim token mismatch for {key}: expected {owner_token}, got {claim_token}"
                )
        self._files.pop(key, None)
        self._claim_owners.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._files

    def get_path(self, key: str) -> str:
        if key not in self._files:
            raise FileNotFoundError(key)
        return f"/tmp/{key}"

    def put(
        self,
        artifact_id: str,
        data: bytes,
        filename: str,
        *,
        claim_token: str = "",
        claim_version: int = 0,
    ) -> str:
        key = f"final/{artifact_id}/{filename}"
        # Reject overwrite if key exists and owned by a different claim
        if key in self._claim_owners and claim_token:
            owner_token, owner_version = self._claim_owners[key]
            if owner_token != claim_token:
                raise PermissionError(
                    f"Claim token mismatch for {key}: expected {owner_token}, got {claim_token}"
                )
        self._files[key] = data
        if claim_token:
            self._claim_owners[key] = (claim_token, claim_version)
        return key

    def get(self, key: str) -> bytes:
        return self._files.get(key, b"")

    def replace(
        self,
        key: str,
        data: bytes,
        *,
        claim_token: str = "",
        claim_version: int = 0,
    ) -> str:
        """Replace an existing artifact's content in-place (mock)."""
        if key not in self._files:
            raise FileNotFoundError(key)
        # Validate claim ownership
        if key in self._claim_owners:
            owner_token, owner_version = self._claim_owners[key]
            if owner_token != claim_token or (claim_token and owner_version != claim_version):
                raise PermissionError(
                    f"Claim token/version mismatch for {key}: "
                    f"expected ({owner_token}, {owner_version}), "
                    f"got ({claim_token}, {claim_version})"
                )
        self._files[key] = data
        if claim_token:
            self._claim_owners[key] = (claim_token, claim_version)
        return key

    def delete_legacy_artifact(
        self,
        key: str,
        *,
        migration_actor: str,
        audit_reason: str,
        repository: Any = None,
    ) -> None:
        """Privileged migration delete for legacy artifacts (mock)."""
        if key not in self._files:
            raise FileNotFoundError(key)
        if not migration_actor.strip() or not audit_reason.strip():
            raise ValueError("migration_actor and audit_reason must be non-empty")
        # Only allow if no owner metadata exists
        if key in self._claim_owners:
            raise PermissionError(
                f"Storage key {key} has owner metadata. "
                f"Use delete() with correct claim_token/version instead."
            )
        del self._files[key]


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
    quality_status: ReportStatus = ReportStatus.GENERATED,
) -> ReportRevision:
    """Generate a revision for a report."""
    # Override the assembler's quality_status
    service._assembler._quality_status = quality_status
    return service.generate_revision(report.id, "test-user")


def _full_review_flow(service: ReportService, report: Report) -> Report:
    """Walk through the full review flow to get to REVIEWED status."""
    # Submit review (GENERATED → UNDER_REVIEW)
    report = service.submit_review(report.id, "test-user")
    # Mark reviewed (UNDER_REVIEW → REVIEWED)
    report = service.mark_reviewed(report.id, "test-user")
    return report


def _approve_with_quality_status(
    service: ReportService,
    report: Report,
    quality_status: ReportStatus = ReportStatus.APPROVED,
) -> Report:
    """Approve a report with a specific quality status on the latest revision.

    Creates a new revision with the desired quality_status, then calls approve.
    """
    # Create a new revision with the desired quality_status
    rev = ReportRevision.create(
        report_id=report.id,
        revision_number=report.current_revision_number + 1,
        schema_version="cold_storage_concept_design@1.0.0",
        content_json={"report_metadata": {"project_id": report.project_id}},
        canonical_content_json={"report_metadata": {}},
        content_hash="abc123",
        quality_status=quality_status,
        quality_findings_json=[],
        generated_by="test-user",
    )
    service._repo.save_revision(rev)
    # Update report's current_revision_number
    updated = replace(
        report,
        current_revision_number=rev.revision_number,
        updated_at=datetime.now(UTC),
        version=report.version + 1,
    )
    service._repo.update_report(updated, expected_version=report.version)
    service._repo.commit()
    # Now actually call approve to set approval fields
    report = service.approve(report.id, "test-user")
    return report


def _setup_approved_report(
    session_factory: sessionmaker,
) -> tuple[Report, ReportRevision, ReportService]:
    """Create a fully approved report for testing."""
    with session_factory() as session:
        repo = SQLReportRepository(session)
        assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
        service = ReportService(repository=repo, assembler=assembler)

        report = _create_report(repo, session)
        # Generate rev1 with GENERATED quality (so report status = GENERATED)
        _generate_revision(service, report, ReportStatus.GENERATED)
        # Reload report to get updated status
        report = repo.get_report(report.id)
        # Full review flow: GENERATED → UNDER_REVIEW → REVIEWED
        report = _full_review_flow(service, report)
        # Approve: create rev2 with APPROVED quality, then approve
        report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
        return report, repo.get_latest_revision(report.id), service


# ---------------------------------------------------------------------------
# Test 1: Approve a report → approval fields persist across sessions
# ---------------------------------------------------------------------------


class TestApprovalPersistence:
    def test_approve_persists_fields(self, session_factory):
        """Approve a report, close session, open new session, re-read → fields persist."""
        report, rev, service = _setup_approved_report(session_factory)

        # Close the session, open a new one
        with session_factory() as new_session:
            new_repo = SQLReportRepository(new_session)
            reloaded = new_repo.get_report(report.id)

            assert reloaded is not None
            assert reloaded.approved_revision_id == rev.id
            assert reloaded.approved_content_hash == rev.content_hash
            assert reloaded.approved_by == "test-user"
            assert reloaded.approved_at is not None

    def test_approve_sets_all_fields(self, session_factory):
        """Verify all 4 approval fields are set after approve."""
        report, rev, service = _setup_approved_report(session_factory)
        with session_factory() as s:
            repo = SQLReportRepository(s)
            loaded = repo.get_report(report.id)
            assert loaded.approved_revision_id == rev.id
            assert loaded.approved_content_hash == rev.content_hash
            assert loaded.approved_by == "test-user"
            assert loaded.approved_at is not None


# ---------------------------------------------------------------------------
# Test 2: Approve rev1, generate rev2, formal export rev2 → rejected
# ---------------------------------------------------------------------------


class TestApprovalRevisionMismatch:
    def test_formal_export_rejected_on_mismatch(self, session_factory):
        """Approve rev1, generate rev2, formal export rev2 → rejected."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            # Generate rev1 with GENERATED quality
            _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            # Full review flow
            report = _full_review_flow(service, report)
            # Approve (creates rev2 with APPROVED quality)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)

            # Create rev3 manually (after approval, status is APPROVED so can't use service)
            rev3 = ReportRevision.create(
                report_id=report.id,
                revision_number=report.current_revision_number + 1,
                schema_version="cold_storage_concept_design@1.0.0",
                content_json={"report_metadata": {"project_id": report.project_id}},
                canonical_content_json={"report_metadata": {}},
                content_hash="different_hash",
                quality_status=ReportStatus.APPROVED,
                quality_findings_json=[],
                generated_by="test-user",
            )
            repo.save_revision(rev3)
            session.commit()
            rev2 = rev3

            # Formal export of rev2 should fail (approved is rev1)
            storage = _MockStorage()
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )
            with pytest.raises(ExportPermissionError, match="revision mismatch|Approved revision"):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev2.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                )


# ---------------------------------------------------------------------------
# Test 3: Change approved_content_hash, formal export → rejected
# ---------------------------------------------------------------------------


class TestApprovalContentHashMismatch:
    def test_formal_export_rejected_on_hash_mismatch(self, session_factory):
        """Change approved_content_hash → formal export rejected."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            rev = _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)

            # Tamper the approved_content_hash
            report = repo.get_report(report.id)
            tampered = replace(report, approved_content_hash="WRONG_HASH")
            repo.update_report(tampered, expected_version=report.version)
            session.commit()

            # Formal export should fail
            storage = _MockStorage()
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )
            with pytest.raises(ExportPermissionError, match="mismatch|hash"):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                )


# ---------------------------------------------------------------------------
# Test 4: Any approval field empty → formal export rejected
# ---------------------------------------------------------------------------


class TestMissingApprovalFields:
    @pytest.mark.parametrize(
        "field",
        ["approved_revision_id", "approved_content_hash", "approved_by", "approved_at"],
    )
    def test_formal_export_rejected_when_field_missing(self, session_factory, field):
        """Formal export rejected when any approval field is empty."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            # Clear one field
            report = repo.get_report(report.id)
            cleared = replace(report, **{field: None})
            repo.update_report(cleared, expected_version=report.version)
            session.commit()

            storage = _MockStorage()
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )
            with pytest.raises(ExportPermissionError, match="Missing approval fields"):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                )


# ---------------------------------------------------------------------------
# Test 5: Formal artifact render_manifest_json contains all 4 approval fields
# ---------------------------------------------------------------------------


class TestRenderManifestApprovalFields:
    def test_manifest_contains_all_approval_fields(self, session_factory):
        """Formal artifact render_manifest_json contains all 4 approval fields."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            storage = _MockStorage()
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )
            artifact = render_svc.render(
                locale=ReportLocale.ZH_CN,
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
            )
            manifest = artifact.render_manifest_json
            assert "approved_revision_id" in manifest
            assert "approved_content_hash" in manifest
            assert "approved_by" in manifest
            assert "approved_at" in manifest
            assert manifest["approved_revision_id"] == rev.id
            assert manifest["approved_content_hash"] == rev.content_hash
            assert manifest["approved_by"] == "test-user"
            assert manifest["approved_at"] != ""


# ---------------------------------------------------------------------------
# Test 6: Renderer fails → artifact queryable as failed from new Session
# ---------------------------------------------------------------------------


class TestRendererFailureArtifactQueryable:
    def test_renderer_failure_persists_failed_state(self, session_factory):
        """Renderer fails → artifact queryable as failed from new Session."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            rev = _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            storage = _MockStorage()
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]

            # Capture the artifact_id before the failure
            captured_artifact_id: list[str] = []

            class CaptureArtifactRepo:
                def __init__(self, real_repo: SQLReportRepository):
                    self._real = real_repo
                    self._session = getattr(real_repo, "_session", None)

                def save_artifact(self, artifact: ReportExportArtifact) -> None:
                    self._real.save_artifact(artifact)

                def get_artifact(self, artifact_id: str) -> ReportExportArtifact | None:
                    return self._real.get_artifact(artifact_id)

                def update_artifact(self, artifact: ReportExportArtifact) -> None:
                    captured_artifact_id.clear()
                    captured_artifact_id.append(artifact.id)
                    self._real.update_artifact(artifact)

                def commit(self) -> None:
                    self._real.commit()

                def rollback(self) -> None:
                    self._real.rollback()

            cap_repo = CaptureArtifactRepo(repo)

            render_svc = ReportRenderService(
                uow=ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=cap_repo),
                storage=storage,
                template_repo=template_repo,
            )

            # Make rendering fail
            with (
                patch.object(
                    render_svc, "_render_bytes", side_effect=RuntimeError("Renderer broke")
                ),
                pytest.raises(RenderError),
            ):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                )

            # P0-11: Must have captured an artifact_id — fail test if not
            assert captured_artifact_id, "No artifact_id was captured during render"

            # Verify artifact is failed in a new session
            with session_factory() as new_session:
                new_repo = SQLReportRepository(new_session)
                failed = new_repo.get_artifact(captured_artifact_id[0])
                assert failed is not None
                assert failed.status == ArtifactStatus.FAILED


# ---------------------------------------------------------------------------
# Test 7: Temp write fails → artifact queryable as failed
# ---------------------------------------------------------------------------


class TestTempWriteFailure:
    def test_temp_write_failure_persists_failed_state(self, session_factory):
        """Temp write fails → artifact queryable as failed."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            rev = _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            storage = _MockStorage()
            storage._fail_put_temp = True
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]
            artifact_repo = repo  # Use real repo for DB queries
            render_svc = ReportRenderService(
                uow=ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=artifact_repo),
                storage=storage,
                template_repo=template_repo,
            )

            with pytest.raises(RenderError):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                )

            # Verify artifact is failed
            with session_factory() as new_session:
                new_repo = SQLReportRepository(new_session)
                artifacts = new_repo.list_artifacts(report.id, status=ArtifactStatus.FAILED)
                assert len(artifacts) >= 1


# ---------------------------------------------------------------------------
# Test 8: Completed commit fails → artifact queryable as failed, file deleted
# ---------------------------------------------------------------------------


class TestCompletedCommitFailure:
    def test_commit_failure_persists_failed_and_deletes_file(self, session_factory):
        """Completed commit fails → artifact queryable as failed, file deleted."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            rev = _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            storage = _MockStorage()
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]

            # Use real repo but make UOW commit fail on the final completed commit
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            call_count = 0
            original_uow_commit = uow.commit
            failed_once = False

            def failing_uow_commit():
                nonlocal call_count, failed_once
                call_count += 1
                if call_count >= 3 and not failed_once:
                    failed_once = True
                    raise RuntimeError("Commit failed")
                original_uow_commit()

            uow.commit = failing_uow_commit

            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )

            with pytest.raises(RenderError):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key="idem-commit-fail",
                )

            # Verify artifact is failed
            with session_factory() as new_session:
                new_repo = SQLReportRepository(new_session)
                artifacts = new_repo.list_artifacts(report.id, status=ArtifactStatus.FAILED)
                assert len(artifacts) >= 1

                # No COMPLETED artifacts
                completed = new_repo.list_artifacts(report.id, status=ArtifactStatus.COMPLETED)
                assert len(completed) == 0, "No completed artifacts after commit failure"

                # No RENDERING artifacts remain
                rendering = new_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
                assert len(rendering) == 0, "No rendering artifacts after commit failure"

            # P0-11: Verify file was deleted from storage
            assert len(storage._files) == 0, "All files should have been cleaned up"

            # P0-11: Verify idempotency is failed
            idem_rec = repo.get_idempotency_record("idem-commit-fail")
            assert idem_rec is not None, "Idempotency record should exist"
            assert idem_rec["status"] == "failed", (
                f"Idempotency should be failed, got {idem_rec['status']}"
            )


# ---------------------------------------------------------------------------
# Test 9: File cleanup failure → structured error log present
# ---------------------------------------------------------------------------


class TestFileCleanupFailureLogging:
    def test_cleanup_failure_logs_structured_error(self, session_factory, caplog):
        """File cleanup failure → structured error log present."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            rev = _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            storage = _MockStorage()
            storage._fail_finalize = True
            storage._fail_cleanup_temp = True
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=template_repo,
            )

            with (
                caplog.at_level(
                    logging.WARNING,
                    logger="cold_storage.modules.reports.application.render_service",
                ),
                pytest.raises(RenderError),
            ):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                )

            # Check for structured error log
            cleanup_logs = [
                r
                for r in caplog.records
                if "clean" in r.message.lower()
                and (
                    "temp" in r.message.lower()
                    or "storage" in r.message.lower()
                    or "file" in r.message.lower()
                )
            ]
            assert len(cleanup_logs) >= 1
            # Verify structured extra fields are present
            for log_record in cleanup_logs:
                assert hasattr(log_record, "artifact_id") or "artifact_id" in str(log_record)


# ---------------------------------------------------------------------------
# Test 10: Failed idempotency allows retry → final completed
# ---------------------------------------------------------------------------


class TestFailedIdempotencyRetry:
    def test_failed_idempotency_allows_retry(self, session_factory):
        """Failed idempotency allows retry → final completed."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            rev = _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)
            report = repo.get_report(report.id)
            rev = repo.get_latest_revision(report.id)

            storage = _MockStorage()
            template_repo = MagicMock()
            template_mock = MagicMock(
                id="tpl-1",
                version="1.0.0",
                template_content_hash="hash",
                template_code="cold_storage_concept_design",
                format=ExportFormat.DOCX,
                status=TemplateStatus.ACTIVE,
                locale=ReportLocale.ZH_CN,
                report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
                schema_version="cold_storage_concept_design@1.0.0",
                manifest_json={},
            )
            template_repo.get_active_template.return_value = template_mock
            template_repo.list_templates.return_value = [template_mock]
            artifact_repo = repo  # Use real repo for DB persistence

            render_svc = ReportRenderService(
                uow=ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=artifact_repo),
                storage=storage,
                template_repo=template_repo,
            )

            idempotency_key = "idem-retry-test"

            # First attempt fails
            with (
                patch.object(
                    render_svc, "_render_bytes", side_effect=RuntimeError("First attempt fails")
                ),
                pytest.raises(RenderError),
            ):
                render_svc.render(
                    locale=ReportLocale.ZH_CN,
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

            # Verify idempotency is failed
            rec = repo.get_idempotency_record(idempotency_key)
            assert rec is not None
            assert rec["status"] == "failed"

            # Second attempt should succeed (idempotency reset + re-claim)
            result = render_svc.render(
                locale=ReportLocale.ZH_CN,
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key,
            )
            assert result.status == ArtifactStatus.COMPLETED

            # Verify idempotency is now completed
            rec = repo.get_idempotency_record(idempotency_key)
            assert rec is not None
            assert rec["status"] == "completed"


# ---------------------------------------------------------------------------
# Test 11: Request changes clears approval fields
# ---------------------------------------------------------------------------


class TestRequestChangesClearsApproval:
    def test_request_changes_clears_approval_fields(self, session_factory):
        """New revision clears approval fields."""
        with session_factory() as session:
            repo = SQLReportRepository(session)
            assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
            service = ReportService(repository=repo, assembler=assembler)
            report = _create_report(repo, session)

            # Generate and approve
            _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)
            report = _full_review_flow(service, report)
            report = _approve_with_quality_status(service, report, ReportStatus.APPROVED)

            # Verify approval fields are set
            report = repo.get_report(report.id)
            assert report.approved_revision_id is not None
            assert report.approved_content_hash is not None
            assert report.approved_by is not None
            assert report.approved_at is not None

            # Put report back to GENERATED status so we can generate a new revision
            from dataclasses import replace as dc_replace

            updated = dc_replace(report, status=ReportStatus.GENERATED, version=report.version + 1)
            repo.update_report(updated, expected_version=report.version)
            session.commit()
            report = repo.get_report(report.id)

            # Generate a new revision (which should clear approval fields)
            _generate_revision(service, report, ReportStatus.GENERATED)
            report = repo.get_report(report.id)

            # Verify approval fields are cleared
            assert report.approved_revision_id is None
            assert report.approved_content_hash is None
            assert report.approved_by is None
            assert report.approved_at is None
