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
    adjacent = _function(tree, "_direct_adjacent_rectangle")

    assert "construct_structured_building_plan_v1" in _called_names(context)
    assert "structured_building_plan" in ast.unparse(context)
    walk_source = ast.unparse(walk)
    assert "_direct_structured_candidates" in _called_names(walk)
    assert walk_source.index("_direct_structured_candidates") < walk_source.index("def visit")
    assert {
        "construct_structured_building_plan_v1",
        "_synthesize_family_main_process",
        "_direct_family_tail_zones",
        "_constructive_main_skeleton_tail_admission",
        "_candidate_payload",
    } <= _called_names(synthesizer)
    adjacent_source = ast.unparse(adjacent)
    assert "plan.admits" in adjacent_source
    assert "_geometry_rejection_reason" in adjacent_source
    assert "_candidate_options" not in adjacent_source
    assert "event_x" not in adjacent_source
    assert "event_y" not in adjacent_source
    assert "_DIRECT_FAMILY_EDGES" in source
    for family in (
        "LINEAR_3_BAND",
        "CENTRAL_PROCESS_WITH_SIDE_BANKS",
        "LONGITUDINAL_PROCESS_SPINE",
    ):
        assert f"{family}: (" in source
    assert {
        "_synthesize_linear_3_band_main_process",
        "_synthesize_central_process_with_side_banks_main_process",
        "_synthesize_longitudinal_process_spine_main_process",
    } <= {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "STRUCTURED_PHASE" in walk_source
    assert "GENERAL_FALLBACK_PHASE" in source


def test_full_program_closure_gate_precedes_candidate_emission() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    visit_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "visit"
    ]
    structured_visits = [
        node for node in visit_functions if "_candidate_payload" in ast.unparse(node)
    ]
    assert structured_visits
    assert any(
        "_building_envelope_closure_rejection" in ast.unparse(node)
        and ast.unparse(node).index("_building_envelope_closure_rejection")
        < ast.unparse(node).index("_candidate_payload")
        for node in structured_visits
    )
    closure = _function(tree, "_building_envelope_closure_rejection")
    assert "derive_building_footprint" in _called_names(closure)
    assert "with_placements" in ast.unparse(closure)
    assert "RECTANGLE" in ast.unparse(closure)
    assert "SIMPLE_L" in ast.unparse(closure)
    direct_closure = _function(tree, "_direct_envelope_closure_rejection")
    assert "SUPPORT_BAND" in ast.unparse(direct_closure)
    assert "PERSONNEL_EDGE_BAND" in ast.unparse(direct_closure)
    assert "PROCESS_CORE_NOT_CONTIGUOUS" in ast.unparse(direct_closure)


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
    assert "structured_layout_family_for_topology" not in placement_source


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
    contains = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "contains"
    )
    body = ast.unparse(contains)
    assert "x_events" in body
    assert "components_mm" in body
    assert "covered_to < top" in body
