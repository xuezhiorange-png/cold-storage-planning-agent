from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cold_storage.modules.layout.domain import placement
from cold_storage.modules.layout.domain.access_authority import (
    PACKAGING,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.structured_building import (
    BASE_LAYOUT_FAMILIES,
    CENTRAL_PROCESS_WITH_SIDE_BANKS,
    LINEAR_3_BAND,
    LONGITUDINAL_PROCESS_SPINE,
    RECTANGLE,
    SIMPLE_L,
)
from tests.evaluation.r2_local_composition_first import _p2d_footprint_regularity_facts


def _square_authorities() -> dict[str, dict[str, object]]:
    return {
        code: {
            "zone_code": code,
            "dimension_mode": "FIXED_RECTANGLE",
            "required_area_m2": 100,
            "geometry": {"width_m": 10, "depth_m": 10, "required_area_m2": 100},
        }
        for code in process_graph().nodes
    }


def _local_context() -> Any:
    return SimpleNamespace(authorities=_square_authorities(), graph=process_graph())


def test_each_family_uses_a_finite_local_composition_and_exact_main_must_chain() -> None:
    context = _local_context()
    synthesizers = {
        LINEAR_3_BAND: placement._synthesize_linear_3_band_local,
        CENTRAL_PROCESS_WITH_SIDE_BANKS: placement._synthesize_central_side_banks_local,
        LONGITUDINAL_PROCESS_SPINE: placement._synthesize_longitudinal_spine_local,
    }

    assert set(synthesizers) == set(BASE_LAYOUT_FAMILIES)
    for family in BASE_LAYOUT_FAMILIES:
        compositions = synthesizers[family](context, "X", "POSITIVE")
        assert compositions
        for composition in compositions:
            rectangles = composition.placements()
            assert set(rectangles) == set(placement.MAIN_PROCESS_ZONE_CODES)
            assert composition.layout_family == family
            assert composition.outline_class in {RECTANGLE, SIMPLE_L, "STAIR_STEP"}
            assert min(rectangle.bounds_mm[0] for rectangle in rectangles.values()) == 0
            assert min(rectangle.bounds_mm[1] for rectangle in rectangles.values()) == 0
            placement._validate_main_process_skeleton_graph(context.graph, rectangles)
            for code, rectangle in rectangles.items():
                others = {
                    other_code: other
                    for other_code, other in rectangles.items()
                    if other_code != code
                }
                assert placement._local_rectangles_clear(rectangle, others)


def test_support_and_personnel_are_jointly_composed_before_envelope_derivation() -> None:
    context = _local_context()
    main = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")[0]
    complete = placement._local_full_building_compositions(context, main, result_limit=1)

    assert complete
    composition = complete[0]
    rectangles = composition.placements()
    assert set(rectangles) == set(context.graph.nodes)
    assert composition.outline_class in {RECTANGLE, SIMPLE_L, "STAIR_STEP"}
    placement._validate_graph_completeness(context.graph, rectangles)

    plan = placement._structured_plan_from_composition(
        composition,
        rectangles,
        obstacles=(),
        site_bounds=(-100_000, -100_000, 100_000, 100_000),
    )
    assert plan.envelope.family == RECTANGLE
    assert plan.envelope.bounds_mm == composition.bounds_mm
    assert plan.envelope.bounds_mm != plan.envelope.site_bounds_mm
    assert plan.envelope.source_zone_union_outline_class == composition.outline_class
    assert plan.envelope.to_dict()["role"] == "PLANNED_COMPOSITION_ENVELOPE"
    assert plan.envelope.to_dict()["engineering_building_footprint_authority"] is False
    assert plan.envelope.components_mm == (composition.bounds_mm,)
    assert len(plan.zone_placements) == len(context.graph.nodes)


def test_branch_support_zones_are_independent_site_modules() -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    bays = (placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000),)

    for zone_code in ("secondary_fruit_buffer", "frozen_fruit_room"):
        options = placement._single_zone_site_module_candidates(context, zone_code, {}, bays)
        assert options
        assert all(set(option) == {zone_code} for option in options)
    assert "packaging_material_storage" not in {
        code
        for zone_code in ("secondary_fruit_buffer", "frozen_fruit_room")
        for option in placement._single_zone_site_module_candidates(context, zone_code, {}, bays)
        for code in option
    }


def test_finished_module_uses_finite_compact_2d_must_chain_packing() -> None:
    context = _local_context()
    chain = (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )

    modules = placement._local_must_chain_module_compositions(context, chain, result_limit=24)

    assert modules
    assert all(set(module) == set(chain) for module in modules)
    for module in modules:
        for first, second in zip(chain, chain[1:], strict=False):
            assert placement.rectangles_share_positive_edge(module[first], module[second])
        for code, rectangle in module.items():
            assert placement._local_rectangles_clear(
                rectangle, {other: row for other, row in module.items() if other != code}
            )
    assert any(
        len(
            {
                "X"
                if placement._adjacent_side(module[first], module[second]) in {"EAST", "WEST"}
                else "Y"
                for first, second in zip(chain, chain[1:], strict=False)
            }
        )
        > 1
        for module in modules
    )
    chain_side_patterns = {
        tuple(
            placement._adjacent_side(module[first], module[second])
            for first, second in zip(chain, chain[1:], strict=False)
        )
        for module in modules
    }
    assert ("WEST", "NORTH", "WEST") in chain_side_patterns
    assert tuple(placement._module_signature(module) for module in modules) == tuple(
        placement._module_signature(module)
        for module in placement._local_must_chain_module_compositions(
            context, chain, result_limit=24
        )
    )


