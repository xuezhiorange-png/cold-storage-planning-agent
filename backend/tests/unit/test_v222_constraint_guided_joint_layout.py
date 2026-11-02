"""Positive physical examples and fail-closed R2 search contracts, no Native."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.autonomous_factory_layout import bind_autonomous_input
from cold_storage.modules.layout.application.autonomous_multi_root_layout import (
    partial_constraint_feedback,
    room_roots,
)
from cold_storage.modules.layout.domain.constraint_guided_installation import (
    room_installation_options,
    storage_capacity_check,
)
from cold_storage.modules.layout.domain.current_process_requirements import (
    current_storage_requirements,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_material_geometry import (
    bounds_inside,
    motion_clear,
)
from cold_storage.modules.layout.domain.functional_portal_layout import joint_portals
from cold_storage.modules.layout.domain.multi_root_space import candidate_distinction
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "docs/previews/v2.2.2/autonomous-multi-root-layout-v14/inputs"


@pytest.fixture(autouse=True, scope="module")
def forbid_native_in_parent_and_children(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("CONSTRAINT_GUIDED_NATIVE_FORBIDDEN")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cp_model.CpSolver, "solve", blocked)
        patch.setattr(cp_model.CpSolver, "Solve", blocked)
        patch.setenv(
            "PYTHONPATH",
            str(ROOT / "backend/tests/functional_native_guard")
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        )
        patch.setenv(
            "R11_FUNCTIONAL_GUARD_AUDIT", str(tmp_path_factory.mktemp("joint-native-guard"))
        )
        yield


@pytest.fixture(scope="module")
def inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    return tuple(
        json.loads((INPUT / f).read_text())
        for f in ("project-input.json", "process-parameters.json")
    )  # type: ignore[return-value]


@pytest.fixture(scope="module")
def guided(inputs: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    p, parameters = inputs
    context = bind_autonomous_input(p)
    cache: dict[str, dict[str, Any]] = {}
    return {
        profile: room_roots(
            p,
            parameters,
            context,
            profile=profile,
            preferences={},
            node_budget=400,
            limit=2,
            constraint_guided=True,
            partial_cache=cache,
        )
        for profile in (
            "LINEAR_BANDED",
            "CENTRAL_PROCESS_CORE",
            "PROCESS_SPINE_WITH_PERIPHERAL_BANKS",
        )
    }


def test_partial_real_capacity_rejects_then_generates_other_complete_options(
    guided: dict[str, Any], inputs: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    p, _ = inputs
    zones = {z["zone_code"]: z for z in bind_autonomous_input(p).plan["result"]["zones"]}
    rejected = []
    total = 0
    for roots, stats in guided.values():
        rejected += [
            q
            for q in stats["partial_constraint_rejections"]
            if q["status"] == "FINITE_GRID_OPTIONS_EXHAUSTED"
        ]
        for rooms in roots:
            total += 1
            for role in current_storage_requirements(bind_autonomous_input(p).plan):
                check = storage_capacity_check(
                    rooms[role],
                    zones[role],
                    p["building"]["columns"],
                    erector=p["equipment_specs"]["case_erector"]
                    if role == "packaging_material_storage"
                    else None,
                )
                assert check["admissible"]
                assert check["required_positions"] == zones[role]["position_count"]
    assert total >= 2 and rejected
    assert any(q["placed_roles"] < 12 for q in rejected)
    assert all(q["placed_roles"] <= 12 and not q["global_infeasibility_proven"] for q in rejected)
    assert all(q["load_edge_margin_mm"] == 50 for q in rejected)


@pytest.mark.parametrize("days,required,total", [(7, 324, 493), (8, 364, 533)])
def test_grid_gate_uses_complete_current_requirement(
    inputs: tuple[dict[str, Any], dict[str, Any]], days: int, required: int, total: int
) -> None:
    p = copy.deepcopy(inputs[0])
    p["business"]["finished_storage_days"] = days
    ctx = bind_autonomous_input(p)
    req = current_storage_requirements(ctx.plan)
    assert req["finished_goods_room"]["required_positions"] == required
    assert sum(q["required_positions"] for q in req.values()) == total
    z = next(q for q in ctx.plan["result"]["zones"] if q["zone_code"] == "finished_goods_room")
    # A small local room is rejected with the true grid, never the smaller n_need.
    r = PlacedRectangleV1("finished_goods_room", Decimal(0), Decimal(0), Decimal(10), Decimal(10))
    check = storage_capacity_check(r, z, p["building"]["columns"])
    assert not check["admissible"] and check["required_positions"] == required
    assert len(check["orientations_checked"]) == 8 and not check["global_infeasibility_proven"]
    assert check["ordered_pick_put"] == "NOT_EVALUATED"


def test_local_equipment_repositions_full_body_around_a_real_column(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    column = next(
        q
        for q in inputs[0]["building"]["columns"]
        if 35000 < q["bbox_mm"][0] < 37000 and 35000 < q["bbox_mm"][1] < 37000
    )
    x, y, _, _ = column["bbox_mm"]
    room = [x - 7000, y - 4000, x + 7000, y + 4000]
    body = {
        "id": "FULL-DEVICE",
        "kind": "test_original_body",
        "bbox_mm": [x - 1000, y - 600, x + 1000, y + 600],
    }
    aisle = {
        "id": "FULL-WIDTH",
        "bbox_mm": [x - 7000, y - 4000, x + 7000, y - 1500],
        "clear_width_mm": 2500,
    }
    options, record = room_installation_options(room, [body], [], [aisle], [column])
    assert record["trials"][0]["body_failures"] and options
    selected = options[0]
    b = selected["items"][0]["bbox_mm"]
    assert b != body["bbox_mm"] and (b[2] - b[0], b[3] - b[1]) == (2000, 1200)
    assert bounds_inside(b, room) and len(selected["items"]) == 1
    assert all(q["clear_width_mm"] == 2500 for q in selected["corridors"])
    assert record["trials_used"] <= record["trial_limit"]


def test_blocked_full_width_aisle_is_rerouted_with_actual_sweeps() -> None:
    room = [0, 0, 18000, 10000]
    col = {"id": "COL", "bbox_mm": [8000, 4500, 8500, 5000]}
    aisle = {"id": "MAIN", "bbox_mm": [0, 3500, 18000, 6000], "clear_width_mm": 2500}
    options, _ = room_installation_options(room, [], [], [aisle], [col], allow_x_mirror=False)
    assert options
    detours = [q for q in options[0]["corridors"] if "derived_centerline_mm" in q]
    assert detours
    path = [tuple(p) for p in detours[0]["derived_centerline_mm"]]
    assert motion_clear(path, room, [col["bbox_mm"]], 2500, 2500)


def test_original_p1_shared_edge_can_select_a_different_legal_portal(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    context = bind_autonomous_input(inputs[0])
    req = next(
        q
        for q in context.binding.access_requirements
        if q["from_ref"] == "packaging_material_storage"
    )
    rooms = {
        "packaging_material_storage": PlacedRectangleV1(
            "packaging_material_storage",
            Decimal(0),
            Decimal(0),
            Decimal("17.3"),
            Decimal("14.5"),
            90,
        ),
        "sorting_packaging_room": PlacedRectangleV1(
            "sorting_packaging_room", Decimal("14.5"), Decimal(0), Decimal("45.76"), Decimal("13.6")
        ),
    }
    eq = {"items": [], "layouts": {k: {"service_corridors": []} for k in rooms}}
    rows = []
    for index in (0, 1):
        access, _, checks = joint_portals(
            rooms,
            [req],
            context.binding.spatial_relationships,
            eq,
            context.boundary,
            [],
            {},
            option_index=index,
            candidate_pair_limit=4,
        )
        assert access[0]["status"] == "PASS"
        assert all(q["status"] == "BODY_FREE_APPROACH" for q in checks)
        assert Decimal(access[0]["portal_clear_width_m"]) >= Decimal("2.4")
        rows.append(access[0])
    assert rows[0]["portal_from"]["segment"] != rows[1]["portal_from"]["segment"]
    for r in rows:
        assert r["canonical_hash"] == canonical_hash(
            {k: v for k, v in r.items() if k != "canonical_hash"}
        )


def test_partial_feedback_names_the_failed_room_not_unrelated_sorting(
    guided: dict[str, Any],
) -> None:
    evidence = next(
        s
        for _, s in guided.values()
        if any(q["room"] != "sorting_packaging_room" for q in s["partial_constraint_rejections"])
    )
    feedback = partial_constraint_feedback(evidence, {})
    assert feedback and any(q["failed_room"] != "sorting_packaging_room" for q in feedback)
    assert all("failed_room" in q and "room_bbox_mm" in q for q in feedback)


def test_guided_search_repeats_exact_room_and_failure_hash(
    inputs: tuple[dict[str, Any], dict[str, Any]], guided: dict[str, Any]
) -> None:
    p, parameters = inputs
    again, stats = room_roots(
        p,
        parameters,
        bind_autonomous_input(p),
        profile="LINEAR_BANDED",
        preferences={},
        node_budget=400,
        limit=2,
        constraint_guided=True,
    )
    roots, old = guided["LINEAR_BANDED"]

    def geometry(rs: Any) -> Any:
        return [{k: list(v.bounds_mm) for k, v in q.items()} for q in rs]

    assert canonical_hash([geometry(again), stats]) == canonical_hash([geometry(roots), old])


def test_local_budget_exhaustion_is_not_infeasible() -> None:
    options, record = room_installation_options(
        [0, 0, 1000, 1000],
        [{"id": "LARGE", "bbox_mm": [0, 0, 2000, 2000]}],
        [],
        [],
        [],
        trial_limit=1,
    )
    assert not options and record["trials_used"] == 1
    assert record["remaining_options"] > 0 and not record["global_infeasibility_proven"]


def test_same_organisation_variant_cannot_earn_new_organisation() -> None:
    # Labels and a process PASS alone cannot substitute for physical/core novelty.
    from cold_storage.modules.layout.domain.multi_root_space import MATERIAL_CORE

    rows = [
        {"zone_code": k, "bbox_mm": [i * 10000, 0, i * 10000 + 5000, 5000], "rotation_deg": 0}
        for i, k in enumerate(MATERIAL_CORE)
    ]
    a = {
        "source_input_hash": "same",
        "rooms": rows,
        "equipment": {"items": [], "layouts": {}},
        "access_results": [],
        "original_building": {"coordinate_mapping": {"axis_x_mm": [0, 6000]}},
        "process_admission": {"accepted": True},
    }
    b = copy.deepcopy(a)
    b["label"] = "new root"
    result = candidate_distinction(a, b)
    assert result["complete_process_qualified"]
    assert not result["physical_plan_different"] and not result["new_qualified_organisation"]


def test_same_core_geometry_with_other_equipment_is_only_a_variant() -> None:
    from cold_storage.modules.layout.domain.multi_root_space import MATERIAL_CORE

    rows = [
        {"zone_code": k, "bbox_mm": [i * 10000, 0, i * 10000 + 5000, 5000], "rotation_deg": 0}
        for i, k in enumerate(MATERIAL_CORE)
    ]
    a = {
        "source_input_hash": "same",
        "rooms": rows,
        "equipment": {
            "items": [
                {"id": "EQ", "room": MATERIAL_CORE[0], "kind": "body", "bbox_mm": [0, 0, 100, 100]}
            ],
            "layouts": {},
        },
        "access_results": [],
        "original_building": {"coordinate_mapping": {"axis_x_mm": [0, 6000]}},
        "process_admission": {"accepted": True},
    }
    b = copy.deepcopy(a)
    b["equipment"]["items"][0]["bbox_mm"] = [100, 0, 200, 100]
    result = candidate_distinction(a, b)
    assert result["physical_plan_different"] and not result["core_organisation_different"]
    assert not result["new_qualified_organisation"]


@pytest.mark.parametrize("index", [-1, 4, 100])
def test_portal_order_budget_rejects_unbounded_configuration(index: int) -> None:
    with pytest.raises(ValueError, match="BOUNDED_PORTAL_OPTION"):
        joint_portals({}, [], [], {}, (), [], {}, option_index=index)


def test_changed_input_cannot_reuse_partial_grid_evidence(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    p, parameters = inputs
    cache: dict[str, dict[str, Any]] = {}
    for days in (7, 8):
        current = copy.deepcopy(p)
        current["business"]["finished_storage_days"] = days
        before = set(cache)
        _, stats = room_roots(
            current,
            parameters,
            bind_autonomous_input(current),
            profile="LINEAR_BANDED",
            preferences={},
            constraint_guided=True,
            partial_cache=cache,
            node_budget=160,
            limit=1,
        )
        assert set(cache) - before and stats["partial_constraint_occurrences"]
        keys = {q["check_id"] for q in stats["partial_constraint_occurrences"]}
        assert keys <= set(cache) - before


def test_every_partial_failure_occurrence_has_reproducible_object_evidence(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    p, parameters = inputs
    cache: dict[str, dict[str, Any]] = {}
    _, stats = room_roots(
        p,
        parameters,
        bind_autonomous_input(p),
        profile="CENTRAL_PROCESS_CORE",
        preferences={},
        constraint_guided=True,
        partial_cache=cache,
        node_budget=120,
        limit=1,
    )
    failed = [q for q in stats["partial_constraint_occurrences"] if not q["admissible"]]
    assert failed and stats["nodes_used"] <= 120
    for q in failed:
        e = cache[q["check_id"]]
        assert e["room_bbox_mm"] and ("columns" in e or "installation" in e)
        assert not e["global_infeasibility_proven"]


def test_failed_local_portal_budget_cannot_escape_to_unaccounted_legacy_search(
    inputs: tuple[dict[str, Any], dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from cold_storage.modules.layout.domain import access_routing as routing

    ctx = bind_autonomous_input(inputs[0])
    req = next(
        q for q in ctx.binding.access_requirements if q["from_ref"] == "packaging_material_storage"
    )
    rooms = {
        "packaging_material_storage": PlacedRectangleV1(
            "packaging_material_storage", Decimal(0), Decimal(0), Decimal("17.3"), Decimal("14.5")
        ),
        "sorting_packaging_room": PlacedRectangleV1(
            "sorting_packaging_room", Decimal("17.3"), Decimal(0), Decimal("45.76"), Decimal("13.6")
        ),
    }

    def no_fallback(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("UNACCOUNTED_LEGACY_PORTAL_SEARCH")

    monkeypatch.setattr(routing, "route_access_requirement", no_fallback)
    eq = {"items": [], "layouts": {k: {"service_corridors": []} for k in rooms}}
    access, _, _ = joint_portals(
        rooms,
        [req],
        ctx.binding.spatial_relationships,
        eq,
        ctx.boundary,
        [],
        {},
        candidate_pair_limit=1,
    )
    assert access[0]["status"] != "PASS"
    assert access[0]["portal_search"]["pairs_used"] <= 1
    assert not access[0]["portal_search"]["all_continuous_portals_exhausted"]


def test_connector_extension_with_only_downstream_moves_is_not_a_new_organisation() -> None:
    from cold_storage.modules.layout.domain.multi_root_space import MATERIAL_CORE

    rows = [
        {"zone_code": k, "bbox_mm": [i * 10000, 0, i * 10000 + 5000, 5000], "rotation_deg": 0}
        for i, k in enumerate(MATERIAL_CORE)
    ]
    rows.append(
        {"zone_code": "coating_room", "bbox_mm": [0, 10000, 16000, 18300], "rotation_deg": 0}
    )
    a = {
        "source_input_hash": "same",
        "rooms": rows,
        "equipment": {"items": [], "layouts": {}},
        "access_results": [],
        "original_building": {"coordinate_mapping": {"axis_x_mm": [0, 6000]}},
        "process_admission": {"accepted": True},
    }
    b = copy.deepcopy(a)
    for r in b["rooms"]:
        if r["zone_code"] in ("finished_goods_room", "shipping_channel"):
            r["bbox_mm"][1] += 5000
            r["bbox_mm"][3] += 5000
        elif r["zone_code"] == "coating_room":
            r["bbox_mm"][3] += 5000
    distinction = candidate_distinction(a, b)
    assert distinction["only_connector_and_downstream_change"]
    assert not distinction["new_qualified_organisation"]


def test_exact_pocket_feedback_moves_incident_room_to_the_real_connection() -> None:
    from cold_storage.modules.layout.domain.constraint_guided_feedback import (
        passage_connection_feedback,
    )

    c = {
        "rooms": [
            {"zone_code": "sorting_packaging_room", "bbox_mm": [0, 0, 10000, 5000]},
            {"zone_code": "coating_room", "bbox_mm": [10000, 0, 16000, 5000]},
            {"zone_code": "finished_goods_room", "bbox_mm": [5000, 10000, 16000, 20000]},
        ],
        "equipment": {"layouts": {}},
        "original_building": {},
    }
    proposals = passage_connection_feedback(
        c,
        {"uncovered_pockets": [{"bbox_mm": [5000, 5000, 16000, 10000], "area_mm2": 55000000}]},
        [],
    )
    target = next(q for q in proposals if q["failed_room"] == "finished_goods_room")
    assert target["room_targets"] == {"finished_goods_room": [[5000, 5000]]}
    assert target["constraint"] == "ACTUAL_UNION_POCKET_CONNECTION"
    assert not any(q["failed_room"] == "sorting_packaging_room" for q in proposals)


def test_real_failed_storage_interface_proposes_its_own_aisle_alignment(
    inputs: tuple[dict[str, Any], dict[str, Any]], guided: dict[str, Any]
) -> None:
    from cold_storage.modules.layout.application.autonomous_multi_root_layout import prepare_root
    from cold_storage.modules.layout.domain.constraint_guided_feedback import (
        passage_connection_feedback,
    )

    p, _ = inputs
    ctx = bind_autonomous_input(p)
    state = guided["LINEAR_BANDED"][0][0]
    c = prepare_root(state, p, ctx)
    req = next(q for q in ctx.binding.access_requirements if q["to_ref"] == "finished_goods_room")
    feedback = passage_connection_feedback(
        c,
        {"original_predicates": [{"requirement_identity": req["identity"], "status": "BLOCKED"}]},
        ctx.binding.access_requirements,
    )
    assert feedback
    assert {q["failed_room"] for q in feedback} <= {req["from_ref"], req["to_ref"]}
    assert all(q["current_neighbor_evidence"]["portal_minimum_mm"] >= 2400 for q in feedback)
    assert any(q["room_targets"][q["failed_room"]][0] != q["room_bbox_mm"][:2] for q in feedback)


@pytest.mark.parametrize(
    "role", ["primary_precooling_room", "secondary_precooling_room", "coating_room"]
)
def test_failed_room_can_receive_its_own_actual_equipment_option(
    role: str, inputs: tuple[dict[str, Any], dict[str, Any]], guided: dict[str, Any]
) -> None:
    from cold_storage.modules.layout.application.autonomous_multi_root_layout import prepare_root
    from cold_storage.modules.layout.domain.constraint_guided_installation import (
        joint_installation_candidates,
    )

    p, parameters = inputs
    ctx = bind_autonomous_input(p)
    seed = prepare_root(guided["LINEAR_BANDED"][0][0], p, ctx)
    normal, _ = joint_installation_candidates(seed, parameters, p["equipment_specs"])
    focused, record = joint_installation_candidates(
        seed, parameters, p["equipment_specs"], focus_role=role, focus_rank=1
    )
    assert focused and record["status"] == "INSTALLATION_OPTIONS_GENERATED"
    assert focused[0]["local_option_selection"][role] == 1

    def positions(row: dict[str, Any]) -> Any:
        equipment = row["candidate"]["equipment"]
        return {
            q["id"]: q["bbox_mm"]
            for q in [*equipment["items"], *equipment.get("process_operator_zones", [])]
            if q["room"] == role
        }

    assert positions(normal[0]) != positions(focused[0])
    assert (
        len(
            focused[0]["candidate"]["equipment"]["layouts"]["sorting_packaging_room"][
                "operator_positions"
            ]
        )
        == 53
    )


def test_endpoint_failure_preserves_original_exception_and_actual_objects(
    inputs: tuple[dict[str, Any], dict[str, Any]], guided: dict[str, Any]
) -> None:
    from cold_storage.modules.layout.application.autonomous_multi_root_layout import prepare_root
    from cold_storage.modules.layout.domain.process_endpoint_routes import (
        ProcessEndpointUnavailable,
        ProcessRoutePlanner,
    )

    p, parameters = inputs
    ctx = bind_autonomous_input(p)
    seed = prepare_root(guided["LINEAR_BANDED"][0][0], p, ctx)
    # A deliberately unaccepted pre-process fixture. This is not a fabricated
    # changing PASS; the negative endpoint check needs only its context binding.
    seed["changing_function"] = {"status": "NOT_EVALUATED_FOR_ENDPOINT_NEGATIVE_TEST"}
    planner = ProcessRoutePlanner(seed, parameters, adaptive_loads=True)
    with pytest.raises(
        ProcessEndpointUnavailable, match="NO_CURRENT_MATERIAL_ACCESS:raw_fruit_buffer"
    ) as rejected:
        planner.choose_pallet_endpoint("raw_fruit_buffer", target_room="primary_precooling_room")
    assert isinstance(rejected.value, ValueError)
    assert (
        tuple(rejected.value.details["room_bbox_mm"])
        == guided["LINEAR_BANDED"][0][0]["raw_fruit_buffer"].bounds_mm
    )
    assert rejected.value.details["required_main_aisle_mm"] == parameters["main_aisle_mm"]
