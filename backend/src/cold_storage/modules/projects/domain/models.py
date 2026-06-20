"""Project domain models with version state machine and immutability rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Version state machine
# ---------------------------------------------------------------------------

# Valid state transitions: frozenset of (from_state, to_state) pairs.
VALID_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("draft", "generated"),
        ("draft", "under_review"),
        ("generated", "under_review"),
        ("under_review", "reviewed"),
        ("under_review", "draft"),
        ("reviewed", "approved"),
        ("reviewed", "draft"),
        ("approved", "archived"),
    }
)

ALL_VERSION_STATUSES: frozenset[str] = frozenset(
    {"draft", "generated", "under_review", "reviewed", "approved", "archived"}
)


class InvalidVersionTransitionError(Exception):
    """Raised when an invalid version state transition is attempted."""

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid transition from '{from_status}' to '{to_status}'. "
            f"Valid transitions from '{from_status}': "
            f"{[t for f, t in VALID_TRANSITIONS if f == from_status]}"
        )


class VersionImmutabilityError(Exception):
    """Raised when an operation attempts to modify a locked (approved/archived) version."""

    def __init__(self, version_id: str, status: str, operation: str) -> None:
        self.version_id = version_id
        self.status = status
        self.operation = operation
        super().__init__(
            f"Cannot {operation} on version {version_id} with status '{status}'. "
            f"Approved/archived versions are immutable."
        )


def validate_transition(current_status: str, target_status: str) -> None:
    """Validate that a state transition is allowed.

    Raises:
        InvalidVersionTransitionError: If the transition is not in VALID_TRANSITIONS.
    """
    if current_status not in ALL_VERSION_STATUSES:
        raise InvalidVersionTransitionError(current_status, target_status)
    if (current_status, target_status) not in VALID_TRANSITIONS:
        raise InvalidVersionTransitionError(current_status, target_status)


# ---------------------------------------------------------------------------
# Domain value objects
# ---------------------------------------------------------------------------


def new_id() -> str:
    return str(uuid4())


@dataclass
class ProjectVersion:
    project_id: str
    version_number: int
    change_summary: str
    status: str = "draft"
    input_snapshot: dict[str, object] = field(default_factory=dict)
    calculation_snapshot: dict[str, object] = field(default_factory=dict)
    assumption_snapshot: dict[str, object] = field(default_factory=dict)
    created_by: str = "system"
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    parent_version_id: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None
    archived_at: datetime | None = None

    # ------------------------------------------------------------------
    # State machine operations
    # ------------------------------------------------------------------

    def transition_to(self, target_status: str) -> None:
        """Validate and apply a state transition.

        Raises:
            InvalidVersionTransitionError: If the transition is not allowed.
            VersionImmutabilityError: If the version is locked and cannot change state
                (except approved → archived).
        """
        if self.is_locked and target_status != "archived":
            raise VersionImmutabilityError(self.id, self.status, f"transition to '{target_status}'")
        validate_transition(self.status, target_status)
        now = datetime.now(UTC)

        # Apply side-effects based on transition
        if target_status == "under_review":
            self.submitted_at = now
        elif target_status == "reviewed":
            self.reviewed_at = now
        elif target_status == "approved":
            self.approved_at = now
            self.approved_by = self.created_by
        elif target_status == "archived":
            self.archived_at = now

        self.status = target_status
        self.updated_at = now

    # ------------------------------------------------------------------
    # Immutability helpers
    # ------------------------------------------------------------------

    @property
    def is_locked(self) -> bool:
        """A version is locked (immutable) when approved or archived."""
        return self.status in ("approved", "archived")

    def assert_not_locked(self, operation: str = "modify") -> None:
        """Raise VersionImmutabilityError if this version is locked."""
        if self.is_locked:
            raise VersionImmutabilityError(self.id, self.status, operation)

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def snapshot_metadata(self) -> dict[str, object]:
        """Return a metadata dict describing the current version snapshots."""
        return {
            "schema_version": SCHEMA_VERSION,
            "version_number": self.version_number,
            "parent_version_id": self.parent_version_id,
        }


@dataclass
class Project:
    code: str
    name: str
    location: str
    product_category: str
    status: str = "draft"
    current_version_number: int = 0
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    versions: list[ProjectVersion] = field(default_factory=list)


@dataclass
class SaveInputsResult:
    success: bool
    error_code: str | None = None
    version: ProjectVersion | None = None
