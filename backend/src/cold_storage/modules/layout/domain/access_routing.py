"""Exact, deterministic access and truck-route predicates for V2.2 P2D.

The P2D domain consumes rectangles and project-supplied maneuver templates that
were already bound by earlier stages.  It does not calculate zone areas, choose
placement candidates, invent access dimensions, or run a vehicle kinematics
solver.  Every geometry predicate uses integer millimetres after the public
boundary, so no floating-point epsilon is needed.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from itertools import permutations
from typing import Any

from cold_storage.modules.layout.domain.access_authority import (
    COLD_ROOM,
    AccessClassV1,
    AccessRequirementV1,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.access_predicates import (
    _evaluate_bound_requirement,
    evaluate_personnel_truck_policy,
)
from cold_storage.modules.layout.domain.building_footprint import (
    derive_building_footprint as derive_building_footprint,
)
from cold_storage.modules.layout.domain.dimensioning import (
    GRID,
    LayoutAuthorityError,
    canonical_hash,
)
from cold_storage.modules.layout.domain.site_geometry import (
    MILLIMETRES_PER_METRE,
    PlacedRectangleV1,
    PolygonMM,
    SegmentMM,
    _polygon_edges,
    _segments_intersect_closed,
    normalize_polygon,
    point_in_polygon,
    polygon_contains_polygon,
    polygon_to_dict,
    segments_share_positive_length,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_REVERSE,
    SUPPORTED_MANEUVER_CLASSES,
    BoundTruckManeuverProjectInputV1,
    transform_maneuver_template,
)

IDENTITY = "site-access-routing-and-validation@1.0.0"
RESULT_IDENTITY = "site_validated_layout@1.0.0"
SCHEMA_VERSION = "1.0.0"
ROUTE_SEARCH_PROFILE_IDENTITY = "deterministic-rectilinear-access-routing@1.0.0"
TRUCK_SEARCH_PROFILE_IDENTITY = "truck-maneuver-chain-search@1.0.0"
GRID_M = GRID
DEFAULT_ROUTE_NODE_BUDGET = 20_000
DEFAULT_TRUCK_NODE_BUDGET = 20_000
TRUCK_REPRESENTATION = "OPTION_C_APPROVED_MANEUVER_TEMPLATES"
INCIDENT_ZONE_INTERIOR_TRANSIT_ALLOWED = False
PORTAL_ONLY_ZONE_BOUNDARY_TRANSIT = True
CROSSING_NECESSITY_INFERRED_FROM_GEOMETRY = False
type _RouteSearchStateV1 = tuple[tuple[int, int], str, tuple[int, int] | None]


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _mm(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("INVALID_ROUTE_GEOMETRY", field=field)
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        raise _error("INVALID_ROUTE_GEOMETRY", field=field) from None
    if not number.is_finite():
        raise _error("INVALID_ROUTE_GEOMETRY", field=field)
    with localcontext(Context(prec=80)):
        scaled = number * MILLIMETRES_PER_METRE
        if scaled != scaled.to_integral_value():
            raise _error("INVALID_ROUTE_GRID_VALUE", field=field, grid_m=str(GRID_M))
    return int(scaled)


def _metres(value_mm: int) -> Decimal:
    with localcontext(Context(prec=80)):
        return Decimal(value_mm) / MILLIMETRES_PER_METRE


def _point(point: tuple[int, int]) -> dict[str, Decimal]:
    return {"x": _metres(point[0]), "y": _metres(point[1])}


def _segment(segment: SegmentMM) -> dict[str, Any]:
    return {"start": _point(segment[0]), "end": _point(segment[1])}


def _point_from_mapping(value: object, *, field: str) -> tuple[int, int]:
    if not isinstance(value, Mapping) or set(value) != {"x", "y"}:
        raise _error("INVALID_ROUTE_GEOMETRY", field=field)
    return (_mm(value["x"], field=f"{field}.x"), _mm(value["y"], field=f"{field}.y"))


def _segment_from_mapping(value: object, *, field: str) -> SegmentMM:
    if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
        raise _error("INVALID_ROUTE_GEOMETRY", field=field)
    start = _point_from_mapping(value["start"], field=f"{field}.start")
    end = _point_from_mapping(value["end"], field=f"{field}.end")
    if start == end:
        raise _error("INVALID_ROUTE_GEOMETRY", field=field)
    return (start, end) if start <= end else (end, start)


def _cross(a: tuple[int, int], b: tuple[int, int], c: tuple[int, int]) -> int:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> bool:
    return (
        _cross(start, end, point) == 0
        and min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
        and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
    )


def _strict_point_in_polygon(point: tuple[int, int], polygon: PolygonMM) -> bool:
    if any(_on_segment(point, start, end) for start, end in _polygon_edges(polygon)):
        return False
    return point_in_polygon(point, polygon)


def _proper_segment_cross(first: SegmentMM, second: SegmentMM) -> bool:
    first_a = _cross(first[0], first[1], second[0])
    first_b = _cross(first[0], first[1], second[1])
    second_a = _cross(second[0], second[1], first[0])
    second_b = _cross(second[0], second[1], first[1])
    return ((first_a > 0 > first_b) or (first_a < 0 < first_b)) and (
        (second_a > 0 > second_b) or (second_a < 0 < second_b)
    )


def _polygon_interiors_overlap(first: PolygonMM, second: PolygonMM) -> bool:
    """Return true for positive-area overlap, but permit boundary contact."""
    if any(
        _proper_segment_cross(first_edge, second_edge)
        for first_edge in _polygon_edges(first)
        for second_edge in _polygon_edges(second)
    ):
        return True
    if any(_strict_point_in_polygon(point, second) for point in first):
        return True
    return any(_strict_point_in_polygon(point, first) for point in second)


def _polygon_intersects_closed(first: PolygonMM, second: PolygonMM) -> bool:
    if any(
        _segments_intersect_closed(a, b, c, d)
        for a, b in _polygon_edges(first)
        for c, d in _polygon_edges(second)
    ):
        return True
    return point_in_polygon(first[0], second) or point_in_polygon(second[0], first)


def _segment_length_mm(segment: SegmentMM) -> int:
    return abs(segment[1][0] - segment[0][0]) + abs(segment[1][1] - segment[0][1])


def _edge_segments(
    rectangle: PlacedRectangleV1,
) -> tuple[tuple[str, str, SegmentMM], ...]:
    left, bottom, right, top = rectangle.bounds_mm
    horizontal_class = "LONG_EDGE" if right - left >= top - bottom else "SHORT_EDGE"
    vertical_class = "SHORT_EDGE" if horizontal_class == "LONG_EDGE" else "LONG_EDGE"
    return (
        ("BOTTOM", horizontal_class, ((left, bottom), (right, bottom))),
        ("LEFT", vertical_class, ((left, bottom), (left, top))),
        ("RIGHT", vertical_class, ((right, bottom), (right, top))),
        ("TOP", horizontal_class, ((left, top), (right, top))),
    )


def _edge_class(value: object) -> str | None:
    if value == "SHORT_EDGE_EXIT_SIDE":
        return "SHORT_EDGE"
    if value == "LONG_EDGE_LOADING_FACE":
        return "LONG_EDGE"
    if value == "LONG_EDGE":
        return "LONG_EDGE"
    if value == "SHORT_EDGE":
        return "SHORT_EDGE"
    return None


def _shared_edge_segment(first: PlacedRectangleV1, second: PlacedRectangleV1) -> SegmentMM | None:
    left_a, bottom_a, right_a, top_a = first.bounds_mm
    left_b, bottom_b, right_b, top_b = second.bounds_mm
    if right_a == left_b or right_b == left_a:
        x = right_a if right_a == left_b else right_b
        low = max(bottom_a, bottom_b)
        high = min(top_a, top_b)
        if high > low:
            return ((x, low), (x, high))
    if top_a == bottom_b or top_b == bottom_a:
        y = top_a if top_a == bottom_b else top_b
        low = max(left_a, left_b)
        high = min(right_a, right_b)
        if high > low:
            return ((low, y), (high, y))
    return None


def _edge_match_for_shared(
    first: PlacedRectangleV1, second: PlacedRectangleV1, shared: SegmentMM
) -> tuple[str | None, str | None]:
    first_class: str | None = None
    second_class: str | None = None
    for _, edge_class, edge in _edge_segments(first):
        if segments_share_positive_length(edge[0], edge[1], shared[0], shared[1]):
            first_class = edge_class
    for _, edge_class, edge in _edge_segments(second):
        if segments_share_positive_length(edge[0], edge[1], shared[0], shared[1]):
            second_class = edge_class
    return first_class, second_class


def _segment_with_width(edge: SegmentMM, width_mm: int, offset_mm: int) -> SegmentMM:
    if edge[0][0] == edge[1][0]:
        x = edge[0][0]
        low, high = sorted((edge[0][1], edge[1][1]))
        start = low + offset_mm
        return ((x, start), (x, start + width_mm))
    y = edge[0][1]
    low, high = sorted((edge[0][0], edge[1][0]))
    start = low + offset_mm
    return ((start, y), (start + width_mm, y))


def _portal_candidates(
    edge: SegmentMM, *, edge_class: str, clear_width_mm: int
) -> tuple[dict[str, Any], ...]:
    length = _segment_length_mm(edge)
    if length < clear_width_mm:
        return ()
    available = length - clear_width_mm
    offsets = sorted(
        {available // 2, 0, available},
        key=lambda offset: (abs(2 * offset - available), offset),
    )
    return tuple(
        {
            "edge_class": edge_class,
            "segment_mm": _segment_with_width(edge, clear_width_mm, offset),
            "clear_width_m": _metres(clear_width_mm),
        }
        for offset in offsets
    )


def _portal_record(
    requirement: Mapping[str, Any], access_ref: str, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "identity": f"portal:{requirement['identity']}:{access_ref}@1.0.0",
        "access_ref": access_ref,
        "edge_class": candidate["edge_class"],
        "segment": _segment(candidate["segment_mm"]),
        "clear_width_m": candidate["clear_width_m"],
        "status": "VALID",
    }


def _portal_center(segment: SegmentMM) -> tuple[int, int]:
    return (
        (segment[0][0] + segment[1][0]) // 2,
        (segment[0][1] + segment[1][1]) // 2,
    )


def _boundary_interior_point(
    point: tuple[int, int], edge: SegmentMM, boundary: PolygonMM, half_width_mm: int
) -> tuple[int, int]:
    """Move an entrance portal center exactly one half envelope inward."""
    dx = edge[1][0] - edge[0][0]
    candidates: tuple[tuple[int, int], ...]
    if dx:
        candidates = ((point[0], point[1] + half_width_mm), (point[0], point[1] - half_width_mm))
    else:
        candidates = ((point[0] + half_width_mm, point[1]), (point[0] - half_width_mm, point[1]))
    for candidate in candidates:
        if point_in_polygon(candidate, boundary) or any(
            _on_segment(candidate, start, end) for start, end in _polygon_edges(boundary)
        ):
            return candidate
    return point


def _strip_rectangle(
    start: tuple[int, int], end: tuple[int, int], width_mm: int
) -> PlacedRectangleV1:
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        return PlacedRectangleV1(
            "__corridor__",
            _metres(start[0] - width_mm // 2),
            _metres(low),
            _metres(width_mm),
            _metres(high - low),
        )
    low, high = sorted((start[0], end[0]))
    return PlacedRectangleV1(
        "__corridor__",
        _metres(low),
        _metres(start[1] - width_mm // 2),
        _metres(high - low),
        _metres(width_mm),
    )


def _corner_rectangle(point: tuple[int, int], width_mm: int) -> PlacedRectangleV1:
    half = width_mm // 2
    return PlacedRectangleV1(
        "__corridor__",
        _metres(point[0] - half),
        _metres(point[1] - half),
        _metres(width_mm),
        _metres(width_mm),
    )


def _path_envelopes(
    path: Sequence[tuple[int, int]], width_mm: int
) -> tuple[PlacedRectangleV1, ...]:
    envelopes: list[PlacedRectangleV1] = []
    for start, end in zip(path, path[1:], strict=False):
        if start == end:
            continue
        if start[0] != end[0] and start[1] != end[1]:
            raise _error("INVALID_RECTILINEAR_ROUTE")
        envelopes.append(_strip_rectangle(start, end, width_mm))
    for point in path[1:-1]:
        envelopes.append(_corner_rectangle(point, width_mm))
    return tuple(envelopes)


def _path_length_mm(path: Sequence[tuple[int, int]]) -> int:
    return sum(
        abs(end[0] - start[0]) + abs(end[1] - start[1])
        for start, end in zip(path, path[1:], strict=False)
    )


def _turn_count(path: Sequence[tuple[int, int]]) -> int:
    directions: list[tuple[int, int]] = []
    for start, end in zip(path, path[1:], strict=False):
        if start[0] != end[0]:
            direction = (1 if end[0] > start[0] else -1, 0)
        else:
            direction = (0, 1 if end[1] > start[1] else -1)
        if direction != directions[-1] if directions else True:
            directions.append(direction)
    return max(0, len(directions) - 1)


def _compact_path(path: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    compact: list[tuple[int, int]] = []
    for point in path:
        if compact and point == compact[-1]:
            continue
        if len(compact) >= 2:
            previous, last = compact[-2], compact[-1]
            if (last[0] - previous[0]) * (point[1] - last[1]) == (last[1] - previous[1]) * (
                point[0] - last[0]
            ):
                compact[-1] = point
                continue
        compact.append(point)
    return tuple(compact)


def _segment_open_interval_overlaps_polygon_interior(
    segment: SegmentMM, polygon: PolygonMM
) -> bool:
    """Return whether a rectilinear segment spends positive length inside a polygon.

    The endpoints are not treated as transit.  This makes exact boundary contact
    at a selected portal legal while rejecting a segment that enters an incident
    room before it reaches, or after it leaves, that portal.  All coordinates are
    integer millimetres; the strict ``>`` comparisons are intentional and do not
    use a floating-point epsilon.
    """
    start, end = segment
    if start == end:
        return False
    left = min(point[0] for point in polygon)
    right = max(point[0] for point in polygon)
    bottom = min(point[1] for point in polygon)
    top = max(point[1] for point in polygon)
    if start[1] == end[1]:
        if not bottom < start[1] < top:
            return False
        segment_left, segment_right = sorted((start[0], end[0]))
        return min(segment_right, right) > max(segment_left, left)
    if start[0] == end[0]:
        if not left < start[0] < right:
            return False
        segment_bottom, segment_top = sorted((start[1], end[1]))
        return min(segment_top, top) > max(segment_bottom, bottom)
    raise _error("INVALID_RECTILINEAR_ROUTE")


def _unit_step(start: tuple[int, int], end: tuple[int, int]) -> tuple[int, int]:
    """Return the first one-millimetre grid point after ``start`` toward ``end``."""
    return (
        start[0] + (1 if end[0] > start[0] else -1 if end[0] < start[0] else 0),
        start[1] + (1 if end[1] > start[1] else -1 if end[1] < start[1] else 0),
    )


def _unit_step_before(start: tuple[int, int], end: tuple[int, int]) -> tuple[int, int]:
    """Return the last one-millimetre grid point before ``end`` from ``start``."""
    return _unit_step(end, start)


def _route_is_safe(
    path: Sequence[tuple[int, int]],
    *,
    width_mm: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
    incident_refs: frozenset[str],
) -> tuple[bool, str | None, tuple[PlacedRectangleV1, ...]]:
    if len(path) < 2:
        return False, "ROUTE_SEARCH_EXHAUSTED", ()
    envelopes = _path_envelopes(path, width_mm)
    first_start, first_end = path[0], path[1]
    last_start, last_end = path[-2], path[-1]
    if any(
        code in incident_refs
        and point_in_polygon(_unit_step(first_start, first_end), rectangle.polygon_mm)
        for code, rectangle in zones.items()
    ) or any(
        code in incident_refs
        and point_in_polygon(_unit_step_before(last_start, last_end), rectangle.polygon_mm)
        for code, rectangle in zones.items()
    ):
        return False, "CORRIDOR_INCIDENT_ZONE_CROSSING", envelopes
    for envelope in envelopes:
        if not polygon_contains_polygon(boundary, envelope.polygon_mm):
            return False, "CORRIDOR_OUTSIDE_BUILDABLE_BOUNDARY", envelopes
        if any(_polygon_intersects_closed(envelope.polygon_mm, obstacle) for obstacle in obstacles):
            return False, "CORRIDOR_OBSTACLE_INTERSECTION", envelopes
        if any(
            code not in incident_refs
            and _polygon_interiors_overlap(envelope.polygon_mm, rectangle.polygon_mm)
            for code, rectangle in zones.items()
        ):
            return False, "CORRIDOR_UNRELATED_ZONE_INTERSECTION", envelopes
        if any(
            code in incident_refs
            and _polygon_interiors_overlap(envelope.polygon_mm, rectangle.polygon_mm)
            for code, rectangle in zones.items()
        ):
            return False, "CORRIDOR_INCIDENT_ZONE_CROSSING", envelopes
    for start, end in zip(path, path[1:], strict=False):
        if any(
            code in incident_refs
            and _segment_open_interval_overlaps_polygon_interior((start, end), rectangle.polygon_mm)
            for code, rectangle in zones.items()
        ):
            return False, "CORRIDOR_INCIDENT_ZONE_CROSSING", envelopes
    return True, None, envelopes


def _candidate_paths(
    start: tuple[int, int], end: tuple[int, int], *, straight_only: bool
) -> tuple[tuple[tuple[int, int], ...], ...]:
    if start == end:
        return ()
    paths: list[tuple[tuple[int, int], ...]] = []
    if start[0] == end[0] or start[1] == end[1]:
        paths.append((start, end))
    if not straight_only and start[0] != end[0] and start[1] != end[1]:
        paths.extend(((start, (end[0], start[1]), end), (start, (start[0], end[1]), end)))
    return tuple(paths)


@dataclass(frozen=True)
class RouteSkeletonEndpointV1:
    """One reached event node and its safe path from the construction source."""

    endpoint: tuple[int, int]
    path: tuple[tuple[int, int], ...]
    envelopes: tuple[PlacedRectangleV1, ...]


@dataclass(frozen=True)
class RouteSkeletonSearchResultV1:
    """Geometry-only result from the shared finite orthogonal route search.

    ``route_access_requirement`` remains the authority for portal/profile
    admission.  This result exposes search provenance so construction callers
    can distinguish a bounded search from an exhausted event graph.
    """

    path: tuple[tuple[int, int], ...] | None
    reason: str
    envelopes: tuple[PlacedRectangleV1, ...]
    nodes_visited: int
    node_budget_exhausted: bool
    graph_exhausted: bool
    search_source: str
    endpoint_skeletons: tuple[RouteSkeletonEndpointV1, ...] = ()


def _route_grid_search(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    width_mm: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
    incident_refs: frozenset[str],
    node_budget: int,
    additional_keepouts: Sequence[PolygonMM] = (),
    enumerate_endpoints: bool = False,
    endpoint_limit: int = 0,
    construction_search: bool = False,
    required_start_direction: tuple[int, int] | None = None,
    required_arrival_direction: tuple[int, int] | None = None,
) -> RouteSkeletonSearchResultV1:
    """Search the router's finite visibility graph in stable coordinate order."""
    half = width_mm // 2
    route_obstacles = (*obstacles, *additional_keepouts)
    x_values = {start[0], end[0]}
    y_values = {start[1], end[1]}
    for point in boundary:
        x_values.add(point[0])
        y_values.add(point[1])
    for rectangle in zones.values():
        left, bottom, right, top = rectangle.bounds_mm
        x_values.update((left - half, left, right, right + half))
        y_values.update((bottom - half, bottom, top, top + half))
    # Keep the production authority graph's event set byte-for-byte equivalent
    # to its pre-extraction form. Construction hints may add one exact-grid
    # clearance event around closed keepouts, but that must not alter the
    # final route authority's candidate ordering or result.
    legal_grid_step_mm = int(GRID * MILLIMETRES_PER_METRE)
    authority_semantics = not enumerate_endpoints and not construction_search
    obstacle_clearance_offsets = (
        (half,)
        if authority_semantics
        else (
            half,
            half + legal_grid_step_mm,
        )
    )
    for obstacle in obstacles:
        for x, y in obstacle:
            x_values.add(x)
            y_values.add(y)
            x_values.update(
                value for offset in obstacle_clearance_offsets for value in (x - offset, x + offset)
            )
            y_values.update(
                value for offset in obstacle_clearance_offsets for value in (y - offset, y + offset)
            )
    if additional_keepouts:
        clearance_offsets = (half, half + legal_grid_step_mm)
        for keepout in additional_keepouts:
            for x, y in keepout:
                x_values.add(x)
                y_values.add(y)
                x_values.update(
                    value for offset in clearance_offsets for value in (x - offset, x + offset)
                )
                y_values.update(
                    value for offset in clearance_offsets for value in (y - offset, y + offset)
                )
    xs = tuple(sorted(x_values))
    ys = tuple(sorted(y_values))
    x_indices = {coordinate: index for index, coordinate in enumerate(xs)}
    y_indices = {coordinate: index for index, coordinate in enumerate(ys)}
    nodes = {
        (x, y)
        for x in xs
        for y in ys
        if point_in_polygon((x, y), boundary)
        or any(_on_segment((x, y), a, b) for a, b in _polygon_edges(boundary))
    }
    nodes.update((start, end))

    def neighbors(node: tuple[int, int]) -> Iterable[tuple[int, int]]:
        x, y = node
        x_index = x_indices[x]
        y_index = y_indices[y]
        candidates: set[tuple[int, int]] = set()
        if x_index:
            candidates.add((xs[x_index - 1], y))
        if x_index + 1 < len(xs):
            candidates.add((xs[x_index + 1], y))
        if y_index:
            candidates.add((x, ys[y_index - 1]))
        if y_index + 1 < len(ys):
            candidates.add((x, ys[y_index + 1]))
        return tuple(sorted(candidate for candidate in candidates if candidate in nodes))

    visited = 0
    # The final authority retains its original point-only BFS semantics.
    # Construction endpoint enumeration tracks incoming axis so alternate
    # safe turn states at the same geometric event are not collapsed.
    if authority_semantics:
        queue_points: deque[tuple[int, int]] = deque([start])
        point_parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        while queue_points:
            current = queue_points.popleft()
            visited += 1
            if visited > node_budget:
                return RouteSkeletonSearchResultV1(
                    None,
                    "ROUTE_SEARCH_EXHAUSTED",
                    (),
                    visited,
                    True,
                    False,
                    "VISIBILITY_EVENT_GRAPH",
                )
            if current == end:
                raw_path: list[tuple[int, int]] = []
                cursor: tuple[int, int] | None = current
                while cursor is not None:
                    raw_path.append(cursor)
                    cursor = point_parents[cursor]
                path = _compact_path(tuple(reversed(raw_path)))
                safe, _reason, envelopes = _route_is_safe(
                    path,
                    width_mm=width_mm,
                    boundary=boundary,
                    obstacles=obstacles,
                    zones=zones,
                    incident_refs=incident_refs,
                )
                if safe:
                    return RouteSkeletonSearchResultV1(
                        path,
                        "",
                        envelopes,
                        visited,
                        False,
                        False,
                        "VISIBILITY_EVENT_GRAPH",
                    )
            for candidate in neighbors(current):
                if candidate in point_parents:
                    continue
                safe, _, _ = _route_is_safe(
                    (current, candidate),
                    width_mm=width_mm,
                    boundary=boundary,
                    obstacles=obstacles,
                    zones=zones,
                    incident_refs=incident_refs,
                )
                if safe:
                    point_parents[candidate] = current
                    queue_points.append(candidate)
        return RouteSkeletonSearchResultV1(
            None,
            "ROUTE_SEARCH_EXHAUSTED",
            (),
            visited,
            False,
            True,
            "VISIBILITY_EVENT_GRAPH",
        )

    # A visibility node alone is not a sufficient construction search state:
    # corridor clearance at a turn depends on the incoming axis. Keep
    # horizontal and vertical arrivals distinct in endpoint-enumeration mode.
    # Construction target-state queries retain the signed incoming direction
    # as part of the state. Ordinary construction searches keep the previous
    # point+axis state shape, and final authority searches stay in the
    # point-only branch above.
    start_state = (start, "", None)
    queue: deque[_RouteSearchStateV1] = deque([start_state])
    parents: dict[_RouteSearchStateV1, _RouteSearchStateV1 | None] = {start_state: None}
    straight_run_starts: dict[_RouteSearchStateV1, tuple[int, int]] = {start_state: start}
    visited = 0
    reached_endpoints: list[RouteSkeletonEndpointV1] = []
    reached_endpoint_states: set[_RouteSearchStateV1] = set()
    wrong_direction_target_reached = False

    def path_to_state(state: _RouteSearchStateV1) -> tuple[tuple[int, int], ...]:
        raw_path: list[tuple[int, int]] = []
        cursor_state: _RouteSearchStateV1 | None = state
        while cursor_state is not None:
            raw_path.append(cursor_state[0])
            cursor_state = parents[cursor_state]
        return _compact_path(tuple(reversed(raw_path)))

    while queue:
        if visited >= node_budget:
            return RouteSkeletonSearchResultV1(
                None,
                "ROUTE_SEARCH_EXHAUSTED",
                (),
                visited,
                True,
                False,
                "VISIBILITY_EVENT_GRAPH_ENDPOINTS",
                tuple(reached_endpoints),
            )
        current_state = queue.popleft()
        current, incoming_axis, incoming_direction = current_state
        visited += 1
        if current == end and not enumerate_endpoints:
            if (
                required_arrival_direction is not None
                and incoming_direction != required_arrival_direction
            ):
                wrong_direction_target_reached = True
                continue
            path = path_to_state(current_state)
            safe, reason, envelopes = _route_is_safe(
                path,
                width_mm=width_mm,
                boundary=boundary,
                obstacles=route_obstacles,
                zones=zones,
                incident_refs=incident_refs,
            )
            if safe:
                return RouteSkeletonSearchResultV1(
                    path,
                    "",
                    envelopes,
                    visited,
                    False,
                    False,
                    "VISIBILITY_EVENT_GRAPH",
                )
            if reason not in {None, "ROUTE_SEARCH_EXHAUSTED"}:
                # Continue looking: another parent may avoid the obstacle.
                pass
        elif (
            enumerate_endpoints
            and current != start
            and current_state not in reached_endpoint_states
        ):
            path = path_to_state(current_state)
            safe, _reason, envelopes = _route_is_safe(
                path,
                width_mm=width_mm,
                boundary=boundary,
                obstacles=route_obstacles,
                zones=zones,
                incident_refs=incident_refs,
            )
            if safe:
                # Keep distinct arrivals at the same physical point. The
                # final segment direction determines which target portal can
                # legally use this event, so point-only deduplication can
                # discard the only portal-compatible construction route.
                reached_endpoint_states.add(current_state)
                reached_endpoints.append(RouteSkeletonEndpointV1(current, path, envelopes))
                if endpoint_limit > 0 and len(reached_endpoints) >= endpoint_limit:
                    return RouteSkeletonSearchResultV1(
                        None,
                        "",
                        (),
                        visited,
                        False,
                        False,
                        "VISIBILITY_EVENT_GRAPH_ENDPOINTS",
                        tuple(reached_endpoints),
                    )
        for candidate in neighbors(current):
            outgoing_axis = "H" if candidate[1] == current[1] else "V"
            direction = (
                1 if candidate[0] > current[0] else -1 if candidate[0] < current[0] else 0,
                1 if candidate[1] > current[1] else -1 if candidate[1] < current[1] else 0,
            )
            if (
                current == start
                and required_start_direction is not None
                and direction != required_start_direction
            ):
                continue
            state_direction = direction if required_arrival_direction is not None else None
            candidate_state: _RouteSearchStateV1 = (candidate, outgoing_axis, state_direction)
            if candidate_state in parents:
                continue
            edge_safe, _, _ = _route_is_safe(
                (current, candidate),
                width_mm=width_mm,
                boundary=boundary,
                obstacles=route_obstacles,
                zones=zones,
                incident_refs=incident_refs,
            )
            if not edge_safe:
                continue
            if incoming_axis and incoming_axis != outgoing_axis:
                previous_state = parents[current_state]
                previous = start if previous_state is None else previous_state[0]
                safe, _, _ = _route_is_safe(
                    (previous, current, candidate),
                    width_mm=width_mm,
                    boundary=boundary,
                    obstacles=route_obstacles,
                    zones=zones,
                    incident_refs=incident_refs,
                )
                next_run_start = current
            else:
                next_run_start = straight_run_starts[current_state]
                # Validate the whole newly extended straight run. Testing only
                # event-to-event edges can miss a zone contained exactly
                # between adjacent event coordinates.
                safe, _, _ = _route_is_safe(
                    (next_run_start, candidate),
                    width_mm=width_mm,
                    boundary=boundary,
                    obstacles=route_obstacles,
                    zones=zones,
                    incident_refs=incident_refs,
                )
            if safe:
                parents[candidate_state] = current_state
                straight_run_starts[candidate_state] = next_run_start
                queue.append(candidate_state)
    return RouteSkeletonSearchResultV1(
        None,
        "NO_DIRECTION_COMPATIBLE_PATH"
        if wrong_direction_target_reached
        else "ROUTE_SEARCH_EXHAUSTED",
        (),
        visited,
        False,
        True,
        "VISIBILITY_EVENT_GRAPH_ENDPOINTS" if enumerate_endpoints else "VISIBILITY_EVENT_GRAPH",
        tuple(reached_endpoints),
    )


