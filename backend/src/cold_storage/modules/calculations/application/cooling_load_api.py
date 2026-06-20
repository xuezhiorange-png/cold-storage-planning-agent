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
from cold_storage.modules.calculations.domain.errors import (
    InvalidCalculationInputError,
    MissingCalculationInputError,
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


def _require_field(data: dict[str, Any], field: str, calculator: str = "cooling_load") -> Any:
    """Return the value or raise MissingCalculationInputError."""
    if field not in data or data[field] is None:
        raise MissingCalculationInputError(calculator, field)
    return data[field]


def build_cooling_load_input(inputs: dict[str, Any]) -> CoolingLoadCalcInput:
    """Build a CoolingLoadCalcInput from a flat dict.

    Required fields are validated explicitly — no hidden defaults.
    Engineering coefficients (design_margin_ratio, diversity_factor)
    must be provided via the coefficients dict.
    """
    zones_data = inputs.get("zones", [])
    if not zones_data:
        raise MissingCalculationInputError("cooling_load", "zones")

    zones = []
    for z in zones_data:
        # Validate required zone fields
        zone_code = _require_field(z, "zone_code")
        zone_name = _require_field(z, "zone_name")
        zone_area = _to_decimal(_require_field(z, "zone_area"))
        room_height = _to_decimal(_require_field(z, "room_height"))
        wall_area = _to_decimal(_require_field(z, "wall_area"))
        roof_area = _to_decimal(_require_field(z, "roof_area"))
        floor_area = _to_decimal(_require_field(z, "floor_area"))
        outdoor_design_temperature = _to_decimal(_require_field(z, "outdoor_design_temperature"))
        room_design_temperature = _to_decimal(_require_field(z, "room_design_temperature"))
        operating_hours_per_day = _to_decimal(_require_field(z, "operating_hours_per_day"))
        product_entry_temperature = _to_decimal(_require_field(z, "product_entry_temperature"))
        product_target_temperature = _to_decimal(_require_field(z, "product_target_temperature"))
        cooling_duration = _to_decimal(_require_field(z, "cooling_duration"))

        # temperature_level is required — no implicit default
        temp_level_str = _require_field(z, "temperature_level")
        try:
            temperature_level = TemperatureLevel(temp_level_str)
        except ValueError:
            raise InvalidCalculationInputError(
                "cooling_load", "temperature_level", temp_level_str
            ) from None

        zones.append(
            ZoneCoolingLoadInput(
                zone_code=zone_code,
                zone_name=zone_name,
                temperature_level=temperature_level,
                zone_area=zone_area,
                room_height=room_height,
                wall_area=wall_area,
                roof_area=roof_area,
                floor_area=floor_area,
                u_value_wall=(_to_decimal(z["u_value_wall"]) if "u_value_wall" in z else None),
                u_value_roof=(_to_decimal(z["u_value_roof"]) if "u_value_roof" in z else None),
                u_value_floor=(_to_decimal(z["u_value_floor"]) if "u_value_floor" in z else None),
                outdoor_design_temperature=outdoor_design_temperature,
                adjacent_temperature=(
                    _to_decimal(z["adjacent_temperature"]) if "adjacent_temperature" in z else None
                ),
                room_design_temperature=room_design_temperature,
                operating_hours_per_day=operating_hours_per_day,
                product_mass_per_day=_to_decimal(z.get("product_mass_per_day", 0)),
                product_entry_temperature=product_entry_temperature,
                product_target_temperature=product_target_temperature,
                cooling_duration=cooling_duration,
                packaging_mass=_to_decimal(z.get("packaging_mass", 0)),
                worker_count=int(z.get("worker_count", 0)),
                lighting_power=_to_decimal(z.get("lighting_power", 0)),
                equipment_power=_to_decimal(z.get("equipment_power", 0)),
                fan_motor_power=_to_decimal(z.get("fan_motor_power", 0)),
            )
        )

    coeff_data = inputs.get("coefficients", {})

    # design_margin_ratio and diversity_factor are REQUIRED engineering coefficients
    # — they must come from the coefficient resolver, not hidden defaults
    design_margin_raw = coeff_data.get("design_margin_ratio")
    diversity_factor_raw = coeff_data.get("diversity_factor")
    if design_margin_raw is None:
        raise MissingCalculationInputError("cooling_load", "design_margin_ratio")
    if diversity_factor_raw is None:
        raise MissingCalculationInputError("cooling_load", "diversity_factor")

    cs = CoefficientSet(
        wall_u_value=(
            _to_decimal(coeff_data["wall_u_value"]) if "wall_u_value" in coeff_data else None
        ),
        roof_u_value=(
            _to_decimal(coeff_data["roof_u_value"]) if "roof_u_value" in coeff_data else None
        ),
        floor_u_value=(
            _to_decimal(coeff_data["floor_u_value"]) if "floor_u_value" in coeff_data else None
        ),
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
        design_margin_ratio=_to_decimal(design_margin_raw),
        diversity_factor=_to_decimal(diversity_factor_raw),
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
