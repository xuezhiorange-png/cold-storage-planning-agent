"""Finite H5 complete-cabinet geometry; reuse original movement/static checks.

NO_PLAN_INTRUSION is an internal CLOSED-DOOR subproof representation only.
Independent required R14 open-door checks are composed by the application.
It is not a selected door product, an actual no-intrusion claim or a full PASS.
"""

import copy
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.domain.cabinet_front_schedule import FrontParameters, _schedule
from cold_storage.modules.layout.domain.functional_room_fit import covered, intersection, rectangle
from cold_storage.modules.layout.domain.functional_room_sizing_input import RoomUseConditions
from cold_storage.modules.layout.domain.h5_space_relayout import waiting_clearances
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    _place,
    validate_use,
)
from cold_storage.modules.layout.domain.reverse_sizing_geometry import (
    activity_parameters,
    hypothetical_room,
    sizing_snapshot,
)
from cold_storage.modules.layout.domain.reverse_sizing_margins import geometry_margins
from cold_storage.modules.layout.domain.reverse_sizing_operation import simulate_sizing_shift
from cold_storage.modules.layout.domain.standing_changing_operation import activity_proof
from cold_storage.modules.layout.domain.ten_door_locker_model import (
    VERSION,
    DoorSensitivity,
    complete_inventory,
    complete_inventory_conflicts,
)


