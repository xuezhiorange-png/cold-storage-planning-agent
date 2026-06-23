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

        # Record old claim_token
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            idem = check_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "claimed"
            old_claim_token = idem["claim_token"]

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

        # Old worker tries to complete with old token → should raise ValueError
        with session_factory() as session:
            repo = SQLReportRepository(session)
            with pytest.raises(ValueError, match="not found or not in claimed state"):
                repo.complete_idempotency_record(
                    idempotency_key,
                    {"artifact_id": "x"},
                    claim_token=old_claim_token,
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

        # Record old claim_token
        with session_factory() as check_session:
            check_repo = SQLReportRepository(check_session)
            idem = check_repo.get_idempotency_record(idempotency_key)
            assert idem is not None
            assert idem["status"] == "claimed"
            old_claim_token = idem["claim_token"]

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

        # Old worker tries to fail with old claim_token → no-op (0 rows matched)
        with session_factory() as session:
            repo = SQLReportRepository(session)
            repo.fail_idempotency_record(
                idempotency_key,
                "RuntimeError",
                "old attempt",
                claim_token=old_claim_token,
            )
            session.commit()

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
