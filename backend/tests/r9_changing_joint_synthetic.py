"""R9 independent eight-room synthetic geometry with movable Changing.

Four placement/face combinations, identical hard model in both search arms.
Uses original native portal/envelope predicates, never factory coordinates.
"""

from types import SimpleNamespace

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.access_authority import PERSONNEL
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import (
    bind_native_portal_positions,
    bind_native_shared_portal,
    disjoint,
    envelopes,
    touch,
)
from cold_storage.modules.layout.infrastructure.stage_b_model_references import ReferenceCpModel
from tests.unit.test_v222_stage_b_area_efficiency import requirements, setup

BOXES = {
    "sorting_packaging_room": (4000, 0, 10000, 4000),
    "packaging_material_storage": (10000, 0, 14000, 4000),
    "secondary_precooling_room": (0, 0, 4000, 4000),
    "coating_room": (0, 4000, 4000, 8000),
    "finished_goods_room": (0, 8000, 4000, 12000),
    "office": (4000, 9000, 8000, 13000),
    "shipping_channel": (8000, 9000, 10000, 13000),
    "changing_room": (4000, 4000, 8000, 6000),
}
# Exact native five-segment template points; duplicate/collinear points are legal.
PATHS = (
    [(16000, 6000), (15000, 6000), (15000, 7000), (6000, 7000), (6000, 7000), (6000, 6000)],
    [(16000, 6000), (15000, 6000), (15000, 6000), (15000, 5000), (9000, 5000), (8000, 5000)],
)


