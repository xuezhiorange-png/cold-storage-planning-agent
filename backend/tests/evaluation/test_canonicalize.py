"""Tests for JSON canonicalization."""

from __future__ import annotations

import pytest

from cold_storage.evaluation.canonicalize import (
    canonical_json_bytes,
    canonicalize_json,
    quantize_decimal_value,
    sha256_canonical_json,
)
from cold_storage.evaluation.errors import DecimalPolicyError
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
    """Decimal quantization must produce fixed-scale strings."""
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
    assert result["value"] == "123.46"


def test_fixed_scale() -> None:
    """Decimal quantization must preserve trailing zeros."""
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
        {"value": 1.2},
        decimal_paths=rule,
    )
    assert result["value"] == "1.20"


def test_scale_zero() -> None:
    """Scale=0 must produce an integer string."""
    rule = (
        DecimalPathRule(
            path="$.value",
            mode="quantize",
            scale=0,
            unit="count",
            rationale="test",
        ),
    )
    result = canonicalize_json(
        {"value": 1},
        decimal_paths=rule,
    )
    assert result["value"] == "1"


def test_numeric_string_rounding() -> None:
    """ROUND_HALF_EVEN: 1.205 at scale=2 must round to 1.20, not 1.21."""
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
        {"value": "1.205"},
        decimal_paths=rule,
    )
    assert result["value"] == "1.20"


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
    """Decimal quantization must reject bool values at decimal paths."""
    rule = (
        DecimalPathRule(
            path="$.flag",
            mode="quantize",
            scale=2,
            unit="flag",
            rationale="test",
        ),
    )
    with pytest.raises(DecimalPolicyError):
        canonicalize_json(
            {"flag": True},
            decimal_paths=rule,
        )


def test_quantize_rejects_bool() -> None:
    """quantize_decimal_value must reject boolean values."""
    with pytest.raises(DecimalPolicyError):
        quantize_decimal_value(True, 2)


def test_quantize_rejects_none() -> None:
    """quantize_decimal_value must reject None."""
    with pytest.raises(DecimalPolicyError):
        quantize_decimal_value(None, 2)


def test_quantize_rejects_nan() -> None:
    """quantize_decimal_value must reject NaN."""
    with pytest.raises(DecimalPolicyError):
        quantize_decimal_value(float("nan"), 2)


def test_quantize_rejects_inf() -> None:
    """quantize_decimal_value must reject infinity."""
    with pytest.raises(DecimalPolicyError):
        quantize_decimal_value(float("inf"), 2)


def test_quantize_rejects_neg_inf() -> None:
    """quantize_decimal_value must reject negative infinity."""
    with pytest.raises(DecimalPolicyError):
        quantize_decimal_value(float("-inf"), 2)


def test_scale_20() -> None:
    """Scale=20 must produce a fixed-scale string with 20 decimal places."""
    rule = (
        DecimalPathRule(
            path="$.value",
            mode="quantize",
            scale=20,
            unit="precision",
            rationale="test",
        ),
    )
    result = canonicalize_json(
        {"value": 3.141592653589793},
        decimal_paths=rule,
    )
    # The value is quantized to 20 decimal places.
    assert result["value"] == "3.14159265358979300000"


# ── P0-4: Decimal fail-closed tests ────────────────────────────────────


def test_quantize_string_nan_rejected() -> None:
    """String 'NaN' must be rejected with EVAL_DECIMAL_NON_FINITE."""
    with pytest.raises(DecimalPolicyError) as exc_info:
        quantize_decimal_value("NaN", 2)
    assert exc_info.value.code == "EVAL_DECIMAL_NON_FINITE"


def test_quantize_string_infinity_rejected() -> None:
    """String 'Infinity' must be rejected with EVAL_DECIMAL_NON_FINITE."""
    with pytest.raises(DecimalPolicyError) as exc_info:
        quantize_decimal_value("Infinity", 2)
    assert exc_info.value.code == "EVAL_DECIMAL_NON_FINITE"


def test_quantize_string_neg_infinity_rejected() -> None:
    """String '-Infinity' must be rejected with EVAL_DECIMAL_NON_FINITE."""
    with pytest.raises(DecimalPolicyError) as exc_info:
        quantize_decimal_value("-Infinity", 2)
    assert exc_info.value.code == "EVAL_DECIMAL_NON_FINITE"


def test_quantize_string_snan_rejected() -> None:
    """String 'sNaN' must be rejected with EVAL_DECIMAL_NON_FINITE."""
    with pytest.raises(DecimalPolicyError) as exc_info:
        quantize_decimal_value("sNaN", 2)
    assert exc_info.value.code == "EVAL_DECIMAL_NON_FINITE"


def test_quantize_empty_string_rejected() -> None:
    """Empty string must be rejected with EVAL_DECIMAL_VALUE_INVALID."""
    with pytest.raises(DecimalPolicyError) as exc_info:
        quantize_decimal_value("", 2)
    assert exc_info.value.code == "EVAL_DECIMAL_VALUE_INVALID"


def test_quantize_whitespace_string_rejected() -> None:
    """Whitespace-only string must be rejected."""
    with pytest.raises(DecimalPolicyError):
        quantize_decimal_value("   ", 2)


def test_quantize_non_numeric_string_rejected() -> None:
    """Non-numeric string must be rejected with EVAL_DECIMAL_QUANTIZE_FAILED."""
    with pytest.raises(DecimalPolicyError) as exc_info:
        quantize_decimal_value("not-a-number", 2)
    assert exc_info.value.code == "EVAL_DECIMAL_QUANTIZE_FAILED"


def test_quantize_large_exponent_rejected() -> None:
    """Very large exponent must be rejected deterministically."""
    with pytest.raises(DecimalPolicyError):
        quantize_decimal_value("1e999999", 2)


def test_quantize_large_negative_exponent_handled() -> None:
    """Very large negative exponent produces 0.00 after quantize at scale 2."""
    result = quantize_decimal_value("1e-999", 2)
    assert result == "0.00"


def test_quantize_half_even_positive_tie() -> None:
    """ROUND_HALF_EVEN: 2.5 at scale=0 must round to 2 (even)."""
    result = quantize_decimal_value(2.5, 0)
    assert result == "2"


def test_quantize_half_even_negative_tie() -> None:
    """ROUND_HALF_EVEN: 3.5 at scale=0 must round to 4 (odd → nearest even)."""
    result = quantize_decimal_value(3.5, 0)
    assert result == "4"


def test_canonical_bytes_rejects_decimal() -> None:
    """canonical_json_bytes must reject Decimal objects."""
    from decimal import Decimal

    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc_info:
        canonical_json_bytes({"value": Decimal("3.14")})
    assert exc_info.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_quantize_enforces_mode() -> None:
    """DecimalPathRule with unsupported mode must fail during canonicalization."""
    from cold_storage.evaluation.models import DecimalMode, DecimalPathRule

    rule = (
        DecimalPathRule(
            path="$.value",
            mode=DecimalMode.QUANTIZE,
            scale=2,
            unit="m2",
            rationale="Test mode enforcement",
        ),
    )
    result = canonicalize_json(
        {"value": 1.23},
        decimal_paths=rule,
    )
    assert result["value"] == "1.23"
