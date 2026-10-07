"""Whole-building structural composition intent, before exact room placement.

This domain describes functional topology only.  It is deliberately not a
geometry, access, Truck, footprint, or validated-layout representation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, cast

from cold_storage.modules.layout.domain.adjacency import (
    PROCESS_FLOW,
    ZONE_CODES,
    AdjacencyGraphV1,
    process_graph,
)

SCHEMA_VERSION = "2.0.0"
IDENTITY_PREFIX = "whole-building-structural-composition"
PERIPHERAL_DOMAIN_IS_ENGINEERING_AUTHORITY = False
AXIS_FAMILY_IS_INTENT_ONLY = True
TRUCK_INTERFACE_IS_COMPOSITION_INTENT_ONLY = True


class StructuralCompositionError(ValueError):
    """Invalid structural intent; this is not an engineering-validity result."""


class CompositionFamilyV2(StrEnum):
    LINEAR_BANDED = "LINEAR_BANDED"
    CENTRAL_PROCESS_CORE = "CENTRAL_PROCESS_CORE"
    PROCESS_SPINE_WITH_PERIPHERAL_BANKS = "PROCESS_SPINE_WITH_PERIPHERAL_BANKS"


class ProcessAxisV1(StrEnum):
    X = "X"
    Y = "Y"


class ProcessDirectionV1(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


class CardinalSideV1(StrEnum):
    NORTH = "NORTH"
    EAST = "EAST"
    SOUTH = "SOUTH"
    WEST = "WEST"
    UNSPECIFIED = "UNSPECIFIED"


class FunctionalGroupIdV1(StrEnum):
    RAW_SIDE_GROUP = "RAW_SIDE_GROUP"
    PROCESSING_CORE_GROUP = "PROCESSING_CORE_GROUP"
    FINISHED_SIDE_GROUP = "FINISHED_SIDE_GROUP"
    SUPPORT_GROUP = "SUPPORT_GROUP"
    PERSONNEL_GROUP = "PERSONNEL_GROUP"


class PeripheralDomainIdV1(StrEnum):
    PERSONNEL_INGRESS_DOMAIN = "PERSONNEL_INGRESS_DOMAIN"
    PACKAGING_SUPPORT_DOMAIN = "PACKAGING_SUPPORT_DOMAIN"
    SECONDARY_BRANCH_DOMAIN = "SECONDARY_BRANCH_DOMAIN"
    FROZEN_BRANCH_DOMAIN = "FROZEN_BRANCH_DOMAIN"
    SHIPPING_TRUCK_INTERFACE_DOMAIN = "SHIPPING_TRUCK_INTERFACE_DOMAIN"


class CompositionRelationKindV1(StrEnum):
    PROCESS_ORDER = "PROCESS_ORDER"
    CENTRAL_ORGANIZER = "CENTRAL_ORGANIZER"
    CORE_FACE_ATTACHMENT = "CORE_FACE_ATTACHMENT"
    SUBORDINATE_BRANCH = "SUBORDINATE_BRANCH"
    OUTSIDE_PRODUCT_CHAIN = "OUTSIDE_PRODUCT_CHAIN"
    PARALLEL_BANK = "PARALLEL_BANK"
    TERMINAL_INTERFACE_INTENT = "TERMINAL_INTERFACE_INTENT"
    INGRESS_DOMAIN_INTENT = "INGRESS_DOMAIN_INTENT"


class MandatoryInterfaceScopeV1(StrEnum):
    INTRA_GROUP = "INTRA_GROUP"
    CROSS_GROUP = "CROSS_GROUP"


@dataclass(frozen=True)
class MandatoryHardInterfaceIntentV1:
    """Coordinate-free reference to an existing hard edge, not new authority.

    The preservation policy is an obligation for a future construction phase;
    this object neither computes attachment capacity nor claims validity.
    """

    endpoint_a_role: str
    endpoint_b_role: str
    endpoint_a_group: FunctionalGroupIdV1
    endpoint_b_group: FunctionalGroupIdV1
    endpoint_a_band: str | None
    endpoint_b_band: str | None
    endpoint_a_peripheral_domains: tuple[PeripheralDomainIdV1, ...]
    endpoint_b_peripheral_domains: tuple[PeripheralDomainIdV1, ...]
    interface_scope: MandatoryInterfaceScopeV1
    source_graph_identity: str
    source_edge_identity: str
    source_constraint_kind: str = "MUST_ADJACENCY"
    hard_requirement: str = "POSITIVE_SHARED_EDGE"
    engineering_authority: bool = False
    geometry_authority: bool = False
    creates_new_authority: bool = False
    references_existing_hard_authority: bool = True
    requires_attachment_capacity_preservation: bool = True
    interface_preservation_policy: str = "PRESERVE_AT_LEAST_ONE_HARD_FEASIBLE_ATTACHMENT_PATH"

    def __post_init__(self) -> None:
        graph = process_graph()
        if self.endpoint_a_role not in graph.nodes or self.endpoint_b_role not in graph.nodes:
            raise StructuralCompositionError("MANDATORY_INTERFACE_UNKNOWN_ROLE")
        edge = tuple(sorted((self.endpoint_a_role, self.endpoint_b_role)))
        if edge not in {tuple(sorted(pair)) for pair in graph.must_adjacencies}:
            raise StructuralCompositionError("MANDATORY_INTERFACE_NON_AUTHORITY_EDGE")
        if (
            self.source_graph_identity != graph.identity
            or self.source_constraint_kind != "MUST_ADJACENCY"
            or self.source_edge_identity != _mandatory_edge_identity(graph, edge)
        ):
            raise StructuralCompositionError("MANDATORY_INTERFACE_SOURCE_INVALID")
        if self.hard_requirement != "POSITIVE_SHARED_EDGE":
            raise StructuralCompositionError("MANDATORY_INTERFACE_REQUIREMENT_INVALID")
        if (
            self.engineering_authority is not False
            or self.geometry_authority is not False
            or self.creates_new_authority is not False
            or self.references_existing_hard_authority is not True
        ):
            raise StructuralCompositionError("MANDATORY_INTERFACE_AUTHORITY_FORBIDDEN")
        if (
            self.requires_attachment_capacity_preservation is not True
            or self.interface_preservation_policy
            != "PRESERVE_AT_LEAST_ONE_HARD_FEASIBLE_ATTACHMENT_PATH"
        ):
            raise StructuralCompositionError("MANDATORY_INTERFACE_PRESERVATION_REQUIRED")
        if not isinstance(self.endpoint_a_peripheral_domains, tuple) or not isinstance(
            self.endpoint_b_peripheral_domains, tuple
        ):
            raise StructuralCompositionError("MANDATORY_INTERFACE_IMMUTABLE_DOMAINS_REQUIRED")


def _mandatory_edge_identity(graph: AdjacencyGraphV1, edge: tuple[str, ...]) -> str:
    return f"{graph.identity}:MUST_ADJACENCY:{':'.join(edge)}"


def project_mandatory_hard_interfaces(
    role_groups: Mapping[str, str],
    role_bands: Mapping[str, str | None],
    role_domains: Mapping[str, tuple[str, ...]],
) -> tuple[MandatoryHardInterfaceIntentV1, ...]:
    """Project every current MUST in source authority order, for any family."""
    graph = process_graph()
    return tuple(
        MandatoryHardInterfaceIntentV1(
            endpoint_a_role=a,
            endpoint_b_role=b,
            endpoint_a_group=FunctionalGroupIdV1(role_groups[a]),
            endpoint_b_group=FunctionalGroupIdV1(role_groups[b]),
            endpoint_a_band=role_bands[a],
            endpoint_b_band=role_bands[b],
            endpoint_a_peripheral_domains=tuple(
                PeripheralDomainIdV1(value) for value in role_domains.get(a, ())
            ),
            endpoint_b_peripheral_domains=tuple(
                PeripheralDomainIdV1(value) for value in role_domains.get(b, ())
            ),
            interface_scope=(
                MandatoryInterfaceScopeV1.INTRA_GROUP
                if role_groups[a] == role_groups[b]
                else MandatoryInterfaceScopeV1.CROSS_GROUP
            ),
            source_graph_identity=graph.identity,
            source_edge_identity=_mandatory_edge_identity(graph, tuple(sorted((a, b)))),
        )
        for a, b in graph.must_adjacencies
    )


def validate_mandatory_hard_interfaces(
    interfaces: tuple[MandatoryHardInterfaceIntentV1, ...],
    role_groups: Mapping[str, str],
    role_bands: Mapping[str, str | None],
    role_domains: Mapping[str, tuple[str, ...]],
) -> None:
    """Reject missing/extra/duplicate edges and drift from endpoint ownership."""
    if not isinstance(interfaces, tuple) or any(
        not isinstance(item, MandatoryHardInterfaceIntentV1) for item in interfaces
    ):
        raise StructuralCompositionError("MANDATORY_INTERFACE_TYPED_COLLECTION_REQUIRED")
    edges = [tuple(sorted((item.endpoint_a_role, item.endpoint_b_role))) for item in interfaces]
    if len(edges) != len(set(edges)):
        raise StructuralCompositionError("MANDATORY_INTERFACE_DUPLICATE")
    expected = project_mandatory_hard_interfaces(role_groups, role_bands, role_domains)
    expected_edges = [
        tuple(sorted((item.endpoint_a_role, item.endpoint_b_role))) for item in expected
    ]
    if set(edges) != set(expected_edges):
        raise StructuralCompositionError("MANDATORY_INTERFACE_AUTHORITY_COVERAGE_INVALID")
    if edges != expected_edges:
        raise StructuralCompositionError("MANDATORY_INTERFACE_AUTHORITY_ORDER_INVALID")
    for item in interfaces:
        # Validate provenance/flags again at the aggregate boundary, then bind
        # group, band and domain references to this plan/handoff's assignments.
        item.__post_init__()
        a, b = item.endpoint_a_role, item.endpoint_b_role
        if (item.endpoint_a_group, item.endpoint_b_group) != (role_groups[a], role_groups[b]):
            raise StructuralCompositionError("MANDATORY_INTERFACE_GROUP_REFERENCE_INVALID")
        if (item.endpoint_a_band, item.endpoint_b_band) != (role_bands[a], role_bands[b]):
            raise StructuralCompositionError("MANDATORY_INTERFACE_BAND_REFERENCE_INVALID")
        if (item.endpoint_a_peripheral_domains, item.endpoint_b_peripheral_domains) != (
            role_domains.get(a, ()),
            role_domains.get(b, ()),
        ):
            raise StructuralCompositionError("MANDATORY_INTERFACE_DOMAIN_REFERENCE_INVALID")
        scope = (
            MandatoryInterfaceScopeV1.INTRA_GROUP
            if role_groups[a] == role_groups[b]
            else MandatoryInterfaceScopeV1.CROSS_GROUP
        )
        if item.interface_scope != scope:
            raise StructuralCompositionError("MANDATORY_INTERFACE_SCOPE_INVALID")


_ZONE_GROUPS: tuple[tuple[FunctionalGroupIdV1, tuple[str, ...]], ...] = (
    (FunctionalGroupIdV1.RAW_SIDE_GROUP, ("raw_fruit_buffer", "primary_precooling_room")),
    (
        FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
        ("sorting_packaging_room", "secondary_precooling_room", "coating_room"),
    ),
    (FunctionalGroupIdV1.FINISHED_SIDE_GROUP, ("finished_goods_room", "shipping_channel")),
    (
        FunctionalGroupIdV1.SUPPORT_GROUP,
        ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
    ),
    (FunctionalGroupIdV1.PERSONNEL_GROUP, ("changing_room", "office")),
)
_FAMILY_ORDER = (
    CompositionFamilyV2.LINEAR_BANDED,
    CompositionFamilyV2.CENTRAL_PROCESS_CORE,
    CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS,
)
_PERIPHERAL_DOMAIN_ORDER = (
    PeripheralDomainIdV1.PERSONNEL_INGRESS_DOMAIN,
    PeripheralDomainIdV1.PACKAGING_SUPPORT_DOMAIN,
    PeripheralDomainIdV1.SECONDARY_BRANCH_DOMAIN,
    PeripheralDomainIdV1.FROZEN_BRANCH_DOMAIN,
    PeripheralDomainIdV1.SHIPPING_TRUCK_INTERFACE_DOMAIN,
)


@dataclass(frozen=True)
class SiteOrientationFactsV1:
    """Coordinate-free projection of already validated site-orientation facts."""

    source_geometry_identity: str
    source_geometry_hash: str
    validation_status: str
    dominant_site_axis: ProcessAxisV1
    main_entrance_side: CardinalSideV1
    truck_entrance_side: CardinalSideV1
    preferred_loading_side: CardinalSideV1

    def __post_init__(self) -> None:
        if not self.source_geometry_identity or not self.source_geometry_hash:
            raise StructuralCompositionError("SITE_ORIENTATION_PROVENANCE_REQUIRED")
        if self.validation_status != "VALIDATED_GEOMETRY_FOUNDATION":
            raise StructuralCompositionError("VALIDATED_SITE_FACTS_REQUIRED")


@dataclass(frozen=True)
class FunctionalGroupV1:
    group_id: FunctionalGroupIdV1
    zone_roles: tuple[str, ...]
    product_chain_relation: str
    structural_role: str


@dataclass(frozen=True)
class PrincipalBandV1:
    band_id: str
    topology: str
    group_ids: tuple[FunctionalGroupIdV1, ...]
    zone_roles: tuple[str, ...]
    axis_relation: str
    sequence_index: int | None
    relative_position: str


@dataclass(frozen=True)
class ZoneRoleAssignmentV1:
    zone_role: str
    group_id: FunctionalGroupIdV1
    band_id: str | None
    topology_role: str


@dataclass(frozen=True)
class PeripheralDomainV1:
    domain_id: PeripheralDomainIdV1
    zone_roles: tuple[str, ...]
    relative_side: str
    group_relationship: str
    band_relationship: str
    topology: str
    engineering_authority: bool = False


@dataclass(frozen=True)
class CompositionRelationshipV1:
    relation_kind: CompositionRelationKindV1
    source: str
    target: str
    topology_intent: str
    engineering_authority: bool = False


@dataclass(frozen=True)
class DominantAxisFamilyV1:
    axes: tuple[str, ...]
    basis: str = "COMPOSITION_INTENT_ONLY"
    engineering_axis_authority: bool = False


@dataclass(frozen=True)
class SiteOrientationIntentV1:
    source_geometry_identity: str
    source_geometry_hash: str
    dominant_site_axis: ProcessAxisV1
    main_entrance_side: CardinalSideV1
    truck_entrance_side: CardinalSideV1
    preferred_loading_side: CardinalSideV1
    selected_process_axis: ProcessAxisV1
    selected_process_direction: ProcessDirectionV1
    direction_policy: str


@dataclass(frozen=True)
class ConstructionProvenanceV1:
    source_geometry_identity: str
    source_geometry_hash: str
    source_validation_status: str
    process_graph_identity: str
    family_coverage_round: int
    variant_index: int
    golden_reference_used: bool = False


@dataclass(frozen=True)
class StructuralCompositionSignatureV1:
    """Stable structural identity, not a serialization hash or random identifier."""

    family: CompositionFamilyV2
    process_axis: ProcessAxisV1
    process_direction: ProcessDirectionV1
    functional_group_order: tuple[str, ...]
    band_topology: tuple[tuple[str, tuple[str, ...], str, int | None], ...]
    peripheral_topology: tuple[tuple[str, str, str, str], ...]
    shipping_truck_relationship: tuple[str, str, str]
    personnel_relationship: tuple[str, str, str]

    @property
    def key(self) -> str:
        parts = (
            self.family.value,
            self.process_axis.value,
            self.process_direction.value,
            repr(self.functional_group_order),
            repr(self.band_topology),
            repr(self.peripheral_topology),
            repr(self.shipping_truck_relationship),
            repr(self.personnel_relationship),
        )
        return "|".join(parts)

    @property
    def topology_key(self) -> tuple[object, ...]:
        """Topology-only comparison deliberately excludes family and orientation labels."""
        return (
            self.functional_group_order,
            self.band_topology,
            self.peripheral_topology,
            self.shipping_truck_relationship,
            self.personnel_relationship,
        )


@dataclass(frozen=True)
class StructuralCompositionPlanV2:
    identity: str
    schema_version: str
    family: CompositionFamilyV2
    process_axis: ProcessAxisV1
    process_direction: ProcessDirectionV1
    functional_groups: tuple[FunctionalGroupV1, ...]
    principal_bands: tuple[PrincipalBandV1, ...]
    zone_role_assignment: tuple[ZoneRoleAssignmentV1, ...]
    peripheral_domains: tuple[PeripheralDomainV1, ...]
    personnel_ingress_relationship: CompositionRelationshipV1
    packaging_branch_relationship: CompositionRelationshipV1
    secondary_branch_relationship: CompositionRelationshipV1
    frozen_branch_relationship: CompositionRelationshipV1
    shipping_truck_interface_relationship: CompositionRelationshipV1
    dominant_axis_family: DominantAxisFamilyV1
    composition_adjacency_intent: tuple[CompositionRelationshipV1, ...]
    site_orientation_intent: SiteOrientationIntentV1
    construction_provenance: ConstructionProvenanceV1
    signature: StructuralCompositionSignatureV1
    mandatory_hard_interfaces: tuple[MandatoryHardInterfaceIntentV1, ...]
    peripheral_domain_is_engineering_authority: bool = PERIPHERAL_DOMAIN_IS_ENGINEERING_AUTHORITY

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise StructuralCompositionError("UNSUPPORTED_COMPOSITION_SCHEMA")
        if not self.identity.startswith(f"{IDENTITY_PREFIX}@{SCHEMA_VERSION}:"):
            raise StructuralCompositionError("INVALID_COMPOSITION_IDENTITY")

        expected_groups = dict(_ZONE_GROUPS)
        actual_groups = {group.group_id: group.zone_roles for group in self.functional_groups}
        if len(actual_groups) != len(self.functional_groups) or actual_groups != expected_groups:
            raise StructuralCompositionError("FUNCTIONAL_GROUP_COVERAGE_INVALID")

        assigned = tuple(item.zone_role for item in self.zone_role_assignment)
        if len(assigned) != len(set(assigned)) or set(assigned) != set(ZONE_CODES):
            raise StructuralCompositionError("ZONE_ROLE_COVERAGE_INVALID")
        role_groups = {item.zone_role: item.group_id for item in self.zone_role_assignment}
        expected_role_groups = {
            role: group_id for group_id, roles in _ZONE_GROUPS for role in roles
        }
        if role_groups != expected_role_groups:
            raise StructuralCompositionError("ZONE_ROLE_GROUP_ASSIGNMENT_INVALID")

        domain_ids = tuple(domain.domain_id for domain in self.peripheral_domains)
        if domain_ids != _PERIPHERAL_DOMAIN_ORDER:
            raise StructuralCompositionError("PERIPHERAL_DOMAIN_COVERAGE_INVALID")
        if any(domain.engineering_authority for domain in self.peripheral_domains):
            raise StructuralCompositionError("PERIPHERAL_DOMAIN_AUTHORITY_FORBIDDEN")
        if self.peripheral_domain_is_engineering_authority:
            raise StructuralCompositionError("PERIPHERAL_DOMAIN_AUTHORITY_FORBIDDEN")
        if self.dominant_axis_family.engineering_axis_authority:
            raise StructuralCompositionError("AXIS_FAMILY_AUTHORITY_FORBIDDEN")
        if not AXIS_FAMILY_IS_INTENT_ONLY or not TRUCK_INTERFACE_IS_COMPOSITION_INTENT_ONLY:
            raise StructuralCompositionError("COMPOSITION_INTENT_AUTHORITY_FORBIDDEN")
        if any(item.engineering_authority for item in self.composition_adjacency_intent):
            raise StructuralCompositionError("COMPOSITION_INTENT_AUTHORITY_FORBIDDEN")
        if self.shipping_truck_interface_relationship.engineering_authority:
            raise StructuralCompositionError("COMPOSITION_INTENT_AUTHORITY_FORBIDDEN")

        personnel = set(expected_groups[FunctionalGroupIdV1.PERSONNEL_GROUP])
        product_groups = {
            FunctionalGroupIdV1.RAW_SIDE_GROUP,
            FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
            FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
            FunctionalGroupIdV1.SUPPORT_GROUP,
        }
        if any(role_groups[role] in product_groups for role in personnel):
            raise StructuralCompositionError("PERSONNEL_PRODUCT_CHAIN_MIXED")
        if self.construction_provenance.golden_reference_used:
            raise StructuralCompositionError("GOLDEN_REFERENCE_RUNTIME_INPUT_FORBIDDEN")
        validate_mandatory_hard_interfaces(
            self.mandatory_hard_interfaces,
            role_groups,
            {item.zone_role: item.band_id for item in self.zone_role_assignment},
            {
                role: tuple(
                    domain.domain_id.value
                    for domain in self.peripheral_domains
                    if role in domain.zone_roles
                )
                for role in assigned
            },
        )
        if self.construction_provenance.process_graph_identity != process_graph().identity:
            raise StructuralCompositionError("MANDATORY_INTERFACE_SOURCE_INVALID")

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible evidence projection."""
        return cast(dict[str, Any], json.loads(json.dumps(asdict(self), sort_keys=True)))


