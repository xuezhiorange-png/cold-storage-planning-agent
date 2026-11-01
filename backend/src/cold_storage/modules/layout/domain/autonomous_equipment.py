"""Deterministic equipment bodies from room-local specifications, never world seeds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def positive_intersection(a: Sequence[int], b: Sequence[int]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def place_factory_equipment(
    rooms: Mapping[str, PlacedRectangleV1],
    specs: Mapping[str, Any],
    zone_plan: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
    access: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    spaces: list[dict[str, Any]] = []
    demands: dict[str, int] = {}
    portal_spaces: list[dict[str, Any]] = []
    for route in access:
        if route.get("status") != "PASS":
            continue
        for portal_side in ("from", "to"):
            code = str(route.get(portal_side + "_ref"))
            portal = route.get("portal_" + portal_side)
            if code not in rooms or not portal:
                continue
            segment = portal["segment"]
            x = round((float(segment["start"]["x"]) + float(segment["end"]["x"])) * 500)
            y = round((float(segment["start"]["y"]) + float(segment["end"]["y"])) * 500)
            half = round(float(portal["clear_width_m"]) * 500)
            depth = 2000 if route["flow_kind"] == "PERSONNEL" else 2500
            a, b, c, d = rooms[code].bounds_mm
            box = (
                [x, y - half, x + depth, y + half]
                if x == a
                else [x - depth, y - half, x, y + half]
                if x == c
                else [x - half, y, x + half, y + depth]
                if y == b
                else [x - half, y - depth, x + half, y]
            )
            portal_spaces.append(
                {
                    "id": portal["identity"],
                    "room": code,
                    "kind": "portal_approach_design_reservation",
                    "bbox_mm": box,
                    "basis": "Original portal width; 2000/2500mm inward design reservation",
                }
            )

    def local_box(code: str, box: Sequence[int]) -> list[int]:
        q = rooms[code]
        x, y, _, _ = q.bounds_mm
        h = int(q.depth_m * 1000)
        a, b, c, d = box
        return (
            [x + a, y + b, x + c, y + d]
            if q.rotation_deg == 0
            else [x + h - d, y + a, x + h - b, y + c]
        )

    def add(code: str, id_: str, kind: str, box: Sequence[int], basis: str, **extra: Any) -> None:
        b = local_box(code, box)
        room = rooms[code].bounds_mm
        causes = []
        if not (room[0] <= b[0] < b[2] <= room[2] and room[1] <= b[1] < b[3] <= room[3]):
            causes.append("OUTSIDE_GENERATED_ROOM")
        causes.extend(str(q["id"]) for q in columns if positive_intersection(b, q["bbox_mm"]))
        causes.extend(
            q["id"] for q in items if q["room"] == code and positive_intersection(b, q["bbox_mm"])
        )
        row = {
            "id": id_,
            "kind": kind,
            "room": code,
            "bbox_mm": b,
            "local_bbox_mm": list(box),
            "rotation_deg": rooms[code].rotation_deg,
            "basis": basis,
            **extra,
        }
        if causes:
            rejected.append({**row, "status": "PLACEMENT_REJECTED", "conflicts": causes})
        else:
            items.append({**row, "status": "BODY_PLACED_OPERATION_NOT_APPROVED"})

    code = "sorting_packaging_room"
    q = rooms[code]
    w, h = int(q.width_m * 1000), int(q.depth_m * 1000)
    line = specs["packing_line"]
    length, depth = line["length_mm"], line["width_mm"]
    demands["packing_line"] = line["quantity"]
    ys = [
        3500 + i * max(1, (h - 4000 - depth) // max(1, line["quantity"] - 1))
        for i in range(line["quantity"])
    ]
    phase = 0
    for shift in (0, 100, 200, 300, 400, 500):
        boxes = [local_box(code, [2500, y + shift, 2500 + length, y + shift + depth]) for y in ys]
        if all(y + shift + depth <= h - 100 for y in ys) and not any(
            positive_intersection(box, col["bbox_mm"]) for box in boxes for col in columns
        ):
            phase = shift
            break
    for i in range(line["quantity"]):
        y = ys[i] + phase
        add(
            code,
            f"PACK-{i + 1:02}",
            "packing_line",
            [2500, y, 2500 + length, y + depth],
            line["basis"],
            material_direction="LOCAL_POSITIVE_X",
        )
        spaces.append(
            {
                "id": f"OP-PACK-{i + 1:02}",
                "room": code,
                "kind": "operator_working_strip",
                "bbox_mm": local_box(code, [2500, y - line["operator_side_mm"], 2500 + length, y]),
                "basis": (
                    "Unapproved 1000mm operation-depth sensitivity; not personnel-motion validation"
                ),
            }
        )
    spaces.append(
        {
            "id": "SORT-TRANSPORT",
            "room": code,
            "kind": "material_clear_aisle",
            "bbox_mm": local_box(code, [0, 0, w, 2500]),
            "basis": "Existing MATERIAL Access clear width 2500mm",
        }
    )
    erect = specs["case_erector"]
    demands["case_erector"] = erect["quantity"]
    sx = 2500 + length + 2500
    ew, eh = erect["width_mm"], erect["length_mm"]
    gx = max(0, (w - 200 - sx - 3 * ew) // 2)
    gy = max(0, h - 2600 - 2 * eh)
    for i in range(erect["quantity"]):
        a, b = sx + (i % 3) * (ew + gx), 2500 + (i // 3) * (eh + gy)
        add(
            code,
            f"ERECT-{i + 1:02}",
            "case_erector",
            [a, b, a + ew, b + eh],
            erect["basis"],
            material_direction="LOCAL_NEGATIVE_X",
            operation_gap_status="REVIEW_REQUIRED_SIDE_GAPS_NOT_MANUFACTURER_GUARANTEED",
        )

    for code, prefix in (("primary_precooling_room", "PRI"), ("secondary_precooling_room", "SEC")):
        q = rooms[code]
        count = round(float(q.width_m) / 4.9)
        demands[prefix + "_pallet"] = count * 6
        for cell in range(count):
            for side in range(2):
                for row in range(3):
                    x = cell * 4900 + (0 if side == 0 else 3700)
                    y = 2500 + row * 2000
                    add(
                        code,
                        f"{prefix}-C{cell + 1}-P{side * 3 + row + 1}",
                        prefix + "_pallet",
                        [x, y, x + 1200, y + 1000],
                        "P1 6-position/4900x10050 cell; 1200x1000mm nominal pallet",
                        carrier="TURNOVER_CRATES"
                        if prefix == "PRI"
                        else "CARTONS_CLAMSHELLS_ON_PALLET",
                    )
            x = cell * 4900 + 2150
            add(
                code,
                f"{prefix}-FAN-{cell + 1}",
                "forced_air_fan_allowance",
                [x, 9250, x + 600, 9850],
                "Conditional 600x600mm fan/tarp-plenum envelope, no cooling-performance approval",
            )
            spaces.append(
                {
                    "id": f"{prefix}-CELL-{cell + 1}-AISLE",
                    "room": code,
                    "kind": "material_clear_aisle",
                    "bbox_mm": local_box(code, [cell * 4900 + 1200, 0, cell * 4900 + 3700, 9000]),
                    "basis": "2500mm center aisle; fan-plenum at rear; no air-performance claim",
                }
            )

    upstream = {z["zone_code"]: z for z in zone_plan["result"]["zones"]}
    for code in (
        "raw_fruit_buffer",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "packaging_material_storage",
    ):
        z = upstream[code]
        if code == "packaging_material_storage":
            nc, nr, sx, sy, px, py, pw, ph = 17, 4, 150, 150, 1000, 4200, 1000, 1200
        else:
            nc, nr = z["n_long"], z["n_short"]
            sx = 2200 if code == "raw_fruit_buffer" else 0
            sy = 2200 if code == "raw_fruit_buffer" else 3000
            px, py, pw, ph = 1200, 1300, 1200, 1000
        count = z["position_count"]
        demands[code + "_pallet"] = count
        for i in range(min(count, nc * nr)):
            x, y = sx + (i % nc) * px, sy + (i // nc) * py
            add(
                code,
                f"{code}-PAL-{i + 1:03}",
                code + "_pallet",
                [x, y, x + pw, y + ph],
                (
                    "Unchanged upstream P1 grid counts/pitch; rejected colum"
                    "n intersections are retained, never hidden"
                ),
            )

    code = "coating_room"
    q = rooms[code]
    w, h = int(q.width_m * 1000), int(q.depth_m * 1000)
    f = specs["case_film_line"]
    length, depth = f["length_mm"], f["width_mm"]
    along_x = w >= length + 1000
    demands["case_film_line"] = 1
    center = (
        ((w - length) // 2, (h - depth) // 2) if along_x else ((w - depth) // 2, (h - length) // 2)
    )
    x, y = center
    lengths = [part["length_mm"] for part in f["components"]]
    boundaries = [0]
    for value in lengths:
        boundaries.append(boundaries[-1] + value)
    for i, label in enumerate(("INFEED", "SEALER", "FILM", "OUTFEED")):
        a, b = boundaries[i : i + 2]
        box = [x + a, y, x + b, y + depth] if along_x else [x, y + a, x + depth, y + b]
        add(
            code,
            "FILM-" + label,
            "case_film_component",
            box,
            f["basis"],
            material_direction="LOCAL_POSITIVE_X" if along_x else "LOCAL_POSITIVE_Y",
        )
    for i, label in enumerate(("DEPALLETIZE", "REPALLETIZE")):
        x = 1000 if i == 0 else w - 2200
        add(
            code,
            label,
            "pallet_handoff",
            [x, 1000, x + 1200, 2000],
            "1200x1000 pallet working place; internal route separately checked",
        )

    code = "changing_room"
    q = rooms[code]
    w, h = int(q.width_m * 1000), int(q.depth_m * 1000)
    locker = specs["locker"]
    demands["ten_door_locker"] = locker["quantity"]
    horizontal = []
    vertical = []
    for i in range(locker["quantity"]):
        row, col = (0, i) if i < 6 else (1, i - 6)
        x, y = (
            100 + col * (locker["width_mm"] + 50),
            100 if row == 0 else h - locker["depth_mm"] - 100,
        )
        horizontal.append([x, y, x + locker["width_mm"], y + locker["depth_mm"]])
        x = 100 if row == 0 else w - locker["depth_mm"] - 100
        y = 100 + col * (locker["width_mm"] + 50)
        vertical.append([x, y, x + locker["depth_mm"], y + locker["width_mm"]])
    layouts = (horizontal, vertical)
    blockers = [q["bbox_mm"] for q in columns] + [
        q["bbox_mm"] for q in portal_spaces if q["room"] == code
    ]

    def rejected_count(layout: list[list[int]]) -> int:
        world = [local_box(code, box) for box in layout]
        a, b, c, d = rooms[code].bounds_mm
        return sum(
            not (a <= box[0] < box[2] <= c and b <= box[1] < box[3] <= d)
            or any(positive_intersection(box, obstacle) for obstacle in blockers)
            for box in world
        )

    selected = min(layouts, key=rejected_count)
    for i, box in enumerate(selected):
        add(
            code,
            f"LOCKER-U{i + 1:02}",
            "ten_door_locker",
            box,
            locker["basis"],
            compartments=10,
            height_mm=locker["height_mm"],
            equipment_rotation_deg=(rooms[code].rotation_deg + (90 if selected is vertical else 0))
            % 180,
            hinge_status="INPUT_REQUIRED",
            occupancy_status="53_PEOPLE_FULL_OPERATION_NOT_EVALUATED",
        )

    clearance = []
    for space in spaces + portal_spaces:
        conflicts = [
            q["id"]
            for q in items
            if q["room"] == space["room"] and positive_intersection(q["bbox_mm"], space["bbox_mm"])
        ]
        conflicts += [
            str(q["id"]) for q in columns if positive_intersection(q["bbox_mm"], space["bbox_mm"])
        ]
        clearance.append(
            {
                **space,
                "status": "GEOMETRIC_CONFLICT"
                if conflicts
                else "NO_BODY_INTERSECTION_IN_CHECKED_ENVELOPE",
                "conflicts": conflicts,
            }
        )
    count_by_kind = {
        kind: sum(x["kind"] == kind for x in items) for kind in sorted({x["kind"] for x in items})
    }
    capacity = []
    for code in (
        "raw_fruit_buffer",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
        "packaging_material_storage",
    ):
        source = upstream[code]
        required = int(source.get("n_need", source["position_count"]))
        placed = count_by_kind.get(code + "_pallet", 0)
        capacity.append(
            {
                "zone_code": code,
                "required_positions": required,
                "original_grid_positions": int(source["position_count"]),
                "body_positions_placed": placed,
                "body_position_shortfall": max(0, required - placed),
                "all_stock_retrieval": "NOT_EVALUATED",
                "design_storage_mass_kg": source.get("design_storage_mass_kg"),
                "original_frozen_deduction_ratio": source.get("frozen_deduction_ratio"),
                "scope": (
                    "Original calculator allocation retained; "
                    "not a new 20t/day throughput certificate"
                ),
            }
        )
    return {
        "calculator_version": "room-local-equipment-placement@1.0.0",
        "items": items,
        "rejected_items": rejected,
        "requested_counts": demands,
        "placed_counts": count_by_kind,
        "operating_spaces": clearance,
        "storage_body_capacity_checks": capacity,
        "scope": (
            "Body fit, column collision and listed static aisle/oper"
            "ation envelopes. No cooling performance, all-stock retr"
            "ieval or full personnel-motion approval."
        ),
        "full_equipment_engineering_pass": False,
    }
