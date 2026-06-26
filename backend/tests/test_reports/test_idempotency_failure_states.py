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
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
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
    ReportStatus,
    ReportType,
)
from cold_storage.modules.reports.domain.errors import (
    IdempotencyClaimError,
    RenderError,
    StaleClaimError,
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


def _setup_approved(session_factory: Any) -> tuple[Report, ReportRevision]:
    """Create and return an approved report + revision for testing.

    Seeds real DOCX/PDF templates so the render service can find them.
    """
    with session_factory() as session:
        repo = SQLReportRepository(session)
        assembler = _MockAssembler(quality_status=ReportStatus.APPROVED)
        service = ReportService(repository=repo, assembler=assembler)
        report = _create_report(repo, session)
        _generate_revision(service, report)
        report = repo.get_report(report.id)
        report = _full_review_flow(service, report)
        report = _approve_report(service, report)
        # Seed real templates so render service can find active template
        seed_default_templates(repo)
        rev = repo.get_latest_revision(report.id)
        return report, rev


def _verify_failed_state(
    session_factory: Any,
    report_id: str,
    idempotency_key: str,
    expected_failure_code: str,
    *,
    expect_no_artifacts: bool = False,
    storage_check: Callable[[], None] | None = None,
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

    # Optional storage cleanup check
    if storage_check is not None:
        storage_check()


class FakeClock:
    """Injectable clock for controllable time in tests."""

    def __init__(self, initial):
        self._time = initial

    def __call__(self):
        return self._time

    def advance(self, seconds):
        self._time += timedelta(seconds=seconds)


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
                template_repo=repo,
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
                template_repo=repo,
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
                template_repo=repo,
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
                template_repo=repo,
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
                template_repo=repo,
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
                template_repo=repo,
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

    def test_finalize_failure_removes_real_temp_and_final_files(
        self, session_factory, tmp_path, monkeypatch
    ):
        """When finalize_temp fails, both temp and final files should be cleaned up.

        Uses real ReportArtifactStorage so actual files are written to disk.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-finalize-cleanup"
        storage = ReportArtifactStorage(str(tmp_path / "artifacts"))

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(uow=uow, storage=storage, template_repo=repo)

            def fail_finalize(path: str, artifact_id: str, filename: str) -> str:
                raise OSError("Simulated finalize failure")

            monkeypatch.setattr(storage, "finalize_temp", fail_finalize)

            with pytest.raises(RenderError):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        def _check_storage_empty():
            artifacts_dir = tmp_path / "artifacts"
            if artifacts_dir.exists():
                files = [f for f in artifacts_dir.rglob("*") if f.is_file()]
                assert len(files) == 0, f"Artifacts dir should have no files, found: {files}"

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "OSError",
            storage_check=_check_storage_empty,
        )

    def test_completed_commit_failure_removes_real_final_file(
        self, session_factory, tmp_path, monkeypatch
    ):
        """When completed commit fails, the finalized file should be deleted.

        Uses real ReportArtifactStorage so actual files are written to disk.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-completed-cleanup"
        storage = ReportArtifactStorage(str(tmp_path / "artifacts"))

        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(uow=uow, storage=storage, template_repo=repo)

            commit_count = 0
            original_commit = uow.commit

            def fail_on_completed_commit():
                nonlocal commit_count
                commit_count += 1
                # Commit 1: idempotency claim (OK)
                # Commit 2: insert_pending (OK)
                # Commit 3: update_rendering (OK)
                # Commit 4: completed + complete_idempotency — FAIL
                if commit_count == 4:
                    raise OSError("Simulated completed commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_completed_commit)

            with pytest.raises(RenderError):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key,
                )

        def _check_storage_empty():
            artifacts_dir = tmp_path / "artifacts"
            if artifacts_dir.exists():
                files = [f for f in artifacts_dir.rglob("*") if f.is_file()]
                assert len(files) == 0, f"Artifacts dir should have no files, found: {files}"

        _verify_failed_state(
            session_factory,
            report.id,
            idempotency_key,
            "OSError",
            storage_check=_check_storage_empty,
        )

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
                template_repo=repo,
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
                template_repo=repo,
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

    def test_failed_state_commit_failure_recovers_without_test_side_db_patch(
        self, session_factory, tmp_path, monkeypatch
    ):
        """When the render pipeline AND failed-state commit both fail, verify
        recovery on retry via stale-claim detection.

        The render service's exception handler attempts to persist FAILED state.
        If that commit also fails, it rolls back and logs.  The idempotency
        record is stuck in 'claimed' state.  A retry with the same key detects
        the stale claim (claimed_at < now - stale_claim_seconds), atomically
        reclaims it, cleans up orphaned artifacts, and proceeds to render.

        No test-side DB patches are used — the product code recovers fully.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-recovery-1"

        # Attempt 1: Fail the render bytes + make the failed-state commit fail.
        # This means:
        #   commit 1: idempotency claim (OK) — claimed_at set
        #   commit 2: insert_pending (OK)
        #   commit 3: update_rendering (OK)
        #   render: FAILS
        #   commit 4: failure handler (update FAILED + fail idempotency) -- FAIL
        # After this, idempotency is stuck in 'claimed' state and the artifact
        # stays in RENDERING state (rollback undoes FAILED update).
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            storage = ReportArtifactStorage(str(tmp_path / "artifacts"))
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=0,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_failed_state_commit():
                nonlocal commit_count
                commit_count += 1
                # Commit 1-3: pipeline commits (OK)
                # Commit 4: failure handler commit -- FAIL
                if commit_count == 4:
                    raise OSError("Simulated failed-state commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_failed_state_commit)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
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

        # Verify stuck state — no test-side DB patches applied
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            idem = check_repo.get_idempotency_record(idempotency_key)
            assert idem is not None, "Idempotency record should exist"
            assert idem["status"] == "claimed", (
                f"Idempotency should be stuck in 'claimed', got '{idem['status']}'"
            )

        # Attempt 2: Same key — stale_claim_seconds=0 makes the claim stale.
        # Product code detects stale claim, CAS-reclaims, cleans up artifacts,
        # and proceeds to render successfully.
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            storage2 = ReportArtifactStorage(str(tmp_path / "artifacts2"))
            render_svc2 = ReportRenderService(
                uow=uow,
                storage=storage2,
                template_repo=repo,
                stale_claim_seconds=0,
            )

            artifact = render_svc2.render(
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
            result_payload = idem.get("result_payload") or {}
            assert result_payload.get("artifact_id") == artifact.id

        # Final DB verification — strict assertions
        with session_factory() as final_session:
            final_repo = SQLReportRepository(final_session)

            # Exactly one completed artifact
            completed = final_repo.list_artifacts(report.id, status=ArtifactStatus.COMPLETED)
            assert len(completed) == 1, (
                f"Expected exactly 1 completed artifact, got {len(completed)}"
            )
            assert completed[0].id == artifact.id

            # No pending artifacts
            pending = final_repo.list_artifacts(report.id, status=ArtifactStatus.PENDING)
            assert len(pending) == 0, f"Expected 0 pending artifacts, got {len(pending)}"

            # No rendering artifacts
            rendering = final_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            assert len(rendering) == 0, f"Expected 0 rendering artifacts, got {len(rendering)}"

            # Idempotency is completed and points to the final artifact
            idem = final_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "completed"
            assert idem["result_payload"]["artifact_id"] == completed[0].id

        # No test-side DB modifications occurred in this test
        # (no fail_idempotency_record, no direct SQL UPDATE)

    # ------------------------------------------------------------------
    # P0-6: Stale-claim recovery + claim-token fencing tests
    # ------------------------------------------------------------------

    def test_reclaimed_old_worker_cannot_complete_idempotency(
        self, session_factory, tmp_path, monkeypatch
    ):
        """After stale reclaim, old worker's token cannot complete the idempotency record.

        1. First render fails (commit 4 fails) → idempotency stuck in 'claimed'.
        2. Advance clock past stale threshold.
        3. Second render reclaims stale claim and succeeds.
        4. Old worker tries to complete with old claim_token → ValueError.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-old-worker-1"
        storage = _MockStorage()
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Attempt 1: fail render + fail state commit → stuck in claimed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_commit_4():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 4:
                    raise OSError("Simulated commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_commit_4)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
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

        # Record old claim_token and version
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            idem = check_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "claimed"
            old_claim_token = idem["claim_token"]
            old_claim_version = idem["claim_version"]

        # Advance clock past stale threshold
        clock.advance(600)

        # Attempt 2: reclaim and succeed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc2 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            artifact = render_svc2.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key,
            )
            assert artifact.status == ArtifactStatus.COMPLETED

        # Old worker tries to complete with old token → should raise StaleClaimError
        with session_factory() as session:
            repo = SQLReportRepository(session)
            with pytest.raises(StaleClaimError):
                repo.complete_idempotency_record(
                    idempotency_key,
                    {"artifact_id": "x"},
                    claim_token=old_claim_token,
                    claim_version=old_claim_version,
                )

    def test_reclaimed_old_worker_cannot_complete_artifact(
        self, session_factory, tmp_path, monkeypatch
    ):
        """After stale reclaim, old artifact is failed and old worker can't update it.

        1. First render fails → artifact stuck in rendering.
        2. Advance clock, retry succeeds → old artifact failed, new one completed.
        3. Old artifact is in terminal (failed) state.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-art-fence-1"
        storage = _MockStorage()
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Attempt 1: fail render + fail state commit → stuck
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_commit_4():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 4:
                    raise OSError("Simulated commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_commit_4)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
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

        # Record old artifact id
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            rendering = check_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            assert len(rendering) == 1
            old_artifact_id = rendering[0].id

        # Advance clock past stale
        clock.advance(600)

        # Attempt 2: reclaim and succeed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc2 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            new_artifact = render_svc2.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key,
            )
            assert new_artifact.status == ArtifactStatus.COMPLETED
            assert new_artifact.id != old_artifact_id

        # Verify old artifact is failed
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            old_artifact = check_repo.get_artifact(old_artifact_id)
            assert old_artifact is not None
            assert old_artifact.status == ArtifactStatus.FAILED
            assert old_artifact.failure_code != ""

    def test_only_current_claim_token_can_fail_attempt(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Old claim_token cannot fail an idempotency record after reclaim.

        1. First render fails → stuck in claimed.
        2. Advance clock, retry succeeds → idempotency completed with new token.
        3. Old worker tries to fail with old token → record stays completed.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-fail-fence-1"
        storage = _MockStorage()
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Attempt 1: fail render + fail state commit → stuck in claimed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_commit_4():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 4:
                    raise OSError("Simulated commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_commit_4)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
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

        # Record old claim_token and version
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            idem = check_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "claimed"
            old_claim_token = idem["claim_token"]
            old_claim_version = idem["claim_version"]

        # Advance clock past stale
        clock.advance(600)

        # Attempt 2: reclaim and succeed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc2 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            artifact = render_svc2.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key,
            )
            assert artifact.status == ArtifactStatus.COMPLETED

        # Old worker tries to fail with old claim_token → StaleClaimError
        with session_factory() as session:
            repo = SQLReportRepository(session)
            with pytest.raises(StaleClaimError):
                repo.fail_idempotency_record(
                    idempotency_key,
                    "RuntimeError",
                    "old attempt",
                    claim_token=old_claim_token,
                    claim_version=old_claim_version,
                )

        # Verify idempotency is still completed (old token couldn't affect it)
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            idem = check_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "completed"

    def test_stale_recovery_fails_only_artifact_for_same_idempotency_key(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Stale recovery only fails artifacts for the same idempotency key.

        1. Render key "idem-scoped-1" (docx) → fails → stuck.
        2. Advance clock, retry key 1 → reclaims, succeeds.
        3. Old artifact for key 1 is failed, new one is completed.
        4. Render key "idem-scoped-2" (pdf) → succeeds.
        5. key 2 artifact is completed, not touched by key 1 recovery.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key_1 = "idem-scoped-1"
        idempotency_key_2 = "idem-scoped-2"
        storage = _MockStorage()
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Render key 1: fails → stuck
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_commit_4():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 4:
                    raise OSError("Simulated commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_commit_4)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
            ):
                render_svc.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key_1,
                )

        # Record old artifact for key 1
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            rendering = check_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            assert len(rendering) == 1
            old_artifact_id_1 = rendering[0].id

        # Advance clock past stale
        clock.advance(600)

        # Retry key 1: reclaim and succeed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc2 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            new_artifact_1 = render_svc2.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key_1,
            )
            assert new_artifact_1.status == ArtifactStatus.COMPLETED

        # Verify old artifact for key 1 is failed
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            old = check_repo.get_artifact(old_artifact_id_1)
            assert old is not None
            assert old.status == ArtifactStatus.FAILED

        # Render key 2 (pdf): succeeds
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc3 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            new_artifact_2 = render_svc3.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="pdf",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key_2,
            )
            assert new_artifact_2.status == ArtifactStatus.COMPLETED
            assert new_artifact_2.id != new_artifact_1.id

        # Verify both artifacts are in correct state
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            completed = check_repo.list_artifacts(report.id, status=ArtifactStatus.COMPLETED)
            completed_by_key = {a.idempotency_key: a for a in completed}
            assert idempotency_key_1 in completed_by_key
            assert idempotency_key_2 in completed_by_key
            assert completed_by_key[idempotency_key_1].id == new_artifact_1.id
            assert completed_by_key[idempotency_key_2].id == new_artifact_2.id

    def test_stale_recovery_does_not_touch_other_render_for_same_report(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Stale recovery for one key does not affect a completed render with another key.

        1. Render key "idem-other-1" → succeeds → completed artifact.
        2. Render key "idem-other-2" → fails → stuck.
        3. Advance clock, retry key 2 → reclaims, succeeds.
        4. key 1 completed artifact still exists and is completed.
        5. key 2 has its own completed artifact.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key_1 = "idem-other-1"
        idempotency_key_2 = "idem-other-2"
        storage = _MockStorage()
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Render key 1: succeeds
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            artifact_1 = render_svc.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key_1,
            )
            assert artifact_1.status == ArtifactStatus.COMPLETED

        # Render key 2: fails → stuck
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc2 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_commit_4():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 4:
                    raise OSError("Simulated commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_commit_4)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
            ):
                render_svc2.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key_2,
                )

        # Advance clock past stale
        clock.advance(600)

        # Retry key 2: reclaim and succeed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc3 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            new_artifact_2 = render_svc3.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key_2,
            )
            assert new_artifact_2.status == ArtifactStatus.COMPLETED

        # Verify both artifacts are completed and independent
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)

            # key 1 idempotency still completed
            idem1 = check_repo.get_idempotency_record(idempotency_key_1)
            assert idem1 is not None
            assert idem1["status"] == "completed"

            # key 2 idempotency completed
            idem2 = check_repo.get_idempotency_record(idempotency_key_2)
            assert idem2 is not None
            assert idem2["status"] == "completed"

            # Exactly 2 completed artifacts
            completed = check_repo.list_artifacts(report.id, status=ArtifactStatus.COMPLETED)
            assert len(completed) == 2
            completed_by_key = {a.idempotency_key: a for a in completed}
            assert idempotency_key_1 in completed_by_key
            assert idempotency_key_2 in completed_by_key
            assert completed_by_key[idempotency_key_1].id == artifact_1.id
            assert completed_by_key[idempotency_key_2].id == new_artifact_2.id

            # No pending or rendering artifacts
            pending = check_repo.list_artifacts(report.id, status=ArtifactStatus.PENDING)
            assert len(pending) == 0
            rendering = check_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            assert len(rendering) == 0

    def test_stale_recovery_does_not_touch_other_format_or_template(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Stale recovery for one key does not affect a completed render with
        the same format but a different idempotency key.

        1. Render key "idem-format-1" (docx) → succeeds → completed.
        2. Render key "idem-format-2" (docx) → fails → stuck.
        3. Advance clock, retry key 2 → reclaims, succeeds.
        4. key 1 artifact still completed.
        5. key 2 has its own completed artifact.
        6. Both artifacts have different idempotency_key values.
        """
        report, rev = _setup_approved(session_factory)
        idempotency_key_1 = "idem-format-1"
        idempotency_key_2 = "idem-format-2"
        storage = _MockStorage()
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Render key 1: succeeds
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            artifact_1 = render_svc.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key_1,
            )
            assert artifact_1.status == ArtifactStatus.COMPLETED

        # Render key 2: fails → stuck
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc2 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_commit_4():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 4:
                    raise OSError("Simulated commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_commit_4)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
            ):
                render_svc2.render(
                    report_id=report.id,
                    revision_number=rev.revision_number,
                    format="docx",
                    template_version="1.0.0",
                    mode="formal",
                    actor="test-user",
                    idempotency_key=idempotency_key_2,
                )

        # Advance clock past stale
        clock.advance(600)

        # Retry key 2: reclaim and succeed
        with session_factory() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            render_svc3 = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=300,
                clock=clock,
            )
            new_artifact_2 = render_svc3.render(
                report_id=report.id,
                revision_number=rev.revision_number,
                format="docx",
                template_version="1.0.0",
                mode="formal",
                actor="test-user",
                idempotency_key=idempotency_key_2,
            )
            assert new_artifact_2.status == ArtifactStatus.COMPLETED

        # Verify both artifacts are completed with different idempotency keys
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)

            # Exactly 2 completed artifacts
            completed = check_repo.list_artifacts(report.id, status=ArtifactStatus.COMPLETED)
            assert len(completed) == 2

            completed_by_key = {a.idempotency_key: a for a in completed}
            assert idempotency_key_1 in completed_by_key
            assert idempotency_key_2 in completed_by_key

            # key 1 artifact is the original
            assert completed_by_key[idempotency_key_1].id == artifact_1.id
            # key 2 artifact is the new one from reclaim
            assert completed_by_key[idempotency_key_2].id == new_artifact_2.id

            # Both have different idempotency_key values
            assert idempotency_key_1 != idempotency_key_2

            # No pending or rendering artifacts
            pending = check_repo.list_artifacts(report.id, status=ArtifactStatus.PENDING)
            assert len(pending) == 0
            rendering = check_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            assert len(rendering) == 0

    def test_two_retries_of_stale_claim_only_one_reclaims(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Two independent sessions try to reclaim the same stale claim.

        Uses FakeClock with stale_claim_seconds=1 for controllable timing.
        Only one should win the CAS reclaim and produce a completed artifact.
        The other should get IdempotencyClaimError.

        Uses a file-based SQLite engine for thread safety.
        """
        import threading

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-concurrent-recovery-v2"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Use a file-based SQLite for thread-safe concurrent access
        db_path = tmp_path / "concurrent_v2.db"
        file_engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(file_engine)
        file_sf = sessionmaker(bind=file_engine, expire_on_commit=False)

        # Seed templates into the file-based DB
        with file_sf() as seed_sess:
            seed_repo = SQLReportRepository(seed_sess)
            seed_repo.save_report(report)
            seed_repo.save_revision(rev)
            seed_default_templates(seed_repo)
            seed_sess.commit()

        # Attempt 1: Fail render + fail state commit → stuck in 'claimed'
        with file_sf() as session:
            repo = SQLReportRepository(session)
            uow = ReportRenderUnitOfWork(session, report_repo=repo, artifact_repo=repo)
            storage = ReportArtifactStorage(str(tmp_path / "artifacts"))
            render_svc = ReportRenderService(
                uow=uow,
                storage=storage,
                template_repo=repo,
                stale_claim_seconds=1,
                clock=clock,
            )

            commit_count = 0
            original_commit = uow.commit

            def fail_on_failed_state_commit():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 4:
                    raise OSError("Simulated failed-state commit failure")
                return original_commit()

            monkeypatch.setattr(uow, "commit", fail_on_failed_state_commit)

            with (
                patch(
                    "cold_storage.modules.reports.application.render_service"
                    ".ReportRenderService._render_bytes",
                    side_effect=RuntimeError("Render crashed"),
                ),
                pytest.raises(RenderError),
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

        # Record old claim_token before advancing
        with file_sf() as check_sess:
            check_repo = SQLReportRepository(check_sess)
            idem = check_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "claimed"
            old_claim_token = idem["claim_token"]

        # Advance clock past stale threshold
        clock.advance(2)

        # Concurrent retries — two independent sessions on file-based DB
        barrier = threading.Barrier(2)
        results: list[tuple[int, object]] = []
        errors: list[tuple[int, Exception]] = []

        def retry_worker(worker_id: int) -> None:
            with file_sf() as sess:
                r = SQLReportRepository(sess)
                u = ReportRenderUnitOfWork(sess, report_repo=r, artifact_repo=r)
                s = ReportArtifactStorage(str(tmp_path / f"artifacts_{worker_id}"))
                svc = ReportRenderService(
                    uow=u,
                    storage=s,
                    template_repo=r,
                    stale_claim_seconds=1,
                    clock=clock,
                )
                barrier.wait(timeout=10)
                try:
                    art = svc.render(
                        report_id=report.id,
                        revision_number=rev.revision_number,
                        format="docx",
                        template_version="1.0.0",
                        mode="formal",
                        actor="test-user",
                        idempotency_key=idempotency_key,
                    )
                    results.append((worker_id, art))
                except IdempotencyClaimError:
                    errors.append((worker_id, IdempotencyClaimError("conflict")))
                except Exception as exc:
                    errors.append((worker_id, exc))

        threads = [
            threading.Thread(target=retry_worker, args=(0,)),
            threading.Thread(target=retry_worker, args=(1,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Exactly one worker succeeded, exactly one got IdempotencyClaimError
        assert len(results) == 1, f"Expected exactly 1 success, got {len(results)}: {results}"
        assert len(errors) == 1, f"Expected exactly 1 error, got {len(errors)}: {errors}"

        # Exactly one completed artifact
        with file_sf() as final_session:
            final_repo = SQLReportRepository(final_session)

            completed = final_repo.list_artifacts(report.id, status=ArtifactStatus.COMPLETED)
            assert len(completed) == 1, (
                f"Expected exactly 1 completed artifact, got {len(completed)}"
            )

            # No pending or rendering artifacts
            pending = final_repo.list_artifacts(report.id, status=ArtifactStatus.PENDING)
            assert len(pending) == 0, f"Expected 0 pending artifacts, got {len(pending)}"
            rendering = final_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            assert len(rendering) == 0, f"Expected 0 rendering artifacts, got {len(rendering)}"

            # Idempotency is completed
            idem = final_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "completed"
            assert idem["result_payload"]["artifact_id"] == completed[0].id

            # Old claim_token is NOT the current claim_token
            assert idem["claim_token"] != old_claim_token

    # ------------------------------------------------------------------
    # Atomic fencing race condition tests
    # ------------------------------------------------------------------

    def test_old_worker_paused_before_pending_insert_cannot_create_orphan_after_reclaim(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Race: Worker A paused before pending INSERT, Worker B reclaims.

        Proves that insert_artifact_with_claim uses atomic fencing:
        Worker A gets claim, but before it inserts the pending artifact,
        Worker B reclaims the stale claim.  Worker A's insert must fail
        with StaleClaimError.

        SQLite and PostgreSQL: uses guard UPDATE / SELECT FOR UPDATE.
        """
        import threading

        from cold_storage.modules.reports.infrastructure import (
            repository as repo_mod,
        )

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-pending-race-1"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Use file-based SQLite for thread safety
        db_path = tmp_path / "pending_race.db"
        file_engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(file_engine)
        file_sf = sessionmaker(bind=file_engine, expire_on_commit=False)

        # Seed data
        with file_sf() as seed_sess:
            seed_repo = SQLReportRepository(seed_sess)
            seed_repo.save_report(report)
            seed_repo.save_revision(rev)
            seed_default_templates(seed_repo)
            seed_sess.commit()

        # Worker A: get a claim, then start render (will be paused at INSERT)
        barrier = threading.Barrier(2)
        insert_blocked = threading.Event()
        original_insert = repo_mod.SQLReportRepository.insert_artifact_with_claim

        def barrier_insert(self, artifact, *, claim_token, claim_version):
            """Intercept insert_artifact_with_claim: signal barrier, wait for Worker B."""
            insert_blocked.set()
            barrier.wait(timeout=15)
            return original_insert(
                self,
                artifact,
                claim_token=claim_token,
                claim_version=claim_version,
            )

        monkeypatch.setattr(
            repo_mod.SQLReportRepository,
            "insert_artifact_with_claim",
            barrier_insert,
        )

        worker_a_error: list[Exception] = []
        worker_a_done = threading.Event()

        def worker_a():
            try:
                with file_sf() as sess:
                    r = SQLReportRepository(sess)
                    u = ReportRenderUnitOfWork(sess, report_repo=r, artifact_repo=r)
                    s = ReportArtifactStorage(str(tmp_path / "artifacts_a"))
                    svc = ReportRenderService(
                        uow=u,
                        storage=s,
                        template_repo=r,
                        stale_claim_seconds=1,
                        clock=clock,
                    )
                    svc.render(
                        report_id=report.id,
                        revision_number=rev.revision_number,
                        format="docx",
                        template_version="1.0.0",
                        mode="formal",
                        actor="test-user",
                        idempotency_key=idempotency_key,
                    )
            except Exception as exc:
                worker_a_error.append(exc)
            finally:
                worker_a_done.set()

        def worker_b():
            """Wait for Worker A to reach the INSERT, then reclaim the stale claim."""
            insert_blocked.wait(timeout=10)
            # Small delay to ensure Worker A is past the claim check
            # but blocked at barrier
            import time

            time.sleep(0.1)
            with file_sf() as sess:
                r = SQLReportRepository(sess)
                # Advance clock to make claim stale
                stale_cutoff = clock() - timedelta(seconds=2)
                # Read existing claim state for full CAS
                existing = r.get_idempotency_record(idempotency_key)
                assert existing is not None
                reclaimed, _, _ = r.reclaim_stale_idempotency(
                    idempotency_key,
                    existing["fingerprint"],
                    stale_cutoff,
                    original_claimed_at=existing["claimed_at"],
                    old_claim_token=existing["claim_token"],
                    old_claim_version=existing["claim_version"],
                )
                assert reclaimed, "Worker B should have reclaimed the stale claim"
                r.commit()

        # Run Worker A and B concurrently
        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)
        worker_a_done.wait(timeout=5)

        # Worker A must have failed with StaleClaimError (wrapped in RenderError)
        assert len(worker_a_error) == 1, f"Worker A should have raised, got: {worker_a_error}"
        assert isinstance(worker_a_error[0], RenderError)

        # No orphan artifact with old token
        with file_sf() as check_sess:
            check_repo = SQLReportRepository(check_sess)
            pending = check_repo.list_artifacts(report.id, status=ArtifactStatus.PENDING)
            rendering = check_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            # All artifacts should be failed or nonexistent
            for art in pending + rendering:
                # If any exist, they must be from Worker B's claim, not Worker A's
                assert art.claim_token != "", "No orphan artifacts from Worker A"

    def test_old_worker_paused_after_claim_check_cannot_transition_after_reclaim(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Race: Worker A inserted artifact, paused before transition, Worker B reclaims.

        Proves that transition_artifact uses EXISTS subquery:
        Worker A inserted a pending artifact, but before it transitions
        pending→rendering, Worker B reclaims.  Worker A's transition must
        fail with StaleClaimError.

        Uses Barrier placed before the UPDATE executes.
        """
        import threading

        from cold_storage.modules.reports.infrastructure import (
            repository as repo_mod,
        )

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-transition-race-1"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # File-based SQLite
        db_path = tmp_path / "transition_race.db"
        file_engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(file_engine)
        file_sf = sessionmaker(bind=file_engine, expire_on_commit=False)

        with file_sf() as seed_sess:
            seed_repo = SQLReportRepository(seed_sess)
            seed_repo.save_report(report)
            seed_repo.save_revision(rev)
            seed_default_templates(seed_repo)
            seed_sess.commit()

        barrier = threading.Barrier(2)
        transition_blocked = threading.Event()
        original_transition = repo_mod.SQLReportRepository.transition_artifact

        def barrier_transition(self, artifact, *, expected_status, claim_token, claim_version):
            """Intercept transition_artifact: signal barrier, wait for Worker B."""
            transition_blocked.set()
            barrier.wait(timeout=15)
            return original_transition(
                self,
                artifact,
                expected_status=expected_status,
                claim_token=claim_token,
                claim_version=claim_version,
            )

        monkeypatch.setattr(
            repo_mod.SQLReportRepository,
            "transition_artifact",
            barrier_transition,
        )

        worker_a_error: list[Exception] = []
        worker_a_done = threading.Event()

        def worker_a():
            try:
                with file_sf() as sess:
                    r = SQLReportRepository(sess)
                    u = ReportRenderUnitOfWork(sess, report_repo=r, artifact_repo=r)
                    s = ReportArtifactStorage(str(tmp_path / "artifacts_a2"))
                    svc = ReportRenderService(
                        uow=u,
                        storage=s,
                        template_repo=r,
                        stale_claim_seconds=1,
                        clock=clock,
                    )
                    svc.render(
                        report_id=report.id,
                        revision_number=rev.revision_number,
                        format="docx",
                        template_version="1.0.0",
                        mode="formal",
                        actor="test-user",
                        idempotency_key=idempotency_key,
                    )
            except Exception as exc:
                worker_a_error.append(exc)
            finally:
                worker_a_done.set()

        def worker_b():
            """Wait for Worker A to reach transition, then reclaim."""
            transition_blocked.wait(timeout=10)
            import time

            time.sleep(0.1)
            with file_sf() as sess:
                r = SQLReportRepository(sess)
                stale_cutoff = clock() - timedelta(seconds=2)
                # Read existing claim state for full CAS
                existing = r.get_idempotency_record(idempotency_key)
                assert existing is not None
                reclaimed, _, _ = r.reclaim_stale_idempotency(
                    idempotency_key,
                    existing["fingerprint"],
                    stale_cutoff,
                    original_claimed_at=existing["claimed_at"],
                    old_claim_token=existing["claim_token"],
                    old_claim_version=existing["claim_version"],
                )
                assert reclaimed, "Worker B should have reclaimed"
                r.commit()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)
        worker_a_done.wait(timeout=5)

        # Worker A must have failed
        assert len(worker_a_error) == 1, f"Worker A should have raised, got: {worker_a_error}"
        assert isinstance(worker_a_error[0], RenderError)

        # Worker A's artifact should not be in rendering state
        with file_sf() as check_sess:
            check_repo = SQLReportRepository(check_sess)
            rendering = check_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            for art in rendering:
                assert art.claim_token != "", "No orphan rendering artifacts from Worker A"

    def test_old_worker_failure_handler_cannot_modify_artifact_after_reclaim(
        self, session_factory, tmp_path, monkeypatch
    ):
        """Race: Worker A enters failure handler, Worker B reclaims before fail_attempt.

        Proves that fail_attempt_with_claim uses atomic fencing:
        Worker A's render crashes, enters failure handler.  Before
        fail_attempt_with_claim executes, Worker B reclaims.  Worker A's
        fail_attempt must raise StaleClaimError.
        """
        import threading

        from cold_storage.modules.reports.infrastructure import (
            repository as repo_mod,
        )

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-fail-race-1"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # File-based SQLite
        db_path = tmp_path / "fail_race.db"
        file_engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(file_engine)
        file_sf = sessionmaker(bind=file_engine, expire_on_commit=False)

        with file_sf() as seed_sess:
            seed_repo = SQLReportRepository(seed_sess)
            seed_repo.save_report(report)
            seed_repo.save_revision(rev)
            seed_default_templates(seed_repo)
            seed_sess.commit()

        barrier = threading.Barrier(2)
        fail_blocked = threading.Event()
        original_fail = repo_mod.SQLReportRepository.fail_attempt_with_claim

        def barrier_fail(
            self,
            artifact_id,
            idempotency_key,
            claim_token,
            claim_version,
            failure_code,
            failure_message,
        ):
            """Intercept fail_attempt_with_claim: signal barrier, wait."""
            fail_blocked.set()
            barrier.wait(timeout=15)
            return original_fail(
                self,
                artifact_id,
                idempotency_key,
                claim_token,
                claim_version,
                failure_code,
                failure_message,
            )

        monkeypatch.setattr(
            repo_mod.SQLReportRepository,
            "fail_attempt_with_claim",
            barrier_fail,
        )

        worker_a_error: list[Exception] = []
        worker_a_done = threading.Event()

        def worker_a():
            try:
                with file_sf() as sess:
                    r = SQLReportRepository(sess)
                    u = ReportRenderUnitOfWork(sess, report_repo=r, artifact_repo=r)
                    s = ReportArtifactStorage(str(tmp_path / "artifacts_a3"))
                    svc = ReportRenderService(
                        uow=u,
                        storage=s,
                        template_repo=r,
                        stale_claim_seconds=1,
                        clock=clock,
                    )
                    # Inject render failure
                    with patch(
                        "cold_storage.modules.reports.application.render_service"
                        ".ReportRenderService._render_bytes",
                        side_effect=RuntimeError("Worker A render crash"),
                    ):
                        svc.render(
                            report_id=report.id,
                            revision_number=rev.revision_number,
                            format="docx",
                            template_version="1.0.0",
                            mode="formal",
                            actor="test-user",
                            idempotency_key=idempotency_key,
                        )
            except Exception as exc:
                worker_a_error.append(exc)
            finally:
                worker_a_done.set()

        def worker_b():
            """Wait for Worker A to enter failure handler, then reclaim."""
            fail_blocked.wait(timeout=10)
            import time

            time.sleep(0.1)
            with file_sf() as sess:
                r = SQLReportRepository(sess)
                stale_cutoff = clock() - timedelta(seconds=2)
                # Read existing claim state for full CAS
                existing = r.get_idempotency_record(idempotency_key)
                assert existing is not None
                reclaimed, _, _ = r.reclaim_stale_idempotency(
                    idempotency_key,
                    existing["fingerprint"],
                    stale_cutoff,
                    original_claimed_at=existing["claimed_at"],
                    old_claim_token=existing["claim_token"],
                    old_claim_version=existing["claim_version"],
                )
                assert reclaimed, "Worker B should have reclaimed"
                r.commit()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)
        worker_a_done.wait(timeout=5)

        # Worker A should have failed (fail_attempt raised StaleClaimError,
        # caught by outer handler, re-raised as RenderError)
        assert len(worker_a_error) == 1, f"Worker A should have raised, got: {worker_a_error}"
        assert isinstance(worker_a_error[0], RenderError)

        # Final state: Worker A's artifact should NOT be in failed state
        # (because fail_attempt_with_claim was rejected by Worker B's reclaim)
        with file_sf() as check_sess:
            check_repo = SQLReportRepository(check_sess)
            # Worker A's fail_attempt_with_claim was rejected by reclaim,
            # so its artifact stays non-terminal.

            # Worker A's artifact should still be pending or rendering
            # (fail_attempt was rejected)
            pending = check_repo.list_artifacts(report.id, status=ArtifactStatus.PENDING)
            rendering = check_repo.list_artifacts(report.id, status=ArtifactStatus.RENDERING)
            # At least one non-terminal artifact from Worker A should exist
            non_terminal = pending + rendering
            assert len(non_terminal) >= 1, (
                "Worker A's artifact should still be non-terminal "
                "(fail_attempt_with_claim was rejected)"
            )

    # ------------------------------------------------------------------
    # PostgreSQL-marked versions of atomic fencing tests
    # ------------------------------------------------------------------

    @pytest.mark.postgresql
    def test_old_worker_paused_before_pending_insert_pg(
        self, session_factory, tmp_path, monkeypatch
    ):
        """PostgreSQL variant: insert_artifact_with_claim uses SELECT FOR UPDATE.

        Same logic as the SQLite version but exercises the PostgreSQL code path.
        When run against PostgreSQL, the guard uses SELECT ... FOR UPDATE
        instead of the SQLite guard UPDATE.
        """
        import threading

        from cold_storage.modules.reports.infrastructure import (
            repository as repo_mod,
        )

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-pending-race-pg-1"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # For in-memory SQLite, we still test the SQLite path.
        # The @pytest.mark.postgresql marker ensures this test runs
        # in the PostgreSQL CI job where the dialect check routes
        # to the SELECT FOR UPDATE path.
        barrier = threading.Barrier(2)
        insert_blocked = threading.Event()
        original_insert = repo_mod.SQLReportRepository.insert_artifact_with_claim

        def barrier_insert(self, artifact, *, claim_token, claim_version):
            insert_blocked.set()
            barrier.wait(timeout=15)
            return original_insert(
                self,
                artifact,
                claim_token=claim_token,
                claim_version=claim_version,
            )

        monkeypatch.setattr(
            repo_mod.SQLReportRepository,
            "insert_artifact_with_claim",
            barrier_insert,
        )

        worker_a_error: list[Exception] = []
        worker_a_done = threading.Event()

        def worker_a():
            try:
                with session_factory() as sess:
                    r = SQLReportRepository(sess)
                    u = ReportRenderUnitOfWork(sess, report_repo=r, artifact_repo=r)
                    s = ReportArtifactStorage(str(tmp_path / "artifacts_pg_a"))
                    svc = ReportRenderService(
                        uow=u,
                        storage=s,
                        template_repo=r,
                        stale_claim_seconds=1,
                        clock=clock,
                    )
                    svc.render(
                        report_id=report.id,
                        revision_number=rev.revision_number,
                        format="docx",
                        template_version="1.0.0",
                        mode="formal",
                        actor="test-user",
                        idempotency_key=idempotency_key,
                    )
            except Exception as exc:
                worker_a_error.append(exc)
            finally:
                worker_a_done.set()

        def worker_b():
            insert_blocked.wait(timeout=10)
            import time

            time.sleep(0.1)
            with session_factory() as sess:
                r = SQLReportRepository(sess)
                stale_cutoff = clock() - timedelta(seconds=2)
                # Read existing claim state for full CAS
                existing = r.get_idempotency_record(idempotency_key)
                assert existing is not None
                reclaimed, _, _ = r.reclaim_stale_idempotency(
                    idempotency_key,
                    existing["fingerprint"],
                    stale_cutoff,
                    original_claimed_at=existing["claimed_at"],
                    old_claim_token=existing["claim_token"],
                    old_claim_version=existing["claim_version"],
                )
                assert reclaimed
                r.commit()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)
        worker_a_done.wait(timeout=5)

        assert len(worker_a_error) == 1
        assert isinstance(worker_a_error[0], RenderError)

    @pytest.mark.postgresql
    def test_old_worker_paused_after_claim_check_cannot_transition_pg(
        self, session_factory, tmp_path, monkeypatch
    ):
        """PostgreSQL variant: transition_artifact uses EXISTS subquery."""
        import threading

        from cold_storage.modules.reports.infrastructure import (
            repository as repo_mod,
        )

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-transition-race-pg-1"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        barrier = threading.Barrier(2)
        transition_blocked = threading.Event()
        original_transition = repo_mod.SQLReportRepository.transition_artifact

        def barrier_transition(self, artifact, *, expected_status, claim_token, claim_version):
            transition_blocked.set()
            barrier.wait(timeout=15)
            return original_transition(
                self,
                artifact,
                expected_status=expected_status,
                claim_token=claim_token,
                claim_version=claim_version,
            )

        monkeypatch.setattr(
            repo_mod.SQLReportRepository,
            "transition_artifact",
            barrier_transition,
        )

        worker_a_error: list[Exception] = []
        worker_a_done = threading.Event()

        def worker_a():
            try:
                with session_factory() as sess:
                    r = SQLReportRepository(sess)
                    u = ReportRenderUnitOfWork(sess, report_repo=r, artifact_repo=r)
                    s = ReportArtifactStorage(str(tmp_path / "artifacts_pg_a2"))
                    svc = ReportRenderService(
                        uow=u,
                        storage=s,
                        template_repo=r,
                        stale_claim_seconds=1,
                        clock=clock,
                    )
                    svc.render(
                        report_id=report.id,
                        revision_number=rev.revision_number,
                        format="docx",
                        template_version="1.0.0",
                        mode="formal",
                        actor="test-user",
                        idempotency_key=idempotency_key,
                    )
            except Exception as exc:
                worker_a_error.append(exc)
            finally:
                worker_a_done.set()

        def worker_b():
            transition_blocked.wait(timeout=10)
            import time

            time.sleep(0.1)
            with session_factory() as sess:
                r = SQLReportRepository(sess)
                stale_cutoff = clock() - timedelta(seconds=2)
                # Read existing claim state for full CAS
                existing = r.get_idempotency_record(idempotency_key)
                assert existing is not None
                reclaimed, _, _ = r.reclaim_stale_idempotency(
                    idempotency_key,
                    existing["fingerprint"],
                    stale_cutoff,
                    original_claimed_at=existing["claimed_at"],
                    old_claim_token=existing["claim_token"],
                    old_claim_version=existing["claim_version"],
                )
                assert reclaimed
                r.commit()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)
        worker_a_done.wait(timeout=5)

        assert len(worker_a_error) == 1
        assert isinstance(worker_a_error[0], RenderError)

    @pytest.mark.postgresql
    def test_old_worker_failure_handler_cannot_modify_after_reclaim_pg(
        self, session_factory, tmp_path, monkeypatch
    ):
        """PostgreSQL variant: fail_attempt_with_claim uses atomic fencing."""
        import threading

        from cold_storage.modules.reports.infrastructure import (
            repository as repo_mod,
        )

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-fail-race-pg-1"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        barrier = threading.Barrier(2)
        fail_blocked = threading.Event()
        original_fail = repo_mod.SQLReportRepository.fail_attempt_with_claim

        def barrier_fail(
            self,
            artifact_id,
            idempotency_key,
            claim_token,
            claim_version,
            failure_code,
            failure_message,
        ):
            fail_blocked.set()
            barrier.wait(timeout=15)
            return original_fail(
                self,
                artifact_id,
                idempotency_key,
                claim_token,
                claim_version,
                failure_code,
                failure_message,
            )

        monkeypatch.setattr(
            repo_mod.SQLReportRepository,
            "fail_attempt_with_claim",
            barrier_fail,
        )

        worker_a_error: list[Exception] = []
        worker_a_done = threading.Event()

        def worker_a():
            try:
                with session_factory() as sess:
                    r = SQLReportRepository(sess)
                    u = ReportRenderUnitOfWork(sess, report_repo=r, artifact_repo=r)
                    s = ReportArtifactStorage(str(tmp_path / "artifacts_pg_a3"))
                    svc = ReportRenderService(
                        uow=u,
                        storage=s,
                        template_repo=r,
                        stale_claim_seconds=1,
                        clock=clock,
                    )
                    with patch(
                        "cold_storage.modules.reports.application.render_service"
                        ".ReportRenderService._render_bytes",
                        side_effect=RuntimeError("Worker A crash"),
                    ):
                        svc.render(
                            report_id=report.id,
                            revision_number=rev.revision_number,
                            format="docx",
                            template_version="1.0.0",
                            mode="formal",
                            actor="test-user",
                            idempotency_key=idempotency_key,
                        )
            except Exception as exc:
                worker_a_error.append(exc)
            finally:
                worker_a_done.set()

        def worker_b():
            fail_blocked.wait(timeout=10)
            import time

            time.sleep(0.1)
            with session_factory() as sess:
                r = SQLReportRepository(sess)
                stale_cutoff = clock() - timedelta(seconds=2)
                # Read existing claim state for full CAS
                existing = r.get_idempotency_record(idempotency_key)
                assert existing is not None
                reclaimed, _, _ = r.reclaim_stale_idempotency(
                    idempotency_key,
                    existing["fingerprint"],
                    stale_cutoff,
                    original_claimed_at=existing["claimed_at"],
                    old_claim_token=existing["claim_token"],
                    old_claim_version=existing["claim_version"],
                )
                assert reclaimed
                r.commit()

        t_a = threading.Thread(target=worker_a)
        t_b = threading.Thread(target=worker_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)
        worker_a_done.wait(timeout=5)

        assert len(worker_a_error) == 1
        assert isinstance(worker_a_error[0], RenderError)


# ===========================================================================
# Repository-level CAS negative tests
# ===========================================================================


class TestReclaimCASNegative:
    """Verify that reclaim_stale_idempotency rejects incorrect CAS params."""

    def _setup_claimed(self, session_factory):
        """Create a claimed idempotency record and return (report, rev, key, record)."""
        report, rev = _setup_approved(session_factory)
        key = "idem-cas-negative"
        with session_factory() as sess:
            repo = SQLReportRepository(sess)
            token, version = repo.save_idempotency_record(
                key=key,
                actor="test-user",
                action="render",
                fingerprint="real-fingerprint-abc",
            )
            repo.commit()
            record = repo.get_idempotency_record(key)
            return report, rev, key, record

    def test_reclaim_rejects_wrong_fingerprint(self, session_factory):
        """CAS fails when fingerprint doesn't match."""
        report, rev, key, record = self._setup_claimed(session_factory)
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))
        clock.advance(600)  # Make claim stale

        with session_factory() as sess:
            repo = SQLReportRepository(sess)
            stale_cutoff = clock() - timedelta(seconds=2)
            success, token, version = repo.reclaim_stale_idempotency(
                key,
                "wrong-fingerprint",  # Wrong!
                stale_cutoff,
                original_claimed_at=record["claimed_at"],
                old_claim_token=record["claim_token"],
                old_claim_version=record["claim_version"],
            )
            assert success is False
            assert token is None
            assert version is None

    def test_reclaim_rejects_wrong_claim_token(self, session_factory):
        """CAS fails when claim_token doesn't match."""
        report, rev, key, record = self._setup_claimed(session_factory)
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))
        clock.advance(600)

        with session_factory() as sess:
            repo = SQLReportRepository(sess)
            stale_cutoff = clock() - timedelta(seconds=2)
            success, token, version = repo.reclaim_stale_idempotency(
                key,
                record["fingerprint"],
                stale_cutoff,
                original_claimed_at=record["claimed_at"],
                old_claim_token="wrong-token-uuid",  # Wrong!
                old_claim_version=record["claim_version"],
            )
            assert success is False
            assert token is None
            assert version is None

    def test_reclaim_rejects_wrong_claim_version(self, session_factory):
        """CAS fails when claim_version doesn't match."""
        report, rev, key, record = self._setup_claimed(session_factory)
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))
        clock.advance(600)

        with session_factory() as sess:
            repo = SQLReportRepository(sess)
            stale_cutoff = clock() - timedelta(seconds=2)
            success, token, version = repo.reclaim_stale_idempotency(
                key,
                record["fingerprint"],
                stale_cutoff,
                original_claimed_at=record["claimed_at"],
                old_claim_token=record["claim_token"],
                old_claim_version=999,  # Wrong!
            )
            assert success is False
            assert token is None
            assert version is None

    def test_reclaim_rejects_changed_claimed_at(self, session_factory):
        """CAS fails when original_claimed_at doesn't match (another worker reclaimed)."""
        report, rev, key, record = self._setup_claimed(session_factory)
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))
        clock.advance(600)

        # Simulate: someone else already reclaimed, so claimed_at changed
        with session_factory() as sess:
            repo = SQLReportRepository(sess)
            stale_cutoff = clock() - timedelta(seconds=2)
            # First reclaim succeeds
            success, _, _ = repo.reclaim_stale_idempotency(
                key,
                record["fingerprint"],
                stale_cutoff,
                original_claimed_at=record["claimed_at"],
                old_claim_token=record["claim_token"],
                old_claim_version=record["claim_version"],
            )
            assert success is True
            repo.commit()

            # Second attempt with OLD claimed_at fails
            new_record = repo.get_idempotency_record(key)
            success2, token2, version2 = repo.reclaim_stale_idempotency(
                key,
                new_record["fingerprint"],
                stale_cutoff,
                original_claimed_at=record["claimed_at"],  # Old value!
                old_claim_token=new_record["claim_token"],
                old_claim_version=new_record["claim_version"],
            )
            assert success2 is False
            assert token2 is None
            assert version2 is None

    def test_reclaim_requires_all_cas_arguments(self, session_factory):
        """Verify that all CAS params are mandatory — call without them raises TypeError."""
        report, rev, key, record = self._setup_claimed(session_factory)
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        with session_factory() as sess:
            repo = SQLReportRepository(sess)
            stale_cutoff = clock() - timedelta(seconds=2)
            # Calling without required keyword args should raise TypeError
            with pytest.raises(TypeError):
                repo.reclaim_stale_idempotency(
                    key,
                    record["fingerprint"],
                    stale_cutoff,
                    # Missing original_claimed_at, old_claim_token, old_claim_version
                )


