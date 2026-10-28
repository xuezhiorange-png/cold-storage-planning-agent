"""R5 deterministic door volumes and continuous orthogonal movement checks.

No Native solver, layout generation, Authority change, or engineering approval.
Units: integer mm. Touching rectangular boundaries is allowed; swept door contact
is conservatively a conflict. Door thickness uses an enclosing planar dilation.
"""

import heapq
import math
from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import covered, rectangle

VERSION = "changing-room-motion-r11-r5@1.0.0"


def overlap3(a: list[int], b: list[int]) -> bool:
    return all(max(a[i], b[i]) < min(a[i + 3], b[i + 3]) for i in range(3))


def prism(bounds: list[int], low: int, high: int) -> list[int]:
    x, y, r, t = rectangle(bounds)
    if type(low) is not int or type(high) is not int or not 0 <= low < high:
        raise ValueError("EXPLICIT_VERTICAL_INTERVAL_REQUIRED")
    return [x, y, low, r, t, high]


def door_sector(
    column: dict[str, Any],
    cell: dict[str, Any],
    *,
    kind: str,
    frame_mm: int,
    thickness_mm: int,
    hinge: str,
) -> dict[str, Any]:
    if kind not in {"OUTWARD_HINGED_90", "NO_PLAN_INTRUSION"} or hinge not in {"LEFT", "RIGHT"}:
        raise ValueError("EXPLICIT_SUPPORTED_DOOR_MECHANISM_REQUIRED")
    x, y, r, t = column["bounds_mm"]
    radius = r - x - 2 * frame_mm
    if radius <= 0 or thickness_mm <= 0 or frame_mm < 0:
        raise ValueError("POSITIVE_LEAF_AND_EXPLICIT_FRAME_REQUIRED")
    hx = x + frame_mm if hinge == "LEFT" else r - frame_mm
    hy = t if column["front"] == "N" else y
    ux = 1 if hinge == "LEFT" else -1
    vy = 1 if column["front"] == "N" else -1
    z = cell["elevation_bounds_mm"]
    # Drawing only. Collision uses the analytic whole quarter-disk, not samples.
    arc = [
        [
            round(hx + ux * radius * math.cos(i * math.pi / 40)),
            round(hy + vy * radius * math.sin(i * math.pi / 40)),
        ]
        for i in range(21)
    ]
    return dict(
        id=cell["independent_door_id"],
        compartment_id=cell["id"],
        column_id=column["id"],
        unit_id=column["unit_id"],
        kind=kind,
        hinge_mm=[hx, hy],
        direction=[ux, vy],
        radius_mm=radius,
        thickness_mm=thickness_mm,
        z_interval_mm=[z[1], z[3]],
        arc_mm=arc,
        open_leaf_mm=[[hx, hy], [hx, hy + vy * radius]],
        source_label="HYPOTHETICAL_NOT_APPROVED",
        angle_degrees=90,
        body_collision_model="ANALYTIC_QUARTER_DISK_WITH_CONSERVATIVE_THICKNESS",
        actual_hinge_door_hardware="INPUT_REQUIRED",
    )


def door_hits_box(door: dict[str, Any], box: list[int], *, projection: bool = False) -> bool:
    if door["kind"] == "NO_PLAN_INTRUSION":
        return False
    z0, z1 = door["z_interval_mm"]
    if not projection and (box[5] <= z0 or box[2] >= z1):
        return False
    hx, hy = door["hinge_mm"]
    ux, vy = door["direction"]
    pad = door["thickness_mm"]
    xx = sorted([(box[0] - hx) * ux, (box[3] - hx) * ux])
    yy = sorted([(box[1] - hy) * vy, (box[4] - hy) * vy])
    if xx[1] + pad < 0 or yy[1] + pad < 0:
        return False
    nearx = max(0, xx[0] - pad)
    neary = max(0, yy[0] - pad)
    return bool(nearx * nearx + neary * neary <= door["radius_mm"] ** 2)


def standing_person(key: str, bounds: list[int], height: int, role: str) -> dict[str, Any]:
    return dict(
        id=key, bounds_mm=bounds, volumes_mm=[prism(bounds, 0, height)], role=role, pose="STANDING"
    )


def seated_person(
    key: str, bounds: list[int], bench: dict[str, Any], seated_height: int
) -> dict[str, Any]:
    x, y, r, t = rectangle(bounds)
    b = bench["bounds_mm"]
    seat = bench["height_mm"]
    if not y <= b[3] < t or seat >= seated_height:
        raise ValueError("EXPLICIT_BENCH_SEAT_AND_LEG_SPACE_REQUIRED")
    return dict(
        id=key,
        bounds_mm=bounds,
        volumes_mm=[prism(bounds, seat, seated_height), prism([x, b[3], r, t], 0, seat)],
        role="BENCH_USER",
        pose="SEATED",
        bench_id=bench["id"],
        stand_up_transition="NOT_EVALUATED",
    )


def swept_segments(points: list[list[int]], width: int, depth: int, height: int) -> list[list[int]]:
    if len(points) < 2 or min(width, depth, height) <= 0:
        raise ValueError("MOVEMENT_PATH_AND_BODY_DIMENSIONS_REQUIRED")
    out = []
    for a, b in zip(points, points[1:], strict=False):
        if a == b:
            continue
        if a[0] != b[0] and a[1] != b[1]:
            raise ValueError("ORTHOGONAL_CONTINUOUS_PATH_REQUIRED")
        out.append(
            [
                min(a[0], b[0]) - width // 2,
                min(a[1], b[1]) - depth // 2,
                0,
                max(a[0], b[0]) + width - width // 2,
                max(a[1], b[1]) + depth - depth // 2,
                height,
            ]
        )
    return out


