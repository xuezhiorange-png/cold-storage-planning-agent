"""Tests for evaluation result comparison."""

from __future__ import annotations

import pytest

from cold_storage.evaluation.compare import (
    ComparisonMismatchKind,
    compare_evaluation_result,
)
from cold_storage.evaluation.json_path import (
    ArrayIndexSegment,
    ObjectKeySegment,
    parse_json_path,
    resolve_json_path,
)
from cold_storage.evaluation.models import (
    ComparisonPolicy,
    DecimalMode,
    DecimalPathRule,
    ExactPathRule,
    IgnoredPathRule,
)


def _policy(
    decimal: list[dict] | None = None,
    ignored: list[dict] | None = None,
) -> ComparisonPolicy:
    """Build a ComparisonPolicy with optional decimal and ignored paths."""
    return ComparisonPolicy(
        exact_paths=(),
        decimal_paths=tuple(
            DecimalPathRule(
                p["path"],
                DecimalMode(p["mode"]),
                p["scale"],
                p["unit"],
                p["rationale"],
            )
            for p in (decimal or [])
        ),
        ignored_paths=tuple(IgnoredPathRule(p["path"], p["reason"]) for p in (ignored or [])),
        artifact_checks=(),
    )


# ── Basic recursive comparison tests ────────────────────────────────────────


def test_exact_success() -> None:
    """Empty policy, identical objects must pass."""
    policy = _policy()
    result = compare_evaluation_result({"value": 42}, {"value": 42}, policy)
    assert result.passed


def test_exact_mismatch() -> None:
    """Empty policy, different values must fail."""
    policy = _policy()
    result = compare_evaluation_result({"value": 42}, {"value": 99}, policy)
    assert not result.passed
    assert len(result.mismatches) == 1
    assert result.mismatches[0].kind == ComparisonMismatchKind.EXACT_MISMATCH


def test_missing_actual() -> None:
    """Expected field missing from actual must fail."""
    policy = _policy()
    result = compare_evaluation_result({"needed": 42}, {"other": 1}, policy)
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.MISSING_ACTUAL


def test_type_mismatch() -> None:
    """String vs int mismatch must fail."""
    policy = _policy()
    result = compare_evaluation_result({"value": 42}, {"value": "42"}, policy)
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.TYPE_MISMATCH


def test_bool_vs_int_mismatch() -> None:
    """Bool vs int mismatch must fail."""
    policy = _policy()
    result = compare_evaluation_result({"flag": True}, {"flag": 1}, policy)
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.TYPE_MISMATCH


