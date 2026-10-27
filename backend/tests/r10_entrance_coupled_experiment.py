"""Bounded three-arm R2 comparison; original authorities, never a real MAIN."""

import argparse
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cold_storage.modules.layout.infrastructure.stage_b_entrance_coupled_spatial import (
    StageBEntranceCoupledSpatialFairSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_functional_spatial_organization import (
    StageBFunctionalSpatialOrganizationFairSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_route_refinement_resources import (
    StageBResourceBoundRouteRefinementFairSolver,
)
from tests import r9_route_refinement_experiment as harness
from tests.r9_full_engineering_synthetic import geometry, sources
from tests.r10_spatial_organization_experiment import bind_functional_bays

STRATEGIES = {
    "r9": StageBResourceBoundRouteRefinementFairSolver,
    "r1": StageBFunctionalSpatialOrganizationFairSolver,
    "r2": StageBEntranceCoupledSpatialFairSolver,
}


def designed_translation(offset_y):
    """Independent oracle fixture, NEVER injected into Native or its Hint."""
    from cold_storage.modules.layout.application.global_composition_solver import (
        validate_generated_global_proposal,
    )
    from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
    from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
    from cold_storage.modules.layout.infrastructure.global_cp_sat_model import envelopes
    from tests.r9_full_engineering_synthetic import routes

    plan, p1, site, h, c, *_ = sources()
    c.ledger.solver_history_verified = True
    c.ledger.execution_authorization = harness.StrictSyntheticQuota("DESIGNED_ORACLE_NOT_NATIVE")
    zones = {
        role: PlacedRectangleV1(
            role, z.x, z.y + Decimal(offset_y), z.width_m, z.depth_m, z.rotation_deg
        )
        for role, z in geometry(c, 40).items()
    }
    actual_routes = routes(c, zones)
    route = next(r for r in actual_routes if r["from_ref"] == "main_entrance")
    x, y, right, _ = zones["changing_room"].bounds_mm
    entry = c.entrances["main_entrance"]
    ex = (entry[0][0] + entry[1][0]) // 2
    centre = (x + right) // 2
    knee = y // 2
    path = [(ex, 0), (ex, knee), (centre, knee), (centre, y)]
    route.update(
        path_mm=path,
        envelopes_mm=envelopes(path, route["width_mm"]),
        portal_from_center_mm=path[0],
        portal_to_center_mm=path[-1],
        turn_count=2,
        length_mm=sum(
            abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(path, path[1:], strict=False)
        ),
    )
    topology = inspect_rectangular_union(
        [z.bounds_mm for z in zones.values()]
        + [tuple(e) for r in actual_routes for e in r["envelopes_mm"]],
        charge=c.ledger.charge,
    )
    result = validate_generated_global_proposal(
        plan,
        p1.to_dict(),
        site,
        c,
        h,
        dict(
            solver_status="INDEPENDENT_DESIGNED_SYNTHETIC_GEOMETRY_NOT_NATIVE",
            zones=[z.to_dict() for z in zones.values()],
            routes=actual_routes,
            model_witness_topology=topology,
            search_stage="ORACLE_FIXTURE_NOT_SEARCH_RESULT",
        ),
    )
    return result


def bind_moving_process_bays(model, context):
    """Second synthetic family: process spine translates, functional rooms vary.

    No translation variable is needed: use existing Sorting x/y as the anchor.
    Fixed-role P1 dimensions/rotations stay, relative process-bank positions stay,
    and Original Access/MUST/Site constraints still determine legal solutions.
    These finite test ranges apply identically to all three strategies.
    """
    baseline = geometry(context, 40)
    anchor = model.rooms["sorting_packaging_room"]

    def add(expression):
        context.ledger.charge("R10_R2_SYNTHETIC_BAY_CONSTRAINT", 1)
        model.m.add(expression)

    add(anchor["x"] >= 38000)
    add(anchor["x"] <= 48000)
    add(anchor["y"] >= 12000)
    add(anchor["y"] <= 36000)
    for role, room in model.rooms.items():
        if role in ("changing_room", "office", "coating_room"):
            continue
        z = baseline[role]
        for key, value in dict(
            nw=int(z.width_m * 1000),
            nd=int(z.depth_m * 1000),
            rot=z.rotation_deg // 90,
        ).items():
            if isinstance(room[key], int):
                assert room[key] == value
            else:
                add(room[key] == value)
        if role != "sorting_packaging_room":
            if role not in ("finished_goods_room", "shipping_channel"):
                add(room["x"] == anchor["x"] + int(z.x * 1000) - 40000)
            add(room["y"] == anchor["y"] + int(z.y * 1000) - 30000)
    changing, office, coating = (
        model.rooms[r] for r in ("changing_room", "office", "coating_room")
    )
    add(changing["x"] >= anchor["x"] - 4000)
    add(changing["x"] <= anchor["x"] + 6000)
    add(changing["Y"] == anchor["y"])
    add(changing["w"] <= 12000)
    add(changing["d"] <= 20000)
    add(office["x"] == model.rooms["shipping_channel"]["x"])
    add(office["Y"] == anchor["y"])
    add(office["w"] <= 12000)
    add(office["d"] <= 15000)
    add(coating["x"] == model.rooms["secondary_precooling_room"]["X"])
    add(coating["y"] == anchor["y"])
    add(coating["w"] <= 14000)
    add(coating["d"] <= 16000)
    add(model.rooms["finished_goods_room"]["x"] == coating["X"])
    add(model.rooms["shipping_channel"]["x"] == model.rooms["finished_goods_room"]["X"])
    return model


def run_arm(output, name, scene="moving"):
    builder = bind_moving_process_bays if scene == "moving" else bind_functional_bays
    with patch.object(harness, "bind_scene", builder):
        return harness.arm(output, STRATEGIES[name])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=tuple(STRATEGIES), required=True)
    parser.add_argument("--scene", choices=("moving", "fixed"), default="moving")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run_arm(args.output, args.arm, args.scene)
    (args.output / "scope.json").write_text(
        json.dumps(
            dict(
                fixture="FULL_1000KG_SYNTHETIC_12_ROLE",
                scene=args.scene,
                common_plan_p1_site_handoff=True,
                caps=harness.CAPS,
                actual_route_copy_work=result["usage"]["resource_events"].get(
                    "ROUTE_LOCAL_MODEL_COPY", 0
                ),
                real_main=False,
                actual_grant_claim=False,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
