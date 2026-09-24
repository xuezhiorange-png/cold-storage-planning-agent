"""Deterministic, placement-only geometry search for the V2.2 P2C MVP.

This module consumes already-bound zone dimensions and site geometry.  It does
not calculate zone areas, generate a building envelope, or validate portals,
corridors, truck manoeuvres, or routes.  All geometry is represented as
integer millimetres at the predicate boundary so the incomplete search is
repeatable and has no floating-point tolerance.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from math import isqrt
from typing import Any, Final, cast

from cold_storage.modules.layout.domain.adjacency import AdjacencyGraphV1
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.objective_profile import (
    CARDINAL_LOADING_SIDE_METRIC,
    LOADING_SIDE_PREFERENCE,
    NEAREST_TRUCK_ENTRANCE_COMPARATOR,
    NEAREST_TRUCK_ENTRANCE_INTERNAL_UNIT,
    SHOULD_ADJACENT,
    approved_objective_profile,
)
from cold_storage.modules.layout.domain.site_geometry import (
    GRID_M,
    MILLIMETRES_PER_METRE,
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    normalize_polygon,
    normalize_segment,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    segments_share_positive_length,
)
from cold_storage.modules.layout.domain.structural_composition import (
    FUNCTIONAL_GROUPS,
    MAIN_PROCESS_PREDECESSOR,
    MAIN_PROCESS_ZONE_CODES,
    SUPPORT_GROUP,
    StructuralCompositionFamilyV1,
    select_structural_composition_family,
    structural_anchor_references,
)

IDENTITY: Final = "site-constrained-deterministic-placement@1.0.0"
PLACEMENT_RESULT_IDENTITY: Final = "site_constrained_factory_layout@1.0.0"
SCHEMA_VERSION: Final = "1.0.0"
SEARCH_PROFILE_IDENTITY: Final = "deterministic-placement-search@1.0.0"
GRID_MM: Final = 1
DEFAULT_NODE_BUDGET: Final = 50_000
MAX_OPTIONS_PER_ZONE: Final = 48

# Group -> band -> zone order: first the authoritative main process, then the
# peripheral personnel group (whose main-entrance access is already frozen),
# then support branches. All non-process groups remain subordinate to the
# process skeleton; hard relationships still come only from frozen authority.
PLACEMENT_ZONE_ORDER: Final = (
    "raw_fruit_buffer",
    "primary_precooling_room",
    "sorting_packaging_room",
    "secondary_precooling_room",
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
    "changing_room",
    "office",
    "packaging_material_storage",
    "secondary_fruit_buffer",
    "frozen_fruit_room",
)
FLEXIBLE_ZONE_CODES: Final = ("coating_room", "changing_room", "office")
SUPPORT_ZONE_CODES: Final = FUNCTIONAL_GROUPS[SUPPORT_GROUP]


@dataclass(frozen=True)
class PlacementCandidateV1:
    """Immutable selected-candidate evidence, excluding derived hash input."""

    payload_json: str
    _content_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PlacementCandidateV1:
        content = dict(payload)
        content.pop("canonical_candidate_hash", None)
        normalized = canonical_json(content)
        return cls(normalized, canonical_hash(content))

    def to_dict(self) -> dict[str, Any]:
        import json

        value = cast(dict[str, Any], json.loads(self.payload_json))
        value["canonical_candidate_hash"] = self._content_hash
        return value

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_candidate_hash(self) -> str:
        return self._content_hash


@dataclass(frozen=True)
class SitePlacementResultV1:
    """Immutable placement result; route validation is deliberately absent."""

    payload_json: str
    _content_hash: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SitePlacementResultV1:
        content = dict(payload)
        content.pop("canonical_result_hash", None)
        normalized = canonical_json(content)
        return cls(normalized, canonical_hash(content))

    def to_dict(self) -> dict[str, Any]:
        import json

        value = cast(dict[str, Any], json.loads(self.payload_json))
        value["canonical_result_hash"] = self._content_hash
        return value

    def canonical_json(self) -> str:
        return self.payload_json

    @property
    def canonical_result_hash(self) -> str:
        return self._content_hash


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _decimal(value: object, *, field: str, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("INVALID_PLACEMENT_AUTHORITY", field=field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _error("INVALID_PLACEMENT_AUTHORITY", field=field) from None
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise _error("INVALID_PLACEMENT_AUTHORITY", field=field)
    return number


def _mm(value: object, *, field: str, positive: bool = False) -> int:
    number = _decimal(value, field=field, positive=positive)
    with localcontext(Context(prec=80)):
        scaled = number * MILLIMETRES_PER_METRE
        if scaled != scaled.to_integral_value() or (positive and scaled <= 0):
            raise _error("INVALID_PLACEMENT_GRID_VALUE", field=field, grid_m=str(GRID_M))
        return int(scaled)


def _m(value: int) -> Decimal:
    with localcontext(Context(prec=80)):
        return Decimal(value) / MILLIMETRES_PER_METRE


def _ceil_fraction(value: Fraction) -> int:
    if value.denominator == 1:
        return value.numerator
    return value.numerator // value.denominator + 1


def _ceil_area_depth(required_area_m2: Decimal, width_mm: int) -> int:
    if width_mm <= 0:
        raise _error("INVALID_FLEXIBLE_DIMENSION", field="width_m")
    # 1 m2 = 1,000,000 mm2.  Fraction preserves every decimal digit from the
    # canonical source and makes the outward grid rounding explicit.
    required_mm2 = Fraction(required_area_m2) * 1_000_000
    return max(1, _ceil_fraction(required_mm2 / width_mm))


def _rectangle_from_mm(
    code: str, x_mm: int, y_mm: int, width_mm: int, depth_mm: int, rotation_deg: int
) -> PlacedRectangleV1:
    return PlacedRectangleV1(code, _m(x_mm), _m(y_mm), _m(width_mm), _m(depth_mm), rotation_deg)


def _bounds(rectangle: PlacedRectangleV1) -> tuple[int, int, int, int]:
    return rectangle.bounds_mm


def _authority_code(authority: Mapping[str, Any]) -> str:
    code = authority.get("zone_code")
    if not isinstance(code, str) or not code:
        raise _error("INVALID_PLACEMENT_AUTHORITY", field="zone_code")
    return code


def _authority_mode(authority: Mapping[str, Any]) -> str:
    mode = authority.get("dimension_mode")
    if not isinstance(mode, str) or mode not in {
        "FIXED_RECTANGLE",
        "DETERMINISTIC_GRID_RECTANGLE",
        "FLEXIBLE_RECTANGLE",
    }:
        raise _error("INVALID_PLACEMENT_AUTHORITY", field="dimension_mode")
    return mode


def _authority_dimensions(authority: Mapping[str, Any]) -> tuple[int, int, Decimal]:
    geometry = authority.get("geometry")
    if not isinstance(geometry, Mapping):
        raise _error("FLEXIBLE_DIMENSION_REQUIRED", zone_code=_authority_code(authority))
    width = _mm(geometry.get("width_m"), field="width_m", positive=True)
    depth = _mm(geometry.get("depth_m"), field="depth_m", positive=True)
    area = _decimal(geometry.get("required_area_m2"), field="required_area_m2")
    return width, depth, area


def _required_area(authority: Mapping[str, Any]) -> Decimal:
    return _decimal(authority.get("required_area_m2"), field="required_area_m2")


def _polygon(value: object) -> PolygonMM:
    if not isinstance(value, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT")
    return normalize_polygon(value, allow_numeric_string=True)


def _boundary_extents(boundary: PolygonMM) -> tuple[int, int, int, int]:
    xs = [point[0] for point in boundary]
    ys = [point[1] for point in boundary]
    return min(xs), min(ys), max(xs), max(ys)


def _unique_dimensions(
    authority: Mapping[str, Any], placed: Mapping[str, PlacedRectangleV1], boundary: PolygonMM
) -> tuple[tuple[int, int], ...]:
    mode = _authority_mode(authority)
    if mode != "FLEXIBLE_RECTANGLE":
        width, depth, _ = _authority_dimensions(authority)
        return ((width, depth),)

    required = _required_area(authority)
    required_mm2 = max(1, _ceil_fraction(Fraction(required) * 1_000_000))
    near = max(1, isqrt(required_mm2))
    if near * near < required_mm2:
        near += 1

    width_candidates: set[int] = {near, near + 1}
    min_x, min_y, max_x, max_y = _boundary_extents(boundary)
    width_candidates.update({max_x - min_x, max_y - min_y})
    for point_a, point_b in zip(boundary, boundary[1:] + boundary[:1], strict=True):
        width_candidates.add(abs(point_b[0] - point_a[0]))
        width_candidates.add(abs(point_b[1] - point_a[1]))
    for rectangle in placed.values():
        left, bottom, right, top = _bounds(rectangle)
        width_candidates.update({right - left, top - bottom})

    dimensions: set[tuple[int, int]] = set()
    for width in sorted(width_candidates):
        if width <= 0:
            continue
        depth = _ceil_area_depth(required, width)
        dimensions.add((width, depth))
        dimensions.add((depth, width))
    if not dimensions:
        raise _error("FLEXIBLE_DIMENSION_CANDIDATES_EMPTY", zone_code=_authority_code(authority))
    return tuple(sorted(dimensions))


def _dimension_variants(
    authority: Mapping[str, Any], placed: Mapping[str, PlacedRectangleV1], boundary: PolygonMM
) -> tuple[tuple[int, int, int], ...]:
    dimensions = _unique_dimensions(authority, placed, boundary)
    rotations = (0, 90)
    variants: list[tuple[int, int, int]] = []
    for width, depth in dimensions:
        for rotation in rotations:
            candidate = (width, depth, rotation)
            if candidate not in variants:
                variants.append(candidate)
    return tuple(variants)


def _edge_anchors(
    neighbor: PlacedRectangleV1, width_mm: int, depth_mm: int
) -> tuple[tuple[int, int], ...]:
    left, bottom, right, top = _bounds(neighbor)
    y_values = (bottom, top - depth_mm, bottom + (top - bottom - depth_mm) // 2)
    x_values = (left, right - width_mm, left + (right - left - width_mm) // 2)
    anchors = (
        {(left - width_mm, y) for y in y_values}
        | {(right, y) for y in y_values}
        | {(x, bottom - depth_mm) for x in x_values}
        | {(x, top) for x in x_values}
    )
    return tuple(sorted(anchors))


def _free_anchors(
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    width_mm: int,
    depth_mm: int,
) -> tuple[tuple[int, int], ...]:
    min_x, min_y, max_x, max_y = _boundary_extents(boundary)
    xs: set[int] = {min_x, max_x - width_mm}
    ys: set[int] = {min_y, max_y - depth_mm}
    for point in boundary:
        xs.update({point[0], point[0] - width_mm})
        ys.update({point[1], point[1] - depth_mm})
    for polygon in obstacles:
        for point in polygon:
            xs.update({point[0], point[0] - width_mm, point[0] + 1})
            ys.update({point[1], point[1] - depth_mm, point[1] + 1})
    anchors: set[tuple[int, int]] = {(x, y) for x in xs for y in ys}
    for rectangle in placed.values():
        left, bottom, right, top = _bounds(rectangle)
        xs.update({left - width_mm, left, right - width_mm, right})
        ys.update({bottom - depth_mm, bottom, top - depth_mm, top})
        anchors.update(_edge_anchors(rectangle, width_mm, depth_mm))
    anchors.update((x, y) for x in xs for y in ys)
    return tuple(sorted(anchors))


def _must_neighbors(
    code: str, placed: Mapping[str, PlacedRectangleV1], graph: AdjacencyGraphV1
) -> tuple[PlacedRectangleV1, ...]:
    neighbors = []
    for first, second in graph.must_adjacencies:
        other: str | None = None
        if first == code:
            other = second
        elif second == code:
            other = first
        if other is not None and other in placed:
            neighbors.append(placed[other])
    return tuple(sorted(neighbors, key=lambda rectangle: rectangle.zone_code))


def _should_local_count(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    graph: AdjacencyGraphV1,
) -> int:
    count = 0
    for first, second in graph.should_adjacencies:
        if (
            (first == code and second in placed) or (second == code and first in placed)
        ) and rectangles_share_positive_edge(rectangle, placed[second if first == code else first]):
            count += 1
    return count


def _rectangle_is_usable(
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    boundary_bounds: tuple[int, int, int, int],
    obstacles: Sequence[PolygonMM],
) -> bool:
    left, bottom, right, top = _bounds(rectangle)
    min_x, min_y, max_x, max_y = boundary_bounds
    if left < min_x or bottom < min_y or right > max_x or top > max_y:
        return False
    if not rectangle_inside_polygon(rectangle, boundary):
        return False
    if any(rectangle_intersects_closed_obstacle(rectangle, obstacle) for obstacle in obstacles):
        return False
    return not any(rectangles_overlap(rectangle, other) for other in placed.values())


def _rectangle_shares_entrance_boundary(rectangle: PlacedRectangleV1, entrance: SegmentMM) -> bool:
    left, bottom, right, top = _bounds(rectangle)
    edges = (
        ((left, bottom), (right, bottom)),
        ((right, bottom), (right, top)),
        ((right, top), (left, top)),
        ((left, top), (left, bottom)),
    )
    return any(segments_share_positive_length(*edge, *entrance) for edge in edges)


def _candidate_options(
    code: str,
    authority: Mapping[str, Any],
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    boundary_bounds: tuple[int, int, int, int],
    obstacles: Sequence[PolygonMM],
    graph: AdjacencyGraphV1,
    structural_family: StructuralCompositionFamilyV1,
    main_entrance: SegmentMM,
) -> tuple[PlacedRectangleV1, ...]:
    variants = _dimension_variants(authority, placed, boundary)
    options: dict[tuple[int, int, int, int, int], PlacedRectangleV1] = {}
    must_neighbors = _must_neighbors(code, placed, graph)
    structural_refs = structural_anchor_references(code, tuple(placed))
    structural_neighbors = tuple(placed[reference] for reference in structural_refs)
    for width_mm, depth_mm, rotation in variants:
        anchor_width_mm, anchor_depth_mm = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        legacy_anchors = (
            {
                anchor
                for neighbor in must_neighbors
                for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
            }
            if must_neighbors
            else set(_free_anchors(placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm))
        )
        if structural_neighbors:
            structural_anchors = {
                anchor
                for neighbor in (*must_neighbors, *structural_neighbors)
                for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
            }
        else:
            structural_anchors = set()
        if code == "changing_room":
            structural_anchors.update(
                anchor
                for anchor in _entrance_anchors(main_entrance, anchor_width_mm, anchor_depth_mm)
            )
        anchors = tuple(sorted(structural_anchors | legacy_anchors))
        for x_mm, y_mm in anchors:
            rectangle = _rectangle_from_mm(code, x_mm, y_mm, width_mm, depth_mm, rotation)
            if not _rectangle_is_usable(rectangle, placed, boundary, boundary_bounds, obstacles):
                continue
            if any(
                not rectangles_share_positive_edge(rectangle, neighbor)
                for neighbor in must_neighbors
            ):
                continue
            key = (x_mm, y_mm, width_mm, depth_mm, rotation)
            options[key] = rectangle

    def stable_geometry_key(rectangle: PlacedRectangleV1) -> tuple[object, ...]:
        entrance_alignment_rank = int(
            code == "changing_room"
            and not _rectangle_shares_entrance_boundary(rectangle, main_entrance)
        )
        linear_rank = 0
        if structural_family.family == "LINEAR_PROCESS_BAND" and code in MAIN_PROCESS_PREDECESSOR:
            predecessor = placed.get(MAIN_PROCESS_PREDECESSOR[code])
            if predecessor is not None:
                linear_rank = int(
                    not _linear_flow_anchor_matches(rectangle, predecessor, structural_family)
                )
        return (
            entrance_alignment_rank,
            linear_rank,
            -_finished_band_axis_reuse(code, rectangle, placed),
            -_support_group_edge_count(code, rectangle, placed),
            -_support_obstacle_x_alignment(code, rectangle, obstacles),
            -_support_process_axis_reuse(code, rectangle, placed),
            -_should_local_count(code, rectangle, placed, graph),
            rectangle.x,
            rectangle.y,
            rectangle.width_m,
            rectangle.depth_m,
            rectangle.rotation_deg,
        )

    def structurally_anchored(rectangle: PlacedRectangleV1) -> bool:
        if code == "changing_room" and _rectangle_shares_entrance_boundary(
            rectangle, main_entrance
        ):
            return True
        if not structural_neighbors:
            if code != "raw_fruit_buffer":
                return False
            return _rectangle_touches_boundary(rectangle, boundary)
        if structural_family.family == "LINEAR_PROCESS_BAND" and code in MAIN_PROCESS_PREDECESSOR:
            predecessor = placed.get(MAIN_PROCESS_PREDECESSOR[code])
            return predecessor is not None and _linear_flow_anchor_matches(
                rectangle, predecessor, structural_family
            )
        return any(
            rectangles_share_positive_edge(rectangle, neighbor) for neighbor in structural_neighbors
        )

    structured = sorted(
        (rectangle for rectangle in options.values() if structurally_anchored(rectangle)),
        key=stable_geometry_key,
    )
    general = sorted(
        (rectangle for rectangle in options.values() if not structurally_anchored(rectangle)),
        key=stable_geometry_key,
    )
    return tuple((*structured, *general)[:MAX_OPTIONS_PER_ZONE])


def _entrance_anchors(
    entrance: SegmentMM, width_mm: int, depth_mm: int
) -> tuple[tuple[int, int], ...]:
    """Place a zone edge over an authoritative site entrance, without offsets."""
    (x1, y1), (x2, y2) = entrance
    anchors: set[tuple[int, int]] = set()
    if x1 == x2:
        low_y, high_y = sorted((y1, y2))
        aligned_y = {
            (low_y + high_y - depth_mm) // 2,
            low_y,
            high_y - depth_mm,
        }
        anchors.update((x1 - width_mm, y) for y in aligned_y)
        anchors.update((x1, y) for y in aligned_y)
    elif y1 == y2:
        low_x, high_x = sorted((x1, x2))
        aligned_x = {
            (low_x + high_x - width_mm) // 2,
            low_x,
            high_x - width_mm,
        }
        anchors.update((x, y1 - depth_mm) for x in aligned_x)
        anchors.update((x, y1) for x in aligned_x)
    return tuple(sorted(anchors))


def _finished_band_axis_reuse(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
) -> int:
    """Prefer exact reuse of the current process-band axes for finished goods."""
    if code != "finished_goods_room":
        return 0
    left, bottom, right, top = _bounds(rectangle)
    major_x_axes = {
        coordinate
        for placed_code, existing in placed.items()
        if placed_code
        in {
            "primary_precooling_room",
            "secondary_precooling_room",
            "sorting_packaging_room",
            "coating_room",
            "packaging_material_storage",
        }
        for coordinate in (_bounds(existing)[0], _bounds(existing)[2])
    }
    major_y_axes = {
        coordinate
        for placed_code, existing in placed.items()
        if placed_code
        in {
            "primary_precooling_room",
            "secondary_precooling_room",
            "sorting_packaging_room",
            "coating_room",
            "packaging_material_storage",
        }
        for coordinate in (_bounds(existing)[1], _bounds(existing)[3])
    }
    return sum(coordinate in major_x_axes for coordinate in (left, right)) + sum(
        coordinate in major_y_axes for coordinate in (bottom, top)
    )


def _support_group_edge_count(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
) -> int:
    """Prefer support-to-support grouping over spreading branches around the core."""
    if code not in SUPPORT_ZONE_CODES:
        return 0
    return sum(
        int(
            reference in SUPPORT_ZONE_CODES
            and reference in placed
            and rectangles_share_positive_edge(rectangle, placed[reference])
        )
        for reference in SUPPORT_ZONE_CODES
        if reference != code
    )


def _support_obstacle_x_alignment(
    code: str,
    rectangle: PlacedRectangleV1,
    obstacles: Sequence[PolygonMM],
) -> int:
    """Prefer the frozen-support block on an exact vertical site-constraint axis."""
    if code != "frozen_fruit_room":
        return 0
    obstacle_x = {point[0] for polygon in obstacles for point in polygon}
    left, _, right, _ = _bounds(rectangle)
    return sum(coordinate in obstacle_x for coordinate in (left, right))


def _support_process_axis_reuse(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
) -> int:
    """Count exact support-zone boundary incidences on established process axes."""
    if code not in SUPPORT_ZONE_CODES:
        return 0
    process_x_axes = {
        coordinate
        for process_code in MAIN_PROCESS_ZONE_CODES
        if process_code in placed
        for coordinate in (_bounds(placed[process_code])[0], _bounds(placed[process_code])[2])
    }
    process_y_axes = {
        coordinate
        for process_code in MAIN_PROCESS_ZONE_CODES
        if process_code in placed
        for coordinate in (_bounds(placed[process_code])[1], _bounds(placed[process_code])[3])
    }
    left, bottom, right, top = _bounds(rectangle)
    return sum(coordinate in process_x_axes for coordinate in (left, right)) + sum(
        coordinate in process_y_axes for coordinate in (bottom, top)
    )


def _linear_flow_anchor_matches(
    rectangle: PlacedRectangleV1,
    predecessor: PlacedRectangleV1,
    family: StructuralCompositionFamilyV1,
) -> bool:
    first = _bounds(predecessor)
    second = _bounds(rectangle)
    if family.dominant_axis == "X":
        if not (first[2] == second[0] or second[2] == first[0]):
            return False
        if min(first[3], second[3]) <= max(first[1], second[1]):
            return False
        delta = second[0] + second[2] - first[0] - first[2]
    else:
        if not (first[3] == second[1] or second[3] == first[1]):
            return False
        if min(first[2], second[2]) <= max(first[0], second[0]):
            return False
        delta = second[1] + second[3] - first[1] - first[3]
    return (delta > 0 and family.dominant_direction == "POSITIVE") or (
        delta < 0 and family.dominant_direction == "NEGATIVE"
    )


def _rectangle_touches_boundary(rectangle: PlacedRectangleV1, boundary: PolygonMM) -> bool:
    left, bottom, right, top = _bounds(rectangle)
    rectangle_edges = (
        ((left, bottom), (right, bottom)),
        ((right, bottom), (right, top)),
        ((right, top), (left, top)),
        ((left, top), (left, bottom)),
    )
    for site_start, site_end in zip(boundary, boundary[1:] + boundary[:1], strict=True):
        for room_start, room_end in rectangle_edges:
            if segments_share_positive_length(site_start, site_end, room_start, room_end):
                return True
    return False


def _cross(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int]) -> int:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> bool:
    return (
        _cross(start, end, point) == 0
        and min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
        and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
    )


def _segments_intersect(
    first_start: tuple[int, int],
    first_end: tuple[int, int],
    second_start: tuple[int, int],
    second_end: tuple[int, int],
) -> bool:
    first_a = _cross(first_start, first_end, second_start)
    first_b = _cross(first_start, first_end, second_end)
    second_a = _cross(second_start, second_end, first_start)
    second_b = _cross(second_start, second_end, first_end)
    return (
        ((first_a > 0 > first_b) or (first_a < 0 < first_b))
        and ((second_a > 0 > second_b) or (second_a < 0 < second_b))
    ) or (
        (first_a == 0 and _on_segment(second_start, first_start, first_end))
        or (first_b == 0 and _on_segment(second_end, first_start, first_end))
        or (second_a == 0 and _on_segment(first_start, second_start, second_end))
        or (second_b == 0 and _on_segment(first_end, second_start, second_end))
    )


def _point_segment_distance_squared(
    point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]
) -> Fraction:
    vector_x = end[0] - start[0]
    vector_y = end[1] - start[1]
    length_squared = vector_x * vector_x + vector_y * vector_y
    if length_squared == 0:
        return Fraction((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2)
    offset_x = point[0] - start[0]
    offset_y = point[1] - start[1]
    projection = Fraction(offset_x * vector_x + offset_y * vector_y, length_squared)
    projection = max(Fraction(0), min(Fraction(1), projection))
    delta_x = Fraction(point[0]) - (Fraction(start[0]) + projection * vector_x)
    delta_y = Fraction(point[1]) - (Fraction(start[1]) + projection * vector_y)
    return delta_x * delta_x + delta_y * delta_y


def segment_distance_squared(first: SegmentMM, second: SegmentMM) -> Fraction:
    """Exact squared distance in integer-mm units; no sqrt or epsilon."""
    if _segments_intersect(first[0], first[1], second[0], second[1]):
        return Fraction(0)
    return min(
        _point_segment_distance_squared(first[0], second[0], second[1]),
        _point_segment_distance_squared(first[1], second[0], second[1]),
        _point_segment_distance_squared(second[0], first[0], first[1]),
        _point_segment_distance_squared(second[1], first[0], first[1]),
    )


def _long_edges(rectangle: PlacedRectangleV1) -> tuple[tuple[str, SegmentMM], ...]:
    left, bottom, right, top = _bounds(rectangle)
    width_mm = _mm(rectangle.width_m, field="width_m", positive=True)
    depth_mm = _mm(rectangle.depth_m, field="depth_m", positive=True)
    width_is_long = width_mm >= depth_mm
    horizontal_long_edges = (width_is_long and rectangle.rotation_deg == 0) or (
        not width_is_long and rectangle.rotation_deg == 90
    )
    if horizontal_long_edges:
        return (
            ("BOTTOM_LONG_EDGE", ((left, bottom), (right, bottom))),
            ("TOP_LONG_EDGE", ((left, top), (right, top))),
        )
    return (
        ("LEFT_LONG_EDGE", ((left, bottom), (left, top))),
        ("RIGHT_LONG_EDGE", ((right, bottom), (right, top))),
    )


def _truck_segment(site_body: Mapping[str, Any]) -> SegmentMM:
    entrances = site_body.get("entrances")
    if not isinstance(entrances, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="entrances")
    value = entrances.get("truck_entrance")
    if not isinstance(value, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="truck_entrance")
    try:
        numeric = {
            "start": {
                "x": Decimal(str(value["start"]["x"])),
                "y": Decimal(str(value["start"]["y"])),
            },
            "end": {
                "x": Decimal(str(value["end"]["x"])),
                "y": Decimal(str(value["end"]["y"])),
            },
        }
    except (KeyError, TypeError, InvalidOperation, ValueError):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="truck_entrance") from None
    return normalize_segment(numeric, error_code="INVALID_SITE_GEOMETRY_RESULT")


def _main_entrance_segment(site_body: Mapping[str, Any]) -> SegmentMM:
    entrances = site_body.get("entrances")
    if not isinstance(entrances, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="entrances")
    value = entrances.get("main_entrance")
    if not isinstance(value, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="main_entrance")
    try:
        numeric = {
            "start": {
                "x": Decimal(str(value["start"]["x"])),
                "y": Decimal(str(value["start"]["y"])),
            },
            "end": {
                "x": Decimal(str(value["end"]["x"])),
                "y": Decimal(str(value["end"]["y"])),
            },
        }
    except (KeyError, TypeError, InvalidOperation, ValueError):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="main_entrance") from None
    return normalize_segment(numeric, error_code="INVALID_SITE_GEOMETRY_RESULT")


def _loading_face(
    rectangle: PlacedRectangleV1, site_body: Mapping[str, Any]
) -> tuple[str, SegmentMM, dict[str, Any], tuple[Any, ...]]:
    preferred = site_body.get("site", {}).get("preferred_loading_side", "UNSPECIFIED")
    edges = _long_edges(rectangle)
    if not isinstance(preferred, str):
        raise _error("INVALID_LOADING_SIDE")
    comparison: tuple[Any, ...]
    if preferred in {"NORTH", "EAST", "SOUTH", "WEST"}:
        side_by_cardinal = {
            "BOTTOM_LONG_EDGE": "SOUTH",
            "TOP_LONG_EDGE": "NORTH",
            "LEFT_LONG_EDGE": "WEST",
            "RIGHT_LONG_EDGE": "EAST",
        }
        matching = [row for row in edges if side_by_cardinal[row[0]] == preferred]
        selected = matching[0] if matching else edges[0]
        score = {"mode": CARDINAL_LOADING_SIDE_METRIC, "match": bool(matching)}
        comparison = (1 if matching else 0,)
    elif preferred == "NEAREST_TRUCK_ENTRANCE":
        truck = _truck_segment(site_body)
        selected = min(
            edges,
            key=lambda row: (segment_distance_squared(row[1], truck), row[0]),
        )
        distance = segment_distance_squared(selected[1], truck)
        score = {
            "mode": "MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE",
            "distance_squared_mm2": str(distance),
            "comparator": NEAREST_TRUCK_ENTRANCE_COMPARATOR,
            "internal_unit": NEAREST_TRUCK_ENTRANCE_INTERNAL_UNIT,
        }
        comparison = (-distance,)
    elif preferred == "UNSPECIFIED":
        selected = edges[0]
        score = {"mode": "DISABLED"}
        comparison = ()
    else:
        raise _error("INVALID_LOADING_SIDE")
    return selected[0], selected[1], score, comparison


def _pair_rows(
    pairs: Sequence[tuple[str, str]], placed: Mapping[str, PlacedRectangleV1]
) -> tuple[list[list[str]], list[list[str]]]:
    satisfied: list[list[str]] = []
    unsatisfied: list[list[str]] = []
    for pair in pairs:
        row = [pair[0], pair[1]]
        if rectangles_share_positive_edge(placed[pair[0]], placed[pair[1]]):
            satisfied.append(row)
        else:
            unsatisfied.append(row)
    return satisfied, unsatisfied


def _zone_record(authority: Mapping[str, Any], rectangle: PlacedRectangleV1) -> dict[str, Any]:
    code = _authority_code(authority)
    mode = _authority_mode(authority)
    required = _required_area(authority)
    if mode == "FLEXIBLE_RECTANGLE":
        if rectangle.actual_area_m2 < required:
            raise _error("FLEXIBLE_DIMENSION_AREA_UNSATISFIED", zone_code=code)
    else:
        geometry = authority.get("geometry")
        if not isinstance(geometry, Mapping):
            raise _error("DIMENSION_AUTHORITY_REQUIRED", zone_code=code)
        if _mm(geometry.get("width_m"), field="width_m", positive=True) != _mm(
            rectangle.width_m, field="width_m", positive=True
        ) or _mm(geometry.get("depth_m"), field="depth_m", positive=True) != _mm(
            rectangle.depth_m, field="depth_m", positive=True
        ):
            raise _error("FIXED_DIMENSION_RESIZE_FORBIDDEN", zone_code=code)
    return {
        "zone_code": code,
        "dimension_mode": mode,
        "required_area_m2": required,
        "x": rectangle.x,
        "y": rectangle.y,
        "width_m": rectangle.width_m,
        "depth_m": rectangle.depth_m,
        "actual_area_m2": rectangle.actual_area_m2,
        "rotation_deg": rectangle.rotation_deg,
        "dimension_authority_identity": authority.get("dimension_authority_identity"),
        "dimensioning_authority": authority.get("authority", "P1_PROJECT_HANDOFF"),
        "capacity_geometry_reference": authority.get("source_zone_hash"),
        "area_requirement": authority.get("area_requirement"),
    }


def _rectangle_edge_segments(
    rectangle: PlacedRectangleV1,
) -> dict[str, tuple[SegmentMM, ...]]:
    """Return relative long/short edge classes for observable evidence only."""
    left, bottom, right, top = _bounds(rectangle)
    width_mm = _mm(rectangle.width_m, field="width_m", positive=True)
    depth_mm = _mm(rectangle.depth_m, field="depth_m", positive=True)
    width_is_long = width_mm >= depth_mm
    horizontal_long_edges = (width_is_long and rectangle.rotation_deg == 0) or (
        not width_is_long and rectangle.rotation_deg == 90
    )
    horizontal = (
        ((left, bottom), (right, bottom)),
        ((left, top), (right, top)),
    )
    vertical = (
        ((left, bottom), (left, top)),
        ((right, bottom), (right, top)),
    )
    if horizontal_long_edges:
        return {"LONG_EDGE": horizontal, "SHORT_EDGE": vertical}
    return {"LONG_EDGE": vertical, "SHORT_EDGE": horizontal}


def _segment_overlap_length_mm(first: SegmentMM, second: SegmentMM) -> int:
    if first[0][1] == first[1][1] == second[0][1] == second[1][1]:
        return max(0, min(first[1][0], second[1][0]) - max(first[0][0], second[0][0]))
    if first[0][0] == first[1][0] == second[0][0] == second[1][0]:
        return max(0, min(first[1][1], second[1][1]) - max(first[0][1], second[0][1]))
    return 0


def _edge_orientation_facts(
    requirement: Mapping[str, Any],
    relationship: Mapping[str, Any] | None,
    placed: Mapping[str, PlacedRectangleV1],
) -> dict[str, Any]:
    """Observe P1 edge classes without validating a route or portal."""
    facts: dict[str, Any] = {
        "edge_orientation_observable": False,
        "edge_orientation_satisfied": None,
        "required_edge_orientation_observable": False,
        "required_edge_orientation_satisfied": None,
    }
    if relationship is None:
        return facts
    from_ref = requirement.get("from_ref")
    to_ref = requirement.get("to_ref")
    from_rectangle = placed.get(from_ref) if isinstance(from_ref, str) else None
    to_rectangle = placed.get(to_ref) if isinstance(to_ref, str) else None
    if from_rectangle is None or to_rectangle is None:
        return facts
    expected_from = relationship.get("from_edge_class")
    expected_to = relationship.get("to_edge_class")
    facts["edge_orientation_contract"] = {
        "identity": relationship.get("identity"),
        "from_edge_class": expected_from,
        "to_edge_class": expected_to,
    }
    matched: list[dict[str, Any]] = []
    from_edges = _rectangle_edge_segments(from_rectangle)
    to_edges = _rectangle_edge_segments(to_rectangle)
    for from_class, from_segments in from_edges.items():
        for to_class, to_segments in to_edges.items():
            for from_segment in from_segments:
                for to_segment in to_segments:
                    overlap = _segment_overlap_length_mm(from_segment, to_segment)
                    if overlap > 0 and segments_share_positive_length(
                        from_segment[0], from_segment[1], to_segment[0], to_segment[1]
                    ):
                        matched.append(
                            {
                                "from_edge_class": from_class,
                                "to_edge_class": to_class,
                                "shared_positive_edge_length_mm": overlap,
                            }
                        )
    facts["edge_orientation_observable"] = bool(matched)
    facts["edge_orientation_matches"] = matched
    facts["edge_orientation_satisfied"] = any(
        row["from_edge_class"] == expected_from
        and (
            row["to_edge_class"] == expected_to
            or (expected_to == "SHORT_EDGE_EXIT_SIDE" and row["to_edge_class"] == "SHORT_EDGE")
            or (expected_to == "LONG_EDGE_LOADING_FACE" and row["to_edge_class"] == "LONG_EDGE")
        )
        for row in matched
    )
    facts["required_edge_orientation_observable"] = facts["edge_orientation_observable"]
    facts["required_edge_orientation_satisfied"] = facts["edge_orientation_satisfied"]
    return facts


def _access_observations(
    access_requirements: Sequence[Mapping[str, Any]],
    spatial_relationships: Sequence[Mapping[str, Any]],
    placed: Mapping[str, PlacedRectangleV1],
    loading_face: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    relationships = {
        relationship.get("identity"): relationship
        for relationship in spatial_relationships
        if isinstance(relationship, Mapping) and isinstance(relationship.get("identity"), str)
    }
    preserved_fields = (
        "identity",
        "from_ref",
        "to_ref",
        "flow_kind",
        "access_class",
        "profile_identity",
        "portal_required",
        "corridor_allowed",
        "direct_allowed",
        "edge_orientation_requirement",
        "route_shape_constraint",
        "cold_room_refs",
        "cold_room_portal_profile_identity",
        "source_authority",
    )
    for requirement in access_requirements:
        from_ref = requirement.get("from_ref")
        to_ref = requirement.get("to_ref")
        from_rectangle = placed.get(from_ref) if isinstance(from_ref, str) else None
        to_rectangle = placed.get(to_ref) if isinstance(to_ref, str) else None
        shared = bool(
            from_rectangle is not None
            and to_rectangle is not None
            and rectangles_share_positive_edge(from_rectangle, to_rectangle)
        )
        facts: dict[str, Any] = {
            "direct_shared_edge_observed": shared,
            "shared_positive_edge_length_mm": 0,
        }
        if from_rectangle is not None and to_rectangle is not None:
            from_edges = _rectangle_edge_segments(from_rectangle)
            to_edges = _rectangle_edge_segments(to_rectangle)
            facts["shared_positive_edge_length_mm"] = max(
                (
                    _segment_overlap_length_mm(first, second)
                    for first_segments in from_edges.values()
                    for first in first_segments
                    for second_segments in to_edges.values()
                    for second in second_segments
                ),
                default=0,
            )
        requirement_identity = requirement.get("identity")
        relationship = relationships.get(requirement.get("edge_orientation_requirement"))
        if requirement.get("edge_orientation_requirement") is not None:
            facts.update(_edge_orientation_facts(requirement, relationship, placed))
        if from_ref == "truck_entrance":
            facts.update(
                {
                    "shipping_loading_face_selected": loading_face["side"],
                    "shipping_loading_face_segment_observed": True,
                    "shipping_loading_face_segment": {
                        "start": {
                            "x": _m(loading_face["segment"][0][0]),
                            "y": _m(loading_face["segment"][0][1]),
                        },
                        "end": {
                            "x": _m(loading_face["segment"][1][0]),
                            "y": _m(loading_face["segment"][1][1]),
                        },
                    },
                }
            )
        rows.append(
            {
                "observation_id": requirement_identity,
                "requirement_identity": requirement_identity,
                **{field: requirement[field] for field in preserved_fields if field in requirement},
                "status": "PENDING_ROUTE_VALIDATION",
                "observable_facts": facts,
            }
        )
    return sorted(rows, key=lambda row: (row["from_ref"], row["to_ref"], row["flow_kind"]))


def _candidate_payload(
    placed: Mapping[str, PlacedRectangleV1],
    authorities: Mapping[str, Mapping[str, Any]],
    graph: AdjacencyGraphV1,
    site_body: Mapping[str, Any],
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    source_objective_profile_hash: str,
    access_requirements: Sequence[Mapping[str, Any]],
    spatial_relationships: Sequence[Mapping[str, Any]],
    search_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    zones = [_zone_record(authorities[code], placed[code]) for code in sorted(placed)]
    must_satisfied, must_unsatisfied = _pair_rows(graph.must_adjacencies, placed)
    should_satisfied, should_unsatisfied = _pair_rows(graph.should_adjacencies, placed)
    shipping_side, shipping_segment, loading_score, loading_comparison = _loading_face(
        placed["shipping_channel"], site_body
    )
    preferred = site_body["site"]["preferred_loading_side"]
    objective_vector: dict[str, Any] = {
        "aggregation": "LEXICOGRAPHIC",
        "priority_order": [SHOULD_ADJACENT, LOADING_SIDE_PREFERENCE],
        "should_adjacency": {
            "satisfied_count": len(should_satisfied),
            "total_count": len(graph.should_adjacencies),
            "satisfied_pairs": should_satisfied,
            "unsatisfied_pairs": should_unsatisfied,
        },
        "loading_side": {
            "preferred_loading_side": preferred,
            **loading_score,
        },
    }
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "placement_result_identity": PLACEMENT_RESULT_IDENTITY,
        "source_zone_plan_hash": source_zone_plan_hash,
        "source_p1_handoff_hash": source_p1_handoff_hash,
        "source_site_geometry_hash": source_site_geometry_hash,
        "source_objective_profile_hash": source_objective_profile_hash,
        "zone_count": len(zones),
        "placement_access_requirement_count": len(access_requirements),
        "zones": zones,
        "shipping_loading_face_side": shipping_side,
        "shipping_loading_face_segment": {
            "start": {"x": _m(shipping_segment[0][0]), "y": _m(shipping_segment[0][1])},
            "end": {"x": _m(shipping_segment[1][0]), "y": _m(shipping_segment[1][1])},
        },
        "must_adjacency_evaluation": {
            "hard_constraints_passed": not must_unsatisfied,
            "satisfied_count": len(must_satisfied),
            "required_count": len(graph.must_adjacencies),
            "satisfied_pairs": must_satisfied,
            "violations": [
                {"code": "HARD_CONSTRAINT_UNSATISFIABLE", "zones": pair}
                for pair in must_unsatisfied
            ],
        },
        "placement_hard_constraints_passed": not must_unsatisfied,
        "should_adjacency_evaluation": {
            "satisfied_count": len(should_satisfied),
            "required_count": len(graph.should_adjacencies),
            "satisfied_pairs": should_satisfied,
            "unsatisfied_pairs": should_unsatisfied,
        },
        "placement_access_observations": _access_observations(
            access_requirements,
            spatial_relationships,
            placed,
            {"side": shipping_side, "segment": shipping_segment},
        ),
        "placement_objective_vector": objective_vector,
        "search_provenance": dict(search_provenance),
    }
    # Keep this local variable in the payload construction so the exact
    # comparator input is explicit and never confused with the candidate hash.
    candidate["_loading_comparison"] = list(loading_comparison)
    return candidate


def _is_better(
    candidate: Mapping[str, Any], best: Mapping[str, Any] | None, preferred_loading_side: str
) -> bool:
    if best is None:
        return True
    candidate_vector = candidate["placement_objective_vector"]
    best_vector = best["placement_objective_vector"]
    candidate_should = int(candidate_vector["should_adjacency"]["satisfied_count"])
    best_should = int(best_vector["should_adjacency"]["satisfied_count"])
    if candidate_should != best_should:
        return candidate_should > best_should
    if preferred_loading_side in {"NORTH", "EAST", "SOUTH", "WEST"}:
        candidate_match = bool(candidate_vector["loading_side"].get("match"))
        best_match = bool(best_vector["loading_side"].get("match"))
        if candidate_match != best_match:
            return candidate_match
    elif preferred_loading_side == "NEAREST_TRUCK_ENTRANCE":
        candidate_distance = Fraction(str(candidate_vector["loading_side"]["distance_squared_mm2"]))
        best_distance = Fraction(str(best_vector["loading_side"]["distance_squared_mm2"]))
        if candidate_distance != best_distance:
            return candidate_distance < best_distance
    candidate_json = canonical_json(
        {
            k: v
            for k, v in candidate.items()
            if k
            not in {
                "_loading_comparison",
                "search_provenance",
                "canonical_candidate_hash",
                "canonical_result_hash",
                "_structural_generation_flag",
                "_structural_composition_family",
            }
        }
    )
    best_json = canonical_json(
        {
            k: v
            for k, v in best.items()
            if k
            not in {
                "_loading_comparison",
                "search_provenance",
                "canonical_candidate_hash",
                "canonical_result_hash",
                "_structural_generation_flag",
                "_structural_composition_family",
            }
        }
    )
    return candidate_json < best_json


def _validate_graph_completeness(
    graph: AdjacencyGraphV1, placed: Mapping[str, PlacedRectangleV1]
) -> None:
    if set(placed) != set(graph.nodes):
        raise _error("PLACEMENT_ZONE_SET_INCOMPLETE")
    must_satisfied, must_unsatisfied = _pair_rows(graph.must_adjacencies, placed)
    if must_unsatisfied:
        raise _error(
            "HARD_CONSTRAINT_UNSATISFIABLE",
            unsatisfied_pairs=must_unsatisfied,
            satisfied_count=len(must_satisfied),
        )


@dataclass(frozen=True)
class _PlacementSearchContext:
    authorities: Mapping[str, Mapping[str, Any]]
    site_body: Mapping[str, Any]
    graph: AdjacencyGraphV1
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    objective_profile_hash: str
    access_requirements: tuple[Mapping[str, Any], ...]
    spatial_relationships: tuple[Mapping[str, Any], ...]
    node_budget: int
    complete_candidate_limit: int | None
    boundary: PolygonMM
    boundary_bounds: tuple[int, int, int, int]
    main_entrance: SegmentMM
    obstacles: tuple[PolygonMM, ...]
    preferred_loading_side: str
    structural_composition_family: StructuralCompositionFamilyV1


@dataclass
class _PlacementSearchStats:
    visited_nodes: int = 0
    generated_candidates: int = 0
    complete_candidates: int = 0
    node_budget_exhausted: bool = False


def _validated_search_context(
    authorities: Mapping[str, Mapping[str, Any]],
    site_body: Mapping[str, Any],
    graph: AdjacencyGraphV1,
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    objective_profile_hash: str | None,
    access_requirements: Sequence[Mapping[str, Any]],
    spatial_relationships: Sequence[Mapping[str, Any]],
    node_budget: int,
    complete_candidate_limit: int | None,
) -> _PlacementSearchContext:
    if set(authorities) != set(graph.nodes) or tuple(PLACEMENT_ZONE_ORDER) != tuple(
        code for code in PLACEMENT_ZONE_ORDER if code in graph.nodes
    ):
        raise _error("PLACEMENT_ZONE_AUTHORITY_SET_INVALID")
    if len(access_requirements) != 12:
        raise _error(
            "P1_ACCESS_REQUIREMENTS_INVALID",
            expected_count=12,
            actual_count=len(access_requirements),
        )
    if node_budget <= 0 or (complete_candidate_limit is not None and complete_candidate_limit <= 0):
        raise _error("INVALID_PLACEMENT_SEARCH_BUDGET")
    site = site_body.get("site")
    obstacles_body = site_body.get("obstacles")
    entrances_body = site_body.get("entrances")
    if (
        not isinstance(site, Mapping)
        or not isinstance(obstacles_body, Mapping)
        or not isinstance(entrances_body, Mapping)
    ):
        raise _error("INVALID_SITE_GEOMETRY_RESULT")
    boundary = _polygon(site.get("effective_buildable_boundary"))
    boundary_bounds = _boundary_extents(boundary)
    main_entrance = _main_entrance_segment(site_body)
    raw_obstacles = obstacles_body.get("hard_obstacles", [])
    if not isinstance(raw_obstacles, list):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="hard_obstacles")
    obstacles = tuple(
        _polygon(row["footprint"])
        for row in raw_obstacles
        if isinstance(row, Mapping) and "footprint" in row
    )
    preferred = site.get("preferred_loading_side", "UNSPECIFIED")
    if not isinstance(preferred, str):
        raise _error("INVALID_LOADING_SIDE")
    structural_family = select_structural_composition_family(site_body, authorities)
    return _PlacementSearchContext(
        authorities=authorities,
        site_body=site_body,
        graph=graph,
        source_zone_plan_hash=source_zone_plan_hash,
        source_p1_handoff_hash=source_p1_handoff_hash,
        source_site_geometry_hash=source_site_geometry_hash,
        objective_profile_hash=objective_profile_hash
        or canonical_hash(approved_objective_profile().to_dict()),
        access_requirements=tuple(access_requirements),
        spatial_relationships=tuple(spatial_relationships),
        node_budget=node_budget,
        complete_candidate_limit=complete_candidate_limit,
        boundary=boundary,
        boundary_bounds=boundary_bounds,
        main_entrance=main_entrance,
        obstacles=obstacles,
        preferred_loading_side=preferred,
        structural_composition_family=structural_family,
    )


def _search_provenance(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
    *,
    search_tree_exhausted: bool,
    objective_optimal_within_search_family: bool,
) -> dict[str, Any]:
    return {
        "search_profile_identity": SEARCH_PROFILE_IDENTITY,
        "node_budget": context.node_budget,
        "complete_candidate_limit": context.complete_candidate_limit,
        "complete_candidate_limit_stops_search": False,
        "visited_nodes": stats.visited_nodes,
        "generated_candidates": stats.generated_candidates,
        "complete_candidates": stats.complete_candidates,
        "budget_exhausted": stats.node_budget_exhausted,
        "node_budget_exhausted": stats.node_budget_exhausted,
        "search_tree_exhausted": search_tree_exhausted,
        "objective_optimal_within_search_family": objective_optimal_within_search_family,
        "node_budget_is_only_search_cutoff": True,
        "candidate_family": "STRUCTURED_GROUP_BAND_ZONE_V1_WITH_GENERAL_FALLBACK",
        "structural_composition_identity": "structural-composition-family@1.0.0",
    }


def _walk_complete_candidate_payloads(
    context: _PlacementSearchContext, stats: _PlacementSearchStats
) -> Iterator[dict[str, Any]]:
    """Yield every complete P2C candidate until the node budget is exhausted."""
    placed: dict[str, PlacedRectangleV1] = {}

    def visit(index: int, structurally_generated: bool) -> Iterator[dict[str, Any]]:
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            return
        stats.visited_nodes += 1
        if index == len(PLACEMENT_ZONE_ORDER):
            _validate_graph_completeness(context.graph, placed)
            stats.complete_candidates += 1
            payload = _candidate_payload(
                placed,
                context.authorities,
                context.graph,
                context.site_body,
                context.source_zone_plan_hash,
                context.source_p1_handoff_hash,
                context.source_site_geometry_hash,
                context.objective_profile_hash,
                context.access_requirements,
                context.spatial_relationships,
                _search_provenance(
                    context,
                    stats,
                    search_tree_exhausted=False,
                    objective_optimal_within_search_family=False,
                ),
            )
            payload["_structural_generation_flag"] = structurally_generated
            payload["_structural_composition_family"] = (
                context.structural_composition_family.to_dict()
            )
            yield payload
            return
        code = PLACEMENT_ZONE_ORDER[index]
        options = _candidate_options(
            code,
            context.authorities[code],
            placed,
            context.boundary,
            context.boundary_bounds,
            context.obstacles,
            context.graph,
            context.structural_composition_family,
            context.main_entrance,
        )
        stats.generated_candidates += len(options)
        for rectangle in options:
            structural_refs = structural_anchor_references(code, tuple(placed))
            if code == "raw_fruit_buffer":
                anchored = _rectangle_touches_boundary(rectangle, context.boundary)
            elif (
                context.structural_composition_family.family == "LINEAR_PROCESS_BAND"
                and code in MAIN_PROCESS_PREDECESSOR
            ):
                predecessor = placed.get(MAIN_PROCESS_PREDECESSOR[code])
                anchored = predecessor is not None and _linear_flow_anchor_matches(
                    rectangle, predecessor, context.structural_composition_family
                )
            else:
                anchored = any(
                    rectangles_share_positive_edge(rectangle, placed[reference])
                    for reference in structural_refs
                )
            placed[code] = rectangle
            yield from visit(index + 1, structurally_generated and anchored)
            placed.pop(code)
            if stats.node_budget_exhausted:
                return

    yield from visit(0, True)


def _materialize_candidate_result(
    payload: Mapping[str, Any], *, provenance: Mapping[str, Any] | None = None
) -> SitePlacementResultV1:
    content = dict(payload)
    content.pop("_loading_comparison", None)
    content.pop("_structural_generation_flag", None)
    content.pop("_structural_composition_family", None)
    if provenance is not None:
        content["search_provenance"] = dict(provenance)
    content.setdefault("placement_engine_identity", IDENTITY)
    content.setdefault("search_profile_identity", SEARCH_PROFILE_IDENTITY)
    content.setdefault("status", "PLACEMENT_FOUND")
    content.setdefault("placement_available", True)
    content.setdefault("placement_hard_constraints_passed", True)
    content.setdefault("routing_validated", False)
    content.setdefault("access_route_validated", False)
    content.setdefault("truck_route_validated", False)
    content.setdefault("project_layout_validated", False)
    content.setdefault("p2_complete", False)
    content.setdefault("layout_infeasible_proof_implemented", False)
    content.setdefault("requires_review", True)
    candidate = PlacementCandidateV1.from_payload(content)
    content["canonical_candidate_hash"] = candidate.canonical_candidate_hash
    return SitePlacementResultV1.from_payload(content)


class PlacementCandidateEnumerationV1:
    """One-shot deterministic stream of complete, P2C-ranked candidates.

    The stream retains no complete-candidate list.  Callers compare each
    materialized candidate and may discard it before requesting the next one.
    ``complete_candidate_limit`` is accepted for compatibility and evidence,
    but never terminates this stream.
    """

    def __init__(self, context: _PlacementSearchContext) -> None:
        self._context = context
        self._stats = _PlacementSearchStats()
        self._started = False
        self._finished = False
        self._structural_flags: dict[str, bool] = {}

    def iter_candidates(self) -> Iterator[SitePlacementResultV1]:
        if self._started:
            raise RuntimeError("placement candidate enumeration is one-shot")
        self._started = True
        iterator = _walk_complete_candidate_payloads(self._context, self._stats)
        while True:
            try:
                payload = next(iterator)
            except StopIteration:
                self._finished = True
                return
            structural_flag = payload.get("_structural_generation_flag") is True
            candidate = _materialize_candidate_result(payload)
            candidate_hash = candidate.to_dict().get("canonical_candidate_hash")
            if isinstance(candidate_hash, str):
                self._structural_flags[candidate_hash] = structural_flag
            yield candidate

    @property
    def completed(self) -> bool:
        return self._finished

    @property
    def candidate_count(self) -> int:
        return self._stats.complete_candidates

    @property
    def generated_candidate_count(self) -> int:
        return self._stats.generated_candidates

    @property
    def visited_node_count(self) -> int:
        return self._stats.visited_nodes

    @property
    def search_tree_exhausted(self) -> bool:
        return self.completed and not self._stats.node_budget_exhausted

    @property
    def node_budget_exhausted(self) -> bool:
        return self._stats.node_budget_exhausted

    @property
    def provenance(self) -> dict[str, Any]:
        return _search_provenance(
            self._context,
            self._stats,
            search_tree_exhausted=self.search_tree_exhausted,
            objective_optimal_within_search_family=self.search_tree_exhausted,
        )

    @property
    def structural_composition_family(self) -> StructuralCompositionFamilyV1:
        return self._context.structural_composition_family

    def structurally_generated(self, candidate_hash: str) -> bool:
        """Report whether every assigned zone used a group/band anchor."""
        return self._structural_flags.get(candidate_hash, False)


def enumerate_placement_candidates(
    authorities: Mapping[str, Mapping[str, Any]],
    site_body: Mapping[str, Any],
    graph: AdjacencyGraphV1,
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    objective_profile_hash: str | None = None,
    access_requirements: Sequence[Mapping[str, Any]] = (),
    spatial_relationships: Sequence[Mapping[str, Any]] = (),
    node_budget: int = DEFAULT_NODE_BUDGET,
    complete_candidate_limit: int | None = None,
) -> PlacementCandidateEnumerationV1:
    """Expose the same validated P2C search family as a lazy candidate stream."""
    return PlacementCandidateEnumerationV1(
        _validated_search_context(
            authorities,
            site_body,
            graph,
            source_zone_plan_hash=source_zone_plan_hash,
            source_p1_handoff_hash=source_p1_handoff_hash,
            source_site_geometry_hash=source_site_geometry_hash,
            objective_profile_hash=objective_profile_hash,
            access_requirements=access_requirements,
            spatial_relationships=spatial_relationships,
            node_budget=node_budget,
            complete_candidate_limit=complete_candidate_limit,
        )
    )


def placement_candidate_is_better(
    candidate: Mapping[str, Any], best: Mapping[str, Any] | None, preferred_loading_side: str
) -> bool:
    """Apply the existing P2B2 objective comparator to one P2C candidate."""
    return _is_better(candidate, best, preferred_loading_side)


def search_placement(
    authorities: Mapping[str, Mapping[str, Any]],
    site_body: Mapping[str, Any],
    graph: AdjacencyGraphV1,
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    objective_profile_hash: str | None = None,
    access_requirements: Sequence[Mapping[str, Any]] = (),
    spatial_relationships: Sequence[Mapping[str, Any]] = (),
    node_budget: int = DEFAULT_NODE_BUDGET,
    complete_candidate_limit: int | None = None,
) -> SitePlacementResultV1:
    """Search a finite candidate family and return found/exhausted semantics.

    This search is intentionally incomplete.  A bounded search that finds no
    candidate returns ``LAYOUT_SEARCH_EXHAUSTED`` rather than claiming a proof
    of infeasibility.
    """
    context = _validated_search_context(
        authorities,
        site_body,
        graph,
        source_zone_plan_hash=source_zone_plan_hash,
        source_p1_handoff_hash=source_p1_handoff_hash,
        source_site_geometry_hash=source_site_geometry_hash,
        objective_profile_hash=objective_profile_hash,
        access_requirements=access_requirements,
        spatial_relationships=spatial_relationships,
        node_budget=node_budget,
        complete_candidate_limit=complete_candidate_limit,
    )
    stats = _PlacementSearchStats()
    best_payload: dict[str, Any] | None = None
    for payload in _walk_complete_candidate_payloads(context, stats):
        if _is_better(payload, best_payload, context.preferred_loading_side):
            best_payload = payload
    search_tree_exhausted = not stats.node_budget_exhausted
    objective_optimal_within_search_family = best_payload is not None and search_tree_exhausted
    provenance = _search_provenance(
        context,
        stats,
        search_tree_exhausted=search_tree_exhausted,
        objective_optimal_within_search_family=objective_optimal_within_search_family,
    )

    if best_payload is None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "placement_result_identity": PLACEMENT_RESULT_IDENTITY,
            "placement_engine_identity": IDENTITY,
            "search_profile_identity": SEARCH_PROFILE_IDENTITY,
            "status": "LAYOUT_SEARCH_EXHAUSTED",
            "placement_available": False,
            "placement_hard_constraints_passed": False,
            "zone_count": 0,
            "source_zone_plan_hash": context.source_zone_plan_hash,
            "source_p1_handoff_hash": context.source_p1_handoff_hash,
            "source_site_geometry_hash": context.source_site_geometry_hash,
            "source_objective_profile_hash": context.objective_profile_hash,
            "placement_access_requirement_count": len(access_requirements),
            "search_provenance": provenance,
            "routing_validated": False,
            "access_route_validated": False,
            "truck_route_validated": False,
            "project_layout_validated": False,
            "p2_complete": False,
            "layout_infeasible_proof_implemented": False,
            "requires_review": True,
            "warnings": [
                (
                    "Search budget exhausted before a placement was found; "
                    "this is not an infeasibility proof."
                    if stats.node_budget_exhausted
                    else (
                        "Finite placement candidate family was exhausted; "
                        "this is not an infeasibility proof."
                    )
                )
            ],
        }
        return SitePlacementResultV1.from_payload(payload)

    best_payload.pop("_loading_comparison", None)
    best_payload.pop("_structural_generation_flag", None)
    best_payload.pop("_structural_composition_family", None)
    best_payload["search_provenance"] = provenance
    best_payload["status"] = "PLACEMENT_FOUND"
    best_payload["placement_available"] = True
    best_payload["placement_engine_identity"] = IDENTITY
    best_payload["search_profile_identity"] = SEARCH_PROFILE_IDENTITY
    best_payload["constraint_evaluation"] = {
        "hard_constraints_passed": True,
        "all_zones_inside_effective_buildable_boundary": True,
        "all_hard_obstacles_clear": True,
        "no_interior_zone_overlap": True,
        "must_adjacencies_passed": True,
        "access_status": "PENDING_ROUTE_VALIDATION",
    }
    best_payload["routing_validated"] = False
    best_payload["access_route_validated"] = False
    best_payload["truck_route_validated"] = False
    best_payload["project_layout_validated"] = False
    best_payload["p2_complete"] = False
    best_payload["layout_infeasible_proof_implemented"] = False
    best_payload["requires_review"] = True
    best_payload["warnings"] = [
        (
            "Placement selected by the deterministic objective within the exhausted finite "
            "search family; portal, corridor and truck routes remain unvalidated."
            if search_tree_exhausted
            else "Placement selected among deterministically explored candidates; "
            "search-family optimum is not proven because the search budget was exhausted; "
            "portal, corridor and truck routes remain unvalidated."
        )
    ]
    selected_candidate = PlacementCandidateV1.from_payload(best_payload)
    best_payload["canonical_candidate_hash"] = selected_candidate.canonical_candidate_hash
    return SitePlacementResultV1.from_payload(best_payload)
