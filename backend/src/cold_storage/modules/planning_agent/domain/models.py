"""Planning agent domain models — frozen dataclasses and value objects."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cold_storage.modules.planning_agent.domain.enums import (
    AuthorizationLevel,
    ConfirmationStatus,
    DecisionType,
    MessageRole,
    SessionStatus,
    ToolCallStatus,
    TurnStatus,
)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


def sha256_json(obj: Any) -> str:
    """Deterministic SHA-256 over JSON-serialisable object."""
    canonical = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentSession:
    id: str = field(default_factory=_new_id)
    project_id: str | None = None
    project_version_id: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    title: str = ""
    created_by: str = ""
    created_at: datetime = field(default_factory=_now_utc)
    updated_at: datetime = field(default_factory=_now_utc)
    closed_at: datetime | None = None
    next_message_sequence: int = 1
    next_turn_sequence: int = 1
    version: int = 1


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentMessage:
    id: str = field(default_factory=_new_id)
    session_id: str = ""
    sequence: int = 1
    role: MessageRole = MessageRole.USER
    content: str = ""
    structured_content: dict[str, Any] | None = None
    tool_call_id: str | None = None
    created_at: datetime = field(default_factory=_now_utc)


# ---------------------------------------------------------------------------
# Turn
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentTurn:
    id: str = field(default_factory=_new_id)
    session_id: str = ""
    turn_number: int = 1
    status: TurnStatus = TurnStatus.PROCESSING
    user_message_id: str = ""
    assistant_message_id: str | None = None
    model_provider: str = ""
    model_name: str = ""
    prompt_version: str = ""
    request_sha256: str = ""
    decision_snapshot: dict[str, Any] | None = None
    warning_messages: list[str] = field(default_factory=list)
    requires_review: bool = False
    created_at: datetime = field(default_factory=_now_utc)
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Tool request (returned by model gateway)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentToolRequest:
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# ---------------------------------------------------------------------------
# Decision (returned by model gateway)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentDecision:
    decision_type: DecisionType = DecisionType.ANSWER
    assistant_message: str = ""
    missing_parameters: list[dict[str, Any]] = field(default_factory=list)
    tool_requests: list[AgentToolRequest] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    requires_review: bool = False
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool call
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentToolCall:
    id: str = field(default_factory=_new_id)
    session_id: str = ""
    turn_id: str = ""
    tool_name: str = ""
    tool_version: str = "1.0.0"
    authorization_level: AuthorizationLevel = AuthorizationLevel.READ
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_sha256: str = ""
    status: ToolCallStatus = ToolCallStatus.PROPOSED
    result: dict[str, Any] | None = None
    result_reference: str | None = None
    warning_messages: list[str] = field(default_factory=list)
    requires_review: bool = False
    proposed_at: datetime = field(default_factory=_now_utc)
    confirmed_at: datetime | None = None
    executed_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentConfirmation:
    id: str = field(default_factory=_new_id)
    tool_call_id: str = ""
    session_id: str = ""
    confirmation_token_hash: str = ""
    arguments_sha256: str = ""
    confirmed_by: str = ""
    status: ConfirmationStatus = ConfirmationStatus.ACTIVE
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=_now_utc)
    used_at: datetime | None = None


# ---------------------------------------------------------------------------
# Tool result (for tool adapter output)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentToolResult:
    tool_name: str = ""
    tool_version: str = "1.0.0"
    output: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    requires_review: bool = False
    persisted: bool = False
