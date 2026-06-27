"""Tests for manifest loader (semantic validation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cold_storage.evaluation.errors import (
    ConflictingComparisonPathError,
    DecimalPolicyError,
    DuplicateComparisonPathError,
    DuplicateScenarioIdError,
    IgnorePolicyError,
    ManifestFileNotFoundError,
    ManifestJsonDecodeError,
    ManifestSchemaError,
    UnknownSchemaVersionError,
)
from cold_storage.evaluation.manifest import load_evaluation_manifest
from cold_storage.evaluation.models import EvaluationManifest

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


def _write_and_load(
    manifest: dict, tmp_path: Path, require_files: bool = False
) -> EvaluationManifest:
    """Write a manifest dict to a temp file and load it."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    result = load_evaluation_manifest(
        str(path),
        evaluation_root=tmp_path,
        require_referenced_files=require_files,
    )
    assert isinstance(result, EvaluationManifest)
    return result


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_loads_valid_manifest(tmp_path: Path) -> None:
    """Valid manifest loads and returns a typed model."""
    manifest = _write_and_load(_make_manifest(), tmp_path)
    assert manifest.schema_version == "1.0"
    assert manifest.suite_id == "cold-storage-pilot-v1"
    assert manifest.suite_revision == 1
    assert len(manifest.scenarios) == 1


def test_loads_valid_manifest_with_existing_files(tmp_path: Path) -> None:
    """With require_referenced_files=True, referenced files must exist."""
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "project-input.json").write_text("{}")
    (examples / "expected-output.json").write_text("{}")

    manifest = _write_and_load(_make_manifest(), tmp_path, require_files=True)
    assert manifest.schema_version == "1.0"


# ---------------------------------------------------------------------------
# JSON and file errors
# ---------------------------------------------------------------------------


def test_missing_manifest_file_rejected(tmp_path: Path) -> None:
    """Non-existent manifest file raises ManifestFileNotFoundError."""
    with pytest.raises(ManifestFileNotFoundError):
        load_evaluation_manifest(
            str(tmp_path / "nonexistent.json"),
            evaluation_root=tmp_path,
        )


