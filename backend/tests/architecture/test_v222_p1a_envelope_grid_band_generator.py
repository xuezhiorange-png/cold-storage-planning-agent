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
    assert "layout_families" in ast.unparse(constructor)
    assert "TAIL_ADMISSIBLE_SKELETON_COMPLETION_LIMIT" in ast.unparse(constructor)
    assert "structured_building_plan" in ast.unparse(root_search)
    assert "structured_plan.admits" in ast.unparse(edge_search)
    assert "aligned_edge_count" in ast.unparse(edge_search)


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
    assert "LINEAR_3_BAND" in source
    assert "CENTRAL_PROCESS_WITH_SIDE_BANKS" in source
    assert "LONGITUDINAL_PROCESS_SPINE" in source
    assert "SIMPLE_L_SITE_ADAPTIVE" in source
    assert "weighted_score" not in source.lower()
    assert "quality_score" not in source.lower()
