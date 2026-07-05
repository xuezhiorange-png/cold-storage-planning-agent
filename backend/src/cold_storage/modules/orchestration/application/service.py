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

Durable rejection contract (P0-1):
  After creating the durable PENDING request, a downstream savepoint
  wraps all preflight + get-or-create + attempt acquisition work.
  Any ``OrchestrationDomainError`` rolls back the downstream savepoint,
  leaving ONLY the PENDING request.  ``execute()`` then persists
  ``PREFLIGHT_REJECTED`` + outbox, yielding zero downstream rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.coefficient_contracts import (
    FrozenCoefficientResolutionCriteria,
    canonical_revision_ids,
    coefficient_item_sort_key,
    derive_required_codes_for_version_vector,
    validate_required_codes,
    validate_string_sequence,
)
from cold_storage.modules.orchestration.application.ports import (
    AuditOutboxRepository,
    CalculationRunRepository,
    CoefficientContextRepository,
    CoefficientResolutionPreflightPort,
    ExecutionSnapshotPreflightPort,
    ExecutionSnapshotRepository,
    OrchestrationAttemptRepository,
    OrchestrationIdentityRepository,
    OrchestrationRequestRepository,
    ResolvedCoefficientContextCandidate,
    SourceBindingRepository,
    TransactionBIdFactory,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    CalculatorPort,
    SourceBindingVerifier,
    TransactionBBlocked,
    TransactionBExecutor,
    TransactionBFailure,
    VerificationReadPort,
)
from cold_storage.modules.orchestration.application.unit_of_work import (
    SqlAlchemyOrchestrationUnitOfWork,
    SqlAlchemyOrchestrationUnitOfWorkFactory,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    OrchestrationRequestCommand,
    OrchestrationResult,
    PreflightFailure,
    RequestStatus,
)
from cold_storage.modules.orchestration.domain.errors import (
    AmbiguousCoefficientError,
    AttemptTerminalDisposition,
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

# ── ProjectVersion loading port ─────────────────────────────────────────────


class ProjectVersionReadPort(Protocol):
    """Read-only port for loading ProjectVersion and its input data.

    Implementations MUST load ``project_product_category`` from
    ``ProjectRecord`` (the authoritative source), not from the
    ``input_snapshot`` or caller.
    """

    def load_by_id(self, session: object, project_version_id: str) -> _LoadedVersion | None: ...


class _LoadedVersion:
    """Value object returned by ``ProjectVersionReadPort.load_by_id``.

    ``project_product_category`` comes from ``ProjectRecord.product_category``
    (the authoritative source).  If the snapshot also contains a
    ``product_category`` field, it must match — otherwise a typed rejection
    is raised.
    """

    __slots__ = (
        "project_id",
        "project_product_category",
        "status",
        "version_number",
        "input_snapshot",
    )

    def __init__(
        self,
        project_id: str,
        project_product_category: str,
        status: str,
        version_number: int = 0,
        input_snapshot: dict[str, object] | None = None,
    ) -> None:
        self.project_id = project_id
        self.project_product_category = project_product_category
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

# Registry version — bumped when REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION changes
_REQUIREMENT_REGISTRY_VERSION = "1.0.0"

# Authoritative required codes derived from the calculator version vector
_AUTHORITATIVE_REQUIRED_CODES: tuple[str, ...] = derive_required_codes_for_version_vector(
    _CALCULATOR_VERSION_VECTOR,
)
_AUTHORITATIVE_REQUIREMENT_HASH: str = result_hash(
    {
        "registry_version": _REQUIREMENT_REGISTRY_VERSION,
        "calculator_version_vector": dict(_CALCULATOR_VERSION_VECTOR),
        "required_codes": list(_AUTHORITATIVE_REQUIRED_CODES),
    }
)


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
        calc_run_repo: CalculationRunRepository,
        source_binding_repo: SourceBindingRepository,
        calculator_port: CalculatorPort,
        verification_read_port: VerificationReadPort,
        id_factory: TransactionBIdFactory | None = None,
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
        self._calc_run_repo = calc_run_repo
        self._source_binding_repo = source_binding_repo
        self._calculator_port = calculator_port
        self._verification_read_port = verification_read_port
        self._id_factory = id_factory

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
                result = self._transaction_a(command, uow)
                uow.commit()
                return result
            except TransactionRejected as rejected:
                self._transaction_rejection(
                    rejected.request_id,
                    rejected.domain_error,
                    command,
                    uow,
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

        # 2 — Create downstream savepoint: all work after durable request creation
        #     is wrapped so domain failures roll back downstream rows while the
        #     PENDING request survives for rejection persistence.
        downstream = session.begin_nested()
        try:
            result = self._transaction_a_downstream(command, ctx, session)
            downstream.commit()
            return result
        except OrchestrationDomainError as exc:
            downstream.rollback()
            raise TransactionRejected(ctx.request_id, exc) from exc

    def _transaction_a_downstream(
        self,
        command: OrchestrationRequestCommand,
        ctx: TransactionAContext,
        session: Session,
    ) -> PreflightAccepted:
        """All downstream work after durable request creation.

        Any ``OrchestrationDomainError`` triggers downstream savepoint
        rollback → only the PENDING request survives → rejection persists.
        """

        # 3 — Load + validate ProjectVersion (now includes ProjectRecord authority)
        version = self._version_port.load_by_id(session, command.project_version_id)
        if version is None:
            raise ProjectVersionNotFoundError(command.project_version_id)
        if version.project_id != command.project_id:
            raise ProjectVersionProjectMismatchError(version.project_id, command.project_id)
        _validate_version_status(version, command.project_version_id)

        # 4 — Preflight ports (domain errors now surface as TransactionRejected)
        self._snapshot_port.validate_candidate(
            project_id=command.project_id,
            project_version_id=command.project_version_id,
            version_status=version.status,
        )

        # Derive frozen coefficient resolution criteria from ProjectVersion
        # and ProjectRecord authority
        frozen_criteria = _derive_frozen_criteria(
            command=command,
            version=version,
        )

        resolved_coeff = self._coefficient_port.resolve(
            criteria=frozen_criteria,
            session=session,
        )

        # P0-5: Validate the resolved coefficient candidate
        _validate_coefficient_candidate(resolved_coeff, command, frozen_criteria)

        # 5 — Get-or-create execution snapshot
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

        # 6 — Get-or-create coefficient context (from resolved candidate, NOT forged)
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

        # 7 — Get-or-create identity (fingerprint uses frozen design fields)
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

        # 8 — Acquire RUNNING attempt (with full acquisition logic)
        attempt_id = self._attempt_repo.acquire(
            session,
            identity_id=identity_id,
            heartbeat_at=datetime.now(UTC),
        )

        # 9 — Transition request → ACCEPTED (with rowcount check)
        self._request_repo.update_status(
            session,
            ctx.request_id,
            status=RequestStatus.ACCEPTED,
            resolved_project_id=command.project_id,
            resolved_project_version_id=command.project_version_id,
            resolved_identity_id=identity_id,
            resolved_attempt_id=attempt_id,
        )

        # 10 — Write request-level outbox event
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
            actor=command.actor,
            correlation_id=command.correlation_id,
            occurred_at=datetime.now(UTC),
            transition_id=f"request:{ctx.request_id}:accepted",
            request_id=ctx.request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
        )

        return PreflightAccepted(ctx.request_id, ctx.request_fingerprint, identity_id, attempt_id)

    # ── Transaction B: calculator execution ────────────────────────────

    def execute_transaction_b(
        self,
        *,
        request_id: str,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
        orchestration_fingerprint: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
    ) -> OrchestrationResult:
        """Run Transaction B — five-stage calculator execution.

        On success: 5 CalculationRuns + 1 SourceBinding persisted,
        attempt → COMPLETED, completion outbox event emitted.

        On failure (``TransactionBFailure`` or ``OrchestrationDomainError``):
        Transaction B UoW is rolled back (partial calculator results
        discarded), an independent terminal UoW marks the attempt as
        FAILED and emits a terminal outbox event, then the original
        error is re-raised.
        """

        # Build dependencies (fresh per call — no mutable instance state)
        verifier = SourceBindingVerifier(read_port=self._verification_read_port)
        executor = TransactionBExecutor(
            calculation_run_repo=self._calc_run_repo,
            source_binding_repo=self._source_binding_repo,
            attempt_repo=self._attempt_repo,
            identity_repo=self._identity_repo,
            outbox_repo=self._outbox_repo,
            calculator_port=self._calculator_port,
            verifier=verifier,
            id_factory=self._id_factory,
        )

        # ── Primary UoW: Transaction B execution ──────────────────────
        # P0-3 (Round 7): envelope must be loaded and validated BEFORE any
        # other precondition check.  All terminal paths below reference
        # ``envelope_actor`` and ``envelope_correlation_id`` — initialize
        # them up front (outside the try) so that except handlers cannot
        # raise UnboundLocalError, and so that the fail-closed contract
        # holds: the only values ever passed to the outbox are the
        # envelope loaded from the durable request, or the explicit
        # "envelope-unavailable" sentinels set when the load itself failed.
        envelope_actor: str | None = None
        envelope_correlation_id: str | None = None
        try:
            with self._uow_factory() as uow:
                # P0-3: load envelope first.  If the durable request has no
                # envelope (the request was created via a non-authoritative
                # code path), fail closed immediately — do not silently
                # substitute "system" / "" anywhere downstream.
                loaded = self._request_repo.get_envelope(uow.session, request_id)
                if loaded is None:
                    raise TransactionBFailure(
                        "TXB_REQUEST_ENVELOPE_MISSING",
                        "Request envelope (actor, correlation_id) is missing "
                        "from the durable request — refusing to emit any "
                        "outbox event without a verified envelope identity.",
                        field="request_envelope",
                        details={"request_id": request_id},
                    )
                envelope_actor, envelope_correlation_id = loaded

                # Pre-condition: verify request is ACCEPTED and attempt is RUNNING
                request_status = self._request_repo.get_status(uow.session, request_id)
                if request_status != RequestStatus.ACCEPTED:
                    raise TransactionBFailure(
                        "TXB_REQUEST_NOT_ACCEPTED",
                        f"Request status is {request_status!r}, expected ACCEPTED",
                        field="request_status",
                        details={
                            "request_id": request_id,
                            "observed_status": request_status,
                        },
                    )

                attempt_status = self._attempt_repo.get_status(
                    uow.session, orchestration_attempt_id
                )
                if attempt_status != AttemptStatus.RUNNING:
                    raise TransactionBFailure(
                        "TXB_ATTEMPT_NOT_RUNNING",
                        f"Attempt status is {attempt_status!r}, expected RUNNING",
                        field="attempt_status",
                        details={
                            "attempt_id": orchestration_attempt_id,
                            "observed_status": attempt_status,
                        },
                    )

                result = executor.execute(
                    uow.session,
                    request_id=request_id,
                    project_id=project_id,
                    project_version_id=project_version_id,
                    execution_snapshot_id=execution_snapshot_id,
                    coefficient_context_id=coefficient_context_id,
                    orchestration_identity_id=orchestration_identity_id,
                    orchestration_attempt_id=orchestration_attempt_id,
                    orchestration_fingerprint=orchestration_fingerprint,
                    execution_snapshot=execution_snapshot,
                    coefficient_context=coefficient_context,
                    actor=envelope_actor,
                    correlation_id=envelope_correlation_id,
                    completed_at=datetime.now(UTC),
                )
                uow.commit()
                return result

        except TransactionBBlocked as exc:
            # ── Engineering blocker → BLOCKED ─────────────────────────
            t_actor, t_corr = self._resolve_terminal_envelope(
                envelope_actor, envelope_correlation_id, exc.code
            )
            self._transaction_b_terminal(
                attempt_id=orchestration_attempt_id,
                request_id=request_id,
                identity_id=orchestration_identity_id,
                exc=exc,
                disposition=exc.terminal_disposition,
                actor=t_actor,
                correlation_id=t_corr,
                occurred_at=datetime.now(UTC),
            )
            raise

        except TransactionBFailure as exc:
            # ── P0-4 (Round 8) fail-closed: if the durable request had
            # no envelope at all, refuse to emit any terminal outbox
            # event.  We only know the envelope was missing because the
            # exception code is ``TXB_REQUEST_ENVELOPE_MISSING``; in
            # that case rolling back the primary UoW is the entire
            # failure contract — no ``envelope-unavailable`` sentinel
            # outbox is written.
            #
            # This branch MUST come after ``except TransactionBBlocked``
            # because ``TransactionBBlocked`` is a subclass of
            # ``TransactionBFailure`` (see transaction_b.py).
            if exc.code == "TXB_REQUEST_ENVELOPE_MISSING":
                # Caller is responsible for rolling back the primary UoW
                # (the ``with`` block above already exits with a
                # rollback on the raised exception).  Do not invoke
                # ``_transaction_b_terminal`` — that helper would emit a
                # terminal outbox event with a sentinel envelope which
                # contradicts the fail-closed contract documented at
                # the envelope-load site.
                raise
            # ── Unexpected failure → FAILED ────────────────────────────
            t_actor, t_corr = self._resolve_terminal_envelope(
                envelope_actor, envelope_correlation_id, exc.code
            )
            self._transaction_b_terminal(
                attempt_id=orchestration_attempt_id,
                request_id=request_id,
                identity_id=orchestration_identity_id,
                exc=exc,
                disposition=AttemptTerminalDisposition.FAILED,
                actor=t_actor,
                correlation_id=t_corr,
                occurred_at=datetime.now(UTC),
            )
            raise

        except OrchestrationDomainError as exc:
            # ── Domain-layer failure (not TransactionBFailure /
            # TransactionBBlocked — those are caught above).  Treat as
            # FAILED and emit the terminal outbox event using the loaded
            # envelope (or the envelope-unavailable sentinel if loading
            # itself raised before assignment).
            t_actor, t_corr = self._resolve_terminal_envelope(
                envelope_actor, envelope_correlation_id, exc.code
            )
            self._transaction_b_terminal(
                attempt_id=orchestration_attempt_id,
                request_id=request_id,
                identity_id=orchestration_identity_id,
                exc=exc,
                disposition=AttemptTerminalDisposition.FAILED,
                actor=t_actor,
                correlation_id=t_corr,
                occurred_at=datetime.now(UTC),
            )
            raise

        except IntegrityError as exc:
            # ── Raw DB persistence failure → FAILED + terminal UoW ────
            wrapped = TransactionBFailure(
                "TXB_PERSISTENCE_FAILURE",
                f"Raw IntegrityError: {exc}",
                field="persistence",
                details={"error_class": type(exc).__name__, "cause": str(exc)},
            )
            t_actor, t_corr = self._resolve_terminal_envelope(
                envelope_actor, envelope_correlation_id, wrapped.code
            )
            self._transaction_b_terminal(
                attempt_id=orchestration_attempt_id,
                request_id=request_id,
                identity_id=orchestration_identity_id,
                exc=wrapped,
                disposition=AttemptTerminalDisposition.FAILED,
                original_exc=exc,
                actor=t_actor,
                correlation_id=t_corr,
                occurred_at=datetime.now(UTC),
            )
            raise wrapped from exc

        except Exception as exc:
            # ── Unexpected non-typed failure → FAILED + terminal UoW ──
            wrapped = TransactionBFailure(
                "TXB_UNEXPECTED_FAILURE",
                f"Unexpected failure: {exc}",
                field="unexpected",
                details={"error_class": type(exc).__name__, "cause": str(exc)},
            )
            t_actor, t_corr = self._resolve_terminal_envelope(
                envelope_actor, envelope_correlation_id, wrapped.code
            )
            self._transaction_b_terminal(
                attempt_id=orchestration_attempt_id,
                request_id=request_id,
                identity_id=orchestration_identity_id,
                exc=wrapped,
                disposition=AttemptTerminalDisposition.FAILED,
                original_exc=exc,
                actor=t_actor,
                correlation_id=t_corr,
                occurred_at=datetime.now(UTC),
            )
            raise wrapped from exc

    # ── Exhaustive disposition → status / event mapping ─────────────────

    _TERMINAL_STATUS_BY_DISPOSITION: dict[AttemptTerminalDisposition, AttemptStatus] = {
        AttemptTerminalDisposition.BLOCKED: AttemptStatus.BLOCKED,
        AttemptTerminalDisposition.FAILED: AttemptStatus.FAILED,
    }

    _TERMINAL_EVENT_BY_DISPOSITION: dict[AttemptTerminalDisposition, str] = {
        AttemptTerminalDisposition.BLOCKED: "orchestration.attempt.blocked",
        AttemptTerminalDisposition.FAILED: "orchestration.attempt.failed",
    }

    def _resolve_terminal_envelope(
        self,
        envelope_actor: str | None,
        envelope_correlation_id: str | None,
        exc_code: str,
    ) -> tuple[str, str]:
        """Resolve the actor/correlation_id for a terminal outbox event.

        P0-3 fail-closed contract:
          * If the durable request envelope was loaded successfully, use
            it verbatim — never substitute defaults.
          * If the envelope could not be loaded (load raised before
            assignment), use an explicit ``envelope-unavailable``
            sentinel tagged with the failure code.  This sentinel is
            recognizable in audit but does NOT use the forbidden
            ``"system"`` / ``""`` defaults.
        """
        if envelope_actor is not None and envelope_correlation_id is not None:
            return envelope_actor, envelope_correlation_id
        # Envelope unavailable — record it explicitly.  We deliberately
        # avoid ``"system"`` and empty string here; the audit trail must
        # show that the envelope was not present at terminal time.
        sentinel_actor = f"envelope-unavailable:{exc_code}"
        sentinel_correlation_id = f"envelope-unavailable:{exc_code}"
        return sentinel_actor, sentinel_correlation_id

    def _transaction_b_terminal(
        self,
        *,
        attempt_id: str,
        request_id: str,
        identity_id: str,
        exc: TransactionBFailure | OrchestrationDomainError,
        disposition: AttemptTerminalDisposition,
        original_exc: Exception | None = None,
        actor: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> None:
        """Persist a Transaction B terminal state atomically in an independent UoW.

        Transitions the attempt to BLOCKED or FAILED via guarded CAS and
        emits a matching terminal outbox event.  The ``disposition``
        parameter MUST be a typed ``AttemptTerminalDisposition`` — raw
        strings are rejected.

        Only ``TRANSITIONED`` outcome produces a terminal outbox event.
        ``ALREADY_COMPLETED``, ``ALREADY_TERMINAL``, ``NOT_FOUND``, and
        ``STATE_CONFLICT`` are silent — no outbox, no overwrite.

        ``actor``, ``correlation_id`` and ``occurred_at`` MUST be supplied
        explicitly — the outbox event envelope uses authoritative values
        sourced from the durable request, not the repository defaults.
        """
        from cold_storage.modules.orchestration.application.ports import (
            TerminalTransitionOutcome,
        )

        if not isinstance(disposition, AttemptTerminalDisposition):
            got = type(disposition).__name__
            raise TypeError(f"disposition must be AttemptTerminalDisposition, got {got!r}")
        failure_code: str = exc.code
        failure_field: str = exc.field
        failure_details: dict[str, object] = dict(exc.details)
        terminal_status = self._TERMINAL_STATUS_BY_DISPOSITION[disposition]
        event_type = self._TERMINAL_EVENT_BY_DISPOSITION[disposition]

        with self._uow_factory() as terminal_uow:
            result = self._attempt_repo.transition_running_to_terminal(
                terminal_uow.session,
                attempt_id=attempt_id,
                identity_id=identity_id,
                target_status=terminal_status,
                failure_code=failure_code,
                failure_details={
                    "failure_code": failure_code,
                    "failure_field": failure_field,
                    "terminal_disposition": disposition,
                    **failure_details,
                },
                completed_at=occurred_at,
            )
            if result.outcome == TerminalTransitionOutcome.TRANSITIONED:
                self._outbox_repo.add(
                    terminal_uow.session,
                    event_type=event_type,
                    aggregate_type="OrchestrationRunAttempt",
                    aggregate_id=attempt_id,
                    payload={
                        "failure_code": failure_code,
                        "failure_field": failure_field,
                        "failure_details": failure_details,
                        "error_class": type(exc).__name__,
                        "terminal_disposition": disposition,
                    },
                    actor=actor,
                    correlation_id=correlation_id,
                    occurred_at=occurred_at,
                    transition_id=f"attempt:{attempt_id}:{disposition.value}",
                    request_id=request_id,
                    identity_id=identity_id,
                    attempt_id=attempt_id,
                )
            terminal_uow.commit()

    # ── Transaction C: attempt → terminal ───────────────────────────────

    def mark_attempt_blocked(
        self,
        attempt_id: str,
        *,
        failure_code: str,
        failure_details: dict[str, object],
        actor: str,
        correlation_id: str,
    ) -> None:
        """Mark a RUNNING attempt as BLOCKED (Transaction C) + outbox.

        ``actor`` and ``correlation_id`` MUST be supplied explicitly —
        the outbox event envelope uses authoritative values from the
        durable request, not repository defaults.
        """
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
                actor=actor,
                correlation_id=correlation_id,
                occurred_at=datetime.now(UTC),
                transition_id=f"attempt:{attempt_id}:blocked:{failure_code}",
                attempt_id=attempt_id,
            )
            uow.commit()

    def mark_attempt_failed(
        self,
        attempt_id: str,
        *,
        failure_code: str,
        failure_details: dict[str, object],
        actor: str,
        correlation_id: str,
    ) -> None:
        """Mark a RUNNING attempt as FAILED (Transaction C) + outbox.

        ``actor`` and ``correlation_id`` MUST be supplied explicitly —
        the outbox event envelope uses authoritative values from the
        durable request, not repository defaults.
        """
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
                actor=actor,
                correlation_id=correlation_id,
                occurred_at=datetime.now(UTC),
                transition_id=f"attempt:{attempt_id}:failed:{failure_code}",
                attempt_id=attempt_id,
            )
            uow.commit()

    # ── Preflight rejection persistence ─────────────────────────────────

    def _transaction_rejection(
        self,
        request_id: str,
        exc: OrchestrationDomainError,
        command: OrchestrationRequestCommand,
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
                event_type="orchestration.request.preflight_rejected",
                aggregate_type="OrchestrationRequest",
                aggregate_id=request_id,
                payload={
                    "error_class": type(exc).__name__,
                    "code": exc.code,
                    "field": exc.field,
                    "details": dict(exc.details),
                },
                actor=command.actor,
                correlation_id=command.correlation_id,
                occurred_at=datetime.now(UTC),
                transition_id=f"request:{request_id}:preflight_rejected",
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


# ── Frozen coefficient resolution criteria derivation ───────────────────────
#
# Authoritative required codes come from the calculator-version registry
# (``REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION``).  The snapshot MAY
# carry a ``required_coefficient_codes`` reference, but if present it
# MUST exactly match the authoritative set.  Empty snapshot override
# cannot erase a non-empty authoritative set.


# ── Caller conflict validation helpers ──────────────────────────────────────
# All recognized caller context aliases that must not conflict with frozen criteria.
_CALLER_CONTEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "product_type": ("product_type",),
    "product_category": ("product_category",),
    "zone_type": ("zone_type", "zone_types"),
    "zone_types": ("zone_type", "zone_types"),
    "process_type": ("process_type", "process_types"),
    "process_types": ("process_type", "process_types"),
    "required_codes": ("required_codes", "required_coefficient_codes"),
    "required_coefficient_codes": ("required_codes", "required_coefficient_codes"),
}

