"""Knowledge lifecycle — state machine for ingestion and review status."""

from __future__ import annotations

from cold_storage.modules.knowledge.domain.errors import (
    ApprovedRevisionImmutabilityError,
    InvalidLifecycleTransitionError,
)

# Allowed transitions: current_status -> set of valid target statuses
INGESTION_TRANSITIONS: dict[str, set[str]] = {
    "uploaded": {"processing"},
    "processing": {"indexed", "requires_ocr", "failed"},
    "failed": {"processing"},
    "indexed": set(),  # terminal
    "requires_ocr": set(),  # terminal
}

REVIEW_TRANSITIONS: dict[str, set[str]] = {
    "unverified": {"reviewed", "withdrawn"},
    "reviewed": {"approved", "withdrawn"},
    "approved": {"withdrawn"},
    "withdrawn": set(),  # terminal
}


def validate_ingestion_transition(current: str, target: str) -> None:
    """Validate that a transition from *current* to *target* ingestion status is allowed."""
    allowed = INGESTION_TRANSITIONS.get(current)
    if allowed is None:
        raise InvalidLifecycleTransitionError(f"Unknown ingestion status: {current!r}")
    if target not in allowed:
        raise InvalidLifecycleTransitionError(
            f"Cannot transition ingestion status from {current!r} to {target!r}"
        )


def validate_review_transition(current: str, target: str) -> None:
    """Validate that a transition from *current* to *target* review status is allowed."""
    allowed = REVIEW_TRANSITIONS.get(current)
    if allowed is None:
        raise InvalidLifecycleTransitionError(f"Unknown review status: {current!r}")
    if target not in allowed:
        raise InvalidLifecycleTransitionError(
            f"Cannot transition review status from {current!r} to {target!r}"
        )


def validate_review_eligibility(ingestion_status: str, review_status: str) -> None:
    """Only ``indexed`` revisions can enter ``reviewed``.  Requires-ocr cannot be approved."""
    if review_status == "reviewed" and ingestion_status != "indexed":
        raise InvalidLifecycleTransitionError(
            "Cannot set review_status to 'reviewed' when ingestion_status"
            f" is {ingestion_status!r}; only 'indexed' revisions are eligible"
        )


def can_transition_ingestion(current: str, target: str) -> bool:
    """Return ``True`` if the transition is allowed without raising."""
    allowed = INGESTION_TRANSITIONS.get(current)
    return allowed is not None and target in allowed


def can_transition_review(current: str, target: str) -> bool:
    """Return ``True`` if the review transition is allowed without raising."""
    allowed = REVIEW_TRANSITIONS.get(current)
    return allowed is not None and target in allowed


def is_terminal_ingestion(status: str) -> bool:
    """Return ``True`` if the ingestion status is terminal (no further transitions)."""
    return len(INGESTION_TRANSITIONS.get(status, set())) == 0


def is_terminal_review(status: str) -> bool:
    """Return ``True`` if the review status is terminal."""
    return len(REVIEW_TRANSITIONS.get(status, set())) == 0


def assert_not_approved(revision_status: str) -> None:
    """Raise if the revision is already approved (immutability guard)."""
    if revision_status == "approved":
        raise ApprovedRevisionImmutabilityError("Cannot modify an approved revision")
