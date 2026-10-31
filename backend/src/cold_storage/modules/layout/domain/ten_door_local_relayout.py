"""R15 finite waiting-home rearrangements; no building or cabinet changes.

The twelve declared combinations are a finite template check, not a proof of
global feasibility/infeasibility. Original motion, body, Portal and door checks
remain mandatory. Units are integer millimetres.
"""

import copy
from itertools import product
from typing import Any

from cold_storage.modules.layout.domain.cabinet_front_schedule import FrontParameters, _schedule
from cold_storage.modules.layout.domain.functional_room_fit import covered, intersection, rectangle
from cold_storage.modules.layout.domain.h5_space_relayout import waiting_clearances
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis, validate_use
from cold_storage.modules.layout.domain.reverse_sizing_geometry import (
    activity_parameters,
    sizing_snapshot,
)
from cold_storage.modules.layout.domain.standing_changing_operation import activity_proof
from cold_storage.modules.layout.domain.ten_door_locker_model import complete_inventory_conflicts

VERSION = "h5-complete-ten-door-local-relayout-r11-r15@1.0.0"
MAX_CANDIDATES = 12


def finite_organizations() -> list[dict[str, Any]]:
    return [
        dict(id=f"R15-{i:02}", south_grid=south, north_row=north, row_order=order)
        for i, (south, north, order) in enumerate(
            product(
                ("LEGACY_GRID", "PORTAL_EDGE_ALIGNED", "PORTAL_PLUS_TARGET"),
                ("LEGACY_NORTH", "NORTH_GAP_ALIGNED"),
                ("EAST_FIRST", "NORTH_FIRST"),
            ),
            1,
        )
    ]


