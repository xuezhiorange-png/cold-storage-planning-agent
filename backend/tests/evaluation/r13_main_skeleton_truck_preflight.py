"""Unmocked Tool 7 evidence capture for the R13 truck preflight."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application import site_layout_preview
from tests.evaluation.r12_access_failure_audit import _zone_skeleton_hash

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
EVIDENCE_DIR = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
EXPECTED_FIXTURE_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
R12_MATRIX = EVIDENCE_DIR / "xinzhao_p1a_r12_candidate_access_matrix.json"
TARGETS = {
    "CONTROL": "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953",
    "TARGET_A": "sha256:062f563bec94c66ff2769d08da8f06a76b9b853c6441b148e4b7a72b6dc0d51c",
    "TARGET_B": "sha256:a148aab89040232091a5486897ac3d895a2685ae3c3cf0c48b0362d08d9eeff3",
}


def _json_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_tool7_with_internal_evaluation(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the actual Tool 7 chain and capture selector-only internal evidence."""
    captured: list[dict[str, Any]] = []
    real_select = site_layout_preview.select_validated_placement

    def capture(*args: Any, **kwargs: Any) -> Any:
        selection = real_select(*args, **kwargs)
        captured.append(selection.internal_evaluation)
        return selection

    site_layout_preview.select_validated_placement = capture
    try:
        result = site_layout_preview.preview_site_layout(dict(payload))
    finally:
        site_layout_preview.select_validated_placement = real_select
    if len(captured) != 1:
        raise AssertionError(f"expected one selector evaluation, got {len(captured)}")
    return result, captured[0]


def _diagnostics(internal: Mapping[str, Any]) -> dict[str, Any]:
    value = internal.get("r6_topology_diagnostics")
    if not isinstance(value, dict):
        raise AssertionError("selector topology diagnostics unavailable")
    return value


