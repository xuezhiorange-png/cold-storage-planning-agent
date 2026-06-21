"""Tool adapters for planning calculations → CalculationService / PlanningService."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.planning.application.service import (
    build_zone_plan_from_inputs,
)
from cold_storage.modules.planning_agent.domain.models import AgentToolResult


class ThroughputInventoryAreaAdapter:
    """Adapts planning.calculate_throughput_inventory_area."""

    def __init__(self, zone_planner: Any, investment_estimator: Any) -> None:
        self._zone_planner = zone_planner
        self._investment_estimator = investment_estimator

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        zone_result = build_zone_plan_from_inputs(arguments, self._zone_planner)
        from dataclasses import asdict

        return AgentToolResult(
            tool_name="planning.calculate_throughput_inventory_area",
            output={"zone_plan": asdict(zone_result)},
            requires_review=zone_result.requires_review
            if hasattr(zone_result, "requires_review")
            else True,
        )


class CoolingLoadEquipmentAdapter:
    """Adapts planning.calculate_cooling_load_and_equipment."""

    def __init__(self, cooling_service: Any) -> None:
        self._service = cooling_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        result = (
            self._service.orchestrate_core_calculation(arguments)
            if hasattr(self._service, "orchestrate_core_calculation")
            else {}
        )
        return AgentToolResult(
            tool_name="planning.calculate_cooling_load_and_equipment",
            output={"result": result},
            requires_review=True,
        )
