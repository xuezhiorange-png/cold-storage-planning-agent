"""Structured error hierarchy for evaluation module."""

from __future__ import annotations


class EvaluationError(Exception):
    """Base evaluation error with stable error code.

    Subclasses pass code, message, and optional field as positional args
    to ``Exception.__init__`` so that ``str(exc)`` is automatically populated.
    """

    def __init__(
        self,
        code: str,
        message: str,
        field: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.field = field
        super().__init__(f"[{code}] {message}")

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class EvaluationManifestError(EvaluationError):
    """Base manifest processing error."""


class ManifestFileNotFoundError(EvaluationManifestError):
    """Referenced manifest file does not exist."""


class ManifestJsonDecodeError(EvaluationManifestError):
    """Manifest file is not valid JSON."""


class ManifestSchemaError(EvaluationManifestError):
    """JSON Schema validation failure."""


class ManifestSemanticError(EvaluationManifestError):
    """Semantic validation failure beyond schema."""


class UnsafeEvaluationPathError(EvaluationError):
    """Referenced path escapes the evaluation root or is absolute."""


class DuplicateScenarioIdError(ManifestSemanticError):
    """Two or more scenarios share the same ID."""


class DuplicateComparisonPathError(ManifestSemanticError):
    """Duplicate comparison policy path within the same scenario."""


class ConflictingComparisonPathError(ManifestSemanticError):
    """Same path appears in two different policy categories (e.g. exact and ignored)."""


class UnknownSchemaVersionError(ManifestSemanticError):
    """Schema version is not recognized by this evaluator."""


class DecimalPolicyError(ManifestSemanticError):
    """Invalid decimal path rule."""


class IgnorePolicyError(ManifestSemanticError):
    """Invalid ignored path rule."""


class RunDirectoryError(EvaluationError):
    """Run directory operation error."""


class RunDirectoryExistsError(RunDirectoryError):
    """Target run directory already exists."""


class RunStateError(RunDirectoryError):
    """Invalid run state transition."""


class CommandNotImplementedError(EvaluationError):
    """CLI command not yet implemented."""


class RunSummaryNotFoundError(RunDirectoryError):
    """Run summary file does not exist."""


class RunSummaryInvalidError(RunDirectoryError):
    """Run summary JSON is malformed."""


class RunIdentityMismatchError(RunDirectoryError):
    """Run summary identity does not match expected."""


class RunManifestMismatchError(RunDirectoryError):
    """Run summary manifest hash does not match expected."""


class RunSummaryStatusInvalidError(RunDirectoryError):
    """Run summary claims passed but run.json status does not match."""


class CanonicalValueError(EvaluationError):
    """Invalid value encountered during canonicalization."""


class DecimalValueInvalidError(DecimalPolicyError):
    """Decimal quantization failed due to invalid value."""


class DecimalNonFiniteError(DecimalPolicyError):
    """Decimal quantization received non-finite value."""


class DecimalQuantizeFailedError(DecimalPolicyError):
    """Decimal quantization operation failed."""


class JsonPathInvalidError(EvaluationError):
    """Invalid JSONPath syntax in comparison policy."""


class RunIdInvalidError(RunDirectoryError):
    """Run ID has invalid format or is a path traversal attempt."""


class RunInputInvalidError(RunDirectoryError):
    """Run creation input validation error."""


class EvaluationPrerequisiteMissingError(EvaluationError):
    """A required production prerequisite is not yet available.

    Raised when the evaluation runner needs a formal production
    orchestration/persistence capability that has not yet been
    implemented.  The evaluation module MUST NOT fabricate its own
    CalculationRunRecord or engineer its own input synthesis.

    This is a structured blocker — not a business outcome.
    The baseline contract still requires ``success``; this error
    marks the *evaluation harness* as blocked, not the scenario
    as ``blocked``.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str = "scheme_source_calculations",
        details: dict[str, object] | None = None,
    ) -> None:
        self.details = details or {
            "required_calculation_types": [
                "zone",
                "investment",
                "cooling_load",
                "equipment",
            ],
            "missing_capability": "formal_application_orchestration_and_persistence",
            "task_status": "blocked",
        }
        super().__init__(
            code="EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING",
            message=message,
            field=field,
        )


class RunIdentityValidationIssue(Exception):
    """Structured internal validation issue carrying *field* and *message* separately.

    Never exposed to public API callers.  Caught internally and converted to
    the appropriate public error type with the exact *field* preserved.

    Args:
        field: The exact field name that failed validation (e.g. ``"suite_id"``,
            ``"scenario_ids[0]"``, ``"manifest_sha256"``).
        message: Human-readable description of the violation.

    Note:
        *field* is NOT parsed from a formatted string — it is stored directly
        on the exception object.  Public API contract guarantees every error
        exposes the same field value as the internal issue.
    """

    def __init__(self, *, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(message)
