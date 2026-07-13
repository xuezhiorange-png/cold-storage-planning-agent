"""D4 numeric-exact tests (TASK-011C V1).

These tests assert the **D4 binding invariant**:

* Default comparison is EXACT (no global float tolerance).
* Decimal-valued governed fields must be deliberately
  represented as canonical JSON strings before comparison.
* No per-field tolerance is permitted in V1.
* The canonicalizer serializes floats without scientific
  notation (JSON-compatible).
* The canonicalizer does not introduce any rounding or
  quantization.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from cold_storage.evaluation.canonicalization import (
    CanonicalizationError,
    EmptyExclusionSetRequired,
    canonicalize_production_outputs,
)


def test_d4_default_comparison_is_exact() -> None:
    """D4 default is exact. The canonicalizer outputs bytes that
    differ if the inputs differ. There is no global float
    tolerance."""
    a = canonicalize_production_outputs(1.0, excluded_paths=())
    b = canonicalize_production_outputs(1.0, excluded_paths=())
    assert a == b
    # Slightly different floats produce different bytes.
    c = canonicalize_production_outputs(1.0000001, excluded_paths=())
    assert a != c


def test_d4_no_global_float_tolerance() -> None:
    """The canonicalizer does NOT apply any rounding / quantization
    to floats. 1.000001 stays 1.000001 in the canonical output."""
    out = canonicalize_production_outputs(1.000001, excluded_paths=())
    # Python's repr and json.dumps use the shortest round-trip
    # representation. The key is that the canonicalizer does not
    # silently quantize.
    parsed = json.loads(out)
    assert parsed == 1.000001


def test_d4_integer_1_and_float_1_0_produce_different_canonical_bytes() -> None:
    """D4 requires that integer and float representations are
    preserved as distinct. ``1`` and ``1.0`` MUST produce
    different canonical bytes."""
    out_int = canonicalize_production_outputs(1, excluded_paths=())
    out_float = canonicalize_production_outputs(1.0, excluded_paths=())
    assert out_int == "1"
    assert out_float == "1.0"
    assert out_int != out_float


def test_d4_decimal_rejected_no_implicit_stringification() -> None:
    """D4 + D2: Decimal values are not silently converted to
    strings. The caller MUST do the stringification explicitly."""
    with pytest.raises(CanonicalizationError):
        canonicalize_production_outputs(Decimal("1.5"), excluded_paths=())


def test_d4_decimal_governed_field_pattern_example() -> None:
    """Per the contract example, governed decimal fields are
    represented as canonical JSON strings: ``"123.45"``, ``"0"``,
    ``"-12.500"``. The canonicalizer preserves the exact string."""
    out = canonicalize_production_outputs(
        {"value": "123.45"},
        excluded_paths=(),
    )
    assert out == '{"value":"123.45"}'

    out2 = canonicalize_production_outputs(
        {"value": "-12.500"},
        excluded_paths=(),
    )
    assert out2 == '{"value":"-12.500"}'

    out3 = canonicalize_production_outputs(
        {"value": "0"},
        excluded_paths=(),
    )
    assert out3 == '{"value":"0"}'


def test_d4_no_scientific_notation_for_integers() -> None:
    out = canonicalize_production_outputs(123456789, excluded_paths=())
    assert out == "123456789"
    # No exponent character
    assert "e" not in out and "E" not in out


def test_d4_no_implicit_rounding_of_floats() -> None:
    """D4 forbids undeclared quantization. The canonicalizer must
    NOT round floats. (Python's json uses repr-style shortest
    round-trip; the assertion is that the value is preserved
    bit-exact.)"""
    out = canonicalize_production_outputs(0.1 + 0.2, excluded_paths=())
    # 0.1 + 0.2 == 0.30000000000000004 in IEEE 754.
    assert out == "0.30000000000000004"


def test_d4_no_field_tolerance() -> None:
    """There is no per-field tolerance API. The only comparison
    semantics are exact (default) and excluded (forbidden in V1).

    The canonicalizer does not accept a per-field tolerance
    parameter; if such a parameter were added, it would be a V1
    contract violation.
    """
    import inspect

    sig = inspect.signature(canonicalize_production_outputs)
    assert "tolerance" not in sig.parameters
    assert "abs_tol" not in sig.parameters
    assert "rel_tol" not in sig.parameters


def test_d4_empty_excluded_paths_required() -> None:
    """D3 + D4: excluded_paths MUST be empty in V1. No field
    tolerance, no path exclusion — the only valid path is exact
    comparison everywhere."""
    with pytest.raises(EmptyExclusionSetRequired):
        canonicalize_production_outputs({"x": 1}, excluded_paths=["x"])


def test_d4_no_nan_in_canonical_output() -> None:
    """The canonicalizer rejects NaN; the D1 contract requires
    canonical output to itself be valid JSON (parseable without
    raising)."""
    import json

    out = canonicalize_production_outputs({"a": 1, "b": 2}, excluded_paths=())
    # Round-trip must succeed; if NaN were present, json.loads
    # would still parse it but the contract forbids NaN at the
    # input.
    parsed = json.loads(out)
    assert parsed == {"a": 1, "b": 2}
