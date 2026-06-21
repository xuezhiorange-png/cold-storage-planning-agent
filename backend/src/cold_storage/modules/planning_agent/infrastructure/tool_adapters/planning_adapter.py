"""Tool adapters for planning calculations -> CalculationService / PlanningService.

Fix #12: fail closed — raise on missing service/method.
"""

from __future__ import annotations

from typing import Any

from cold_storage.modules.planning.application.service import (
    build_zone_plan_from_inputs,
)
from cold_storage.modules.planning_agent.domain.errors import PlanningAgentError
from cold_storage.modules.planning_agent.domain.models import AgentToolResult


class ThroughputInventoryAreaAdapter:
    """Adapts planning.calculate_throughput_inventory_area.

    Accepts daily_inbound_mass + mass_unit, converts to daily_inbound_mass_kg
    before passing to the calculation service.
    """

    _UNIT_FACTORS = {"kg": 1.0, "tons": 1000.0}

    def __init__(self, zone_planner: Any, investment_estimator: Any) -> None:
        self._zone_planner = zone_planner
        self._investment_estimator = investment_estimator

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        if self._zone_planner is None:
            raise PlanningAgentError(
                "Zone planner not configured — cannot execute throughput calculation"
            )
        # Unit conversion: value + unit → daily_inbound_mass_kg
        calc_args = dict(arguments)
        if "daily_inbound_mass" in calc_args and "mass_unit" in calc_args:
            value = calc_args.pop("daily_inbound_mass")
            unit = calc_args.pop("mass_unit")
            factor = self._UNIT_FACTORS.get(unit)
            if factor is None:
                raise PlanningAgentError(f"Unknown mass unit: {unit}")
            calc_args["daily_inbound_mass_kg"] = value * factor

        zone_result = build_zone_plan_from_inputs(calc_args, self._zone_planner)
        from dataclasses import asdict

        return AgentToolResult(
            tool_name="planning.calculate_throughput_inventory_area",
            output={"zone_plan": asdict(zone_result)},
            requires_review=zone_result.requires_review
            if hasattr(zone_result, "requires_review")
            else True,
        )


class CoolingLoadEquipmentAdapter:
    """Adapts planning.calculate_cooling_load_and_equipment.

    Fix #12: fail closed — raise if service lacks the required method.
    """

    def __init__(self, cooling_service: Any) -> None:
        self._service = cooling_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        # Fix #12: fail closed, never return empty dict on missing method
        if not hasattr(self._service, "orchestrate_core_calculation"):
            raise PlanningAgentError("CoolingService missing orchestrate_core_calculation method")
        result = self._service.orchestrate_core_calculation(arguments)
        return AgentToolResult(
            tool_name="planning.calculate_cooling_load_and_equipment",
            output={"result": result},
            requires_review=True,
        )
