"""Explicit post-baseline route refinement; no default/runner activation.

Clone the current model into a bounded local scope, freeze accepted room geometry,
area proxy and non-personnel Access witnesses, then minimize the EXACT exported
personnel polyline length. Original engineering feedback remains authoritative.
No local constraints, objective or hints are copied back to the parent model.
"""

from collections.abc import Generator
from typing import Any, cast

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import (
    validate_global_geometry,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
from cold_storage.modules.layout.infrastructure.global_cp_sat_solver import (
    physical_assignment_variables,
)
from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
    area_efficiency_snapshot,
    compare_area_efficient_quality,
)
from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
    compare_balanced_quality,
)
from cold_storage.modules.layout.infrastructure.stage_b_changing_frontage_corridor import (
    POLICY_HASH as R9_HASH,
)
from cold_storage.modules.layout.infrastructure.stage_b_changing_frontage_corridor import (
    StageBChangingFrontageCorridorFairSolver,
    _ChangingFrontageCorridorNative,
)

MAX_ROUTE_ATTEMPTS = 2
MAX_ROUTE_SECONDS = 1.5
MIN_ROUTE_SECONDS = 0.02
POLICY = "stage-b-r9-same-proxy-personnel-route-refinement@1.0.0"
POLICY_HASH = canonical_hash(
    dict(
        version=POLICY,
        parent=R9_HASH,
        activation="AFTER_SECOND_STAGE_INDEPENDENT_ENGINEERING_ACCEPTANCE",
        scope="CLONE_ACCEPTED_ROOMS_PROXY_AND_OTHER_ACCESS_WITNESSES",
        objective="EXACT_ORIGINAL_EXPORTED_PERSONNEL_POLYLINE_LENGTH_MM",
        attempts=MAX_ROUTE_ATTEMPTS,
        seconds_per_call=MAX_ROUTE_SECONDS,
        allocation="AT_MOST_QUARTER_REMAINING_HANDOFF_NATIVE_AND_ELAPSED",
        feedback="ORIGINAL_APPLICATION_ORACLES_BEFORE_ACCEPTANCE",
        exit="DISCARD_LOCAL_MODEL_THEN_ORIGINAL_EXACT_ROOM_ENUMERATION",
        comparison="UNCHANGED_NINE_AND_TWELVE_WITH_V2_ISOLATION",
        resources="ORIGINAL_CUMULATIVE_LEDGER_NO_NEW_SHARE",
    )
)


class _Definitions:
    """Bill real local variable/constraint writes, before each operation."""

    def __init__(self, model: Any, charge: Any) -> None:
        self.m, self.charge = model, charge

    def integer(self, low: int, high: int, name: str) -> Any:
        self.charge("ROUTE_LOCAL_VARIABLE", 1)
        return self.m.new_int_var(low, high, name)

    def boolean(self, name: str) -> Any:
        self.charge("ROUTE_LOCAL_VARIABLE", 1)
        return self.m.new_bool_var(name)

    def add(self, expression: Any) -> Any:
        self.charge("ROUTE_LOCAL_CONSTRAINT", 1)
        return self.m.add(expression)

    def both(self, literals: list[Any]) -> Any:
        b = self.boolean("route_and")
        self.charge("ROUTE_LOCAL_CONSTRAINT", 2)
        self.m.add_bool_and(literals).only_enforce_if(b)
        self.m.add_bool_or([v.Not() for v in literals] + [b])
        return b

    def either(self, literals: list[Any]) -> Any:
        b = self.boolean("route_or")
        self.charge("ROUTE_LOCAL_CONSTRAINT", 2)
        self.m.add_bool_or(literals).only_enforce_if(b)
        self.m.add_bool_and([v.Not() for v in literals]).only_enforce_if(b.Not())
        return b


