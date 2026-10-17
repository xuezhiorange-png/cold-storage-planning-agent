"""Bounded implementation of the application-owned global solver port.

Warmups produce hints from this invocation only. The final model contains all
12 rooms and all 11 non-Truck requirements; warmups are never accepted layouts.
The native footprint predicate rejects holes before a candidate is exported.
"""

from __future__ import annotations

import time
from decimal import Decimal
from importlib.metadata import version
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import (
    GlobalGenerationContext,
    validate_global_geometry,
)
from cold_storage.modules.layout.application.site_geometry import (
    validate_building_footprint_against_site,
)
from cold_storage.modules.layout.domain.access_routing import derive_building_footprint
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, polygon_to_dict
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel, GlobalModel


def _room_hint(model: Any, zones: dict[str, PlacedRectangleV1]) -> None:
    model.m.clear_hints()
    for key, room in model.rooms.items():
        row = zones[key]
        for name, value in (
            ("x", row.x * 1000),
            ("y", row.y * 1000),
            ("rot", row.rotation_deg // 90),
            ("nw", row.width_m * 1000),
            ("nd", row.depth_m * 1000),
        ):
            if not isinstance(room[name], int):
                model.m.add_hint(room[name], int(value))


def physical_assignment_variables(model: Any, solver: Any) -> list[Any]:
    """Only physical variables: do not exclude a room layout on UNKNOWN."""
    variables: list[Any] = []
    for room in model.rooms.values():
        variables.extend(
            room[k] for k in ("x", "y", "nw", "nd", "rot") if not isinstance(room[k], int)
        )
    for interface in model.interfaces:
        variables.append(interface["active"])
        if solver.boolean_value(interface["active"]):
            variables.append(interface["center"])
    for route in model.routes:
        variables.append(route["corridor"])
        if solver.boolean_value(route["corridor"]):
            variables.extend(v for point in route["points"] for v in point)
        else:
            for direct in route["direct"]:
                variables.append(direct["active"])
                if solver.boolean_value(direct["active"]):
                    variables.append(direct["center"])
    return list({v.index: v for v in variables}.values())


class OrToolsGlobalCompositionSolver:
    """Stage-A single deterministic configuration, not an automatic recovery loop."""

    def _run(
        self, context: GlobalGenerationContext, model: cp_model.CpModel, seconds: float, phase: str
    ) -> tuple[cp_model.CpSolver, Any]:
        ledger = context.ledger
        ledger.guard()
        remaining = ledger.remaining_solver_seconds()
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 3 if phase == "ALL_ROOMS_ALL_ACCESS" else 0
        if phase == "ALL_ROOMS_ALL_ACCESS":
            solver.parameters.search_branching = cp_model.PARTIAL_FIXED_SEARCH
        allowance = min(seconds, remaining, 140 - (time.monotonic() - ledger.started))
        if allowance <= 0:
            raise LayoutAuthorityError("CP_SAT_CUMULATIVE_ALLOWANCE_EXHAUSTED")
        solver.parameters.max_time_in_seconds = allowance
        solver.parameters.max_memory_in_mb = 512
        solver.parameters.stop_after_first_solution = True
        error = model.validate()
        if error:
            raise LayoutAuthorityError("GLOBAL_CP_SAT_MODEL_INVALID", reason=error)
        ledger.native_solver_active = True
        ledger.checkpoint("CP_SAT_STARTED")
        started = time.monotonic()
        try:
            status = solver.solve(model)
        except BaseException:
            ledger.solver_history_verified = False
            ledger.checkpoint("CP_SAT_INTERRUPTED_NATIVE_COUNTERS_INCOMPLETE")
            raise
        ledger.native_solver_active = False
        elapsed = time.monotonic() - started
        ledger.solver_wall += solver.wall_time
        ledger.solver_monotonic_wall += max(elapsed, solver.wall_time)
        ledger.attempts.append(
            {
                "phase": phase,
                "solver_status": solver.status_name(status),
                "wall_time": solver.wall_time,
                "monotonic_wall_time": elapsed,
                "deterministic_time": solver.response_proto.deterministic_time,
                "native_call_count": len(ledger.attempts) + 1,
                "branches": solver.num_branches,
                "conflicts": solver.num_conflicts,
                "response_stats": solver.response_stats(),
                "variables": len(model.proto.variables),
                "constraints": len(model.proto.constraints),
                "warmup_only": phase != "ALL_ROOMS_ALL_ACCESS",
                "ortools_version": version("ortools"),
            }
        )
        ledger.checkpoint("CP_SAT_RETURNED")
        ledger.guard()
        return solver, status

    def solve(
        self, context: GlobalGenerationContext, handoff: StructuralCompositionPlacementHandoffV1
    ) -> dict[str, Any]:
        try:
            context.ledger.remaining_solver_seconds()
        except LayoutAuthorityError as error:
            return {
                "solver_status": "NOT_STARTED",
                "codes": [error.code],
                "global_infeasibility_claimed": False,
                "candidate_generated": False,
            }
        global_model = GlobalModel(context, handoff)
        hints: dict[str, PlacedRectangleV1] | None = None
        for phase, cut, seconds in (
            ("ALL_ROOM_GEOMETRY_HINT", global_model.geometry_constraint_count, 4),
            ("ALL_ROOM_MUST_HINT", global_model.must_constraint_count, 6),
            ("COMPOSITION_PACKAGING_HINT", None, 10),
        ):
            partial: Any = global_model.m.clone()
            if cut is not None:
                # Keep interval indices stable; 9.15 uses pybind repeated fields.
                empty = cp_model.CpModel().proto.constraints.add()
                for index in range(cut, len(partial.proto.constraints)):
                    partial.proto.constraints[index].copy_from(empty)
            if hints:
                _room_hint(global_model, hints)
                partial.clear_hints()
                for hint_var, value in zip(
                    global_model.m.proto.solution_hint.vars,
                    global_model.m.proto.solution_hint.values,
                    strict=True,
                ):
                    partial.add_hint(partial.get_int_var_from_proto_index(hint_var), value)
            solver, status = self._run(context, partial, seconds, phase)
            if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
                hints = {
                    k: PlacedRectangleV1(
                        k,
                        Decimal(solver.value(r["x"])) / 1000,
                        Decimal(solver.value(r["y"])) / 1000,
                        Decimal(r["nw"] if isinstance(r["nw"], int) else solver.value(r["nw"]))
                        / 1000,
                        Decimal(r["nd"] if isinstance(r["nd"], int) else solver.value(r["nd"]))
                        / 1000,
                        solver.value(r["rot"]) * 90,
                    )
                    for k, r in global_model.rooms.items()
                }
        access_hint_model = AccessModel(context, handoff, True)
        if hints:
            _room_hint(access_hint_model, hints)
        hint_solver, hint_status = self._run(
            context, access_hint_model.m, 8, "ALL_ACCESS_FRESH_HINT_ONLY"
        )
        if hint_status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            hints, _ = access_hint_model.export(hint_solver)
        model = AccessModel(context, handoff, True)
        if hints:
            _room_hint(model, hints)
        # Unused corridor variables have no physical meaning when direct is selected.
        for route in model.routes:
            for point in route["points"]:
                for var in point:
                    model.m.add(var == 0).only_enforce_if(route["corridor"].Not())
        model.m.add_decision_strategy(
            [r["corridor"] for r in model.routes], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
        )
        cuts: list[dict[str, Any]] = []
        for refinement in range(max(0, 20 - context.ledger.checked_solutions)):
            solver, status = self._run(
                context, model.m, context.ledger.remaining_solver_seconds(), "ALL_ROOMS_ALL_ACCESS"
            )
            record: dict[str, Any] = {
                "solver_status": solver.status_name(status),
                "model_zone_count": len(model.rooms),
                "model_access_count": len(model.routes) + 1,
                "must_constraint_count": len(context.must),
                "model_scope": (
                    "RECTANGULAR_SITE_AND_OBSTACLES_INTEGER_MM_FIVE_SEGMENT_SEPARATE_CORRIDORS"
                ),
                "global_infeasibility_claimed": False,
                "topology_refinement_cuts": list(cuts),
                "topology_checked_solution_index": refinement,
            }
            if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
                return record
            context.ledger.checked_solutions += 1
            zones, interface = model.export(solver)
            routes = model.export_routes(solver, zones, interface)
            checked = validate_global_geometry(context, handoff, zones, routes)
            record.update(
                zones=[zones[k].to_dict() for k in sorted(zones)],
                routes=routes,
                packaging_interface=interface,
                independent_validation=checked,
            )
            exact_boxes = [tuple(z.bounds_mm) for z in zones.values()] + [
                tuple(box) for row in routes for box in row["envelopes_mm"]
            ]
            topology = inspect_rectangular_union(exact_boxes, charge=context.ledger.charge)
            record["model_witness_topology"] = topology
            if not checked["pass"]:
                record["model_validation_mismatch"] = True
                return record
            if not topology["valid"]:
                variables = physical_assignment_variables(model, solver)
                model.m.add_forbidden_assignments(variables, [[solver.value(v) for v in variables]])
                cuts.append(
                    {
                        "scope": "EXACT_ROOM_AND_SELECTED_WITNESS_ASSIGNMENT_ONLY",
                        "room_only_pruning": False,
                        "certificate": topology,
                    }
                )
                context.ledger.checkpoint("EXACT_INVALID_WITNESS_CUT")
                continue
            if checked["pass"]:
                try:
                    envelopes = [
                        ((x, y), (right, y), (right, top), (x, top))
                        for row in routes
                        for x, y, right, top in row["envelopes_mm"]
                    ]
                    footprint = derive_building_footprint(zones, envelopes)
                    payload = polygon_to_dict(footprint)
                    validate_building_footprint_against_site(payload, context.site)
                    record["model_witness_footprint"] = {
                        "derived": True,
                        "site_pass": True,
                        "polygon": payload,
                    }
                except LayoutAuthorityError as error:
                    record["model_witness_footprint"] = {
                        "derived": False,
                        "code": error.code,
                        "details": error.details,
                    }
            return record

        return {
            "solver_status": "BOUNDED_TOPOLOGY_REFINEMENT_LIMIT",
            "topology_refinement_cuts": cuts,
            "candidate_generated": False,
            "global_infeasibility_claimed": False,
        }
