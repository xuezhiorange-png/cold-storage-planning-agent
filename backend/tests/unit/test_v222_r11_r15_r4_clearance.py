"""Directed R4 conditional geometry, full-flow and provenance regressions."""

import copy
import gzip
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from build_r11_r15_r4_clearance_review import engineering_report, summarize
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.ten_door_clearance_review import (
    SOURCE_WITNESS,
    review_adjustment,
    review_local_clearance,
    source_case,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.ten_door_local_clearance import (
    MAX_CANDIDATES,
    construct_local_adjustment,
    finite_adjustments,
    local_section,
    require_frozen_basis,
)
from cold_storage.modules.layout.domain.ten_door_locker_model import DoorSensitivity
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import check_flow_doors
from cold_storage.modules.layout.infrastructure.ten_door_clearance_evidence import (
    MANIFEST_SHA256,
    R15,
    read_r15_archive,
)
from cold_storage.modules.layout.infrastructure.ten_door_clearance_page import (
    coordinate_comparison,
    plan_svg,
    review_page,
    section_svg,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def no_native():
    def blocked(*args, **kwargs):
        raise RuntimeError("R15_R4_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
            patch.setattr(cp_model.CpSolver, "solve", blocked)
            patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def archive():
    return read_r15_archive(ROOT)


@pytest.fixture(scope="module")
def base(archive):
    return source_case(archive)


@pytest.fixture(scope="module")
def report(archive):
    return review_local_clearance(archive)


@pytest.fixture(scope="module")
def selected(report):
    return next(c for c in report["reports"] if c["id"] == report["selected_candidate_id"])


def test_six_predeclared_checks_include_control_and_section_only_negative():
    choices = finite_adjustments()
    assert len(choices) == MAX_CANDIDATES == 6
    assert len({canonical_hash(c) for c in choices}) == 6
    assert sum(c["scope"] == "SECTION_ONLY" for c in choices) == 1
    assert choices == finite_adjustments()


@pytest.mark.parametrize("bad", ["witness", "body", "project", "flow"])
def test_modified_history_cannot_become_source(base, bad):
    other = copy.deepcopy(base)
    if bad == "witness":
        other["witness_hash"] = "sha256:forged"
    elif bad == "body":
        other["geometry"]["parameters"]["person_width_mm"] = 400
    elif bad == "project":
        other["geometry"]["room"]["scope_id"] = "another-project"
    else:
        other["closed_door_flows"][0]["completed_users"] = 52
    with pytest.raises(ValueError, match="SOURCE_OR_WITNESS"):
        source_case({"reports": [other]})


def test_source_has_full_fixed_witness_and_only_one_record(archive, base):
    assert len(archive["reports"]) == 1
    assert canonical_hash(base["payload"]) == SOURCE_WITNESS
    require_frozen_basis(base["geometry"])


@pytest.mark.parametrize(
    "bad", ["room", "aisle", "activity", "gap", "body", "persons", "cabinet", "portal"]
)
def test_protected_room_bodies_aisle_people_product_and_portal_not_reduced(base, bad):
    g = copy.deepcopy(base["geometry"])
    if bad == "room":
        g["room"]["local_bounds_mm"][3] += 100
    elif bad == "aisle":
        g["parameters"]["aisle_mm"] = 1200
    elif bad == "activity":
        g["front_parameters"]["activity_depth_mm"] = 800
    elif bad == "gap":
        g["parameters"]["person_gap_mm"] = 100
    elif bad == "body":
        g["parameters"]["person_width_mm"] = 400
    elif bad == "persons":
        g["demand"]["simultaneous_room_users"] = 52
    elif bad == "cabinet":
        g["inventory"]["cabinet_units"][0]["dimensions_mm"][0] = 800
    else:
        g["room"]["portals"][0]["clear_width_mm"] = 1400
    with pytest.raises(ValueError, match="FROZEN_R15_03"):
        require_frozen_basis(g)


def test_undeclared_seventh_combination_rejected(base):
    choice = dict(finite_adjustments()[2], operator_delta_mm=36)
    with pytest.raises(ValueError, match="DECLARED_R4"):
        construct_local_adjustment(base["geometry"], choice)


def test_person_only_shift_transfers_35mm_deficit_and_creates_no_success_witness(base):
    choice = finite_adjustments()[1]
    s = local_section(base["geometry"], choice)
    assert s["body_mm"] == [880, 1075, 1330, 1725]
    assert s["gaps"]["conditional_own_door_mm"] == 100
    assert s["gaps"]["standing_activity_to_branch_mm"] == 65
    assert not s["all_section_100_met"]
    r = review_adjustment(base, choice)
    assert r["geometry"] is None and r["closed_door_flows"] == r["profiles"] == []
    assert r["full_flow_status"] == "NOT_EVALUATED_SECTION_NEGATIVE_CONTROL"
    assert not r["geometry_or_flow_witness_created"]


def test_zero_delta_control_reproduces_original_movements_not_just_summary(report, base):
    r = report["reports"][0]
    assert r["closed_door_flows"] == base["closed_door_flows"]
    assert not r["all_100_met"]
    assert (
        r["profiles"][0]["analytic_distances"]["minimum"]["distance"]["model_distance_lower_um"]
        == 65000
    )


def test_minimum_selected_adjustment_is_35mm_without_moving_any_home_or_cabinet(selected, base):
    assert selected["id"] == "R4-02"
    assert selected["all_100_met"]
    g = selected["geometry"]
    assert g["parameters"]["operator_standoff_mm"] == 515
    assert g["conditions"]["operator_standoff_mm"] == 415
    assert g["inventory"] == base["geometry"]["inventory"]
    assert g["room"] == base["geometry"]["room"]
    assert g["model"] == base["geometry"]["model"]
    assert selected["coordinate_diff"]["changed_homes"] == []
    assert selected["section"]["gaps"] == dict(
        conditional_own_door_mm=100,
        operator_to_branch_mm=100,
        standing_activity_to_branch_mm=100,
        north_home_to_branch_mm=100,
        north_home_to_finished_wall_mm=145,
    )


@pytest.mark.parametrize("shift", [1, 2])
def test_full_actual_roster_entry_two_locker_operations_change_exit(selected, shift):
    f = next(f for f in selected["closed_door_flows"] if f["shift"] == shift)
    assert f["status"] == "VERIFIED_UNDER_HYPOTHESES"
    assert f["initial_service_occupancy"] == f["completed_users"] == 53
    assert set(f["served_person_ids"]) == set(f["completed_person_ids"])
    assert len(f["completed_batches"]) == f["expected_batches"] == 14
    assert f["not_entered_people"] == f["remaining_inside"] == []
    assert sum(e["operation"] == "ENTER_PORTAL" for e in f["events"]) == 53
    assert sum(e["operation"] == "EXIT_PORTAL" for e in f["events"]) == 53
    assert all(
        e["inside_people"] + e["departed_people"] + e["not_entered_people"] == 53
        for e in f["events"]
    )
    assert all(e["proof"]["conflicts"] == [] for e in f["events"])
    for batch in f["completed_batches"]:
        actions = [e["operation"] for e in f["events"] if e["batch"] == batch]
        required = [
            "OPEN_FOR_RETRIEVE",
            "RETRIEVE_CLOTHES",
            "CLOSE_AFTER_RETRIEVE",
            "PARALLEL_STANDING_CHANGE",
            "OPEN_FOR_STORE",
            "STORE_CLOTHES",
            "CLOSE_AFTER_STORE",
        ]
        assert [x for x in actions if x in required] == required


@pytest.mark.parametrize("profile", [0, 1])
def test_both_hypotheses_recheck_212_openings_and_all_live_objects(selected, profile):
    p = selected["profiles"][profile]
    assert len(p["doors"]["registry"]) == 110
    assert p["doors"]["complete_106_person_coverage"]
    assert p["doors"]["served_compartments"] == 106
    assert p["doors"]["checked_open_events"] == 212
    distances = p["analytic_distances"]
    assert len(distances["own_person_openings"]) == 212
    assert distances["all_object_volume_checks"] == 8148
    assert all(
        o["distance"]["model_distance_lower_um"]
        == o["distance"]["model_distance_upper_um"]
        == 100000
        for o in distances["own_person_openings"]
    )
    assert distances["minimum"]["distance"]["model_distance_lower_um"] == 100000
    assert all(e["proof"]["conflicts"] == [] for e in p["doors"]["events"])
    assert p["combined"]["complete"] and p["combined"]["all_declared_100_met"]


def test_actual_critical_event_is_rebuilt_and_not_hand_edited(selected, base):
    new = selected["closed_door_flows"][0]["events"][110]
    old = base["closed_door_flows"][0]["events"][110]
    assert new["operation"] == old["operation"] == "OPEN_FOR_RETRIEVE"
    a = next(p for p in old["proof"]["people_before"] if p["id"] == "S1-P001")
    b = next(p for p in new["proof"]["people_before"] if p["id"] == "S1-P001")
    assert [b["bounds_mm"][i] - a["bounds_mm"][i] for i in range(4)] == [0, 35, 0, 35]
    assert new["inside_people"] == 53
    assert canonical_hash(selected["payload"]) == selected["witness_hash"]


def test_50mm_shift_without_north_reorganization_preserves_flow_but_fails_margin(report):
    c = report["reports"][3]
    assert c["full_flow_status"] == "CONDITIONAL_FULL_FLOW_COMPLETE"
    assert c["margins"]["minimum_declared_spatial_margin"]["extra_mm"] == 85
    assert (
        c["profiles"][0]["analytic_distances"]["minimum"]["distance"]["model_distance_lower_um"]
        == 115000
    )
    assert not c["all_100_met"]


@pytest.mark.parametrize("index,delta,wall", [(4, 15, 130), (5, 45, 100)])
def test_north_positions_are_derived_from_actual_branch_and_waiting_gap(report, index, delta, wall):
    c = report["reports"][index]
    assert c["section"]["north_home_delta_mm"] == delta
    assert c["section"]["gaps"]["north_home_to_finished_wall_mm"] == wall
    assert c["all_100_met"]
    assert len(c["coordinate_diff"]["changed_homes"]) == 15
    assert all(
        h["after"]["bounds_mm"][1] - h["before"]["bounds_mm"][1] == delta
        for h in c["coordinate_diff"]["changed_homes"]
    )


def test_own_person_clearance_is_not_misreported_as_minimum_over_other_cabinets(report):
    c = report["reports"][5]
    for p in c["profiles"]:
        assert (
            min(
                o["distance"]["model_distance_lower_um"]
                for o in p["analytic_distances"]["own_person_openings"]
            )
            == 145000
        )
        assert p["analytic_distances"]["minimum"]["distance"]["model_distance_lower_um"] == 117000


def test_thicker_door_is_still_rejected_by_original_checker(selected):
    checked = check_flow_doors(
        selected["geometry"],
        selected["closed_door_flows"],
        DoorSensitivity("ALL_LEFT", leaf_thickness_mm=140),
    )
    assert checked["status"] == "CONFIGURATION_NOT_FIT"
    assert any(e["proof"]["conflicts"] for e in checked["events"])


def test_missing_real_second_shift_opening_never_inherits_full_flow(selected):
    flows = copy.deepcopy(selected["closed_door_flows"])
    flows[1]["events"] = [e for e in flows[1]["events"] if e["operation"] != "OPEN_FOR_STORE"]
    check = check_flow_doors(selected["geometry"], flows, DoorSensitivity("MIRRORED"))
    assert not check["complete_106_person_coverage"]
    assert check["checked_open_events"] == 159


def test_geometry_is_deterministic_and_does_not_mutate_history(base, selected):
    before = canonical_hash(base)
    a = construct_local_adjustment(base["geometry"], finite_adjustments()[2])
    b = construct_local_adjustment(base["geometry"], finite_adjustments()[2])
    assert canonical_hash(a) == canonical_hash(b) == canonical_hash(selected["geometry"])
    assert canonical_hash(base) == before


def test_html_svgs_and_report_are_faithful_and_do_not_claim_actual_approval(report, selected):
    summary = summarize(report)
    for svg in (
        plan_svg(selected),
        coordinate_comparison(report["reports"][0], selected),
        section_svg(report["reports"][0], selected),
    ):
        node = ET.fromstring(svg)
        assert node.tag == "{http://www.w3.org/2000/svg}svg"
        assert "viewBox" in node.attrib
    page = review_page(summary)
    assert "INPUT_REQUIRED" in page and "NOT_EVALUATED" in page
    assert "fetch(" not in page and "data:image/" not in page
    md = engineering_report(summary)
    assert "100mm不是实测操作净距" in md
    assert "117mm" in md and "NOT_EVALUATED" in md
    assert "必要断面负对照" in md
    assert report["native_solves"] == 0 and not report["main_executed"]
    assert report["photo_r2"] == "PAUSED_NOT_EVALUATED"


def test_pinned_manifest_and_raw_archive_are_unchanged():
    assert (
        hashlib.sha256((ROOT / R15 / "source-manifest.json").read_bytes()).hexdigest()
        == MANIFEST_SHA256
    )
    source = json.loads((ROOT / R15 / "source-manifest.json").read_bytes())
    for name, expected in source["derived_files"].items():
        assert hashlib.sha256((ROOT / R15 / name).read_bytes()).hexdigest() == expected


def test_published_witnesses_and_derived_hashes_match_actual_results(report):
    path = ROOT / "docs/previews/v2.2.2/r11-r15-r4-local-clearance"
    assert path.is_dir(), "PUBLISHED_R4_EVIDENCE_REQUIRED"
    manifest = json.loads((path / "source-manifest.json").read_bytes())
    raw = json.loads(gzip.decompress((path / "full-witnesses.json.gz").read_bytes()))
    assert canonical_hash(raw) == canonical_hash(report)
    for name, expected in manifest["derived_files"].items():
        assert hashlib.sha256((path / name).read_bytes()).hexdigest() == expected
    assert manifest["photo_r2"] == "PAUSED_NOT_EVALUATED"
    assert not manifest["original_photo_published"]
    assert not any(p.suffix.lower() in {".jpeg", ".jpg", ".heic"} for p in path.iterdir())


@pytest.mark.parametrize("api", ["solve", "Solve"])
def test_parent_and_child_native_apis_are_blocked(tmp_path, api):
    with pytest.raises(RuntimeError, match="NATIVE_FORBIDDEN"):
        getattr(cp_model.CpSolver(), api)(cp_model.CpModel())
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "backend/tests/functional_native_guard")
    env["R11_FUNCTIONAL_GUARD_AUDIT"] = str(tmp_path / "guard")
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ortools.sat.python import cp_model; "
            + f"cp_model.CpSolver().{api}(cp_model.CpModel())",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode != 0 and "R11_FUNCTIONAL_NATIVE_FORBIDDEN" in child.stderr
    assert any(
        "NATIVE_REQUEST_BLOCKED" in p.read_text() for p in (tmp_path / "guard").glob("*.jsonl")
    )


def test_fast_ci_runs_new_tests_without_dropping_existing_functional_or_native_tests():
    text = (ROOT / ".github/workflows/ci-fast.yml").read_text()
    assert text.count("tests/unit/test_v222_r11_r15_r4_clearance.py") == 1
    assert "tests/unit/test_v222_r11_r15_local_relayout.py" in text
    assert "tests/unit/test_v222_stage_b_route_refinement.py" in text
    assert "tests/unit/test_v222_r11_r14_ten_door_locker.py" in text
