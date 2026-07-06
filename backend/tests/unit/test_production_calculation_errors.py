"""Unit tests for the Phase 2 error model.

The error model is fail-closed: every error carries a stable
machine-readable code, a field tag, and a details mapping.  These
tests verify the contract — callers MUST NOT parse ``message``
text to determine error class.
"""

from __future__ import annotations

import pytest

from cold_storage.modules.orchestration.application.production_calculation.errors import (
    AdapterContractViolationError,
    CalculatorRejectedInputError,
    InvalidProjectInputError,
    MissingApprovedProjectVersionError,
    ProductionCalculationErrorCode,
    UnsupportedReviewRequiredOutputError,
)


class TestInvalidProjectInputError:
    def test_field_is_carried(self) -> None:
        err = InvalidProjectInputError(field_name="actor", reason="empty")
        assert err.field == "actor"
        assert err.code is ProductionCalculationErrorCode.PROJ_INPUT_INVALID
        assert "empty" in str(err)
        assert err.details["field"] == "actor"
        assert err.details["reason"] == "empty"

    def test_code_is_machine_readable(self) -> None:
        err = InvalidProjectInputError(field_name="x", reason="y")
        assert err.code.value == "PROJ_INPUT_INVALID"


class TestMissingApprovedProjectVersionError:
    def test_includes_observed_metadata(self) -> None:
        err = MissingApprovedProjectVersionError(
            project_id="proj-1",
            project_version_id="v-1",
            observed_status="DRAFT",
            is_archived=False,
        )
        assert err.code is ProductionCalculationErrorCode.PROJ_VERSION_NOT_APPROVED
        assert err.field == "project_version_id"
        assert err.details["project_id"] == "proj-1"
        assert err.details["observed_status"] == "DRAFT"
        assert err.details["is_archived"] is False

    def test_optional_observed_metadata(self) -> None:
        err = MissingApprovedProjectVersionError(project_id="proj-1", project_version_id="v-1")
        assert err.details["observed_status"] is None
        assert err.details["is_archived"] is None


class TestCalculatorRejectedInputError:
    def test_carries_calculation_type(self) -> None:
        err = CalculatorRejectedInputError(
            calculation_type="cooling_load",
            reason="missing fields",
        )
        assert err.code is ProductionCalculationErrorCode.CALCULATOR_REJECTED_INPUT
        assert err.details["calculation_type"] == "cooling_load"
        assert err.details["reason"] == "missing fields"


class TestUnsupportedReviewRequiredOutputError:
    def test_carries_calculation_type(self) -> None:
        err = UnsupportedReviewRequiredOutputError(calculation_type="investment")
        assert err.code is ProductionCalculationErrorCode.CALC_OUTPUT_REVIEW_REQUIRED
        assert err.field == "requires_review"
        assert err.details["calculation_type"] == "investment"


class TestAdapterContractViolationError:
    def test_carries_invariant(self) -> None:
        err = AdapterContractViolationError(
            calculation_type="cooling_load",
            invariant="content_hash mismatch",
        )
        assert err.code is ProductionCalculationErrorCode.ADAPTER_CONTRACT_VIOLATION
        assert err.field == "adapter_result"
        assert err.details["invariant"] == "content_hash mismatch"


class TestErrorCodeEnumeration:
    @pytest.mark.parametrize(
        "code",
        [
            "PROJ_VERSION_NOT_APPROVED",
            "PROJ_INPUT_INVALID",
            "CALCULATOR_REJECTED_INPUT",
            "CALC_OUTPUT_REVIEW_REQUIRED",
            "ADAPTER_CONTRACT_VIOLATION",
        ],
    )
    def test_all_phase2_codes_exist(self, code: str) -> None:
        # Each documented Phase 2 code must exist in the enum.
        assert ProductionCalculationErrorCode(code).value == code
