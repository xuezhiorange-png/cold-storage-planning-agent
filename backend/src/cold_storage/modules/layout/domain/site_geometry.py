"""Exact local-Cartesian geometry primitives for the V2.2 P2A foundation.

This module validates and compares geometry.  It deliberately does not place
zones, solve routes, search layouts, or choose engineering dimensions.
Coordinates are converted to integer millimetres at the boundary so all hard
predicates remain exact and independent of floating-point tolerances.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import (
    GRID,
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)

IDENTITY = "site-geometry-foundation@1.0.0"
SCHEMA_VERSION = "1.0.0"
COORDINATE_SYSTEM = "LOCAL_CARTESIAN_METERS"
GRID_M = GRID
MILLIMETRES_PER_METRE = 1000
MAX_COORDINATE_M = Decimal("1000000000")

type PointPair = tuple[int, int]
type PolygonMM = tuple[PointPair, ...]
type SegmentMM = tuple[PointPair, PointPair]


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _coordinate_to_mm(
    value: object, *, code: str, field: str, allow_numeric_string: bool = False
) -> int:
    """Convert a JSON number on the exact 0.001m grid to integer millimetres."""
    accepted = (int, float, Decimal, str) if allow_numeric_string else (int, float, Decimal)
    if isinstance(value, bool) or not isinstance(value, accepted):
        raise _error(code, field=field, value=str(value))
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _error(code, field=field, value=str(value)) from None
    if not number.is_finite() or abs(number) > MAX_COORDINATE_M:
        raise _error(code, field=field, value=str(value))
    with localcontext(Context(prec=80)):
        scaled = number * MILLIMETRES_PER_METRE
        if scaled != scaled.to_integral_value():
            raise _error(code, field=field, value=str(value), grid_m=str(GRID_M))
        return int(scaled)


def _positive_length_to_mm(value: object, *, code: str, field: str) -> int:
    millimetres = _coordinate_to_mm(value, code=code, field=field)
    if millimetres <= 0:
        raise _error(code, field=field, value=str(value))
    return millimetres


def _mm_to_m(value: int) -> Decimal:
    with localcontext(Context(prec=80)):
        return Decimal(value) / MILLIMETRES_PER_METRE


def _point_from_mapping(
    value: object, *, code: str, field: str, allow_numeric_string: bool = False
) -> PointPair:
    if not isinstance(value, Mapping) or set(value) != {"x", "y"}:
        raise _error(code, field=field)
    return (
        _coordinate_to_mm(
            value["x"], code=code, field=f"{field}.x", allow_numeric_string=allow_numeric_string
        ),
        _coordinate_to_mm(
            value["y"], code=code, field=f"{field}.y", allow_numeric_string=allow_numeric_string
        ),
    )


def point_to_dict(point: PointPair) -> dict[str, Decimal]:
    return {"x": _mm_to_m(point[0]), "y": _mm_to_m(point[1])}


def polygon_to_dict(polygon: PolygonMM) -> dict[str, Any]:
    return {"type": "polygon", "points": [point_to_dict(point) for point in polygon]}


def _cross(a: PointPair, b: PointPair, c: PointPair) -> int:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point: PointPair, start: PointPair, end: PointPair) -> bool:
    return (
        _cross(start, end, point) == 0
        and min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
        and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
    )


def _segments_intersect_closed(a: PointPair, b: PointPair, c: PointPair, d: PointPair) -> bool:
    ab_c = _cross(a, b, c)
    ab_d = _cross(a, b, d)
    cd_a = _cross(c, d, a)
    cd_b = _cross(c, d, b)
    if ((ab_c > 0 > ab_d) or (ab_c < 0 < ab_d)) and ((cd_a > 0 > cd_b) or (cd_a < 0 < cd_b)):
        return True
    return (
        (ab_c == 0 and _on_segment(c, a, b))
        or (ab_d == 0 and _on_segment(d, a, b))
        or (cd_a == 0 and _on_segment(a, c, d))
        or (cd_b == 0 and _on_segment(b, c, d))
    )


def _adjacent_edges_intersect_beyond_vertex(
    first: PointPair, shared: PointPair, last: PointPair
) -> bool:
    # Adjacent edges may meet at their common vertex, but may not backtrack or
    # overlap along a collinear interval.
    return _on_segment(first, shared, last) or _on_segment(last, first, shared)


def _polygon_edges(polygon: PolygonMM) -> tuple[tuple[PointPair, PointPair], ...]:
    return tuple(
        (polygon[index], polygon[(index + 1) % len(polygon)]) for index in range(len(polygon))
    )


def _signed_double_area(polygon: PolygonMM) -> int:
    return sum(
        first[0] * second[1] - second[0] * first[1] for first, second in _polygon_edges(polygon)
    )


def normalize_polygon(
    value: object,
    *,
    error_code: str = "INVALID_SITE_BOUNDARY",
    allow_numeric_string: bool = False,
) -> PolygonMM:
    """Validate a simple, implicitly closed polygon and return integer-mm points."""
    if not isinstance(value, Mapping) or set(value) != {"type", "points"}:
        raise _error(error_code)
    if value.get("type") != "polygon":
        raise _error(error_code)
    raw_points = value.get("points")
    if not isinstance(raw_points, (list, tuple)) or len(raw_points) < 3:
        raise _error(error_code)
    points = tuple(
        _point_from_mapping(
            point,
            code=error_code,
            field=f"points[{index}]",
            allow_numeric_string=allow_numeric_string,
        )
        for index, point in enumerate(raw_points)
    )
    if points[0] == points[-1] or len(set(points)) != len(points):
        raise _error(error_code, reason="REPEATED_VERTEX")
    if any(first == second for first, second in _polygon_edges(points)):
        raise _error(error_code, reason="ZERO_LENGTH_EDGE")
    if _signed_double_area(points) == 0:
        raise _error(error_code, reason="ZERO_AREA")
    edges = _polygon_edges(points)
    edge_count = len(edges)
    for first_index, (first_start, first_end) in enumerate(edges):
        for second_index in range(first_index + 1, edge_count):
            second_start, second_end = edges[second_index]
            adjacent = second_index == first_index + 1 or (
                first_index == 0 and second_index == edge_count - 1
            )
            if adjacent:
                shared = first_end if second_index == first_index + 1 else first_start
                first_non_shared = first_start if shared == first_end else first_end
                second_non_shared = second_end if shared == second_start else second_start
                if _adjacent_edges_intersect_beyond_vertex(
                    first_non_shared, shared, second_non_shared
                ):
                    raise _error(error_code, reason="SELF_TOUCHING")
            elif _segments_intersect_closed(first_start, first_end, second_start, second_end):
                raise _error(error_code, reason="SELF_INTERSECTING")
    return points


def _fraction_point(point: PointPair) -> tuple[Fraction, Fraction]:
    return Fraction(point[0]), Fraction(point[1])


def _fraction_cross(
    a: tuple[Fraction, Fraction],
    b: tuple[Fraction, Fraction],
    c: tuple[Fraction, Fraction],
) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_on_fraction_segment(
    point: tuple[Fraction, Fraction],
    start: tuple[Fraction, Fraction],
    end: tuple[Fraction, Fraction],
) -> bool:
    return (
        _fraction_cross(start, end, point) == 0
        and min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
        and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
    )


def _point_in_polygon_fraction(point: tuple[Fraction, Fraction], polygon: PolygonMM) -> bool:
    edges = tuple((_fraction_point(a), _fraction_point(b)) for a, b in _polygon_edges(polygon))
    if any(_point_on_fraction_segment(point, start, end) for start, end in edges):
        return True
    inside = False
    x, y = point
    for start, end in edges:
        if (start[1] > y) != (end[1] > y):
            intersection_x = start[0] + (y - start[1]) * (end[0] - start[0]) / (end[1] - start[1])
            if intersection_x > x:
                inside = not inside
    return inside


def point_in_polygon(point: PointPair, polygon: PolygonMM) -> bool:
    return _point_in_polygon_fraction(_fraction_point(point), polygon)


def _segment_intersection_parameters(
    start: PointPair, end: PointPair, other_start: PointPair, other_end: PointPair
) -> tuple[Fraction, ...]:
    """Return all closed intersection parameters on [start,end]."""
    p = _fraction_point(start)
    r = (
        Fraction(end[0] - start[0]),
        Fraction(end[1] - start[1]),
    )
    q = _fraction_point(other_start)
    s = (
        Fraction(other_end[0] - other_start[0]),
        Fraction(other_end[1] - other_start[1]),
    )
    denominator = r[0] * s[1] - r[1] * s[0]
    q_minus_p = (q[0] - p[0], q[1] - p[1])
    if denominator != 0:
        t = (q_minus_p[0] * s[1] - q_minus_p[1] * s[0]) / denominator
        u = (q_minus_p[0] * r[1] - q_minus_p[1] * r[0]) / denominator
        if 0 <= t <= 1 and 0 <= u <= 1:
            return (t,)
        return ()
    if q_minus_p[0] * r[1] - q_minus_p[1] * r[0] != 0:
        return ()
    if r[0] != 0:
        first = Fraction(other_start[0] - start[0], end[0] - start[0])
        second = Fraction(other_end[0] - start[0], end[0] - start[0])
    else:
        first = Fraction(other_start[1] - start[1], end[1] - start[1])
        second = Fraction(other_end[1] - start[1], end[1] - start[1])
    lower = max(Fraction(0), min(first, second))
    upper = min(Fraction(1), max(first, second))
    if lower > upper:
        return ()
    return (lower, upper)


def _segment_inside_or_boundary(start: PointPair, end: PointPair, polygon: PolygonMM) -> bool:
    parameters: set[Fraction] = {Fraction(0), Fraction(1)}
    for other_start, other_end in _polygon_edges(polygon):
        parameters.update(_segment_intersection_parameters(start, end, other_start, other_end))
    ordered = sorted(parameters)
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left == right:
            continue
        midpoint_parameter = (left + right) / 2
        midpoint = (
            Fraction(start[0]) + midpoint_parameter * (end[0] - start[0]),
            Fraction(start[1]) + midpoint_parameter * (end[1] - start[1]),
        )
        if not _point_in_polygon_fraction(midpoint, polygon):
            return False
    return True


def polygon_contains_polygon(container: PolygonMM, candidate: PolygonMM) -> bool:
    """Containment with shared boundary allowed, including concave containers."""
    return all(
        _segment_inside_or_boundary(start, end, container)
        for start, end in _polygon_edges(candidate)
    )


def _segment_on_polygon_boundary(start: PointPair, end: PointPair, polygon: PolygonMM) -> bool:
    if start == end or not point_in_polygon(start, polygon) or not point_in_polygon(end, polygon):
        return False
    if not any(
        _on_segment(start, edge_start, edge_end) for edge_start, edge_end in _polygon_edges(polygon)
    ):
        return False
    if not any(
        _on_segment(end, edge_start, edge_end) for edge_start, edge_end in _polygon_edges(polygon)
    ):
        return False
    parameters: set[Fraction] = {Fraction(0), Fraction(1)}
    for edge_start, edge_end in _polygon_edges(polygon):
        parameters.update(_segment_intersection_parameters(start, end, edge_start, edge_end))
    ordered = sorted(parameters)
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left == right:
            continue
        midpoint_parameter = (left + right) / 2
        midpoint = (
            Fraction(start[0]) + midpoint_parameter * (end[0] - start[0]),
            Fraction(start[1]) + midpoint_parameter * (end[1] - start[1]),
        )
        if not any(
            _point_on_fraction_segment(
                midpoint, _fraction_point(edge_start), _fraction_point(edge_end)
            )
            for edge_start, edge_end in _polygon_edges(polygon)
        ):
            return False
    return True


def segment_on_polygon_boundary(start: PointPair, end: PointPair, polygon: PolygonMM) -> bool:
    return _segment_on_polygon_boundary(start, end, polygon)


def segments_share_positive_length(
    first_start: PointPair,
    first_end: PointPair,
    second_start: PointPair,
    second_end: PointPair,
) -> bool:
    if (
        _cross(first_start, first_end, second_start) != 0
        or _cross(first_start, first_end, second_end) != 0
    ):
        return False
    if first_start[0] != first_end[0]:
        first_interval = sorted((first_start[0], first_end[0]))
        second_interval = sorted((second_start[0], second_end[0]))
    else:
        first_interval = sorted((first_start[1], first_end[1]))
        second_interval = sorted((second_start[1], second_end[1]))
    return min(first_interval[1], second_interval[1]) > max(first_interval[0], second_interval[0])


def normalize_segment(value: object, *, error_code: str = "INVALID_ENTRANCE") -> SegmentMM:
    if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
        raise _error(error_code)
    start = _point_from_mapping(value["start"], code=error_code, field="start")
    end = _point_from_mapping(value["end"], code=error_code, field="end")
    if start == end:
        raise _error(error_code, reason="ZERO_LENGTH")
    return (start, end) if start <= end else (end, start)


def segment_to_dict(segment: SegmentMM) -> dict[str, Any]:
    return {"start": point_to_dict(segment[0]), "end": point_to_dict(segment[1])}


def entrance_is_valid(segment: SegmentMM, site: PolygonMM) -> bool:
    return _segment_on_polygon_boundary(segment[0], segment[1], site)


@dataclass(frozen=True)
class PlacedRectangleV1:
    """Axis-aligned post-rotation rectangle observation used by future placement."""

    zone_code: str
    x: Decimal | int | float
    y: Decimal | int | float
    width_m: Decimal | int | float
    depth_m: Decimal | int | float
    rotation_deg: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.zone_code, str) or not self.zone_code:
            raise _error("INVALID_PLACED_RECTANGLE", field="zone_code")
        object.__setattr__(
            self,
            "x",
            _mm_to_m(_coordinate_to_mm(self.x, code="INVALID_PLACED_RECTANGLE", field="x")),
        )
        object.__setattr__(
            self,
            "y",
            _mm_to_m(_coordinate_to_mm(self.y, code="INVALID_PLACED_RECTANGLE", field="y")),
        )
        object.__setattr__(
            self,
            "width_m",
            _mm_to_m(
                _positive_length_to_mm(
                    self.width_m, code="INVALID_PLACED_RECTANGLE", field="width_m"
                )
            ),
        )
        object.__setattr__(
            self,
            "depth_m",
            _mm_to_m(
                _positive_length_to_mm(
                    self.depth_m, code="INVALID_PLACED_RECTANGLE", field="depth_m"
                )
            ),
        )
        if type(self.rotation_deg) is not int or self.rotation_deg not in (0, 90):
            raise _error("INVALID_ROTATION", field="rotation_deg")

    @property
    def bounds_mm(self) -> tuple[int, int, int, int]:
        x = _coordinate_to_mm(self.x, code="INVALID_PLACED_RECTANGLE", field="x")
        y = _coordinate_to_mm(self.y, code="INVALID_PLACED_RECTANGLE", field="y")
        width = _positive_length_to_mm(
            self.width_m, code="INVALID_PLACED_RECTANGLE", field="width_m"
        )
        depth = _positive_length_to_mm(
            self.depth_m, code="INVALID_PLACED_RECTANGLE", field="depth_m"
        )
        if self.rotation_deg == 90:
            width, depth = depth, width
        return x, y, x + width, y + depth

    @property
    def actual_area_m2(self) -> Decimal:
        width_mm = _positive_length_to_mm(
            self.width_m, code="INVALID_PLACED_RECTANGLE", field="width_m"
        )
        depth_mm = _positive_length_to_mm(
            self.depth_m, code="INVALID_PLACED_RECTANGLE", field="depth_m"
        )
        with localcontext(Context(prec=80)):
            return Decimal(width_mm * depth_mm) / 1000000

    @property
    def polygon_mm(self) -> PolygonMM:
        left, bottom, right, top = self.bounds_mm
        return ((left, bottom), (right, bottom), (right, top), (left, top))

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_code": self.zone_code,
            "x": self.x,
            "y": self.y,
            "width_m": self.width_m,
            "depth_m": self.depth_m,
            "rotation_deg": self.rotation_deg,
            "actual_area_m2": self.actual_area_m2,
        }


def placed_rectangle_from_mapping(value: object) -> PlacedRectangleV1:
    if not isinstance(value, Mapping) or set(value) != {
        "zone_code",
        "x",
        "y",
        "width_m",
        "depth_m",
        "rotation_deg",
    }:
        raise _error("INVALID_PLACED_RECTANGLE")
    if not isinstance(value["zone_code"], str):
        raise _error("INVALID_PLACED_RECTANGLE", field="zone_code")
    return PlacedRectangleV1(
        value["zone_code"],
        value["x"],
        value["y"],
        value["width_m"],
        value["depth_m"],
        value["rotation_deg"],
    )


def _rectangle(value: PlacedRectangleV1 | Mapping[str, Any]) -> PlacedRectangleV1:
    return value if isinstance(value, PlacedRectangleV1) else placed_rectangle_from_mapping(value)


def rectangle_inside_polygon(
    rectangle: PlacedRectangleV1 | Mapping[str, Any], polygon: PolygonMM | Mapping[str, Any]
) -> bool:
    rect = _rectangle(rectangle)
    candidate = polygon if isinstance(polygon, tuple) else normalize_polygon(polygon)
    return polygon_contains_polygon(candidate, rect.polygon_mm)


def rectangles_overlap(
    first: PlacedRectangleV1 | Mapping[str, Any], second: PlacedRectangleV1 | Mapping[str, Any]
) -> bool:
    left_a, bottom_a, right_a, top_a = _rectangle(first).bounds_mm
    left_b, bottom_b, right_b, top_b = _rectangle(second).bounds_mm
    return min(right_a, right_b) > max(left_a, left_b) and min(top_a, top_b) > max(
        bottom_a, bottom_b
    )


def rectangles_share_positive_edge(
    first: PlacedRectangleV1 | Mapping[str, Any], second: PlacedRectangleV1 | Mapping[str, Any]
) -> bool:
    left_a, bottom_a, right_a, top_a = _rectangle(first).bounds_mm
    left_b, bottom_b, right_b, top_b = _rectangle(second).bounds_mm
    return (
        (right_a == left_b or right_b == left_a) and min(top_a, top_b) > max(bottom_a, bottom_b)
    ) or ((top_a == bottom_b or top_b == bottom_a) and min(right_a, right_b) > max(left_a, left_b))


def rectangle_intersects_closed_obstacle(
    rectangle: PlacedRectangleV1 | Mapping[str, Any], obstacle: PolygonMM | Mapping[str, Any]
) -> bool:
    rect = _rectangle(rectangle)
    polygon = obstacle if isinstance(obstacle, tuple) else normalize_polygon(obstacle)
    rect_edges = _polygon_edges(rect.polygon_mm)
    obstacle_edges = _polygon_edges(polygon)
    if any(
        _segments_intersect_closed(a, b, c, d) for a, b in rect_edges for c, d in obstacle_edges
    ):
        return True
    left, bottom, right, top = rect.bounds_mm
    return any(point_in_polygon(point, polygon) for point in rect.polygon_mm) or any(
        left <= point[0] <= right and bottom <= point[1] <= top for point in polygon
    )


def building_footprint_polygon(value: object) -> PolygonMM:
    """Validate the future building primitive without generating an envelope."""
    polygon = normalize_polygon(value, error_code="INVALID_BUILDING_FOOTPRINT")
    edges = _polygon_edges(polygon)
    if any(start[0] != end[0] and start[1] != end[1] for start, end in edges):
        raise _error("INVALID_BUILDING_FOOTPRINT", reason="NON_ORTHOGONAL")
    return polygon


def validate_flexible_candidate(
    authority: Mapping[str, Any], width_m: object, depth_m: object
) -> dict[str, Any]:
    if authority.get("dimension_mode") != "FLEXIBLE_RECTANGLE":
        raise _error("INVALID_FLEXIBLE_DIMENSION_AUTHORITY")
    code = authority.get("zone_code")
    required = authority.get("required_area_m2")
    if not isinstance(code, str) or not isinstance(
        authority.get("p2_may_select_width_depth"), bool
    ):
        raise _error("INVALID_FLEXIBLE_DIMENSION_AUTHORITY")
    if authority.get("p2_may_select_width_depth") is not True:
        raise _error("FLEXIBLE_DIMENSION_SELECTION_NOT_AUTHORIZED", zone_code=code)
    required_number = _decimal_positive_or_zero(required, "required_area_m2")
    width = _mm_to_m(
        _positive_length_to_mm(width_m, code="INVALID_FLEXIBLE_DIMENSION", field="width_m")
    )
    depth = _mm_to_m(
        _positive_length_to_mm(depth_m, code="INVALID_FLEXIBLE_DIMENSION", field="depth_m")
    )
    with localcontext(Context(prec=80)):
        actual = width * depth
    if actual < required_number:
        raise _error(
            "FLEXIBLE_DIMENSION_AREA_UNSATISFIED",
            zone_code=code,
            required_area_m2=str(required_number),
            actual_area_m2=str(actual),
        )
    return {
        "zone_code": code,
        "dimension_mode": "FLEXIBLE_RECTANGLE",
        "required_area_m2": required_number,
        "width_m": width,
        "depth_m": depth,
        "actual_area_m2": actual,
        "rotation_deg": 0,
        "dimension_authority_identity": authority.get("dimension_authority_identity"),
    }


def _decimal_positive_or_zero(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise _error("INVALID_DIMENSIONING_VALUE", field=field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise _error("INVALID_DIMENSIONING_VALUE", field=field) from None
    if not number.is_finite() or number < 0:
        raise _error("INVALID_DIMENSIONING_VALUE", field=field)
    return number


def validate_concrete_candidate(
    authority: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    """Reject caller changes to a fixed/deterministic P1 geometry authority."""
    mode = authority.get("dimension_mode")
    if mode not in {"FIXED_RECTANGLE", "DETERMINISTIC_GRID_RECTANGLE"}:
        raise _error("INVALID_CONCRETE_DIMENSION_AUTHORITY")
    geometry = authority.get("geometry")
    if not isinstance(geometry, Mapping):
        raise _error("DIMENSION_AUTHORITY_REQUIRED", zone_code=authority.get("zone_code"))
    code = authority.get("zone_code")
    for field in (
        "zone_code",
        "required_area_m2",
        "width_m",
        "depth_m",
        "actual_area_m2",
        "dimensioning_profile_identity",
        "capacity_geometry_reference",
    ):
        if field in candidate and candidate[field] != geometry.get(field) and field != "zone_code":
            raise _error("FIXED_DIMENSION_RESIZE_FORBIDDEN", zone_code=code, field=field)
    if candidate.get("zone_code", code) != code:
        raise _error("FIXED_DIMENSION_ZONE_MISMATCH", zone_code=code)
    rotation = candidate.get("rotation_deg", 0)
    if type(rotation) is not int or rotation not in (0, 90):
        raise _error("INVALID_ROTATION", zone_code=code)
    return dict(geometry)


def geometry_hash(value: object) -> str:
    """Explicit name for canonical geometry hashing at this boundary."""
    return canonical_hash(value)


def geometry_json(value: object) -> str:
    return canonical_json(value)