# Caller self-attestation fields that must be completely ignored
_IGNORED_CALLER_FIELDS: frozenset[str] = frozenset(
    {
        "approved_revision_ids",
        "status",
        "validity_status",
        "approved",
    }
)


def _extract_caller_value(
    caller_ctx: dict[str, object],
    primary_key: str,
) -> object | None:
    """Extract a value from caller context, checking all aliases for the key."""
    aliases = _CALLER_CONTEXT_ALIASES.get(primary_key, (primary_key,))
    found_value: object | None = None
    found_count = 0
    for alias in aliases:
        if alias in caller_ctx:
            val = caller_ctx[alias]
            if val is not None:
                found_value = val
                found_count += 1
    # If multiple aliases are present, they must agree
    if found_count > 1:
        values_seen: list[object] = []
        for alias in aliases:
            if alias in caller_ctx and caller_ctx[alias] is not None:
                values_seen.append(caller_ctx[alias])
        # Check all values are equivalent using semantic normalization
        _check_alias_consistency(values_seen, primary_key)
    return found_value


# ── Alias normalization keys ──────────────────────────────────────────────
_ZONE_PROCESS_KEYS: frozenset[str] = frozenset(
    {
        "zone_type",
        "zone_types",
        "process_type",
        "process_types",
    }
)
_PRODUCT_KEYS: frozenset[str] = frozenset({"product_type", "product_category"})
_CODES_KEYS: frozenset[str] = frozenset({"required_codes", "required_coefficient_codes"})


