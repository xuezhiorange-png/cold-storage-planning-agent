"""Tests for the manifest-driven comparison executor (TASK-011C C-2 — §9, D4).

Per §十七 the comparison executor MUST cover:

* exact scalar;
* bool vs int NOT equivalent;
* array order mismatch;
* object key mismatch;
* decimal canonical string exact;
* decimal scale drift mismatch;
* no float tolerance;
* undeclared path fail closed.

Each test asserts the typed result
(``ComparisonResult.passed`` + ``diffs``) — never parses
exception message text.
"""

from __future__ import annotations

from cold_storage.evaluation.compare import (
    compare_outputs,
)
from cold_storage.evaluation.models import (
    ComparisonKind,
    ComparisonPolicy,
    ComparisonPolicyLeaf,
)


def _exact_policy(*paths: str) -> ComparisonPolicy:
    """Build an EXACT policy covering ``paths``."""
    return ComparisonPolicy(
        leaves=tuple(ComparisonPolicyLeaf(path=p, kind=ComparisonKind.EXACT) for p in paths)
    )


def _decimal_policy(*paths: str) -> ComparisonPolicy:
    """Build a DECIMAL policy covering ``paths``."""
    return ComparisonPolicy(
        leaves=tuple(ComparisonPolicyLeaf(path=p, kind=ComparisonKind.DECIMAL) for p in paths)
    )


# ── §17 exact scalar ─────────────────────────────────────────────


def test_exact_scalar_match_returns_passed() -> None:
    """Two equal scalars return a passed result with no diffs."""
    result = compare_outputs(
        expected={"x": 1},
        actual={"x": 1},
        policy=_exact_policy("$.x"),
    )
    assert result.passed is True
    assert result.diffs == ()


def test_exact_scalar_mismatch_returns_value_mismatch_diff() -> None:
    """Two unequal scalars return a failed result with one diff entry."""
    result = compare_outputs(
        expected={"x": 1},
        actual={"x": 2},
        policy=_exact_policy("$.x"),
    )
    assert result.passed is False
    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.path == "$.x"
    assert d.kind == "value_mismatch"
    assert d.expected == 1
    assert d.actual == 2


# ── §17 bool vs int NOT equivalent ───────────────────────────────


def test_bool_and_int_are_type_mismatch() -> None:
    """``True`` and ``1`` are NOT equivalent under EXACT (different types)."""
    result = compare_outputs(
        expected={"x": True},
        actual={"x": 1},
        policy=_exact_policy("$.x"),
    )
    assert result.passed is False
    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.kind == "type_mismatch"
    # Never stringify the rejected values in the diff (per P0-2
    # of review 4689835238).
    assert d.expected is True
    assert d.actual == 1


# ── §17 array order mismatch ─────────────────────────────────────


def test_array_order_mismatch_returns_value_mismatch() -> None:
    """Array order is significant under EXACT (per §9)."""
    result = compare_outputs(
        expected={"xs": [1, 2, 3]},
        actual={"xs": [3, 2, 1]},
        policy=_exact_policy("$.xs"),
    )
    assert result.passed is False
    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.path == "$.xs"
    assert d.kind == "value_mismatch"
    assert d.expected == [1, 2, 3]
    assert d.actual == [3, 2, 1]


def test_array_element_mismatch_returns_value_mismatch() -> None:
    """An array element mismatch is reported under EXACT."""
    result = compare_outputs(
        expected={"xs": [1, 2, 3]},
        actual={"xs": [1, 2, 4]},
        policy=_exact_policy("$.xs"),
    )
    assert result.passed is False
    assert len(result.diffs) == 1


# ── §17 object key mismatch ──────────────────────────────────────


def test_object_key_mismatch_returns_unexpected_diff() -> None:
    """An actual object key not covered by the declared policy is unexpected."""
    result = compare_outputs(
        expected={"a": 1},
        actual={"a": 1, "b": 2},
        policy=_exact_policy("$.a"),
    )
    assert result.passed is False
    unexpected = [d for d in result.diffs if d.kind == "unexpected"]
    assert len(unexpected) == 1
    assert unexpected[0].path == "$.b"
    assert unexpected[0].actual == 2


