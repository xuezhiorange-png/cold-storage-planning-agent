"""FastAPI routes for the planning agent API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from cold_storage.modules.planning_agent.api.schemas import (
    ConfirmToolCallRequest,
    CreateSessionRequest,
    MessageResponse,
    PostMessageRequest,
    PostMessageResponse,
    RejectToolCallRequest,
    SessionCancelResponse,
    SessionResponse,
    ToolCallInfo,
    TurnResponse,
)
from cold_storage.modules.planning_agent.application.service import PlanningAgentService
from cold_storage.modules.planning_agent.domain.errors import (
    ConcurrentTurnError,
    ConfirmationAlreadyUsedError,
    ConfirmationExpiredError,
    InvalidStructuredOutputError,
    InvalidTransitionError,
    ModelGatewayError,
    PlanningAgentError,
    SessionCompletedError,
    SessionNotFoundError,
    StaleConfirmationError,
    ToolArgumentValidationError,
    ToolCallLimitExceededError,
    UnauthorizedError,
    UnregisteredToolError,
)


def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert dataclass or dict to plain dict."""
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    if isinstance(obj, dict):
        return obj
    return {}


def create_agent_router(service: PlanningAgentService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

    @router.post("/sessions", response_model=SessionResponse, status_code=201)
    def create_session(req: CreateSessionRequest) -> Any:
        session = service.create_session(
            project_id=req.project_id,
            project_version_id=req.project_version_id,
            title=req.title,
        )
        return SessionResponse(
            id=session.id,
            project_id=session.project_id,
            project_version_id=session.project_version_id,
            status=session.status.value,
            title=session.title,
            created_by=session.created_by,
            created_at=session.created_at,
            updated_at=session.updated_at,
            closed_at=session.closed_at,
            next_message_sequence=session.next_message_sequence,
            next_turn_sequence=session.next_turn_sequence,
            version=session.version,
        )

    @router.get("/sessions", response_model=list[SessionResponse])
    def list_sessions() -> Any:
        sessions = service.list_sessions()
        return [
            SessionResponse(
                id=s.id,
                project_id=s.project_id,
                project_version_id=s.project_version_id,
                status=s.status.value,
                title=s.title,
                created_by=s.created_by,
                created_at=s.created_at,
                updated_at=s.updated_at,
                closed_at=s.closed_at,
                next_message_sequence=s.next_message_sequence,
                next_turn_sequence=s.next_turn_sequence,
                version=s.version,
            )
            for s in sessions
        ]

    @router.get("/sessions/{session_id}", response_model=SessionResponse)
    def get_session(session_id: str) -> Any:
        try:
            s = service.get_session(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return SessionResponse(
            id=s.id,
            project_id=s.project_id,
            project_version_id=s.project_version_id,
            status=s.status.value,
            title=s.title,
            created_by=s.created_by,
            created_at=s.created_at,
            updated_at=s.updated_at,
            closed_at=s.closed_at,
            next_message_sequence=s.next_message_sequence,
            next_turn_sequence=s.next_turn_sequence,
            version=s.version,
        )

    @router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
    def get_messages(session_id: str) -> Any:
        try:
            service.get_session(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        msgs = service.get_messages(session_id)
        return [
            MessageResponse(
                id=m.id,
                session_id=m.session_id,
                sequence=m.sequence,
                role=m.role.value,
                content=m.content,
                structured_content=m.structured_content,
                tool_call_id=m.tool_call_id,
                created_at=m.created_at,
            )
            for m in msgs
        ]

    @router.post(
        "/sessions/{session_id}/messages", response_model=PostMessageResponse, status_code=201
    )
    def post_message(session_id: str, req: PostMessageRequest) -> Any:
        # Fix #6: Domain errors are NOT caught here — they propagate from service.
        # Only infrastructure/transport errors are caught for HTTP mapping.
        try:
            result = service.post_user_message(
                session_id,
                req.content,
                idempotency_key=req.idempotency_key,
            )
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except SessionCompletedError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except ConcurrentTurnError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except UnauthorizedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except (
            UnregisteredToolError,
            ToolArgumentValidationError,
            ToolCallLimitExceededError,
        ) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except InvalidStructuredOutputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except ModelGatewayError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        except PlanningAgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

        return PostMessageResponse(
            session_id=result["session_id"],
            turn_id=result["turn_id"],
            assistant_message=result["assistant_message"],
            decision_type=result["decision_type"],
            tool_calls=[ToolCallInfo(**tc) for tc in result["tool_calls"]],
            missing_parameters=result.get("missing_parameters", []),
            requires_review=result.get("requires_review", False),
            warnings=result.get("warnings", []),
            prompt_version=result.get("prompt_version", ""),
            model_metadata=_to_dict(result.get("model_metadata", {})),
        )

    @router.get("/sessions/{session_id}/turns/{turn_id}", response_model=TurnResponse)
    def get_turn(session_id: str, turn_id: str) -> Any:
        turn = service.get_turn(turn_id)
        if turn is None or turn.session_id != session_id:
            raise HTTPException(status_code=404, detail="Turn not found")
        return TurnResponse(
            id=turn.id,
            session_id=turn.session_id,
            turn_number=turn.turn_number,
            status=turn.status.value,
            assistant_message_id=turn.assistant_message_id,
            model_provider=turn.model_provider,
            model_name=turn.model_name,
            prompt_version=turn.prompt_version,
            requires_review=turn.requires_review,
            created_at=turn.created_at,
            completed_at=turn.completed_at,
            error_code=turn.error_code,
            error_message=turn.error_message,
        )

    @router.get("/sessions/{session_id}/tool-calls", response_model=list[ToolCallInfo])
    def list_tool_calls(session_id: str) -> Any:
        try:
            service.get_session(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        tcs = service.list_tool_calls(session_id)
        return [
            ToolCallInfo(
                id=tc.id,
                tool_name=tc.tool_name,
                status=tc.status.value,
                requires_confirmation=(tc.status.value == "awaiting_confirmation"),
                arguments=tc.arguments,
                result=tc.result,
                warnings=tc.warning_messages,
                requires_review=tc.requires_review,
            )
            for tc in tcs
        ]

    @router.post("/tool-calls/{tool_call_id}/confirm")
    def confirm_tool_call(tool_call_id: str, req: ConfirmToolCallRequest) -> Any:
        try:
            result = service.confirm_tool_call(
                tool_call_id, confirmation_token=req.confirmation_token
            )
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ConfirmationAlreadyUsedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except ConfirmationExpiredError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except StaleConfirmationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except UnauthorizedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        tc = result["tool_call"]
        return {
            "id": tc.id,
            "tool_name": tc.tool_name,
            "status": tc.status.value,
            "requires_confirmation": False,
            "arguments": tc.arguments,
            "result": tc.result,
            "warnings": tc.warning_messages,
            "requires_review": tc.requires_review,
            "session_status": result["session_status"],
        }

    @router.post("/tool-calls/{tool_call_id}/reject")
    def reject_tool_call(tool_call_id: str, req: RejectToolCallRequest) -> Any:  # noqa: ARG001
        try:
            result = service.reject_tool_call(tool_call_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except UnauthorizedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        tc = result["tool_call"]
        return {
            "id": tc.id,
            "tool_name": tc.tool_name,
            "status": tc.status.value,
            "requires_confirmation": False,
            "arguments": tc.arguments,
            "result": tc.result,
            "warnings": tc.warning_messages,
            "requires_review": tc.requires_review,
            "session_status": result["session_status"],
        }

    @router.post("/sessions/{session_id}/cancel", response_model=SessionCancelResponse)
    def cancel_session(session_id: str) -> Any:
        try:
            s = service.cancel_session(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except UnauthorizedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return SessionCancelResponse(session_id=s.id, status=s.status.value)

    return router
