"""Official OpenAI Responses API adapter for the provider-neutral gateway port.

The adapter owns provider transport, strict response decoding, and the bounded
application retry policy.  Provider-native objects never cross this module's
boundary; callers receive an existing ``AgentDecision`` or a classified
``ModelGatewayError``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any, Final

from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    RateLimitError,
    UnprocessableEntityError,
)
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, ValidationError

from cold_storage.bootstrap.settings import get_settings
from cold_storage.modules.planning_agent.domain.enums import DecisionType
from cold_storage.modules.planning_agent.domain.errors import (
    AgentProviderFailureCode,
    ModelGatewayError,
    provider_failure_metadata,
)
from cold_storage.modules.planning_agent.domain.gateways import (
    AgentModelGateway,
    AgentModelRequest,
    GatewayMetadata,
)
from cold_storage.modules.planning_agent.domain.models import (
    AgentDecision,
    AgentToolRequest,
)

OPENAI_SDK_VERSION: Final = "2.53.0"
OPENAI_PROVIDER_ID: Final = "openai"
MAX_PROVIDER_RETRIES: Final = 1
MAX_PROVIDER_ATTEMPTS: Final = 2
MAX_OUTPUT_TOKENS: Final = 8192
MAX_RESPONSE_BYTES: Final = 1_000_000

_MISSING = object()


class _AgentToolRequestPayload(BaseModel):
    """Strict transport schema for one closed domain tool request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    tool_name: StrictStr
    arguments: dict[str, Any]
    reason: StrictStr


class _AgentDecisionPayload(BaseModel):
    """Strict transport schema kept private to the provider adapter."""

    model_config = ConfigDict(extra="forbid", strict=True)

    decision_type: StrictStr
    assistant_message: StrictStr
    missing_parameters: list[dict[str, Any]]
    tool_requests: list[_AgentToolRequestPayload]
    citations: list[dict[str, Any]]
    requires_review: StrictBool
    warnings: list[StrictStr]


def _failure(code: AgentProviderFailureCode) -> ModelGatewayError:
    """Build a gateway error using only the frozen safe provider metadata."""

    return ModelGatewayError(provider_failure_metadata(code).safe_message, code=code)


