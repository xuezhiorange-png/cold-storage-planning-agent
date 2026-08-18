"""Unit tests for the injected-transport OpenAI Responses adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from cold_storage.modules.planning_agent.domain.enums import DecisionType
from cold_storage.modules.planning_agent.domain.errors import (
    AgentProviderFailureCode,
    ModelGatewayError,
    provider_failure_metadata,
)
from cold_storage.modules.planning_agent.domain.gateways import AgentModelRequest
from cold_storage.modules.planning_agent.domain.models import AgentDecision
from cold_storage.modules.planning_agent.infrastructure.real_gateways import (
    MAX_PROVIDER_ATTEMPTS,
    OPENAI_OFFICIAL_BASE_URL,
    OpenAIAgentModelGateway,
)


def _decision_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "decision_type": "propose_tools",
        "assistant_message": "已准备好执行计算。",
        "missing_parameters": [],
        "tool_requests": [
            {
                "tool_name": "planning.calculate_throughput_inventory_area",
                "arguments": {"daily_inbound_mass": 25.0},
                "reason": "根据输入计算面积",
            }
        ],
        "citations": [{"source": "user"}],
        "requires_review": True,
        "warnings": ["请复核计算结果"],
    }
    payload.update(overrides)
    return payload


def _response(payload: Any, *, status: str = "completed", **kwargs: Any) -> Any:
    values: dict[str, Any] = {
        "output_parsed": payload,
        "output_text": None,
        "status": status,
        "incomplete_details": None,
        "error": None,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


class _FakeResponses:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.responses = _FakeResponses(outcomes)


class _ProviderFailure(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"provider status {status_code}")
        self.status_code = status_code


def _gateway(client: _FakeClient, *, max_retries: int = 0) -> OpenAIAgentModelGateway:
    return OpenAIAgentModelGateway(
        client=client,
        model_name="gpt-test",
        timeout_seconds=10,
        max_retries=max_retries,
    )


def test_responses_request_is_bounded_and_strictly_decoded() -> None:
    client = _FakeClient([_response(_decision_payload())])
    gateway = _gateway(client)
    request = AgentModelRequest(
        system_prompt="你是规划助手。",
        messages=[{"role": "user", "content": "请计算面积"}],
        tools=[
            {
                "name": "planning.calculate_throughput_inventory_area",
                "description": "计算面积",
                "input_schema": {
                    "type": "object",
                    "properties": {"daily_inbound_mass": {"type": "number"}},
                    "required": ["daily_inbound_mass"],
                    "additionalProperties": False,
                },
            }
        ],
        max_tokens=321,
    )

    decision = gateway.generate_decision(request)

    assert isinstance(decision, AgentDecision)
    assert decision.decision_type is DecisionType.PROPOSE_TOOLS
    assert decision.tool_requests[0].arguments == {"daily_inbound_mass": 25.0}
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["max_output_tokens"] == 321
    assert call["store"] is False
    assert call["instructions"] == "你是规划助手。"
    assert call["input"] == [{"role": "user", "content": "请计算面积"}]
    assert call["tools"][0]["type"] == "function"
    assert call["tools"][0]["parameters"]["type"] == "object"
    assert "background" not in call
    assert "conversation" not in call


def test_metadata_is_bounded_to_openai_and_explicit_model() -> None:
    gateway = _gateway(_FakeClient([_response(_decision_payload())]))

    metadata = gateway.get_metadata()

    assert metadata.provider == "openai"
    assert metadata.model_name == "gpt-test"
    assert metadata.production_ready is False
    assert metadata.requires_review is True
    assert len(metadata.model_name) <= 128


def test_sdk_retry_budget_is_disabled_at_client_construction() -> None:
    seen: dict[str, Any] = {}
    client = _FakeClient([_response(_decision_payload())])

    def factory(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return client

    OpenAIAgentModelGateway(
        api_key="test-only-key",
        model_name="gpt-test",
        timeout_seconds=10,
        max_retries=1,
        client_factory=factory,
    )

    assert seen == {
        "api_key": "test-only-key",
        "base_url": OPENAI_OFFICIAL_BASE_URL,
        "timeout": 10,
        "max_retries": 0,
    }
    assert MAX_PROVIDER_ATTEMPTS == 2


def test_sdk_factory_ignores_openai_base_url_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    seen: dict[str, Any] = {}
    client = _FakeClient([_response(_decision_payload())])

    def factory(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return client

    OpenAIAgentModelGateway(
        api_key="test-only-key",
        model_name="gpt-test",
        timeout_seconds=10,
        max_retries=0,
        client_factory=factory,
    )

    assert seen["base_url"] == OPENAI_OFFICIAL_BASE_URL
    assert seen["base_url"] != "https://example.invalid/v1"


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (408, AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT),
        (409, AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE),
    ],
)
def test_http_408_and_409_use_explicit_retryable_classification(
    status_code: int, expected_code: AgentProviderFailureCode
) -> None:
    client = _FakeClient([_ProviderFailure(status_code)])
    gateway = _gateway(client, max_retries=0)

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    assert exc_info.value.provider_failure_code is expected_code
    assert exc_info.value.retryable is True
    assert len(client.responses.calls) == 1


def test_http_408_retries_once_then_succeeds() -> None:
    client = _FakeClient([_ProviderFailure(408), _response(_decision_payload())])
    gateway = _gateway(client, max_retries=1)

    decision = gateway.generate_decision(AgentModelRequest())

    assert decision.decision_type is DecisionType.PROPOSE_TOOLS
    assert len(client.responses.calls) == 2


def test_http_408_stops_after_two_attempts() -> None:
    client = _FakeClient([_ProviderFailure(408), _ProviderFailure(408)])
    gateway = _gateway(client, max_retries=1)

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    assert exc_info.value.provider_failure_code is AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT
    assert len(client.responses.calls) == 2


def test_http_409_stops_after_two_attempts() -> None:
    client = _FakeClient(
        [_ProviderFailure(409), _ProviderFailure(409), _response(_decision_payload())]
    )
    gateway = _gateway(client, max_retries=1)

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    assert (
        exc_info.value.provider_failure_code is AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE
    )
    assert exc_info.value.retryable is True
    assert len(client.responses.calls) == 2


@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        (
            _ProviderFailure(401),
            AgentProviderFailureCode.AGENT_PROVIDER_CREDENTIAL_INVALID,
        ),
        (TimeoutError("timeout"), AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT),
        (ConnectionError("connection"), AgentProviderFailureCode.AGENT_PROVIDER_CONNECTION_FAILED),
        (
            _ProviderFailure(429),
            AgentProviderFailureCode.AGENT_PROVIDER_RATE_LIMITED,
        ),
        (
            _ProviderFailure(503),
            AgentProviderFailureCode.AGENT_PROVIDER_UPSTREAM_5XX,
        ),
        (
            _response(None),
            AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED,
        ),
        (
            _response(
                None,
                status="incomplete",
                incomplete_details={"reason": "max_output_tokens"},
            ),
            AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE,
        ),
        (
            _ProviderFailure(413),
            AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_TOO_LARGE,
        ),
        (RuntimeError("provider unavailable"), AgentProviderFailureCode.AGENT_PROVIDER_UNAVAILABLE),
    ],
)
def test_provider_failures_use_only_frozen_codes(
    outcome: Any, expected_code: AgentProviderFailureCode
) -> None:
    client = _FakeClient([outcome])
    gateway = _gateway(client)

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    error = exc_info.value
    assert error.provider_failure_code is expected_code
    metadata = provider_failure_metadata(expected_code)
    assert str(error) == metadata.safe_message
    assert error.safe_message == metadata.safe_message
    assert error.retryable is metadata.retryable


def test_retryable_failure_uses_one_application_retry_only() -> None:
    client = _FakeClient([TimeoutError("first"), _response(_decision_payload())])
    gateway = _gateway(client, max_retries=1)

    decision = gateway.generate_decision(AgentModelRequest())

    assert decision.decision_type is DecisionType.PROPOSE_TOOLS
    assert len(client.responses.calls) == 2


def test_non_retryable_failure_is_not_retried() -> None:
    client = _FakeClient([_response(None), _response(_decision_payload())])
    gateway = _gateway(client, max_retries=1)

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    assert exc_info.value.code is AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED
    assert len(client.responses.calls) == 1


def test_retryable_failure_stops_at_two_attempts() -> None:
    client = _FakeClient([TimeoutError("first"), TimeoutError("second")])
    gateway = _gateway(client, max_retries=1)

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    assert exc_info.value.code is AgentProviderFailureCode.AGENT_PROVIDER_TIMEOUT
    assert len(client.responses.calls) == 2


def test_unknown_response_fields_fail_closed() -> None:
    payload = _decision_payload(unexpected="must be rejected")
    gateway = _gateway(_FakeClient([_response(payload)]))

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    assert exc_info.value.code is AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED


@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    [
        (
            {"model_name": "", "timeout_seconds": 10, "max_retries": 0},
            AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING,
        ),
        (
            {
                "provider": "other",
                "model_name": "gpt-test",
                "timeout_seconds": 10,
                "max_retries": 0,
            },
            AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID,
        ),
        (
            {"model_name": "gpt-test", "timeout_seconds": 0, "max_retries": 0},
            AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID,
        ),
        (
            {"model_name": "gpt-test", "timeout_seconds": 10, "max_retries": 2},
            AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID,
        ),
    ],
)
def test_configuration_failures_reuse_p2a_codes(
    kwargs: dict[str, Any], expected_code: AgentProviderFailureCode
) -> None:
    with pytest.raises(ModelGatewayError) as exc_info:
        OpenAIAgentModelGateway(client=_FakeClient([]), **kwargs)

    assert exc_info.value.code is expected_code


def test_strict_nested_tool_shape_rejects_non_object_arguments() -> None:
    payload = _decision_payload(
        tool_requests=[
            {
                "tool_name": "planning.calculate_throughput_inventory_area",
                "arguments": ["not", "an", "object"],
                "reason": "invalid",
            }
        ]
    )
    gateway = _gateway(_FakeClient([_response(payload)]))

    with pytest.raises(ModelGatewayError) as exc_info:
        gateway.generate_decision(AgentModelRequest())

    assert exc_info.value.code is AgentProviderFailureCode.AGENT_PROVIDER_RESPONSE_MALFORMED
