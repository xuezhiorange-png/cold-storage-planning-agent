"""Deterministic fake gateways for testing.

Completely deterministic, no network access, no external SDK dependency.
Returns fixed structured decisions based on fixed test inputs.
"""

from __future__ import annotations

import re

from cold_storage.modules.planning_agent.domain.enums import DecisionType
from cold_storage.modules.planning_agent.domain.gateways import (
    AgentModelRequest,
    GatewayMetadata,
)
from cold_storage.modules.planning_agent.domain.models import AgentDecision, AgentToolRequest


class FakeAgentModelGateway:
    """Deterministic fake model gateway for tests and local dev."""

    GATEWAY_VERSION = "1.0.0"

    def generate_decision(self, request: AgentModelRequest) -> AgentDecision:
        # Extract last user message
        user_text = ""
        for msg in reversed(request.messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        # Deterministic routing based on keywords
        if "蓝莓" in user_text or "blueberry" in user_text.lower():
            if "吨" in user_text or "kg" in user_text.lower():
                return AgentDecision(
                    decision_type=DecisionType.PROPOSE_TOOLS,
                    assistant_message="检测到蓝莓加工厂规划需求，准备执行通量和面积计算。",
                    tool_requests=[
                        AgentToolRequest(
                            tool_name="planning.calculate_throughput_inventory_area",
                            arguments={
                                "daily_inbound_mass_kg": _extract_tons(user_text) * 1000,
                                "working_time_h_per_day": _extract_hours(user_text),
                            },
                            reason="用户提供了产品类型和产能信息",
                        ),
                    ],
                    requires_review=True,
                    warnings=["使用演示系数，结果需专业复核"],
                )
            return AgentDecision(
                decision_type=DecisionType.ASK_CLARIFICATION,
                assistant_message="请提供日入库量（吨/天）和工作时间（小时/天）。",
                missing_parameters=[
                    {
                        "name": "daily_inbound_mass_kg",
                        "reason": "required_by_tool",
                        "expected_unit": "kg",
                    },
                    {
                        "name": "working_time_h_per_day",
                        "reason": "required_by_tool",
                        "expected_unit": "hours",
                    },
                ],
            )

        if "方案" in user_text or "scheme" in user_text.lower():
            if "project_id" in user_text or "项目" in user_text:
                return AgentDecision(
                    decision_type=DecisionType.PROPOSE_TOOLS,
                    assistant_message="准备生成方案对比。",
                    tool_requests=[
                        AgentToolRequest(
                            tool_name="scheme.generate_and_compare",
                            arguments={"project_id": "demo", "version_number": 1},
                            reason="用户请求方案生成",
                        ),
                    ],
                    requires_review=True,
                )
            return AgentDecision(
                decision_type=DecisionType.ASK_CLARIFICATION,
                assistant_message="请指定项目ID。",
                missing_parameters=[
                    {"name": "project_id", "reason": "required_by_tool", "expected_unit": None},
                ],
            )

        # Default: plain answer
        return AgentDecision(
            decision_type=DecisionType.ANSWER,
            assistant_message="我已收到您的消息。请提供更多规划参数以便执行计算。",
        )

    def get_metadata(self) -> GatewayMetadata:
        return GatewayMetadata(
            provider="fake",
            model_name="fake-deterministic-v1",
            gateway_version=self.GATEWAY_VERSION,
            production_ready=False,
            requires_review=True,
        )


class DefaultAgentModelGateway:
    """Default gateway — falls back to fake when no production provider configured."""

    def __init__(self, provider: str = "fake", model_name: str = "none") -> None:
        self._provider = provider
        self._model_name = model_name
        self._production_ready = False
        self._fake = FakeAgentModelGateway()

    def generate_decision(self, request: AgentModelRequest) -> AgentDecision:
        if not self._production_ready:
            return self._fake.generate_decision(request)
        raise NotImplementedError("Production model gateway not yet configured")

    def get_metadata(self) -> GatewayMetadata:
        return GatewayMetadata(
            provider=self._provider,
            model_name=self._model_name,
            gateway_version="1.0.0",
            production_ready=self._production_ready,
            requires_review=not self._production_ready,
        )


def _extract_tons(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*吨", text)
    if match:
        return float(match.group(1))
    return 25.0  # default demo


def _extract_hours(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", text)
    if match:
        return float(match.group(1))
    return 16.0  # default demo
