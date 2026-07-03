"""Orchestration preflight ports.

Defines the application-level contracts for snapshot-schema and
coefficient-resolution validation.  Concrete implementations belong
in later sub-tasks (B/C); this phase uses test doubles to verify
error mapping.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from cold_storage.modules.orchestration.application.coefficient_contracts import (
    FrozenCoefficientResolutionCriteria,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    RequestStatus,
)

# ── Terminal transition outcome ─────────────────────────────────────────────


class TerminalTransitionOutcome(StrEnum):
    """Result classification for guarded terminal CAS transitions."""

    TRANSITIONED = "TRANSITIONED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"
    NOT_FOUND = "NOT_FOUND"
    STATE_CONFLICT = "STATE_CONFLICT"


@dataclass(frozen=True, slots=True)
class TerminalTransitionResult:
    """Structured result from a guarded terminal CAS transition."""

    outcome: TerminalTransitionOutcome
    observed_status: AttemptStatus | None = None


# ── Preflight ports ─────────────────────────────────────────────────────────


class ExecutionSnapshotPreflightPort(Protocol):
    """Validate that the approved ProjectVersion can be captured as a valid
    execution snapshot candidate."""

    def validate_candidate(
        self,
        *,
        project_id: str,
        project_version_id: str,
        version_status: str,
    ) -> None:
        """Raise ``ExecutionSnapshotSchemaError`` when the snapshot schema
        is invalid or unsupported."""
        ...


@dataclass(frozen=True, slots=True)
class ResolvedCoefficientContextCandidate:
    """Resolved coefficient context returned by the resolution port.

    All fields are derived from the production coefficient catalog,
    never from caller self-attestation.
    """

    project_id: str
    project_version_id: str
    schema_version: str
    content: Mapping[str, object]
    content_hash: str
    approved_revision_ids: tuple[str, ...]


class CoefficientResolutionPreflightPort(Protocol):
    """Resolve an approved coefficient context for the given project/version.

    Returns a typed ``ResolvedCoefficientContextCandidate`` with verified
    approved revisions.  The caller must not forge ``source_type=approved``
    in the payload — that field comes from the catalog.

    ``criteria`` is derived from the frozen ProjectVersion — the resolver
    MUST NOT accept caller-provided product_type / zone_type / process_type /
    required_codes as authoritative.

    The resolver may receive the current Transaction A session (or None
    for test doubles).  It MUST NOT create sessions, commit, or rollback.
    """

    def resolve(
        self,
        *,
        criteria: FrozenCoefficientResolutionCriteria,
        session: object | None = None,
    ) -> ResolvedCoefficientContextCandidate:
        """Return a verified coefficient candidate.

        Raises ``CoefficientResolutionError``, ``CoefficientNotApprovedError``,
        or ``AmbiguousCoefficientError`` as appropriate.
        """
        ...


# ── Repository ABCs (application-layer contracts) ───────────────────────────
#
# Repository methods accept an opaque session (``Any``) and operate within the
# caller's transaction boundary.  They MUST NOT call ``session.commit()``,
# ``session.rollback()``, ``session.close()``, or create sessions.


class OrchestrationRequestRepository(ABC):
    """Read/write ``OrchestrationRequestRecord`` rows."""

    @abstractmethod
    def add(
        self,
        session: Any,
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
        session: Any,
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

    @abstractmethod
    def get_status(self, session: Any, /, request_id: str) -> str | None:
        """Return the current status string for a request, or None if not found."""
        ...


class ExecutionSnapshotRepository(ABC):
    """Read/write ``ProjectVersionExecutionSnapshotRecord`` rows."""

    @abstractmethod
    def get_or_create(
        self,
        session: Any,
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


class CoefficientContextRepository(ABC):
    """Read/write ``CoefficientContextRecord`` rows."""

    @abstractmethod
    def get_or_create(
        self,
        session: Any,
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


class OrchestrationIdentityRepository(ABC):
    """Read/write ``OrchestrationIdentityRecord`` rows."""

    @abstractmethod
    def get_or_create(
        self,
        session: Any,
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
        session: Any,
        /,
        identity_id: str,
        attempt_id: str,
    ) -> bool:
        """Set the authoritative completed attempt for an identity (CAS).

        Returns True if exactly one row was updated, False otherwise.
        The update is guarded by:
        - identity.status = 'ACTIVE'
        - attempt belongs to the identity
        - attempt.status = 'COMPLETED'
        """
        ...

    @abstractmethod
    def get_calculator_version_vector(
        self,
        session: Any,
        /,
        identity_id: str,
    ) -> dict[str, str]:
        """Return the calculator version vector for an identity."""
        ...


class OrchestrationAttemptRepository(ABC):
    """Read/write ``OrchestrationRunAttemptRecord`` rows."""

    @abstractmethod
    def acquire(
        self,
        session: Any,
        /,
        *,
        identity_id: str,
        heartbeat_at: datetime,
    ) -> str:
        """Acquire a new RUNNING attempt for the identity."""
        ...

    @abstractmethod
    def find_running_attempt(self, session: Any, /, identity_id: str) -> dict[str, object] | None:
        """Return the current RUNNING attempt for an identity (if any)."""
        ...

    @abstractmethod
    def find_authoritative_completed(
        self, session: Any, /, identity_id: str
    ) -> dict[str, object] | None:
        """Return the authoritative COMPLETED attempt (if any)."""
        ...

    @abstractmethod
    def get_max_attempt_number(self, session: Any, /, identity_id: str) -> int:
        """Return the max attempt_number for the identity (0 if none)."""
        ...

    @abstractmethod
    def update_status(
        self,
        session: Any,
        /,
        attempt_id: str,
        *,
        status: AttemptStatus,
        source_binding_id: str | None = None,
        failure_code: str | None = None,
        failure_details: dict[str, object] | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Transition attempt to terminal status.

        .. deprecated::
            Use :meth:`transition_running_to_terminal` for guarded CAS
            transitions.  This method is retained for success-path
            completion (COMPLETED) and legacy callers.
        """
        ...

    @abstractmethod
    def transition_running_to_terminal(
        self,
        session: Any,
        /,
        *,
        attempt_id: str,
        identity_id: str,
        target_status: AttemptStatus,
        failure_code: str,
        failure_details: dict[str, object],
        completed_at: datetime,
    ) -> TerminalTransitionResult:
        """Guarded CAS: transition a RUNNING attempt to BLOCKED or FAILED.

        Uses ``WHERE id = :attempt_id AND identity_id = :identity_id
        AND status = 'RUNNING'``.  When rowcount == 0, reads the
        current attempt to classify the outcome.
        """
        ...

    @abstractmethod
    def get_status(self, session: Any, /, attempt_id: str) -> str | None:
        """Return the current status string for an attempt, or None if not found."""
        ...

    @abstractmethod
    def takeover_stale(
        self,
        session: Any,
        /,
        *,
        attempt_id: str,
        observed_heartbeat: datetime,
        now: datetime,
    ) -> bool:
        """CAS-transition an expired RUNNING attempt to ABANDONED."""
        ...

    @abstractmethod
    def complete_attempt_cas(
        self,
        session: Any,
        /,
        *,
        attempt_id: str,
        identity_id: str,
        source_binding_id: str,
        completed_at: datetime,
    ) -> bool:
        """CAS-complete a RUNNING attempt."""
        ...