def enumerate_structural_compositions(
    site_facts: SiteOrientationFactsV1,
    *,
    zone_roles: tuple[str, ...] = ZONE_CODES,
) -> tuple[StructuralCompositionPlanV2, ...]:
    """Enumerate family-first structural intents without generating room geometry.

    The first round emits exactly one composition per family. A second round
    covers the cross-axis orientation, with family order preserved.
    """
    if zone_roles != ZONE_CODES:
        raise StructuralCompositionError("CANONICAL_ZONE_ROLE_SET_REQUIRED")
    graph = process_graph()
    if tuple(graph.nodes) != ZONE_CODES:
        raise StructuralCompositionError("PROCESS_GRAPH_ROLE_SET_MISMATCH")

    axes = (site_facts.dominant_site_axis, _cross_axis(site_facts.dominant_site_axis))
    plans: list[StructuralCompositionPlanV2] = []
    for round_index, axis in enumerate(axes):
        for family in _FAMILY_ORDER:
            direction, direction_policy = _direction_for_axis(axis, site_facts)
            plans.append(
                _build_plan(
                    family=family,
                    axis=axis,
                    direction=direction,
                    direction_policy=direction_policy,
                    site_facts=site_facts,
                    graph=graph,
                    round_index=round_index,
                    variant_index=round_index,
                )
            )
    _require_complete_enumeration(tuple(plans))
    return tuple(plans)


