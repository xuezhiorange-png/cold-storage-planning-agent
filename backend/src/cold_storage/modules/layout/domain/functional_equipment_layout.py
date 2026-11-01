"""Portal-ready equipment families, bounded storage trials and function requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.access_routing import _shared_edge_segment
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.functional_changing_layout import changing_layout
from cold_storage.modules.layout.domain.functional_material_geometry import (
    axis_transform,
    bounds_inside,
)
from cold_storage.modules.layout.domain.functional_storage_layout import (
    ordered_stock_movement,
    storage_layouts,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def coating_dimensions(spec: Mapping[str, Any]) -> tuple[int, int]:
    return (
        (int(spec["length_mm"]) + 2 * 1200 + 2 * 2500 + 2 * 100 + 99) // 100 * 100,
        (int(spec["width_mm"]) + 2 * 2500 + 99) // 100 * 100,
    )


def build_functional_equipment(
    rooms: Mapping[str, PlacedRectangleV1],
    specs: Mapping[str, Any],
    zone_plan: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    layouts: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    trials = []
    spaces = []

    def local_add(
        code: str, id_: str, kind: str, box: Sequence[int], **extra: Any
    ) -> dict[str, Any]:
        q = rooms[code]
        b = axis_transform(box, q.bounds_mm, q.rotation_deg // 90)
        row = {
            "id": id_,
            "room": code,
            "kind": kind,
            "bbox_mm": list(b),
            "rotation_deg": q.rotation_deg,
            "basis": "Joint deterministic geometry; original device dimensions",
            "status": "CONDITIONAL_BODY_PLACEMENT",
            **extra,
        }
        conflicts = [c["id"] for c in columns if positive_intersection(b, c["bbox_mm"])]
        conflicts += [c["id"] for c in items if positive_intersection(b, c["bbox_mm"])]
        if not bounds_inside(b, q.bounds_mm):
            conflicts.append("OUTSIDE_ROOM")
        if conflicts:
            failures.append({"id": id_, "code": "EQUIPMENT_BODY_CONFLICT", "objects": conflicts})
        items.append(row)
        return row

    def corridor(code: str, box: Sequence[int], id_: str, width: int) -> dict[str, Any]:
        q = rooms[code]
        b = axis_transform(box, q.bounds_mm, q.rotation_deg // 90)
        return {"id": id_, "bbox_mm": list(b), "clear_width_mm": width}

    code = "sorting_packaging_room"
    q = rooms[code]
    w, h = int(q.width_m * 1000), int(q.depth_m * 1000)
    line = specs["packing_line"]
    L, D = int(line["length_mm"]), int(line["width_mm"])
    aisle = 2500
    line_x = aisle + 100
    pair_h = 2 * D + 1000
    gap = (h - 2 * (aisle + 100) - 3 * pair_h) // 2
    if gap < 0:
        failures.append({"code": "PACKING_PAIR_SECTION_TOO_SMALL"})
    operators: list[dict[str, Any]] = []
    for pair in range(3):
        y = aisle + 100 + pair * (pair_h + max(gap, 0))
        for side, yy in enumerate((y, y + D + 1000)):
            local_add(
                code,
                f"PACK-{2 * pair + side + 1:02}",
                "packing_line",
                [line_x, yy, line_x + L, yy + D],
                material_direction="LOCAL_POSITIVE_X",
            )
        for person in range(18 if pair < 2 else 17):
            x = line_x + 150 + person * 800
            box = [x, y + D + 50, x + 600, y + D + 950]
            b = axis_transform(box, q.bounds_mm, q.rotation_deg // 90)
            if any(positive_intersection(b, c["bbox_mm"]) for c in columns):
                failures.append({"code": "PACKING_OPERATOR_COLUMN_CONFLICT", "pair": pair})
            operators.append(
                {
                    "id": f"PACK-OP-{len(operators) + 1:02}",
                    "room": code,
                    "bbox_mm": list(b),
                    "paired_line": 2 * pair + person % 2 + 1,
                    "source_type": "demo",
                    "validity_status": "unverified",
                    "requires_review": True,
                }
            )
    bank = line_x + L + aisle + 200
    erect = specs["case_erector"]
    ew, eh = int(erect["length_mm"]), int(erect["width_mm"])
    for i in range(4):
        x = bank + (i % 2) * (ew + 1000)
        y = 2600 + (i // 2) * (eh + 2700)
        local_add(
            code,
            f"ERECT-{i + 1:02}",
            "case_erector",
            [x, y, x + ew, y + eh],
            equipment_rotation_deg=q.rotation_deg,
            operation_face="DESIGN_PROPOSAL; MANUFACTURER_INFEED_OUTFEED_REQUIRED",
        )
    corr = [
        corridor(code, [0, 0, w, 2500], "SORT-SOUTH", 2500),
        corridor(code, [0, 0, 2500, h], "SORT-WEST", 2500),
        corridor(code, [line_x + L + 100, 0, line_x + L + 2600, h], "SORT-TRANSFER", 2500),
        corridor(code, [0, h - 2500, line_x + L + 2600, h], "SORT-NORTH", 2500),
        corridor(code, [line_x + L + 100, eh + 2700, w, eh + 5200], "CASE-MIDDLE", 2500),
    ]
    layouts[code] = {"service_corridors": corr, "operator_positions": operators}

    for code, prefix in (("primary_precooling_room", "PRI"), ("secondary_precooling_room", "SEC")):
        q = rooms[code]
        w, h = int(q.width_m * 1000), int(q.depth_m * 1000)
        n = round(w / 4900)
        north = code == "primary_precooling_room"
        corridors = []
        corridors.append(corridor(code, [0, h - 2500, w, h], prefix + "-NORTH", 2500))
        if not north:
            corridors.append(corridor(code, [0, 0, w, 2500], prefix + "-SOUTH", 2500))
        for cell in range(n):
            for side in range(2):
                x = cell * 4900 + (100 if side == 0 else 3800)
                for row in range(3):
                    y = 3000 + row * 1300
                    local_add(
                        code,
                        f"{prefix}-C{cell + 1}-P{side * 3 + row + 1}",
                        prefix + "_pallet",
                        [x, y, x + 1000, y + 1200],
                        carrier="TURNOVER_CRATES" if north else "CARTONS_ON_PALLET",
                    )
            x = cell * 4900 + 100
            y = 6850
            local_add(
                code,
                f"{prefix}-FAN-{cell + 1}",
                "forced_air_fan_allowance",
                [x, y, x + 600, y + 600],
                cooling_performance="INPUT_REQUIRED",
            )
            # At the incoming end only the lane aligned to the sort-feed
            # aisle must reach the boundary. Other lanes join the north cross.
            low = 0
            test = corridor(
                code, [cell * 4900 + 1250, 0, cell * 4900 + 3750, h], prefix + "-test", 2500
            )
            if north and any(positive_intersection(test["bbox_mm"], c["bbox_mm"]) for c in columns):
                low = 2700
            corridors.append(
                corridor(
                    code,
                    [cell * 4900 + 1250, low, cell * 4900 + 3750, h],
                    f"{prefix}-LANE-{cell + 1}",
                    2500,
                )
            )
        layouts[code] = {"service_corridors": corridors}

    code = "coating_room"
    q = rooms[code]
    w, h = int(q.width_m * 1000), int(q.depth_m * 1000)
    cw, ch = coating_dimensions(specs["case_film_line"])
    if w < cw or h < ch:
        failures.append(
            {
                "code": "COATING_FUNCTIONAL_SIZE_REQUEST",
                "room": code,
                "requested_shape_mm": [cw, ch],
            }
        )
        layouts[code] = {"service_corridors": [], "requested_shape_mm": [cw, ch]}
    else:
        x = 3800
        y = 2500
        for part in specs["case_film_line"]["components"]:
            length = int(part["length_mm"])
            depth = int(part["width_mm"])
            yy = y + (2020 - depth) // 2
            local_add(
                code,
                "FILM-" + part["kind"],
                "case_film_component",
                [x, yy, x + length, yy + depth],
                material_direction="LOCAL_POSITIVE_X",
                manufacturer_clearances="INPUT_REQUIRED",
            )
            x += length
        for key, sx in (("DEPALLETIZE", 2500), ("REPALLETIZE", x + 100)):
            local_add(code, key, "pallet_handoff", [sx, 3010, sx + 1200, 4010])
        layouts[code] = {
            "service_corridors": [
                corridor(code, [0, 0, w, 2500], "FILM-SOUTH", 2500),
                corridor(code, [0, h - 2500, w, h], "FILM-NORTH", 2500),
                corridor(code, [0, 0, 2500, h], "FILM-WEST", 2500),
                corridor(code, [w - 2500, 0, w, h], "FILM-EAST", 2500),
            ]
        }

    upstream = {z["zone_code"]: z for z in zone_plan["result"]["zones"]}
    storage = []
    for code in (
        "packaging_material_storage",
        "finished_goods_room",
        "raw_fruit_buffer",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
    ):
        q = rooms[code]
        ls = storage_layouts(
            q,
            upstream[code],
            columns,
            case_erector=erect if code == "packaging_material_storage" else None,
        )
        linked = [
            str(r["to_ref"] if r["from_ref"] == code else r["from_ref"])
            for r in relationships
            if code in (r.get("from_ref"), r.get("to_ref")) and r.get("flow_kind") != "TRUCK"
        ]

        def connection_score(
            layout: Mapping[str, Any], linked: list[str] = linked, q: PlacedRectangleV1 = q
        ) -> int:
            score = 0
            box = layout["main_aisle_bbox_mm"]
            for neighbor in linked:
                if neighbor not in rooms:
                    continue
                edge = _shared_edge_segment(q, rooms[neighbor])
                if not edge:
                    continue
                a, b = edge
                neighbor_aisles = layouts.get(neighbor, {}).get("service_corridors", [])
                if a[0] == b[0]:
                    for aisle in neighbor_aisles:
                        u, v, s, z = aisle["bbox_mm"]
                        score += int(
                            box[0] <= a[0] <= box[2]
                            and u <= a[0] <= s
                            and min(b[1], box[3], z) - max(a[1], box[1], v) >= 2500
                        )
                else:
                    for aisle in neighbor_aisles:
                        u, v, s, z = aisle["bbox_mm"]
                        score += int(
                            box[1] <= a[1] <= box[3]
                            and v <= a[1] <= z
                            and min(b[0], box[2], s) - max(a[0], box[0], u) >= 2500
                        )
            return score

        ls.sort(
            key=lambda a: (
                not a["static_capacity_pass"],
                -connection_score(a),
                -a["placed_positions"],
                a["id"],
            )
        )
        selected = None
        movement = None
        for layout in ls[:3]:
            movement = ordered_stock_movement(layout, q, columns)
            trials.append(
                {
                    "room": code,
                    "candidate": layout["id"],
                    "placed": layout["placed_positions"],
                    "minimum": layout["minimum_positions"],
                    "main_aisle_column_conflicts": layout["main_aisle_column_conflicts"],
                    "retrieved": movement["retrieved_positions"],
                    "returned": movement["putaway_positions"],
                }
            )
            selected = layout
            if layout["static_capacity_pass"] and movement["conditional_pick_put_geometry_pass"]:
                break
        if selected is None or movement is None:
            failures.append({"code": "NO_STORAGE_LAYOUT", "room": code})
            continue
        if (
            not selected["static_capacity_pass"]
            or not movement["conditional_pick_put_geometry_pass"]
        ):
            failures.append(
                {
                    "code": "STORAGE_PICK_PUT_NOT_COMPLETE",
                    "room": code,
                    "placed": selected["placed_positions"],
                    "minimum": selected["minimum_positions"],
                }
            )
        items.extend(selected["items"])
        items.extend(selected["extra_equipment"])
        layouts[code] = {
            "service_corridors": [
                {
                    "id": "STORAGE-MAIN",
                    "bbox_mm": selected["main_aisle_bbox_mm"],
                    "clear_width_mm": selected["main_aisle_width_mm"],
                }
            ],
            "storage_layout_id": selected["id"],
        }
        storage.append({"layout": selected, "movement": movement})

    code = "changing_room"
    g = changing_layout(rooms[code], columns)
    if g["status"] != "STATIC_GEOMETRY_READY":
        failures.append(
            {
                "code": "CHANGING_FUNCTIONAL_SIZE_REQUEST",
                "room": code,
                "requested_shape_mm": g.get("requested_shape_mm"),
            }
        )
        layouts[code] = {"service_corridors": []}
    else:
        for u in g["inventory"]["cabinet_units"]:
            b = axis_transform(u["bounds_mm"], rooms[code].bounds_mm, 0)
            items.append(
                {
                    "id": "LOCKER-" + u["id"],
                    "room": code,
                    "kind": "ten_door_locker",
                    "bbox_mm": list(b),
                    "rotation_deg": 0,
                    "compartments": 10,
                    "basis": "R11 complete physical inventory, recalculated in new room",
                    "status": "CONDITIONAL_BODY_PLACEMENT",
                }
            )
        layouts[code] = {
            "service_corridors": [
                {
                    "id": f"CHANGING-AISLE-{i}",
                    "bbox_mm": list(axis_transform(a, rooms[code].bounds_mm, 0)),
                    "clear_width_mm": 2000 if i < 2 else 1200,
                }
                for i, a in enumerate(g["aisles"])
            ],
            "functional_geometry": g,
        }
    for code in ("shipping_channel", "office"):
        q = rooms[code]
        left, bottom, right, _ = q.bounds_mm
        layouts[code] = {
            "service_corridors": [
                {
                    "id": "SOUTH-SERVICE-AISLE",
                    "bbox_mm": [left, bottom, right, bottom + 2500],
                    "clear_width_mm": 2500,
                }
            ]
        }
    for code, layout_record in layouts.items():
        for a in layout_record["service_corridors"]:
            conflicts = [
                i["id"]
                for i in items
                if i["room"] == code and positive_intersection(a["bbox_mm"], i["bbox_mm"])
            ]
            conflicts += [
                c["id"] for c in columns if positive_intersection(a["bbox_mm"], c["bbox_mm"])
            ]
            spaces.append(
                {
                    **a,
                    "room": code,
                    "kind": "material_clear_aisle",
                    "conflicts": conflicts,
                    "status": "GEOMETRIC_CONFLICT"
                    if conflicts
                    else "NO_BODY_INTERSECTION_IN_CHECKED_ENVELOPE",
                }
            )
    return {
        "items": items,
        "rejected_items": [],
        "placed_counts": {
            k: sum(i["kind"] == k for i in items) for k in sorted({i["kind"] for i in items})
        },
        "layouts": layouts,
        "operating_spaces": spaces,
        "storage": storage,
        "storage_trials": trials,
        "failures": failures,
        "full_equipment_engineering_pass": False,
        "scope": (
            "Joint bodies, reserved aisles and explicit conditional movement; "
            "manufacturer/vehicle/hygiene approval separate"
        ),
    }
