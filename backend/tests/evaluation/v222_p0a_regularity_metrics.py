"""Offline geometry facts for V2.2.2 P0A calibration evidence only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

_MAJOR_ZONE_CODES = (
    "primary_precooling_room",
    "secondary_precooling_room",
    "sorting_packaging_room",
    "finished_goods_room",
    "packaging_material_storage",
)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _zone_bounds(zone: Mapping[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    x = _decimal(zone["x"])
    y = _decimal(zone["y"])
    width = _decimal(zone["width_m"])
    depth = _decimal(zone["depth_m"])
    rotation = zone["rotation_deg"]
    if rotation == 90:
        width, depth = depth, width
    elif rotation != 0:
        raise ValueError("unsupported rotation in P0A geometry evidence")
    return x, y, x + width, y + depth


def major_zone_grid_alignment_rate(layout: Mapping[str, Any]) -> Decimal:
    """Apply the exact P0 shared-major-zone-axis incidence definition."""
    zones_by_code = {
        str(zone["zone_code"]): zone for zone in layout["zones"] if isinstance(zone, Mapping)
    }
    zones = [zones_by_code[code] for code in _MAJOR_ZONE_CODES]
    bounds = [_zone_bounds(zone) for zone in zones]
    primary_x_axes: set[Decimal] = set()
    primary_y_axes: set[Decimal] = set()

    for first_index, first in enumerate(bounds):
        for second in bounds[first_index + 1 :]:
            first_left, first_bottom, first_right, first_top = first
            second_left, second_bottom, second_right, second_top = second
            if first_right == second_left or second_right == first_left:
                if min(first_top, second_top) > max(first_bottom, second_bottom):
                    primary_x_axes.add(first_right if first_right == second_left else first_left)
            if first_top == second_bottom or second_top == first_bottom:
                if min(first_right, second_right) > max(first_left, second_left):
                    primary_y_axes.add(first_top if first_top == second_bottom else first_bottom)

    aligned = 0
    for left, bottom, right, top in bounds:
        aligned += int(left in primary_x_axes) + int(right in primary_x_axes)
        aligned += int(bottom in primary_y_axes) + int(top in primary_y_axes)
    return Decimal(aligned) / Decimal(len(bounds) * 4)


def _polygon_points(footprint: Mapping[str, Any]) -> list[tuple[Decimal, Decimal]]:
    polygon = footprint["footprint"]
    if not isinstance(polygon, Mapping) or polygon.get("type") != "polygon":
        raise ValueError("P0A requires the authoritative single polygon footprint")
    raw_points = polygon.get("points")
    if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes)):
        raise ValueError("invalid P0A footprint point list")
    points = [(_decimal(point["x"]), _decimal(point["y"])) for point in raw_points]
    if len(points) < 4:
        raise ValueError("P0A footprint polygon has too few points")
    return points


def building_geometry_facts(layout: Mapping[str, Any]) -> dict[str, Any]:
    """Return only exact facts defined by P0; no threshold/classifier is added."""
    footprint = layout["building_footprint"]
    if not isinstance(footprint, Mapping):
        raise ValueError("missing authoritative building footprint")
    points = _polygon_points(footprint)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    shoelace_twice_area = sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )
    polygon_area = abs(shoelace_twice_area) / Decimal(2)
    declared_area = _decimal(footprint["gross_area_m2"])
    if polygon_area != declared_area or width <= 0 or height <= 0:
        raise ValueError("authoritative footprint area/bounds are inconsistent")

    reflex_count = 0
    orientation = 1 if shoelace_twice_area > 0 else -1
    for index, current in enumerate(points):
        previous = points[index - 1]
        following = points[(index + 1) % len(points)]
        incoming_x = current[0] - previous[0]
        incoming_y = current[1] - previous[1]
        outgoing_x = following[0] - current[0]
        outgoing_y = following[1] - current[1]
        cross = incoming_x * outgoing_y - incoming_y * outgoing_x
        if cross * orientation < 0:
            reflex_count += 1

    return {
        "BOUNDING_RECTANGLE_OCCUPANCY": declared_area / (width * height),
        "EXTERIOR_REFLEX_CORNER_COUNT": reflex_count,
        "MAIN_BUILDING_COMPONENT_COUNT": 1,
        "FOOTPRINT_AREA_M2": declared_area,
        "FOOTPRINT_BOUNDS_M": {
            "min_x": min(xs),
            "min_y": min(ys),
            "max_x": max(xs),
            "max_y": max(ys),
        },
    }
