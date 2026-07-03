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
from sqlalchemy.engine import Engine

from cold_storage.modules.orchestration.application.outbox_dispatcher_port import (
    ClaimedOutboxEvent,
)
from cold_storage.modules.orchestration.application.outbox_errors import (
    OutboxClaimLostError,
    OutboxMaterializationMismatchError,
    OutboxPayloadIntegrityError,
)
from cold_storage.modules.orchestration.application.outbox_identity import (
    compute_envelope_hash,
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


def _generate_claim_token() -> str:
    return str(uuid4())


def _is_sqlite_engine(engine: Engine) -> bool:
    """Return True if *engine* is a SQLite dialect."""
    return engine.dialect.name == "sqlite"


def _compare_now_for_dialect(session: Any, now: datetime) -> datetime:
    """Return *now* in a form suitable for SQL WHERE lease comparisons.

    SQLite stores naive datetimes, so strip tzinfo for SQLite.
    PostgreSQL stores aware datetimes, so keep tzinfo.
    """
    try:
        bind = session.get_bind()
        if _is_sqlite_engine(bind) and now.tzinfo is not None:
            return now.replace(tzinfo=None)
    except Exception:
        pass
    return now


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
        per_row_token = _generate_claim_token()
        row.status = "PROCESSING"
        row.claimed_at = now
        row.claimed_by = worker_id
        row.claim_token = per_row_token
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
                claim_token=per_row_token,
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
    engine: Any,
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: float,
    now: datetime,
) -> list[ClaimedOutboxEvent]:
    """SQLite atomic claim using BEGIN IMMEDIATE on an independent connection.

    The caller passes the Engine directly so this function can open a
    dedicated connection and acquire an exclusive write lock via
    ``BEGIN IMMEDIATE`` — concurrent workers cannot interleave between the
    eligibility SELECT and the guarded UPDATE. The guarded UPDATE repeats
    the eligibility predicate (``PENDING AND next_retry_at <= now`` OR
    ``PROCESSING AND claim_expires_at <= now``) so that even if the SELECT
    picked rows another worker is racing to claim, only one wins per row.

    Each row receives an independent ``claim_token = uuid4()``. The
    RETURNING clause yields the exact set of rows actually claimed — the
    caller never sees ghost rows.
    """
    now = ensure_utc_aware(now)
    now_naive = now.replace(tzinfo=None).replace(microsecond=0)
    now_str = now_naive.strftime("%Y-%m-%d %H:%M:%S")
    expires_at = now_naive + timedelta(seconds=lease_seconds)
    expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: deterministically select eligible IDs under IMMEDIATE lock
    select_ids_sql = text(
        "SELECT id FROM orchestration_audit_outbox "
        "WHERE (status = 'PENDING' AND substr(next_retry_at,1,19) <= :now_str) "
        "   OR (status = 'PROCESSING' AND substr(claim_expires_at,1,19) <= :now_str) "
        "ORDER BY next_retry_at ASC, created_at ASC, id ASC "
        "LIMIT :batch_size"
    )

    # Step 2: guarded UPDATE — repeat the eligibility predicate, RETURNING
    # the columns we need for downstream processing. UPDATE returns 0 rows
    # for any ID that lost the race.
    update_returning_sql = text(
        "UPDATE orchestration_audit_outbox "
        "SET status = 'PROCESSING', "
        "    claimed_at = :now_str, "
        "    claimed_by = :worker_id, "
        "    claim_token = :per_row_token, "
        "    claim_expires_at = :expires_str, "
        "    attempt_count = attempt_count + 1 "
        "WHERE id = :row_id "
        "  AND ((status = 'PENDING' AND substr(next_retry_at,1,19) <= :now_str) "
        "       OR (status = 'PROCESSING' AND substr(claim_expires_at,1,19) <= :now_str)) "
        "RETURNING id, event_identity, event_type, event_schema_version, "
        "          aggregate_type, aggregate_id, actor, correlation_id, occurred_at, "
        "          payload, payload_hash, attempt_count, "
        "          request_id, identity_id, attempt_id, "
        "          calculation_run_id, source_binding_id"
    )

    claimed: list[ClaimedOutboxEvent] = []
    # Independent connection: SQLite serializes writers, so BEGIN IMMEDIATE
    # gives us an exclusive write lock for the duration of the claim txn.
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            id_rows = conn.execute(
                select_ids_sql, {"now_str": now_str, "batch_size": batch_size}
            ).fetchall()

            for (row_id,) in id_rows:
                per_row_token = _generate_claim_token()
                returning = conn.execute(
                    update_returning_sql,
                    {
                        "now_str": now_str,
                        "worker_id": worker_id,
                        "per_row_token": per_row_token,
                        "expires_str": expires_str,
                        "row_id": row_id,
                    },
                ).fetchone()
                if returning is None:
                    # Lost the race for this row — skip without raising.
                    continue
                claimed.append(
                    ClaimedOutboxEvent(
                        outbox_row_id=returning[0],
                        event_identity=returning[1],
                        event_type=returning[2],
                        event_schema_version=returning[3],
                        aggregate_type=returning[4],
                        aggregate_id=returning[5],
                        actor=returning[6],
                        correlation_id=returning[7],
                        occurred_at=returning[8],
                        payload=returning[9],
                        payload_hash=returning[10],
                        attempt_count=returning[11],
                        claim_token=per_row_token,
                        claim_expires_at=expires_at,
                        request_id=returning[12],
                        identity_id=returning[13],
                        attempt_id=returning[14],
                        calculation_run_id=returning[15],
                        source_binding_id=returning[16],
                    )
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
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
    Uses dialect-aware comparison: SQLite stores naive datetimes,
    PostgreSQL stores aware datetimes.
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

    now_compare = _compare_now_for_dialect(session, now)
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
    P0-4: CAS includes claim_expires_at > now for lease boundary check.
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

    # 3b. Fail closed on empty envelope_hash (no legacy skip)
    if not db_row.envelope_hash:
        raise OutboxPayloadIntegrityError(db_row.id, db_row.envelope_hash or "", "")
    # 3c. Verify envelope hash integrity against the full frozen envelope
    actual_envelope_hash = compute_envelope_hash(
        event_identity=db_row.event_identity,
        event_schema_version=db_row.event_schema_version,
        event_type=db_row.event_type,
        aggregate_type=db_row.aggregate_type,
        aggregate_id=db_row.aggregate_id,
        actor=db_row.actor,
        correlation_id=db_row.correlation_id,
        occurred_at=db_row.occurred_at,
        request_id=db_row.request_id,
        identity_id=db_row.identity_id,
        attempt_id=db_row.attempt_id,
        calculation_run_id=db_row.calculation_run_id,
        source_binding_id=db_row.source_binding_id,
        payload=db_row.payload,
    )
    if actual_envelope_hash != db_row.envelope_hash:
        raise OutboxPayloadIntegrityError(db_row.id, db_row.envelope_hash, actual_envelope_hash)

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
            "occurred_at": (
                ensure_utc_aware(db_row.occurred_at).isoformat() if db_row.occurred_at else None
            ),
            "payload_hash": db_row.payload_hash,
            "envelope_hash": db_row.envelope_hash,
            "request_id": db_row.request_id,
            "identity_id": db_row.identity_id,
            "attempt_id": db_row.attempt_id,
            "calculation_run_id": db_row.calculation_run_id,
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
    # P0-4: Added claim_expires_at > now for lease boundary check
    now_compare = _compare_now_for_dialect(session, now)
    result = session.execute(
        update(AuditOutboxRecord)
        .where(
            AuditOutboxRecord.id == claimed.outbox_row_id,
            AuditOutboxRecord.status == "PROCESSING",
            AuditOutboxRecord.claimed_by == worker_id,
            AuditOutboxRecord.claim_token == claim_token,
            AuditOutboxRecord.claim_expires_at > now_compare,
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

    now_compare = _compare_now_for_dialect(session, current_time)
    result = session.execute(
        update(AuditOutboxRecord)
        .where(
            AuditOutboxRecord.id == event_id,
            AuditOutboxRecord.status == "PROCESSING",
            AuditOutboxRecord.claimed_by == worker_id,
            AuditOutboxRecord.claim_token == claim_token,
            AuditOutboxRecord.claim_expires_at > now_compare,
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

    now_compare = _compare_now_for_dialect(session, current_time)
    result = session.execute(
        update(AuditOutboxRecord)
        .where(
            AuditOutboxRecord.id == event_id,
            AuditOutboxRecord.status == "PROCESSING",
            AuditOutboxRecord.claimed_by == worker_id,
            AuditOutboxRecord.claim_token == claim_token,
            AuditOutboxRecord.claim_expires_at > now_compare,
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
    """Check if an IntegrityError is a unique conflict on audit_events.outbox_event_id.

    P0-9: Exact match — no substring matching or error text fallback.
    - PG: SQLSTATE == '23505' AND constraint_name == 'audit_events_outbox_event_id_key'
    - SQLite: extended error code == 2067 (SQLITE_CONSTRAINT_UNIQUE) AND the
      failed column set must equal exactly {audit_events.outbox_event_id}.
      Other UNIQUE / composite / FK / CHECK / NOT NULL must propagate.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False

    # ── PostgreSQL ──────────────────────────────────────────────────────
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == "23505":
        diag = getattr(orig, "diag", None)
        constraint_name = None
        if diag is not None:
            constraint_name = getattr(diag, "constraint_name", None)
        if constraint_name is None:
            constraint_name = getattr(orig, "constraint_name", None)
        return constraint_name == "audit_events_outbox_event_id_key"

    # ── SQLite ──────────────────────────────────────────────────────────
    sqlite_errcode = getattr(orig, "sqlite_errorcode", None)
    if sqlite_errcode is not None:
        if sqlite_errcode == 2067:  # SQLITE_CONSTRAINT_UNIQUE
            # Parse the error message and require the *exact* failed column set
            orig_str = str(orig)
            if "UNIQUE constraint failed:" not in orig_str:
                return False
            detail = orig_str.split("UNIQUE constraint failed:", 1)[-1].strip()
            entries = [e.strip() for e in detail.split(",") if e.strip()]
            parsed: set[tuple[str, str]] = set()
            for entry in entries:
                if "." not in entry:
                    return False
                tbl, col = entry.rsplit(".", 1)
                parsed.add((tbl.strip(), col.strip()))
            # Exact column-set match required
            return parsed == {("audit_events", "outbox_event_id")}
        return False

    return False


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
