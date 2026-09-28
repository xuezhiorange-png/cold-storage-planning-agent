"""Architecture guard for the R13 necessary truck-manuever preflight."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLACEMENT = ROOT / "src/cold_storage/modules/layout/domain/placement.py"
APP_PLACEMENT = ROOT / "src/cold_storage/modules/layout/application/placement.py"
SELECTION = ROOT / "src/cold_storage/modules/layout/application/validated_candidate_selection.py"
P2D_ACCESS = ROOT / "src/cold_storage/modules/layout/application/access_routing.py"
SITE_PREVIEW = ROOT / "src/cold_storage/modules/aily/application/site_layout_preview.py"


def _calls(source: str, name: str) -> list[ast.Call]:
    tree = ast.parse(source)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]


def test_preflight_is_after_complete_skeleton_and_before_tail_dfs() -> None:
    source = PLACEMENT.read_text(encoding="utf-8")
    assert source.index("_main_skeleton_truck_maneuver_preflight(context, seed)") < source.index(
        "for tail_event in visit(len(MAIN_PROCESS_ZONE_CODES), True, seed):"
    )
    preflight = source.split("def _main_skeleton_truck_maneuver_preflight(", 1)[1].split(
        "\ndef _search_provenance(", 1
    )[0]
    assert "set(zones) != set(MAIN_PROCESS_SKELETON_ZONE_CODES)" in preflight


def test_preflight_reuses_loading_face_and_the_single_authoritative_truck_predicate() -> None:
    placement_source = PLACEMENT.read_text(encoding="utf-8")
    app_placement_source = APP_PLACEMENT.read_text(encoding="utf-8")
    p2d_source = P2D_ACCESS.read_text(encoding="utf-8")
    selector_source = SELECTION.read_text(encoding="utf-8")
    assert len(_calls(placement_source, "validate_truck_maneuver_chain")) == 0
    assert len(_calls(p2d_source, "validate_truck_maneuver_chain")) == 1
    preflight = placement_source.split("def _main_skeleton_truck_maneuver_preflight(", 1)[1].split(
        "\ndef _search_provenance(", 1
    )[0]
    assert '_loading_face(zones["shipping_channel"], context.site_body)' in preflight
    assert "_truck_segment(context.site_body)" in preflight
    assert "node_budget=context.truck_node_budget" in preflight
    assert "validator = context.truck_maneuver_validator" in preflight
    assert "result = validator(" in preflight
    assert "truck_maneuver_validator=truck_maneuver_validator" in app_placement_source
    assert "truck_maneuver_validator=validate_truck_maneuver_chain" in selector_source


def test_final_p2d_remains_mandatory_and_public_tool_contract_is_not_extended() -> None:
    selector_source = SELECTION.read_text(encoding="utf-8")
    assert "route_site_placement(" in selector_source
    assert "main_skeleton_truck_preflight_trace" in selector_source
    assert "main_skeleton_truck_preflight_trace" not in SITE_PREVIEW.read_text(encoding="utf-8")
    assert "main_skeleton_truck_preflight_trace" not in (
        ROOT / "src/cold_storage/modules/aily/application/mcp_site_layout.py"
    ).read_text(encoding="utf-8")


def test_existing_production_budgets_and_domain_authority_are_unchanged() -> None:
    preview = SITE_PREVIEW.read_text(encoding="utf-8")
    assert "P4_PLACEMENT_NODE_BUDGET = 120" in preview
    assert "P4_TRUCK_NODE_BUDGET = 5_000" in preview
    assert "golden" not in PLACEMENT.read_text(encoding="utf-8").lower()