def family_coverage_evidence(
    plans: tuple[StructuralCompositionPlanV2, ...],
) -> dict[str, object]:
    """Machine-readable deterministic family coverage facts for this enumerator."""
    counts = {family.value: 0 for family in _FAMILY_ORDER}
    for plan in plans:
        counts[plan.family.value] += 1
    first_round = tuple(plan.family for plan in plans[: len(_FAMILY_ORDER)])
    return {
        "family_coverage_order": [family.value for family in first_round],
        "family_first_round_complete": first_round == _FAMILY_ORDER,
        "family_enumeration_count_by_family": counts.copy(),
        "composition_count_by_family": counts,
    }


def _cross_axis(axis: ProcessAxisV1) -> ProcessAxisV1:
    return ProcessAxisV1.Y if axis == ProcessAxisV1.X else ProcessAxisV1.X


def _side_axis(side: CardinalSideV1) -> ProcessAxisV1 | None:
    if side in (CardinalSideV1.EAST, CardinalSideV1.WEST):
        return ProcessAxisV1.X
    if side in (CardinalSideV1.NORTH, CardinalSideV1.SOUTH):
        return ProcessAxisV1.Y
    return None


def _direction_for_axis(
    axis: ProcessAxisV1, facts: SiteOrientationFactsV1
) -> tuple[ProcessDirectionV1, str]:
    """Orient the finished terminal toward a same-axis truck/loading side when known."""
    for source, side in (
        ("PREFERRED_LOADING_SIDE", facts.preferred_loading_side),
        ("TRUCK_ENTRANCE_SIDE", facts.truck_entrance_side),
    ):
        if _side_axis(side) == axis:
            direction = (
                ProcessDirectionV1.POSITIVE
                if side in (CardinalSideV1.EAST, CardinalSideV1.NORTH)
                else ProcessDirectionV1.NEGATIVE
            )
            return direction, f"FINISHED_TERMINAL_TOWARD_{source}"
    # No validated side constrains this orientation; use a stable policy.
    return ProcessDirectionV1.POSITIVE, "DETERMINISTIC_POSITIVE_NO_ALIGNED_INTERFACE"


