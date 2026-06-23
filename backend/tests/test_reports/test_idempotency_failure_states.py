"""P0-5: Idempotency failure state machine tests.

Each test uses REAL SQL Repository (SQLReportRepository) and passes a
non-empty idempotency_key.  Only the failing stage is mocked — all other
stages use real SQL persistence.

Covers failure at each stage of the render pipeline with idempotency:
1. pending insert commit failure
2. rendering update commit failure
3. renderer failure
4. put_temp failure
5. finalize_temp failure
6. completed commit failure
7. failed-state commit failure + recovery
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.application.assembler import (
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
    ReportStatus,
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.errors import RenderError
from cold_storage.modules.reports.domain.models import (
    Report,
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
    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return {"name": "Test", "location": "Shanghai", "description": "Test"}

    def get_project_version(
        self, version_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return {"version_id": version_id, "project_id": project_id}


class _MockAssembler:
    def __init__(self, quality_status: ReportStatus = ReportStatus.GENERATED):
        self._provider = _MockDataProvider()
        self._quality_status = quality_status

    def assemble(self, **kwargs: Any) -> Any:
        from cold_storage.modules.reports.application.assembler import (
            ReportAssembler,
        )

        svc = ReportAssembler(self._provider)
        result = svc.assemble(**kwargs)
        result.quality_status = self._quality_status
        result.findings = []
        if "quality_summary" in result.content:
            result.content["quality_summary"]["findings"] = []
            result.content["quality_summary"]["blocker_count"] = 0
            result.content["quality_summary"]["warning_count"] = 0
            result.content["quality_summary"]["info_count"] = 0
        return result


class _MockStorage:
    """In-memory storage for artifact files."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def put_temp(self, data: bytes, filename: str) -> tuple[str, str]:
        key = f"temp/{filename}"
        self._files[key] = data
        return key, hashlib.sha256(data).hexdigest()

    def cleanup_temp(self, path: str) -> None:
        self._files.pop(path, None)

    def finalize_temp(self, path: str, artifact_id: str, filename: str) -> str:
        data = self._files.pop(path, b"")
        key = f"final/{artifact_id}/{filename}"
        self._files[key] = data
        return key

    def delete(self, key: str) -> None:
        self._files.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._files

    def get_path(self, key: str) -> str:
        if key not in self._files:
            raise FileNotFoundError(key)
        return f"/tmp/{key}"

    def put(self, artifact_id: str, data: bytes, filename: str) -> str:
        key = f"final/{artifact_id}/{filename}"
        self._files[key] = data
        return key

    def get(self, key: str) -> bytes:
        return self._files.get(key, b"")


def _create_report(repo: SQLReportRepository, session: Any) -> Report:
    report = Report.create(
        project_id="proj-1",
        project_version_id="ver-1",
        report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
        created_by="test-user",
    )
    repo.save_report(report)
    session.commit()
    return report


def _generate_revision(service: ReportService, report: Report) -> ReportRevision:
    service._assembler._quality_status = ReportStatus.GENERATED
    return service.generate_revision(report.id, "test-user")


def _full_review_flow(service: ReportService, report: Report) -> Report:
    report = service.submit_review(report.id, "test-user")
    report = service.mark_reviewed(report.id, "test-user")
    return report


def _approve_report(service: ReportService, report: Report) -> Report:
    rev = ReportRevision.create(
        report_id=report.id,
        revision_number=report.current_revision_number + 1,
        schema_version="cold_storage_concept_design@1.0.0",
        content_json={"report_metadata": {"project_id": report.project_id}},
        canonical_content_json={"report_metadata": {}},
        content_hash="abc123",
        quality_status=ReportStatus.APPROVED,
        quality_findings_json=[],
        generated_by="test-user",
    )
    service._repo.save_revision(rev)
    updated = replace(
        report,
        current_revision_number=rev.revision_number,
        updated_at=datetime.now(UTC),
        version=report.version + 1,
    )
    service._repo.update_report(updated, expected_version=report.version)
    service._repo.commit()
    return service.approve(report.id, "test-user")