def exported_length_expression(model: Any, points: list[Any], charge: Any) -> Any:
    """Encode AccessModel.export_routes' six-point compression, including reversals.

    States contain indices of the original points in the exporter's small stack.
    Duplicate -> keep; three collinear -> replace last; otherwise -> append.
    This is a total definition, not a simple-path restriction or a distance proxy.
    """
    if len(points) != 6 or any(len(p) != 2 for p in points):
        raise LayoutAuthorityError("ROUTE_REFINEMENT_FIVE_SEGMENT_REQUIRED")
    d = _Definitions(model, charge)
    bounds: list[int] = []
    for p in points:
        for v in p:
            charge("ROUTE_LOCAL_REFERENCE", 1)
            if v.model_proto is not model.proto or v.index < 0 or not v.proto.domain:
                raise LayoutAuthorityError("ROUTE_REFINEMENT_FOREIGN_POINT")
            bounds.extend((v.proto.domain[0], v.proto.domain[len(v.proto.domain) - 1]))
    span = max(bounds) - min(bounds)
    if span < 0 or 10 * span >= (1 << 62):
        raise LayoutAuthorityError("ROUTE_REFINEMENT_LENGTH_OVERFLOW")
    equal: dict[tuple[int, int, int], Any] = {}
    distance: dict[tuple[int, int], Any] = {}

    def eq(i: int, j: int, axis: int) -> Any:
        key = (min(i, j), max(i, j), axis)
        if key not in equal:
            b = d.boolean("route_coordinate_equal")
            d.add(points[i][axis] == points[j][axis]).only_enforce_if(b)
            d.add(points[i][axis] != points[j][axis]).only_enforce_if(b.Not())
            equal[key] = b
        return equal[key]

    def dist(i: int, j: int) -> Any:
        key = (min(i, j), max(i, j))
        if key not in distance:
            terms = []
            for axis in (0, 1):
                v = d.integer(0, span, "route_abs_coordinate")
                charge("ROUTE_LOCAL_CONSTRAINT", 1)
                model.add_abs_equality(v, points[i][axis] - points[j][axis])
                terms.append(v)
            v = d.integer(0, 2 * span, "route_point_distance")
            d.add(v == sum(terms))
            distance[key] = v
        return distance[key]

    initial = d.boolean("route_initial_stack")
    d.add(initial == 1)
    states: dict[tuple[int, ...], Any] = {(0,): initial}
    for i in range(1, 6):
        incoming: dict[tuple[int, ...], list[Any]] = {}
        for stack, active in states.items():
            duplicate = d.both([eq(stack[-1], i, 0), eq(stack[-1], i, 1)])
            incoming.setdefault(stack, []).append(d.both([active, duplicate]))
            remaining = [active, duplicate.Not()]
            if len(stack) > 1:
                collinear = d.either(
                    [
                        d.both([eq(stack[-2], stack[-1], axis), eq(stack[-1], i, axis)])
                        for axis in (0, 1)
                    ]
                )
                incoming.setdefault((*stack[:-1], i), []).append(d.both([*remaining, collinear]))
                remaining.append(collinear.Not())
            incoming.setdefault((*stack, i), []).append(d.both(remaining))
        states = {}
        for stack, paths in incoming.items():
            flag = d.boolean("route_export_stack")
            d.add(flag == sum(paths))
            states[stack] = flag
    length = d.integer(0, 10 * span, "route_exported_length_mm")
    for stack, flag in states.items():
        terms = [dist(first, second) for first, second in zip(stack, stack[1:], strict=False)]
        d.add(length == sum(terms)).only_enforce_if(flag)
    return length


def _personnel_route(model: Any) -> Any:
    routes = [
        r
        for r in model.routes
        if (r["req"]["from_ref"], r["req"]["to_ref"]) == ("main_entrance", "changing_room")
    ]
    if len(routes) != 1 or routes[0]["req"]["flow_kind"] != "PEOPLE":
        raise LayoutAuthorityError("ROUTE_REFINEMENT_UNIQUE_PERSONNEL_REQUIRED")
    return routes[0]


