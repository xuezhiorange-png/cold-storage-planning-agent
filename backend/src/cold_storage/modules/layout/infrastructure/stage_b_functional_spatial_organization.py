"""R10 opt-in, post-baseline room organization; no local route model copy.

Branch on the existing P1-demand-normalized room compactness definitions BEFORE
entrance-facing location/portal choices. This is soft search metadata, not a
new objective, room-size Authority, layout template, or quality acceptance rule.
Coating retains its process relationships; only Changing follows the entrance.
"""

from copy import deepcopy
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import _demands
from cold_storage.modules.layout.infrastructure.stage_b_changing_frontage_corridor import (
    POLICY_HASH as R9_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_construction_guidance import (
    FUNCTIONAL_SHAPE_ROLES,
)
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
    StageBFirstFeasibleRecoveryFairSolver,
    _FirstFeasibleRecoveryNative,
)
from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import _entrance_face
from cold_storage.modules.layout.infrastructure.stage_b_model_references import ReferenceCpModel

POLICY = "stage-b-r10-functional-spatial-organization-soft-order@1.0.0"
POLICY_HASH = canonical_hash(
    dict(
        version=POLICY,
        reference_policy=R9_HASH,
        first_stage="UNCHANGED_R7_FIRST_FEASIBLE_REFERENCE_MODEL",
        activation="AFTER_THIS_HANDOFF_PERSISTED_ENGINEERING_VALID_BASELINE",
        compactness="EXISTING_P1_NORMALIZED_CHANGING_OFFICE_COATING_PROXIES_FIRST",
        placement="CHANGING_ENTRANCE_NORMAL_THEN_ENTRANCE_TANGENT_HALF_SITE",
        process="EXISTING_OFFICE_SHIPPING_MUST_AND_COATING_PROCESS_FRONTAGES",
        physical_domain="IDENTICAL_VARIABLES_CONSTRAINTS_DOMAINS_AND_OBJECTIVE",
        hints="CURRENT_VALID_PHYSICAL_HINT_UNCHANGED",
        weighting="NONE_NO_COMPOSITE_SCORE_OR_NEW_SIZE_THRESHOLD",
        resources="SAME_MODEL_HANDOFF_AND_LEDGER_NO_LOCAL_COPY_OR_EXTRA_SOLVE",
        quality="UNCHANGED_NINE_AND_TWELVE_METRICS_WITH_V2_ISOLATION",
    )
)


