"""Report status machine — enforces allowed transitions and CAS."""

from __future__ import annotations

from cold_storage.modules.reports.domain.enums import (
    ACTION_TRANSITIONS,
    STATUS_TRANSITIONS,
    ReportStatus,
    ReviewAction,
)
from cold_storage.modules.reports.domain.errors import InvalidStatusTransitionError


def validate_transition(from_status: ReportStatus, to_status: ReportStatus) -> None:
    """Raise if the transition is not allowed."""
    allowed = STATUS_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidStatusTransitionError(from_status.value, to_status.value)


def apply_action(
    current_status: ReportStatus,
    action: ReviewAction,
) -> ReportStatus:
    """Return the target status for the given action, or raise."""
    expected = ACTION_TRANSITIONS.get(action)
    if expected is None:
        raise InvalidStatusTransitionError(current_status.value, action.value)
    from_s, to_s = expected
    if current_status != from_s:
        raise InvalidStatusTransitionError(current_status.value, to_s.value)
    return to_s
