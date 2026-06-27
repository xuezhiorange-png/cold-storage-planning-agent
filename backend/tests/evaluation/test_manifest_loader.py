"""Tests for manifest loader (semantic validation)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from cold_storage.evaluation.errors import (
    ConflictingComparisonPathError,
    IgnorePolicyError,
    ManifestFileNotFoundError,
    ManifestJsonDecodeError,
    ManifestSchemaError,
)
from cold_storage.evaluation.manifest import load_evaluation_manifest

_EVAL_ROOT = Path.cwd().parent / "evaluation"
_VALID_SCENARIO = {
    "scenario_id": "baseline-feasible",
    "fixture_revision": 1,
    "project_input_path": "examples/project-input.json",
    "document_refs": [],
    "required_stages": ["planning"],
    "expected_outcome": "success",
    "expected_path": "examples/expected-output.json",
    "comparison_policy": {
        "exact_paths": [{"path": "$.summary.requires_review"}],
        "decimal_paths": [],
        "ignored_paths": [],
        "artifact_checks": [],
    },
    "provenance": {"source": "reviewed", "rationale": "baseline"},
}


def _make_manifest(scenarios: list | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "suite_id": "cold-storage-pilot-v1",
        "suite_revision": 1,
        "scenarios": scenarios or [_VALID_SCENARIO],
    }


def test_loads_valid_manifest() -> None:
    """Valid manifest with referenced files loads correctly."""
    manifest = load_evaluation_manifest(
        _EVAL_ROOT / "manifest.example.json",
        evaluation_root=_EVAL_ROOT,
    )
    assert manifest.schema_version == "1.0"
    assert len(manifest.scenarios) >= 1


def test_duplicate_scenario_id_rejected() -> None:
    """Duplicate scenario IDs must fail."""
    dup = dict(_VALID_SCENARIO)
    data = _make_manifest([dup, dict(dup, project_input_path="examples/project-input.json")])
    tmp = _write_json(data)
    with pytest.raises(ManifestSchemaError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_duplicate_exact_path_rejected() -> None:
    """Duplicate exact path in same scenario must fail."""
    data = _make_manifest(
        [
            {
                **_VALID_SCENARIO,
                "comparison_policy": {
                    "exact_paths": [
                        {"path": "$.summary.value"},
                        {"path": "$.summary.value"},
                    ],
                    "decimal_paths": [],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
            }
        ]
    )
    tmp = _write_json(data)
    with pytest.raises(ManifestSchemaError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_same_path_in_exact_and_ignored_rejected() -> None:
    """Same path in exact and ignored must fail."""
    data = _make_manifest(
        [
            {
                **_VALID_SCENARIO,
                "comparison_policy": {
                    "exact_paths": [{"path": "$.summary.value"}],
                    "decimal_paths": [],
                    "ignored_paths": [{"path": "$.summary.value", "reason": "test"}],
                    "artifact_checks": [],
                },
            }
        ]
    )
    tmp = _write_json(data)
    with pytest.raises(ConflictingComparisonPathError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_same_path_in_decimal_and_ignored_rejected() -> None:
    """Same path in decimal and ignored must fail."""
    data = _make_manifest(
        [
            {
                **_VALID_SCENARIO,
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [
                        {
                            "path": "$.summary.total_area_m2",
                            "mode": "quantize",
                            "scale": 2,
                            "unit": "m2",
                            "rationale": "test",
                        }
                    ],
                    "ignored_paths": [
                        {"path": "$.summary.total_area_m2", "reason": "test"},
                    ],
                    "artifact_checks": [],
                },
            }
        ]
    )
    tmp = _write_json(data)
    with pytest.raises(ConflictingComparisonPathError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_ignored_rule_missing_reason_rejected() -> None:
    """Ignored rule without reason must fail."""
    data = _make_manifest(
        [
            {
                **_VALID_SCENARIO,
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [],
                    "ignored_paths": [{"path": "$.metadata.generated_at"}],
                    "artifact_checks": [],
                },
            }
        ]
    )
    tmp = _write_json(data)
    with pytest.raises(ManifestSchemaError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_decimal_rule_missing_unit_rejected() -> None:
    """Decimal rule without unit must fail."""
    data = _make_manifest(
        [
            {
                **_VALID_SCENARIO,
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [
                        {
                            "path": "$.summary.total_area_m2",
                            "mode": "quantize",
                            "scale": 2,
                            "rationale": "test",
                        }
                    ],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
            }
        ]
    )
    tmp = _write_json(data)
    with pytest.raises(ManifestSchemaError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_decimal_rule_missing_rationale_rejected() -> None:
    """Decimal rule without rationale must fail."""
    data = _make_manifest(
        [
            {
                **_VALID_SCENARIO,
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [
                        {
                            "path": "$.summary.total_area_m2",
                            "mode": "quantize",
                            "scale": 2,
                            "unit": "m2",
                        }
                    ],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
            }
        ]
    )
    tmp = _write_json(data)
    with pytest.raises(ManifestSchemaError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_root_ignore_path_rejected() -> None:
    """Ignoring the root path '$' must fail."""
    data = _make_manifest(
        [
            {
                **_VALID_SCENARIO,
                "comparison_policy": {
                    "exact_paths": [],
                    "decimal_paths": [],
                    "ignored_paths": [{"path": "$", "reason": "test"}],
                    "artifact_checks": [],
                },
            }
        ]
    )
    tmp = _write_json(data)
    with pytest.raises(IgnorePolicyError, match="Cannot ignore the root path"):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_missing_manifest_rejected() -> None:
    """Non-existent manifest file must fail."""
    with pytest.raises(ManifestFileNotFoundError):
        load_evaluation_manifest("/nonexistent/manifest.json", evaluation_root=Path.cwd())


def test_invalid_json_rejected() -> None:
    """Invalid JSON file must fail."""
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_bytes(b"not json at all")
    with pytest.raises(ManifestJsonDecodeError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def test_unknown_schema_version_semantic() -> None:
    """Unknown schema version in semantic validation must fail."""
    data = dict(_make_manifest(), schema_version="3.0-beta")
    tmp = _write_json(data)
    with pytest.raises(ManifestSchemaError):
        load_evaluation_manifest(tmp, evaluation_root=_EVAL_ROOT, require_referenced_files=False)


def _write_json(data: dict) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(data), "utf-8")
    return tmp
