"""Deterministic JSON comparison for evaluation results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cold_storage.evaluation.canonicalize import (
    JsonValue,
    canonicalize_json,
    quantize_decimal_value,
)
from cold_storage.evaluation.models import ComparisonPolicy


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


# Sentinel for missing data
class _Missing:
    """Sentinel for a missing path."""


# ---------------------------------------------------------------------------
# JSONPath parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObjectKeySegment:
    """Access an object key by name."""

    key: str


@dataclass(frozen=True, slots=True)
class ArrayIndexSegment:
    """Access an array element by integer index."""

    index: int


@dataclass(frozen=True, slots=True)
class ParsedJsonPath:
    """A parsed JSONPath expression for simple lookup operations."""

    raw: str
    segments: tuple[ObjectKeySegment | ArrayIndexSegment, ...]


def parse_json_path(path_str: str) -> ParsedJsonPath:
    """Parse a simple JSONPath expression.

    Supports the grammar:
      $                 root (no segments)
      $.field           object key access
      $[0]              array index access
      $.items[0]        chained access
      $.matrix[0][1]    repeated array index

    Does NOT support:
      wildcards, recursive descent, filters, negative indexes, slices,
      quoted property expressions, or root arrays as entry point.

    Raises:
        ValueError: If the path uses unsupported syntax.
    """
    if not path_str:
        raise ValueError("Empty JSONPath is not allowed")
    if path_str == "$":
        return ParsedJsonPath(raw=path_str, segments=())

    if not path_str.startswith("$"):
        raise ValueError(f"JSONPath must start with '$': '{path_str}'")

    remainder = path_str[1:]  # strip leading $
    segments: list[ObjectKeySegment | ArrayIndexSegment] = []

    # Parse segments: either .key or [index]
    idx = 0
    while idx < len(remainder):
        ch = remainder[idx]
        if ch == ".":
            # Object key: .field_name
            idx += 1
            start = idx
            while idx < len(remainder) and remainder[idx] not in ("[", "."):
                idx += 1
            key = remainder[start:idx]
            if not key:
                raise ValueError(f"Empty object key in JSONPath: '{path_str}'")
            segments.append(ObjectKeySegment(key=key))
        elif ch == "[":
            # Array index: [digits]
            idx += 1
            start = idx
            while idx < len(remainder) and remainder[idx] != "]":
                idx += 1
            if idx >= len(remainder) or remainder[idx] != "]":
                raise ValueError(f"Unclosed bracket in JSONPath: '{path_str}'")
            idx_str = remainder[start:idx]
            if not idx_str:
                raise ValueError(f"Empty array index in JSONPath: '{path_str}'")
            try:
                index = int(idx_str)
            except ValueError:
                raise ValueError(
                    f"Invalid array index '{idx_str}' in JSONPath: '{path_str}'"
                ) from None
            if index < 0:
                raise ValueError(f"Negative array index not allowed in JSONPath: '{path_str}'")
            segments.append(ArrayIndexSegment(index=index))
            idx += 1  # skip closing ]
        else:
            # Implicit leading .? No — after $ must come . or [
            raise ValueError(f"Unexpected character '{ch}' in JSONPath: '{path_str}'")

    return ParsedJsonPath(raw=path_str, segments=tuple(segments))


def resolve_path(obj: JsonValue, parsed: ParsedJsonPath) -> tuple[JsonValue, bool]:
    """Resolve a parsed JSONPath against a JSON value.

    Returns (value, found) where found is True if the path exists.
    """
    current = obj
    for seg in parsed.segments:
        if isinstance(seg, ObjectKeySegment):
            if not isinstance(current, dict):
                return None, False  # type: ignore[return-value]
            if seg.key not in current:
                return None, False  # type: ignore[return-value]
            current = current[seg.key]
        elif isinstance(seg, ArrayIndexSegment):
            if not isinstance(current, (list, tuple)):
                return None, False  # type: ignore[return-value]
            if seg.index < 0 or seg.index >= len(current):
                return None, False  # type: ignore[return-value]
            current = current[seg.index]
    return current, True


# ---------------------------------------------------------------------------
# Main comparison entry point
# ---------------------------------------------------------------------------


def compare_evaluation_result(
    expected: JsonValue,
    actual: JsonValue,
    policy: ComparisonPolicy,
) -> ComparisonResult:
    """Compare expected vs actual JSON values according to policy.

    Semantics:
    - Expected value defines the complete allowed structure.
    - All non-ignored, non-decimal-override fields in expected are
      recursively compared by exact value and type.
    - Decimal paths override the default exact comparison for those
      specific paths.
    - Ignored paths are removed from both sides before comparison.
    - Extra fields in `actual` that are not in `expected` cause failure.
    - Missing fields in `actual` that are in `expected` cause failure.
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

    # Build decimal path lookup
    decimal_paths_map: dict[str, int] = {}
    for dr in policy.decimal_paths:
        decimal_paths_map[dr.path] = dr.scale

    # Canonicalize both sides (removes ignored paths, applies decimal quantization)
    canon_expected = canonicalize_json(
        expected,
        ignored_paths=policy.ignored_paths,
        decimal_paths=policy.decimal_paths,
    )
    canon_actual = canonicalize_json(
        actual,
        ignored_paths=policy.ignored_paths,
        decimal_paths=policy.decimal_paths,
    )

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
            child_path = f"{path}.{key}" if path != "$" else f"${key}"
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
                child_path = f"{path}.{key}" if path != "$" else f"${key}"
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
                    expected=len(expected),  # type: ignore[arg-type]
                    actual=len(actual),  # type: ignore[arg-type]
                    message=(
                        f"Array length mismatch at '{path}': "
                        f"expected {len(expected)} elements, got {len(actual)}"
                    ),
                )
            )
            # Still compare common elements
            common_len = min(len(expected), len(actual))
            # Don't return — let it fall through to element comparison
        else:
            common_len = len(expected)

        for i in range(common_len):
            child_path = f"{path}[{i}]"
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
                message=(f"Exact mismatch at '{path}': expected '{expected}', got '{actual}'"),
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
    # Both values are already canonicalized (decimal → string)
    # Expected should be a string from quantize; actual may be int/float/str

    def _to_scalar(v: JsonValue) -> str | int | float | bool | None:
        """Narrow JsonValue to scalar for quantize_decimal_value."""
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
                message=(f"Decimal mismatch at '{path}': expected {d_expected}, got {d_actual}"),
            )
        )