def test_source_pair_representatives_preserve_finished_bank_topology_classes() -> None:
    context = _local_context()
    compositions = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    pairs = placement._main_module_source_pairs(context, compositions)
    raw_chain = ("raw_fruit_buffer", "primary_precooling_room")
    chain = (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )

    raw_modules = tuple(
        row[0] for row in placement._local_bank_compositions(context, raw_chain, result_limit=24)
    )
    finished_modules = placement._local_must_chain_module_compositions(
        context, chain, result_limit=24
    )
    catalog_pairs = placement._main_module_source_pairs(
        context,
        compositions,
        module_variants=(raw_modules, finished_modules),
    )
    raw_classes = {
        placement._module_construction_class_signature(
            module, interface_zone="primary_precooling_room", chain=raw_chain
        )
        for module in raw_modules
    }
    finished_classes = {
        placement._module_construction_class_signature(
            module, interface_zone="secondary_precooling_room", chain=chain
        )
        for module in finished_modules
    }
    paired_raw_classes = {
        placement._module_construction_class_signature(
            raw, interface_zone="primary_precooling_room", chain=raw_chain
        )
        for raw, _finished in pairs
    }
    paired_finished_classes = {
        placement._module_construction_class_signature(
            finished, interface_zone="secondary_precooling_room", chain=chain
        )
        for _raw, finished in pairs
    }

    assert 0 < len(pairs) <= 32
    assert tuple(
        (placement._module_signature(raw), placement._module_signature(finished))
        for raw, finished in catalog_pairs
    ) == tuple(
        (placement._module_signature(raw), placement._module_signature(finished))
        for raw, finished in pairs
    )
    assert raw_classes <= paired_raw_classes
    assert finished_classes <= paired_finished_classes
    finished_patterns = {
        tuple(
            placement._adjacent_side(module[first], module[second])
            for first, second in zip(chain, chain[1:], strict=False)
        )
        for _raw, module in pairs
    }
    assert ("WEST", "NORTH", "WEST") in finished_patterns


def test_site_pair_enumerates_all_rigid_transforms_without_truncating_module_classes() -> None:
    context = _local_context()
    compositions = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    pairs = placement._main_module_source_pairs(context, compositions)
    variant_rows = tuple(
        placement._balanced_site_module_pair_variants(raw, finished) for raw, finished in pairs
    )

    assert len(variant_rows) == len(pairs)
    for variants in variant_rows:
        signatures = {
            (placement._module_signature(raw), placement._module_signature(finished))
            for raw, finished in variants
        }
        assert len(variants) > 1
        assert len(signatures) == len(variants)