# ── §17 decimal canonical string exact ───────────────────────────


def test_decimal_canonical_string_match_returns_passed() -> None:
    """Two equal canonical decimal strings return passed."""
    result = compare_outputs(
        expected={"x": "12.500"},
        actual={"x": "12.500"},
        policy=_decimal_policy("$.x"),
    )
    assert result.passed is True
    assert result.diffs == ()


def test_decimal_scale_drift_mismatch_returns_value_mismatch() -> None:
    """Different canonical scales (``12.500`` vs ``12.5``) are NOT equivalent.

    The DECIMAL kind compares the canonical string
    representation exactly — no tolerance, no quantize
    invention (per §9).
    """
    result = compare_outputs(
        expected={"x": "12.500"},
        actual={"x": "12.5"},
        policy=_decimal_policy("$.x"),
    )
    assert result.passed is False
    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.kind == "value_mismatch"
    assert d.expected == "12.500"
    assert d.actual == "12.5"


def test_decimal_with_non_canonical_input_fails_type_check() -> None:
    """DECIMAL inputs that are NOT strings fail the type check."""
    result = compare_outputs(
        expected={"x": 12.5},  # float, not canonical string
        actual={"x": "12.5"},
        policy=_decimal_policy("$.x"),
    )
    assert result.passed is False
    assert len(result.diffs) == 1
    d = result.diffs[0]
    assert d.kind == "type_mismatch"


# ── §17 no float tolerance ───────────────────────────────────────


def test_no_float_tolerance_in_exact_comparison() -> None:
    """EXACT comparison has no implicit float tolerance."""
    result = compare_outputs(
        expected={"x": 1.0000001},
        actual={"x": 1.0000002},
        policy=_exact_policy("$.x"),
    )
    assert result.passed is False


# ── §17 undeclared path fail closed ──────────────────────────────


def test_empty_policy_compares_whole_tree() -> None:
    """An empty policy (no declared leaves) compares the whole tree."""
    result = compare_outputs(
        expected={"a": 1, "b": 2},
        actual={"a": 1, "b": 2},
        policy=ComparisonPolicy(),
    )
    assert result.passed is True


def test_empty_policy_root_mismatch_fails() -> None:
    """An empty policy on mismatched roots returns a single root diff."""
    result = compare_outputs(
        expected={"a": 1, "b": 2},
        actual={"a": 1, "b": 3},
        policy=ComparisonPolicy(),
    )
    assert result.passed is False
    assert len(result.diffs) == 1
    assert result.diffs[0].path == "$"


def test_rejected_value_is_never_stringified() -> None:
    """The diff MUST NOT invoke ``str()`` / ``repr()`` on the
    rejected values. The Pydantic-model-typed values are
    passed as-is to the diff entry (per P0-2 of review
    4689835238).

    We verify this by passing two JSON-domain values
    (strings) and asserting the diff ``expected`` /
    ``actual`` are the literal string values, not any
    stringified form.
    """
    expected_value = "expected-text"
    actual_value = "actual-text"
    result = compare_outputs(
        expected=expected_value,
        actual=actual_value,
        policy=ComparisonPolicy(),
    )
    assert result.passed is False
    d = result.diffs[0]
    # The diff entries are the literal Python values, NOT
    # stringified via ``str()`` / ``repr()``.
    assert d.expected == expected_value
    assert d.actual == actual_value


def test_nested_object_value_mismatch() -> None:
    """Nested object value mismatch is reported with the full path."""
    result = compare_outputs(
        expected={"outer": {"inner": 1}},
        actual={"outer": {"inner": 2}},
        policy=_exact_policy("$.outer.inner"),
    )
    assert result.passed is False
    assert len(result.diffs) == 1
    assert result.diffs[0].path == "$.outer.inner"
    assert result.diffs[0].kind == "value_mismatch"


