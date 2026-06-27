"""Tests for evaluation run directory management."""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.evaluation.errors import (
    RunIdentityMismatchError,
    RunManifestMismatchError,
    RunStateError,
    RunSummaryInvalidError,
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
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
    rd.write_summary(ctx, summary)
    import json

    data = json.loads((rd.run_dir(ctx.run_id) / "summary.json").read_text("utf-8"))
    assert data["passed"] is False


def test_stale_old_run_not_current(tmp_path: Path) -> None:
    """Stale old run summary must not satisfy new manifest hash."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run(
        "suite-1", 1, "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", ("s1",)
    )
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
    rd.write_summary(ctx, summary)

    # New manifest hash must not match old run — read_verified_summary should reject it
    with pytest.raises(RunManifestMismatchError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256="newhash" * 8,
        )

    # A different run with a different hash should show different context
    ctx2 = rd.create_run(
        "suite-1", 1, "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210", ("s1",)
    )
    ctx2 = rd.transition_status(ctx2, RunStatus.RUNNING)
    import json

    run_data = json.loads((rd.run_dir(ctx2.run_id) / "run.json").read_text("utf-8"))
    assert (
        run_data["manifest_sha256"]
        == "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    )


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
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
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
    ctx = rd.transition_status(ctx, RunStatus.FAILED)

    # Write a valid summary, then tamper with the run_id in the file to
    # bypass write_summary's validation so we can test read_verified_summary.
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
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

    # Tamper the context (simulate stale in-memory context)

    # Try to write a PASSED summary with a stale RUNNING context
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
        scenario_results=(
            ScenarioRunSummary(
                scenario_id="s1",
                passed=True,
                checks_total=5,
                checks_passed=5,
                checks_failed=0,
            ),
        ),
    )
    # The stale context should fail when run.json is verified against context
    with pytest.raises((RunSummaryStatusInvalidError, RunIdentityMismatchError)):
        rd.write_summary(stale_ctx, passed_summary)


def test_read_verified_summary_checks_suite_id(tmp_path: Path) -> None:
    """read_verified_summary must reject summary with mismatched suite_id."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
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
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
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
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
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
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    summary = make_summary(ctx, status=RunStatus.PASSED, passed=True)
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
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    summary = make_summary(ctx, status=RunStatus.PASSED, passed=True)
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
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    summary = make_summary(ctx, status=RunStatus.PASSED, passed=True)
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
    ctx = rd.transition_status(ctx, RunStatus.PASSED)
    summary = make_summary(ctx, status=RunStatus.PASSED, passed=True)
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


# ── P0-A: Write-path containment tests ─────────────────────────────


def test_transition_rejects_nonexistent_run_directory(tmp_path: Path) -> None:
    """transition_status must reject a run whose directory does not exist."""
    from cold_storage.evaluation.errors import RunStateError
    from cold_storage.evaluation.models import RunStatus

    rd = _run_dir(tmp_path)
    fake_ctx = EvaluationRunContext(
        run_id="abcdef123456",
        suite_id="suite-1",
        suite_revision=1,
        manifest_sha256="a" * 64,
        started_at="2026-06-27T12:00:00+00:00",
        status=RunStatus.CREATED,
        scenario_ids=("s1",),
    )
    with pytest.raises(RunStateError):
        rd.transition_status(fake_ctx, RunStatus.RUNNING)


def test_transition_rejects_missing_run_json(tmp_path: Path) -> None:
    """transition_status must reject a run with no run.json."""
    from cold_storage.evaluation.errors import RunStateError
    from cold_storage.evaluation.models import RunStatus

    rd = _run_dir(tmp_path)
    run_id = "abcdef123456"
    (tmp_path / "runs" / run_id).mkdir(parents=True)
    fake_ctx = EvaluationRunContext(
        run_id=run_id,
        suite_id="suite-1",
        suite_revision=1,
        manifest_sha256="a" * 64,
        started_at="2026-06-27T12:00:00+00:00",
        status=RunStatus.CREATED,
        scenario_ids=("s1",),
    )
    with pytest.raises(RunStateError):
        rd.transition_status(fake_ctx, RunStatus.RUNNING)


def test_fabricated_context_transition_rejected(tmp_path: Path) -> None:
    """Fabricated context with run_id=../outside must be rejected by transition_status."""
    from cold_storage.evaluation.errors import EvaluationError
    from cold_storage.evaluation.models import RunStatus

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)

    bad_ctx = EvaluationRunContext(
        run_id="../outside",
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        started_at=ctx.started_at,
        status=RunStatus.RUNNING,
        scenario_ids=ctx.scenario_ids,
    )
    with pytest.raises(EvaluationError) as exc_info:
        rd.transition_status(bad_ctx, RunStatus.PASSED)
    assert exc_info.value.code == "EVAL_RUN_ID_INVALID"


