"""White-listed non-Native adaptive generation and complete process admission."""

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

from cold_storage.modules.layout.application.autonomous_adaptive_layout import (
    _rectangles,
    generate_adaptive_layout,
)
from cold_storage.modules.layout.application.autonomous_factory_layout import bind_autonomous_input
from cold_storage.modules.layout.application.autonomous_process_continuity import (
    assess_process_candidate,
)
from cold_storage.modules.layout.domain.adaptive_room_feedback import feedback_room_proposals
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.current_process_requirements import (
    current_passage_requirements,
    current_storage_requirements,
)
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.functional_material_geometry import (
    bounds_inside,
    motion_clear,
)
from cold_storage.modules.layout.domain.process_endpoint_routes import ProcessRoutePlanner
from cold_storage.modules.layout.infrastructure.adaptive_layout_export import export_adaptive_suite
from cold_storage.modules.layout.infrastructure.process_continuity_export import (
    draw_process_candidate,
)

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "docs/previews/v2.2.2/autonomous-adaptive-layout-v13/inputs"
CONFIG = {"candidate_node_budget": 24, "full_evaluation_budget": 8, "candidate_limit": 2}


@pytest.fixture(autouse=True, scope="module")
def forbid_native() -> Iterator[None]:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("ADAPTIVE_LAYOUT_NATIVE_FORBIDDEN")

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
def results(project: dict[str, Any], parameters: dict[str, Any]) -> dict[int, Any]:
    generated = {}
    for days in (7, 8):
        current = copy.deepcopy(project)
        current["business"]["finished_storage_days"] = days
        generated[days] = generate_adaptive_layout(current, parameters, CONFIG)
    return generated


def _project(project: dict[str, Any], days: int) -> dict[str, Any]:
    p = copy.deepcopy(project)
    p["business"]["finished_storage_days"] = days
    return p


@pytest.mark.parametrize("days,grid,minimum,total", [(7, 324, 315, 493), (8, 364, 360, 533)])
def test_current_input_grid_not_old_or_lower_minimum(
    days: int, grid: int, minimum: int, total: int, results: dict[int, Any], project: dict[str, Any]
) -> None:
    r = results[days]
    ctx = bind_autonomous_input(_project(project, days))
    req = current_storage_requirements(ctx.plan)
    assert req == r["current_storage_requirements"]
    assert req["finished_goods_room"]["p1_grid_positions"] == grid
    assert req["finished_goods_room"]["minimum_positions"] == minimum
    assert sum(q["required_positions"] for q in req.values()) == total
    assert r["candidate_count"] == 2
    for c in r["candidates"]:
        stock = c["equipment"]["storage"]
        assert sum(q["layout"]["placed_positions"] for q in stock) == total
        assert all(
            q["layout"]["placed_positions"] >= req[q["layout"]["room"]]["required_positions"]
            for q in stock
        )
        assert all(q["movement"]["conditional_pick_put_geometry_pass"] for q in stock)


