"""Print lightweight canonical P1 evidence; no placement or routing calls."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from tests.unit.test_v222_p1a_composition_authority_handoff import _result

BASELINE = "aa9556369af3917825b5ee56a6011ee3747e74b2"
ROOT = Path(__file__).resolve().parents[3]


def capture() -> dict[str, Any]:
    first, second = _result(), _result()
    old = json.loads(
        (
            ROOT / "docs/tasks/evidence/"
            "v2_2_2_p1a_structural_hard_interface_reservation_p0/"
            "xinzhao_mandatory_hard_interface_contract.json"
        ).read_text()
    )
    compositions = []
    for plan, handoff, previous in zip(
        first.compositions,
        first.placement_handoffs,
        old["compositions"],
        strict=True,
    ):
        interfaces = [asdict(i) for i in plan.mandatory_hard_interfaces]
        assert json.loads(canonical_json(interfaces)) == previous["mandatory_interfaces"]
        reservations = [asdict(r) for r in plan.mandatory_interface_reservations]
        gate = asdict(plan.structural_interface_capacity_gate)
        office = next(r for r in reservations if r["endpoint_a_role"] == "office")
        p0_plan = plan.to_dict()
        p0_plan.pop("mandatory_interface_reservations")
        p0_plan.pop("structural_interface_capacity_gate")
        assert canonical_hash(p0_plan) == previous["plan_hash"]
        p0_handoff = asdict(handoff)
        p0_handoff.pop("mandatory_interface_reservations")
        p0_handoff.pop("structural_interface_capacity_gate")
        p0_handoff["source_composition_hash"] = canonical_hash(p0_plan)
        assert canonical_hash(p0_handoff) == previous["handoff_hash"]
        compositions.append(
            {
                "composition_identity": plan.identity,
                "family": plan.family,
                "axis": plan.process_axis,
                "direction": plan.process_direction,
                "mandatory_interfaces": interfaces,
                "mandatory_interface_reservations": reservations,
                "structural_interface_capacity_gate": gate,
                "interface_count": len(interfaces),
                "reservation_count": len(reservations),
                "assessment_count": len(gate["assessments"]),
                "cross_group_reservations": [
                    r for r in reservations if r["reservation_scope"] == "CROSS_GROUP"
                ],
                "office_shipping_reservation": office,
                "handoff_projection": {
                    "reservation_source_edges": [
                        r.interface_source_edge_identity
                        for r in handoff.mandatory_interface_reservations
                    ],
                    "reservations_equal": handoff.mandatory_interface_reservations
                    == plan.mandatory_interface_reservations,
                    "gate_equal": handoff.structural_interface_capacity_gate
                    == plan.structural_interface_capacity_gate,
                    "canonical_hash": handoff.canonical_result_hash,
                },
                "plan_hash": canonical_hash(plan.to_dict()),
                "p0_projection_hash_preserved": True,
            }
        )
    assert first.to_dict() == second.to_dict()
    return {
        "task_id": "V2_2_2_P1A_STRUCTURAL_HARD_INTERFACE_RESERVATION_P1",
        "p0_baseline_sha": BASELINE,
        # A file cannot embed its own containing commit SHA. Bind its immutable
        # blob to the published final SHA in the PR body and final receipt.
        "p1_final_sha_binding": "CONTAINING_COMMIT_RESOLVED_BY_GIT_AND_EXACT_HEAD_CI",
        "generation_scope": "TOPOLOGICAL_RESERVATION_ONLY",
        "metric_geometric_attachment_capacity_proven": False,
        "complete_layout_proven": False,
        "full_exact_placement_search_executed": False,
        "source_process_graph_identity": process_graph().identity,
        "source_must_adjacencies": process_graph().must_adjacencies,
        "compositions": compositions,
        "schema_version_audit": {
            "decision": "PRESERVE_INTERNAL_ADDITIVE",
            "audited": True,
            "plan_schema": "2.0.0",
            "handoff_schema": "1.0.0",
            "internal_typed_consumers": [
                "layout/application/structural_composition.py:_handoff_for_composition",
                "layout/application/composition_placement.py:_validate_replayed_handoff",
                "layout/application/composition_placement.py:_assert_server_replay",
                "layout/domain/composition_placement.py:enumerate_composition_placements",
            ],
            "strict_external_or_persisted_deserializers_found": False,
            "api_public_boundary": "server rebuilds; caller serialized composition is not an input",
            "historical_evidence": (
                "S1/S2 and P0 blobs unchanged; old field projection hashes checked"
            ),
            "hash_compatibility": (
                "current plan/handoff/result hashes change; "
                "identities and topology signatures do not"
            ),
            "reservation_signature_policy": "DERIVED_NOT_INCLUDED",
        },
        "authority_freeze": {
            name: False
            for name in (
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
                "pr_306_code_reused",
            )
        },
        "determinism": {
            "first_result_hash": first.canonical_result_hash,
            "second_result_hash": second.canonical_result_hash,
            "same_composition_order": [p.identity for p in first.compositions]
            == [p.identity for p in second.compositions],
            "same_interface_order": [p.mandatory_hard_interfaces for p in first.compositions]
            == [p.mandatory_hard_interfaces for p in second.compositions],
            "same_reservation_order": [
                p.mandatory_interface_reservations for p in first.compositions
            ]
            == [p.mandatory_interface_reservations for p in second.compositions],
            "same_assessment_order_and_gate": [
                p.structural_interface_capacity_gate for p in first.compositions
            ]
            == [p.structural_interface_capacity_gate for p in second.compositions],
            "same_serialized_handoffs": [
                canonical_json(h.to_dict()) for h in first.placement_handoffs
            ]
            == [canonical_json(h.to_dict()) for h in second.placement_handoffs],
            "same_handoff_hashes": [h.canonical_result_hash for h in first.placement_handoffs]
            == [h.canonical_result_hash for h in second.placement_handoffs],
        },
        "p2_authorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(capture(), ensure_ascii=False, sort_keys=True, indent=2))
