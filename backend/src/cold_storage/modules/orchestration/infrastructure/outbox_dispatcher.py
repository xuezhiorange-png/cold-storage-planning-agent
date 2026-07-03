"""Infrastructure implementation of the audit outbox dispatcher.

Handles dialect-aware claim (PG: FOR UPDATE SKIP LOCKED, SQLite: IMMEDIATE txn),
idempotent AuditEvent materialization, and state transitions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import exc as sa_exc
from sqlalchemy import select, text, update

from cold_storage.modules.orchestration.application.outbox_dispatcher_port import (
    ClaimedOutboxEvent,
)
from cold_storage.modules.orchestration.application.outbox_errors import (
    OutboxClaimLostError,
    OutboxMaterializationMismatchError,
    OutboxPayloadIntegrityError,
)
from cold_storage.modules.orchestration.application.outbox_identity import (
    compute_payload_hash,
    ensure_utc_aware,
)
from cold_storage.modules.orchestration.application.outbox_retry import (
    DEFAULT_RETRY_POLICY,
    RetryPolicy,
)
from cold_storage.modules.orchestration.infrastructure.orm import AuditOutboxRecord
from cold_storage.modules.projects.infrastructure.orm import AuditEventRecord

# ── Claim token ────────────────────────────────────────────────────────────

_NEW_CLAIM_TOKEN_NONE = None  # sentinel


def _generate_claim_token() -> str:
    return str(uuid4())


# ── Dialect-aware claim ────────────────────────────────────────────────────


def claim_events_pg(
    session: Any,
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: float,
    now: datetime,
) -> list[ClaimedOutboxEvent]:
    """PostgreSQL claim using FOR UPDATE SKIP LOCKED in a short transaction."""
    now = ensure_utc_aware(now)
    expires_at = now + timedelta(seconds=lease_seconds)
    token = _generate_claim_token()

    eligible = (
        session.execute(
            select(AuditOutboxRecord)
            .where(
                ((AuditOutboxRecord.status == "PENDING") & (AuditOutboxRecord.next_retry_at <= now))
                | (
                    (AuditOutboxRecord.status == "PROCESSING")
                    & (AuditOutboxRecord.claim_expires_at <= now)
                )
            )
            .order_by(
                AuditOutboxRecord.next_retry_at.asc(),
                AuditOutboxRecord.created_at.asc(),
                AuditOutboxRecord.id.asc(),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

    claimed: list[ClaimedOutboxEvent] = []
    for row in eligible:
        row.status = "PROCESSING"
        row.claimed_at = now
        row.claimed_by = worker_id
        row.claim_token = token
        row.claim_expires_at = expires_at
        row.attempt_count += 1
        claimed.append(
            ClaimedOutboxEvent(
                outbox_row_id=row.id,
                event_identity=row.event_identity,
                event_type=row.event_type,
                event_schema_version=row.event_schema_version,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                actor=row.actor,
                correlation_id=row.correlation_id,
                occurred_at=row.occurred_at,
                payload=row.payload,
                payload_hash=row.payload_hash,
                attempt_count=row.attempt_count,
                claim_token=token,
                claim_expires_at=expires_at,
                request_id=row.request_id,
                identity_id=row.identity_id,
                attempt_id=row.attempt_id,
                calculation_run_id=row.calculation_run_id,
                source_binding_id=row.source_binding_id,
            )
        )
    session.flush()
    return claimed


def claim_events_sqlite(
    session: Any,
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: float,
    now: datetime,
) -> list[ClaimedOutboxEvent]:
    """SQLite claim using a single atomic write transaction.

    SQLite stores datetimes as ISO format strings without timezone.
    We use ``text()`` for the eligibility query to ensure correct
    datetime comparison at the SQL level.
    """
    # Normalize to naive UTC for SQLite datetime comparison.
    now = ensure_utc_aware(now)
    now_naive = now.replace(tzinfo=None)
    now_naive = now_naive.replace(microsecond=0)
    now_str = now_naive.strftime("%Y-%m-%d %H:%M:%S")
    expires_at = now_naive + timedelta(seconds=lease_seconds)
    token = _generate_claim_token()

    eligible = (
        session.execute(
            select(AuditOutboxRecord)
            .where(
                text(
                    "(status = 'PENDING' AND substr(next_retry_at,1,19) <= :now_str)"
                    " OR (status = 'PROCESSING' AND substr(claim_expires_at,1,19) <= :now_str)"
                )
            )
            .params(now_str=now_str)
            .order_by(
                AuditOutboxRecord.next_retry_at.asc(),
                AuditOutboxRecord.created_at.asc(),
                AuditOutboxRecord.id.asc(),
            )
            .limit(batch_size)
        )
        .scalars()
        .all()
    )

    claimed: list[ClaimedOutboxEvent] = []
    for row in eligible:
        row.status = "PROCESSING"
        row.claimed_at = now_naive
        row.claimed_by = worker_id
        row.claim_token = token
        row.claim_expires_at = expires_at
        row.attempt_count += 1
        claimed.append(
            ClaimedOutboxEvent(
                outbox_row_id=row.id,
                event_identity=row.event_identity,
                event_type=row.event_type,
                event_schema_version=row.event_schema_version,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                actor=row.actor,
                correlation_id=row.correlation_id,
                occurred_at=row.occurred_at,
                payload=row.payload,
                payload_hash=row.payload_hash,
                attempt_count=row.attempt_count,
                claim_token=token,
                claim_expires_at=expires_at,
                request_id=row.request_id,
                identity_id=row.identity_id,
                attempt_id=row.attempt_id,
                calculation_run_id=row.calculation_run_id,
                source_binding_id=row.source_binding_id,
            )
        )
    session.flush()
    return claimed


# ── Claim validation ───────────────────────────────────────────────────────


def validate_claim(
    session: Any,
    *,
    event_id: str,
    worker_id: str,
    claim_token: str,
    now: datetime,
) -> AuditOutboxRecord:
    """Validate that a claim is still active.

    Raises OutboxClaimLostError if the claim has been superseded.
    Normalizes ``now`` to naive for SQLite compatibility.
    """
    now = ensure_utc_aware(now)
    row = session.execute(
        select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
    ).scalar_one_or_none()

    if row is None:
        raise OutboxClaimLostError(event_id, worker_id, claim_token)

    if row.status != "PROCESSING":
        raise OutboxClaimLostError(event_id, worker_id, claim_token)

    if row.claimed_by != worker_id or row.claim_token != claim_token:
        raise OutboxClaimLostError(event_id, worker_id, claim_token)

    now_compare = now.replace(tzinfo=None) if now.tzinfo is not None else now
    if row.claim_expires_at is not None and row.claim_expires_at <= now_compare:
        raise OutboxClaimLostError(event_id, worker_id, claim_token)

    result: AuditOutboxRecord = row
    return result


# ── Materialization ────────────────────────────────────────────────────────


def materialize_event(
    session: Any,
    *,
    claimed: ClaimedOutboxEvent,
    worker_id: str,
    claim_token: str,
    now: datetime,
) -> None:
    """Materialize a claimed event into AuditEventRecord and mark outbox PUBLISHED.

    Must be called within the same transaction that validates the claim.
    AuditEvent creation and outbox PUBLISHED update happen atomically.

    P0-6: After validate_claim(), re-read the outbox row from the database
    and use the DB row for ALL event data.
    P0-7: AuditEvent INSERT is wrapped in a SAVEPOINT for idempotency.
    P0-8: AuditEvent INSERT + outbox PUBLISHED update are in the same function.
    """
    now = ensure_utc_aware(now)

    # 1. Validate claim is still active
    validate_claim(
        session,
        event_id=claimed.outbox_row_id,
        worker_id=worker_id,
        claim_token=claim_token,
        now=now,
    )

    # 2. P0-6: Re-read outbox row from DB — use DB row for ALL event data
    db_row = session.execute(
        select(AuditOutboxRecord).where(AuditOutboxRecord.id == claimed.outbox_row_id)
    ).scalar_one_or_none()
    if db_row is None:
        raise OutboxClaimLostError(claimed.outbox_row_id, worker_id, claim_token)

    # 3. Verify payload integrity from the DB row
    actual_hash = compute_payload_hash(db_row.payload)
    if actual_hash != db_row.payload_hash:
        raise OutboxPayloadIntegrityError(db_row.id, db_row.payload_hash, actual_hash)

    # 4. Build AuditEventRecord from the frozen DB row (NOT claimed DTO)
    audit_event = AuditEventRecord(
        id=str(uuid4()),
        actor=db_row.actor,
        action=db_row.event_type,
        entity_type=db_row.aggregate_type,
        entity_id=db_row.aggregate_id,
        before_snapshot={},
        after_snapshot=db_row.payload,
        event_metadata={
            "event_identity": db_row.event_identity,
            "event_schema_version": db_row.event_schema_version,
            "correlation_id": db_row.correlation_id,
            "occurred_at": db_row.occurred_at.isoformat() if db_row.occurred_at else None,
            "payload_hash": db_row.payload_hash,
            "request_id": db_row.request_id,
            "identity_id": db_row.identity_id,
            "attempt_id": db_row.attempt_id,
            "source_binding_id": db_row.source_binding_id,
        },
        created_at=now,
        outbox_event_id=db_row.event_identity,
    )

    # 5. P0-7: Insert AuditEvent via SAVEPOINT (idempotent)
    nested = session.begin_nested()
    try:
        session.add(audit_event)
        session.flush()
        nested.commit()
    except (sa_exc.IntegrityError, sa_exc.InternalError) as exc:
        nested.rollback()
        # Handle exact unique conflict on outbox_event_id
        if _is_outbox_event_id_conflict(exc):
            # Idempotent: existing event must match
            existing = session.execute(
                select(AuditEventRecord).where(
                    AuditEventRecord.outbox_event_id == db_row.event_identity
                )
            ).scalar_one_or_none()
            if existing is None:
                raise
            mismatches = _compare_audit_events(audit_event, existing)
            if mismatches:
                raise OutboxMaterializationMismatchError(db_row.event_identity, mismatches) from exc
            # Idempotent match — continue to mark published
        else:
            raise

    # 6. P0-8: Mark outbox PUBLISHED (CAS: must still be PROCESSING with correct token)
    result = session.execute(
        update(AuditOutboxRecord)
        .where(
            AuditOutboxRecord.id == claimed.outbox_row_id,
            AuditOutboxRecord.status == "PROCESSING",
            AuditOutboxRecord.claimed_by == worker_id,
            AuditOutboxRecord.claim_token == claim_token,
        )
        .values(
            status="PUBLISHED",
            published_at=now,
            claimed_at=None,
            claimed_by=None,
            claim_token=None,
            claim_expires_at=None,
        )
    )
    if result.rowcount == 0:
        raise OutboxClaimLostError(claimed.outbox_row_id, worker_id, claim_token)

    session.flush()


# ── Failure handling ───────────────────────────────────────────────────────


def mark_retryable_failure(
    session: Any,
    *,
    event_id: str,
    worker_id: str,
    claim_token: str,
    error: Exception,
    retry_policy: RetryPolicy | None = None,
    now: datetime | None = None,
) -> None:
    """Return a claimed event to PENDING with retry metadata."""
    policy = retry_policy or DEFAULT_RETRY_POLICY
    current_time = ensure_utc_aware(now or datetime.now(UTC))

    # Read current attempt count for backoff
    row = session.execute(
        select(AuditOutboxRecord).where(AuditOutboxRecord.id == event_id)
    ).scalar_one_or_none()
    if row is not None:
        next_retry = policy.next_retry_at(
            attempt_count=row.attempt_count,
            now=current_time,
        )
    else:
        next_retry = policy.next_retry_at(
            attempt_count=0,
            now=current_time,
        )

    result = session.execute(
        update(AuditOutboxRecord)
        .where(
            AuditOutboxRecord.id == event_id,
            AuditOutboxRecord.status == "PROCESSING",
            AuditOutboxRecord.claimed_by == worker_id,
            AuditOutboxRecord.claim_token == claim_token,
        )
        .values(
            status="PENDING",
            next_retry_at=next_retry,
            claimed_at=None,
            claimed_by=None,
            claim_token=None,
            claim_expires_at=None,
            last_error_class=type(error).__name__,
            last_error_code=getattr(error, "reason", str(error))[:100],
            last_error_details={"error": str(error)},
            last_error_at=current_time,
        )
    )
    if result.rowcount == 0:
        raise OutboxClaimLostError(event_id, worker_id, claim_token)
    session.flush()


def mark_terminal_failure(
    session: Any,
    *,
    event_id: str,
    worker_id: str,
    claim_token: str,
    error: Exception,
    now: datetime | None = None,
) -> None:
    """Move a claimed event to the FAILED terminal state."""
    current_time = ensure_utc_aware(now or datetime.now(UTC))

    result = session.execute(
        update(AuditOutboxRecord)
        .where(
            AuditOutboxRecord.id == event_id,
            AuditOutboxRecord.status == "PROCESSING",
            AuditOutboxRecord.claimed_by == worker_id,
            AuditOutboxRecord.claim_token == claim_token,
        )
        .values(
            status="FAILED",
            failed_at=current_time,
            claimed_at=None,
            claimed_by=None,
            claim_token=None,
            claim_expires_at=None,
            last_error_class=type(error).__name__,
            last_error_code=getattr(error, "reason", str(error))[:100],
            last_error_details={"error": str(error)},
            last_error_at=current_time,
        )
    )
    if result.rowcount == 0:
        raise OutboxClaimLostError(event_id, worker_id, claim_token)
    session.flush()


# ── Helpers ────────────────────────────────────────────────────────────────


def _is_outbox_event_id_conflict(exc: Exception) -> bool:
    """Check if an IntegrityError is on audit_events.outbox_event_id."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False

    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False

    diag = getattr(orig, "diag", None)
    constraint_name = None
    if diag is not None:
        constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name is None:
        constraint_name = getattr(orig, "constraint_name", None)

    # PostgreSQL: uq_audit_events_outbox_event_id or audit_events_outbox_event_id_key
    # SQLite: uq_audit_events_outbox_event_id
    if constraint_name and "outbox_event_id" in constraint_name:
        return True

    # Fallback: check error message
    err_str = str(orig).lower()
    return "audit_events" in err_str and "outbox_event_id" in err_str


def _compare_audit_events(
    new: AuditEventRecord,
    existing: AuditEventRecord,
) -> list[str]:
    """Compare two AuditEventRecords for idempotency match.

    Returns a list of mismatched field names, empty if they match.
    """
    fields_to_compare = [
        "action",
        "entity_type",
        "entity_id",
        "actor",
        "before_snapshot",
        "after_snapshot",
        "event_metadata",
    ]
    mismatches: list[str] = []
    for field in fields_to_compare:
        new_val = getattr(new, field, None)
        existing_val = getattr(existing, field, None)
        if new_val != existing_val:
            mismatches.append(field)
    return mismatches
