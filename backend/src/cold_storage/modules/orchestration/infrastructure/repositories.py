"""Orchestration repository protocols — session-bound, never commits.

Repository methods accept a SQLAlchemy Session and operate within the
caller's transaction boundary.  They MUST NOT call ``session.commit()``,
``session.rollback()``, ``session.close()``, or create sessions.

Concrete SQLAlchemy implementations are provided for all protocols
needed by Transaction A (request + snapshot + context + identity +
attempt).

Concurrent-safety: get-or-create methods use nested-transaction retry
targeting only the specific unique constraint for each entity.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cold_storage.modules.orchestration.application.ports import (
        TerminalTransitionResult,
    )
    from cold_storage.modules.orchestration.application.transaction_b import (
        VerificationState,
    )

from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.ports import (
    AuditOutboxRepository,
    CalculationRunRepository,
    CoefficientContextRepository,
    ExecutionSnapshotRepository,
    OrchestrationAttemptRepository,
    OrchestrationIdentityRepository,
    OrchestrationRequestRepository,
    SourceBindingRepository,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    RequestStatus,
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def _ensure_str(value: object) -> str:
    """Safe cast from dict[str, object] to str."""
    if not isinstance(value, str):
        raise TypeError(f"Expected str, got {type(value).__name__}")
    return value


def _ensure_datetime(value: object) -> datetime:
    """Safe cast from dict[str, object] to datetime.

    SQLite stores naive datetimes — add UTC timezone if missing.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"Expected datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        from datetime import UTC

        return value.replace(tzinfo=UTC)
    return value


def _require_idempotency_key(value: str | None) -> str:
    """Phase 1 (P1-2) repository-level invariant for new writes.

    The ``orchestration_run_attempts.idempotency_key`` column is
    NULLABLE at the schema layer so that legacy rows (pre-Phase-1)
    can carry NULL without breaking the upgrade path. But for any
    new write — application, repository, fixture, or migration —
    a NULL ``idempotency_key`` is an invariant violation: it
    defeats the unique index ``uq_attempt_idempotency_key_db`` and
    silently corrupts the deduplication contract.

    This helper enforces the invariant at the call site. New
    repository write paths that need to insert an attempt should
    call ``_require_idempotency_key(...)`` on the inbound value
    and pass the returned non-null string to the ORM. Tests in
    ``tests/unit/repositories/test_phase1_idempotency_required.py``
    assert the helper's behaviour.
    """
    if value is None:
        raise ValueError(
            "idempotency_key is required on new attempt writes "
            "(Phase 1 schema contract; legacy rows pre-Phase-1 are "
            "an explicit exception handled by the migration, not "
            "by the repository). Refusing to insert NULL."
        )
    if not isinstance(value, str):
        raise TypeError(f"idempotency_key must be str, got {type(value).__name__}")
    if not value:
        raise ValueError("idempotency_key must be a non-empty string (Phase 1 schema contract).")
    return value


def _is_target_unique_violation(
    exc: sa_exc.IntegrityError,
    *,
    postgres_constraint_names: frozenset[str] | None = None,
    sqlite_table: str | None = None,
    sqlite_column_sets: frozenset[tuple[str, ...]] | None = None,
) -> bool:
    """Return True if *exc* matches a target unique constraint.

    PostgreSQL:
      Reads ``diag.constraint_name`` and requires an exact match against one of
      *postgres_constraint_names*.  No substring or prefix matching.

    SQLite:
      Reads ``sqlite_errorcode`` (SQLITE_CONSTRAINT_UNIQUE / PRIMARYKEY only).
      Then parses the error message to extract the table and column set, and
      requires an exact match against *sqlite_column_sets*.

    Non-target FK, CHECK, NOT NULL, and non-target UNIQUE violations are never
    matched and must propagate to the caller.
    """
    if exc.orig is None:
        return False

    # ── PostgreSQL ───────────────────────────────────────────────────────
    pg_name: str | None = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if pg_name is not None:
        if postgres_constraint_names is None:
            return False
        return pg_name in postgres_constraint_names

    # ── SQLite ───────────────────────────────────────────────────────────
    # Verify the SQLite extended error code is UNIQUE or PRIMARY KEY constraint
    sqlite_errcode = getattr(exc.orig, "sqlite_errorcode", None)
    if sqlite_errcode is None:
        return False

    # SQLITE_CONSTRAINT_UNIQUE = 2067, SQLITE_CONSTRAINT_PRIMARYKEY = 1555
    _SQLITE_UNIQUE = 2067
    _SQLITE_PRIMARYKEY = 1555

    if sqlite_errcode not in {_SQLITE_UNIQUE, _SQLITE_PRIMARYKEY}:
        return False

    if sqlite_table is None or sqlite_column_sets is None:
        return False

    # Parse table and columns from: "UNIQUE constraint failed: table.col1, table.col2"
    orig_str = str(exc.orig)
    if "UNIQUE constraint failed" not in orig_str and "PRIMARY KEY" not in orig_str:
        return False

    parts = orig_str.split(":", 1)
    if len(parts) < 2:
        return False

    detail = parts[1].strip()
    entries = [e.strip() for e in detail.split(",")]
    table_cols: dict[str, set[str]] = {}
    for entry in entries:
        if "." in entry:
            tbl, col = entry.rsplit(".", 1)
            table_cols.setdefault(tbl, set()).add(col)

    columns_for_table = table_cols.get(sqlite_table, set())
    if not columns_for_table:
        return False

    target_sets = {frozenset(s) for s in sqlite_column_sets}
    return frozenset(columns_for_table) in target_sets


# ── Attempt insert conflict classifier ────────────────────────────────────


class AttemptInsertConflictKind(StrEnum):
    """Classifies IntegrityError on attempt INSERT for targeted recovery."""

    IDENTITY_NUMBER = "identity_number"
    ONE_RUNNING = "one_running"
    NON_TARGET = "non_target"


def _classify_attempt_insert_integrity_error(
    exc: sa_exc.IntegrityError,
) -> AttemptInsertConflictKind:
    """Classify an IntegrityError from attempt INSERT.

    Returns IDENTITY_NUMBER if the violation is on uq_attempt_identity_number,
    ONE_RUNNING if on uq_attempt_one_running (partial unique index),
    or NON_TARGET for any other constraint violation.
    """
    pg_name: str | None = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if pg_name == "uq_attempt_identity_number":
        return AttemptInsertConflictKind.IDENTITY_NUMBER
    if pg_name == "uq_attempt_one_running":
        return AttemptInsertConflictKind.ONE_RUNNING

    # SQLite: parse message to determine which column set matches.
    sqlite_errcode = getattr(exc.orig, "sqlite_errorcode", None)
    if sqlite_errcode is not None:
        _SQLITE_UNIQUE = 2067
        _SQLITE_PRIMARYKEY = 1555
        if sqlite_errcode in {_SQLITE_UNIQUE, _SQLITE_PRIMARYKEY}:
            orig_str = str(exc.orig)
            if "UNIQUE constraint failed" in orig_str:
                parts = orig_str.split(":", 1)
                if len(parts) >= 2:
                    detail = parts[1].strip()
                    entries = [e.strip() for e in detail.split(",")]
                    cols = set()
                    for entry in entries:
                        if "." in entry:
                            _, col = entry.rsplit(".", 1)
                            cols.add(col)
                    if cols == {"identity_id", "attempt_number"}:
                        return AttemptInsertConflictKind.IDENTITY_NUMBER
                    if cols == {"identity_id"}:
                        return AttemptInsertConflictKind.ONE_RUNNING

    return AttemptInsertConflictKind.NON_TARGET


