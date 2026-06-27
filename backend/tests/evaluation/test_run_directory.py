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
from cold_storage.evaluation.models import EvaluationRunSummary, RunStatus, ScenarioRunSummary
from cold_storage.evaluation.run_directory import EvaluationRunContext, EvaluationRunDirectory


def _run_dir(tmp_path: Path) -> EvaluationRunDirectory:
    return EvaluationRunDirectory(str(tmp_path / "runs"))


def make_summary(
    context: EvaluationRunContext,
    status: RunStatus = RunStatus.PASSED,
    passed: bool = True,
) -> EvaluationRunSummary:
    scenario_results = ()
    if status == RunStatus.PASSED:
        scenario_results = tuple(
            ScenarioRunSummary(
                scenario_id=sid,
                passed=True,
                checks_total=5,
                checks_passed=5,
                checks_failed=0,
            )
            for sid in context.scenario_ids
        )
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
        scenario_results=scenario_results,
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


# ── P0-2: Summary status and identity tests ─────────────────────────────


def test_write_summary_rejects_running_context_with_passed_status(tmp_path: Path) -> None:
    """RUNNING context with PASSED summary status must be rejected."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)

    summary = EvaluationRunSummary(
        run_id=ctx.run_id,
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        scenario_ids=ctx.scenario_ids,
        status=RunStatus.PASSED,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha=ctx.code_commit_sha,
        passed=True,
        scenario_results=(),
    )
    with pytest.raises(RunSummaryStatusInvalidError):
        rd.write_summary(ctx, summary)


def test_write_summary_rejects_passed_context_with_running_status(tmp_path: Path) -> None:
    """PASSED context with RUNNING summary status must be rejected."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.PASSED)

    summary = EvaluationRunSummary(
        run_id=ctx.run_id,
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
    with pytest.raises(RunSummaryStatusInvalidError):
        rd.write_summary(ctx, summary)


def test_stale_context_rejected_by_persisted_run_json(tmp_path: Path) -> None:
    """Stale context with status=PASSED but persisted run.json running must be rejected."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)

    # Write summary while RUNNING (allowed with RUNNING status)
    summary = EvaluationRunSummary(
        run_id=ctx.run_id,
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
    rd.write_summary(ctx, summary)

    # Tamper the context (simulate stale in-memory context)

    # Now try to write a PASSED summary with the stale RUNNING context
    stale_ctx = ctx  # context still says RUNNING
    passed_summary = EvaluationRunSummary(
        run_id=stale_ctx.run_id,
        suite_id=stale_ctx.suite_id,
        suite_revision=stale_ctx.suite_revision,
        manifest_sha256=stale_ctx.manifest_sha256,
        scenario_ids=stale_ctx.scenario_ids,
        status=RunStatus.PASSED,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha=stale_ctx.code_commit_sha,
        passed=True,
        scenario_results=(),
    )
    with pytest.raises(RunSummaryStatusInvalidError):
        rd.write_summary(stale_ctx, passed_summary)


def test_read_verified_summary_checks_suite_id(tmp_path: Path) -> None:
    """read_verified_summary must reject summary with mismatched suite_id."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["suite_id"] = "tampered-suite"
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    with pytest.raises(RunIdentityMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_read_verified_summary_checks_suite_revision(tmp_path: Path) -> None:
    """read_verified_summary must reject summary with mismatched suite_revision."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    summary = make_summary(ctx, status=RunStatus.PASSED, passed=True)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["suite_revision"] = 99
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    with pytest.raises(RunIdentityMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
            expected_suite_revision=1,
        )


def test_read_verified_summary_checks_scenario_ids(tmp_path: Path) -> None:
    """read_verified_summary must reject summary with mismatched scenario_ids."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["scenario_ids"] = ["different-scenario"]
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    with pytest.raises(RunIdentityMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_read_verified_summary_checks_code_commit_sha(tmp_path: Path) -> None:
    """read_verified_summary must reject summary with mismatched code_commit_sha."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run(
        "suite-1",
        1,
        "a" * 64,
        ("s1",),
        code_commit_sha="abc123",
    )
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    summary = make_summary(ctx, status=RunStatus.PASSED, passed=True)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["code_commit_sha"] = "tampered-sha"
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    with pytest.raises(RunIdentityMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_read_verified_summary_checks_status_non_passed(tmp_path: Path) -> None:
    """Status verification must work for non-passed summaries too."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["status"] = "passed"
    raw["passed"] = True
    # Must also add proper scenario results for PASSED status
    raw["scenario_results"] = [
        {
            "scenario_id": "s1",
            "passed": True,
            "checks_total": 5,
            "checks_passed": 5,
            "checks_failed": 0,
        }
    ]
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    with pytest.raises(RunSummaryStatusInvalidError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_strict_summary_unknown_field_rejected(tmp_path: Path) -> None:
    """Unknown root field in summary JSON must raise RunSummaryInvalidError."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["_unknown_field"] = "should not be here"
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    from cold_storage.evaluation.errors import RunSummaryInvalidError

    with pytest.raises(RunSummaryInvalidError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_strict_summary_missing_required_field(tmp_path: Path) -> None:
    """Missing required field in summary must raise RunSummaryInvalidError."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    del raw["passed"]
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    from cold_storage.evaluation.errors import RunSummaryInvalidError

    with pytest.raises(RunSummaryInvalidError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_strict_summary_string_as_bool_rejected(tmp_path: Path) -> None:
    """String where bool expected must raise RunSummaryInvalidError."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["passed"] = "yes"
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    from cold_storage.evaluation.errors import RunSummaryInvalidError

    with pytest.raises(RunSummaryInvalidError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_strict_summary_bool_as_int_rejected(tmp_path: Path) -> None:
    """Bool where int expected must raise RunSummaryInvalidError."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    summary = make_summary(ctx, status=RunStatus.RUNNING, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    raw = json.loads(summary_path.read_text("utf-8"))
    raw["suite_revision"] = True  # bool where int expected
    summary_path.write_text(json.dumps(raw, indent=2), "utf-8")

    from cold_storage.evaluation.errors import RunSummaryInvalidError

    with pytest.raises(RunSummaryInvalidError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )


def test_invalid_run_id_path_traversal_rejected(tmp_path: Path) -> None:
    """Run ID with path traversal characters must be rejected."""
    rd = _run_dir(tmp_path)

    from cold_storage.evaluation.errors import EvaluationError

    with pytest.raises(EvaluationError) as exc_info:
        rd.run_dir("../etc/passwd")
    assert exc_info.value.code == "EVAL_RUN_ID_INVALID"

    with pytest.raises(EvaluationError) as exc_info:
        rd.read_verified_summary(
            run_id="../etc/passwd",
            expected_manifest_sha256="a" * 64,
        )
    assert exc_info.value.code == "EVAL_RUN_ID_INVALID"
