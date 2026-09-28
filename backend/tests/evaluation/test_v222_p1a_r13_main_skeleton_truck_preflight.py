"""Real Tool 7 acceptance for the R13 truck-maneuver necessary preflight."""

from __future__ import annotations

import json
from typing import Any

from tests.evaluation.r13_main_skeleton_truck_preflight import (
    TARGETS,
    capture_xinzhao_replays,
)


def test_real_xinzhao_tool7_preflights_the_control_and_rejects_targets_before_tail() -> None:
    replay = capture_xinzhao_replays()
    first = replay["first"]
    second = replay["second"]
    result = first["result"]
    layout = result["layout"]
    preflights: dict[str, dict[str, Any]] = first["preflights"]
    registry: dict[str, dict[str, Any]] = first["registry_by_hash"]
    survival = {
        row["skeleton_hash"]: row
        for row in first["internal"]["skeleton_survival"]
        if isinstance(row.get("skeleton_hash"), str)
    }

    assert result["project_layout_validated"] is True
    assert result["p2_complete"] is True
    assert result["zone_count"] == 12
    assert layout["access_pass_count"] == 12
    assert layout["access_requirement_count"] == 12
    assert layout["truck_route_validated"] is True
    assert layout.get("building_footprint")

    control = preflights[TARGETS["CONTROL"]]
    assert control["preflight_status"] == "PASS"
    assert control["tail_search_started"] is True
    assert registry[TARGETS["CONTROL"]]["p2d_full_pass_count"] >= 1

    for label in ("TARGET_A", "TARGET_B"):
        row = preflights[TARGETS[label]]
        registry_row = registry[TARGETS[label]]
        assert row["preflight_status"] == "REJECT"
        assert row["failure_codes"] == ["TRUCK_MANEUVER_SEARCH_EXHAUSTED"]
        assert row["search_tree_exhausted"] is True
        assert row["node_budget_exhausted"] is False
        assert row["visited_nodes"] == 39
        assert row["node_budget"] == 5000
        assert row["tail_search_started"] is False
        assert registry_row["tail_search_started"] is False
        assert registry_row["p2d_reached"] is False
        lifecycle = survival[TARGETS[label]]
        assert lifecycle["main_skeleton_truck_preflight_status"] == "REJECT"
        assert lifecycle["first_failure_stage"] == "MAIN_SKELETON_TRUCK_PREFLIGHT"
        assert lifecycle["first_failure_reason"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
        assert lifecycle["tail_search_started"] is False

    selected_skeleton_hash = next(
        row["main_skeleton_hash"]
        for row in preflights.values()
        if row.get("shipping_loading_face_segment") == layout["shipping_loading_face_segment"]
        and row.get("preflight_status") == "PASS"
    )
    assert selected_skeleton_hash == TARGETS["CONTROL"]

    assert first["preflights"] == second["preflights"]
    assert result["layout"] == second["result"]["layout"]
    assert result["canonical_result_hash"] == second["result"]["canonical_result_hash"]
    assert result["drawing"]["svg"] == second["result"]["drawing"]["svg"]
    assert result["svg_sha256"] == second["result"]["svg_sha256"]
    assert (
        first["internal"]["r6_topology_diagnostics"]["r11_scheduler_trace"]
        == second["internal"]["r6_topology_diagnostics"]["r11_scheduler_trace"]
    )

    # Internal preflight evidence must not become a Tool 7 response field.
    assert "main_skeleton_truck_preflight_trace" not in json.dumps(result, sort_keys=True)
    assert result["selection"]["search_provenance"]["node_budget"] == 120
