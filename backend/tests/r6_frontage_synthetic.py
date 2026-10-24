"""Eight-room synthetic planning scene, never frozen 20t or project evidence.

Both actual portal/route alternatives satisfy the same deterministic geometry.
Only the R6 decision prefix differs; the area objective remains identical.
"""

from types import SimpleNamespace

from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
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
    model.faces = {"packaging_material_storage": ("X", 1), "changing_room": ("X", -1)}
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
    for role, (x, y, X, Y) in BOXES.items():
        model.rooms[role] = {
            k: m.new_int_var(v, v, role + "_" + k)
            for k, v in (("x", x), ("y", y), ("X", X), ("Y", Y))
        }
        for side, value in (("w", X - x), ("d", Y - y)):
            model.rooms[role][side] = m.new_int_var(value, value, role + "_physical_" + side)
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
        )
        reqs.append(req)
        corridor = m.new_bool_var(f"route_{i}_corridor")
        m.add(corridor == (i == 0))
        route = dict(
            req=req,
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
                    m.add_allowed_assignments(
                        [choice, v], [(c, path[j][axis]) for c, path in enumerate(PATHS)]
                    )
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
                        4000,
                        6000 if vertical else 8000,
                        1500,
                        flag,
                        16000,
                        f"changing_native_{side}",
                    )
                )
            # Native corridor envelopes must remain inside site and outside every room.
            for c, path in enumerate(PATHS):
                active = route["to_faces"][1 if c else 3]
                for j, (x, y, X, Y) in enumerate(envelopes(path, 2000)):
                    box = {k: v for k, v in zip(("x", "y", "X", "Y"), (x, y, X, Y), strict=True)}
                    assert 0 <= x <= X <= 16000 and 0 <= y <= Y <= 14000
                    for role, room in model.rooms.items():
                        disjoint(m, box, room, f"staff_{c}_{j}_{role}", when=active)
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
        )
    )
    context.binding.access_requirements = tuple(reqs)
    if before_seal is not None:
        before_seal(context, model)
    if reference:
        m.seal(model)
    return context, model
