"""Explicit non-Native joint placement and original-predicate regressions."""

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

from cold_storage.modules.layout.application.autonomous_factory_layout import bind_autonomous_input
from cold_storage.modules.layout.application.functional_autonomous_layout import (
    generate_functional_layout,
)
from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.autonomous_process_routes import _ring
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.functional_changing_layout import (
    changing_dimensions,
    changing_layout,
    evaluate_changing_use,
)
from cold_storage.modules.layout.domain.functional_material_geometry import (
    motion_clear,
    rectilinear_path,
)
from cold_storage.modules.layout.domain.functional_storage_layout import (
    ordered_stock_movement,
    storage_layouts,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.infrastructure.functional_layout_export import (
    draw_functional_candidate,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs/previews/v2.2.2/autonomous-factory-layout-v11/inputs/project-input.json"


@pytest.fixture(autouse=True, scope="module")
def forbid_native() -> Iterator[None]:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("JOINT_LAYOUT_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cp_model.CpSolver, "solve", blocked)
        patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def project() -> dict[str, Any]:
    return json.loads(SOURCE.read_text())  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def result(project: dict[str, Any]) -> dict[str, Any]:
    return generate_functional_layout(project)


@pytest.fixture(scope="module")
def candidate(result: dict[str, Any]) -> dict[str, Any]:
    assert result["candidate_count"] == 1
    return result["candidates"][0]  # type: ignore[no-any-return]


def test_feedback_recalculates_geometry_not_same_failure(
    result: dict[str, Any], candidate: dict[str, Any]
) -> None:
    a = result["attempts"]
    assert len(a) == 3
    assert a[0]["requested_flexible_shapes"]
    assert a[1]["topology_feedback"]["status"] == "NOT_VERIFIED"
    assert len({r["room_geometry_hash"] for r in a}) == 3
    assert not candidate["equipment"]["failures"]


def test_original_rooms_must_and_footprint(candidate: dict[str, Any]) -> None:
    assert len(candidate["rooms"]) == 12
    assert candidate["room_non_overlap_and_MUST"]["geometry_passed"]
    assert candidate["legacy_room_obstacle_oracle"]["status"] == "PASS"
    assert candidate["building_footprint"]["status"] == "SINGLE_CONNECTED_ZERO_HOLE_UNION"


def test_authority_sources_and_fixed_dimensions_preserved(
    project: dict[str, Any], candidate: dict[str, Any]
) -> None:
    ctx = bind_autonomous_input(project)
    assert candidate["source_p1_handoff_hash"] == ctx.binding.p1_handoff_hash
    for row in candidate["rooms"]:
        a = ctx.binding.dimension_authorities[row["zone_code"]]
        assert row["area_requirement"] == a["area_requirement"]
        if a["dimension_mode"] != "FLEXIBLE_RECTANGLE":
            assert Decimal(row["authority_width_m"]) == Decimal(a["geometry"]["width_m"])
            assert Decimal(row["authority_depth_m"]) == Decimal(a["geometry"]["depth_m"])
        else:
            assert Decimal(row["area_m2"]) >= Decimal(a["required_area_m2"])


@pytest.mark.parametrize(
    "kind,count",
    [
        ("packing_line", 6),
        ("case_erector", 5),
        ("ten_door_locker", 11),
        ("case_film_component", 4),
        ("PRI_pallet", 18),
        ("SEC_pallet", 12),
    ],
)
def test_complete_equipment_counts(kind: str, count: int, candidate: dict[str, Any]) -> None:
    assert candidate["equipment"]["placed_counts"][kind] == count
    assert not candidate["equipment"]["rejected_items"]


def test_all_bodies_and_reserved_aisles_avoid_columns(candidate: dict[str, Any]) -> None:
    eq = candidate["equipment"]
    rooms = {r["zone_code"]: r["bbox_mm"] for r in candidate["rooms"]}
    items = eq["items"]
    for i, q in enumerate(items):
        b = q["bbox_mm"]
        a = rooms[q["room"]]
        assert a[0] <= b[0] < b[2] <= a[2] and a[1] <= b[1] < b[3] <= a[3]
        assert not any(
            positive_intersection(b, c["bbox_mm"])
            for c in candidate["original_building"]["columns"]
        )
        assert not any(positive_intersection(b, c["bbox_mm"]) for c in items[:i])
    assert all(not a["conflicts"] for a in eq["operating_spaces"])


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
def test_storage_capacity_and_actual_ordered_movement(
    role: str, minimum: int, candidate: dict[str, Any]
) -> None:
    s = next(s for s in candidate["equipment"]["storage"] if s["layout"]["room"] == role)
    layout, m = s["layout"], s["movement"]
    assert layout["placed_positions"] >= minimum and layout["minimum_positions"] == minimum
    assert m["conditional_pick_put_geometry_pass"]
    assert m["retrieved_positions"] == m["putaway_positions"] == layout["placed_positions"]
    assert m["arbitrary_order_direct_access"] is False
    assert layout["main_aisle_width_mm"] >= 2500


def test_original_access_predicates_and_no_portal_approach_conflicts(
    project: dict[str, Any], candidate: dict[str, Any]
) -> None:
    assert candidate["non_truck_access_pass_count"] == 11
    assert len(candidate["portal_approach_checks"]) == 21
    assert all(q["status"] == "BODY_FREE_APPROACH" for q in candidate["portal_approach_checks"])
    ctx = bind_autonomous_input(project)
    reqs = {r["identity"]: r for r in ctx.binding.access_requirements}
    for row in candidate["access_results"]:
        if row["flow_kind"] == "TRUCK":
            continue
        assert (
            routing._evaluate_bound_requirement(
                routing._requirement_object(reqs[row["requirement_identity"]]), row
            )["status"]
            == "PASS"
        )
        assert Decimal(row["portal_to"]["clear_width_m"]) >= Decimal("1.5")


def test_every_storage_pickup_goal_reaches_real_process_portal(candidate: dict[str, Any]) -> None:
    routes = candidate["storage_portal_interfaces"]
    assert len(routes) == 6
    assert len({r["room"] for r in routes}) == 5
    assert all(r["status"] == "STORAGE_AISLE_TO_REAL_PORTAL_VERIFIED" for r in routes)


def test_key_material_interiors_reuse_original_full_width_predicate(
    candidate: dict[str, Any],
) -> None:
    paths = candidate["equipment_aware_interior_paths"]
    assert len(paths) == 10
    assert all(p["status"] == "INTERIOR_FULL_WIDTH_PATH_VERIFIED" for p in paths)
    for p in paths:
        room = next(r for r in candidate["rooms"] if r["zone_code"] == p["room"])
        obstacles = [
            _ring(q["bbox_mm"]) for q in candidate["equipment"]["items"] if q["room"] == p["room"]
        ]
        obstacles += [_ring(q["bbox_mm"]) for q in candidate["original_building"]["columns"]]
        safe, _, _ = routing._route_is_safe(
            [tuple(q) for q in p["centerline_mm"]],
            width_mm=p["clear_width_mm"],
            boundary=_ring(room["bbox_mm"]),
            obstacles=obstacles,
            zones={},
            incident_refs=frozenset(),
        )
        assert safe
        assert p["centerline_mm"] and p["clear_width_mm"] in (2000, 2500)
        assert room["bbox_mm"][0] <= p["centerline_mm"][0][0] <= room["bbox_mm"][2]


def test_two_real_shifts_53_people_and_110_distinct_cells(candidate: dict[str, Any]) -> None:
    g = candidate["equipment"]["layouts"]["changing_room"]["functional_geometry"]
    assert len(g["homes"]) == 53 and len(g["inventory"]["compartments"]) == 110
    f = candidate["changing_function"]
    assert f["conditional_complete_sequence_verified"]
    assert [s["completed_cabinet_cycles"] for s in f["shifts"]] == [53, 53]
    assert all(s["cycle_geometry_pass"] for s in f["shifts"])
    for s in f["entry_exit"]["shifts"]:
        assert s["entry_count"] == s["exit_count"] == 53
        assert not s["conflicts"]
    assert f["functional_status"] == "INPUT_REQUIRED" and not f["full_flow_verified"]
    assert f["legacy_H5_adapter"] == "UNSUPPORTED_NON_HISTORICAL_ROOM_AND_PORTALS"


def test_person_occupying_aisle_is_rejected(candidate: dict[str, Any]) -> None:
    g = copy.deepcopy(candidate["equipment"]["layouts"]["changing_room"]["functional_geometry"])
    g["homes"][0]["bounds_mm"] = [800, 4000, 1250, 4650]
    assert evaluate_changing_use(g)["status"] == "CONFIGURATION_NOT_FIT"


def test_small_room_requests_size_never_marks_locker_count_as_fit() -> None:
    q = PlacedRectangleV1("changing_room", Decimal(0), Decimal(0), Decimal(20), Decimal(2))
    g = changing_layout(q, [])
    assert g["status"] == "FUNCTIONAL_SIZE_REQUEST"
    assert not g["full_flow_verified"] and g["design_users"] == 53
    assert g["requested_shape_mm"] == [
        changing_dimensions()["width_mm"],
        changing_dimensions()["depth_mm"],
    ]


@pytest.mark.parametrize(
    "role,key,value",
    [
        ("locker", "quantity", 10),
        ("locker", "depth_mm", 500),
        ("packing_line", "quantity", 5),
        ("case_erector", "quantity", 4),
    ],
)
def test_unsupported_counts_or_physical_locker_fail_closed(
    project: dict[str, Any], role: str, key: str, value: int
) -> None:
    p = copy.deepcopy(project)
    p["equipment_specs"][role][key] = value
    with pytest.raises(LayoutAuthorityError, match="UNSUPPORTED_FUNCTIONAL"):
        generate_functional_layout(p)


@pytest.mark.parametrize(
    "key,value", [("people_in_changing", 52), ("persons_per_shift", 52), ("bench_count", 1)]
)
def test_owner_population_and_posture_cannot_be_silently_reduced(
    project: dict[str, Any], key: str, value: int
) -> None:
    p = copy.deepcopy(project)
    p["owner_facts"][key] = value
    with pytest.raises(LayoutAuthorityError, match="UNSUPPORTED_FUNCTIONAL_OWNER_CONFIGURATION"):
        generate_functional_layout(p)


def test_same_input_deterministic_and_result_bound(
    project: dict[str, Any], result: dict[str, Any]
) -> None:
    other = generate_functional_layout(project)
    assert other["result_hash"] == result["result_hash"]
    assert result["source_input_hash"] == canonical_hash(project)


def test_changed_storage_days_recomputes_real_rooms(
    project: dict[str, Any], result: dict[str, Any]
) -> None:
    p = copy.deepcopy(project)
    p["business"]["finished_storage_days"] = 8
    r = generate_functional_layout(p)
    assert r["p1_handoff_hash"] != result["p1_handoff_hash"]
    assert r["zone_plan"] != result["zone_plan"]
    if r["candidates"]:
        a = next(
            q for q in result["candidates"][0]["rooms"] if q["zone_code"] == "finished_goods_room"
        )
        b = next(q for q in r["candidates"][0]["rooms"] if q["zone_code"] == "finished_goods_room")
        assert a["bbox_mm"] != b["bbox_mm"] and a["area_m2"] != b["area_m2"]
    else:
        assert r["status"] == "BOUNDED_SEARCH_NO_CANDIDATE" and not r["global_infeasibility_proven"]


def test_child_generates_without_any_historical_layout_files(
    tmp_path: Path, project: dict[str, Any]
) -> None:
    inp = tmp_path / "only-input.json"
    inp.write_text(json.dumps(project))
    code = """import json,sys
from pathlib import Path
p=json.loads(Path(sys.argv[1]).read_text())
def deny(event,args):
 forbidden=('/docs/previews/','autonomous-layout-A.json','stage-b-r9-resource-bound-real-main')
 if event=='open' and isinstance(args[0],str) and any(x in args[0] for x in forbidden):
  raise AssertionError('HISTORICAL_LAYOUT_READ_FORBIDDEN')
sys.addaudithook(deny)
from cold_storage.modules.layout.application import functional_autonomous_layout as joint
r=joint.generate_functional_layout(p)
assert r['candidate_count']==1 and not r['source_layout_coordinates_loaded']
print(r['result_hash'])"""
    env = {
        **os.environ,
        "PYTHONPATH": f"{ROOT}/backend/tests/functional_native_guard:{ROOT}/backend/src",
        "R11_FUNCTIONAL_GUARD_AUDIT": str(tmp_path / "guard"),
    }
    r = subprocess.run(
        [sys.executable, "-c", code, str(inp)], env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0, r.stderr
    audit = "".join(p.read_text() for p in (tmp_path / "guard").glob("*.jsonl"))
    assert "GUARD_READY" in audit and "NATIVE_REQUEST_BLOCKED" not in audit


@pytest.mark.parametrize("obstacle", [(4800, 0, 5200, 10000), (0, 0, 10000, 10000)])
def test_failed_motion_never_turns_into_success(obstacle: tuple[int, int, int, int]) -> None:
    path, _ = rectilinear_path(
        (2000, 5000), (8000, 5000), (0, 0, 10000, 10000), [obstacle], 1200, 1200, node_budget=20
    )
    assert not path
    assert not motion_clear(
        [(2000, 5000), (8000, 5000)], (0, 0, 10000, 10000), [obstacle], 1200, 1200
    )


def test_no_stock_deleted_to_fake_retrieval() -> None:
    room = PlacedRectangleV1("finished_goods_room", Decimal(0), Decimal(0), Decimal(5), Decimal(6))
    layout = storage_layouts(room, {"position_count": 4, "n_need": 4}, [])[0]
    block = [{"id": "BLOCK", "bbox_mm": [0, 2000, 5000, 3000]}]
    m = ordered_stock_movement(layout, room, block, node_budget=20)
    assert not m["conditional_pick_put_geometry_pass"]


def test_a1_scale_projection_preserves_same_json_equipment(
    candidate: dict[str, Any], tmp_path: Path
) -> None:
    path = tmp_path / "A1"
    draw_functional_candidate(candidate, path)
    with fitz.open(path.with_suffix(".pdf")) as pdf:
        assert abs(pdf[0].rect.width * 25.4 / 72 - 841) < 0.01
        assert abs(pdf[0].rect.height * 25.4 / 72 - 594) < 0.01
    svg = path.with_suffix(".svg").read_text()
    assert 'width="841mm"' in svg and "108000 = 18 × 6000" in svg
    assert svg.count("data-room=") == 12
    assert svg.count("data-equipment=") == len(candidate["equipment"]["items"])
    assert 'x="36.0"' in svg or 'x="36"' in svg


def test_no_production_acceptance_is_invented(
    candidate: dict[str, Any], result: dict[str, Any]
) -> None:
    assert not candidate["truck_route_validated"] and not candidate["P2D_full_pass"]
    assert not result["MAIN"] and not result["grant_claim_accessed"]
    assert not result["production_default_changed"] and result["native_calls"] == 0
    assert candidate["engineering_approval"] == "NOT_EVALUATED"
