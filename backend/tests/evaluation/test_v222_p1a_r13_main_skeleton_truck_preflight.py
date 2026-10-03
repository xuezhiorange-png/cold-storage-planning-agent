"""Integrity checks for the immutable R13 truck-preflight evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTROL = "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
TARGET_A = "sha256:062f563bec94c66ff2769d08da8f06a76b9b853c6441b148e4b7a72b6dc0d51c"
TARGET_B = "sha256:a148aab89040232091a5486897ac3d895a2685ae3c3cf0c48b0362d08d9eeff3"


def _evidence(name: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3] / "docs/tasks/evidence/v2_2_2_p1a"
    value = json.loads((root / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_r13_checked_in_preflight_matrix_is_historically_consistent() -> None:
    matrix = _evidence("xinzhao_p1a_r13_main_skeleton_preflight_matrix.json")
    selected = _evidence("xinzhao_p1a_r13_selected_result.json")
    budget = _evidence("xinzhao_p1a_r13_budget_accounting.json")
    rows = {row["skeleton_hash"]: row for row in matrix["rows"]}

    assert matrix["identity"] == "v222-p1a-r13-main-skeleton-truck-preflight-matrix@1.0.0"
    assert matrix["runtime_replay"] == "UNMOCKED_TOOL7"
    assert set(rows) == {CONTROL, TARGET_A, TARGET_B}
    assert rows[CONTROL]["preflight_status"] == "PASS"
    assert rows[CONTROL]["tail_search_started"] is True
    assert rows[CONTROL]["p2d_reached"] is True
    assert rows[CONTROL]["p2d_full_pass_count"] == 2
    for skeleton_hash in (TARGET_A, TARGET_B):
        row = rows[skeleton_hash]
        assert row["preflight_status"] == "REJECT"
        assert row["failure_codes"] == ["TRUCK_MANEUVER_SEARCH_EXHAUSTED"]
        assert row["search_tree_exhausted"] is True
        assert row["node_budget_exhausted"] is False
        assert row["visited_nodes"] == 39
        assert row["tail_search_started"] is False

    assert selected["selected_main_process_skeleton_hash"] == CONTROL
    assert selected["project_layout_validated"] is True
    assert selected["p2_complete"] is True
    assert selected["access_pass_count"] == selected["access_requirement_count"] == 12
    assert selected["truck_route_validated"] is True
    assert selected["building_footprint_present"] is True
    assert budget["production_placement_node_budget"] == 120
    assert budget["production_placement_node_budget_changed"] is False
    assert budget["truck_node_budget"] == 5000
    assert budget["truck_node_budget_changed"] is False
