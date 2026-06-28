"""Orchestration repository protocols — session-bound, never commits.

Repository methods accept a SQLAlchemy Session and operate within the
caller's transaction boundary.  They MUST NOT call ``session.commit()``,
``session.rollback()``, ``session.close()``, or create sessions.

Concrete SQLAlchemy implementations are provided for all protocols
needed by Transaction A (request + snapshot + context + identity +
attempt).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    RequestStatus,
)


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
        """Update request status and optional resolution/failure metadata."""
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
        session.execute(stmt)


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
        """Return existing record ID or create a new one."""
        ...


class SqlAlchemyExecutionSnapshotRepository(ExecutionSnapshotRepository):
    """Session-bound repository for ``ProjectVersionExecutionSnapshotRecord``."""

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

        # Try to find existing
        existing = session.execute(
            select(ProjectVersionExecutionSnapshotRecord.id).where(
                ProjectVersionExecutionSnapshotRecord.project_version_id == project_version_id,
                ProjectVersionExecutionSnapshotRecord.input_snapshot_hash == input_snapshot_hash,
                ProjectVersionExecutionSnapshotRecord.schema_version == schema_version,
            )
        ).scalar()
        if existing:
            return existing

        # Create new
        record = ProjectVersionExecutionSnapshotRecord(
            id=str(uuid4()),
            project_id=project_id,
            project_version_id=project_version_id,
            version_number=version_number,
            input_snapshot=input_snapshot,
            input_snapshot_hash=input_snapshot_hash,
            schema_version=schema_version,
            captured_status="approved",
        )
        session.add(record)
        session.flush()
        return record.id


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
        """Return existing record ID or create a new one."""
        ...


class SqlAlchemyCoefficientContextRepository(CoefficientContextRepository):
    """Session-bound repository for ``CoefficientContextRecord``."""

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
            return existing

        record = CoefficientContextRecord(
            id=str(uuid4()),
            project_id=project_id,
            project_version_id=project_version_id,
            content=content,
            content_hash=content_hash,
            schema_version=schema_version,
        )
        session.add(record)
        session.flush()
        return record.id


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
        """Return existing identity ID or create a new one."""
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
            return existing

        record = OrchestrationIdentityRecord(
            id=str(uuid4()),
            fingerprint=fingerprint,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            definition_version=definition_version,
            calculator_version_vector=calculator_version_vector,
            status="ACTIVE",
        )
        session.add(record)
        session.flush()
        return record.id

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
        attempt_number: int,
        heartbeat_at: datetime,
    ) -> str:
        """Create a new RUNNING attempt and return its ID."""
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

    def acquire(
        self,
        session: Session,
        /,
        *,
        identity_id: str,
        attempt_number: int,
        heartbeat_at: datetime,
    ) -> str:
        from uuid import uuid4

        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        record = OrchestrationRunAttemptRecord(
            id=str(uuid4()),
            identity_id=identity_id,
            attempt_number=attempt_number,
            status="RUNNING",
            heartbeat_at=heartbeat_at,
        )
        session.add(record)
        session.flush()
        return record.id

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
        # rowcount on CursorResult returns the number of matched rows
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
    """Session-bound repository for ``AuditOutboxRecord``.

    Implements request/attempt-level append.  claim / retry / dispatcher
    are not implemented in this phase.
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
