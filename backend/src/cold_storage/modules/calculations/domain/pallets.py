"""Pallet calculator — deterministic, Decimal-based.

Computes pallet counts, reserve pallets, and required pallet positions
from design inventory and pallet configuration parameters.

Design rules
- Uses ``decimal.Decimal`` for all arithmetic.
- Pure function — no database or network access.
- Returns a ``CalculationResult`` with step-by-step traceability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
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

CALCULATOR_NAME = "pallets"
CALCULATOR_VERSION = "1.0.0"
_D = Decimal


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PalletCalcInput:
    """Inputs for the pallet calculator."""

    design_inventory: Decimal
    net_product_per_pallet: Decimal
    pallet_utilization_ratio: Decimal = _D("1.0")
    pallet_turnover_ratio: Decimal = _D("1.0")
    stacking_level: int = 1
    reserve_ratio: Decimal = _D("0.10")

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_inventory": str(self.design_inventory),
            "net_product_per_pallet": str(self.net_product_per_pallet),
            "pallet_utilization_ratio": str(self.pallet_utilization_ratio),
            "pallet_turnover_ratio": str(self.pallet_turnover_ratio),
            "stacking_level": self.stacking_level,
            "reserve_ratio": str(self.reserve_ratio),
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_strictly_positive(value: Decimal, name: str) -> None:
    if value is None:
        raise MissingCalculationInputError(CALCULATOR_NAME, name)
    if value <= 0:
        raise InvalidCalculationInputError(CALCULATOR_NAME, name, value)


def _validate_positive_int(value: int, name: str) -> None:
    if value <= 0:
        raise InvalidCalculationInputError(CALCULATOR_NAME, name, value)


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------


def calculate_pallets(
    inp: PalletCalcInput,
) -> CalculationResult:
    """Run the pallet calculation and return a traceable result."""

    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []

    # --- validate inputs ---------------------------------------------------
    _validate_strictly_positive(inp.design_inventory, "design_inventory")
    _validate_strictly_positive(inp.net_product_per_pallet, "net_product_per_pallet")
    _validate_strictly_positive(inp.pallet_utilization_ratio, "pallet_utilization_ratio")
    _validate_strictly_positive(inp.pallet_turnover_ratio, "pallet_turnover_ratio")
    _validate_positive_int(inp.stacking_level, "stacking_level")
    if inp.reserve_ratio < 0:
        raise InvalidCalculationInputError(CALCULATOR_NAME, "reserve_ratio", inp.reserve_ratio)

    # --- step 1: effective pallet capacity (with utilisation ratio) --------
    effective_capacity_per_pallet = (
        inp.net_product_per_pallet * inp.pallet_utilization_ratio
    ).quantize(_D("0.01"), rounding=ROUND_HALF_UP)

    steps.append(
        CalculationStep(
            step_id="PL-001",
            formula="net_product_per_pallet × pallet_utilization_ratio",
            description="Effective product capacity per pallet",
            inputs={
                "net_product_per_pallet": str(inp.net_product_per_pallet),
                "pallet_utilization_ratio": str(inp.pallet_utilization_ratio),
            },
            output_name="effective_capacity_per_pallet",
            output_value=str(effective_capacity_per_pallet),
        )
    )

    # --- step 2: net pallet quantity ---------------------------------------
    # Divide design inventory by effective capacity per pallet, rounding up
    net_pallets = int(
        (inp.design_inventory / effective_capacity_per_pallet).quantize(
            _D("1"), rounding=ROUND_CEILING
        )
    )

    steps.append(
        CalculationStep(
            step_id="PL-002",
            formula="ceil(design_inventory / effective_capacity_per_pallet)",
            description="Net pallet count required",
            inputs={
                "design_inventory": str(inp.design_inventory),
                "effective_capacity_per_pallet": str(effective_capacity_per_pallet),
            },
            output_name="net_pallet_quantity",
            output_value=str(net_pallets),
        )
    )

    # --- step 3: reserve pallet quantity -----------------------------------
    reserve_pallets = int(
        (_D(str(net_pallets)) * inp.reserve_ratio).quantize(_D("1"), rounding=ROUND_CEILING)
    )

    steps.append(
        CalculationStep(
            step_id="PL-003",
            formula="ceil(net_pallet_quantity × reserve_ratio)",
            description="Reserve pallet count",
            inputs={
                "net_pallet_quantity": str(net_pallets),
                "reserve_ratio": str(inp.reserve_ratio),
            },
            output_name="reserve_pallet_quantity",
            output_value=str(reserve_pallets),
        )
    )

    # --- step 4: design pallet quantity ------------------------------------
    design_pallets = net_pallets + reserve_pallets

    steps.append(
        CalculationStep(
            step_id="PL-004",
            formula="net_pallet_quantity + reserve_pallet_quantity",
            description="Total design pallet count",
            inputs={
                "net_pallet_quantity": str(net_pallets),
                "reserve_pallet_quantity": str(reserve_pallets),
            },
            output_name="design_pallet_quantity",
            output_value=str(design_pallets),
        )
    )

    # --- step 5: required pallet positions (accounting for stacking) -------
    if inp.stacking_level > 1:
        required_positions = int(
            (_D(str(design_pallets)) / _D(str(inp.stacking_level))).quantize(
                _D("1"), rounding=ROUND_CEILING
            )
        )
    else:
        required_positions = design_pallets

    steps.append(
        CalculationStep(
            step_id="PL-005",
            formula="ceil(design_pallet_quantity / stacking_level)",
            description="Required pallet positions (floor-level)",
            inputs={
                "design_pallet_quantity": str(design_pallets),
                "stacking_level": str(inp.stacking_level),
            },
            output_name="required_pallet_positions",
            output_value=str(required_positions),
        )
    )

    # --- step 6: pallet turnover ratio check ------------------------------
    # If turnover > 1.0, we need fewer physical pallets because they
    # cycle through faster.  The positions count already reflects the
    # snapshot design; this step documents the turnover effect.
    adjusted_positions = int(
        (_D(str(required_positions)) / inp.pallet_turnover_ratio).quantize(
            _D("1"), rounding=ROUND_CEILING
        )
    )

    steps.append(
        CalculationStep(
            step_id="PL-006",
            formula="ceil(required_positions / pallet_turnover_ratio)",
            description="Adjusted positions with turnover effect",
            inputs={
                "required_pallet_positions": str(required_positions),
                "pallet_turnover_ratio": str(inp.pallet_turnover_ratio),
            },
            output_name="adjusted_pallet_positions",
            output_value=str(adjusted_positions),
        )
    )

    # --- warnings ----------------------------------------------------------
    if inp.stacking_level > 3:
        warnings.append(
            CalculationWarning(
                code="HIGH_STACKING",
                message=f"Stacking level {inp.stacking_level} exceeds recommended maximum of 3",
                details={"stacking_level": inp.stacking_level},
            )
        )

    if inp.reserve_ratio == _D("0"):
        warnings.append(
            CalculationWarning(
                code="NO_RESERVE",
                message="No reserve pallets configured",
                details={"reserve_ratio": "0"},
            )
        )

    result_dict = {
        "effective_capacity_per_pallet": float(effective_capacity_per_pallet),
        "net_pallet_quantity": net_pallets,
        "reserve_pallet_quantity": reserve_pallets,
        "design_pallet_quantity": design_pallets,
        "required_pallet_positions": required_positions,
        "adjusted_pallet_positions": adjusted_positions,
    }

    return CalculationResult(
        success=True,
        calculator_name=CALCULATOR_NAME,
        calculator_version=CALCULATOR_VERSION,
        input_snapshot=inp.to_dict(),
        result=result_dict,
        steps=steps,
        warnings=warnings,
        requires_review=any(w.code in ("HIGH_STACKING", "NO_RESERVE") for w in warnings),
    )
