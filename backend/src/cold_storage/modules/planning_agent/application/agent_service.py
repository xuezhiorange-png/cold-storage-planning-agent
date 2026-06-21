"""Legacy agent service — kept for backward compatibility with demo_overview.

The new PlanningAgentService lives in service.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from cold_storage.modules.planning_agent.domain.gateways import AgentModelGateway


@dataclass(frozen=True)
class AgentResponse:
    message: str
    structured_output: dict[str, object]
    tool_calls: list[str]


class LegacyPlanningAgentService:
    """Legacy agent service using the old single-prompt pattern."""

    def __init__(self, model_gateway: AgentModelGateway) -> None:
        self.model_gateway = model_gateway

    def handle_message(self, message: str) -> AgentResponse:
        from cold_storage.modules.planning_agent.domain.gateways import AgentModelRequest

        request = AgentModelRequest(messages=[{"role": "user", "content": message}])
        decision = self.model_gateway.generate_decision(request)
        return AgentResponse(
            message=decision.assistant_message,
            structured_output={
                "decision_type": decision.decision_type.value,
                "missing_parameters": decision.missing_parameters,
            },
            tool_calls=[tr.tool_name for tr in decision.tool_requests],
        )
