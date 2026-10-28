"""Opt-in R5 H5 template evaluation, installation, use and adjacent-batch paths.

All parameters are explicit hypotheses, never P1 or approved functional inputs.
The template catalogue is finite and deterministic, without Native/layout search.
"""

import copy
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.access_routing import _path_envelopes
from cold_storage.modules.layout.domain.changing_room_motion import (
    door_hits_box,
    door_sector,
    network_path,
    overlap3,
    prism,
    seated_person,
    standing_person,
    swept_segments,
    verify_movement,
)
from cold_storage.modules.layout.domain.functional_room_fit import (
    covered,
    integer,
    intersection,
    rectangle,
)
from cold_storage.modules.layout.domain.multi_tier_locker_layout import inventory_conflicts
from cold_storage.modules.layout.domain.multi_tier_locker_model import (
    MultiTierHypothesis,
    service_waves,
    storage_inventory,
)

VERSION = "h5-practical-changing-r11-r5@1.0.0"


@dataclass(frozen=True)
class H5Hypothesis:
    arrangement: str = "SINGLE_SIDE"
    door_kind: str = "OUTWARD_HINGED_90"
    hinge: str = "LEFT"
    column_width_mm: int = 400
    column_depth_mm: int = 500
    cabinet_height_mm: int = 1800
    cell_height_mm: int = 300
    plinth_mm: int = 100
    shelf_mm: int = 20
    columns_per_unit: int = 2
    finish_mm: int = 20
    installation_gap_mm: int = 20
    unit_gap_mm: int = 20
    end_clearance_mm: int = 100
    segment_gap_mm: int = 1200
    frame_mm: int = 20
    leaf_thickness_mm: int = 15
    operator_standoff_mm: int = 380
    aisle_mm: int = 1200
    person_width_mm: int = 400
    person_depth_mm: int = 600
    standing_height_mm: int = 1800
    seated_height_mm: int = 1300
    person_gap_mm: int = 20
    front_concurrency: int = 4
    changing_operation_width_mm: int = 800
    changing_operation_depth_mm: int = 900
    bench_count: int = 2
    bench_length_mm: int = 1800
    bench_depth_mm: int = 400
    bench_height_mm: int = 450
    seat_pitch_mm: int = 600
    bench_gap_mm: int = 500
    room_door_intrusion_mm: int = 0
    entrance_landing_mm: int = 1200
    reach_low_mm: int = 100
    reach_high_mm: int = 1700
    reach_horizontal_mm: int = 600
    clear_height_mm: int = 3000

    def checked(self) -> None:
        if self.arrangement not in {"SINGLE_SIDE", "OPPOSED", "SEGMENTED"}:
            raise ValueError("EXPLICIT_H5_TEMPLATE_REQUIRED")
        if self.door_kind not in {"OUTWARD_HINGED_90", "NO_PLAN_INTRUSION"} or self.hinge not in {
            "LEFT",
            "RIGHT",
        }:
            raise ValueError("EXPLICIT_SUPPORTED_DOOR_REQUIRED")
        for k, v in asdict(self).items():
            if isinstance(v, str):
                continue
            integer(
                v,
                0
                if k
                in {
                    "finish_mm",
                    "installation_gap_mm",
                    "unit_gap_mm",
                    "room_door_intrusion_mm",
                    "person_gap_mm",
                }
                else 1,
            )
            if v > 60000:
                raise ValueError("BOUNDED_HYPOTHESIS_REQUIRED")
        if self.front_concurrency > 53 or self.columns_per_unit > 6 or self.bench_count > 8:
            raise ValueError("BOUNDED_H5_REVIEW_REQUIRED")
        if (
            self.changing_operation_width_mm < self.person_width_mm
            or self.changing_operation_depth_mm < self.person_depth_mm
        ):
            raise ValueError("CHANGING_OPERATION_MUST_CONTAIN_FULL_PERSON")
        if self.reach_high_mm <= self.reach_low_mm or self.bench_depth_mm >= self.person_depth_mm:
            raise ValueError("EXPLICIT_REACH_AND_BENCH_LEG_SPACE_REQUIRED")


def _rect_lines(points: list[list[int]], width: int) -> list[list[int]]:
    return [list(r.bounds_mm) for r in _path_envelopes([(x, y) for x, y in points], width)]


