"""Deterministic placement search for the V2.2 P2C MVP.

This module consumes already-bound zone dimensions and site geometry.  It does
not calculate zone areas, generate a building envelope, or validate portals,
corridors, or final routes. The Tool 7 structured path may run the existing
authoritative truck-maneuver validator as a necessary-condition preflight on a
frozen seven-zone main-process skeleton before tail search. All geometry is
represented as integer millimetres at the predicate boundary so the bounded
search is repeatable and has no floating-point tolerance.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from itertools import product
from math import isqrt
from typing import Any, Final, cast

from cold_storage.modules.layout.domain.adjacency import AdjacencyGraphV1
from cold_storage.modules.layout.domain.building_footprint import derive_building_footprint
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.main_process_skeleton import (
    MainProcessSkeletonCandidateV1,
    canonicalize_main_process_skeleton_for_evaluation,
)
from cold_storage.modules.layout.domain.main_process_topology import (
    classify_main_process_topology_v1,
    decide_main_process_topology_ownership_v1,
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
    polygon_to_dict,
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
    segments_share_positive_length,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    FINISHED_SIDE_GROUP,
    FUNCTIONAL_GROUPS,
    LINEAR_PROCESS_BAND,
    MAIN_PROCESS_SKELETON_ZONE_CODES,
    MAIN_PROCESS_ZONE_CODES,
    OFFSET_LINEAR_BAND,
    PROCESSING_CORE_GROUP,
    RAW_SIDE_GROUP,
    STRAIGHT_LINEAR_BAND,
    SUPPORT_GROUP,
    StructuralCompositionFamilyV1,
    StructuralSkeletonV1,
    functional_group_for_zone,
    select_structural_composition_family,
    structural_anchor_references,
    structural_skeleton_candidates,
)
from cold_storage.modules.layout.domain.structural_quality import _outline_class
from cold_storage.modules.layout.domain.structured_building import (
    BASE_LAYOUT_FAMILIES,
    CENTRAL_PROCESS_WITH_SIDE_BANKS,
    LINEAR_3_BAND,
    LONGITUDINAL_PROCESS_SPINE,
    PERSONNEL_EDGE_BAND,
    RECTANGLE,
    SIMPLE_L,
    SUPPORT_BAND,
    StructuredBuildingSkeletonV1,
    _must_chain_alignment_sequences,
    _must_chain_side_sequences,
    _zone_dimension_options,
    construct_legacy_compatibility_search_plan_v1,
    construct_structured_building_plan_v1,
    structured_layout_family_for_topology,
)
from cold_storage.modules.layout.domain.tail_slot_feasibility import (
    EXACT_ORTHOGONAL_EVENT_ENUMERATION,
    evaluate_tail_zone_slot_feasibility_v1,
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
_DIRECT_STRUCTURAL_VARIANT_ROUNDS: Final = (
    (0, RECTANGLE, "DEFAULT_SUPPORT_SIDE", 0),
    (1, RECTANGLE, "DEFAULT_SUPPORT_SIDE", 0),
)
DIRECT_SYNTHESIS_ATTEMPT_COUNT: Final = len(_DIRECT_STRUCTURAL_VARIANT_ROUNDS) * len(
    BASE_LAYOUT_FAMILIES
)
# Bound the tail search under one already placed main-process skeleton so the
# deterministic node budget reaches distinct process arrangements before it
# is consumed by office/support permutations. A small fixed sample preserves
# P2D-relevant personnel/support alternatives without treating those
# variations as new process skeletons.
STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON: Final = 2
# Bound the tail search under a core root, but preserve a small set of
# personnel/support variants for P2D to evaluate against its unchanged access,
# truck, and single-building-footprint authorities.
STRUCTURED_COMPLETIONS_PER_CORE_ROOT: Final = 4
MIN_CONSTRUCTIVE_SKELETON_NODE_ALLOWANCE: Final = 15
# At the frozen 120-node global cutoff this permits up to eight geometry
# seeds (120 / 15), rather than stopping each topology after two raw seeds.
# The shared scheduler remains the actual global bound; rejected preflights
# therefore cannot turn this per-lane ceiling into a production quota.
CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT: Final = 8
STRUCTURED_SKELETON_CONSTRUCTION_SHARE_NUMERATOR: Final = 1
STRUCTURED_SKELETON_CONSTRUCTION_SHARE_DENOMINATOR: Final = 2
# Construction-share values are scheduler quantum ceilings, not lifetime
# search termination limits. Each topology keeps its generator continuation.
ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_NUMERATOR: Final = 3
ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_DENOMINATOR: Final = 4
CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET: Final = 20
CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET: Final = 16
# A scheduler turn is a bounded fairness quantum. Its generator remains alive
# after yielding, so reaching this limit never declares the search exhausted.
PLACEMENT_SEARCH_QUANTUM_NODES: Final = CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET
_CARDINAL_SIDES: Final = ("WEST", "EAST", "SOUTH", "NORTH")
_OPPOSITE_SIDE: Final = {"WEST": "EAST", "EAST": "WEST", "SOUTH": "NORTH", "NORTH": "SOUTH"}

# Group -> band -> zone order: first the authoritative main process, then the
# peripheral personnel interface whose main-entrance access is frozen, then
# local support branches. The complete process skeleton is constructed and
# frozen before either tail group is searched; this ordering only reserves
# access-critical perimeter geometry before support occupies remaining faces.
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
    # The process skeleton is already immutable. Place personnel/access tails
    # before support so peripheral support cannot consume their feasible access
    # corridor; neither tail can move any main-process rectangle.
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


def _minimum_authoritative_axis_extent(
    context: _PlacementSearchContext, zone_code: str, axis: str
) -> int:
    """Return a deterministic lower extent from existing dimension variants."""
    variants = _dimension_variants(context.authorities[zone_code], {}, context.boundary)
    extents = [
        (depth if rotation == 90 else width)
        if axis == "X"
        else (width if rotation == 90 else depth)
        for width, depth, rotation in variants
    ]
    return min(extents) if extents else 0


def _topology_root_ordering_penalty(
    context: _PlacementSearchContext, rectangle: PlacedRectangleV1
) -> int:
    """Rank roots by a coarse complete-topology envelope; never prune roots.

    Extents are derived from existing authoritative dimension variants. The
    buildable polygon and obstacle constraints remain checked only by the
    exact placement predicates. This estimate is deliberately ordering-only.
    """
    family = context.structural_composition_family
    bounds = _bounds(rectangle)
    axis = context.structural_skeleton.ordering_axis
    low, high = (0, 2) if axis == "X" else (1, 3)
    site_low, site_high = context.boundary_bounds[low], context.boundary_bounds[high]

    if context.structural_topology in {STRAIGHT_LINEAR_BAND, OFFSET_LINEAR_BAND}:
        upstream = max(
            _minimum_authoritative_axis_extent(context, code, axis)
            for code in ("raw_fruit_buffer", "primary_precooling_room")
        )
        downstream = max(
            _minimum_authoritative_axis_extent(context, code, axis)
            for code in (
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            )
        )
        if family.dominant_direction == "POSITIVE":
            upstream_available = bounds[low] - site_low
            downstream_available = site_high - bounds[high]
        else:
            upstream_available = site_high - bounds[high]
            downstream_available = bounds[low] - site_low
        return max(0, upstream - upstream_available) + max(0, downstream - downstream_available)

    # For the hub, estimate required reach independently on each selected
    # face-pair. Choose the least-penalty pairing for ordering, without
    # rejecting a root based on this coarse rectangle-only estimate.
    penalty_options: list[int] = []
    for raw_side, finished_side in _family_attachment_sides(family):
        penalty = 0
        for side, codes in (
            (raw_side, ("raw_fruit_buffer", "primary_precooling_room")),
            (
                finished_side,
                (
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                ),
            ),
        ):
            measure_axis = "X" if side in {"WEST", "EAST"} else "Y"
            minimum_extent = max(
                _minimum_authoritative_axis_extent(context, code, measure_axis) for code in codes
            )
            measure_low, measure_high = (0, 2) if measure_axis == "X" else (1, 3)
            if side in {"WEST", "SOUTH"}:
                available = bounds[measure_low] - context.boundary_bounds[measure_low]
            else:
                available = context.boundary_bounds[measure_high] - bounds[measure_high]
            penalty += max(0, minimum_extent - available)
        penalty_options.append(penalty)
    return min(penalty_options, default=0)


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


def _rectangle_distance_squared_to_entrance(
    rectangle: PlacedRectangleV1, entrance: SegmentMM
) -> int:
    """Exact orthogonal rectangle-to-entrance distance used only for option order."""
    left, bottom, right, top = _bounds(rectangle)
    (x1, y1), (x2, y2) = entrance
    if x1 == x2:
        dx = max(left - x1, 0, x1 - right)
        entrance_low, entrance_high = sorted((y1, y2))
        dy = max(bottom - entrance_high, 0, entrance_low - top)
    elif y1 == y2:
        dy = max(bottom - y1, 0, y1 - top)
        entrance_low, entrance_high = sorted((x1, x2))
        dx = max(left - entrance_high, 0, entrance_low - right)
    else:
        raise ValueError("truck entrance must be axis-aligned")
    return dx * dx + dy * dy


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
    structured_building_plan: StructuredBuildingSkeletonV1 | None = None,
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
            if (
                search_phase == STRUCTURED_PHASE
                and structured_building_plan is not None
                and not structured_building_plan.admits(code, rectangle)
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
                # Coating is a frozen MUST transition from secondary
                # precooling to finished goods. Sorting-to-coating is only a
                # SHOULD relationship and cannot be a phase-admission gate.
                return bool(must_neighbors) and any(
                    rectangles_share_positive_edge(rectangle, neighbor)
                    for neighbor in must_neighbors
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
        # Preserve the R1 general-fallback candidate stream exactly: ordinary
        # exact-feasible options precede structural anchors. The phase is
        # separate for accounting, not a new candidate-ordering policy.
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


def _truck_dock_points_at_entrance(context: _PlacementSearchContext) -> tuple[tuple[int, int], ...]:
    """Project authoritative dock-template endpoints from truck entrance events.

    These points only seed and order shipping-interface geometry. They do not
    assert maneuver feasibility; the existing truck-chain validator remains
    the sole admission predicate for every completed seven-zone skeleton.
    """
    binding = getattr(context, "truck_maneuver_binding", None)
    if binding is None:
        return ()
    project = getattr(binding, "maneuver_project_input", None)
    if project is None and isinstance(binding, Mapping):
        project_body = binding.get("maneuver_project_input")
        if isinstance(project_body, Mapping):
            template_set = project_body.get("template_set")
            templates = (
                template_set.get("templates", ()) if isinstance(template_set, Mapping) else ()
            )
        else:
            templates = ()
    else:
        template_set = getattr(project, "template_set", None)
        templates = getattr(template_set, "templates", ())

    entrance = _truck_segment(context.site_body)
    start, end = entrance
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        entry_points = ((start[0], low), (start[0], (low + high) // 2), (start[0], high))
    else:
        low, high = sorted((start[0], end[0]))
        entry_points = ((low, start[1]), ((low + high) // 2, start[1]), (high, start[1]))

    points: set[tuple[int, int]] = set()
    for template in templates:
        maneuver_class = getattr(template, "maneuver_class", None)
        reference_frame = getattr(template, "reference_frame", None)
        dock_pose = getattr(template, "final_dock_pose", None)
        if isinstance(template, Mapping):
            maneuver_class = template.get("maneuver_class", maneuver_class)
            reference_frame = template.get("reference_frame", reference_frame)
            dock_pose = template.get("final_dock_pose", dock_pose)
        if maneuver_class != "DOCK_REVERSE" or not isinstance(reference_frame, Mapping):
            continue
        entry_pose = reference_frame.get("entry_pose")
        if not isinstance(entry_pose, Mapping) or not isinstance(dock_pose, Mapping):
            continue
        entry = (
            _mm(entry_pose.get("x"), field="truck_template.entry_pose.x"),
            _mm(entry_pose.get("y"), field="truck_template.entry_pose.y"),
        )
        dock = (
            _mm(dock_pose.get("x"), field="truck_template.final_dock_pose.x"),
            _mm(dock_pose.get("y"), field="truck_template.final_dock_pose.y"),
        )
        for entry_point in entry_points:
            for rotation in (0, 90, 180, 270):
                rotated_entry = _rotate_orthogonal_mm(entry, rotation)
                rotated_dock = _rotate_orthogonal_mm(dock, rotation)
                translation = (
                    entry_point[0] - rotated_entry[0],
                    entry_point[1] - rotated_entry[1],
                )
                points.add((translation[0] + rotated_dock[0], translation[1] + rotated_dock[1]))
    return tuple(sorted(points))


def _rotate_orthogonal_mm(point: tuple[int, int], rotation_deg: int) -> tuple[int, int]:
    x, y = point
    if rotation_deg == 0:
        return x, y
    if rotation_deg == 90:
        return -y, x
    if rotation_deg == 180:
        return -x, -y
    return y, -x


def _shipping_rectangles_for_dock_events(
    context: _PlacementSearchContext,
) -> tuple[PlacedRectangleV1, ...]:
    """Create finite shipping-rectangle candidates whose loading face includes
    a dock-template point projected from the authoritative entrance events.
    Exact placement and truck feasibility are checked by existing predicates.
    """
    points = _truck_dock_points_at_entrance(context)
    if not points:
        return ()
    authority = context.authorities.get("shipping_channel")
    if authority is None:
        return ()
    candidates: dict[tuple[int, int, int, int], PlacedRectangleV1] = {}
    for width_mm, depth_mm, rotation in _dimension_variants(authority, {}, context.boundary):
        sample = _rectangle_from_mm("shipping_channel", 0, 0, width_mm, depth_mm, rotation)
        _, local_face, _, _ = _loading_face(sample, context.site_body)
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        for dock_x, dock_y in points:
            if local_face[0][1] == local_face[1][1]:
                x_origins = {
                    dock_x,
                    dock_x - actual_width,
                    context.boundary_bounds[0],
                    context.boundary_bounds[2] - actual_width,
                }
                y_origin = dock_y - local_face[0][1]
                origins = ((x, y_origin) for x in sorted(x_origins))
            else:
                y_origins = {
                    dock_y,
                    dock_y - actual_depth,
                    context.boundary_bounds[1],
                    context.boundary_bounds[3] - actual_depth,
                }
                x_origin = dock_x - local_face[0][0]
                origins = ((x_origin, y) for y in sorted(y_origins))
            for x_mm, y_mm in origins:
                rectangle = _rectangle_from_mm(
                    "shipping_channel", x_mm, y_mm, width_mm, depth_mm, rotation
                )
                _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
                if not _on_segment((dock_x, dock_y), loading_face[0], loading_face[1]):
                    continue
                if _geometry_rejection_reason(rectangle, {}, context) is not None:
                    continue
                candidates[_bounds(rectangle)] = rectangle
    return tuple(candidates[key] for key in sorted(candidates))


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


def _building_envelope_closure_rejection(
    context: _PlacementSearchContext,
    placed: Mapping[str, PlacedRectangleV1],
) -> str | None:
    """Require every structured zone and its exact room union to close cleanly."""
    plan = context.structured_building_plan
    if plan is None:
        return "BUILDING_ENVELOPE_CLOSURE_PLAN_UNAVAILABLE"
    try:
        plan.with_placements(placed)
    except LayoutAuthorityError:
        return "BUILDING_ENVELOPE_CLOSURE_BAND_OR_CONTAINMENT_FAIL"
    try:
        footprint = derive_building_footprint(placed, ())
    except LayoutAuthorityError:
        return "BUILDING_ENVELOPE_CLOSURE_DISCONNECTED_OR_AMBIGUOUS"
    outline, _rank = _outline_class(
        {"building_footprint": {"footprint": polygon_to_dict(footprint)}}
    )
    if outline not in {"RECTANGLE", "SIMPLE_L"}:
        return f"BUILDING_ENVELOPE_CLOSURE_OUTLINE_{outline}"
    return None


def _is_better(
    candidate: Mapping[str, Any], best: Mapping[str, Any] | None, preferred_loading_side: str
) -> bool:
    if best is None:
        return True
    business_comparison = compare_placement_candidate_business_objectives(
        candidate, best, preferred_loading_side
    )
    if business_comparison != 0:
        return business_comparison > 0
    return placement_candidate_canonical_tiebreak_key(candidate) < (
        placement_candidate_canonical_tiebreak_key(best)
    )


def compare_placement_candidate_business_objectives(
    candidate: Mapping[str, Any], best: Mapping[str, Any], preferred_loading_side: str
) -> int:
    """Compare only authorized P2B2 objectives, excluding deterministic fallback."""
    candidate_vector = candidate["placement_objective_vector"]
    best_vector = best["placement_objective_vector"]
    candidate_should = int(candidate_vector["should_adjacency"]["satisfied_count"])
    best_should = int(best_vector["should_adjacency"]["satisfied_count"])
    if candidate_should != best_should:
        return 1 if candidate_should > best_should else -1
    if preferred_loading_side in {"NORTH", "EAST", "SOUTH", "WEST"}:
        candidate_match = bool(candidate_vector["loading_side"].get("match"))
        best_match = bool(best_vector["loading_side"].get("match"))
        if candidate_match != best_match:
            return 1 if candidate_match else -1
    elif preferred_loading_side == "NEAREST_TRUCK_ENTRANCE":
        candidate_distance = Fraction(str(candidate_vector["loading_side"]["distance_squared_mm2"]))
        best_distance = Fraction(str(best_vector["loading_side"]["distance_squared_mm2"]))
        if candidate_distance != best_distance:
            return 1 if candidate_distance < best_distance else -1
    return 0


def placement_candidate_canonical_tiebreak_key(candidate: Mapping[str, Any]) -> str:
    """Return stable serialization used only after all objectives compare equal."""
    return canonical_json(
        {
            key: value
            for key, value in candidate.items()
            if key
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


def _validate_main_process_skeleton_graph(
    graph: AdjacencyGraphV1, placed: Mapping[str, PlacedRectangleV1]
) -> None:
    """Validate the seven-zone main-chain subset without requiring tail zones."""
    if set(placed) != set(MAIN_PROCESS_ZONE_CODES):
        raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
    main_codes = set(MAIN_PROCESS_ZONE_CODES)
    main_must_pairs = tuple(
        pair for pair in graph.must_adjacencies if pair[0] in main_codes and pair[1] in main_codes
    )
    must_satisfied, must_unsatisfied = _pair_rows(main_must_pairs, placed)
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
    truck_maneuver_binding: Any
    truck_node_budget: int
    truck_maneuver_validator: Callable[..., Mapping[str, Any]] | None
    complete_candidate_limit: int | None
    boundary: PolygonMM
    boundary_bounds: tuple[int, int, int, int]
    main_entrance: SegmentMM
    obstacles: tuple[PolygonMM, ...]
    preferred_loading_side: str
    placement_zone_order: tuple[str, ...]
    structural_composition_family: StructuralCompositionFamilyV1
    structural_skeleton: StructuralSkeletonV1
    structured_building_plan: StructuredBuildingSkeletonV1 | None
    structural_topology: str
    search_phase: str
    direct_synthesis_enabled: bool
    global_main_process_geometry_registry: dict[str, dict[str, Any]] | None
    global_cross_topology_duplicate_trace: list[dict[str, Any]] | None


def _legacy_compatibility_search_plan(
    *,
    boundary: PolygonMM,
    obstacles: tuple[PolygonMM, ...],
    authorities: Mapping[str, Mapping[str, Any]],
    process_axis: str,
    process_direction: str,
    topology: str,
    main_entrance: SegmentMM,
) -> StructuredBuildingSkeletonV1:
    """Build the isolated R1-compatible topology lane search context."""
    return construct_legacy_compatibility_search_plan_v1(
        boundary=boundary,
        obstacles=obstacles,
        authorities=authorities,
        process_axis=process_axis,
        process_direction=process_direction,
        layout_family=structured_layout_family_for_topology(topology),
        main_entrance=main_entrance,
    )


@dataclass
class _PlacementSearchStats:
    visited_nodes: int = 0
    generated_candidates: int = 0
    complete_candidates: int = 0
    node_budget_exhausted: bool = False
    structured_main_skeleton_completions: dict[str, int] | None = None
    structured_core_root_completions: dict[str, int] | None = None
    constructed_main_skeletons: dict[str, MainProcessSkeletonCandidateV1] | None = None
    skeleton_generation_patterns: dict[str, int] | None = None
    rejection_reason_counts: dict[str, int] | None = None
    skeleton_construction_attempts: list[dict[str, Any]] | None = None
    skeleton_search_truncated: bool = False
    root_preflight_rows: list[dict[str, Any]] | None = None
    tail_nodes_by_skeleton: dict[str, int] | None = None
    skeleton_tail_lifecycle: list[dict[str, Any]] | None = None
    construction_nodes_by_skeleton: dict[str, int] | None = None
    tail_zone_search_facts: dict[str, dict[str, dict[str, int]]] | None = None
    topology_ownership_duplicates: list[dict[str, Any]] | None = None
    offset_transition_trace: list[dict[str, Any]] | None = None
    constructive_divergence_attempts: list[dict[str, Any]] | None = None
    topology_classification_failures: list[dict[str, Any]] | None = None
    geometry_evaluation_admissions: list[dict[str, Any]] | None = None
    tail_slot_preflight_rows: list[dict[str, Any]] | None = None
    main_skeleton_truck_preflight_rows: list[dict[str, Any]] | None = None
    cross_topology_duplicate_count: int = 0
    quantum_node_limit: int | None = None
    quantum_nodes_visited: int = 0
    quantum_nodes_by_layout_family: dict[str, int] | None = None
    current_work_item: dict[str, Any] | None = None
    normal_stop_reason: str | None = None
    construction_node_count: int = 0


@dataclass(frozen=True)
class _SearchQuantumYield:
    """Internal cooperative yield; the owning generator remains resumable."""

    work_item: Mapping[str, Any] | None


@dataclass(frozen=True)
class PlacementCandidateQuantumAdvanceV1:
    """One bounded advance of a persistent P2C candidate stream."""

    candidates: tuple[SitePlacementResultV1, ...]
    nodes_visited: int
    status: str
    work_item: Mapping[str, Any] | None
    search_exhausted: bool
    completed: bool


def _quantum_checkpoint(stats: _PlacementSearchStats) -> _SearchQuantumYield | None:
    if stats.quantum_node_limit is None:
        return None
    work_item = dict(stats.current_work_item) if stats.current_work_item is not None else None
    if work_item is not None and isinstance(work_item.get("band_family"), str):
        if stats.quantum_nodes_by_layout_family is None:
            stats.quantum_nodes_by_layout_family = {}
        family = f"{work_item.get('topology', 'UNCLASSIFIED')}:{work_item['band_family']}"
        visited = stats.quantum_nodes_by_layout_family.get(family, 0) + 1
        if visited < stats.quantum_node_limit:
            stats.quantum_nodes_by_layout_family[family] = visited
            return None
        stats.quantum_nodes_by_layout_family[family] = 0
        return _SearchQuantumYield(work_item)
    stats.quantum_nodes_visited += 1
    if stats.quantum_nodes_visited < stats.quantum_node_limit:
        return None
    stats.quantum_nodes_visited = 0
    return _SearchQuantumYield(work_item)


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
    truck_maneuver_binding: Any = None,
    truck_node_budget: int = 20_000,
    truck_maneuver_validator: Callable[..., Mapping[str, Any]] | None = None,
    complete_candidate_limit: int | None,
    structural_family: StructuralCompositionFamilyV1 | None = None,
    structural_topology: str | None = None,
    search_phase: str = LEGACY_COMPAT_PHASE,
    direct_synthesis_enabled: bool = True,
    global_main_process_geometry_registry: dict[str, dict[str, Any]] | None = None,
    global_cross_topology_duplicate_trace: list[dict[str, Any]] | None = None,
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
    selected_topology = structural_topology or (
        CENTRAL_PROCESS_HUB
        if selected_family.family == CENTRAL_PROCESS_HUB
        else STRAIGHT_LINEAR_BAND
    )
    if selected_topology not in {
        STRAIGHT_LINEAR_BAND,
        OFFSET_LINEAR_BAND,
        CENTRAL_PROCESS_HUB,
    }:
        raise _error("MAIN_PROCESS_TOPOLOGY_INVALID")
    if (selected_topology == CENTRAL_PROCESS_HUB) != (
        selected_family.family == CENTRAL_PROCESS_HUB
    ):
        raise _error("MAIN_PROCESS_TOPOLOGY_FAMILY_MISMATCH")
    skeletons = structural_skeleton_candidates(
        site_body,
        tuple(authorities),
        zone_authorities=authorities,
        family_candidates=(selected_family,),
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
    structured_building_plan: StructuredBuildingSkeletonV1 | None = None
    if search_phase == STRUCTURED_PHASE:
        # Direct synthesis is admitted only with a real program-derived plan.
        for layout_family in BASE_LAYOUT_FAMILIES:
            for envelope_family in (RECTANGLE, SIMPLE_L):
                try:
                    structured_building_plan = construct_structured_building_plan_v1(
                        boundary=boundary,
                        obstacles=obstacles,
                        authorities=authorities,
                        process_axis=skeleton.ordering_axis,
                        layout_family=layout_family,
                        envelope_family=envelope_family,
                        main_entrance=main_entrance,
                    )
                except LayoutAuthorityError:
                    continue
                break
            if structured_building_plan is not None:
                break
    elif search_phase == GENERAL_FALLBACK_PHASE:
        # Compatibility search remains in the original whole-site search
        # domain.  The R2 envelope/band plan is a separate candidate source
        # and must not constrain the fallback that protects existing callers.
        structured_building_plan = _legacy_compatibility_search_plan(
            boundary=boundary,
            obstacles=obstacles,
            authorities=authorities,
            process_axis=skeleton.ordering_axis,
            process_direction=(
                selected_family.dominant_direction
                if selected_family.dominant_direction in {"POSITIVE", "NEGATIVE"}
                else "POSITIVE"
            ),
            topology=selected_topology,
            main_entrance=main_entrance,
        )
    elif search_phase != LEGACY_COMPAT_PHASE:
        raise _error("PLACEMENT_SEARCH_PHASE_INVALID", search_phase=search_phase)
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
        truck_maneuver_binding=truck_maneuver_binding,
        truck_node_budget=truck_node_budget,
        truck_maneuver_validator=truck_maneuver_validator,
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
        structured_building_plan=structured_building_plan,
        structural_topology=selected_topology,
        search_phase=search_phase,
        direct_synthesis_enabled=direct_synthesis_enabled,
        global_main_process_geometry_registry=global_main_process_geometry_registry,
        global_cross_topology_duplicate_trace=global_cross_topology_duplicate_trace,
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
        # A hub is side-organized, not a one-dimensional three-band projection:
        # raw and finished groups must attach to distinct sorting faces, while
        # each group retains its explicit adjacent process chain.
        return finished_side is not None and finished_side != raw_side
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


def _topology_geometry_valid(
    placed: Mapping[str, PlacedRectangleV1], topology: str, longitudinal_axis: str
) -> bool:
    """Require the lane to own its exact geometry under canonical precedence."""
    classification = classify_main_process_topology_v1(placed)
    if classification.canonical_owner != topology:
        return False
    if topology in {STRAIGHT_LINEAR_BAND, OFFSET_LINEAR_BAND}:
        return classification.process_axis == longitudinal_axis
    return topology == CENTRAL_PROCESS_HUB


def _packaging_tail_slot_preflight(
    context: _PlacementSearchContext,
    skeleton: MainProcessSkeletonCandidateV1,
) -> dict[str, Any]:
    authority = context.authorities["packaging_material_storage"]
    dimension_variants = _dimension_variants(authority, {}, context.boundary)
    proof = evaluate_tail_zone_slot_feasibility_v1(
        zone_code="packaging_material_storage",
        dimension_variants=dimension_variants,
        dimension_authority_complete=_authority_mode(authority)
        in {"FIXED_RECTANGLE", "DETERMINISTIC_GRID_RECTANGLE"},
        boundary=context.boundary,
        obstacles=context.obstacles,
        fixed_main_process_rectangles=skeleton.zone_rectangles,
    )
    return proof.to_dict()


def _truck_maneuver_preflight_decision(result: Mapping[str, Any]) -> tuple[str, str | None]:
    """Reject only a completed authoritative search with no truck witness."""
    if result.get("truck_route_validated") is True:
        return "PASS", None
    search = result.get("search_provenance")
    search = search if isinstance(search, Mapping) else {}
    if (
        result.get("status") == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
        and search.get("search_tree_exhausted") is True
        and search.get("node_budget_exhausted") is False
    ):
        return "REJECT", "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
    if search.get("node_budget_exhausted") is True:
        return "UNRESOLVED", "TRUCK_MANEUVER_SEARCH_BUDGET_EXHAUSTED"
    return "UNRESOLVED", None


def _main_skeleton_truck_maneuver_preflight(
    context: _PlacementSearchContext,
    skeleton: MainProcessSkeletonCandidateV1,
) -> dict[str, Any]:
    """Apply the existing truck authority to only the frozen seven-zone skeleton.

    A completed no-route search is a necessary-condition rejection. Missing
    authority and bounded-search exhaustion are unresolved and still proceed
    to the normal tail/P2D path, where the existing fail-closed result remains
    authoritative.
    """
    zones = {rectangle.zone_code: rectangle for rectangle in skeleton.zone_rectangles}
    if set(zones) != set(MAIN_PROCESS_SKELETON_ZONE_CODES):
        raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
    loading_side, loading_face, _, _ = _loading_face(zones["shipping_channel"], context.site_body)
    validator = context.truck_maneuver_validator
    if validator is None:
        return {
            "preflight_name": "MAIN_SKELETON_TRUCK_MANEUVER_NECESSARY_CONDITION_V1",
            "main_skeleton_hash": skeleton.main_process_skeleton_hash,
            "preflight_status": "UNRESOLVED",
            "preflight_action": "ALLOW_TAIL_SEARCH",
            "tail_search_started": False,
            "truck_route_validated": False,
            "failure_codes": ["TRUCK_PREFLIGHT_AUTHORITY_NOT_INJECTED"],
            "failure_reason": None,
            "search_profile_identity": None,
            "visited_nodes": 0,
            "node_budget": context.truck_node_budget,
            "node_budget_exhausted": False,
            "search_tree_exhausted": False,
            "shipping_loading_face_side": loading_side,
            "shipping_loading_face_segment": {
                "start": {"x": _m(loading_face[0][0]), "y": _m(loading_face[0][1])},
                "end": {"x": _m(loading_face[1][0]), "y": _m(loading_face[1][1])},
            },
            "zones_checked": list(MAIN_PROCESS_SKELETON_ZONE_CODES),
            "truck_validation_result_hash": None,
        }
    result = validator(
        context.truck_maneuver_binding,
        truck_entrance=_truck_segment(context.site_body),
        shipping_loading_face=loading_face,
        boundary=context.boundary,
        obstacles=context.obstacles,
        zones=zones,
        node_budget=context.truck_node_budget,
    )
    status, failure_reason = _truck_maneuver_preflight_decision(result)
    search = result.get("search_provenance")
    search = search if isinstance(search, Mapping) else {}
    face_segment = {
        "start": {"x": _m(loading_face[0][0]), "y": _m(loading_face[0][1])},
        "end": {"x": _m(loading_face[1][0]), "y": _m(loading_face[1][1])},
    }
    return {
        "preflight_name": "MAIN_SKELETON_TRUCK_MANEUVER_NECESSARY_CONDITION_V1",
        "main_skeleton_hash": skeleton.main_process_skeleton_hash,
        "preflight_status": status,
        "preflight_action": "REJECT_SKELETON" if status == "REJECT" else "ALLOW_TAIL_SEARCH",
        "tail_search_started": False,
        "truck_route_validated": result.get("truck_route_validated") is True,
        "failure_codes": list(result.get("codes", [])),
        "failure_reason": failure_reason,
        "search_profile_identity": result.get("search_profile_identity"),
        "visited_nodes": int(search.get("visited_nodes", 0)),
        "node_budget": int(search.get("node_budget", context.truck_node_budget)),
        "node_budget_exhausted": search.get("node_budget_exhausted") is True,
        "search_tree_exhausted": search.get("search_tree_exhausted") is True,
        "shipping_loading_face_side": loading_side,
        "shipping_loading_face_segment": face_segment,
        "zones_checked": list(MAIN_PROCESS_SKELETON_ZONE_CODES),
        "truck_validation_result_hash": result.get("canonical_result_hash"),
    }


def _shipping_loading_face_approach_axis_penalty(
    context: _PlacementSearchContext, rectangle: PlacedRectangleV1
) -> int:
    """Prefer a loading-face axis aligned with the approach normal.

    This is an exact, categorical branch-order fact derived from the existing
    truck-entrance segment and the shared loading-face authority. It is not a
    hard prune; the authoritative maneuver validator still decides admission.
    """
    _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
    entrance = _truck_segment(context.site_body)
    entrance_is_vertical = entrance[0][0] == entrance[1][0]
    loading_face_is_horizontal = loading_face[0][1] == loading_face[1][1]
    return int(entrance_is_vertical != loading_face_is_horizontal)


def _loading_face_dock_endpoint_penalty(
    context: _PlacementSearchContext, rectangle: PlacedRectangleV1
) -> int:
    """Visit exact dock events at loading-face endpoints before interior events."""
    _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
    dock_points = _truck_dock_points_at_entrance(context)
    if any(point == loading_face[0] or point == loading_face[1] for point in dock_points):
        return 0
    if any(_on_segment(point, loading_face[0], loading_face[1]) for point in dock_points):
        return 1
    return 2


def _shipping_options_by_loading_face_approach(
    context: _PlacementSearchContext,
    options: Sequence[PlacedRectangleV1],
) -> tuple[PlacedRectangleV1, ...]:
    """Keep established edge options ahead of added dock-event branches."""
    del context
    return tuple(options)


def _interleave_finished_truck_interface_options(
    options: Sequence[PlacedRectangleV1],
    truck_interface_only_bounds: set[tuple[int, int, int, int]],
) -> tuple[PlacedRectangleV1, ...]:
    """Sample a dock-paired finished-room branch without starving legacy options."""
    ordered = tuple(options)
    established = tuple(row for row in ordered if _bounds(row) not in truck_interface_only_bounds)
    interface = tuple(row for row in ordered if _bounds(row) in truck_interface_only_bounds)
    if not established or not interface:
        return ordered
    return (established[0], interface[0], *established[1:], *interface[1:])


def _finished_options_by_shipping_approach(
    context: _PlacementSearchContext,
    placed: Mapping[str, PlacedRectangleV1],
    options: Sequence[PlacedRectangleV1],
) -> tuple[PlacedRectangleV1, ...]:
    """Preserve the established finished-room branch order deterministically."""
    del context, placed
    return tuple(options)


def _constructive_main_skeleton_tail_admission(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
    skeleton: MainProcessSkeletonCandidateV1,
) -> bool:
    """Admit only tail-capable, truck-feasible skeletons to completion quota.

    Both checks reuse their existing exact authorities.  A failed candidate is
    recorded in the geometry registry and the constructive generator may
    continue to its next shipping/interface branch without spending a tail
    search or skeleton-completion slot.
    """
    geometry_hash = skeleton.main_process_skeleton_hash
    registry = context.global_main_process_geometry_registry
    existing = registry.get(geometry_hash) if registry is not None else None
    first_discovery_topology = (
        str(existing.get("first_discovery_topology"))
        if existing is not None and existing.get("first_discovery_topology") is not None
        else context.structural_topology
    )

    if existing is not None and existing.get("tail_search_started") is True:
        duplicate_row = {
            "event": "EXISTING_GEOMETRY_DUPLICATE_DISCOVERY",
            "skeleton_hash": geometry_hash,
            "first_discovery_topology": first_discovery_topology,
            "duplicate_discovery_topology": context.structural_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "tail_search_started_by_topology": existing.get("tail_search_discovery_topology"),
            "cross_topology_duplicate": first_discovery_topology != context.structural_topology,
            "duplicate_action": "SKIP_ALREADY_EVALUATED_GEOMETRY",
        }
        if stats.topology_ownership_duplicates is None:
            stats.topology_ownership_duplicates = []
        stats.topology_ownership_duplicates.append(duplicate_row)
        if duplicate_row["cross_topology_duplicate"]:
            stats.cross_topology_duplicate_count += 1
            if context.global_cross_topology_duplicate_trace is not None:
                context.global_cross_topology_duplicate_trace.append(duplicate_row)
        return False

    packaging_status = existing.get("packaging_preflight_status") if existing else None
    if packaging_status is None:
        packaging = _packaging_tail_slot_preflight(context, skeleton)
        proof_mode = str(packaging["proof_mode"])
        slot_exists = packaging["legal_slot_exists"]
        packaging_status = (
            "NO_LEGAL_SLOT"
            if slot_exists is False and proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION
            else "LEGAL_SLOT_EXISTS"
            if slot_exists is True
            else "UNAVAILABLE"
        )
        packaging_row = {
            "event": "TAIL_SLOT_PREFLIGHT_CONSTRUCTION_GATE",
            "stage": "TAIL_SLOT_PREFLIGHT",
            "skeleton_hash": geometry_hash,
            "discovery_topology": context.structural_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "canonical_family": skeleton.family.to_dict(),
            "packaging_preflight_status": packaging_status,
            "packaging_slot_exists": slot_exists,
            "tail_admissible": (
                False
                if packaging_status == "NO_LEGAL_SLOT"
                else None
                if packaging_status == "UNAVAILABLE"
                else True
            ),
            "tail_search_started": False,
            "preflight_reexecuted": True,
            "preflight": packaging,
        }
        if stats.tail_slot_preflight_rows is None:
            stats.tail_slot_preflight_rows = []
        stats.tail_slot_preflight_rows.append(packaging_row)
    else:
        slot_exists = existing.get("packaging_slot_exists") if existing else None

    registry_row = existing if existing is not None else {}
    registry_row.update(
        {
            "skeleton_hash": geometry_hash,
            "first_discovery_topology": first_discovery_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "canonical_family": skeleton.family.to_dict(),
            "packaging_preflight_status": packaging_status,
            "packaging_slot_exists": slot_exists,
            "tail_admissible": (
                False
                if packaging_status == "NO_LEGAL_SLOT"
                else None
                if packaging_status == "UNAVAILABLE"
                else True
            ),
            "tail_search_started": False,
        }
    )
    if registry is not None:
        registry[geometry_hash] = registry_row

    if packaging_status == "NO_LEGAL_SLOT":
        _record_rejection(stats, "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT")
        if stats.skeleton_tail_lifecycle is None:
            stats.skeleton_tail_lifecycle = []
        stats.skeleton_tail_lifecycle.append(
            {
                "topology": skeleton.topology,
                "skeleton_hash": geometry_hash,
                "discovery_topology": context.structural_topology,
                "canonical_topology_owner": skeleton.canonical_topology_owner,
                "canonical_family": skeleton.family.to_dict(),
                "packaging_preflight_executed": True,
                "packaging_slot_exists": False,
                "tail_admissible": False,
                "tail_search_started": False,
                "tail_nodes": 0,
                "tail_node_limit": 0,
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "first_failure_stage": "TAIL_SLOT_PREFLIGHT",
                "first_failure_reason": "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT",
            }
        )
        return False

    cached_truck_preflight = registry_row.get("main_skeleton_truck_preflight")
    if isinstance(cached_truck_preflight, Mapping):
        truck_row = dict(cached_truck_preflight)
        truck_row.update(
            {
                "event": "CACHED_MAIN_SKELETON_TRUCK_PREFLIGHT_CONSTRUCTION_GATE",
                "discovery_topology": context.structural_topology,
                "preflight_reexecuted": False,
                "preflight_compute_nodes": 0,
            }
        )
    else:
        truck_result = _main_skeleton_truck_maneuver_preflight(context, skeleton)
        planned_envelope_bounds = getattr(skeleton, "planned_envelope_bounds_mm", None)
        truck_row = {
            **truck_result,
            "event": "MAIN_SKELETON_TRUCK_PREFLIGHT_CONSTRUCTION_GATE",
            "stage": "MAIN_SKELETON_TRUCK_PREFLIGHT",
            "discovery_topology": context.structural_topology,
            "canonical_topology_owner": skeleton.canonical_topology_owner,
            "canonical_family": skeleton.family.to_dict(),
            "layout_family": getattr(skeleton, "building_layout_family", None),
            "envelope_family": getattr(skeleton, "building_envelope_family", None),
            "planned_envelope_bounds_mm": (
                list(planned_envelope_bounds)
                if isinstance(planned_envelope_bounds, tuple)
                else None
            ),
            "preflight_reexecuted": True,
            "preflight_compute_nodes": int(truck_result["visited_nodes"]),
        }
        registry_row["main_skeleton_truck_preflight"] = dict(truck_row)
        registry_row.setdefault("p2d_reached", False)
        registry_row.setdefault("p2d_candidate_count", 0)
        registry_row.setdefault("p2d_full_pass_count", 0)
        if registry is not None:
            registry[geometry_hash] = registry_row

    if truck_row["preflight_status"] == "REJECT":
        if stats.main_skeleton_truck_preflight_rows is None:
            stats.main_skeleton_truck_preflight_rows = []
        stats.main_skeleton_truck_preflight_rows.append(truck_row)
        _record_rejection(
            stats,
            str(truck_row.get("failure_reason") or "TRUCK_MANEUVER_SEARCH_EXHAUSTED"),
        )
        if stats.skeleton_tail_lifecycle is None:
            stats.skeleton_tail_lifecycle = []
        stats.skeleton_tail_lifecycle.append(
            {
                "topology": skeleton.topology,
                "skeleton_hash": geometry_hash,
                "discovery_topology": context.structural_topology,
                "canonical_topology_owner": skeleton.canonical_topology_owner,
                "canonical_family": skeleton.family.to_dict(),
                "packaging_preflight_executed": True,
                "packaging_preflight_status": packaging_status,
                "packaging_slot_exists": slot_exists,
                "main_skeleton_truck_preflight_executed": True,
                "main_skeleton_truck_preflight_status": "REJECT",
                "truck_preflight_failure_codes": list(truck_row.get("failure_codes", [])),
                "truck_preflight_visited_nodes": int(truck_row.get("visited_nodes", 0)),
                "truck_preflight_node_budget": int(truck_row.get("node_budget", 0)),
                "truck_preflight_node_budget_exhausted": truck_row.get("node_budget_exhausted"),
                "truck_preflight_search_tree_exhausted": truck_row.get("search_tree_exhausted"),
                "tail_search_started": False,
                "tail_nodes": 0,
                "tail_node_limit": 0,
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "first_failure_stage": "MAIN_SKELETON_TRUCK_PREFLIGHT",
                "first_failure_reason": (
                    truck_row.get("failure_reason") or "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
                ),
            }
        )
        return False
    return True


def _direct_candidate_plan(
    plan: StructuredBuildingSkeletonV1,
    placements: Mapping[str, PlacedRectangleV1],
) -> StructuredBuildingSkeletonV1:
    """Attach synthesized zones to the exact envelope/grid/bands that planned them."""
    return plan.with_placements(placements)


def _synthesize_linear_3_band_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    del shipping
    candidates = _linear_3_band_geometry(context, plan, variant_index, failure_reasons)
    if not candidates:
        if not failure_reasons:
            failure_reasons.append("LINEAR_3_BAND_JOINT_PACKING_OR_MUST_INTERFACE_UNAVAILABLE")
        return None
    return candidates[0]


def _synthesize_central_process_with_side_banks_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    del shipping
    candidates = _central_side_bank_geometry(context, plan, variant_index, failure_reasons)
    if not candidates:
        if not failure_reasons:
            failure_reasons.append("CENTRAL_SIDE_BANK_JOINT_PACKING_OR_MUST_INTERFACE_UNAVAILABLE")
        return None
    return candidates[0]


def _synthesize_longitudinal_process_spine_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    del shipping
    candidates = _longitudinal_spine_geometry(context, plan, variant_index, failure_reasons)
    if not candidates:
        if not failure_reasons:
            failure_reasons.append("LONGITUDINAL_SPINE_JOINT_PACKING_OR_MUST_INTERFACE_UNAVAILABLE")
        return None
    return candidates[0]


def _synthesize_family_main_process(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    shipping: PlacedRectangleV1 | None,
    *,
    variant_index: int,
    failure_reasons: list[str],
) -> dict[str, PlacedRectangleV1] | None:
    # The shipping rectangle is now packed together with the other finished
    # band members. Keep the positional parameter for the stable internal
    # call seam, but do not use it as a room-chain root.
    del shipping
    constructors = {
        LINEAR_3_BAND: _synthesize_linear_3_band_main_process,
        CENTRAL_PROCESS_WITH_SIDE_BANKS: _synthesize_central_process_with_side_banks_main_process,
        LONGITUDINAL_PROCESS_SPINE: _synthesize_longitudinal_process_spine_main_process,
    }
    constructor = constructors.get(plan.layout_family)
    if constructor is None:
        failure_reasons.append("DIRECT_LAYOUT_FAMILY_SYNTHESIZER_UNAVAILABLE")
        return None
    return constructor(
        context,
        plan,
        None,
        variant_index=variant_index,
        failure_reasons=failure_reasons,
    )


def synthesize_band_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    band_code: str,
    zone_codes: Sequence[str],
    *,
    packing_axis: str,
    reverse_order: bool,
    cross_alignment: str,
    fixed_placements: Mapping[str, PlacedRectangleV1] | None = None,
    transition_zone_codes: frozenset[str] = frozenset(),
    result_limit: int = 12,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Pack a whole functional band from its bounds and cumulative dimensions.

    This is a finite row/column composition: coordinates are calculated once
    from authoritative room dimensions and the selected band edge. It does
    not enumerate site/event coordinates or grow a room-by-room DFS chain.
    """
    if packing_axis not in {"X", "Y"} or cross_alignment not in {"LOW", "CENTER", "HIGH"}:
        return ()
    if result_limit <= 0 or not zone_codes:
        return ()
    band = plan.band_for_zone(zone_codes[0])
    if (
        band.band_code != band_code
        or any(
            plan.band_for_zone(code).band_code != band_code and code not in transition_zone_codes
            for code in zone_codes
        )
        or not transition_zone_codes
        <= set(next(row.transition_zone_codes for row in plan.bands if row.band_code == band_code))
    ):
        return ()
    # Pack from the declared band bounds, not one tile at a time. The band
    # predicate validates exact coverage by the region union, while the
    # existing site and no-build predicates remain the authoritative gates.
    left, bottom, right, top = band.bounds_mm
    along_low, along_high = (left, right) if packing_axis == "X" else (bottom, top)
    cross_low, cross_high = (bottom, top) if packing_axis == "X" else (left, right)
    along_span = along_high - along_low
    cross_span = cross_high - cross_low
    order = tuple(reversed(zone_codes)) if reverse_order else tuple(zone_codes)

    choices_by_zone: list[tuple[tuple[int, int, int, int, int], ...]] = []
    for code in order:
        authority = context.authorities.get(code)
        if authority is None:
            return ()
        unique: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
        for width_mm, depth_mm in _zone_dimension_options(authority):
            for rotation in (0, 90):
                actual_width, actual_depth = (
                    (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
                )
                if packing_axis == "X":
                    along_extent, cross_extent = actual_width, actual_depth
                else:
                    along_extent, cross_extent = actual_depth, actual_width
                if along_extent > along_span or cross_extent > cross_span:
                    continue
                unique.setdefault(
                    (actual_width, actual_depth),
                    (width_mm, depth_mm, rotation, along_extent, cross_extent),
                )
        variants = tuple(unique[key] for key in sorted(unique))
        if not variants:
            return ()
        choices_by_zone.append(variants)

    candidates: list[dict[str, PlacedRectangleV1]] = []
    seen: set[tuple[tuple[str, tuple[int, int, int, int, int]], ...]] = set()
    for dimension_rows in product(*choices_by_zone):
        total_along = sum(row[3] for row in dimension_rows)
        max_cross = max(row[4] for row in dimension_rows)
        if total_along > along_span or max_cross > cross_span:
            continue
        cursor = along_high - total_along if reverse_order else along_low
        packed: dict[str, PlacedRectangleV1] = {}
        valid = True
        for code, (width_mm, depth_mm, rotation, along_extent, cross_extent) in zip(
            order, dimension_rows, strict=True
        ):
            if cross_alignment == "LOW":
                cross_origin = cross_low
            elif cross_alignment == "HIGH":
                cross_origin = cross_high - cross_extent
            else:
                cross_origin = cross_low + (cross_span - cross_extent) // 2
            if packing_axis == "X":
                x_mm, y_mm = cursor, cross_origin
            else:
                x_mm, y_mm = cross_origin, cursor
            rectangle = _rectangle_from_mm(code, x_mm, y_mm, width_mm, depth_mm, rotation)
            if (
                not plan.admits_to_band(code, rectangle, band_code)
                or _geometry_rejection_reason(
                    rectangle, {**(fixed_placements or {}), **packed}, context
                )
                is not None
            ):
                valid = False
                break
            packed[code] = rectangle
            cursor += -along_extent if reverse_order else along_extent
        if not valid:
            continue
        signature = tuple(
            sorted(
                (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                for code, rectangle in packed.items()
            )
        )
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append(packed)
        if len(candidates) >= result_limit:
            break
    return tuple(candidates)


def _band_chain_shape_options(
    context: _PlacementSearchContext, zone_code: str
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Return unique authority-derived post-rotation shapes for a band member."""
    authority = context.authorities.get(zone_code)
    if authority is None:
        return ()
    unique: dict[tuple[int, int], tuple[int, int, int, int, int]] = {}
    for width_mm, depth_mm in _zone_dimension_options(authority):
        for rotation in (0, 90):
            actual_width, actual_depth = (
                (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
            )
            unique.setdefault(
                (actual_width, actual_depth),
                (width_mm, depth_mm, rotation, actual_width, actual_depth),
            )
    return tuple(unique[key] for key in sorted(unique))


def _band_edge_chain_origins(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    band_code: str,
    first_zone: str,
    width_mm: int,
    depth_mm: int,
    fixed_placements: Mapping[str, PlacedRectangleV1],
) -> tuple[tuple[int, int], ...]:
    """Derive finite root origins from band boundaries or an exact MUST edge."""
    mandatory_neighbors = tuple(
        neighbor for neighbor in _must_neighbors(first_zone, fixed_placements, context.graph)
    )
    origins: set[tuple[int, int]] = set()
    for neighbor in mandatory_neighbors:
        origins.update(_edge_anchors(neighbor, width_mm, depth_mm))
    if not origins:
        left, bottom, right, top = plan.band_for_zone(first_zone).bounds_mm
        x_positions = {left, right - width_mm, left + (right - left - width_mm) // 2}
        y_positions = {bottom, top - depth_mm, bottom + (top - bottom - depth_mm) // 2}
        origins.update((x, y) for x in x_positions for y in y_positions)
    return tuple(sorted(origins))


def synthesize_must_chain_band_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    band_code: str,
    zone_codes: Sequence[str],
    *,
    fixed_placements: Mapping[str, PlacedRectangleV1] | None = None,
    transition_zone_codes: frozenset[str] = frozenset(),
    result_limit: int = 12,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Jointly enumerate finite orthogonal MUST-chain patterns inside a band.

    A pattern is selected as a complete discrete combination of authoritative
    room dimensions, cardinal edge transitions, and shared-edge alignments.
    Coordinates are derived only from the first band's exact edge anchor and
    successive shared rectangle edges; no local-event-axis or free-coordinate
    search is used. The full pattern is accepted only after exact band, site,
    obstacle, overlap, and positive-edge predicates pass.
    """
    if len(zone_codes) < 2 or result_limit <= 0:
        return ()
    band = plan.band_for_zone(zone_codes[0])
    if (
        band.band_code != band_code
        or any(
            plan.band_for_zone(code).band_code != band_code and code not in transition_zone_codes
            for code in zone_codes
        )
        or not transition_zone_codes
        <= set(next(row.transition_zone_codes for row in plan.bands if row.band_code == band_code))
    ):
        return ()

    fixed = dict(fixed_placements or {})
    shape_options = tuple(_band_chain_shape_options(context, code) for code in zone_codes)
    if any(not rows for rows in shape_options):
        return ()
    side_sequences = _must_chain_side_sequences(len(zone_codes) - 1)
    alignment_sequences = _must_chain_alignment_sequences(len(zone_codes) - 1)
    results: list[dict[str, PlacedRectangleV1]] = []
    signatures: set[tuple[tuple[str, tuple[int, int, int, int, int]], ...]] = set()

    for shapes in product(*shape_options):
        first_width, first_depth = shapes[0][3], shapes[0][4]
        origins = _band_edge_chain_origins(
            context,
            plan,
            band_code,
            zone_codes[0],
            first_width,
            first_depth,
            fixed,
        )
        for origin_x, origin_y in origins:
            first = _rectangle_from_mm(
                zone_codes[0], origin_x, origin_y, shapes[0][0], shapes[0][1], shapes[0][2]
            )
            if not plan.admits_to_band(zone_codes[0], first, band_code) or any(
                rectangles_overlap(first, other) for other in fixed.values()
            ):
                continue
            for side_sequence in side_sequences:
                for alignment_sequence in alignment_sequences:
                    packed: dict[str, PlacedRectangleV1] = {zone_codes[0]: first}
                    valid = True
                    for index, (side, alignment) in enumerate(
                        zip(side_sequence, alignment_sequence, strict=True), start=1
                    ):
                        previous = packed[zone_codes[index - 1]]
                        width_mm, depth_mm, rotation, actual_width, actual_depth = shapes[index]
                        left, bottom, right, top = previous.bounds_mm
                        if side in {"EAST", "WEST"}:
                            y_origin = (
                                bottom
                                if alignment == "LOW"
                                else top - actual_depth
                                if alignment == "HIGH"
                                else bottom + (top - bottom - actual_depth) // 2
                            )
                            x_origin = right if side == "EAST" else left - actual_width
                        else:
                            x_origin = (
                                left
                                if alignment == "LOW"
                                else right - actual_width
                                if alignment == "HIGH"
                                else left + (right - left - actual_width) // 2
                            )
                            y_origin = top if side == "NORTH" else bottom - actual_depth
                        rectangle = _rectangle_from_mm(
                            zone_codes[index], x_origin, y_origin, width_mm, depth_mm, rotation
                        )
                        if (
                            not rectangles_share_positive_edge(previous, rectangle)
                            or not plan.admits_to_band(zone_codes[index], rectangle, band_code)
                            or any(
                                rectangles_overlap(rectangle, other)
                                for other in (*fixed.values(), *packed.values())
                            )
                        ):
                            valid = False
                            break
                        packed[zone_codes[index]] = rectangle
                    if not valid:
                        continue
                    signature = tuple(
                        sorted(
                            (code, rectangle.bounds_mm + (rectangle.rotation_deg,))
                            for code, rectangle in packed.items()
                        )
                    )
                    if signature in signatures:
                        continue
                    signatures.add(signature)
                    results.append(packed)
                    if len(results) >= result_limit:
                        return tuple(results)
    return tuple(results)


def _family_main_band_packings(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    *,
    band_sequence: tuple[tuple[str, tuple[str, ...], str, frozenset[str]], ...],
    variant_index: int,
    failure_reasons: list[str] | None = None,
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    reverse = bool(variant_index % 2)
    alignment = ("LOW", "CENTER", "HIGH")[variant_index % 3]
    merged_candidates: list[dict[str, PlacedRectangleV1]] = []

    def pack_band(index: int, placed: dict[str, PlacedRectangleV1]) -> None:
        if len(merged_candidates) >= 12:
            return
        if index == len(band_sequence):
            try:
                _validate_main_process_skeleton_graph(context.graph, placed)
            except LayoutAuthorityError:
                if failure_reasons is not None and not failure_reasons:
                    failure_reasons.append("GRAPH_HARD_VALIDATION")
                return
            merged_candidates.append(dict(placed))
            return

        spec = band_sequence[index]
        band_code, zone_codes, preferred_axis, transition_zone_codes = spec
        if tuple(zone_codes) in {
            ("raw_fruit_buffer", "primary_precooling_room"),
            (
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            ),
        }:
            rows = synthesize_must_chain_band_geometry(
                context,
                plan,
                band_code,
                zone_codes,
                fixed_placements=placed,
                transition_zone_codes=transition_zone_codes,
                result_limit=3,
            )
            if rows:
                for row in rows:
                    pack_band(index + 1, {**placed, **row})
                    if len(merged_candidates) >= 12:
                        return
            elif failure_reasons is not None and not failure_reasons:
                failure_reasons.append(f"BAND_PACKING_UNAVAILABLE:{band_code}")
            return
        alternate_axis = "Y" if preferred_axis == "X" else "X"
        axis_order = (
            (preferred_axis, alternate_axis) if not reverse else (alternate_axis, preferred_axis)
        )
        found_for_band = False
        for packing_axis in axis_order:
            for band_reverse in (reverse ^ bool(index % 2), not (reverse ^ bool(index % 2))):
                for cross_alignment in (alignment, "LOW", "CENTER", "HIGH"):
                    rows = synthesize_band_geometry(
                        context,
                        plan,
                        band_code,
                        zone_codes,
                        packing_axis=packing_axis,
                        reverse_order=band_reverse,
                        cross_alignment=cross_alignment,
                        fixed_placements=placed,
                        transition_zone_codes=transition_zone_codes,
                        result_limit=12,
                    )
                    if rows:
                        found_for_band = True
                    for row in rows:
                        pack_band(index + 1, {**placed, **row})
                        if len(merged_candidates) >= 12:
                            return
        if not found_for_band and failure_reasons is not None and not failure_reasons:
            failure_reasons.append(f"BAND_PACKING_UNAVAILABLE:{band_code}")

    pack_band(0, {})
    return tuple(merged_candidates)


def _linear_3_band_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    variant_index: int,
    failure_reasons: list[str],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Compose upstream, core, and downstream bands in one process direction."""
    process_axis = plan.process_axis
    return _family_main_band_packings(
        context,
        plan,
        band_sequence=(
            (
                "RAW_SIDE_BAND",
                ("raw_fruit_buffer", "primary_precooling_room"),
                process_axis,
                frozenset(),
            ),
            ("PROCESS_CORE_BAND", ("sorting_packaging_room",), process_axis, frozenset()),
            (
                "FINISHED_SIDE_BAND",
                (
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                ),
                process_axis,
                frozenset({"coating_room"}),
            ),
        ),
        variant_index=variant_index,
        failure_reasons=failure_reasons,
    )


def _central_side_bank_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    variant_index: int,
    failure_reasons: list[str],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Place the process core first, then construct its two opposing banks."""
    cross_axis = "Y" if plan.process_axis == "X" else "X"
    return _family_main_band_packings(
        context,
        plan,
        band_sequence=(
            ("PROCESS_CORE_BAND", ("sorting_packaging_room",), cross_axis, frozenset()),
            (
                "RAW_SIDE_BAND",
                ("raw_fruit_buffer", "primary_precooling_room"),
                plan.process_axis,
                frozenset(),
            ),
            (
                "FINISHED_SIDE_BAND",
                (
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                ),
                plan.process_axis,
                frozenset({"coating_room"}),
            ),
        ),
        variant_index=variant_index,
        failure_reasons=failure_reasons,
    )


def _longitudinal_spine_geometry(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    variant_index: int,
    failure_reasons: list[str],
) -> tuple[dict[str, PlacedRectangleV1], ...]:
    """Set the process spine first, then pack raw and finished side banks."""
    cross_axis = "Y" if plan.process_axis == "X" else "X"
    return _family_main_band_packings(
        context,
        plan,
        band_sequence=(
            ("PROCESS_CORE_BAND", ("sorting_packaging_room",), plan.process_axis, frozenset()),
            (
                "RAW_SIDE_BAND",
                ("raw_fruit_buffer", "primary_precooling_room"),
                cross_axis,
                frozenset(),
            ),
            (
                "FINISHED_SIDE_BAND",
                (
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                ),
                cross_axis,
                frozenset({"coating_room"}),
            ),
        ),
        variant_index=variant_index,
        failure_reasons=failure_reasons,
    )


def _direct_family_tail_zones(
    context: _PlacementSearchContext,
    plan: StructuredBuildingSkeletonV1,
    placed: Mapping[str, PlacedRectangleV1],
    *,
    variant_index: int,
    failure_reasons: list[str] | None = None,
) -> dict[str, PlacedRectangleV1] | None:
    support_axes = ("X", "Y") if variant_index % 2 == 0 else ("Y", "X")
    personnel_axes = ("Y", "X") if variant_index % 2 == 0 else ("X", "Y")
    alignments = ("LOW", "CENTER", "HIGH")
    for support_axis in support_axes:
        support_rows = synthesize_band_geometry(
            context,
            plan,
            SUPPORT_BAND,
            ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
            packing_axis=support_axis,
            reverse_order=bool(variant_index % 2),
            cross_alignment=alignments[variant_index % len(alignments)],
            fixed_placements=placed,
            result_limit=12,
        )
        if not support_rows:
            if failure_reasons is not None:
                failure_reasons.append("SUPPORT_BAND_PACKING_NO_GEOMETRY")
            continue
        for support_row in support_rows:
            with_support = {**placed, **support_row}
            for personnel_axis in personnel_axes:
                personnel_rows = synthesize_band_geometry(
                    context,
                    plan,
                    PERSONNEL_EDGE_BAND,
                    ("office", "changing_room"),
                    packing_axis=personnel_axis,
                    reverse_order=bool((variant_index + 1) % 2),
                    cross_alignment=alignments[(variant_index + 1) % len(alignments)],
                    fixed_placements=with_support,
                    result_limit=12,
                )
                if not personnel_rows:
                    if failure_reasons is not None:
                        failure_reasons.append("PERSONNEL_BAND_PACKING_NO_GEOMETRY")
                    continue
                for personnel_row in personnel_rows:
                    complete = {**with_support, **personnel_row}
                    if set(complete) != set(context.graph.nodes):
                        continue
                    try:
                        _validate_graph_completeness(context.graph, complete)
                    except LayoutAuthorityError:
                        if failure_reasons is not None:
                            failure_reasons.append("GRAPH_HARD_VALIDATION")
                        continue
                    return complete
    if failure_reasons is not None and not failure_reasons:
        failure_reasons.append("TAIL_BAND_PACKING_NO_VALID_COMBINATION")
    return None


def _direct_structured_candidates(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
    """Construct finite complete buildings from envelope/grid/band plans.

    A work node is one complete family/dock-event/mirror construction attempt.
    No local event-axis room DFS is entered in this phase; unsuccessful direct
    synthesis exhausts cleanly so the selector can spend remaining global
    placement nodes in the existing compatibility fallback.
    """
    reference_axis = (
        context.structured_building_plan.process_axis
        if context.structured_building_plan is not None
        else context.structural_skeleton.ordering_axis
    )
    process_axes = tuple(dict.fromkeys((reference_axis, "Y" if reference_axis == "X" else "X")))
    # One node is one family/axis/envelope/support-side structural attempt.
    # Shipping is synthesized from finished-band axes and truck feasibility is
    # applied after the regular building geometry exists.
    default_support_side = (
        context.structured_building_plan.support_side
        if context.structured_building_plan is not None
        else "WEST"
    )
    opposite_support_side = {
        "NORTH": "SOUTH",
        "SOUTH": "NORTH",
        "EAST": "WEST",
        "WEST": "EAST",
    }[default_support_side]
    structural_rounds = tuple(
        (
            axis_index,
            envelope_family,
            opposite_support_side
            if side == "OPPOSITE_SUPPORT_SIDE"
            else default_support_side
            if side == "DEFAULT_SUPPORT_SIDE"
            else side,
            terminal_variant_index,
        )
        for axis_index, envelope_family, side, terminal_variant_index in (
            _DIRECT_STRUCTURAL_VARIANT_ROUNDS
        )
    )
    attempt_specs = [
        (
            layout_family,
            process_axes[axis_index],
            envelope_family,
            0,
            terminal_variant_index,
            side,
        )
        for axis_index, envelope_family, side, terminal_variant_index in structural_rounds
        for layout_family in BASE_LAYOUT_FAMILIES
    ]
    # Each round is a finite structural variant. Family is innermost so all
    # three layout families receive coverage before the scheduler revisits an
    # axis/envelope combination. No room-local event-axis coordinates enter
    # this direct synthesis phase.
    seen_hashes: set[str] = set()
    plan_cache: dict[
        tuple[str, str, str, str, int, str],
        StructuredBuildingSkeletonV1 | LayoutAuthorityError,
    ] = {}
    for attempt_index, (
        layout_family,
        process_axis,
        envelope_family,
        variant_index,
        terminal_variant_index,
        support_side,
    ) in enumerate(attempt_specs):
        process_direction = "NEGATIVE" if variant_index % 2 else "POSITIVE"
        plan_key = (
            layout_family,
            process_axis,
            envelope_family,
            support_side,
            terminal_variant_index,
            process_direction,
        )
        cached_plan = plan_cache.get(plan_key)
        if isinstance(cached_plan, LayoutAuthorityError):
            plan_row = {
                "layout_family": layout_family,
                "process_axis": process_axis,
                "envelope_family": envelope_family,
                "support_side": support_side,
                "terminal_variant_index": terminal_variant_index,
                "construction_nodes": 0,
                "result": "DETERMINISTIC_SYNTHESIS_IMPOSSIBLE",
                "first_failure_stage": "PLAN",
                "rejection_reason": cached_plan.code,
                "reason": cached_plan.code,
                "construction_policy": f"{layout_family}_DIRECT_SYNTHESIS_V1",
                "plan_failure_reused": True,
            }
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(plan_row)
            continue
        try:
            if isinstance(cached_plan, StructuredBuildingSkeletonV1):
                plan = cached_plan
            else:
                plan_error: LayoutAuthorityError | None = None
                plan = None
                for planned_envelope_family in tuple(
                    dict.fromkeys((envelope_family, SIMPLE_L, RECTANGLE))
                ):
                    try:
                        plan = construct_structured_building_plan_v1(
                            boundary=context.boundary,
                            obstacles=context.obstacles,
                            authorities=context.authorities,
                            process_axis=process_axis,
                            process_direction=process_direction,
                            layout_family=layout_family,
                            envelope_family=planned_envelope_family,
                            main_entrance=context.main_entrance,
                            support_side=support_side,
                            envelope_candidate_index=(
                                terminal_variant_index if planned_envelope_family == SIMPLE_L else 0
                            ),
                        )
                    except LayoutAuthorityError as error:
                        plan_error = error
                        continue
                    break
                if plan is None:
                    if plan_error is not None:
                        raise plan_error
                    raise _error("PROGRAM_BUILDING_ENVELOPE_UNAVAILABLE")
                plan_cache[plan_key] = plan
        except LayoutAuthorityError as error:
            plan_cache[plan_key] = error
            plan_row = {
                "layout_family": layout_family,
                "process_axis": process_axis,
                "envelope_family": envelope_family,
                "support_side": support_side,
                "construction_nodes": 0,
                "result": "DETERMINISTIC_SYNTHESIS_IMPOSSIBLE",
                "first_failure_stage": "PLAN",
                "rejection_reason": error.code,
                "reason": error.code,
                "construction_policy": f"{layout_family}_DIRECT_SYNTHESIS_V1",
            }
            _record_rejection(stats, error.code)
            if stats.constructive_divergence_attempts is None:
                stats.constructive_divergence_attempts = []
            stats.constructive_divergence_attempts.append(plan_row)
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(plan_row)
            continue
        assert plan is not None
        # A site-incompatible plan is an exact deterministic planning result,
        # not a placement node. Charge the shared placement budget only when
        # a feasible family plan is ready to enter finite zone synthesis.
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            stats.skeleton_search_truncated = True
            return
        stats.visited_nodes += 1
        stats.construction_node_count += 1
        stats.current_work_item = {
            "topology": context.structural_topology,
            "layout_family": layout_family,
            "process_axis": process_axis,
            "envelope_family": envelope_family,
            "support_side": support_side,
            "mirror_variant": variant_index,
            "terminal_variant_index": terminal_variant_index,
            "branch": "DIRECT_FULL_BUILDING_SYNTHESIS",
            "family_plan_subvariant": attempt_index,
            "placement_node_charged": True,
        }
        quantum = _quantum_checkpoint(stats)
        if quantum is not None:
            yield quantum
        if stats.constructive_divergence_attempts is None:
            stats.constructive_divergence_attempts = []
        stats.constructive_divergence_attempts.append(
            {
                "layout_family": layout_family,
                "process_axis": process_axis,
                "envelope_family": envelope_family,
                "envelope_candidate_index": 0,
                "support_side": support_side,
                "result": "FAMILY_PLAN_READY",
                "construction_policy": f"{layout_family}_DIRECT_SYNTHESIS_V1",
                "envelope_bounds_mm": list(plan.envelope.bounds_mm),
                "envelope_components_mm": [list(row) for row in plan.envelope.components_mm],
                "primary_x_axes_mm": list(plan.primary_grid.x_axes_mm),
                "primary_y_axes_mm": list(plan.primary_grid.y_axes_mm),
                "support_band_bounds_mm": list(
                    plan.band_for_zone("packaging_material_storage").bounds_mm
                ),
                "personnel_band_bounds_mm": list(plan.band_for_zone("office").bounds_mm),
            }
        )
        construction_failure_reasons: list[str] = []
        main_placements = _synthesize_family_main_process(
            context,
            plan,
            None,
            variant_index=variant_index,
            failure_reasons=construction_failure_reasons,
        )
        attempt_row = {
            "layout_family": layout_family,
            "envelope_family": plan.envelope.family,
            "process_axis": plan.process_axis,
            "support_side": support_side,
            "mirror_variant": variant_index,
            "construction_policy": f"{plan.layout_family}_PLAN_TO_GEOMETRY_V1",
            "construction_nodes": 1,
            "result": "GEOMETRY_SYNTHESIS_REJECTED",
            "first_failure_stage": "MAIN_BAND_PACKING",
            "first_failure_interface": None,
            "rejection_reason": None,
        }
        if main_placements is None:
            failure_reason = (
                construction_failure_reasons[-1]
                if construction_failure_reasons
                else "DIRECT_FAMILY_PACKING_NO_COMPLETE_GEOMETRY"
            )
            attempt_row["rejection_reason"] = failure_reason
            if failure_reason.startswith("BAND_PACKING_UNAVAILABLE:"):
                attempt_row["first_failure_stage"] = "MAIN_BAND_PACKING"
                attempt_row["first_failure_interface"] = failure_reason.split(":", 1)[1]
            elif failure_reason == "GRAPH_HARD_VALIDATION":
                attempt_row["first_failure_stage"] = "GRAPH_HARD_VALIDATION"
            else:
                attempt_row["first_failure_interface"] = (
                    failure_reason.split(":", 1)[1] if ":" in failure_reason else None
                )
            _record_rejection(stats, failure_reason)
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue

        try:
            classification = classify_main_process_topology_v1(main_placements)
            if classification.canonical_owner is None:
                raise _error("SKELETON_TOPOLOGY_INVALID")
            discovery_seed = MainProcessSkeletonCandidateV1.create(
                family=context.structural_composition_family,
                rectangles=main_placements,
                topology=classification.canonical_owner,
                generation_pattern=(
                    f"{plan.layout_family}:DOCK_EVENT_ROOT:{attempt_index}:MIRROR:{variant_index}"
                ),
                hard_geometry_predicates_passed=(
                    "SITE_CONTAINMENT",
                    "NO_BUILD_CLEAR",
                    "NON_OVERLAP",
                    "MUST_ADJACENCY",
                    "FAMILY_DIRECT_CONSTRUCTION",
                ),
                construction_policy=f"{plan.layout_family}_PLAN_TO_GEOMETRY_V1",
                topology_divergence_stage="FAMILY_EDGE_COMPOSITION",
                discovery_topology=context.structural_topology,
                discovery_family=context.structural_composition_family,
                building_layout_family=plan.layout_family,
                building_envelope_family=plan.envelope.family,
                planned_envelope_bounds_mm=plan.envelope.bounds_mm,
            )
            seed = canonicalize_main_process_skeleton_for_evaluation(
                discovery_seed,
                classification,
                site_geometry=context.site_body,
            )
            if not _topology_geometry_valid(
                main_placements, seed.canonical_topology_owner, seed.dominant_axis
            ):
                raise _error("SKELETON_TOPOLOGY_INVALID")
        except LayoutAuthorityError as error:
            attempt_row["rejection_reason"] = error.code
            attempt_row["first_failure_stage"] = "GRAPH_HARD_VALIDATION"
            attempt_row["first_failure_interface"] = error.details.get("unsatisfied_pairs")
            _record_rejection(stats, error.code)
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue

        geometry_hash = seed.main_process_skeleton_hash
        attempt_row["skeleton_hash"] = geometry_hash
        attempt_row["result"] = "FULL_GEOMETRY_SYNTHESIZED"
        if geometry_hash in seen_hashes:
            attempt_row["result"] = "DUPLICATE_GEOMETRY"
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue
        seen_hashes.add(geometry_hash)
        if stats.constructed_main_skeletons is None:
            stats.constructed_main_skeletons = {}
        stats.constructed_main_skeletons.setdefault(geometry_hash, seed)
        if stats.skeleton_generation_patterns is None:
            stats.skeleton_generation_patterns = {}
        stats.skeleton_generation_patterns[seed.generation_pattern] = (
            stats.skeleton_generation_patterns.get(seed.generation_pattern, 0) + 1
        )
        if not _constructive_main_skeleton_tail_admission(context, stats, seed):
            attempt_row["result"] = "MAIN_SKELETON_PREFLIGHT_REJECTED"
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue

        tail_failure_reasons: list[str] = []
        synthesis = _direct_family_tail_zones(
            context,
            plan,
            main_placements,
            variant_index=variant_index,
            failure_reasons=tail_failure_reasons,
        )
        if synthesis is None:
            attempt_row["result"] = "DIRECT_TAIL_BAND_SYNTHESIS_REJECTED"
            failure_reason = (
                tail_failure_reasons[-1]
                if tail_failure_reasons
                else "TAIL_BAND_PACKING_NO_VALID_COMBINATION"
            )
            attempt_row["first_failure_stage"] = (
                "PERSONNEL_PACKING"
                if failure_reason.startswith("PERSONNEL")
                else "SUPPORT_PACKING"
                if failure_reason.startswith("SUPPORT")
                else "GRAPH_HARD_VALIDATION"
                if failure_reason == "GRAPH_HARD_VALIDATION"
                else "TAIL_PACKING"
            )
            attempt_row["rejection_reason"] = failure_reason
            _record_rejection(stats, failure_reason)
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue

        try:
            exact_plan = _direct_candidate_plan(
                plan,
                synthesis,
            )
            _validate_graph_completeness(context.graph, synthesis)
        except LayoutAuthorityError as error:
            attempt_row["result"] = "BAND_OR_GRAPH_VALIDATION_REJECTED"
            attempt_row["rejection_reason"] = error.code
            attempt_row["first_failure_stage"] = (
                "GRAPH_HARD_VALIDATION"
                if error.code == "HARD_CONSTRAINT_UNSATISFIABLE"
                else "ENVELOPE_CLOSURE"
            )
            attempt_row["first_failure_interface"] = error.details.get("unsatisfied_pairs")
            _record_rejection(stats, error.code)
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue

        canonical_skeletons = structural_skeleton_candidates(
            context.site_body,
            tuple(context.authorities),
            zone_authorities=context.authorities,
            family_candidates=(seed.family,),
        )
        canonical_structural_skeleton = next(
            (row for row in canonical_skeletons if row.family.to_dict() == seed.family.to_dict()),
            None,
        )
        if canonical_structural_skeleton is None:
            attempt_row["result"] = "CANONICAL_STRUCTURAL_SKELETON_UNAVAILABLE"
            if stats.skeleton_construction_attempts is None:
                stats.skeleton_construction_attempts = []
            stats.skeleton_construction_attempts.append(attempt_row)
            continue

        candidate_context = replace(
            context,
            structural_composition_family=seed.family,
            structural_skeleton=canonical_structural_skeleton,
            structured_building_plan=exact_plan,
            structural_topology=seed.canonical_topology_owner,
        )
        _validate_graph_completeness(context.graph, synthesis)
        stats.complete_candidates += 1
        stats.generated_candidates += len(synthesis)
        payload = _candidate_payload(
            synthesis,
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
                candidate_context,
                stats,
                search_tree_exhausted=False,
                objective_optimal_within_search_family=False,
            ),
        )
        payload["_structural_generation_flag"] = True
        payload["_structural_composition_family"] = seed.family.to_dict()
        payload["_structural_skeleton"] = canonical_structural_skeleton.to_dict()
        payload["_search_phase"] = STRUCTURED_PHASE
        payload["_structured_building_plan"] = exact_plan.to_dict()
        payload["_main_process_skeleton"] = seed.to_evaluation_dict()
        payload["_r5_skeleton_hash"] = geometry_hash
        payload["_r5_topology"] = seed.canonical_topology_owner
        payload["_r7_discovery_topology"] = context.structural_topology
        if stats.skeleton_tail_lifecycle is None:
            stats.skeleton_tail_lifecycle = []
        stats.skeleton_tail_lifecycle.append(
            {
                "topology": seed.canonical_topology_owner,
                "skeleton_hash": geometry_hash,
                "layout_family": plan.layout_family,
                "envelope_family": exact_plan.envelope.family,
                "construction_mode": "DIRECT_FULL_12_ZONE_SYNTHESIS",
                "tail_search_started": True,
                "tail_nodes": 0,
                "complete_candidate_count": 1,
                "p2d_reached": True,
                "first_failure_stage": None,
                "first_failure_reason": None,
            }
        )
        attempt_row["result"] = "FULL_12_ZONE_CANDIDATE_EMITTED"
        if stats.skeleton_construction_attempts is None:
            stats.skeleton_construction_attempts = []
        stats.skeleton_construction_attempts.append(attempt_row)
        yield payload


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
        "main_process_skeleton_construction": {
            "identity": "main-process-skeleton-construction@1.0.0",
            "constructed_candidate_count": len(stats.constructed_main_skeletons or {}),
            "generation_patterns": dict(sorted((stats.skeleton_generation_patterns or {}).items())),
            "rejection_reason_counts": dict(sorted((stats.rejection_reason_counts or {}).items())),
            "candidates": [
                {
                    "main_process_skeleton_hash": candidate.main_process_skeleton_hash,
                    "family": candidate.family.to_dict(),
                    "generation_pattern": candidate.generation_pattern,
                    "layout_family": candidate.building_layout_family,
                    "envelope_family": candidate.building_envelope_family,
                }
                for candidate in sorted(
                    (stats.constructed_main_skeletons or {}).values(),
                    key=lambda row: row.main_process_skeleton_hash,
                )
            ],
        },
    }


def _record_rejection(stats: _PlacementSearchStats, reason: str) -> None:
    if stats.rejection_reason_counts is None:
        stats.rejection_reason_counts = {}
    stats.rejection_reason_counts[reason] = stats.rejection_reason_counts.get(reason, 0) + 1


def _geometry_rejection_reason(
    rectangle: PlacedRectangleV1,
    placed: Mapping[str, PlacedRectangleV1],
    context: _PlacementSearchContext,
) -> str | None:
    left, bottom, right, top = _bounds(rectangle)
    min_x, min_y, max_x, max_y = context.boundary_bounds
    if left < min_x or bottom < min_y or right > max_x or top > max_y:
        return "SITE_OUTSIDE"
    if not rectangle_inside_polygon(rectangle, context.boundary):
        return "SITE_OUTSIDE"
    if any(
        rectangle_intersects_closed_obstacle(rectangle, obstacle) for obstacle in context.obstacles
    ):
        return "NO_BUILD_COLLISION"
    if any(rectangles_overlap(rectangle, other) for other in placed.values()):
        return "ZONE_OVERLAP"
    return None


def _constructive_edge_options(
    context: _PlacementSearchContext,
    code: str,
    placed: Mapping[str, PlacedRectangleV1],
    neighbor_code: str,
    *,
    required_side: str | tuple[str, ...] | None = None,
    bridge_code: str | None = None,
    bank_alignment_code: str | None = None,
    anchor_reference_codes: Sequence[str] = (),
    prefer_truck_entrance: bool = False,
    stats: _PlacementSearchStats,
) -> tuple[PlacedRectangleV1, ...]:
    """Construct exact adjacent options for one named skeleton edge."""
    neighbor = placed[neighbor_code]
    authority = context.authorities[code]
    variants = _dimension_variants(authority, placed, context.boundary)
    if not variants:
        _record_rejection(stats, "DIMENSION_VARIANT_UNAVAILABLE")
        return ()
    options: dict[tuple[int, int, int, int], PlacedRectangleV1] = {}
    truck_interface_shipping = (
        _shipping_rectangles_for_dock_events(context)
        if code in {"shipping_channel", "finished_goods_room"}
        else ()
    )
    truck_interface_only_bounds: set[tuple[int, int, int, int]] = set()
    graph_neighbors = _must_neighbors(code, placed, context.graph)
    anchor_references = tuple(
        placed[reference_code]
        for reference_code in anchor_reference_codes
        if reference_code in placed and reference_code != neighbor_code
    )
    for width_mm, depth_mm, rotation in variants:
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        candidate_anchors = set(_edge_anchors(neighbor, actual_width, actual_depth))
        established_anchors = set(candidate_anchors)
        if code == "shipping_channel":
            truck_event_anchors = {
                (rectangle.bounds_mm[0], rectangle.bounds_mm[1])
                for rectangle in truck_interface_shipping
            }
            candidate_anchors.update(truck_event_anchors)
        elif code == "finished_goods_room":
            truck_event_anchors = set()
            for shipping_rectangle in truck_interface_shipping:
                truck_event_anchors.update(
                    _edge_anchors(shipping_rectangle, actual_width, actual_depth)
                )
            candidate_anchors.update(truck_event_anchors)
        else:
            truck_event_anchors = set()
        for anchor_reference in anchor_references:
            reference_anchors = set(_edge_anchors(anchor_reference, actual_width, actual_depth))
            established_anchors.update(reference_anchors)
            candidate_anchors.update(reference_anchors)
        for x_mm, y_mm in sorted(candidate_anchors):
            rectangle = _rectangle_from_mm(code, x_mm, y_mm, width_mm, depth_mm, rotation)
            candidate_side = _adjacent_side(neighbor, rectangle)
            if required_side is not None and candidate_side not in (
                required_side if isinstance(required_side, tuple) else (required_side,)
            ):
                continue
            rejection = _geometry_rejection_reason(rectangle, placed, context)
            if rejection is not None:
                _record_rejection(stats, rejection)
                continue
            structured_plan = getattr(context, "structured_building_plan", None)
            if structured_plan is not None and not structured_plan.admits(code, rectangle):
                _record_rejection(stats, "ENVELOPE_OR_BAND_REJECT")
                continue
            if any(
                not rectangles_share_positive_edge(rectangle, must_neighbor)
                for must_neighbor in graph_neighbors
            ):
                _record_rejection(stats, "MUST_ADJACENCY_FAIL")
                continue
            left, bottom, right, top = _bounds(rectangle)
            key = (left, bottom, right, top)
            if (
                code in {"shipping_channel", "finished_goods_room"}
                and (x_mm, y_mm) in truck_event_anchors
                and (x_mm, y_mm) not in established_anchors
            ):
                truck_interface_only_bounds.add(key)
            current = options.get(key)
            current_variant = (
                (
                    _mm(current.width_m, field="candidate.width_m"),
                    _mm(current.depth_m, field="candidate.depth_m"),
                    current.rotation_deg,
                )
                if current is not None
                else None
            )
            variant = (width_mm, depth_mm, rotation)
            if current_variant is None or variant < current_variant:
                options[key] = rectangle
    rows = tuple(options[key] for key in sorted(options))
    if not rows:
        _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
        return ()

    def preference(
        rectangle: PlacedRectangleV1,
    ) -> tuple[int, ...]:
        alignment_penalty = 0
        topology_alignment_penalty = 0
        truck_distance_squared = 0
        truck_dock_ordering = (0, 0, 0)
        if bank_alignment_code is not None:
            bank_reference = placed[bank_alignment_code]
            reference_bounds = _bounds(bank_reference)
            candidate_bounds = _bounds(rectangle)
            candidate_side = _adjacent_side(neighbor, rectangle)
            if candidate_side in {"EAST", "WEST"}:
                alignment_penalty = int(
                    candidate_bounds[1] != reference_bounds[1]
                    or candidate_bounds[3] != reference_bounds[3]
                )
            else:
                alignment_penalty = int(
                    candidate_bounds[0] != reference_bounds[0]
                    or candidate_bounds[2] != reference_bounds[2]
                )
        if context.structural_topology == OFFSET_LINEAR_BAND and code in {
            "primary_precooling_room",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        }:
            candidate_bounds = _bounds(rectangle)
            neighbor_bounds = _bounds(neighbor)
            candidate_side = _adjacent_side(neighbor, rectangle)
            if candidate_side in {"NORTH", "SOUTH"}:
                cross_axis_aligned = (
                    candidate_bounds[0] == neighbor_bounds[0]
                    and candidate_bounds[2] == neighbor_bounds[2]
                )
            else:
                cross_axis_aligned = (
                    candidate_bounds[1] == neighbor_bounds[1]
                    and candidate_bounds[3] == neighbor_bounds[3]
                )
            # For the offset topology, aligned/unaligned is only an ordering
            # preference. Positive edge adjacency and the exact final topology
            # predicate remain mandatory.
            topology_alignment_penalty = int(cross_axis_aligned)
        bridge_penalty = int(
            bridge_code is not None
            and not rectangles_share_positive_edge(rectangle, placed[bridge_code])
        )
        entrance_penalty = int(
            prefer_truck_entrance
            and not _rectangle_shares_entrance_boundary(
                rectangle, _truck_segment(context.site_body)
            )
        )
        if code == "shipping_channel" and prefer_truck_entrance:
            truck_distance_squared = _rectangle_distance_squared_to_entrance(
                rectangle, _truck_segment(context.site_body)
            )
            _, loading_face, _, _ = _loading_face(rectangle, context.site_body)
            dock_location_penalty = _loading_face_dock_endpoint_penalty(context, rectangle)
            truck_dock_ordering = (
                _shipping_loading_face_approach_axis_penalty(context, rectangle),
                0 if dock_location_penalty == 0 else 1 if dock_location_penalty == 1 else 2,
                int(
                    not any(
                        _on_segment(point, loading_face[0], loading_face[1])
                        for point in _truck_dock_points_at_entrance(context)
                    )
                ),
            )
        return (
            alignment_penalty,
            topology_alignment_penalty,
            bridge_penalty,
            entrance_penalty,
            int(_bounds(rectangle) in truck_interface_only_bounds),
            *truck_dock_ordering,
            truck_distance_squared,
            -(
                context_plan.primary_grid.aligned_edge_count(rectangle)
                if (context_plan := getattr(context, "structured_building_plan", None)) is not None
                else 0
            ),
            *_bounds(rectangle)[:2],
            _bounds(rectangle)[2],
            rectangle.rotation_deg,
        )

    ordered_rows = tuple(sorted(rows, key=preference))
    if code == "finished_goods_room" and truck_interface_only_bounds:
        # Preserve one established branch first, then interleave a room
        # explicitly paired to an entrance/dock-derived shipping event.
        # This is deterministic coverage ordering, not a hard constraint
        # or topology ranking bonus.
        return _interleave_finished_truck_interface_options(
            ordered_rows, truck_interface_only_bounds
        )
    return ordered_rows


def _constructive_sorting_roots(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> tuple[PlacedRectangleV1, ...]:
    plan = context.structured_building_plan
    if plan is None:
        return ()
    authority = context.authorities["sorting_packaging_room"]
    variants = _dimension_variants(authority, {}, context.boundary)
    if not variants:
        _record_rejection(stats, "DIMENSION_VARIANT_UNAVAILABLE")
        return ()
    skeleton_roots = set(context.structural_skeleton.root_anchor_candidates)
    roots: dict[tuple[int, int, int, int], PlacedRectangleV1] = {}
    for width_mm, depth_mm, rotation in variants:
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        anchors = set(
            _structural_event_anchors(
                {}, context.boundary, context.obstacles, actual_width, actual_depth
            )
        )
        anchors.update(
            (int(x * MILLIMETRES_PER_METRE), int(y * MILLIMETRES_PER_METRE))
            for x, y, root_rotation in skeleton_roots
            if root_rotation == rotation
        )
        process_band = next(band for band in plan.bands if band.band_code == "PROCESS_CORE_BAND")
        grid = plan.primary_grid
        planned_origins = {
            *((x_mm, y_mm) for x_mm in grid.event_x_mm for y_mm in grid.y_axes_mm),
            *((x_mm, y_mm) for x_mm in grid.x_axes_mm for y_mm in grid.event_y_mm),
        }
        anchors.update(
            (x_mm, y_mm)
            for x_mm, y_mm in planned_origins
            if process_band.contains(
                _rectangle_from_mm(
                    "sorting_packaging_room", x_mm, y_mm, width_mm, depth_mm, rotation
                )
            )
        )
        for x_mm, y_mm in sorted(anchors):
            rectangle = _rectangle_from_mm(
                "sorting_packaging_room", x_mm, y_mm, width_mm, depth_mm, rotation
            )
            rejection = _geometry_rejection_reason(rectangle, {}, context)
            if rejection is not None:
                _record_rejection(stats, rejection)
                continue
            if not plan.admits("sorting_packaging_room", rectangle):
                _record_rejection(stats, "ENVELOPE_OR_BAND_REJECT")
                continue
            left, bottom, right, top = _bounds(rectangle)
            key = (left, bottom, right, top)
            current = roots.get(key)
            current_variant = (
                (
                    _mm(current.width_m, field="sorting.width_m"),
                    _mm(current.depth_m, field="sorting.depth_m"),
                    current.rotation_deg,
                )
                if current is not None
                else None
            )
            variant = (width_mm, depth_mm, rotation)
            if current_variant is None or variant < current_variant:
                roots[key] = rectangle

    preferred_positions = {
        (int(x * MILLIMETRES_PER_METRE), int(y * MILLIMETRES_PER_METRE))
        for x, y, _rotation in skeleton_roots
    }
    canonical_roots = sorted(
        roots.values(),
        key=lambda row: (row.bounds_mm[1], row.bounds_mm[0], row.rotation_deg),
    )
    preflight_penalties = {
        row.bounds_mm: _topology_root_ordering_penalty(context, row) for row in canonical_roots
    }
    if not canonical_roots:
        _record_rejection(stats, "NO_ROOT_INSIDE_STRUCTURED_PROCESS_BAND")
        return ()
    if context.structural_topology == CENTRAL_PROCESS_HUB:
        # Preserve the established, deterministic Hub root lane. Ordering the
        # existing structural anchor events first is important: the recent
        # envelope penalty reordered them and caused a known hard-valid Hub
        # path to disappear inside its unchanged tail budget.
        ordered = [row for row in canonical_roots if row.bounds_mm[:2] in preferred_positions]
        remaining = [row for row in canonical_roots if row.bounds_mm[:2] not in preferred_positions]
        if not ordered and remaining:
            ordered.append(remaining.pop(0))
    else:
        first = min(
            canonical_roots,
            key=lambda row: (
                preflight_penalties[row.bounds_mm],
                row.bounds_mm[:2] not in preferred_positions,
                row.bounds_mm[1],
                row.bounds_mm[0],
                row.rotation_deg,
            ),
        )
        ordered = [first]
        remaining = [row for row in canonical_roots if row != first]
    if stats.root_preflight_rows is None:
        stats.root_preflight_rows = []
    while remaining:

        def diversity_key(row: PlacedRectangleV1) -> tuple[int, int, int, int, int]:
            x_mm, y_mm = row.bounds_mm[:2]
            minimum_squared_distance = min(
                (x_mm - chosen.bounds_mm[0]) ** 2 + (y_mm - chosen.bounds_mm[1]) ** 2
                for chosen in ordered
            )
            # Max-min anchor spacing samples genuinely different potential
            # process cores without introducing a weighted quality score.
            if context.structural_topology == CENTRAL_PROCESS_HUB:
                return (
                    minimum_squared_distance,
                    -y_mm,
                    -x_mm,
                    -row.rotation_deg,
                    -row.bounds_mm[2],
                )
            return (
                -preflight_penalties[row.bounds_mm],
                minimum_squared_distance,
                -y_mm,
                -x_mm,
                -row.rotation_deg,
            )

        next_root = max(remaining, key=diversity_key)
        ordered.append(next_root)
        remaining.remove(next_root)
    stats.root_preflight_rows.extend(
        {
            "sorting_root_bounds_mm": list(row.bounds_mm),
            "estimated_topology_envelope_penalty_mm": preflight_penalties[row.bounds_mm],
            "use": "ORDERING_ONLY",
            "hard_pruned": False,
        }
        for row in ordered
    )
    return tuple(ordered)


def _family_attachment_sides(
    family: StructuralCompositionFamilyV1,
    topology: str | None = None,
) -> tuple[tuple[str, str], ...]:
    if family.family == "LINEAR_PROCESS_BAND":
        raw_side = {
            ("X", "POSITIVE"): "WEST",
            ("X", "NEGATIVE"): "EAST",
            ("Y", "POSITIVE"): "SOUTH",
            ("Y", "NEGATIVE"): "NORTH",
        }[(family.dominant_axis, family.dominant_direction)]
        return ((raw_side, _OPPOSITE_SIDE[raw_side]),)
    if topology == CENTRAL_PROCESS_HUB:
        # Distinct adjacent faces are explored first because they create a
        # genuine two-dimensional hub candidate space; opposite-face pairs
        # remain available after this constructive divergence is attempted.
        return (
            ("SOUTH", "WEST"),
            ("SOUTH", "EAST"),
            ("NORTH", "WEST"),
            ("NORTH", "EAST"),
            ("WEST", "SOUTH"),
            ("WEST", "NORTH"),
            ("EAST", "SOUTH"),
            ("EAST", "NORTH"),
            ("SOUTH", "NORTH"),
            ("NORTH", "SOUTH"),
            ("WEST", "EAST"),
            ("EAST", "WEST"),
        )
    return (
        ("SOUTH", "NORTH"),
        ("SOUTH", "WEST"),
        ("NORTH", "SOUTH"),
        ("EAST", "NORTH"),
        ("WEST", "NORTH"),
        ("WEST", "SOUTH"),
        ("EAST", "SOUTH"),
        ("NORTH", "EAST"),
        ("NORTH", "WEST"),
        ("SOUTH", "EAST"),
        ("WEST", "EAST"),
        ("EAST", "WEST"),
    )


def _sorting_roots_for_attachment_pair(
    context: _PlacementSearchContext,
    roots: Sequence[PlacedRectangleV1],
    raw_side: str,
    finished_side: str,
) -> tuple[PlacedRectangleV1, ...]:
    """Order planned core roots by exact adjacent-room projection room.

    This is an ordering prior only. Site polygons, obstacles, band membership,
    adjacency, and all later hard predicates remain authoritative. In
    particular, legacy topology anchors no longer get first service merely
    because they appeared in the old rectangle-first root list.
    """
    return tuple(
        sorted(
            roots,
            key=lambda rectangle: _sorting_root_attachment_pair_key(
                context, rectangle, raw_side, finished_side
            ),
        )
    )


def _sorting_root_attachment_pair_key(
    context: _PlacementSearchContext,
    rectangle: PlacedRectangleV1,
    raw_side: str,
    finished_side: str,
) -> tuple[int, int, int, int, int, int]:
    bounds = _bounds(rectangle)
    side_indexes = {"WEST": 0, "EAST": 2, "SOUTH": 1, "NORTH": 3}
    deficits: list[int] = []
    residual_clearances: list[int] = []
    for side, zone_code in (
        (raw_side, "primary_precooling_room"),
        (finished_side, "secondary_precooling_room"),
    ):
        index = side_indexes[side]
        available = (
            bounds[index] - context.boundary_bounds[index]
            if side in {"WEST", "SOUTH"}
            else context.boundary_bounds[index] - bounds[index]
        )
        normal_axis = "X" if side in {"WEST", "EAST"} else "Y"
        required = _minimum_authoritative_axis_extent(context, zone_code, normal_axis)
        deficits.append(max(0, required - available))
        residual_clearances.append(available - required)
    return (
        sum(deficits),
        max(deficits, default=0),
        -min(residual_clearances, default=0),
        _topology_root_ordering_penalty(context, rectangle),
        bounds[1],
        bounds[0],
    )


def _offset_transition_options(
    context: _PlacementSearchContext,
    placed: Mapping[str, PlacedRectangleV1],
    sorting: PlacedRectangleV1,
    candidates: Sequence[PlacedRectangleV1],
    direction: str,
    required_side: str,
    stats: _PlacementSearchStats,
) -> tuple[tuple[PlacedRectangleV1, ...], dict[tuple[int, int, int, int], int]]:
    """Construct only exact CORE->FINISHED edge options with nonzero band shift."""
    process_axis = context.structural_skeleton.ordering_axis
    cross_axis = "Y" if process_axis == "X" else "X"
    raw = _group_axis_interval(RAW_SIDE_GROUP, placed, cross_axis)
    core = _group_axis_interval(PROCESSING_CORE_GROUP, placed, cross_axis)
    if raw is None or core is None:
        return (), {}
    common_low = max(raw[0], core[0])
    common_high = min(raw[1], core[1])
    if common_low >= common_high:
        return (), {}
    cross_low_index, cross_high_index = (1, 3) if cross_axis == "Y" else (0, 2)
    sorting_bounds = _bounds(sorting)
    sorting_cross_low = sorting_bounds[cross_low_index]
    sorting_cross_high = sorting_bounds[cross_high_index]
    expanded_options = {_bounds(row): row for row in candidates}
    authority = context.authorities["secondary_precooling_room"]
    for width_mm, depth_mm, rotation in _dimension_variants(authority, placed, context.boundary):
        actual_width, actual_depth = (
            (depth_mm, width_mm) if rotation == 90 else (width_mm, depth_mm)
        )
        cross_extent = actual_width if cross_axis == "X" else actual_depth
        cross_start = common_high if direction == "POSITIVE" else common_low - cross_extent
        for anchor_x, anchor_y in _edge_anchors(sorting, actual_width, actual_depth):
            x_mm = cross_start if cross_axis == "X" else anchor_x
            y_mm = cross_start if cross_axis == "Y" else anchor_y
            candidate = _rectangle_from_mm(
                "secondary_precooling_room", x_mm, y_mm, width_mm, depth_mm, rotation
            )
            candidate_side = _adjacent_side(sorting, candidate)
            if candidate_side != required_side:
                continue
            rejection = _geometry_rejection_reason(candidate, placed, context)
            if rejection is not None:
                _record_rejection(stats, rejection)
                continue
            if candidate_side not in _CARDINAL_SIDES or not rectangles_share_positive_edge(
                sorting, candidate
            ):
                continue
            if any(
                not rectangles_share_positive_edge(candidate, neighbor)
                for neighbor in _must_neighbors("secondary_precooling_room", placed, context.graph)
            ):
                _record_rejection(stats, "MUST_ADJACENCY_FAIL")
                continue
            expanded_options[_bounds(candidate)] = candidate
    shifts_by_key: dict[tuple[int, int, int, int], int] = {}
    selected: list[PlacedRectangleV1] = []
    for candidate in (expanded_options[key] for key in sorted(expanded_options)):
        bounds = _bounds(candidate)
        interval = (bounds[cross_low_index], bounds[cross_high_index])
        core_overlap = max(interval[0], core[0]) < min(interval[1], core[1])
        if not core_overlap:
            continue
        if _adjacent_side(sorting, candidate) not in {"NORTH", "SOUTH", "EAST", "WEST"}:
            continue
        if direction == "POSITIVE":
            shift_mm = interval[0] - sorting_cross_low
            transition_valid = shift_mm > 0 and interval[0] >= common_high
        else:
            shift_mm = interval[1] - sorting_cross_high
            transition_valid = shift_mm < 0 and interval[1] <= common_low
        if transition_valid:
            selected.append(candidate)
            shifts_by_key[bounds] = shift_mm
    selected.sort(key=lambda row: (*_bounds(row), row.rotation_deg))
    if stats.offset_transition_trace is None:
        stats.offset_transition_trace = []
    stats.offset_transition_trace.append(
        {
            "topology": OFFSET_LINEAR_BAND,
            "transition_stage": "CORE_TO_FINISHED",
            "direction": direction,
            "cross_axis": cross_axis,
            "sorting_root_mm": list(sorting.bounds_mm),
            "raw_side": _adjacent_side(sorting, placed["primary_precooling_room"]),
            "finished_side": required_side,
            "raw_core_common_interval_mm": [common_low, common_high],
            "candidate_option_count": len(candidates),
            "transition_option_count": len(selected),
            "cross_axis_shifts_mm": sorted(shifts_by_key.values()),
            "transition_option_bounds_mm": [list(_bounds(row)) for row in selected],
        }
    )
    return tuple(selected), shifts_by_key


def _interleave_raw_bank_options(
    primary: PlacedRectangleV1,
    options: Sequence[PlacedRectangleV1],
    side_order: Sequence[str],
) -> tuple[PlacedRectangleV1, ...]:
    """Visit each legal raw-bank attachment face before repeating one face."""
    grouped: dict[str, list[PlacedRectangleV1]] = {}
    for option in options:
        side = _adjacent_side(primary, option)
        if side is not None:
            grouped.setdefault(side, []).append(option)
    interleaved: list[PlacedRectangleV1] = []
    while any(grouped.values()):
        for side in side_order:
            candidates = grouped.get(side)
            if candidates:
                interleaved.append(candidates.pop(0))
    return tuple(interleaved)


def _construct_face_skeletons(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
    sorting: PlacedRectangleV1,
    raw_side: str,
    finished_side: str,
    skeleton_node_limit: int,
    skeleton_limit: int,
    offset_direction: str | None = None,
) -> Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]:
    """Construct one complete seven-zone skeleton for one core topology.

    Shipping-interface alternatives are deliberately not allowed to consume
    the whole constructive lane before another raw/finished face topology is
    tried.  Candidate diversity must come from the main process geometry, not
    merely from moving the terminal shipping rectangle.
    """
    plan = context.structured_building_plan
    if plan is None:
        return
    placed: dict[str, PlacedRectangleV1] = {"sorting_packaging_room": sorting}
    emitted_skeletons = 0
    primary_options = _constructive_edge_options(
        context,
        "primary_precooling_room",
        placed,
        "sorting_packaging_room",
        required_side=raw_side,
        stats=stats,
    )
    raw_required_sides: tuple[str, ...] = (
        ("WEST", "EAST") if context.structural_skeleton.ordering_axis == "Y" else ("SOUTH", "NORTH")
    )
    if context.structural_composition_family.family != "LINEAR_PROCESS_BAND":
        raw_required_sides = tuple(
            side for side in _CARDINAL_SIDES if side != _OPPOSITE_SIDE[raw_side]
        )
    for primary in primary_options:
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            stats.skeleton_search_truncated = True
            return
        stats.current_work_item = {
            "topology": context.structural_topology,
            "envelope_family": plan.envelope.family,
            "band_family": plan.layout_family,
            "sorting_root_mm": list(sorting.bounds_mm),
            "raw_side": raw_side,
            "finished_side": finished_side,
            "offset_direction": offset_direction,
            "branch": "PRIMARY",
        }
        stats.visited_nodes += 1
        stats.construction_node_count += 1
        quantum = _quantum_checkpoint(stats)
        if quantum is not None:
            yield quantum
        for descendant in (
            "raw_fruit_buffer",
            "secondary_precooling_room",
            "coating_room",
            "finished_goods_room",
            "shipping_channel",
        ):
            placed.pop(descendant, None)
        placed["primary_precooling_room"] = primary
        raw_options = _constructive_edge_options(
            context,
            "raw_fruit_buffer",
            placed,
            "primary_precooling_room",
            required_side=raw_required_sides,
            bank_alignment_code="primary_precooling_room",
            stats=stats,
        )
        # Sample each legal raw-bank attachment face before consuming the
        # remaining options on one face.  This is deterministic candidate
        # coverage, not a geometry preference or a hard constraint.
        raw_options = _interleave_raw_bank_options(primary, raw_options, raw_required_sides)
        for raw in raw_options:
            if stats.visited_nodes >= context.node_budget:
                stats.node_budget_exhausted = True
                stats.skeleton_search_truncated = True
                return
            stats.current_work_item = {
                "topology": context.structural_topology,
                "envelope_family": plan.envelope.family,
                "band_family": plan.layout_family,
                "sorting_root_mm": list(sorting.bounds_mm),
                "raw_side": raw_side,
                "finished_side": finished_side,
                "offset_direction": offset_direction,
                "branch": "RAW",
            }
            stats.visited_nodes += 1
            stats.construction_node_count += 1
            quantum = _quantum_checkpoint(stats)
            if quantum is not None:
                yield quantum
            for descendant in (
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            ):
                placed.pop(descendant, None)
            placed["raw_fruit_buffer"] = raw
            secondary_options = _constructive_edge_options(
                context,
                "secondary_precooling_room",
                placed,
                "sorting_packaging_room",
                required_side=finished_side,
                stats=stats,
            )
            offset_shifts: dict[tuple[int, int, int, int], int] = {}
            if context.structural_topology == OFFSET_LINEAR_BAND:
                if offset_direction not in {"POSITIVE", "NEGATIVE"}:
                    _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                    continue
                secondary_options_tuple, offset_shifts = _offset_transition_options(
                    context,
                    placed,
                    sorting,
                    secondary_options,
                    offset_direction,
                    finished_side,
                    stats,
                )
                secondary_options = secondary_options_tuple
                if not secondary_options:
                    _record_rejection(stats, "OFFSET_TRANSITION_UNAVAILABLE")
            for secondary in secondary_options:
                if stats.visited_nodes >= context.node_budget:
                    stats.node_budget_exhausted = True
                    stats.skeleton_search_truncated = True
                    return
                stats.current_work_item = {
                    "topology": context.structural_topology,
                    "envelope_family": plan.envelope.family,
                    "band_family": plan.layout_family,
                    "sorting_root_mm": list(sorting.bounds_mm),
                    "raw_side": raw_side,
                    "finished_side": finished_side,
                    "offset_direction": offset_direction,
                    "branch": "SECONDARY",
                }
                stats.visited_nodes += 1
                stats.construction_node_count += 1
                quantum = _quantum_checkpoint(stats)
                if quantum is not None:
                    yield quantum
                for descendant in ("coating_room", "finished_goods_room", "shipping_channel"):
                    placed.pop(descendant, None)
                placed["secondary_precooling_room"] = secondary
                coating_options = _constructive_edge_options(
                    context,
                    "coating_room",
                    placed,
                    "secondary_precooling_room",
                    bridge_code="sorting_packaging_room",
                    stats=stats,
                )
                for coating in coating_options:
                    if stats.visited_nodes >= context.node_budget:
                        stats.node_budget_exhausted = True
                        stats.skeleton_search_truncated = True
                        return
                    stats.current_work_item = {
                        "topology": context.structural_topology,
                        "envelope_family": plan.envelope.family,
                        "band_family": plan.layout_family,
                        "sorting_root_mm": list(sorting.bounds_mm),
                        "raw_side": raw_side,
                        "finished_side": finished_side,
                        "offset_direction": offset_direction,
                        "branch": "COATING",
                    }
                    stats.visited_nodes += 1
                    stats.construction_node_count += 1
                    quantum = _quantum_checkpoint(stats)
                    if quantum is not None:
                        yield quantum
                    placed.pop("finished_goods_room", None)
                    placed.pop("shipping_channel", None)
                    placed["coating_room"] = coating
                    finished_options = _constructive_edge_options(
                        context,
                        "finished_goods_room",
                        placed,
                        "coating_room",
                        anchor_reference_codes=(
                            ("secondary_precooling_room",)
                            if context.structural_topology == OFFSET_LINEAR_BAND
                            else ()
                        ),
                        stats=stats,
                    )
                    finished_options = _finished_options_by_shipping_approach(
                        context,
                        placed,
                        finished_options,
                    )
                    for finished in finished_options:
                        if stats.visited_nodes >= context.node_budget:
                            stats.node_budget_exhausted = True
                            stats.skeleton_search_truncated = True
                            return
                        stats.current_work_item = {
                            "topology": context.structural_topology,
                            "envelope_family": plan.envelope.family,
                            "band_family": plan.layout_family,
                            "sorting_root_mm": list(sorting.bounds_mm),
                            "raw_side": raw_side,
                            "finished_side": finished_side,
                            "offset_direction": offset_direction,
                            "branch": "FINISHED",
                        }
                        stats.visited_nodes += 1
                        stats.construction_node_count += 1
                        quantum = _quantum_checkpoint(stats)
                        if quantum is not None:
                            yield quantum
                        placed.pop("shipping_channel", None)
                        placed["finished_goods_room"] = finished
                        shipping_options = _constructive_edge_options(
                            context,
                            "shipping_channel",
                            placed,
                            "finished_goods_room",
                            prefer_truck_entrance=True,
                            stats=stats,
                        )
                        shipping_options = _shipping_options_by_loading_face_approach(
                            context, shipping_options
                        )
                        if not shipping_options:
                            _record_rejection(stats, "SHIPPING_INTERFACE_FAIL")
                        for shipping in shipping_options:
                            if stats.visited_nodes >= context.node_budget:
                                stats.node_budget_exhausted = True
                                stats.skeleton_search_truncated = True
                                return
                            stats.current_work_item = {
                                "topology": context.structural_topology,
                                "envelope_family": plan.envelope.family,
                                "band_family": plan.layout_family,
                                "sorting_root_mm": list(sorting.bounds_mm),
                                "raw_side": raw_side,
                                "finished_side": finished_side,
                                "offset_direction": offset_direction,
                                "branch": "SHIPPING",
                            }
                            stats.visited_nodes += 1
                            stats.construction_node_count += 1
                            quantum = _quantum_checkpoint(stats)
                            if quantum is not None:
                                yield quantum
                            placed["shipping_channel"] = shipping
                            if set(placed) != set(MAIN_PROCESS_ZONE_CODES):
                                _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                            elif not _main_group_order_monotonic(
                                placed, context.structural_skeleton
                            ):
                                _record_rejection(stats, "GROUP_ORDER_FAIL")
                            else:
                                try:
                                    classification = classify_main_process_topology_v1(placed)
                                    if classification.canonical_owner is None:
                                        _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                                        if stats.topology_classification_failures is None:
                                            stats.topology_classification_failures = []
                                        stats.topology_classification_failures.append(
                                            {
                                                "topology": context.structural_topology,
                                                "canonical_owner": None,
                                                "matched_topologies": list(
                                                    classification.matched_topologies
                                                ),
                                                "process_axis": classification.process_axis,
                                                "expected_process_axis": (
                                                    context.structural_skeleton.ordering_axis
                                                ),
                                                "zone_bounds_mm": {
                                                    code: list(_bounds(rectangle))
                                                    for code, rectangle in sorted(placed.items())
                                                },
                                            }
                                        )
                                        continue
                                    offset_shift = offset_shifts.get(_bounds(secondary))
                                    discovery_seed = MainProcessSkeletonCandidateV1.create(
                                        family=context.structural_composition_family,
                                        rectangles=placed,
                                        topology=context.structural_topology,
                                        generation_pattern=(
                                            f"{context.structural_topology}:"
                                            f"{plan.layout_family}:"
                                            f"RAW_{raw_side}:"
                                            f"RAW_BANK_{_adjacent_side(primary, raw)}:"
                                            f"FINISHED_{finished_side}:"
                                            f"ROOT_{sorting.x}_{sorting.y}_"
                                            "CONSTRUCTIVE_PROCESS_CHAIN"
                                        ),
                                        hard_geometry_predicates_passed=(
                                            "SITE_CONTAINMENT",
                                            "NO_BUILD_CLEAR",
                                            "NON_OVERLAP",
                                            "MUST_ADJACENCY",
                                            "GROUP_ORDER",
                                            "TOPOLOGY_RULE",
                                        ),
                                        construction_policy=(
                                            f"{context.structural_topology}_{plan.layout_family}_V1"
                                        ),
                                        topology_divergence_stage="ENVELOPE_GRID_BAND_FORMATION",
                                        offset_transition_stage=(
                                            "CORE_TO_FINISHED"
                                            if context.structural_topology == OFFSET_LINEAR_BAND
                                            else None
                                        ),
                                        offset_direction=offset_direction,
                                        offset_cross_axis_shift_mm=offset_shift,
                                        discovery_topology=context.structural_topology,
                                        discovery_family=context.structural_composition_family,
                                        building_layout_family=plan.layout_family,
                                        building_envelope_family=plan.envelope.family,
                                        planned_envelope_bounds_mm=getattr(
                                            plan.envelope, "bounds_mm", None
                                        ),
                                    )
                                    seed = canonicalize_main_process_skeleton_for_evaluation(
                                        discovery_seed,
                                        classification,
                                        site_geometry=context.site_body,
                                    )
                                    geometry_hash = seed.main_process_skeleton_hash
                                    if not _topology_geometry_valid(
                                        placed,
                                        seed.topology,
                                        seed.dominant_axis,
                                    ):
                                        _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                                        if stats.topology_classification_failures is None:
                                            stats.topology_classification_failures = []
                                        stats.topology_classification_failures.append(
                                            {
                                                "discovery_topology": context.structural_topology,
                                                "canonical_owner": seed.canonical_topology_owner,
                                                "matched_topologies": list(
                                                    classification.matched_topologies
                                                ),
                                                "process_axis": classification.process_axis,
                                                "expected_process_axis": seed.dominant_axis,
                                                "zone_bounds_mm": {
                                                    code: list(_bounds(rectangle))
                                                    for code, rectangle in sorted(placed.items())
                                                },
                                            }
                                        )
                                        continue
                                    if not _constructive_main_skeleton_tail_admission(
                                        context, stats, seed
                                    ):
                                        continue
                                    registry = context.global_main_process_geometry_registry
                                    existing = (
                                        registry.get(geometry_hash)
                                        if registry is not None
                                        else None
                                    )
                                    first_discovery_topology = (
                                        str(existing["first_discovery_topology"])
                                        if existing is not None
                                        else None
                                    )
                                    cached_preflight_status = (
                                        existing.get("packaging_preflight_status")
                                        if existing is not None
                                        else None
                                    )
                                    if cached_preflight_status == "NO_LEGAL_SLOT":
                                        assert existing is not None
                                        duplicate_preflight_row = {
                                            "event": "DUPLICATE_PRETAIL_REJECTED_GEOMETRY",
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "packaging_preflight_status": (cached_preflight_status),
                                            "packaging_slot_exists": False,
                                            "tail_admissible": False,
                                            "tail_search_started": False,
                                            "preflight_reexecuted": False,
                                        }
                                        if stats.tail_slot_preflight_rows is None:
                                            stats.tail_slot_preflight_rows = []
                                        stats.tail_slot_preflight_rows.append(
                                            duplicate_preflight_row
                                        )
                                        if (
                                            context.global_cross_topology_duplicate_trace
                                            is not None
                                            and existing.get("first_discovery_topology")
                                            != context.structural_topology
                                        ):
                                            stats.cross_topology_duplicate_count += 1
                                            context.global_cross_topology_duplicate_trace.append(
                                                duplicate_preflight_row
                                            )
                                        continue

                                    if cached_preflight_status is None:
                                        preflight_result = _packaging_tail_slot_preflight(
                                            context, seed
                                        )
                                        proof_mode = str(preflight_result["proof_mode"])
                                        slot_exists = preflight_result["legal_slot_exists"]
                                        preflight_status = (
                                            "NO_LEGAL_SLOT"
                                            if slot_exists is False
                                            and proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION
                                            else "LEGAL_SLOT_EXISTS"
                                            if slot_exists is True
                                            else "UNAVAILABLE"
                                        )
                                        tail_search_admitted = preflight_status != "NO_LEGAL_SLOT"
                                        preflight_row = {
                                            "event": "TAIL_SLOT_PREFLIGHT",
                                            "stage": "TAIL_SLOT_PREFLIGHT",
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "canonical_family": seed.family.to_dict(),
                                            "packaging_preflight_status": preflight_status,
                                            "packaging_slot_exists": slot_exists,
                                            "tail_admissible": (
                                                False
                                                if preflight_status == "NO_LEGAL_SLOT"
                                                else None
                                                if preflight_status == "UNAVAILABLE"
                                                else True
                                            ),
                                            "tail_search_started": tail_search_admitted,
                                            "preflight_reexecuted": True,
                                            "preflight": preflight_result,
                                        }
                                        if stats.tail_slot_preflight_rows is None:
                                            stats.tail_slot_preflight_rows = []
                                        stats.tail_slot_preflight_rows.append(preflight_row)
                                        if registry is not None:
                                            registry_row = existing if existing is not None else {}
                                            registry_row.update(
                                                {
                                                    "skeleton_hash": geometry_hash,
                                                    "first_discovery_topology": (
                                                        first_discovery_topology
                                                        or context.structural_topology
                                                    ),
                                                    "canonical_topology_owner": (
                                                        seed.canonical_topology_owner
                                                    ),
                                                    "canonical_family": seed.family.to_dict(),
                                                    "packaging_preflight_status": preflight_status,
                                                    "packaging_slot_exists": slot_exists,
                                                    "tail_admissible": preflight_row[
                                                        "tail_admissible"
                                                    ],
                                                    "tail_search_started": False,
                                                    "tail_search_discovery_topology": None,
                                                    "p2d_reached": False,
                                                    "p2d_candidate_count": 0,
                                                    "p2d_full_pass_count": 0,
                                                }
                                            )
                                            registry[geometry_hash] = registry_row
                                        if preflight_status == "NO_LEGAL_SLOT":
                                            _record_rejection(
                                                stats,
                                                "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT",
                                            )
                                            if stats.skeleton_tail_lifecycle is None:
                                                stats.skeleton_tail_lifecycle = []
                                            stats.skeleton_tail_lifecycle.append(
                                                {
                                                    "topology": seed.topology,
                                                    "skeleton_hash": geometry_hash,
                                                    "discovery_topology": (
                                                        context.structural_topology
                                                    ),
                                                    "canonical_topology_owner": (
                                                        seed.canonical_topology_owner
                                                    ),
                                                    "canonical_family": seed.family.to_dict(),
                                                    "packaging_preflight_executed": True,
                                                    "packaging_slot_exists": False,
                                                    "tail_admissible": False,
                                                    "tail_search_started": False,
                                                    "tail_nodes": 0,
                                                    "tail_node_limit": 0,
                                                    "complete_candidate_count": 0,
                                                    "p2d_reached": False,
                                                    "first_failure_stage": "TAIL_SLOT_PREFLIGHT",
                                                    "first_failure_reason": (
                                                        "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT"
                                                    ),
                                                }
                                            )
                                            continue
                                    else:
                                        assert existing is not None
                                        preflight_status = str(cached_preflight_status)
                                        slot_exists = existing.get("packaging_slot_exists")
                                        preflight_row = {
                                            "event": "CACHED_TAIL_SLOT_PREFLIGHT",
                                            "stage": "TAIL_SLOT_PREFLIGHT",
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "packaging_preflight_status": preflight_status,
                                            "packaging_slot_exists": slot_exists,
                                            "tail_admissible": existing.get("tail_admissible"),
                                            "tail_search_started": False,
                                            "preflight_reexecuted": False,
                                        }
                                        if stats.tail_slot_preflight_rows is None:
                                            stats.tail_slot_preflight_rows = []
                                        stats.tail_slot_preflight_rows.append(preflight_row)

                                    cached_truck_preflight = (
                                        existing.get("main_skeleton_truck_preflight")
                                        if existing is not None
                                        else None
                                    )
                                    if isinstance(cached_truck_preflight, Mapping):
                                        truck_preflight_row = {
                                            **dict(cached_truck_preflight),
                                            "event": "CACHED_MAIN_SKELETON_TRUCK_PREFLIGHT",
                                            "discovery_topology": context.structural_topology,
                                            "preflight_reexecuted": False,
                                            "preflight_compute_nodes": int(
                                                cached_truck_preflight.get(
                                                    "preflight_compute_nodes",
                                                    cached_truck_preflight.get("visited_nodes", 0),
                                                )
                                            ),
                                        }
                                    else:
                                        truck_preflight_result = (
                                            _main_skeleton_truck_maneuver_preflight(context, seed)
                                        )
                                        truck_preflight_row = {
                                            **truck_preflight_result,
                                            "event": "MAIN_SKELETON_TRUCK_PREFLIGHT",
                                            "stage": "MAIN_SKELETON_TRUCK_PREFLIGHT",
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "canonical_family": seed.family.to_dict(),
                                            "preflight_reexecuted": True,
                                            "preflight_compute_nodes": int(
                                                truck_preflight_result["visited_nodes"]
                                            ),
                                        }
                                    truck_preflight_row.update(
                                        {
                                            "layout_family": seed.building_layout_family,
                                            "envelope_family": seed.building_envelope_family,
                                            "planned_envelope_bounds_mm": (
                                                list(seed.planned_envelope_bounds_mm)
                                                if seed.planned_envelope_bounds_mm is not None
                                                else None
                                            ),
                                        }
                                    )
                                    if registry is not None:
                                        registry_row = (
                                            existing
                                            if existing is not None
                                            else registry.get(geometry_hash, {})
                                        )
                                        registry_row.update(
                                            {
                                                "skeleton_hash": geometry_hash,
                                                "first_discovery_topology": (
                                                    first_discovery_topology
                                                    or context.structural_topology
                                                ),
                                                "main_skeleton_truck_preflight": dict(
                                                    truck_preflight_row
                                                ),
                                            }
                                        )
                                        registry_row.setdefault("tail_search_started", False)
                                        registry_row.setdefault(
                                            "tail_search_discovery_topology", None
                                        )
                                        registry_row.setdefault("p2d_reached", False)
                                        registry_row.setdefault("p2d_candidate_count", 0)
                                        registry_row.setdefault("p2d_full_pass_count", 0)
                                        registry[geometry_hash] = registry_row
                                    if stats.main_skeleton_truck_preflight_rows is None:
                                        stats.main_skeleton_truck_preflight_rows = []
                                    stats.main_skeleton_truck_preflight_rows.append(
                                        truck_preflight_row
                                    )
                                    if truck_preflight_row["preflight_status"] == "REJECT":
                                        if stats.skeleton_tail_lifecycle is None:
                                            stats.skeleton_tail_lifecycle = []
                                        stats.skeleton_tail_lifecycle.append(
                                            {
                                                "topology": seed.topology,
                                                "skeleton_hash": geometry_hash,
                                                "discovery_topology": context.structural_topology,
                                                "canonical_topology_owner": (
                                                    seed.canonical_topology_owner
                                                ),
                                                "canonical_family": seed.family.to_dict(),
                                                "packaging_preflight_executed": True,
                                                "packaging_preflight_status": preflight_status,
                                                "packaging_slot_exists": slot_exists,
                                                "main_skeleton_truck_preflight_executed": True,
                                                "main_skeleton_truck_preflight_status": "REJECT",
                                                "truck_preflight_failure_codes": list(
                                                    truck_preflight_row.get("failure_codes", [])
                                                ),
                                                "truck_preflight_visited_nodes": int(
                                                    truck_preflight_row.get("visited_nodes", 0)
                                                ),
                                                "truck_preflight_node_budget": int(
                                                    truck_preflight_row.get("node_budget", 0)
                                                ),
                                                "truck_preflight_node_budget_exhausted": (
                                                    truck_preflight_row.get("node_budget_exhausted")
                                                ),
                                                "truck_preflight_search_tree_exhausted": (
                                                    truck_preflight_row.get("search_tree_exhausted")
                                                ),
                                                "tail_search_started": False,
                                                "tail_nodes": 0,
                                                "tail_node_limit": 0,
                                                "complete_candidate_count": 0,
                                                "p2d_reached": False,
                                                "first_failure_stage": (
                                                    "MAIN_SKELETON_TRUCK_PREFLIGHT"
                                                ),
                                                "first_failure_reason": (
                                                    truck_preflight_row.get("failure_reason")
                                                    or "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
                                                ),
                                            }
                                        )
                                        continue

                                    tail_search_discovery_topology = (
                                        str(existing["tail_search_discovery_topology"])
                                        if existing is not None
                                        and existing.get("tail_search_discovery_topology")
                                        is not None
                                        else None
                                    )
                                    ownership_decision = decide_main_process_topology_ownership_v1(
                                        lane_topology=context.structural_topology,
                                        canonical_owner=seed.canonical_topology_owner,
                                        first_discovery_topology=first_discovery_topology,
                                        tail_search_discovery_topology=(
                                            tail_search_discovery_topology
                                        ),
                                        geometry_previously_seen=existing is not None,
                                        tail_search_started=(
                                            existing is not None
                                            and existing.get("tail_search_started") is True
                                        ),
                                    )
                                    truck_preflight_row["tail_search_started"] = (
                                        ownership_decision.start_tail_search
                                    )
                                    if not ownership_decision.start_tail_search:
                                        if ownership_decision.cross_topology_duplicate:
                                            stats.cross_topology_duplicate_count += 1
                                        duplicate_row = {
                                            "event": "EXISTING_GEOMETRY_DUPLICATE_DISCOVERY",
                                            "skeleton_hash": geometry_hash,
                                            "first_discovery_topology": first_discovery_topology,
                                            "duplicate_discovery_topology": (
                                                context.structural_topology
                                            ),
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "tail_search_started_by_topology": (
                                                tail_search_discovery_topology
                                            ),
                                            "cross_topology_duplicate": (
                                                ownership_decision.cross_topology_duplicate
                                            ),
                                            "duplicate_action": ownership_decision.action,
                                            "construction_attempt_index": len(
                                                stats.skeleton_construction_attempts or []
                                            ),
                                        }
                                        if stats.topology_ownership_duplicates is None:
                                            stats.topology_ownership_duplicates = []
                                        stats.topology_ownership_duplicates.append(duplicate_row)
                                        if (
                                            ownership_decision.cross_topology_duplicate
                                            and context.global_cross_topology_duplicate_trace
                                            is not None
                                        ):
                                            context.global_cross_topology_duplicate_trace.append(
                                                duplicate_row
                                            )
                                        continue

                                    if registry is not None:
                                        registry_row = (
                                            existing
                                            if existing is not None
                                            else registry.get(geometry_hash, {})
                                        )
                                        registry_row.update(
                                            {
                                                "skeleton_hash": geometry_hash,
                                                "first_discovery_topology": (
                                                    first_discovery_topology
                                                    or context.structural_topology
                                                ),
                                                "canonical_topology_owner": (
                                                    seed.canonical_topology_owner
                                                ),
                                                "canonical_family": seed.family.to_dict(),
                                                "tail_search_started": True,
                                                "tail_search_discovery_topology": (
                                                    context.structural_topology
                                                ),
                                                "packaging_preflight_status": preflight_status,
                                                "packaging_slot_exists": slot_exists,
                                                "tail_admissible": (
                                                    existing.get("tail_admissible")
                                                    if existing is not None
                                                    else preflight_row.get("tail_admissible")
                                                ),
                                            }
                                        )
                                        truck_preflight = registry_row.get(
                                            "main_skeleton_truck_preflight"
                                        )
                                        if isinstance(truck_preflight, Mapping):
                                            registry_row["main_skeleton_truck_preflight"] = {
                                                **dict(truck_preflight),
                                                "tail_search_started": True,
                                            }
                                        registry_row.setdefault("p2d_reached", False)
                                        registry_row.setdefault("p2d_candidate_count", 0)
                                        registry_row.setdefault("p2d_full_pass_count", 0)
                                        registry[geometry_hash] = registry_row
                                    if stats.geometry_evaluation_admissions is None:
                                        stats.geometry_evaluation_admissions = []
                                    stats.geometry_evaluation_admissions.append(
                                        {
                                            "event": (
                                                "NEW_GEOMETRY_NON_OWNER_DISCOVERY"
                                                if context.structural_topology
                                                != seed.canonical_topology_owner
                                                else "NEW_GEOMETRY_DISCOVERY"
                                            ),
                                            "skeleton_hash": geometry_hash,
                                            "discovery_topology": context.structural_topology,
                                            "canonical_topology_owner": (
                                                seed.canonical_topology_owner
                                            ),
                                            "discovery_lane_matches_canonical_owner": (
                                                context.structural_topology
                                                == seed.canonical_topology_owner
                                            ),
                                            "discovery_family": (
                                                context.structural_composition_family.to_dict()
                                            ),
                                            "canonical_family": seed.family.to_dict(),
                                            "geometry_previously_seen": (
                                                ownership_decision.geometry_previously_seen
                                            ),
                                            "action": ownership_decision.action,
                                            "evaluation_admission": "TAIL_SEARCH_STARTED",
                                        }
                                    )
                                except LayoutAuthorityError:
                                    _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                                else:
                                    # Emit this seed only after every exact geometry,
                                    # packaging-slot, truck, and ownership gate above
                                    # completed successfully. This is the try/except
                                    # success clause; a for-else here can run after an
                                    # invalid branch and reference an unbound `seed`.
                                    emitted_skeletons += 1
                                    yield seed
                        if emitted_skeletons >= skeleton_limit:
                            return


def _construct_main_process_skeletons(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]:
    """Try distinct band construction policies under the shared node budget."""
    reference_plan = context.structured_building_plan
    if reference_plan is None:
        return
    if stats.constructive_divergence_attempts is None:
        stats.constructive_divergence_attempts = []
    preferred_axis = reference_plan.process_axis
    alternate_axis = "X" if preferred_axis == "Y" else "Y"
    if context.search_phase == GENERAL_FALLBACK_PHASE:
        primary_family = reference_plan.layout_family
        legacy_family_order = {
            LINEAR_3_BAND: (
                LINEAR_3_BAND,
                LONGITUDINAL_PROCESS_SPINE,
                CENTRAL_PROCESS_WITH_SIDE_BANKS,
            ),
            LONGITUDINAL_PROCESS_SPINE: (
                LONGITUDINAL_PROCESS_SPINE,
                LINEAR_3_BAND,
                CENTRAL_PROCESS_WITH_SIDE_BANKS,
            ),
            CENTRAL_PROCESS_WITH_SIDE_BANKS: (
                CENTRAL_PROCESS_WITH_SIDE_BANKS,
                LONGITUDINAL_PROCESS_SPINE,
                LINEAR_3_BAND,
            ),
        }.get(primary_family, (primary_family,))
        variant_pairs = tuple((family, preferred_axis) for family in legacy_family_order)
    else:
        variant_pairs = tuple(
            (family, process_axis)
            for family in BASE_LAYOUT_FAMILIES
            for process_axis in (preferred_axis, alternate_axis)
        )
    searches: list[
        tuple[tuple[str, str], Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]]
    ] = []
    for layout_family, process_axis in variant_pairs:
        plan: StructuredBuildingSkeletonV1 | None = None
        envelope_failures: list[str] = []
        if context.search_phase == GENERAL_FALLBACK_PHASE:
            plan = construct_legacy_compatibility_search_plan_v1(
                boundary=context.boundary,
                obstacles=context.obstacles,
                authorities=context.authorities,
                process_axis=process_axis,
                process_direction=(
                    context.structural_composition_family.dominant_direction
                    if context.structural_composition_family.dominant_direction
                    in {"POSITIVE", "NEGATIVE"}
                    else "POSITIVE"
                ),
                layout_family=layout_family,
                main_entrance=context.main_entrance,
            )
        else:
            # Axis is an explicit candidate dimension, not an exclusive
            # selector outcome. Each family constructs its own envelope,
            # grid, and bands on both orthogonal orientations.
            for envelope_family in (RECTANGLE, SIMPLE_L):
                try:
                    plan = construct_structured_building_plan_v1(
                        boundary=context.boundary,
                        obstacles=context.obstacles,
                        authorities=context.authorities,
                        process_axis=process_axis,
                        layout_family=layout_family,
                        envelope_family=envelope_family,
                        main_entrance=context.main_entrance,
                    )
                except LayoutAuthorityError as error:
                    envelope_failures.append(error.code)
                    continue
                break
        stats.constructive_divergence_attempts.append(
            {
                "topology": context.structural_topology,
                "layout_family": layout_family,
                "process_axis": process_axis,
                "attempted": True,
                "construction_policy": f"{layout_family}_{process_axis}_V1",
                "divergence_stage": "ENVELOPE_GRID_BAND_FORMATION",
                "result": "PLAN_READY" if plan is not None else "NO_SITE_FEASIBLE_ENVELOPE",
                "envelope_failures": envelope_failures,
                "selected_envelope_family": plan.envelope.family if plan is not None else None,
                "envelope_bounds_mm": (list(plan.envelope.bounds_mm) if plan is not None else None),
                "envelope_components_mm": (
                    [list(row) for row in plan.envelope.components_mm] if plan is not None else []
                ),
                "primary_x_axes_mm": (
                    list(plan.primary_grid.x_axes_mm) if plan is not None else []
                ),
                "primary_y_axes_mm": (
                    list(plan.primary_grid.y_axes_mm) if plan is not None else []
                ),
                "local_event_x_axis_count": (
                    len(plan.primary_grid.event_x_mm) if plan is not None else 0
                ),
                "local_event_y_axis_count": (
                    len(plan.primary_grid.event_y_mm) if plan is not None else 0
                ),
                "functional_band_bounds_mm": (
                    {band.band_code: list(band.bounds_mm) for band in plan.bands}
                    if plan is not None
                    else {}
                ),
                "support_band_is_full_envelope": (
                    plan.band_for_zone("packaging_material_storage").bounds_mm
                    == plan.envelope.bounds_mm
                    if plan is not None
                    else None
                ),
                "personnel_band_is_full_envelope": (
                    plan.band_for_zone("office").bounds_mm == plan.envelope.bounds_mm
                    if plan is not None
                    else None
                ),
            }
        )
        if plan is None:
            continue
        plan_context = replace(
            context,
            structured_building_plan=plan,
            structural_skeleton=replace(context.structural_skeleton, ordering_axis=process_axis),
        )
        searches.append(
            (
                (layout_family, process_axis),
                iter(_construct_main_process_skeletons_for_plan(plan_context, stats)),
            )
        )

    # Completion coverage is selector-global, not a per-lane quotient.  A
    # lane's node allowance already bounds its work; dividing that allowance
    # by a nominal per-skeleton estimate here used to stop at two seeds in a
    # 40-node lane and prevented the remaining band policies from running.
    skeleton_limit = CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT
    eligible_variants = tuple(variant for variant, _search in searches)

    def family_coverage_count(variant: tuple[str, str]) -> int:
        family, axis = variant
        return sum(
            1
            for skeleton in (stats.constructed_main_skeletons or {}).values()
            if skeleton.building_layout_family == family and skeleton.dominant_axis == axis
        )

    while searches:
        if stats.node_budget_exhausted:
            return
        coverage_complete = all(family_coverage_count(variant) > 0 for variant in eligible_variants)
        if len(stats.constructed_main_skeletons or {}) >= skeleton_limit and coverage_complete:
            stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
            return
        selected_index = min(
            range(len(searches)),
            key=lambda index: (
                family_coverage_count(searches[index][0]),
                index,
            ),
        )
        layout_variant, search = searches.pop(selected_index)
        try:
            item = next(search)
        except StopIteration:
            continue
        yield item
        if stats.node_budget_exhausted:
            return
        coverage_complete = all(family_coverage_count(variant) > 0 for variant in eligible_variants)
        if len(stats.constructed_main_skeletons or {}) >= skeleton_limit and coverage_complete:
            stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
            return
        searches.append((layout_variant, search))


def _construct_main_process_skeletons_for_plan(
    context: _PlacementSearchContext,
    stats: _PlacementSearchStats,
) -> Iterator[MainProcessSkeletonCandidateV1 | _SearchQuantumYield]:
    """Build full seven-zone candidates before any support/personnel search."""
    plan = context.structured_building_plan
    if plan is None:
        return
    # This is a selector-wide coverage ceiling.  Per-lane/context node budgets
    # are enforced at each exact search node below; using them again to derive
    # a lifetime completion cap starves later envelope/grid/band policies.
    skeleton_completion_limit = CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT
    if stats.constructed_main_skeletons is None:
        stats.constructed_main_skeletons = {}
    if stats.skeleton_generation_patterns is None:
        stats.skeleton_generation_patterns = {}
    if stats.skeleton_construction_attempts is None:
        stats.skeleton_construction_attempts = []
    roots = _constructive_sorting_roots(context, stats)
    emitted = sum(
        1
        for skeleton in stats.constructed_main_skeletons.values()
        if getattr(skeleton, "building_layout_family", None) == plan.layout_family
    )
    previous_seed_node = 0
    if stats.constructive_divergence_attempts is None:
        stats.constructive_divergence_attempts = []
    directions: tuple[str | None, ...] = (
        ("POSITIVE", "NEGATIVE") if context.structural_topology == OFFSET_LINEAR_BAND else (None,)
    )
    stats.constructive_divergence_attempts.append(
        {
            "topology": context.structural_topology,
            "attempted": True,
            "construction_policy": f"{context.structural_topology}_V1",
            "divergence_stage": (
                "CORE_TO_FINISHED"
                if context.structural_topology == OFFSET_LINEAR_BAND
                else "RAW_FINISHED_FACE_PAIR"
                if context.structural_topology == CENTRAL_PROCESS_HUB
                else "ROOT_OR_GROUP_BAND_FORMATION"
            ),
            "offset_directions": [value for value in directions if value is not None],
        }
    )
    face_pairs = _family_attachment_sides(
        context.structural_composition_family, context.structural_topology
    )
    attempts = tuple(
        (raw_side, finished_side, offset_direction)
        for raw_side, finished_side in face_pairs
        for offset_direction in directions
    )

    def attachment_attempt_key(
        item: tuple[int, tuple[str, str, str | None]],
    ) -> tuple[int, int, int, int, int, int, int]:
        original_index, (raw_side, finished_side, _offset_direction) = item
        best_root_key = min(
            (
                _sorting_root_attachment_pair_key(context, root, raw_side, finished_side)
                for root in roots
            ),
            default=(10**18, 10**18, 10**18, 10**18, 10**18, 10**18),
        )
        return (*best_root_key, original_index)

    ordered_attempts = sorted(enumerate(attempts), key=attachment_attempt_key)
    for face_pair_index, (raw_side, finished_side, offset_direction) in ordered_attempts:
        if emitted >= skeleton_completion_limit:
            stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
            return
        face_pair_roots = (
            roots
            if context.search_phase == GENERAL_FALLBACK_PHASE
            else _sorting_roots_for_attachment_pair(context, roots, raw_side, finished_side)
        )
        for sorting in face_pair_roots:
            if stats.visited_nodes >= context.node_budget:
                stats.node_budget_exhausted = True
                stats.skeleton_search_truncated = True
                return
            stats.current_work_item = {
                "topology": context.structural_topology,
                "envelope_family": plan.envelope.family,
                "band_family": plan.layout_family,
                "family": context.structural_composition_family.to_dict(),
                "axis": context.structural_composition_family.dominant_axis,
                "direction": context.structural_composition_family.dominant_direction,
                "sorting_root_mm": list(sorting.bounds_mm),
                "raw_side": raw_side,
                "finished_side": finished_side,
                "offset_direction": offset_direction,
                "branch": "SORTING_ROOT",
                "face_pair_index": face_pair_index,
            }
            stats.visited_nodes += 1
            stats.construction_node_count += 1
            quantum = _quantum_checkpoint(stats)
            if quantum is not None:
                yield quantum
            face_pair_node_quantum = CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET
            sorting_root_node_quantum = CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET
            emitted_for_face = 0
            rejection_counts_before = dict(stats.rejection_reason_counts or {})
            attempt_skeleton_hashes: list[str] = []
            attempt_node_start = stats.visited_nodes
            for seed in _construct_face_skeletons(
                context,
                stats,
                sorting,
                raw_side,
                finished_side,
                context.node_budget,
                skeleton_limit=max(1, skeleton_completion_limit - emitted),
                offset_direction=offset_direction,
            ):
                if isinstance(seed, _SearchQuantumYield):
                    yield seed
                    continue
                if seed.main_process_skeleton_hash in stats.constructed_main_skeletons:
                    _record_rejection(stats, "SKELETON_TOPOLOGY_INVALID")
                    continue
                stats.constructed_main_skeletons[seed.main_process_skeleton_hash] = seed
                if stats.construction_nodes_by_skeleton is None:
                    stats.construction_nodes_by_skeleton = {}
                stats.construction_nodes_by_skeleton[seed.main_process_skeleton_hash] = max(
                    0, stats.visited_nodes - previous_seed_node
                )
                previous_seed_node = stats.visited_nodes
                attempt_skeleton_hashes.append(seed.main_process_skeleton_hash)
                stats.skeleton_generation_patterns[seed.generation_pattern] = (
                    stats.skeleton_generation_patterns.get(seed.generation_pattern, 0) + 1
                )
                emitted += 1
                emitted_for_face += 1
                yield seed
                if emitted >= skeleton_completion_limit:
                    stats.normal_stop_reason = "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT"
                    stats.skeleton_construction_attempts.append(
                        {
                            "topology": context.structural_topology,
                            "envelope_family": plan.envelope.family,
                            "band_family": plan.layout_family,
                            "offset_direction": offset_direction,
                            "construction_attempt_index": len(stats.skeleton_construction_attempts),
                            "raw_side": raw_side,
                            "finished_side": finished_side,
                            "sorting_root_mm": list(sorting.bounds_mm),
                            "result": "SKELETON_CONSTRUCTED",
                            "skeleton_hashes": attempt_skeleton_hashes,
                            "face_pair_node_quantum": face_pair_node_quantum,
                            "sorting_root_node_quantum": sorting_root_node_quantum,
                            "search_truncated": False,
                            "visited_node_delta": stats.visited_nodes - attempt_node_start,
                        }
                    )
                    return
            if stats.node_budget_exhausted:
                return
            rejection_counts_after = stats.rejection_reason_counts or {}
            stats.skeleton_construction_attempts.append(
                {
                    "topology": context.structural_topology,
                    "envelope_family": plan.envelope.family,
                    "band_family": plan.layout_family,
                    "offset_direction": offset_direction,
                    "construction_attempt_index": len(stats.skeleton_construction_attempts),
                    "raw_side": raw_side,
                    "finished_side": finished_side,
                    "sorting_root_mm": list(sorting.bounds_mm),
                    "result": "TRUNCATED"
                    if stats.node_budget_exhausted
                    else "SKELETON_CONSTRUCTED"
                    if attempt_skeleton_hashes
                    else "REJECTED",
                    "face_pair_node_quantum": face_pair_node_quantum,
                    "sorting_root_node_quantum": sorting_root_node_quantum,
                    "search_truncated": stats.node_budget_exhausted,
                    "skeleton_hashes": attempt_skeleton_hashes,
                    "rejection_reason_counts": {
                        reason: rejection_counts_after.get(reason, 0) - count
                        for reason, count in sorted(rejection_counts_before.items())
                        if rejection_counts_after.get(reason, 0) > count
                    }
                    | {
                        reason: count
                        for reason, count in sorted(rejection_counts_after.items())
                        if reason not in rejection_counts_before and count > 0
                    },
                    "visited_node_delta": stats.visited_nodes - attempt_node_start,
                }
            )


def _canonical_tail_search_context(
    discovery_context: _PlacementSearchContext,
    skeleton: MainProcessSkeletonCandidateV1,
) -> _PlacementSearchContext:
    """Bind tail search to the canonical geometry family without moving it."""
    canonical_topology = skeleton.canonical_topology_owner
    canonical_family = skeleton.family
    if canonical_topology != skeleton.topology or canonical_family.family not in {
        CENTRAL_PROCESS_HUB,
        LINEAR_PROCESS_BAND,
    }:
        raise _error("CANONICAL_SKELETON_IDENTITY_INCONSISTENT")
    structural_skeleton = next(
        (
            row
            for row in structural_skeleton_candidates(
                discovery_context.site_body,
                tuple(discovery_context.authorities),
                zone_authorities=discovery_context.authorities,
                family_candidates=(canonical_family,),
            )
            if row.family.to_dict() == canonical_family.to_dict()
        ),
        None,
    )
    if structural_skeleton is None:
        raise _error("CANONICAL_STRUCTURAL_SKELETON_UNAVAILABLE")
    placement_zone_order = (
        LINEAR_STRUCTURED_PLACEMENT_ZONE_ORDER
        if canonical_family.family == LINEAR_PROCESS_BAND
        else STRUCTURED_PLACEMENT_ZONE_ORDER
    )
    if discovery_context.search_phase == GENERAL_FALLBACK_PHASE:
        compatibility_plan = discovery_context.structured_building_plan
        if compatibility_plan is None:
            raise _error("GENERAL_FALLBACK_SEARCH_PLAN_UNAVAILABLE")
        canonical_plan = replace(
            compatibility_plan,
            layout_family=structured_layout_family_for_topology(canonical_topology),
            process_axis=structural_skeleton.ordering_axis,
            process_direction=canonical_family.dominant_direction,
        )
    else:
        canonical_plan = construct_structured_building_plan_v1(
            boundary=discovery_context.boundary,
            obstacles=discovery_context.obstacles,
            authorities=discovery_context.authorities,
            process_axis=structural_skeleton.ordering_axis,
            layout_family=skeleton.building_layout_family or LINEAR_3_BAND,
            envelope_family=skeleton.building_envelope_family or RECTANGLE,
            main_entrance=discovery_context.main_entrance,
        )
    return replace(
        discovery_context,
        structural_composition_family=canonical_family,
        structural_skeleton=structural_skeleton,
        structured_building_plan=canonical_plan,
        structural_topology=canonical_topology,
        placement_zone_order=placement_zone_order,
    )


def _walk_complete_candidate_payloads(
    context: _PlacementSearchContext, stats: _PlacementSearchStats
) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
    """Yield every complete P2C candidate until the node budget is exhausted."""
    if context.search_phase == STRUCTURED_PHASE and context.direct_synthesis_enabled:
        yield from _direct_structured_candidates(context, stats)
        return
    if context.search_phase == STRUCTURED_PHASE and context.structured_building_plan is None:
        return
    placed: dict[str, PlacedRectangleV1] = {}
    # Keep the separately accounted R2 fallback phase on the R1 structured
    # candidate mechanics. The phase label remains GENERAL_FALLBACK_PHASE;
    # only candidate anchoring/admission follows the compatibility path.
    candidate_policy_phase = (
        STRUCTURED_PHASE if context.search_phase == GENERAL_FALLBACK_PHASE else context.search_phase
    )
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

    def visit(
        index: int,
        structurally_generated: bool,
        main_process_skeleton: MainProcessSkeletonCandidateV1 | None = None,
    ) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
        root_signature = core_root_signature()
        if (
            candidate_policy_phase == STRUCTURED_PHASE
            and index >= len(MAIN_PROCESS_ZONE_CODES)
            and len(placed) >= len(MAIN_PROCESS_ZONE_CODES)
            and main_skeleton_completions.get(main_skeleton_signature(), 0)
            >= STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON
        ):
            return
        if (
            candidate_policy_phase == STRUCTURED_PHASE
            and index > 0
            and root_signature is not None
            and core_root_completions.get(root_signature, 0) >= STRUCTURED_COMPLETIONS_PER_CORE_ROOT
        ):
            return
        if stats.visited_nodes >= context.node_budget:
            stats.node_budget_exhausted = True
            return
        stats.visited_nodes += 1
        stats.current_work_item = {
            "topology": context.structural_topology,
            "band_family": (
                context.structured_building_plan.layout_family
                if context.structured_building_plan is not None
                else None
            ),
            "envelope_family": (
                context.structured_building_plan.envelope.family
                if context.structured_building_plan is not None
                else None
            ),
            "skeleton_hash": (
                main_process_skeleton.main_process_skeleton_hash
                if main_process_skeleton is not None
                else None
            ),
            "zone_code": context.placement_zone_order[index]
            if index < len(context.placement_zone_order)
            else None,
            "branch": "TAIL" if main_process_skeleton is not None else "GENERAL",
        }
        if main_process_skeleton is not None:
            if stats.tail_nodes_by_skeleton is None:
                stats.tail_nodes_by_skeleton = {}
            skeleton_hash = main_process_skeleton.main_process_skeleton_hash
            stats.tail_nodes_by_skeleton[skeleton_hash] = (
                stats.tail_nodes_by_skeleton.get(skeleton_hash, 0) + 1
            )
        quantum = _quantum_checkpoint(stats)
        if quantum is not None:
            yield quantum
        # Constructed main-process skeletons have already passed their
        # discovery-topology construction predicates and exact canonical
        # classification. Reapplying this lane-oriented proxy after family
        # rebinding would turn canonical identity into a second admission gate.
        if (
            candidate_policy_phase == STRUCTURED_PHASE
            and main_process_skeleton is None
            and index == len(MAIN_PROCESS_ZONE_CODES)
            and not _main_group_order_monotonic(placed, context.structural_skeleton)
        ):
            return
        if index == len(context.placement_zone_order):
            _validate_graph_completeness(context.graph, placed)
            stats.complete_candidates += 1
            if candidate_policy_phase == STRUCTURED_PHASE:
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
            if candidate_policy_phase == STRUCTURED_PHASE:
                assert context.structured_building_plan is not None
                payload["_structured_building_plan"] = (
                    context.structured_building_plan.with_placements(placed).to_dict()
                )
            if main_process_skeleton is not None:
                payload["_main_process_skeleton"] = main_process_skeleton.to_evaluation_dict()
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
                search_phase=candidate_policy_phase,
                structural_skeleton=context.structural_skeleton,
                structured_building_plan=context.structured_building_plan,
                zone_authorities=context.authorities,
                truck_entrance=truck_entrance,
            )
        if main_process_skeleton is not None and index >= len(MAIN_PROCESS_ZONE_CODES):
            if stats.tail_zone_search_facts is None:
                stats.tail_zone_search_facts = {}
            skeleton_facts = stats.tail_zone_search_facts.setdefault(
                main_process_skeleton.main_process_skeleton_hash, {}
            )
            zone_facts = skeleton_facts.setdefault(
                code,
                {
                    "branch_visits": 0,
                    "candidate_options": 0,
                    "skeleton_region_options": 0,
                    "empty_option_branches": 0,
                },
            )
            zone_facts["branch_visits"] += 1
            zone_facts["candidate_options"] += len(options)
            skeleton_region_options = sum(
                int(
                    candidate_policy_phase != STRUCTURED_PHASE
                    or _candidate_fits_skeleton_region(
                        code, rectangle, placed, context.structural_skeleton
                    )
                )
                for rectangle in options
            )
            zone_facts["skeleton_region_options"] += skeleton_region_options
            if not skeleton_region_options:
                zone_facts["empty_option_branches"] += 1
        stats.generated_candidates += len(options)
        for rectangle in options:
            if candidate_policy_phase == STRUCTURED_PHASE and not _candidate_fits_skeleton_region(
                code, rectangle, placed, context.structural_skeleton
            ):
                continue
            structural_refs = structural_anchor_references(code, tuple(placed))
            if candidate_policy_phase == STRUCTURED_PHASE and code in MAIN_PROCESS_ZONE_CODES:
                # Main-flow candidates are structurally generated only after
                # passing the versioned group/band predicate and existing
                # MUST-edge checks performed by _candidate_options.
                anchored = _candidate_fits_skeleton_region(
                    code, rectangle, placed, context.structural_skeleton
                )
            elif code == "sorting_packaging_room" and candidate_policy_phase == STRUCTURED_PHASE:
                anchored = True
            elif code == "raw_fruit_buffer" and candidate_policy_phase != STRUCTURED_PHASE:
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
            placed[code] = rectangle
            yield from visit(
                index + 1,
                structurally_generated
                and anchored
                and context.search_phase != GENERAL_FALLBACK_PHASE,
                main_process_skeleton,
            )
            placed.pop(code)
            if stats.node_budget_exhausted:
                return

    if context.search_phase == STRUCTURED_PHASE:
        # Admit each exact, preflight-passing skeleton to tail search as soon
        # as it is constructed. Draining the constructor first can consume the
        # shared budget collecting seeds while leaving no quantum for the
        # already-admissible seed's tail, regressing existing full-chain cases.
        discovery_context = context
        for seed_or_quantum in _construct_main_process_skeletons(discovery_context, stats):
            if isinstance(seed_or_quantum, _SearchQuantumYield):
                yield seed_or_quantum
                continue
            seed = seed_or_quantum
            context = _canonical_tail_search_context(discovery_context, seed)
            placed.update({row.zone_code: row for row in seed.zone_rectangles})
            if len(placed) != len(MAIN_PROCESS_ZONE_CODES):
                raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
            tail_node_limit = max(0, context.node_budget - stats.visited_nodes)
            tail_start_node = stats.visited_nodes
            complete_start_count = stats.complete_candidates
            lifecycle_row: dict[str, Any] = {
                "topology": seed.topology,
                "skeleton_hash": seed.main_process_skeleton_hash,
                "layout_family": seed.building_layout_family,
                "envelope_family": seed.building_envelope_family,
                "planned_envelope_bounds_mm": (
                    list(seed.planned_envelope_bounds_mm)
                    if seed.planned_envelope_bounds_mm is not None
                    else None
                ),
                "discovery_topology": seed.discovery_topology,
                "canonical_topology_owner": seed.canonical_topology_owner,
                "discovery_family": (seed.discovery_family or seed.family).to_dict(),
                "canonical_family": seed.family.to_dict(),
                "tail_search_started_by_topology": seed.discovery_topology,
                "construction_nodes": (stats.construction_nodes_by_skeleton or {}).get(
                    seed.main_process_skeleton_hash, 0
                ),
                "tail_nodes": 0,
                "tail_node_limit": tail_node_limit,
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "p2d_full_pass_count": 0,
                "search_status": "ACTIVE",
                "first_failure_stage": None,
                "first_failure_reason": None,
            }
            if stats.skeleton_tail_lifecycle is None:
                stats.skeleton_tail_lifecycle = []
            stats.skeleton_tail_lifecycle.append(lifecycle_row)
            for tail_event in visit(len(MAIN_PROCESS_ZONE_CODES), True, seed):
                complete_count_so_far = stats.complete_candidates - complete_start_count
                lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
                lifecycle_row["complete_candidate_count"] = complete_count_so_far
                lifecycle_row["p2d_reached"] = complete_count_so_far > 0
                if isinstance(tail_event, _SearchQuantumYield):
                    lifecycle_row["search_status"] = "QUANTUM_EXHAUSTED"
                    yield tail_event
                else:
                    yield tail_event
            complete_count = stats.complete_candidates - complete_start_count
            lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
            lifecycle_row["complete_candidate_count"] = complete_count
            lifecycle_row["p2d_reached"] = complete_count > 0
            lifecycle_row["search_status"] = (
                "SEARCH_EXHAUSTED" if not stats.node_budget_exhausted else "ACTIVE"
            )
            if complete_count == 0 and stats.node_budget_exhausted:
                lifecycle_row["first_failure_stage"] = "TAIL_SEARCH"
                lifecycle_row["first_failure_reason"] = "GLOBAL_PLACEMENT_NODE_BUDGET_EXHAUSTED"
            elif complete_count == 0:
                lifecycle_row["first_failure_stage"] = "TAIL_SEARCH"
                lifecycle_row["first_failure_reason"] = (
                    "TAIL_SEARCH_COMPLETED_WITHOUT_COMPLETE_P2C_CANDIDATE"
                )
            placed.clear()
            context = discovery_context
            if stats.node_budget_exhausted:
                return
        if stats.node_budget_exhausted:
            return
    elif context.search_phase == GENERAL_FALLBACK_PHASE:
        # Keep the pre-R2 skeleton constructor as a genuine independent
        # compatibility source, while retaining GENERAL_FALLBACK semantics
        # for its tail: canonical identity is rebound, but the new envelope
        # must not become an admission boundary for legacy layouts.
        discovery_context = context
        for seed_or_quantum in _construct_main_process_skeletons(discovery_context, stats):
            if isinstance(seed_or_quantum, _SearchQuantumYield):
                yield seed_or_quantum
                continue
            seed = seed_or_quantum
            context = _canonical_tail_search_context(discovery_context, seed)
            placed.update({row.zone_code: row for row in seed.zone_rectangles})
            if len(placed) != len(MAIN_PROCESS_ZONE_CODES):
                raise _error("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
            complete_start_count = stats.complete_candidates
            tail_start_node = stats.visited_nodes
            lifecycle_row = {
                "topology": seed.topology,
                "skeleton_hash": seed.main_process_skeleton_hash,
                "layout_family": seed.building_layout_family,
                "envelope_family": seed.building_envelope_family,
                "discovery_topology": seed.discovery_topology,
                "canonical_topology_owner": seed.canonical_topology_owner,
                "discovery_family": (seed.discovery_family or seed.family).to_dict(),
                "canonical_family": seed.family.to_dict(),
                "tail_search_started_by_topology": seed.discovery_topology,
                "construction_nodes": (stats.construction_nodes_by_skeleton or {}).get(
                    seed.main_process_skeleton_hash, 0
                ),
                "tail_nodes": 0,
                "tail_node_limit": max(0, context.node_budget - stats.visited_nodes),
                "complete_candidate_count": 0,
                "p2d_reached": False,
                "p2d_full_pass_count": 0,
                "search_status": "ACTIVE",
                "first_failure_stage": None,
                "first_failure_reason": None,
            }
            if stats.skeleton_tail_lifecycle is None:
                stats.skeleton_tail_lifecycle = []
            stats.skeleton_tail_lifecycle.append(lifecycle_row)
            for tail_event in visit(len(MAIN_PROCESS_ZONE_CODES), True, seed):
                lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
                lifecycle_row["complete_candidate_count"] = (
                    stats.complete_candidates - complete_start_count
                )
                lifecycle_row["p2d_reached"] = lifecycle_row["complete_candidate_count"] > 0
                if isinstance(tail_event, _SearchQuantumYield):
                    lifecycle_row["search_status"] = "QUANTUM_EXHAUSTED"
                yield tail_event
            lifecycle_row["tail_nodes"] = stats.visited_nodes - tail_start_node
            lifecycle_row["complete_candidate_count"] = (
                stats.complete_candidates - complete_start_count
            )
            lifecycle_row["p2d_reached"] = lifecycle_row["complete_candidate_count"] > 0
            lifecycle_row["search_status"] = (
                "ACTIVE" if stats.node_budget_exhausted else "SEARCH_EXHAUSTED"
            )
            if not lifecycle_row["p2d_reached"]:
                lifecycle_row["first_failure_stage"] = "TAIL_SEARCH"
                lifecycle_row["first_failure_reason"] = (
                    "GLOBAL_PLACEMENT_NODE_BUDGET_EXHAUSTED"
                    if stats.node_budget_exhausted
                    else "TAIL_SEARCH_COMPLETED_WITHOUT_COMPLETE_P2C_CANDIDATE"
                )
            placed.clear()
            context = discovery_context
            if stats.node_budget_exhausted:
                return
    # GENERAL_FALLBACK_PHASE is the independent whole-layout compatibility
    # room-level source. It uses the exact pre-R2 candidate ordering and any
    # remaining nodes after the legacy skeleton constructor above.
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
    content.pop("_main_process_skeleton", None)
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
    """Deterministic P2C stream with an optional resumable quantum interface.

    The same generator and its branch stack survive every ``advance_quantum``
    call. No prefix is replayed when a scheduler gives the lane another turn.
    """

    def __init__(self, context: _PlacementSearchContext) -> None:
        self._context = context
        self._stats = _PlacementSearchStats()
        self._started = False
        self._finished = False
        self._structural_flags: dict[str, bool] = {}
        self._candidate_skeleton_hashes: dict[str, str | None] = {}
        self._candidate_topologies: dict[str, str] = {}
        self._candidate_families: dict[str, StructuralCompositionFamilyV1] = {}
        self._candidate_discovery_topologies: dict[str, str] = {}
        self._iterator: Iterator[dict[str, Any] | _SearchQuantumYield] | None = None
        self._quantum_mode = False

    def _ensure_iterator(self) -> Iterator[dict[str, Any] | _SearchQuantumYield]:
        if self._iterator is None:
            self._iterator = _walk_complete_candidate_payloads(self._context, self._stats)
        return self._iterator

    def _materialize_payload(self, payload: Mapping[str, Any]) -> SitePlacementResultV1:
        structural_flag = payload.get("_structural_generation_flag") is True
        internal_skeleton = payload.get("_main_process_skeleton")
        candidate = _materialize_candidate_result(payload)
        candidate_hash = candidate.to_dict().get("canonical_candidate_hash")
        if isinstance(candidate_hash, str):
            self._structural_flags[candidate_hash] = structural_flag
            skeleton_hash = (
                internal_skeleton.get("main_process_skeleton_hash")
                if isinstance(internal_skeleton, Mapping)
                else None
            )
            self._candidate_skeleton_hashes[candidate_hash] = (
                skeleton_hash if isinstance(skeleton_hash, str) else None
            )
            topology = (
                internal_skeleton.get("topology")
                if isinstance(internal_skeleton, Mapping)
                else self._context.structural_topology
            )
            self._candidate_topologies[candidate_hash] = str(topology)
            family_body = (
                internal_skeleton.get("family") if isinstance(internal_skeleton, Mapping) else None
            )
            if isinstance(family_body, Mapping):
                family_name = family_body.get("family")
                axis = family_body.get("dominant_axis")
                direction = family_body.get("dominant_direction")
                reason = family_body.get("generation_reason")
                if all(isinstance(value, str) for value in (family_name, axis, direction, reason)):
                    self._candidate_families[candidate_hash] = StructuralCompositionFamilyV1(
                        str(family_name), str(axis), str(direction), str(reason)
                    )
            discovery_topology = (
                internal_skeleton.get("discovery_topology")
                if isinstance(internal_skeleton, Mapping)
                else None
            )
            if isinstance(discovery_topology, str):
                self._candidate_discovery_topologies[candidate_hash] = discovery_topology
        return candidate

    def iter_candidates(self) -> Iterator[SitePlacementResultV1]:
        if self._started or self._quantum_mode:
            raise RuntimeError("placement candidate enumeration is one-shot")
        self._started = True
        iterator = self._ensure_iterator()
        while True:
            try:
                item = next(iterator)
            except StopIteration:
                self._finished = True
                return
            if isinstance(item, _SearchQuantumYield):
                continue
            yield self._materialize_payload(item)

    def advance_quantum(self, node_limit: int) -> PlacementCandidateQuantumAdvanceV1:
        """Advance this persistent generator by at most one scheduler slice."""
        if self._finished:
            return PlacementCandidateQuantumAdvanceV1((), 0, "COMPLETED", None, True, True)
        if self._started and not self._quantum_mode:
            raise RuntimeError("candidate iterator already started without quantum scheduling")
        if node_limit <= 0:
            raise ValueError("node_limit must be positive")
        self._started = True
        self._quantum_mode = True
        share_numerator = (
            ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_NUMERATOR
            if self._context.structural_topology in {OFFSET_LINEAR_BAND, CENTRAL_PROCESS_HUB}
            else STRUCTURED_SKELETON_CONSTRUCTION_SHARE_NUMERATOR
        )
        share_denominator = (
            ALTERNATIVE_TOPOLOGY_CONSTRUCTION_SHARE_DENOMINATOR
            if self._context.structural_topology in {OFFSET_LINEAR_BAND, CENTRAL_PROCESS_HUB}
            else STRUCTURED_SKELETON_CONSTRUCTION_SHARE_DENOMINATOR
        )
        share_quantum_ceiling = max(
            1, self._context.node_budget * share_numerator // share_denominator
        )
        self._stats.quantum_node_limit = min(
            node_limit,
            CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET,
            CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET,
            share_quantum_ceiling,
        )
        self._stats.quantum_nodes_visited = 0
        start_nodes = self._stats.visited_nodes
        candidates: list[SitePlacementResultV1] = []
        iterator = self._ensure_iterator()
        while True:
            try:
                item = next(iterator)
            except StopIteration:
                self._finished = True
                self._stats.quantum_node_limit = None
                search_exhausted = self.search_tree_exhausted
                return PlacementCandidateQuantumAdvanceV1(
                    tuple(candidates),
                    self._stats.visited_nodes - start_nodes,
                    "SEARCH_EXHAUSTED" if search_exhausted else "COMPLETED",
                    dict(self._stats.current_work_item or {}),
                    search_exhausted,
                    True,
                )
            if isinstance(item, _SearchQuantumYield):
                work_item = dict(item.work_item or {})
                return PlacementCandidateQuantumAdvanceV1(
                    tuple(candidates),
                    self._stats.visited_nodes - start_nodes,
                    "QUANTUM_EXHAUSTED",
                    work_item,
                    False,
                    False,
                )
            candidates.append(self._materialize_payload(item))

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
        return len(self._stats.constructed_main_skeletons or {})

    @property
    def skeleton_generation_report(self) -> dict[str, Any]:
        return {
            "identity": "main-process-skeleton-construction@1.0.0",
            "topology": self._context.structural_topology,
            "constructed_candidate_count": len(self._stats.constructed_main_skeletons or {}),
            "candidates": [
                candidate.to_evaluation_dict()
                for candidate in sorted(
                    (self._stats.constructed_main_skeletons or {}).values(),
                    key=lambda row: row.main_process_skeleton_hash,
                )
            ],
            "rejection_reason_counts": dict(
                sorted((self._stats.rejection_reason_counts or {}).items())
            ),
            "construction_attempts": list(self._stats.skeleton_construction_attempts or []),
            "root_preflight_mode": "EXACT_NECESSARY_PREDICATE_OR_ORDERING_ONLY",
            "heuristic_root_pruning": False,
            "root_preflight_ordering": list(self._stats.root_preflight_rows or []),
            "tail_slot_preflight_rows": list(self._stats.tail_slot_preflight_rows or []),
            "skeleton_tail_lifecycle": list(self._stats.skeleton_tail_lifecycle or []),
            "tail_search_zone_facts": {
                skeleton_hash: {
                    zone_code: dict(zone_facts)
                    for zone_code, zone_facts in sorted(zone_rows.items())
                }
                for skeleton_hash, zone_rows in sorted(
                    (self._stats.tail_zone_search_facts or {}).items()
                )
            },
            "node_budget_exhausted": self._stats.node_budget_exhausted,
            "construction_search_truncated": self._stats.skeleton_search_truncated,
            "normal_stop_reason": self._stats.normal_stop_reason,
            "construction_node_count": self._stats.construction_node_count,
            "tail_node_count": sum((self._stats.tail_nodes_by_skeleton or {}).values()),
            "continuation_work_item": dict(self._stats.current_work_item or {}),
            "_r6_topology_ownership_duplicates": list(
                self._stats.topology_ownership_duplicates or []
            ),
            "_r7_geometry_evaluation_admissions": list(
                self._stats.geometry_evaluation_admissions or []
            ),
            "_r6_offset_transition_trace": list(self._stats.offset_transition_trace or []),
            "_r6_constructive_divergence_attempts": list(
                self._stats.constructive_divergence_attempts or []
            ),
            "_r6_topology_classification_failures": list(
                self._stats.topology_classification_failures or []
            ),
            "_r6_cross_topology_duplicate_count": self._stats.cross_topology_duplicate_count,
        }

    @property
    def distinct_structural_core_root_count(self) -> int:
        return len(self._stats.structured_core_root_completions or {})

    @property
    def main_skeleton_truck_preflight_rows(self) -> list[dict[str, Any]]:
        """Internal selector diagnostics, kept out of Tool 7 serialization."""
        return list(self._stats.main_skeleton_truck_preflight_rows or [])

    @property
    def visited_node_count(self) -> int:
        return self._stats.visited_nodes

    @property
    def search_tree_exhausted(self) -> bool:
        return (
            self.completed
            and not self._stats.node_budget_exhausted
            and not self._stats.skeleton_search_truncated
            and self._stats.normal_stop_reason is None
        )

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

    @property
    def structural_topology(self) -> str:
        return self._context.structural_topology

    def structurally_generated(self, candidate_hash: str) -> bool:
        """Report whether every assigned zone used a group/band anchor."""
        return self._structural_flags.get(candidate_hash, False)

    def candidate_main_process_skeleton_hash(self, candidate_hash: str) -> str | None:
        return self._candidate_skeleton_hashes.get(candidate_hash)

    def candidate_topology(self, candidate_hash: str) -> str | None:
        return self._candidate_topologies.get(candidate_hash)

    def candidate_structural_family(
        self, candidate_hash: str
    ) -> StructuralCompositionFamilyV1 | None:
        return self._candidate_families.get(candidate_hash)

    def candidate_discovery_topology(self, candidate_hash: str) -> str | None:
        return self._candidate_discovery_topologies.get(candidate_hash)


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
    truck_maneuver_binding: Any = None,
    truck_node_budget: int = 20_000,
    truck_maneuver_validator: Callable[..., Mapping[str, Any]] | None = None,
    complete_candidate_limit: int | None = None,
    structural_family: StructuralCompositionFamilyV1 | None = None,
    structural_topology: str | None = None,
    search_phase: str = LEGACY_COMPAT_PHASE,
    direct_synthesis_enabled: bool = True,
    global_main_process_geometry_registry: dict[str, dict[str, Any]] | None = None,
    global_cross_topology_duplicate_trace: list[dict[str, Any]] | None = None,
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
            truck_maneuver_binding=truck_maneuver_binding,
            truck_node_budget=truck_node_budget,
            truck_maneuver_validator=truck_maneuver_validator,
            complete_candidate_limit=complete_candidate_limit,
            structural_family=structural_family,
            structural_topology=structural_topology,
            search_phase=search_phase,
            direct_synthesis_enabled=direct_synthesis_enabled,
            global_main_process_geometry_registry=global_main_process_geometry_registry,
            global_cross_topology_duplicate_trace=global_cross_topology_duplicate_trace,
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
        if isinstance(payload, _SearchQuantumYield):
            continue
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