def test_finished_dock_order_compares_site_attached_geometry() -> None:
    context = _local_context()
    chain = (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    module = placement._local_must_chain_module_compositions(context, chain, result_limit=1)[0]
    sorting = placement._rectangle_from_mm(
        "sorting_packaging_room", 40_000, 30_000, 10_000, 10_000, 0
    )
    attached = placement._module_attached_to_zone(
        module, "secondary_precooling_room", sorting, "EAST", "CENTER"
    )

    assert attached is not None
    site_dock = attached["shipping_channel"]
    site_order = placement._finished_module_site_dock_order(
        module, sorting, "EAST", ("CENTER", "LOW", "HIGH"), (site_dock,)
    )
    local_origin_order = placement._finished_module_site_dock_order(
        module, sorting, "EAST", ("CENTER", "LOW", "HIGH"), (module["shipping_channel"],)
    )

    assert site_order[0:2] == (0, 0)
    assert local_origin_order[0] == 1
    assert site_order < local_origin_order


def test_changing_room_is_not_hard_bound_to_office_shared_edge() -> None:
    context = _local_context()
    main = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")[0]
    compositions = placement._local_full_building_compositions(context, main, result_limit=48)

    assert compositions
    assert any(
        placement._adjacent_side(
            composition.placements()["office"], composition.placements()["changing_room"]
        )
        is None
        for composition in compositions
    )


def test_stair_step_zone_union_is_diagnostic_and_not_a_planned_envelope_gate() -> None:
    context = _local_context()
    positions_mm = {
        "raw_fruit_buffer": (0, 0),
        "primary_precooling_room": (10000, 0),
        "sorting_packaging_room": (20000, 0),
        "secondary_precooling_room": (20000, 10000),
        "coating_room": (30000, 10000),
        "finished_goods_room": (40000, 10000),
        "shipping_channel": (50000, 10000),
        "packaging_material_storage": (0, 20000),
        "secondary_fruit_buffer": (10000, 20000),
        "frozen_fruit_room": (20000, 20000),
        "office": (60000, 10000),
        "changing_room": (70000, 10000),
    }
    placements = {
        code: placement._rectangle_from_mm(code, *positions_mm[code], 10000, 10000, 0)
        for code in context.graph.nodes
    }
    placement._validate_graph_completeness(context.graph, placements)
    assert placement._local_outline_class(placements)[0] == "STAIR_STEP"

    composition = placement.LocalBuildingCompositionV1(
        LINEAR_3_BAND,
        "X",
        "POSITIVE",
        tuple(
            placement.LocalZonePlacementV1(code, placement.zone_band_assignment(code), rectangle)
            for code, rectangle in sorted(placements.items())
        ),
        tuple(context.graph.must_adjacencies),
        outline_class="STAIR_STEP",
        bounds_mm=(0, 0, 80000, 30000),
    )
    plan = placement._structured_plan_from_composition(
        composition,
        placements,
        obstacles=(),
        site_bounds=(-10000, -10000, 10000, 10000),
    )

    assert plan.envelope.bounds_mm == (0, 0, 80000, 30000)
    void_probe = placement._rectangle_from_mm("void_probe", 40000, 20000, 10000, 10000, 0)
    assert plan.envelope.contains(void_probe)
    assert plan.envelope.source_zone_union_outline_class == "STAIR_STEP"
    assert len(plan.zone_placements) == len(context.graph.nodes)


def test_local_shape_combinations_are_finite_and_deterministic() -> None:
    options = tuple((width, width + 1, 0, width, width + 1) for width in (10, 20, 30))
    shape_options = tuple(options for _ in placement.MAIN_PROCESS_ZONE_CODES)

    first = placement._bounded_local_shape_rows(shape_options)
    second = placement._bounded_local_shape_rows(shape_options)

    assert first == second
    assert len(first) == placement.LOCAL_COMPOSITION_SHAPE_VARIANT_LIMIT
    assert len(first) < 3 ** len(shape_options)


def test_partial_and_complete_local_compositions_use_only_site_extent_pruning() -> None:
    context = _local_context()
    context.boundary_bounds = (0, 0, 30_000, 30_000)
    candidates = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")

    assert candidates
    assert all(
        placement._local_bbox_fits_site_extents(context, row.placements()) for row in candidates
    )
    assert all(
        max(row.bounds_mm[2] for row in composition.placements().values()) <= 30_000
        and max(row.bounds_mm[3] for row in composition.placements().values()) <= 30_000
        for composition in candidates
    )


def test_bbox_necessary_condition_accepts_only_normal_or_whole_building_rotated_fit() -> None:
    context = _local_context()
    rectangle = placement._rectangle_from_mm("probe", 0, 0, 40_000, 20_000, 0)
    context.boundary_bounds = (0, 0, 20_000, 40_000)
    assert placement._local_bbox_fits_site_extents(context, {"probe": rectangle})

    context.boundary_bounds = (0, 0, 19_999, 40_000)
    assert not placement._local_bbox_fits_site_extents(context, {"probe": rectangle})


def test_compact_state_retention_preserves_distinct_corner_occupancy() -> None:
    context = SimpleNamespace(boundary_bounds=(0, 0, 30_000, 30_000))
    without_northeast = {
        "sw": placement._rectangle_from_mm("sw", 0, 0, 8_000, 8_000, 0),
        "nw": placement._rectangle_from_mm("nw", 0, 12_000, 8_000, 8_000, 0),
        "se": placement._rectangle_from_mm("se", 12_000, 0, 8_000, 8_000, 0),
    }
    with_all_corners = {
        **without_northeast,
        "ne": placement._rectangle_from_mm("ne", 12_000, 12_000, 8_000, 8_000, 0),
    }

    retained = placement._retain_compact_local_states(
        (without_northeast, with_all_corners), context, "X", 2
    )

    assert len(retained) == 2
    assert {placement._local_quadrant_occupancy_signature(state) for state in retained} == {
        (True, True, True, False),
        (True, True, True, True),
    }
    assert len({placement._local_grid_occupancy_signature(state) for state in retained}) == 2
    first_corner_representative = placement._retain_compact_local_states(
        (without_northeast, with_all_corners), context, "X", 1
    )
    assert placement._local_quadrant_occupancy_signature(first_corner_representative[0]) == (
        True,
        True,
        True,
        False,
    )


def test_compact_embedding_keeps_all_main_must_interfaces_and_is_deterministic() -> None:
    context = _local_context()
    context.boundary_bounds = (0, 0, 30_000, 30_000)
    first = placement._synthesize_central_side_banks_local(context, "X", "POSITIVE")
    second = placement._synthesize_central_side_banks_local(context, "X", "POSITIVE")

    assert first
    assert first == second
    for composition in first:
        rectangles = composition.placements()
        placement._validate_main_process_skeleton_graph(context.graph, rectangles)
        assert placement._local_bbox_fits_site_extents(context, rectangles)
        assert placement._adjacent_side(
            rectangles["sorting_packaging_room"], rectangles["primary_precooling_room"]
        ) != placement._adjacent_side(
            rectangles["sorting_packaging_room"], rectangles["secondary_precooling_room"]
        )


def test_rigid_site_placement_rect_fast_path_matches_exact_rectangle_predicates() -> None:
    boundary = ((0, 0), (20_000, 0), (20_000, 20_000), (0, 20_000))
    obstacle = ((8_000, 8_000), (12_000, 8_000), (12_000, 12_000), (8_000, 12_000))
    context = SimpleNamespace(
        boundary=boundary,
        boundary_bounds=(0, 0, 20_000, 20_000),
        obstacles=(obstacle,),
        main_entrance=((20_000, 9_000), (20_000, 11_000)),
        site_body={
            "entrances": {
                "truck_entrance": {
                    "start": {"x": 0, "y": 9},
                    "end": {"x": 0, "y": 11},
                }
            }
        },
    )
    local = {"probe": placement._rectangle_from_mm("probe", 0, 0, 6_000, 6_000, 0)}

    candidates = placement._whole_building_site_placements(context, local, result_limit=24)

    assert candidates
    assert all(
        placement._rectangle_is_usable(
            candidate["probe"], {}, context.boundary, context.boundary_bounds, context.obstacles
        )
        for candidate in candidates
    )


def test_rigid_site_placement_includes_first_clear_integer_mm_after_closed_obstacle() -> None:
    boundary = ((0, 0), (20_000, 0), (20_000, 20_000), (0, 20_000))
    obstacle = ((0, 0), (12_000, 0), (12_000, 20_000), (0, 20_000))
    context = SimpleNamespace(
        boundary=boundary,
        boundary_bounds=(0, 0, 20_000, 20_000),
        obstacles=(obstacle,),
        main_entrance=((20_000, 9_000), (20_000, 11_000)),
        site_body={
            "entrances": {
                "truck_entrance": {
                    "start": {"x": 0, "y": 9},
                    "end": {"x": 0, "y": 11},
                }
            }
        },
    )
    local = {"probe": placement._rectangle_from_mm("probe", 0, 0, 7_999, 6_000, 0)}

    candidates = placement._whole_building_site_placements(context, local, result_limit=24)

    assert candidates
    assert any(candidate["probe"].bounds_mm[0] == 12_001 for candidate in candidates)
    assert all(
        placement._rectangle_is_usable(
            candidate["probe"], {}, context.boundary, context.boundary_bounds, context.obstacles
        )
        for candidate in candidates
    )


def test_visual_regularity_uses_authoritative_p2d_footprint_not_zone_union() -> None:
    candidate = {
        "zones": [
            {
                "zone_code": "a",
                "x": "0",
                "y": "0",
                "width_m": "1",
                "depth_m": "1",
                "rotation_deg": 0,
            },
            {
                "zone_code": "b",
                "x": "1",
                "y": "0",
                "width_m": "1",
                "depth_m": "1",
                "rotation_deg": 0,
            },
            {
                "zone_code": "c",
                "x": "1",
                "y": "1",
                "width_m": "1",
                "depth_m": "1",
                "rotation_deg": 0,
            },
        ]
    }
    p2d_result = {
        "building_footprint": {
            "source": "EXACT_ZONE_RECTANGLES_PLUS_ACCESS_CORRIDOR_ENVELOPES",
            "footprint": {
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 2, "y": 0},
                    {"x": 2, "y": 2},
                    {"x": 0, "y": 2},
                    {"x": 0, "y": 0},
                ]
            },
        }
    }

    facts = _p2d_footprint_regularity_facts(candidate, p2d_result)

    assert facts["local_zone_union_outline_class"] == SIMPLE_L
    assert facts["p2d_building_footprint_outline_class"] == RECTANGLE
    assert facts["visual_regularity_pass"] is True
    assert facts["p2d_building_footprint_source"] == (
        "EXACT_ZONE_RECTANGLES_PLUS_ACCESS_CORRIDOR_ENVELOPES"
    )


