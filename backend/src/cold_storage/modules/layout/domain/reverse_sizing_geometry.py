"""Counterfactual room adapter with explicit boundary/Portal mapping and padding.

Unchanged R5/R8/R9 physical validators are reused. This does not edit the sealed
room, infer external Access, or turn a section inequality into a complete fit.
"""

import copy
from dataclasses import asdict, replace
from typing import Any

from cold_storage.modules.layout.domain.cabinet_front_schedule import FrontParameters, _schedule
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_room_fit import covered, intersection, rectangle
from cold_storage.modules.layout.domain.functional_room_sizing_input import (
    PROFILES,
    VERSION,
    RoomUseConditions,
    physical_north_width,
)
from cold_storage.modules.layout.domain.h5_space_relayout import waiting_clearances
from cold_storage.modules.layout.domain.multi_tier_locker_layout import inventory_conflicts
from cold_storage.modules.layout.domain.multi_tier_locker_model import (
    MultiTierHypothesis,
    storage_inventory,
)
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    _place,
    _rect_lines,
    _snapshot,
    validate_use,
)
from cold_storage.modules.layout.domain.standing_changing_operation import activity_proof


def hypothetical_room(original: dict[str, Any], length: int, width: int) -> dict[str, Any]:
    if original["local_bounds_mm"] != [0, 0, 26331, 3250]:
        raise ValueError("FROZEN_H5_SOURCE_REQUIRED")
    if (
        type(length) is not int
        or type(width) is not int
        or not 26331 <= length <= 60000
        or not 3250 <= width <= 60000
    ):
        raise ValueError("EXPLICIT_NORTH_EAST_EXPANSION_PROFILE_REQUIRED")
    room = copy.deepcopy(original)
    room.update(
        local_bounds_mm=[0, 0, length, width],
        world_bounds_mm=None,
        record="HYPOTHETICAL_H5",
        scope_id="hypothetical:" + canonical_hash([original["scope_id"], length, width]),
        original_engineering_status="NOT_HISTORICAL_OR_ENGINEERING_APPROVED",
    )
    room["source_historical_geometry"] = copy.deepcopy(original)
    room["hypothetical"] = True
    mappings = []
    for q in room["portals"]:
        before = copy.deepcopy(q)
        if q["segment_mm"][0][0] == q["segment_mm"][1][0] == 26331:
            q["segment_mm"] = [[length, v[1]] for v in q["segment_mm"]]
        if q["segment_mm"] != before["segment_mm"]:
            q["id"] = "hypothetical:" + q["id"]
        mappings.append(
            dict(
                original=before,
                mapped=copy.deepcopy(q),
                position_changed=q["segment_mm"] != before["segment_mm"],
                external_access_status="NOT_EVALUATED_REVALIDATION_REQUIRED"
                if (length, width) != (26331, 3250)
                else "ARCHIVED_REFERENCE_ONLY",
            )
        )
    room["boundary_mapping"] = dict(
        anchor="WEST_AND_SOUTH_FIXED",
        east_delta_mm=length - 26331,
        north_delta_mm=width - 3250,
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        portal_mappings=mappings,
        site_footprint_and_external_access="NOT_EVALUATED_REVALIDATION_REQUIRED"
        if (length, width) != (26331, 3250)
        else "ARCHIVED_REFERENCE_ONLY",
    )
    # The candidate is never identified as the historical Native candidate.
    room["source_candidate_hash"] = room.pop("candidate_hash")
    return room


def activity_parameters(g: dict[str, Any]) -> Any:
    cfg = FrontParameters(**g["front_parameters"])
    return replace(
        cfg.standing(),
        standing_height_mm=g["conditions"]["body_height_mm"],
        activity_height_mm=g["conditions"]["body_height_mm"],
    )


def sizing_snapshot(
    g: dict[str, Any], shift: int, actions: list[dict[str, str]], key: str
) -> dict[str, Any]:
    p = H5Hypothesis(**g["parameters"])
    s = _snapshot(g["room"], g["inventory"], g["model"], p, shift, actions, key)
    extra = g["spatial_padding_mm"]
    if extra:
        branch = copy.deepcopy(s["branch_centerline_mm"])
        branch[0][1] += extra
        branch[1][1] += extra
        join = [
            [g["model"]["branch_bend_x"], g["model"]["main_y"]],
            [g["model"]["south_x"], g["model"]["main_y"]],
        ]
        paths = [branch, g["model"]["main_route"], join]
        aisles = [a for path in paths for a in _rect_lines(path, p.aisle_mm)]
        for x, y in [*branch, [g["model"]["south_x"], g["model"]["main_y"]]]:
            half = p.aisle_mm // 2
            aisles.append([x - half, y - half, x + p.aisle_mm - half, y + p.aisle_mm - half])
        s.update(
            aisles=aisles,
            branch_centerline_mm=branch,
            branch_y=s["branch_y"] + extra,
            network_lines=[
                list(pair)
                for path in paths
                for pair in zip(path, path[1:], strict=False)
                if pair[0] != pair[1]
            ],
        )
    return s