def _build_plan(
    *,
    family: CompositionFamilyV2,
    axis: ProcessAxisV1,
    direction: ProcessDirectionV1,
    direction_policy: str,
    site_facts: SiteOrientationFactsV1,
    graph: AdjacencyGraphV1,
    round_index: int,
    variant_index: int,
) -> StructuralCompositionPlanV2:
    groups = tuple(
        FunctionalGroupV1(
            group_id=group_id,
            zone_roles=roles,
            product_chain_relation=(
                "OUTSIDE_PRODUCT_CHAIN"
                if group_id == FunctionalGroupIdV1.PERSONNEL_GROUP
                else "PRODUCT_FLOW_GROUP"
                if group_id
                in {
                    FunctionalGroupIdV1.RAW_SIDE_GROUP,
                    FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
                    FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
                }
                else "SUBORDINATE_SUPPORT_GROUP"
            ),
            structural_role=_group_structural_role(family, group_id),
        )
        for group_id, roles in _ZONE_GROUPS
    )
    bands, assignments, group_order = _family_structure(family, axis)
    domains = _peripheral_domains(family)
    relations = _relationships(family, graph)
    personnel = next(
        item
        for item in relations
        if item.relation_kind == CompositionRelationKindV1.INGRESS_DOMAIN_INTENT
    )
    packaging = next(item for item in relations if item.source == "packaging_material_storage")
    secondary = next(item for item in relations if item.source == "secondary_fruit_buffer")
    frozen = next(item for item in relations if item.source == "frozen_fruit_room")
    shipping = next(
        item
        for item in relations
        if item.relation_kind == CompositionRelationKindV1.TERMINAL_INTERFACE_INTENT
    )

    site_intent = SiteOrientationIntentV1(
        source_geometry_identity=site_facts.source_geometry_identity,
        source_geometry_hash=site_facts.source_geometry_hash,
        dominant_site_axis=site_facts.dominant_site_axis,
        main_entrance_side=site_facts.main_entrance_side,
        truck_entrance_side=site_facts.truck_entrance_side,
        preferred_loading_side=site_facts.preferred_loading_side,
        selected_process_axis=axis,
        selected_process_direction=direction,
        direction_policy=direction_policy,
    )
    signature = StructuralCompositionSignatureV1(
        family=family,
        process_axis=axis,
        process_direction=direction,
        functional_group_order=group_order,
        band_topology=tuple(
            (
                band.band_id,
                tuple(group.value for group in band.group_ids),
                band.topology,
                band.sequence_index,
            )
            for band in bands
        ),
        peripheral_topology=tuple(
            (
                domain.domain_id.value,
                domain.relative_side,
                domain.band_relationship,
                domain.topology,
            )
            for domain in domains
        ),
        shipping_truck_relationship=(shipping.source, shipping.target, shipping.topology_intent),
        personnel_relationship=(personnel.source, personnel.target, personnel.topology_intent),
    )
    return StructuralCompositionPlanV2(
        identity=(
            f"{IDENTITY_PREFIX}@{SCHEMA_VERSION}:{family.value}:"
            f"{axis.value}:{direction.value}:r{round_index}"
        ),
        schema_version=SCHEMA_VERSION,
        family=family,
        process_axis=axis,
        process_direction=direction,
        functional_groups=groups,
        principal_bands=bands,
        zone_role_assignment=assignments,
        peripheral_domains=domains,
        personnel_ingress_relationship=personnel,
        packaging_branch_relationship=packaging,
        secondary_branch_relationship=secondary,
        frozen_branch_relationship=frozen,
        shipping_truck_interface_relationship=shipping,
        dominant_axis_family=DominantAxisFamilyV1(
            ("PRIMARY_PROCESS_AXIS", "CROSS_BAND_AXIS", "PERIPHERAL_BANK_AXIS")
        ),
        composition_adjacency_intent=relations,
        site_orientation_intent=site_intent,
        construction_provenance=ConstructionProvenanceV1(
            source_geometry_identity=site_facts.source_geometry_identity,
            source_geometry_hash=site_facts.source_geometry_hash,
            source_validation_status=site_facts.validation_status,
            process_graph_identity=graph.identity,
            family_coverage_round=round_index,
            variant_index=variant_index,
        ),
        signature=signature,
        mandatory_hard_interfaces=project_mandatory_hard_interfaces(
            {item.zone_role: item.group_id for item in assignments},
            {item.zone_role: item.band_id for item in assignments},
            {
                item.zone_role: tuple(
                    domain.domain_id.value
                    for domain in domains
                    if item.zone_role in domain.zone_roles
                )
                for item in assignments
            },
        ),
    )


