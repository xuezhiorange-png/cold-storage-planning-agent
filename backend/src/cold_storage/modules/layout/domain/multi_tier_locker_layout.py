"""Deterministic R4 sensitivity arrangements and occupied-space checks; zero solve.

These are supplied-template snapshots, not approved functional layouts. A failed
template is not a proof of room infeasibility or a new P1/Stage B constraint.
"""

import copy
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.domain.access_routing import _path_envelopes
from cold_storage.modules.layout.domain.changing_locker_screening import _free_spans
from cold_storage.modules.layout.domain.functional_room_fit import (
    STATES,
    connected,
    covered,
    intersection,
    rectangle,
)
from cold_storage.modules.layout.domain.multi_tier_locker_model import (
    TIERS,
    MultiTierHypothesis,
    service_waves,
    storage_inventory,
)

VERSION = "multi-tier-locker-snapshot-r11-r4@1.0.0"


def inventory_conflicts(inventory: dict[str, Any], demand: dict[str, Any]) -> list[str]:
    errors = []
    units = {v["id"]: v for v in inventory["cabinet_units"]}
    columns = {v["id"]: v for v in inventory["vertical_columns"]}
    cells = {v["id"]: v for v in inventory["compartments"]}
    people = {v["person_id"]: v for v in inventory["person_assignments"]}
    if (
        len(units) != len(inventory["cabinet_units"])
        or len(columns) != len(inventory["vertical_columns"])
        or len(cells) != len(inventory["compartments"])
        or len(people) != sum(demand["shift_users"])
    ):
        errors.append("DUPLICATE_OR_MISSING_PHYSICAL_OR_PERSON_IDENTITY")
    if len(columns) != demand["total_columns"] or len(cells) != demand["total_capacity"]:
        errors.append("INVENTORY_CAPACITY_MISMATCH")
    referenced_columns = [c for unit in units.values() for c in unit["column_ids"]]
    referenced_cells = [c for col in columns.values() for c in col["compartment_ids"]]
    if (
        len(referenced_columns) != len(set(referenced_columns))
        or set(referenced_columns) != set(columns)
        or len(referenced_cells) != len(set(referenced_cells))
        or set(referenced_cells) != set(cells)
    ):
        errors.append("PHYSICAL_HIERARCHY_MUST_COVER_EACH_CHILD_ONCE")
    for shift in (1, 2):
        if (
            sum(c["shift"] == shift for c in columns.values())
            != demand["columns_per_shift"][shift - 1]
        ):
            errors.append("SHIFT_COLUMN_CAPACITY_MISMATCH")
    assigned: list[str] = []
    for person in people.values():
        owned = person["compartment_ids"]
        assigned.extend(owned)
        if len(owned) != demand["compartments_per_person"]:
            errors.append("PERSON_COMPARTMENT_COUNT_MISMATCH")
        for key in owned:
            cell = cells.get(key)
            if (
                cell is None
                or cell["assigned_person_id"] != person["person_id"]
                or cell["shift"] != person["shift"]
            ):
                errors.append("CROSS_PERSON_OR_CROSS_SHIFT_COMPARTMENT_REUSE")
    if len(assigned) != len(set(assigned)):
        errors.append("COMPARTMENT_NOT_INDEPENDENTLY_ASSIGNED")
    if set(assigned) != {c["id"] for c in cells.values() if c["assigned_person_id"] is not None}:
        errors.append("COMPARTMENT_ASSIGNMENT_BACK_REFERENCE_MISMATCH")
    doors = [c["independent_door_id"] for c in cells.values()]
    if len(doors) != len(set(doors)):
        errors.append("INDEPENDENT_COMPARTMENT_DOOR_REQUIRED")
    for column in columns.values():
        unit = units.get(column["unit_id"])
        keys = column["compartment_ids"]
        if unit is None or column["id"] not in unit["column_ids"]:
            errors.append("COLUMN_WITHOUT_PHYSICAL_CABINET_UNIT")
            continue
        if len(keys) != TIERS or len(set(keys)) != TIERS:
            errors.append("FIVE_DISTINCT_COMPARTMENTS_PER_COLUMN_REQUIRED")
        previous = -1
        for level, key in enumerate(keys, 1):
            cell = cells.get(key)
            if cell is None or cell["column_id"] != column["id"] or cell["tier"] != level:
                errors.append("COMPARTMENT_COLUMN_TIER_MISMATCH")
                continue
            a, z, b, t = cell["elevation_bounds_mm"]
            if (
                not 0 <= a < b <= unit["dimensions_mm"][0]
                or not 0 <= z < t <= unit["dimensions_mm"][2]
                or z < previous
            ):
                errors.append("COMPARTMENT_ELEVATION_OVERLAP_OR_CABINET_OVERFLOW")
            previous = t
    return sorted(set(errors))


