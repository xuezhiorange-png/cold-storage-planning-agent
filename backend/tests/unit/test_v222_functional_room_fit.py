"""R11 diagnostics, always zero Native calls and no execution authorization."""

import json
import random
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.functional_room_review import sealed_file
from cold_storage.modules.layout.domain.functional_room_fit import (
    COMMON,
    REQUIRED,
    STATES,
    area,
    covered,
    evaluate_functional_room,
)
from cold_storage.modules.layout.infrastructure.functional_room_fit_examples import scenario
from cold_storage.modules.layout.infrastructure.functional_room_review_page import render_review

ROOT = Path(__file__).resolve().parents[3]
PREVIEW = ROOT / "docs/previews/v2.2.2/r11-functional-room-fit-r1"


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def denied(*a, **k):
        raise AssertionError("R11_NATIVE_SOLVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", denied)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", denied)


def evaluate(kind="SINGLE_SIDE", mutate=None):
    room, refs, w, b = scenario(kind)
    if mutate:
        mutate(room, refs, w, b)
    return evaluate_functional_room(room, refs, w, reviewed_basis=b)


@pytest.mark.parametrize("kind", ["SINGLE_SIDE", "DOUBLE_SIDE", "OFFICE", "COATING"])
def test_explicit_layouts_fit_conditionally_never_approve(kind):
    r = evaluate(kind)
    assert r["functional_status"] == "CONDITIONAL_FIT", r
    assert not r["engineering_approval"] and not r["modifies_p1"] and r["native_solves"] == 0
    assert set(r["state_results"]) == set(STATES)
    assert all(s["portal_reachable_aisle_count"] > 0 for s in r["state_results"].values())


def test_same_40_square_metres_does_not_prove_internal_use():
    r = evaluate("NARROW")
    assert r["p1_area_status"] == "AREA_SATISFIED"
    assert r["functional_status"] == "CONFIGURATION_NOT_FIT"
    assert r["no_fit_proof_scope"] == "SUPPLIED_CONFIGURATION_ONLY_NOT_GLOBAL_INFEASIBILITY"


@pytest.mark.parametrize("field", list(COMMON | REQUIRED["changing_room"]))
def test_each_missing_functional_input_stays_input_required(field):
    r = evaluate(mutate=lambda room, refs, w, b: refs.pop(field))
    assert r["functional_status"] == "INPUT_REQUIRED" and field in r["missing_inputs"]


@pytest.mark.parametrize("i", range(27))
def test_archived_geometry_area_and_function_are_three_independent_results(i):
    data = json.loads((PREVIEW / "review-data.json").read_text())
    row = data["room_evaluations"][i]
    room = deepcopy(row["room"])
    old = deepcopy(room)
    r = evaluate_functional_room(room)
    assert r["original_engineering_status"] == "EXISTING_STAGE_B_ELIGIBLE"
    assert r["p1_area_status"] == "AREA_SATISFIED"
    assert r["functional_status"] == "INPUT_REQUIRED" and r["missing_inputs"]
    assert room == old


def test_archived_nine_records_eight_rectangles_and_r9_separate():
    d = json.loads((PREVIEW / "review-data.json").read_text())
    assert d["original_record_count"] == 9 and d["physical_group_count"] == 8
    assert d["physical_groups"]["G01"] == ["P01", "P02"]
    assert len(d["historical_r9_reference"]) == 3
    assert all(
        r["evaluation"]["functional_status"] == "INPUT_REQUIRED"
        and not r["formal_pareto_comparison"]
        for r in d["historical_r9_reference"]
    )
    assert not d["owner_business_rules"]["historical_staffing_bound"]
    assert all(r["evaluation"]["input_facts"] == {} for r in d["room_evaluations"])


def test_caller_cannot_self_approve_fields_or_reuse_another_scope():
    room, refs, w, b = scenario()
    forged = {k: "OWNER_CONFIRMED" for k in refs}
    assert evaluate_functional_room(room, forged, w)["functional_status"] == "INPUT_REQUIRED"
    b = {k: replace(v, scope_id="OTHER_PROJECT") for k, v in b.items()}
    assert (
        evaluate_functional_room(room, refs, w, reviewed_basis=b)["functional_status"]
        == "INPUT_REQUIRED"
    )