def _find_route_skeleton_endpoints_v1(
    start: tuple[int, int],
    *,
    width_mm: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
    incident_refs: frozenset[str],
    node_budget: int,
    endpoint_limit: int,
    additional_keepouts: Sequence[PolygonMM] = (),
) -> RouteSkeletonSearchResultV1:
    """Enumerate safe event-node route skeletons from one source portal.

    The event coordinates and clearance checks are the exact same machinery as
    `_route_grid_search`; this variant gathers bounded reachable endpoints so a
    construction caller can derive a target rectangle from a route endpoint.
    """
    return _route_grid_search(
        start,
        start,
        width_mm=width_mm,
        boundary=boundary,
        obstacles=obstacles,
        zones=zones,
        incident_refs=incident_refs,
        node_budget=node_budget,
        additional_keepouts=additional_keepouts,
        enumerate_endpoints=True,
        endpoint_limit=endpoint_limit,
        construction_search=True,
    )


def _route_grid_path(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    width_mm: int,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
    incident_refs: frozenset[str],
    node_budget: int,
) -> tuple[tuple[tuple[int, int], ...] | None, str, tuple[PlacedRectangleV1, ...]]:
    """Backward-compatible tuple view of the shared visibility-graph search."""
    result = _route_grid_search(
        start,
        end,
        width_mm=width_mm,
        boundary=boundary,
        obstacles=obstacles,
        zones=zones,
        incident_refs=incident_refs,
        node_budget=node_budget,
    )
    return result.path, result.reason, result.envelopes