def _place(room: dict[str, Any], inv: dict[str, Any], p: H5Hypothesis) -> dict[str, Any]:
    length, depth = room["local_bounds_mm"][2:]
    clear = [p.finish_mm, p.finish_mm, length - p.finish_mm, depth - p.finish_mm]
    start = p.finish_mm + p.aisle_mm // 2 + p.end_clearance_mm
    cols = {c["id"]: c for c in inv["vertical_columns"]}
    cursors = {1: start, 2: start}
    for unit in inv["cabinet_units"]:
        row = unit["shift"] if p.arrangement == "OPPOSED" else 1
        if p.arrangement == "SEGMENTED" and unit["id"] == "S2-U01":
            cursors[1] += p.segment_gap_mm
        x = cursors[row]
        w, d, h = unit["dimensions_mm"]
        y = (
            p.finish_mm + p.installation_gap_mm
            if row == 1
            else depth - p.finish_mm - p.installation_gap_mm - d
        )
        unit.update(
            bounds_mm=[x, y, x + w, y + d],
            front="N" if row == 1 else "S",
            volumes_mm=[prism([x, y, x + w, y + d], 0, h)],
        )
        for key in unit["column_ids"]:
            col = cols[key]
            cx = x + col["offset_x_mm"]
            col.update(bounds_mm=[cx, y, cx + p.column_width_mm, y + d], front=unit["front"])
        cursors[row] = x + w + p.unit_gap_mm
    end = max(u["bounds_mm"][2] for u in inv["cabinet_units"])
    bend = end + p.aisle_mm // 2 + p.end_clearance_mm
    waiting_start = bend + p.aisle_mm // 2 + p.person_width_mm // 2
    east = next(q for q in room["portals"] if q["segment_mm"][0][0] == length)
    south = next(q for q in room["portals"] if q["segment_mm"][0][1] == q["segment_mm"][1][1] == 0)
    main_y = sum(v[1] for v in east["segment_mm"]) // 2
    south_x = sum(v[0] for v in south["segment_mm"]) // 2
    net_bottom = main_y - p.aisle_mm // 2
    net_top = main_y + p.aisle_mm - p.aisle_mm // 2
    landing = [
        length - p.entrance_landing_mm,
        min(v[1] for v in east["segment_mm"]),
        length,
        max(v[1] for v in east["segment_mm"]),
    ]
    openings = [
        [length - p.finish_mm, east["segment_mm"][0][1], length, east["segment_mm"][1][1]],
        [south["segment_mm"][0][0], 0, south["segment_mm"][1][0], p.finish_mm or 1],
    ]
    # A finished opening throat is explicit; it does not move the historical Portal.
    openings = [b for b in openings if b[0] < b[2] and b[1] < b[3]]
    benches: list[dict[str, Any]] = []
    seat_boxes: list[dict[str, Any]] = []
    bench_start = max(waiting_start, max(v[0] for v in south["segment_mm"]) + p.end_clearance_mm)
    for j in range(p.bench_count):
        x = bench_start + j * (p.bench_length_mm + p.bench_gap_mm)
        y = net_bottom - p.person_depth_mm
        b: dict[str, Any] = dict(
            id=f"B{j + 1}",
            bounds_mm=[x, y, x + p.bench_length_mm, y + p.bench_depth_mm],
            height_mm=p.bench_height_mm,
        )
        b["volumes_mm"] = [prism(b["bounds_mm"], 0, p.bench_height_mm)]
        benches.append(b)
        for seat in range(p.bench_length_mm // p.seat_pitch_mm):
            sx = x + seat * p.seat_pitch_mm + (p.seat_pitch_mm - p.person_width_mm) // 2
            seat_boxes.append(
                dict(
                    bounds_mm=[sx, y, sx + p.person_width_mm, y + p.person_depth_mm],
                    bench_id=b["id"],
                )
            )
    main_route = [[length, main_y], [south_x, main_y], [south_x, 0]]
    trunk = _rect_lines(main_route, p.aisle_mm)
    homes: list[dict[str, Any]] = []
    changing_zone = [
        length - p.entrance_landing_mm - p.end_clearance_mm - p.changing_operation_width_mm,
        net_top,
        length - p.entrance_landing_mm - p.end_clearance_mm,
        net_top + p.changing_operation_depth_mm,
    ]
    needed = 53 - len(seat_boxes) - 1
    if needed < 1:
        raise ValueError("BENCH_TEMPLATE_MUST_KEEP_STANDING_AND_OPERATOR_USERS")
    blockers = [
        *trunk,
        changing_zone,
        landing,
        *[b["bounds_mm"] for b in benches],
        *[s["bounds_mm"] for s in seat_boxes],
        *[u["bounds_mm"] for u in inv["cabinet_units"]],
    ]
    for y in [net_top, net_bottom - p.person_depth_mm]:
        for x in range(
            waiting_start,
            length - p.finish_mm - p.person_width_mm + 1,
            p.person_width_mm + p.person_gap_mm,
        ):
            box = [x, y, x + p.person_width_mm, y + p.person_depth_mm]
            if covered(rectangle(box), [rectangle(clear)]) and not any(
                intersection(rectangle(box), rectangle(b)) for b in blockers
            ):
                homes.append(dict(bounds_mm=box, pose="STANDING"))
                if len(homes) == needed:
                    break
        if len(homes) == needed:
            break
    homes.append(dict(bounds_mm=changing_zone, pose="CHANGING_OPERATION_ENVELOPE"))
    homes += [dict(s, pose="SEATED") for s in seat_boxes]
    return dict(
        room=copy.deepcopy(room),
        changing_zone=changing_zone,
        clear=clear,
        openings=openings,
        landing=landing,
        benches=benches,
        homes=homes,
        main_route=main_route,
        main_y=main_y,
        south_x=south_x,
        branch_bend_x=bend,
        cabinet_start_x=start,
        waiting_start_x=waiting_start,
    )


def _people(
    inv: dict[str, Any],
    model: dict[str, Any],
    p: H5Hypothesis,
    shift: int,
    actions: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active = {a["person_id"]: a for a in actions}
    cols = {c["id"]: c for c in inv["vertical_columns"]}
    benches = {b["id"]: b for b in model["benches"]}
    people = []
    homes = []
    members = [a["person_id"] for a in inv["person_assignments"] if a["shift"] == shift]
    for key, slot in zip(members, model["homes"], strict=False):
        home = (
            standing_person(
                key, slot["bounds_mm"], p.standing_height_mm, "OTHER_CHANGING_OR_WAITING"
            )
            if slot["pose"] != "SEATED"
            else seated_person(
                key, slot["bounds_mm"], benches[slot["bench_id"]], p.seated_height_mm
            )
        )
        if slot["pose"] == "CHANGING_OPERATION_ENVELOPE":
            home["role"] = "CHANGING_OPERATOR"
            home["pose"] = "CHANGING_OPERATION_ENVELOPE"
            home["motion_scope"] = "HYPOTHETICAL_RECTANGULAR_CLOTHING_OPERATION_VOLUME"
        homes.append(home)
        if key in active:
            c = cols[active[key]["column_id"]]
            x, y, r, t = c["bounds_mm"]
            py = (
                t + p.operator_standoff_mm
                if c["front"] == "N"
                else y - p.operator_standoff_mm - p.person_depth_mm
            )
            person = standing_person(
                key,
                [x, py, x + p.person_width_mm, py + p.person_depth_mm],
                p.standing_height_mm,
                "FRONT_OPERATOR",
            )
            person.update(column_id=c["id"], compartment_id=active[key]["compartment_id"])
            people.append(person)
        else:
            people.append(copy.deepcopy(home))
    return people, homes


def _snapshot(
    room: dict[str, Any],
    inv: dict[str, Any],
    model: dict[str, Any],
    p: H5Hypothesis,
    shift: int,
    actions: list[dict[str, str]],
    key: str,
) -> dict[str, Any]:
    columns = {c["id"]: c for c in inv["vertical_columns"]}
    cells = {c["id"]: c for c in inv["compartments"]}
    people, homes = _people(inv, model, p, shift, actions)
    front = "N" if p.arrangement != "OPPOSED" or shift == 1 else "S"
    if front == "N":
        branch_y = (
            p.finish_mm
            + p.installation_gap_mm
            + p.column_depth_mm
            + p.operator_standoff_mm
            + p.person_depth_mm
            + p.aisle_mm // 2
        )
    else:
        branch_y = (
            room["local_bounds_mm"][3]
            - p.finish_mm
            - p.installation_gap_mm
            - p.column_depth_mm
            - p.operator_standoff_mm
            - p.person_depth_mm
            - (p.aisle_mm - p.aisle_mm // 2)
        )
    start = model["cabinet_start_x"] + p.column_width_mm // 2
    bend = model["branch_bend_x"]
    branch = [[start, branch_y], [bend, branch_y], [bend, model["main_y"]]]
    # Union of trunk and branch; a separate segment joins the bend to trunk.
    aisles = (
        _rect_lines(branch, p.aisle_mm)
        + _rect_lines(model["main_route"], p.aisle_mm)
        + _rect_lines([[bend, model["main_y"]], [model["south_x"], model["main_y"]]], p.aisle_mm)
    )
    # Reserve full turning/end bays at internal centerline nodes, never beyond Portal.
    for x, y in [*branch, [model["south_x"], model["main_y"]]]:
        half = p.aisle_mm // 2
        aisles.append([x - half, y - half, x + p.aisle_mm - half, y + p.aisle_mm - half])
    lines = [
        list(pair)
        for path in [
            branch,
            model["main_route"],
            [[bend, model["main_y"]], [model["south_x"], model["main_y"]]],
        ]
        for pair in zip(path, path[1:], strict=False)
        if pair[0] != pair[1]
    ]
    doors = [
        door_sector(
            columns[a["column_id"]],
            cells[a["compartment_id"]],
            kind=p.door_kind,
            frame_mm=p.frame_mm,
            thickness_mm=p.leaf_thickness_mm,
            hinge=p.hinge,
        )
        for a in actions
    ]
    return dict(
        id=key,
        shift=shift,
        states=["USE", "STAGGERED_SHIFT_CHANGE"],
        people=people,
        home_people=homes,
        actions=actions,
        doors=doors,
        aisles=aisles,
        branch_centerline_mm=branch,
        main_route_mm=model["main_route"],
        network_lines=lines,
        branch_y=branch_y,
        main_y=model["main_y"],
        movement_order="CLOSE_CABINET_DOORS_RETURN_TO_HOMES_THEN_NEXT_OPERATORS",
        simultaneous_room_users=53,
        other_shift="NOT_SIMULTANEOUS",
        room_doors="HYPOTHETICAL_OPEN_RECESSED"
        if p.room_door_intrusion_mm == 0
        else "HYPOTHETICAL_INWARD_EXCLUSION",
    )


def validate_use(
    room: dict[str, Any],
    inv: dict[str, Any],
    model: dict[str, Any],
    p: H5Hypothesis,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    issues = []

    def fail(code: str, *ids: str) -> None:
        issues.append(dict(code=code, components=list(ids)))

    bodies = [*inv["cabinet_units"], *model["benches"]]
    people = snapshot["people"]
    aisles = snapshot["aisles"]
    inside = [rectangle(model["clear"]), *[rectangle(b) for b in model["openings"]]]
    members = {
        a["person_id"]: set(a["compartment_ids"])
        for a in inv["person_assignments"]
        if a["shift"] == snapshot["shift"]
    }
    if len(people) != 53 or {v["id"] for v in people} != set(members):
        fail("ALL_53_DISTINCT_SHIFT_USERS_REQUIRED")
    if len(snapshot["actions"]) > p.front_concurrency or len(
        {a["column_id"] for a in snapshot["actions"]}
    ) != len(snapshot["actions"]):
        fail("FRONT_CONCURRENCY_OR_COLUMN_CONFLICT")
    if len(model["homes"]) != 53:
        fail("53_DISTINCT_HOME_POSITIONS_NOT_AVAILABLE")
    for b in bodies:
        if not covered(rectangle(b["bounds_mm"]), [rectangle(model["clear"])]):
            fail("BODY_OUTSIDE_FINISHED_ROOM", b["id"])
        if b["volumes_mm"][0][5] > p.clear_height_mm:
            fail("BODY_EXCEEDS_CLEAR_HEIGHT", b["id"])
    for b in bodies:
        if intersection(rectangle(b["bounds_mm"]), rectangle(model["landing"])):
            fail("BODY_INTRUDES_ENTRANCE_LANDING", b["id"])
    for i, b in enumerate(bodies):
        for other in bodies[i + 1 :]:
            if any(overlap3(a, c) for a in b["volumes_mm"] for c in other["volumes_mm"]):
                fail("FIXED_BODY_COLLISION", b["id"], other["id"])
    for aisle in aisles:
        if not covered(rectangle(aisle), inside):
            fail("NET_AISLE_OUTSIDE_FINISHED_ROOM")
        for b in bodies:
            if intersection(rectangle(aisle), rectangle(b["bounds_mm"])):
                fail("FIXED_BODY_INTRUDES_NET_AISLE", b["id"])
    required_actions = {
        (a["person_id"], a["compartment_id"], a["column_id"]) for a in snapshot["actions"]
    }
    represented = {
        (v["id"], v.get("compartment_id"), v.get("column_id"))
        for v in people
        if v["role"] == "FRONT_OPERATOR"
    }
    if required_actions != represented or len(required_actions) != len(snapshot["actions"]):
        fail("ACTIVE_OPERATOR_ACTION_BINDING_MISMATCH")
    expected_doors = [
        door_sector(
            next(c for c in inv["vertical_columns"] if c["id"] == a["column_id"]),
            next(c for c in inv["compartments"] if c["id"] == a["compartment_id"]),
            kind=p.door_kind,
            frame_mm=p.frame_mm,
            thickness_mm=p.leaf_thickness_mm,
            hinge=p.hinge,
        )
        for a in snapshot["actions"]
    ]
    if snapshot["doors"] != expected_doors:
        fail("ACTIVE_DOOR_SWEEP_BINDING_MISMATCH")
    for i, person in enumerate(people):
        if intersection(rectangle(person["bounds_mm"]), rectangle(model["landing"])):
            fail("PERSON_INTRUDES_ENTRANCE_LANDING", person["id"])
        if any(v[2] < 0 or v[5] > p.clear_height_mm for v in person["volumes_mm"]):
            fail("PERSON_EXCEEDS_CLEAR_HEIGHT", person["id"])
        if not covered(rectangle(person["bounds_mm"]), [rectangle(model["clear"])]):
            fail("PERSON_OUTSIDE_FINISHED_ROOM", person["id"])
        if any(intersection(rectangle(person["bounds_mm"]), rectangle(a)) for a in aisles):
            fail("STATIONARY_PERSON_INTRUDES_NET_AISLE", person["id"])
        for obj in [*bodies, *people[i + 1 :]]:
            if any(overlap3(a, b) for a in person["volumes_mm"] for b in obj["volumes_mm"]):
                fail("PERSON_3D_BODY_COLLISION", person["id"], obj["id"])
        if person["role"] == "FRONT_OPERATOR":
            if person["compartment_id"] not in members.get(person["id"], set()):
                fail("WRONG_SHIFT_COMPARTMENT", person["id"])
            c = next(v for v in inv["compartments"] if v["id"] == person["compartment_id"])
            col = next(v for v in inv["vertical_columns"] if v["id"] == c["column_id"])
            x, y, right, top = col["bounds_mm"]
            py = (
                top + p.operator_standoff_mm
                if col["front"] == "N"
                else y - p.operator_standoff_mm - p.person_depth_mm
            )
            if (
                person["bounds_mm"] != [x, py, x + p.person_width_mm, py + p.person_depth_mm]
                or person["column_id"] != col["id"]
            ):
                fail("OPERATOR_NOT_AT_ASSIGNED_COLUMN", person["id"])
            z = c["elevation_bounds_mm"]
            if (
                z[1] < p.reach_low_mm
                or z[3] > p.reach_high_mm
                or p.operator_standoff_mm > p.reach_horizontal_mm
            ):
                fail("HYPOTHETICAL_REACH_RANGE_NOT_MET", person["id"], c["id"])
    projections = []
    for door in snapshot["doors"]:
        if door["kind"] != "NO_PLAN_INTRUSION":
            hx, hy = door["hinge_mm"]
            ux, vy = door["direction"]
            rad = door["radius_mm"] + door["thickness_mm"]
            bounds = (
                min(hx, hx + ux * rad),
                min(hy, hy + vy * rad),
                max(hx, hx + ux * rad),
                max(hy, hy + vy * rad),
            )
            if (
                not covered(bounds, [rectangle(model["clear"])])
                or door["z_interval_mm"][1] > p.clear_height_mm
            ):
                fail("DOOR_SWEEP_OUTSIDE_FINISHED_ROOM", door["id"])
        for obj in [*bodies, *people]:
            if obj["id"] == door["unit_id"]:
                continue  # attachment to its own frame is intentional
            hits = any(door_hits_box(door, b) for b in obj["volumes_mm"])
            projected = any(door_hits_box(door, b, projection=True) for b in obj["volumes_mm"])
            if projected:
                projections.append(
                    dict(
                        door=door["id"],
                        object=obj["id"],
                        collision_3d=hits,
                        z_interval_mm=door["z_interval_mm"],
                    )
                )
            if hits:
                fail("HINGED_DOOR_3D_COLLISION", door["id"], obj["id"])
        for aisle in aisles:
            if door_hits_box(door, prism(aisle, 0, p.clear_height_mm), projection=True):
                fail("DOOR_PROJECTION_REDUCES_RESERVED_PASSAGE", door["id"])
    for i, a in enumerate(snapshot["doors"]):
        for b in snapshot["doors"][i + 1 :]:
            # Different assigned columns. Conservative bounding solids ensure
            # simultaneous leaves do not intersect even between sampled angles.
            hx, hy = b["hinge_mm"]
            sx, sy = b["direction"]
            r = b["radius_mm"] + b["thickness_mm"]
            z0, z1 = b["z_interval_mm"]
            if b["kind"] != "NO_PLAN_INTRUSION" and door_hits_box(
                a,
                [
                    min(hx, hx + sx * r),
                    min(hy, hy + sy * r),
                    z0,
                    max(hx, hx + sx * r),
                    max(hy, hy + sy * r),
                    z1,
                ],
            ):
                fail("SIMULTANEOUS_DOOR_SWEEPS_CONFLICT", a["id"], b["id"])
    portal_results = []
    for q, end in zip(
        room["portals"], [snapshot["main_route_mm"][0], snapshot["main_route_mm"][-1]], strict=True
    ):
        a, b = q["segment_mm"]
        half = p.aisle_mm // 2
        after = p.aisle_mm - half
        fit = (
            a[0] == b[0] == end[0] and min(a[1], b[1]) + half <= end[1] <= max(a[1], b[1]) - after
        ) or (
            a[1] == b[1] == end[1] and min(a[0], b[0]) + half <= end[0] <= max(a[0], b[0]) - after
        )
        okay = fit and p.aisle_mm <= q["clear_width_mm"]
        portal_results.append(
            dict(
                id=q["id"],
                valid=okay,
                original_segment_mm=q["segment_mm"],
                clear_width_mm=q["clear_width_mm"],
            )
        )
        if not okay:
            fail("ORIGINAL_PORTAL_FULL_WIDTH_CONNECTION_FAILED", q["id"])
    if p.room_door_intrusion_mm:
        fail("ACTUAL_ROOM_DOOR_SWING_MUST_BE_RESOLVED_BEFORE_CLEAR_PASSAGE")
    return dict(
        status="STATIC_TEMPLATE_VERIFIED_UNDER_HYPOTHESES"
        if not issues
        else "CONFIGURATION_NOT_FIT",
        conflicts=issues,
        portal_results=portal_results,
        door_projection_vs_3d=projections,
        people_count=len(people),
        front_operators=sum(v["role"] == "FRONT_OPERATOR" for v in people),
        changing_operators=sum(v["role"] == "CHANGING_OPERATOR" for v in people),
        bench_users=sum(v["role"] == "BENCH_USER" for v in people),
        other_users=sum(v["role"] == "OTHER_CHANGING_OR_WAITING" for v in people),
        reserved_aisle_mm=p.aisle_mm,
        functional_status="INPUT_REQUIRED",
    )


def adjacent_transition(
    before: dict[str, Any],
    after: dict[str, Any],
    inv: dict[str, Any],
    model: dict[str, Any],
    p: H5Hypothesis,
) -> dict[str, Any]:
    if (
        validate_use(model["room"], inv, model, p, before)["status"]
        != "STATIC_TEMPLATE_VERIFIED_UNDER_HYPOTHESES"
        or validate_use(model["room"], inv, model, p, after)["status"]
        != "STATIC_TEMPLATE_VERIFIED_UNDER_HYPOTHESES"
    ):
        return dict(
            status="NOT_EVALUATED",
            reason="VALID_ENDPOINT_SNAPSHOTS_REQUIRED",
            shift=before["shift"],
            moves=[],
        )
    current = {v["id"]: copy.deepcopy(v) for v in before["people"]}
    homes = {v["id"]: v for v in before["home_people"]}
    final = {v["id"]: v for v in after["people"]}
    sequence = [(a["person_id"], homes[a["person_id"]]) for a in before["actions"]] + [
        (a["person_id"], final[a["person_id"]]) for a in after["actions"]
    ]
    moves = []
    for key, target in sequence:
        source = current[key]
        if source["bounds_mm"] == target["bounds_mm"]:
            continue

        def point(o: dict[str, Any]) -> list[int]:
            b = o["bounds_mm"]
            return [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2]

        start = point(source)
        end = point(target)
        sy = before["branch_y"] if source["role"] == "FRONT_OPERATOR" else before["main_y"]
        ey = after["branch_y"] if target["role"] == "FRONT_OPERATOR" else after["main_y"]
        connectors = [[start, [start[0], sy]], [[end[0], ey], end]]
        lines = [*before["network_lines"], *connectors]
        path = network_path(start, end, lines)
        if path is None:
            moves.append(
                dict(person_id=key, status="CONFIGURATION_NOT_FIT", reason="NO_AISLE_NETWORK_PATH")
            )
            break
        allowed = [
            *before["aisles"],
            *[
                [v[0], v[1], v[3], v[4]]
                for c in connectors
                if c[0] != c[1]
                for v in swept_segments(
                    c, p.person_width_mm, p.person_depth_mm, p.standing_height_mm
                )
            ],
        ]
        proof = verify_movement(
            path,
            source,
            target,
            [v for k, v in current.items() if k != key],
            [*inv["cabinet_units"], *model["benches"]],
            model["clear"],
            p.person_width_mm,
            p.person_depth_mm,
            p.standing_height_mm,
            allowed,
            [],
            p.clear_height_mm,
        )
        proof.update(
            person_id=key,
            start_pose=source["pose"],
            end_pose=target["pose"],
            people_before=copy.deepcopy(list(current.values())),
        )
        moves.append(proof)
        if proof["status"] != "CONTINUOUS_PATH_VERIFIED_UNDER_HYPOTHESES":
            break
        current[key] = copy.deepcopy(target)
    complete = set(current) == set(final) and all(
        all(
            current[k].get(field) == final[k].get(field)
            for field in (
                "bounds_mm",
                "volumes_mm",
                "pose",
                "role",
                "bench_id",
                "column_id",
                "compartment_id",
            )
        )
        for k in current
    )
    okay = complete and all(
        m["status"] == "CONTINUOUS_PATH_VERIFIED_UNDER_HYPOTHESES" for m in moves
    )
    return dict(
        status="ADJACENT_BATCH_TRANSITION_VERIFIED_UNDER_HYPOTHESES"
        if okay
        else "NOT_FULLY_VERIFIED",
        shift=before["shift"],
        from_snapshot=before["id"],
        to_snapshot=after["id"],
        moves=moves,
        endpoint_all_53_match=complete,
        occupancy_maintained=53,
        concurrent_movers=1,
        doors_during_movement="CLOSED_BY_EXPLICIT_PROCESS_ASSUMPTION",
        simultaneous_through_traffic="NOT_EVALUATED",
        all_other_batch_transitions="NOT_EVALUATED",
        seated_stand_up="NOT_EVALUATED",
        hygiene="INPUT_REQUIRED",
    )


def evaluate_h5(room: dict[str, Any], demand: dict[str, Any], p: H5Hypothesis) -> dict[str, Any]:
    p.checked()
    if room["local_bounds_mm"] != [0, 0, 26331, 3250] or demand["simultaneous_room_users"] != 53:
        raise ValueError("EXACT_H5_ROOM_AND_53_USER_PROJECT_SCOPE_REQUIRED")
    rp = MultiTierHypothesis(
        column_width_mm=p.column_width_mm,
        column_depth_mm=p.column_depth_mm,
        cabinet_height_mm=p.cabinet_height_mm,
        compartment_clear_height_mm=p.cell_height_mm,
        plinth_mm=p.plinth_mm,
        shelf_mm=p.shelf_mm,
        columns_per_unit=p.columns_per_unit,
    )
    inv = storage_inventory(demand, rp)
    errors = inventory_conflicts(inv, demand)
    model = _place(room, inv, p)
    snapshots = []
    for shift in (1, 2):
        for i, actions in enumerate(service_waves(inv, shift, p.front_concurrency), 1):
            s = _snapshot(room, inv, model, p, shift, actions, f"S{shift}-W{i:02}")
            s["evaluation"] = validate_use(room, inv, model, p, s)
            snapshots.append(s)
    transitions = []
    for shift in (1, 2):
        seq = [s for s in snapshots if s["shift"] == shift]
        if len(seq) >= 2:
            transitions.append(adjacent_transition(seq[0], seq[1], inv, model, p))
    metrics = dict(
        columns=demand["total_columns"],
        compartments=demand["total_capacity"],
        hypothetical_procurement_units=len(inv["cabinet_units"]),
        occupied_cabinet_length_mm=sum(u["dimensions_mm"][0] for u in inv["cabinet_units"]),
        cabinet_footprint_mm2=sum(
            u["dimensions_mm"][0] * u["dimensions_mm"][1] for u in inv["cabinet_units"]
        ),
        reserved_aisle_mm=p.aisle_mm,
        bench_count=len(model["benches"]),
        bench_seat_capacity=sum(p.bench_length_mm // p.seat_pitch_mm for _ in model["benches"]),
        distinct_home_positions=len(model["homes"]),
        changing_operation_zone_mm=model["changing_zone"],
        snapshots=len(snapshots),
        static_pass_count=sum(
            s["evaluation"]["status"] == "STATIC_TEMPLATE_VERIFIED_UNDER_HYPOTHESES"
            for s in snapshots
        ),
        adjacent_batch_pass_count=sum(
            t["status"] == "ADJACENT_BATCH_TRANSITION_VERIFIED_UNDER_HYPOTHESES"
            for t in transitions
        ),
    )
    return dict(
        version=VERSION,
        room=copy.deepcopy(room),
        demand=demand,
        parameters=asdict(p),
        inventory=inv,
        model=model,
        snapshots=snapshots,
        transitions=transitions,
        metrics=metrics,
        hierarchy_failures=errors,
        project_functional_status="INPUT_REQUIRED",
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        source_label="HYPOTHETICAL_NOT_APPROVED",
        template_status="TEMPLATE_AND_ADJACENT_TRANSITIONS_VERIFIED_UNDER_HYPOTHESES"
        if not errors
        and metrics["static_pass_count"] == len(snapshots)
        and metrics["adjacent_batch_pass_count"] == 2
        else "CONFIGURATION_NOT_FULLY_VERIFIED",
        hygiene=dict(
            internal_divider="INPUT_REQUIRED",
            two_compartment_separation="INPUT_REQUIRED",
            flow_direction="EAST_ENTRY_TO_SOUTH_SORTING_REFERENCE_ONLY",
            cross_contamination="NOT_EVALUATED",
        ),
        unverified=[
            "actual cabinet catalogue, anchorage, fire and service clearances",
            "internal compartment clear volume and clothing storage fit",
            "selected hardware and door angles beyond the 90 degree hypothesis",
            "human posture, grasp, step/ladder, wheelchair and evacuation capability",
            "bench sit/stand transition and all batch transitions beyond first adjacent pair",
            "timing, queues, shift handover overlap, cleaning and maintenance task performance",
            "approved clean/unclean procedures and full hygienic segregation",
        ],
        formulas=[
            "columns_i=ceil(required_cells_i/5); original R4 demand and inventory",
            "cabinet footprint=sum(physical unit width*depth), not compartment count",
            "hinged door swept quarter disk x tier z interval; conservative thickness dilation",
            "continuous movement=union of axis-aligned body sweeps along each full segment",
        ],
        units="integer mm; mm2; people; compartments",
        native_solves=0,
    )
