"""Tests for the V1 restricted JSON Path (TASK-011C C-2 — §8).

Per §十七 (D10) the JSON Path module MUST cover:

* root;
* nested key;
* array index;
* missing key;
* wrong container type;
* wildcard rejected;
* recursive descent rejected;
* filter / script rejected.

Each test asserts the typed result (success value or typed
error code) — never parses exception message text.
"""

from __future__ import annotations

import pytest

from cold_storage.evaluation.json_path import (
    JSONPathLookupError,
    JSONPathParseError,
    PathStep,
    lookup,
    parse_path,
)


# ── §十七 positive cases ─────────────────────────────────────────


def test_root_path_parses_to_single_root_step() -> None:
    """``$`` parses to a single root step."""
    steps = parse_path("$")
    assert steps == [PathStep(kind="root", value="$")]


def test_root_path_lookup_returns_the_value_unchanged() -> None:
    """Looking up the root path returns the value as-is."""
    assert lookup({"a": 1}, parse_path("$")) == {"a": 1}
    assert lookup([1, 2, 3], parse_path("$")) == [1, 2, 3]
    assert lookup(None, parse_path("$")) is None
    assert lookup(42, parse_path("$")) == 42


def test_nested_key_path_parses_and_resolves() -> None:
    """``$.a.b`` parses to [root, key(a), key(b)] and resolves."""
    steps = parse_path("$.a.b")
    assert steps == [
        PathStep(kind="root", value="$"),
        PathStep(kind="key", value="a"),
        PathStep(kind="key", value="b"),
    ]
    assert lookup({"a": {"b": "leaf"}}, steps) == "leaf"


def test_array_index_path_parses_and_resolves() -> None:
    """``$.array[0]`` parses to [root, key(array), index(0)] and resolves."""
    steps = parse_path("$.array[0]")
    assert steps == [
        PathStep(kind="root", value="$"),
        PathStep(kind="key", value="array"),
        PathStep(kind="index", value=0),
    ]
    assert lookup({"array": ["x", "y", "z"]}, steps) == "x"


def test_combined_nested_and_indexed_path() -> None:
    """``$.a[0].b`` (combined key + index + key) resolves correctly."""
    steps = parse_path("$.a[0].b")
    assert lookup({"a": [{"b": "deep"}]}, steps) == "deep"


# ── §十七 negative cases (rejection at PARSE time) ────────────────


def test_empty_path_is_rejected_at_parse_time() -> None:
    """An empty path is rejected at PARSE time with a typed error."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_non_string_path_is_rejected_at_parse_time() -> None:
    """A non-string path is rejected at PARSE time with a typed error."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path(123)  # type: ignore[arg-type]
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_path_without_dollar_root_marker_is_rejected() -> None:
    """A path that does not start with ``$`` is rejected."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("a.b")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_wildcard_is_rejected_at_parse_time() -> None:
    """Wildcard (``*``) is rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.*")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_wildcard_inside_step_is_rejected() -> None:
    """A wildcard in a multi-character segment is rejected."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.a.*.b")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_recursive_descent_is_rejected_at_parse_time() -> None:
    """Recursive descent (``..``) is rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$..foo")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_filter_expression_is_rejected_at_parse_time() -> None:
    """Filter expressions (``[?(...)]``) are rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.a[?(@.x)]")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_script_expression_is_rejected_at_parse_time() -> None:
    """Script expressions (``[(...)]``) are rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.a[(@.x)]")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_negative_index_is_rejected_at_parse_time() -> None:
    """Negative indexes (``[-1]``) are rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.a[-1]")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_slice_is_rejected_at_parse_time() -> None:
    """Slices (``[0:3]``) are rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.a[0:3]")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_unquoted_dynamic_expression_is_rejected() -> None:
    """Unquoted dynamic expressions (``[foo]``) are rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.a[foo]")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


def test_malformed_index_is_rejected() -> None:
    """Malformed index (``[abc]``) is rejected at PARSE time."""
    with pytest.raises(JSONPathParseError) as exc_info:
        parse_path("$.a[abc]")
    assert exc_info.value.code == "JSON_PATH_PARSE_ERROR"


# ── §十七 negative cases (rejection at LOOKUP time) ──────────────


def test_missing_key_raises_lookup_error() -> None:
    """A missing key in a dict container raises a typed lookup error."""
    steps = parse_path("$.missing")
    with pytest.raises(JSONPathLookupError) as exc_info:
        lookup({"a": 1}, steps)
    assert exc_info.value.code == "JSON_PATH_LOOKUP_ERROR"


def test_wrong_container_type_for_key_raises_lookup_error() -> None:
    """A key step on a non-dict container raises a typed lookup error."""
    steps = parse_path("$.a")
    with pytest.raises(JSONPathLookupError) as exc_info:
        lookup([1, 2, 3], steps)
    assert exc_info.value.code == "JSON_PATH_LOOKUP_ERROR"


def test_wrong_container_type_for_index_raises_lookup_error() -> None:
    """An index step on a non-list container raises a typed lookup error."""
    steps = parse_path("$.a[0]")
    with pytest.raises(JSONPathLookupError) as exc_info:
        lookup({"a": "not a list"}, steps)
    assert exc_info.value.code == "JSON_PATH_LOOKUP_ERROR"


def test_out_of_range_index_raises_lookup_error() -> None:
    """An out-of-range index raises a typed lookup error."""
    steps = parse_path("$.a[5]")
    with pytest.raises(JSONPathLookupError) as exc_info:
        lookup({"a": [1, 2, 3]}, steps)
    assert exc_info.value.code == "JSON_PATH_LOOKUP_ERROR"
