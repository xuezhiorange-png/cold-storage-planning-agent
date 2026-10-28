"""R5 whole door sweep, all users, continuous movement and immutable review scope."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.practical_changing_review import (
    preview_request,
    review_h5,
)
from cold_storage.modules.layout.domain.changing_room_motion import (
    door_hits_box,
    door_sector,
    network_path,
    prism,
    standing_person,
    swept_segments,
    verify_movement,
)
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    adjacent_transition,
    validate_use,
)
from cold_storage.modules.layout.infrastructure.practical_changing_review_page import (
    plan_svg,
    presentation,
    render_page,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("R11_R5_NATIVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", forbidden)


@pytest.fixture(scope="module")
def catalog():
    return json.loads(
        (
            ROOT
            / "docs/previews/v2.2.2/r11-r4-multi-tier-locker-review-r1"
            / "project-and-room-catalog.json"
        ).read_bytes()
    )


@pytest.fixture(scope="module")
def good(catalog):
    return review_h5(catalog, "INTERNAL_PARTITION", H5Hypothesis())


def codes(value):
    return {v["code"] for v in value["conflicts"]}


def assess(result, snapshot):
    return validate_use(
        result["room"],
        result["inventory"],
        result["model"],
        H5Hypothesis(**result["parameters"]),
        snapshot,
    )


def test_two_shifts_all_cells_and_53_users(good):
    m = good["metrics"]
    assert (m["columns"], m["compartments"], m["hypothetical_procurement_units"]) == (22, 110, 12)
    assert m["occupied_cabinet_length_mm"] == 8800 and m["cabinet_footprint_mm2"] == 4400000
    assert m["static_pass_count"] == m["snapshots"] == 30
    for shift in (1, 2):
        ss = [s for s in good["snapshots"] if s["shift"] == shift]
        assigned = {
            c["id"]
            for c in good["inventory"]["compartments"]
            if c["shift"] == shift and c["assigned_person_id"]
        }
        actions = [a for s in ss for a in s["actions"]]
        assert {a["compartment_id"] for a in actions} == assigned and len(actions) == 53
        for s in ss:
            assert len(s["people"]) == len({p["id"] for p in s["people"]}) == 53
            assert s["evaluation"]["front_operators"] <= 4
            assert (
                sum(
                    s["evaluation"][k]
                    for k in ["front_operators", "bench_users", "other_users", "changing_operators"]
                )
                == 53
            )
            assert len(s["evaluation"]["portal_results"]) == 2
            assert all(
                p["valid"] and p["clear_width_mm"] == 1500
                for p in s["evaluation"]["portal_results"]
            )
    assert (
        good["project_functional_status"] == "INPUT_REQUIRED" and not good["engineering_approval"]
    )


def test_adjacent_batches_real_sweeps_and_all_people(good):
    assert good["metrics"]["adjacent_batch_pass_count"] == 2
    for t in good["transitions"]:
        assert t["endpoint_all_53_match"]
        assert len(t["moves"]) == 8
        assert t["doors_during_movement"] == "CLOSED_BY_EXPLICIT_PROCESS_ASSUMPTION"
        assert t["all_other_batch_transitions"] == "NOT_EVALUATED"
        assert t["seated_stand_up"] == "NOT_EVALUATED"
        for move in t["moves"]:
            assert move["other_users"] == 52 and len(move["people_before"]) == 53
            assert move["swept_volumes_mm"] and move["length_mm"] > 0
            assert move["status"] == "CONTINUOUS_PATH_VERIFIED_UNDER_HYPOTHESES"
            assert move["timing"] == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"arrangement": "OPPOSED"}, "FIXED_BODY_INTRUDES_NET_AISLE"),
        (
            {"arrangement": "SEGMENTED", "segment_gap_mm": 2000},
            "53_DISTINCT_HOME_POSITIONS_NOT_AVAILABLE",
        ),
        ({"operator_standoff_mm": 0}, "HINGED_DOOR_3D_COLLISION"),
        (
            {"room_door_intrusion_mm": 300},
            "ACTUAL_ROOM_DOOR_SWING_MUST_BE_RESOLVED_BEFORE_CLEAR_PASSAGE",
        ),
        ({"cell_height_mm": 350, "cabinet_height_mm": 2000}, "HYPOTHETICAL_REACH_RANGE_NOT_MET"),
    ],
)
def test_failed_templates_preserve_failure(catalog, change, expected):
    # Zero standoff is a valid collision experiment, not an approved installation.
    if change.get("operator_standoff_mm") == 0:
        change = {"operator_standoff_mm": 1}
    r = review_h5(catalog, "INTERNAL_PARTITION", replace(H5Hypothesis(), **change))
    assert any(expected in codes(s["evaluation"]) for s in r["snapshots"])
    assert r["project_functional_status"] == "INPUT_REQUIRED"
    assert r["template_status"] == "CONFIGURATION_NOT_FULLY_VERIFIED"


def test_double_cells_do_not_reduce_people_to_pass(catalog):
    r = review_h5(catalog, "TWO_COMPARTMENTS", H5Hypothesis())
    assert r["metrics"]["columns"] == 44 and r["metrics"]["compartments"] == 220
    assert r["demand"]["simultaneous_room_users"] == 53
    assert r["metrics"]["static_pass_count"] == 0
    assert any(
        "53_DISTINCT_HOME_POSITIONS_NOT_AVAILABLE" in codes(s["evaluation"]) for s in r["snapshots"]
    )
    assert r["hygiene"]["two_compartment_separation"] == "INPUT_REQUIRED"


@pytest.mark.parametrize(
    "hypothesis",
    [
        H5Hypothesis(door_kind="NO_PLAN_INTRUSION"),
        H5Hypothesis(arrangement="SEGMENTED", segment_gap_mm=600),
    ],
)
def test_alternatives_are_only_hypotheses(catalog, hypothesis):
    r = review_h5(catalog, "INTERNAL_PARTITION", hypothesis)
    assert r["metrics"]["static_pass_count"] == 30
    assert r["project_functional_status"] == "INPUT_REQUIRED"
    assert (
        r["source_type"] == "demo" and r["requires_review"] and r["validity_status"] == "unverified"
    )


@pytest.mark.parametrize("role", ["FRONT_OPERATOR", "OTHER_CHANGING_OR_WAITING", "BENCH_USER"])
def test_no_static_person_may_occupy_net_aisle(good, role):
    s = copy.deepcopy(good["snapshots"][0])
    i = next(i for i, p in enumerate(s["people"]) if p["role"] == role)
    s["people"][i] = standing_person(
        s["people"][i]["id"], [15000, 1200, 15400, 1800], 1800, "OTHER_CHANGING_OR_WAITING"
    )
    assert "STATIONARY_PERSON_INTRUDES_NET_AISLE" in codes(assess(good, s))


def test_missing_shift_member_and_overlap_fail(good):
    s = copy.deepcopy(good["snapshots"][0])
    s["people"].pop()
    assert "ALL_53_DISTINCT_SHIFT_USERS_REQUIRED" in codes(assess(good, s))
    s = copy.deepcopy(good["snapshots"][0])
    s["people"][6]["bounds_mm"] = s["people"][5]["bounds_mm"]
    s["people"][6]["volumes_mm"] = s["people"][5]["volumes_mm"]
    assert "PERSON_3D_BODY_COLLISION" in codes(assess(good, s))


def test_wrong_assignment_and_operator_location_fail(good):
    s = copy.deepcopy(good["snapshots"][0])
    person = next(p for p in s["people"] if p["role"] == "FRONT_OPERATOR")
    person["compartment_id"] = next(
        c["id"] for c in good["inventory"]["compartments"] if c["shift"] == 2
    )
    assert "WRONG_SHIFT_COMPARTMENT" in codes(assess(good, s))
    assert "OPERATOR_NOT_AT_ASSIGNED_COLUMN" in codes(assess(good, s))


def test_failed_endpoints_cannot_create_transition(good):
    a = copy.deepcopy(good["snapshots"][0])
    a["people"].pop()
    t = adjacent_transition(
        a, good["snapshots"][1], good["inventory"], good["model"], H5Hypothesis()
    )
    assert t["status"] == "NOT_EVALUATED" and not t["moves"]


def sample_door(z0=100, z1=400, front="N", hinge="LEFT"):
    return door_sector(
        dict(id="col", unit_id="unit", bounds_mm=[100, 100, 500, 600], front=front),
        dict(id="cell", independent_door_id="door", elevation_bounds_mm=[0, z0, 400, z1]),
        kind="OUTWARD_HINGED_90",
        frame_mm=20,
        thickness_mm=15,
        hinge=hinge,
    )


def test_height_matters_but_aisle_projection_still_reserved():
    high = sample_door(1380, 1680)
    low = sample_door()
    bench = [150, 650, 0, 350, 750, 450]
    assert door_hits_box(low, bench)
    assert not door_hits_box(high, bench)
    assert door_hits_box(high, bench, projection=True)
    assert door_hits_box(high, [150, 650, 0, 350, 750, 1800])


@pytest.mark.parametrize(
    "front,hinge", [("N", "LEFT"), ("N", "RIGHT"), ("S", "LEFT"), ("S", "RIGHT")]
)
def test_whole_sector_not_only_closed_and_open_leaf(front, hinge):
    d = sample_door(front=front, hinge=hinge)
    hx, hy = d["hinge_mm"]
    sx, sy = d["direction"]
    x = hx + sx * 180
    y = hy + sy * 180
    assert door_hits_box(d, [x - 5, y - 5, 150, x + 5, y + 5, 350])
    assert not door_hits_box(
        d, [hx + sx * 500 - 5, hy + sy * 500 - 5, 150, hx + sx * 500 + 5, hy + sy * 500 + 5, 350]
    )


def test_no_intrusion_requires_explicit_supported_mechanism():
    d = sample_door()
    d["kind"] = "NO_PLAN_INTRUSION"
    assert not door_hits_box(d, [150, 650, 0, 350, 750, 1800])
    with pytest.raises(ValueError):
        door_sector(
            dict(bounds_mm=[0, 0, 400, 500]),
            {},
            kind="ASSUME_ALL_UPPER_DOORS_SAFE",
            frame_mm=20,
            thickness_mm=15,
            hinge="LEFT",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("column_width_mm", 0),
        ("front_concurrency", 0),
        ("bench_count", 0),
        ("person_width_mm", False),
        ("aisle_mm", -1),
        ("columns_per_unit", 7),
        ("front_concurrency", 54),
    ],
)
def test_invalid_or_reduced_functions_not_silently_accepted(field, value):
    with pytest.raises(ValueError):
        replace(H5Hypothesis(), **{field: value}).checked()


def test_network_and_sweep_are_complete_not_endpoint_only():
    assert network_path(
        [200, 300], [2000, 1300], [[[200, 300], [2000, 300]], [[2000, 300], [2000, 1300]]]
    ) == [[200, 300], [2000, 300], [2000, 1300]]
    assert swept_segments([[200, 300], [2000, 300]], 400, 600, 1800) == [[0, 0, 0, 2200, 600, 1800]]
    with pytest.raises(ValueError):
        swept_segments([[200, 300], [2000, 1300]], 400, 600, 1800)
    assert network_path([1, 1], [2, 2], [[[0, 1], [1, 1]]]) is None


def movement_case():
    person = standing_person("active", [0, 0, 400, 600], 1800, "FRONT_OPERATOR")
    target = standing_person("active", [1800, 0, 2200, 600], 1800, "OTHER_CHANGING_OR_WAITING")
    others = [
        standing_person(
            f"person-{i}",
            [3000 + i * 500, 2000, 3400 + i * 500, 2600],
            1800,
            "OTHER_CHANGING_OR_WAITING",
        )
        for i in range(52)
    ]
    return dict(
        points=[[200, 300], [2000, 300]],
        person=person,
        target=target,
        others=others,
        bodies=[],
        clear=[0, 0, 30000, 3000],
        width=400,
        depth=600,
        height=1800,
        allowed=[[0, 0, 2200, 600]],
        open_doors=[],
        clear_height=3000,
    )


def test_movement_clear_endpoints_mid_segment_collision():
    k = movement_case()
    assert verify_movement(**k)["status"] == "CONTINUOUS_PATH_VERIFIED_UNDER_HYPOTHESES"
    k["bodies"] = [dict(id="cabinet", volumes_mm=[[900, 100, 0, 1000, 500, 1000]])]
    assert "CONTINUOUS_BODY_COLLISION" in codes(verify_movement(**k))


def test_movement_cannot_discard_other_people_or_leave_corridor():
    k = movement_case()
    k["others"].pop()
    assert "53_DISTINCT_USERS_MUST_BE_PRESERVED" in codes(verify_movement(**k))
    k = movement_case()
    k["allowed"] = [[0, 0, 500, 600], [1700, 0, 2200, 600]]
    assert "MOVEMENT_OUTSIDE_RESERVED_AISLE_OR_ENDPOINT_APPROACH" in codes(verify_movement(**k))
    k = movement_case()
    k["others"][0]["volumes_mm"] = [[900, 100, 0, 1000, 500, 1800]]
    assert "CONTINUOUS_BODY_COLLISION" in codes(verify_movement(**k))


def test_seated_static_does_not_prove_stand_up():
    k = movement_case()
    k["person"]["pose"] = "SEATED"
    assert verify_movement(**k)["status"] == "NOT_EVALUATED"


def test_no_motion_body_shrink_or_identity_swap():
    k = movement_case()
    k["width"] = 200
    assert "MOVEMENT_BODY_DIMENSIONS_CHANGED" in codes(verify_movement(**k))
    k = movement_case()
    k["target"]["id"] = "another"
    assert "MOVEMENT_PERSON_IDENTITY_CHANGED" in codes(verify_movement(**k))


def test_same_project_raw_portals_and_source_preserved(catalog, good):
    before = copy.deepcopy(catalog)
    review_h5(catalog, "INTERNAL_PARTITION", H5Hypothesis())
    assert catalog == before
    assert good["record_access_readbacks"] == catalog["groups"][0]["record_access_readbacks"]
    assert good["records"] == ["P01", "P02"]
    assert good["room"]["portals"] == catalog["groups"][0]["room"]["portals"]
    bad = copy.deepcopy(catalog)
    bad["groups"][0]["room"]["portals"][0]["clear_width_mm"] = 1200
    with pytest.raises(ValueError, match="ORIGINAL_R4_REVIEW_CATALOG_SOURCE"):
        review_h5(bad, "INTERNAL_PARTITION", H5Hypothesis())


@pytest.mark.parametrize(
    "extra", ["source_label", "status", "project_facts", "simultaneous_room_users", "approved"]
)
def test_ui_cannot_write_approval_or_reduce_people(catalog, extra):
    with pytest.raises(ValueError):
        preview_request(
            catalog, dict(scenario="INTERNAL_PARTITION", parameters={extra: "APPROVED"})
        )


def test_rendered_plan_uses_real_portals_and_physical_units(good):
    svg = plan_svg(good, good["snapshots"][0])
    assert "26331" in svg and "12415" in svg and "13915" in svg
    assert "HYPOTHETICAL_NOT_APPROVED" in svg
    assert "净通道1200" in svg
    assert "S1-U01" in svg and "S2-U01" in svg
    view = presentation(good)
    page = render_page({"A": view})
    assert "INPUT_REQUIRED" in page and "座凳起坐" in page
    assert len(view["transitions"]["1"]) == 8
    assert "Math.ceil" not in page  # engineering formulas remain in Python


def test_determinism_and_no_native(catalog, good):
    assert review_h5(catalog, "INTERNAL_PARTITION", H5Hypothesis()) == good
    assert good["native_solves"] == 0


def test_people_and_motion_must_fit_clear_height(catalog):
    r = review_h5(
        catalog, "INTERNAL_PARTITION", H5Hypothesis(standing_height_mm=4000, seated_height_mm=3500)
    )
    assert r["metrics"]["static_pass_count"] == 0
    assert all("PERSON_EXCEEDS_CLEAR_HEIGHT" in codes(s["evaluation"]) for s in r["snapshots"])
    k = movement_case()
    k["height"] = 4000
    assert "MOVEMENT_EXCEEDS_CLEAR_HEIGHT" in codes(verify_movement(**k))


def test_omitted_or_changed_active_door_cannot_pass(catalog):
    r = review_h5(catalog, "INTERNAL_PARTITION", H5Hypothesis(operator_standoff_mm=300))
    s = copy.deepcopy(r["snapshots"][0])
    assert "HINGED_DOOR_3D_COLLISION" in codes(s["evaluation"])
    s["doors"] = []
    assert "ACTIVE_DOOR_SWEEP_BINDING_MISMATCH" in codes(assess(r, s))
    s = copy.deepcopy(r["snapshots"][0])
    s["doors"][0]["kind"] = "NO_PLAN_INTRUSION"
    assert "ACTIVE_DOOR_SWEEP_BINDING_MISMATCH" in codes(assess(r, s))


def test_cached_evaluation_cannot_hide_pose_change(good):
    s = copy.deepcopy(good["snapshots"][1])
    person = next(p for p in s["people"] if p["role"] == "BENCH_USER")
    replacement = standing_person(
        person["id"], person["bounds_mm"], 1800, "OTHER_CHANGING_OR_WAITING"
    )
    s["people"][s["people"].index(person)] = replacement
    assert s["evaluation"]["status"] == "STATIC_TEMPLATE_VERIFIED_UNDER_HYPOTHESES"
    t = adjacent_transition(
        good["snapshots"][0], s, good["inventory"], good["model"], H5Hypothesis()
    )
    assert t["status"] == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "part", ["source", "room_scope", "portal_id", "readbacks", "external_routes"]
)
def test_frozen_source_identity_cannot_be_fabricated(catalog, part):
    bad = copy.deepcopy(catalog)
    row = bad["groups"][0]
    if part == "source":
        bad["project_facts"]["source_sha256"] = "fake"
    elif part == "room_scope":
        row["room"]["scope_id"] = "fake"
    elif part == "portal_id":
        row["room"]["portals"][0]["id"] = row["room"]["portals"][1]["id"]
    elif part == "readbacks":
        row["record_access_readbacks"] = []
    else:
        row["external_routes"] = []
    with pytest.raises(ValueError, match="SOURCE_MISMATCH"):
        review_h5(bad, "INTERNAL_PARTITION", H5Hypothesis())


def test_actual_occupancy_display_for_failed_plan(catalog):
    r = review_h5(catalog, "TWO_COMPARTMENTS", H5Hypothesis())
    s = r["snapshots"][0]
    assert s["evaluation"]["people_count"] < 53
    assert f"图示{s['evaluation']['people_count']}/要求53人" in plan_svg(r, s)


def test_changing_operation_zone_remains_outside_aisle(good):
    for s in good["snapshots"]:
        people = [p for p in s["people"] if p["role"] == "CHANGING_OPERATOR"]
        assert len(people) <= 1
        for p in people:
            assert p["bounds_mm"] == good["model"]["changing_zone"]
            assert (
                p["bounds_mm"][2] - p["bounds_mm"][0],
                p["bounds_mm"][3] - p["bounds_mm"][1],
            ) == (800, 900)
    s = copy.deepcopy(good["snapshots"][0])
    person = next(p for p in s["people"] if p["role"] == "CHANGING_OPERATOR")
    person["bounds_mm"] = [15000, 1200, 15800, 2100]
    person["volumes_mm"] = [prism(person["bounds_mm"], 0, 1800)]
    assert "STATIONARY_PERSON_INTRUDES_NET_AISLE" in codes(assess(good, s))


def test_changing_cannot_occupy_real_entry_landing(good):
    s = copy.deepcopy(good["snapshots"][0])
    person = next(p for p in s["people"] if p["role"] == "CHANGING_OPERATOR")
    person["bounds_mm"] = [25511, 2225, 26311, 3125]
    person["volumes_mm"] = [prism(person["bounds_mm"], 0, 1800)]
    assert "PERSON_INTRUDES_ENTRANCE_LANDING" in codes(assess(good, s))


def test_changing_envelope_cannot_shrink_person(catalog):
    with pytest.raises(ValueError, match="CONTAIN_FULL_PERSON"):
        review_h5(
            catalog,
            "INTERNAL_PARTITION",
            H5Hypothesis(changing_operation_width_mm=1, changing_operation_depth_mm=1),
        )


def test_movement_height_bound_to_actual_person():
    k = movement_case()
    k["height"] = 1000
    k["bodies"] = [dict(id="high_obstacle", volumes_mm=[[900, 100, 1200, 1000, 500, 1700]])]
    assert "MOVEMENT_BODY_DIMENSIONS_CHANGED" in codes(verify_movement(**k))
