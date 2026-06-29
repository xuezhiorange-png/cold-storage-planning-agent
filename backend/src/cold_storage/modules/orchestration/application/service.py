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

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.coefficient_contracts import (
    FrozenCoefficientResolutionCriteria,
    canonical_revision_ids,
    coefficient_item_sort_key,
    derive_required_codes_for_version_vector,
    validate_required_codes,
)
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
                result = self._transaction_a(command, uow)
                uow.commit()
                return result
            except TransactionRejected as rejected:
                self._transaction_rejection(rejected.request_id, rejected.domain_error, uow)
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
        _validate_coefficient_candidate(resolved_coeff, command)

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
            request_id=ctx.request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
        )

        return PreflightAccepted(ctx.request_id, ctx.request_fingerprint, identity_id, attempt_id)

    # ── Transaction C: attempt → terminal ───────────────────────────────

    def mark_attempt_blocked(
        self,
        attempt_id: str,
        *,
        failure_code: str,
        failure_details: dict[str, object],
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
        self,
        attempt_id: str,
        *,
        failure_code: str,
        failure_details: dict[str, object],
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
        # Check all values are equivalent
        if len(set(str(v) for v in values_seen)) > 1:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller context aliases for {primary_key!r} disagree: "
                f"{dict((a, caller_ctx.get(a)) for a in aliases if a in caller_ctx)}",
            )
    return found_value


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
    if caller_zt is not None and zone_types:
        if isinstance(caller_zt, str):
            caller_zt_list = [caller_zt.strip()]
        elif isinstance(caller_zt, (list, tuple)):
            caller_zt_list = [str(z).strip() for z in caller_zt if isinstance(z, str) and z.strip()]
        else:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller zone_type must be str or list, got {type(caller_zt).__name__}",
            )
        frozen_zt = sorted(zone_types)
        if sorted(caller_zt_list) != frozen_zt:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller zone_types {sorted(caller_zt_list)!r} != frozen {frozen_zt!r}",
            )

    # Process type conflict
    caller_pr = _extract_caller_value(caller_ctx, "process_type")
    if caller_pr is not None and process_types:
        if isinstance(caller_pr, str):
            caller_pr_list = [caller_pr.strip()]
        elif isinstance(caller_pr, (list, tuple)):
            caller_pr_list = [str(p).strip() for p in caller_pr if isinstance(p, str) and p.strip()]
        else:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller process_type must be str or list, got {type(caller_pr).__name__}",
            )
        frozen_pr = sorted(process_types)
        if sorted(caller_pr_list) != frozen_pr:
            raise CoefficientResolutionError(
                "criteria_conflict",
                f"Caller process_types {sorted(caller_pr_list)!r} != frozen {frozen_pr!r}",
            )

    # Required codes conflict
    caller_req = _extract_caller_value(caller_ctx, "required_codes")
    if caller_req is not None and required_codes:
        if isinstance(caller_req, (list, tuple)):
            validated = validate_required_codes(caller_req, field_name="caller_required_codes")
            frozen_set = set(required_codes)
            caller_set = set(validated)
            if caller_set != frozen_set:
                raise CoefficientResolutionError(
                    "criteria_conflict",
                    f"Caller required_codes {sorted(caller_set)!r}"
                    f" != frozen {sorted(frozen_set)!r}",
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
    if isinstance(raw_pt, str) and raw_pt.strip():
        product_type = raw_pt.strip()

    # ── Zone types from snapshot ────────────────────────────────────────
    zone_types: tuple[str, ...] = ()
    raw_zt = input_snapshot.get("zone_types")
    if isinstance(raw_zt, list):
        zone_types = tuple(str(z) for z in raw_zt if isinstance(z, str) and z.strip())

    # ── Process types from snapshot ─────────────────────────────────────
    process_types: tuple[str, ...] = ()
    raw_pr = input_snapshot.get("process_types")
    if isinstance(raw_pr, list):
        process_types = tuple(str(p) for p in raw_pr if isinstance(p, str) and p.strip())

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
        required_codes=required_codes,
    )


def _validate_coefficient_candidate(
    candidate: ResolvedCoefficientContextCandidate,
    command: OrchestrationRequestCommand,
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
    content_req_version = candidate.content.get("requirement_registry_version")
    if content_req_version is not None and content_req_version != _REQUIREMENT_REGISTRY_VERSION:
        raise CoefficientResolutionError(
            "mismatch",
            f"Content requirement_registry_version {content_req_version!r} != "
            f"service {_REQUIREMENT_REGISTRY_VERSION!r}",
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
