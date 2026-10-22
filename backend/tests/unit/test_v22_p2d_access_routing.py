"""P2D route, truck-chain and final-layout validation tests."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain.access_routing import (
    _route_is_safe,
    evaluate_personnel_truck_interaction,
    route_access_requirement,
)
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.objective_profile import approved_objective_profile
from cold_storage.modules.layout.domain.placement import SitePlacementResultV1, _long_edges
from cold_storage.modules.layout.domain.site_geometry import (
    PlacedRectangleV1,
    normalize_polygon,
)
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_FACE_REFERENCE,
    DOCK_REVERSE,
    FORWARD_AXIS,
    ORIGIN_REFERENCE,
    REFERENCE_FRAME,
    STRAIGHT_APPROACH,
    TURN_90,
    validate_truck_maneuver_project_binding,
)
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.unit.test_v22_p1f_project_truck_input import truck_input
from tests.unit.test_v22_p2b1_truck_maneuver_templates import (
    p1f_input,
    project_payload,
    template_payload,
)


def _point(x: object, y: object) -> dict[str, object]:
    return {"x": x, "y": y}


def rebuilt_access_context() -> tuple[Any, ...]:
    """Replay genuine server-owned sources; mapping is explicitly experimental."""
    fixtures = Path(__file__).parents[1] / "fixtures" / "v22"
    candidate = json.loads((fixtures / "rebuilt_access_baseline_r11.json").read_text())
    raw = (fixtures / "xinzhao_20t_site_layout_input_v3.json").read_bytes()
    assert sha256(raw).hexdigest() == candidate["fixture_sha256"]
    # The persisted hash is standard compact JSON, distinct from source identity.
    assert (
        "sha256:"
        + sha256(
            json.dumps(candidate["zones"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == candidate["geometry_hash"]
    )
    source = json.loads(raw)
    plan = asdict(
        ColdRoomZonePlanner().plan(
            ColdRoomZonePlanInput(
                daily_inbound_mass_kg=source["daily_inbound_mass_kg"],
                working_time_h_per_day=16,
                finished_storage_days=source["finished_storage_days"],
                packaging_storage_days=3,
                precooling_required_ratio=1,
                frozen_storage_days=source["frozen_storage_days"],
                main_packaging_storage_days=source["main_packaging_storage_days"],
                auxiliary_packaging_storage_days=source["auxiliary_packaging_storage_days"],
            )
        )
    )
    handoff = build_p1_project_handoff(plan, source["truck_access"])
    site = validate_site_geometry(
        {"site_constraints": source["site_constraints"], "truck_access": source["truck_access"]},
        plan,
        p1_handoff=handoff,
    )
    binding = bind_layout_authority(plan, handoff, site)
    body = site.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = validated_hard_obstacle_polygons(body)
    zones = {
        z["zone_code"]: PlacedRectangleV1(
            z["zone_code"],
            Decimal(z["x"]),
            Decimal(z["y"]),
            Decimal(z["width_m"]),
            Decimal(z["depth_m"]),
            z["rotation_deg"],
        )
        for z in candidate["zones"]
    }
    relationships = {r["identity"]: r for r in binding.spatial_relationships}
    entrances = {
        k: routing._segment_from_mapping(v, field=k)
        for k, v in body["entrances"].items()
        if k in {"main_entrance", "truck_entrance"}
    }
    side, segment = _long_edges(zones["shipping_channel"])[0]
    placement = dict(
        placement_result_identity="site_constrained_factory_layout@1.0.0",
        schema_version="1.0.0",
        source_zone_plan_hash=binding.canonical_zone_plan_hash,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=site.canonical_result_hash,
        source_objective_profile_hash=approved_objective_profile().canonical_result_hash,
        placement_hard_constraints_passed=True,
        zones=candidate["zones"],
        shipping_loading_face_side=side,
        shipping_loading_face_segment=routing._segment(segment),
        EXPERIMENTAL_CANDIDATE_ADAPTER=True,
        SERVER_REPLAY_ACCEPTED=False,
    )
    placement["canonical_result_hash"] = canonical_hash(placement)
    return (
        plan,
        handoff,
        site,
        placement,
        binding,
        zones,
        boundary,
        obstacles,
        relationships,
        entrances,
    )


def test_rebuilt_production_domain_and_application_access() -> None:
    (
        plan,
        handoff,
        site,
        placement,
        binding,
        zones,
        boundary,
        obstacles,
        relationships,
        entrances,
    ) = rebuilt_access_context()
    requirements = [r for r in binding.access_requirements if r["flow_kind"] != "TRUCK"]
    assert len(zones) == 12 and len(requirements) == 11
    assert all(
        routing._shared_edge_segment(zones[a], zones[b]) is not None
        for a, b in process_graph().must_adjacencies
    )
    results = []
    for requirement in requirements:
        work = 0

        def meter(frame: Any, event: str, arg: Any) -> None:
            nonlocal work
            if (
                event == "call"
                and "/layout/domain/" in frame.f_code.co_filename
                and frame.f_code.co_name
                in {
                    "_cross",
                    "_fraction_cross",
                    "_on_segment",
                    "_segments_intersect_closed",
                    "_segment_intersection_parameters",
                    "point_in_polygon",
                    "_point_on_fraction_segment",
                    "rectangles_overlap",
                    "rectangles_share_positive_edge",
                    "_portal_candidates",
                    "_apply_template",
                }
            ):
                work += 1
                assert work <= 20000, "Original per-requirement experimental Host protection"

        try:
            sys.setprofile(meter)
            result, _ = route_access_requirement(
                requirement,
                relationships=relationships,
                zones=zones,
                boundary=boundary,
                obstacles=obstacles,
                entrances=entrances,
                route_node_budget=20000,
            )
        finally:
            sys.setprofile(None)
        assert result["status"] == "PASS", result
        results.append(result)
    packaging = next(r for r in results if r["from_ref"] == "packaging_material_storage")
    assert packaging["portal_from"]["edge_class"] == "LONG_EDGE"
    assert packaging["portal_to"]["edge_class"] == "SHORT_EDGE"
    application = route_site_placement(
        plan, handoff, site, placement, None, route_node_budget=20000, truck_node_budget=20000
    ).to_dict()
    non_truck = [r for r in application["access_results"] if r["flow_kind"] != "TRUCK"]
    assert len(non_truck) == 11 and all(r["status"] == "PASS" for r in non_truck)
    assert {r["requirement_identity"]: r for r in non_truck} == {
        r["requirement_identity"]: r for r in json.loads(json.dumps(results, default=str))
    }


@pytest.mark.parametrize(
    "a,b,overlap,closed",
    [
        ((0, 0, 10, 10), (0, 0, 10, 10), True, True),
        ((0, 0, 10, 10), (5, 0, 15, 10), True, True),
        ((0, 0, 10, 10), (0, 2, 10, 8), True, True),
        ((0, 4, 10, 6), (4, 0, 6, 10), True, True),
        ((0, 0, 10, 10), (10, 0, 20, 10), False, True),
        ((0, 0, 10, 10), (10, 10, 20, 20), False, True),
        ((0, 0, 10, 10), (11, 0, 20, 10), False, False),
    ],
)
def test_exact_rectangle_contact_semantics(a: Any, b: Any, overlap: bool, closed: bool) -> None:
    def polygon(box: Any) -> Any:
        x, y, X, Y = box
        return ((x, y), (X, y), (X, Y), (x, Y))

    assert routing._polygon_interiors_overlap(polygon(a), polygon(b)) is overlap
    assert routing._polygon_intersects_closed(polygon(a), polygon(b)) is closed


def test_concave_and_nonorthogonal_exact_predicates_fail_closed() -> None:
    notch = ((0, 0), (10, 0), (10, 3), (3, 3), (3, 7), (10, 7), (10, 10), (0, 10))
    assert not routing._segment_open_interval_overlaps_polygon_interior(((4, 5), (8, 5)), notch)
    assert routing._segment_open_interval_overlaps_polygon_interior(((1, 5), (8, 5)), notch)
    assert not routing._segment_open_interval_overlaps_polygon_interior(((3, 3), (3, 7)), notch)
    triangle = ((0, 0), (10, 0), (5, 10))
    assert routing._polygon_interiors_overlap(triangle, triangle)
    assert routing._polygon_interiors_overlap(triangle, ((3, 2), (7, 2), (5, 6)))
    assert not routing._polygon_interiors_overlap(triangle, ((10, 0), (20, 0), (15, 10)))
    assert not routing._polygon_interiors_overlap(notch, ((4, 4), (8, 4), (8, 6), (4, 6)))
    for invalid in (((0, 0), (1, 1), (2, 2)), ((0, 0), (10, 10), (0, 10), (10, 0))):
        with pytest.raises(LayoutAuthorityError):
            routing._polygon_interiors_overlap(invalid, triangle)
    with pytest.raises(LayoutAuthorityError, match="INVALID_RECTILINEAR_ROUTE"):
        routing._segment_open_interval_overlaps_polygon_interior(((0, 0), (1, 1)), triangle)


def test_route_cache_is_input_bound_and_optional() -> None:
    boundary = ((0, 0), (20000, 0), (20000, 20000), (0, 20000))
    kw = dict(width_mm=2000, boundary=boundary, obstacles=(), zones={}, incident_refs=frozenset())
    cache: dict[Any, Any] = {}
    path = ((5000, 5000), (15000, 5000))
    assert routing._cached_route_is_safe(
        path, **kw, cache=cache, capacity=20000
    ) == routing._cached_route_is_safe(path, **kw, cache=None, capacity=20000)
    assert routing._cached_route_is_safe(path, **kw, cache=cache, capacity=20000)[0]
    changed = dict(kw, obstacles=(((9000, 4000), (11000, 4000), (11000, 6000), (9000, 6000)),))
    assert not routing._cached_route_is_safe(path, **changed, cache=cache, capacity=20000)[0]
    changed = dict(kw, width_mm=12000)
    assert not routing._cached_route_is_safe(path, **changed, cache=cache, capacity=20000)[0]
    changed = dict(kw, boundary=((0, 0), (10000, 0), (10000, 20000), (0, 20000)))
    assert not routing._cached_route_is_safe(path, **changed, cache=cache, capacity=20000)[0]
    zone = PlacedRectangleV1("incident", Decimal(8), Decimal(4), Decimal(4), Decimal(2), 0)
    changed = dict(kw, zones={"incident": zone}, incident_refs=frozenset({"incident"}))
    assert not routing._cached_route_is_safe(path, **changed, cache=cache, capacity=20000)[0]


@pytest.mark.parametrize(
    "width,depth,expected", [(4, 6, "LONG_EDGE"), (8, 6, "SHORT_EDGE"), (6, 6, "SHORT_EDGE")]
)
def test_shared_edge_square_tie_rule_is_not_relabelled(
    width: int, depth: int, expected: str
) -> None:
    a = PlacedRectangleV1("a", Decimal(0), Decimal(0), Decimal(width), Decimal(depth), 0)
    b = PlacedRectangleV1("b", Decimal(width), Decimal(0), Decimal(width), Decimal(depth), 0)
    shared = routing._shared_edge_segment(a, b)
    assert shared is not None
    assert routing._edge_match_for_shared(a, b, shared) == (expected, expected)


def test_necessary_final_strip_is_contained_in_every_legal_last_turn() -> None:
    # Independent exact coordinate-cell containment, all four face normals,
    # two even widths, including turns nearer than the full strip length.
    for width in (2, 4):
        for nx, ny in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for distance in range(width // 2, 9):
                end = (20, 20)
                turn = (20 + nx * distance, 20 + ny * distance)
                start = (turn[0] - ny * 8, turn[1] + nx * 8)
                actual = [x.bounds_mm for x in routing._path_envelopes((start, turn, end), width)]
                probe = routing._path_envelopes(((20 + nx * width, 20 + ny * width), end), width)[
                    0
                ].bounds_mm
                xs = sorted({probe[0], probe[2]} | {x for b in actual for x in (b[0], b[2])})
                ys = sorted({probe[1], probe[3]} | {y for b in actual for y in (b[1], b[3])})
                for x, X in zip(xs, xs[1:], strict=False):
                    for y, Y in zip(ys, ys[1:], strict=False):
                        if probe[0] <= x < X <= probe[2] and probe[1] <= y < Y <= probe[3]:
                            assert any(
                                b[0] <= x < X <= b[2] and b[1] <= y < Y <= b[3] for b in actual
                            )


def test_actual_entry_cache_on_off_determinism(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, _, _, binding, zones, boundary, obstacles, relationships, entrances = (
        rebuilt_access_context()
    )
    req = next(q for q in binding.access_requirements if q["from_ref"] == "main_entrance")
    kw = dict(
        relationships=relationships,
        zones=zones,
        boundary=boundary,
        obstacles=obstacles,
        entrances=entrances,
        route_node_budget=20000,
    )
    cached = route_access_requirement(req, **kw)
    original = routing._cached_route_is_safe

    def uncached(path: Any, **kwargs: Any) -> Any:
        return original(path, **{**kwargs, "cache": None})

    monkeypatch.setattr(routing, "_cached_route_is_safe", uncached)
    assert route_access_requirement(req, **kw) == cached
    assert route_access_requirement(req, **kw) == cached


@pytest.mark.parametrize("from_rotation,to_rotation", [(0, 0), (0, 90), (90, 0), (90, 90)])
def test_direct_portals_derive_each_rotated_physical_edge(
    from_rotation: int, to_rotation: int
) -> None:
    _, _, _, _, binding, _, _, _, relationships, _ = rebuilt_access_context()
    req = next(
        q for q in binding.access_requirements if q["from_ref"] == "packaging_material_storage"
    )
    a = PlacedRectangleV1(
        req["from_ref"],
        Decimal(0),
        Decimal(0),
        Decimal(4 if from_rotation == 0 else 6),
        Decimal(6 if from_rotation == 0 else 4),
        from_rotation,
    )
    b = PlacedRectangleV1(
        req["to_ref"],
        Decimal(4),
        Decimal(0),
        Decimal(8 if to_rotation == 0 else 6),
        Decimal(6 if to_rotation == 0 else 8),
        to_rotation,
    )
    raw, _ = route_access_requirement(
        req,
        relationships=relationships,
        zones={a.zone_code: a, b.zone_code: b},
        boundary=((-10000, -10000), (30000, -10000), (30000, 30000), (-10000, 30000)),
        obstacles=(),
        entrances={},
    )
    assert raw["status"] == "PASS" and raw["topology"] == "DIRECT_SHARED_EDGE"
    assert raw["portal_from"]["edge_class"] == "LONG_EDGE"
    assert raw["portal_to"]["edge_class"] == "SHORT_EDGE"
    assert raw["portal_from"]["segment"] == raw["portal_to"]["segment"]


def _reference_frame(
    exit_pose: dict[str, object], entry_pose: dict[str, object] | None = None
) -> dict[str, object]:
    entry = entry_pose or {**_point(0, 0), "rotation_deg": 0}
    return {
        "reference_frame": REFERENCE_FRAME,
        "forward_axis": FORWARD_AXIS,
        "origin_reference": ORIGIN_REFERENCE,
        "vehicle_reference_point": _point(0, 0),
        "entry_pose": entry,
        "exit_pose": exit_pose,
    }


def _truck_maneuver_payload() -> dict[str, object]:
    straight = template_payload(
        STRAIGHT_APPROACH,
        template_id="straight",
        vehicle_width_m=Decimal("2.731"),
        vehicle_length_m=Decimal("11.113"),
        envelope_geometry={
            "type": "polygon",
            "points": [_point(0, -2), _point(40, -2), _point(40, 2), _point(0, 2)],
        },
        reference_frame=_reference_frame({**_point(40, 0), "rotation_deg": 0}),
    )
    turn = template_payload(
        TURN_90,
        template_id="turn",
        vehicle_width_m=Decimal("2.731"),
        vehicle_length_m=Decimal("11.113"),
        envelope_geometry={
            "type": "polygon",
            "points": [_point(0, 0), _point(4, 0), _point(4, 20), _point(0, 20)],
        },
        reference_frame=_reference_frame({**_point(0, 20), "rotation_deg": 0}),
        turn_direction="LEFT",
    )
    dock = template_payload(
        DOCK_REVERSE,
        template_id="dock",
        vehicle_width_m=Decimal("2.731"),
        vehicle_length_m=Decimal("11.113"),
        envelope_geometry={
            "type": "polygon",
            "points": [_point(0, 0), _point(88.6, 0), _point(88.6, 20), _point(0, 20)],
        },
        reference_frame=_reference_frame(
            {**_point(88.6, 12), "rotation_deg": 0},
        ),
        dock_face_reference=DOCK_FACE_REFERENCE,
        approach_pose={**_point(0, 0), "rotation_deg": 0},
        final_dock_pose={**_point(88.6, 12), "rotation_deg": 180},
    )
    return project_payload(
        templates=[straight, turn, dock],
        classes=[STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE],
    )


def _site_input() -> dict[str, Any]:
    return {
        "site_boundary": {
            "type": "polygon",
            "points": [_point(0, 0), _point(220, 0), _point(220, 160), _point(0, 160)],
        },
        "main_entrance": {"start": _point(Decimal("34.7"), 0), "end": _point(Decimal("44.7"), 0)},
        "truck_entrance": {"start": _point(220, 78), "end": _point(220, 82)},
        "preferred_loading_side": "UNSPECIFIED",
        "no_build_zones": [],
    }


def _zone(
    code: str,
    x: object,
    y: object,
    width: object,
    depth: object,
    rotation: int = 0,
) -> dict[str, object]:
    return {
        "zone_code": code,
        "x": x,
        "y": y,
        "width_m": width,
        "depth_m": depth,
        "rotation_deg": rotation,
    }


def _placement(zone_plan: dict[str, Any], handoff: Any, geometry: Any) -> SitePlacementResultV1:
    rows = [
        _zone("raw_fruit_buffer", "19.5", 20, "15.2", "8.7"),
        _zone("primary_precooling_room", 20, "28.7", "14.7", "10.05"),
        _zone("sorting_packaging_room", "34.7", 29, "45.76", "13.6"),
        _zone("secondary_precooling_room", "34.7", "42.6", "9.8", "10.05"),
        _zone("coating_room", "44.5", "42.6", 8, 10),
        _zone("finished_goods_room", "52.5", "42.6", "32.4", "18.6"),
        _zone("shipping_channel", "84.9", "42.6", "6.5", "7.693"),
        _zone("changing_room", "34.7", 19, 4, 10),
        _zone("office", "84.9", "50.293", 6, 10),
        # Keep the P1D3 long-edge -> sorting short-edge relationship physically
        # valid under the portal-only corridor boundary rule.  The rotated
        # long edge shares the sorting room's left short edge without blocking
        # the project-bound truck maneuver area.
        _zone("packaging_material_storage", "20.2", "38.8", "17.3", "14.5", rotation=90),
        _zone("secondary_fruit_buffer", 50, "22.1", "8.4", "6.9"),
        _zone("frozen_fruit_room", "58.4", "20.8", "10.8", "8.2"),
    ]
    return SitePlacementResultV1.from_payload(
        {
            "schema_version": "1.0.0",
            "placement_result_identity": "site_constrained_factory_layout@1.0.0",
            "source_zone_plan_hash": canonical_hash(zone_plan),
            "source_p1_handoff_hash": handoff.canonical_result_hash,
            "source_site_geometry_hash": geometry.canonical_result_hash,
            "source_objective_profile_hash": approved_objective_profile().canonical_result_hash,
            "zone_count": 12,
            "placement_access_requirement_count": 12,
            "zones": rows,
            "shipping_loading_face_side": "RIGHT_LONG_EDGE",
            "shipping_loading_face_segment": {
                "start": _point("91.4", "42.6"),
                "end": _point("91.4", "49.1"),
            },
            "placement_hard_constraints_passed": True,
            "must_adjacency_evaluation": {"hard_constraints_passed": True},
            "should_adjacency_evaluation": {"satisfied_count": 0, "required_count": 5},
            "placement_access_observations": [],
            "placement_objective_vector": {},
            "search_provenance": {"fixture": True},
        }
    )


@pytest.fixture(scope="module")
def representative_context() -> tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any]:
    zone_plan = snapshot()
    p1f = truck_input()
    handoff = build_p1_project_handoff(zone_plan, p1f)
    geometry = validate_site_geometry(
        {"site_constraints": _site_input(), "truck_access": p1f},
        zone_plan,
        p1_handoff=handoff,
    )
    placement = _placement(zone_plan, handoff, geometry)
    binding = validate_truck_maneuver_project_binding(p1f_input(), _truck_maneuver_payload())
    return zone_plan, handoff, geometry, placement, binding


def test_representative_full_pass_validates_all_access_and_truck_requirements(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    result = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    ).to_dict()
    assert result["access_requirement_count"] == 12
    assert result["access_result_count"] == 12
    assert result["access_pass_count"] == 12
    assert result["truck_route_validated"] is True
    assert result["project_layout_validated"] is True
    assert result["p2_complete"] is True
    assert result["building_footprint"] is not None
    assert result["route_metrics"]["available"] is True
    assert result["route_metrics"]["objective_optimization_active"] is False
    assert all(row["status"] == "PASS" for row in result["access_results"])


def test_missing_truck_binding_keeps_twelve_results_but_fails_closed(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, _ = representative_context
    result = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        None,
        route_node_budget=5000,
    ).to_dict()
    assert result["access_result_count"] == 12
    assert result["truck_route_validated"] is False
    assert result["project_layout_validated"] is False
    assert result["p2_complete"] is False
    truck = next(row for row in result["access_results"] if row["flow_kind"] == "TRUCK")
    assert truck["codes"] == ["BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"]


def test_replay_is_deterministic_and_access_observations_are_one_to_one(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    first = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    second = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=5000,
    )
    first_body = first.to_dict()
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert len(first_body["placement_access_observations"]) == 12
    expected_ids = {
        row["identity"]
        for row in handoff.to_dict()["p1e_historical_handoff"]["access_requirements"]
    }
    assert {
        row["observation_id"] for row in first_body["placement_access_observations"]
    } == expected_ids
    assert (
        first_body["access_requirements"]
        == handoff.to_dict()["p1e_historical_handoff"]["access_requirements"]
    )


def test_placement_source_hash_and_p1_authority_are_bound(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    tampered = placement.to_dict()
    tampered["source_zone_plan_hash"] = "sha256:" + "0" * 64
    with pytest.raises(LayoutAuthorityError) as error:
        route_site_placement(zone_plan, handoff, geometry, tampered, binding)
    assert error.value.code == "PLACEMENT_INTEGRITY_MISMATCH"

    handoff_body = handoff.to_dict()
    handoff_body["p1e_historical_handoff"]["access_requirements"][0]["direct_allowed"] = False
    with pytest.raises(LayoutAuthorityError) as error:
        route_site_placement(zone_plan, handoff_body, geometry, placement, binding)
    assert error.value.code == "P1_HANDOFF_INTEGRITY_MISMATCH"


def test_maneuver_binding_is_project_bound_and_not_defaulted(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, _ = representative_context
    invalid = deepcopy(_truck_maneuver_payload())
    invalid["project_id"] = "another-project"
    with pytest.raises(LayoutAuthorityError):
        route_site_placement(
            zone_plan,
            handoff,
            geometry,
            placement,
            invalid,
        )


def test_selected_loading_face_cannot_be_switched_during_routing(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    tampered = placement.to_dict()
    tampered["shipping_loading_face_side"] = "LEFT_LONG_EDGE"
    tampered.pop("canonical_result_hash")
    tampered["canonical_result_hash"] = canonical_hash(tampered)
    with pytest.raises(LayoutAuthorityError) as error:
        route_site_placement(zone_plan, handoff, geometry, tampered, binding)
    assert error.value.code == "PLACEMENT_INTEGRITY_MISMATCH"


def test_truck_search_budget_exhaustion_does_not_claim_validation(
    representative_context: tuple[dict[str, Any], Any, Any, SitePlacementResultV1, Any],
) -> None:
    zone_plan, handoff, geometry, placement, binding = representative_context
    result = route_site_placement(
        zone_plan,
        handoff,
        geometry,
        placement,
        binding,
        route_node_budget=5000,
        truck_node_budget=0,
    ).to_dict()
    assert result["truck_route_validated"] is False
    assert result["project_layout_validated"] is False
    assert result["p2_complete"] is False
    assert result["truck_route_status"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
    assert result["truck_search_provenance"]["node_budget_exhausted"] is True


def test_packaging_access_rejects_a_non_straight_route() -> None:
    requirement = {
        "identity": "access:packaging_material_storage->sorting_packaging_room@1.0.0",
        "from_ref": "packaging_material_storage",
        "to_ref": "sorting_packaging_room",
        "flow_kind": "PACKAGING",
        "access_class": "MATERIAL_LOGISTICS",
        "profile_identity": "packaging-sorting-straight-access@1.0.0",
        "portal_required": True,
        "corridor_allowed": True,
        "direct_allowed": True,
        "route_shape_constraint": "STRAIGHT_ONLY",
        "edge_orientation_requirement": "packaging-sorting-edge-connection@1.0.0",
        "cold_room_refs": [],
        "cold_room_portal_profile_identity": None,
        "source_authority": "Charles:V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1",
    }
    zones = {
        "packaging_material_storage": PlacedRectangleV1(
            "packaging_material_storage", 5, 5, 17.3, 14.5
        ),
        "sorting_packaging_room": PlacedRectangleV1("sorting_packaging_room", 55, 50, 45.76, 13.6),
    }
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(0, 0), _point(130, 0), _point(130, 100), _point(0, 100)],
        }
    )
    result, corridors = route_access_requirement(
        requirement,
        relationships={
            "packaging-sorting-edge-connection@1.0.0": {
                "identity": "packaging-sorting-edge-connection@1.0.0",
                "from_edge_class": "LONG_EDGE",
                "to_edge_class": "SHORT_EDGE_EXIT_SIDE",
            }
        },
        zones=zones,
        boundary=boundary,
        obstacles=(),
        entrances={},
    )
    assert result["status"] in {"BLOCKED", "FAIL"}
    assert "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED" in result["codes"]
    assert corridors == ()


def test_portal_width_is_fail_closed() -> None:
    requirement = {
        "identity": "access:raw_fruit_buffer->primary_precooling_room@1.0.0",
        "from_ref": "raw_fruit_buffer",
        "to_ref": "primary_precooling_room",
        "flow_kind": "MATERIAL",
        "access_class": "MATERIAL_LOGISTICS",
        "profile_identity": "manual-pallet-jack-clear-envelope@1.0.0",
        "portal_required": True,
        "corridor_allowed": True,
        "direct_allowed": True,
        "route_shape_constraint": "NOT_FROZEN",
        "edge_orientation_requirement": None,
        "cold_room_refs": [],
        "cold_room_portal_profile_identity": None,
        "source_authority": "Charles:V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1",
    }
    zones = {
        "raw_fruit_buffer": PlacedRectangleV1("raw_fruit_buffer", 5, 5, 1, 1),
        "primary_precooling_room": PlacedRectangleV1("primary_precooling_room", 6, 5, 1, 1),
    }
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(0, 0), _point(20, 0), _point(20, 20), _point(0, 20)],
        }
    )
    result, _ = route_access_requirement(
        requirement,
        relationships={},
        zones=zones,
        boundary=boundary,
        obstacles=(),
        entrances={},
    )
    assert result["status"] == "FAIL"
    assert "PORTAL_CLEAR_WIDTH_INSUFFICIENT" in result["codes"]


def test_corridor_may_touch_incident_boundaries_only_at_portals() -> None:
    zones = {
        "from_zone": PlacedRectangleV1("from_zone", 0, 0, 10, 10),
        "to_zone": PlacedRectangleV1("to_zone", 20, 0, 10, 10),
    }
    boundary = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(-10, -10), _point(40, -10), _point(40, 20), _point(-10, 20)],
        }
    )
    safe, reason, _ = _route_is_safe(
        ((10_000, 5_000), (20_000, 5_000)),
        width_mm=2_500,
        boundary=boundary,
        obstacles=(),
        zones=zones,
        incident_refs=frozenset({"from_zone", "to_zone"}),
    )
    assert safe is True
    assert reason is None

    unsafe, reason, _ = _route_is_safe(
        ((10_000, 5_000), (9_000, 5_000), (20_000, 5_000)),
        width_mm=2_500,
        boundary=boundary,
        obstacles=(),
        zones=zones,
        incident_refs=frozenset({"from_zone", "to_zone"}),
    )
    assert unsafe is False
    assert reason == "CORRIDOR_INCIDENT_ZONE_CROSSING"


def test_personnel_truck_crossing_is_not_inferred_as_necessary() -> None:
    personnel = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(0, 0), _point(10, 0), _point(10, 2), _point(0, 2)],
        }
    )
    touching_truck = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(4, 2), _point(6, 2), _point(6, 4), _point(4, 4)],
        }
    )
    result = evaluate_personnel_truck_interaction((personnel,), (touching_truck,))
    assert result["status"] == "REQUIRES_ENGINEERING_REVIEW"
    assert result["crossing"] is True
    assert result["crossing_necessary"] == "UNDETERMINED"
    assert result["codes"] == ["PERSONNEL_TRUCK_INTERACTION_REQUIRES_ENGINEERING_REVIEW"]

    overlapping_truck = normalize_polygon(
        {
            "type": "polygon",
            "points": [_point(4, 1), _point(6, 1), _point(6, 3), _point(4, 3)],
        }
    )
    shared = evaluate_personnel_truck_interaction((personnel,), (overlapping_truck,))
    assert shared["status"] == "FAIL"
    assert shared["shared_route"] is True
    assert shared["codes"] == ["PERSONNEL_TRUCK_SHARED_ROUTE_PROHIBITED"]
