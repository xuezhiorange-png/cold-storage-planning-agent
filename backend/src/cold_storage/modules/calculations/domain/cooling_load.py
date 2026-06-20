"""Cooling load calculator — deterministic, Decimal-based.

Computes refrigeration load components for cold rooms:
- Envelope (transmission) load
- Product (sensible + packaging + respiration) load
- Infiltration (ventilation) load
- Internal (people, lighting, equipment, fans) load
- Defrost load
- Summary with diversity factor and design margin

Design rules:
- Uses ``decimal.Decimal`` for all arithmetic.
- Pure function — no database or network access.
- Returns a ``CalculationResult`` with step-by-step traceability.
- Units: all loads in kW(r), temperatures in °C, areas in m².
- Coefficients are injected via the ``CoefficientSet`` parameter.

Boundary with equipment capability:
- This calculator outputs load demands in kW(r).
- Equipment sizing (evaporator, compressor, condenser) is in equipment.py.
- Installed power (kW(e)) is in power.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from cold_storage.modules.calculations.domain.errors import (
    CoefficientMissingError,
    InvalidCalculationInputError,
    MissingCalculationInputError,
)
from cold_storage.modules.calculations.domain.models import (
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CoefficientReference,
)

CALCULATOR_NAME = "cooling_load"
CALCULATOR_VERSION = "1.0.0"

_D = Decimal


# ---------------------------------------------------------------------------
# Coefficient set — injected at call time
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoefficientSet:
    """Set of coefficients for the cooling load calculation.

    Each coefficient carries value, unit, revision_id, source_type, and
    approval status.  Demo/unverified coefficients trigger warnings.
    """

    wall_u_value: Decimal | None = None
    roof_u_value: Decimal | None = None
    floor_u_value: Decimal | None = None
    product_specific_heat: Decimal | None = None  # kJ/(kg·K)
    respiration_heat: Decimal | None = None  # W/kg
    air_change_rate: Decimal | None = None  # 1/h
    worker_heat_gain: Decimal | None = None  # W/person
    design_margin_ratio: Decimal = _D("1.10")
    diversity_factor: Decimal = _D("1.0")
    evaporating_temp_diff: Decimal = _D("5")  # K
    condenser_heat_rejection_factor: Decimal = _D("1.25")
    compressor_cop: Decimal | None = None
    motor_efficiency: Decimal | None = None

    # Metadata for traceability
    revision_ids: dict[str, str] = field(default_factory=dict)
    source_types: dict[str, str] = field(default_factory=dict)

    def get_coefficient_metadata(self, code: str) -> dict[str, Any]:
        """Return metadata for a coefficient used in traceability."""
        return {
            "revision_id": self.revision_ids.get(code, "demo"),
            "source_type": self.source_types.get(code, "demo"),
            "requires_review": self.source_types.get(code, "demo") != "approved",
        }


# ---------------------------------------------------------------------------
# Temperature level grouping
# ---------------------------------------------------------------------------


class TemperatureLevel(StrEnum):
    """Temperature levels for cold room grouping."""

    MEDIUM_TEMPERATURE = "medium_temperature"  # 0~5°C
    LOW_TEMPERATURE = "low_temperature"  # -18~-25°C
    PRECOOLING = "precooling"  # 0~5°C
    SPECIAL_PROCESS = "special_process"  # other


# ---------------------------------------------------------------------------
# Zone input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneCoolingLoadInput:
    """Cooling load inputs for a single zone / cold room."""

    zone_code: str
    zone_name: str
    temperature_level: TemperatureLevel

    # Geometry
    zone_area: Decimal  # m²
    room_height: Decimal  # m
    wall_area: Decimal  # m² (total wall surface)
    roof_area: Decimal  # m²
    floor_area: Decimal  # m²

    # Envelope U-values (W/(m²·K)) — from coefficient set or project input
    u_value_wall: Decimal | None = None
    u_value_roof: Decimal | None = None
    u_value_floor: Decimal | None = None

    # Temperatures (°C)
    outdoor_design_temperature: Decimal = _D("35")
    adjacent_temperature: Decimal | None = None  # temperature of adjacent space
    room_design_temperature: Decimal = _D("0")
    room_relative_humidity: Decimal = _D("0.85")

    # Operating hours
    operating_hours_per_day: Decimal = _D("24")

    # Product load inputs
    product_mass_per_day: Decimal = _D("0")  # kg/day
    product_entry_temperature: Decimal = _D("25")  # °C
    product_target_temperature: Decimal = _D("0")  # °C
    product_specific_heat: Decimal | None = None  # kJ/(kg·K), overrides coefficient
    cooling_duration: Decimal = _D("4")  # h
    packaging_mass: Decimal = _D("0")  # kg
    packaging_specific_heat: Decimal = _D("1.67")  # kJ/(kg·K)

    # Infiltration / ventilation
    room_volume: Decimal | None = None  # m³, computed if None
    infiltration_airflow: Decimal | None = None  # m³/h, overrides air change rate
    door_opening_factor: Decimal = _D("1.0")
    air_curtain_factor: Decimal = _D("1.0")

    # Internal loads
    worker_count: int = 0
    worker_heat_gain: Decimal | None = None  # W/person, overrides coefficient
    lighting_power: Decimal = _D("0")  # W
    equipment_power: Decimal = _D("0")  # W (electrical input)
    fan_motor_power: Decimal = _D("0")  # W (evaporator fans)
    motor_efficiency: Decimal | None = None  # ratio, overrides coefficient
    operating_fraction: Decimal = _D("1.0")  # fraction of operating hours

    # Defrost
    defrost_power: Decimal = _D("0")  # W
    defrost_duration: Decimal = _D("0")  # h/day
    heat_recovery_fraction: Decimal = _D("0")  # fraction of defrost heat recovered


@dataclass(frozen=True)
class CoolingLoadCalcInput:
    """Top-level input for the cooling load calculator."""

    zones: list[ZoneCoolingLoadInput]
    coefficients: CoefficientSet
    design_margin_ratio: Decimal | None = None  # overrides coefficient
    diversity_factor: Decimal | None = None  # overrides coefficient


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _require_coefficient(
    cs: CoefficientSet, code: str, value: Decimal | None, calculator: str
) -> Decimal:
    """Return the coefficient value or raise CoefficientMissingError."""
    if value is not None:
        return value
    raise CoefficientMissingError(calculator, code)


def _warn_demo(cs: CoefficientSet, code: str, warnings: list[CalculationWarning]) -> None:
    """Add a warning if the coefficient source type is not approved."""
    meta = cs.get_coefficient_metadata(code)
    if meta["source_type"] != "approved":
        warnings.append(
            CalculationWarning(
                code="DEMO_COEFFICIENT",
                message=f"Coefficient {code} uses demo/unverified value",
                details=meta,
            )
        )


# ---------------------------------------------------------------------------
# Zone cooling load calculator
# ---------------------------------------------------------------------------


def _calculate_zone_cooling_load(
    zone: ZoneCoolingLoadInput,
    cs: CoefficientSet,
    warnings: list[CalculationWarning],
    steps: list[CalculationStep],
    coeff_refs: list[CoefficientReference],
) -> dict[str, Any]:
    """Calculate all load components for a single zone.

    Returns a dict with all load components in kW(r).
    """
    step_counter = 0

    def _next_step_id(prefix: str) -> str:
        nonlocal step_counter
        step_counter += 1
        return f"{prefix}-{step_counter:03d}"

    # --- 1. Envelope (transmission) load ---
    u_wall = _require_coefficient(cs, "cooling.wall_u_value", zone.u_value_wall, CALCULATOR_NAME)
    u_roof = _require_coefficient(cs, "cooling.roof_u_value", zone.u_value_roof, CALCULATOR_NAME)
    u_floor = _require_coefficient(cs, "cooling.floor_u_value", zone.u_value_floor, CALCULATOR_NAME)

    _warn_demo(cs, "cooling.wall_u_value", warnings)
    _warn_demo(cs, "cooling.roof_u_value", warnings)
    _warn_demo(cs, "cooling.floor_u_value", warnings)

    # Temperature difference for walls: outdoor - room
    delta_t_wall = zone.outdoor_design_temperature - zone.room_design_temperature
    if delta_t_wall < 0:
        raise InvalidCalculationInputError(
            CALCULATOR_NAME, "outdoor_design_temperature", zone.outdoor_design_temperature
        )

    # Adjacent temperature for floor/ceiling: use adjacent or outdoor
    t_adjacent = (
        zone.adjacent_temperature
        if zone.adjacent_temperature is not None
        else zone.outdoor_design_temperature
    )
    delta_t_floor = t_adjacent - zone.room_design_temperature
    if delta_t_floor < 0:
        delta_t_floor = _D("0")  # no cooling needed if adjacent is colder

    # Transmission loads in W (U × A × ΔT)
    wall_load_w = (u_wall * zone.wall_area * delta_t_wall).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )
    roof_load_w = (u_roof * zone.roof_area * delta_t_wall).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )
    floor_load_w = (u_floor * zone.floor_area * delta_t_floor).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    # Convert W → kW(r)
    wall_load_kw = (wall_load_w / _D("1000")).quantize(_D("0.001"), rounding=ROUND_HALF_UP)
    roof_load_kw = (roof_load_w / _D("1000")).quantize(_D("0.001"), rounding=ROUND_HALF_UP)
    floor_load_kw = (floor_load_w / _D("1000")).quantize(_D("0.001"), rounding=ROUND_HALF_UP)
    total_transmission_kw = wall_load_kw + roof_load_kw + floor_load_kw

    steps.append(
        CalculationStep(
            step_id=_next_step_id("CL"),
            formula="Q = U × A × ΔT  (wall: outdoor-room, floor: adjacent-room)",
            description=f"Envelope transmission load — {zone.zone_name}",
            inputs={
                "u_wall": str(u_wall),
                "u_roof": str(u_roof),
                "u_floor": str(u_floor),
                "wall_area": str(zone.wall_area),
                "roof_area": str(zone.roof_area),
                "floor_area": str(zone.floor_area),
                "delta_t_wall": str(delta_t_wall),
                "delta_t_floor": str(delta_t_floor),
            },
            output_name="total_transmission_load_kw_r",
            output_value=str(total_transmission_kw),
        )
    )

    # --- 2. Product load ---
    product_load_kw = _D("0")
    if zone.product_mass_per_day > 0:
        c_product = _require_coefficient(
            cs, "cooling.product_specific_heat", zone.product_specific_heat, CALCULATOR_NAME
        )
        _warn_demo(cs, "cooling.product_specific_heat", warnings)

        delta_t_product = zone.product_entry_temperature - zone.product_target_temperature
        if delta_t_product < 0:
            raise InvalidCalculationInputError(
                CALCULATOR_NAME,
                "product_entry_temperature",
                zone.product_entry_temperature,
            )

        # Sensible heat: Q = m × c × ΔT / (t × 3600)  → kW
        if zone.cooling_duration > 0:
            product_sensible_kw = (
                zone.product_mass_per_day
                * c_product
                * delta_t_product
                / zone.cooling_duration
                / _D("3600")
            ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)
        else:
            product_sensible_kw = _D("0")
            warnings.append(
                CalculationWarning(
                    code="ZERO_COOLING_DURATION",
                    message=f"Zone {zone.zone_code}: cooling_duration is zero",
                )
            )

        # Packaging load
        packaging_kw = _D("0")
        if zone.packaging_mass > 0 and zone.cooling_duration > 0:
            packaging_kw = (
                zone.packaging_mass
                * zone.packaging_specific_heat
                * delta_t_product
                / zone.cooling_duration
                / _D("3600")
            ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

        # Respiration heat (only for applicable products at appropriate temperatures)
        respiration_kw = _D("0")
        if zone.temperature_level in (
            TemperatureLevel.MEDIUM_TEMPERATURE,
            TemperatureLevel.PRECOOLING,
        ):
            resp_heat = cs.respiration_heat
            if resp_heat is not None:
                _warn_demo(cs, "cooling.respiration_heat", warnings)
                coeff_refs.append(
                    CoefficientReference(
                        revision_id=cs.revision_ids.get("cooling.respiration_heat", "demo"),
                        code="cooling.respiration_heat",
                        value=resp_heat,
                        unit="W/kg",
                        status="demo"
                        if cs.source_types.get("cooling.respiration_heat", "demo") != "approved"
                        else "approved",
                        source_type=cs.source_types.get("cooling.respiration_heat", "demo"),
                        requires_review=cs.source_types.get("cooling.respiration_heat", "demo")
                        != "approved",
                    )
                )
                respiration_kw = (zone.product_mass_per_day * resp_heat / _D("1000")).quantize(
                    _D("0.001"), rounding=ROUND_HALF_UP
                )

        product_load_kw = product_sensible_kw + packaging_kw + respiration_kw

        steps.append(
            CalculationStep(
                step_id=_next_step_id("CL"),
                formula="Q_product = m × c × ΔT / (t × 3600) + packaging + respiration",
                description=f"Product load — {zone.zone_name}",
                inputs={
                    "product_mass_per_day": str(zone.product_mass_per_day),
                    "specific_heat": str(c_product),
                    "delta_t": str(delta_t_product),
                    "cooling_duration": str(zone.cooling_duration),
                    "packaging_load_kw": str(packaging_kw),
                    "respiration_load_kw": str(respiration_kw),
                },
                output_name="total_product_load_kw_r",
                output_value=str(product_load_kw),
            )
        )

    # --- 3. Infiltration / ventilation load ---
    infiltration_kw = _D("0")
    volume = (
        zone.room_volume if zone.room_volume is not None else (zone.zone_area * zone.room_height)
    )
    air_change_rate = _require_coefficient(
        cs, "cooling.air_change_rate", cs.air_change_rate, CALCULATOR_NAME
    )
    _warn_demo(cs, "cooling.air_change_rate", warnings)

    if air_change_rate > 0 and volume > 0:
        # Air density ≈ 1.2 kg/m³, specific heat ≈ 1.006 kJ/(kg·K)
        air_density = _D("1.2")
        air_specific_heat = _D("1.006")  # kJ/(kg·K)

        # Base infiltration: air change rate × volume
        base_airflow = air_change_rate * volume  # m³/h

        # Apply door opening and air curtain factors
        effective_airflow = base_airflow * zone.door_opening_factor * zone.air_curtain_factor

        delta_t_air = zone.outdoor_design_temperature - zone.room_design_temperature

        # Sensible infiltration load: Q = ρ × V̇ × cp × ΔT / 3600  → kW
        sensible_infiltration_kw = (
            air_density * effective_airflow * air_specific_heat * delta_t_air / _D("3600")
        ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

        infiltration_kw = sensible_infiltration_kw

        steps.append(
            CalculationStep(
                step_id=_next_step_id("CL"),
                formula="Q_infiltration = ρ × V̇ × cp × ΔT / 3600",
                description=f"Infiltration/ventilation load — {zone.zone_name}",
                inputs={
                    "air_change_rate": str(air_change_rate),
                    "volume": str(volume),
                    "door_opening_factor": str(zone.door_opening_factor),
                    "air_curtain_factor": str(zone.air_curtain_factor),
                    "delta_t_air": str(delta_t_air),
                },
                output_name="total_infiltration_load_kw_r",
                output_value=str(infiltration_kw),
            )
        )

    # --- 4. Internal loads ---
    # People load
    worker_gain = _require_coefficient(
        cs, "cooling.worker_heat_gain", zone.worker_heat_gain, CALCULATOR_NAME
    )
    _warn_demo(cs, "cooling.worker_heat_gain", warnings)

    people_kw = (
        Decimal(str(zone.worker_count)) * worker_gain * zone.operating_fraction / _D("1000")
    ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

    # Lighting load
    lighting_kw = (zone.lighting_power * zone.operating_fraction / _D("1000")).quantize(
        _D("0.001"), rounding=ROUND_HALF_UP
    )

    # Equipment load: only the heat dissipated into the cold room
    # Not all electrical power becomes heat load — use motor efficiency
    motor_eff = _require_coefficient(
        cs, "power.motor_efficiency", zone.motor_efficiency, CALCULATOR_NAME
    )
    _warn_demo(cs, "power.motor_efficiency", warnings)
    equipment_dissipation_factor = _D("1") - motor_eff  # motor losses become heat
    internal_equipment_kw = (
        zone.equipment_power * zone.operating_fraction * equipment_dissipation_factor / _D("1000")
    ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

    # Evaporator fan load (all fan power becomes heat in the cold room)
    fan_kw = (zone.fan_motor_power * zone.operating_fraction / _D("1000")).quantize(
        _D("0.001"), rounding=ROUND_HALF_UP
    )

    total_internal_kw = people_kw + lighting_kw + internal_equipment_kw + fan_kw

    steps.append(
        CalculationStep(
            step_id=_next_step_id("CL"),
            formula="Q_internal = people + lighting + equipment_dissipation + fans",
            description=f"Internal loads — {zone.zone_name}",
            inputs={
                "worker_count": str(zone.worker_count),
                "worker_heat_gain": str(worker_gain),
                "lighting_power": str(zone.lighting_power),
                "equipment_power": str(zone.equipment_power),
                "fan_motor_power": str(zone.fan_motor_power),
                "motor_efficiency": str(motor_eff),
                "operating_fraction": str(zone.operating_fraction),
            },
            output_name="total_internal_load_kw_r",
            output_value=str(total_internal_kw),
        )
    )

    # --- 5. Defrost load ---
    defrost_kw = _D("0")
    if zone.defrost_power > 0 and zone.defrost_duration > 0:
        # Average defrost load over the day
        defrost_kw = (
            zone.defrost_power
            * zone.defrost_duration
            * (1 - zone.heat_recovery_fraction)
            / zone.operating_hours_per_day
            / _D("1000")
        ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

        steps.append(
            CalculationStep(
                step_id=_next_step_id("CL"),
                formula="Q_defrost = P × t × (1-η) / operating_hours / 1000",
                description=f"Defrost load — {zone.zone_name}",
                inputs={
                    "defrost_power": str(zone.defrost_power),
                    "defrost_duration": str(zone.defrost_duration),
                    "heat_recovery_fraction": str(zone.heat_recovery_fraction),
                },
                output_name="defrost_load_kw_r",
                output_value=str(defrost_kw),
            )
        )

    # --- 6. Zone subtotal ---
    subtotal_kw = (
        total_transmission_kw + product_load_kw + infiltration_kw + total_internal_kw + defrost_kw
    )

    steps.append(
        CalculationStep(
            step_id=_next_step_id("CL"),
            formula="subtotal = transmission + product + infiltration + internal + defrost",
            description=f"Zone load subtotal — {zone.zone_name}",
            inputs={
                "transmission": str(total_transmission_kw),
                "product": str(product_load_kw),
                "infiltration": str(infiltration_kw),
                "internal": str(total_internal_kw),
                "defrost": str(defrost_kw),
            },
            output_name="subtotal_load_kw_r",
            output_value=str(subtotal_kw),
        )
    )

    return {
        "zone_code": zone.zone_code,
        "zone_name": zone.zone_name,
        "temperature_level": zone.temperature_level.value,
        "transmission_load_kw_r": float(total_transmission_kw),
        "wall_transmission_load_kw_r": float(wall_load_kw),
        "roof_transmission_load_kw_r": float(roof_load_kw),
        "floor_transmission_load_kw_r": float(floor_load_kw),
        "product_load_kw_r": float(product_load_kw),
        "infiltration_load_kw_r": float(infiltration_kw),
        "internal_load_kw_r": float(total_internal_kw),
        "people_load_kw_r": float(people_kw),
        "lighting_load_kw_r": float(lighting_kw),
        "internal_equipment_load_kw_r": float(internal_equipment_kw),
        "evaporator_fan_load_kw_r": float(fan_kw),
        "defrost_load_kw_r": float(defrost_kw),
        "subtotal_load_kw_r": float(subtotal_kw),
    }


# ---------------------------------------------------------------------------
# Top-level calculator
# ---------------------------------------------------------------------------


def calculate_cooling_load(inp: CoolingLoadCalcInput) -> CalculationResult:
    """Run the cooling load calculation for all zones and return a traceable result.

    This calculator:
    1. Computes load components for each zone.
    2. Groups zones by temperature level.
    3. Applies diversity factor to each temperature level.
    4. Applies design margin to get final design refrigeration load.
    5. Returns traceable steps for every calculation.
    """
    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []
    coeff_refs: list[CoefficientReference] = []

    if not inp.zones:
        raise MissingCalculationInputError(CALCULATOR_NAME, "zones")

    # Override design margin from input or coefficient
    design_margin = inp.design_margin_ratio or inp.coefficients.design_margin_ratio
    diversity = inp.diversity_factor or inp.coefficients.diversity_factor

    # --- Phase 1: calculate zone loads ---
    zone_results: list[dict[str, Any]] = []
    for zone in inp.zones:
        zone_result = _calculate_zone_cooling_load(
            zone, inp.coefficients, warnings, steps, coeff_refs
        )
        zone_results.append(zone_result)

    # --- Phase 2: group by temperature level ---
    level_groups: dict[str, list[dict[str, Any]]] = {}
    for zr in zone_results:
        level = zr["temperature_level"]
        level_groups.setdefault(level, []).append(zr)

    level_summaries: list[dict[str, Any]] = []
    total_subtotal = _D("0")

    for level_code, zones_in_level in level_groups.items():
        level_subtotal = _D("0")
        for zr in zones_in_level:
            level_subtotal += _D(str(zr["subtotal_load_kw_r"]))

        # Apply diversity factor to temperature level total
        diversified = (level_subtotal * diversity).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

        level_summaries.append(
            {
                "temperature_level_code": level_code,
                "room_count": len(zones_in_level),
                "subtotal_load_kw_r": float(level_subtotal),
                "diversified_load_kw_r": float(diversified),
                "zones": [zr["zone_code"] for zr in zones_in_level],
            }
        )

        total_subtotal += level_subtotal

    steps.append(
        CalculationStep(
            step_id="CL-GROUP",
            formula="group by temperature_level, apply diversity_factor per level",
            description="Temperature level grouping and diversity adjustment",
            inputs={
                "levels": str(list(level_groups.keys())),
                "diversity_factor": str(diversity),
            },
            output_name="total_subtotal_load_kw_r",
            output_value=str(total_subtotal),
        )
    )

    # --- Phase 3: total load with design margin ---
    total_diversified = _D("0")
    for ls in level_summaries:
        total_diversified += _D(str(ls["diversified_load_kw_r"]))

    design_margin_value = (total_diversified * (design_margin - _D("1"))).quantize(
        _D("0.001"), rounding=ROUND_HALF_UP
    )
    design_refrigeration_load = (total_diversified + design_margin_value).quantize(
        _D("0.001"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="CL-FINAL",
            formula="design_load = diversified × design_margin_ratio",
            description="Final design refrigeration load with margin",
            inputs={
                "total_diversified_load_kw_r": str(total_diversified),
                "design_margin_ratio": str(design_margin),
                "design_margin_kw_r": str(design_margin_value),
            },
            output_name="design_refrigeration_load_kw_r",
            output_value=str(design_refrigeration_load),
        )
    )

    # Check for demo coefficients
    _cs = inp.coefficients
    has_demo = any(
        _cs.source_types.get(code, "demo") != "approved"
        for code in [
            "cooling.wall_u_value",
            "cooling.roof_u_value",
            "cooling.floor_u_value",
            "cooling.product_specific_heat",
            "cooling.air_change_rate",
            "cooling.worker_heat_gain",
            "power.motor_efficiency",
        ]
        if _cs.source_types.get(code) is not None
    )
    # Also check if any coefficient was used from defaults (demo)
    if not inp.coefficients.source_types:
        has_demo = True
        warnings.append(
            CalculationWarning(
                code="NO_COEFFICIENT_SOURCES",
                message="No coefficient source metadata provided; all coefficients treated as demo",
            )
        )

    # Build result dict
    result_dict: dict[str, Any] = {
        "zones": zone_results,
        "temperature_levels": level_summaries,
        "total_subtotal_load_kw_r": float(total_subtotal),
        "diversity_factor": str(diversity),
        "total_diversified_load_kw_r": float(total_diversified),
        "design_margin_ratio": str(design_margin),
        "design_margin_kw_r": float(design_margin_value),
        "design_refrigeration_load_kw_r": float(design_refrigeration_load),
    }

    # Input snapshot (serialize Decimal to string)
    input_snapshot: dict[str, Any] = {
        "zone_count": len(inp.zones),
        "design_margin_ratio": str(design_margin),
        "diversity_factor": str(diversity),
    }

    return CalculationResult(
        success=True,
        calculator_name=CALCULATOR_NAME,
        calculator_version=CALCULATOR_VERSION,
        input_snapshot=input_snapshot,
        result=result_dict,
        steps=steps,
        coefficient_references=coeff_refs,
        warnings=warnings,
        requires_review=has_demo or any(w.code == "DEMO_COEFFICIENT" for w in warnings),
    )
