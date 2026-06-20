from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FormulaReference:
    formula_id: str
    formula_version: str
    expression: str
    description: str


@dataclass(frozen=True)
class CalculationWarning:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalculationError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalculationResult:
    success: bool
    calculator_name: str
    calculator_version: str
    input: dict[str, Any]
    result: dict[str, Any]
    formula_references: list[FormulaReference]
    coefficients: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[CalculationWarning] = field(default_factory=list)
    errors: list[CalculationError] = field(default_factory=list)
    source_references: list[dict[str, Any]] = field(default_factory=list)
    requires_review: bool = False
