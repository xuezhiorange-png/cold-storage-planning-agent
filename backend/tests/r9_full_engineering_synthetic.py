"""Independent synthetic input. No historical input/geometry, production edits or Solve."""

from dataclasses import asdict
from decimal import Decimal as D

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.global_composition_solver import (
    GlobalGenerationContext,
    StageALedger,
    rectangular_scope,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.access_authority import resolve_access_profile
from cold_storage.modules.layout.domain.access_routing import (
    _segment_from_mapping,
    _shared_edge_segment,
)
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import envelopes
from tests.unit.test_v22_p1f_project_truck_input import truck_input
from tests.unit.test_v22_p2c_deterministic_placement import site_input

INPUT = dict(
    daily_inbound_mass_kg=1000,
    working_time_h_per_day=8,
    finished_storage_days=1,
    packaging_storage_days=1,
    precooling_required_ratio=1,
    frozen_storage_days=1,
    main_packaging_storage_days=1,
    auxiliary_packaging_storage_days=1,
)


def sources():
    plan = asdict(ColdRoomZonePlanner().plan(ColdRoomZonePlanInput(**INPUT)))
    assert plan["success"]
    truck = truck_input()
    truck["project_id"] = "synthetic-r9-full-fixture-1000kg-not-project-data"
    for value in truck.values():
        if isinstance(value, dict):
            value["project_id"] = truck["project_id"]
    p1 = build_p1_project_handoff(plan, truck)
    rawsite = site_input(width=200, depth=100)
    rawsite["main_entrance"] = {"start": {"x": 45, "y": 0}, "end": {"x": 55, "y": 0}}
    rawsite["no_build_zones"] = [
        {
            "type": "polygon",
            "points": [
                {"x": 150, "y": 80},
                {"x": 155, "y": 80},
                {"x": 155, "y": 85},
                {"x": 150, "y": 85},
            ],
        }
    ]
    site = validate_site_geometry(
        {"site_constraints": rawsite, "truck_access": truck}, plan, p1_handoff=p1
    )
    binding = bind_layout_authority(plan, p1, site)
    hs = build_structural_compositions(plan, p1, site).placement_handoffs
    h = next(h for h in hs if h.family.value == "LINEAR_BANDED" and h.process_axis.value == "X")
    body = site.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obs = validated_hard_obstacle_polygons(body)
    pack = next(r for r in binding.access_requirements if r["flow_kind"] == "PACKAGING")
    c = GlobalGenerationContext(
        binding,
        site,
        boundary,
        obs,
        rectangular_scope(boundary),
        tuple(rectangular_scope(o) for o in obs),
        {
            k: _segment_from_mapping(v, field=k)
            for k, v in body["entrances"].items()
            if k in ("main_entrance", "truck_entrance")
        },
        tuple(process_graph().must_adjacencies),
        pack,
        resolve_access_profile(pack["profile_identity"]),
        StageALedger(),
    )
    assert set(binding.dimension_authorities) == set(ZONE_CODES)
    assert len(c.must) == 7 and len(binding.access_requirements) == 12
    return plan, p1, site, h, c, rawsite, truck


# Independently designed synthetic floor plan, not copied from any historical layout.
# A process spine with three north-side banks and a south-side personnel room.
# Fixed-role dimensions below are generated from the current P1, not overridden.
def _initial_geometry(c, changing_x):
    defs = {
        "sorting_packaging_room": ("40", "30", None, None),
        "primary_precooling_room": ("35.1", "24", None, None),
        "raw_fruit_buffer": ("28.3", "24", None, None),
        "secondary_precooling_room": ("54.96", "30", None, None),
        "coating_room": ("59.86", "30", "8", "10"),
        "finished_goods_room": ("67.86", "30", None, None),
        "shipping_channel": ("72.66", "30", None, None),
        "office": ("72.66", "20", "6", "10"),
        "changing_room": (str(changing_x), "20", "4", "10"),
        "packaging_material_storage": ("36", "34.05", None, None),
        "secondary_fruit_buffer": ("44", "37.6", None, None),
        "frozen_fruit_room": ("46.4", "37.6", None, None),
    }
    rows = {}
    for role, (x, y, w, d) in defs.items():
        a = c.binding.dimension_authorities[role]
        if w is None:
            w = a["geometry"]["width_m"]
            d = a["geometry"]["depth_m"]
        rows[role] = PlacedRectangleV1(role, D(x), D(y), D(w), D(d), 0)
    return rows


def geometry(c, changing_x):
    rows = _initial_geometry(c, changing_x)
    # Original 14.96 x 7.6 nominal Sorting dimensions, legally rotated 90deg.
    a = c.binding.dimension_authorities["sorting_packaging_room"]
    assert a["rotation_allowed"] == [0, 90]
    s = rows["sorting_packaging_room"]
    rows["sorting_packaging_room"] = PlacedRectangleV1(
        s.zone_code, s.x, s.y, s.width_m, s.depth_m, 90
    )
    # Consequent offsets only: keep original process spine, banks and personnel bay.
    coordinates = {
        "secondary_precooling_room": ("47.6", "30"),
        "coating_room": ("52.5", "30"),
        "finished_goods_room": ("60.5", "30"),
        "shipping_channel": ("65.3", "30"),
        "office": ("65.3", "20"),
        "packaging_material_storage": ("40", "44.96"),
        "secondary_fruit_buffer": ("37.6", "40.05"),
        "frozen_fruit_room": ("47.6", "40.05"),
    }
    for role, (x, y) in coordinates.items():
        z = rows[role]
        rows[role] = PlacedRectangleV1(role, D(x), D(y), z.width_m, z.depth_m, z.rotation_deg)
    return rows


def routes(c, z):
    out = []
    for req in c.binding.access_requirements:
        if req["flow_kind"] == "TRUCK":
            continue
        profile = resolve_access_profile(req["profile_identity"])
        pw = int(profile.portal_clear_width_m * 1000)
        cw = int(profile.corridor_clear_width_m * 1000)
        if req["from_ref"] == "main_entrance":
            x, y, X, Y = z["changing_room"].bounds_mm
            path = [(50000, 0), (50000, 10000), ((x + X) // 2, 10000), ((x + X) // 2, y)]
            pa, pb = path[0], path[-1]
            mode = "CORRIDOR_MEDIATED"
            E = envelopes(path, cw)
        else:
            shared = _shared_edge_segment(z[req["from_ref"]], z[req["to_ref"]])
            assert shared, (req["from_ref"], req["to_ref"])
            a, b = shared
            pa = pb = tuple((a[i] + b[i]) // 2 for i in (0, 1))
            mode = "DIRECT_SHARED_EDGE"
            path = []
            E = []
        out.append(
            dict(
                requirement_identity=req["identity"],
                from_ref=req["from_ref"],
                to_ref=req["to_ref"],
                topology=mode,
                portal_from_center_mm=pa,
                portal_to_center_mm=pb,
                portal_width_mm=pw,
                width_mm=cw,
                path_mm=path,
                envelopes_mm=E,
                turn_count=max(0, len(path) - 2),
                length_mm=sum(
                    abs(a[0] - b[0]) + abs(a[1] - b[1])
                    for a, b in zip(path, path[1:], strict=False)
                ),
            )
        )
    return out
