"""Pydantic schemas for planning agent API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    project_id: str | None = None
    project_version_id: str | None = None
    title: str = ""


class SessionResponse(BaseModel):
    id: str
    project_id: str | None = None
    project_version_id: str | None = None
    status: str
    title: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    next_message_sequence: int
    next_turn_sequence: int
    version: int


class PostMessageRequest(BaseModel):
    content: str
    idempotency_key: str | None = None


class ToolCallInfo(BaseModel):
    id: str
    tool_name: str
    status: str
    requires_confirmation: bool = False
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    requires_review: bool = False


class PendingConfirmation(BaseModel):
    """Fix #3: One-time confirmation token returned in post-message response.

    Token is only returned on first proposal — subsequent queries do not
    leak the token.
    """
    tool_call_id: str
    confirmation_token: str
    arguments_sha256: str
    expires_at: str


class TurnResponse(BaseModel):
    id: str
    session_id: str
    turn_number: int
    status: str
    assistant_message_id: str | None = None
    model_provider: str = ""
    model_name: str = ""
    prompt_version: str = ""
    requires_review: bool = False
    created_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class MessageResponse(BaseModel):
    id: str
    session_id: str
    sequence: int
    role: str
    content: str
    structured_content: dict[str, Any] | None = None
    tool_call_id: str | None = None
    created_at: datetime


class PostMessageResponse(BaseModel):
    session_id: str
    turn_id: str
    assistant_message: str
    decision_type: str
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    pending_confirmations: list[PendingConfirmation] = Field(default_factory=list)
    missing_parameters: list[dict[str, Any]] = Field(default_factory=list)
    requires_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    prompt_version: str = ""
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class ConfirmToolCallRequest(BaseModel):
    confirmation_token: str


class RejectToolCallRequest(BaseModel):
    pass


class ErrorDetail(BaseModel):
    detail: str
    error_code: str | None = None


class SessionCancelResponse(BaseModel):
    session_id: str
    status: str
