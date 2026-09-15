"""Bind approved access requirements without altering dimension authority."""

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.application.dimension_handoff import build_dimension_handoff
from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.domain.access_authority import (
    COLD_ROOM,
    MATERIAL,
    PACKAGING,
    PERSONNEL,
    TRUCK,
    AccessClassV1,
    AccessRequirementV1,
    TruckAccessContractV1,
    approved_access_profiles,
    personnel_truck_policy,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.access_predicates import _evaluate_bound_requirement
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimension_handoff import EdgeOrientedConnectionV1
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.projects.application.operator_process_input import (
    REFRIGERATED_ZONE_REGISTRY,
)

IDENTITY = "p1-dimension-access-handoff@1.0.0"


def required_access_connections() -> tuple[AccessRequirementV1, ...]:
    """Only existing flow edges, plus the P0 required outdoor truck connection."""
    cold_zones = {code for code, _, _ in REFRIGERATED_ZONE_REGISTRY}
    requirements = []
    for flow in process_graph().flows:
        if flow.kind == "PEOPLE":
            profile_id = PERSONNEL
        elif flow.kind == "PACKAGING":
            profile_id = PACKAGING
        else:
            profile_id = MATERIAL
        profile = resolve_access_profile(profile_id)
        cold_refs = (
            tuple(ref for ref in (flow.from_ref, flow.to_ref) if ref in cold_zones)
            if flow.kind != "PEOPLE"
            else ()
        )
        requirements.append(
            AccessRequirementV1(
                identity=f"access:{flow.from_ref}->{flow.to_ref}@1.0.0",
                from_ref=flow.from_ref,
                to_ref=flow.to_ref,
                flow_kind=flow.kind,
                access_class=profile.access_class,
                profile_identity=profile_id,
                portal_required=True,
                corridor_allowed=True,
                direct_allowed=True,
                route_shape_constraint=profile.route_shape_constraint,
                edge_orientation_requirement=EdgeOrientedConnectionV1().identity
                if flow.kind == "PACKAGING"
                else None,
                cold_room_refs=cold_refs,
                cold_room_portal_profile_identity=COLD_ROOM if cold_refs else None,
            )
        )
    requirements.append(
        AccessRequirementV1(
            identity="access:truck_entrance->shipping_channel@1.0.0",
            from_ref="truck_entrance",
            to_ref="shipping_channel",
            flow_kind="TRUCK",
            access_class=AccessClassV1.TRUCK,
            profile_identity=TRUCK,
            portal_required=False,
            corridor_allowed=True,
            direct_allowed=True,
            route_shape_constraint="OWNER_INPUT_REQUIRED",
            edge_orientation_requirement="shipping_channel:LONG_EDGE_LOADING_FACE",
        )
    )
    return tuple(requirements)


def build_access_handoff(snapshot: Mapping[str, Any] | None) -> ZoneDimensioningResultV1:
    dimension = build_dimension_handoff(snapshot)
    body = dimension.to_dict()
    payload = {
        "identity": IDENTITY,
        "schema_version": "1.0.0",
        "dimension_handoff": body,
        "dimension_handoff_hash": dimension.canonical_result_hash,
        "access_requirements": [asdict(r) for r in required_access_connections()],
        "access_profiles": [asdict(p) for p in approved_access_profiles()],
        "truck_profile": TruckAccessContractV1().to_dict(),
        "shared_route_and_crossing_policy": personnel_truck_policy(),
        "spatial_relationships": body["spatial_relationships"],
        "authority_status": {
            "dimension_authority_complete": not body["blocked_zones"],
            "personnel_access_authority_complete": True,
            "material_access_authority_complete": True,
            "truck_access_contract_complete": True,
            "truck_access_engineering_values_complete": False,
            "p1_complete": False,
        },
        "office_shipping_personnel_portal_required": False,
        "p1_closure_blockers": [
            "TRUCK_OWNER_INPUT_REQUIRED",
            "P1_CLOSURE_REQUIRES_CONTRACT_DECISION",
        ],
        "access_validation_status": "NOT_EVALUATED_NO_PLACEMENT",
        "p2_implemented": False,
        "requires_review": True,
    }
    return ZoneDimensioningResultV1(canonical_json(payload))


def validate_access_handoff_integrity(
    snapshot: Mapping[str, Any], handoff: Mapping[str, Any]
) -> bool:
    return canonical_hash(handoff) == build_access_handoff(snapshot).canonical_result_hash


def evaluate_access_observation(
    requirement_identity: str, observation: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve server-owned rule; arbitrary caller-created profiles are not authority."""
    if not isinstance(observation, Mapping):
        raise LayoutAuthorityError("INVALID_ACCESS_OBSERVATION")
    requirement = next(
        (r for r in required_access_connections() if r.identity == requirement_identity), None
    )
    if requirement is None:
        raise LayoutAuthorityError("UNKNOWN_ACCESS_REQUIREMENT")
    return _evaluate_bound_requirement(requirement, observation)
