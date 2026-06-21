"""Deterministic fake gateways for testing.

Completely deterministic, no network access, no external SDK dependency.
Returns fixed structured decisions based on fixed test inputs.

Fix #7: No silent defaulting of critical engineering parameters.
When required params are missing, returns ask_clarification.
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
            tons = _extract_tons(user_text)
            hours = _extract_hours(user_text)

            # Fix #7: No silent defaults — ask_clarification if missing
            if tons is None or hours is None:
                missing = []
                if tons is None:
                    missing.append(
                        {
                            "name": "daily_inbound_mass_kg",
                            "reason": "required_by_tool",
                            "expected_unit": "kg",
                        }
                    )
                if hours is None:
                    missing.append(
                        {
                            "name": "working_time_h_per_day",
                            "reason": "required_by_tool",
                            "expected_unit": "hours",
                        }
                    )
                return AgentDecision(
                    decision_type=DecisionType.ASK_CLARIFICATION,
                    assistant_message="请提供日入库量（吨/天）和工作时间（小时/天）。",
                    missing_parameters=missing,
                )

            return AgentDecision(
                decision_type=DecisionType.PROPOSE_TOOLS,
                assistant_message="检测到蓝莓加工厂规划需求，准备执行通量和面积计算。",
                tool_requests=[
                    AgentToolRequest(
                        tool_name="planning.calculate_throughput_inventory_area",
                        arguments={
                            "daily_inbound_mass_kg": tons,
                            "working_time_h_per_day": hours,
                        },
                        reason="用户提供了产品类型和产能信息",
                    ),
                ],
                requires_review=True,
                warnings=["使用演示系数，结果需专业复核"],
            )

        if "方案" in user_text or "scheme" in user_text.lower():
            # Fix #7: Extract project_id from user text, never hardcode "demo"
            project_id = _extract_project_id(user_text)
            if project_id is None:
                return AgentDecision(
                    decision_type=DecisionType.ASK_CLARIFICATION,
                    assistant_message="请提供项目ID以生成方案对比。",
                    missing_parameters=[
                        {"name": "project_id", "reason": "required_by_tool", "expected_unit": None},
                    ],
                )
            version_number = _extract_version_number(user_text)
            return AgentDecision(
                decision_type=DecisionType.PROPOSE_TOOLS,
                assistant_message="准备生成方案对比。",
                tool_requests=[
                    AgentToolRequest(
                        tool_name="scheme.generate_and_compare",
                        arguments={"project_id": project_id, "version_number": version_number},
                        reason="用户请求方案生成",
                    ),
                ],
                requires_review=True,
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


def _extract_tons(text: str) -> float | None:
    """Extract tonnage from text. Returns None if not found (no silent default)."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*吨", text)
    if match:
        return float(match.group(1))
    match_kg = re.search(r"(\d+(?:\.\d+)?)\s*kg", text, re.IGNORECASE)
    if match_kg:
        return float(match_kg.group(1)) / 1000
    return None  # Fix #7: no silent default


def _extract_hours(text: str) -> float | None:
    """Extract working hours from text. Returns None if not found (no silent default)."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", text)
    if match:
        return float(match.group(1))
    return None  # Fix #7: no silent default


def _extract_version_number(text: str) -> int:
    """Extract version number from user text. Defaults to 1 if not found.

    Recognizes patterns like:
    - 版本1 / 版本号1 / version 1 / version_number=1
    """
    match = re.search(r"版本[号]?\s*[=:]?\s*(\d+)", text)
    if match:
        return int(match.group(1))
    match = re.search(r"version[_ ]?number?[=:]?\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 1  # Default to version 1 when not specified


def _extract_project_id(text: str) -> str | None:
    """Extract project_id from user text. Returns None if not found.

    Recognizes patterns like:
    - 项目ID是xxx / 项目ID: xxx / project_id=xxx / project_id: xxx
    """
    # Chinese patterns
    match = re.search(r"项目[Ii][Dd][是:=]\s*(\S+)", text)
    if match:
        return match.group(1)
    # English patterns
    match = re.search(r"project[_ ]?[Ii][Dd][=:]\s*(\S+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None
