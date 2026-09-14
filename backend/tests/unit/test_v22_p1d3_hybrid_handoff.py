"""Current hybrid authority, no site placement or access compliance claims."""

from copy import deepcopy
from decimal import Decimal, localcontext
from math import isqrt

import pytest

from cold_storage.modules.layout.application.dimension_handoff import (
    build_dimension_handoff,
    validate_handoff_integrity,
)
from cold_storage.modules.layout.application.dimension_zones import dimension_zones
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.dimension_handoff import EdgeOrientedConnectionV1
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.packaging_dimensioning import dimension_packaging_zone
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot

D = Decimal


def test_canonical_hybrid_and_unchanged_eight():
    source = snapshot()
    before = deepcopy(source)
    old = dimension_zones(source).to_dict()
    first = build_dimension_handoff(source)
    with localcontext() as context:
        context.prec = 2
        second = build_dimension_handoff(source)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert source == before
    body = first.to_dict()
    assert body["status"] == "DIMENSION_AUTHORITY_COMPLETE"
    assert len(body["dimensions"]) == 9
    assert len(body["authorities"]) == 12
    assert body["blocked_zones"] == []
    assert [r for r in body["dimensions"] if r["zone_code"] != "packaging_material_storage"] == old[
        "dimensions"
    ]
    assert body["adjacency_graph"] == old["adjacency_graph"]
    assert body["p1_complete"] is False
    assert body["p2_implementation_authorized"] is False
    assert body["constraint_evaluation"]["access_status"] == "ACCESS_PROFILE_REQUIRED"
    assert validate_handoff_integrity(source, body)


@pytest.mark.parametrize("code", ["coating_room", "changing_room", "office"])
def test_flexible_has_no_fake_geometry(code):
    body = build_dimension_handoff(snapshot()).to_dict()
    row = next(r for r in body["authorities"] if r["zone_code"] == code)
    assert row["status"] == "FLEXIBLE_AUTHORIZED"
    assert row["dimension_mode"] == "FLEXIBLE_RECTANGLE"
    assert row["p2_may_select_width_depth"] is True
    assert row["p2_may_change_required_area"] is False
    assert row["aspect_ratio_bounds"] is None
    assert row["rotation_allowed"] == [0, 90]
    assert row["grid_m"] == "0.001"
    assert row["area_requirement"]["reported_required_area_m2"] == row["required_area_m2"]
    assert not {"width_m", "depth_m", "actual_area_m2", "geometry", "x", "y"} & row.keys()
    assert row["personnel_portal_authorized"] is False


@pytest.mark.parametrize("mutation", ["area", "resize", "geometry", "flexible_width"])
def test_mutable_copy_cannot_override_canonical_authority(mutation):
    source = snapshot()
    body = build_dimension_handoff(source).to_dict()
    fixed = next(r for r in body["authorities"] if r["status"] == "DIMENSIONED")
    flexible = next(r for r in body["authorities"] if r["status"] == "FLEXIBLE_AUTHORIZED")
    if mutation == "area":
        flexible["required_area_m2"] = "1"
    elif mutation == "resize":
        fixed["p2_may_select_width_depth"] = True
    elif mutation == "geometry":
        fixed["geometry"]["width_m"] = "999"
    else:
        flexible["width_m"] = "8"
    assert not validate_handoff_integrity(source, body)


def test_connection_is_neither_extra_flow_nor_shared_edge_requirement():
    connection = EdgeOrientedConnectionV1()
    assert connection.accepts_topology("DIRECT_SHARED_EDGE")
    assert connection.accepts_topology("CORRIDOR_MEDIATED")
    assert not connection.accepts_topology("NEARBY")
    graph = process_graph()
    assert len(graph.must_adjacencies) == 7 and len(graph.should_adjacencies) == 5
    pair = {"packaging_material_storage", "sorting_packaging_room"}
    assert all(set(edge) != pair for edge in graph.must_adjacencies)
    assert sum(f.kind == "PACKAGING" for f in graph.flows) == 1
    body = build_dimension_handoff(snapshot()).to_dict()
    relation = body["spatial_relationships"][0]
    assert relation["from_edge_class"] == "LONG_EDGE"
    assert relation["to_edge_class"] == "SHORT_EDGE_EXIT_SIDE"
    assert relation["direction_alignment_required"]
    assert relation["portal_access_profile_required"]
    sorting = next(r for r in body["authorities"] if r["zone_code"] == "sorting_packaging_room")
    assert sorting["material_exit_edge_class"] == "SHORT_EDGE"
    assert sorting["exit_side_selection"] == "P2_RELATIVE_EDGE_SELECTION_REQUIRED"
    assert "NORTH" not in str(relation) and "corridor_width_m" not in relation