def test_structured_candidate_stream_does_not_call_site_first_or_room_chain_generators() -> None:
    source = Path(placement.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_direct_structured_candidates"
    )
    called = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "construct_structured_building_plan_v1" not in called
    assert "synthesize_band_geometry" not in called
    assert "synthesize_must_chain_band_geometry" not in called
    assert "_direct_family_tail_zones" not in called
    assert "_whole_building_site_placements" in called
    assert "_structured_plan_from_composition" in called


def test_orthogonal_buildable_bays_are_exact_deterministic_and_obstacle_derived() -> None:
    boundary = ((0, 0), (20_000, 0), (20_000, 20_000), (0, 20_000))
    obstacle = ((8_000, 5_000), (12_000, 5_000), (12_000, 15_000), (8_000, 15_000))
    site_body = {
        "entrances": {
            "truck_entrance": {
                "start": {"x": 0, "y": 9},
                "end": {"x": 0, "y": 11},
            }
        }
    }
    context = SimpleNamespace(
        boundary=boundary,
        boundary_bounds=(0, 0, 20_000, 20_000),
        obstacles=(obstacle,),
        main_entrance=((20_000, 9_000), (20_000, 11_000)),
        site_body=site_body,
    )

    first = placement._orthogonal_site_buildable_bays(context)
    second = placement._orthogonal_site_buildable_bays(context)

    assert first
    assert first == second
    assert all(row.area_mm2 < 20_000 * 20_000 for row in first)
    for bay in first:
        left, bottom, right, top = bay.bounds_mm
        rectangle = placement._rectangle_from_mm(
            "bay-test", left, bottom, right - left, top - bottom, 0
        )
        assert placement.rectangle_inside_polygon(rectangle, boundary)
        assert not placement.rectangle_intersects_closed_obstacle(rectangle, obstacle)


def test_orthogonal_bays_include_maximal_regions_across_partition_strips() -> None:
    boundary = ((0, 0), (20_000, 0), (20_000, 20_000), (0, 20_000))
    obstacle = ((8_000, 5_000), (12_000, 5_000), (12_000, 15_000), (8_000, 15_000))
    context = SimpleNamespace(
        boundary=boundary,
        boundary_bounds=(0, 0, 20_000, 20_000),
        obstacles=(obstacle,),
        main_entrance=((20_000, 9_000), (20_000, 11_000)),
        site_body={
            "entrances": {
                "truck_entrance": {
                    "start": {"x": 0, "y": 9},
                    "end": {"x": 0, "y": 11},
                }
            }
        },
    )

    bays = placement._orthogonal_site_buildable_bays(context)
    bounds = {bay.bounds_mm for bay in bays}

    assert (0, 0, 7_999, 20_000) in bounds
    assert (12_001, 0, 20_000, 20_000) in bounds
    assert (0, 0, 20_000, 4_999) in bounds
    assert (0, 15_001, 20_000, 20_000) in bounds
    assert len({bay.bay_id for bay in bays}) == len(bays)
    assert any(bay.bay_role == "CONNECTIVITY_PARTITION_REGION" for bay in bays)


