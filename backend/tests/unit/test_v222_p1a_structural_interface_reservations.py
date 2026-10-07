"""P1 topology-only slots and fail-closed Plan/Handoff gates. No exact search."""

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.domain import structural_composition as domain
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from cold_storage.modules.layout.domain.mandatory_interface_reservation import (
    MandatoryCapacityStatusV1 as Capacity,
)
from cold_storage.modules.layout.domain.mandatory_interface_reservation import (
    MandatoryReservationKindV1 as Kind,
)
from cold_storage.modules.layout.domain.mandatory_interface_reservation import (
    StructuralCapacityGateStatusV1 as Gate,
)
from cold_storage.modules.layout.domain.mandatory_interface_reservation import (
    StructuralContainerKindV1,
    StructuralContainerReferenceV1,
    assess_mandatory_interface_capacity,
    reserve_mandatory_interfaces,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _result


@pytest.fixture(scope="module")
def result() -> Any:
    return _result()


def assess(plan: Any, reservations: Any = None, topology: Any = None) -> Any:
    return assess_mandatory_interface_capacity(
        plan.mandatory_hard_interfaces,
        plan.mandatory_interface_reservations if reservations is None else reservations,
        plan.mandatory_interface_topology if topology is None else topology,
    )


def test_reservation_full_coverage(result: Any) -> None:
    assert len(result.compositions) == 6
    assert sum(len(p.mandatory_interface_reservations) for p in result.compositions) == 42
    for p in result.compositions:
        assert len(p.mandatory_interface_reservations) == 7
        assert assess(p).status == Gate.PASS_TO_EXACT_PLACEMENT


def test_reservation_one_to_one_with_interface(result: Any) -> None:
    for p in result.compositions:
        assert tuple(
            r.interface_source_edge_identity for r in p.mandatory_interface_reservations
        ) == (tuple(i.source_edge_identity for i in p.mandatory_hard_interfaces))


def test_cross_group_reservation_classification(result: Any) -> None:
    for p in result.compositions:
        assert (
            sum(r.reservation_scope == "CROSS_GROUP" for r in p.mandatory_interface_reservations)
            == 3
        )
        assert (
            sum(r.reservation_scope == "INTRA_GROUP" for r in p.mandatory_interface_reservations)
            == 4
        )


def test_office_shipping_reservation(result: Any) -> None:
    for p in result.compositions:
        reservation = p.mandatory_interface_reservations[-1]
        assert (reservation.endpoint_a_role, reservation.endpoint_b_role) == (
            "office",
            "shipping_channel",
        )
        assert reservation.reservation_kind == Kind.CROSS_CONTAINER_MANDATORY_BRIDGE
        assert reservation.host_a.container_id == "PERSONNEL_INGRESS_DOMAIN"
        assert reservation.host_b.container_id == "SHIPPING_TRUCK_INTERFACE_DOMAIN"
        assert reservation.endpoint_a_group == "PERSONNEL_GROUP"
        assert reservation.endpoint_b_group == "FINISHED_SIDE_GROUP"
        assert reservation.required_attachment_kind == "POSITIVE_SHARED_EDGE"
        assert reservation.capacity_obligation == "PRESERVE_AT_LEAST_ONE_ATTACHMENT_SLOT"
        assert p.structural_interface_capacity_gate.assessments[-1].status == Capacity.RESERVED


def test_missing_office_shipping_reservation_rejects_composition(result: Any) -> None:
    for p in result.compositions:
        remaining = p.mandatory_interface_reservations[:-1]
        gate = assess(p, remaining)
        assert gate.status == Gate.REJECT_STRUCTURAL_COMPOSITION
        assert gate.assessments[-1].reason == "MISSING_OR_DUPLICATE_RESERVATION"
        # Contract omission rejects the composition without pretending that
        # no structural host can exist.
        assert gate.assessments[-1].status == Capacity.UNKNOWN
        with pytest.raises(ValueError, match="REJECT_STRUCTURAL_COMPOSITION"):
            replace(p, mandatory_interface_reservations=remaining)


@pytest.mark.parametrize("index", range(7))
def test_any_missing_mandatory_reservation_rejects(result: Any, index: int) -> None:
    for p, h in zip(result.compositions, result.placement_handoffs, strict=True):
        reservations = p.mandatory_interface_reservations
        remaining = reservations[:index] + reservations[index + 1 :]
        assert assess(p, remaining).status == Gate.REJECT_STRUCTURAL_COMPOSITION
        for aggregate in (p, h):
            with pytest.raises(ValueError, match="REJECT_STRUCTURAL_COMPOSITION"):
                replace(aggregate, mandatory_interface_reservations=remaining)


def test_non_authority_reservation_rejected(result: Any) -> None:
    p = result.compositions[0]
    fake = replace(p.mandatory_interface_reservations[0], interface_source_edge_identity="invented")
    gate = assess(p, (*p.mandatory_interface_reservations, fake))
    assert gate.status == Gate.REJECT_STRUCTURAL_COMPOSITION
    assert any("NON_AUTHORITY_RESERVATION" in e for e in gate.contract_errors)
    with pytest.raises(ValueError, match="REJECT_STRUCTURAL_COMPOSITION"):
        replace(p, mandatory_interface_reservations=(*p.mandatory_interface_reservations, fake))


@pytest.mark.parametrize("reversed_edge", (False, True))
def test_duplicate_reservation_rejected(result: Any, reversed_edge: bool) -> None:
    p = result.compositions[0]
    first = p.mandatory_interface_reservations[0]
    duplicate = (
        replace(
            first,
            endpoint_a_role=first.endpoint_b_role,
            endpoint_b_role=first.endpoint_a_role,
            endpoint_a_group=first.endpoint_b_group,
            endpoint_b_group=first.endpoint_a_group,
            endpoint_a_band=first.endpoint_b_band,
            endpoint_b_band=first.endpoint_a_band,
            endpoint_a_peripheral_domains=first.endpoint_b_peripheral_domains,
            endpoint_b_peripheral_domains=first.endpoint_a_peripheral_domains,
            host_a=first.host_b,
            host_b=first.host_a,
        )
        if reversed_edge
        else first
    )
    gate = assess(p, (*p.mandatory_interface_reservations, duplicate))
    assert gate.status == Gate.REJECT_STRUCTURAL_COMPOSITION
    assert any("DUPLICATE_RESERVATION" in e for e in gate.contract_errors)
    with pytest.raises(ValueError, match="REJECT_STRUCTURAL_COMPOSITION"):
        replace(
            p, mandatory_interface_reservations=(*p.mandatory_interface_reservations, duplicate)
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("endpoint_a_role", "office"),
        ("endpoint_b_role", "unknown"),
        ("endpoint_a_group", "PERSONNEL_GROUP"),
        ("endpoint_a_band", "invented"),
        ("endpoint_a_peripheral_domains", ("PERSONNEL_INGRESS_DOMAIN",)),
        ("source_graph_identity", "invented"),
        ("interface_source_edge_identity", "invented"),
        ("reservation_scope", "CROSS_GROUP"),
        (
            "host_a",
            StructuralContainerReferenceV1(StructuralContainerKindV1.PRINCIPAL_BAND, "invented"),
        ),
    ),
)
def test_reservation_endpoint_provenance(result: Any, field: str, value: Any) -> None:
    p = result.compositions[0]
    reservations = p.mandatory_interface_reservations
    wrong = replace(reservations[0], **{field: value})
    for aggregate in (p, result.placement_handoffs[0]):
        with pytest.raises(ValueError, match="REJECT_STRUCTURAL_COMPOSITION"):
            replace(aggregate, mandatory_interface_reservations=(wrong, *reservations[1:]))


