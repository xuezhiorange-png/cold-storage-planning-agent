from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

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


def _local_context() -> SimpleNamespace:
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
            assert composition.outline_class in {RECTANGLE, SIMPLE_L}
            assert min(rectangle.bounds_mm[0] for rectangle in rectangles.values()) == 0
            assert min(rectangle.bounds_mm[1] for rectangle in rectangles.values()) == 0
            placement._validate_main_process_skeleton_graph(context.graph, rectangles)


def test_support_and_personnel_are_jointly_composed_before_envelope_derivation() -> None:
    context = _local_context()
    main = placement._synthesize_linear_3_band_local(context, "X", "POSITIVE")[0]
    complete = placement._local_full_building_compositions(context, main, result_limit=1)

    assert complete
    composition = complete[0]
    rectangles = composition.placements()
    assert set(rectangles) == set(context.graph.nodes)
    assert composition.outline_class in {RECTANGLE, SIMPLE_L}
    placement._validate_graph_completeness(context.graph, rectangles)

    plan = placement._structured_plan_from_composition(
        composition,
        rectangles,
        obstacles=(),
        site_bounds=(-100_000, -100_000, 100_000, 100_000),
    )
    assert plan.envelope.family == composition.outline_class
    assert plan.envelope.bounds_mm == composition.bounds_mm
    assert plan.envelope.bounds_mm != plan.envelope.site_bounds_mm
    assert len(plan.zone_placements) == len(context.graph.nodes)


def test_local_shape_combinations_are_finite_and_deterministic() -> None:
    options = tuple((width, width + 1, 0, width, width + 1) for width in (10, 20, 30))
    shape_options = tuple(options for _ in placement.MAIN_PROCESS_ZONE_CODES)

    first = placement._bounded_local_shape_rows(shape_options)
    second = placement._bounded_local_shape_rows(shape_options)

    assert first == second
    assert len(first) == placement.LOCAL_COMPOSITION_SHAPE_VARIANT_LIMIT
    assert len(first) < 3 ** len(shape_options)


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
