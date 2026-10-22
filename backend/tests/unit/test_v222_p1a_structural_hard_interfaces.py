"""P0 projects existing hard authority; no placement or routing is executed."""

from dataclasses import asdict, replace
from typing import Any

import pytest

from cold_storage.modules.layout.domain import structural_composition as domain
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from cold_storage.modules.layout.domain.structural_composition import (
    FunctionalGroupIdV1,
    MandatoryInterfaceScopeV1,
    PeripheralDomainIdV1,
    StructuralCompositionError,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _result


@pytest.fixture(scope="module")
def result() -> Any:
    return _result()


def edges(items: Any) -> set[frozenset[str]]:
    return {frozenset((item.endpoint_a_role, item.endpoint_b_role)) for item in items}


def test_must_interface_full_coverage(result: Any) -> None:
    expected = {frozenset(pair) for pair in process_graph().must_adjacencies}
    assert len(expected) == 7
    for plan in result.compositions:
        assert edges(plan.mandatory_hard_interfaces) == expected
        assert len(plan.mandatory_hard_interfaces) == 7


def test_cross_group_interface_classification(result: Any) -> None:
    expected = {
        frozenset(("primary_precooling_room", "sorting_packaging_room")),
        frozenset(("coating_room", "finished_goods_room")),
        frozenset(("office", "shipping_channel")),
    }
    for plan in result.compositions:
        cross = tuple(
            i for i in plan.mandatory_hard_interfaces if i.interface_scope == "CROSS_GROUP"
        )
        assert edges(cross) == expected
        assert sum(i.interface_scope == "INTRA_GROUP" for i in plan.mandatory_hard_interfaces) == 4


def test_office_shipping_structural_interface(result: Any) -> None:
    for plan in result.compositions:
        interface = next(i for i in plan.mandatory_hard_interfaces if i.endpoint_a_role == "office")
        assert interface.endpoint_b_role == "shipping_channel"
        assert interface.endpoint_a_group == "PERSONNEL_GROUP"
        assert interface.endpoint_b_group == "FINISHED_SIDE_GROUP"
        assert interface.interface_scope == MandatoryInterfaceScopeV1.CROSS_GROUP
        assert interface.hard_requirement == "POSITIVE_SHARED_EDGE"
        assert interface.endpoint_a_peripheral_domains == ("PERSONNEL_INGRESS_DOMAIN",)
        assert interface.endpoint_b_peripheral_domains == ("SHIPPING_TRUCK_INTERFACE_DOMAIN",)


def test_office_functional_group_regression(result: Any) -> None:
    for plan in result.compositions:
        roles = {item.zone_role: item for item in plan.zone_role_assignment}
        assert roles["office"].group_id == "PERSONNEL_GROUP"
        assert roles["shipping_channel"].group_id == "FINISHED_SIDE_GROUP"


@pytest.mark.parametrize(
    ("role", "domain_id"),
    (
        ("office", "PERSONNEL_INGRESS_DOMAIN"),
        ("shipping_channel", "SHIPPING_TRUCK_INTERFACE_DOMAIN"),
    ),
)
def test_peripheral_domain_ownership_regression(result: Any, role: str, domain_id: str) -> None:
    for plan, handoff in zip(result.compositions, result.placement_handoffs, strict=True):
        assert [d.domain_id for d in plan.peripheral_domains if role in d.zone_roles] == [domain_id]
        assignment = next(item for item in handoff.zone_role_assignment if item.zone_role == role)
        assert assignment.peripheral_domain_membership == (domain_id,)


def test_mandatory_interface_handoff_preservation(result: Any) -> None:
    for plan, handoff in zip(result.compositions, result.placement_handoffs, strict=True):
        assert handoff.mandatory_hard_interfaces is plan.mandatory_hard_interfaces
        assert len(handoff.mandatory_hard_interfaces) == 7
        for item in handoff.mandatory_hard_interfaces:
            assert item.source_graph_identity == process_graph().identity
            assert item.source_constraint_kind == "MUST_ADJACENCY"
            assert item.requires_attachment_capacity_preservation is True
            assert item.interface_preservation_policy == (
                "PRESERVE_AT_LEAST_ONE_HARD_FEASIBLE_ATTACHMENT_PATH"
            )
            assert item.references_existing_hard_authority is True
            assert not item.creates_new_authority
            assert not item.engineering_authority
            assert not item.geometry_authority


def test_mandatory_interface_coordinate_free(result: Any) -> None:
    forbidden = {"x", "y", "width", "height", "depth", "bounds", "rectangle", "coordinates"}

    def check(value: Any) -> None:
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                check(child)

    for handoff in result.placement_handoffs:
        check(handoff.to_dict()["mandatory_hard_interfaces"])
        assert "dimension_authority_ref" not in asdict(handoff.mandatory_hard_interfaces[0])


@pytest.mark.parametrize("reversed_edge", (False, True))
def test_mandatory_interface_duplicate_rejected(result: Any, reversed_edge: bool) -> None:
    plan = result.compositions[0]
    first = plan.mandatory_hard_interfaces[0]
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
        )
        if reversed_edge
        else first
    )
    for aggregate in (plan, result.placement_handoffs[0]):
        with pytest.raises(StructuralCompositionError, match="MANDATORY_INTERFACE_DUPLICATE"):
            replace(
                aggregate,
                mandatory_hard_interfaces=(*aggregate.mandatory_hard_interfaces, duplicate),
            )