def _check_alias_consistency(
    values_seen: list[object],
    primary_key: str,
) -> None:
    """Normalize multiple alias values and verify they are semantically equivalent.

    Raises CoefficientResolutionError("invalid_criteria", ...) when a value
    fails normalization, or ("criteria_conflict", ...) when canonical forms differ.
    """
    canonical: list[object] = []

    if primary_key in _ZONE_PROCESS_KEYS:
        for val in values_seen:
            try:
                canonical.append(validate_string_sequence(val, field_name=f"caller_{primary_key}"))
            except CoefficientResolutionError as exc:
                raise CoefficientResolutionError(
                    "invalid_criteria",
                    f"Caller {primary_key} value {val!r} is not a valid string sequence",
                ) from exc
        if len(set(canonical)) > 1:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller context aliases for {primary_key!r} disagree: {values_seen}",
            )

    elif primary_key in _PRODUCT_KEYS:
        for val in values_seen:
            if not isinstance(val, str):
                raise CoefficientResolutionError(
                    "invalid_criteria",
                    f"Caller {primary_key} value {val!r} must"
                    f" be a string, got {type(val).__name__}",
                )
            canonical.append(val.strip())
        if len(set(canonical)) > 1:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller context aliases for {primary_key!r} disagree: {values_seen}",
            )

    elif primary_key in _CODES_KEYS:
        for val in values_seen:
            try:
                canonical.append(validate_required_codes(val, field_name=f"caller_{primary_key}"))
            except CoefficientResolutionError as exc:
                raise CoefficientResolutionError(
                    "invalid_criteria",
                    f"Caller {primary_key} value {val!r} is not valid",
                ) from exc
        if len(set(canonical)) > 1:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller context aliases for {primary_key!r} disagree: {values_seen}",
            )

    else:
        # Fallback: string comparison for unrecognized keys
        if len(set(str(v) for v in values_seen)) > 1:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller context aliases for {primary_key!r} disagree: {values_seen}",
            )