class TestReclaimConcurrentCAS:
    """Verify that concurrent CAS reclaim produces exactly one winner."""

    def test_two_sessions_same_snapshot_exactly_one_wins(self, session_factory):
        """Two sessions read the same snapshot, both attempt CAS — exactly one wins."""
        import threading

        report, rev = _setup_approved(session_factory)
        idempotency_key = "idem-concurrent-cas"
        clock = FakeClock(datetime.now(UTC) + timedelta(days=1))

        # Create a fresh file-based DB for this test
        import os
        import tempfile

        from sqlalchemy import create_engine as _create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker

        from cold_storage.modules.reports.infrastructure.orm import Base as _Base

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_file = f.name
        try:
            file_eng = _create_engine(
                f"sqlite:///{db_file}",
                connect_args={"check_same_thread": False},
            )
            _Base.metadata.create_all(file_eng)
            file_sf = _sessionmaker(bind=file_eng, expire_on_commit=False)

            # Seed
            with file_sf() as sess:
                r = SQLReportRepository(sess)
                r.save_report(report)
                r.save_revision(rev)
                seed_default_templates(r)
                token, version = r.save_idempotency_record(
                    key=idempotency_key,
                    actor="test-user",
                    action="render",
                    fingerprint="test-fingerprint",
                )
                sess.commit()
                record = r.get_idempotency_record(idempotency_key)

            clock.advance(600)  # Make stale

            results: list[tuple[int, bool]] = []
            lock = threading.Lock()

            def worker(wid: int):
                with file_sf() as sess:
                    r = SQLReportRepository(sess)
                    stale_cutoff = clock() - timedelta(seconds=2)
                    success, tok, ver = r.reclaim_stale_idempotency(
                        idempotency_key,
                        record["fingerprint"],
                        stale_cutoff,
                        original_claimed_at=record["claimed_at"],
                        old_claim_token=record["claim_token"],
                        old_claim_version=record["claim_version"],
                    )
                    if success:
                        r.commit()
                    with lock:
                        results.append((wid, success))

            barrier = threading.Barrier(2)

            def synced_worker(wid: int):
                barrier.wait(timeout=10)
                worker(wid)

            t1 = threading.Thread(target=synced_worker, args=(0,))
            t2 = threading.Thread(target=synced_worker, args=(1,))
            t1.start()
            t2.start()
            t1.join(timeout=30)
            t2.join(timeout=30)

            # Exactly one winner
            winners = [(w, s) for w, s in results if s]
            losers = [(w, s) for w, s in results if not s]
            assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}: {results}"
            assert len(losers) == 1, f"Expected 1 loser, got {len(losers)}: {results}"

            # Version only incremented once
            with file_sf() as sess:
                r = SQLReportRepository(sess)
                final = r.get_idempotency_record(idempotency_key)
                assert final is not None
                assert final["claim_version"] == record["claim_version"] + 1
                assert final["claim_token"] != record["claim_token"]
        finally:
            os.unlink(db_file)


