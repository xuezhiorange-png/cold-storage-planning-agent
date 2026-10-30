"""Exact overlay diagnostics. No placement, route search or engineering approval."""

from collections.abc import Sequence
from typing import Any

from cold_storage.modules.layout.domain.functional_room_fit import Rect, area, covered, intersection
from cold_storage.modules.layout.domain.functional_sizing_advisory import area_text
from cold_storage.modules.layout.domain.site_geometry import PolygonMM, polygon_contains_polygon

IDENTITY = "functional-room-site-impact-review@1.0.0"


def polygon_of(box: Rect) -> PolygonMM:
    x, y, r, t = box
    return ((x, y), (r, y), (r, t), (x, t))


def positive_intersection(first: Rect, second: Rect) -> Rect | None:
    if intersection(first, second) == 0:
        return None
    return (
        max(first[0], second[0]),
        max(first[1], second[1]),
        min(first[2], second[2]),
        min(first[3], second[3]),
    )


def rectangular_union_area(boxes: Sequence[Rect]) -> int:
    """Compress actual endpoints; use the existing exact union-coverage predicate."""
    xs = sorted({x for b in boxes for x in (b[0], b[2])})
    ys = sorted({y for b in boxes for y in (b[1], b[3])})
    return sum(
        area((x, y, r, t))
        for x, r in zip(xs, xs[1:], strict=False)
        for y, t in zip(ys, ys[1:], strict=False)
        if covered((x, y, r, t), boxes)
    )


def orthogonal_tiles(polygon: PolygonMM) -> list[Rect]:
    """Exact orthogonal polygon decomposition, not sampled raster geometry."""
    edges = list(zip(polygon, (*polygon[1:], polygon[0]), strict=True))
    if any(a[0] != b[0] and a[1] != b[1] for a, b in edges):
        raise ValueError("ORTHOGONAL_AREA_EVIDENCE_REQUIRED")
    xs, ys = sorted({p[0] for p in polygon}), sorted({p[1] for p in polygon})
    return [
        (x, y, r, t)
        for x, r in zip(xs, xs[1:], strict=False)
        for y, t in zip(ys, ys[1:], strict=False)
        if polygon_contains_polygon(polygon, polygon_of((x, y, r, t)))
    ]


def expansion_bands(original: Rect, expanded: Rect) -> list[dict[str, Any]]:
    if original[:2] != expanded[:2] or expanded[2] < original[2] or expanded[3] < original[3]:
        raise ValueError("WEST_SOUTH_ANCHORED_EXPANSION_REQUIRED")
    boxes = [
        ("NORTH", (original[0], original[3], original[2], expanded[3])),
        ("EAST", (original[2], original[1], expanded[2], expanded[3])),
    ]
    return [
        dict(side=side, bounds_mm=list(b), area_mm2=area(b), area_m2=area_text(area(b)))
        for side, b in boxes
        if b[0] < b[2] and b[1] < b[3]
    ]


def contact_report(
    bands: Sequence[Rect], objects: Sequence[dict[str, Any]] | None
) -> dict[str, Any]:
    if objects is None:
        return dict(status="NOT_EVALUATED", reason="ARCHIVED_GEOMETRY_MISSING", contacts=[])
    contacts = []
    all_intersections = []
    for obj in objects:
        pieces = sorted(
            {
                overlap
                for band in bands
                for box in obj["boxes_mm"]
                if (overlap := positive_intersection(band, tuple(box))) is not None
            }
        )
        if pieces:
            all_intersections.extend(pieces)
            contacts.append(
                dict(
                    object_id=obj["id"],
                    reference=obj["reference"],
                    object_hash=obj["object_hash"],
                    object_bounds_mm=obj["boxes_mm"],
                    intersection_rectangles_mm=[list(p) for p in pieces],
                    intersection_area_mm2=rectangular_union_area(pieces),
                    intersection_area_m2=area_text(rectangular_union_area(pieces)),
                )
            )
    return dict(
        status="POSITIVE_AREA_INTERSECTION_DETECTED"
        if contacts
        else "NO_POSITIVE_INTERSECTION_IN_CHECKED_INPUTS",
        checked_object_count=len(objects),
        contacts=contacts,
        unique_intersection_area_mm2=rectangular_union_area(all_intersections),
        unique_intersection_area_m2=area_text(rectangular_union_area(all_intersections)),
        boundary_contact_is_positive_intersection=False,
    )


def polygon_metrics(polygon: PolygonMM) -> dict[str, Any]:
    pairs = list(zip(polygon, (*polygon[1:], polygon[0]), strict=True))
    twice = sum(a[0] * b[1] - b[0] * a[1] for a, b in pairs)
    if twice % 2:
        raise ValueError("INTEGER_AREA_EVIDENCE_REQUIRED")
    sign = 1 if twice > 0 else -1
    return dict(
        area_mm2=abs(twice) // 2,
        area_m2=area_text(abs(twice) // 2),
        perimeter_mm=sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in pairs),
        turn_count=len(polygon),
        concave_corner_count=sum(
            sign
            * (
                (p[0] - polygon[i - 1][0]) * (polygon[(i + 1) % len(polygon)][1] - p[1])
                - (p[1] - polygon[i - 1][1]) * (polygon[(i + 1) % len(polygon)][0] - p[0])
            )
            < 0
            for i, p in enumerate(polygon)
        ),
        polygon_mm=[list(p) for p in polygon],
        role="DIAGNOSTIC_SUPERPOSITION_UNION_NOT_APPROVED_FOOTPRINT",
    )
