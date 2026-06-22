"""State machine validation for agent domain entities."""

from __future__ import annotations

from cold_storage.modules.planning_agent.domain.enums import (
    ConfirmationStatus,
    SessionStatus,
    ToolCallStatus,
    TurnStatus,
)
from cold_storage.modules.planning_agent.domain.errors import InvalidTransitionError

# ---------------------------------------------------------------------------
# Session transitions
# ---------------------------------------------------------------------------

_SESSION_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.ACTIVE: {
        SessionStatus.AWAITING_CONFIRMATION,
        SessionStatus.COMPLETED,
        SessionStatus.CANCELLED,
        SessionStatus.FAILED,
    },
    SessionStatus.AWAITING_CONFIRMATION: {
        SessionStatus.ACTIVE,
        SessionStatus.COMPLETED,
        SessionStatus.CANCELLED,
        SessionStatus.FAILED,
    },
    SessionStatus.COMPLETED: set(),
    SessionStatus.CANCELLED: set(),
    SessionStatus.FAILED: set(),
}


def validate_session_transition(current: SessionStatus, target: SessionStatus) -> None:
    if target not in _SESSION_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError("session", current.value, target.value)


# ---------------------------------------------------------------------------
# Turn transitions
# ---------------------------------------------------------------------------

_TURN_TRANSITIONS: dict[TurnStatus, set[TurnStatus]] = {
    TurnStatus.PROCESSING: {
        TurnStatus.AWAITING_INPUT,
        TurnStatus.AWAITING_CONFIRMATION,
        TurnStatus.COMPLETED,
        TurnStatus.FAILED,
        TurnStatus.CANCELLED,
    },
    TurnStatus.AWAITING_INPUT: {TurnStatus.PROCESSING, TurnStatus.CANCELLED},
    TurnStatus.AWAITING_CONFIRMATION: {
        TurnStatus.PROCESSING,
        TurnStatus.COMPLETED,
        TurnStatus.FAILED,
        TurnStatus.CANCELLED,
    },
    TurnStatus.COMPLETED: set(),
    TurnStatus.FAILED: set(),
    TurnStatus.CANCELLED: set(),
}


def validate_turn_transition(current: TurnStatus, target: TurnStatus) -> None:
    if target not in _TURN_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError("turn", current.value, target.value)


# ---------------------------------------------------------------------------
# Tool call transitions
# ---------------------------------------------------------------------------

_TOOL_CALL_TRANSITIONS: dict[ToolCallStatus, set[ToolCallStatus]] = {
    ToolCallStatus.PROPOSED: {
        ToolCallStatus.AWAITING_CONFIRMATION,
        ToolCallStatus.EXECUTING,
        ToolCallStatus.REJECTED,
        ToolCallStatus.CANCELLED,
        ToolCallStatus.EXPIRED,
    },
    ToolCallStatus.AWAITING_CONFIRMATION: {
        ToolCallStatus.CONFIRMED,
        ToolCallStatus.REJECTED,
        ToolCallStatus.EXPIRED,
        ToolCallStatus.CANCELLED,
    },
    ToolCallStatus.CONFIRMED: {
        ToolCallStatus.EXECUTING,
        ToolCallStatus.CANCELLED,
    },
    ToolCallStatus.EXECUTING: {
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
    },
    ToolCallStatus.SUCCEEDED: set(),
    ToolCallStatus.FAILED: set(),
    ToolCallStatus.REJECTED: set(),
    ToolCallStatus.CANCELLED: set(),
    ToolCallStatus.EXPIRED: set(),
}


def validate_tool_call_transition(current: ToolCallStatus, target: ToolCallStatus) -> None:
    if target not in _TOOL_CALL_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError("tool_call", current.value, target.value)


# ---------------------------------------------------------------------------
# Confirmation transitions
# ---------------------------------------------------------------------------

_CONFIRMATION_TRANSITIONS: dict[ConfirmationStatus, set[ConfirmationStatus]] = {
    ConfirmationStatus.ACTIVE: {
        ConfirmationStatus.USED,
        ConfirmationStatus.EXPIRED,
        ConfirmationStatus.REVOKED,
    },
    ConfirmationStatus.USED: set(),
    ConfirmationStatus.EXPIRED: set(),
    ConfirmationStatus.REVOKED: set(),
}


def validate_confirmation_transition(
    current: ConfirmationStatus, target: ConfirmationStatus
) -> None:
    if target not in _CONFIRMATION_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError("confirmation", current.value, target.value)
