"""Planning Agent Application Service.

Manages session lifecycle, message flow, tool confirmation, and orchestration.
The service owns transaction boundaries. The orchestrator does NOT hold a DB session.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from cold_storage.modules.planning_agent.application.orchestrator import AgentOrchestrator
from cold_storage.modules.planning_agent.application.tool_registry import ToolRegistry
from cold_storage.modules.planning_agent.domain.authorization import check_authorization
from cold_storage.modules.planning_agent.domain.enums import (
    AuthorizationLevel,
    ConfirmationStatus,
    MessageRole,
    SessionStatus,
    ToolCallStatus,
    TurnStatus,
)
from cold_storage.modules.planning_agent.domain.errors import (
    ConcurrentTurnError,
    ConfirmationAlreadyUsedError,
    ConfirmationExpiredError,
    SessionCompletedError,
    SessionNotFoundError,
    StaleConfirmationError,
)
from cold_storage.modules.planning_agent.domain.gateways import AgentModelGateway
from cold_storage.modules.planning_agent.domain.lifecycle import (
    validate_session_transition,
    validate_tool_call_transition,
)
from cold_storage.modules.planning_agent.domain.models import (
    AgentConfirmation,
    AgentMessage,
    AgentSession,
    AgentToolCall,
    AgentTurn,
)
from cold_storage.modules.planning_agent.infrastructure.repository import AgentRepository


class PlanningAgentService:
    """Application service: session/message/turn/tool-call management."""

    def __init__(
        self,
        repository: AgentRepository,
        gateway: AgentModelGateway,
        registry: ToolRegistry,
        orchestrator: AgentOrchestrator,
        *,
        max_tool_calls_per_turn: int = 5,
    ) -> None:
        self._repo = repository
        self._gateway = gateway
        self._registry = registry
        self._orchestrator = orchestrator
        self._max_tool_calls = max_tool_calls_per_turn

    # ----- Session -----

    def create_session(
        self,
        *,
        created_by: str = "user",
        project_id: str | None = None,
        project_version_id: str | None = None,
        title: str = "",
    ) -> AgentSession:
        now = datetime.now(UTC)
        session = AgentSession(
            project_id=project_id,
            project_version_id=project_version_id,
            title=title or f"Session {now.isoformat()}",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        return self._repo.create_session(session)

    def get_session(self, session_id: str) -> AgentSession:
        return self._repo.get_session(session_id)

    def list_sessions(self, limit: int = 50) -> list[AgentSession]:
        return self._repo.list_sessions(limit=limit)

    def cancel_session(self, session_id: str, *, user: str = "user") -> AgentSession:
        session = self._repo.get_session(session_id)
        check_authorization(AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user))
        validate_session_transition(session.status, SessionStatus.CANCELLED)
        closed = AgentSession(
            **{
                **asdict(session),
                "status": SessionStatus.CANCELLED,
                "closed_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "version": session.version + 1,
            }
        )
        return self._repo.update_session(closed)

    # ----- Messages -----

    def post_user_message(
        self,
        session_id: str,
        content: str,
        *,
        user: str = "user",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        session = self._repo.get_session(session_id)

        # Check session is active
        if session.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
            raise SessionCompletedError(session_id)

        # Check no active turn (concurrency guard)
        active_turn = self._repo.get_active_turn(session_id)
        if active_turn is not None:
            raise ConcurrentTurnError(session_id)

        check_authorization(AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user))

        # Create user message
        now = datetime.now(UTC)
        user_msg = AgentMessage(
            session_id=session_id,
            sequence=session.next_message_sequence,
            role=MessageRole.USER,
            content=content,
            created_at=now,
        )
        self._repo.add_message(user_msg)

        # Update session sequence
        updated_session = AgentSession(
            **{
                **asdict(session),
                "next_message_sequence": session.next_message_sequence + 1,
                "updated_at": now,
                "version": session.version + 1,
            }
        )
        self._repo.update_session(updated_session)

        # Create processing turn
        turn = AgentTurn(
            session_id=session_id,
            turn_number=session.next_turn_sequence,
            status=TurnStatus.PROCESSING,
            user_message_id=user_msg.id,
            created_at=now,
        )
        self._repo.add_turn(turn)

        # Update session turn sequence
        updated_session2 = AgentSession(
            **{
                **asdict(updated_session),
                "next_turn_sequence": session.next_turn_sequence + 1,
                "updated_at": now,
                "version": updated_session.version + 1,
            }
        )
        self._repo.update_session(updated_session2)

        # Orchestrate: get model decision + execute tools
        try:
            result = self._orchestrator.orchestrate_turn(
                session=updated_session2,
                turn=turn,
                user_message=user_msg,
                gateway=self._gateway,
                registry=self._registry,
                repo=self._repo,
            )
            return result
        except Exception as exc:
            # Mark turn as failed
            failed_turn = AgentTurn(
                **{
                    **asdict(turn),
                    "status": TurnStatus.FAILED,
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                    "completed_at": datetime.now(UTC),
                }
            )
            self._repo.update_turn(failed_turn)
            return {"error": str(exc), "turn_id": turn.id}

    def get_messages(self, session_id: str) -> list[AgentMessage]:
        return self._repo.get_messages(session_id)

    def get_turn(self, turn_id: str) -> AgentTurn | None:
        return self._repo.get_turn(turn_id)

    def get_tool_call(self, tool_call_id: str) -> AgentToolCall | None:
        return self._repo.get_tool_call(tool_call_id)

    def list_tool_calls(self, session_id: str) -> list[AgentToolCall]:
        return self._repo.list_tool_calls(session_id)

    # ----- Confirmation flow -----

    def confirm_tool_call(
        self,
        tool_call_id: str,
        *,
        confirmation_token: str,
        user: str = "user",
    ) -> AgentToolCall:
        tc = self._repo.get_tool_call(tool_call_id)
        if tc is None:
            raise SessionNotFoundError(tool_call_id)

        session = self._repo.get_session(tc.session_id)
        check_authorization(AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user))

        token_hash = hashlib.sha256(confirmation_token.encode()).hexdigest()

        # Find confirmation
        confirmation = self._repo.get_confirmation_by_token_hash(token_hash)
        if confirmation is None:
            raise SessionNotFoundError("confirmation")

        # Validate
        if confirmation.status != ConfirmationStatus.ACTIVE:
            raise ConfirmationAlreadyUsedError(confirmation.id)
        if confirmation.expires_at and confirmation.expires_at < datetime.now(UTC):
            raise ConfirmationExpiredError(confirmation.id)
        if confirmation.tool_call_id != tool_call_id:
            raise StaleConfirmationError(confirmation.id, "tool_call_id mismatch")
        if confirmation.session_id != tc.session_id:
            raise StaleConfirmationError(confirmation.id, "session mismatch")
        if confirmation.arguments_sha256 != tc.arguments_sha256:
            raise StaleConfirmationError(confirmation.id, "arguments changed")

        # Mark confirmation as used
        used_confirmation = AgentConfirmation(
            **{
                **asdict(confirmation),
                "status": ConfirmationStatus.USED,
                "used_at": datetime.now(UTC),
            }
        )
        self._repo.update_confirmation(used_confirmation)

        # Transition tool call: awaiting_confirmation -> confirmed -> executing
        validate_tool_call_transition(tc.status, ToolCallStatus.CONFIRMED)
        confirmed_tc = AgentToolCall(
            **{
                **asdict(tc),
                "status": ToolCallStatus.CONFIRMED,
                "confirmed_at": datetime.now(UTC),
            }
        )
        self._repo.update_tool_call(confirmed_tc)

        # Execute the tool
        execute_tc = AgentToolCall(
            **{
                **asdict(confirmed_tc),
                "status": ToolCallStatus.EXECUTING,
                "executed_at": datetime.now(UTC),
            }
        )
        self._repo.update_tool_call(execute_tc)

        try:
            tool_result = self._orchestrator.execute_single_tool(
                tc.tool_name, tc.arguments, self._registry
            )
            succeeded_tc = AgentToolCall(
                **{
                    **asdict(execute_tc),
                    "status": ToolCallStatus.SUCCEEDED,
                    "result": tool_result.output,
                    "warning_messages": tool_result.warnings,
                    "requires_review": tool_result.requires_review,
                    "completed_at": datetime.now(UTC),
                }
            )
            return self._repo.update_tool_call(succeeded_tc)
        except Exception as exc:
            failed_tc = AgentToolCall(
                **{
                    **asdict(execute_tc),
                    "status": ToolCallStatus.FAILED,
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                    "completed_at": datetime.now(UTC),
                }
            )
            return self._repo.update_tool_call(failed_tc)

    def reject_tool_call(
        self,
        tool_call_id: str,
        *,
        user: str = "user",
    ) -> AgentToolCall:
        tc = self._repo.get_tool_call(tool_call_id)
        if tc is None:
            raise SessionNotFoundError(tool_call_id)
        session = self._repo.get_session(tc.session_id)
        check_authorization(AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user))
        validate_tool_call_transition(tc.status, ToolCallStatus.REJECTED)
        rejected = AgentToolCall(
            **{**asdict(tc), "status": ToolCallStatus.REJECTED, "completed_at": datetime.now(UTC)}
        )
        return self._repo.update_tool_call(rejected)