# ── Test hooks protocol ─────────────────────────────────────────────────────


@runtime_checkable
class AttemptAcquireTestHooks(Protocol):
    """Optional injection points for testing concurrent acquire() paths."""

    def after_running_lookup(
        self,
        *,
        identity_id: str,
        running_attempt: dict[str, object] | None,
        retry_index: int,
    ) -> None: ...
    def after_next_number_read(
        self,
        *,
        identity_id: str,
        next_attempt_number: int,
        retry_index: int,
    ) -> None: ...
    def before_attempt_flush(
        self,
        *,
        identity_id: str,
        attempt_number: int,
        retry_index: int,
    ) -> None: ...
    def after_integrity_conflict(
        self,
        *,
        constraint_name: str | None,
        identity_id: str,
        attempt_number: int,
        retry_index: int,
    ) -> None: ...
    def after_retry_state_refresh(
        self,
        *,
        identity_id: str,
        running_attempt: dict[str, object] | None,
        max_attempt_number: int,
        retry_index: int,
    ) -> None: ...


# ── Orchestration Request ───────────────────────────────────────────────────


class SqlAlchemyOrchestrationRequestRepository(OrchestrationRequestRepository):
    """Session-bound repository for ``OrchestrationRequestRecord``."""

    def add(
        self,
        session: Session,
        /,
        *,
        requested_project_id: str,
        requested_project_version_id: str,
        request_fingerprint: str,
        actor: str,
        correlation_id: str,
    ) -> str:
        from uuid import uuid4

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRequestRecord,
        )

        record = OrchestrationRequestRecord(
            id=str(uuid4()),
            requested_project_id=requested_project_id,
            requested_project_version_id=requested_project_version_id,
            request_fingerprint=request_fingerprint,
            actor=actor,
            correlation_id=correlation_id,
            status="PENDING",
        )
        session.add(record)
        session.flush()
        return record.id

    def update_status(
        self,
        session: Session,
        /,
        request_id: str,
        *,
        status: RequestStatus,
        failure_code: str | None = None,
        failure_field: str | None = None,
        failure_details: dict[str, object] | None = None,
        resolved_project_id: str | None = None,
        resolved_project_version_id: str | None = None,
        resolved_identity_id: str | None = None,
        resolved_attempt_id: str | None = None,
    ) -> None:
        from datetime import UTC, datetime

        from sqlalchemy import update

        from cold_storage.modules.orchestration.domain.errors import (
            PersistenceInvariantError,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRequestRecord,
        )

        values: dict[str, object] = {
            "status": status.value,
            "failure_code": failure_code,
            "failure_field": failure_field,
            "failure_details": failure_details,
            "resolved_project_id": resolved_project_id,
            "resolved_project_version_id": resolved_project_version_id,
            "resolved_identity_id": resolved_identity_id,
            "resolved_attempt_id": resolved_attempt_id,
            "completed_at": datetime.now(UTC),
        }
        stmt = (
            update(OrchestrationRequestRecord)
            .where(OrchestrationRequestRecord.id == request_id)
            .values(**{k: v for k, v in values.items() if v is not None or k == "status"})
        )
        result = session.execute(stmt)
        if hasattr(result, "rowcount") and result.rowcount == 0:
            raise PersistenceInvariantError(
                f"update_status affected 0 rows for request_id={request_id!r}"
            )

    def get_status(self, session: Session, /, request_id: str) -> str | None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRequestRecord,
        )

        row = session.execute(
            select(OrchestrationRequestRecord.status).where(
                OrchestrationRequestRecord.id == request_id
            )
        ).scalar_one_or_none()
        return row

    def get_envelope(
        self,
        session: Session,
        /,
        request_id: str,
    ) -> tuple[str, str] | None:
        """Return (actor, correlation_id) for the durable request."""
        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRequestRecord,
        )

        row = session.execute(
            select(
                OrchestrationRequestRecord.actor,
                OrchestrationRequestRecord.correlation_id,
            ).where(OrchestrationRequestRecord.id == request_id)
        ).first()
        if row is None:
            return None
        return (row[0], row[1])


# ── Execution Snapshot ──────────────────────────────────────────────────────


class SqlAlchemyExecutionSnapshotRepository(ExecutionSnapshotRepository):
    """Session-bound repository for ``ProjectVersionExecutionSnapshotRecord``."""

    _MAX_RETRIES = 3
    _TARGET_CONSTRAINT = frozenset({"uq_exec_snapshot_version_hash_schema"})
    _SQLITE_TABLE = "orchestration_execution_snapshots"
    _SQLITE_COLUMN_SETS: frozenset[tuple[str, ...]] = frozenset(
        {("project_version_id", "input_snapshot_hash", "schema_version")}
    )

    def get_or_create(
        self,
        session: Session,
        /,
        *,
        project_version_id: str,
        input_snapshot_hash: str,
        schema_version: str,
        project_id: str,
        version_number: int,
        input_snapshot: dict[str, object],
    ) -> str:
        from uuid import uuid4

        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProjectVersionExecutionSnapshotRecord,
        )

        # Try to find existing first
        existing = session.execute(
            select(ProjectVersionExecutionSnapshotRecord.id).where(
                ProjectVersionExecutionSnapshotRecord.project_version_id == project_version_id,
                ProjectVersionExecutionSnapshotRecord.input_snapshot_hash == input_snapshot_hash,
                ProjectVersionExecutionSnapshotRecord.schema_version == schema_version,
            )
        ).scalar()
        if existing:
            return str(existing)

        return self._insert_with_retry(
            session,
            ProjectVersionExecutionSnapshotRecord,
            dict(
                id=str(uuid4()),
                project_id=project_id,
                project_version_id=project_version_id,
                version_number=version_number,
                input_snapshot=input_snapshot,
                input_snapshot_hash=input_snapshot_hash,
                schema_version=schema_version,
                captured_status="approved",
            ),
            select_filter={
                "project_version_id": project_version_id,
                "input_snapshot_hash": input_snapshot_hash,
                "schema_version": schema_version,
            },
        )

    def _insert_with_retry(
        self,
        session: Session,
        model_cls: type[Any],
        fields: dict[str, object],
        select_filter: dict[str, object],
    ) -> str:
        """Concurrent-safe insert using nested transaction handle.

        Only retries on the target unique constraint violation.
        All other IntegrityError subclasses propagate immediately.
        """
        from sqlalchemy import select

        for _attempt_no in range(self._MAX_RETRIES):
            nested = session.begin_nested()
            try:
                record = model_cls(**fields)
                session.add(record)
                session.flush()
                nested.commit()
                return str(record.id)
            except sa_exc.IntegrityError as exc:
                nested.rollback()
                if not _is_target_unique_violation(
                    exc,
                    postgres_constraint_names=self._TARGET_CONSTRAINT,
                    sqlite_table=self._SQLITE_TABLE,
                    sqlite_column_sets=self._SQLITE_COLUMN_SETS,
                ):
                    raise
                # Re-read — another transaction may have inserted
                stmt = select(model_cls.id)
                for k, v in select_filter.items():
                    stmt = stmt.where(getattr(model_cls, k) == v)
                existing = session.execute(stmt).scalar()
                if existing:
                    return str(existing)
                continue

        raise RuntimeError(
            f"Failed to get-or-create {model_cls.__name__} after {self._MAX_RETRIES} retries"
        )


