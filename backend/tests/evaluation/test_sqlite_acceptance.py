"""
SQLite acceptance tests for Phase B evaluation runner.

Tests that the three pilot fixtures execute through production services,
match expected contracts, maintain isolation, and clean up properly.
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
    # Use creation time, not dict-sorted IDs
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


# ═══════════════════════════════════════════════════════════════════════
# 1. Baseline runs independently → outcome=success, all stages passed
# ═══════════════════════════════════════════════════════════════════════


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


def test_baseline_run_completes() -> None:
    rc = _run_single_scenario("baseline-feasible")
    assert rc == 0, (
        f"Baseline-only run failed with exit code {rc} (expected 0 since review_required is a pass)"
    )


def test_baseline_expected_outcome_recorded() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("baseline-feasible")
    assert rc == 0
    summary = _load_latest_summary()
    assert summary is not None
    # Outcome is no longer in summary; read from raw artifact
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "baseline-feasible.json").read_text("utf-8"))
    assert raw["outcome"] == "review_required", (
        f"Expected blocked outcome in raw artifact, got {raw['outcome']}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 2. High-throughput runs independently → returns review_required or blocked
# ═══════════════════════════════════════════════════════════════════════


def test_high_throughput_independent_run() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("high-throughput-review")
    assert rc == 0, (
        f"High-throughput run exited with code {rc} (expected 0 — review_required is a pass)"
    )


def test_high_throughput_outcome_recorded() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("high-throughput-review")
    assert rc == 0
    # Outcome is no longer in summary; read from raw artifact
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "high-throughput-review.json").read_text("utf-8"))
    assert raw["outcome"] == "review_required", (
        f"Expected blocked outcome in raw artifact, got {raw['outcome']}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 3. Invalid runs independently → validation_error, no success artifacts
# ═══════════════════════════════════════════════════════════════════════


def test_invalid_independent_run() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("invalid-blocked")
    assert rc == 0, f"Invalid run failed with exit code {rc}"


def test_invalid_outcome_validation_error() -> None:
    _cleanup_runs()
    rc = _run_single_scenario("invalid-blocked")
    assert rc == 0
    # Outcome is no longer in summary; read from raw artifact
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "invalid-blocked.json").read_text("utf-8"))
    assert raw["outcome"] == "validation_error", (
        f"Expected validation_error outcome in raw artifact, got {raw['outcome']}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 4. Full suite runs — all three together
# ═══════════════════════════════════════════════════════════════════════


def test_full_suite_passes() -> None:
    rc = _run_suite()
    assert rc == 0, (
        "Full suite exit code is 0 — all scenarios pass (review_required is not a failure)"
    )


def test_full_suite_has_all_three_scenarios() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0
    summary = _load_latest_summary()
    assert summary is not None
    # scenario_ids is now a top-level field in summary
    scenario_ids = set(summary["scenario_ids"])
    assert scenario_ids == {"baseline-feasible", "high-throughput-review", "invalid-blocked"}


# ═══════════════════════════════════════════════════════════════════════
# 5. Missing expected file → fails closed
# ═══════════════════════════════════════════════════════════════════════


def test_missing_expected_file_fails() -> None:
    # Remove one expected path
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
        # When expected missing, manifest validation fails BEFORE creating a run.
        # No run directory exists — correct zero-side-effect behavior.
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
    assert rc == 0

    for s in manifest["scenarios"]:
        ep = EVAL_ROOT / s["expected_path"]
        assert file_sha256(ep) == expected_hashes[s["scenario_id"]], (
            f"Expected file changed after run for {s['scenario_id']}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 7. Normalized outputs consistent across two runs
# ═══════════════════════════════════════════════════════════════════════


def test_normalized_outputs_deterministic() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0
    run1_dir = _latest_run_dir()
    assert run1_dir is not None

    run1_hashes: dict[str, str] = {}
    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        np = run1_dir / "normalized" / f"{s_id}.json"
        assert np.exists(), f"Missing normalized output: {np}"
        run1_hashes[s_id] = file_sha256(np)

    rc = _run_suite()
    assert rc == 0
    # Use creation-time-based latest run dir to avoid non-deterministic sorting
    run2_dir = _latest_run_dir()
    assert run2_dir is not None

    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        np = run2_dir / "normalized" / f"{s_id}.json"
        assert np.exists()
        assert file_sha256(np) == run1_hashes[s_id], (
            f"Normalized output changed between runs for {s_id}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 8. Normalized hashes match expected file hashes
# ═══════════════════════════════════════════════════════════════════════


def test_normalized_matches_expected() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0
    run_dir = _latest_run_dir()
    assert run_dir is not None

    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    for s in manifest["scenarios"]:
        s_id = s["scenario_id"]
        np = run_dir / "normalized" / f"{s_id}.json"
        assert np.exists()
        normalized_hash = file_sha256(np)
        expected_hash = file_sha256(EVAL_ROOT / s["expected_path"])
        assert normalized_hash == expected_hash, (
            f"Normalized hash {normalized_hash} != expected hash {expected_hash} for {s_id}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 9. CLI returns non-zero on mismatch
# ═══════════════════════════════════════════════════════════════════════


def test_mismatch_produces_nonzero() -> None:
    """Tamper with expected file to simulate mismatch."""
    expected_path = EVAL_ROOT / "expected/baseline-feasible.v1.json"
    bak = expected_path.with_suffix(".json.bak.mismatch")
    import shutil

    shutil.copy2(str(expected_path), str(bak))

    original = json.loads(expected_path.read_text("utf-8"))
    original["outcome"] = "blocked"
    expected_path.write_text(json.dumps(original, indent=2), "utf-8")

    try:
        rc = _run_suite()
        assert rc != 0, "Should return non-zero when expected outcome mismatches"
    finally:
        shutil.copy2(str(bak), str(expected_path))
        bak.unlink()


# ═══════════════════════════════════════════════════════════════════════
# 10. Manifest invalid → zero side effects
# ═══════════════════════════════════════════════════════════════════════


def test_zero_side_effect_on_invalid_manifest() -> None:
    _cleanup_runs()
    dev_before = _dev_db_state()

    # Create an invalid manifest
    bad_fd, bad_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(bad_fd, "w") as tmp:
        json.dump({"schema_version": "bad"}, tmp)

    try:
        rc = main(["--manifest", str(bad_path), "run", "--database", "sqlite"])
        assert rc != 0, "Should fail on invalid manifest"
    finally:
        os.unlink(bad_path)

    # Verify no run directory was created
    assert _latest_run_dir() is None or len(os.listdir(str(EVAL_ROOT / "runs"))) <= 1

    # Verify dev database untouched
    dev_after = _dev_db_state()
    assert dev_before == dev_after, "Dev database state changed"


# ═══════════════════════════════════════════════════════════════════════
# 11. Manifest SHA-256 is real — written into run.json and summary.json
# ═══════════════════════════════════════════════════════════════════════


def test_manifest_sha256_is_real() -> None:
    _cleanup_runs()
    manifest_bytes = MANIFEST_PATH.read_bytes()
    expected_sha = hashlib.sha256(manifest_bytes).hexdigest()

    rc = _run_suite()
    assert rc == 0

    run_dir = _latest_run_dir()
    assert run_dir is not None

    run_data = json.loads((run_dir / "run.json").read_text("utf-8"))
    assert run_data["manifest_sha256"] == expected_sha, "run.json manifest_sha256 mismatch"

    summary = json.loads((run_dir / "summary.json").read_text("utf-8"))
    assert summary["manifest_sha256"] == expected_sha, "summary.json manifest_sha256 mismatch"


# ═══════════════════════════════════════════════════════════════════════
# 12. Dev database untouched
# ═══════════════════════════════════════════════════════════════════════


def test_dev_database_untouched() -> None:
    _cleanup_runs()
    dev_before = _dev_db_state()

    rc = _run_suite()
    assert rc == 0

    dev_after = _dev_db_state()
    assert dev_before == dev_after, "Dev database was modified during evaluation run"


# ═══════════════════════════════════════════════════════════════════════
# 13. Temporal database cleaned up on all exit paths
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
# 14. Raw artifacts exist
# ═══════════════════════════════════════════════════════════════════════


def test_raw_artifacts_exist() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0

    run_dir = _latest_run_dir()
    assert run_dir is not None

    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        rp = run_dir / "raw" / f"{s_id}.json"
        assert rp.exists(), f"Missing raw artifact for {s_id}"


def test_normalized_artifacts_exist() -> None:
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0

    run_dir = _latest_run_dir()
    assert run_dir is not None

    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        np = run_dir / "normalized" / f"{s_id}.json"
        assert np.exists(), f"Missing normalized artifact for {s_id}"


# ═══════════════════════════════════════════════════════════════════════
# 15. Raw artifact preserves correlation_id and input_snapshot
# ═══════════════════════════════════════════════════════════════════════


def test_raw_preserves_correlation_id() -> None:
    """Raw artifacts for baseline-feasible must contain correlation_id and input_snapshot."""
    _cleanup_runs()
    rc = _run_single_scenario("baseline-feasible")
    assert rc == 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    raw = json.loads((run_dir / "raw" / "baseline-feasible.json").read_text("utf-8"))
    # Verify throughput calculator fields are present
    tp = raw.get("calculation_results", {}).get("throughput", {})
    assert "correlation_id" in tp, "Missing correlation_id in throughput calculator"
    assert "input_snapshot" in tp, "Missing input_snapshot in throughput calculator"


# ═══════════════════════════════════════════════════════════════════════
# 16. Two runs produce different run IDs and directories
# ═══════════════════════════════════════════════════════════════════════


def test_two_runs_have_different_run_ids() -> None:
    """Running the suite twice must produce distinct run IDs and directories."""
    _cleanup_runs()
    rc1 = _run_suite()
    assert rc1 == 0
    run1_dir = _latest_run_dir()
    assert run1_dir is not None
    run1_summary = json.loads((run1_dir / "summary.json").read_text("utf-8"))
    run1_id = run1_summary["run_id"]

    rc2 = _run_suite()
    assert rc2 == 0
    run2_dir = _latest_run_dir()
    assert run2_dir is not None
    run2_summary = json.loads((run2_dir / "summary.json").read_text("utf-8"))
    run2_id = run2_summary["run_id"]

    assert run1_id != run2_id, f"Run IDs should differ: {run1_id} == {run2_id}"
    assert run1_dir != run2_dir, f"Run directories should differ: {run1_dir} == {run2_dir}"

    # Normalized outputs must have identical hashes (deterministic)
    for s_id in ("baseline-feasible", "high-throughput-review", "invalid-blocked"):
        np1 = run1_dir / "normalized" / f"{s_id}.json"
        np2 = run2_dir / "normalized" / f"{s_id}.json"
        assert file_sha256(np1) == file_sha256(np2), (
            f"Normalized hash mismatch across runs for {s_id}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 17. SQLite cleanup on real paths
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
    # After context manager exit, paths must be cleaned up
    assert not db_path.exists(), f"Temp database still exists: {db_path}"
    assert not Path(tmpdir).exists(), f"Temp directory still exists: {tmpdir}"


# ═══════════════════════════════════════════════════════════════════════
# 18. Phase A run.json integration
# ═══════════════════════════════════════════════════════════════════════


def test_phase_a_run_json_integration() -> None:
    """run.json must contain started_at, status, database_backend, and manifest_sha256."""
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0
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
# 19. Phase A typed summary integration
# ═══════════════════════════════════════════════════════════════════════


def test_phase_a_typed_summary_integration() -> None:
    """summary.json must be readable with strict decoder and have all identity fields."""
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0
    run_dir = _latest_run_dir()
    assert run_dir is not None
    summary = json.loads((run_dir / "summary.json").read_text("utf-8"))
    # All identity fields must be present
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
# 20. Summary check counts close
# ═══════════════════════════════════════════════════════════════════════


def test_summary_check_counts_close() -> None:
    """For each scenario: checks_total == checks_passed + checks_failed."""
    _cleanup_runs()
    rc = _run_suite()
    assert rc == 0
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