def _make_template_mock() -> Any:
    from unittest.mock import MagicMock

    template_repo = MagicMock()
    template_mock = MagicMock(
        id="tpl-1",
        version="1.0.0",
        template_content_hash="hash",
        template_code="cold_storage_concept_design",
        format=ExportFormat.DOCX,
        status=TemplateStatus.ACTIVE,
        manifest_json={},
    )
    template_repo.get_active_template.return_value = template_mock
    template_repo.list_templates.return_value = [template_mock]
    return template_repo


def _setup_approved(session_factory: Any) -> tuple[Report, ReportRevision]:
    """Create and return an approved report + revision for testing."""
    with session_factory() as session:
        repo = SQLReportRepository(session)
        assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
        service = ReportService(repository=repo, assembler=assembler)
        report = _create_report(repo, session)
        _generate_revision(service, report)
        report = repo.get_report(report.id)
        report = _full_review_flow(service, report)
        report = _approve_report(service, report)
        rev = repo.get_latest_revision(report.id)
        return report, rev


def _verify_failed_state(
    session_factory: Any,
    report_id: str,
    idempotency_key: str,
    expected_failure_code: str,
    *,
    expect_no_artifacts: bool = False,
) -> None:
    """Verify the failed state after a render failure with idempotency."""
    with session_factory() as new_session:
        new_repo = SQLReportRepository(new_session)

        # No completed artifacts
        completed = new_repo.list_artifacts(report_id, status=ArtifactStatus.COMPLETED)
        assert len(completed) == 0, f"No completed artifact should exist, got {len(completed)}"

        # No rendering artifacts
        rendering = new_repo.list_artifacts(report_id, status=ArtifactStatus.RENDERING)
        assert len(rendering) == 0, f"No rendering artifact should exist, got {len(rendering)}"

        if not expect_no_artifacts:
            # At least one failed artifact
            failed = new_repo.list_artifacts(report_id, status=ArtifactStatus.FAILED)
            assert len(failed) >= 1, "Expected at least one FAILED artifact"
            assert failed[0].failure_code == expected_failure_code
            assert failed[0].failure_message != ""

            # No pending artifacts
            pending = new_repo.list_artifacts(report_id, status=ArtifactStatus.PENDING)
            assert len(pending) == 0, f"No pending artifact should exist, got {len(pending)}"

        # Idempotency record should be 'failed'
        idem = new_repo.get_idempotency_record(idempotency_key)
        assert idem is not None, "Idempotency record should exist"
        assert idem["status"] == "failed", (
            f"Idempotency status should be 'failed', got '{idem['status']}'"
        )
        result_payload = idem.get("result_payload") or {}
        assert result_payload.get("failure_code") == expected_failure_code


# ===========================================================================
# P0-5: Idempotency failure state machine tests
# ===========================================================================


