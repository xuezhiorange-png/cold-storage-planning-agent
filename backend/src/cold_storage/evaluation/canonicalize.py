"""Deterministic JSON canonicalization for evaluation comparisons."""

from __future__ import annotations

import hashlib
import json
import math
from decimal import (
    ROUND_HALF_EVEN,
    Clamped,
    Decimal,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    localcontext,
)
from math import isfinite, isnan

from cold_storage.evaluation.errors import CanonicalValueError, DecimalPolicyError
from cold_storage.evaluation.json_path import append_object_key
from cold_storage.evaluation.models import DecimalMode, DecimalPathRule, IgnoredPathRule

# JSON value: dict, list, str, int, float, bool, None
JsonValue = dict[str, "JsonValue"] | list["JsonValue"] | str | int | float | bool | None
JsonScalar = str | int | float | bool | None

# Frozen precision for Decimal quantization — sufficient for all allowed scales.
_FROZEN_PRECISION = 50
_FROZEN_ROUNDING = ROUND_HALF_EVEN


def quantize_decimal_value(
    value: JsonScalar,
    scale: int,
    *,
    rule: DecimalPathRule | None = None,
) -> str:
    """Quantize a numeric value to a fixed-scale deterministic string.

    Args:
        value: The value to quantize (int, float, or numeric string).
        scale: Number of decimal places (0-20).
        rule: Optional full DecimalPathRule to enforce mode.

    Returns:
        A deterministic fixed-scale string representation.

    Raises:
        DecimalPolicyError: On bool, non-numeric, NaN, Infinity, etc.
    """
    if isinstance(value, bool):
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_VALUE_INVALID",
            message=f"Cannot quantize boolean value: {value}",
            field=str(value),
        )
    if value is None:
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_VALUE_INVALID",
            message="Cannot quantize None",
            field="None",
        )

    # Validate scale at the helper boundary
    if isinstance(scale, bool) or not isinstance(scale, int):
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_POLICY_INVALID",
            message=f"Scale must be an int, got {type(scale).__name__}: {scale!r}",
            field=str(scale),
        )
    if not 0 <= scale <= 20:
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_POLICY_INVALID",
            message=f"Scale {scale} out of range [0, 20]",
            field=str(scale),
        )

    # Enforce mode when a full rule is provided
    if rule is not None and rule.mode != DecimalMode.QUANTIZE:
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_POLICY_INVALID",
            message=f"Unsupported decimal mode '{rule.mode}'; only 'quantize' is supported",
            field=rule.path,
        )

    # Guard against huge exponent that could cause unbounded resource use
    if isinstance(value, (int, float)):
        try:
            exponent = math.floor(math.log10(abs(float(value)))) if value else 0
        except (ValueError, OverflowError):
            raise DecimalPolicyError(
                code="EVAL_DECIMAL_QUANTIZE_FAILED",
                message=f"Cannot determine magnitude for value '{value}'",
                field=str(value),
            ) from None
        max_exponent = 100
        if exponent > max_exponent:
            raise DecimalPolicyError(
                code="EVAL_DECIMAL_QUANTIZE_FAILED",
                message=f"Value '{value}' has exponent {exponent} exceeding max {max_exponent}",
                field=str(value),
            )

    # Parse to Decimal
    try:
        if isinstance(value, float):
            if isnan(value):
                raise DecimalPolicyError(
                    code="EVAL_DECIMAL_NON_FINITE",
                    message="Cannot quantize NaN",
                    field=str(value),
                )
            if not isfinite(value):
                raise DecimalPolicyError(
                    code="EVAL_DECIMAL_NON_FINITE",
                    message=f"Cannot quantize non-finite float: {value}",
                    field=str(value),
                )
            d = Decimal(str(value))
        elif isinstance(value, int):
            d = Decimal(value)
        elif isinstance(value, str):
            if not value:
                raise DecimalPolicyError(
                    code="EVAL_DECIMAL_VALUE_INVALID",
                    message="Cannot quantize empty string",
                    field="",
                )
            # Strip whitespace — Decimal("  ") would succeed but we reject it
            stripped = value.strip()
            if not stripped:
                raise DecimalPolicyError(
                    code="EVAL_DECIMAL_VALUE_INVALID",
                    message="Cannot quantize whitespace-only string",
                    field=value,
                )
            d = Decimal(stripped)
        else:
            raise DecimalPolicyError(
                code="EVAL_DECIMAL_VALUE_INVALID",
                message=f"Unsupported type for decimal quantization: {type(value).__name__}",
                field=str(value),
            )
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_QUANTIZE_FAILED",
            message=f"Cannot quantize value '{value}': {exc}",
            field=str(value),
        ) from exc

    # Check finite for all inputs (catches string "NaN", "Infinity", etc.)
    if not d.is_finite():
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_NON_FINITE",
            message=f"Cannot quantize non-finite value: '{value}'",
            field=str(value),
        )

    # Quantize inside a frozen localcontext so ambient Decimal settings
    # (precision, rounding, traps) cannot change the result.
    try:
        with localcontext() as ctx:
            ctx.prec = _FROZEN_PRECISION
            ctx.rounding = _FROZEN_ROUNDING
            ctx.traps[Clamped] = True
            ctx.traps[Overflow] = True
            # Inexact / Rounded are informational; we keep them enabled to
            # detect unexpected precision loss.
            ctx.traps[Inexact] = False
            ctx.traps[Rounded] = False
            quantized = d.quantize(Decimal(10) ** -scale, context=ctx)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise DecimalPolicyError(
            code="EVAL_DECIMAL_QUANTIZE_FAILED",
            message=f"Quantization failed for value '{value}' at scale {scale}: {exc}",
            field=str(value),
        ) from exc

    return str(quantized)


