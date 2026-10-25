"""R9 optional, post-baseline physical Changing/frontage/corridor branching.

Only search metadata changes. AccessModel still owns door fit, offsets,
clearance, room relations and corridor envelopes; independent validators own
acceptance. A branching preference is neither a new feasible layout nor a
route-length objective. R7 first feasibility and R6 validated hints are reused.
"""

from copy import deepcopy
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.access_authority import (
    AccessClassV1,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
    POLICY_HASH as R7_POLICY_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
    StageBFirstFeasibleRecoveryFairSolver,
    _FirstFeasibleRecoveryNative,
)
from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import _entrance_face

POLICY = "stage-b-r9-changing-frontage-corridor-soft-order@1.0.0"
POLICY_HASH = canonical_hash(
    dict(
        version=POLICY,
        parent=R7_POLICY_HASH,
        activation="ONLY_AFTER_THIS_HANDOFF_INDEPENDENT_ENGINEERING_ACCEPTANCE",
        order="LEGAL_FACE_NEAR_EDGE_PHYSICAL_SPANS_TRANSVERSE_POSITION_ROUTE_POINTS",
        spans="INTERVAL_BISECTION_NO_NEW_MINIMUM_OR_AREA_CAP",
        entrance="CURRENT_SITE_BOUNDARY_NO_HISTORICAL_COORDINATES",
        objective="UNCHANGED_R5_AREA_PROXY",
        acceptance="UNCHANGED_NINE_TWELVE_TOPOLOGY_AND_ACCESS",
        resources="SAME_MODEL_LEDGER_SHARES_NO_EXTRA_NATIVE_CALL",
    )
)


def _joint_plan(model: Any, context: Any) -> tuple[list[tuple[list[Any], Any]], int, int]:
    """Validate existing references before writing any search metadata."""
    if model.c is not context:
        raise LayoutAuthorityError("R9_CONTEXT_MISMATCH")
    pair = ("main_entrance", "changing_room")
    # Charge actual route reference visits; never scan all proto variables.
    routes = []
    for route in model.routes:
        context.ledger.charge("R9_ROUTE_REFERENCE_READ", 1)
        if (route["req"]["from_ref"], route["req"]["to_ref"]) == pair:
            routes.append(route)
    authorities = []
    for req in context.binding.access_requirements:
        context.ledger.charge("R9_AUTHORITY_REFERENCE_READ", 1)
        if (req["from_ref"], req["to_ref"]) == pair:
            authorities.append(req)
    if len(routes) != 1 or len(authorities) != 1 or routes[0]["req"] != authorities[0]:
        raise LayoutAuthorityError("R9_UNIQUE_PERSONNEL_AUTHORITY_REQUIRED")
    route, req = routes[0], authorities[0]
    profile = resolve_access_profile(req["profile_identity"])
    if (
        req["flow_kind"] != "PEOPLE"
        or not req["corridor_allowed"]
        or not req["portal_required"]
        or profile.access_class != AccessClassV1.PERSONNEL
        or route["pw"] != int(profile.portal_clear_width_m * 1000)
        or route["cw"] != int(profile.corridor_clear_width_m * 1000)
        or len(route["to_faces"]) != 4
        or len(route["to_offsets"]) != 4
        or len(route["points"]) != 6
        or any(len(p) != 2 for p in route["points"])
    ):
        raise LayoutAuthorityError("R9_EXISTING_PORTAL_CORRIDOR_REQUIRED")
    face = _entrance_face(context)
    normal = 0 if face < 2 else 1
    tangent = 1 - normal
    room = model.rooms["changing_room"]
    edge = ("x", "X", "y", "Y")[face]
    nearest = cp_model.SELECT_MAX_VALUE if face in (1, 3) else cp_model.SELECT_MIN_VALUE
    groups = [
        (
            [route["to_faces"][i] for i in (face, *[j for j in range(4) if j != face])],
            cp_model.SELECT_MAX_VALUE,
        ),
        ([room[edge]], nearest),
        ([room["w"], room["d"]], cp_model.SELECT_LOWER_HALF),
        ([room[("x", "y")[tangent]]], cp_model.SELECT_LOWER_HALF),
        ([p[normal] for p in reversed(route["points"])], nearest),
        ([p[tangent] for p in reversed(route["points"])], cp_model.SELECT_LOWER_HALF),
    ]
    seen: set[int] = set()
    checked = []
    for group, selection in groups:
        unique = []
        for v in group:
            context.ledger.charge("R9_PHYSICAL_REFERENCE_READ", 1)
            if v.model_proto is not model.m.proto or v.index < 0 or not v.proto.domain:
                raise LayoutAuthorityError("R9_PHYSICAL_REFERENCE_MISMATCH")
            if v.index not in seen:
                seen.add(v.index)
                unique.append(v)
        if unique:
            checked.append((unique, selection))
    return checked, face, route["pw"]


def apply_changing_frontage_corridor_search(model: Any, context: Any) -> dict[str, Any]:
    """Prepend soft choices; no definitions, constraints, objective or hints."""
    groups, face, portal_width = _joint_plan(model, context)
    strategies = model.m.proto.search_strategy
    # Admit the whole actual metadata-copy/write operation before mutation.
    work = len(strategies) + sum(len(s.exprs) for s in strategies)
    work += len(groups) + sum(len(g) for g, _ in groups)
    context.ledger.charge("R9_JOINT_STRATEGY_METADATA", work)
    previous = [deepcopy(s) for s in strategies]
    strategies.clear()
    for group, selection in groups:
        model.m.add_decision_strategy(group, cp_model.CHOOSE_FIRST, selection)
    strategies.extend(previous)
    return dict(
        policy_hash=POLICY_HASH,
        preferred_face=("WEST", "EAST", "SOUTH", "NORTH")[face],
        variable_indices=[v.index for group, _ in groups for v in group],
        physical_edge=("x", "X", "y", "Y")[face],
        portal_width_mm=portal_width,
        new_variables=0,
        new_constraints=0,
        hard_domain_changed=False,
        objective_changed=False,
        extra_native_calls=0,
        real_layout_quality_improved=False,
    )


class _ChangingFrontageCorridorNative(_FirstFeasibleRecoveryNative):
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def begin_improvement(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        # R7 enforces same model/ledger, remaining share, baseline hint and
        # one transition; R9 neither runs Solve nor rebuilds that model.
        receipt = super().begin_improvement(model, context, solver)
        joint = apply_changing_frontage_corridor_search(model, context)
        return dict(receipt, changing_joint_search=joint, policy_hash=POLICY_HASH)


class StageBChangingFrontageCorridorFairSolver(StageBFirstFeasibleRecoveryFairSolver):
    """Explicit R9 port; no bootstrap, historical runner or default is changed."""

    quality_policy_hash = POLICY_HASH
    native_type = _ChangingFrontageCorridorNative
