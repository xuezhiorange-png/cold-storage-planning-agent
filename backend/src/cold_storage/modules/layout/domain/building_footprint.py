"""Exact outline derivation for a placed layout's occupied building footprint."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    _cross,
    _on_segment,
    normalize_polygon,
    polygon_to_dict,
)


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _orthogonal_rectangles(
    polygons: tuple[PolygonMM, ...],
) -> tuple[tuple[int, int, int, int], ...]:
    rectangles: list[tuple[int, int, int, int]] = []
    for polygon in polygons:
        if len(polygon) != 4:
            raise _error("BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED")
        xs = sorted({point[0] for point in polygon})
        ys = sorted({point[1] for point in polygon})
        if len(xs) != 2 or len(ys) != 2:
            raise _error("BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED")
        rectangles.append((xs[0], ys[0], xs[1], ys[1]))
    return tuple(rectangles)


def _merge_collinear(loop: list[tuple[int, int]]) -> list[tuple[int, int]]:
    changed = True
    while changed and len(loop) >= 3:
        changed = False
        result: list[tuple[int, int]] = []
        for index, current in enumerate(loop):
            previous = loop[index - 1]
            following = loop[(index + 1) % len(loop)]
            if _cross(previous, current, following) == 0 and _on_segment(
                current, previous, following
            ):
                changed = True
                continue
            result.append(current)
        loop = result
    return loop


def derive_building_footprint(
    zone_rectangles: Mapping[str, PlacedRectangleV1],
    corridor_polygons: Sequence[PolygonMM],
) -> PolygonMM:
    """Return the exact single simple orthogonal boundary of a rectangle union."""
    rectangles = _orthogonal_rectangles(
        tuple(rectangle.polygon_mm for rectangle in zone_rectangles.values())
        + tuple(corridor_polygons)
    )
    xs = tuple(sorted({value for left, _, right, _ in rectangles for value in (left, right)}))
    ys = tuple(sorted({value for _, bottom, _, top in rectangles for value in (bottom, top)}))
    covered: set[tuple[int, int]] = set()
    for left, right in zip(xs, xs[1:], strict=False):
        for bottom, top in zip(ys, ys[1:], strict=False):
            if any(
                left >= a and right <= c and bottom >= b and top <= d for a, b, c, d in rectangles
            ):
                covered.add((left, bottom))
    if not covered:
        raise _error("BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED")

    boundary_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()

    def toggle(edge: tuple[tuple[int, int], tuple[int, int]]) -> None:
        reverse = (edge[1], edge[0])
        if reverse in boundary_edges:
            boundary_edges.remove(reverse)
        elif edge in boundary_edges:
            boundary_edges.remove(edge)
        else:
            boundary_edges.add(edge)

    for left, right in zip(xs, xs[1:], strict=False):
        for bottom, top in zip(ys, ys[1:], strict=False):
            if (left, bottom) not in covered:
                continue
            toggle(((left, bottom), (right, bottom)))
            toggle(((right, bottom), (right, top)))
            toggle(((right, top), (left, top)))
            toggle(((left, top), (left, bottom)))

    outgoing: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for start, end in boundary_edges:
        outgoing.setdefault(start, []).append(end)
    for choices in outgoing.values():
        choices.sort()
    remaining = set(boundary_edges)
    loops: list[list[tuple[int, int]]] = []
    while remaining:
        start = min(remaining)[0]
        current = start
        loop = [start]
        while True:
            choices = [
                point for point in outgoing.get(current, []) if (current, point) in remaining
            ]
            if len(choices) != 1:
                raise _error("BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED")
            next_point = choices[0]
            remaining.remove((current, next_point))
            current = next_point
            if current == start:
                break
            loop.append(current)
        loops.append(_merge_collinear(loop))
    if len(loops) != 1:
        raise _error("BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED", component_count=len(loops))
    try:
        return normalize_polygon(
            polygon_to_dict(tuple(loops[0])), error_code="INVALID_BUILDING_FOOTPRINT"
        )
    except LayoutAuthorityError:
        raise _error("BUILDING_FOOTPRINT_DERIVATION_EXHAUSTED") from None
