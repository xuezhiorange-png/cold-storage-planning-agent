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

    Strict field-mapping only — no engineering derivations, no fixed ratios,
    no default-zero fallbacks.  All values come from the deterministic
    calculation service; missing required fields cause fail-closed errors.
    Optional fields (condenser, energy) are omitted when upstream does not
    provide them, with a ``not_calculated`` warning.
    """

    def __init__(self, cooling_service: Any) -> None:
        self._service = cooling_service

    def execute(self, arguments: dict[str, Any]) -> AgentToolResult:
        if not hasattr(self._service, "orchestrate_core_calculation"):
            raise PlanningAgentError("CoolingService missing orchestrate_core_calculation method")
        result = self._service.orchestrate_core_calculation(arguments)
        warnings: list[str] = []
        requires_review: bool = True

        # --- Extract required fields from upstream CalculationResult dicts ---

        # Cooling load (kW(r))
        cooling_load_val: float | None = None
        if hasattr(result, "cooling_load") and result.cooling_load is not None:
            cl = getattr(result.cooling_load, "result", {})
            cooling_load_val = cl.get("design_refrigeration_load_kw_r")

        # Equipment capacity (kW(r)) and electrical input (kW(e))
        equipment_capacity_val: float | None = None
        electrical_input_val: float | None = None
        equipment_list: list[Any] = []
        if hasattr(result, "equipment") and result.equipment is not None:
            eq = getattr(result.equipment, "result", {})
            equipment_capacity_val = eq.get("total_compressor_capacity_kw_r")
            electrical_input_val = eq.get("total_compressor_input_power_kw_e")
            if "systems" in eq:
                equipment_list = eq["systems"]

        # Fail closed: required fields must be present
        missing: list[str] = []
        if cooling_load_val is None:
            missing.append("cooling_load (design_refrigeration_load_kw_r)")
        if equipment_capacity_val is None:
            missing.append("equipment_capacity (total_compressor_capacity_kw_r)")
        if electrical_input_val is None:
            missing.append("electrical_input (total_compressor_input_power_kw_e)")
        if missing:
            raise PlanningAgentError(
                f"Upstream calculation missing required fields: {', '.join(missing)}"
            )

        # --- Optional fields: map directly, no derivation ---

        # Condenser heat rejection (kW(th)) — from equipment calc
        condenser_val: float | None = None
        if hasattr(result, "equipment") and result.equipment is not None:
            eq = getattr(result.equipment, "result", {})
            condenser_val = eq.get("total_condenser_rejection_kw")

        # Daily energy (kWh) — from installed_power calc if available
        daily_energy_val: float | None = None
        if hasattr(result, "installed_power") and result.installed_power is not None:
            ip = getattr(result.installed_power, "result", {})
            daily_energy_val = ip.get("total_installed_power_kw_e")

        if condenser_val is None:
            warnings.append("condenser_heat_rejection: not_calculated by upstream")
        if daily_energy_val is None:
            warnings.append("daily_energy: not_calculated by upstream")

        # Build result dict — only include optional fields when present
        result_dict: dict[str, Any] = {
            "total_cooling_load_kw": cooling_load_val,
            "total_cooling_load_unit": "kW(r)",
            "equipment_list": equipment_list,
            "total_equipment_capacity_kw": equipment_capacity_val,
            "total_equipment_capacity_unit": "kW(r)",
            "total_electrical_input_kw": electrical_input_val,
            "total_electrical_input_unit": "kW(e)",
        }
        if condenser_val is not None:
            result_dict["condenser_heat_rejection_kw"] = condenser_val
            result_dict["condenser_heat_rejection_unit"] = "kW(th)"
        if daily_energy_val is not None:
            result_dict["daily_energy_kwh"] = daily_energy_val
            result_dict["daily_energy_unit"] = "kWh"

        output = {
            "source_tool": "planning.calculate_cooling_load_and_equipment",
            "tool_version": "1.0.0",
            "result_id": str(uuid.uuid4()),
            "payload": {
                "result": result_dict,
            },
            "warnings": warnings,
            "requires_review": requires_review,
        }
        return AgentToolResult(
            tool_name="planning.calculate_cooling_load_and_equipment",
            output=output,
        )
