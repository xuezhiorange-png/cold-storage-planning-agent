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
    SUPPORT_GROUP,
    StructuralCompositionFamilyV1,
)

IDENTITY: Final = "structural-quality-vector@2.0.0"
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


def _group_envelope_facts(
    zones: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Derive exact group extents and shared-edge component facts."""
    result: dict[str, dict[str, Any]] = {}
    for group, members in FUNCTIONAL_GROUPS.items():
        existing = tuple(code for code in members if code in zones)
        bounds = {code: _bounds(zones[code]) for code in existing}
        adjacency: dict[str, set[str]] = {code: set() for code in existing}
        edge_count = 0
        for index, first in enumerate(existing):
            for second in existing[index + 1 :]:
                if _shared_edge_orientation(bounds[first], bounds[second]) is not None:
                    edge_count += 1
                    adjacency[first].add(second)
                    adjacency[second].add(first)
        components = 0
        unseen = set(existing)
        while unseen:
            components += 1
            pending = [min(unseen)]
            unseen.remove(pending[0])
            while pending:
                current = pending.pop()
                for neighbor in sorted(adjacency[current] & unseen):
                    unseen.remove(neighbor)
                    pending.append(neighbor)
        if bounds:
            result[group] = {
                "min_x": str(min(row[0] for row in bounds.values())),
                "min_y": str(min(row[1] for row in bounds.values())),
                "max_x": str(max(row[2] for row in bounds.values())),
                "max_y": str(max(row[3] for row in bounds.values())),
                "zone_count": len(existing),
                "connected_shared_edge_component_count": components,
                "shared_internal_edge_count": edge_count,
            }
        else:
            result[group] = {
                "min_x": None,
                "min_y": None,
                "max_x": None,
                "max_y": None,
                "zone_count": 0,
                "connected_shared_edge_component_count": 0,
                "shared_internal_edge_count": 0,
            }
    return result


def _main_group_order_fact(
    zones: Mapping[str, Mapping[str, Any]], family: StructuralCompositionFamilyV1
) -> tuple[bool, str, dict[str, Any]]:
    axis = (
        family.dominant_axis
        if family.family == LINEAR_PROCESS_BAND
        else ("Y" if family.dominant_axis == "X" else "X")
    )
    group_intervals: list[tuple[int, Decimal, Decimal]] = []
    terminal_codes = ("finished_goods_room", "shipping_channel")
    group_codes = (
        FUNCTIONAL_GROUPS["RAW_SIDE_GROUP"],
        FUNCTIONAL_GROUPS["PROCESSING_CORE_GROUP"],
        terminal_codes,
    )
    for codes in group_codes:
        rows = [zones[code] for code in codes if code in zones]
        if not rows:
            return False, axis, {}
        group_bounds = [_bounds(row) for row in rows]
        low_index, high_index = (0, 2) if axis == "X" else (1, 3)
        group_intervals.append(
            (
                len(rows),
                min(bounds[low_index] for bounds in group_bounds),
                max(bounds[high_index] for bounds in group_bounds),
            )
        )
    _, raw_low, raw_high = group_intervals[0]
    _, core_low, core_high = group_intervals[1]
    _, finished_low, finished_high = group_intervals[2]
    if family.family == LINEAR_PROCESS_BAND and family.dominant_direction == "POSITIVE":
        valid = raw_high <= core_low and core_high <= finished_low
    elif family.family == LINEAR_PROCESS_BAND:
        valid = finished_high <= core_low and core_high <= raw_low
    else:
        valid = (raw_high <= core_low and core_high <= finished_low) or (
            finished_high <= core_low and core_high <= raw_low
        )
    facts = {
        "axis": axis,
        "raw_interval": [str(raw_low), str(raw_high)],
        "processing_core_interval": [str(core_low), str(core_high)],
        "finished_interval": [str(finished_low), str(finished_high)],
        "finished_terminal_zone_codes": list(terminal_codes),
        "transition_zone_codes": ["secondary_precooling_room"],
    }
    return valid, axis, facts


def _support_attachment_sides(zones: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    core_codes = ("sorting_packaging_room", "packaging_material_storage")
    sides: set[str] = set()
    for support in _SUPPORT_CODES:
        if support not in zones:
            continue
        support_bounds = _bounds(zones[support])
        for root in core_codes:
            if root not in zones:
                continue
            root_bounds = _bounds(zones[root])
            if _shared_edge_orientation(support_bounds, root_bounds) is None:
                continue
            if support_bounds[2] == root_bounds[0]:
                sides.add("WEST")
            elif support_bounds[0] == root_bounds[2]:
                sides.add("EAST")
            elif support_bounds[3] == root_bounds[1]:
                sides.add("SOUTH")
            elif support_bounds[1] == root_bounds[3]:
                sides.add("NORTH")
    return tuple(sorted(sides))


def _process_core_face_facts(
    zones: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Measure exposed and support-occupied faces of the sorting core exactly."""
    core_code = "sorting_packaging_room"
    if core_code not in zones:
        return (), ()
    core = _bounds(zones[core_code])
    faces = {"NORTH", "EAST", "SOUTH", "WEST"}
    occupied_by_any: set[str] = set()
    occupied_by_support: set[str] = set()
    for code, zone in zones.items():
        if code == core_code:
            continue
        bounds = _bounds(zone)
        if _shared_edge_orientation(core, bounds) is None:
            continue
        if bounds[2] == core[0]:
            side = "WEST"
        elif bounds[0] == core[2]:
            side = "EAST"
        elif bounds[3] == core[1]:
            side = "SOUTH"
        else:
            side = "NORTH"
        occupied_by_any.add(side)
        if code in _SUPPORT_CODES:
            occupied_by_support.add(side)
    return tuple(sorted(faces - occupied_by_any)), tuple(sorted(occupied_by_support))


def _storage_bank_alignment_facts(
    zones: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    banks = {
        "RAW_SIDE_BANK": ("raw_fruit_buffer", "primary_precooling_room"),
        "FINISHED_SIDE_BANK": ("secondary_precooling_room", "finished_goods_room"),
        "FROZEN_SIDE_BRANCH": ("frozen_fruit_room",),
    }
    result: dict[str, Any] = {}
    for bank, codes in banks.items():
        pairs = [
            (first, second)
            for index, first in enumerate(codes)
            for second in codes[index + 1 :]
            if first in zones and second in zones
        ]
        aligned = 0
        for first, second in pairs:
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
        result[bank] = {
            "status": "MEASURED" if pairs else "NOT_APPLICABLE",
            "aligned_pair_count": aligned,
            "eligible_pair_count": len(pairs),
        }
    return result


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
    search_phase: str = "STRUCTURED",
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
    group_envelopes = _group_envelope_facts(zones)
    group_order_monotonic, group_order_axis, group_order_facts = _main_group_order_fact(
        zones, family
    )
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
    support_sides = _support_attachment_sides(zones)
    exposed_core_faces, support_occupied_core_faces = _process_core_face_facts(zones)
    support_components = group_envelopes[SUPPORT_GROUP]["connected_shared_edge_component_count"]
    process_core_components = group_envelopes["PROCESSING_CORE_GROUP"][
        "connected_shared_edge_component_count"
    ]
    process_core_contiguous = process_core_components == 1
    storage_bank_alignment = _storage_bank_alignment_facts(zones)
    storage_bank_aligned_pairs = sum(
        row["aligned_pair_count"]
        for row in storage_bank_alignment.values()
        if isinstance(row, Mapping)
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
        "structural_profile_identity": "structural-quality-profile@2.0.0",
        "composition_family": family.to_dict(),
        "search_phase": search_phase,
        "inferred_process_family": inferred_family,
        "composition_family_match": family_match,
        "group_envelopes": group_envelopes,
        "main_group_order_monotonic": {
            "status": "MEASURED",
            "value": group_order_monotonic,
            "axis": group_order_axis,
            "intervals": group_order_facts,
        },
        "process_core_contiguous": {
            "status": "MEASURED",
            "value": process_core_contiguous,
            "component_count": process_core_components,
        },
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
            "attachment_sides": list(support_sides),
            "attachment_side_count": len(support_sides),
            "support_component_count": support_components,
            "authoritative_access_routes": support_route_pass_count,
            "required_access_routes": len(support_routes),
            "support_chain_root": "sorting_packaging_room",
        },
        "process_core_faces": {
            "status": "MEASURED",
            "core_zone_code": "sorting_packaging_room",
            "core_exposed_main_faces": list(exposed_core_faces),
            "support_occupied_core_faces": list(support_occupied_core_faces),
        },
        "storage_bank_alignment": {
            "status": "MEASURED",
            "banks": storage_bank_alignment,
            "aligned_pair_count": storage_bank_aligned_pairs,
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
        int(group_order_monotonic),
        int(process_core_contiguous),
        int(family_match),
        *tuple(group_edges[group] for group in FUNCTIONAL_GROUPS),
        process_core_edges,
        support_route_pass_count,
        -len(support_sides),
        -int(support_components),
        support_direct,
        -len(support_occupied_core_faces),
        len(exposed_core_faces),
        personnel_boundary_contacts,
        storage_bank_aligned_pairs,
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
