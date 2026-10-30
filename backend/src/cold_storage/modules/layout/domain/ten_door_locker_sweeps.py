"""Required, independent per-door 3-D subproof, separate from closed-door flow."""

import math
from typing import Any

from cold_storage.modules.layout.domain.changing_room_motion import door_hits_box, prism
from cold_storage.modules.layout.domain.functional_room_fit import covered, rectangle
from cold_storage.modules.layout.domain.reverse_sizing_margins import rectangle_gap
from cold_storage.modules.layout.domain.ten_door_locker_model import DoorSensitivity


def sensitivity_doors(inv: dict[str, Any], p: DoorSensitivity) -> list[dict[str, Any]]:
    p.checked()
    cols = {c["id"]: c for c in inv["vertical_columns"]}
    out = []
    for c in inv["compartments"]:
        col = cols[c["column_id"]]
        x, _, r, top = col["bounds_mm"]
        right = p.hinges == "MIRRORED" and col["offset_x_mm"] == 425
        hx = r - (425 - p.left_frame_mm - p.leaf_width_mm) if right else x + p.left_frame_mm
        direction = -1 if right else 1
        z = p.bottom_mm + (c["tier"] - 1) * (p.leaf_height_mm + p.tier_gap_mm)
        out.append(
            dict(
                id=c["independent_door_id"],
                compartment_id=c["id"],
                column_id=c["column_id"],
                unit_id=c["unit_id"],
                kind="OUTWARD_HINGED_90",
                hinge_side="RIGHT" if right else "LEFT",
                conditional_front_frame_mm=[
                    p.left_frame_mm,
                    425 - p.left_frame_mm - p.leaf_width_mm,
                ],
                hinge_mm=[hx, top],
                direction=[direction, 1],
                radius_mm=p.leaf_width_mm,
                thickness_mm=p.leaf_thickness_mm,
                z_interval_mm=[z, z + p.leaf_height_mm],
                angle_degrees=p.angle_degrees,
                arc_mm=[
                    [
                        round(hx + direction * p.leaf_width_mm * math.cos(i * math.pi / 40)),
                        round(top + p.leaf_width_mm * math.sin(i * math.pi / 40)),
                    ]
                    for i in range(21)
                ],
                open_leaf_mm=[[hx, top], [hx, top + p.leaf_width_mm]],
                actual_hardware_status="INPUT_REQUIRED",
                source_label="HYPOTHETICAL_NOT_APPROVED",
                body_collision_model="ORIGINAL_ANALYTIC_QUARTER_DISK_WITH_THICKNESS",
            )
        )
    return out


def sweep_box(d: dict[str, Any]) -> list[int]:
    x, y = d["hinge_mm"]
    dx, dy = d["direction"]
    r = d["radius_mm"] + d["thickness_mm"]
    z, top = d["z_interval_mm"]
    return [min(x, x + dx * r), min(y, y + dy * r), z, max(x, x + dx * r), max(y, y + dy * r), top]


