"""Area calculator — deterministic, Decimal-based.

Computes zone-by-zone net area, circulation allowances, auxiliary areas,
and total design area for a cold storage facility.

Support zones:
  - raw_material_staging
  - precooling
  - sorting_and_packing
  - finished_goods_storage
  - shipping_staging
  - circulation_and_auxiliary
  - equipment_or_machine_room

Design rules
- Uses ``decimal.Decimal`` for all arithmetic.
- Pure function — no database or network access.
- Returns a ``CalculationResult`` with step-by-step traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from cold_storage.modules.calculations.domain.errors import (
    InvalidCalculationInputError,
)
from cold_storage.modules.calculations.domain.models import (
    CalculationResult,
    CalculationStep,
    CalculationWarning,
)

CALCULATOR_NAME = "areas"
CALCULATOR_VERSION = "1.0.0"
_D = Decimal


# ---------------------------------------------------------------------------
# Supported zone codes
# ---------------------------------------------------------------------------

SUPPORTED_ZONE_CODES: frozenset[str] = frozenset(
    {
        "raw_material_staging",
        "precooling",
        "sorting_and_packing",
        "finished_goods_storage",
        "shipping_staging",
        "circulation_and_auxiliary",
        "equipment_or_machine_room",
    }
)


# ---------------------------------------------------------------------------
# Zone specification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneAreaSpec:
    """Specification for a single zone's area calculation."""

    zone_code: str
    zone_name: str
    net_area: Decimal
    circulation_allowance: Decimal = _D("0.15")  # default 15%
    auxiliary_allowance: Decimal = _D("0")  # default 0%
    unit: str = "m2"
    calculation_basis: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_code": self.zone_code,
            "zone_name": self.zone_name,
            "net_area": str(self.net_area),
            "circulation_allowance": str(self.circulation_allowance),
            "auxiliary_allowance": str(self.auxiliary_allowance),
            "unit": self.unit,
            "calculation_basis": self.calculation_basis,
        }


# ---------------------------------------------------------------------------
# Area summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AreaSummary:
    """Aggregate area summary across all zones."""

    total_net_area: Decimal
    total_circulation_area: Decimal
    total_auxiliary_area: Decimal
    total_design_area: Decimal
    zone_area_breakdown: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_net_area": str(self.total_net_area),
            "total_circulation_area": str(self.total_circulation_area),
            "total_auxiliary_area": str(self.total_auxiliary_area),
            "total_design_area": str(self.total_design_area),
            "zone_area_breakdown": self.zone_area_breakdown,
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_zone_spec(spec: ZoneAreaSpec) -> None:
    if spec.zone_code not in SUPPORTED_ZONE_CODES:
        raise InvalidCalculationInputError(
            CALCULATOR_NAME,
            "zone_code",
            spec.zone_code,
        )
    if spec.net_area <= 0:
        raise InvalidCalculationInputError(
            CALCULATOR_NAME,
            f"{spec.zone_code}.net_area",
            spec.net_area,
        )


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------


def calculate_areas(
    zones: list[ZoneAreaSpec],
    *,
    circulation_allowance_override: Decimal | None = None,
    auxiliary_allowance_override: Decimal | None = None,
) -> CalculationResult:
    """Run the area calculation and return a traceable result.

    Parameters
    ----------
    zones:
        List of zone specifications.  Each must have a supported zone_code
        and a positive net_area.
    circulation_allowance_override:
        If provided, overrides each zone's individual circulation_allowance.
    auxiliary_allowance_override:
        If provided, overrides each zone's individual auxiliary_allowance.
    """

    warnings: list[CalculationWarning] = []
    steps: list[CalculationStep] = []
    zone_results: list[dict[str, Any]] = []

    # --- validate all zones ------------------------------------------------
    for spec in zones:
        _validate_zone_spec(spec)

    # --- compute per-zone areas --------------------------------------------
    total_net = _D("0")
    total_circulation = _D("0")
    total_auxiliary = _D("0")

    for idx, spec in enumerate(zones):
        circ_rate = (
            circulation_allowance_override
            if circulation_allowance_override is not None
            else spec.circulation_allowance
        )
        aux_rate = (
            auxiliary_allowance_override
            if auxiliary_allowance_override is not None
            else spec.auxiliary_allowance
        )

        # Circulation area = net_area × circulation_allowance
        circulation_area = (spec.net_area * circ_rate).quantize(_D("0.01"), rounding=ROUND_HALF_UP)

        # Auxiliary area = net_area × auxiliary_allowance
        auxiliary_area = (spec.net_area * aux_rate).quantize(_D("0.01"), rounding=ROUND_HALF_UP)

        # Design area = net + circulation + auxiliary
        design_area = (spec.net_area + circulation_area + auxiliary_area).quantize(
            _D("0.01"), rounding=ROUND_HALF_UP
        )

        step_id = f"AR-{(idx + 1):03d}"
        steps.append(
            CalculationStep(
                step_id=step_id,
                formula=(
                    f"net_area × (1 + circ_allowance + aux_allowance) = "
                    f"{spec.net_area} × (1 + {circ_rate} + {aux_rate})"
                ),
                description=f"Design area for zone '{spec.zone_code}'",
                inputs={
                    "zone_code": spec.zone_code,
                    "net_area": str(spec.net_area),
                    "circulation_allowance": str(circ_rate),
                    "auxiliary_allowance": str(aux_rate),
                },
                output_name=f"{spec.zone_code}.design_area",
                output_value=str(design_area),
            )
        )

        total_net += spec.net_area
        total_circulation += circulation_area
        total_auxiliary += auxiliary_area

        zone_results.append(
            {
                "zone_code": spec.zone_code,
                "zone_name": spec.zone_name,
                "net_area": float(spec.net_area),
                "circulation_area": float(circulation_area),
                "auxiliary_area": float(auxiliary_area),
                "design_area": float(design_area),
                "unit": spec.unit,
                "calculation_basis": spec.calculation_basis,
                "warnings": spec.warnings,
            }
        )

        # Carry zone-level warnings into the result
        for msg in spec.warnings:
            warnings.append(
                CalculationWarning(
                    code=f"ZONE_WARNING_{spec.zone_code.upper()}",
                    message=msg,
                    details={"zone_code": spec.zone_code},
                )
            )

    # --- total design area -------------------------------------------------
    total_design = (total_net + total_circulation + total_auxiliary).quantize(
        _D("0.01"), rounding=ROUND_HALF_UP
    )

    steps.append(
        CalculationStep(
            step_id="AR-TOTAL",
            formula="Σ(net_area + circulation_area + auxiliary_area)",
            description="Total design area across all zones",
            inputs={
                "total_net_area": str(total_net),
                "total_circulation_area": str(total_circulation),
                "total_auxiliary_area": str(total_auxiliary),
            },
            output_name="total_design_area",
            output_value=str(total_design),
        )
    )

    summary = AreaSummary(
        total_net_area=total_net,
        total_circulation_area=total_circulation,
        total_auxiliary_area=total_auxiliary,
        total_design_area=total_design,
        zone_area_breakdown=zone_results,
    )

    result_dict = summary.to_dict()

    return CalculationResult(
        success=True,
        calculator_name=CALCULATOR_NAME,
        calculator_version=CALCULATOR_VERSION,
        input_snapshot={"zones": [z.to_dict() for z in zones]},
        result=result_dict,
        steps=steps,
        warnings=warnings,
        requires_review=len(warnings) > 0,
    )
