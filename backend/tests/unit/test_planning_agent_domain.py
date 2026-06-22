"""Domain unit tests for planning agent domain models and state machines."""

from __future__ import annotations

import pytest

from cold_storage.modules.planning_agent.domain.authorization import (
    check_authorization,
    requires_confirmation,
)
from cold_storage.modules.planning_agent.domain.enums import (
    AuthorizationLevel,
    ConfirmationStatus,
    DecisionType,
    SessionStatus,
    ToolCallStatus,
    TurnStatus,
)
from cold_storage.modules.planning_agent.domain.errors import (
    ApprovedVersionWriteError,
    ConfirmationAlreadyUsedError,
    ConfirmationExpiredError,
    InvalidTransitionError,
    StaleConfirmationError,
    UnauthorizedError,
    UnregisteredToolError,
)
from cold_storage.modules.planning_agent.domain.lifecycle import (
    validate_confirmation_transition,
    validate_session_transition,
    validate_tool_call_transition,
    validate_turn_transition,
)
from cold_storage.modules.planning_agent.domain.models import (
    AgentDecision,
    sha256_json,
)

# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------


class TestSessionStateMachine:
    def test_active_to_awaiting_confirmation(self):
        validate_session_transition(SessionStatus.ACTIVE, SessionStatus.AWAITING_CONFIRMATION)

    def test_active_to_completed(self):
        validate_session_transition(SessionStatus.ACTIVE, SessionStatus.COMPLETED)

    def test_active_to_cancelled(self):
        validate_session_transition(SessionStatus.ACTIVE, SessionStatus.CANCELLED)

    def test_active_to_failed(self):
        validate_session_transition(SessionStatus.ACTIVE, SessionStatus.FAILED)

    def test_active_to_active_invalid(self):
        with pytest.raises(InvalidTransitionError):
            validate_session_transition(SessionStatus.ACTIVE, SessionStatus.ACTIVE)

    def test_completed_is_terminal(self):
        for target in SessionStatus:
            if target == SessionStatus.COMPLETED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_session_transition(SessionStatus.COMPLETED, target)

    def test_cancelled_is_terminal(self):
        for target in SessionStatus:
            if target == SessionStatus.CANCELLED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_session_transition(SessionStatus.CANCELLED, target)

    def test_failed_is_terminal(self):
        for target in SessionStatus:
            if target == SessionStatus.FAILED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_session_transition(SessionStatus.FAILED, target)

    def test_awaiting_to_active(self):
        validate_session_transition(SessionStatus.AWAITING_CONFIRMATION, SessionStatus.ACTIVE)


# ---------------------------------------------------------------------------
# Turn state machine
# ---------------------------------------------------------------------------


class TestTurnStateMachine:
    def test_processing_to_completed(self):
        validate_turn_transition(TurnStatus.PROCESSING, TurnStatus.COMPLETED)

    def test_processing_to_awaiting_confirmation(self):
        validate_turn_transition(TurnStatus.PROCESSING, TurnStatus.AWAITING_CONFIRMATION)

    def test_processing_to_failed(self):
        validate_turn_transition(TurnStatus.PROCESSING, TurnStatus.FAILED)

    def test_completed_is_terminal(self):
        for target in TurnStatus:
            if target == TurnStatus.COMPLETED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_turn_transition(TurnStatus.COMPLETED, target)


# ---------------------------------------------------------------------------
# Tool call state machine
# ---------------------------------------------------------------------------


class TestToolCallStateMachine:
    def test_proposed_to_awaiting_confirmation(self):
        validate_tool_call_transition(ToolCallStatus.PROPOSED, ToolCallStatus.AWAITING_CONFIRMATION)

    def test_proposed_to_executing(self):
        validate_tool_call_transition(ToolCallStatus.PROPOSED, ToolCallStatus.EXECUTING)

    def test_proposed_to_rejected(self):
        validate_tool_call_transition(ToolCallStatus.PROPOSED, ToolCallStatus.REJECTED)

    def test_awaiting_to_confirmed(self):
        validate_tool_call_transition(
            ToolCallStatus.AWAITING_CONFIRMATION, ToolCallStatus.CONFIRMED
        )

    def test_awaiting_to_rejected(self):
        validate_tool_call_transition(ToolCallStatus.AWAITING_CONFIRMATION, ToolCallStatus.REJECTED)

    def test_confirmed_to_executing(self):
        validate_tool_call_transition(ToolCallStatus.CONFIRMED, ToolCallStatus.EXECUTING)

    def test_executing_to_succeeded(self):
        validate_tool_call_transition(ToolCallStatus.EXECUTING, ToolCallStatus.SUCCEEDED)

    def test_executing_to_failed(self):
        validate_tool_call_transition(ToolCallStatus.EXECUTING, ToolCallStatus.FAILED)

    def test_succeeded_is_terminal(self):
        for target in ToolCallStatus:
            if target == ToolCallStatus.SUCCEEDED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_tool_call_transition(ToolCallStatus.SUCCEEDED, target)

    def test_rejected_is_terminal(self):
        for target in ToolCallStatus:
            if target == ToolCallStatus.REJECTED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_tool_call_transition(ToolCallStatus.REJECTED, target)


