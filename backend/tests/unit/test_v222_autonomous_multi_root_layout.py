"""Bounded, current-input, non-Native multi-root engineering generation."""

from __future__ import annotations

import builtins
import copy
import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.autonomous_factory_layout import bind_autonomous_input
from cold_storage.modules.layout.application.autonomous_multi_root_layout import (
    DEFAULT_SEARCH,
    collision_root_feedback,
    generate_multi_root_layout,
    prepare_root,
    room_roots,
)
from cold_storage.modules.layout.application.autonomous_process_continuity import (
    assess_process_candidate,
)
from cold_storage.modules.layout.domain.autonomous_equipment import positive_intersection
from cold_storage.modules.layout.domain.autonomous_room_search import search_room_arrangements
from cold_storage.modules.layout.domain.current_process_requirements import (
    current_storage_requirements,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.multi_root_space import (
    organisation_key,
    physical_candidate_key,
    space_difference,
    uncovered_pockets,
)
from cold_storage.modules.layout.domain.process_flow_arrangement import arrange_process_workplaces
from cold_storage.modules.layout.infrastructure.multi_root_layout_export import (
    export_multi_root_suite,
)

ROOT = Path(__file__).resolve().parents[3]
PREVIEW = ROOT / "docs/previews/v2.2.2/autonomous-multi-root-layout-v14"
TEST_SEARCH = {**DEFAULT_SEARCH, "root_search_limit": 18, "total_room_node_budget": 6000}


@pytest.fixture(autouse=True, scope="module")
def forbid_native() -> Iterator[None]:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("MULTI_ROOT_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cp_model.CpSolver, "solve", blocked)
        patch.setattr(cp_model.CpSolver, "Solve", blocked)
        yield


@pytest.fixture(scope="module")
def project() -> dict[str, Any]:
    return json.loads((PREVIEW / "inputs/project-input.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def parameters() -> dict[str, Any]:
    return json.loads((PREVIEW / "inputs/process-parameters.json").read_text())  # type: ignore[no-any-return]


def at_days(project: dict[str, Any], days: int) -> dict[str, Any]:
    p = copy.deepcopy(project)
    p["business"]["finished_storage_days"] = days
    return p


@pytest.fixture(scope="module")
def generated(project: dict[str, Any], parameters: dict[str, Any]) -> dict[int, Any]:
    results = {}
    read_text = Path.read_text
    file_open, io_open = builtins.open, io.open

    def assert_current_path(path: Any) -> None:
        if any(
            q in str(path)
            for q in (
                "/results/",
                "autonomous-layout-A",
                "layout-v3",
                "layout-v2",
                "/artifacts/stage-b-",
                "/output/pdf/",
            )
        ):
            raise AssertionError(f"HISTORICAL_LAYOUT_READ_FORBIDDEN:{path}")

    def guarded_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        assert_current_path(path)
        return file_open(path, *args, **kwargs)

    def guarded_io_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        assert_current_path(path)
        return io_open(path, *args, **kwargs)

    def no_history(path: Path, *args: Any, **kwargs: Any) -> str:
        assert_current_path(path)
        return read_text(path, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "read_text", no_history)
        patch.setattr(builtins, "open", guarded_open)
        patch.setattr(io, "open", guarded_io_open)
        for days in (7, 8):
            results[days] = generate_multi_root_layout(
                at_days(project, days), parameters, TEST_SEARCH
            )
    return results


@pytest.fixture(scope="module")
def roots(project: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    context = bind_autonomous_input(project)
    return {
        profile: room_roots(
            project, parameters, context, profile=profile, preferences={}, limit=2, node_budget=400
        )
        for profile in (
            "LINEAR_BANDED",
            "CENTRAL_PROCESS_CORE",
            "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
        )
    }


@pytest.mark.parametrize("days,grid,total", [(7, 324, 493), (8, 364, 533)])
def test_current_capacity_all_survivors_and_no_lower_minimum(
    days: int, grid: int, total: int, generated: dict[int, Any], project: dict[str, Any]
) -> None:
    result = generated[days]
    context = bind_autonomous_input(at_days(project, days))
    requirements = current_storage_requirements(context.plan)
    assert result["current_storage_requirements"] == requirements
    assert requirements["finished_goods_room"]["required_positions"] == grid
    assert sum(r["required_positions"] for r in requirements.values()) == total
    assert result["candidate_count"] >= 1
    for c in result["candidates"]:
        assert sum(s["layout"]["placed_positions"] for s in c["equipment"]["storage"]) == total
        assert all(
            s["movement"]["conditional_pick_put_geometry_pass"] for s in c["equipment"]["storage"]
        )


@pytest.mark.parametrize("days", [7, 8])
def test_each_accepted_root_reexecutes_complete_original_admission(
    days: int, generated: dict[int, Any], project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    for c in generated[days]["candidates"]:
        a = assess_process_candidate(c, at_days(project, days), parameters)
        assert a["accepted"] and all(a["engineering_checks"].values())
        assert a["main_line_count"] == 6
        assert all(q["status"] == "CONDITIONAL_CONNECTED" for q in a["auxiliary_flows"])
        assert len(a["auxiliary_flows"]) == 3
        assert [(q["required"], q["verified"]) for q in a["v11_coverage"]] == [(10, 10), (6, 6)]
        assert len(c["process_continuity"]["transfers"]) == 57
        assert c["non_truck_access_pass_count"] == 11
        assert len(c["rooms"]) == 12 and c["room_non_overlap_and_MUST"]["geometry_passed"]
        assert c["changing_function"]["conditional_complete_sequence_verified"]
        assert not c["P2D_full_pass"] and not c["truck_route_validated"]
        assert a["engineering_approval"] == a["factory_applicability"] == "NOT_EVALUATED"


def test_real_profiles_search_different_core_geometry(roots: dict[str, Any]) -> None:
    signatures = set()
    boxes = set()
    for groups, stats in roots.values():
        assert len(groups) == 2
        assert stats["nodes_used"] <= 400
        assert stats["actual_root_trials"] and stats["rejection_counts"]
        assert stats["rejection_examples"]
        for room_map in groups:
            rows = [{"zone_code": k, "bbox_mm": list(q.bounds_mm)} for k, q in room_map.items()]
            signatures.add(organisation_key({"rooms": rows}))
            boxes.add(canonical_hash(rows))
    assert len(boxes) >= 4 and len(signatures) >= 3


def test_repeated_current_input_search_is_deterministic(
    project: dict[str, Any], parameters: dict[str, Any], roots: dict[str, Any]
) -> None:
    again, stats = room_roots(
        project,
        parameters,
        bind_autonomous_input(project),
        profile="PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
        preferences={},
        limit=2,
        node_budget=400,
    )
    before, old_stats = roots["PROCESS_SPINE_WITH_PERIPHERAL_BANKS"]

    def coordinates(groups: Any) -> list[Any]:
        return [[(k, q.bounds_mm, q.rotation_deg) for k, q in sorted(r.items())] for r in groups]

    assert coordinates(again) == coordinates(before)
    assert stats == old_stats


def test_preserved_seven_day_b_is_regenerated_before_historical_comparison(
    generated: dict[int, Any],
) -> None:
    original = json.loads(
        (
            ROOT / "docs/previews/v2.2.2/autonomous-adaptive-layout-v13/results/7-days/"
            "autonomous-layout-A13-B.json"
        ).read_text()
    )
    regenerated = generated[7]["candidates"][0]
    assert original["rooms"] == regenerated["rooms"]
    assert original["equipment"]["items"] == regenerated["equipment"]["items"]
    assert original["adaptive_metrics"] == regenerated["adaptive_metrics"]


def test_business_change_rebinds_real_p1_and_room_coordinates(generated: dict[int, Any]) -> None:
    old, new = (generated[d] for d in (7, 8))
    assert old["p1_handoff_hash"] != new["p1_handoff_hash"]
    assert old["source_input_hash"] != new["source_input_hash"]
    rows = [
        next(q for q in r["candidates"][0]["rooms"] if q["zone_code"] == "finished_goods_room")
        for r in (old, new)
    ]
    assert rows[0]["bbox_mm"] != rows[1]["bbox_mm"]
    assert rows[0]["authority_width_m"] != rows[1]["authority_width_m"]


def test_no_label_only_success_and_real_device_changes(generated: dict[int, Any]) -> None:
    for result in generated.values():
        base = result["candidates"][0]
        keys = {organisation_key(c) for c in result["candidates"]}
        assert len(keys) == result["organisation_count"]
        for c in result["candidates"][1:]:
            d = space_difference(base, c)
            assert d == c["difference_from_current_reference"]
            if organisation_key(base) != organisation_key(c):
                assert d["substantive_spatial_change"]
                assert len(d["changed_material_core_rooms"]) >= 2
                assert d["changed_equipment_count"] > 6
                # Upstream reorganisation need not also move the packing bodies.
                assert set(d["changed_equipment_kinds"]) & {
                    "packing_line",
                    "PRI_pallet",
                    "SEC_pallet",
                    "finished_goods_room_pallet",
                    "raw_fruit_buffer_pallet",
                }
        if len(keys) == 1:
            assert result["status"] == "NO_NEW_ORGANISATION_WITHIN_BOUNDED_SEARCH"


@pytest.mark.parametrize("days", [7, 8])
def test_root_budget_fairness_and_actual_failed_objects(
    days: int, generated: dict[int, Any]
) -> None:
    r = generated[days]
    b = r["search_budget"]
    assert b["root_search_calls_used"] <= TEST_SEARCH["root_search_limit"]
    assert b["room_nodes_used"] <= TEST_SEARCH["total_room_node_budget"]
    assert b["full_pipeline_attempts_used"] <= DEFAULT_SEARCH["full_pipeline_limit"]
    assert len(b["profile_search_allocations"]) == 3
    assert all(n > 0 for n in b["profile_search_allocations"].values())
    assert len(r["roots"]) >= 6 or r["new_qualified_organisation_count"] >= 1
    assert any(q["static_conflicts"] for q in r["roots"]) or any(
        "BOUNDED_INSTALLATION_NOT_FOUND" in key
        for s in r["root_searches"]
        for key in s["stats"].get("partial_constraint_rejection_counts", {})
    )
    # R2 deliberately rejects these before a complete root/equipment build.
    assert any(q["capacity_deficit"] for q in r["roots"]) or any(
        "FINITE_GRID_OPTIONS_EXHAUSTED" in key
        for s in r["root_searches"]
        for key in s["stats"].get("partial_constraint_rejection_counts", {})
    )
    assert all(len(q["room_coordinates"]) == 12 and q["equipment_coordinates"] for q in r["roots"])
    assert all(
        q["stats"]["nodes_used"] <= DEFAULT_SEARCH["nodes_per_root_search"]
        for q in r["root_searches"]
    )
    assert not r["global_infeasibility_proven"]


def test_feedback_separates_real_column_using_new_input_edges(
    project: dict[str, Any], parameters: dict[str, Any], roots: dict[str, Any]
) -> None:
    context = bind_autonomous_input(project)
    state = roots["PROCESS_SPINE_WITH_PERIPHERAL_BANKS"][0][0]
    seed = prepare_root(state, project, context)
    arranged = arrange_process_workplaces(seed, parameters)
    proposals = collision_root_feedback(seed, arranged)
    assert proposals and all(p["trigger"]["other"] for p in proposals)
    moved = copy.deepcopy(arranged)
    obstruction = proposals[0]["trigger"]["other"]
    column = next(
        c for c in moved["candidate"]["original_building"]["columns"] if c["id"] == obstruction
    )
    column["bbox_mm"][1] += 200
    column["bbox_mm"][3] += 200
    other = collision_root_feedback(seed, moved)
    assert canonical_hash(proposals) != canonical_hash(other)
    assert all(p["obstacle_bbox_mm"] and p["moving_bbox_mm"] for p in proposals)
    assert all(p["source_type"] == "demo" and p["requires_review"] for p in proposals)


def test_failure_feedback_really_regenerates_room_and_device_coordinates(
    project: dict[str, Any], parameters: dict[str, Any], roots: dict[str, Any]
) -> None:
    context = bind_autonomous_input(project)
    state = roots["PROCESS_SPINE_WITH_PERIPHERAL_BANKS"][0][0]
    before = prepare_root(state, project, context)
    arranged = arrange_process_workplaces(before, parameters)
    proposals = collision_root_feedback(before, arranged)
    attempts = []
    for f in proposals:
        groups, stats = room_roots(
            project,
            parameters,
            context,
            profile="PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
            preferences={},
            limit=1,
            node_budget=400,
            anchor=tuple(f["root_anchor_mm"]),
        )
        assert stats["nodes_used"] <= 400
        if not groups:
            continue
        after = prepare_root(groups[0], project, context)
        attempts.append(after)
        assert before["rooms"] != after["rooms"]
        objects = [
            {q["id"]: q["bbox_mm"] for q in c["equipment"]["items"]} for c in (before, after)
        ]
        assert objects[0]["PACK-01"] != objects[1]["PACK-01"]
        assert after["room_non_overlap_and_MUST"]["geometry_passed"]
        assert not after.get("process_admission")  # Not an invented engineering PASS.
        break
    assert attempts


def test_parent_native_methods_are_blocked_and_search_defaults_are_immutable() -> None:
    for api in ("solve", "Solve"):
        with pytest.raises(AssertionError, match="MULTI_ROOT_NATIVE_FORBIDDEN"):
            getattr(cp_model.CpSolver(), api)(cp_model.CpModel())
    assert not hasattr(DEFAULT_SEARCH, "__setitem__")


@pytest.mark.parametrize("change", ["label", "translation", "mirror", "rotation", "coating_only"])
def test_cosmetic_or_coating_changes_do_not_earn_structural_diversity(
    change: str, generated: dict[int, Any]
) -> None:
    original = generated[7]["candidates"][0]
    altered = copy.deepcopy(original)
    altered["profile"] = "ANOTHER_LABEL"
    for room in altered["rooms"]:
        x, y, r, t = room["bbox_mm"]
        if change == "translation":
            room["bbox_mm"] = [x + 1500, y + 2200, r + 1500, t + 2200]
        elif change == "mirror":
            room["bbox_mm"] = [-r, y, -x, t]
        elif change == "rotation":
            room["bbox_mm"] = [-t, x, -y, r]
        elif change == "coating_only" and room["zone_code"] == "coating_room":
            room["bbox_mm"][3] += 300
    assert organisation_key(original) == organisation_key(altered)
    assert not space_difference(original, altered)["substantive_spatial_change"]


def test_physical_dedup_uses_equipment_portals_and_selected_routes(
    generated: dict[int, Any],
) -> None:
    a = generated[7]["candidates"][0]
    b = copy.deepcopy(a)
    b["label"] = "Renamed"
    b["rooms"].reverse()
    b["equipment"]["items"].reverse()
    b["access_results"].reverse()
    assert physical_candidate_key(a) == physical_candidate_key(b)
    b["equipment"]["items"][0]["bbox_mm"][0] += 100
    assert physical_candidate_key(a) != physical_candidate_key(b)


@pytest.mark.parametrize("days", [7, 8])
def test_fixed_authority_and_actual_column_avoidance(
    days: int, generated: dict[int, Any], project: dict[str, Any]
) -> None:
    context = bind_autonomous_input(at_days(project, days))
    for c in generated[days]["candidates"]:
        for room in c["rooms"]:
            authority = context.binding.dimension_authorities[room["zone_code"]]
            assert room["area_requirement"] == authority["area_requirement"]
            assert room["rotation_deg"] in authority["rotation_allowed"]
            if authority["dimension_mode"] != "FLEXIBLE_RECTANGLE":
                assert Decimal(room["authority_width_m"]) == Decimal(
                    authority["geometry"]["width_m"]
                )
                assert Decimal(room["authority_depth_m"]) == Decimal(
                    authority["geometry"]["depth_m"]
                )
        assert not any(
            positive_intersection(q["bbox_mm"], col["bbox_mm"])
            for q in c["equipment"]["items"]
            for col in project["building"]["columns"]
        )


@pytest.mark.parametrize(
    "mutation", ["one_main", "secondary", "frozen", "carton", "transfer", "stale"]
)
def test_old_acceptance_cannot_cross_space_or_skip_required_flow(
    mutation: str, generated: dict[int, Any], project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    c = copy.deepcopy(generated[7]["candidates"][0])
    f = c["process_continuity"]
    if mutation == "one_main":
        ident = f["product_chains"][0]["stages"][0]["route_id"]
        next(q for q in f["routes"] if q["id"] == ident)["geometry_status"] = "NOT_VERIFIED"
    elif mutation in ("secondary", "frozen"):
        f["auxiliary_branches"] = [
            q for q in f["auxiliary_branches"] if mutation not in str(q).lower()
        ]
    elif mutation == "carton":
        ident = f["case_supply"]["line_assignments"][0]["route_id"]
        next(q for q in f["routes"] if q["id"] == ident)["geometry_status"] = "NOT_VERIFIED"
    elif mutation == "transfer":
        f["transfers"][0]["geometry_status"] = "NOT_VERIFIED"
    else:
        c["equipment"]["items"][0]["bbox_mm"][0] += 100
    assert not assess_process_candidate(c, project, parameters)["accepted"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("root_search_limit", 65),
        ("roots_per_search", 5),
        ("feedback_children", 0),
        ("nodes_per_root_search", True),
        ("full_pipeline_limit", 25),
        ("initial_layout", {}),
    ],
)
def test_invalid_or_coordinate_seed_configuration_rejected(
    field: str, value: Any, project: dict[str, Any], parameters: dict[str, Any]
) -> None:
    config = {**DEFAULT_SEARCH, field: value}
    with pytest.raises(LayoutAuthorityError):
        generate_multi_root_layout(project, parameters, config)


def test_exact_pocket_diagnostic_distinguishes_hole_from_open_channel() -> None:
    frame = [[0, 0, 1000, 100], [0, 900, 1000, 1000], [0, 100, 100, 900], [900, 100, 1000, 900]]
    assert uncovered_pockets(frame) == [
        {"bbox_mm": [100, 100, 900, 900], "area_mm2": 640000, "cells_mm": [[100, 100, 900, 900]]}
    ]
    assert uncovered_pockets(frame[:-1]) == []


def test_twelve_room_node_limit_is_actual(roots: dict[str, Any], project: dict[str, Any]) -> None:
    context = bind_autonomous_input(project)
    groups, stats = search_room_arrangements(
        context.binding.dimension_authorities,
        context.boundary,
        context.walls,
        profile="CENTRAL_PROCESS_CORE",
        node_budget=1,
        complete_limit=2,
        diverse_cores=True,
    )
    assert not groups and stats["nodes_used"] <= 1
    assert not stats["actual_root_trials"][0]["completed_in_root"]


def test_child_process_inherits_both_native_api_blocks(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend/tests/functional_native_guard"),
        "R11_FUNCTIONAL_GUARD_AUDIT": str(tmp_path),
    }
    code = """from ortools.sat.python import cp_model
for api in ('solve','Solve'):
 try: getattr(cp_model.CpSolver(),api)(cp_model.CpModel())
 except RuntimeError as e: assert 'NATIVE_FORBIDDEN' in str(e)
 else: raise AssertionError('Native was not blocked')
"""
    run = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    events = [
        json.loads(s) for file in tmp_path.glob("*.jsonl") for s in file.read_text().splitlines()
    ]
    assert sum(q["kind"] == "NATIVE_REQUEST_BLOCKED" for q in events) == 2


def test_export_is_read_only_json_coordinate_projection(
    generated: dict[int, Any], project: dict[str, Any], parameters: dict[str, Any], tmp_path: Path
) -> None:
    before = canonical_hash(generated)
    cases = [
        {"project": at_days(project, d), "result": generated[d], "resources": {"native_calls": 0}}
        for d in (7, 8)
    ]
    export_multi_root_suite(cases, parameters, tmp_path / "review", drawings=False)
    assert canonical_hash(generated) == before
    assert (tmp_path / "review/layout-review.html").exists()
    for days in (7, 8):
        folder = tmp_path / "review" / f"{days}-days"
        c = json.loads((folder / "autonomous-layout-A14-A.json").read_text())
        assert canonical_hash(c["rooms"]) == canonical_hash(
            generated[days]["candidates"][0]["rooms"]
        )
    with pytest.raises(FileExistsError):
        export_multi_root_suite(cases, parameters, tmp_path / "review", drawings=False)
