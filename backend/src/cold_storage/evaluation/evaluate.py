"""Suite-level evaluation orchestrator.

Loads a manifest, validates it (zero side effects), runs each scenario
through production services on per-scenario isolated SQLite databases,
compares against expected contracts, and writes run/summary artifacts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cold_storage.evaluation.artifacts import (
    file_sha256,
    write_normalized,
    write_raw,
    write_run_json,
    write_summary_json,
)
from cold_storage.evaluation.compare import ComparisonResult, compare_evaluation_result
from cold_storage.evaluation.execute import run_evaluation_scenario
from cold_storage.evaluation.manifest import (
    load_evaluation_manifest,
)
from cold_storage.evaluation.run_directory import EvaluationRunDirectory
from cold_storage.evaluation.sqlite_scope import SqliteScope


def _compute_check_counts(
    scenario_results: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Aggregate checks_total, checks_passed, checks_failed across scenarios."""
    total = 0
    passed = 0
    failed = 0
    for r in scenario_results:
        total += r.get("checks_total", 1)
        passed += r.get("checks_passed", 0)
        failed += r.get("checks_failed", 0)
    return total, passed, failed


def _build_stage_checks(scenario: dict[str, Any]) -> int:
    """Count how many checks a scenario contributes."""
    checks = 0
    stage_ledger = scenario.get("stage_ledger", {})
    for _stage_name, stage_info in stage_ledger.items():
        if stage_info.get("status") in ("passed", "failed"):
            checks += 1
    # outcome check
    checks += 1
    return max(checks, 1)


