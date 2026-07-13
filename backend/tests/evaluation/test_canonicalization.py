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
