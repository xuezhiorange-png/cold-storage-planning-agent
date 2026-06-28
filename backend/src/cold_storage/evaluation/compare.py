"""Deterministic JSON comparison for evaluation results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cold_storage.evaluation.canonicalize import JsonValue, quantize_decimal_value
from cold_storage.evaluation.json_path import (
    append_array_index,
    append_object_key,
    parse_json_path,
    resolve_json_path,
)
from cold_storage.evaluation.models import (
    ComparisonPolicy,
    ExactPathRule,
)

JsonScalar = str | int | float | bool | None


class ComparisonMismatchKind(StrEnum):
    """Stable kind identifiers for comparison mismatches."""

    EXACT_MISMATCH = "exact_mismatch"
    MISSING_EXPECTED = "missing_expected"
    MISSING_ACTUAL = "missing_actual"
    TYPE_MISMATCH = "type_mismatch"
    DECIMAL_MISMATCH = "decimal_mismatch"
    EXTRA_ACTUAL_FIELD = "extra_actual_field"
    ARRAY_LENGTH_MISMATCH = "array_length_mismatch"


@dataclass(frozen=True, slots=True)
class ComparisonMismatch:
    """A single comparison failure with path, kind, and values."""

    path: str
    kind: ComparisonMismatchKind
    expected: JsonValue | None
    actual: JsonValue | None
    message: str


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Aggregate comparison result with all mismatches collected."""

    passed: bool
    mismatches: tuple[ComparisonMismatch, ...]


def compare_evaluation_result(
    expected: JsonValue,
    actual: JsonValue,
    policy: ComparisonPolicy,
) -> ComparisonResult:
    """Compare expected vs actual JSON values according to policy.

    Semantics:
    - Expected value defines the complete allowed structure.
    - Explicitly declared exact_paths are validated for presence on both sides.
    - All non-ignored, non-decimal-override fields in expected are
      recursively compared by exact value and type.
    - Decimal paths override the default exact comparison for those
      specific paths.
    - Ignored paths are removed from both sides before comparison.
    - Extra fields in ``actual`` that are not in ``expected`` cause failure.
    - Missing fields in ``actual`` that are in ``expected`` cause failure.
    - Lists are compared by length and element-wise order.
    - All mismatches are collected (non-fail-fast).
    - Mismatches are ordered deterministically by path.

    Args:
        expected: The expected (golden) JSON value.
        actual: The actual (run-produced) JSON value.
        policy: The comparison policy with exact/decimal/ignored rules.

    Returns:
        ComparisonResult with all collected mismatches.
    """
    mismatches: list[ComparisonMismatch] = []

    # Build decimal path lookup by rendered path strings
    decimal_paths_map: dict[str, int] = {}
    for dr in policy.decimal_paths:
        decimal_paths_map[dr.path] = dr.scale

    # Validate explicitly declared exact_paths
    _validate_exact_paths(expected, actual, policy.exact_paths, mismatches)

    # Canonicalize both sides (removes ignored paths, applies decimal quantization)
    canon_expected = _canonicalize_with_policy(expected, policy)
    canon_actual = _canonicalize_with_policy(actual, policy)

    # Full recursive comparison starting from root
    _compare_recursive(
        path="$",
        expected=canon_expected,
        actual=canon_actual,
        decimal_paths=decimal_paths_map,
        mismatches=mismatches,
    )

    return ComparisonResult(
        passed=len(mismatches) == 0,
        mismatches=tuple(mismatches),
    )


def _canonicalize_with_policy(value: JsonValue, policy: ComparisonPolicy) -> JsonValue:
    """Canonicalize a value using the comparison policy's ignored/decimal paths."""
    from cold_storage.evaluation.canonicalize import canonicalize_json

    return canonicalize_json(
        value,
        ignored_paths=policy.ignored_paths,
        decimal_paths=policy.decimal_paths,
    )


def _validate_exact_paths(
    expected: JsonValue,
    actual: JsonValue,
    exact_paths: tuple[ExactPathRule, ...],
    mismatches: list[ComparisonMismatch],
) -> None:
    """Validate that each declared exact path exists on both sides.

    Collects mismatches for missing paths on either side; does
    not fail-fast.
    """
    for rule in exact_paths:
        try:
            parsed = parse_json_path(rule.path)
        except ValueError as exc:
            mismatches.append(
                ComparisonMismatch(
                    path=rule.path,
                    kind=ComparisonMismatchKind.EXACT_MISMATCH,
                    expected=None,
                    actual=None,
                    message=f"Invalid exact path '{rule.path}': {exc}",
                )
            )
            continue

        exp_val, exp_found = resolve_json_path(expected, parsed)
        act_val, act_found = resolve_json_path(actual, parsed)

        if not exp_found and not act_found:
            mismatches.append(
                ComparisonMismatch(
                    path=rule.path,
                    kind=ComparisonMismatchKind.MISSING_EXPECTED,
                    expected=None,
                    actual=None,
                    message=f"Exact path '{rule.path}' not found in expected or actual data",
                )
            )
        elif not exp_found:
            mismatches.append(
                ComparisonMismatch(
                    path=rule.path,
                    kind=ComparisonMismatchKind.MISSING_EXPECTED,
                    expected=None,
                    actual=act_val,
                    message=f"Exact path '{rule.path}' not found in expected data",
                )
            )
        elif not act_found:
            mismatches.append(
                ComparisonMismatch(
                    path=rule.path,
                    kind=ComparisonMismatchKind.MISSING_ACTUAL,
                    expected=exp_val,
                    actual=None,
                    message=f"Exact path '{rule.path}' not found in actual data",
                )
            )


