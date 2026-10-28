"""Pure R4 capacity and occupied-space review; both Native APIs are prohibited."""

import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.multi_tier_locker_review import (
    SOURCE_SHA256,
    bind_multi_tier_review,
    review_multi_tier_template,
)
from cold_storage.modules.layout.domain.multi_tier_locker_layout import (
    inventory_conflicts,
    portal_route_check,
    validate_snapshot,
)
from cold_storage.modules.layout.domain.multi_tier_locker_model import (
    MultiTierHypothesis,
    service_waves,
    storage_demand,
    storage_inventory,
)
from cold_storage.modules.layout.infrastructure.multi_tier_locker_review_page import (
    elevation_svg,
    plan_svg,
    preview_request,
)

ROOT = Path(__file__).resolve().parents[3]
PARAMS = MultiTierHypothesis(
    front_concurrent_users=11, cabinet_door_sweep_mm=0, room_door_sweep_mm=0
)


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("R11_R4_NATIVE_FORBIDDEN")

    monkeypatch.setattr(cp_model.CpSolver, "solve", forbidden)
    monkeypatch.setattr(cp_model.CpSolver, "Solve", forbidden)


@pytest.fixture(scope="module")
def r3():
    return json.loads(
        (
            ROOT
            / "docs/previews/v2.2.2/r11-r3-locker-layout-review-r1/project-and-room-catalog.json"
        ).read_bytes()
    )


@pytest.fixture(scope="module")
def catalog(r3):
    raw = (ROOT / "docs/tasks/V2_2_2-r11-r4-reviewed-locker-form.txt").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256
    return bind_multi_tier_review(r3, raw)


@pytest.fixture(scope="module")
def h5(catalog):
    return review_multi_tier_template(catalog, "G01", "INTERNAL_PARTITION", PARAMS)


def test_storage_counts_are_cells_columns_and_manufacturer_dependent_units():
    d = storage_demand([53, 53], 53, "INTERNAL_PARTITION")
    assert d["required_compartments_per_shift"] == [53, 53]
    assert d["columns_per_shift"] == [11, 11]
    assert d["capacity_per_shift"] == [55, 55]
    assert d["total_capacity"] == 110 and d["total_columns"] == 22
    assert d["spare_per_shift"] == [2, 2]
    assert d["physical_cabinet_unit_count"] == "INPUT_REQUIRED"
    one = storage_inventory(d, PARAMS)
    two = storage_inventory(d, replace(PARAMS, columns_per_unit=2))
    assert len(one["cabinet_units"]) == 22
    assert len(two["cabinet_units"]) == 12
    assert len(two["vertical_columns"]) == 22 and len(two["compartments"]) == 110
    assert sum(u["partial_unit"] for u in two["cabinet_units"]) == 2
    assert one["person_assignments"] == two["person_assignments"]
    assert not inventory_conflicts(one, d) and not inventory_conflicts(two, d)


def test_two_cells_scenario_separates_identity_but_cannot_approve_hygiene():
    d = storage_demand([53, 53], 53, "TWO_COMPARTMENTS")
    assert d["columns_per_shift"] == [22, 22] and d["total_capacity"] == 220
    assert d["separation_satisfied"] == "INPUT_REQUIRED"
    inv = storage_inventory(d, PARAMS)
    cells = {c["id"]: c for c in inv["compartments"]}
    for person in inv["person_assignments"]:
        owned = [cells[k] for k in person["compartment_ids"]]
        assert {c["purpose"] for c in owned} == {"WORK_CLOTHES", "PRIVATE_CLOTHES"}
        assert len({c["independent_door_id"] for c in owned}) == 2
        assert {c["assigned_person_id"] for c in owned} == {person["person_id"]}
    assert len(inv["cabinet_units"]) == 44


@pytest.mark.parametrize("k", [1, 5, 11, 53])
@pytest.mark.parametrize("mode", ["INTERNAL_PARTITION", "TWO_COMPARTMENTS"])
def test_finite_waves_cover_every_assigned_cell_without_same_column_concurrency(k, mode):
    inv = storage_inventory(storage_demand([53, 53], 53, mode), PARAMS)
    for shift in (1, 2):
        waves = service_waves(inv, shift, k)
        keys = []
        for w in waves:
            assert len(w) <= k and len({a["column_id"] for a in w}) == len(w)
            assert len({a["person_id"] for a in w}) == len(w)
            keys.extend(a["compartment_id"] for a in w)
        expected = {
            c["id"] for c in inv["compartments"] if c["shift"] == shift and c["assigned_person_id"]
        }
        assert len(keys) == len(set(keys)) and set(keys) == expected


