"""PostgreSQL integration tests for the audit outbox dispatcher.

Lightweight suite that exercises the core dispatcher paths on a real
PostgreSQL instance using the Alembic head schema. Each test runs in a
fresh TRUNCATE'd namespace inside a module-scoped database.

Tag: ``@pytest.mark.postgresql``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid as _uuid_mod
from datetime import UTC, datetime, timedelta
from pathlib import Path

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


@pytest.fixture(scope="module")
def pg_outbox_engine(pg_database: str):
    """PostgreSQL engine with Alembic head schema applied once per module.

    pg_database (function-scoped) creates an isolated database per test
    module via the existing conftest.py helper; this fixture then runs
    alembic upgrade head on it. Downgrade is handled by pg_database's
    teardown.
    """
    _run_alembic(pg_database, "upgrade", "head")
    engine = create_engine(pg_database, poolclass=NullPool)
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
            text(
                "TRUNCATE TABLE audit_events, orchestration_audit_outbox "
                "RESTART IDENTITY CASCADE"
            )
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
            select(AuditOutboxRecord).where(
                AuditOutboxRecord.id == claimed[0].outbox_row_id
            )
        ).scalar_one()
        assert row.status == "PUBLISHED"
        sess2.close()
        sess.close()

    def test_sequential_duplicate_delivery(self, pg_outbox_engine):
        factory = sessionmaker(bind=pg_outbox_engine, expire_on_commit=False)
        sess = factory()
        _make_event(sess, transition_id="dup-seq-1")
        sess.commit()
        sess.close()

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

        sess = factory()
        claimed2 = claim_events_pg(
            sess,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=datetime.now(UTC),
        )
        assert len(claimed2) == 0
        sess.close()

        sess = factory()
        count = sess.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.outbox_event_id == claimed1[0].event_identity
            )
        ).all()
        assert len(count) == 1
        sess.close()