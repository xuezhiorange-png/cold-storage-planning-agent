"""Trusted operator entry: one fixed Owner grant, one real pool, one replay.

Not an MCP tool. It accepts neither geometry, family labels nor resource budgets.
After commit/push and validation, invoke with the pinned Owner instruction file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

from cold_storage.bootstrap.global_composition import (
    approved_stage_b_pool_store,
    generate_controlled_global_layout_pool,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.svg_projection import build_projection_payload
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolLease


def dump(path: Path, body: Any) -> None:
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str) + "\n")


def server_inputs(repo: Path) -> tuple[Any, Any, Any]:
    raw = (repo / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json").read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
    ):
        raise LayoutAuthorityError("POOL_FIXTURE_CHANGED")
    source = json.loads(raw)
    business = {
        k: source[k]
        for k in (
            "daily_inbound_mass_kg",
            "finished_storage_days",
            "frozen_storage_days",
            "main_packaging_storage_days",
            "auxiliary_packaging_storage_days",
        )
    }
    plan = asdict(
        ColdRoomZonePlanner().plan(
            ColdRoomZonePlanInput(
                **business,
                working_time_h_per_day=16,
                packaging_storage_days=3,
                precooling_required_ratio=1,
            )
        )
    )
    p1 = build_p1_project_handoff(plan, source["truck_access"])
    site = validate_site_geometry(
        {"site_constraints": source["site_constraints"], "truck_access": source["truck_access"]},
        plan,
        p1_handoff=p1,
    )
    return plan, p1.to_dict(), site


def execution_binding(repo: Path, plan: Any, p1: Any, site: Any) -> dict[str, Any]:
    authority = bind_layout_authority(plan, p1, site)
    handoffs = build_structural_compositions(plan, p1, site).placement_handoffs
    buckets: dict[str, list[Any]] = {}
    for h in sorted(handoffs, key=lambda h: h.composition_identity):
        buckets.setdefault(h.family.value, []).append(h)
    ordered = [
        buckets[f][i]
        for i in range(max(map(len, buckets.values())))
        for f in sorted(buckets)
        if i < len(buckets[f])
    ]
    files = sorted((repo / "backend/src").rglob("*.py")) + sorted(
        (repo / "backend/scripts").glob("*.py")
    )
    files += [
        repo / "backend/uv.lock",
        repo / "backend/pyproject.toml",
        repo / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json",
    ]
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "repository_root": str(repo),
        "dependency_file": str(repo / "backend/uv.lock"),
        "dependency_hash": sources[str(repo / "backend/uv.lock")],
        "source_files": sources,
        "zone_plan_hash": authority.canonical_zone_plan_hash,
        "p1_hash": authority.p1_handoff_hash,
        "site_hash": authority.site_geometry_hash,
        "schedule_hash": canonical_hash([h.to_dict() for h in ordered]),
        "compositions": [
            {
                "identity": h.composition_identity,
                "composition_hash": h.source_composition_hash,
                "handoff_hash": canonical_hash(h.to_dict()),
            }
            for h in ordered
        ],
        "solver_version": version("ortools"),
    }


def semantic_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schedule": result["schedule"],
        "sources": result["sources"],
        "attempts": [
            {
                "composition_identity": a["composition_identity"],
                "status": a["status"],
                "diversity": a.get("diversity"),
                "rooms": a.get("candidate_result", {}).get("proposal", {}).get("zones"),
                "model_routes": a.get("candidate_result", {}).get("proposal", {}).get("routes"),
                "engineering": a.get("candidate_result", {}).get("engineering_validation"),
                "independent": a.get("candidate_result", {}).get("independent_validation"),
                "native_independent": a.get("candidate_result", {}).get(
                    "native_independent_validation"
                ),
            }
            for a in result["attempts"]
        ],
        "accepted_ids": [c["candidate_id"] for c in result["candidates"]],
    }


def export_candidates(root: Path, result: dict[str, Any], site: Any) -> None:
    for i, row in enumerate(result["candidates"], 1):
        path = root / f"candidate-{i:02}"
        path.mkdir()
        body = row["candidate_result"]
        app = body["engineering_validation"]
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
        dump(path / "diversity.json", row["diversity"])
        dump(path / "resource_usage.json", body["resource_ledger"])
        svg = build_projection_payload(app, site.to_dict(), source_layout_hash=canonical_hash(app))[
            "svg"
        ]
        (path / "layout.svg").write_text(
            svg.replace("<svg ", '<svg data-stage="STAGE_B_CONCEPT_NOT_P2D" ', 1)
        )


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
    # Read real process-lifetime RSS before burning this task's one allocation.
    preflight = StageALedger()
    preflight.guard()
    args.output.mkdir(parents=True, exist_ok=False)
    plan, p1, site = server_inputs(repo)
    binding = execution_binding(repo, plan, p1, site)
    dump(args.output / "source_binding.json", binding)
    dump(
        args.output / "server_authorities.json",
        {"canonical_zone_plan": plan, "p1_handoff": p1, "typed_site": site.to_dict()},
    )
    store = approved_stage_b_pool_store()
    store.approve(args.owner_instruction.read_bytes(), binding)
    results = []
    for mode in ("MAIN", "REPLAY"):
        try:
            ledger = store.open(mode)
        except LayoutAuthorityError as error:
            dump(
                args.output / (mode.lower() + "_not_executed.json"),
                {"code": error.code, "details": error.details},
            )
            break
        lease = ledger.execution_authorization
        assert isinstance(lease, PoolLease)
        result = None
        try:
            result = generate_controlled_global_layout_pool(plan, p1, site, execution_ledger=ledger)
            dump(args.output / (mode.lower() + "_pool.json"), result)
            results.append(result)
        except Exception as error:
            dump(
                args.output / (mode.lower() + "_failure.json"),
                {"type": type(error).__name__, "message": str(error)},
            )
        finally:
            lease.finish_pool(result["canonical_result_hash"] if result else None)
        if result is None:
            break
    dump(
        args.output / "resource_ledger.json",
        json.loads((store.root / "task_ledger.json").read_text()),
    )
    if results:
        export_candidates(args.output, results[0], site)
    compared = len(results) == 2 and semantic_result(results[0]) == semantic_result(results[1])
    dump(
        args.output / "determinism.json",
        {
            "status": "PASS_ACTUAL_PARTIAL_POOL"
            if compared and results[0]["candidates"]
            else "NO_ACCEPTED_CANDIDATES_NOT_ESTABLISHED"
            if len(results) == 2 and not results[0]["candidates"]
            else "FAIL_DIFFERENT_GEOMETRY_OR_ENGINEERING"
            if len(results) == 2
            else "REPLAY_NOT_EXECUTED_RESOURCE_LIMIT",
            "semantic_hashes": [canonical_hash(semantic_result(r)) for r in results],
            "real_pool_count": len(results),
            "timing_and_execution_identity_excluded": True,
        },
    )
    print(
        json.dumps(
            {
                "real_pool_count": len(results),
                "candidate_counts": [len(r["candidates"]) for r in results],
            }
        )
    )


if __name__ == "__main__":
    main()
