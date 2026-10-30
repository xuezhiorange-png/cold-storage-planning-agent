"""Complete products, independent allocation, original motion and required sweeps."""

import copy
import csv
import gzip
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from build_r11_r14_ten_door_review import summary_report, write_review
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.physical_room_calibration_review import (
    calibration_context,
)
from cold_storage.modules.layout.application.ten_door_locker_review import (
    SOURCE_PATH,
    SOURCE_SHA256,
    bind_owner_selection,
    combine_flow,
    evidence_is_current,
    review_ten_door_selection,
)
from cold_storage.modules.layout.domain.changing_room_motion import door_hits_box
from cold_storage.modules.layout.domain.functional_room_sizing_input import RoomUseConditions
from cold_storage.modules.layout.domain.ten_door_locker_geometry import complete_cabinet_geometry
from cold_storage.modules.layout.domain.ten_door_locker_model import (
    DoorSensitivity,
    actual_door_records,
    complete_inventory,
    complete_inventory_conflicts,
)
from cold_storage.modules.layout.domain.ten_door_locker_sweeps import (
    check_flow_doors,
    validate_door_event,
)
from cold_storage.modules.layout.infrastructure.physical_calibration_evidence import (
    read_calibration_evidence,
)
from cold_storage.modules.layout.infrastructure.ten_door_locker_page import (
    complete_elevation,
    complete_plan,
    review_page,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def no_native():
    def blocked(*args, **kwargs):
        raise RuntimeError("R14_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
            patch.setattr(cp_model.CpSolver, "solve", blocked)
            patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def ctx():
    return calibration_context(read_calibration_evidence(ROOT))


@pytest.fixture(scope="module")
def owner():
    return (ROOT / SOURCE_PATH).read_bytes()


@pytest.fixture(scope="module")
def report(ctx, owner):
    return review_ten_door_selection(ctx, owner)


@pytest.fixture(scope="module")
def good(report):
    return report["reports"][0]


def test_owner_source_is_nominal_selection_not_supplier_approval(ctx, owner):
    b = bind_owner_selection(ctx, owner)
    assert hashlib.sha256(owner).hexdigest() == SOURCE_SHA256
    assert b["status"] == "OWNER_SELECTED_NOMINAL_DESIGN_BASIS"
    assert b["reviewed_selection"]["SELECTED_CABINET_NOMINAL_WIDTH_MM"]["value"] == 850
    assert b["supplier_technical_review"] == b["procurement_acceptance"] == "NOT_EVALUATED"


def test_missing_photo_has_no_invented_image_digest(ctx, owner):
    b = bind_owner_selection(ctx, owner)
    assert b["photo_file"] is b["photo_sha256"] is None
    assert b["photo_evidence_status"] == "INPUT_REQUIRED"


@pytest.mark.parametrize(
    "source", [b"", b"{}", b'{"approved":true}', b"Owner approves another project"]
)
def test_ordinary_json_or_other_text_cannot_bind_selection(ctx, source):
    with pytest.raises(ValueError, match="SOURCE_MISMATCH"):
        bind_owner_selection(ctx, source)


@pytest.mark.parametrize("field", ["project_scope_id", "physical_room_id"])
def test_wrong_project_or_physical_room_is_rejected(ctx, owner, field):
    c = copy.deepcopy(ctx)
    c["overlay"][field] = "another-project-or-room"
    with pytest.raises(ValueError, match="FROZEN_H5"):
        bind_owner_selection(c, owner)


def test_eleven_complete_products_not_twelve_shift_grouped_units(report):
    inv = report["inventory"]
    assert len(inv["cabinet_units"]) == 11
    assert all(
        u["dimensions_mm"] == [850, 390, 1800]
        and not u["partial_unit"]
        and len(u["column_ids"]) == 2
        for u in inv["cabinet_units"]
    )
    assert all(u["shift"] is None for u in inv["cabinet_units"])


def test_middle_cabinet_has_two_shifts_but_one_body(report):
    inv = report["inventory"]
    u = next(x for x in inv["cabinet_units"] if x["id"] == "U06")
    assert u["allocated_shifts"] == [1, 2]
    cols = {c["id"]: c for c in inv["vertical_columns"]}
    assert [cols[k]["shift"] for k in u["column_ids"]] == [1, 2]
    assert len({cols[k]["unit_id"] for k in u["column_ids"]}) == 1


def test_106_people_have_106_unique_cells_and_four_spares(report):
    inv = report["inventory"]
    assert len(inv["person_assignments"]) == 106
    assert len({a["compartment_ids"][0] for a in inv["person_assignments"]}) == 106
    assert sum(c["assigned_person_id"] is None for c in inv["compartments"]) == 4
    for s in (1, 2):
        cells = [c for c in inv["compartments"] if c["shift"] == s]
        assert len(cells) == 55
        assert sum(c["assigned_person_id"] is None for c in cells) == 2


def test_all_columns_have_five_separate_doors_and_no_verified_net_size(report):
    inv = report["inventory"]
    assert len(inv["vertical_columns"]) == 22
    assert len({c["independent_door_id"] for c in inv["compartments"]}) == 110
    assert all(len(c["compartment_ids"]) == 5 for c in inv["vertical_columns"])
    assert all(
        c["net_width_mm"] is c["net_depth_mm"] is c["net_height_mm"] is None
        for c in inv["compartments"]
    )
    assert all(
        c["dimensions_mm"][0] == 425 and "NOT_NET_WIDTH" in c["pitch_basis"]
        for c in inv["vertical_columns"]
    )


def test_actual_door_hardware_stays_unknown(report):
    a = actual_door_records(report["inventory"])
    assert len(a) == 110
    assert all(
        d["actual_hinge"] is d["actual_angle_degrees"] is d["actual_sweep"] is None for d in a
    )
    assert all(d["actual_status"] == "INPUT_REQUIRED" for d in a)


def test_nominal_320_door_face_is_not_exposed_as_internal_clear_height(report):
    for c in report["reports"]:
        assert "cell_height_mm" not in c["conditions"]
        assert c["conditions"]["door_face_height_sensitivity_mm"] == 320
        assert all(v["net_height_mm"] is None for v in c["geometry"]["inventory"]["compartments"])
        assert (
            "NOT_INTERNAL_CLEAR_HEIGHT" in c["geometry"]["legacy_field_semantics"]["cell_height_mm"]
        )


@pytest.mark.parametrize(
    "kind", ["half", "twelve", "dimension", "shift", "shared-cell", "extra-spare"]
)
def test_product_and_assignment_conflicts_fail_closed(ctx, report, kind):
    inv = copy.deepcopy(report["inventory"])
    if kind == "half":
        inv["cabinet_units"][0]["partial_unit"] = True
    elif kind == "twelve":
        inv["cabinet_units"].append(copy.deepcopy(inv["cabinet_units"][0]))
    elif kind == "dimension":
        inv["cabinet_units"][0]["dimensions_mm"][0] = 425
    elif kind == "shift":
        inv["cabinet_units"][0]["shift"] = 1
    elif kind == "shared-cell":
        inv["person_assignments"][-1]["compartment_ids"] = inv["person_assignments"][0][
            "compartment_ids"
        ][:]
    else:
        inv["compartments"][0]["assigned_person_id"] = None
    assert complete_inventory_conflicts(inv, ctx["demand"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("shift_users", [52, 53]),
        ("simultaneous_room_users", 52),
        ("total_capacity", 106),
        ("compartments_per_person", 2),
        ("total_columns", 21),
    ],
)
def test_fixed_project_design_basis_cannot_be_reduced(ctx, key, value):
    demand = copy.deepcopy(ctx["demand"])
    demand[key] = value
    with pytest.raises(ValueError, match="PROJECT_BASIS"):
        complete_inventory(demand, DoorSensitivity("ALL_LEFT"))


@pytest.mark.parametrize(
    "p",
    [
        DoorSensitivity("UNKNOWN"),
        DoorSensitivity("MIRRORED", angle_degrees=80),
        DoorSensitivity("ALL_LEFT", leaf_width_mm=426),
        DoorSensitivity("ALL_LEFT", leaf_height_mm=400),
        DoorSensitivity("ALL_LEFT", leaf_thickness_mm=0),
        DoorSensitivity("ALL_LEFT", bottom_mm=True),
    ],
)
def test_unsupported_or_inconsistent_door_configuration_not_silently_replaced(p):
    with pytest.raises(ValueError):
        p.checked()


def test_nominal_850_by_390_envelope_is_used_for_each_body(good):
    for u in good["geometry"]["inventory"]["cabinet_units"]:
        x, y, r, t = u["bounds_mm"]
        assert (r - x, t - y) == (850, 390)
    assert good["geometry"]["metrics"]["cabinet_footprint_mm2"] == 3646500


def test_conditional_centers_and_frames_are_independent_of_net_cell_sizes(good):
    g = good["geometry"]
    for c in g["inventory"]["vertical_columns"]:
        x, _, right, _ = c["bounds_mm"]
        assert c["exact_front_center_x"] == dict(numerator=x + right, denominator=2, unit="mm")
    assert all(
        d["conditional_front_frame_mm"] == [12, 13]
        for d in good["door_profiles"][0]["doors"]["registry"]
    )
    assert all(c["net_width_mm"] is None for c in g["inventory"]["compartments"])


def test_existing_two_portals_are_not_moved(good, ctx):
    assert good["geometry"]["room"]["portals"] == ctx["room"]["portals"]
    assert [p["clear_width_mm"] for p in good["geometry"]["room"]["portals"]] == [1500, 1500]
    assert all(p["valid"] for p in good["geometry"]["waiting_evaluation"]["portal_results"])


def test_both_rooms_have_identical_conditions_inside_each_parameter_group(report):
    a, b, c, d = report["reports"]
    assert a["conditions"] == b["conditions"]
    assert c["conditions"] == d["conditions"]
    assert (
        a["conditions"]["finish_mm"],
        a["conditions"]["installation_gap_mm"],
        a["margin_target_mm"],
    ) == (20, 20, 50)
    assert (
        c["conditions"]["finish_mm"],
        c["conditions"]["installation_gap_mm"],
        c["margin_target_mm"],
    ) == (30, 40, 100)


def test_both_53_user_flows_are_reexecuted_in_good_cases(report):
    for case in report["reports"][:2]:
        assert case["home_count"] == 53 and case["completed_users"] == [53, 53]
        for f in case["closed_door_flows"]:
            assert f["initial_service_occupancy"] == 53
            assert f["completed_users"] == len(f["completed_person_ids"]) == 53
            assert not f["blocker"]
            ops = {e["operation"] for e in f["events"]}
            assert {
                "ENTER_PORTAL",
                "TO_PERSONAL_LOCKER",
                "PARALLEL_STANDING_CHANGE",
                "EXIT_PORTAL",
            } <= ops


def test_unknown_actual_hardware_never_inherits_conditional_pass(report):
    assert report["actual_calibration"] == "INPUT_REQUIRED"
    assert report["engineering_approval"] == report["factory_applicability"] == "NOT_EVALUATED"
    assert all(
        p["combined"]["actual_functional_status"] == "INPUT_REQUIRED"
        for c in report["reports"]
        for p in c["door_profiles"]
    )


def test_new_sweeps_check_both_shifts_all_212_open_events(good):
    for p in good["door_profiles"]:
        d = p["doors"]
        assert d["status"] == "CONDITIONAL_DOOR_EVENTS_PASS"
        assert d["served_compartments"] == 106
        assert d["checked_open_events"] == d["required_open_events"] == 212
        assert d["complete_106_person_coverage"]
        assert all(not e["proof"]["conflicts"] for e in d["events"])


def test_mirrored_profile_is_distinct_not_default_actual_hardware(good):
    a, b = good["door_profiles"]
    ad = {d["id"]: d for d in a["doors"]["registry"]}
    bd = {d["id"]: d for d in b["doors"]["registry"]}
    assert ad["U01-R-T1-DOOR"]["hinge_side"] == "LEFT"
    assert bd["U01-R-T1-DOOR"]["hinge_side"] == "RIGHT"
    assert a["witness_hash"] != b["witness_hash"]


def test_door_margin_is_not_hidden_by_closed_door_50mm_margin(good):
    for p in good["door_profiles"]:
        assert p["combined"]["minimum_declared_margin_lower_bound_mm"] == 15
        assert not p["combined"]["margin_target_met"]
        assert p["doors"]["minimum_door_clearance_lower_bound"]["extra_mm"] == 15


def test_30_40_failures_keep_all_53_users_and_do_not_inherit_old_pass(report):
    c, d = report["reports"][2:]
    assert [c["home_count"], d["home_count"]] == [38, 52]
    assert [c["missing_home_count"], d["missing_home_count"]] == [15, 1]
    for case in (c, d):
        assert not case["closed_door_flows"]
        assert all(not p["combined"]["complete"] for p in case["door_profiles"])
        assert case["geometry"]["demand"]["simultaneous_room_users"] == 53


def test_thick_door_collision_prevents_combined_pass_even_if_closed_flow_passes(good):
    g = good["geometry"]
    d = check_flow_doors(
        g, good["closed_door_flows"], DoorSensitivity("ALL_LEFT", leaf_thickness_mm=100)
    )
    assert d["status"] == "CONFIGURATION_NOT_FIT"
    assert any(
        x["code"] == "HINGED_DOOR_3D_COLLISION"
        for e in d["events"]
        for x in e["proof"]["conflicts"]
    )
    assert not combine_flow({"shifts": good["closed_door_flows"]}, d)["complete"]


def test_sweep_height_distinguishes_plan_projection_from_3d(good):
    d = good["door_profiles"][0]["doors"]["registry"][0]
    x, y = d["hinge_mm"]
    high = [x + 20, y + 20, 500, x + 100, y + 100, 600]
    assert door_hits_box(d, high, projection=True)
    assert not door_hits_box(d, high)
    low = high[:]
    low[2], low[5] = 100, 300
    assert door_hits_box(d, low)


def test_missing_one_store_open_event_is_not_complete(good):
    flows = copy.deepcopy(good["closed_door_flows"])
    i = next(i for i, e in enumerate(flows[0]["events"]) if e["operation"] == "OPEN_FOR_STORE")
    del flows[0]["events"][i]
    result = check_flow_doors(good["geometry"], flows, DoorSensitivity("ALL_LEFT"))
    assert not result["complete_106_person_coverage"]
    assert result["status"] != "CONDITIONAL_DOOR_EVENTS_PASS"


def test_duplicate_door_identity_is_rejected(good):
    registry = copy.deepcopy(good["door_profiles"][0]["doors"]["registry"])
    registry[1]["id"] = registry[0]["id"]
    s = good["geometry"]["snapshots"][0]
    with pytest.raises(ValueError, match="110_DISTINCT"):
        validate_door_event(good["geometry"], s, s["people"], registry, expected_people_count=53)


def test_missing_waiting_person_cannot_be_hidden_in_new_sweep_check(good):
    s = good["geometry"]["snapshots"][0]
    r = validate_door_event(
        good["geometry"],
        s,
        s["people"][:-1],
        good["door_profiles"][0]["doors"]["registry"],
        expected_people_count=53,
    )
    assert any(x["code"] == "LIVE_PEOPLE_COUNT_OR_IDENTITY_MISMATCH" for x in r["conflicts"])


@pytest.mark.parametrize("change", ["conditions", "geometry", "hinge", "source", "hash"])
def test_changed_input_or_evidence_invalidates_new_witness(ctx, owner, good, change):
    c = copy.deepcopy(good)
    p = c["door_profiles"][0]
    assert evidence_is_current(ctx, owner, c, p)
    if change == "conditions":
        c["conditions"]["finish_mm"] += 1
    elif change == "geometry":
        c["geometry"]["model"]["homes"][0]["bounds_mm"][0] += 1
    elif change == "hinge":
        p["hypothesis"]["hinges"] = "MIRRORED"
    elif change == "source":
        p["payload"]["owner"]["source_sha256"] = "0" * 64
    else:
        p["witness_hash"] = "sha256:" + "0" * 64
    assert not evidence_is_current(ctx, owner, c, p)


def test_storage_counts_do_not_prove_clothing_partition_or_reach(report):
    s = report["storage_function_checks"]
    assert s["capacity_arithmetic"]["status"] == "SATISFIED_ARITHMETIC_ONLY"
    assert all(v["status"] == "INPUT_REQUIRED" for k, v in s.items() if k != "capacity_arithmetic")
    assert s["actual_internal_clear_dimensions"]["nominal_400_360_320_is_net"] is False
    assert not s["work_private_separation"]["automatic_extra_partition"]


def test_exact_outer_envelope_comparison_not_area_only_functional_claim(report):
    d = report["difference_from_400_500_reference"]
    assert d["new_floor_footprint_mm2"] == 11 * 850 * 390 == 3646500
    assert d["footprint_delta_mm2"] == -753500
    assert d["summed_width_delta_mm"] == 550


def test_wrong_selected_envelope_is_not_silently_adapted(ctx):
    with pytest.raises(ValueError, match="SELECTED_COMPLETE"):
        complete_cabinet_geometry(ctx["room"], ctx["demand"], RoomUseConditions(), 3550, 50)


def test_same_inputs_are_deterministic_and_context_is_read_only(ctx, owner, report):
    before = json.dumps(ctx, sort_keys=True)
    other = review_ten_door_selection(ctx, owner)
    assert [p["witness_hash"] for c in other["reports"] for p in c["door_profiles"]] == [
        p["witness_hash"] for c in report["reports"] for p in c["door_profiles"]
    ]
    assert json.dumps(ctx, sort_keys=True) == before


def test_figures_are_mm_scaled_and_all_11_cabinets_visible(good):
    for svg in (complete_plan(good), complete_plan(good, doors=True), complete_elevation(good)):
        assert ET.fromstring(svg).tag.endswith("svg")
    plan = complete_plan(good)
    assert all(f"U{i:02}" in plan for i in range(1, 12))
    assert "U06" in complete_elevation(good) and "不是净宽" in complete_elevation(good)


def test_page_distinguishes_unreviewed_geometry_from_owner_selection(report):
    text = review_page(summary_report(report))
    assert "照片Hash为null" in text and "425mm" in text
    assert "INPUT_REQUIRED" in text and "NOT_EVALUATED" in text
    assert "无跨班" not in text or "格口" in text
    assert "fetch(" not in text and "localStorage" not in text


def test_new_test_file_is_present_in_actual_fast_ci_list():
    text = (ROOT / ".github/workflows/ci-fast.yml").read_text()
    for module in (
        "test_v222_r11_r14_ten_door_locker.py",
        "test_v222_r11_r13_physical_calibration.py",
        "test_v222_r11_r12_site_impact.py",
        "test_v222_r11_r10_reverse_sizing.py",
    ):
        assert text.count("tests/unit/" + module) == 1


def test_fresh_export_has_110_allocation_rows_new_hashes_and_valid_svg(tmp_path):
    out = tmp_path / "review"
    s = write_review(ROOT, out)
    with (out / "compartment-allocation.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert b"\r" not in (out / "compartment-allocation.csv").read_bytes()
    assert len(rows) == 110 and sum(bool(r["person_id"]) for r in rows) == 106
    raw = json.loads(gzip.decompress((out / "full-new-witnesses.json.gz").read_bytes()))
    assert len(raw["reports"]) == 4 and s["physical_room_count"] == 1
    for path in out.glob("*.svg"):
        ET.fromstring(path.read_bytes())
    manifest = json.loads((out / "source-manifest.json").read_text())
    assert all(
        hashlib.sha256((out / n).read_bytes()).hexdigest() == d
        for n, d in manifest["derived_files"].items()
    )
    with pytest.raises(ValueError, match="FRESH_R14"):
        write_review(ROOT, out)


def test_historical_preview_is_never_an_output_target():
    with pytest.raises(ValueError, match="FRESH_R14"):
        write_review(
            ROOT, ROOT / "docs/previews/v2.2.2/r11-r13-physical-input-calibration-r1/forbidden"
        )


def test_child_guard_rejects_both_native_apis(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "backend/tests/functional_native_guard")
    env["R11_FUNCTIONAL_GUARD_AUDIT"] = str(tmp_path / "guard")
    code = (
        "from ortools.sat.python import cp_model\n"
        "for method in ('solve','Solve'):\n"
        " try: getattr(cp_model.CpSolver(),method)(cp_model.CpModel())\n"
        " except RuntimeError as e: print(str(e))\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert (
        r.returncode == 0 and r.stdout.count("R11_FUNCTIONAL_NATIVE_FORBIDDEN_IN_THIS_PROCESS") == 2
    )
    assert (
        sum(
            p.read_text().count("NATIVE_REQUEST_BLOCKED")
            for p in (tmp_path / "guard").glob("*.jsonl")
        )
        == 2
    )


def test_r13_original_manifest_and_sources_stay_exact(ctx):
    assert all(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        for name, digest in ctx["source_hashes"].items()
    )
    old = ROOT / "docs/previews/v2.2.2/r11-r13-physical-input-calibration-r1"
    m = json.loads((old / "source-manifest.json").read_text())
    assert all(
        hashlib.sha256((old / name).read_bytes()).hexdigest() == digest
        for name, digest in m["derived_files"].items()
    )