@pytest.mark.parametrize("days", [7, 8])
def test_full_original_admission_and_recomputed_changing(
    days: int, results: dict[int, Any], project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    for c in results[days]["candidates"]:
        a = assess_process_candidate(c, _project(project, days), parameters)
        assert a["accepted"] and all(a["engineering_checks"].values())
        assert a["main_line_count"] == 6
        assert len(a["auxiliary_flows"]) == 3
        assert all(q["status"] == "CONDITIONAL_CONNECTED" for q in a["auxiliary_flows"])
        assert [(q["required"], q["verified"]) for q in a["v11_coverage"]] == [(10, 10), (6, 6)]
        assert len(c["process_continuity"]["transfers"]) == 57
        assert c["non_truck_access_pass_count"] == 11
        assert len(c["rooms"]) == 12 and c["room_non_overlap_and_MUST"]["geometry_passed"]
        assert c["changing_function"]["conditional_complete_sequence_verified"]
        assert (
            c["changing_function"]["entry_exit_revalidation"]
            == "EXISTING_UNMODIFIED_ADAPTER_REEXECUTED"
        )
        assert not c["P2D_full_pass"] and not c["truck_route_validated"]
        assert a["engineering_approval"] == a["factory_applicability"] == "NOT_EVALUATED"


def test_input_change_recalculates_authority_dimensions_and_actual_coordinates(
    results: dict[int, Any],
) -> None:
    old, new = (results[d] for d in (7, 8))
    assert old["source_input_hash"] != new["source_input_hash"]
    assert old["p1_handoff_hash"] != new["p1_handoff_hash"]
    a, b = (
        next(q for q in r["candidates"][0]["rooms"] if q["zone_code"] == "finished_goods_room")
        for r in (old, new)
    )
    assert a["bbox_mm"] != b["bbox_mm"] and a["area_requirement"] != b["area_requirement"]
    assert a["width_mm"] * a["depth_mm"] != b["width_mm"] * b["depth_mm"]
    assert (b["authority_width_m"], b["authority_depth_m"]) != (
        a["authority_width_m"],
        a["authority_depth_m"],
    )


@pytest.mark.parametrize("days", [7, 8])
def test_spatial_diversity_and_actual_finite_rejections(days: int, results: dict[int, Any]) -> None:
    r = results[days]
    assert len({canonical_hash(c["rooms"]) for c in r["candidates"]}) == 2
    assert {c["adaptive_origin"] for c in r["candidates"]} == {
        "BLOCKER_EDGE_COUPLED_TRANSLATION",
        "FLEXIBLE_CONNECTOR_EXTENSION",
    }
    assert any(
        a["kind"] == "ALTERNATE_FIXED_ROTATION"
        and a["status"] == "ORIGINAL_ROOM_CONSTRAINT_REJECTED"
        for a in r["attempts"]
    )
    assert all(len(a["room_coordinates"]) == 12 for a in r["attempts"])
    assert r["search_budget"]["candidate_nodes_used"] == len(r["attempts"]) <= 24
    assert r["search_budget"]["full_evaluations_used"] <= 8
    assert not r["global_infeasibility_proven"]


def test_real_blocker_and_grid_failure_generates_other_space(results: dict[int, Any]) -> None:
    r = results[8]
    first = r["attempts"][0]
    assert first["status"] == "CURRENT_GRID_CAPACITY_REJECTED"
    assert first["failure_location"]["required_positions"] == 364
    assert first["failure_location"]["blocking_column_ids"]
    assert max(q["positions"] for q in first["finished_storage_trials"]) < 364 or all(
        not q["static_pass"] for q in first["finished_storage_trials"]
    )
    assert any(a["status"] == "CONDITIONAL_PROCESS_CANDIDATE" for a in r["attempts"][1:])


def test_actual_logistics_failure_retries_layout_and_endpoints(results: dict[int, Any]) -> None:
    a = results[7]["attempts"]
    assert a[0]["status"] == "INTERRUPTED_PROCESS_CANDIDATE"
    assert a[0]["selected_route_failures"] and a[0]["feedback_enqueued"]
    assert all(
        r["source_bbox_mm"] and r["target_bbox_mm"] and r["reserved_width_mm"] >= 2500
        for r in a[0]["selected_route_failures"]
    )
    retry = next(q for q in a if q["kind"] == "INTERFACE_FAILURE_FEEDBACK")
    assert retry["feedback_from_node"] == a[0]["node"]
    assert retry["endpoint_rank"] == 1 and retry["storage_rank"] == 1
    assert any(
        q["status"] == "CONDITIONAL_PROCESS_CANDIDATE"
        and q["room_geometry_hash"] != a[0]["room_geometry_hash"]
        for q in a
    )


@pytest.mark.parametrize("days", [7, 8])
def test_fixed_dimensions_original_authority_and_columns(
    days: int, results: dict[int, Any], project: dict[str, Any]
) -> None:
    ctx = bind_autonomous_input(_project(project, days))
    for c in results[days]["candidates"]:
        for room in c["rooms"]:
            a = ctx.binding.dimension_authorities[room["zone_code"]]
            assert room["area_requirement"] == a["area_requirement"]
            assert room["rotation_deg"] in a["rotation_allowed"]
            if a["dimension_mode"] != "FLEXIBLE_RECTANGLE":
                assert Decimal(room["authority_width_m"]) == Decimal(a["geometry"]["width_m"])
                assert Decimal(room["authority_depth_m"]) == Decimal(a["geometry"]["depth_m"])
            else:
                assert Decimal(room["area_m2"]) >= Decimal(a["required_area_m2"])
        for item in c["equipment"]["items"]:
            assert not any(
                positive_intersection(item["bbox_mm"], col["bbox_mm"])
                for col in c["original_building"]["columns"]
            )


def test_feedback_uses_changed_blocker_edges_not_constant_north_offset(
    results: dict[int, Any], project: dict[str, Any]
) -> None:
    ctx = bind_autonomous_input(_project(project, 8))
    rooms = _rectangles(results[8]["candidates"][0])
    room = rooms["finished_goods_room"].bounds_mm
    col = {
        "id": "DIAG-CURRENT-BLOCKER",
        "bbox_mm": [room[0] + 5000, room[1] + 500, room[0] + 5200, room[1] + 700],
    }
    p = feedback_room_proposals(rooms, [col], ctx.binding.dimension_authorities, node_budget=24)
    moved = copy.deepcopy(col)
    moved["bbox_mm"][3] += 400
    q = feedback_room_proposals(rooms, [moved], ctx.binding.dimension_authorities, node_budget=24)
    first = next(x for x in p if x["kind"] == "BLOCKER_EDGE_COUPLED_TRANSLATION")
    second = next(x for x in q if x["kind"] == "BLOCKER_EDGE_COUPLED_TRANSLATION")
    assert second["delta_mm"][1] - first["delta_mm"][1] == 400
    assert first["blocker"] == col["id"]
    # Proposals cannot change any fixed width/depth Authority, even rejected ones.
    for v in p:
        for key, r in v["rooms"].items():
            if ctx.binding.dimension_authorities[key]["dimension_mode"] != "FLEXIBLE_RECTANGLE":
                assert (r.width_m, r.depth_m) == (rooms[key].width_m, rooms[key].depth_m)


def test_rotated_grid_keeps_spacing_margins_and_main_aisle(results: dict[int, Any]) -> None:
    for c in results[8]["candidates"]:
        s = next(
            x for x in c["equipment"]["storage"] if x["layout"]["room"] == "finished_goods_room"
        )
        assert s["layout"]["pallet_local_rotation_deg"] == 90
        assert s["layout"]["grid_pitch_mm"] == [1300, 1200]
        assert s["layout"]["main_aisle_width_mm"] == 3000
        assert s["movement"]["load_margin_each_side_mm"] == 50
        assert sorted(s["movement"]["world_load_dimensions_mm"]) == [1000, 1200]
        assert s["movement"]["retrieved_positions"] == s["movement"]["putaway_positions"] == 364
        assert not s["movement"]["arbitrary_order_direct_access"]


def test_rotated_load_endpoints_still_use_original_carrier_and_real_load_centres(
    results: dict[int, Any], parameters: dict[str, Any]
) -> None:
    c = results[8]["candidates"][0]
    f = c["process_continuity"]
    ends = {e["id"]: e for e in f["endpoints"]}
    planner = ProcessRoutePlanner(c, parameters, adaptive_loads=True)
    for r in f["routes"]:
        if "source_dock" not in r or r["carrier"] != "LOADED_PALLET":
            continue
        assert r["main_reserved_width_mm"] == 2500 and r["turn_square_mm"] == 2222
        for role in ("source", "target"):
            e = ends[r[role + "_endpoint"]]
            assert e["carrier_envelope_unchanged"]
            assert sorted(r[role + "_dock"]["oriented_body_mm"]) == [1300, 1800]
            if e["carried_pallet"]:
                b = e["object_bbox_mm"]
                actual = [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2]
                contact = next(
                    q for q in r["endpoint_contact_transfers"] if q["object_id"] == e["object_id"]
                )
                assert contact["load_centre_mm"] == actual
            carried = set(r["load_state"]["carried_source_or_empty_reserved_destination"])
            obs = [q["bbox_mm"] for q in planner.obstacles(e["room"], carried)]
            for seg in r[role + "_dock"]["segments"]:
                assert motion_clear(
                    seg["centerline_mm"], planner.rooms[e["room"]], obs, *seg["body_mm"]
                )
            assert bounds_inside(
                r[role + "_dock"]["main_staging_square_mm"], planner.rooms[e["room"]]
            )


@pytest.mark.parametrize(
    "mutation",
    [
        "fixed_size",
        "capacity",
        "main_line",
        "branch",
        "device_move",
        "transfer",
        "old_coverage",
        "project",
    ],
)
def test_bad_or_stale_candidates_do_not_enter_ranking(
    mutation: str, results: dict[int, Any], project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    c = copy.deepcopy(results[8]["candidates"][0])
    if mutation == "fixed_size":
        room = next(q for q in c["rooms"] if q["zone_code"] == "finished_goods_room")
        room["authority_width_m"] = str(Decimal(room["authority_width_m"]) - 1)
    elif mutation == "capacity":
        s = next(
            q for q in c["equipment"]["storage"] if q["layout"]["room"] == "finished_goods_room"
        )
        s["layout"]["placed_positions"] = 360
        s["layout"]["items"] = s["layout"]["items"][:360]
    elif mutation == "main_line":
        c["process_continuity"]["product_chains"].pop()
    elif mutation == "branch":
        c["process_continuity"]["auxiliary_branches"].pop()
    elif mutation == "device_move":
        c["equipment"]["items"][0]["bbox_mm"][0] += 1
    elif mutation == "transfer":
        c["process_continuity"]["transfers"][0]["load_path_mm"] = []
    elif mutation == "old_coverage":
        c["storage_portal_interfaces"][0]["geometry_context_hash"] = "old-witness"
    else:
        c["source_input_hash"] = "another-project"
    a = assess_process_candidate(c, _project(project, 8), parameters)
    assert not a["accepted"] and a["failures"]
    if mutation == "capacity":
        assert not a["engineering_checks"]["current_p1_grid_capacity_and_pick_put"]


def test_coverage_requirements_come_from_current_p1_not_old_pass(
    results: dict[int, Any], project: dict[str, Any]
) -> None:
    ctx = bind_autonomous_input(_project(project, 8))
    roles = [q["zone_code"] for q in results[8]["candidates"][0]["rooms"]]
    r = current_passage_requirements(ctx.binding.access_requirements, roles)
    assert len(r["equipment_aware_interior_paths"]) == 10
    assert len(r["storage_portal_interfaces"]) == 6
    assert all("status" not in q and "centerline_mm" not in q for rows in r.values() for q in rows)


def test_budget_stops_actual_failed_pipeline_without_claiming_infeasible(
    project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    r = generate_adaptive_layout(project, parameters, {**CONFIG, "full_evaluation_budget": 2})
    assert not r["candidates"] and r["status"] == "BOUNDED_ADAPTIVE_SEARCH_NO_CANDIDATE"
    assert r["search_budget"]["full_evaluations_used"] == 2
    assert r["search_budget"]["remaining_queue"] > 0
    assert not r["global_infeasibility_proven"]


def test_initial_room_budget_failure_remains_a_reproducible_bounded_result(
    project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    bounded = copy.deepcopy(project)
    bounded["search"]["node_budget"] = 1
    r = generate_adaptive_layout(bounded, parameters, CONFIG)
    assert r["status"] == "BOUNDED_INITIAL_ATTACHMENT_SEARCH_NO_CANDIDATE"
    assert r["candidate_count"] == 0 and not r["global_infeasibility_proven"]
    assert r["current_storage_requirements"]["finished_goods_room"]["required_positions"] == 324
    assert r["result_hash"] == canonical_hash({k: v for k, v in r.items() if k != "result_hash"})


@pytest.mark.parametrize(
    "key,value",
    [
        ("candidate_node_budget", 49),
        ("candidate_node_budget", 2),
        ("full_evaluation_budget", 13),
        ("full_evaluation_budget", 0),
        ("candidate_limit", 5),
        ("initial_endpoint_rank", 4),
        ("initial_storage_choice_rank", 8),
    ],
)
def test_search_limits_rejected_before_generation(
    key: str, value: int, project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    with pytest.raises(LayoutAuthorityError, match="ADAPTIVE_SEARCH_BOUNDS_INVALID"):
        generate_adaptive_layout(project, parameters, {**CONFIG, key: value})


@pytest.mark.parametrize(
    "key,value",
    [
        ("main_aisle_mm", 2400),
        ("buffer_slots_per_group", 6),
        ("routing_node_budget", 20001),
        ("initial_layout", {}),
        ("line_workers", [9, 10, 10, 8, 8, 7]),
    ],
)
def test_original_process_basis_is_not_bypassed(
    key: str, value: Any, project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    changed = {**parameters, key: value}
    with pytest.raises(LayoutAuthorityError):
        generate_adaptive_layout(project, changed, CONFIG)


def test_identical_input_is_deterministic_without_historical_files(
    project: dict[str, Any],
    parameters: dict[str, Any],
    results: dict[int, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = Path.read_text
    opened = Path.open

    def deny(path: Path, *args: Any, **kwargs: Any) -> str:
        if any(
            x in str(path)
            for x in ("autonomous-layout-", "layout-generation-results", "layout-v3", "stage-b-")
        ):
            raise AssertionError("HISTORICAL_COORDINATES_FORBIDDEN")
        return read(path, *args, **kwargs)

    def deny_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if any(
            x in str(path)
            for x in ("autonomous-layout-", "layout-generation-results", "layout-v3", "stage-b-")
        ):
            raise AssertionError("HISTORICAL_COORDINATES_FORBIDDEN")
        return opened(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny)
    monkeypatch.setattr(Path, "open", deny_open)
    r = generate_adaptive_layout(_project(project, 8), parameters, CONFIG)
    assert r["result_hash"] == results[8]["result_hash"]
    assert not r["source_layout_coordinates_loaded"]
    assert r["native_calls"] == 0 and not r["MAIN"] and not r["grant_claim_accessed"]


def test_counts_are_actual_operations_not_discounted_stage_work(results: dict[int, Any]) -> None:
    r = results[8]
    for key, value in r["operation_counts"].items():
        assert value == sum(a.get("operation_counts", {}).get(key, 0) for a in r["attempts"])
        assert value > 0
    assert "not Stage A/B Work" in r["operation_scope"]
    assert "NOT_FORMAL_PARETO" in r["ranking"]


def test_guard_blocks_both_native_apis_in_child(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend/tests/functional_native_guard"),
        "R11_FUNCTIONAL_GUARD_AUDIT": str(tmp_path),
    }
    for method in ("solve", "Solve"):
        r = subprocess.run(
            [
                sys.executable,
                "-c",
                "from ortools.sat.python import cp_model; import sys; "
                "getattr(cp_model.CpSolver(),sys.argv[1])(cp_model.CpModel())",
                method,
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode != 0 and "R11_FUNCTIONAL_NATIVE_FORBIDDEN" in r.stderr
    assert len(list(tmp_path.glob("process-*.jsonl"))) == 2


def test_drawing_and_raw_export_share_actual_coordinates(
    results: dict[int, Any], project: dict[str, Any], parameters: dict[str, Any], tmp_path: Path
) -> None:
    c = results[8]["candidates"][0]
    draw_process_candidate(c, tmp_path / "plan", revision="V1.3", candidate_label="8d / A13-A")
    with fitz.open(tmp_path / "plan.pdf") as doc:
        assert abs(doc[0].rect.width * 25.4 / 72 - 841) < 0.01
        assert abs(doc[0].rect.height * 25.4 / 72 - 594) < 0.01
        assert "108000" in doc[0].get_text() and "V1.3" in doc[0].get_text()
    svg = (tmp_path / "plan.svg").read_text()
    assert all(f'data-equipment="{q["id"]}"' in svg for q in c["equipment"]["items"])
    cases = [
        {"project": _project(project, 8), "result": results[8], "resources": {"native_calls": 0}}
    ]
    export_adaptive_suite(cases, parameters, tmp_path / "export", drawings=False)
    raw = json.loads((tmp_path / "export/8-days/autonomous-layout-A13-A.json").read_text())
    # The persisted contract represents Decimal millimetre/metre values as text
    # and tuples as arrays. Compare the actual serialized values, not Python types.
    assert raw == json.loads(canonical_json(c))
    assert canonical_hash(raw) == canonical_hash(c)
    assert raw["result_hash"] == canonical_hash(
        {k: v for k, v in raw.items() if k != "result_hash"}
    )
    assert assess_process_candidate(raw, _project(project, 8), parameters)["accepted"]
    summary = json.loads((tmp_path / "export/case-comparison.json").read_text())[0]
    assert summary["candidates"][0]["hash"] == c["result_hash"]
    with pytest.raises(FileExistsError):
        export_adaptive_suite(cases, parameters, tmp_path / "export", drawings=False)