def construct_sizing_geometry(
    original: dict[str, Any], demand: dict[str, Any], c: RoomUseConditions, point: dict[str, Any]
) -> dict[str, Any]:
    c.checked()
    if (
        demand["shift_users"] != [53, 53]
        or demand["simultaneous_room_users"] != 53
        or demand["total_columns"] != 22
        or demand["total_capacity"] != 110
    ):
        raise ValueError("H5_ENGINEERING_ADAPTER_REQUIRES_REVIEWED_53_53_22_110_BASIS")
    length, width, m, profile = (
        point[k] for k in ("length_mm", "width_mm", "margin_mm", "profile")
    )
    if profile not in PROFILES or type(m) is not int or not 0 <= m <= 150:
        raise ValueError("SUPPORTED_FINITE_SIZING_PROFILE_REQUIRED")
    room = hypothetical_room(original, length, width)
    if 2 * c.finish_mm >= min(length, width):
        raise ValueError("FINISHED_DIMENSIONS_MUST_BE_POSITIVE")
    cfg = FrontParameters(
        person_width_mm=c.transport_width_mm,
        person_depth_mm=c.transport_depth_mm,
        person_gap_mm=c.waiting_gap_mm + m,
        activity_width_mm=c.activity_width_mm,
        activity_depth_mm=c.activity_depth_mm,
        columns_per_unit=c.columns_per_unit,
        unit_gap_mm=c.unit_gap_mm + m,
        room_door_intrusion_mm=c.room_door_intrusion_mm,
    )
    cfg.standing()
    overhang = (c.activity_width_mm + c.transport_width_mm) // 2 - c.column_width_mm
    p = H5Hypothesis(
        bench_count=0,
        column_width_mm=c.column_width_mm,
        column_depth_mm=c.column_depth_mm,
        cabinet_height_mm=c.cabinet_height_mm,
        cell_height_mm=c.cell_height_mm,
        plinth_mm=c.plinth_mm,
        shelf_mm=c.shelf_mm,
        columns_per_unit=c.columns_per_unit,
        finish_mm=c.finish_mm,
        installation_gap_mm=c.installation_gap_mm + m,
        unit_gap_mm=c.unit_gap_mm + m,
        end_clearance_mm=max(100, overhang) + m,
        operator_standoff_mm=c.operator_standoff_mm + m,
        aisle_mm=c.aisle_required_mm + m,
        person_width_mm=c.transport_width_mm,
        person_depth_mm=c.transport_depth_mm,
        standing_height_mm=c.body_height_mm,
        person_gap_mm=c.waiting_gap_mm + m,
        room_door_intrusion_mm=c.room_door_intrusion_mm,
        door_kind=c.door_kind,
    )
    inv = storage_inventory(
        demand,
        MultiTierHypothesis(
            column_width_mm=p.column_width_mm,
            column_depth_mm=p.column_depth_mm,
            cabinet_height_mm=p.cabinet_height_mm,
            compartment_clear_height_mm=p.cell_height_mm,
            plinth_mm=p.plinth_mm,
            shelf_mm=p.shelf_mm,
            columns_per_unit=p.columns_per_unit,
        ),
    )
    model = _place(room, inv, p)
    model.update(homes=[], changing_zone=None)
    g: dict[str, Any] = dict(
        version=VERSION,
        room=room,
        demand=copy.deepcopy(demand),
        parameters=asdict(p),
        front_parameters=asdict(cfg),
        inventory=inv,
        model=model,
        spatial_padding_mm=m,
        point=copy.deepcopy(point),
        conditions=asdict(c),
        snapshots=[],
        schedule_diagnostics=[],
        hierarchy_failures=inventory_conflicts(inv, demand),
        project_functional_status="INPUT_REQUIRED",
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        native_solves=0,
    )
    ref = sizing_snapshot(g, 1, [], "NETWORK")
    g["cross_section"] = dict(
        status="NECESSARY_CONDITIONS_PASS"
        if max(a[3] for a in ref["aisles"]) <= model["clear"][3] and p.aisle_mm <= 1500
        else "SECTION_REJECTED_FOR_THIS_TEMPLATE",
        branch_north_edge_mm=ref["branch_y"] + p.aisle_mm - p.aisle_mm // 2,
        rotated_north_row_physical_width_mm=physical_north_width(c, m, c.transport_width_mm),
        normal_north_row_physical_width_mm=physical_north_width(c, m, c.transport_depth_mm),
        section_scope="THIS_FINITE_TEMPLATE; NOT_GLOBAL_INFEASIBILITY_OR_FLOW_PASS",
    )
    homes = model["homes"]
    probes = []
    blockers = [*ref["aisles"], model["landing"], *[u["bounds_mm"] for u in inv["cabinet_units"]]]

    def row(start: int, y: int, w: int, d: int, label: str) -> None:
        for x in range(start, model["clear"][2] - w + 1, w + p.person_gap_mm):
            if len(homes) == 53:
                break
            b = [x, y, x + w, y + d]
            fail = (
                min(b) < 0
                or not covered(rectangle(b), [rectangle(model["clear"])])
                or any(intersection(rectangle(b), rectangle(q)) for q in blockers)
            )
            for h in homes:
                a = h["bounds_mm"]
                if (
                    max(max(a[0] - b[2], b[0] - a[2], 0), max(a[1] - b[3], b[1] - a[3], 0))
                    < p.person_gap_mm
                ):
                    fail = True
            if fail:
                probes.append(
                    dict(bounds_mm=b, region=label, code="WAITING_POSITION_OUTSIDE_OR_BLOCKED")
                )
                continue
            homes.append(
                dict(
                    bounds_mm=b,
                    pose="STANDING",
                    region=label,
                    yaw_degrees=0 if (w, d) == (c.transport_width_mm, c.transport_depth_mm) else 90,
                )
            )

    north = ref["branch_y"] + p.aisle_mm - p.aisle_mm // 2 + m
    east_top = model["main_y"] + p.aisle_mm - p.aisle_mm // 2 + m
    bottom = model["main_y"] - p.aisle_mm // 2 - m
    if profile == "MIXED":
        row(
            model["waiting_start_x"],
            east_top,
            c.transport_width_mm,
            c.transport_depth_mm,
            "EAST_NORTH_NORMAL",
        )
        row(
            model["waiting_start_x"],
            bottom - c.transport_depth_mm,
            c.transport_width_mm,
            c.transport_depth_mm,
            "EAST_SOUTH_NORMAL",
        )
        row(
            model["cabinet_start_x"],
            north,
            c.transport_depth_mm,
            c.transport_width_mm,
            "NORTH_ROTATED",
        )
    elif profile == "NORTH_ROTATED_SOUTH_NORMAL":
        row(
            model["cabinet_start_x"],
            north,
            c.transport_depth_mm,
            c.transport_width_mm,
            "NORTH_ROTATED",
        )
        row(
            model["waiting_start_x"],
            bottom - c.transport_depth_mm,
            c.transport_width_mm,
            c.transport_depth_mm,
            "EAST_SOUTH_NORMAL",
        )
    else:
        row(
            model["cabinet_start_x"],
            north,
            c.transport_width_mm,
            c.transport_depth_mm,
            "NORTH_NORMAL",
        )
        row(
            model["waiting_start_x"],
            bottom - c.transport_width_mm,
            c.transport_depth_mm,
            c.transport_width_mm,
            "EAST_SOUTH_ROTATED",
        )
    g["rejected_home_probes"] = probes
    g["waiting_snapshots"] = {str(s): sizing_snapshot(g, s, [], "ALL_WAITING") for s in (1, 2)}
    g["waiting_evaluation"] = validate_use(room, inv, model, p, g["waiting_snapshots"]["1"])
    g["waiting_clearance_conflicts"] = waiting_clearances(g)
    static = not (
        g["hierarchy_failures"]
        or g["waiting_evaluation"]["conflicts"]
        or g["waiting_clearance_conflicts"]
    )
    if static and g["cross_section"]["status"] == "NECESSARY_CONDITIONS_PASS":
        for shift in (1, 2):
            proposed, diag = _schedule(g, shift, cfg)
            rebuilt = []
            for s in proposed:
                q = sizing_snapshot(g, shift, s["actions"], s["id"])
                q["evaluation"] = validate_use(room, inv, model, p, q)
                current = {o["id"]: o for o in q["people"]}
                q["front_activity_evaluation"] = activity_proof(
                    g, q, current, [a["person_id"] for a in q["actions"]], activity_parameters(g)
                )
                q["group_verified"] = (
                    not q["evaluation"]["conflicts"]
                    and not q["front_activity_evaluation"]["conflicts"]
                )
                rebuilt.append(q)
            g["snapshots"].extend(rebuilt)
            g["schedule_diagnostics"].append(dict(diag, shift=shift))
    g["static_status"] = "STATIC_GEOMETRY_PASS" if static else "STATIC_GEOMETRY_REJECTED"
    g["metrics"] = dict(
        columns=22,
        compartments=110,
        home_count=len(homes),
        rotated_home_count=sum(h["yaw_degrees"] == 90 for h in homes),
        reserved_aisle_mm=p.aisle_mm,
        north_strip_available_mm=model["clear"][3]
        - (ref["branch_y"] + p.aisle_mm - p.aisle_mm // 2),
        cabinet_footprint_mm2=sum(
            (u["bounds_mm"][2] - u["bounds_mm"][0]) * (u["bounds_mm"][3] - u["bounds_mm"][1])
            for u in inv["cabinet_units"]
        ),
    )
    return g
