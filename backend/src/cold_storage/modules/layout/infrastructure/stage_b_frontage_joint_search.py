"""R6 opt-in: existing frontage choices, physical hints, independent search frontier.

No new physical constraint, objective weight, tolerance, budget or authorization.
The original nine/twelve comparators and first accepted baseline are unchanged.
"""

from copy import deepcopy
from fractions import Fraction
from typing import Any, cast

from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    POLICY_HASH as R5_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    SCALE,
    StageBAreaEfficientQualityFairSearchSolver,
    _area_receipt,
    _area_specs,
    _AreaEfficientNative,
    _define_area_proxy,
    _demands,
)
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    SHAPE_POLICY_HASH as R5_SHAPE_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_model_references import ReferenceCpModel

SHAPE_POLICY_HASH = canonical_hash(
    dict(
        version="r6-owned-reference-area-preparation@1.0.0",
        objective=R5_SHAPE_HASH,
        validation="SAME_P1_POSITIVE_DOMAIN_GLOBAL_AND_DERIVED_INT64_CHECKS",
        facts="APPEND_ONLY_SOURCE_OWNED_MODEL_NO_CROSS_MODEL_CACHE",
    )
)
FRONTAGE_POLICY_HASH = canonical_hash(
    dict(
        version="r6-existing-frontage-seam-decision-prefix@1.0.0",
        entrance="BOUNDARY_FACING_CHANGING_PORTAL",
        changing_exit="EXISTING_PERSONNEL_DOMAIN_TO_SORTING_SIDE",
        packaging="DIRECT_THEN_EXISTING_DOMAIN_SIDE",
        seams="EXISTING_MUST_PROCESS_DIRECTION_THEN_EXISTING_OFFSETS",
        office="EXISTING_OFFICE_SHIPPING_MUST_ONLY_NO_NEW_DOOR_AUTHORITY",
        hard_constraints="UNCHANGED",
        objective="UNCHANGED_R5",
    )
)
POLICY_HASH = canonical_hash(
    dict(
        version="stage-b-r6-frontage-joint-search@1.0.0",
        parent=R5_HASH,
        preparation=SHAPE_POLICY_HASH,
        frontage=FRONTAGE_POLICY_HASH,
        hint="THIS_EXECUTION_ACCEPTED_PHYSICAL_CHOICES_ONLY",
        frontier="MONOTONE_VALIDATED_PROXY_INDEPENDENT_OF_FORMAL_PARETO",
        baseline="NEVER_REPLACE",
        resources="ORIGINAL_LEDGER_NO_EXTRA_SOLVE",
    )
)


class _ReferenceAccessModel(AccessModel):
    def _new_cp_model(self) -> ReferenceCpModel:
        return ReferenceCpModel(self.c.ledger.charge)

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.m.seal(self)


def apply_reference_area_guidance(model: Any, context: Any) -> dict[str, Any]:
    if model.c is not context or not isinstance(model.m, ReferenceCpModel):
        raise LayoutAuthorityError("R6_SOURCE_OWNED_REFERENCE_MODEL_REQUIRED")
    if model.m.has_objective():
        raise LayoutAuthorityError("R5_CONTEXT_OR_OBJECTIVE_MISMATCH")
    demands = _demands(context.binding)
    magnitude, refs = model.m.checked_physical(model)
    physical = {r: tuple(refs[r + "_physical_" + s] for s in ("w", "d")) for r in demands}
    specs = _area_specs(demands, physical, magnitude)
    # Same 27 definitions plus exactly 13 real creation-time records. Admit
    # the WHOLE batch before any target definitions/objective are modified.
    context.ledger.precharge_work(40)
    with model.m.definitions():
        _define_area_proxy(model, context, specs)
    return dict(
        _area_receipt(context, demands),
        policy_hash=SHAPE_POLICY_HASH,
        reference_variable_count=6,
        full_proto_scan=False,
        creation_records=model.m.recorded,
        implicit_constant_reads=model.m.implicit_reads,
    )