def canonicalize_json(
    value: JsonValue,
    *,
    ignored_paths: tuple[IgnoredPathRule, ...] = (),
    decimal_paths: tuple[DecimalPathRule, ...] = (),
) -> JsonValue:
    """Canonicalize a deserialized JSON value for deterministic comparison.

    The input is not mutated.  The output uses stable key ordering, removes
    ignored paths, and quantizes decimal-policy values (as strings).

    Args:
        value: The JSON value to canonicalize.
        ignored_paths: Paths to remove from the output.
        decimal_paths: Decimal fields to quantize.

    Returns:
        A new, canonicalized value.
    """
    return _canonicalize(
        value,
        path="$",
        ignored={r.path for r in ignored_paths},
        decimal={r.path: r for r in decimal_paths},
    )


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Serialize a canonicalized JSON value to deterministic bytes.

    Raises:
        CanonicalValueError: If value contains non-standard JSON types.
    """
    _validate_json_types(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_canonical_json(value: JsonValue) -> str:
    """Compute the SHA-256 of a canonicalized JSON value.

    This is the *evaluation* normalization hash, distinct from any
    production content hash.
    """
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_json_types(value: object, *, path: str = "$") -> None:
    """Recursively verify all values are strict JSON types.

    Rejects:
    - ``tuple``, ``set``, ``Decimal``, ``datetime``, custom objects
    - non-string dict keys
    - non-finite floats (NaN, Infinity, -Infinity)
    Any non-strict type raises ``CanonicalValueError`` (code
    ``EVAL_CANONICAL_VALUE_INVALID``) with the JSON ``path`` context.
    """
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        # bool is already handled above; int is fine
        return
    if isinstance(value, float):
        if not isfinite(value):
            raise CanonicalValueError(
                code="EVAL_CANONICAL_VALUE_INVALID",
                message=f"Non-finite float at {path}: {value!r}",
                field=path,
            )
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            _validate_json_types(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            child_path = f"{path}.{k}" if path != "$" else f"$.{k}"
            if not isinstance(k, str):
                raise CanonicalValueError(
                    code="EVAL_CANONICAL_VALUE_INVALID",
                    message=f"Non-string dict key at {path}: {type(k).__name__}",
                    field=path,
                )
            _validate_json_types(v, path=child_path)
        return
    # Reject any non-JSON-compatible type (tuple, set, Decimal, datetime, …)
    type_name = type(value).__name__
    raise CanonicalValueError(
        code="EVAL_CANONICAL_VALUE_INVALID",
        message=f"Non-JSON-compatible type at {path}: {type_name}",
        field=path,
    )


def _canonicalize(
    value: JsonValue,
    path: str,
    ignored: set[str],
    decimal: dict[str, DecimalPathRule],
) -> JsonValue:
    if path in ignored:
        return _SENTINEL  # type: ignore[return-value]

    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key in sorted(value):
            child_path = append_object_key(path, key)
            child = _canonicalize(value[key], child_path, ignored, decimal)
            if child is not _SENTINEL:  # type: ignore[comparison-overlap]
                result[key] = child
        return result

    if isinstance(value, list):
        result_list: list[JsonValue] = []
        for idx, item in enumerate(value):
            child = _canonicalize(item, f"{path}[{idx}]", ignored, decimal)
            if child is not _SENTINEL:  # type: ignore[comparison-overlap]
                result_list.append(child)
        return result_list

    if path in decimal:
        rule = decimal[path]
        quantized = quantize_decimal_value(value, rule.scale, rule=rule)
        return quantized

    return value


class _Sentinel:
    """Internal sentinel for deleted values."""


_SENTINEL = _Sentinel()
