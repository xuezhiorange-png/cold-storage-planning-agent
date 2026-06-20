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


class MissingSourceDataError(SchemeGenerationError):
    """Raised when required Task 4/5 source data is missing."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        super().__init__(f"Required source data missing: '{source_name}'")


class InvalidProfileError(SchemeDomainError):
    """Raised for invalid or missing profile parameters."""

    def __init__(self, profile_code: str, detail: str) -> None:
        self.profile_code = profile_code
        super().__init__(f"Invalid profile '{profile_code}': {detail}")


class DivisionByZeroError(SchemeDomainError):
    """Raised when normalization encounters identical min/max."""

    def __init__(self, criterion_code: str) -> None:
        self.criterion_code = criterion_code
        super().__init__(f"All candidates have identical values for '{criterion_code}'")
