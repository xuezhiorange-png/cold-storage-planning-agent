"""Planning agent domain errors and frozen provider failure metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


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


class AgentProviderFailureCode(StrEnum):
    """The closed set of safe, machine-readable provider failure identities."""

    AGENT_PROVIDER_CONFIGURATION_MISSING = "AGENT_PROVIDER_CONFIGURATION_MISSING"
    AGENT_PROVIDER_CONFIGURATION_INVALID = "AGENT_PROVIDER_CONFIGURATION_INVALID"
    AGENT_PROVIDER_CREDENTIAL_INVALID = "AGENT_PROVIDER_CREDENTIAL_INVALID"
    AGENT_PROVIDER_TIMEOUT = "AGENT_PROVIDER_TIMEOUT"
    AGENT_PROVIDER_CONNECTION_FAILED = "AGENT_PROVIDER_CONNECTION_FAILED"
    AGENT_PROVIDER_RATE_LIMITED = "AGENT_PROVIDER_RATE_LIMITED"
    AGENT_PROVIDER_UPSTREAM_5XX = "AGENT_PROVIDER_UPSTREAM_5XX"
    AGENT_PROVIDER_RESPONSE_MALFORMED = "AGENT_PROVIDER_RESPONSE_MALFORMED"
    AGENT_PROVIDER_RESPONSE_TOO_LARGE = "AGENT_PROVIDER_RESPONSE_TOO_LARGE"
    AGENT_PROVIDER_UNAVAILABLE = "AGENT_PROVIDER_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class AgentProviderFailureMetadata:
    """Safe external metadata for one frozen provider failure identity."""

    code: AgentProviderFailureCode
    safe_message: str
    retryable: bool


ProviderFailureCode = AgentProviderFailureCode
ProviderFailureMetadata = AgentProviderFailureMetadata

_PROVIDER_FAILURE_METADATA: dict[AgentProviderFailureCode, AgentProviderFailureMetadata] = {
    AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING,
        "agent provider configuration is missing",
        False,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID,
        "agent provider configuration is invalid",
        False,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_CREDENTIAL_INVALID: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_CREDENTIAL_INVALID,
        "agent provider credentials are invalid",
        False,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT,
        "agent provider request timed out",
        True,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_CONNECTION_FAILED: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_CONNECTION_FAILED,
        "agent provider connection failed",
        True,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_RATE_LIMITED: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_RATE_LIMITED,
        "agent provider rate limited",
        True,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_UPSTREAM_5XX: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_UPSTREAM_5XX,
        "agent provider upstream failure",
        True,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED,
        "agent provider response is malformed",
        False,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE,
        "agent provider response is too large",
        False,
    ),
    AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE: AgentProviderFailureMetadata(
        AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE,
        "agent provider is unavailable",
        True,
    ),
}
PROVIDER_FAILURE_METADATA: Mapping[AgentProviderFailureCode, AgentProviderFailureMetadata] = (
    MappingProxyType(_PROVIDER_FAILURE_METADATA)
)
PROVIDER_FAILURE_CODES = tuple(AgentProviderFailureCode)
FROZEN_PROVIDER_FAILURE_CODES = PROVIDER_FAILURE_CODES


def provider_failure_metadata(
    code: AgentProviderFailureCode | str,
) -> AgentProviderFailureMetadata:
    """Return only the frozen safe metadata for a provider failure code."""

    try:
        normalized = AgentProviderFailureCode(code)
    except ValueError as exc:
        raise ValueError("unknown provider failure code") from exc
    return PROVIDER_FAILURE_METADATA[normalized]


class ModelGatewayError(PlanningAgentError):
    def __init__(
        self,
        detail: str = "Model gateway unavailable",
        *,
        code: AgentProviderFailureCode | str | None = None,
    ) -> None:
        self.code = AgentProviderFailureCode(code) if code is not None else None
        self.provider_failure_code = self.code
        if self.code is None:
            self.safe_message: str | None = None
            self.retryable: bool | None = None
        else:
            metadata = provider_failure_metadata(self.code)
            self.safe_message = metadata.safe_message
            self.retryable = metadata.retryable
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
