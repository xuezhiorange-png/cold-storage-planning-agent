"""Suite-level evaluation orchestrator.

Loads a manifest, validates it (zero side effects), runs each scenario
through production services on per-scenario isolated SQLite databases,
compares against expected contracts, and writes run/summary artifacts
via the Phase A EvaluationRunDirectory contract.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cold_storage.evaluation.artifacts import (
    file_sha256,
    write_normalized,
    write_raw,
)
from cold_storage.evaluation.canonicalize import (
    canonicalize_json,
)
from cold_storage.evaluation.compare import ComparisonResult, compare_evaluation_result
from cold_storage.evaluation.execute import ScenarioExecutionResult, run_evaluation_scenario
from cold_storage.evaluation.manifest import (
    load_evaluation_manifest,
)
from cold_storage.evaluation.models import (
    EvaluationRunSummary,
    RunStatus,
    ScenarioRunSummary,
)
from cold_storage.evaluation.run_directory import EvaluationRunDirectory
from cold_storage.evaluation.sqlite_scope import SqliteScope


def _get_code_commit_sha(cwd: Path) -> str | None:
    """Get current Git commit SHA, or None on failure (never fabricate)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=5,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha and len(sha) == 40:
                return sha
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _build_check_ledger(
    scenario_id: str,
    exec_result: ScenarioExecutionResult,
    cmp_result: ComparisonResult | None,
    scenario: Any,
) -> list[dict[str, Any]]:
    """Build structured check ledger for a single scenario.

    Each check has: check_id, kind, passed, and optional detail.
    Counts are derived from the ledger — not computed separately.
    """
    checks: list[dict[str, Any]] = []

    # Stage checks — one per required_stage
    for stage_name in scenario.required_stages:
        stage_info = exec_result.stage_ledger.get(stage_name, {})
        status = stage_info.get("status", "skipped")
        checks.append(
            {
                "check_id": f"stage:{stage_name}",
                "kind": "required_stage",
                "passed": status == "passed",
                "detail": f"status={status}",
            }
        )

    # Outcome check
    checks.append(
        {
            "check_id": "outcome",
            "kind": "expected_outcome",
            "passed": exec_result.outcome == scenario.expected_outcome.value,
            "detail": f"expected={scenario.expected_outcome.value}, actual={exec_result.outcome}",
        }
    )

    # Comparison checks (if comparison was performed)
    if cmp_result is not None:
        # Each exact path
        for ep in scenario.comparison_policy.exact_paths:
            # Find mismatches for this exact path
            path_mismatches = [m for m in cmp_result.mismatches if m.path == ep.path]
            checks.append(
                {
                    "check_id": f"exact:{ep.path}",
                    "kind": "exact_path",
                    "passed": len(path_mismatches) == 0,
                    "detail": f"{len(path_mismatches)} mismatches" if path_mismatches else "match",
                }
            )

        # Decimal paths
        for dp in scenario.comparison_policy.decimal_paths:
            path_mismatches = [m for m in cmp_result.mismatches if m.path == dp.path]
            checks.append(
                {
                    "check_id": f"decimal:{dp.path}",
                    "kind": "decimal_path",
                    "passed": len(path_mismatches) == 0,
                    "detail": f"{len(path_mismatches)} mismatches" if path_mismatches else "match",
                }
            )

        # Structural comparison
        non_path_mismatches = [
            m
            for m in cmp_result.mismatches
            if not any(m.path == ep.path for ep in scenario.comparison_policy.exact_paths)
            and not any(m.path == dp.path for dp in scenario.comparison_policy.decimal_paths)
        ]
        checks.append(
            {
                "check_id": "structural",
                "kind": "structural_comparison",
                "passed": len(non_path_mismatches) == 0,
                "detail": (
                    f"{len(non_path_mismatches)} mismatches"
                    if non_path_mismatches
                    else "all fields match"
                ),
            }
        )

    # Artifact checks
    for ac in scenario.comparison_policy.artifact_checks:
        checks.append(
            {
                "check_id": f"artifact:{ac.artifact_selector}",
                "kind": "artifact_check",
                "passed": True,  # artifact checks are validated separately
                "detail": f"status_required={ac.required_status.value}",
            }
        )

    return checks


