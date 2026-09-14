"""Current production replay and hostile source-binding regression."""

from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, localcontext

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.sorting_dimension_authority import (
    dimension_sorting_zone,
    sorting_profile,
)
from cold_storage.modules.layout.domain.dimensioning import (
    AreaReportingProjectionV1,
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
    dimension_zone,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot
from tests.v22_p1c0_historical_application import dimension_zones as historical_dimension_zones
from tests.v22_p1c_historical_application import dimension_zones

D = Decimal


def sorting_row(source):
    return next(r for r in source["result"]["zones"] if r["zone_code"] == "sorting_packaging_room")


def test_production_20t_seven_dimensions_and_exact_source_binding() -> None:
    source = snapshot()
    before = deepcopy(source)
    result = dimension_zones(source)
    body = result.to_dict()
    assert source == before
    assert body["calculator_identity"] == "zone_dimensioning_foundation@1.3.0"
    assert body["schema_version"] == "1.1.0"  # existing shape, revision changes profile set
    assert len(body["dimensions"]) == 7
    assert {r["zone_code"] for r in body["authority_matrix"] if r["block_reason"]} == {
        "office",
        "changing_room",
        "coating_room",
        "packaging_material_storage",
        "shipping_channel",
    }
    dimension = next(r for r in body["dimensions"] if r["zone_code"] == "sorting_packaging_room")
    assert (dimension["width_m"], dimension["depth_m"], dimension["actual_area_m2"]) == (
        "45.76",
        "13.6",
        "622.336",
    )
    assert dimension["required_area_m2"] == "622.34"
    requirement = dimension["area_requirement"]
    exact = requirement["exact_authority"]
    assert exact["exact_geometry_required_area_m2"] == "622.336"
    assert exact["source_identity"] == dimension["dimensioning_profile_identity"]
    assert exact["source_authority"] == dimension["dimensioning_authority"]
    assert (
        exact["source_snapshot_hash"]
        == dimension["capacity_geometry_reference"]
        == canonical_hash(sorting_row(source))
    )
    assert exact["source_snapshot_json"] == canonical_json(sorting_row(source))
    assert exact["operand_source_paths"] == [
        "/raw_required_area_m2",
        "/sorting_packaging_area_factor",
    ]
    assert exact["operands"] == ["565.76", "1.1"]
    assert exact["formula_identity"] == "exact-decimal-product@1.0.0"
    assert "x" not in dimension and "y" not in dimension
    old = historical_dimension_zones(source).to_dict()["dimensions"]
    assert [r for r in body["dimensions"] if r["zone_code"] != "sorting_packaging_room"] == old
    with localcontext() as ctx:
        ctx.prec = 2
        second = dimension_zones(source)
    assert second.canonical_json() == result.canonical_json()
    assert second.canonical_result_hash == result.canonical_result_hash


def test_generic_precheck_uses_requirement_and_no_exact_stays_strict() -> None:
    row = sorting_row(snapshot())
    dimension = dimension_sorting_zone(row)
    req = dimension.area_requirement
    assert req is not None and req.exact_authority is not None
    assert AreaReportingProjectionV1().project(req.exact_authority) == D("622.34")
    assert dimension_zone(row, sorting_profile(), area_requirement=req) == dimension
    with pytest.raises(LayoutAuthorityError, match="ZONE_DIMENSIONING_AUTHORITY_REQUIRED"):
        dimension_zone(row, sorting_profile())
    with pytest.raises(LayoutAuthorityError, match="ZONE_DIMENSIONING_AUTHORITY_REQUIRED"):
        dimension_zone(
            row, replace(sorting_profile(), width_offset_m=D("2.639")), area_requirement=req
        )
    with pytest.raises(LayoutAuthorityError, match="EXACT_AREA_SOURCE_BINDING_MISMATCH"):
        replace(req.exact_authority, source_snapshot_hash="sha256:" + "a" * 64)
    with pytest.raises(LayoutAuthorityError, match="EXACT_AREA_SOURCE_BINDING_MISMATCH"):
        dimension_zone(
            {**row, "extra": "changed snapshot"}, sorting_profile(), area_requirement=req
        )


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("raw_required_area_m2", 565.75, "SORTING_RAW_AREA_GEOMETRY_MISMATCH"),
        ("raw_required_area_m2", None, "INVALID_DIMENSIONING_VALUE"),
        ("sorting_packaging_area_factor", 1.2, "SORTING_AREA_FACTOR_AUTHORITY_MISMATCH"),
        ("sorting_packaging_area_factor", True, "INVALID_DIMENSIONING_VALUE"),
        ("required_area_m2", 622.33, "AREA_REPORTING_PROJECTION_MISMATCH"),
        ("n_long", 8, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("n_short", 4, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("n_actual", 22, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("n_long", True, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("position_count", 22, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("table_count", 19, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("unused_cells", 0, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("layout", {"n_long": 8, "n_short": 3}, "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
        ("aisle_layout", "guess", "INVALID_UPSTREAM_CAPACITY_GEOMETRY"),
    ],
)
def test_tampered_upstream_fails_closed(field, value, code) -> None:
    source = snapshot()
    sorting_row(source)[field] = value
    body = dimension_zones(source).to_dict()
    row = next(r for r in body["authority_matrix"] if r["zone_code"] == "sorting_packaging_room")
    assert row["dimensioning_result"] == "BLOCKED"
    assert row["block_reason"]["code"] == code
    assert len(body["dimensions"]) == 6


def test_no_caller_area_authority_or_profile_override() -> None:
    source = snapshot()
    row = sorting_row(source)
    row["exact_authority"] = {"operands": [1, 1]}
    row["dimensioning_profile_identity"] = "caller@1.0.0"
    result = dimension_sorting_zone(row)
    assert result.actual_area_m2 == D("622.336")
    assert result.dimensioning_profile_identity == sorting_profile().identity
    assert result.area_requirement.exact_authority.operands == (D("565.76"), D("1.1"))
    source["calculator_version"] = "unknown"
    with pytest.raises(LayoutAuthorityError, match="ZONE_PLAN_IDENTITY_INVALID"):
        dimension_zones(source)


@pytest.mark.parametrize("mass", [500, 1000, 5000, 10000, 20000, 30000, 50000, 100000, 200000])
def test_real_multi_grid_production_parity(mass) -> None:
    source = asdict(
        ColdRoomZonePlanner().plan(
            ColdRoomZonePlanInput(
                daily_inbound_mass_kg=mass,
                working_time_h_per_day=16,
                finished_storage_days=7,
                packaging_storage_days=3,
                precooling_required_ratio=1,
                frozen_storage_days=10,
                main_packaging_storage_days=4,
                auxiliary_packaging_storage_days=12,
            )
        )
    )
    row = sorting_row(source)
    dimension = dimension_sorting_zone(row)
    assert dimension.width_m == ((D(row["n_long"]) - 1) * D("5.6") + D("8")) * D("1.1")
    assert dimension.depth_m == (D(row["n_short"]) - 1) * D("3") + D("7.6")
    exact = D(str(row["raw_required_area_m2"])) * D(str(row["sorting_packaging_area_factor"]))
    assert dimension.actual_area_m2 == exact
    assert dimension.required_area_m2 == D(str(row["required_area_m2"]))
    first, second = dimension_zones(source), dimension_zones(source)
    assert len(first.to_dict()["dimensions"]) == 7
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
