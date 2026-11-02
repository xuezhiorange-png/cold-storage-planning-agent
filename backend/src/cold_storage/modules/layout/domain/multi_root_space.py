"""Physical identities and main-process relationship diversity, never labels."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json

MATERIAL_CORE = (
    "sorting_packaging_room",
    "primary_precooling_room",
    "secondary_precooling_room",
    "packaging_material_storage",
    "finished_goods_room",
    "shipping_channel",
    "raw_fruit_buffer",
)


def organisation_key(candidate: Mapping[str, Any]) -> str:
    """Ignore translation/reflection/quarter-turn and coating-only extensions.

    Compare actual separation/overlap/contact directions under all eight global
    orthogonal frames. A profile rename or a whole-plan mirror earns no diversity.
    """
    rooms = {r["zone_code"]: r["bbox_mm"] for r in candidate["rooms"]}
    versions = []
    for swap in (False, True):
        for sx in (-1, 1):
            for sy in (-1, 1):
                transformed = {}
                for role in MATERIAL_CORE:
                    a, b, r, t = rooms[role]
                    points = [(x, y) for x in (a, r) for y in (b, t)]
                    points = [(sx * (y if swap else x), sy * (x if swap else y)) for x, y in points]
                    transformed[role] = [
                        min(p[0] for p in points),
                        min(p[1] for p in points),
                        max(p[0] for p in points),
                        max(p[1] for p in points),
                    ]
                rows = []
                for i, role in enumerate(MATERIAL_CORE):
                    a, b, r, t = transformed[role]
                    for other in MATERIAL_CORE[i + 1 :]:
                        u, v, s, z = transformed[other]
                        rows.append(
                            [
                                role,
                                other,
                                "W" if s <= a else "E" if u >= r else "X_OVERLAP",
                                "S" if z <= b else "N" if v >= t else "Y_OVERLAP",
                                ((r == u or s == a) and min(t, z) > max(b, v))
                                or ((t == v or z == b) and min(r, s) > max(a, u)),
                            ]
                        )
                versions.append(canonical_json(rows))
    return canonical_hash(min(versions))


def physical_candidate_key(candidate: Mapping[str, Any]) -> str:
    return canonical_hash(
        {
            "project": candidate["source_input_hash"],
            "rooms": [
                (r["zone_code"], r["bbox_mm"], r["rotation_deg"])
                for r in sorted(candidate["rooms"], key=lambda q: q["zone_code"])
            ],
            "equipment": [
                (q["id"], q["room"], q["bbox_mm"], q.get("rotation_deg"))
                for q in sorted(candidate["equipment"]["items"], key=lambda q: q["id"])
            ],
            "portals": [
                (r["requirement_identity"], r.get("portal_from"), r.get("portal_to"))
                for r in sorted(
                    candidate["access_results"], key=lambda q: q["requirement_identity"]
                )
            ],
            "aisles": {
                k: v["service_corridors"] for k, v in candidate["equipment"]["layouts"].items()
            },
            "selected_path_topology": sorted(
                (q["id"], q["centerline_mm"])
                for q in candidate.get("process_continuity", {}).get("routes", [])
                if q["id"] in candidate.get("process_admission", {}).get("selected_route_ids", [])
            ),
        }
    )


def space_difference(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    aa = {q["zone_code"]: q for q in first["rooms"]}
    bb = {q["zone_code"]: q for q in second["rooms"]}
    eq0 = {q["id"]: q for q in first["equipment"]["items"]}
    eq1 = {q["id"]: q for q in second["equipment"]["items"]}
    changed = [k for k in aa if aa[k]["bbox_mm"] != bb[k]["bbox_mm"]]
    moved = [k for k in eq0 if k in eq1 and eq0[k]["bbox_mm"] != eq1[k]["bbox_mm"]]
    scale = first["original_building"]["coordinate_mapping"]["axis_x_mm"]
    threshold = min(b - a for a, b in zip(scale, scale[1:], strict=False)) // 2
    relative = []
    # Best global orthogonal alignment avoids rewarding a whole-plan mirror.
    for swap in (False, True):
        for sx in (-1, 1):
            for sy in (-1, 1):
                centers = [
                    {
                        k: [
                            (r["bbox_mm"][0] + r["bbox_mm"][2]) // 2,
                            (r["bbox_mm"][1] + r["bbox_mm"][3]) // 2,
                        ]
                        for k, r in d.items()
                    }
                    for d in (aa, bb)
                ]
                u, v = (d["sorting_packaging_room"] for d in centers)
                changed_far = []
                for k in MATERIAL_CORE:
                    p, q = (d[k] for d in centers)
                    x, y = p[0] - u[0], p[1] - u[1]
                    dx, dy = q[0] - v[0], q[1] - v[1]
                    tx, ty = sx * (dy if swap else dx), sy * (dx if swap else dy)
                    if max(abs(x - tx), abs(y - ty)) >= threshold:
                        changed_far.append(k)
                relative.append(changed_far)
    far = min(relative, key=lambda q: (len(q), q))
    return {
        "different_main_process_relationships": organisation_key(first) != organisation_key(second),
        "changed_rooms": changed,
        "changed_material_core_rooms": [k for k in changed if k in MATERIAL_CORE],
        "changed_equipment_count": len(moved),
        "changed_equipment_ids": moved,
        "changed_equipment_kinds": sorted({eq0[k]["kind"] for k in moved}),
        "coating_only_change": not any(k in MATERIAL_CORE for k in changed),
        "substantive_relative_core_changes": far,
        "diversity_distance_threshold_mm": threshold,
        "threshold_is_engineering_constraint": False,
        "substantive_spatial_change": organisation_key(first) != organisation_key(second)
        and len(far) >= 2,
    }


def uncovered_pockets(boxes: list[list[int]]) -> list[dict[str, Any]]:
    """Exact integer-cell diagnostic of enclosed empty regions, never a PASS.

    Only use the current room/corridor union. The original footprint validator
    remains the sole acceptance authority; these cells locate its failure.
    """
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    ys = sorted({v for b in boxes for v in (b[1], b[3])})
    free = {
        (i, j)
        for i in range(len(xs) - 1)
        for j in range(len(ys) - 1)
        if not any(
            xs[i] >= b[0] and xs[i + 1] <= b[2] and ys[j] >= b[1] and ys[j + 1] <= b[3]
            for b in boxes
        )
    }
    found = []
    while free:
        todo = [min(free)]
        free.remove(todo[0])
        cells = []
        edge = False
        while todo:
            i, j = todo.pop()
            cells.append([xs[i], ys[j], xs[i + 1], ys[j + 1]])
            edge |= i in (0, len(xs) - 2) or j in (0, len(ys) - 2)
            for q in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
                if q in free:
                    free.remove(q)
                    todo.append(q)
        if not edge:
            found.append(
                {
                    "bbox_mm": [
                        min(b[0] for b in cells),
                        min(b[1] for b in cells),
                        max(b[2] for b in cells),
                        max(b[3] for b in cells),
                    ],
                    "area_mm2": sum((b[2] - b[0]) * (b[3] - b[1]) for b in cells),
                    "cells_mm": sorted(cells),
                }
            )
    return found