@pytest.mark.parametrize(
    "field",
    (
        "engineering_authority",
        "geometry_authority",
        "validation_authority",
        "creates_new_hard_edge",
    ),
)
def test_reservation_authority_escalation_rejected(result: Any, field: str) -> None:
    with pytest.raises(ValueError, match="AUTHORITY_ESCALATION_FORBIDDEN"):
        replace(result.compositions[0].mandatory_interface_reservations[0], **{field: True})


def test_reservation_derives_from_authority(result: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    graph = process_graph()
    extended = replace(
        graph, must_adjacencies=(*graph.must_adjacencies, ("office", "raw_fruit_buffer"))
    )
    monkeypatch.setattr(domain, "process_graph", lambda: extended)
    plans = domain.enumerate_structural_compositions(result.site_orientation_facts)
    assert all(len(p.mandatory_interface_reservations) == 8 for p in plans)
    assert all(len(p.structural_interface_capacity_gate.assessments) == 8 for p in plans)


def test_reservation_coordinate_free(result: Any) -> None:
    forbidden = {
        "x",
        "y",
        "bounds",
        "rectangle",
        "coordinates",
        "width",
        "depth",
        "height",
        "world_width",
        "world_depth",
        "dimension_authority_ref",
        "shape_variants",
    }

    def check(value: Any) -> None:
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                check(child)

    for h in result.placement_handoffs:
        check(h.to_dict()["mandatory_interface_reservations"])
        check(asdict(h.structural_interface_capacity_gate))


def test_capacity_assessment_full_coverage(result: Any) -> None:
    for p in result.compositions:
        gate = p.structural_interface_capacity_gate
        assert tuple(a.interface_source_edge_identity for a in gate.assessments) == tuple(
            i.source_edge_identity for i in p.mandatory_hard_interfaces
        )
        assert all(a.status == Capacity.RESERVED for a in gate.assessments)
        assert gate.scope == "TOPOLOGICAL_RESERVATION_ONLY"
        assert not gate.metric_geometric_attachment_capacity_proven


def test_capacity_gate_aggregation(result: Any) -> None:
    p = result.compositions[0]
    assert assess(p).status == Gate.PASS_TO_EXACT_PLACEMENT
    unknown = replace(p.mandatory_interface_topology, policy_known=False)
    assert assess(p, topology=unknown).status == Gate.UNKNOWN_STRUCTURAL_CAPACITY
    prohibited = replace(p.mandatory_interface_topology, allowed_reservation_kinds=())
    assert assess(p, topology=prohibited).status == Gate.REJECT_STRUCTURAL_COMPOSITION
    # Known absent host, not a metric-space claim.
    absent = replace(p.mandatory_interface_topology, containers=())
    assert assess(p, topology=absent).status == Gate.REJECT_STRUCTURAL_COMPOSITION
    assert (
        assess(p, p.mandatory_interface_reservations[:-1], unknown).status
        == Gate.REJECT_STRUCTURAL_COMPOSITION
    )
    with pytest.raises(ValueError, match="AGGREGATE_INVALID"):
        replace(assess(p), status=Gate.REJECT_STRUCTURAL_COMPOSITION)


def test_reservation_handoff_preservation(result: Any) -> None:
    for p, h in zip(result.compositions, result.placement_handoffs, strict=True):
        assert h.mandatory_interface_reservations is p.mandatory_interface_reservations
        assert h.mandatory_interface_reservations == reserve_mandatory_interfaces(
            h.mandatory_hard_interfaces, h.mandatory_interface_topology
        )


def test_capacity_gate_handoff_preservation(result: Any) -> None:
    for p, h in zip(result.compositions, result.placement_handoffs, strict=True):
        assert h.structural_interface_capacity_gate is p.structural_interface_capacity_gate
        assert assess(p) == h.structural_interface_capacity_gate
        gate = h.structural_interface_capacity_gate
        fake_assessment = replace(gate.assessments[0], reason="unverified")
        forged = replace(gate, assessments=(fake_assessment, *gate.assessments[1:]))
        with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
            replace(h, structural_interface_capacity_gate=forged)
        with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
            replace(
                h,
                structural_interface_capacity_gate=replace(gate, assessments=gate.assessments[:-1]),
            )


def test_reservation_determinism(result: Any) -> None:
    second = _result()
    assert result.to_dict() == second.to_dict()
    for a, b in zip(result.placement_handoffs, second.placement_handoffs, strict=True):
        assert canonical_json(a.to_dict()) == canonical_json(b.to_dict())
        assert a.canonical_result_hash == b.canonical_result_hash


def test_p0_contract_regression(result: Any) -> None:
    for p in result.compositions:
        projected = domain.project_mandatory_hard_interfaces(
            {a.zone_role: a.group_id for a in p.zone_role_assignment},
            {a.zone_role: a.band_id for a in p.zone_role_assignment},
            {
                a.zone_role: tuple(
                    d.domain_id for d in p.peripheral_domains if a.zone_role in d.zone_roles
                )
                for a in p.zone_role_assignment
            },
        )
        assert p.mandatory_hard_interfaces == projected
        assert canonical_hash([asdict(i) for i in projected]) == canonical_hash(
            [asdict(i) for i in p.mandatory_hard_interfaces]
        )


def test_p1_canonical_evidence_matches_two_current_builds() -> None:
    from tests.evaluation.v222_p1a_reservation_capacity_evidence import capture

    root = Path(__file__).resolve().parents[3]
    evidence = root / (
        "docs/tasks/evidence/v2_2_2_p1a_structural_hard_interface_reservation_p1/"
        "xinzhao_structural_interface_reservation_capacity_gate.json"
    )
    assert json.loads(canonical_json(capture())) == json.loads(evidence.read_text())


def test_reservation_source_order_and_mutable_collection_rejected(result: Any) -> None:
    p = result.compositions[0]
    with pytest.raises(ValueError, match="AUTHORITY_ORDER_INVALID"):
        replace(
            p, mandatory_interface_reservations=tuple(reversed(p.mandatory_interface_reservations))
        )
    with pytest.raises(ValueError, match="TYPED_COLLECTION_REQUIRED"):
        replace(p, mandatory_interface_reservations=list(p.mandatory_interface_reservations))


def test_container_binding_rejects_inconsistent_topology(result: Any) -> None:
    p = result.compositions[0]
    topology = p.mandatory_interface_topology
    changed = replace(topology.containers[0], zone_roles=())
    topology = replace(topology, containers=(changed, *topology.containers[1:]))
    assert assess(p, topology=topology).status == Gate.REJECT_STRUCTURAL_COMPOSITION
