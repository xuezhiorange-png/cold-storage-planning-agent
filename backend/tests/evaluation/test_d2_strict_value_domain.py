"""D2 strict-JSON value-domain tests (TASK-011C V1).

These tests assert that the canonicalizer (D1) accepts only the
D2 strict-JSON value domain and rejects every value on the
rejected list:

  REJECTED = [NaN, Infinity, -Infinity, Decimal objects,
              datetime/date/time, UUID objects, bytes/bytearray,
              set/frozenset, tuple as implicit array, custom classes,
              non-string mapping keys, unsupported enums,
              implicit stringification]
"""

from __future__ import annotations

import datetime as _dt
import uuid as _uuid
from decimal import Decimal

import pytest

from cold_storage.evaluation.canonicalization import (
    UnsupportedJSONValueError,
    canonicalize_production_outputs,
)

# ── Allowed values (D2) ──────────────────────────────────────────────


def test_d2_null_accepted() -> None:
    assert canonicalize_production_outputs(None, excluded_paths=()) == "null"


def test_d2_boolean_true_accepted() -> None:
    assert canonicalize_production_outputs(True, excluded_paths=()) == "true"


def test_d2_boolean_false_accepted() -> None:
    assert canonicalize_production_outputs(False, excluded_paths=()) == "false"


def test_d2_integer_accepted() -> None:
    assert canonicalize_production_outputs(42, excluded_paths=()) == "42"
    assert canonicalize_production_outputs(-1, excluded_paths=()) == "-1"
    assert canonicalize_production_outputs(0, excluded_paths=()) == "0"


def test_d2_finite_float_accepted() -> None:
    assert canonicalize_production_outputs(1.5, excluded_paths=()) == "1.5"
    assert canonicalize_production_outputs(0.0, excluded_paths=()) == "0.0"
    assert canonicalize_production_outputs(-2.5, excluded_paths=()) == "-2.5"


def test_d2_string_accepted() -> None:
    assert canonicalize_production_outputs("hello", excluded_paths=()) == '"hello"'
    assert canonicalize_production_outputs("", excluded_paths=()) == '""'


def test_d2_array_of_allowed_values_accepted() -> None:
    out = canonicalize_production_outputs([1, "a", None, True, 1.5], excluded_paths=())
    assert out == '[1,"a",null,true,1.5]'


def test_d2_object_with_string_keys_accepted() -> None:
    out = canonicalize_production_outputs({"k": "v"}, excluded_paths=())
    assert out == '{"k":"v"}'


# ── Rejected values (D2) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_d2_non_finite_float_rejected(value: float) -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(value, excluded_paths=())


def test_d2_decimal_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(Decimal("123.45"), excluded_paths=())


def test_d2_decimal_in_nested_structure_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs({"k": Decimal("0.0")}, excluded_paths=())


def test_d2_datetime_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_dt.datetime(2024, 1, 1, 12, 0, 0), excluded_paths=())


def test_d2_date_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_dt.date(2024, 1, 1), excluded_paths=())


def test_d2_time_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_dt.time(12, 0), excluded_paths=())


def test_d2_timedelta_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_dt.timedelta(seconds=1), excluded_paths=())


def test_d2_uuid_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(_uuid.uuid4(), excluded_paths=())


def test_d2_bytes_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(b"abc", excluded_paths=())


def test_d2_bytearray_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(bytearray(b"abc"), excluded_paths=())


def test_d2_set_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs({1, 2}, excluded_paths=())


def test_d2_frozenset_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(frozenset([1, 2]), excluded_paths=())


def test_d2_tuple_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs((1, 2, 3), excluded_paths=())


def test_d2_non_string_dict_key_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs({1: "a"}, excluded_paths=())


def test_d2_unsupported_enum_rejected() -> None:
    import enum

    class Color(enum.Enum):
        RED = "red"

    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(Color.RED, excluded_paths=())


def test_d2_implicit_str_coercion_forbidden() -> None:
    """Custom objects must NOT be silently stringified."""

    class Custom:
        def __str__(self) -> str:
            return "secret"

    with pytest.raises(UnsupportedJSONValueError) as exc_info:
        canonicalize_production_outputs(Custom(), excluded_paths=())
    assert "secret" not in str(exc_info.value)


def test_d2_custom_class_rejected() -> None:
    class Custom:
        pass

    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(Custom(), excluded_paths=())


def test_d2_int_enum_rejected() -> None:
    """IntEnum is a subclass of int; the D2 contract forbids Enum
    acceptance even when the value is numeric."""

    import enum

    class Color(enum.IntEnum):
        RED = 1

    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(Color.RED, excluded_paths=())


def test_d2_exception_object_rejected() -> None:
    with pytest.raises(UnsupportedJSONValueError):
        canonicalize_production_outputs(ValueError("x"), excluded_paths=())