def _validate_caller_conflicts(
    *,
    caller_ctx: dict[str, object],
    product_category: str | None,
    product_type: str | None,
    zone_types: tuple[str, ...],
    process_types: tuple[str, ...],
    required_codes: tuple[str, ...],
) -> None:
    """Validate that caller context does not conflict with frozen criteria.

    All recognized aliases are checked.  Approval/status/revision self-attestation
    fields are ignored.  Type errors are rejected.
    """
    # Product category conflict
    caller_pc = _extract_caller_value(caller_ctx, "product_category")
    if caller_pc is not None and product_category is not None:
        if not isinstance(caller_pc, str):
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller product_category must be str, got {type(caller_pc).__name__}",
            )
        if caller_pc.strip() != product_category:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller product_category {caller_pc!r} != frozen {product_category!r}",
            )

    # Product type conflict
    caller_pt = _extract_caller_value(caller_ctx, "product_type")
    if caller_pt is not None and product_type is not None:
        if not isinstance(caller_pt, str):
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller product_type must be str, got {type(caller_pt).__name__}",
            )
        if caller_pt.strip() != product_type:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller product_type {caller_pt!r} != frozen {product_type!r}",
            )

    # Zone type conflict
    caller_zt = _extract_caller_value(caller_ctx, "zone_type")
    if caller_zt is not None:
        caller_zt_tuple = validate_string_sequence(caller_zt, field_name="caller_zone_type")
        if not zone_types and caller_zt_tuple:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Frozen zone_types is empty but caller provides {sorted(caller_zt_tuple)!r}",
            )
        if zone_types:
            frozen_zt = sorted(zone_types)
            if sorted(caller_zt_tuple) != frozen_zt:
                raise CoefficientResolutionError(
                    "criteria_conflict",
                    f"Caller zone_types {sorted(caller_zt_tuple)!r} != frozen {frozen_zt!r}",
                )

    # Process type conflict
    caller_pr = _extract_caller_value(caller_ctx, "process_type")
    if caller_pr is not None:
        caller_pr_tuple = validate_string_sequence(caller_pr, field_name="caller_process_type")
        if not process_types and caller_pr_tuple:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Frozen process_types is empty but caller provides {sorted(caller_pr_tuple)!r}",
            )
        if process_types:
            frozen_pr = sorted(process_types)
            if sorted(caller_pr_tuple) != frozen_pr:
                raise CoefficientResolutionError(
                    "criteria_conflict",
                    f"Caller process_types {sorted(caller_pr_tuple)!r} != frozen {frozen_pr!r}",
                )

    # Required codes conflict
    caller_req = _extract_caller_value(caller_ctx, "required_codes")
    if caller_req is not None:
        if not required_codes:
            # frozen empty + caller non-empty → conflict
            raise CoefficientResolutionError(
                "criteria_conflict",
                "Frozen required_codes is empty but caller provides required_codes",
            )
        if isinstance(caller_req, (list, tuple)):
            validated = validate_required_codes(caller_req, field_name="caller_required_codes")
            frozen_list = list(required_codes)
            caller_list = list(validated)
            if caller_list != frozen_list:
                raise CoefficientResolutionError(
                    "criteria_conflict",
                    f"Caller required_codes {caller_list!r} != frozen {frozen_list!r}",
                )
        else:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller required_codes must be list/tuple, got {type(caller_req).__name__}",
            )


