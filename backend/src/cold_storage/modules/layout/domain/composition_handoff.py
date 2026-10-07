"""Versioned, geometry-free handoff from structural intent to future placement.

This is a composition-constrained placement input contract only.  It is not a
placement candidate, engineering-validity result, or final layout authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.domain.adjacency import ZONE_CODES
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.mandatory_interface_reservation import (
    MandatoryInterfaceReservationV1,
    MandatoryInterfaceTopologyV1,
    StructuralMandatoryInterfaceCapacityGateV1,
    interface_topology,
    validate_reserved_interface_contract,
)
from cold_storage.modules.layout.domain.structural_composition import (
    CompositionFamilyV2,
    DominantAxisFamilyV1,
    MandatoryHardInterfaceIntentV1,
    PeripheralDomainIdV1,
    ProcessAxisV1,
    ProcessDirectionV1,
    SiteOrientationIntentV1,
    validate_mandatory_hard_interfaces,
)

IDENTITY = "structural-composition-placement-handoff@1.0.0"
SCHEMA_VERSION = "1.0.0"
PLACEMENT_HANDOFF_IS_FINAL_LAYOUT = False
PLACEMENT_HANDOFF_IS_P2C_CANDIDATE = False
PLACEMENT_HANDOFF_IS_ENGINEERING_VALIDITY_RESULT = False
_ROLE_GROUP = {
    "raw_fruit_buffer": "RAW_SIDE_GROUP",
    "primary_precooling_room": "RAW_SIDE_GROUP",
    "sorting_packaging_room": "PROCESSING_CORE_GROUP",
    "secondary_precooling_room": "PROCESSING_CORE_GROUP",
    "coating_room": "PROCESSING_CORE_GROUP",
    "finished_goods_room": "FINISHED_SIDE_GROUP",
    "shipping_channel": "FINISHED_SIDE_GROUP",
    "packaging_material_storage": "SUPPORT_GROUP",
    "secondary_fruit_buffer": "SUPPORT_GROUP",
    "frozen_fruit_room": "SUPPORT_GROUP",
    "changing_room": "PERSONNEL_GROUP",
    "office": "PERSONNEL_GROUP",
}
_ROLE_DOMAINS = {
    "changing_room": ("PERSONNEL_INGRESS_DOMAIN",),
    "office": ("PERSONNEL_INGRESS_DOMAIN",),
    "packaging_material_storage": ("PACKAGING_SUPPORT_DOMAIN",),
    "secondary_fruit_buffer": ("SECONDARY_BRANCH_DOMAIN",),
    "frozen_fruit_room": ("FROZEN_BRANCH_DOMAIN",),
    "shipping_channel": ("SHIPPING_TRUCK_INTERFACE_DOMAIN",),
}


@dataclass(frozen=True)
class DimensionAuthorityReferenceV1:
    """A pointer to existing dimensions, never a second copy of those dimensions."""

    authority_identity: str
    zone_code: str
    source_p1_handoff_hash: str


@dataclass(frozen=True)
class ZoneRolePlacementIntentV1:
    zone_role: str
    dimension_authority_ref: DimensionAuthorityReferenceV1
    composition_group: str
    composition_band: str | None
    topology_role: str
    peripheral_domain_membership: tuple[str, ...]


@dataclass(frozen=True)
class PrincipalBandIntentV1:
    band_id: str
    topology: str
    group_ids: tuple[str, ...]
    zone_roles: tuple[str, ...]
    axis_relation: str
    sequence_index: int | None
    relative_position: str


@dataclass(frozen=True)
class PeripheralDomainIntentV1:
    domain_id: str
    zone_roles: tuple[str, ...]
    relative_side: str
    group_relationship: str
    band_relationship: str
    topology: str
    engineering_authority: bool = False


@dataclass(frozen=True)
class CompositionRelationshipIntentV1:
    relation_kind: str
    source: str
    target: str
    topology_intent: str
    engineering_authority: bool = False


@dataclass(frozen=True)
class StructuralCompositionPlacementHandoffV1:
    identity: str
    schema_version: str
    composition_identity: str
    composition_signature: str
    family: CompositionFamilyV2
    process_axis: ProcessAxisV1
    process_direction: ProcessDirectionV1
    zone_role_assignment: tuple[ZoneRolePlacementIntentV1, ...]
    principal_band_intents: tuple[PrincipalBandIntentV1, ...]
    peripheral_domain_intents: tuple[PeripheralDomainIntentV1, ...]
    dominant_axis_family: DominantAxisFamilyV1
    site_orientation_intent: SiteOrientationIntentV1
    composition_relationships: tuple[CompositionRelationshipIntentV1, ...]
    source_composition_hash: str
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    dimension_authority_identity: str
    mandatory_hard_interfaces: tuple[MandatoryHardInterfaceIntentV1, ...]
    mandatory_interface_reservations: tuple[MandatoryInterfaceReservationV1, ...]
    structural_interface_capacity_gate: StructuralMandatoryInterfaceCapacityGateV1
    composition_relationships_are_engineering_authority: bool = False
    placement_handoff_is_final_layout: bool = PLACEMENT_HANDOFF_IS_FINAL_LAYOUT
    placement_handoff_is_p2c_candidate: bool = PLACEMENT_HANDOFF_IS_P2C_CANDIDATE
    placement_handoff_is_engineering_validity_result: bool = (
        PLACEMENT_HANDOFF_IS_ENGINEERING_VALIDITY_RESULT
    )

    def __post_init__(self) -> None:
        if self.identity != IDENTITY or self.schema_version != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_COMPOSITION_PLACEMENT_HANDOFF")
        roles = tuple(item.zone_role for item in self.zone_role_assignment)
        if len(roles) != len(ZONE_CODES) or set(roles) != set(ZONE_CODES):
            raise ValueError("COMPOSITION_HANDOFF_ROLE_COVERAGE_INVALID")
        if len(roles) != len(set(roles)):
            raise ValueError("COMPOSITION_HANDOFF_ROLE_DUPLICATE")
        domain_ids = tuple(item.domain_id for item in self.peripheral_domain_intents)
        if domain_ids != tuple(domain.value for domain in PeripheralDomainIdV1):
            raise ValueError("COMPOSITION_HANDOFF_PERIPHERAL_DOMAIN_COVERAGE_INVALID")
        for assignment in self.zone_role_assignment:
            if assignment.composition_group != _ROLE_GROUP[assignment.zone_role]:
                raise ValueError("COMPOSITION_HANDOFF_ROLE_GROUP_INVALID")
            if assignment.peripheral_domain_membership != _ROLE_DOMAINS.get(
                assignment.zone_role, ()
            ):
                raise ValueError("COMPOSITION_HANDOFF_ROLE_DOMAIN_INVALID")
            if (
                assignment.dimension_authority_ref.zone_code != assignment.zone_role
                or assignment.dimension_authority_ref.source_p1_handoff_hash
                != self.source_p1_handoff_hash
                or assignment.dimension_authority_ref.authority_identity
                != self.dimension_authority_identity
            ):
                raise ValueError("COMPOSITION_HANDOFF_DIMENSION_REFERENCE_INVALID")
        if any(item.engineering_authority for item in self.peripheral_domain_intents):
            raise ValueError("COMPOSITION_HANDOFF_AUTHORITY_FORBIDDEN")
        if any(item.engineering_authority for item in self.composition_relationships):
            raise ValueError("COMPOSITION_HANDOFF_AUTHORITY_FORBIDDEN")
        if self.composition_relationships_are_engineering_authority:
            raise ValueError("COMPOSITION_HANDOFF_AUTHORITY_FORBIDDEN")
        if (
            self.placement_handoff_is_final_layout
            or self.placement_handoff_is_p2c_candidate
            or self.placement_handoff_is_engineering_validity_result
        ):
            raise ValueError("COMPOSITION_HANDOFF_LAYOUT_CLAIM_FORBIDDEN")
        if not all(
            (
                self.composition_identity,
                self.composition_signature,
                self.source_composition_hash,
                self.source_zone_plan_hash,
                self.source_p1_handoff_hash,
                self.source_site_geometry_hash,
                self.dimension_authority_identity,
            )
        ):
            raise ValueError("COMPOSITION_HANDOFF_PROVENANCE_REQUIRED")
        validate_mandatory_hard_interfaces(
            self.mandatory_hard_interfaces,
            {item.zone_role: item.composition_group for item in self.zone_role_assignment},
            {item.zone_role: item.composition_band for item in self.zone_role_assignment},
            {
                item.zone_role: item.peripheral_domain_membership
                for item in self.zone_role_assignment
            },
        )
        validate_reserved_interface_contract(
            self.mandatory_hard_interfaces,
            self.mandatory_interface_reservations,
            self.structural_interface_capacity_gate,
            self.mandatory_interface_topology,
        )

    @property
    def mandatory_interface_topology(self) -> MandatoryInterfaceTopologyV1:
        return interface_topology(
            self.family,
            tuple(
                (b.band_id, b.zone_roles, b.topology, b.sequence_index)
                for b in self.principal_band_intents
            ),
            tuple((d.domain_id, d.zone_roles) for d in self.peripheral_domain_intents),
            tuple(
                (
                    group,
                    tuple(
                        a.zone_role
                        for a in self.zone_role_assignment
                        if a.composition_group == group
                    ),
                )
                for group in sorted({a.composition_group for a in self.zone_role_assignment})
            ),
        )

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["canonical_result_hash"] = self.canonical_result_hash
        return result