@pytest.mark.parametrize(
    "case",
    [
        "lockers",
        "people",
        "height",
        "aisle",
        "collision",
        "door",
        "chair",
        "maintenance",
        "process_face",
        "disconnected",
        "bench",
    ],
)
def test_specific_functional_conflicts(case):
    kind = (
        "OFFICE"
        if case == "chair"
        else "COATING"
        if case in {"maintenance", "process_face"}
        else "SINGLE_SIDE"
    )

    def change(room, refs, w, b):
        if case == "lockers":
            w["components"] = [c for c in w["components"] if c["id"] != "locker-16"]
        if case == "people":
            w["components"] = [c for c in w["components"] if c["role"] != "PERSON"]
        if case == "height":
            b["clear_height_mm"] = replace(b["clear_height_mm"], value=1000)
        if case == "aisle":
            b["aisle_width_mm"] = replace(b["aisle_width_mm"], value=1800)
        if case == "collision":
            next(c for c in w["components"] if c["id"] == "locker-2")["bounds_mm"] = [
                500,
                500,
                900,
                1000,
            ]
        if case == "door":
            w["components"][0]["bounds_mm"] = [500, 4000, 600, 4500]
        if case == "chair":
            w["components"] = [c for c in w["components"] if c["role"] != "CHAIR"]
        if case == "maintenance":
            b["maintenance_clearances_mm"] = replace(
                b["maintenance_clearances_mm"], value=[5000, 0, 800, 800]
            )
        if case == "process_face":
            b["equipment_flow_faces"] = replace(
                b["equipment_flow_faces"], value={"INFEED": "E", "OUTFEED": "E"}
            )
        if case == "disconnected":
            # The remote person rectangle fits in the room but not in its aisle network.
            next(c for c in w["components"] if c["id"] == "person-1")["bounds_mm"] = [
                4000,
                4000,
                4400,
                4600,
            ]
        if case == "bench":
            b["bench_operation_mm"] = replace(b["bench_operation_mm"], value=4000)

    r = evaluate(kind, change)
    assert r["functional_status"] in {"CONFIGURATION_NOT_FIT", "INPUT_REQUIRED"} and (
        r["conflicts"] or r["missing_inputs"]
    )


def test_unreviewed_partition_cannot_be_declared_hygiene_pass():
    r = evaluate(
        mutate=lambda room, refs, w, b: b.update(
            clean_separation=replace(b["clean_separation"], value="PARTITION_REQUIRED")
        )
    )
    assert r["functional_status"] == "INPUT_REQUIRED"
    assert "reviewed_clean_unclean_partition_and_portal_design" in r["missing_inputs"]


@pytest.mark.parametrize(
    "case",
    [
        "float",
        "bool",
        "unit",
        "model",
        "states",
        "body_disappears",
        "duplicate",
        "no_route",
        "invalid_portal",
        "outside_clear",
    ],
)
def test_invalid_or_ambiguous_input_never_fits(case):
    def change(room, refs, w, b):
        if case == "float":
            b["aisle_width_mm"] = replace(b["aisle_width_mm"], value=1200.0)
        if case == "bool":
            b["simultaneous_users"] = replace(b["simultaneous_users"], value=True)
        if case == "unit":
            b["aisle_width_mm"] = replace(b["aisle_width_mm"], unit="m")
        if case == "model":
            b["locker_model"] = replace(b["locker_model"], value="")
        if case == "states":
            w["components"][1]["states"] = ["UNKNOWN"]
        if case == "body_disappears":
            w["components"][1]["states"] = ["USE"]
        if case == "duplicate":
            w["components"].append(deepcopy(w["components"][1]))
        if case == "no_route":
            w["routes"] = []
        if case == "invalid_portal":
            room["portals"][0]["segment_mm"] = [[1000, 1000], [1000, 2500]]
        if case == "outside_clear":
            b["finished_clear_bounds_mm"] = replace(
                b["finished_clear_bounds_mm"], value=[0, 0, 9000, 5000]
            )

    assert evaluate(mutate=change)["functional_status"] == "INPUT_REQUIRED"