def _organization_plan(
    model: Any, context: Any, proxy_index: int
) -> tuple[list[tuple[list[Any], Any]], dict[str, Any]]:
    m = model.m
    if (
        model.c is not context
        or not isinstance(m, ReferenceCpModel)
        or m.owner is not model
        or not m.defined
        or not m.has_objective()
    ):
        raise LayoutAuthorityError("R10_BOUND_PREPARED_MODEL_REQUIRED")
    context.ledger.charge("R10_P1_DEMAND_READ", len(FUNCTIONAL_SHAPE_ROLES))
    demands = _demands(context.binding)  # Original source/positive-area checks, no new areas.
    # R5 creates a checked, contiguous block of 3*4 total definitions + max.
    # Its captured max index remains stable when later topology cuts add vars.
    # Read only this 13-reference block, never index all model variables by name.
    names = [
        "r5_area_" + role + "_" + suffix
        for role in FUNCTIONAL_SHAPE_ROLES
        for suffix in ("semiperimeter", "square", "n", "proxy")
    ] + ["r5_area_worst"]
    if type(proxy_index) is not int or not 12 <= proxy_index < len(m.proto.variables):
        raise LayoutAuthorityError("R10_AREA_REFERENCE_BLOCK_REQUIRED")
    proxies = {}
    for index, name in zip(range(proxy_index - 12, proxy_index + 1), names, strict=True):
        context.ledger.charge("R10_AREA_REFERENCE_READ", 1)
        variable = m.get_int_var_from_proto_index(index)
        if variable.name != name or not variable.proto.domain or variable.proto.domain[0] <= 0:
            raise LayoutAuthorityError("R10_AREA_REFERENCE_BLOCK_REQUIRED")
        if name.endswith("_proxy"):
            proxies[name] = variable
    objective = m.proto.objective
    if list(objective.vars) != [proxy_index] or list(objective.coeffs) != [1]:
        raise LayoutAuthorityError("R10_ORIGINAL_AREA_OBJECTIVE_REQUIRED")
    if ("office", "shipping_channel") not in context.must:
        raise LayoutAuthorityError("R10_OFFICE_SHIPPING_MUST_REQUIRED")
    for pair in (
        ("office", "shipping_channel"),
        ("secondary_precooling_room", "coating_room"),
        ("coating_room", "finished_goods_room"),
    ):
        context.ledger.charge("R10_MUST_REFERENCE_READ", 1)
        if pair not in context.must or len(model.must_choices.get(pair, ())) != 4:
            raise LayoutAuthorityError("R10_ORIGINAL_PROCESS_MUST_REQUIRED")
    ingress = []
    for route in model.routes:
        context.ledger.charge("R10_ROUTE_REFERENCE_READ", 1)
        if (route["req"]["from_ref"], route["req"]["to_ref"]) == (
            "main_entrance",
            "changing_room",
        ):
            ingress.append(route)
    if len(ingress) != 1 or len(ingress[0]["to_faces"]) != 4:
        raise LayoutAuthorityError("R10_ORIGINAL_PERSONNEL_ROUTE_REQUIRED")
    face = _entrance_face(context)
    normal = 0 if face < 2 else 1
    tangent = 1 - normal
    a, b = context.entrances["main_entrance"]
    # Compare doubled midpoints; no rounding, historical point, room width or
    # furniture dimension is introduced. The choice remains a branch preference.
    entrance_sum = a[tangent] + b[tangent]
    site_sum = context.sitebox[tangent] + context.sitebox[tangent + 2]
    tangent_selection = (
        cp_model.SELECT_MIN_VALUE if entrance_sum <= site_sum else cp_model.SELECT_MAX_VALUE
    )
    edge = ("x", "X", "y", "Y")[face]
    toward_entrance = cp_model.SELECT_MIN_VALUE if face in (0, 2) else cp_model.SELECT_MAX_VALUE
    changing = model.rooms["changing_room"]
    groups = [
        ([proxies["r5_area_" + role + "_proxy"]], cp_model.SELECT_MIN_VALUE)
        for role in ("changing_room", "office", "coating_room")
    ]
    # Compact room spans are considered before trying a boundary-extreme position.
    # Original R7 frontage/process strategies remain as the unchanged suffix.
    groups += [
        ([changing["w"], changing["d"]], cp_model.SELECT_LOWER_HALF),
        ([changing[edge]], toward_entrance),
        ([changing[("x", "y")[tangent]]], tangent_selection),
        (
            [ingress[0]["to_faces"][i] for i in (face, *[j for j in range(4) if j != face])],
            cp_model.SELECT_MAX_VALUE,
        ),
    ]
    seen = set()
    checked = []
    for group, selection in groups:
        unique = []
        for v in group:
            context.ledger.charge("R10_PHYSICAL_REFERENCE_READ", 1)
            if v.model_proto is not m.proto or v.index < 0 or not v.proto.domain:
                raise LayoutAuthorityError("R10_PHYSICAL_REFERENCE_MISMATCH")
            if v.index not in seen:
                seen.add(v.index)
                unique.append(v)
        if unique:
            checked.append((unique, selection))
    return checked, dict(
        preferred_entrance_face=("WEST", "EAST", "SOUTH", "NORTH")[face],
        normal_axis=("X", "Y")[normal],
        tangent_axis=("X", "Y")[tangent],
        entrance_tangent_midpoint_twice_mm=entrance_sum,
        site_tangent_midpoint_twice_mm=site_sum,
        tangent_preference="LOWER" if entrance_sum <= site_sum else "UPPER",
        required_area_m2={r: str(v) for r, v in demands.items()},
    )


def apply_functional_spatial_organization(
    model: Any, context: Any, proxy_index: int
) -> dict[str, Any]:
    """Validate/charge before reordering; no physical assignment can be removed."""
    groups, facts = _organization_plan(model, context, proxy_index)
    strategies = model.m.proto.search_strategy
    work = len(strategies) + sum(len(s.exprs) for s in strategies)
    work += len(groups) + sum(len(group) for group, _ in groups)
    context.ledger.charge("R10_ORGANIZATION_SEARCH_METADATA", work)
    previous = [deepcopy(s) for s in strategies]
    strategies.clear()
    for group, selection in groups:
        model.m.add_decision_strategy(group, cp_model.CHOOSE_FIRST, selection)
    strategies.extend(previous)
    return dict(
        facts,
        policy_hash=POLICY_HASH,
        variable_indices=[v.index for group, _ in groups for v in group],
        new_variables=0,
        new_constraints=0,
        hard_domain_changed=False,
        objective_changed=False,
        hint_changed=False,
        local_model_copies=0,
        extra_native_calls=0,
        furniture_layout_validated=False,
        real_layout_quality_improved=False,
    )


class _FunctionalSpatialNative(_FirstFeasibleRecoveryNative):
    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def begin_improvement(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        receipt = super().begin_improvement(model, context, solver)
        organization = apply_functional_spatial_organization(
            model, context, self._feedback_proxy_index
        )
        return dict(receipt, spatial_organization=organization, policy_hash=POLICY_HASH)


class StageBFunctionalSpatialOrganizationFairSolver(StageBFirstFeasibleRecoveryFairSolver):
    """Explicit R10 strategy only; no Runner, Store, lease or production default."""

    quality_policy_hash = POLICY_HASH
    native_type = _FunctionalSpatialNative
