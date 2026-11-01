"""Whitelisted non-Native device logistics, not inherited native experiment tests."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import fitz
import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.autonomous_process_continuity import (
    VERIFIED,
    assess_process_candidate,
    generate_process_layout,
)
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.functional_material_geometry import (
    bounds_inside,
    motion_clear,
    rectilinear_path,
)
from cold_storage.modules.layout.domain.process_endpoint_routes import (
    ProcessRoutePlanner,
    path_length,
    shared_sweep_inside,
)
from cold_storage.modules.layout.domain.process_flow_arrangement import (
    coating_service_depth,
    realize_coating_aisles,
)
from cold_storage.modules.layout.domain.process_transfer_interfaces import (
    ASSUMED,
    GEOMETRY,
    route_is_conditionally_usable,
)
from cold_storage.modules.layout.infrastructure.process_continuity_export import (
    draw_process_candidate,
    export_process_package,
)

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "docs/previews/v2.2.2/autonomous-factory-layout-v12/inputs"


@pytest.fixture(autouse=True, scope="module")
def forbid_native() -> Iterator[None]:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("PROCESS_CONTINUITY_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cp_model.CpSolver, "solve", blocked)
        patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def project() -> dict[str, Any]:
    return json.loads((INPUT / "project-input.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def parameters() -> dict[str, Any]:
    return json.loads((INPUT / "process-parameters.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def result(project: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    return generate_process_layout(project, parameters)


@pytest.fixture(scope="module")
def candidate(result: dict[str, Any]) -> dict[str, Any]:
    return result["candidates"][0]  # type: ignore[no-any-return]


def test_complete_original_room_authority_and_access(
    candidate: dict[str, Any], result: dict[str, Any]
) -> None:
    assert len(candidate["rooms"]) == 12
    assert candidate["room_non_overlap_and_MUST"]["geometry_passed"]
    assert candidate["non_truck_access_pass_count"] == 11
    assert candidate["building_footprint"]["status"] == "SINGLE_CONNECTED_ZERO_HOLE_UNION"
    assert candidate["dimension_and_area_authorities_unchanged"]
    assert not candidate["remaining_geometry_issues"]
    for row in candidate["rooms"]:
        if row["dimension_mode"] == "FLEXIBLE_RECTANGLE":
            assert Decimal(row["area_m2"]) >= Decimal(row["required_area_m2"])
        else:
            source = next(
                q for q in result["baseline"]["rooms"] if q["zone_code"] == row["zone_code"]
            )
            assert row["area_requirement"] == source["area_requirement"]
            assert (row["authority_width_m"], row["authority_depth_m"]) == (
                source["authority_width_m"],
                source["authority_depth_m"],
            )
    assert result["native_calls"] == 0 and not result["MAIN"] and not result["grant_claim_accessed"]
    assert not candidate["P2D_full_pass"] and not candidate["truck_route_validated"]


@pytest.mark.parametrize(
    "kind,count",
    [
        ("packing_line", 6),
        ("case_erector", 5),
        ("ten_door_locker", 11),
        ("PRI_pallet", 18),
        ("SEC_pallet", 12),
        ("case_film_component", 4),
    ],
)
def test_full_device_counts(kind: str, count: int, candidate: dict[str, Any]) -> None:
    assert candidate["equipment"]["placed_counts"][kind] == count


def test_buffers_and_work_positions_are_distinct(candidate: dict[str, Any]) -> None:
    v = candidate["process_continuity"]
    eq = candidate["equipment"]["items"]
    assert v["buffer_count"] == 14 and v["line_pallet_workplace_count"] == 6
    buffers = [q for q in eq if q["kind"] == "precooling_buffer"]
    work = [q for q in eq if q["kind"] == "packing_pallet_workplace"]
    assert len(buffers) == 14 and len(work) == 6
    assert len({tuple(q["bbox_mm"]) for q in [*buffers, *work]}) == 20
    assert all(q["capacity_credit"] == "BUFFER_ONLY" for q in buffers)
    assert v["buffer_verified_count"] == 14


def test_six_actual_device_chains_no_room_centres(candidate: dict[str, Any]) -> None:
    v = candidate["process_continuity"]
    routes = {q["id"]: q for q in v["routes"]}
    assert v["continuous_main_product_chain_count"] == 6
    for chain in v["product_chains"]:
        assert chain["continuous_object_chain"] and not chain["failed_segments"]
        assert len(chain["stages"]) >= 18
        for a, b in zip(chain["stages"], chain["stages"][1:], strict=False):
            assert a["target_object"] == b["source_object"]
        used = [routes[q["route_id"]] for q in chain["stages"] if q["route_id"] in routes]
        assert sum(len(q.get("portal_crossings", [])) for q in used) == 6
        assert chain["length_mm"] == sum(q["length_mm"] for q in used)
        assert all(route_is_conditionally_usable(q) for q in used)
    assert all(
        e["object_id"] in {q["id"] for q in candidate["equipment"]["items"]} for e in v["endpoints"]
    )
    assert all(e["role"] not in ("ROOM_CENTRE", "PORTAL_TO_PORTAL") for e in v["endpoints"])


def test_every_route_rechecks_recorded_sweeps(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> None:
    planner = ProcessRoutePlanner(candidate, parameters)
    for row in candidate["process_continuity"]["routes"]:
        assert route_is_conditionally_usable(row)
        assert row["length_mm"] == path_length(row["centerline_mm"])
        if "source_dock" not in row:
            continue
        carry = set(row["load_state"]["carried_source_or_empty_reserved_destination"])
        for role in ("source", "target"):
            endpoint = next(
                e
                for e in candidate["process_continuity"]["endpoints"]
                if e["id"] == row[role + "_endpoint"]
            )
            obs = [q["bbox_mm"] for q in planner.obstacles(endpoint["room"], carry)]
            dock = row[role + "_dock"]
            clear = planner.rooms[endpoint["room"]]
            assert dock["status"] == "DOCK_AND_TURN_VERIFIED"
            for seg in dock["segments"]:
                assert motion_clear(seg["centerline_mm"], clear, obs, *seg["body_mm"])
            for b in [*dock["turn_envelopes_mm"], dock["main_staging_square_mm"]]:
                assert bounds_inside(b, clear) and not any(positive_intersection(b, o) for o in obs)
        for seg in row["segments"]:
            if seg["kind"] != "ROOM_MAIN_AISLE":
                continue
            obs = [q["bbox_mm"] for q in planner.obstacles(seg["room"], carry)]
            assert motion_clear(
                seg["centerline_mm"],
                planner.rooms[seg["room"]],
                obs,
                seg["reserved_width_mm"],
                seg["reserved_width_mm"],
            )


def test_crossings_are_real_p1_portals_and_do_not_turn_in_doors(candidate: dict[str, Any]) -> None:
    access = {q["requirement_identity"]: q for q in candidate["access_results"]}
    for row in candidate["process_continuity"]["routes"]:
        for door in row.get("portal_crossings", []):
            source = access[door["requirement_identity"]]
            assert source["status"] == "PASS"
            assert door["portal_segment"] == source["portal_from"]["segment"]
            assert door["clear_width_mm"] == 2400
            assert door["throat_envelope_mm"] <= door["clear_width_mm"]
            assert not door["turn_in_doorway"]


@pytest.mark.parametrize(
    "role,minimum",
    [
        ("packaging_material_storage", 67),
        ("finished_goods_room", 324),
        ("raw_fruit_buffer", 45),
        ("secondary_fruit_buffer", 21),
        ("frozen_fruit_room", 36),
    ],
)
def test_no_capacity_deletion(role: str, minimum: int, candidate: dict[str, Any]) -> None:
    s = next(s for s in candidate["equipment"]["storage"] if s["layout"]["room"] == role)
    assert s["layout"]["placed_positions"] >= minimum
    assert s["layout"]["placed_positions"] == s["layout"]["original_grid_positions"]
    assert len(s["layout"]["items"]) == s["layout"]["placed_positions"]
    assert s["movement"]["conditional_pick_put_geometry_pass"]


def test_failed_real_capacity_trials_trigger_other_arrangement(result: dict[str, Any]) -> None:
    rejected = result["attempts"][:6]
    assert len(rejected) == 6 and all(q["status"] == "CAPACITY_REJECTED" for q in rejected)
    assert all(q["placed_positions"] == 63 and q["minimum_positions"] == 67 for q in rejected)
    assert result["attempts"][6]["status"] == "STATIC_REJECTED"
    assert result["attempts"][6]["conflicts"]
    assert result["attempts"][-1]["continuous_main_product_chains"] == 6


def test_five_erectors_supply_six_actual_lines(candidate: dict[str, Any]) -> None:
    v = candidate["process_continuity"]
    s = v["case_supply"]
    routes = {q["id"]: q for q in v["routes"]}
    assert s["all_five_blank_supplies_verified"]
    assert (
        len(s["line_assignments"]) == 6 and len({q["erector"] for q in s["line_assignments"]}) == 5
    )
    assert all(routes[q["route_id"]]["status"] == VERIFIED for q in s["line_assignments"])
    assert s["bounded_assignment_count"] == 1800


def test_only_flexible_room_feedback_not_authority_rewrite(
    result: dict[str, Any], candidate: dict[str, Any], parameters: dict[str, Any]
) -> None:
    old = {q["zone_code"]: q for q in result["baseline"]["rooms"]}
    now = {q["zone_code"]: q for q in candidate["rooms"]}
    assert old["coating_room"]["depth_mm"] == 7100
    assert now["coating_room"]["depth_mm"] == coating_service_depth(parameters)["depth_mm"] == 8300
    assert old["coating_room"]["required_area_m2"] == now["coating_room"]["required_area_m2"]
    assert candidate["changing_internal_model_unchanged"]
    assert candidate["changing_function"]["conditional_complete_sequence_verified"]


def test_column_feedback_preserves_original_324_positions(
    result: dict[str, Any], candidate: dict[str, Any]
) -> None:
    trials = [q for q in result["attempts"] if "required_existing_positions" in q]
    assert trials[0]["placed_positions"]["finished_goods_room"] == 317
    assert trials[0]["status"] == "EXISTING_CAPACITY_REJECTED"
    assert trials[1]["placed_positions"]["finished_goods_room"] == 324
    assert trials[1]["group_translation_north_mm"] == 2316
    assert all(not q["conflicts"] for q in candidate["equipment"]["operating_spaces"])
    feedback = candidate["coating_actual_aisle_feedback"]
    assert feedback["status"] == "EQUAL_WIDTH_ACTUAL_ROUTES_REALIZED"
    assert not feedback["geometry_exceptions_used"] and feedback["stationary_pallets_retained"]
    assert all(q["clear_width_mm"] == 2500 for q in feedback["realized_reserved_aisles"])


def test_actual_aisle_rejects_occupied_stationary_pallet(candidate: dict[str, Any]) -> None:
    c = copy.deepcopy(candidate)
    eq = c["equipment"]
    old = c["coating_actual_aisle_feedback"]["rejected_proposals"]
    eq["operating_spaces"] = [
        q for q in eq["operating_spaces"] if q["room"] != "coating_room"
    ] + old
    body = next(q["bbox_mm"] for q in eq["items"] if q["id"] == "DEPALLETIZE")
    centre = [(body[0] + body[2]) // 2, (body[1] + body[3]) // 2]
    for row in c["process_continuity"]["routes"]:
        for seg in row.get("segments", []):
            if seg["kind"] == "ROOM_MAIN_AISLE" and seg["room"] == "coating_room":
                seg["centerline_mm"] = [centre, centre]
                break
        else:
            continue
        break
    conflicts = [{"code": "RESERVED_AISLE_OCCUPIED", "room": "coating_room"}]
    checked = realize_coating_aisles(c, c["process_continuity"], conflicts)
    assert checked["status"] == "ACTUAL_AISLE_REJECTED"
    assert conflicts and any("DEPALLETIZE" in q["conflicts"] for q in checked["failures"])


def test_preserved_person_count_and_unapproved_inputs(candidate: dict[str, Any]) -> None:
    g = candidate["changing_function"]
    assert g["initial_53_people_verified"]
    assert len(g["shifts"]) == 2 and all(s["cycle_geometry_pass"] for s in g["shifts"])
    assert g["functional_status"] == "INPUT_REQUIRED"
    assert candidate["process_continuity"]["vehicle_kinematics"] == "INPUT_REQUIRED"
    assert not candidate["process_continuity"]["capacity_conditions"]["capacity_recalculated"]


def test_exact_width_aisle_needs_centred_event_not_artificial_mm_shrink() -> None:
    obstacles = [[0, 0, 5000, 2000], [0, 4500, 5000, 6500]]
    path, _ = rectilinear_path(
        (1250, 3250),
        (3750, 3250),
        (0, 0, 5000, 6500),
        obstacles,
        2500,
        2500,
        waypoints=[(2500, 3250)],
    )
    assert path and motion_clear(path, (0, 0, 5000, 6500), obstacles, 2500, 2500)
    blocked, _ = rectilinear_path(
        (1250, 3250), (3750, 3250), (0, 0, 5000, 6500), obstacles, 2501, 2501
    )
    assert not blocked


def test_door_crossing_requires_actual_room_union_and_actual_mouth() -> None:
    a = [0, 0, 10000, 10000]
    b = [10000, 5000, 20000, 15000]
    seg = {"start": {"x": 10, "y": 5.5}, "end": {"x": 10, "y": 7.9}}
    assert shared_sweep_inside([9000, 5500, 11000, 7700], a, b, seg)
    assert not shared_sweep_inside([9000, 5400, 11000, 7600], a, b, seg)
    assert not shared_sweep_inside([9000, 4500, 11000, 6500], a, b, seg)


def test_oversized_carton_cannot_be_clipped_into_packing_body(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> None:
    params = copy.deepcopy(parameters)
    params["carton_projection_mm"] = [600, 700]
    p = ProcessRoutePlanner(candidate, params)
    q = p.handoff("PACK-01", "PACK-01", "OVERSIZED-CARTON", internal=True)
    assert q["status"] == "HANDOFF_COLLISION" and not q["centerline_mm"]


def test_blocked_existing_door_cannot_be_replaced_by_wall_teleport(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> None:
    c = copy.deepcopy(candidate)
    flow = c["process_continuity"]
    source = flow["routes"][0]
    for row in c["access_results"]:
        if row["requirement_identity"].startswith("access:raw_fruit_buffer->"):
            row["status"] = "FAIL"
    p = ProcessRoutePlanner(c, parameters)
    p.endpoints = {q["id"]: q for q in flow["endpoints"]}
    q = p.route(source["source_endpoint"], source["target_endpoint"], "NEGATIVE-DOOR", "BLOCKED")
    assert q["status"] != VERIFIED and q["failure"] == "NO_EXISTING_MATERIAL_PORTAL_CHAIN"
    assert not q["centerline_mm"]


def test_occupied_staging_area_is_not_hidden(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> None:
    c = copy.deepcopy(candidate)
    row = next(q for q in c["process_continuity"]["routes"] if q["id"] == "LINE-BUFFER-1")
    stage = row["source_dock"]["main_staging_square_mm"]
    c["equipment"]["items"].append(
        {
            "id": "BLOCKED-BUFFER-EXIT",
            "room": "sorting_packaging_room",
            "kind": "test_occupied_pallet",
            "bbox_mm": stage,
        }
    )
    p = ProcessRoutePlanner(c, parameters)
    p.endpoints = {e["id"]: e for e in c["process_continuity"]["endpoints"]}
    q = p.route(row["source_endpoint"], row["target_endpoint"], "NEGATIVE-STOCK", "BLOCKED")
    assert q["status"] != VERIFIED and not q["centerline_mm"]


def test_internal_machine_exceptions_are_named_and_separate(candidate: dict[str, Any]) -> None:
    internals = [
        q
        for q in candidate["process_continuity"]["routes"]
        if q["purpose"] == "CARTON_MACHINE_INTERNAL"
    ]
    assert len(internals) == 4
    assert all(q["vendor_internal_transport"] == "INPUT_REQUIRED" for q in internals)
    assert all(q["segments"][0]["owner_body_exceptions"] == [q["source_object"]] for q in internals)
    assert all(
        q["segments"][0]["internal_projection_clipped_at_registered_machine_mouths"]
        for q in internals
    )


def test_all_route_endpoint_identities_resolve_and_contacts_are_real(
    candidate: dict[str, Any],
) -> None:
    v = candidate["process_continuity"]
    ends = {q["id"]: q for q in v["endpoints"]}
    for row in v["routes"]:
        for side in ("source", "target"):
            assert row[side + "_endpoint"] in ends
            e = ends[row[side + "_endpoint"]]
            a, b, c, d = e["object_bbox_mm"]
            x, y = e["contact_mm"]
            assert (x in (a, c) and b <= y <= d) or (y in (b, d) and a <= x <= c)
        for contact in row.get("endpoint_contact_transfers", []):
            assert contact["status"] in ("BOUND_TO_ACTUAL_LOAD", "CONTACT_SWEEP_VERIFIED")


def test_determinism_no_historical_coordinates(
    project: dict[str, Any],
    parameters: dict[str, Any],
    result: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Path.read_text

    def denied(path: Path, *args: Any, **kwargs: Any) -> str:
        if any(
            x in str(path)
            for x in ("autonomous-layout-", "layout-generation-results", "layout-v3", "stage-b-")
        ):
            raise AssertionError("HISTORICAL_LAYOUT_READ_FORBIDDEN")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    again = generate_process_layout(copy.deepcopy(project), copy.deepcopy(parameters))
    assert again["result_hash"] == result["result_hash"]
    assert not again["source_layout_coordinates_loaded"]


def test_changed_business_input_is_recomputed(
    project: dict[str, Any], parameters: dict[str, Any], result: dict[str, Any]
) -> None:
    changed = copy.deepcopy(project)
    changed["business"]["finished_storage_days"] = 8
    r = generate_process_layout(changed, parameters)
    assert r["source_input_hash"] != result["source_input_hash"]
    if r["candidates"]:
        old = next(
            q for q in result["candidates"][0]["rooms"] if q["zone_code"] == "finished_goods_room"
        )
        new = next(
            q for q in r["candidates"][0]["rooms"] if q["zone_code"] == "finished_goods_room"
        )
        assert old["area_requirement"] != new["area_requirement"]
        assert old["bbox_mm"] != new["bbox_mm"]
    else:
        assert "NO_CANDIDATE" in r["status"]


def test_larger_carrier_returns_real_interruption_not_old_success(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> None:
    p2 = copy.deepcopy(parameters)
    p2["carriers"]["LOADED_PALLET"]["tangent_mm"] = 2500
    p = ProcessRoutePlanner(candidate, p2)
    old = candidate["process_continuity"]
    p.endpoints = {e["id"]: e for e in old["endpoints"]}
    row = old["routes"][0]
    q = p.route(row["source_endpoint"], row["target_endpoint"], "WIDE-CARRIER", "REGRESSION")
    assert q["status"] != VERIFIED and not q["centerline_mm"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("main_aisle_mm", 2400),
        ("buffer_slots_per_group", 6),
        ("line_workers", [9, 10, 10, 8, 8, 7]),
        ("routing_node_budget", 20001),
    ],
)
def test_reduced_or_unbounded_design_basis_rejected(
    field: str, value: Any, project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    p = copy.deepcopy(parameters)
    p[field] = value
    with pytest.raises(LayoutAuthorityError):
        generate_process_layout(project, p)


def test_child_native_apis_are_blocked_not_executed(tmp_path: Path) -> None:
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT / "backend/tests/functional_native_guard"),
        R11_FUNCTIONAL_GUARD_AUDIT=str(tmp_path),
    )
    code = (
        "from ortools.sat.python import cp_model; s=cp_model.CpSolver(); "
        'getattr(s,__import__("sys").argv[1])(cp_model.CpModel())'
    )
    for method in ("solve", "Solve"):
        p = subprocess.run(
            [sys.executable, "-c", code, method],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert p.returncode != 0 and "R11_FUNCTIONAL_NATIVE_FORBIDDEN" in p.stderr
    assert len(list(tmp_path.glob("process-*.jsonl"))) == 2


def test_projection_scale_and_evidence_single_source(
    candidate: dict[str, Any], tmp_path: Path
) -> None:
    draw_process_candidate(candidate, tmp_path / "plan")
    with fitz.open(tmp_path / "plan.pdf") as pdf:
        assert abs(pdf[0].rect.width * 25.4 / 72 - 841) < 0.01
        assert abs(pdf[0].rect.height * 25.4 / 72 - 594) < 0.01
        assert "108000" in pdf[0].get_text()
    svg = (tmp_path / "plan.svg").read_text()
    assert 'width="841mm"' in svg and "108000 = 18 × 6000" in svg
    assert all(f'data-equipment="{q["id"]}"' in svg for q in candidate["equipment"]["items"])


def test_export_references_raw_witnesses_does_not_duplicate(
    result: dict[str, Any], project: dict[str, Any], parameters: dict[str, Any], tmp_path: Path
) -> None:
    export_process_package(result, project, parameters, tmp_path / "export", drawings=False)
    index = json.loads((tmp_path / "export/equipment-endpoints-and-routes.json").read_text())
    assert index["routes_json_pointer"] == "/process_continuity/routes"
    assert "routes" not in index
    c = json.loads((tmp_path / "export/autonomous-layout-A12.json").read_text())
    c.pop("result_hash")
    assert canonical_hash(c) == result["candidates"][0]["result_hash"]
    assert "NOT_EVALUATED" in (tmp_path / "export/layout-comparison.md").read_text()


# R1_CORRECTION_1: the full process admission is exercised, not a summary flag.
def test_full_process_admission_and_route_classification(candidate, project, parameters):
    a = assess_process_candidate(candidate, project, parameters)
    assert a["accepted"] and a["main_line_count"] == 6 and not a["failures"]
    assert a["counts"] == {
        "all_routes": 91,
        "selected_routes": 67,
        "exploratory_alternatives": 24,
        "conditional_machine_internal_routes": 10,
        "conditional_short_handoffs": 5,
        "explicit_transfers": 57,
    }
    assert {q["flow_kind"] for q in a["auxiliary_flows"]} == {"PACKAGING", "SECONDARY", "FROZEN"}
    assert all(q["status"] == "CONDITIONAL_CONNECTED" for q in a["auxiliary_flows"])
    assert sum(s["layout"]["placed_positions"] for s in candidate["equipment"]["storage"]) == 493
    assert not candidate["P2D_full_pass"]


@pytest.mark.parametrize("number", range(1, 7))
def test_any_failed_main_line_rejects_whole_candidate(number, candidate, project, parameters):
    c = copy.deepcopy(candidate)
    next(q for q in c["process_continuity"]["routes"] if q["id"] == f"PACK-PALLET-{number}")[
        "status"
    ] = "BOUNDED_PATH_NOT_FOUND"
    a = assess_process_candidate(c, project, parameters)
    assert not a["accepted"] and a["main_line_count"] == 5


@pytest.mark.parametrize("kind", ["SECONDARY", "FROZEN"])
def test_missing_auxiliary_branch_never_passes(kind, candidate, project, parameters):
    c = copy.deepcopy(candidate)
    c["process_continuity"]["auxiliary_branches"] = [
        q for q in c["process_continuity"]["auxiliary_branches"] if q["flow_kind"] != kind
    ]
    a = assess_process_candidate(c, project, parameters)
    assert (
        not a["accepted"] and {"code": "AUXILIARY_BRANCH_INCOMPLETE", "id": kind} in a["failures"]
    )


@pytest.mark.parametrize("index", range(6))
def test_each_selected_supply_path_required(index, candidate, project, parameters):
    c = copy.deepcopy(candidate)
    id_ = c["process_continuity"]["case_supply"]["line_assignments"][index]["route_id"]
    next(q for q in c["process_continuity"]["routes"] if q["id"] == id_)["status"] = (
        "FAILED_SELECTED"
    )
    assert not assess_process_candidate(c, project, parameters)["accepted"]


def test_failed_unselected_alternative_is_not_a_selected_failure(candidate, project, parameters):
    c = copy.deepcopy(candidate)
    id_ = c["process_admission"]["alternative_route_ids"][0]
    next(q for q in c["process_continuity"]["routes"] if q["id"] == id_)["status"] = (
        "FAILED_EXPLORATION"
    )
    assert assess_process_candidate(c, project, parameters)["accepted"]


@pytest.mark.parametrize("mutation", ["remove", "anchor", "payload", "path", "operation"])
def test_broken_carrier_transfer_cannot_be_bridged_by_owner_id(
    mutation, candidate, project, parameters
):
    c = copy.deepcopy(candidate)
    ts = c["process_continuity"]["transfers"]
    t = next(q for q in ts if q["kind"] == "UNLOAD_CRATES_TO_FOOD_BIN")
    assert t["from"]["object_id"] == t["to"]["object_id"] == "RAW-UNLOAD"
    if mutation == "remove":
        ts.remove(t)
    elif mutation == "anchor":
        t["to"]["load_anchor_mm"][1] += 1
    elif mutation == "payload":
        t["before_state"]["payload_form"] = "PACKED_CARTON"
    elif mutation == "path":
        t["load_path_mm"] = []
    else:
        t["geometry_status"] = "TRANSFER_GEOMETRY_REJECTED"
    assert not assess_process_candidate(c, project, parameters)["accepted"]


@pytest.mark.parametrize("identity", ["ERECT-01", "PACK-03", "WORK-PACK-01"])
def test_moved_body_rejects_old_passes(identity, candidate, project, parameters):
    c = copy.deepcopy(candidate)
    b = next(q for q in c["equipment"]["items"] if q["id"] == identity)["bbox_mm"]
    b[0] += 1
    b[2] += 1
    a = assess_process_candidate(c, project, parameters)
    assert not a["accepted"]
    assert any(q["code"] == "STALE_GEOMETRY_EVIDENCE" for q in a["failures"])


@pytest.mark.parametrize("field", ["equipment_aware_interior_paths", "storage_portal_interfaces"])
@pytest.mark.parametrize("mutation", ["remove", "old_context", "duplicate", "failed"])
def test_each_original_function_needs_fresh_nonduplicate_coverage(
    field, mutation, candidate, project, parameters
):
    c = copy.deepcopy(candidate)
    rows = c[field]
    if mutation == "remove":
        rows.pop()
    elif mutation == "old_context":
        rows[0]["geometry_context_hash"] = "old_v11_PASS"
    elif mutation == "duplicate":
        rows[-1] = copy.deepcopy(rows[0])
    else:
        rows[0]["status"] = "BOUNDED_PATH_NOT_FOUND"
    a = assess_process_candidate(c, project, parameters)
    assert not a["accepted"]
    assert any(q["code"] == "V11_REQUIRED_FUNCTION_NOT_RECOVERED_OR_STALE" for q in a["failures"])


def test_raw_750mm_reference_gap_has_real_load_and_actor_paths(candidate):
    ts = candidate["process_continuity"]["transfers"]
    raw = [q for q in ts if q["kind"] == "UNLOAD_CRATES_TO_FOOD_BIN"]
    assert len(raw) == 6
    for t in raw:
        assert t["reference_gap_mm"] == 750
        assert t["from"]["load_anchor_mm"] != t["to"]["load_anchor_mm"]
        assert t["load_path_mm"] and t["load_swept_bbox_mm"]
        assert t["actor_paths"] and all(a["geometry_status"] == GEOMETRY for a in t["actor_paths"])
        assert t["geometry_status"] == GEOMETRY and t["validation_status"] == ASSUMED
        assert t["actual_operation_status"] == "INPUT_REQUIRED" and t["required_inputs"]


def test_internal_and_short_transfers_are_not_manufacturer_pass(candidate):
    internals = [
        q
        for q in candidate["process_continuity"]["routes"]
        if q["purpose"]
        in ("PACKING_MACHINE_INTERNAL", "CARTON_MACHINE_INTERNAL", "CARTON_SHORT_HANDOFF")
    ]
    assert len(internals) == 15
    assert all(
        q["status"] == ASSUMED
        and q["geometry_status"] == GEOMETRY
        and q["actual_operation_status"] == "INPUT_REQUIRED"
        for q in internals
    )


@pytest.mark.parametrize("kind", ["SECONDARY", "FROZEN"])
def test_real_reject_slot_and_original_p1_door_geometry(kind, candidate, parameters):
    b = next(
        q for q in candidate["process_continuity"]["auxiliary_branches"] if q["flow_kind"] == kind
    )
    rr = {q["id"]: q for q in candidate["process_continuity"]["routes"]}
    pickup, delivery = [rr[i] for i in b["route_ids"]]
    assert pickup["source_object"].startswith("PACK-")
    assert pickup["carrier"] == "FOOD_TOTE_CARRY" and delivery["carrier"] == "LOADED_PALLET"
    assert delivery["target_object"] == b["stock_handoff_object"]
    assert len(delivery["portal_crossings"]) == 1
    assert (
        delivery["portal_crossings"][0]["requirement_identity"]
        == "access:sorting_packaging_room->" + b["to_ref"] + "@1.0.0"
    )
    assert all(route_is_conditionally_usable(q) for q in (pickup, delivery))
    assert b["actual_sort_outlet_and_storage_process"] == "INPUT_REQUIRED"


def test_original_predicate_rejects_touch_and_layout_feedback_preserves_width(
    candidate, parameters
):
    from cold_storage.modules.layout.domain import access_routing as routing
    from cold_storage.modules.layout.domain.autonomous_process_routes import _ring

    assert not routing._route_is_safe(
        [(1250, 3250), (3750, 3250)],
        width_mm=2500,
        boundary=_ring([0, 0, 5000, 6500]),
        obstacles=[_ring([0, 0, 5000, 2000])],
        zones={},
        incident_refs=frozenset(),
    )[0]
    q = candidate["equipment"]["layouts"]["sorting_packaging_room"]["service_corridors"]
    middle = next(a for a in q if a["id"] == "CASE-MIDDLE")
    assert middle["clear_width_mm"] == parameters["main_aisle_mm"] == 2500
    assert middle["bbox_mm"][3] - middle["bbox_mm"][1] == 2540
    assert parameters["case_middle_extra_mm"] == 40
    assert len(candidate["equipment_aware_interior_paths"]) == 10
    assert all(
        a["status"] == "INTERIOR_FULL_WIDTH_PATH_VERIFIED"
        for a in candidate["equipment_aware_interior_paths"]
    )


def test_r1_export_includes_admission_transfers_and_coverage(result, project, parameters, tmp_path):
    export_process_package(result, project, parameters, tmp_path / "r1", drawings=False)
    for name in (
        "process-admission.json",
        "process-interfaces.json",
        "v11-function-coverage.json",
        "route-selection.json",
        "process-detail.md",
    ):
        assert (tmp_path / "r1" / name).is_file()
    selection = json.loads((tmp_path / "r1/route-selection.json").read_text())
    assert (
        selection["original_route_count"],
        selection["original_selected_count"],
        selection["original_alternative_count"],
    ) == (87, 63, 24)


@pytest.mark.parametrize("mutation", ["upgrade_internal", "duplicate_blanks", "duplicate_buffer"])
def test_verification_levels_and_all_required_distinct_connections(
    mutation, candidate, project, parameters
):
    c = copy.deepcopy(candidate)
    f = c["process_continuity"]
    if mutation == "upgrade_internal":
        r = next(q for q in f["routes"] if q["id"] == "PROCESS-PACK-01")
        r["status"] = GEOMETRY
        r.pop("witness_hash")
        r["witness_hash"] = canonical_hash(r)
    elif mutation == "duplicate_blanks":
        f["case_supply"]["blank_supply_routes"][-1] = f["case_supply"]["blank_supply_routes"][0]
    else:
        f["buffer_routes"][-1] = f["buffer_routes"][0]
    assert not assess_process_candidate(c, project, parameters)["accepted"]
