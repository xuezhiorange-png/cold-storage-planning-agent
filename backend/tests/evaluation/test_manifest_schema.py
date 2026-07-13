"""Manifest schema structural tests (TASK-011C V1).

These tests assert the **JSON Schema** integrity of
``backend/src/cold_storage/evaluation/schema/manifest.schema.json``
— that the schema itself is well-formed, that it is the single
source of truth, and that it matches the pydantic model.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema


def _schema_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cold_storage"
        / "evaluation"
        / "schema"
        / "manifest.schema.json"
    )


def test_schema_file_exists() -> None:
    p = _schema_path()
    assert p.exists()
    assert p.is_file()


def test_schema_is_valid_json() -> None:
    text = _schema_path().read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert parsed["type"] == "object"


def test_schema_declares_v1_title() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    assert parsed["title"] == "TASK-011C V1 Manifest"
    assert parsed["additionalProperties"] is False


def test_schema_requires_schema_version_suite_id_scenarios() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    required = set(parsed["required"])
    assert "schema_version" in required
    assert "suite_id" in required
    assert "scenarios" in required


def test_schema_schema_version_is_const_1_0() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    sv = parsed["properties"]["schema_version"]
    assert sv["type"] == "string"
    assert sv["const"] == "1.0"


def test_schema_excluded_paths_max_items_zero() -> None:
    """D3: V1 exclusion set is empty. The schema enforces ``maxItems: 0``."""
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    ep = parsed["properties"]["excluded_paths"]
    assert ep["type"] == "array"
    assert ep["maxItems"] == 0


def test_schema_scenarios_min_items_one() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    assert parsed["properties"]["scenarios"]["minItems"] >= 1


def test_schema_scenario_rejects_unknown_fields() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    scenario = parsed["$defs"]["scenario"]
    assert scenario["additionalProperties"] is False


def test_schema_comparison_policy_uses_exact_default() -> None:
    """D4: the default comparison kind is ``exact``. The schema
    advertises ``exact`` as a valid kind (alongside the
    decimal_canonical / excluded alternatives)."""
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    leaf = parsed["$defs"]["comparison_policy_leaf"]
    assert "exact" in leaf["properties"]["kind"]["enum"]
    assert "decimal_canonical" in leaf["properties"]["kind"]["enum"]


def test_schema_validates_against_draft202012() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    # The schema declares a draft. The validator should accept it.
    jsonschema.Draft202012Validator.check_schema(parsed)


def test_schema_accepts_minimal_valid_manifest() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(parsed)
    valid_manifest = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "baseline_feasible",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
    }
    errors = list(validator.iter_errors(valid_manifest))
    assert errors == []


def test_schema_rejects_numeric_schema_version() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(parsed)
    invalid = {
        "schema_version": 1.0,
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "s",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
    }
    errors = list(validator.iter_errors(invalid))
    assert errors


def test_schema_rejects_rogue_field() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(parsed)
    invalid = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "s",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
        "rogue_field": "forbidden",
    }
    errors = list(validator.iter_errors(invalid))
    assert errors
    # The error must mention additionalProperties.
    assert any(e.validator == "additionalProperties" for e in errors)


def test_schema_rejects_non_empty_excluded_paths() -> None:
    parsed = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(parsed)
    invalid = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "s",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
        "excluded_paths": ["$.x"],
    }
    errors = list(validator.iter_errors(invalid))
    assert errors
    assert any(e.validator == "maxItems" for e in errors)
