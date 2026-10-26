"""Bounded full synthetic R9/refinement experiment, never a MAIN or real Store.

CLI output must be new. Each comparison arm shares ONE 8s Native allowance
across original warmups, first feasibility, continuation and local refinement.
No known route coordinates or historical hints are inserted into Native search.
"""

import argparse
import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from cold_storage.modules.layout.application.global_composition_enumeration import (
    generate_global_composition_candidates,
)
from cold_storage.modules.layout.application.global_composition_pool import _eligible
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure import global_cp_sat_solver as native_module
from cold_storage.modules.layout.infrastructure import (
    stage_b_frontage_joint_search as frontage_module,
)
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    area_efficiency_snapshot,
)
from cold_storage.modules.layout.infrastructure.stage_b_changing_frontage_corridor import (
    StageBChangingFrontageCorridorFairSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_route_refinement import (
    StageBSameProxyRouteRefinementFairSolver,
)
from tests.r9_full_engineering_synthetic import geometry, sources

CAPS = dict(
    native_seconds=8.0,
    elapsed_seconds=85,
    work=600000,
    rss_mib=512,
    native_calls=12,
    checked=6,
    host_work=20000,
)


class StrictSyntheticQuota:
    """Memory-only diagnostic adapter; not a Grant/Claim, Lease or real registry."""

    def __init__(self, policy):
        self.events = []
        self.failed = False
        self.decision = dict(balanced_quality_policy_hash=policy)

    def guard(self, ledger):
        if (
            max(ledger.solver_wall, ledger.solver_monotonic_wall) > CAPS["native_seconds"]
            or ledger.model_work + ledger.native_host_work > CAPS["work"]
            or time.monotonic() - ledger.started > CAPS["elapsed_seconds"]
            or ledger.peak_rss_bytes > CAPS["rss_mib"] * 1024**2
            or ledger.checked_solutions > CAPS["checked"]
            or len(ledger.attempts) > CAPS["native_calls"]
        ):
            self.failed = True
            raise LayoutAuthorityError("SYNTHETIC_RESOURCE_FAIL")

    def validate(self, ledger):
        self.guard(ledger)

    def precharge_work(self, ledger, amount):
        self.guard(ledger)
        if ledger.model_work + ledger.native_host_work + amount > CAPS["work"]:
            raise LayoutAuthorityError("SYNTHETIC_WORK_PRECHARGE_LIMIT")

    def remaining_solver_seconds(self, ledger):
        self.guard(ledger)
        if (
            ledger.checked_solutions >= CAPS["checked"]
            or len(ledger.attempts) >= CAPS["native_calls"]
        ):
            return 0.0
        return max(
            0.0,
            CAPS["native_seconds"] - max(ledger.solver_wall, ledger.solver_monotonic_wall) - 0.08,
        )

    def checkpoint(self, phase, snapshot):
        self.events.append(dict(phase=phase, snapshot=deepcopy(snapshot)))

    def begin(self, bindings):
        self.events.append(dict(begin=deepcopy(bindings)))

    def record_enumeration(self, bindings, event):
        self.events.append(dict(bindings=deepcopy(bindings), event=deepcopy(event)))


def bind_scene(model, context):
    """R3/R4's independently designed same synthetic family; no forced route."""
    for role, room in model.rooms.items():
        z = geometry(context, 40)[role]
        for key, value in dict(
            x=int(z.x * 1000),
            y=int(z.y * 1000),
            nw=int(z.width_m * 1000),
            nd=int(z.depth_m * 1000),
            rot=z.rotation_deg // 90,
        ).items():
            if role == "changing_room" and key == "x":
                model.m.add(room[key] >= 40000)
                model.m.add(room[key] <= 42000)
            elif isinstance(room[key], int):
                assert room[key] == value
            else:
                model.m.add(room[key] == value)
    return model


def arm(folder, kind):
    folder.mkdir()

    def save(name, value):
        (folder / name).write_text(json.dumps(value, indent=2, default=str, ensure_ascii=False))

    plan, p1, site, h, c, *_ = sources()
    port = kind()
    ledger = c.ledger
    ledger.solver_history_verified = True
    quota = StrictSyntheticQuota(port.quality_policy_hash)
    ledger.execution_authorization = quota
    port.start_handoff(ledger, 1)
    original_run = port.native._run
    original_feedback = port.native._solve_with_feedback
    traces = []
    returned = []
    snapshots = []

    def feedback(context, solver, model, phase):
        log = []
        solver.parameters.log_search_progress = True
        solver.parameters.log_to_stdout = False
        solver.log_callback = log.append
        try:
            return original_feedback(context, solver, model, phase)
        finally:
            (folder / f"call-{len(ledger.attempts) + 1:02d}.log").write_text("".join(log))

    port.native._solve_with_feedback = feedback

    def run(context, model, seconds, phase):
        quota.guard(ledger)
        n = len(ledger.attempts) + 1
        local = model is getattr(port.native, "_route_model", None)
        before = dict(
            ordinal=n,
            phase=phase,
            local_route=local,
            improving=port.native.improving,
            requested_seconds=seconds,
            hint_count=len(model.proto.solution_hint.vars),
            model_sha256=hashlib.sha256(str(model.proto).encode()).hexdigest(),
            variables=len(model.proto.variables),
            constraints=len(model.proto.constraints),
            native_before=max(ledger.solver_wall, ledger.solver_monotonic_wall),
        )
        (folder / f"call-{n:02d}.pbtxt").write_text(str(model.proto))
        try:
            solver, status = original_run(context, model, seconds, phase)
            before.update(native=deepcopy(ledger.attempts[-1]), parameters=str(solver.parameters))
            quota.guard(ledger)
            return solver, status
        finally:
            before["native_after"] = max(ledger.solver_wall, ledger.solver_monotonic_wall)
            traces.append(before)
            save("calls.json", traces)

    port.native._run = run
    original_global = native_module.GlobalModel
    original_access = native_module.AccessModel
    original_reference = frontage_module._ReferenceAccessModel

    def global_factory(c, h, *a, **kw):
        return bind_scene(original_global(c, h, *a, **kw), c)

    def access_factory(c, h, *a, **kw):
        return bind_scene(original_access(c, h, *a, **kw), c)

    def reference_factory(c, h, *a, **kw):
        return bind_scene(original_reference(c, h, *a, **kw), c)

    error = None
    try:
        with (
            patch.object(native_module, "GlobalModel", global_factory),
            patch.object(native_module, "AccessModel", access_factory),
            patch.object(frontage_module, "_ReferenceAccessModel", reference_factory),
        ):
            gen = generate_global_composition_candidates(
                plan,
                p1.to_dict(),
                site,
                solver=port,
                composition_identity=h.composition_identity,
                execution_ledger=ledger,
            )
            try:
                for result in gen:
                    okay = _eligible(
                        result,
                        {
                            q["identity"]
                            for q in c.binding.access_requirements
                            if q["flow_kind"] != "TRUCK"
                        },
                    )
                    save(f"candidate-{len(returned) + 1:02d}.json", result)
                    returned.append(
                        dict(
                            eligible=okay,
                            stage=result["proposal"].get("search_stage"),
                            geometry_hash=result["proposal"].get("geometry_hash"),
                            route_refinement=result["proposal"].get("route_refinement"),
                            status=result["proposal"]["solver_status"],
                        )
                    )
                    if okay:
                        snapshots.append(
                            area_efficiency_snapshot(result, h.source_composition_hash, c.binding)
                        )
            finally:
                gen.close()
    except LayoutAuthorityError as exc:
        error = dict(code=exc.code, details=exc.details)
    save("audit.json", quota.events)
    usage = dict(
        model_work=ledger.model_work,
        native_host_work=ledger.native_host_work,
        total_work=ledger.model_work + ledger.native_host_work,
        resource_events=ledger.resource_events,
        solver_wall=ledger.solver_wall,
        solver_monotonic_wall=ledger.solver_monotonic_wall,
        attempts=ledger.attempts,
        checked=ledger.checked_solutions,
        native_requirements=ledger.native_requirements,
        peak_rss_bytes=ledger.peak_rss_bytes,
        elapsed_seconds=time.monotonic() - ledger.started,
    )
    result = dict(
        strategy=kind.__name__,
        policy_hash=port.quality_policy_hash,
        caps=CAPS,
        resource_fail=quota.failed,
        terminal_error=error,
        returned=returned,
        snapshots=snapshots,
        usage=usage,
        baseline=port.baseline,
        counts=dict(
            engineering_valid_witnesses=len(snapshots),
            distinct_room_geometries=len({s["geometry_hash"] for s in snapshots}),
        ),
    )
    save("result.json", result)
    print(
        json.dumps(
            dict(
                strategy=kind.__name__,
                resource_fail=quota.failed,
                native=usage["solver_monotonic_wall"],
                work=usage["total_work"],
                rows=[
                    dict(
                        stage=r["stage"],
                        eligible=r["eligible"],
                        route=s["metrics"]["personnel_route_m"],
                    )
                    for r, s in zip([r for r in returned if r["eligible"]], snapshots, strict=True)
                ],
                error=error,
            )
        ),
        flush=True,
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    a = arm(args.output / "r9-control", StageBChangingFrontageCorridorFairSolver)
    b = arm(args.output / "route-refinement", StageBSameProxyRouteRefinementFairSolver)
    (args.output / "comparison.json").write_text(
        json.dumps(
            dict(
                task="V2_2_2_STAGE_B_R9_SAME_PROXY_ROUTE_REFINEMENT_R6",
                per_arm_native_seconds=8,
                not_factory_data=True,
                control=a,
                refinement=b,
            ),
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
