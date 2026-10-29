"""Finite reverse sizing, complete two-shift proof, margins and inherited child guard."""

import copy
import gzip
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from http.server import HTTPServer
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.room_reverse_sizing_review import (
    evaluate_sizing_point,
    preview_request,
    preview_room_sizing,
    select_designs,
)
from cold_storage.modules.layout.domain.functional_room_sizing_input import (
    RoomUseConditions,
    SizingSearch,
    search_points,
)
from cold_storage.modules.layout.domain.h5_space_relayout import relayout_geometry
from cold_storage.modules.layout.domain.reverse_sizing_geometry import hypothetical_room
from cold_storage.modules.layout.infrastructure.room_reverse_sizing_page import (
    comparison_svg,
    plan_svg,
    plot_record,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def no_native():
    def blocked(*a, **k):
        raise RuntimeError("R11_R10_TEST_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as m:
        if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
            m.setattr(cp_model.CpSolver, "solve", blocked)
            m.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def sources():
    c = json.loads(
        (
            ROOT
            / "docs/previews/v2.2.2/r11-r5-h5-practical-changing-review-r1"
            / "project-and-room-catalog.json"
        ).read_bytes()
    )
    return (
        c,
        (ROOT / "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt").read_bytes(),
        (ROOT / "docs/tasks/V2_2_2-r11-r8-reviewed-cabinet-front-facts.txt").read_bytes(),
    )


def point(L=26331, W=3250, m=0, p="MIXED"):
    return dict(
        length_mm=L,
        width_mm=W,
        margin_mm=m,
        profile=p,
        mode="A_FIXED_LENGTH" if L == 26331 else "B_JOINT_DIMENSIONS",
    )


@pytest.fixture(scope="module")
def cases(sources):
    c = sources[0]
    room = c["groups"][0]["room"]
    demand = c["demands"]["INTERNAL_PARTITION"]
    points = [
        point(),
        point(W=3440, p="NORTH_NORMAL_SOUTH_ROTATED"),
        point(W=3550, m=50),
        point(L=28000, W=4350, m=150, p="NORTH_NORMAL_SOUTH_ROTATED"),
    ]
    return [evaluate_sizing_point(room, demand, RoomUseConditions(), p) for p in points]


def test_owner_facts_retained_and_dimensions_never_promoted(sources):
    c, s7, s8 = sources
    grid = SizingSearch(
        widths_mm=(3250,),
        joint_lengths_mm=(26331,),
        joint_widths_mm=(3250,),
        margin_targets_mm=(0,),
        profiles=("MIXED",),
        derived_width_checkpoints=False,
    )
    x = preview_room_sizing(c, s7, s8, RoomUseConditions(), grid)
    facts = x["binding"]["reviewed_design_requirements"]
    assert facts["USERS_PER_SHIFT"]["value"] == 53 and facts["CABINET_COLUMNS"]["value"] == 22
    assert all(
        f["source_label"] == "OWNER_CONFIRMED"
        and f["project_scope_id"] == x["binding"]["project_scope_id"]
        for f in facts.values()
    )
    assert "column_width_mm" not in facts
    assert x["conditions_classification"] == "HYPOTHETICAL_NOT_APPROVED"
    assert x["source_physical_room_count"] == 1 and x["source_records"] == ["P01", "P02"]
    assert x["source_area_m2"] == "85.575750" and x["actual_functional_status"] == "INPUT_REQUIRED"
    assert not x["new_main"] and not x["new_grant"] and not x["new_claim"]


@pytest.mark.parametrize(
    "raw",
    [
        {"owner_facts": {}},
        {"conditions": {"source_label": "OWNER_CONFIRMED"}},
        {"search": {"status": "APPROVED"}},
    ],
)
def test_json_status_labels_and_fact_overrides_rejected(raw):
    with pytest.raises(ValueError):
        preview_request(raw)


def test_unreviewed_owner_source_rejected(sources):
    c, s7, _ = sources
    with pytest.raises(ValueError):
        preview_room_sizing(
            c, s7, b"CHANGING_LOCATION=PERSONAL_CABINET_FRONT", RoomUseConditions(), SizingSearch()
        )


def test_full_default_grid_is_finite_and_covers_owner_points():
    points = search_points(RoomUseConditions(), SizingSearch())
    assert len(points) == 396
    assert {3250, 3300, 3350, 3400, 3440, 3460, 3500, 3600} <= {
        p["width_mm"] for p in points if p["mode"] == "A_FIXED_LENGTH"
    }
    assert {27000, 28000, 30000} <= {p["length_mm"] for p in points}
    assert {0, 50, 100, 150} == {p["margin_mm"] for p in points}
    assert len(
        {(p["length_mm"], p["width_mm"], p["margin_mm"], p["profile"]) for p in points}
    ) == len(points)
    assert points == search_points(RoomUseConditions(), SizingSearch())


@pytest.mark.parametrize(
    "c",
    [
        RoomUseConditions(transport_width_mm=449),
        RoomUseConditions(transport_depth_mm=649),
        RoomUseConditions(activity_width_mm=440),
        RoomUseConditions(aisle_required_mm=1000),
    ],
)
def test_not_shrinking_bodies_or_passage_to_fit(c):
    with pytest.raises(ValueError):
        c.checked()


@pytest.mark.parametrize(
    "search",
    [
        SizingSearch(widths_mm=(3250, 3250)),
        SizingSearch(widths_mm=(3200,)),
        SizingSearch(margin_targets_mm=(True,)),
        SizingSearch(derived_width_checkpoints="yes"),
        SizingSearch(profiles=("FAKE",)),
    ],
)
def test_invalid_ranges_and_options_fail_before_geometry(search):
    with pytest.raises(ValueError):
        search_points(RoomUseConditions(), search)


def test_preview_size_limit_is_not_an_engineering_infeasibility():
    with pytest.raises(ValueError, match="FINITE_PREVIEW_LIMIT"):
        search_points(
            RoomUseConditions(),
            SizingSearch(
                widths_mm=tuple(range(3250, 3450, 10)),
                joint_lengths_mm=tuple(range(27000, 30001, 200)),
                joint_widths_mm=tuple(range(3250, 3450, 10)),
            ),
        )


def test_original_room_and_source_portals_are_immutable(sources):
    r = copy.deepcopy(sources[0]["groups"][0]["room"])
    before = copy.deepcopy(r)
    h = hypothetical_room(r, 28000, 4350)
    assert r == before and h is not r and h["hypothetical"]
    assert h["world_bounds_mm"] is None and "candidate_hash" not in h
    assert h["original_engineering_status"] == "NOT_HISTORICAL_OR_ENGINEERING_APPROVED"
    assert h["portals"][0]["segment_mm"] == [[28000, 875], [28000, 2375]]
    assert h["portals"][1]["segment_mm"] == before["portals"][1]["segment_mm"]
    assert h["boundary_mapping"]["portal_mappings"][0]["position_changed"]
    assert (
        h["boundary_mapping"]["site_footprint_and_external_access"]
        == "NOT_EVALUATED_REVALIDATION_REQUIRED"
    )


def test_width_only_keeps_portal_coordinates_but_not_external_approval(sources):
    r = sources[0]["groups"][0]["room"]
    h = hypothetical_room(r, 26331, 3550)
    assert [p["segment_mm"] for p in h["portals"]] == [p["segment_mm"] for p in r["portals"]]
    assert h["boundary_mapping"]["north_delta_mm"] == 300
    assert (
        h["boundary_mapping"]["site_footprint_and_external_access"]
        == "NOT_EVALUATED_REVALIDATION_REQUIRED"
    )


def test_r9_baseline_geometry_and_10mm_reproduced(cases, sources):
    c = cases[0]
    g = c["geometry"]
    catalog = sources[0]
    old = relayout_geometry(
        catalog["groups"][0]["room"],
        catalog["demands"]["INTERNAL_PARTITION"],
        "MIXED_NORTH_RESERVE",
    )
    assert [h["bounds_mm"] for h in g["model"]["homes"]] == [
        h["bounds_mm"] for h in old["model"]["homes"]
    ]
    assert g["inventory"] == old["inventory"]
    assert c["margins"]["north_waiting_finished_wall_margin_mm"] == 10
    assert c["summary"]["minimum_margin_mm"] == 0


def test_r9_30mm_finish_failure_is_not_reinterpreted(sources):
    c = sources[0]
    x = evaluate_sizing_point(
        c["groups"][0]["room"],
        c["demands"]["INTERNAL_PARTITION"],
        RoomUseConditions(finish_mm=30),
        point(),
    )
    assert x["summary"]["home_count"] == 47
    assert x["summary"]["static_status"] == "STATIC_GEOMETRY_REJECTED"
    assert x["summary"]["full_flow_status"] == "NOT_EVALUATED_UPSTREAM_REJECTED"
    assert x["shifts"] == []


@pytest.mark.parametrize("index", range(4))
def test_full_53_users_and_110_compartments_both_shifts(cases, index):
    c = cases[index]
    g = c["geometry"]
    assert (
        g["metrics"]["columns"] == 22
        and g["metrics"]["compartments"] == 110
        and g["metrics"]["home_count"] == 53
    )
    assert c["summary"]["full_flow_status"] == "CONDITIONAL_FLOW_PASS"
    for s in c["shifts"]:
        assert s["initial_service_occupancy"] == s["completed_users"] == 53
        assert len(set(s["served_person_ids"])) == 53 and len(set(s["completed_person_ids"])) == 53
        assert not s["remaining_inside"] and not s["not_entered_people"]
        assert all(e["proof"]["status"] == "VERIFIED_UNDER_HYPOTHESES" for e in s["events"])
        first = next(e for e in s["events"] if e["operation"] == "TO_PERSONAL_LOCKER")
        assert first["inside_people"] == 53
        assert all(
            e["inside_people"] + e["departed_people"] + e["not_entered_people"] == 53
            for e in s["events"]
        )
        assert s["full_shift_seconds"] is None
    assert not g["model"]["benches"] and g["model"]["changing_zone"] is None


@pytest.mark.parametrize("index", range(4))
def test_complete_position_replay_no_teleportation(cases, index):
    for s in cases[index]["shifts"]:
        current = {}
        exited = set()
        for e in s["events"]:
            p = e["proof"]
            assert {o["id"]: o for o in p["people_before"]} == current
            if e["operation"] == "ENTER_PORTAL":
                current[p["person_id"]] = p["interior_person"]
            elif e["operation"] in {
                "REACH_WAITING_POSITION",
                "TO_PERSONAL_LOCKER",
                "TO_PACKAGING_PORTAL",
            }:
                assert p["source"] == current[p["person_id"]]
                current[p["person_id"]] = p["target"]
            elif e["operation"] == "EXIT_PORTAL":
                del current[p["person_id"]]
                exited.add(p["person_id"])
        assert not current and len(exited) == 53


def test_3440_is_full_witness_only_for_checked_template_not_a_general_rule(cases, sources):
    c = cases[1]
    assert c["summary"]["full_flow_verified"] and c["summary"]["minimum_margin_mm"] == 0
    catalog = sources[0]
    other = evaluate_sizing_point(
        catalog["groups"][0]["room"],
        catalog["demands"]["INTERNAL_PARTITION"],
        RoomUseConditions(),
        point(W=3440, m=100, p="NORTH_NORMAL_SOUTH_ROTATED"),
    )
    assert not other["summary"]["full_flow_verified"]
    assert other["summary"]["actual_engineering_approval"] == "INPUT_REQUIRED"


def test_margin_is_measured_not_copied_from_request(cases, sources):
    c = cases[2]
    assert c["summary"]["minimum_margin_mm"] == 50 and c["summary"]["north_wall_margin_mm"] == 60
    catalog = sources[0]
    f = evaluate_sizing_point(
        catalog["groups"][0]["room"],
        catalog["demands"]["INTERNAL_PARTITION"],
        RoomUseConditions(finish_mm=30),
        point(W=3550, m=50),
    )
    assert f["summary"]["full_flow_verified"] and not f["summary"]["margin_target_met"]
    assert f["summary"]["minimum_margin_mm"] == 40
    assert f["summary"]["actual_engineering_approval"] == "INPUT_REQUIRED"


def test_generous_design_and_actual_dimension_chain(cases):
    c = cases[3]
    m = c["margins"]
    assert (
        c["summary"]["minimum_margin_mm"] == 150
        and m["north_waiting_finished_wall_margin_mm"] == 160
    )
    assert sum(x["mm"] for x in m["section_chain_mm"]) == 4350
    assert c["summary"]["area_m2"] == "121.800000" and c["summary"]["added_area_m2"] == "36.224250"
    assert all(
        x["location"] and x["source_label"].startswith("ENGINEERING_DERIVED")
        for x in m["families"].values()
    )
    assert m["other_unapproved_limits"]["horizontal_reach_reserve_mm"] == 70


def test_robust_width_only_alternative_is_actually_checked(sources):
    c = sources[0]
    r = evaluate_sizing_point(
        c["groups"][0]["room"],
        c["demands"]["INTERNAL_PARTITION"],
        RoomUseConditions(finish_mm=30, installation_gap_mm=40),
        point(W=3600, m=50),
    )
    assert r["summary"]["completed_users"] == [53, 53]
    assert r["summary"]["minimum_margin_mm"] == 40 and not r["summary"]["margin_target_met"]
    stronger = evaluate_sizing_point(
        c["groups"][0]["room"],
        c["demands"]["INTERNAL_PARTITION"],
        RoomUseConditions(finish_mm=30, installation_gap_mm=40),
        point(W=3850, m=100),
    )
    assert stronger["summary"]["completed_users"] == [53, 53]
    assert stronger["summary"]["minimum_margin_mm"] == 70
    assert stronger["summary"]["area_m2"] == "101.374350"
    # 70mm meets the separate 50mm robustness review target, not the 100mm padding target.
    assert not stronger["summary"]["margin_target_met"]


def test_sizing_goals_do_not_choose_unvalidated_or_tight_as_recommendation(cases):
    rows = [c["summary"] for c in cases]
    fake = dict(
        rows[0], id="FAKE_TINY", area_mm2=1, minimum_margin_mm=500, full_flow_verified=False
    )
    x = select_designs([fake, *rows], 50)
    assert x["A_MIN_VERIFIED_AREA"] == rows[0]["id"]
    assert x["B_LARGER_MARGIN"] == rows[3]["id"] and x["C_MIN_BOUNDARY_CHANGE"] == rows[2]["id"]
    assert x["recommended_for_review"] != rows[0]["id"]
    assert select_designs([fake], 50)["conclusion"] == "NO_FULLY_VALIDATED_CANDIDATE_IN_TESTED_SET"


def test_same_input_has_identical_complete_witness(cases, sources):
    c = sources[0]
    r = evaluate_sizing_point(
        c["groups"][0]["room"], c["demands"]["INTERNAL_PARTITION"], RoomUseConditions(), point()
    )
    assert r["summary"]["witness_sha256"] == cases[0]["summary"]["witness_sha256"]
    assert json.dumps(r, sort_keys=True) == json.dumps(cases[0], sort_keys=True)


def test_original_inventory_demand_cannot_be_reduced(sources):
    c = sources[0]
    d = copy.deepcopy(c["demands"]["INTERNAL_PARTITION"])
    d["simultaneous_room_users"] = 52
    with pytest.raises(ValueError, match="53_53_22_110"):
        evaluate_sizing_point(c["groups"][0]["room"], d, RoomUseConditions(), point())


def test_height_is_not_truncated_in_activity_proof(sources):
    c = sources[0]
    r = evaluate_sizing_point(
        c["groups"][0]["room"],
        c["demands"]["INTERNAL_PARTITION"],
        RoomUseConditions(body_height_mm=1850),
        point(),
    )
    assert r["summary"]["full_flow_verified"]
    for s in r["shifts"]:
        for e in s["events"]:
            if e["operation"] == "PARALLEL_STANDING_CHANGE":
                assert all(a["volumes_mm"][0][5] == 1850 for a in e["proof"]["activity_volumes"])


def test_svg_dimensions_are_from_candidate_and_comparison_common_scale(cases):
    p = plot_record(cases[3])
    svg = plan_svg(p)
    ET.fromstring(svg)
    assert "28000 × 4350mm" in svg and "121.800000" in svg
    assert "1500mm Portal" in svg and "INPUT_REQUIRED" in svg
    ET.fromstring(comparison_svg({str(i): plot_record(c) for i, c in enumerate(cases[:3])}))


def test_parent_native_requests_are_blocked_without_execution():
    for api in ("solve", "Solve"):
        with pytest.raises(RuntimeError, match="NATIVE_FORBIDDEN"):
            getattr(cp_model.CpSolver(), api)(None)


def test_child_native_startup_guard_covers_both_apis(tmp_path):
    env = dict(os.environ, R11_FUNCTIONAL_GUARD_AUDIT=str(tmp_path / "audit"))
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "backend/tests/functional_native_guard"), str(ROOT / "backend/src")]
    )
    code = """import os
from ortools.sat.python import cp_model
assert os.environ['R11_FUNCTIONAL_GUARD_ACTIVE']=='1'
for api in ('solve','Solve'):
    assert getattr(cp_model.CpSolver,api).__module__=='sitecustomize'
    try:getattr(cp_model.CpSolver(),api)(None)
    except RuntimeError:pass
    else:raise AssertionError('NATIVE_NOT_BLOCKED')
"""
    r = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, r.stdout + r.stderr
    events = [
        json.loads(line)
        for p in (tmp_path / "audit").glob("*.jsonl")
        for line in p.read_text().splitlines()
    ]
    assert [e["kind"] for e in events].count("GUARD_READY") == 1
    assert [e["kind"] for e in events].count("NATIVE_REQUEST_BLOCKED") == 2


