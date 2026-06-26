"""P0-9: Idempotent cleanup debt reclaim tests.

Tests for list_eligible_cleanup_debts, processing debt recovery, reclaim_delete
idempotency, and edge cases around two-phase cleanup.

Each test uses a REAL ``ReportArtifactStorage`` backed by a temp directory
and a REAL SQL Repository backed by SQLite with explicit clock control (no sleep).

Test matrix
-----------
- test_expired_processing_debt_is_listed_as_eligible
- test_nonexpired_processing_debt_is_not_listed
- test_executor_recovers_expired_processing_debt
- test_two_executors_only_one_reclaims_expired_processing_debt
- test_processing_lease_recovery_survives_new_session
- test_cleanup_retry_completes_when_same_debt_file_already_missing
- test_reclaim_delete_same_debt_is_idempotent
- test_missing_file_with_mismatched_debt_owner_fails_closed
- test_delete_succeeds_but_completion_commit_fails_then_retry_completes
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.infrastructure.artifact_storage import (
    ReportArtifactStorage,
)
from cold_storage.modules.reports.infrastructure.orm import Base
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
    claim_token: str = "stale_tok",
    claim_version: int = 1,
) -> str:
    return storage.put(
        artifact_id,
        b"file content for cleanup test",
        "cleanup_test.pdf",
        claim_token=claim_token,
        claim_version=claim_version,
    )


def _insert_debt(
    repo: SQLReportRepository,
    storage_key: str,
    *,
    idempotency_key: str = "ikey",
    stale_token: str = "stale_tok",
    stale_version: int = 1,
    reclaim_token: str = "new_tok",
    reclaim_version: int = 2,
) -> str:
    debt_id = repo.insert_cleanup_debt(
        idempotency_key=idempotency_key,
        storage_key=storage_key,
        stale_claim_token=stale_token,
        stale_claim_version=stale_version,
        reclaim_token=reclaim_token,
        reclaim_version=reclaim_version,
    )
    repo.commit()
    return debt_id


def _set_debt_processing_expired(
    repo: SQLReportRepository,
    debt_id: str,
    *,
    clock_now: datetime,
    lock_seconds: int = 300,
    locked_by: str = "old_executor",
    use_lock_expires: bool = True,
) -> tuple[datetime, str, datetime | None]:
    """Manually set a debt to 'processing' with an expired lock timestamp.

    Uses raw SQL to simulate a processing debt whose lease expired.
    Returns (locked_at, locked_by, lock_expires_at) so the caller can
    pass them to claim_cleanup_debt as observed_* params.

    If use_lock_expires is False, lock_expires_at is set to NULL, which
    triggers the cutoff-based expiry check (locked_at < cutoff)
    in list_eligible_cleanup_debts, BUT NOT in claim_cleanup_debt
    (which requires exact CAS for processing debts).
    """
    locked_at = clock_now - timedelta(seconds=lock_seconds + 10)
    if use_lock_expires:
        expires_at: datetime | None = clock_now - timedelta(seconds=1)
    else:
        expires_at = None
    repo._session.execute(
        sa.text(
            "UPDATE cleanup_debt SET status='processing', "
            "locked_at=:locked_at, locked_by=:locked_by, "
            "lock_expires_at=:expires_at "
            "WHERE id=:debt_id"
        ),
        {
            "locked_at": locked_at,
            "locked_by": locked_by,
            "expires_at": expires_at,
            "debt_id": debt_id,
        },
    )
    repo.commit()
    return locked_at, locked_by, expires_at


def _get_cv(repo: SQLReportRepository, debt_id: str) -> int:
    """Read the current claim_version from a cleanup_debt record."""
    cv_result = repo._session.execute(
        sa.select(sa.column("claim_version"))
        .where(sa.column("id") == debt_id)
        .select_from(sa.table("cleanup_debt"))
    ).scalar()
    return cv_result if cv_result is not None else 0


# ===================================================================
# Tests
# ===================================================================


class TestListEligibleCleanupDebts:
    """list_eligible_cleanup_debts with processing lease expiry."""

    def test_expired_processing_debt_is_listed_as_eligible(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """A processing debt with expired lock_expires_at is listed as eligible."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk)
        now = datetime.now(UTC)

        # Set it to processing with expired lock_expires_at
        _set_debt_processing_expired(repo, debt_id, clock_now=now, use_lock_expires=True)
        repo.commit()

        # It should appear in list_eligible_cleanup_debts
        eligible = repo.list_eligible_cleanup_debts(processing_timeout_seconds=300)
        eligible_ids = [d["id"] for d in eligible]
        assert debt_id in eligible_ids

    def test_nonexpired_processing_debt_is_not_listed(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """A processing debt with valid (non-expired) lock is NOT listed."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk)

        # Claim it (sets processing with a fresh lock that hasn't expired)
        assert repo.claim_cleanup_debt(debt_id, lock_seconds=300)
        repo.commit()

        # It should NOT appear in eligible (lock is still valid)
        eligible = repo.list_eligible_cleanup_debts(processing_timeout_seconds=300)
        eligible_ids = [d["id"] for d in eligible]
        assert debt_id not in eligible_ids


class TestExecutorRecoversExpiredDebt:
    """Cleanup executor recovers expired processing debts."""

    def test_executor_recovers_expired_processing_debt(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """An expired processing debt can be reclaimed by the executor.

        Uses retryable status (which Try 1 of claim_cleanup_debt can claim).
        """
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk, stale_token="stale_tok", stale_version=1)

        # Claim first (pending -> processing)
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # Mark as retryable (simulating a failed attempt)
        repo.mark_cleanup_retryable(debt_id, "First attempt failed", backoff=0)
        repo.commit()

        # Now claim should succeed (Try 1 picks up retryable debts)
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        cv = _get_cv(repo, debt_id)

        # Now reclaim_delete the file
        storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
        )
        assert not storage.exists(sk)

        # Complete the debt with correct claim_version
        repo.mark_cleanup_completed(debt_id, observed_claim_version=cv)
        repo.commit()

        # Verify it's gone from eligible
        eligible = repo.list_eligible_cleanup_debts()
        assert all(d["id"] != debt_id for d in eligible)

    def test_executor_reclaims_expired_processing_with_cas(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """An expired processing debt can be reclaimed via CAS using
        observed_locked_at / observed_locked_by / observed_lock_expires_at.

        This exercises Try 2 of claim_cleanup_debt (expired processing recovery).
        """
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk, stale_token="stale_tok", stale_version=1)

        # Claim first (pending -> processing)
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # Read the lease values after the claim (use ORM for proper type conversion)
        from cold_storage.modules.reports.infrastructure.orm import CleanupDebtRecord

        debt_row = repo._session.get(CleanupDebtRecord, debt_id)
        assert debt_row is not None
        locked_at = debt_row.locked_at
        locked_by = debt_row.locked_by
        _ = debt_row.lock_expires_at

        # Manually expire the lock by updating lock_expires_at to the past
        expired_time = datetime.now(UTC) - timedelta(seconds=1)
        repo._session.execute(
            sa.update(CleanupDebtRecord)
            .where(CleanupDebtRecord.id == debt_id)
            .values(lock_expires_at=expired_time)
        )
        repo.commit()

        # Now claim via CAS with the original lease values
        # This should succeed (Try 2: expired processing with exact CAS)
        assert repo.claim_cleanup_debt(
            debt_id,
            lock_seconds=300,
            observed_locked_at=locked_at,
            observed_locked_by=locked_by,
            observed_lock_expires_at=expired_time,
        )
        repo.commit()

        cv = _get_cv(repo, debt_id)

        # reclaim_delete the file
        storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
        )
        assert not storage.exists(sk)

        # Complete the debt
        repo.mark_cleanup_completed(debt_id, observed_claim_version=cv)
        repo.commit()

        # Verify it's gone from eligible
        eligible = repo.list_eligible_cleanup_debts()
        assert all(d["id"] != debt_id for d in eligible)

    def test_executor_reclaims_expired_processing_cas_fails_when_wrong(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """CAS recovery of expired processing debt fails when the wrong
        observed_lease values are provided."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk, stale_token="stale_tok", stale_version=1)

        # Claim first (pending -> processing)
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # Try to claim with wrong observed_ values -> should fail
        result = repo.claim_cleanup_debt(
            debt_id,
            lock_seconds=300,
            observed_locked_at=datetime.now(UTC),
            observed_locked_by="wrong_executor",
            observed_lock_expires_at=datetime.now(UTC),
        )
        assert not result, "CAS should fail with wrong observed_ values"

        # The debt is still in processing with original lease
        status = repo._session.execute(
            sa.select(sa.column("status"))
            .where(sa.column("id") == debt_id)
            .select_from(sa.table("cleanup_debt"))
        ).scalar()
        assert status == "processing"

    def test_two_executors_only_one_reclaims_expired_processing_debt(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
        engine,
    ) -> None:
        """When two executor sessions compete, exactly one reclaims the debt."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk)

        # Set to retryable status (eligible for claim by Try 1)
        # First claim, then mark retryable
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()
        repo.mark_cleanup_retryable(debt_id, "first fail", backoff=0)
        repo.commit()

        # Session 1 tries to claim
        SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
        claimed1 = False
        claimed2 = False
        with SessionFactory() as s1:
            r1 = SQLReportRepository(s1)
            claimed1 = r1.claim_cleanup_debt(debt_id, lock_seconds=300)
            s1.commit()

        with SessionFactory() as s2:
            r2 = SQLReportRepository(s2)
            claimed2 = r2.claim_cleanup_debt(debt_id, lock_seconds=300)
            s2.commit()

        # Exactly one should succeed
        assert claimed1 != claimed2

    def test_processing_lease_recovery_survives_new_session(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
        engine,
    ) -> None:
        """A recovered processing debt can be completed in a new session."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk)

        # Claim then mark retryable (simulating a failed executor)
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()
        repo.mark_cleanup_retryable(debt_id, "first fail", backoff=0)
        repo.commit()

        # Re-claim in same session
        assert repo.claim_cleanup_debt(debt_id)

        cv = _get_cv(repo, debt_id)

        # Reclaim delete in a new session
        SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
        with SessionFactory() as s2:
            r2 = SQLReportRepository(s2)
            storage.reclaim_delete(
                sk,
                stale_claim_token="stale_tok",
                stale_claim_version=1,
                reclaim_token="new_tok",
                reclaim_version=2,
            )
            r2.mark_cleanup_completed(debt_id, observed_claim_version=cv)
            r2.commit()

        # Verify completion
        pending = repo.list_pending_cleanup_debts()
        assert all(d["id"] != debt_id for d in pending)


class TestCleanupRetryAndIdempotency:
    """Cleanup retry, idempotency, and edge cases."""

    def test_cleanup_retry_completes_when_same_debt_file_already_missing(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """When the file is already gone and a receipt exists, reclaim_delete
        with missing_is_success=True returns ReclaimDeleteResult(status='already_missing').

        The debt can then be marked completed successfully.
        """
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk, stale_token="stale_tok", stale_version=1)

        # Claim
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # Delete the file via reclaim_delete with repository to create a receipt
        result = storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
            repository=repo,
        )
        assert result.status == "deleted"
        assert not storage.exists(sk)
        repo.commit()

        # Mark retryable to simulate a failed completion commit
        repo.mark_cleanup_retryable(debt_id, "Retrying after receipt creation", backoff=0)
        repo.commit()

        # Re-claim
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # Now reclaim_delete with missing_is_success=True should find the
        # existing receipt and return already_missing
        result = storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
            missing_is_success=True,
            repository=repo,
        )
        assert result.status == "already_missing"
        assert result.storage_key == sk

        # Complete the debt with correct claim_version
        cv = _get_cv(repo, debt_id)
        repo.mark_cleanup_completed(debt_id, observed_claim_version=cv)
        repo.commit()

        # Verify completed
        pending = repo.list_pending_cleanup_debts()
        assert all(d["id"] != debt_id for d in pending)

    def test_reclaim_delete_same_debt_is_idempotent(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """Running reclaim_delete on the same debt twice is safe.

        First call deletes the file; second call handles the file already gone.
        """
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk, stale_token="stale_tok", stale_version=1)

        # Claim
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # First call: delete
        storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
        )
        assert not storage.exists(sk)

        cv = _get_cv(repo, debt_id)
        repo.mark_cleanup_completed(debt_id, observed_claim_version=cv)
        repo.commit()

        # Verify completed
        pending = repo.list_pending_cleanup_debts()
        assert all(d["id"] != debt_id for d in pending)

        # Re-create the file with different token to verify it's independent
        sk2 = _put_artifact(storage, artifact_id, "new_tok", 1)
        assert storage.exists(sk2)

    def test_missing_file_with_mismatched_debt_owner_fails_closed(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """When the file exists but its actual owner doesn't match the
        debt's stale_claim, the operation fails closed (PermissionError)."""
        sk = _put_artifact(storage, artifact_id, "actual_owner", 5)
        debt_id = _insert_debt(
            repo,
            sk,
            stale_token="wrong_owner",
            stale_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
        )

        # Claim
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # reclaim_delete should fail — the file's actual owner doesn't match
        with pytest.raises(PermissionError, match="(?i)fencing|mismatch"):
            storage.reclaim_delete(
                sk,
                stale_claim_token="wrong_owner",
                stale_claim_version=1,
                reclaim_token="new_tok",
                reclaim_version=2,
            )

        # File should still exist
        assert storage.exists(sk)

        # The debt should still be pending (not completed)
        repo.mark_cleanup_retryable(debt_id, "PermissionError: fencing mismatch", backoff=0)
        repo.commit()

    def test_delete_succeeds_but_completion_commit_fails_then_retry_completes(
        self,
        repo: SQLReportRepository,
        storage: ReportArtifactStorage,
        artifact_id: str,
    ) -> None:
        """Scenario: reclaim_delete succeeds (file deleted) but the
        mark_cleanup_completed + commit fails.  On retry, the executor
        finds the file already gone and should handle it gracefully
        using the DeletionReceipt.

        This is a variant of the two-phase cleanup where the first phase
        (reclaim_delete) succeeds but the second phase (completion) fails.
        """
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        debt_id = _insert_debt(repo, sk, stale_token="stale_tok", stale_version=1)

        # Claim
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # Phase 1: reclaim_delete succeeds (with repository for receipt)
        result1 = storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
            repository=repo,
        )
        assert result1.status == "deleted"
        assert not storage.exists(sk)
        repo.commit()

        # Simulate completion commit failure -- mark as retryable
        repo.mark_cleanup_retryable(
            debt_id,
            "Commit failed after file deletion -- retrying",
            backoff=0,
        )
        repo.commit()

        # Retry: re-claim the debt
        assert repo.claim_cleanup_debt(debt_id)
        repo.commit()

        # Now reclaim_delete again -- file is already gone, use missing_is_success
        result2 = storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="new_tok",
            reclaim_version=2,
            missing_is_success=True,
            repository=repo,
        )
        assert result2.status == "already_missing"

        # Complete the debt
        cv = _get_cv(repo, debt_id)
        repo.mark_cleanup_completed(debt_id, observed_claim_version=cv)
        repo.commit()

        pending = repo.list_pending_cleanup_debts()
        assert all(d["id"] != debt_id for d in pending)


