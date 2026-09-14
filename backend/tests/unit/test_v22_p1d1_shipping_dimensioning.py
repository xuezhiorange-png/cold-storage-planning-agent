"""Approved pit clearance envelopes, current graph and unchanged seven-zone replay."""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from cold_storage.modules.layout.application.dimension_zones import dimension_zones
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.shipping_dimensioning import dimension_shipping_zone
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.v22_p1c_historical_application import dimension_zones as historical_dimensions
from tests.v22_p1c_historical_application import process_graph as historical_graph

D = Decimal


def row(n=1, area="50"):
    return {
        "zone_code": "shipping_channel",
        "platform_count": n,
        "position_count": n,
        "required_area_m2": area,
    }


def test_real_20t_current_eight_and_original_seven_unchanged() -> None:
    source = snapshot()
    before = deepcopy(source)
    first = dimension_zones(source)
    with localcontext() as ctx:
        ctx.prec = 2
        second = dimension_zones(source)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert source == before
    body = first.to_dict()
    assert body["calculator_identity"] == "zone_dimensioning_foundation@1.4.0"
    assert body["schema_version"] == "1.2.0"
    assert len(body["dimensions"]) == 8
    assert {r["zone_code"] for r in body["authority_matrix"] if r["block_reason"]} == {
        "office",
        "changing_room",
        "coating_room",
        "packaging_material_storage",
    }
    assert [
        r for r in body["dimensions"] if r["zone_code"] != "shipping_channel"
    ] == historical_dimensions(source).to_dict()["dimensions"]
    shipping = next(r for r in body["dimensions"] if r["zone_code"] == "shipping_channel")
    assert shipping["width_m"] == "6.5"
    assert shipping["depth_m"] == "7.693"
    assert shipping["actual_area_m2"] == "50.0045"
    assert shipping["required_area_m2"] == "50"
    assert shipping["platform_count"] == 1
    assert shipping["loading_edge_min_m"] == "7"
    assert shipping["controlling_constraint"] == "AREA"
    assert shipping["loading_face"] == "LONG_EDGE"
    assert shipping["loading_edge_dimension"] == "depth_m"
    assert shipping["area_requirement"]["exact_authority"] is None
    assert "x" not in shipping and "y" not in shipping
    assert body["constraint_evaluation"]["access_status"] == "ACCESS_PROFILE_REQUIRED"


@pytest.mark.parametrize("n", [1, 2, 3, 10, 100])
@pytest.mark.parametrize("area,controller", [("1", "PIT_MODULE"), ("10000", "AREA")])
def test_pits_wall_clearances_and_area_both_constrain(n, area, controller) -> None:
    result = dimension_shipping_zone(row(n, area))
    minimum = 2 * D("2.5") + n * D("2") + (n - 1) * D("2.5")
    assert result["loading_edge_min_m"] == minimum
    assert result["width_m"] == D("6.5")
    assert result["depth_m"] >= minimum
    assert result["min_pit_to_pit_clearance_m"] == D("2.5")
    assert result["min_pit_to_side_wall_clearance_m"] == D("2.5")
    assert result["pit_width_m"] == D("2")
    assert result["actual_area_m2"] == D("6.5") * result["depth_m"] >= D(area)
    assert result["depth_m"] % D("0.001") == 0
    assert result["controlling_constraint"] == controller
    # One grid step smaller must violate an approved lower bound: no arbitrary inflation.
    shorter = result["depth_m"] - D("0.001")
    assert shorter < minimum or shorter * D("6.5") < D(area)


@pytest.mark.parametrize(
    "area,depth",
    [("45.5", "7"), ("45.500000000001", "7.001"), ("50", "7.693"), ("50.0045", "7.693")],
)
def test_no_epsilon_and_exact_outward_grid(area, depth) -> None:
    dimension = dimension_shipping_zone(row(1, area))
    assert dimension["depth_m"] == D(depth)
    if area == "45.5":
        assert dimension["controlling_constraint"] == "BOTH"


@pytest.mark.parametrize("count", [None, True, 0, -1, "1", 1.5, 10**12 + 1])
def test_invalid_platform_count_is_never_recomputed(count) -> None:
    with pytest.raises(LayoutAuthorityError, match="INVALID_UPSTREAM_SHIPPING_AUTHORITY"):
        dimension_shipping_zone(row(count))


def test_count_mismatch_and_no_profile_override() -> None:
    with pytest.raises(LayoutAuthorityError, match="INVALID_UPSTREAM_SHIPPING_AUTHORITY"):
        dimension_shipping_zone({**row(), "position_count": 2})
    assert dimension_shipping_zone({**row(), "fixed_width_m": 999})["width_m"] == D("6.5")


def test_office_relations_do_not_change_flows_or_duplicate_edges() -> None:
    graph = process_graph()
    old = historical_graph()
    assert graph.identity == "charles-v22-process-flow@1.1.0"
    assert graph.must_adjacencies == old.must_adjacencies + (("office", "shipping_channel"),)
    assert graph.should_adjacencies == old.should_adjacencies + (
        ("office", "primary_precooling_room"),
    )
    assert graph.flows == tuple(
        type(graph.flows[0])(f.kind, f.from_ref, f.to_ref) for f in old.flows
    )
    assert graph.zone_access_proximities == old.zone_access_proximities
    assert len({frozenset(p) for p in (*graph.must_adjacencies, *graph.should_adjacencies)}) == 12