def _entrance_face(context: Any) -> int:
    """Endpoint order: W,E,S,N (NOT the MUST/direct E,W,N,S order)."""
    a, b = context.entrances["main_entrance"]
    sx, sy, sr, st = context.sitebox
    if a[0] == b[0] == sr:
        return 1
    if a[0] == b[0] == sx:
        return 0
    if a[1] == b[1] == st:
        return 3
    if a[1] == b[1] == sy:
        return 2
    raise LayoutAuthorityError("R6_BOUNDARY_ENTRANCE_REFERENCE_REQUIRED")


def apply_frontage_joint_search(model: Any, context: Any) -> dict[str, Any]:
    """Prefix existing Boolean decisions; no added vars, constraints or objective."""
    if model.c is not context:
        raise LayoutAuthorityError("R6_FRONTAGE_CONTEXT_MISMATCH")
    routes = {(r["req"]["from_ref"], r["req"]["to_ref"]): r for r in model.routes}
    if len(routes) != len(model.routes):
        raise LayoutAuthorityError("R6_FRONTAGE_AMBIGUOUS_REQUIREMENT")
    pairs = [
        ("main_entrance", "changing_room"),
        ("changing_room", "sorting_packaging_room"),
        ("secondary_precooling_room", "coating_room"),
        ("coating_room", "finished_goods_room"),
    ]
    if any(p not in routes for p in pairs):
        raise LayoutAuthorityError("R6_FRONTAGE_REQUIREMENT_MISSING")
    required = {(r["from_ref"], r["to_ref"]): r for r in context.binding.access_requirements}
    if any(p not in required or required[p]["flow_kind"] == "TRUCK" for p in pairs):
        raise LayoutAuthorityError("R6_FRONTAGE_AUTHORITY_MISSING")
    face = _entrance_face(context)
    ingress = routes[pairs[0]]
    if len(ingress["to_faces"]) != 4:
        raise LayoutAuthorityError("R6_CHANGING_FACE_BINDING_REQUIRED")
    direction = model.handoff.process_direction.value
    axis = model.handoff.process_axis.value
    forward = (
        (0 if direction == "POSITIVE" else 1)
        if axis == "X"
        else (2 if direction == "POSITIVE" else 3)
    )
    groups: list[tuple[list[Any], Any]] = [
        (
            [ingress["to_faces"][i] for i in (face, *[j for j in range(4) if j != face])],
            cp_model.SELECT_MAX_VALUE,
        )
    ]
    offsets: list[Any] = []
    for pair in pairs[1:]:
        route = routes[pair]
        groups.append(([route["corridor"]], cp_model.SELECT_MIN_VALUE))
        preferred_direct = forward
        if pair == ("changing_room", "sorting_packaging_room"):
            ax, sign = model.faces["changing_room"]
            # Existing domain says where Changing's centre lies relative to
            # Sorting. Try the connecting face first, never enforce that side.
            preferred_direct = (0 if sign < 0 else 1) if ax == "X" else (2 if sign < 0 else 3)
        direct = sorted(route["direct"], key=lambda d: (d["side"] != preferred_direct, d["side"]))
        groups.append(([d["active"] for d in direct], cp_model.SELECT_MAX_VALUE))
        for d in direct:
            offsets.extend(d["portal_choices"])
    if not model.interfaces:
        raise LayoutAuthorityError("R6_PACKAGING_CHOICES_REQUIRED")
    domain_axis, sign = model.faces["packaging_material_storage"]
    preferred = (
        ("EAST" if sign > 0 else "WEST")
        if domain_axis == "X"
        else ("NORTH" if sign > 0 else "SOUTH")
    )
    interfaces = sorted(
        model.interfaces, key=lambda i: (i["corridor"], i["side"] != preferred, i["side"])
    )
    groups.append(([i["active"] for i in interfaces], cp_model.SELECT_MAX_VALUE))
    for pair in [
        ("secondary_precooling_room", "coating_room"),
        ("coating_room", "finished_goods_room"),
        ("office", "shipping_channel"),
    ]:
        flags = model.must_choices.get(pair)
        if flags is None or pair not in context.must:
            raise LayoutAuthorityError("R6_EXISTING_MUST_REFERENCE_REQUIRED")
        groups.append(
            (
                [flags[i] for i in (forward, *[j for j in range(4) if j != forward])],
                cp_model.SELECT_MAX_VALUE,
            )
        )
    for route in (routes[p] for p in pairs):
        for key in ("from_offsets", "to_offsets"):
            for group in route[key]:
                offsets.extend(group)
    for interface in interfaces:
        for group in interface["portal_choices"]:
            offsets.extend(group)
    groups.append((offsets, cp_model.SELECT_MAX_VALUE))
    seen = set()
    selected = []
    for group, selection in groups:
        unique = []
        for v in group:
            context.ledger.charge("R6_FRONTAGE_REFERENCE_READ", 1)
            if v.model_proto is not model.m.proto or v.index < 0 or list(v.proto.domain) != [0, 1]:
                raise LayoutAuthorityError("R6_FRONTAGE_LITERAL_IDENTITY_MISMATCH")
            if v.index not in seen:
                seen.add(v.index)
                unique.append(v)
        if unique:
            selected.append((unique, selection))
    context.ledger.charge("R6_FRONTAGE_STRATEGY_WRITE", len(seen))
    for group, selection in selected:
        model.m.add_decision_strategy(group, cp_model.CHOOSE_FIRST, selection)
    return dict(
        policy_hash=FRONTAGE_POLICY_HASH,
        variable_indices=[v.index for g, _ in selected for v in g],
        changing_preferred_endpoint_face=("WEST", "EAST", "SOUTH", "NORTH")[face],
        packaging_preferred_side=preferred,
        hard_domain_changed=False,
        new_variables=0,
        new_constraints=0,
        objective_changed=False,
    )


