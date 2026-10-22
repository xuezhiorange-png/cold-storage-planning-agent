"""Offline source-bound geometry tests, never real layout/Truck search."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_review as build
import offline_functional_fit as fit
import offline_functional_renderer as renderer


@pytest.fixture(scope="module")
def audit() -> dict[str, Any]:
    root = os.environ.get("STAGE_B_PREFLIGHT_ARTIFACT_ROOT")
    assert root, "Explicit authorized evidence root required"
    return fit.audit_rooms(Path(root))


@pytest.fixture(autouse=True)
def no_search(monkeypatch: pytest.MonkeyPatch) -> None:
    from cold_storage.modules.layout.application import access_routing as application
    from cold_storage.modules.layout.domain import access_routing as domain
    from cold_storage.modules.layout.domain import truck_parameter_input as r13

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("OFFLINE_FUNCTIONAL_REVIEW_CANNOT_SEARCH")

    monkeypatch.setattr(application, "route_site_placement", forbidden)
    monkeypatch.setattr(application, "validate_truck_maneuver_chain", forbidden)
    monkeypatch.setattr(domain, "validate_truck_maneuver_chain", forbidden)
    monkeypatch.setattr(r13, "preview_parameterized_truck", forbidden)


def run(doc: dict[str, Any], root: Path) -> dict[str, Any]:
    return fit.evaluate(build.seal_synthetic(doc, root, "test-evidence.json"), root)


@pytest.mark.parametrize("index", range(24))
def test_each_real_room_source_geometry_portals_and_missing_function(
    audit: Any, index: int
) -> None:
    r = audit["ROOMS"][index]
    assert r["FUNCTIONAL_FIT_STATUS"] == "INPUT_REQUIRED"
    assert (
        r["AREA_AUTHORITY_M2"]
        == {"office": 60, "changing_room": 40, "coating_room": 80}[r["ZONE_CODE"]]
    )
    assert r["ROOM_AREA_MM2"] >= r["AREA_AUTHORITY_M2"] * 1000000
    assert r["ROOM_AREA_MM2"] == r["ROOM_WIDTH_MM"] * r["ROOM_DEPTH_MM"]
    assert r["RAW_CANDIDATE_SHA256"] and r["SOURCE_GEOMETRY_HASH"]
    assert not r["PROJECT_FUNCTIONAL_FIT_APPROVED"]
    if r["ZONE_CODE"] == "office":
        assert r["PORTALS"] == []  # spatial MUST is not a personnel door
    for p in r["PORTALS"]:
        assert p["DOOR_SWING"] is None and p["PORTAL_FUNCTIONAL_ACCESS"] == "NOT_EVALUATED"
        assert p["LOCAL_SEGMENT_MM"] == [fit.local_point(x, r) for x in p["WORLD_SEGMENT_MM"]]
        assert p["ORIGINAL"]["access_ref"] == r["ZONE_CODE"]


def test_exact_eight_twentyfour_and_extreme_geometry_are_not_inferred(audit: Any) -> None:
    assert audit["CANDIDATES_AUDITED"] == 8 and audit["ROOMS_AUDITED"] == 24
    short = {(r["ZONE_CODE"], r["SHORT_EDGE_MM"]) for r in audit["ROOMS"]}
    assert {
        ("office", 1656),
        ("changing_room", 875),
        ("changing_room", 977),
        ("coating_room", 1950),
    } <= short
    assert len({r["CANDIDATE_ID"] for r in audit["ROOMS"]}) == 8


@pytest.mark.parametrize("zone", fit.ZONES)
@pytest.mark.parametrize("negative", (False, True))
def test_three_functional_models_positive_and_counterexample(
    tmp_path: Path, zone: str, negative: bool
) -> None:
    result = run(build.scenario(zone, negative), tmp_path)
    assert result["FUNCTIONAL_FIT_STATUS"] == (
        "CONDITIONAL_SCENARIO_NOT_FIT" if negative else "GEOMETRY_CHECK_ONLY"
    )
    assert not result["MISSING_INPUTS"]
    assert (
        not result[("PROJECT_FUNCTIONAL_FIT_APPROVED")] and result[("FUNCTIONAL_ROOM_AREA")] is None
    )
    if negative:
        assert result["NO_FIT_PROOF_SCOPE"].endswith("NOT_ALL_ROOM_USES")


@pytest.mark.parametrize("angle,expected", [(0, [0, 0, 2000, 1000]), (90, [-1000, 0, 0, 2000])])
def test_exact_rotation(angle: int, expected: list[int]) -> None:
    geo = fit.dependencies()[0]
    rect = geo.transform_rect(
        [0, 0, 2000, 1000], [{"ROTATION_DEG": angle, "TRANSLATION_MM": [0, 0]}]
    )
    assert list(rect) == expected


def test_area_union_not_bounding_or_room_area() -> None:
    geo = fit.dependencies()[0]
    rects = [geo.transform_rect(r, []) for r in [[0, 0, 2, 1], [0, 1, 1, 2]]]
    assert geo.union_area(rects) == 3
    assert geo.bounds(rects) == [0, 0, 2, 2]
    assert geo.intersection(rects[0], rects[1]) == 0


@pytest.mark.parametrize("width", (875, 977))
def test_opposed_rows_necessary_failure_only_for_explicit_configuration(width: int) -> None:
    result = fit.opposed_width_proof(width, 500, 500)
    assert result["STATUS"] == "CONDITIONAL_SCENARIO_NOT_FIT"
    assert result["DEFICIT_MM"] == 1000 - width
    assert not result["OTHER_ARRANGEMENTS_EXCLUDED"]


def test_opposed_necessary_width_is_not_functional_pass() -> None:
    r = fit.opposed_width_proof(1500, 500, 500)
    assert r["STATUS"] == "GEOMETRY_CHECK_ONLY" and not r["PROJECT_FUNCTIONAL_FIT_APPROVED"]


def test_owner_business_is_reused_not_project_staffing() -> None:
    r = fit.business_examples()
    assert not r["BOUND_TO_HISTORICAL_LAYOUT_STAFFING"] and r["PROJECT_STAFFING"] is None
    assert [x["OFFICE_DESIGN_STAFF"] for x in r["OFFICE_CONDITIONAL_SCENARIOS"].values()] == [
        12,
        20,
        30,
    ]
    assert r["UNKNOWN_FACTORY_SIZE"]["OFFICE_STAFF_STATUS"] == "OWNER_INPUT_REQUIRED"
    n = r["CONDITIONAL_20T_PACKAGED_PRODUCT_EXAMPLE"]["staffing_and_tables"]
    assert n["LOCKER_COUNT"] == 106 and n["SIMULTANEOUS_CHANGING_USERS"] == 53
    assert n["PACKING_TABLE_COUNT"] == 18 and n["WORKERS_PER_PACKING_TABLE"] == 3
    assert n["TABLE_SHARED_BETWEEN_SHIFTS"] and n["LOCKER_INTERNAL_SEPARATION"]


def test_office_unknown_factory_size_not_inferred(tmp_path: Path) -> None:
    doc = build.scenario("office")
    doc["CONFIGURATION"]["factory_size"] = None
    r = run(doc, tmp_path)
    assert r["FUNCTIONAL_FIT_STATUS"] == "INPUT_REQUIRED"
    assert r["OFFICE_BUSINESS_INPUT"]["OFFICE_STAFF_STATUS"] == "OWNER_INPUT_REQUIRED"


@pytest.mark.parametrize("process", ("FRUIT_WAXING", "FRUIT_COATING", ("PALLET_STRETCH_WRAPPING")))
def test_wrong_film_process_rejected(tmp_path: Path, process: str) -> None:
    doc = build.scenario("coating_room")
    doc["CONFIGURATION"]["process_type"] = process
    assert "BOX_FILM_SEALING_ONLY" in run(doc, tmp_path)["MISSING_INPUTS"][0]


@pytest.mark.parametrize(
    "zone,key",
    [
        ("coating_room", "effective_runtime_hours"),
        ("coating_room", "equipment_model"),
        ("changing_room", "locker_model"),
        ("office", "furniture_model"),
        ("coating_room", "maintenance_procedure"),
        ("office", "door_operation"),
    ],
)
def test_missing_real_operating_inputs_never_filled(tmp_path: Path, zone: str, key: str) -> None:
    doc = build.scenario(zone)
    doc["CONFIGURATION"][key] = None
    r = run(doc, tmp_path)
    assert r["FUNCTIONAL_FIT_STATUS"] == "INPUT_REQUIRED" and key in r["MISSING_INPUTS"]


def test_locker_door_body_collision(tmp_path: Path) -> None:
    doc = build.scenario("changing_room")
    door = next(c for c in doc["COMPONENTS"] if c["ID"] == "door_1")
    doc["COMPONENTS"].append(
        {**deepcopy(door), "ID": "blocking_body", "ROLE": "BODY", "ACTIVE_STATES": list(fit.STATES)}
    )
    r = run(doc, tmp_path)
    assert any(
        c["CLASS"] == "HARD_GEOMETRY_CONFLICT" and c["CODE"] == "ACTIVE_BODY_DOOR_SWEEP"
        for c in r["CONFLICTS"]
    )


def test_reach_overlap_is_review_not_body_collision(tmp_path: Path) -> None:
    doc = build.scenario("coating_room")
    body = next(c for c in doc["COMPONENTS"] if c["ROLE"] == "BODY")
    doc["COMPONENTS"].append({**deepcopy(body), "ID": "reach", "ROLE": "REACH"})
    r = run(doc, tmp_path)
    assert r["FUNCTIONAL_FIT_STATUS"] == "INTERACTION_REVIEW_REQUIRED"
    assert all(c["CLASS"] != "HARD_GEOMETRY_CONFLICT" for c in r["CONFLICTS"])


def test_supply_outfeed_crossing_recorded(tmp_path: Path) -> None:
    doc = build.scenario("coating_room")
    supply = next(c for c in doc["COMPONENTS"] if c["ROLE"] == "SUPPLY")
    out = next(c for c in doc["COMPONENTS"] if c["ROLE"] == "OUTFEED")
    out["BOUNDS_MM"] = supply["BOUNDS_MM"]
    r = run(doc, tmp_path)
    assert any(
        c["CODE"] == "ACTIVE_OUTFEED_SUPPLY" and c["CLASS"] == "INTERACTION_REVIEW_REQUIRED"
        for c in r["CONFLICTS"]
    )


def test_missing_circulation_and_cleaning_not_pass(tmp_path: Path) -> None:
    doc = build.scenario("office")
    doc["ROUTES"] = []
    doc["COMPONENTS"] = [c for c in doc["COMPONENTS"] if c["ROLE"] != "SERVICE"]
    r = run(doc, tmp_path)
    assert r["FUNCTIONAL_FIT_STATUS"] == "INPUT_REQUIRED"
    assert "CLEANING:service_envelope" in r["MISSING_INPUTS"]
    assert "NORMAL_OPERATION:full_width_circulation" in r["MISSING_INPUTS"]


def test_full_width_not_just_centerline(tmp_path: Path) -> None:
    doc = build.scenario("office")
    doc["ROUTES"][0]["WIDTH_MM"] = 800
    r = run(doc, tmp_path)
    assert any(c["CODE"] == "FULL_WIDTH_ROUTE_BLOCKED_OR_UNCOVERED" for c in r["CONFLICTS"])


def test_full_width_bound_portal_crossing_no_outside_route_approval(tmp_path: Path) -> None:
    r = run(build.scenario("office"), tmp_path)
    routes = r["STATE_RESULTS"]["NORMAL_OPERATION"]["ROUTES"]
    assert routes[0]["PORTAL_CONNECTION_PROVEN"] and routes[0]["FULL_WIDTH_GEOMETRY_CLEAR"]
    assert routes[0]["PORTAL_FUNCTIONAL_ACCESS"] == "NOT_EVALUATED"


def test_portal_body_block_recorded(tmp_path: Path) -> None:
    doc = build.scenario("office")
    doc["COMPONENTS"].append(
        {
            "ID": "entry_block",
            "ROLE": "BODY",
            "BOUNDS_MM": [0, 4200, 600, 5400],
            "TRANSFORM": {"ROTATION_DEG": 0, "TRANSLATION_MM": [0, 0]},
            "ACTIVE_STATES": list(fit.STATES),
        }
    )
    assert any(c["CODE"] == "PORTAL_BLOCKED_BY_BODY" for c in run(doc, tmp_path)["CONFLICTS"])


def test_maintenance_independent_and_non_film_through_route(tmp_path: Path) -> None:
    doc = build.scenario("coating_room", True)
    r = run(doc, tmp_path)
    assert r["STATE_RESULTS"]["NORMAL_OPERATION"]["STATUS"] == "GEOMETRY_CHECK_ONLY"
    assert r["STATE_RESULTS"]["MAINTENANCE"]["STATUS"] == "HARD_GEOMETRY_CONFLICT"
    assert "non_sealing_pass_through" not in r["MISSING_INPUTS"]
    assert not r["TIME_SHARING_APPROVED"] and not r["CAPACITY_VALIDATED"]


@pytest.mark.parametrize(
    "mutation",
    ("float", "angle", "unknown", "body_state", "mode", "approval", "hash", "changed_fact"),
)
def test_invalid_or_forged_input_fail_closed(tmp_path: Path, mutation: str) -> None:
    doc = build.seal_synthetic(build.scenario("office"), tmp_path, "source.json")
    if mutation == "float":
        doc["ROOM_BOUNDS_MM"][2] = 10000.0
    elif mutation == "angle":
        doc["COMPONENTS"][0]["TRANSFORM"]["ROTATION_DEG"] = 45
    elif mutation == "unknown":
        doc["COMPONENTS"][0]["ROLE"] = "UNKNOWN"
    elif mutation == "body_state":
        doc["COMPONENTS"][0]["ACTIVE_STATES"] = ["NORMAL_OPERATION"]
    elif mutation == "mode":
        doc["MODE"] = "PROJECT_CANDIDATE_INPUT"
    elif mutation == "approval":
        doc["APPROVED"] = True
    elif mutation == "hash":
        doc["SOURCES"]["SYNTHETIC_ROOM_TEST"]["SHA256"] = "0" * 64
    else:
        doc["CONFIGURATION"]["design_staff"] = 20
    r = fit.evaluate(doc, tmp_path)
    assert r["FUNCTIONAL_FIT_STATUS"] == "INPUT_REQUIRED"
    assert not r["PROJECT_FUNCTIONAL_FIT_APPROVED"]


@pytest.mark.parametrize("index", range(8))
def test_real_svg_uniform_scale_safe_deterministic(audit: Any, index: int) -> None:
    rows = audit["ROOMS"][index * 3 : index * 3 + 3]
    raw = renderer.real_candidate(rows)
    tree = ET.fromstring(raw)
    assert tree.attrib["data-scale-px-per-mm"] == "0.01"
    assert raw == renderer.real_candidate(deepcopy(rows))
    assert b"INPUT_REQUIRED" in raw and b"NOT FUNCTIONAL APPROVAL" in raw
    assert all(
        node.tag.rsplit("}", 1)[-1] not in ("script", "foreignObject", "image")
        for node in tree.iter()
    )
    assert not any(
        "href" in key or key.lower().startswith("on") for node in tree.iter() for key in node.attrib
    )


@pytest.mark.parametrize("zone", fit.ZONES)
def test_synthetic_svg_and_json_deterministic(tmp_path: Path, zone: str) -> None:
    docs = [
        build.seal_synthetic(build.scenario(zone, n), tmp_path, f"source-{n}.json")
        for n in (False, True)
    ]
    results = [fit.evaluate(d, tmp_path) for d in docs]
    raw = renderer.synthetic(docs, results)
    ET.fromstring(raw)
    assert b"SYNTHETIC_TEST_GEOMETRY" in raw
    assert renderer.synthetic(deepcopy(docs), deepcopy(results)) == raw
    assert fit.encode(results) == fit.encode([fit.evaluate(d, tmp_path) for d in docs])


def test_integer_mm_conversion_exact_no_pixels() -> None:
    assert fit.mm("1.656") == 1656
    with pytest.raises(ValueError):
        fit.mm("0.0001")
    with pytest.raises(ValueError):
        fit.mm(1.656)
    geo = fit.dependencies()[0]
    assert geo.path_envelope([(Fraction(0), Fraction(0)), (Fraction(10), Fraction(0))], 3)[0][
        1
    ] == Fraction(-3, 2)


def test_all_old_tracked_bytes_and_p1_canonical_replay() -> None:
    r = build.history()
    assert r["STATUS"] == "PASS" and not r["CHANGED_PREEXISTING_FILES"]
    replay = r["LEGACY_REPLAY"]
    assert replay["status"] == "READ_ONLY_FULL_SNAPSHOT_AND_DIMENSION_REPLAY_PASS"
    assert r["UNMODELED_FLEXIBLE_DIMENSION_RULE_UNCHANGED"]


def test_false_completion_and_zero_calls(audit: Any) -> None:
    for k in (
        "REAL_FACTORY_SOLVES",
        "REAL_TRUCK_SEARCHES",
        "NATIVE_SOLVER_CALLS",
        "P2D_FULL_PASS_COUNT",
    ):
        assert audit[k] == 0
    assert (
        not audit["NEW_OWNER_GRANT"]
        and not audit["STAGE_B_COMPLETE"]
        and not audit["VERSION_COMPLETE"]
    )
