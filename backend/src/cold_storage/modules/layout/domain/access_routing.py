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
    for index, (start, end) in enumerate(zip(path, path[1:], strict=False)):
        midpoint = ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)
        for code, rectangle in zones.items():
            if code not in incident_refs or not _strict_point_in_polygon(
                midpoint, rectangle.polygon_mm
            ):
                continue
            if index not in {0, len(path) - 2}:
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
    """Search a finite visibility graph in stable coordinate order."""
    half = width_mm // 2
    x_values = {start[0], end[0]}
    y_values = {start[1], end[1]}
    for point in boundary:
        x_values.add(point[0])
        y_values.add(point[1])
    for rectangle in zones.values():
        left, bottom, right, top = rectangle.bounds_mm
        x_values.update((left - half, left, right, right + half))
        y_values.update((bottom - half, bottom, top, top + half))
    for obstacle in obstacles:
        for x, y in obstacle:
            x_values.update((x - half, x, x + half))
            y_values.update((y - half, y, y + half))
    xs = tuple(sorted(x_values))
    ys = tuple(sorted(y_values))
    nodes = {
        (x, y)
        for x in xs
        for y in ys
        if point_in_polygon((x, y), boundary)
        or any(_on_segment((x, y), a, b) for a, b in _polygon_edges(boundary))
    }
    nodes.update((start, end))
    queue: deque[tuple[int, int]] = deque([start])
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    visited = 0

    def neighbors(node: tuple[int, int]) -> Iterable[tuple[int, int]]:
        x, y = node
        x_index = xs.index(x)
        y_index = ys.index(y)
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

    while queue:
        current = queue.popleft()
        visited += 1
        if visited > node_budget:
            return None, "ROUTE_SEARCH_EXHAUSTED", ()
        if current == end:
            raw_path: list[tuple[int, int]] = []
            cursor: tuple[int, int] | None = current
            while cursor is not None:
                raw_path.append(cursor)
                cursor = parents[cursor]
            path = _compact_path(tuple(reversed(raw_path)))
            safe, reason, envelopes = _route_is_safe(
                path,
                width_mm=width_mm,
                boundary=boundary,
                obstacles=obstacles,
                zones=zones,
                incident_refs=incident_refs,
            )
            if safe:
                return path, "", envelopes
            if reason not in {None, "ROUTE_SEARCH_EXHAUSTED"}:
                # Continue looking: another parent may avoid the obstacle.
                pass
        for candidate in neighbors(current):
            if candidate in parents:
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
                parents[candidate] = current
                queue.append(candidate)
    return None, "ROUTE_SEARCH_EXHAUSTED", ()


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
    reasons: list[str] = []
    for path in _candidate_paths(start, end, straight_only=straight_only):
        safe, reason, envelopes = _route_is_safe(
            path,
            width_mm=width_mm,
            boundary=boundary,
            obstacles=obstacles,
            zones=zones,
            incident_refs=incident_refs,
        )
        if safe:
            return path, "", envelopes
        if reason is not None:
            reasons.append(reason)
    if straight_only:
        # A straight-only requirement has no legal fallback route.  Keep the
        # failure stable even when the straight segment also hits an obstacle
        # or an unrelated zone; callers must not interpret a rejected bend as
        # an ordinary route-search exhaustion.
        return None, "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED", ()
    grid_path, reason, envelopes = _route_grid_path(
        start,
        end,
        width_mm=width_mm,
        boundary=boundary,
        obstacles=obstacles,
        zones=zones,
        incident_refs=incident_refs,
        node_budget=node_budget,
    )
    return grid_path, reason or (reasons[0] if reasons else "ROUTE_SEARCH_EXHAUSTED"), envelopes


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


def _orthogonal_rectangles(polygons: Sequence[PolygonMM]) -> tuple[tuple[int, int, int, int], ...]:
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
    """Return the single simple orthogonal boundary of the exact rectangle union."""
    rectangles = _orthogonal_rectangles(
        [rectangle.polygon_mm for rectangle in zone_rectangles.values()] + list(corridor_polygons)
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
    predicate = evaluate_personnel_truck_policy(
        shared_route=shared,
        crossing=crossing,
        crossing_necessary=crossing,
    )
    return {
        "status": predicate["status"],
        "shared_route": shared,
        "crossing": crossing,
        "crossing_necessary": crossing,
        "requires_review": predicate["requires_review"],
        "codes": list(predicate.get("codes", [])),
        "warnings": list(predicate.get("warnings", [])),
        "warning": ("PERSONNEL_TRUCK_CROSSING_REQUIRES_ENGINEERING_REVIEW" if crossing else None),
    }


def route_payload_hash(payload: Mapping[str, Any]) -> str:
    """Public canonical hash helper for route result evidence."""
    return canonical_hash(payload)