def _derive_frozen_criteria(
    *,
    command: OrchestrationRequestCommand,
    version: _LoadedVersion,
) -> FrozenCoefficientResolutionCriteria:
    """Derive authoritative coefficient resolution criteria from the frozen
    ProjectVersion, ProjectRecord authority, and the calculator-version
    registry.

    The caller's context is validated for consistency; conflicts raise
    a typed CoefficientResolutionError.

    The authoritative required codes come from
    ``REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION`` via
    ``_CALCULATOR_VERSION_VECTOR``.  The snapshot MAY carry a
    ``required_coefficient_codes`` field, but if present it MUST
    exactly match the authoritative set.
    """
    input_snapshot = version.input_snapshot

    # ── Product category from ProjectRecord (authoritative) ─────────────
    product_category: str | None = version.project_product_category

    # If snapshot also has product_category, it must match
    snapshot_pc = input_snapshot.get("product_category")
    if snapshot_pc is not None:
        if not isinstance(snapshot_pc, str):
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Snapshot product_category must be str, got {type(snapshot_pc).__name__}",
            )
        if snapshot_pc.strip() != product_category:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Snapshot product_category {snapshot_pc!r} != ProjectRecord {product_category!r}",
            )

    # ── Product type from snapshot ──────────────────────────────────────
    product_type: str | None = None
    raw_pt = input_snapshot.get("product_type")
    if raw_pt is not None:
        if not isinstance(raw_pt, str):
            raise CoefficientResolutionError(
                "invalid_criteria",
                f"Snapshot product_type must be str, got {type(raw_pt).__name__}",
            )
        stripped_pt = raw_pt.strip()
        if not stripped_pt:
            raise CoefficientResolutionError(
                "invalid_criteria",
                "Snapshot product_type must not be blank",
            )
        product_type = stripped_pt

    # ── Zone types from snapshot ────────────────────────────────────────
    raw_zt = input_snapshot.get("zone_types")
    zone_types: tuple[str, ...] = (
        validate_string_sequence(raw_zt, field_name="snapshot_zone_types")
        if raw_zt is not None
        else ()
    )

    # ── Process types from snapshot ─────────────────────────────────────
    raw_pr = input_snapshot.get("process_types")
    process_types: tuple[str, ...] = (
        validate_string_sequence(raw_pr, field_name="snapshot_process_types")
        if raw_pr is not None
        else ()
    )

    # ── Required codes: authoritative from registry ─────────────────────
    # Snapshot MAY carry required_coefficient_codes, but it MUST exactly
    # match the authoritative set.  Empty snapshot override cannot erase
    # a non-empty authoritative set.
    required_codes = _AUTHORITATIVE_REQUIRED_CODES

    raw_req = input_snapshot.get("required_coefficient_codes")
    if raw_req is not None:
        validated_snapshot_req = validate_required_codes(
            raw_req, field_name="snapshot_required_coefficient_codes"
        )
        if set(validated_snapshot_req) != set(required_codes):
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Snapshot required_coefficient_codes {sorted(validated_snapshot_req)!r} "
                f"!= authoritative {sorted(required_codes)!r}",
            )

    # ── Validate caller context conflicts ───────────────────────────────
    caller_ctx = dict(command.coefficient_resolution_context)

    # Ignored self-attestation fields — strip them before validation
    for ignored_field in _IGNORED_CALLER_FIELDS:
        caller_ctx.pop(ignored_field, None)

    _validate_caller_conflicts(
        caller_ctx=caller_ctx,
        product_category=product_category,
        product_type=product_type,
        zone_types=zone_types,
        process_types=process_types,
        required_codes=required_codes,
    )

    return FrozenCoefficientResolutionCriteria(
        project_id=command.project_id,
        project_version_id=command.project_version_id,
        product_category=product_category,
        product_type=product_type,
        zone_types=zone_types,
        process_types=process_types,
        requirement_registry_version=_REQUIREMENT_REGISTRY_VERSION,
        calculator_version_vector=dict(_CALCULATOR_VERSION_VECTOR),
        required_codes=required_codes,
        requirement_hash=_AUTHORITATIVE_REQUIREMENT_HASH,
    )


