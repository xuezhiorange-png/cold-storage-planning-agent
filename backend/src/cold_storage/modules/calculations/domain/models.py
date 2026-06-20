"""Input and output models for the core planning calculators.

Key design decisions:
- ``CalculationInput`` is a frozen dataclass whose numeric values are
  ``decimal.Decimal`` to guarantee deterministic arithmetic.
- ``CalculationResult`` carries the same traceability payload that the
  existing ``result.CalculationResult`` uses (formula references,
  coefficient references, assumptions, warnings).
- ``CoefficientReference`` is the serialisable snapshot of a single
  coefficient value used during a calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# Coefficient reference — lightweight provenance record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoefficientReference:
    """Snapshot of a single coefficient value used in a calculation."""

    revision_id: str
    code: str
    value: Decimal
    unit: str
    status: str
    source_type: str = "demo"
    source_reference: str = ""
    requires_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "code": self.code,
            "value": float(self.value),
            "unit": self.unit,
            "status": self.status,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "requires_review": self.requires_review,
        }


# ---------------------------------------------------------------------------
# Calculation step — records one atomic operation within a calculator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalculationStep:
    """One atomic step inside a calculator, for traceability."""

    step_id: str
    formula: str
    description: str
    inputs: dict[str, str]
    output_name: str
    output_value: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "formula": self.formula,
            "description": self.description,
            "inputs": self.inputs,
            "output_name": self.output_name,
            "output_value": self.output_value,
        }


# ---------------------------------------------------------------------------
# Calculation warning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalculationWarning:
    """Non-fatal issue identified during a calculation."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Calculation input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalculationInput:
    """Generic wrapper carrying all named numeric inputs for a calculator.

    This is *not* a typed input like ``ThroughputInput``; it is the
    serialisable form that lives inside ``CalculationResult.input``.
    """

    calculator_name: str
    calculator_version: str
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        serialised: dict[str, Any] = {}
        for key, value in self.values.items():
            if isinstance(value, Decimal):
                serialised[key] = str(value)
            else:
                serialised[key] = value
        return {
            "calculator_name": self.calculator_name,
            "calculator_version": self.calculator_version,
            "values": serialised,
        }


# ---------------------------------------------------------------------------
# Calculation output — the final return type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalculationResult:
    """Deterministic, traceable output of a core planning calculator.

    This is intentionally separate from the legacy ``result.CalculationResult``
    to avoid coupling.  The orchestration layer bridges the two.
    """

    success: bool
    calculator_name: str
    calculator_version: str
    input_snapshot: dict[str, Any]
    result: dict[str, Any]
    steps: list[CalculationStep] = field(default_factory=list)
    coefficient_references: list[CoefficientReference] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[CalculationWarning] = field(default_factory=list)
    requires_review: bool = False
    calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "calculator_name": self.calculator_name,
            "calculator_version": self.calculator_version,
            "input_snapshot": self.input_snapshot,
            "result": self.result,
            "steps": [s.to_dict() for s in self.steps],
            "coefficient_references": [c.to_dict() for c in self.coefficient_references],
            "assumptions": self.assumptions,
            "warnings": [w.to_dict() for w in self.warnings],
            "requires_review": self.requires_review,
            "calculated_at": self.calculated_at.isoformat(),
            "correlation_id": self.correlation_id,
        }
