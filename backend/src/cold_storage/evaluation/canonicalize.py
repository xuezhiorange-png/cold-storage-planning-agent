"""Deterministic JSON canonicalization for evaluation comparisons."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from cold_storage.evaluation.models import (
    DecimalMode,
    DecimalPathRule,
    IgnoredPathRule,
)

# JSON value: dict, list, str, int, float, bool, None
JsonValue = dict[str, "JsonValue"] | list["JsonValue"] | str | int | float | bool | None


def canonicalize_json(
    value: JsonValue,
    *,
    ignored_paths: tuple[IgnoredPathRule, ...] = (),
    decimal_paths: tuple[DecimalPathRule, ...] = (),
) -> JsonValue:
    """Canonicalize a deserialized JSON value for deterministic comparison.

    The input is not mutated.  The output uses stable key ordering, removes
    ignored paths, and quantizes decimal-policy values.

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
    """Serialize a canonicalized JSON value to deterministic bytes."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
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
        if isinstance(value, bool):
            return value
        try:
            d = Decimal(str(value))
            quantized = d.quantize(Decimal(10) ** -scale)
            return float(quantized) if not scale else float(quantized)
        except (ValueError, TypeError):
            return value

    return value


class _Sentinel:
    """Internal sentinel for deleted values."""


_SENTINEL = _Sentinel()
