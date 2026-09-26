"""Architecture locks for structural layout generation without contract drift."""

from __future__ import annotations

import ast
import hashlib
import json
import struct
from pathlib import Path

from cold_storage.modules.aily.application.site_layout_preview import (
    P4_PLACEMENT_NODE_BUDGET,
    PREVIEW_SITE_LAYOUT_INPUT_FIELDS,
)
from cold_storage.modules.layout.domain.placement import STRUCTURED_PLACEMENT_ZONE_ORDER
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    FUNCTIONAL_GROUPS,
    LINEAR_PROCESS_BAND,
    MAIN_PROCESS_ZONE_CODES,
)

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src/cold_storage/modules"
LAYOUT = BACKEND_SRC / "layout"
P1A_EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"


def _source(relative_path: str) -> str:
    return (LAYOUT / relative_path).read_text(encoding="utf-8")


def test_p1a_keeps_tool7_contract_and_uses_evidence_supported_search_budget() -> None:
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
    assert P4_PLACEMENT_NODE_BUDGET == 120
    preview_source = (BACKEND_SRC / "aily/application/site_layout_preview.py").read_text(
        encoding="utf-8"
    )
    assert "select_validated_placement(" in preview_source
    assert "place_zones(" not in preview_source
    assert "route_site_placement(" not in preview_source


def test_structural_search_has_group_band_zone_and_three_required_family_lanes() -> None:
    placement_source = _source("domain/placement.py")
    composition_source = _source("domain/structural_composition.py")
    assert "PLACEMENT_ZONE_ORDER" in placement_source
    assert placement_source.index('"sorting_packaging_room"') < placement_source.index(
        '"packaging_material_storage"'
    )
    assert "MAIN_PROCESS_PREDECESSOR" in composition_source
    assert "composition_family_candidates" in composition_source
    assert "structural_anchor_references" in placement_source
    assert LINEAR_PROCESS_BAND == "LINEAR_PROCESS_BAND"
    assert CENTRAL_PROCESS_HUB == "CENTRAL_PROCESS_HUB"
    assert len(FUNCTIONAL_GROUPS) == 5
    assert MAIN_PROCESS_ZONE_CODES[-1] == "shipping_channel"
    selector = _source("application/validated_candidate_selection.py")
    assert '"STAGED_COVERAGE_THEN_PREFERENCE"' in selector
    assert "for lane_index in lane_order" in selector
    assert "lane_budgets[lane_index]" in selector
    assert "GENERAL_FALLBACK_PHASE" in selector


def test_r5_staged_topology_coverage_is_bounded_and_xinzhao_result_is_partial() -> None:
    composition = _source("domain/structural_composition.py")
    selector = _source("application/validated_candidate_selection.py")
    placement = _source("domain/placement.py")
    r5_metrics = json.loads(
        (P1A_EVIDENCE / "xinzhao_p1a_r5_metrics.json").read_text(encoding="utf-8")
    )
    cross_fixture = json.loads(
        (P1A_EVIDENCE / "xinzhao_p1a_r5_cross_fixture_regression.json").read_text(encoding="utf-8")
    )

    assert all(
        topology in composition
        for topology in (
            "STRAIGHT_LINEAR_BAND",
            "OFFSET_LINEAR_BAND",
            "CENTRAL_PROCESS_HUB",
        )
    )
    assert '"STAGED_COVERAGE_THEN_PREFERENCE"' in selector
    assert '"root_preflight_mode": "EXACT_NECESSARY_PREDICATE_OR_ORDERING_ONLY"' in placement
    assert '"heuristic_root_pruning": False' in placement
    assert "WEIGHTED_SCORE" not in selector
    assert "XINZHAO" not in selector.upper()
    assert r5_metrics["production_placement_node_budget"] == 120
    assert r5_metrics["production_budget_changed"] is False
    assert r5_metrics["topology_count_explored"] == 3
    assert r5_metrics["topology_count_with_constructed_skeleton"] == 2
    assert r5_metrics["distinct_p2d_full_pass_main_process_skeleton_count"] == 1
    assert r5_metrics["distinct_runner_up_present"] is False
    assert r5_metrics["result"] == "PARTIAL"
    assert r5_metrics["owner_xinzhao_p1a_r5_visual_review"] == "PENDING"
    assert r5_metrics["p1b_threshold_activated"] is False
    assert r5_metrics["weighted_score_used"] is False
    assert cross_fixture["result"] == "PASS"
    assert cross_fixture["full_chain_authoritative_fixture_count"] == 3
    assert cross_fixture["composition_only_fixture_count"] == 2
    assert cross_fixture["scenario_count"] == 5
    assert cross_fixture["acceptance_facts"]["all_scenarios_pass"] is True