def test_no_square_rule_or_3000_mm_minimum_is_introduced():
    room, refs, w, b = scenario()
    room["local_bounds_mm"] = [0, 0, 40000, 2800]
    room["portals"][0]["segment_mm"] = [[29250, 0], [30750, 0]]
    b["finished_clear_bounds_mm"] = replace(
        b["finished_clear_bounds_mm"], value=[0, 0, 40000, 2800]
    )
    b["bench_count"] = replace(b["bench_count"], value=0)
    b["door_operation_envelopes_mm"] = replace(
        b["door_operation_envelopes_mm"], value={"entry": [[30750, 0, 32250, 100]]}
    )
    w["components"] = [
        c for c in w["components"] if c["role"] != "BENCH" and c["id"] != "bench-link"
    ]
    w["components"][0]["bounds_mm"] = [30750, 0, 32250, 100]
    next(c for c in w["components"] if c["id"] == "front")["bounds_mm"] = [0, 1600, 40000, 2800]
    w["components"].append(
        dict(id="entry-link", role="AISLE", bounds_mm=[29400, 0, 30600, 2800], states=list(STATES))
    )
    w["routes"][0]["points_mm"] = [[30000, 0], [30000, 2200], [7400, 2200]]
    r = evaluate_functional_room(room, refs, w, reviewed_basis=b)
    assert r["functional_status"] == "CONDITIONAL_FIT", r


def test_exact_union_coverage_does_not_fill_holes():
    target = (0, 0, 10, 10)
    assert covered(target, [(0, 0, 5, 10), (5, 0, 10, 10)])
    assert not covered(target, [(0, 0, 4, 10), (5, 0, 10, 10)])
    rng = random.Random(11)
    for _ in range(80):
        cover = []
        for _ in range(5):
            x, r = sorted(rng.sample(range(11), 2))
            y, t = sorted(rng.sample(range(11), 2))
            cover.append((x, y, r, t))
        pixels = sum(
            any(a <= x < r and b <= y < t for a, b, r, t in cover)
            for x in range(10)
            for y in range(10)
        )
        assert covered(target, cover) == (pixels == area(target))


def test_sealed_loader_refuses_missing_tampered_or_escaping_files(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        sealed_file(tmp_path, "data.json", {"data.json": "0" * 64})
    with pytest.raises(ValueError, match="PATH_INVALID"):
        sealed_file(tmp_path, "../outside", {"../outside": "0" * 64})


def test_review_is_local_does_not_compute_engineering_in_javascript():
    d = json.loads((PREVIEW / "review-data.json").read_text())
    e = json.loads((PREVIEW / "synthetic-examples.json").read_text())
    html = render_review(d, e)
    assert "fetch(" not in html and "http://" not in html and "https://" not in html
    assert 'data-mode="example"' in html and "不属于真实 MAIN" in html
    assert "hist-G08" in html and "INPUT_REQUIRED" in html
    assert "原Stage B有效状态" in html and "柜体、通道、座凳" in html
    assert "eval(" not in html and "localStorage" not in html


def test_narrow_corner_overlap_does_not_prove_full_width_connectivity():
    from cold_storage.modules.layout.domain.functional_room_fit import connected

    assert not connected((0, 0, 4000, 1200), (3900, 1100, 5100, 5000), 1200)
    assert connected((0, 0, 4000, 1200), (2800, 0, 4000, 5000), 1200)


def test_explicit_open_portal_requires_no_invented_door_leaf():
    def change(room, refs, w, b):
        b["door_operation"] = replace(b["door_operation"], value="OPEN_PORTAL")
        b["door_operation_envelopes_mm"] = replace(
            b["door_operation_envelopes_mm"], value={"entry": []}
        )
        w["components"] = [c for c in w["components"] if c["role"] != "DOOR_OPERATION"]

    assert evaluate(mutate=change)["functional_status"] == "CONDITIONAL_FIT"


def test_required_locker_compartment_feature_and_shift_identity_are_checked():
    def no_feature(room, refs, w, b):
        b["locker_internal_separation_available"] = replace(
            b["locker_internal_separation_available"], value=False
        )

    assert evaluate(mutate=no_feature)["functional_status"] == "CONFIGURATION_NOT_FIT"

    def bad_shift(room, refs, w, b):
        next(c for c in w["components"] if c["role"] == "LOCKER")["shift"] = True

    assert evaluate(mutate=bad_shift)["functional_status"] == "CONFIGURATION_NOT_FIT"


def test_reference_must_match_the_semantic_input_field():
    def change(room, refs, w, b):
        refs["bench_dimensions_mm"] = "locker_dimensions_mm"

    r = evaluate(mutate=change)
    assert (
        r["functional_status"] == "INPUT_REQUIRED" and "bench_dimensions_mm" in r["missing_inputs"]
    )


def test_office_actual_door_is_not_inferred_from_whole_building_access():
    def change(room, refs, w, b):
        room["portals"] = []

    assert "actual_room_portal" in evaluate("OFFICE", change)["missing_inputs"]
