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
from cold_storage.modules.layout.domain.process_flow_arrangement import coating_service_depth
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
        assert all(q["status"] == VERIFIED for q in used)
    assert all(
        e["object_id"] in {q["id"] for q in candidate["equipment"]["items"]} for e in v["endpoints"]
    )
    assert all(e["role"] not in ("ROOM_CENTRE", "PORTAL_TO_PORTAL") for e in v["endpoints"])


def test_every_route_rechecks_recorded_sweeps(
    candidate: dict[str, Any], parameters: dict[str, Any]
) -> None:
    planner = ProcessRoutePlanner(candidate, parameters)
    for row in candidate["process_continuity"]["routes"]:
        assert row["status"] == VERIFIED
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
        ("finished_goods_room", 315),
        ("raw_fruit_buffer", 37),
        ("secondary_fruit_buffer", 19),
        ("frozen_fruit_room", 34),
    ],
)
def test_no_capacity_deletion(role: str, minimum: int, candidate: dict[str, Any]) -> None:
    s = next(s for s in candidate["equipment"]["storage"] if s["layout"]["room"] == role)
    assert s["layout"]["placed_positions"] >= minimum
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
