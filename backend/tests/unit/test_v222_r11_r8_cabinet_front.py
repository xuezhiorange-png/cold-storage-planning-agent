"""Interleaved physical groups, full 53-user flow, door cycles and honest timing."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.cabinet_front_review import (
    bind_front_project,
    comparison_cases,
    review_front,
)
from cold_storage.modules.layout.domain.cabinet_front_operation import (
    FrontTiming,
    simulate_front_shift,
)
from cold_storage.modules.layout.domain.cabinet_front_schedule import FrontParameters
from cold_storage.modules.layout.domain.changing_operation_motion import PASS
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis, validate_use

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("R11_R8_NATIVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", forbidden)


@pytest.fixture(scope="module")
def sources():
    c = json.loads(
        (
            ROOT
            / "docs/previews/v2.2.2/r11-r4-multi-tier-locker-review-r1"
            / "project-and-room-catalog.json"
        ).read_bytes()
    )
    r7 = (ROOT / "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt").read_bytes()
    r8 = (ROOT / "docs/tasks/V2_2_2-r11-r8-reviewed-cabinet-front-facts.txt").read_bytes()
    return c, r7, r8


@pytest.fixture(scope="module")
def cases(sources):
    return list(comparison_cases(*sources).values())


def test_owner_location_bound_but_concurrency_and_hardware_not_approved(sources):
    b = bind_front_project(*sources)
    facts = b["reviewed_project_facts"]
    assert facts["CHANGING_LOCATION"]["value"] == "PERSONAL_CABINET_FRONT"
    assert facts["BENCH_COUNT"]["value"] == facts["SEPARATE_CHANGING_AREA_COUNT"]["value"] == 0
    assert all(
        f["source_label"] == "OWNER_CONFIRMED"
        and f["project_scope_id"] == b["project_scope_id"]
        and f["reference"]
        for f in facts.values()
    )
    assert b["r7_distributed_process"] == "HISTORICAL_COMPARISON_ONLY"
    assert b["project_functional_status"] == "INPUT_REQUIRED" and not b["engineering_approval"]
    assert "approved_cabinet_front_concurrency_and_waiting_protocol" in b["missing_inputs"]


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"CHANGING_LOCATION=PERSONAL_CABINET_FRONT",
        {"source_label": "OWNER_CONFIRMED", "status": "APPROVED"},
    ],
)
def test_source_labels_are_not_approval(sources, bad):
    c, r7, _ = sources
    with pytest.raises(ValueError):
        bind_front_project(c, r7, bad)


def test_old_source_and_scope_cannot_be_repurposed(sources):
    c, r7, r8 = sources
    with pytest.raises(ValueError):
        bind_front_project(c, r7, r7)
    with pytest.raises(ValueError):
        bind_front_project(c, b"changed", r8)
    c = copy.deepcopy(c)
    c["project_scope_id"] = "other"
    with pytest.raises(ValueError):
        bind_front_project(c, r7, r8)


@pytest.mark.parametrize("index", range(8))
def test_all_concurrencies_both_envelopes_complete_all_53(cases, index):
    c = cases[index]
    g = c["geometry"]
    assert g["metrics"]["columns"] == 22 and g["metrics"]["compartments"] == 110
    assert g["metrics"]["home_count"] == 53 and g["metrics"]["reserved_aisle_mm"] == 1200
    assert not g["model"]["benches"] and g["model"]["changing_zone"] is None
    for s in c["shifts"]:
        assert s["status"] == PASS and s["initial_service_occupancy"] == s["completed_users"] == 53
        assert (
            s["actual_peak_concurrency"]
            == s["requested_concurrency"]
            == g["front_parameters"]["requested_concurrency"]
        )
        assert (
            len(set(s["completed_person_ids"])) == 53
            and not s["remaining_inside"]
            and not s["not_entered_people"]
        )
        assert sum(int(n) * count for n, count in s["concurrency_histogram"].items()) == 53
        assert len(s["completed_batches"]) == s["expected_batches"]
        assert all(
            e["inside_people"] + e["departed_people"] + e["not_entered_people"] == 53
            for e in s["events"]
        )
        assert all(len(e["proof"]["people_before"]) == e["inside_people"] for e in s["events"])
    assert c["project_functional_status"] == "INPUT_REQUIRED"


def test_grouping_only_change_preserves_physical_geometry_and_portals(cases):
    inter, adj = cases[6]["geometry"], cases[8]["geometry"]
    assert inter["inventory"] == adj["inventory"] and inter["model"] == adj["model"]
    assert inter["room"] == adj["room"]
    assert [p["segment_mm"] for p in inter["room"]["portals"]] == [
        [[26331, 875], [26331, 2375]],
        [[12415, 0], [13915, 0]],
    ]
    assert all(p["clear_width_mm"] == 1500 for p in inter["room"]["portals"])


def test_each_group_is_physically_separated_and_fully_checked(cases):
    g = cases[6]["geometry"]
    columns = {c["id"]: c for c in g["inventory"]["vertical_columns"]}
    for s in g["snapshots"]:
        assert len({a["column_id"] for a in s["actions"]}) == len(s["actions"])
        positions = [columns[a["column_id"]]["bounds_mm"][0] for a in s["actions"]]
        assert all(abs(a - b) >= 600 for i, a in enumerate(positions) for b in positions[i + 1 :])
        assert (
            s["group_verified"]
            and not validate_use(
                g["room"], g["inventory"], g["model"], H5Hypothesis(**g["parameters"]), s
            )["conflicts"]
        )
        assert s["front_activity_evaluation"]["status"] == PASS
    # Contiguous negative control starts all53 and retains a real failed operation.
    for s in cases[8]["shifts"]:
        assert s["initial_service_occupancy"] == 53 and s["completed_users"] == 0
        assert s["blocker"]["operation"] == "PARALLEL_STANDING_CHANGE"
        assert any(e["operation"] == "OPEN_FOR_RETRIEVE" for e in s["events"])
        assert s["full_shift_seconds"] is None


def test_complete_two_opening_door_order_and_no_other_changing_zone(cases):
    c = cases[6]
    for s in c["shifts"]:
        for key in s["completed_person_ids"]:
            ops = [e["operation"] for e in s["events"] if key in e["active_people"]]
            required = [
                "TO_PERSONAL_LOCKER",
                "OPEN_FOR_RETRIEVE",
                "RETRIEVE_CLOTHES",
                "CLOSE_AFTER_RETRIEVE",
                "PARALLEL_STANDING_CHANGE",
                "OPEN_FOR_STORE",
                "STORE_CLOTHES",
                "CLOSE_AFTER_STORE",
                "TO_PACKAGING_PORTAL",
                "EXIT_PORTAL",
            ]
            assert [o for o in ops if o in required] == required
            assert not any(k in o for o in ops for k in ("BENCH", "SEATED", "DISTRIBUTED"))
        assert all(
            e["proof"]["doors"] for e in s["events"] if e["operation"].startswith("OPEN_FOR")
        )


def test_open_during_dressing_is_not_silently_accepted(cases):
    assert all(
        x["proof"]["status"] == "CONFIGURATION_NOT_FIT"
        for x in cases[6]["open_door_changing_sensitivity"]
    )
    assert any(
        c["code"] == "OPEN_DOOR_DRESSING_COLLISION"
        for x in cases[6]["open_door_changing_sensitivity"]
        for c in x["proof"]["conflicts"]
    )
    assert all(s["status"] == PASS for s in cases[6]["shifts"])


def test_wall_time_walk_parallel_actions_and_waiting_partition(cases):
    for s in cases[6]["shifts"]:
        assert sum(e["duration_seconds"] for e in s["events"]) == pytest.approx(
            s["full_shift_seconds"]
        )
        assert s["movement_parallelism"] == 1
        for v in s["personnel_time_and_route"].values():
            assert v["action_seconds"] == 142
            assert v["walking_seconds"] == pytest.approx(v["route_mm"] / 600)
            assert v["serial_waiting_seconds"] >= 0
            assert v["residence_seconds"] == pytest.approx(
                v["walking_seconds"] + v["action_seconds"] + v["serial_waiting_seconds"]
            )
        groups = len(s["completed_batches"])
        assert s["duration_by_operation_seconds"]["PARALLEL_STANDING_CHANGE"] == groups * 90
        assert s["duration_by_operation_seconds"]["OPEN_FOR_STORE"] == groups * 3
        assert s["duration_by_operation_seconds"]["STORE_CLOTHES"] == groups * 20
        for e in s["events"]:
            p = e["proof"]
            if p.get("points_mm"):
                assert p["length_mm"] == sum(
                    abs(a[0] - b[0]) + abs(a[1] - b[1])
                    for a, b in zip(p["points_mm"], p["points_mm"][1:], strict=False)
                )


def test_larger_space_or_cabinet_gap_failure_keeps_design_53(cases):
    for i in (9, 10, 11):
        c = cases[i]
        assert c["geometry"]["demand"]["simultaneous_room_users"] == 53
        assert c["geometry"]["room"]["local_bounds_mm"] == [0, 0, 26331, 3250]
        assert all(
            s["completed_users"] == 0 and s["full_shift_seconds"] is None for s in c["shifts"]
        )
    assert cases[9]["geometry"]["metrics"]["closed_door_front_depth_available_mm"] == 980
    assert cases[9]["geometry"]["metrics"]["activity_depth_required_mm"] == 1100
    assert cases[10]["geometry"]["metrics"]["home_count"] == 47
    assert cases[11]["geometry"]["metrics"]["home_count"] == 46


@pytest.mark.parametrize("index", (0, -1))
def test_stale_verified_flag_cannot_hide_modified_people(cases, index):
    g = copy.deepcopy(cases[6]["geometry"])
    g["snapshots"][index]["people"].pop()
    assert g["snapshots"][index]["group_verified"]
    s = simulate_front_shift(g, g["snapshots"][index]["shift"], FrontParameters(), FrontTiming())
    assert not s["events"] and s["completed_users"] == 0


def test_missing_time_cannot_invent_capacity(cases):
    s = simulate_front_shift(cases[6]["geometry"], 1, FrontParameters(), None)
    assert s["completed_users"] == 53 and s["full_shift_seconds"] is None
    assert all(e["end_seconds"] is None for e in s["events"])
    assert all(v["serial_waiting_seconds"] is None for v in s["personnel_time_and_route"].values())
    assert s["actual_throughput_satisfied"] == "INPUT_REQUIRED"


@pytest.mark.parametrize(
    "key,value",
    [
        ("person_width_mm", 399),
        ("person_depth_mm", 599),
        ("activity_width_mm", 399),
        ("requested_concurrency", 0),
        ("requested_concurrency", 12),
        ("columns_per_unit", 0),
        ("grouping", "APPROVED"),
        ("unit_gap_mm", -1),
        ("person_width_mm", True),
    ],
)
def test_invalid_or_smaller_hypothesis_rejected(key, value):
    with pytest.raises(ValueError):
        replace(FrontParameters(), **{key: value}).standing()


@pytest.mark.parametrize("value", [0, -1, True, 1.5, 3601])
def test_times_are_explicit_positive_hypotheses(value):
    with pytest.raises(ValueError):
        FrontTiming(open_seconds=value).checked()


def test_failed_last_exit_retains_person_and_incomplete_time(cases, monkeypatch):
    from cold_storage.modules.layout.domain import cabinet_front_operation as module

    original = module.transfer

    def blocked(current, target, result, snapshot, **kwargs):
        if len(kwargs.get("exited", set())) == 52 and target["role"] == "PORTAL_TRANSIT":
            return dict(
                status="CONFIGURATION_NOT_FIT",
                person_id=target["id"],
                conflicts=[dict(code="INJECTED_LAST_EXIT_BLOCK")],
            )
        return original(current, target, result, snapshot, **kwargs)

    monkeypatch.setattr(module, "transfer", blocked)
    s = simulate_front_shift(cases[6]["geometry"], 1, FrontParameters(), FrontTiming())
    assert s["completed_users"] == 52 and len(s["remaining_inside"]) == 1
    assert s["full_shift_seconds"] is None and len(s["served_person_ids"]) == 53


def test_same_input_reproduces_geometry_groups_and_trace(sources, cases):
    assert review_front(*sources, FrontParameters(), FrontTiming()) == cases[6]


def test_replay_every_position_waiting_users_do_not_teleport(cases):
    for s in cases[6]["shifts"]:
        current = {}
        for e in s["events"]:
            proof = e["proof"]
            assert {v["id"]: v for v in proof["people_before"]} == current
            if e["operation"] == "EXIT_PORTAL":
                del current[proof["person_id"]]
            elif "target" in proof:
                current[proof["person_id"]] = proof["target"]
            elif (
                e["operation"] == "ENTER_AND_REACH_WAITING_POSITION" and "interior_person" in proof
            ):
                current[proof["person_id"]] = proof["interior_person"]
        assert not current
        assert s["wall_walking_seconds"] + s["wall_parallel_action_seconds"] == pytest.approx(
            s["full_shift_seconds"]
        )


def test_rejected_storage_phase_cannot_be_completed_or_exit(cases, monkeypatch):
    from cold_storage.modules.layout.domain import cabinet_front_operation as module

    original = module.validate_live_locker_use
    calls = 0

    def reject_store(*args, **kwargs):
        nonlocal calls
        calls += 1
        return (
            original(*args, **kwargs)
            if calls != 2
            else [dict(code="INJECTED_STORAGE_DOOR_CONFLICT")]
        )

    monkeypatch.setattr(module, "validate_live_locker_use", reject_store)
    s = simulate_front_shift(cases[6]["geometry"], 1, FrontParameters(), FrontTiming())
    assert s["blocker"]["operation"] == "OPEN_FOR_STORE"
    assert not s["completed_person_ids"] and not s["served_person_ids"]
    assert len(s["remaining_inside"]) == 53 and s["full_shift_seconds"] is None


def test_drawings_include_failure_templates_without_inventing_flow(cases):
    from cold_storage.modules.layout.infrastructure.cabinet_front_page import (
        initial_proof,
        page,
        plan_svg,
    )

    for i, c in enumerate(cases):
        for shift in (1, 2):
            svg = plan_svg(c, shift)
            assert "26331 × 3250" in svg and "INPUT_REQUIRED" in svg
            if i >= 9:
                assert (
                    initial_proof(c, shift)["scope"] == "TEMPLATE_ONLY_NO_COMPLETE_FLOW_GENERATED"
                )
    rendered = page({"selected": cases[6]})
    assert "__DATA__" not in rendered and "本人柜前" in rendered
    assert "历史对照" in rendered and "INPUT_REQUIRED" in rendered


def test_current_room_door_intrusion_still_rejects(sources):
    r = review_front(
        *sources, replace(FrontParameters(), room_door_intrusion_mm=200), FrontTiming()
    )
    assert all(s["completed_users"] == 0 and not s["events"] for s in r["shifts"])
    assert any(
        c["code"] == "ACTUAL_ROOM_DOOR_SWING_MUST_BE_RESOLVED_BEFORE_CLEAR_PASSAGE"
        for c in r["geometry"]["waiting_evaluation"]["conflicts"]
    )
