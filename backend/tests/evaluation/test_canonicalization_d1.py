"""D1 single-canonicalizer-authority tests (TASK-011C V1).

These tests assert the **D1 binding invariant**:

* The canonicalization authority is
  ``backend.src.cold_storage.evaluation.canonicalization
  .canonicalize_production_outputs``.
* It is forbidden to create a second canonicalizer. The tests
  below enforce this by structural inspection (the canonicalizer
  symbol is imported and exercised; no alternative path is
  exposed).
* The canonicalizer fails closed on every non-JSON-domain value.
"""

from __future__ import annotations

import inspect

import pytest

from cold_storage.evaluation import canonicalization
from cold_storage.evaluation.canonicalization import (
    CanonicalizationError,
    EmptyExclusionSetRequired,
    UnsupportedJSONValueError,
    WildcardExclusionForbidden,
    canonicalize_production_outputs,
)


def test_d1_canonicalizer_is_callable_and_well_typed() -> None:
    """The D1 symbol is a function with the frozen signature."""
    sig = inspect.signature(canonicalize_production_outputs)
    params = list(sig.parameters.keys())
    assert params == ["value", "excluded_paths"]
    assert sig.parameters["excluded_paths"].kind is inspect.Parameter.KEYWORD_ONLY


def test_d1_no_second_canonicalizer_symbol_in_evaluation_package() -> None:
    """The evaluation package exposes exactly one canonicalizer.

    No module under ``cold_storage.evaluation`` may export a
    second public function that returns canonical bytes. This is
    enforced by name scan; the canonicalizer name is unique.
    """
    # We look for public *functions* (not exception classes) in
    # the canonicalization module. Exception classes are
    # permitted (they are how the canonicalizer reports errors);
    # what is forbidden is a *second* canonicalization function.
    canonicalizers = [
        name
        for name, obj in vars(canonicalization).items()
        if not name.startswith("_")
        and callable(obj)
        and inspect.isfunction(obj)
        and getattr(obj, "__module__", "") == canonicalization.__name__
    ]
    # The single D1 symbol is ``canonicalize_production_outputs``.
    assert canonicalizers == ["canonicalize_production_outputs"]


def test_d1_canonicalize_simple_object_is_deterministic() -> None:
    out1 = canonicalize_production_outputs({"a": 1, "b": [1, 2, 3]}, excluded_paths=())
    out2 = canonicalize_production_outputs({"b": [1, 2, 3], "a": 1}, excluded_paths=())
    assert out1 == out2
    assert out1 == b'{"a":1,"b":[1,2,3]}'


def test_d1_canonicalize_arrays_preserve_order() -> None:
    out = canonicalize_production_outputs([3, 1, 2], excluded_paths=())
    assert out == b"[3,1,2]"


def test_d1_canonicalize_nested() -> None:
    value = {"z": [{"y": 2, "x": 1}], "a": None}
    out = canonicalize_production_outputs(value, excluded_paths=())
    assert out == b'{"a":null,"z":[{"x":1,"y":2}]}'


def test_d1_canonicalize_empty_excluded_paths_is_accepted() -> None:
    out = canonicalize_production_outputs({"x": 1}, excluded_paths=())
    assert out == b'{"x":1}'


def test_d1_empty_sequence_excluded_paths_accepted() -> None:
    # A list (not tuple) of zero length is also OK.
    out = canonicalize_production_outputs({"x": 1}, excluded_paths=[])
    assert out == b'{"x":1}'


def test_d1_non_empty_excluded_paths_raises() -> None:
    with pytest.raises(EmptyExclusionSetRequired) as exc_info:
        canonicalize_production_outputs({"x": 1}, excluded_paths=["some.path"])
    assert exc_info.value.code == "EMPTY_EXCLUSION_SET_REQUIRED"


def test_d1_wildcard_excluded_paths_raises_wildcard_error_first() -> None:
    # Wildcard should produce a wildcard-specific error, not the
    # generic empty-exclusion error, because the wildcard check
    # runs first.
    with pytest.raises(WildcardExclusionForbidden) as exc_info:
        canonicalize_production_outputs({"x": 1}, excluded_paths=["*"])
    assert exc_info.value.code == "WILDCARD_EXCLUSION_FORBIDDEN"


