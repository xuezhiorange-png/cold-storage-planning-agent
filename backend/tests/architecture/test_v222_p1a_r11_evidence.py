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


def test_r11_reports_r10_frontier_reachability_and_hard_regression() -> None:
    frontier = _evidence("xinzhao_p1a_r11_r10_frontier_reachability.json")
    regression = _evidence("xinzhao_p1a_r11_cross_fixture_regression.json")

    assert len(frontier["targets"]) == 2
    assert all(target["production_reached"] is False for target in frontier["targets"])
    assert regression["classification"] == "FAIL_REGRESSION"
    assert regression["hard_valid_to_invalid_regression_count"] == 1
