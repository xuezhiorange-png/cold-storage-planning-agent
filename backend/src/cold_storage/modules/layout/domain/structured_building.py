"""Versioned envelope/grid/band plans for structured layout construction.

The objects in this module describe candidate-search geometry only.  Zone
dimensions continue to come from the bound P1 authorities and all candidate
rectangles continue to be checked by the existing exact P2C/P2D predicates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from math import isqrt
from typing import Final

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
)
from cold_storage.modules.layout.domain.structural_composition import (
    FINISHED_SIDE_GROUP,
    FUNCTIONAL_GROUPS,
    MAIN_PROCESS_ZONE_CODES,
    PERSONNEL_GROUP,
    PROCESSING_CORE_GROUP,
    RAW_SIDE_GROUP,
    SUPPORT_GROUP,
    functional_group_for_zone,
)

IDENTITY: Final = "structured-building-skeleton@1.0.0"
RECTANGLE: Final = "RECTANGLE"
SIMPLE_L: Final = "SIMPLE_L"
LINEAR_3_BAND: Final = "LINEAR_3_BAND"
CENTRAL_PROCESS_WITH_SIDE_BANKS: Final = "CENTRAL_PROCESS_WITH_SIDE_BANKS"
LONGITUDINAL_PROCESS_SPINE: Final = "LONGITUDINAL_PROCESS_SPINE"
SIMPLE_L_SITE_ADAPTIVE: Final = "SIMPLE_L_SITE_ADAPTIVE"

RAW_SIDE_BAND: Final = "RAW_SIDE_BAND"
PROCESS_CORE_BAND: Final = "PROCESS_CORE_BAND"
FINISHED_SIDE_BAND: Final = "FINISHED_SIDE_BAND"
SUPPORT_BAND: Final = "SUPPORT_BAND"
PERSONNEL_EDGE_BAND: Final = "PERSONNEL_EDGE_BAND"

_BAND_GROUPS: Final = {
    RAW_SIDE_BAND: RAW_SIDE_GROUP,
    PROCESS_CORE_BAND: PROCESSING_CORE_GROUP,
    FINISHED_SIDE_BAND: FINISHED_SIDE_GROUP,
    SUPPORT_BAND: SUPPORT_GROUP,
    PERSONNEL_EDGE_BAND: PERSONNEL_GROUP,
}
_LAYOUT_FAMILIES: Final = {
    LINEAR_3_BAND,
    CENTRAL_PROCESS_WITH_SIDE_BANKS,
    LONGITUDINAL_PROCESS_SPINE,
    SIMPLE_L_SITE_ADAPTIVE,
}

BoundsMM = tuple[int, int, int, int]


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _envelope_bounds(boundary: PolygonMM) -> BoundsMM:
    if len(boundary) < 3:
        raise _error("STRUCTURED_ENVELOPE_BOUNDARY_INVALID")
    return (
        min(point[0] for point in boundary),
        min(point[1] for point in boundary),
        max(point[0] for point in boundary),
        max(point[1] for point in boundary),
    )


def _axis_extent(bounds: BoundsMM, axis: str) -> int:
    return bounds[2] - bounds[0] if axis == "X" else bounds[3] - bounds[1]


def _projected_minimum_mm(authority: Mapping[str, object], axis: str) -> int:
    geometry = authority.get("geometry")
    if isinstance(geometry, Mapping):
        width = geometry.get("width_m")
        depth = geometry.get("depth_m")
        if width is not None and depth is not None:
            width_mm = int(Decimal(str(width)) * 1000)
            depth_mm = int(Decimal(str(depth)) * 1000)
            return min(width_mm, depth_mm)
    area_value = authority.get("required_area_m2")
    if area_value is None and isinstance(geometry, Mapping):
        area_value = geometry.get("required_area_m2")
    if area_value is None:
        raise _error("STRUCTURED_ZONE_DIMENSION_AUTHORITY_MISSING")
    area_mm2 = int((Decimal(str(area_value)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    side = isqrt(area_mm2)
    if side * side < area_mm2:
        side += 1
    return side


@dataclass(frozen=True)
class BuildingEnvelopeV1:
    """A search envelope with exact site/no-build geometry retained."""

    family: str
    bounds_mm: BoundsMM
    components_mm: tuple[BoundsMM, ...]
    hard_obstacles_mm: tuple[PolygonMM, ...]
    extension_reason: str | None = None

    def contains(self, rectangle: PlacedRectangleV1) -> bool:
        left, bottom, right, top = rectangle.bounds_mm
        return any(
            left >= x0 and bottom >= y0 and right <= x1 and top <= y1
            for x0, y0, x1, y1 in self.components_mm
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": "building-envelope@1.0.0",
            "family": self.family,
            "bounds_mm": list(self.bounds_mm),
            "components_mm": [list(row) for row in self.components_mm],
            "hard_obstacle_count": len(self.hard_obstacles_mm),
            "extension_reason": self.extension_reason,
        }


@dataclass(frozen=True)
class PrimaryGridV1:
    """Finite exact event axes used to seed shared room/band boundaries."""

    x_axes_mm: tuple[int, ...]
    y_axes_mm: tuple[int, ...]
    event_x_mm: tuple[int, ...] = ()
    event_y_mm: tuple[int, ...] = ()
    axis_usage: tuple[tuple[str, int, tuple[str, ...]], ...] = ()

    def aligned_edge_count(self, rectangle: PlacedRectangleV1) -> int:
        left, bottom, right, top = rectangle.bounds_mm
        return sum(value in self.x_axes_mm for value in (left, right)) + sum(
            value in self.y_axes_mm for value in (bottom, top)
        )

    def with_placements(self, placements: Mapping[str, PlacedRectangleV1]) -> PrimaryGridV1:
        usage: dict[tuple[str, int], set[str]] = {}
        for code, rectangle in sorted(placements.items()):
            left, bottom, right, top = rectangle.bounds_mm
            for axis, value, allowed in (
                ("X", left, self.x_axes_mm),
                ("X", right, self.x_axes_mm),
                ("Y", bottom, self.y_axes_mm),
                ("Y", top, self.y_axes_mm),
            ):
                if value in allowed:
                    usage.setdefault((axis, value), set()).add(code)
        rows = tuple(
            (axis, value, tuple(sorted(codes))) for (axis, value), codes in sorted(usage.items())
        )
        return PrimaryGridV1(
            self.x_axes_mm,
            self.y_axes_mm,
            self.event_x_mm,
            self.event_y_mm,
            rows,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": "primary-grid@1.0.0",
            "primary_x_axes_mm": list(self.x_axes_mm),
            "primary_y_axes_mm": list(self.y_axes_mm),
            "event_x_mm": list(self.event_x_mm),
            "event_y_mm": list(self.event_y_mm),
            "grid_axis_usage": [
                {"axis": axis, "coordinate_mm": coordinate, "zone_codes": list(zones)}
                for axis, coordinate, zones in self.axis_usage
            ],
        }


@dataclass(frozen=True)
class FunctionalBandV1:
    """A planned region and semantic membership, created before zone placement."""

    band_code: str
    group_code: str
    zone_codes: tuple[str, ...]
    bounds_mm: BoundsMM
    process_axis: str
    ordering_role: str

    def contains(self, rectangle: PlacedRectangleV1) -> bool:
        left, bottom, right, top = rectangle.bounds_mm
        x0, y0, x1, y1 = self.bounds_mm
        return left >= x0 and bottom >= y0 and right <= x1 and top <= y1

    def to_dict(self) -> dict[str, object]:
        return {
            "band_code": self.band_code,
            "group_code": self.group_code,
            "zone_codes": list(self.zone_codes),
            "bounds_mm": list(self.bounds_mm),
            "process_axis": self.process_axis,
            "ordering_role": self.ordering_role,
        }


@dataclass(frozen=True)
class BandZonePlacementV1:
    zone_code: str
    band_code: str
    rectangle_bounds_mm: BoundsMM
    aligned_primary_edge_count: int


@dataclass(frozen=True)
class StructuredBuildingSkeletonV1:
    """Envelope → grid → bands plan plus zones assigned inside those bands."""

    layout_family: str
    process_axis: str
    envelope: BuildingEnvelopeV1
    primary_grid: PrimaryGridV1
    bands: tuple[FunctionalBandV1, ...]
    zone_placements: tuple[BandZonePlacementV1, ...] = ()

    def __post_init__(self) -> None:
        if self.layout_family not in _LAYOUT_FAMILIES:
            raise _error("STRUCTURED_LAYOUT_FAMILY_INVALID", layout_family=self.layout_family)
        if self.process_axis not in {"X", "Y"}:
            raise _error("STRUCTURED_PROCESS_AXIS_INVALID")
        if {row.band_code for row in self.bands} != set(_BAND_GROUPS):
            raise _error("STRUCTURED_FUNCTIONAL_BAND_SET_INVALID")

    def band_for_zone(self, zone_code: str) -> FunctionalBandV1:
        rows = tuple(row for row in self.bands if zone_code in row.zone_codes)
        if len(rows) != 1:
            raise _error("STRUCTURED_ZONE_BAND_ASSIGNMENT_INVALID", zone_code=zone_code)
        return rows[0]

    def admits(self, zone_code: str, rectangle: PlacedRectangleV1) -> bool:
        return self.envelope.contains(rectangle) and self.band_for_zone(zone_code).contains(
            rectangle
        )

    def with_placements(
        self, placements: Mapping[str, PlacedRectangleV1]
    ) -> StructuredBuildingSkeletonV1:
        rows: list[BandZonePlacementV1] = []
        for code, rectangle in sorted(placements.items()):
            band = self.band_for_zone(code)
            if not self.admits(code, rectangle):
                raise _error("STRUCTURED_ZONE_OUTSIDE_PLANNED_BAND", zone_code=code)
            rows.append(
                BandZonePlacementV1(
                    code,
                    band.band_code,
                    rectangle.bounds_mm,
                    self.primary_grid.aligned_edge_count(rectangle),
                )
            )
        return StructuredBuildingSkeletonV1(
            self.layout_family,
            self.process_axis,
            self.envelope,
            self.primary_grid.with_placements(placements),
            self.bands,
            tuple(rows),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": IDENTITY,
            "layout_family": self.layout_family,
            "process_axis": self.process_axis,
            "envelope": self.envelope.to_dict(),
            "primary_grid": self.primary_grid.to_dict(),
            "functional_bands": [row.to_dict() for row in self.bands],
            "band_zone_placements": [
                {
                    "zone_code": row.zone_code,
                    "band_code": row.band_code,
                    "rectangle_bounds_mm": list(row.rectangle_bounds_mm),
                    "aligned_primary_edge_count": row.aligned_primary_edge_count,
                }
                for row in self.zone_placements
            ],
        }


def _simple_l_envelopes(
    boundary: PolygonMM, obstacles: Sequence[PolygonMM], bounds: BoundsMM
) -> tuple[BuildingEnvelopeV1, ...]:
    x0, y0, x1, y1 = bounds
    x_events = {x0, x1, *(point[0] for point in boundary)}
    y_events = {y0, y1, *(point[1] for point in boundary)}
    x_events.update(point[0] for polygon in obstacles for point in polygon)
    y_events.update(point[1] for polygon in obstacles for point in polygon)
    candidates: dict[tuple[BoundsMM, ...], BuildingEnvelopeV1] = {}
    for split_x in sorted(x_events):
        if not x0 < split_x < x1:
            continue
        for split_y in sorted(y_events):
            if not y0 < split_y < y1:
                continue
            component_sets = (
                ((x0, y0, split_x, y1), (split_x, y0, x1, split_y)),
                ((x0, y0, x1, split_y), (x0, split_y, split_x, y1)),
                ((split_x, y0, x1, y1), (x0, y0, split_x, split_y)),
                ((x0, split_y, x1, y1), (x0, y0, split_x, split_y)),
            )
            for components in component_sets:
                if any(a >= c or b >= d for a, b, c, d in components):
                    continue
                safe = True
                for index, component in enumerate(components):
                    cell = PlacedRectangleV1(
                        f"envelope_component_{index}",
                        Decimal(component[0]) / 1000,
                        Decimal(component[1]) / 1000,
                        Decimal(component[2] - component[0]) / 1000,
                        Decimal(component[3] - component[1]) / 1000,
                    )
                    if not rectangle_inside_polygon(cell, boundary) or any(
                        rectangle_intersects_closed_obstacle(cell, obstacle)
                        for obstacle in obstacles
                    ):
                        safe = False
                        break
                if not safe:
                    continue
                components_key = tuple(sorted(components))
                candidates[components_key] = BuildingEnvelopeV1(
                    SIMPLE_L,
                    bounds,
                    components_key,
                    tuple(obstacles),
                )
    return tuple(candidates[key] for key in sorted(candidates))


def _band_extents(
    authorities: Mapping[str, Mapping[str, object]], axis: str
) -> tuple[int, int, int]:
    projected = {
        code: _projected_minimum_mm(authorities[code], axis) for code in MAIN_PROCESS_ZONE_CODES
    }
    raw = max(projected[code] for code in FUNCTIONAL_GROUPS[RAW_SIDE_GROUP])
    core = max(projected[code] for code in FUNCTIONAL_GROUPS[PROCESSING_CORE_GROUP])
    finished = max(
        projected["secondary_precooling_room"] + projected["finished_goods_room"],
        projected["shipping_channel"],
    )
    return raw, core, finished


def _maximum_group_extents(
    authorities: Mapping[str, Mapping[str, object]], axis: str
) -> tuple[int, int, int]:
    def maximum(code: str) -> int:
        geometry = authorities[code].get("geometry")
        if isinstance(geometry, Mapping):
            width = geometry.get("width_m")
            depth = geometry.get("depth_m")
            if width is not None and depth is not None:
                value = width if axis == "X" else depth
                return int(Decimal(str(value)) * 1000)
        return _projected_minimum_mm(authorities[code], axis)

    raw = max(maximum(code) for code in FUNCTIONAL_GROUPS[RAW_SIDE_GROUP])
    core = max(maximum(code) for code in FUNCTIONAL_GROUPS[PROCESSING_CORE_GROUP])
    finished = max(maximum(code) for code in FUNCTIONAL_GROUPS[FINISHED_SIDE_GROUP])
    return raw, core, finished


def _authority_projection(authority: Mapping[str, object], axis: str) -> int:
    geometry = authority.get("geometry")
    if isinstance(geometry, Mapping):
        value = geometry.get("width_m" if axis == "X" else "depth_m")
        if value is not None:
            return int(Decimal(str(value)) * 1000)
    return _projected_minimum_mm(authority, axis)


def _band_bounds(
    layout_family: str,
    group_band: str,
    envelope: BoundsMM,
    axis: str,
    extents: tuple[int, int, int],
    cross_extents: tuple[int, int, int],
) -> BoundsMM:
    x0, y0, x1, y1 = envelope
    low = x0 if axis == "X" else y0
    high = x1 if axis == "X" else y1
    span = high - low
    raw, core, finished = extents

    if layout_family == LINEAR_3_BAND:
        if group_band == RAW_SIDE_BAND:
            lo, hi = low, min(high, low + raw + core // 2)
        elif group_band == PROCESS_CORE_BAND:
            # The core contains both sorting and coating.  Their authoritative
            # rectangles can occupy a downstream transition while remaining
            # one process band, so the band deliberately overlaps the
            # finished-side envelope rather than cutting coating off at a
            # centroid-derived midline.
            lo, hi = max(low, low + raw // 2), min(high, low + raw + core + finished)
        elif group_band == FINISHED_SIDE_BAND:
            lo, hi = max(low, low + raw + core // 2), high
        else:
            lo, hi = low, high
        if axis == "X":
            return lo, y0, hi, y1
        return x0, lo, x1, hi

    cross_axis = "Y" if axis == "X" else "X"
    cross_low, cross_high = (y0, y1) if cross_axis == "Y" else (x0, x1)
    cross_span = cross_high - cross_low
    axis_middle = low + span // 2
    if layout_family == CENTRAL_PROCESS_WITH_SIDE_BANKS:
        if group_band == PROCESS_CORE_BAND:
            core_cross = cross_extents[1]
            span = min(cross_span, core_cross + min(cross_extents[0], cross_extents[2]) // 2)
            cross_a = cross_low + max(0, (cross_span - span) // 2)
            cross_b = min(cross_high, cross_a + span)
            return (x0, cross_a, x1, cross_b) if axis == "X" else (cross_a, y0, cross_b, y1)
        if group_band == RAW_SIDE_BAND:
            axis_a, axis_b = low, min(high, axis_middle + core // 2)
            return (
                (axis_a, cross_low, axis_b, cross_high)
                if axis == "X"
                else (
                    cross_low,
                    axis_a,
                    cross_high,
                    axis_b,
                )
            )
        if group_band == FINISHED_SIDE_BAND:
            axis_a, axis_b = max(low, axis_middle - core // 2), high
            return (
                (axis_a, cross_low, axis_b, cross_high)
                if axis == "X"
                else (
                    cross_low,
                    axis_a,
                    cross_high,
                    axis_b,
                )
            )
        return x0, y0, x1, y1
    if layout_family == LONGITUDINAL_PROCESS_SPINE:
        raw_cross, core_cross, finished_cross = cross_extents
        transition_extension = min(raw_cross, finished_cross) // 2
        spine_cross_span = min(cross_span, core_cross + transition_extension)
        core_half = spine_cross_span // 2
        middle = cross_low + cross_span // 2
        cross_a = max(cross_low, middle - core_half)
        cross_b = min(cross_high, middle + core_half)
        if group_band == PROCESS_CORE_BAND:
            return (
                (low, cross_a, high, cross_b)
                if axis == "X"
                else (
                    cross_a,
                    low,
                    cross_b,
                    high,
                )
            )
        if group_band == RAW_SIDE_BAND:
            return (
                (low, cross_low, high, cross_b)
                if axis == "X"
                else (
                    cross_low,
                    low,
                    cross_b,
                    high,
                )
            )
        if group_band == FINISHED_SIDE_BAND:
            return (
                (low, cross_a, high, cross_high)
                if axis == "X"
                else (
                    cross_a,
                    low,
                    cross_high,
                    high,
                )
            )
        return x0, y0, x1, y1

    if group_band == PROCESS_CORE_BAND:
        required = min(core, cross_span)
        middle = cross_low + cross_span // 2
        cross_a = max(cross_low, middle - required // 2)
        cross_b = min(cross_high, cross_a + required)
        lo, hi = low, high
        if axis == "X":
            return lo, cross_a, hi, cross_b
        return cross_a, lo, cross_b, hi
    if group_band in {RAW_SIDE_BAND, FINISHED_SIDE_BAND}:
        # Side-bank regions meet the central core region with a half-band
        # overlap derived from the authoritative group projections.
        core_half = min(core, cross_span) // 2
        middle = cross_low + cross_span // 2
        if group_band == RAW_SIDE_BAND:
            cross_a, cross_b = cross_low, min(cross_high, middle + core_half)
        else:
            cross_a, cross_b = max(cross_low, middle - core_half), cross_high
        lo, hi = low, high
        if axis == "X":
            return lo, cross_a, hi, cross_b
        return cross_a, lo, cross_b, hi
    # Support is kept in the envelope as a subordinate branch; personnel has
    # a peripheral envelope. The exact tail/access authorities still decide.
    return x0, y0, x1, y1


def construct_structured_building_plan_v1(
    *,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    authorities: Mapping[str, Mapping[str, object]],
    process_axis: str,
    layout_family: str,
    envelope_family: str = RECTANGLE,
) -> StructuredBuildingSkeletonV1:
    """Create the envelope, event grid, then bands before any zone is placed."""
    if process_axis not in {"X", "Y"}:
        raise _error("STRUCTURED_PROCESS_AXIS_INVALID")
    if layout_family not in _LAYOUT_FAMILIES:
        raise _error("STRUCTURED_LAYOUT_FAMILY_INVALID", layout_family=layout_family)
    envelope_bounds = _envelope_bounds(boundary)
    if envelope_family == RECTANGLE:
        envelope = BuildingEnvelopeV1(
            RECTANGLE, envelope_bounds, (envelope_bounds,), tuple(obstacles)
        )
    elif envelope_family == SIMPLE_L:
        candidates = _simple_l_envelopes(boundary, obstacles, envelope_bounds)
        if not candidates:
            raise _error("SIMPLE_L_ENVELOPE_UNAVAILABLE")
        envelope = candidates[0]
    else:
        raise _error("BUILDING_ENVELOPE_FAMILY_INVALID", envelope_family=envelope_family)

    x_axes = {envelope_bounds[0], envelope_bounds[2]}
    y_axes = {envelope_bounds[1], envelope_bounds[3]}
    for point in boundary:
        x_axes.add(point[0])
        y_axes.add(point[1])
    for obstacle in obstacles:
        for x_mm, y_mm in obstacle:
            x_axes.add(x_mm)
            y_axes.add(y_mm)
    # Bands must account for the authoritative dimensions in their actual
    # axis, not the shorter side of a room.  The previous min-side projection
    # made a rotated coating room fall outside the core band even when its
    # exact geometry and process adjacency were valid.
    extents = _maximum_group_extents(authorities, process_axis)
    cross_axis = "Y" if process_axis == "X" else "X"
    cross_extents = _maximum_group_extents(authorities, cross_axis)
    # Primary axes are derived from shared room-bank dimensions. X supports a
    # two-room raw bank and the shared process-core origin; Y carries the
    # ordered raw/core/finished chain cuts. These are construction axes, not a
    # per-room free coordinate grid.
    x_low, y_low = envelope_bounds[0], envelope_bounds[1]
    raw_width = _authority_projection(authorities["raw_fruit_buffer"], "X")
    primary_width = _authority_projection(authorities["primary_precooling_room"], "X")
    sorting_width = _authority_projection(authorities["sorting_packaging_room"], "X")
    x_axes.update(
        coordinate
        for coordinate in (
            x_low + raw_width,
            x_low + raw_width + primary_width,
            x_low + raw_width + sorting_width,
        )
        if envelope_bounds[0] < coordinate < envelope_bounds[2]
    )
    raw_band_y = max(
        _authority_projection(authorities[code], "Y") for code in FUNCTIONAL_GROUPS[RAW_SIDE_GROUP]
    )
    y_extents = (
        raw_band_y,
        _authority_projection(authorities["sorting_packaging_room"], "Y"),
        _authority_projection(authorities["secondary_precooling_room"], "Y"),
        _authority_projection(authorities["finished_goods_room"], "Y"),
    )
    y_offset = 0
    for extent in y_extents:
        y_offset += extent
        coordinate = y_low + y_offset
        if envelope_bounds[1] < coordinate < envelope_bounds[3]:
            y_axes.add(coordinate)
    low = envelope_bounds[0] if process_axis == "X" else envelope_bounds[1]
    high = envelope_bounds[2] if process_axis == "X" else envelope_bounds[3]
    if layout_family == LINEAR_3_BAND:
        raw, core, finished = extents
        cuts = (low + raw, low + raw + core, low + raw + core + finished)
        for cut in cuts:
            if low < cut < high:
                (x_axes if process_axis == "X" else y_axes).add(cut)
    event_x = set(x_axes)
    event_y = set(y_axes)
    for authority in authorities.values():
        geometry = authority.get("geometry")
        if not isinstance(geometry, Mapping):
            continue
        for key in ("width_m", "depth_m"):
            value = geometry.get(key)
            if value is None:
                continue
            extent = int(Decimal(str(value)) * 1000)
            event_x.update(coordinate + sign * extent for coordinate in x_axes for sign in (-1, 1))
            event_y.update(coordinate + sign * extent for coordinate in y_axes for sign in (-1, 1))
    event_x = {value for value in event_x if envelope_bounds[0] <= value <= envelope_bounds[2]}
    event_y = {value for value in event_y if envelope_bounds[1] <= value <= envelope_bounds[3]}
    grid = PrimaryGridV1(
        tuple(sorted(x_axes)),
        tuple(sorted(y_axes)),
        tuple(sorted(event_x)),
        tuple(sorted(event_y)),
    )
    bands = tuple(
        FunctionalBandV1(
            band_code,
            group_code,
            tuple(FUNCTIONAL_GROUPS[group_code]),
            _band_bounds(
                layout_family,
                band_code,
                envelope_bounds,
                process_axis,
                extents,
                cross_extents,
            ),
            process_axis,
            ordering_role,
        )
        for band_code, group_code, ordering_role in (
            (RAW_SIDE_BAND, RAW_SIDE_GROUP, "UPSTREAM"),
            (PROCESS_CORE_BAND, PROCESSING_CORE_GROUP, "CORE"),
            (FINISHED_SIDE_BAND, FINISHED_SIDE_GROUP, "DOWNSTREAM"),
            (SUPPORT_BAND, SUPPORT_GROUP, "SUBORDINATE_BRANCH"),
            (PERSONNEL_EDGE_BAND, PERSONNEL_GROUP, "PERIPHERAL"),
        )
    )
    return StructuredBuildingSkeletonV1(layout_family, process_axis, envelope, grid, bands)


def structured_layout_family_for_topology(topology: str) -> str:
    if topology == "STRAIGHT_LINEAR_BAND":
        return LINEAR_3_BAND
    if topology == "OFFSET_LINEAR_BAND":
        return LONGITUDINAL_PROCESS_SPINE
    if topology == "CENTRAL_PROCESS_HUB":
        return CENTRAL_PROCESS_WITH_SIDE_BANKS
    raise _error("MAIN_PROCESS_TOPOLOGY_INVALID")


def zone_band_assignment(zone_code: str) -> str:
    group = functional_group_for_zone(zone_code)
    return next(band for band, band_group in _BAND_GROUPS.items() if band_group == group)


__all__ = [
    "BuildingEnvelopeV1",
    "BandZonePlacementV1",
    "CENTRAL_PROCESS_WITH_SIDE_BANKS",
    "FINISHED_SIDE_BAND",
    "FunctionalBandV1",
    "IDENTITY",
    "LINEAR_3_BAND",
    "LONGITUDINAL_PROCESS_SPINE",
    "PERSONNEL_EDGE_BAND",
    "PrimaryGridV1",
    "PROCESS_CORE_BAND",
    "RAW_SIDE_BAND",
    "RECTANGLE",
    "SIMPLE_L",
    "SIMPLE_L_SITE_ADAPTIVE",
    "SUPPORT_BAND",
    "StructuredBuildingSkeletonV1",
    "construct_structured_building_plan_v1",
    "structured_layout_family_for_topology",
    "zone_band_assignment",
]
