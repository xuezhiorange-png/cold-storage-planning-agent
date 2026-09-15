"""Owner values, per-edge binding, hostile observations and unchanged dimensions."""

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal, localcontext

import pytest

from cold_storage.modules.layout.application.access_handoff import (
    build_access_handoff,
    evaluate_access_observation,
    required_access_connections,
    validate_access_handoff_integrity,
)
from cold_storage.modules.layout.application.dimension_handoff import build_dimension_handoff
from cold_storage.modules.layout.domain.access_authority import (
    COLD_ROOM,
    MATERIAL,
    PACKAGING,
    PERSONNEL,
    TRUCK,
    TRUCK_REQUIRED_FIELDS,
    AccessRequirementV1,
    approved_access_profiles,
    resolve_access_profile,
)
from cold_storage.modules.layout.domain.access_predicates import evaluate_personnel_truck_policy
from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW, process_graph
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot

D = Decimal


def requirement(first, second):
    return next(
        r for r in required_access_connections() if (r.from_ref, r.to_ref) == (first, second)
    )


def observation(**overrides):
    return {
        "topology": "CORRIDOR_MEDIATED",
        "portal_clear_width_m": "2.4",
        "corridor_clear_width_m": "2.5",
        **overrides,
    }


def test_combined_handoff_keeps_entire_dimension_payload_immutable():
    source = snapshot()
    before = deepcopy(source)
    dimension = build_dimension_handoff(source)
    first = build_access_handoff(source)
    with localcontext() as ctx:
        ctx.prec = 2
        second = build_access_handoff(source)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert source == before
    body = first.to_dict()
    assert body["dimension_handoff"] == dimension.to_dict()
    assert body["dimension_handoff_hash"] == dimension.canonical_result_hash
    assert len(body["dimension_handoff"]["dimensions"]) == 9
    assert (
        sum(a["status"] == "FLEXIBLE_AUTHORIZED" for a in body["dimension_handoff"]["authorities"])
        == 3
    )
    assert body["spatial_relationships"] == dimension.to_dict()["spatial_relationships"]
    status = body["authority_status"]
    assert status["dimension_authority_complete"]
    assert status["personnel_access_authority_complete"]
    assert status["material_access_authority_complete"]
    assert status["truck_access_contract_complete"]
    assert not status["truck_access_engineering_values_complete"]
    assert not status["p1_complete"]
    assert body["office_shipping_personnel_portal_required"] is False
    assert validate_access_handoff_integrity(source, body)
    body["access_profiles"][0]["portal_clear_width_m"] = "0.1"
    assert not validate_access_handoff_integrity(source, body)


def test_approved_profiles_no_forklift_or_height_rule():
    p = {p.identity: p for p in approved_access_profiles()}
    assert (p[PERSONNEL].portal_clear_width_m, p[PERSONNEL].corridor_clear_width_m) == (
        D("1.5"),
        D("2"),
    )
    assert (p[MATERIAL].portal_clear_width_m, p[MATERIAL].corridor_clear_width_m) == (
        D("2.4"),
        D("2.5"),
    )
    assert p[MATERIAL].transport_mode == "MANUAL_PALLET_JACK"
    assert p[COLD_ROOM].portal_clear_width_m == D("2.4")
    assert p[PACKAGING].corridor_clear_width_m == D("5")
    assert p[PACKAGING].route_shape_constraint == "STRAIGHT_ONLY"
    assert all(not row.door_height_validation for row in p.values())


def test_exact_connection_counts_and_no_graph_changes():
    connections = required_access_connections()
    assert len(connections) == len({r.identity for r in connections}) == 12
    assert [(r.from_ref, r.to_ref) for r in connections if r.flow_kind == "PEOPLE"] == [
        ("main_entrance", "changing_room"),
        ("changing_room", "sorting_packaging_room"),
    ]
    assert [(r.from_ref, r.to_ref) for r in connections if r.flow_kind == "MATERIAL"] == list(
        zip(PROCESS_FLOW[:-1], PROCESS_FLOW[1:], strict=True)
    )
    assert len([r for r in connections if r.flow_kind in ("SECONDARY", "FROZEN")]) == 2
    assert len([r for r in connections if r.flow_kind == "PACKAGING"]) == 1
    assert not any(r.from_ref == "office" for r in connections)
    graph = process_graph()
    assert len(graph.must_adjacencies) == 7 and len(graph.should_adjacencies) == 5
    for r in connections:
        if r.profile_identity != TRUCK:
            assert resolve_access_profile(r.profile_identity).access_class == r.access_class


@pytest.mark.parametrize(
    "code",
    [
        "primary_precooling_room",
        "secondary_precooling_room",
        "finished_goods_room",
        "secondary_fruit_buffer",
        "frozen_fruit_room",
    ],
)
def test_cold_room_endpoint_binding(code):
    bindings = [r for r in required_access_connections() if code in r.cold_room_refs]
    assert bindings
    assert all(r.cold_room_portal_profile_identity == COLD_ROOM for r in bindings)


@pytest.mark.parametrize(
    "portal,corridor,status",
    [("1.5", "2", "PASS"), ("1.499999999999", "2", "FAIL"), ("1.5", "1.999999999999", "FAIL")],
)
def test_personnel_exact_widths(portal, corridor, status):
    r = requirement("main_entrance", "changing_room")
    result = evaluate_access_observation(
        r.identity, observation(portal_clear_width_m=portal, corridor_clear_width_m=corridor)
    )
    assert result["status"] == status
    assert result["full_access_validated"] is False