def _family_structure(
    family: CompositionFamilyV2,
    axis: ProcessAxisV1,
) -> tuple[
    tuple[PrincipalBandV1, ...],
    tuple[ZoneRoleAssignmentV1, ...],
    tuple[str, ...],
]:
    bands: tuple[PrincipalBandV1, ...]
    mapping: dict[str, tuple[PrincipalBandV1 | None, str]]
    group_order: tuple[str, ...]
    if family == CompositionFamilyV2.LINEAR_BANDED:
        bands = (
            _band(
                "RAW_UPSTREAM_BAND",
                "ORDERED_GROUP_BAND",
                (FunctionalGroupIdV1.RAW_SIDE_GROUP,),
                ("raw_fruit_buffer", "primary_precooling_room"),
                axis,
                0,
                "PROCESS_UPSTREAM",
            ),
            _band(
                "PROCESS_CORE_BAND",
                "ORDERED_PROCESS_CORE_BAND",
                (FunctionalGroupIdV1.PROCESSING_CORE_GROUP,),
                ("sorting_packaging_room", "secondary_precooling_room", "coating_room"),
                axis,
                1,
                "PROCESS_MIDDLE",
            ),
            _band(
                "FINISHED_TERMINAL_BAND",
                "ORDERED_FINISHED_TERMINAL_BAND",
                (FunctionalGroupIdV1.FINISHED_SIDE_GROUP,),
                ("finished_goods_room", "shipping_channel"),
                axis,
                2,
                "PROCESS_DOWNSTREAM",
            ),
            _band(
                "SUPPORT_BRANCH_BAND",
                "SUBORDINATE_PARALLEL_SUPPORT_BAND",
                (FunctionalGroupIdV1.SUPPORT_GROUP,),
                ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
                axis,
                None,
                "PERIPHERAL_SERVICE_SIDE",
            ),
        )
        mapping = {
            "raw_fruit_buffer": (bands[0], "RAW_CHAIN_ENTRY"),
            "primary_precooling_room": (bands[0], "RAW_PRECOOL_LINK"),
            "sorting_packaging_room": (bands[1], "PROCESS_CORE"),
            "secondary_precooling_room": (bands[1], "PROCESS_TRANSITION"),
            "coating_room": (bands[1], "PROCESS_TRANSITION"),
            "finished_goods_room": (bands[2], "FINISHED_STORAGE"),
            "shipping_channel": (bands[2], "SHIPPING_TERMINAL"),
            "packaging_material_storage": (bands[3], "PACKAGING_BRANCH"),
            "secondary_fruit_buffer": (bands[3], "SECONDARY_BRANCH"),
            "frozen_fruit_room": (bands[3], "FROZEN_BRANCH"),
            "changing_room": (None, "PERSONNEL_INGRESS"),
            "office": (None, "PERSONNEL_SUPPORT"),
        }
        group_order = tuple(group.value for group in _FAMILY_ORDER_GROUP_ORDER[family])
    elif family == CompositionFamilyV2.CENTRAL_PROCESS_CORE:
        bands = (
            _band(
                "CENTRAL_SORTING_CORE",
                "CENTRAL_ORGANIZER_CORE",
                (FunctionalGroupIdV1.PROCESSING_CORE_GROUP,),
                ("sorting_packaging_room",),
                axis,
                None,
                "COMPOSITION_CENTER",
            ),
            _band(
                "RAW_CORE_FACE",
                "DISTINCT_CORE_FACE_ATTACHMENT",
                (FunctionalGroupIdV1.RAW_SIDE_GROUP,),
                ("raw_fruit_buffer", "primary_precooling_room"),
                axis,
                None,
                "CORE_FACE_A",
            ),
            _band(
                "PROCESS_CORE_FACE",
                "PROCESSING_CORE_SUPPORT_ARC",
                (FunctionalGroupIdV1.PROCESSING_CORE_GROUP,),
                ("secondary_precooling_room", "coating_room"),
                axis,
                None,
                "CORE_FACE_B",
            ),
            _band(
                "FINISHED_OPPOSING_FACE",
                "DISTINCT_OPPOSING_CORE_FACE",
                (FunctionalGroupIdV1.FINISHED_SIDE_GROUP,),
                ("finished_goods_room", "shipping_channel"),
                axis,
                None,
                "OPPOSITE_CORE_FACE",
            ),
            _band(
                "SUPPORT_OTHER_FACES",
                "MULTI_FACE_PERIPHERAL_GROUP",
                (FunctionalGroupIdV1.SUPPORT_GROUP,),
                ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
                axis,
                None,
                "OTHER_PERIPHERAL_FACES",
            ),
        )
        mapping = {
            "raw_fruit_buffer": (bands[1], "RAW_FACE_ENTRY"),
            "primary_precooling_room": (bands[1], "RAW_FACE_PRECOOL"),
            "sorting_packaging_room": (bands[0], "CENTRAL_ORGANIZER"),
            "secondary_precooling_room": (bands[2], "CORE_PROCESS_FACE"),
            "coating_room": (bands[2], "PROCESS_TRANSITION_FACE"),
            "finished_goods_room": (bands[3], "FINISHED_OPPOSING_FACE"),
            "shipping_channel": (bands[3], "FINISHED_SIDE_TERMINAL"),
            "packaging_material_storage": (bands[4], "PACKAGING_PERIPHERAL_FACE"),
            "secondary_fruit_buffer": (bands[4], "SECONDARY_PERIPHERAL_FACE"),
            "frozen_fruit_room": (bands[4], "FROZEN_PERIPHERAL_FACE"),
            "changing_room": (None, "PERSONNEL_SEPARATE_FACE"),
            "office": (None, "PERSONNEL_SEPARATE_FACE"),
        }
        group_order = tuple(group.value for group in _FAMILY_ORDER_GROUP_ORDER[family])
    else:
        bands = (
            _band(
                "DOMINANT_PROCESS_SPINE",
                "LONGITUDINAL_ROLE_SEQUENCE",
                (
                    FunctionalGroupIdV1.RAW_SIDE_GROUP,
                    FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
                    FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
                ),
                PROCESS_FLOW,
                axis,
                0,
                "SPINE_ENTRY_TO_FINISHED_TERMINAL",
            ),
            _band(
                "PRODUCT_SUPPORT_SIDE_BANK",
                "PARALLEL_PRODUCT_SUPPORT_BANK",
                (FunctionalGroupIdV1.SUPPORT_GROUP,),
                ("packaging_material_storage", "secondary_fruit_buffer", "frozen_fruit_room"),
                axis,
                None,
                "SPINE_SIDE_BANK_A",
            ),
            _band(
                "PERSONNEL_INGRESS_BANK",
                "SEPARATE_PERSONNEL_BANK",
                (FunctionalGroupIdV1.PERSONNEL_GROUP,),
                ("changing_room", "office"),
                axis,
                None,
                "SPINE_SIDE_BANK_B_OUTSIDE_PRODUCT_CHAIN",
            ),
        )
        mapping = {
            "raw_fruit_buffer": (bands[0], "SPINE_ENTRY"),
            "primary_precooling_room": (bands[0], "RAW_PRECOOL_SPINE_LINK"),
            "sorting_packaging_room": (bands[0], "PROCESS_CORE_ON_SPINE"),
            "secondary_precooling_room": (bands[0], "PROCESS_SPINE_TRANSITION"),
            "coating_room": (bands[0], "PROCESS_SPINE_TRANSITION"),
            "finished_goods_room": (bands[0], "SPINE_FINISHED_ROLE"),
            "shipping_channel": (bands[0], "SPINE_FINISHED_TERMINAL"),
            "packaging_material_storage": (bands[1], "PACKAGING_SIDE_BANK"),
            "secondary_fruit_buffer": (bands[1], "SECONDARY_SIDE_BANK"),
            "frozen_fruit_room": (bands[1], "FROZEN_SIDE_BANK"),
            "changing_room": (bands[2], "PERSONNEL_INGRESS_BANK"),
            "office": (bands[2], "PERSONNEL_INGRESS_BANK"),
        }
        group_order = tuple(group.value for group in _FAMILY_ORDER_GROUP_ORDER[family])
    assignments = tuple(
        _role_assignment(role, group_id, mapping[role])
        for group_id, roles in _ZONE_GROUPS
        for role in roles
    )
    return bands, assignments, group_order