def test_extra_actual_field_rejected() -> None:
    """Extra fields in actual not declared in expected must fail."""
    policy = _policy()
    result = compare_evaluation_result(
        {"known": 1},
        {"known": 1, "unexpected": 2},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.EXTRA_ACTUAL_FIELD


def test_multiple_mismatches_collected() -> None:
    """Multiple mismatches must all be collected."""
    policy = _policy()
    result = compare_evaluation_result(
        {"a": 1, "b": 2},
        {"a": 10, "b": 20},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) >= 2


# ── Ignored paths ───────────────────────────────────────────────────────────


def test_ignored_field_does_not_affect() -> None:
    """Ignored fields must not participate in comparison."""
    policy = _policy(
        ignored=[{"path": "$.ignore", "reason": "test"}],
    )
    result = compare_evaluation_result(
        {"value": 42, "ignore": "anything"},
        {"value": 42, "ignore": "different"},
        policy,
    )
    assert result.passed


# ── Decimal path tests ──────────────────────────────────────────────────────


def test_decimal_quantize_success() -> None:
    """Decimal quantization with matching values must pass."""
    policy = _policy(
        decimal=[
            {
                "path": "$.area",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "test",
            }
        ],
    )
    result = compare_evaluation_result(
        {"area": 100.00},
        {"area": 100.001},
        policy,
    )
    assert result.passed


def test_decimal_mismatch() -> None:
    """Decimal mismatch must produce DECIMAL_MISMATCH kind."""
    policy = _policy(
        decimal=[
            {
                "path": "$.area",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "test",
            }
        ],
    )
    result = compare_evaluation_result(
        {"area": 100.00},
        {"area": 150.00},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.DECIMAL_MISMATCH


# ── New recursive comparison tests ──────────────────────────────────────────


def test_empty_policy_nested_value_changed() -> None:
    """Empty policy catches mismatch at a nested path."""
    policy = _policy()
    result = compare_evaluation_result(
        {"outer": {"inner": 42}},
        {"outer": {"inner": 99}},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) == 1
    assert result.mismatches[0].kind == ComparisonMismatchKind.EXACT_MISMATCH


def test_array_length_changed() -> None:
    """Array length differences must be detected."""
    policy = _policy()
    result = compare_evaluation_result(
        {"items": [1, 2, 3]},
        {"items": [1, 2]},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.ARRAY_LENGTH_MISMATCH


def test_list_order_matters() -> None:
    """List comparison is element-by-index, so order matters."""
    policy = _policy()
    result = compare_evaluation_result(
        {"items": [1, 2]},
        {"items": [2, 1]},
        policy,
    )
    assert not result.passed
    assert len(result.mismatches) >= 1


def test_list_element_type_changed() -> None:
    """Type mismatch inside a list must be detected."""
    policy = _policy()
    result = compare_evaluation_result(
        {"items": [42]},
        {"items": ["42"]},
        policy,
    )
    assert not result.passed
    assert result.mismatches[0].kind == ComparisonMismatchKind.TYPE_MISMATCH


# ── JSONPath parser tests ───────────────────────────────────────────────────


def test_parse_jsonpath_root() -> None:
    """'$' must parse to empty segments."""
    parsed = parse_json_path("$")
    assert parsed.raw == "$"
    assert parsed.segments == ()


def test_parse_jsonpath_field() -> None:
    """'$.field' must parse to a single ObjectKeySegment."""
    parsed = parse_json_path("$.field")
    assert parsed.raw == "$.field"
    assert parsed.segments == (ObjectKeySegment(key="field"),)


def test_parse_jsonpath_index() -> None:
    """'$[0]' must parse to a single ArrayIndexSegment."""
    parsed = parse_json_path("$[0]")
    assert parsed.raw == "$[0]"
    assert parsed.segments == (ArrayIndexSegment(index=0),)


def test_parse_jsonpath_unsupported() -> None:
    """Negative index and wildcard must raise JsonPathInvalidError."""
    from cold_storage.evaluation.errors import JsonPathInvalidError

    with pytest.raises(JsonPathInvalidError):
        parse_json_path("$[-1]")
    with pytest.raises(JsonPathInvalidError):
        parse_json_path("$[*]")


def test_resolve_path_works() -> None:
    """resolve_path must correctly resolve a parsed path."""
    obj = {"a": [{"b": 42}]}
    parsed = parse_json_path("$.a[0].b")
    value, found = resolve_json_path(obj, parsed)
    assert found is True
    assert value == 42


def test_resolve_path_missing() -> None:
    """resolve_path must return (None, False) for a missing path."""
    obj = {"a": 1}
    parsed = parse_json_path("$.b")
    value, found = resolve_json_path(obj, parsed)
    assert found is False
    assert value is None


# ── Exact path validation tests (P0-1) ─────────────────────────────────


def test_exact_path_expected_missing_actual() -> None:
    """Exact path declared in expected but absent in actual must fail."""
    policy = ComparisonPolicy(
        exact_paths=(ExactPathRule(path="$.required"),),
        decimal_paths=(),
        ignored_paths=(),
        artifact_checks=(),
    )
    result = compare_evaluation_result(
        {"required": 42},
        {"other": 1},
        policy,
    )
    assert not result.passed
    assert any(m.kind == ComparisonMismatchKind.MISSING_ACTUAL for m in result.mismatches)


def test_exact_path_actual_missing_expected() -> None:
    """Exact path in actual but missing from expected must fail with MISSING_EXPECTED."""
    policy = ComparisonPolicy(
        exact_paths=(ExactPathRule(path="$.extra"),),
        decimal_paths=(),
        ignored_paths=(),
        artifact_checks=(),
    )
    result = compare_evaluation_result(
        {"known": 1},
        {"known": 1, "extra": 2},
        policy,
    )
    assert not result.passed
    assert any(
        m.kind == ComparisonMismatchKind.MISSING_EXPECTED and m.path == "$.extra"
        for m in result.mismatches
    )


def test_exact_path_both_missing() -> None:
    """Exact path absent from both sides must fail (MISSING_EXPECTED)."""
    policy = ComparisonPolicy(
        exact_paths=(ExactPathRule(path="$.required"),),
        decimal_paths=(),
        ignored_paths=(),
        artifact_checks=(),
    )
    result = compare_evaluation_result(
        {},
        {},
        policy,
    )
    assert not result.passed
    assert any(
        m.kind == ComparisonMismatchKind.MISSING_EXPECTED and m.path == "$.required"
        for m in result.mismatches
    )


def test_exact_path_present_passes() -> None:
    """Exact path present on both sides with matching values must pass."""
    policy = ComparisonPolicy(
        exact_paths=(ExactPathRule(path="$.value"),),
        decimal_paths=(),
        ignored_paths=(),
        artifact_checks=(),
    )
    result = compare_evaluation_result(
        {"value": 42},
        {"value": 42},
        policy,
    )
    assert result.passed


def test_decimal_match_returns_passed() -> None:
    """Decimal paths with matching quantized values must pass."""
    policy = _policy(
        decimal=[
            {
                "path": "$.area",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "Testing decimal match",
            }
        ],
    )
    result = compare_evaluation_result(
        {"area": 100.004},
        {"area": 100.001},
        policy,
    )
    assert result.passed


def test_decimal_mismatch_no_duplicate_exact() -> None:
    """Decimal mismatch must not also report EXACT_MISMATCH for the same path."""
    policy = _policy(
        decimal=[
            {
                "path": "$.area",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "Test",
            }
        ],
    )
    result = compare_evaluation_result(
        {"area": 100.00},
        {"area": 200.00},
        policy,
    )
    assert not result.passed
    kinds = [m.kind for m in result.mismatches]
    assert ComparisonMismatchKind.DECIMAL_MISMATCH in kinds
    assert ComparisonMismatchKind.EXACT_MISMATCH not in kinds


def test_root_path_format_uses_dot() -> None:
    """Root child paths must use $.field format, not $field."""
    policy = _policy()
    result = compare_evaluation_result(
        {"area": 100},
        {"area": 200},
        policy,
    )
    assert not result.passed
    assert any("$.area" in m.path for m in result.mismatches)


def test_nested_path_format() -> None:
    """Nested paths must use $.a.b format."""
    policy = _policy()
    result = compare_evaluation_result(
        {"a": {"b": 1}},
        {"a": {"b": 2}},
        policy,
    )
    assert not result.passed
    assert any("$.a.b" in m.path for m in result.mismatches)


def test_array_path_format() -> None:
    """Array paths must use $[0] format."""
    policy = _policy()
    result = compare_evaluation_result(
        {"items": [1, 2, 3]},
        {"items": [1, 99, 3]},
        policy,
    )
    assert not result.passed
    assert any("$.items[1]" in m.path for m in result.mismatches)


def test_unsupported_jsonpath_raises_stable_error() -> None:
    """Unsupported JSONPath grammar must raise JsonPathInvalidError (not bare ValueError)."""
    from cold_storage.evaluation.errors import JsonPathInvalidError

    with pytest.raises(JsonPathInvalidError) as exc_info:
        parse_json_path("$[*]")
    assert exc_info.value.code == "EVAL_JSON_PATH_INVALID"


def test_repeated_array_index_path() -> None:
    """Matrix-style path $.matrix[0][1] must work."""
    parsed = parse_json_path("$.matrix[0][1]")
    assert len(parsed.segments) == 3
    assert parsed.segments[0].key == "matrix"  # type: ignore[attr-defined]
    assert parsed.segments[1].index == 0  # type: ignore[attr-defined]
    assert parsed.segments[2].index == 1  # type: ignore[attr-defined]


def test_ignored_path_uses_same_parser() -> None:
    """Ignored path must use the same parser as exact/decimal paths."""
    policy = _policy(
        ignored=[{"path": "$.metadata", "reason": "runtime timestamp excluded"}],
    )
    result = compare_evaluation_result(
        {"value": 42, "metadata": {"ts": "now"}},
        {"value": 42, "metadata": {"ts": "later"}},
        policy,
    )
    assert result.passed


# ── P0-5: JSONPath grammar regression tests ────────────────────────


class TestJsonPathGrammar:
    """JSONPath grammar must match manifest.schema.json constraints."""

    def test_non_string_input_rejected(self):
        """Non-string path_str must raise JsonPathInvalidError."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        for bad in (None, 123, True, [], {}):
            with pytest.raises(JsonPathInvalidError) as exc:
                parse_json_path(bad)  # type: ignore[arg-type]
            assert exc.value.code == "EVAL_JSON_PATH_INVALID"

    def test_array_index_leading_zero_rejected(self):
        """$[01] must raise JsonPathInvalidError (leading zero)."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$[01]")

    def test_array_index_positive_sign_rejected(self):
        """$[+1] must raise JsonPathInvalidError."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$[+1]")

    def test_array_index_space_rejected(self):
        """$[ 1] must raise JsonPathInvalidError."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$[ 1]")

    def test_array_index_trailing_space_rejected(self):
        """$[1 ] must raise JsonPathInvalidError."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$[1 ]")

    def test_object_key_wildcard_rejected(self):
        """$.* must raise JsonPathInvalidError (wildcard)."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$.*")

    def test_object_key_dash_rejected(self):
        """$.-field must raise JsonPathInvalidError."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$.-field")

    def test_object_key_number_prefix_rejected(self):
        """$.1field must raise JsonPathInvalidError."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$.1field")

    def test_object_key_double_dot_rejected(self):
        """$..field must raise JsonPathInvalidError (recursive descent)."""
        from cold_storage.evaluation.errors import JsonPathInvalidError
        from cold_storage.evaluation.json_path import parse_json_path

        with pytest.raises(JsonPathInvalidError):
            parse_json_path("$..field")