def _find_route_skeleton_v1(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    width_mm: int,
    straight_only: bool,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
    incident_refs: frozenset[str],
    node_budget: int,
    additional_keepouts: Sequence[PolygonMM] = (),
    required_start_direction: tuple[int, int] | None = None,
    required_arrival_direction: tuple[int, int] | None = None,
) -> RouteSkeletonSearchResultV1:
    """Find a route skeleton using the same geometry search as final P2D.

    Extra keepouts are a construction-only extension (for example reserved
    truck envelopes). The public access requirement evaluator calls this with
    no extra keepouts and still owns all final route/profile decisions.
    """
    route_obstacles = (*obstacles, *additional_keepouts)
    reasons: list[str] = []
    for path in _candidate_paths(start, end, straight_only=straight_only):
        if len(path) < 2:
            if required_start_direction is not None or required_arrival_direction is not None:
                continue
        else:
            first_direction = (
                0 if path[1][0] == path[0][0] else (1 if path[1][0] > path[0][0] else -1),
                0 if path[1][1] == path[0][1] else (1 if path[1][1] > path[0][1] else -1),
            )
            last_direction = (
                0 if path[-1][0] == path[-2][0] else (1 if path[-1][0] > path[-2][0] else -1),
                0 if path[-1][1] == path[-2][1] else (1 if path[-1][1] > path[-2][1] else -1),
            )
            if (
                required_start_direction is not None and first_direction != required_start_direction
            ) or (
                required_arrival_direction is not None
                and last_direction != required_arrival_direction
            ):
                continue
        safe, reason, envelopes = _route_is_safe(
            path,
            width_mm=width_mm,
            boundary=boundary,
            obstacles=route_obstacles,
            zones=zones,
            incident_refs=incident_refs,
        )
        if safe:
            return RouteSkeletonSearchResultV1(
                path, "", envelopes, 0, False, False, "PORTAL_LOCAL_CANDIDATE"
            )
        if reason is not None:
            reasons.append(reason)
    if straight_only:
        # Preserve the official validator's stable failure code for a frozen
        # straight-only relationship; no visibility-graph detour is allowed.
        return RouteSkeletonSearchResultV1(
            None,
            "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED",
            (),
            0,
            False,
            True,
            "STRAIGHT_ONLY_PROHIBITION",
        )
    result = _route_grid_search(
        start,
        end,
        width_mm=width_mm,
        boundary=boundary,
        obstacles=obstacles,
        zones=zones,
        incident_refs=incident_refs,
        node_budget=node_budget,
        additional_keepouts=additional_keepouts,
        construction_search=True,
        required_start_direction=required_start_direction,
        required_arrival_direction=required_arrival_direction,
    )
    if result.path is not None:
        return result
    return RouteSkeletonSearchResultV1(
        None,
        result.reason or (reasons[0] if reasons else "ROUTE_SEARCH_EXHAUSTED"),
        result.envelopes,
        result.nodes_visited,
        result.node_budget_exhausted,
        result.graph_exhausted,
        result.search_source,
    )


