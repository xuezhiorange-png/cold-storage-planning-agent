"""Finite R9 H5 spatial templates; no Native, new grouping algorithm or Authority.

An identical 450x650 body may wait facing across the room (650x450 in plan).
That pose requires a separately checked translation and continuous yaw turn in
the existing aisle. A static rotated rectangle is never a movement certificate.
"""

import copy
from dataclasses import asdict, replace
from typing import Any

from cold_storage.modules.layout.domain.cabinet_front_schedule import (
    FrontParameters,
    _schedule,
    front_geometry,
)
from cold_storage.modules.layout.domain.functional_room_fit import covered, intersection, rectangle
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    _place,
    _snapshot,
    validate_use,
)

VERSION = "h5-functional-space-relayout-r11-r9@1.0.0"
TEMPLATES = ("MIXED_NORTH_RESERVE", "NORTH_WALL_WAITING", "SEGMENTED_NORTH_WAITING")


def sensitivity_parameters() -> FrontParameters:
    return FrontParameters(person_width_mm=450, person_depth_mm=650, person_gap_mm=100)


def waiting_clearances(g: dict[str, Any]) -> list[dict[str, Any]]:
    """100mm is a waiting-position gap, not an approved dynamic human clearance."""
    p = H5Hypothesis(**g["parameters"])
    errors = []
    for i, a in enumerate(g["model"]["homes"]):
        x, y, r, t = a["bounds_mm"]
        if (r - x, t - y) not in {
            (p.person_width_mm, p.person_depth_mm),
            (p.person_depth_mm, p.person_width_mm),
        }:
            errors.append(dict(code="WAITING_BODY_DIMENSIONS_CHANGED", home=i + 1))
        for j, b in enumerate(g["model"]["homes"][i + 1 :], i + 2):
            bx, by, br, bt = b["bounds_mm"]
            dx, dy = max(bx - r, x - br, 0), max(by - t, y - bt, 0)
            if max(dx, dy) < p.person_gap_mm:
                errors.append(dict(code="WAITING_GAP_NOT_PRESERVED", homes=[i + 1, j]))
    return errors