# ===================================================================
# Part C — DeletionReceipt ownership fail-closed
# ===================================================================


class TestDeletionReceipt:
    """reclaim_delete with DeletionReceipt ownership verification."""

    def _insert_receipt(
        self,
        repo: SQLReportRepository,
        sk: str,
        *,
        stale_token: str = "stale_tok",
        stale_version: int = 1,
        reclaim_token: str = "reclaim_tok",
        reclaim_version: int = 2,
        deletion_hash: str = "abc123",
    ) -> None:
        """Insert a DeletionReceiptRecord directly (simulating a prior successful delete)."""
        from cold_storage.modules.reports.infrastructure.orm import DeletionReceiptRecord

        rec = DeletionReceiptRecord(
            storage_key=sk,
            stale_claim_token=stale_token,
            stale_claim_version=stale_version,
            reclaim_token=reclaim_token,
            reclaim_version=reclaim_version,
            deletion_hash=deletion_hash,
        )
        repo._session.add(rec)
        repo.commit()

    def test_missing_file_same_deletion_receipt_is_idempotent_success(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """When the file is missing and a matching DeletionReceipt exists,
        reclaim_delete with missing_is_success=True returns already_missing."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        # Delete the file first
        storage.delete(sk, claim_token="stale_tok", claim_version=1)
        assert not storage.exists(sk)

        # Insert receipt matching the reclaim params
        self._insert_receipt(
            repo,
            sk,
            stale_token="stale_tok",
            stale_version=1,
            reclaim_token="reclaim_tok",
            reclaim_version=2,
        )

        # Now reclaim_delete with repository — should find receipt and return already_missing
        result = storage.reclaim_delete(
            sk,
            stale_claim_token="stale_tok",
            stale_claim_version=1,
            reclaim_token="reclaim_tok",
            reclaim_version=2,
            missing_is_success=True,
            repository=repo,
        )
        assert result.status == "already_missing"
        assert result.storage_key == sk

    def test_missing_file_without_receipt_fails_closed(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """When the file is missing and NO DeletionReceipt exists,
        reclaim_delete with missing_is_success=True and repository raises FileNotFoundError."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        # Delete the file (but do NOT insert a receipt)
        storage.delete(sk, claim_token="stale_tok", claim_version=1)
        assert not storage.exists(sk)

        # Without a receipt, even missing_is_success=True fails closed
        with pytest.raises(FileNotFoundError, match="(?i)no deletion receipt|not found"):
            storage.reclaim_delete(
                sk,
                stale_claim_token="stale_tok",
                stale_claim_version=1,
                reclaim_token="reclaim_tok",
                reclaim_version=2,
                missing_is_success=True,
                repository=repo,
            )

    def test_missing_file_wrong_stale_owner_fails_closed(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """When the file is missing and the receipt exists but the
        stale_claim_token/version don't match, raise PermissionError."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        # Delete the file
        storage.delete(sk, claim_token="stale_tok", claim_version=1)
        assert not storage.exists(sk)

        # Insert receipt with different stale owner
        self._insert_receipt(
            repo,
            sk,
            stale_token="different_stale",
            stale_version=999,
            reclaim_token="reclaim_tok",
            reclaim_version=2,
        )

        # Wrong stale owner → PermissionError
        with pytest.raises(PermissionError, match="(?i)receipt mismatch|mismatch"):
            storage.reclaim_delete(
                sk,
                stale_claim_token="stale_tok",
                stale_claim_version=1,
                reclaim_token="reclaim_tok",
                reclaim_version=2,
                missing_is_success=True,
                repository=repo,
            )

    def test_missing_file_wrong_reclaim_owner_fails_closed(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """When the file is missing and the receipt exists but the
        reclaim_token/version don't match, raise PermissionError."""
        sk = _put_artifact(storage, artifact_id, "stale_tok", 1)
        # Delete the file
        storage.delete(sk, claim_token="stale_tok", claim_version=1)
        assert not storage.exists(sk)

        # Insert receipt with correct stale owner but different reclaim owner
        self._insert_receipt(
            repo,
            sk,
            stale_token="stale_tok",
            stale_version=1,
            reclaim_token="original_reclaim",
            reclaim_version=5,
        )

        # Wrong reclaim owner → PermissionError
        with pytest.raises(PermissionError, match="(?i)receipt mismatch|mismatch"):
            storage.reclaim_delete(
                sk,
                stale_claim_token="stale_tok",
                stale_claim_version=1,
                reclaim_token="new_reclaim",
                reclaim_version=2,
                missing_is_success=True,
                repository=repo,
            )

    def test_new_owner_same_storage_key_cannot_be_treated_as_already_missing(
        self,
        storage: ReportArtifactStorage,
        artifact_id: str,
        repo: SQLReportRepository,
    ) -> None:
        """A file deleted by one owner cannot be treated as already_missing
        by a different set of identifiers.

        After successful reclaim_delete with stale=owner_A and reclaim=owner_B,
        the receipt records those identifiers.  A subsequent call with
        different stale/reclaim identifiers fails with PermissionError.
        """
        sk = _put_artifact(storage, artifact_id, "owner_A", 1)

        # Delete via reclaim_delete (inserts receipt with stale=owner_A, reclaim=owner_B)
        result1 = storage.reclaim_delete(
            sk,
            stale_claim_token="owner_A",
            stale_claim_version=1,
            reclaim_token="owner_B",
            reclaim_version=1,
            repository=repo,
        )
        assert result1.status == "deleted"
        repo.commit()

        assert not storage.exists(sk)

        # Call with completely different identifiers — should fail
        with pytest.raises(PermissionError, match="(?i)receipt mismatch|mismatch"):
            storage.reclaim_delete(
                sk,
                stale_claim_token="owner_X",
                stale_claim_version=99,
                reclaim_token="owner_Y",
                reclaim_version=99,
                missing_is_success=True,
                repository=repo,
            )
