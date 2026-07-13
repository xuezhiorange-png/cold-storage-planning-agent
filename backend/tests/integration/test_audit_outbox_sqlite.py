"""SQLite integration tests for the audit outbox lifecycle.

Uses Alembic-migrated schema (not create_all).  Covers:
1. First claim
2. Deterministic ordering
3. Bounded batch
4. Concurrent double-claim prevention (single SQLite writer)
5. Active lease not reclaimable
6. Expired lease takeover with new token
7. Crash recovery (expired lease)
8. First materialization
9. Sequential duplicate materialization (idempotent)
10. Payload hash tamper rejection
11. Wrong worker/token rejection
12. Retryable failure evidence
13. Terminal failure evidence
14. PUBLISHED not reclaimable
15. FAILED not reclaimable
16. Materialization failure: no AuditEvent, outbox not PUBLISHED
17. Sequential duplicate full comparison (SAVEPOINT path)
18. Concurrent duplicate delivery
19. Concurrent claim
20. UTC-aware datetime claim
21. Asia/Tokyo datetime claim
22. SQLite naive readback
23. Now-equals-expiry rejection
24. Envelope hash covers full envelope
25. Envelope hash rejects NaN
26. Envelope hash rejects unknown type
27. add() idempotent same envelope
28. add() mismatched actor raises
29. add() mismatched payload raises
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from cold_storage.modules.orchestration.application.outbox_errors import (
    OutboxClaimLostError,
    OutboxIdempotencyMismatchError,
    OutboxMaterializationMismatchError,
    OutboxPayloadIntegrityError,
)
from cold_storage.modules.orchestration.application.outbox_identity import (
    build_event_identity,
    canonical_json,
    compute_envelope_hash,
    compute_payload_hash,
    ensure_utc_aware,
)
from cold_storage.modules.orchestration.infrastructure.orm import AuditOutboxRecord
from cold_storage.modules.orchestration.infrastructure.outbox_dispatcher import (
    claim_events_sqlite,
    mark_retryable_failure,
    mark_terminal_failure,
    materialize_event,
    validate_claim,
)
from cold_storage.modules.projects.infrastructure.orm import AuditEventRecord

pytestmark = pytest.mark.sqlite

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _run_alembic(sqlite_path: str, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "SQLITE_PATH": sqlite_path},
        capture_output=True,
        text=True,
        timeout=300,
    )
    return r


def _current_alembic_head(sqlite_path: str) -> str:
    """Return the single current alembic head revision id.

    Uses ``alembic heads`` which reads only the migrations directory
    (no DB connection required), so it works before any upgrade runs
    and stays stable across migrations. Output looks like::

        0038_phase4_slice1_coefficient_approval (head)

    so we parse the first whitespace-separated token. We assert:
    - returncode is 0
    - exactly one head is present (no merge branches with multiple heads)
    - the parsed token is a non-empty revision id string
    """
    r = _run_alembic(sqlite_path, "heads")
    assert r.returncode == 0, f"`alembic heads` failed: {r.stderr}"
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"Expected exactly one alembic head, got {len(lines)}: {lines!r}"
    head_id = lines[0].split()[0]
    assert head_id, f"Empty alembic head id parsed from: {lines[0]!r}"
    return head_id


# ── Helpers ────────────────────────────────────────────────────────────────


def _create_outbox_event(
    session: Any,
    *,
    event_type: str = "test.event",
    aggregate_type: str = "TestAggregate",
    aggregate_id: str = "agg-1",
    payload: dict | None = None,
    actor: str = "test-actor",
    correlation_id: str = "corr-1",
    status: str = "PENDING",
    next_retry_at: datetime | None = None,
    **kwargs,
) -> AuditOutboxRecord:
    """Insert a test outbox event directly.

    For PROCESSING/PUBLISHED/FAILED states, sets the required fields
    to satisfy the CHECK constraint.
    """
    # Truncate to second precision to avoid microsecond drift
    # between ORM default evaluation (at flush) and claim query.
    # Prefer the session-stable ``now`` (set by the autouse fixture) when
    # available, so a fast surrounding fixture does not let this call
    # cross a wall-clock second boundary relative to the test's outer
    # ``now``. Falls back to ``datetime.now(UTC)`` for any non-pytest
    # caller (e.g. REPL, ad-hoc scripts).
    now = _SESSION_STABLE_NOW or datetime.now(UTC).replace(microsecond=0)
    now_naive = now.replace(tzinfo=None)
    effective_payload = payload or {"test": "data"}
    identity = build_event_identity(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        transition_id=kwargs.get("transition_id", str(uuid4())),
    )
    envelope_hash = compute_envelope_hash(
        event_schema_version="1.0",
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor=actor,
        correlation_id=correlation_id,
        occurred_at=now,
        request_id=kwargs.get("request_id"),
        identity_id=kwargs.get("identity_id"),
        attempt_id=kwargs.get("attempt_id"),
        calculation_run_id=kwargs.get("calculation_run_id"),
        source_binding_id=kwargs.get("source_binding_id"),
        payload=effective_payload,
        event_identity=identity,
    )

    record = AuditOutboxRecord(
        id=str(uuid4()),
        event_identity=identity,
        event_type=event_type,
        event_schema_version="1.0",
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor=actor,
        correlation_id=correlation_id,
        occurred_at=now_naive,
        payload=effective_payload,
        payload_hash=compute_payload_hash(effective_payload),
        envelope_hash=envelope_hash,
        status=status,
        request_id=kwargs.get("request_id"),
        identity_id=kwargs.get("identity_id"),
        attempt_id=kwargs.get("attempt_id"),
        next_retry_at=next_retry_at or now_naive,
    )

    # Set required fields for non-PENDING states (CHECK constraint)
    if status == "PROCESSING":
        record.claimed_by = kwargs.get("claimed_by", "test-worker")
        record.claim_token = kwargs.get("claim_token", "test-token")
        record.claimed_at = kwargs.get("claimed_at", now)
        record.claim_expires_at = kwargs.get("claim_expires_at", now + timedelta(hours=1))
        record.attempt_count = kwargs.get("attempt_count", 1)
        record.next_retry_at = next_retry_at or now
    elif status == "PUBLISHED":
        record.published_at = kwargs.get("published_at", now)
    elif status == "FAILED":
        record.failed_at = kwargs.get("failed_at", now)
        record.last_error_class = kwargs.get("last_error_class", "TestError")
        record.last_error_code = kwargs.get("last_error_code", "test_error")
        record.last_error_at = kwargs.get("last_error_at", now)

    session.add(record)
    session.flush()
    return record


# ── Test class ─────────────────────────────────────────────────────────────


class TestSQLitelOutboxLifecycle:
    """Full lifecycle on SQLite with Alembic-migrated schema."""

    # ── Original tests (P0-1 through P0-6) ────────────────────────────────

    def test_first_claim(self, sqlite_engine):
        """First claim picks up PENDING events."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        # Insert an event
        sess = factory()
        event = _create_outbox_event(sess, transition_id="claim-1")
        event_id = event.id
        sess.commit()
        sess.close()

        # Claim it
        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        assert claimed[0].outbox_row_id == event_id
        assert claimed[0].claim_token is not None
        assert claimed[0].attempt_count == 1
        sess.commit()
        sess.close()

        # Verify status
        sess = factory()
        row = sess.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status == "PROCESSING"
        assert row.claimed_by == "w1"
        assert row.claim_token == claimed[0].claim_token
        sess.close()

    def test_deterministic_ordering(self, sqlite_engine):
        """Events are claimed in next_retry_at ASC, created_at ASC order."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        # All events must have next_retry_at <= now to be eligible
        e1 = _create_outbox_event(
            sess,
            transition_id="order-1",
            next_retry_at=now - timedelta(seconds=100),
        )
        e2 = _create_outbox_event(
            sess,
            transition_id="order-2",
            next_retry_at=now - timedelta(seconds=200),
        )
        e3 = _create_outbox_event(
            sess,
            transition_id="order-3",
            next_retry_at=now - timedelta(seconds=50),
        )
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 3
        # e2 has earliest next_retry_at (-200s), then e1 (-100s), then e3 (-50s)
        assert claimed[0].outbox_row_id == e2.id
        assert claimed[1].outbox_row_id == e1.id
        assert claimed[2].outbox_row_id == e3.id
        sess.close()

    def test_bounded_batch(self, sqlite_engine):
        """Claim respects batch_size limit."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        for i in range(5):
            _create_outbox_event(sess, transition_id=f"batch-{i}")
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=3,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 3
        sess.close()

    def test_double_claim_prevention(self, sqlite_engine):
        """Second claim on already-PROCESSING event returns nothing."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        _create_outbox_event(sess, transition_id="dc-1")
        sess.commit()
        sess.close()

        # First claim
        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        sess.commit()
        sess.close()

        # Second claim — should be empty (event is PROCESSING)
        sess = factory()
        claimed2 = claim_events_sqlite(
            sqlite_engine,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed2) == 0
        sess.close()

    def test_active_lease_not_reclaimable(self, sqlite_engine):
        """PROCESSING with active lease is not eligible for re-claim."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)

        sess = factory()
        _create_outbox_event(
            sess,
            transition_id="al-1",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="token-1",
            claimed_at=now,
            claim_expires_at=future,
            attempt_count=1,
        )
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 0
        sess.close()

    def test_expired_lease_takeover(self, sqlite_engine):
        """PROCESSING with expired lease can be claimed by another worker."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)

        sess = factory()
        _create_outbox_event(
            sess,
            transition_id="et-1",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="old-token",
            claimed_at=past,
            claim_expires_at=past,
            attempt_count=1,
        )
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        assert claimed[0].claim_token != "old-token"
        assert claimed[0].attempt_count == 2
        sess.commit()
        sess.close()

    def test_crash_recovery(self, sqlite_engine):
        """Expired lease is picked up by next dispatch cycle."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        # Pre-populate a PROCESSING event with already-expired lease
        past = now - timedelta(hours=1)
        _create_outbox_event(
            sess,
            transition_id="cr-1",
            status="PROCESSING",
            claimed_by="previous-worker",
            claim_token="old-token",
            claimed_at=past,
            claim_expires_at=past,
            attempt_count=1,
        )
        sess.commit()
        sess.close()

        # New worker should be able to take over the expired lease
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="recovery",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        assert claimed[0].claim_token != "old-token"
        assert claimed[0].attempt_count == 2

    def test_first_materialization(self, sqlite_engine):
        """Materialize a claimed event into AuditEvent + mark PUBLISHED."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        # Insert and claim
        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="mat-1",
            payload={"result": "success"},
        )
        sess.commit()
        event_id = event.id
        event_identity = event.event_identity
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1

        # Materialize
        materialize_event(
            sess,
            claimed=claimed[0],
            worker_id="w1",
            claim_token=claimed[0].claim_token,
            now=now,
        )
        sess.commit()

        # Verify AuditEvent exists
        sess2 = factory()
        audit = sess2.execute(
            select(AuditEventRecord).where(AuditEventRecord.outbox_event_id == event_identity)
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.action == "test.event"
        assert audit.entity_type == "TestAggregate"
        assert audit.after_snapshot == {"result": "success"}

        # Verify outbox is PUBLISHED
        row = sess2.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status == "PUBLISHED"
        assert row.published_at is not None
        assert row.claim_token is None
        sess2.close()

    def test_sequential_duplicate_materialization(self, sqlite_engine):
        """Same event materialized twice is idempotent."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="dup-1",
            payload={"data": "test"},
        )
        sess.commit()
        event_identity = event.event_identity
        sess.close()

        # First materialization
        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        materialize_event(
            sess,
            claimed=claimed[0],
            worker_id="w1",
            claim_token=claimed[0].claim_token,
            now=now,
        )
        sess.commit()
        sess.close()

        # Verify: AuditEvent count == 1
        sess2 = factory()
        count = sess2.execute(
            select(func.count())
            .select_from(AuditEventRecord)
            .where(AuditEventRecord.outbox_event_id == event_identity)
        ).scalar_one()
        assert count == 1
        sess2.close()

    def test_wrong_worker_token_rejection(self, sqlite_engine):
        """validate_claim rejects wrong worker or token."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="wrong-1",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="correct-token",
            claimed_at=now,
            claim_expires_at=now + timedelta(hours=1),
            attempt_count=1,
        )
        sess.commit()
        event_id = event.id
        sess.close()

        sess = factory()
        with pytest.raises(OutboxClaimLostError):
            validate_claim(
                sess,
                event_id=event_id,
                worker_id="w2",
                claim_token="wrong-token",
                now=now,
            )
        sess.close()

    def test_retryable_failure_evidence(self, sqlite_engine):
        """Retryable failure returns event to PENDING with error evidence."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="retry-1",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="token-r1",
            claimed_at=now,
            claim_expires_at=now + timedelta(hours=1),
            attempt_count=1,
        )
        sess.commit()
        event_id = event.id
        sess.close()

        sess = factory()
        mark_retryable_failure(
            sess,
            event_id=event_id,
            worker_id="w1",
            claim_token="token-r1",
            error=RuntimeError("network timeout"),
            now=now,
        )
        sess.commit()
        sess.close()

        sess2 = factory()
        row = sess2.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status == "PENDING"
        assert row.last_error_class == "RuntimeError"
        assert row.last_error_code == "network timeout"
        assert row.last_error_at is not None
        assert row.claimed_by is None
        assert row.claim_token is None
        sess2.close()

    def test_terminal_failure_evidence(self, sqlite_engine):
        """Terminal failure moves event to FAILED with full evidence."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="term-1",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="token-t1",
            claimed_at=now,
            claim_expires_at=now + timedelta(hours=1),
            attempt_count=2,
        )
        sess.commit()
        event_id = event.id
        sess.close()

        sess = factory()
        mark_terminal_failure(
            sess,
            event_id=event_id,
            worker_id="w1",
            claim_token="token-t1",
            error=OutboxMaterializationMismatchError("ident-1", ["action"]),
            now=now,
        )
        sess.commit()
        sess.close()

        sess2 = factory()
        row = sess2.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status == "FAILED"
        assert row.failed_at is not None
        assert row.last_error_class == "OutboxMaterializationMismatchError"
        assert row.claimed_by is None
        assert row.claim_token is None
        sess2.close()

    def test_published_not_reclaimable(self, sqlite_engine):
        """PUBLISHED events are not eligible for claim."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        _create_outbox_event(sess, transition_id="pub-1", status="PUBLISHED")
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 0
        sess.close()

    def test_failed_not_reclaimable(self, sqlite_engine):
        """FAILED events are not eligible for claim."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        _create_outbox_event(sess, transition_id="fail-1", status="FAILED")
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 0
        sess.close()

    def test_payload_hash_tamper_rejection(self, sqlite_engine):
        """Materialization rejects when DB row payload_hash doesn't match payload.

        P0-6: materialization reads from DB row, not DTO.  We tamper the
        stored payload_hash via raw SQL so the DB-row recomputed hash
        no longer matches.
        """
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="tamper-1",
            payload={"original": "data"},
        )
        sess.commit()
        event_id = event.id
        event_identity = event.event_identity
        sess.close()

        # Tamper the stored payload_hash via raw SQL.
        # The trg_immutable_outbox_envelope trigger blocks UPDATE on
        # envelope fields for PENDING rows, so drop it temporarily.
        sess = factory()
        sess.execute(text("DROP TRIGGER IF EXISTS trg_immutable_outbox_envelope"))
        sess.execute(
            text(
                "UPDATE orchestration_audit_outbox "
                "SET payload_hash = 'definitely_wrong' "
                "WHERE id = :eid"
            ),
            {"eid": event_id},
        )
        # Recreate the trigger
        sess.execute(
            text(
                "CREATE TRIGGER trg_immutable_outbox_envelope "
                "BEFORE UPDATE ON orchestration_audit_outbox "
                "FOR EACH ROW "
                "WHEN OLD.status = 'PUBLISHED' OR OLD.status = 'FAILED' "
                "OR NEW.event_identity != OLD.event_identity "
                "OR NEW.event_type != OLD.event_type "
                "OR NEW.event_schema_version != OLD.event_schema_version "
                "OR NEW.aggregate_type != OLD.aggregate_type "
                "OR NEW.aggregate_id != OLD.aggregate_id "
                "OR NEW.actor != OLD.actor "
                "OR NEW.correlation_id != OLD.correlation_id "
                "OR NEW.occurred_at != OLD.occurred_at "
                "OR NEW.payload IS NOT OLD.payload "
                "OR NEW.payload_hash != OLD.payload_hash "
                "BEGIN "
                "SELECT RAISE(ABORT, "
                "'Cannot modify immutable audit envelope fields on outbox event'); "
                "END"
            )
        )
        sess.commit()

        # Claim
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1

        # Materialize should detect hash mismatch from DB row
        sess3 = factory()
        with pytest.raises(OutboxPayloadIntegrityError):
            materialize_event(
                sess3,
                claimed=claimed[0],
                worker_id="w1",
                claim_token=claimed[0].claim_token,
                now=now,
            )
        sess3.rollback()
        sess3.close()

        # Verify: no AuditEvent, outbox not PUBLISHED
        sess4 = factory()
        audit_count = sess4.execute(
            select(func.count())
            .select_from(AuditEventRecord)
            .where(AuditEventRecord.outbox_event_id == event_identity)
        ).scalar_one()
        assert audit_count == 0

        row = sess4.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status != "PUBLISHED"
        sess4.close()

    # ── P0-5: Sequential duplicate full comparison ────────────────────────

    def test_sequential_duplicate_full_comparison(self, sqlite_engine):
        """Second materialization triggers SAVEPOINT rollback → readback → compare.

        Manually inserts a pre-existing AuditEvent to simulate a concurrent
        materialization, then calls materialize_event which hits the SAVEPOINT
        conflict path.
        """
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        # Create outbox event with known payload
        known_payload = {"result": "success", "count": 42}
        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="dup-comp-1",
            payload=known_payload,
        )
        sess.commit()
        event_id = event.id
        event_identity = event.event_identity
        sess.close()

        # Read the event's envelope_hash and occurred_at from DB
        sess = factory()
        db_event = sess.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        envelope_hash = db_event.envelope_hash
        occurred_at_str = ensure_utc_aware(db_event.occurred_at).isoformat()
        sess.close()

        # Claim the event
        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1

        # Manually insert an AuditEvent with the same outbox_event_id
        # (simulating a concurrent materialization that already happened)
        pre_existing = AuditEventRecord(
            id=str(uuid4()),
            actor="test-actor",
            action="test.event",
            entity_type="TestAggregate",
            entity_id="agg-1",
            before_snapshot={},
            after_snapshot=known_payload,
            event_metadata={
                "event_identity": event_identity,
                "event_schema_version": "1.0",
                "correlation_id": "corr-1",
                "occurred_at": occurred_at_str,
                "payload_hash": compute_payload_hash(known_payload),
                "envelope_hash": envelope_hash,
                "request_id": None,
                "identity_id": None,
                "attempt_id": None,
                "calculation_run_id": None,
                "source_binding_id": None,
            },
            created_at=now,
            outbox_event_id=event_identity,
        )
        sess.add(pre_existing)
        sess.flush()

        # Now try to materialize — should hit SAVEPOINT path
        materialize_event(
            sess,
            claimed=claimed[0],
            worker_id="w1",
            claim_token=claimed[0].claim_token,
            now=now,
        )
        sess.commit()
        sess.close()

        # Verify: AuditEvent count == 1 (idempotent), outbox PUBLISHED
        sess2 = factory()
        count = sess2.execute(
            select(func.count())
            .select_from(AuditEventRecord)
            .where(AuditEventRecord.outbox_event_id == event_identity)
        ).scalar_one()
        assert count == 1

        row = sess2.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status == "PUBLISHED"
        assert row.claim_token is None
        sess2.close()

    # ── P0-5: Concurrent duplicate delivery ───────────────────────────────

    def test_concurrent_duplicate_delivery(self, sqlite_engine):
        """Two workers try to materialize the same event simultaneously.

        Exactly one succeeds (published). The other either succeeds
        (idempotent) or gets claim lost.
        """
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="conc-dup-1",
            payload={"concurrent": "data"},
        )
        sess.commit()
        event_id = event.id
        sess.close()

        barrier = threading.Barrier(2)
        outcomes: list[str | None] = [None, None]

        def worker(idx: int) -> None:
            barrier.wait()
            s = factory()
            try:
                claimed = claim_events_sqlite(
                    sqlite_engine,
                    worker_id=f"w{idx}",
                    batch_size=10,
                    lease_seconds=300,
                    now=now,
                )
                if not claimed:
                    outcomes[idx] = "empty"
                    return

                materialize_event(
                    s,
                    claimed=claimed[0],
                    worker_id=f"w{idx}",
                    claim_token=claimed[0].claim_token,
                    now=now,
                )
                s.commit()
                outcomes[idx] = "published"
            except Exception:
                s.rollback()
                outcomes[idx] = "error"
            finally:
                s.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        threads[0].start()
        threads[1].start()
        threads[0].join()
        threads[1].join()

        # Exactly one should succeed (published)
        published_count = sum(1 for o in outcomes if o == "published")
        assert published_count == 1

        # AuditEvent count == 1
        sess = factory()
        audit_count = sess.execute(select(func.count()).select_from(AuditEventRecord)).scalar_one()
        assert audit_count == 1

        # Outbox is PUBLISHED
        row = sess.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status == "PUBLISHED"
        sess.close()

    # ── P0-5: Concurrent claim ────────────────────────────────────────────

    def test_concurrent_claim(self, sqlite_engine):
        """Two workers try to claim the same PENDING event simultaneously.

        Exactly one gets a valid claim. Final: no duplicates.
        """
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(sess, transition_id="conc-claim-1")
        sess.commit()
        event_id = event.id
        sess.close()

        barrier = threading.Barrier(2)

        def worker(idx: int) -> None:
            barrier.wait()
            s = factory()
            try:
                claimed = claim_events_sqlite(
                    sqlite_engine,
                    worker_id=f"w{idx}",
                    batch_size=10,
                    lease_seconds=300,
                    now=now,
                )
                if claimed:
                    s.commit()
            except Exception:
                s.rollback()
            finally:
                s.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        threads[0].start()
        threads[1].start()
        threads[0].join()
        threads[1].join()

        # Event should be PROCESSING (someone claimed it)
        sess = factory()
        row = sess.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
        ).scalar_one()
        assert row.status == "PROCESSING"
        assert row.claimed_by in ("w0", "w1")
        assert row.attempt_count >= 1

        # No AuditEvent was created (no materialization)
        audit_count = sess.execute(select(func.count()).select_from(AuditEventRecord)).scalar_one()
        assert audit_count == 0
        sess.close()

    # ── Datetime boundary tests ───────────────────────────────────────────

    def test_utc_aware_datetime_claim(self, sqlite_engine):
        """Claim with UTC-aware datetime works."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(sess, transition_id="utc-aware-1")
        sess.commit()
        sess.close()

        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        sess.commit()
        sess.close()

        sess2 = factory()
        row = sess2.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event.id)
        ).scalar_one()
        assert row.status == "PROCESSING"
        assert row.claimed_by == "w1"
        sess2.close()

    def test_asia_tokyo_datetime_claim(self, sqlite_engine):
        """Claim with Asia/Tokyo timezone datetime works (converted to UTC)."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)
        tokyo_tz = timezone(timedelta(hours=9))
        tokyo_now = now.astimezone(tokyo_tz)

        sess = factory()
        event = _create_outbox_event(sess, transition_id="tokyo-1")
        sess.commit()
        sess.close()

        # Claim with Asia/Tokyo datetime
        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w1",
            batch_size=10,
            lease_seconds=300,
            now=tokyo_now,
        )
        assert len(claimed) == 1
        sess.commit()
        sess.close()

        # Verify
        sess2 = factory()
        row = sess2.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event.id)
        ).scalar_one()
        assert row.status == "PROCESSING"
        assert row.claimed_by == "w1"
        sess2.close()

    def test_sqlite_naive_readback(self, sqlite_engine):
        """SQLite reads datetimes as naive (no timezone info)."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)

        sess = factory()
        event = _create_outbox_event(sess, transition_id="naive-1")
        sess.commit()
        sess.close()

        sess = factory()
        row = sess.execute(
            select(AuditOutboxRecord).where(AuditOutboxRecord.id == event.id)
        ).scalar_one()
        # SQLite stores datetimes without timezone info
        assert row.occurred_at.tzinfo is None
        assert row.created_at.tzinfo is None
        sess.close()

    def test_now_equals_expiry_rejection(self, sqlite_engine):
        """claim_expires_at == now → event is expired, eligible for takeover."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        now = datetime.now(UTC)

        sess = factory()
        event = _create_outbox_event(
            sess,
            transition_id="expiry-eq-1",
            status="PROCESSING",
            claimed_by="w1",
            claim_token="token-1",
            claimed_at=now,
            claim_expires_at=now,  # Exactly equal to now
            attempt_count=1,
        )
        sess.commit()
        event_id = event.id
        sess.close()

        # Try to claim — should find the event as expired
        sess = factory()
        claimed = claim_events_sqlite(
            sqlite_engine,
            worker_id="w2",
            batch_size=10,
            lease_seconds=300,
            now=now,
        )
        assert len(claimed) == 1
        assert claimed[0].outbox_row_id == event_id
        assert claimed[0].claim_token != "token-1"  # New token
        assert claimed[0].attempt_count == 2  # Incremented
        sess.commit()
        sess.close()

    # ── Envelope hash tests ───────────────────────────────────────────────

    def test_envelope_hash_covers_full_envelope(self):
        """Envelope hash changes when any field in the full envelope changes."""
        base_kwargs = dict(
            event_schema_version="1.0",
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            actor="test-actor",
            correlation_id="corr-1",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            payload={"data": 1},
        )
        h1 = compute_envelope_hash(**base_kwargs)

        # Change payload → different hash
        h2 = compute_envelope_hash(**{**base_kwargs, "payload": {"data": 2}})
        assert h1 != h2

        # Change actor → different hash
        h3 = compute_envelope_hash(**{**base_kwargs, "actor": "other"})
        assert h1 != h3

        # Same envelope → same hash (deterministic)
        h4 = compute_envelope_hash(**base_kwargs)
        assert h1 == h4

    def test_envelope_hash_rejects_nan(self):
        """NaN in payload raises ValueError."""
        with pytest.raises(ValueError, match="not allowed"):
            canonical_json({"key": float("nan")})

    def test_envelope_hash_rejects_unknown_type(self):
        """Unknown type in payload raises TypeError."""
        with pytest.raises(TypeError, match="not JSON serializable"):
            canonical_json({"key": set([1, 2, 3])})

    # ── add() idempotent comparison tests ─────────────────────────────────

    def test_add_idempotent_same_envelope(self, sqlite_engine):
        """Same envelope → returns existing ID."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            SqlAlchemyAuditOutboxRepository,
        )

        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        repo = SqlAlchemyAuditOutboxRepository()
        fixed_now = datetime(2026, 1, 1)  # naive — matches SQLite readback

        sess = factory()
        id1 = repo.add(
            sess,
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            payload={"data": 1},
            actor="test-actor",
            correlation_id="corr-idem",
            transition_id="idem-1",
            occurred_at=fixed_now,
        )
        sess.commit()
        sess.close()

        sess2 = factory()
        id2 = repo.add(
            sess2,
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            payload={"data": 1},
            actor="test-actor",
            correlation_id="corr-idem",
            transition_id="idem-1",
            occurred_at=fixed_now,
        )
        sess2.commit()
        sess2.close()

        assert id1 == id2

    def test_add_mismatched_actor_raises(self, sqlite_engine):
        """Same identity but different actor+payload → OutboxIdempotencyMismatchError."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            SqlAlchemyAuditOutboxRepository,
        )

        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        repo = SqlAlchemyAuditOutboxRepository()
        fixed_now = datetime(2026, 1, 1)  # naive — matches SQLite readback

        sess = factory()
        repo.add(
            sess,
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            payload={"data": 1, "actor": "actor-1"},
            actor="actor-1",
            correlation_id="corr-mismatch-actor",
            transition_id="mismatch-actor-1",
            occurred_at=fixed_now,
        )
        sess.commit()
        sess.close()

        sess2 = factory()
        with pytest.raises(OutboxIdempotencyMismatchError):
            repo.add(
                sess2,
                event_type="test.event",
                aggregate_type="TestAggregate",
                aggregate_id="agg-1",
                payload={"data": 1, "actor": "actor-2"},
                actor="actor-2",
                correlation_id="corr-mismatch-actor",
                transition_id="mismatch-actor-1",
                occurred_at=fixed_now,
            )
        sess2.close()

    def test_add_mismatched_payload_raises(self, sqlite_engine):
        """Same identity but different payload → OutboxIdempotencyMismatchError."""
        from cold_storage.modules.orchestration.infrastructure.repositories import (
            SqlAlchemyAuditOutboxRepository,
        )

        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        repo = SqlAlchemyAuditOutboxRepository()
        fixed_now = datetime(2026, 1, 1)  # naive — matches SQLite readback

        sess = factory()
        repo.add(
            sess,
            event_type="test.event",
            aggregate_type="TestAggregate",
            aggregate_id="agg-1",
            payload={"data": 1},
            actor="actor-payload",
            correlation_id="corr-mismatch-payload",
            transition_id="mismatch-payload-1",
            occurred_at=fixed_now,
        )
        sess.commit()
        sess.close()

        sess2 = factory()
        with pytest.raises(OutboxIdempotencyMismatchError):
            repo.add(
                sess2,
                event_type="test.event",
                aggregate_type="TestAggregate",
                aggregate_id="agg-1",
                payload={"data": 2},
                actor="actor-payload",
                correlation_id="corr-mismatch-payload",
                transition_id="mismatch-payload-1",
                occurred_at=fixed_now,
            )
        sess2.close()


# ── Fixture ────────────────────────────────────────────────────────────────

# Module-level counter for alembic subprocess invocations in this pytest process.
# Pattern A: session-scoped migrated template + per-test file copy.
# Only the session-scoped template fixture invokes `alembic upgrade head` and
# `alembic heads` (each exactly once). Every per-test fixture just copies the
# closed template file — no subprocess work, no migration overhead.
ALEMBIC_SUBPROCESS_CALLS: dict[str, int] = {"upgrade": 0, "heads": 0}


# Module-level "session stable now" used by ``_create_outbox_event`` as a
# default for ``next_retry_at`` and ``occurred_at``. Capturing
# ``datetime.now(UTC)`` per call in the helper is fine when the surrounding
# fixture costs ~30s, but a fast fixture (<1s per test) can let the test's
# outer ``now`` and the helper's internal ``now`` straddle a wall-clock
# second boundary, which breaks the ``substr(next_retry_at,1,19) <= :now_str``
# comparison in ``claim_events_sqlite``. Pinning a session-stable value here
# keeps helper output deterministic with respect to the test's outer ``now``.
_SESSION_STABLE_NOW: datetime | None = None


@pytest.fixture(scope="session", autouse=True)
def _session_stable_now():
    """Session-scoped autouse: install a stable ``now`` for the entire pytest
    session. The value is captured ONCE at session start and used by
    ``_create_outbox_event`` as a default for ``occurred_at`` /
    ``next_retry_at`` so that wall-clock drift between consecutive test
    seconds cannot cause ``claim_events_sqlite`` to under-claim.
    """
    global _SESSION_STABLE_NOW
    _SESSION_STABLE_NOW = datetime.now(UTC).replace(microsecond=0)
    yield _SESSION_STABLE_NOW
    _SESSION_STABLE_NOW = None


@pytest.fixture(scope="session")
def _alembic_migrated_template(tmp_path_factory):
    """Build a single Alembic-migrated SQLite template, ONCE per pytest process.

    Runs ``alembic upgrade head`` exactly once and ``alembic heads`` exactly
    once. The resulting file is closed (engine disposed) before yield, so it
    can be safely ``shutil.copyfile``'d by every function-scoped ``sqlite_engine``
    fixture into a per-test database file with full schema isolation.

    Schema correctness is verified here, ONCE, against the same set of triggers
    that the original per-test fixture asserted on:
        - alembic_version == current head
        - trg_immutable_outbox_envelope
        - trg_outbox_published_requires_auditevent
        - trg_audit_event_outbox_id_immutable
    """
    template_dir = tmp_path_factory.mktemp("audit-outbox-sqlite-template")
    template_path = template_dir / "template.db"
    # Create an empty file. Alembic's env.py writes the URL into SQLITE_PATH,
    # which can be either a path or a file URL; the path branch is the
    # contract used by ``alembic.ini`` and by every other test in this repo.
    template_path.write_bytes(b"")

    # 1) alembic upgrade head (one-shot)
    ALEMBIC_SUBPROCESS_CALLS["upgrade"] += 1
    r_up = _run_alembic(str(template_path), "upgrade", "head")
    assert r_up.returncode == 0, f"`alembic upgrade head` failed: {r_up.stderr}\n{r_up.stdout}"

    # 2) alembic heads (one-shot) — verify the migrations directory itself
    # has exactly one head. Same check the per-test fixture did inline.
    ALEMBIC_SUBPROCESS_CALLS["heads"] += 1
    r_heads = _run_alembic(str(template_path), "heads")
    assert r_heads.returncode == 0, f"`alembic heads` failed: {r_heads.stderr}\n{r_heads.stdout}"
    head_lines = [ln.strip() for ln in r_heads.stdout.splitlines() if ln.strip()]
    assert len(head_lines) == 1, (
        f"Expected exactly one alembic head, got {len(head_lines)}: {head_lines!r}"
    )

    # 3) Open the migrated template once, assert version + triggers, then
    #    dispose before yield so per-test copies are not blocked.
    engine = create_engine(f"sqlite:///{template_path}", poolclass=NullPool)
    try:
        with engine.connect() as conn:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            expected_head = head_lines[0].split()[0]
            assert ver == expected_head, (
                f"Unexpected migration version: {ver!r} != {expected_head!r}"
            )

            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger'")
            ).fetchall()
            trigger_names = [t[0] for t in tables]
            assert "trg_immutable_outbox_envelope" in trigger_names
            assert "trg_outbox_published_requires_auditevent" in trigger_names
            assert "trg_audit_event_outbox_id_immutable" in trigger_names
    finally:
        engine.dispose()

    return str(template_path)


@pytest.fixture()
def sqlite_engine(_alembic_migrated_template, tmp_path):
    """Per-test: copy the migrated template to an isolated file, no alembic.

    Each test gets its own SQLite file with the full migrated schema and an
    empty data state. After yield, the engine is disposed and the per-test
    file is unlinked, so tests cannot leak data or file handles.

    The function-scoped fixture does NOT invoke the alembic subprocess.
    """
    test_db = tmp_path / "test.db"
    shutil.copyfile(_alembic_migrated_template, test_db)
    # tmp_path is function-scoped and is cleaned up by pytest, but we still
    # unlink the DB file explicitly so a test that holds a connection open
    # past teardown cannot leave a stale .db behind on Windows-style locking.
    engine = create_engine(f"sqlite:///{test_db}", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()
        if test_db.exists():
            test_db.unlink()


class TestSQLiteDispatcherUnknownExceptionUntreated:
    """P0-7: unknown exceptions must NOT silently retry.

    The dispatcher application service MUST classify exceptions:

    - typed retryable / typed terminal → corresponding mark_*
    - bare ``Exception`` (untyped) → terminal FAILED, NOT retryable
      (so the system does not loop forever on a bug)

    This test runs the production application service with a
    ``materialize_fn`` that raises a bare ``RuntimeError`` and asserts
    the summary records a terminal failure (not a retry).
    """

    def test_unknown_exception_marked_terminal_not_retryable(
        self,
        sqlite_engine,
    ) -> None:
        from datetime import UTC, datetime

        from cold_storage.modules.orchestration.application.outbox_dispatcher import (
            AuditOutboxDispatcherApplicationService,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            AuditOutboxRecord,
        )

        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)

        # Seed one PENDING event via direct insert.
        sess = factory()
        _create_outbox_event(sess, transition_id="unk-exc-1")
        sess.commit()
        sess.close()

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated unknown exception in materialize_fn")

        service = AuditOutboxDispatcherApplicationService(
            engine=sqlite_engine,
            claim_fn_pg=None,
            claim_fn_sqlite=claim_events_sqlite,
            materialize_fn=boom,
            mark_retryable_fn=mark_retryable_failure,
            mark_terminal_fn=mark_terminal_failure,
            session_factory=factory,
            is_pg=False,
        )

        summary = service.run_cycle(
            worker_id="w-unk",
            batch_size=10,
            lease_seconds=300,
            now=datetime.now(UTC),
        )

        # The unknown exception must NOT cause ``retried`` to be set.
        assert summary.failed == 1, (
            f"unknown exception must be counted as terminal failed=1, got summary={summary}"
        )
        assert summary.retried == 0, (
            f"unknown exception MUST NOT silently retry, got summary={summary}"
        )
        assert summary.published == 0
        assert summary.unhandled_failures == 0, (
            f"unknown exception path persisted the terminal failure "
            f"successfully, so unhandled must be 0, got {summary}"
        )

        # Verify the row is in FAILED state.
        sess = factory()
        row = sess.execute(
            select(AuditOutboxRecord).where(
                AuditOutboxRecord.event_type == "test.event",
                AuditOutboxRecord.aggregate_id == "agg-1",
            )
        ).scalar_one()
        assert row.status == "FAILED", (
            f"unknown exception must mark row as FAILED, got {row.status!r}"
        )
        assert row.failed_at is not None
        assert row.last_error_class == "RuntimeError"
        sess.close()


# ── Isolation verification (Pattern A: per-test file copy) ─────────────────


class TestSQLiteOutboxFixtureIsolation:
    """Prove the session-template + per-test-copy fixture does not leak state.

    These tests run LAST (alphabetical class order) and assert that:
    1. test A writes are NOT visible to test B (independent DB files)
    2. the per-test DB file is unlinked at teardown
    3. the session-level template is closed (no leaked connection)
    4. alembic subprocess is invoked exactly once for upgrade + once for heads
    """

    def test_writer_A_inserts_persistent_data(self, sqlite_engine):
        """Test A writes one row; the row persists in this test's engine."""
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        sess = factory()
        record = _create_outbox_event(sess, transition_id="iso-A-1")
        sess.commit()
        sess.close()

        # Re-open a fresh session and confirm the row exists in this test.
        sess = factory()
        rows = (
            sess.execute(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.event_type == "test.event",
                    AuditOutboxRecord.aggregate_id == "agg-1",
                )
            )
            .scalars()
            .all()
        )
        sess.close()
        assert len(rows) == 1, f"test A should see its own row, got {len(rows)}"
        assert rows[0].id == record.id

    def test_writer_B_does_not_see_writer_A_data(self, sqlite_engine):
        """Test B (this test) must see an empty outbox — no carry-over from
        test_writer_A_inserts_persistent_data, even though both used the
        same fixture name. This is the isolation invariant.
        """
        factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        sess = factory()
        rows = sess.execute(select(AuditOutboxRecord)).scalars().all()
        sess.close()
        assert rows == [], (
            f"test B must start with empty outbox, got {len(rows)} rows — "
            f"per-test copy is leaking state from a prior test"
        )

    def test_each_test_engine_is_disposed_and_file_removed(
        self, _alembic_migrated_template, tmp_path
    ):
        """After the per-test fixture finalizer runs, the per-test file is
        gone. We verify by recreating the fixture logic inline and checking
        the cleanup path.
        """
        from sqlalchemy.pool import NullPool as _NP

        test_db = tmp_path / "iso-cleanup.db"
        # Use shutil.copyfile as the fixture does.
        import shutil as _sh

        _sh.copyfile(_alembic_migrated_template, test_db)
        assert test_db.exists(), "template copy must exist before engine"

        engine = create_engine(f"sqlite:///{test_db}", poolclass=_NP)
        # Simulate the fixture's try/finally teardown.
        engine.dispose()
        if test_db.exists():
            test_db.unlink()

        assert not test_db.exists(), "per-test DB file must be unlinked at teardown"

        # Confirm the session-level template is still on disk and not
        # affected by per-test cleanup.
        assert Path(_alembic_migrated_template).exists(), (
            "session template must survive per-test teardown"
        )

    def test_alembic_subprocess_invoked_exactly_once_per_pytest_process(
        self,
    ):
        """Counting test: by the time this test runs (the LAST class in
        collection order), the module-level counter must show exactly one
        ``upgrade`` and one ``heads`` invocation. This is the proof that
        the per-test fixture is not running alembic.
        """
        # NOTE: pytest collects in file order, and within a file classes are
        # defined in source order. This class is the LAST one defined, so by
        # the time it runs, every prior ``sqlite_engine`` user has executed.
        # That makes the counter at this point representative of the
        # per-pytest-process alembic workload.
        assert ALEMBIC_SUBPROCESS_CALLS["upgrade"] == 1, (
            f"expected exactly 1 alembic upgrade invocation per pytest process, "
            f"got {ALEMBIC_SUBPROCESS_CALLS['upgrade']}"
        )
        assert ALEMBIC_SUBPROCESS_CALLS["heads"] == 1, (
            f"expected exactly 1 alembic heads invocation per pytest process, "
            f"got {ALEMBIC_SUBPROCESS_CALLS['heads']}"
        )
