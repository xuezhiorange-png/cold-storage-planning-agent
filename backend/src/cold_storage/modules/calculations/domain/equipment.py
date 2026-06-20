"""Equipment capability calculator — deterministic, Decimal-based.

Computes equipment capability requirements from cooling load results:
- Evaporator capacity requirements
- Compressor capacity requirements (operating + standby)
- Condenser heat rejection requirements
- Temperature system grouping

Design rules:
- Uses ``decimal.Decimal`` for all arithmetic.
- Pure function — no database or network access.
- Returns a ``CalculationResult`` with step-by-step traceability.
- Units: all capacities in kW(r) unless noted; power in kW(e).
- This calculator does NOT select manufacturer models or final equipment types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from cold_storage.modules.calculations.domain.errors import (
    CoefficientMissingError,
    MissingCalculationInputError,
)
from cold_storage.modules.calculations.domain.models import (
    CalculationResult,
    CalculationStep,
    CalculationWarning,
    CoefficientReference,
)

CALCULATOR_NAME = "equipment"
CALCULATOR_VERSION = "1.0.0"

_D = Decimal


# ---------------------------------------------------------------------------
# Equipment coefficient set
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EquipmentCoefficientSet:
    """Coefficients for equipment capability calculation."""

    redundancy_ratio: Decimal | None = None  # compressor redundancy
    evaporator_capacity_margin: Decimal | None = None  # evaporator margin
    condenser_capacity_margin: Decimal | None = None  # condenser margin
    condenser_heat_rejection_factor: Decimal | None = None  # Q_condenser = Q_ref + W_comp
    compressor_cop: Decimal | None = None  # coefficient of performance

    revision_ids: dict[str, str] = field(default_factory=dict)
    source_types: dict[str, str] = field(default_factory=dict)
    revision_statuses: dict[str, str] = field(default_factory=dict)

    def get_coefficient_metadata(self, code: str) -> dict[str, Any]:
        revision_status = self.revision_statuses.get(code, "demo")
        return {
            "revision_id": self.revision_ids.get(code, "demo"),
            "source_type": self.source_types.get(code, "demo"),
            "revision_status": revision_status,
            "requires_review": revision_status != "approved",
        }


# ---------------------------------------------------------------------------
# Zone equipment input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneEquipmentInput:
    """Equipment inputs for a single zone."""

    zone_code: str
    zone_name: str
    design_cooling_load_kw_r: Decimal  # from cooling load calculation
    evaporator_count: int = 1
    evaporation_temperature_c: Decimal = _D("-10")  # °C
    defrost_method: str = "electric"


@dataclass(frozen=True)
class TemperatureSystemInput:
    """Equipment inputs for a temperature system group."""

    system_code: str
    system_name: str
    design_evaporating_temperature: Decimal  # °C
    zones: list[ZoneEquipmentInput]


@dataclass(frozen=True)
class EquipmentCapabilityCalcInput:
    """Top-level input for the equipment capability calculator."""

    systems: list[TemperatureSystemInput]
    coefficients: EquipmentCoefficientSet


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _warn_demo_coeff(
    cs: EquipmentCoefficientSet, code: str, warnings: list[CalculationWarning]
) -> None:
    meta = cs.get_coefficient_metadata(code)
    if meta["revision_status"] != "approved":
        warnings.append(
            CalculationWarning(
                code="DEMO_COEFFICIENT",
                message=f"Coefficient {code} uses demo/unverified value",
                details=meta,
            )
        )


def _require_coefficient(
    cs: EquipmentCoefficientSet, code: str, value: Decimal | None, calculator: str
) -> Decimal:
    """Return the coefficient value or raise CoefficientMissingError."""
    if value is not None:
        return value
    raise CoefficientMissingError(calculator, code)


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------


def calculate_equipment_capability(
    inp: EquipmentCapabilityCalcInput,
) -> CalculationResult:
    """Calculate equipment capability requirements for each temperature system.

    For each system:
    1. Sum zone design loads → system simultaneous load.
    2. Apply evaporator capacity margin.
    3. Compute compressor operating capacity.
    4. Compute compressor standby capacity (N+1 redundancy).
    5. Compute condenser heat rejection = refrigeration + compressor input power.
    """
    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []
    coeff_refs: list[CoefficientReference] = []
    cs = inp.coefficients

    if not inp.systems:
        raise MissingCalculationInputError(CALCULATOR_NAME, "systems")

    _warn_demo_coeff(cs, "equipment.redundancy_ratio", warnings)
    _warn_demo_coeff(cs, "equipment.evaporator_capacity_margin", warnings)
    _warn_demo_coeff(cs, "equipment.condenser_capacity_margin", warnings)
    _warn_demo_coeff(cs, "equipment.condenser_heat_rejection_factor", warnings)

    # Validate required coefficients upfront
    redundancy_ratio = _require_coefficient(
        cs, "equipment.redundancy_ratio", cs.redundancy_ratio, CALCULATOR_NAME
    )
    evap_margin_default = _require_coefficient(
        cs, "equipment.evaporator_capacity_margin", cs.evaporator_capacity_margin, CALCULATOR_NAME
    )
    condenser_margin_default = _require_coefficient(
        cs, "equipment.condenser_capacity_margin", cs.condenser_capacity_margin, CALCULATOR_NAME
    )
    condenser_rejection_default = _require_coefficient(
        cs,
        "equipment.condenser_heat_rejection_factor",
        cs.condenser_heat_rejection_factor,
        CALCULATOR_NAME,
    )

    system_results: list[dict[str, Any]] = []
    total_design_load = _D("0")
    total_compressor_capacity = _D("0")
    total_condenser_rejection = _D("0")
    total_compressor_input_power = _D("0")

    for system in inp.systems:
        # Sum zone design loads
        zone_loads = []
        system_simultaneous = _D("0")
        for zi in system.zones:
            zone_loads.append(
                {
                    "zone_code": zi.zone_code,
                    "zone_name": zi.zone_name,
                    "design_cooling_load_kw_r": float(zi.design_cooling_load_kw_r),
                    "evaporator_count": zi.evaporator_count,
                    "defrost_method": zi.defrost_method,
                }
            )
            system_simultaneous += zi.design_cooling_load_kw_r

        steps.append(
            CalculationStep(
                step_id=f"EQ-SUM-{system.system_code}",
                formula="system_load = Σ zone_design_loads",
                description=f"Sum zone loads for system {system.system_name}",
                inputs={
                    "zone_count": str(len(system.zones)),
                    "loads": str([float(zi.design_cooling_load_kw_r) for zi in system.zones]),
                },
                output_name="system_simultaneous_load_kw_r",
                output_value=str(system_simultaneous),
            )
        )

        # Evaporator capacity with margin
        evap_margin = evap_margin_default
        evaporator_total = (system_simultaneous * evap_margin).quantize(
            _D("0.001"), rounding=ROUND_HALF_UP
        )

        total_evaporators = sum(zi.evaporator_count for zi in system.zones)
        single_evaporator = (
            (evaporator_total / Decimal(str(total_evaporators))).quantize(
                _D("0.001"), rounding=ROUND_HALF_UP
            )
            if total_evaporators > 0
            else _D("0")
        )

        steps.append(
            CalculationStep(
                step_id=f"EQ-EVAP-{system.system_code}",
                formula="evaporator_total = system_load × evaporator_margin",
                description=f"Evaporator capacity — {system.system_name}",
                inputs={
                    "system_load": str(system_simultaneous),
                    "margin": str(evap_margin),
                },
                output_name="evaporator_total_capacity_kw_r",
                output_value=str(evaporator_total),
            )
        )

        # Compressor operating capacity
        compressor_operating = system_simultaneous  # must meet the load

        # Compressor standby (N+1 redundancy)
        redundancy = redundancy_ratio
        compressor_installed = (compressor_operating * redundancy).quantize(
            _D("0.001"), rounding=ROUND_HALF_UP
        )
        standby = (compressor_installed - compressor_operating).quantize(
            _D("0.001"), rounding=ROUND_HALF_UP
        )

        steps.append(
            CalculationStep(
                step_id=f"EQ-COMP-{system.system_code}",
                formula="installed = operating × redundancy; standby = installed - operating",
                description=f"Compressor capacity — {system.system_name}",
                inputs={
                    "operating_capacity": str(compressor_operating),
                    "redundancy_ratio": str(redundancy),
                },
                output_name="compressor_installed_capacity_kw_r",
                output_value=str(compressor_installed),
            )
        )

        # Compressor input power (kW(e)) from COP
        compressor_input_power_kw_e = _D("0")
        if cs.compressor_cop is not None and cs.compressor_cop > 0:
            compressor_input_power_kw_e = (compressor_operating / cs.compressor_cop).quantize(
                _D("0.001"), rounding=ROUND_HALF_UP
            )

            coeff_refs.append(
                CoefficientReference(
                    revision_id=cs.revision_ids.get("power.compressor_cop", "demo"),
                    code="power.compressor_cop",
                    value=cs.compressor_cop,
                    unit="ratio",
                    status=cs.revision_statuses.get("power.compressor_cop", "demo"),
                    source_type=cs.source_types.get("power.compressor_cop", "demo"),
                    requires_review=cs.revision_statuses.get("power.compressor_cop", "demo")
                    != "approved",
                )
            )

            steps.append(
                CalculationStep(
                    step_id=f"EQ-COP-{system.system_code}",
                    formula="input_power = refrigeration_capacity / COP",
                    description=f"Compressor input power — {system.system_name}",
                    inputs={
                        "refrigeration_capacity_kw_r": str(compressor_operating),
                        "cop": str(cs.compressor_cop),
                    },
                    output_name="compressor_input_power_kw_e",
                    output_value=str(compressor_input_power_kw_e),
                )
            )

        # Condenser heat rejection: Q_condenser = Q_refrigeration + W_compressor_input
        condenser_rejection_factor = condenser_rejection_default
        condenser_kw = (
            (compressor_operating + compressor_input_power_kw_e) * condenser_rejection_factor
        ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

        condenser_margin = condenser_margin_default
        condenser_with_margin = (condenser_kw * condenser_margin).quantize(
            _D("0.001"), rounding=ROUND_HALF_UP
        )

        steps.append(
            CalculationStep(
                step_id=f"EQ-COND-{system.system_code}",
                formula="Q_condenser = (Q_ref + W_comp) × rejection_factor × margin",
                description=f"Condenser heat rejection — {system.system_name}",
                inputs={
                    "refrigeration_capacity": str(compressor_operating),
                    "compressor_input_power_kw_e": str(compressor_input_power_kw_e),
                    "rejection_factor": str(condenser_rejection_factor),
                    "margin": str(condenser_margin),
                },
                output_name="condenser_heat_rejection_kw",
                output_value=str(condenser_with_margin),
            )
        )

        system_results.append(
            {
                "system_code": system.system_code,
                "system_name": system.system_name,
                "design_evaporating_temperature_c": str(system.design_evaporating_temperature),
                "zones": zone_loads,
                "system_simultaneous_load_kw_r": float(system_simultaneous),
                "evaporator_total_capacity_kw_r": float(evaporator_total),
                "evaporator_count": total_evaporators,
                "single_evaporator_capacity_kw_r": float(single_evaporator),
                "compressor_operating_capacity_kw_r": float(compressor_operating),
                "compressor_installed_capacity_kw_r": float(compressor_installed),
                "compressor_standby_capacity_kw_r": float(standby),
                "compressor_input_power_kw_e": float(compressor_input_power_kw_e),
                "condenser_heat_rejection_kw": float(condenser_with_margin),
                "defrost_methods": list({zi.defrost_method for zi in system.zones}),
            }
        )

        total_design_load += system_simultaneous
        total_compressor_capacity += compressor_installed
        total_condenser_rejection += condenser_with_margin
        total_compressor_input_power += compressor_input_power_kw_e

    # Final summary
    steps.append(
        CalculationStep(
            step_id="EQ-TOTAL",
            formula="total = Σ system capacities",
            description="Total equipment capability across all systems",
            inputs={"system_count": str(len(inp.systems))},
            output_name="total_compressor_capacity_kw_r",
            output_value=str(total_compressor_capacity),
        )
    )

    has_demo = not cs.revision_statuses or any(
        cs.revision_statuses.get(c, "demo") != "approved"
        for c in ["equipment.redundancy_ratio", "equipment.evaporator_capacity_margin"]
        if cs.revision_statuses.get(c) is not None
    )

    result_dict: dict[str, Any] = {
        "systems": system_results,
        "total_design_load_kw_r": float(total_design_load),
        "total_compressor_capacity_kw_r": float(total_compressor_capacity),
        "total_compressor_input_power_kw_e": float(total_compressor_input_power),
        "total_condenser_rejection_kw": float(total_condenser_rejection),
    }

    input_snapshot: dict[str, Any] = {
        "system_count": len(inp.systems),
        "redundancy_ratio": str(cs.redundancy_ratio),
        "evaporator_margin": str(cs.evaporator_capacity_margin),
        "condenser_margin": str(cs.condenser_capacity_margin),
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
