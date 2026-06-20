"""Domain exceptions for core planning calculations.

All calculators raise these domain-specific exceptions rather than
generic ValueError or TypeError.  Each exception carries enough context
for callers to produce actionable error messages.
"""

from __future__ import annotations


class CoreCalculationError(Exception):
    """Base class for all core-calculation domain errors."""


class MissingCalculationInputError(CoreCalculationError):
    """Raised when a required input field is absent or None."""

    def __init__(self, calculator: str, field_name: str) -> None:
        self.calculator = calculator
        self.field_name = field_name
        super().__init__(f"{calculator}: required input '{field_name}' is missing or None")


class InvalidCalculationInputError(CoreCalculationError):
    """Raised when an input value violates a domain constraint (e.g. ≤ 0)."""

    def __init__(self, calculator: str, field_name: str, value: object) -> None:
        self.calculator = calculator
        self.field_name = field_name
        self.value = value
        super().__init__(f"{calculator}: input '{field_name}' has invalid value {value}")


class CoefficientMissingError(CoreCalculationError):
    """Raised when a required coefficient is not present in the CoefficientSet."""

    def __init__(self, calculator: str, coefficient_code: str) -> None:
        self.calculator = calculator
        self.coefficient_code = coefficient_code
        super().__init__(f"{calculator}: required coefficient '{coefficient_code}' not found")


class CoefficientConflictError(CoreCalculationError):
    """Raised when a coefficient code is found with conflicting revisions."""

    def __init__(self, calculator: str, coefficient_code: str, detail: str) -> None:
        self.calculator = calculator
        self.coefficient_code = coefficient_code
        self.detail = detail
        super().__init__(f"{calculator}: coefficient '{coefficient_code}' conflict — {detail}")


class CapacityShortfallError(CoreCalculationError):
    """Raised when a design capacity cannot meet the demand within limits."""

    def __init__(self, calculator: str, short_by: object, unit: str = "") -> None:
        self.calculator = calculator
        self.short_by = short_by
        self.unit = unit
        super().__init__(f"{calculator}: capacity shortfall of {short_by} {unit}".strip())


class CalculationConsistencyError(CoreCalculationError):
    """Raised when the orchestration layer detects cross-calculator inconsistencies."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Calculation consistency check failed: {detail}")


class LockedProjectVersionError(CoreCalculationError):
    """Raised when attempting to write results to a locked project version."""

    def __init__(self, version_id: str, status: str) -> None:
        self.version_id = version_id
        self.status = status
        super().__init__(
            f"Project version {version_id} (status={status}) is locked; "
            "cannot save calculation results"
        )
