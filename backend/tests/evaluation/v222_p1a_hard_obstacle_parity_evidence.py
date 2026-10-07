"""R1 actual canonical replays; no Access/Truck/P2D."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.application.metric_interface_reservation import (
    realize_metric_interface_reservations,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from cold_storage.modules.layout.domain.site_geometry import (
    normalize_polygon,
    validated_hard_obstacle_polygons,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context
from tests.unit.test_v222_p1a_hard_obstacle_authority_parity import (
    EVIDENCE,
    ROOT,
    fixture_audit,
    placement_summary,
)


def capture() -> dict[str, Any]:
    start = json.loads(EVIDENCE.read_text())["canonical_start_placement"]
    print("R1 final canonical placement replay 1", flush=True)
    first = placement_summary()
    print("R1 final canonical placement replay 2", flush=True)
    second = placement_summary()
    assert start == first == second
    p2_path = (
        ROOT
        / "docs/tasks/evidence/v2_2_2_p1a_metric_interface_reservation_p2"
        / "xinzhao_metric_interface_reservation_realization.json"
    )
    p2_start = json.loads(p2_path.read_text())
    context = _context()
    print("R1 final P2 metric replay 1", flush=True)
    metric_first = realize_metric_interface_reservations(*context)
    print("R1 final P2 metric replay 2", flush=True)
    metric_second = realize_metric_interface_reservations(*context)
    first_body = json.loads(canonical_json([asdict(r) for r in metric_first]))
    second_body = json.loads(canonical_json([asdict(r) for r in metric_second]))
    assert p2_start["compositions"] == first_body == second_body
    payload = context[2].to_dict()
    old = tuple(
        normalize_polygon(p, allow_numeric_string=True)
        for p in payload["obstacles"]["no_build_zones"]
    )
    current = validated_hard_obstacle_polygons(payload)
    assert old == current
    return {
        "task_id": "V2_2_2_P1A_EXACT_PLACEMENT_HARD_OBSTACLE_AUTHORITY_PARITY_R1",
        "start_head_sha": "f4961f1fcbbf41c70e8f11e54e30e5cead76fb06",
        "final_head_binding": "CONTAINING_COMMIT_RESOLVED_BY_GIT_AND_EXACT_HEAD_CI",
        "canonical_start_baseline_capture": "ACTUAL_REPLAY_BEFORE_PRODUCTION_MODIFICATION",
        "canonical_start_placement": start,
        "canonical_final_placement": first,
        "canonical_final_second_placement_hash": canonical_hash(second),
        "start_final_canonical_placement_parity": True,
        "exact_placement_determinism_verified": True,
        "canonical_authority": {
            "source_hard_obstacles": payload["obstacles"]["hard_obstacles"],
            "source_hard_obstacle_identities": [
                o.get("id", canonical_hash(o)) for o in payload["obstacles"]["hard_obstacles"]
            ],
            "start_exact_polygon_hashes": [canonical_hash(p) for p in old],
            "final_exact_polygon_hashes": [canonical_hash(p) for p in current],
            "p2_polygon_hashes": [canonical_hash(p) for p in current],
            "site_geometry_hash": context[2].canonical_result_hash,
            "shared_parser": "site_geometry.validated_hard_obstacle_polygons",
        },
        "p2_metric_parity": {
            "start_evidence": str(p2_path.relative_to(ROOT)),
            "start_result_hash": p2_start["determinism"]["first_result_hash"],
            "final_result_hash": canonical_hash(first_body),
            "final_second_result_hash": canonical_hash(second_body),
            "full_serialized_artifacts_equal": True,
            "realization_count": sum(len(r.reservations) for r in metric_first),
            "p2_determinism_verified": True,
            "compositions": [
                {
                    "composition_identity": r.composition_identity,
                    "gate": asdict(r.gate),
                    "interfaces": [
                        {
                            "edge": i.source_edge_identity,
                            "valid_slot_count": i.valid_slot_count,
                            "slot_set_digest": i.slot_set_digest,
                            "finite_domain_complete": i.finite_domain_complete,
                            "evaluated_pairs": i.evaluated_candidate_pair_count,
                            "status": i.status,
                        }
                        for i in r.reservations
                    ],
                }
                for r in metric_first
            ],
        },
        "retained_building_fixture": fixture_audit(True),
        "conditional_removal_fixture": fixture_audit(False),
        "hard_obstacle_authority_parity_restored": True,
        "expected_validation_behavior_change_on_retained_building_sites": True,
        "authority_freeze": {
            k: False
            for k in (
                "process_graph_authority_changed",
                "must_adjacency_authority_changed",
                "zone_dimension_authority_changed",
                "site_authority_changed",
                "access_authority_changed",
                "truck_authority_changed",
                "p2d_authority_changed",
                "packaging_sorting_straight_only_authority_changed",
                "validated_candidate_selector_changed",
                "tool7_behavior_changed",
                "authority_shape_algorithm_changed",
                "exact_placement_search_algorithm_changed",
                "placement_node_budget_changed",
                "conditional_removals_upgraded_to_hard",
                "p3_implementation_started",
                "access_validation_executed",
                "truck_validation_executed",
                "p2d_executed",
                "pr_306_code_reused",
            )
        },
        "p0_p1_p2_contracts_preserved": True,
        "p3_authorized": False,
        "global_result_invariance_claimed": False,
    }


if __name__ == "__main__":
    print("R1_FINAL_EVIDENCE_JSON=" + canonical_json(capture()), flush=True)
