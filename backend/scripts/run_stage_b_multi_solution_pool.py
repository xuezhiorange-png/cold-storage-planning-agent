"""Trusted fixed-grant entry: one real enumeration pool and one exact replay.

No caller geometry, budget, registry, family, seed or task-identity parameters.
Source must be committed before execution. Export is after the shared experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import subprocess
import sys
from pathlib import Path
from typing import Any

from run_stage_b_owner_pool import execution_binding, semantic_result, server_inputs

from cold_storage.bootstrap.global_composition import (
    approved_stage_b_multi_solution_store,
    generate_multi_solution_global_layout_pool,
)
from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.svg_projection import build_projection_payload
from cold_storage.modules.layout.infrastructure.stage_b_multi_solution_execution import (
    ENUMERATION_CONTRACT,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolLease


def dump(path: Path, body: Any) -> None:
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str) + "\n")


def export_pool(root: Path, result: dict[str, Any], site: Any) -> None:
    """Render actual native application corridors; only captions are annotated."""
    root.mkdir()
    rows = [dict(row, construction_counted=True) for row in result["candidates"]]
    seen = {row["diversity"].get("symmetry_invariant_geometry_hash") for row in rows}
    for attempt in result.get("attempts", []):
        if attempt.get("status") != "SAME_MAJOR_ORGANIZATION_NOT_COUNTED":
            continue
        geometry = attempt["diversity"]["symmetry_invariant_geometry_hash"]
        if geometry not in seen:
            rows.append(dict(attempt, construction_counted=False))
            seen.add(geometry)
    exports = []
    for i, row in enumerate(rows, 1):
        path = root / f"candidate-{i:02}"
        path.mkdir()
        body = row["candidate_result"]
        app = body["engineering_validation"]
        admission = {
            "directory": path.name,
            "construction_counted": row["construction_counted"],
            "reason": "COUNTED" if row["construction_counted"] else "SAME_MAJOR_ORGANIZATION",
            "diversity": row["diversity"],
        }
        dump(path / "construction_admission.json", admission)
        exports.append(admission)
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
        projection = build_projection_payload(
            app, site.to_dict(), source_layout_hash=canonical_hash(app)
        )
        dump(path / "projection.native.json", projection)
        native_svg = projection["svg"]
        (path / "layout.native.svg").write_text(native_svg)
        non_truck = [r for r in app["access_results"] if r.get("flow_kind") != "TRUCK"]
        passed = sum(r.get("status") == "PASS" for r in non_truck)
        svg = (
            native_svg.replace("Layout status: VALIDATED", "Layout status: CONSTRUCTION ONLY")
            .replace("Access: 12/12", f"Non-Truck Access: {passed}/{len(non_truck)}")
            .replace("Truck route: VALIDATED", "Truck: BLOCKED - project input required")
        )
        svg = svg.replace("<svg ", '<svg data-stage="STAGE_B_CONCEPT_NOT_P2D" ', 1)
        (path / "layout.svg").write_text(svg)
        svg_hash = "sha256:" + hashlib.sha256(svg.encode()).hexdigest()
        dump(
            path / "projection.json",
            {
                **projection,
                "svg": svg,
                "svg_sha256": svg_hash,
                "canonical_svg_hash": svg_hash,
                "project_layout_validated": app.get("project_layout_validated", False),
                "p2_complete": app.get("p2_complete", False),
                "renderer_status_is_not_engineering_acceptance": True,
            },
        )
        dump(
            path / "drawing_provenance.json",
            {
                "candidate_file_sha256": hashlib.sha256(
                    (path / "candidate.json").read_bytes()
                ).hexdigest(),
                "source_application_hash": canonical_hash(app),
                "native_svg_sha256": hashlib.sha256(native_svg.encode()).hexdigest(),
                "svg_sha256": hashlib.sha256(svg.encode()).hexdigest(),
                "only_root_stage_attribute_and_truthful_status_text_changed": True,
                "room_and_corridor_coordinates_changed": False,
                "p2d_full_pass": False,
            },
        )
    dump(root / "engineering_exports.json", exports)


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
    StageALedger().guard()  # Real lifetime RSS before consuming the single grant.
    args.output.mkdir(parents=True, exist_ok=False)
    plan, p1, site = server_inputs(repo)
    binding = execution_binding(repo, plan, p1, site)
    binding["enumeration_contract"] = dict(ENUMERATION_CONTRACT)
    dump(args.output / "source_binding.json", binding)
    dump(
        args.output / "server_authorities.json",
        {
            "canonical_zone_plan": plan,
            "p1_handoff": p1,
            "typed_site": site.to_dict(),
        },
    )
    store = approved_stage_b_multi_solution_store()
    store.approve(args.owner_instruction.read_bytes(), binding)
    results = []
    for mode in ("MAIN", "REPLAY"):
        try:
            ledger = store.open(mode)
        except LayoutAuthorityError as error:
            dump(
                args.output / (mode.lower() + "_not_executed.json"),
                {
                    "code": error.code,
                    "details": error.details,
                },
            )
            break
        lease = ledger.execution_authorization
        assert isinstance(lease, PoolLease)
        result = None
        try:
            result = generate_multi_solution_global_layout_pool(
                plan, p1, site, execution_ledger=ledger
            )
            dump(args.output / (mode.lower() + "_pool.json"), result)
            results.append(result)
        except Exception as error:
            dump(
                args.output / (mode.lower() + "_failure.json"),
                {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            )
        finally:
            lease.finish_pool(result["canonical_result_hash"] if result else None)
        if result is None:
            break
    dump(
        args.output / "resource_ledger.json",
        json.loads((store.root / "task_ledger.json").read_text()),
    )
    semantics = [semantic_result(result) for result in results]
    compared = len(semantics) == 2 and semantics[0] == semantics[1]
    dump(
        args.output / "determinism.json",
        {
            "status": "PASS_ACTUAL_PARTIAL_POOL"
            if compared and results[0]["candidates"]
            else "NOT_ESTABLISHED_NO_ACCEPTED_CANDIDATES"
            if compared
            else "FAIL_DIFFERENT_ACTUAL_RESULTS"
            if len(results) == 2
            else "NOT_EXECUTED_RESOURCE_LIMIT",
            "semantic_hashes": [canonical_hash(s) for s in semantics],
            "real_pool_count": len(results),
            "timing_and_execution_identity_excluded": True,
        },
    )
    for mode, result in zip(("main", "replay"), results, strict=False):
        export_pool(args.output / mode, result, site)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    dump(
        args.output / "post_export_process_resource.json",
        {
            "raw_ru_maxrss": rss,
            "unit": "BYTES" if sys.platform == "darwin" else "KIB",
            "peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
            "includes_preflight_and_post_solver_export": True,
        },
    )
    print(
        json.dumps(
            {
                "real_pool_count": len(results),
                "counted_candidates": [len(r["candidates"]) for r in results],
            }
        )
    )


if __name__ == "__main__":
    main()
