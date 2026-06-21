"""Tests for FakeAgentModelGateway and DefaultAgentModelGateway.

Updated for Fix #7: no silent defaults — gateway returns ask_clarification
when critical params (tons, hours) are missing.
"""

from __future__ import annotations

from cold_storage.modules.planning_agent.domain.enums import DecisionType
from cold_storage.modules.planning_agent.domain.gateways import AgentModelRequest
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import (
    DefaultAgentModelGateway,
    FakeAgentModelGateway,
)


class TestFakeAgentModelGateway:
    def setup_method(self):
        self.gateway = FakeAgentModelGateway()

    def test_deterministic_blueberry_with_tons_and_hours(self):
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "我有25吨蓝莓需要入库，每天工作16小时"}],
        )
        d1 = self.gateway.generate_decision(req)
        d2 = self.gateway.generate_decision(req)
        assert d1 == d2
        assert d1.decision_type == DecisionType.PROPOSE_TOOLS
        assert len(d1.tool_requests) == 1
        assert d1.tool_requests[0].tool_name == "planning.calculate_throughput_inventory_area"
        # Verify args are correctly extracted (Fix #7: no silent defaults)
        args = d1.tool_requests[0].arguments
        assert args["daily_inbound_mass_kg"] == 25.0
        assert args["working_time_h_per_day"] == 16.0

    def test_blueberry_without_hours_returns_clarification(self):
        """Fix #7: Missing hours → ask_clarification, NOT silent default."""
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "我有25吨蓝莓需要入库"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.decision_type == DecisionType.ASK_CLARIFICATION
        missing_names = [p["name"] for p in d.missing_parameters]
        assert "working_time_h_per_day" in missing_names

    def test_blueberry_without_tons_returns_clarification(self):
        """Fix #7: Missing tons → ask_clarification, NOT silent default."""
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "我想做蓝莓加工厂规划，每天工作16小时"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.decision_type == DecisionType.ASK_CLARIFICATION
        missing_names = [p["name"] for p in d.missing_parameters]
        assert "daily_inbound_mass_kg" in missing_names

    def test_blueberry_without_params(self):
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "我想做一个蓝莓加工厂规划"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.decision_type == DecisionType.ASK_CLARIFICATION
        assert len(d.missing_parameters) >= 2

    def test_scheme_request(self):
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "帮我生成项目方案 项目ID是abc"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.decision_type == DecisionType.PROPOSE_TOOLS
        assert d.tool_requests[0].tool_name == "scheme.generate_and_compare"

    def test_plain_answer(self):
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "你好"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.decision_type == DecisionType.ANSWER
        assert len(d.tool_requests) == 0

    def test_metadata(self):
        m = self.gateway.get_metadata()
        assert m.provider == "fake"
        assert m.production_ready is False

    def test_requires_review_only_when_tools_proposed(self):
        """requires_review is True only when tools are proposed."""
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "25吨蓝莓 16小时"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.requires_review is True

    def test_clarification_has_no_requires_review(self):
        """ask_clarification decisions should not have requires_review."""
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "我想做蓝莓加工厂规划"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.requires_review is False

    def test_empty_messages(self):
        req = AgentModelRequest(messages=[])
        d = self.gateway.generate_decision(req)
        assert d.decision_type == DecisionType.ANSWER

    def test_non_user_messages(self):
        req = AgentModelRequest(
            messages=[{"role": "assistant", "content": "test"}],
        )
        d = self.gateway.generate_decision(req)
        assert d.decision_type == DecisionType.ANSWER


class TestDefaultAgentModelGateway:
    def test_falls_back_to_fake(self):
        gw = DefaultAgentModelGateway()
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "25吨蓝莓 16小时"}],
        )
        d = gw.generate_decision(req)
        assert d.decision_type == DecisionType.PROPOSE_TOOLS

    def test_falls_back_to_fake_clarification(self):
        gw = DefaultAgentModelGateway()
        req = AgentModelRequest(
            messages=[{"role": "user", "content": "25吨蓝莓"}],
        )
        d = gw.generate_decision(req)
        assert d.decision_type == DecisionType.ASK_CLARIFICATION

    def test_metadata_not_production_ready(self):
        gw = DefaultAgentModelGateway()
        m = gw.get_metadata()
        assert m.production_ready is False
        assert m.requires_review is True

    def test_custom_provider(self):
        gw = DefaultAgentModelGateway(provider="openai", model_name="gpt-4")
        m = gw.get_metadata()
        assert m.provider == "openai"
        assert m.model_name == "gpt-4"