def complete_cabinet_geometry(
    original: dict[str, Any],
    demand: dict[str, Any],
    conditions: RoomUseConditions,
    width: int,
    margin: int,
) -> dict[str, Any]:
    conditions.checked()
    if width not in (3550, 3850) or margin not in (50, 100):
        raise ValueError("FINITE_R14_C_3850_SENSITIVITY_REQUIRED")
    if (conditions.column_width_mm, conditions.column_depth_mm, conditions.cabinet_height_mm) != (
        425,
        390,
        1800,
    ):
        raise ValueError("SELECTED_COMPLETE_CABINET_NOMINAL_ENVELOPE_REQUIRED")
    c = conditions
    room = hypothetical_room(original, 26331, width)
    point = dict(length_mm=26331, width_mm=width, margin_mm=margin, profile="MIXED")
    cfg = FrontParameters(
        person_width_mm=c.transport_width_mm,
        person_depth_mm=c.transport_depth_mm,
        person_gap_mm=c.waiting_gap_mm + margin,
        activity_width_mm=c.activity_width_mm,
        activity_depth_mm=c.activity_depth_mm,
        columns_per_unit=2,
        unit_gap_mm=c.unit_gap_mm + margin,
    )
    p = H5Hypothesis(
        bench_count=0,
        door_kind="NO_PLAN_INTRUSION",
        column_width_mm=425,
        column_depth_mm=390,
        cabinet_height_mm=1800,
        cell_height_mm=320,
        plinth_mm=100,
        shelf_mm=20,
        columns_per_unit=2,
        finish_mm=c.finish_mm,
        installation_gap_mm=c.installation_gap_mm + margin,
        unit_gap_mm=c.unit_gap_mm + margin,
        end_clearance_mm=max(100, (c.activity_width_mm + c.transport_width_mm) // 2 - 425) + margin,
        operator_standoff_mm=c.operator_standoff_mm + margin,
        aisle_mm=c.aisle_required_mm + margin,
        person_width_mm=c.transport_width_mm,
        person_depth_mm=c.transport_depth_mm,
        standing_height_mm=c.body_height_mm,
        person_gap_mm=c.waiting_gap_mm + margin,
        # Explicit R14 sensitivity range, not actual ergonomic validation. The
        # 100..1780 nominal leaf faces cannot reuse R13's 100..1700 reference.
        reach_low_mm=100,
        reach_high_mm=1800,
    )
    inv = complete_inventory(demand, DoorSensitivity("ALL_LEFT"))
    model = _place(room, inv, p)
    for unit in inv["cabinet_units"]:
        x, y, right, top = unit["bounds_mm"]
        unit["physical_centerline_mm"] = [[x + 425, y], [x + 425, top]]
        unit["front_segment_mm"] = [[x, top], [right, top]]
        unit["actual_frame_status"] = "INPUT_REQUIRED"
    for col in inv["vertical_columns"]:
        x, _, right, top = col["bounds_mm"]
        col["front_segment_mm"] = [[x, top], [right, top]]
        col["exact_front_center_x"] = dict(numerator=x + right, denominator=2, unit="mm")
        col["axis_basis"] = "EXACT_RATIONAL_EQUAL_DIVISION_SENSITIVITY_NOT_MEASURED_COLUMN"
    model.update(homes=[], changing_zone=None)
    g: dict[str, Any] = dict(
        version=VERSION,
        room=room,
        demand=copy.deepcopy(demand),
        parameters=asdict(p),
        front_parameters=asdict(cfg),
        inventory=inv,
        model=model,
        spatial_padding_mm=margin,
        point=point,
        conditions=asdict(c),
        snapshots=[],
        schedule_diagnostics=[],
        hierarchy_failures=complete_inventory_conflicts(inv, demand),
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        project_functional_status="INPUT_REQUIRED",
        closed_door_subproof_scope="CABINET_DOORS_CLOSED; OPEN_SWEEPS_REQUIRE_SEPARATE_R14_PROOF",
        legacy_field_semantics=dict(
            cell_height_mm="CONDITIONAL_DOOR_FACE_HEIGHT_NOT_INTERNAL_CLEAR_HEIGHT",
            plinth_mm="CONDITIONAL_BOTTOM_DOOR_FACE_ELEVATION_NOT_VERIFIED_BASE_STRUCTURE",
            shelf_mm="CONDITIONAL_DOOR_FACE_VERTICAL_GAP_NOT_VERIFIED_BOARD_THICKNESS",
        ),
        conditional_reach_mm=[100, 1800, p.reach_horizontal_mm],
        actual_reach_status="INPUT_REQUIRED",
        native_solves=0,
    )
    ref = sizing_snapshot(g, 1, [], "NETWORK")
    g["cross_section"] = dict(
        status="NECESSARY_CONDITIONS_PASS"
        if max(a[3] for a in ref["aisles"]) <= model["clear"][3] and p.aisle_mm <= 1500
        else "SECTION_REJECTED_FOR_THIS_TEMPLATE",
        branch_north_edge_mm=ref["branch_y"] + p.aisle_mm - p.aisle_mm // 2,
        scope="FINITE_TEMPLATE_NECESSARY_CONDITION_ONLY",
    )
    blockers = [*ref["aisles"], model["landing"], *[u["bounds_mm"] for u in inv["cabinet_units"]]]
    probes = []

    def row(start: int, y: int, w: int, d: int, label: str) -> None:
        for x in range(start, model["clear"][2] - w + 1, w + p.person_gap_mm):
            if len(model["homes"]) == 53:
                break
            b = [x, y, x + w, y + d]
            fail = not covered(rectangle(b), [rectangle(model["clear"])]) or any(
                intersection(rectangle(b), rectangle(q)) for q in blockers
            )
            for h in model["homes"]:
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
            else:
                model["homes"].append(
                    dict(
                        bounds_mm=b,
                        pose="STANDING",
                        region=label,
                        yaw_degrees=0
                        if (w, d) == (c.transport_width_mm, c.transport_depth_mm)
                        else 90,
                    )
                )

    upper = model["main_y"] + p.aisle_mm - p.aisle_mm // 2 + margin
    lower = model["main_y"] - p.aisle_mm // 2 - margin
    north = ref["branch_y"] + p.aisle_mm - p.aisle_mm // 2 + margin
    row(
        model["waiting_start_x"],
        upper,
        c.transport_width_mm,
        c.transport_depth_mm,
        "EAST_NORTH_NORMAL",
    )
    row(
        model["waiting_start_x"],
        lower - c.transport_depth_mm,
        c.transport_width_mm,
        c.transport_depth_mm,
        "EAST_SOUTH_NORMAL",
    )
    row(
        model["cabinet_start_x"], north, c.transport_depth_mm, c.transport_width_mm, "NORTH_ROTATED"
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
            for s in proposed:
                q = sizing_snapshot(g, shift, s["actions"], s["id"])
                q["evaluation"] = validate_use(room, inv, model, p, q)
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
    g["static_status"] = "STATIC_GEOMETRY_PASS" if static else "STATIC_GEOMETRY_REJECTED"
    g["metrics"] = dict(
        cabinets=11,
        columns=22,
        compartments=110,
        home_count=len(model["homes"]),
        rotated_home_count=sum(h["yaw_degrees"] == 90 for h in model["homes"]),
        reserved_aisle_mm=p.aisle_mm,
        cabinet_footprint_mm2=sum(
            (u["bounds_mm"][2] - u["bounds_mm"][0]) * (u["bounds_mm"][3] - u["bounds_mm"][1])
            for u in inv["cabinet_units"]
        ),
    )
    return g


def closed_door_flow(g: dict[str, Any]) -> dict[str, Any]:
    ready = (
        g["static_status"] == "STATIC_GEOMETRY_PASS"
        and g["cross_section"]["status"] == "NECESSARY_CONDITIONS_PASS"
    )
    flows = [simulate_sizing_shift(g, shift, None) for shift in (1, 2)] if ready else []
    return dict(
        geometry=g,
        shifts=flows,
        margins=geometry_margins(g, flows),
        proof_scope=(
            "CLOSED_CABINET_DOOR_GEOMETRY_AND_MOVEMENT_ONLY; NEVER_A_COMPLETE_DOOR_OR_STORAGE_PASS"
        ),
    )
