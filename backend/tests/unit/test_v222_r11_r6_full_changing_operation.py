"""All 28 transitions, real seat envelopes, partial protocols and honest timing."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.full_changing_operation_review import review_operation
from cold_storage.modules.layout.application.practical_changing_review import review_h5
from cold_storage.modules.layout.domain.changing_operation_motion import (
    PASS,
    portal_crossing,
    seat_pose,
    transfer,
)
from cold_storage.modules.layout.domain.changing_room_motion import prism
from cold_storage.modules.layout.domain.full_changing_operation import (
    OperationHypothesis,
    TimingHypothesis,
    activity_check,
    audit_transition,
    evaluate_operation,
    timing_bounds,
)
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("R11_R6_NATIVE_FORBIDDEN")

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
def result(catalog):
    return review_operation(catalog, H5Hypothesis(), OperationHypothesis(), TimingHypothesis())


def test_all_30_batches_28_transitions_and_106_distinct_assignments(result):
    g, o = result["geometry"], result["operation"]
    assert g["metrics"]["columns"] == 22 and g["metrics"]["compartments"] == 110
    assert o["expected_transitions"] == o["verified_transitions"] == 28
    for shift in (1, 2):
        ss = [s for s in g["snapshots"] if s["shift"] == shift]
        tt = [t for t in o["transitions"] if t["shift"] == shift]
        assert len(ss) == 15 and len(tt) == 14
        assert len({a["person_id"] for s in ss for a in s["actions"]}) == 53
        assert [(t["from_batch"], t["to_batch"]) for t in tt] == [
            (a["id"], b["id"]) for a, b in zip(ss, ss[1:], strict=False)
        ]
        assert all(t["endpoint_all_53_match"] for t in tt)
        assert all(
            m["accounted_people"] == m["inside_people"] == 53 for t in tt for m in t["moves"]
        )
    assert any(m["pose_checks"] for t in o["transitions"] for m in t["moves"])


def test_final_pair_is_checked_not_first_pair_only(result):
    g = copy.deepcopy(result["geometry"])
    s = g["snapshots"][14]
    s["people"][0]["bounds_mm"] = [0, 0, 400, 600]
    a = audit_transition(g, g["snapshots"][13], s, OperationHypothesis())
    assert a["status"] == "NOT_EVALUATED"


def test_protocol_block_is_not_upgraded_from_28_valid_pairs(result):
    o = result["operation"]
    for s in o["full_shifts"]:
        assert s["status"] == "BLOCKED"
        assert s["complete_service_users"] == 3
        assert s["remaining_inside"] == 53
        assert s["full_shift_seconds"] is None
        assert s["blocker"]["operation"] == "VACATE_SERVICE_AREA"
        assert len(s["unvisited_people"]) == 50
        assert s["events"][-1]["end_seconds"] is None
        assert any(e["operation"] == "LOCKER_TO_CHANGING_ZONE" for e in s["events"])
        assert any(e["operation"] == "CHANGING_TO_BENCH_AND_SIT" for e in s["events"])
        assert any(e["operation"] == "RISE_AND_RETURN" for e in s["events"])
    assert result["project_functional_status"] == "INPUT_REQUIRED"
    assert not result["engineering_approval"]


def test_entry_and_exit_separate_not_fake_complete_service(result):
    for a in result["operation"]["portal_sequences"]:
        assert a["status"] == PASS and a["completed_people"] == 53
        assert a["scope"] == "INDEPENDENT_PORTAL_SEQUENCE"
        assert a["accounted_people"] == 53
    assert all(
        s["departure"] == "NOT_EVALUATED_SERVICE_SEQUENCE_INCOMPLETE"
        for s in result["operation"]["full_shifts"]
    )


def test_sit_rise_keep_bench_in_collision_checks(result):
    g = result["geometry"]
    p = H5Hypothesis()
    seat = next(s for s in g["snapshots"][0]["home_people"] if s["pose"] == "SEATED")
    bench = next(b for b in g["model"]["benches"] if b["id"] == seat["bench_id"])
    bodies = [*g["inventory"]["cabinet_units"], *g["model"]["benches"]]
    proof = seat_pose(seat, bench, [], bodies, g["model"]["clear"], p, 50)
    assert proof["status"] == PASS
    # An actual leg obstruction in front of the bench must fail; never remove bench.
    b = proof["standing"]["bounds_mm"]
    bodies.append(dict(id="leg-block", volumes_mm=[prism(b, 0, 100)]))
    assert (
        seat_pose(seat, bench, [], bodies, g["model"]["clear"], p, 50)["status"]
        == "CONFIGURATION_NOT_FIT"
    )
    bodies.pop()
    # A person in the conservative sit/stand upper-body sweep must also fail.
    other = dict(id="other-user", volumes_mm=proof["swept_volumes_mm"])
    assert (
        seat_pose(seat, bench, [other], bodies, g["model"]["clear"], p, 50)["status"]
        == "CONFIGURATION_NOT_FIT"
    )


@pytest.mark.parametrize("margin", [10, 25, 50, 100])
def test_static_pass_does_not_prove_activity_clearance(result, margin):
    g = result["geometry"]
    before = copy.deepcopy(g["snapshots"][0]["people"])
    assert not activity_check(g, g["snapshots"][0], 0)["conflicts"]
    a = activity_check(g, g["snapshots"][0], margin)
    assert a["status"] == "CONFIGURATION_NOT_FIT"
    assert g["snapshots"][0]["people"] == before
    assert a["actual_human_motion"] == "INPUT_REQUIRED"


def test_20mm_gap_does_not_allow_25mm_per_side_motion(result):
    g = result["geometry"]
    a = activity_check(g, g["snapshots"][0], 25)
    assert any(c["code"] == "ACTIVITY_ENVELOPES_OVERLAP" for c in a["conflicts"])


def test_no_reviewed_time_means_no_duration(result):
    a = evaluate_operation(result["geometry"], OperationHypothesis())
    assert a["timing"]["status"] == "INPUT_REQUIRED"
    assert all(
        s["prefix_seconds"] is None and s["full_shift_seconds"] is None for s in a["full_shifts"]
    )
    assert all(e["duration_seconds"] is None for s in a["full_shifts"] for e in s["events"])


def test_time_is_prefix_and_lower_bound_not_throughput(result):
    o = result["operation"]
    t = o["timing"]
    assert t["lower_bound_seconds"] == 53 * 90
    assert t["bottleneck"] == "changing"
    assert t["complete_shift_seconds"] is None
    assert t["throughput_satisfied"] == "INPUT_REQUIRED"
    for s in o["full_shifts"]:
        passed = [e for e in s["events"] if e["status"] == PASS]
        assert sum(e["duration_seconds"] for e in passed) == pytest.approx(s["prefix_seconds"])
        assert passed[0]["operation"] == "ENTRY_TO_HOME"


@pytest.mark.parametrize("field", list(TimingHypothesis.__dataclass_fields__))
@pytest.mark.parametrize("value", [0, -1, True, 1.2])
def test_bad_time_input_rejected(field, value):
    with pytest.raises(ValueError):
        replace(TimingHypothesis(), **{field: value}).checked()


def test_explicit_time_changes_lower_bound_not_geometry(result):
    g = result["geometry"]
    before = copy.deepcopy(g)
    t = timing_bounds(g, replace(TimingHypothesis(), changing_seconds=180))
    assert t["lower_bound_seconds"] == 9540
    assert g == before


def test_dropped_person_cannot_make_route_pass(result):
    g = result["geometry"]
    s = g["snapshots"][0]
    current = {v["id"]: copy.deepcopy(v) for v in s["people"]}
    target = s["home_people"][0]
    current.pop(s["people"][-1]["id"])
    with pytest.raises(ValueError, match="53_PERSON"):
        transfer(current, target, g, s, seat_allowance_mm=50)


def test_changed_body_dimensions_rejected(result):
    g = result["geometry"]
    s = g["snapshots"][0]
    current = {v["id"]: copy.deepcopy(v) for v in s["people"]}
    target = copy.deepcopy(s["home_people"][0])
    target["bounds_mm"][2] += 10
    with pytest.raises(ValueError, match="DIMENSIONS"):
        transfer(current, target, g, s, seat_allowance_mm=50)


def test_real_portals_and_door_conflicts(result):
    g = copy.deepcopy(result["geometry"])
    person = g["snapshots"][0]["people"][0]
    for portal in g["room"]["portals"]:
        assert portal_crossing(person, portal, g, [], entering=True)["status"] == PASS
    fake = copy.deepcopy(g["room"]["portals"][0])
    fake["segment_mm"][0][1] += 1
    with pytest.raises(ValueError, match="ORIGINAL"):
        portal_crossing(person, fake, g, [], entering=True)
    g["parameters"]["room_door_intrusion_mm"] = 300
    assert (
        portal_crossing(person, g["room"]["portals"][0], g, [], entering=False)["status"]
        == "CONFIGURATION_NOT_FIT"
    )


@pytest.mark.parametrize(
    "changes",
    [
        dict(front_concurrency=2),
        dict(front_concurrency=6),
        dict(bench_count=1),
        dict(bench_count=3),
        dict(changing_operation_width_mm=1000, changing_operation_depth_mm=1000),
        dict(person_width_mm=450, person_depth_mm=650, person_gap_mm=100),
        dict(person_gap_mm=100),
    ],
)
def test_sensitivity_never_reduces_required_roster(catalog, changes):
    r = review_operation(
        catalog, replace(H5Hypothesis(), **changes), OperationHypothesis(), TimingHypothesis()
    )
    assert r["geometry"]["demand"]["simultaneous_room_users"] == 53
    assert r["geometry"]["metrics"]["columns"] == 22
    assert r["project_functional_status"] == "INPUT_REQUIRED"
    assert all(s["full_shift_seconds"] is None for s in r["operation"]["full_shifts"])


def test_forged_source_rejected_and_originals_unchanged(catalog, result):
    bad = copy.deepcopy(catalog)
    bad["groups"][0]["handoff"] = 99
    with pytest.raises(ValueError, match="SOURCE_MISMATCH"):
        review_operation(bad, H5Hypothesis(), OperationHypothesis(), None)
    fresh = review_h5(catalog, "INTERNAL_PARTITION", H5Hypothesis())
    assert fresh == result["geometry"]


def test_persisted_viewer_contains_all_pairs_and_no_approval(result):
    import base64
    import gzip
    import re

    from cold_storage.modules.layout.infrastructure.full_changing_operation_page import page

    html = page({"A": result})
    packed = re.search(r"const packed='([^']+)'", html).group(1)
    persisted = json.loads(gzip.decompress(base64.b64decode(packed)))
    assert len(persisted["A"]["operation"]["transitions"]) == 28
    assert "全部相邻批次转换" in html and "INPUT_REQUIRED" in html
    assert "完整使用时间线" in html and "坐起三维包络" in html
    assert "CONDITIONAL_FIT" not in html


def test_no_successful_state_update_after_collision(result):
    g = copy.deepcopy(result["geometry"])
    s = g["snapshots"][0]
    current = {v["id"]: copy.deepcopy(v) for v in s["people"]}
    target = copy.deepcopy(s["home_people"][0])
    blocker = next(v for k, v in current.items() if k != target["id"])
    blocker["bounds_mm"] = target["bounds_mm"][:]
    blocker["volumes_mm"] = target["volumes_mm"][:]
    before = copy.deepcopy(current)
    proof = transfer(current, target, g, s, seat_allowance_mm=50)
    assert proof["status"] == "CONFIGURATION_NOT_FIT"
    assert current == before


def test_scope_rejects_reduced_cells_or_opposed_layout(result):
    for field, value in [("columns", 21), ("compartments", 106)]:
        g = copy.deepcopy(result["geometry"])
        g["metrics"][field] = value
        with pytest.raises(ValueError, match="SCOPE"):
            evaluate_operation(g, OperationHypothesis())


def test_last_entrant_route_failure_is_not_53_person_success(result):
    from cold_storage.modules.layout.domain.full_changing_operation import portal_audit

    g = copy.deepcopy(result["geometry"])
    # First ID enters last. Its counterfeit target is inside a real cabinet.
    h = g["snapshots"][0]["home_people"][0]
    h["bounds_mm"] = [720, 40, 1120, 640]
    h["volumes_mm"] = [prism(h["bounds_mm"], 0, 1800)]
    a = portal_audit(g, 1, OperationHypothesis(), entering=True)
    assert a["status"] == "BLOCKED"
    assert a["completed_people"] == 52
    assert a["final_inside"] == 53  # crossed doorway, did not reach home
    assert a["moves"][-1]["status"] == "CONFIGURATION_NOT_FIT"


def test_no_seat_capacity_cannot_compute_fake_throughput(result):
    g = copy.deepcopy(result["geometry"])
    g["metrics"]["bench_seat_capacity"] = 0
    t = timing_bounds(g, TimingHypothesis())
    assert t["status"] == "CONFIGURATION_NOT_FIT"
    assert t["complete_shift_seconds"] is None