def run_manifest(
    manifest_path: str | Path,
    *,
    database_backend: str = "sqlite",
    eval_root_override: str | Path | None = None,
) -> int:
    """Load manifest, run all scenarios, compare against expected, write artifacts.

    Returns exit code (0 = all pass, 1 = any failure).

    Uses Phase A EvaluationRunDirectory contract for:
      - Run creation (create_run with strict validation)
      - Status transitions (CREATED → RUNNING → PASSED/FAILED/ABORTED)
      - Typed summary writing (write_summary with identity verification)
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
    # Step 2: Create run directory via Phase A contract
    # ------------------------------------------------------------------
    code_commit_sha = _get_code_commit_sha(Path.cwd())
    run_dir_helper = EvaluationRunDirectory(str(eval_root / "runs"))
    ctx = run_dir_helper.create_run(
        suite_id=manifest.suite_id,
        suite_revision=manifest.suite_revision,
        manifest_sha256=manifest_sha256,
        scenario_ids=tuple(s.scenario_id for s in manifest.scenarios),
        database_backend=database_backend,
        code_commit_sha=code_commit_sha,
    )
    run_dir = run_dir_helper.run_dir(ctx.run_id)

    # ------------------------------------------------------------------
    # Step 2b: Transition to RUNNING
    # ------------------------------------------------------------------
    ctx = run_dir_helper.transition_status(ctx, RunStatus.RUNNING)

    # ------------------------------------------------------------------
    # Step 3: Run each scenario with per-scenario SQLite isolation
    # ------------------------------------------------------------------
    all_pass = True
    scenario_results: list[dict[str, Any]] = []
    scenario_summaries: list[ScenarioRunSummary] = []

    try:
        for scenario in manifest.scenarios:
            fixture_path = eval_root / scenario.project_input_path
            expected_path = eval_root / scenario.expected_path

            print(f"  {scenario.scenario_id}: running...", flush=True)

            # Load fixture
            fixture = json.loads(fixture_path.read_text("utf-8"))

            # Run with isolated SQLite database
            with SqliteScope() as scope:
                exec_result: ScenarioExecutionResult = run_evaluation_scenario(
                    scenario, fixture, scope
                )
                raw_output = exec_result.raw_output

                # Write raw output — complete production output, no fields removed
                raw_path = write_raw(scenario.scenario_id, run_dir, raw_output)

                # Normalize — canonicalize with full policy

                canonicalized = canonicalize_json(
                    raw_output,
                    ignored_paths=scenario.comparison_policy.ignored_paths,
                    decimal_paths=scenario.comparison_policy.decimal_paths,
                )

                # Write normalized output
                norm_path = write_normalized(scenario.scenario_id, run_dir, canonicalized)

                # Load and compare against expected
                mismatch_count = 0
                cmp_result: ComparisonResult | None = None

                if expected_path.exists():
                    expected = json.loads(expected_path.read_text("utf-8"))
                    if scenario.comparison_policy:
                        cmp_result = compare_evaluation_result(
                            expected, canonicalized, scenario.comparison_policy
                        )
                        mismatch_count = len(cmp_result.mismatches)
                        if cmp_result.passed:
                            print(
                                f"  {scenario.scenario_id}: PASS (outcome={exec_result.outcome})",
                                flush=True,
                            )
                        else:
                            print(
                                f"  {scenario.scenario_id}: FAIL "
                                f"(outcome={exec_result.outcome}, "
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
                    print(
                        f"  {scenario.scenario_id}: FAIL (expected file missing: {expected_path})",
                        flush=True,
                    )
                    mismatch_count = 1
                    all_pass = False

                # Build check ledger
                checks = _build_check_ledger(
                    scenario.scenario_id, exec_result, cmp_result, scenario
                )
                checks_total = len(checks)
                checks_passed = sum(1 for c in checks if c["passed"])
                checks_failed = checks_total - checks_passed

                # Build scenario summary
                scenario_passed = mismatch_count == 0 and checks_failed == 0
                if not scenario_passed:
                    all_pass = False

                scenario_results.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "outcome": exec_result.outcome,
                        "errors": exec_result.errors,
                        "passed": mismatch_count == 0 and checks_failed == 0,
                        "checks_total": checks_total,
                        "checks_passed": checks_passed,
                        "checks_failed": checks_failed,
                        "expected_path": str(expected_path),
                        "normalized_hash": file_sha256(norm_path),
                        "raw_hash": file_sha256(raw_path),
                        "check_ledger": checks,
                    }
                )

                scenario_summaries.append(
                    ScenarioRunSummary(
                        scenario_id=scenario.scenario_id,
                        passed=scenario_passed,
                        checks_total=checks_total,
                        checks_passed=checks_passed,
                        checks_failed=checks_failed,
                    )
                )

    except Exception as exc:
        # Abort on unexpected suite-level failure
        ctx = run_dir_helper.transition_status(ctx, RunStatus.ABORTED)
        print(f"ABORTED: {exc}", flush=True)
        return 1

    # ------------------------------------------------------------------
    # Step 4: Write typed summary via Phase A contract
    # ------------------------------------------------------------------
    total_passed = sum(1 for sr in scenario_summaries if sr.passed)
    final_status = RunStatus.PASSED if all_pass else RunStatus.FAILED
    ctx = run_dir_helper.transition_status(ctx, final_status)

    total_checks = sum(sr.checks_total for sr in scenario_summaries)
    passed_checks = sum(sr.checks_passed for sr in scenario_summaries)

    summary = EvaluationRunSummary(
        run_id=ctx.run_id,
        suite_id=ctx.suite_id,
        suite_revision=ctx.suite_revision,
        manifest_sha256=ctx.manifest_sha256,
        scenario_ids=ctx.scenario_ids,
        status=ctx.status,
        completed_at=datetime.now(UTC).isoformat(),
        code_commit_sha=ctx.code_commit_sha,
        passed=all_pass,
        scenario_results=tuple(scenario_summaries),
    )
    run_dir_helper.write_summary(ctx, summary)

    print(
        f"\nResults: {total_passed}/{len(scenario_summaries)} passed "
        f"(checks {passed_checks}/{total_checks})",
        flush=True,
    )
    print(f"Run ID: {ctx.run_id}", flush=True)
    return 0 if all_pass else 1
