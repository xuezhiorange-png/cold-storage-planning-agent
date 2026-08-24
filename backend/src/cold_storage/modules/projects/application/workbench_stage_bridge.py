"""Bridge cold-room zone planning outputs into five-stage calculator inputs.

Demo geometry and coefficient defaults are explicit workbench bridging only.
They do not change calculator formulas; missing refrigerated zones fail closed.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from cold_storage.modules.calculations.application.cooling_load_api import build_cooling_load_input
from cold_storage.modules.calculations.domain.cooling_load import (
    TemperatureLevel,
    calculate_cooling_load,
)
from cold_storage.modules.calculations.domain.equipment import (
    EquipmentCapabilityCalcInput,
    EquipmentCoefficientSet,
    TemperatureSystemInput,
    ZoneEquipmentInput,
    calculate_equipment_capability,
)
from cold_storage.modules.calculations.domain.models import CalculationResult as NewCalculationResult
from cold_storage.modules.calculations.domain.power import (
    InstalledPowerCalcInput,
    calculate_installed_power,
)
from cold_storage.modules.planning.application.service import as_float

POWER_CONFIGURATION_CALCULATOR = "power_configuration"

# Demo bridging coefficients — always unverified and require review.
DEMO_COOLING_COEFFICIENTS: dict[str, str] = {
    "design_margin_ratio": "1.10",
    "diversity_factor": "0.85",
    "product_specific_heat": "3.6",
    "respiration_heat": "0.0",
    "air_change_rate": "0.5",
    "worker_heat_gain": "0.275",
    "motor_efficiency": "0.85",
    "wall_u_value": "0.25",
    "roof_u_value": "0.20",
    "floor_u_value": "0.30",
}

DEMO_EQUIPMENT_COEFFICIENTS: dict[str, str] = {
    "redundancy_ratio": "1.0",
    "evaporator_capacity_margin": "1.1",
    "condenser_capacity_margin": "1.1",
    "compressor_cop": "2.5",
}


class WorkbenchStageBridgeError(Exception):
    """Fail-closed bridge error when required stage inputs cannot be built."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def _derive_geometry(area_m2: float, room_height: float = 5.0) -> dict[str, str]:
    area = max(area_m2, 1.0)
    side = math.sqrt(area)
    perimeter = 4 * side
    return {
        "zone_area": str(round(area, 2)),
        "room_height": str(room_height),
        "wall_area": str(round(perimeter * room_height, 2)),
        "roof_area": str(round(area, 2)),
        "floor_area": str(round(area, 2)),
    }


def _temperature_band_to_level(band: str, zone_name: str) -> TemperatureLevel | None:
    if band == "常温":
        return None
    if "预冷" in zone_name or "precool" in zone_name.lower():
        return TemperatureLevel.PRECOOLING
    if "-18" in band or "冻" in band:
        return TemperatureLevel.LOW_TEMPERATURE
    return TemperatureLevel.MEDIUM_TEMPERATURE


def _room_design_temperature(level: TemperatureLevel) -> str:
    if level is TemperatureLevel.LOW_TEMPERATURE:
        return "-18.0"
    return "2.0"


def _evaporation_temperature(level: TemperatureLevel) -> str:
    if level is TemperatureLevel.LOW_TEMPERATURE:
        return "-25.0"
    if level is TemperatureLevel.PRECOOLING:
        return "-2.0"
    return "-5.0"


