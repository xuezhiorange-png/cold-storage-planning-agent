"""Exact finite event search for a fixed axis-aligned tail rectangle.

The event search is complete only for integer-mm, axis-aligned rectangles and
orthogonal site, obstacle, and fixed-zone polygons.  In that case every
predicate transition in candidate-origin space occurs when one rectangle edge
aligns with a polygon edge, at ``edge`` or ``edge - rectangle_extent``.
Legality is constant in each open cell of that rectilinear arrangement.  The
event coordinates and their adjacent integer-mm lattice points therefore
provide a representative for every non-empty integer-lattice cell.  The
existing exact polygon predicates decide each representative; no bounding-box
approximation is used.

For non-orthogonal geometry, or a dimension authority whose complete allowed
rectangle set is not supplied, the result is explicitly UNAVAILABLE and must
not be used to prune a skeleton.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Final

from cold_storage.modules.layout.domain.site_geometry import (
    MILLIMETRES_PER_METRE,
    PlacedRectangleV1,
    PolygonMM,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
)

IDENTITY: Final = "tail-zone-slot-feasibility@1.0.0"
EXACT_ORTHOGONAL_EVENT_ENUMERATION: Final = "EXACT_ORTHOGONAL_EVENT_ENUMERATION"
EVENT_COMPLETENESS_UNAVAILABLE: Final = "EXACT_EVENT_COMPLETENESS_UNAVAILABLE"
SITE_ANCHOR_IDENTITY: Final = "tail-zone-site-anchor-enumeration@1.0.0"


@lru_cache(maxsize=131_072)
def _cached_rectangle_inside_polygon(
    bounds_mm: tuple[int, int, int, int], polygon: PolygonMM
) -> bool:
    """Memoize the existing exact predicate for repeated event rectangles.

    Slot proofs for different skeletons often revisit the same site/obstacle
    event origin.  The cache key is the complete axis-aligned rectangle and
    normalized polygon; the authoritative predicate still decides every
    cache miss.  This changes neither the event set nor proof accounting.
    """
    left, bottom, right, top = bounds_mm
    rectangle = PlacedRectangleV1(
        "tail-slot-cache",
        Decimal(left) / MILLIMETRES_PER_METRE,
        Decimal(bottom) / MILLIMETRES_PER_METRE,
        Decimal(right - left) / MILLIMETRES_PER_METRE,
        Decimal(top - bottom) / MILLIMETRES_PER_METRE,
    )
    return rectangle_inside_polygon(rectangle, polygon)


@lru_cache(maxsize=131_072)
def _cached_rectangle_intersects_obstacle(
    bounds_mm: tuple[int, int, int, int], obstacle: PolygonMM
) -> bool:
    """Memoize the existing exact closed-obstacle predicate by geometry."""
    left, bottom, right, top = bounds_mm
    rectangle = PlacedRectangleV1(
        "tail-slot-cache",
        Decimal(left) / MILLIMETRES_PER_METRE,
        Decimal(bottom) / MILLIMETRES_PER_METRE,
        Decimal(right - left) / MILLIMETRES_PER_METRE,
        Decimal(top - bottom) / MILLIMETRES_PER_METRE,
    )
    return rectangle_intersects_closed_obstacle(rectangle, obstacle)


@dataclass(frozen=True)
class TailZoneSlotFeasibilityV1:
    """Evidence for whether an authoritative fixed-size rectangle has a slot."""

    zone_code: str
    orientation_count: int
    event_origin_count: int
    evaluated_placement_count: int
    legal_slot_exists: bool | None
    first_witness_rectangle: PlacedRectangleV1 | None
    site_rejection_count: int
    no_build_rejection_count: int
    main_skeleton_overlap_rejection_count: int
    proof_mode: str

    def to_dict(self) -> dict[str, object]:
        witness = self.first_witness_rectangle
        return {
            "identity": IDENTITY,
            "zone_code": self.zone_code,
            "orientation_count": self.orientation_count,
            "event_origin_count": self.event_origin_count,
            "evaluated_placement_count": self.evaluated_placement_count,
            "legal_slot_exists": self.legal_slot_exists,
            "first_witness_rectangle": witness.to_dict() if witness is not None else None,
            "site_rejection_count": self.site_rejection_count,
            "no_build_rejection_count": self.no_build_rejection_count,
            "main_skeleton_overlap_rejection_count": self.main_skeleton_overlap_rejection_count,
            "proof_mode": self.proof_mode,
        }


@dataclass(frozen=True)
class TailZoneSiteAnchorEnumerationV1:
    """All exact legal site-only anchors for one authoritative zone."""

    zone_code: str
    orientation_count: int
    event_origin_count: int
    evaluated_placement_count: int
    legal_anchors: tuple[PlacedRectangleV1, ...]
    site_rejection_count: int
    no_build_rejection_count: int
    proof_mode: str
    main_skeleton_overlap_rejection_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": SITE_ANCHOR_IDENTITY,
            "zone_code": self.zone_code,
            "orientation_count": self.orientation_count,
            "event_origin_count": self.event_origin_count,
            "evaluated_placement_count": self.evaluated_placement_count,
            "legal_anchor_count": len(self.legal_anchors),
            "legal_anchors": [row.to_dict() for row in self.legal_anchors],
            "site_rejection_count": self.site_rejection_count,
            "no_build_rejection_count": self.no_build_rejection_count,
            "main_skeleton_overlap_rejection_count": self.main_skeleton_overlap_rejection_count,
            "proof_mode": self.proof_mode,
        }


def _is_orthogonal(polygon: PolygonMM) -> bool:
    return all(
        first[0] == second[0] or first[1] == second[1]
        for first, second in zip(polygon, polygon[1:] + polygon[:1], strict=True)
    )


def _polygon_bounds(polygon: PolygonMM) -> tuple[int, int, int, int]:
    return (
        min(point[0] for point in polygon),
        min(point[1] for point in polygon),
        max(point[0] for point in polygon),
        max(point[1] for point in polygon),
    )


def _closed_bounds_may_intersect(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> bool:
    """Return false only when two closed bounds are provably disjoint."""
    return not (
        first[2] < second[0] or second[2] < first[0] or first[3] < second[1] or second[3] < first[1]
    )


def _axis_events(
    polygons: Sequence[PolygonMM],
    *,
    axis_index: int,
    extent_mm: int,
    minimum_mm: int,
    maximum_origin_mm: int,
) -> tuple[int, ...]:
    exact_events = {
        point[axis_index] - offset
        for polygon in polygons
        for point in polygon
        for offset in (0, extent_mm)
    }
    # Include the nearest integer-mm lattice point on both sides of each event.
    # This captures open cells adjacent to closed no-build obstacles exactly.
    candidates = {
        event + delta
        for event in exact_events
        for delta in (-1, 0, 1)
        if minimum_mm <= event + delta <= maximum_origin_mm
    }
    candidates.update(value for value in exact_events if minimum_mm <= value <= maximum_origin_mm)
    return tuple(sorted(candidates))


def evaluate_tail_zone_slot_feasibility_v1(
    *,
    zone_code: str,
    dimension_variants: Sequence[tuple[int, int, int]],
    dimension_authority_complete: bool,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    fixed_main_process_rectangles: Sequence[PlacedRectangleV1],
) -> TailZoneSlotFeasibilityV1:
    """Enumerate a finite exact event set, or decline to make a hard finding.

    ``dimension_variants`` contain authoritative width/depth in integer mm and
    their allowed 0/90-degree rotations.  A negative result is conclusive only
    when the complete dimension authority and every relevant polygon are
    orthogonal.
    """
    polygons = (boundary, *obstacles, *(row.polygon_mm for row in fixed_main_process_rectangles))
    if (
        not dimension_authority_complete
        or not dimension_variants
        or any(
            width <= 0 or depth <= 0 or rotation not in (0, 90)
            for width, depth, rotation in dimension_variants
        )
        or any(not _is_orthogonal(polygon) for polygon in polygons)
    ):
        return TailZoneSlotFeasibilityV1(
            zone_code=zone_code,
            orientation_count=0,
            event_origin_count=0,
            evaluated_placement_count=0,
            legal_slot_exists=None,
            first_witness_rectangle=None,
            site_rejection_count=0,
            no_build_rejection_count=0,
            main_skeleton_overlap_rejection_count=0,
            proof_mode=EVENT_COMPLETENESS_UNAVAILABLE,
        )

    min_x = min(point[0] for point in boundary)
    min_y = min(point[1] for point in boundary)
    max_x = max(point[0] for point in boundary)
    max_y = max(point[1] for point in boundary)
    boundary_bounds = (min_x, min_y, max_x, max_y)
    obstacle_bounds = tuple(_polygon_bounds(obstacle) for obstacle in obstacles)
    variants = tuple(
        sorted(
            {(width, depth, rotation) for width, depth, rotation in dimension_variants},
            key=lambda row: (row[2], row[0], row[1]),
        )
    )
    origins_by_variant: list[tuple[tuple[int, int, int], tuple[int, ...], tuple[int, ...]]] = []
    all_origins: set[tuple[int, int]] = set()
    for width_mm, depth_mm, rotation in variants:
        bounds_width, bounds_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        xs = _axis_events(
            polygons,
            axis_index=0,
            extent_mm=bounds_width,
            minimum_mm=min_x,
            maximum_origin_mm=max_x - bounds_width,
        )
        ys = _axis_events(
            polygons,
            axis_index=1,
            extent_mm=bounds_depth,
            minimum_mm=min_y,
            maximum_origin_mm=max_y - bounds_depth,
        )
        origins_by_variant.append(((width_mm, depth_mm, rotation), xs, ys))
        all_origins.update((x, y) for x in xs for y in ys)

    site_rejections = 0
    no_build_rejections = 0
    overlap_rejections = 0
    evaluated = 0
    for (width_mm, depth_mm, rotation), xs, ys in origins_by_variant:
        for x_mm in xs:
            for y_mm in ys:
                evaluated += 1
                rectangle = PlacedRectangleV1(
                    zone_code,
                    Decimal(x_mm) / MILLIMETRES_PER_METRE,
                    Decimal(y_mm) / MILLIMETRES_PER_METRE,
                    Decimal(width_mm) / MILLIMETRES_PER_METRE,
                    Decimal(depth_mm) / MILLIMETRES_PER_METRE,
                    rotation,
                )
                bounds_mm = rectangle.bounds_mm
                # This coarse check only rejects rectangles provably outside
                # the boundary bounding box.  Every remaining placement is
                # still decided by the authoritative exact polygon predicate.
                if (
                    bounds_mm[0] < boundary_bounds[0]
                    or bounds_mm[1] < boundary_bounds[1]
                    or bounds_mm[2] > boundary_bounds[2]
                    or bounds_mm[3] > boundary_bounds[3]
                    or not _cached_rectangle_inside_polygon(bounds_mm, boundary)
                ):
                    site_rejections += 1
                    continue
                if any(
                    _closed_bounds_may_intersect(bounds_mm, obstacle_bounds[index])
                    and _cached_rectangle_intersects_obstacle(bounds_mm, obstacle)
                    for index, obstacle in enumerate(obstacles)
                ):
                    no_build_rejections += 1
                    continue
                if any(
                    rectangles_overlap(rectangle, fixed) for fixed in fixed_main_process_rectangles
                ):
                    overlap_rejections += 1
                    continue
                return TailZoneSlotFeasibilityV1(
                    zone_code=zone_code,
                    orientation_count=len(variants),
                    event_origin_count=len(all_origins),
                    evaluated_placement_count=evaluated,
                    legal_slot_exists=True,
                    first_witness_rectangle=rectangle,
                    site_rejection_count=site_rejections,
                    no_build_rejection_count=no_build_rejections,
                    main_skeleton_overlap_rejection_count=overlap_rejections,
                    proof_mode=EXACT_ORTHOGONAL_EVENT_ENUMERATION,
                )

    return TailZoneSlotFeasibilityV1(
        zone_code=zone_code,
        orientation_count=len(variants),
        event_origin_count=len(all_origins),
        evaluated_placement_count=evaluated,
        legal_slot_exists=False,
        first_witness_rectangle=None,
        site_rejection_count=site_rejections,
        no_build_rejection_count=no_build_rejections,
        main_skeleton_overlap_rejection_count=overlap_rejections,
        proof_mode=EXACT_ORTHOGONAL_EVENT_ENUMERATION,
    )


def enumerate_tail_zone_site_anchors_v1(
    *,
    zone_code: str,
    dimension_variants: Sequence[tuple[int, int, int]],
    dimension_authority_complete: bool,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    fixed_main_process_rectangles: Sequence[PlacedRectangleV1] = (),
) -> TailZoneSiteAnchorEnumerationV1:
    """Enumerate every legal exact event anchor, optionally clear of fixed zones.

    This is a construction primitive, not a replacement for the fixed-skeleton
    feasibility proof above. It deliberately shares the same orthogonality,
    integer-mm event generation, site containment, and closed-obstacle
    predicates so a returned anchor is an actual legal rectangle.
    """
    polygons = (
        boundary,
        *obstacles,
        *(row.polygon_mm for row in fixed_main_process_rectangles),
    )
    if (
        not dimension_authority_complete
        or not dimension_variants
        or any(
            width <= 0 or depth <= 0 or rotation not in (0, 90)
            for width, depth, rotation in dimension_variants
        )
        or any(not _is_orthogonal(polygon) for polygon in polygons)
    ):
        return TailZoneSiteAnchorEnumerationV1(
            zone_code=zone_code,
            orientation_count=0,
            event_origin_count=0,
            evaluated_placement_count=0,
            legal_anchors=(),
            site_rejection_count=0,
            no_build_rejection_count=0,
            proof_mode=EVENT_COMPLETENESS_UNAVAILABLE,
            main_skeleton_overlap_rejection_count=0,
        )

    min_x = min(point[0] for point in boundary)
    min_y = min(point[1] for point in boundary)
    max_x = max(point[0] for point in boundary)
    max_y = max(point[1] for point in boundary)
    variants = tuple(
        sorted(
            {(width, depth, rotation) for width, depth, rotation in dimension_variants},
            key=lambda row: (row[2], row[0], row[1]),
        )
    )
    origins_by_variant: list[tuple[tuple[int, int, int], tuple[int, ...], tuple[int, ...]]] = []
    all_origins: set[tuple[int, int]] = set()
    for width_mm, depth_mm, rotation in variants:
        bounds_width, bounds_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        xs = _axis_events(
            polygons,
            axis_index=0,
            extent_mm=bounds_width,
            minimum_mm=min_x,
            maximum_origin_mm=max_x - bounds_width,
        )
        ys = _axis_events(
            polygons,
            axis_index=1,
            extent_mm=bounds_depth,
            minimum_mm=min_y,
            maximum_origin_mm=max_y - bounds_depth,
        )
        origins_by_variant.append(((width_mm, depth_mm, rotation), xs, ys))
        all_origins.update((x, y) for x in xs for y in ys)

    site_rejections = 0
    no_build_rejections = 0
    overlap_rejections = 0
    evaluated = 0
    anchors: dict[tuple[tuple[int, int, int, int], int], PlacedRectangleV1] = {}
    for (width_mm, depth_mm, rotation), xs, ys in origins_by_variant:
        for x_mm in xs:
            for y_mm in ys:
                evaluated += 1
                rectangle = PlacedRectangleV1(
                    zone_code,
                    Decimal(x_mm) / MILLIMETRES_PER_METRE,
                    Decimal(y_mm) / MILLIMETRES_PER_METRE,
                    Decimal(width_mm) / MILLIMETRES_PER_METRE,
                    Decimal(depth_mm) / MILLIMETRES_PER_METRE,
                    rotation,
                )
                if not rectangle_inside_polygon(rectangle, boundary):
                    site_rejections += 1
                    continue
                if any(
                    rectangle_intersects_closed_obstacle(rectangle, obstacle)
                    for obstacle in obstacles
                ):
                    no_build_rejections += 1
                    continue
                if any(
                    rectangles_overlap(rectangle, fixed) for fixed in fixed_main_process_rectangles
                ):
                    overlap_rejections += 1
                    continue
                anchors[(rectangle.bounds_mm, rotation)] = rectangle

    ordered_anchors = tuple(
        anchors[key] for key in sorted(anchors, key=lambda row: (row[1], row[0]))
    )
    return TailZoneSiteAnchorEnumerationV1(
        zone_code=zone_code,
        orientation_count=len(variants),
        event_origin_count=len(all_origins),
        evaluated_placement_count=evaluated,
        legal_anchors=ordered_anchors,
        site_rejection_count=site_rejections,
        no_build_rejection_count=no_build_rejections,
        proof_mode=EXACT_ORTHOGONAL_EVENT_ENUMERATION,
        main_skeleton_overlap_rejection_count=overlap_rejections,
    )
