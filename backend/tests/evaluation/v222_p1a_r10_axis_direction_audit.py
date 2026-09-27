"""Evaluation-only R10 audit of Linear process-axis/direction candidate coverage.

The helper redirects one in-process Tool 7 run to a single diagnostic lane.
It does not modify runtime files, public payloads, engineering authorities, or
the production node budget.  Each lane is finite and reports exhaustion
separately from truncation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application import site_layout_preview
from cold_storage.modules.aily.application.mcp_site_layout import invoke_preview_site_layout_tool
from cold_storage.modules.layout.application import validated_candidate_selection as selector
from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    LINEAR_PROCESS_BAND,
    OFFSET_LINEAR_BAND,
    STRAIGHT_LINEAR_BAND,
    StructuralCompositionFamilyV1,
    StructuralTopologyLaneV1,
)

ROOT = Path(__file__).resolve().parents[3]
XINZHAO_FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
XINZHAO_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
DIAGNOSTIC_NODE_LIMIT_PER_VARIANT = 120

LINEAR_VARIANTS = tuple(
    {
        "variant_id": f"{topology}_{axis}_{direction}",
        "topology": topology,
        "axis": axis,
        "direction": direction,
    }
    for topology in (STRAIGHT_LINEAR_BAND, OFFSET_LINEAR_BAND)
    for axis in ("X", "Y")
    for direction in ("POSITIVE", "NEGATIVE")
)


def _lane_summary(lane: Mapping[str, Any]) -> dict[str, Any]:
    family = lane.get("family", lane.get("composition_family"))
    return {
        "topology": lane.get("topology"),
        "family": dict(family) if isinstance(family, Mapping) else None,
    }


def _production_lane_summary(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    lanes = evaluation.get("family_lanes", [])
    summaries: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, Mapping):
            continue
        phases = lane.get("phases", [])
        phase_summaries: list[dict[str, Any]] = []
        for phase in phases:
            if not isinstance(phase, Mapping):
                continue
            generation = phase.get("main_process_skeleton_generation", {})
            if not isinstance(generation, Mapping):
                generation = {}
            attempts = generation.get("construction_attempts", [])
            phase_summaries.append(
                {
                    key: phase.get(key)
                    for key in (
                        "search_phase",
                        "node_budget",
                        "visited_nodes",
                        "complete_candidates",
                        "distinct_main_process_skeleton_count",
                        "node_budget_exhausted",
                        "search_tree_exhausted",
                    )
                }
                | {
                    "construction_search_truncated": generation.get(
                        "construction_search_truncated"
                    ),
                    "constructed_candidate_count": generation.get("constructed_candidate_count"),
                    "root_count": len(generation.get("root_preflight_ordering", [])),
                    "construction_attempt_count": len(attempts),
                    "construction_attempts": attempts,
                }
            )
        summaries.append(
            {
                "topology": lane.get("topology"),
                "family": lane.get("composition_family"),
                "lane_node_budget": lane.get("lane_node_budget"),
                "global_budget_before_lane": lane.get("global_budget_before_lane"),
                "global_budget_after_lane": lane.get("global_budget_after_lane"),
                "visited_nodes": lane.get("visited_nodes"),
                "node_budget_exhausted": lane.get("node_budget_exhausted"),
                "search_tree_exhausted": lane.get("search_tree_exhausted"),
                "complete_candidates": lane.get("complete_candidates"),
                "phases": phase_summaries,
            }
        )
    visits = sum(int(row.get("visited_nodes") or 0) for row in summaries)
    return {
        "production_budget": 120,
        "placement_node_visits": visits,
        "placement_nodes_remaining": 120 - visits,
        "lane_reports": summaries,
    }


def _write_evidence_pack(matrix: Mapping[str, Any], output_dir: Path) -> None:
    """Write the task's split evidence views from one deterministic matrix run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = matrix["variants"]
    skeleton_rows = [
        {"variant_id": variant["variant_id"], **skeleton}
        for variant in variants
        for skeleton in variant["skeletons"]
    ]
    p2d_rows = [
        {
            "variant_id": variant["variant_id"],
            "topology": variant["topology"],
            "axis": variant["axis"],
            "direction": variant["direction"],
            "tool7_result": variant["tool7_result"],
            "project_layout_validated": variant["project_layout_validated"],
            "p2_complete": variant["p2_complete"],
            "access_pass_count": variant["access_pass_count"],
            "access_requirement_count": variant["access_requirement_count"],
            "truck_route_validated": variant["truck_route_validated"],
            "building_footprint_present": variant["building_footprint_present"],
            "skeletons": [
                {
                    key: skeleton.get(key)
                    for key in (
                        "hash",
                        "tail_admissible",
                        "tail_search_started",
                        "p2c_complete_candidate_count",
                        "p2d_reached",
                        "p2d_full_pass_count",
                        "first_failure_stage",
                        "first_failure_reason",
                    )
                }
                for skeleton in variant["skeletons"]
                if skeleton.get("tail_admissible") is True
            ],
        }
        for variant in variants
    ]
    preflight_rows = [
        {
            "variant_id": variant["variant_id"],
            "topology": variant["topology"],
            "axis": variant["axis"],
            "direction": variant["direction"],
            "pass_count": variant["packaging_preflight_pass_count"],
            "fail_count": variant["packaging_preflight_fail_count"],
            "unavailable_count": variant["packaging_preflight_unavailable_count"],
            "skeletons": [
                {
                    key: skeleton.get(key)
                    for key in (
                        "hash",
                        "sorting_root",
                        "generation_pattern",
                        "canonical_topology_owner",
                        "canonical_family",
                        "packaging_slot_status",
                        "packaging_slot_exists",
                        "packaging_witness",
                    )
                }
                for skeleton in variant["skeletons"]
            ],
        }
        for variant in variants
    ]
    files = {
        "xinzhao_p1a_r10_axis_direction_matrix.json": {
            "identity": matrix["identity"],
            "fixture": matrix["fixture"],
            "diagnostic_policy": matrix["diagnostic_policy"],
            "current_runtime": matrix["current_runtime"],
            "linear_diagnostic_variant_count": matrix["linear_diagnostic_variant_count"],
            "hub_reference_variant_count": matrix["hub_reference_variant_count"],
            "matrix_complete": matrix["matrix_complete"],
            "variants": [
                {
                    key: variant.get(key)
                    for key in (
                        "variant_id",
                        "topology",
                        "axis",
                        "direction",
                        "lane_budget",
                        "visited_nodes",
                        "root_count",
                        "roots_visited",
                        "face_pair_count",
                        "construction_attempt_count",
                        "search_exhausted",
                        "search_truncated",
                        "distinct_main_skeleton_count",
                        "packaging_preflight_pass_count",
                        "packaging_preflight_fail_count",
                        "packaging_preflight_unavailable_count",
                        "tail_admissible_skeleton_count",
                        "p2d_evaluated_distinct_skeleton_count",
                        "p2d_full_pass_distinct_skeleton_count",
                    )
                }
                for variant in variants
            ],
        },
        "xinzhao_p1a_r10_skeleton_matrix.json": {
            "identity": matrix["identity"],
            "skeletons": skeleton_rows,
        },
        "xinzhao_p1a_r10_preflight_matrix.json": {
            "identity": matrix["identity"],
            "proof_mode": "EXACT_ORTHOGONAL_EVENT_ENUMERATION",
            "preflight_by_variant": preflight_rows,
        },
        "xinzhao_p1a_r10_p2d_matrix.json": {
            "identity": matrix["identity"],
            "p2d_by_variant": p2d_rows,
        },
        "xinzhao_p1a_r10_runtime_gap_analysis.json": {
            "identity": matrix["identity"],
            "current_runtime": matrix["current_runtime"],
            "aggregate": matrix["aggregate"],
            "production_search_accounting": matrix["production_search_accounting"],
            "findings": matrix["findings"],
            "next_implementation_path": matrix["next_implementation_path"],
        },
    }
    for filename, payload in files.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _variant_summary(
    variant: Mapping[str, str],
    evaluation: Mapping[str, Any],
    response: Mapping[str, Any],
    captured_skeletons: list[dict[str, Any]],
) -> dict[str, Any]:
    lanes = evaluation.get("family_lanes", [])
    lane = next(
        (
            row
            for row in lanes
            if isinstance(row, Mapping) and row.get("topology") == variant["topology"]
        ),
        lanes[0] if lanes and isinstance(lanes[0], Mapping) else {},
    )
    phases = lane.get("phases", []) if isinstance(lane, Mapping) else []
    phase = phases[0] if phases and isinstance(phases[0], Mapping) else {}
    generation = phase.get("main_process_skeleton_generation", {})
    if not isinstance(generation, Mapping):
        generation = {}
    topology_diagnostics = evaluation.get("r6_topology_diagnostics", {})
    if not isinstance(topology_diagnostics, Mapping):
        topology_diagnostics = {}

    ownership_rows = topology_diagnostics.get("ownership_matrix", [])
    ownership_by_hash = {
        str(row.get("skeleton_hash")): row
        for row in ownership_rows
        if isinstance(row, Mapping) and isinstance(row.get("skeleton_hash"), str)
    }
    preflight_rows = topology_diagnostics.get("tail_slot_preflight_trace", [])
    preflight_by_hash = {
        str(row.get("skeleton_hash")): row
        for row in preflight_rows
        if isinstance(row, Mapping) and isinstance(row.get("skeleton_hash"), str)
    }
    lifecycle_rows = generation.get("skeleton_tail_lifecycle", [])
    lifecycle_by_hash = {
        str(row.get("skeleton_hash")): row
        for row in lifecycle_rows
        if isinstance(row, Mapping) and isinstance(row.get("skeleton_hash"), str)
    }
    candidates_by_hash = {
        str(row.get("main_process_skeleton_hash")): row
        for row in generation.get("candidates", [])
        if isinstance(row, Mapping) and isinstance(row.get("main_process_skeleton_hash"), str)
    }
    captured_by_hash = {
        str(row.get("hash")): row for row in captured_skeletons if isinstance(row.get("hash"), str)
    }
    discovered_hashes = sorted(
        set(candidates_by_hash)
        | set(preflight_by_hash)
        | set(lifecycle_by_hash)
        | set(captured_by_hash)
    )
    skeletons: list[dict[str, Any]] = []
    for skeleton_hash in discovered_hashes:
        row = candidates_by_hash.get(skeleton_hash, {})
        captured = captured_by_hash.get(skeleton_hash, {})
        geometry = captured.get("skeleton", {})
        if not isinstance(geometry, Mapping):
            geometry = {}
        zones = geometry.get("zone_rectangles", row.get("zone_rectangles", []))
        sorting = next(
            (
                zone
                for zone in zones
                if isinstance(zone, Mapping) and zone.get("zone_code") == "sorting_packaging_room"
            ),
            {},
        )
        ownership = ownership_by_hash.get(skeleton_hash, {})
        preflight = preflight_by_hash.get(skeleton_hash, {})
        lifecycle = lifecycle_by_hash.get(skeleton_hash, {})
        captured_proof = captured.get("preflight", {})
        if not isinstance(captured_proof, Mapping):
            captured_proof = {}
        packaging_exists = preflight.get(
            "packaging_slot_exists", captured_proof.get("legal_slot_exists")
        )
        packaging_status = preflight.get("packaging_preflight_status")
        if packaging_status is None:
            packaging_status = (
                "LEGAL_SLOT_EXISTS"
                if packaging_exists is True
                else "NO_LEGAL_SLOT"
                if packaging_exists is False
                else "UNAVAILABLE"
            )
        proof_witness = captured_proof.get("first_witness_rectangle")
        skeletons.append(
            {
                "hash": skeleton_hash,
                "sorting_root": {key: sorting.get(key) for key in ("x", "y")},
                "generation_pattern": geometry.get(
                    "generation_pattern", row.get("generation_pattern")
                ),
                "discovery_topology": ownership.get(
                    "discovery_topology", geometry.get("discovery_topology")
                ),
                "canonical_topology_owner": ownership.get(
                    "canonical_owner", geometry.get("canonical_topology_owner")
                ),
                "canonical_family": ownership.get(
                    "canonical_family", geometry.get("canonical_family")
                ),
                "packaging_slot_status": packaging_status,
                "packaging_slot_exists": packaging_exists,
                "packaging_witness": (
                    preflight.get("preflight", {}).get("first_witness_rectangle", proof_witness)
                    if isinstance(preflight.get("preflight"), Mapping)
                    else proof_witness
                ),
                "tail_admissible": preflight.get("tail_admissible"),
                "tail_search_started": preflight.get("tail_search_started"),
                "p2c_complete_candidate_count": lifecycle.get("complete_candidate_count"),
                "p2d_reached": lifecycle.get("p2d_reached"),
                "p2d_full_pass_count": lifecycle.get("p2d_full_pass_count"),
                "first_failure_stage": lifecycle.get("first_failure_stage"),
                "first_failure_reason": lifecycle.get("first_failure_reason"),
            }
        )

    attempts = generation.get("construction_attempts", [])
    root_keys = {
        tuple(row.get("sorting_root_mm", []))
        for row in attempts
        if isinstance(row, Mapping) and isinstance(row.get("sorting_root_mm"), list)
    }
    face_pairs = {
        (row.get("raw_side"), row.get("finished_side"))
        for row in attempts
        if isinstance(row, Mapping)
    }
    preflight_pass = sum(
        row.get("packaging_slot_exists") is True for row in preflight_by_hash.values()
    )
    preflight_fail = sum(
        row.get("packaging_slot_exists") is False for row in preflight_by_hash.values()
    )
    preflight_unavailable = sum(
        row.get("packaging_preflight_status") == "UNAVAILABLE" for row in preflight_by_hash.values()
    )
    selected_layout = response.get("layout")
    if not isinstance(selected_layout, Mapping):
        selected_layout = {}

    return {
        **dict(variant),
        "diagnostic_node_limit": DIAGNOSTIC_NODE_LIMIT_PER_VARIANT,
        "lane_budget": lane.get("lane_node_budget") if isinstance(lane, Mapping) else None,
        "visited_nodes": lane.get("visited_nodes") if isinstance(lane, Mapping) else None,
        "root_count": len(generation.get("root_preflight_ordering", [])),
        "roots_visited": len(root_keys),
        "face_pair_count": len(face_pairs),
        "construction_attempt_count": len(attempts),
        "search_exhausted": lane.get("search_tree_exhausted") is True,
        "search_truncated": lane.get("search_tree_exhausted") is not True,
        "distinct_main_skeleton_count": len(skeletons),
        "packaging_preflight_pass_count": preflight_pass,
        "packaging_preflight_fail_count": preflight_fail,
        "packaging_preflight_unavailable_count": preflight_unavailable,
        "tail_admissible_skeleton_count": sum(row["tail_admissible"] is True for row in skeletons),
        "p2d_evaluated_distinct_skeleton_count": sum(
            row["p2d_reached"] is True for row in skeletons
        ),
        "p2d_full_pass_distinct_skeleton_count": sum(
            int(row["p2d_full_pass_count"] or 0) > 0 for row in skeletons
        ),
        "tool7_result": "PASS" if response.get("ok") is True else "NO_SELECTED_LAYOUT",
        "project_layout_validated": selected_layout.get("project_layout_validated"),
        "p2_complete": selected_layout.get("p2_complete"),
        "access_pass_count": selected_layout.get("access_pass_count"),
        "access_requirement_count": selected_layout.get("access_requirement_count"),
        "truck_route_validated": selected_layout.get("truck_route_validated"),
        "building_footprint_present": bool(
            isinstance(selected_layout.get("building_footprint"), Mapping)
            and selected_layout["building_footprint"].get("footprint")
        ),
        "p2d_candidate_count": sum(
            int(row.get("validated_unique_candidates", 0))
            for row in phases
            if isinstance(row, Mapping)
        ),
        "p2d_full_pass_candidate_count": sum(
            int(row.get("p2d_full_pass_candidate_count", 0))
            for row in phases
            if isinstance(row, Mapping)
        ),
        "skeletons": skeletons,
        "root_preflight_rows": generation.get("root_preflight_ordering", []),
        "construction_attempts": attempts,
    }


