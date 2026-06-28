"""Tests for evaluation CLI."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

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
    """Run command must exit with appropriate code (Phase B implemented)."""
    # This test verifies the run command is no longer raising NotImplementedError.
    # Without a manifest path it should still error.
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")  # noqa: SIM115
    tmp.write("{}")
    tmp.close()
    rc = main(["--manifest", tmp.name, "run"])
    assert rc != 0  # Invalid manifest should fail


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


# ── P0-5: CLI malformed path tests ──────────────────────────────────────


@pytest.fixture
def _malformed_manifest(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Build a fully valid manifest with a malformed path at the given rule type.

    The fixture creates reference files at the expected paths so the manifest
    itself passes schema validation.  Only the comparison ``path`` value is
    malformed, isolating the defect under test.
    """
    rule_type: str = request.param[0]
    bad_value: object = request.param[1]

    # Create reference files at required paths
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    minimal_json = json.dumps({"key": "value"}, indent=2)
    (examples_dir / "project-input.json").write_text(minimal_json, "utf-8")
    (examples_dir / "expected-output.json").write_text(minimal_json, "utf-8")

    exact_paths: list[dict] = []
    decimal_paths: list[dict] = []
    ignored_paths: list[dict] = []

    if rule_type == "exact":
        exact_paths = [{"path": bad_value}]
    elif rule_type == "decimal":
        decimal_paths = [
            {
                "path": bad_value,
                "mode": "quantize",
                "scale": 2,
                "unit": "kW",
                "rationale": "fixed-scale numeric comparison for CLI regression",
            }
        ]
    elif rule_type == "ignored":
        ignored_paths = [
            {
                "path": bad_value,
                "reason": "runtime-generated value excluded from comparison",
            }
        ]

    manifest = {
        "schema_version": "1.0",
        "suite_id": "cli-malformed-path-test",
        "suite_revision": 1,
        "scenarios": [
            {
                "scenario_id": "malformed-path-case",
                "fixture_revision": 1,
                "project_input_path": "examples/project-input.json",
                "document_refs": [],
                "required_stages": ["planning"],
                "expected_outcome": "success",
                "expected_path": "examples/expected-output.json",
                "comparison_policy": {
                    "exact_paths": exact_paths,
                    "decimal_paths": decimal_paths,
                    "ignored_paths": ignored_paths,
                    "artifact_checks": [],
                },
                "provenance": {
                    "source": "repository-owned synthetic CLI regression fixture",
                    "rationale": "isolates malformed comparison path validation",
                },
            }
        ],
    }

    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2), "utf-8")
    return p


@pytest.fixture
def _control_manifest(tmp_path: Path) -> Path:
    """Build a fully valid manifest with a legal path for control tests."""
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    minimal_json = json.dumps({"key": "value"}, indent=2)
    (examples_dir / "project-input.json").write_text(minimal_json, "utf-8")
    (examples_dir / "expected-output.json").write_text(minimal_json, "utf-8")

    manifest = {
        "schema_version": "1.0",
        "suite_id": "cli-control-test",
        "suite_revision": 1,
        "scenarios": [
            {
                "scenario_id": "control-case",
                "fixture_revision": 1,
                "project_input_path": "examples/project-input.json",
                "document_refs": [],
                "required_stages": ["planning"],
                "expected_outcome": "success",
                "expected_path": "examples/expected-output.json",
                "comparison_policy": {
                    "exact_paths": [{"path": "$.value"}],
                    "decimal_paths": [],
                    "ignored_paths": [],
                    "artifact_checks": [],
                },
                "provenance": {
                    "source": "repository-owned synthetic CLI control fixture",
                    "rationale": "demonstrates that the fixture itself is valid",
                },
            }
        ],
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2), "utf-8")
    return p


@pytest.mark.parametrize(
    "_malformed_manifest",
    [
        ("exact", []),
        ("exact", {}),
        ("exact", None),
        ("exact", True),
        ("exact", 123),
        ("decimal", []),
        ("decimal", {}),
        ("decimal", None),
        ("decimal", True),
        ("decimal", 123),
        ("ignored", []),
        ("ignored", {}),
        ("ignored", None),
        ("ignored", True),
        ("ignored", 123),
    ],
    indirect=True,
)
def test_cli_malformed_path_rejected(_malformed_manifest: Path) -> None:
    """CLI must reject malformed comparison paths in all three rule types."""
    import io

    from cold_storage.evaluation.cli import main

    stderr = io.StringIO()
    old_stderr = sys.stderr
    try:
        sys.stderr = stderr
        rc = main(["--manifest", str(_malformed_manifest), "validate"])
    finally:
        sys.stderr = old_stderr
    assert rc != 0
    err_text = stderr.getvalue()
    assert "EVAL_SCHEMA_INVALID" in err_text, f"Got: {err_text}"
    assert "Traceback" not in err_text
    assert "TypeError" not in err_text
    assert "AttributeError" not in err_text
    assert "KeyError" not in err_text


def test_cli_control_manifest_accepted(_control_manifest: Path) -> None:
    """A fully valid manifest with a legal path must pass CLI validate (exit 0)."""
    from cold_storage.evaluation.cli import main

    rc = main(["--manifest", str(_control_manifest), "validate"])
    assert rc == 0, f"Control fixture should pass but got exit code {rc}"
