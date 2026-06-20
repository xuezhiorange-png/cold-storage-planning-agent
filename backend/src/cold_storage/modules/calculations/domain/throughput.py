"""Throughput calculator — deterministic, Decimal-based.

Computes required and available hourly throughput, labour requirements,
and capacity utilisation from peak daily output parameters.

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

CALCULATOR_NAME = "throughput"
CALCULATOR_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThroughputCalcInput:
    """Inputs for the throughput calculator.

    All values are ``Decimal`` to guarantee reproducible results.
    """

    peak_output_kg_per_day: Decimal
    processing_hours_per_day: Decimal
    shift_count: int = 1
    effective_working_ratio: Decimal = Decimal("0.85")
    labour_efficiency_kg_per_person_hour: Decimal = Decimal("150")
    available_workers: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "peak_output_kg_per_day": str(self.peak_output_kg_per_day),
            "processing_hours_per_day": str(self.processing_hours_per_day),
            "shift_count": self.shift_count,
            "effective_working_ratio": str(self.effective_working_ratio),
            "labour_efficiency_kg_per_person_hour": str(self.labour_efficiency_kg_per_person_hour),
            "available_workers": self.available_workers,
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_D = Decimal


def _validate_positive(value: Decimal, name: str) -> None:
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


def calculate_throughput(
    inp: ThroughputCalcInput,
) -> CalculationResult:
    """Run the throughput calculation and return a traceable result."""

    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []

    # --- validate inputs ---------------------------------------------------
    _validate_positive(inp.peak_output_kg_per_day, "peak_output_kg_per_day")
    _validate_positive(inp.processing_hours_per_day, "processing_hours_per_day")
    _validate_positive_int(inp.shift_count, "shift_count")
    _validate_positive(inp.effective_working_ratio, "effective_working_ratio")
    _validate_positive(
        inp.labour_efficiency_kg_per_person_hour,
        "labour_efficiency_kg_per_person_hour",
    )

    # --- step 1: required hourly throughput --------------------------------
    required_hourly = (inp.peak_output_kg_per_day / inp.processing_hours_per_day).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="TH-001",
            formula="peak_output_kg_per_day / processing_hours_per_day",
            description="Required hourly throughput (kg/h)",
            inputs={
                "peak_output_kg_per_day": str(inp.peak_output_kg_per_day),
                "processing_hours_per_day": str(inp.processing_hours_per_day),
            },
            output_name="required_hourly_throughput_kg_h",
            output_value=str(required_hourly),
        )
    )

    # --- step 2: available hourly throughput (after efficiency) -------------
    available_hourly = (required_hourly / inp.effective_working_ratio).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="TH-002",
            formula="required_hourly_throughput / effective_working_ratio",
            description="Available (design) hourly throughput (kg/h)",
            inputs={
                "required_hourly_throughput_kg_h": str(required_hourly),
                "effective_working_ratio": str(inp.effective_working_ratio),
            },
            output_name="available_hourly_throughput_kg_h",
            output_value=str(available_hourly),
        )
    )

    # --- step 3: capacity utilisation ratio ---------------------------------
    if available_hourly > 0:
        utilisation = (required_hourly / available_hourly).quantize(
            _D("0.0001"), rounding=ROUND_HALF_UP
        )
    else:
        utilisation = _D("0")

    steps.append(
        CalculationStep(
            step_id="TH-003",
            formula="required / available  (capacity utilisation)",
            description="Capacity utilisation ratio",
            inputs={
                "required_hourly_throughput_kg_h": str(required_hourly),
                "available_hourly_throughput_kg_h": str(available_hourly),
            },
            output_name="capacity_utilisation_ratio",
            output_value=str(utilisation),
        )
    )

    # --- step 4: required labour hours -------------------------------------
    if inp.labour_efficiency_kg_per_person_hour > 0:
        required_labour_hours = (
            inp.peak_output_kg_per_day / inp.labour_efficiency_kg_per_person_hour
        ).quantize(_D("0.01"), rounding=ROUND_HALF_UP)
    else:
        required_labour_hours = _D("0")

    steps.append(
        CalculationStep(
            step_id="TH-004",
            formula="peak_output / labour_efficiency",
            description="Required total labour person-hours per day",
            inputs={
                "peak_output_kg_per_day": str(inp.peak_output_kg_per_day),
                "labour_efficiency_kg_per_person_hour": str(
                    inp.labour_efficiency_kg_per_person_hour
                ),
            },
            output_name="required_labour_hours",
            output_value=str(required_labour_hours),
        )
    )

    # --- step 5: required worker count -------------------------------------
    if inp.processing_hours_per_day > 0 and inp.labour_efficiency_kg_per_person_hour > 0:
        required_workers = int(
            (
                inp.peak_output_kg_per_day
                / (inp.labour_efficiency_kg_per_person_hour * inp.processing_hours_per_day)
            ).quantize(_D("1"), rounding=ROUND_CEILING)
        )
    else:
        required_workers = 0

    steps.append(
        CalculationStep(
            step_id="TH-005",
            formula="ceil(peak_output / (efficiency × hours))",
            description="Required worker count",
            inputs={
                "peak_output_kg_per_day": str(inp.peak_output_kg_per_day),
                "labour_efficiency": str(inp.labour_efficiency_kg_per_person_hour),
                "processing_hours_per_day": str(inp.processing_hours_per_day),
            },
            output_name="required_worker_count",
            output_value=str(required_workers),
        )
    )

    # --- step 6: capacity shortfall ----------------------------------------
    capacity_shortfall = _D("0")
    if inp.available_workers > 0 and required_workers > inp.available_workers:
        capacity_shortfall = _D(str(required_workers - inp.available_workers))
        warnings.append(
            CalculationWarning(
                code="CAPACITY_SHORTFALL",
                message=(
                    f"Available workers ({inp.available_workers}) are fewer than "
                    f"the required {required_workers}; shortfall = "
                    f"{capacity_shortfall} workers"
                ),
                details={
                    "available_workers": inp.available_workers,
                    "required_workers": required_workers,
                    "shortfall": int(capacity_shortfall),
                },
            )
        )

    steps.append(
        CalculationStep(
            step_id="TH-006",
            formula="max(required_workers - available_workers, 0)",
            description="Worker capacity shortfall",
            inputs={
                "required_worker_count": str(required_workers),
                "available_workers": str(inp.available_workers),
            },
            output_name="capacity_shortfall_workers",
            output_value=str(capacity_shortfall),
        )
    )

    # --- warnings for demo / unverified use --------------------------------
    if inp.effective_working_ratio == _D("0.85"):
        warnings.append(
            CalculationWarning(
                code="DEMO_COEFFICIENT",
                message="effective_working_ratio uses demo default 0.85",
                details={"effective_working_ratio": "0.85"},
            )
        )

    result_dict = {
        "required_hourly_throughput_kg_h": float(required_hourly),
        "available_hourly_throughput_kg_h": float(available_hourly),
        "capacity_utilisation_ratio": float(utilisation),
        "required_labour_hours": float(required_labour_hours),
        "required_worker_count": required_workers,
        "capacity_shortfall_workers": int(capacity_shortfall),
    }

    return CalculationResult(
        success=True,
        calculator_name=CALCULATOR_NAME,
        calculator_version=CALCULATOR_VERSION,
        input_snapshot=inp.to_dict(),
        result=result_dict,
        steps=steps,
        warnings=warnings,
        requires_review=any(w.code == "DEMO_COEFFICIENT" for w in warnings),
    )
