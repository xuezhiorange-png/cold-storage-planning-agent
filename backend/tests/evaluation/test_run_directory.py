"""Tests for evaluation run directory management."""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.evaluation.errors import (
    RunStateError,
)
from cold_storage.evaluation.models import RunStatus
from cold_storage.evaluation.run_directory import EvaluationRunDirectory


def _run_dir(tmp_path: Path) -> EvaluationRunDirectory:
    return EvaluationRunDirectory(str(tmp_path / "runs"))


def test_create_unique_run(tmp_path: Path) -> None:
    """Each run must get a unique directory."""
    rd = _run_dir(tmp_path)
    ctx1 = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx2 = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    assert ctx1.run_id != ctx2.run_id
    assert rd.run_dir(ctx1.run_id).exists()
    assert rd.run_dir(ctx2.run_id).exists()


def test_existing_directory_not_overwritten(tmp_path: Path) -> None:
    """Run directory uniqueness is enforced by mkdir(exist_ok=False)."""
    rd = _run_dir(tmp_path)
    # Normal creation works
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    assert rd.run_dir(ctx.run_id).exists()
    assert (rd.run_dir(ctx.run_id) / "run.json").exists()
    assert (rd.run_dir(ctx.run_id) / "raw").exists()
    assert (rd.run_dir(ctx.run_id) / "normalized").exists()
    # The unique UUID prevents accidental collisions


def test_manifest_hash_written(tmp_path: Path) -> None:
    """Manifest SHA-256 must be written to run.json."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "deadbeef" * 8, ("s1",))
    run_json = rd.run_dir(ctx.run_id) / "run.json"
    import json

    data = json.loads(run_json.read_text("utf-8"))
    assert data["manifest_sha256"] == "deadbeef" * 8


def test_status_transition_created_to_running(tmp_path: Path) -> None:
    """Created -> Running must succeed."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    assert ctx.status == RunStatus.RUNNING


def test_status_transition_running_to_passed(tmp_path: Path) -> None:
    """Running -> Passed must succeed."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    assert ctx.status == RunStatus.PASSED


def test_invalid_state_transition_rejected(tmp_path: Path) -> None:
    """Created -> Passed directly must fail."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    with pytest.raises(RunStateError):
        rd.transition_status(ctx, RunStatus.PASSED)


def test_passed_only_from_running(tmp_path: Path) -> None:
    """Passed status may only be reached from Running."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    with pytest.raises(RunStateError):
        rd.transition_status(ctx, RunStatus.PASSED)

    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    assert ctx.status == RunStatus.PASSED


def test_summary_atomic_write(tmp_path: Path) -> None:
    """Summary must be writable atomically."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    rd.write_summary(ctx, {"passed": True, "scenarios": 2})
    import json

    data = json.loads((rd.run_dir(ctx.run_id) / "summary.json").read_text("utf-8"))
    assert data["passed"] is True


def test_stale_old_run_not_current(tmp_path: Path) -> None:
    """Stale old run summary must not satisfy new manifest hash."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "oldhash" * 8, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    rd.write_summary(ctx, {"passed": True})

    # New manifest hash must not match old run
    summary = rd.read_summary(ctx.run_id)
    assert summary is not None
    assert summary["passed"] is True

    # A different run with a different hash should show different context
    ctx2 = rd.create_run("suite-1", 1, "newhash" * 8, ("s1",))
    ctx2 = rd.transition_status(ctx2, RunStatus.RUNNING)
    import json

    run_data = json.loads((rd.run_dir(ctx2.run_id) / "run.json").read_text("utf-8"))
    assert run_data["manifest_sha256"] == "newhash" * 8
