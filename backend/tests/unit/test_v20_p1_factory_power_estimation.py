"""Unit tests for the V2.0 P1 factory-power canonical result calculator."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from cold_storage.modules.calculations.domain.factory_power_estimation import (
    CALCULATOR_IDENTITY,
    CALCULATOR_VERSION,
    MAIN_SYSTEM_COP,
    FactoryPowerEstimationError,
    FactoryPowerEstimationInput,
    build_factory_power_estimation_input,
    calculate_factory_power_estimation,
    calculate_factory_power_estimation_from_mapping,
)


def _scheme(scheme_id: str, room_count: int, area_m2: int) -> dict[str, object]:
    positions_per_room = 6 if scheme_id == "6_position" else 8
    return {
        "scheme_id": scheme_id,
        "room_count": room_count,
        "position_count": room_count * positions_per_room,
        "required_area_m2": area_m2,
    }


def _zone_rows() -> list[dict[str, object]]:
    return [
        {"zone_code": "office", "temperature_band": "常温", "required_area_m2": 80},
        {
            "zone_code": "primary_precooling_room",
            "temperature_band": "8~10℃",
            "required_area_m2": 84,
            "minimum_estimated_cooling_load_kw_r": 20,
            "cooling_estimation_basis": "v1.9-minimum-estimate",
            "reporting_scheme_id": "6_position",
            "schemes": [_scheme("6_position", 2, 84), _scheme("8_position", 1, 56)],
            "raw_position_count": 999,
        },
        {
            "zone_code": "secondary_precooling_room",
            "temperature_band": "1~3℃",
            "required_area_m2": 84,
            "minimum_estimated_cooling_load_kw_r": 15,
            "cooling_estimation_basis": "v1.9-minimum-estimate",
            "reporting_scheme_id": "6_position",
            "schemes": [_scheme("6_position", 2, 84), _scheme("8_position", 1, 56)],
            "raw_position_count": 999,
        },
        {
            "zone_code": "raw_fruit_buffer",
            "temperature_band": "8~10℃",
            "required_area_m2": 80,
            "minimum_estimated_cooling_load_kw_r": 40,
            "cooling_estimation_basis": "v1.9-minimum-estimate",
        },
        {
            "zone_code": "sorting_packaging_room",
            "temperature_band": "8~10℃",
            "required_area_m2": 140.01,
            "minimum_estimated_cooling_load_kw_r": 30,
            "cooling_estimation_basis": "v1.9-minimum-estimate",
        },
        {
            "zone_code": "coating_room",
            "temperature_band": "1~3℃",
            "required_area_m2": 70,
            "minimum_estimated_cooling_load_kw_r": 30,
            "cooling_estimation_basis": "v1.9-minimum-estimate",
        },
        {
            "zone_code": "finished_goods_room",
            "temperature_band": "1~3℃",
            "required_area_m2": 140,
            "minimum_estimated_cooling_load_kw_r": 30,
            "cooling_estimation_basis": "v1.9-minimum-estimate",
        },
        {
            "zone_code": "secondary_fruit_buffer",
            "temperature_band": "8~10℃",
            "required_area_m2": 10,
        },
        {"zone_code": "frozen_fruit_room", "temperature_band": "-18℃", "required_area_m2": 20},
        {
            "zone_code": "shipping_channel",
            "temperature_band": "1~3℃",
            "required_area_m2": 50.01,
        },
    ]


def _raw_input(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "factory_area_m2": 2500,
        "cold_storage_area_m2": 100,
        "zone_plan": {"result": {"zones": _zone_rows()}},
    }
    payload.update(overrides)
    return payload


def _details(result: Any) -> dict[str, Any]:
    return {detail.equipment_or_zone: detail for detail in result.details}


def _row(payload: dict[str, object], zone_code: str) -> dict[str, object]:
    zone_plan = payload["zone_plan"]
    assert isinstance(zone_plan, dict)
    result = zone_plan["result"]
    assert isinstance(result, dict)
    rows = result["zones"]
    assert isinstance(rows, list)
    row = next(item for item in rows if isinstance(item, dict) and item["zone_code"] == zone_code)
    assert isinstance(row, dict)
    return row


def _typed_input() -> FactoryPowerEstimationInput:
    return build_factory_power_estimation_input(_raw_input())


def _typed_input_with_zone(
    zone_code: str,
    **changes: object,
) -> FactoryPowerEstimationInput:
    calculation_input = _typed_input()
    zones = tuple(
        replace(zone, **changes) if zone.zone_code == zone_code else zone
        for zone in calculation_input.zones
    )
    return replace(calculation_input, zones=zones)


def _typed_input_with_scheme(
    zone_code: str,
    scheme_index: int = 0,
    **changes: object,
) -> FactoryPowerEstimationInput:
    calculation_input = _typed_input()
    zones = []
    for zone in calculation_input.zones:
        if zone.zone_code != zone_code:
            zones.append(zone)
            continue
        schemes = tuple(
            replace(scheme, **changes) if index == scheme_index else scheme
            for index, scheme in enumerate(zone.schemes)
        )
        zones.append(replace(zone, schemes=schemes))
    return replace(calculation_input, zones=tuple(zones))


def _assert_direct_typed_blocker(
    calculation_input: FactoryPowerEstimationInput,
    expected_code: str,
) -> None:
    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_estimation(calculation_input)

    assert exc.value.code == expected_code
    blocker = exc.value.to_blocker()
    assert blocker["success"] is False
    assert blocker["blocker"]["code"] == expected_code  # type: ignore[index]
    assert isinstance(blocker["blocker"]["details"], dict)  # type: ignore[index]


def test_v2_identity_is_distinct_and_result_has_one_canonical_shape() -> None:
    result = calculate_factory_power_estimation_from_mapping(_raw_input())

    assert CALCULATOR_IDENTITY == "factory_power_estimation@2.0.0-p1"
    assert CALCULATOR_VERSION == "2.0.0-p1"
    assert result.to_dict()["calculator"] == {
        "id": "factory_power_estimation",
        "version": "2.0.0-p1",
        "identity": "factory_power_estimation@2.0.0-p1",
    }
    payload = result.to_dict()
    assert payload["result_kind"] == "factory_power_canonical_result"
    assert payload["input_authority"]["factory_area_m2"] == "2500"
    assert payload["input_authority"]["cold_storage_area_m2"] == "100"
    raw_zone = next(
        zone
        for zone in payload["input_authority"]["zones"]
        if zone["zone_code"] == "raw_fruit_buffer"
    )
    assert raw_zone["cooling_estimation_basis"] == "v1.9-minimum-estimate"
    assert payload["provenance"]["runtime_document_parsing"] is False
    assert payload["provenance"]["legacy_authority_used"] is False
    assert payload["review"]["requires_review"] is True
    assert payload["unit_semantics"]["not_energy"] is True


@pytest.mark.parametrize(
    ("factory_area_m2", "expected_band"),
    [
        ("2499", "SMALL"),
        ("2500", "SMALL"),
        ("2500.01", "MEDIUM"),
        ("4999", "MEDIUM"),
        ("5000", "MEDIUM"),
        ("5000.01", "LARGE"),
    ],
)
def test_factory_area_band_boundaries_are_exact(
    factory_area_m2: str,
    expected_band: str,
) -> None:
    result = calculate_factory_power_estimation_from_mapping(
        _raw_input(factory_area_m2=factory_area_m2)
    )

    assert result.factory_area_band == expected_band


def test_zone_rules_use_selected_scheme_and_next_even_sorting_quantity() -> None:
    result = calculate_factory_power_estimation_from_mapping(_raw_input())
    details = _details(result)

    assert details["primary_precooling_room.air_cooler.motor"].configured_quantity == 4
    assert details["primary_precooling_room.air_cooler.defrost"].configured_quantity == 4
    assert details["primary_precooling_room.precooling_axial_fan"].configured_quantity == 48
    assert details["secondary_precooling_room.air_cooler.motor"].configured_quantity == 4
    assert details["secondary_precooling_room.precooling_axial_fan"].configured_quantity == 48
    assert details["sorting_packaging_room.air_cooler.motor"].configured_quantity == 4
    assert details["raw_fruit_buffer.air_cooler.motor"].configured_quantity == 1
    assert details["shipping_channel.air_cooler.motor"].configured_quantity == 2


@pytest.mark.parametrize(
    ("zone_code", "required_area_m2", "expected_quantity"),
    [
        ("raw_fruit_buffer", "79.99", 1),
        ("raw_fruit_buffer", "80", 1),
        ("raw_fruit_buffer", "80.01", 2),
        ("sorting_packaging_room", "69.99", 2),
        ("sorting_packaging_room", "70", 2),
        ("sorting_packaging_room", "70.01", 2),
        ("sorting_packaging_room", "140", 2),
        ("sorting_packaging_room", "140.01", 4),
        ("coating_room", "69.99", 1),
        ("coating_room", "70", 1),
        ("coating_room", "70.01", 2),
        ("finished_goods_room", "69.99", 1),
        ("finished_goods_room", "70", 1),
        ("finished_goods_room", "70.01", 2),
        ("shipping_channel", "49.99", 1),
        ("shipping_channel", "50", 1),
        ("shipping_channel", "50.01", 2),
    ],
)
def test_area_denominator_boundaries_drive_executed_quantities(
    zone_code: str,
    required_area_m2: str,
    expected_quantity: int,
) -> None:
    payload = _raw_input()
    _row(payload, zone_code)["required_area_m2"] = required_area_m2

    details = _details(calculate_factory_power_estimation_from_mapping(payload))

    assert details[f"{zone_code}.air_cooler.motor"].configured_quantity == expected_quantity


def test_eight_position_scheme_is_selected_by_reporting_scheme_id() -> None:
    payload = _raw_input()
    for zone_code in ("primary_precooling_room", "secondary_precooling_room"):
        row = _row(payload, zone_code)
        row["reporting_scheme_id"] = "8_position"
        row["schemes"] = [_scheme("6_position", 1, 42), _scheme("8_position", 3, 168)]

    details = _details(calculate_factory_power_estimation_from_mapping(payload))
    assert details["primary_precooling_room.air_cooler.motor"].configured_quantity == 6
    assert details["primary_precooling_room.precooling_axial_fan"].configured_quantity == 96
    assert details["secondary_precooling_room.air_cooler.motor"].configured_quantity == 6
    assert details["secondary_precooling_room.precooling_axial_fan"].configured_quantity == 96


@pytest.mark.parametrize(
    ("cold_storage_area_m2", "lighting_quantity", "uv_quantity"),
    [("10", 1, 1), ("10.01", 2, 1), ("20", 2, 1), ("20.01", 3, 2)],
)
def test_lighting_uses_cold_storage_area_boundaries(
    cold_storage_area_m2: str,
    lighting_quantity: int,
    uv_quantity: int,
) -> None:
    result = calculate_factory_power_estimation_from_mapping(
        _raw_input(cold_storage_area_m2=cold_storage_area_m2)
    )
    details = _details(result)

    assert details["cold_storage_lighting"].configured_quantity == lighting_quantity
    assert details["uv_lighting"].configured_quantity == uv_quantity


@pytest.mark.parametrize(
    ("factory_area_m2", "quantity"),
    [("2500", 15), ("5000", 30), ("5000.01", 50)],
)
def test_public_equipment_band_values_are_frozen(
    factory_area_m2: str,
    quantity: int,
) -> None:
    result = calculate_factory_power_estimation_from_mapping(
        _raw_input(factory_area_m2=factory_area_m2)
    )
    details = _details(result)
    door = details["public.electric_sliding_door"]

    assert door.configured_quantity == quantity
    assert door.unit_power_kw == Decimal("0.5")
    assert door.pool == "POOL_B"


def test_main_compressor_uses_exact_six_v19_minimum_loads_and_cop() -> None:
    result = calculate_factory_power_estimation_from_mapping(_raw_input())
    details = _details(result)
    main = details["main_system.compressor_shaft_power"]

    assert Decimal("3.3") == MAIN_SYSTEM_COP
    assert main.unit_power_kw == Decimal("50")
    assert main.installed_power_kw == Decimal("50")
    assert all(
        f"{zone_code}.dedicated_compressor_shaft_power" in details
        for zone_code in ("frozen_fruit_room", "secondary_fruit_buffer", "shipping_channel")
    )


def test_three_pools_are_disjoint_and_summary_replays_from_details() -> None:
    result = calculate_factory_power_estimation_from_mapping(_raw_input())
    details = result.details
    summary = result.summary

    assert len({detail.equipment_or_zone for detail in details}) == len(details)
    assert {detail.pool for detail in details} == {"POOL_A", "POOL_B", "POOL_C"}
    assert all(
        detail.pool == "POOL_A"
        for detail in details
        if detail.equipment_or_zone.endswith(".defrost")
    )
    assert all(
        detail.pool != "POOL_C"
        for detail in details
        if detail.equipment_or_zone != "production_equipment"
    )
    assert summary.defrost_installed_power_kw == Decimal("262.4")
    assert summary.defrost_coincident_power_kw == Decimal("78.720")
    assert summary.production_equipment_installed_power_kw == Decimal("200.0")
    assert summary.production_equipment_coincident_power_kw == Decimal("170.000")
    assert summary.total_installed_power_kw == (
        summary.defrost_installed_power_kw
        + summary.other_installed_power_kw
        + summary.production_equipment_installed_power_kw
    )
    assert summary.estimated_total_power_kw == (
        summary.defrost_coincident_power_kw
        + summary.other_coincident_power_kw
        + summary.production_equipment_coincident_power_kw
    )


def test_decimal_serialization_is_deterministic_without_binary_float_values() -> None:
    calculation_input = build_factory_power_estimation_input(_raw_input())
    first = calculate_factory_power_estimation(calculation_input)
    second = calculate_factory_power_estimation(calculation_input)

    assert first.canonical_json() == second.canonical_json()
    assert "500.02" in first.canonical_json()
    assert "kWh" in first.canonical_json()


@pytest.mark.parametrize(
    ("bad_value", "expected_code"),
    [
        (Decimal("-1"), "INVALID_REQUIRED_AREA_M2"),
        (Decimal("NaN"), "INVALID_REQUIRED_AREA_M2"),
        (Decimal("Infinity"), "INVALID_REQUIRED_AREA_M2"),
        ("not-a-number", "INVALID_REQUIRED_AREA_M2"),
        (True, "INVALID_REQUIRED_AREA_M2"),
    ],
)
def test_direct_typed_zone_area_is_fail_closed(
    bad_value: object,
    expected_code: str,
) -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_zone("raw_fruit_buffer", required_area_m2=bad_value),
        expected_code,
    )


@pytest.mark.parametrize(
    ("bad_value", "expected_code"),
    [
        (Decimal("-1"), "INVALID_SCHEME_REQUIRED_AREA"),
        (Decimal("NaN"), "INVALID_SCHEME_REQUIRED_AREA"),
        (Decimal("Infinity"), "INVALID_SCHEME_REQUIRED_AREA"),
        ("not-a-number", "INVALID_SCHEME_REQUIRED_AREA"),
    ],
)
def test_direct_typed_scheme_area_is_fail_closed(
    bad_value: object,
    expected_code: str,
) -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_scheme(
            "primary_precooling_room",
            required_area_m2=bad_value,
        ),
        expected_code,
    )


@pytest.mark.parametrize(
    "bad_value",
    [Decimal("-1"), Decimal("1.5"), 1.0, True],
)
def test_direct_typed_scheme_room_count_is_fail_closed(bad_value: object) -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_scheme("primary_precooling_room", room_count=bad_value),
        "INVALID_SCHEME_ROOM_COUNT",
    )


@pytest.mark.parametrize(
    "bad_value",
    [Decimal("-1"), Decimal("1.5"), 1.0, True],
)
def test_direct_typed_scheme_position_count_is_fail_closed(bad_value: object) -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_scheme("primary_precooling_room", position_count=bad_value),
        "INVALID_SCHEME_POSITION_COUNT",
    )


@pytest.mark.parametrize(
    ("bad_value", "expected_code"),
    [
        (123, "INVALID_REPORTING_SCHEME_ID"),
        ("", "INVALID_REPORTING_SCHEME_ID"),
        ("unknown", "UNKNOWN_REPORTING_SCHEME_ID"),
    ],
)
def test_direct_typed_reporting_scheme_id_is_fail_closed(
    bad_value: object,
    expected_code: str,
) -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_zone("primary_precooling_room", reporting_scheme_id=bad_value),
        expected_code,
    )


@pytest.mark.parametrize(
    ("bad_value", "expected_code"),
    [
        (123, "INVALID_PRECOOLING_SCHEME"),
        ("", "INVALID_PRECOOLING_SCHEME"),
        ("unknown", "UNKNOWN_REPORTING_SCHEME_ID"),
    ],
)
def test_direct_typed_scheme_id_is_fail_closed(
    bad_value: object,
    expected_code: str,
) -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_scheme("primary_precooling_room", scheme_id=bad_value),
        expected_code,
    )


@pytest.mark.parametrize(
    "bad_value",
    [Decimal("-1"), Decimal("NaN"), Decimal("Infinity")],
)
def test_direct_typed_cooling_authority_is_fail_closed(bad_value: object) -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_zone(
            "raw_fruit_buffer",
            minimum_estimated_cooling_load_kw_r=bad_value,
        ),
        "INVALID_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R",
    )


def test_direct_typed_cooling_basis_is_fail_closed() -> None:
    _assert_direct_typed_blocker(
        _typed_input_with_zone("raw_fruit_buffer", cooling_estimation_basis=123),
        "INVALID_COOLING_ESTIMATION_BASIS",
    )


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected_code"),
    [
        ("factory_area_m2", -1, "INVALID_FACTORY_AREA_AUTHORITY"),
        ("cold_storage_area_m2", Decimal("NaN"), "INVALID_COLD_STORAGE_AREA_AUTHORITY"),
    ],
)
def test_direct_typed_top_level_authorities_are_fail_closed(
    field_name: str,
    bad_value: object,
    expected_code: str,
) -> None:
    _assert_direct_typed_blocker(
        replace(_typed_input(), **{field_name: bad_value}),
        expected_code,
    )


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            {
                "cold_storage_area_m2": 100,
                "zone_plan": {"result": {"zones": _zone_rows()}},
                "total_area_m2": 2500,
            },
            "MISSING_FACTORY_AREA_AUTHORITY",
        ),
        (
            {
                "factory_area_m2": 2500,
                "zone_plan": {"result": {"zones": _zone_rows()}},
                "refrigerated_area_m2": 100,
            },
            "MISSING_COLD_STORAGE_AREA_AUTHORITY",
        ),
    ],
)
def test_missing_canonical_area_authority_fails_closed(
    payload: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_estimation_from_mapping(payload)

    assert exc.value.code == code
    assert exc.value.to_blocker()["success"] is False


def test_missing_required_area_does_not_fallback_to_another_area() -> None:
    payload = _raw_input()
    _row(payload, "raw_fruit_buffer").pop("required_area_m2")
    _row(payload, "raw_fruit_buffer")["total_area_m2"] = 10000

    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_estimation_from_mapping(payload)

    assert exc.value.code == "MISSING_REQUIRED_AREA_M2"


def test_missing_v19_minimum_load_does_not_fallback_to_subtotal() -> None:
    payload = _raw_input()
    row = _row(payload, "raw_fruit_buffer")
    row.pop("minimum_estimated_cooling_load_kw_r")
    row["subtotal_load_kw_r"] = 999

    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_estimation_from_mapping(payload)

    assert exc.value.code == "MISSING_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R"


def test_missing_reporting_scheme_does_not_use_raw_position_count() -> None:
    payload = _raw_input()
    row = _row(payload, "primary_precooling_room")
    row.pop("reporting_scheme_id")

    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_estimation_from_mapping(payload)

    assert exc.value.code == "MISSING_REPORTING_SCHEME_ID"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda row: row.pop("reporting_scheme_id"), "MISSING_REPORTING_SCHEME_ID"),
        (
            lambda row: row.__setitem__("reporting_scheme_id", "unknown"),
            "UNKNOWN_REPORTING_SCHEME_ID",
        ),
        (
            lambda row: row.__setitem__(
                "schemes", [_scheme("6_position", 2, 84), _scheme("6_position", 2, 84)]
            ),
            "DUPLICATE_REPORTING_SCHEME_ID",
        ),
        (
            lambda row: row["schemes"][0].pop("room_count"),
            "MISSING_SCHEME_ROOM_COUNT",
        ),
        (
            lambda row: row["schemes"][0].pop("position_count"),
            "MISSING_SCHEME_POSITION_COUNT",
        ),
    ],
)
def test_precooling_scheme_authority_fail_closed(mutation: Any, code: str) -> None:
    payload = _raw_input()
    mutation(_row(payload, "primary_precooling_room"))

    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_estimation_from_mapping(payload)

    assert exc.value.code == code


@pytest.mark.parametrize("bad_value", ["not-a-number", "NaN", "Infinity", -1])
def test_invalid_v19_authority_value_fails_closed(bad_value: object) -> None:
    payload = _raw_input()
    _row(payload, "raw_fruit_buffer")["minimum_estimated_cooling_load_kw_r"] = bad_value

    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_estimation_from_mapping(payload)

    assert exc.value.code == "INVALID_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R"


def test_missing_duplicate_and_unknown_refrigerated_zones_fail_closed() -> None:
    missing = _raw_input()
    missing_rows = missing["zone_plan"]["result"]["zones"]  # type: ignore[index]
    assert isinstance(missing_rows, list)
    missing_rows[:] = [
        row
        for row in missing_rows
        if row["zone_code"] != "shipping_channel"  # type: ignore[index]
    ]
    with pytest.raises(FactoryPowerEstimationError, match="nine refrigerated zones") as missing_exc:
        calculate_factory_power_estimation_from_mapping(missing)
    assert missing_exc.value.code == "MISSING_REFRIGERATED_ZONE"

    duplicate = _raw_input()
    duplicate_rows = duplicate["zone_plan"]["result"]["zones"]  # type: ignore[index]
    assert isinstance(duplicate_rows, list)
    duplicate_rows.append(deepcopy(_row(duplicate, "frozen_fruit_room")))
    with pytest.raises(FactoryPowerEstimationError) as duplicate_exc:
        calculate_factory_power_estimation_from_mapping(duplicate)
    assert duplicate_exc.value.code == "DUPLICATE_REFRIGERATED_ZONE"

    unknown = _raw_input()
    unknown_rows = unknown["zone_plan"]["result"]["zones"]  # type: ignore[index]
    assert isinstance(unknown_rows, list)
    unknown_rows.append({"zone_code": "unknown_refrigerated_zone", "temperature_band": "1~3℃"})
    with pytest.raises(FactoryPowerEstimationError) as unknown_exc:
        calculate_factory_power_estimation_from_mapping(unknown)
    assert unknown_exc.value.code == "UNKNOWN_REFRIGERATED_ZONE"
