"""Exact route-aware admission for the structured S2 tail modules."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from cold_storage.modules.layout.application.access_handoff import required_access_connections
from cold_storage.modules.layout.domain import placement
from cold_storage.modules.layout.domain.access_authority import COLD_ROOM, resolve_access_profile
from cold_storage.modules.layout.domain.access_routing import (
    _edge_options,
    _find_route_skeleton_endpoints_v1,
    _find_route_skeleton_v1,
    route_access_requirement,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def _rectangle(
    code: str, bounds: tuple[int, int, int, int], *, rotation_deg: int = 0
) -> PlacedRectangleV1:
    left, bottom, right, top = bounds
    return PlacedRectangleV1(
        code,
        Decimal(left) / 1000,
        Decimal(bottom) / 1000,
        Decimal(right - left) / 1000,
        Decimal(top - bottom) / 1000,
        rotation_deg,
    )


def _route_skeleton_provider(
    start: tuple[int, int], end: tuple[int, int], **kwargs: Any
) -> dict[str, Any]:
    result = _find_route_skeleton_v1(start, end, **kwargs)
    return {
        "path": result.path,
        "reason": result.reason,
        "corridor_envelopes": tuple(row.polygon_mm for row in result.envelopes),
        "nodes_visited": result.nodes_visited,
        "node_budget_exhausted": result.node_budget_exhausted,
        "graph_exhausted": result.graph_exhausted,
        "search_source": result.search_source,
    }


def _route_skeleton_endpoint_provider(start: tuple[int, int], **kwargs: Any) -> dict[str, Any]:
    result = _find_route_skeleton_endpoints_v1(start, **kwargs)
    return {
        "endpoint_skeletons": tuple(
            {
                "endpoint": row.endpoint,
                "path": row.path,
                "corridor_envelopes": tuple(envelope.polygon_mm for envelope in row.envelopes),
            }
            for row in result.endpoint_skeletons
        ),
        "reason": result.reason,
        "nodes_visited": result.nodes_visited,
        "node_budget_exhausted": result.node_budget_exhausted,
        "graph_exhausted": result.graph_exhausted,
        "search_source": result.search_source,
    }


def _access_context(route: Any) -> SimpleNamespace:
    pairs = (
        ("main_entrance", "changing_room", "PEOPLE"),
        ("changing_room", "sorting_packaging_room", "PEOPLE"),
        ("sorting_packaging_room", "secondary_fruit_buffer", "MATERIAL"),
        ("sorting_packaging_room", "frozen_fruit_room", "MATERIAL"),
    )
    requirements = tuple(
        {
            "identity": f"REQ:{from_ref}->{to_ref}",
            "from_ref": from_ref,
            "to_ref": to_ref,
            "flow_kind": flow_kind,
        }
        for from_ref, to_ref, flow_kind in pairs
    )
    return SimpleNamespace(
        access_requirements=requirements,
        access_route_validator=route,
        spatial_relationships=(),
        boundary=((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000)),
        obstacles=(),
        main_entrance=((0, 45_000), (0, 55_000)),
    )


def test_route_corridor_reservation_uses_positive_area_not_boundary_contact() -> None:
    candidate = {"zone": _rectangle("zone", (10, 10, 20, 20))}
    touching = ((20, 10), (30, 10), (30, 20), (20, 20))
    overlapping = ((19, 10), (29, 10), (29, 20), (19, 20))
    l_shape = ((0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10))

    assert not placement._tail_corridor_conflicts(candidate, (touching,))
    assert placement._tail_corridor_conflicts(candidate, (overlapping,))
    assert placement._rectangle_interiors_overlap_orthogonal_polygon(
        _rectangle("arm", (8, 1, 9, 3)), l_shape
    )
    assert not placement._rectangle_interiors_overlap_orthogonal_polygon(
        _rectangle("void", (8, 6, 9, 8)), l_shape
    )


def test_people_route_truck_envelope_overlap_is_an_exact_ordering_fact() -> None:
    truck_envelope = ((10, 0), (20, 0), (20, 10), (10, 10))
    touching_route = ((20, 2), (30, 2), (30, 8), (20, 8))
    overlapping_route = ((19, 2), (29, 2), (29, 8), (19, 8))
    l_shaped_route = ((0, 0), (12, 0), (12, 3), (3, 3), (3, 12), (0, 12))
    separated_l_shape = ((0, 0), (8, 0), (8, 3), (3, 3), (3, 12), (0, 12))

    assert not placement._orthogonal_polygons_interiors_overlap(touching_route, truck_envelope)
    assert placement._orthogonal_polygons_interiors_overlap(overlapping_route, truck_envelope)
    assert placement._orthogonal_polygons_interiors_overlap(l_shaped_route, truck_envelope)
    assert not placement._orthogonal_polygons_interiors_overlap(separated_l_shape, truck_envelope)


def test_tail_route_probe_set_is_deterministic_and_spreads_side_and_rotation() -> None:
    sorting = _rectangle("sorting_packaging_room", (20_000, 20_000, 30_000, 30_000))
    fixed = {"sorting_packaging_room": sorting}
    candidates = []
    for _side, origins in {
        "WEST": ((10_000, 20_000), (10_000, 25_000)),
        "EAST": ((30_000, 20_000), (30_000, 25_000)),
        "SOUTH": ((20_000, 10_000), (25_000, 10_000)),
        "NORTH": ((20_000, 30_000), (25_000, 30_000)),
    }.items():
        for index, (x, y) in enumerate(origins):
            candidates.append(
                {
                    "secondary_fruit_buffer": _rectangle(
                        "secondary_fruit_buffer",
                        (x, y, x + 10_000, y + 10_000),
                        rotation_deg=90 if index == 0 else 0,
                    )
                }
            )
    first = placement._bounded_tail_candidate_representatives(
        SimpleNamespace(main_entrance=((0, 45_000), (0, 55_000))),
        "SECONDARY_SUPPORT_MODULE",
        candidates,
        fixed,
        limit=6,
    )
    second = placement._bounded_tail_candidate_representatives(
        SimpleNamespace(main_entrance=((0, 45_000), (0, 55_000))),
        "SECONDARY_SUPPORT_MODULE",
        candidates,
        fixed,
        limit=6,
    )

    assert tuple(placement._module_signature(row) for row in first) == tuple(
        placement._module_signature(row) for row in second
    )
    assert {row["secondary_fruit_buffer"].rotation_deg for row in first} == {0, 90}
    assert {placement._adjacent_side(sorting, row["secondary_fruit_buffer"]) for row in first} == {
        "NORTH",
        "SOUTH",
        "EAST",
        "WEST",
    }


def test_module_slot_probe_checks_only_new_module_routes_before_extension_revalidation() -> None:
    seen: list[str] = []

    def validator(requirement: Any, **_kwargs: Any) -> tuple[dict[str, Any], tuple[Any, ...]]:
        seen.append(f"{requirement['from_ref']}->{requirement['to_ref']}")
        return (
            {**requirement, "status": "PASS", "codes": [], "topology": "DIRECT_SHARED_EDGE"},
            (),
        )

    context = _access_context(validator)
    fixed = {
        "sorting_packaging_room": _rectangle(
            "sorting_packaging_room", (20_000, 20_000, 30_000, 30_000)
        ),
        "changing_room": _rectangle("changing_room", (30_000, 20_000, 40_000, 30_000)),
        "office": _rectangle("office", (40_000, 20_000, 50_000, 30_000)),
        "secondary_fruit_buffer": _rectangle(
            "secondary_fruit_buffer", (50_000, 20_000, 60_000, 30_000)
        ),
        "frozen_fruit_room": _rectangle("frozen_fruit_room", (60_000, 20_000, 70_000, 30_000)),
    }

    result = placement._tail_access_route_rows(
        context,
        fixed,
        placement._tail_access_requirement_rows(context) or (),
        module_name="FROZEN_SUPPORT_MODULE",
        stats=None,
        requirement_pairs=frozenset({("sorting_packaging_room", "frozen_fruit_room")}),
    )

    assert result is not None
    assert seen == ["sorting_packaging_room->frozen_fruit_room"]


def test_tail_slot_route_attempts_share_the_existing_placement_budget() -> None:
    context = SimpleNamespace(
        node_budget=1,
        structural_topology="STRAIGHT_LINEAR_BAND",
        structured_building_plan=SimpleNamespace(layout_family="LINEAR_3_BAND"),
    )
    stats = placement._PlacementSearchStats()

    assert placement._charge_tail_access_slot_node(
        context,
        stats,
        module_name="CHANGING_MODULE",
        candidate_index=1,
        skeleton_hash="skeleton-a",
    )
    assert stats.visited_nodes == 1
    assert stats.tail_access_slot_attempt_count == 1
    assert stats.current_work_item == {
        "topology": "STRAIGHT_LINEAR_BAND",
        "layout_family": "LINEAR_3_BAND",
        "band_family": "LINEAR_3_BAND",
        "skeleton_hash": "skeleton-a",
        "branch": "S2_ACCESS_VALID_TAIL_SLOT",
        "tail_module": "CHANGING_MODULE",
        "tail_candidate_index": 1,
        "placement_node_charged": True,
    }

    assert not placement._charge_tail_access_slot_node(
        context,
        stats,
        module_name="CHANGING_MODULE",
        candidate_index=2,
        skeleton_hash="skeleton-a",
    )
    assert stats.visited_nodes == 1
    assert stats.node_budget_exhausted is True
    assert stats.skeleton_search_truncated is True
    assert stats.tail_access_slot_budget_exhausted is True


def test_s2_routes_receive_current_partial_zones_and_reserve_real_corridors() -> None:
    seen: list[tuple[str, tuple[str, ...]]] = []
    corridor = ((5_000, 5_000), (8_000, 5_000), (8_000, 8_000), (5_000, 8_000))

    def validator(requirement: Any, **kwargs: Any) -> tuple[dict[str, Any], tuple[Any, ...]]:
        pair = (str(requirement["from_ref"]), str(requirement["to_ref"]))
        zones = kwargs["zones"]
        seen.append(("->".join(pair), tuple(sorted(zones))))
        topology = (
            "CORRIDOR_MEDIATED"
            if pair == ("main_entrance", "changing_room")
            else "DIRECT_SHARED_EDGE"
        )
        row = {
            **requirement,
            "status": "PASS",
            "codes": [],
            "topology": topology,
            "centerline": [],
            "route_shape": "STRAIGHT",
            "turn_count": 0,
            "route_length_m": "0",
        }
        return row, (corridor,) if topology == "CORRIDOR_MEDIATED" else ()

    context = _access_context(validator)
    fixed = {
        "sorting_packaging_room": _rectangle(
            "sorting_packaging_room", (20_000, 20_000, 30_000, 30_000)
        ),
        "changing_room": _rectangle("changing_room", (40_000, 20_000, 50_000, 30_000)),
        "secondary_fruit_buffer": _rectangle(
            "secondary_fruit_buffer", (60_000, 20_000, 70_000, 30_000)
        ),
    }
    stats = placement._PlacementSearchStats(site_module_assembly_trace=[])

    result = placement._tail_access_route_rows(
        context,
        fixed,
        placement._tail_access_requirement_rows(context) or (),
        module_name="SECONDARY_SUPPORT_MODULE",
        stats=stats,
    )

    assert result is not None
    assert {row[0] for row in seen} == {
        "main_entrance->changing_room",
        "changing_room->sorting_packaging_room",
        "sorting_packaging_room->secondary_fruit_buffer",
    }
    assert all(set(zones) == set(fixed) for _pair, zones in seen)
    assert stats.access_route_revalidation_count == 3
    assert stats.direct_shared_edge_access_witness_count == 2
    assert stats.corridor_mediated_access_witness_count == 1
    assert stats.reserved_access_corridor_geometries == {tuple(sorted(corridor))}
    assert len(result[1]) == 1


def test_failed_shoulder_route_rejects_candidate_without_becoming_a_must_edge() -> None:
    calls: list[str] = []

    def validator(requirement: Any, **_kwargs: Any) -> tuple[dict[str, Any], tuple[Any, ...]]:
        pair = f"{requirement['from_ref']}->{requirement['to_ref']}"
        calls.append(pair)
        status = "BLOCKED" if pair == "sorting_packaging_room->frozen_fruit_room" else "PASS"
        return (
            {
                **requirement,
                "status": status,
                "codes": ["ROUTE_SEARCH_EXHAUSTED"] if status != "PASS" else [],
                "topology": "CORRIDOR_MEDIATED",
                "centerline": [],
                "route_shape": "STRAIGHT",
                "turn_count": 0,
                "route_length_m": "1",
            },
            (),
        )

    context = _access_context(validator)
    fixed = {
        "sorting_packaging_room": _rectangle(
            "sorting_packaging_room", (20_000, 20_000, 30_000, 30_000)
        ),
        "changing_room": _rectangle("changing_room", (40_000, 20_000, 50_000, 30_000)),
        "secondary_fruit_buffer": _rectangle(
            "secondary_fruit_buffer", (60_000, 20_000, 70_000, 30_000)
        ),
        "frozen_fruit_room": _rectangle("frozen_fruit_room", (80_000, 20_000, 90_000, 30_000)),
    }
    stats = placement._PlacementSearchStats(site_module_assembly_trace=[])

    result = placement._tail_access_route_rows(
        context,
        fixed,
        placement._tail_access_requirement_rows(context) or (),
        module_name="FROZEN_SUPPORT_MODULE",
        stats=stats,
    )

    assert result is None
    assert calls == [
        "changing_room->sorting_packaging_room",
        "main_entrance->changing_room",
        "sorting_packaging_room->frozen_fruit_room",
    ]
    assert stats.construction_access_requirement_failure_counts == {
        "sorting_packaging_room->frozen_fruit_room": 1
    }
    assert stats.construction_access_failure_code_counts == {"ROUTE_SEARCH_EXHAUSTED": 1}


def _tail_geometry_context(route: Any = None) -> SimpleNamespace:
    bounds = ((0, 0), (200_000, 0), (200_000, 200_000), (0, 200_000))
    codes = ("office", "changing_room", "secondary_fruit_buffer", "frozen_fruit_room")
    return SimpleNamespace(
        authorities={
            code: {
                "zone_code": code,
                "dimension_mode": "FIXED_RECTANGLE",
                "required_area_m2": 200,
                "geometry": {"width_m": 10, "depth_m": 20, "required_area_m2": 200},
            }
            for code in codes
        },
        boundary=bounds,
        boundary_bounds=(0, 0, 200_000, 200_000),
        obstacles=(),
        main_entrance=((0, 45_000), (0, 55_000)),
        access_requirements=_access_context(route).access_requirements,
        access_route_validator=route,
        spatial_relationships=(),
    )


def _one_bay() -> tuple[placement.BuildableBayV1, ...]:
    return (placement.BuildableBayV1("BAY-0001", (0, 0, 200_000, 200_000), 40_000_000_000),)


def _xinzhao_frozen_corridor_context() -> tuple[Any, dict[str, PlacedRectangleV1]]:
    main = {
        "raw_fruit_buffer": _rectangle("raw_fruit_buffer", (45_060, 0, 60_260, 8_700)),
        "primary_precooling_room": _rectangle(
            "primary_precooling_room", (60_260, 0, 74_960, 10_050)
        ),
        "sorting_packaging_room": _rectangle(
            "sorting_packaging_room", (29_200, 10_050, 74_960, 23_650)
        ),
        "secondary_precooling_room": _rectangle(
            "secondary_precooling_room", (22_763, 23_650, 32_563, 33_700)
        ),
        "coating_room": _rectangle("coating_room", (32_563, 23_650, 40_524, 33_700)),
        "finished_goods_room": _rectangle("finished_goods_room", (32_563, 33_700, 40_524, 52_300)),
        "shipping_channel": _rectangle("shipping_channel", (1_624, 33_700, 8_124, 41_393)),
        "packaging_material_storage": _rectangle(
            "packaging_material_storage", (14_700, 0, 29_200, 17_300)
        ),
    }
    requirements = tuple(
        asdict(requirement)
        for requirement in required_access_connections()
        if (requirement.from_ref, requirement.to_ref)
        == ("sorting_packaging_room", "frozen_fruit_room")
    )
    boundary = ((0, 0), (75_460, 0), (75_460, 55_000), (0, 55_000))
    obstacles = (
        ((0, 8_701), (14_699, 8_701), (14_699, 18_750), (0, 18_750)),
        ((41_718, 27_000), (74_999, 27_000), (74_999, 39_385), (41_718, 39_385)),
        ((41_718, 39_386), (74_999, 39_386), (74_999, 53_886), (41_718, 53_886)),
    )

    def portal_events(
        requirement: Any, endpoint_ref: str, rectangle: PlacedRectangleV1
    ) -> dict[str, Any]:
        profile = resolve_access_profile(str(requirement["profile_identity"]))
        portal_width = int(profile.portal_clear_width_m * 1000)
        if endpoint_ref in requirement.get("cold_room_refs", ()):
            portal_width = max(
                portal_width,
                int(resolve_access_profile(COLD_ROOM).portal_clear_width_m * 1000),
            )
        left, bottom, right, top = rectangle.bounds_mm
        portals = []
        for option in _edge_options(rectangle, required_class=None, clear_width_mm=portal_width):
            (x0, y0), (x1, y1) = option["segment_mm"]
            side = (
                "WEST"
                if x0 == x1 == left
                else "EAST"
                if x0 == x1 == right
                else "SOUTH"
                if y0 == y1 == bottom
                else "NORTH"
                if y0 == y1 == top
                else None
            )
            if side is not None:
                portals.append(
                    {
                        "side": side,
                        "edge_class": option["edge_class"],
                        "segment_mm": option["segment_mm"],
                        "center_mm": (
                            (option["segment_mm"][0][0] + option["segment_mm"][1][0]) // 2,
                            (option["segment_mm"][0][1] + option["segment_mm"][1][1]) // 2,
                        ),
                        "clear_width_mm": portal_width,
                    }
                )
        return {
            "portals": tuple(portals),
            "portal_clear_width_mm": portal_width,
            "corridor_clear_width_mm": int(profile.corridor_clear_width_m * 1000),
        }

    context = SimpleNamespace(
        authorities={
            "frozen_fruit_room": {
                "zone_code": "frozen_fruit_room",
                "dimension_mode": "FIXED_RECTANGLE",
                "required_area_m2": 88.56,
                "geometry": {"width_m": 10.8, "depth_m": 8.2, "required_area_m2": 88.56},
            }
        },
        access_requirements=requirements,
        access_portal_event_provider=portal_events,
        access_route_skeleton_provider=_route_skeleton_provider,
        access_route_skeleton_endpoint_provider=_route_skeleton_endpoint_provider,
        access_route_hint_node_budget=20_000,
        boundary=boundary,
        boundary_bounds=(0, 0, 75_460, 55_000),
        obstacles=obstacles,
        spatial_relationships=(),
        main_entrance=((75_460, 24_525), (75_460, 26_525)),
    )
    return context, main


def test_frozen_truck_clear_corridor_event_gets_official_route_pass() -> None:
    context, _main = _xinzhao_frozen_corridor_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    sorting = _rectangle("sorting_packaging_room", (30_000, 30_000, 45_000, 43_600))
    fixed = {"sorting_packaging_room": sorting}
    truck_envelopes = (((70_000, 70_000), (80_000, 70_000), (80_000, 70_001), (70_000, 70_001)),)
    candidates = placement._frozen_truck_clear_corridor_candidates(
        context,
        fixed,
        (),
        truck_envelopes,
        stats=None,
        main_identity="open-site-main",
    )
    candidate = next(
        candidate
        for candidate in candidates
        if candidate.endpoint_event_class == "FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED"
    )
    frozen = candidate.as_placements()["frozen_fruit_room"]
    corridor_centerline = candidate.construction_corridor_centerline_mm
    construction_corridors = placement._corridor_rectangles_for_centerline(
        corridor_centerline, 2_500
    )
    result, corridors = route_access_requirement(
        context.access_requirements[0],
        relationships={},
        zones={**fixed, "frozen_fruit_room": frozen},
        boundary=context.boundary,
        obstacles=context.obstacles,
        entrances={},
    )
    assert candidate.endpoint_event_class == "FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED"
    assert "SORTING_PORTAL" in candidate.anchor_source
    assert candidate.construction_corridor_centerline_mm
    assert candidate.construction_corridor_envelopes_mm
    assert (
        candidate.construction_corridor_centerline_mm[0]
        != (candidate.construction_corridor_centerline_mm[-1])
    )
    assert tuple(row.polygon_mm for row in construction_corridors) == (
        candidate.construction_corridor_envelopes_mm
    )
    repeated = placement._frozen_truck_clear_corridor_candidates(
        context,
        fixed,
        (),
        truck_envelopes,
        stats=None,
        main_identity="open-site-main",
    )
    assert [row.as_placements() for row in candidates] == [row.as_placements() for row in repeated]
    assert result["status"] == "PASS"
    assert result["topology"] == "CORRIDOR_MEDIATED"
    assert corridors
    assert result["centerline"]
    assert all(
        not placement._orthogonal_polygons_interiors_overlap(corridor, truck_envelopes[0])
        for corridor in corridors
    )
    assert all(
        not placement._orthogonal_polygons_interiors_overlap(corridor, zone.polygon_mm)
        for corridor in corridors
        for zone in (sorting, frozen)
    )
    assert all(
        not placement._orthogonal_polygons_interiors_overlap(corridor, truck_envelopes[0])
        for corridor in corridors
    )


def test_frozen_direct_seed_is_rejected_for_exact_truck_overlap() -> None:
    context, fixed = _xinzhao_frozen_corridor_context()
    truck_envelope = (
        (39_000, 2_000),
        (39_500, 2_000),
        (39_500, 9_800),
        (39_000, 9_800),
    )
    stats = placement._PlacementSearchStats()

    placement._frozen_truck_clear_corridor_candidates(
        context,
        fixed,
        (),
        (truck_envelope,),
        stats=stats,
        main_identity="verified-direct-truck-overlap",
    )

    assert (
        stats.tail_direct_seed_counts_before_truck_filter_by_main["verified-direct-truck-overlap"][
            "FROZEN_SUPPORT_MODULE"
        ]
        == 1
    )
    assert (
        stats.tail_direct_seed_counts_after_truck_filter_by_main["verified-direct-truck-overlap"][
            "FROZEN_SUPPORT_MODULE"
        ]
        == 0
    )
    rejection = stats.frozen_direct_seed_truck_rejection_rows[0]
    assert rejection["truck_envelope_identity"] == "TRUCK_ENVELOPE-01"
    assert rejection["exact_positive_area_overlap"] is True
    assert rejection["overlap_bounds_mm"] == [39_000, 2_000, 39_500, 9_800]


def test_frozen_target_portal_can_be_anchored_to_remote_free_space_event() -> None:
    context, _main = _xinzhao_frozen_corridor_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    sorting = _rectangle("sorting_packaging_room", (30_000, 30_000, 45_000, 43_600))
    changing = _rectangle("changing_room", (5_000, 45_000, 15_800, 50_000))
    fixed = {"sorting_packaging_room": sorting, "changing_room": changing}
    truck_envelopes = (((70_000, 70_000), (80_000, 70_000), (80_000, 80_000), (70_000, 80_000)),)

    candidates = placement._frozen_truck_clear_corridor_candidates(
        context,
        fixed,
        (),
        truck_envelopes,
        stats=None,
        main_identity="remote-event-main",
    )
    candidate = next(
        candidate
        for candidate in candidates
        if candidate.as_placements()["frozen_fruit_room"].bounds_mm[1] == 50_000
    )
    frozen = candidate.as_placements()["frozen_fruit_room"]
    result, corridors = route_access_requirement(
        context.access_requirements[0],
        relationships={},
        zones={**fixed, "frozen_fruit_room": frozen},
        boundary=context.boundary,
        obstacles=context.obstacles,
        entrances={},
    )

    assert "VISIBILITY_ENDPOINT" in candidate.anchor_source
    assert "SORTING_PORTAL" in candidate.anchor_source
    assert result["status"] == "PASS"
    if candidate.endpoint_event_class == "FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED":
        assert len(candidate.construction_corridor_centerline_mm) >= 2
        assert candidate.construction_corridor_envelopes_mm
        assert corridors
    else:
        assert candidate.endpoint_event_class == "FROZEN_ENDPOINT_PAIR_ROUTE_PENDING"
        assert candidate.construction_corridor_centerline_mm == ()
        assert candidate.construction_corridor_envelopes_mm == ()


def test_frozen_router_pass_overlapping_fixed_zone_is_rejected_for_construction() -> None:
    context, main = _xinzhao_frozen_corridor_context()
    frozen = _rectangle("frozen_fruit_room", (20_800, 33_700, 31_600, 41_900))
    fixed = {
        **main,
        "changing_room": _rectangle("changing_room", (44_480, 23_650, 59_680, 26_282)),
        "office": _rectangle("office", (378, 25_954, 8_124, 33_700)),
        "secondary_fruit_buffer": _rectangle(
            "secondary_fruit_buffer", (29_200, 3_150, 37_600, 10_050)
        ),
        "frozen_fruit_room": frozen,
    }
    authoritative, corridors = route_access_requirement(
        context.access_requirements[0],
        relationships={},
        zones=fixed,
        boundary=context.boundary,
        obstacles=context.obstacles,
        entrances={},
    )
    assert authoritative["status"] == "PASS"
    assert any(
        placement._orthogonal_polygons_interiors_overlap(
            corridor, fixed["secondary_precooling_room"].polygon_mm
        )
        for corridor in corridors
    )

    context.access_route_validator = route_access_requirement
    context.access_requirements = tuple(
        asdict(requirement)
        for requirement in required_access_connections()
        if (requirement.from_ref, requirement.to_ref)
        in {
            ("main_entrance", "changing_room"),
            ("changing_room", "sorting_packaging_room"),
            ("sorting_packaging_room", "secondary_fruit_buffer"),
            ("sorting_packaging_room", "frozen_fruit_room"),
        }
    )
    stats = placement._PlacementSearchStats()
    admitted = placement._tail_access_route_rows(
        context,
        fixed,
        context.access_requirements,
        module_name="FROZEN_SUPPORT_MODULE",
        stats=stats,
        requirement_pairs=frozenset({("sorting_packaging_room", "frozen_fruit_room")}),
        require_truck_clear_corridors=True,
        main_identity="main-34888140",
    )
    assert admitted is None
    assert stats.frozen_candidate_rejection_taxonomy_by_main == {
        "main-34888140": {"FROZEN_CORRIDOR_OVERLAPS_FIXED_ZONE": 1}
    }


def test_access_driven_changing_uses_both_endpoints_and_finite_event_classes() -> None:
    context = _tail_geometry_context()
    sorting = _rectangle("sorting_packaging_room", (30_000, 40_000, 40_000, 50_000))
    shipping = _rectangle("shipping_channel", (70_000, 70_000, 80_000, 80_000))
    fixed = {"sorting_packaging_room": sorting, "shipping_channel": shipping}

    candidates = placement._access_driven_tail_candidates(
        context, "CHANGING_MODULE", "changing_room", fixed, _one_bay()
    )
    shifted_sorting = dict(fixed)
    shifted_sorting["sorting_packaging_room"] = _rectangle(
        "sorting_packaging_room", (80_000, 40_000, 90_000, 50_000)
    )
    changed_sorting = placement._access_driven_tail_candidates(
        context, "CHANGING_MODULE", "changing_room", shifted_sorting, _one_bay()
    )
    changed_entrance_context = _tail_geometry_context()
    changed_entrance_context.main_entrance = ((200_000, 45_000), (200_000, 55_000))
    changed_entrance = placement._access_driven_tail_candidates(
        changed_entrance_context, "CHANGING_MODULE", "changing_room", fixed, _one_bay()
    )

    classes = {candidate.endpoint_event_class for candidate in candidates}
    assert {
        "SORTING_DIRECT",
        "ENTRANCE_DIRECT",
        "ENTRANCE_SORTING_BRIDGE",
        "CORRIDOR_MEDIATED",
    } <= classes
    assert {placement._module_signature(row.as_placements()) for row in candidates} != {
        placement._module_signature(row.as_placements()) for row in changed_sorting
    }
    assert {placement._module_signature(row.as_placements()) for row in candidates} != {
        placement._module_signature(row.as_placements()) for row in changed_entrance
    }
    assert all(set(dict(candidate.placements)) == {"changing_room"} for candidate in candidates)


@pytest.mark.parametrize(
    ("candidate_bounds", "expected"),
    (
        ((50_000, 125_000, 100_000, 175_000), ("WEST", 125_000, 175_000)),
        ((200_000, 125_000, 250_000, 175_000), ("EAST", 125_000, 175_000)),
        ((125_000, 50_000, 175_000, 100_000), ("SOUTH", 125_000, 175_000)),
        ((125_000, 200_000, 175_000, 250_000), ("NORTH", 125_000, 175_000)),
    ),
)
def test_sorting_side_branch_intervals_are_exact_and_side_labeled(
    candidate_bounds: tuple[int, int, int, int], expected: tuple[str, int, int]
) -> None:
    sorting = _rectangle("sorting_packaging_room", (100_000, 100_000, 200_000, 200_000))
    candidate = _rectangle("branch_zone", candidate_bounds)

    assert placement._sorting_shared_interval_mm(sorting, candidate) == expected


def _flexible_changing_context(
    entrance: tuple[tuple[int, int], tuple[int, int]],
) -> SimpleNamespace:
    context = _tail_geometry_context()
    context.main_entrance = entrance
    context.authorities["changing_room"] = {
        "zone_code": "changing_room",
        "dimension_mode": "FLEXIBLE_RECTANGLE",
        "required_area_m2": 40,
        "geometry": {"required_area_m2": 40},
    }
    return context


def test_changing_uses_p2c_flexible_dimension_domain_including_non_square_shapes() -> None:
    context = _flexible_changing_context(((200_000, 45_000), (200_000, 55_000)))

    shapes = placement._access_tail_dimension_shapes(context, "changing_room", {})
    non_square = [shape for shape in shapes if shape[0] != shape[1]]

    assert shapes
    assert non_square
    assert all(width * depth >= 40_000_000 for width, depth, *_ in shapes)
    assert len({(shape[0], shape[1], shape[2]) for shape in shapes}) == len(shapes)
    assert len({(shape[3], shape[4]) for shape in shapes}) == len(shapes)
    authority_shapes = placement._access_tail_authority_shape_signatures(
        context, "changing_room", {}
    )
    assert len(authority_shapes) > len(shapes)


@pytest.mark.parametrize(
    ("entrance", "sorting_bounds", "route_start"),
    (
        (
            ((200_000, 45_000), (200_000, 55_000)),
            (160_000, 45_000, 180_000, 55_000),
            (198_000, 50_000),
        ),
        (
            ((45_000, 200_000), (55_000, 200_000)),
            (45_000, 160_000, 55_000, 180_000),
            (50_000, 198_000),
        ),
    ),
)
def test_entrance_corridor_compatible_changing_seed_is_sorting_direct_and_not_boundary_touching(
    entrance: tuple[tuple[int, int], tuple[int, int]],
    sorting_bounds: tuple[int, int, int, int],
    route_start: tuple[int, int],
) -> None:
    context = _flexible_changing_context(entrance)
    context.main_entrance_route_start_points = (route_start,)
    sorting = _rectangle("sorting_packaging_room", sorting_bounds)

    candidates = placement._access_driven_tail_candidates(
        context,
        "CHANGING_MODULE",
        "changing_room",
        {"sorting_packaging_room": sorting},
        _one_bay(),
    )
    aligned = [
        dict(candidate.placements)["changing_room"]
        for candidate in candidates
        if candidate.endpoint_event_class == "ENTRANCE_CORRIDOR_COMPATIBLE_SORTING_DIRECT"
    ]

    assert aligned
    assert candidates[0].endpoint_event_class == ("ENTRANCE_CORRIDOR_COMPATIBLE_SORTING_DIRECT")
    for rectangle in aligned:
        left, bottom, right, top = rectangle.bounds_mm
        assert not (left <= route_start[0] <= right and bottom <= route_start[1] <= top)
        assert placement._shared_edge_length_mm(sorting, rectangle) >= 1_500
        assert placement._entrance_shared_length_mm(rectangle, entrance) == 0


@pytest.mark.parametrize(
    ("entrance", "sorting_bounds"),
    (
        (((200_000, 45_000), (200_000, 55_000)), (160_000, 45_000, 180_000, 55_000)),
        (((45_000, 200_000), (55_000, 200_000)), (45_000, 160_000, 55_000, 180_000)),
    ),
)
def test_changing_dual_endpoint_direct_supports_vertical_and_horizontal_entrances(
    entrance: tuple[tuple[int, int], tuple[int, int]],
    sorting_bounds: tuple[int, int, int, int],
) -> None:
    context = _flexible_changing_context(entrance)
    sorting = _rectangle("sorting_packaging_room", sorting_bounds)
    candidates = placement._access_driven_tail_candidates(
        context,
        "CHANGING_MODULE",
        "changing_room",
        {"sorting_packaging_room": sorting},
        _one_bay(),
    )
    dual = [
        dict(candidate.placements)["changing_room"]
        for candidate in candidates
        if candidate.endpoint_event_class == "ENTRANCE_SORTING_DUAL_DIRECT"
    ]

    assert dual
    assert all(placement._entrance_shared_length_mm(row, entrance) >= 1_500 for row in dual)
    assert all(placement._shared_edge_length_mm(sorting, row) >= 1_500 for row in dual)
    assert all(
        placement._site_module_is_usable(
            context, {"changing_room": row}, {"sorting_packaging_room": sorting}
        )
        for row in dual
    )
    entrance_clearance_spans = [
        min(placement._entrance_shared_length_mm(row, entrance), 2_000) for row in dual
    ]
    first = dual[0]
    first_clearance_span = min(placement._entrance_shared_length_mm(first, entrance), 2_000)
    first_sorting_span = placement._shared_edge_length_mm(sorting, first)
    assert first_clearance_span == max(entrance_clearance_spans)
    assert first_sorting_span == max(
        placement._shared_edge_length_mm(sorting, row)
        for row, entrance_span in zip(dual, entrance_clearance_spans, strict=True)
        if entrance_span == first_clearance_span
    )


def test_tail_capacity_cursor_continues_and_unresolved_is_not_s2_admissible(
    monkeypatch: Any,
) -> None:
    def validator(requirement: Any, **kwargs: Any) -> tuple[dict[str, Any], tuple[Any, ...]]:
        pair = f"{requirement['from_ref']}->{requirement['to_ref']}"
        changing = kwargs["zones"].get("changing_room")
        if pair == "main_entrance->changing_room" and changing is not None:
            bounds = changing.bounds_mm
            blocked = bounds[0] == 100_000
        else:
            bounds = kwargs["zones"].get("frozen_fruit_room")
            if pair == "sorting_packaging_room->frozen_fruit_room" and bounds is not None:
                blocked = True
            else:
                blocked = False
        status = "BLOCKED" if blocked else "PASS"
        return (
            {
                **requirement,
                "status": status,
                "codes": ["ROUTE_SEARCH_EXHAUSTED"] if blocked else [],
                "topology": "DIRECT_SHARED_EDGE",
            },
            (),
        )

    context = _tail_geometry_context(validator)
    context.node_budget = 120
    context.structural_topology = "STRAIGHT_LINEAR_BAND"
    context.structured_building_plan = SimpleNamespace(layout_family="LINEAR_3_BAND")
    main = {
        code: _rectangle(
            code,
            (index * 10_000, 0, (index + 1) * 10_000, 10_000),
        )
        for index, code in enumerate(
            (
                "raw_fruit_buffer",
                "primary_precooling_room",
                "sorting_packaging_room",
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
                "packaging_material_storage",
            )
        )
    }

    def seeded_candidates(
        _context: Any,
        module_name: str,
        zone_code: str,
        _fixed: Any,
        _bays: Any,
        **_kwargs: Any,
    ) -> tuple[placement.AccessDrivenTailCandidateV1, ...]:
        x_origins = {
            "CHANGING_MODULE": (100_000, 110_000),
            "SECONDARY_SUPPORT_MODULE": (120_000,),
            "FROZEN_SUPPORT_MODULE": (140_000,),
        }[module_name]
        return tuple(
            placement.AccessDrivenTailCandidateV1(
                module_name,
                ((zone_code, _rectangle(zone_code, (x, 100_000, x + 8_000, 110_000))),),
                (f"REQ:{module_name}",),
                "UNIT_TEST_ENDPOINT",
                "UNIT_TEST_DIRECT",
                True,
            )
            for x in x_origins
        )

    monkeypatch.setattr(placement, "_access_driven_tail_candidates", seeded_candidates)
    monkeypatch.setattr(
        placement,
        "_office_site_module_candidates",
        lambda *_args: ({"office": _rectangle("office", (160_000, 100_000, 168_000, 110_000))},),
    )
    stats = placement._PlacementSearchStats()

    first = tuple(
        placement._tail_access_capacity_preflight(
            context, (("main-a", main),), _one_bay(), stats, node_limit=1
        )
    )[-1]
    second = tuple(
        placement._tail_access_capacity_preflight(
            context, (("main-a", main),), _one_bay(), stats, node_limit=8
        )
    )[-1]
    identity = placement._tail_access_main_identity("main-a", main)
    changing_rows = [
        row
        for row in stats.tail_access_capacity_preflight_rows or []
        if row["module_name"] == "CHANGING_MODULE"
    ]

    assert first[identity] == "UNRESOLVED_COVERAGE"
    assert second[identity] == "TAIL_ACCESS_INCAPABLE_MAIN"
    assert [row["candidate_index"] for row in changing_rows] == [1, 2]
    assert len({row["zone_bounds_mm"]["changing_room"][0] for row in changing_rows}) == 2
    assert stats.tail_access_capacity_candidate_cursor_by_main[identity]["CHANGING_MODULE"] == 2
    assert stats.tail_access_capacity_continuation_count == 1
    assert placement._tail_access_main_is_s2_admissible("TAIL_ACCESS_CAPABLE_MAIN")
    assert not placement._tail_access_main_is_s2_admissible("UNRESOLVED_COVERAGE")
    assert not placement._tail_access_main_is_s2_admissible("TAIL_ACCESS_INCAPABLE_MAIN")


def test_sorting_and_shipping_independently_drive_tail_zone_origins() -> None:
    context = _tail_geometry_context()
    sorting_a = _rectangle("sorting_packaging_room", (30_000, 40_000, 40_000, 50_000))
    sorting_b = _rectangle("sorting_packaging_room", (90_000, 90_000, 100_000, 100_000))
    fixed_a = {"sorting_packaging_room": sorting_a}
    fixed_b = {"sorting_packaging_room": sorting_b}
    for module_name, zone_code in (
        ("SECONDARY_SUPPORT_MODULE", "secondary_fruit_buffer"),
        ("FROZEN_SUPPORT_MODULE", "frozen_fruit_room"),
    ):
        first = placement._access_driven_tail_candidates(
            context, module_name, zone_code, fixed_a, _one_bay()
        )
        second = placement._access_driven_tail_candidates(
            context, module_name, zone_code, fixed_b, _one_bay()
        )
        assert {placement._module_signature(row.as_placements()) for row in first} != {
            placement._module_signature(row.as_placements()) for row in second
        }

    shipping_a = _rectangle("shipping_channel", (70_000, 70_000, 80_000, 80_000))
    shipping_b = _rectangle("shipping_channel", (150_000, 150_000, 160_000, 160_000))
    office_a = placement._office_site_module_candidates(context, {"shipping_channel": shipping_a})
    office_b = placement._office_site_module_candidates(context, {"shipping_channel": shipping_b})
    assert {placement._module_signature(row) for row in office_a} != {
        placement._module_signature(row) for row in office_b
    }
    assert all(
        placement.rectangles_share_positive_edge(shipping_a, row["office"]) for row in office_a
    )


def test_office_and_changing_are_independent_site_modules() -> None:
    context = _tail_geometry_context()
    shipping = _rectangle("shipping_channel", (70_000, 70_000, 80_000, 80_000))
    sorting = _rectangle("sorting_packaging_room", (120_000, 70_000, 130_000, 80_000))
    office = _rectangle("office", (80_000, 70_000, 90_000, 80_000))
    fixed = {"shipping_channel": shipping, "sorting_packaging_room": sorting, "office": office}
    changing = placement._access_driven_tail_candidates(
        context, "CHANGING_MODULE", "changing_room", fixed, _one_bay()
    )

    assert changing
    assert all(set(dict(candidate.placements)) == {"changing_room"} for candidate in changing)
    assert any(
        not placement.rectangles_share_positive_edge(
            office, dict(candidate.placements)["changing_room"]
        )
        for candidate in changing
    )


def test_tail_access_capacity_skips_empty_module_domains_and_fairly_probes_remaining_mains(
    monkeypatch: Any,
) -> None:
    def validator(requirement: Any, **_kwargs: Any) -> tuple[dict[str, Any], tuple[Any, ...]]:
        return (
            {**requirement, "status": "PASS", "codes": [], "topology": "DIRECT_SHARED_EDGE"},
            (),
        )

    context = _tail_geometry_context(validator)
    context.node_budget = 120
    context.structural_topology = "STRAIGHT_LINEAR_BAND"
    context.structured_building_plan = SimpleNamespace(layout_family="LINEAR_3_BAND")
    mains = []
    for main_index in range(3):
        main = {
            code: _rectangle(
                code,
                (
                    index * 10_000,
                    main_index * 20_000,
                    (index + 1) * 10_000,
                    main_index * 20_000 + 10_000,
                ),
            )
            for index, code in enumerate(
                (
                    "raw_fruit_buffer",
                    "primary_precooling_room",
                    "sorting_packaging_room",
                    "secondary_precooling_room",
                    "coating_room",
                    "finished_goods_room",
                    "shipping_channel",
                    "packaging_material_storage",
                )
            )
        }
        mains.append((f"main-{main_index}", main))
    same_process_different_packaging = dict(mains[0][1])
    package = same_process_different_packaging["packaging_material_storage"]
    left, bottom, right, top = package.bounds_mm
    same_process_different_packaging["packaging_material_storage"] = _rectangle(
        "packaging_material_storage", (left, bottom + 1_000, right, top + 1_000)
    )
    mains.append(("main-0", same_process_different_packaging))

    def seeded_candidates(
        _context: Any,
        module_name: str,
        zone_code: str,
        _fixed: Any,
        _bays: Any,
        **_kwargs: Any,
    ) -> tuple[placement.AccessDrivenTailCandidateV1, ...]:
        offset = {
            "CHANGING_MODULE": 100_000,
            "SECONDARY_SUPPORT_MODULE": 120_000,
            "FROZEN_SUPPORT_MODULE": 140_000,
        }[module_name]
        rectangle = _rectangle(zone_code, (offset, 100_000, offset + 10_000, 110_000))
        return (
            placement.AccessDrivenTailCandidateV1(
                module_name,
                ((zone_code, rectangle),),
                (f"REQ:{module_name}",),
                "UNIT_TEST_ENDPOINT",
                "UNIT_TEST_DIRECT",
                True,
            ),
        )

    monkeypatch.setattr(placement, "_access_driven_tail_candidates", seeded_candidates)
    monkeypatch.setattr(
        placement,
        "_office_site_module_candidates",
        lambda _context, fixed: (
            ()
            if fixed["raw_fruit_buffer"].bounds_mm[1] == 0
            else ({"office": _rectangle("office", (160_000, 100_000, 170_000, 110_000))},)
        ),
    )
    stats = placement._PlacementSearchStats(site_module_assembly_trace=[])
    preflight_events = tuple(
        placement._tail_access_capacity_preflight(context, mains, _one_bay(), stats)
    )
    statuses = preflight_events[-1]

    rows = stats.tail_access_capacity_preflight_rows or []
    changing_round = [
        row["main_skeleton_hash"] for row in rows if row["module_name"] == "CHANGING_MODULE"
    ]
    assert changing_round == ["main-1", "main-2"]
    main_identities = {
        placement._tail_access_main_identity(main_hash, main) for main_hash, main in mains
    }
    incapable_identities = {placement._tail_access_main_identity(mains[0][0], mains[0][1])}
    duplicate_identity = placement._tail_access_main_identity("main-0", mains[-1][1])
    incapable_identities.add(duplicate_identity)
    capable_identities = main_identities - incapable_identities
    assert statuses == {
        **{identity: "TAIL_ACCESS_INCAPABLE_MAIN" for identity in incapable_identities},
        **{identity: "TAIL_ACCESS_CAPABLE_MAIN" for identity in capable_identities},
    }
    assert stats.tail_access_capacity_preflight_nodes_by_main == {
        identity: 4 for identity in capable_identities
    }
    assert len(stats.tail_access_capacity_route_cache or {}) == 6
    assert all(
        stats.tail_incapable_reason_by_main[identity] == ["OFFICE_MODULE"]
        for identity in incapable_identities
    )


def test_tail_access_main_identity_includes_packaging_anchor_geometry() -> None:
    main = {
        code: _rectangle(code, (index * 10_000, 0, (index + 1) * 10_000, 10_000))
        for index, code in enumerate(
            (
                "raw_fruit_buffer",
                "primary_precooling_room",
                "sorting_packaging_room",
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
                "shipping_channel",
            )
        )
    }
    first = {
        **main,
        "packaging_material_storage": _rectangle(
            "packaging_material_storage", (0, 20_000, 10_000, 30_000)
        ),
    }
    second = {
        **main,
        "packaging_material_storage": _rectangle(
            "packaging_material_storage", (20_000, 20_000, 30_000, 30_000)
        ),
    }

    assert placement._tail_access_main_identity("same-seven-zone-hash", first) != (
        placement._tail_access_main_identity("same-seven-zone-hash", second)
    )


def test_tail_capacity_round_reserves_only_within_the_existing_placement_budget() -> None:
    for budget in (0, 1, 12, 36, 120):
        reserve = placement._tail_access_capacity_round_reserve(budget)
        s1_ceiling = budget - reserve

        assert reserve >= 0
        assert s1_ceiling >= 0
        assert s1_ceiling + reserve == budget
    assert placement._tail_access_capacity_round_reserve(36) == 12
    assert placement._tail_access_capacity_round_reserve(120) == 12