class TestJsonPathRoundTrip:
    """parse + render must round-trip for all legal paths."""

    @pytest.mark.parametrize(
        "path",
        [
            "$",
            "$.field",
            "$._field",
            "$.field_1",
            "$[0]",
            "$.items[10]",
            "$.matrix[0][1]",
            "$.a.b.c",
            "$.a[0].b[1]",
        ],
    )
    def test_round_trip(self, path: str):
        from cold_storage.evaluation.json_path import parse_json_path, render_json_path

        parsed = parse_json_path(path)
        assert parsed.raw == path
        assert render_json_path(parsed) == path


# ── P0-6: Malformed comparison path loader/CLI tests ───────────────


@pytest.mark.parametrize(
    "bad_path",
    [
        {"path": []},
        {"path": {}},
        {"path": None},
        {"path": True},
        {"path": 123},
    ],
)
def test_malformed_exact_path_via_loader(tmp_path, bad_path):
    """Malformed exact path must raise ManifestSchemaError via loader."""
    import json

    from cold_storage.evaluation.errors import ManifestSchemaError
    from cold_storage.evaluation.manifest import load_evaluation_manifest

    manifest = {
        "schema_version": "1.0",
        "suite_id": "test",
        "suite_revision": 1,
        "scenarios": [
            {
                "scenario_id": "s1",
                "fixture_revision": 1,
                "expected_outcome": "success",
                "project_input_path": "../evaluation/examples/project-input.json",
                "document_refs": [],
                "required_stages": [],
                "expected_path": "../evaluation/examples/expected-output.json",
                "provenance": {"source": "test", "rationale": "regression test"},
                "comparison_policy": {
                    "exact_paths": [bad_path],
                    "decimal_paths": [],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
            }
        ],
    }
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps(manifest), "utf-8")

    with pytest.raises(ManifestSchemaError) as exc:
        load_evaluation_manifest(str(mf))
    assert exc.value.code == "EVAL_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "bad_path",
    [
        {"path": []},
        {"path": {}},
        {"path": None},
        {"path": True},
        {"path": 123},
    ],
)
def test_malformed_decimal_path_via_loader(tmp_path, bad_path):
    """Malformed decimal path must raise ManifestSchemaError via loader."""
    import json

    from cold_storage.evaluation.errors import ManifestSchemaError
    from cold_storage.evaluation.manifest import load_evaluation_manifest

    manifest = {
        "schema_version": "1.0",
        "suite_id": "test",
        "suite_revision": 1,
        "scenarios": [
            {
                "scenario_id": "s1",
                "fixture_revision": 1,
                "expected_outcome": "success",
                "project_input_path": "../evaluation/examples/project-input.json",
                "document_refs": [],
                "required_stages": [],
                "expected_path": "../evaluation/examples/expected-output.json",
                "provenance": {"source": "test", "rationale": "regression test"},
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [bad_path],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
            }
        ],
    }
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps(manifest), "utf-8")

    with pytest.raises(ManifestSchemaError) as exc:
        load_evaluation_manifest(str(mf))
    assert exc.value.code == "EVAL_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "bad_path",
    [
        {"path": []},
        {"path": {}},
        {"path": None},
        {"path": True},
        {"path": 123},
    ],
)
def test_malformed_ignored_path_via_loader(tmp_path, bad_path):
    """Malformed ignored path must raise ManifestSchemaError via loader."""
    import json

    from cold_storage.evaluation.errors import ManifestSchemaError
    from cold_storage.evaluation.manifest import load_evaluation_manifest

    manifest = {
        "schema_version": "1.0",
        "suite_id": "test",
        "suite_revision": 1,
        "scenarios": [
            {
                "scenario_id": "s1",
                "fixture_revision": 1,
                "expected_outcome": "success",
                "project_input_path": "../evaluation/examples/project-input.json",
                "document_refs": [],
                "required_stages": [],
                "expected_path": "../evaluation/examples/expected-output.json",
                "provenance": {"source": "test", "rationale": "regression test"},
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [],
                    "ignored_paths": [bad_path],
                    "artifact_checks": [],
                },
            }
        ],
    }
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps(manifest), "utf-8")

    with pytest.raises(ManifestSchemaError) as exc:
        load_evaluation_manifest(str(mf))
    assert exc.value.code == "EVAL_SCHEMA_INVALID"
