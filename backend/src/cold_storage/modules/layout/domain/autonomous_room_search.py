"""Finite, opt-in attachment search over existing P1 rectangles. No native solver.

This adds event anchors and process-first ordering, not engineering constraints.
An exhausted template is explicitly not a proof of global infeasibility.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from math import isqrt
from typing import Any

from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
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
CORE_ROLES = tuple(q for q in ORDER[:7] if q != "coating_room")
CORE_PREFIX_END = 7


def core_relationship_signature(rooms: Mapping[str, PlacedRectangleV1]) -> str:
    """Translation-invariant actual core contacts/sides, not a profile label."""
    rows = []
    for i, a in enumerate(CORE_ROLES):
        if a not in rooms:
            continue
        b = rooms[a].bounds_mm
        for name in CORE_ROLES[i + 1 :]:
            if name not in rooms:
                continue
            c = rooms[name].bounds_mm
            rows.append(
                [
                    a,
                    name,
                    "W" if c[2] <= b[0] else "E" if c[0] >= b[2] else "X_OVERLAP",
                    "S" if c[3] <= b[1] else "N" if c[1] >= b[3] else "Y_OVERLAP",
                    _shared_boxes(b, c) > 0,
                    rooms[name].rotation_deg,
                ]
            )
    return canonical_hash(rows)


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
    functional_shapes: Mapping[str, Sequence[tuple[int, int]]] | None = None,
    functional_alignment: bool = False,
    functional_open_chain: bool = False,
    root_index: int | None = None,
    diverse_cores: bool = False,
    side_preferences: Mapping[str, str] | None = None,
    event_root_anchors: bool = False,
    root_anchor_mm: tuple[int, int, int] | None = None,
    root_rotation_deg: int | None = None,
    partial_feasibility: Callable[[Mapping[str, PlacedRectangleV1], str], Mapping[str, Any]]
    | None = None,
    attachment_offsets: Mapping[str, Sequence[tuple[int, int]]] | None = None,
    room_targets: Mapping[str, Sequence[tuple[int, int]]] | None = None,
) -> tuple[list[dict[str, PlacedRectangleV1]], dict[str, Any]]:
    if profile not in PROFILES or not 1 <= node_budget <= 60000 or not 1 <= complete_limit <= 4:
        raise ValueError("AUTONOMOUS_SEARCH_CONFIGURATION_INVALID")
    if set(authorities) != set(ORDER):
        raise ValueError("AUTONOMOUS_ROLE_SET_INVALID")
    if root_index is not None and not 0 <= root_index < 240:
        raise ValueError("AUTONOMOUS_ROOT_INDEX_INVALID")
    if (
        root_rotation_deg is not None
        and root_rotation_deg not in authorities[ORDER[0]]["rotation_allowed"]
    ):
        raise ValueError("AUTONOMOUS_ROOT_ROTATION_INVALID")
    if root_anchor_mm is not None and (
        len(root_anchor_mm) != 3
        or any(type(v) is not int for v in root_anchor_mm)
        or root_anchor_mm[2] not in (0, 90)
    ):
        raise ValueError("AUTONOMOUS_ROOT_ANCHOR_INVALID")
    if side_preferences and any(
        k not in ORDER or v not in ("N", "S", "E", "W") for k, v in side_preferences.items()
    ):
        raise ValueError("AUTONOMOUS_ATTACHMENT_PREFERENCE_INVALID")
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
    completed_cores: set[str] = set()
    if diverse_cores:
        stats["actual_root_trials"] = []
        stats["duplicate_core_branches_pruned"] = 0
        stats["rejection_counts"] = {}
        stats["rejection_examples"] = []
    rejection_keys: set[tuple[str, str]] = set()
    if partial_feasibility is not None:
        stats["partial_constraint_checks"] = 0
        stats["partial_constraint_rejections"] = []
        stats["partial_constraint_rejection_counts"] = {}
        stats["partial_constraint_occurrences"] = []

    def rejected(reason: str, role: str, bounds: tuple[int, int, int, int], objects: Any) -> None:
        if not diverse_cores:
            return
        key = (role, reason)
        counts = stats["rejection_counts"]
        counts[role + ":" + reason] = counts.get(role + ":" + reason, 0) + 1
        if key not in rejection_keys and len(rejection_keys) < 48:
            rejection_keys.add(key)
            stats["rejection_examples"].append(
                {
                    "zone_code": role,
                    "predicate": reason,
                    "candidate_bbox_mm": list(bounds),
                    "objects": objects,
                }
            )

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
        if functional_shapes and code in functional_shapes:
            if authorities[code]["dimension_mode"] != "FLEXIBLE_RECTANGLE":
                raise ValueError("FIXED_AUTHORITY_DIMENSIONS_CANNOT_BE_REPLACED")
            shapes = []
            for w, h in functional_shapes[code]:
                validate_flexible_candidate(authorities[code], _m(w), _m(h))
                shapes.append((w, h, 0))
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
                if diverse_cores:
                    xs.update((root[0], root[2]))
                    ys.update((root[1], root[3]))
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
                if event_root_anchors:
                    ys = {o[3] + 100 for o in columns} | {o[1] - hh - 100 for o in columns}
                    anchors.update((x, y) for x in xs for y in ys)
                if root_anchor_mm is not None:
                    anchors = (
                        {(root_anchor_mm[0], root_anchor_mm[1])}
                        if rot == root_anchor_mm[2]
                        else set()
                    )
            for q in neighbors:
                x, y, r, t = q.bounds_mm
                ys = {y, t - hh, (y + t - hh) // 2}
                xs = {x, r - ww, (x + r - ww) // 2}
                if functional_alignment and code == "primary_precooling_room":
                    xs.update(x - 1250 - 4900 * j for j in range(3))
                    if partial_feasibility is not None:
                        # Derive alternative lane-to-boundary alignments from
                        # the actual sorting frontage, never archived origins.
                        xs.update(
                            target - 1250 - 4900 * j
                            for target in ((x + r) // 2, r - 1250)
                            for j in range(3)
                        )
                for other in placed.values():
                    ob = other.bounds_mm
                    ys.update((ob[1], ob[3], ob[1] - hh, ob[3] - hh))
                    xs.update((ob[0], ob[2], ob[0] - ww, ob[2] - ww))
                ys.update(v for v in fixed_ys if y - hh + 2400 <= v <= t - 2400)
                anchors.update((xx, yy) for xx in (x - ww, r) for yy in ys)
                anchors.update((xx, yy) for yy in (y - hh, t) for xx in xs)
                if attachment_offsets and code in attachment_offsets:
                    for dx, dy in attachment_offsets[code]:
                        anchors.update(((x + dx, t + dy), (r + dx, y + dy)))
            if room_targets and code in room_targets:
                anchors.update((p[0], p[1]) for p in room_targets[code])
            for x, y in anchors:
                stats["options_checked"] += 1
                b = (x, y, x + ww, y + hh)
                if x < bb[0] or y < bb[1] or b[2] > bb[2] or b[3] > bb[3]:
                    rejected("ORIGINAL_BUILDABLE_BOUNDARY", code, b, [list(bb)])
                    continue
                if any(
                    min(b[2], o[2]) > max(x, o[0]) and min(b[3], o[3]) > max(y, o[1])
                    for o in occupied
                ):
                    rejected(
                        "ORIGINAL_ROOM_NON_OVERLAP",
                        code,
                        b,
                        [
                            {"room": k, "bbox_mm": list(q.bounds_mm)}
                            for k, q in placed.items()
                            if rectangles_overlap(
                                q, PlacedRectangleV1(code, _m(x), _m(y), _m(w), _m(h), rot)
                            )
                        ]
                        if diverse_cores
                        else [],
                    )
                    continue
                if any(
                    _shared_boxes(b, n) < (1500 if code == "changing_room" else 2400)
                    for n in neighbor_boxes
                ):
                    rejected(
                        "ORIGINAL_MUST_OR_ACCESS_SHARED_FRONTAGE",
                        code,
                        b,
                        [
                            {
                                "room": q.zone_code,
                                "bbox_mm": list(q.bounds_mm),
                                "shared_mm": _shared_boxes(b, q.bounds_mm),
                            }
                            for q in neighbors
                        ]
                        if diverse_cores
                        else [],
                    )
                    continue
                # All source obstacles are axis-aligned exact rectangles in
                # this input. This cheap necessary filter precedes the same
                # original exact polygon predicate below.
                if any(x <= o[2] and b[2] >= o[0] and y <= o[3] and b[3] >= o[1] for o, _ in obs):
                    rejected("ORIGINAL_RETAINED_WALL_OBSTACLE", code, b, [list(o) for o, _ in obs])
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
                    rejected(
                        "PARTITION_CANNOT_CUT_RETAINED_COLUMN",
                        code,
                        b,
                        [
                            list(o)
                            for o in columns
                            if min(b[2], o[2]) > max(x, o[0]) and min(b[3], o[3]) > max(y, o[1])
                        ]
                        if diverse_cores
                        else [],
                    )
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
            if functional_alignment and code == "packaging_material_storage":
                return abs(t - root[3]), side, x, y
            if functional_alignment and code == "primary_precooling_room":
                target = root[0]
                if partial_feasibility is not None and profile == "CENTRAL_PROCESS_CORE":
                    target = (root[0] + root[2]) // 2
                elif (
                    partial_feasibility is not None
                    and profile == "PROCESS_SPINE_WITH_PERIPHERAL_BANKS"
                ):
                    target = root[2] - 1250
                aligned = min(abs(x + 1250 + 4900 * j - target) for j in range(3))
                return int(q.rotation_deg != 0), aligned, abs(y - root[3]), side, x, y
            if functional_alignment and code == "raw_fruit_buffer":
                primary = placed["primary_precooling_room"].bounds_mm
                return abs(t - primary[3]), side, x, y
            if functional_alignment and code in ("secondary_fruit_buffer", "frozen_fruit_room"):
                return int(t > root[1]), side, abs(cy - rcy), x, y
            if functional_alignment and code in ("secondary_precooling_room", "coating_room"):
                return int(q.rotation_deg != 0), side, abs(y - root[1]), abs(cy - rcy), x, y
            if functional_open_chain and code == "finished_goods_room":
                coating = placed["coating_room"].bounds_mm
                return abs(x - coating[0]), side, abs(cy - rcy), x, y
            if functional_open_chain and code == "shipping_channel":
                finished = placed["finished_goods_room"].bounds_mm
                return abs(y - finished[1]), abs(r - finished[0]), side, x, y
            if functional_open_chain and code == "office":
                shipping = placed["shipping_channel"].bounds_mm
                return int(y < shipping[3]), compact, side, x, y
            if functional_alignment and code == "changing_room":
                count = sum(
                    min(r, c[2]) > max(x, c[0]) and min(t, c[3]) > max(y, c[1]) for c in columns
                )
                ex, ey = personnel_entry or ((bb[0] + bb[2]) // 2, bb[1])
                return count, compact, abs(cx - ex) + abs(cy - ey), x, y
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

        def preferred_score(q: PlacedRectangleV1) -> tuple[Any, ...]:
            if room_targets and code in room_targets:
                b = q.bounds_mm
                return (
                    min(abs(b[0] - p[0]) + abs(b[1] - p[1]) for p in room_targets[code]),
                    *score(q),
                )
            if not side_preferences or code not in side_preferences:
                return score(q)
            if not neighbors and code != "changing_room":
                return score(q)
            reference = neighbors[0] if neighbors else placed["sorting_packaging_room"]
            a, b = q.bounds_mm, reference.bounds_mm
            side = "E" if a[0] >= b[2] else "W" if a[2] <= b[0] else "N" if a[1] >= b[3] else "S"
            return (int(side != side_preferences[code]), *score(q))

        return sorted(found.values(), key=preferred_score)[
            : (240 if code == "sorting_packaging_room" else 80)
        ]

    def walk(index: int) -> None:
        if stats["nodes_used"] >= node_budget or len(results) >= complete_limit:
            return
        stats["nodes_used"] += 1
        if diverse_cores and index > stats["max_roles"]:
            stats["deepest_partial_rooms"] = [
                {"zone_code": k, "bbox_mm": list(q.bounds_mm), "rotation_deg": q.rotation_deg}
                for k, q in placed.items()
            ]
        stats["max_roles"] = max(stats["max_roles"], index)
        if (
            diverse_cores
            and index >= CORE_PREFIX_END
            and core_relationship_signature(placed) in completed_cores
        ):
            stats["duplicate_core_branches_pruned"] += 1
            return
        if index == len(ORDER):
            if all(
                rectangles_share_positive_edge(placed[a], placed[b])
                for a, b in graph.must_adjacencies
            ):
                results.append(dict(placed))
                if diverse_cores:
                    completed_cores.add(core_relationship_signature(placed))
            return
        code = ORDER[index]
        for rect in options(code):
            placed[code] = rect
            if partial_feasibility is not None:
                stats["partial_constraint_checks"] += 1
                check = partial_feasibility(placed, code)
                stats["partial_constraint_occurrences"].append(
                    {
                        "check_id": check.get("check_id"),
                        "room": code,
                        "placed_roles": len(placed),
                        "admissible": check["admissible"],
                    }
                )
                if not check["admissible"]:
                    label = code + ":" + str(check["status"])
                    counts = stats["partial_constraint_rejection_counts"]
                    counts[label] = counts.get(label, 0) + 1
                    if len(stats["partial_constraint_rejections"]) < 64:
                        stats["partial_constraint_rejections"].append(
                            {"placed_roles": len(placed), "room": code, **check}
                        )
                    placed.pop(code)
                    # Rejected partial branches also consume actual node budget.
                    stats["nodes_used"] += 1
                    if stats["nodes_used"] >= node_budget:
                        return
                    continue
            walk(index + 1)
            placed.pop(code)
            if stats["nodes_used"] >= node_budget or len(results) >= complete_limit:
                return

    roots = options(ORDER[0])
    if root_rotation_deg is not None:
        roots = [q for q in roots if q.rotation_deg == root_rotation_deg]
    stats["root_count"] = len(roots)
    if root_index is not None:
        roots = roots[root_index : root_index + 1]
    per_root = max(120, node_budget // max(1, len(roots)))
    for root in roots:
        start = stats["nodes_used"]
        completed_before = len(results)
        total_limit = node_budget
        node_budget = min(total_limit, start + per_root)
        placed[ORDER[0]] = root
        if partial_feasibility is not None:
            stats["partial_constraint_checks"] += 1
            check = partial_feasibility(placed, ORDER[0])
            stats["partial_constraint_occurrences"].append(
                {
                    "check_id": check.get("check_id"),
                    "room": ORDER[0],
                    "placed_roles": 1,
                    "admissible": check["admissible"],
                }
            )
            if not check["admissible"]:
                stats["nodes_used"] += 1
                label = ORDER[0] + ":" + str(check["status"])
                counts = stats["partial_constraint_rejection_counts"]
                counts[label] = counts.get(label, 0) + 1
                if len(stats["partial_constraint_rejections"]) < 64:
                    stats["partial_constraint_rejections"].append(
                        {"placed_roles": 1, "room": ORDER[0], **check}
                    )
            else:
                walk(1)
        else:
            walk(1)
        placed.pop(ORDER[0])
        if diverse_cores:
            stats["actual_root_trials"].append(
                {
                    "bbox_mm": list(root.bounds_mm),
                    "rotation_deg": root.rotation_deg,
                    "nodes_used": stats["nodes_used"] - start,
                    "completed_in_root": len(results) - completed_before,
                }
            )
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