def test_maximal_bays_preserve_real_shared_interface_adjacency() -> None:
    boundary = (
        (0, 0),
        (20_000, 0),
        (20_000, 10_000),
        (10_000, 10_000),
        (10_000, 20_000),
        (0, 20_000),
    )
    context = SimpleNamespace(
        boundary=boundary,
        boundary_bounds=(0, 0, 20_000, 20_000),
        obstacles=(),
        main_entrance=((20_000, 4_000), (20_000, 6_000)),
        site_body={
            "entrances": {
                "truck_entrance": {
                    "start": {"x": 0, "y": 4},
                    "end": {"x": 0, "y": 6},
                }
            }
        },
    )

    bays = placement._orthogonal_site_buildable_bays(context)

    assert len([bay for bay in bays if bay.bay_role == "MAXIMAL_PLACEMENT_REGION"]) == 2
    assert any(bay.adjacent_bay_ids for bay in bays)
    assert any(bay.shared_interface_segments for bay in bays)


def test_module_rigid_transforms_preserve_internal_must_interface() -> None:
    module = {
        "raw_fruit_buffer": placement._rectangle_from_mm(
            "raw_fruit_buffer", 0, 0, 10_000, 8_000, 0
        ),
        "primary_precooling_room": placement._rectangle_from_mm(
            "primary_precooling_room", 10_000, 0, 8_000, 8_000, 0
        ),
    }

    variants = placement._rigid_module_variants(module)

    assert variants
    assert all(
        placement.rectangles_share_positive_edge(
            row["raw_fruit_buffer"], row["primary_precooling_room"]
        )
        for row in variants
    )
    assert all(set(row) == set(module) for row in variants)
    site_variants = placement._site_assembly_module_variants(module)
    assert any(
        row["raw_fruit_buffer"].rotation_deg == 90
        or row["primary_precooling_room"].rotation_deg == 90
        for row in site_variants
    )
    assert len(site_variants) == len(variants)


def test_site_translation_events_align_interface_zones_to_bays() -> None:
    placements = {
        "sorting_packaging_room": placement._rectangle_from_mm(
            "sorting_packaging_room", 0, 0, 10_000, 20_000, 0
        ),
        "primary_precooling_room": placement._rectangle_from_mm(
            "primary_precooling_room", -8_000, 5_000, 8_000, 10_000, 0
        ),
        "secondary_precooling_room": placement._rectangle_from_mm(
            "secondary_precooling_room", 10_000, 5_000, 8_000, 10_000, 0
        ),
    }
    bay = placement.BuildableBayV1("BAY-0001", (30_000, 40_000, 70_000, 80_000), 1_600_000_000)

    translations = placement._site_translations_from_bay_edges(placements, (bay,))

    assert (30_000, 40_000) in translations
    assert (38_000, 35_000) in translations


