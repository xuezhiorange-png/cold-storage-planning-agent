"""Finite storage layouts and reversible, explicitly ordered load movement.

Block storage is NOT arbitrary direct access. Every successful withdrawal keeps
all not-yet-withdrawn loads present. Vehicle kinematics and operating policy need
review; 2500/5000mm main aisles are never replaced by a narrow pickup interface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.functional_material_geometry import (
    axis_transform,
    bounds_inside,
    motion_clear,
    point_transform,
    rectilinear_path,
    route_record,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def storage_layouts(
    room: PlacedRectangleV1,
    zone: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    *,
    preferred_turn: int | None = None,
    case_erector: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    clear = room.bounds_mm
    width, depth = clear[2] - clear[0], clear[3] - clear[1]
    minimum = int(zone.get("n_need", zone["position_count"]))
    original = int(zone["position_count"])
    aisle = 5000 if room.zone_code == "packaging_material_storage" else 3000
    cols = [q for q in columns if positive_intersection(clear, q["bbox_mm"])]
    results = []
    for turn in range(4):
        w, h = (width, depth) if turn % 2 == 0 else (depth, width)
        for dx in (0, 100, 200):
            for dy in (0, 100):
                extra = []
                if case_erector is not None:
                    ew, eh = int(case_erector["width_mm"]), int(case_erector["length_mm"])
                    eb = axis_transform(
                        (w - ew - 100, aisle + 100, w - 100, aisle + 100 + eh), clear, turn
                    )
                    extra = [
                        {
                            "id": "ERECT-05",
                            "room": room.zone_code,
                            "kind": "case_erector",
                            "bbox_mm": list(eb),
                            "rotation_deg": (90 + 90 * turn) % 180,
                            "material_direction": "CANONICAL_NEGATIVE_Y",
                            "basis": (
                                "Joint carton forming proposal in packaging-material store; "
                                "original full body"
                            ),
                            "operation_face": "DESIGN_PROPOSAL_OUTPUT_TO_MAIN_AISLE",
                            "manufacturer_interfaces": "INPUT_REQUIRED",
                        }
                    ]
                    if not bounds_inside(eb, clear) or any(
                        positive_intersection(eb, c["bbox_mm"]) for c in cols
                    ):
                        continue
                blockers = [*cols, *extra]
                available = []
                blocked = []
                main = axis_transform((0, 0, w, aisle), clear, turn)
                aisle_conflicts = [
                    c["id"] for c in blockers if positive_intersection(main, c["bbox_mm"])
                ]
                for row, y in enumerate(range(aisle + dy, h - 1200 + 1, 1300)):
                    for col, x in enumerate(range(dx, w - 1000 + 1, 1200)):
                        box = axis_transform((x, y, x + 1000, y + 1200), clear, turn)
                        conflicts = [
                            c["id"] for c in blockers if positive_intersection(box, c["bbox_mm"])
                        ]
                        load_box = axis_transform((x - 50, y - 50, x + 1050, y + 1250), clear, turn)
                        if not bounds_inside(load_box, clear):
                            conflicts.append("LOAD_MARGIN_OUTSIDE_ROOM")
                        conflicts.extend(
                            c["id"] + ":LOAD_MARGIN"
                            for c in blockers
                            if positive_intersection(load_box, c["bbox_mm"])
                        )
                        cell = {
                            "grid_row": row,
                            "grid_column": col,
                            "bbox_mm": list(box),
                            "canonical_center_mm": [x + 500, y + 600],
                        }
                        if conflicts:
                            blocked.append({**cell, "conflicts": conflicts})
                        else:
                            available.append(cell)
                selected = available[:original]
                items = [
                    {
                        **cell,
                        "id": f"{room.zone_code}-PAL-{i + 1:03}",
                        "room": room.zone_code,
                        "kind": room.zone_code + "_pallet",
                        "rotation_deg": (90 + 90 * turn) % 180,
                        "basis": (
                            "Original 1200x1000mm pallet, rotated; finite re-grid, "
                            "no capacity reduction"
                        ),
                        "status": "BODY_PLACED_PICKUP_PROOF_SEPARATE",
                    }
                    for i, cell in enumerate(selected)
                ]
                results.append(
                    {
                        "id": f"STORE-T{turn}-X{dx}-Y{dy}",
                        "room": room.zone_code,
                        "turn": turn,
                        "minimum_positions": minimum,
                        "original_grid_positions": original,
                        "placed_positions": len(items),
                        "items": items,
                        "extra_equipment": extra,
                        "blocked_slots": blocked,
                        "main_aisle_bbox_mm": list(main),
                        "main_aisle_width_mm": aisle,
                        "main_point_mm": list(point_transform((w // 2, aisle // 2), clear, turn)),
                        "main_aisle_column_conflicts": aisle_conflicts,
                        "static_capacity_pass": len(items) >= minimum and not aisle_conflicts,
                        "source_type": "demo",
                        "validity_status": "unverified",
                        "requires_review": True,
                    }
                )
    return sorted(
        results,
        key=lambda r: (
            not r["static_capacity_pass"],
            0 if preferred_turn is None or r["turn"] == preferred_turn else 1,
            -r["placed_positions"],
            len(r["blocked_slots"]),
            r["id"],
        ),
    )


def ordered_stock_movement(
    layout: Mapping[str, Any],
    room: PlacedRectangleV1,
    columns: Sequence[Mapping[str, Any]],
    *,
    node_budget: int = 2500,
) -> dict[str, Any]:
    """Actual stateful pick/put simulation of all stored loads, with a finite retry.

    50mm per-side LOAD margin is an unapproved sensitivity. It is not a truck
    width. Reserved main aisle remains >=2500mm, checked independently.
    """
    fixed = [q["bbox_mm"] for q in columns if positive_intersection(q["bbox_mm"], room.bounds_mm)]
    fixed.extend(q["bbox_mm"] for q in layout.get("extra_equipment", ()))
    stock = {q["id"]: q for q in layout["items"]}
    turn = int(layout["turn"])
    ew, ed = (1100, 1300) if turn % 2 == 0 else (1300, 1100)
    goal = tuple(layout["main_point_mm"])
    events: list[dict[str, Any]] = []
    failed = []
    operations = 0
    graph_nodes = 0
    # Retry only after a real withdrawal changes occupancy. Never hide a load
    # to obtain a path for another load.
    while stock:
        progress = False
        for key, q in list(stock.items()):
            obstacles = [*fixed, *[v["bbox_mm"] for k, v in stock.items() if k != key]]
            b = q["bbox_mm"]
            start = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
            path, nodes = rectilinear_path(
                start, goal, room.bounds_mm, obstacles, ew, ed, node_budget=node_budget
            )
            operations += 1
            graph_nodes += nodes
            if not path:
                failed.append(
                    {"id": key, "remaining_loads": len(stock), "node_budget": node_budget}
                )
                continue
            event = route_record(
                path,
                ew,
                ed,
                id=key,
                room=room.zone_code,
                other_stored_loads=len(stock) - 1,
                order=len(events) + 1,
            )
            events.append(event)
            del stock[key]
            progress = True
        if not progress:
            break
    returned: dict[str, Any] = {}
    items = {q["id"]: q for q in layout["items"]}
    reverse_ok = not stock
    if reverse_ok:
        for e in reversed(events):
            path = [tuple(p) for p in reversed(e["centerline_mm"])]
            obstacles = [*fixed, *[q["bbox_mm"] for q in returned.values()]]
            if not motion_clear(path, room.bounds_mm, obstacles, ew, ed):
                reverse_ok = False
                break
            returned[e["id"]] = items[e["id"]]
    return {
        "room": room.zone_code,
        "placed_positions": len(layout["items"]),
        "minimum_positions": layout["minimum_positions"],
        "retrieved_positions": len(events),
        "putaway_positions": len(returned),
        "conditional_pick_put_geometry_pass": bool(
            reverse_ok and len(events) >= layout["minimum_positions"]
        ),
        "arbitrary_order_direct_access": False,
        "operating_policy": "EXPLICIT_WITNESSED_FRONT_FIRST_WITH_RETRIES; REVERSE_PUTAWAY",
        "load_dimensions_mm": [1000, 1200],
        "load_margin_each_side_mm": 50,
        "main_aisle_width_mm": layout["main_aisle_width_mm"],
        "load_pickup_interface_is_not_a_reduced_main_aisle": True,
        "vehicle_kinematics": "INPUT_REQUIRED_NOT_A_FORKLIFT_CERTIFICATE",
        "storage_policy_approval": "INPUT_REQUIRED",
        "failed_attempts": failed,
        "unretrieved_ids": list(stock),
        "events": events,
        "motion_attempts": operations,
        "event_grid_nodes": graph_nodes,
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
    }
