"""Coefficient domain models with state machine and immutability rules.

Domain models for the coefficient registry:
- CoefficientDefinition: the canonical identity of a coefficient
- CoefficientRevision: a versioned value with governance metadata
- CoefficientValue: immutable resolved value for calculations
- CoefficientSet: immutable collection of resolved values

Rules:
- Valid revision transitions: draft→unverified, draft→reviewed,
  unverified→reviewed, reviewed→approved, approved→withdrawn
- Approved revisions cannot be modified
- Withdrawn revisions cannot be reactivated
- revision_number is unique per definition
- supersedes_revision_id cannot cross definitions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# Valid revision state transitions: frozenset of (from_state, to_state) pairs.
VALID_REVISION_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("draft", "unverified"),
        ("draft", "reviewed"),
        ("unverified", "reviewed"),
        ("reviewed", "approved"),
        ("approved", "withdrawn"),
    }
)

ALL_REVISION_STATUSES: frozenset[str] = frozenset(
    {"draft", "unverified", "reviewed", "approved", "withdrawn"}
)

ALL_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "standard",
        "book",
        "manufacturer",
        "enterprise_standard",
        "historical_project",
        "engineering_judgement",
        "demo",
        "unknown",
    }
)

ALL_SCOPE_TYPES: frozenset[str] = frozenset(
    {"global", "product", "zone", "process", "project", "project_version"}
)

ALL_VALUE_TYPES: frozenset[str] = frozenset({"decimal", "json"})

SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def new_id() -> str:
    return str(uuid4())


def validate_revision_transition(current_status: str, target_status: str) -> None:
    """Validate that a revision state transition is allowed.

    Raises:
        InvalidRevisionTransitionError: If the transition is not in
            VALID_REVISION_TRANSITIONS.
    """
    from cold_storage.modules.coefficients.domain.exceptions import (
        InvalidRevisionTransitionError,
    )

    if current_status not in ALL_REVISION_STATUSES:
        raise InvalidRevisionTransitionError(current_status, target_status)
    if (current_status, target_status) not in VALID_REVISION_TRANSITIONS:
        raise InvalidRevisionTransitionError(current_status, target_status)


# ---------------------------------------------------------------------------
# Domain value objects
# ---------------------------------------------------------------------------


@dataclass
class CoefficientDefinition:
    """Canonical identity of an engineering coefficient.

    A definition represents the persistent identity of a coefficient,
    while revisions track versioned values over time.
    """

    code: str
    name: str
    description: str
    category: str
    canonical_unit: str
    value_type: str = "decimal"
    scope_type: str = "global"
    is_active: bool = True
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.value_type not in ALL_VALUE_TYPES:
            msg = f"Invalid value_type: {self.value_type}. Must be one of {ALL_VALUE_TYPES}"
            raise ValueError(msg)
        if self.scope_type not in ALL_SCOPE_TYPES:
            msg = f"Invalid scope_type: {self.scope_type}. Must be one of {ALL_SCOPE_TYPES}"
            raise ValueError(msg)


@dataclass
class CoefficientRevision:
    """A versioned value with governance metadata.

    Revisions track the history of value changes for a coefficient definition.
    Each revision goes through a state machine from draft to approved/withdrawn.
    """

    coefficient_definition_id: str
    revision_number: int
    unit: str
    status: str = "draft"
    source_type: str = "demo"
    created_by: str = "system"
    id: str = field(default_factory=new_id)
    value_decimal: Decimal | None = None
    value_json: dict[str, object] | None = None
    source_title: str | None = None
    source_reference: str | None = None
    source_page: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    applicable_product_type: str | None = None
    applicable_zone_type: str | None = None
    applicable_process_type: str | None = None
    supersedes_revision_id: str | None = None
    change_reason: str | None = None
    reviewed_by: str | None = None
    approved_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    withdrawn_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.status not in ALL_REVISION_STATUSES:
            msg = f"Invalid status: {self.status}. Must be one of {ALL_REVISION_STATUSES}"
            raise ValueError(msg)
        if self.source_type not in ALL_SOURCE_TYPES:
            msg = f"Invalid source_type: {self.source_type}. Must be one of {ALL_SOURCE_TYPES}"
            raise ValueError(msg)

    # ------------------------------------------------------------------
    # State machine operations
    # ------------------------------------------------------------------

    def transition_to(self, target_status: str) -> None:
        """Validate and apply a state transition.

        Raises:
            InvalidRevisionTransitionError: If the transition is not allowed.
            RevisionImmutabilityError: If the revision is locked (except
                approved → withdrawn).
        """
        from cold_storage.modules.coefficients.domain.exceptions import (
            RevisionImmutabilityError,
        )

        if self.is_locked and not (self.status == "approved" and target_status == "withdrawn"):
            msg = f"transition to '{target_status}'"
            raise RevisionImmutabilityError(self.id, self.status, msg)
        validate_revision_transition(self.status, target_status)
        now = datetime.now(UTC)

        # Apply side-effects based on transition
        if target_status == "reviewed":
            self.reviewed_at = now
        elif target_status == "approved":
            self.approved_at = now
            if self.approved_by is None:
                self.approved_by = self.created_by
        elif target_status == "withdrawn":
            self.withdrawn_at = now

        self.status = target_status

    # ------------------------------------------------------------------
    # Immutability helpers
    # ------------------------------------------------------------------

    @property
    def is_locked(self) -> bool:
        """A revision is locked (immutable) when approved or withdrawn."""
        return self.status in ("approved", "withdrawn")

    def assert_not_locked(self, operation: str = "modify") -> None:
        """Raise RevisionImmutabilityError if this revision is locked."""
        if self.is_locked:
            from cold_storage.modules.coefficients.domain.exceptions import (
                RevisionImmutabilityError,
            )

            raise RevisionImmutabilityError(self.id, self.status, operation)

    # ------------------------------------------------------------------
    # Value access helpers
    # ------------------------------------------------------------------

    def get_decimal_value(self) -> Decimal:
        """Return the decimal value or raise if not set."""
        if self.value_decimal is None:
            msg = f"Revision {self.id} has no decimal value"
            raise ValueError(msg)
        return self.value_decimal

    def get_json_value(self) -> dict[str, object]:
        """Return the JSON value or raise if not set."""
        if self.value_json is None:
            msg = f"Revision {self.id} has no JSON value"
            raise ValueError(msg)
        return self.value_json.copy()

    def has_value(self) -> bool:
        """Return True if this revision has either a decimal or JSON value."""
        return self.value_decimal is not None or self.value_json is not None

    def set_reviewed(self, reviewer: str) -> None:
        """Mark as reviewed by the given reviewer."""
        self.reviewed_by = reviewer
        self.transition_to("reviewed")

    def set_approved(self, approver: str) -> None:
        """Mark as approved by the given approver."""
        self.created_by = approver  # used by transition_to for approved_by
        self.transition_to("approved")


@dataclass(frozen=True)
class CoefficientValue:
    """Immutable resolved coefficient value for calculations.

    This is what calculators receive — a snapshot of the approved value
    with full provenance metadata.
    """

    code: str
    revision_id: str
    revision_number: int
    value: Decimal
    unit: str
    status: str
    source_type: str
    source_reference: str | None
    requires_review: bool


@dataclass(frozen=True)
class CoefficientSet:
    """Immutable collection of resolved coefficient values.

    Captures a point-in-time snapshot of coefficient values for a calculation.
    """

    items: dict[str, CoefficientValue]
    schema_version: str = SCHEMA_VERSION
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get(self, code: str) -> CoefficientValue | None:
        """Return a coefficient by code, or None if not present."""
        return self.items.get(code)

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, code: str) -> bool:
        return code in self.items