def install_physical_hint(model: Any, context: Any, solver: Any) -> dict[str, Any]:
    """Read only current accepted physical choices; never raw historical coordinates."""
    found: dict[int, Any] = {}

    def add(v: Any) -> None:
        if isinstance(v, int):
            return
        context.ledger.charge("R6_PHYSICAL_HINT_REFERENCE", 1)
        if v.model_proto is not model.m.proto or v.index < 0:
            raise LayoutAuthorityError("R6_PHYSICAL_HINT_MODEL_MISMATCH")
        found[v.index] = v

    def active(v: Any) -> bool:
        context.ledger.charge("R6_PHYSICAL_HINT_SELECTOR", 1)
        return bool(solver.boolean_value(v))

    for room in model.rooms.values():
        for key in ("x", "y", "w", "d"):
            add(room[key])
    for interface in model.interfaces:
        add(interface["active"])
        if active(interface["active"]):
            add(interface["center"])
            for group in interface.get("portal_choices", ()):
                for v in group:
                    add(v)
    for route in model.routes:
        add(route["corridor"])
        if active(route["corridor"]):
            for point in route["points"]:
                for v in point:
                    add(v)
            for key in ("from_faces", "to_faces"):
                for v in route[key]:
                    add(v)
        else:
            for direct in route["direct"]:
                add(direct["active"])
                if active(direct["active"]):
                    add(direct["center"])
    context.ledger.charge("R6_CURRENT_VALID_PHYSICAL_HINT", len(found))
    values = [(v, solver.value(v)) for v in found.values()]
    model.m.clear_hints()
    for v, value in values:
        model.m.add_hint(v, value)
    return dict(
        hint_variable_count=len(found),
        total_variables=len(model.m.proto.variables),
        source="THIS_MODEL_CURRENT_EXECUTION_INDEPENDENTLY_ACCEPTED",
        hard_domain_changed=False,
    )