def test_non_authority_mandatory_edge_rejected(result: Any) -> None:
    with pytest.raises(StructuralCompositionError, match="NON_AUTHORITY_EDGE"):
        replace(result.compositions[0].mandatory_hard_interfaces[0], endpoint_b_role="office")


def test_unknown_mandatory_role_rejected(result: Any) -> None:
    with pytest.raises(StructuralCompositionError, match="UNKNOWN_ROLE"):
        replace(result.compositions[0].mandatory_hard_interfaces[0], endpoint_b_role="unknown")


def test_missing_authority_must_edge_rejected(result: Any) -> None:
    for aggregate in (result.compositions[0], result.placement_handoffs[0]):
        without_office = tuple(
            i for i in aggregate.mandatory_hard_interfaces if i.endpoint_a_role != "office"
        )
        with pytest.raises(StructuralCompositionError, match="AUTHORITY_COVERAGE_INVALID"):
            replace(aggregate, mandatory_hard_interfaces=without_office)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("endpoint_a_group", FunctionalGroupIdV1.SUPPORT_GROUP, "GROUP_REFERENCE_INVALID"),
        ("endpoint_a_band", "unknown-band", "BAND_REFERENCE_INVALID"),
        (
            "endpoint_a_peripheral_domains",
            (PeripheralDomainIdV1.FROZEN_BRANCH_DOMAIN,),
            "DOMAIN_REFERENCE_INVALID",
        ),
        ("interface_scope", MandatoryInterfaceScopeV1.CROSS_GROUP, "SCOPE_INVALID"),
    ),
)
def test_wrong_endpoint_reference_rejected(
    result: Any, field: str, value: Any, message: str
) -> None:
    for aggregate in (result.compositions[0], result.placement_handoffs[0]):
        interfaces = aggregate.mandatory_hard_interfaces
        wrong = replace(interfaces[0], **{field: value})
        with pytest.raises(StructuralCompositionError, match=message):
            replace(aggregate, mandatory_hard_interfaces=(wrong, *interfaces[1:]))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("engineering_authority", True),
        ("geometry_authority", True),
        ("creates_new_authority", True),
        ("references_existing_hard_authority", False),
        ("requires_attachment_capacity_preservation", False),
        ("interface_preservation_policy", "IGNORE"),
        ("source_graph_identity", "invented"),
        ("source_edge_identity", "invented"),
        ("source_constraint_kind", "SHOULD_ADJACENCY"),
        ("hard_requirement", "NEAR"),
    ),
)
def test_no_new_authority_or_weakened_requirement(result: Any, field: str, value: Any) -> None:
    with pytest.raises(StructuralCompositionError):
        replace(result.compositions[0].mandatory_hard_interfaces[0], **{field: value})


def test_mandatory_interface_determinism(result: Any) -> None:
    other = _result()
    assert result.to_dict() == other.to_dict()
    for a, b in zip(result.placement_handoffs, other.placement_handoffs, strict=True):
        assert canonical_json(a.to_dict()) == canonical_json(b.to_dict())
        assert a.canonical_result_hash == b.canonical_result_hash
        assert canonical_hash(asdict(a.mandatory_hard_interfaces[0])) == canonical_hash(
            asdict(b.mandatory_hard_interfaces[0])
        )


def test_projection_derives_all_edges_from_authority_not_office_special_case(
    result: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = process_graph()
    extended = replace(
        original, must_adjacencies=(*original.must_adjacencies, ("office", "raw_fruit_buffer"))
    )
    monkeypatch.setattr(domain, "process_graph", lambda: extended)
    plan = result.compositions[0]
    projected = domain.project_mandatory_hard_interfaces(
        {item.zone_role: item.group_id for item in plan.zone_role_assignment},
        {item.zone_role: item.band_id for item in plan.zone_role_assignment},
        {
            role: tuple(d.domain_id for d in plan.peripheral_domains if role in d.zone_roles)
            for role in original.nodes
        },
    )
    assert len(projected) == 8
    assert edges(projected) == {frozenset(pair) for pair in extended.must_adjacencies}


def test_interface_order_is_source_authority_order(result: Any) -> None:
    for plan in result.compositions:
        assert (
            tuple((i.endpoint_a_role, i.endpoint_b_role) for i in plan.mandatory_hard_interfaces)
            == process_graph().must_adjacencies
        )
    plan = result.compositions[0]
    with pytest.raises(StructuralCompositionError, match="AUTHORITY_ORDER_INVALID"):
        replace(plan, mandatory_hard_interfaces=tuple(reversed(plan.mandatory_hard_interfaces)))