def _find_route(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    width_mm: int,
    straight_only: bool,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
    incident_refs: frozenset[str],
    node_budget: int,
) -> tuple[tuple[tuple[int, int], ...] | None, str, tuple[PlacedRectangleV1, ...]]:
    result = _find_route_skeleton_v1(
        start,
        end,
        width_mm=width_mm,
        straight_only=straight_only,
        boundary=boundary,
        obstacles=obstacles,
        zones=zones,
        incident_refs=incident_refs,
        node_budget=node_budget,
    )
    return result.path, result.reason, result.envelopes


def _requirement_object(requirement: Mapping[str, Any]) -> AccessRequirementV1:
    try:
        access_class = AccessClassV1(str(requirement["access_class"]))
        return AccessRequirementV1(
            identity=str(requirement["identity"]),
            from_ref=str(requirement["from_ref"]),
            to_ref=str(requirement["to_ref"]),
            flow_kind=str(requirement["flow_kind"]),
            access_class=access_class,
            profile_identity=str(requirement["profile_identity"]),
            portal_required=bool(requirement["portal_required"]),
            corridor_allowed=bool(requirement["corridor_allowed"]),
            direct_allowed=bool(requirement["direct_allowed"]),
            route_shape_constraint=str(requirement["route_shape_constraint"]),
            edge_orientation_requirement=(
                str(requirement["edge_orientation_requirement"])
                if requirement.get("edge_orientation_requirement") is not None
                else None
            ),
            cold_room_refs=tuple(str(ref) for ref in requirement.get("cold_room_refs", ())),
            cold_room_portal_profile_identity=(
                str(requirement["cold_room_portal_profile_identity"])
                if requirement.get("cold_room_portal_profile_identity") is not None
                else None
            ),
            source_authority=str(requirement.get("source_authority", "")),
        )
    except (KeyError, TypeError, ValueError, LayoutAuthorityError):
        raise _error("P1_ACCESS_REQUIREMENT_INVALID") from None


