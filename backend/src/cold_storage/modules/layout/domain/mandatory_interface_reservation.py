"""Topological attachment slots only; never metric feasibility or new authority."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cold_storage.modules.layout.domain.structural_composition import (
        MandatoryHardInterfaceIntentV1,
    )


class StructuralContainerKindV1(StrEnum):
    PRINCIPAL_BAND = "PRINCIPAL_BAND"
    PERIPHERAL_DOMAIN = "PERIPHERAL_DOMAIN"
    FUNCTIONAL_GROUP = "FUNCTIONAL_GROUP"


class MandatoryReservationKindV1(StrEnum):
    INTRA_STRUCTURAL_CONTAINER = "INTRA_STRUCTURAL_CONTAINER"
    ADJACENT_PRINCIPAL_BAND_INTERFACE = "ADJACENT_PRINCIPAL_BAND_INTERFACE"
    BAND_TO_PERIPHERAL_DOMAIN_INTERFACE = "BAND_TO_PERIPHERAL_DOMAIN_INTERFACE"
    PERIPHERAL_DOMAIN_TO_PERIPHERAL_DOMAIN_INTERFACE = (
        "PERIPHERAL_DOMAIN_TO_PERIPHERAL_DOMAIN_INTERFACE"
    )
    CROSS_CONTAINER_MANDATORY_BRIDGE = "CROSS_CONTAINER_MANDATORY_BRIDGE"


class MandatoryCapacityStatusV1(StrEnum):
    RESERVED = "PASS_STRUCTURAL_CAPACITY_RESERVED"
    NO_CAPACITY = "PROVED_NO_STRUCTURAL_RESERVATION_CAPACITY"
    UNKNOWN = "UNKNOWN_STRUCTURAL_CAPACITY"


class StructuralCapacityGateStatusV1(StrEnum):
    PASS_TO_EXACT_PLACEMENT = "PASS_TO_EXACT_PLACEMENT"
    REJECT_STRUCTURAL_COMPOSITION = "REJECT_STRUCTURAL_COMPOSITION"
    UNKNOWN_STRUCTURAL_CAPACITY = "UNKNOWN_STRUCTURAL_CAPACITY"


@dataclass(frozen=True)
class StructuralContainerReferenceV1:
    kind: StructuralContainerKindV1
    container_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StructuralContainerKindV1) or not self.container_id:
            raise ValueError("RESERVATION_CONTAINER_REFERENCE_INVALID")


@dataclass(frozen=True)
class StructuralContainerDefinitionV1:
    reference: StructuralContainerReferenceV1
    zone_roles: tuple[str, ...]
    topology: str
    sequence_index: int | None = None


@dataclass(frozen=True)
class MandatoryInterfaceTopologyV1:
    """Family policy accepts bridges as obligations, not spatial contact proofs."""

    family: str
    containers: tuple[StructuralContainerDefinitionV1, ...]
    allowed_reservation_kinds: tuple[MandatoryReservationKindV1, ...]
    policy_known: bool = True


def interface_topology(
    family: str,
    bands: tuple[tuple[str, tuple[str, ...], str, int | None], ...],
    domains: tuple[tuple[str, tuple[str, ...]], ...],
    groups: tuple[tuple[str, tuple[str, ...]], ...],
) -> MandatoryInterfaceTopologyV1:
    # These three existing families permit mandatory bridges between their
    # containers. No claim is made that a bridge can be realized on a site.
    known = family in (
        "LINEAR_BANDED",
        "CENTRAL_PROCESS_CORE",
        "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
    )
    containers = (
        tuple(
            StructuralContainerDefinitionV1(
                StructuralContainerReferenceV1(StructuralContainerKindV1.PRINCIPAL_BAND, name),
                roles,
                topology,
                sequence,
            )
            for name, roles, topology, sequence in bands
        )
        + tuple(
            StructuralContainerDefinitionV1(
                StructuralContainerReferenceV1(StructuralContainerKindV1.PERIPHERAL_DOMAIN, name),
                roles,
                "PERIPHERAL_DOMAIN",
            )
            for name, roles in domains
        )
        + tuple(
            StructuralContainerDefinitionV1(
                StructuralContainerReferenceV1(StructuralContainerKindV1.FUNCTIONAL_GROUP, name),
                roles,
                "FUNCTIONAL_CONTEXT",
            )
            for name, roles in groups
        )
    )
    return MandatoryInterfaceTopologyV1(
        family, containers, tuple(MandatoryReservationKindV1) if known else (), known
    )


@dataclass(frozen=True)
class MandatoryInterfaceReservationV1:
    interface_source_edge_identity: str
    source_graph_identity: str
    endpoint_a_role: str
    endpoint_b_role: str
    endpoint_a_group: str
    endpoint_b_group: str
    endpoint_a_band: str | None
    endpoint_b_band: str | None
    endpoint_a_peripheral_domains: tuple[str, ...]
    endpoint_b_peripheral_domains: tuple[str, ...]
    reservation_scope: str
    reservation_kind: MandatoryReservationKindV1
    host_a: StructuralContainerReferenceV1
    host_b: StructuralContainerReferenceV1
    required_attachment_kind: str = "POSITIVE_SHARED_EDGE"
    capacity_obligation: str = "PRESERVE_AT_LEAST_ONE_ATTACHMENT_SLOT"
    downstream_consumption_required: bool = True
    references_existing_mandatory_interface: bool = True
    engineering_authority: bool = False
    geometry_authority: bool = False
    validation_authority: bool = False
    creates_new_hard_edge: bool = False

    def __post_init__(self) -> None:
        if any(
            value is not False
            for value in (
                self.engineering_authority,
                self.geometry_authority,
                self.validation_authority,
                self.creates_new_hard_edge,
            )
        ):
            raise ValueError("RESERVATION_AUTHORITY_ESCALATION_FORBIDDEN")
        if (
            self.references_existing_mandatory_interface is not True
            or self.downstream_consumption_required is not True
            or self.required_attachment_kind != "POSITIVE_SHARED_EDGE"
            or self.capacity_obligation != "PRESERVE_AT_LEAST_ONE_ATTACHMENT_SLOT"
            or not isinstance(self.reservation_kind, MandatoryReservationKindV1)
            or not isinstance(self.host_a, StructuralContainerReferenceV1)
            or not isinstance(self.host_b, StructuralContainerReferenceV1)
            or not isinstance(self.endpoint_a_peripheral_domains, tuple)
            or not isinstance(self.endpoint_b_peripheral_domains, tuple)
        ):
            raise ValueError("RESERVATION_OBLIGATION_INVALID")


def _host(
    topology: MandatoryInterfaceTopologyV1,
    role: str,
    kind: StructuralContainerKindV1,
    container_id: str | None = None,
) -> StructuralContainerDefinitionV1 | None:
    return next(
        (
            c
            for c in topology.containers
            if c.reference.kind == kind
            and role in c.zone_roles
            and (container_id is None or c.reference.container_id == container_id)
        ),
        None,
    )


def _derive_one(
    interface: MandatoryHardInterfaceIntentV1,
    topology: MandatoryInterfaceTopologyV1,
) -> MandatoryInterfaceReservationV1 | None:
    interface.__post_init__()
    for role, group, band, domains in (
        (
            interface.endpoint_a_role,
            interface.endpoint_a_group,
            interface.endpoint_a_band,
            interface.endpoint_a_peripheral_domains,
        ),
        (
            interface.endpoint_b_role,
            interface.endpoint_b_group,
            interface.endpoint_b_band,
            interface.endpoint_b_peripheral_domains,
        ),
    ):
        if _host(topology, role, StructuralContainerKindV1.FUNCTIONAL_GROUP, group) is None:
            return None
        actual_bands = tuple(
            c.reference.container_id
            for c in topology.containers
            if c.reference.kind == StructuralContainerKindV1.PRINCIPAL_BAND and role in c.zone_roles
        )
        actual_domains = tuple(
            c.reference.container_id
            for c in topology.containers
            if c.reference.kind == StructuralContainerKindV1.PERIPHERAL_DOMAIN
            and role in c.zone_roles
        )
        if actual_bands != (() if band is None else (band,)) or actual_domains != domains:
            return None
    band_a = _host(
        topology,
        interface.endpoint_a_role,
        StructuralContainerKindV1.PRINCIPAL_BAND,
        interface.endpoint_a_band,
    )
    band_b = _host(
        topology,
        interface.endpoint_b_role,
        StructuralContainerKindV1.PRINCIPAL_BAND,
        interface.endpoint_b_band,
    )
    domain_a = _host(
        topology, interface.endpoint_a_role, StructuralContainerKindV1.PERIPHERAL_DOMAIN
    )
    domain_b = _host(
        topology, interface.endpoint_b_role, StructuralContainerKindV1.PERIPHERAL_DOMAIN
    )
    kind = MandatoryReservationKindV1.CROSS_CONTAINER_MANDATORY_BRIDGE
    if band_a and band_b and band_a.reference == band_b.reference:
        host_a, host_b = band_a, band_b
        kind = MandatoryReservationKindV1.INTRA_STRUCTURAL_CONTAINER
    elif (
        band_a
        and band_b
        and (
            (
                topology.family == "LINEAR_BANDED"
                and band_a.sequence_index is not None
                and band_b.sequence_index is not None
                and abs(band_a.sequence_index - band_b.sequence_index) == 1
            )
            or (
                topology.family == "CENTRAL_PROCESS_CORE"
                and "CENTRAL_ORGANIZER_CORE" in (band_a.topology, band_b.topology)
            )
        )
    ):
        host_a, host_b = band_a, band_b
        kind = MandatoryReservationKindV1.ADJACENT_PRINCIPAL_BAND_INTERFACE
    elif domain_a and domain_b:
        host_a, host_b = domain_a, domain_b
        if interface.endpoint_a_group == interface.endpoint_b_group:
            kind = MandatoryReservationKindV1.PERIPHERAL_DOMAIN_TO_PERIPHERAL_DOMAIN_INTERFACE
    elif domain_a and band_b:
        host_a, host_b = domain_a, band_b
        kind = MandatoryReservationKindV1.BAND_TO_PERIPHERAL_DOMAIN_INTERFACE
    elif band_a and domain_b:
        host_a, host_b = band_a, domain_b
        kind = MandatoryReservationKindV1.BAND_TO_PERIPHERAL_DOMAIN_INTERFACE
    else:
        fallback_a = (
            band_a
            or domain_a
            or _host(
                topology,
                interface.endpoint_a_role,
                StructuralContainerKindV1.FUNCTIONAL_GROUP,
                interface.endpoint_a_group,
            )
        )
        fallback_b = (
            band_b
            or domain_b
            or _host(
                topology,
                interface.endpoint_b_role,
                StructuralContainerKindV1.FUNCTIONAL_GROUP,
                interface.endpoint_b_group,
            )
        )
        if fallback_a is None or fallback_b is None:
            return None
        host_a, host_b = fallback_a, fallback_b
    return MandatoryInterfaceReservationV1(
        interface_source_edge_identity=interface.source_edge_identity,
        source_graph_identity=interface.source_graph_identity,
        endpoint_a_role=interface.endpoint_a_role,
        endpoint_b_role=interface.endpoint_b_role,
        endpoint_a_group=interface.endpoint_a_group,
        endpoint_b_group=interface.endpoint_b_group,
        endpoint_a_band=interface.endpoint_a_band,
        endpoint_b_band=interface.endpoint_b_band,
        endpoint_a_peripheral_domains=interface.endpoint_a_peripheral_domains,
        endpoint_b_peripheral_domains=interface.endpoint_b_peripheral_domains,
        reservation_scope=interface.interface_scope,
        reservation_kind=kind,
        host_a=host_a.reference,
        host_b=host_b.reference,
        required_attachment_kind=interface.hard_requirement,
    )


def reserve_mandatory_interfaces(
    interfaces: tuple[MandatoryHardInterfaceIntentV1, ...],
    topology: MandatoryInterfaceTopologyV1,
) -> tuple[MandatoryInterfaceReservationV1, ...]:
    """Source-authority order; no endpoint-specific generation branches."""
    return tuple(item for interface in interfaces if (item := _derive_one(interface, topology)))


@dataclass(frozen=True)
class MandatoryInterfaceCapacityAssessmentV1:
    interface_source_edge_identity: str
    source_graph_identity: str
    status: MandatoryCapacityStatusV1
    reason: str
    assessment_scope: str = "TOPOLOGICAL_RESERVATION_ONLY"
    metric_geometric_attachment_capacity_proven: bool = False
    engineering_authority: bool = False
    geometry_authority: bool = False
    validation_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, MandatoryCapacityStatusV1)
            or self.assessment_scope != "TOPOLOGICAL_RESERVATION_ONLY"
            or any(
                value is not False
                for value in (
                    self.metric_geometric_attachment_capacity_proven,
                    self.engineering_authority,
                    self.geometry_authority,
                    self.validation_authority,
                )
            )
        ):
            raise ValueError("CAPACITY_ASSESSMENT_SCOPE_OR_AUTHORITY_INVALID")


@dataclass(frozen=True)
class StructuralMandatoryInterfaceCapacityGateV1:
    status: StructuralCapacityGateStatusV1
    assessments: tuple[MandatoryInterfaceCapacityAssessmentV1, ...]
    contract_errors: tuple[str, ...] = ()
    scope: str = "TOPOLOGICAL_RESERVATION_ONLY"
    metric_geometric_attachment_capacity_proven: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.assessments, tuple) or not isinstance(self.contract_errors, tuple):
            raise ValueError("CAPACITY_GATE_IMMUTABLE_COLLECTION_REQUIRED")
        for item in self.assessments:
            if not isinstance(item, MandatoryInterfaceCapacityAssessmentV1):
                raise ValueError("CAPACITY_ASSESSMENT_TYPED_COLLECTION_REQUIRED")
            item.__post_init__()
        expected = (
            StructuralCapacityGateStatusV1.REJECT_STRUCTURAL_COMPOSITION
            if self.contract_errors
            or not self.assessments
            or any(a.status == MandatoryCapacityStatusV1.NO_CAPACITY for a in self.assessments)
            else StructuralCapacityGateStatusV1.UNKNOWN_STRUCTURAL_CAPACITY
            if any(a.status == MandatoryCapacityStatusV1.UNKNOWN for a in self.assessments)
            else StructuralCapacityGateStatusV1.PASS_TO_EXACT_PLACEMENT
        )
        if (
            not isinstance(self.status, StructuralCapacityGateStatusV1)
            or self.status != expected
            or self.scope != "TOPOLOGICAL_RESERVATION_ONLY"
            or self.metric_geometric_attachment_capacity_proven is not False
        ):
            raise ValueError("CAPACITY_GATE_AGGREGATE_INVALID")


def assess_mandatory_interface_capacity(
    interfaces: tuple[MandatoryHardInterfaceIntentV1, ...],
    reservations: tuple[MandatoryInterfaceReservationV1, ...],
    topology: MandatoryInterfaceTopologyV1,
) -> StructuralMandatoryInterfaceCapacityGateV1:
    """Complete diagnostics for missing, duplicate, extra and incompatible slots.

    Missing reservation is a structural contract rejection, NOT a claim that
    physical attachment is impossible. Unknown family policy is never PASS.
    """
    if not isinstance(reservations, tuple) or any(
        not isinstance(r, MandatoryInterfaceReservationV1) for r in reservations
    ):
        raise ValueError("RESERVATION_TYPED_COLLECTION_REQUIRED")
    counts = Counter(r.interface_source_edge_identity for r in reservations)
    expected_ids = {i.source_edge_identity for i in interfaces}
    errors = (
        [f"NON_AUTHORITY_RESERVATION:{key}" for key in counts.keys() - expected_ids]
        + [f"DUPLICATE_RESERVATION:{key}" for key, count in counts.items() if count != 1]
        + [f"MISSING_RESERVATION:{key}" for key in expected_ids - counts.keys()]
    )
    assessments = []
    for interface in interfaces:
        expected = _derive_one(interface, topology)
        found = tuple(
            r
            for r in reservations
            if r.interface_source_edge_identity == interface.source_edge_identity
        )
        status = MandatoryCapacityStatusV1.UNKNOWN
        reason = "MISSING_OR_DUPLICATE_RESERVATION"
        if expected is None:
            status, reason = MandatoryCapacityStatusV1.NO_CAPACITY, "NO_STRUCTURAL_HOST"
        elif len(found) == 1:
            found[0].__post_init__()
            if found[0] != expected:
                reason = "RESERVATION_ENDPOINT_OR_HOST_PROVENANCE_DRIFT"
                errors.append(f"INVALID_RESERVATION_PROVENANCE:{interface.source_edge_identity}")
            elif not topology.policy_known:
                status, reason = MandatoryCapacityStatusV1.UNKNOWN, "FAMILY_POLICY_UNKNOWN"
            elif found[0].reservation_kind not in topology.allowed_reservation_kinds:
                status = MandatoryCapacityStatusV1.NO_CAPACITY
                reason = "FAMILY_POLICY_PROHIBITS_RESERVATION_KIND"
            else:
                status, reason = MandatoryCapacityStatusV1.RESERVED, "STRUCTURAL_SLOT_BOUND"
        assessments.append(
            MandatoryInterfaceCapacityAssessmentV1(
                interface.source_edge_identity,
                interface.source_graph_identity,
                status,
                reason,
            )
        )
    statuses = {a.status for a in assessments}
    gate_status = (
        StructuralCapacityGateStatusV1.REJECT_STRUCTURAL_COMPOSITION
        if errors or not assessments or MandatoryCapacityStatusV1.NO_CAPACITY in statuses
        else StructuralCapacityGateStatusV1.UNKNOWN_STRUCTURAL_CAPACITY
        if MandatoryCapacityStatusV1.UNKNOWN in statuses
        else StructuralCapacityGateStatusV1.PASS_TO_EXACT_PLACEMENT
    )
    return StructuralMandatoryInterfaceCapacityGateV1(
        gate_status, tuple(assessments), tuple(sorted(errors))
    )


def validate_reserved_interface_contract(
    interfaces: tuple[MandatoryHardInterfaceIntentV1, ...],
    reservations: tuple[MandatoryInterfaceReservationV1, ...],
    gate: StructuralMandatoryInterfaceCapacityGateV1,
    topology: MandatoryInterfaceTopologyV1,
) -> None:
    """Recompute, never trust caller assessments, status, ownership or hosts."""
    expected = assess_mandatory_interface_capacity(interfaces, reservations, topology)
    if expected.status != StructuralCapacityGateStatusV1.PASS_TO_EXACT_PLACEMENT:
        raise ValueError(f"{expected.status}:{expected}")
    if reservations != reserve_mandatory_interfaces(interfaces, topology):
        raise ValueError("RESERVATION_AUTHORITY_ORDER_INVALID")
    if not isinstance(gate, StructuralMandatoryInterfaceCapacityGateV1) or gate != expected:
        raise ValueError("CAPACITY_GATE_REPLAY_MISMATCH")
    gate.__post_init__()
