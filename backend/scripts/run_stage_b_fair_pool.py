"""Fixed Owner fair-pool MAIN/REPLAY; no geometry, policy, budget or registry args."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import subprocess
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from run_stage_b_multi_solution_pool import dump
from run_stage_b_owner_pool import execution_binding, semantic_result, server_inputs

from cold_storage.bootstrap.global_composition import (
    approved_stage_b_fair_pool_store,
    generate_fair_multi_solution_global_layout_pool,
)
from cold_storage.modules.layout.application.global_composition_pool import _eligible
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.stage_b_search_policy import POLICY_HASH, schedule_hash
from cold_storage.modules.layout.domain.construction_branch_diversity import (
    construction_branch_diversity,
)
from cold_storage.modules.layout.domain.construction_diversity import construction_diversity
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.svg_projection import build_projection_payload
from cold_storage.modules.layout.infrastructure.stage_b_fair_execution import (
    FAIR_ENUMERATION_CONTRACT,
    FairMultiSolutionPoolExecutionStore,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolLease


def fair_binding(repo: Path, plan: Any, p1: Any, site: Any) -> dict[str, Any]:
    binding = execution_binding(repo, plan, p1, site)
    binding["server_schedule_hash"] = binding["schedule_hash"]
    binding["schedule_hash"] = schedule_hash(binding["server_schedule_hash"])
    binding["fair_search_policy_hash"] = POLICY_HASH
    binding["enumeration_contract"] = dict(FAIR_ENUMERATION_CONTRACT)
    return binding


def fair_semantics(result: dict[str, Any]) -> dict[str, Any]:
    return {
        **semantic_result(result),
        "terminal_status": result["status"],
        "compositions": [
            {k: row.get(k) for k in ("composition_identity", "status", "error")}
            for row in result["compositions"]
        ],
        "functional_diversity": [a.get("functional_diversity") for a in result["attempts"]],
        "counts": {
            k: result[k]
            for k in (
                "distinct_physical_geometry_count",
                "distinct_meaningful_construction_count",
                "legacy_distinct_organization_count",
                "major_structural_family_count",
            )
        },
    }


def export_fair_pool(root: Path, result: dict[str, Any], site: Any, identities: set[str]) -> None:
    """Original renderer, actual application routes; no coordinate modification."""
    root.mkdir()
    accepted = {c["geometry_hash"] for c in result["candidates"]}
    seen: set[str] = set()
    index = []
    for attempt in result["attempts"]:
        body = attempt["candidate_result"]
        if not _eligible(body, identities):
            continue
        v1 = construction_diversity(body["proposal"]["zones"])
        geometry = v1["symmetry_invariant_geometry_hash"]
        if geometry in seen:
            continue
        seen.add(geometry)
        app = body["engineering_validation"]
        v2 = construction_branch_diversity(body["proposal"]["zones"], app["access_results"])
        counted = geometry in accepted
        path = root / f"candidate-{len(index) + 1:02}"
        path.mkdir()
        admission = dict(
            directory=path.name,
            geometry_hash=geometry,
            v2_construction_counted=counted,
            major_family_hash=v1["major_family_hash"],
            reason=attempt["status"],
            non_truck_access="PASS_11_OF_11",
            truck="BLOCKED",
            p2d_full_pass=False,
        )
        dump(path / "construction_admission.json", admission)
        dump(path / "candidate.json", body)
        dump(
            path / "engineering_validation.json",
            {
                "independent": body["independent_validation"],
                "native_independent": body["native_independent_validation"],
                "application": app,
            },
        )
        dump(path / "access_results.json", app["access_results"])
        dump(path / "diversity.json", {"v1": v1, "v2": v2, **admission})
        dump(path / "resource_usage.json", body["resource_ledger"])
        projection = build_projection_payload(
            app, site.to_dict(), source_layout_hash=canonical_hash(app)
        )
        dump(path / "projection.native.json", projection)
        native = projection["svg"]
        (path / "layout.native.svg").write_text(native)
        svg = (
            native.replace(
                "Layout status: VALIDATED", f"Layout status: CONSTRUCTION ONLY; V2={counted}"
            )
            .replace("Access: 12/12", "Non-Truck Access: 11/11")
            .replace("Truck route: VALIDATED", "Truck: BLOCKED - project input required")
        )
        svg = svg.replace("<svg ", '<svg data-stage="STAGE_B_NOT_P2D" ', 1)
        svg = (
            svg.replace(
                ">",
                "><metadata>" + escape(json.dumps(admission, sort_keys=True)) + "</metadata>",
                1,
            )
            if svg.startswith("<svg ")
            else svg
        )
        (path / "layout.svg").write_text(svg)
        dump(
            path / "drawing_provenance.json",
            {
                "candidate_file_sha256": hashlib.sha256(
                    (path / "candidate.json").read_bytes()
                ).hexdigest(),
                "candidate_canonical_hash": body["canonical_result_hash"],
                "source_application_hash": canonical_hash(app),
                "native_svg_sha256": hashlib.sha256(native.encode()).hexdigest(),
                "svg_sha256": hashlib.sha256(svg.encode()).hexdigest(),
                "room_and_corridor_coordinates_changed": False,
                "changes": "TRUTHFUL_STATUS_TEXT_ROOT_STAGE_ATTRIBUTE_METADATA_ONLY",
            },
        )
        index.append(admission)
    dump(root / "engineering_exports.json", index)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-instruction", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    dirty = subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=repo, text=True)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "backend/src", "backend/scripts"],
        cwd=repo,
        text=True,
    )
    if dirty.strip() or untracked.strip():
        raise LayoutAuthorityError("POOL_COMMITTED_SOURCE_REQUIRED")
    StageALedger().guard()
    args.output.mkdir(parents=True, exist_ok=False)
    plan, p1, site = server_inputs(repo)
    binding = fair_binding(repo, plan, p1, site)
    dump(args.output / "source_binding.json", binding)
    dump(
        args.output / "server_authorities.json",
        dict(canonical_zone_plan=plan, p1_handoff=p1, typed_site=site.to_dict()),
    )
    store = approved_stage_b_fair_pool_store()
    execute_fair_pools(
        args.output, plan, p1, site, store, args.owner_instruction.read_bytes(), binding
    )


def execute_fair_pools(
    output: Path,
    plan: Any,
    p1: Any,
    site: Any,
    store: FairMultiSolutionPoolExecutionStore,
    instruction: bytes,
    binding: dict[str, Any],
) -> None:
    """Shared unchanged two-pool execution/export; approval remains bootstrap-owned."""
    store.approve(instruction, binding)
    results = []
    for mode in ("MAIN", "REPLAY"):
        try:
            ledger = store.open(mode)
        except LayoutAuthorityError as error:
            dump(
                output / (mode.lower() + "_not_executed.json"),
                dict(code=error.code, details=error.details),
            )
            break
        lease = ledger.execution_authorization
        assert isinstance(lease, PoolLease)
        result = None
        try:
            result = generate_fair_multi_solution_global_layout_pool(
                plan, p1, site, execution_ledger=ledger
            )
            dump(output / (mode.lower() + "_pool.json"), result)
            results.append(result)
        except Exception as error:
            dump(
                output / (mode.lower() + "_failure.json"),
                dict(type=type(error).__name__, message=str(error)),
            )
        finally:
            lease.finish_pool(result["canonical_result_hash"] if result else None)
        if result is None:
            break
    state = json.loads((store.root / "task_ledger.json").read_text())
    dump(output / "resource_ledger.json", state)
    semantics = [fair_semantics(r) for r in results]
    compared = len(semantics) == 2 and semantics[0] == semantics[1]
    dump(
        output / "determinism.json",
        dict(
            status="PASS_ACTUAL_PARTIAL_POOL"
            if compared and results[0]["candidates"]
            else "NOT_ESTABLISHED_NO_ACCEPTED_CANDIDATES"
            if compared
            else "FAIL_DIFFERENT_ACTUAL_RESULTS"
            if len(results) == 2
            else "NOT_EXECUTED_RESOURCE_LIMIT",
            semantic_hashes=[canonical_hash(s) for s in semantics],
            real_pool_count=len(results),
            comparison_includes_termination_and_v1_v2=True,
            timing_and_execution_identity_excluded=True,
        ),
    )
    for mode, semantic in zip(("main", "replay"), semantics, strict=False):
        dump(output / (mode + "_semantics.json"), semantic)
    ids = {
        r["identity"]
        for r in bind_layout_authority(plan, p1, site).access_requirements
        if r["flow_kind"] != "TRUCK"
    }
    for mode, result in zip(("main", "replay"), results, strict=False):
        export_fair_pool(output / mode, result, site, ids)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    dump(
        output / "post_export_process_resource.json",
        dict(
            raw_ru_maxrss=rss,
            peak_rss_bytes=rss if sys.platform == "darwin" else rss * 1024,
            includes_preflight_and_post_solver_export=True,
        ),
    )
    print(
        json.dumps(
            dict(
                real_pool_count=len(results),
                counted_candidates=[len(r["candidates"]) for r in results],
            )
        )
    )


if __name__ == "__main__":
    main()
