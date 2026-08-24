"""Map workbench calculator outputs into legacy CalculationResult for persistence."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.calculations.domain.models import (
    CalculationResult as NewCalculationResult,
)
from cold_storage.modules.calculations.domain.result import (
    CalculationError,
    CalculationResult,
    CalculationWarning,
    FormulaReference,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
)


def new_calculation_result_to_legacy(result: NewCalculationResult) -> CalculationResult:
    """Bridge the Task 5 calculator result shape into project persistence."""
    warnings = [
        CalculationWarning(w.code, w.message, dict(w.details)) for w in result.warnings
    ]
    formulas = [
        FormulaReference(
            step.step_id,
            result.calculator_version,
            step.formula,
            step.description,
        )
        for step in result.steps
    ]
    coefficients = [ref.to_dict() for ref in result.coefficient_references]
    return CalculationResult(
        success=result.success,
        calculator_name=result.calculator_name,
        calculator_version=result.calculator_version,
        input=result.input_snapshot,
        result=result.result,
        formula_references=formulas,
        coefficients=coefficients,
        assumptions=list(result.assumptions),
        warnings=warnings,
        requires_review=result.requires_review,
    )


def adapter_result_to_legacy(result: AdapterResult) -> CalculationResult:
    """Bridge a production adapter result into project persistence."""
    warnings = [
        CalculationWarning(w.code, w.message, dict(w.details)) for w in result.warnings
    ]
    errors = [
        CalculationError(b.code, b.message, dict(b.details)) for b in result.blockers
    ]
    formulas = [
        FormulaReference(
            str(f.get("formula_id", "")),
            str(f.get("formula_version", "")),
            str(f.get("expression", "")),
            str(f.get("description", "")),
        )
        for f in result.provenance.formulas
        if isinstance(f, dict)
    ]
    coefficients = [
        dict(c) for c in result.provenance.coefficients if isinstance(c, dict)
    ]
    source_references = [
        dict(s) for s in result.provenance.source_references if isinstance(s, dict)
    ]
    return CalculationResult(
        success=result.calculator_success and not result.blockers,
        calculator_name=result.calculator_name,
        calculator_version=result.calculator_version,
        input=dict(result.execution_input_snapshot),
        result=dict(result.payload),
        formula_references=formulas,
        coefficients=coefficients,
        assumptions=list(result.provenance.assumptions),
        warnings=warnings,
        errors=errors,
        source_references=source_references,
        requires_review=result.requires_review,
    )


def power_configuration_to_legacy(power_configuration: dict[str, Any]) -> CalculationResult:
    """Persist the workbench equipment/power table as a calculation run."""
    return CalculationResult(
        success=True,
        calculator_name="power_configuration",
        calculator_version="1.0.0",
        input={},
        result=power_configuration,
        formula_references=[],
        assumptions=list(power_configuration.get("assumptions", [])),
        requires_review=bool(power_configuration.get("requires_review", True)),
    )