def test_invalid_json_rejected(tmp_path: Path) -> None:
    """Non-JSON file raises ManifestJsonDecodeError."""
    path = tmp_path / "bad.json"
    path.write_text("not json")
    with pytest.raises(ManifestJsonDecodeError):
        load_evaluation_manifest(str(path), evaluation_root=tmp_path)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_unknown_schema_version_rejected(tmp_path: Path) -> None:
    """Unknown schema_version raises EVAL_SCHEMA_VERSION_UNSUPPORTED."""
    manifest = _make_manifest()
    manifest["schema_version"] = "9.9"
    with pytest.raises(UnknownSchemaVersionError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_SCHEMA_VERSION_UNSUPPORTED"


def test_unknown_root_field_rejected(tmp_path: Path) -> None:
    """Extra root field raises ManifestSchemaError."""
    manifest = _make_manifest()
    manifest["extra_field"] = "surprise"
    with pytest.raises(ManifestSchemaError):
        _write_and_load(manifest, tmp_path)


def test_unknown_nested_field_rejected(tmp_path: Path) -> None:
    """Extra nested field raises ManifestSchemaError."""
    scenario = dict(_VALID_SCENARIO)
    scenario["extra_nested"] = "nope"
    manifest = _make_manifest([scenario])
    with pytest.raises(ManifestSchemaError):
        _write_and_load(manifest, tmp_path)


def test_invalid_expected_outcome_rejected(tmp_path: Path) -> None:
    """Unknown expected_outcome raises ManifestSchemaError."""
    scenario = dict(_VALID_SCENARIO)
    scenario["expected_outcome"] = "magic_success"
    manifest = _make_manifest([scenario])
    with pytest.raises(ManifestSchemaError):
        _write_and_load(manifest, tmp_path)


def test_invalid_required_stage_rejected(tmp_path: Path) -> None:
    """Unknown required_stages value raises ManifestSchemaError."""
    scenario = dict(_VALID_SCENARIO)
    scenario["required_stages"] = ["non_existent_stage"]
    manifest = _make_manifest([scenario])
    with pytest.raises(ManifestSchemaError):
        _write_and_load(manifest, tmp_path)


def test_revision_zero_rejected(tmp_path: Path) -> None:
    """suite_revision = 0 raises ManifestSchemaError."""
    manifest = _make_manifest()
    manifest["suite_revision"] = 0
    with pytest.raises(ManifestSchemaError):
        _write_and_load(manifest, tmp_path)


def test_invalid_kebab_case_id_rejected(tmp_path: Path) -> None:
    """Non-kebab-case scenario_id raises ManifestSchemaError."""
    scenario = dict(_VALID_SCENARIO)
    scenario["scenario_id"] = "Bad_ID with spaces"
    manifest = _make_manifest([scenario])
    with pytest.raises(ManifestSchemaError):
        _write_and_load(manifest, tmp_path)


# ---------------------------------------------------------------------------
# Semantic validation
# ---------------------------------------------------------------------------


def test_duplicate_scenario_id_rejected(tmp_path: Path) -> None:
    """Duplicate scenario IDs fail with EVAL_SCENARIO_ID_DUPLICATE."""
    manifest = _make_manifest([_VALID_SCENARIO, _VALID_SCENARIO])
    with pytest.raises(DuplicateScenarioIdError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_SCENARIO_ID_DUPLICATE"


def test_duplicate_exact_path_rejected(tmp_path: Path) -> None:
    """Duplicate exact_path entries fail with EVAL_COMPARISON_PATH_DUPLICATE."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [
            {"path": "$.summary.requires_review"},
            {"path": "$.summary.requires_review"},
        ],
        "decimal_paths": [],
        "ignored_paths": [],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(DuplicateComparisonPathError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_COMPARISON_PATH_DUPLICATE"


def test_path_in_exact_and_decimal_rejected(tmp_path: Path) -> None:
    """Same path in exact and decimal must fail."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [{"path": "$.summary.total_area_m2"}],
        "decimal_paths": [
            {
                "path": "$.summary.total_area_m2",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "Testing conflict detection",
            }
        ],
        "ignored_paths": [],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(ConflictingComparisonPathError):
        _write_and_load(manifest, tmp_path)


def test_path_in_exact_and_ignored_rejected(tmp_path: Path) -> None:
    """Same path in exact and ignored must fail."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [{"path": "$.summary.requires_review"}],
        "decimal_paths": [],
        "ignored_paths": [
            {
                "path": "$.summary.requires_review",
                "reason": "Testing conflict detection",
            }
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(ConflictingComparisonPathError):
        _write_and_load(manifest, tmp_path)


def test_path_in_decimal_and_ignored_rejected(tmp_path: Path) -> None:
    """Same path in decimal and ignored must fail."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [
            {
                "path": "$.summary.total_area_m2",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "area",
            }
        ],
        "ignored_paths": [
            {
                "path": "$.summary.total_area_m2",
                "reason": "Testing conflict detection",
            }
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(ConflictingComparisonPathError):
        _write_and_load(manifest, tmp_path)


def test_ignored_rule_missing_reason_rejected(tmp_path: Path) -> None:
    """Ignored path without reason raises EVAL_IGNORE_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [{"path": "$.metadata.generated_at", "reason": ""}],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(IgnorePolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_IGNORE_POLICY_INVALID"


def test_decimal_rule_missing_unit_rejected(tmp_path: Path) -> None:
    """Decimal path without unit raises EVAL_DECIMAL_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [
            {
                "path": "$.summary.total_area_m2",
                "mode": "quantize",
                "scale": 2,
                "unit": "",
                "rationale": "Testing",
            }
        ],
        "ignored_paths": [],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(DecimalPolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_DECIMAL_POLICY_INVALID"


def test_decimal_rule_missing_rationale_rejected(tmp_path: Path) -> None:
    """Decimal path without rationale raises EVAL_DECIMAL_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [
            {
                "path": "$.summary.total_area_m2",
                "mode": "quantize",
                "scale": 2,
                "unit": "m2",
                "rationale": "",
            }
        ],
        "ignored_paths": [],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(DecimalPolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_DECIMAL_POLICY_INVALID"


def test_root_ignored_rejected(tmp_path: Path) -> None:
    """Ignoring root path must fail with EVAL_IGNORE_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [{"path": "$", "reason": "Testing root ignore rejection"}],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(IgnorePolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_IGNORE_POLICY_INVALID"


# ---------------------------------------------------------------------------
# Ignore rationale denylist
# ---------------------------------------------------------------------------


def test_placeholder_reason_dynamic(tmp_path: Path) -> None:
    """reason='dynamic' -> EVAL_IGNORE_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [
            {"path": "$.metadata.generated_at", "reason": "dynamic"}
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(IgnorePolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_IGNORE_POLICY_INVALID"


def test_placeholder_reason_ignore(tmp_path: Path) -> None:
    """reason='ignore' -> EVAL_IGNORE_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [
            {"path": "$.metadata.generated_at", "reason": "ignore"}
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(IgnorePolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_IGNORE_POLICY_INVALID"


def test_placeholder_reason_nondeterministic(tmp_path: Path) -> None:
    """reason='nondeterministic' -> EVAL_IGNORE_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [
            {"path": "$.metadata.generated_at", "reason": "nondeterministic"}
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(IgnorePolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_IGNORE_POLICY_INVALID"


def test_placeholder_reason_short(tmp_path: Path) -> None:
    """reason='short' (< 12 chars, single word) -> EVAL_IGNORE_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [
            {"path": "$.metadata.generated_at", "reason": "short"}
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(IgnorePolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_IGNORE_POLICY_INVALID"


def test_placeholder_reason_single_word(tmp_path: Path) -> None:
    """reason='testing' (single word) -> EVAL_IGNORE_POLICY_INVALID."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [
            {"path": "$.metadata.generated_at", "reason": "testing"}
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    with pytest.raises(IgnorePolicyError) as exc_info:
        _write_and_load(manifest, tmp_path)
    assert exc_info.value.code == "EVAL_IGNORE_POLICY_INVALID"


def test_good_rationale_passes(tmp_path: Path) -> None:
    """A meaningful multi-word reason passes validation."""
    scenario = dict(_VALID_SCENARIO)
    scenario["comparison_policy"] = {
        "exact_paths": [],
        "decimal_paths": [],
        "ignored_paths": [
            {
                "path": "$.metadata.generated_at",
                "reason": "UTC timestamp excluded for deterministic comparison",
            }
        ],
        "artifact_checks": [],
    }
    manifest = _make_manifest([scenario])
    result = _write_and_load(manifest, tmp_path)
    assert result is not None
