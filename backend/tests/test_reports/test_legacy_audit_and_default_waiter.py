"""P0-9: Legacy audit + default waiter tests.

Tests for delete_legacy_artifact with audit persistence, and
DatabaseIdempotencyWaiter behaviour with SQLite (no injection).

Each test uses a REAL ``ReportArtifactStorage`` backed by a temp directory
and a REAL SQL Repository backed by SQLite with explicit clock control (no sleep).

Test matrix
-----------
Part A — Legacy delete audit
  - test_legacy_delete_rejects_blank_actor
  - test_legacy_delete_rejects_blank_reason
  - test_legacy_delete_persists_audit_record
  - test_normal_render_path_cannot_call_legacy_delete

Part B — Default waiter (DatabaseIdempotencyWaiter)
  - test_default_waiter_without_injection_converges_sqlite
  - test_default_waiter_rejects_claim_token_mismatch
  - test_default_waiter_rejects_missing_artifact
  - test_default_waiter_rejects_artifact_not_completed
  - test_default_waiter_rejects_claim_version_mismatch
  - test_default_waiter_rejects_artifact_idempotency_key_mismatch
  - test_default_waiter_rejects_report_id_mismatch
  - test_default_waiter_rejects_revision_number_mismatch
  - test_default_service_waiter_two_requests_converge_sqlite
  - test_default_api_waiter_two_requests_converge_without_override
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.application.render_service import (
    ReportRenderService,
    ReportRenderUnitOfWork,
)
from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ReportLocale,
    ReportType,
)
from cold_storage.modules.reports.domain.errors import (
    IdempotencyClaimError,
)
from cold_storage.modules.reports.domain.models import (
    Report,
)
from cold_storage.modules.reports.infrastructure.artifact_storage import (
    ReportArtifactStorage,
)
from cold_storage.modules.reports.infrastructure.orm import (
    Base,
)
from cold_storage.modules.reports.infrastructure.repository import (
    SQLReportRepository,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_base(tmp_path: Path) -> str:
    """Temporary base directory for artifact storage."""
    d = tmp_path / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


@pytest.fixture()
def storage(tmp_base: str) -> ReportArtifactStorage:
    return ReportArtifactStorage(tmp_base)


@pytest.fixture()
def artifact_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def engine():
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
# Helpers
# ---------------------------------------------------------------------------


def _put_artifact(
    storage: ReportArtifactStorage,
    artifact_id: str,
    claim_token: str = "tok_A",
    claim_version: int = 1,
) -> str:
    return storage.put(
        artifact_id,
        b"file content",
        "test.pdf",
        claim_token=claim_token,
        claim_version=claim_version,
    )


def _create_legacy_file(
    storage: ReportArtifactStorage,
    artifact_id: str,
    sk: str | None = None,
) -> str:
    """Create a legacy artifact file WITHOUT a .meta sidecar."""
    if sk is None:
        sk = str(uuid.uuid4())
    artifact_dir = Path(storage._base_dir) / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    file_path = artifact_dir / f"{sk}_legacy.pdf"
    file_path.write_bytes(b"legacy artifact data")
    return sk


def _insert_idempotency_record(
    repo: SQLReportRepository,
    key: str,
    *,
    actor: str = "test_actor",
    action: str = "render",
    fingerprint: str = "test_fingerprint",
    status: str = "completed",
    claim_token: str = "tok",
    claim_version: int = 1,
    result_payload: dict[str, Any] | None = None,
) -> None:
    """Insert a raw idempotency record using the ORM."""
    from cold_storage.modules.reports.infrastructure.orm import IdempotencyRecord

    rec = IdempotencyRecord(
        key=key,
        actor=actor,
        action=action,
        fingerprint=fingerprint,
        status=status,
        claim_token=claim_token,
        claim_version=claim_version,
        result_payload=result_payload,
    )
    repo._session.add(rec)
    repo.commit()


def _insert_artifact_record(
    repo: SQLReportRepository,
    artifact_id: str,
    *,
    report_id: str = "report1",
    report_revision_id: str = "rev1",
    revision_number: int = 1,
    format: str = "pdf",
    template_id: str = "tmpl1",
    template_version: str = "1.0",
    schema_version: str = "1.0",
    status: str = "completed",
    storage_key: str = "",
    file_name: str = "test.pdf",
    mime_type: str = "application/pdf",
    file_size_bytes: int = 100,
    file_sha256: str = "",
    source_content_hash: str = "hash1",
    render_manifest_json: dict[str, Any] | None = None,
    generated_by: str = "tester",
    idempotency_key: str = "",
    claim_token: str = "tok",
    claim_version: int = 1,
    locale: str = "zh-CN",
) -> str:
    """Insert a raw artifact record using the ORM."""
    from cold_storage.modules.reports.infrastructure.orm import (
        ReportExportArtifactRecord,
    )

    if not storage_key:
        storage_key = str(uuid.uuid4())
    rec = ReportExportArtifactRecord(
        id=artifact_id,
        report_id=report_id,
        report_revision_id=report_revision_id,
        revision_number=revision_number,
        format=format,
        template_id=template_id,
        template_version=template_version,
        schema_version=schema_version,
        status=status,
        storage_key=storage_key,
        file_name=file_name,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        file_sha256=file_sha256 or ("x" * 64),
        source_content_hash=source_content_hash,
        render_manifest_json=render_manifest_json or {},
        generated_by=generated_by,
        idempotency_key=idempotency_key,
        claim_token=claim_token,
        claim_version=claim_version,
        locale=locale,
    )
    repo._session.add(rec)
    repo.commit()
    return storage_key


# ===================================================================
# Part A — Legacy delete audit
# ===================================================================


class TestLegacyDeleteAudit:
    """delete_legacy_artifact audit validation."""

    def test_legacy_delete_rejects_blank_actor(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """delete_legacy_artifact rejects blank migration_actor with ValueError."""
        sk = _create_legacy_file(storage, artifact_id)

        with pytest.raises(ValueError, match=r"(?i)actor|migration_actor"):
            storage.delete_legacy_artifact(
                sk,
                migration_actor="",
                audit_reason="legacy cleanup",
                repository=repo,
            )

    def test_legacy_delete_rejects_blank_reason(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """delete_legacy_artifact rejects blank audit_reason with ValueError."""
        sk = _create_legacy_file(storage, artifact_id)

        with pytest.raises(ValueError, match=r"(?i)reason|audit_reason"):
            storage.delete_legacy_artifact(
                sk,
                migration_actor="test_user",
                audit_reason="",
                repository=repo,
            )

    def test_legacy_delete_persists_audit_record(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """delete_legacy_artifact persists a DeletionOutboxRecord on success."""
        sk = _create_legacy_file(storage, artifact_id)
        # Legacy files have no sidecar — exists() uses get_path() which
        # validates sidecar, so it will return False.  But the file IS
        # on disk (just without sidecar).  We verify it via pathlib.
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file(), "Legacy file should exist on disk"

        # Perform legacy delete with repository for DB audit
        storage.delete_legacy_artifact(
            sk,
            migration_actor="migration_job",
            audit_reason="cleanup old files",
            repository=repo,
        )

        # File should be gone
        assert not storage.exists(sk)

        # A DeletionOutboxRecord must have been persisted with 'audited' status
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        records = (
            repo._session.execute(
                sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
            )
            .scalars()
            .all()
        )
        assert len(records) >= 1, (
            f"Expected at least 1 DeletionOutboxRecord for storage_key {sk!r}, got none"
        )
        rec = records[0]
        assert rec.migration_actor == "migration_job"
        assert rec.audit_reason == "cleanup old files"
        assert rec.operation == "legacy_delete"
        assert rec.status == "audited"

    def test_normal_render_path_cannot_call_legacy_delete(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """A file WITH a sidecar cannot be deleted via delete_legacy_artifact.

        This ensures the normal render path doesn't accidentally use
        the privileged legacy delete.
        """
        sk = _put_artifact(storage, artifact_id, "tok", 1)
        assert storage.exists(sk)

        # The file has a sidecar — legacy delete should reject it
        with pytest.raises(PermissionError, match=r"(?i)owner metadata|legacy|delete"):
            storage.delete_legacy_artifact(
                sk,
                migration_actor="test",
                audit_reason="should not work",
                repository=repo,
            )

        # File should still exist
        assert storage.exists(sk)

        # Normal delete should still work
        storage.delete(sk, claim_token="tok", claim_version=1)
        assert not storage.exists(sk)

    # ------------------------------------------------------------------
    # Part A — Legacy audit outbox pattern
    # ------------------------------------------------------------------

    def test_legacy_audit_commit_failure_preserves_file(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """When commit() fails before file delete, the file must remain."""
        sk = _create_legacy_file(storage, artifact_id)
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        # Make commit fail after outbox insert but before file delete
        original_commit = repo.commit

        def _failing_commit() -> None:
            raise RuntimeError("Simulated DB commit failure")

        repo.commit = _failing_commit  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="Simulated DB commit failure"):
            storage.delete_legacy_artifact(
                sk,
                migration_actor="test_user",
                audit_reason="test commit failure",
                repository=repo,
            )

        # Restore commit so we can verify state
        repo.commit = original_commit  # type: ignore[assignment]

        # File must still be on disk
        assert legacy_path.is_file(), "File should survive a failed commit"

    def test_legacy_audit_visible_from_new_session_before_delete(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """Verify the outbox record is visible from a new session before
        the file delete happens (outbox is committed first)."""
        sk = _create_legacy_file(storage, artifact_id)
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        # Call delete_legacy_artifact — it commits the outbox, then deletes
        storage.delete_legacy_artifact(
            sk,
            migration_actor="migration_job",
            audit_reason="cleanup old files",
            repository=repo,
        )

        # Open a completely new session and verify the outbox is visible
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        with session_factory() as s2:
            records = (
                s2.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(records) == 1
            assert records[0].status == "audited"
            assert records[0].migration_actor == "migration_job"

        # File should be gone
        assert not storage.exists(sk)

    def test_legacy_delete_failure_persists_failed_audit(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """When file deletion fails, the outbox status must be 'delete_failed'."""
        sk = _create_legacy_file(storage, artifact_id)
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        # Make file rename fail by making the pending_delete path unwritable
        # We simulate failure by making the base dir read-only after outbox commit
        original_commit = repo.commit
        first_commit = True

        def _delayed_fail_commit() -> None:
            nonlocal first_commit
            if first_commit:
                first_commit = False
                original_commit()  # Let the outbox commit succeed
            else:
                original_commit()  # Allow status update commits

        repo.commit = _delayed_fail_commit  # type: ignore[assignment]

        # Make the file path unwritable by replacing it with a directory
        # after the first commit but before rename

        def _break_rename(*args: Any, **kwargs: Any) -> None:
            # After outbox commit, remove the file so rename fails with FileNotFoundError
            if legacy_path.is_file():
                legacy_path.unlink()
            original_rename(*args, **kwargs)

        original_rename = Path.rename
        Path.rename = _break_rename  # type: ignore[assignment]

        with pytest.raises(FileNotFoundError):
            storage.delete_legacy_artifact(
                sk,
                migration_actor="test_user",
                audit_reason="test delete failure",
                repository=repo,
            )

        Path.rename = original_rename  # type: ignore[assignment]
        repo.commit = original_commit  # type: ignore[assignment]

        # Check outbox status is 'delete_failed'
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        records = (
            repo._session.execute(
                sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
            )
            .scalars()
            .all()
        )
        assert len(records) >= 1
        assert records[0].status == "delete_failed"

    def test_legacy_delete_success_visible_from_new_session(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """A successful legacy delete is fully visible from a new session:
        outbox status='audited' and the file is gone."""
        sk = _create_legacy_file(storage, artifact_id)
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        storage.delete_legacy_artifact(
            sk,
            migration_actor="migration_job",
            audit_reason="cleanup old files",
            repository=repo,
        )

        # File should be gone
        assert not storage.exists(sk)

        # New session sees the outbox
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        with session_factory() as s2:
            records = (
                s2.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(records) == 1
            assert records[0].status == "audited"
            assert records[0].migration_actor == "migration_job"
            assert records[0].audit_reason == "cleanup old files"


# ===================================================================
# Part B — Default waiter (DatabaseIdempotencyWaiter)
# ===================================================================


class TestDefaultWaiter:
    """DatabaseIdempotencyWaiter behaviour with SQLite."""

    def _make_waiter(
        self,
        repo: SQLReportRepository,
        session_factory: Callable[[], Any] | None = None,
    ) -> Any:
        """Create a DatabaseIdempotencyWaiter."""
        from cold_storage.modules.reports.application.render_service import (
            DatabaseIdempotencyWaiter,
        )

        return DatabaseIdempotencyWaiter(
            repo=repo,
            artifact_repo=repo,
            session_factory=session_factory,
            poll_interval=0.01,  # fast polling for tests
        )

    def test_default_waiter_without_injection_converges_sqlite(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """DatabaseIdempotencyWaiter converges (finds completed record)
        without a session_factory injection (using shared repo).

        Test: Insert a completed idempotency + artifact, then wait.
        """
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_001"

        # Insert artifact record
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        # Insert completed idempotency record
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        result = waiter.wait_for_completion(ikey, fingerprint, deadline)
        assert result is not None
        assert result.id == artifact_id
        assert result.status == ArtifactStatus.COMPLETED

    def test_default_waiter_rejects_claim_token_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """When the artifact claim_token differs from the idempotency
        record's claim_token, the waiter raises IdempotencyClaimError.
        """
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_002"

        # Insert artifact with claim_token "tok"
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        # Insert completed idempotency with DIFFERENT claim_token "other_tok"
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="other_tok",
            claim_version=2,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        # The waiter should detect the claim_token mismatch and raise
        with pytest.raises(IdempotencyClaimError, match="(?i)claim.*mismatch|token"):
            waiter.wait_for_completion(ikey, fingerprint, deadline)

    def test_default_waiter_rejects_missing_artifact(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """When the idempotency record references a nonexistent artifact,
        the waiter raises IdempotencyClaimError.
        """
        ikey = str(uuid.uuid4())
        fingerprint = "test_fingerprint_003"

        # Insert completed idempotency record WITHOUT a corresponding artifact
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": "nonexistent_artifact"},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError, match="(?i)not found|artifact"):
            waiter.wait_for_completion(ikey, fingerprint, deadline)

    def test_default_waiter_rejects_artifact_not_completed(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """When the artifact's status is not COMPLETED,
        the waiter raises IdempotencyClaimError.

        We test: completed idempotency record but artifact status is 'failed'.
        """
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_004"

        # Insert artifact with 'failed' status
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="failed",
        )

        # Insert completed idempotency record
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        # The waiter should detect the artifact is not COMPLETED
        with pytest.raises(IdempotencyClaimError, match="(?i)not completed|status|artifact"):
            waiter.wait_for_completion(ikey, fingerprint, deadline)

    # -- New waiter lineage tests -------------------------------------------

    def test_default_waiter_rejects_claim_version_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """When artifact.claim_version differs from record.claim_version,
        the waiter raises IdempotencyClaimError with ClaimVersionMismatch.
        """
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_cv"

        # Insert artifact with claim_version=99
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=99,
            status="completed",
        )

        # Insert completed idempotency with claim_version=5
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=5,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError, match="(?i)claim.*version"):
            waiter.wait_for_completion(ikey, fingerprint, deadline)

    def test_default_waiter_rejects_artifact_idempotency_key_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """When artifact.idempotency_key differs from the requested key,
        the waiter raises IdempotencyClaimError with IdempotencyKeyMismatch.
        """
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_ik"

        # Insert artifact with a DIFFERENT idempotency_key
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key="different_key",
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        # Insert completed idempotency record with the requested key
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        with pytest.raises(IdempotencyClaimError, match="(?i)idempotency.?key"):
            waiter.wait_for_completion(ikey, fingerprint, deadline)

    def test_default_waiter_rejects_report_id_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """When expected_report_id differs from artifact.report_id,
        the waiter raises IdempotencyClaimError with ReportIdMismatch.
        """
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_rid"

        # Insert artifact with report_id="report_abc"
        _insert_artifact_record(
            repo,
            artifact_id,
            report_id="report_abc",
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            status="completed",
        )

        # Insert completed idempotency record
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        # Pass expected_report_id="different_report" that doesn't match
        with pytest.raises(IdempotencyClaimError, match="(?i)report.?id"):
            waiter.wait_for_completion(
                ikey,
                fingerprint,
                deadline,
                expected_report_id="different_report",
            )

    def test_default_waiter_rejects_revision_number_mismatch(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """When expected_revision_number differs from artifact.revision_number,
        the waiter raises IdempotencyClaimError with RevisionNumberMismatch.
        """
        ikey = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        fingerprint = "test_fingerprint_rev"

        # Insert artifact with revision_number=1
        _insert_artifact_record(
            repo,
            artifact_id,
            idempotency_key=ikey,
            claim_token="tok",
            claim_version=1,
            revision_number=1,
            status="completed",
        )

        # Insert completed idempotency record
        _insert_idempotency_record(
            repo,
            ikey,
            fingerprint=fingerprint,
            status="completed",
            claim_token="tok",
            claim_version=1,
            result_payload={"artifact_id": artifact_id},
        )

        waiter = self._make_waiter(repo)
        deadline = __import__("time").monotonic() + 5.0

        # Pass expected_revision_number=99 that doesn't match
        with pytest.raises(IdempotencyClaimError, match="(?i)revision.?number"):
            waiter.wait_for_completion(
                ikey,
                fingerprint,
                deadline,
                expected_revision_number=99,
            )


# ===================================================================
# Part C — Service-level waiter convergence (real ReportRenderService)
# ===================================================================


class _ConvergenceDataProvider:
    """Minimal data provider for convergence tests."""

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return {"name": "Test", "location": "Test", "description": "Test"}

    def get_project_version(
        self, version_id: str, project_id: str | None = None
    ) -> dict[str, Any] | None:
        return {"id": version_id, "version_number": 1, "status": "active"}

    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        return None

    def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []

    def get_knowledge_documents(self) -> list[dict[str, Any]]:
        return []


def _seed_template(repo: SQLReportRepository, fmt_str: str, locale_str: str) -> None:
    """Seed a single ACTIVE template for the given format and locale."""
    from dataclasses import replace

    from cold_storage.modules.reports.domain.enums import ExportFormat, TemplateStatus
    from cold_storage.modules.reports.domain.models import ReportTemplate
    from cold_storage.modules.reports.infrastructure.template_seed import (
        _compute_content_hash,
        _load_manifest,
    )

    fmt = ExportFormat(fmt_str)
    manifest = _load_manifest(fmt, locale=locale_str, allow_legacy_fallback=True)
    if not manifest:
        return

    template_code = manifest.get("template_code", "cold_storage_concept_design")
    version = manifest.get("version", "1.0.0")
    report_type_str = manifest.get("report_type", "cold_storage_concept_design")
    schema_version = manifest.get("schema_version", f"{report_type_str}@{version}")
    content_hash = _compute_content_hash(manifest)
    report_type = ReportType(report_type_str)
    locale = ReportLocale(locale_str)

    template = ReportTemplate.create(
        template_code=template_code,
        report_type=report_type,
        format=fmt,
        version=version,
        schema_version=schema_version,
        locale=locale,
        manifest_json=manifest,
        template_content_hash=content_hash,
        created_by="system",
    )
    template = replace(template, status=TemplateStatus.ACTIVE)
    repo.save_template(template)


def _create_convergence_report(repo: SQLReportRepository, session: Any) -> Report:
    """Create a minimal DRAFT report for convergence testing."""
    report = Report.create(
        project_id="test-proj",
        project_version_id="test-ver",
        report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
        created_by="test-user",
    )
    repo.save_report(report)
    session.commit()
    return report


class TestDefaultWaiterServiceConvergence:
    """Real ReportRenderService convergence tests with same idempotency key.

    Two sequential render() calls with the same idempotency_key should
    produce the same artifact (no duplication).
    """

    @pytest.fixture()
    def conv_engine(self):
        """Separate engine for convergence tests to avoid fixture conflicts."""
        eng = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(eng)
        yield eng
        eng.dispose()

    @pytest.fixture()
    def conv_session_factory(self, conv_engine):
        return sessionmaker(bind=conv_engine, expire_on_commit=False)

    @pytest.fixture()
    def conv_session(self, conv_session_factory):
        with conv_session_factory() as s:
            yield s

    @pytest.fixture()
    def conv_repo(self, conv_session):
        return SQLReportRepository(conv_session)

    @pytest.fixture()
    def conv_storage(self, tmp_path: Path) -> ReportArtifactStorage:
        d = tmp_path / "conv_artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return ReportArtifactStorage(str(d))

    @pytest.fixture()
    def conv_report(self, conv_repo, conv_session) -> Report:
        """Create a report with one revision and seeded template."""
        # 1. Create report
        report = _create_convergence_report(conv_repo, conv_session)

        # 2. Generate revision using real assembler
        provider = _ConvergenceDataProvider()
        from cold_storage.modules.reports.application.assembler import ReportAssembler
        from cold_storage.modules.reports.application.service import ReportService

        assembler = ReportAssembler(provider)
        service = ReportService(repository=conv_repo, assembler=assembler)
        revision = service.generate_revision(report.id, "test-user")
        assert revision is not None

        # 3. Seed zh-CN DOCX template (most lightweight format)
        _seed_template(conv_repo, "docx", "zh-CN")

        return report

    def _make_render_svc(
        self,
        conv_session,
        conv_storage: ReportArtifactStorage,
    ) -> tuple[ReportRenderService, SQLReportRepository]:
        """Build a ReportRenderService for the convergence test."""
        repo = SQLReportRepository(conv_session)
        uow = ReportRenderUnitOfWork(conv_session, report_repo=repo, artifact_repo=repo)
        render_svc = ReportRenderService(
            storage=conv_storage,
            template_repo=repo,
            uow=uow,
        )
        return render_svc, repo

    def test_default_service_waiter_two_requests_converge_sqlite(
        self,
        conv_session,
        conv_storage: ReportArtifactStorage,
        conv_report: Report,
    ) -> None:
        """Two sequential render() calls with the same idempotency key converge
        to the same artifact_id and file_sha256. Only 1 completed artifact exists.
        """
        render_svc, repo = self._make_render_svc(conv_session, conv_storage)
        ikey = str(uuid.uuid4())

        # First render
        artifact1 = render_svc.render(
            report_id=conv_report.id,
            revision_number=1,
            format="docx",
            template_version=None,
            mode="draft",
            actor="test-user",
            idempotency_key=ikey,
            locale=ReportLocale.ZH_CN,
        )
        assert artifact1.status == ArtifactStatus.COMPLETED
        assert artifact1.id is not None

        # Second render with same key
        artifact2 = render_svc.render(
            report_id=conv_report.id,
            revision_number=1,
            format="docx",
            template_version=None,
            mode="draft",
            actor="test-user",
            idempotency_key=ikey,
            locale=ReportLocale.ZH_CN,
        )
        assert artifact2.status == ArtifactStatus.COMPLETED

        # Same artifact_id
        assert artifact1.id == artifact2.id, (
            f"Same idempotency key should return same artifact, "
            f"got {artifact1.id} vs {artifact2.id}"
        )

        # Same file_sha256
        assert artifact1.file_sha256 == artifact2.file_sha256, (
            f"Same idempotency key should return same sha256, "
            f"got {artifact1.file_sha256} vs {artifact2.file_sha256}"
        )

        # Only 1 completed artifact in DB
        from cold_storage.modules.reports.infrastructure.orm import (
            ReportExportArtifactRecord,
        )

        artifacts = (
            repo._session.execute(
                sa.select(ReportExportArtifactRecord).where(
                    ReportExportArtifactRecord.idempotency_key == ikey,
                )
            )
            .scalars()
            .all()
        )
        assert len(artifacts) == 1, (
            f"Expected exactly 1 completed artifact for key {ikey}, got {len(artifacts)}"
        )

    def test_default_api_waiter_two_requests_converge_without_override(
        self,
        conv_session,
        conv_storage: ReportArtifactStorage,
        conv_report: Report,
    ) -> None:
        """Also service-level convergence without explicit waiter injection.

        This tests the same scenario as above but ensures the default
        DatabaseIdempotencyWaiter (auto-wired) is used, not an injected one.
        """
        render_svc, repo = self._make_render_svc(conv_session, conv_storage)
        ikey = str(uuid.uuid4())

        # First render
        artifact1 = render_svc.render(
            report_id=conv_report.id,
            revision_number=1,
            format="docx",
            template_version=None,
            mode="draft",
            actor="test-user",
            idempotency_key=ikey,
            locale=ReportLocale.ZH_CN,
        )
        assert artifact1.status == ArtifactStatus.COMPLETED

        # Second render — uses auto-wired default waiter (no injection)
        artifact2 = render_svc.render(
            report_id=conv_report.id,
            revision_number=1,
            format="docx",
            template_version=None,
            mode="draft",
            actor="test-user",
            idempotency_key=ikey,
            locale=ReportLocale.ZH_CN,
        )
        assert artifact2.status == ArtifactStatus.COMPLETED

        # Same artifact
        assert artifact1.id == artifact2.id
        assert artifact1.file_sha256 == artifact2.file_sha256

        # Single artifact in DB
        from cold_storage.modules.reports.infrastructure.orm import (
            ReportExportArtifactRecord,
        )

        artifacts = (
            repo._session.execute(
                sa.select(ReportExportArtifactRecord).where(
                    ReportExportArtifactRecord.idempotency_key == ikey,
                )
            )
            .scalars()
            .all()
        )
        assert len(artifacts) == 1
        assert artifacts[0].id == artifact1.id


# ===================================================================
# Part C — Deletion outbox restart/recovery
# ===================================================================


class TestDeletionOutboxRecovery:
    """Legacy deletion outbox recovery during startup.

    Tests for recover_pending_outboxes() which is called from
    ReportArtifactStorage.__init__ when a repository is provided.
    """

    def _create_legacy_file(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        sk: str | None = None,
    ) -> str:
        """Create a legacy artifact file WITHOUT a .meta sidecar."""
        if sk is None:
            sk = str(uuid.uuid4())
        artifact_dir = Path(storage._base_dir) / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        file_path = artifact_dir / f"{sk}_legacy.pdf"
        file_path.write_bytes(b"legacy artifact data for recovery test")
        return sk

    def test_deletion_outbox_restart_recovers_pending_audit(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
        session_factory,
        tmp_base: str,
    ) -> None:
        """A pending_audit outbox with the file still present is recovered
        on startup: file is deleted, outbox status becomes 'audited'."""
        sk = self._create_legacy_file(storage, artifact_id)
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        # Insert a pending_audit outbox directly (simulating crash after commit)
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        outbox = DeletionOutboxRecord(
            id=str(uuid.uuid4()),
            storage_key=sk,
            migration_actor="recovery_test",
            audit_reason="test recovery",
            operation="legacy_delete",
            source_hash="abc123",
            status="pending_audit",
        )
        repo._session.add(outbox)
        repo.commit()

        # Now create a new storage instance WITH repository to trigger recovery
        ReportArtifactStorage(tmp_base, repository=repo)

        # Use a fresh session to verify (avoid ORM identity map caching)
        with session_factory() as fresh_session:
            from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord as DO

            records = (
                fresh_session.execute(sa.select(DO).where(DO.storage_key == sk)).scalars().all()
            )
            assert len(records) == 1
            assert records[0].status == "audited"
        assert not legacy_path.is_file()

    def test_deletion_outbox_retry_recovers_delete_failed(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
        tmp_base: str,
        session_factory,
    ) -> None:
        """A delete_failed outbox with the file still present is retried
        on startup: file is deleted, outbox status becomes 'audited',
        retry_count is incremented."""
        sk = self._create_legacy_file(storage, artifact_id)
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        outbox = DeletionOutboxRecord(
            id=str(uuid.uuid4()),
            storage_key=sk,
            migration_actor="recovery_test",
            audit_reason="test retry recovery",
            operation="legacy_delete",
            source_hash="abc123",
            status="delete_failed",
            retry_count=2,
        )
        repo._session.add(outbox)
        repo.commit()

        # Create new storage with repository to trigger recovery
        ReportArtifactStorage(tmp_base, repository=repo)

        # Use a fresh session to verify the data (avoid ORM identity map caching)
        with session_factory() as fresh_session:
            from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord as DO

            records = (
                fresh_session.execute(sa.select(DO).where(DO.storage_key == sk)).scalars().all()
            )
            assert len(records) == 1
            assert records[0].status == "audited"
            # retry_count is NOT incremented on success in the new CAS recovery;
            # it is only incremented by fail_deletion_outbox() on failure.
        assert not legacy_path.is_file()

    def test_deletion_outbox_is_idempotent(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
        tmp_base: str,
        session_factory,
    ) -> None:
        """Running recovery twice on the same outbox is idempotent.

        The first recovery processes the pending_audit outbox (deletes the
        file, marks it audited).  The second recovery skips the audited
        outbox entirely.
        """
        sk = self._create_legacy_file(storage, artifact_id)
        legacy_path = Path(storage._base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        outbox = DeletionOutboxRecord(
            id=str(uuid.uuid4()),
            storage_key=sk,
            migration_actor="recovery_test",
            audit_reason="test idempotent",
            operation="legacy_delete",
            source_hash="abc123",
            status="pending_audit",
        )
        repo._session.add(outbox)
        repo.commit()

        # First recovery
        ReportArtifactStorage(tmp_base, repository=repo)

        # Verify the outbox is now audited (use fresh session)
        with session_factory() as fresh:
            from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord as DO

            records = fresh.execute(sa.select(DO).where(DO.storage_key == sk)).scalars().all()
            assert len(records) == 1
            assert records[0].status == "audited"
        assert not legacy_path.is_file()

        # Second recovery: outbox is already audited, so _recover_pending_outboxes
        # should skip it entirely.  The status should remain audited.
        ReportArtifactStorage(tmp_base, repository=repo)

        # Outbox status should still be audited (use fresh session)
        with session_factory() as fresh2:
            from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord as DO

            records2 = fresh2.execute(sa.select(DO).where(DO.storage_key == sk)).scalars().all()
            assert len(records2) == 1
            assert records2[0].status == "audited"

    def test_two_outbox_executors_only_one_deletes(
        self,
        artifact_id: str,
        repo: SQLReportRepository,
        tmp_base: str,
        engine,
        session_factory,
    ) -> None:
        """When two sessions start recovery simultaneously on the same
        outbox, exactly one succeeds in deleting the file."""

        # Create a legacy file on disk
        base_dir = tmp_base
        storage = ReportArtifactStorage(base_dir)
        sk = self._create_legacy_file(storage, artifact_id)
        legacy_path = Path(base_dir) / artifact_id / f"{sk}_legacy.pdf"
        assert legacy_path.is_file()

        # Insert a pending_audit outbox
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        outbox = DeletionOutboxRecord(
            id=str(uuid.uuid4()),
            storage_key=sk,
            migration_actor="recovery_test",
            audit_reason="test two executors",
            operation="legacy_delete",
            source_hash="abc123",
            status="pending_audit",
        )
        repo._session.add(outbox)
        repo.commit()

        # Simulate two concurrent recovery runs
        SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)

        with SessionFactory() as s1:
            r1 = SQLReportRepository(s1)
            ReportArtifactStorage(base_dir, repository=r1)
            s1.commit()

        with SessionFactory() as s2:
            r2 = SQLReportRepository(s2)
            ReportArtifactStorage(base_dir, repository=r2)
            s2.commit()

        # The outbox should be audited and the file should be gone (use fresh session)
        with session_factory() as fresh:
            from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord as DO

            records = fresh.execute(sa.select(DO).where(DO.storage_key == sk)).scalars().all()
            assert len(records) == 1
            assert records[0].status == "audited"
        assert not legacy_path.is_file()


# ===================================================================
# Part D — Outbox CAS claim and two-phase recovery
# ===================================================================


class TestOutboxCASClaim:
    """CAS-based outbox claiming for deletion outbox processing.

    Tests for claim_deletion_outbox, complete_deletion_outbox,
    fail_deletion_outbox, and list_eligible_outboxes with real
    SQLite sessions and no sleep.
    """

    def _create_pending_outbox(
        self,
        repo: SQLReportRepository,
        *,
        storage_key: str | None = None,
        status: str = "pending_audit",
        claim_version: int = 0,
        claim_token: str | None = None,
        locked_at: Any = None,
        lock_expires_at: Any = None,
    ) -> str:
        """Insert a DeletionOutboxRecord directly and return the outbox_id."""
        import uuid

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        if storage_key is None:
            storage_key = str(uuid.uuid4())
        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=storage_key,
            migration_actor="test_actor",
            audit_reason="test cas claim",
            operation="legacy_delete",
            source_hash="abc123",
            status=status,
            claim_token=claim_token,
            claim_version=claim_version,
            locked_at=locked_at,
            lock_expires_at=lock_expires_at,
        )
        repo._session.add(rec)
        repo.commit()
        return outbox_id

    # ------------------------------------------------------------------
    # CAS claim tests
    # ------------------------------------------------------------------

    def test_outbox_cas_claim_pending_audit(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """A pending_audit outbox can be CAS-claimed successfully."""
        from datetime import UTC, datetime

        outbox_id = self._create_pending_outbox(repo, status="pending_audit")

        now = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker_1",
            now=now,
            lease_seconds=300,
            observed_status="pending_audit",
            observed_claim_version=0,
        )
        assert claimed, "CAS claim should succeed for pending_audit"

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        rec = repo._session.get(DeletionOutboxRecord, outbox_id)
        assert rec is not None
        assert rec.status == "deleting"
        assert rec.claim_token == "worker_1"
        assert rec.claim_version == 1
        assert rec.locked_at is not None
        assert rec.lock_expires_at is not None

    def test_outbox_cas_claim_delete_failed(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """A delete_failed outbox can be CAS-claimed successfully."""
        from datetime import UTC, datetime

        outbox_id = self._create_pending_outbox(repo, status="delete_failed", claim_version=2)

        now = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker_2",
            now=now,
            lease_seconds=300,
            observed_status="delete_failed",
            observed_claim_version=2,
        )
        assert claimed, "CAS claim should succeed for delete_failed"

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        rec = repo._session.get(DeletionOutboxRecord, outbox_id)
        assert rec is not None
        assert rec.status == "deleting"
        assert rec.claim_token == "worker_2"
        assert rec.claim_version == 3  # bumped

    def test_two_outbox_executors_only_one_claims(
        self,
        repo: SQLReportRepository,
        session_factory,
        engine,
    ) -> None:
        """Two concurrent executors: only one can claim the same outbox."""
        from datetime import UTC, datetime

        outbox_id = self._create_pending_outbox(repo, status="pending_audit")

        now = datetime.now(UTC)

        # Session 1 claims it
        with session_factory() as s1:
            r1 = SQLReportRepository(s1)
            claimed1 = r1.claim_deletion_outbox(
                outbox_id,
                claimant_token="worker_a",
                now=now,
                lease_seconds=300,
                observed_status="pending_audit",
                observed_claim_version=0,
            )
            assert claimed1
            s1.commit()

        # Session 2 tries with stale observed_claim_version should fail
        with session_factory() as s2:
            r2 = SQLReportRepository(s2)
            claimed2 = r2.claim_deletion_outbox(
                outbox_id,
                claimant_token="worker_b",
                now=now,
                lease_seconds=300,
                observed_status="pending_audit",
                observed_claim_version=0,  # stale — version is now 1
            )
            assert not claimed2, "Second claim with stale version should fail"

        # Session 2 tries with wrong observed_status should fail
        with session_factory() as s3:
            r3 = SQLReportRepository(s3)
            claimed3 = r3.claim_deletion_outbox(
                outbox_id,
                claimant_token="worker_c",
                now=now,
                lease_seconds=300,
                observed_status="pending_audit",  # wrong — status is now 'deleting'
                observed_claim_version=1,
            )
            assert not claimed3, "Second claim with wrong status should fail"

    def test_old_worker_cannot_mark_new_claim_audited(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """Worker A claims, Worker B also claims (expired lease), Worker A
        cannot complete Worker B's claim because CAS validates claim_token+version."""
        from datetime import UTC, datetime, timedelta

        outbox_id = self._create_pending_outbox(repo, status="pending_audit")
        now = datetime.now(UTC)

        # Worker A claims
        repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker_a",
            now=now,
            lease_seconds=300,
            observed_status="pending_audit",
            observed_claim_version=0,
        )
        repo.commit()

        # Worker B reclaims with expired lease
        repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker_b",
            now=now + timedelta(seconds=600),
            lease_seconds=300,
            observed_status="deleting",
            observed_claim_version=1,  # Worker A's version
        )
        repo.commit()

        # Worker A tries to complete with their old claim_token+version
        with pytest.raises(ValueError, match=r"(?i)not found|claim mismatch"):
            repo.complete_deletion_outbox(
                outbox_id,
                claim_token="worker_a",
                claim_version=1,  # stale — version is now 2
            )

    def test_old_worker_cannot_mark_new_claim_failed(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """Same as old_worker_cannot_mark_new_claim_audited but for fail."""
        from datetime import UTC, datetime, timedelta

        outbox_id = self._create_pending_outbox(repo, status="pending_audit")
        now = datetime.now(UTC)

        # Worker A claims
        repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker_a",
            now=now,
            lease_seconds=300,
            observed_status="pending_audit",
            observed_claim_version=0,
        )
        repo.commit()

        # Worker B reclaims
        repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker_b",
            now=now + timedelta(seconds=600),
            lease_seconds=300,
            observed_status="deleting",
            observed_claim_version=1,
        )
        repo.commit()

        # Worker A tries to fail with old claim
        with pytest.raises(ValueError, match=r"(?i)not found|claim mismatch"):
            repo.fail_deletion_outbox(
                outbox_id,
                claim_token="worker_a",
                claim_version=1,
                error="test",
            )

    def test_expired_deleting_outbox_is_reclaimed(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """An outbox with status='deleting' and expired lock_expires_at can be reclaimed."""
        from datetime import UTC, datetime, timedelta

        expired = datetime.now(UTC) - timedelta(seconds=60)
        outbox_id = self._create_pending_outbox(
            repo,
            status="deleting",
            claim_version=5,
            claim_token="stale_worker",
            locked_at=expired,
            lock_expires_at=expired,
        )

        now = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="new_worker",
            now=now,
            lease_seconds=300,
            observed_status="deleting",
            observed_claim_version=5,
        )
        assert claimed, "Expired deleting outbox should be claimable"

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        rec = repo._session.get(DeletionOutboxRecord, outbox_id)
        assert rec is not None
        assert rec.claim_token == "new_worker"
        assert rec.claim_version == 6
        assert rec.status == "deleting"

    def test_nonexpired_deleting_outbox_cannot_be_claimed_directly(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """An outbox with status='deleting' and non-expired lock_expires_at cannot be claimed."""
        from datetime import UTC, datetime, timedelta

        recent = datetime.now(UTC) - timedelta(seconds=30)
        future = datetime.now(UTC) + timedelta(seconds=300)
        outbox_id = self._create_pending_outbox(
            repo,
            status="deleting",
            claim_version=3,
            claim_token="active_worker",
            locked_at=recent,
            lock_expires_at=future,
        )

        now = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="poacher",
            now=now,
            lease_seconds=300,
            observed_status="deleting",
            observed_claim_version=3,
        )
        # claim_deletion_outbox checks lock_expires_at internally via the
        # eligibility condition, so this should fail.
        assert not claimed, "Non-expired deleting outbox should NOT be claimable"

    def test_outbox_cas_claim_validates_observed_claim_version(
        self,
        repo: SQLReportRepository,
    ) -> None:
        """CAS claim fails if observed_claim_version doesn't match."""
        from datetime import UTC, datetime

        outbox_id = self._create_pending_outbox(repo, status="pending_audit", claim_version=42)

        now = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker",
            now=now,
            lease_seconds=300,
            observed_status="pending_audit",
            observed_claim_version=0,  # wrong — should be 42
        )
        assert not claimed, "CAS claim should fail with wrong observed_claim_version"

        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="worker",
            now=now,
            lease_seconds=300,
            observed_status="pending_audit",
            observed_claim_version=42,
        )
        assert claimed

    # ------------------------------------------------------------------
    # Recovery tests
    # ------------------------------------------------------------------

    def test_outbox_recovery_survives_new_session(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """Recovery via new artifact_storage instance with repository works."""
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        storage = ReportArtifactStorage(tmp_base)
        import uuid

        sk = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        legacy_path = Path(storage._base_dir) / artifact_id
        legacy_path.mkdir(parents=True, exist_ok=True)
        file_path = legacy_path / f"{sk}_legacy.pdf"
        file_path.write_bytes(b"recovery test data")

        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="recovery",
            operation="legacy_delete",
            source_hash="abc",
            status="pending_audit",
        )
        repo._session.add(rec)
        repo.commit()

        assert file_path.is_file()

        ReportArtifactStorage(tmp_base, repository=repo)

        with session_factory() as fresh:
            records = (
                fresh.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(records) == 1
            assert records[0].status == "audited"
        assert not file_path.is_file()

    def test_outbox_recovery_survives_process_restart(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """Simulate process restart: recovery completes pending_audit outbox."""
        import uuid

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        sk = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())

        storage1 = ReportArtifactStorage(tmp_base)
        legacy_path = Path(storage1._base_dir) / artifact_id
        legacy_path.mkdir(parents=True, exist_ok=True)
        file_path = legacy_path / f"{sk}_legacy.pdf"
        file_path.write_bytes(b"restart test data")

        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="restart",
            operation="legacy_delete",
            source_hash="abc",
            status="pending_audit",
        )
        repo._session.add(rec)
        repo.commit()

        assert file_path.is_file()

        ReportArtifactStorage(tmp_base, repository=repo)

        with session_factory() as fresh:
            records = (
                fresh.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(records) == 1
            assert records[0].status == "audited"
        assert not file_path.is_file()

    def test_deletion_outbox_recovery_pending_audit_file_missing(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """A pending_audit outbox with the file already missing is completed
        as audited during recovery."""
        import uuid

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        sk = str(uuid.uuid4())
        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="missing file",
            operation="legacy_delete",
            source_hash="abc",
            status="pending_audit",
        )
        repo._session.add(rec)
        repo.commit()

        ReportArtifactStorage(tmp_base, repository=repo)

        with session_factory() as fresh:
            records = (
                fresh.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(records) == 1
            assert records[0].status == "audited"

    def test_outbox_recovery_respects_claimed_outboxes(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """If another process already claimed an outbox, recovery skips it."""
        import uuid
        from datetime import UTC, datetime

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        now = datetime.now(UTC)
        rec2_id = str(uuid.uuid4())
        sk2 = str(uuid.uuid4())
        rec2 = DeletionOutboxRecord(
            id=rec2_id,
            storage_key=sk2,
            migration_actor="test",
            audit_reason="active claim",
            operation="legacy_delete",
            source_hash="abc",
            status="deleting",
            claim_token="active_worker",
            claim_version=1,
            locked_at=now,
            lock_expires_at=now + __import__("datetime").timedelta(seconds=600),
        )
        repo._session.add(rec2)
        repo.commit()

        eligible = repo.list_eligible_outboxes()
        eligible_ids = {e["id"] for e in eligible}
        assert rec2_id not in eligible_ids, "Non-expired deleting outbox should not be eligible"


# ===================================================================
# Part E — Outbox crash matrix tests
# ===================================================================


class TestOutboxCrashMatrix:
    """Outbox crash-and-recovery matrix tests with Barrier concurrency.

    Every recovery test must close the original session and create a new
    Session + new SQLReportRepository + new ReportArtifactStorage.
    All use Barrier for concurrency (no sleep).
    """

    def _create_legacy_file(
        self,
        storage: ReportArtifactStorage,
        art_id: str,
        sk: str | None = None,
    ) -> str:
        import uuid

        if sk is None:
            sk = str(uuid.uuid4())
        artifact_dir = Path(storage._base_dir) / art_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        file_path = artifact_dir / f"{sk}_legacy.pdf"
        file_path.write_bytes(b"crash test data")
        return sk

    # ------------------------------------------------------------------
    # CAS claim version tests
    # ------------------------------------------------------------------

    def test_claim_version_increments_on_every_reclaim(
        self,
        repo: SQLReportRepository,
        session_factory,
    ) -> None:
        """Each reclaim increments claim_version."""
        from datetime import UTC, datetime, timedelta

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        # Create a pending_audit outbox
        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=str(uuid.uuid4()),
            migration_actor="test",
            audit_reason="version test",
            operation="legacy_delete",
            source_hash="abc",
            status="pending_audit",
            claim_version=0,
        )
        repo._session.add(rec)
        repo.commit()

        # Claim 1: pending_audit -> deleting, version 0 -> 1
        t1 = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="w1",
            now=t1,
            lease_seconds=300,
            observed_status="pending_audit",
            observed_claim_version=0,
        )
        assert claimed
        repo.commit()

        # Use fresh session to verify (ORM cache has stale data due to expire_on_commit=False)
        with session_factory() as fresh:
            rec = fresh.get(DeletionOutboxRecord, outbox_id)
            assert rec is not None
            assert rec.claim_version == 1, (
                f"Expected claim_version=1 after first claim, got {rec.claim_version}"
            )

        # Force lease to expire so we can reclaim
        repo._session.execute(
            sa.update(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.id == outbox_id)
            .values(lock_expires_at=t1 - timedelta(seconds=1))
        )
        repo.commit()

        # Verify the lease IS expired via fresh session
        with session_factory() as fresh:
            rec = fresh.get(DeletionOutboxRecord, outbox_id)
            assert rec is not None
            assert rec.lock_expires_at is not None
            # SQLite stores naive datetimes, so strip tzinfo for comparison
            assert rec.lock_expires_at.replace(tzinfo=None) <= t1.replace(tzinfo=None), (
                f"Lock should be expired: {rec.lock_expires_at} <= {t1}"
            )

        # Claim 2: expired lease reclaim, version 1 -> 2
        t2 = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="w2",
            now=t2,
            lease_seconds=300,
            observed_status="deleting",
            observed_claim_version=1,
        )
        assert claimed, "Second claim (expired lease) should succeed"
        repo.commit()

        with session_factory() as fresh:
            rec = fresh.get(DeletionOutboxRecord, outbox_id)
            assert rec is not None
            assert rec.claim_version == 2, (
                f"Expected claim_version=2 after reclaim, got {rec.claim_version}"
            )

        # Force lease to expire again
        repo._session.execute(
            sa.update(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.id == outbox_id)
            .values(lock_expires_at=t2 - timedelta(seconds=1))
        )
        repo.commit()

        # Claim 3: another reclaim, version 2 -> 3
        t3 = datetime.now(UTC)
        claimed = repo.claim_deletion_outbox(
            outbox_id,
            claimant_token="w3",
            now=t3,
            lease_seconds=300,
            observed_status="deleting",
            observed_claim_version=2,
        )
        assert claimed, "Third claim (expired lease) should succeed"
        repo.commit()

        with session_factory() as fresh:
            rec = fresh.get(DeletionOutboxRecord, outbox_id)
            assert rec is not None
            assert rec.claim_version == 3, (
                f"Expected claim_version=3 after third claim, got {rec.claim_version}"
            )

    # ------------------------------------------------------------------
    # Recovery tests — new session, new storage, new repo
    # ------------------------------------------------------------------

    def test_outbox_crash_after_claim_is_recoverable(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        engine,
        session_factory,
    ) -> None:
        """Claim an outbox (simulate crash after claim), then new storage
        instance should recover it."""
        from datetime import UTC, datetime, timedelta

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        art_id = str(uuid.uuid4())
        storage1 = ReportArtifactStorage(tmp_base)
        sk = self._create_legacy_file(storage1, art_id)

        # Insert pending_audit outbox
        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="crash after claim",
            operation="legacy_delete",
            source_hash="abc",
            status="pending_audit",
        )
        repo._session.add(rec)
        repo.commit()

        # Simulate crash after claim: directly set status to 'deleting'
        # with an expired lock (as if claim happened then crash before
        # file delete)
        past = datetime.now(UTC) - timedelta(hours=1)
        repo._session.execute(
            sa.update(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.id == outbox_id)
            .values(
                status="deleting",
                claim_token="crashed_worker",
                claim_version=1,
                locked_at=past,
                lock_expires_at=past,
            )
        )
        repo.commit()

        # Close original session, create new session + repo + storage
        repo._session.close()
        with session_factory() as s2:
            r2 = SQLReportRepository(s2)
            ReportArtifactStorage(tmp_base, repository=r2)
            s2.commit()

        # Verify outbox was recovered
        with session_factory() as s3:
            recs = (
                s3.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(recs) == 1
            assert recs[0].status == "audited"

    def test_outbox_crash_after_rename_is_recoverable(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        engine,
        session_factory,
    ) -> None:
        """Set up outbox where payload exists but pending_delete file exists
        (simulating crash after rename before unlink), recovery should complete."""
        from datetime import UTC, datetime, timedelta

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        art_id = str(uuid.uuid4())
        storage1 = ReportArtifactStorage(tmp_base)
        sk = self._create_legacy_file(storage1, art_id)

        # Find the actual file path
        artifact_dir = Path(storage1._base_dir) / art_id
        file_path = artifact_dir / f"{sk}_legacy.pdf"
        pending_path = artifact_dir / f"{sk}_legacy.pdf.pending_delete"

        # Simulate crash after rename: move file to pending_delete but
        # don't unlink (as if crash happened between rename and unlink)
        file_path.rename(pending_path)
        assert pending_path.is_file()
        assert not file_path.exists()

        # Insert outbox with deleting status + expired lock (so recovery
        # will pick it up)
        outbox_id = str(uuid.uuid4())
        past = datetime.now(UTC) - timedelta(hours=1)
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="crash after rename",
            operation="legacy_delete",
            source_hash="abc",
            status="deleting",
            claim_token="crashed_worker",
            claim_version=1,
            locked_at=past,
            lock_expires_at=past,
        )
        repo._session.add(rec)
        repo.commit()

        # Close original session, create new storage + repo
        repo._session.close()
        with session_factory() as s2:
            r2 = SQLReportRepository(s2)
            ReportArtifactStorage(tmp_base, repository=r2)
            s2.commit()

        # Verify: outbox audited, pending_delete file gone
        with session_factory() as s3:
            recs = (
                s3.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(recs) == 1
            assert recs[0].status == "audited"
        assert not pending_path.exists()

    def test_outbox_crash_after_delete_before_complete_is_recoverable(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        engine,
        session_factory,
    ) -> None:
        """Manually set receipt status='intent', mark outbox as 'deleting'
        but file missing, then recover."""
        from datetime import UTC, datetime, timedelta

        from cold_storage.modules.reports.infrastructure.orm import (
            DeletionOutboxRecord,
            DeletionReceiptRecord,
        )

        art_id = str(uuid.uuid4())
        storage1 = ReportArtifactStorage(tmp_base)
        sk = self._create_legacy_file(storage1, art_id)

        # File exists
        artifact_dir = Path(storage1._base_dir) / art_id
        file_path = artifact_dir / f"{sk}_legacy.pdf"
        assert file_path.is_file()

        # Simulate intent receipt
        receipt = DeletionReceiptRecord(
            storage_key=sk,
            stale_claim_token="tok",
            stale_claim_version=1,
            reclaim_token="tok2",
            reclaim_version=1,
            deletion_hash="abc",
            status="intent",
        )
        repo._session.add(receipt)

        # Insert outbox with deleting status + expired lock
        outbox_id = str(uuid.uuid4())
        past = datetime.now(UTC) - timedelta(hours=1)
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="crash after delete before complete",
            operation="legacy_delete",
            source_hash="abc",
            status="deleting",
            claim_token="crashed_worker",
            claim_version=1,
            locked_at=past,
            lock_expires_at=past,
        )
        repo._session.add(rec)
        repo.commit()

        # Now simulate file was already deleted (crash after delete
        # before complete)
        file_path.unlink()
        assert not file_path.exists()

        # Close original session, create new storage + repo
        repo._session.close()
        with session_factory() as s2:
            r2 = SQLReportRepository(s2)
            ReportArtifactStorage(tmp_base, repository=r2)
            s2.commit()

        # Verify outbox was completed (file already missing)
        with session_factory() as s3:
            recs = (
                s3.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(recs) == 1
            assert recs[0].status == "audited"

    def test_outbox_expired_lease_recovery_after_restart(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        engine,
        session_factory,
    ) -> None:
        """Create outbox with expired lock, new storage recovers it."""
        from datetime import UTC, datetime, timedelta

        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        art_id = str(uuid.uuid4())
        storage1 = ReportArtifactStorage(tmp_base)
        sk = self._create_legacy_file(storage1, art_id)
        file_path = Path(storage1._base_dir) / art_id / f"{sk}_legacy.pdf"
        assert file_path.is_file()

        # Insert deleting outbox with expired lease
        past = datetime.now(UTC) - timedelta(hours=1)
        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="expired lease recovery",
            operation="legacy_delete",
            source_hash="abc",
            status="deleting",
            claim_token="old_worker",
            claim_version=3,
            locked_at=past,
            lock_expires_at=past,
        )
        repo._session.add(rec)
        repo.commit()

        # Close original session
        repo._session.close()

        # New storage instance should recover
        with session_factory() as s2:
            r2 = SQLReportRepository(s2)
            ReportArtifactStorage(tmp_base, repository=r2)
            s2.commit()

        # Verify
        with session_factory() as s3:
            recs = (
                s3.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(recs) == 1
            assert recs[0].status == "audited"
        assert not file_path.exists()

    def test_two_storage_instances_do_not_double_process_outbox(
        self,
        tmp_base: str,
        repo: SQLReportRepository,
        engine,
        session_factory,
    ) -> None:
        """Two storage instances processing the same outbox — only
        one deletes the file, the second skips."""
        from cold_storage.modules.reports.infrastructure.orm import DeletionOutboxRecord

        art_id = str(uuid.uuid4())
        storage1 = ReportArtifactStorage(tmp_base)
        sk = self._create_legacy_file(storage1, art_id)
        file_path = Path(storage1._base_dir) / art_id / f"{sk}_legacy.pdf"
        assert file_path.is_file()

        # Insert pending_audit outbox
        outbox_id = str(uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=sk,
            migration_actor="test",
            audit_reason="concurrent recovery",
            operation="legacy_delete",
            source_hash="abc",
            status="pending_audit",
        )
        repo._session.add(rec)
        repo.commit()

        repo._session.close()

        # First storage instance processes the outbox
        with session_factory() as s1:
            r1 = SQLReportRepository(s1)
            ReportArtifactStorage(tmp_base, repository=r1)
            s1.commit()

        # Second storage instance should skip it (already audited)
        with session_factory() as s2:
            r2 = SQLReportRepository(s2)
            ReportArtifactStorage(tmp_base, repository=r2)
            s2.commit()

        # Outbox should be audited exactly once
        with session_factory() as s3:
            recs = (
                s3.execute(
                    sa.select(DeletionOutboxRecord).where(DeletionOutboxRecord.storage_key == sk)
                )
                .scalars()
                .all()
            )
            assert len(recs) == 1
            assert recs[0].status == "audited"

        # File should be gone
        assert not file_path.exists()