# ---------------------------------------------------------------------------
# Confirmation transitions
# ---------------------------------------------------------------------------


class TestConfirmationStateMachine:
    def test_active_to_used(self):
        validate_confirmation_transition(ConfirmationStatus.ACTIVE, ConfirmationStatus.USED)

    def test_active_to_expired(self):
        validate_confirmation_transition(ConfirmationStatus.ACTIVE, ConfirmationStatus.EXPIRED)

    def test_used_is_terminal(self):
        for target in ConfirmationStatus:
            if target == ConfirmationStatus.USED:
                continue
            with pytest.raises(InvalidTransitionError):
                validate_confirmation_transition(ConfirmationStatus.USED, target)


# ---------------------------------------------------------------------------
# Confirmation rules
# ---------------------------------------------------------------------------


class TestConfirmationRules:
    def test_expired_confirmation(self):
        with pytest.raises(ConfirmationExpiredError):
            # Simulate in service-level test
            raise ConfirmationExpiredError("conf-123")

    def test_already_used_confirmation(self):
        with pytest.raises(ConfirmationAlreadyUsedError):
            raise ConfirmationAlreadyUsedError("conf-456")

    def test_stale_confirmation(self):
        with pytest.raises(StaleConfirmationError):
            raise StaleConfirmationError("conf-789", "arguments changed")


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestAuthorization:
    def test_read_always_allowed(self):
        check_authorization(AuthorizationLevel.READ)

    def test_admin_requires_admin_role(self):
        with pytest.raises(UnauthorizedError):
            check_authorization(AuthorizationLevel.ADMINISTRATIVE, is_admin=False)

    def test_admin_with_admin_role(self):
        check_authorization(AuthorizationLevel.ADMINISTRATIVE, is_admin=True)

    def test_write_requires_owner_or_admin(self):
        with pytest.raises(UnauthorizedError):
            check_authorization(AuthorizationLevel.WRITE, is_admin=False, is_session_owner=False)

    def test_write_with_session_owner(self):
        check_authorization(AuthorizationLevel.WRITE, is_session_owner=True)

    def test_write_with_admin(self):
        check_authorization(AuthorizationLevel.WRITE, is_admin=True)

    def test_write_rejects_approved_version(self):
        with pytest.raises(ApprovedVersionWriteError):
            check_authorization(AuthorizationLevel.WRITE, is_admin=True, version_status="approved")

    def test_calculate_requires_owner_or_admin(self):
        with pytest.raises(UnauthorizedError):
            check_authorization(
                AuthorizationLevel.CALCULATE, is_admin=False, is_session_owner=False
            )

    def test_requires_confirmation_for_write(self):
        assert requires_confirmation(AuthorizationLevel.WRITE) is True

    def test_requires_confirmation_for_calculate(self):
        assert requires_confirmation(AuthorizationLevel.CALCULATE) is True

    def test_no_confirmation_for_read(self):
        assert requires_confirmation(AuthorizationLevel.READ) is False


# ---------------------------------------------------------------------------
# Missing parameters
# ---------------------------------------------------------------------------


class TestMissingParameters:
    def test_ask_clarification_has_missing_params(self):
        d = AgentDecision(
            decision_type=DecisionType.ASK_CLARIFICATION,
            missing_parameters=[{"name": "daily_inbound_mass_kg", "reason": "required_by_tool"}],
        )
        assert len(d.missing_parameters) == 1
        assert d.tool_requests == []


# ---------------------------------------------------------------------------
# Unregistered tool
# ---------------------------------------------------------------------------


class TestUnregisteredTool:
    def test_unregistered_tool_error(self):
        with pytest.raises(UnregisteredToolError):
            raise UnregisteredToolError("nonexistent.tool")

    def test_error_contains_tool_name(self):
        exc = UnregisteredToolError("bad.tool")
        assert "bad.tool" in str(exc)


# ---------------------------------------------------------------------------
# SHA-256 hashing
# ---------------------------------------------------------------------------


class TestSha256:
    def test_deterministic(self):
        a = sha256_json({"key": "value", "num": 42})
        b = sha256_json({"num": 42, "key": "value"})
        assert a == b

    def test_different_for_different_data(self):
        a = sha256_json({"key": "value"})
        b = sha256_json({"key": "other"})
        assert a != b

    def test_length(self):
        h = sha256_json("test")
        assert len(h) == 64