def test_five_tiers_are_not_five_floor_rectangles(h5):
    assert len(h5["inventory"]["cabinet_units"]) == 22
    assert len(h5["inventory"]["compartments"]) == 110
    first = h5["inventory"]["compartments"][:5]
    assert [c["tier"] for c in first] == [1, 2, 3, 4, 5]
    assert first[0]["elevation_bounds_mm"] == [0, 100, 400, 400]
    assert first[-1]["elevation_bounds_mm"] == [0, 1380, 400, 1680]
    assert h5["parameters"]["cabinet_height_mm"] == 1800


@pytest.mark.parametrize(
    "bad", ["missing", "duplicate", "reuse", "cross_shift", "height", "door", "orphan"]
)
def test_invalid_physical_hierarchy_cannot_be_accepted(bad):
    d = storage_demand([53, 53], 53, "INTERNAL_PARTITION")
    inv = storage_inventory(d, PARAMS)
    if bad == "missing":
        inv["compartments"].pop()
    if bad == "duplicate":
        inv["compartments"][-1]["id"] = inv["compartments"][0]["id"]
    if bad == "reuse":
        inv["person_assignments"][1]["compartment_ids"] = inv["person_assignments"][0][
            "compartment_ids"
        ]
    if bad == "cross_shift":
        inv["compartments"][0]["shift"] = 2
    if bad == "height":
        inv["compartments"][0]["elevation_bounds_mm"][3] = 1801
    if bad == "door":
        inv["compartments"][1]["independent_door_id"] = inv["compartments"][0][
            "independent_door_id"
        ]
    if bad == "orphan":
        inv["cabinet_units"][0]["column_ids"] = []
    assert inventory_conflicts(inv, d)


def test_new_owner_form_binding_does_not_approve_dimensions_or_mutate_r3(catalog, r3):
    before = copy.deepcopy(r3)
    raw = (ROOT / "docs/tasks/V2_2_2-r11-r4-reviewed-locker-form.txt").read_bytes()
    c = bind_multi_tier_review(r3, raw)
    assert r3 == before
    assert c["project_facts"]["source_label"] == "OWNER_CONFIRMED"
    assert c["reference_dimensions"]["status"] == "REFERENCE_ONLY_NOT_APPROVED_DIMENSION"
    assert c["cabinet_front_concurrent_users"] == "INPUT_REQUIRED"
    assert c["physical_cabinet_unit_count"] == "INPUT_REQUIRED"
    assert c["project_functional_status"] == "INPUT_REQUIRED"
    assert c["design_basis"]["simultaneous_room_users"] == 53
    assert len(c["groups"]) == 8 and sum(len(r["records"]) for r in c["groups"]) == 9
    assert c["groups"][0]["records"] == ["P01", "P02"]
    for row, old in zip(c["groups"], r3["groups"], strict=True):
        assert row["room"] == old["room"]
        assert row["record_access_readbacks"] == old["record_access_readbacks"]
        assert len(row["room"]["portals"]) == 2
        assert all(
            v["portal_geometry_matches"] and v["two_access_passes"]
            for v in row["record_access_readbacks"]
        )
    with pytest.raises(ValueError, match="SOURCE_MISMATCH"):
        bind_multi_tier_review(r3, b'{"source_label":"OWNER_CONFIRMED","tiers":5}')


@pytest.mark.parametrize(
    "field,value",
    [("simultaneous_users", 11), ("shift_workers", [11, 11]), ("packaged_mass_kg_per_day", 10000)],
)
def test_cannot_lower_room_occupancy_or_change_project_design(r3, field, value):
    altered = copy.deepcopy(r3)
    altered["design_counts"][field] = value
    raw = (ROOT / "docs/tasks/V2_2_2-r11-r4-reviewed-locker-form.txt").read_bytes()
    with pytest.raises(ValueError, match="DESIGN_COUNTS_CHANGED"):
        bind_multi_tier_review(altered, raw)


def test_default_concurrency_and_door_motion_require_input(catalog):
    result = review_multi_tier_template(catalog, "G01", "INTERNAL_PARTITION", MultiTierHypothesis())
    assert result["geometry_status"] == "INPUT_REQUIRED"
    assert set(result["missing_hypothetical_inputs"]) == {
        "front_concurrent_users",
        "cabinet_door_sweep_mm",
        "room_door_sweep_mm",
    }
    assert result["snapshots"] == []


