"""Task 11B Phase 3 — production SourceBinding assembly use case.

The use case is the **application-level entry point** that drives
``OrchestrationService`` end-to-end through Transaction A and
Transaction B using the Phase 2 adapter ports.  It is the single
caller-facing surface that proves Phase 2's ports are wired into
the production path.

Why a dedicated use case
========================

* ``OrchestrationService`` exposes two separate entry points
  (``execute`` for Transaction A, ``execute_transaction_b`` for
  Transaction B).  Both are needed to drive a real production
  attempt.
* Test code that needs an end-to-end production attempt
  (5 ``CalculationRunRecord`` + 1 ``SourceBindingRecord``) needs
  the two-step wiring done correctly — request creation,
  identity / attempt creation, snapshot / coefficient loading,
  then Transaction B execution.
* Phase 2 left the production calculator wiring (the
  :class:`Phase2AdapterCalculatorPort`) as a separate, swappable port
  implementation.  The use case binds ``OrchestrationService``
  to the Phase 2 port so any caller using the use case gets
  Phase 2's adapters by default.

Fail-closed contract
====================

* The use case does not fabricate a ``SourceBinding`` row.  The
  binding is produced by ``TransactionBExecutor`` only after the
  five CalculationRuns are committed and the
  ``SourceBindingVerifier`` re-verifies every invariant.
* The use case does not invent calculator outputs.  Every stage
  result comes from the corresponding Phase 2 adapter
  (production calculators, no mocks, no fixtures, no
  ``SourceSnapshotContentV1`` payloads hand-written).
* The use case does not bypass the ``CalculatorPort`` —
  ``OrchestrationService.execute_transaction_b`` is the only
  path it can call.
* The use case does not write directly to ``CalculationRunRecord``,
  ``SourceBindingRecord``, or ``SourceArchiveRecord``.  Those
  writes are owned by the underlying ``TransactionBExecutor`` and
  the production ``SchemeService`` consumer.
* The use case propagates ``TransactionBFailure`` and
  ``OrchestrationDomainError`` unchanged.  The caller is
  responsible for rolling back its session.
* The use case re-reads the orchestration fingerprint from the
  durable ``OrchestrationIdentityRecord`` (via
  ``VerificationReadPort``).  It never accepts a hand-typed
  fingerprint from the caller — the fingerprint is derived
  from the persisted state, not from the caller's memory of how
  Transaction A computed it.

Out of scope for Phase 3
========================

* Running ``SchemeService`` after the binding is created.
  ``ProductionSourceBindingUseCase`` returns the verified
  ``SourceBindingRecord.id``; a separate consumer (the
  ``SchemeService`` E2E test) is responsible for feeding it into
  the production ``SchemeService``.  This split keeps the use
  case single-purpose: assemble + verify, do not score.
* Approved non-demo coefficient governance.
* Task 11 Phase B resumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from cold_storage.modules.orchestration.application.service import OrchestrationService
from cold_storage.modules.orchestration.application.transaction_b import (
    VerificationReadPort,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
)


def _load_orchestration_fingerprint(
    *,
    session: Any,
    identity_id: str,
) -> str:
    """Read the orchestration fingerprint from the durable identity row.

    The fingerprint is the single source of truth for the
    orchestrator's ``orchestration_fingerprint`` argument; it is
    computed once during Transaction A and persisted on the
    ``OrchestrationIdentityRecord``.  We read it back here so
    the caller does not have to trust its own memory of the
    Transaction A computation.

    The read goes through SQLAlchemy Core (``select``) — not
    through :class:`VerificationReadPort.load_verification_state`
    — because that helper's 5-CalRun invariant is for the
    post-Transaction-B verifier, not for the pre-Transaction-B
    fingerprint lookup.
    """
    from cold_storage.modules.orchestration.infrastructure.orm import (
        OrchestrationIdentityRecord,
    )

    record = session.execute(
        select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == identity_id)
    ).scalar_one_or_none()
    if record is None:
        return ""
    return record.fingerprint or ""


def _decimalize_for_hash(value: object) -> object:
    """Recursively convert ``float`` leaves to ``Decimal``.

    The orchestrator's canonical-JSON helper rejects binary
    ``float`` and only accepts ``Decimal``.  This is the
    boundary the use case applies to the caller-supplied
    ``execution_snapshot_payload`` and
    ``coefficient_context_payload`` before handing them to the
    orchestrator.  Production callers in real deployments
    already produce ``Decimal`` payloads, but the test
    fixtures often start from ``float`` literals — the helper
    bridges the two without changing the production contract.
    """
    from decimal import Decimal as _D

    if isinstance(value, float):
        return _D(str(value))
    if isinstance(value, dict):
        return {k: _decimalize_for_hash(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decimalize_for_hash(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_decimalize_for_hash(v) for v in value)
    return value


@dataclass(frozen=True, slots=True)
class ProductionSourceBindingOutcome:
    """Result of a single production SourceBinding assembly run.

    ``source_binding_id`` is the verified binding produced by
    Transaction B.  ``attempt_id`` / ``identity_id`` /
    ``request_id`` are the durable request / identity / attempt
    rows the binding is anchored to.  ``requires_review`` is
    propagated verbatim from the calculator verdict — the use
    case never flips it to ``False``.
    """

    request_id: str
    identity_id: str
    attempt_id: str
    source_binding_id: str
    requires_review: bool


class ProductionSourceBindingUseCase:
    """Application-level use case for production SourceBinding assembly.

    The use case is constructed once with a fully-wired
    :class:`OrchestrationService` and the
    :class:`VerificationReadPort` the service uses internally.
    It exposes a single :meth:`run` method that drives
    Transaction A + Transaction B end-to-end.
    """

    def __init__(
        self,
        *,
        service: OrchestrationService,
        verification_read_port: VerificationReadPort,
    ) -> None:
        self._service = service
        self._verification_read_port = verification_read_port

    def run(
        self,
        session: Any,
        /,
        *,
        command: OrchestrationRequestCommand,
        execution_snapshot_payload: dict[str, Any],
        coefficient_context_payload: dict[str, Any],
        execution_snapshot_id: str,
        coefficient_context_id: str,
    ) -> ProductionSourceBindingOutcome:
        """Run Transaction A + Transaction B for a real production attempt.

        ``execution_snapshot_payload`` and
        ``coefficient_context_payload`` are the verbatim dicts the
        calculators consume — they originate from the approved
        project version's input snapshot, never from evaluation
        fixtures or hand-written demo records.

        ``execution_snapshot_id`` and ``coefficient_context_id``
        are the durable ``OrchestrationExecutionSnapshotRecord``
        and ``OrchestrationCoefficientContextRecord`` ids that
        Transaction A produced.  The use case does not look them
        up — the caller supplies them so the contract is
        explicit and the test fixtures can stay deterministic.

        The caller is expected to manage the surrounding session
        lifecycle (``session.begin()`` / ``session.commit()`` /
        ``session.rollback()``) per the production UoW contract.
        """
        # Transaction A: preflight + identity + attempt.  This
        # call owns its own UoW (begins / commits / closes) via
        # the service's UoW factory.
        accepted = self._service.execute(command)

        # Re-read the orchestration fingerprint from the durable
        # identity row.  This is the production read path: the
        # fingerprint is whatever the identity row says it is,
        # not whatever the caller typed.  We deliberately avoid
        # ``VerificationReadPort.load_verification_state`` here
        # because that helper's fail-closed 5-CalRun invariant
        # is meant for the post-Transaction-B verifier, not for
        # pre-Transaction-B fingerprint lookup.  The fingerprint
        # is read directly from the
        # ``OrchestrationIdentityRecord`` row.
        fingerprint = _load_orchestration_fingerprint(
            session=session,
            identity_id=accepted.identity_id,
        )
        if not fingerprint:
            raise RuntimeError(
                f"Identity {accepted.identity_id!r} has an empty "
                f"fingerprint — production state is inconsistent; "
                f"refusing to run Transaction B"
            )

        # Transaction B: five-stage calculator execution.
        # The orchestrator's canonical-JSON helper rejects binary
        # ``float``; normalise the caller-supplied payloads to
        # ``Decimal`` at the use case boundary so production
        # callers (which already produce ``Decimal``) and test
        # fixtures (which often start from ``float``) share a
        # single contract.
        result = self._service.execute_transaction_b(
            request_id=accepted.request_id,
            project_id=command.project_id,
            project_version_id=command.project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=accepted.identity_id,
            orchestration_attempt_id=accepted.attempt_id,
            orchestration_fingerprint=fingerprint,
            execution_snapshot=_decimalize_for_hash(  # type: ignore[arg-type]
                execution_snapshot_payload
            ),
            coefficient_context=_decimalize_for_hash(  # type: ignore[arg-type]
                coefficient_context_payload
            ),
        )

        if result.source_binding_id is None:
            raise RuntimeError(
                "Transaction B returned OrchestrationResult without "
                "a SourceBinding id — production verifier accepted "
                "the five CalculationRuns but the binding was not "
                "persisted; refusing to return a half-completed "
                "outcome"
            )

        return ProductionSourceBindingOutcome(
            request_id=accepted.request_id,
            identity_id=accepted.identity_id,
            attempt_id=accepted.attempt_id,
            source_binding_id=result.source_binding_id,
            requires_review=bool(result.requires_review),
        )


__all__ = [
    "ProductionSourceBindingOutcome",
    "ProductionSourceBindingUseCase",
]
