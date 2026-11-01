"""New-room adapter reusing R11 H5 inventory, motion and analytic door checks.

No historical H5 room/Portal coordinates are accepted. The finite legacy sizing
adapter is explicitly unsupported for arbitrary rooms; this adapter proves only
the generated conditional geometry, never actual hardware/hygiene approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.autonomous_process_routes import _inward
from cold_storage.modules.layout.domain.changing_room_motion import (
    network_path,
    overlap3,
    prism,
    standing_person,
    swept_segments,
    verify_movement,
)
from cold_storage.modules.layout.domain.functional_room_fit import covered, intersection, rectangle
from cold_storage.modules.layout.domain.multi_tier_locker_model import storage_demand
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.ten_door_locker_model import (
    DoorSensitivity,
    complete_inventory,
)
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import (
    sensitivity_doors,
    validate_door_event,
)


def changing_dimensions() -> dict[str, Any]:
    users = 53
    pw, pd, gap = 450, 650, 100
    finish, installation = 20, 100
    main, branch = 2000, 1200
    cabinet_run = 11 * 850 + 10 * 100
    width = ((main + cabinet_run + 2 * (finish + installation) + 99) // 100) * 100
    per_row = (width - main - 2 * finish + gap) // (pw + gap)
    rows = (users + per_row - 1) // per_row
    waiting_top = finish + main
    for row in range(rows):
        waiting_top += pd
        if row % 2 == 0:
            waiting_top += branch
        elif row < rows - 1:
            waiting_top += gap
    cabinet_y = waiting_top + 200
    # Cabinet fronts N; body/900mm activity and branch corridor never coincide.
    branch_y = cabinet_y + 390 + 480 + 650 + 125 + 100 + branch // 2
    height = ((branch_y + branch // 2 + finish + 99) // 100) * 100
    return {
        "width_mm": width,
        "depth_mm": height,
        "users": users,
        "waiting_rows": rows,
        "homes_per_row": per_row,
        "cabinet_y_mm": cabinet_y,
        "branch_y_mm": branch_y,
        "main_mm": main,
        "branch_mm": branch,
        "finish_mm": finish,
        "person_mm": [pw, pd, 1800],
        "activity_mm": [600, 900],
        "waiting_gap_mm": gap,
        "cabinet_run_mm": cabinet_run,
        "operator_standoff_mm": 480,
        "formulas": [
            "W=round_up_100(main+11*850+10*100+2*(finish+installation))",
            "rows=ceil(53/floor((W-main-2*finish+gap)/(450+gap)))",
            "H from actual waiting rows, branch, cabinet, body/activity and finish geometry",
        ],
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
    }


def changing_layout(
    room: PlacedRectangleV1, columns: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    request = changing_dimensions()
    w, h = room.bounds_mm[2] - room.bounds_mm[0], room.bounds_mm[3] - room.bounds_mm[1]
    if (w, h) != (request["width_mm"], request["depth_mm"]):
        return {
            "status": "FUNCTIONAL_SIZE_REQUEST",
            "requested_shape_mm": [request["width_mm"], request["depth_mm"]],
            "current_shape_mm": [w, h],
            "design_users": 53,
            "full_flow_verified": False,
            "legacy_H5_adapter": "UNSUPPORTED_NON_HISTORICAL_ROOM_AND_PORTALS",
            "functional_status": "INPUT_REQUIRED",
            "requirements": request,
        }
    f = request["finish_mm"]
    main = request["main_mm"]
    branch = request["branch_mm"]
    clear = [f, f, w - f, h - f]
    demand = storage_demand([53, 53], 53, "INTERNAL_PARTITION")
    inv = complete_inventory(demand, DoorSensitivity("ALL_LEFT"))
    for i, unit in enumerate(inv["cabinet_units"]):
        x = f + main + 100 + i * 950
        y = request["cabinet_y_mm"]
        b = [x, y, x + 850, y + 390]
        unit.update(bounds_mm=b, front="N", volumes_mm=[prism(b, 0, 1800)])
        for col in inv["vertical_columns"]:
            if col["unit_id"] == unit["id"]:
                cx = x + col["offset_x_mm"]
                col.update(bounds_mm=[cx, y, cx + 425, y + 390], front="N")
    homes: list[dict[str, Any]] = []
    branches = []
    y = f + main
    for row in range(request["waiting_rows"]):
        if row % 2 == 0:
            aisle_y = y + 650 + branch // 2
            branches.append([f + main, y + 650, w - f, y + 650 + branch])
        else:
            aisle_y = y - branch // 2
        for i in range(request["homes_per_row"]):
            if len(homes) == 53:
                break
            x = f + main + i * 550
            homes.append({"bounds_mm": [x, y, x + 450, y + 650], "aisle_y": aisle_y})
        y += 650 + (branch if row % 2 == 0 else 100)
    aisles = [
        [f, f, f + main, h - f],
        [f, f, w - f, f + main],
        *branches,
        [f + main, request["branch_y_mm"] - 600, w - f, request["branch_y_mm"] + 600],
    ]
    lines = [
        [[f + main // 2, f + 325], [f + main // 2, h - f - 325]],
        [[f + main // 2, f + main // 2], [w - f - 225, f + main // 2]],
    ]
    for ay in sorted({q["aisle_y"] for q in homes} | {request["branch_y_mm"]}):
        lines.append([[f + main // 2, ay], [w - f - 225, ay]])
    local_columns = []
    for col in columns:
        b = col["bbox_mm"]
        a = room.bounds_mm
        if max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]):
            box = [b[0] - a[0], b[1] - a[1], b[2] - a[0], b[3] - a[1]]
            local_columns.append(
                {"id": col["id"], "bounds_mm": box, "volumes_mm": [prism(box, 0, 3000)]}
            )
    bodies = [*inv["cabinet_units"], *local_columns]
    static = []
    for i, body in enumerate(inv["cabinet_units"]):
        if not covered(rectangle(body["bounds_mm"]), [rectangle(clear)]):
            static.append({"body": body["id"], "code": "CABINET_OUTSIDE_CLEAR_ROOM"})
        for other in [*inv["cabinet_units"][:i], *local_columns]:
            if intersection(rectangle(body["bounds_mm"]), rectangle(other["bounds_mm"])):
                static.append(
                    {"body": body["id"], "other": other["id"], "code": "CABINET_BODY_COLLISION"}
                )
    for i, q in enumerate(homes):
        b = q["bounds_mm"]
        if not covered(rectangle(b), [rectangle(clear)]):
            static.append({"home": i + 1, "code": "HOME_OUTSIDE_CLEAR_ROOM"})
        for obj in bodies:
            if intersection(rectangle(b), rectangle(obj["bounds_mm"])):
                static.append({"home": i + 1, "body": obj["id"], "code": "HOME_BODY_COLLISION"})
        if any(intersection(rectangle(b), rectangle(a)) for a in aisles):
            static.append({"home": i + 1, "code": "HOME_OCCUPIES_RESERVED_AISLE"})
        for other in homes[:i]:
            if intersection(rectangle(b), rectangle(other["bounds_mm"])):
                static.append({"home": i + 1, "code": "HOME_PERSON_COLLISION"})
    return {
        "status": "STATIC_GEOMETRY_READY"
        if not static and len(homes) == 53
        else "CONFIGURATION_NOT_FIT",
        "requirements": request,
        "room_bounds_mm": [0, 0, w, h],
        "clear": clear,
        "inventory": inv,
        "homes": homes,
        "aisles": aisles,
        "network": lines,
        "bodies": bodies,
        "static_conflicts": static,
        "design_users": 53,
        "full_flow_verified": False,
        "legacy_H5_adapter": "UNSUPPORTED_NON_HISTORICAL_ROOM_AND_PORTALS",
        "functional_status": "INPUT_REQUIRED",
    }


def evaluate_changing_use(g: Mapping[str, Any]) -> dict[str, Any]:
    """All 53 hold real homes during each cabinet cycle; two independent shifts."""
    if g["status"] != "STATIC_GEOMETRY_READY":
        return {
            "status": "NOT_EVALUATED_UPSTREAM_REJECTED",
            "full_flow_verified": False,
            "design_users": 53,
            "functional_status": "INPUT_REQUIRED",
        }
    inv = g["inventory"]
    cols = {q["id"]: q for q in inv["vertical_columns"]}
    results = []
    for shift in (1, 2):
        assignments = [a for a in inv["person_assignments"] if a["shift"] == shift]
        people = {
            a["person_id"]: standing_person(a["person_id"], q["bounds_mm"], 1800, "PERSON")
            for a, q in zip(assignments, g["homes"], strict=True)
        }
        events = []
        door_count = {"ALL_LEFT": 0, "MIRRORED": 0}
        errors = []
        for assignment, home in zip(assignments, g["homes"], strict=True):
            pid = assignment["person_id"]
            person = people[pid]
            cellid = assignment["compartment_ids"][0]
            cell = next(c for c in inv["compartments"] if c["id"] == cellid)
            col = cols[cell["column_id"]]
            b = col["bounds_mm"]
            cx = (b[0] + b[2]) // 2
            oy = b[3] + 480
            target = standing_person(pid, [cx - 225, oy, cx + 225, oy + 650], 1800, "PERSON")
            start = [
                (person["bounds_mm"][0] + person["bounds_mm"][2]) // 2,
                (person["bounds_mm"][1] + person["bounds_mm"][3]) // 2,
            ]
            end = [cx, oy + 325]
            link1 = [start, [start[0], home["aisle_y"]]]
            link2 = [end, [cx, g["requirements"]["branch_y_mm"]]]
            path = network_path(start, end, [*g["network"], link1, link2])
            others = [v for k, v in people.items() if k != pid]
            allowed = [*g["aisles"], person["bounds_mm"], target["bounds_mm"]]
            if path:
                allowed.extend(
                    [
                        [
                            min(a[0], b[0]) - 225,
                            min(a[1], b[1]) - 325,
                            max(a[0], b[0]) + 225,
                            max(a[1], b[1]) + 325,
                        ]
                        for a, b in (link1, link2)
                    ]
                )
                proof = verify_movement(
                    path,
                    person,
                    target,
                    others,
                    g["bodies"],
                    g["clear"],
                    450,
                    650,
                    1800,
                    allowed,
                    [],
                    3000,
                )
            else:
                proof = {
                    "status": "CONFIGURATION_NOT_FIT",
                    "conflicts": [{"code": "NO_NETWORK_PATH"}],
                }
            if proof["status"] != "CONTINUOUS_PATH_VERIFIED_UNDER_HYPOTHESES":
                errors.extend(proof["conflicts"])
                events.append({"person": pid, "move": proof})
                break
            assert path is not None
            action = {"person_id": pid, "compartment_id": cellid, "column_id": col["id"]}
            snapshot = {"shift": shift, "actions": [action], "aisles": g["aisles"]}
            at_front = [*others, target]
            door_checks: dict[str, dict[str, Any]] = {}
            for hinges in ("ALL_LEFT", "MIRRORED"):
                registry = sensitivity_doors(inv, DoorSensitivity(hinges))
                door_checks[hinges] = {}
                for phase in ("TAKE_AND_CLOSE", "STORE_AND_CLOSE"):
                    check = validate_door_event(
                        {"inventory": inv, "model": {"clear": g["clear"]}},
                        snapshot,
                        at_front,
                        registry,
                        expected_people_count=53,
                    )
                    door_checks[hinges][phase] = check
                    if check["status"] == "VERIFIED_UNDER_HYPOTHESES":
                        door_count[hinges] += 1
                    else:
                        errors.extend(check["conflicts"])
            activity = [cx - 300, oy - 125, cx + 300, oy + 775]
            activity_conflicts = [
                o["id"]
                for o in [*others, *g["bodies"]]
                if intersection(rectangle(activity), rectangle(o["bounds_mm"]))
            ]
            activity_conflicts += [
                f"AISLE-{i}"
                for i, a in enumerate(g["aisles"])
                if intersection(rectangle(activity), rectangle(a))
            ]
            if activity_conflicts:
                errors.append({"code": "ACTIVITY_CONFLICT", "objects": activity_conflicts})
            back = verify_movement(
                list(reversed(path)),
                target,
                person,
                others,
                g["bodies"],
                g["clear"],
                450,
                650,
                1800,
                allowed,
                [],
                3000,
            )
            if back["status"] != "CONTINUOUS_PATH_VERIFIED_UNDER_HYPOTHESES":
                errors.extend(back["conflicts"])
            events.append(
                {
                    "person": pid,
                    "cell": cellid,
                    "move_to_cabinet": proof,
                    "door_checks": door_checks,
                    "activity_box_mm": activity,
                    "activity_conflicts": activity_conflicts,
                    "return_to_home": back,
                    "sequence": [
                        "MOVE_TO_OWN_CABINET",
                        "TAKE_AND_CLOSE",
                        "STANDING_CHANGE_WITH_DOOR_CLOSED",
                        "STORE_AND_CLOSE",
                        "RETURN_HOME",
                    ],
                }
            )
            if errors:
                break
        results.append(
            {
                "shift": shift,
                "initial_inside": 53,
                "completed_cabinet_cycles": len(events),
                "cycle_geometry_pass": len(events) == 53 and not errors,
                "door_events_per_hypothesis": door_count,
                "events": events,
                "conflicts": errors,
            }
        )
    return {
        "status": "CONDITIONAL_CABINET_CYCLES_VERIFIED"
        if all(s["cycle_geometry_pass"] for s in results)
        else "CONFIGURATION_NOT_FIT",
        "shifts": results,
        "design_users": 53,
        "initial_53_people_verified": True,
        "full_flow_verified": False,
        "entry_exit_with_current_proposed_Portals": "NOT_EVALUATED",
        "legacy_H5_adapter": "UNSUPPORTED_NON_HISTORICAL_ROOM_AND_PORTALS",
        "functional_status": "INPUT_REQUIRED",
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
        "missing_inputs": [
            "Actual cabinet hinges and net compartment sizes",
            "Actual human/reach dimensions",
            "Hygiene/clothing separation",
            "Door leaf behavior",
            "Entry/exit adaptation",
        ],
    }


def evaluate_changing_entry_exit(
    g: Mapping[str, Any], room: PlacedRectangleV1, access: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Stateful entry/exit; only actual occupants remain in the room.

    Reuses H5 motion network and exact 3D sweeps. The legacy 52-other-users
    invariant is used for cabinet cycles, not falsely applied during filling.
    Door leaf dynamics and external queue capacity remain unverified.
    """
    portals = {}
    for r in access:
        if r.get("status") != "PASS":
            continue
        if r.get("from_ref") == "main_entrance" and r.get("to_ref") == "changing_room":
            portals["entry"] = r["portal_to"]
        if r.get("from_ref") == "changing_room" and r.get("to_ref") == "sorting_packaging_room":
            portals["exit"] = r["portal_from"]
    if set(portals) != {"entry", "exit"} or g["status"] != "STATIC_GEOMETRY_READY":
        return {
            "status": "NOT_EVALUATED",
            "reason": "CURRENT_PORTAL_OR_GEOMETRY_MISSING",
            "full_flow_verified": False,
        }
    points = {}
    ox, oy, _, _ = room.bounds_mm
    for key, p in portals.items():
        wx, wy = _inward(p, room, 345)
        point = [wx - ox, wy - oy]
        # Current adapter covers the west main aisle / south cross only.
        if point[0] < 2020:
            anchor = [1020, point[1]]
        elif point[1] < 2020:
            anchor = [point[0], 1020]
        else:
            return {
                "status": "NOT_EVALUATED",
                "reason": "UNSUPPORTED_CURRENT_PORTAL_FACE",
                "full_flow_verified": False,
            }
        points[key] = (point, anchor)
    results = []
    for shift in (1, 2):
        assignments = [a for a in g["inventory"]["person_assignments"] if a["shift"] == shift]
        people = {
            a["person_id"]: standing_person(a["person_id"], q["bounds_mm"], 1800, "PERSON")
            for a, q in zip(assignments, g["homes"], strict=True)
        }
        occupied: dict[str, Any] = {}
        events = []
        errors = []
        for state in ("entry", "exit"):
            portal_point, anchor = points[state]
            for a, home in zip(assignments, g["homes"], strict=True):
                pid = a["person_id"]
                person = people[pid]
                b = person["bounds_mm"]
                center = [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2]
                home_link = [center, [center[0], home["aisle_y"]]]
                door_link = [portal_point, anchor]
                path = network_path(portal_point, center, [*g["network"], home_link, door_link])
                if state == "exit" and path:
                    path = list(reversed(path))
                others = [o for k, o in occupied.items() if k != pid]
                conflicts: list[dict[str, Any]] = []
                if not path:
                    conflicts.append({"code": "NO_CURRENT_PORTAL_PATH"})
                else:
                    for n, volume in enumerate(swept_segments(path, 450, 650, 1800)):
                        if not covered(
                            (volume[0], volume[1], volume[3], volume[4]), [rectangle(g["clear"])]
                        ):
                            conflicts.append({"code": "MOTION_OUTSIDE_FINISHED_ROOM", "segment": n})
                        for other in [*others, *g["bodies"]]:
                            if any(overlap3(volume, v) for v in other["volumes_mm"]):
                                conflicts.append(
                                    {
                                        "code": "CONTINUOUS_BODY_COLLISION",
                                        "other": other["id"],
                                        "segment": n,
                                    }
                                )
                events.append(
                    {
                        "person": pid,
                        "phase": state,
                        "other_users": len(others),
                        "centerline_mm": path,
                        "status": "SWEPT_GEOMETRY_VERIFIED"
                        if not conflicts
                        else "CONFIGURATION_NOT_FIT",
                        "conflicts": conflicts,
                    }
                )
                if conflicts:
                    errors.extend(conflicts)
                    break
                if state == "entry":
                    occupied[pid] = person
                else:
                    occupied.pop(pid)
            if errors:
                break
        results.append(
            {
                "shift": shift,
                "events": events,
                "entry_count": sum(e["phase"] == "entry" and not e["conflicts"] for e in events),
                "exit_count": sum(e["phase"] == "exit" and not e["conflicts"] for e in events),
                "conflicts": errors,
            }
        )
    passed = all(
        s["entry_count"] == 53 and s["exit_count"] == 53 and not s["conflicts"] for s in results
    )
    return {
        "status": "CONDITIONAL_ENTRY_EXIT_GEOMETRY_VERIFIED" if passed else "CONFIGURATION_NOT_FIT",
        "entry_exit_verified": passed,
        "shifts": results,
        "portals": portals,
        "full_flow_verified": False,
        "door_leaf_and_external_queue": "INPUT_REQUIRED",
        "functional_status": "INPUT_REQUIRED",
    }
