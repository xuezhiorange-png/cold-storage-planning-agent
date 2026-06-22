"""Planning agent domain enumerations."""

from enum import StrEnum


class SessionStatus(StrEnum):
    ACTIVE = "active"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class TurnStatus(StrEnum):
    PROCESSING = "processing"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolCallStatus(StrEnum):
    PROPOSED = "proposed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ConfirmationStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AuthorizationLevel(StrEnum):
    READ = "read"
    CALCULATE = "calculate"
    WRITE = "write"
    ADMINISTRATIVE = "administrative"


class DecisionType(StrEnum):
    ASK_CLARIFICATION = "ask_clarification"
    ANSWER = "answer"
    PROPOSE_TOOLS = "propose_tools"
