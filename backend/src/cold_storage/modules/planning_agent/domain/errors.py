"""Planning agent domain errors."""

from __future__ import annotations


class PlanningAgentError(Exception):
    """Base error for all planning agent domain errors."""


class SessionNotFoundError(PlanningAgentError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session not found: {session_id}")
        self.session_id = session_id


class InvalidTransitionError(PlanningAgentError):
    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(f"Invalid transition for {entity}: {current} -> {target}")
        self.entity = entity
        self.current = current
        self.target = target


class UnauthorizedError(PlanningAgentError):
    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(detail)


class UnregisteredToolError(PlanningAgentError):
    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool not registered: {tool_name}")
        self.tool_name = tool_name


class ToolArgumentValidationError(PlanningAgentError):
    def __init__(self, tool_name: str, errors: list[str]) -> None:
        super().__init__(f"Tool {tool_name} argument validation failed: {errors}")
        self.tool_name = tool_name
        self.validation_errors = errors


class ConfirmationExpiredError(PlanningAgentError):
    def __init__(self, confirmation_id: str) -> None:
        super().__init__(f"Confirmation expired: {confirmation_id}")
        self.confirmation_id = confirmation_id


class ConfirmationAlreadyUsedError(PlanningAgentError):
    def __init__(self, confirmation_id: str) -> None:
        super().__init__(f"Confirmation already used: {confirmation_id}")
        self.confirmation_id = confirmation_id


class StaleConfirmationError(PlanningAgentError):
    def __init__(self, confirmation_id: str, detail: str = "Arguments changed") -> None:
        super().__init__(f"Stale confirmation {confirmation_id}: {detail}")
        self.confirmation_id = confirmation_id


class ConcurrentTurnError(PlanningAgentError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session {session_id} already has a processing turn")
        self.session_id = session_id


class ToolCallLimitExceededError(PlanningAgentError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Tool call limit exceeded: {limit}")
        self.limit = limit


class ModelGatewayError(PlanningAgentError):
    def __init__(self, detail: str = "Model gateway unavailable") -> None:
        super().__init__(detail)


class InvalidStructuredOutputError(PlanningAgentError):
    def __init__(self, detail: str = "Invalid structured output from model") -> None:
        super().__init__(detail)


class ApprovedVersionWriteError(PlanningAgentError):
    def __init__(self, version_id: str) -> None:
        super().__init__(f"Cannot modify approved version: {version_id}")
        self.version_id = version_id


class SessionCompletedError(PlanningAgentError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session is completed and cannot accept new turns: {session_id}")
        self.session_id = session_id


class IdempotencyKeyReplayError(PlanningAgentError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Idempotency key already processed: {key}")
        self.key = key
