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


def test_runtime_constructs_envelope_grid_bands_before_search_roots() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    context = _function(tree, "_validated_search_context")
    constructor = _function(tree, "_construct_main_process_skeletons")
    root_search = _function(tree, "_constructive_sorting_roots")
    edge_search = _function(tree, "_constructive_edge_options")

    assert "construct_structured_building_plan_v1" in _called_names(context)
    assert "structured_building_plan" in ast.unparse(context)
    assert "construct_structured_building_plan_v1" in _called_names(constructor)
    assert "BASE_LAYOUT_FAMILIES" in ast.unparse(constructor)
    assert "envelope_family" in ast.unparse(constructor)
    assert "NO_SITE_FEASIBLE_ENVELOPE" in ast.unparse(constructor)
    assert "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT" in ast.unparse(constructor)
    assert "preferred_axis" in ast.unparse(constructor)
    assert "alternate_axis" in ast.unparse(constructor)
    assert "process_axis" in ast.unparse(constructor)
    assert "structured_building_plan" in ast.unparse(root_search)
    assert "structured_plan.admits" in ast.unparse(edge_search)
    assert "aligned_edge_count" in ast.unparse(edge_search)


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