def _role_assignment(
    role: str,
    group_id: FunctionalGroupIdV1,
    location: tuple[PrincipalBandV1 | None, str],
) -> ZoneRoleAssignmentV1:
    band, topology_role = location
    return ZoneRoleAssignmentV1(
        zone_role=role,
        group_id=group_id,
        band_id=band.band_id if band is not None else None,
        topology_role=topology_role,
    )


_FAMILY_ORDER_GROUP_ORDER = {
    CompositionFamilyV2.LINEAR_BANDED: (
        FunctionalGroupIdV1.RAW_SIDE_GROUP,
        FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
        FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
        FunctionalGroupIdV1.SUPPORT_GROUP,
        FunctionalGroupIdV1.PERSONNEL_GROUP,
    ),
    CompositionFamilyV2.CENTRAL_PROCESS_CORE: (
        FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
        FunctionalGroupIdV1.RAW_SIDE_GROUP,
        FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
        FunctionalGroupIdV1.SUPPORT_GROUP,
        FunctionalGroupIdV1.PERSONNEL_GROUP,
    ),
    CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS: (
        FunctionalGroupIdV1.RAW_SIDE_GROUP,
        FunctionalGroupIdV1.PROCESSING_CORE_GROUP,
        FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
        FunctionalGroupIdV1.SUPPORT_GROUP,
        FunctionalGroupIdV1.PERSONNEL_GROUP,
    ),
}


