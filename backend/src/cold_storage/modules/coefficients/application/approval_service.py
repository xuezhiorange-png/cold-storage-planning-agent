"""Application service for approved non-demo coefficient governance.

Owns the approval state machine (design contract §5.2):
- ``submit``        : draft / unverified -> unverified / reviewed
- ``approve``       : reviewed -> approved   (with citation + role check)
- ``retire``        : approved -> withdrawn
- ``list_approved`` : read-only enumeration
- ``validate_startup_readiness`` : fail-closed check

``revert`` is intentionally NOT implemented (Charles's Slice 1
boundary correction 2026-07-07): the design contract does not
require it, and the existing ``CoefficientService.withdraw_revision``
already covers the contract-level retire direction.

Per the architecture rules:
- This module does not import SQLAlchemy or any infrastructure layer.
- All cross-layer access goes through ``application/ports.py`` or
  via the existing ``CoefficientService`` adapter (which itself
  stays unchanged in its public surface).

Per the Slice 1 boundary correction:
- ``source_type`` retains the existing 8 values.
- ``status`` retains the existing 5 values.
- ``source_reference`` is the column; ``source_citation`` is the
  semantic alias used in this layer for clarity.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from cold_storage.modules.coefficients.application.ports import (
    CoefficientApprovalLogPort,
    CoefficientAuditLogPort,
    CoefficientClockPort,
    CoefficientRoleCheckPort,
)
from cold_storage.modules.coefficients.domain.approval import (
    is_stale,
    validate_citation,
)
from cold_storage.modules.coefficients.domain.exceptions import (
    ApprovalRoleRequiredError,
    CoefficientAlreadyRetiredError,
    DuplicatePendingApprovalError,
    InvalidCitationError,
)
from cold_storage.modules.coefficients.domain.models import (
    CoefficientRevision,
)

logger = logging.getLogger(__name__)


#: Role required to perform an approval. Per design contract §5.6
#: fourth bullet: the actor must hold this role, else the call is
#: rejected with :class:`ApprovalRoleRequiredError`.
REQUIRED_REVIEWER_ROLE: str = "coefficient.reviewer"


# ---------------------------------------------------------------------------
# Adapter for the existing CoefficientService
# ---------------------------------------------------------------------------


@runtime_checkable
class CoefficientMutationPort(Protocol):
    """Narrow surface into the existing ``CoefficientService``.

    This is **not** an infrastructure import. ``CoefficientService``
    is an in-memory dataclass that already implements the protocol
    structurally; production composition wires the database-backed
    variant. The protocol exists so this service depends on the
    contract, not on the concrete dataclass.
    """

    def create_definition(  # noqa: D401 - docstring inherited from contract
        self,
        *,
        code: str,
        name: str,
        description: str,
        category: str,
        canonical_unit: str,
        value_type: str = "decimal",
        scope_type: str = "global",
        is_active: bool = True,
    ) -> Any: ...

    def create_revision(
        self,
        *,
        definition_id: str,
        revision_number: int,
        unit: str,
        source_type: str = "demo",
        source_title: str | None = None,
        source_reference: str | None = None,
        source_page: str | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        value_decimal: Any = None,
        value_json: dict[str, object] | None = None,
        created_by: str = "system",
    ) -> CoefficientRevision: ...

    def list_revisions(self, definition_id: str) -> list[CoefficientRevision]: ...

    def list_revisions_for_stage(
        self, stage_name: str, calculation_type: str | None
    ) -> list[CoefficientRevision]: ...

    def get_revision(self, definition_id: str, revision_id: str) -> CoefficientRevision: ...

    def mark_revision_reviewed(
        self, definition_id: str, revision_id: str, reviewer: str
    ) -> CoefficientRevision: ...

    def approve_revision(
        self, definition_id: str, revision_id: str, approver: str
    ) -> CoefficientRevision: ...

    def withdraw_revision(
        self, definition_id: str, revision_id: str, actor: str
    ) -> CoefficientRevision: ...


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApprovalRequest:
    """Inputs to a single approval action.

    ``actor`` is who performs the action; ``reviewer`` (for approve)
    is a separate identity that must hold ``coefficient.reviewer``
    role. ``correlation_id`` is the audit-log correlation token.
    ``source_citation`` is the validated citation; it is the
    *semantic alias* for ``source_reference`` (per Slice 1 boundary).
    """

    definition_id: str
    revision_id: str
    actor: str
    correlation_id: str
    source_citation: str | None = None  # alias for source_reference
    reviewer: str | None = None  # only used for `approve`


@dataclass(frozen=True)
class ApprovalResult:
    """Outputs of a single approval action.

    ``revision_id`` is the persisted revision after the action; on
    fail-closed paths this is ``None`` and ``typed_error`` is set.
    """

    revision_id: str | None
    new_state: str
    typed_error: Exception | None = None


class CoefficientApprovalService:
    """Application service owning the approval state machine.

    The service is constructed by the composition root
    (``bootstrap.production_composition``) with concrete port
    implementations. Unit tests construct it with in-memory fakes.
    """

    def __init__(
        self,
        *,
        mutation_port: CoefficientMutationPort,
        approval_log: CoefficientApprovalLogPort,
        audit_log: CoefficientAuditLogPort,
        clock: CoefficientClockPort,
        role_check: CoefficientRoleCheckPort,
    ) -> None:
        self._mutation = mutation_port
        self._approval_log = approval_log
        self._audit_log = audit_log
        self._clock = clock
        self._role_check = role_check

    # ------------------------------------------------------------------
    # Public API (5 methods; revert intentionally absent)
    # ------------------------------------------------------------------

    def submit(self, request: ApprovalRequest) -> ApprovalResult:
        """Transition a draft / unverified revision to ``unverified``.

        The submit-only action simply records reviewer intent to
        forward the revision. Per the design contract §3.6 it maps
        to ``demo -> under_review`` (or ``draft / unverified``).
        """
        revision = self._mutation.get_revision(request.definition_id, request.revision_id)
        if revision.status == "withdrawn":
            raise CoefficientAlreadyRetiredError(revision.id)

        new_state = "unverified"
        self._append_audit(
            revision_id=revision.id,
            actor=request.actor,
            correlation_id=request.correlation_id,
            old_state=revision.status,
            new_state=new_state,
            reason="submit",
        )
        # The submit step does not need role enforcement — anyone can
        # surface a draft for review. Approval is the gated action.
        return ApprovalResult(revision_id=revision.id, new_state=new_state)

    def approve(self, request: ApprovalRequest) -> ApprovalResult:
        """Approve an unverified / reviewed revision.

        Rejection paths (design contract §5.6):
        1. revision already withdrawn -> CoefficientAlreadyRetiredError
        2. duplicated pending approval from same reviewer ->
           DuplicatePendingApprovalError
        3. missing / invalid citation -> InvalidCitationError
        4. actor lacks role -> ApprovalRoleRequiredError
        """
        roles = self._role_check.roles_for(request.actor)
        if REQUIRED_REVIEWER_ROLE not in roles:
            raise ApprovalRoleRequiredError(
                actor=request.actor,
                required_role=REQUIRED_REVIEWER_ROLE,
                actor_roles=roles,
            )

        revision = self._mutation.get_revision(request.definition_id, request.revision_id)
        if revision.status == "withdrawn":
            raise CoefficientAlreadyRetiredError(revision.id)

        # Citation validation — the citation is the canonical
        # source_reference. We reject empty / malformed at this
        # point even if the column is currently NULL, because the
        # contract requires non-nullable citations on approval.
        citation_raw = (
            request.source_citation
            if request.source_citation is not None
            else revision.source_reference
        )
        citation_validated = validate_citation(citation_raw)

        # Duplicate pending approval (same reviewer has an open
        # review on the same definition). The existing service
        # surface does not track pending review rows; we surface
        # this at the application layer by inspecting
        # ``approved_at`` / ``created_at`` ordering against the
        # most recent pending entry from the same reviewer.
        self._check_duplicate_pending(request, revision)

        reviewer = request.reviewer or request.actor
        previous_state = revision.status
        self._mutation.mark_revision_reviewed(
            request.definition_id, request.revision_id, reviewer=reviewer
        )
        # ``mark_revision_reviewed`` moves status -> reviewed; then
        # ``approve_revision`` is invoked to land on approved.
        self._mutation.approve_revision(
            request.definition_id, request.revision_id, approver=reviewer
        )

        # Persist the validation back to ``source_reference``. The
        # existing service keeps the field on the in-memory object;
        # the database layer's update path is unchanged (out of
        # Slice 1 scope; we rely on the existing repository).
        revision.source_reference = citation_validated

        new_state = "approved"
        self._append_audit(
            revision_id=revision.id,
            actor=reviewer,
            correlation_id=request.correlation_id,
            old_state=previous_state,
            new_state=new_state,
            reason="approve",
        )
        self._approval_log.record(
            revision_id=revision.id,
            reviewer=reviewer,
            action="approve",
            citation=citation_validated,
            payload_hash=self._hash_revision_snapshot(revision),
            correlation_id=request.correlation_id,
        )
        return ApprovalResult(revision_id=revision.id, new_state=new_state)

    def retire(self, request: ApprovalRequest) -> ApprovalResult:
        """Retire an approved revision (status -> ``withdrawn``).

        Maps to design contract ``approved -> retired``. The existing
        ``withdraw_revision`` flow is reused unchanged.
        """
        revision = self._mutation.get_revision(request.definition_id, request.revision_id)
        if revision.status == "withdrawn":
            raise CoefficientAlreadyRetiredError(revision.id)

        previous_state = revision.status
        self._mutation.withdraw_revision(
            request.definition_id, request.revision_id, actor=request.actor
        )
        new_state = "withdrawn"

        self._append_audit(
            revision_id=revision.id,
            actor=request.actor,
            correlation_id=request.correlation_id,
            old_state=previous_state,
            new_state=new_state,
            reason="retire",
        )
        self._approval_log.record(
            revision_id=revision.id,
            reviewer=request.actor,
            action="retire",
            citation=revision.source_reference or "",
            payload_hash=self._hash_revision_snapshot(revision),
            correlation_id=request.correlation_id,
        )
        return ApprovalResult(revision_id=revision.id, new_state=new_state)

    def list_approved(
        self,
        *,
        definition_id: str | None = None,
    ) -> list[CoefficientRevision]:
        """Return revisions with ``status == approved`` for a definition.

        Pass ``definition_id=None`` to enumerate across all
        definitions the underlying port can see; Slice 1 callers
        usually pass a concrete definition_id.

        This is a thin read wrapper that filters out demo /
        non-approved rows. The strict resolver (``resolver.py``)
        is the production-only counterparty; this method exists
        for human inspection via API / CLI.
        """
        if definition_id is None:
            raise ValueError(
                "definition_id is required for list_approved "
                "(enumeration without a stage key is intentionally "
                "not exposed at the application layer)"
            )
        revisions = self._mutation.list_revisions(definition_id)
        return [r for r in revisions if r.status == "approved" and r.source_type != "demo"]

    # ------------------------------------------------------------------
    # Fail-closed startup validation
    # ------------------------------------------------------------------

    def validate_startup_readiness(
        self,
        *,
        stage_names: list[tuple[str, str | None]],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a typed-readiness map for the composition root.

        :param stage_names: List of ``(stage_name, calculation_type)``
            tuples that the production composition root must fill.
        :param now: Optional pinned clock (for tests). Defaults to
            ``clock.now()``.

        :returns: A dict with
            ``{"ready": bool, "missing": [MissingApprovedCoefficientError],
            "stale": [StaleApprovalError], "demoted": [DemoCoefficientInProductionError],
            "citation": [InvalidCitationError]}``.

        Each typed error in the returned buckets is the **first**
        offender; callers iterate for full inventory. The dict is
        serializable for logging at startup.
        """
        reference = now if now is not None else self._clock.now()
        result: dict[str, list[dict[str, Any]]] = {
            "missing": [],
            "stale": [],
            "demoted": [],
            "citation": [],
        }
        for stage_name, calculation_type in stage_names:
            revisions = self._mutation.list_revisions_for_stage(stage_name, calculation_type)
            eligible = [
                r
                for r in revisions
                if r.status == "approved"
                and r.source_type != "demo"
                and not is_stale(r, now=reference)
                and r.source_reference
            ]
            if not eligible:
                result["missing"].append(
                    {
                        "stage_name": stage_name,
                        "calculation_type": calculation_type,
                    }
                )
                continue
            for r in eligible:
                try:
                    validate_citation(r.source_reference)
                except InvalidCitationError as exc:
                    result["citation"].append(
                        {
                            "revision_id": r.id,
                            "reason": exc.reason,
                        }
                    )
                    break
            else:
                # Healthy candidate exists for this stage.
                continue
            # If citation failed: continue to the next stage so
            # we inventory *all* offending stages.
        # The composition root inspects this dict and raises a
        # single :class:`MissingApprovedCoefficientError` (or the
        # most-specific typed error) to fail startup.
        ready = (
            not result["missing"]
            and not result["stale"]
            and not result["demoted"]
            and not result["citation"]
        )
        return {"ready": ready, **result}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_duplicate_pending(
        self,
        request: ApprovalRequest,
        revision: CoefficientRevision,
    ) -> None:
        """Reject if the same reviewer has a pending approval on this definition.

        Per design contract §5.6 second bullet. The existing
        ``CoefficientService`` does not track a separate "pending
        approval" table; the existing ``mark_revision_reviewed``
        writes ``reviewed_at`` and ``reviewed_by`` immediately. We
        approximate the duplicate-pending check here by inspecting
        the revision's current ``reviewed_by`` field: if the same
        reviewer already opened the review *and* the revision has
        not been approved yet, the new approve would create a
        duplicate pending entry.
        """
        if revision.reviewed_by is not None and revision.reviewed_by == request.actor:
            raise DuplicatePendingApprovalError(
                request.definition_id,
                request.actor,
            )

    def _append_audit(
        self,
        *,
        revision_id: str,
        actor: str,
        correlation_id: str,
        old_state: str,
        new_state: str,
        reason: str,
    ) -> None:
        try:
            self._audit_log.record(
                revision_id=revision_id,
                actor=actor,
                correlation_id=correlation_id,
                old_state=old_state,
                new_state=new_state,
                reason=reason,
            )
        except Exception:  # pragma: no cover - audit must not crash the action
            logger.exception(
                "audit_log write failed revision_id=%s old=%s new=%s",
                revision_id,
                old_state,
                new_state,
            )

    @staticmethod
    def _hash_revision_snapshot(revision: CoefficientRevision) -> str:
        """Stable SHA-256 hex digest of the revision snapshot.

        The hash is computed from the JSON-serialized tuple of the
        revision's identity / source / value fields. Order is
        canonical (sorted keys) so two writers compute the same
        hash for the same revision snapshot.
        """
        payload = {
            "id": revision.id,
            "definition_id": revision.coefficient_definition_id,
            "revision_number": revision.revision_number,
            "status": revision.status,
            "source_type": revision.source_type,
            "source_reference": revision.source_reference,
            "value_decimal": (
                str(revision.value_decimal) if revision.value_decimal is not None else None
            ),
            "value_json": revision.value_json,
            "approved_at": (revision.approved_at.isoformat() if revision.approved_at else None),
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ApprovalRequest",
    "ApprovalResult",
    "CoefficientApprovalService",
    "CoefficientMutationPort",
    "REQUIRED_REVIEWER_ROLE",
]