def test_site_translation_events_include_existing_truck_dock_template_points() -> None:
    shipping = placement._rectangle_from_mm("shipping_channel", 10_000, 20_000, 7_693, 6_050, 0)
    placements = {"shipping_channel": shipping}
    bay = placement.BuildableBayV1("BAY-0001", (0, 0, 75_460, 55_000), 4_150_300_000)
    site_body = {
        "site": {"preferred_loading_side": "UNSPECIFIED"},
        "entrances": {
            "truck_entrance": {
                "start": {"x": 0, "y": 33.7},
                "end": {"x": 0, "y": 33.701},
            }
        },
    }
    dock_point = (1_624, 33_700)
    face = placement._loading_face(shipping, site_body)[1]
    face_points = (
        face[0],
        face[1],
        ((face[0][0] + face[1][0]) // 2, (face[0][1] + face[1][1]) // 2),
    )
    expected_dock_translations = {
        (dock_point[0] - point[0], dock_point[1] - point[1]) for point in face_points
    }

    translations = placement._site_translations_from_bay_edges(
        placements,
        (bay,),
        site_body=site_body,
        truck_dock_points=(dock_point,),
    )

    assert expected_dock_translations <= set(translations)
    assert any(
        placement._on_segment(
            dock_point,
            placement._loading_face(
                placement._translate_module(placements, dx, dy)["shipping_channel"],
                site_body,
            )[1][0],
            placement._loading_face(
                placement._translate_module(placements, dx, dy)["shipping_channel"],
                site_body,
            )[1][1],
        )
        for dx, dy in translations
    )

    authoritative_event_placement = placement._rectangle_from_mm(
        "shipping_channel", 1_624, 33_700, 7_693, 6_050, 0
    )
    event_translations = placement._site_translations_from_bay_edges(
        placements,
        (bay,),
        site_body=site_body,
        shipping_dock_placements=(authoritative_event_placement,),
    )
    assert event_translations[0] == (-8_376, 13_700)


def test_site_event_rectangle_sampling_is_finite_canonical_and_spread() -> None:
    events = tuple(
        placement._rectangle_from_mm("shipping_channel", index, index * 2, 3_000, 4_000, 0)
        for index in range(40)
    )

    sampled = placement._bounded_site_event_rectangles(events, limit=5)

    assert len(sampled) == 5
    assert sampled == placement._bounded_site_event_rectangles(tuple(reversed(events)), limit=5)
    assert sampled[0].bounds_mm == min(row.bounds_mm for row in events)
    assert sampled[-1].bounds_mm == max(row.bounds_mm for row in events)


def test_site_module_assembly_keeps_modules_rigid_and_avoids_whole_body_translation(
    monkeypatch: Any,
) -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    context.authorities["sorting_packaging_room"]["geometry"] = {
        "width_m": 13.6,
        "depth_m": 45.76,
        "required_area_m2": 622.336,
    }
    context.authorities["sorting_packaging_room"]["required_area_m2"] = 622.336
    context.main_entrance = ((100_000, 45_000), (100_000, 55_000))
    context.site_body = {
        "entrances": {
            "truck_entrance": {
                "start": {"x": 0, "y": 45},
                "end": {"x": 0, "y": 55},
            }
        }
    }
    main = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    bays = (placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000),)
    stats = placement._PlacementSearchStats()

    def reject_whole_body_translation(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("module site assembly must not translate the whole 7-zone body")

    monkeypatch.setattr(placement, "_whole_building_site_placements", reject_whole_body_translation)

    candidates = tuple(
        row
        for row in placement._module_main_site_assemblies(
            context,
            main,
            LINEAR_3_BAND,
            "X",
            "POSITIVE",
            bays,
            limit=4,
            stats=stats,
        )
        if row is not None
    )

    assert candidates
    assert len(candidates) > 2
    assert all(
        set(row) == {*placement.MAIN_PROCESS_ZONE_CODES, "packaging_material_storage"}
        for row in candidates
    )
    signatures = {placement._module_signature(row) for row in candidates}
    assert len(signatures) == len(candidates)
    assert len(
        {
            (
                row["packaging_material_storage"].bounds_mm,
                row["packaging_material_storage"].rotation_deg,
            )
            for row in candidates
        }
    ) == len(candidates)
    for candidate in candidates:
        placement._validate_main_process_skeleton_graph(
            context.graph,
            {code: candidate[code] for code in placement.MAIN_PROCESS_SKELETON_ZONE_CODES},
        )
        package = candidate["packaging_material_storage"]
        assert placement.rectangle_inside_polygon(package, context.boundary)
        assert all(
            not placement.rectangles_overlap(package, candidate[code])
            for code in placement.MAIN_PROCESS_SKELETON_ZONE_CODES
        )
    assert stats.packaging_anchor_sorting_rotation_attempts_by_group is not None
    construction_anchor_ids = {
        anchor.anchor_id for anchor in stats.site_packaging_construction_anchors or ()
    }
    assert construction_anchor_ids
    assert all(
        stats.packaging_anchor_sorting_rotation_attempts_by_group[anchor_id] == {"0", "90"}
        for anchor_id in construction_anchor_ids
    )


def test_critical_eight_zone_assembly_can_complete_with_site_valid_personnel_slot() -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    context.main_entrance = ((100_000, 45_000), (100_000, 55_000))
    context.site_body = {
        "entrances": {
            "truck_entrance": {
                "start": {"x": 0, "y": 45},
                "end": {"x": 0, "y": 55},
            }
        }
    }
    main_compositions = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    bays = (placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000),)
    stats = placement._PlacementSearchStats(site_module_assembly_trace=[])
    critical_candidates = tuple(
        row
        for row in placement._module_main_site_assemblies(
            context,
            main_compositions,
            LINEAR_3_BAND,
            "X",
            "POSITIVE",
            bays,
            limit=4,
            stats=stats,
        )
        if row is not None
    )
    assert critical_candidates
    # The first authoritative package anchors are deliberately on a bay edge.
    # Translate the complete 8-zone assembly as one rigid test fixture so this
    # unit isolates S2 tail completion with free space around the shipping
    # face; production site assembly still owns the actual anchor/placement.
    tail_fixture = placement._translate_module(critical_candidates[0], 30_000, 30_000)
    completed = tuple(
        complete
        for complete in placement._module_full_site_assemblies(
            context, tail_fixture, bays, limit=1, stats=stats
        )
        if complete is not None
    )
    assert completed
    assert set(process_graph().nodes) <= set(completed[0])
    assert placement._site_module_is_usable(context, completed[0], {})


def test_s1_continues_same_source_pair_after_packaging_slot_rejection(
    monkeypatch: Any,
) -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    context.main_entrance = ((100_000, 45_000), (100_000, 55_000))
    context.site_body = {
        "entrances": {
            "truck_entrance": {
                "start": {"x": 0, "y": 45},
                "end": {"x": 0, "y": 55},
            }
        }
    }
    main = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    source_pair = placement._main_module_source_pairs(context, main)
    bays = (placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000),)
    real_preflight = placement._packaging_tail_slot_preflight_for_rectangles
    preflight_calls = 0

    def reject_first_geometry(
        preflight_context: Any,
        fixed_rectangles: Any,
    ) -> dict[str, Any]:
        nonlocal preflight_calls
        preflight_calls += 1
        result = real_preflight(preflight_context, fixed_rectangles)
        if preflight_calls == 1:
            return {**result, "legal_slot_exists": False}
        return result

    monkeypatch.setattr(
        placement,
        "_packaging_tail_slot_preflight_for_rectangles",
        reject_first_geometry,
    )
    stats = placement._PlacementSearchStats()

    candidates = tuple(
        row
        for row in placement._module_main_site_assemblies(
            context,
            main,
            LINEAR_3_BAND,
            "X",
            "POSITIVE",
            bays,
            limit=1,
            source_pairs=source_pair,
            stats=stats,
        )
        if row is not None
    )

    counts = stats.site_main_assembly_counts_by_family[LINEAR_3_BAND]
    assert preflight_calls >= 2
    assert 1 <= len(candidates) <= 4
    main_signatures = {
        placement._module_signature(
            {code: candidate[code] for code in placement.MAIN_PROCESS_SKELETON_ZONE_CODES}
        )
        for candidate in candidates
    }
    assert len(main_signatures) == 1
    assert counts["raw_site_valid_main_count"] >= 2
    assert counts["packaging_slot_rejected_main_count"] == 1
    assert counts["tail_capable_main_count"] == 1
    assert stats.site_main_source_pair_rows[-1]["result"] == "PACKAGING_RESERVED_MAIN_LIMIT_REACHED"
    assert stats.site_main_source_pair_rows[-1]["source_pair_exhausted"] is False


