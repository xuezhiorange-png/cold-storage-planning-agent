"""Planning Agent Application Service.

Manages session lifecycle, message flow, tool confirmation, and orchestration.
The service owns transaction boundaries. The orchestrator does NOT hold a DB session.
"""

from __future__ import annotations

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
    validate_turn_transition,
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
        check_authorization(
            AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user)
        )
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

        # Fix #4: Idempotency — check for duplicate key
        if idempotency_key:
            existing = self._repo.get_session_by_idempotency_key(idempotency_key)
            if existing is not None:
                # Return the previous result for this idempotency key
                return self._repo.get_last_result(idempotency_key) or {
                    "session_id": session_id,
                    "turn_id": "",
                    "assistant_message": "Already processed",
                    "decision_type": "answer",
                    "tool_calls": [],
                    "idempotent_replay": True,
                }

        # Check session is active (or awaiting_confirmation for follow-up)
        if session.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
            raise SessionCompletedError(session_id)

        # Check no active turn (concurrency guard)
        active_turn = self._repo.get_active_turn(session_id)
        if active_turn is not None:
            raise ConcurrentTurnError(session_id)

        check_authorization(
            AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user)
        )

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
        # Fix #6: Re-raise domain errors instead of catch-all
        result = self._orchestrator.orchestrate_turn(
            session=updated_session2,
            turn=turn,
            user_message=user_msg,
            gateway=self._gateway,
            registry=self._registry,
            repo=self._repo,
        )

        # Fix #9: Transaction boundary — commit after orchestration
        self._repo.commit()

        return result

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
    ) -> dict[str, Any]:
        """Confirm a pending tool call.

        Returns dict with tool_call info and session state updates.
        Transitions: turn awaiting_confirmation -> completed, 
        session awaiting_confirmation -> active.
        """
        tc = self._repo.get_tool_call(tool_call_id)
        if tc is None:
            raise SessionNotFoundError(tool_call_id)

        session = self._repo.get_session(tc.session_id)
        check_authorization(
            AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user)
        )

        token_hash = sha256_json(confirmation_token)

        # Find confirmation
        confirmation = self._repo.get_confirmation_by_token_hash(token_hash)
        if confirmation is None:
            raise SessionNotFoundError("confirmation")

        # Validate
        if confirmation.status != ConfirmationStatus.ACTIVE:
            raise ConfirmationAlreadyUsedError(confirmation.id)
        if confirmation.expires_at:
            expires = confirmation.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < datetime.now(UTC):
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
            self._repo.update_tool_call(succeeded_tc)
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
            self._repo.update_tool_call(failed_tc)

        # --- Fix #3: Transition turn and session after confirm/reject ---
        now = datetime.now(UTC)

        # Find the turn that was awaiting_confirmation
        turn = self._repo.get_active_turn(tc.session_id)
        if turn is not None and turn.status == TurnStatus.AWAITING_CONFIRMATION:
            validate_turn_transition(turn.status, TurnStatus.COMPLETED)
            completed_turn = AgentTurn(
                **{
                    **asdict(turn),
                    "status": TurnStatus.COMPLETED,
                    "completed_at": now,
                }
            )
            self._repo.update_turn(completed_turn)

        # Transition session from awaiting_confirmation -> active
        session = self._repo.get_session(tc.session_id)
        if session.status == SessionStatus.AWAITING_CONFIRMATION:
            validate_session_transition(
                session.status, SessionStatus.ACTIVE
            )
            resumed = AgentSession(
                **{
                    **asdict(session),
                    "status": SessionStatus.ACTIVE,
                    "updated_at": now,
                    "version": session.version + 1,
                }
            )
            self._repo.update_session(resumed)

        # Fix #9: Transaction boundary — commit after confirmation flow
        self._repo.commit()

        # Get the updated tool call for response
        final_tc = self._repo.get_tool_call(tool_call_id)
        return {
            "tool_call": final_tc,
            "session_status": self._repo.get_session(tc.session_id).status.value,
        }

    def reject_tool_call(
        self,
        tool_call_id: str,
        *,
        user: str = "user",
    ) -> dict[str, Any]:
        """Reject a pending tool call.

        Returns dict with tool_call info and session state updates.
        Transitions: turn awaiting_confirmation -> completed,
        session awaiting_confirmation -> active.
        """
        tc = self._repo.get_tool_call(tool_call_id)
        if tc is None:
            raise SessionNotFoundError(tool_call_id)
        session = self._repo.get_session(tc.session_id)
        check_authorization(
            AuthorizationLevel.WRITE, is_session_owner=(session.created_by == user)
        )
        validate_tool_call_transition(tc.status, ToolCallStatus.REJECTED)
        rejected = AgentToolCall(
            **{
                **asdict(tc),
                "status": ToolCallStatus.REJECTED,
                "completed_at": datetime.now(UTC),
            }
        )
        self._repo.update_tool_call(rejected)

        # --- Fix #3: Transition turn and session ---
        now = datetime.now(UTC)

        turn = self._repo.get_active_turn(tc.session_id)
        if turn is not None and turn.status == TurnStatus.AWAITING_CONFIRMATION:
            validate_turn_transition(turn.status, TurnStatus.COMPLETED)
            completed_turn = AgentTurn(
                **{
                    **asdict(turn),
                    "status": TurnStatus.COMPLETED,
                    "completed_at": now,
                }
            )
            self._repo.update_turn(completed_turn)

        session = self._repo.get_session(tc.session_id)
        if session.status == SessionStatus.AWAITING_CONFIRMATION:
            validate_session_transition(
                session.status, SessionStatus.ACTIVE
            )
            resumed = AgentSession(
                **{
                    **asdict(session),
                    "status": SessionStatus.ACTIVE,
                    "updated_at": now,
                    "version": session.version + 1,
                }
            )
            self._repo.update_session(resumed)

        # Fix #9: Transaction boundary — commit after reject flow
        self._repo.commit()

        final_tc = self._repo.get_tool_call(tool_call_id)
        return {
            "tool_call": final_tc,
            "session_status": self._repo.get_session(tc.session_id).status.value,
        }


def sha256_json(obj: Any) -> str:
    """Local SHA-256 helper — same as domain sha256_json."""
    from cold_storage.modules.planning_agent.domain.models import sha256_json as _sha256_json
    return _sha256_json(obj)
