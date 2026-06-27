"""Deterministic JSON comparison for evaluation results."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from cold_storage.evaluation.canonicalize import (
    JsonValue,
    canonicalize_json,
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

    Collects all mismatches (non-fail-fast).  Returns passed=True only
    when every declared check passes with no extra actual fields.

    Args:
        expected: The expected (golden) JSON value.
        actual: The actual (run-produced) JSON value.
        policy: The comparison policy with exact/decimal/ignored/artifact rules.

    Returns:
        ComparisonResult with all collected mismatches.
    """
    mismatches: list[ComparisonMismatch] = []

    # Canonicalize both sides
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

    # Compare exact and decimal paths
    all_compared_paths: set[str] = set()

    for exact_rule in policy.exact_paths:
        all_compared_paths.add(exact_rule.path)
        _compare_exact(exact_rule.path, canon_expected, canon_actual, mismatches)

    for decimal_rule in policy.decimal_paths:
        all_compared_paths.add(decimal_rule.path)
        _compare_decimal(
            decimal_rule.path, canon_expected, canon_actual, decimal_rule.scale, mismatches
        )

    # Check for extra actual fields not in expected
    _check_extra_actual("$", canon_expected, canon_actual, all_compared_paths, mismatches)

    return ComparisonResult(
        passed=len(mismatches) == 0,
        mismatches=tuple(mismatches),
    )


def _get_by_path(obj: JsonValue, path: str) -> JsonValue | _Missing:
    """Resolve a simple JSONPath like ``$.field.sub[0]``."""
    if not path.startswith("$"):
        return _Missing()
    if path == "$":
        return obj

    parts = path.removeprefix("$.").replace("].[", "[").split(".")
    current = obj
    for part in parts:
        if "[" in part and part.endswith("]"):
            key, rest = part.split("[", 1)
            idx_str = rest.rstrip("]")
            if key:
                if not isinstance(current, dict) or key not in current:
                    return _Missing()
                current = current[key]
            if idx_str:
                if not isinstance(current, (list, tuple)):
                    return _Missing()
                try:
                    idx = int(idx_str)
                except ValueError:
                    return _Missing()
                if idx < 0 or idx >= len(current):
                    return _Missing()
                current = current[idx]
        else:
            if not isinstance(current, dict):
                return _Missing()
            if part not in current:
                return _Missing()
            current = current[part]
    return current


def _compare_exact(
    path: str,
    expected: JsonValue,
    actual: JsonValue,
    mismatches: list[ComparisonMismatch],
) -> None:
    expected_val = _get_by_path(expected, path)
    actual_val = _get_by_path(actual, path)

    # Convert _Missing to None for comparison dataclass
    _exp: JsonValue | None = None if isinstance(expected_val, _Missing) else expected_val
    _act: JsonValue | None = None if isinstance(actual_val, _Missing) else actual_val

    if isinstance(expected_val, _Missing):
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.MISSING_EXPECTED,
                expected=None,
                actual=_act,
                message=f"Expected path '{path}' not found in expected data",
            )
        )
        return

    if isinstance(actual_val, _Missing):
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.MISSING_ACTUAL,
                expected=_exp,
                actual=None,
                message=f"Expected path '{path}' not found in actual data",
            )
        )
        return

    if type(expected_val) is not type(actual_val):
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.TYPE_MISMATCH,
                expected=_exp,
                actual=_act,
                message=(
                    f"Type mismatch at '{path}': "
                    f"expected {type(expected_val).__name__}, "
                    f"got {type(actual_val).__name__}"
                ),
            )
        )
        return

    # Bool vs int: bool is subclass of int in Python, but we must reject
    if isinstance(expected_val, bool) and not isinstance(actual_val, bool):
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.TYPE_MISMATCH,
                expected=_exp,
                actual=_act,
                message=f"Bool/int mismatch at '{path}': expected bool, got int",
            )
        )
        return
    if isinstance(actual_val, bool) and not isinstance(expected_val, bool):
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.TYPE_MISMATCH,
                expected=_exp,
                actual=_act,
                message=f"Bool/int mismatch at '{path}': expected int, got bool",
            )
        )
        return

    if expected_val != actual_val:
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.EXACT_MISMATCH,
                expected=_exp,
                actual=_act,
                message=(
                    f"Exact mismatch at '{path}': expected '{expected_val}', got '{actual_val}'"
                ),
            )
        )


def _compare_decimal(
    path: str,
    expected: JsonValue,
    actual: JsonValue,
    scale: int,
    mismatches: list[ComparisonMismatch],
) -> None:
    expected_val = _get_by_path(expected, path)
    actual_val = _get_by_path(actual, path)

    # Convert _Missing to None for comparison dataclass
    _exp: JsonValue | None = None if isinstance(expected_val, _Missing) else expected_val
    _act: JsonValue | None = None if isinstance(actual_val, _Missing) else actual_val

    if isinstance(expected_val, _Missing):
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.MISSING_EXPECTED,
                expected=None,
                actual=_act,
                message=f"Decimal path '{path}' not found in expected data",
            )
        )
        return

    if isinstance(actual_val, _Missing):
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.MISSING_ACTUAL,
                expected=_exp,
                actual=None,
                message=f"Decimal path '{path}' not found in actual data",
            )
        )
        return

    try:
        d_expected = Decimal(str(expected_val)).quantize(Decimal(10) ** -scale)
        d_actual = Decimal(str(actual_val)).quantize(Decimal(10) ** -scale)
    except (ValueError, TypeError) as exc:
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.DECIMAL_MISMATCH,
                expected=_exp,
                actual=_act,
                message=f"Decimal parse error at '{path}': {exc}",
            )
        )
        return

    if d_expected != d_actual:
        mismatches.append(
            ComparisonMismatch(
                path=path,
                kind=ComparisonMismatchKind.DECIMAL_MISMATCH,
                expected=float(d_expected),
                actual=float(d_actual),
                message=f"Decimal mismatch at '{path}': expected {d_expected}, got {d_actual}",
            )
        )


def _check_extra_actual(
    path: str,
    expected: JsonValue,
    actual: JsonValue,
    compared: set[str],
    mismatches: list[ComparisonMismatch],
) -> None:
    """Detect extra fields in actual that don't exist in expected.

    Only checks fields that are dicts (object keys). Array elements
    are compared positionally.
    """
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return

    for key in sorted(actual):
        child = f"{path}.{key}"
        if key not in expected:
            # Check if this path was explicitly compared
            if child not in compared:
                mismatches.append(
                    ComparisonMismatch(
                        path=child,
                        kind=ComparisonMismatchKind.EXTRA_ACTUAL_FIELD,
                        expected=None,
                        actual=actual[key],
                        message=f"Unexpected field '{child}' in actual data",
                    )
                )
        elif isinstance(expected[key], dict) and isinstance(actual[key], dict):
            _check_extra_actual(child, expected[key], actual[key], compared, mismatches)


class _Missing:
    """Sentinel for a missing path."""
