"""PostgreSQL attempt acquire race-condition integration tests.

Verifies that concurrent attempt acquisition correctly handles:
  1. uq_attempt_identity_number race — two sessions competing for the same
     attempt_number → one gets UNIQUE violation → savepoint rollback →
     reread → AttemptAlreadyRunningError.
  2. uq_attempt_one_running race — two sessions both trying to create a
     RUNNING attempt → one gets UNIQUE violation → savepoint rollback →
     AttemptAlreadyRunningError.
  3. Stale takeover CAS — heartbeat-based compare-and-swap for expired
     RUNNING attempts, including concurrent CAS conflict.
  4. Bounded retry exhaustion — CAS conflict leads to retry exhaustion.
  5. Non-target integrity errors — FK, CHECK, NOT NULL violations
     propagate as-is and are NOT caught by the attempt retry logic.

Requires a real PostgreSQL instance.  Tagged with ``@pytest.mark.postgresql``.

Thread-synchronization approach:
  Uses ``threading.Event`` for deterministic interleaving.  Each hook in
  thread A/B uses events to pause/resume, ensuring the race window is
  hit reliably rather than depending on OS scheduling luck.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from cold_storage.modules.orchestration.domain.errors import (
    AttemptAlreadyRunningError,
    AttemptTakeoverConflictError,
)
from cold_storage.modules.orchestration.infrastructure.orm import (
    CoefficientContextRecord,
    OrchestrationIdentityRecord,
    OrchestrationRunAttemptRecord,
    ProjectVersionExecutionSnapshotRecord,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    SqlAlchemyOrchestrationAttemptRepository,
)
from cold_storage.modules.projects.infrastructure.orm import (
    ProjectRecord,
    ProjectVersionRecord,
)

pytestmark = pytest.mark.postgresql


# ── Seed helpers ──────────────────────────────────────────────────────


def _seed_identity(
    session,
    *,
    identity_id: str = "ident-1",
    fingerprint: str = "fp-test-001",
    project_id: str = "p-1",
    version_id: str = "pv-1",
) -> str:
    """Seed a project, version, snapshot, coefficient context, and identity.

    Returns the identity_id.
    """
    session.add(
        ProjectRecord(
            id=project_id,
            code=f"T_{project_id}",
            name="Test Project",
            location="test",
            product_category="blueberry",
            created_at=datetime.now(UTC),
        )
    )
    session.flush()
    session.add(
        ProjectVersionRecord(
            id=version_id,
            project_id=project_id,
            version_number=1,
            change_summary="test",
            created_by="test",
            status="approved",
            created_at=datetime.now(UTC),
            input_snapshot={"throughput_t": "25.0"},
        )
    )
    session.flush()
    snap = ProjectVersionExecutionSnapshotRecord(
        id="snap-1",
        project_id=project_id,
        project_version_id=version_id,
        version_number=1,
        input_snapshot={"throughput_t": "25.0"},
        input_snapshot_hash="hash-snap",
        schema_version="1.0.0",
        captured_status="approved",
    )
    session.add(snap)
    coeff = CoefficientContextRecord(
        id="coeff-1",
        project_id=project_id,
        project_version_id=version_id,
        content={"coefficients": []},
        content_hash="hash-coeff",
        schema_version="1.0.0",
    )
    session.add(coeff)
    session.flush()
    identity = OrchestrationIdentityRecord(
        id=identity_id,
        fingerprint=fingerprint,
        execution_snapshot_id="snap-1",
        coefficient_context_id="coeff-1",
        definition_version="1.0.0",
        calculator_version_vector={
            "zone": "1.0.0",
            "cooling_load": "1.0.0",
            "equipment": "1.0.0",
            "power": "1.0.0",
            "investment": "1.0.0",
        },
        status="ACTIVE",
    )
    session.add(identity)
    session.commit()
    return identity_id


# ── Hook classes for deterministic thread synchronization ─────────────


class _IdentityNumberRaceHooks:
    """Pauses thread A after computing next attempt_number.

    Thread A signals ``a_read_number``; thread B waits for it before
    calling ``acquire()``.  Thread B signals ``b_committed`` after its
    session commits, unblocking thread A.
    """

    def __init__(self) -> None:
        self.a_read_number = threading.Event()
        self.b_committed = threading.Event()
        self.thread_a_id: int | None = None

    def after_running_lookup(self, **_kw: object) -> None:
        pass

    def after_next_number_read(self, **_kw: object) -> None:
        if threading.get_ident() == self.thread_a_id:
            self.a_read_number.set()
            self.b_committed.wait(timeout=10)

    def before_attempt_flush(self, **_kw: object) -> None:
        pass

    def after_integrity_conflict(self, **_kw: object) -> None:
        pass


class _OneRunningRaceHooks:
    """Pauses both threads before ``session.flush()``, then releases in order.

    Both threads signal ``*_at_flush`` when they reach the flush point.
    The test releases thread A first (``release_a``), waits for it to
    complete, then releases thread B (``release_b``).
    """

    def __init__(self) -> None:
        self.a_at_flush = threading.Event()
        self.b_at_flush = threading.Event()
        self.release_a = threading.Event()
        self.release_b = threading.Event()
        self.thread_ids: dict[str, int] = {}

    def after_running_lookup(self, **_kw: object) -> None:
        pass

    def after_next_number_read(self, **_kw: object) -> None:
        pass

    def before_attempt_flush(self, **_kw: object) -> None:
        tid = threading.get_ident()
        if tid == self.thread_ids.get("a"):
            self.a_at_flush.set()
            self.release_a.wait(timeout=10)
        elif tid == self.thread_ids.get("b"):
            self.b_at_flush.set()
            self.release_b.wait(timeout=10)

    def after_integrity_conflict(self, **_kw: object) -> None:
        pass


class _HeartbeatMutatingHooks:
    """Mutates the running attempt's heartbeat on every ``after_running_lookup``.

    Because the mutation is committed in a *separate* session, the CAS
    ``UPDATE … WHERE heartbeat_at = observed`` inside ``takeover_stale()``
    sees the new value (READ COMMITTED) and returns ``rowcount=0``.
    """

    def __init__(self, session_factory) -> None:
        self._sf = session_factory
        self.lookup_count = 0

    def after_running_lookup(
        self, *, running_attempt: dict[str, object] | None, **_kw: object
    ) -> None:
        if running_attempt is not None:
            self.lookup_count += 1
            with self._sf() as s:
                s.execute(
                    OrchestrationRunAttemptRecord.__table__.update()
                    .where(OrchestrationRunAttemptRecord.id == running_attempt["id"])
                    .values(heartbeat_at=datetime.now(UTC))
                )
                s.commit()

    def after_next_number_read(self, **_kw: object) -> None:
        pass

    def before_attempt_flush(self, **_kw: object) -> None:
        pass

    def after_integrity_conflict(self, **_kw: object) -> None:
        pass


# ── Test 1: uq_attempt_identity_number race ──────────────────────────


class TestIdentityNumberRace:
    """True dual-transaction race for ``uq_attempt_identity_number``.

    Setup: pre-seed identity with ONE COMPLETED attempt (number=1).

    Thread A pauses after computing ``next_attempt_number=2``.
    Thread B runs ``acquire()`` to completion (inserts 2, commits).
    Thread A resumes → tries to insert 2 → UNIQUE violation → savepoint
    rollback → re-reads → sees B's live RUNNING →
    ``AttemptAlreadyRunningError``.
    """

    def test_identity_number_race(self, pg_database: str, pg_session_factory) -> None:
        # ── Setup ─────────────────────────────────────────────────────
        with pg_session_factory() as s:
            _seed_identity(s)
            s.add(
                OrchestrationRunAttemptRecord(
                    id="att-seed",
                    identity_id="ident-1",
                    attempt_number=1,
                    status="COMPLETED",
                    heartbeat_at=datetime.now(UTC),
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                )
            )
            s.commit()

        hooks = _IdentityNumberRaceHooks()
        repo = SqlAlchemyOrchestrationAttemptRepository(hooks=hooks)
        now = datetime.now(UTC)
        result_a: dict[str, object] = {}
        result_b: dict[str, object] = {}

        # ── Thread A ──────────────────────────────────────────────────
        def _thread_a() -> None:
            try:
                hooks.thread_a_id = threading.get_ident()
                with pg_session_factory() as session:
                    try:
                        aid = repo.acquire(
                            session,
                            identity_id="ident-1",
                            heartbeat_at=now,
                        )
                        session.commit()
                        result_a["attempt_id"] = aid
                    except AttemptAlreadyRunningError as exc:
                        result_a["error"] = exc
                        # Verify session is still usable after the error.
                        cnt = session.execute(
                            select(func.count()).select_from(OrchestrationRunAttemptRecord)
                        ).scalar()
                        result_a["session_usable"] = cnt is not None
            except Exception as exc:  # noqa: BLE001
                result_a["unexpected"] = exc

        # ── Thread B ──────────────────────────────────────────────────
        def _thread_b() -> None:
            try:
                hooks.a_read_number.wait(timeout=10)
                with pg_session_factory() as session:
                    aid = repo.acquire(
                        session,
                        identity_id="ident-1",
                        heartbeat_at=now + timedelta(seconds=1),
                    )
                    session.commit()
                    result_b["attempt_id"] = aid
            except Exception as exc:  # noqa: BLE001
                result_b["unexpected"] = exc
            finally:
                hooks.b_committed.set()

        # ── Run ───────────────────────────────────────────────────────
        t_a = threading.Thread(target=_thread_a)
        t_b = threading.Thread(target=_thread_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not t_a.is_alive(), "Thread A deadlocked"
        assert not t_b.is_alive(), "Thread B deadlocked"

        # ── Assertions ────────────────────────────────────────────────
        assert "error" in result_a, f"Expected AttemptAlreadyRunningError, got: {result_a}"
        assert isinstance(result_a["error"], AttemptAlreadyRunningError)
        assert result_a.get("session_usable") is True
        assert "unexpected" not in result_a

        assert "attempt_id" in result_b, f"Thread B failed: {result_b}"
        assert "unexpected" not in result_b

        # Database: exactly 2 attempts, no duplicate attempt numbers.
        with pg_session_factory() as s:
            attempts = (
                s.execute(
                    select(OrchestrationRunAttemptRecord)
                    .where(OrchestrationRunAttemptRecord.identity_id == "ident-1")
                    .order_by(OrchestrationRunAttemptRecord.attempt_number)
                )
                .scalars()
                .all()
            )
            assert len(attempts) == 2
            assert attempts[0].attempt_number == 1
            assert attempts[0].status == "COMPLETED"
            assert attempts[1].attempt_number == 2
            assert attempts[1].status == "RUNNING"
            numbers = [a.attempt_number for a in attempts]
            assert len(numbers) == len(set(numbers)), "Duplicate attempt numbers"


# ── Test 2: uq_attempt_one_running race ──────────────────────────────


class TestOneRunningRace:
    """True dual-transaction race for ``uq_attempt_one_running``.

    Both threads see no RUNNING attempt (fresh identity).
    Both pause just before ``session.flush()``.
    Thread A is released first → flushes + commits.
    Thread B is released → flush → ``uq_attempt_one_running`` → savepoint
    rollback → re-reads → sees A's live RUNNING →
    ``AttemptAlreadyRunningError``.
    """

    def test_one_running_race(self, pg_database: str, pg_session_factory) -> None:
        # ── Setup ─────────────────────────────────────────────────────
        with pg_session_factory() as s:
            _seed_identity(s)

        hooks = _OneRunningRaceHooks()
        repo = SqlAlchemyOrchestrationAttemptRepository(hooks=hooks)
        now = datetime.now(UTC)
        result_a: dict[str, object] = {}
        result_b: dict[str, object] = {}

        # ── Thread A ──────────────────────────────────────────────────
        def _thread_a() -> None:
            try:
                hooks.thread_ids["a"] = threading.get_ident()
                with pg_session_factory() as session:
                    try:
                        aid = repo.acquire(
                            session,
                            identity_id="ident-1",
                            heartbeat_at=now,
                        )
                        session.commit()
                        result_a["attempt_id"] = aid
                    except AttemptAlreadyRunningError as exc:
                        result_a["error"] = exc
            except Exception as exc:  # noqa: BLE001
                result_a["unexpected"] = exc

        # ── Thread B ──────────────────────────────────────────────────
        def _thread_b() -> None:
            try:
                hooks.thread_ids["b"] = threading.get_ident()
                with pg_session_factory() as session:
                    try:
                        aid = repo.acquire(
                            session,
                            identity_id="ident-1",
                            heartbeat_at=now + timedelta(seconds=1),
                        )
                        session.commit()
                        result_b["attempt_id"] = aid
                    except AttemptAlreadyRunningError as exc:
                        result_b["error"] = exc
                        # Verify session is still usable.
                        cnt = session.execute(
                            select(func.count()).select_from(OrchestrationRunAttemptRecord)
                        ).scalar()
                        result_b["session_usable"] = cnt is not None
            except Exception as exc:  # noqa: BLE001
                result_b["unexpected"] = exc

        # ── Run ───────────────────────────────────────────────────────
        t_a = threading.Thread(target=_thread_a)
        t_b = threading.Thread(target=_thread_b)
        t_a.start()
        t_b.start()

        # Wait for both threads to reach the flush point.
        assert hooks.a_at_flush.wait(timeout=10), "Thread A did not reach before_attempt_flush"
        assert hooks.b_at_flush.wait(timeout=10), "Thread B did not reach before_attempt_flush"

        # Release A first → A inserts RUNNING, commits.
        hooks.release_a.set()
        t_a.join(timeout=10)
        assert not t_a.is_alive(), "Thread A deadlocked"

        # Release B → B tries to insert → conflict.
        hooks.release_b.set()
        t_b.join(timeout=10)
        assert not t_b.is_alive(), "Thread B deadlocked"

        # ── Assertions ────────────────────────────────────────────────
        assert "attempt_id" in result_a, f"Thread A failed: {result_a}"
        assert "unexpected" not in result_a

        assert "error" in result_b, f"Expected AttemptAlreadyRunningError for B, got: {result_b}"
        assert isinstance(result_b["error"], AttemptAlreadyRunningError)
        assert result_b.get("session_usable") is True
        assert "unexpected" not in result_b

        # Database: exactly 1 RUNNING attempt (A's).
        with pg_session_factory() as s:
            running = (
                s.execute(
                    select(OrchestrationRunAttemptRecord).where(
                        OrchestrationRunAttemptRecord.identity_id == "ident-1",
                        OrchestrationRunAttemptRecord.status == "RUNNING",
                    )
                )
                .scalars()
                .all()
            )
            assert len(running) == 1
            assert running[0].id == result_a["attempt_id"]


# ── Test 3: Stale takeover CAS ────────────────────────────────────────


class TestStaleLeaseConcurrent:
    """Stale attempt CAS takeover via ``acquire()``."""

    def test_stale_lease_takeover_success(self, pg_database: str, pg_session_factory) -> None:
        """``acquire()`` finds an expired RUNNING attempt → CAS takeover →
        inserts a new RUNNING attempt."""
        with pg_session_factory() as s:
            _seed_identity(s)

        stale_time = datetime.now(UTC) - timedelta(minutes=10)
        with pg_session_factory() as session:
            session.add(
                OrchestrationRunAttemptRecord(
                    id="att-stale",
                    identity_id="ident-1",
                    attempt_number=1,
                    status="RUNNING",
                    heartbeat_at=stale_time,
                )
            )
            session.commit()

        repo = SqlAlchemyOrchestrationAttemptRepository()
        now = datetime.now(UTC)

        with pg_session_factory() as session:
            new_id = repo.acquire(session, identity_id="ident-1", heartbeat_at=now)
            session.commit()

        # Old attempt is ABANDONED, new is RUNNING.
        with pg_session_factory() as s:
            old = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == "att-stale"
                )
            ).scalar_one()
            assert old.status == "ABANDONED"
            assert old.completed_at is not None

            new = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == new_id
                )
            ).scalar_one()
            assert new.status == "RUNNING"
            assert new.attempt_number == 2

    def test_concurrent_stale_cas_race(self, pg_database: str, pg_session_factory) -> None:
        """Two threads race to CAS-takeover the same stale attempt.

        Exactly one succeeds; the other re-reads → sees the winner's live
        RUNNING → ``AttemptAlreadyRunningError``.
        """
        with pg_session_factory() as s:
            _seed_identity(s)

        stale_time = datetime.now(UTC) - timedelta(minutes=10)
        with pg_session_factory() as session:
            session.add(
                OrchestrationRunAttemptRecord(
                    id="att-stale-race",
                    identity_id="ident-1",
                    attempt_number=1,
                    status="RUNNING",
                    heartbeat_at=stale_time,
                )
            )
            session.commit()

        repo = SqlAlchemyOrchestrationAttemptRepository()
        now = datetime.now(UTC)
        result_a: dict[str, object] = {}
        result_b: dict[str, object] = {}
        barrier = threading.Barrier(2, timeout=10)

        def _thread_fn(heartbeat: datetime, result: dict[str, object]) -> None:
            try:
                barrier.wait()
                with pg_session_factory() as session:
                    try:
                        aid = repo.acquire(
                            session,
                            identity_id="ident-1",
                            heartbeat_at=heartbeat,
                        )
                        session.commit()
                        result["attempt_id"] = aid
                    except AttemptAlreadyRunningError as exc:
                        result["error"] = exc
            except Exception as exc:  # noqa: BLE001
                result["unexpected"] = exc

        t_a = threading.Thread(target=_thread_fn, args=(now, result_a))
        t_b = threading.Thread(target=_thread_fn, args=(now + timedelta(seconds=1), result_b))
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not t_a.is_alive(), "Thread A deadlocked"
        assert not t_b.is_alive(), "Thread B deadlocked"

        successes = [r for r in (result_a, result_b) if "attempt_id" in r]
        errors = [r for r in (result_a, result_b) if "error" in r]
        assert len(successes) == 1, f"Expected 1 success: {successes}"
        assert len(errors) == 1, f"Expected 1 error: {errors}"
        assert isinstance(errors[0]["error"], AttemptAlreadyRunningError)

        # Database: exactly 1 RUNNING attempt.
        with pg_session_factory() as s:
            running = (
                s.execute(
                    select(OrchestrationRunAttemptRecord).where(
                        OrchestrationRunAttemptRecord.identity_id == "ident-1",
                        OrchestrationRunAttemptRecord.status == "RUNNING",
                    )
                )
                .scalars()
                .all()
            )
            assert len(running) == 1


# ── Test 4: Bounded retry exhaustion ─────────────────────────────────


class TestBoundedRetryExhaustion:
    """CAS conflict on every retry → ``AttemptTakeoverConflictError``."""

    def test_retry_exhaustion_via_heartbeat_mutation(
        self, pg_database: str, pg_session_factory
    ) -> None:
        """Hooks mutate heartbeat on every ``after_running_lookup`` so that
        ``takeover_stale()`` CAS always misses → after
        ``_MAX_ACQUIRE_RETRIES`` (3) attempts:
        ``AttemptTakeoverConflictError``.
        """
        with pg_session_factory() as s:
            _seed_identity(s)

        stale_time = datetime.now(UTC) - timedelta(minutes=10)
        with pg_session_factory() as session:
            session.add(
                OrchestrationRunAttemptRecord(
                    id="att-exhaust",
                    identity_id="ident-1",
                    attempt_number=1,
                    status="RUNNING",
                    heartbeat_at=stale_time,
                )
            )
            session.commit()

        hooks = _HeartbeatMutatingHooks(pg_session_factory)
        repo = SqlAlchemyOrchestrationAttemptRepository(hooks=hooks)

        with pg_session_factory() as session:
            with pytest.raises(AttemptTakeoverConflictError):
                repo.acquire(
                    session,
                    identity_id="ident-1",
                    heartbeat_at=datetime.now(UTC),
                )
            session.rollback()

        # Each retry fires after_running_lookup once.
        assert hooks.lookup_count >= 3, f"Expected ≥3 lookups, got {hooks.lookup_count}"

        # Attempt is still RUNNING — CAS never succeeded.
        with pg_session_factory() as s:
            row = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == "att-exhaust"
                )
            ).scalar_one()
            assert row.status == "RUNNING"


# ── Test 5: Non-target integrity errors propagate ────────────────────


class TestNonTargetIntegrityErrors:
    """FK, CHECK, NOT NULL violations must propagate as-is — NOT caught
    by the attempt retry logic (which only targets ``uq_attempt_*``
    constraints).
    """

    def test_fk_violation_through_acquire(self, pg_database: str, pg_session_factory) -> None:
        """``acquire()`` with non-existent identity_id → FK ``IntegrityError``
        propagates (not caught by the retry logic)."""
        repo = SqlAlchemyOrchestrationAttemptRepository()
        with pg_session_factory() as session:
            nested = session.begin_nested()
            with pytest.raises(IntegrityError) as exc_info:
                repo.acquire(
                    session,
                    identity_id="nonexistent-identity",
                    heartbeat_at=datetime.now(UTC),
                )
            err_str = str(exc_info.value)
            assert "uq_attempt_identity_number" not in err_str
            assert "uq_attempt_one_running" not in err_str
            assert (
                "orchestration_run_attempts_identity_id_fkey" in err_str
                or "foreign key" in err_str.lower()
            )
            nested.rollback()

    def test_not_null_violation_propagates(self, pg_database: str, pg_session_factory) -> None:
        """NOT NULL violation on required column → ``IntegrityError``
        propagates."""
        with pg_session_factory() as s:
            _seed_identity(s)

        with pg_session_factory() as session:
            nested = session.begin_nested()
            rec = OrchestrationRunAttemptRecord(
                id="att-nn-bad",
                identity_id="ident-1",
                attempt_number=None,  # type: ignore[arg-type]
                status="RUNNING",
                heartbeat_at=datetime.now(UTC),
            )
            session.add(rec)
            with pytest.raises(IntegrityError) as exc_info:
                session.flush()
            err_str = str(exc_info.value)
            assert "uq_attempt_identity_number" not in err_str
            assert "uq_attempt_one_running" not in err_str
            nested.rollback()

    def test_check_violation_propagates(self, pg_database: str, pg_session_factory) -> None:
        """CHECK constraint violation on a related table propagates."""
        with pg_session_factory() as session:
            nested = session.begin_nested()
            from cold_storage.modules.orchestration.infrastructure.orm import (
                OrchestrationRequestRecord,
            )

            rec = OrchestrationRequestRecord(
                id="req-check-bad",
                requested_project_id="p-1",
                requested_project_version_id="pv-1",
                request_fingerprint="fp-check-bad",
                actor="test",
                correlation_id="corr-check",
                status="PENDING",
                failure_code="should-not-be-set",  # violates CHECK
            )
            session.add(rec)
            with pytest.raises(IntegrityError) as exc_info:
                session.flush()
            err_str = str(exc_info.value)
            assert "uq_attempt_identity_number" not in err_str
            assert "uq_attempt_one_running" not in err_str
            assert "ck_orch_request_status_nullity" in err_str or "check" in err_str.lower()
            nested.rollback()

    def test_non_target_unique_violation_propagates(
        self, pg_database: str, pg_session_factory
    ) -> None:
        """A UNIQUE violation on a non-target constraint propagates."""
        with pg_session_factory() as s:
            _seed_identity(s)

        with pg_session_factory() as session:
            rec1 = OrchestrationRunAttemptRecord(
                id="att-uniq-1",
                identity_id="ident-1",
                attempt_number=1,
                status="RUNNING",
                heartbeat_at=datetime.now(UTC),
            )
            session.add(rec1)
            session.flush()

            nested = session.begin_nested()
            dup_identity = OrchestrationIdentityRecord(
                id="ident-dup",
                fingerprint="fp-test-001",  # duplicate fingerprint
                execution_snapshot_id="snap-1",
                coefficient_context_id="coeff-1",
                definition_version="1.0.0",
                calculator_version_vector={"zone": "1.0.0"},
                status="ACTIVE",
            )
            session.add(dup_identity)
            with pytest.raises(IntegrityError) as exc_info:
                session.flush()
            err_str = str(exc_info.value)
            assert "uq_orch_identity_fingerprint" in err_str
            assert "uq_attempt_identity_number" not in err_str
            assert "uq_attempt_one_running" not in err_str
            nested.rollback()
            session.commit()
