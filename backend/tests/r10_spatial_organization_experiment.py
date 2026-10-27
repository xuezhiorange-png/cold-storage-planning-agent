"""Full 12-role synthetic comparison, not frozen20t data or a MAIN Runner.

Reuse the original complete synthetic P1/Site/Handoff and original application
acceptance stream. Relax the three functional bays and the downstream process
position together, identically in both arms. No accepted geometry is injected
as a Hint; the original first stage must obtain and validate its own baseline.
"""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from cold_storage.modules.layout.infrastructure.stage_b_functional_spatial_organization import (
    StageBFunctionalSpatialOrganizationFairSolver,
)
from cold_storage.modules.layout.infrastructure.stage_b_route_refinement_resources import (
    StageBResourceBoundRouteRefinementFairSolver,
)
from tests import r9_route_refinement_experiment as harness
from tests.r9_full_engineering_synthetic import geometry


def bind_functional_bays(model, context):
    """Test-only finite bays. All original physical/engineering constraints stay.

    Nine process/bank shapes come from the existing synthetic P1. Changing is
    south of Sorting, Office south of Shipping, Coating between precooling and
    finished goods. Those bays allow continuous integer-mm shapes/positions,
    not a prescribed alternative rectangle or a new P1 minimum room width.
    """
    baseline = geometry(context, 40)

    def add(expr):
        context.ledger.charge("R10_SYNTHETIC_BAY_CONSTRAINT", 1)
        model.m.add(expr)

    for role, room in model.rooms.items():
        if role in ("changing_room", "office", "coating_room"):
            continue
        z = baseline[role]
        for key, value in dict(
            x=int(z.x * 1000),
            y=int(z.y * 1000),
            nw=int(z.width_m * 1000),
            nd=int(z.depth_m * 1000),
            rot=z.rotation_deg // 90,
        ).items():
            if role in ("finished_goods_room", "shipping_channel") and key == "x":
                continue
            if isinstance(room[key], int):
                assert room[key] == value
            else:
                add(room[key] == value)
    changing, office, coating = (
        model.rooms[r] for r in ("changing_room", "office", "coating_room")
    )
    add(changing["x"] >= 36000)
    add(changing["x"] <= 46000)
    add(changing["Y"] == 30000)
    add(changing["w"] <= 12000)
    add(changing["d"] <= 20000)
    add(office["x"] == model.rooms["shipping_channel"]["x"])
    add(office["Y"] == 30000)
    add(office["w"] <= 12000)
    add(office["d"] <= 15000)
    add(coating["x"] == 52500)
    add(coating["y"] == 30000)
    add(coating["w"] <= 14000)
    add(coating["d"] <= 16000)
    add(model.rooms["finished_goods_room"]["x"] == coating["X"])
    add(model.rooms["shipping_channel"]["x"] == model.rooms["finished_goods_room"]["X"])
    return model


def run_arm(output, name):
    strategy = (
        StageBResourceBoundRouteRefinementFairSolver
        if name == "r9"
        else StageBFunctionalSpatialOrganizationFairSolver
    )
    # Patch only the independent synthetic model constructor's finite domains;
    # production Solves, validators, hints, feedback, metering and caps are real.
    with patch.object(harness, "bind_scene", bind_functional_bays):
        return harness.arm(output, strategy)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("r9", "r10"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run_arm(args.output, args.arm)
    (args.output / "scope.json").write_text(
        json.dumps(
            dict(
                fixture="EXISTING_R9_FULL_1000KG_SYNTHETIC_INPUT_WITH_MOVABLE_FUNCTIONAL_BAYS",
                fixed_engineering_authorities=True,
                historical_coordinates_used=False,
                full_role_count=12,
                non_truck_requirements=11,
                per_arm_caps=harness.CAPS,
                route_copy_work=result["usage"]["resource_events"].get("ROUTE_LOCAL_MODEL_COPY", 0),
                input_is_real_factory=False,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