def run_axis_direction_variant(
    monkeypatch: Any,
    variant: Mapping[str, str],
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one diagnostic lane through the real, unmocked Tool 7 chain."""
    captured: list[dict[str, Any]] = []
    captured_skeletons: list[dict[str, Any]] = []
    original_lane_selector = selector._selector_topology_lanes
    original_select = site_layout_preview.select_validated_placement
    original_preflight = placement_domain._packaging_tail_slot_preflight
    runtime_lanes: list[dict[str, Any]] = []

    def one_lane(site_geometry: Mapping[str, Any], handoff: object | None = None):
        live_lanes = original_lane_selector(site_geometry, handoff)
        if not runtime_lanes:
            runtime_lanes.extend(_lane_summary(lane.to_dict()) for lane in live_lanes)
        if variant["topology"] == CENTRAL_PROCESS_HUB:
            return (next(lane for lane in live_lanes if lane.topology == CENTRAL_PROCESS_HUB),)
        family = StructuralCompositionFamilyV1(
            LINEAR_PROCESS_BAND,
            variant["axis"],
            variant["direction"],
            "R10_DIAGNOSTIC_AXIS_DIRECTION_VARIANT",
        )
        return (StructuralTopologyLaneV1(variant["topology"], family),)

    def bounded_diagnostic_selector(*args: Any, **kwargs: Any) -> Any:
        kwargs["placement_node_budget"] = DIAGNOSTIC_NODE_LIMIT_PER_VARIANT
        result = original_select(*args, **kwargs)
        captured.append(result.internal_evaluation)
        return result

    def capture_preflight(context: Any, skeleton: Any) -> dict[str, Any]:
        proof = original_preflight(context, skeleton)
        captured_skeletons.append(
            {
                "hash": skeleton.main_process_skeleton_hash,
                "skeleton": skeleton.to_evaluation_dict(),
                "preflight": proof,
            }
        )
        return proof

    with monkeypatch.context() as scoped:
        scoped.setattr(selector, "_selector_topology_lanes", one_lane)
        scoped.setattr(placement_domain, "_packaging_tail_slot_preflight", capture_preflight)
        scoped.setattr(
            site_layout_preview,
            "select_validated_placement",
            bounded_diagnostic_selector,
        )
        response = invoke_preview_site_layout_tool(payload)

    if len(captured) != 1:
        raise AssertionError(f"Tool 7 selector capture count was {len(captured)}")
    evaluation = captured[0]
    summary = _variant_summary(variant, evaluation, response, captured_skeletons)
    summary["production_runtime_lanes"] = runtime_lanes
    return summary, evaluation


def run_full_matrix(monkeypatch: Any) -> dict[str, Any]:
    raw = XINZHAO_FIXTURE.read_bytes()
    raw_sha = hashlib.sha256(raw).hexdigest()
    if raw_sha != XINZHAO_SHA256:
        raise AssertionError("canonical Xinzhao fixture bytes changed")
    payload = json.loads(raw)
    variants = [dict(variant) for variant in LINEAR_VARIANTS]
    # The Hub reference retains the live production lane's site-derived axis.
    variants.append(
        {
            "variant_id": "CENTRAL_PROCESS_HUB_REFERENCE",
            "topology": CENTRAL_PROCESS_HUB,
            "axis": "SITE_DERIVED",
            "direction": "UNRESOLVED",
        }
    )
    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for variant in variants:
        summary, evaluation = run_axis_direction_variant(monkeypatch, variant, payload)
        rows.append(summary)
        details[variant["variant_id"]] = evaluation
    runtime_lanes = rows[-1]["production_runtime_lanes"]
    straight_offset = [row for row in runtime_lanes if row["topology"] != CENTRAL_PROCESS_HUB]
    current_axis = straight_offset[0]["family"]["dominant_axis"] if straight_offset else None
    current_direction = (
        straight_offset[0]["family"]["dominant_direction"] if straight_offset else None
    )
    runtime_lane_keys = {
        (
            row["topology"],
            row["family"]["dominant_axis"],
            row["family"]["dominant_direction"],
        )
        for row in runtime_lanes
    }
    unique_skeletons: dict[str, dict[str, Any]] = {}
    for row in rows:
        lane_key = (row["topology"], row["axis"], row["direction"])
        for skeleton in row["skeletons"]:
            identity = str(skeleton["hash"])
            unique_skeletons.setdefault(
                identity,
                {
                    "hash": identity,
                    "discovered_variant": row["variant_id"],
                    "current_runtime_reachable": lane_key in runtime_lane_keys,
                    "tail_admissible": skeleton["tail_admissible"] is True,
                    "p2d_reached": skeleton["p2d_reached"] is True,
                    "p2d_full_pass": int(skeleton["p2d_full_pass_count"] or 0) > 0,
                },
            )
    production_capture: list[dict[str, Any]] = []
    original_select = site_layout_preview.select_validated_placement

    def capture_current_selector(*args: Any, **kwargs: Any) -> Any:
        result = original_select(*args, **kwargs)
        production_capture.append(result.internal_evaluation)
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(site_layout_preview, "select_validated_placement", capture_current_selector)
        current_response = invoke_preview_site_layout_tool(payload)
    if len(production_capture) != 1:
        raise AssertionError("default production Tool 7 selector was not captured exactly once")
    production_search_accounting = _production_lane_summary(production_capture[0])
    runtime_lane_topologies = {row["topology"] for row in runtime_lanes}
    current_runtime_reachable_by_hash: dict[str, bool] = {}
    for row in rows:
        lane_key = (row["topology"], row["axis"], row["direction"])
        lane_reachable = lane_key in runtime_lane_keys or (
            row["topology"] == CENTRAL_PROCESS_HUB
            and CENTRAL_PROCESS_HUB in runtime_lane_topologies
        )
        for skeleton in row["skeletons"]:
            identity = str(skeleton["hash"])
            current_runtime_reachable_by_hash[identity] = (
                current_runtime_reachable_by_hash.get(identity, False) or lane_reachable
            )
    for identity, reachable in current_runtime_reachable_by_hash.items():
        if identity in unique_skeletons:
            unique_skeletons[identity]["current_runtime_reachable"] = reachable
    skeleton_rows = list(unique_skeletons.values())
    aggregate = {
        "distinct_main_skeleton_count": len(skeleton_rows),
        "tail_admissible_distinct_skeleton_count": sum(
            row["tail_admissible"] for row in skeleton_rows
        ),
        "p2d_evaluated_distinct_skeleton_count": sum(row["p2d_reached"] for row in skeleton_rows),
        "p2d_full_pass_distinct_skeleton_count": sum(row["p2d_full_pass"] for row in skeleton_rows),
        "runtime_excluded_admissible_skeleton_found": any(
            row["tail_admissible"] and not row["current_runtime_reachable"] for row in skeleton_rows
        ),
        "runtime_excluded_full_pass_skeleton_found": any(
            row["p2d_full_pass"] and not row["current_runtime_reachable"] for row in skeleton_rows
        ),
        "search_exhausted_variant_count": sum(row["search_exhausted"] for row in rows),
        "search_truncated_variant_count": sum(row["search_truncated"] for row in rows),
        "unique_skeletons": skeleton_rows,
    }
    final_lane = production_search_accounting["lane_reports"][-1]
    production_lane_truncated = final_lane["search_tree_exhausted"] is not True
    if production_search_accounting["placement_nodes_remaining"] > 0:
        unused_node_cause = (
            "FINAL_LANE_INTERNAL_SEARCH_CUTOFF_OR_CAP;GLOBAL_SCHEDULER_DID_NOT_REVISIT_EARLIER_LANES"
            if production_lane_truncated
            else "FINAL_LANE_SEARCH_EXHAUSTED_WITH_NO_REMAINING_BRANCHES"
        )
    else:
        unused_node_cause = "NONE_GLOBAL_BUDGET_CONSUMED"
    findings = {
        "process_axis_selection_docstring_claim": "ORDERING_ONLY",
        "process_axis_selection_actual_effect": (
            "SELECTED_AXIS_IS_THE_ONLY_LINEAR_AXIS_ADMITTED_TO_CURRENT_RUNTIME_LANES"
        ),
        "ordering_only_claim_accurate": False,
        "alternate_axis_currently_enumerated": any(
            row["family"]["dominant_axis"] != current_axis for row in straight_offset
        ),
        "negative_process_direction_currently_enumerated": any(
            row["family"]["dominant_direction"] == "NEGATIVE" for row in straight_offset
        ),
        "diagnostic_distinct_main_skeleton_count": aggregate["distinct_main_skeleton_count"],
        "diagnostic_tail_admissible_distinct_main_skeleton_count": aggregate[
            "tail_admissible_distinct_skeleton_count"
        ],
        "diagnostic_p2d_evaluated_distinct_main_skeleton_count": aggregate[
            "p2d_evaluated_distinct_skeleton_count"
        ],
        "diagnostic_p2d_full_pass_distinct_main_skeleton_count": aggregate[
            "p2d_full_pass_distinct_skeleton_count"
        ],
        "runtime_excluded_admissible_skeleton_found": aggregate[
            "runtime_excluded_admissible_skeleton_found"
        ],
        "runtime_excluded_full_pass_skeleton_found": aggregate[
            "runtime_excluded_full_pass_skeleton_found"
        ],
        "final_production_lane_search_exhausted": final_lane["search_tree_exhausted"],
        "final_production_lane_search_truncated": production_lane_truncated,
        "production_unused_node_cause": unused_node_cause,
        "production_final_lane": final_lane["topology"],
        "infeasibility_proven": False,
        "next_implementation_path": "CONSTRUCTIVE_SEARCH_COVERAGE_REDESIGN",
    }
    return {
        "identity": "v222-p1a-r10-axis-direction-candidate-space-audit@1.0.0",
        "fixture": {
            "path": "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json",
            "sha256": raw_sha,
        },
        "diagnostic_policy": {
            "runtime_persisted": False,
            "tool7_payload_changed": False,
            "diagnostic_budget_is_production_budget": False,
            "node_limit_per_variant": DIAGNOSTIC_NODE_LIMIT_PER_VARIANT,
            "constructor_computational_caps": "CURRENT_RUNTIME_VALUES_UNMODIFIED",
            "same_authoritative_tool7_chain": True,
            "p2d_mocked": False,
        },
        "current_runtime": {
            "linear_lanes": straight_offset,
            "process_axis": current_axis,
            "process_direction": current_direction,
            "alternate_axis_enumerated": len(
                {row["family"]["dominant_axis"] for row in straight_offset}
            )
            > 1,
            "negative_process_direction_enumerated": any(
                row["family"]["dominant_direction"] == "NEGATIVE" for row in straight_offset
            ),
            "process_band_axis_docstring_claim": "ORDERING_ONLY",
            "ordering_only_claim_accurate": False,
        },
        "linear_diagnostic_variant_count": len(LINEAR_VARIANTS),
        "hub_reference_variant_count": 1,
        "matrix_complete": len(rows) == 9
        and {row["variant_id"] for row in rows} == {row["variant_id"] for row in variants},
        "aggregate": aggregate,
        "production_search_accounting": production_search_accounting,
        "default_tool7_response_ok": current_response.get("ok") is True,
        "findings": findings,
        "next_implementation_path": findings["next_implementation_path"],
        "variants": rows,
        "variant_evaluations": details,
    }


def test_r10_axis_direction_matrix_runs_all_variants_with_real_tool7(
    monkeypatch: Any,
) -> None:
    matrix = run_full_matrix(monkeypatch)
    assert matrix["matrix_complete"] is True
    assert matrix["linear_diagnostic_variant_count"] == 8
    assert matrix["hub_reference_variant_count"] == 1
    assert matrix["current_runtime"]["alternate_axis_enumerated"] is False
    assert matrix["current_runtime"]["negative_process_direction_enumerated"] is False
    assert matrix["diagnostic_policy"]["p2d_mocked"] is False
    assert all(
        row["diagnostic_node_limit"] == DIAGNOSTIC_NODE_LIMIT_PER_VARIANT
        for row in matrix["variants"]
    )
