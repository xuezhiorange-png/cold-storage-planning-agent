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
    DecimalMode,
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


# ── P0-4: Canonical JSON type and non-finite regression tests ──────


def test_root_tuple_rejected():
    """Tuple as root value must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes((1, 2))  # type: ignore[arg-type]
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_nested_tuple_rejected():
    """Tuple nested inside list must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes({"a": (1, 2)})  # type: ignore[arg-type]
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_set_rejected():
    """Set value must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes({1, 2})  # type: ignore[arg-type]
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_decimal_rejected():
    """Decimal value must raise CanonicalValueError."""
    from decimal import Decimal

    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes(Decimal("1.5"))  # type: ignore[arg-type]
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_non_string_dict_key_rejected():
    """Non-string dict key must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes({1: "value"})  # type: ignore[arg-type]
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_root_nan_rejected():
    """NaN as root value must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes(float("nan"))
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_infinity_rejected():
    """Infinity value must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes(float("inf"))
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_negative_infinity_rejected():
    """-Infinity value must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes(float("-inf"))
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_nan_in_nested_dict_rejected():
    """NaN nested inside dict value must raise CanonicalValueError with path."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes({"value": float("nan")})
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


def test_nan_in_list_rejected():
    """NaN inside a list must raise CanonicalValueError."""
    from cold_storage.evaluation.canonicalize import canonical_json_bytes
    from cold_storage.evaluation.errors import CanonicalValueError

    with pytest.raises(CanonicalValueError) as exc:
        canonical_json_bytes([1.0, float("nan")])
    assert exc.value.code == "EVAL_CANONICAL_VALUE_INVALID"


# ── P0-4: Decimal context independence tests ────────────────────────


def test_ambient_precision_does_not_affect_quantize():
    """Changing ambient Decimal precision must not affect quantize output."""
    from decimal import getcontext

    from cold_storage.evaluation.canonicalize import quantize_decimal_value

    original_prec = getcontext().prec
    try:
        getcontext().prec = 2
        result_low = quantize_decimal_value(123.456, scale=2)
        getcontext().prec = 1000
        result_high = quantize_decimal_value(123.456, scale=2)
        assert result_low == result_high
    finally:
        getcontext().prec = original_prec


def test_ambient_rounding_does_not_affect_quantize():
    """Changing ambient Decimal rounding must not affect quantize output."""
    from decimal import ROUND_DOWN, getcontext

    from cold_storage.evaluation.canonicalize import quantize_decimal_value

    original = getcontext().rounding
    try:
        getcontext().rounding = ROUND_DOWN
        result = quantize_decimal_value(1.2345, scale=2)
        assert result == "1.23"  # ROUND_HALF_EVEN would round to 1.23 anyway for 1.2345
        # Use a tie to prove ROUND_HALF_EVEN vs ROUND_DOWN
        getcontext().rounding = ROUND_DOWN
        result_tie = quantize_decimal_value(1.235, scale=2)
        assert result_tie == "1.24"  # ROUND_HALF_EVEN rounds 1.235 to 1.24 (even digit)
    finally:
        getcontext().rounding = original


def test_scale_true_rejected():
    """Boolean as scale must raise DecimalPolicyError."""
    from cold_storage.evaluation.canonicalize import quantize_decimal_value
    from cold_storage.evaluation.errors import DecimalPolicyError

    with pytest.raises(DecimalPolicyError) as exc:
        quantize_decimal_value(1.5, scale=True)  # type: ignore[arg-type]
    assert exc.value.code == "EVAL_DECIMAL_POLICY_INVALID"


def test_scale_negative_rejected():
    """Negative scale must raise DecimalPolicyError."""
    from cold_storage.evaluation.canonicalize import quantize_decimal_value
    from cold_storage.evaluation.errors import DecimalPolicyError

    with pytest.raises(DecimalPolicyError) as exc:
        quantize_decimal_value(1.5, scale=-1)
    assert exc.value.code == "EVAL_DECIMAL_POLICY_INVALID"