def test_whitelist_has_no_stage_b_or_historical_native_test_modules():
    from validate_r11_r10_whitelist import ALLOWED, ARCHITECTURE_ALLOWED

    assert len(set(ALLOWED)) == len(ALLOWED)
    assert all(
        "test_v222_r11_" in p
        or p.endswith(
            ("test_v222_functional_room_fit.py", "test_v222_functional_project_input_binding.py")
        )
        for p in ALLOWED
    )
    assert all(
        p.startswith("tests/architecture/test_") and p.endswith(".py") for p in ARCHITECTURE_ALLOWED
    )
    assert not any("stage_b" in p for p in ALLOWED)


def test_preview_http_api_returns_real_flow_and_rejects_approval_override(tmp_path):
    from serve_r11_r10_sizing_preview import preview_handler

    (tmp_path / "index.html").write_text("<html>Functional sizing review only</html>")
    (tmp_path / "reverse-sizing-report.md").write_text("Saved functional evidence only")
    with HTTPServer(("127.0.0.1", 0), preview_handler(ROOT, tmp_path)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(url + "/reverse-sizing-report.md") as response:
                assert response.read() == b"Saved functional evidence only"
            with pytest.raises(urllib.error.HTTPError) as invalid_path:
                urllib.request.urlopen(url + "/%2e%2e%2findex.html")
            assert invalid_path.value.code == 404
            request = {
                "search": {
                    "widths_mm": [3250],
                    "joint_lengths_mm": [26331],
                    "joint_widths_mm": [3250],
                    "margin_targets_mm": [0],
                    "profiles": ["MIXED"],
                    "derived_width_checkpoints": False,
                }
            }
            with urllib.request.urlopen(
                urllib.request.Request(
                    url + "/preview",
                    data=json.dumps(request).encode(),
                    headers={"Content-Type": "application/json"},
                )
            ) as response:
                body = json.load(response)
            row = body["data"]["candidates"][0]
            assert (
                row["completed_users"] == [53, 53]
                and row["actual_engineering_approval"] == "INPUT_REQUIRED"
            )
            with urllib.request.urlopen(url + "/evidence/" + row["id"]) as response:
                proof = json.loads(gzip.decompress(response.read()))
            assert (
                proof["summary"]["witness_sha256"] == row["witness_sha256"]
                and len(proof["shifts"]) == 2
            )
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(
                    urllib.request.Request(
                        url + "/preview",
                        data=b'{"owner_facts":{}}',
                        headers={"Content-Type": "application/json"},
                    )
                )
            assert error.value.code == 400
        finally:
            server.shutdown()
            thread.join(timeout=10)