def test_source_pair_is_marked_tail_capacity_exhausted_after_exact_slot_negatives(
    monkeypatch: Any,
) -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    context.main_entrance = ((100_000, 45_000), (100_000, 55_000))
    context.site_body = {
        "entrances": {
            "truck_entrance": {
                "start": {"x": 0, "y": 45},
                "end": {"x": 0, "y": 55},
            }
        }
    }
    main = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    source_pair = placement._main_module_source_pairs(context, main)
    bays = (placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000),)

    def no_packaging_slot(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "legal_slot_exists": False,
            "proof_mode": placement.EXACT_ORTHOGONAL_EVENT_ENUMERATION,
            "first_witness_rectangle": None,
        }

    monkeypatch.setattr(
        placement,
        "_packaging_tail_slot_preflight_for_rectangles",
        no_packaging_slot,
    )
    stats = placement._PlacementSearchStats()
    candidates = tuple(
        row
        for row in placement._module_main_site_assemblies(
            context,
            main,
            LINEAR_3_BAND,
            "X",
            "POSITIVE",
            bays,
            limit=1,
            source_pairs=source_pair,
            stats=stats,
        )
        if row is not None
    )

    counts = stats.site_main_assembly_counts_by_family[LINEAR_3_BAND]
    assert candidates == ()
    assert counts["raw_site_valid_main_count"] > 0
    assert counts["packaging_slot_rejected_main_count"] == counts["raw_site_valid_main_count"]
    assert counts["tail_capable_main_count"] == 0
    assert any(
        row["result"] == "SOURCE_PAIR_TAIL_CAPACITY_EXHAUSTED"
        and row["tail_capacity_exhausted"] is True
        for row in stats.site_main_source_pair_rows
    )


def test_exact_packaging_preflight_is_cached_by_distinct_main_geometry(
    monkeypatch: Any,
) -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    context.main_entrance = ((100_000, 45_000), (100_000, 55_000))
    context.site_body = {
        "entrances": {
            "truck_entrance": {
                "start": {"x": 0, "y": 45},
                "end": {"x": 0, "y": 55},
            }
        }
    }
    main = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    source_pair = placement._main_module_source_pairs(context, main)[:1]
    bays = (placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000),)
    preflight_calls = 0
    real_preflight = placement._packaging_tail_slot_preflight_for_rectangles

    def count_exact_slot_checks(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal preflight_calls
        preflight_calls += 1
        return real_preflight(*args, **kwargs)

    monkeypatch.setattr(
        placement,
        "_packaging_tail_slot_preflight_for_rectangles",
        count_exact_slot_checks,
    )
    stats = placement._PlacementSearchStats()
    run_args = (
        context,
        main,
        LINEAR_3_BAND,
        "X",
        "POSITIVE",
        bays,
    )
    first = tuple(
        row
        for row in placement._module_main_site_assemblies(
            *run_args,
            limit=1,
            source_pairs=source_pair,
            stats=stats,
        )
        if row is not None
    )
    second = tuple(
        row
        for row in placement._module_main_site_assemblies(
            *run_args,
            limit=1,
            source_pairs=source_pair,
            stats=stats,
        )
        if row is not None
    )

    counts = stats.site_main_assembly_counts_by_family[LINEAR_3_BAND]
    assert first and second
    assert placement._module_signature(first[0]) == placement._module_signature(second[0])
    assert preflight_calls == 1
    assert counts["raw_site_valid_main_count"] == 1
    assert counts["tail_capable_main_count"] == 1
    assert (
        sum(
            row.get("preflight_reused") is True
            for row in stats.site_module_assembly_trace or ()
            if row.get("stage") == "S1_PACKAGING_RESERVED_MAIN_PREFLIGHT"
        )
        == 1
    )


def test_family_core_faces_cover_opposite_banks_and_linear_one_bend() -> None:
    linear = placement._family_core_face_pairs(LINEAR_3_BAND, "Y", "POSITIVE")
    central = placement._family_core_face_pairs(CENTRAL_PROCESS_WITH_SIDE_BANKS, "Y", "POSITIVE")

    assert linear[0] == ("SOUTH", "NORTH")
    assert ("WEST", "EAST") in linear
    assert ("WEST", "NORTH") in linear
    assert ("NORTH", "NORTH") in linear
    assert ("SOUTH", "SOUTH") in linear
    assert all(first != second for first, second in central)
    assert {"WEST", "EAST"} <= {side for pair in central for side in pair}
    spine = placement._family_core_face_pairs(LONGITUDINAL_PROCESS_SPINE, "X", "POSITIVE")
    assert ("EAST", "EAST") in spine


def test_packaging_anchor_changes_sorting_root_candidates_and_covers_rotations() -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    context.authorities["sorting_packaging_room"]["geometry"] = {
        "width_m": 13.6,
        "depth_m": 45.76,
        "required_area_m2": 622.336,
    }
    context.authorities["sorting_packaging_room"]["required_area_m2"] = 622.336
    packaging_profile = resolve_access_profile(PACKAGING)
    context.access_requirements = (
        {
            "from_ref": "packaging_material_storage",
            "to_ref": "sorting_packaging_room",
            "profile_identity": PACKAGING,
            "route_shape_constraint": "STRAIGHT_ONLY",
            "construction_portal_clear_width_m": str(packaging_profile.portal_clear_width_m),
            "construction_corridor_clear_width_m": str(packaging_profile.corridor_clear_width_m),
        },
    )
    first_anchor = placement.PackagingAnchorV1(
        "PACKAGING-0-10000-10000",
        "BAY-0001",
        placement._rectangle_from_mm(
            "packaging_material_storage", 10_000, 10_000, 17_300, 14_500, 0
        ),
    )
    second_anchor = placement.PackagingAnchorV1(
        "PACKAGING-0-50000-10000",
        "BAY-0001",
        placement._rectangle_from_mm(
            "packaging_material_storage", 50_000, 10_000, 17_300, 14_500, 0
        ),
    )
    bay = placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 40_000), 4_000_000_000)
    stats = placement._PlacementSearchStats()

    first_roots = placement._packaging_driven_sorting_roots(
        context, first_anchor, bays=(bay,), stats=stats
    )
    second_roots = placement._packaging_driven_sorting_roots(
        context, second_anchor, bays=(bay,), stats=stats
    )

    first_geometry = {root.bounds_mm + (root.rotation_deg,) for root, *_ in first_roots}
    second_geometry = {root.bounds_mm + (root.rotation_deg,) for root, *_ in second_roots}
    assert first_geometry and second_geometry
    assert first_geometry != second_geometry
    assert stats.packaging_anchor_sorting_rotation_attempts_by_group == {
        first_anchor.anchor_id: {"0", "90"},
        second_anchor.anchor_id: {"0", "90"},
    }
    assert any(witness["gap_mm"] == 5_000 for *_prefix, witness in first_roots)
    assert any(witness["gap_event"].startswith("BAY-") for *_prefix, witness in first_roots)
    assert any(
        witness["alignment_source"] == "PRIMARY_PRECOOLING_ROOM_DIMENSION_EVENT"
        for *_prefix, witness in first_roots
    )
    assert all(witness["final_p2d_route_validated"] is False for *_prefix, witness in first_roots)


