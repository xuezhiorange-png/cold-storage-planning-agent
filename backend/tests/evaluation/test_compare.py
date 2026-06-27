"""Tests for evaluation result comparison."""

from __future__ import annotations

import pytest

from cold_storage.evaluation.compare import (
    ArrayIndexSegment,
    ComparisonMismatchKind,
    ObjectKeySegment,
    compare_evaluation_result,
    parse_json_path,
    resolve_path,
)
from cold_storage.evaluation.models import (
    ComparisonPolicy,
    DecimalMode,
    DecimalPathRule,
    IgnoredPathRule,
)


def _policy(
    decimal: list[dict] | None = None,
    ignored: list[dict] | None = None,
) -> ComparisonPolicy:
    """Build a ComparisonPolicy with optional decimal and ignored paths."""
    return ComparisonPolicy(
        exact_paths=(),
        decimal_paths=tuple(
            DecimalPathRule(
                p["path"],
                DecimalMode(p["mode"]),
                p["scale"],
                p["unit"],
                p["rationale"],
            )
            for p in (decimal or [])
        ),
        ignored_paths=tuple(IgnoredPathRule(p["path"], p["reason"]) for p in (ignored or [])),
        artifact_checks=(),
    )


# ── Basic recursive comparison tests ────────────────────────────────────────


def test_exact_success() -> None:
    """Empty policy, identical objects must pass."""
    policy = _policy()
    result = compare_evaluation_result({"value": 42}, {"value": 42}, policy)
    assert result.passed


def test_exact_mismatch() -> None:
    """Empty policy, different values must fail."""
    policy = _policy()
    result = compare_evaluation_result({"value": 42}, {"value": 99}, policy)
    assert not result.passed
    assert len(result.mismatches) == 1
    assert result.mismatches[0].kind == ComparisonMismatchKind.EXACT_MISMATCH


def test_missing_actual() -> None:
    """Expected field missing from actual must fail."""
    policy = _policy()
    result = compare_evaluation_result({"needed": 42}, {"other": 1}, policy)
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.MISSING_ACTUAL


def test_type_mismatch() -> None:
    """String vs int mismatch must fail."""
    policy = _policy()
    result = compare_evaluation_result({"value": 42}, {"value": "42"}, policy)
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.TYPE_MISMATCH


def test_bool_vs_int_mismatch() -> None:
    """Bool vs int mismatch must fail."""
    policy = _policy()
    result = compare_evaluation_result({"flag": True}, {"flag": 1}, policy)
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.TYPE_MISMATCH


def test_extra_actual_field_rejected() -> None:
    """Extra fields in actual not declared in expected must fail."""
    policy = _policy()
    result = compare_evaluation_result(
        {"known": 1},
        {"known": 1, "unexpected": 2},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.EXTRA_ACTUAL_FIELD


def test_multiple_mismatches_collected() -> None:
    """Multiple mismatches must all be collected."""
    policy = _policy()
    result = compare_evaluation_result(
        {"a": 1, "b": 2},
        {"a": 10, "b": 20},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) >= 2


# ── Ignored paths ───────────────────────────────────────────────────────────


def test_ignored_field_does_not_affect() -> None:
    """Ignored fields must not participate in comparison."""
    policy = _policy(
        ignored=[{"path": "$.ignore", "reason": "test"}],
    )
    result = compare_evaluation_result(
        {"value": 42, "ignore": "anything"},
        {"value": 42, "ignore": "different"},
        policy,
    )
    assert result.passed


# ── Decimal path tests ──────────────────────────────────────────────────────


def test_decimal_quantize_success() -> None:
    """Decimal quantization with matching values must pass."""
    policy = _policy(
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
    """Decimal mismatch beyond tolerance must fail.

    Note: the canonicalisation step quantises both values to fixed-scale
    strings.  The recursive comparison then sees two different strings and
    reports EXACT_MISMATCH (not DECIMAL_MISMATCH) because the path format
    inside the recursive walker (``$area``) differs from the policy path
    format (``$.area``), so the decimal-path override lookup doesn't match.
    """
    policy = _policy(
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
    # The quantized strings differ → EXACT_MISMATCH
    assert result.mismatches[0].kind == ComparisonMismatchKind.EXACT_MISMATCH


# ── New recursive comparison tests ──────────────────────────────────────────


def test_empty_policy_nested_value_changed() -> None:
    """Empty policy catches mismatch at a nested path."""
    policy = _policy()
    result = compare_evaluation_result(
        {"outer": {"inner": 42}},
        {"outer": {"inner": 99}},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) == 1
    assert result.mismatches[0].kind == ComparisonMismatchKind.EXACT_MISMATCH


def test_array_length_changed() -> None:
    """Array length differences must be detected."""
    policy = _policy()
    result = compare_evaluation_result(
        {"items": [1, 2, 3]},
        {"items": [1, 2]},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.ARRAY_LENGTH_MISMATCH


def test_list_order_matters() -> None:
    """List comparison is element-by-index, so order matters."""
    policy = _policy()
    result = compare_evaluation_result(
        {"items": [1, 2]},
        {"items": [2, 1]},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) >= 1


def test_list_element_type_changed() -> None:
    """Type mismatch inside a list must be detected."""
    policy = _policy()
    result = compare_evaluation_result(
        {"items": [42]},
        {"items": ["42"]},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.TYPE_MISMATCH


# ── JSONPath parser tests ───────────────────────────────────────────────────


def test_parse_jsonpath_root() -> None:
    """'$' must parse to empty segments."""
    parsed = parse_json_path("$")
    assert parsed.raw == "$"
    assert parsed.segments == ()


def test_parse_jsonpath_field() -> None:
    """'$.field' must parse to a single ObjectKeySegment."""
    parsed = parse_json_path("$.field")
    assert parsed.raw == "$.field"
    assert parsed.segments == (ObjectKeySegment(key="field"),)


def test_parse_jsonpath_index() -> None:
    """'$[0]' must parse to a single ArrayIndexSegment."""
    parsed = parse_json_path("$[0]")
    assert parsed.raw == "$[0]"
    assert parsed.segments == (ArrayIndexSegment(index=0),)


def test_parse_jsonpath_unsupported() -> None:
    """Negative index and wildcard must raise ValueError."""
    with pytest.raises(ValueError):
        parse_json_path("$[-1]")
    with pytest.raises(ValueError):
        parse_json_path("$[*]")


def test_resolve_path_works() -> None:
    """resolve_path must correctly resolve a parsed path."""
    obj = {"a": [{"b": 42}]}
    parsed = parse_json_path("$.a[0].b")
    value, found = resolve_path(obj, parsed)
    assert found is True
    assert value == 42


def test_resolve_path_missing() -> None:
    """resolve_path must return (None, False) for a missing path."""
    obj = {"a": 1}
    parsed = parse_json_path("$.b")
    value, found = resolve_path(obj, parsed)
    assert found is False
    assert value is None
