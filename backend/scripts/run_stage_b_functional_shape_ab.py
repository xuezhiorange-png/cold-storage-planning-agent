"""Pinned A then B MAIN-only operator. Never replay or issue replacement claims."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from run_stage_b_fair_pool import export_fair_pool, fair_binding
from run_stage_b_guided_fair_pool import github_admission
from run_stage_b_owner_pool import dump, server_inputs

from cold_storage.bootstrap.stage_b_functional_shape_ab import approved_functional_shape_ab_stores
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.global_multi_solution_pool import (
    generate_multi_solution_pool,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_a_execution import _durable
from cold_storage.modules.layout.infrastructure.stage_b_fair_search import (
    StageBFairSearchSolver,
    StageBFunctionalShapeFairSearchSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_functional_shape_ab import (
    CONTRACT,
    OWNER_SHA256,
    TASK,
    FunctionalShapeABLease,
    arm_binding,
)

REFERENCE_HEAD = "6042ac821582f881e8bbe8b70ee2423b5c813c71"


def runtime_dependencies() -> dict[str, Any]:
    """Hash actual installed bytes, not just package version/lock declarations."""
    result = {}
    for dist in importlib.metadata.distributions():
        rows = {}
        for item in dist.files or ():
            path = Path(str(dist.locate_file(item)))
            if path.is_file() and path.suffix != ".pyc":
                rows[str(item)] = hashlib.sha256(path.read_bytes()).hexdigest()
        name = dist.metadata["Name"]
        # The repository's editable egg-info has no installed-file RECORD. Its
        # actual Python sources are already frozen by execution_binding().
        if name == "cold-storage-agent" and not rows:
            root = Path(__file__).resolve().parents[1] / "src"
            metadata = root / "cold_storage_agent.egg-info/PKG-INFO"
            if Path(str(dist.locate_file(""))).resolve() == root and metadata.is_file():
                rows["editable-project-PKG-INFO"] = hashlib.sha256(
                    metadata.read_bytes()
                ).hexdigest()
        if not name or not rows or name in result:
            raise LayoutAuthorityError("AB_RUNTIME_DEPENDENCY_IDENTITY_UNVERIFIED")
        result[name] = {
            "version": dist.version,
            "actual_files_hash": canonical_hash(rows),
            "files": len(rows),
        }
    return {
        "packages": result,
        "python": sys.version,
        "executable_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
    }


def committed_source(repo: Path) -> None:
    dirty = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=repo, text=True)
    extra = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "backend/src",
            "backend/scripts",
        ],
        cwd=repo,
        text=True,
    )
    if dirty.strip() or extra.strip():
        raise LayoutAuthorityError("POOL_COMMITTED_SOURCE_REQUIRED")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", REFERENCE_HEAD, "HEAD"], cwd=repo, check=True
    )


def execute(output: Path, repo: Path, instruction: bytes, admission: dict[str, Any]) -> None:
    stores = approved_functional_shape_ab_stores()
    if any(s.root.exists() or s.shared_root.exists() for s in stores):
        raise LayoutAuthorityError("AB_EXISTING_FIXED_SLOT_REQUIRES_INSPECTION_NO_RESTART")
    StageALedger().guard()
    plan, p1, site = server_inputs(repo)
    dependencies = runtime_dependencies()
    common = fair_binding(repo, plan, p1, site)
    # Include non-Python runtime schemas/templates too, not just original .py files.
    tracked = subprocess.check_output(
        ["git", "ls-files", "backend/src", "backend/scripts"], cwd=repo, text=True
    ).splitlines()
    common["source_files"].update(
        {
            str(repo / path): hashlib.sha256((repo / path).read_bytes()).hexdigest()
            for path in tracked
        }
    )
    common["runtime_dependency_hash"] = canonical_hash(dependencies)
    common["experiment_owner_sha256"] = OWNER_SHA256
    bindings = [arm_binding(common, arm) for arm in ("A", "B")]
    output.mkdir(parents=True, exist_ok=True)
    _durable(
        output / "execution-started.json",
        {"head": admission["head"], "owner_sha256": OWNER_SHA256},
        exclusive=True,
    )
    (output / "owner-instruction.txt").write_bytes(instruction)
    dump(output / "ci-admission.json", admission)
    dump(
        output / "source-admission.json",
        {
            "head": common["head"],
            "dependency_files": dependencies,
            "committed_source": True,
            "same_plan_p1_site": True,
            "same_six_handoffs": True,
        },
    )
    dump(
        output / "owner-execution-binding.json",
        {"A": bindings[0], "B": bindings[1], "contract": dict(CONTRACT)},
    )
    dump(
        output / "server-authorities.json",
        {"canonical_zone_plan": plan, "p1_handoff": p1, "typed_site": site.to_dict()},
    )
    for store, binding in zip(stores, bindings, strict=True):
        store.approve(instruction, binding)
    results = {}
    for arm, store, solver in zip(
        ("A", "B"),
        stores,
        (StageBFairSearchSolver(), StageBFunctionalShapeFairSearchSolver()),
        strict=True,
    ):
        root = output / f"arm-{arm.lower()}"
        root.mkdir()
        # No source/runtime drift between arms and no export work inside B's reserve.
        committed_source(repo)
        if (
            common["head"]
            != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            or canonical_hash(runtime_dependencies()) != common["runtime_dependency_hash"]
        ):
            raise LayoutAuthorityError("AB_EXECUTION_SOURCE_OR_RUNTIME_CHANGED")
        try:
            ledger = store.open("MAIN")
        except LayoutAuthorityError as error:
            dump(root / "not-executed.json", {"status": "NOT_EXECUTED", "code": error.code})
            break
        lease = ledger.execution_authorization
        assert isinstance(lease, FunctionalShapeABLease)
        result = None
        try:
            result = generate_multi_solution_pool(
                plan, p1, site, solver=solver, execution_ledger=ledger, fair_search=True
            )
            dump(root / "pool.json", result)
            results[arm] = result
        except BaseException as error:
            dump(root / "failure.json", {"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            lease.finish_pool(result["canonical_result_hash"] if result else None)
            shutil.copyfile(store.root / "task_ledger.json", root / "resource-ledger.json")
            shutil.copyfile(
                store.shared_root / "shared-resource-ledger.json",
                output / "shared-resource-ledger.json",
            )
        if not lease.state["accounting_complete"]:
            raise LayoutAuthorityError("AB_INTERRUPTED_UNKNOWN_CONSUMPTION_STOP")
        counters = lease.record["counters"]
        if (
            max(ledger.solver_wall, ledger.solver_monotonic_wall) > 49.9
            or counters["elapsed_seconds"] > 85
            or ledger.model_work + ledger.native_host_work > 600_000
        ):
            raise LayoutAuthorityError("AB_ACCOUNTED_ARM_RESOURCE_LIMIT_STOP")
    ids = {
        r["identity"]
        for r in bind_layout_authority(plan, p1, site).access_requirements
        if r["flow_kind"] != "TRUCK"
    }
    previews = output / "previews"
    previews.mkdir()
    for arm, result in results.items():
        export_fair_pool(previews / f"arm-{arm.lower()}", result, site, ids)
    shared = json.loads((stores[0].shared_root / "shared-resource-ledger.json").read_text())
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss = raw if sys.platform == "darwin" else raw * 1024
    shared["post_export_elapsed_seconds"] = time.monotonic() - shared["started_monotonic"]
    shared["post_export_process_peak_rss_bytes"] = rss
    shared["real_replay_determinism"] = "NOT_EVALUATED"
    shared["resource_caps_respected"] = (
        shared["post_export_elapsed_seconds"] <= 180
        and rss <= 512 * 1024 * 1024
        and shared["totals"]["native_solver_seconds"] <= 100
        and shared["totals"]["observable_work"] <= 1_200_000
        and shared["totals"]["native_calls"] <= 100
        and all(row["totals"]["native_solver_seconds"] <= 49.9 for row in shared["arms"].values())
    )
    dump(output / "shared-resource-ledger.json", shared)
    print(
        json.dumps(
            {
                "task": TASK,
                "arms_executed": list(results),
                "resource_caps_respected": shared["resource_caps_respected"],
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-instruction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    instruction = args.owner_instruction.read_bytes()
    if hashlib.sha256(instruction).hexdigest() != OWNER_SHA256:
        raise LayoutAuthorityError("POOL_OWNER_SOURCE_MISMATCH")
    repo = Path(__file__).resolve().parents[2]
    committed_source(repo)
    admission = github_admission(repo)  # both exact-head terminal successes BEFORE approval/claim
    execute(args.output, repo, instruction, admission)


if __name__ == "__main__":
    main()