def test_packaging_construction_representatives_interleave_anchor_rotations() -> None:
    context = _local_context()
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    bay = placement.BuildableBayV1("BAY-0001", context.boundary_bounds, 10_000_000_000)
    anchors: list[placement.PackagingAnchorV1] = []
    for rotation, width, depth in ((0, 17_300, 14_500), (90, 14_500, 17_300)):
        positions = (
            (0, 0),
            ((100_000 - width) // 2, 0),
            ((100_000 - width) // 2, (100_000 - depth) // 2),
        )
        for index, (left, bottom) in enumerate(positions):
            anchor_id = f"PACKAGING-{rotation}-{index}"
            anchors.append(
                placement.PackagingAnchorV1(
                    anchor_id,
                    bay.bay_id,
                    placement._rectangle_from_mm(
                        "packaging_material_storage",
                        left,
                        bottom,
                        17_300,
                        14_500,
                        rotation,
                    ),
                )
            )
    root = placement._rectangle_from_mm("sorting_packaging_room", 0, 0, 1, 1, 0)
    root_options = {anchor.anchor_id: ((root, "WEST", None, {}),) for anchor in anchors}

    selected = placement._packaging_anchor_construction_representatives(
        context,
        anchors,
        (bay,),
        root_options_by_anchor=root_options,
    )

    assert len(selected) >= 4
    assert [row.rectangle.rotation_deg for row in selected[:4]] == [0, 90, 0, 90]


def test_package_derived_sorting_roots_are_cached_without_changing_anchor_coverage(
    monkeypatch: Any,
) -> None:
    context = _local_context()
    context.boundary = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
    context.boundary_bounds = (0, 0, 100_000, 100_000)
    context.obstacles = ()
    bays = (placement.BuildableBayV1("BAY-0001", (0, 0, 100_000, 100_000), 10_000_000_000),)
    stats = placement._PlacementSearchStats()
    original = placement._packaging_driven_sorting_roots
    calls: list[str] = []

    def counted(context_arg: Any, anchor: Any, **kwargs: Any) -> Any:
        calls.append(anchor.anchor_id)
        return original(context_arg, anchor, **kwargs)

    monkeypatch.setattr(placement, "_packaging_driven_sorting_roots", counted)
    compositions = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")
    first = tuple(
        row
        for row in placement._module_main_site_assemblies(
            context,
            compositions,
            LINEAR_3_BAND,
            "X",
            "POSITIVE",
            bays,
            limit=1,
            stats=stats,
        )
        if row is not None
    )
    first_call_count = len(calls)
    second = tuple(
        row
        for row in placement._module_main_site_assemblies(
            context,
            compositions,
            LINEAR_3_BAND,
            "X",
            "POSITIVE",
            bays,
            limit=1,
            stats=stats,
        )
        if row is not None
    )

    assert first and second
    assert first_call_count == len(stats.site_packaging_anchors or ())
    assert len(calls) == first_call_count
    assert stats.site_packaging_sorting_roots_by_anchor is not None
