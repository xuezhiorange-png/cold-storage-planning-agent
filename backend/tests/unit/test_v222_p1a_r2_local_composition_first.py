from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cold_storage.modules.layout.domain import placement
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
