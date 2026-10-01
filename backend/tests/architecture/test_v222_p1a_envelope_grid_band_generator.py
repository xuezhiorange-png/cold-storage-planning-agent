from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLACEMENT = ROOT / "backend/src/cold_storage/modules/layout/domain/placement.py"
STRUCTURED = ROOT / "backend/src/cold_storage/modules/layout/domain/structured_building.py"


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_names(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def test_structured_runtime_directly_synthesizes_family_geometry_without_event_axis_dfs() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    context = _function(tree, "_validated_search_context")
    walk = _function(tree, "_walk_complete_candidate_payloads")
    synthesizer = _function(tree, "_direct_structured_candidates")

    assert "construct_structured_building_plan_v1" in _called_names(context)
    assert "structured_building_plan" in ast.unparse(context)
    walk_source = ast.unparse(walk)
    assert "_direct_structured_candidates" in _called_names(walk)
    assert walk_source.index("_direct_structured_candidates") < walk_source.index("def visit")
    assert {
        "_local_full_building_compositions",
        "_whole_building_site_placements",
        "_constructive_main_skeleton_tail_admission",
        "_structured_plan_from_composition",
        "_candidate_payload",
    } <= _called_names(synthesizer)
    synthesizer_source = ast.unparse(synthesizer)
    assert all(
        fragment in synthesizer_source
        for fragment in (
            "LINEAR_3_BAND: _synthesize_linear_3_band_local",
            "CENTRAL_PROCESS_WITH_SIDE_BANKS: _synthesize_central_side_banks_local",
            "LONGITUDINAL_PROCESS_SPINE: _synthesize_longitudinal_spine_local",
        )
    )
    assert "event_x" not in synthesizer_source
    assert "event_y" not in synthesizer_source
    assert "_candidate_options" not in _called_names(synthesizer)
    assert "_direct_adjacent_rectangle" not in _called_names(synthesizer)
    assert "_walk_complete_candidate_payloads" not in _called_names(synthesizer)
    assert "STRUCTURED_PHASE" in walk_source
    assert "GENERAL_FALLBACK_PHASE" in source


def test_general_fallback_retains_the_legacy_full_zone_enumerator() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    context = _function(tree, "_validated_search_context")
    walk = _function(tree, "_walk_complete_candidate_payloads")
    canonical_tail = _function(tree, "_canonical_tail_search_context")
    compatibility_plan = _function(tree, "_legacy_compatibility_search_plan")

    assert "_legacy_compatibility_search_plan" in _called_names(context)
    assert "GENERAL_FALLBACK_PHASE" in ast.unparse(context)
    walk_source = ast.unparse(walk)
    assert "GENERAL_FALLBACK_PHASE" in walk_source
    assert "yield from visit(0, True)" in walk_source
    assert "if context.search_phase == STRUCTURED_PHASE" in walk_source
    assert "structured_layout_family_for_topology" in _called_names(canonical_tail)
    assert "construct_legacy_compatibility_search_plan_v1" in _called_names(compatibility_plan)


def test_structured_geometry_gates_do_not_add_non_authoritative_closure_rules() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    synthesizer = _function(tree, "_direct_structured_candidates")
    main_compositions = _function(tree, "_local_main_process_compositions")
    full_compositions = _function(tree, "_local_full_building_compositions")
    planned_frame = _function(tree, "_structured_plan_from_composition")
    family_packer = _function(tree, "_family_main_band_packings")
    visit_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "visit"
    ]
    structured_visits = [
        node for node in visit_functions if "_candidate_payload" in ast.unparse(node)
    ]
    assert structured_visits
    assert all(
        "_building_envelope_closure_rejection" not in _called_names(node)
        for node in structured_visits
    )
    assert "_direct_envelope_closure_rejection" not in source
    assert "rectangles_share_positive_edge" not in ast.unparse(family_packer)
    assert "rectangles_share_positive_edge" not in ast.unparse(synthesizer)
    for composition in (main_compositions, full_compositions):
        composition_source = ast.unparse(composition)
        assert "_local_outline_class" in composition_source
        assert 'outline not in {"RECTANGLE", "SIMPLE_L"}' not in composition_source
    planned_frame_source = ast.unparse(planned_frame)
    assert "PLANNED_COMPOSITION_FRAME_NOT_FOOTPRINT_AUTHORITY" in planned_frame_source
    assert 'outline not in {"RECTANGLE", "SIMPLE_L"}' not in planned_frame_source


def test_domain_model_explicitly_encodes_envelope_grid_bands_and_zone_assignment() -> None:
    source = STRUCTURED.read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert {
        "BuildingEnvelopeV1",
        "PrimaryGridV1",
        "FunctionalBandV1",
        "BandZonePlacementV1",
        "StructuredBuildingSkeletonV1",
    } <= classes
    assert "Decimal(str(value)) * 1000" in source
    assert "rectangle_inside_polygon" in source
    assert "rectangle_intersects_closed_obstacle" in source
    assert "golden" not in source.lower()
    assert "xinzhao" not in source.lower()


def test_layout_families_are_construction_policies_not_selection_bonuses() -> None:
    source = STRUCTURED.read_text(encoding="utf-8")
    placement_source = PLACEMENT.read_text(encoding="utf-8")
    assert "LINEAR_3_BAND" in source
    assert "CENTRAL_PROCESS_WITH_SIDE_BANKS" in source
    assert "LONGITUDINAL_PROCESS_SPINE" in source
    assert "SIMPLE_L_SITE_ADAPTIVE" in source
    assert "weighted_score" not in source.lower()
    assert "quality_score" not in source.lower()
    placement_tree = ast.parse(placement_source)
    direct_synthesis = _function(placement_tree, "_direct_structured_candidates")
    compatibility_plan = _function(placement_tree, "_legacy_compatibility_search_plan")
    assert "structured_layout_family_for_topology" not in ast.unparse(direct_synthesis)
    assert "structured_layout_family_for_topology" in _called_names(compatibility_plan)
    context_builder = _function(placement_tree, "_validated_search_context")
    assert "GENERAL_FALLBACK_PHASE" in ast.unparse(context_builder)
    for constructor in (
        "_synthesize_linear_3_band_main_process",
        "_synthesize_central_process_with_side_banks_main_process",
        "_synthesize_longitudinal_process_spine_main_process",
    ):
        node = _function(ast.parse(placement_source), constructor)
        assert any(
            name in _called_names(node)
            for name in (
                "_linear_3_band_geometry",
                "_central_side_bank_geometry",
                "_longitudinal_spine_geometry",
            )
        )


def test_outer_bands_are_subregions_not_the_whole_envelope() -> None:
    source = STRUCTURED.read_text(encoding="utf-8")
    tree = ast.parse(source)
    band_bounds = _function(tree, "_band_bounds")
    band_source = ast.unparse(band_bounds)
    assert "SUPPORT_BAND, PERSONNEL_EDGE_BAND" in band_source
    assert "support_width" in band_source
    assert "personnel_width" in band_source
    assert "return envelope[0], envelope[1], envelope[2], envelope[3]" not in band_source


def test_simple_l_envelope_uses_exact_union_coverage_for_cross_component_zones() -> None:
    source = STRUCTURED.read_text(encoding="utf-8")
    tree = ast.parse(source)
    exact_union = _function(tree, "_bounds_covered_by_regions")
    body = ast.unparse(exact_union)
    assert "x_events" in body
    assert "regions" in body
    assert "covered_to < top" in body