# ── Coefficient Context ─────────────────────────────────────────────────────


class SqlAlchemyCoefficientContextRepository(CoefficientContextRepository):
    """Session-bound repository for ``CoefficientContextRecord``."""

    _MAX_RETRIES = 3
    _TARGET_CONSTRAINT = frozenset({"uq_coeff_context_version_hash"})
    _SQLITE_TABLE = "orchestration_coefficient_contexts"
    _SQLITE_COLUMN_SETS: frozenset[tuple[str, ...]] = frozenset(
        {("project_version_id", "content_hash")}
    )

    def get_or_create(
        self,
        session: Session,
        /,
        *,
        project_version_id: str,
        content_hash: str,
        content: dict[str, object],
        schema_version: str,
        project_id: str,
    ) -> str:
        from uuid import uuid4

        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            CoefficientContextRecord,
        )

        existing = session.execute(
            select(CoefficientContextRecord.id).where(
                CoefficientContextRecord.project_version_id == project_version_id,
                CoefficientContextRecord.content_hash == content_hash,
            )
        ).scalar()
        if existing:
            return str(existing)

        return self._insert_with_retry(
            session,
            CoefficientContextRecord,
            dict(
                id=str(uuid4()),
                project_id=project_id,
                project_version_id=project_version_id,
                content=content,
                content_hash=content_hash,
                schema_version=schema_version,
            ),
            select_filter={
                "project_version_id": project_version_id,
                "content_hash": content_hash,
            },
        )

    def _insert_with_retry(
        self,
        session: Session,
        model_cls: type[Any],
        fields: dict[str, object],
        select_filter: dict[str, object],
    ) -> str:
        from sqlalchemy import select

        for _attempt_no in range(self._MAX_RETRIES):
            nested = session.begin_nested()
            try:
                record = model_cls(**fields)
                session.add(record)
                session.flush()
                nested.commit()
                return str(record.id)
            except sa_exc.IntegrityError as exc:
                nested.rollback()
                if not _is_target_unique_violation(
                    exc,
                    postgres_constraint_names=self._TARGET_CONSTRAINT,
                    sqlite_table=self._SQLITE_TABLE,
                    sqlite_column_sets=self._SQLITE_COLUMN_SETS,
                ):
                    raise
                stmt = select(model_cls.id)
                for k, v in select_filter.items():
                    stmt = stmt.where(getattr(model_cls, k) == v)
                existing = session.execute(stmt).scalar()
                if existing:
                    return str(existing)
                continue

        raise RuntimeError(
            f"Failed to get-or-create {model_cls.__name__} after {self._MAX_RETRIES} retries"
        )


# ── Orchestration Identity ──────────────────────────────────────────────────


class SqlAlchemyOrchestrationIdentityRepository(OrchestrationIdentityRepository):
    """Session-bound repository for ``OrchestrationIdentityRecord``."""

    _MAX_RETRIES = 3
    _TARGET_CONSTRAINT = frozenset({"uq_orch_identity_fingerprint"})
    _SQLITE_TABLE = "orchestration_identities"
    _SQLITE_COLUMN_SETS: frozenset[tuple[str, ...]] = frozenset({("fingerprint",)})

    def get_or_create(
        self,
        session: Session,
        /,
        *,
        fingerprint: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        definition_version: str,
        calculator_version_vector: dict[str, str],
    ) -> str:
        from uuid import uuid4

        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
        )

        existing = session.execute(
            select(OrchestrationIdentityRecord.id).where(
                OrchestrationIdentityRecord.fingerprint == fingerprint,
            )
        ).scalar()
        if existing:
            return str(existing)

        return self._insert_with_retry(
            session,
            OrchestrationIdentityRecord,
            dict(
                id=str(uuid4()),
                fingerprint=fingerprint,
                execution_snapshot_id=execution_snapshot_id,
                coefficient_context_id=coefficient_context_id,
                definition_version=definition_version,
                calculator_version_vector=calculator_version_vector,
                status="ACTIVE",
            ),
            select_filter={"fingerprint": fingerprint},
        )

    def _insert_with_retry(
        self,
        session: Session,
        model_cls: type[Any],
        fields: dict[str, object],
        select_filter: dict[str, object],
    ) -> str:
        from sqlalchemy import select

        for _attempt_no in range(self._MAX_RETRIES):
            nested = session.begin_nested()
            try:
                record = model_cls(**fields)
                session.add(record)
                session.flush()
                nested.commit()
                return str(record.id)
            except sa_exc.IntegrityError as exc:
                nested.rollback()
                if not _is_target_unique_violation(
                    exc,
                    postgres_constraint_names=self._TARGET_CONSTRAINT,
                    sqlite_table=self._SQLITE_TABLE,
                    sqlite_column_sets=self._SQLITE_COLUMN_SETS,
                ):
                    raise
                stmt = select(model_cls.id)
                for k, v in select_filter.items():
                    stmt = stmt.where(getattr(model_cls, k) == v)
                existing = session.execute(stmt).scalar()
                if existing:
                    return str(existing)
                continue

        raise RuntimeError(
            f"Failed to get-or-create {model_cls.__name__} after {self._MAX_RETRIES} retries"
        )

    def set_authoritative_attempt(
        self,
        session: Session,
        /,
        identity_id: str,
        attempt_id: str,
    ) -> bool:
        from sqlalchemy import select, update

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
            OrchestrationRunAttemptRecord,
        )

        result = session.execute(
            update(OrchestrationIdentityRecord)
            .where(
                OrchestrationIdentityRecord.id == identity_id,
                OrchestrationIdentityRecord.status == "ACTIVE",
                OrchestrationIdentityRecord.id.in_(
                    select(OrchestrationRunAttemptRecord.identity_id).where(
                        OrchestrationRunAttemptRecord.id == attempt_id,
                        OrchestrationRunAttemptRecord.identity_id == identity_id,
                        OrchestrationRunAttemptRecord.status == "COMPLETED",
                    )
                ),
            )
            .values(authoritative_attempt_id=attempt_id)
        )
        return bool(result.rowcount == 1)  # type: ignore[attr-defined]

    def get_calculator_version_vector(
        self,
        session: Session,
        /,
        identity_id: str,
    ) -> dict[str, str]:
        """Load the calculator_version_vector from the identity record.

        Raises ``PersistenceInvariantError`` if the identity is not found.
        """
        from sqlalchemy import select

        from cold_storage.modules.orchestration.domain.errors import (
            PersistenceInvariantError,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
        )

        identity = session.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == identity_id)
        ).scalar_one_or_none()
        if identity is None:
            raise PersistenceInvariantError(
                f"Identity {identity_id!r} not found for calculator_version_vector lookup"
            )
        vector = identity.calculator_version_vector
        if not isinstance(vector, dict):
            raise PersistenceInvariantError(
                f"Identity {identity_id!r} has non-dict calculator_version_vector"
            )
        return dict(vector)

    def get_fingerprint(
        self,
        session: Session,
        /,
        *,
        identity_id: str,
    ) -> str:
        """Return the fingerprint persisted on the identity row.

        Slice 2C of Phase 4 / Issue #35 closes the
        ``phase3_exceptions`` retirement: this port replaces the
        application-layer direct ``OrchestrationIdentityRecord`` import
        that ``ProductionSourceBindingUseCase`` previously used to
        re-read the fingerprint before Transaction B.  The repository
        is the only layer that touches the ORM; the application layer
        receives an opaque string and remains free of SQLAlchemy.

        Returns the empty string (matching the prior
        ``_load_orchestration_fingerprint`` contract at
        ``production_source_binding.py`` §3.4) when the identity row
        is missing so callers can distinguish "no row" from "row
        present with empty fingerprint" if needed.
        """
        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
        )

        record = session.execute(
            select(OrchestrationIdentityRecord).where(
                OrchestrationIdentityRecord.id == identity_id
            )
        ).scalar_one_or_none()
        if record is None:
            return ""
        return record.fingerprint or ""


