"""Domain exceptions for the coefficient registry."""

from __future__ import annotations


class CoefficientDomainError(Exception):
    """Base exception for all coefficient domain errors."""


class CoefficientNotFoundError(CoefficientDomainError):
    """Raised when a coefficient definition or revision is not found."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"Coefficient not found: {identifier}")


class DuplicateCoefficientCodeError(CoefficientDomainError):
    """Raised when attempting to create a definition with a duplicate code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Coefficient code already exists: {code}")


class DuplicateRevisionNumberError(CoefficientDomainError):
    """Raised when a revision number already exists for a definition."""

    def __init__(self, definition_id: str, revision_number: int) -> None:
        self.definition_id = definition_id
        self.revision_number = revision_number
        super().__init__(
            f"Revision {revision_number} already exists for definition {definition_id}"
        )


class InvalidRevisionTransitionError(CoefficientDomainError):
    """Raised when an invalid revision state transition is attempted."""

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid transition from '{from_status}' to '{to_status}'")


class RevisionImmutabilityError(CoefficientDomainError):
    """Raised when attempting to modify a locked (approved/withdrawn) revision."""

    def __init__(self, revision_id: str, status: str, operation: str) -> None:
        self.revision_id = revision_id
        self.status = status
        self.operation = operation
        super().__init__(
            f"Cannot {operation} on revision {revision_id} with status '{status}'. "
            f"Approved/withdrawn revisions are immutable."
        )


class SupersedesCrossDefinitionError(CoefficientDomainError):
    """Raised when supersedes_revision_id crosses definition boundaries."""

    def __init__(self, supersedes_id: str, expected_def: str, actual_def: str) -> None:
        self.supersedes_id = supersedes_id
        self.expected_definition_id = expected_def
        self.actual_definition_id = actual_def
        super().__init__(
            f"Revision supersedes {supersedes_id} belongs to definition "
            f"{actual_def}, not {expected_def}"
        )


# ---------------------------------------------------------------------------
# Phase 4 Issue #35 Slice 1 — typed errors for approved non-demo
# coefficient governance. Per Charles's Slice 1 authorization
# (2026-07-07): append-only, no existing class is replaced.
# ---------------------------------------------------------------------------


class ApprovedCoefficientGovernanceError(CoefficientDomainError):
    """Base class for all Phase 4 Slice 1 approved-coefficient errors.

    All Slice 1 governance errors are typed errors (per design contract
    §5 / §7). Tests and startup-validation paths distinguish by class,
    never by message text.
    """


class MissingApprovedCoefficientError(ApprovedCoefficientGovernanceError):
    """Raised when a required approved non-demo coefficient is absent.

    Per design contract §5.3 + §7 (no demo fallback) + §8.1: the
    fail-closed startup path raises this typed error when a required
    stage has no ``status == approved`` revision with a non-demo
    ``source_type``.
    """

    def __init__(self, *, stage_name: str, calculation_type: str | None) -> None:
        self.stage_name = stage_name
        self.calculation_type = calculation_type
        super().__init__(
            f"No approved non-demo coefficient for stage={stage_name!r} "
            f"calculation_type={calculation_type!r}"
        )


class StaleApprovalError(ApprovedCoefficientGovernanceError):
    """Raised when the only approved coefficient is past ``valid_to``.

    Per design contract §5.4: stale approvals fail closed.
    """

    def __init__(self, revision_id: str) -> None:
        self.revision_id = revision_id
        super().__init__(f"Approved revision {revision_id} is stale (past valid_to)")


class InvalidCitationError(ApprovedCoefficientGovernanceError):
    """Raised when a citation does not match a supported pattern.

    Per design contract §5.5 + §5.6 (rejection paths).
    """

    def __init__(self, citation: str, reason: str) -> None:
        self.citation = citation
        self.reason = reason
        super().__init__(f"Invalid citation {citation!r}: {reason}")