def _relation_for(
    requirement: Mapping[str, Any], relationships: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    identity = requirement.get("edge_orientation_requirement")
    return relationships.get(identity) if isinstance(identity, str) else None


def _edge_options(
    rectangle: PlacedRectangleV1 | None,
    *,
    required_class: str | None,
    clear_width_mm: int,
    boundary_segment: SegmentMM | None = None,
) -> tuple[dict[str, Any], ...]:
    if boundary_segment is not None:
        return _portal_candidates(
            boundary_segment,
            edge_class="BOUNDARY_ACCESS",
            clear_width_mm=clear_width_mm,
        )
    if rectangle is None:
        return ()
    options: list[dict[str, Any]] = []
    for _, edge_class, edge in _edge_segments(rectangle):
        if required_class is None or edge_class == required_class:
            options.extend(
                _portal_candidates(edge, edge_class=edge_class, clear_width_mm=clear_width_mm)
            )
    return tuple(
        sorted(
            options,
            key=lambda row: (
                row["edge_class"],
                row["segment_mm"][0],
                row["segment_mm"][1],
            ),
        )
    )


def _access_result_base(requirement: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "requirement_identity": requirement.get("identity"),
        "from_ref": requirement.get("from_ref"),
        "to_ref": requirement.get("to_ref"),
        "flow_kind": requirement.get("flow_kind"),
        "access_class": requirement.get("access_class"),
        "profile_identity": requirement.get("profile_identity"),
        "portal_required": requirement.get("portal_required"),
        "corridor_allowed": requirement.get("corridor_allowed"),
        "direct_allowed": requirement.get("direct_allowed"),
        "edge_orientation_requirement": requirement.get("edge_orientation_requirement"),
        "route_shape_constraint": requirement.get("route_shape_constraint"),
        "topology": None,
        "portal_from": None,
        "portal_to": None,
        "centerline": [],
        "clear_width_m": None,
        "corridor_envelope": [],
        "route_length_m": None,
        "turn_count": None,
        "route_shape": None,
        "edge_alignment_verified": False,
        "status": "BLOCKED",
        "codes": [],
        "requires_review": True,
    }


def _hashed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("canonical_hash", None)
    result["canonical_hash"] = canonical_hash(result)
    return result


def route_access_requirement(
    requirement: Mapping[str, Any],
    *,
    relationships: Mapping[str, Mapping[str, Any]],
    zones: Mapping[str, PlacedRectangleV1],
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    entrances: Mapping[str, SegmentMM],
    route_node_budget: int = DEFAULT_ROUTE_NODE_BUDGET,
) -> tuple[dict[str, Any], tuple[PolygonMM, ...]]:
    """Return one portal/corridor result and its corridor polygons."""
    result = _access_result_base(requirement)
    requirement_object = _requirement_object(requirement)
    profile = resolve_access_profile(requirement_object.profile_identity)
    portal_width_mm = _mm(profile.portal_clear_width_m, field="portal_clear_width_m")
    if requirement_object.cold_room_refs:
        portal_width_mm = max(
            portal_width_mm,
            _mm(
                resolve_access_profile(COLD_ROOM).portal_clear_width_m,
                field="cold_room_portal_clear_width_m",
            ),
        )
    corridor_width_mm = _mm(profile.corridor_clear_width_m, field="corridor_clear_width_m")
    relation = _relation_for(requirement, relationships)
    expected_from = _edge_class(relation.get("from_edge_class")) if relation else None
    expected_to = _edge_class(relation.get("to_edge_class")) if relation else None
    from_ref = requirement_object.from_ref
    to_ref = requirement_object.to_ref
    from_rectangle = zones.get(from_ref)
    to_rectangle = zones.get(to_ref)
    if from_ref != "main_entrance" and from_rectangle is None:
        result["codes"] = ["ACCESS_ENDPOINT_NOT_PLACED"]
        return _hashed(result), ()
    if to_rectangle is None:
        result["codes"] = ["ACCESS_ENDPOINT_NOT_PLACED"]
        return _hashed(result), ()

    if requirement_object.direct_allowed and from_rectangle and to_rectangle:
        shared = _shared_edge_segment(from_rectangle, to_rectangle)
        if shared is not None:
            actual_from, actual_to = _edge_match_for_shared(from_rectangle, to_rectangle, shared)
            aligned = (expected_from is None or actual_from == expected_from) and (
                expected_to is None or actual_to == expected_to
            )
            if aligned and _segment_length_mm(shared) >= portal_width_mm:
                portal = _portal_candidates(
                    shared,
                    edge_class=actual_from or "SHARED_EDGE",
                    clear_width_mm=portal_width_mm,
                )[0]
                observation = {
                    "topology": "DIRECT_SHARED_EDGE",
                    "profile_identity": requirement_object.profile_identity,
                    "transport_mode": profile.transport_mode,
                    "portal_clear_width_m": portal["clear_width_m"],
                    "edge_alignment_verified": True,
                    "route_shape": "STRAIGHT",
                    "turn_count": 0,
                }
                predicate = _evaluate_bound_requirement(requirement_object, observation)
                portal_center = _point(_portal_center(portal["segment_mm"]))
                result.update(
                    {
                        "topology": "DIRECT_SHARED_EDGE",
                        "portal_from": _portal_record(requirement, from_ref, portal),
                        "portal_to": _portal_record(requirement, to_ref, portal),
                        "centerline": [portal_center, portal_center],
                        "clear_width_m": portal["clear_width_m"],
                        "route_length_m": Decimal("0"),
                        "turn_count": 0,
                        "route_shape": "STRAIGHT",
                        "edge_alignment_verified": True,
                        "status": "PASS" if predicate["status"] == "PASS" else "FAIL",
                        "codes": list(predicate.get("codes", [])),
                    }
                )
                return _hashed(result), ()
            if not aligned:
                result["codes"] = ["EDGE_ORIENTATION_ALIGNMENT_REQUIRED"]
            elif _segment_length_mm(shared) < portal_width_mm:
                result["codes"] = ["PORTAL_CLEAR_WIDTH_INSUFFICIENT"]

    if not requirement_object.corridor_allowed:
        result["status"] = "FAIL"
        result["codes"] = result["codes"] or ["ACCESS_TOPOLOGY_PROHIBITED"]
        return _hashed(result), ()

    from_options = _edge_options(
        from_rectangle,
        required_class=expected_from,
        clear_width_mm=portal_width_mm,
        boundary_segment=entrances.get(from_ref),
    )
    to_options = _edge_options(
        to_rectangle,
        required_class=expected_to,
        clear_width_mm=portal_width_mm,
    )
    if not from_options or not to_options:
        result["status"] = "FAIL"
        result["codes"] = list(dict.fromkeys([*result["codes"], "PORTAL_CLEAR_WIDTH_INSUFFICIENT"]))
        return _hashed(result), ()

    straight_only = requirement_object.route_shape_constraint == "STRAIGHT_ONLY"
    route_failures: list[str] = []
    for from_candidate in from_options:
        for to_candidate in to_options:
            start = _portal_center(from_candidate["segment_mm"])
            end = _portal_center(to_candidate["segment_mm"])
            if from_ref in entrances:
                start = _boundary_interior_point(
                    start,
                    entrances[from_ref],
                    boundary,
                    corridor_width_mm // 2,
                )
            path, reason, envelopes = _find_route(
                start,
                end,
                width_mm=corridor_width_mm,
                straight_only=straight_only,
                boundary=boundary,
                obstacles=obstacles,
                zones=zones,
                incident_refs=frozenset((from_ref, to_ref)),
                node_budget=route_node_budget,
            )
            if path is None:
                route_failures.append(reason)
                continue
            aligned = (expected_from is None or from_candidate["edge_class"] == expected_from) and (
                expected_to is None or to_candidate["edge_class"] == expected_to
            )
            if not aligned:
                route_failures.append("EDGE_ORIENTATION_ALIGNMENT_REQUIRED")
                continue
            turn_count = _turn_count(path)
            route_shape = "STRAIGHT" if turn_count == 0 else "ORTHOGONAL"
            observation = {
                "topology": "CORRIDOR_MEDIATED",
                "profile_identity": requirement_object.profile_identity,
                "transport_mode": profile.transport_mode,
                "portal_clear_width_m": from_candidate["clear_width_m"],
                "corridor_clear_width_m": _metres(corridor_width_mm),
                "edge_alignment_verified": aligned,
                "route_shape": route_shape,
                "turn_count": turn_count,
            }
            predicate = _evaluate_bound_requirement(requirement_object, observation)
            if predicate["status"] != "PASS":
                route_failures.extend(str(code) for code in predicate.get("codes", []))
                continue
            result.update(
                {
                    "topology": "CORRIDOR_MEDIATED",
                    "portal_from": _portal_record(requirement, from_ref, from_candidate),
                    "portal_to": _portal_record(requirement, to_ref, to_candidate),
                    "centerline": [_point(point) for point in path],
                    "clear_width_m": _metres(corridor_width_mm),
                    "corridor_envelope": [
                        polygon_to_dict(envelope.polygon_mm) for envelope in envelopes
                    ],
                    "route_length_m": _metres(_path_length_mm(path)),
                    "turn_count": turn_count,
                    "route_shape": route_shape,
                    "edge_alignment_verified": aligned,
                    "status": "PASS",
                    "codes": [],
                }
            )
            return _hashed(result), tuple(envelope.polygon_mm for envelope in envelopes)

    result["codes"] = list(dict.fromkeys(route_failures or ["ROUTE_SEARCH_EXHAUSTED"]))
    result["status"] = (
        "FAIL" if any(code != "ROUTE_SEARCH_EXHAUSTED" for code in result["codes"]) else "BLOCKED"
    )
    return _hashed(result), ()


def _pose_mm(pose: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        _mm(pose["x"], field="pose.x"),
        _mm(pose["y"], field="pose.y"),
        int(pose["rotation_deg"]),
    )


def _pose_equal(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    return _pose_mm(first) == _pose_mm(second)


def _translation_for_entry(
    template: Any, desired_entry: tuple[int, int], rotation_deg: int
) -> dict[str, Decimal]:
    frame = template.reference_frame
    entry = _pose_mm(frame["entry_pose"])
    if rotation_deg == 0:
        rotated = entry[:2]
    elif rotation_deg == 90:
        rotated = (-entry[1], entry[0])
    elif rotation_deg == 180:
        rotated = (-entry[0], -entry[1])
    else:
        rotated = (entry[1], -entry[0])
    return {
        "x": _metres(desired_entry[0] - rotated[0]),
        "y": _metres(desired_entry[1] - rotated[1]),
    }


def _segment_lattice_points(segment: SegmentMM) -> tuple[tuple[int, int], ...]:
    start, end = segment
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        return tuple((start[0], value) for value in (low, (low + high) // 2, high))
    low, high = sorted((start[0], end[0]))
    return tuple((value, start[1]) for value in (low, (low + high) // 2, high))


def _transformed_maneuver_safe(
    transformed: Mapping[str, Any],
    *,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
) -> bool:
    envelope = normalize_polygon(
        transformed["envelope_geometry"],
        error_code="INVALID_TRANSFORMED_MANEUVER_ENVELOPE",
        allow_numeric_string=True,
    )
    if not polygon_contains_polygon(boundary, envelope):
        return False
    if any(_polygon_intersects_closed(envelope, obstacle) for obstacle in obstacles):
        return False
    return not any(
        _polygon_interiors_overlap(envelope, rectangle.polygon_mm) for rectangle in zones.values()
    )


def validate_truck_maneuver_chain(
    binding: BoundTruckManeuverProjectInputV1 | Mapping[str, Any] | None,
    *,
    truck_entrance: SegmentMM,
    shipping_loading_face: SegmentMM,
    boundary: PolygonMM,
    obstacles: Sequence[PolygonMM],
    zones: Mapping[str, PlacedRectangleV1],
    node_budget: int = DEFAULT_TRUCK_NODE_BUDGET,
) -> dict[str, Any]:
    """Search one finite, exact Option-C maneuver chain."""
    result: dict[str, Any] = {
        "representation": TRUCK_REPRESENTATION,
        "search_profile_identity": TRUCK_SEARCH_PROFILE_IDENTITY,
        "truck_entrance_segment": _segment(truck_entrance),
        "shipping_loading_face_segment": _segment(shipping_loading_face),
        "truck_route_validated": False,
        "status": "BLOCKED",
        "codes": [],
        "maneuver_chain": [],
        "truck_envelopes": [],
        "search_provenance": {
            "node_budget": node_budget,
            "visited_nodes": 0,
            "node_budget_exhausted": False,
            "search_tree_exhausted": False,
            "template_reuse_allowed": False,
        },
        "requires_review": True,
    }
    if binding is None:
        result["status"] = "BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"
        result["codes"] = ["BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"]
        return _hashed(result)
    try:
        bound = (
            BoundTruckManeuverProjectInputV1.from_mapping(binding.to_dict())
            if isinstance(binding, BoundTruckManeuverProjectInputV1)
            else BoundTruckManeuverProjectInputV1.from_mapping(binding)
        )
        project = bound.maneuver_project_input.require_complete()
    except (LayoutAuthorityError, TypeError, ValueError) as error:
        result["status"] = "BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"
        result["codes"] = [getattr(error, "code", "INVALID_TRUCK_MANEUVER_PROJECT_BINDING")]
        details = getattr(error, "details", None)
        if isinstance(details, Mapping):
            result["details"] = dict(details)
        return _hashed(result)

    templates = tuple(sorted(project.template_set.templates, key=lambda item: item.identity))
    by_class = {
        maneuver_class: tuple(
            template for template in templates if template.maneuver_class == maneuver_class
        )
        for maneuver_class in SUPPORTED_MANEUVER_CLASSES
    }
    required = tuple(
        maneuver_class
        for maneuver_class in SUPPORTED_MANEUVER_CLASSES
        if maneuver_class in project.requirement.required_maneuver_classes
    )
    if DOCK_REVERSE not in required:
        result["status"] = "BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"
        result["codes"] = ["TRUCK_MANEUVER_TEMPLATE_REQUIRED"]
        return _hashed(result)

    sequences = tuple(
        sequence for sequence in permutations(required) if sequence[-1] == DOCK_REVERSE
    )
    visited = 0
    found: list[tuple[dict[str, Any], ...]] = []
    budget_exhausted = False

    def recurse(
        sequence: tuple[str, ...],
        index: int,
        chain: tuple[dict[str, Any], ...],
        used: frozenset[str],
    ) -> bool:
        nonlocal visited, budget_exhausted
        if index == len(sequence):
            final_pose = chain[-1].get("final_dock_pose")
            if not isinstance(final_pose, Mapping):
                return False
            final_point = _pose_mm(final_pose)[:2]
            if not _on_segment(final_point, shipping_loading_face[0], shipping_loading_face[1]):
                return False
            found.append(chain)
            return True
        maneuver_class = sequence[index]
        for template in by_class.get(maneuver_class, ()):
            if template.identity in used:
                continue
            desired_entries: tuple[tuple[int, int], ...]
            rotations: tuple[int, ...]
            if index == 0:
                desired_entries = _segment_lattice_points(truck_entrance)
                rotations = (0, 90, 180, 270)
            else:
                previous_exit = chain[-1]["reference_frame"]["exit_pose"]
                previous = _pose_mm(previous_exit)
                desired_entries = (previous[:2],)
                rotations = (previous[2],)
            for desired_entry in desired_entries:
                for rotation in rotations:
                    visited += 1
                    if visited > node_budget:
                        budget_exhausted = True
                        return False
                    transformed = transform_maneuver_template(
                        template,
                        _translation_for_entry(template, desired_entry, rotation),
                        rotation,
                    )
                    frame = transformed["reference_frame"]
                    if index == 0 and not _on_segment(
                        _pose_mm(frame["entry_pose"])[:2],
                        truck_entrance[0],
                        truck_entrance[1],
                    ):
                        continue
                    if index > 0 and not _pose_equal(
                        chain[-1]["reference_frame"]["exit_pose"], frame["entry_pose"]
                    ):
                        continue
                    if not _transformed_maneuver_safe(
                        transformed,
                        boundary=boundary,
                        obstacles=obstacles,
                        zones=zones,
                    ):
                        continue
                    if index == len(sequence) - 1:
                        final_pose = transformed.get("final_dock_pose")
                        if not isinstance(final_pose, Mapping) or not _on_segment(
                            _pose_mm(final_pose)[:2],
                            shipping_loading_face[0],
                            shipping_loading_face[1],
                        ):
                            continue
                    if recurse(
                        sequence, index + 1, (*chain, transformed), used | {template.identity}
                    ):
                        return True
                    if budget_exhausted:
                        return False
        return False

    for sequence in sequences:
        if recurse(sequence, 0, (), frozenset()):
            break
        if budget_exhausted:
            break
    result["search_provenance"]["visited_nodes"] = visited
    result["search_provenance"]["node_budget_exhausted"] = budget_exhausted
    result["search_provenance"]["search_tree_exhausted"] = not budget_exhausted
    if not found:
        result["status"] = "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
        result["codes"] = ["TRUCK_MANEUVER_SEARCH_EXHAUSTED"]
        return _hashed(result)
    selected = found[0]
    result.update(
        {
            "project_id": bound.project_id,
            "binding_identity": bound.identity,
            "binding_hash": bound.canonical_result_hash,
            "required_maneuver_classes": list(required),
            "maneuver_chain": list(selected),
            "truck_envelopes": [row["envelope_geometry"] for row in selected],
            "status": "PASS",
            "truck_route_validated": True,
            "codes": [],
        }
    )
    return _hashed(result)


def evaluate_personnel_truck_interaction(
    personnel_corridors: Sequence[PolygonMM], truck_envelopes: Sequence[PolygonMM]
) -> dict[str, Any]:
    shared = any(
        _polygon_interiors_overlap(personnel, truck)
        for personnel in personnel_corridors
        for truck in truck_envelopes
    )
    crossing = not shared and any(
        _polygon_intersects_closed(personnel, truck)
        for personnel in personnel_corridors
        for truck in truck_envelopes
    )
    if crossing:
        return {
            "status": "REQUIRES_ENGINEERING_REVIEW",
            "shared_route": False,
            "crossing": True,
            "crossing_necessary": "UNDETERMINED",
            "requires_review": True,
            "codes": ["PERSONNEL_TRUCK_INTERACTION_REQUIRES_ENGINEERING_REVIEW"],
            "warnings": ["PERSONNEL_TRUCK_CROSSING_REQUIRES_ENGINEERING_REVIEW"],
            "warning": "PERSONNEL_TRUCK_CROSSING_REQUIRES_ENGINEERING_REVIEW",
        }
    predicate = evaluate_personnel_truck_policy(
        shared_route=shared,
        crossing=False,
        crossing_necessary=False,
    )
    return {
        "status": predicate["status"],
        "shared_route": shared,
        "crossing": crossing,
        "crossing_necessary": False,
        "requires_review": predicate["requires_review"],
        "codes": list(predicate.get("codes", [])),
        "warnings": list(predicate.get("warnings", [])),
        "warning": None,
    }


def route_payload_hash(payload: Mapping[str, Any]) -> str:
    """Public canonical hash helper for route result evidence."""
    return canonical_hash(payload)
