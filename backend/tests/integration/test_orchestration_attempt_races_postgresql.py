"""PostgreSQL attempt acquire constraint-isolation tests.

Each test targets exactly ONE production constraint so the captured
PostgreSQL constraint name proves that specific recovery path executed.

Scenarios:
  1. uq_attempt_identity_number ONLY — different attempt numbers, only one
     RUNNING; loser retries with next number and succeeds.
  2. uq_attempt_one_running ONLY — different attempt numbers, both RUNNING;
     loser re-reads live lease and raises AttemptAlreadyRunningError.
  3. Stale takeover CAS — heartbeat-based compare-and-swap.
  4. Bounded retry exhaustion — CAS always misses → typed conflict error
     with precise retry count; session remains usable (no rollback).
  5. Non-target integrity errors — FK / NOT NULL / CHECK / non-target UNIQUE
     propagate through production classifier as NON_TARGET.

Requires a real PostgreSQL instance.  Tagged with ``@pytest.mark.postgresql``.

Thread-synchronisation:
  Uses ``threading.Event`` for deterministic interleaving.  Each hook in
  thread A/B uses events to pause/resume, ensuring the targeted constraint
  window is hit reliably.
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
    AttemptInsertConflictKind,
    SqlAlchemyOrchestrationAttemptRepository,
    _classify_attempt_insert_integrity_error,
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
    """Seed project, version, snapshot, coefficient context, and identity."""
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


# ── Hook classes ─────────────────────────────────────────────────────


class _IdentityNumberConflictHooks:
    """Pauses Thread A after computing next attempt_number so that Thread B
    can insert a COMPLETED row with the same number via direct ORM.

    Thread A then resumes, tries the same number through production
    acquire(), hits ONLY uq_attempt_identity_number, retries with N+2,
    and succeeds.

    Records captured state for audit assertions.
    """

    def __init__(self) -> None:
        self.a_read_number = threading.Event()
        self.b_committed = threading.Event()
        self.thread_a_id: int | None = None
        # Captured state
        self.captured_constraints: list[str | None] = []
        self.first_next_number: int | None = None
        self.retry_next_number: int | None = None
        self.retry_state_refreshes: list[dict[str, object]] = []

    def after_running_lookup(
        self, *, identity_id: str, running_attempt: dict[str, object] | None, retry_index: int
    ) -> None:
        pass

    def after_next_number_read(
        self, *, identity_id: str, next_attempt_number: int, retry_index: int
    ) -> None:
        if threading.get_ident() == self.thread_a_id:
            if retry_index == 0:
                self.first_next_number = next_attempt_number
                self.a_read_number.set()
                self.b_committed.wait(timeout=15)
            else:
                self.retry_next_number = next_attempt_number

    def before_attempt_flush(
        self, *, identity_id: str, attempt_number: int, retry_index: int
    ) -> None:
        pass

    def after_integrity_conflict(
        self,
        *,
        constraint_name: str | None,
        identity_id: str,
        attempt_number: int,
        retry_index: int,
    ) -> None:
        if threading.get_ident() == self.thread_a_id:
            self.captured_constraints.append(constraint_name)

    def after_retry_state_refresh(
        self,
        *,
        identity_id: str,
        running_attempt: dict[str, object] | None,
        max_attempt_number: int,
        retry_index: int,
    ) -> None:
        if threading.get_ident() == self.thread_a_id:
            self.retry_state_refreshes.append(
                {
                    "retry_index": retry_index,
                    "running_attempt": running_attempt,
                    "max_attempt_number": max_attempt_number,
                }
            )


class _OneRunningConflictHooks:
    """Pauses both threads before ``session.flush()``, then releases A first.

    Thread B uses a number-shifted repo subclass so both threads compute
    different attempt numbers.  Only ``uq_attempt_one_running`` fires.
    """

    def __init__(self) -> None:
        self.a_at_flush = threading.Event()
        self.b_at_flush = threading.Event()
        self.release_a = threading.Event()
        self.release_b = threading.Event()
        self.thread_ids: dict[str, int] = {}
        # Captured state
        self.captured_constraints: list[str | None] = []
        self.a_running_lookups: list[dict[str, object] | None] = []
        self.b_running_lookups: list[dict[str, object] | None] = []
        self.a_attempt_number: int | None = None
        self.b_attempt_number: int | None = None
        self.retry_state_refreshes: list[dict[str, object]] = []

    def after_running_lookup(
        self, *, identity_id: str, running_attempt: dict[str, object] | None, retry_index: int
    ) -> None:
        tid = threading.get_ident()
        if tid == self.thread_ids.get("a"):
            self.a_running_lookups.append(running_attempt)
        elif tid == self.thread_ids.get("b"):
            self.b_running_lookups.append(running_attempt)

    def after_next_number_read(
        self, *, identity_id: str, next_attempt_number: int, retry_index: int
    ) -> None:
        tid = threading.get_ident()
        if tid == self.thread_ids.get("a"):
            self.a_attempt_number = next_attempt_number
        elif tid == self.thread_ids.get("b"):
            self.b_attempt_number = next_attempt_number

    def before_attempt_flush(
        self, *, identity_id: str, attempt_number: int, retry_index: int
    ) -> None:
        tid = threading.get_ident()
        if tid == self.thread_ids.get("a"):
            self.a_at_flush.set()
            self.release_a.wait(timeout=15)
        elif tid == self.thread_ids.get("b"):
            self.b_at_flush.set()
            self.release_b.wait(timeout=15)

    def after_integrity_conflict(
        self,
        *,
        constraint_name: str | None,
        identity_id: str,
        attempt_number: int,
        retry_index: int,
    ) -> None:
        tid = threading.get_ident()
        if tid == self.thread_ids.get("b"):
            self.captured_constraints.append(constraint_name)

    def after_retry_state_refresh(
        self,
        *,
        identity_id: str,
        running_attempt: dict[str, object] | None,
        max_attempt_number: int,
        retry_index: int,
    ) -> None:
        tid = threading.get_ident()
        if tid == self.thread_ids.get("b"):
            self.retry_state_refreshes.append(
                {
                    "retry_index": retry_index,
                    "running_attempt": running_attempt,
                    "max_attempt_number": max_attempt_number,
                }
            )


class _NumberShiftingAttemptRepo(SqlAlchemyOrchestrationAttemptRepository):
    """Shifts the computed next attempt number for a designated thread.

    Used to give Thread B a different number than Thread A so that only
    ``uq_attempt_one_running`` (not ``uq_attempt_identity_number``) fires.
    """

    def __init__(
        self,
        *,
        hooks=None,
        shift_thread_id: int,
        shift: int = 1,
    ) -> None:
        super().__init__(hooks=hooks)
        self._shift_thread_id = shift_thread_id
        self._shift = shift

    def get_max_attempt_number(self, session, identity_id: str) -> int:
        base = super().get_max_attempt_number(session, identity_id)
        if threading.get_ident() == self._shift_thread_id:
            return base + self._shift
        return base


class _HeartbeatMutatingHooks:
    """Mutates the running attempt's heartbeat on every ``after_running_lookup``
    so that the CAS ``UPDATE … WHERE heartbeat_at = observed`` always misses.
    """

    def __init__(self, session_factory) -> None:
        self._sf = session_factory
        self.lookup_count = 0
        self.retry_indexes: list[int] = []

    def after_running_lookup(
        self,
        *,
        identity_id: str,
        running_attempt: dict[str, object] | None,
        retry_index: int,
    ) -> None:
        if running_attempt is not None:
            self.lookup_count += 1
            self.retry_indexes.append(retry_index)
            new_stale = datetime.now(UTC) - timedelta(minutes=10, seconds=self.lookup_count)
            with self._sf() as s:
                s.execute(
                    OrchestrationRunAttemptRecord.__table__.update()
                    .where(OrchestrationRunAttemptRecord.id == running_attempt["id"])
                    .values(heartbeat_at=new_stale)
                )
                s.commit()

    def after_next_number_read(self, **_kw: object) -> None:
        pass

    def before_attempt_flush(self, **_kw: object) -> None:
        pass

    def after_integrity_conflict(self, **_kw: object) -> None:
        pass

    def after_retry_state_refresh(self, **_kw: object) -> None:
        pass


# ── Test 1: uq_attempt_identity_number only ──────────────────────────


class TestIdentityNumberConflict:
    """Proves isolation of uq_attempt_identity_number recovery.

    Setup: one COMPLETED attempt (number=1).  Thread A computes next=2 and
    pauses.  Thread B inserts attempt_number=2 as COMPLETED via direct ORM
    and commits.  Thread A resumes → inserts (2, RUNNING) through production
    acquire() → PostgreSQL hits ONLY ``uq_attempt_identity_number`` →
    savepoint rollback → re-reads max=2, next=3 → inserts (3, RUNNING) →
    succeeds.
    """

    def test_identity_number_conflict_recomputes_and_inserts_next_number(
        self, pg_database: str, pg_session_factory
    ) -> None:
        # ── Seed ────────────────────────────────────────────────────
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

        hooks = _IdentityNumberConflictHooks()
        repo = SqlAlchemyOrchestrationAttemptRepository(hooks=hooks)
        now = datetime.now(UTC)
        result_a: dict[str, object] = {}
        result_b: dict[str, object] = {}

        # ── Thread A ────────────────────────────────────────────────
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
                    except (AttemptAlreadyRunningError, AttemptTakeoverConflictError) as exc:
                        result_a["error"] = exc
                        result_a["session_usable"] = _check_session_usable(session)
            except Exception as exc:  # noqa: BLE001
                result_a["unexpected"] = exc

        # ── Thread B ────────────────────────────────────────────────
        def _thread_b() -> None:
            try:
                hooks.a_read_number.wait(timeout=15)
                # Insert a COMPLETED attempt with the same number via direct ORM
                with pg_session_factory() as session:
                    session.add(
                        OrchestrationRunAttemptRecord(
                            id="att-b-2",
                            identity_id="ident-1",
                            attempt_number=2,
                            status="COMPLETED",
                            heartbeat_at=datetime.now(UTC),
                            started_at=datetime.now(UTC),
                            completed_at=datetime.now(UTC),
                        )
                    )
                    session.commit()
                    result_b["inserted_number"] = 2
            except Exception as exc:  # noqa: BLE001
                result_b["unexpected"] = exc
            finally:
                hooks.b_committed.set()

        # ── Run ─────────────────────────────────────────────────────
        t_a = threading.Thread(target=_thread_a)
        t_b = threading.Thread(target=_thread_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not t_a.is_alive(), "Thread A deadlocked"
        assert not t_b.is_alive(), "Thread B deadlocked"

        # ── Thread A succeeded ──────────────────────────────────────
        assert "unexpected" not in result_a, f"Unexpected: {result_a}"
        assert "unexpected" not in result_b, f"Unexpected: {result_b}"
        assert "attempt_id" in result_a, f"Thread A should succeed: {result_a}"
        assert "error" not in result_a, f"Thread A should not error: {result_a}"

        # ── Captured constraint names ───────────────────────────────
        assert hooks.captured_constraints == ["uq_attempt_identity_number"], (
            f"Expected only identity_number conflict, got: {hooks.captured_constraints}"
        )

        # ── Number computation proof ────────────────────────────────
        assert hooks.first_next_number == 2, (
            f"First next should be 2, got {hooks.first_next_number}"
        )
        assert hooks.retry_next_number == 3, (
            f"Retry next should be 3, got {hooks.retry_next_number}"
        )
        assert len(hooks.retry_state_refreshes) == 1

        # ── Database final state ────────────────────────────────────
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
            assert len(attempts) == 3
            # Seed: number=1 COMPLETED
            assert attempts[0].attempt_number == 1
            assert attempts[0].status == "COMPLETED"
            # Thread B: number=2 COMPLETED
            assert attempts[1].attempt_number == 2
            assert attempts[1].status == "COMPLETED"
            # Thread A: number=3 RUNNING (recovered with N+2)
            assert attempts[2].attempt_number == 3
            assert attempts[2].status == "RUNNING"
            assert attempts[2].id == result_a["attempt_id"]

            numbers = [a.attempt_number for a in attempts]
            assert len(numbers) == len(set(numbers)), "Duplicate attempt numbers"


# ── Test 2: uq_attempt_one_running only ──────────────────────────────


class TestOneRunningConflict:
    """Proves isolation of uq_attempt_one_running recovery.

    Both threads use production acquire() but Thread B's repo shifts its
    computed number by +1 so that Thread A gets number=2 and Thread B gets
    number=3.  Both are RUNNING.  Only ``uq_attempt_one_running`` fires
    for Thread B.
    """

    def test_one_running_conflict_rereads_live_lease(
        self, pg_database: str, pg_session_factory
    ) -> None:
        # ── Seed ────────────────────────────────────────────────────
        with pg_session_factory() as s:
            _seed_identity(s)
            # Pre-seed one COMPLETED so both compute next=2 (A) / next=3 (B shifted)
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

        hooks = _OneRunningConflictHooks()
        now = datetime.now(UTC)
        result_a: dict[str, object] = {}
        result_b: dict[str, object] = {}

        # Thread A: normal repo
        repo_a = SqlAlchemyOrchestrationAttemptRepository(hooks=hooks)
        # Thread B: number-shifted repo (shift=1 so next=3 instead of 2)
        repo_b: SqlAlchemyOrchestrationAttemptRepository

        # ── Thread A ────────────────────────────────────────────────
        def _thread_a() -> None:
            try:
                hooks.thread_ids["a"] = threading.get_ident()
                with pg_session_factory() as session:
                    aid = repo_a.acquire(
                        session,
                        identity_id="ident-1",
                        heartbeat_at=now,
                    )
                    session.commit()
                    result_a["attempt_id"] = aid
            except Exception as exc:  # noqa: BLE001
                result_a["unexpected"] = exc

        # ── Thread B ────────────────────────────────────────────────
        def _thread_b() -> None:
            try:
                hooks.thread_ids["b"] = threading.get_ident()
                # Create repo_b here so it captures the correct thread ID
                nonlocal repo_b
                repo_b = _NumberShiftingAttemptRepo(
                    hooks=hooks,
                    shift_thread_id=threading.get_ident(),
                    shift=1,
                )
                with pg_session_factory() as session:
                    try:
                        aid = repo_b.acquire(
                            session,
                            identity_id="ident-1",
                            heartbeat_at=now + timedelta(seconds=1),
                        )
                        session.commit()
                        result_b["attempt_id"] = aid
                    except AttemptAlreadyRunningError as exc:
                        result_b["error"] = exc
                        result_b["session_usable"] = _check_session_usable(session)
            except Exception as exc:  # noqa: BLE001
                result_b["unexpected"] = exc

        # ── Run ─────────────────────────────────────────────────────
        t_a = threading.Thread(target=_thread_a)
        t_b = threading.Thread(target=_thread_b)
        t_a.start()
        t_b.start()

        # Wait for both to reach flush point
        assert hooks.a_at_flush.wait(timeout=15), "Thread A did not reach flush"
        assert hooks.b_at_flush.wait(timeout=15), "Thread B did not reach flush"

        # Release A first → A inserts RUNNING, commits
        hooks.release_a.set()
        t_a.join(timeout=15)
        assert not t_a.is_alive(), "Thread A deadlocked"

        # Release B → B tries → uq_attempt_one_running
        hooks.release_b.set()
        t_b.join(timeout=15)
        assert not t_b.is_alive(), "Thread B deadlocked"

        # ── Assertions ──────────────────────────────────────────────
        assert "unexpected" not in result_a, f"Unexpected: {result_a}"
        assert "unexpected" not in result_b, f"Unexpected: {result_b}"

        # Thread A succeeds
        assert "attempt_id" in result_a, f"Thread A should succeed: {result_a}"

        # Thread B gets AttemptAlreadyRunningError
        assert "error" in result_b, f"Thread B should get error: {result_b}"
        assert isinstance(result_b["error"], AttemptAlreadyRunningError)
        assert result_b.get("session_usable") is True

        # Both threads initially saw no RUNNING
        assert hooks.a_running_lookups[0] is None
        assert hooks.b_running_lookups[0] is None

        # Numbers were different
        assert hooks.a_attempt_number == 2
        assert hooks.b_attempt_number == 3

        # Constraint name
        assert hooks.captured_constraints == ["uq_attempt_one_running"], (
            f"Expected only one_running conflict, got: {hooks.captured_constraints}"
        )

        # B's retry_state_refresh saw A's live RUNNING
        assert len(hooks.retry_state_refreshes) == 1
        refresh = hooks.retry_state_refreshes[0]
        assert refresh["running_attempt"] is not None

        # Database: exactly 1 RUNNING attempt (A's)
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
    """Stale attempt CAS takeover via production acquire()."""

    def test_stale_lease_takeover_success(self, pg_database: str, pg_session_factory) -> None:
        """acquire() finds an expired RUNNING → CAS takeover → inserts new RUNNING."""
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
        RUNNING → AttemptAlreadyRunningError.
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
        barrier = threading.Barrier(2, timeout=15)

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
    """CAS conflict on every retry → AttemptTakeoverConflictError."""

    def test_retry_exhaustion_preserves_session_read_and_write_capability(
        self, pg_database: str, pg_session_factory
    ) -> None:
        """Hooks mutate heartbeat on every lookup so CAS always misses.

        After exactly _MAX_ACQUIRE_RETRIES (3) attempts, typed error is
        raised.  Session remains usable with real ORM write — no
        session-level rollback, non-empty flush, successful commit,
        and cross-session persistence verification.
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
            with pytest.raises(AttemptTakeoverConflictError) as exc_info:
                repo.acquire(
                    session,
                    identity_id="ident-1",
                    heartbeat_at=datetime.now(UTC),
                )

            err = exc_info.value
            assert err.code == "ORCH_ATTEMPT_TAKEOVER_CONFLICT"
            assert err.details["identity_id"] == "ident-1"
            assert err.details["attempt_id"] == "att-exhaust"
            assert err.details["retry_count"] == repo._MAX_ACQUIRE_RETRIES

            # ── Session read capability (no rollback needed) ────────
            val = session.execute(
                select(func.count()).select_from(OrchestrationRunAttemptRecord)
            ).scalar()
            assert val is not None

            # ── Real ORM write + non-empty flush ────────────────────
            project = session.execute(
                select(ProjectRecord).where(ProjectRecord.id == "p-1")
            ).scalar_one()
            project.name = "Session Still Writable"
            session.flush()

            # Verify write is visible within this transaction
            reloaded = session.execute(
                select(ProjectRecord.name).where(ProjectRecord.id == "p-1")
            ).scalar_one()
            assert reloaded == "Session Still Writable"

            # Commit succeeds
            session.commit()

        # Cross-session persistence verification
        with pg_session_factory() as s:
            persisted = s.execute(
                select(ProjectRecord.name).where(ProjectRecord.id == "p-1")
            ).scalar_one()
            assert persisted == "Session Still Writable"

        # Precise retry count
        assert hooks.lookup_count == repo._MAX_ACQUIRE_RETRIES
        assert hooks.retry_indexes == [0, 1, 2]

        # Attempt is still RUNNING — CAS never succeeded
        with pg_session_factory() as s:
            row = s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == "att-exhaust"
                )
            ).scalar_one()
            assert row.status == "RUNNING"


