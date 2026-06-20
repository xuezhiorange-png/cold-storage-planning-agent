"""Scheme domain errors — all scheme-specific exceptions."""

from __future__ import annotations


class SchemeDomainError(Exception):
    """Base for all scheme domain errors."""


class SchemeGenerationError(SchemeDomainError):
    """Raised when scheme generation fails."""


class SchemeValidationError(SchemeDomainError):
    """Raised when a hard constraint fails."""


class WeightSetError(SchemeDomainError):
    """Raised for invalid weight sets."""


class WeightSumError(WeightSetError):
    """Raised when non-hard-constraint weights do not sum to 1.0."""

    def __init__(self, actual_sum: float) -> None:
        self.actual_sum = actual_sum
        super().__init__(f"Non-hard-constraint weights sum to {actual_sum}, expected 1.0")


class NegativeWeightError(WeightSetError):
    """Raised when a weight is negative."""

    def __init__(self, criterion_code: str, weight: float) -> None:
        self.criterion_code = criterion_code
        self.weight = weight
        super().__init__(f"Negative weight for '{criterion_code}': {weight}")


class WeightOutOfRangeError(WeightSetError):
    """Raised when a weight exceeds [0, 1]."""

    def __init__(self, criterion_code: str, weight: float) -> None:
        self.criterion_code = criterion_code
        self.weight = weight
        super().__init__(f"Weight for '{criterion_code}' out of range: {weight}")


class DuplicateCriterionError(WeightSetError):
    """Raised when duplicate criterion codes exist in a weight set."""

    def __init__(self, criterion_code: str) -> None:
        self.criterion_code = criterion_code
        super().__init__(f"Duplicate criterion code: '{criterion_code}'")


class MissingCriterionError(WeightSetError):
    """Raised when a required criterion is missing from a weight set."""

    def __init__(self, criterion_code: str) -> None:
        self.criterion_code = criterion_code
        super().__init__(f"Missing required criterion: '{criterion_code}'")


class WithdrawnWeightSetError(WeightSetError):
    """Raised when trying to use a withdrawn weight set."""

    def __init__(self, weight_set_id: str) -> None:
        self.weight_set_id = weight_set_id
        super().__init__(f"Weight set '{weight_set_id}' is withdrawn")


class NoFeasibleSchemeError(SchemeDomainError):
    """Raised when no scheme passes all hard constraints."""

    def __init__(self) -> None:
        super().__init__("No feasible scheme found — all candidates failed hard constraints")


class SourceCalculationMissingError(SchemeGenerationError):
    """Raised when a required Task 4/5 source calculation is missing."""

    def __init__(self, calculation_name: str) -> None:
        self.calculation_name = calculation_name
        super().__init__(f"Required source calculation missing: '{calculation_name}'")


class SourceSnapshotInvalidError(SchemeGenerationError):
    """Raised when source snapshot hash does not match persisted data."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Source snapshot invalid: {detail}")


class InvalidProfileError(SchemeDomainError):
    """Raised for invalid or missing profile parameters."""

    def __init__(self, profile_code: str, detail: str) -> None:
        self.profile_code = profile_code
        super().__init__(f"Invalid profile '{profile_code}': {detail}")


class MissingProfileParameterError(SchemeDomainError):
    """Raised when a required profile parameter is missing."""

    def __init__(self, profile_code: str, parameter_name: str) -> None:
        self.profile_code = profile_code
        self.parameter_name = parameter_name
        super().__init__(
            f"Missing required parameter '{parameter_name}' for profile '{profile_code}'"
        )


class InvalidProfileParameterError(SchemeDomainError):
    """Raised when a profile parameter has an invalid value."""

    def __init__(self, profile_code: str, parameter_name: str, detail: str) -> None:
        self.profile_code = profile_code
        self.parameter_name = parameter_name
        super().__init__(
            f"Invalid parameter '{parameter_name}' for profile '{profile_code}': {detail}"
        )


class ProjectNotFoundError(SchemeGenerationError):
    """Raised when the project does not exist."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"Project not found: '{project_id}'")


class ProjectVersionNotFoundError(SchemeGenerationError):
    """Raised when the project version does not exist."""

    def __init__(self, project_id: str, version_number: int) -> None:
        self.project_id = project_id
        self.version_number = version_number
        super().__init__(
            f"Project version not found: project '{project_id}' version {version_number}"
        )


class VersionConflictError(SchemeGenerationError):
    """Raised when project version does not belong to the project or calculations don\'t match."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Version conflict: {detail}")


class CompletedRunImmutabilityError(SchemeDomainError):
    """Raised when attempting to modify a completed SchemeRun."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Cannot modify completed scheme run '{run_id}'")


class DivisionByZeroError(SchemeDomainError):
    """Raised when normalization encounters identical min/max."""

    def __init__(self, criterion_code: str) -> None:
        self.criterion_code = criterion_code
        super().__init__(f"All candidates have identical values for '{criterion_code}'")
