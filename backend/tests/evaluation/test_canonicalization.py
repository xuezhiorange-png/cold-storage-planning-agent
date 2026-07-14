"""Generic canonicalization tests (TASK-011C V1 — D1).

These tests cover the canonicalizer's general behavior:

* Determinism (same input → same output).
* Key sorting.
* Array order preservation.
* UTF-8 byte output (real ``bytes``, not ``str``).
* Strict-JSON accept list (D2).
* SHA-256 of the canonical bytes is deterministic (P0-2).
"""

from __future__ import annotations

import hashlib
import json

from cold_storage.evaluation.canonicalization import (
    canonicalize_production_outputs,
)


def test_canonical_output_is_utf8_bytes() -> None:
    """The canonicalizer returns real ``bytes`` (P0-2)."""
    out = canonicalize_production_outputs({"name": "你好"}, excluded_paths=())
    assert isinstance(out, bytes)
    # Round-trips through json.loads (bytes are accepted by json).
    parsed = json.loads(out)
    assert parsed == {"name": "你好"}


def test_canonical_output_contains_utf8_bytes_for_unicode() -> None:
    """Unicode characters are preserved as UTF-8 bytes, not escaped."""
    out = canonicalize_production_outputs({"name": "你好"}, excluded_paths=())
    # UTF-8 encoding of 你好.
    assert "你好".encode() in out
    # No ``\\uXXXX`` escape sequences in the bytes.
    assert b"\\u" not in out


def test_canonical_output_is_deterministic() -> None:
    a = canonicalize_production_outputs({"a": [1, 2, 3], "b": {"x": 1, "y": 2}}, excluded_paths=())
    b = canonicalize_production_outputs({"b": {"y": 2, "x": 1}, "a": [1, 2, 3]}, excluded_paths=())
    assert a == b


def test_canonical_output_uses_sorted_keys() -> None:
    out = canonicalize_production_outputs({"z": 1, "y": 2, "x": 3, "a": 4}, excluded_paths=())
    assert out == b'{"a":4,"x":3,"y":2,"z":1}'


def test_canonical_output_preserves_array_order() -> None:
    out = canonicalize_production_outputs([3, 1, 4, 1, 5, 9, 2, 6], excluded_paths=())
    assert out == b"[3,1,4,1,5,9,2,6]"


def test_canonical_output_uses_compact_separators() -> None:
    out = canonicalize_production_outputs({"a": 1, "b": 2}, excluded_paths=())
    # No whitespace in the output.
    assert b" " not in out
    assert out == b'{"a":1,"b":2}'


def test_canonical_output_is_valid_json() -> None:
    """The canonical output must be valid JSON. This is the
    meta-circular property the contract requires."""
    inputs = [
        None,
        True,
        42,
        3.14,
        "hello",
        [],
        {},
        [None, True, 1, 1.5, "s", [], {}],
        {"nested": {"a": [1, 2, 3], "b": {"x": 1}}},
    ]
    for value in inputs:
        out = canonicalize_production_outputs(value, excluded_paths=())
        # Round-trip parses successfully.
        json.loads(out)


def test_canonical_output_round_trip_equality() -> None:
    inputs = [
        {"a": 1, "b": [1, 2, 3]},
        {"nested": {"key": "value"}},
        [{"x": 1}, {"x": 2}],
    ]
    for value in inputs:
        out = canonicalize_production_outputs(value, excluded_paths=())
        parsed = json.loads(out)
        # The parsed value equals the input semantically.
        assert parsed == value


def test_canonical_output_unicode_is_not_escaped() -> None:
    """The canonicalizer uses ``ensure_ascii=False``, so unicode
    characters are preserved in the output rather than escaped."""
    out = canonicalize_production_outputs({"name": "你好"}, excluded_paths=())
    assert "你好".encode() in out
    # No \\uXXXX escapes.
    assert b"\\u" not in out


def test_canonical_output_handles_deeply_nested_structures() -> None:
    """The canonicalizer handles nested objects and arrays."""
    value = {"a": {"b": {"c": {"d": [1, [2, [3, [4, [5]]]]]}}}}
    out = canonicalize_production_outputs(value, excluded_paths=())
    parsed = json.loads(out)
    assert parsed == value


def test_canonical_output_handles_large_arrays() -> None:
    arr = list(range(1000))
    out = canonicalize_production_outputs(arr, excluded_paths=())
    parsed = json.loads(out)
    assert parsed == arr


def test_canonical_output_handles_large_objects() -> None:
    obj = {f"k{i}": i for i in range(1000)}
    out = canonicalize_production_outputs(obj, excluded_paths=())
    parsed = json.loads(out)
    assert parsed == obj


