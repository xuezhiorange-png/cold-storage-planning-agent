"""Tests for evaluation CLI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cold_storage.evaluation.cli import main


def _make_manifest(data: dict) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(data), "utf-8")
    return tmp


_VALID_MANIFEST = {
    "schema_version": "1.0",
    "suite_id": "cold-storage-pilot-v1",
    "suite_revision": 1,
    "scenarios": [],
}


def test_validate_success_exit_zero() -> None:
    """Valid manifest with --manifest must exit 0."""
    tmp = _make_manifest(_VALID_MANIFEST)
    rc = main(["--manifest", str(tmp), "validate"])
    assert rc == 0


def test_schema_failure_nonzero() -> None:
    """Invalid manifest must exit non-zero."""
    data = dict(_VALID_MANIFEST, schema_version="bad")
    tmp = _make_manifest(data)
    rc = main(["--manifest", str(tmp), "validate"])
    assert rc != 0


def test_missing_file_nonzero() -> None:
    """Non-existent manifest must exit non-zero."""
    rc = main(["--manifest", "/nonexistent/manifest.json", "validate"])
    assert rc != 0


def test_inspect_output_json() -> None:
    """Inspect must output stable JSON."""
    tmp = _make_manifest(_VALID_MANIFEST)
    rc = main(["--manifest", str(tmp), "inspect"])
    assert rc == 0


def test_run_not_implemented() -> None:
    """Run command must exit non-zero in Phase A."""
    tmp = _make_manifest(_VALID_MANIFEST)
    rc = main(["--manifest", str(tmp), "run"])
    assert rc != 0


# ── P0-5: Stable error code tests via CLI ──────────────────────────────


def test_cli_unsupported_version_code(tmp_path: Path) -> None:
    """CLI validate with unsupported schema version must emit EVAL_SCHEMA_VERSION_UNSUPPORTED."""
    import io
    import sys

    data = dict(_VALID_MANIFEST, schema_version="42.0")
    tmp = _make_manifest(data)
    stderr = io.StringIO()
    old_stderr = sys.stderr
    try:
        sys.stderr = stderr
        rc = main(["--manifest", str(tmp), "validate"])
    finally:
        sys.stderr = old_stderr
    assert rc != 0
    assert "EVAL_SCHEMA_VERSION_UNSUPPORTED" in stderr.getvalue()


def test_cli_duplicate_scenario_code(tmp_path: Path) -> None:
    """CLI validate with duplicate scenario IDs must emit EVAL_SCENARIO_ID_DUPLICATE."""
    import io
    import sys

    scenario = {
        "scenario_id": "duplicate-id",
        "fixture_revision": 1,
        "project_input_path": "examples/project-input.json",
        "document_refs": [],
        "required_stages": ["planning"],
        "expected_outcome": "success",
        "expected_path": "examples/expected-output.json",
        "comparison_policy": {
            "exact_paths": [],
            "decimal_paths": [],
            "ignored_paths": [],
            "artifact_checks": [],
        },
        "provenance": {"source": "reviewed", "rationale": "baseline"},
    }
    data = dict(_VALID_MANIFEST)
    data["scenarios"] = [scenario, scenario]
    tmp = _make_manifest(data)
    stderr = io.StringIO()
    old_stderr = sys.stderr
    try:
        sys.stderr = stderr
        rc = main(["--manifest", str(tmp), "validate"])
    finally:
        sys.stderr = old_stderr
    assert rc != 0
    assert "EVAL_SCENARIO_ID_DUPLICATE" in stderr.getvalue()


def test_cli_duplicate_exact_path_code(tmp_path: Path) -> None:
    """CLI validate with duplicate exact paths must emit EVAL_COMPARISON_PATH_DUPLICATE."""
    import io
    import sys

    scenario = {
        "scenario_id": "scenario-1",
        "fixture_revision": 1,
        "project_input_path": "examples/project-input.json",
        "document_refs": [],
        "required_stages": ["planning"],
        "expected_outcome": "success",
        "expected_path": "examples/expected-output.json",
        "comparison_policy": {
            "exact_paths": [
                {"path": "$.duplicate"},
                {"path": "$.duplicate"},
            ],
            "decimal_paths": [],
            "ignored_paths": [],
            "artifact_checks": [],
        },
        "provenance": {"source": "reviewed", "rationale": "baseline"},
    }
    data = dict(_VALID_MANIFEST)
    data["scenarios"] = [scenario]
    tmp = _make_manifest(data)
    stderr = io.StringIO()
    old_stderr = sys.stderr
    try:
        sys.stderr = stderr
        rc = main(["--manifest", str(tmp), "validate"])
    finally:
        sys.stderr = old_stderr
    assert rc != 0
    assert "EVAL_COMPARISON_PATH_DUPLICATE" in stderr.getvalue()
