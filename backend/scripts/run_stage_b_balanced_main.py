"""One fixed balanced MAIN; unarmed until a future Owner execution digest is pinned."""

from __future__ import annotations

import argparse
import hashlib
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

from run_stage_b_fair_pool import fair_binding
from run_stage_b_feasibility_first_main import export_evidence
from run_stage_b_functional_shape_ab import committed_source, runtime_dependencies
from run_stage_b_guided_fair_pool import github_admission
from run_stage_b_owner_pool import dump, server_inputs

from cold_storage.bootstrap.stage_b_balanced_main import approved_balanced_main_store
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.global_multi_solution_pool import (
    generate_multi_solution_pool,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_balanced_main_execution import (
    CONTRACT,
    TASK,
    BalancedMainLease,
    main_binding,
    owner_execution_digest,
)
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    StageBBalancedQualityFairSearchSolver,
)

REFERENCE_HEAD = "ec324151d02aa45a3cbb555d4a14c3325e021ac7"


def run_main(output: Path, instruction_path: Path) -> None:
    digest = owner_execution_digest()  # Unissued wiring approval cannot start anything.
    instruction = instruction_path.read_bytes()
    if hashlib.sha256(instruction).hexdigest() != digest:
        raise LayoutAuthorityError("BALANCED_OWNER_SOURCE_MISMATCH")
    repo = Path(__file__).resolve().parents[2]
    committed_source(repo)
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", REFERENCE_HEAD, "HEAD"], cwd=repo, check=True
    )
    admission = github_admission(repo)
    store = approved_balanced_main_store()
    if store.root.exists():
        raise LayoutAuthorityError("BALANCED_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION")
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
        raise LayoutAuthorityError("BALANCED_SOURCE_OR_RUNTIME_CHANGED")
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
    store.approve(instruction, binding)
    ledger = store.open("MAIN")  # One exclusive durable Claim; no loop or retry.
    lease = ledger.execution_authorization
    if not isinstance(lease, BalancedMainLease):
        raise LayoutAuthorityError("BALANCED_SEALED_LEASE_REQUIRED")
    result = None
    try:
        result = generate_multi_solution_pool(
            plan,
            p1,
            site,
            solver=StageBBalancedQualityFairSearchSolver(),
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
        export_evidence(output, result, lease, site, ids, task=TASK)
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
