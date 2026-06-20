"""API-level service for cooling load calculation endpoint.

Handles input parsing, calculation execution, and result formatting.
Keeps engineering formula logic out of app.py routes.

This module lives in the API layer — it may depend on domain calculators
and application services, but it must not contain engineering formulas.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from cold_storage.modules.calculations.domain.cooling_load import (
    CoefficientSet,
    CoolingLoadCalcInput,
    TemperatureLevel,
    ZoneCoolingLoadInput,
    calculate_cooling_load,
)
from cold_storage.modules.calculations.domain.models import CalculationResult


def _to_decimal(value: Any) -> Decimal:
    """Safely convert a value to Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError(f"Cannot convert {type(value)} to Decimal")


def build_cooling_load_input(inputs: dict[str, Any]) -> CoolingLoadCalcInput:
    """Build a CoolingLoadCalcInput from a flat dict.

    This is an input-parsing function, not an engineering formula.
    """
    zones_data = inputs.get("zones", [])
    zones = []
    for z in zones_data:
        zones.append(
            ZoneCoolingLoadInput(
                zone_code=z.get("zone_code", "unknown"),
                zone_name=z.get("zone_name", "Unknown Zone"),
                temperature_level=TemperatureLevel(
                    z.get("temperature_level", "medium_temperature")
                ),
                zone_area=_to_decimal(z.get("zone_area", 0)),
                room_height=_to_decimal(z.get("room_height", 4)),
                wall_area=_to_decimal(z.get("wall_area", 0)),
                roof_area=_to_decimal(z.get("roof_area", 0)),
                floor_area=_to_decimal(z.get("floor_area", 0)),
                u_value_wall=_to_decimal(z["u_value_wall"]) if "u_value_wall" in z else None,
                u_value_roof=_to_decimal(z["u_value_roof"]) if "u_value_roof" in z else None,
                u_value_floor=_to_decimal(z["u_value_floor"]) if "u_value_floor" in z else None,
                outdoor_design_temperature=_to_decimal(z.get("outdoor_design_temperature", 35)),
                adjacent_temperature=(
                    _to_decimal(z["adjacent_temperature"]) if "adjacent_temperature" in z else None
                ),
                room_design_temperature=_to_decimal(z.get("room_design_temperature", 0)),
                operating_hours_per_day=_to_decimal(z.get("operating_hours_per_day", 24)),
                product_mass_per_day=_to_decimal(z.get("product_mass_per_day", 0)),
                product_entry_temperature=_to_decimal(z.get("product_entry_temperature", 25)),
                product_target_temperature=_to_decimal(z.get("product_target_temperature", 0)),
                cooling_duration=_to_decimal(z.get("cooling_duration", 4)),
                packaging_mass=_to_decimal(z.get("packaging_mass", 0)),
                worker_count=int(z.get("worker_count", 0)),
                lighting_power=_to_decimal(z.get("lighting_power", 0)),
                equipment_power=_to_decimal(z.get("equipment_power", 0)),
                fan_motor_power=_to_decimal(z.get("fan_motor_power", 0)),
            )
        )

    coeff_data = inputs.get("coefficients", {})
    cs = CoefficientSet(
        wall_u_value=_to_decimal(coeff_data["wall_u_value"])
        if "wall_u_value" in coeff_data
        else None,
        roof_u_value=_to_decimal(coeff_data["roof_u_value"])
        if "roof_u_value" in coeff_data
        else None,
        floor_u_value=_to_decimal(coeff_data["floor_u_value"])
        if "floor_u_value" in coeff_data
        else None,
        product_specific_heat=(
            _to_decimal(coeff_data["product_specific_heat"])
            if "product_specific_heat" in coeff_data
            else None
        ),
        respiration_heat=(
            _to_decimal(coeff_data["respiration_heat"])
            if "respiration_heat" in coeff_data
            else None
        ),
        air_change_rate=(
            _to_decimal(coeff_data["air_change_rate"]) if "air_change_rate" in coeff_data else None
        ),
        worker_heat_gain=(
            _to_decimal(coeff_data["worker_heat_gain"])
            if "worker_heat_gain" in coeff_data
            else None
        ),
        design_margin_ratio=_to_decimal(coeff_data.get("design_margin_ratio", "1.10")),
        diversity_factor=_to_decimal(coeff_data.get("diversity_factor", "1.0")),
        motor_efficiency=(
            _to_decimal(coeff_data["motor_efficiency"])
            if "motor_efficiency" in coeff_data
            else None
        ),
    )

    return CoolingLoadCalcInput(zones=zones, coefficients=cs)


def run_cooling_load_from_dict(inputs: dict[str, Any]) -> CalculationResult:
    """Parse inputs, run calculation, and return result.

    This is the single entry point for the API layer — app.py should
    call only this function.
    """
    calc_input = build_cooling_load_input(inputs)
    return calculate_cooling_load(calc_input)
