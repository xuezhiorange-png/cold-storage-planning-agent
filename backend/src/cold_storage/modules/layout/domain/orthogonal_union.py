"""Exact topology diagnostics for a proposed union of positive rectangles.

This is not Building Footprint authority. The existing native derivation and
typed-Site validation remain mandatory. No tolerance, raster sampling, filling
or new clearance rule is used; coordinates are compressed at actual endpoints.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from typing import Any

RectangleMM = tuple[int, int, int, int]
PointMM = tuple[int, int]


def inspect_rectangular_union(
    boxes: Sequence[RectangleMM], *, charge: Callable[[str, int], None] | None = None
) -> dict[str, Any]:
    work = 0

    def count() -> None:
        nonlocal work
        work += 1
        if charge is not None:
            charge("EXACT_UNION_PRIMITIVE", 1)

    if not boxes or any(x >= right or y >= top for x, y, right, top in boxes):
        return {"valid": False, "error": "NONPOSITIVE_OR_EMPTY_RECTANGLE_UNION"}
    xs = sorted({v for x, _, right, _ in boxes for v in (x, right)})
    ys = sorted({v for _, y, _, top in boxes for v in (y, top)})
    cells: set[tuple[int, int]] = set()
    for i, (x, right) in enumerate(zip(xs, xs[1:], strict=False)):
        for j, (y, top) in enumerate(zip(ys, ys[1:], strict=False)):
            for bx, by, br, bt in boxes:
                count()
                if bx <= x and by <= y and br >= right and bt >= top:
                    cells.add((i, j))
                    break
    remaining = set(cells)
    components = 0
    while remaining:
        components += 1
        todo = [min(remaining)]
        while todo:
            cell = todo.pop()
            count()
            if cell not in remaining:
                continue
            remaining.remove(cell)
            i, j = cell
            todo.extend(
                n for n in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)) if n in remaining
            )
    edges: set[tuple[PointMM, PointMM]] = set()
    for i, j in cells:
        x, right = xs[i], xs[i + 1]
        y, top = ys[j], ys[j + 1]
        for neighbor, a, b in (
            ((i, j - 1), (x, y), (right, y)),
            ((i + 1, j), (right, y), (right, top)),
            ((i, j + 1), (right, top), (x, top)),
            ((i - 1, j), (x, top), (x, y)),
        ):
            count()
            if neighbor not in cells:
                edges.add((a, b))
    outgoing: dict[PointMM, list[PointMM]] = defaultdict(list)
    incoming: Counter[PointMM] = Counter()
    for a, b in edges:
        outgoing[a].append(b)
        incoming[b] += 1
    singular = sorted(v for v in outgoing if len(outgoing[v]) != 1 or incoming[v] != 1)
    loops: list[dict[str, Any]] = []
    remaining_edges = set(edges)
    if not singular:
        while remaining_edges:
            a, b = min(remaining_edges)
            start = a
            points = []
            while True:
                count()
                points.append(a)
                remaining_edges.remove((a, b))
                a = b
                if a == start:
                    break
                b = outgoing[a][0]
            points = [
                p
                for i, p in enumerate(points)
                if not (
                    points[i - 1][0] == p[0] == points[(i + 1) % len(points)][0]
                    or points[i - 1][1] == p[1] == points[(i + 1) % len(points)][1]
                )
            ]
            signed = sum(
                a[0] * b[1] - a[1] * b[0]
                for a, b in zip(points, points[1:] + points[:1], strict=True)
            )
            loops.append(
                {
                    "points_mm": points,
                    "signed_area_twice_mm2": signed,
                    "kind": "HOLE" if signed < 0 else "EXTERIOR",
                }
            )
    holes = sum(loop["kind"] == "HOLE" for loop in loops)
    valid = components == 1 and len(loops) == 1 and not singular and not holes
    return {
        "valid": valid,
        "connected_component_count": components,
        "boundary_loop_count": len(loops) if not singular else None,
        "hole_count": holes if not singular else None,
        "singular_points_mm": singular,
        "boundary_loops": loops,
        "primitive_work": work,
        "error": None
        if valid
        else "SINGULAR_POINT_CONTACT"
        if singular
        else "ENCLOSED_HOLE"
        if holes
        else "MULTIPLE_COMPONENTS",
    }
