"""Architecture locks for structural layout generation without contract drift."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from cold_storage.modules.aily.application.site_layout_preview import (
    P4_PLACEMENT_NODE_BUDGET,
    PREVIEW_SITE_LAYOUT_INPUT_FIELDS,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    FUNCTIONAL_GROUPS,
    LINEAR_PROCESS_BAND,
    MAIN_PROCESS_ZONE_CODES,
)

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src/cold_storage/modules"
LAYOUT = BACKEND_SRC / "layout"


def _source(relative_path: str) -> str:
    return (LAYOUT / relative_path).read_text(encoding="utf-8")


def test_p1a_keeps_tool7_public_input_contract_and_budget_unchanged() -> None:
    assert PREVIEW_SITE_LAYOUT_INPUT_FIELDS == (
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
        "site_constraints",
        "truck_access",
        "truck_maneuver",
    )
    assert P4_PLACEMENT_NODE_BUDGET == 15
    preview_source = (BACKEND_SRC / "aily/application/site_layout_preview.py").read_text(
        encoding="utf-8"
    )
    assert "select_validated_placement(" in preview_source
    assert "place_zones(" not in preview_source
    assert "route_site_placement(" not in preview_source


def test_structural_search_is_group_band_zone_and_has_two_versioned_families() -> None:
    placement_source = _source("domain/placement.py")
    assert "PLACEMENT_ZONE_ORDER" in placement_source
    assert placement_source.index('"sorting_packaging_room"') < placement_source.index(
        '"packaging_material_storage"'
    )
    assert "MAIN_PROCESS_PREDECESSOR" in placement_source
    assert "structural_anchor_references" in placement_source
    assert LINEAR_PROCESS_BAND == "LINEAR_PROCESS_BAND"
    assert CENTRAL_PROCESS_HUB == "CENTRAL_PROCESS_HUB"
    assert len(FUNCTIONAL_GROUPS) == 5
    assert MAIN_PROCESS_ZONE_CODES[-1] == "shipping_channel"


def test_selector_enforces_p2d_full_pass_before_structural_quality_and_old_tie_break() -> None:
    selector = _source("application/validated_candidate_selection.py")
    hard_gate = selector.index("if not full_pass:")
    structural_evaluation = selector.index("build_structural_quality_facts(")
    assert hard_gate < structural_evaluation
    assert "structural_candidate_is_better" in selector
    assert "placement_candidate_is_better" in selector
    assert "candidate_facts.comparison_key != best_facts.comparison_key" in selector
    assert "P2B2_FINAL_TIE_BREAK" in selector
    assert "LEXICOGRAPHIC_ATOMIC_FACTS" in selector
    assert "weighted_score" not in selector.lower()
    assert "selection_body" not in selector


def test_no_uncalibrated_p1b_threshold_or_p2d_runtime_dependency_in_structural_domain() -> None:
    composition = _source("domain/structural_composition.py")
    quality = _source("domain/structural_quality.py")
    placement = _source("domain/placement.py")

    for source in (composition, quality, placement):
        tree = ast.parse(source)
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not any("access_routing" in module for module in imported_modules)
        assert not any("site_layout_preview" in module for module in imported_modules)
        assert "GRID_ALIGNMENT_THRESHOLD" not in source
        assert "DEPTH_ALIGNMENT_THRESHOLD" not in source
        assert "OCCUPANCY_THRESHOLD" not in source
        assert "NOTCH_THRESHOLD" not in source
        assert "APPENDAGE_THRESHOLD" not in source

    assert '"main_flow_backtrack_count": {"status": "UNAVAILABLE"' in quality
    assert '"main_flow_turn_count": {"status": "UNAVAILABLE"' in quality
    assert '"process_route_efficiency": {"status": "UNAVAILABLE"' in quality


def test_structural_quality_remains_internal_and_does_not_redefine_hard_status() -> None:
    selector = _source("application/validated_candidate_selection.py")
    assert "_internal_evaluation_json" in selector
    assert '"project_layout_validated": True' in selector
    assert '"p2_complete": True' in selector
    assert '"PROCESS_FLOW_VALIDATED"' not in selector
    assert '"LAYOUT_REGULARITY_VALIDATED"' not in selector


def test_xinzhao_evidence_pins_hashes_and_does_not_hide_unimproved_core_facts() -> None:
    evidence = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
    report = json.loads((evidence / "xinzhao_p1a_metrics.json").read_text(encoding="utf-8"))
    assert report["historical_v221_baseline"]["canonical_result_hash"].endswith(
        "eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30"
    )
    assert report["p1a_result"]["project_layout_validated"] is True
    assert report["p1a_result"]["p2_complete"] is True
    assert report["p1a_result"]["access_pass_count"] == 12
    assert report["p1a_result"]["process_core_direct_edge_count"] == 2
    assert report["comparative_result"]["process_core_legibility_improved"] is False
    assert report["p1a_result"]["main_flow_turn_count"] == "UNAVAILABLE"
    for artifact_name, expected_sha in (
        (
            "xinzhao_v221_before.svg",
            "db63fa7a6954820dd21dc0a7c70aba6f2cbfa7de6c5d2299027176100b109973",
        ),
        (
            "xinzhao_p1a_after.svg",
            "7f24aabd674218c097ce71d229d7bd57d9d774ab47f3ec612fded749abf2779f",
        ),
    ):
        assert hashlib.sha256((evidence / artifact_name).read_bytes()).hexdigest() == expected_sha
    assert (evidence / "xinzhao_v221_before.png").is_file()
    assert (evidence / "xinzhao_p1a_after.png").is_file()
