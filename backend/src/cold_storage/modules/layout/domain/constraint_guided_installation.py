"""Finite partial-room installation options, using the original physical predicates.

No Native, historical coordinates, new Authority or global infeasibility claim.
Exhaustion means only the enumerated grid/event templates were checked.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_equipment_layout import precooling_room_template
from cold_storage.modules.layout.domain.functional_material_geometry import (
    axis_transform,
    bounds_inside,
    rectilinear_path,
    swept_boxes,
)
from cold_storage.modules.layout.domain.functional_storage_layout import storage_layouts
from cold_storage.modules.layout.domain.process_flow_arrangement import (
    arrange_process_workplaces,
    process_static_conflicts,
    sorting_workplaces,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def storage_capacity_check(
    room: PlacedRectangleV1,
    zone: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    erector: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """All four directions, both original pallet orientations and finite offsets.

    The final original ordered pick/put and doorway checks are still mandatory.
    A failure is NOT a proof that every continuous layout is impossible.
    """
    choices = storage_layouts(room, zone, columns, case_erector=erector, allow_pallet_rotation=True)
    target = max(int(zone["position_count"]), int(zone.get("n_need", zone["position_count"])))
    valid = [q for q in choices if q["static_capacity_pass"]]
    best = min(
        choices,
        key=lambda q: (bool(q["main_aisle_column_conflicts"]), -q["placed_positions"], q["id"]),
    )
    return {
        "admissible": bool(valid),
        "status": "NECESSARY_GRID_CAPACITY_AVAILABLE" if valid else "FINITE_GRID_OPTIONS_EXHAUSTED",
        "room": room.zone_code,
        "room_bbox_mm": list(room.bounds_mm),
        "required_positions": target,
        "best_positions": max(q["placed_positions"] for q in choices),
        "main_aisle_mm": best["main_aisle_width_mm"],
        "load_edge_margin_mm": 50,
        "options_checked": len(choices),
        "orientations_checked": sorted(
            {(q["turn"], q.get("pallet_local_rotation_deg", 0)) for q in choices}
        ),
        "passing_option_ids": [q["id"] for q in valid],
        "best_layout": {
            k: best[k]
            for k in (
                "id",
                "placed_positions",
                "main_aisle_bbox_mm",
                "main_aisle_column_conflicts",
                "blocked_slots",
            )
        },
        "columns": [q for q in columns if positive_intersection(room.bounds_mm, q["bbox_mm"])],
        "scope": "ALL_48_EXISTING_GRID_TEMPLATES_NOT_ALL_CONTINUOUS_PHYSICAL_LAYOUTS",
        "ordered_pick_put": "NOT_EVALUATED",
        "global_infeasibility_proven": False,
    }


def _conflicts(
    room: Sequence[int], items: Sequence[Mapping[str, Any]], columns: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    failures = []
    for i, q in enumerate(items):
        b = q["bbox_mm"]
        if not bounds_inside(b, room):
            failures.append(
                {
                    "code": "BODY_OUTSIDE_ROOM",
                    "id": q["id"],
                    "bbox_mm": b,
                    "room_bbox_mm": list(room),
                }
            )
        for other in [*items[:i], *columns]:
            if positive_intersection(b, other["bbox_mm"]):
                failures.append(
                    {
                        "code": "BODY_COLLISION",
                        "id": q["id"],
                        "bbox_mm": b,
                        "other": other["id"],
                        "obstacle_bbox_mm": other["bbox_mm"],
                    }
                )
    return failures


def _transform(
    records: Sequence[Mapping[str, Any]],
    room: Sequence[int],
    *,
    mx: bool = False,
    my: bool = False,
    dx: int = 0,
    dy: int = 0,
) -> list[dict[str, Any]]:
    result = copy.deepcopy([dict(q) for q in records])
    for q in result:
        x, y, r, t = q["bbox_mm"]
        if mx:
            x, r = room[0] + room[2] - r, room[0] + room[2] - x
        if my:
            y, t = room[1] + room[3] - t, room[1] + room[3] - y
        q["bbox_mm"] = [x + dx, y + dy, r + dx, t + dy]
        for field in (
            "front",
            "output_face",
            "magazine_face",
            "process_in_face",
            "process_out_face",
        ):
            if field in q:
                if mx:
                    q[field] = {"W": "E", "E": "W"}.get(q[field], q[field])
                if my:
                    q[field] = {"N": "S", "S": "N"}.get(q[field], q[field])
    return result


def _corridors(
    room: Sequence[int], corridors: Sequence[Mapping[str, Any]], fixed: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Keep every required full width; reroute a blocked rectangle with real sweeps."""
    result, failed = [], []
    nodes = 0
    obstacles = [q["bbox_mm"] for q in fixed]
    for a in corridors:
        b, width = a["bbox_mm"], a["clear_width_mm"]
        if bounds_inside(b, room) and not any(positive_intersection(b, q) for q in obstacles):
            result.append(dict(a))
            continue
        half = width // 2
        if b[2] - b[0] > b[3] - b[1]:
            start, end = (b[0] + half, (b[1] + b[3]) // 2), (b[2] - half, (b[1] + b[3]) // 2)
        else:
            start, end = ((b[0] + b[2]) // 2, b[1] + half), ((b[0] + b[2]) // 2, b[3] - half)
        path, used = rectilinear_path(start, end, room, obstacles, width, width, node_budget=1200)
        nodes += used
        boxes = swept_boxes(path, width, width) if path else []
        if not boxes or any(
            not bounds_inside(s, room) or any(positive_intersection(s, o) for o in obstacles)
            for s in boxes
        ):
            failed.append(
                {
                    "code": "FULL_WIDTH_CORRIDOR_NOT_FOUND",
                    "id": a["id"],
                    "bbox_mm": b,
                    "required_width_mm": width,
                    "blocking_objects": [
                        q for q in fixed if positive_intersection(b, q["bbox_mm"])
                    ],
                    "status": "BOUNDED_ROUTE_NOT_FOUND",
                }
            )
            continue
        result.extend(
            {
                **a,
                "id": a["id"] + f"-DETOUR-{i}",
                "bbox_mm": list(s),
                "derived_centerline_mm": [list(p) for p in path],
            }
            for i, s in enumerate(boxes)
        )
    return result, failed, nodes


def room_installation_options(
    room: Sequence[int],
    items: Sequence[Mapping[str, Any]],
    operators: Sequence[Mapping[str, Any]],
    corridors: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
    *,
    limit: int = 4,
    trial_limit: int = 48,
    allow_x_mirror: bool = True,
    repair_sorting: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rigid equipment/operation groups and actual obstacle-edge displacement.

    No body, operator or aisle shrinks. The finite event set is not exhaustive.
    """
    columns = [q for q in columns if positive_intersection(room, q["bbox_mm"])]
    pending = [(False, False, 0, 0), (False, True, 0, 0)]
    if allow_x_mirror:
        pending += [(True, False, 0, 0), (True, True, 0, 0)]
    seen = set()
    valid: list[dict[str, Any]] = []
    trials: list[dict[str, Any]] = []
    while pending and len(trials) < trial_limit and len(valid) < limit:
        mx, my, dx, dy = pending.pop(0)
        key = (mx, my, dx, dy)
        if key in seen:
            continue
        seen.add(key)
        bodies = _transform(items, room, mx=mx, my=my, dx=dx, dy=dy)
        ops = _transform(operators, room, mx=mx, my=my, dx=dx, dy=dy)
        cs = _transform(corridors, room, mx=mx, my=my)
        repair_events = []
        if repair_sorting:
            repair_events = repair_sorting_groups(bodies, ops, cs, room, columns)
        conflicts = _conflicts(room, [*bodies, *ops], columns)
        resolved: list[dict[str, Any]] = []
        aisle_fail: list[dict[str, Any]] = []
        nodes = 0
        if not conflicts:
            resolved, aisle_fail, nodes = _corridors(room, cs, [*bodies, *ops, *columns])
        row = {
            "transform": list(key),
            "body_failures": conflicts,
            "corridor_failures": aisle_fail,
            "route_nodes": nodes,
            "passed": not conflicts and not aisle_fail,
            "local_body_adjustments": repair_events,
        }
        trials.append(row)
        if row["passed"]:
            valid.append(
                {"items": bodies, "operators": ops, "corridors": resolved, "transform": list(key)}
            )
        # A real collision generates displacements along its actual separating axes.
        body_index = {q["id"]: q for q in [*bodies, *ops]}
        obstacle_index = {q["id"]: q for q in columns}
        for f in conflicts[:12]:
            if f.get("other") not in obstacle_index:
                continue
            a, b = body_index[f["id"]]["bbox_mm"], obstacle_index[f["other"]]["bbox_mm"]
            for axis in (1, 0):
                for delta in (b[axis] - a[axis + 2] - 50, b[axis + 2] - a[axis] + 50):
                    pending.append(
                        (mx, my, dx + (delta if axis == 0 else 0), dy + (delta if axis == 1 else 0))
                    )
    return valid, {
        "trials": trials,
        "trials_used": len(trials),
        "trial_limit": trial_limit,
        "remaining_options": len(pending),
        "status": "OPTIONS_FOUND" if valid else "BOUNDED_INSTALLATION_NOT_FOUND",
        "scope": "FINITE_RIGID_GROUP_AND_OBSTACLE_EDGE_OPTIONS",
        "global_infeasibility_proven": False,
    }


def repair_sorting_groups(
    items: list[dict[str, Any]],
    operators: list[dict[str, Any]],
    corridors: Sequence[Mapping[str, Any]],
    room: Sequence[int],
    columns: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep all workers; redistribute their real bodies along the original pair bay.

    Erector rotations keep the full manufacturer body. Existing 1800mm magazine
    separation and full output aisles remain explicit constraints.
    """
    changes = []
    placed: list[Mapping[str, Any]] = []
    lines = {q["id"]: q for q in items if q["kind"] == "packing_line"}
    for op in operators:
        a = op["bbox_mm"]
        if not any(positive_intersection(a, q["bbox_mm"]) for q in columns):
            placed.append(op)
            continue
        line = lines[f"PACK-{op['line']:02}"]["bbox_mm"]
        xs = {
            line[0] + 150,
            a[0],
            *[q["bbox_mm"][2] + 50 for q in columns],
            *[q["bbox_mm"][2] + 200 for q in placed],
        }
        for x in sorted(xs, key=lambda x: (abs(x - a[0]), x)):
            b = [x, a[1], x + a[2] - a[0], a[3]]
            if b[0] < line[0] or b[2] > line[2] or not bounds_inside(b, room):
                continue
            if any(
                positive_intersection(b, q["bbox_mm"])
                for q in [*items, *operators, *columns]
                if q["id"] != op["id"]
            ):
                continue
            if any(
                min(b[3], q["bbox_mm"][3]) > max(b[1], q["bbox_mm"][1])
                and max(b[0], q["bbox_mm"][0]) - min(b[2], q["bbox_mm"][2]) < 200
                for q in operators
                if q["id"] != op["id"]
            ):
                continue
            changes.append(
                {
                    "id": op["id"],
                    "from_bbox_mm": list(a),
                    "to_bbox_mm": b,
                    "reason": "RETAINED_COLUMN_IN_OPERATOR_BAY",
                }
            )
            op["bbox_mm"] = b
            break
        placed.append(op)
    for item in items:
        if item["kind"] != "case_erector" or not any(
            positive_intersection(item["bbox_mm"], q["bbox_mm"]) for q in columns
        ):
            continue
        a = item["bbox_mm"]
        sizes = [(a[2] - a[0], a[3] - a[1]), (a[3] - a[1], a[2] - a[0])]
        blockers = [q for q in [*items, *operators, *columns] if q["id"] != item["id"]]
        found = False
        for w, h in sizes:
            xs = {a[0], a[2] - w, *[q["bbox_mm"][2] + 50 for q in columns]}
            ys = {
                a[1],
                a[3] - h,
                *[q["bbox_mm"][1] - h - 50 for q in columns],
                *[q["bbox_mm"][3] + 50 for q in columns],
            }
            attempts = sorted(
                ((x, y) for x in xs for y in ys),
                key=lambda p: (abs(p[0] - a[0]) + abs(p[1] - a[1]), p),
            )[:24]
            for x, y in attempts:
                b = [x, y, x + w, y + h]
                if (
                    not bounds_inside(b, room)
                    or any(positive_intersection(b, q["bbox_mm"]) for q in blockers)
                    or any(positive_intersection(b, q["bbox_mm"]) for q in corridors)
                ):
                    continue
                # Preserve a magazine bay between erectors facing each other.
                if any(
                    q["kind"] == "case_erector"
                    and min(b[3], q["bbox_mm"][3]) > max(b[1], q["bbox_mm"][1])
                    and 0 <= max(b[0], q["bbox_mm"][0]) - min(b[2], q["bbox_mm"][2]) < 1800
                    for q in blockers
                    if "kind" in q
                ):
                    continue
                changes.append(
                    {
                        "id": item["id"],
                        "from_bbox_mm": list(a),
                        "to_bbox_mm": b,
                        "reason": "FULL_BODY_LOCAL_ROTATION_OR_OBSTACLE_EDGE",
                    }
                )
                item["bbox_mm"] = b
                turned = w != a[2] - a[0]
                item["equipment_rotation_deg"] = (
                    int(item.get("equipment_rotation_deg", 90)) + 90 * turned
                ) % 360
                item["rotation_deg"] = item["equipment_rotation_deg"]
                if turned:
                    for field in ("output_face", "magazine_face"):
                        if field in item:
                            item[field] = {"E": "N", "N": "W", "W": "S", "S": "E"}[item[field]]
                found = True
                break
            if found:
                break
    return changes


def sorting_installation_options(
    room: PlacedRectangleV1,
    specs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    limit: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Six full lines, four full erectors, all 53 operators and 14+6+1 addresses."""
    line, erector = specs["packing_line"], specs["case_erector"]
    prototype = []
    for kind, prefix, count, spec in (
        ("packing_line", "PACK", 6, line),
        ("case_erector", "ERECT", 4, erector),
    ):
        for i in range(count):
            prototype.append(
                {
                    "id": f"{prefix}-{i + 1:02}",
                    "kind": kind,
                    "room": room.zone_code,
                    "bbox_mm": [0, 0, int(spec["length_mm"]), int(spec["width_mm"])],
                }
            )
    local_room = {"bbox_mm": [0, 0, int(room.width_m * 1000), int(room.depth_m * 1000)]}
    s = sorting_workplaces(local_room, prototype, parameters)
    turn = room.rotation_deg // 90
    for group in (s["items"], s["operator_positions"], s["service_corridors"]):
        for q in group:
            q["bbox_mm"] = list(axis_transform(q["bbox_mm"], room.bounds_mm, turn))
            if q.get("kind") == "packing_line":
                q.update(process_in_face="W", process_out_face="E")
            for field in (
                "front",
                "output_face",
                "magazine_face",
                "process_in_face",
                "process_out_face",
            ):
                if field in q:
                    q[field] = ("E", "N", "W", "S")[
                        (("E", "N", "W", "S").index(q[field]) + turn) % 4
                    ]
    return room_installation_options(
        room.bounds_mm,
        s["items"],
        s["operator_positions"],
        s["service_corridors"],
        columns,
        limit=limit,
        repair_sorting=True,
    )


def precooling_installation_options(
    room: PlacedRectangleV1,
    columns: Sequence[Mapping[str, Any]],
    *,
    limit: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(code: str, identity: str, kind: str, box: Sequence[int], **extra: Any) -> None:
        items.append(
            {
                "id": identity,
                "room": code,
                "kind": kind,
                "bbox_mm": list(axis_transform(box, room.bounds_mm, room.rotation_deg // 90)),
                "rotation_deg": room.rotation_deg,
                "source_type": "demo",
                "validity_status": "unverified",
                "requires_review": True,
                **extra,
            }
        )

    def aisle(code: str, box: Sequence[int], identity: str, width: int) -> dict[str, Any]:
        return {
            "id": identity,
            "bbox_mm": list(axis_transform(box, room.bounds_mm, room.rotation_deg // 90)),
            "clear_width_mm": width,
        }

    layout = precooling_room_template(room, columns, add, aisle)
    return room_installation_options(
        room.bounds_mm, items, [], layout["service_corridors"], columns, limit=limit
    )


def joint_installation_candidates(
    seed: Mapping[str, Any],
    parameters: Mapping[str, Any],
    specs: Mapping[str, Any],
    *,
    limit: int = 4,
    focus_role: str | None = None,
    focus_rank: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Bounded independent room options, followed by original full static checks."""
    base = arrange_process_workplaces(seed, parameters)
    c = base["candidate"]
    eq, columns = c["equipment"], c["original_building"]["columns"]
    rows = {q["zone_code"]: q for q in c["rooms"]}
    options, records = {}, {}
    from cold_storage.modules.layout.domain.process_endpoint_routes import room_rectangles

    rectangles = room_rectangles(c)
    # Preserve the Authority rotation, not the world bounding rectangle's orientation.
    for code, r in rows.items():
        from decimal import Decimal

        rectangles[code] = PlacedRectangleV1(
            code,
            Decimal(r["x_mm"]) / 1000,
            Decimal(r["y_mm"]) / 1000,
            Decimal(r["authority_width_m"]),
            Decimal(r["authority_depth_m"]),
            r["rotation_deg"],
        )
    options["sorting_packaging_room"], records["sorting_packaging_room"] = (
        sorting_installation_options(
            rectangles["sorting_packaging_room"], specs, parameters, columns, limit=limit
        )
    )
    for code in (
        "primary_precooling_room",
        "secondary_precooling_room",
        "coating_room",
        "shipping_channel",
    ):
        bodies = [q for q in eq["items"] if q["room"] == code]
        ops = [q for q in eq.get("process_operator_zones", []) if q["room"] == code]
        opts, record = room_installation_options(
            rows[code]["bbox_mm"],
            bodies,
            ops,
            eq["layouts"][code]["service_corridors"],
            columns,
            limit=limit,
            allow_x_mirror=code not in ("coating_room",),
        )
        if code in ("primary_precooling_room", "secondary_precooling_room"):
            opts, record = precooling_installation_options(rectangles[code], columns, limit=limit)
        # Coating's original equal-width actual-route realization is retained.
        if code == "coating_room" and not opts:
            opts = [
                {
                    "items": bodies,
                    "operators": ops,
                    "corridors": eq["layouts"][code]["service_corridors"],
                    "transform": [False, False, 0, 0],
                }
            ]
            record["deferred_actual_aisles"] = True
        options[code], records[code] = opts, record
    if any(not q for q in options.values()):
        return [], {"rooms": records, "status": "BOUNDED_LOCAL_INSTALLATION_REJECTED"}
    candidates = []
    choices = [dict.fromkeys(options, 0)]
    if focus_role in options and 0 < focus_rank < len(options[focus_role]):
        choices.insert(0, {**choices[0], focus_role: focus_rank})
    roles = sorted(options, key=lambda k: (k != focus_role, k != "coating_room", k))
    for rank in range(1, max(len(q) for q in options.values())):
        choices.extend(
            {**dict.fromkeys(options, 0), code: rank} for code in roles if rank < len(options[code])
        )
    for choice in choices[:limit]:
        a = copy.deepcopy(base)
        cc, ee = a["candidate"], a["candidate"]["equipment"]
        for code, rank in choice.items():
            o = options[code][rank]
            ee["items"] = [q for q in ee["items"] if q["room"] != code] + copy.deepcopy(o["items"])
            ee["layouts"][code]["service_corridors"] = copy.deepcopy(o["corridors"])
            if code == "sorting_packaging_room":
                ee["layouts"][code]["operator_positions"] = copy.deepcopy(o["operators"])
            else:
                ee["process_operator_zones"] = [
                    q for q in ee.get("process_operator_zones", []) if q["room"] != code
                ] + copy.deepcopy(o["operators"])
        a["static_conflicts"] = process_static_conflicts(cc)
        a["local_option_selection"] = choice
        a["geometry_hash"] = canonical_hash(
            {"rooms": cc["rooms"], "items": ee["items"], "layouts": ee["layouts"]}
        )
        candidates.append(a)
    return candidates, {
        "rooms": records,
        "status": "INSTALLATION_OPTIONS_GENERATED",
        "combinations_checked": len(candidates),
        "combination_limit": limit,
    }