def portal_route_check(
    room: dict[str, Any],
    points: list[list[int]],
    width: int,
    clear: list[int],
    aisles: list[list[int]],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Same integer-mm P2 envelopes and original portal-width endpoint rule."""
    try:
        if len(points) < 2 or len({tuple(p) for p in points}) < 2:
            raise ValueError("NONZERO_ROUTE_REQUIRED")
        envelopes = [
            list(r.bounds_mm) for r in _path_envelopes([(p[0], p[1]) for p in points], width)
        ]
        proven = []
        for portal in room["portals"]:
            a, b = portal["segment_mm"]
            for end in (points[0], points[-1]):
                on_face = (
                    a[0] == b[0] == end[0]
                    and min(a[1], b[1]) + width // 2
                    <= end[1]
                    <= max(a[1], b[1]) - (width - width // 2)
                    or a[1] == b[1] == end[1]
                    and min(a[0], b[0]) + width // 2
                    <= end[0]
                    <= max(a[0], b[0]) - (width - width // 2)
                )
                if on_face and width <= portal["clear_width_mm"]:
                    proven.append(portal["id"])
        expected = {p["id"] for p in room["portals"]}
        valid = (
            len(expected) == len(room["portals"]) == 2
            and set(proven) == expected
            and all(
                covered(rectangle(e), [rectangle(clear)])
                and covered(rectangle(e), [rectangle(a) for a in aisles])
                and not any(intersection(rectangle(e), rectangle(b["bounds_mm"])) for b in blockers)
                for e in envelopes
            )
        )
        return dict(
            valid=valid,
            proven_portal_ids=sorted(set(proven)),
            envelopes_mm=envelopes,
            points_mm=points,
            width_mm=width,
        )
    except (ValueError, TypeError, IndexError):
        return dict(
            valid=False, proven_portal_ids=[], envelopes_mm=[], points_mm=points, width_mm=width
        )


def validate_snapshot(
    room: dict[str, Any],
    demand: dict[str, Any],
    inventory: dict[str, Any],
    p: MultiTierHypothesis,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Check total occupancy independently of simultaneous cabinet-front actions."""
    issues: list[dict[str, Any]] = []

    def fail(code: str, *ids: str) -> None:
        issues.append(dict(code=code, components=list(ids)))

    try:
        clear = rectangle(snapshot["finished_clear_bounds_mm"])
        bodies = [*inventory["cabinet_units"], *snapshot["benches"]]
        people = snapshot["people"]
        active = snapshot["active_actions"]
        operations = snapshot["operation_zones"]
        aisles = snapshot["aisles"]
        routes = portal_route_check(
            room, snapshot["route_points_mm"], p.aisle_mm, list(clear), aisles, bodies
        )
        if not routes["valid"]:
            fail("BOTH_ORIGINAL_PORTALS_FULL_WIDTH_ROUTE_UNPROVEN")
        for i, body in enumerate(bodies):
            box = rectangle(body["bounds_mm"])
            if not covered(box, [clear]):
                fail("BODY_OUTSIDE_FINISHED_ROOM", body["id"])
            if body.get("dimensions_mm", [0, 0, 0])[2] > p.clear_height_mm:
                fail("CABINET_ABOVE_CLEAR_HEIGHT", body["id"])
            for other in bodies[i + 1 :]:
                if intersection(box, rectangle(other["bounds_mm"])):
                    fail("PHYSICAL_BODY_OVERLAP", body["id"], other["id"])
        net = [*aisles, *routes["envelopes_mm"]]
        for aisle in aisles:
            if not covered(rectangle(aisle), [clear]):
                fail("NET_AISLE_OUTSIDE_FINISHED_ROOM")
            if min(aisle[2] - aisle[0], aisle[3] - aisle[1]) < p.aisle_mm:
                fail("HYPOTHETICAL_NET_AISLE_WIDTH_SHORTFALL")
        reached = {
            i
            for i, a in enumerate(aisles)
            if routes["valid"]
            and any(intersection(rectangle(a), rectangle(e)) for e in routes["envelopes_mm"])
        }
        while True:
            expanded = reached | {
                i
                for i, a in enumerate(aisles)
                if any(connected(rectangle(a), rectangle(aisles[j]), p.aisle_mm) for j in reached)
            }
            if expanded == reached:
                break
            reached = expanded
        usable = [aisles[i] for i in reached]
        # Both declared net aisles and actual route envelopes remain clear.
        occupied = [*bodies, *people, *operations, *snapshot["door_exclusions"]]
        for c in occupied:
            r = rectangle(c["bounds_mm"])
            if not covered(r, [clear]):
                fail("OCCUPIED_SPACE_OUTSIDE_FINISHED_ROOM", c["id"])
            if any(intersection(r, rectangle(a)) for a in net):
                fail("OCCUPIED_SPACE_INTRUDES_NET_PASSAGE", c["id"])
        ids = [c["id"] for c in people]
        shift = snapshot["shift"]
        current = {
            a["person_id"]: a for a in inventory["person_assignments"] if a["shift"] == shift
        }
        if any(s in {"USE", "SHIFT_CHANGE"} for s in snapshot["states"]):
            if len(ids) != demand["simultaneous_room_users"] or set(ids) != set(current):
                fail("TOTAL_53_ROOM_OCCUPANTS_MUST_BE_PRESERVED")
            if any(
                a["person_id"] not in current
                or a["compartment_id"] not in current[a["person_id"]]["compartment_ids"]
                for a in active
            ):
                fail("ACTIVE_PERSON_COMPARTMENT_ASSIGNMENT_MISMATCH")
        if len(ids) != len(set(ids)):
            fail("DUPLICATE_PERSON_POSITION")
        if len(active) > (p.front_concurrent_users or 0):
            fail("HYPOTHETICAL_FRONT_CONCURRENCY_EXCEEDED")
        if len({a["column_id"] for a in active}) != len(active):
            fail("CONCURRENT_OPERATORS_SHARE_SAME_COLUMN_FRONT")
        if len({a["person_id"] for a in active}) != len(active):
            fail("PERSON_ACTIVE_AT_MULTIPLE_COMPARTMENTS")
        cells = {c["id"]: c for c in inventory["compartments"]}
        cols = {c["id"]: c for c in inventory["vertical_columns"]}
        for action in active:
            person = next((c for c in people if c["id"] == action["person_id"]), None)
            cell = cells.get(action["compartment_id"])
            if person is None or cell is None or cell["column_id"] != action["column_id"]:
                fail("COMPARTMENT_SERVICE_WITNESS_MISSING")
                continue
            col = cols[action["column_id"]]
            a, b, c, d = person["bounds_mm"]
            x, y, r, t = col["bounds_mm"]
            if not (x <= a < c <= r and (b == t if col["front"] == "N" else d == y)):
                fail("OPERATOR_NOT_AT_ASSOCIATED_COLUMN_FRONT", person["id"])
            z = cell["elevation_bounds_mm"]
            if z[1] < p.reach_low_mm or z[3] > p.reach_high_mm:
                fail("COMPARTMENT_OUTSIDE_HYPOTHETICAL_REACH_RANGE", cell["id"])
            if any(state in {"CLEANING", "MAINTENANCE"} for state in snapshot["states"]):
                serviced = action.get("serviced_compartment_ids", [])
                if set(serviced) != set(col["compartment_ids"]):
                    fail("ALL_FIVE_TIERS_SERVICE_COVERAGE_REQUIRED", col["id"])
                for key in serviced:
                    tier = cells[key]["elevation_bounds_mm"]
                    if tier[1] < p.reach_low_mm or tier[3] > p.reach_high_mm:
                        fail("SERVICE_TIER_OUTSIDE_HYPOTHETICAL_REACH_RANGE", key)
        for i, person in enumerate(people):
            r = rectangle(person["bounds_mm"])
            if [r[2] - r[0], r[3] - r[1]] != [p.person_width_mm, p.person_depth_mm]:
                fail("PERSON_SPACE_DIMENSION_MISMATCH", person["id"])
            if not any(
                connected(r, rectangle(a), min(p.person_width_mm, p.person_depth_mm))
                for a in usable
            ):
                fail("PERSON_NOT_CONNECTED_TO_PORTAL_AISLE", person["id"])
            for other in [*bodies, *people[i + 1 :], *snapshot["door_exclusions"]]:
                if intersection(r, rectangle(other["bounds_mm"])):
                    fail("PERSON_BODY_PERSON_OR_DOOR_CONFLICT", person["id"], other["id"])
            for op in operations:
                if op.get("person_id") != person["id"] and intersection(
                    r, rectangle(op["bounds_mm"])
                ):
                    fail("PERSON_OTHER_OPERATION_CONFLICT", person["id"], op["id"])
        for index, op in enumerate(operations):
            r = rectangle(op["bounds_mm"])
            if not any(connected(r, rectangle(a), min(r[2] - r[0], r[3] - r[1])) for a in usable):
                fail("OPERATION_NOT_CONNECTED_TO_PORTAL_AISLE", op["id"])
            for body in bodies:
                if intersection(r, rectangle(body["bounds_mm"])):
                    fail("OPERATION_BODY_CONFLICT", op["id"], body["id"])
            for other in operations[index + 1 :]:
                if intersection(r, rectangle(other["bounds_mm"])):
                    fail("INDEPENDENT_OPERATION_SPACES_OVERLAP", op["id"], other["id"])
        for door in snapshot["door_exclusions"]:
            for body in bodies:
                if intersection(rectangle(door["bounds_mm"]), rectangle(body["bounds_mm"])):
                    fail("DOOR_SWEEP_BODY_CONFLICT", door["id"], body["id"])
        return dict(
            status="SNAPSHOT_VALID_UNDER_HYPOTHESES" if not issues else "CONFIGURATION_NOT_FIT",
            conflicts=issues,
            route=routes,
            people_count=len(people),
            active_operator_count=len(active),
            other_room_users=len(people) - len(active),
            all_person_ids=ids,
        )
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return dict(
            status="INPUT_REQUIRED",
            conflicts=issues,
            missing_inputs=["complete_snapshot:" + str(exc)],
        )


def _place_units(
    room: dict[str, Any], inventory: dict[str, Any], p: MultiTierHypothesis
) -> list[str]:
    x0, y0, x1, y1 = rectangle(room["local_bounds_mm"])
    if x0 or y0 or x1 < y1:
        return ["THIS_LONG_HORIZONTAL_WALL_TEMPLATE_NOT_APPLICABLE"]
    by_id = {c["id"]: c for c in inventory["vertical_columns"]}
    for row in (1, 2):
        selected = [
            u
            for u in inventory["cabinet_units"]
            if (u["shift"] if p.arrangement == "OPPOSED" else 1) == row
        ]
        blocked = []
        wall = 0 if row == 1 else y1
        for portal in room["portals"]:
            a, b = portal["segment_mm"]
            if a[1] == b[1] == wall:
                blocked.append((min(a[0], b[0]), max(a[0], b[0])))
        spans = _free_spans(x1, blocked, p.finish_inset_mm)
        cursor = p.finish_inset_mm
        for unit in selected:
            w, d, _h = unit["dimensions_mm"]
            available = [(max(lo, cursor), hi) for lo, hi in spans if max(lo, cursor) + w <= hi]
            if not available:
                return ["PORTAL_SEGMENTED_CABINET_UNIT_POSITIONS_INSUFFICIENT"]
            x = available[0][0]
            y = p.finish_inset_mm if row == 1 else y1 - p.finish_inset_mm - d
            if y < 0:
                return ["CABINET_DEPTH_EXCEEDS_ROOM"]
            unit["bounds_mm"] = [x, y, x + w, y + d]
            unit["front"] = "N" if row == 1 else "S"
            for key in unit["column_ids"]:
                col = by_id[key]
                a = x + col["offset_x_mm"]
                col["bounds_mm"] = [a, y, a + p.column_width_mm, y + d]
                col["front"] = unit["front"]
            cursor = x + w
    return []


def _snapshot(
    room: dict[str, Any],
    demand: dict[str, Any],
    inv: dict[str, Any],
    p: MultiTierHypothesis,
    shift: int,
    actions: list[dict[str, Any]],
    states: list[str],
) -> dict[str, Any]:
    _, _, length, depth = room["local_bounds_mm"]
    cols = {c["id"]: c for c in inv["vertical_columns"]}
    south = [q for q in room["portals"] if all(v[1] == 0 for v in q["segment_mm"])]
    east = [q for q in room["portals"] if all(v[0] == length for v in q["segment_mm"])]
    north = [q for q in room["portals"] if all(v[1] == depth for v in q["segment_mm"])]
    if len(south) != 1 or len(east) + len(north) != 1:
        raise ValueError("TEMPLATE_REQUIRES_ORIGINAL_SOUTH_AND_EAST_OR_NORTH_PORTALS")
    first = south[0]
    second = (east or north)[0]
    sx = sum(v[0] for v in first["segment_mm"]) // 2
    half, after = p.aisle_mm // 2, p.aisle_mm - p.aisle_mm // 2
    lower = (
        p.finish_inset_mm
        + p.column_depth_mm
        + (p.front_clearance_mm if shift == 1 or p.arrangement == "SINGLE_SIDE" else 0)
    )
    upper = (
        depth
        - p.finish_inset_mm
        - (
            p.column_depth_mm + p.front_clearance_mm
            if shift == 2 and p.arrangement == "OPPOSED"
            else 0
        )
    )
    # Reserve only this snapshot's active bank; the other bank is explicitly closed.
    center = lower + half if shift == 1 or p.arrangement == "SINGLE_SIDE" else upper - after
    if east:
        lo, hi = sorted(v[1] for v in second["segment_mm"])
        center = min(max(center, lo + half), hi - after)
    if center - half < lower or center + after > upper:
        raise ValueError("ACTIVE_BANK_AND_ORIGINAL_PORTAL_CANNOT_SHARE_THIS_STRAIGHT_AISLE")
    net_low, net_high = center - half, center + after
    # Any enlargement is measured free floor, not a reduction in the net width.
    if shift == 1 and east:
        net_high = min(upper, max(net_high, max(v[1] for v in second["segment_mm"])))
    clear = [
        p.finish_inset_mm,
        p.finish_inset_mm,
        length - p.finish_inset_mm,
        depth - p.finish_inset_mm,
    ]
    aisles = [[clear[0], net_low, clear[2], net_high], [sx - half, 0, sx + after, center + after]]
    points = [[sx, 0], [sx, center]]
    if east:
        points.append([length, center])
    else:
        nx = sum(v[0] for v in second["segment_mm"]) // 2
        points += [[nx, center], [nx, depth]]
        aisles.append([nx - half, center - half, nx + after, depth])
    bodies = inv["cabinet_units"]
    people = []
    ops = []
    doors = []
    for action in actions:
        col = cols[action["column_id"]]
        x, y, r, t = col["bounds_mm"]
        py = t if col["front"] == "N" else y - p.person_depth_mm
        people.append(
            dict(
                id=action["person_id"],
                role="FRONT_OPERATOR",
                bounds_mm=[x, py, x + p.person_width_mm, py + p.person_depth_mm],
                compartment_id=action["compartment_id"],
                column_id=col["id"],
            )
        )
        oy = t if col["front"] == "N" else y - p.front_clearance_mm
        ops.append(
            dict(
                id=action["compartment_id"] + "-operation",
                person_id=action["person_id"],
                bounds_mm=[x, oy, r, oy + p.front_clearance_mm],
            )
        )
        if p.cabinet_door_sweep_mm:
            dy = t if col["front"] == "N" else y - p.cabinet_door_sweep_mm
            doors.append(
                dict(
                    id=action["compartment_id"] + "-sweep",
                    bounds_mm=[x, dy, r, dy + p.cabinet_door_sweep_mm],
                )
            )
    benches = []
    max_body_end = max(u["bounds_mm"][2] for u in bodies)
    for i in range(p.bench_count):
        x = max_body_end + 200 + i * p.bench_width_mm
        benches.append(
            dict(
                id=f"bench-{i + 1}",
                role="BENCH",
                bounds_mm=[x, 0, x + p.bench_width_mm, p.bench_depth_mm],
            )
        )
        ops.append(
            dict(
                id=f"bench-{i + 1}-operation",
                bounds_mm=[
                    x,
                    p.bench_depth_mm,
                    x + p.bench_width_mm,
                    p.bench_depth_mm + p.bench_operation_mm,
                ],
            )
        )
    if p.room_door_sweep_mm:
        for portal in room["portals"]:
            a, b = portal["segment_mm"]
            if a[1] == b[1]:
                y = 0 if a[1] == 0 else depth - p.room_door_sweep_mm
                box = [min(a[0], b[0]), y, max(a[0], b[0]), y + p.room_door_sweep_mm]
            else:
                x = 0 if a[0] == 0 else length - p.room_door_sweep_mm
                box = [x, min(a[1], b[1]), x + p.room_door_sweep_mm, max(a[1], b[1])]
            doors.append(dict(id=portal["id"] + "-hypothetical-sweep", bounds_mm=box))
    # Every non-operating user still receives a distinct occupied rectangle.
    expected = (
        [a["person_id"] for a in inv["person_assignments"] if a["shift"] == shift]
        if "USE" in states
        else [a["person_id"] for a in actions]
    )
    active_ids = {a["person_id"] for a in actions}
    # Distinct cells of this explicit grid never overlap each other. Check static
    # blockers once, then assign cells, rather than repeating the same scan/user.
    slots = []
    blockers = [rectangle(b["bounds_mm"]) for b in [*bodies, *benches, *people, *ops, *doors]]
    net_boxes = [rectangle(a) for a in aisles]
    for py in (net_low - p.person_depth_mm, net_high):
        if py < clear[1] or py + p.person_depth_mm > clear[3]:
            continue
        for x in range(clear[0], clear[2] - p.person_width_mm + 1, p.person_width_mm):
            cell_box = (x, py, x + p.person_width_mm, py + p.person_depth_mm)
            if not any(intersection(cell_box, b) for b in [*blockers, *net_boxes]):
                slots.append(list(cell_box))
    unplaced = []
    waiting = [key for key in expected if key not in active_ids]
    for index, key in enumerate(waiting):
        if index >= len(slots):
            unplaced.append(key)
        else:
            people.append(dict(id=key, role="OTHER_CHANGING_OCCUPANT", bounds_mm=slots[index]))
    return dict(
        shift=shift,
        states=states,
        active_actions=copy.deepcopy(actions),
        people=people,
        benches=benches,
        operation_zones=ops,
        door_exclusions=doors,
        aisles=aisles,
        route_points_mm=points,
        finished_clear_bounds_mm=clear,
        unplaced_people=unplaced,
        inactive_compartment_doors="HYPOTHETICALLY_CLOSED",
        transition_paths="NOT_EVALUATED",
    )


def assess_template(
    room: dict[str, Any], demand: dict[str, Any], p: MultiTierHypothesis
) -> dict[str, Any]:
    """Build finite sensitivity snapshots; keep actual-project status INPUT_REQUIRED."""
    inv = storage_inventory(demand, p)
    errors = inventory_conflicts(inv, demand)
    errors += _place_units(room, inv, p)
    missing = []
    for key in ("front_concurrent_users", "cabinet_door_sweep_mm", "room_door_sweep_mm"):
        if getattr(p, key) is None:
            missing.append(key)
    if (
        p.front_concurrent_users is not None
        and p.front_concurrent_users > demand["simultaneous_room_users"]
    ):
        raise ValueError("FRONT_CONCURRENCY_CANNOT_EXCEED_ROOM_OCCUPANCY")
    _, _, length, width = room["local_bounds_mm"]
    rows = 2 if p.arrangement == "OPPOSED" else 1
    required_width = rows * p.column_depth_mm + p.aisle_mm
    if width - 2 * p.finish_inset_mm < required_width:
        errors.append("CABINET_AND_NET_AISLE_WIDTH_SHORTFALL_FOR_THIS_TEMPLATE")
    snapshots: list[dict[str, Any]] = []
    if not errors and not missing:
        for shift in (1, 2):
            waves = service_waves(inv, shift, p.front_concurrent_users or 1)
            for index, actions in enumerate(waves, 1):
                try:
                    witness = _snapshot(
                        room, demand, inv, p, shift, actions, ["USE", "SHIFT_CHANGE"]
                    )
                    result = validate_snapshot(room, demand, inv, p, witness)
                    snapshots.append(
                        dict(id=f"S{shift}-W{index:02}", witness=witness, evaluation=result)
                    )
                except (ValueError, KeyError, IndexError) as exc:
                    errors.append(str(exc))
                    break
            # Sequential cleaning/maintenance is a separate unapproved scenario.
            for col in [c for c in inv["vertical_columns"] if c["shift"] == shift]:
                action = dict(
                    person_id="hypothetical-service-worker",
                    column_id=col["id"],
                    compartment_id=col["compartment_ids"][0],
                    serviced_compartment_ids=col["compartment_ids"],
                )
                try:
                    witness = _snapshot(
                        room, demand, inv, p, shift, [action], ["CLEANING", "MAINTENANCE"]
                    )
                    snapshots.append(
                        dict(
                            id=col["id"] + "-service",
                            witness=witness,
                            evaluation=validate_snapshot(room, demand, inv, p, witness),
                        )
                    )
                except (ValueError, KeyError, IndexError) as exc:
                    errors.append(str(exc))
                    break
    bad = [s for s in snapshots if s["evaluation"]["status"] != "SNAPSHOT_VALID_UNDER_HYPOTHESES"]
    return dict(
        version=VERSION,
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        source_label="HYPOTHETICAL_NOT_APPROVED",
        project_functional_status="INPUT_REQUIRED",
        geometry_status="INPUT_REQUIRED"
        if missing
        else "CONFIGURATION_NOT_FIT"
        if errors or bad
        else "SNAPSHOTS_VALID_UNDER_HYPOTHESES",
        room=room,
        demand=demand,
        parameters=asdict(p),
        inventory=inv,
        required_width_mm=required_width,
        available_width_mm=width - 2 * p.finish_inset_mm,
        column_row_length_mm=(
            max(demand["columns_per_shift"]) if rows == 2 else demand["total_columns"]
        )
        * p.column_width_mm,
        missing_hypothetical_inputs=missing,
        template_failures=sorted(set(errors)),
        snapshots=snapshots,
        failed_snapshot_count=len(bad),
        separation_satisfied="INPUT_REQUIRED",
        operating_states=list(STATES),
        transition_paths="NOT_EVALUATED",
        approval_limit="STATIC_SUPPLIED_TEMPLATE_SNAPSHOTS_ONLY_NOT_CONDITIONAL_FIT",
        formulas=[
            "floor footprint counts physical units, never stacked compartments",
            "53 room occupants = front operators + other changing occupants in each use wave",
            "original P2 full-width envelopes and exact rectangle intersections",
        ],
        warnings=[
            "No transition/evacuation/throughput or reach-ergonomics approval",
            "No new layout candidate or Native solve; historical Access remains independent",
            "Internal divider and two-compartment hygiene options both require review",
        ],
    )
