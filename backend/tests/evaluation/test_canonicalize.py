"""Tests for JSON canonicalization."""

from __future__ import annotations

from cold_storage.evaluation.canonicalize import (
    canonical_json_bytes,
    canonicalize_json,
    sha256_canonical_json,
)
from cold_storage.evaluation.models import (
    DecimalPathRule,
    IgnoredPathRule,
)


def test_key_ordering_stable() -> None:
    """Canonicalized dict keys must be sorted."""
    result = canonicalize_json({"z": 1, "a": 2, "m": 3})
    assert list(result.keys()) == ["a", "m", "z"]


def test_input_not_mutated() -> None:
    """Original input must not be modified."""
    original = {"b": 1, "a": 2}
    canonicalize_json(original)
    assert list(original.keys()) == ["b", "a"]


def test_unicode_serialization_stable() -> None:
    """Unicode must be preserved in output."""
    data = {"name": "蓝莓"}
    canonical = canonicalize_json(data)
    canonical_json_bytes(canonical)
    # Re-serialize and check
    serialized = canonical_json_bytes(canonical)
    assert "蓝莓".encode() in serialized


def test_decimal_quantize() -> None:
    """Decimal quantization must produce exact values."""
    rule = (
        DecimalPathRule(
            path="$.value",
            mode="quantize",
            scale=2,
            unit="m2",
            rationale="test",
        ),
    )
    result = canonicalize_json(
        {"value": 123.456},
        decimal_paths=rule,
    )
    assert result["value"] == 123.46


def test_float_bool_not_confused() -> None:
    """Bool must not be confused with int."""
    result = canonicalize_json({"flag": True, "count": 1})
    assert result["flag"] is True
    assert result["count"] == 1


def test_ignored_exact_path_removed() -> None:
    """Exact ignored path must be removed from output."""
    rule = (IgnoredPathRule(path="$.metadata", reason="test"),)
    result = canonicalize_json(
        {"metadata": {"ts": "2024-01-01"}, "value": 42},
        ignored_paths=rule,
    )
    assert "metadata" not in result
    assert result["value"] == 42


def test_nested_ignored_path() -> None:
    """Nested ignored path must be removed."""
    rule = (IgnoredPathRule(path="$.data.timestamp", reason="test"),)
    result = canonicalize_json(
        {"data": {"timestamp": "now", "value": 99}},
        ignored_paths=rule,
    )
    assert "data" in result
    assert "timestamp" not in result["data"]
    assert result["data"]["value"] == 99


def test_array_order_preserved() -> None:
    """Array order must be preserved by default."""
    result = canonicalize_json([3, 1, 2])
    assert result == [3, 1, 2]


def test_hash_repeatable() -> None:
    """SHA-256 of same data must be identical."""
    data = {"a": 1, "b": 2}
    h1 = sha256_canonical_json(data)
    h2 = sha256_canonical_json(data)
    assert h1 == h2


def test_hash_differs_when_value_changes() -> None:
    """Different data must produce different hashes."""
    h1 = sha256_canonical_json({"a": 1})
    h2 = sha256_canonical_json({"a": 2})
    assert h1 != h2


def test_decimal_not_applied_to_bool() -> None:
    """Decimal quantization must not alter bool values."""
    rule = (
        DecimalPathRule(
            path="$.flag",
            mode="quantize",
            scale=2,
            unit="flag",
            rationale="test",
        ),
    )
    result = canonicalize_json(
        {"flag": True},
        decimal_paths=rule,
    )
    assert result["flag"] is True