def _band(
    band_id: str,
    topology: str,
    group_ids: tuple[FunctionalGroupIdV1, ...],
    zone_roles: tuple[str, ...],
    axis: ProcessAxisV1,
    sequence_index: int | None,
    relative_position: str,
) -> PrincipalBandV1:
    return PrincipalBandV1(
        band_id=band_id,
        topology=topology,
        group_ids=group_ids,
        zone_roles=zone_roles,
        axis_relation=(
            "ALONG_PROCESS_AXIS" if sequence_index is not None else "PERIPHERAL_OR_CORE_FACE"
        ),
        sequence_index=sequence_index,
        relative_position=relative_position,
    )


def _group_structural_role(family: CompositionFamilyV2, group_id: FunctionalGroupIdV1) -> str:
    if group_id == FunctionalGroupIdV1.PERSONNEL_GROUP:
        return "SEPARATE_PERSONNEL_INGRESS_DOMAIN"
    if group_id == FunctionalGroupIdV1.SUPPORT_GROUP:
        return {
            CompositionFamilyV2.LINEAR_BANDED: "SUBORDINATE_PARALLEL_BRANCH",
            CompositionFamilyV2.CENTRAL_PROCESS_CORE: "PERIPHERAL_CORE_FACES",
            CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS: "SPINE_SIDE_BANK",
        }[family]
    if group_id == FunctionalGroupIdV1.PROCESSING_CORE_GROUP:
        return {
            CompositionFamilyV2.LINEAR_BANDED: "MIDDLE_PROCESS_BAND",
            CompositionFamilyV2.CENTRAL_PROCESS_CORE: "CENTRAL_ORGANIZER_CORE",
            CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS: "PROCESS_CORE_ON_SPINE",
        }[family]
    return {
        CompositionFamilyV2.LINEAR_BANDED: "ORDERED_PROCESS_END_BAND",
        CompositionFamilyV2.CENTRAL_PROCESS_CORE: "DISTINCT_CORE_FACE_ATTACHMENT",
        CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS: "SPINE_TERMINAL_GROUP",
    }[family]


def _peripheral_domains(family: CompositionFamilyV2) -> tuple[PeripheralDomainV1, ...]:
    topologies = {
        CompositionFamilyV2.LINEAR_BANDED: (
            "PERSONNEL_OUTSIDE_LINEAR_PRODUCT_BANDS",
            "SUBORDINATE_TO_PROCESS_CORE",
            "BRANCH_FROM_PROCESS_CORE",
            "BRANCH_FROM_PROCESS_CORE",
            "FINISHED_TERMINAL_WITH_TRUCK_INTERFACE_INTENT",
        ),
        CompositionFamilyV2.CENTRAL_PROCESS_CORE: (
            "PERSONNEL_ON_SEPARATE_CORE_FACE",
            "PACKAGING_ON_PERIPHERAL_CORE_FACE",
            "SECONDARY_ON_PERIPHERAL_CORE_FACE",
            "FROZEN_ON_PERIPHERAL_CORE_FACE",
            "SHIPPING_ON_FINISHED_OPPOSING_FACE",
        ),
        CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS: (
            "PERSONNEL_SEPARATE_SPINE_BANK",
            "PACKAGING_PRODUCT_SUPPORT_BANK",
            "SECONDARY_PRODUCT_SUPPORT_BANK",
            "FROZEN_PRODUCT_SUPPORT_BANK",
            "SPINE_FINISHED_TERMINAL_TRUCK_INTENT",
        ),
    }[family]
    side_classes = {
        CompositionFamilyV2.LINEAR_BANDED: (
            "PERSONNEL_SIDE_OUTSIDE_PRODUCT_FLOW",
            "SERVICE_SIDE_OF_PROCESS_BAND",
            "BRANCH_SIDE_OF_PROCESS_BAND",
            "BRANCH_SIDE_OF_PROCESS_BAND",
            "FINISHED_TERMINAL_SIDE",
        ),
        CompositionFamilyV2.CENTRAL_PROCESS_CORE: (
            "SEPARATE_INGRESS_FACE",
            "PERIPHERAL_FACE_A",
            "PERIPHERAL_FACE_B",
            "PERIPHERAL_FACE_C",
            "FINISHED_SIDE_INTERFACE",
        ),
        CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS: (
            "PERSONNEL_BANK_SEPARATE_FROM_PRODUCT_BANK",
            "PRODUCT_SUPPORT_BANK_A",
            "PRODUCT_SUPPORT_BANK_A",
            "PRODUCT_SUPPORT_BANK_A",
            "FINISHED_SPINE_TERMINAL",
        ),
    }[family]
    roles = (
        ("changing_room", "office"),
        ("packaging_material_storage",),
        ("secondary_fruit_buffer",),
        ("frozen_fruit_room",),
        ("shipping_channel",),
    )
    groups = (
        FunctionalGroupIdV1.PERSONNEL_GROUP,
        FunctionalGroupIdV1.SUPPORT_GROUP,
        FunctionalGroupIdV1.SUPPORT_GROUP,
        FunctionalGroupIdV1.SUPPORT_GROUP,
        FunctionalGroupIdV1.FINISHED_SIDE_GROUP,
    )
    bands = (
        "OUTSIDE_PRODUCT_BANDS",
        "SUPPORT_BRANCH",
        "SUPPORT_BRANCH",
        "SUPPORT_BRANCH",
        "FINISHED_TERMINAL",
    )
    return tuple(
        PeripheralDomainV1(
            domain_id=domain_id,
            zone_roles=roles[index],
            relative_side=side_classes[index],
            group_relationship=groups[index].value,
            band_relationship=bands[index],
            topology=topologies[index],
        )
        for index, domain_id in enumerate(_PERIPHERAL_DOMAIN_ORDER)
    )


