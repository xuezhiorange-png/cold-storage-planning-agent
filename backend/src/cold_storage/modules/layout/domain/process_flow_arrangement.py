"""Finite internal arrangements for device-to-device logistics, never Native.

N/S identify the B4 production service groups, not copied B1 hall coordinates.
Every buffer and line pallet address is an independent physical rectangle.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.functional_material_geometry import (
    bounds_inside,
    swept_boxes,
)
from cold_storage.modules.layout.domain.functional_storage_layout import storage_layouts
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def coating_service_depth(parameters: Mapping[str, Any]) -> dict[str, Any]:
    aisle = int(parameters["main_aisle_mm"])
    pallet_depth = max(parameters["pallet_mm"])
    operation = int(parameters["station_operator_mm"][1])
    gap = int(parameters["station_gap_mm"])
    finish = int(parameters["station_boundary_margin_mm"])
    half = pallet_depth // 2 + operation + gap + finish
    return {
        "depth_mm": 2 * (aisle + half),
        "formula": "2*(main aisle + pallet half-depth + operator depth + gap + boundary margin)",
        "input_mm": {
            "aisle": aisle,
            "pallet_depth": pallet_depth,
            "operator_depth": operation,
            "gap": gap,
            "boundary_margin": finish,
        },
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
    }


def realize_coating_aisles(
    candidate: dict[str, Any], flows: Mapping[str, Any], static_conflicts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Replace blocked rectangular proposals with the ACTUAL equal-width route.

    No occupied rectangle is silently accepted. Every replacement is rechecked
    against all bodies (including both stationary handoff pallets), operators,
    columns and the original room. Source/destination exceptions are NOT used.
    """
    code = "coating_room"
    eq = candidate["equipment"]
    layout = eq["layouts"][code]
    rejected = [a for a in eq["operating_spaces"] if a["room"] == code and a["conflicts"]]
    if not rejected:
        return {"status": "ORIGINAL_RESERVED_AISLES_CLEAR", "rejected_proposals": []}
    clear = next(q["bbox_mm"] for q in candidate["rooms"] if q["zone_code"] == code)
    fixed = [
        *eq["items"],
        *eq.get("process_operator_zones", []),
        *candidate["original_building"]["columns"],
    ]
    replacements = {}
    failures = []
    for row in flows["routes"]:
        if row["status"] != "CONDITIONAL_DEVICE_ROUTE_VERIFIED":
            continue
        for seg in row.get("segments", []):
            if seg["kind"] != "ROOM_MAIN_AISLE" or seg["room"] != code:
                continue
            width = seg["reserved_width_mm"]
            boxes = swept_boxes(seg["centerline_mm"], width, width)
            if not boxes and seg["centerline_mm"]:
                x, y = seg["centerline_mm"][0]
                boxes = [
                    (x - width // 2, y - width // 2, x + width - width // 2, y + width - width // 2)
                ]
            for b in boxes:
                collisions = [q["id"] for q in fixed if positive_intersection(b, q["bbox_mm"])]
                if not bounds_inside(b, clear) or collisions:
                    failures.append(
                        {"route": row["id"], "bbox_mm": list(b), "conflicts": collisions}
                    )
                replacements[b] = {
                    "bbox_mm": list(b),
                    "clear_width_mm": width,
                    "source_route": row["id"],
                }
    if failures or not replacements:
        return {
            "status": "ACTUAL_AISLE_REJECTED",
            "rejected_proposals": rejected,
            "failures": failures,
        }
    proposals = [a for a in eq["operating_spaces"] if a["room"] == code and not a["conflicts"]]
    realized = [
        {"id": f"FILM-ACTUAL-{i + 1}", **a, "conflicts": []}
        for i, a in enumerate(replacements.values())
    ]
    layout["service_corridors"] = [*proposals, *realized]
    eq["operating_spaces"] = [a for a in eq["operating_spaces"] if a["room"] != code] + [
        {"room": code, **a} for a in layout["service_corridors"]
    ]
    static_conflicts[:] = [
        x
        for x in static_conflicts
        if not (x["code"] == "RESERVED_AISLE_OCCUPIED" and x.get("room") == code)
    ]
    return {
        "status": "EQUAL_WIDTH_ACTUAL_ROUTES_REALIZED",
        "rejected_proposals": rejected,
        "realized_reserved_aisles": realized,
        "stationary_pallets_retained": True,
        "geometry_exceptions_used": False,
    }


def relocation_capacity_trials(
    rooms: Mapping[str, PlacedRectangleV1],
    plan: Mapping[str, Any],
    specs: Mapping[str, Any],
    columns: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Try a real second full erector in the material store before rejecting it."""
    q = rooms["packaging_material_storage"]
    x, y, r, _ = q.bounds_mm
    zone = next(z for z in plan["result"]["zones"] if z["zone_code"] == q.zone_code)
    ew, eh = int(specs["case_erector"]["length_mm"]), int(specs["case_erector"]["width_mm"])
    trials = []
    for offset in (100, 300, 600, 900, 1200, 1500):
        b = [r - 5000 - 100 - ew, y + offset, r - 5000 - 100, y + offset + eh]
        obstacle = {"id": "equipment:ERECT-02", "bbox_mm": b}
        choices = storage_layouts(q, zone, [*columns, obstacle], case_erector=specs["case_erector"])
        east = [c for c in choices if c["turn"] == 1]
        best = max(east, key=lambda c: c["placed_positions"])
        trials.append(
            {
                "variant": "SECOND_ERECTOR_IN_MATERIAL_STORE",
                "offset_mm": offset,
                "equipment_bbox_mm": b,
                "minimum_positions": best["minimum_positions"],
                "placed_positions": best["placed_positions"],
                "status": "CAPACITY_REJECTED"
                if not best["static_capacity_pass"]
                else "STATIC_CAPACITY_ONLY",
                "authority_changed": False,
            }
        )
    return trials


def arrange_process_workplaces(
    candidate: Mapping[str, Any], parameters: Mapping[str, Any]
) -> dict[str, Any]:
    """Keep rooms and counts; rotate four erectors and re-space non-route gaps."""
    c = copy.deepcopy(candidate)
    eq = c["equipment"]
    items = eq["items"]
    rooms = {r["zone_code"]: r for r in c["rooms"]}
    box = rooms["sorting_packaging_room"]["bbox_mm"]
    sx, sy, sr, st = box
    aisle = int(parameters["main_aisle_mm"])
    gap = int(parameters["interpair_nonroute_gap_mm"])
    packing = sorted((i for i in items if i["kind"] == "packing_line"), key=lambda q: q["id"])
    length = packing[0]["bbox_mm"][2] - packing[0]["bbox_mm"][0]
    depth = packing[0]["bbox_mm"][3] - packing[0]["bbox_mm"][1]
    op = 1000
    left = sx + aisle + 100
    first = sy + aisle + 50
    pair_h = 2 * depth + op
    operators: list[dict[str, Any]] = []
    staffing = parameters["line_workers"]
    for pair in range(3):
        bottom = first + pair * (pair_h + gap)
        for side in range(2):
            i = 2 * pair + side
            y = bottom + side * (depth + op)
            packing[i].update(
                bbox_mm=[left, y, left + length, y + depth],
                material_direction="WORLD_POSITIVE_X",
                rotation_deg=0,
            )
        for line_no in (2 * pair + 1, 2 * pair + 2):
            for _ in range(staffing[line_no - 1]):
                j = len([p for p in operators if p["pair"] == pair])
                x = left + 150 + j * 800
                operators.append(
                    {
                        "id": f"PACK-OP-{len(operators) + 1:02}",
                        "room": "sorting_packaging_room",
                        "pair": pair,
                        "line": line_no,
                        "bbox_mm": [x, bottom + depth + 50, x + 600, bottom + depth + 950],
                        "source_type": "demo",
                        "validity_status": "unverified",
                        "requires_review": True,
                    }
                )
    transfer = [left + length + 100, sy, left + length + aisle + 100, st]
    bank = transfer[2] + 100
    case = [
        i for i in items if i["kind"] == "case_erector" and i["room"] == "sorting_packaging_room"
    ]
    old = case[0]["bbox_mm"]
    cw, ch = old[2] - old[0], old[3] - old[1]
    # All four original full bodies rotate.  Two discharge north and two south
    # into the 2500mm middle aisle; magazine faces share a larger operation bay.
    row_bottom = sy + 50
    case_middle = row_bottom + cw
    inner_gap = int(parameters["case_magazine_bay_mm"])
    for i, q in enumerate(sorted(case, key=lambda q: q["id"])):
        col = i % 2
        case_row = i // 2
        x = bank + col * (ch + inner_gap)
        y = row_bottom + case_row * (cw + aisle)
        q.update(
            bbox_mm=[x, y, x + ch, y + cw],
            rotation_deg=90 if case_row == 0 else 270,
            equipment_rotation_deg=90 if case_row == 0 else 270,
            output_face="N" if case_row == 0 else "S",
            magazine_face="E" if col == 0 else "W",
            interface_status="DESIGN_ASSUMPTION_VENDOR_CONFIRMATION_REQUIRED",
        )
    middle = [transfer[0], case_middle, sr, case_middle + aisle]
    east = [sr - aisle, sy, sr, st]
    north = [sx, st - aisle, transfer[2], st]
    south = [sx, sy, transfer[2], sy + aisle]
    corridors = [
        {"id": name, "bbox_mm": b, "clear_width_mm": aisle}
        for name, b in (
            ("SORT-WEST", [sx, sy, sx + aisle, st]),
            ("SORT-TRANSFER", transfer),
            ("CASE-MIDDLE", middle),
            ("SORT-EAST", east),
            ("SORT-NORTH", north),
            ("SORT-SOUTH", south),
        )
    ]
    eq["layouts"]["sorting_packaging_room"] = {
        "service_corridors": corridors,
        "operator_positions": operators,
    }
    # 7+7 waiting pallets plus SIX separate line-end work addresses. N/S are
    # service groups re-mapped into this single autonomous room, not B1 halls.
    y = max(q["bbox_mm"][3] for q in packing) + 100
    pw, pd = min(parameters["pallet_mm"]), max(parameters["pallet_mm"])
    pitch = pw + int(parameters["pallet_tangent_gap_mm"])
    work = []
    for i in range(21):
        x = left + 100 + i * pitch
        if i < 7:
            id_ = f"BUF-N-{i + 1:02}"
            kind = "precooling_buffer"
            group = "N"
        elif i < 14:
            id_ = f"BUF-S-{i - 6:02}"
            kind = "precooling_buffer"
            group = "S"
        elif i < 20:
            id_ = f"WORK-PACK-{i - 13:02}"
            kind = "packing_pallet_workplace"
            group = "N" if i < 17 else "S"
        else:
            id_ = "RAW-UNLOAD"
            kind = "raw_crate_handoff"
            group = "RAW"
        row = {
            "id": id_,
            "room": "sorting_packaging_room",
            "kind": kind,
            "bbox_mm": [x, y, x + pw, y + pd],
            "rotation_deg": 90,
            "front": "N",
            "group": group,
            "capacity_credit": "BUFFER_ONLY" if i < 14 else "LINE_WORKPLACE_NOT_BUFFER",
            "basis": "Derived from packing bodies and maintained north aisle; no historical XY",
            "source_type": "demo",
            "validity_status": "unverified",
            "requires_review": True,
        }
        work.append(row)
    items.extend(work)
    coat = rooms["coating_room"]["bbox_mm"]
    cx, cy, cr, ct = coat
    film = sorted(
        (i for i in items if i["kind"] == "case_film_component"), key=lambda q: q["bbox_mm"][0]
    )
    centre = cy + (ct - cy) // 2
    for q in film:
        h = q["bbox_mm"][3] - q["bbox_mm"][1]
        q["bbox_mm"][1] = centre - h // 2
        q["bbox_mm"][3] = centre + (h - h // 2)
    operator_zones = []
    for id_ in ("DEPALLETIZE", "REPALLETIZE"):
        q = next(q for q in items if q["id"] == id_)
        mx = (q["bbox_mm"][0] + q["bbox_mm"][2]) // 2
        q.update(
            bbox_mm=[mx - pw // 2, centre - pd // 2, mx + pw // 2, centre + pd // 2],
            rotation_deg=90,
            front="N",
        )
        ow, od = parameters["station_operator_mm"]
        top = q["bbox_mm"][1] - parameters["station_gap_mm"]
        operator_zones.append(
            {
                "id": id_ + "-OPERATOR",
                "room": "coating_room",
                "kind": "standing_operation",
                "bbox_mm": [mx - ow // 2, top - od, mx + ow // 2, top],
                "source_type": "demo",
                "validity_status": "unverified",
                "requires_review": True,
            }
        )
    ship = rooms["shipping_channel"]["bbox_mm"]
    dispatch = {
        "id": "DISPATCH-01",
        "room": "shipping_channel",
        "kind": "dispatch_pallet_workplace",
        "bbox_mm": [ship[0] + 1500, ship[1] + 1600, ship[0] + 1500 + pw, ship[1] + 1600 + pd],
        "rotation_deg": 90,
        "front": "N",
        "basis": "Generated dispatch handoff; not truck validation",
    }
    items.append(dispatch)
    eq["process_operator_zones"] = operator_zones
    eq["layouts"]["shipping_channel"]["service_corridors"] = [
        {
            "id": "DISPATCH-NORTH",
            "bbox_mm": [ship[0], ship[3] - aisle, ship[2], ship[3]],
            "clear_width_mm": aisle,
        }
    ]
    eq["layouts"]["coating_room"]["service_corridors"] = [
        {"id": name, "bbox_mm": b, "clear_width_mm": aisle}
        for name, b in (
            ("FILM-WEST", [cx, cy, cx + aisle, ct]),
            ("FILM-EAST", [cr - aisle, cy, cr, ct]),
            ("FILM-SOUTH", [cx, cy, cr, cy + aisle]),
            ("FILM-NORTH", [cx, ct - aisle, cr, ct]),
        )
    ]
    static = []
    fixed = [*items, *operator_zones, *operators]
    columns = c["original_building"]["columns"]
    for i, q in enumerate(fixed):
        b = q["bbox_mm"]
        a = rooms[q["room"]]["bbox_mm"]
        if not (a[0] <= b[0] < b[2] <= a[2] and a[1] <= b[1] < b[3] <= a[3]):
            static.append({"code": "BODY_OUTSIDE_ROOM", "id": q["id"]})
        for other in [*fixed[:i], *columns]:
            if positive_intersection(b, other["bbox_mm"]):
                static.append({"code": "BODY_COLLISION", "id": q["id"], "other": other["id"]})
    for code, layout in eq["layouts"].items():
        if code == "shipping_channel":
            continue  # Actual 2500mm dispatch route replaces the old rectangle.
        for a in layout["service_corridors"]:
            for q in [*fixed, *columns]:
                if positive_intersection(a["bbox_mm"], q["bbox_mm"]):
                    static.append(
                        {
                            "code": "RESERVED_AISLE_OCCUPIED",
                            "room": code,
                            "aisle": a["id"],
                            "other": q["id"],
                        }
                    )
    eq["operating_spaces"] = [
        {
            "room": code,
            **a,
            "conflicts": [
                q["id"]
                for q in [*fixed, *columns]
                if positive_intersection(a["bbox_mm"], q["bbox_mm"])
            ],
        }
        for code, layout in eq["layouts"].items()
        if code != "shipping_channel"
        for a in layout["service_corridors"]
    ]
    eq["placed_counts"] = {
        k: sum(q["kind"] == k for q in items) for k in sorted({q["kind"] for q in items})
    }
    return {
        "candidate": c,
        "static_conflicts": static,
        "workplaces": work,
        "operator_zones": operator_zones,
        "group_mapping": {
            "N": {"lines": [1, 2, 3], "slots": 7},
            "S": {"lines": [4, 5, 6], "slots": 7},
            "physical_location": (
                "Two independent service groups in the regenerated north working strip, "
                "NOT copied north/south B1 hall coordinates"
            ),
        },
        "coating_service_depth": coating_service_depth(parameters),
    }
