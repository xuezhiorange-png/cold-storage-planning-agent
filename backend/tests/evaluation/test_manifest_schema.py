"""Tests for manifest JSON Schema validation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from cold_storage.evaluation.errors import ManifestSchemaError
from cold_storage.evaluation.manifest import validate_manifest_structure

_VALID = {
    "schema_version": "1.0",
    "suite_id": "cold-storage-pilot-v1",
    "suite_revision": 1,
    "scenarios": [],
}


def _write_manifest(data: dict) -> Path:
    """Write a manifest dict to a temp file and return the path."""
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(data), "utf-8")
    return tmp


def test_valid_empty_scenarios() -> None:
    """Empty scenarios array passes validation."""
    tmp = _write_manifest(_VALID)
    info = validate_manifest_structure(tmp)
    assert info["scenario_count"] == 0


def test_unknown_schema_version_rejected() -> None:
    """Unknown schema_version must fail."""
    data = dict(_VALID, schema_version="2.0")
    tmp = _write_manifest(data)
    with pytest.raises(ManifestSchemaError):
        validate_manifest_structure(tmp)


def test_root_unknown_field_rejected() -> None:
    """Unknown field at root level must fail."""
    data = dict(_VALID, extra_field="nope")
    tmp = _write_manifest(data)
    with pytest.raises(ManifestSchemaError):
        validate_manifest_structure(tmp)


def test_nested_unknown_field_rejected() -> None:
    """Unknown field inside a scenario must fail."""
    data = dict(
        _VALID,
        scenarios=[
            {
                "scenario_id": "test",
                "fixture_revision": 1,
                "project_input_path": "projects/input.json",
                "document_refs": [],
                "required_stages": ["planning"],
                "expected_outcome": "success",
                "expected_path": "expected/out.json",
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
                "provenance": {"source": "test", "rationale": "test"},
                "bogus_field": True,
            }
        ],
    )
    tmp = _write_manifest(data)
    with pytest.raises(ManifestSchemaError):
        validate_manifest_structure(tmp)


def test_invalid_outcome_rejected() -> None:
    """Invalid expected_outcome must fail."""
    data = dict(
        _VALID,
        scenarios=[
            {
                "scenario_id": "test",
                "fixture_revision": 1,
                "project_input_path": "projects/input.json",
                "document_refs": [],
                "required_stages": ["planning"],
                "expected_outcome": "not_a_real_outcome",
                "expected_path": "expected/out.json",
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
                "provenance": {"source": "test", "rationale": "test"},
            }
        ],
    )
    tmp = _write_manifest(data)
    with pytest.raises(ManifestSchemaError):
        validate_manifest_structure(tmp)


def test_invalid_stage_rejected() -> None:
    """Invalid required_stage must fail."""
    data = dict(
        _VALID,
        scenarios=[
            {
                "scenario_id": "test",
                "fixture_revision": 1,
                "project_input_path": "projects/input.json",
                "document_refs": [],
                "required_stages": ["not_a_stage"],
                "expected_outcome": "success",
                "expected_path": "expected/out.json",
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
                "provenance": {"source": "test", "rationale": "test"},
            }
        ],
    )
    tmp = _write_manifest(data)
    with pytest.raises(ManifestSchemaError):
        validate_manifest_structure(tmp)


def test_revision_zero_rejected() -> None:
    """suite_revision = 0 must fail (minimum 1)."""
    data = dict(_VALID, suite_revision=0)
    tmp = _write_manifest(data)
    with pytest.raises(ManifestSchemaError):
        validate_manifest_structure(tmp)


def test_invalid_kebab_case_id_rejected() -> None:
    """Invalid scenario_id format must fail."""
    data = dict(
        _VALID,
        scenarios=[
            {
                "scenario_id": "Bad ID with Spaces",
                "fixture_revision": 1,
                "project_input_path": "projects/input.json",
                "document_refs": [],
                "required_stages": ["planning"],
                "expected_outcome": "success",
                "expected_path": "expected/out.json",
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
                "provenance": {"source": "test", "rationale": "test"},
            }
        ],
    )
    tmp = _write_manifest(data)
    with pytest.raises(ManifestSchemaError):
        validate_manifest_structure(tmp)
