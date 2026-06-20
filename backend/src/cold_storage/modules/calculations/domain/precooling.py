"""Precooling calculator — deterministic, Decimal-based.

Computes required precooling capacity, batch cycles, room counts,
and capacity margins from daily inbound flow and equipment parameters.

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

CALCULATOR_NAME = "precooling"
CALCULATOR_VERSION = "1.0.0"
_D = Decimal


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrecoolingCalcInput:
    """Inputs for the precooling calculator."""

    precooled_quantity_per_day: Decimal
    precooled_ratio: Decimal = _D("1.0")
    batch_capacity: Decimal = _D("500")  # kg per batch
    batch_duration: Decimal = _D("4")  # hours
    loading_unloading_duration: Decimal = _D("1")  # hours
    available_precooling_hours: Decimal = _D("16")  # hours per day
    simultaneous_batch_count: int = 1
    reserve_capacity_ratio: Decimal = _D("1.10")

    def to_dict(self) -> dict[str, Any]:
        return {
            "precooled_quantity_per_day": str(self.precooled_quantity_per_day),
            "precooled_ratio": str(self.precooled_ratio),
            "batch_capacity": str(self.batch_capacity),
            "batch_duration": str(self.batch_duration),
            "loading_unloading_duration": str(self.loading_unloading_duration),
            "available_precooling_hours": str(self.available_precooling_hours),
            "simultaneous_batch_count": self.simultaneous_batch_count,
            "reserve_capacity_ratio": str(self.reserve_capacity_ratio),
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


def calculate_precooling(
    inp: PrecoolingCalcInput,
) -> CalculationResult:
    """Run the precooling calculation and return a traceable result."""

    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []

    # --- validate inputs ---------------------------------------------------
    _validate_strictly_positive(inp.precooled_quantity_per_day, "precooled_quantity_per_day")
    _validate_strictly_positive(inp.precooled_ratio, "precooled_ratio")
    _validate_strictly_positive(inp.batch_capacity, "batch_capacity")
    _validate_strictly_positive(inp.batch_duration, "batch_duration")
    _validate_strictly_positive(inp.loading_unloading_duration, "loading_unloading_duration")
    _validate_strictly_positive(inp.available_precooling_hours, "available_precooling_hours")
    _validate_positive_int(inp.simultaneous_batch_count, "simultaneous_batch_count")
    _validate_strictly_positive(inp.reserve_capacity_ratio, "reserve_capacity_ratio")

    # --- step 1: required precooling quantity per day ----------------------
    required_quantity = (inp.precooled_quantity_per_day * inp.precooled_ratio).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="PC-001",
            formula="precooled_quantity_per_day × precooled_ratio",
            description="Required daily precooling quantity",
            inputs={
                "precooled_quantity_per_day": str(inp.precooled_quantity_per_day),
                "precooled_ratio": str(inp.precooled_ratio),
            },
            output_name="required_precooling_quantity",
            output_value=str(required_quantity),
        )
    )

    # --- step 2: effective cycle duration ----------------------------------
    effective_cycle = (inp.batch_duration + inp.loading_unloading_duration).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="PC-002",
            formula="batch_duration + loading_unloading_duration",
            description="Effective precooling cycle duration (hours)",
            inputs={
                "batch_duration": str(inp.batch_duration),
                "loading_unloading_duration": str(inp.loading_unloading_duration),
            },
            output_name="effective_cycle_duration",
            output_value=str(effective_cycle),
        )
    )

    # --- step 3: available cycles per day ----------------------------------
    available_cycles = (inp.available_precooling_hours / effective_cycle).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="PC-003",
            formula="available_precooling_hours / effective_cycle_duration",
            description="Available batch cycles per day",
            inputs={
                "available_precooling_hours": str(inp.available_precooling_hours),
                "effective_cycle_duration": str(effective_cycle),
            },
            output_name="available_cycles_per_day",
            output_value=str(available_cycles),
        )
    )

    # --- step 4: required batches per day (with reserve) -------------------
    if inp.batch_capacity > 0 and available_cycles > 0:
        raw_batches = required_quantity / inp.batch_capacity
        batches_with_reserve = (raw_batches * inp.reserve_capacity_ratio).quantize(
            _D("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        batches_with_reserve = _D("0")

    steps.append(
        CalculationStep(
            step_id="PC-004",
            formula="ceil(required_qty / batch_capacity) × reserve_ratio",
            description="Required batches per day (with reserve)",
            inputs={
                "required_precooling_quantity": str(required_quantity),
                "batch_capacity": str(inp.batch_capacity),
                "reserve_capacity_ratio": str(inp.reserve_capacity_ratio),
            },
            output_name="required_batches_per_day",
            output_value=str(batches_with_reserve),
        )
    )

    # --- step 5: required simultaneous capacity ---------------------------
    # Simultaneous capacity = batches × batch_capacity
    required_simultaneous = (batches_with_reserve * inp.batch_capacity).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="PC-005",
            formula="required_batches_per_day × batch_capacity",
            description="Required simultaneous precooling capacity (kg)",
            inputs={
                "required_batches_per_day": str(batches_with_reserve),
                "batch_capacity": str(inp.batch_capacity),
            },
            output_name="required_simultaneous_capacity",
            output_value=str(required_simultaneous),
        )
    )

    # --- step 6: required precooling positions -----------------------------
    # Number of batches that can run simultaneously × batch capacity → positions
    required_batches_simul = int(batches_with_reserve.quantize(_D("1"), rounding=ROUND_CEILING))
    # Each position holds one batch
    required_positions = required_batches_simul

    steps.append(
        CalculationStep(
            step_id="PC-006",
            formula="ceil(required_batches_per_day) → simultaneous positions",
            description="Required precooling positions",
            inputs={
                "required_batches_per_day": str(batches_with_reserve),
            },
            output_name="required_precooling_positions",
            output_value=str(required_positions),
        )
    )

    # --- step 7: required precooling rooms ---------------------------------
    # Group positions by simultaneous_batch_count (positions per room)
    if inp.simultaneous_batch_count > 0:
        required_rooms = int(
            (_D(str(required_positions)) / _D(str(inp.simultaneous_batch_count))).quantize(
                _D("1"), rounding=ROUND_CEILING
            )
        )
    else:
        required_rooms = required_positions

    steps.append(
        CalculationStep(
            step_id="PC-007",
            formula="ceil(required_positions / simultaneous_batch_count)",
            description="Required precooling rooms",
            inputs={
                "required_precooling_positions": str(required_positions),
                "simultaneous_batch_count": str(inp.simultaneous_batch_count),
            },
            output_name="required_precooling_rooms",
            output_value=str(required_rooms),
        )
    )

    # --- step 8: capacity margin -------------------------------------------
    total_capacity = (
        _D(str(required_rooms)) * _D(str(inp.simultaneous_batch_count)) * inp.batch_capacity
    )
    capacity_margin = total_capacity - required_quantity

    steps.append(
        CalculationStep(
            step_id="PC-008",
            formula="total_capacity - required_quantity",
            description="Capacity margin (surplus)",
            inputs={
                "total_capacity": str(total_capacity),
                "required_precooling_quantity": str(required_quantity),
            },
            output_name="capacity_margin",
            output_value=str(capacity_margin),
        )
    )

    # --- warnings ----------------------------------------------------------
    if capacity_margin <= 0:
        warnings.append(
            CalculationWarning(
                code="NO_CAPACITY_MARGIN",
                message="Precooling capacity margin is zero or negative",
                details={
                    "capacity_margin": str(capacity_margin),
                    "total_capacity": str(total_capacity),
                    "required_quantity": str(required_quantity),
                },
            )
        )

    if inp.reserve_capacity_ratio == _D("1.0"):
        warnings.append(
            CalculationWarning(
                code="NO_RESERVE",
                message="reserve_capacity_ratio is 1.0 (no reserve capacity)",
                details={"reserve_capacity_ratio": "1.0"},
            )
        )

    result_dict = {
        "required_precooling_quantity": float(required_quantity),
        "effective_cycle_duration": float(effective_cycle),
        "available_cycles_per_day": float(available_cycles),
        "required_batches_per_day": float(batches_with_reserve),
        "required_simultaneous_capacity": float(required_simultaneous),
        "required_precooling_positions": required_positions,
        "required_precooling_rooms": required_rooms,
        "capacity_margin": float(capacity_margin),
    }

    return CalculationResult(
        success=True,
        calculator_name=CALCULATOR_NAME,
        calculator_version=CALCULATOR_VERSION,
        input_snapshot=inp.to_dict(),
        result=result_dict,
        steps=steps,
        warnings=warnings,
        requires_review=any(w.code in ("NO_CAPACITY_MARGIN", "NO_RESERVE") for w in warnings),
    )