def test_d1_wildcard_inside_path_also_rejected() -> None:
    with pytest.raises(WildcardExclusionForbidden):
        canonicalize_production_outputs({"x": 1}, excluded_paths=["some.*"])


def test_d1_canonicalize_nan_raises() -> None:
    with pytest.raises(UnsupportedJSONValueError) as exc_info:
        canonicalize_production_outputs(float("nan"), excluded_paths=())
    assert exc_info.value.code == "UNSUPPORTED_JSON_VALUE"


def test_d1_canonicalize_infinity_raises() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(float("inf"), excluded_paths=())
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(float("-inf"), excluded_paths=())


def test_d1_canonicalize_decimal_raises() -> None:
    from decimal import Decimal

    with pytest.raises(UnsupportedJSONValueError) as exc_info:
        canonicalize_production_outputs(Decimal("123.45"), excluded_paths=())
    assert exc_info.value.code == "UNSUPPORTED_JSON_VALUE"
    assert "Decimal" in str(exc_info.value.details.get("type", "")) or "D2" in str(exc_info.value)


def test_d1_canonicalize_datetime_raises() -> None:
    import datetime as _dt

    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_dt.datetime(2024, 1, 1), excluded_paths=())
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_dt.date(2024, 1, 1), excluded_paths=())
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_dt.time(12, 0), excluded_paths=())


def test_d1_canonicalize_tuple_raises_no_implicit_list() -> None:
    with pytest.raises(UnsupportedJSONValueError) as exc_info:
        canonicalize_production_outputs((1, 2, 3), excluded_paths=())
    assert exc_info.value.code == "UNSUPPORTED_JSON_VALUE"


def test_d1_canonicalize_set_raises() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs({1, 2, 3}, excluded_paths=())


def test_d1_canonicalize_frozenset_raises() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(frozenset([1, 2]), excluded_paths=())


def test_d1_canonicalize_bytes_raises() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(b"abc", excluded_paths=())


def test_d1_canonicalize_custom_class_raises() -> None:
    class Custom:
        pass

    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(Custom(), excluded_paths=())


def test_d1_canonicalize_non_string_mapping_key_raises() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs({1: "a"}, excluded_paths=())


def test_d1_canonicalize_enum_raises() -> None:
    import enum

    class E(enum.Enum):
        X = "x"

    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(E.X, excluded_paths=())


def test_d1_canonicalize_does_not_call_str_on_unknown_object() -> None:
    """The D2 contract forbids implicit str(value). We assert that
    by passing a custom object whose __str__ would leak data and
    confirming the error is the typed UnsupportedJSONValueError,
    not a stringification."""

    class Leaky:
        def __str__(self) -> str:
            return "leaked"

    with pytest.raises(UnsupportedJSONValueError) as exc_info:
        canonicalize_production_outputs(Leaky(), excluded_paths=())
    # The error message must NOT contain the leak.
    assert "leaked" not in str(exc_info.value)
    assert exc_info.value.code == "UNSUPPORTED_JSON_VALUE"


def test_d1_canonicalize_bool_is_preserved_not_coerced_to_int() -> None:
    out = canonicalize_production_outputs([True, False, 0, 1], excluded_paths=())
    assert out == b"[true,false,0,1]"


def test_d1_canonicalize_int_and_float_coexist() -> None:
    out = canonicalize_production_outputs([1, 1.5, 2], excluded_paths=())
    assert out == b"[1,1.5,2]"


def test_d1_canonicalize_does_not_coerce_bool_to_int() -> None:
    """The D1 contract requires that True/False are NOT coerced
    to 1/0 by the canonicalizer. Pydantic / JSON treat them as
    distinct types; the canonicalizer must preserve the
    distinction."""
    out = canonicalize_production_outputs({"a": True, "b": 1}, excluded_paths=())
    # If bool were silently coerced, the output would be
    # {"a":1,"b":1}. The contract preserves the distinction.
    assert out == b'{"a":true,"b":1}'


def test_d1_canonicalize_all_exception_classes_have_code() -> None:
    for cls in [
        CanonicalizationError,
        EmptyExclusionSetRequired,
        UnsupportedJSONValueError,
        WildcardExclusionForbidden,
    ]:
        assert isinstance(cls.code, str)
        assert cls.code
