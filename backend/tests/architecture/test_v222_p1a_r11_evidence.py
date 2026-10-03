"""R11 runtime-search outcomes remain explicit and evidence-bound."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _evidence(name: str) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[3]
    path = repository_root / "docs" / "tasks" / "evidence" / "v2_2_2_p1a" / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_r11_budget_evidence_has_no_stranded_nodes_or_prefix_replay() -> None:
    accounting = _evidence("xinzhao_p1a_r11_budget_accounting.json")

    assert accounting["global_budget"] == 120
    assert accounting["global_nodes_visited"] <= accounting["global_budget"]
    assert accounting["replayed_prefix_node_count"] == 0
    assert accounting["unused_global_nodes_with_active_truncated_work"] == 0
    assert accounting["classified_node_total"] == accounting["global_nodes_visited"]


def test_r11_reports_r10_frontier_reachability_without_hard_regression() -> None:
    candidates = _evidence("xinzhao_p1a_r11_candidate_frontier.json")
    frontier = _evidence("xinzhao_p1a_r11_r10_frontier_reachability.json")
    regression = _evidence("xinzhao_p1a_r11_cross_fixture_regression.json")

    assert candidates["distinct_constructed_skeleton_count"] == 11
    assert candidates["packaging_preflight_rejected_distinct_skeleton_count"] == 8
    assert candidates["tail_admissible_distinct_skeleton_count"] == 3
    assert candidates["p2d_evaluated_distinct_skeleton_count"] == 3
    assert candidates["p2d_full_pass_distinct_skeleton_count"] == 1
    assert candidates["selected_skeleton_hash"].endswith(
        "55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
    )
    assert candidates["project_layout_validated"] is True
    assert candidates["access_pass_count"] == candidates["access_requirement_count"]
    assert len(frontier["targets"]) == 2
    assert all(target["production_reached"] is False for target in frontier["targets"])
    assert regression["classification"] == "NO_HARD_VALID_TO_INVALID_REGRESSION"
    assert regression["hard_valid_to_invalid_regression_count"] == 0