def _relationships(
    family: CompositionFamilyV2, graph: AdjacencyGraphV1
) -> tuple[CompositionRelationshipV1, ...]:
    family_intents = {
        CompositionFamilyV2.LINEAR_BANDED: (
            CompositionRelationshipV1(
                CompositionRelationKindV1.PROCESS_ORDER,
                "RAW_SIDE_GROUP",
                "PROCESSING_CORE_GROUP",
                "UPSTREAM_TO_MIDDLE_BAND",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.PROCESS_ORDER,
                "PROCESSING_CORE_GROUP",
                "FINISHED_SIDE_GROUP",
                "MIDDLE_TO_DOWNSTREAM_BAND",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.INGRESS_DOMAIN_INTENT,
                "PERSONNEL_GROUP",
                "PERSONNEL_INGRESS_DOMAIN",
                "OUTSIDE_PRODUCT_CHAIN",
            ),
        ),
        CompositionFamilyV2.CENTRAL_PROCESS_CORE: (
            CompositionRelationshipV1(
                CompositionRelationKindV1.CENTRAL_ORGANIZER,
                "sorting_packaging_room",
                "PROCESSING_CORE_GROUP",
                "SORTING_IS_CENTRAL_ORGANIZER",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.CORE_FACE_ATTACHMENT,
                "RAW_SIDE_GROUP",
                "sorting_packaging_room",
                "ONE_CORE_FACE",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.CORE_FACE_ATTACHMENT,
                "FINISHED_SIDE_GROUP",
                "sorting_packaging_room",
                "DISTINCT_OPPOSING_CORE_FACE",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.INGRESS_DOMAIN_INTENT,
                "PERSONNEL_GROUP",
                "PERSONNEL_INGRESS_DOMAIN",
                "SEPARATE_FROM_PRODUCT_CHAIN",
            ),
        ),
        CompositionFamilyV2.PROCESS_SPINE_WITH_PERIPHERAL_BANKS: (
            CompositionRelationshipV1(
                CompositionRelationKindV1.PROCESS_ORDER,
                "RAW_SIDE_GROUP",
                "PROCESSING_CORE_GROUP",
                "SPINE_ENTRY_TO_CORE",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.PROCESS_ORDER,
                "PROCESSING_CORE_GROUP",
                "FINISHED_SIDE_GROUP",
                "CORE_TO_SPINE_FINISHED_TERMINAL",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.PARALLEL_BANK,
                "SUPPORT_GROUP",
                "DOMINANT_PROCESS_SPINE",
                "PARALLEL_PRODUCT_SUPPORT_BANK",
            ),
            CompositionRelationshipV1(
                CompositionRelationKindV1.INGRESS_DOMAIN_INTENT,
                "PERSONNEL_GROUP",
                "PERSONNEL_INGRESS_DOMAIN",
                "SEPARATE_PERSONNEL_BANK",
            ),
        ),
    }[family]
    branches = (
        CompositionRelationshipV1(
            CompositionRelationKindV1.SUBORDINATE_BRANCH,
            "packaging_material_storage",
            "sorting_packaging_room",
            "PACKAGING_SUPPORT_RELATIONSHIP_INTENT",
        ),
        CompositionRelationshipV1(
            CompositionRelationKindV1.SUBORDINATE_BRANCH,
            "secondary_fruit_buffer",
            "sorting_packaging_room",
            "SECONDARY_BRANCH_RELATIONSHIP_INTENT",
        ),
        CompositionRelationshipV1(
            CompositionRelationKindV1.SUBORDINATE_BRANCH,
            "frozen_fruit_room",
            "sorting_packaging_room",
            "FROZEN_BRANCH_RELATIONSHIP_INTENT",
        ),
        CompositionRelationshipV1(
            CompositionRelationKindV1.TERMINAL_INTERFACE_INTENT,
            "shipping_channel",
            "SHIPPING_TRUCK_INTERFACE_DOMAIN",
            "FINISHED_SIDE_TERMINAL_TRUCK_INTERFACE_INTENT_ONLY",
        ),
    )
    material_flow_intents = tuple(
        CompositionRelationshipV1(
            CompositionRelationKindV1.PROCESS_ORDER,
            flow.from_ref,
            flow.to_ref,
            "CURRENT_PROCESS_GRAPH_FLOW_DIRECTION_ONLY",
        )
        for flow in graph.flows
        if flow.kind == "MATERIAL"
    )
    return material_flow_intents + family_intents + branches


def _require_complete_enumeration(plans: tuple[StructuralCompositionPlanV2, ...]) -> None:
    if len(plans) < len(_FAMILY_ORDER):
        raise StructuralCompositionError("FAMILY_FIRST_ROUND_INCOMPLETE")
    if tuple(plan.family for plan in plans[:3]) != _FAMILY_ORDER:
        raise StructuralCompositionError("FAMILY_FIRST_ROUND_INCOMPLETE")
    topology_keys = [plan.signature.topology_key for plan in plans[:3]]
    if len(set(topology_keys)) != 3:
        raise StructuralCompositionError("FAMILY_TOPOLOGY_COLLAPSE")