@pytest.mark.parametrize(
    "portal,corridor,status",
    [("2.4", "2.5", "PASS"), ("2.399999999999", "2.5", "FAIL"), ("2.4", "2.499999999999", "FAIL")],
)
def test_material_exact_widths(portal, corridor, status):
    r = requirement("raw_fruit_buffer", "primary_precooling_room")
    assert (
        evaluate_access_observation(
            r.identity, observation(portal_clear_width_m=portal, corridor_clear_width_m=corridor)
        )["status"]
        == status
    )


@pytest.mark.parametrize("height", [None, 0, "not a height"])
def test_height_not_part_of_2d_validation(height):
    r = requirement("sorting_packaging_room", "frozen_fruit_room")
    assert (
        evaluate_access_observation(r.identity, observation(door_height_m=height))["status"]
        == "PASS"
    )


@pytest.mark.parametrize("value", [True, None, "NaN", "Infinity", "abc", -1])
def test_hostile_widths_fail_closed(value):
    r = requirement("raw_fruit_buffer", "primary_precooling_room")
    assert (
        evaluate_access_observation(r.identity, observation(portal_clear_width_m=value))["status"]
        == "FAIL"
    )


def test_missing_width_and_fake_profile_or_transport():
    r = requirement("raw_fruit_buffer", "primary_precooling_room")
    assert (
        evaluate_access_observation(r.identity, {"topology": "DIRECT_SHARED_EDGE"})["status"]
        == "BLOCKED"
    )
    assert (
        evaluate_access_observation(r.identity, observation(profile_identity=PERSONNEL))["status"]
        == "FAIL"
    )
    assert (
        evaluate_access_observation(r.identity, observation(transport_mode="FORKLIFT"))["status"]
        == "FAIL"
    )
    with pytest.raises(LayoutAuthorityError):
        evaluate_access_observation("fake", observation())


@pytest.mark.parametrize(
    "shape,turns,width,aligned,status",
    [
        ("STRAIGHT", 0, "5", True, "PASS"),
        ("STRAIGHT", 0, "4.999", True, "FAIL"),
        ("TURN_90", 1, "5", True, "FAIL"),
        ("POLYLINE", 2, "5", True, "FAIL"),
        ("STRAIGHT", False, "5", True, "FAIL"),
        ("STRAIGHT", 0, "5", False, "FAIL"),
    ],
)
def test_packaging_straight_only(shape, turns, width, aligned, status):
    r = requirement("packaging_material_storage", "sorting_packaging_room")
    assert r.edge_orientation_requirement == "packaging-sorting-edge-connection@1.0.0"
    result = evaluate_access_observation(
        r.identity,
        observation(
            corridor_clear_width_m=width,
            route_shape=shape,
            turn_count=turns,
            edge_alignment_verified=aligned,
        ),
    )
    assert result["status"] == status


def test_packaging_direct_needs_portal_not_corridor_width():
    r = requirement("packaging_material_storage", "sorting_packaging_room")
    o = {
        "topology": "DIRECT_SHARED_EDGE",
        "portal_clear_width_m": "2.4",
        "edge_alignment_verified": True,
    }
    assert evaluate_access_observation(r.identity, o)["status"] == "PASS"
    o["portal_clear_width_m"] = "2.3"
    assert evaluate_access_observation(r.identity, o)["status"] == "FAIL"


@pytest.mark.parametrize("zone", ["secondary_fruit_buffer", "frozen_fruit_room"])
@pytest.mark.parametrize("topology", ["DIRECT_SHARED_EDGE", "CORRIDOR_MEDIATED"])
def test_side_flow_alternatives_without_must(zone, topology):
    r = requirement("sorting_packaging_room", zone)
    assert r.portal_required and r.direct_allowed and r.corridor_allowed
    assert (
        evaluate_access_observation(r.identity, observation(topology=topology))["status"] == "PASS"
    )
    assert all(set(edge) != {r.from_ref, r.to_ref} for edge in process_graph().must_adjacencies)


@pytest.mark.parametrize(
    "shared,crossing,necessary,status",
    [
        (True, False, False, "FAIL"),
        (True, True, True, "FAIL"),
        (False, True, True, "PASS_WITH_REVIEW"),
        (False, True, False, "FAIL"),
        (False, False, False, "PASS"),
        (1, False, False, "FAIL"),
    ],
)
def test_people_truck_policy(shared, crossing, necessary, status):
    r = evaluate_personnel_truck_policy(
        shared_route=shared, crossing=crossing, crossing_necessary=necessary
    )
    assert r["status"] == status
    if status == "PASS_WITH_REVIEW":
        assert r["requires_review"]
        assert r["warnings"] == ["PERSONNEL_TRUCK_CROSSING_REQUIRES_ENGINEERING_REVIEW"]


def test_truck_has_no_invented_dimensions_and_never_passes_missing_values():
    b = build_access_handoff(snapshot()).to_dict()
    t = b["truck_profile"]
    assert all(t[field] is None for field in TRUCK_REQUIRED_FIELDS)
    assert t["outdoor_only"] and not t["inside_building_allowed"]
    r = requirement("truck_entrance", "shipping_channel")
    assert evaluate_access_observation(r.identity, {"inside_building": True})["status"] == "FAIL"
    out = evaluate_access_observation(
        r.identity, {"inside_building": False, "vehicle_width_m": "999"}
    )
    assert out["status"] == "BLOCKED"
    assert out["missing_owner_inputs"] == list(TRUCK_REQUIRED_FIELDS)


def test_wrong_connection_profile_rejected():
    data = asdict(requirement("raw_fruit_buffer", "primary_precooling_room"))
    data["profile_identity"] = PERSONNEL
    with pytest.raises(LayoutAuthorityError):
        AccessRequirementV1(**data)