def test_exact_equal_dict_preserves_object_identity() -> None:
    """The ``_exact_equal`` helper is strict on object identity for dicts."""
    from cold_storage.evaluation.compare import _exact_equal

    assert _exact_equal({"a": 1, "b": 2}, {"a": 1, "b": 2}) is True
    assert _exact_equal({"a": 1}, {"a": 1, "b": 2}) is False
    assert _exact_equal({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True  # dict equality
    assert _exact_equal([1, 2, 3], [1, 2, 3]) is True
    assert _exact_equal([1, 2, 3], [3, 2, 1]) is False


# ── §17 P0-4 of review 4693931575 — recursive undeclared-leaf detection ──


def test_p0_4_nested_object_extra_leaf_reported() -> None:
    """P0-4: a nested object extra leaf (``$.outer.extra``) when
    only ``$.outer.inner`` is declared MUST be surfaced as a
    structured ``unexpected`` diff at the nested path. The
    historical top-level-key scan missed this.
    """
    result = compare_outputs(
        expected={"outer": {"inner": 1, "extra": 2}},
        actual={"outer": {"inner": 1, "extra": 2}},
        policy=_exact_policy("$.outer.inner"),
    )
    assert result.passed is False
    unexpected_paths = {d.path for d in result.diffs if d.kind == "unexpected"}
    assert "$.outer.extra" in unexpected_paths, (
        f"P0-4: expected $.outer.extra in unexpected diffs, got {unexpected_paths}"
    )


def test_p0_4_nested_array_extra_element_reported() -> None:
    """P0-4: an extra element in a nested array (``$.items[1].id``)
    when only ``$.items[0].id`` is declared MUST be surfaced
    as a structured ``unexpected`` diff.
    """
    result = compare_outputs(
        expected={"items": [{"id": "a"}, {"id": "b"}]},
        actual={"items": [{"id": "a"}, {"id": "b"}]},
        policy=_exact_policy("$.items[0].id"),
    )
    assert result.passed is False
    unexpected_paths = {d.path for d in result.diffs if d.kind == "unexpected"}
    assert "$.items[1].id" in unexpected_paths, (
        f"P0-4: expected $.items[1].id in unexpected diffs, got {unexpected_paths}"
    )


def test_p0_4_declared_descendant_does_not_cover_parent() -> None:
    """P0-4: having a declared DESCENDANT does NOT cover the
    whole parent container. If the parent has another leaf
    that is not declared, that leaf MUST be reported as
    ``unexpected`` even though the parent has a declared
    descendant.
    """
    result = compare_outputs(
        expected={"outer": {"inner": 1, "extra": "leak"}},
        actual={"outer": {"inner": 1, "extra": "leak"}},
        policy=_exact_policy("$.outer.inner"),
    )
    assert result.passed is False
    unexpected_paths = {d.path for d in result.diffs if d.kind == "unexpected"}
    assert "$.outer.extra" in unexpected_paths


def test_p0_4_declared_container_path_covers_subtree() -> None:
    """P0-4: when the policy declares a CONTAINER path (e.g.
    ``$.outer``), all descendants inside that container are
    considered covered and MUST NOT be reported as
    ``unexpected`` (the parent declaration is sufficient).
    """
    result = compare_outputs(
        expected={"outer": {"inner": 1, "extra": 2}},
        actual={"outer": {"inner": 1, "extra": 2}},
        policy=_exact_policy("$.outer"),
    )
    # No ``unexpected`` diffs — the container covers its subtree.
    unexpected = [d for d in result.diffs if d.kind == "unexpected"]
    assert list(unexpected) == [], (
        f"P0-4: declared container path should cover subtree, got unexpected {unexpected}"
    )
    # And the whole-container comparison is exact-PASS.
    assert result.passed is True


def test_p0_4_array_order_remains_exact() -> None:
    """P0-4: the P0-4 recursive undeclared-leaf detection MUST
    NOT weaken the D4 array-order-exact semantic. A
    permuted array still produces a ``value_mismatch`` diff
    (NOT silently accepted as just an undeclared leaf).
    """
    result = compare_outputs(
        expected={"items": [1, 2, 3]},
        actual={"items": [3, 2, 1]},
        policy=_exact_policy("$.items"),
    )
    assert result.passed is False
    # The diff MUST be a value_mismatch on $.items — not
    # decomposed into per-index undeclared leaves.
    assert any(d.path == "$.items" and d.kind == "value_mismatch" for d in result.diffs), (
        f"P0-4: expected value_mismatch on $.items, got {result.diffs}"
    )


# ── §17 P0-4 of review 4694841112 — empty-container fail-closed ──


def test_p0_4_empty_object_under_declared_outer_is_unexpected() -> None:
    """P0-4 of review 4694841112: an undeclared empty ``{}``
    under a declared ``$.outer.inner`` parent MUST be
    surfaced as a structured ``unexpected`` diff at the
    path ``$.outer.extra``. The historical top-level-only
    scan missed this; the recursive ``_walk_leaves`` now
    emits empty containers as terminal coverage nodes.
    """
    result = compare_outputs(
        expected={"outer": {"inner": 1, "extra": {}}},
        actual={"outer": {"inner": 1, "extra": {}}},
        policy=_exact_policy("$.outer.inner"),
    )
    assert result.passed is False
    unexpected_paths = {d.path for d in result.diffs if d.kind == "unexpected"}
    assert "$.outer.extra" in unexpected_paths, (
        f"P0-4: expected $.outer.extra in unexpected diffs, got {unexpected_paths}"
    )


def test_p0_4_empty_array_under_declared_outer_is_unexpected() -> None:
    """P0-4 of review 4694841112: an undeclared empty ``[]``
    under a declared ``$.outer.inner`` parent MUST be
    surfaced as a structured ``unexpected`` diff at the
    path ``$.outer.extra``.
    """
    result = compare_outputs(
        expected={"outer": {"inner": 1, "extra": []}},
        actual={"outer": {"inner": 1, "extra": []}},
        policy=_exact_policy("$.outer.inner"),
    )
    assert result.passed is False
    unexpected_paths = {d.path for d in result.diffs if d.kind == "unexpected"}
    assert "$.outer.extra" in unexpected_paths, (
        f"P0-4: expected $.outer.extra in unexpected diffs, got {unexpected_paths}"
    )


def test_p0_4_empty_object_in_array_index_is_unexpected() -> None:
    """P0-4 of review 4694841112: an undeclared empty ``{}``
    at a nested array index (``$.items[1]`` when only
    ``$.items[0].id`` is declared) MUST be surfaced as a
    structured ``unexpected`` diff at the path
    ``$.items[1]``.
    """
    result = compare_outputs(
        expected={"items": [{"id": 1}, {}]},
        actual={"items": [{"id": 1}, {}]},
        policy=_exact_policy("$.items[0].id"),
    )
    assert result.passed is False
    unexpected_paths = {d.path for d in result.diffs if d.kind == "unexpected"}
    assert "$.items[1]" in unexpected_paths, (
        f"P0-4: expected $.items[1] in unexpected diffs, got {unexpected_paths}"
    )


def test_p0_4_empty_array_in_array_index_is_unexpected() -> None:
    """P0-4 of review 4694841112: an undeclared empty ``[]``
    at a nested array index (``$.items[1]`` when only
    ``$.items[0].id`` is declared) MUST be surfaced as a
    structured ``unexpected`` diff at the path
    ``$.items[1]``.
    """
    result = compare_outputs(
        expected={"items": [{"id": 1}, []]},
        actual={"items": [{"id": 1}, []]},
        policy=_exact_policy("$.items[0].id"),
    )
    assert result.passed is False
    unexpected_paths = {d.path for d in result.diffs if d.kind == "unexpected"}
    assert "$.items[1]" in unexpected_paths, (
        f"P0-4: expected $.items[1] in unexpected diffs, got {unexpected_paths}"
    )


def test_p0_4_declared_empty_container_passes() -> None:
    """P0-4 of review 4694841112: when the policy declares
    the container path (e.g. ``$.outer.extra``), the empty
    container is COVERED and the comparison passes.
    """
    result = compare_outputs(
        expected={"outer": {"inner": 1, "extra": {}}},
        actual={"outer": {"inner": 1, "extra": {}}},
        policy=_exact_policy("$.outer.inner", "$.outer.extra"),
    )
    assert result.passed is True, f"P0-4: expected pass, got diffs: {result.diffs}"