@pytest.mark.parametrize("count,area", [(1, "10"), (2, "20"), (3, "20"), (7, "40"), (67, "250.85")])
def test_packaging_integer_search_and_aisle_not_added(count, area):
    row = {
        "zone_code": "packaging_material_storage",
        "position_count": count,
        "required_area_m2": area,
    }
    result = dimension_packaging_zone(row)
    assert result == dimension_packaging_zone(row)
    assert result["position_count"] == count
    assert result["required_area_m2"] == D(area)
    assert result["actual_area_m2"] >= D(area)
    assert result["actual_area_m2"] == result["width_m"] * result["depth_m"]
    assert result["width_m"] >= result["depth_m"]
    assert result["rows"] * result["columns"] >= count
    long, depth = (D("1.2"), D("1")) if result["pallet_rotation_deg"] == 0 else (D("1"), D("1.2"))
    assert result["width_m"] >= result["columns"] * long
    assert result["depth_m"] >= result["rows"] * depth + D("3")
    assert result["aisle_added_to_required_area"] is False
    assert result["width_m"] % D("0.001") == result["depth_m"] % D("0.001") == 0


@pytest.mark.parametrize("count", [None, True, 0, -1, "67", 1.5, 10001])
def test_invalid_packaging_count_fails_closed(count):
    with pytest.raises(LayoutAuthorityError):
        dimension_packaging_zone(
            {
                "zone_code": "packaging_material_storage",
                "position_count": count,
                "required_area_m2": "10",
            }
        )


def test_packaging_resource_block_does_not_block_flexible_or_guess_count():
    source = snapshot()
    row = next(
        r for r in source["result"]["zones"] if r["zone_code"] == "packaging_material_storage"
    )
    row["position_count"] = 10001
    body = build_dimension_handoff(source).to_dict()
    assert body["blocked_zones"] == ["packaging_material_storage"]
    assert sum(r["status"] == "FLEXIBLE_AUTHORIZED" for r in body["authorities"]) == 3


def test_20t_rotation_and_independent_exact_area_optimum():
    source = snapshot()
    row = next(
        r for r in source["result"]["zones"] if r["zone_code"] == "packaging_material_storage"
    )
    r = dimension_packaging_zone(row)
    assert (r["width_m"], r["depth_m"], r["actual_area_m2"]) == (D("17.3"), D("14.5"), D("250.85"))
    assert r["pallet_rotation_deg"] == 90
    # An exact lower-bound solution exists. Independently enumerate its factor
    # pairs and all feasible grids to prove perimeter and lexical tie-break.
    candidates = []
    total = 250850000
    for short in range(1, isqrt(total) + 1):
        if total % short:
            continue
        long = total // short
        for rows in range(1, 68):
            cols = (67 + rows - 1) // rows
            for angle, a, b in ((0, 1200, 1000), (90, 1000, 1200)):
                if cols * a <= long and rows * b + 3000 <= short:
                    candidates.append((2 * (long + short), rows, cols, angle, long, short))
    best = min(candidates)
    assert best[1:] == (r["rows"], r["columns"], r["pallet_rotation_deg"], 17300, 14500)


def test_no_epsilon_or_additive_aisle_rounding():
    r = dimension_packaging_zone(
        {
            "zone_code": "packaging_material_storage",
            "position_count": 1,
            "required_area_m2": "20.000000000001",
        }
    )
    assert r["actual_area_m2"] > D("20")
    assert r["actual_area_m2"] < D("21")
