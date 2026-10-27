"""R10 R2: entrance-facing Changing/Sorting choices before compactness.

Only post-baseline search metadata changes. No room constraint, route clone,
objective, quality metric, old strategy or default is changed.
"""

from copy import deepcopy
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
    StageBFirstFeasibleRecoveryFairSolver,
    _FirstFeasibleRecoveryNative,
)
from cold_storage.modules.layout.infrastructure.stage_b_functional_spatial_organization import (
    POLICY_HASH as R1_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_functional_spatial_organization import (
    _organization_plan,
)

POLICY = "stage-b-r10-entrance-coupled-spatial-soft-order@2.0.0"
POLICY_HASH = canonical_hash(
    dict(
        version=POLICY,
        reference_policy=R1_HASH,
        first_stage="UNCHANGED_R7_FIRST_FEASIBLE",
        activation="AFTER_THIS_HANDOFF_INDEPENDENTLY_ACCEPTED_BASELINE",
        order="CHANGING_SORTING_ENTRANCE_BOUNDARIES_SPANS_COMPACTNESS_PORTAL_ROUTE",
        tangent="TOWARD_VALIDATED_CURRENT_ENTRANCE_PORTAL_FROM_VALIDATED_ROOM_CENTRE",
        objective="UNCHANGED_R5_MAX_DEMAND_NORMALIZED_SEMIPERIMETER_SQUARED",
        physical_domain="IDENTICAL_CONSTRAINTS_VARIABLES_DOMAINS_AND_HINT",
        quality="UNCHANGED_NINE_TWELVE_AND_V2_SCOPE",
        resources="SAME_MODEL_LEDGER_AND_SHARE_NO_ROUTE_COPY_OR_EXTRA_SOLVE",
    )
)


def apply_entrance_coupled_spatial(model: Any, context: Any, proxy_index: int) -> dict[str, Any]:
    # Reuse R1's prepared Reference model, original P1/area definitions,
    # Office/Shipping and Coating-process checks; this does not mutate metadata.
    original_groups, facts = _organization_plan(model, context, proxy_index)
    pair = ("changing_room", "sorting_packaging_room")
    refs = []
    for route in model.routes:
        context.ledger.charge("R10_R2_ACCESS_REFERENCE_READ", 1)
        if (route["req"]["from_ref"], route["req"]["to_ref"]) == pair:
            refs.append(route)
    required = []
    for req in context.binding.access_requirements:
        context.ledger.charge("R10_R2_AUTHORITY_REFERENCE_READ", 1)
        if (req["from_ref"], req["to_ref"]) == pair:
            required.append(req)
    if len(refs) != 1 or len(required) != 1 or refs[0]["req"] != required[0]:
        raise LayoutAuthorityError("R10_R2_ORIGINAL_CHANGING_SORTING_ACCESS_REQUIRED")
    ingress = next(
        r
        for r in model.routes
        if (r["req"]["from_ref"], r["req"]["to_ref"]) == ("main_entrance", "changing_room")
    )
    if not model.m.proto.has_solution_hint():
        raise LayoutAuthorityError("R10_R2_VALID_PHYSICAL_HINT_REQUIRED")
    hint = model.m.proto.solution_hint
    if len(hint.vars) != len(hint.values):
        raise LayoutAuthorityError("R10_R2_VALID_PHYSICAL_HINT_REQUIRED")
    context.ledger.charge("R10_R2_HINT_REFERENCE_READ", len(hint.vars))
    values = dict(zip(hint.vars, hint.values, strict=True))
    if len(values) != len(hint.vars):
        raise LayoutAuthorityError("R10_R2_VALID_PHYSICAL_HINT_REQUIRED")
    face = ("WEST", "EAST", "SOUTH", "NORTH").index(facts["preferred_entrance_face"])
    normal = 0 if face < 2 else 1
    tangent = 1 - normal
    near = ("x", "X", "y", "Y")[face]
    toward = cp_model.SELECT_MIN_VALUE if face in (0, 2) else cp_model.SELECT_MAX_VALUE
    coord, span = ("x", "y")[tangent], ("w", "d")[tangent]
    context.ledger.charge("R10_R2_ENTRY_POINT_READ", 2)
    point = ingress["points"][0]
    if any(v.model_proto is not model.m.proto or v.index not in values for v in point):
        raise LayoutAuthorityError("R10_R2_VALIDATED_ENTRANCE_PORTAL_REQUIRED")
    entry = [values[v.index] for v in point]
    a, b = context.entrances["main_entrance"]
    if entry[normal] != a[normal] or not min(a[tangent], b[tangent]) <= entry[tangent] <= max(
        a[tangent], b[tangent]
    ):
        raise LayoutAuthorityError("R10_R2_VALIDATED_ENTRANCE_PORTAL_REQUIRED")
    entrance_tangent_twice = 2 * entry[tangent]
    tangent_groups = []
    centres = {}
    for role in ("changing_room", "sorting_packaging_room"):
        room = model.rooms[role]
        context.ledger.charge("R10_R2_VALIDATED_CENTRE_READ", 2)
        if any(room[k].index not in values for k in (coord, span)):
            raise LayoutAuthorityError("R10_R2_VALID_PHYSICAL_HINT_REQUIRED")
        centre = 2 * values[room[coord].index] + values[room[span].index]
        centres[role] = centre
        # Current entrance portal and room centre use doubled integer-mm values.
        # Only choose a soft direction; no historical point or target is fixed.
        selection = (
            cp_model.SELECT_MAX_VALUE
            if entrance_tangent_twice > centre
            else cp_model.SELECT_MIN_VALUE
        )
        tangent_groups.append(([room[coord]], selection))
    changing, sorting = (model.rooms[r] for r in ("changing_room", "sorting_packaging_room"))
    groups = [
        ([changing[near]], toward),
        ([sorting[near]], toward),
        *tangent_groups,
        ([changing["w"], changing["d"]], cp_model.SELECT_LOWER_HALF),
        *original_groups[:3],  # Unchanged P1-normalized compactness references.
        (
            [ingress["to_faces"][i] for i in (face, *[j for j in range(4) if j != face])],
            cp_model.SELECT_MAX_VALUE,
        ),
        ([p[normal] for p in ingress["points"]], toward),
    ]
    seen = set()
    checked = []
    for group, selection in groups:
        unique = []
        for variable in group:
            context.ledger.charge("R10_R2_PHYSICAL_REFERENCE_READ", 1)
            if (
                variable.model_proto is not model.m.proto
                or variable.index < 0
                or not variable.proto.domain
            ):
                raise LayoutAuthorityError("R10_R2_PHYSICAL_REFERENCE_MISMATCH")
            if variable.index not in seen:
                unique.append(variable)
                seen.add(variable.index)
        if unique:
            checked.append((unique, selection))
    strategies = model.m.proto.search_strategy
    work = len(strategies) + sum(len(s.exprs) for s in strategies)
    work += len(checked) + sum(len(group) for group, _ in checked)
    context.ledger.charge("R10_R2_COUPLED_SEARCH_METADATA", work)
    previous = [deepcopy(s) for s in strategies]
    strategies.clear()
    for group, selection in checked:
        model.m.add_decision_strategy(group, cp_model.CHOOSE_FIRST, selection)
    strategies.extend(previous)
    return dict(
        facts,
        policy_hash=POLICY_HASH,
        validated_entrance_portal_mm=entry,
        validated_tangent_centres_twice_mm=centres,
        variable_indices=[v.index for group, _ in checked for v in group],
        new_variables=0,
        new_constraints=0,
        hard_domain_changed=False,
        objective_changed=False,
        hint_changed=False,
        local_model_copies=0,
        extra_native_calls=0,
        overall_quality_improvement_claimed=False,
    )


class _EntranceCoupledSpatialNative(_FirstFeasibleRecoveryNative):
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def begin_improvement(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        receipt = super().begin_improvement(model, context, solver)
        coupled = apply_entrance_coupled_spatial(model, context, self._feedback_proxy_index)
        return dict(receipt, entrance_coupled_search=coupled, policy_hash=POLICY_HASH)


class StageBEntranceCoupledSpatialFairSolver(StageBFirstFeasibleRecoveryFairSolver):
    """Independent R2 experiment; no old Runner, Grant or default selects it."""

    quality_policy_hash = POLICY_HASH
    native_type = _EntranceCoupledSpatialNative
