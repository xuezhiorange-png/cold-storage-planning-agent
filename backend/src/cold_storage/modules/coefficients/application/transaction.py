"""Transactional context shared between application and infrastructure.

Carries everything the application service has already computed
(role check passed, citation validated, state-machine transition
allowed, payload hash computed) so the infrastructure layer can
execute ``UPDATE coefficient_revisions`` +
``INSERT INTO coefficient_audit_log`` + ``INSERT INTO coefficient_approval_log``
in a single ``session.begin()`` without re-running business
validation.

Per Charles's Slice 1 boundary correction (2026-07-07): the
context is a passive data carrier. It carries no SQLAlchemy,
no FastAPI, no Redis, no network, no I/O. The application
service computes every field; the infrastructure
:func:`TransactionalCoefficientApprovalRepository.apply_*`
methods consume it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from cold_storage.modules.coefficients.domain.models import CoefficientRevision


def _hash_revision_snapshot(revision: CoefficientRevision) -> str:
    """Stable SHA-256 hex digest of the revision snapshot for log rows.

    Mirrors :meth:`CoefficientApprovalService._hash_revision_snapshot`
    — duplicated here so this module does not need to import from
    ``approval_service`` (which would invert the dependency
    direction: ``application.transaction`` is leaf-side and must
    not depend on ``application.approval_service``). The two
    serialisation shapes must remain byte-identical; if they ever
    diverge, snapshot hashes differ between the audit log and
    the approval log, and the deferred integration test will
    surface it.
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


@dataclass(frozen=True)
class ApprovalTransactionContext:
    """Inputs to a single atomic approval / retire / submit transition.

    Fields are populated by the application service after role
    check, citation validation, and state-machine guard have
    passed. The infrastructure layer
    (:class:`TransactionalCoefficientApprovalRepository`)
    consumes the context to issue a single ``session.begin()``
    with three writes.

    Application-layer invariants the service has already
    verified before constructing the context:

    * The actor holds the ``coefficient.reviewer`` role
      (already enforced on ``approve``).
    * The ``citation`` matches one of the three supported
      patterns (DOI / STANDARD / INTERNAL).
    * The transition
      ``old_state -> new_state`` is in
      ``VALID_REVISION_TRANSITIONS``.
    * The revision is not in
      ``status == withdrawn`` for ``approve`` /
      ``submit``.
    """

    definition_id: str
    revision_id: str
    actor: str
    correlation_id: str

    # Revision state machine
    old_state: str
    new_state: str
    reason: str

    # Action hint (the repository uses this to decide which log
    # rows to insert: "approve" writes audit-log + approval-log,
    # "retire" writes audit-log + approval-log, "submit" writes
    # audit-log only).
    action: str

    # Citation (validated, non-empty). Required for "approve";
    # optional for "submit" / "retire" (the latter carries the
    # existing citation forward).
    citation: str

    # Reviewer (defaults to actor unless overridden). Required
    # on "approve".
    reviewer: str

    # Snapshot hash for the approval-log row (commit 3 already
    # persisted one; commit 8 recomputes here so the transaction
    # scope is self-contained).
    payload_hash: str

    # Wall-clock time the application observed (used by the
    # repository to set ``approved_at`` / ``created_at`` so the
    # audit log's timestamp matches the application flow).
    observed_at: datetime

    @staticmethod
    def build_for_approve(
        *,
        revision: CoefficientRevision,
        actor: str,
        correlation_id: str,
        reviewer: str,
        citation_validated: str,
        previous_state: str,
        observed_at: datetime,
    ) -> ApprovalTransactionContext:
        """Build a context for the ``approve`` transition.

        The application service has already validated the
        citation and verified the role; this helper supplies
        the snapshot hash and the computed state transition.
        """
        return ApprovalTransactionContext(
            definition_id=revision.coefficient_definition_id,
            revision_id=revision.id,
            actor=actor,
            correlation_id=correlation_id,
            old_state=previous_state,
            new_state="approved",
            reason="approve",
            action="approve",
            citation=citation_validated,
            reviewer=reviewer,
            payload_hash=_hash_revision_snapshot(revision),
            observed_at=observed_at,
        )

    @staticmethod
    def build_for_retire(
        *,
        revision: CoefficientRevision,
        actor: str,
        correlation_id: str,
        previous_state: str,
        observed_at: datetime,
    ) -> ApprovalTransactionContext:
        """Build a context for the ``retire`` transition.

        The reviewer is the actor; the citation carries forward
        verbatim (no citation rewrite on retire).
        """
        return ApprovalTransactionContext(
            definition_id=revision.coefficient_definition_id,
            revision_id=revision.id,
            actor=actor,
            correlation_id=correlation_id,
            old_state=previous_state,
            new_state="withdrawn",
            reason="retire",
            action="retire",
            citation=revision.source_reference or "",
            reviewer=actor,
            payload_hash=_hash_revision_snapshot(revision),
            observed_at=observed_at,
        )

    @staticmethod
    def build_for_submit(
        *,
        revision: CoefficientRevision,
        actor: str,
        correlation_id: str,
        previous_state: str,
        observed_at: datetime,
    ) -> ApprovalTransactionContext:
        """Build a context for the ``submit`` transition.

        Submit writes an audit-log row only; no approval-log
        row is inserted (per design contract §5.2 — approval
        log records approve / retire only). The context is
        still shaped uniformly so the repository can use one
        helper to commit.
        """
        return ApprovalTransactionContext(
            definition_id=revision.coefficient_definition_id,
            revision_id=revision.id,
            actor=actor,
            correlation_id=correlation_id,
            old_state=previous_state,
            new_state="unverified",
            reason="submit",
            action="submit",
            citation=revision.source_reference or "",
            reviewer=actor,
            payload_hash=_hash_revision_snapshot(revision),
            observed_at=observed_at,
        )


__all__ = ["ApprovalTransactionContext"]
