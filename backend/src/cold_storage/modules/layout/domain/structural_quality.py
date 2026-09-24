"""Exact, non-weighted P1A structural facts and lexicographic comparison."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from cold_storage.modules.layout.domain.dimensioning import canonical_json
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    FUNCTIONAL_GROUPS,
    LINEAR_PROCESS_BAND,
    MAIN_PROCESS_ZONE_CODES,
    StructuralCompositionFamilyV1,
)

IDENTITY: Final = "structural-quality-vector@1.0.0"
MAJOR_ZONE_CODES: Final = (
    "primary_precooling_room",
    "secondary_precooling_room",
    "sorting_packaging_room",
    "finished_goods_room",
    "packaging_material_storage",
)
_SUPPORT_CODES: Final = FUNCTIONAL_GROUPS["SUPPORT_GROUP"]
_PERSONNEL_CODES: Final = FUNCTIONAL_GROUPS["PERSONNEL_GROUP"]


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"invalid structural fact: {field}") from None
    if not result.is_finite():
        raise ValueError(f"invalid structural fact: {field}")
    return result


def _bounds(zone: Mapping[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    x = _decimal(zone.get("x"), field="zone.x")
    y = _decimal(zone.get("y"), field="zone.y")
    width = _decimal(zone.get("width_m"), field="zone.width_m")
    depth = _decimal(zone.get("depth_m"), field="zone.depth_m")
    rotation = zone.get("rotation_deg")
    if rotation == 90:
        width, depth = depth, width
    elif rotation != 0:
        raise ValueError("invalid structural fact: zone.rotation_deg")
    return x, y, x + width, y + depth


def _shared_edge_orientation(
    first: tuple[Decimal, Decimal, Decimal, Decimal],
    second: tuple[Decimal, Decimal, Decimal, Decimal],
) -> str | None:
    left_a, bottom_a, right_a, top_a = first
    left_b, bottom_b, right_b, top_b = second
    if (right_a == left_b or right_b == left_a) and min(top_a, top_b) > max(bottom_a, bottom_b):
        return "VERTICAL"
    if (top_a == bottom_b or top_b == bottom_a) and min(right_a, right_b) > max(left_a, left_b):
        return "HORIZONTAL"
    return None


def _major_axis_facts(
    zones: Mapping[str, Mapping[str, Any]],
) -> tuple[int, int, Decimal]:
    bounds = {code: _bounds(zones[code]) for code in MAJOR_ZONE_CODES if code in zones}
    if len(bounds) != len(MAJOR_ZONE_CODES):
        return 0, 0, Decimal(0)
    primary_x: set[Decimal] = set()
    primary_y: set[Decimal] = set()
    values = tuple(bounds.values())
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            orientation = _shared_edge_orientation(first, second)
            if orientation == "VERTICAL":
                primary_x.add(first[2] if first[2] == second[0] else first[0])
            elif orientation == "HORIZONTAL":
                primary_y.add(first[3] if first[3] == second[1] else first[1])
    aligned = 0
    for left, bottom, right, top in values:
        aligned += int(left in primary_x) + int(right in primary_x)
        aligned += int(bottom in primary_y) + int(top in primary_y)
    total = len(values) * 4
    return aligned, total, Decimal(aligned) / Decimal(total)


def _depth_alignment_facts(
    zones: Mapping[str, Mapping[str, Any]],
) -> tuple[int, int, str]:
    # P0's compatible, same-band pairs are only admitted when exact geometry
    # shows a positive shared edge between members of the same frozen group.
    eligible_pairs: list[tuple[str, str]] = []
    for members in FUNCTIONAL_GROUPS.values():
        major_members = tuple(
            code for code in members if code in MAJOR_ZONE_CODES and code in zones
        )
        for index, first in enumerate(major_members):
            for second in major_members[index + 1 :]:
                if _shared_edge_orientation(_bounds(zones[first]), _bounds(zones[second])):
                    eligible_pairs.append((first, second))
    if not eligible_pairs:
        return 0, 0, "NOT_APPLICABLE"
    aligned = 0
    for first, second in eligible_pairs:
        first_bounds = _bounds(zones[first])
        second_bounds = _bounds(zones[second])
        orientation = _shared_edge_orientation(first_bounds, second_bounds)
        if orientation == "VERTICAL":
            aligned += int(
                first_bounds[1] == second_bounds[1] and first_bounds[3] == second_bounds[3]
            )
        elif orientation == "HORIZONTAL":
            aligned += int(
                first_bounds[0] == second_bounds[0] and first_bounds[2] == second_bounds[2]
            )
    return aligned, len(eligible_pairs), "MEASURED"


def _group_edge_facts(
    zones: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    facts: dict[str, int] = {}
    for group, members in FUNCTIONAL_GROUPS.items():
        existing = tuple(code for code in members if code in zones)
        edge_count = 0
        for index, first in enumerate(existing):
            for second in existing[index + 1 :]:
                edge_count += int(
                    _shared_edge_orientation(_bounds(zones[first]), _bounds(zones[second]))
                    is not None
                )
        facts[group] = edge_count
    return facts


def _personnel_boundary_contacts(
    zones: Mapping[str, Mapping[str, Any]], site_geometry: Mapping[str, Any]
) -> int:
    site = site_geometry.get("site")
    boundary = site.get("effective_buildable_boundary") if isinstance(site, Mapping) else None
    raw_points = boundary.get("points") if isinstance(boundary, Mapping) else None
    if not isinstance(raw_points, list) or len(raw_points) < 3:
        return 0
    points = [
        (_decimal(point["x"], field="boundary.x"), _decimal(point["y"], field="boundary.y"))
        for point in raw_points
        if isinstance(point, Mapping) and "x" in point and "y" in point
    ]
    if len(points) != len(raw_points):
        return 0
    contacts = 0
    for code in _PERSONNEL_CODES:
        if code not in zones:
            continue
        left, bottom, right, top = _bounds(zones[code])
        touched = False
        for first, second in zip(points, points[1:] + points[:1], strict=True):
            if first[0] == second[0] and first[0] in {left, right}:
                touched = min(top, max(first[1], second[1])) > max(bottom, min(first[1], second[1]))
            elif first[1] == second[1] and first[1] in {bottom, top}:
                touched = min(right, max(first[0], second[0])) > max(left, min(first[0], second[0]))
            if touched:
                break
        contacts += int(touched)
    return contacts


def _outline_class(layout: Mapping[str, Any]) -> tuple[str, int]:
    footprint = layout.get("building_footprint")
    if not isinstance(footprint, Mapping):
        return "UNAVAILABLE", 9
    polygon = footprint.get("footprint")
    raw_points = polygon.get("points") if isinstance(polygon, Mapping) else None
    if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes)):
        return "UNAVAILABLE", 9
    points: list[tuple[Decimal, Decimal]] = []
    for point in raw_points:
        if not isinstance(point, Mapping):
            return "AMBIGUOUS_REQUIRES_OWNER_REVIEW", 8
        points.append(
            (
                _decimal(point.get("x"), field="footprint.x"),
                _decimal(point.get("y"), field="footprint.y"),
            )
        )
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    simplified: list[tuple[Decimal, Decimal]] = []
    for point in points:
        simplified.append(point)
    changed = True
    while changed and len(simplified) > 4:
        changed = False
        reduced: list[tuple[Decimal, Decimal]] = []
        size = len(simplified)
        for index, current in enumerate(simplified):
            previous = simplified[index - 1]
            following = simplified[(index + 1) % size]
            if (previous[0] == current[0] == following[0]) or (
                previous[1] == current[1] == following[1]
            ):
                changed = True
            else:
                reduced.append(current)
        if len(reduced) < 4:
            break
        simplified = reduced
    if any(
        first[0] != second[0] and first[1] != second[1]
        for first, second in zip(simplified, simplified[1:] + simplified[:1], strict=True)
    ):
        return "AMBIGUOUS_REQUIRES_OWNER_REVIEW", 8
    if len(simplified) == 4:
        return "RECTANGLE", 0
    twice_area = sum(
        simplified[index][0] * simplified[(index + 1) % len(simplified)][1]
        - simplified[(index + 1) % len(simplified)][0] * simplified[index][1]
        for index in range(len(simplified))
    )
    orientation = 1 if twice_area > 0 else -1
    reflex_count = 0
    for index, current in enumerate(simplified):
        previous = simplified[index - 1]
        following = simplified[(index + 1) % len(simplified)]
        cross = (current[0] - previous[0]) * (following[1] - current[1]) - (
            current[1] - previous[1]
        ) * (following[0] - current[0])
        reflex_count += int(cross * orientation < 0)
    if reflex_count == 1:
        return "SIMPLE_L", 1
    if reflex_count >= 2:
        # Multiple exact re-entrant corners describe a more stepped outline;
        # this label is categorical and does not constitute a numeric gate.
        return "STAIR_STEP", 3
    return "AMBIGUOUS_REQUIRES_OWNER_REVIEW", 8


def _route_topologies(routed: Mapping[str, Any]) -> dict[str, str]:
    rows = routed.get("access_results")
    if not isinstance(rows, list):
        return {}
    result: dict[str, str] = {}
    for row in rows:
        if isinstance(row, Mapping):
            identity = row.get("requirement_identity")
            topology = row.get("topology")
            if isinstance(identity, str) and isinstance(topology, str):
                result[identity] = topology
    return result


def _process_family(zones: Mapping[str, Mapping[str, Any]]) -> str:
    orientations: list[str] = []
    for first, second in zip(
        MAIN_PROCESS_ZONE_CODES[:-1], MAIN_PROCESS_ZONE_CODES[1:], strict=True
    ):
        if first not in zones or second not in zones:
            continue
        orientation = _shared_edge_orientation(_bounds(zones[first]), _bounds(zones[second]))
        if orientation is None:
            continue
        orientations.append(orientation)
    if orientations and len(set(orientations)) == 1:
        return LINEAR_PROCESS_BAND
    return CENTRAL_PROCESS_HUB


@dataclass(frozen=True)
class StructuralQualityFactsV1:
    """Immutable internal facts; intentionally not added to Tool 7 payloads."""

    facts_json: str
    comparison_key: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.facts_json)
        if not isinstance(value, dict):
            raise TypeError("structural quality facts must be an object")
        return value


def build_structural_quality_facts(
    candidate: Mapping[str, Any],
    routed_layout: Mapping[str, Any],
    site_geometry: Mapping[str, Any],
    family: StructuralCompositionFamilyV1,
    *,
    structurally_generated: bool,
) -> StructuralQualityFactsV1:
    raw_zones = candidate.get("zones")
    if not isinstance(raw_zones, list):
        raise ValueError("structural candidate zones unavailable")
    zones = {
        str(row["zone_code"]): row
        for row in raw_zones
        if isinstance(row, Mapping) and isinstance(row.get("zone_code"), str)
    }
    if set(zones) != set(code for members in FUNCTIONAL_GROUPS.values() for code in members):
        raise ValueError("structural zone binding incomplete")

    group_edges = _group_edge_facts(zones)
    grid_count, grid_total, grid_rate = _major_axis_facts(zones)
    depth_aligned, depth_eligible, depth_status = _depth_alignment_facts(zones)
    outline, outline_rank = _outline_class(routed_layout)
    topologies = _route_topologies(routed_layout)
    support_direct = 0
    for code in _SUPPORT_CODES:
        if code not in zones:
            continue
        if any(
            _shared_edge_orientation(_bounds(zones[code]), _bounds(zones[reference])) is not None
            for reference in ("sorting_packaging_room", *_SUPPORT_CODES)
            if reference != code and reference in zones
        ):
            support_direct += 1
    support_routes = {
        "packaging_material_storage": (
            "access:packaging_material_storage->sorting_packaging_room@1.0.0"
        ),
        "secondary_fruit_buffer": "access:sorting_packaging_room->secondary_fruit_buffer@1.0.0",
        "frozen_fruit_room": "access:sorting_packaging_room->frozen_fruit_room@1.0.0",
    }
    support_route_pass_count = sum(
        int(topologies.get(identity) in {"DIRECT_SHARED_EDGE", "CORRIDOR_MEDIATED"})
        for identity in support_routes.values()
    )
    process_core_edges = sum(
        int(_shared_edge_orientation(_bounds(zones[first]), _bounds(zones[second])) is not None)
        for first, second in (
            ("primary_precooling_room", "sorting_packaging_room"),
            ("sorting_packaging_room", "secondary_precooling_room"),
        )
    )
    personnel_boundary_contacts = _personnel_boundary_contacts(zones, site_geometry)

    # A central core is the selected family when sorting is the largest
    # authoritative process zone.  This is an ordinal semantic fact, not a
    # calibrated pass threshold.
    process_areas = {
        code: _decimal(zones[code].get("required_area_m2"), field=f"{code}.area")
        for code in MAIN_PROCESS_ZONE_CODES
        if code in zones
    }
    core_area = process_areas.get("sorting_packaging_room")
    core_dominant = core_area is not None and all(
        core_area >= value
        for code, value in process_areas.items()
        if code != "sorting_packaging_room"
    )
    inferred_family = _process_family(zones)
    family_match = inferred_family == family.family or (
        family.family == CENTRAL_PROCESS_HUB and core_dominant
    )

    # P1A keeps unsupported route-backtrack/turn/efficiency claims unavailable.
    # P2D's exact route topology and direct-edge evidence above are consumed as
    # facts, but not converted into centroid/Manhattan proxies.
    metrics: dict[str, Any] = {
        "identity": IDENTITY,
        "structural_profile_identity": "structural-quality-profile@1.0.0",
        "composition_family": family.to_dict(),
        "inferred_process_family": inferred_family,
        "composition_family_match": family_match,
        "structurally_generated": structurally_generated,
        "structural_fallback_used": not structurally_generated,
        "functional_group_edge_counts": group_edges,
        "functional_grouping_status": "MEASURED",
        "process_core_legibility": {
            "status": "MEASURED",
            "direct_main_process_edges": process_core_edges,
            "required_edges": 2,
        },
        "support_branch_subordination": {
            "status": "MEASURED",
            "direct_group_edges": support_direct,
            "authoritative_access_routes": support_route_pass_count,
            "required_access_routes": len(support_routes),
        },
        "personnel_peripherality": {
            "status": "MEASURED",
            "zones_touching_effective_boundary": personnel_boundary_contacts,
            "zone_count": len(_PERSONNEL_CODES),
        },
        "major_zone_grid_alignment": {
            "status": "MEASURED",
            "aligned_boundary_incidences": grid_count,
            "total_boundary_incidences": grid_total,
            "rate": str(grid_rate),
        },
        "major_zone_depth_alignment": {
            "status": depth_status,
            "aligned_eligible_pairs": depth_aligned,
            "eligible_pairs": depth_eligible,
            "rate": str(Decimal(depth_aligned) / Decimal(depth_eligible))
            if depth_eligible
            else None,
        },
        "building_outline_class": outline,
        "main_flow_backtrack_count": {"status": "UNAVAILABLE", "value": None},
        "main_flow_turn_count": {"status": "UNAVAILABLE", "value": None},
        "process_route_efficiency": {"status": "UNAVAILABLE", "value": None},
        "hard_feasibility_passed": True,
    }

    # Fixed component order.  There is no aggregation, weighting or numeric
    # threshold.  P2B2's historical comparator is consulted only on exact ties.
    comparison_key = (
        int(structurally_generated),
        int(family_match),
        *tuple(group_edges[group] for group in FUNCTIONAL_GROUPS),
        process_core_edges,
        support_route_pass_count,
        support_direct,
        personnel_boundary_contacts,
        grid_count,
        depth_aligned,
        -outline_rank,
    )
    return StructuralQualityFactsV1(canonical_json(metrics), comparison_key)


def structural_candidate_is_better(
    candidate: StructuralQualityFactsV1,
    best: StructuralQualityFactsV1 | None,
) -> bool:
    """Compare atomically and lexicographically; no weighted score."""
    return best is None or candidate.comparison_key > best.comparison_key


__all__ = [
    "IDENTITY",
    "MAJOR_ZONE_CODES",
    "StructuralQualityFactsV1",
    "build_structural_quality_facts",
    "structural_candidate_is_better",
]