def test_r3_constructs_seven_zone_skeleton_before_tail_search_and_records_rejections() -> None:
    placement_source = _source("domain/placement.py")
    constructor = placement_source.index("def _construct_main_process_skeletons(")
    walker = placement_source.index("def _walk_complete_candidate_payloads(")
    skeleton_seed = placement_source.index(
        "skeleton_seeds = tuple(_construct_main_process_skeletons(context, stats))", walker
    )
    tail_walk = placement_source.index(
        "yield from visit(len(MAIN_PROCESS_ZONE_CODES), True, seed)", skeleton_seed
    )
    assert constructor < walker < skeleton_seed < tail_walk
    assert "placed.update({row.zone_code: row for row in seed.zone_rectangles})" in placement_source
    assert "MAIN_PROCESS_SKELETON_ZONE_CODES" in placement_source
    assert not set(STRUCTURED_PLACEMENT_ZONE_ORDER[len(MAIN_PROCESS_ZONE_CODES) :]) & set(
        MAIN_PROCESS_ZONE_CODES
    )

    rejection_codes = (
        "SITE_OUTSIDE",
        "NO_BUILD_COLLISION",
        "ZONE_OVERLAP",
        "MUST_ADJACENCY_FAIL",
        "GROUP_ORDER_FAIL",
        "SHIPPING_INTERFACE_FAIL",
        "DIMENSION_VARIANT_UNAVAILABLE",
        "SKELETON_TOPOLOGY_INVALID",
    )
    for code in rejection_codes:
        assert f'"{code}"' in placement_source

    skeleton_source = _source("domain/main_process_skeleton.py")
    assert 'IDENTITY: Final = "main-process-skeleton-candidate@1.0.0"' in skeleton_source
    assert '"authority": "CANDIDATE_SEARCH_GEOMETRY_ONLY"' in skeleton_source
    assert '"rotation_deg": rectangle.rotation_deg' in skeleton_source
    assert "MAIN_PROCESS_ZONE_CODES" in skeleton_source


def test_r3_evidence_is_explicitly_partial_and_keeps_the_xinzhao_geometry_gap() -> None:
    metrics = json.loads((P1A_EVIDENCE / "xinzhao_p1a_r3_metrics.json").read_text(encoding="utf-8"))
    search = json.loads(
        (P1A_EVIDENCE / "xinzhao_p1a_r3_skeleton_search.json").read_text(encoding="utf-8")
    )
    assert metrics["result"] == "PARTIAL"
    assert metrics["owner_xinzhao_p1a_r3_visual_review"] == "PENDING"
    assert metrics["r3_main_process_geometry_changed"] is False
    assert metrics["r3_main_process_changed_zone_count"] == 0
    assert metrics["distinct_full_pass_main_process_skeleton_count"] == 1
    assert metrics["p2d_full_pass_candidate_count"] == 2
    assert metrics["first_decisive_component"] == "P2B2_FINAL_TIE_BREAK"
    assert metrics["node_budget"] == 120
    assert metrics["search_provenance"]["global_optimum_claimed"] is False
    assert metrics["search_provenance"]["node_budget_is_only_search_cutoff"] is True

    lanes = search["family_lanes"]
    assert {
        (lane["composition_family"]["family"], lane["composition_family"]["dominant_direction"])
        for lane in lanes
    } == {
        ("LINEAR_PROCESS_BAND", "POSITIVE"),
        ("LINEAR_PROCESS_BAND", "NEGATIVE"),
        ("CENTRAL_PROCESS_HUB", "UNRESOLVED"),
    }
    central = next(
        lane for lane in lanes if lane["composition_family"]["family"] == "CENTRAL_PROCESS_HUB"
    )
    constructed = [
        candidate
        for phase in central["phases"]
        for candidate in phase["main_process_skeleton_generation"]["candidates"]
    ]
    assert len(constructed) == 2
    assert all(len(candidate["zone_rectangles"]) == 7 for candidate in constructed)
    assert len({candidate["main_process_skeleton_hash"] for candidate in constructed}) == 2
    assert all(lane["search_tree_exhausted"] is False for lane in lanes)


