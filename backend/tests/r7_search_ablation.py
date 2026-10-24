"""Small, independent search experiments, never a frozen 20t solver input.

The original eight-room scene is deliberately retained as a negative control:
production presolve removes its branching. The packing variant adds six
synthetic office service blocks on a 0.5m grid. Staff frontage selects which
1m clearance strip is reserved (north or east). This is an explicit synthetic
assumption, NOT an actual equipment requirement or a new production Authority.
"""

from copy import deepcopy
from importlib.metadata import version

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import _route_geometry_errors
from cold_storage.modules.layout.domain.access_routing import _compact_path
from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
from cold_storage.modules.layout.infrastructure import stage_b_area_efficiency as r5
from cold_storage.modules.layout.infrastructure import stage_b_frontage_joint_search as r6
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import envelopes
from cold_storage.modules.layout.infrastructure.stage_b_first_feasible_recovery import (
    StageBFirstFeasibleRecoveryFairSolver,
)
from tests.r6_frontage_synthetic import BOXES, build_scene

SERVICE_BLOCKS = ((3, 3), (3, 3), (3, 3), (3, 3), (2, 3), (2, 3))


def add_service_bank(context, model):
    """Identical hard geometry in all arms; no historical coordinates."""
    m = model.m
    xs, ys, blocks = [], [], []
    for i, (w, d) in enumerate(SERVICE_BLOCKS):
        x = m.new_int_var(0, 8 - w, f"service_{i}_x")
        y = m.new_int_var(0, 8 - d, f"service_{i}_y")
        m.add(x + w <= 6).only_enforce_if(model.choice)
        m.add(y + d <= 6).only_enforce_if(model.choice.Not())
        xs.append(m.new_fixed_size_interval_var(x, w, f"service_x_{i}"))
        ys.append(m.new_fixed_size_interval_var(y, d, f"service_y_{i}"))
        blocks.append((x, y, w, d))
    m.add_no_overlap_2d(xs, ys)
    model.service_blocks = blocks


def prepare(arm, *, packing=True, drop_groups=(), delayed=False):
    context, model = build_scene(
        reference=arm != "A", before_seal=add_service_bank if packing else None
    )
    if arm == "C" and not delayed:
        r6.apply_frontage_joint_search(model, context)
        if drop_groups:
            # Controlled soft-metadata ablation only; preserve all other groups.
            remaining = [
                deepcopy(s)
                for i, s in enumerate(model.m.proto.search_strategy)
                if i not in drop_groups
            ]
            model.m.proto.search_strategy.clear()
            model.m.proto.search_strategy.extend(remaining)
    if delayed:
        port = StageBFirstFeasibleRecoveryFairSolver()
        port.start_handoff(context.ledger, 1)
        assert "final_model_search" not in port._continuation_options(context)
        port._final_guidance(model, context)
    else:
        guidance = (
            r5.apply_area_efficient_guidance if arm == "A" else r6.apply_reference_area_guidance
        )
        guidance(model, context)
    model.m.add_decision_strategy(
        [r["corridor"] for r in model.routes], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
    )
    return context, model


def validate_scene(model, solver):
    """Independent original route/union predicates, plus measured block geometry."""
    raw_path = [tuple(solver.value(v) for v in point) for point in model.routes[0]["points"]]
    path = list(_compact_path(raw_path))
    headings = [
        (int(b[0] > a[0]) - int(b[0] < a[0]), int(b[1] > a[1]) - int(b[1] < a[1]))
        for a, b in zip(path, path[1:], strict=False)
        if a != b
    ]
    length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:], strict=False))
    turns = sum(a != b for a, b in zip(headings, headings[1:], strict=False))
    strips = envelopes(path, 2000)
    route = dict(
        topology="CORRIDOR_MEDIATED",
        path_mm=path,
        raw_template_points_mm=raw_path,
        portal_from_center_mm=path[0],
        portal_to_center_mm=path[-1],
        width_mm=2000,
        envelopes_mm=strips,
        length_mm=length,
        turn_count=turns,
    )
    errors = _route_geometry_errors(route)
    topology = inspect_rectangular_union(list(BOXES.values()) + strips)
    blocks = [
        (solver.value(x), solver.value(y), w, d)
        for x, y, w, d in getattr(model, "service_blocks", [])
    ]
    clear = all(x + w <= 6 if solver.value(model.choice) else y + d <= 6 for x, y, w, d in blocks)
    disjoint = all(
        x + w <= X or x >= X + W or y + d <= Y or y >= Y + D
        for i, (x, y, w, d) in enumerate(blocks)
        for X, Y, W, D in blocks[i + 1 :]
    )
    return dict(
        path_mm=path,
        route_length_mm=length,
        route_turns=turns,
        route_errors=errors,
        topology=topology,
        service_blocks=blocks,
        service_geometry_valid=clear and disjoint,
        valid=not errors and topology["valid"] and clear and disjoint,
        scope="SYNTHETIC_NATIVE_ROUTE_AND_UNION_NOT_FACTORY_APPLICATION_PASS",
    )


def run(arm, *, packing=True, production=True, drop_groups=(), delayed=False):
    context, model = prepare(arm, packing=packing, drop_groups=drop_groups, delayed=delayed)
    if not production:
        model.m.add_decision_strategy(
            [model.choice], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
        )
    solver = cp_model.CpSolver()
    p = solver.parameters
    p.num_search_workers = 1
    p.random_seed = 3
    p.cp_model_presolve = production
    p.search_branching = cp_model.PARTIAL_FIXED_SEARCH if production else cp_model.FIXED_SEARCH
    p.stop_after_first_solution = True
    p.max_time_in_seconds = 2
    p.max_memory_in_mb = 512
    p.log_search_progress = True
    p.log_to_stdout = False
    logs = []
    solver.log_callback = logs.append

    class First(cp_model.CpSolverSolutionCallback):
        first = None

        def on_solution_callback(self):
            if self.first is None:
                self.first = dict(
                    seconds=self.wall_time,
                    branches=self.num_branches,
                    conflicts=self.num_conflicts,
                    objective=self.objective_value,
                )

    callback = First()
    status = solver.solve(model.m, callback)
    return dict(
        arm=arm,
        packing=packing,
        production=production,
        drop_groups=drop_groups,
        delayed=delayed,
        ortools_version=version("ortools"),
        parameters=str(p),
        status=solver.status_name(status),
        first=callback.first,
        wall_seconds=solver.wall_time,
        deterministic_seconds=solver.response_proto.deterministic_time,
        branches=solver.num_branches,
        conflicts=solver.num_conflicts,
        geometry=validate_scene(model, solver) if callback.first else None,
        response_stats=solver.response_stats(),
        presolve_log="".join(logs),
        work=context.ledger.model_work,
    )
