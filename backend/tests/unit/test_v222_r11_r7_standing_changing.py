"""Reviewed no-bench facts, full rosters, real conflicts and concurrent timing."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.standing_changing_review import (
    bind_standing_project,
    comparison_cases,
    review_standing,
)
from cold_storage.modules.layout.domain.changing_operation_motion import PASS
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis
from cold_storage.modules.layout.domain.standing_changing_layout import StandingParameters
from cold_storage.modules.layout.domain.standing_changing_operation import (
    StandingTiming,
    activity_proof,
    simulate_shift,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("R11_R7_NATIVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", forbidden)


@pytest.fixture(scope="module")
def source():
    return (ROOT / "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt").read_bytes()


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
def cases(catalog, source):
    return list(comparison_cases(catalog, source).values())


def test_reviewed_scope_and_zero_are_not_missing(catalog, source):
    b = bind_standing_project(catalog, source)
    facts = b["reviewed_project_facts"]
    assert facts["BENCH_COUNT"]["value"] == 0
    assert facts["CHANGING_POSTURE"]["value"] == "STANDING"
    assert all(
        f["project_scope_id"] == b["project_scope_id"] and f["reference"] for f in facts.values()
    )
    assert all(f["source_label"] == "OWNER_CONFIRMED" for f in facts.values())
    assert b["design_basis"]["simultaneous_room_users"] == 53
    assert not any(m.startswith("benches_") for m in b["missing_inputs"])
    assert b["project_functional_status"] == "INPUT_REQUIRED"


@pytest.mark.parametrize(
    "source", [b"", b"BENCH_COUNT=0", {"status": "APPROVED", "source_label": "OWNER_CONFIRMED"}]
)
def test_labels_and_unreviewed_text_cannot_bind(catalog, source):
    with pytest.raises(ValueError):
        bind_standing_project(catalog, source)


@pytest.mark.parametrize("field", ["project_scope_id", "project_facts", "design_basis", "groups"])
def test_modified_historical_catalog_rejected(catalog, source, field):
    c = copy.deepcopy(catalog)
    c[field] = "forged"
    with pytest.raises(ValueError):
        bind_standing_project(c, source)


def test_geometry_has_no_seats_station_or_bench_and_original_portals(cases):
    g = cases[0]["geometry"]
    assert g["metrics"]["columns"] == 22 and g["metrics"]["compartments"] == 110
    assert g["metrics"]["bench_count"] == g["metrics"]["seat_count"] == 0
    assert g["model"]["benches"] == [] and g["model"]["changing_zone"] is None
    assert g["metrics"]["home_count"] == 53
    assert all(p["pose"] == "STANDING" for s in g["snapshots"] for p in s["people"])
    assert [p["segment_mm"] for p in g["room"]["portals"]] == [
        [[26331, 875], [26331, 2375]],
        [[12415, 0], [13915, 0]],
    ]
    assert all(p["clear_width_mm"] == 1500 for p in g["room"]["portals"])
    assert g["metrics"]["reserved_aisle_mm"] == 1200


def test_both_full_shifts_all_batches_and_no_seated_operations(cases):
    for s in cases[0]["shifts"]:
        assert s["status"] == PASS
        assert s["initial_service_occupancy"] == s["completed_users"] == 53
        assert len(s["completed_batches"]) == 15 and s["completed_batch_boundaries"] == 14
        assert not s["remaining_inside"] and not s["not_entered_people"]
        assert len(set(s["completed_person_ids"])) == len(s["served_person_ids"]) == 53
        assert all(e["accounted_users"] == 53 for e in s["events"])
        assert all(
            e["inside_people"] + e["departed_people"] + e["not_entered_people"] == 53
            for e in s["events"]
        )
        assert not any(
            any(k in e["operation"].split("_") for k in ("BENCH", "SEATED", "SIT", "RISE"))
            for e in s["events"]
        )
        assert s["entry"]["final_inside"] == 53
        assert all(len(e["proof"]["people_before"]) == e["inside_people"] for e in s["events"])


def test_parallel_time_is_wall_duration_not_sum_of_person_times(cases):
    for s in cases[0]["shifts"]:
        phases = [e for e in s["events"] if e["operation"] == "PARALLEL_STANDING_CHANGE"]
        assert len(phases) == 15 and sum(len(e["active_people"]) for e in phases) == 53
        assert any(len(e["active_people"]) == 4 for e in phases)
        assert all(
            e["duration_seconds"] == 90
            and e["end_seconds"] - e["start_seconds"] == pytest.approx(90)
            for e in phases
        )
        assert s["duration_by_operation_seconds"]["PARALLEL_STANDING_CHANGE"] == 15 * 90
        assert s["duration_by_operation_seconds"]["PARALLEL_LOCKER_USE_AND_CLOSE"] == 15 * 20
        assert sum(e["duration_seconds"] for e in s["events"]) == pytest.approx(
            s["full_shift_seconds"]
        )
        assert s["movement_parallelism"] == 1  # No unproved simultaneous corridor traffic.


def test_every_person_has_locker_change_exit_order_and_real_route(cases):
    for s in cases[0]["shifts"]:
        for key in s["completed_person_ids"]:
            ops = [e["operation"] for e in s["events"] if key in e["active_people"]]
            assert ops.index("TO_PERSONAL_LOCKER") < ops.index("PARALLEL_LOCKER_USE_AND_CLOSE")
            assert ops.index("PARALLEL_LOCKER_USE_AND_CLOSE") < ops.index(
                "PARALLEL_STANDING_CHANGE"
            )
            assert ops.index("PARALLEL_STANDING_CHANGE") < ops.index("EXIT_PORTAL")
            lengths = [
                e["proof"].get("length_mm", 0)
                for e in s["events"]
                if e["proof"].get("person_id") == key
            ]
            assert sum(lengths) == s["personnel_route_mm"][key] > 0
        for e in s["events"]:
            p = e["proof"]
            if p.get("points_mm"):
                assert p["length_mm"] == sum(
                    abs(a[0] - b[0]) + abs(a[1] - b[1])
                    for a, b in zip(p["points_mm"], p["points_mm"][1:], strict=False)
                )


def test_front_parallel_conflict_is_preserved_and_one_at_a_time_is_conditional(cases):
    for s in cases[1]["shifts"]:
        assert s["completed_users"] == 0 and s["full_shift_seconds"] is None
        assert s["blocker"]["operation"] == "PARALLEL_STANDING_CHANGE"
        assert any(c["code"] == "SWEPT_BODY_COLLISION" for c in s["blocker"]["conflicts"])
        assert len(s["remaining_inside"]) == 53
    assert all(s["completed_users"] == 53 for s in cases[2]["shifts"])
    assert all(s["actual_throughput_satisfied"] == "INPUT_REQUIRED" for s in cases[2]["shifts"])


def test_human_space_sensitivity_does_not_drop_people(cases):
    for index in (5, 6):
        for s in cases[index]["shifts"]:
            assert s["status"] == "BLOCKED" and s["completed_users"] == 0
            assert s["full_shift_seconds"] is None
    assert cases[6]["geometry"]["metrics"]["home_count"] == 47
    assert cases[6]["geometry"]["demand"]["simultaneous_room_users"] == 53
    # Passing the body-only boundary is deliberately not an ergonomic result.
    assert all(s["status"] == PASS for s in cases[7]["shifts"])
    assert cases[7]["project_functional_status"] == "INPUT_REQUIRED"


def test_concurrency_changes_action_time_not_walking_distances(cases):
    for shift in (0, 1):
        a, d, e = [cases[i]["shifts"][shift] for i in (0, 3, 4)]
        assert d["full_shift_seconds"] > a["full_shift_seconds"] > e["full_shift_seconds"]
        assert d["total_route_mm"] == a["total_route_mm"] == e["total_route_mm"]


def test_missing_time_cannot_produce_duration(cases):
    s = simulate_shift(cases[0]["geometry"], 1, StandingParameters(), None)
    assert s["completed_users"] == 53 and s["full_shift_seconds"] is None
    assert all(e["duration_seconds"] is None and e["start_seconds"] is None for e in s["events"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("front_concurrency", 0),
        ("front_concurrency", 12),
        ("person_width_mm", True),
        ("activity_width_mm", 399),
        ("activity_depth_mm", 599),
        ("mode", "APPROVED"),
        ("person_gap_mm", -1),
        ("activity_height_mm", 1700),
    ],
)
def test_invalid_hypotheses_rejected(field, value):
    with pytest.raises(ValueError):
        replace(StandingParameters(), **{field: value}).checked()


@pytest.mark.parametrize("value", [0, -1, True, 2.5, 3601])
def test_invalid_time_rejected(value):
    with pytest.raises(ValueError):
        StandingTiming(changing_seconds=value).checked()


def test_zero_bench_does_not_rewrite_old_r5_policy():
    with pytest.raises(ValueError):
        H5Hypothesis(bench_count=0).checked()
    H5Hypothesis().checked()


@pytest.mark.parametrize("index", [0, 14, 15, 29])
def test_cached_static_pass_cannot_hide_modified_geometry(cases, index):
    g = copy.deepcopy(cases[0]["geometry"])
    g["snapshots"][index]["people"].pop()
    assert not g["snapshots"][index]["evaluation"]["conflicts"]
    s = simulate_shift(g, 1 if index < 15 else 2, StandingParameters(), StandingTiming())
    assert s["blocker"]["operation"] == "STATIC_TEMPLATE"
    assert not s["events"] and s["completed_users"] == 0


def test_original_door_and_aisle_guards_still_reject(catalog, source):
    c = review_standing(catalog, source, replace(StandingParameters(), room_door_intrusion_mm=200))
    assert all(s["blocker"]["operation"] == "STATIC_TEMPLATE" for s in c["shifts"])
    assert any(
        v["code"] == "ACTUAL_ROOM_DOOR_SWING_MUST_BE_RESOLVED_BEFORE_CLEAR_PASSAGE"
        for v in c["shifts"][0]["blocker"]["conflicts"]
    )


def test_activity_on_aisle_and_waiting_person_collision_rejected(cases):
    g = cases[0]["geometry"]
    e = next(
        e for e in cases[0]["shifts"][0]["events"] if e["operation"] == "PARALLEL_STANDING_CHANGE"
    )
    current = {o["id"]: copy.deepcopy(o) for o in e["proof"]["people_before"]}
    key = e["active_people"][0]
    current[key]["bounds_mm"][1:4:2] = [1700, 2300]
    p = activity_proof(g, g["snapshots"][0], current, e["active_people"], StandingParameters())
    assert any(c["code"] == "DRESSING_ACTIVITY_INTRUDES_NET_AISLE" for c in p["conflicts"])


def test_deterministic_binding_and_simulation(catalog, source, cases):
    assert review_standing(catalog, source, StandingParameters(), StandingTiming()) == cases[0]


def test_last_person_exit_failure_does_not_forge_complete_shift(cases, monkeypatch):
    from cold_storage.modules.layout.domain import standing_changing_operation as module

    original = module.transfer

    def late_block(current, target, result, snapshot, **kwargs):
        if len(kwargs.get("exited", set())) == 52 and target["role"] == "PORTAL_TRANSIT":
            return dict(
                status="CONFIGURATION_NOT_FIT",
                person_id=target["id"],
                conflicts=[dict(code="INJECTED_LAST_EXIT_OBSTRUCTION")],
            )
        return original(current, target, result, snapshot, **kwargs)

    monkeypatch.setattr(module, "transfer", late_block)
    s = simulate_shift(cases[0]["geometry"], 1, StandingParameters(), StandingTiming())
    assert s["completed_users"] == 52 and len(s["remaining_inside"]) == 1
    assert len(s["served_person_ids"]) == 53
    assert s["full_shift_seconds"] is None and s["status"] == "BLOCKED"
    assert s["events"][-1]["end_seconds"] is None


def test_failed_final_entry_keeps_actual_inside_people_without_accepting_baseline(
    cases, monkeypatch
):
    from cold_storage.modules.layout.domain import standing_changing_operation as module

    entry = copy.deepcopy(cases[0]["shifts"][0]["entry"])
    entry["status"] = "BLOCKED"
    entry["moves"][-1].update(
        status="CONFIGURATION_NOT_FIT", conflicts=[dict(code="INJECTED_TARGET_BLOCK")]
    )
    monkeypatch.setattr(module, "portal_audit", lambda *args, **kwargs: entry)
    s = simulate_shift(cases[0]["geometry"], 1, StandingParameters(), StandingTiming())
    assert len(s["remaining_inside"]) == 53 and s["completed_users"] == 0
    assert s["initial_service_occupancy"] == 0 and not s["service_started"]
    assert s["full_shift_seconds"] is None


@pytest.mark.parametrize(
    "timing", [StandingTiming(changing_seconds=60), StandingTiming(changing_seconds=180)]
)
def test_condition_times_change_only_verified_group_durations(cases, timing):
    old = cases[0]["shifts"][0]
    new = simulate_shift(cases[0]["geometry"], 1, StandingParameters(), timing)
    assert new["total_route_mm"] == old["total_route_mm"]
    assert new["completed_users"] == 53
    assert new["full_shift_seconds"] - old["full_shift_seconds"] == pytest.approx(
        15 * (timing.changing_seconds - 90)
    )


def test_activity_must_not_discard_or_duplicate_present_people(cases):
    g = cases[0]["geometry"]
    s = g["snapshots"][0]
    people = {o["id"]: o for o in s["people"]}
    key = next(iter(people))
    for keys in ([key, key], ["unregistered"]):
        with pytest.raises(ValueError):
            activity_proof(g, s, people, keys, StandingParameters())


def test_rendered_page_exposes_confirmed_and_hypothetical_boundaries(cases):
    from cold_storage.modules.layout.infrastructure.standing_changing_page import page, plan_svg

    rendered = page({"A": cases[0]})
    assert "CONFIRMED_PROJECT_BASIS" in rendered and "INPUT_REQUIRED" in rendered
    assert "__DATA__" not in rendered
    svg = plan_svg(cases[0])
    assert "26331 × 3250" in svg and "0座凳" in svg
    assert "条件" in rendered and "未批准" in rendered
