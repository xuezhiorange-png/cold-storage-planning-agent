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
    FINISHED_SIDE_GROUP,
    FUNCTIONAL_GROUPS,
    MAIN_PROCESS_SKELETON_ZONE_CODES,
    MAIN_PROCESS_ZONE_CODES,
    PROCESSING_CORE_GROUP,
    RAW_SIDE_GROUP,
    SUPPORT_GROUP,
    StructuralCompositionFamilyV1,
    StructuralSkeletonV1,
    functional_group_for_zone,
    select_structural_composition_family,
    structural_anchor_references,
    structural_skeleton_candidates,
)

IDENTITY: Final = "site-constrained-deterministic-placement@1.0.0"
PLACEMENT_RESULT_IDENTITY: Final = "site_constrained_factory_layout@1.0.0"
SCHEMA_VERSION: Final = "1.0.0"
SEARCH_PROFILE_IDENTITY: Final = "deterministic-placement-search@1.0.0"
GRID_MM: Final = 1
DEFAULT_NODE_BUDGET: Final = 50_000
MAX_OPTIONS_PER_ZONE: Final = 48
STRUCTURED_MAX_OPTIONS_PER_ZONE: Final = 6
STRUCTURED_PHASE: Final = "STRUCTURED"
GENERAL_FALLBACK_PHASE: Final = "GENERAL_FALLBACK"
LEGACY_COMPAT_PHASE: Final = "LEGACY_COMPAT"
# Bound the tail search under one already placed main-process skeleton so the
# deterministic node budget reaches distinct process arrangements before it
# is consumed by office/support permutations. A small fixed sample preserves
# P2D-relevant personnel/support alternatives (notably truck-clear storage
# positions) without treating those variations as new process skeletons.
STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON: Final = 2
# Bound the tail search under a core root, but preserve a small set of
# personnel/support variants for P2D to evaluate against its unchanged access,
# truck, and single-building-footprint authorities.
STRUCTURED_COMPLETIONS_PER_CORE_ROOT: Final = 4

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
STRUCTURED_PLACEMENT_ZONE_ORDER: Final = (
    "sorting_packaging_room",
    "primary_precooling_room",
    "raw_fruit_buffer",
    "secondary_precooling_room",
    # Place the dimensioned transition room first so the flexible coating
    # room can bridge the actual P2C core interfaces instead of guessing a
    # future secondary-precooling rectangle.
    "coating_room",
    "finished_goods_room",
    "shipping_channel",
    # Freeze the complete main-process skeleton, then attach personnel to the
    # project main entrance before peripheral support consumes useful faces.
    "changing_room",
    "office",
    "packaging_material_storage",
    "frozen_fruit_room",
    "secondary_fruit_buffer",
)
LINEAR_STRUCTURED_PLACEMENT_ZONE_ORDER: Final = (
    # A linear lane starts at the raw-side band and grows toward the core and
    # finished side. This is a different search skeleton from the hub lane,
    # not merely another sort order for the same root-first search.
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
    "frozen_fruit_room",
    "secondary_fruit_buffer",
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


def _finished_anchors_for_truck_interface(
    shipping_authority: Mapping[str, Any],
    truck_entrance: SegmentMM,
    boundary: PolygonMM,
    finished_width_mm: int,
    finished_depth_mm: int,
) -> tuple[tuple[int, int], ...]:
    """Derive finished-room anchors that can share the truck-side shipping zone."""
    anchors: set[tuple[int, int]] = set()
    for width_mm, depth_mm, rotation in _dimension_variants(shipping_authority, {}, boundary):
        shipping_width, shipping_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        for x_mm, y_mm in _entrance_anchors(truck_entrance, shipping_width, shipping_depth):
            truck_side_shipping = _rectangle_from_mm(
                "shipping_channel",
                x_mm,
                y_mm,
                width_mm,
                depth_mm,
                rotation,
            )
            anchors.update(_edge_anchors(truck_side_shipping, finished_width_mm, finished_depth_mm))
    return tuple(sorted(anchors))


def _central_core_bridge_anchors(
    sorting: PlacedRectangleV1,
    secondary_authority: Mapping[str, Any],
    *,
    candidate_width_mm: int,
    candidate_depth_mm: int,
    candidate_rotation: int,
    ordering_axis: str,
    boundary: PolygonMM,
) -> tuple[tuple[int, int], ...]:
    """Align the flexible coating core with a dimensioned secondary interface."""
    sort_left, sort_bottom, sort_right, sort_top = _bounds(sorting)
    candidate_x_extent, candidate_y_extent = (
        (candidate_depth_mm, candidate_width_mm)
        if candidate_rotation == 90
        else (candidate_width_mm, candidate_depth_mm)
    )
    secondary_extents: set[int] = set()
    for width_mm, depth_mm, rotation in _dimension_variants(secondary_authority, {}, boundary):
        actual_x, actual_y = (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        secondary_extents.add(actual_x if ordering_axis == "X" else actual_y)

    anchors: set[tuple[int, int]] = set()
    for secondary_extent in secondary_extents:
        if ordering_axis == "Y":
            candidate_y_positions = (
                sort_top + secondary_extent - candidate_y_extent,
                sort_bottom - secondary_extent,
            )
            anchors.update(
                (x, y)
                for y in candidate_y_positions
                for x in (sort_left - candidate_x_extent, sort_right)
            )
        else:
            candidate_x_positions = (
                sort_right + secondary_extent - candidate_x_extent,
                sort_left - secondary_extent,
            )
            anchors.update(
                (x, y)
                for x in candidate_x_positions
                for y in (sort_bottom - candidate_y_extent, sort_top)
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
            # Obstacles are closed. Add exact one-grid-unit inboard anchors so
            # a structured band can preserve a deterministic clearance while
            # sharing the next legal site line.
            xs.update({point[0], point[0] - width_mm, point[0] - width_mm - 1, point[0] + 1})
            ys.update({point[1], point[1] - depth_mm, point[1] - depth_mm - 1, point[1] + 1})
    anchors: set[tuple[int, int]] = {(x, y) for x in xs for y in ys}
    for rectangle in placed.values():
        left, bottom, right, top = _bounds(rectangle)
        xs.update({left - width_mm, left, right - width_mm, right})
        ys.update({bottom - depth_mm, bottom, top - depth_mm, top})
        anchors.update(_edge_anchors(rectangle, width_mm, depth_mm))
    anchors.update((x, y) for x in xs for y in ys)
    return tuple(sorted(anchors))


def _structural_event_anchors(
    placed: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    width_mm: int,
    depth_mm: int,
) -> tuple[tuple[int, int], ...]:
    """Return bounded geometry-event anchors without a Cartesian free-grid."""
    anchors: set[tuple[int, int]] = set()
    for x, y in boundary:
        anchors.update(
            {
                (x, y),
                (x - width_mm, y),
                (x, y - depth_mm),
                (x - width_mm, y - depth_mm),
            }
        )
    for rectangle in placed.values():
        anchors.update(_edge_anchors(rectangle, width_mm, depth_mm))
    for polygon in obstacles:
        for x, y in polygon:
            anchors.update(
                {
                    (x - width_mm - 1, y),
                    (x + 1, y),
                    (x, y - depth_mm - 1),
                    (x, y + 1),
                    (x - width_mm - 1, y - depth_mm - 1),
                    (x + 1, y + 1),
                }
            )
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
    *,
    search_phase: str = LEGACY_COMPAT_PHASE,
    structural_skeleton: StructuralSkeletonV1 | None = None,
    zone_authorities: Mapping[str, Mapping[str, Any]] | None = None,
    truck_entrance: SegmentMM | None = None,
) -> tuple[PlacedRectangleV1, ...]:
    variants = _dimension_variants(authority, placed, boundary)
    options: dict[tuple[int, int, int, int, int], PlacedRectangleV1] = {}
    must_neighbors = _must_neighbors(code, placed, graph)
    structural_refs = structural_anchor_references(code, tuple(placed))
    structural_neighbors = tuple(placed[reference] for reference in structural_refs)
    prioritized_bridge_keys: set[tuple[int, int, int, int, int]] = set()
    prioritized_truck_finished_keys: set[tuple[int, int, int, int, int]] = set()
    for width_mm, depth_mm, rotation in variants:
        anchor_width_mm, anchor_depth_mm = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        if search_phase == STRUCTURED_PHASE:
            legacy_anchors: set[tuple[int, int]] = set()
        elif must_neighbors:
            legacy_anchors = {
                anchor
                for neighbor in must_neighbors
                for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
            }
        else:
            legacy_anchors = set(
                _free_anchors(placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm)
            )
        structural_anchor_neighbors = tuple(
            {
                neighbor.zone_code: neighbor
                for neighbor in (*must_neighbors, *structural_neighbors)
            }.values()
        )
        if structural_anchor_neighbors:
            structural_anchors = {
                anchor
                for neighbor in structural_anchor_neighbors
                for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
            }
        else:
            structural_anchors = set()
        if code == "raw_fruit_buffer":
            # The first raw-side zone has no earlier room anchor; its
            # structured skeleton roots only at exact buildable-boundary
            # anchors, never at the unrestricted legacy site cross-product.
            structural_anchors.update(
                _structural_event_anchors(
                    placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                )
            )
        if code in SUPPORT_ZONE_CODES and search_phase == STRUCTURED_PHASE:
            # Keep support placement within the skeleton search while also
            # admitting exact site/obstacle event positions. A support room
            # can remain edge-attached to the process core at more than one
            # longitudinal offset; using only the room-edge-aligned anchor
            # can hide hard-valid peripheral placements from P2D.
            structural_anchors.update(
                _structural_event_anchors(
                    placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                )
            )
        if code == "sorting_packaging_room" and not placed:
            if search_phase == STRUCTURED_PHASE and structural_skeleton is not None:
                structural_anchors.update(
                    (_mm(x, field="skeleton_root.x"), _mm(y, field="skeleton_root.y"))
                    for x, y, root_rotation in structural_skeleton.root_anchor_candidates
                    if root_rotation == rotation and x >= 0 and y >= 0
                )
                # Root the family at the site's exact boundary/obstacle events
                # as well as the canonical group-derived starts. This is a
                # bounded structural skeleton search, not a legacy free-grid:
                # every admitted room still passes the exact site/no-build
                # predicates and the downstream group-band constraints.
                structural_anchors.update(
                    _structural_event_anchors(
                        placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                    )
                )
            else:
                structural_anchors.update(
                    _free_anchors(placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm)
                )
        if (
            code
            in {
                "coating_room",
                "secondary_precooling_room",
                "primary_precooling_room",
            }
            and placed
        ):
            # Main-flow zones may need to slide along an authoritative shared
            # edge to clear another already-placed process room or a site
            # obstacle. These are bounded geometry-event anchors; mandatory
            # adjacency and the skeleton region predicate below still decide
            # whether a candidate is admitted. They are not legacy free-form
            # options and are never mixed into the structured phase by union.
            structural_anchors.update(
                _structural_event_anchors(
                    placed, boundary, obstacles, anchor_width_mm, anchor_depth_mm
                )
            )
        if (
            code == "coating_room"
            and search_phase == STRUCTURED_PHASE
            and structural_family.family == "CENTRAL_PROCESS_HUB"
            and structural_skeleton is not None
            and "sorting_packaging_room" in placed
        ):
            secondary_authority = (
                zone_authorities.get("secondary_precooling_room")
                if zone_authorities is not None
                else None
            )
            if isinstance(secondary_authority, Mapping):
                bridge_anchors = _central_core_bridge_anchors(
                    placed["sorting_packaging_room"],
                    secondary_authority,
                    candidate_width_mm=width_mm,
                    candidate_depth_mm=depth_mm,
                    candidate_rotation=rotation,
                    ordering_axis=structural_skeleton.ordering_axis,
                    boundary=boundary,
                )
                structural_anchors.update(bridge_anchors)
                prioritized_bridge_keys.update(
                    (x_mm, y_mm, width_mm, depth_mm, rotation) for x_mm, y_mm in bridge_anchors
                )
        if code == "changing_room":
            entrance_anchors = _entrance_anchors(main_entrance, anchor_width_mm, anchor_depth_mm)
            structural_anchors.update(entrance_anchors)
            sorting = placed.get("sorting_packaging_room")
            if sorting is not None:
                core_edge_anchors = _edge_anchors(sorting, anchor_width_mm, anchor_depth_mm)
                # Combine exact entrance-aligned X events with exact core-edge
                # Y events (and vice versa) so a personnel room can bridge
                # both authorities without moving either geometry.
                structural_anchors.update(
                    (entrance_x, core_y)
                    for entrance_x, _entrance_y in entrance_anchors
                    for _core_x, core_y in core_edge_anchors
                )
                structural_anchors.update(
                    (core_x, entrance_y)
                    for _entrance_x, entrance_y in entrance_anchors
                    for core_x, _core_y in core_edge_anchors
                )
        if code == "shipping_channel" and truck_entrance is not None:
            approach_anchors = _entrance_anchors(truck_entrance, anchor_width_mm, anchor_depth_mm)
            structural_anchors.update(approach_anchors)
            if search_phase == STRUCTURED_PHASE:
                # Intersect the exact truck-entrance alignment events with
                # the already-placed finished-goods edge events. This lets
                # P2D evaluate a shipping interface that is both P2C-adjacent
                # and entrance-aligned without P2C consuming maneuver poses
                # or computing truck routes.
                finished_edge_anchors = {
                    anchor
                    for neighbor in (*must_neighbors, *structural_neighbors)
                    for anchor in _edge_anchors(neighbor, anchor_width_mm, anchor_depth_mm)
                }
                structural_anchors.update(
                    (edge_x, entrance_y)
                    for edge_x, _edge_y in finished_edge_anchors
                    for _entry_x, entrance_y in approach_anchors
                )
                structural_anchors.update(
                    (entrance_x, edge_y)
                    for _entry_x, edge_y in finished_edge_anchors
                    for entrance_x, _entry_y in approach_anchors
                )
        if (
            code == "finished_goods_room"
            and search_phase == STRUCTURED_PHASE
            and truck_entrance is not None
            and zone_authorities is not None
            and isinstance(zone_authorities.get("shipping_channel"), Mapping)
        ):
            truck_side_finished = _finished_anchors_for_truck_interface(
                zone_authorities["shipping_channel"],
                truck_entrance,
                boundary,
                anchor_width_mm,
                anchor_depth_mm,
            )
            structural_anchors.update(truck_side_finished)
            prioritized_truck_finished_keys.update(
                (x_mm, y_mm, width_mm, depth_mm, rotation) for x_mm, y_mm in truck_side_finished
            )
        anchors = (
            tuple(sorted(structural_anchors))
            if search_phase == STRUCTURED_PHASE
            else tuple(sorted(structural_anchors | legacy_anchors))
        )
        for x_mm, y_mm in anchors:
            rectangle = _rectangle_from_mm(code, x_mm, y_mm, width_mm, depth_mm, rotation)
            if not _rectangle_is_usable(rectangle, placed, boundary, boundary_bounds, obstacles):
                continue
            if any(
                not rectangles_share_positive_edge(rectangle, neighbor)
                for neighbor in must_neighbors
            ):
                continue
            if (
                search_phase == STRUCTURED_PHASE
                and structural_skeleton is not None
                and not _candidate_fits_skeleton_region(
                    code, rectangle, placed, structural_skeleton
                )
            ):
                continue
            key = (x_mm, y_mm, width_mm, depth_mm, rotation)
            options[key] = rectangle

    def stable_geometry_key(rectangle: PlacedRectangleV1) -> tuple[object, ...]:
        width_mm = _mm(rectangle.width_m, field="candidate.width_m", positive=True)
        depth_mm = _mm(rectangle.depth_m, field="candidate.depth_m", positive=True)
        flexible_shape_skew = (
            Fraction(abs(width_mm - depth_mm), max(width_mm, depth_mm))
            if code in FLEXIBLE_ZONE_CODES
            else Fraction(0)
        )
        changing_entrance_rank = int(
            code == "changing_room"
            and not _rectangle_shares_entrance_boundary(rectangle, main_entrance)
        )
        entrance_midpoint_rank = 0
        if code == "changing_room":
            entrance_start, entrance_end = main_entrance
            entrance_midpoint = (
                (entrance_start[0] + entrance_end[0]) // 2,
                (entrance_start[1] + entrance_end[1]) // 2,
            )
            room_bounds = _bounds(rectangle)
            entrance_midpoint_rank = int(
                room_bounds[0] <= entrance_midpoint[0] <= room_bounds[2]
                and room_bounds[1] <= entrance_midpoint[1] <= room_bounds[3]
            )
        changing_core_edge_rank = int(
            code == "changing_room"
            and "sorting_packaging_room" in placed
            and not rectangles_share_positive_edge(rectangle, placed["sorting_packaging_room"])
        )
        office_process_attachment_rank = 0
        if code == "office":
            coating = placed.get("coating_room")
            shipping = placed.get("shipping_channel")
            office_process_attachment_rank = int(
                coating is None
                or shipping is None
                or not rectangles_share_positive_edge(rectangle, coating)
                or not rectangles_share_positive_edge(rectangle, shipping)
            )
        shipping_truck_entrance_rank = int(
            code == "shipping_channel"
            and truck_entrance is not None
            and not _rectangle_shares_entrance_boundary(rectangle, truck_entrance)
        )
        shipping_entrance_axis_rank = 0
        shipping_long_axis_rank = 0
        if code == "shipping_channel" and truck_entrance is not None:
            (entrance_start, entrance_end) = truck_entrance
            truck_approach_axis = (
                "X"
                if entrance_start[0] == entrance_end[0]
                else "Y"
                if entrance_start[1] == entrance_end[1]
                else None
            )
            if truck_approach_axis is not None:
                left, bottom, right, top = _bounds(rectangle)
                shipping_long_axis = "X" if right - left >= top - bottom else "Y"
                shipping_long_axis_rank = int(shipping_long_axis != truck_approach_axis)
                low_x, high_x = sorted((entrance_start[0], entrance_end[0]))
                low_y, high_y = sorted((entrance_start[1], entrance_end[1]))
                entrance_axis_aligned = any(
                    (edge[0][1] == edge[1][1] and low_y <= edge[0][1] <= high_y)
                    if truck_approach_axis == "X"
                    else (edge[0][0] == edge[1][0] and low_x <= edge[0][0] <= high_x)
                    for _, edge in _long_edges(rectangle)
                )
                shipping_entrance_axis_rank = int(not entrance_axis_aligned)
        process_band_axis_rank = 0
        if code == "secondary_precooling_room" and structural_skeleton is not None:
            left, bottom, right, top = _bounds(rectangle)
            zone_long_axis = "X" if right - left >= top - bottom else "Y"
            process_band_axis_rank = int(zone_long_axis != structural_skeleton.ordering_axis)
        finished_truck_interface_rank = int(
            code == "finished_goods_room"
            and (
                _mm(rectangle.x, field="candidate.x"),
                _mm(rectangle.y, field="candidate.y"),
                _mm(rectangle.width_m, field="candidate.width_m"),
                _mm(rectangle.depth_m, field="candidate.depth_m"),
                rectangle.rotation_deg,
            )
            not in prioritized_truck_finished_keys
        )
        finished_core_axis_alignment_rank = 0
        if code == "finished_goods_room" and structural_skeleton is not None:
            # Reuse an exact transverse axis from the already placed process
            # core before falling back to lexical coordinates. This keeps the
            # terminal storage band attached to the core envelope instead of
            # stretching across unrelated site space. It is a geometry fact,
            # not a route-distance score or a pass/fail threshold.
            transverse_bounds_index = (1, 3) if structural_skeleton.ordering_axis == "X" else (0, 2)
            candidate_bounds = _bounds(rectangle)
            candidate_axis_edges = (
                candidate_bounds[transverse_bounds_index[0]],
                candidate_bounds[transverse_bounds_index[1]],
            )
            core_axis_edges = tuple(
                edge
                for core_code in structural_skeleton.core_zone_codes
                if (core_zone := placed.get(core_code)) is not None
                for core_bounds in (_bounds(core_zone),)
                for edge in (
                    core_bounds[transverse_bounds_index[0]],
                    core_bounds[transverse_bounds_index[1]],
                )
            )
            if core_axis_edges:
                finished_core_axis_alignment_rank = min(
                    abs(candidate_edge - core_edge)
                    for candidate_edge in candidate_axis_edges
                    for core_edge in core_axis_edges
                )
        central_raw_side_rank = 0
        central_band_alignment_rank = 0
        support_region_rank = 0
        support_perimeter_rank = 0
        support_root_rank = 0
        support_side_coherence_rank = 0
        if (
            code == "primary_precooling_room"
            and structural_family.family == "CENTRAL_PROCESS_HUB"
            and structural_skeleton is not None
            and "sorting_packaging_room" in placed
        ):
            side = _adjacent_side(placed["sorting_packaging_room"], rectangle)
            low_side = "WEST" if structural_skeleton.ordering_axis == "X" else "SOUTH"
            high_side = "EAST" if structural_skeleton.ordering_axis == "X" else "NORTH"
            central_raw_side_rank = 0 if side == low_side else 1 if side == high_side else 2
            sorting_bounds = _bounds(placed["sorting_packaging_room"])
            primary_bounds = _bounds(rectangle)
            if structural_skeleton.ordering_axis == "Y":
                if primary_bounds[0] == sorting_bounds[0]:
                    central_band_alignment_rank = 0
                elif primary_bounds[2] == sorting_bounds[2]:
                    central_band_alignment_rank = 1
                else:
                    central_band_alignment_rank = 2
            elif primary_bounds[1] == sorting_bounds[1]:
                central_band_alignment_rank = 0
            elif primary_bounds[3] == sorting_bounds[3]:
                central_band_alignment_rank = 1
            else:
                central_band_alignment_rank = 2
        if code in SUPPORT_ZONE_CODES and structural_skeleton is not None:
            sorting = placed.get("sorting_packaging_room")
            allowed_sides = (
                {"NORTH", "SOUTH"} if structural_skeleton.ordering_axis == "X" else {"EAST", "WEST"}
            )
            direct_side = _adjacent_side(sorting, rectangle) if sorting is not None else None
            shares_core_band = False
            if sorting is not None:
                axis_low, axis_high = (0, 2) if structural_skeleton.ordering_axis == "X" else (1, 3)
                core_bounds = _bounds(sorting)
                candidate_bounds = _bounds(rectangle)
                shares_core_band = min(core_bounds[axis_high], candidate_bounds[axis_high]) > max(
                    core_bounds[axis_low], candidate_bounds[axis_low]
                )
            attachment_side: str | None = None
            if direct_side is not None:
                support_root_rank = 0
                support_region_rank = (
                    0
                    if direct_side in allowed_sides and shares_core_band
                    else 1
                    if direct_side in allowed_sides
                    else 2
                )
                attachment_side = direct_side
            elif code in {"secondary_fruit_buffer", "frozen_fruit_room"}:
                support_parent = next(
                    (
                        placed[parent_code]
                        for parent_code in (
                            "frozen_fruit_room",
                            "packaging_material_storage",
                        )
                        if parent_code != code
                        and parent_code in placed
                        and rectangles_share_positive_edge(rectangle, placed[parent_code])
                    ),
                    None,
                )
                if support_parent is not None:
                    parent_adjacent_side: str | None = (
                        _adjacent_side(sorting, support_parent) if sorting is not None else None
                    )
                    support_root_rank = 1
                    support_region_rank = (
                        0
                        if parent_adjacent_side in allowed_sides and shares_core_band
                        else 1
                        if parent_adjacent_side in allowed_sides
                        else 2
                    )
                    attachment_side = parent_adjacent_side
                else:
                    support_root_rank = 2
                    support_region_rank = 2
                    attachment_side = None
            else:
                support_root_rank = 2
                support_region_rank = 2
                attachment_side = None
            support_perimeter_rank = int(not _rectangle_touches_boundary(rectangle, boundary))
            occupied_support_sides = {
                side
                for support_code in SUPPORT_ZONE_CODES
                if (support := placed.get(support_code)) is not None
                if sorting is not None
                if (side := _adjacent_side(sorting, support)) is not None
            }
            support_side_coherence_rank = (
                (0 if attachment_side in occupied_support_sides else 1)
                if occupied_support_sides
                else 0
            )
        root_axis_rank: int | Decimal = 0
        if code == "raw_fruit_buffer":
            root_bounds = _bounds(rectangle)
            root_axis = (
                structural_skeleton.ordering_axis
                if structural_skeleton is not None
                else structural_family.dominant_axis
            )
            root_low, root_high = (
                (root_bounds[0], root_bounds[2])
                if root_axis == "X"
                else (root_bounds[1], root_bounds[3])
            )
            direction = structural_family.dominant_direction
            root_axis_rank = -root_low if direction == "NEGATIVE" else root_low
        major_axis_rank = 0
        site_center_distance = 0
        if code in {"sorting_packaging_room", "primary_precooling_room"}:
            left, bottom, right, top = _bounds(rectangle)
            min_x, min_y, max_x, max_y = boundary_bounds
            # Compare doubled centres using integers, so ranking is exact and
            # independent of floating-point/epsilon behavior.
            site_center_distance = abs((left + right) - (min_x + max_x)) + abs(
                (bottom + top) - (min_y + max_y)
            )
        if code == "sorting_packaging_room":
            left, bottom, right, top = _bounds(rectangle)
            preferred_long_axis = structural_family.dominant_axis
            if structural_family.family == "LINEAR_PROCESS_BAND":
                # A linear band's axis describes group order, not the long
                # dimension of each room. Orienting the dominant sorting hall
                # across the band leaves room for raw/core/finished bands on
                # either side instead of consuming the entire flow axis.
                preferred_long_axis = "Y" if preferred_long_axis == "X" else "X"
            major_axis_rank = int(
                not (
                    (right - left) >= (top - bottom)
                    if preferred_long_axis == "X"
                    else (top - bottom) >= (right - left)
                )
            )
        linear_rank = 0
        linear_predecessor = _structural_linear_predecessor(code)
        if structural_family.family == "LINEAR_PROCESS_BAND" and linear_predecessor is not None:
            predecessor = placed.get(linear_predecessor)
            if predecessor is not None:
                linear_rank = int(
                    not _linear_flow_anchor_matches(rectangle, predecessor, structural_family)
                )
        return (
            int(
                code == "coating_room"
                and (
                    _mm(rectangle.x, field="candidate.x"),
                    _mm(rectangle.y, field="candidate.y"),
                    _mm(rectangle.width_m, field="candidate.width_m"),
                    _mm(rectangle.depth_m, field="candidate.depth_m"),
                    rectangle.rotation_deg,
                )
                not in prioritized_bridge_keys
            ),
            changing_entrance_rank,
            entrance_midpoint_rank,
            changing_core_edge_rank,
            office_process_attachment_rank,
            flexible_shape_skew,
            process_band_axis_rank,
            finished_core_axis_alignment_rank,
            finished_truck_interface_rank,
            shipping_entrance_axis_rank,
            shipping_long_axis_rank,
            shipping_truck_entrance_rank,
            central_raw_side_rank,
            central_band_alignment_rank,
            support_root_rank,
            support_region_rank,
            support_side_coherence_rank,
            support_perimeter_rank,
            major_axis_rank,
            site_center_distance,
            root_axis_rank,
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
        if code == "sorting_packaging_room" and not placed:
            return True
        if structural_family.family == "LINEAR_PROCESS_BAND":
            if code == "coating_room":
                sorting = placed.get("sorting_packaging_room")
                secondary = placed.get("secondary_precooling_room")
                return (
                    sorting is not None
                    and secondary is not None
                    and rectangles_share_positive_edge(rectangle, sorting)
                    and rectangles_share_positive_edge(rectangle, secondary)
                )
            if code == "finished_goods_room":
                return _linear_group_flow_anchor_matches(
                    rectangle,
                    placed,
                    ("secondary_precooling_room", "coating_room"),
                    structural_family,
                )
            linear_predecessor = _structural_linear_predecessor(code)
            if linear_predecessor is not None:
                predecessor = placed.get(linear_predecessor)
                return predecessor is not None and _linear_flow_anchor_matches(
                    rectangle, predecessor, structural_family
                )
        if code == "primary_precooling_room":
            return any(
                rectangles_share_positive_edge(rectangle, neighbor) for neighbor in must_neighbors
            )
        if code == "changing_room" and _rectangle_shares_entrance_boundary(
            rectangle, main_entrance
        ):
            return True
        if code == "coating_room" and "sorting_packaging_room" in placed:
            return rectangles_share_positive_edge(rectangle, placed["sorting_packaging_room"])
        if not structural_neighbors:
            if code != "raw_fruit_buffer":
                return False
            return _rectangle_touches_boundary(rectangle, boundary)
        if code == "secondary_precooling_room":
            # It is a frozen process interface adjacent to sorting and
            # coating, not a spatial predecessor of the entire core envelope.
            return any(
                rectangles_share_positive_edge(rectangle, neighbor)
                for neighbor in structural_neighbors
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
    if search_phase == STRUCTURED_PHASE:
        return tuple(structured[:STRUCTURED_MAX_OPTIONS_PER_ZONE])
    if search_phase == GENERAL_FALLBACK_PHASE:
        # The fallback removes the global skeleton predicates while keeping
        # every exact P2C anchor and all unchanged hard geometry predicates.
        return tuple((*general, *structured)[:MAX_OPTIONS_PER_ZONE])
    if search_phase == LEGACY_COMPAT_PHASE:
        return tuple((*structured, *general)[:MAX_OPTIONS_PER_ZONE])
    raise _error("PLACEMENT_SEARCH_PHASE_INVALID", search_phase=search_phase)


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


def _structural_linear_predecessor(code: str) -> str | None:
    """Return the spatial predecessor used by each generated process band."""
    predecessors = {
        "primary_precooling_room": "raw_fruit_buffer",
        "sorting_packaging_room": "primary_precooling_room",
        # The secondary room is the downstream transition from sorting.
        # Coating is a core-side interface adjacent to both, not a serial
        # room on the dominant axis.
        "secondary_precooling_room": "sorting_packaging_room",
        "shipping_channel": "finished_goods_room",
    }
    return predecessors.get(code)


def _linear_group_flow_anchor_matches(
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    group_zone_codes: Sequence[str],
    family: StructuralCompositionFamilyV1,
) -> bool:
    """Require contact at the exact downstream face of an already placed group."""
    targets = tuple(placed[code] for code in group_zone_codes if code in placed)
    if not targets:
        return False
    candidate = _bounds(rectangle)
    target_bounds = tuple(_bounds(target) for target in targets)
    if family.dominant_axis == "X":
        if family.dominant_direction == "POSITIVE":
            terminal = max(bounds[2] for bounds in target_bounds)
            return candidate[0] == terminal and any(
                bounds[2] == terminal
                and min(candidate[3], bounds[3]) > max(candidate[1], bounds[1])
                for bounds in target_bounds
            )
        terminal = min(bounds[0] for bounds in target_bounds)
        return candidate[2] == terminal and any(
            bounds[0] == terminal and min(candidate[3], bounds[3]) > max(candidate[1], bounds[1])
            for bounds in target_bounds
        )
    if family.dominant_direction == "POSITIVE":
        terminal = max(bounds[3] for bounds in target_bounds)
        return candidate[1] == terminal and any(
            bounds[3] == terminal and min(candidate[2], bounds[2]) > max(candidate[0], bounds[0])
            for bounds in target_bounds
        )
    terminal = min(bounds[1] for bounds in target_bounds)
    return candidate[3] == terminal and any(
        bounds[1] == terminal and min(candidate[2], bounds[2]) > max(candidate[0], bounds[0])
        for bounds in target_bounds
    )


def _adjacent_side(reference: PlacedRectangleV1, candidate: PlacedRectangleV1) -> str | None:
    """Return candidate's exact cardinal side when it shares a positive edge."""
    first = _bounds(reference)
    second = _bounds(candidate)
    if first[2] == second[0] and min(first[3], second[3]) > max(first[1], second[1]):
        return "EAST"
    if first[0] == second[2] and min(first[3], second[3]) > max(first[1], second[1]):
        return "WEST"
    if first[3] == second[1] and min(first[2], second[2]) > max(first[0], second[0]):
        return "NORTH"
    if first[1] == second[3] and min(first[2], second[2]) > max(first[0], second[0]):
        return "SOUTH"
    return None


def _candidate_fits_skeleton_region(
    code: str,
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    skeleton: StructuralSkeletonV1,
) -> bool:
    """Apply group-to-band projection order while each group is generated."""
    group = functional_group_for_zone(code)
    if group == SUPPORT_GROUP:
        # The support region is a search preference, not a new engineering
        # hard constraint. Its exact face/attachment facts are ranked below;
        # general fallback remains available for constrained sites.
        return True
    if group not in {RAW_SIDE_GROUP, PROCESSING_CORE_GROUP, FINISHED_SIDE_GROUP}:
        return True

    axis = skeleton.ordering_axis
    low_index, high_index = (0, 2) if axis == "X" else (1, 3)
    candidate_bounds = _bounds(rectangle)
    candidate_interval = (candidate_bounds[low_index], candidate_bounds[high_index])

    def interval(group_name: str) -> tuple[int, int] | None:
        values = [
            _bounds(existing)
            for zone_code, existing in placed.items()
            if functional_group_for_zone(zone_code) == group_name
        ]
        if not values:
            return None
        return min(row[low_index] for row in values), max(row[high_index] for row in values)

    raw_interval = interval(RAW_SIDE_GROUP)
    core_interval = interval(PROCESSING_CORE_GROUP)
    finished_interval = interval(FINISHED_SIDE_GROUP)
    if skeleton.family.family == "LINEAR_PROCESS_BAND":
        sorting = placed.get("sorting_packaging_room")
        secondary = placed.get("secondary_precooling_room")
        finished = placed.get("finished_goods_room")
        if code == "secondary_precooling_room":
            return sorting is not None and _linear_flow_anchor_matches(
                rectangle, sorting, skeleton.family
            )
        if code == "coating_room":
            return (
                sorting is not None
                and secondary is not None
                and rectangles_share_positive_edge(rectangle, sorting)
                and rectangles_share_positive_edge(rectangle, secondary)
            )
        if code == "finished_goods_room":
            return _linear_group_flow_anchor_matches(
                rectangle,
                placed,
                ("secondary_precooling_room", "coating_room"),
                skeleton.family,
            )
        if code == "shipping_channel":
            return finished is not None and _linear_flow_anchor_matches(
                rectangle, finished, skeleton.family
            )
    if group == RAW_SIDE_GROUP:
        if skeleton.family.family == "CENTRAL_PROCESS_HUB":
            sorting = placed.get("sorting_packaging_room")
            if code == "primary_precooling_room":
                if sorting is None:
                    return False
                occupied_core_sides = {
                    side
                    for zone_code in ("coating_room", "secondary_precooling_room")
                    if (zone := placed.get(zone_code)) is not None
                    if (side := _adjacent_side(sorting, zone)) is not None
                }
                primary_side = _adjacent_side(sorting, rectangle)
                return primary_side is not None and primary_side not in occupied_core_sides
            if code == "raw_fruit_buffer":
                primary = placed.get("primary_precooling_room")
                if sorting is None or primary is None:
                    return False
                primary_side = _adjacent_side(sorting, primary)
                raw_side = _adjacent_side(primary, rectangle)
                if primary_side is None or raw_side is None:
                    return False
                # The raw buffer may continue along the raw band or attach
                # laterally to the primary room, but cannot be placed on the
                # face that points back into the sorting core.
                toward_core = {
                    "NORTH": "SOUTH",
                    "SOUTH": "NORTH",
                    "EAST": "WEST",
                    "WEST": "EAST",
                }[primary_side]
                if raw_side == toward_core:
                    return False
                primary_bounds = _bounds(primary)
                if core_interval is None:
                    return False
                primary_interval = (
                    primary_bounds[low_index],
                    primary_bounds[high_index],
                )
                if primary_interval[1] <= core_interval[0]:
                    return candidate_interval[1] <= core_interval[0]
                if primary_interval[0] >= core_interval[1]:
                    return candidate_interval[0] >= core_interval[1]
                return False
        if code == "primary_precooling_room":
            if core_interval is None:
                # LINEAR lanes grow raw -> core. At this point the raw room
                # has been placed, while the core is intentionally not yet
                # present; exact MUST adjacency is checked independently.
                return (
                    skeleton.family.family == "LINEAR_PROCESS_BAND" and "raw_fruit_buffer" in placed
                )
            if skeleton.family.family == "LINEAR_PROCESS_BAND":
                if skeleton.family.dominant_direction == "POSITIVE":
                    return candidate_interval[1] <= core_interval[0]
                return candidate_interval[0] >= core_interval[1]
            # The hub lane permits either exact side of the core; the raw
            # buffer is subsequently constrained to continue outward from the
            # selected primary-precooling side.
            return (
                candidate_interval[1] <= core_interval[0]
                or candidate_interval[0] >= core_interval[1]
            )
        if code == "raw_fruit_buffer":
            primary = placed.get("primary_precooling_room")
            if primary is None:
                # In the linear skeleton the raw buffer is the deterministic
                # boundary-root zone, so it is generated before its primary
                # precooling attachment and before the process core exists.
                return skeleton.family.family == "LINEAR_PROCESS_BAND"
            if core_interval is None:
                return False
            # The raw group is a band, not a single-file chain. Its buffer
            # may attach to the primary room on a transverse face as long as
            # the complete raw-group projection remains upstream of the core.
            primary_bounds = _bounds(primary)
            primary_interval = (primary_bounds[low_index], primary_bounds[high_index])
            if primary_interval[1] <= core_interval[0]:
                return candidate_interval[1] <= core_interval[0]
            if primary_interval[0] >= core_interval[1]:
                return candidate_interval[0] >= core_interval[1]
            return False
        return False
    if group == PROCESSING_CORE_GROUP:
        if core_interval is not None:
            sorting = placed.get("sorting_packaging_room")
            if sorting is None or code != "coating_room":
                return False
            # Sorting is the core anchor; the smaller coating function joins
            # one of its free faces.  Requiring it to span the full process
            # axis made it consume an entire end face and frequently stranded
            # the frozen finished-goods adjacency.  This is an exact shared
            # edge predicate, not a route proxy or a relaxation of P2D.
            # The coating function may bridge a sorting-hall face to the
            # secondary-precooling interface. It remains part of the core
            # when it shares a real edge with sorting; containment within the
            # hall's long-axis projection is not a frozen engineering rule.
            return rectangles_share_positive_edge(rectangle, sorting)
        if skeleton.family.family == "LINEAR_PROCESS_BAND":
            # The linear skeleton deliberately generates RAW before CORE.
            # Require the sorting root to continue in the lane's frozen
            # direction from the already placed raw-side envelope.
            if code != "sorting_packaging_room" or raw_interval is None:
                return False
            if skeleton.family.dominant_direction == "POSITIVE":
                return raw_interval[1] <= candidate_interval[0]
            return candidate_interval[1] <= raw_interval[0]
        # The processing core is the structural skeleton root. It is placed
        # before raw/finished bands so those groups organize around its actual
        # feasible envelope instead of biasing it into residual space.
        return (
            code == "sorting_packaging_room" and raw_interval is None and finished_interval is None
        )
    if core_interval is None:
        return False
    if skeleton.family.family == "CENTRAL_PROCESS_HUB":
        return True
    if code == "secondary_precooling_room":
        # P2D freezes secondary precooling between sorting and coating, while
        # P1A places coating inside the process-core envelope. Keep secondary
        # precooling as the explicit spatial interface to the core.  It is a
        # transition zone, not a reason to force the finished-goods room past
        # the entire core projection.
        return True
    if raw_interval is None:
        return False
    downstream = _structural_downstream_direction(skeleton, raw_interval, core_interval)
    if downstream is None:
        return False
    finished = placed.get("finished_goods_room")
    if code == "finished_goods_room":
        # The frozen P2D graph requires this room to share edges with both
        # coating and secondary precooling.  Its band therefore starts at the
        # core interface and extends downstream; requiring full interval
        # separation would make those unchanged hard adjacencies impossible.
        return (
            candidate_interval[1] > core_interval[1]
            if downstream == "POSITIVE"
            else candidate_interval[0] < core_interval[0]
        )
    if code == "shipping_channel" and finished is not None:
        # Shipping is an interface attached to finished goods, not another
        # serial room whose full rectangle must sit beyond the goods interval.
        # Keep it on the downstream side of the process core; the final
        # finished-group envelope check verifies the group order.
        return (
            candidate_interval[1] > core_interval[1]
            if downstream == "POSITIVE"
            else candidate_interval[0] < core_interval[0]
        )
    return (
        candidate_interval[0] >= core_interval[1]
        if downstream == "POSITIVE"
        else candidate_interval[1] <= core_interval[0]
    )


def _structural_downstream_direction(
    skeleton: StructuralSkeletonV1,
    raw_interval: tuple[int, int] | None,
    core_interval: tuple[int, int] | None,
) -> str | None:
    if skeleton.family.family == "LINEAR_PROCESS_BAND":
        return skeleton.family.dominant_direction
    if raw_interval is None or core_interval is None:
        return None
    if raw_interval[1] <= core_interval[0]:
        return "POSITIVE"
    if core_interval[1] <= raw_interval[0]:
        return "NEGATIVE"
    return None


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
    placement_zone_order: tuple[str, ...]
    structural_composition_family: StructuralCompositionFamilyV1
    structural_skeleton: StructuralSkeletonV1
    search_phase: str


@dataclass
class _PlacementSearchStats:
    visited_nodes: int = 0
    generated_candidates: int = 0
    complete_candidates: int = 0
    node_budget_exhausted: bool = False
    structured_main_skeleton_completions: dict[str, int] | None = None
    structured_core_root_completions: dict[str, int] | None = None


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
    structural_family: StructuralCompositionFamilyV1 | None = None,
    search_phase: str = LEGACY_COMPAT_PHASE,
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
    if search_phase not in {STRUCTURED_PHASE, GENERAL_FALLBACK_PHASE, LEGACY_COMPAT_PHASE}:
        raise _error("PLACEMENT_SEARCH_PHASE_INVALID", search_phase=search_phase)
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
    selected_family = structural_family or select_structural_composition_family(
        site_body, authorities
    )
    skeletons = structural_skeleton_candidates(
        site_body, tuple(authorities), zone_authorities=authorities
    )
    skeleton = next(
        (
            candidate
            for candidate in skeletons
            if candidate.family.to_dict() == selected_family.to_dict()
        ),
        None,
    )
    if skeleton is None:
        raise _error("STRUCTURAL_SKELETON_UNAVAILABLE")
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
        placement_zone_order=(
            (
                LINEAR_STRUCTURED_PLACEMENT_ZONE_ORDER
                if selected_family.family == "LINEAR_PROCESS_BAND"
                else STRUCTURED_PLACEMENT_ZONE_ORDER
            )
            if search_phase == STRUCTURED_PHASE
            else PLACEMENT_ZONE_ORDER
        ),
        structural_composition_family=selected_family,
        structural_skeleton=skeleton,
        search_phase=search_phase,
    )


def _group_axis_interval(
    group: str,
    placed: Mapping[str, PlacedRectangleV1],
    axis: str,
) -> tuple[int, int] | None:
    members = tuple(code for code in FUNCTIONAL_GROUPS[group] if code in placed)
    if not members:
        return None
    bounds = tuple(_bounds(placed[code]) for code in members)
    coordinate_pair = (0, 2) if axis == "X" else (1, 3)
    return (
        min(row[coordinate_pair[0]] for row in bounds),
        max(row[coordinate_pair[1]] for row in bounds),
    )


def _main_group_order_monotonic(
    placed: Mapping[str, PlacedRectangleV1], skeleton: StructuralSkeletonV1
) -> bool:
    raw = _group_axis_interval(RAW_SIDE_GROUP, placed, skeleton.ordering_axis)
    core = _group_axis_interval(PROCESSING_CORE_GROUP, placed, skeleton.ordering_axis)
    terminal_codes = ("finished_goods_room", "shipping_channel")
    terminal_bounds = tuple(_bounds(placed[code]) for code in terminal_codes if code in placed)
    if raw is None or core is None or len(terminal_bounds) != len(terminal_codes):
        return False
    if skeleton.family.family == "CENTRAL_PROCESS_HUB":
        sorting = placed.get("sorting_packaging_room")
        primary = placed.get("primary_precooling_room")
        raw_zone = placed.get("raw_fruit_buffer")
        secondary = placed.get("secondary_precooling_room")
        if any(zone is None for zone in (sorting, primary, raw_zone, secondary)):
            return False
        raw_side = _adjacent_side(sorting, primary)  # type: ignore[arg-type]
        raw_attachment = _adjacent_side(primary, raw_zone)  # type: ignore[arg-type]
        if raw_side is None or raw_attachment is None:
            return False
        toward_core = {
            "NORTH": "SOUTH",
            "SOUTH": "NORTH",
            "EAST": "WEST",
            "WEST": "EAST",
        }[raw_side]
        if raw_attachment == toward_core:
            return False
        finished_side = _adjacent_side(sorting, secondary)  # type: ignore[arg-type]
        if finished_side is None or finished_side == raw_side:
            return False
        low_index, high_index = (0, 2) if skeleton.ordering_axis == "X" else (1, 3)
        raw_interval = _group_axis_interval(RAW_SIDE_GROUP, placed, skeleton.ordering_axis)
        core_interval = _group_axis_interval(PROCESSING_CORE_GROUP, placed, skeleton.ordering_axis)
        terminal_interval = (
            min(row[low_index] for row in terminal_bounds),
            max(row[high_index] for row in terminal_bounds),
        )
        if raw_interval is None or core_interval is None:
            return False
        return (
            raw_interval[1] <= core_interval[0] and core_interval[1] <= terminal_interval[0]
        ) or (terminal_interval[1] <= core_interval[0] and core_interval[1] <= raw_interval[0])
    low_index, high_index = (0, 2) if skeleton.ordering_axis == "X" else (1, 3)
    finished = (
        min(row[low_index] for row in terminal_bounds),
        max(row[high_index] for row in terminal_bounds),
    )
    downstream = _structural_downstream_direction(skeleton, raw, core)
    if downstream == "POSITIVE":
        return raw[1] <= core[0] and finished[1] > core[1]
    if downstream == "NEGATIVE":
        return core[1] <= raw[0] and finished[0] < core[0]
    return False


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
        "candidate_family": "MULTI_FAMILY_STRUCTURAL_SKELETON_V1",
        "structural_composition_identity": "structural-composition-family@1.0.0",
        "structural_skeleton": context.structural_skeleton.to_dict(),
        "search_phase": context.search_phase,
        "placement_zone_order": list(context.placement_zone_order),
        "structured_main_skeleton_diversity": {
            "policy_identity": "main-process-skeleton-sampling@1.0.0",
            "completion_cap_per_skeleton": STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON,
            "distinct_skeletons_with_complete_candidate": len(
                stats.structured_main_skeleton_completions or {}
            ),
            "completion_counts": sorted(
                (stats.structured_main_skeleton_completions or {}).values()
            ),
        },
        "structured_core_root_diversity": {
            "policy_identity": "process-core-root-sampling@1.0.0",
            "distinct_roots_with_complete_candidate": len(
                stats.structured_core_root_completions or {}
            ),
            "completion_cap_per_root": STRUCTURED_COMPLETIONS_PER_CORE_ROOT,
        },
    }


def _walk_complete_candidate_payloads(
    context: _PlacementSearchContext, stats: _PlacementSearchStats
) -> Iterator[dict[str, Any]]:
    """Yield every complete P2C candidate until the node budget is exhausted."""
    placed: dict[str, PlacedRectangleV1] = {}
    truck_entrance = _truck_segment(context.site_body)
    if stats.structured_main_skeleton_completions is None:
        stats.structured_main_skeleton_completions = {}
    if stats.structured_core_root_completions is None:
        stats.structured_core_root_completions = {}
    main_skeleton_completions = stats.structured_main_skeleton_completions
    core_root_completions = stats.structured_core_root_completions
    assert main_skeleton_completions is not None
    assert core_root_completions is not None

    def main_skeleton_signature() -> str:
        return canonical_json(
            [
                {
                    "zone_code": code,
                    "x": str(placed[code].x),
                    "y": str(placed[code].y),
                    "width_m": str(placed[code].width_m),
                    "depth_m": str(placed[code].depth_m),
                    "rotation_deg": placed[code].rotation_deg,
                }
                for code in MAIN_PROCESS_SKELETON_ZONE_CODES
                if code in placed
            ]
        )

    def core_root_signature() -> str | None:
        sorting = placed.get("sorting_packaging_room")
        if sorting is None:
            return None
        return canonical_json(
            {
                "x": str(sorting.x),
                "y": str(sorting.y),
                "width_m": str(sorting.width_m),
                "depth_m": str(sorting.depth_m),
                "rotation_deg": sorting.rotation_deg,
            }
        )

    def visit(index: int, structurally_generated: bool) -> Iterator[dict[str, Any]]:
        root_signature = core_root_signature()
        if (
            context.search_phase == STRUCTURED_PHASE
            and index >= len(MAIN_PROCESS_ZONE_CODES)
            and len(placed) >= len(MAIN_PROCESS_ZONE_CODES)
            and main_skeleton_completions.get(main_skeleton_signature(), 0)
            >= STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON
        ):
            return
        if (
            context.search_phase == STRUCTURED_PHASE
            and index > 0
            and root_signature is not None
            and core_root_completions.get(root_signature, 0) >= STRUCTURED_COMPLETIONS_PER_CORE_ROOT
        ):
            return
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            return
        stats.visited_nodes += 1
        if (
            context.search_phase == STRUCTURED_PHASE
            and index == len(MAIN_PROCESS_ZONE_CODES)
            and not _main_group_order_monotonic(placed, context.structural_skeleton)
        ):
            return
        if index == len(context.placement_zone_order):
            _validate_graph_completeness(context.graph, placed)
            stats.complete_candidates += 1
            if context.search_phase == STRUCTURED_PHASE:
                signature = main_skeleton_signature()
                main_skeleton_completions[signature] = (
                    main_skeleton_completions.get(signature, 0) + 1
                )
                root_signature = core_root_signature()
                if root_signature is not None:
                    core_root_completions[root_signature] = (
                        core_root_completions.get(root_signature, 0) + 1
                    )
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
            payload["_structural_skeleton"] = context.structural_skeleton.to_dict()
            payload["_search_phase"] = context.search_phase
            yield payload
            return
        code = context.placement_zone_order[index]
        option_arguments = (
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
        if context.search_phase == LEGACY_COMPAT_PHASE:
            options = _candidate_options(*option_arguments)
        else:
            options = _candidate_options(
                *option_arguments,
                search_phase=context.search_phase,
                structural_skeleton=context.structural_skeleton,
                zone_authorities=context.authorities,
                truck_entrance=truck_entrance,
            )
        stats.generated_candidates += len(options)
        for rectangle in options:
            if context.search_phase == STRUCTURED_PHASE and not _candidate_fits_skeleton_region(
                code, rectangle, placed, context.structural_skeleton
            ):
                continue
            structural_refs = structural_anchor_references(code, tuple(placed))
            if context.search_phase == STRUCTURED_PHASE and code in MAIN_PROCESS_ZONE_CODES:
                # Main-flow candidates are structurally generated only after
                # passing the versioned group/band predicate and existing
                # MUST-edge checks performed by _candidate_options.
                anchored = _candidate_fits_skeleton_region(
                    code, rectangle, placed, context.structural_skeleton
                )
            elif code == "sorting_packaging_room" and context.search_phase == STRUCTURED_PHASE:
                anchored = True
            elif code == "raw_fruit_buffer" and context.search_phase != STRUCTURED_PHASE:
                anchored = _rectangle_touches_boundary(rectangle, context.boundary)
            elif (
                context.structural_composition_family.family == "LINEAR_PROCESS_BAND"
                and _structural_linear_predecessor(code) is not None
            ):
                predecessor = placed.get(_structural_linear_predecessor(code) or "")
                anchored = predecessor is not None and _linear_flow_anchor_matches(
                    rectangle, predecessor, context.structural_composition_family
                )
            else:
                anchored = any(
                    rectangles_share_positive_edge(rectangle, placed[reference])
                    for reference in structural_refs
                )
            if (
                context.search_phase == STRUCTURED_PHASE
                and code == "coating_room"
                and "sorting_packaging_room" in placed
            ):
                anchored = anchored and rectangles_share_positive_edge(
                    rectangle, placed["sorting_packaging_room"]
                )
            placed[code] = rectangle
            yield from visit(
                index + 1,
                structurally_generated
                and anchored
                and context.search_phase != GENERAL_FALLBACK_PHASE,
            )
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
    content.pop("_structural_skeleton", None)
    content.pop("_search_phase", None)
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
    def distinct_main_process_skeleton_count(self) -> int:
        return len(self._stats.structured_main_skeleton_completions or {})

    @property
    def distinct_structural_core_root_count(self) -> int:
        return len(self._stats.structured_core_root_completions or {})

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

    @property
    def structural_skeleton(self) -> StructuralSkeletonV1:
        return self._context.structural_skeleton

    @property
    def search_phase(self) -> str:
        return self._context.search_phase

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
    structural_family: StructuralCompositionFamilyV1 | None = None,
    search_phase: str = LEGACY_COMPAT_PHASE,
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
            structural_family=structural_family,
            search_phase=search_phase,
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
