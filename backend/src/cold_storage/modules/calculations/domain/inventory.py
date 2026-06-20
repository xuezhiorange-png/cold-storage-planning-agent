"""Inventory calculator — deterministic, Decimal-based.

Computes base, safety, peak, and design inventory quantities from
daily inbound/outbound flow, turnover days, and safety stock parameters.

Design rules
- Uses ``decimal.Decimal`` for all arithmetic.
- Pure function — no database or network access.
- Returns a ``CalculationResult`` with step-by-step traceability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from cold_storage.modules.calculations.domain.errors import (
    InvalidCalculationInputError,
    MissingCalculationInputError,
)
from cold_storage.modules.calculations.domain.models import (
    CalculationResult,
    CalculationStep,
    CalculationWarning,
)

CALCULATOR_NAME = "inventory"
CALCULATOR_VERSION = "1.0.0"
_D = Decimal


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InventoryCalcInput:
    """Inputs for the inventory calculator."""

    daily_inbound_quantity: Decimal
    daily_outbound_quantity: Decimal
    turnover_days: Decimal
    safety_stock_days: Decimal = _D("0")
    storage_ratio: Decimal = _D("1.0")
    inventory_peak_factor: Decimal = _D("1.0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_inbound_quantity": str(self.daily_inbound_quantity),
            "daily_outbound_quantity": str(self.daily_outbound_quantity),
            "turnover_days": str(self.turnover_days),
            "safety_stock_days": str(self.safety_stock_days),
            "storage_ratio": str(self.storage_ratio),
            "inventory_peak_factor": str(self.inventory_peak_factor),
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_positive(value: Decimal, name: str) -> None:
    if value is None:
        raise MissingCalculationInputError(CALCULATOR_NAME, name)
    if value < 0:
        raise InvalidCalculationInputError(CALCULATOR_NAME, name, value)


def _validate_strictly_positive(value: Decimal, name: str) -> None:
    if value is None:
        raise MissingCalculationInputError(CALCULATOR_NAME, name)
    if value <= 0:
        raise InvalidCalculationInputError(CALCULATOR_NAME, name, value)


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------


def calculate_inventory(
    inp: InventoryCalcInput,
) -> CalculationResult:
    """Run the inventory calculation and return a traceable result."""

    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []

    # --- validate inputs ---------------------------------------------------
    _validate_strictly_positive(inp.daily_inbound_quantity, "daily_inbound_quantity")
    _validate_positive(inp.daily_outbound_quantity, "daily_outbound_quantity")
    _validate_strictly_positive(inp.turnover_days, "turnover_days")
    _validate_positive(inp.safety_stock_days, "safety_stock_days")
    _validate_strictly_positive(inp.storage_ratio, "storage_ratio")
    _validate_strictly_positive(inp.inventory_peak_factor, "inventory_peak_factor")

    # --- step 1: base inventory (average stock during turnover) ------------
    base_inventory = (inp.daily_inbound_quantity * inp.turnover_days).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="INV-001",
            formula="daily_inbound_quantity × turnover_days",
            description="Base inventory quantity",
            inputs={
                "daily_inbound_quantity": str(inp.daily_inbound_quantity),
                "turnover_days": str(inp.turnover_days),
            },
            output_name="base_inventory",
            output_value=str(base_inventory),
        )
    )

    # --- step 2: safety inventory -----------------------------------------
    safety_inventory = (inp.daily_inbound_quantity * inp.safety_stock_days).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="INV-002",
            formula="daily_inbound_quantity × safety_stock_days",
            description="Safety stock quantity",
            inputs={
                "daily_inbound_quantity": str(inp.daily_inbound_quantity),
                "safety_stock_days": str(inp.safety_stock_days),
            },
            output_name="safety_inventory",
            output_value=str(safety_inventory),
        )
    )

    # --- step 3: peak inventory (with peak factor) -------------------------
    subtotal = base_inventory + safety_inventory
    peak_inventory = (subtotal * inp.inventory_peak_factor).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="INV-003",
            formula="(base + safety) × inventory_peak_factor",
            description="Peak inventory with seasonal/demand factor",
            inputs={
                "base_inventory": str(base_inventory),
                "safety_inventory": str(safety_inventory),
                "inventory_peak_factor": str(inp.inventory_peak_factor),
            },
            output_name="peak_inventory",
            output_value=str(peak_inventory),
        )
    )

    # --- step 4: design inventory (with storage ratio) --------------------
    design_inventory = (peak_inventory * inp.storage_ratio).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="INV-004",
            formula="peak_inventory × storage_ratio",
            description="Design inventory (storage-ready quantity)",
            inputs={
                "peak_inventory": str(peak_inventory),
                "storage_ratio": str(inp.storage_ratio),
            },
            output_name="design_inventory",
            output_value=str(design_inventory),
        )
    )

    # --- warnings ----------------------------------------------------------
    if inp.safety_stock_days == _D("0"):
        warnings.append(
            CalculationWarning(
                code="NO_SAFETY_STOCK",
                message="safety_stock_days is zero; no safety stock calculated",
                details={"safety_stock_days": "0"},
            )
        )

    if inp.inventory_peak_factor == _D("1.0"):
        warnings.append(
            CalculationWarning(
                code="PEAK_FACTOR_DEFAULT",
                message="inventory_peak_factor is 1.0 (no peak adjustment)",
                details={"inventory_peak_factor": "1.0"},
            )
        )

    result_dict = {
        "base_inventory": float(base_inventory),
        "safety_inventory": float(safety_inventory),
        "peak_inventory": float(peak_inventory),
        "design_inventory": float(design_inventory),
    }

    return CalculationResult(
        success=True,
        calculator_name=CALCULATOR_NAME,
        calculator_version=CALCULATOR_VERSION,
        input_snapshot=inp.to_dict(),
        result=result_dict,
        steps=steps,
        warnings=warnings,
        requires_review=any(w.code in ("NO_SAFETY_STOCK", "PEAK_FACTOR_DEFAULT") for w in warnings),
    )