def build_scene(reference=False, before_seal=None):
    context, _, _ = setup(area="16")
    requirements(context, "16")
    auth = context.binding.dimension_authorities["changing_room"]
    auth["required_area_m2"] = "8"
    auth["area_requirement"]["reported_required_area_m2"] = "8"
    m = ReferenceCpModel(context.ledger.charge) if reference else cp_model.CpModel()
    context.ledger = context.ledger or StageALedger()
    model = SimpleNamespace(m=m, c=context, rooms={}, routes=[], interfaces=[], must_choices={})
    model.faces = {"packaging_material_storage": ("X", 1), "changing_room": ("Y", 1)}
    model.handoff = SimpleNamespace(
        process_axis=SimpleNamespace(value="Y"), process_direction=SimpleNamespace(value="POSITIVE")
    )
    context.sitebox = (0, 0, 16000, 14000)
    context.entrances = {"main_entrance": ((16000, 5000), (16000, 7000))}
    context.must = (
        ("secondary_precooling_room", "coating_room"),
        ("coating_room", "finished_goods_room"),
        ("office", "shipping_channel"),
    )
    position = m.new_bool_var("changing_east_position")
    for role, (x, y, X, Y) in BOXES.items():
        model.rooms[role] = {
            k: m.new_int_var(
                v, v + (2000 if role == "changing_room" and k in ("x", "X") else 0), role + "_" + k
            )
            for k, v in (("x", x), ("y", y), ("X", X), ("Y", Y))
        }
        for side, value in (("w", X - x), ("d", Y - y)):
            model.rooms[role][side] = m.new_int_var(value, value, role + "_physical_" + side)
    room = model.rooms["changing_room"]
    m.add(room["x"] == 4000 + 2000 * position)
    m.add(room["X"] == room["x"] + room["w"])
    m.add(room["Y"] == room["y"] + room["d"])
    model.position = position
    for i, (a, A) in enumerate(model.rooms.items()):
        for b, B in list(model.rooms.items())[i + 1 :]:
            disjoint(m, A, B, "scene_" + a + "_" + b)
    for a, b in context.must:
        model.must_choices[a, b] = tuple(touch(m, model.rooms[a], model.rooms[b], a + "_" + b))
    choice = m.new_bool_var("entrance_facing_choice")
    model.choice = choice
    # The test installs identical generic MIN fallback AFTER the optional R6 prefix.
    pairs = (
        ("main_entrance", "changing_room"),
        ("changing_room", "sorting_packaging_room"),
        ("secondary_precooling_room", "coating_room"),
        ("coating_room", "finished_goods_room"),
    )
    reqs = []
    for i, (a, b) in enumerate(pairs):
        req = dict(
            identity=f"synthetic:{a}->{b}",
            from_ref=a,
            to_ref=b,
            flow_kind="PEOPLE" if i < 2 else "MATERIAL",
            direct_allowed=i != 0,
            corridor_allowed=True,
            portal_required=True,
            profile_identity=PERSONNEL,
        )
        reqs.append(req)
        corridor = m.new_bool_var(f"route_{i}_corridor")
        m.add(corridor == (i == 0))
        route = dict(
            req=req,
            pw=1500,
            cw=2000,
            corridor=corridor,
            direct=[],
            points=[],
            from_faces=[],
            to_faces=[],
            from_offsets=[],
            to_offsets=[],
        )
        if i == 0:
            for j in range(6):
                point = []
                for axis in range(2):
                    v = m.new_int_var(0, 16000, f"staff_point_{j}_{axis}")
                    rows = []
                    for pos in (0, 1):
                        for c, path in enumerate(PATHS):
                            value = path[j][axis] + (
                                2000 * pos if axis == 0 and j >= (4 if c else 3) else 0
                            )
                            rows.append((pos, c, value))
                    m.add_allowed_assignments([position, choice, v], rows)
                    point.append(v)
                route["points"].append(point)
            for side in range(4):
                flag = m.new_bool_var(f"changing_face_{side}")
                m.add(flag == (choice if side == 1 else 1 - choice if side == 3 else 0))
                route["to_faces"].append(flag)
                vertical = side < 2
                pos = route["points"][-1][1 if vertical else 0]
                route["to_offsets"].append(
                    bind_native_portal_positions(
                        m,
                        pos,
                        4000 if vertical else room["x"],
                        6000 if vertical else room["X"],
                        1500,
                        flag,
                        16000,
                        f"changing_native_{side}",
                    )
                )
            # Same native envelopes for all four real route/position choices.
            for pos in (0, 1):
                for c, original in enumerate(PATHS):
                    path = [
                        (x + (2000 * pos if j >= (4 if c else 3) else 0), y)
                        for j, (x, y) in enumerate(original)
                    ]
                    active = m.new_bool_var(f"staff_choice_{pos}_{c}")
                    m.add_allowed_assignments(
                        [position, choice, active],
                        [(p, f, int((p, f) == (pos, c))) for p in (0, 1) for f in (0, 1)],
                    )
                    for j, (x, y, X, Y) in enumerate(envelopes(path, 2000)):
                        box = dict(zip(("x", "y", "X", "Y"), (x, y, X, Y), strict=True))
                        assert 0 <= x <= X <= 16000 and 0 <= y <= Y <= 14000
                        for role, other in model.rooms.items():
                            disjoint(m, box, other, f"staff_{pos}_{c}_{j}_{role}", when=active)
        else:
            A, B = model.rooms[a], model.rooms[b]
            for side in range(4):
                flag = m.new_bool_var(f"direct_{i}_{side}")
                m.add(flag == (side == (3 if i == 1 else 2)))
                center = m.new_int_var(0, 16000, f"portal_{i}_{side}")
                offsets = bind_native_shared_portal(
                    m,
                    center,
                    A,
                    B,
                    side < 2,
                    1500 if i == 1 else 2400,
                    flag,
                    16000,
                    f"direct_native_{i}_{side}",
                )
                route["direct"].append(
                    dict(active=flag, center=center, side=side, portal_choices=offsets)
                )
        model.routes.append(route)
    A, B = model.rooms["packaging_material_storage"], model.rooms["sorting_packaging_room"]
    for corridor in (False, True):
        for side in ("EAST", "WEST", "NORTH", "SOUTH"):
            active = m.new_bool_var(f"packaging_{corridor}_{side}")
            m.add(active == (not corridor and side == "EAST"))
            center = m.new_int_var(0, 16000, f"package_center_{corridor}_{side}")
            offsets = bind_native_shared_portal(
                m,
                center,
                A,
                B,
                side in ("EAST", "WEST"),
                2400,
                active,
                16000,
                f"pack_native_{corridor}_{side}",
            )
            model.interfaces.append(
                dict(
                    active=active,
                    corridor=corridor,
                    side=side,
                    center=center,
                    portal_choices=(offsets,),
                )
            )
    reqs.append(
        dict(
            identity="synthetic:packaging",
            from_ref="packaging_material_storage",
            to_ref="sorting_packaging_room",
            flow_kind="PACKAGING",
            direct_allowed=True,
            corridor_allowed=True,
            portal_required=True,
            profile_identity=PERSONNEL,
        )
    )
    context.binding.access_requirements = tuple(reqs)
    if before_seal is not None:
        before_seal(context, model)
    if reference:
        m.seal(model)
    return context, model