def test_both_shifts_keep_all_53_users_every_wave_and_preserve_original_portals(h5):
    assert h5["geometry_status"] == "SNAPSHOTS_VALID_UNDER_HYPOTHESES"
    assert h5["project_functional_status"] == "INPUT_REQUIRED"
    for shift in (1, 2):
        waves = [
            s
            for s in h5["snapshots"]
            if s["witness"]["shift"] == shift and "USE" in s["witness"]["states"]
        ]
        assert len(waves) == 5
        assert sum(s["evaluation"]["active_operator_count"] for s in waves) == 53
        for s in waves:
            e = s["evaluation"]
            assert e["people_count"] == 53
            assert e["active_operator_count"] <= 11
            assert e["other_room_users"] == 53 - e["active_operator_count"]
            assert e["route"]["valid"] and len(e["route"]["proven_portal_ids"]) == 2
    assert {v["record"] for v in h5["original_access_readbacks"]} == {"P01", "P02"}
    assert h5["separation_satisfied"] == "INPUT_REQUIRED"
    assert h5["transition_paths"] == "NOT_EVALUATED"


@pytest.mark.parametrize("group", [f"G{i:02}" for i in range(2, 9)])
@pytest.mark.parametrize("arrangement", ["SINGLE_SIDE", "OPPOSED"])
def test_h6_new_cabinet_template_fails_net_aisle_width_not_old_106_floor_count(
    catalog, group, arrangement
):
    r = review_multi_tier_template(
        catalog, group, "INTERNAL_PARTITION", replace(PARAMS, arrangement=arrangement)
    )
    assert r["geometry_status"] == "CONFIGURATION_NOT_FIT"
    assert "CABINET_AND_NET_AISLE_WIDTH_SHORTFALL_FOR_THIS_TEMPLATE" in r["template_failures"]
    assert 1008 <= r["available_width_mm"] <= 1015
    assert r["required_width_mm"] == (1700 if arrangement == "SINGLE_SIDE" else 2200)
    assert len(r["inventory"]["vertical_columns"]) == 22
    assert r["snapshots"] == [] and r["project_functional_status"] == "INPUT_REQUIRED"


def _codes(result):
    return {v["code"] for v in result["conflicts"]}


@pytest.mark.parametrize(
    "bad,expected",
    [
        ("aisle", "OCCUPIED_SPACE_INTRUDES_NET_PASSAGE"),
        ("missing", "TOTAL_53_ROOM_OCCUPANTS_MUST_BE_PRESERVED"),
        ("crossshift", "ACTIVE_PERSON_COMPARTMENT_ASSIGNMENT_MISMATCH"),
        ("repeatcolumn", "CONCURRENT_OPERATORS_SHARE_SAME_COLUMN_FRONT"),
        ("door", "PERSON_BODY_PERSON_OR_DOOR_CONFLICT"),
        ("portal", "BOTH_ORIGINAL_PORTALS_FULL_WIDTH_ROUTE_UNPROVEN"),
        ("island", "PERSON_NOT_CONNECTED_TO_PORTAL_AISLE"),
    ],
)
def test_false_positive_occupancy_and_portal_cases_rejected(h5, bad, expected):
    s = copy.deepcopy(h5["snapshots"][0]["witness"])
    if bad == "aisle":
        s["people"][0]["bounds_mm"] = [0, 1100, 400, 1700]
    if bad == "missing":
        s["people"].pop()
    if bad == "crossshift":
        s["active_actions"][0]["compartment_id"] = "S2-C01-T1"
    if bad == "repeatcolumn":
        s["active_actions"][1]["column_id"] = s["active_actions"][0]["column_id"]
    if bad == "door":
        s["door_exclusions"].append(dict(id="door", bounds_mm=s["people"][0]["bounds_mm"]))
    if bad == "portal":
        s["route_points_mm"][-1][1] = 0
    if bad == "island":
        s["people"][0]["bounds_mm"] = [20000, 0, 20400, 600]
        s["aisles"].append([20000, 600, 21200, 1800])
        # Isolate an apparently adjacent aisle from the real portal route.
        s["route_points_mm"][-1][1] = 0
    e = validate_snapshot(h5["room"], h5["demand"], h5["inventory"], PARAMS, s)
    assert expected in _codes(e) and e["status"] == "CONFIGURATION_NOT_FIT"


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"reach_high_mm": 1200}, "COMPARTMENT_OUTSIDE_HYPOTHETICAL_REACH_RANGE"),
        ({"cabinet_door_sweep_mm": 400}, "PERSON_BODY_PERSON_OR_DOOR_CONFLICT"),
        ({"room_door_sweep_mm": 500}, "OCCUPIED_SPACE_INTRUDES_NET_PASSAGE"),
        ({"clear_height_mm": 1700}, "CABINET_ABOVE_CLEAR_HEIGHT"),
    ],
)
def test_unapproved_parameter_changes_reveal_real_component_conflicts(catalog, changes, code):
    r = review_multi_tier_template(catalog, "G01", "INTERNAL_PARTITION", replace(PARAMS, **changes))
    assert r["geometry_status"] == "CONFIGURATION_NOT_FIT"
    assert any(code in _codes(s["evaluation"]) for s in r["snapshots"])
    assert r["project_functional_status"] == "INPUT_REQUIRED"