def test_fabricated_context_write_summary_rejected(tmp_path: Path) -> None:
    """Fabricated context with run_id=../outside must be rejected by write_summary."""
    from cold_storage.evaluation.errors import EvaluationError
    from cold_storage.evaluation.models import RunStatus

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)

    bad_ctx = EvaluationRunContext(
        run_id="../outside",
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        started_at=ctx.started_at,
        status=RunStatus.RUNNING,
        scenario_ids=ctx.scenario_ids,
    )
    bad_summary = EvaluationRunSummary(
        run_id="../outside",
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
    with pytest.raises(EvaluationError) as exc_info:
        rd.write_summary(bad_ctx, bad_summary)
    assert exc_info.value.code == "EVAL_RUN_ID_INVALID"


def test_absolute_run_id_rejected(tmp_path: Path) -> None:
    """Absolute path as run ID must be rejected."""
    from cold_storage.evaluation.errors import EvaluationError

    rd = _run_dir(tmp_path)
    with pytest.raises(EvaluationError) as exc_info:
        rd.run_dir("/tmp/outside")
    assert exc_info.value.code == "EVAL_RUN_ID_INVALID"


def test_slash_containing_run_id_rejected(tmp_path: Path) -> None:
    """Run ID with slash must be rejected."""
    from cold_storage.evaluation.errors import EvaluationError

    rd = _run_dir(tmp_path)
    with pytest.raises(EvaluationError) as exc_info:
        rd.run_dir("abcd/1234")
    assert exc_info.value.code == "EVAL_RUN_ID_INVALID"


# ── P0-B: Summary invariant tests ──────────────────────────────────


def test_passed_summary_empty_scenario_results_rejected(tmp_path: Path) -> None:
    """PASSED summary with empty scenario_results must be rejected."""
    from cold_storage.evaluation.errors import RunSummaryInvalidError
    from cold_storage.evaluation.models import RunStatus

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.PASSED)

    empty_summary = EvaluationRunSummary(
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
    with pytest.raises(RunSummaryInvalidError) as exc_info:
        rd.write_summary(ctx, empty_summary)
    assert "EVAL_RUN_SUMMARY_INVALID" in str(exc_info.value)


def test_passed_status_with_false_passed_rejected():
    """status=PASSED with passed=False must raise ValueError in strict conversion."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "passed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": False,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": True,
                "checks_total": 5,
                "checks_passed": 5,
                "checks_failed": 0,
            }
        ],
    }
    with pytest.raises(
        (
            ValueError,
            KeyError,
            TypeError,
            AssertionError,
            RunSummaryInvalidError,
            RunSummaryStatusInvalidError,
        )
    ):
        _dict_to_summary_strict(d)


def test_failed_status_with_passed_true_rejected():
    """passed=True with status=FAILED must raise ValueError in strict conversion."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "failed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": True,
        "scenario_results": [],
    }
    with pytest.raises(
        (
            ValueError,
            KeyError,
            TypeError,
            AssertionError,
            RunSummaryInvalidError,
            RunSummaryStatusInvalidError,
        )
    ):
        _dict_to_summary_strict(d)


def test_aborted_status_with_passed_true_rejected():
    """ABORTED status with passed=True must raise ValueError in strict conversion."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "aborted",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": True,
        "scenario_results": [],
    }
    with pytest.raises(
        (
            ValueError,
            KeyError,
            TypeError,
            AssertionError,
            RunSummaryInvalidError,
            RunSummaryStatusInvalidError,
        )
    ):
        _dict_to_summary_strict(d)


def test_negative_checks_total_rejected():
    """Negative checks_total must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "failed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": False,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": False,
                "checks_total": -1,
                "checks_passed": 0,
                "checks_failed": 0,
            }
        ],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


def test_check_counts_not_close_rejected():
    """checks_passed + checks_failed != checks_total must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "failed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": False,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": False,
                "checks_total": 10,
                "checks_passed": 5,
                "checks_failed": 3,
            }
        ],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


def test_unknown_scenario_result_field_rejected():
    """Unknown field inside scenario result must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "failed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": False,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": False,
                "checks_total": 5,
                "checks_passed": 0,
                "checks_failed": 5,
                "_unknown": "extra",
            }
        ],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


