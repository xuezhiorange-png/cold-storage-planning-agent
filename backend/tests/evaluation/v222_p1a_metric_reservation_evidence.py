"""Two actual canonical pairwise realizations, bounded summaries only; no layout search."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.metric_interface_reservation import (
    realize_metric_interface_reservations,
)
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    DEFAULT_PAIR_EVALUATION_CAP,
    DOMAIN_POLICY,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context


def capture() -> dict[str, Any]:
    context = _context()
    structural = build_structural_compositions(*context)
    before = structural.to_dict()
    print("P2 canonical run 1: start", flush=True)
    first = realize_metric_interface_reservations(*context)
    print("P2 canonical run 1: complete; run 2: start", flush=True)
    second = realize_metric_interface_reservations(*context)
    first_body = [asdict(r) for r in first]
    second_body = [asdict(r) for r in second]
    assert first_body == second_body
    assert before == build_structural_compositions(*context).to_dict()
    old_path = (
        Path(__file__).resolve().parents[3]
        / "docs/tasks/evidence/v2_2_2_p1a_structural_hard_interface_reservation_p1"
        / "xinzhao_structural_interface_reservation_capacity_gate.json"
    )
    old = json.loads(old_path.read_text())
    for plan, handoff, previous in zip(
        structural.compositions, structural.placement_handoffs, old["compositions"], strict=True
    ):
        assert canonical_hash(plan.to_dict()) == previous["plan_hash"]
        assert handoff.canonical_result_hash == previous["handoff_projection"]["canonical_hash"]
    body = context[2].to_dict()
    return {
        "task_id": "V2_2_2_P1A_METRIC_INTERFACE_RESERVATION_REALIZATION_P2",
        "p2_start_head_sha": "4576614282a362e86b9cd1f7bf48eb296eac1674",
        "final_sha_binding": "CONTAINING_COMMIT_RESOLVED_BY_GIT_AND_EXACT_HEAD_CI",
        "scope": "PAIRWISE_SITE_DIMENSION_HARD_INTERFACE_CAPACITY",
        "pairwise_capacity_only": True,
        "complete_layout_proven": False,
        "project_layout_validated_claimed": False,
        "other_zone_non_overlap_proven": False,
        "structural_host_metric_footprint_proven": False,
        "p0_p1_serialized_contracts_unchanged": True,
        "finite_domain_policy": DOMAIN_POLICY,
        "finite_domain_definition": {
            "anchor_origins": (
                "all four footprint corners at buildable vertices; all four corners "
                "at hard-obstacle vertices with (+/-1,+/-1) mm offsets"
            ),
            "shared_face_origins": "four faces, tangential start/end/integer-center alignment",
            "union": "A-first plus B-first; exact duplicate removal, canonical role order",
            "shape_coverage": (
                "all authoritative variants, deduplicated only by identical world footprints"
            ),
            "digest_policy": (
                "SHA256 of ASCII bounds-pair tuples plus newline, "
                "deterministic canonical role/shape/event traversal"
            ),
            "evaluation_cap_per_unique_edge": DEFAULT_PAIR_EVALUATION_CAP,
            "cap_exhaustion": "UNKNOWN_METRIC_RESERVATION_DOMAIN_INCOMPLETE",
            "continuous_domain_completeness_claimed": False,
            "representative_slots_are_not_exclusive_domain": True,
            "within_invocation_pair_domain_reuse": (
                "same site, shape set and unordered edge; "
                "each family receives separately bound provenance"
            ),
        },
        "authority_sources": {
            "site_geometry_hash": context[2].canonical_result_hash,
            "effective_buildable_boundary_hash": canonical_hash(
                body["site"]["effective_buildable_boundary"]
            ),
            "hard_obstacle_count": len(body["obstacles"]["hard_obstacles"]),
            "hard_obstacles": [
                {
                    "index": i,
                    "kind": o["kind"],
                    "identity": o.get("id", canonical_hash(o)),
                    "footprint_hash": canonical_hash(o["footprint"]),
                }
                for i, o in enumerate(body["obstacles"]["hard_obstacles"])
            ],
            "graph_identity": first[0].source_graph_identity,
            "dimension_authority_identity": first[0].dimension_authority_identity,
        },
        "compositions": first_body,
        "canonical_metric_domain_complete_count": sum(
            all(i.finite_domain_complete for i in r.reservations) for r in first
        ),
        "metric_realization_count": sum(len(r.reservations) for r in first),
        "gate_counts": {
            status: sum(r.gate.status == status for r in first)
            for status in (
                "PASS_METRIC_RESERVATIONS_TO_FUTURE_PLACEMENT",
                "REJECT_COMPOSITION_IN_CURRENT_METRIC_DOMAIN",
                "UNKNOWN_METRIC_RESERVATION_CAPACITY",
            )
        },
        "site_authority_parity_audit": {
            "audited": True,
            "p2_obstacles": "ValidatedSiteGeometryV1.obstacles.hard_obstacles",
            "existing_exact_obstacles": "obstacles.no_build_zones",
            "exact_placement_uses_full_hard_obstacle_set": False,
            "parity_gap": True,
            "parity_gap_remediated": False,
            "p3_consumption_blocked_by_parity_gap": True,
            "canonical_retained_building_count": sum(
                o["kind"] == "RETAINED_EXISTING_BUILDING"
                for o in body["obstacles"]["hard_obstacles"]
            ),
        },
        "authority_freeze": {
            k: False
            for k in (
                "process_graph_authority_changed",
                "must_adjacency_authority_changed",
                "zone_dimension_authority_changed",
                "site_authority_changed",
                "access_authority_changed",
                "packaging_sorting_straight_only_authority_changed",
                "truck_authority_changed",
                "p2d_authority_changed",
                "validated_candidate_selector_changed",
                "tool7_behavior_changed",
                "exact_placement_search_behavior_changed",
                "placement_node_budget_changed",
                "historical_geometry_runtime_seed_used",
                "pr_306_code_reused",
                "full_exact_placement_search_executed",
            )
        },
        "determinism": {
            "first_result_hash": canonical_hash(first_body),
            "second_result_hash": canonical_hash(second_body),
            "same_composition_interface_order": True,
            "same_finite_domain_identity": True,
            "same_evaluated_pair_count": True,
            "same_valid_slot_count": True,
            "same_slot_set_digest": True,
            "same_representative_slots": True,
            "same_gate": True,
        },
        "global_infeasibility_proven": False,
        "p3_authorized": False,
    }


if __name__ == "__main__":
    print("P2_EVIDENCE_JSON=" + json.dumps(capture(), ensure_ascii=False, sort_keys=True))