def test_separated_storage_does_not_remove_53_room_users(catalog):
    r = review_multi_tier_template(catalog, "G01", "TWO_COMPARTMENTS", PARAMS)
    assert r["geometry_status"] == "SNAPSHOTS_VALID_UNDER_HYPOTHESES"
    for shift in (1, 2):
        waves = [
            s
            for s in r["snapshots"]
            if s["witness"]["shift"] == shift and "USE" in s["witness"]["states"]
        ]
        assert sum(s["evaluation"]["active_operator_count"] for s in waves) == 106
        assert all(s["evaluation"]["people_count"] == 53 for s in waves)
    assert r["separation_satisfied"] == "INPUT_REQUIRED"


def test_bench_and_operator_intersection_are_checked(h5):
    s = copy.deepcopy(h5["snapshots"][0]["witness"])
    s["benches"].append(dict(id="bench", bounds_mm=s["people"][0]["bounds_mm"]))
    e = validate_snapshot(h5["room"], h5["demand"], h5["inventory"], PARAMS, s)
    assert "PERSON_BODY_PERSON_OR_DOOR_CONFLICT" in _codes(e)


def test_invalid_or_missing_portal_does_not_default_to_valid_route(h5):
    room = copy.deepcopy(h5["room"])
    room["portals"].pop()
    s = h5["snapshots"][0]["witness"]
    e = portal_route_check(
        room,
        s["route_points_mm"],
        1200,
        s["finished_clear_bounds_mm"],
        s["aisles"],
        h5["inventory"]["cabinet_units"],
    )
    assert not e["valid"]


@pytest.mark.parametrize(
    "field",
    [
        "source_label",
        "status",
        "shift_users",
        "simultaneous_room_users",
        "tiers_per_column",
        "project_scope_id",
    ],
)
def test_preview_cannot_import_approvals_or_change_project_basis(catalog, field):
    body = dict(group="G01", scenario="INTERNAL_PARTITION", parameters=asdict(PARAMS))
    body["parameters"][field] = "OWNER_CONFIRMED"
    with pytest.raises(ValueError, match="HYPOTHESES_ONLY"):
        preview_request(catalog, body)


def test_elevation_and_plan_are_separate_real_scale_svg(h5):
    plan = ET.fromstring(plan_svg(h5, h5["snapshots"][0]))
    elevation = ET.fromstring(elevation_svg(h5, 1))
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert plan.attrib["viewBox"] == "-400 -3900 27131 5150"
    cells = [r for r in elevation.findall(".//s:rect", ns) if float(r.attrib["height"]) == 300]
    assert len(cells) == 55
    assert "INPUT_REQUIRED" in plan_svg(h5)
    assert "HYPOTHETICAL_NOT_APPROVED" in elevation_svg(h5, 2)
    assert h5["inventory"]["compartments"][0]["id"] in elevation_svg(h5, 1)


def test_cleaning_maintenance_cover_all_five_tiers_and_reject_missing_service(h5):
    service = next(s for s in h5["snapshots"] if "MAINTENANCE" in s["witness"]["states"])
    action = service["witness"]["active_actions"][0]
    assert len(action["serviced_compartment_ids"]) == 5
    s = copy.deepcopy(service["witness"])
    s["active_actions"][0]["serviced_compartment_ids"].pop()
    e = validate_snapshot(h5["room"], h5["demand"], h5["inventory"], PARAMS, s)
    assert "ALL_FIVE_TIERS_SERVICE_COVERAGE_REQUIRED" in _codes(e)
    e = validate_snapshot(
        h5["room"],
        h5["demand"],
        h5["inventory"],
        replace(PARAMS, reach_high_mm=1200),
        service["witness"],
    )
    assert "SERVICE_TIER_OUTSIDE_HYPOTHETICAL_REACH_RANGE" in _codes(e)


def test_hypothetical_front_count_does_not_change_total_occupants(catalog):
    result = review_multi_tier_template(
        catalog, "G01", "INTERNAL_PARTITION", replace(PARAMS, front_concurrent_users=5)
    )
    uses = [s for s in result["snapshots"] if "USE" in s["witness"]["states"]]
    # Column exclusion can require more waves than ceil(53 / K); never claim
    # throughput from division alone. Every assigned user is still serviced.
    assert len(uses) >= 22
    assert sum(s["evaluation"]["active_operator_count"] for s in uses) == 106
    assert all(s["evaluation"]["people_count"] == 53 for s in uses)
    assert all(s["evaluation"]["active_operator_count"] <= 5 for s in uses)
    assert result["project_functional_status"] == "INPUT_REQUIRED"