def _validate_coefficient_candidate(
    candidate: ResolvedCoefficientContextCandidate,
    command: OrchestrationRequestCommand,
    frozen_criteria: FrozenCoefficientResolutionCriteria,
) -> None:
    """P0-5: Validate that the resolved coefficient candidate is authoritative.

    The caller must not self-attest approval — the resolver must return
    a candidate whose identity fields match the command and whose content
    hash is self-consistent.

    Checks:
      - project_id / project_version_id match command
      - content_hash == result_hash(content)
      - approved_revision_ids non-empty, no duplicates
      - schema_version supported
      - content schema_version matches typed schema_version
      - content identity fields match typed fields
      - coefficients is a list, coefficient_count matches
      - each coefficient item is a mapping with required fields
      - code, definition_id, revision_id are unique
      - approved_revision_ids matches content revision IDs exactly (order + set)
      - items in canonical order (by code then revision_id)
    """
    # Identity match
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

    # Content hash self-consistency
    if candidate.content_hash != result_hash(candidate.content):
        raise CoefficientResolutionError(
            "hash",
            f"Content hash mismatch: candidate claims {candidate.content_hash!r}, "
            f"computed {result_hash(candidate.content)!r}",
        )

    # Schema version support
    if candidate.schema_version not in _SUPPORTED_COEFFICIENT_SCHEMA_VERSIONS:
        raise CoefficientResolutionError(
            "schema",
            f"Unsupported coefficient schema version {candidate.schema_version!r}",
        )

    # Content schema_version must match typed schema_version
    content_schema = candidate.content.get("schema_version")
    if content_schema is not None and content_schema != candidate.schema_version:
        raise CoefficientResolutionError(
            "schema",
            f"Content schema_version {content_schema!r} != typed {candidate.schema_version!r}",
        )

    # Approved revision IDs validation
    if not candidate.approved_revision_ids:
        raise CoefficientNotApprovedError("empty_approved_revisions")
    if len(candidate.approved_revision_ids) != len(set(candidate.approved_revision_ids)):
        raise AmbiguousCoefficientError("duplicate_approved_revisions")

    # Content identity fields must match typed fields
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

    # ── Structural integrity checks ──────────────────────────────────
    _validate_coefficient_content_structure(candidate)

    # ── Audit fields: verify requirement registry reference ──────────
    # ALL 4 requirement metadata fields are MANDATORY — no skip-on-missing.

    # 1. requirement_registry_version
    content_req_version = candidate.content.get("requirement_registry_version")
    if not isinstance(content_req_version, str) or not content_req_version.strip():
        raise CoefficientResolutionError(
            "mismatch",
            "Content requirement_registry_version is missing or not a non-empty string",
        )
    if content_req_version != frozen_criteria.requirement_registry_version:
        raise CoefficientResolutionError(
            "mismatch",
            f"Content requirement_registry_version {content_req_version!r} != "
            f"frozen {frozen_criteria.requirement_registry_version!r}",
        )

    # 2. calculator_version_vector
    content_calc_vec = candidate.content.get("calculator_version_vector")
    if not isinstance(content_calc_vec, Mapping):
        raise CoefficientResolutionError(
            "mismatch",
            f"Content calculator_version_vector must be a Mapping, "
            f"got {type(content_calc_vec).__name__}",
        )
    for k, v in content_calc_vec.items():
        if not isinstance(k, str) or not k.strip():
            raise CoefficientResolutionError(
                "mismatch",
                f"Content calculator_version_vector has non-string or blank key: {k!r}",
            )
        if not isinstance(v, str) or not v.strip():
            raise CoefficientResolutionError(
                "mismatch",
                f"Content calculator_version_vector[{k!r}] has non-string or blank value: {v!r}",
            )
    frozen_vec = dict(frozen_criteria.calculator_version_vector)
    if dict(content_calc_vec) != frozen_vec:
        raise CoefficientResolutionError(
            "mismatch",
            f"Content calculator_version_vector {dict(content_calc_vec)!r} != "
            f"frozen {frozen_vec!r}",
        )

    # 3. required_codes
    content_req_codes = candidate.content.get("required_codes")
    if not isinstance(content_req_codes, (list, tuple)):
        raise CoefficientResolutionError(
            "mismatch",
            f"Content required_codes must be list or tuple, got {type(content_req_codes).__name__}",
        )
    validated_codes = validate_required_codes(
        content_req_codes, field_name="content_required_codes"
    )
    if validated_codes != frozen_criteria.required_codes:
        raise CoefficientResolutionError(
            "mismatch",
            f"Content required_codes {list(validated_codes)!r} != "
            f"frozen {list(frozen_criteria.required_codes)!r}",
        )

    # 4. requirement_hash — dual binding
    #    (a) Verify frozen criteria itself is self-consistent
    #    (b) Verify candidate content matches frozen criteria exactly
    content_req_hash = candidate.content.get("requirement_hash")
    if not isinstance(content_req_hash, str) or not content_req_hash.strip():
        raise CoefficientResolutionError(
            "mismatch",
            "Content requirement_hash is missing or not a non-empty string",
        )
    recomputed = result_hash(
        {
            "registry_version": frozen_criteria.requirement_registry_version,
            "calculator_version_vector": dict(frozen_criteria.calculator_version_vector),
            "required_codes": list(frozen_criteria.required_codes),
        }
    )
    if frozen_criteria.requirement_hash != recomputed:
        raise CoefficientResolutionError(
            "criteria_integrity",
            "Frozen requirement_hash is inconsistent with frozen requirement metadata",
        )
    if content_req_hash != frozen_criteria.requirement_hash:
        raise CoefficientResolutionError(
            "mismatch",
            f"Candidate requirement_hash {content_req_hash!r}"
            f" != frozen {frozen_criteria.requirement_hash!r}",
        )


