"""One pinned feasibility-first MAIN. No replay, quota, seed or strategy arguments."""

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
from xml.etree import ElementTree as ET

from run_stage_b_fair_pool import export_fair_pool, fair_binding
from run_stage_b_functional_shape_ab import committed_source, runtime_dependencies
from run_stage_b_guided_fair_pool import github_admission
from run_stage_b_owner_pool import dump, server_inputs

from cold_storage.bootstrap.stage_b_feasibility_main import approved_feasibility_first_main_store
from cold_storage.modules.layout.application.global_composition_pool import _eligible
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.global_multi_solution_pool import (
    generate_multi_solution_pool,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_first import (
    StageBFeasibilityFirstFairSearchSolver,
    _quality_facts,
)
from cold_storage.modules.layout.infrastructure.stage_b_feasibility_main_execution import (
    CONTRACT,
    OWNER_SHA256,
    TASK,
    FeasibilityFirstMainLease,
    main_binding,
)

REFERENCE_HEAD = "0a5e5e77ced298dda58eeb773ad8386a8e7d6562"


def export_evidence(
    output: Path, result: Any, lease: Any, site: Any, ids: set[str], *, task: str = TASK
) -> None:
    """Read original validation events/results; no new search or engineering oracle."""
    events = lease.record.get("enumeration_events", [])
    transitions = [
        e
        for e in events
        if e["kind"]
        in {
            "FINAL_MODEL_GUIDANCE_APPLIED",
            "BOUNDED_IMPROVEMENT_STARTED",
            "FEASIBILITY_FIRST_QUALITY_FACTS",
        }
    ]
    dump(output / "stage-transition-events.json", transitions)
    comparisons = [e for e in events if e["kind"] == "FEASIBILITY_FIRST_QUALITY_FACTS"]
    validations = [e["candidate_result"] for e in events if e["kind"] == "VALIDATION_RESULT"]
    if result is not None:
        attempts = result["attempts"]
    else:
        attempts = [
            dict(candidate_result=c, status="RECOVERED_VALIDATION_NOT_POOL_COUNTED")
            for c in validations
        ]
    rows: list[dict[str, Any]] = []
    bases: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    (output / "previews").mkdir()
    for attempt in attempts:
        candidate = attempt["candidate_result"]
        if not _eligible(candidate, ids):
            continue
        digest = candidate["canonical_result_hash"]
        if digest != canonical_hash(
            {k: v for k, v in candidate.items() if k != "canonical_result_hash"}
        ):
            raise LayoutAuthorityError("FEASIBILITY_EXPORTED_CANDIDATE_HASH_MISMATCH")
        # Export EACH validated proposal, even a repeated room geometry with a
        # different real route. The existing exporter/renderer remains unchanged.
        folder = output / "previews" / f"proposal-{len(rows) + 1:02}"
        counted = [
            c
            for c in (result or {}).get("candidates", [])
            if c["candidate_result"]["canonical_result_hash"] == digest
        ]
        export_fair_pool(folder, {"attempts": [attempt], "candidates": counted}, site, ids)
        svg = folder / "candidate-01/layout.svg"
        parsed = ET.fromstring(svg.read_bytes())
        if any(
            e.tag.rsplit("}", 1)[-1] in {"script", "foreignObject"}
            or any(
                k.rsplit("}", 1)[-1] in {"href", "src"} and not v.startswith("#")
                for k, v in e.attrib.items()
            )
            for e in parsed.iter()
        ):
            raise LayoutAuthorityError("FEASIBILITY_SVG_EXTERNAL_CONTENT_REJECTED")
        row = {
            "candidate_hash": digest,
            "source_composition_hash": candidate["source_composition_hash"],
            "search_stage": candidate["proposal"].get("search_stage"),
            "geometry_hash": candidate["proposal"]["geometry_hash"],
            "counted_construction": bool(counted),
            "svg": str(svg.relative_to(output)),
            "svg_sha256": hashlib.sha256(svg.read_bytes()).hexdigest(),
            "facts": _quality_facts(candidate),
        }
        rows.append(row)
        (bases if row["search_stage"] == "FEASIBILITY_FIRST" else improvements).append(row)
    preserved = all(
        any(c["canonical_result_hash"] == r["candidate_hash"] for c in validations) for r in bases
    )
    pareto = [e for e in comparisons if e["status"] == "GEOMETRIC_PARETO_IMPROVEMENT"]
    tradeoffs = [
        e
        for e in comparisons
        if any(v > 0 for v in e.get("metric_directions_minus_one_better", {}).values())
        and any(v < 0 for v in e.get("metric_directions_minus_one_better", {}).values())
    ]
    started = sum(e["kind"] == "BOUNDED_IMPROVEMENT_STARTED" for e in events)
    compared_hashes = {e["candidate"]["candidate_hash"] for e in comparisons if "candidate" in e}
    unreviewed = any(r["candidate_hash"] not in compared_hashes for r in improvements)
    summary = {
        "task": task,
        "main_status": (result or {}).get("status", "INTERRUPTED_SEE_FAILURE_AND_DURABLE_EVENTS"),
        "main_execution_count": 1,
        "handoffs_attempted": lease.record["cursor"],
        "base_engineering_valid_count": len(bases),
        "improvement_stage_started_count": started,
        "improvement_engineering_valid_proposals": len(improvements),
        "improvement_new_geometry_count": len(
            {r["geometry_hash"] for r in improvements} - {r["geometry_hash"] for r in bases}
        ),
        "baseline_preserved": preserved if bases else "NOT_APPLICABLE_NO_VALID_BASELINE",
        "baseline_hashes_unchanged": preserved if bases else "NOT_APPLICABLE_NO_VALID_BASELINE",
        "geometric_pareto_improvement_count": len(pareto),
        "quality_tradeoff_count": len(tradeoffs),
        "meaningful_constructions": (result or {}).get("distinct_meaningful_construction_count", 0),
        "major_families": (result or {}).get("major_structural_family_count", 0),
        "real_two_stage_result": "INCONCLUSIVE"
        if not bases or not started or unreviewed
        else "IMPROVED"
        if pareto and not tradeoffs
        else "TRADEOFF"
        if tradeoffs
        else "NO_IMPROVEMENT",
        "real_layout_quality_improved": "NOT_ESTABLISHED",
        "real_replay_determinism": "NOT_EVALUATED",
        "functional_fit": "INPUT_REQUIRED",
        "p2d_full_pass_count": 0,
        "stage_b_complete": False,
        "version_complete": False,
    }
    dump(output / "candidate-index.json", rows)
    dump(output / "engineering-validation.json", validations)
    dump(
        output / "quality-comparison.json",
        {
            "original_comparison_events": comparisons,
            "all_valid_proposal_facts": rows,
            "comparison_scope": "SAME_HANDOFF_CURRENT_EXECUTION_BASELINE_ONLY",
            "last_unresumed_proposals_not_assumed_pareto": True,
        },
    )
    dump(output / "execution-summary.json", summary)
    (output / "results.md").write_text(
        ("# Feasibility-first MAIN" if task == TASK else "# Balanced Stage B MAIN")
        + " — actual result\n\n```json\n"
        + json.dumps(summary, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        + "All facts: quality-comparison.json.\n"
        + "Original certificates: engineering-validation.json.\n"
        + "Regression Fixture only; NOT approved Xinzhao Phase II engineering input.\n"
        + "Coating = PACKAGING_BOX_FILM_SEALING. Truck BLOCKED_PROJECT_INPUT.\n"
        + "No replay, second MAIN, default promotion, Ready/Merge/Deploy. STOP.\n",
        encoding="utf-8",
    )


def run_main(output: Path, instruction_path: Path) -> None:
    instruction = instruction_path.read_bytes()
    if hashlib.sha256(instruction).hexdigest() != OWNER_SHA256:
        raise LayoutAuthorityError("FEASIBILITY_OWNER_SOURCE_MISMATCH")
    repo = Path(__file__).resolve().parents[2]
    committed_source(repo)
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", REFERENCE_HEAD, "HEAD"], cwd=repo, check=True
    )
    admission = github_admission(repo)  # No approval/claim before exact-head formal PR acceptance.
    store = approved_feasibility_first_main_store()
    if store.root.exists():
        raise LayoutAuthorityError("FEASIBILITY_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION")
    StageALedger().guard()
    plan, p1, site = server_inputs(repo)
    dependencies = runtime_dependencies()
    common = fair_binding(repo, plan, p1, site)
    tracked = subprocess.check_output(
        ["git", "ls-files", "backend/src", "backend/scripts"], cwd=repo, text=True
    ).splitlines()
    common["source_files"].update(
        {str(repo / n): hashlib.sha256((repo / n).read_bytes()).hexdigest() for n in tracked}
    )
    common["runtime_dependency_hash"] = canonical_hash(dependencies)
    binding = main_binding(common)
    committed_source(repo)
    if (
        binding["head"] != admission["head"]
        or canonical_hash(runtime_dependencies()) != (binding["runtime_dependency_hash"])
    ):
        raise LayoutAuthorityError("FEASIBILITY_SOURCE_OR_RUNTIME_CHANGED")
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "ci-admission.json", admission)
    dump(output / "source-binding.json", binding)
    dump(
        output / "owner-policy-binding.json",
        {
            "task": TASK,
            "owner_sha256": OWNER_SHA256,
            "contract": dict(CONTRACT),
            "policy_hash": binding["feasibility_first_policy_hash"],
            "owner_source": "ORIGINAL_FULL_CHAT_INSTRUCTION_UTF8_LF_NOT_RESUME_MESSAGE",
        },
    )
    dump(output / "runtime-dependencies.json", dependencies)
    dump(output / "server-authorities.json", dict(plan=plan, p1=p1, site=site.to_dict()))
    (output / "owner-instruction.txt").write_bytes(instruction)
    store.approve(instruction, binding)
    ledger = store.open("MAIN")  # The only execution call; no loop/replay/resume.
    lease = ledger.execution_authorization
    assert isinstance(lease, FeasibilityFirstMainLease)
    result = None
    try:
        result = generate_multi_solution_pool(
            plan,
            p1,
            site,
            solver=StageBFeasibilityFirstFairSearchSolver(),
            execution_ledger=ledger,
            fair_search=True,
        )
        dump(output / "main-pool.json", result)
    except BaseException as error:
        dump(output / "failure.json", {"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        lease.finish_pool(result["canonical_result_hash"] if result else None)
        shutil.copyfile(store.root / "task_ledger.json", output / "resource-ledger.json")
        ids = {
            r["identity"]
            for r in bind_layout_authority(plan, p1, site).access_requirements
            if r["flow_kind"] != "TRUCK"
        }
        export_evidence(output, result, lease, site, ids)
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = raw if sys.platform == "darwin" else raw * 1024
        totals = dict(lease.state["totals"])
        totals.update(
            post_export_elapsed_seconds=time.monotonic() - ledger.started,
            process_peak_rss_bytes=rss,
        )
        respected = (
            lease.state["accounting_complete"]
            and totals["native_solver_seconds"] <= 49.9
            and totals["post_export_elapsed_seconds"] <= 85
            and totals["observable_work"] <= 600_000
            and rss <= 512 * 1024 * 1024
            and totals["native_calls"] <= 100
            and ledger.checked_solutions <= 20
        )
        dump(
            output / "resource-usage.json",
            {
                **totals,
                "resource_caps_respected": respected,
                "accounting_complete": lease.state["accounting_complete"],
                "old_grants_reused": False,
                "replay_executed": False,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-instruction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_main(args.output, args.owner_instruction)


if __name__ == "__main__":
    main()
