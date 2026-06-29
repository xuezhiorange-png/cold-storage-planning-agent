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

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session

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


class OrchestrationRequestRepository(ABC):
    """Read/write ``OrchestrationRequestRecord`` rows."""

    @abstractmethod
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
        """Insert a new PENDING request and return its ID."""
        ...

    @abstractmethod
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
        """Update request status and optional resolution/failure metadata.

        Raises ``PersistenceInvariantError`` when 0 rows are affected.
        """
        ...


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


# ── Execution Snapshot ──────────────────────────────────────────────────────


class ExecutionSnapshotRepository(ABC):
    """Read/write ``ProjectVersionExecutionSnapshotRecord`` rows."""

    @abstractmethod
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
        """Return existing record ID or create a new one (concurrent-safe)."""
        ...


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


class CoefficientContextRepository(ABC):
    """Read/write ``CoefficientContextRecord`` rows."""

    @abstractmethod
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
        """Return existing record ID or create a new one (concurrent-safe)."""
        ...


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


class OrchestrationIdentityRepository(ABC):
    """Read/write ``OrchestrationIdentityRecord`` rows."""

    @abstractmethod
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
        """Return existing identity ID or create a new one (concurrent-safe)."""
        ...

    @abstractmethod
    def set_authoritative_attempt(
        self,
        session: Session,
        /,
        identity_id: str,
        attempt_id: str,
    ) -> None:
        """Set the authoritative completed attempt for an identity."""
        ...


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
    ) -> None:
        from sqlalchemy import update

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationIdentityRecord,
        )

        session.execute(
            update(OrchestrationIdentityRecord)
            .where(OrchestrationIdentityRecord.id == identity_id)
            .values(authoritative_attempt_id=attempt_id)
        )


# ── Orchestration Attempt ───────────────────────────────────────────────────


class OrchestrationAttemptRepository(ABC):
    """Read/write ``OrchestrationRunAttemptRecord`` rows."""

    @abstractmethod
    def acquire(
        self,
        session: Session,
        /,
        *,
        identity_id: str,
        heartbeat_at: datetime,
    ) -> str:
        """Acquire a new RUNNING attempt for the identity.

        - Each retry re-reads RUNNING attempt and max(attempt_number)+1.
        - If a live RUNNING attempt exists, raises ``AttemptAlreadyRunningError``.
        - If an expired RUNNING attempt exists, CAS-takes over.
        - CAS conflict → bounded retry with fresh state.
        - Insert uses independent savepoint; only target unique constraints
          (uq_attempt_identity_number, uq_attempt_one_running) trigger retry.
        """
        ...

    @abstractmethod
    def find_running_attempt(
        self, session: Session, /, identity_id: str
    ) -> dict[str, object] | None:
        """Return the current RUNNING attempt for an identity (if any)."""
        ...

    @abstractmethod
    def find_authoritative_completed(
        self, session: Session, /, identity_id: str
    ) -> dict[str, object] | None:
        """Return the authoritative COMPLETED attempt (if any)."""
        ...

    @abstractmethod
    def get_max_attempt_number(self, session: Session, /, identity_id: str) -> int:
        """Return the max attempt_number for the identity (0 if none)."""
        ...

    @abstractmethod
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
        """Transition attempt to terminal status."""
        ...

    @abstractmethod
    def takeover_stale(
        self,
        session: Session,
        /,
        *,
        attempt_id: str,
        observed_heartbeat: datetime,
        now: datetime,
    ) -> bool:
        """CAS-transition an expired RUNNING attempt to ABANDONED."""
        ...


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


# ── Source Binding ──────────────────────────────────────────────────────────


class SourceBindingRepository(ABC):
    """Read/write ``SourceBindingRecord`` rows."""

    @abstractmethod
    def add(
        self,
        session: Session,
        /,
        *,
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
        """Insert a new SourceBinding and return its ID."""
        ...


# ── Audit Outbox ────────────────────────────────────────────────────────────


class AuditOutboxRepository(ABC):
    """Read/write ``AuditOutboxRecord`` rows."""

    @abstractmethod
    def add(
        self,
        session: Session,
        /,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        request_id: str | None = None,
        identity_id: str | None = None,
        attempt_id: str | None = None,
        calculation_run_id: str | None = None,
        source_binding_id: str | None = None,
        available_at: datetime | None = None,
    ) -> str:
        """Insert a PENDING outbox event and return its ID."""
        ...

    @abstractmethod
    def claim(self, session: Session, /, *, worker_id: str, limit: int = 10) -> Sequence[str]:
        """Atomically claim up to ``limit`` eligible outbox events."""
        ...

    @abstractmethod
    def mark_published(self, session: Session, /, event_id: str) -> None:
        """Mark a claimed event as PUBLISHED."""
        ...

    @abstractmethod
    def mark_failed(
        self,
        session: Session,
        /,
        event_id: str,
        *,
        error_code: str,
        next_retry_at: datetime,
    ) -> None:
        """Return an event to PENDING with retry metadata."""
        ...


class SqlAlchemyAuditOutboxRepository(AuditOutboxRepository):
    """Session-bound repository for ``AuditOutboxRecord``."""

    def add(
        self,
        session: Session,
        /,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        request_id: str | None = None,
        identity_id: str | None = None,
        attempt_id: str | None = None,
        calculation_run_id: str | None = None,
        source_binding_id: str | None = None,
        available_at: datetime | None = None,
    ) -> str:
        from uuid import uuid4

        from cold_storage.modules.orchestration.infrastructure.orm import (
            AuditOutboxRecord,
        )

        record = AuditOutboxRecord(
            id=str(uuid4()),
            event_identity=str(uuid4()),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            request_id=request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
            calculation_run_id=calculation_run_id,
            source_binding_id=source_binding_id,
            payload=payload,
            status="PENDING",
        )
        session.add(record)
        session.flush()
        return record.id

    def claim(self, session: Session, /, *, worker_id: str, limit: int = 10) -> Sequence[str]:
        raise NotImplementedError("Outbox claim not implemented in this phase")

    def mark_published(self, session: Session, /, event_id: str) -> None:
        raise NotImplementedError("Outbox dispatcher not implemented in this phase")

    def mark_failed(
        self,
        session: Session,
        /,
        event_id: str,
        *,
        error_code: str,
        next_retry_at: datetime,
    ) -> None:
        raise NotImplementedError("Outbox retry not implemented in this phase")


# ── Calculation Run ─────────────────────────────────────────────────────────


class CalculationRunRepository(ABC):
    """Read/write ``CalculationRunRecord`` rows (extended for orchestration fields)."""

    @abstractmethod
    def add(
        self,
        session: Session,
        /,
        *,
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
    ) -> str:
        """Insert a new orchestrated CalculationRunRecord and return its ID."""
        ...
