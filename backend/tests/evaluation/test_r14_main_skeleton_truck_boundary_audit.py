"""Integrity checks for the immutable R14 Tool 7 truck-preflight snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.evaluation.r14_main_skeleton_truck_boundary_audit import (
    EXPECTED_SKELETON_ORDER,
)


@pytest.fixture(scope="module")  # type: ignore[untyped-decorator]
def r14_evidence() -> dict[str, Any]:
    evidence_root = Path(__file__).resolve().parents[3] / "docs/tasks/evidence/v2_2_2_p1a"
    artifact_names = (
        "xinzhao_p1a_r14_skeleton_truck_geometry_matrix.json",
        "xinzhao_p1a_r14_truck_search_tree.json",
        "xinzhao_p1a_r14_rejection_taxonomy.json",
        "xinzhao_p1a_r14_control_pass_chain.json",
        "xinzhao_p1a_r14_control_vs_rejected_geometry_diff.json",
        "xinzhao_p1a_r14_zone_removal_counterfactual.json",
        "xinzhao_p1a_r14_loading_face_counterfactual.json",
        "xinzhao_p1a_r14_local_translation_sensitivity.json",
        "xinzhao_p1a_r14_search_coverage.json",
        "xinzhao_p1a_r14_root_cause_summary.json",
        "xinzhao_p1a_r14_selected_result.json",
        "xinzhao_p1a_r14_determinism.json",
    )
    return {
        name: json.loads((evidence_root / name).read_text(encoding="utf-8"))
        for name in artifact_names
    }


def _artifact(r14_evidence: dict[str, Any], name: str) -> dict[str, Any]:
    value = r14_evidence[name]
    assert isinstance(value, dict)
    return value


def test_r14_snapshot_covers_all_six_unique_real_r13_skeletons(
    r14_evidence: dict[str, Any],
) -> None:
    matrix = _artifact(r14_evidence, "xinzhao_p1a_r14_skeleton_truck_geometry_matrix.json")
    rows = matrix["rows"]
    assert isinstance(rows, list)
    assert [row["skeleton_hash"] for row in rows] == list(EXPECTED_SKELETON_ORDER)
    assert all(row["shipping_channel"] for row in rows)
    assert all(row["shipping_loading_face"] for row in rows)
    assert all(row["truck_entrance"] for row in rows)


def test_control_passes_and_every_reject_is_authoritatively_exhausted(
    r14_evidence: dict[str, Any],
) -> None:
    tree = _artifact(r14_evidence, "xinzhao_p1a_r14_truck_search_tree.json")
    rows = tree["skeletons"]
    assert isinstance(rows, list)
    assert rows[0]["result"]["truck_route_validated"] is True
    assert rows[0]["result"]["search_tree_exhausted"] is True
    assert rows[0]["attempted_node_count"] == rows[0]["visited_nodes_reported"] == 3

    for row in rows[1:]:
        assert row["result"]["status"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
        assert row["result"]["search_tree_exhausted"] is True
        assert row["result"]["node_budget_exhausted"] is False
        assert row["attempted_node_count"] == row["visited_nodes_reported"] == 39
        assert row["attempted_nodes_match_validator"] is True
        assert (
            row["direct_rejected_node_count"] + row["descendant_exhausted_node_count"]
            == row["attempted_node_count"]
        )


def test_rejections_are_multi_causal_but_have_one_repeated_failure_signature(
    r14_evidence: dict[str, Any],
) -> None:
    taxonomy = _artifact(r14_evidence, "xinzhao_p1a_r14_rejection_taxonomy.json")
    rejected = taxonomy["rejected_skeletons"]
    assert isinstance(rejected, list)
    assert len(rejected) == 5
    for row in rejected:
        assert row["first_decisive_failure_class"] == "MULTI_CAUSAL_EXHAUSTION"
        assert row["direct_failure_classes"] == [
            "BOUNDARY_CONFLICT",
            "FINAL_DOCK_NOT_ON_LOADING_FACE",
        ]
        assert row["first_decisive_blocking_zone_codes"] == {}
        assert row["search_tree_exhausted"] is True
        assert row["node_budget_exhausted"] is False

    summary = _artifact(r14_evidence, "xinzhao_p1a_r14_root_cause_summary.json")
    assert summary["common_root_cause"] is True
    assert summary["multi_causal_exhaustion"] is True
    assert summary["root_cause_class"] == "SHIPPING_CHANNEL_LOADING_FACE_AND_BOUNDARY_REACHABILITY"
    assert (
        summary["directly_rejected_node_total"]
        + summary["descendant_search_exhausted_node_total"]
        + summary["selected_pass_chain_node_total"]
        == summary["attempted_node_total"]
    )


def test_counterfactuals_are_evaluation_only_and_do_not_find_a_witness(
    r14_evidence: dict[str, Any],
) -> None:
    alternate = _artifact(r14_evidence, "xinzhao_p1a_r14_loading_face_counterfactual.json")
    assert alternate["evaluation_only"] is True
    assert alternate["current_authority_loading_face_changed"] is False
    assert alternate["alternate_loading_face_pass_count"] == 0
    assert all(row["result"]["truck_route_validated"] is False for row in alternate["rows"])

    removals = _artifact(r14_evidence, "xinzhao_p1a_r14_zone_removal_counterfactual.json")
    assert removals["evaluation_only"] is True
    assert removals["production_candidate"] is False
    assert removals["pass_witnesses"] == []

    translations = _artifact(r14_evidence, "xinzhao_p1a_r14_local_translation_sensitivity.json")
    assert translations["evaluation_only"] is True
    assert translations["no_local_feasible_translation_found"] is True
    assert translations["local_feasibility_witness_found"] is False
    assert translations["nearest_diagnostic_pass"] is None


def test_control_dock_pose_matches_its_loading_face_and_tool7_is_unchanged(
    r14_evidence: dict[str, Any],
) -> None:
    matrix = _artifact(r14_evidence, "xinzhao_p1a_r14_skeleton_truck_geometry_matrix.json")
    control = matrix["rows"][0]
    assert control["final_dock_pose_points_on_loading_face"]
    assert all(control["final_dock_pose_points_on_loading_face"].values())

    selected = _artifact(r14_evidence, "xinzhao_p1a_r14_selected_result.json")
    assert selected["unchanged_from_r13"] is True
    assert selected["project_layout_validated"] is True
    assert selected["p2_complete"] is True
    assert selected["access_pass_count"] == selected["access_requirement_count"] == 12
    assert selected["truck_route_validated"] is True
    assert selected["zone_count"] == 12
    assert selected["building_footprint_present"] is True


def test_same_tool7_input_produces_identical_r14_diagnostic_replays(
    r14_evidence: dict[str, Any],
) -> None:
    determinism = _artifact(r14_evidence, "xinzhao_p1a_r14_determinism.json")
    assert determinism["same_input_same_diagnostic_tree"] is True
    assert determinism["same_input_same_preflight_matrix"] is True
    assert determinism["same_input_same_selected_canonical_hash"] is True
    assert determinism["same_input_same_svg_hash"] is True
