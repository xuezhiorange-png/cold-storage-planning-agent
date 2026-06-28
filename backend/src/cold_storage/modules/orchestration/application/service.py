"""Orchestration application service — Transaction A and C.

Implements the first vertical core closure from approved design:
  Transaction A (success):
    request → snapshot → coefficient context → identity →
    RUNNING attempt → request ACCEPTED

  Preflight rejection:
    durable PREFLIGHT_REJECTED + outbox event, zero downstream rows

  Transaction C (blocked/failed):
    attempt → BLOCKED/FAILED + outbox event (no calculator execution)

All repository operations are session-bound.  The service owns the
UnitOfWork lifecycle via the injected factory.

The request_id is threaded through a frozen ``TransactionAContext``
and carried via ``TransactionRejected`` internal exception — never
stored in mutable instance state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from cold_storage.modules.orchestration.application.ports import (
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWork,
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    OrchestrationRequestCommand,
    PreflightFailure,
    RequestStatus,
)
from cold_storage.modules.orchestration.domain.errors import (
    AmbiguousCoefficientError,
    CoefficientNotApprovedError,
    CoefficientResolutionError,
    OrchestrationDomainError,
    OrchestrationRequestIdentityError,
    ProjectVersionArchivedError,
    ProjectVersionNotFoundError,
    ProjectVersionNotReadyError,
    ProjectVersionProjectMismatchError,
    ProjectVersionStatusInvalidError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.infrastructure.repositories import (
    AuditOutboxRepository,
    CoefficientContextRepository,
    ExecutionSnapshotRepository,
    OrchestrationAttemptRepository,
    OrchestrationIdentityRepository,
    OrchestrationRequestRepository,
)

# ── ProjectVersion loading port ─────────────────────────────────────────────


class ProjectVersionReadPort(Protocol):
    """Read-only port for loading ProjectVersion and its input data."""

    def load_by_id(self, session: object, project_version_id: str) -> _LoadedVersion | None: ...


class _LoadedVersion:
    """Value object returned by ``ProjectVersionReadPort.load_by_id``."""

    __slots__ = ("project_id", "status", "version_number", "input_snapshot")

    def __init__(
        self,
        project_id: str,
        status: str,
        version_number: int = 0,
        input_snapshot: dict[str, object] | None = None,
    ) -> None:
        self.project_id = project_id
        self.status = status
        self.version_number = version_number
        self.input_snapshot: dict[str, object] = input_snapshot or {}


# ── Result types ────────────────────────────────────────────────────────────


class PreflightAccepted:
    """Result returned when preflight passes and Transaction A commits."""

    __slots__ = ("request_id", "fingerprint", "identity_id", "attempt_id")

    def __init__(
        self,
        request_id: str,
        fingerprint: str,
        identity_id: str,
        attempt_id: str,
    ) -> None:
        self.request_id = request_id
        self.fingerprint = fingerprint
        self.identity_id = identity_id
        self.attempt_id = attempt_id


@dataclass(frozen=True, slots=True)
class TransactionAContext:
    """Immutable context carrying the durable request identity through
    the full Transaction A lifecycle."""

    request_id: str
    request_fingerprint: str


class TransactionRejected(Exception):
    """Internal signal carrying the durable request_id of a failed
    Transaction A.  Raised from ``_transaction_a`` and caught in
    ``execute`` to persist rejection atomically."""

    __slots__ = ("request_id", "domain_error")

    def __init__(self, request_id: str, domain_error: OrchestrationDomainError) -> None:
        super().__init__(domain_error.code)
        self.request_id = request_id
        self.domain_error = domain_error


# ── Service ─────────────────────────────────────────────────────────────────

_ORCHESTRATION_DEFINITION_VERSION = "1.0.0"
_CALCULATOR_VERSION_VECTOR: dict[str, str] = {
    "zone": "1.0.0",
    "cooling_load": "1.0.0",
    "equipment": "1.0.0",
    "power": "1.0.0",
    "investment": "1.0.0",
}
_INPUT_MAPPING_SCHEMA_VERSION = "1.0.0"
_SOURCE_SNAPSHOT_SCHEMA_VERSION = "1.0.0"
_SNAPSHOT_SCHEMA_VERSION = "1.0.0"
_COEFFICIENT_SCHEMA_VERSION = "1.0.0"
_SUPPORTED_COEFFICIENT_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0.0"})


class OrchestrationService:
    """Orchestrates request validation and identity/attempt creation.

    Receives a UnitOfWork factory and owns the transaction lifecycle.
    Repositories are session-bound and never manage transactions.

    The service carries NO mutable per-request state.  All request-scoped
    data lives in local variables or ``TransactionAContext``.
    """

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyOrchestrationUnitOfWorkFactory,
        request_repo: OrchestrationRequestRepository,
        outbox_repo: AuditOutboxRepository,
        snapshot_repo: ExecutionSnapshotRepository,
        coefficient_repo: CoefficientContextRepository,
        identity_repo: OrchestrationIdentityRepository,
        attempt_repo: OrchestrationAttemptRepository,
        version_port: ProjectVersionReadPort,
        snapshot_port: ExecutionSnapshotPreflightPort,
        coefficient_port: CoefficientResolutionPreflightPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_repo = request_repo
        self._outbox_repo = outbox_repo
        self._snapshot_repo = snapshot_repo
        self._coefficient_repo = coefficient_repo
        self._identity_repo = identity_repo
        self._attempt_repo = attempt_repo
        self._version_port = version_port
        self._snapshot_port = snapshot_port
        self._coefficient_port = coefficient_port

    # ── Transaction A: request → ACCEPTED ───────────────────────────────

    def execute(self, command: OrchestrationRequestCommand) -> PreflightAccepted:
        """Run full Transaction A.

        On success: request ACCEPTED + identity + RUNNING attempt committed.
        On failure: PREFLIGHT_REJECTED + outbox committed.

        The caller receives ``PreflightAccepted`` on success, or
        ``PreflightFailure`` is raised (already persisted).
        """
        with self._uow_factory() as uow:
            try:
                return self._transaction_a(command, uow)
            except TransactionRejected as rejected:
                self._transaction_rejection(
                    rejected.request_id, rejected.domain_error, uow
                )
                uow.commit()
                raise PreflightFailure(
                    request_id=rejected.request_id,
                    project_id=command.project_id,
                    project_version_id=command.project_version_id,
                    error_class=type(rejected.domain_error).__name__,
                    code=rejected.domain_error.code,
                    field=rejected.domain_error.field,
                    details=rejected.domain_error.details,
                    occurred_at=datetime.now(UTC),
                ) from rejected.domain_error
            except Exception:
                uow.rollback()
                raise

    def _transaction_a(
        self,
        command: OrchestrationRequestCommand,
        uow: SqlAlchemyOrchestrationUnitOfWork,
    ) -> PreflightAccepted:
        session = uow.session

        # 1 — Validate + create PENDING request; capture context immediately
        _validate_command_identity(command)
        fingerprint = _compute_request_fingerprint(command)
        ctx = TransactionAContext(
            request_id=self._request_repo.add(
                session,
                requested_project_id=command.project_id,
                requested_project_version_id=command.project_version_id,
                request_fingerprint=fingerprint,
                actor=command.actor,
                correlation_id=command.correlation_id,
            ),
            request_fingerprint=fingerprint,
        )

        # 2 — Load + validate ProjectVersion
        version = self._version_port.load_by_id(session, command.project_version_id)
        if version is None:
            raise TransactionRejected(
                ctx.request_id, ProjectVersionNotFoundError(command.project_version_id)
            )
        if version.project_id != command.project_id:
            raise TransactionRejected(
                ctx.request_id,
                ProjectVersionProjectMismatchError(version.project_id, command.project_id),
            )
        try:
            _validate_version_status(version, command.project_version_id)
        except OrchestrationDomainError as exc:
            raise TransactionRejected(ctx.request_id, exc) from exc

        # 3 — Preflight ports
        self._snapshot_port.validate_candidate(
            project_id=command.project_id,
            project_version_id=command.project_version_id,
            version_status=version.status,
        )
        resolved_coeff = self._coefficient_port.resolve(
            project_id=command.project_id,
            project_version_id=command.project_version_id,
            coefficient_resolution_context=dict(command.coefficient_resolution_context),
        )

        # P0-5: Validate the resolved coefficient candidate
        _validate_coefficient_candidate(resolved_coeff, command)

        # 4 — Get-or-create execution snapshot
        input_snapshot_hash = result_hash(version.input_snapshot)
        snapshot_id = self._snapshot_repo.get_or_create(
            session,
            project_version_id=command.project_version_id,
            input_snapshot_hash=input_snapshot_hash,
            schema_version=_SNAPSHOT_SCHEMA_VERSION,
            project_id=command.project_id,
            version_number=version.version_number,
            input_snapshot=version.input_snapshot,
        )

        # 5 — Get-or-create coefficient context (from resolved candidate, NOT forged)
        coefficient_content = dict(resolved_coeff.content)
        coefficient_hash = resolved_coeff.content_hash
        coefficient_id = self._coefficient_repo.get_or_create(
            session,
            project_version_id=command.project_version_id,
            content_hash=coefficient_hash,
            content=coefficient_content,
            schema_version=_COEFFICIENT_SCHEMA_VERSION,
            project_id=command.project_id,
        )

        # 6 — Get-or-create identity (fingerprint uses frozen design fields)
        orchestration_fingerprint = _compute_orchestration_fingerprint(
            execution_identity_hash=input_snapshot_hash,
            coefficient_context_hash=coefficient_hash,
            definition_version=_ORCHESTRATION_DEFINITION_VERSION,
            calculator_version_vector=_CALCULATOR_VERSION_VECTOR,
            input_mapping_schema_version=_INPUT_MAPPING_SCHEMA_VERSION,
            source_snapshot_schema_version=_SOURCE_SNAPSHOT_SCHEMA_VERSION,
        )
        identity_id = self._identity_repo.get_or_create(
            session,
            fingerprint=orchestration_fingerprint,
            execution_snapshot_id=snapshot_id,
            coefficient_context_id=coefficient_id,
            definition_version=_ORCHESTRATION_DEFINITION_VERSION,
            calculator_version_vector=_CALCULATOR_VERSION_VECTOR,
        )

        # 7 — Acquire RUNNING attempt (with full acquisition logic)
        attempt_id = self._attempt_repo.acquire(
            session,
            identity_id=identity_id,
            heartbeat_at=datetime.now(UTC),
        )

        # 8 — Transition request → ACCEPTED (with rowcount check)
        self._request_repo.update_status(
            session,
            ctx.request_id,
            status=RequestStatus.ACCEPTED,
            resolved_project_id=command.project_id,
            resolved_project_version_id=command.project_version_id,
            resolved_identity_id=identity_id,
            resolved_attempt_id=attempt_id,
        )

        # 9 — Write request-level outbox event
        self._outbox_repo.add(
            session,
            event_type="orchestration.request.accepted",
            aggregate_type="OrchestrationRequest",
            aggregate_id=ctx.request_id,
            payload={
                "identity_id": identity_id,
                "attempt_id": attempt_id,
                "fingerprint": orchestration_fingerprint,
            },
            request_id=ctx.request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
        )

        uow.commit()
        return PreflightAccepted(ctx.request_id, fingerprint, identity_id, attempt_id)

    # ── Transaction C: attempt → terminal ───────────────────────────────

    def mark_attempt_blocked(
        self, attempt_id: str, *, failure_code: str, failure_details: dict[str, object]
    ) -> None:
        """Mark a RUNNING attempt as BLOCKED (Transaction C) + outbox."""
        with self._uow_factory() as uow:
            self._attempt_repo.update_status(
                uow.session,
                attempt_id,
                status=AttemptStatus.BLOCKED,
                failure_code=failure_code,
                failure_details=failure_details,
            )
            self._outbox_repo.add(
                uow.session,
                event_type="orchestration.attempt.blocked",
                aggregate_type="OrchestrationRunAttempt",
                aggregate_id=attempt_id,
                payload={
                    "failure_code": failure_code,
                    "failure_details": failure_details,
                },
                attempt_id=attempt_id,
            )
            uow.commit()

    def mark_attempt_failed(
        self, attempt_id: str, *, failure_code: str, failure_details: dict[str, object]
    ) -> None:
        """Mark a RUNNING attempt as FAILED (Transaction C) + outbox."""
        with self._uow_factory() as uow:
            self._attempt_repo.update_status(
                uow.session,
                attempt_id,
                status=AttemptStatus.FAILED,
                failure_code=failure_code,
                failure_details=failure_details,
            )
            self._outbox_repo.add(
                uow.session,
                event_type="orchestration.attempt.failed",
                aggregate_type="OrchestrationRunAttempt",
                aggregate_id=attempt_id,
                payload={
                    "failure_code": failure_code,
                    "failure_details": failure_details,
                },
                attempt_id=attempt_id,
            )
            uow.commit()

    # ── Preflight rejection persistence ─────────────────────────────────

    def _transaction_rejection(
        self,
        request_id: str,
        exc: OrchestrationDomainError,
        uow: SqlAlchemyOrchestrationUnitOfWork,
    ) -> None:
        """Persist a preflight rejection atomically using the explicit request_id.

        The request_id is carried via ``TransactionRejected`` from
        ``_transaction_a`` — never read from instance state.
        """
        session = uow.session

        # P0-3: nested try/except — if rejection persistence fails, we roll back
        try:
            self._request_repo.update_status(
                session,
                request_id,
                status=RequestStatus.PREFLIGHT_REJECTED,
                failure_code=exc.code,
                failure_field=exc.field,
                failure_details=dict(exc.details),
            )
            self._outbox_repo.add(
                session,
                event_type="orchestration.request.rejected",
                aggregate_type="OrchestrationRequest",
                aggregate_id=request_id,
                payload={
                    "error_class": type(exc).__name__,
                    "code": exc.code,
                    "field": exc.field,
                    "details": dict(exc.details),
                },
                request_id=request_id,
            )
        except Exception:
            uow.rollback()
            raise


# ── Module-level helpers ────────────────────────────────────────────────────


def _validate_command_identity(command: OrchestrationRequestCommand) -> None:
    if not command.actor or not command.actor.strip():
        raise OrchestrationRequestIdentityError(field="actor", message="Actor is required")
    if not command.correlation_id or not command.correlation_id.strip():
        raise OrchestrationRequestIdentityError(
            field="correlation_id", message="Correlation ID is required"
        )
    if not command.project_id or not command.project_id.strip():
        raise OrchestrationRequestIdentityError(
            field="project_id", message="Project ID is required"
        )
    if not command.project_version_id or not command.project_version_id.strip():
        raise OrchestrationRequestIdentityError(
            field="project_version_id", message="Project version ID is required"
        )


def _validate_version_status(version: _LoadedVersion, pv_id: str) -> None:
    status = version.status
    if status == "approved":
        return
    if status == "draft":
        raise ProjectVersionNotReadyError(pv_id, status)
    if status == "archived":
        raise ProjectVersionArchivedError(pv_id)
    raise ProjectVersionStatusInvalidError(pv_id, status)


def _validate_coefficient_candidate(
    candidate: ResolvedCoefficientContextCandidate,
    command: OrchestrationRequestCommand,
) -> None:
    """P0-5: Validate that the resolved coefficient candidate is authoritative.

    The caller must not self-attest approval — the resolver must return
    a candidate whose identity fields match the command and whose content
    hash is self-consistent.
    """
    if candidate.project_id != command.project_id:
        raise CoefficientResolutionError(
            "mismatch",
            f"Candidate project_id {candidate.project_id!r} != "
            f"command project_id {command.project_id!r}",
        )
    if candidate.project_version_id != command.project_version_id:
        raise CoefficientResolutionError(
            "mismatch",
            f"Candidate project_version_id {candidate.project_version_id!r} != "
            f"command project_version_id {command.project_version_id!r}",
        )
    if candidate.content_hash != result_hash(candidate.content):
        raise CoefficientResolutionError(
            "hash",
            f"Content hash mismatch: candidate claims {candidate.content_hash!r}, "
            f"computed {result_hash(candidate.content)!r}",
        )
    if not candidate.approved_revision_ids:
        raise CoefficientNotApprovedError("empty_approved_revisions")
    if len(candidate.approved_revision_ids) != len(set(candidate.approved_revision_ids)):
        raise AmbiguousCoefficientError("duplicate_approved_revisions")
    if candidate.schema_version not in _SUPPORTED_COEFFICIENT_SCHEMA_VERSIONS:
        raise CoefficientResolutionError(
            "schema",
            f"Unsupported coefficient schema version {candidate.schema_version!r}",
        )
    # Content must not self-attest approval without resolver backing
    if candidate.content.get("source_type") == "approved" and not candidate.approved_revision_ids:
        raise CoefficientNotApprovedError("self_attested_approved")
    # If content carries identity fields, they must match typed fields
    content_pid = candidate.content.get("project_id")
    if content_pid is not None and content_pid != candidate.project_id:
        raise CoefficientResolutionError(
            "mismatch",
            f"Content project_id {content_pid!r} != typed {candidate.project_id!r}",
        )
    content_pvid = candidate.content.get("project_version_id")
    if content_pvid is not None and content_pvid != candidate.project_version_id:
        raise CoefficientResolutionError(
            "mismatch",
            f"Content project_version_id {content_pvid!r} != "
            f"typed {candidate.project_version_id!r}",
        )


def _compute_request_fingerprint(command: OrchestrationRequestCommand) -> str:
    return result_hash(
        {
            "project_id": command.project_id,
            "project_version_id": command.project_version_id,
            "coefficient_resolution_context": dict(command.coefficient_resolution_context),
            "actor": command.actor,
            "correlation_id": command.correlation_id,
        }
    )


def _compute_orchestration_fingerprint(
    *,
    execution_identity_hash: str,
    coefficient_context_hash: str,
    definition_version: str,
    calculator_version_vector: dict[str, str],
    input_mapping_schema_version: str,
    source_snapshot_schema_version: str,
) -> str:
    """Compute the orchestration fingerprint from the frozen design fields.

    Uses real content hashes and version vectors — never DB random IDs.
    """
    return result_hash(
        {
            "execution_identity_hash": execution_identity_hash,
            "coefficient_context_hash": coefficient_context_hash,
            "orchestration_definition_version": definition_version,
            "calculator_version_vector": calculator_version_vector,
            "input_mapping_schema_version": input_mapping_schema_version,
            "source_snapshot_schema_version": source_snapshot_schema_version,
        }
    )