def build_cooling_load_raw_inputs(
    zones: list[dict[str, Any]],
    project_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Build cooling-load calculator inputs from persisted zone planning zones."""
    working_hours = as_float(project_inputs.get("working_time_h_per_day", 16))
    cooling_zones: list[dict[str, Any]] = []

    for zone in zones:
        if not isinstance(zone, dict):
            continue
        band = str(zone.get("temperature_band", ""))
        zone_name = str(zone.get("zone_name", ""))
        level = _temperature_band_to_level(band, zone_name)
        if level is None:
            continue

        area = as_float(zone.get("required_area_m2", 0))
        if area <= 0:
            continue

        geometry = _derive_geometry(area)
        room_temp = _room_design_temperature(level)
        cooling_zones.append(
            {
                "zone_code": str(zone.get("zone_code", zone_name)),
                "zone_name": zone_name,
                "temperature_level": level.value,
                **geometry,
                "u_value_wall": DEMO_COOLING_COEFFICIENTS["wall_u_value"],
                "u_value_roof": DEMO_COOLING_COEFFICIENTS["roof_u_value"],
                "u_value_floor": DEMO_COOLING_COEFFICIENTS["floor_u_value"],
                "outdoor_design_temperature": "30.0",
                "room_design_temperature": room_temp,
                "operating_hours_per_day": str(working_hours),
                "product_entry_temperature": "20.0",
                "product_target_temperature": room_temp,
                "cooling_duration": "8.0",
                "worker_heat_gain": DEMO_COOLING_COEFFICIENTS["worker_heat_gain"],
                "motor_efficiency": DEMO_COOLING_COEFFICIENTS["motor_efficiency"],
            }
        )

    if not cooling_zones:
        raise WorkbenchStageBridgeError(
            "WORKBENCH_COOLING_ZONES_MISSING",
            "制冷负荷阶段缺少可计算的冷藏分区",
            {"zone_count": len(zones)},
        )

    return {
        "zones": cooling_zones,
        "coefficients": dict(DEMO_COOLING_COEFFICIENTS),
    }


def run_cooling_load_stage(raw_inputs: dict[str, Any]) -> NewCalculationResult:
    calc_input = build_cooling_load_input(raw_inputs)
    return calculate_cooling_load(calc_input)


def build_equipment_raw_inputs(
    cooling_result: NewCalculationResult,
    zones: list[dict[str, Any]],
) -> dict[str, Any]:
    """Group refrigerated zones by evaporation temperature for equipment sizing."""
    if not cooling_result.success:
        raise WorkbenchStageBridgeError(
            "WORKBENCH_COOLING_STAGE_FAILED",
            "设备选型阶段的上游制冷负荷计算未成功",
        )

    cooling_zones = cooling_result.result.get("zones", [])
    if not isinstance(cooling_zones, list):
        raise WorkbenchStageBridgeError(
            "WORKBENCH_COOLING_ZONES_INVALID",
            "制冷负荷结果缺少分区明细",
        )

    load_by_code: dict[str, Decimal] = {}
    for zone in cooling_zones:
        if not isinstance(zone, dict):
            continue
        code = str(zone.get("zone_code", ""))
        load = zone.get("design_refrigeration_load_kw_r", zone.get("total_zone_load_kw_r", 0))
        load_by_code[code] = Decimal(str(load))

    systems: dict[str, dict[str, Any]] = {}
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        band = str(zone.get("temperature_band", ""))
        zone_name = str(zone.get("zone_name", ""))
        level = _temperature_band_to_level(band, zone_name)
        if level is None:
            continue
        code = str(zone.get("zone_code", zone_name))
        evap_temp = _evaporation_temperature(level)
        system_key = evap_temp
        if system_key not in systems:
            systems[system_key] = {
                "system_code": f"SYS_{evap_temp.replace('.', '_').replace('-', 'm')}",
                "system_name": f"系统 {evap_temp}℃",
                "design_evaporating_temperature": evap_temp,
                "zones": [],
            }
        systems[system_key]["zones"].append(
            {
                "zone_code": code,
                "zone_name": zone_name,
                "design_cooling_load_kw_r": str(load_by_code.get(code, Decimal("0"))),
                "evaporator_count": max(int(as_float(zone.get("position_count", 1))), 1),
                "evaporation_temperature_c": evap_temp,
                "defrost_method": "electric",
            }
        )

    if not systems:
        raise WorkbenchStageBridgeError(
            "WORKBENCH_EQUIPMENT_ZONES_MISSING",
            "设备选型阶段缺少可用的冷藏分区",
        )

    return {
        "condensing_temperature_c": "40.0",
        "systems": list(systems.values()),
        "coefficients": dict(DEMO_EQUIPMENT_COEFFICIENTS),
    }


def run_equipment_stage(raw_inputs: dict[str, Any]) -> NewCalculationResult:
    systems_raw = raw_inputs.get("systems", [])
    systems: list[TemperatureSystemInput] = []
    for system in systems_raw:
        if not isinstance(system, dict):
            continue
        zone_inputs = [
            ZoneEquipmentInput(
                zone_code=str(z["zone_code"]),
                zone_name=str(z["zone_name"]),
                design_cooling_load_kw_r=Decimal(str(z["design_cooling_load_kw_r"])),
                evaporator_count=int(z.get("evaporator_count", 1)),
                evaporation_temperature_c=Decimal(str(z.get("evaporation_temperature_c", "-10"))),
                defrost_method=str(z.get("defrost_method", "electric")),
            )
            for z in system.get("zones", [])
            if isinstance(z, dict)
        ]
        systems.append(
            TemperatureSystemInput(
                system_code=str(system["system_code"]),
                system_name=str(system["system_name"]),
                design_evaporating_temperature=Decimal(
                    str(system.get("design_evaporating_temperature", "-10"))
                ),
                zones=zone_inputs,
            )
        )

    coeff_raw = raw_inputs.get("coefficients", {})
    coeff = coeff_raw if isinstance(coeff_raw, dict) else {}
    coefficient_set = EquipmentCoefficientSet(
        redundancy_ratio=Decimal(str(coeff.get("redundancy_ratio", "1.0"))),
        evaporator_capacity_margin=Decimal(str(coeff.get("evaporator_capacity_margin", "1.1"))),
        condenser_capacity_margin=Decimal(str(coeff.get("condenser_capacity_margin", "1.1"))),
        compressor_cop=Decimal(str(coeff.get("compressor_cop", "2.5"))),
        revision_statuses={},
    )
    typed_input = EquipmentCapabilityCalcInput(
        systems=systems,
        coefficients=coefficient_set,
    )
    return calculate_equipment_capability(typed_input)


def build_power_raw_inputs(
    equipment_result: NewCalculationResult,
    cooling_result: NewCalculationResult,
) -> dict[str, Any]:
    if not equipment_result.success:
        raise WorkbenchStageBridgeError(
            "WORKBENCH_EQUIPMENT_STAGE_FAILED",
            "装机功率阶段的上游设备选型计算未成功",
        )

    equipment_payload = equipment_result.result
    compressor_kw = equipment_payload.get("total_compressor_input_power_kw_e", 0)
    evaporator_fan_kw = cooling_result.result.get("total_evaporator_fan_load_kw_r", 0)
    if evaporator_fan_kw == 0:
        # Aggregate from zone rows when the total field is absent.
        zones = cooling_result.result.get("zones", [])
        if isinstance(zones, list):
            evaporator_fan_kw = sum(
                float(z.get("evaporator_fan_load_kw_r", 0))
                for z in zones
                if isinstance(z, dict)
            )

    condenser_kw = float(equipment_payload.get("total_condenser_rejection_kw", 0)) * 0.03
    return {
        "compressor_input_power_kw_e": str(compressor_kw),
        "evaporator_fan_power_kw_e": str(evaporator_fan_kw),
        "condenser_fan_power_kw_e": str(round(condenser_kw, 2)),
    }


def run_power_stage(raw_inputs: dict[str, Any]) -> NewCalculationResult:
    typed_input = InstalledPowerCalcInput(
        compressor_input_power_kw_e=Decimal(str(raw_inputs.get("compressor_input_power_kw_e", 0))),
        evaporator_fan_power_kw_e=Decimal(str(raw_inputs.get("evaporator_fan_power_kw_e", 0))),
        condenser_fan_power_kw_e=Decimal(str(raw_inputs.get("condenser_fan_power_kw_e", 0))),
    )
    return calculate_installed_power(typed_input)
