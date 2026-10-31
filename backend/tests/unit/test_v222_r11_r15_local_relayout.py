"""Source bytes, analytic distance, finite homes and complete live-person flows."""

import copy
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from build_r11_r15_local_relayout_review import summarize, write_review
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.physical_room_calibration_review import (
    calibration_context,
)
from cold_storage.modules.layout.application.ten_door_locker_review import SOURCE_PATH as R14_SOURCE
from cold_storage.modules.layout.application.ten_door_relayout_review import (
    PHOTO_OWNER_REPORTED_SHA256,
    SOURCE_PATH,
    SOURCE_SHA256,
    photo_source_supplement,
    review_local_relayout,
    verify_private_photo,
)
from cold_storage.modules.layout.domain.changing_room_motion import door_hits_box
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.h5_space_relayout import waiting_clearances
from cold_storage.modules.layout.domain.ten_door_local_relayout import (
    MAX_CANDIDATES,
    finite_organizations,
    rearrange_homes,
)
from cold_storage.modules.layout.domain.ten_door_locker_model import (
    DoorSensitivity,
    complete_inventory_conflicts,
)
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import check_flow_doors
from cold_storage.modules.layout.domain.ten_door_sweep_clearance import certified_sweep_distance
from cold_storage.modules.layout.infrastructure.physical_calibration_evidence import (
    read_calibration_evidence,
)
from cold_storage.modules.layout.infrastructure.ten_door_relayout_evidence import (
    R14,
    read_r14_archive,
)
from cold_storage.modules.layout.infrastructure.ten_door_relayout_page import (
    case_plan,
    clearance_svg,
    comparison_plan,
    review_page,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def no_native():
    def blocked(*args, **kwargs):
        raise RuntimeError("R15_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
            patch.setattr(cp_model.CpSolver, "solve", blocked)
            patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def ctx():
    return calibration_context(read_calibration_evidence(ROOT))


@pytest.fixture(scope="module")
def archive():
    return read_r14_archive(ROOT)


@pytest.fixture(scope="module")
def sources():
    return (ROOT / R14_SOURCE).read_bytes(), (ROOT / SOURCE_PATH).read_bytes()


@pytest.fixture(scope="module")
def report(ctx, archive, sources):
    return review_local_relayout(ctx, archive, *sources)


@pytest.fixture(scope="module")
def selected(report):
    return next(c for c in report["reports"] if c["id"] == report["selected_candidate_id"])


def test_owner_digest_is_reported_separately_from_missing_raw_bytes(ctx, sources):
    q = photo_source_supplement(ctx, *sources)
    assert hashlib.sha256(sources[1]).hexdigest() == SOURCE_SHA256
    assert q["owner_reported_sha256"] == PHOTO_OWNER_REPORTED_SHA256
    assert q["actual_photo_sha256"] is None
    assert q["photo_file_evidence"] == "INPUT_REQUIRED_ORIGINAL_PHOTO_FILE_MISSING"
    assert q["photo_publication_authorized"] is q["photo_embedded_or_copied"] is False
    assert q["actual_net_compartment_dimensions"] == q["actual_hardware"] == "INPUT_REQUIRED"


@pytest.mark.parametrize("raw", [b"", b'{"approved":true}', b"Owner", b"x" * 100])
def test_text_status_cannot_replace_pinned_owner_source(ctx, sources, raw):
    with pytest.raises(ValueError, match="SOURCE_MISMATCH"):
        photo_source_supplement(ctx, sources[0], raw)


@pytest.mark.parametrize("raw", [b"image", b"approved=true", b"IMG_0875.jpeg"])
def test_wrong_photo_bytes_reject_instead_of_borrowing_owner_digest(ctx, sources, raw):
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        photo_source_supplement(ctx, *sources, raw)


def test_raw_byte_verifier_hashes_a_control_file_without_claiming_real_photo():
    raw = b"SYNTHETIC_PRIVATE_PHOTO_HASH_CONTROL_NOT_THE_OWNER_PHOTO"
    expected = hashlib.sha256(raw).hexdigest()
    assert expected != PHOTO_OWNER_REPORTED_SHA256
    assert verify_private_photo(raw, expected) == expected
    with pytest.raises(ValueError, match="SHA256_MISMATCH"):
        verify_private_photo(raw + b"edited", expected)


@pytest.mark.parametrize("key", ["project_scope_id", "physical_room_id"])
def test_other_project_or_physical_room_cannot_use_supplement(ctx, sources, key):
    other = copy.deepcopy(ctx)
    other["overlay"][key] = "other"
    with pytest.raises(ValueError):
        photo_source_supplement(other, *sources)


@pytest.mark.parametrize("kind", ["homes", "source", "hash", "budget"])
def test_stale_or_forged_r14_witness_rejected(ctx, archive, sources, kind):
    a = copy.deepcopy(archive)
    c = a["reports"][0]
    if kind == "homes":
        c["geometry"]["model"]["homes"][0]["bounds_mm"][0] += 1
    elif kind == "source":
        c["door_profiles"][0]["payload"]["source_hashes"] = {}
    elif kind == "hash":
        c["door_profiles"][0]["witness_hash"] = "sha256:fake"
    else:
        c["conditions"]["finish_mm"] = 0
    with pytest.raises(ValueError, match="ARCHIVE_WITNESS"):
        review_local_relayout(ctx, a, *sources)


def test_all_twelve_declared_combinations_are_unique_and_bounded():
    choices = finite_organizations()
    assert len(choices) == MAX_CANDIDATES == 12 < 36
    assert len({canonical_hash(q) for q in choices}) == 12
    assert choices == finite_organizations()


def test_history_failure_and_positive_controls_remain_separate(report):
    assert [r["homes"] for r in report["historical_r14_summary"]] == [53, 53, 38, 52]
    assert report["archived_baseline"]["closed_door_flows"] == []
    assert report["actual_candidates"] == 12
    assert len(report["complete_candidate_ids"]) == 5
    assert report["all_margin_100_target_candidate_ids"] == []


def test_rearrangement_does_not_mutate_input_inventory_room_or_portals(archive):
    base = archive["reports"][3]["geometry"]
    digest = canonical_hash(base)
    g = rearrange_homes(base, finite_organizations()[2])
    assert canonical_hash(base) == digest
    assert g["room"] == base["room"]
    assert g["inventory"] == base["inventory"]
    assert g["parameters"] == base["parameters"]
    assert g["conditions"] == base["conditions"]
    assert g["model"]["landing"] == base["model"]["landing"]


@pytest.mark.parametrize("bad", ["body", "gap", "margin", "aisle", "room", "half-unit"])
def test_reduced_protected_geometry_or_product_is_not_accepted(archive, bad):
    base = copy.deepcopy(archive["reports"][3]["geometry"])
    if bad == "body":
        base["parameters"]["person_width_mm"] = 400
    elif bad == "gap":
        base["parameters"]["person_gap_mm"] = 100
    elif bad == "margin":
        base["spatial_padding_mm"] = 50
    elif bad == "aisle":
        base["parameters"]["aisle_mm"] = 1200
    elif bad == "room":
        base["room"]["local_bounds_mm"][3] = 3900
    else:
        base["inventory"]["cabinet_units"][0]["partial_unit"] = True
    with pytest.raises(ValueError, match="STRICT_3850"):
        rearrange_homes(base, finite_organizations()[2])


def test_arbitrary_37th_coordinate_template_cannot_enter(archive):
    with pytest.raises(ValueError, match="DECLARED_FINITE"):
        rearrange_homes(archive["reports"][3]["geometry"], dict(id="OTHER", south_grid="CUSTOM"))


def test_selected_geometry_reaches_53_without_any_cabinet_change(selected):
    g = selected["geometry"]
    assert selected["id"] == "R15-03"
    assert len(g["model"]["homes"]) == 53
    assert not waiting_clearances(g)
    assert g["parameters"]["person_gap_mm"] == 200
    assert g["parameters"]["aisle_mm"] == 1300
    assert g["spatial_padding_mm"] == 100
    assert not complete_inventory_conflicts(g["inventory"], g["demand"])
    assert all(u["dimensions_mm"] == [850, 390, 1800] for u in g["inventory"]["cabinet_units"])
    assert all(
        not selected["coordinate_diff"][k]
        for k in ("cabinets_changed", "room_changed", "portals_changed")
    )


def test_north_row_alignment_is_a_real_35mm_move_and_one_added_home(selected, report):
    old = report["archived_baseline"]["geometry"]["model"]["homes"]
    new = selected["geometry"]["model"]["homes"]
    assert new[:38] == old[:38]
    for a, b in zip(old[38:], new[38:52], strict=True):
        assert [b["bounds_mm"][i] - a["bounds_mm"][i] for i in range(4)] == [0, 35, 0, 35]
    assert new[52]["bounds_mm"] == [12780, 3225, 13430, 3675]
    assert len(selected["coordinate_diff"]["changed_homes"]) == 15


def test_static_53_can_fail_continuous_entry_and_is_not_promoted(report):
    c = next(c for c in report["reports"] if c["id"] == "R15-04")
    assert c["home_count"] == 53 and c["geometry"]["static_status"] == "STATIC_GEOMETRY_PASS"
    for f in c["closed_door_flows"]:
        assert f["initial_service_occupancy"] == f["completed_users"] == 0
        assert f["blocker"]["operation"] == "REACH_WAITING_POSITION"
        assert any(q["code"] == "SWEPT_BODY_COLLISION" for q in f["blocker"]["conflicts"])
    assert all(not p["combined"]["complete"] for p in c["profiles"])


@pytest.mark.parametrize("shift", [1, 2])
def test_each_shift_has_all_53_enter_service_exit_and_live_roster(selected, shift):
    f = next(f for f in selected["closed_door_flows"] if f["shift"] == shift)
    assert f["status"] == "VERIFIED_UNDER_HYPOTHESES"
    assert f["initial_service_occupancy"] == f["completed_users"] == 53
    assert len(set(f["completed_person_ids"])) == 53
    assert set(f["served_person_ids"]) == set(f["completed_person_ids"])
    assert f["remaining_inside"] == f["not_entered_people"] == []
    assert sum(e["operation"] == "ENTER_PORTAL" for e in f["events"]) == 53
    assert sum(e["operation"] == "EXIT_PORTAL" for e in f["events"]) == 53
    assert all(
        e["inside_people"] + e["departed_people"] + e["not_entered_people"] == 53
        for e in f["events"]
    )
    assert all(e["proof"]["status"] == "VERIFIED_UNDER_HYPOTHESES" for e in f["events"])


@pytest.mark.parametrize("profile", [0, 1])
def test_all_110_doors_and_212_person_openings_rechecked(selected, profile):
    d = selected["profiles"][profile]["doors"]
    assert len(d["registry"]) == len({d["id"] for d in d["registry"]}) == 110
    assert d["checked_open_events"] == d["required_open_events"] == 212
    assert d["served_compartments"] == 106
    assert d["complete_106_person_coverage"] is True
    assert all(e["proof"]["conflicts"] == [] for e in d["events"])
    assert d["minimum_door_clearance_lower_bound"]["extra_mm"] == 65
    assert selected["profiles"][profile]["combined"]["complete"] is True
    assert selected["profiles"][profile]["combined"]["margin_target_met"] is False


def test_missing_second_opening_is_not_full_flow(selected):
    flows = copy.deepcopy(selected["closed_door_flows"])
    flows[1]["events"] = [e for e in flows[1]["events"] if e["operation"] != "OPEN_FOR_STORE"]
    d = check_flow_doors(selected["geometry"], flows, DoorSensitivity("ALL_LEFT"))
    assert d["complete_106_person_coverage"] is False
    assert d["checked_open_events"] < 212
    assert d["status"] != "CONDITIONAL_DOOR_EVENTS_PASS"


def test_thick_door_cannot_be_hidden_by_closed_door_flow(selected):
    d = check_flow_doors(
        selected["geometry"],
        selected["closed_door_flows"],
        DoorSensitivity("ALL_LEFT", leaf_thickness_mm=100),
    )
    assert d["status"] == "CONFIGURATION_NOT_FIT"
    assert any(e["proof"]["conflicts"] for e in d["events"])


def test_old_15mm_minimum_is_analytic_15mm_not_claimed_50mm(report):
    for t in report["clearance_traces"]:
        d = t["distance"]
        assert t["shift"] == 1 and t["event"] == 110 and t["tier"] == 1
        assert t["door"]["id"] == "U01-L-T1-DOOR" and t["person"]["id"] == "S1-P001"
        assert t["people_count"] == 53
        assert len(t["simultaneous_doors"]) == 4
        assert t["original_event_revalidation"]["conflicts"] == []
        assert t["archived_lower_bound_mm"] == 15
        assert d["model_distance_lower_um"] == d["model_distance_upper_um"] == 15000
        assert not d["sensitivity_50mm_met"] and not d["collision_original_predicate"]
        assert d["actual_hardware_and_human_clearance"] == "INPUT_REQUIRED"


def test_selected_65mm_clearance_is_still_below_100_target(report):
    for t in report["new_clearance_traces"]:
        assert (
            t["distance"]["model_distance_lower_um"]
            == t["distance"]["model_distance_upper_um"]
            == 65000
        )
    assert report["all_margin_100_target_candidate_ids"] == []


def model_door(**changes):
    return dict(
        kind="OUTWARD_HINGED_90",
        angle_degrees=90,
        direction=[1, 1],
        hinge_mm=[0, 0],
        radius_mm=400,
        thickness_mm=15,
        z_interval_mm=[100, 420],
        **changes,
    )


def test_bounding_box_overlap_does_not_prevent_tighter_arc_distance():
    q = certified_sweep_distance(model_door(), [350, 350, 0, 450, 450, 1800])
    assert q["bounding_box_lower_bound_mm"] == 0
    assert 73000 < q["model_distance_lower_um"] <= q["model_distance_upper_um"] < 74000
    assert q["model_distance_upper_um"] - q["model_distance_lower_um"] <= 1
    assert not q["collision_original_predicate"]


@pytest.mark.parametrize(
    "volume,expected",
    [
        ([0, 430, 0, 450, 1080, 1800], 15000),
        ([-115, 0, 0, -100, 10, 1800], 85000),
        ([0, -115, 0, 10, -100, 1800], 85000),
        ([-15, -15, 0, -1, -1, 1800], 0),
        ([0, 0, 500, 100, 100, 1800], 80000),
    ],
)
def test_certified_axes_quadrants_thickness_and_height(volume, expected):
    q = certified_sweep_distance(model_door(), volume)
    assert q["model_distance_lower_um"] == q["model_distance_upper_um"] == expected
    assert q["collision_original_predicate"] == door_hits_box(model_door(), volume)


@pytest.mark.parametrize("direction", [[1, 1], [-1, 1], [1, -1], [-1, -1]])
def test_distance_is_invariant_under_hinge_axis_mirroring(direction):
    d = model_door()
    d["direction"] = direction
    x = sorted([350 * direction[0], 450 * direction[0]])
    y = sorted([350 * direction[1], 450 * direction[1]])
    q = certified_sweep_distance(d, [x[0], y[0], 0, x[1], y[1], 1800])
    ref = certified_sweep_distance(model_door(), [350, 350, 0, 450, 450, 1800])
    assert q["model_distance_lower_um"] == ref["model_distance_lower_um"]
    assert q["model_distance_upper_um"] == ref["model_distance_upper_um"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("angle_degrees", 80),
        ("radius_mm", 0),
        ("thickness_mm", -1),
        ("direction", [0, 1]),
        ("hinge_mm", [0.0, 0]),
    ],
)
def test_unknown_hardware_geometry_is_not_silently_approximated(field, value):
    d = model_door()
    d[field] = value
    with pytest.raises(ValueError):
        certified_sweep_distance(d, [350, 350, 0, 450, 450, 1800])


def test_same_inputs_produce_identical_geometry_and_new_witness(selected, archive):
    first = rearrange_homes(archive["reports"][3]["geometry"], selected["organization"])
    second = rearrange_homes(archive["reports"][3]["geometry"], selected["organization"])
    assert canonical_hash(first) == canonical_hash(second) == canonical_hash(selected["geometry"])
    assert canonical_hash(selected["payload"]) == selected["witness_hash"]


def test_new_report_keeps_missing_real_inputs_and_source_states(report):
    assert report["actual_calibration"] == "INPUT_REQUIRED"
    assert report["engineering_approval"] == report["factory_applicability"] == "NOT_EVALUATED"
    assert report["native_solves"] == 0
    assert report["main_executed"] is report["real_grant_claim"] is False


def test_views_render_current_geometry_and_failures(report, selected):
    summary = summarize(report)
    for svg in (
        case_plan(selected),
        case_plan(selected, doors=True),
        comparison_plan(report["archived_baseline"], selected),
        clearance_svg(report["clearance_traces"][0]),
    ):
        assert '<svg xmlns="http://www.w3.org/2000/svg"' in svg
    page = review_page(summary)
    assert "INPUT_REQUIRED_ORIGINAL_PHOTO_FILE_MISSING" in page
    assert "R15-04" in page and "SWEPT_BODY_COLLISION" in page
    assert "100mm目标" in page and "原15mm不能" not in page
    assert "fetch(" not in page and "XMLHttpRequest" not in page
    assert "data:image/" not in page


def test_fresh_export_has_hashes_new_witness_and_no_original_image(tmp_path):
    output = tmp_path / "review"
    summary = write_review(ROOT, output)
    assert summary["selected_candidate_id"] == "R15-03"
    raw = json.loads(gzip.decompress((output / "full-new-witnesses.json.gz").read_bytes()))
    assert len(raw["reports"]) == 12
    manifest = json.loads((output / "source-manifest.json").read_bytes())
    for name, digest in manifest["derived_files"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert not any(p.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"} for p in output.iterdir())
    assert manifest["original_photo_published"] is False
    with pytest.raises(ValueError, match="FRESH_R15"):
        write_review(ROOT, output)


@pytest.mark.parametrize(
    "directory", ["r11-r14-ten-door-locker-r1", "r11-r13-physical-calibration-r1"]
)
def test_historical_output_locations_are_protected(directory):
    with pytest.raises(ValueError, match="FRESH_R15"):
        write_review(ROOT, ROOT / "docs/previews/v2.2.2" / directory)


@pytest.mark.parametrize("api", ["solve", "Solve"])
def test_both_native_aliases_blocked_in_current_test_process(api):
    with pytest.raises(RuntimeError, match="R15_NATIVE_FORBIDDEN|R11_FUNCTIONAL_NATIVE_FORBIDDEN"):
        getattr(cp_model.CpSolver(), api)(cp_model.CpModel())


@pytest.mark.parametrize("api", ["solve", "Solve"])
def test_both_native_aliases_are_blocked_in_child_startup(tmp_path, api):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "backend/tests/functional_native_guard")
    env["R11_FUNCTIONAL_GUARD_AUDIT"] = str(tmp_path / "audit")
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ortools.sat.python import cp_model; "
            f"cp_model.CpSolver().{api}(cp_model.CpModel())",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0
    assert "R11_FUNCTIONAL_NATIVE_FORBIDDEN" in r.stderr
    assert any(
        "NATIVE_REQUEST_BLOCKED" in p.read_text() for p in (tmp_path / "audit").glob("*.jsonl")
    )


def test_new_tests_are_in_fast_ci_without_removing_existing_modules():
    text = (ROOT / ".github/workflows/ci-fast.yml").read_text()
    assert text.count("tests/unit/test_v222_r11_r15_local_relayout.py") == 1
    for filename in (
        "test_v222_r11_r14_ten_door_locker.py",
        "test_v222_stage_b_route_refinement.py",
        "test_v222_r11_r10_reverse_sizing.py",
    ):
        assert filename in text


def test_r14_source_and_every_derived_hash_still_validate():
    r = read_r14_archive(ROOT)
    assert r["reports"][3]["home_count"] == 52
    assert r["owner_selection"]["photo_sha256"] is None
    manifest = json.loads((ROOT / R14 / "source-manifest.json").read_bytes())
    assert manifest["historical_records_changed"] is False
