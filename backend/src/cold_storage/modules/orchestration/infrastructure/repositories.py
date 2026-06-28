"""Orchestration repository protocols — session-bound, never commits.

Repository methods accept a SQLAlchemy Session and operate within the
caller's transaction boundary.  They MUST NOT call ``session.commit()``.

Full implementation in later phases.
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


class OrchestrationRequestRepository(ABC):
    """Read/write ``OrchestrationRequestRecord`` rows."""

    @abstractmethod
    def add(
        self,
        session: Session,
        /,
        *,
        project_id: str,
        project_version_id: str,
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
        resolved_identity_id: str | None = None,
        resolved_attempt_id: str | None = None,
    ) -> None:
        """Update request status and optional resolution/failure metadata."""
        ...


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
        """CAS-transition an expired RUNNING attempt to ABANDONED. Returns True on success."""
        ...


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
