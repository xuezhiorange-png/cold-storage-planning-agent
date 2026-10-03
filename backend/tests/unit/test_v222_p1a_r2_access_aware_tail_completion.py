"""Exact route-aware admission for the structured S2 tail modules."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from cold_storage.modules.layout.domain import placement
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
        module_name="PERSONNEL_MODULE",
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
        "tail_module": "PERSONNEL_MODULE",
        "tail_candidate_index": 1,
        "placement_node_charged": True,
    }

    assert not placement._charge_tail_access_slot_node(
        context,
        stats,
        module_name="PERSONNEL_MODULE",
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


def test_exhausted_zero_access_personnel_domain_prunes_before_other_route_probes(
    monkeypatch: Any,
) -> None:
    route_pairs: list[str] = []
    geometry_calls: list[str] = []

    def validator(requirement: Any, **_kwargs: Any) -> tuple[dict[str, Any], tuple[Any, ...]]:
        pair = f"{requirement['from_ref']}->{requirement['to_ref']}"
        route_pairs.append(pair)
        return (
            {**requirement, "status": "BLOCKED", "codes": ["ROUTE_SEARCH_EXHAUSTED"]},
            (),
        )

    context = _access_context(validator)
    context.node_budget = 100
    context.structural_topology = "STRAIGHT_LINEAR_BAND"
    context.structured_building_plan = SimpleNamespace(layout_family="LINEAR_3_BAND")
    main = {
        code: _rectangle(code, (index * 10_000, 10_000, (index + 1) * 10_000, 20_000))
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
    personnel = {
        "office": _rectangle("office", (10_000, 30_000, 20_000, 40_000)),
        "changing_room": _rectangle("changing_room", (20_000, 30_000, 30_000, 40_000)),
    }

    monkeypatch.setattr(
        placement,
        "_personnel_site_module_candidates",
        lambda *_args: (personnel,),
    )

    def branch_candidate(context_arg: Any, code: str, *_args: Any) -> tuple[dict[str, Any], ...]:
        geometry_calls.append(code)
        return (
            {code: _rectangle(code, (70_000, 70_000, 80_000, 80_000))},
            {code: _rectangle(code, (70_000, 80_000, 80_000, 90_000))},
        )

    monkeypatch.setattr(placement, "_single_zone_site_module_candidates", branch_candidate)

    rows = tuple(
        placement._module_full_site_assemblies(
            context,
            main,
            (),
            limit=1,
            stats=placement._PlacementSearchStats(site_module_assembly_trace=[]),
        )
    )

    assert rows == (None,)
    assert route_pairs == ["changing_room->sorting_packaging_room"]
    assert set(geometry_calls) == {"secondary_fruit_buffer", "frozen_fruit_room"}


def test_personnel_module_is_synthesized_from_shipping_and_sorting_site_interfaces() -> None:
    bounds = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context = SimpleNamespace(
        authorities={
            code: {
                "zone_code": code,
                "dimension_mode": "FIXED_RECTANGLE",
                "required_area_m2": 100,
                "geometry": {"width_m": 10, "depth_m": 10, "required_area_m2": 100},
            }
            for code in ("office", "changing_room")
        },
        boundary=bounds,
        boundary_bounds=(0, 0, 100_000, 100_000),
        obstacles=(),
        main_entrance=((0, 45_000), (0, 55_000)),
    )
    shipping = _rectangle("shipping_channel", (50_000, 50_000, 60_000, 60_000))
    sorting_a = _rectangle("sorting_packaging_room", (30_000, 40_000, 40_000, 50_000))
    sorting_b = _rectangle("sorting_packaging_room", (10_000, 10_000, 20_000, 20_000))
    bay = placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000)

    candidates_a = placement._personnel_site_module_candidates(
        context, {"shipping_channel": shipping, "sorting_packaging_room": sorting_a}, (bay,)
    )
    candidates_b = placement._personnel_site_module_candidates(
        context, {"shipping_channel": shipping, "sorting_packaging_room": sorting_b}, (bay,)
    )
    signatures_a = {placement._module_signature(row) for row in candidates_a}
    signatures_b = {placement._module_signature(row) for row in candidates_b}

    assert candidates_a
    assert signatures_a != signatures_b
    assert all(
        placement.rectangles_share_positive_edge(shipping, row["office"]) for row in candidates_a
    )
    assert any(
        placement.rectangles_share_positive_edge(sorting_a, row["changing_room"])
        for row in candidates_a
    )
