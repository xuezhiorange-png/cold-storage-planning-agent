"""Deterministic JSON canonicalization for evaluation comparisons."""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from math import isfinite, isnan

from cold_storage.evaluation.errors import (
    DecimalPolicyError,
)
from cold_storage.evaluation.models import (
    DecimalMode,
    DecimalPathRule,
    IgnoredPathRule,
)

# JSON value: dict, list, str, int, float, bool, None
JsonValue = dict[str, "JsonValue"] | list["JsonValue"] | str | int | float | bool | None
JsonScalar = str | int | float | bool | None


def quantize_decimal_value(
    value: JsonScalar,
    scale: int,
) -> str:
    """Quantize a numeric value to a fixed-scale deterministic string.

    Args:
        value: The value to quantize (int, float, or numeric string).
        scale: Number of decimal places (0-20).

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
            # Empty string is not valid
            if not value:
                raise DecimalPolicyError(
                    code="EVAL_DECIMAL_VALUE_INVALID",
                    message="Cannot quantize empty string",
                    field="",
                )
            d = Decimal(value)
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

    # Quantize with explicit rounding
    quantized = d.quantize(Decimal(10) ** -scale, rounding=ROUND_HALF_EVEN)
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
        decimal={r.path: (r.scale, r.mode) for r in decimal_paths},
    )


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Serialize a canonicalized JSON value to deterministic bytes.

    Raises:
        TypeError: If value contains non-standard JSON types.
    """
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_canonical_json(value: JsonValue) -> str:
    """Compute the SHA-256 of a canonicalized JSON value.

    This is the *evaluation* normalization hash, distinct from any
    production content hash.
    """
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _canonicalize(
    value: JsonValue,
    path: str,
    ignored: set[str],
    decimal: dict[str, tuple[int, DecimalMode]],
) -> JsonValue:
    if path in ignored:
        return _SENTINEL  # type: ignore[return-value]  # sentinel checked by identity

    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key in sorted(value):
            child = _canonicalize(value[key], f"{path}.{key}", ignored, decimal)
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
        scale, mode = decimal[path]
        # Quantize to fixed-scale string (fail-closed for invalid values)
        quantized = quantize_decimal_value(value, scale)
        return quantized

    return value


class _Sentinel:
    """Internal sentinel for deleted values."""


_SENTINEL = _Sentinel()