def _measured_route(routes: list[Any]) -> Any:
    rows = [r for r in routes if r["from_ref"] == "main_entrance"]
    if len(rows) != 1 or rows[0]["to_ref"] != "changing_room":
        raise LayoutAuthorityError("ROUTE_REFINEMENT_EXPORTED_PERSONNEL_REQUIRED")
    return rows[0]


def _local_model(model: Any, solver: Any, context: Any, proxy_index: int) -> tuple[Any, Any]:
    """Copy no Reference ownership certificates; reuse completed total definitions."""
    original = model.m
    charge = context.ledger.charge
    # Copy visits all protobuf entities and their metadata; no discounted copy.
    charge(
        "ROUTE_LOCAL_MODEL_COPY",
        len(original.proto.variables)
        + len(original.proto.constraints)
        + (len(original.proto.solution_hint.vars) if original.proto.has_solution_hint() else 0)
        + sum(len(s.exprs) + 1 for s in original.proto.search_strategy),
    )
    local = cp_model.CpModel()
    local.proto.copy_from(original.proto)
    personnel = _personnel_route(model)
    free = {
        v.index
        for group in [
            *personnel["points"],
            personnel["from_faces"],
            personnel["to_faces"],
            *personnel["from_offsets"],
            *personnel["to_offsets"],
        ]
        for v in group
    }
    charge("ROUTE_LOCAL_FREE_REFERENCE", len(free) + 1)
    free.add(personnel["corridor"].index)
    # Meter the original helper's actual reference/selector reads as well as
    # the later fixing writes. No discounted all-variable scan is introduced.
    count = len(model.rooms) * 5
    for interface in model.interfaces:
        charge("ROUTE_LOCAL_SCOPE_SELECTOR", 1)
        count += 1 + int(solver.boolean_value(interface["active"]))
    for route in model.routes:
        charge("ROUTE_LOCAL_SCOPE_SELECTOR", 1)
        count += 1
        if solver.boolean_value(route["corridor"]):
            count += sum(len(p) for p in route["points"])
        else:
            for direct in route["direct"]:
                charge("ROUTE_LOCAL_SCOPE_SELECTOR", 1)
                count += 1 + int(solver.boolean_value(direct["active"]))
    charge("ROUTE_LOCAL_SCOPE_ENUMERATION", count)
    refs = physical_assignment_variables(model, solver)
    refs += [r[k] for r in model.rooms.values() for k in ("x", "y", "w", "d")]
    for v in {v.index: v for v in refs if not isinstance(v, int)}.values():
        charge("ROUTE_LOCAL_SCOPE_REFERENCE", 1)
        if v.index not in free:
            charge("ROUTE_LOCAL_CONSTRAINT", 1)
            local.add(local.get_int_var_from_proto_index(v.index) == solver.value(v))
    proxy = local.get_int_var_from_proto_index(proxy_index)
    if proxy.name != "r5_area_worst":
        raise LayoutAuthorityError("ROUTE_REFINEMENT_AREA_PROXY_REQUIRED")
    charge("ROUTE_LOCAL_CONSTRAINT", 1)
    local.add(proxy == solver.value(proxy))
    points = [[local.get_int_var_from_proto_index(v.index) for v in p] for p in personnel["points"]]
    length = exported_length_expression(local, points, charge)
    charge("ROUTE_LOCAL_OBJECTIVE", 1)
    local.minimize(length)
    return local, length


