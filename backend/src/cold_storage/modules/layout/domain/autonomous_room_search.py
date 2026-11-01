"""Finite, opt-in attachment search over existing P1 rectangles. No native solver.

This adds event anchors and process-first ordering, not engineering constraints.
An exhausted template is explicitly not a proof of global infeasibility.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from math import isqrt
from typing import Any

from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.placement import _ceil_area_depth
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    validate_flexible_candidate,
)

VERSION = "autonomous-process-attachment-search@1.0.0"
ORDER = (
    "sorting_packaging_room",
    "packaging_material_storage",
    "secondary_precooling_room",
    "primary_precooling_room",
    "raw_fruit_buffer",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
    "office",
    "changing_room",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
)
PROFILES = ("LINEAR_BANDED", "CENTRAL_PROCESS_CORE", "PROCESS_SPINE_WITH_PERIPHERAL_BANKS")


def _m(n: int) -> Decimal:
    return Decimal(n) / 1000


def _bounds(poly: PolygonMM) -> tuple[int, int, int, int]:
    return (
        min(p[0] for p in poly),
        min(p[1] for p in poly),
        max(p[0] for p in poly),
        max(p[1] for p in poly),
    )


def _shared(a: PlacedRectangleV1, b: PlacedRectangleV1) -> int:
    return _shared_boxes(a.bounds_mm, b.bounds_mm)


def _shared_boxes(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> int:
    x, y, r, t = first
    u, v, s, z = second
    if r == u or s == x:
        return max(0, min(t, z) - max(y, v))
    if t == v or z == y:
        return max(0, min(r, s) - max(x, u))
    return 0


def _shapes(authority: Mapping[str, Any], remaining_widths: set[int]) -> list[tuple[int, int, int]]:
    if authority["dimension_mode"] != "FLEXIBLE_RECTANGLE":
        g = authority["geometry"]
        return [
            (int(Decimal(str(g["width_m"])) * 1000), int(Decimal(str(g["depth_m"])) * 1000), r)
            for r in authority["rotation_allowed"]
        ]
    area = Decimal(str(authority["required_area_m2"]))
    near = isqrt(int(area * 1_000_000)) + 1
    pairs = set()
    for w in {near, 4000, 5000, 6000, 8000, 10000, 12000, *remaining_widths}:
        if not 2500 <= w <= 30000:
            continue
        h = _ceil_area_depth(area, w)
        validate_flexible_candidate(authority, _m(w), _m(h))
        pairs.add((w, h))
    return [(w, h, 0) for w, h in sorted(pairs, key=lambda q: (max(q) / min(q), q))]


def search_room_arrangements(
    authorities: Mapping[str, Mapping[str, Any]],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    *,
    profile: str,
    node_budget: int = 12000,
    complete_limit: int = 1,
    internal_columns: Sequence[PolygonMM] = (),
    personnel_entry: tuple[int, int] | None = None,
) -> tuple[list[dict[str, PlacedRectangleV1]], dict[str, Any]]:
    if profile not in PROFILES or not 1 <= node_budget <= 60000 or not 1 <= complete_limit <= 4:
        raise ValueError("AUTONOMOUS_SEARCH_CONFIGURATION_INVALID")
    if set(authorities) != set(ORDER):
        raise ValueError("AUTONOMOUS_ROLE_SET_INVALID")
    bb = _bounds(boundary)
    obs = [(_bounds(q), q) for q in obstacles]
    columns = [_bounds(q) for q in internal_columns]
    entry_band = (
        isqrt(int(Decimal(str(authorities["changing_room"]["required_area_m2"])) * 1000000)) + 2500
    )
    fixed_ys = sorted(
        {
            bb[1] + 500,
            bb[1] + entry_band,
            bb[3] - 500,
            *[v + d for b, _ in obs for v in (b[1], b[3]) for d in (-1, 1)],
        }
    )
    placed: dict[str, PlacedRectangleV1] = {}
    results: list[dict[str, PlacedRectangleV1]] = []
    stats: dict[str, Any] = {
        "version": VERSION,
        "profile": profile,
        "node_budget": node_budget,
        "nodes_used": 0,
        "options_checked": 0,
        "max_roles": 0,
        "global_infeasibility_proven": False,
        "new_hard_constraints": False,
    }
    graph = process_graph()
    extra = (
        ("packaging_material_storage", "sorting_packaging_room"),
        ("secondary_fruit_buffer", "sorting_packaging_room"),
        ("frozen_fruit_room", "sorting_packaging_room"),
    )

    def clear(rect: PlacedRectangleV1) -> bool:
        b = rect.bounds_mm
        if b[0] < bb[0] or b[1] < bb[1] or b[2] > bb[2] or b[3] > bb[3]:
            return False
        if any(rectangles_overlap(rect, q) for q in placed.values()):
            return False
        for o, poly in obs:
            if (
                b[0] <= o[2]
                and b[2] >= o[0]
                and b[1] <= o[3]
                and b[3] >= o[1]
                and rectangle_intersects_closed_obstacle(rect, poly)
            ):
                return False
        return rectangle_inside_polygon(rect, boundary)

    def options(code: str) -> list[PlacedRectangleV1]:
        neighbors = [
            placed[b if a == code else a]
            for a, b in graph.must_adjacencies + extra
            if code in (a, b) and (b if a == code else a) in placed
        ]
        rem = {bb[2] - q.bounds_mm[2] for q in placed.values()} | {
            q.bounds_mm[0] - bb[0] for q in placed.values()
        }
        shapes = _shapes(authorities[code], rem)
        occupied = [q.bounds_mm for q in placed.values()]
        neighbor_boxes = [q.bounds_mm for q in neighbors]
        found: dict[tuple[int, int, int, int], PlacedRectangleV1] = {}
        for w, h, rot in shapes:
            ww, hh = (h, w) if rot == 90 else (w, h)
            if code == "packaging_material_storage":
                sb = placed["sorting_packaging_room"].bounds_mm
                if (ww > hh) == (sb[2] - sb[0] > sb[3] - sb[1]):
                    continue  # LONG->SHORT in either legal building orientation
            anchors: set[tuple[int, int]] = set()
            if not neighbors and code == "changing_room":
                ex, ey = personnel_entry or ((bb[0] + bb[2]) // 2, bb[1])
                xs = {ex - ww // 2, bb[0] + 2500, bb[2] - ww - 2500}
                xs.update(q.bounds_mm[2] + 2500 for q in placed.values())
                xs.update(q.bounds_mm[0] - ww - 2500 for q in placed.values())
                ys = {ey + 2500, bb[3] - hh - 2500}
                root = placed["sorting_packaging_room"].bounds_mm
                ys.update((root[1] - hh, root[3], root[3] + 2500))
                anchors.update((x, y) for x in xs for y in ys)
            elif not neighbors:
                xs = {bb[0] + 100, bb[2] - ww - 100, (bb[0] + bb[2] - ww) // 2}
                for authority in authorities.values():
                    g = authority.get("geometry")
                    if g:
                        for dim in (g["width_m"], g["depth_m"]):
                            span = int(Decimal(str(dim)) * 1000)
                            xs.update((bb[0] + 100 + span, bb[2] - 100 - ww - span))
                for y in fixed_ys:
                    anchors.update((x, yy) for x in xs for yy in (y, y - hh))
            for q in neighbors:
                x, y, r, t = q.bounds_mm
                ys = {y, t - hh, (y + t - hh) // 2}
                xs = {x, r - ww, (x + r - ww) // 2}
                for other in placed.values():
                    ob = other.bounds_mm
                    ys.update((ob[1], ob[3], ob[1] - hh, ob[3] - hh))
                    xs.update((ob[0], ob[2], ob[0] - ww, ob[2] - ww))
                ys.update(v for v in fixed_ys if y - hh + 2400 <= v <= t - 2400)
                anchors.update((xx, yy) for xx in (x - ww, r) for yy in ys)
                anchors.update((xx, yy) for yy in (y - hh, t) for xx in xs)
            for x, y in anchors:
                stats["options_checked"] += 1
                b = (x, y, x + ww, y + hh)
                if x < bb[0] or y < bb[1] or b[2] > bb[2] or b[3] > bb[3]:
                    continue
                if any(
                    min(b[2], o[2]) > max(x, o[0]) and min(b[3], o[3]) > max(y, o[1])
                    for o in occupied
                ):
                    continue
                if any(
                    _shared_boxes(b, n) < (1500 if code == "changing_room" else 2400)
                    for n in neighbor_boxes
                ):
                    continue
                # All source obstacles are axis-aligned exact rectangles in
                # this input. This cheap necessary filter precedes the same
                # original exact polygon predicate below.
                if any(x <= o[2] and b[2] >= o[0] and y <= o[3] and b[3] >= o[1] for o, _ in obs):
                    continue
                # Separate, explicit real-building interpretation: a room may
                # contain a retained column, but a new partition cannot cut it.
                # Net floor area and equipment loss remain separate diagnostics.
                if any(
                    min(b[2], o[2]) > max(x, o[0])
                    and min(b[3], o[3]) > max(y, o[1])
                    and not (x <= o[0] and y <= o[1] and b[2] >= o[2] and b[3] >= o[3])
                    for o in columns
                ):
                    continue
                rect = PlacedRectangleV1(code, _m(x), _m(y), _m(w), _m(h), rot)
                if not clear(rect) or any(
                    _shared(rect, n) < (1500 if code == "changing_room" else 2400)
                    for n in neighbors
                ):
                    continue
                if code == "packaging_material_storage":
                    n = placed["sorting_packaging_room"]
                    nb = n.bounds_mm
                    vertical = nb[2] - nb[0] > nb[3] - nb[1]
                    if vertical and rect.bounds_mm[0] != nb[2] and rect.bounds_mm[2] != nb[0]:
                        continue
                    if not vertical and rect.bounds_mm[1] != nb[3] and rect.bounds_mm[3] != nb[1]:
                        continue
                found[(x, y, ww, hh)] = rect

        def score(q: PlacedRectangleV1) -> tuple[Any, ...]:
            x, y, r, t = q.bounds_mm
            cx, cy = (x + r) // 2, (y + t) // 2
            root = placed.get("sorting_packaging_room", q).bounds_mm
            rcx, rcy = (root[0] + root[2]) // 2, (root[1] + root[3]) // 2
            if code == "sorting_packaging_room":
                band_y = (
                    (bb[1] + bb[3] - (t - y)) // 2
                    if profile == "CENTRAL_PROCESS_CORE"
                    else bb[1] + entry_band
                )
                return abs(y - band_y), abs(cx - (bb[0] + bb[2]) // 2), x, y
            preferred_left = code in (
                "packaging_material_storage",
                "primary_precooling_room",
                "raw_fruit_buffer",
            )
            if profile == "PROCESS_SPINE_WITH_PERIPHERAL_BANKS":
                preferred_left = code in ("primary_precooling_room", "raw_fruit_buffer")
            side = int((cx > rcx) if preferred_left else (cx < rcx))
            compact = max(r - x, t - y) / min(r - x, t - y)
            if code == "changing_room":
                ex, ey = personnel_entry or ((bb[0] + bb[2]) // 2, bb[1])
                return compact, abs(cx - ex) + abs(cy - ey), x, y
            return (
                side,
                compact if authorities[code]["dimension_mode"] == "FLEXIBLE_RECTANGLE" else 0,
                abs(cy - rcy),
                x,
                y,
            )

        return sorted(found.values(), key=score)[
            : (240 if code == "sorting_packaging_room" else 80)
        ]

    def walk(index: int) -> None:
        if stats["nodes_used"] >= node_budget or len(results) >= complete_limit:
            return
        stats["nodes_used"] += 1
        stats["max_roles"] = max(stats["max_roles"], index)
        if index == len(ORDER):
            if all(
                rectangles_share_positive_edge(placed[a], placed[b])
                for a, b in graph.must_adjacencies
            ):
                results.append(dict(placed))
            return
        code = ORDER[index]
        for rect in options(code):
            placed[code] = rect
            walk(index + 1)
            placed.pop(code)
            if stats["nodes_used"] >= node_budget or len(results) >= complete_limit:
                return

    roots = options(ORDER[0])
    stats["root_count"] = len(roots)
    per_root = max(120, node_budget // max(1, len(roots)))
    for root in roots:
        start = stats["nodes_used"]
        total_limit = node_budget
        node_budget = min(total_limit, start + per_root)
        placed[ORDER[0]] = root
        walk(1)
        placed.pop(ORDER[0])
        node_budget = total_limit
        if stats["nodes_used"] >= node_budget or len(results) >= complete_limit:
            break
    stats["status"] = "CANDIDATE_FOUND" if results else "BOUNDED_TEMPLATE_NO_CANDIDATE"
    stats["template_limitations"] = (
        "Finite event anchors; direct auxiliary attachments; 80 "
        "ordered options/role. Profiles are search preferences, "
        "not certified V2 composition identities."
    )
    return results, stats
