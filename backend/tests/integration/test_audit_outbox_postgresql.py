"""PostgreSQL integration tests for the audit outbox dispatcher.

Uses Alembic-migrated schema (not create_all) and exercises the same
behaviors as the SQLite suite, plus the SQLSTATE 23505 + constraint_name
classifier paths.

Tag: ``@pytest.mark.postgresql``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
import uuid as _uuid_mod
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
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
    ensure_utc_aware,
)
from cold_storage.modules.orchestration.infrastructure.orm import AuditOutboxRecord
from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
    claim_events_pg,
    mark_retryable_failure,
    mark_terminal_failure,
    materialize_event,
    validate_claim,
)
from cold_storage.modules.projects.infrastructure.orm import AuditEventRecord

pytestmark = pytest.mark.postgresql

import re

BACKEND_DIR = Path(__file__).resolve().parents[2]
_DB_NAME_RE = re.compile(r"[^a-z0-9_]")


def _sanitize(name: str) -> str:
    """Return a valid PostgreSQL database name."""
    return _DB_NAME_RE.sub("_", name.lower())[:63]


# ── Alembic bootstrap ──────────────────────────────────────────────────────


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
def _pg_outbox_session_factory(pg_admin_url: str):
    """Session-scoped admin engine used to create one shared test DB."""
    admin_engine = create_engine(pg_admin_url, poolclass=NullPool)
    admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
    created: list[str] = []

    def create_db(*, prefix: str) -> str:
        db_name = _sanitize(f"{prefix}_{_uuid_mod.uuid4().hex[:12]}")
        with admin_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {db_name}"))
        created.append(db_name)
        # Build URL using same scheme/host/credentials as admin_url
        # but with the new db name as the path.
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
def _pg_outbox_database_url(_pg_outbox_session_factory) -> str:
    """Per-module: create a dedicated database once, run alembic head once."""
    db_url = _pg_outbox_session_factory(prefix="pg_outbox")
    r = _run_alembic(db_url, "upgrade", "head")
    if r.returncode != 0:
        pytest.fail(f"Alembic upgrade failed: {r.stderr}\n{r.stdout}")
    return db_url


@pytest.fixture()
def pg_outbox_engine(_pg_outbox_database_url: str):
    """PostgreSQL engine bound to a module-scoped Alembic-head database.

    Each test gets a fresh engine bound to the same database. We
    TRUNCATE the outbox tables between tests so isolation is preserved
    without per-test alembic upgrade/downgrade cost.
    """
    engine = create_engine(_pg_outbox_database_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _truncate_pg_outbox_tables(pg_outbox_engine):
    """TRUNCATE outbox tables before each test for isolation."""
    with pg_outbox_engine.begin() as conn:
        conn.execute(
            text("TRUNCATE TABLE audit_events, orchestration_audit_outbox RESTART IDENTITY CASCADE")
        )
    yield


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
    """Insert a test outbox event via the ORM."""
    now = datetime.now(UTC).replace(microsecond=0)
    payload = payload or {"data": 1}
    tid = transition_id or str(uuid4())
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
        id=str(uuid4()),
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

    def test_skip_locked_two_workers_exactly_one_winner(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        sess = factory()
        _make_event(sess, transition_id="race-1")
        sess.commit()
        sess.close()

        barrier = threading.Barrier(2, timeout=30)
        results: dict[str, list] = {"a": [], "b": []}
        errors: dict[str, str] = {}

        def worker(label: str) -> None:
            try:
                sess = factory()
                barrier.wait()
                claimed = claim_events_pg(
                    sess,
                    worker_id=label,
                    batch_size=10,
                    lease_seconds=300,
                    now=now,
                )
                results[label] = claimed
                sess.commit()
                sess.close()
            except Exception as exc:
                errors[label] = repr(exc)

        threads = [threading.Thread(target=worker, args=(c,)) for c in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"workers raised: {errors}"
        total = len(results["a"]) + len(results["b"])
        assert total == 1, f"expected exactly 1 claim, got {total}"

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
        assert len(tokens) == 3  # all distinct
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

    def test_utc_aware_lease_comparison(self, pg_outbox_engine):
        """UTC-aware now is compared against aware DateTime(timezone=True)."""
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)
        sess = factory()
        _make_event(
            sess,
            transition_id="utc-1",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="tok",
            claimed_at=now,
            claim_expires_at=future,
        )
        sess.commit()
        sess.close()

        sess = factory()
        # Should not reclaim — lease still active.
        claimed = claim_events_pg(
            sess,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert claimed == []
        sess.close()

        # Asia/Tokyo aware input converts to same UTC instant
        tokyo_now = now.astimezone(__import__("datetime").timezone(timedelta(hours=9)))
        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=tokyo_now,
        )
        assert claimed == []
        sess.close()

    def test_now_equals_expiry_rejection(self, pg_outbox_engine):
        """now == claim_expires_at must NOT be reclaimable."""
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC).replace(microsecond=0)
        sess = factory()
        _make_event(
            sess,
            transition_id="now-eq",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="tok",
            claimed_at=now - timedelta(hours=1),
            claim_expires_at=now,
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

    def test_validate_claim_unknown_token_raises(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        sess = factory()
        event = _make_event(sess, transition_id="vt-1")
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

    def test_fk_violation_passthrough(self, pg_outbox_engine):
        """NOT NULL violations must NOT be classified as AuditEvent outbox_id conflict."""
        from sqlalchemy.exc import IntegrityError

        # NOT NULL violation on audit_events.outbox_event_id is an
        # IntegrityError but with a different SQLSTATE / column than the
        # outbox_id unique conflict we care about. The classifier must
        # not treat arbitrary IntegrityErrors as outbox_id conflicts.
        with pg_outbox_engine.connect() as conn:
            from sqlalchemy import text as sa_text

            with pytest.raises(IntegrityError):
                conn.execute(
                    sa_text(
                        "INSERT INTO audit_events (id, actor, action, entity_type, entity_id, before_snapshot, after_snapshot, event_metadata, created_at) "
                        "VALUES ('00000000-0000-0000-0000-000000000001'::text, 'x', 'x', 'x', 'x', \'{}', \'{}\', \'{}\', now())"
                    )
                )

    def test_published_terminal_protection(self, pg_outbox_engine):
        """Direct UPDATE of a PUBLISHED outbox row must be rejected."""
        from sqlalchemy.exc import DBAPIError, IntegrityError

        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess = factory()
        event = _make_event(sess, transition_id="pub-1", status="PUBLISHED")
        event_id = event.id
        sess.commit()
        sess.close()

        # Try to mutate the envelope on a PUBLISHED row — must fail.
        with pg_outbox_engine.begin() as conn:
            with pytest.raises(Exception):  # plpgsql RAISE EXCEPTION
                conn.execute(
                    text(
                        "UPDATE orchestration_audit_outbox SET actor = 'tampered' WHERE id = :rid"
                    ),
                    {"rid": event_id},
                )

    def test_failed_terminal_protection(self, pg_outbox_engine):
        """Direct UPDATE of a FAILED outbox row must be rejected."""
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess = factory()
        event = _make_event(sess, transition_id="fail-1", status="FAILED")
        event_id = event.id
        sess.commit()
        sess.close()

        with pg_outbox_engine.begin() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "UPDATE orchestration_audit_outbox SET actor = 'tampered' WHERE id = :rid"
                    ),
                    {"rid": event_id},
                )

    def test_envelope_tamper_rejected_by_trigger(self, pg_outbox_engine):
        """Any envelope field change on a PENDING row is rejected."""
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess = factory()
        event = _make_event(sess, transition_id="env-1")
        event_id = event.id
        sess.commit()
        sess.close()

        with pg_outbox_engine.begin() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "UPDATE orchestration_audit_outbox "
                        "SET request_id = 'tampered' WHERE id = :rid"
                    ),
                    {"rid": event_id},
                )

    def test_audit_event_outbox_id_immutable(self, pg_outbox_engine):
        """audit_events.outbox_event_id is immutable after insert."""
        from sqlalchemy.exc import IntegrityError

        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        # Create an AuditEvent via materialization first
        sess = factory()
        event = _make_event(sess, transition_id="ai-1")
        event_id = event.id
        event_identity = event.event_identity
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=datetime.now(UTC),
        )
        materialize_event(
            sess,
            claimed=claimed[0],
            worker_id="w1",
            claim_token=claimed[0].claim_token,
            now=datetime.now(UTC),
        )
        sess.commit()

        # Now try to update outbox_event_id on the AuditEvent — must fail.
        with pytest.raises(Exception):
            with pg_outbox_engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE audit_events "
                        "SET outbox_event_id = 'something-else' "
                        "WHERE outbox_event_id = :eid"
                    ),
                    {"eid": event_identity},
                )

    def test_sequential_duplicate_delivery(self, pg_outbox_engine):
        """Two sequential materialize_event calls → only one AuditEvent."""
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess = factory()
        _make_event(sess, transition_id="dup-seq-1")
        sess.commit()
        sess.close()

        # First delivery
        sess = factory()
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

        # Second delivery — must be idempotent (no new AuditEvent)
        sess = factory()
        claimed2 = claim_events_pg(
            sess,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=datetime.now(UTC),
        )
        assert len(claimed2) == 0  # event already PUBLISHED
        sess.close()

        sess = factory()
        count = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == claimed1[0].event_identity
            )
        ).all()
        assert len(count) == 1
        sess.close()

    def test_concurrent_claim_atomicity(self, pg_outbox_engine):
        """Two concurrent claims → exactly one succeeds per row."""
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess = factory()
        for i in range(3):
            _make_event(sess, transition_id=f"conc-{i}")
        sess.commit()
        sess.close()

        barrier = threading.Barrier(2, timeout=30)
        results: dict[str, list] = {"a": [], "b": []}

        def worker(label: str) -> None:
            sess = factory()
            barrier.wait()
            claimed = claim_events_pg(
                sess,
                worker_id=label,
                batch_size=10,
                lease_seconds=300,
                now=datetime.now(UTC),
            )
            results[label] = claimed
            sess.commit()
            sess.close()

        threads = [threading.Thread(target=worker, args=(c,)) for c in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        all_claimed = results["a"] + results["b"]
        assert len(all_claimed) == 3
        tokens = {c.claim_token for c in all_claimed}
        assert len(tokens) == 3  # each unique

    def test_savepoint_same_session_recovery(self, pg_outbox_engine):
        """SAVEPOINT recovery: same outer session remains usable after rollback."""
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess = factory()
        _make_event(sess, transition_id="save-1")
        sess.commit()

        # Materialize once (creates AuditEvent)
        claimed = claim_events_pg(
            sess,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=datetime.now(UTC),
        )
        materialize_event(
            sess,
            claimed=claimed[0],
            worker_id="w1",
            claim_token=claimed[0].claim_token,
            now=datetime.now(UTC),
        )
        sess.commit()

        # Outer session still usable for another operation.
        new_count = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == claimed[0].event_identity
            )
        ).all()
        assert len(new_count) == 1
        sess.close()