class _RouteRefinementNative(_ChangingFrontageCorridorNative):
    """Same first/global Solve path; only a private local model uses route objective."""

    continuation_policy = POLICY
    continuation_policy_hash = POLICY_HASH

    def _solve_with_feedback(self, context: Any, solver: Any, model: Any, phase: str) -> Any:
        if model is getattr(self, "_route_model", None):
            return solver.solve(model), {"kind": "BOUNDED_SAME_PROXY_ROUTE_SOLVE"}
        return super()._solve_with_feedback(context, solver, model, phase)

    def refine_routes(
        self, context: Any, model: Any, accepted_solver: Any, record: dict[str, Any]
    ) -> Generator[dict[str, Any], str | None, None]:
        if (
            not self.improving
            or model.m is not self._feedback_model
            or model.c is not context
            or context.ledger is not self.ledger
        ):
            raise LayoutAuthorityError("ROUTE_REFINEMENT_ACCEPTED_SECOND_STAGE_REQUIRED")
        self._route_composition_hash = model.handoff.source_composition_hash
        rooms = tuple(
            accepted_solver.value(r[k]) for r in model.rooms.values() for k in ("x", "y", "w", "d")
        )
        context.ledger.charge("ROUTE_LOCAL_GEOMETRY_KEY", len(rooms))
        visited: set[tuple[int, ...]] = getattr(self, "_route_visited", set())
        if rooms in visited:
            return
        remaining, elapsed = self.remaining_share(context)
        if min(remaining, elapsed, context.ledger.remaining_solver_seconds()) <= MIN_ROUTE_SECONDS:
            self._event(context, "NOT_STARTED_INSUFFICIENT_RESOURCES")
            return
        self._route_visited = visited | {rooms}
        self._route_composition_hash = model.handoff.source_composition_hash
        before = _measured_route(record["routes"])
        best = int(before["length_mm"])
        local, length = _local_model(model, accepted_solver, context, self._feedback_proxy_index)
        self._route_model = local
        seen = {canonical_hash(before)}
        try:
            for attempt in range(MAX_ROUTE_ATTEMPTS):
                remaining, elapsed = self.remaining_share(context)
                seconds = min(
                    MAX_ROUTE_SECONDS,
                    remaining / 4,
                    elapsed / 4,
                    context.ledger.remaining_solver_seconds(),
                )
                if seconds <= MIN_ROUTE_SECONDS:
                    self._event(context, "NOT_STARTED_INSUFFICIENT_RESOURCES")
                    return
                context.ledger.charge("ROUTE_LOCAL_CONSTRAINT", 1)
                local.add(length < best)
                solver, status = self._run(context, local, seconds, "ALL_ROOMS_ALL_ACCESS")
                self._event(context, solver.status_name(status), attempt=attempt + 1)
                if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
                    return  # Local UNKNOWN/INFEASIBLE is never a global proof/retry.
                context.ledger.checked_solutions += 1
                context.ledger.guard()
                zones, interface = model.export(solver)  # Original indices are stable in clone.
                routes = model.export_routes(solver, zones, interface)
                route = _measured_route(routes)
                context.ledger.charge("ROUTE_LOCAL_LENGTH_READBACK", len(route["path_mm"]))
                if solver.value(length) != route["length_mm"] or route["length_mm"] >= best:
                    raise LayoutAuthorityError("ROUTE_REFINEMENT_EXPORTED_LENGTH_MISMATCH")
                fingerprint = canonical_hash(route)
                if fingerprint in seen:
                    self._event(context, "DUPLICATE_PHYSICAL_ROUTE")
                    return
                seen.add(fingerprint)
                checked = validate_global_geometry(context, model.handoff, zones, routes)
                topology = inspect_rectangular_union(
                    [z.bounds_mm for z in zones.values()]
                    + [tuple(e) for r in routes for e in r["envelopes_mm"]],
                    charge=context.ledger.charge,
                )
                proposal = dict(
                    solver_status=solver.status_name(status),
                    zones=[zones[k].to_dict() for k in sorted(zones)],
                    routes=routes,
                    packaging_interface=interface,
                    independent_validation=checked,
                    model_witness_topology=topology,
                    model_zone_count=len(zones),
                    model_access_count=len(routes),
                    must_constraint_count=len(context.must),
                    global_infeasibility_claimed=False,
                    search_stage="SAME_PROXY_ROUTE_REFINEMENT",
                    route_refinement=dict(
                        policy_hash=POLICY_HASH,
                        attempt=attempt + 1,
                        max_attempts=MAX_ROUTE_ATTEMPTS,
                        same_physical_rooms=True,
                        area_proxy=accepted_solver.value(
                            model.m.get_int_var_from_proto_index(self._feedback_proxy_index)
                        ),
                        baseline_route=before,
                        native_route=route,
                        cp_length_mm=solver.value(length),
                        physical_route_hash=fingerprint,
                        hint_preserved=True,
                        scope="TEMPORARY_ACCEPTED_ROOMS_AND_OTHER_ACCESS_WITNESSES",
                    ),
                )
                if checked["pass"] and topology["valid"]:
                    feedback = yield proposal  # Original full application/Access/Site/_eligible.
                    if feedback == "ENGINEERING_ACCEPTED":
                        best = int(route["length_mm"])
                        if status == cp_model.OPTIMAL:
                            return
                else:
                    self._event(
                        context, "ORIGINAL_GEOMETRY_OR_TOPOLOGY_REJECTED", proposal=proposal
                    )
                # Rejected path cut is exact physical witness, never room-only.
                variables = [v for p in _personnel_route(model)["points"] for v in p]
                context.ledger.charge("ROUTE_LOCAL_WITNESS_CUT", len(variables) + 1)
                local.add_forbidden_assignments(
                    [local.get_int_var_from_proto_index(v.index) for v in variables],
                    [[solver.value(v) for v in variables]],
                )
        finally:
            self._route_model = None  # No scoped restriction can reach the global model.
            self._event(context, "LOCAL_SCOPE_DISCARDED")

    def _event(self, context: Any, status: str, **facts: Any) -> None:
        context.ledger.execution_authorization.record_enumeration(
            {
                "zone_plan_hash": context.binding.canonical_zone_plan_hash,
                "p1_hash": context.binding.p1_handoff_hash,
                "site_hash": context.binding.site_geometry_hash,
                "composition_hash": self._route_composition_hash,
            },
            dict(
                kind="SAME_PROXY_ROUTE_REFINEMENT", status=status, policy_hash=POLICY_HASH, **facts
            ),
        )