def run_manifest(
    manifest_path: str | Path,
    *,
    database_backend: str = "sqlite",
    eval_root_override: str | Path | None = None,
) -> int:
    """Load manifest, run all scenarios, compare against expected, write artifacts.

    Returns exit code (0 = all pass, 1 = any failure).

    Database lifecycle (per-scenario, not shared):
      - Each scenario creates its own temporary SQLite database via ``SqliteScope``.
      - The database is disposed and file deleted on every exit path.
      - No shared or persistent database.
    """
    manifest_path = Path(manifest_path)
    eval_root = Path(eval_root_override) if eval_root_override else manifest_path.parent

    # ------------------------------------------------------------------
    # Step 1: Full manifest validation (zero side effects)
    # ------------------------------------------------------------------
    print("Validating manifest...", flush=True)
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    manifest = load_evaluation_manifest(
        manifest_path,
        evaluation_root=eval_root,
        require_referenced_files=True,
    )

    # ------------------------------------------------------------------
    # Step 2: Create run directory
    # ------------------------------------------------------------------
    run_dir_helper = EvaluationRunDirectory(str(eval_root / "runs"))
    ctx = run_dir_helper.create_run(
        manifest.suite_id,
        manifest.suite_revision,
        manifest_sha256,
        tuple(s.scenario_id for s in manifest.scenarios),
    )
    run_dir = eval_root / "runs" / ctx.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write run.json
    run_data = {
        "run_id": ctx.run_id,
        "suite_id": ctx.suite_id,
        "suite_revision": ctx.suite_revision,
        "manifest_sha256": ctx.manifest_sha256,
        "code_commit_sha": ctx.code_commit_sha,
        "scenario_ids": [s.scenario_id for s in manifest.scenarios],
        "created_at": datetime.now(UTC).isoformat(),
    }
    write_run_json(run_dir, run_data)

    # ------------------------------------------------------------------
    # Step 3: Run each scenario with per-scenario SQLite isolation
    # ------------------------------------------------------------------
    all_pass = True
    scenario_results: list[dict[str, Any]] = []

    for scenario in manifest.scenarios:
        fixture_path = eval_root / scenario.project_input_path
        expected_path = eval_root / scenario.expected_path

        print(f"  {scenario.scenario_id}: running...", flush=True)

        # Load fixture
        fixture = json.loads(fixture_path.read_text("utf-8"))

        # Run with isolated SQLite database
        with SqliteScope() as scope:
            actual = run_evaluation_scenario(scenario, fixture, scope)
            # Also record raw output
            write_raw(scenario.scenario_id, run_dir, actual)

            # Normalize — apply comparison policy exclusions
            normalized = _normalize(actual, scenario)

            # Write normalized output
            norm_path = write_normalized(scenario.scenario_id, run_dir, normalized)

            # Load and compare against expected
            mismatch_count = 0
            check_count = _build_stage_checks(actual)

            if expected_path.exists():
                expected = json.loads(expected_path.read_text("utf-8"))
                if scenario.comparison_policy:
                    cmp_result: ComparisonResult = compare_evaluation_result(
                        expected, normalized, scenario.comparison_policy
                    )
                    mismatch_count = len(cmp_result.mismatches)
                    if cmp_result.passed:
                        print(
                            f"  {scenario.scenario_id}: PASS "
                            f"(outcome={actual.get('outcome', '?')})",
                            flush=True,
                        )
                    else:
                        print(
                            f"  {scenario.scenario_id}: FAIL "
                            f"(outcome={actual.get('outcome', '?')}, "
                            f"{mismatch_count} mismatches)",
                            flush=True,
                        )
                        for m in cmp_result.mismatches:
                            print(
                                f"    [{m.kind.value}] {m.path}: {m.message}",
                                flush=True,
                            )
                        all_pass = False
                else:
                    print(f"  {scenario.scenario_id}: NO COMPARISON POLICY", flush=True)
                    all_pass = False
                    mismatch_count = 1
            else:
                # P0-1: Missing expected file must fail closed
                print(
                    f"  {scenario.scenario_id}: FAIL (expected file missing: {expected_path})",
                    flush=True,
                )
                mismatch_count = 1
                all_pass = False

            # Build scenario summary entry
            checks_passed = max(0, check_count - mismatch_count)
            checks_failed = mismatch_count
            scenario_results.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "outcome": actual.get("outcome", "?"),
                    "errors": actual.get("errors", []),
                    "passed": mismatch_count == 0,
                    "checks_total": check_count,
                    "checks_passed": checks_passed,
                    "checks_failed": checks_failed,
                    "expected_path": str(expected_path),
                    "normalized_hash": file_sha256(norm_path),
                }
            )

    # Write summary.json
    total_checks, passed_checks, failed_checks = _compute_check_counts(scenario_results)
    final_status = "passed" if all_pass else "failed"

    summary = {
        "run_id": ctx.run_id,
        "suite_id": ctx.suite_id,
        "suite_revision": ctx.suite_revision,
        "manifest_sha256": manifest_sha256,
        "scenario_ids": [s.scenario_id for s in manifest.scenarios],
        "status": final_status,
        "passed": all_pass,
        "completed_at": datetime.now(UTC).isoformat(),
        "code_commit_sha": ctx.code_commit_sha,
        "checks_total": total_checks,
        "checks_passed": passed_checks,
        "checks_failed": failed_checks,
        "scenario_results": scenario_results,
    }
    write_summary_json(run_dir, summary)

    total_passed = sum(1 for r in scenario_results if r["passed"])
    print(
        f"\nResults: {total_passed}/{len(scenario_results)} passed "
        f"(checks {passed_checks}/{total_checks})",
        flush=True,
    )
    return 0 if all_pass else 1


def _normalize(actual: dict[str, Any], scenario: Any) -> dict[str, Any]:
    """Apply comparison policy exclusions to produce canonical normalized output.

    Removes ignored paths and applies decimal quantization.
    """
    import typing

    normalized: dict[str, Any] = typing.cast(
        dict[str, Any], json.loads(json.dumps(actual, sort_keys=True))
    )
    policy = scenario.comparison_policy
    if not policy:
        return normalized

    # Apply ignored paths
    for ignored in policy.ignored_paths:
        _remove_json_path(normalized, ignored.path)
    return normalized


def _remove_json_path(data: Any, path: str) -> None:
    """Remove a JSON path like '$.project.code' from nested dict data."""
    if not path.startswith("$."):
        return
    parts = path[2:].split(".")
    current = data
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            if isinstance(current, dict) and part in current:
                del current[part]
            break
        if isinstance(current, dict):
            current = current.get(part, {})
        else:
            break
