"""One fixed R5 MAIN, only after separate Owner confirmation and preissued Grant."""

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

from cold_storage.bootstrap.stage_b_r5_main import approved_r5_main_store
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.global_multi_solution_pool import (
    generate_multi_solution_pool,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    COMPARISON_POLICY,
    StageBAreaEfficientQualityFairSearchSolver,
    area_efficiency_snapshot,
    compare_area_efficient_quality,
)
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    COMPARISON_POLICY as NINE_METRIC_POLICY,
)
from cold_storage.modules.layout.infrastructure.stage_b_r5_main_execution import (
    CI_IDENTITY,
    CONTRACT,
    REFERENCE_HEAD,
    TASK,
    R5MainLease,
    main_binding,
    owner_execution_digest,
)

OWNER_SCOPE_PATH = "docs/tasks/V2_2_2-stage-b-r5-owner-scope.txt"


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


def quality_evidence(
    candidates: list[dict[str, Any]], binding: Any, events: list[Any]
) -> dict[str, Any]:
    """Read independently accepted geometries with the existing R5 fact/comparison functions."""
    snapshots = {
        c["canonical_result_hash"]: area_efficiency_snapshot(
            c, c["source_composition_hash"], binding
        )
        for c in candidates
    }
    comparisons = []
    for event in events:
        if event.get("kind") != "FEASIBILITY_FIRST_QUALITY_FACTS" or "candidate" not in event:
            continue
        before = snapshots.get(event.get("baseline_candidate_hash"))
        after = snapshots.get(event.get("candidate_hash"))
        if before is None or after is None:
            comparisons.append(dict(status="NOT_EVALUATED", original_event=event))
            continue
        twelve = compare_area_efficient_quality(before, after)
        if canonical_hash(twelve) != canonical_hash({k: event[k] for k in twelve}):
            raise LayoutAuthorityError("R5_EXPORTED_COMPARISON_RECEIPT_MISMATCH")
        comparisons.append(
            dict(
                baseline_candidate_hash=before["candidate_hash"],
                candidate_hash=after["candidate_hash"],
                original_nine=twelve["original_nine_metric_comparison"],
                twelve=twelve,
            )
        )
    return dict(
        comparison_policy=COMPARISON_POLICY,
        original_nine_metric_policy=NINE_METRIC_POLICY,
        comparison_scope="SAME_EXECUTION_HANDOFF_V2_ORGANIZATION_AND_AUTHORITY_ONLY",
        all_valid_proposal_facts=list(snapshots.values()),
        comparisons=comparisons,
        unpaired_candidate_status="NOT_EVALUATED",
        historical_cross_handoff_pareto_allowed=False,
        formal_quality_acceptance=False,
    )


def export_r5_evidence(
    output: Path, result: Any, lease: Any, site: Any, ids: set[str], binding: Any
) -> None:
    # Preserve the original exporter, eligibility checks, certificates, SVGs and hashes.
    export_base_evidence(output, result, lease, site, ids, task=TASK)
    index = json.loads((output / "candidate-index.json").read_text())
    candidates = [
        json.loads((output / Path(row["svg"]).parent / "candidate.json").read_text())
        for row in index
    ]
    events = lease.record.get("enumeration_events", [])
    facts = quality_evidence(candidates, binding, events)
    dump(output / "area-quality-comparison.json", facts)
    # Keep entire certificates, including legal null/unknown hole counts. No second topology oracle.
    dump(
        output / "topology-rejections.json",
        [e for e in events if e.get("kind") == "TOPOLOGY_REJECTED_WITNESS_CUT"],
    )
    summary = json.loads((output / "execution-summary.json").read_text())
    summary["comparison_policy"] = COMPARISON_POLICY
    summary["original_nine_metric_policy"] = NINE_METRIC_POLICY
    summary["independent_comparison_counts"] = {
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
    }
    dump(output / "execution-summary.json", summary)
    with (output / "results.md").open("a", encoding="utf-8") as report:
        report.write(
            "\nR5: area-quality-comparison.json contains P1 demand, actual areas, allocation/"
            "over-allocation, room aspects, measured personnel routes and actual footprint facts.\n"
            "Original nine and new twelve comparisons are independent; unpaired or cross-structure "
            "candidates are NOT_EVALUATED / NOT_COMPARABLE_STRUCTURE, never assumed Pareto.\n"
            "Generic improvement counts above use the twelve-metric policy. "
            "See execution-summary.json for independent counts.\n"
            "Original topology certificates: topology-rejections.json. "
            "No synthetic layout or overall engineering improvement is claimed.\n"
        )


def run_main(output: Path, instruction_path: Path) -> None:
    digest = owner_execution_digest()
    instruction = instruction_path.read_bytes()
    if hashlib.sha256(instruction).hexdigest() != digest:
        raise LayoutAuthorityError("R5_OWNER_SOURCE_MISMATCH")
    repo = Path(__file__).resolve().parents[2]
    committed_source(repo)
    admission = github_admission(repo)  # PR311 actual pinned Base; never PR307 evidence.
    store = approved_r5_main_store()
    store.require_unclaimed_grant()  # No input generation or output/Claim before Grant.
    StageALedger().guard()
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
    committed_source(repo)
    if (
        binding["head"] != admission["head"]
        or canonical_hash(runtime_dependencies()) != binding["runtime_dependency_hash"]
    ):
        raise LayoutAuthorityError("R5_SOURCE_OR_RUNTIME_CHANGED")
    store.validate_existing_binding(instruction, binding)
    # Recheck source/PR/Base/CI after potentially slow server/runtime preparation.
    if _pr_identity(github_admission(repo)["pr"]) != _pr_identity(admission["pr"]):
        raise LayoutAuthorityError("R5_PR_IDENTITY_CHANGED")
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
    if not isinstance(lease, R5MainLease):
        raise LayoutAuthorityError("R5_SEALED_LEASE_REQUIRED")
    result = None
    try:
        result = generate_multi_solution_pool(
            plan,
            p1,
            site,
            solver=StageBAreaEfficientQualityFairSearchSolver(),
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
        ids = {
            r["identity"]
            for r in bind_layout_authority(plan, p1, site).access_requirements
            if r["flow_kind"] != "TRUCK"
        }
        export_r5_evidence(output, result, lease, site, ids, bind_layout_authority(plan, p1, site))
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = raw if sys.platform == "darwin" else raw * 1024
        totals = dict(lease.state["totals"])
        totals.update(
            post_export_elapsed_seconds=time.monotonic() - ledger.started,
            process_peak_rss_bytes=rss,
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
