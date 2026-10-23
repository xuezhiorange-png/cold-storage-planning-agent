"""One fixed R4 MAIN, only after separate Owner confirmation and preissued Grant."""

from __future__ import annotations

import argparse
import hashlib
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from run_stage_b_fair_pool import fair_binding
from run_stage_b_feasibility_first_main import export_evidence
from run_stage_b_functional_shape_ab import committed_source, runtime_dependencies
from run_stage_b_guided_fair_pool import _github_admission, _pr_identity
from run_stage_b_owner_pool import dump, server_inputs

from cold_storage.bootstrap.stage_b_r4_main import approved_r4_main_store
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.global_multi_solution_pool import (
    generate_multi_solution_pool,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    StageBFirstStageBalancedQualityFairSearchSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_r4_main_execution import (
    CI_IDENTITY,
    CONTRACT,
    REFERENCE_HEAD,
    TASK,
    R4MainLease,
    main_binding,
    owner_execution_digest,
)

OWNER_SCOPE_PATH = "docs/tasks/V2_2_2-stage-b-r4-owner-scope.txt"


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


def run_main(output: Path, instruction_path: Path) -> None:
    digest = owner_execution_digest()
    instruction = instruction_path.read_bytes()
    if hashlib.sha256(instruction).hexdigest() != digest:
        raise LayoutAuthorityError("R4_OWNER_SOURCE_MISMATCH")
    repo = Path(__file__).resolve().parents[2]
    committed_source(repo)
    admission = github_admission(repo)  # PR310 actual pinned Base; never PR307 evidence.
    store = approved_r4_main_store()
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
        raise LayoutAuthorityError("R4_SOURCE_OR_RUNTIME_CHANGED")
    store.validate_existing_binding(instruction, binding)
    # Recheck source/PR/Base/CI after potentially slow server/runtime preparation.
    if _pr_identity(github_admission(repo)["pr"]) != _pr_identity(admission["pr"]):
        raise LayoutAuthorityError("R4_PR_IDENTITY_CHANGED")
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
    if not isinstance(lease, R4MainLease):
        raise LayoutAuthorityError("R4_SEALED_LEASE_REQUIRED")
    result = None
    try:
        result = generate_multi_solution_pool(
            plan,
            p1,
            site,
            solver=StageBFirstStageBalancedQualityFairSearchSolver(),
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