# ── Orchestration Attempt ───────────────────────────────────────────────────


class SqlAlchemyOrchestrationAttemptRepository(OrchestrationAttemptRepository):
    """Session-bound repository for ``OrchestrationRunAttemptRecord``."""

    def __init__(self, hooks: AttemptAcquireTestHooks | None = None) -> None:
        self._hooks = hooks

    _LEASE_TIMEOUT_SECONDS = 300  # 5 minutes
    _MAX_ACQUIRE_RETRIES = 3
    _TARGET_CONSTRAINTS = frozenset({"uq_attempt_identity_number", "uq_attempt_one_running"})
    _SQLITE_TABLE = "orchestration_run_attempts"
    _SQLITE_COLUMN_SETS: frozenset[tuple[str, ...]] = frozenset(
        {
            ("identity_id", "attempt_number"),
            ("identity_id",),  # partial unique index WHERE status='RUNNING'
        }
    )

    def acquire(
        self,
        session: Session,
        /,
        *,
        identity_id: str,
        heartbeat_at: datetime,
    ) -> str:
        from datetime import UTC
        from datetime import datetime as _dt
        from uuid import uuid4

        from cold_storage.modules.orchestration.domain.errors import (
            AttemptAlreadyRunningError,
            AttemptTakeoverConflictError,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        # Phase 1 schema (migrations 0035 + 0036) requires the
        # `database_backend` and `correlation_id` columns to be
        # NOT NULL with **no** server_default, so every INSERT must
        # supply explicit values. The repository is the only path
        # through which application code can insert an attempt,
        # so the abstraction derives them from runtime facts that
        # are always available at the persistence layer:
        #
        # * ``database_backend`` is read from the SQLAlchemy
        #   session's bound dialect name (the single source of
        #   truth for which backend this row is being persisted
        #   to).
        # * ``correlation_id`` for an *attempt creation* event
        #   has no caller-supplied upstream source — the
        #   durable request envelope is not yet resolved at the
        #   moment of attempt acquisition. We therefore mint a
        #   per-attempt identifier with the explicit
        #   ``attempt-corr:`` prefix so that:
        #     (a) it is unambiguously non-empty (passes the
        #         ``ck_attempt_correlation_id_nonempty`` CHECK
        #         added in 0036),
        #     (b) it does NOT collide with the legacy sentinel
        #         ``legacy-migration-0036`` (which is reserved
        #         for backfilled pre-0036 rows),
        #     (c) it does NOT collide with request-level
        #         correlation_ids minted upstream (those use the
        #         ``req-corr:`` convention enforced by
        #         ``OrchestrationRequestRepository.create``).
        # Phase 2 application code can override the per-attempt
        # correlation_id by extending the contract — for Phase 1
        # we ship the deterministic-runtime default.
        bind_dialect_name: str = session.bind.dialect.name  # type: ignore[union-attr]
        if bind_dialect_name == "postgresql":
            derived_database_backend: str = "postgresql"
        else:
            derived_database_backend = "sqlite"
        derived_correlation_id: str = f"attempt-corr:{uuid4().hex}"

        stale_attempt_id: str | None = None
        for retry_idx in range(self._MAX_ACQUIRE_RETRIES):
            # Re-read fresh state each retry
            running = self.find_running_attempt(session, identity_id)
            if self._hooks:
                self._hooks.after_running_lookup(
                    identity_id=identity_id,
                    running_attempt=running,
                    retry_index=retry_idx,
                )
            if running is not None:
                running_id: str = _ensure_str(running["id"])
                running_heartbeat: datetime = _ensure_datetime(running["heartbeat_at"])
                stale_attempt_id = running_id
                age = (_dt.now(UTC) - running_heartbeat).total_seconds()
                if age > self._LEASE_TIMEOUT_SECONDS:
                    now = _dt.now(UTC)
                    if self.takeover_stale(
                        session,
                        attempt_id=running_id,
                        observed_heartbeat=running_heartbeat,
                        now=now,
                    ):
                        # Successfully abandoned; fall through to create
                        pass
                    else:
                        # CAS lost — retry with fresh state
                        continue
                else:
                    raise AttemptAlreadyRunningError(identity_id)

            # Recompute attempt_number each iteration
            attempt_number = self.get_max_attempt_number(session, identity_id) + 1
            if self._hooks:
                self._hooks.after_next_number_read(
                    identity_id=identity_id,
                    next_attempt_number=attempt_number,
                    retry_index=retry_idx,
                )

            record = OrchestrationRunAttemptRecord(
                id=str(uuid4()),
                identity_id=identity_id,
                attempt_number=attempt_number,
                status="RUNNING",
                heartbeat_at=heartbeat_at,
                database_backend=derived_database_backend,
                correlation_id=derived_correlation_id,
            )

            # Independent savepoint for the insert
            nested = session.begin_nested()
            try:
                session.add(record)
                if self._hooks:
                    self._hooks.before_attempt_flush(
                        identity_id=identity_id,
                        attempt_number=attempt_number,
                        retry_index=retry_idx,
                    )
                session.flush()
                nested.commit()
                return record.id
            except sa_exc.IntegrityError as exc:
                nested.rollback()
                pg_name: str | None = getattr(
                    getattr(exc.orig, "diag", None), "constraint_name", None
                )
                if self._hooks:
                    self._hooks.after_integrity_conflict(
                        constraint_name=pg_name,
                        identity_id=identity_id,
                        attempt_number=attempt_number,
                        retry_index=retry_idx,
                    )
                kind = _classify_attempt_insert_integrity_error(exc)
                if kind is AttemptInsertConflictKind.NON_TARGET:
                    raise
                # Target conflict — re-read state and retry
                refreshed_running = self.find_running_attempt(session, identity_id)
                max_num = self.get_max_attempt_number(session, identity_id)
                if self._hooks:
                    self._hooks.after_retry_state_refresh(
                        identity_id=identity_id,
                        running_attempt=refreshed_running,
                        max_attempt_number=max_num,
                        retry_index=retry_idx,
                    )
                continue

        raise AttemptTakeoverConflictError(
            identity_id=identity_id,
            attempt_id=stale_attempt_id,
            retry_count=self._MAX_ACQUIRE_RETRIES,
        )

    def find_running_attempt(
        self, session: Session, /, identity_id: str
    ) -> dict[str, object] | None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        row = session.execute(
            select(OrchestrationRunAttemptRecord).where(
                OrchestrationRunAttemptRecord.identity_id == identity_id,
                OrchestrationRunAttemptRecord.status == "RUNNING",
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {"id": row.id, "heartbeat_at": row.heartbeat_at, "status": row.status}

    def find_authoritative_completed(
        self, session: Session, /, identity_id: str
    ) -> dict[str, object] | None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
            OrchestrationRunAttemptRecord,
        )

        identity = session.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == identity_id)
        ).scalar_one_or_none()
        if identity is None or identity.authoritative_attempt_id is None:
            return None

        attempt = session.execute(
            select(OrchestrationRunAttemptRecord).where(
                OrchestrationRunAttemptRecord.id == identity.authoritative_attempt_id
            )
        ).scalar_one_or_none()
        if attempt is None:
            return None
        return {
            "id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "status": attempt.status,
        }

    def get_max_attempt_number(self, session: Session, /, identity_id: str) -> int:
        from sqlalchemy import func, select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        max_num = session.execute(
            select(func.max(OrchestrationRunAttemptRecord.attempt_number)).where(
                OrchestrationRunAttemptRecord.identity_id == identity_id
            )
        ).scalar()
        return max_num if max_num is not None else 0

    def update_status(
        self,
        session: Session,
        /,
        attempt_id: str,
        *,
        status: AttemptStatus,
        source_binding_id: str | None = None,
        failure_code: str | None = None,
        failure_details: dict[str, object] | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        from datetime import UTC, datetime

        from sqlalchemy import update

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        values: dict[str, object] = {
            "status": status.value,
            "source_binding_id": source_binding_id,
            "failure_code": failure_code,
            "failure_details": failure_details,
            "completed_at": completed_at or datetime.now(UTC),
        }
        session.execute(
            update(OrchestrationRunAttemptRecord)
            .where(OrchestrationRunAttemptRecord.id == attempt_id)
            .values(**{k: v for k, v in values.items() if v is not None or k == "status"})
        )

    def transition_running_to_terminal(
        self,
        session: Session,
        /,
        *,
        attempt_id: str,
        identity_id: str,
        target_status: AttemptStatus,
        failure_code: str,
        failure_details: dict[str, object],
        completed_at: datetime,
    ) -> TerminalTransitionResult:
        from sqlalchemy import select, update

        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
            TerminalTransitionResult,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            PersistenceInvariantError,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        if target_status not in (AttemptStatus.BLOCKED, AttemptStatus.FAILED):
            raise PersistenceInvariantError(
                f"terminal CAS only allows BLOCKED or FAILED, got {target_status.value!r}"
            )

        result = session.execute(
            update(OrchestrationRunAttemptRecord)
            .where(
                OrchestrationRunAttemptRecord.id == attempt_id,
                OrchestrationRunAttemptRecord.identity_id == identity_id,
                OrchestrationRunAttemptRecord.status == "RUNNING",
            )
            .values(
                status=target_status.value,
                failure_code=failure_code,
                failure_details=failure_details,
                completed_at=completed_at,
            )
        )
        if result.rowcount is not None and result.rowcount > 0:  # type: ignore[attr-defined]
            return TerminalTransitionResult(outcome=TerminalTransitionOutcome.TRANSITIONED)

        # CAS missed — classify the reason.
        row = session.execute(
            select(OrchestrationRunAttemptRecord).where(
                OrchestrationRunAttemptRecord.id == attempt_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return TerminalTransitionResult(outcome=TerminalTransitionOutcome.NOT_FOUND)

        if row.identity_id != identity_id:
            return TerminalTransitionResult(
                outcome=TerminalTransitionOutcome.STATE_CONFLICT,
                observed_status=AttemptStatus(row.status),
            )

        current = AttemptStatus(row.status)
        if current == AttemptStatus.COMPLETED:
            return TerminalTransitionResult(
                outcome=TerminalTransitionOutcome.ALREADY_COMPLETED,
                observed_status=current,
            )
        if current in (AttemptStatus.BLOCKED, AttemptStatus.FAILED):
            return TerminalTransitionResult(
                outcome=TerminalTransitionOutcome.ALREADY_TERMINAL,
                observed_status=current,
            )
        return TerminalTransitionResult(
            outcome=TerminalTransitionOutcome.STATE_CONFLICT,
            observed_status=current,
        )

    def get_status(self, session: Session, /, attempt_id: str) -> str | None:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        row = session.execute(
            select(OrchestrationRunAttemptRecord.status).where(
                OrchestrationRunAttemptRecord.id == attempt_id
            )
        ).scalar_one_or_none()
        return row

    def takeover_stale(
        self,
        session: Session,
        /,
        *,
        attempt_id: str,
        observed_heartbeat: datetime,
        now: datetime,
    ) -> bool:
        from sqlalchemy import update

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        result = session.execute(
            update(OrchestrationRunAttemptRecord)
            .where(
                OrchestrationRunAttemptRecord.id == attempt_id,
                OrchestrationRunAttemptRecord.heartbeat_at == observed_heartbeat,
                OrchestrationRunAttemptRecord.status == "RUNNING",
            )
            .values(status="ABANDONED", completed_at=now)
        )
        return result.rowcount is not None and result.rowcount > 0  # type: ignore[attr-defined]

    def complete_attempt_cas(
        self,
        session: Session,
        /,
        *,
        attempt_id: str,
        identity_id: str,
        source_binding_id: str,
        completed_at: datetime,
    ) -> bool:
        from sqlalchemy import update

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        result = session.execute(
            update(OrchestrationRunAttemptRecord)
            .where(
                OrchestrationRunAttemptRecord.id == attempt_id,
                OrchestrationRunAttemptRecord.identity_id == identity_id,
                OrchestrationRunAttemptRecord.status == "RUNNING",
            )
            .values(
                status="COMPLETED",
                source_binding_id=source_binding_id,
                completed_at=completed_at,
            )
        )
        return bool(result.rowcount == 1)  # type: ignore[attr-defined]


# ── Source Binding ──────────────────────────────────────────────────────────


class SqlAlchemySourceBindingRepository(SourceBindingRepository):
    """Session-bound repository for ``SourceBindingRecord``."""

    def add(
        self,
        session: Session,
        /,
        *,
        id: str | None = None,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_run_attempt_id: str,
        orchestration_fingerprint: str,
        zone_calculation_id: str,
        cooling_load_calculation_id: str,
        equipment_calculation_id: str,
        power_calculation_id: str,
        investment_calculation_id: str,
        per_calculation_result_hashes: dict[str, str],
        combined_source_hash: str,
        schema_version: str,
    ) -> str:
        from uuid import uuid4

        from cold_storage.modules.orchestration.infrastructure.orm import (
            SourceBindingRecord,
        )

        record = SourceBindingRecord(
            id=id or str(uuid4()),
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_run_attempt_id=orchestration_run_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            zone_calculation_id=zone_calculation_id,
            cooling_load_calculation_id=cooling_load_calculation_id,
            equipment_calculation_id=equipment_calculation_id,
            power_calculation_id=power_calculation_id,
            investment_calculation_id=investment_calculation_id,
            per_calculation_result_hashes=per_calculation_result_hashes,
            combined_source_hash=combined_source_hash,
            schema_version=schema_version,
        )
        session.add(record)
        session.flush()
        return record.id


# ── Audit Outbox ────────────────────────────────────────────────────────────


class SqlAlchemyAuditOutboxRepository(AuditOutboxRepository):
    """Session-bound repository for ``AuditOutboxRecord``.

    Inherits ``add()`` from ``AuditOutboxRepository`` (application port).
    Dispatcher operations are free functions in the infrastructure layer.
    """

    def add(
        self,
        session: Session,
        /,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        transition_id: str,
        actor: str,
        correlation_id: str,
        occurred_at: datetime,
        event_schema_version: str = "1.0",
        request_id: str | None = None,
        identity_id: str | None = None,
        attempt_id: str | None = None,
        calculation_run_id: str | None = None,
        source_binding_id: str | None = None,
        available_at: datetime | None = None,
    ) -> str:
        """Insert a PENDING outbox event and return its ID.

        Fail-closed validation: ``actor`` and ``correlation_id`` must be
        non-empty after stripping.  ``occurred_at`` must be supplied.
        Event identity is deterministic (content-addressable).  Idempotent
        on (event_identity, envelope_hash).  On idempotent match, ALL
        immutable envelope fields are compared and a mismatch raises
        :class:`OutboxIdempotencyMismatchError`.
        """
        from datetime import UTC
        from uuid import uuid4

        from cold_storage.modules.orchestration.application.outbox_errors import (
            OutboxIdempotencyMismatchError,
        )
        from cold_storage.modules.orchestration.application.outbox_identity import (
            build_event_identity,
            compute_envelope_hash,
            compute_payload_hash,
        )
        from cold_storage.modules.orchestration.application.ports import (
            OutboxEnvelopeValidationError,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            AuditOutboxRecord,
        )

        # ── Fail-closed envelope validation (P0-12) ────────────────
        if not isinstance(actor, str) or not actor.strip():
            raise OutboxEnvelopeValidationError(
                field="actor",
                message=(
                    "AuditOutboxRepository.add requires a non-empty actor; "
                    "callers must pass the durable request actor explicitly."
                ),
            )
        if not isinstance(correlation_id, str) or not correlation_id.strip():
            raise OutboxEnvelopeValidationError(
                field="correlation_id",
                message=(
                    "AuditOutboxRepository.add requires a non-empty "
                    "correlation_id; callers must pass the durable request "
                    "correlation_id or a dispatcher trace id explicitly."
                ),
            )
        if occurred_at is None:
            raise OutboxEnvelopeValidationError(
                field="occurred_at",
                message=(
                    "AuditOutboxRepository.add requires occurred_at; "
                    "callers must pass the authoritative transition timestamp."
                ),
            )

        now = datetime.now(UTC)
        effective_occurred_at = occurred_at
        event_identity = build_event_identity(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            transition_id=transition_id,
            schema_version=event_schema_version,
        )
        payload_hash = compute_payload_hash(payload)
        envelope_hash = compute_envelope_hash(
            event_schema_version=event_schema_version,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor=actor,
            correlation_id=correlation_id,
            occurred_at=effective_occurred_at,
            request_id=request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
            calculation_run_id=calculation_run_id,
            source_binding_id=source_binding_id,
            payload=payload,
            event_identity=event_identity,
        )

        from sqlalchemy import select

        # Use SAVEPOINT for concurrent-safe idempotent insert.
        # On IntegrityError, roll back the savepoint, read the existing
        # row, and compare the full envelope.
        nested = session.begin_nested()
        try:
            record = AuditOutboxRecord(
                id=str(uuid4()),
                event_identity=event_identity,
                event_type=event_type,
                event_schema_version=event_schema_version,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                actor=actor,
                correlation_id=correlation_id,
                occurred_at=effective_occurred_at,
                payload=payload,
                payload_hash=payload_hash,
                envelope_hash=envelope_hash,
                request_id=request_id,
                identity_id=identity_id,
                attempt_id=attempt_id,
                calculation_run_id=calculation_run_id,
                source_binding_id=source_binding_id,
                status="PENDING",
                next_retry_at=available_at or now,
            )
            session.add(record)
            session.flush()
            nested.commit()
            return record.id
        except sa_exc.IntegrityError as exc:
            nested.rollback()
            if not _is_target_unique_violation(
                exc,
                postgres_constraint_names=frozenset({"uq_outbox_event_identity"}),
                sqlite_table="orchestration_audit_outbox",
                sqlite_column_sets=frozenset({("event_identity",)}),
            ):
                raise
            # Read existing row and compare full envelope
            existing = session.execute(
                select(AuditOutboxRecord).where(AuditOutboxRecord.event_identity == event_identity)
            ).scalar_one_or_none()
            if existing is None:
                raise

            # P0-8: Compare ALL immutable envelope fields
            mismatches = _compare_outbox_envelopes(
                existing=existing,
                new_event_type=event_type,
                new_event_schema_version=event_schema_version,
                new_aggregate_type=aggregate_type,
                new_aggregate_id=aggregate_id,
                new_actor=actor,
                new_correlation_id=correlation_id,
                new_occurred_at=effective_occurred_at,
                new_payload=payload,
                new_payload_hash=payload_hash,
                new_envelope_hash=envelope_hash,
                new_request_id=request_id,
                new_identity_id=identity_id,
                new_attempt_id=attempt_id,
                new_calculation_run_id=calculation_run_id,
                new_source_binding_id=source_binding_id,
            )
            if mismatches:
                raise OutboxIdempotencyMismatchError(
                    event_identity,
                    mismatches,
                    existing_payload_hash=existing.payload_hash,
                    new_payload_hash=payload_hash,
                ) from exc
            return existing.id


def _normalize_occurred_at_for_compare(val: object) -> object:
    """Normalize occurred_at to naive UTC ISO string for cross-dialect comparison.

    SQLite stores naive datetimes; PG stores aware. This ensures both
    compare identically by normalizing to naive UTC ISO string.
    """
    if isinstance(val, datetime):
        from cold_storage.modules.orchestration.application.outbox_identity import ensure_utc_aware

        return ensure_utc_aware(val).replace(tzinfo=None).isoformat()
    return val


def _compare_outbox_envelopes(
    *,
    existing: Any,
    new_event_type: str,
    new_event_schema_version: str,
    new_aggregate_type: str,
    new_aggregate_id: str,
    new_actor: str,
    new_correlation_id: str,
    new_occurred_at: datetime,
    new_payload: dict[str, object],
    new_payload_hash: str,
    new_envelope_hash: str,
    new_request_id: str | None,
    new_identity_id: str | None,
    new_attempt_id: str | None,
    new_calculation_run_id: str | None,
    new_source_binding_id: str | None,
) -> list[str]:
    """Compare all immutable envelope fields between an existing DB row and new values.

    Returns a list of mismatched field names, empty if they match.
    """
    mismatches: list[str] = []
    field_pairs: list[tuple[str, object, object]] = [
        ("event_type", existing.event_type, new_event_type),
        ("event_schema_version", existing.event_schema_version, new_event_schema_version),
        ("aggregate_type", existing.aggregate_type, new_aggregate_type),
        ("aggregate_id", existing.aggregate_id, new_aggregate_id),
        ("actor", existing.actor, new_actor),
        ("correlation_id", existing.correlation_id, new_correlation_id),
        (
            "occurred_at",
            _normalize_occurred_at_for_compare(existing.occurred_at),
            _normalize_occurred_at_for_compare(new_occurred_at),
        ),
        ("payload", existing.payload, new_payload),
        ("payload_hash", existing.payload_hash, new_payload_hash),
        ("envelope_hash", getattr(existing, "envelope_hash", None), new_envelope_hash),
        ("request_id", existing.request_id, new_request_id),
        ("identity_id", existing.identity_id, new_identity_id),
        ("attempt_id", existing.attempt_id, new_attempt_id),
        ("calculation_run_id", existing.calculation_run_id, new_calculation_run_id),
        ("source_binding_id", existing.source_binding_id, new_source_binding_id),
    ]
    for name, old_val, new_val in field_pairs:
        if old_val != new_val:
            mismatches.append(name)
    return mismatches


# ── Calculation Run ─────────────────────────────────────────────────────────


class SqlAlchemyCalculationRunRepository(CalculationRunRepository):
    """Session-bound repository for ``CalculationRunRecord``."""

    def add(
        self,
        session: Session,
        /,
        *,
        id: str | None = None,
        project_id: str,
        project_version_id: str,
        calculator_name: str,
        calculator_version: str,
        calculation_type: str,
        input_snapshot: dict[str, object],
        result_snapshot: dict[str, object],
        requires_review: bool,
        orchestration_identity_id: str,
        orchestration_run_attempt_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        input_hash: str,
        result_hash: str,
        provenance: dict[str, object],
        schema_version: str,
        orchestration_fingerprint: str,
        formulas: list[dict[str, object]],
        coefficients: list[dict[str, object]],
        assumptions: list[str],
        warnings: list[dict[str, object]],
        source_references: list[dict[str, object]],
    ) -> str:
        from uuid import uuid4

        from cold_storage.modules.projects.infrastructure.orm import (
            CalculationRunRecord,
        )

        record = CalculationRunRecord(
            id=id or str(uuid4()),
            project_id=project_id,
            project_version_id=project_version_id,
            calculator_name=calculator_name,
            calculator_version=calculator_version,
            calculation_type=calculation_type,
            input_snapshot=input_snapshot,
            result_snapshot=result_snapshot,
            requires_review=requires_review,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_run_attempt_id=orchestration_run_attempt_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            input_hash=input_hash,
            result_hash=result_hash,
            provenance=provenance,
            schema_version=schema_version,
            orchestration_fingerprint=orchestration_fingerprint,
            formulas=formulas,
            coefficients=coefficients,
            assumptions=assumptions,
            warnings=warnings,
            source_references=source_references,
        )
        session.add(record)
        session.flush()
        return record.id


# ── Verification Read Port ──────────────────────────────────────────────────

# calculator_name → stage_name reverse mapping
_CALCULATOR_NAME_TO_STAGE: dict[str, str] = {
    "cold_room_zone_plan": "zone",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "installed_power": "power",
    "investment_estimate": "investment",
}

_EXPECTED_STAGE_COUNT = 5


class SqlAlchemyVerificationReadPort:
    """SQLAlchemy implementation of the ``VerificationReadPort`` protocol.

    Loads the full verification state (request + identity + attempt + five
    CalculationRun snapshots) from the database in a fail-closed manner:
    any missing entity, wrong relationship, or stage count mismatch raises
    a domain error.
    """

    def load_verification_state(
        self,
        session: Any,
        /,
        *,
        request_id: str,
        identity_id: str,
        attempt_id: str,
    ) -> VerificationState:
        from sqlalchemy import select

        from cold_storage.modules.orchestration.application.transaction_b import (
            CalculationRunSnapshot,
            VerificationState,
        )
        from cold_storage.modules.orchestration.domain.dag import (
            ORCHESTRATION_STAGE_ORDER,
        )
        from cold_storage.modules.orchestration.domain.errors import (
            PersistenceInvariantError,
        )
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
            OrchestrationRequestRecord,
            OrchestrationRunAttemptRecord,
        )
        from cold_storage.modules.projects.infrastructure.orm import (
            CalculationRunRecord,
        )

        # ── 1. Load request ──────────────────────────────────────────────
        request = session.execute(
            select(OrchestrationRequestRecord).where(OrchestrationRequestRecord.id == request_id)
        ).scalar_one_or_none()
        if request is None:
            raise PersistenceInvariantError(
                f"Request {request_id!r} not found",
                details={"request_id": request_id},
            )

        # ── 2. Load identity ─────────────────────────────────────────────
        identity = session.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == identity_id)
        ).scalar_one_or_none()
        if identity is None:
            raise PersistenceInvariantError(
                f"Identity {identity_id!r} not found",
                details={"identity_id": identity_id},
            )

        # ── 3. Validate identity belongs to request ──────────────────────
        if request.resolved_identity_id != identity_id:
            raise PersistenceInvariantError(
                f"Identity {identity_id!r} does not match request "
                f"{request_id!r} resolved_identity_id "
                f"{request.resolved_identity_id!r}",
                details={
                    "request_id": request_id,
                    "identity_id": identity_id,
                    "resolved_identity_id": request.resolved_identity_id,
                },
            )

        # ── 4. Load attempt ──────────────────────────────────────────────
        attempt = session.execute(
            select(OrchestrationRunAttemptRecord).where(
                OrchestrationRunAttemptRecord.id == attempt_id
            )
        ).scalar_one_or_none()
        if attempt is None:
            raise PersistenceInvariantError(
                f"Attempt {attempt_id!r} not found",
                details={"attempt_id": attempt_id},
            )

        # ── 5. Validate attempt belongs to identity ──────────────────────
        if attempt.identity_id != identity_id:
            raise PersistenceInvariantError(
                f"Attempt {attempt_id!r} belongs to identity "
                f"{attempt.identity_id!r}, not {identity_id!r}",
                details={
                    "attempt_id": attempt_id,
                    "expected_identity_id": identity_id,
                    "actual_identity_id": attempt.identity_id,
                },
            )

        # ── 6. Load calculation runs for the attempt ─────────────────────
        calc_runs = list(
            session.execute(
                select(CalculationRunRecord).where(
                    CalculationRunRecord.orchestration_run_attempt_id == attempt_id
                )
            )
            .scalars()
            .all()
        )

        # ── 7. Validate exactly 5 runs and map by stage_name ────────────
        if len(calc_runs) != _EXPECTED_STAGE_COUNT:
            raise PersistenceInvariantError(
                f"Expected {_EXPECTED_STAGE_COUNT} calculation runs for attempt "
                f"{attempt_id!r}, found {len(calc_runs)}",
                details={
                    "attempt_id": attempt_id,
                    "expected_count": _EXPECTED_STAGE_COUNT,
                    "actual_count": len(calc_runs),
                },
            )

        stage_runs: dict[str, CalculationRunSnapshot] = {}
        seen_stages: set[str] = set()
        expected_stages = set(ORCHESTRATION_STAGE_ORDER)

        for run in calc_runs:
            # Map calculator_name → stage_name
            stage_name = _CALCULATOR_NAME_TO_STAGE.get(run.calculator_name)
            if stage_name is None:
                raise PersistenceInvariantError(
                    f"Unknown calculator_name {run.calculator_name!r} in "
                    f"calculation run {run.id!r}",
                    details={
                        "calculator_name": run.calculator_name,
                        "calculation_run_id": run.id,
                    },
                )

            # Duplicate stage detection
            if stage_name in seen_stages:
                raise PersistenceInvariantError(
                    f"Duplicate stage {stage_name!r} in calculation runs for "
                    f"attempt {attempt_id!r}",
                    details={
                        "stage_name": stage_name,
                        "attempt_id": attempt_id,
                    },
                )
            seen_stages.add(stage_name)

            # Extra stage detection (not in the expected 5)
            if stage_name not in expected_stages:
                raise PersistenceInvariantError(
                    f"Unexpected stage {stage_name!r} in calculation runs for "
                    f"attempt {attempt_id!r}",
                    details={
                        "stage_name": stage_name,
                        "attempt_id": attempt_id,
                    },
                )

            # Extract upstream_calculation_ids from provenance
            provenance = run.provenance or {}
            upstream_ids: dict[str, str] = {}
            raw_upstream = provenance.get("upstream_calculation_ids")
            if isinstance(raw_upstream, dict):
                upstream_ids = dict(raw_upstream)

            stage_runs[stage_name] = CalculationRunSnapshot(
                id=run.id,
                calculator_name=run.calculator_name,
                calculator_version=run.calculator_version,
                calculation_type=run.calculation_type or "",
                result_snapshot=run.result_snapshot,
                result_hash=run.result_hash,
                orchestration_identity_id=run.orchestration_identity_id,
                orchestration_run_attempt_id=run.orchestration_run_attempt_id,
                execution_snapshot_id=run.execution_snapshot_id,
                coefficient_context_id=run.coefficient_context_id,
                orchestration_fingerprint=run.orchestration_fingerprint,
                requires_review=run.requires_review,
                schema_version=run.schema_version,
                project_id=run.project_id,
                project_version_id=run.project_version_id,
                formulas=list(run.formulas or []),
                coefficients=list(run.coefficients or []),
                assumptions=list(run.assumptions or []),
                warnings=list(run.warnings or []),
                source_references=list(run.source_references or []),
                upstream_calculation_ids=upstream_ids,
                input_hash=run.input_hash or "",
            )

        # Missing stages detection
        missing_stages = expected_stages - seen_stages
        if missing_stages:
            raise PersistenceInvariantError(
                f"Missing stages {sorted(missing_stages)!r} in calculation runs "
                f"for attempt {attempt_id!r}",
                details={
                    "missing_stages": sorted(missing_stages),
                    "attempt_id": attempt_id,
                },
            )

        # ── 8. Return VerificationState ──────────────────────────────────
        return VerificationState(
            request_status=request.status,
            resolved_identity_id=request.resolved_identity_id,
            resolved_attempt_id=request.resolved_attempt_id,
            identity_fingerprint=identity.fingerprint,
            identity_execution_snapshot_id=identity.execution_snapshot_id,
            identity_coefficient_context_id=identity.coefficient_context_id,
            identity_authoritative_attempt_id=identity.authoritative_attempt_id,
            attempt_identity_id=attempt.identity_id,
            attempt_status=attempt.status,
            attempt_source_binding_id=attempt.source_binding_id,
            calculation_runs=stage_runs,
        )
