"""Tool adapters for planning calculations -> CalculationService / PlanningService.

Fix #12: fail closed — raise on missing service/method.
"""

from __future__ import annotations

import uuid
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

        warnings: list[str] = []
        requires_review: bool = (
            zone_result.requires_review if hasattr(zone_result, "requires_review") else True
        )
        output = {
            "source_tool": "planning.calculate_throughput_inventory_area",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {"zone_plan": asdict(zone_result)},
            "warnings": warnings,
            "requires_review": requires_review,
        }
        return AgentToolResult(
            tool_name="planning.calculate_throughput_inventory_area",
            output=output,
        )


class CoolingLoadEquipmentAdapter:
    """Adapts planning.calculate_cooling_load_and_equipment.

    Extracts cooling load, equipment, and power values from the orchestration
    result and maps them to the strict output schema with correct engineering units.
    """

    def __init__(self, cooling_service: Any) -> None:
        self._service = cooling_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        if not hasattr(self._service, "orchestrate_core_calculation"):
            raise PlanningAgentError("CoolingService missing orchestrate_core_calculation method")
        result = self._service.orchestrate_core_calculation(arguments)
        warnings: list[str] = []
        requires_review: bool = True

        # Extract values from orchestration result
        cooling_load_val = 0.0
        equipment_capacity_val = 0.0
        electrical_input_val = 0.0
        condenser_rejection_val = 0.0
        daily_energy_val = 0.0
        equipment_list: list[Any] = []

        if hasattr(result, "cooling_load") and result.cooling_load:
            cl = result.cooling_load
            cooling_load_val = getattr(cl, "value", 0.0) or 0.0
        if hasattr(result, "equipment") and result.equipment:
            eq = result.equipment
            equipment_capacity_val = getattr(eq, "value", 0.0) or 0.0
            # Extract equipment list from structured output
            if hasattr(eq, "output") and isinstance(eq.output, dict):
                equipment_list = eq.output.get("equipment_list", [])
        if hasattr(result, "installed_power") and result.installed_power:
            ip = result.installed_power
            electrical_input_val = getattr(ip, "value", 0.0) or 0.0

        # Condenser heat rejection ≈ cooling load × (1 + 1/COP)
        # Default estimate if not directly available
        condenser_rejection_val = cooling_load_val * 1.25
        # Daily energy ≈ electrical input × operating hours
        daily_energy_val = electrical_input_val * 10.0

        output = {
            "source_tool": "planning.calculate_cooling_load_and_equipment",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {
                "result": {
                    "total_cooling_load_kw": cooling_load_val,
                    "total_cooling_load_unit": "kW(r)",
                    "equipment_list": equipment_list,
                    "total_equipment_capacity_kw": equipment_capacity_val,
                    "total_equipment_capacity_unit": "kW(r)",
                    "total_electrical_input_kw": electrical_input_val,
                    "total_electrical_input_unit": "kW(e)",
                    "condenser_heat_rejection_kw": condenser_rejection_val,
                    "condenser_heat_rejection_unit": "kW(th)",
                    "daily_energy_kwh": daily_energy_val,
                    "daily_energy_unit": "kWh",
                },
            },
            "warnings": warnings,
            "requires_review": requires_review,
        }
        return AgentToolResult(
            tool_name="planning.calculate_cooling_load_and_equipment",
            output=output,
        )
