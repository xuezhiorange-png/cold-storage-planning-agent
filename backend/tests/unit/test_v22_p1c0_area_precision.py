"""Exact geometry vs reported area: generic contract, no production sorting binder."""

from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, localcontext

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.layout.application.dimension_zones import dimension_zones
from cold_storage.modules.layout.domain.dimensioning import (
    AreaReportingProjectionV1,
    AreaRequirementV1,
    ExactAreaAuthorityV1,
    LayoutAuthorityError,
    ZoneDimensionV1,
    canonical_hash,
    canonical_json,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot

D = Decimal
PROFILE = "synthetic-area-contract@1.0.0"
SOURCE = "synthetic contract fixture; not production engineering approval"
HASH = canonical_hash({"operand0": "565.76", "operand1": "1.10"})


def authority(*operands: str) -> ExactAreaAuthorityV1:
    source = {f"operand{i}": value for i, value in enumerate(operands)}
    return ExactAreaAuthorityV1(
        PROFILE,
        SOURCE,
        canonical_hash(source),
        tuple(f"/operand{i}" for i in range(len(operands))),
        tuple(D(v) for v in operands),
        canonical_json(source),
    )


def requirement(reported: str = "622.34") -> AreaRequirementV1:
    return AreaRequirementV1(
        D(reported),
        exact_authority=authority("565.76", "1.10"),
        reporting_projection=AreaReportingProjectionV1(),
    )


def dimension(
    req: AreaRequirementV1 | None = None,
    width: str = "45.76",
    depth: str = "13.60",
    actual: str = "622.336",
) -> ZoneDimensionV1:
    return ZoneDimensionV1(
        "synthetic-zone",
        D("622.34"),
        D(width),
        D(depth),
        D(actual),
        0,
        PROFILE,
        SOURCE,
        HASH,
        req,
    )


def test_exact_geometry_vs_reported_area_rounding_no_inflation() -> None:
    result = dimension(requirement())
    assert result.width_m == D("45.76") and result.depth_m == D("13.60")
    assert result.actual_area_m2 == D("622.336")
    assert result.required_area_m2 == D("622.34")
    evidence = asdict(result)["area_requirement"]
    assert evidence["exact_authority"]["exact_geometry_required_area_m2"] == D("622.336")
    assert evidence["exact_authority"]["source_snapshot_hash"] == HASH
    first_hash = canonical_hash(asdict(result))
    with localcontext() as ctx:
        ctx.prec = 2
        assert canonical_hash(asdict(dimension(requirement()))) == first_hash


@pytest.mark.parametrize("actual", ["622.335", "622.335999", "622.331"])
def test_actual_below_exact_no_epsilon(actual: str) -> None:
    with pytest.raises(LayoutAuthorityError, match="INVALID_ZONE_DIMENSION"):
        dimension(requirement(), width=actual, depth="1", actual=actual)


def test_reporting_mismatch_rejected() -> None:
    with pytest.raises(LayoutAuthorityError, match="AREA_REPORTING_PROJECTION_MISMATCH"):
        requirement("622.33")


def test_missing_exact_authority_keeps_strict_invariant() -> None:
    for req in (None, AreaRequirementV1(D("622.34"))):
        with pytest.raises(LayoutAuthorityError, match="INVALID_ZONE_DIMENSION"):
            dimension(req)
    with pytest.raises(LayoutAuthorityError, match="EXACT_AREA_AUTHORITY_REQUIRED"):
        AreaRequirementV1(D("622.34"), reporting_projection=AreaReportingProjectionV1())


@pytest.mark.parametrize(
    "field,value",
    [
        ("identity", "unknown@1.0.0"),
        ("quantum", D("0.1")),
        ("source_authority", "caller"),
        ("projection_method", "ROUND_HALF_UP"),
    ],
)
def test_invalid_projection_identity_and_method_fail_closed(field: str, value: object) -> None:
    with pytest.raises(LayoutAuthorityError, match="INVALID_REPORTING_PROJECTION"):
        replace(AreaReportingProjectionV1(), **{field: value})


def test_no_reported_value_aliasing_no_naked_exact_number_or_cross_source() -> None:
    with pytest.raises(LayoutAuthorityError, match="INVALID_ZONE_DIMENSION"):
        dimension(requirement(), actual="622.34")
    with pytest.raises(LayoutAuthorityError, match="INVALID_EXACT_AREA_AUTHORITY"):
        AreaRequirementV1(D("622.34"), exact_authority=D("622.336"))  # type: ignore[arg-type]
    for field, value in (
        ("source_identity", "other-profile@1.0.0"),
        ("source_authority", "other authority"),
    ):
        req = replace(
            requirement(), exact_authority=replace(authority("565.76", "1.10"), **{field: value})
        )
        with pytest.raises(LayoutAuthorityError, match="EXACT_AREA_SOURCE_BINDING_MISMATCH"):
            dimension(req)


@pytest.mark.parametrize("change", ["hash", "operand", "path", "snapshot"])
def test_exact_operands_bound_to_source_snapshot_not_self_reported(change: str) -> None:
    changes = {
        "hash": {"source_snapshot_hash": "sha256:" + "b" * 64},
        "operand": {"operands": (D("1"), D("1.10"))},
        "path": {"operand_source_paths": ("/unknown", "/operand1")},
        "snapshot": {"source_snapshot_json": '{"operand0":"1","operand1":"1.10"}'},
    }
    with pytest.raises(LayoutAuthorityError, match="EXACT_AREA_SOURCE_BINDING_MISMATCH"):
        replace(authority("565.76", "1.10"), **changes[change])


@pytest.mark.parametrize("value", ["2.675", "1.005", "2.685", "622.336", "0", "100.125"])
def test_projection_is_python_binary64_round_not_half_up(value: str) -> None:
    assert AreaReportingProjectionV1().project(authority(value)) == D(str(round(float(value), 2)))
    assert AreaReportingProjectionV1().project(authority("2.675")) == D("2.67")


def test_reporting_replays_operand_order_not_float_of_exact_product() -> None:
    source = authority("0.1", "0.35")
    assert source.exact_geometry_required_area_m2 == D("0.035")
    assert AreaReportingProjectionV1().project(source) == D("0.03")
    assert round(float(source.exact_geometry_required_area_m2), 2) == 0.04


@pytest.mark.parametrize("mass", [500, 1000, 5000, 10000, 20000, 30000, 50000, 100000, 200000])
def test_real_planner_reporting_parity_over_multiple_grid_candidates(mass: int) -> None:
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
    assert source["success"]
    row = next(r for r in source["result"]["zones"] if r["zone_code"] == "sorting_packaging_room")
    raw_long = (D(row["n_long"]) - 1) * D("5.6") + D("8.0")
    raw_short = (D(row["n_short"]) - 1) * D("3.0") + D("7.6")
    assert raw_long * raw_short == D(str(row["raw_required_area_m2"]))
    evidence = authority(
        str(row["raw_required_area_m2"]), str(row["sorting_packaging_area_factor"])
    )
    assert AreaReportingProjectionV1().project(evidence) == D(str(row["required_area_m2"]))


def test_existing_six_zone_geometry_and_capacity_unchanged_sorting_still_blocked() -> None:
    source = snapshot()
    original = deepcopy(source)
    result = dimension_zones(source)
    body = result.to_dict()
    assert source == original
    assert body["calculator_identity"] == "zone_dimensioning_foundation@1.2.0"
    assert body["schema_version"] == "1.1.0"
    # Immutable P1B 20t geometry, not newly derived expected dimensions.
    expected = {
        "raw_fruit_buffer": ("15.2", "8.7", "132.24"),
        "finished_goods_room": ("32.4", "18.6", "602.64"),
        "secondary_fruit_buffer": ("8.4", "6.9", "57.96"),
        "frozen_fruit_room": ("10.8", "8.2", "88.56"),
        "primary_precooling_room": ("14.7", "10.05", "147.735"),
        "secondary_precooling_room": ("9.8", "10.05", "98.49"),
    }
    assert {
        r["zone_code"]: (r["width_m"], r["depth_m"], r["actual_area_m2"])
        for r in body["dimensions"]
    } == expected
    assert all(r["area_requirement"]["exact_authority"] is None for r in body["dimensions"])
    blocked = {r["zone_code"] for r in body["authority_matrix"] if r["block_reason"]}
    assert blocked == {
        "office",
        "changing_room",
        "sorting_packaging_room",
        "coating_room",
        "packaging_material_storage",
        "shipping_channel",
    }
    assert result.canonical_json() == dimension_zones(source).canonical_json()
    assert result.canonical_result_hash == dimension_zones(source).canonical_result_hash