# ── Test 5: Non-target integrity errors ───────────────────────────────


class TestNonTargetIntegrityErrors:
    """FK / NOT NULL / CHECK / non-target UNIQUE violations must propagate
    through the production classifier as NON_TARGET.
    """

    def test_fk_violation_through_acquire(self, pg_database: str, pg_session_factory) -> None:
        """acquire() with non-existent identity_id → FK IntegrityError."""
        repo = SqlAlchemyOrchestrationAttemptRepository()
        with pg_session_factory() as session:
            nested = session.begin_nested()
            with pytest.raises(IntegrityError):
                repo.acquire(
                    session,
                    identity_id="nonexistent-identity",
                    heartbeat_at=datetime.now(UTC),
                )
            nested.rollback()

    def test_fk_violation_classified_non_target(self, pg_database: str, pg_session_factory) -> None:
        """FK IntegrityError is classified as NON_TARGET by production classifier."""
        repo = SqlAlchemyOrchestrationAttemptRepository()
        with pg_session_factory() as session:
            nested = session.begin_nested()
            try:
                repo.acquire(
                    session,
                    identity_id="nonexistent-identity",
                    heartbeat_at=datetime.now(UTC),
                )
            except IntegrityError as exc:
                kind = _classify_attempt_insert_integrity_error(exc)
                assert kind is AttemptInsertConflictKind.NON_TARGET
                nested.rollback()
                return
            nested.rollback()
            pytest.fail("Expected IntegrityError")

    def test_not_null_violation_classified_non_target(
        self, pg_database: str, pg_session_factory
    ) -> None:
        """NOT NULL violation → classifier returns NON_TARGET."""
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
            try:
                session.flush()
            except IntegrityError as exc:
                kind = _classify_attempt_insert_integrity_error(exc)
                assert kind is AttemptInsertConflictKind.NON_TARGET
                nested.rollback()
                return
            nested.rollback()
            pytest.fail("Expected IntegrityError")

    def test_check_violation_classified_non_target(
        self, pg_database: str, pg_session_factory
    ) -> None:
        """CHECK constraint violation → classifier returns NON_TARGET."""
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
                failure_code="should-not-be-set",
            )
            session.add(rec)
            try:
                session.flush()
            except IntegrityError as exc:
                kind = _classify_attempt_insert_integrity_error(exc)
                assert kind is AttemptInsertConflictKind.NON_TARGET
                nested.rollback()
                return
            nested.rollback()
            pytest.fail("Expected IntegrityError")

    def test_non_target_unique_classified_non_target(
        self, pg_database: str, pg_session_factory
    ) -> None:
        """UNIQUE violation on non-target constraint → NON_TARGET."""
        with pg_session_factory() as s:
            _seed_identity(s)

        with pg_session_factory() as session:
            rec = OrchestrationRunAttemptRecord(
                id="att-uniq-1",
                identity_id="ident-1",
                attempt_number=1,
                status="RUNNING",
                heartbeat_at=datetime.now(UTC),
            )
            session.add(rec)
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
            try:
                session.flush()
            except IntegrityError as exc:
                kind = _classify_attempt_insert_integrity_error(exc)
                assert kind is AttemptInsertConflictKind.NON_TARGET
                pg_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
                assert pg_name == "uq_orch_identity_fingerprint"
                nested.rollback()
                session.commit()
                return
            nested.rollback()
            session.commit()
            pytest.fail("Expected IntegrityError")


# ── Helpers ──────────────────────────────────────────────────────────


def _check_session_usable(session) -> bool:
    """Verify session can still execute queries after an error."""
    try:
        cnt = session.execute(
            select(func.count()).select_from(OrchestrationRunAttemptRecord)
        ).scalar()
        return cnt is not None
    except Exception:  # noqa: BLE001
        return False