def relayout_geometry(
    room: dict[str, Any], demand: dict[str, Any], template: str, *, finish_mm: int = 20
) -> dict[str, Any]:
    if template not in TEMPLATES:
        raise ValueError("EXPLICIT_FINITE_R9_SPATIAL_TEMPLATE_REQUIRED")
    if type(finish_mm) is not int or not 20 <= finish_mm <= 100:
        raise ValueError("EXPLICIT_FINISH_SENSITIVITY_20_TO_100MM_REQUIRED")
    cfg = sensitivity_parameters()
    g = front_geometry(room, demand, cfg)
    hp = H5Hypothesis(**g["parameters"])
    # Last column's 600-wide activity is centered on a 450-wide person, not
    # the 400-wide cabinet. Keep its right overhang outside the 1200 turn bay.
    right_overhang = (cfg.activity_width_mm + hp.person_width_mm) // 2 - hp.column_width_mm
    hp = replace(hp, end_clearance_mm=max(hp.end_clearance_mm, right_overhang), finish_mm=finish_mm)
    if template == "SEGMENTED_NORTH_WAITING":
        hp = replace(hp, arrangement="SEGMENTED")
    g["model"] = _place(room, g["inventory"], hp)
    g["model"].update(changing_zone=None, homes=[])
    model = g["model"]
    ref = _snapshot(room, g["inventory"], model, hp, 1, [], "NETWORK")
    blockers = [
        *ref["aisles"],
        model["landing"],
        *[u["bounds_mm"] for u in g["inventory"]["cabinet_units"]],
    ]
    homes: list[dict[str, Any]] = []
    probes = []

    def append_row(start: int, y: int, width: int, depth: int, region: str) -> None:
        for x in range(start, model["clear"][2] - width + 1, width + hp.person_gap_mm):
            box = [x, y, x + width, y + depth]
            if len(homes) == 53:
                break
            inside = covered(rectangle(box), [rectangle(model["clear"])])
            collision = any(intersection(rectangle(box), rectangle(b)) for b in blockers)
            if not inside or collision:
                probes.append(
                    dict(
                        bounds_mm=box,
                        reason="OUTSIDE_FINISHED_ROOM"
                        if not inside
                        else "RESERVED_AISLE_FIXED_BODY_OR_LANDING",
                        north_boundary_deficit_mm=max(0, box[3] - model["clear"][3]),
                        region=region,
                    )
                )
                continue
            homes.append(
                dict(
                    bounds_mm=box,
                    pose="STANDING",
                    region=region,
                    yaw_degrees=90 if width == 650 else 0,
                )
            )

    bottom = model["main_y"] - hp.aisle_mm // 2 - hp.person_depth_mm
    top = model["main_y"] + hp.aisle_mm // 2
    north = ref["branch_y"] + hp.aisle_mm // 2
    if template == "MIXED_NORTH_RESERVE":
        append_row(model["waiting_start_x"], top, 450, 650, "EAST_NORTH_NORMAL")
        append_row(model["waiting_start_x"], bottom, 450, 650, "EAST_SOUTH_NORMAL")
        append_row(model["cabinet_start_x"], north, 650, 450, "WEST_NORTH_ROTATED")
    else:
        append_row(model["cabinet_start_x"], north, 650, 450, "NORTH_WALL_ROTATED")
        append_row(model["waiting_start_x"], bottom, 450, 650, "EAST_SOUTH_NORMAL")
    model["homes"] = homes
    g.update(
        version=VERSION,
        spatial_template=template,
        parameters=asdict(hp),
        snapshots=[],
        schedule_diagnostics=[],
        rejected_home_probes=probes,
        pose_basis="HYPOTHETICAL_SAME_450x650_BODY_WITH_CHECKED_AISLE_YAW_TURN",
    )
    g["waiting_snapshots"] = {
        str(s): _snapshot(room, g["inventory"], model, hp, s, [], "ALL_WAITING") for s in (1, 2)
    }
    g["waiting_evaluation"] = validate_use(
        room, g["inventory"], model, hp, g["waiting_snapshots"]["1"]
    )
    g["waiting_clearance_conflicts"] = waiting_clearances(g)
    if not (
        g["waiting_evaluation"]["conflicts"]
        or g["waiting_clearance_conflicts"]
        or g["hierarchy_failures"]
    ):
        # Exactly the R8 grouping implementation: this task changes space, not concurrency.
        for shift in (1, 2):
            batches, diag = _schedule(g, shift, cfg)
            g["snapshots"].extend(batches)
            g["schedule_diagnostics"].append(dict(diag, shift=shift))
    g["metrics"].update(
        home_count=len(homes),
        waiting_positions_missing=max(0, 53 - len(homes)),
        rotated_home_count=sum(h["yaw_degrees"] == 90 for h in homes),
        normal_home_count=sum(h["yaw_degrees"] == 0 for h in homes),
        north_strip_available_mm=model["clear"][3] - north,
        rotated_waiting_depth_mm=450,
        north_strip_margin_mm=model["clear"][3] - north - 450,
        cabinet_run_length_mm=max(u["bounds_mm"][2] for u in g["inventory"]["cabinet_units"])
        - min(u["bounds_mm"][0] for u in g["inventory"]["cabinet_units"]),
        waiting_start_x_mm=model["waiting_start_x"],
        batches=len(g["snapshots"]),
        static_pass_count=sum(not s["evaluation"]["conflicts"] for s in g["snapshots"]),
        verified_front_groups=sum(s["group_verified"] for s in g["snapshots"]),
    )
    g["dimension_chains"] = dict(
        units="mm",
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        transverse_cabinet_zone=[
            dict(label="完成面", value=hp.finish_mm),
            dict(label="安装退让", value=hp.installation_gap_mm),
            dict(label="柜深", value=hp.column_depth_mm),
            dict(label="柜前人距", value=hp.operator_standoff_mm),
            dict(label="运输人体纵深", value=hp.person_depth_mm),
            dict(label="净通道", value=hp.aisle_mm),
            dict(label="转向等候人体纵深", value=450),
            dict(label="剩余余量", value=model["clear"][3] - north - 450),
            dict(label="完成面", value=hp.finish_mm),
        ],
        activity_width_mm=600,
        activity_depth_mm=900,
        waiting_body_mm=[450, 650],
        rotated_waiting_body_mm=[650, 450],
        waiting_gap_mm=100,
        cabinet_end_activity_overhang_mm=right_overhang,
        cabinet_end_turning_clearance_mm=hp.end_clearance_mm,
        minimum_unrotated_north_row_building_depth_mm=north + 650 + hp.finish_mm,
        counterfactual_status="HYPOTHETICAL_NOT_APPROVED; NECESSARY_CROSS_SECTION_ONLY",
    )
    return copy.deepcopy(g)