def solve_scene(joint, *, production=True):
    """One bounded synthetic Solve per arm; no real input or authorization."""
    from decimal import Decimal

    from cold_storage.modules.layout.application.global_composition_solver import (
        _route_geometry_errors,
    )
    from cold_storage.modules.layout.domain.access_routing import (
        _compact_path,
        route_access_requirement,
    )
    from cold_storage.modules.layout.domain.orthogonal_union import inspect_rectangular_union
    from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
    from cold_storage.modules.layout.infrastructure.stage_b_changing_frontage_corridor import (
        apply_changing_frontage_corridor_search,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
        apply_frontage_joint_search,
        apply_reference_area_guidance,
    )

    context, model = build_scene(reference=True)
    apply_reference_area_guidance(model, context)
    apply_frontage_joint_search(model, context)
    receipt = apply_changing_frontage_corridor_search(model, context) if joint else None
    model.m.add_decision_strategy(
        [model.position], cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE
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
    status = solver.solve(model.m)
    result = dict(
        status=solver.status_name(status),
        parameters=str(p),
        wall_seconds=solver.wall_time,
        branches=solver.num_branches,
        conflicts=solver.num_conflicts,
        joint=joint,
        receipt=receipt,
        work=context.ledger.model_work,
        resource_events=context.ledger.resource_events,
        scope="SYNTHETIC_ONLY_NOT_FACTORY_QUALITY_OR_APPLICATION_PASS",
    )
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return result
    boxes = {
        r: tuple(solver.value(room[k]) for k in ("x", "y", "X", "Y"))
        for r, room in model.rooms.items()
    }
    raw = [tuple(solver.value(v) for v in point) for point in model.routes[0]["points"]]
    path = list(_compact_path(raw))
    route = dict(
        topology="CORRIDOR_MEDIATED",
        path_mm=path,
        raw_template_points_mm=raw,
        portal_from_center_mm=path[0],
        portal_to_center_mm=path[-1],
        width_mm=2000,
        envelopes_mm=envelopes(path, 2000),
        length_mm=sum(
            abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:], strict=False)
        ),
        turn_count=len(path) - 2,
    )
    errors = _route_geometry_errors(route)
    topology = inspect_rectangular_union(list(boxes.values()) + route["envelopes_mm"])
    zones = {
        role: PlacedRectangleV1(role, *(Decimal(v) / 1000 for v in (x, y, X - x, Y - y)))
        for role, (x, y, X, Y) in boxes.items()
    }
    requirement = dict(
        model.routes[0]["req"], access_class="PERSONNEL", route_shape_constraint="NOT_FROZEN"
    )
    access, _ = route_access_requirement(
        requirement,
        relationships={},
        zones=zones,
        boundary=((0, 0), (16000, 0), (16000, 14000), (0, 14000)),
        obstacles=(),
        entrances=context.entrances,
        route_hint=path,
        route_node_budget=20000,
    )
    result.update(
        independent_access=access,
        area_shape={
            role: dict(
                physical_width_m=str(Decimal(X - x) / 1000),
                physical_depth_m=str(Decimal(Y - y) / 1000),
                actual_area_m2=str(Decimal((X - x) * (Y - y)) / 1_000_000),
                required_area_m2=context.binding.dimension_authorities[role]["required_area_m2"],
                aspect_ratio=str(Decimal(max(X - x, Y - y)) / min(X - x, Y - y)),
                formula="area=w_mm*d_mm/1e6; aspect=max(w_mm,d_mm)/min(w_mm,d_mm)",
                calculator_version="r9-synthetic-physical-facts@1.0.0",
                source_type="synthetic",
                requires_review=True,
            )
            for role, (x, y, X, Y) in boxes.items()
            if role in ("office", "changing_room", "coating_room")
        },
        boxes=boxes,
        path_mm=path,
        route=route,
        route_errors=errors,
        topology=topology,
        changing_face="EAST" if solver.value(model.choice) else "NORTH",
        objective=solver.objective_value,
        must_contacts={
            str(pair): any(solver.boolean_value(v) for v in choices)
            for pair, choices in model.must_choices.items()
        },
    )
    return result