def validated_area_proxy(snapshot: dict[str, Any]) -> int:
    values = []
    for room in snapshot["area_efficiency"]["rooms"].values():
        w, d = (Fraction(room[k]) * 1000 for k in ("physical_width_m", "physical_depth_m"))
        area = Fraction(room["required_area_m2"]) * 1_000_000
        minimum = -(-area.numerator // area.denominator)
        if w.denominator != 1 or d.denominator != 1 or w <= 0 or d <= 0 or minimum <= 0:
            raise LayoutAuthorityError("R6_VALIDATED_INTEGER_PHYSICAL_FACTS_REQUIRED")
        values.append((SCALE * int(w + d) ** 2 + 4 * minimum - 1) // (4 * minimum))
    if len(values) != 3:
        raise LayoutAuthorityError("R6_THREE_BOUND_ROOMS_REQUIRED")
    return max(values)


class _FrontageNative(_AreaEfficientNative):
    continuation_policy = "stage-b-r6-frontage-joint-search@1.0.0"
    continuation_policy_hash = POLICY_HASH

    def _new_final_model(self, context: Any, handoff: Any) -> Any:
        return _ReferenceAccessModel(context, handoff, True)

    def prepare_first_stage(self, model: Any, context: Any) -> dict[str, Any]:
        receipt = apply_reference_area_guidance(model, context)
        self._area_model = model.m
        self._feedback_proxy_index = len(model.m.proto.variables) - 1
        self._area_receipt = deepcopy(receipt)
        return receipt

    def _hint_current_assignment(self, model: Any, context: Any, solver: Any) -> None:
        self.last_hint_receipt = install_physical_hint(model, context, solver)

    def advance_frontier(self, model: Any, context: Any, solver: Any, proxy: int) -> None:
        if (
            model.c is not context
            or context.ledger is not self.ledger
            or model.m is not self._feedback_model
            or solver.value(model.m.get_int_var_from_proto_index(self._feedback_proxy_index))
            != proxy
            or proxy >= self._baseline_proxy
        ):
            raise LayoutAuthorityError("R6_VALIDATED_FRONTIER_MODEL_MISMATCH")
        context.ledger.charge("R6_VALIDATED_SEARCH_FRONTIER", 1)
        self._baseline_proxy = proxy

    def refresh_validated_hint(self, model: Any, context: Any, solver: Any) -> dict[str, Any]:
        if (
            model.c is not context
            or context.ledger is not self.ledger
            or model.m is not self._feedback_model
        ):
            raise LayoutAuthorityError("R6_VALIDATED_HINT_MODEL_MISMATCH")
        receipt = install_physical_hint(model, context, solver)
        return dict(receipt, policy_hash=POLICY_HASH, original_baseline_preserved=True)


class StageBFrontageJointSearchFairSolver(StageBAreaEfficientQualityFairSearchSolver):
    quality_policy_hash = POLICY_HASH
    native_type = _FrontageNative

    def start_handoff(self, ledger: Any, remaining_handoffs: int) -> None:
        super().start_handoff(ledger, remaining_handoffs)
        self.search_frontier: int | None = None
        self.pending_frontier: tuple[int, str] | None = None

    def _continuation_options(self, context: Any) -> dict[str, Any]:
        return dict(
            super()._continuation_options(context),
            final_model_search=lambda model: apply_frontage_joint_search(model, context),
        )

    def _observe_search_frontier(self, snapshot: dict[str, Any]) -> None:
        # Three physical facts per room, then the maximum reduction. Reuse the
        # already validated snapshot, but still charge this new search operation.
        self.native.ledger.charge("R6_VALIDATED_PROXY_FACTS", 10)
        proxy = validated_area_proxy(snapshot)
        if self.search_frontier is None:
            self.search_frontier = proxy
        elif proxy < self.search_frontier:
            self.search_frontier = proxy
            self.pending_frontier = (proxy, snapshot["candidate_hash"])

    def _refresh_validated_hint(
        self, model: Any, context: Any, solver: Any
    ) -> dict[str, Any] | None:
        if self.pending_frontier is not None:
            if self.baseline is None:
                raise LayoutAuthorityError("R6_VALIDATED_BASELINE_REQUIRED")
            proxy, candidate_hash = self.pending_frontier
            engine = cast(_FrontageNative, self.native)
            previous = engine._baseline_proxy
            engine.advance_frontier(model, context, solver, proxy)
            context.ledger.execution_authorization.record_enumeration(
                dict(
                    zone_plan_hash=context.binding.canonical_zone_plan_hash,
                    p1_hash=context.binding.p1_handoff_hash,
                    site_hash=context.binding.site_geometry_hash,
                    composition_hash=self.baseline["composition_hash"],
                ),
                dict(
                    kind="VALIDATED_SEARCH_FRONTIER_UPDATED",
                    policy_hash=POLICY_HASH,
                    previous_proxy=previous,
                    search_proxy=proxy,
                    candidate_hash=candidate_hash,
                    formal_quality_improvement=False,
                    hard_domain_changed=False,
                ),
            )
            self.pending_frontier = None
        return super()._refresh_validated_hint(model, context, solver)