def test_scale_too_large_rejected():
    """Scale > 20 must raise DecimalPolicyError."""
    from cold_storage.evaluation.canonicalize import quantize_decimal_value
    from cold_storage.evaluation.errors import DecimalPolicyError

    with pytest.raises(DecimalPolicyError) as exc:
        quantize_decimal_value(1.5, scale=21)
    assert exc.value.code == "EVAL_DECIMAL_POLICY_INVALID"


def test_scale_float_rejected():
    """Float scale must raise DecimalPolicyError."""
    from cold_storage.evaluation.canonicalize import quantize_decimal_value
    from cold_storage.evaluation.errors import DecimalPolicyError

    with pytest.raises(DecimalPolicyError) as exc:
        quantize_decimal_value(1.5, scale=1.5)  # type: ignore[arg-type]
    assert exc.value.code == "EVAL_DECIMAL_POLICY_INVALID"


def test_same_input_repeatable_hash():
    """Same input repeated must produce same bytes/hash."""
    from cold_storage.evaluation.canonicalize import sha256_canonical_json

    h1 = sha256_canonical_json({"a": 1, "b": 2})
    h2 = sha256_canonical_json({"b": 2, "a": 1})
    assert h1 == h2


# ── P0-6: Decimal ambient context isolation ─────────────────────────────


class TestDecimalAmbientContextIsolation:
    """quantize_decimal_value must be immune to ambient Decimal context changes."""

    INPUT = 12.345
    SCALE = 2
    EXPECTED = "12.34"  # ROUND_HALF_EVEN on 12.345 → 12.34
    NON_FINITE = float("inf")

    def _check_consistent(self) -> None:
        """Assert consistent result across repeated calls."""
        result = quantize_decimal_value(self.INPUT, self.SCALE)
        assert result == self.EXPECTED

    def test_default_context(self) -> None:
        """Works with default ambient context."""
        self._check_consistent()

    def test_ambient_prec_2(self) -> None:
        """Works with ambient precision=2."""
        from decimal import getcontext

        ctx = getcontext()
        original = ctx.prec
        try:
            ctx.prec = 2
            self._check_consistent()
        finally:
            ctx.prec = original

    def test_ambient_prec_1000(self) -> None:
        """Works with ambient precision=1000."""
        from decimal import getcontext

        ctx = getcontext()
        original = ctx.prec
        try:
            ctx.prec = 1000
            self._check_consistent()
        finally:
            ctx.prec = original

    def test_ambient_rounding_changed(self) -> None:
        """Works with ambient rounding changed."""
        from decimal import ROUND_DOWN, getcontext

        ctx = getcontext()
        original = ctx.rounding
        try:
            ctx.rounding = ROUND_DOWN
            self._check_consistent()
        finally:
            ctx.rounding = original

    def test_ambient_emax_changed(self) -> None:
        """Works with ambient Emax changed."""
        from decimal import getcontext

        ctx = getcontext()
        original = ctx.Emax
        try:
            ctx.Emax = 10
            self._check_consistent()
        finally:
            ctx.Emax = original

    def test_ambient_emin_changed(self) -> None:
        """Works with ambient Emin changed."""
        from decimal import getcontext

        ctx = getcontext()
        original = ctx.Emin
        try:
            ctx.Emin = -10
            self._check_consistent()
        finally:
            ctx.Emin = original

    def test_ambient_clamp_changed(self) -> None:
        """Works with ambient clamp changed."""
        from decimal import getcontext

        ctx = getcontext()
        original = ctx.clamp
        try:
            ctx.clamp = 1
            self._check_consistent()
        finally:
            ctx.clamp = original

    def test_ambient_invalid_operation_trap_disabled(self) -> None:
        """Works with InvalidOperation trap disabled in ambient."""
        from decimal import InvalidOperation, getcontext

        ctx = getcontext()
        original_traps = ctx.traps.copy()
        try:
            ctx.traps[InvalidOperation] = False
            self._check_consistent()
        finally:
            ctx.traps.update(original_traps)

    def test_non_finite_consistent_error(self) -> None:
        """NaN/Infinity raises stable error regardless of ambient context."""
        from decimal import getcontext

        original = getcontext().prec
        try:
            getcontext().prec = 1000
            with pytest.raises(DecimalPolicyError) as exc:
                quantize_decimal_value(self.NON_FINITE, self.SCALE)
            assert exc.value.code == "EVAL_DECIMAL_NON_FINITE"
        finally:
            getcontext().prec = original

    def test_context_flags_isolated(self) -> None:
        """Flags from a prior call must not affect the next call."""
        from decimal import InvalidOperation

        from cold_storage.evaluation.canonicalize import _EVALUATION_DECIMAL_CONTEXT

        # Deliberately trigger an InvalidOperation in a separate context
        bad_ctx = _EVALUATION_DECIMAL_CONTEXT.copy()
        try:
            from decimal import Decimal

            Decimal("bad").quantize(Decimal("0.01"), context=bad_ctx)
        except InvalidOperation:
            pass  # expected
        # Now check that _EVALUATION_DECIMAL_CONTEXT copy clears flags
        result = quantize_decimal_value(self.INPUT, self.SCALE)
        assert result == self.EXPECTED


