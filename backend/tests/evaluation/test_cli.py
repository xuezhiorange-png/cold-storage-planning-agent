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