def validate_door_event(
    g: dict[str, Any],
    snapshot: dict[str, Any],
    people: list[dict[str, Any]],
    registry: list[dict[str, Any]],
    *,
    expected_people_count: int,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    by_cell = {d["compartment_id"]: d for d in registry}
    if len(registry) != 110 or len(by_cell) != 110 or len({d["id"] for d in registry}) != 110:
        raise ValueError("110_DISTINCT_DOOR_IDENTITIES_REQUIRED")
    actual_people = {v["id"] for v in people}
    if len(people) != expected_people_count or len(actual_people) != len(people):
        errors.append(dict(code="LIVE_PEOPLE_COUNT_OR_IDENTITY_MISMATCH"))
    doors = []
    clearances = []
    cells = {c["id"]: c for c in g["inventory"]["compartments"]}
    for action in snapshot["actions"]:
        c = cells[action["compartment_id"]]
        d = by_cell[c["id"]]
        if (
            c["assigned_person_id"] != action["person_id"]
            or c["shift"] != snapshot["shift"]
            or c["column_id"] != action["column_id"]
            or action["person_id"] not in actual_people
            or d["id"] != c["independent_door_id"]
            or d["unit_id"] != c["unit_id"]
        ):
            errors.append(dict(code="DOOR_PERSON_SHIFT_PHYSICAL_BINDING_MISMATCH", door=d["id"]))
        doors.append(d)
    for d in doors:
        b = sweep_box(d)
        if (
            not covered(rectangle([b[0], b[1], b[3], b[4]]), [rectangle(g["model"]["clear"])])
            or b[5] > 3000
        ):
            errors.append(dict(code="DOOR_SWEEP_OUTSIDE_FINISHED_ROOM", door=d["id"]))
        for obj in [*people, *g["inventory"]["cabinet_units"]]:
            if obj["id"] == d["unit_id"]:
                continue
            if any(door_hits_box(d, v) for v in obj["volumes_mm"]):
                errors.append(dict(code="HINGED_DOOR_3D_COLLISION", door=d["id"], object=obj["id"]))
            if any(
                max(v[2], d["z_interval_mm"][0]) < min(v[5], d["z_interval_mm"][1])
                for v in obj["volumes_mm"]
            ):
                clearances.append(
                    dict(
                        extra_mm=rectangle_gap([b[0], b[1], b[3], b[4]], obj["bounds_mm"]),
                        door=d["id"],
                        object=obj["id"],
                        bounds_mm=[b[0], b[1], b[3], b[4]],
                        definition=(
                            "CONSERVATIVE_SWEEP_BOUNDING_BOX_LOWER_BOUND; NOT_ERGONOMIC_APPROVAL"
                        ),
                    )
                )
        for index, aisle in enumerate(snapshot["aisles"]):
            if door_hits_box(d, prism(aisle, 0, 3000), projection=True):
                errors.append(
                    dict(code="DOOR_SWEEP_REDUCES_RESERVED_PASSAGE", door=d["id"], aisle=index)
                )
    for i, a in enumerate(doors):
        for other in doors[i + 1 :]:
            if door_hits_box(a, sweep_box(other)):
                errors.append(
                    dict(code="SIMULTANEOUS_DOOR_SWEEPS_CONFLICT", door=a["id"], other=other["id"])
                )
    return dict(
        status="VERIFIED_UNDER_HYPOTHESES" if not errors else "CONFIGURATION_NOT_FIT",
        conflicts=errors,
        doors=doors,
        people_count=len(people),
        minimum_clearance_lower_bound=min(
            clearances, key=lambda x: (x["extra_mm"], x["door"], x["object"])
        )
        if clearances
        else None,
        scope="ALL_ACTIVE_FULL_3D_SWEEPS_AT_THIS_ACTUAL_FLOW_EVENT; NOT_ACTUAL_HARDWARE_APPROVAL",
    )


def check_flow_doors(
    g: dict[str, Any], flows: list[dict[str, Any]], p: DoorSensitivity
) -> dict[str, Any]:
    registry = sensitivity_doors(g["inventory"], p)
    snapshots = {s["id"]: s for s in g["snapshots"]}
    checks = []
    counts: dict[tuple[int, str, str], int] = {}
    for flow in flows:
        for event in flow["events"]:
            if event["operation"] not in {"OPEN_FOR_RETRIEVE", "OPEN_FOR_STORE"}:
                continue
            proof = validate_door_event(
                g,
                snapshots[event["batch"]],
                event["proof"]["people_before"],
                registry,
                expected_people_count=event["inside_people"],
            )
            for d in proof["doors"]:
                key = (flow["shift"], d["compartment_id"], event["operation"])
                counts[key] = counts.get(key, 0) + 1
            checks.append(
                dict(shift=flow["shift"], event=event["index"], batch=event["batch"], proof=proof)
            )
    served = {d["compartment_id"] for check in checks for d in check["proof"]["doors"]}
    expected = {c["id"] for c in g["inventory"]["compartments"] if c["assigned_person_id"]}
    expected_events = {
        (c["shift"], c["id"], op)
        for c in g["inventory"]["compartments"]
        if c["assigned_person_id"]
        for op in ("OPEN_FOR_RETRIEVE", "OPEN_FOR_STORE")
    }
    complete = (
        len(flows) == 2
        and all(f["completed_users"] == 53 for f in flows)
        and served == expected
        and set(counts) == expected_events
        and all(v == 1 for v in counts.values())
    )
    okay = complete and all(c["proof"]["status"] == "VERIFIED_UNDER_HYPOTHESES" for c in checks)
    minima = [
        dict(c["proof"]["minimum_clearance_lower_bound"], shift=c["shift"], event=c["event"])
        for c in checks
        if c["proof"]["minimum_clearance_lower_bound"] is not None
    ]
    return dict(
        status="CONDITIONAL_DOOR_EVENTS_PASS"
        if okay
        else "CONFIGURATION_NOT_FIT"
        if any(c["proof"]["conflicts"] for c in checks)
        else "NOT_EVALUATED_INCOMPLETE_CLOSED_DOOR_FLOW",
        complete_106_person_coverage=complete,
        served_compartments=len(served),
        required_open_events=212,
        checked_open_events=sum(counts.values()),
        minimum_door_clearance_lower_bound=min(minima, key=lambda x: (x["extra_mm"], x["door"]))
        if minima
        else None,
        registry=registry,
        events=checks,
        actual_hardware_status="INPUT_REQUIRED",
        storage_hygiene_status="INPUT_REQUIRED",
    )