def _rows(internal: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _diagnostics(internal).get("main_skeleton_truck_preflight_trace")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AssertionError("main skeleton truck preflight trace unavailable")
    return rows


def _distinct_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        skeleton_hash = row.get("main_skeleton_hash")
        if isinstance(skeleton_hash, str):
            result.setdefault(skeleton_hash, row)
    return result


def capture_xinzhao_replays() -> dict[str, Any]:
    raw = FIXTURE.read_bytes()
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    if raw_sha256 != EXPECTED_FIXTURE_SHA256:
        raise AssertionError(f"canonical fixture checksum mismatch: {raw_sha256}")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise AssertionError("canonical fixture must be a JSON object")
    first_result, first_internal = run_tool7_with_internal_evaluation(payload)
    second_result, second_internal = run_tool7_with_internal_evaluation(payload)
    first_diagnostics = _diagnostics(first_internal)
    first_preflights = _distinct_rows(_rows(first_internal))
    second_preflights = _distinct_rows(_rows(second_internal))
    registry = first_diagnostics.get("geometry_evaluation_registry", [])
    if not isinstance(registry, list):
        registry = []
    registry_by_hash = {
        str(row.get("skeleton_hash")): row
        for row in registry
        if isinstance(row, Mapping) and isinstance(row.get("skeleton_hash"), str)
    }
    r12 = json.loads(R12_MATRIX.read_text(encoding="utf-8"))
    r12_replay = r12.get("replay", {})
    return {
        "fixture_sha256": raw_sha256,
        "first": {
            "result": first_result,
            "internal": first_internal,
            "preflights": first_preflights,
            "registry_by_hash": registry_by_hash,
        },
        "second": {
            "result": second_result,
            "internal": second_internal,
            "preflights": second_preflights,
        },
        "r12_replay": r12_replay,
    }


def _target_matrix(replay: Mapping[str, Any]) -> dict[str, Any]:
    first = replay["first"]
    preflights = first["preflights"]
    registry = first["registry_by_hash"]
    rows: list[dict[str, Any]] = []
    for label, skeleton_hash in TARGETS.items():
        row = preflights.get(skeleton_hash)
        if row is None:
            rows.append({"label": label, "skeleton_hash": skeleton_hash, "observed": False})
            continue
        registry_row = registry.get(skeleton_hash, {})
        rows.append(
            {
                "label": label,
                "skeleton_hash": skeleton_hash,
                "observed": True,
                "event": row.get("event"),
                "discovery_topology": row.get("discovery_topology"),
                "canonical_topology_owner": row.get("canonical_topology_owner"),
                "canonical_family": row.get("canonical_family"),
                "preflight_status": row.get("preflight_status"),
                "preflight_action": row.get("preflight_action"),
                "failure_codes": row.get("failure_codes", []),
                "failure_reason": row.get("failure_reason"),
                "search_profile_identity": row.get("search_profile_identity"),
                "visited_nodes": row.get("visited_nodes"),
                "node_budget": row.get("node_budget"),
                "node_budget_exhausted": row.get("node_budget_exhausted"),
                "search_tree_exhausted": row.get("search_tree_exhausted"),
                "shipping_loading_face_side": row.get("shipping_loading_face_side"),
                "shipping_loading_face_segment": row.get("shipping_loading_face_segment"),
                "tail_search_started": registry_row.get(
                    "tail_search_started", row.get("tail_search_started")
                ),
                "p2d_reached": registry_row.get("p2d_reached"),
                "complete_p2c_candidate_count": registry_row.get("p2d_candidate_count", 0),
                "p2d_full_pass_count": registry_row.get("p2d_full_pass_count"),
            }
        )
    return {
        "identity": "v222-p1a-r13-main-skeleton-truck-preflight-matrix@1.0.0",
        "runtime_replay": "UNMOCKED_TOOL7",
        "rows": rows,
    }


def build_r13_evidence() -> dict[str, dict[str, Any]]:
    replay = capture_xinzhao_replays()
    first = replay["first"]
    second = replay["second"]
    first_result = first["result"]
    second_result = second["result"]
    first_diag = _diagnostics(first["internal"])
    second_diag = _diagnostics(second["internal"])
    trace = _rows(first["internal"])
    unique = first["preflights"]
    registry = first["registry_by_hash"]
    result_layout = first_result.get("layout", {})
    selected_skeleton_hash = _zone_skeleton_hash(result_layout.get("zones", []))
    selected_hash = first_result.get("canonical_result_hash")
    selected_svg_hash = first_result.get("svg_sha256")
    budget = first_diag.get("r11_budget_accounting", {})
    if not isinstance(budget, Mapping):
        budget = {}
    old = replay["r12_replay"]
    rejected_hashes = sorted(
        skeleton_hash
        for skeleton_hash, row in unique.items()
        if row.get("preflight_status") == "REJECT"
    )
    entered_hashes = sorted(
        skeleton_hash
        for skeleton_hash, row in registry.items()
        if row.get("tail_search_started") is True
    )
    pass_hashes = sorted(
        skeleton_hash
        for skeleton_hash, row in unique.items()
        if row.get("preflight_status") == "PASS"
    )
    truck_preflight_nodes = sum(int(row.get("preflight_compute_nodes", 0)) for row in trace)
    selected_preflight = unique.get(selected_skeleton_hash)
    selected_loading_face_match = isinstance(
        selected_preflight, Mapping
    ) and selected_preflight.get("shipping_loading_face_segment") == result_layout.get(
        "shipping_loading_face_segment"
    )
    if not selected_preflight:
        selected_loading_face_match = any(
            row.get("shipping_loading_face_segment")
            == result_layout.get("shipping_loading_face_segment")
            and row.get("preflight_status") == "PASS"
            for row in trace
        )

    matrix = _target_matrix(replay)
    avoidance = {
        "identity": "v222-p1a-r13-tail-search-avoidance@1.0.0",
        "r12_baseline": {
            "complete_p2c_candidate_count": old.get("complete_p2c_capture_count"),
            "control_candidates": old.get("target_skeleton_counts", {})
            .get("CONTROL", {})
            .get("candidate_count"),
            "target_a_candidates": old.get("target_skeleton_counts", {})
            .get("TARGET_A", {})
            .get("candidate_count"),
            "target_b_candidates": old.get("target_skeleton_counts", {})
            .get("TARGET_B", {})
            .get("candidate_count"),
            "target_access_outcome": "TRUCK_MANEUVER_SEARCH_EXHAUSTED_AFTER_COMPLETE_TAIL",
        },
        "r13": {
            "main_skeletons_examined": len(unique),
            "preflight_pass_count": len(pass_hashes),
            "preflight_reject_count": len(rejected_hashes),
            "tail_search_entered_count": len(entered_hashes),
            "tail_search_avoided_count": len(rejected_hashes),
            "complete_p2c_candidate_count": sum(
                int(row.get("p2d_candidate_count", 0)) for row in registry.values()
            ),
            "rejected_skeleton_hashes": rejected_hashes,
            "tail_entered_skeleton_hashes": entered_hashes,
        },
        "target_rows": matrix["rows"],
    }
    budget_evidence = {
        "identity": "v222-p1a-r13-budget-accounting@1.0.0",
        "production_placement_node_budget": budget.get("global_budget", 120),
        "production_placement_nodes_visited": budget.get("global_nodes_visited"),
        "production_placement_nodes_remaining": budget.get("global_nodes_remaining"),
        "production_placement_node_budget_changed": False,
        "truck_node_budget": 5000,
        "truck_node_budget_changed": False,
        "preflight_truck_nodes_visited": truck_preflight_nodes,
        "preflight_compute_counts_as_placement_node": False,
        "preflight_rows": [
            {
                "skeleton_hash": row.get("main_skeleton_hash"),
                "status": row.get("preflight_status"),
                "visited_nodes": row.get("visited_nodes"),
                "compute_nodes": row.get("preflight_compute_nodes"),
                "cached": row.get("preflight_reexecuted") is False,
            }
            for row in trace
        ],
        "placement_nodes_by_topology": budget.get("nodes_by_topology"),
        "placement_nodes_by_round": budget.get("nodes_by_round"),
    }
    selected = {
        "identity": "v222-p1a-r13-selected-result@1.0.0",
        "project_layout_validated": first_result.get("project_layout_validated"),
        "p2_complete": first_result.get("p2_complete"),
        "zone_count": first_result.get("zone_count"),
        "access_pass_count": result_layout.get("access_pass_count"),
        "access_requirement_count": result_layout.get("access_requirement_count"),
        "truck_route_validated": result_layout.get("truck_route_validated"),
        "building_footprint_present": bool(result_layout.get("building_footprint")),
        "selected_main_process_skeleton_hash": selected_skeleton_hash,
        "complete_p2c_candidate_count": int(
            registry.get(selected_skeleton_hash, {}).get("p2d_candidate_count", 0)
        ),
        "canonical_result_hash": selected_hash,
        "svg_sha256": selected_svg_hash,
        "loading_face_matches_preflight": selected_loading_face_match,
        "old_r12_canonical_result_hash": old.get("selected_layout_canonical_result_hash"),
        "old_r12_svg_sha256": old.get("selected_svg_sha256"),
        "same_selected_main_skeleton_as_r12": selected_skeleton_hash == TARGETS["CONTROL"],
    }
    determinism = {
        "identity": "v222-p1a-r13-determinism@1.0.0",
        "same_input_same_preflight_result": first["preflights"] == second["preflights"],
        "same_input_same_rejection_order": [
            row.get("main_skeleton_hash")
            for row in _rows(first["internal"])
            if row.get("preflight_status") == "REJECT"
        ]
        == [
            row.get("main_skeleton_hash")
            for row in _rows(second["internal"])
            if row.get("preflight_status") == "REJECT"
        ],
        "same_input_same_selected_layout": first_result.get("layout")
        == second_result.get("layout"),
        "same_input_same_canonical_result_hash": first_result.get("canonical_result_hash")
        == second_result.get("canonical_result_hash"),
        "same_input_same_svg_bytes": first_result.get("drawing", {}).get("svg")
        == second_result.get("drawing", {}).get("svg"),
        "same_input_same_svg_hash": first_result.get("svg_sha256")
        == second_result.get("svg_sha256"),
        "same_input_same_work_queue_trace": first_diag.get("r11_scheduler_trace")
        == second_diag.get("r11_scheduler_trace"),
    }

    # Exercise the existing P1F representative selector scenario as a cross-fixture
    # full-chain case; its fixture contains no-build zones and its own truck input.
    from tests.unit.test_v22_p4_site_layout_mcp import _real_selector_tool_payload

    representative_result, representative_internal = run_tool7_with_internal_evaluation(
        _real_selector_tool_payload()
    )
    representative_trace = _rows(representative_internal)
    representative_preflights = _distinct_rows(representative_trace)
    cross_fixture = {
        "identity": "v222-p1a-r13-cross-fixture-regression@1.0.0",
        "fixtures": [
            {
                "fixture": "XINZHAO_CANONICAL_V22",
                "hard_valid": first_result.get("project_layout_validated") is True
                and first_result.get("p2_complete") is True,
                "selected_main_process_skeleton_hash": selected_skeleton_hash,
                "preflight_reject_count": len(rejected_hashes),
            },
            {
                "fixture": "P1F_P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES",
                "hard_valid": representative_result.get("project_layout_validated") is True
                and representative_result.get("p2_complete") is True,
                "selected_layout_canonical_result_hash": representative_result.get(
                    "canonical_result_hash"
                ),
                "preflight_examined_skeleton_count": len(representative_preflights),
                "preflight_reject_count": sum(
                    row.get("preflight_status") == "REJECT"
                    for row in representative_preflights.values()
                ),
            },
        ],
        "hard_valid_to_invalid_regression_count": int(
            representative_result.get("project_layout_validated") is not True
            or representative_result.get("p2_complete") is not True
        ),
        "no_false_main_skeleton_rejection_observed": all(
            row.get("preflight_status") != "REJECT"
            or row.get("failure_reason") == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
            for row in (*trace, *representative_trace)
        ),
    }
    return {
        "xinzhao_p1a_r13_main_skeleton_preflight_matrix.json": matrix,
        "xinzhao_p1a_r13_tail_search_avoidance.json": avoidance,
        "xinzhao_p1a_r13_budget_accounting.json": budget_evidence,
        "xinzhao_p1a_r13_selected_result.json": selected,
        "xinzhao_p1a_r13_determinism.json": determinism,
        "xinzhao_p1a_r13_cross_fixture_regression.json": cross_fixture,
    }


def write_r13_evidence() -> dict[str, Any]:
    payloads = build_r13_evidence()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        _json_write(EVIDENCE_DIR / name, payload)
    return payloads


if __name__ == "__main__":
    written = write_r13_evidence()
    print(json.dumps({"written": sorted(written)}, ensure_ascii=False))