def _validate_coefficient_content_structure(
    candidate: ResolvedCoefficientContextCandidate,
) -> None:
    """Verify that the coefficient content has correct structure.

    Checks coefficient list type, count, item structure, field uniqueness,
    and that approved_revision_ids matches content revision IDs exactly.
    """

    content = candidate.content

    # coefficients must be a list
    coefficients = content.get("coefficients")
    if not isinstance(coefficients, list):
        raise CoefficientResolutionError(
            "structure",
            f"coefficients must be a list, got {type(coefficients).__name__}",
        )

    # coefficient_count must match
    expected_count = len(coefficients)
    declared_count = content.get("coefficient_count")
    if declared_count != expected_count:
        raise CoefficientResolutionError(
            "structure",
            f"coefficient_count {declared_count!r} != len(coefficients) {expected_count}",
        )

    if expected_count == 0:
        raise CoefficientNotApprovedError("empty_coefficients_list")

    # Each item must be a mapping with required fields
    codes: set[str] = set()
    def_ids: set[str] = set()
    rev_ids: list[str] = []

    for i, item in enumerate(coefficients):
        if not isinstance(item, dict):
            raise CoefficientResolutionError(
                "structure",
                f"coefficient item [{i}] must be a mapping, got {type(item).__name__}",
            )

        code = item.get("code")
        if not isinstance(code, str) or not code.strip():
            raise CoefficientResolutionError(
                "structure",
                f"coefficient item [{i}] missing or invalid 'code' field",
            )
        if code in codes:
            raise CoefficientResolutionError(
                "structure",
                f"Duplicate coefficient code {code!r} at item [{i}]",
            )
        codes.add(code)

        def_id = item.get("definition_id")
        if not isinstance(def_id, str) or not def_id.strip():
            raise CoefficientResolutionError(
                "structure",
                f"coefficient item [{i}] missing or invalid 'definition_id' field",
            )
        if def_id in def_ids:
            raise CoefficientResolutionError(
                "structure",
                f"Duplicate definition_id {def_id!r} at item [{i}]",
            )
        def_ids.add(def_id)

        rev_id = item.get("revision_id")
        if not isinstance(rev_id, str) or not rev_id.strip():
            raise CoefficientResolutionError(
                "structure",
                f"coefficient item [{i}] missing or invalid 'revision_id' field",
            )
        rev_ids.append(str(rev_id))

    # No duplicate revision IDs
    if len(rev_ids) != len(set(rev_ids)):
        raise CoefficientResolutionError(
            "structure",
            "Duplicate revision_id in coefficient items",
        )

    # approved_revision_ids must match content revision IDs exactly
    content_revision_ids = canonical_revision_ids(coefficients)
    if candidate.approved_revision_ids != content_revision_ids:
        raise CoefficientResolutionError(
            "mismatch",
            f"approved_revision_ids {candidate.approved_revision_ids!r} != "
            f"content revision_ids {content_revision_ids!r}",
        )

    # Items must be in canonical order
    sorted_items = sorted(coefficients, key=coefficient_item_sort_key)
    if coefficients != sorted_items:
        raise CoefficientResolutionError(
            "structure",
            "Coefficient items are not in canonical order (by code then revision_id)",
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