def test_r3_four_way_visual_artifacts_are_direct_rasters_with_pinned_hashes() -> None:
    metrics = json.loads((P1A_EVIDENCE / "xinzhao_p1a_r3_metrics.json").read_text(encoding="utf-8"))
    sources = {
        "V221": ("xinzhao_v221_before.svg", "xinzhao_p1a_r3_compare_v221.png"),
        "R1": ("xinzhao_p1a_after.svg", "xinzhao_p1a_r3_compare_r1.png"),
        "R2": ("xinzhao_p1a_r2_after.svg", "xinzhao_p1a_r3_compare_r2.png"),
        "R3": ("xinzhao_p1a_r3_after.svg", "xinzhao_p1a_r3_after.png"),
    }
    hashes: dict[str, str] = {}
    for profile, (svg_name, png_name) in sources.items():
        svg_bytes = (P1A_EVIDENCE / svg_name).read_bytes()
        assert b'viewBox="0 0 1931.62 830"' in svg_bytes
        png_bytes = (P1A_EVIDENCE / png_name).read_bytes()
        assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png_bytes[16:24])
        assert (width, height) == (2400, 2400)
        digest = hashlib.sha256(png_bytes).hexdigest()
        hashes[profile] = digest
        record = metrics["visual_render_records"][profile]
        assert record["sha256"] == digest
        assert record["rasterizer"].startswith("macOS Quick Look")
        assert (record["width"], record["height"]) == (width, height)

    assert hashes["R2"] == hashes["R3"]
    debug_svg_hash = hashlib.sha256(
        (P1A_EVIDENCE / "xinzhao_p1a_r3_skeleton_debug.svg").read_bytes()
    ).hexdigest()
    assert debug_svg_hash == metrics["skeleton_debug_svg_sha256"]
    debug_png = (P1A_EVIDENCE / "xinzhao_p1a_r3_skeleton_debug.png").read_bytes()
    assert hashlib.sha256(debug_png).hexdigest() == metrics["skeleton_debug_png"]["sha256"]
    assert struct.unpack(">II", debug_png[16:24]) == (2400, 2400)


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


def test_r2_evidence_reports_multi_family_limits_and_visual_non_improvement() -> None:
    evidence = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
    metrics = json.loads((evidence / "xinzhao_p1a_r2_metrics.json").read_text(encoding="utf-8"))
    budget = json.loads(
        (evidence / "xinzhao_p1a_r2_budget_sensitivity.json").read_text(encoding="utf-8")
    )
    assert [row["node_budget"] for row in budget["runs"]] == [15, 30, 60, 120, 240]
    assert budget["decision"]["smallest_tested_budget_yielding_two_p2d_full_pass_candidates"] == 120
    assert budget["decision"]["distinct_full_pass_families_at_budget_120"] == 1
    assert budget["decision"]["linear_lane_noncompletion_is_proven_infeasible"] is False
    assert metrics["p2d_full_pass_candidate_count"] == 2
    assert metrics["distinct_full_pass_family_count"] == 1
    assert metrics["runner_up_present"] is True
    assert metrics["first_decisive_component"] == "P2B2_FINAL_TIE_BREAK"
    assert metrics["main_process_geometry_equal_to_v221"] is True
    assert metrics["main_process_geometry_equal_to_r1"] is True
    assert metrics["owner_xinzhao_p1a_r2_visual_review"] == "PENDING"

    baseline = json.loads((evidence / "xinzhao_v221_before_layout.json").read_text())
    r1 = json.loads((evidence / "xinzhao_p1a_after_layout.json").read_text())
    r2 = json.loads((evidence / "xinzhao_p1a_r2_after_layout.json").read_text())
    main_zones = (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )

    def geometry(layout: dict[str, object]) -> dict[str, tuple[object, ...]]:
        rows = layout["zones"]
        assert isinstance(rows, list)
        return {
            str(row["zone_code"]): tuple(
                row.get(field) for field in ("x", "y", "width_m", "depth_m", "rotation_deg")
            )
            for row in rows
            if isinstance(row, dict) and row.get("zone_code") in main_zones
        }

    baseline_geometry = geometry(baseline)
    r1_geometry = geometry(r1)
    r2_geometry = geometry(r2)
    assert set(r2_geometry) == set(main_zones)
    assert r2_geometry == baseline_geometry == r1_geometry

    for name in (
        "xinzhao_v221_before.svg",
        "xinzhao_p1a_after.svg",
        "xinzhao_p1a_r2_after.svg",
    ):
        svg = (evidence / name).read_text(encoding="utf-8")
        assert 'viewBox="0 0 1931.62 830"' in svg
    assert "OWNER_XINZHAO_P1A_R2_VISUAL_REVIEW=PENDING" in (
        evidence / "xinzhao_p1a_r2_comparison.md"
    ).read_text(encoding="utf-8")
