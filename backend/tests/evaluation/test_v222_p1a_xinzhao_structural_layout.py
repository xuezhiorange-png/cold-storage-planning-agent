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
R5_METRICS = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r5_metrics.json"


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


def test_xinzhao_real_tool7_staged_topology_search_is_hard_valid_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_INPUT_SHA256
    payload = json.loads(raw)
    baseline = json.loads(V221_BASELINE.read_text(encoding="utf-8"))
    saved_r1_layout = json.loads(R1_LAYOUT.read_text(encoding="utf-8"))
    saved_r2_layout = json.loads(R2_LAYOUT.read_text(encoding="utf-8"))
    saved_r3_layout = json.loads(R3_LAYOUT.read_text(encoding="utf-8"))
    r3_metrics = json.loads(R3_METRICS.read_text(encoding="utf-8"))
    r5_metrics = json.loads(R5_METRICS.read_text(encoding="utf-8"))
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
        assert [row["lane_node_budget"] for row in lane_reports] == [40, 40, 40]
        assert result["selection"]["search_provenance"]["node_budget"] == 120

    assert len(evaluations) == 2
    first_evaluation = evaluations[0]
    assert first_evaluation == evaluations[1]
    assert first_evaluation["search_policy"] == "STAGED_COVERAGE_THEN_PREFERENCE"
    assert {row["topology"] for row in first_evaluation["family_lanes"]} == {
        "STRAIGHT_LINEAR_BAND",
        "OFFSET_LINEAR_BAND",
        "CENTRAL_PROCESS_HUB",
    }
    assert first_evaluation["topology_count_explored"] == 3
    assert first_evaluation["topology_count_with_constructed_skeleton"] == 2
    assert first_evaluation["constructed_main_process_skeleton_count"] == 1
    assert r5_metrics["p2d_full_pass_candidate_count"] == 4
    assert r5_metrics["constructed_skeleton_topologies"] == [
        "CENTRAL_PROCESS_HUB",
        "STRAIGHT_LINEAR_BAND",
    ]
    assert len(r5_metrics["constructed_main_process_skeleton_hashes"]) == 1
    assert first_evaluation["p2d_full_pass_distinct_main_process_skeleton_count"] == 1
    lifecycle_by_topology = {
        row["topology"]: row for row in first_evaluation["skeleton_survival"]
    }
    assert lifecycle_by_topology["STRAIGHT_LINEAR_BAND"]["p2d_candidate_count"] == 2
    assert lifecycle_by_topology["STRAIGHT_LINEAR_BAND"]["p2d_full_pass_count"] == 2
    assert lifecycle_by_topology["CENTRAL_PROCESS_HUB"]["p2d_candidate_count"] == 2
    assert lifecycle_by_topology["CENTRAL_PROCESS_HUB"]["p2d_full_pass_count"] == 2
    assert "OFFSET_LINEAR_BAND" not in lifecycle_by_topology
    assert first_evaluation["distinct_runner_up_present"] is False
    assert (
        first_evaluation["distinct_skeleton_first_decisive_component"]
        == "ONLY_ONE_P2D_FULL_PASS_MAIN_SKELETON"
    )

    assert first["canonical_result_hash"] == second["canonical_result_hash"]
    assert first["layout"]["canonical_result_hash"] == second["layout"]["canonical_result_hash"]
    assert first["drawing"]["svg"] == second["drawing"]["svg"]
    assert first["svg_sha256"] == second["svg_sha256"]
    assert first["canonical_result_hash"] == r5_metrics["r5_canonical_result_hash"]
    assert first["svg_sha256"] == r5_metrics["r5_svg_sha256"]
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
                zones[code].get(field)
                for field in ("x", "y", "width_m", "depth_m", "rotation_deg")
            )
            for code in main_zone_codes
        }

    assert main_geometry(new_zones) == main_geometry(old_zones)
    assert main_geometry(new_zones) == main_geometry(r1_zones)
    assert main_geometry(new_zones) == main_geometry(r2_zones)
    assert main_geometry(new_zones) == main_geometry(_zone_map(saved_r3_layout))
    old_groups = _group_edge_facts(old_zones)
    new_groups = _group_edge_facts(new_zones)
    assert old_groups["SUPPORT_GROUP"] == 0
    assert new_groups["SUPPORT_GROUP"] == r5_metrics["support_group_shared_internal_edge_count"]
    # The core stays fully connected, but its direct-edge count does not
    # improve over the hard-valid v2.2.1 baseline and is reported as such.
    assert _direct_core_edges(old_zones) == 2
    assert _direct_core_edges(new_zones) == 2
    assert first["selection"]["search_provenance"]["node_budget"] == 120
    assert first["selection"]["search_provenance"]["node_budget_exhausted"] is False
    assert first["selection"]["search_provenance"]["search_tree_exhausted"] is False
    assert first["selection"]["search_provenance"]["global_optimum_claimed"] is False
