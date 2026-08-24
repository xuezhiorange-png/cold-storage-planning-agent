"""Map workbench planning outputs into legacy CalculationResult for persistence."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.calculations.domain.result import CalculationResult


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