def test_canonical_sha_is_deterministic_and_hashes_bytes() -> None:
    """The SHA-256 of the canonical output is deterministic and
    hashes the canonical ``bytes`` directly (P0-2).

    The expected SHA is computed by:
    1. Canonicalize to ``bytes`` (UTF-8).
    2. ``hashlib.sha256(canonical_bytes).hexdigest()`` — no second
       ``.encode(...)`` step.
    """
    value = {"a": 1, "b": [1, 2, 3]}
    out = canonicalize_production_outputs(value, excluded_paths=())
    # Direct SHA-256 of the bytes — no intermediate encode step.
    expected = hashlib.sha256(out).hexdigest()
    # Re-canonicalize; must be identical (deterministic).
    out2 = canonicalize_production_outputs(value, excluded_paths=())
    assert hashlib.sha256(out2).hexdigest() == expected


def test_canonical_output_bytes_decodes_to_deterministic_utf8() -> None:
    """The bytes output decodes to deterministic UTF-8."""
    out = canonicalize_production_outputs({"a": 1}, excluded_paths=())
    # Bytes are valid UTF-8.
    decoded = out.decode("utf-8")
    assert decoded == '{"a":1}'


# ---------------------------------------------------------------------------
# P0-2 of review 4689835238 — hostile object must not trigger str()/repr()
# ---------------------------------------------------------------------------


class _HostileKey:
    """A hostile non-string dict key whose __str__/__repr__ raise.

    Per P0-2 of review 4689835238, the canonicalizer must reject this
    key without ever invoking ``str(key)`` or ``repr(key)``. The
    canonicalizer only inspects the type (via ``isinstance``) and
    records the type name; it never reads or stringifies the
    user-supplied value.
    """

    def __init__(self) -> None:
        self.str_called = False
        self.repr_called = False

    def __str__(self) -> str:
        self.str_called = True
        raise AssertionError("__str__ must not be called on a hostile key")

    def __repr__(self) -> str:
        self.repr_called = True
        raise AssertionError("__repr__ must not be called on a hostile key")

    def __hash__(self) -> int:
        return 0  # make it hashable so it can be a dict key at all

    def __eq__(self, other: object) -> bool:
        return self is other


def test_hostile_dict_key_does_not_trigger_str_or_repr() -> None:
    """A hostile non-string dict key must be rejected via type check
    only; neither ``str(key)`` nor ``repr(key)`` may be invoked.

    The error details record ONLY the structural path and the
    key's type name (``_HostileKey``); the key itself is never
    read or stringified.
    """
    from cold_storage.evaluation.canonicalization import (
        UnsupportedJSONValueError,
    )

    hostile = _HostileKey()
    try:
        canonicalize_production_outputs({hostile: "value"}, excluded_paths=())
    except UnsupportedJSONValueError as exc:
        assert exc.code == "UNSUPPORTED_JSON_VALUE", f"unexpected code {exc.code!r}"
        details = exc.details
        assert details["key_type"] == "_HostileKey", (
            f"key_type should be the class name, got {details.get('key_type')!r}"
        )
        # The hostile key itself must NOT be in the details.
        assert "value" not in details, (
            f"hostile value must not be recorded; got details={details!r}"
        )
        assert "key_repr" not in details, (
            f"key_repr must not be recorded (P0-2); got details={details!r}"
        )
    else:
        raise AssertionError("expected UnsupportedJSONValueError for hostile dict key")
    # The hostile object's __str__/__repr__ must NEVER have been called.
    assert hostile.str_called is False, "__str__ was called on hostile key — P0-2 violation"
    assert hostile.repr_called is False, "__repr__ was called on hostile key — P0-2 violation"


def test_hostile_excluded_paths_entry_does_not_trigger_str_or_repr() -> None:
    """A hostile entry in ``excluded_paths`` must be rejected via
    type check only; neither ``str(entry)`` nor ``repr(entry)`` may
    be invoked.

    The error details record ONLY the field name, the entry's
    index, and the entry's type name.
    """
    from typing import cast

    from cold_storage.evaluation.canonicalization import (
        UnsupportedJSONValueError,
    )

    hostile = _HostileKey()
    try:
        # type: ignore[arg-type] — hostile is intentionally not a str
        canonicalize_production_outputs(
            {"a": 1},
            excluded_paths=cast("list[str]", [hostile]),
        )
    except UnsupportedJSONValueError as exc:
        assert exc.code == "UNSUPPORTED_JSON_VALUE", f"unexpected code {exc.code!r}"
        details = exc.details
        assert details["field"] == "excluded_paths", (
            f"field should be 'excluded_paths', got {details.get('field')!r}"
        )
        assert details["index"] == 0, (
            f"index should be 0 (the hostile position), got {details.get('index')!r}"
        )
        assert details["value_type"] == "_HostileKey", (
            f"value_type should be the class name, got {details.get('value_type')!r}"
        )
        # The hostile value itself must NOT be in the details.
        assert "value" not in details, (
            f"hostile value must not be recorded; got details={details!r}"
        )
    else:
        raise AssertionError("expected UnsupportedJSONValueError for hostile excluded_paths entry")
    # The hostile object's __str__/__repr__ must NEVER have been called.
    assert hostile.str_called is False, (
        "__str__ was called on hostile excluded_paths entry — P0-2 violation"
    )
    assert hostile.repr_called is False, (
        "__repr__ was called on hostile excluded_paths entry — P0-2 violation"
    )