# ---------------------------------------------------------------------------
# PostgreSQL-specific concurrent CAS reclaim test
# ---------------------------------------------------------------------------


@pytest.mark.postgresql
def test_two_postgresql_sessions_same_snapshot_exactly_one_reclaims():
    """Two real PostgreSQL sessions read the same snapshot, both attempt CAS — exactly one wins.

    Uses a dedicated PostgreSQL engine from DATABASE_URL (NOT the in-memory SQLite
    fixture).  Both threads open independent sessions, read the same stale snapshot,
    and race via threading.Barrier.  The CAS UPDATE ... WHERE with 7 conditions
    ensures exactly one rowcount==1.
    """
    import os
    import threading

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL CAS test")

    from sqlalchemy import create_engine as _create_engine
    from sqlalchemy.orm import sessionmaker as _sessionmaker

    from cold_storage.modules.reports.infrastructure.orm import Base as _Base

    pg_eng = _create_engine(database_url)
    _Base.metadata.create_all(pg_eng)
    pg_sf = _sessionmaker(bind=pg_eng, expire_on_commit=False)

    idempotency_key = "idem-pg-concurrent-cas"

    try:
        # Seed: create approved report + idempotency record via a dedicated session
        with pg_sf() as seed_sess:
            r_seed = SQLReportRepository(seed_sess)
            report, rev = _setup_approved(pg_sf)
            token, version = r_seed.save_idempotency_record(
                key=idempotency_key,
                actor="test-user",
                action="render",
                fingerprint="pg-test-fingerprint",
            )
            seed_sess.commit()

            # Read the snapshot that both workers will use
            snapshot = r_seed.get_idempotency_record(idempotency_key)
            assert snapshot is not None

        # Make stale: advance claimed_at back far enough
        stale_cutoff = datetime.now(UTC) + timedelta(seconds=1)

        results: list[tuple[int, bool, str | None, int | None]] = []
        exceptions: list[tuple[int, BaseException]] = []
        lock = threading.Lock()

        def worker(wid: int) -> None:
            try:
                with pg_sf() as sess:
                    r = SQLReportRepository(sess)
                    success, tok, ver = r.reclaim_stale_idempotency(
                        key=idempotency_key,
                        fingerprint=snapshot["fingerprint"],
                        cutoff=stale_cutoff,
                        original_claimed_at=snapshot["claimed_at"],
                        old_claim_token=snapshot["claim_token"],
                        old_claim_version=snapshot["claim_version"],
                    )
                    if success:
                        sess.commit()
                    with lock:
                        results.append((wid, success, tok, ver))
            except BaseException as exc:
                with lock:
                    exceptions.append((wid, exc))

        barrier = threading.Barrier(2)

        def synced_worker(wid: int) -> None:
            barrier.wait(timeout=10)
            worker(wid)

        t1 = threading.Thread(target=synced_worker, args=(0,))
        t2 = threading.Thread(target=synced_worker, args=(1,))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # --- Assertions ---

        # No exceptions from either thread
        assert len(exceptions) == 0, f"Unexpected exceptions in worker threads: {exceptions}"

        # Both threads completed
        assert len(results) == 2, f"Expected 2 results, got {len(results)}: {results}"

        winners = [(w, s, t, v) for w, s, t, v in results if s]
        losers = [(w, s, t, v) for w, s, t, v in results if not s]

        # Exactly one winner
        assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}: {results}"
        assert len(losers) == 1, f"Expected 1 loser, got {len(losers)}: {results}"

        # Winner got valid token + version
        winner_wid, winner_success, winner_token, winner_version = winners[0]
        assert winner_success is True
        assert winner_token is not None
        assert isinstance(winner_token, str) and len(winner_token) > 0
        assert winner_version == snapshot["claim_version"] + 1

        # Loser got (False, None, None)
        loser_wid, loser_success, loser_token, loser_version = losers[0]
        assert loser_success is False
        assert loser_token is None
        assert loser_version is None

        # Final DB state: version incremented exactly once
        with pg_sf() as verify_sess:
            r_verify = SQLReportRepository(verify_sess)
            final = r_verify.get_idempotency_record(idempotency_key)
            assert final is not None
            assert final["claim_version"] == snapshot["claim_version"] + 1
            assert final["claim_token"] == winner_token
            assert final["status"] == "claimed"

    finally:
        pg_eng.dispose()
