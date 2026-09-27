"""Unmocked Tool 7 P1A regression for the Owner-labelled Xinzhao fixture."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.aily.application import site_layout_preview as site_layout_preview_module
from cold_storage.modules.layout.domain.structural_quality import (
    _bounds,
    _group_edge_facts,
    _shared_edge_orientation,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
V221_BASELINE = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_v221_before_layout.json"
EXPECTED_INPUT_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
V221_RESULT_HASH = "sha256:eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30"
V221_SVG_SHA256 = "sha256:db63fa7a6954820dd21dc0a7c70aba6f2cbfa7de6c5d2299027176100b109973"
R1_LAYOUT = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_after_layout.json"
R2_LAYOUT = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r2_after_layout.json"
R2_SVG = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r2_after.svg"
R3_LAYOUT = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r3_after_layout.json"
R3_SVG = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r3_after.svg"
R3_METRICS = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r3_metrics.json"
R5_LAYOUT = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r5_selected_layout.json"
R5_METRICS = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r5_metrics.json"
R6_METRICS = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r6_metrics.json"
R11_BUDGET = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r11_budget_accounting.json"
R5_SHARED_SKELETON = "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"


def _zone_map(layout: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = layout.get("zones")
    assert isinstance(rows, list)
    return {
        str(row["zone_code"]): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("zone_code"), str)
    }


def _direct_core_edges(zones: Mapping[str, Mapping[str, Any]]) -> int:
    return sum(
        int(_shared_edge_orientation(_bounds(zones[first]), _bounds(zones[second])) is not None)
        for first, second in (
            ("primary_precooling_room", "sorting_packaging_room"),
            ("sorting_packaging_room", "secondary_precooling_room"),
        )
    )


def test_xinzhao_real_tool7_r9_preflight_is_hard_valid_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_INPUT_SHA256
    payload = json.loads(raw)
    baseline = json.loads(V221_BASELINE.read_text(encoding="utf-8"))
    saved_r1_layout = json.loads(R1_LAYOUT.read_text(encoding="utf-8"))
    saved_r2_layout = json.loads(R2_LAYOUT.read_text(encoding="utf-8"))
    saved_r3_layout = json.loads(R3_LAYOUT.read_text(encoding="utf-8"))
    saved_r5_layout = json.loads(R5_LAYOUT.read_text(encoding="utf-8"))
    r3_metrics = json.loads(R3_METRICS.read_text(encoding="utf-8"))
    r5_metrics = json.loads(R5_METRICS.read_text(encoding="utf-8"))
    r6_metrics = json.loads(R6_METRICS.read_text(encoding="utf-8"))
    r11_budget = json.loads(R11_BUDGET.read_text(encoding="utf-8"))
    assert baseline["canonical_result_hash"] == V221_RESULT_HASH

    evaluations: list[dict[str, Any]] = []
    real_select = site_layout_preview_module.select_validated_placement

    def capture_evaluation(*args: Any, **kwargs: Any) -> Any:
        selection = real_select(*args, **kwargs)
        evaluations.append(selection.internal_evaluation)
        return selection

    monkeypatch.setattr(
        site_layout_preview_module,
        "select_validated_placement",
        capture_evaluation,
    )
    first = site_layout_preview_module.preview_site_layout(payload)
    second = site_layout_preview_module.preview_site_layout(payload)

    for result in (first, second):
        layout = result["layout"]
        assert result["project_layout_validated"] is True
        assert result["p2_complete"] is True
        assert result["validated_layout_selected"] is True
        assert result["zone_count"] == 12
        assert layout["access_requirement_count"] == 12
        assert layout["access_pass_count"] == 12
        assert layout["truck_route_validated"] is True
        assert layout.get("building_footprint")
        assert result["drawing"]["identity"] == "validated-layout-svg-projection@1.0.0"
        assert result["drawing"]["svg"]
        assert result["selection"]["p2d_full_pass_candidate_count"] >= 1
        lane_reports = result["selection"]["search_provenance"]["family_lanes"]
        assert len(lane_reports) == 3
        assert sum(int(row["visited_nodes"]) for row in lane_reports) <= 120
        assert result["selection"]["search_provenance"]["node_budget"] == 120

    assert len(evaluations) == 2
    first_evaluation = evaluations[0]
    assert first_evaluation == evaluations[1]
    assert first_evaluation["search_policy"] == "STAGED_COVERAGE_THEN_PREFERENCE"
    assert {row["topology"] for row in first_evaluation["family_lanes"]} == {
        "OFFSET_LINEAR_BAND",
        "CENTRAL_PROCESS_HUB",
        "STRAIGHT_LINEAR_BAND",
    }
    assert first_evaluation["topology_count_explored"] == 3
    assert first_evaluation["topology_count_with_constructed_skeleton"] == 3
    assert first_evaluation["constructed_main_process_skeleton_count"] == 11
    assert sum(int(row["visited_nodes"]) for row in first_evaluation["family_lanes"]) <= 120
    assert r5_metrics["p2d_full_pass_candidate_count"] == 4
    assert r5_metrics["constructed_skeleton_topologies"] == [
        "CENTRAL_PROCESS_HUB",
        "STRAIGHT_LINEAR_BAND",
    ]
    assert len(r5_metrics["constructed_main_process_skeleton_hashes"]) == 1
    assert first_evaluation["p2d_full_pass_distinct_main_process_skeleton_count"] == 1
    lifecycle_by_hash = {row["skeleton_hash"]: row for row in first_evaluation["skeleton_survival"]}
    assert lifecycle_by_hash[R5_SHARED_SKELETON]["discovery_topology"] == ("STRAIGHT_LINEAR_BAND")
    assert lifecycle_by_hash[R5_SHARED_SKELETON]["p2d_candidate_count"] == 2
    assert lifecycle_by_hash[R5_SHARED_SKELETON]["p2d_full_pass_count"] == 2
    r6_second_geometry = "sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"
    second_lifecycle = lifecycle_by_hash[r6_second_geometry]
    assert second_lifecycle["discovery_topology"] == "CENTRAL_PROCESS_HUB"
    assert second_lifecycle["canonical_topology_owner"] == "STRAIGHT_LINEAR_BAND"
    assert second_lifecycle["canonical_family"]["family"] == "LINEAR_PROCESS_BAND"
    assert second_lifecycle["packaging_preflight_executed"] is True
    assert second_lifecycle["packaging_slot_exists"] is False
    assert second_lifecycle["tail_search_started"] is False
    assert second_lifecycle["complete_candidate_count"] == 0
    assert second_lifecycle["p2d_reached"] is False
    assert second_lifecycle["first_failure_stage"] == "TAIL_SLOT_PREFLIGHT"
    assert second_lifecycle["first_failure_reason"] == (
        "AUTHORITATIVE_PACKAGING_RECTANGLE_NO_LEGAL_SLOT"
    )
    assert second_lifecycle["tail_nodes"] == 0
    assert second_lifecycle["tail_node_limit"] == 0
    assert first_evaluation["p2d_evaluated_distinct_main_process_skeleton_count"] == 3
    assert first_evaluation["p2d_full_pass_distinct_main_process_skeleton_count"] == 1
    assert first_evaluation["distinct_runner_up_present"] is False
    assert first_evaluation["selected_main_process_skeleton_hash"] == R5_SHARED_SKELETON
    assert (
        first_evaluation["distinct_skeleton_first_decisive_component"]
        == "ONLY_ONE_P2D_FULL_PASS_MAIN_SKELETON"
    )
    topology_diagnostics = first_evaluation["r6_topology_diagnostics"]
    assert {
        row["topology"]
        for row in topology_diagnostics["constructive_divergence_trace"]
        if row["attempted"] is True
    } == {"STRAIGHT_LINEAR_BAND", "OFFSET_LINEAR_BAND", "CENTRAL_PROCESS_HUB"}
    offset_rows = topology_diagnostics["offset_transition_trace"]
    assert offset_rows
    assert any(shift != 0 for row in offset_rows for shift in row["cross_axis_shifts_mm"])
    preflight_956 = next(
        row
        for row in topology_diagnostics["tail_slot_preflight_trace"]
        if row["skeleton_hash"] == r6_second_geometry
    )
    assert preflight_956["discovery_topology"] == "CENTRAL_PROCESS_HUB"
    assert preflight_956["canonical_topology_owner"] == "STRAIGHT_LINEAR_BAND"
    assert preflight_956["packaging_preflight_status"] == "NO_LEGAL_SLOT"
    assert preflight_956["tail_search_started"] is False
    assert not any(
        row.get("skeleton_hash") == r6_second_geometry
        for row in topology_diagnostics["ownership_matrix"]
    )
    registry_956 = next(
        row
        for row in topology_diagnostics["geometry_evaluation_registry"]
        if row["skeleton_hash"] == r6_second_geometry
    )
    assert registry_956["first_discovery_topology"] == "CENTRAL_PROCESS_HUB"
    assert registry_956["canonical_topology_owner"] == "STRAIGHT_LINEAR_BAND"
    assert registry_956["packaging_preflight_status"] == "NO_LEGAL_SLOT"
    assert registry_956["packaging_slot_exists"] is False
    assert registry_956["tail_admissible"] is False
    assert registry_956["tail_search_started"] is False
    assert registry_956["tail_search_discovery_topology"] is None
    assert registry_956["p2d_reached"] is False
    assert topology_diagnostics["cross_topology_duplicate_geometry_count"] == len(
        topology_diagnostics["cross_topology_duplicate_geometry_trace"]
    )
    assert topology_diagnostics["global_unique_skeleton_geometry_count"] == 11
    assert not any(
        row.get("constructed_topology") == "CENTRAL_PROCESS_HUB"
        and row.get("skeleton_hash") == R5_SHARED_SKELETON
        for row in topology_diagnostics["ownership_matrix"]
    )

    assert first["canonical_result_hash"] == second["canonical_result_hash"]
    assert first["layout"]["canonical_result_hash"] == second["layout"]["canonical_result_hash"]
    assert first["drawing"]["svg"] == second["drawing"]["svg"]
    assert first["svg_sha256"] == second["svg_sha256"]
    assert json.dumps(first["layout"], sort_keys=True, separators=(",", ":")) == json.dumps(
        second["layout"], sort_keys=True, separators=(",", ":")
    )
    public_serialization = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert all(
        field not in public_serialization
        for field in (
            "canonical_topology_owner",
            "construction_policy",
            "topology_divergence_stage",
            "offset_transition_stage",
            "offset_direction",
            "offset_cross_axis_shift_mm",
        )
    )
    assert first["canonical_result_hash"] != r5_metrics["r5_canonical_result_hash"]
    assert first["canonical_result_hash"] == r11_budget["selected_canonical_result_hash"]
    assert first["svg_sha256"] == r5_metrics["r5_svg_sha256"]
    assert first["svg_sha256"] == r6_metrics["r6_svg_sha256"]
    assert hashlib.sha256(first["drawing"]["svg"].encode("utf-8")).hexdigest() == (
        first["svg_sha256"].removeprefix("sha256:")
    )
    assert first["canonical_result_hash"] != V221_RESULT_HASH
    assert first["svg_sha256"] != V221_SVG_SHA256
    assert r3_metrics["result"] == "PARTIAL"
    assert r3_metrics["owner_xinzhao_p1a_r3_visual_review"] == "PENDING"
    assert r5_metrics["result"] == "PARTIAL"
    assert r5_metrics["owner_xinzhao_p1a_r5_visual_review"] == "PENDING"
    assert r5_metrics["distinct_p2d_full_pass_main_process_skeleton_count"] == 1
    assert r5_metrics["selected_main_process_geometry_changed_from_r3"] is False
    assert r5_metrics["selected_main_process_changed_zone_count"] == 0
    assert r5_metrics["r5_svg_hash_equals_r3"] is True
    for record in r5_metrics["visual_render_records"].values():
        rendered = (ROOT / "docs/tasks/evidence/v2_2_2_p1a" / record["file"]).read_bytes()
        assert hashlib.sha256(rendered).hexdigest() == record["sha256"]

    old_zones = _zone_map(baseline)
    new_zones = _zone_map(first["layout"])
    r1_zones = _zone_map(saved_r1_layout)
    r2_zones = _zone_map(saved_r2_layout)
    r5_zones = _zone_map(saved_r5_layout)
    main_zone_codes = (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )

    def main_geometry(zones: Mapping[str, Mapping[str, Any]]) -> dict[str, tuple[Any, ...]]:
        return {
            code: tuple(
                zones[code].get(field) for field in ("x", "y", "width_m", "depth_m", "rotation_deg")
            )
            for code in main_zone_codes
        }

    assert main_geometry(new_zones) == main_geometry(old_zones)
    assert main_geometry(new_zones) == main_geometry(r1_zones)
    assert main_geometry(new_zones) == main_geometry(r2_zones)
    assert main_geometry(new_zones) == main_geometry(_zone_map(saved_r3_layout))
    assert main_geometry(new_zones) == main_geometry(r5_zones)
    old_groups = _group_edge_facts(old_zones)
    new_groups = _group_edge_facts(new_zones)
    assert old_groups["SUPPORT_GROUP"] == 0
    assert new_groups["SUPPORT_GROUP"] == r5_metrics["support_group_shared_internal_edge_count"]
    # The core stays fully connected, but its direct-edge count does not
    # improve over the hard-valid v2.2.1 baseline and is reported as such.
    assert _direct_core_edges(old_zones) == 2
    assert _direct_core_edges(new_zones) == 2
    assert first["selection"]["search_provenance"]["node_budget"] == 120
    assert first["selection"]["search_provenance"]["node_budget_exhausted"] is True
    assert first["selection"]["search_provenance"]["search_tree_exhausted"] is False
    assert first["selection"]["search_provenance"]["global_optimum_claimed"] is False
