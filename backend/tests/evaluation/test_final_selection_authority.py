"""Regression evidence for the P1A final selection authority closure."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
CONTROL = "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
MEANINGFUL_NEW = "sha256:1c5379589c1da63835062ea8943a14d9af8f24611081395a176e4d5ef60709dc"
MILLIMETRE_OFFSET = "sha256:e05ce4ee27571b7e7fb7fdb72517353584455740217651f2f083927ba7ada834"


def test_three_full_pass_candidates_have_geometry_facts_and_comparable_drawings() -> None:
    evidence = json.loads(
        (EVIDENCE / "xinzhao_p1a_final_selection_candidates.json").read_text(encoding="utf-8")
    )
    rows = evidence["candidate_rows"]
    assert evidence["candidate_count"] == 3
    assert evidence["all_candidates_p2d_full_pass"] is True
    assert {row["skeleton_hash"] for row in rows} == {
        CONTROL,
        MEANINGFUL_NEW,
        MILLIMETRE_OFFSET,
    }
    assert all(row["p2d_result"]["project_layout_validated"] is True for row in rows)
    assert all(row["p2d_result"]["p2_complete"] is True for row in rows)
    assert all(row["p2d_result"]["access_pass_count"] == 12 for row in rows)
    assert all(row["p2d_result"]["truck_route_validated"] is True for row in rows)
    for suffix in (
        "selection_candidates.png",
        "candidate_a.png",
        "candidate_b.png",
        "candidate_c.png",
        "candidate_a.svg",
        "candidate_b.svg",
        "candidate_c.svg",
        "before.png",
        "after.png",
        "side_by_side.png",
    ):
        assert (EVIDENCE / f"xinzhao_p1a_final_{suffix}").is_file()
    assert evidence["visuals"]["candidates_canvas"]["same_canvas"] is True
    assert evidence["visuals"]["candidates_canvas"]["same_scale"] is True
    assert evidence["visuals"]["candidates_canvas"]["uncropped"] is True


def test_distinct_layout_selection_is_decided_by_structural_engineering_fact() -> None:
    evidence = json.loads(
        (EVIDENCE / "xinzhao_p1a_final_selection_candidates.json").read_text(encoding="utf-8")
    )
    rows = {row["skeleton_hash"]: row for row in evidence["candidate_rows"]}
    selected = evidence["selection"]

    assert selected["selected_skeleton_hash"] == CONTROL
    assert selected["runner_up_skeleton_hash"] == MILLIMETRE_OFFSET
    assert selected["first_decisive_component"] == "FINISHED_SHIPPING_INTERFACE_ALIGNMENT"
    assert selected["winner_value"] == 1
    assert selected["runner_up_value"] == 0
    assert selected["distinct_skeleton_p2b2_business_objective_used"] is False
    assert selected["distinct_skeleton_canonical_json_tiebreak_used"] is False
    assert selected["project_layout_validated"] is True
    assert selected["p2_complete"] is True

    assert (
        rows[CONTROL]["structural_comparison_key"]
        > rows[MILLIMETRE_OFFSET]["structural_comparison_key"]
    )
    assert (
        rows[CONTROL]["structural_comparison_key"]
        > rows[MEANINGFUL_NEW]["structural_comparison_key"]
    )
    assert evidence["determinism"] == {
        "same_canonical_result_hash": True,
        "same_selected_layout": True,
        "same_svg_bytes": True,
        "same_svg_hash": True,
    }
    assert selected["canonical_json_tiebreak_used"] is True
    assert selected["canonical_json_tiebreak_scope"] == ("SAME_MAIN_PROCESS_SKELETON_TAIL_VARIANTS")
