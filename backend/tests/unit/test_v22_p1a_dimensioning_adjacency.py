"""Actual planner replay, hostile authority cases, pure rectangle predicates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from typing import Any

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.dimension_zones import (
    GRID_ZONES,
    dimension_zones,
    upstream_profiles,
)
from cold_storage.modules.layout.domain.adjacency import (
    PROCESS_FLOW,
    RectangleObservationV1,
    evaluate_adjacency,
    process_graph,
    shared_edge_adjacent,
)
from cold_storage.modules.layout.domain.dimensioning import (
    AccessProfileV1,
    LayoutAuthorityError,
    ZoneDimensionProfileV1,
    canonical_hash,
    canonical_json,
    dimension_zone,
    require_access_profile,
)

D = Decimal


def snapshot() -> dict[str, Any]:
    result = ColdRoomZonePlanner().plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=20000,
            working_time_h_per_day=16,
            finished_storage_days=7,
            packaging_storage_days=3,
            precooling_required_ratio=1,
            frozen_storage_days=10,
            main_packaging_storage_days=4,
            auxiliary_packaging_storage_days=12,
        )
    )
    assert result.success
    return asdict(result)


def test_actual_current_planner_authority_matrix_and_determinism() -> None:
    source = snapshot()
    before = deepcopy(source)
    first, second = dimension_zones(source), dimension_zones(source)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert source == before
    body = first.to_dict()
    assert body["source_zone_plan_result_hash"] == canonical_hash(source)
    assert body["source_formula_authority"] == "POST-V2.1.1-charles-engineering-rule-adjustments"
    assert body["status"] == "PARTIAL_ENGINEERING_AUTHORITY"
    assert len(body["authority_matrix"]) == 12
    assert {row["zone_code"] for row in body["dimensions"]} == set(GRID_ZONES)
    assert len(body["dimensions"]) == 4
    rows = {row["zone_code"]: row for row in source["result"]["zones"]}
    for row in body["dimensions"]:
        assert D(row["actual_area_m2"]) == D(row["width_m"]) * D(row["depth_m"])
        assert D(row["actual_area_m2"]) >= D(str(rows[row["zone_code"]]["required_area_m2"]))
        assert row["capacity_geometry_reference"] == canonical_hash(rows[row["zone_code"]])
        assert "x" not in row and "y" not in row
    for entry in body["authority_matrix"]:
        assert canonical_json(entry["upstream_zone"]) == canonical_json(rows[entry["zone_code"]])
        if entry["dimensioning_result"] == "BLOCKED":
            error = entry["block_reason"]
            assert error["code"] == "ZONE_DIMENSIONING_AUTHORITY_REQUIRED"
            assert error["details"]["zone_code"] == entry["zone_code"]
            assert error["details"]["missing_profile"] is True
    sorting = next(
        row for row in body["authority_matrix"] if row["zone_code"] == "sorting_packaging_room"
    )
    assert sorting["required_area_m2"] == "622.34"
    assert sorting["upstream_zone"]["raw_required_area_m2"] == "565.76"
    assert sorting["dimensioning_result"] == "BLOCKED"
    for code in ("primary_precooling_room", "secondary_precooling_room"):
        assert rows[code]["schemes"]
        assert rows[code]["reporting_scheme_id"] == "6_position"
    # A consumer mutating its copy cannot mutate the held canonical evidence.
    body["dimensions"][0]["width_m"] = "99999"
    assert first.canonical_result_hash == second.canonical_result_hash
    reversed_keys = dict(reversed(list(source.items())))
    assert dimension_zones(reversed_keys).canonical_result_hash == first.canonical_result_hash
    with localcontext() as ctx:
        ctx.prec = 2
        assert dimension_zones(source).canonical_json() == first.canonical_json()


@pytest.mark.parametrize("value", [None, True, -1, "NaN", "Infinity", "abc", "-Infinity"])
def test_invalid_area_is_source_failure(value: object) -> None:
    source = snapshot()
    source["result"]["zones"][0]["required_area_m2"] = value
    with pytest.raises(LayoutAuthorityError, match="ZONE_PLAN_IDENTITY_INVALID"):
        dimension_zones(source)


@pytest.mark.parametrize(
    "field,value",
    [
        ("success", False),
        ("success", 1),
        ("calculator_name", "fake"),
        ("calculator_version", "2.0.0"),
        ("result", None),
    ],
)
def test_identity_fail_closed(field: str, value: object) -> None:
    source = snapshot()
    source[field] = value
    with pytest.raises(LayoutAuthorityError, match="ZONE_PLAN_IDENTITY_INVALID"):
        dimension_zones(source)


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "formula", "area_missing"])
def test_source_hostile_set_and_formula(change: str) -> None:
    source = snapshot()
    rows = source["result"]["zones"]
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[-1] = deepcopy(rows[0])
    elif change == "unknown":
        rows[-1]["zone_code"] = "fake_zone"
    elif change == "formula":
        source["result"]["planning_parameters"]["formula_authority"] = "old"
    else:
        del rows[0]["required_area_m2"]
    with pytest.raises(LayoutAuthorityError, match="ZONE_PLAN_IDENTITY_INVALID"):
        dimension_zones(source)


@pytest.mark.parametrize(
    "field,value",
    [
        ("n_long", 0),
        ("n_short", True),
        ("n_actual", 1),
        ("position_count", 1),
        ("layout", {}),
        ("aisle_layout", "fake"),
    ],
)
def test_upstream_geometry_cannot_be_repaired_or_repacked(field: str, value: object) -> None:
    source = snapshot()
    row = next(z for z in source["result"]["zones"] if z["zone_code"] == "raw_fruit_buffer")
    row[field] = value
    body = dimension_zones(source).to_dict()
    entry = next(z for z in body["authority_matrix"] if z["zone_code"] == "raw_fruit_buffer")
    assert entry["block_reason"]["code"] == "INVALID_UPSTREAM_CAPACITY_GEOMETRY"
    assert "raw_fruit_buffer" not in {z["zone_code"] for z in body["dimensions"]}


def fixed_profile() -> ZoneDimensionProfileV1:
    # Explicit test-only profile, not a shipped/Charles-approved engineering rule.
    return ZoneDimensionProfileV1(
        "test-only-office",
        "1.0.0",
        "office",
        "FIXED_ENVELOPE",
        D("2.0001"),
        D("3"),
        "synthetic unit fixture",
    )


def test_explicit_profile_rounds_outward_and_never_multiplies_required_area() -> None:
    row = {"zone_code": "office", "required_area_m2": "6.001"}
    result = dimension_zone(row, fixed_profile())
    assert result.width_m == D("2.001")
    assert result.actual_area_m2 == D("6.003")
    assert (
        dimension_zone(row, fixed_profile(), rotation_deg=90).actual_area_m2
        == result.actual_area_m2
    )
    with pytest.raises(LayoutAuthorityError, match="INVALID_ROTATION"):
        dimension_zone(row, fixed_profile(), rotation_deg=45)
    with pytest.raises(LayoutAuthorityError, match="ZONE_DIMENSIONING_AUTHORITY_REQUIRED"):
        dimension_zone({**row, "required_area_m2": "10"}, fixed_profile())
    with pytest.raises(LayoutAuthorityError, match="ZONE_DIMENSIONING_AUTHORITY_REQUIRED") as exc:
        dimension_zone(row, None)
    assert exc.value.details == {
        "zone_code": "office",
        "missing_profile": True,
        "required_area_m2": "6.001",
    }
    with pytest.raises(LayoutAuthorityError, match="ZONE_DIMENSIONING_AUTHORITY_REQUIRED"):
        dimension_zone({**row, "schemes": []}, fixed_profile())
    with pytest.raises(LayoutAuthorityError, match="MAY_NOT_BE_REPACKED"):
        replace(fixed_profile(), capacity_geometry_policy="REPACK")


def test_profile_source_and_result_are_hash_bound() -> None:
    source = snapshot()
    first = dimension_zones(source)
    source["result"]["zones"][0]["required_area_m2"] += 1
    second = dimension_zones(source)
    assert first.canonical_result_hash != second.canonical_result_hash
    profile = upstream_profiles()[0]
    assert canonical_hash(asdict(profile)) != canonical_hash(
        asdict(replace(profile, profile_version="2"))
    )


def test_process_graph_exact_authority() -> None:
    expected = (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    graph = process_graph()
    assert expected == PROCESS_FLOW
    assert graph.must_adjacencies == tuple(zip(expected[:-1], expected[1:], strict=True))
    assert len(graph.must_adjacencies) == 6
    assert len(graph.should_adjacencies) == 4
    assert len(graph.nodes) == 12
    assert graph.zone_access_proximities == (("shipping_channel", "truck_entrance"),)
    assert ("packaging_material_storage", "sorting_packaging_room") not in graph.must_adjacencies
    with pytest.raises(LayoutAuthorityError, match="INVALID_ADJACENCY_GRAPH"):
        replace(graph, must_adjacencies=graph.must_adjacencies + (graph.must_adjacencies[0],))


def rectangle(
    code: str, x: str, y: str, w: str = "2", d: str = "2", rotation: int = 0
) -> RectangleObservationV1:
    return RectangleObservationV1(code, D(x), D(y), D(w), D(d), rotation)


@pytest.mark.parametrize(
    "x,y,expected",
    [
        ("2", "0", True),
        ("2", "1", True),
        ("2", "2", False),
        ("2.001", "0", False),
        ("1", "1", False),
        ("0", "0", False),
    ],
)
def test_positive_edge_only_not_corner_nearby_or_overlap(x: str, y: str, expected: bool) -> None:
    assert (
        shared_edge_adjacent(rectangle("office", "0", "0"), rectangle("changing_room", x, y))
        is expected
    )


def test_adjacency_evaluation_not_full_site_acceptance() -> None:
    graph = process_graph()
    assert evaluate_adjacency(graph, ())["geometry_passed"] is False
    # Synthetic observations test predicates; no production placement solver.
    observations = tuple(rectangle(code, str(i * 2), "0") for i, code in enumerate(PROCESS_FLOW))
    observations += tuple(
        rectangle(code, str(i * 3), "20")
        for i, code in enumerate(graph.nodes)
        if code not in PROCESS_FLOW
    )
    evaluation = evaluate_adjacency(graph, observations)
    assert evaluate_adjacency(graph, tuple(reversed(observations))) == evaluation
    with localcontext() as ctx:
        ctx.prec = 2
        assert evaluate_adjacency(graph, observations) == evaluation
        assert rectangle("office", "123.001", "0").bounds()[2] == D("125.001")
    assert evaluation["geometry_passed"] is True
    assert evaluation["access_status"] == "NOT_EVALUATED"
    assert evaluation["unsatisfied_should"]
    overlapping = (observations[0], replace(observations[1], x=D("1")))
    errors = evaluate_adjacency(graph, overlapping)["violations"]
    assert any(error["code"] == "ZONE_OVERLAP" for error in errors)
    assert any(error["code"] == "HARD_CONSTRAINT_UNSATISFIABLE" for error in errors)
    with pytest.raises(LayoutAuthorityError):
        evaluate_adjacency(graph, (observations[0], observations[0]))
    assert shared_edge_adjacent(
        rectangle("office", "0", "0", "3", "2", 90), rectangle("changing_room", "2", "0")
    )


def test_access_authority_required_never_guessed() -> None:
    with pytest.raises(LayoutAuthorityError, match="ACCESS_PROFILE_REQUIRED"):
        require_access_profile(None)
    profile = AccessProfileV1("test-only@1", "synthetic", D("1"))
    assert require_access_profile(profile) == profile
    with pytest.raises(LayoutAuthorityError):
        AccessProfileV1("test-only@1", "synthetic", D("NaN"))
