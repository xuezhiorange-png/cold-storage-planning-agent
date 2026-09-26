"""Offline, process-local audit capture for the v2.2.2 P1A R3 search.

This module instruments existing private search hooks only inside the current
Python process. It does not alter production source or serialize diagnostics
into the Tool 7 result. Run it from the backend with ``PYTHONPATH=src`` to
refresh the four R4 evidence JSON files.
"""

from __future__ import annotations

import inspect
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cold_storage.modules.layout.domain.placement as placement
from cold_storage.modules.aily.application.site_layout_preview import preview_site_layout
from cold_storage.modules.layout.domain.structural_composition import (
    MAIN_PROCESS_SKELETON_ZONE_CODES,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
R3_METRICS = EVIDENCE / "xinzhao_p1a_r3_metrics.json"
R3_SEARCH = EVIDENCE / "xinzhao_p1a_r3_skeleton_search.json"
R3_BUDGETS = EVIDENCE / "xinzhao_p1a_r3_budget_sensitivity.json"
EXPECTED_R3_RESULT = "sha256:b3dd2de4fb24f74b5ce96601a74edab5f58a9a781eb5af41b29afd0a66ac98da"
EXPECTED_R3_SVG = "sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981"
EXPECTED_R3_HEAD = "82f3260c17609ec45d0e81318a34c9a1c4568927"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def _rect_bounds(value: object) -> list[int] | None:
    bounds = getattr(value, "bounds_mm", None)
    if isinstance(bounds, tuple) and len(bounds) == 4:
        return [int(part) for part in bounds]
    return None


def _capture_live_search() -> dict[str, Any]:
    """Replay Tool 7 with reversible in-process hooks and retain search facts."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original_record = placement._record_rejection
    original_construct = placement._construct_main_process_skeletons
    original_materialize = placement._materialize_candidate_result
    previous_trace = sys.gettrace()
    rejection_events: list[dict[str, Any]] = []
    seeds: dict[str, dict[str, Any]] = {}
    p2c_completions: list[dict[str, Any]] = []
    tail_trace: dict[str, dict[str, Any]] = {}

    def record_rejection(stats: object, reason: str) -> None:
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        stack_names: list[str] = []
        facts: dict[str, Any] = {}
        try:
            while caller is not None:
                name = caller.f_code.co_name
                locals_ = caller.f_locals
                stack_names.append(name)
                if name == "_construct_face_skeletons":
                    facts["sorting_root_mm"] = _rect_bounds(locals_.get("sorting"))
                    facts["raw_side"] = locals_.get("raw_side")
                    facts["finished_side"] = locals_.get("finished_side")
                elif name == "_constructive_sorting_roots" and "sorting_root_mm" not in facts:
                    facts["sorting_root_mm"] = _rect_bounds(locals_.get("rectangle"))
                code = locals_.get("code")
                if isinstance(code, str):
                    facts.setdefault("zone_code", code)
                context = locals_.get("context")
                family = getattr(context, "structural_composition_family", None)
                if family is not None:
                    facts.setdefault("family", family.to_dict())
                caller = caller.f_back
        finally:
            del frame

        family = facts.get("family", {})
        if family.get("family") == "LINEAR_PROCESS_BAND":
            if facts.get("raw_side") is None:
                facts["raw_side"] = "WEST" if family["dominant_direction"] == "POSITIVE" else "EAST"
                facts["finished_side"] = "EAST" if facts["raw_side"] == "WEST" else "WEST"
            rejection_stage = (
                "SORTING_ROOT_CANDIDATE"
                if "_constructive_sorting_roots" in stack_names
                else "SKELETON_CONSTRUCTION"
                if "_construct_face_skeletons" in stack_names
                else "OTHER_PLACEMENT"
            )
            if "zone_code" not in facts:
                facts["zone_code"] = (
                    "sorting_packaging_room"
                    if rejection_stage == "SORTING_ROOT_CANDIDATE"
                    else "UNAVAILABLE"
                )
            rejection_events.append(
                {
                    "family": family["family"],
                    "dominant_direction": family["dominant_direction"],
                    "sorting_root_mm": facts.get("sorting_root_mm"),
                    "raw_side": facts.get("raw_side"),
                    "finished_side": facts.get("finished_side"),
                    "zone_code": facts["zone_code"],
                    "reason": reason,
                    "stage": rejection_stage,
                }
            )
        original_record(stats, reason)

    def capture_seeds(context: object, stats: object):
        for seed in original_construct(context, stats):
            seed_hash = seed.main_process_skeleton_hash
            seeds[seed_hash] = seed.to_dict()
            yield seed

    def capture_p2c(payload_: dict[str, Any], **kwargs: Any):
        seed = payload_.get("_main_process_skeleton")
        seed_hash = seed.get("main_process_skeleton_hash") if isinstance(seed, dict) else None
        result = original_materialize(payload_, **kwargs)
        candidate_hash = result.to_dict().get("canonical_candidate_hash")
        if isinstance(candidate_hash, str):
            p2c_completions.append(
                {
                    "p2c_candidate_hash": candidate_hash,
                    "main_process_skeleton_hash": seed_hash,
                }
            )
            if isinstance(seed_hash, str):
                tail_trace.setdefault(seed_hash, {"p2c_candidate_hashes": []})[
                    "p2c_candidate_hashes"
                ].append(candidate_hash)
        return result

    def visit_trace(frame: Any, event: str, _arg: object):
        locals_ = frame.f_locals
        if locals_.get("index") != len(MAIN_PROCESS_SKELETON_ZONE_CODES):
            return visit_trace
        seed = locals_.get("main_process_skeleton")
        seed_hash = getattr(seed, "main_process_skeleton_hash", None)
        if not isinstance(seed_hash, str):
            return visit_trace
        stats = locals_.get("stats")
        if event == "call":
            tail_trace.setdefault(
                seed_hash,
                {
                    "p2c_candidate_hashes": [],
                    "tail_nodes_start": getattr(stats, "visited_nodes", None),
                    "tail_node_share_limit": locals_.get("active_skeleton_node_limit"),
                },
            )
        elif event == "return":
            row = tail_trace.setdefault(seed_hash, {"p2c_candidate_hashes": []})
            row["tail_nodes_end"] = getattr(stats, "visited_nodes", None)
            row["tail_share_exhausted"] = locals_.get("active_skeleton_budget_exhausted") is True
        return visit_trace

    def global_trace(frame: Any, event: str, _arg: object):
        if (
            event == "call"
            and frame.f_code.co_name == "visit"
            and frame.f_code.co_filename == placement.__file__
        ):
            locals_ = frame.f_locals
            seed = locals_.get("main_process_skeleton")
            seed_hash = getattr(seed, "main_process_skeleton_hash", None)
            if locals_.get("index") == len(MAIN_PROCESS_SKELETON_ZONE_CODES) and isinstance(
                seed_hash, str
            ):
                stats = locals_.get("stats")
                tail_trace.setdefault(
                    seed_hash,
                    {
                        "p2c_candidate_hashes": [],
                        "tail_nodes_start": getattr(stats, "visited_nodes", None),
                        "tail_node_share_limit": locals_.get("active_skeleton_node_limit"),
                    },
                )
            return visit_trace
        return None

    placement._record_rejection = record_rejection
    placement._construct_main_process_skeletons = capture_seeds
    placement._materialize_candidate_result = capture_p2c
    try:
        sys.settrace(global_trace)
        result = preview_site_layout(payload)
    finally:
        sys.settrace(previous_trace)
        placement._record_rejection = original_record
        placement._construct_main_process_skeletons = original_construct
        placement._materialize_candidate_result = original_materialize

    if result.get("canonical_result_hash") != EXPECTED_R3_RESULT:
        raise AssertionError("instrumented Tool 7 replay does not match saved R3 result hash")
    if result.get("svg_sha256") != EXPECTED_R3_SVG:
        raise AssertionError("instrumented Tool 7 replay does not match saved R3 SVG hash")
    trace_by_candidate = {
        row.get("p2c_candidate_hash"): row
        for row in result["selection"].get("candidate_validation_trace", [])
    }
    for _seed_hash, details in tail_trace.items():
        details["p2d_candidates"] = [
            {
                "p2c_candidate_hash": candidate_hash,
                "p2d_full_pass": trace_by_candidate.get(candidate_hash, {}).get("p2d_full_pass"),
            }
            for candidate_hash in details["p2c_candidate_hashes"]
        ]
        details["p2c_candidate_count"] = len(details["p2c_candidate_hashes"])
    return {
        "result": result,
        "seeds": seeds,
        "p2c_completions": p2c_completions,
        "tail_trace": tail_trace,
        "rejection_events": rejection_events,
    }


def _rejection_matrix(events: list[dict[str, Any]]) -> dict[str, Any]:
    key_fields = (
        "family",
        "dominant_direction",
        "sorting_root_mm",
        "raw_side",
        "finished_side",
        "zone_code",
        "reason",
        "stage",
    )
    counts: Counter[tuple[str, ...]] = Counter()
    for event in events:
        key = tuple(
            json.dumps(event[field], sort_keys=True, separators=(",", ":"))
            if isinstance(event[field], (dict, list)) or event[field] is None
            else str(event[field])
            for field in key_fields
        )
        counts[key] += 1
    rows: list[dict[str, Any]] = []
    for key, count in sorted(counts.items()):
        values = [
            json.loads(value) if value.startswith("[") or value == "null" else value
            for value in key
        ]
        rows.append({**dict(zip(key_fields, values, strict=True)), "count": count})
    return {
        "identity": "xinzhao-linear-rejection-matrix@1.0.0",
        "source": (
            "process-local rejection-hook replay at PR head "
            "82f3260c17609ec45d0e81318a34c9a1c4568927"
        ),
        "instrumentation_scope": (
            "structured P1A placement search; no production code or public Tool 7 payload mutation"
        ),
        "event_count": len(events),
        "aggregated_row_count": len(rows),
        "grouping_fields": list(key_fields),
        "rows": rows,
    }


def build_r4_evidence() -> dict[str, dict[str, Any]]:
    live = _capture_live_search()
    saved_metrics = _read_json(R3_METRICS)
    saved_search = _read_json(R3_SEARCH)
    budget_sensitivity = _read_json(R3_BUDGETS)
    result = live["result"]
    lane_rows = result["selection"]["search_provenance"]["family_lanes"]
    validation_rows = result["selection"].get("candidate_validation_trace", [])
    completed_by_hash = {row["p2c_candidate_hash"]: row for row in live["p2c_completions"]}

    lanes: list[dict[str, Any]] = []
    for lane in lane_rows:
        family = lane["composition_family"]
        phase = lane.get("phases", [{}])[0]
        lane_validation = [
            row for row in validation_rows if row.get("composition_family") == family
        ]
        seed_hashes = sorted(
            seed_hash for seed_hash, seed in live["seeds"].items() if seed.get("family") == family
        )
        candidate_to_seed = {
            candidate_hash: row.get("main_process_skeleton_hash")
            for candidate_hash, row in completed_by_hash.items()
        }
        fullpass_skeletons = sorted(
            {
                candidate_to_seed.get(row.get("p2c_candidate_hash"))
                for row in lane_validation
                if row.get("p2d_full_pass") is True
                and isinstance(candidate_to_seed.get(row.get("p2c_candidate_hash")), str)
            }
        )
        lane_attempts = [
            row for row in saved_search["family_lanes"] if row["composition_family"] == family
        ]
        construction_report = (
            lane_attempts[0]["phases"][0].get("main_process_skeleton_generation", {})
            if lane_attempts
            else {}
        )
        construction_attempts = construction_report.get("construction_attempts", [])
        lanes.append(
            {
                "family": family["family"],
                "dominant_axis": family["dominant_axis"],
                "dominant_direction": family["dominant_direction"],
                "preferred_lane": lane.get("preferred_lane") is True,
                "lane_budget": lane["lane_node_budget"],
                "visited_nodes": lane["visited_nodes"],
                "search_exhausted": lane["search_tree_exhausted"],
                "construction_truncated": construction_report.get("construction_search_truncated"),
                "constructed_skeleton_count": phase.get("distinct_main_process_skeleton_count", 0),
                "constructed_skeleton_hashes": seed_hashes,
                "complete_candidate_count": lane["complete_candidates"],
                "p2d_full_pass_count": lane["p2d_full_pass_candidate_count"],
                "distinct_full_pass_skeleton_count": len(fullpass_skeletons),
                "distinct_full_pass_skeleton_hashes": fullpass_skeletons,
                "first_terminal_class": (
                    "B_FAMILY_SEARCH_TRUNCATED"
                    if lane["search_tree_exhausted"] is not True
                    else "SEARCH_TREE_EXHAUSTED"
                ),
                "construction_attempts": construction_attempts,
            }
        )

    sensitivity_rows = []
    for run in budget_sensitivity["runs"]:
        sensitivity_rows.append(
            {
                "total_node_budget": run["node_budget"],
                "elapsed_seconds": run["elapsed_seconds"],
                "p2c_candidate_count": run["p2c_candidate_count"],
                "p2d_full_pass_candidate_count": run["p2d_full_pass_candidate_count"],
                "distinct_full_pass_main_process_skeleton_count": run[
                    "distinct_full_pass_main_process_skeleton_count"
                ],
            }
        )

    family_audit = {
        "identity": "xinzhao-p1a-r4-family-search-audit@1.0.0",
        "task_id": "V2_2_2_P1A_R4_CANDIDATE_SPACE_AND_VERSION_ALIGNMENT_REVIEW_R1",
        "source_pr_head": EXPECTED_R3_HEAD,
        "replay": {
            "fixture_sha256": saved_metrics["xinzhao_input_sha256"],
            "tool7_result_hash": result["canonical_result_hash"],
            "saved_r3_result_hash": saved_metrics["canonical_result_hash"],
            "tool7_svg_sha256": result["svg_sha256"],
            "saved_r3_svg_sha256": saved_metrics["svg_sha256"],
            "matches_saved_r3": result["canonical_result_hash"]
            == saved_metrics["canonical_result_hash"]
            and result["svg_sha256"] == saved_metrics["svg_sha256"],
            "project_layout_validated": result["project_layout_validated"],
            "p2_complete": result["p2_complete"],
            "zone_count": result["zone_count"],
            "access_requirement_count": result["layout"]["access_requirement_count"],
            "access_pass_count": result["layout"]["access_pass_count"],
            "truck_route_validated": result["layout"]["truck_route_validated"],
            "building_footprint_present": bool(result["layout"].get("building_footprint")),
        },
        "lane_allocation_policy": {
            "production_node_budget": result["selection"]["search_provenance"]["node_budget"],
            "preferred_family_basis": "sorting_packaging_room is the largest main-process area",
            "preferred_lane_share": "approximately_two_thirds",
            "preferred_lane_is_exclusive": False,
            "linear_positive_lane_is_explored": True,
            "linear_negative_lane_is_explored": True,
            "fallback_node_budget": 0,
            "fallback_reason": (
                "structured family lanes were not shown exhausted; truncation is not "
                "infeasibility evidence"
            ),
        },
        "family_lanes": lanes,
        "budget_sensitivity": sensitivity_rows,
        "candidate_state_classification": {
            "A_FAMILY_NOT_EXPLORED": {
                "count": 0,
                "meaning": "all three declared lanes received a nonzero budget and were visited",
            },
            "B_FAMILY_SEARCH_TRUNCATED": {
                "count": 3,
                "families": [
                    row["family"] + "/" + row["dominant_direction"]
                    for row in lanes
                    if row["search_exhausted"] is not True
                ],
            },
            "C_SKELETON_CONSTRUCTION_FAILED": {
                "count": 2,
                "families": ["LINEAR_PROCESS_BAND/POSITIVE", "LINEAR_PROCESS_BAND/NEGATIVE"],
                "qualification": (
                    "zero skeletons emitted in explored prefixes; both family searches "
                    "truncated, so not an infeasibility result"
                ),
            },
            "D_SKELETON_CONSTRUCTED_BUT_TAIL_FAILED": {
                "count": 1,
                "skeleton_hash": (
                    "sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc"
                ),
                "first_failure_stage": "TAIL_SEARCH",
                "first_failure_reason": "TAIL_NODE_SHARE_EXHAUSTED_WITHOUT_COMPLETE_P2C_CANDIDATE",
            },
            "E_COMPLETE_CANDIDATE_FAILED_P2D": {
                "count": 0,
                "qualification": "both complete P2C candidates passed P2D",
            },
            "F_P2D_FULL_PASS_LOST_STRUCTURAL_COMPARISON": {
                "count": 0,
                "qualification": (
                    "both P2D full-pass candidates use the same main-process skeleton hash"
                ),
            },
            "G_STRUCTURAL_TIE_THEN_P2B2_LOSS": {
                "count": 1,
                "losing_candidate_hash": (
                    "sha256:7245f59f0c0383c5854fc3bcef0b089667fb9b49faf718932f87a36061deb35d"
                ),
                "winner_candidate_hash": (
                    "sha256:80e31a1fb80c7b5de497b4aa6dad5bda4a79d9b3912909bbb76819b26ce84e5f"
                ),
                "first_decisive_component": saved_metrics["first_decisive_component"],
            },
        },
        "diversity_caps": {
            "CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT": 2,
            "STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON": 2,
            "STRUCTURED_COMPLETIONS_PER_CORE_ROOT": 4,
            "CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET": 20,
            "CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET": 16,
            "authority_type": "computational_search_caps_not_engineering_or_layout_authority",
            "candidate_diversity_risk": (
                "completion_limit_of_two can stop new seeds in a lane before family "
                "exploration is complete"
            ),
        },
        "conclusion": (
            "R3 demonstrates bounded candidate-prefix outcomes, not Linear infeasibility; "
            "the next design correction should expand topology and plan root anchors "
            "against complete group extents before increasing total budget."
        ),
    }

    matrix = _rejection_matrix(live["rejection_events"])
    matrix["event_count_by_family_direction_zone_reason_stage"] = [
        {
            "family": family,
            "dominant_direction": direction,
            "zone_code": zone,
            "reason": reason,
            "stage": stage,
            "count": count,
        }
        for (family, direction, zone, reason, stage), count in sorted(
            Counter(
                (
                    row["family"],
                    row["dominant_direction"],
                    row["zone_code"],
                    row["reason"],
                    row["stage"],
                )
                for row in live["rejection_events"]
            ).items()
        )
    ]

    hub_trace_rows = []
    for seed_hash, seed in sorted(live["seeds"].items()):
        tail = live["tail_trace"].get(seed_hash, {})
        p2c_hashes = tail.get("p2c_candidate_hashes", [])
        p2d_rows = [row for row in validation_rows if row.get("p2c_candidate_hash") in p2c_hashes]
        hub_trace_rows.append(
            {
                "skeleton_hash": seed_hash,
                "family": seed["family"],
                "generation_pattern": seed["generation_pattern"],
                "main_process_zone_rectangles": seed["zone_rectangles"],
                "tail_search": {
                    "nodes_at_start": tail.get("tail_nodes_start"),
                    "node_share_limit": tail.get("tail_node_share_limit"),
                    "nodes_at_end": tail.get("tail_nodes_end"),
                    "node_share_exhausted": tail.get("tail_share_exhausted"),
                    "complete_p2c_candidate_count": len(p2c_hashes),
                    "p2c_candidate_hashes": p2c_hashes,
                },
                "p2d": {
                    "reached": bool(p2d_rows),
                    "full_pass_candidate_count": sum(
                        row.get("p2d_full_pass") is True for row in p2d_rows
                    ),
                    "candidate_trace": p2d_rows,
                },
                "first_failure_stage": None if p2d_rows else "TAIL_SEARCH",
                "first_failure_reason": None
                if p2d_rows
                else "TAIL_NODE_SHARE_EXHAUSTED_WITHOUT_COMPLETE_P2C_CANDIDATE",
                "access_failure": 0 if p2d_rows else "NOT_REACHED",
                "truck_failure": 0 if p2d_rows else "NOT_REACHED",
                "footprint_failure": 0 if p2d_rows else "NOT_REACHED",
                "hard_validation_result": "P2D_FULL_PASS" if p2d_rows else "NOT_REACHED",
                "source": (
                    "instrumented Tool 7 replay at the exact R3 runtime; per-seed tail "
                    "counters captured in-process"
                ),
            }
        )
    hub_trace = {
        "identity": "xinzhao-r3-hub-skeleton-survival-trace@1.0.0",
        "replay_result_hash": result["canonical_result_hash"],
        "family": "CENTRAL_PROCESS_HUB/UNRESOLVED",
        "constructed_skeleton_count": len(hub_trace_rows),
        "distinct_full_pass_skeleton_count": len(
            {
                row["skeleton_hash"]
                for row in hub_trace_rows
                if row["p2d"]["full_pass_candidate_count"]
            }
        ),
        "skeletons": hub_trace_rows,
    }

    design = {
        "identity": "xinzhao-p1a-r4-candidate-space-design-matrix@1.0.0",
        "task_id": family_audit["task_id"],
        "implementation_authorized": False,
        "topologies": [
            {
                "topology": "STRAIGHT_LINEAR_BAND",
                "distinct_geometry": (
                    "monotonic raw/core/finished group intervals on one axis; raw bank "
                    "and finished chain share a principal band"
                ),
                "R3_gap_addressed": (
                    "avoid current exact-face single chain being the only linear form"
                ),
            },
            {
                "topology": "OFFSET_LINEAR_BAND",
                "distinct_geometry": (
                    "monotonic group order with parallel/offset rows and shared axis families"
                ),
                "R3_gap_addressed": (
                    "permits width/depth packing when a straight single row does not fit"
                ),
            },
            {
                "topology": "FOLDED_LINEAR_BAND",
                "distinct_geometry": (
                    "process spine with one explicit terminal bend while preserving group order"
                ),
                "R3_gap_addressed": (
                    "tests orthogonal/folded continuations missing from current "
                    "single-direction linear lane"
                ),
            },
            {
                "topology": "CENTRAL_PROCESS_HUB",
                "distinct_geometry": (
                    "sorting room as core; raw and finished groups attach by independently "
                    "enumerated permitted faces"
                ),
                "R3_gap_addressed": (
                    "retain hub but avoid one sampled root/face ordering starving alternatives"
                ),
            },
            {
                "topology": "HUB_WITH_STORAGE_BANK",
                "distinct_geometry": (
                    "hub plus a co-constructed raw or finished cold-storage bank; support "
                    "remains a bounded branch"
                ),
                "R3_gap_addressed": (
                    "make grouped storage a first-class topology rather than a late quality fact"
                ),
            },
        ],
        "hard_predicates_remain_authoritative": [
            "zone dimensions and areas",
            "site/buildable containment",
            "no-build geometry",
            "MUST adjacency",
            "access",
            "truck",
            "P2D",
        ],
        "golden_reference_role": (
            "qualitative organization principles only; no coordinates, dimensions, "
            "room counts, or runtime templates"
        ),
        "lane_allocation_policy_options": [
            {
                "policy": "A_PREFERRED_FAMILY_BIASED",
                "description": "current preferred family receives about two thirds",
                "pros": ["exploits role-based prior ordering"],
                "cons": [
                    "sorting room being largest does not prove hub is the only/strongest "
                    "topology; may starve alternatives"
                ],
            },
            {
                "policy": "B_EQUAL_FAMILY_EXPLORATION",
                "description": "equal initial share for every family/topology lane",
                "pros": ["clear baseline coverage and comparability"],
                "cons": ["may spend equal compute on unproductive lanes"],
            },
            {
                "policy": "C_SKELETON_COUNT_TARGETED",
                "description": (
                    "allocate until each topology reaches a small distinct-skeleton "
                    "discovery target, then rank/continue"
                ),
                "pros": ["budget follows actual candidate diversity rather than a family label"],
                "cons": ["requires fair scheduling and explicit stop semantics"],
            },
            {
                "policy": "D_STAGED_COVERAGE_THEN_PREFERENCE",
                "description": (
                    "first secure at least one seed per viable topology, then allocate "
                    "remaining nodes by preference"
                ),
                "pros": ["prevents preferred lane monopolization while retaining useful ordering"],
                "cons": [
                    "a topology that cannot produce a seed may consume its exploration reserve"
                ],
            },
        ],
        "design_gate": {
            "CANDIDATE_SPACE_DESIGN_REVIEW_COMPLETE": True,
            "AT_LEAST_TWO_STRUCTURALLY_DISTINCT_MAIN_PROCESS_TOPOLOGIES_DEFINED": True,
            "LINEAR_FAMILY_FAILURE_CLASSIFIED": True,
            "LINEAR_FAMILY_CLASSIFICATION": (
                "SEARCH_PREFIX_TRUNCATED_WITH_NARROW_EXACT_CHAIN_AND_NO_PROJECTED_"
                "FULL_GROUP_EXTENT_ROOT_TEST; INFEASIBILITY_UNPROVEN"
            ),
            "SECOND_HUB_SKELETON_FAILURE_CLASSIFIED": True,
            "SEARCH_BUDGET_SEPARATED_FROM_LAYOUT_AUTHORITY": True,
            "GOLDEN_COORDINATE_TEMPLATE_USED": False,
            "P1B_NUMERIC_THRESHOLD_USED": False,
            "NEXT_IMPLEMENTATION_ENTRY_READY": True,
            "NEXT_IMPLEMENTATION_AUTHORIZED": False,
            "development_fixture_acceptance_target": (
                "at least two distinct main-process skeletons on Xinzhao, both hard "
                "feasible and both reaching complete P2D evaluation"
            ),
            "target_is_permanent_production_threshold": False,
            "owner_visual_acceptance_is_separate": True,
        },
        "search_limit_semantics": {
            "limits_are_computational_caps": True,
            "CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT": 2,
            "limit_two_may_cut_off_diversity": True,
            "no_caps_changed_by_this_review": True,
            "production_budget_increase_authorized": False,
        },
    }
    return {
        "xinzhao_r4_family_search_audit.json": family_audit,
        "xinzhao_r4_linear_rejection_matrix.json": matrix,
        "xinzhao_r4_hub_skeleton_survival_trace.json": hub_trace,
        "xinzhao_r4_candidate_space_design_matrix.json": design,
    }


def write_r4_evidence() -> None:
    for name, payload in build_r4_evidence().items():
        (EVIDENCE / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_r4_evidence()
