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

    @abstractmethod
    def get_envelope(
        self,
        session: Any,
        /,
        request_id: str,
    ) -> tuple[str, str] | None:
        """Return ``(actor, correlation_id)`` for the durable request, or None."""
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

    @abstractmethod
    def get_fingerprint(
        self,
        session: Any,
        /,
        *,
        identity_id: str,
    ) -> str:
        """Return the orchestration fingerprint persisted on the identity row.

        Returns the ``fingerprint`` column value when the
        ``OrchestrationIdentityRecord`` row exists, otherwise the empty
        string.  Slice 2C of Phase 4 / Issue #35 promotes the
        fingerprint read-path off the application-layer direct-import
        shortcut (Phase 3 ``phase3_exceptions``) and onto this port.
        The application layer (``ProductionSourceBindingUseCase``)
        receives the port by injection; the SQLAlchemy concrete
        repository implements the read against
        ``OrchestrationIdentityRecord`` without exposing the ORM model
        to callers.
        """
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


class OutboxEnvelopeValidationError(ValueError):
    """Raised when the audit outbox envelope fields fail fail-closed validation.

    The port and infrastructure implementations MUST reject empty ``actor``
    or empty ``correlation_id`` rather than silently substituting defaults.
    Callers that need to materialise a system-level event must pass an
    explicit non-empty actor (e.g. the durable request actor) and a
    non-empty correlation_id (e.g. the durable request correlation_id or
    a dispatcher-generated trace id).
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.code = "outbox_envelope_invalid"


class AuditOutboxRepository(ABC):
    """Write ``AuditOutboxRecord`` rows (add only).

    Dispatcher operations (claim / mark_published / mark_failed) are
    implemented in the infrastructure layer as free functions.
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

        ``actor``, ``correlation_id`` and ``occurred_at`` are REQUIRED and
        must be passed explicitly by callers.  Implementations MUST raise
        :class:`OutboxEnvelopeValidationError` if ``actor`` or
        ``correlation_id`` are empty after stripping.

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


# ── Production source archive ports ─────────────────────────────────────────


class ProductionSourceArchiveWritePort(Protocol):
    """Write-side port for the ``production_source_archives`` table.

    The application layer (orchestration.application.source_archive_builder)
    constructs an archive row from a verified SchemeRun and delegates the
    SQL INSERT to a port implementation in the infrastructure layer
    (orchestration.infrastructure.source_archive_repository).  This indirection
    is what keeps the application layer free of SQLAlchemy imports and
    raw session binding.

    Implementations MUST execute the INSERT against the *active* SQLAlchemy
    session/transaction that the caller has already opened in their
    ``session`` argument.  The implementation MUST NOT commit or rollback
    the surrounding transaction — that responsibility belongs to the
    caller's Unit of Work.

    Parameters
    ----------
    session :
        An active SQLAlchemy ``Session`` (or compatible) bound to the
        same transaction the SchemeRun UoW is operating in.  The type is
        intentionally ``Any`` so the application layer does not import
        ``sqlalchemy.orm``.
    archive_id :
        The pre-computed UUID for this archive row.  Production code
        generates via the same ``TransactionBIdFactory`` family;
        backfill tests may inject a fixed string.
    """

    def add_archive(
        self,
        session: Any,
        *,
        archive_id: str,
        scheme_run_id: str,
        source_binding_id: str | None,
        source_contract_version: str,
        archive_schema_version: str,
        archive_payload: Mapping[str, Any],
        archive_hash: str,
        combined_source_hash: str | None,
        weight_set_revision_id: str | None,
        weight_set_content_hash: str | None,
        binding_schema_version: str | None,
        execution_snapshot_id: str | None,
        coefficient_context_id: str | None,
        orchestration_identity_id: str | None,
        authoritative_attempt_id: str | None,
        orchestration_fingerprint: str | None,
        created_at: datetime,
        created_by: str,
        reason: str,
    ) -> None:
        """Persist the archive row in ``session``'s transaction.

        MUST NOT commit. MUST NOT rollback.  MUST raise on integrity
        errors so the caller can convert them into domain errors.
        """
        ...


class ProductionSourceArchiveReadPort(Protocol):
    """Read-side port for the ``production_source_archives`` table.

    Returns ``None`` if no archive exists for the given scheme_run_id;
    raises ``SchemeRunHistoricalSourceUnavailableError`` only when the
    caller asks for a non-resolved bundle and the read-empty result must
    be converted to a domain error.
    """

    def find_by_scheme_run_id(
        self,
        session: Any,
        scheme_run_id: str,
    ) -> Mapping[str, Any] | None:
        """Return the archive row for ``scheme_run_id`` or None."""
        ...