class SourceBindingRepository(ABC):
    """Read/write ``SourceBindingRecord`` rows."""

    @abstractmethod
    def add(
        self,
        session: Any,
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
        """Insert a new SourceBinding and return its ID."""
        ...


class AuditOutboxRepository(ABC):
    """Write ``AuditOutboxRecord`` rows (add only).

    Dispatcher operations (claim / mark_published / mark_failed) are
    defined separately in ``AuditOutboxDispatcher`` and live in the
    infrastructure layer.
    """

    @abstractmethod
    def add(
        self,
        session: Any,
        /,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
        actor: str = "system",
        correlation_id: str = "",
        occurred_at: datetime | None = None,
        event_schema_version: str = "1.0",
        transition_id: str | None = None,
        request_id: str | None = None,
        identity_id: str | None = None,
        attempt_id: str | None = None,
        calculation_run_id: str | None = None,
        source_binding_id: str | None = None,
        available_at: datetime | None = None,
    ) -> str:
        """Insert a PENDING outbox event and return its ID.

        Event identity is deterministic from business fields.
        Idempotent: same event_identity + same payload_hash returns existing ID.
        """
        ...


class CalculationRunRepository(ABC):
    """Read/write ``CalculationRunRecord`` rows (extended for orchestration fields)."""

    @abstractmethod
    def add(
        self,
        session: Any,
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
        """Insert a new orchestrated CalculationRunRecord and return its ID."""
        ...


# ── Deterministic ID factory for Transaction B ──────────────────────────────


class TransactionBIdFactory(Protocol):
    """Deterministic ID generation for Transaction B records.

    Production code uses ``UUIDTransactionBIdFactory`` (random UUIDs).
    Tests inject ``FixedTransactionBIdFactory`` to produce deterministic,
    golden-verifiable IDs.
    """

    def calculation_run_id(self, stage_name: str) -> str:
        """Return a stable ID for a CalculationRun of the given stage."""
        ...

    def source_binding_id(self) -> str:
        """Return a stable ID for the SourceBinding record."""
        ...
