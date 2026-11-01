"""Bounded integer-mm motion for joint equipment layout, not vehicle kinematics."""

from __future__ import annotations

import heapq
from collections.abc import Sequence
from typing import Any

from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.changing_room_motion import swept_segments

Box = tuple[int, int, int, int]
Point = tuple[int, int]


def bounds_inside(box: Sequence[int], clear: Sequence[int]) -> bool:
    return clear[0] <= box[0] < box[2] <= clear[2] and clear[1] <= box[1] < box[3] <= clear[3]


def swept_boxes(path: Sequence[Point], width: int, depth: int) -> list[Box]:
    return [
        (b[0], b[1], b[3], b[4]) for b in swept_segments([list(p) for p in path], width, depth, 1)
    ]


def motion_clear(
    path: Sequence[Point],
    clear: Sequence[int],
    obstacles: Sequence[Sequence[int]],
    width: int,
    depth: int,
) -> bool:
    if len(path) < 2:
        return False
    for box in swept_boxes(path, width, depth):
        if not bounds_inside(box, clear) or any(positive_intersection(box, b) for b in obstacles):
            return False
    return True


def rectilinear_path(
    start: Point,
    end: Point,
    clear: Sequence[int],
    obstacles: Sequence[Sequence[int]],
    width: int,
    depth: int,
    *,
    node_budget: int = 4000,
    waypoints: Sequence[Point] = (),
) -> tuple[list[Point], int]:
    """Original swept-body geometry; finite event grid, with no Native calls.

    Returns no witness on exhaustion. This never claims global infeasibility.
    Full-width aisle and narrow load-pickup proofs are deliberately separate.
    """
    if not 1 <= node_budget <= 20000 or min(width, depth) <= 0:
        raise ValueError("BOUNDED_MOTION_PARAMETERS_REQUIRED")
    obs = [tuple(b) for b in obstacles if positive_intersection(clear, b)]
    hw, hd = width // 2, depth // 2
    cw, cd = width - hw, depth - hd
    a, b, c, d = clear

    def free(p: Point) -> bool:
        box = [p[0] - hw, p[1] - hd, p[0] + cw, p[1] + cd]
        return bounds_inside(box, clear) and not any(positive_intersection(box, o) for o in obs)

    if not free(start) or not free(end):
        return [], 0
    if start == end:
        return [start, end], 0
    for trial in ((start, end), (start, (start[0], end[1]), end), (start, (end[0], start[1]), end)):
        if all(
            p[0] == q[0] or p[1] == q[1] for p, q in zip(trial, trial[1:], strict=False)
        ) and motion_clear(trial, clear, obs, width, depth):
            return list(dict.fromkeys(trial)), 0
    xs = {a + hw, c - cw, start[0], end[0]}
    ys = {b + hd, d - cd, start[1], end[1]}
    # Exact reserved-aisle centre lines can matter when the clear width equals
    # the requested swept width. Empty by default; prior callers are unchanged.
    xs.update(p[0] for p in waypoints)
    ys.update(p[1] for p in waypoints)
    for x, y, r, t in obs:
        xs.update((x - cw - 1, r + hw + 1))
        ys.update((y - cd - 1, t + hd + 1))
    xx = sorted(x for x in xs if a + hw <= x <= c - cw)
    yy = sorted(y for y in ys if b + hd <= y <= d - cd)
    xi = {x: i for i, x in enumerate(xx)}
    yi = {y: i for i, y in enumerate(yy)}
    distance = {start: 0}
    previous: dict[Point, Point] = {}
    queue = [(abs(start[0] - end[0]) + abs(start[1] - end[1]), 0, start)]
    checked: dict[Point, bool] = {}
    nodes = 0
    while queue and nodes < node_budget:
        _, cost, p = heapq.heappop(queue)
        if cost != distance[p]:
            continue
        nodes += 1
        if p == end:
            route = [p]
            while route[-1] != start:
                route.append(previous[route[-1]])
            route.reverse()
            compact = [route[0]]
            for q in route[1:]:
                if len(compact) > 1 and (
                    (compact[-2][0] == compact[-1][0] == q[0])
                    or (compact[-2][1] == compact[-1][1] == q[1])
                ):
                    compact[-1] = q
                else:
                    compact.append(q)
            if not motion_clear(compact, clear, obs, width, depth):
                raise ValueError("INTERNAL_MOTION_WITNESS_RECHECK_FAILED")
            return compact, nodes
        i, j = xi[p[0]], yi[p[1]]
        for ni, nj in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
            if not (0 <= ni < len(xx) and 0 <= nj < len(yy)):
                continue
            q = (xx[ni], yy[nj])
            if q not in checked:
                checked[q] = free(q)
            if not checked[q] or not motion_clear((p, q), clear, obs, width, depth):
                continue
            value = cost + abs(p[0] - q[0]) + abs(p[1] - q[1])
            if value < distance.get(q, 10**18):
                distance[q] = value
                previous[q] = p
                heapq.heappush(queue, (value + abs(q[0] - end[0]) + abs(q[1] - end[1]), value, q))
    return [], nodes


def axis_transform(box: Sequence[int], origin: Sequence[int], turn: int) -> Box:
    """Orient a complete internal arrangement without changing its room."""
    x, y, r, t = box
    a, b, c, d = origin
    if turn == 0:
        return a + x, b + y, a + r, b + t
    if turn == 1:
        return c - t, b + x, c - y, b + r
    if turn == 2:
        return c - r, d - t, c - x, d - y
    if turn == 3:
        return a + y, d - r, a + t, d - x
    raise ValueError("QUARTER_TURN_REQUIRED")


def point_transform(point: Point, origin: Sequence[int], turn: int) -> Point:
    x, y = point
    a, b, c, d = origin
    return ((a + x, b + y), (c - y, b + x), (c - x, d - y), (a + y, d - x))[turn]


def route_record(path: Sequence[Point], width: int, depth: int, **identity: Any) -> dict[str, Any]:
    return {
        **identity,
        "centerline_mm": [list(p) for p in path],
        "envelope_bbox_mm": [list(p) for p in swept_boxes(path, width, depth)] if path else [],
        "moving_envelope_mm": [width, depth],
        "length_mm": sum(
            abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(path, path[1:], strict=False)
        ),
        "geometry_status": "SWEPT_GEOMETRY_VERIFIED" if path else "BOUNDED_PATH_NOT_FOUND",
        "vehicle_kinematics": "INPUT_REQUIRED",
    }
