"""Installed power calculator — deterministic, Decimal-based.

Computes electrical installed capacity (kW(e)) from equipment capabilities
and auxiliary equipment specifications.

Key boundary:
- This calculator outputs kW(e) — electrical installed power.
- It does NOT output energy consumption (kWh) or daily electricity usage.
- It does NOT determine transformer sizing or maximum demand (unless provided
  as explicit inputs with demand factors).

Design rules:
- Uses ``decimal.Decimal`` for all arithmetic.
- Pure function — no database or network access.
- Returns a ``CalculationResult`` with step-by-step traceability.
- kW(r) ≠ kW(e): refrigeration capacity and electrical power are distinct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from cold_storage.modules.calculations.domain.models import (
    CalculationResult,
    CalculationStep,
    CalculationWarning,
)

CALCULATOR_NAME = "installed_power"
CALCULATOR_VERSION = "1.0.0"

_D = Decimal


# ---------------------------------------------------------------------------
# Power equipment item
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PowerEquipmentItem:
    """A single piece of equipment with its electrical power rating."""

    name: str
    category: str  # "refrigeration", "production", "lighting", "auxiliary"
    quantity: int
    unit_power_kw_e: Decimal  # kW(e) per unit
    demand_factor: Decimal = _D("1.0")  # fraction of time running simultaneously

    @property
    def total_power_kw_e(self) -> Decimal:
        return (self.quantity * self.unit_power_kw_e).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

    @property
    def demand_power_kw_e(self) -> Decimal:
        return (self.total_power_kw_e * self.demand_factor).quantize(
            _D("0.001"), rounding=ROUND_HALF_UP
        )


# ---------------------------------------------------------------------------
# Installed power input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InstalledPowerCalcInput:
    """Input for the installed power calculator."""

    # From equipment capability calculation
    compressor_input_power_kw_e: Decimal = _D("0")  # total compressor kW(e)
    evaporator_fan_power_kw_e: Decimal = _D("0")  # all evaporator fan kW(e)
    condenser_fan_power_kw_e: Decimal = _D("0")  # condenser fan kW(e)
    pump_power_kw_e: Decimal = _D("0")  # coolant pump kW(e)
    defrost_power_kw_e: Decimal = _D("0")  # defrost system kW(e)

    # Additional equipment
    processing_equipment_power_kw_e: Decimal = _D("0")  # production line kW(e)
    lighting_power_kw_e: Decimal = _D("0")  # facility lighting kW(e)
    other_auxiliary_power_kw_e: Decimal = _D("0")  # other kW(e)

    # Equipment list (optional, for detailed breakdown)
    equipment_items: list[PowerEquipmentItem] = field(default_factory=list)

    # Demand factors (for peak demand estimation)
    refrigeration_demand_factor: Decimal = _D("0.90")
    production_demand_factor: Decimal = _D("0.90")

    def to_dict(self) -> dict[str, Any]:
        return {
            "compressor_input_power_kw_e": str(self.compressor_input_power_kw_e),
            "evaporator_fan_power_kw_e": str(self.evaporator_fan_power_kw_e),
            "condenser_fan_power_kw_e": str(self.condenser_fan_power_kw_e),
            "pump_power_kw_e": str(self.pump_power_kw_e),
            "defrost_power_kw_e": str(self.defrost_power_kw_e),
            "processing_equipment_power_kw_e": str(self.processing_equipment_power_kw_e),
            "lighting_power_kw_e": str(self.lighting_power_kw_e),
            "other_auxiliary_power_kw_e": str(self.other_auxiliary_power_kw_e),
            "refrigeration_demand_factor": str(self.refrigeration_demand_factor),
            "production_demand_factor": str(self.production_demand_factor),
            "equipment_item_count": len(self.equipment_items),
        }


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------


def calculate_installed_power(inp: InstalledPowerCalcInput) -> CalculationResult:
    """Calculate installed electrical power and estimated peak demand.

    Output categories:
    1. Refrigeration system: compressor + evaporator fans + condenser fans + pumps + defrost
    2. Processing equipment: production line equipment
    3. Lighting: facility lighting
    4. Auxiliary: other equipment

    All values in kW(e).
    """
    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []

    # --- 1. Refrigeration system power ---
    refrigeration_total = (
        inp.compressor_input_power_kw_e
        + inp.evaporator_fan_power_kw_e
        + inp.condenser_fan_power_kw_e
        + inp.pump_power_kw_e
        + inp.defrost_power_kw_e
    )

    steps.append(
        CalculationStep(
            step_id="PW-REFRIG",
            formula="P_refrig = compressor + evaporator_fans + condenser_fans + pumps + defrost",
            description="Refrigeration system installed power",
            inputs={
                "compressor": str(inp.compressor_input_power_kw_e),
                "evaporator_fans": str(inp.evaporator_fan_power_kw_e),
                "condenser_fans": str(inp.condenser_fan_power_kw_e),
                "pumps": str(inp.pump_power_kw_e),
                "defrost": str(inp.defrost_power_kw_e),
            },
            output_name="refrigeration_system_installed_power_kw_e",
            output_value=str(refrigeration_total),
        )
    )

    # --- 2. Processing equipment power ---
    processing_total = inp.processing_equipment_power_kw_e
    steps.append(
        CalculationStep(
            step_id="PW-PROC",
            formula="P_process = processing_equipment_power",
            description="Processing equipment installed power",
            inputs={"processing_equipment": str(processing_total)},
            output_name="process_equipment_installed_power_kw_e",
            output_value=str(processing_total),
        )
    )

    # --- 3. Lighting power ---
    lighting_total = inp.lighting_power_kw_e
    steps.append(
        CalculationStep(
            step_id="PW-LIGHT",
            formula="P_lighting = lighting_power",
            description="Lighting installed power",
            inputs={"lighting": str(lighting_total)},
            output_name="lighting_installed_power_kw_e",
            output_value=str(lighting_total),
        )
    )

    # --- 4. Auxiliary power ---
    auxiliary_total = inp.other_auxiliary_power_kw_e
    steps.append(
        CalculationStep(
            step_id="PW-AUX",
            formula="P_aux = other_auxiliary_power",
            description="Auxiliary installed power",
            inputs={"auxiliary": str(auxiliary_total)},
            output_name="auxiliary_installed_power_kw_e",
            output_value=str(auxiliary_total),
        )
    )

    # --- 5. Total installed power ---
    total_installed = refrigeration_total + processing_total + lighting_total + auxiliary_total

    steps.append(
        CalculationStep(
            step_id="PW-TOTAL",
            formula="P_total = refrigeration + processing + lighting + auxiliary",
            description="Total installed electrical power",
            inputs={
                "refrigeration": str(refrigeration_total),
                "processing": str(processing_total),
                "lighting": str(lighting_total),
                "auxiliary": str(auxiliary_total),
            },
            output_name="total_installed_power_kw_e",
            output_value=str(total_installed),
        )
    )

    # --- 6. Estimated peak demand ---
    refrigeration_demand = (refrigeration_total * inp.refrigeration_demand_factor).quantize(
        _D("0.001"), rounding=ROUND_HALF_UP
    )
    production_demand = (processing_total * inp.production_demand_factor).quantize(
        _D("0.001"), rounding=ROUND_HALF_UP
    )
    estimated_peak_demand = (
        refrigeration_demand + production_demand + lighting_total + auxiliary_total
    ).quantize(_D("0.001"), rounding=ROUND_HALF_UP)

    steps.append(
        CalculationStep(
            step_id="PW-DEMAND",
            formula="peak_demand = refrig×df_ref + process×df_proc + lighting + aux",
            description="Estimated peak demand (kW(e))",
            inputs={
                "refrigeration_demand_factor": str(inp.refrigeration_demand_factor),
                "production_demand_factor": str(inp.production_demand_factor),
            },
            output_name="estimated_peak_demand_kw_e",
            output_value=str(estimated_peak_demand),
        )
    )

    # --- 7. Equipment item breakdown (if provided) ---
    item_breakdown: list[dict[str, Any]] = []
    if inp.equipment_items:
        for item in inp.equipment_items:
            item_breakdown.append(
                {
                    "name": item.name,
                    "category": item.category,
                    "quantity": item.quantity,
                    "unit_power_kw_e": str(item.unit_power_kw_e),
                    "total_power_kw_e": str(item.total_power_kw_e),
                    "demand_factor": str(item.demand_factor),
                    "demand_power_kw_e": str(item.demand_power_kw_e),
                }
            )

    # Warnings
    if inp.defrost_power_kw_e > 0 and inp.refrigeration_demand_factor > _D("0.5"):
        warnings.append(
            CalculationWarning(
                code="DEFAULT_DEMAND_FACTOR",
                message="Refrigeration demand factor may be too high with defrost cycles",
                details={
                    "refrigeration_demand_factor": str(inp.refrigeration_demand_factor),
                },
            )
        )

    result_dict: dict[str, Any] = {
        "refrigeration_system_installed_power_kw_e": float(refrigeration_total),
        "process_equipment_installed_power_kw_e": float(processing_total),
        "lighting_installed_power_kw_e": float(lighting_total),
        "auxiliary_installed_power_kw_e": float(auxiliary_total),
        "total_installed_power_kw_e": float(total_installed),
        "estimated_peak_demand_kw_e": float(estimated_peak_demand),
        "equipment_items": item_breakdown,
    }

    return CalculationResult(
        success=True,
        calculator_name=CALCULATOR_NAME,
        calculator_version=CALCULATOR_VERSION,
        input_snapshot=inp.to_dict(),
        result=result_dict,
        steps=steps,
        warnings=warnings,
        requires_review=False,
    )