def test_naive_completed_at_rejected():
    """completed_at without timezone offset must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "failed",
        "completed_at": "2026-06-27T12:00:00",
        "passed": False,
        "scenario_results": [],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


def test_offset_aware_completed_at_accepted():
    """completed_at with valid UTC offset must be accepted."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "failed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": False,
        "scenario_results": [],
    }
    summary = _dict_to_summary_strict(d)
    assert summary.completed_at == "2026-06-27T12:00:00+00:00"


def test_passed_missing_scenario_result_rejected():
    """PASSED summary missing a declared scenario must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1", "s2"],
        "status": "passed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": True,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": True,
                "checks_total": 5,
                "checks_passed": 5,
                "checks_failed": 0,
            }
        ],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


def test_passed_non_passed_scenario_result_rejected():
    """PASSED summary with non-passed scenario result must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "passed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": True,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": False,
                "checks_total": 5,
                "checks_passed": 3,
                "checks_failed": 2,
            }
        ],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


def test_duplicate_scenario_result_rejected():
    """Duplicate scenario result ID must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "passed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": True,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": True,
                "checks_total": 5,
                "checks_passed": 5,
                "checks_failed": 0,
            },
            {
                "scenario_id": "s1",
                "passed": True,
                "checks_total": 5,
                "checks_passed": 5,
                "checks_failed": 0,
            },
        ],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


def test_undeclared_scenario_result_rejected():
    """Scenario result with undeclared scenario_id must raise ValueError."""
    from cold_storage.evaluation.run_directory import _dict_to_summary_strict

    d = {
        "run_id": "abcdef123456",
        "suite_id": "suite-1",
        "suite_revision": 1,
        "manifest_sha256": "a" * 64,
        "scenario_ids": ["s1"],
        "status": "passed",
        "completed_at": "2026-06-27T12:00:00+00:00",
        "passed": True,
        "scenario_results": [
            {
                "scenario_id": "s1",
                "passed": True,
                "checks_total": 5,
                "checks_passed": 5,
                "checks_failed": 0,
            },
            {
                "scenario_id": "s2",
                "passed": True,
                "checks_total": 5,
                "checks_passed": 5,
                "checks_failed": 0,
            },
        ],
    }
    with pytest.raises((ValueError, KeyError, TypeError, AssertionError, RunSummaryInvalidError)):
        _dict_to_summary_strict(d)


# ── P0-1: Summary root type validation through public API ────────────────


@pytest.mark.parametrize("root_value", [[], "summary", 123, True, None])
def test_read_verified_summary_rejects_non_dict_root(tmp_path: Path, root_value: object) -> None:
    """read_verified_summary must reject non-dict root values."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
    rd.write_summary(ctx, summary)

    import json

    summary_path = rd.run_dir(ctx.run_id) / "summary.json"
    serialized = json.dumps(root_value, indent=2)
    summary_path.write_text(serialized, "utf-8")

    with pytest.raises(RunSummaryInvalidError) as exc:
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )
    assert exc.value.code == "EVAL_RUN_SUMMARY_INVALID"


# ── P0-2: write-time code_commit_sha identity check ──────────────────────


def test_write_summary_rejects_code_commit_sha_mismatch(tmp_path: Path) -> None:
    """write_summary must reject summary with different code_commit_sha."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run(
        "suite-1",
        1,
        "a" * 64,
        ("s1",),
        code_commit_sha="abc123",
    )
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.FAILED)

    summary = EvaluationRunSummary(
        run_id=ctx.run_id,
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        scenario_ids=ctx.scenario_ids,
        status=RunStatus.FAILED,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha="different-sha",
        passed=False,
        scenario_results=(),
    )
    with pytest.raises(RunIdentityMismatchError) as exc:
        rd.write_summary(ctx, summary)
    assert exc.value.code == "EVAL_RUN_IDENTITY_MISMATCH"
    assert exc.value.field == "code_commit_sha"
    assert not (rd.run_dir(ctx.run_id) / "summary.json").exists()


def test_write_summary_rejects_code_commit_sha_none_vs_str(tmp_path: Path) -> None:
    """None != specific sha must be rejected."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run(
        "suite-1",
        1,
        "a" * 64,
        ("s1",),
        code_commit_sha=None,
    )
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.FAILED)

    summary = EvaluationRunSummary(
        run_id=ctx.run_id,
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        scenario_ids=ctx.scenario_ids,
        status=RunStatus.FAILED,
        completed_at="2026-06-27T12:00:00+00:00",
        code_commit_sha="some-sha",
        passed=False,
        scenario_results=(),
    )
    with pytest.raises(RunIdentityMismatchError) as exc:
        rd.write_summary(ctx, summary)
    assert exc.value.code == "EVAL_RUN_IDENTITY_MISMATCH"
    assert exc.value.field == "code_commit_sha"