def _field(value: Any, name: str, default: Any = _MISSING) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _status_code(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if type(status) is int:
        return status
    status = getattr(error, "status", None)
    return status if type(status) is int else None


def _classify_provider_exception(error: BaseException) -> AgentProviderFailureCode:
    """Map SDK/transport failures to the closed P2-A failure taxonomy."""

    if isinstance(error, (APITimeoutError, TimeoutError)):
        return AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT
    if isinstance(error, AuthenticationError):
        return AgentProviderFailureCode.AGENT_PROVIDER_CREDENTIAL_INVALID
    if isinstance(error, RateLimitError):
        return AgentProviderFailureCode.AGENT_PROVIDER_RATE_LIMITED
    if isinstance(error, InternalServerError):
        return AgentProviderFailureCode.AGENT_PROVIDER_UPSTREAM_5XX
    if isinstance(error, (APIConnectionError, ConnectionError, OSError)):
        return AgentProviderFailureCode.AGENT_PROVIDER_CONNECTION_FAILED
    if isinstance(error, (APIResponseValidationError, ValidationError, json.JSONDecodeError)):
        return AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED

    status = _status_code(error)
    if status in (401, 403):
        return AgentProviderFailureCode.AGENT_PROVIDER_CREDENTIAL_INVALID
    if status == 413:
        return AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE
    if status == 429:
        return AgentProviderFailureCode.AGENT_PROVIDER_RATE_LIMITED
    if status is not None and 500 <= status <= 599:
        return AgentProviderFailureCode.AGENT_PROVIDER_UPSTREAM_5XX
    if status is not None and 400 <= status <= 499:
        return AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID
    if isinstance(error, (BadRequestError, UnprocessableEntityError)):
        return AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID
    if isinstance(error, APIStatusError):
        return AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE
    if isinstance(error, APIError):
        return AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE
    if isinstance(error, (TypeError, KeyError, ValueError)):
        return AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED
    return AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE


class OpenAIAgentModelGateway(AgentModelGateway):
    """Strict OpenAI Responses API implementation of ``AgentModelGateway``."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        provider: str | None = None,
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        settings: Any | None = None

        def setting(name: str) -> Any:
            nonlocal settings
            if settings is None:
                try:
                    settings = get_settings()
                except Exception as error:
                    raise _failure(
                        AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID
                    ) from error
            return getattr(settings, name, None)

        injected_transport = client is not None or client_factory is not None
        resolved_provider = provider
        if resolved_provider is None:
            resolved_provider = (
                OPENAI_PROVIDER_ID if injected_transport else setting("agent_provider")
            )
        resolved_model = model_name if model_name is not None else setting("agent_model")
        resolved_timeout = (
            timeout_seconds if timeout_seconds is not None else setting("agent_timeout_seconds")
        )
        resolved_retries = max_retries if max_retries is not None else setting("agent_max_retries")
        resolved_api_key = api_key
        if not injected_transport and resolved_api_key is None:
            resolved_api_key = setting("openai_api_key")

        if not isinstance(resolved_provider, str) or not resolved_provider.strip():
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING)
        if resolved_provider != OPENAI_PROVIDER_ID:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
        if not isinstance(resolved_model, str) or not resolved_model.strip():
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING)
        if type(resolved_timeout) is not int or not 1 <= resolved_timeout <= 30:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
        if type(resolved_retries) is not int or resolved_retries not in (0, 1):
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
        if not injected_transport and (
            not isinstance(resolved_api_key, str) or not resolved_api_key.strip()
        ):
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING)
        if (
            injected_transport
            and resolved_api_key is not None
            and (not isinstance(resolved_api_key, str) or not resolved_api_key.strip())
        ):
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)

        self._model_name = resolved_model
        self._timeout_seconds = resolved_timeout
        self._max_retries = resolved_retries

        if client is not None:
            self._client = client
        else:
            factory = client_factory or OpenAI
            try:
                # The official SDK is deliberately given no custom base URL and
                # owns no retry budget; the application gateway owns retries.
                self._client = factory(
                    api_key=resolved_api_key,
                    timeout=resolved_timeout,
                    max_retries=0,
                )
            except Exception as error:
                raise _failure(_classify_provider_exception(error)) from error

    def get_metadata(self) -> GatewayMetadata:
        return GatewayMetadata(
            provider=OPENAI_PROVIDER_ID,
            model_name=self._model_name,
            gateway_version=f"openai-sdk-{OPENAI_SDK_VERSION}",
            production_ready=False,
            requires_review=True,
        )

    def generate_decision(self, request: AgentModelRequest) -> AgentDecision:
        """Call the provider with zero or one application retry."""

        attempts = 1 + self._max_retries
        if attempts > MAX_PROVIDER_ATTEMPTS:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)

        for attempt in range(attempts):
            try:
                return self._generate_once(request)
            except ModelGatewayError as error:
                if error.retryable is True and attempt + 1 < attempts:
                    continue
                raise

        raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE)

    def _generate_once(self, request: AgentModelRequest) -> AgentDecision:
        payload = self._request_payload(request)
        try:
            response = self._client.responses.parse(**payload)
        except ModelGatewayError:
            raise
        except Exception as error:
            raise _failure(_classify_provider_exception(error)) from error

        try:
            return self._decode_response(response)
        except ModelGatewayError:
            raise
        except Exception as error:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED) from error

    def _request_payload(self, request: AgentModelRequest) -> dict[str, Any]:
        if type(request.max_tokens) is not int or not 1 <= request.max_tokens <= MAX_OUTPUT_TOKENS:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
        if type(request.temperature) is not float or not math.isfinite(request.temperature):
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
        if not 0.0 <= request.temperature <= 2.0:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)

        messages: list[dict[str, str]] = []
        for message in request.messages:
            if not isinstance(message, Mapping):
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or role not in {
                "user",
                "assistant",
                "system",
                "developer",
            }:
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
            if not isinstance(content, str):
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
            messages.append({"role": role, "content": content})

        tools: list[dict[str, Any]] = []
        for tool in request.tools:
            if not isinstance(tool, Mapping):
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
            name = tool.get("name")
            description = tool.get("description", "")
            input_schema = tool.get("input_schema")
            if not isinstance(name, str) or not name.strip():
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
            if not isinstance(description, str):
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
            if not isinstance(input_schema, Mapping):
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID)
            tools.append(
                {
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": dict(input_schema),
                    "strict": True,
                }
            )

        return {
            "model": self._model_name,
            "instructions": request.system_prompt,
            "input": messages,
            "tools": tools,
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
            "store": False,
            "text_format": _AgentDecisionPayload,
        }

    def _decode_response(self, response: Any) -> AgentDecision:
        incomplete = _field(response, "incomplete_details", None)
        reason = _field(incomplete, "reason", None) if incomplete is not None else None
        if reason in {"max_output_tokens", "length"}:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE)
        if _field(response, "status", None) == "incomplete":
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED)
        if _field(response, "error", None) is not None:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE)

        parsed = _field(response, "output_parsed", _MISSING)
        if parsed is _MISSING:
            output_text = _field(response, "output_text", None)
            if not isinstance(output_text, str) or not output_text:
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED)
            if len(output_text.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE)
            try:
                parsed = json.loads(output_text)
            except json.JSONDecodeError as error:
                raise _failure(
                    AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED
                ) from error
        if parsed is None:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED)

        if isinstance(parsed, AgentDecision):
            parsed_value: Any = asdict(parsed)
        elif isinstance(parsed, BaseModel):
            parsed_value = parsed.model_dump(mode="python")
        else:
            parsed_value = parsed

        try:
            if (
                len(json.dumps(parsed_value, ensure_ascii=False).encode("utf-8"))
                > MAX_RESPONSE_BYTES
            ):
                raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE)
        except TypeError as error:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED) from error

        try:
            decoded = _AgentDecisionPayload.model_validate(parsed_value)
        except ValidationError as error:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED) from error

        try:
            decision_type = DecisionType(decoded.decision_type)
        except ValueError as error:
            raise _failure(AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED) from error

        return AgentDecision(
            decision_type=decision_type,
            assistant_message=decoded.assistant_message,
            missing_parameters=[dict(item) for item in decoded.missing_parameters],
            tool_requests=[
                AgentToolRequest(
                    tool_name=item.tool_name,
                    arguments=dict(item.arguments),
                    reason=item.reason,
                )
                for item in decoded.tool_requests
            ],
            citations=[dict(item) for item in decoded.citations],
            requires_review=decoded.requires_review,
            warnings=list(decoded.warnings),
        )


# Explicit aliases keep the infrastructure seam discoverable without creating
# another provider-neutral or production composition surface.
OpenAIModelGateway = OpenAIAgentModelGateway
RealAgentModelGateway = OpenAIAgentModelGateway
