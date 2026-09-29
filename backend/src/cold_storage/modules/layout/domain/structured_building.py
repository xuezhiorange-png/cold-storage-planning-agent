"""Versioned envelope/grid/band plans for structured layout construction.

The objects in this module describe candidate-search geometry only.  Zone
dimensions continue to come from the bound P1 authorities and all candidate
rectangles continue to be checked by the existing exact P2C/P2D predicates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from functools import lru_cache
from math import isqrt
from typing import Final

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
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
BASE_LAYOUT_FAMILIES: Final = (
    LINEAR_3_BAND,
    CENTRAL_PROCESS_WITH_SIDE_BANKS,
    LONGITUDINAL_PROCESS_SPINE,
)

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


def _site_bounds(boundary: PolygonMM) -> BoundsMM:
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
    """A program-derived planned building envelope, distinct from site bounds."""

    family: str
    bounds_mm: BoundsMM
    components_mm: tuple[BoundsMM, ...]
    hard_obstacles_mm: tuple[PolygonMM, ...]
    site_bounds_mm: BoundsMM
    extension_reason: str | None = None

    def contains(self, rectangle: PlacedRectangleV1) -> bool:
        left, bottom, right, top = rectangle.bounds_mm
        if not self.components_mm or right <= left or top <= bottom:
            return False
        x_events = {left, right}
        for x0, _y0, x1, _y1 in self.components_mm:
            if left < x0 < right:
                x_events.add(x0)
            if left < x1 < right:
                x_events.add(x1)
        ordered_x = sorted(x_events)
        for slab_left, slab_right in zip(ordered_x, ordered_x[1:], strict=False):
            if slab_left == slab_right:
                continue
            covered_to = bottom
            intervals = sorted(
                (y0, y1)
                for x0, y0, x1, y1 in self.components_mm
                if x0 <= slab_left and x1 >= slab_right and y1 > bottom and y0 < top
            )
            for interval_low, interval_high in intervals:
                if interval_low > covered_to:
                    break
                covered_to = max(covered_to, interval_high)
                if covered_to >= top:
                    break
            if covered_to < top:
                return False
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": "building-envelope@1.0.0",
            "family": self.family,
            "bounds_mm": list(self.bounds_mm),
            "components_mm": [list(row) for row in self.components_mm],
            "hard_obstacle_count": len(self.hard_obstacles_mm),
            "site_bounds_mm": list(self.site_bounds_mm),
            "extension_reason": self.extension_reason,
        }


@dataclass(frozen=True)
class PrimaryGridV1:
    """Structural axes and separate local exact-event axes."""

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
        envelope_axes = set()
        if self.x_axes_mm:
            envelope_axes.update({("X", self.x_axes_mm[0]), ("X", self.x_axes_mm[-1])})
        if self.y_axes_mm:
            envelope_axes.update({("Y", self.y_axes_mm[0]), ("Y", self.y_axes_mm[-1])})
        single_use = sum(
            len(zones) == 1 and (axis, coordinate) not in envelope_axes
            for axis, coordinate, zones in self.axis_usage
        )
        return {
            "identity": "primary-grid@1.0.0",
            "primary_x_axes_mm": list(self.x_axes_mm),
            "primary_y_axes_mm": list(self.y_axes_mm),
            "event_x_mm": list(self.event_x_mm),
            "event_y_mm": list(self.event_y_mm),
            "primary_axis_usage_count": len(self.axis_usage),
            "single_use_primary_axis_count": single_use,
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
    attachment_side: str | None = None

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
            "attachment_side": self.attachment_side,
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
    support_side: str = "WEST"
    personnel_side: str = "EAST"

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
            self.support_side,
            self.personnel_side,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": IDENTITY,
            "layout_family": self.layout_family,
            "process_axis": self.process_axis,
            "support_attachment_side": self.support_side,
            "personnel_peripheral_side": self.personnel_side,
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


@lru_cache(maxsize=8)
def _simple_l_envelopes(
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    minimum_program_area_mm2: int,
    minimum_width_mm: int,
    minimum_height_mm: int,
    support_side: str,
    support_width_mm: int,
    support_length_mm: int,
    personnel_side: str,
    personnel_width_mm: int,
    personnel_length_mm: int,
    main_entrance: SegmentMM | None,
) -> tuple[BuildingEnvelopeV1, ...]:
    site = _site_bounds(boundary)
    # Event coordinates are exact site/obstacle vertices.  One lattice tick
    # outside a closed no-build edge is included because contact itself is
    # rejected by the existing obstacle predicate; this is a geometry event,
    # not a tolerance or clearance rule.
    x_events = {point[0] for point in boundary}
    y_events = {point[1] for point in boundary}
    for obstacle in obstacles:
        for x_mm, y_mm in obstacle:
            x_events.update((x_mm - 1, x_mm, x_mm + 1))
            y_events.update((y_mm - 1, y_mm, y_mm + 1))
    x_events.update((site[0], site[2]))
    y_events.update((site[1], site[3]))
    x_events = {value for value in x_events if site[0] <= value <= site[2]}
    y_events = {value for value in y_events if site[1] <= value <= site[3]}
    envelopes: dict[tuple[BoundsMM, ...], BuildingEnvelopeV1] = {}
    for x0 in sorted(x_events):
        for x1 in sorted(value for value in x_events if value > x0):
            for y0 in sorted(y_events):
                for y1 in sorted(value for value in y_events if value > y0):
                    for split_x in sorted(value for value in x_events if x0 < value < x1):
                        for split_y in sorted(value for value in y_events if y0 < value < y1):
                            component_sets = (
                                ((x0, y0, split_x, y1), (split_x, y0, x1, split_y)),
                                ((x0, y0, x1, split_y), (x0, split_y, split_x, y1)),
                                ((split_x, y0, x1, y1), (x0, y0, split_x, split_y)),
                                ((x0, split_y, x1, y1), (x0, y0, split_x, split_y)),
                            )
                            for components in component_sets:
                                if any(a >= c or b >= d for a, b, c, d in components):
                                    continue
                                bounds = (
                                    min(row[0] for row in components),
                                    min(row[1] for row in components),
                                    max(row[2] for row in components),
                                    max(row[3] for row in components),
                                )
                                if (
                                    bounds[2] - bounds[0] < minimum_width_mm
                                    or bounds[3] - bounds[1] < minimum_height_mm
                                ):
                                    continue
                                area = sum((c - a) * (d - b) for a, b, c, d in components)
                                if area < minimum_program_area_mm2:
                                    continue
                                components_key = tuple(sorted(components))
                                if not _envelope_has_edge_band_slot(
                                    components_key,
                                    bounds,
                                    support_side,
                                    support_width_mm,
                                    support_length_mm,
                                ) or not _envelope_has_edge_band_slot(
                                    components_key,
                                    bounds,
                                    personnel_side,
                                    personnel_width_mm,
                                    personnel_length_mm,
                                ):
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
                                bounds = (
                                    min(row[0] for row in components_key),
                                    min(row[1] for row in components_key),
                                    max(row[2] for row in components_key),
                                    max(row[3] for row in components_key),
                                )
                                envelopes[components_key] = BuildingEnvelopeV1(
                                    SIMPLE_L,
                                    bounds,
                                    components_key,
                                    tuple(obstacles),
                                    site,
                                )

    def envelope_order(
        envelope: BuildingEnvelopeV1,
    ) -> tuple[int, int, BoundsMM, tuple[BoundsMM, ...]]:
        x0, y0, x1, y1 = envelope.bounds_mm
        area = sum((x2 - x1_) * (y2 - y1_) for x1_, y1_, x2, y2 in envelope.components_mm)
        entrance_miss = 1
        if main_entrance is not None:
            (ax, ay), (bx, by) = main_entrance
            entrance_miss = int(
                not any(
                    (
                        ax == bx == edge_x
                        and min(y1_, y2) <= min(ay, by)
                        and max(y1_, y2) >= max(ay, by)
                    )
                    or (
                        ay == by == edge_y
                        and min(x1_, x2) <= min(ax, bx)
                        and max(x1_, x2) >= max(ax, bx)
                    )
                    for x1_, y1_, x2, y2 in envelope.components_mm
                    for edge_x in (x1_, x2)
                    for edge_y in (y1_, y2)
                )
            )
        return entrance_miss, area, envelope.bounds_mm, envelope.components_mm

    return tuple(sorted(envelopes.values(), key=envelope_order))


def _simple_l_envelopes_for_terminal(
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    minimum_program_area_mm2: int,
    minimum_width_mm: int,
    minimum_height_mm: int,
    support_side: str,
    support_width_mm: int,
    support_length_mm: int,
    personnel_side: str,
    personnel_width_mm: int,
    personnel_length_mm: int,
    main_entrance: SegmentMM | None,
    terminal: PlacedRectangleV1,
) -> tuple[BuildingEnvelopeV1, ...]:
    """Compose L envelopes from a finite census of exact-clear rectangles.

    Event cells are split at site vertices, obstacle edges and the fixed
    terminal edges.  A two-dimensional prefix table makes the clear-rectangle
    census bounded and cheap; final components are still rechecked by the
    authoritative polygon/obstacle predicates.
    """
    site = _site_bounds(boundary)
    terminal_bounds = terminal.bounds_mm
    clear_rectangles = _maximal_clear_event_rectangles(
        tuple(boundary), tuple(tuple(row) for row in obstacles), terminal_bounds
    )
    candidates: dict[tuple[BoundsMM, ...], BuildingEnvelopeV1] = {}
    for first_index, first in enumerate(clear_rectangles):
        for second in clear_rectangles[first_index + 1 :]:
            bounds = (
                min(first[0], second[0]),
                min(first[1], second[1]),
                max(first[2], second[2]),
                max(first[3], second[3]),
            )
            x0, y0, x1, y1 = bounds
            if x1 - x0 < minimum_width_mm or y1 - y0 < minimum_height_mm:
                continue
            first_vertical = first[1] == y0 and first[3] == y1
            second_vertical = second[1] == y0 and second[3] == y1
            first_horizontal = first[0] == x0 and first[2] == x1
            second_horizontal = second[0] == x0 and second[2] == x1
            if not (
                (first_vertical and second_horizontal) or (second_vertical and first_horizontal)
            ):
                continue
            vertical, horizontal = (first, second) if first_vertical else (second, first)
            overlap_width = min(vertical[2], horizontal[2]) - max(vertical[0], horizontal[0])
            overlap_height = min(vertical[3], horizontal[3]) - max(vertical[1], horizontal[1])
            missing_width = x1 - x0 - (vertical[2] - vertical[0])
            missing_height = y1 - y0 - (horizontal[3] - horizontal[1])
            if min(overlap_width, overlap_height, missing_width, missing_height) <= 0:
                continue
            component_area = (
                sum((right - left) * (top - bottom) for left, bottom, right, top in (first, second))
                - overlap_width * overlap_height
            )
            if component_area < minimum_program_area_mm2:
                continue
            components = tuple(sorted((first, second)))
            envelope = BuildingEnvelopeV1(SIMPLE_L, bounds, components, tuple(obstacles), site)
            if not envelope.contains(terminal):
                continue
            if not _envelope_has_edge_band_slot(
                components, bounds, support_side, support_width_mm, support_length_mm
            ) or not _envelope_has_edge_band_slot(
                components, bounds, personnel_side, personnel_width_mm, personnel_length_mm
            ):
                continue
            candidates[components] = envelope

    def order_key(
        envelope: BuildingEnvelopeV1,
    ) -> tuple[int, int, BoundsMM, tuple[BoundsMM, ...]]:
        area = sum(
            (right - left) * (top - bottom) for left, bottom, right, top in envelope.components_mm
        )
        entrance_miss = 1
        if main_entrance is not None:
            (ax, ay), (bx, by) = main_entrance
            x0, y0, x1, y1 = envelope.bounds_mm
            entrance_miss = int(not (x0 <= ax <= x1 and y0 <= ay <= y1))
        return entrance_miss, area, envelope.bounds_mm, envelope.components_mm

    return tuple(sorted(candidates.values(), key=order_key))


@lru_cache(maxsize=64)
def _maximal_clear_event_rectangles(
    boundary: PolygonMM,
    obstacles: tuple[PolygonMM, ...],
    terminal_bounds: BoundsMM,
) -> tuple[BoundsMM, ...]:
    """Return exact, maximal event-aligned rectangles clear of site obstacles."""
    site = _site_bounds(boundary)
    x_events = {point[0] for point in boundary}
    y_events = {point[1] for point in boundary}
    for obstacle in obstacles:
        for x_mm, y_mm in obstacle:
            x_events.update((x_mm - 1, x_mm, x_mm + 1))
            y_events.update((y_mm - 1, y_mm, y_mm + 1))
    x_events.update((terminal_bounds[0], terminal_bounds[2]))
    y_events.update((terminal_bounds[1], terminal_bounds[3]))
    xs = tuple(sorted(value for value in x_events if site[0] <= value <= site[2]))
    ys = tuple(sorted(value for value in y_events if site[1] <= value <= site[3]))
    if len(xs) < 2 or len(ys) < 2:
        return ()

    columns, rows = len(xs) - 1, len(ys) - 1
    invalid = [[0] * columns for _ in range(rows)]
    for row in range(rows):
        for column in range(columns):
            left, right = xs[column], xs[column + 1]
            bottom, top = ys[row], ys[row + 1]
            cell = PlacedRectangleV1(
                "event_cell",
                Decimal(left) / 1000,
                Decimal(bottom) / 1000,
                Decimal(right - left) / 1000,
                Decimal(top - bottom) / 1000,
            )
            invalid[row][column] = int(
                not rectangle_inside_polygon(cell, boundary)
                or any(
                    rectangle_intersects_closed_obstacle(cell, obstacle) for obstacle in obstacles
                )
            )
    prefix = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(rows):
        for column in range(columns):
            prefix[row + 1][column + 1] = (
                invalid[row][column]
                + prefix[row][column + 1]
                + prefix[row + 1][column]
                - prefix[row][column]
            )

    def blocked(left: int, bottom: int, right: int, top: int) -> bool:
        return (
            prefix[top][right] - prefix[bottom][right] - prefix[top][left] + prefix[bottom][left]
        ) > 0

    valid_rectangles: list[BoundsMM] = []
    for left_index in range(columns):
        for right_index in range(left_index + 1, columns + 1):
            for bottom_index in range(rows):
                for top_index in range(bottom_index + 1, rows + 1):
                    if blocked(left_index, bottom_index, right_index, top_index):
                        continue
                    bounds = (
                        xs[left_index],
                        ys[bottom_index],
                        xs[right_index],
                        ys[top_index],
                    )
                    rectangle = PlacedRectangleV1(
                        "maximal_event_rectangle",
                        Decimal(bounds[0]) / 1000,
                        Decimal(bounds[1]) / 1000,
                        Decimal(bounds[2] - bounds[0]) / 1000,
                        Decimal(bounds[3] - bounds[1]) / 1000,
                    )
                    if not rectangle_inside_polygon(rectangle, boundary) or any(
                        rectangle_intersects_closed_obstacle(rectangle, obstacle)
                        for obstacle in obstacles
                    ):
                        continue
                    expandable = (
                        left_index > 0
                        and not blocked(left_index - 1, bottom_index, right_index, top_index),
                        right_index < columns
                        and not blocked(left_index, bottom_index, right_index + 1, top_index),
                        bottom_index > 0
                        and not blocked(left_index, bottom_index - 1, right_index, top_index),
                        top_index < rows
                        and not blocked(left_index, bottom_index, right_index, top_index + 1),
                    )
                    if not any(expandable):
                        valid_rectangles.append(bounds)
    return tuple(sorted(set(valid_rectangles)))


def _envelope_has_edge_band_slot(
    components: tuple[BoundsMM, ...],
    bounds: BoundsMM,
    side: str,
    band_width_mm: int,
    band_length_mm: int,
) -> bool:
    """Check necessary dimensional capacity on the selected exterior edge."""
    x0, y0, x1, y1 = bounds
    for cx0, cy0, cx1, cy1 in components:
        if side in {"WEST", "EAST"}:
            touches_edge = cx0 == x0 if side == "WEST" else cx1 == x1
            if touches_edge and cx1 - cx0 >= band_width_mm and cy1 - cy0 >= band_length_mm:
                return True
        else:
            touches_edge = cy0 == y0 if side == "SOUTH" else cy1 == y1
            if touches_edge and cx1 - cx0 >= band_length_mm and cy1 - cy0 >= band_width_mm:
                return True
    return False


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
        if authorities[code].get("dimension_mode") == "FLEXIBLE_RECTANGLE":
            return _projected_minimum_mm(authorities[code], axis)
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
    finished = max(
        maximum("secondary_precooling_room") + maximum("finished_goods_room"),
        maximum("shipping_channel"),
    )
    return raw, core, finished


def _program_band_extents(
    authorities: Mapping[str, Mapping[str, object]], axis: str, shared_cross_span: int
) -> tuple[int, int, int]:
    """Necessary process-axis spans for the three main functional bands."""

    def group_extent(codes: Sequence[str]) -> int:
        projected = max(
            _authority_extent(authorities[code], axis)
            if authorities[code].get("dimension_mode") != "FLEXIBLE_RECTANGLE"
            else _minimum_turnable_extent(authorities[code])
            for code in codes
        )
        required_area = sum(_required_area_mm2(authorities[code]) for code in codes)
        return max(projected, _ceil_ratio(required_area, shared_cross_span))

    return (
        group_extent(FUNCTIONAL_GROUPS[RAW_SIDE_GROUP]),
        group_extent(FUNCTIONAL_GROUPS[PROCESSING_CORE_GROUP]),
        group_extent(FUNCTIONAL_GROUPS[FINISHED_SIDE_GROUP]),
    )


def _authority_projection(authority: Mapping[str, object], axis: str) -> int:
    geometry = authority.get("geometry")
    if isinstance(geometry, Mapping):
        value = geometry.get("width_m" if axis == "X" else "depth_m")
        if value is not None:
            return int(Decimal(str(value)) * 1000)
    return _projected_minimum_mm(authority, axis)


def _authority_extent(authority: Mapping[str, object], axis: str) -> int:
    geometry = authority.get("geometry")
    if not isinstance(geometry, Mapping):
        return _projected_minimum_mm(authority, axis)
    value = geometry.get("width_m" if axis == "X" else "depth_m")
    if value is None:
        return _projected_minimum_mm(authority, axis)
    return int(Decimal(str(value)) * 1000)


def _minimum_turnable_extent(authority: Mapping[str, object]) -> int:
    geometry = authority.get("geometry")
    if isinstance(geometry, Mapping):
        width = geometry.get("width_m")
        depth = geometry.get("depth_m")
        if width is not None and depth is not None:
            return min(int(Decimal(str(width)) * 1000), int(Decimal(str(depth)) * 1000))
    return _projected_minimum_mm(authority, "X")


def _peripheral_band_dimensions(
    authorities: Mapping[str, Mapping[str, object]], group_code: str
) -> tuple[int, int]:
    """Return exact short-side thickness and summed long-side room span."""
    short_sides: list[int] = []
    length = 0
    for code in FUNCTIONAL_GROUPS[group_code]:
        geometry = authorities[code].get("geometry")
        if isinstance(geometry, Mapping):
            width = geometry.get("width_m")
            depth = geometry.get("depth_m")
        else:
            width = depth = None
        if width is None or depth is None:
            side = _minimum_turnable_extent(authorities[code])
            width_mm = depth_mm = side
        else:
            width_mm = int(Decimal(str(width)) * 1000)
            depth_mm = int(Decimal(str(depth)) * 1000)
        short_sides.append(min(width_mm, depth_mm))
        length += max(width_mm, depth_mm)
    return max(short_sides), length


def _required_area_mm2(authority: Mapping[str, object]) -> int:
    value = authority.get("required_area_m2")
    if value is None:
        geometry = authority.get("geometry")
        value = geometry.get("required_area_m2") if isinstance(geometry, Mapping) else None
    if value is None:
        raise _error("STRUCTURED_ZONE_DIMENSION_AUTHORITY_MISSING")
    area = Decimal(str(value)) * 1_000_000
    return int(area.to_integral_value(rounding=ROUND_CEILING))


def _ceil_ratio(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise _error("STRUCTURED_ENVELOPE_DIMENSION_INVALID")
    return (numerator + denominator - 1) // denominator


def _entrance_side(entrance: SegmentMM | None, bounds: BoundsMM) -> str:
    if entrance is None:
        return "EAST"
    (ax, ay), (bx, by) = entrance
    x0, y0, x1, y1 = bounds
    if ax == bx:
        return "WEST" if abs(ax - x0) <= abs(ax - x1) else "EAST"
    if ay == by:
        return "SOUTH" if abs(ay - y0) <= abs(ay - y1) else "NORTH"
    distances = {
        "WEST": min(abs(ax - x0), abs(bx - x0)),
        "EAST": min(abs(ax - x1), abs(bx - x1)),
        "SOUTH": min(abs(ay - y0), abs(by - y0)),
        "NORTH": min(abs(ay - y1), abs(by - y1)),
    }
    return min(distances, key=lambda side: (distances[side], side))


def _program_envelope_dimensions(
    authorities: Mapping[str, Mapping[str, object]],
    process_axis: str,
    layout_family: str,
    personnel_side: str,
    *,
    support_side: str | None = None,
    include_peripheral_strips: bool = True,
) -> tuple[int, int]:
    """Derive the minimum envelope dimensions from the complete 12-zone program.

    Main-band spans are derived from authoritative room projections and the
    exact area needed to pack each group into the shared band depth. Support
    and personnel strips are then added on their selected exterior sides.
    The returned dimensions are family-specific and are never sourced from the
    site bounding box.
    """
    cross_axis = "Y" if process_axis == "X" else "X"
    core_cross = max(
        _authority_extent(authorities[code], cross_axis)
        if authorities[code].get("dimension_mode") != "FLEXIBLE_RECTANGLE"
        else _minimum_turnable_extent(authorities[code])
        for code in FUNCTIONAL_GROUPS[PROCESSING_CORE_GROUP]
    )
    raw_cross = max(
        _minimum_turnable_extent(authorities[code]) for code in FUNCTIONAL_GROUPS[RAW_SIDE_GROUP]
    )
    finished_cross = max(
        _minimum_turnable_extent(authorities[code])
        for code in FUNCTIONAL_GROUPS[FINISHED_SIDE_GROUP]
    )
    main_cross = max(core_cross, raw_cross, finished_cross)
    support_width, support_length = _peripheral_band_dimensions(authorities, SUPPORT_GROUP)
    personnel_width, personnel_length = _peripheral_band_dimensions(authorities, PERSONNEL_GROUP)
    band_extents = _program_band_extents(authorities, process_axis, main_cross)
    if layout_family in {LINEAR_3_BAND, SIMPLE_L_SITE_ADAPTIVE}:
        main_flow_extent = sum(band_extents)
    elif layout_family == CENTRAL_PROCESS_WITH_SIDE_BANKS:
        raw_extent, core_extent, finished_extent = band_extents
        main_flow_extent = max(core_extent, 2 * max(raw_extent, finished_extent))
    elif layout_family == LONGITUDINAL_PROCESS_SPINE:
        main_flow_extent = max(band_extents)
    else:
        raise _error("STRUCTURED_LAYOUT_FAMILY_INVALID", layout_family=layout_family)
    main_cross_extent = max(
        _authority_extent(authorities[code], cross_axis)
        if authorities[code].get("dimension_mode") != "FLEXIBLE_RECTANGLE"
        else _minimum_turnable_extent(authorities[code])
        for group in (RAW_SIDE_GROUP, PROCESSING_CORE_GROUP, FINISHED_SIDE_GROUP)
        for code in FUNCTIONAL_GROUPS[group]
    )
    width_mm, height_mm = (
        (main_flow_extent, main_cross_extent)
        if process_axis == "X"
        else (main_cross_extent, main_flow_extent)
    )
    selected_support_side = (
        support_side
        or {
            "WEST": "EAST",
            "EAST": "WEST",
            "NORTH": "SOUTH",
            "SOUTH": "NORTH",
        }[personnel_side]
    )
    if include_peripheral_strips:
        for side, strip, length in (
            (selected_support_side, support_width, support_length),
            (personnel_side, personnel_width, personnel_length),
        ):
            if side in {"WEST", "EAST"}:
                width_mm += strip
                height_mm = max(height_mm, length)
            else:
                height_mm += strip
                width_mm = max(width_mm, length)
    total_program_area = sum(_required_area_mm2(row) for row in authorities.values())
    if width_mm * height_mm < total_program_area:
        if process_axis == "X":
            height_mm = _ceil_ratio(total_program_area, width_mm)
        else:
            width_mm = _ceil_ratio(total_program_area, height_mm)
    return width_mm, height_mm


def _program_envelope_bounds(
    authorities: Mapping[str, Mapping[str, object]],
    boundary: PolygonMM,
    process_axis: str,
    layout_family: str,
    personnel_side: str,
    obstacles: Sequence[PolygonMM],
    envelope_family: str,
    candidate_index: int = 0,
    required_terminal_rectangle: PlacedRectangleV1 | None = None,
    support_side: str | None = None,
) -> BoundsMM:
    """Place the program-derived rectangular envelope at exact site events."""
    site = _site_bounds(boundary)
    width_mm, height_mm = _program_envelope_dimensions(
        authorities,
        process_axis,
        layout_family,
        personnel_side,
        support_side=support_side,
    )
    if width_mm > site[2] - site[0] or height_mm > site[3] - site[1]:
        raise _error(
            "FULL_PROGRAM_BUILDING_ENVELOPE_UNAVAILABLE",
            width_mm=width_mm,
            height_mm=height_mm,
            site_bounds_mm=list(site),
        )
    # Enumerate exact geometry events rather than treating the site bounding
    # rectangle as the building.  For RECTANGLE, the selected planned body
    # must itself be inside the effective site and clear of hard obstacles.
    x_events = {point[0] for point in boundary}
    y_events = {point[1] for point in boundary}
    for obstacle in obstacles:
        x_events.update(point[0] for point in obstacle)
        y_events.update(point[1] for point in obstacle)
    x_origins = {coordinate + shift for coordinate in x_events for shift in (0, -width_mm)}
    y_origins = {coordinate + shift for coordinate in y_events for shift in (0, -height_mm)}
    x_origins.update((site[0], site[2] - width_mm))
    y_origins.update((site[1], site[3] - height_mm))
    feasible: list[BoundsMM] = []
    for x0 in sorted(value for value in x_origins if site[0] <= value <= site[2] - width_mm):
        for y0 in sorted(value for value in y_origins if site[1] <= value <= site[3] - height_mm):
            bounds = (x0, y0, x0 + width_mm, y0 + height_mm)
            rectangle = PlacedRectangleV1(
                "planned_building_envelope",
                Decimal(x0) / 1000,
                Decimal(y0) / 1000,
                Decimal(width_mm) / 1000,
                Decimal(height_mm) / 1000,
            )
            if envelope_family == RECTANGLE and (
                not rectangle_inside_polygon(rectangle, boundary)
                or any(
                    rectangle_intersects_closed_obstacle(rectangle, obstacle)
                    for obstacle in obstacles
                )
            ):
                continue
            if required_terminal_rectangle is not None:
                left, bottom, right, top = required_terminal_rectangle.bounds_mm
                if not (
                    x0 <= left and y0 <= bottom and right <= x0 + width_mm and top <= y0 + height_mm
                ):
                    continue
            feasible.append(bounds)
    if not feasible:
        raise _error(
            "PROGRAM_BUILDING_ENVELOPE_NO_EXACT_SITE_SLOT",
            width_mm=width_mm,
            height_mm=height_mm,
            site_bounds_mm=list(site),
        )

    def entrance_attachment_penalty(bounds: BoundsMM) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = bounds
        primary_gap = {
            "WEST": x0 - site[0],
            "EAST": site[2] - x1,
            "SOUTH": y0 - site[1],
            "NORTH": site[3] - y1,
        }[personnel_side]
        return primary_gap, y0, x0, y1 - y0

    ordered = sorted(feasible, key=entrance_attachment_penalty)
    if candidate_index >= len(ordered):
        raise _error(
            "PROGRAM_BUILDING_ENVELOPE_VARIANT_UNAVAILABLE",
            candidate_index=candidate_index,
            candidate_count=len(ordered),
        )
    return ordered[candidate_index]


def _band_bounds(
    layout_family: str,
    group_band: str,
    envelope: BoundsMM,
    axis: str,
    extents: tuple[int, int, int],
    cross_extents: tuple[int, int, int],
    *,
    main_bounds: BoundsMM,
    support_side: str,
    personnel_side: str,
    support_width: int,
    personnel_width: int,
    support_length: int,
    personnel_length: int,
    main_entrance: SegmentMM | None,
    envelope_components: tuple[BoundsMM, ...],
) -> BoundsMM:
    x0, y0, x1, y1 = main_bounds
    low = x0 if axis == "X" else y0
    high = x1 if axis == "X" else y1
    span = high - low
    raw, core, finished = extents

    if group_band in {SUPPORT_BAND, PERSONNEL_EDGE_BAND}:
        side = support_side if group_band == SUPPORT_BAND else personnel_side
        width = support_width if group_band == SUPPORT_BAND else personnel_width
        length = support_length if group_band == SUPPORT_BAND else personnel_length
        target = (
            sum(point[1] for point in main_entrance) // 2
            if side in {"WEST", "EAST"}
            and group_band == PERSONNEL_EDGE_BAND
            and main_entrance is not None
            else sum(point[0] for point in main_entrance) // 2
            if side in {"NORTH", "SOUTH"}
            and group_band == PERSONNEL_EDGE_BAND
            and main_entrance is not None
            else (y0 + y1) // 2
            if side in {"WEST", "EAST"}
            else (x0 + x1) // 2
        )
        feasible_bands: list[tuple[tuple[int, int, BoundsMM], BoundsMM]] = []
        for component in envelope_components:
            cx0, cy0, cx1, cy1 = component
            if side in {"WEST", "EAST"}:
                touches_side = cx0 == x0 if side == "WEST" else cx1 == x1
                if not touches_side or cx1 - cx0 < width or cy1 - cy0 < length:
                    continue
                low = min(max(target - length // 2, cy0), cy1 - length)
                left = cx0 if side == "WEST" else cx1 - width
                band = (left, low, left + width, low + length)
            else:
                touches_side = cy0 == y0 if side == "SOUTH" else cy1 == y1
                if not touches_side or cx1 - cx0 < length or cy1 - cy0 < width:
                    continue
                low = min(max(target - length // 2, cx0), cx1 - length)
                bottom = cy0 if side == "SOUTH" else cy1 - width
                band = (low, bottom, low + length, bottom + width)
            band_center = (
                (band[1] + band[3]) // 2 if side in {"WEST", "EAST"} else (band[0] + band[2]) // 2
            )
            feasible_bands.append(
                ((abs(band_center - target), (cx1 - cx0) * (cy1 - cy0), component), band)
            )
        if not feasible_bands:
            raise _error(
                "STRUCTURED_PERIPHERAL_BAND_NO_ENVELOPE_SLOT",
                band_code=group_band,
                side=side,
                required_width_mm=width,
                required_length_mm=length,
            )
        return min(feasible_bands, key=lambda row: row[0])[1]

    if layout_family in {LINEAR_3_BAND, SIMPLE_L_SITE_ADAPTIVE}:
        # The linear family owns three ordered process-axis intervals inside
        # the central building body. Transition bands overlap by dimensions
        # derived from the frozen room program, not by visual thresholds.
        if group_band == RAW_SIDE_BAND:
            lo, hi = low, min(high, low + raw)
        elif group_band == PROCESS_CORE_BAND:
            lo = max(low, low + raw)
            hi = min(high, lo + core)
        elif group_band == FINISHED_SIDE_BAND:
            lo = max(low, high - finished)
            hi = high
        else:
            raise _error("STRUCTURED_BAND_FAMILY_INVALID", band_code=group_band)
        if axis == "X":
            return lo, y0, hi, y1
        return x0, lo, x1, hi

    cross_axis = "Y" if axis == "X" else "X"
    cross_low, cross_high = (y0, y1) if cross_axis == "Y" else (x0, x1)
    cross_span = cross_high - cross_low
    axis_middle = low + span // 2
    if layout_family == CENTRAL_PROCESS_WITH_SIDE_BANKS:
        if group_band == PROCESS_CORE_BAND:
            core_cross = min(cross_span, cross_extents[1])
            cross_a = cross_low + max(0, (cross_span - core_cross) // 2)
            cross_b = min(cross_high, cross_a + core_cross)
            return (x0, cross_a, x1, cross_b) if axis == "X" else (cross_a, y0, cross_b, y1)
        if group_band == RAW_SIDE_BAND:
            axis_a, axis_b = low, min(high, axis_middle)
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
            axis_a, axis_b = max(low, axis_middle), high
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
        raise _error("STRUCTURED_BAND_FAMILY_INVALID", band_code=group_band)
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
        raise _error("STRUCTURED_BAND_FAMILY_INVALID", band_code=group_band)

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
    raise _error("STRUCTURED_BAND_FAMILY_INVALID", band_code=group_band)


def construct_structured_building_plan_v1(
    *,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    authorities: Mapping[str, Mapping[str, object]],
    process_axis: str,
    layout_family: str,
    envelope_family: str = RECTANGLE,
    main_entrance: SegmentMM | None = None,
    envelope_candidate_index: int = 0,
    required_terminal_rectangle: PlacedRectangleV1 | None = None,
    support_side: str | None = None,
) -> StructuredBuildingSkeletonV1:
    """Create the envelope, event grid, then bands before any zone is placed."""
    if process_axis not in {"X", "Y"}:
        raise _error("STRUCTURED_PROCESS_AXIS_INVALID")
    if layout_family not in _LAYOUT_FAMILIES:
        raise _error("STRUCTURED_LAYOUT_FAMILY_INVALID", layout_family=layout_family)
    site_bounds = _site_bounds(boundary)
    personnel_side = _entrance_side(main_entrance, site_bounds)
    default_support_side = {
        "WEST": "EAST",
        "EAST": "WEST",
        "NORTH": "SOUTH",
        "SOUTH": "NORTH",
    }[personnel_side]
    selected_support_side = support_side or default_support_side
    if selected_support_side not in {"WEST", "EAST", "NORTH", "SOUTH"}:
        raise _error("STRUCTURED_SUPPORT_SIDE_INVALID", support_side=selected_support_side)
    support_width, support_length = _peripheral_band_dimensions(authorities, SUPPORT_GROUP)
    personnel_width, personnel_length = _peripheral_band_dimensions(authorities, PERSONNEL_GROUP)
    if envelope_family == RECTANGLE:
        envelope_bounds = _program_envelope_bounds(
            authorities,
            boundary,
            process_axis,
            layout_family,
            personnel_side,
            obstacles,
            envelope_family,
            envelope_candidate_index,
            required_terminal_rectangle,
            selected_support_side,
        )
        envelope = BuildingEnvelopeV1(
            RECTANGLE, envelope_bounds, (envelope_bounds,), tuple(obstacles), site_bounds
        )
    elif envelope_family == SIMPLE_L:
        minimum_program_area = sum(_required_area_mm2(row) for row in authorities.values())
        minimum_width, minimum_height = _program_envelope_dimensions(
            authorities,
            process_axis,
            layout_family,
            personnel_side,
            support_side=selected_support_side,
            include_peripheral_strips=False,
        )
        if required_terminal_rectangle is not None:
            candidates = _simple_l_envelopes_for_terminal(
                boundary,
                obstacles,
                minimum_program_area,
                minimum_width,
                minimum_height,
                selected_support_side,
                support_width,
                support_length,
                personnel_side,
                personnel_width,
                personnel_length,
                main_entrance,
                required_terminal_rectangle,
            )
        else:
            candidates = _simple_l_envelopes(
                boundary,
                obstacles,
                minimum_program_area,
                minimum_width,
                minimum_height,
                selected_support_side,
                support_width,
                support_length,
                personnel_side,
                personnel_width,
                personnel_length,
                main_entrance,
            )
        if not candidates:
            raise _error("SIMPLE_L_ENVELOPE_UNAVAILABLE")
        compatible = tuple(
            candidate
            for candidate in candidates
            if required_terminal_rectangle is None
            or candidate.contains(required_terminal_rectangle)
        )
        if envelope_candidate_index >= len(compatible):
            raise _error(
                "SIMPLE_L_ENVELOPE_TERMINAL_VARIANT_UNAVAILABLE",
                candidate_index=envelope_candidate_index,
                candidate_count=len(compatible),
            )
        envelope = compatible[envelope_candidate_index]
        envelope_bounds = envelope.bounds_mm
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
    support_side_bounds = _band_bounds(
        layout_family,
        SUPPORT_BAND,
        envelope_bounds,
        process_axis,
        extents,
        cross_extents,
        main_bounds=envelope_bounds,
        support_side=selected_support_side,
        personnel_side=personnel_side,
        support_width=support_width,
        personnel_width=personnel_width,
        support_length=support_length,
        personnel_length=personnel_length,
        main_entrance=main_entrance,
        envelope_components=envelope.components_mm,
    )
    personnel_side_bounds = _band_bounds(
        layout_family,
        PERSONNEL_EDGE_BAND,
        envelope_bounds,
        process_axis,
        extents,
        cross_extents,
        main_bounds=envelope_bounds,
        support_side=selected_support_side,
        personnel_side=personnel_side,
        support_width=support_width,
        personnel_width=personnel_width,
        support_length=support_length,
        personnel_length=personnel_length,
        main_entrance=main_entrance,
        envelope_components=envelope.components_mm,
    )
    main_bounds = envelope_bounds
    extents = _program_band_extents(
        authorities,
        process_axis,
        main_bounds[3] - main_bounds[1] if process_axis == "X" else main_bounds[2] - main_bounds[0],
    )
    raw_band = _band_bounds(
        layout_family,
        RAW_SIDE_BAND,
        envelope_bounds,
        process_axis,
        extents,
        cross_extents,
        main_bounds=main_bounds,
        support_side=selected_support_side,
        personnel_side=personnel_side,
        support_width=support_width,
        personnel_width=personnel_width,
        support_length=support_length,
        personnel_length=personnel_length,
        main_entrance=main_entrance,
        envelope_components=envelope.components_mm,
    )
    process_band = _band_bounds(
        layout_family,
        PROCESS_CORE_BAND,
        envelope_bounds,
        process_axis,
        extents,
        cross_extents,
        main_bounds=main_bounds,
        support_side=selected_support_side,
        personnel_side=personnel_side,
        support_width=support_width,
        personnel_width=personnel_width,
        support_length=support_length,
        personnel_length=personnel_length,
        main_entrance=main_entrance,
        envelope_components=envelope.components_mm,
    )
    finished_band = _band_bounds(
        layout_family,
        FINISHED_SIDE_BAND,
        envelope_bounds,
        process_axis,
        extents,
        cross_extents,
        main_bounds=main_bounds,
        support_side=selected_support_side,
        personnel_side=personnel_side,
        support_width=support_width,
        personnel_width=personnel_width,
        support_length=support_length,
        personnel_length=personnel_length,
        main_entrance=main_entrance,
        envelope_components=envelope.components_mm,
    )
    if required_terminal_rectangle is not None:
        if not envelope.contains(required_terminal_rectangle):
            raise _error("STRUCTURED_TERMINAL_ZONE_OUTSIDE_ENVELOPE")
        left, bottom, right, top = finished_band
        terminal_left, terminal_bottom, terminal_right, terminal_top = (
            required_terminal_rectangle.bounds_mm
        )
        finished_band = (
            min(left, terminal_left),
            min(bottom, terminal_bottom),
            max(right, terminal_right),
            max(top, terminal_top),
        )
    band_bounds = {
        RAW_SIDE_BAND: raw_band,
        PROCESS_CORE_BAND: process_band,
        FINISHED_SIDE_BAND: finished_band,
        SUPPORT_BAND: support_side_bounds,
        PERSONNEL_EDGE_BAND: personnel_side_bounds,
    }

    # Primary axes consist only of envelope and major-band boundaries.
    # Boundary, obstacle, and dimension events remain local search axes.
    x_axes = {envelope_bounds[0], envelope_bounds[2]}
    y_axes = {envelope_bounds[1], envelope_bounds[3]}
    for bounds in (raw_band, process_band, finished_band):
        x_axes.update((bounds[0], bounds[2]))
        y_axes.update((bounds[1], bounds[3]))
    event_x = {point[0] for point in boundary}
    event_y = {point[1] for point in boundary}
    for obstacle in obstacles:
        event_x.update(point[0] for point in obstacle)
        event_y.update(point[1] for point in obstacle)
    event_x.update(x_axes)
    event_y.update(y_axes)
    for bounds in (support_side_bounds, personnel_side_bounds):
        event_x.update((bounds[0], bounds[2]))
        event_y.update((bounds[1], bounds[3]))
    dimension_events: set[int] = set()
    for authority in authorities.values():
        geometry = authority.get("geometry")
        if not isinstance(geometry, Mapping):
            continue
        for key in ("width_m", "depth_m"):
            value = geometry.get(key)
            if value is None:
                continue
            dimension_events.add(int(Decimal(str(value)) * 1000))
    # Dimension-derived local origins are based only on original geometry
    # events.  Recursively expanding already-derived events creates a
    # combinatorial coordinate closure and accidentally turns local placement
    # anchors into a second, unbounded grid.
    base_event_x = tuple(sorted(event_x))
    base_event_y = tuple(sorted(event_y))
    event_x.update(
        coordinate + sign * extent
        for coordinate in base_event_x
        for extent in dimension_events
        for sign in (-1, 1)
    )
    event_y.update(
        coordinate + sign * extent
        for coordinate in base_event_y
        for extent in dimension_events
        for sign in (-1, 1)
    )
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
            band_bounds[band_code],
            process_axis,
            ordering_role,
            selected_support_side
            if band_code == SUPPORT_BAND
            else personnel_side
            if band_code == PERSONNEL_EDGE_BAND
            else None,
        )
        for band_code, group_code, ordering_role in (
            (RAW_SIDE_BAND, RAW_SIDE_GROUP, "UPSTREAM"),
            (PROCESS_CORE_BAND, PROCESSING_CORE_GROUP, "CORE"),
            (FINISHED_SIDE_BAND, FINISHED_SIDE_GROUP, "DOWNSTREAM"),
            (SUPPORT_BAND, SUPPORT_GROUP, "SUBORDINATE_BRANCH"),
            (PERSONNEL_EDGE_BAND, PERSONNEL_GROUP, "PERIPHERAL"),
        )
    )
    return StructuredBuildingSkeletonV1(
        layout_family,
        process_axis,
        envelope,
        grid,
        bands,
        support_side=selected_support_side,
        personnel_side=personnel_side,
    )


def zone_band_assignment(zone_code: str) -> str:
    group = functional_group_for_zone(zone_code)
    return next(band for band, band_group in _BAND_GROUPS.items() if band_group == group)


__all__ = [
    "BuildingEnvelopeV1",
    "BASE_LAYOUT_FAMILIES",
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
    "zone_band_assignment",
]