class StageBSameProxyRouteRefinementFairSolver(StageBChangingFrontageCorridorFairSolver):
    quality_policy_hash = POLICY_HASH
    native_type = _RouteRefinementNative

    def _continuation_options(self, context: Any) -> dict[str, Any]:
        return dict(
            super()._continuation_options(context),
            before_accepted_geometry_cut=lambda model, solver, record: cast(
                _RouteRefinementNative, self.native
            ).refine_routes(context, model, solver, record),
        )

    def observe_validated_candidate(
        self, context: Any, handoff: Any, candidate: dict[str, Any], feedback: str
    ) -> None:
        if "route_refinement" not in candidate.get("proposal", {}):
            return super().observe_validated_candidate(context, handoff, candidate, feedback)
        if feedback != "ENGINEERING_ACCEPTED":
            return
        snapshot = area_efficiency_snapshot(
            candidate, handoff.source_composition_hash, context.binding
        )
        if self.baseline is None:
            raise LayoutAuthorityError("ROUTE_REFINEMENT_BASELINE_REQUIRED")
        # Route witnesses are separately audited. They must not install a clone's
        # solver into the parent's proxy/hint frontier or replace the baseline.
        context.ledger.execution_authorization.record_enumeration(
            {
                "zone_plan_hash": context.binding.canonical_zone_plan_hash,
                "p1_hash": context.binding.p1_handoff_hash,
                "site_hash": context.binding.site_geometry_hash,
                "composition_hash": handoff.source_composition_hash,
            },
            dict(
                kind="SAME_PROXY_ROUTE_ENGINEERING_ACCEPTED",
                candidate=snapshot,
                nine=compare_balanced_quality(self.baseline, snapshot),
                twelve=compare_area_efficient_quality(self.baseline, snapshot),
                room_geometry_not_new=True,
                formal_quality_improvement_claimed=False,
            ),
        )