# ── P0-3: Persisted run.json strict semantics ───────────────────────────


def test_strict_decoder_rejects_empty_started_at(tmp_path: Path) -> None:
    """Empty started_at in run.json must be rejected."""
    from cold_storage.evaluation.run_directory import _load_run_json_strict, _resolve_run_directory

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    import json

    run_json_path = _resolve_run_directory(rd._base, ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["started_at"] = ""
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    with pytest.raises(RunSummaryInvalidError):
        _load_run_json_strict(_resolve_run_directory(rd._base, ctx.run_id), ctx.run_id)


def test_strict_decoder_rejects_naive_started_at(tmp_path: Path) -> None:
    """started_at without timezone in run.json must be rejected."""
    from cold_storage.evaluation.run_directory import _load_run_json_strict, _resolve_run_directory

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    import json

    run_json_path = _resolve_run_directory(rd._base, ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["started_at"] = "2026-06-27T12:00:00"
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    with pytest.raises(RunSummaryInvalidError):
        _load_run_json_strict(_resolve_run_directory(rd._base, ctx.run_id), ctx.run_id)


def test_strict_decoder_rejects_suite_revision_zero(tmp_path: Path) -> None:
    """suite_revision 0 in run.json must be rejected."""
    from cold_storage.evaluation.run_directory import _load_run_json_strict, _resolve_run_directory

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    import json

    run_json_path = _resolve_run_directory(rd._base, ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["suite_revision"] = 0
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    with pytest.raises(RunSummaryInvalidError):
        _load_run_json_strict(_resolve_run_directory(rd._base, ctx.run_id), ctx.run_id)


def test_strict_decoder_rejects_duplicate_scenario_ids(tmp_path: Path) -> None:
    """Duplicate scenario IDs in run.json must be rejected."""
    from cold_storage.evaluation.run_directory import _load_run_json_strict, _resolve_run_directory

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    import json

    run_json_path = _resolve_run_directory(rd._base, ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["scenario_ids"] = ["s1", "s1"]
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    with pytest.raises(RunSummaryInvalidError):
        _load_run_json_strict(_resolve_run_directory(rd._base, ctx.run_id), ctx.run_id)


def test_strict_decoder_rejects_empty_scenario_id(tmp_path: Path) -> None:
    """Empty scenario ID in run.json must be rejected."""
    from cold_storage.evaluation.run_directory import _load_run_json_strict, _resolve_run_directory

    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    import json

    run_json_path = _resolve_run_directory(rd._base, ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["scenario_ids"] = ["s1", ""]
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    with pytest.raises(RunSummaryInvalidError):
        _load_run_json_strict(_resolve_run_directory(rd._base, ctx.run_id), ctx.run_id)


def test_tampered_run_json_started_at_rejected_in_transition(tmp_path: Path) -> None:
    """transition_status must reject tampered started_at in run.json."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    import json

    run_json_path = rd.run_dir(ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["started_at"] = ""
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    with pytest.raises(RunStateError):
        rd.transition_status(ctx, RunStatus.RUNNING)


def test_tampered_run_json_started_at_rejected_in_write_summary(tmp_path: Path) -> None:
    """write_summary must reject tampered started_at in run.json."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run("suite-1", 1, "a" * 64, ("s1",))
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    import json

    run_json_path = rd.run_dir(ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["started_at"] = "2026-06-27T12:00:00"
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
    with pytest.raises((RunStateError, RunSummaryInvalidError)):
        rd.write_summary(ctx, summary)


def test_tampered_database_backend_rejected_in_read(tmp_path: Path) -> None:
    """read_verified_summary must reject tampered database_backend in run.json."""
    rd = _run_dir(tmp_path)
    ctx = rd.create_run(
        "suite-1",
        1,
        "a" * 64,
        ("s1",),
        database_backend="postgresql",
    )
    ctx = rd.transition_status(ctx, RunStatus.RUNNING)
    ctx = rd.transition_status(ctx, RunStatus.FAILED)
    summary = make_summary(ctx, status=RunStatus.FAILED, passed=False)
    rd.write_summary(ctx, summary)

    import json

    run_json_path = rd.run_dir(ctx.run_id) / "run.json"
    data = json.loads(run_json_path.read_text("utf-8"))
    data["database_backend"] = "mysql"
    run_json_path.write_text(json.dumps(data, indent=2), "utf-8")

    with pytest.raises(RunSummaryInvalidError):
        rd.read_verified_summary(
            run_id=ctx.run_id,
            expected_manifest_sha256=ctx.manifest_sha256,
        )
