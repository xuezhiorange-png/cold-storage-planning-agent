"""One fixed R7 MAIN, only after separate Owner confirmation and preissued Grant."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from run_stage_b_fair_pool import fair_binding
from run_stage_b_feasibility_first_main import export_evidence as export_base_evidence
from run_stage_b_functional_shape_ab import committed_source, runtime_dependencies
from run_stage_b_guided_fair_pool import _github_admission, _pr_identity
from run_stage_b_owner_pool import dump, server_inputs
from run_stage_b_r5_main import quality_evidence
from run_stage_b_r6_main import work_evidence as original_work_evidence

from cold_storage.bootstrap.stage_b_r7_main import approved_r7_main_store
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.global_multi_solution_pool import (
    generate_multi_solution_pool,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    COMPARISON_POLICY as NINE_METRIC_POLICY,
)
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
    StageBFirstFeasibleRecoveryFairSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_r7_main_execution import (
    CI_IDENTITY,
    COMPARISON_POLICY,
    CONTRACT,
    REFERENCE_HEAD,
    TASK,
    R7MainLease,
    main_binding,
    owner_execution_digest,
)

OWNER_SCOPE_PATH = "docs/tasks/V2_2_2-stage-b-r7-owner-scope.txt"


def github_admission(repo: Path) -> dict[str, Any]:
    return _github_admission(
        repo,
        pr_number=CI_IDENTITY["pr_number"],
        base_ref=CI_IDENTITY["base_ref"],
        base_sha=CI_IDENTITY["base_sha"],
        head_ref=CI_IDENTITY["head_ref"],
        reference_head=REFERENCE_HEAD,
        required_jobs=frozenset(CI_IDENTITY["required_jobs"]),
    )


def server_binding(repo: Path) -> tuple[Any, Any, Any, dict[str, Any], dict[str, Any]]:
    """Read the fixed server inputs and source/runtime binding; no approval or Claim."""
    plan, p1, site = server_inputs(repo)
    dependencies = runtime_dependencies()
    common = fair_binding(repo, plan, p1, site)
    tracked = subprocess.check_output(
        ["git", "ls-files", "backend/src", "backend/scripts", OWNER_SCOPE_PATH],
        cwd=repo,
        text=True,
    ).splitlines()
    common["source_files"].update(
        {str(repo / n): hashlib.sha256((repo / n).read_bytes()).hexdigest() for n in tracked}
    )
    common["runtime_dependency_hash"] = canonical_hash(dependencies)
    binding = main_binding(common)
    return plan, p1, site, dependencies, binding


def work_evidence(lease: Any) -> dict[str, Any]:
    report = original_work_evidence(lease)
    deferred: dict[str, int] = {}
    for name in (
        "R6_FRONTAGE_REFERENCE_READ",
        "R6_FRONTAGE_STRATEGY_WRITE",
        "R7_DEFERRED_STRATEGY_REORDER",
    ):
        for group in report["groups"].values():
            if name in group["labels"]:
                deferred[name] = group["labels"].pop(name)
                group["work"] = sum(group["labels"].values())
    report["groups"]["deferred_frontage"] = dict(work=sum(deferred.values()), labels=deferred)
    return report


def search_recovery_evidence(
    output: Path, lease: Any, index: list[dict[str, Any]]
) -> dict[str, Any]:
    """Read durable baseline audit checkpoints; never invent first-witness timing."""
    events = lease.record.get("enumeration_events", [])
    exported = {r["candidate_hash"]: r for r in index}
    journal = output / "journal.jsonl"
    checkpoints = (
        [json.loads(s) for s in journal.read_text().splitlines()] if journal.is_file() else []
    )
    baselines = []
    for event in events:
        if (
            event.get("kind") != "FEASIBILITY_FIRST_QUALITY_FACTS"
            or event.get("status") != "BASE_VALID_CANDIDATE_PRESERVED"
        ):
            continue
        baseline = event["baseline"]
        row = exported.get(baseline["candidate_hash"])
        if row is None:
            continue
        if (
            row.get("search_stage") != "FEASIBILITY_FIRST"
            or row["source_composition_hash"] != baseline["composition_hash"]
            or row["geometry_hash"] != baseline["geometry_hash"]
        ):
            raise LayoutAuthorityError("R7_BASELINE_EXPORT_IDENTITY_MISMATCH")
        sequence = event.get("sequence")
        found = [
            c
            for c in checkpoints
            if type(sequence) is int
            and c.get("phase") == "STAGE_B_ENUMERATION_AUDIT_RECORDED"
            and c.get("snapshot", {})
            .get("resource_events", {})
            .get("STAGE_B_ENUMERATION_AUDIT_RECORD")
            == sequence
        ]
        totals = found[0]["totals"] if len(found) == 1 else {}
        baselines.append(
            dict(
                candidate_hash=baseline["candidate_hash"],
                geometry_hash=baseline["geometry_hash"],
                composition_hash=baseline["composition_hash"],
                sequence=sequence,
                measurement_point="INDEPENDENTLY_ACCEPTED_BASELINE_PERSISTENCE_AUDIT",
                native_seconds=totals.get("native_solver_seconds", "NOT_EVALUATED"),
                observable_work=totals.get("observable_work", "NOT_EVALUATED"),
                elapsed_seconds=totals.get("elapsed_seconds", "NOT_EVALUATED"),
                checkpoint_matches=len(found),
                resources=totals
                if len(found) == 1
                else "NOT_EVALUATED_MISSING_OR_AMBIGUOUS_JOURNAL",
            )
        )
    return dict(
        task=TASK,
        first_stage_search_recovered=bool(baselines),
        first_valid_baseline=baselines[0] if baselines else "NOT_EVALUATED_NO_VALID_BASELINE",
        per_handoff_baselines=baselines,
        second_stage_started_count=sum(e["kind"] == "BOUNDED_IMPROVEMENT_STARTED" for e in events),
        first_stage_frontage_event_count=sum(
            e["kind"] == "FINAL_MODEL_SEARCH_APPLIED" for e in events
        ),
        search_recovery_is_layout_quality_improvement=False,
        overall_layout_quality_improved="NOT_ESTABLISHED",
        truck="BLOCKED_PROJECT_INPUT",
        p2d_full_pass=False,
    )


def export_r7_evidence(
    output: Path, result: Any, lease: Any, site: Any, ids: set[str], binding: Any
) -> None:
    export_base_evidence(output, result, lease, site, ids, task=TASK)
    index = json.loads((output / "candidate-index.json").read_text())
    candidates = [
        json.loads((output / Path(row["svg"]).parent / "candidate.json").read_text())
        for row in index
    ]
    events = lease.record.get("enumeration_events", [])
    facts = quality_evidence(
        candidates, binding, events
    )  # Unchanged R5 physical facts / strict order.
    dump(output / "area-quality-comparison.json", facts)
    dump(
        output / "topology-rejections.json",
        [e for e in events if e.get("kind") == "TOPOLOGY_REJECTED_WITNESS_CUT"],
    )
    dump(
        output / "r7-search-feedback.json",
        [
            e
            for e in events
            if e.get("kind")
            in {
                "FINAL_MODEL_SEARCH_APPLIED",
                "FINAL_MODEL_GUIDANCE_APPLIED",
                "BOUNDED_IMPROVEMENT_STARTED",
                "VALIDATED_SEARCH_FRONTIER_UPDATED",
                "VALIDATED_QUALITY_HINT_UPDATED",
                "FEASIBILITY_FIRST_QUALITY_FACTS",
            }
        ],
    )
    dump(output / "work-breakdown.json", work_evidence(lease))
    recovery = search_recovery_evidence(output, lease, index)
    dump(output / "search-recovery.json", recovery)
    summary = json.loads((output / "execution-summary.json").read_text())
    summary.update(
        first_stage_search_recovered=recovery["first_stage_search_recovered"],
        first_valid_baseline_resources=recovery["first_valid_baseline"],
        comparison_policy=COMPARISON_POLICY,
        original_nine_metric_policy=NINE_METRIC_POLICY,
        search_progress_is_formal_quality_improvement=False,
        valid_proposal_count=len(index),
        distinct_valid_geometry_count=len({r["geometry_hash"] for r in index}),
        distinct_valid_v2_organization_count=len(
            {
                r["functional_diversity"]["meaningful_construction_hash"]
                for r in facts["all_valid_proposal_facts"]
                if r["functional_diversity"]["countable"]
            }
        ),
        independent_comparison_counts={
            key: {
                status: sum(c.get(key, {}).get("status") == status for c in facts["comparisons"])
                for status in (
                    "GEOMETRIC_PARETO_IMPROVEMENT",
                    "QUALITY_TRADEOFF",
                    "NO_MEASURABLE_IMPROVEMENT",
                    "NOT_COMPARABLE_STRUCTURE",
                    "INCOMPLETE_EVIDENCE",
                )
            }
            for key in ("original_nine", "twelve")
        },
    )
    dump(output / "execution-summary.json", summary)
    with (output / "results.md").open("a", encoding="utf-8") as report:
        report.write(
            "\nR7 uses unchanged P1-bound physical room areas, dimensions, aspect ratios, "
            "personnel routes and footprint metrics in area-quality-comparison.json. "
            "Nine and twelve metric "
            "comparisons are separate and restricted to the same Handoff/V2/Authority.\n"
            "Search frontier progress is NOT formal Pareto improvement. "
            "See r7-search-feedback.json. Original counter labels and totals: "
            "work-breakdown.json; raw durable history: journal.jsonl "
            "and execution-record.json. Unknown topology values remain unknown.\n"
            "No historical coordinate Seed, new engineering approval or "
            "overall improvement is claimed.\n"
        )


def run_main(output: Path, instruction_path: Path) -> None:
    digest = owner_execution_digest()
    instruction = instruction_path.read_bytes()
    if hashlib.sha256(instruction).hexdigest() != digest:
        raise LayoutAuthorityError("R7_OWNER_SOURCE_MISMATCH")
    repo = Path(__file__).resolve().parents[2]
    committed_source(repo)
    admission = github_admission(repo)  # PR313 fixed R6 Base; never historical PR CI evidence.
    store = approved_r7_main_store()
    store.require_unclaimed_grant()  # No input generation or output/Claim before Grant.
    StageALedger().guard()
    plan, p1, site, dependencies, binding = server_binding(repo)
    committed_source(repo)
    if (
        binding["head"] != admission["head"]
        or canonical_hash(runtime_dependencies()) != binding["runtime_dependency_hash"]
    ):
        raise LayoutAuthorityError("R7_SOURCE_OR_RUNTIME_CHANGED")
    store.validate_existing_binding(instruction, binding)
    # Recheck source/PR/Base/CI after potentially slow server/runtime preparation.
    if _pr_identity(github_admission(repo)["pr"]) != _pr_identity(admission["pr"]):
        raise LayoutAuthorityError("R7_PR_IDENTITY_CHANGED")
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "ci-admission.json", admission)
    dump(output / "source-binding.json", binding)
    dump(
        output / "owner-policy-binding.json",
        dict(task=TASK, owner_sha256=digest, contract=dict(CONTRACT)),
    )
    dump(output / "runtime-dependencies.json", dependencies)
    dump(output / "server-authorities.json", dict(plan=plan, p1=p1, site=site.to_dict()))
    (output / "owner-instruction.txt").write_bytes(instruction)
    ledger = store.open("MAIN")  # One exclusive durable Claim, never a retry loop.
    lease = ledger.execution_authorization
    if not isinstance(lease, R7MainLease):
        raise LayoutAuthorityError("R7_SEALED_LEASE_REQUIRED")
    result = None
    try:
        result = generate_multi_solution_pool(
            plan,
            p1,
            site,
            solver=StageBFirstFeasibleRecoveryFairSolver(),
            execution_ledger=ledger,
            fair_search=True,
        )
        dump(output / "main-pool.json", result)
    except BaseException as error:
        dump(output / "failure.json", dict(type=type(error).__name__, message=str(error)))
        raise
    finally:
        lease.finish_pool(result["canonical_result_hash"] if result else None)
        shutil.copyfile(store.root / "task_ledger.json", output / "resource-ledger.json")
        shutil.copyfile(store.root / "journal.jsonl", output / "journal.jsonl")
        dump(output / "execution-record.json", lease.record)
        ids = {
            r["identity"]
            for r in bind_layout_authority(plan, p1, site).access_requirements
            if r["flow_kind"] != "TRUCK"
        }
        export_r7_evidence(output, result, lease, site, ids, bind_layout_authority(plan, p1, site))
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = raw if sys.platform == "darwin" else raw * 1024
        totals = dict(lease.state["totals"])
        totals.update(
            post_export_elapsed_seconds=time.monotonic() - ledger.started,
            process_peak_rss_bytes=rss,
            checked_assignments=ledger.checked_solutions,
        )
        respected = (
            lease.state["accounting_complete"]
            and totals["native_solver_seconds"] <= CONTRACT["native_seconds"]
            and totals["post_export_elapsed_seconds"] <= CONTRACT["elapsed_seconds"]
            and totals["observable_work"] <= CONTRACT["observable_work"]
            and rss <= CONTRACT["memory_bytes"]
            and totals["native_calls"] <= CONTRACT["native_calls"]
            and ledger.checked_solutions <= CONTRACT["checked_assignments"]
        )
        dump(
            output / "resource-usage.json",
            dict(
                totals,
                resource_caps_respected=respected,
                accounting_complete=lease.state["accounting_complete"],
                old_grants_reused=False,
                replay_executed=False,
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-instruction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_main(args.output, args.owner_instruction)


if __name__ == "__main__":
    main()