def _compare_recursive(
    *,
    path: str,
    expected: JsonValue,
    actual: JsonValue,
    decimal_paths: dict[str, int],
    mismatches: list[ComparisonMismatch],
) -> None:
    """Recursively compare expected and actual values.

    Handles dicts, lists, and scalars with type-strict comparison.
    Decimal paths get special treatment (string comparison after quantize).
    """
    # 1. Type mismatch check
    if type(expected) is not type(actual):
        # Special case: bool vs int (bool is subclass of int in Python)
        if isinstance(expected, bool) != isinstance(actual, bool):
            mismatches.append(
                ComparisonMismatch(
                    path=path,
                    kind=ComparisonMismatchKind.TYPE_MISMATCH,
                    expected=expected,
                    actual=actual,
                    message=(
                        f"Type mismatch at '{path}': "
                        f"expected {type(expected).__name__}, "
                        f"got {type(actual).__name__}"
                    ),
                )
            )
            return
        # Non-bool type mismatch
        if type(expected) is not type(actual):
            mismatches.append(
                ComparisonMismatch(
                    path=path,
                    kind=ComparisonMismatchKind.TYPE_MISMATCH,
                    expected=expected,
                    actual=actual,
                    message=(
                        f"Type mismatch at '{path}': "
                        f"expected {type(expected).__name__}, "
                        f"got {type(actual).__name__}"
                    ),
                )
            )
            return

    # 2. Check for decimal override
    if path in decimal_paths:
        scale = decimal_paths[path]
        _compare_decimal(path, expected, actual, scale, mismatches)
        return

    # 3. Dict comparison
    if isinstance(expected, dict) and isinstance(actual, dict):
        # Check all expected keys exist in actual
        for key in sorted(expected):
            child_path = append_object_key(path, key)
            if key not in actual:
                mismatches.append(
                    ComparisonMismatch(
                        path=child_path,
                        kind=ComparisonMismatchKind.MISSING_ACTUAL,
                        expected=expected[key],
                        actual=None,
                        message=f"Expected field '{child_path}' missing from actual data",
                    )
                )
            else:
                _compare_recursive(
                    path=child_path,
                    expected=expected[key],
                    actual=actual[key],
                    decimal_paths=decimal_paths,
                    mismatches=mismatches,
                )

        # Check for extra fields in actual
        for key in sorted(actual):
            if key not in expected:
                child_path = append_object_key(path, key)
                mismatches.append(
                    ComparisonMismatch(
                        path=child_path,
                        kind=ComparisonMismatchKind.EXTRA_ACTUAL_FIELD,
                        expected=None,
                        actual=actual[key],
                        message=f"Unexpected field '{child_path}' in actual data",
                    )
                )
        return

    # 4. List comparison
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            mismatches.append(
                ComparisonMismatch(
                    path=path,
                    kind=ComparisonMismatchKind.ARRAY_LENGTH_MISMATCH,
                    expected=str(len(expected)),
                    actual=str(len(actual)),
                    message=(
                        f"Array length mismatch at '{path}': "
                        f"expected {len(expected)} elements, got {len(actual)}"
                    ),
                )
            )
            common_len = min(len(expected), len(actual))
        else:
            common_len = len(expected)

        for i in range(common_len):
            child_path = append_array_index(path, i)
            _compare_recursive(
                path=child_path,
                expected=expected[i],
                actual=actual[i],
                decimal_paths=decimal_paths,
                mismatches=mismatches,
            )
        return

    # 5. Scalar comparison
    if expected != actual:
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.EXACT_MISMATCH,
                expected=expected,
                actual=actual,
                message=f"Exact mismatch at '{path}': expected '{expected}', got '{actual}'",
            )
        )


def _compare_decimal(
    path: str,
    expected: JsonValue,
    actual: JsonValue,
    scale: int,
    mismatches: list[ComparisonMismatch],
) -> None:
    """Compare two values using deterministic decimal quantization."""

    def _to_scalar(v: JsonValue) -> str | int | float | bool | None:
        if isinstance(v, (str, int, float, bool)):
            return v
        return None

    exp_scalar = _to_scalar(expected)
    act_scalar = _to_scalar(actual)

    try:
        d_expected = quantize_decimal_value(exp_scalar, scale)
    except Exception as exc:
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.DECIMAL_MISMATCH,
                expected=expected,
                actual=actual,
                message=f"Expected value '{expected}' cannot be quantized: {exc}",
            )
        )
        return

    try:
        d_actual = quantize_decimal_value(act_scalar, scale)
    except Exception as exc:
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.DECIMAL_MISMATCH,
                expected=d_expected,
                actual=actual,
                message=f"Actual value '{actual}' cannot be quantized: {exc}",
            )
        )
        return

    if d_expected != d_actual:
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.DECIMAL_MISMATCH,
                expected=d_expected,
                actual=d_actual,
                message=f"Decimal mismatch at '{path}': expected {d_expected}, got {d_actual}",
            )
        )
