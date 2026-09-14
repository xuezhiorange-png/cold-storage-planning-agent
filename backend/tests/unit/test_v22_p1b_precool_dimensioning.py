"""Explicit room authority, upstream integrity and real canonical replay."""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.precool_dimensioning import (
    PRECOOL_ZONES,
    dimension_precool_zone,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.v22_p1c0_historical_application import dimension_zones


@pytest.mark.parametrize("code", PRECOOL_ZONES)
@pytest.mark.parametrize("positions,depth", [(6, "10.05"), (8, "12.95")])
@pytest.mark.parametrize("rooms", [1, 2, 7])
def test_explicit_room_array(code: str, positions: int, depth: str, rooms: int) -> None:
    row = {
        "zone_code": code,
        "reporting_scheme_id": f"{positions}_position",
        "position_count": rooms * positions,
        "required_area_m2": rooms * (42 if positions == 6 else 56),
    }
    row["schemes"] = [
        {
            "scheme_id": row["reporting_scheme_id"],
            "room_count": rooms,
            "positions_per_room": positions,
            "position_count": row["position_count"],
            "required_area_m2": row["required_area_m2"],
        }
    ]
    original = deepcopy(row)
    dimension = dimension_precool_zone(row)
    assert row == original
    assert dimension["width_m"] == rooms * Decimal("4.90")
    assert dimension["depth_m"] == Decimal(depth)
    assert dimension["actual_area_m2"] == rooms * Decimal("4.90") * Decimal(depth)
    assert dimension["required_area_m2"] == row["required_area_m2"]
    assert dimension["room_count"] == rooms
    assert dimension["position_count"] == row["position_count"]
    assert dimension["selected_scheme_id"] == row["reporting_scheme_id"]
    assert dimension["room_arrangement"] == "LONG_SIDES_PARALLEL"
    assert "x" not in dimension and "y" not in dimension


def test_actual_20t_six_dimensioned_six_blocked_and_hash_deterministic() -> None:
    source = snapshot()
    before = deepcopy(source)
    first = dimension_zones(source)
    with localcontext() as context:
        context.prec = 2
        second = dimension_zones(source)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert source == before
    body = first.to_dict()
    assert body["calculator_identity"] == "zone_dimensioning_foundation@1.2.0"
    assert len(body["dimensions"]) == 6
    blocked = {r["zone_code"] for r in body["authority_matrix"] if r["block_reason"]}
    assert blocked == {
        "office",
        "changing_room",
        "sorting_packaging_room",
        "coating_room",
        "packaging_material_storage",
        "shipping_channel",
    }
    for code, rooms, width, required, actual in (
        (PRECOOL_ZONES[0], 3, "14.7", "126", "147.735"),
        (PRECOOL_ZONES[1], 2, "9.8", "84", "98.49"),
    ):
        dimension = next(r for r in body["dimensions"] if r["zone_code"] == code)
        assert dimension["room_count"] == rooms
        assert dimension["selected_scheme_id"] == "6_position"
        assert dimension["width_m"] == width
        assert dimension["depth_m"] == "10.05"
        assert dimension["required_area_m2"] == required
        assert dimension["actual_area_m2"] == actual


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "missing_id",
        "missing_selected",
        "duplicate_selected",
        "bad_list",
        "rooms_bool",
        "rooms_zero",
        "rooms_fractional",
        "positions",
        "per_room",
        "top_positions",
        "top_rooms",
        "area_mismatch",
        "insufficient",
        "no_room_count",
    ],
)
def test_hostile_selected_scheme_never_repaired(mutation: str) -> None:
    source = snapshot()
    row = next(r for r in source["result"]["zones"] if r["zone_code"] == PRECOOL_ZONES[0])
    selected = row["schemes"][0]
    if mutation == "unknown":
        row["reporting_scheme_id"] = "unknown"
    elif mutation == "missing_id":
        del row["reporting_scheme_id"]
    elif mutation == "missing_selected":
        row["schemes"] = row["schemes"][1:]
    elif mutation == "duplicate_selected":
        row["schemes"].append(deepcopy(selected))
    elif mutation == "bad_list":
        row["schemes"] = None
    elif mutation.startswith("rooms_"):
        selected["room_count"] = {"rooms_bool": True, "rooms_zero": 0, "rooms_fractional": 1.5}[
            mutation
        ]
    elif mutation == "positions":
        selected["position_count"] = 999
    elif mutation == "per_room":
        selected["positions_per_room"] = 8
    elif mutation == "top_positions":
        row["position_count"] = True
    elif mutation == "top_rooms":
        row["room_count"] = 999
    elif mutation == "no_room_count":
        del selected["room_count"]
    elif mutation == "area_mismatch":
        row["required_area_m2"] = 999
    else:
        row["required_area_m2"] = selected["required_area_m2"] = 999
    before = deepcopy(source)
    body = dimension_zones(source).to_dict()
    assert source == before
    assert PRECOOL_ZONES[0] not in {r["zone_code"] for r in body["dimensions"]}
    error = next(r for r in body["authority_matrix"] if r["zone_code"] == PRECOOL_ZONES[0])[
        "block_reason"
    ]
    expected = (
        "UNKNOWN_PRECOOL_GEOMETRY_PROFILE"
        if mutation in {"unknown", "missing_id"}
        else "UPSTREAM_PRECOOL_AREA_MISMATCH"
        if mutation == "area_mismatch"
        else "PRECOOL_GEOMETRY_AREA_INSUFFICIENT"
        if mutation == "insufficient"
        else "INVALID_UPSTREAM_PRECOOL_SCHEME"
    )
    assert error["code"] == expected
    if mutation == "insufficient":
        assert Decimal(error["details"]["actual_area_m2"]) == Decimal("147.735")


def test_no_area_derived_edges_or_fallback_to_reporting_default() -> None:
    source = snapshot()
    row = next(r for r in source["result"]["zones"] if r["zone_code"] == PRECOOL_ZONES[0])
    selected = row["schemes"][1]
    row["reporting_scheme_id"] = selected["scheme_id"]
    row["position_count"] = selected["position_count"]
    row["required_area_m2"] = selected["required_area_m2"]
    result = dimension_precool_zone(row)
    assert result["selected_scheme_id"] == "8_position"
    assert result["depth_m"] == Decimal("12.95")
    row["required_area_m2"] = selected["required_area_m2"] = 1
    assert dimension_precool_zone(row)["width_m"] == result["width_m"]
    assert dimension_precool_zone(row)["depth_m"] == result["depth_m"]
    row["zone_code"] = "office"
    with pytest.raises(LayoutAuthorityError, match="INVALID_PRECOOL_ZONE"):
        dimension_precool_zone(row)