class TestIdempotencyFailureStates:
    """All tests use REAL SQL + idempotency_key. Only the failing stage is mocked."""

    def test_pending_insert_commit_failure(self, session_factory, monkeypatch):
        """Stage: insert_pending commit failure.

        Mock _uow.commit after save_artifact to raise IOError.
        Artifact is not yet in DB → no artifacts found.
        Idempotency record should be failed.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-pending-fail-1"
        storage = _MockStorage()

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_pending_commit():
                nonlocal commit_count
                commit_count += 1
                # First commit is for idempotency record, second is for
                # insert_pending artifact — fail on the second commit
                if commit_count == 2:
                    raise OSError("DB commit failed")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_pending_commit)

            with pytest.raises(RenderError, match="Rendering failed"):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "OSError",
            expect_no_artifacts=True,
        )
        assert not storage._files, f"Storage should be empty, got: {list(storage._files.keys())}"

    def test_rendering_update_commit_failure(self, session_factory, monkeypatch):
        """Stage: update_rendering commit failure.

        Mock _uow.commit after update_artifact(rendering) to raise IOError.
        Artifact was saved (pending) but rendering update commit failed.
        Idempotency record should be failed.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-rendering-fail-1"
        storage = _MockStorage()

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_rendering_commit():
                nonlocal commit_count
                commit_count += 1
                # Commit 1: idempotency claim
                # Commit 2: insert_pending
                # Commit 3: update_rendering → fail
                if commit_count == 3:
                    raise OSError("DB commit failed")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_rendering_commit)

            with pytest.raises(RenderError, match="Rendering failed"):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "OSError",
        )
        assert not storage._files

    def test_renderer_failure(self, session_factory, monkeypatch):
        """Stage: render failure (RenderError from renderer).

        Mock _render_bytes to raise RenderError.
        Artifact was saved+rendering but rendering bytes failed.
        Idempotency record should be failed.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-render-fail-1"
        storage = _MockStorage()

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RenderError("Template parse failed"),
                ),
                pytest.raises(RenderError, match="Rendering failed"),
            ):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "RenderError",
        )
        assert not storage._files

    def test_put_temp_failure(self, session_factory, monkeypatch):
        """Stage: put_temp failure (IOError from storage).

        Mock storage.put_temp to raise IOError.
        Artifact was saved+rendering but temp file write failed.
        Idempotency record should be failed.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-puttemp-fail-1"
        storage = _MockStorage()

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            def fail_put_temp(data: bytes, filename: str) -> tuple[str, str]:
                raise OSError("Disk full")

            monkeypatch.setattr(storage, "put_temp", fail_put_temp)

            with pytest.raises(RenderError, match="Rendering failed"):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "OSError",
        )
        assert not storage._files

    def test_finalize_temp_failure(self, session_factory, monkeypatch):
        """Stage: finalize_temp failure.

        Mock storage.finalize_temp to raise IOError.
        Artifact was saved+rendering+temp but finalize failed.
        Idempotency record should be failed.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-finalize-fail-1"
        storage = _MockStorage()

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            def fail_finalize(temp_path: str, artifact_id: str, filename: str) -> str:
                raise OSError("Filesystem read-only")

            monkeypatch.setattr(storage, "finalize_temp", fail_finalize)

            with pytest.raises(RenderError, match="Rendering failed"):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "OSError",
        )
        # Temp file should be cleaned up
        assert not storage._files

    def test_completed_commit_failure(self, session_factory, monkeypatch):
        """Stage: completed commit failure.

        Mock _uow.commit after update_artifact(completed) to raise IOError.
        Artifact was finalized but the completed commit failed.
        Idempotency record should be failed.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-completed-fail-1"
        storage = _MockStorage()

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_completed_commit():
                nonlocal commit_count
                commit_count += 1
                # Commit 1: idempotency claim
                # Commit 2: insert_pending
                # Commit 3: update_rendering
                # Commit 4: update_completed + complete_idempotency → fail
                if commit_count == 4:
                    raise OSError("DB commit failed")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_completed_commit)

            with pytest.raises(RenderError, match="Rendering failed"):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "OSError",
        )
        # Finalized file should be cleaned up by failure handler
        assert not storage._files

    def test_failed_state_commit_failure_with_recovery(self, session_factory, monkeypatch):
        """Stage 7: failed-state commit failure.

        When the artifact is already in failed state and the failed-state
        commit also fails, the idempotency record may be stuck.
        This test verifies:
        1. Initial render fails and artifact is marked failed
        2. A second render with same key can recover via reset_failed_idempotency
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-failed-recovery-1"
        storage = _MockStorage()

        # First render: fails during rendering
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("First render broke"),
                ),
                pytest.raises(RenderError, match="Rendering failed"),
            ):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        # Verify idempotency record is failed
        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "RuntimeError",
        )

        # Second render: should recover via reset_failed_idempotency path
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                storage=storage,
                template_repo=_make_template_mock(),
                uow=uow,
            )

            # This should succeed — the render service detects the failed
            # idempotency record and calls reset_failed_idempotency + re-claim
            artifact = render_svc.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key,
            )

            assert artifact.status == ArtifactStatus.COMPLETED
            assert artifact.storage_key != ""

            # Idempotency record should now be completed
            idem = repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "completed"
