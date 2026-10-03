"""Architecture locks for exact, necessary R9 tail-slot pruning."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLACEMENT = ROOT / "backend/src/cold_storage/modules/layout/domain/placement.py"
SLOT_DOMAIN = ROOT / "backend/src/cold_storage/modules/layout/domain/tail_slot_feasibility.py"
SELECTOR = (
    ROOT / "backend/src/cold_storage/modules/layout/application/validated_candidate_selection.py"
)
TOOL7 = ROOT / "backend/src/cold_storage/modules/aily/application/site_layout_preview.py"


def _function_node(source: str, function_name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )


def test_event_slot_search_is_finite_orthogonal_exact_and_has_no_mm_sweep() -> None:
    source = SLOT_DOMAIN.read_text(encoding="utf-8")
    function = _function_node(source, "evaluate_tail_zone_slot_feasibility_v1")
    called_names = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "_cached_rectangle_inside_polygon" in called_names
    assert "_cached_rectangle_intersects_obstacle" in called_names
    assert "rectangles_overlap" in called_names
    assert "rectangle_inside_polygon" in {
        node.func.id
        for node in ast.walk(_function_node(source, "_cached_rectangle_inside_polygon"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "rectangle_intersects_closed_obstacle" in {
        node.func.id
        for node in ast.walk(_function_node(source, "_cached_rectangle_intersects_obstacle"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "range" not in called_names
    assert "EXACT_ORTHOGONAL_EVENT_ENUMERATION" in source
    assert "EXACT_EVENT_COMPLETENESS_UNAVAILABLE" in source
    assert "any(not _is_orthogonal(polygon) for polygon in polygons)" in source


def test_only_proven_no_slot_result_skips_tail_and_unavailable_proof_admits() -> None:
    placement_source = PLACEMENT.read_text(encoding="utf-8")
    selector_source = SELECTOR.read_text(encoding="utf-8")

    assert "slot_exists is False" in placement_source
    assert "proof_mode == EXACT_ORTHOGONAL_EVENT_ENUMERATION" in placement_source
    assert 'preflight_status == "NO_LEGAL_SLOT"' in placement_source
    assert 'preflight_status != "NO_LEGAL_SLOT"' in placement_source
    assert '"tail_slot_preflight_trace": []' in selector_source
    assert '("tail_slot_preflight_rows", "tail_slot_preflight_trace")' in selector_source


def test_preflight_rejection_precedes_admissible_completion_quota_and_tail() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    check = source.index('if preflight_status == "NO_LEGAL_SLOT":')
    rejection_continue = source.index("continue", check)
    admissible_increment = source.index("emitted_skeletons += 1", check)
    tail_yield = source.index("yield seed", check)

    assert check < rejection_continue < admissible_increment < tail_yield
    assert "PREFLIGHT_COMPUTE_COUNTS_AS_PLACEMENT_NODE" not in source


def test_rejected_geometry_is_cached_and_duplicate_does_not_restart_tail() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    rejected_branch = source.index('if cached_preflight_status == "NO_LEGAL_SLOT":')
    duplicate_record = source.index('"DUPLICATE_PRETAIL_REJECTED_GEOMETRY"', rejected_branch)
    no_rerun_record = source.index('"preflight_reexecuted": False', duplicate_record)
    duplicate_continue = source.index("continue", no_rerun_record)
    first_preflight = source.index("_packaging_tail_slot_preflight(", duplicate_continue)

    assert rejected_branch < duplicate_record < no_rerun_record < duplicate_continue
    assert duplicate_continue < first_preflight


def test_runtime_preflight_is_fixture_agnostic_and_only_targets_packaging_storage() -> None:
    placement_source = PLACEMENT.read_text(encoding="utf-8").lower()
    slot_source = SLOT_DOMAIN.read_text(encoding="utf-8").lower()

    assert 'context.authorities["packaging_material_storage"]' in placement_source
    for fixture_marker in ("xinzhao", "新哨", "956e85", "55589c", "gd-001", "gd-005"):
        assert fixture_marker not in placement_source
        assert fixture_marker not in slot_source


def test_tool7_budget_and_public_input_boundary_remain_unchanged() -> None:
    source = TOOL7.read_text(encoding="utf-8")
    assert "P4_PLACEMENT_NODE_BUDGET = 120" in source
    assert "PREVIEW_SITE_LAYOUT_INPUT_FIELDS" in source
    assert "tail_slot_preflight" not in source