def network_path(
    start: list[int], end: list[int], lines: list[list[list[int]]]
) -> list[list[int]] | None:
    """Finite exact graph on supplied orthogonal aisle centerlines (not a layout solve)."""
    a, b = tuple(start), tuple(end)
    points = {a, b, *[tuple(p) for line in lines for p in line]}
    for p, q in lines:
        if p[0] != q[0] and p[1] != q[1]:
            raise ValueError("ORTHOGONAL_NETWORK_REQUIRED")
    for p, q in lines:
        for r, s in lines:
            if (
                p[0] == q[0]
                and r[1] == s[1]
                and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
                and min(r[0], s[0]) <= p[0] <= max(r[0], s[0])
            ):
                points.add((p[0], r[1]))
    graph: dict[tuple[int, ...], dict[tuple[int, ...], int]] = {p: {} for p in points}
    for p, q in lines:
        on = sorted(
            v
            for v in points
            if min(p[0], q[0]) <= v[0] <= max(p[0], q[0])
            and min(p[1], q[1]) <= v[1] <= max(p[1], q[1])
        )
        for v, w in zip(on, on[1:], strict=False):
            cost = abs(v[0] - w[0]) + abs(v[1] - w[1])
            graph[v][w] = cost
            graph[w][v] = cost
    heap = [(0, a)]
    dist = {a: 0}
    prev: dict[tuple[int, ...], tuple[int, ...]] = {}
    while heap:
        cost, node = heapq.heappop(heap)
        if cost != dist[node]:
            continue
        if node == b:
            path = [b]
            while path[-1] != a:
                path.append(prev[path[-1]])
            return [list(p) for p in reversed(path)]
        for nxt, weight in sorted(graph[node].items()):
            value = cost + weight
            if value < dist.get(nxt, 10**18):
                dist[nxt] = value
                prev[nxt] = node
                heapq.heappush(heap, (value, nxt))
    return None


def verify_movement(
    points: list[list[int]],
    person: dict[str, Any],
    target: dict[str, Any],
    others: list[dict[str, Any]],
    bodies: list[dict[str, Any]],
    clear: list[int],
    width: int,
    depth: int,
    height: int,
    allowed: list[list[int]],
    open_doors: list[dict[str, Any]],
    clear_height: int,
) -> dict[str, Any]:
    """All other 52 users remain at their actual coordinates while one user moves."""
    errors: list[dict[str, Any]] = []
    if len(points) < 2:
        raise ValueError("MOVEMENT_PATH_REQUIRED")
    if (
        len(others) != 52
        or len({o["id"] for o in others}) != 52
        or person["id"] in {o["id"] for o in others}
    ):
        errors.append(dict(code="53_DISTINCT_USERS_MUST_BE_PRESERVED"))
    if person["id"] != target["id"]:
        errors.append(dict(code="MOVEMENT_PERSON_IDENTITY_CHANGED"))
    for obj in (person, target):
        b = obj["bounds_mm"]
        if (
            b[2] - b[0] != width
            or b[3] - b[1] != depth
            or max(v[5] for v in obj["volumes_mm"]) != height
        ):
            errors.append(dict(code="MOVEMENT_BODY_DIMENSIONS_CHANGED"))
    for obj, p in ((person, points[0]), (target, points[-1])):
        box = obj["bounds_mm"]
        if p != [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]:
            errors.append(dict(code="PATH_ENDPOINT_NOT_AT_PERSON", component=obj["id"]))
    if person["pose"] != "STANDING" or target["pose"] != "STANDING":
        return dict(
            status="NOT_EVALUATED",
            reason="SEATED_STAND_UP_POSE_TRANSITION_REQUIRED",
            points_mm=points,
        )
    swept = swept_segments(points, width, depth, height)
    for i, box in enumerate(swept):
        if box[2] < 0 or box[5] > clear_height:
            errors.append(dict(code="MOVEMENT_EXCEEDS_CLEAR_HEIGHT", segment=i))
        foot = (box[0], box[1], box[3], box[4])
        if not covered(foot, [rectangle(clear)]):
            errors.append(dict(code="MOVEMENT_OUTSIDE_FINISHED_ROOM", segment=i))
        if not covered(foot, [rectangle(r) for r in allowed]):
            errors.append(
                dict(code="MOVEMENT_OUTSIDE_RESERVED_AISLE_OR_ENDPOINT_APPROACH", segment=i)
            )
        for obj in [*others, *bodies]:
            if any(overlap3(box, v) for v in obj["volumes_mm"]):
                errors.append(
                    dict(code="CONTINUOUS_BODY_COLLISION", segment=i, component=obj["id"])
                )
        for door in open_doors:
            if door_hits_box(door, box):
                errors.append(
                    dict(code="MOVEMENT_OPEN_DOOR_COLLISION", segment=i, component=door["id"])
                )
    return dict(
        status="CONTINUOUS_PATH_VERIFIED_UNDER_HYPOTHESES"
        if not errors
        else "CONFIGURATION_NOT_FIT",
        conflicts=errors,
        points_mm=points,
        swept_volumes_mm=swept,
        body_dimensions_mm=[width, depth, height],
        other_users=len(others),
        length_mm=sum(
            abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(points, points[1:], strict=False)
        ),
        timing="NOT_EVALUATED",
        policy="ONE_PERSON_MOVES_OTHERS_HOLD_DOORS_CLOSED",
        source_label="HYPOTHETICAL_NOT_APPROVED",
    )