def rearrange_homes(base: dict[str, Any], organization: dict[str, Any]) -> dict[str, Any]:
    if organization not in finite_organizations():
        raise ValueError("DECLARED_FINITE_R15_ORGANIZATION_REQUIRED")
    p = H5Hypothesis(**base["parameters"])
    if (
        base["room"]["local_bounds_mm"] != [0, 0, 26331, 3850]
        or (p.finish_mm, base["conditions"]["installation_gap_mm"]) != (30, 40)
        or base["spatial_padding_mm"] != 100
        or (p.person_width_mm, p.person_depth_mm, p.person_gap_mm, p.aisle_mm)
        != (450, 650, 200, 1300)
        or (
            base["front_parameters"]["activity_width_mm"],
            base["front_parameters"]["activity_depth_mm"],
        )
        != (600, 900)
        or complete_inventory_conflicts(base["inventory"], base["demand"])
    ):
        raise ValueError("UNCHANGED_R14_STRICT_3850_PROJECT_AND_ENVELOPES_REQUIRED")
    g = copy.deepcopy(base)
    g.update(
        version=VERSION,
        organization=copy.deepcopy(organization),
        snapshots=[],
        schedule_diagnostics=[],
    )
    model = g["model"]
    model["homes"] = []
    ref = sizing_snapshot(g, 1, [], "NETWORK")
    margin = g["spatial_padding_mm"]
    c = g["conditions"]
    blockers = [
        *ref["aisles"],
        model["landing"],
        *[u["bounds_mm"] for u in g["inventory"]["cabinet_units"]],
    ]
    north_y = ref["branch_y"] + p.aisle_mm - p.aisle_mm // 2 + margin
    east_y = model["main_y"] + p.aisle_mm - p.aisle_mm // 2 + margin
    if organization["north_row"] == "NORTH_GAP_ALIGNED":
        north_y = max(north_y, east_y + c["transport_depth_mm"] + p.person_gap_mm)
    south_x = model["waiting_start_x"]
    if organization["south_grid"] != "LEGACY_GRID":
        south_x = model["south_x"] + p.aisle_mm - p.aisle_mm // 2 + margin
        if organization["south_grid"] == "PORTAL_PLUS_TARGET":
            south_x += margin
    rows = [
        (model["waiting_start_x"], east_y, 450, 650, "EAST_NORTH_NORMAL"),
        (south_x, model["main_y"] - p.aisle_mm // 2 - margin - 650, 450, 650, "EAST_SOUTH_NORMAL"),
        (model["cabinet_start_x"], north_y, 650, 450, "NORTH_ROTATED"),
    ]
    if organization["row_order"] == "NORTH_FIRST":
        rows = [rows[2], rows[0], rows[1]]
    probes = []
    for start, y, width, depth, label in rows:
        for x in range(start, model["clear"][2] - width + 1, width + p.person_gap_mm):
            if len(model["homes"]) == 53:
                break
            box = [x, y, x + width, y + depth]
            fail = not covered(rectangle(box), [rectangle(model["clear"])]) or any(
                intersection(rectangle(box), rectangle(b)) for b in blockers
            )
            for home in model["homes"]:
                a = home["bounds_mm"]
                if (
                    max(max(a[0] - box[2], box[0] - a[2], 0), max(a[1] - box[3], box[1] - a[3], 0))
                    < p.person_gap_mm
                ):
                    fail = True
            if fail:
                probes.append(
                    dict(bounds_mm=box, region=label, code="WAITING_POSITION_OUTSIDE_OR_BLOCKED")
                )
            else:
                model["homes"].append(
                    dict(
                        bounds_mm=box,
                        pose="STANDING",
                        region=label,
                        yaw_degrees=0 if width == 450 else 90,
                    )
                )
    g["rejected_home_probes"] = probes
    g["waiting_snapshots"] = {str(s): sizing_snapshot(g, s, [], "ALL_WAITING") for s in (1, 2)}
    g["waiting_evaluation"] = validate_use(
        g["room"], g["inventory"], model, p, g["waiting_snapshots"]["1"]
    )
    g["waiting_clearance_conflicts"] = waiting_clearances(g)
    static = not (
        g["hierarchy_failures"]
        or g["waiting_evaluation"]["conflicts"]
        or g["waiting_clearance_conflicts"]
    )
    g["static_status"] = "STATIC_GEOMETRY_PASS" if static else "STATIC_GEOMETRY_REJECTED"
    if static and g["cross_section"]["status"] == "NECESSARY_CONDITIONS_PASS":
        cfg = FrontParameters(**g["front_parameters"])
        for shift in (1, 2):
            proposed, diag = _schedule(g, shift, cfg)
            for s in proposed:
                q = sizing_snapshot(g, shift, s["actions"], s["id"])
                q["evaluation"] = validate_use(g["room"], g["inventory"], model, p, q)
                q["front_activity_evaluation"] = activity_proof(
                    g,
                    q,
                    {o["id"]: o for o in q["people"]},
                    [a["person_id"] for a in q["actions"]],
                    activity_parameters(g),
                )
                q["group_verified"] = not (
                    q["evaluation"]["conflicts"] or q["front_activity_evaluation"]["conflicts"]
                )
                g["snapshots"].append(q)
            g["schedule_diagnostics"].append(dict(diag, shift=shift))
    g["metrics"].update(
        home_count=len(model["homes"]),
        rotated_home_count=sum(h["yaw_degrees"] == 90 for h in model["homes"]),
    )
    g["finite_check_scope"] = "TWELVE_DECLARED_TEMPLATES_ONLY; NOT_GLOBAL_INFEASIBILITY"
    return g


def home_coordinate_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old, new = before["model"]["homes"], after["model"]["homes"]
    # Index is the actual per-shift roster binding used by the original checker.
    rows = [
        dict(
            home=i + 1,
            before=old[i] if i < len(old) else None,
            after=new[i] if i < len(new) else None,
        )
        for i in range(max(len(old), len(new)))
        if (old[i] if i < len(old) else None) != (new[i] if i < len(new) else None)
    ]
    return dict(
        changed_homes=rows,
        cabinets_changed=before["inventory"] != after["inventory"],
        room_changed=before["room"] != after["room"],
        portals_changed=before["room"]["portals"] != after["room"]["portals"],
        dimensions_mm=after["room"]["local_bounds_mm"][2:],
    )
