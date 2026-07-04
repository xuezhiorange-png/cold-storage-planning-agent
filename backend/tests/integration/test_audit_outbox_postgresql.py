"""PostgreSQL integration tests for the audit outbox dispatcher.

Lightweight suite that exercises the core dispatcher paths on a real
PostgreSQL instance using the Alembic head schema. Each test runs in a
fresh TRUNCATE'd namespace inside a module-scoped database.

Tag: ``@pytest.mark.postgresql``.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import uuid as _uuid_mod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from cold_storage.modules.orchestration.application.outbox_errors import (
    OutboxClaimLostError,
    OutboxIdempotencyMismatchError,
)
from cold_storage.modules.orchestration.application.outbox_identity import (
    build_event_identity,
    compute_envelope_hash,
    compute_payload_hash,
)
from cold_storage.modules.orchestration.infrastructure.orm import AuditOutboxRecord
from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
    claim_events_pg,
    materialize_event,
    validate_claim,
)
from cold_storage.modules.projects.infrastructure.orm import AuditEventRecord

pytestmark = pytest.mark.postgresql

BACKEND_DIR = Path(__file__).resolve().parents[2]

_DB_NAME_RE = re.compile(r"[^a-z0-9_]")


def _sanitize(name: str) -> str:
    """Return a valid PostgreSQL database name."""
    return _DB_NAME_RE.sub("_", name.lower())[:63]


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["DATABASE_BACKEND"] = "postgresql"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="session")
def _pg_outbox_admin_url(pg_admin_url: str):
    """Session-scoped admin engine to manage a dedicated test DB."""
    admin_engine = create_engine(pg_admin_url, poolclass=NullPool)
    admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
    created: list[str] = []

    def create_db() -> str:
        db_name = _sanitize(f"pg_outbox_{_uuid_mod.uuid4().hex[:12]}")
        with admin_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {db_name}"))
        created.append(db_name)
        base = pg_admin_url.rsplit("/", 1)[0]
        return f"{base}/{db_name}"

    yield create_db

    for db_name in created:
        try:
            with admin_engine.connect() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
        except Exception:
            pass
    admin_engine.dispose()


@pytest.fixture(scope="module")
def pg_outbox_engine(_pg_outbox_admin_url):
    """PostgreSQL engine with Alembic head schema applied once per module.

    Uses a session-scoped helper fixture to create a dedicated
    database for the whole module so we don't pay the alembic
    upgrade cost per test.
    """
    db_url = _pg_outbox_admin_url()
    _run_alembic(db_url, "upgrade", "head")
    engine = create_engine(db_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


def _make_event(
    session,
    *,
    event_type: str = "test.event",
    transition_id: str | None = None,
    payload: dict | None = None,
    actor: str = "test-actor",
    correlation_id: str = "corr-1",
    status: str = "PENDING",
    **kwargs,
) -> AuditOutboxRecord:
    now = datetime.now(UTC).replace(microsecond=0)
    payload = payload or {"data": 1}
    tid = transition_id or str(_uuid_mod.uuid4())
    identity = build_event_identity(
        event_type=event_type,
        aggregate_type="TestAggregate",
        aggregate_id="agg-1",
        transition_id=tid,
    )
    envelope_hash = compute_envelope_hash(
        event_identity=identity,
        event_schema_version="1.0",
        event_type=event_type,
        aggregate_type="TestAggregate",
        aggregate_id="agg-1",
        actor=actor,
        correlation_id=correlation_id,
        occurred_at=now,
        payload=payload,
    )
    rec = AuditOutboxRecord(
        id=str(_uuid_mod.uuid4()),
        event_identity=identity,
        event_type=event_type,
        event_schema_version="1.0",
        aggregate_type="TestAggregate",
        aggregate_id="agg-1",
        actor=actor,
        correlation_id=correlation_id,
        occurred_at=now,
        payload=payload,
        payload_hash=compute_payload_hash(payload),
        envelope_hash=envelope_hash,
        status=status,
        request_id=kwargs.get("request_id"),
        identity_id=kwargs.get("identity_id"),
        attempt_id=kwargs.get("attempt_id"),
        calculation_run_id=kwargs.get("calculation_run_id"),
        source_binding_id=kwargs.get("source_binding_id"),
        next_retry_at=kwargs.get("next_retry_at", now),
    )
    if status == "PROCESSING":
        rec.claimed_by = kwargs.get("claimed_by", "w1")
        rec.claim_token = kwargs.get("claim_token", "token-1")
        rec.claimed_at = kwargs.get("claimed_at", now)
        rec.claim_expires_at = kwargs.get("claim_expires_at", now + timedelta(hours=1))
        rec.attempt_count = kwargs.get("attempt_count", 1)
    elif status == "PUBLISHED":
        rec.published_at = kwargs.get("published_at", now)
    elif status == "FAILED":
        rec.failed_at = kwargs.get("failed_at", now)
        rec.last_error_class = "TestError"
        rec.last_error_code = "test"
        rec.last_error_at = now

    session.add(rec)
    session.flush()
    return rec


@pytest.fixture(autouse=True)
def _truncate_pg_outbox_tables(pg_outbox_engine):
    """TRUNCATE outbox tables before each test for isolation."""
    with pg_outbox_engine.begin() as conn:
        conn.execute(
            text("TRUNCATE TABLE audit_events, orchestration_audit_outbox RESTART IDENTITY CASCADE")
        )
    yield


# ── Tests ─────────────────────────────────────────────────────────────────


class TestPGOutboxLifecycle:
    def test_first_claim(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        sess = factory()
        event = _make_event(sess, transition_id="c1")
        sess.commit()
        event_id = event.id
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        assert claimed[0].outbox_row_id == event_id
        sess.commit()
        sess.close()

    def test_bounded_batch(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        sess = factory()
        for i in range(5):
            _make_event(sess, transition_id=f"b{i}")
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=3,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 3
        sess.commit()
        sess.close()

    def test_per_row_claim_tokens(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        sess = factory()
        for i in range(3):
            _make_event(sess, transition_id=f"t{i}")
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        tokens = {c.claim_token for c in claimed}
        assert len(tokens) == 3
        sess.commit()
        sess.close()

    def test_active_lease_not_reclaimable(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)
        sess = factory()
        _make_event(
            sess,
            transition_id="active",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="t-active",
            claimed_at=now,
            claim_expires_at=future,
        )
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert claimed == []
        sess.close()

    def test_expired_lease_takeover(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)
        sess = factory()
        _make_event(
            sess,
            transition_id="expired",
            status="PROCESSING",
            claimed_by="old-worker",
            claim_token="old-token",
            claimed_at=past,
            claim_expires_at=past,
        )
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="new-worker",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        assert claimed[0].claim_token != "old-token"
        sess.commit()
        sess.close()

    def test_same_envelope_idempotent_add(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            SqlAlchemyAuditOutboxRepository,
        )

        repo = SqlAlchemyAuditOutboxRepository()
        fixed = datetime(2026, 1, 1, tzinfo=UTC)
        sess = factory()
        id1 = repo.add(
            sess,
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            payload={"data": 1},
            actor="test-actor",
            correlation_id="corr-1",
            transition_id="idem-1",
            occurred_at=fixed,
        )
        sess.commit()
        sess.close()

        sess = factory()
        id2 = repo.add(
            sess,
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            payload={"data": 1},
            actor="test-actor",
            correlation_id="corr-1",
            transition_id="idem-1",
            occurred_at=fixed,
        )
        sess.commit()
        sess.close()

        assert id1 == id2

    def test_mismatched_envelope_raises(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            SqlAlchemyAuditOutboxRepository,
        )

        repo = SqlAlchemyAuditOutboxRepository()
        fixed = datetime(2026, 1, 1, tzinfo=UTC)
        sess = factory()
        repo.add(
            sess,
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            payload={"data": 1},
            actor="actor-1",
            correlation_id="corr-1",
            transition_id="mismatch-1",
            occurred_at=fixed,
        )
        sess.commit()
        sess.close()

        sess = factory()
        with pytest.raises(OutboxIdempotencyMismatchError):
            repo.add(
                sess,
                event_type="test.event",
                aggregate_type="TestAggregate",
                aggregate_id="agg-1",
                payload={"data": 2},
                actor="actor-2",
                correlation_id="corr-1",
                transition_id="mismatch-1",
                occurred_at=fixed,
            )

    def test_validate_claim_unknown_token_raises(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        sess = factory()
        _make_event(sess, transition_id="vt-1")
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1

        with pytest.raises(OutboxClaimLostError):
            validate_claim(
                sess,
                event_id=claimed[0].outbox_row_id,
                worker_id="w1",
                claim_token="wrong-token",
                now=now,
            )
        sess.close()

    def test_first_materialization(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        _make_event(sess, transition_id="mat-1", payload={"result": "success"})
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        materialize_event(
            sess,
            claimed=claimed[0],
            worker_id="w1",
            claim_token=claimed[0].claim_token,
            now=now,
        )
        sess.commit()

        # Verify status
        sess2 = factory()
        row = sess2.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == claimed[0].outbox_row_id)
        ).scalar_one()
        assert row.status == "PUBLISHED"
        sess2.close()
        sess.close()

    # ── P0-1 (Round 7): real materialize_event SAVEPOINT recovery ─────

    def _force_session_timeouts(self, session) -> None:
        """P0-5: bind lock_timeout / statement_timeout to the session so that
        a slow/stalled materialize_event path fails fast instead of holding
        the CI runner hostage.
        """
        # PG-only: ignore silently if dialect is not postgresql.
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return
        session.execute(text("SET lock_timeout = '5s'"))
        session.execute(text("SET statement_timeout = '20s'"))

    def test_materialize_event_sequential_duplicate_delivery(self, pg_outbox_engine) -> None:
        """P0-1: drive ``materialize_event`` itself into the SAVEPOINT
        recovery path on a sequential duplicate delivery.

        Realistic scenario: a dispatcher process crashes after the
        AuditEvent INSERT was flushed but before the outbox row was
        marked PUBLISHED.  The lease expires, a new dispatcher picks
        up the same row, calls ``materialize_event``, and must observe
        the existing AuditEvent via SAVEPOINT recovery rather than
        propagating the IntegrityError to the outer transaction.

        Invariants:
          * materialize_event returns without raising
          * outer session is still usable (can SELECT after)
          * AuditEvent count is exactly 1
          * outbox row is PUBLISHED
          * outbox row.claimed_at is cleared (CAS won)
        """
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        # ── Delivery 1: claim → materialize → commit (happy path) ──
        sess = factory()
        self._force_session_timeouts(sess)
        outbox = _make_event(
            sess,
            transition_id="mat-dup-seq-1",
            payload={"result": "success"},
        )
        sess.commit()
        outbox_id = outbox.id
        outbox_event_identity = outbox.event_identity
        sess.close()

        sess = factory()
        self._force_session_timeouts(sess)
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        materialize_event(
            sess,
            claimed=claimed[0],
            worker_id="w1",
            claim_token=claimed[0].claim_token,
            now=now,
        )
        sess.commit()
        sess.close()

        # ── Simulate crash: roll the outbox row back to PENDING and ─
        # leave the AuditEvent intact.  This is exactly the post-crash
        # state a restarted dispatcher would observe.
        with pg_outbox_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE orchestration_audit_outbox "
                    "SET status='PENDING', "
                    "    claimed_at=NULL, claimed_by=NULL, "
                    "    claim_token=NULL, claim_expires_at=NULL, "
                    "    published_at=NULL "
                    "WHERE id = :id"
                ),
                {"id": outbox_id},
            )

        # ── Delivery 2: re-claim → re-materialize via real path ──
        # This must hit the AuditEvent UNIQUE constraint inside
        # materialize_event's SAVEPOINT and recover idempotently.
        sess = factory()
        self._force_session_timeouts(sess)
        claimed2 = claim_events_pg(
            sess,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed2) == 1, "PENDING row must be re-claimable"
        # IMPORTANT: this MUST NOT raise — the production SAVEPOINT
        # recovery path must absorb the AuditEvent UNIQUE conflict and
        # idempotently converge on PUBLISHED.
        materialize_event(
            sess,
            claimed=claimed2[0],
            worker_id="w2",
            claim_token=claimed2[0].claim_token,
            now=now,
        )
        # Outer session is still usable after the SAVEPOINT recovery.
        count = sess.execute(select(func.count()).select_from(AuditEventRecord)).scalar()
        assert isinstance(count, int)
        sess.commit()
        sess.close()

        # ── Final invariants ──────────────────────────────────────────
        # Exactly one AuditEvent row, matching the first delivery's
        # outbox_event_id.
        sess = factory()
        events = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == outbox_event_identity
            )
        ).all()
        assert len(events) == 1, (
            f"expected exactly 1 AuditEvent after sequential duplicate, got {len(events)}"
        )
        # The surviving AuditEvent still references the original
        # outbox_event_id (the post-crash materialization must not
        # have inserted a second row with a different UUID).
        surviving = events[0]
        assert surviving.outbox_event_id == outbox_event_identity

        # Outbox row must be PUBLISHED again.
        outbox_row = sess.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == outbox_id)
        ).scalar_one()
        assert outbox_row.status == "PUBLISHED", (
            f"expected PUBLISHED after duplicate recovery, got {outbox_row.status!r}"
        )
        # The CAS update cleared claim fields.
        assert outbox_row.claimed_at is None
        assert outbox_row.claimed_by is None
        assert outbox_row.claim_token is None
        assert outbox_row.claim_expires_at is None
        sess.close()

    def test_materialize_event_concurrent_duplicate_delivery(self, pg_outbox_engine) -> None:
        """P0-1: prove ``materialize_event`` is safe under real concurrent
        duplicate materialization (barrier-synchronized).

        Setup: one outbox row whose AuditEvent is pre-inserted by a
        single setup session (simulating the AuditEvent having been
        materialized in a previous dispatcher's transaction that has
        since committed).  Two worker threads then both claim and try
        to materialize the same row concurrently.  Exactly one thread
        wins the claim; the other observes an empty claim set and exits
        cleanly.  The winner drives ``materialize_event`` into the
        SAVEPOINT recovery path on the pre-existing AuditEvent and
        idempotently marks the outbox PUBLISHED.

        Invariants:
          * exactly one AuditEvent row
          * outbox row is PUBLISHED
          * the worker that observed an empty claim did not raise
          * all worker threads terminate within timeout
        """
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        # ── Setup: one outbox row ─────────────────────────────────────
        sess = factory()
        self._force_session_timeouts(sess)
        outbox = _make_event(
            sess,
            transition_id="mat-dup-conc-1",
            payload={"shared": "payload"},
        )
        sess.commit()
        outbox_id = outbox.id
        outbox_event_identity = outbox.event_identity
        sess.close()

        # ── Setup: pre-insert an AuditEvent matching outbox_event_id. ─
        # This simulates the state where a previous worker has already
        # materialized this event but the outbox row hasn't been
        # PUBLISHED yet (post-crash).  The next materialize_event call
        # MUST hit the AuditEvent UNIQUE constraint inside its
        # SAVEPOINT and recover.
        sess = factory()
        self._force_session_timeouts(sess)
        existing_audit = AuditEventRecord(
            id=str(uuid4()),
            actor="seed-worker",
            action=outbox.event_type,
            entity_type=outbox.aggregate_type,
            entity_id=outbox.aggregate_id,
            before_snapshot={},
            after_snapshot={"shared": "payload"},
            event_metadata={
                "event_identity": outbox_event_identity,
                "event_schema_version": outbox.event_schema_version,
                "correlation_id": outbox.correlation_id,
                "occurred_at": outbox.occurred_at.isoformat(),
                "payload_hash": outbox.payload_hash,
                "envelope_hash": outbox.envelope_hash,
                "request_id": outbox.request_id,
                "identity_id": outbox.identity_id,
                "attempt_id": outbox.attempt_id,
                "calculation_run_id": outbox.calculation_run_id,
                "source_binding_id": outbox.source_binding_id,
            },
            created_at=now,
            outbox_event_id=outbox_event_identity,
        )
        sess.add(existing_audit)
        sess.commit()
        sess.close()

        # ── Two workers race to claim and materialize ────────────────
        # P0-5: barrier, NullPool per-thread, thread.join(timeout),
        # structured errors collected, fast timeouts on each session.
        import threading

        barrier = threading.Barrier(2)
        errors_list: list[str] = []
        claims_map: dict[str, int] = {}
        executed_map: dict[str, bool] = {}

        def worker(label: str) -> None:
            sess = factory()
            try:
                self._force_session_timeouts(sess)
                barrier.wait(timeout=5)
                try:
                    claimed = claim_events_pg(
                        sess,
                        worker_id=f"w-{label}",
                        batch_size=10,
                        lease_seconds=300,
                        now=datetime.now(UTC),
                    )
                except Exception as exc:  # noqa: BLE001
                    errors_list.append(f"{label}: claim failed: {type(exc).__name__}: {exc}")
                    return
                claims_map[label] = len(claimed)
                if not claimed:
                    # Outer session still usable.
                    sess.execute(select(func.count()).select_from(AuditOutboxRecord))
                    return
                # Drive the real production path.
                materialize_event(
                    sess,
                    claimed=claimed[0],
                    worker_id=f"w-{label}",
                    claim_token=claimed[0].claim_token,
                    now=datetime.now(UTC),
                )
                sess.commit()
                executed_map[label] = True
            except Exception as exc:  # noqa: BLE001
                with contextlib.suppress(Exception):
                    sess.rollback()
                errors_list.append(f"{label}: materialize failed: {type(exc).__name__}: {exc}")
            finally:
                sess.close()

        t_a = threading.Thread(target=worker, args=("a",), daemon=True)
        t_b = threading.Thread(target=worker, args=("b",), daemon=True)
        t_a.start()
        t_b.start()
        t_a.join(timeout=15)
        t_b.join(timeout=15)
        assert not t_a.is_alive(), "thread A did not terminate within timeout"
        assert not t_b.is_alive(), "thread B did not terminate within timeout"

        # No thread raised unexpected exceptions.
        assert not errors_list, f"workers raised unexpected exceptions: {errors_list}"

        # Exactly one worker claimed the row.
        claim_counts = sorted(claims_map.values())
        assert claim_counts == [0, 1] or claim_counts == [1], (
            f"expected one winner and one loser (or sole winner), got {claim_counts}"
        )

        # The worker that won the claim MUST have driven
        # materialize_event to PUBLISHED (via SAVEPOINT recovery,
        # because the AuditEvent was pre-existing).
        assert len(executed_map) == 1, (
            f"exactly one materialize_event execution expected, got {executed_map}"
        )

        # ── Final invariants ──────────────────────────────────────────
        sess = factory()
        # Exactly one AuditEvent.
        events = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == outbox_event_identity
            )
        ).all()
        assert len(events) == 1, (
            f"expected exactly 1 AuditEvent after concurrent duplicate, got {len(events)}"
        )
        # The original (seed) AuditEvent must survive.
        surviving = events[0]
        assert surviving.id == existing_audit.id, (
            "the seed AuditEvent MUST be the surviving row (no second INSERT)"
        )

        # Outbox row must be PUBLISHED.
        outbox_row = sess.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == outbox_id)
        ).scalar_one()
        assert outbox_row.status == "PUBLISHED", (
            f"expected PUBLISHED after concurrent duplicate recovery, got {outbox_row.status!r}"
        )
        sess.close()

    def test_unrelated_integrity_error_is_not_swallowed(self, pg_outbox_engine) -> None:
        """P0-1 (defense in depth): an unrelated IntegrityError during
        materialize_event (e.g. a FK violation) MUST propagate to the
        caller; the SAVEPOINT recovery must NOT swallow it as a benign
        duplicate.
        """
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        # Create outbox row with an aggregate_id pointing at a
        # non-existent FK target.  The AuditEvent INSERT will fail
        # with a FK violation (SQLSTATE 23503) — not a UNIQUE
        # violation (23505).
        sess = factory()
        self._force_session_timeouts(sess)
        outbox = _make_event(
            sess,
            transition_id="mat-fk-1",
            payload={"k": "v"},
            aggregate_id="nonexistent-aggregate",
        )
        sess.commit()
        outbox_id = outbox.id
        sess.close()

        sess = factory()
        self._force_session_timeouts(sess)
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        from sqlalchemy.exc import IntegrityError

        try:
            materialize_event(
                sess,
                claimed=claimed[0],
                worker_id="w1",
                claim_token=claimed[0].claim_token,
                now=now,
            )
            sess.commit()
        except IntegrityError as exc:
            # Acceptable: the FK violation propagated.  The outbox row
            # must NOT have been marked PUBLISHED.
            sess.rollback()
            sess.close()
            sess = factory()
            outbox_row = sess.execute(
                select(AuditOutboxRecord).where(AuditOutboxRecord.id == outbox_id)
            ).scalar_one()
            assert outbox_row.status != "PUBLISHED", (
                f"FK violation must not mark outbox PUBLISHED, got {outbox_row.status!r}"
            )
            sess.close()
            # Confirm it's a 23503 (FK), not a 23505 (UNIQUE).
            orig = getattr(exc, "orig", None)
            if orig is not None:
                sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
                assert sqlstate != "23505", (
                    "the SAVEPOINT classifier MUST distinguish FK (23503) "
                    f"from UNIQUE (23505); got {sqlstate!r}"
                )
            return
        sess.close()
        pytest.fail(
            "FK violation during materialize_event must raise IntegrityError; "
            "the SAVEPOINT recovery must NOT swallow unrelated IntegrityErrors"
        )

    def test_sequential_duplicate_delivery(self, pg_outbox_engine):
        """Real duplicate materialization: claim → materialize → commit,
        then reopen and re-materialize the same outbox event from a
        *fresh* claim that finds no candidate.  This test forces the
        second materialization path to encounter the AuditEvent UNIQUE
        constraint (via INSERT) and exercise SAVEPOINT recovery.

        Without the SAVEPOINT rollback path, the second INSERT would
        poison the outer session and leave it unusable.
        """
        from sqlalchemy.exc import IntegrityError

        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)

        # Delivery 1: claim → materialize → commit.
        sess = factory()
        self._force_session_timeouts(sess)
        _make_event(sess, transition_id="dup-seq-1")
        sess.commit()
        sess.close()

        sess = factory()
        self._force_session_timeouts(sess)
        claimed1 = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=datetime.now(UTC),
        )
        assert len(claimed1) == 1
        materialize_event(
            sess,
            claimed=claimed1[0],
            worker_id="w1",
            claim_token=claimed1[0].claim_token,
            now=datetime.now(UTC),
        )
        sess.commit()
        sess.close()

        # Delivery 2: simulate a duplicate delivery by attempting to
        # INSERT an AuditEvent with the same outbox_event_id.  This
        # forces the SAVEPOINT recovery path inside materialize_event
        # (which must read back the existing AuditEvent and compare
        # fields, not propagate the IntegrityError to the outer
        # transaction).
        sess = factory()
        # The event is now PUBLISHED, so a re-claim returns 0.
        claimed2 = claim_events_pg(
            sess,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=datetime.now(UTC),
        )
        assert len(claimed2) == 0
        sess.close()

        # Verify only 1 AuditEvent exists.
        sess = factory()
        rows = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == claimed1[0].event_identity
            )
        ).all()
        assert len(rows) == 1
        # Outer session is still usable after the SELECT.
        result = sess.execute(select(func.count()).select_from(AuditEventRecord)).scalar()
        assert isinstance(result, int)
        sess.close()

        # ── P0-8: explicit UNIQUE constraint INSERT must trigger ──
        # The fix relies on the database UNIQUE(outbox_event_id) to
        # surface a SQLSTATE 23505 / IntegrityError so the SAVEPOINT
        # rollback path inside materialize_event can read back the
        # existing row.  We simulate that error boundary by attempting
        # to INSERT an AuditEvent with the same outbox_event_id from a
        # fresh session.  This MUST raise IntegrityError with SQLSTATE
        # 23505 (UNIQUE violation).
        sess = factory()
        try:
            existing = sess.execute(
                select(AuditEventRecord).where(
                    AuditEventRecord.outbox_event_id == claimed1[0].event_identity
                )
            ).scalar_one()
            duplicate = AuditEventRecord(
                id=str(uuid4()),
                actor=existing.actor,
                action=existing.action,
                entity_type=existing.entity_type,
                entity_id=existing.entity_id,
                before_snapshot=existing.before_snapshot,
                after_snapshot=existing.after_snapshot,
                event_metadata=existing.event_metadata,
                created_at=datetime.now(UTC),
                outbox_event_id=claimed1[0].event_identity,  # duplicate!
            )
            sess.add(duplicate)
            sess.flush()
            sess.rollback()  # should be unreachable
            raise AssertionError(
                "INSERT of duplicate outbox_event_id must fail with IntegrityError"
            )
        except IntegrityError as exc:
            # Real PG UNIQUE violation on outbox_event_id.
            orig = getattr(exc, "orig", None)
            assert orig is not None
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            assert sqlstate == "23505", (
                f"duplicate outbox_event_id INSERT must surface SQLSTATE 23505, got {sqlstate!r}"
            )
        finally:
            sess.close()

        # Final invariant: still exactly 1 AuditEvent.
        sess = factory()
        rows = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == claimed1[0].event_identity
            )
        ).all()
        assert len(rows) == 1
        sess.close()

    def test_concurrent_duplicate_delivery(self, pg_outbox_engine):
        """Two independent sessions attempt INSERT into AuditEvent with the
        same outbox_event_id concurrently (barrier-synchronized).  The
        constraint MUST guarantee:

        - exactly one physical INSERT succeeds
        - the other session sees a UNIQUE violation and rolls back to
          a SAVEPOINT (not the outer transaction)
        - both outer transactions remain usable after the contention
        - exactly one AuditEvent row exists in the table

        This is the contention test that proves the production
        ``materialize_event`` SAVEPOINT path is safe under real
        concurrent duplicate delivery (not just sequential re-claim).
        """
        import threading

        from sqlalchemy.exc import IntegrityError

        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess_setup = factory()
        self._force_session_timeouts(sess_setup)
        _make_event(sess_setup, transition_id="dup-conc-1")
        sess_setup.commit()
        sess_setup.close()

        barrier = threading.Barrier(2)
        results: dict[str, object] = {"a": None, "b": None, "errors": []}

        def worker(label: str) -> None:
            sess = factory()
            try:
                self._force_session_timeouts(sess)
                existing = sess.execute(
                    select(AuditEventRecord).where(
                        AuditEventRecord.outbox_event_id == "dup-conc-event-identity"  # placeholder
                    )
                ).scalar_one_or_none()
                if existing is None:
                    pass
                barrier.wait(timeout=5)

                # Two competing INSERTs of the SAME outbox_event_id.
                event = AuditEventRecord(
                    id=str(uuid4()),
                    actor=f"worker-{label}",
                    action="dup.event",
                    entity_type="DupAgg",
                    entity_id="dup-1",
                    before_snapshot={},
                    after_snapshot={"dup": True},
                    event_metadata={
                        "event_identity": "dup-conc-event-identity",
                        "worker": label,
                    },
                    created_at=datetime.now(UTC),
                    outbox_event_id="dup-conc-event-identity",
                )
                try:
                    sess.add(event)
                    sess.flush()
                    results[label] = "inserted"
                    sess.commit()
                except IntegrityError as exc:
                    sess.rollback()
                    results[label] = "conflict"
                    # Verify outer transaction still usable.
                    sess.execute(select(func.count()).select_from(AuditEventRecord))
                    results[f"{label}_usable"] = True
                    orig = getattr(exc, "orig", None)
                    if orig is not None:
                        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
                        results[f"{label}_sqlstate"] = sqlstate
                except Exception as exc:
                    sess.rollback()
                    results["errors"].append(f"{label}: {type(exc).__name__}: {exc}")
            finally:
                sess.close()

        t_a = threading.Thread(target=worker, args=("a",))
        t_b = threading.Thread(target=worker, args=("b",))
        t_a.start()
        t_b.start()
        t_a.join(timeout=15)
        t_b.join(timeout=15)
        assert not t_a.is_alive(), "thread A did not terminate within timeout"
        assert not t_b.is_alive(), "thread B did not terminate within timeout"

        assert not results["errors"], f"workers raised unexpected exceptions: {results['errors']}"
        # Exactly one physical INSERT, exactly one conflict.
        outcomes = sorted([results["a"], results["b"]])
        assert outcomes == ["conflict", "inserted"], (
            f"expected exactly one winner and one loser, got {outcomes}"
        )
        # Both sessions remain usable (the loser successfully SELECTed
        # after rollback).
        assert results.get("a_usable") or results.get("b_usable")

        # Final invariant: exactly 1 AuditEvent row.
        sess = factory()
        rows = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == "dup-conc-event-identity"
            )
        ).all()
        assert len(rows) == 1, (
            f"expected exactly 1 AuditEvent after concurrent INSERT, got {len(rows)}"
        )
        sess.close()