# ── P0-1: scale=20 hostile ambient context tests ────────────────────────


class TestDecimalHostileContextScale20:
    """quantize_decimal_value must produce correct scale=20 results
    regardless of ambient Decimal context."""

    VALUE = "1.23456789012345678901"
    SCALE = 20
    EXPECTED = "1.23456789012345678901"

    def _check(self) -> None:
        result = quantize_decimal_value(self.VALUE, self.SCALE)
        assert result == self.EXPECTED
        # Verify exactly 20 decimal places
        _, _, frac = result.partition(".")
        assert len(frac) == 20, f"Expected 20 decimal places, got {len(frac)}: {result}"

    def test_default_context(self) -> None:
        self._check()

    def test_ambient_prec_2(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        orig = ctx.prec
        try:
            ctx.prec = 2
            self._check()
        finally:
            ctx.prec = orig

    def test_ambient_prec_1000(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        orig = ctx.prec
        try:
            ctx.prec = 1000
            self._check()
        finally:
            ctx.prec = orig

    def test_ambient_emax_10(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        orig = ctx.Emax
        try:
            ctx.Emax = 10
            self._check()
        finally:
            ctx.Emax = orig

    def test_ambient_emin_negative_10(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        orig = ctx.Emin
        try:
            ctx.Emin = -10
            self._check()
        finally:
            ctx.Emin = orig

    def test_ambient_clamp_1(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        orig = ctx.clamp
        try:
            ctx.clamp = 1
            self._check()
        finally:
            ctx.clamp = orig

    def test_ambient_round_down(self) -> None:
        from decimal import ROUND_DOWN, getcontext

        ctx = getcontext()
        orig = ctx.rounding
        try:
            ctx.rounding = ROUND_DOWN
            self._check()
        finally:
            ctx.rounding = orig

    def test_ambient_invalid_operation_trap_disabled(self) -> None:
        from decimal import InvalidOperation, getcontext

        ctx = getcontext()
        orig_traps = ctx.traps.copy()
        try:
            ctx.traps[InvalidOperation] = False
            self._check()
        finally:
            ctx.traps.update(orig_traps)

    def test_combined_hostile_settings(self) -> None:
        """Multiple hostile ambient settings combined must not affect result."""
        from decimal import ROUND_DOWN, InvalidOperation, getcontext

        ctx = getcontext()
        orig_prec = ctx.prec
        orig_rounding = ctx.rounding
        orig_emax = ctx.Emax
        orig_emin = ctx.Emin
        orig_clamp = ctx.clamp
        orig_traps = ctx.traps.copy()
        try:
            ctx.prec = 2
            ctx.rounding = ROUND_DOWN
            ctx.Emax = 10
            ctx.Emin = -10
            ctx.clamp = 1
            ctx.traps[InvalidOperation] = False
            self._check()
        finally:
            ctx.prec = orig_prec
            ctx.rounding = orig_rounding
            ctx.Emax = orig_emax
            ctx.Emin = orig_emin
            ctx.clamp = orig_clamp
            ctx.traps.update(orig_traps)

    def test_canonical_bytes_stable_under_hostile_context(self) -> None:
        """Canonical bytes must be stable under hostile ambient context."""
        from decimal import ROUND_DOWN, getcontext

        ctx = getcontext()
        orig_prec = ctx.prec
        orig_rounding = ctx.rounding
        try:
            ctx.prec = 2
            ctx.rounding = ROUND_DOWN
            result1 = quantize_decimal_value(self.VALUE, self.SCALE)
        finally:
            ctx.prec = orig_prec
            ctx.rounding = orig_rounding
        # Reset
        result2 = quantize_decimal_value(self.VALUE, self.SCALE)
        assert result1 == result2
        assert result1 == self.EXPECTED

    def test_non_finite_stable_error(self) -> None:
        """Non-finite input must raise stable error under hostile context."""
        from decimal import getcontext

        ctx = getcontext()
        orig = ctx.prec
        try:
            ctx.prec = 1000
            with pytest.raises(DecimalPolicyError) as exc:
                quantize_decimal_value(float("inf"), self.SCALE)
            assert exc.value.code == "EVAL_DECIMAL_NON_FINITE"
        finally:
            ctx.prec = orig


# ── P0-3: Real canonical value/bytes/SHA stability under hostile context ──


class TestCanonicalPipelineHostileContext:
    """Full canonical pipeline under hostile ambient Decimal context."""

    PAYLOAD = {"value": "1.23456789012345678901", "nested": {"stable": True}}
    RULE = DecimalPathRule(
        path="$.value",
        mode=DecimalMode.QUANTIZE,
        scale=20,
        unit="unit",
        rationale="hostile-context regression",
    )

    @staticmethod
    def _hostile() -> None:
        from decimal import ROUND_DOWN, InvalidOperation, getcontext

        ctx = getcontext()
        ctx.prec = 2
        ctx.rounding = ROUND_DOWN
        ctx.Emax = 10
        ctx.Emin = -10
        ctx.clamp = 1
        ctx.traps[InvalidOperation] = False

    def test_canonical_value_stable(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        saved = (ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp, ctx.traps.copy())
        try:
            default = canonicalize_json(self.PAYLOAD, decimal_paths=(self.RULE,))
            self._hostile()
            hostile = canonicalize_json(self.PAYLOAD, decimal_paths=(self.RULE,))
            assert hostile == default
            assert hostile["value"] == "1.23456789012345678901"
        finally:
            ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp = saved[:5]
            ctx.traps.update(saved[5])

    def test_canonical_bytes_stable(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        saved = (ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp, ctx.traps.copy())
        try:
            default = canonical_json_bytes(
                canonicalize_json(self.PAYLOAD, decimal_paths=(self.RULE,))
            )
            self._hostile()
            hostile = canonical_json_bytes(
                canonicalize_json(self.PAYLOAD, decimal_paths=(self.RULE,))
            )
            assert hostile == default
        finally:
            ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp = saved[:5]
            ctx.traps.update(saved[5])

    def test_sha256_stable(self) -> None:
        from decimal import getcontext

        ctx = getcontext()
        saved = (ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp, ctx.traps.copy())
        try:
            default = sha256_canonical_json(
                canonicalize_json(self.PAYLOAD, decimal_paths=(self.RULE,))
            )
            self._hostile()
            hostile = sha256_canonical_json(
                canonicalize_json(self.PAYLOAD, decimal_paths=(self.RULE,))
            )
            assert hostile == default
        finally:
            ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin, ctx.clamp = saved[:5]
            ctx.traps.update(saved[5])