class UnknownCitationPatternError(InvalidCitationError):
    """Raised when the citation prefix is recognized but the body is malformed.

    A specialization of :class:`InvalidCitationError` so callers can
    branch on the specific cause (prefix vs body) if they need to
    without parsing message text. Per Slice 1 authorization §4 the
    rule remains: unknown pattern fails closed.
    """


class DemoCoefficientInProductionError(ApprovedCoefficientGovernanceError):
    """Raised when a demo coefficient surfaces in a production path.

    Per design contract §7 (no demo fallback).
    """

    def __init__(self, revision_id: str, source_type: str) -> None:
        self.revision_id = revision_id
        self.source_type = source_type
        super().__init__(
            f"Revision {revision_id} uses source_type={source_type!r}; "
            "demo coefficients are not eligible in production"
        )


class PartialStageCoverageError(ApprovedCoefficientGovernanceError):
    """Raised when only a subset of required stages has approved rows.

    Per design contract §5.3 + §7 (no partial coverage). Reserved for
    multi-stage evaluation; not exercised by Slice 1 unit tests but the
    typed error is shipped so future Slices consume it directly.
    """

    def __init__(self, *, covered: list[str], missing: list[str]) -> None:
        self.covered = covered
        self.missing = missing
        super().__init__(f"Partial stage coverage: covered={covered!r} missing={missing!r}")


class AmbiguousLatestRowError(ApprovedCoefficientGovernanceError):
    """Raised when two eligible revisions tie for "latest" by ordering.

    Per design contract §7 (no latest-row fallback). Production path
    requires an explicit identity; equal-priority rows are ambiguous
    and fail closed. See also ``ApprovedCoefficientResolver`` in
    application layer for the deterministic priority resolver.
    """

    def __init__(self, *, definition_id: str, revision_ids: list[str], tie_breaker: str) -> None:
        self.definition_id = definition_id
        self.revision_ids = revision_ids
        self.tie_breaker = tie_breaker
        super().__init__(
            f"Ambiguous latest row for definition {definition_id!r}: "
            f"{len(revision_ids)} revisions tie on {tie_breaker!r} "
            f"({revision_ids!r}); production path requires explicit identity"
        )


class ApprovalRejectionError(ApprovedCoefficientGovernanceError):
    """Base class for ApprovalService rejection paths.

    Per design contract §5.6 (4 rejection paths). Each path is a
    specialized subclass below.
    """


class CoefficientAlreadyRetiredError(ApprovalRejectionError):
    """Raised when approve/revert is invoked on a withdrawn revision.

    Per design contract §5.6 first bullet.
    """

    def __init__(self, revision_id: str) -> None:
        self.revision_id = revision_id
        super().__init__(f"Revision {revision_id} is withdrawn; no further approval action")


class DuplicatePendingApprovalError(ApprovalRejectionError):
    """Raised when the same coefficient_id has a pending review from the same reviewer.

    Per design contract §5.6 second bullet.
    """

    def __init__(self, definition_id: str, reviewer: str) -> None:
        self.definition_id = definition_id
        self.reviewer = reviewer
        super().__init__(
            f"Definition {definition_id!r} already has a pending approval "
            f"from reviewer {reviewer!r}"
        )


class ApprovalRoleRequiredError(ApprovalRejectionError):
    """Raised when the actor lacks the coefficient.reviewer role.

    Per design contract §5.6 fourth bullet. ``actor_roles`` is the
    set of roles the actor carries at the call site. The transport
    layer is responsible for populating it (out of Slice 1 scope —
    see Slice 1 contract §5.6 and the deferred note).
    """

    def __init__(self, actor: str, required_role: str, actor_roles: frozenset[str]) -> None:
        self.actor = actor
        self.required_role = required_role
        self.actor_roles = actor_roles
        super().__init__(
            f"Actor {actor!r} lacks required role {required_role!r} "
            f"(actor has roles {sorted(actor_roles)})"
        )
