"""Tests for evaluation run directory management."""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.evaluation.errors import (
    RunIdentityMismatchError,
    RunManifestMismatchError,
    RunStateError,
    RunSummaryStatusInvalidError,
)
from cold_storage.evaluation.models import EvaluationRunSummary, RunStatus
from cold_storage.evaluation.run_directory import EvaluationRunContext, EvaluationRunDirectory


def _run_dir(tmp_path: Path) -> EvaluationRunDirectory:
    return EvaluationRunDirectory(str(tmp_path / "runs"))


def make_summary(
    context: EvaluationRunContext,
    status: RunStatus = RunStatus.PASSED,
    passed: bool = True,
) -> EvaluationRunSummary:
    return EvaluationRunSummary(
        run_id=context.run_id,
        suite_id=context.suite_id,
        suite_revision=context.suite_revision,
        manifest_sha256=context.manifest_sha256,
        scenario_ids=context.scenario_ids,
        status=status,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha=context.code_commit_sha,
        passed=passed,
        scenario_results=(),
    )


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
    """Summary must be writable atomically with a typed summary object."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)
    import json

    data = json.loads((rd.run_dir(ctx.run_id) / "summary.json").read_text("utf-8"))
    assert data["passed"] is False


def test_stale_old_run_not_current(tmp_path: Path) -> None:
    """Stale old run summary must not satisfy new manifest hash."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "oldhash" * 8, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    # New manifest hash must not match old run — read_verified_summary should reject it
    with pytest.raises(RunManifestMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256="newhash" * 8,
        )

    # A different run with a different hash should show different context
    ctx2 = rd.create_run("suite-1", 1, "newhash" * 8, ("s1",))
    ctx2 = rd.transition_status(ctx2, RunStatus.RUNNING)
    import json

    run_data = json.loads((rd.run_dir(ctx2.run_id) / "run.json").read_text("utf-8"))
    assert run_data["manifest_sha256"] == "newhash" * 8


def test_write_summary_rejects_mismatched_run_id(tmp_path: Path) -> None:
    """write_summary must reject a summary whose run_id differs from context."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    bad_summary = EvaluationRunSummary(
        run_id="bogus-run-id",
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        scenario_ids=ctx.scenario_ids,
        status=RunStatus.RUNNING,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha=ctx.code_commit_sha,
        passed=False,
        scenario_results=(),
    )
    with pytest.raises(RunIdentityMismatchError):
        rd.write_summary(ctx, bad_summary)


def test_write_summary_rejects_mismatched_manifest_hash(tmp_path: Path) -> None:
    """write_summary must reject a summary whose manifest_sha256 differs from context."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    bad_summary = EvaluationRunSummary(
        run_id=ctx.run_id,
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256="b" * 64,
        scenario_ids=ctx.scenario_ids,
        status=RunStatus.RUNNING,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha=ctx.code_commit_sha,
        passed=False,
        scenario_results=(),
    )
    with pytest.raises(RunManifestMismatchError):
        rd.write_summary(ctx, bad_summary)


def test_write_summary_rejects_passed_with_running_status(tmp_path: Path) -> None:
    """write_summary must reject passed=True when status is not PASSED."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    bad_summary = make_summary(ctx, status=RunStatus.RUNNING, passed=True)
    with pytest.raises(RunSummaryStatusInvalidError):
        rd.write_summary(ctx, bad_summary)


def test_read_verified_summary_rejects_stale_manifest_hash(tmp_path: Path) -> None:
    """read_verified_summary must reject a summary with wrong manifest hash."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    with pytest.raises(RunManifestMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256="different" + "b" * 55,
        )


def test_read_verified_summary_validates_identity(tmp_path: Path) -> None:
    """read_verified_summary must reject a summary whose run_id doesn't match the directory."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)

    # Write a valid summary, then tamper with the run_id in the file to
    # bypass write_summary's validation so we can test read_verified_summary.
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["run_id"] = "tampered-run-id"
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    with pytest.raises(RunIdentityMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_code_commit_sha_persisted(tmp_path: Path) -> None:
    """code_commit_sha must be written to run.json if provided."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run(
        "suite-1",
        1,
        "a" * 64,
        ("s1",),
        code_commit_sha="abc123def456",
    )
    import json

    run_json = rd.run_dir(ctx.run_id) / "run.json"
    data = json.loads(run_json.read_text("utf-8"))
    assert data["code_commit_sha"] == "abc123def456"
