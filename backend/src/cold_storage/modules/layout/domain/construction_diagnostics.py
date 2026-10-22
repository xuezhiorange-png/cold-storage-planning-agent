"""Exact construction facts, never a calibrated P0 quality validator/selector."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW
from cold_storage.modules.layout.domain.construction_diversity import physical_boxes
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError

IDENTITY = "construction-fact-diagnostics@1.0.0"
MAJOR_ROLES = (
    "primary_precooling_room",
    "secondary_precooling_room",
    "sorting_packaging_room",
    "finished_goods_room",
    "packaging_material_storage",
)


def _mm(value: Any) -> int:
    n = Decimal(str(value)) * 1000
    if not n.is_finite() or n != n.to_integral_value():
        raise LayoutAuthorityError("CONSTRUCTION_DIAGNOSTIC_NON_MM_COORDINATE")
    return int(n)


def _direction(a: tuple[int, ...], b: tuple[int, ...]) -> str:
    if min(a[3], b[3]) > max(a[1], b[1]):
        if a[2] == b[0]:
            return "E"
        if b[2] == a[0]:
            return "W"
    if min(a[2], b[2]) > max(a[0], b[0]):
        if a[3] == b[1]:
            return "N"
        if b[3] == a[1]:
            return "S"
    return "UNAVAILABLE"


def construction_diagnostics(
    zones: Sequence[Mapping[str, Any]], application: Mapping[str, Any]
) -> dict[str, Any]:
    boxes = physical_boxes(zones)
    directions = [
        _direction(boxes[a], boxes[b])
        for a, b in zip(PROCESS_FLOW[:-1], PROCESS_FLOW[1:], strict=True)
    ]
    opposite = {"E": "W", "W": "E", "N": "S", "S": "N"}
    transitions = list(zip(directions[:-1], directions[1:], strict=True))
    shapes = {
        r: {
            "physical_width_m": str(Decimal(c - a) / 1000),
            "physical_depth_m": str(Decimal(d - b) / 1000),
            "area_m2": str(Decimal((c - a) * (d - b)) / 1000000),
            "aspect_ratio": str(Decimal(max(c - a, d - b)) / min(c - a, d - b)),
        }
        for r, (a, b, c, d) in boxes.items()
    }
    routes = []
    for row in application.get("access_results", []):
        if row.get("flow_kind") == "TRUCK":
            continue
        path = [(_mm(p["x"]), _mm(p["y"])) for p in row.get("centerline", [])]
        lengths, headings = [], []
        for (x, y), (u, v) in zip(path, path[1:], strict=False):
            if x == u and y == v:
                continue
            if x != u and y != v:
                raise LayoutAuthorityError("CONSTRUCTION_DIAGNOSTIC_NON_ORTHOGONAL_ROUTE")
            lengths.append(abs(x - u) + abs(y - v))
            headings.append("E" if u > x else "W" if u < x else "N" if v > y else "S")
        length = sum(lengths)
        lower = abs(path[0][0] - path[-1][0]) + abs(path[0][1] - path[-1][1]) if path else None
        routes.append(
            {
                "identity": row["requirement_identity"],
                "from_ref": row["from_ref"],
                "to_ref": row["to_ref"],
                "status": row["status"],
                "topology": row["topology"],
                "centerline": row.get("centerline"),
                "portal_from": row.get("portal_from"),
                "portal_to": row.get("portal_to"),
                "clear_width_m": row.get("clear_width_m"),
                "measured_centerline_length_m": str(Decimal(length) / 1000),
                "measured_heading_changes": sum(
                    a != b for a, b in zip(headings, headings[1:], strict=False)
                ),
                "reported_route_length_matches": Decimal(str(row["route_length_m"]))
                == Decimal(length) / 1000,
                "endpoint_manhattan_lower_bound_m": str(Decimal(lower) / 1000)
                if lower is not None
                else None,
                "necessary_detour": "UNAVAILABLE_NO_COMPARABLE_SHORTEST_FEASIBLE_ROUTE",
            }
        )
    axes: dict[tuple[str, int], set[str]] = defaultdict(set)
    for role in MAJOR_ROLES:
        x, y, right, top = boxes[role]
        for ax, pos in (("X", x), ("X", right), ("Y", y), ("Y", top)):
            axes[ax, pos].add(role)
    aligned = sum(len(roles) for roles in axes.values() if len(roles) >= 2)
    footprint = None
    raw = application.get("building_footprint")
    if raw:
        points = [(_mm(p["x"]), _mm(p["y"])) for p in raw["footprint"]["points"]]
        if points[0] == points[-1]:
            points.pop()
        pairs = list(zip(points, points[1:] + points[:1], strict=True))
        signed = sum(x * v - u * y for (x, y), (u, v) in pairs)
        perimeter = sum(abs(u - x) + abs(v - y) for (x, y), (u, v) in pairs)
        crosses = []
        for i, (x, y) in enumerate(points):
            a, b = points[i - 1]
            c, d = points[(i + 1) % len(points)]
            crosses.append((x - a) * (d - y) - (y - b) * (c - x))
        bbox = (max(p[0] for p in points) - min(p[0] for p in points)) * (
            max(p[1] for p in points) - min(p[1] for p in points)
        )
        footprint = {
            "source": "ACTUAL_APPLICATION_BUILDING_FOOTPRINT",
            "area_m2": str(Decimal(abs(signed)) / 2000000),
            "perimeter_m": str(Decimal(perimeter) / 1000),
            "outline_turn_count": sum(c != 0 for c in crosses),
            "reflex_corner_count": sum(c * signed < 0 for c in crosses),
            "bounding_rectangle_area_m2": str(Decimal(bbox) / 1000000),
            "bounding_rectangle_occupancy": str(Decimal(abs(signed)) / (2 * bbox)),
            "notch_count": "UNAVAILABLE_VERSIONED_CLASSIFIER_NOT_CALIBRATED",
            "isolated_appendage_count": "UNAVAILABLE_VERSIONED_CLASSIFIER_NOT_CALIBRATED",
        }
    return {
        "identity": IDENTITY,
        "formal_quality_gate_applied": False,
        "process_flow_validated": "NOT_EVALUATED",
        "layout_regularity_validated": "NOT_EVALUATED_UNCALIBRATED",
        "adjacency_directions": directions,
        "adjacency_direction_changes": sum(a != b for a, b in transitions)
        if "UNAVAILABLE" not in directions
        else None,
        "adjacent_opposite_directions": sum(opposite.get(a) == b for a, b in transitions)
        if "UNAVAILABLE" not in directions
        else None,
        "adjacency_directions_are_not_route_turns": True,
        "main_flow_backtrack_count": None,
        "main_flow_turn_count": None,
        "formal_main_flow_status": "UNAVAILABLE_RECEIVING_DIRECTION_BANDS_AND_INTERNAL_CONNECTORS",
        "main_process_route_length_m": None,
        "room_shapes": shapes,
        "actual_access_route_facts": routes,
        "major_zone_grid_alignment_rate": str(Decimal(aligned) / (4 * len(MAJOR_ROLES))),
        "grid_numeric_gate_applied": False,
        "depth_alignment_rate": "UNAVAILABLE_ELIGIBLE_PAIR_AUTHORITY_NOT_BOUND",
        "footprint": footprint,
        "shipping_loading_face_segment": application.get("shipping_loading_face_segment"),
        "shipping_loading_face_side": application.get("shipping_loading_face_side"),
        "truck_route_status": application.get("truck_route_status", "NOT_EVALUATED"),
        "real_truck_approval_claimed": False,
    }
