"""Tests for evaluation result comparison."""

from __future__ import annotations

from cold_storage.evaluation.compare import compare_evaluation_result
from cold_storage.evaluation.models import (
    ComparisonPolicy,
    DecimalPathRule,
    ExactPathRule,
    IgnoredPathRule,
)


def _policy(
    exact: list[dict] | None = None,
    decimal: list[dict] | None = None,
    ignored: list[dict] | None = None,
) -> ComparisonPolicy:
    return ComparisonPolicy(
        exact_paths=tuple(ExactPathRule(p["path"]) for p in (exact or [])),
        decimal_paths=tuple(
            DecimalPathRule(p["path"], p["mode"], p["scale"], p["unit"], p["rationale"])
            for p in (decimal or [])
        ),
        ignored_paths=tuple(IgnoredPathRule(p["path"], p["reason"]) for p in (ignored or [])),
        artifact_checks=(),
    )


def test_exact_success() -> None:
    """Identical exact paths must pass."""
    policy = _policy(exact=[{"path": "$.value"}])
    result = compare_evaluation_result(
        {"value": 42},
        {"value": 42},
        policy,
    )
    assert result.passed


def test_exact_mismatch() -> None:
    """Different exact values must fail."""
    policy = _policy(exact=[{"path": "$.value"}])
    result = compare_evaluation_result(
        {"value": 42},
        {"value": 99},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) == 1
    assert result.mismatches[0].path == "$.value"


def test_missing_expected() -> None:
    """Missing expected path must fail."""
    policy = _policy(exact=[{"path": "$.missing"}])
    result = compare_evaluation_result(
        {"present": 1},
        {"present": 1},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind.value == "missing_expected"


def test_missing_actual() -> None:
    """Missing actual path must fail."""
    policy = _policy(exact=[{"path": "$.needed"}])
    result = compare_evaluation_result(
        {"needed": 42},
        {"other": 1},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind.value == "missing_actual"


def test_type_mismatch() -> None:
    """String vs int mismatch must fail."""
    policy = _policy(exact=[{"path": "$.value"}])
    result = compare_evaluation_result(
        {"value": 42},
        {"value": "42"},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind.value == "type_mismatch"


def test_bool_vs_int_mismatch() -> None:
    """Bool vs int mismatch must fail."""
    policy = _policy(exact=[{"path": "$.flag"}])
    result = compare_evaluation_result(
        {"flag": True},
        {"flag": 1},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind.value == "type_mismatch"


def test_decimal_quantize_success() -> None:
    """Decimal quantization with matching values must pass."""
    policy = _policy(
        exact=[],
        decimal=[
            {
                "path": "$.area",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "test",
            }
        ],
    )
    result = compare_evaluation_result(
        {"area": 100.00},
        {"area": 100.001},
        policy,
    )
    assert result.passed


def test_decimal_mismatch() -> None:
    """Decimal mismatch beyond tolerance must fail."""
    policy = _policy(
        exact=[],
        decimal=[
            {
                "path": "$.area",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "test",
            }
        ],
    )
    result = compare_evaluation_result(
        {"area": 100.00},
        {"area": 150.00},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind.value == "decimal_mismatch"


def test_extra_actual_field_rejected() -> None:
    """Extra fields in actual not declared in expected must fail."""
    policy = _policy()
    result = compare_evaluation_result(
        {"known": 1},
        {"known": 1, "unexpected": 2},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind.value == "extra_actual_field"


def test_multiple_mismatches_collected() -> None:
    """Multiple mismatches must all be collected."""
    policy = _policy(
        exact=[{"path": "$.a"}, {"path": "$.b"}],
    )
    result = compare_evaluation_result(
        {"a": 1, "b": 2},
        {"a": 10, "b": 20},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) >= 2


def test_ignored_field_does_not_affect() -> None:
    """Ignored fields must not participate in comparison."""
    policy = _policy(
        exact=[{"path": "$.value"}],
        ignored=[{"path": "$.ignore", "reason": "test"}],
    )
    result = compare_evaluation_result(
        {"value": 42, "ignore": "anything"},
        {"value": 42, "ignore": "different"},
        policy,
    )
    assert result.passed
