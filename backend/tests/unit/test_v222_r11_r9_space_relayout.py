"""Spatial arrangements, real 53-user traces and conservative continuous yaw."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.h5_space_relayout_review import review_relayouts
from cold_storage.modules.layout.domain.cabinet_front_schedule import group_proof
from cold_storage.modules.layout.domain.changing_operation_motion import PASS, center
from cold_storage.modules.layout.domain.changing_room_motion import prism
from cold_storage.modules.layout.domain.h5_relayout_motion import relayout_transfer
from cold_storage.modules.layout.domain.h5_relayout_operation import (
    RelayoutTiming,
    simulate_relayout_shift,
)
from cold_storage.modules.layout.domain.h5_space_relayout import (
    TEMPLATES,
    relayout_geometry,
    sensitivity_parameters,
    waiting_clearances,
)
from cold_storage.modules.layout.domain.practical_changing_layout import (
    H5Hypothesis,
    _snapshot,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("R11_R9_NATIVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", forbidden)


@pytest.fixture(scope="module")
def sources():
    c = json.loads(
        (
            ROOT
            / "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1"
            / "project-and-room-catalog.json"
        ).read_bytes()
    )
    r7 = (ROOT / "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt").read_bytes()
    r8 = (ROOT / "docs/tasks/V2_2_2-r11-r8-reviewed-cabinet-front-facts.txt").read_bytes()
    return c, r7, r8


@pytest.fixture(scope="module")
def cases(sources):
    return list(review_relayouts(*sources).values())


@pytest.mark.parametrize("i", range(3))
def test_three_distinct_original_h5_organizations(cases, sources, i):
    g = cases[i]["geometry"]
    assert g["room"] == sources[0]["groups"][0]["room"]
    assert g["room"]["local_bounds_mm"] == [0, 0, 26331, 3250]
    assert g["metrics"]["home_count"] == 53
    assert g["metrics"]["columns"] == 22 and g["metrics"]["compartments"] == 110
    assert not waiting_clearances(g) and not g["waiting_evaluation"]["conflicts"]
    assert not g["model"]["benches"] and g["model"]["changing_zone"] is None
    assert g["front_parameters"] == vars(sensitivity_parameters())
    assert sum(v["value"] for v in g["dimension_chains"]["transverse_cabinet_zone"]) == 3250
    assert g["metrics"]["north_strip_margin_mm"] == 10


def test_spatial_changes_are_real_and_not_new_grouping(cases):
    a, b, c = [x["geometry"] for x in cases[:3]]
    assert a["metrics"]["rotated_home_count"] == 6
    assert b["metrics"]["rotated_home_count"] == c["metrics"]["rotated_home_count"] == 34
    assert a["model"]["homes"] != b["model"]["homes"]
    assert a["inventory"]["cabinet_units"] != c["inventory"]["cabinet_units"]
    assert c["metrics"]["cabinet_run_length_mm"] - b["metrics"]["cabinet_run_length_mm"] == 1200
    for shift in (1, 2):
        plans = [[s["actions"] for s in g["snapshots"] if s["shift"] == shift] for g in (a, b, c)]
        assert plans[0] == plans[1] == plans[2]


@pytest.mark.parametrize("i", range(3))
@pytest.mark.parametrize("shift", (1, 2))
def test_complete_53_user_service_both_shifts(cases, i, shift):
    c = cases[i]
    g = c["geometry"]
    flow = c["shifts"][shift - 1]
    assert flow["status"] == PASS
    assert flow["initial_service_occupancy"] == flow["completed_users"] == 53
    assert len(set(flow["served_person_ids"])) == len(set(flow["completed_person_ids"])) == 53
    assert not flow["remaining_inside"] and not flow["not_entered_people"]
    assert len(flow["completed_batches"]) == flow["expected_batches"] == 14
    assert all(e["proof"]["status"] == PASS for e in flow["events"])
    assert all(
        e["inside_people"] + e["departed_people"] + e["not_entered_people"] == 53
        for e in flow["events"]
    )
    first = next(e for e in flow["events"] if e["operation"] == "TO_PERSONAL_LOCKER")
    assert first["inside_people"] == 53
    operations = [e for e in flow["events"] if e["operation"] == "PARALLEL_STANDING_CHANGE"]
    assert sum(len(e["active_people"]) for e in operations) == 53
    assert all(
        e["proof"]["cabinet_doors"] == "CLOSED_AFTER_REVIEW_REQUIRED_LOCKER_PHASE"
        for e in operations
    )
    assert flow["full_shift_seconds"] == pytest.approx(
        sum(flow["duration_by_operation_seconds"].values())
    )
    assert all(
        s["evaluation"]["status"] == "STATIC_TEMPLATE_VERIFIED_UNDER_HYPOTHESES"
        for s in g["snapshots"]
    )


@pytest.mark.parametrize("i", range(3))
@pytest.mark.parametrize("shift", (1, 2))
def test_actual_position_replay_preserves_all_other_occupants(cases, i, shift):
    current = {}
    exited = set()
    for event in cases[i]["shifts"][shift - 1]["events"]:
        p = event["proof"]
        assert {v["id"]: v for v in p["people_before"]} == current
        if event["operation"] == "ENTER_PORTAL":
            current[p["person_id"]] = p["interior_person"]
        elif event["operation"] in {
            "REACH_WAITING_POSITION",
            "TO_PERSONAL_LOCKER",
            "TO_PACKAGING_PORTAL",
        }:
            assert current[p["person_id"]] == p["source"]
            current[p["person_id"]] = p["target"]
        elif event["operation"] == "EXIT_PORTAL":
            del current[p["person_id"]]
            exited.add(p["person_id"])
        assert not set(current) & exited
    assert not current and len(exited) == 53


@pytest.mark.parametrize("i", range(3))
def test_original_1500mm_portals_and_1200mm_aisles(cases, i):
    c = cases[i]
    g = c["geometry"]
    assert [p["segment_mm"] for p in g["room"]["portals"]] == [
        [[26331, 875], [26331, 2375]],
        [[12415, 0], [13915, 0]],
    ]
    assert g["parameters"]["aisle_mm"] == 1200
    for flow in c["shifts"]:
        crossings = [
            e["proof"] for e in flow["events"] if e["operation"] in {"ENTER_PORTAL", "EXIT_PORTAL"}
        ]
        assert len(crossings) == 106 and all(p["status"] == PASS for p in crossings)
        assert all(
            p["original_segment_mm"] in [q["segment_mm"] for q in g["room"]["portals"]]
            for p in crossings
        )
    assert len(c["original_access_readbacks"]) == 2


@pytest.mark.parametrize("i", range(3))
def test_every_rotated_person_has_two_checked_yaws(cases, i):
    c = cases[i]
    g = c["geometry"]
    for flow in c["shifts"]:
        rotated_moves = [e["proof"] for e in flow["events"] if e["proof"].get("yaw_turn_count")]
        assert len(rotated_moves) == 2 * g["metrics"]["rotated_home_count"]
        for p in rotated_moves:
            assert len(p["legs"]) == 3
            turn = next(v for v in p["legs"] if v["operation"] == "YAW_90_IN_EXISTING_AISLE")
            assert turn["bounding_square_side_mm"] == 792
            assert turn["original_body_mm"] == [450, 650] and turn["rotated_body_mm"] == [650, 450]
            assert turn["status"] == PASS and not turn["conflicts"]


def test_original_47_home_template_not_reclassified(cases):
    old = cases[3]
    assert old["geometry"]["metrics"]["home_count"] == 47
    assert all(s["status"] == "BLOCKED" and s["completed_users"] == 0 for s in old["shifts"])
    assert old["geometry"]["parameters"]["end_clearance_mm"] == 100


def test_finish_sensitivity_retains_failure_not_global_infeasibility(cases):
    c = cases[4]
    g = c["geometry"]
    assert g["metrics"]["north_strip_margin_mm"] == -10
    assert any(
        q["reason"] == "OUTSIDE_FINISHED_ROOM" and q["north_boundary_deficit_mm"] == 10
        for q in g["rejected_home_probes"]
    )
    assert g["metrics"]["home_count"] < 53
    assert all(s["status"] == "BLOCKED" and s["full_shift_seconds"] is None for s in c["shifts"])
    assert g["dimension_chains"]["minimum_unrotated_north_row_building_depth_mm"] == 3460


def _move_fixture(cases):
    g = copy.deepcopy(cases[0]["geometry"])
    s = g["snapshots"][0]
    current = {o["id"]: copy.deepcopy(o) for o in s["home_people"]}
    key = next(k for k, o in current.items() if o["bounds_mm"][2] - o["bounds_mm"][0] == 650)
    target = copy.deepcopy(s["people"][0])
    # Use this person's actual assigned operator geometry.
    assignment = next(a for a in g["inventory"]["person_assignments"] if a["person_id"] == key)
    cell = next(
        c for c in g["inventory"]["compartments"] if c["id"] == assignment["compartment_ids"][0]
    )
    proof = group_proof(
        g,
        1,
        [dict(person_id=key, compartment_id=cell["id"], column_id=cell["column_id"])],
        sensitivity_parameters().standing(),
        "TEST",
    )
    target = next(p for p in proof["people"] if p["id"] == key)
    return g, s, current, key, target


def test_yaw_detects_collision_outside_endpoint_poses(cases):
    g, s, current, key, target = _move_fixture(cases)
    x, _ = center(current[key])
    y = s["branch_y"]
    # Corner is outside both 450x650 / 650x450 endpoint rectangles.
    box = [x + 350, y + 350, x + 370, y + 370]
    g["inventory"]["cabinet_units"].append(
        dict(id="YAW_CORNER_OBSTACLE", bounds_mm=box, volumes_mm=[prism(box, 0, 1800)])
    )
    before = copy.deepcopy(current)
    p = relayout_transfer(current, target, g, s, exited=set())
    assert p["status"] != "VERIFIED_UNDER_HYPOTHESES" and current == before
    assert any(
        e.get("component") == "YAW_CORNER_OBSTACLE" and e["leg"] == "YAW_90_IN_EXISTING_AISLE"
        for e in p["conflicts"]
    )


def test_rotated_motion_cannot_hide_missing_occupant(cases):
    g, s, current, key, target = _move_fixture(cases)
    del current[next(k for k in current if k != key)]
    with pytest.raises(ValueError, match="COMPLETE_53"):
        relayout_transfer(current, target, g, s, exited=set())


def test_body_shrinking_rejected(cases):
    g, s, current, key, target = _move_fixture(cases)
    current[key]["bounds_mm"][2] -= 1
    with pytest.raises(ValueError, match="SAME_BODY"):
        relayout_transfer(current, target, g, s, exited=set())


def test_waiting_gap_is_real_geometry(cases):
    g = copy.deepcopy(cases[0]["geometry"])
    a = g["model"]["homes"][0]["bounds_mm"]
    g["model"]["homes"][1]["bounds_mm"] = [a[2] + 99, a[1], a[2] + 549, a[3]]
    assert any(e["code"] == "WAITING_GAP_NOT_PRESERVED" for e in waiting_clearances(g))


def test_no_stale_waiting_pass(cases):
    g = copy.deepcopy(cases[0]["geometry"])
    g["waiting_snapshots"]["1"]["people"][0]["bounds_mm"][0] += 1
    with pytest.raises(ValueError, match="REFERENCE_MUST_MATCH"):
        simulate_relayout_shift(g, 1, None)


def test_missing_times_preserve_geometry_without_throughput_claim(cases):
    s = simulate_relayout_shift(cases[0]["geometry"], 1, None)
    assert s["completed_users"] == 53 and s["status"] == PASS
    assert s["full_shift_seconds"] is None and all(
        e["duration_seconds"] is None for e in s["events"]
    )
    assert s["actual_throughput_satisfied"] == "INPUT_REQUIRED"


def test_corner_activity_needs_derived_125mm(cases):
    g = copy.deepcopy(cases[0]["geometry"])
    assert g["parameters"]["end_clearance_mm"] == 125
    assert g["dimension_chains"]["cabinet_end_activity_overhang_mm"] == 125
    g["model"]["branch_bend_x"] -= 25
    hp = H5Hypothesis(**g["parameters"])
    g["waiting_snapshots"] = {
        str(s): _snapshot(g["room"], g["inventory"], g["model"], hp, s, [], "ALL_WAITING")
        for s in (1, 2)
    }
    g["snapshots"] = [
        group_proof(g, s["shift"], s["actions"], sensitivity_parameters().standing(), s["id"])
        for s in g["snapshots"]
    ]
    s = simulate_relayout_shift(g, 2, None)
    assert s["status"] == "BLOCKED"
    assert s["blocker"]["operation"] == "PARALLEL_STANDING_CHANGE"
    assert any(
        e["code"] == "DRESSING_ACTIVITY_INTRUDES_NET_AISLE" for e in s["blocker"]["conflicts"]
    )


@pytest.mark.parametrize("i", range(3))
def test_sources_and_actual_approval_remain_input_required(cases, i):
    c = cases[i]
    assert (
        c["binding"]["reviewed_project_facts"]["CHANGING_LOCATION"]["value"]
        == "PERSONAL_CABINET_FRONT"
    )
    assert not c["binding"]["engineering_approval"]
    assert c["project_functional_status"] == "INPUT_REQUIRED"
    assert (
        c["source_type"] == "demo" and c["validity_status"] == "unverified" and c["requires_review"]
    )
    assert c["native_solves"] == 0 and not c["historical_records_changed"]


@pytest.mark.parametrize("bad", [b"", b"source_label=OWNER_CONFIRMED"])
def test_existing_project_fact_review_not_bypassed(sources, bad):
    with pytest.raises(ValueError):
        review_relayouts(sources[0], sources[1], bad)


@pytest.mark.parametrize("finish", [19, 101, True, 20.5])
def test_explicit_finish_range(sources, finish):
    c = sources[0]
    with pytest.raises(ValueError):
        relayout_geometry(
            c["groups"][0]["room"],
            c["demands"]["INTERNAL_PARTITION"],
            TEMPLATES[0],
            finish_mm=finish,
        )


def test_no_unapproved_template_or_changed_room(sources):
    c = copy.deepcopy(sources[0])
    r = c["groups"][0]["room"]
    d = c["demands"]["INTERNAL_PARTITION"]
    with pytest.raises(ValueError):
        relayout_geometry(r, d, "ARBITRARY")
    r["local_bounds_mm"][3] = 3440
    with pytest.raises(ValueError, match="FROZEN_H5"):
        relayout_geometry(r, d, TEMPLATES[0])


def test_invalid_time_input_and_no_bench_enforced(cases):
    with pytest.raises(ValueError):
        replace(RelayoutTiming(), yaw_seconds=0).checked()
    g = copy.deepcopy(cases[0]["geometry"])
    g["model"]["changing_zone"] = [1, 1, 2, 2]
    with pytest.raises(ValueError, match="NO_BENCH"):
        simulate_relayout_shift(g, 1, None)


def test_yaw_leg_pose_trace_is_continuous(cases):
    for event in cases[0]["shifts"][0]["events"]:
        p = event["proof"]
        if not p.get("yaw_turn_count"):
            continue
        current = {o["id"]: o for o in p["people_before"]}
        for leg in p["legs"]:
            assert {o["id"]: o for o in leg["people_before"]} == current
            assert leg["source"] == current[p["person_id"]]
            current[p["person_id"]] = leg["target"]
        assert current[p["person_id"]] == p["target"]


def test_same_height_body_volumes_cannot_be_falsified(cases):
    g, s, current, key, target = _move_fixture(cases)
    current[key]["volumes_mm"][0][5] = 100
    with pytest.raises(ValueError, match="FULL_HEIGHT_ACTUAL"):
        relayout_transfer(current, target, g, s, exited=set())


def test_full_scale_page_and_failure_figures_read_persisted_evidence(cases):
    import base64
    import gzip
    import re
    import xml.etree.ElementTree as ET

    from build_r11_r9_space_relayout_review import summarize

    from cold_storage.modules.layout.infrastructure.h5_space_relayout_page import page, space_svg

    data = {str(i): c for i, c in enumerate(cases)}
    report = page(data, [summarize(k, c) for k, c in data.items()])
    embedded = re.search(r"atob\('([^']+)'\)", report).group(1)
    saved = json.loads(gzip.decompress(base64.b64decode(embedded)))
    assert (
        saved["cases"]["0"]["geometry"]["model"]["homes"] == cases[0]["geometry"]["model"]["homes"]
    )
    for c in cases:
        svg = space_svg(c)
        ET.fromstring(svg)
        assert "26331mm" in svg and "INPUT_REQUIRED" in svg
        assert svg.count("<title>本位") == c["geometry"]["metrics"]["home_count"]
    assert "650×450" in report and "连续90°" in report
