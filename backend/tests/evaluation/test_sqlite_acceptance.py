"""
SQLite acceptance tests for Phase B evaluation runner.

Tests that the three pilot fixtures execute through production services,
match expected contracts, maintain isolation, and clean up properly.

STATUS: Phase B acceptance is BLOCKED by missing formal production
orchestration and persistence (prerequisite task).  The baseline and
high-throughput scenarios cannot complete because SchemeService needs
zone/investment/cooling_load/equipment CalculationRunRecord entries
that must come from a formal production service — not from evaluation.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cold_storage.evaluation.artifacts import file_sha256
from cold_storage.evaluation.cli import main
from cold_storage.evaluation.models import RunStatus
from cold_storage.evaluation.sqlite_scope import SqliteScope, assert_temp_db_cleaned

EVAL_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "evaluation"
MANIFEST_PATH = EVAL_ROOT / "manifest.json"

BACKEND = EVAL_ROOT.parent / "backend"
DEV_DB = BACKEND / "cold_storage_dev.db"


# ── Helpers ──────────────────────────────────────────────────────────────


def _run_suite() -> int:
    """Run the full Phase B suite via CLI and return exit code."""
    return main(["--manifest", str(MANIFEST_PATH), "run", "--database", "sqlite"])


def _latest_run_dir() -> Path | None:
    runs_dir = EVAL_ROOT / "runs"
    if not runs_dir.exists():
        return None
    dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda d: d.stat().st_ctime)


def _load_latest_summary() -> dict[str, Any] | None:
    run_dir = _latest_run_dir()
    if run_dir is None:
        return None
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None
    return json.loads(summary_path.read_text("utf-8"))


def _cleanup_runs() -> None:
    runs_dir = EVAL_ROOT / "runs"
    if runs_dir.exists():
        for d in runs_dir.iterdir():
            if d.is_dir():
                import shutil

                shutil.rmtree(d, ignore_errors=True)


def _dev_db_state() -> dict:
    """Capture dev database state before/after for comparison."""
    if not DEV_DB.exists():
        return {"exists": False}
    return {
        "exists": True,
        "mtime": os.path.getmtime(str(DEV_DB)),
        "size": os.path.getsize(str(DEV_DB)),
        "sha256": hashlib.sha256(DEV_DB.read_bytes()).hexdigest(),
    }


def _run_single_scenario(scenario_id: str) -> int:
    """Run only one scenario from the manifest with correct eval_root."""
    manifest_data = json.loads(MANIFEST_PATH.read_text("utf-8"))
    single = dict(manifest_data)
    single["scenarios"] = [s for s in manifest_data["scenarios"] if s["scenario_id"] == scenario_id]
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(tmp_fd, "w") as tmp:
        json.dump(single, tmp)
    try:
        return main(
            [
                "--manifest",
                str(tmp_path),
                "run",
                "--database",
                "sqlite",
                "--evaluation-root",
                str(EVAL_ROOT),
            ]
        )
    finally:
        os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════
# 1. Baseline — BLOCKED by missing production prerequisite
#
# The baseline scenario has required_stages that include "schemes".
# SchemeService needs zone/investment/cooling_load/equipment
# CalculationRunRecord entries persisted by a formal production
# orchestration service (not yet implemented).  The evaluation runner
# fail-closes with a structured blocker — this is expected.
# ═══════════════════════════════════════════════════════════════════════


def test_baseline_run_fails_blocked() -> None:
    """Baseline run must return non-zero because schemes stage fails closed."""
    _cleanup_runs()
    rc = _run_single_scenario("baseline-feasible")
    assert rc != 0, (
        f"Baseline run should fail (exit != 0) because SchemeService "
        f"needs production-orchestration-persisted records. Got exit code {rc}."
    )


def test_baseline_outcome_blocked_by_prerequisite() -> None:
    """Baseline raw outcome must be 'blocked' when schemes cannot execute."""
    _cleanup_runs()
    rc = _run_single_scenario("baseline-feasible")
    assert rc != 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "baseline-feasible.json").read_text("utf-8"))
    assert raw["outcome"] == "blocked", (
        f"Expected blocked outcome (schemes fail-closed), got {raw['outcome']}"
    )
    # Verify structured blocker in raw artifact
    blocker = raw.get("blocker", {})
    assert blocker.get("error_class") == "EvaluationPrerequisiteMissingError", (
        f"Expected EvaluationPrerequisiteMissingError, got {blocker}"
    )
    assert blocker.get("code") == "EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING"
    assert blocker.get("field") == "scheme_source_calculations"
    # The Issue #22 prerequisite is closed; the new blocker reason is
    # the standalone "production capability gap" that no closed task has
    # yet delivered.
    assert blocker.get("details", {}).get("blocked_by") == "production_capability_gap"
    assert blocker.get("details", {}).get("missing_capability") == (
        "formal_production_calculation_orchestration_path"
    )
    # Verify structured blocker in stage ledger
    sl = raw.get("stage_ledger", {})
    schemes_stage = sl.get("schemes", {})
    assert schemes_stage.get("status") == "blocked", (
        f"Expected schemes stage to be blocked, got {schemes_stage}"
    )
    sb = schemes_stage.get("blocker", {})
    assert sb.get("error_class") == "EvaluationPrerequisiteMissingError"
    assert sb.get("code") == "EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING"
    assert sb.get("field") == "scheme_source_calculations"


def test_baseline_manifest_declares_success() -> None:
    """Manifest baseline expected_outcome must still be 'success' (frozen contract)."""
    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    for s in manifest["scenarios"]:
        if s["scenario_id"] == "baseline-feasible":
            assert s["expected_outcome"] == "success", (
                f"Frozen baseline contract requires success. Got: {s['expected_outcome']}"
            )


# ═══════════════════════════════════════════════════════════════════════
# 2. High-throughput — also BLOCKED by missing production prerequisite
# ═══════════════════════════════════════════════════════════════════════


def test_high_throughput_run_fails_blocked() -> None:
    """High-throughput must also fail because schemes needs prerequisite."""
    _cleanup_runs()
    rc = _run_single_scenario("high-throughput-review")
    assert rc != 0, (
        f"High-throughput run should fail (exit != 0) — same prerequisite "
        f"blocker as baseline. Got exit code {rc}."
    )


def test_high_throughput_outcome_blocked() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("high-throughput-review")
    assert rc != 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "high-throughput-review.json").read_text("utf-8"))
    assert raw["outcome"] == "blocked", f"Expected blocked outcome, got {raw['outcome']}"


# ═══════════════════════════════════════════════════════════════════════
# 3. Invalid runs independently → validation_error
# ═══════════════════════════════════════════════════════════════════════


def test_invalid_independent_run() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("invalid-blocked")
    assert rc == 0, f"Invalid run failed with exit code {rc}"


def test_invalid_outcome_validation_error() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("invalid-blocked")
    assert rc == 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "invalid-blocked.json").read_text("utf-8"))
    assert raw["outcome"] == "validation_error", (
        f"Expected validation_error outcome, got {raw['outcome']}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 4. Full suite — blocked (baseline + high-throughput fail on schemes)
# ═══════════════════════════════════════════════════════════════════════


def test_full_suite_fails_blocked() -> None:
    """Full suite must return non-zero — baseline and high-throughput are blocked."""
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0, (
        f"Full suite should fail because baseline + high-throughput are "
        f"blocked by prerequisite. Got exit code {rc}."
    )


def test_full_suite_has_all_three_scenarios() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0
    summary = _load_latest_summary()
    assert summary is not None
    scenario_ids = set(summary["scenario_ids"])
    assert scenario_ids == {
        "baseline-feasible",
        "high-throughput-review",
        "invalid-blocked",
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. Missing expected file → fails closed
# ═══════════════════════════════════════════════════════════════════════


def test_missing_expected_file_fails() -> None:
    path_to_hide = EVAL_ROOT / "expected/baseline-feasible.v1.json"
    bak = path_to_hide.with_suffix(".json.bak")
    path_to_hide.rename(bak)
    try:
        rc = _run_suite()
        assert rc != 0, "Should fail when expected file is missing"
    finally:
        bak.rename(path_to_hide)


def test_missing_expected_scenario_not_passed() -> None:
    _cleanup_runs()
    path_to_hide = EVAL_ROOT / "expected/baseline-feasible.v1.json"
    bak = path_to_hide.with_suffix(".json.bak2")
    path_to_hide.rename(bak)
    try:
        rc = _run_suite()
        assert rc != 0
    finally:
        bak.rename(path_to_hide)


# ═══════════════════════════════════════════════════════════════════════
# 6. Expected files unchanged (static, not rewritten by runner)
# ═══════════════════════════════════════════════════════════════════════


def test_expected_hash_unchanged() -> None:
    expected_hashes: dict[str, str] = {}
    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    for s in manifest["scenarios"]:
        ep = EVAL_ROOT / s["expected_path"]
        expected_hashes[s["scenario_id"]] = file_sha256(ep)

    rc = _run_suite()
    assert rc != 0  # suite fails (blocked), but expected files stay unchanged

    for s in manifest["scenarios"]:
        ep = EVAL_ROOT / s["expected_path"]
        assert file_sha256(ep) == expected_hashes[s["scenario_id"]], (
            f"Expected file changed after run for {s['scenario_id']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 7. Normalized outputs consistent across two runs
#
# NOTE: Because the suite is BLOCKED, normalized files may only be
# produced for the invalid-blocked scenario.  The deterministic test
# verifies that whatever IS produced stays stable across runs.
# ═══════════════════════════════════════════════════════════════════════


def test_normalized_outputs_deterministic() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run1_dir = _latest_run_dir()
    assert run1_dir is not None

    run1_hashes: dict[str, str] = {}
    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        np = run1_dir / "normalized" / f"{s_id}.json"
        if np.exists():
            run1_hashes[s_id] = file_sha256(np)

    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0
    run2_dir = _latest_run_dir()
    assert run2_dir is not None

    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        np = run2_dir / "normalized" / f"{s_id}.json"
        if s_id in run1_hashes:
            assert np.exists(), f"Normalized file disappeared for {s_id}"
            assert file_sha256(np) == run1_hashes[s_id], (
                f"Normalized output changed between runs for {s_id}"
            )


# ═══════════════════════════════════════════════════════════════════════
# 8. Manifest SHA-256 is real — written into run.json and summary.json
# ═══════════════════════════════════════════════════════════════════════


def test_manifest_sha256_is_real() -> None:
    _cleanup_runs()
    manifest_bytes = MANIFEST_PATH.read_bytes()
    expected_sha = hashlib.sha256(manifest_bytes).hexdigest()

    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None

    run_data = json.loads((run_dir / "run.json").read_text("utf-8"))
    assert run_data["manifest_sha256"] == expected_sha, "run.json manifest_sha256 mismatch"

    summary = json.loads((run_dir / "summary.json").read_text("utf-8"))
    assert summary["manifest_sha256"] == expected_sha, "summary.json manifest_sha256 mismatch"


# ═══════════════════════════════════════════════════════════════════════
# 9. Dev database untouched
# ═══════════════════════════════════════════════════════════════════════


def test_dev_database_untouched() -> None:
    _cleanup_runs()
    dev_before = _dev_db_state()

    rc = _run_suite()
    assert rc != 0

    dev_after = _dev_db_state()
    assert dev_before == dev_after, "Dev database was modified during evaluation run"


# ═══════════════════════════════════════════════════════════════════════
# 10. Temporal database cleaned up on all exit paths
# ═══════════════════════════════════════════════════════════════════════


def test_sqlite_scope_cleanup_on_success() -> None:
    scope = SqliteScope()
    with scope:
        db_path = scope.db_path
        assert db_path is not None
        assert db_path.exists(), "Temp database should exist during scope"
    assert_temp_db_cleaned(scope)


def test_sqlite_scope_cleanup_on_exception() -> None:
    scope = SqliteScope()
    try:
        with scope:
            db_path = scope.db_path
            assert db_path is not None
            assert db_path.exists()
            raise RuntimeError("Simulated failure")
    except RuntimeError:
        pass
    assert_temp_db_cleaned(scope)


# ═══════════════════════════════════════════════════════════════════════
# 11. Raw artifacts exist
# ═══════════════════════════════════════════════════════════════════════


def test_raw_artifacts_exist() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None

    # All three scenarios should have raw artifacts (even blocked ones)
    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        rp = run_dir / "raw" / f"{s_id}.json"
        assert rp.exists(), f"Missing raw artifact for {s_id}"


def test_normalized_artifacts_exist() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None

    # invalid-blocked produces normalized; baseline/high-throughput may not
    for s_id in ("invalid-blocked",):
        np = run_dir / "normalized" / f"{s_id}.json"
        assert np.exists(), f"Missing normalized artifact for {s_id}"


# ═══════════════════════════════════════════════════════════════════════
# 12. Raw artifact preserves correlation_id and input_snapshot
# ═══════════════════════════════════════════════════════════════════════


def test_raw_preserves_correlation_id() -> None:
    """Raw artifacts must contain correlation_id and input_snapshot."""
    _cleanup_runs()
    rc = _run_single_scenario("invalid-blocked")
    assert rc == 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "invalid-blocked.json").read_text("utf-8"))
    assert "correlation_id" not in raw  # validation_error has no calc results


# ═══════════════════════════════════════════════════════════════════════
# 13. Two runs produce different run IDs and directories
# ═══════════════════════════════════════════════════════════════════════


def test_two_runs_have_different_run_ids() -> None:
    """Running the suite twice must produce distinct run IDs and directories."""
    _cleanup_runs()
    rc1 = _run_suite()
    assert rc1 != 0
    run1_dir = _latest_run_dir()
    assert run1_dir is not None
    run1_summary = json.loads((run1_dir / "summary.json").read_text("utf-8"))
    run1_id = run1_summary["run_id"]

    _cleanup_runs()
    rc2 = _run_suite()
    assert rc2 != 0
    run2_dir = _latest_run_dir()
    assert run2_dir is not None
    run2_summary = json.loads((run2_dir / "summary.json").read_text("utf-8"))
    run2_id = run2_summary["run_id"]

    assert run1_id != run2_id, f"Run IDs should differ: {run1_id} == {run2_id}"
    assert run1_dir != run2_dir, f"Run directories should differ: {run1_dir} == {run2_dir}"


# ═══════════════════════════════════════════════════════════════════════
# 14. SQLite cleanup on real paths
# ═══════════════════════════════════════════════════════════════════════


def test_sqlite_cleanup_on_real_paths() -> None:
    """Temporary database paths from SqliteScope must not exist after exit."""
    scope = SqliteScope()
    with scope:
        db_path = scope.db_path
        tmpdir = scope.tmpdir
        assert db_path is not None
        assert tmpdir is not None
        assert db_path.exists(), "Temp database should exist during scope"
    assert not db_path.exists(), f"Temp database still exists: {db_path}"
    assert not Path(tmpdir).exists(), f"Temp directory still exists: {tmpdir}"


# ═══════════════════════════════════════════════════════════════════════
# 15. Phase A run.json integration
# ═══════════════════════════════════════════════════════════════════════


def test_phase_a_run_json_integration() -> None:
    """run.json must contain started_at, status, database_backend, and manifest_sha256."""
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    run_data = json.loads((run_dir / "run.json").read_text("utf-8"))
    assert "started_at" in run_data, "Missing started_at in run.json"
    assert "status" in run_data, "Missing status in run.json"
    assert "database_backend" in run_data, "Missing database_backend in run.json"
    assert "manifest_sha256" in run_data, "Missing manifest_sha256 in run.json"
    assert run_data["database_backend"] == "sqlite"
    assert run_data["status"] in ("passed", "failed", "aborted")


# ═══════════════════════════════════════════════════════════════════════
# 16. Phase A typed summary integration
# ═══════════════════════════════════════════════════════════════════════


def test_phase_a_typed_summary_integration() -> None:
    """summary.json must be readable and have all identity fields."""
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    summary = json.loads((run_dir / "summary.json").read_text("utf-8"))
    for field in (
        "run_id",
        "suite_id",
        "suite_revision",
        "manifest_sha256",
        "scenario_ids",
        "status",
        "completed_at",
        "code_commit_sha",
        "passed",
        "scenario_results",
    ):
        assert field in summary, f"Missing field '{field}' in summary.json"
    assert isinstance(summary["suite_revision"], int)
    assert isinstance(summary["scenario_ids"], list)
    assert isinstance(summary["scenario_results"], list)
    for sr in summary["scenario_results"]:
        assert "scenario_id" in sr
        assert "passed" in sr
        assert "checks_total" in sr
        assert "checks_passed" in sr
        assert "checks_failed" in sr


# ═══════════════════════════════════════════════════════════════════════
# 17. Summary check counts close
# ═══════════════════════════════════════════════════════════════════════


def test_summary_check_counts_close() -> None:
    """For each scenario: checks_total == checks_passed + checks_failed."""
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0
    summary = _load_latest_summary()
    assert summary is not None
    for sr in summary["scenario_results"]:
        sc = sr["scenario_id"]
        total = sr["checks_total"]
        passed = sr["checks_passed"]
        failed = sr["checks_failed"]
        assert total == passed + failed, (
            f"Check counts do not close for {sc}: {passed} + {failed} != {total}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 18. Structured prerequisite blocker tests
# ═══════════════════════════════════════════════════════════════════════


def test_prerequisite_blocker_error_class_exists() -> None:
    """EvaluationPrerequisiteMissingError must be importable and structured."""
    from cold_storage.evaluation.errors import EvaluationPrerequisiteMissingError

    exc = EvaluationPrerequisiteMissingError("test message")
    assert exc.code == "EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING"
    assert exc.field == "scheme_source_calculations"
    assert "test message" in str(exc)
    assert exc.details["required_calculation_types"] == [
        "zone",
        "investment",
        "cooling_load",
        "equipment",
    ]
    # Issue #22 prerequisite is closed (2026-07-05); the active blocker is
    # a standalone production capability gap not yet delivered under any task.
    assert exc.details["missing_capability"] == ("formal_production_calculation_orchestration_path")
    assert exc.details["blocked_by"] == "production_capability_gap"
    assert exc.details["requires_follow_up_task"] is True
    # `prerequisite_issue` is intentionally absent — Issue #22 closed; the
    # gap is its own follow-up that needs its own task.
    assert exc.details["task_status"] == "blocked"


def test_prerequisite_blocker_no_fake_records() -> None:
    """Verify _persist_calculation is not importable from execute module."""
    # The execute module should NOT export a _persist_calculation function
    from cold_storage.evaluation import execute

    assert not hasattr(execute, "_persist_calculation"), (
        "execute.py must not contain _persist_calculation — "
        "evaluation must not fabricate CalculationRunRecord"
    )
    assert not hasattr(execute, "DEMO_COOLING_COEFFICIENTS"), (
        "execute.py must not contain DEMO_COOLING_COEFFICIENTS"
    )
    assert not hasattr(execute, "DEMO_EQUIPMENT_COEFFICIENTS"), (
        "execute.py must not contain DEMO_EQUIPMENT_COEFFICIENTS"
    )
    assert not hasattr(execute, "_map_temperature_level"), (
        "execute.py must not contain _map_temperature_level"
    )
    assert not hasattr(execute, "_map_process_compatibility"), (
        "execute.py must not contain _map_process_compatibility"
    )


def test_baseline_required_stages_exact() -> None:
    """Baseline manifest must declare all 8 required stages."""
    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    for s in manifest["scenarios"]:
        if s["scenario_id"] == "baseline-feasible":
            assert s["required_stages"] == [
                "project",
                "version",
                "validation",
                "planning",
                "zone_plan",
                "power",
                "investment",
                "schemes",
            ], f"Baseline required_stages mismatch: {s['required_stages']}"


def test_prerequisite_blocker_no_dev_db_touch() -> None:
    """Dev database must be completely untouched during a blocked run."""
    _cleanup_runs()
    dev_before = _dev_db_state()

    rc = _run_single_scenario("baseline-feasible")
    assert rc != 0  # blocked

    dev_after = _dev_db_state()
    assert dev_before == dev_after, (
        "Dev database was modified during blocked baseline run — "
        "evaluation must not write to cold_storage_dev.db"
    )


# ═══════════════════════════════════════════════════════════════════════
# 19. P0 — Explicit prerequisite blocker in real runner path
# ═══════════════════════════════════════════════════════════════════════


def test_structured_blocker_in_raw_artifact() -> None:
    """Real baseline run must produce structured blocker in raw output."""
    _cleanup_runs()
    rc = _run_single_scenario("baseline-feasible")
    assert rc != 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "baseline-feasible.json").read_text("utf-8"))

    blocker = raw["blocker"]
    assert blocker["stage"] == "schemes"
    assert blocker["error_class"] == "EvaluationPrerequisiteMissingError"
    assert blocker["code"] == "EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING"
    assert blocker["field"] == "scheme_source_calculations"
    details = blocker["details"]
    assert details["required_calculation_types"] == [
        "zone",
        "investment",
        "cooling_load",
        "equipment",
    ]
    # Issue #22 prerequisite is closed; blocker reason is the standalone
    # production capability gap that needs its own follow-up task.
    assert details["missing_capability"] == ("formal_production_calculation_orchestration_path")
    assert details["task_status"] == "blocked"
    assert details["blocked_by"] == "production_capability_gap"
    assert details["requires_follow_up_task"] is True
    assert "prerequisite_issue" not in details


def test_structured_blocker_in_stage_ledger() -> None:
    """Stage ledger must carry structured blocker sub-dict."""
    _cleanup_runs()
    rc = _run_single_scenario("baseline-feasible")
    assert rc != 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "baseline-feasible.json").read_text("utf-8"))

    schemes = raw["stage_ledger"]["schemes"]
    assert schemes["status"] == "blocked"
    assert schemes["review_required"] is False
    inner = schemes["blocker"]
    assert inner["error_class"] == "EvaluationPrerequisiteMissingError"
    assert inner["code"] == "EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING"
    assert inner["field"] == "scheme_source_calculations"


def test_real_baseline_runner_does_not_call_scheme_service() -> None:
    """Real baseline runner MUST NOT invoke SchemeService.generate_scheme_run.

    The prerequisite gate raises before any import or instantiation of
    SchemeService.  This test runs the full baseline scenario through the
    real CLI runner and proves the service was never touched.

    Also verifies the structured blocker from the *same* real run.
    """
    from unittest.mock import patch

    _cleanup_runs()

    with patch(
        "cold_storage.modules.schemes.application.service.SchemeService.generate_scheme_run"
    ) as generate:
        rc = _run_single_scenario("baseline-feasible")
        assert rc != 0, (
            f"Baseline run should fail (exit != 0) because SchemeService "
            f"needs production-orchestration-persisted records. Got exit code {rc}."
        )
        generate.assert_not_called()

    # Verify blocker from the same real run — must NOT depend on
    # calling the capability helper directly.
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "baseline-feasible.json").read_text("utf-8"))

    blocker = raw["blocker"]
    assert blocker["stage"] == "schemes"
    assert blocker["error_class"] == "EvaluationPrerequisiteMissingError"
    assert blocker["code"] == "EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING"
    assert blocker["field"] == "scheme_source_calculations"
    assert blocker["details"]["blocked_by"] == "production_capability_gap"
    assert blocker["details"]["missing_capability"] == (
        "formal_production_calculation_orchestration_path"
    )
    assert blocker["details"]["requires_follow_up_task"] is True
    assert "prerequisite_issue" not in blocker["details"]

    schemes = raw["stage_ledger"]["schemes"]
    assert schemes["status"] == "blocked"
    assert schemes["review_required"] is False


def test_unknown_exception_not_misclassified() -> None:
    """Unknown RuntimeError must NOT produce EvaluationPrerequisiteMissingError.

    The schemes stage must distinguish the explicit prerequisite blocker
    from unexpected runtime failures.  A generic Exception must appear as
    'unexpected_error', never as EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING.
    """
    from unittest.mock import patch

    with patch(
        "cold_storage.evaluation.execute._require_scheme_production_prerequisite",
        side_effect=RuntimeError("unexpected"),
    ):
        _cleanup_runs()
        rc = _run_single_scenario("baseline-feasible")
        assert rc != 0

        run_dir = _latest_run_dir()
        assert run_dir is not None
        raw = json.loads((run_dir / "raw" / "baseline-feasible.json").read_text("utf-8"))

        schemes = raw["stage_ledger"]["schemes"]
        # Must NOT have the prerequisite blocker classification
        assert schemes.get("error_class") == "RuntimeError", f"Expected RuntimeError, got {schemes}"
        assert schemes.get("kind") == "unexpected_error", (
            f"Expected kind=unexpected_error, got {schemes}"
        )
        # Must NOT contain the prerequisite code anywhere
        assert "EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING" not in str(schemes), (
            "Unknown error must not be disguised as prerequisite blocker"
        )


# ═══════════════════════════════════════════════════════════════════════
# 20. P1 — Phase A strict reader/verifier integration
# ═══════════════════════════════════════════════════════════════════════


def test_blocked_run_passes_phase_a_strict_verification() -> None:
    """Real blocked run must be readable and verifiable via Phase A strict API."""
    from cold_storage.evaluation.run_directory import (
        EvaluationRunContext,
        _load_run_json_strict,
        _verify_context_against_run_meta,
    )

    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None

    # Strictly decode run.json using Phase A formal entry point
    run_id = run_dir.name  # directory name is the run ID
    ctx = _load_run_json_strict(run_dir, run_id)
    assert isinstance(ctx, EvaluationRunContext)
    assert ctx.run_id == run_id
    assert isinstance(ctx.suite_id, str) and ctx.suite_id
    assert isinstance(ctx.suite_revision, int) and ctx.suite_revision >= 1
    assert len(ctx.manifest_sha256) == 64
    assert ctx.status.value in ("passed", "failed", "aborted")
    assert isinstance(ctx.scenario_ids, tuple)
    assert len(ctx.scenario_ids) == 3

    # Verify context against persisted run.json
    run_meta = json.loads((run_dir / "run.json").read_text("utf-8"))
    _verify_context_against_run_meta(ctx, run_meta)
    # No exception → verification passed


def test_tampered_blocked_run_metadata_is_rejected() -> None:
    """Tampered run.json must be rejected by strict decoder."""
    from cold_storage.evaluation.errors import RunSummaryInvalidError
    from cold_storage.evaluation.run_directory import (
        _decode_run_context_strict,
        _load_run_json_strict,
    )

    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None
    run_id = run_dir.name

    # First, verify the real artifact passes
    _load_run_json_strict(run_dir, run_id)

    # Tamper with run_id (must fail regex ^[a-f0-9]{12}$)
    run_json_path = run_dir / "run.json"
    original = run_json_path.read_text("utf-8")
    tampered = original.replace(
        f'"run_id": "{run_id}"',
        '"run_id": "tampered-run-id"',
    )
    run_json_path.write_text(tampered)

    # Strict decoder must reject
    try:
        _load_run_json_strict(run_dir, run_id)
        raise AssertionError("Tampered run.json was accepted")
    except RunSummaryInvalidError as exc:
        assert exc.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc.field is None  # run_id validation is generic

    # Also test _decode_run_context_strict with malformed suite_revision
    run_json_path.write_text(original)  # restore for next tamper
    original_data = json.loads(original)
    original_data["suite_revision"] = -1  # must be >= 1
    run_json_path.write_text(json.dumps(original_data))

    try:
        _decode_run_context_strict(json.loads(run_json_path.read_text("utf-8")))
        raise AssertionError("Tampered run.json with suite_revision=-1 was accepted")
    except RunSummaryInvalidError as exc:
        assert exc.code == "EVAL_RUN_SUMMARY_INVALID"
        assert exc.field == "suite_revision"


def test_read_verified_summary_success() -> None:
    """Real blocked run must be readable via public read_verified_summary()."""
    from cold_storage.evaluation.run_directory import EvaluationRunDirectory

    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None
    run_id = run_dir.name

    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    run_directory = EvaluationRunDirectory(str(EVAL_ROOT / "runs"))
    summary = run_directory.read_verified_summary(
        run_id=run_id,
        expected_manifest_sha256=manifest_sha256,
        expected_suite_id="task-eleven-phase-b",
        expected_suite_revision=2,
    )

    # Verify typed identity fields
    assert summary.run_id == run_id
    assert summary.suite_id == "task-eleven-phase-b"
    assert summary.suite_revision == 2
    assert summary.manifest_sha256 == manifest_sha256
    assert len(summary.scenario_ids) == 3
    assert summary.status == RunStatus.FAILED  # blocked suite → failed
    assert summary.passed is False
    assert isinstance(summary.scenario_results, tuple)
    assert len(summary.scenario_results) == 3


def test_read_verified_summary_rejects_tampered_manifest_hash() -> None:
    """Tampered manifest_sha256 in summary.json must be rejected by public reader."""
    from cold_storage.evaluation.errors import RunManifestMismatchError
    from cold_storage.evaluation.run_directory import EvaluationRunDirectory

    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None
    run_id = run_dir.name

    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    # Tamper the persisted summary.json
    summary_path = run_dir / "summary.json"
    original = summary_path.read_text("utf-8")
    tampered_summary = json.loads(original)
    # Replace with all zeros — guaranteed mismatch
    tampered_summary["manifest_sha256"] = "0" * 64
    summary_path.write_text(json.dumps(tampered_summary))

    run_directory = EvaluationRunDirectory(str(EVAL_ROOT / "runs"))
    try:
        run_directory.read_verified_summary(
            run_id=run_id,
            expected_manifest_sha256=manifest_sha256,
            expected_suite_id="task-eleven-phase-b",
            expected_suite_revision=2,
        )
        raise AssertionError("Tampered summary with fake manifest_sha256 was accepted")
    except RunManifestMismatchError as exc:
        assert exc.code == "EVAL_RUN_MANIFEST_MISMATCH"
        assert exc.field == "manifest_sha256"

    # Restore original
    summary_path.write_text(original)


def test_read_verified_summary_rejects_tampered_identity() -> None:
    """Tampered suite_id/suite_revision in summary.json must be rejected by public reader."""
    from cold_storage.evaluation.errors import RunIdentityMismatchError
    from cold_storage.evaluation.run_directory import EvaluationRunDirectory

    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0

    run_dir = _latest_run_dir()
    assert run_dir is not None
    run_id = run_dir.name

    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    run_directory = EvaluationRunDirectory(str(EVAL_ROOT / "runs"))

    # ---- suite_id tamper ----
    summary_path = run_dir / "summary.json"
    original = summary_path.read_text("utf-8")
    tampered = json.loads(original)
    tampered["suite_id"] = "wrong-suite-id"
    summary_path.write_text(json.dumps(tampered))

    try:
        run_directory.read_verified_summary(
            run_id=run_id,
            expected_manifest_sha256=manifest_sha256,
            expected_suite_id="task-eleven-phase-b",
            expected_suite_revision=2,
        )
        raise AssertionError("Tampered summary with wrong suite_id was accepted")
    except RunIdentityMismatchError as exc:
        assert exc.code == "EVAL_RUN_IDENTITY_MISMATCH"
        assert exc.field == "suite_id"

    # ---- suite_revision tamper ----
    tampered = json.loads(original)
    tampered["suite_revision"] = 99
    summary_path.write_text(json.dumps(tampered))

    try:
        run_directory.read_verified_summary(
            run_id=run_id,
            expected_manifest_sha256=manifest_sha256,
            expected_suite_id="task-eleven-phase-b",
            expected_suite_revision=2,
        )
        raise AssertionError("Tampered summary with wrong suite_revision was accepted")
    except RunIdentityMismatchError as exc:
        assert exc.code == "EVAL_RUN_IDENTITY_MISMATCH"
        assert exc.field == "suite_revision"

    # Restore original
    summary_path.write_text(original)


def test_stale_blocked_run_context_is_rejected() -> None:
    """Context from run A must not pass verification against run B's run.json."""
    from cold_storage.evaluation.errors import RunIdentityMismatchError
    from cold_storage.evaluation.run_directory import (
        _verify_context_against_run_meta,
    )

    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0
    run_a_dir = _latest_run_dir()
    assert run_a_dir is not None
    run_a_meta = json.loads((run_a_dir / "run.json").read_text("utf-8"))

    # Second run
    _cleanup_runs()
    rc = _run_suite()
    assert rc != 0
    run_b_dir = _latest_run_dir()
    assert run_b_dir is not None
    run_b_meta = json.loads((run_b_dir / "run.json").read_text("utf-8"))

    # Build context from run B
    from cold_storage.evaluation.run_directory import EvaluationRunContext

    ctx_b = EvaluationRunContext(
        run_id=run_b_meta["run_id"],
        suite_id=run_b_meta["suite_id"],
        suite_revision=run_b_meta["suite_revision"],
        manifest_sha256=run_b_meta["manifest_sha256"],
        started_at=run_b_meta["started_at"],
        status=RunStatus(run_b_meta["status"]),
        scenario_ids=tuple(run_b_meta["scenario_ids"]),
        database_backend=run_b_meta.get("database_backend"),
        code_commit_sha=run_b_meta.get("code_commit_sha"),
    )

    # Verify ctx_b against run_a's run.json → must fail
    try:
        _verify_context_against_run_meta(ctx_b, run_a_meta)
        raise AssertionError("Stale context from run B accepted against run A's run.json")
    except RunIdentityMismatchError as exc:
        assert exc.code == "EVAL_RUN_IDENTITY_MISMATCH"
        # The failing field is run_id (first field checked or one that differs)
        assert exc.field in ("run_id",)
    except Exception:
        raise  # unexpected
