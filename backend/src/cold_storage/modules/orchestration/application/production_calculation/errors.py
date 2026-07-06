"""Task 11B Phase 2 — error model for production calculation ports & adapters.

The error model is fail-closed: every error is a structured exception
with a machine-readable ``code`` and a ``field`` tag so callers can
map it back to the input that caused the failure.  Callers MUST NOT
parse ``message`` text to determine error class.

Mapping to Charles's Round 8 P0 contracts
-----------------------------------------
* ``PROJ_VERSION_NOT_APPROVED`` — missing approved project version
* ``PROJ_INPUT_INVALID`` — invalid project input
* ``CALCULATOR_REJECTED_INPUT`` — calculator rejected input
* ``CALC_OUTPUT_REVIEW_REQUIRED`` — unsupported review-required output
* ``ADAPTER_CONTRACT_VIOLATION`` — adapter contract violation
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class ProductionCalculationErrorCode(StrEnum):
    """Machine-readable error codes for production calculation adapters."""

    PROJ_VERSION_NOT_APPROVED = "PROJ_VERSION_NOT_APPROVED"
    PROJ_INPUT_INVALID = "PROJ_INPUT_INVALID"
    CALCULATOR_REJECTED_INPUT = "CALCULATOR_REJECTED_INPUT"
    CALC_OUTPUT_REVIEW_REQUIRED = "CALC_OUTPUT_REVIEW_REQUIRED"
    ADAPTER_CONTRACT_VIOLATION = "ADAPTER_CONTRACT_VIOLATION"


class ProductionCalculationDomainError(Exception):
    """Base for all production calculation adapter errors.

    Carries a stable ``code`` (one of
    :class:`ProductionCalculationErrorCode`), a ``field`` (where the
    failure originated) and a ``details`` mapping so callers can map
    the error back to its origin without parsing the message.
    """

    code: ProductionCalculationErrorCode
    field: str

    def __init__(
        self,
        *,
        code: ProductionCalculationErrorCode,
        message: str,
        field: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.details: Mapping[str, object] = details if details is not None else {}


# ── Preflight errors ────────────────────────────────────────────────────────


class MissingApprovedProjectVersionError(ProductionCalculationDomainError):
    """The read port did not return an approved project version.

    Raised when the approved project version read port returns
    ``None`` (version not found), returns an archived version, or
    returns a version whose status is not ``APPROVED``.  This is
    a fail-closed outcome — adapters MUST NOT proceed without an
    approved version.
    """

    def __init__(
        self,
        *,
        project_id: str,
        project_version_id: str,
        observed_status: str | None = None,
        is_archived: bool | None = None,
    ) -> None:
        observed = (
            f" (status={observed_status!r}, archived={is_archived})"
            if observed_status is not None or is_archived is not None
            else ""
        )
        super().__init__(
            code=ProductionCalculationErrorCode.PROJ_VERSION_NOT_APPROVED,
            message=(
                f"Approved project version not available for project={project_id!r}, "
                f"version={project_version_id!r}{observed}"
            ),
            field="project_version_id",
            details={
                "project_id": project_id,
                "project_version_id": project_version_id,
                "observed_status": observed_status,
                "is_archived": is_archived,
            },
        )


class InvalidProjectInputError(ProductionCalculationDomainError):
    """The approved project version snapshot is missing required fields.

    Raised when the projection helper cannot build a typed
    ``CalculatorInputProjection`` because the upstream snapshot
    lacks required fields or violates the projection contract.
    """

    def __init__(self, *, field_name: str, reason: str) -> None:
        super().__init__(
            code=ProductionCalculationErrorCode.PROJ_INPUT_INVALID,
            message=f"Invalid project input at {field_name!r}: {reason}",
            field=field_name,
            details={"field": field_name, "reason": reason},
        )


# ── Adapter errors ─────────────────────────────────────────────────────────


class CalculatorRejectedInputError(ProductionCalculationDomainError):
    """The calculator itself returned ``success=False`` or raised.

    The adapter propagates the calculator's structured error
    message as a typed blocker.  This error is raised when the
    adapter cannot build an ``AdapterResult`` at all (e.g. the
    calculator raised an exception that was not caught by the
    adapter boundary).
    """

    def __init__(self, *, calculation_type: str, reason: str) -> None:
        super().__init__(
            code=ProductionCalculationErrorCode.CALCULATOR_REJECTED_INPUT,
            message=(f"Calculator for {calculation_type!r} rejected the input: {reason}"),
            field="calculator_input",
            details={"calculation_type": calculation_type, "reason": reason},
        )


class UnsupportedReviewRequiredOutputError(ProductionCalculationDomainError):
    """The adapter contract does not allow suppressing review-required outputs.

    Raised when an adapter attempt to suppress, reclassify, or
    override a calculator's ``requires_review=True`` verdict.  The
    adapter contract forbids suppression; callers MUST surface the
    ``requires_review`` flag verbatim.
    """

    def __init__(self, *, calculation_type: str) -> None:
        super().__init__(
            code=ProductionCalculationErrorCode.CALC_OUTPUT_REVIEW_REQUIRED,
            message=(
                f"Adapter for {calculation_type!r} attempted to suppress a "
                f"review-required calculator output — suppression is forbidden"
            ),
            field="requires_review",
            details={"calculation_type": calculation_type},
        )


class AdapterContractViolationError(ProductionCalculationDomainError):
    """The adapter returned a result that violates its contract.

    Raised by the contract validation helper when the adapter's
    output is missing required fields, carries inconsistent
    content-hash / payload identity, or otherwise violates the
    documented adapter result shape.
    """

    def __init__(self, *, calculation_type: str, invariant: str) -> None:
        super().__init__(
            code=ProductionCalculationErrorCode.ADAPTER_CONTRACT_VIOLATION,
            message=(f"Adapter for {calculation_type!r} violated contract: {invariant}"),
            field="adapter_result",
            details={"calculation_type": calculation_type, "invariant": invariant},
        )
