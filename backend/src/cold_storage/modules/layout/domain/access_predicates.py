"""Comparisons on supplied observations only; not route/access feasibility proof."""

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain.access_authority import (
    COLD_ROOM,
    TRUCK,
    TRUCK_REQUIRED_FIELDS,
    AccessRequirementV1,
    personnel_truck_policy,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, decimal_value


def _result(status: str, codes: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "scope": "SUPPLIED_ACCESS_OBSERVATION_PREDICATES_ONLY",
        "status": status,
        "codes": codes,
        "full_access_validated": False,
        "requires_review": True,
        **extra,
    }


def _evaluate_bound_requirement(
    requirement: AccessRequirementV1, observation: Mapping[str, Any]
) -> dict[str, Any]:
    """Private domain operation: application resolves the requirement from its ID."""
    if requirement.profile_identity == TRUCK:
        indoor = observation.get("inside_building")
        if indoor is True:
            return _result("FAIL", ["TRUCK_INSIDE_BUILDING_PROHIBITED"])
        if indoor is not None and type(indoor) is not bool:
            return _result("FAIL", ["INVALID_ACCESS_OBSERVATION"])
        return _result(
            "BLOCKED", ["OWNER_INPUT_REQUIRED"], missing_owner_inputs=list(TRUCK_REQUIRED_FIELDS)
        )
    profile = resolve_access_profile(requirement.profile_identity)
    if observation.get("transport_mode", profile.transport_mode) != profile.transport_mode:
        return _result("FAIL", ["ACCESS_TRANSPORT_AUTHORITY_MISMATCH"])
    if observation.get("profile_identity", profile.identity) != profile.identity:
        return _result("FAIL", ["ACCESS_PROFILE_BINDING_MISMATCH"])
    topology = observation.get("topology")
    if topology not in ("DIRECT_SHARED_EDGE", "CORRIDOR_MEDIATED"):
        return _result("BLOCKED", ["ACCESS_TOPOLOGY_REQUIRED"])
    if (topology == "DIRECT_SHARED_EDGE" and not requirement.direct_allowed) or (
        topology == "CORRIDOR_MEDIATED" and not requirement.corridor_allowed
    ):
        return _result("FAIL", ["ACCESS_TOPOLOGY_PROHIBITED"])
    codes = []
    widths = []
    if requirement.portal_required:
        minimum = profile.portal_clear_width_m
        if requirement.cold_room_refs:
            minimum = max(minimum, resolve_access_profile(COLD_ROOM).portal_clear_width_m)
        widths.append(("portal_clear_width_m", minimum, "PORTAL_CLEAR_WIDTH_INSUFFICIENT"))
    if topology == "CORRIDOR_MEDIATED":
        widths.append(
            (
                "corridor_clear_width_m",
                profile.corridor_clear_width_m,
                "CORRIDOR_CLEAR_WIDTH_INSUFFICIENT",
            )
        )
    for field, minimum, code in widths:
        if field not in observation:
            return _result("BLOCKED", ["ACCESS_OBSERVATION_REQUIRED"], missing_fields=[field])
        try:
            width = decimal_value(observation[field])
        except LayoutAuthorityError:
            return _result("FAIL", ["INVALID_ACCESS_OBSERVATION"], field=field)
        if width < minimum:
            codes.append(code)
    if (
        requirement.edge_orientation_requirement
        and observation.get("edge_alignment_verified") is not True
    ):
        codes.append("EDGE_ORIENTATION_ALIGNMENT_REQUIRED")
    if (
        profile.route_shape_constraint == "STRAIGHT_ONLY"
        and topology == "CORRIDOR_MEDIATED"
        and (
            observation.get("route_shape") != "STRAIGHT"
            or type(observation.get("turn_count")) is not int
            or observation["turn_count"] != 0
        )
    ):
        codes.append("PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED")
    # Height is deliberately neither required nor compared. Supplied minimum
    # widths cover all relevant openings/segments, but their measurements and
    # actual centerline/envelope still require future P2 geometry verification.
    return _result("FAIL" if codes else "PASS", codes, profile_identity=profile.identity)


def evaluate_personnel_truck_policy(
    *, shared_route: bool, crossing: bool, crossing_necessary: bool
) -> dict[str, Any]:
    if any(type(value) is not bool for value in (shared_route, crossing, crossing_necessary)):
        return _result("FAIL", ["INVALID_ACCESS_OBSERVATION"])
    policy = personnel_truck_policy()
    if shared_route:
        return _result("FAIL", ["PERSONNEL_TRUCK_SHARED_ROUTE_PROHIBITED"])
    if crossing:
        if not crossing_necessary:
            return _result("FAIL", ["PERSONNEL_TRUCK_CROSSING_NECESSITY_REQUIRED"])
        return _result("PASS_WITH_REVIEW", [], warnings=[policy["crossing_warning"]])
    return _result("PASS", [], warnings=[])
