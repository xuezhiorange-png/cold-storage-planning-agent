"""Application-layer ports for approved non-demo coefficient governance.

These are :class:`typing.Protocol` types consumed by the application
service (``CoefficientApprovalService``) and the strict resolver
(``ApprovedCoefficientResolver``). Their concrete implementations live
in ``infrastructure.repositories`` (committed in Slice 1) and in
existing ``infrastructure.database`` adapters. Per the project
architecture rules, application-layer code does **not** import
SQLAlchemy directly; all cross-layer access goes through these
protocols.

Per Charles's Slice 1 boundary correction (2026-07-07):
- These protocols are read by ``application/`` code; only the
  ``infrastructure/`` layer implements them.
- Existing ``CoefficientService`` / ``DatabaseCoefficientService``
  are not refactored; the new types co-exist.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from cold_storage.modules.coefficients.domain.models import (
    CoefficientDefinition,
    CoefficientRevision,
)

# ---------------------------------------------------------------------------
# Approval / resolver read ports
# ---------------------------------------------------------------------------


@runtime_checkable
class CoefficientRevisionReadPort(Protocol):
    """Read-only access to coefficient revisions, indexed for resolution.

    Implementations are typically backed by ``DatabaseCoefficientService``
    (or a focused slice of it). Each method is a pure read.
    """

    def list_approved_revisions(
        self,
        *,
        stage_name: str,
        calculation_type: str | None,
    ) -> list[CoefficientRevision]:
        """Return all revisions whose definition is ``status=approved``,
        ``source_type != demo``, and that match the requested stage /
        calculation-type binding.

        Implementations MUST NOT silently filter on ``created_at`` /
        ``approved_at`` (no latest-row fallback). The application
        resolver layer applies the deterministic priority logic.
        """
        ...

    def get_definition_by_code(self, code: str) -> CoefficientDefinition:
        """Return the coefficient definition with the given code.

        :raises CoefficientNotFoundError: If the code is not registered.
        """
        ...

    def get_revision(self, definition_id: str, revision_id: str) -> CoefficientRevision:
        """Return a specific revision belonging to a definition.

        :raises CoefficientNotFoundError: If either id is unknown.
        """
        ...


@runtime_checkable
class CoefficientClockPort(Protocol):
    """Wall-clock abstraction. Tests pin a deterministic value."""

    def now(self) -> datetime:
        """Return current UTC ``datetime``."""
        ...


# ---------------------------------------------------------------------------
# Approval log ports (written by ``CoefficientApprovalService``)
# ---------------------------------------------------------------------------


@runtime_checkable
class CoefficientApprovalLogPort(Protocol):
    """Append-only approval-log writes.

    Per design contract §3.2 the approval is recorded in
    ``coefficient_approval_log`` with reviewer, timestamp, source
    citation, and a payload hash. Implementation lives in
    ``infrastructure.repositories``.
    """

    def record(
        self,
        *,
        revision_id: str,
        reviewer: str,
        action: str,
        citation: str,
        payload_hash: str,
        correlation_id: str,
    ) -> None:
        """Append a single row to the approval log.

        ``action`` is one of ``submit``, ``approve``, ``retire`` per
        the design contract. ``citation`` is the validated citation
        string (non-empty, matched pattern). ``payload_hash`` is the
        SHA-256 hex digest of the revision snapshot at write time.
        """
        ...


@runtime_checkable
class CoefficientAuditLogPort(Protocol):
    """Append-only audit-log writes for state transitions.

    Per design contract §3.3 every transition writes a row to
    ``coefficient_audit_log`` with: actor, correlation_id, old state,
    new state, timestamp, reason. The log is append-only and
    tamper-evident at the schema level (out of Slice 1 scope; the
    base schema does not yet enforce append-only — that arrives in a
    follow-up Slice together with archive persistence).

    Slice 1: write-only API, no UPDATE / DELETE path is exposed.
    """

    def record(
        self,
        *,
        revision_id: str,
        actor: str,
        correlation_id: str,
        old_state: str,
        new_state: str,
        reason: str,
    ) -> None:
        """Append a single audit row.

        ``old_state`` and ``new_state`` are revision-level ``status``
        values (existing 5 values: draft / unverified / reviewed /
        approved / withdrawn — see Slice 1 boundary correction).
        """
        ...


# ---------------------------------------------------------------------------
# Role-check port (used by §5.6 rejection paths)
# ---------------------------------------------------------------------------


@runtime_checkable
class CoefficientRoleCheckPort(Protocol):
    """Resolve the set of roles an actor carries.

    Per design contract §5.6 fourth bullet: reject approve if
    the actor lacks the ``coefficient.reviewer`` role. The
    production auth source is out of Slice 1 scope (deferred);
    this protocol is the seam the follow-up transport layer
    will populate. The default implementation
    (:class:`InMemoryRoleCheckAdapter` in
    ``infrastructure/approval_adapters.py``) returns a fixed
    role mapping for the canonical reviewer identity; tests
    construct their own adapter. The production wiring in
    ``bootstrap.production_composition`` uses the default
    implementation for Slice 1.

    Implementation note: do **not** mis-interpret "default" as
    "silent"; the production path raises
    :class:`ApprovalRoleRequiredError` (typed) when the actor
    lacks the role. The default implementation simply returns
    the empty ``frozenset()`` for unknown actors, which is
    caught by the application-side ``approve`` flow.
    """

    def roles_for(self, actor: str) -> frozenset[str]:
        """Return the actor's roles."""
        ...
