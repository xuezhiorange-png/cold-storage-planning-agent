"""Unit coverage for the V2.1 P1 factory-power authority adapter."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest

from cold_storage.modules.calculations.domain.factory_power_estimation import (
    FactoryPowerEstimationError,
    calculate_factory_power_estimation_from_mapping,
)
from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner
from cold_storage.modules.planning.application.service import (
    build_zone_plan_from_inputs,
    demo_inputs,
)
from cold_storage.modules.projects.application.factory_power_upstream_authority import (
    EXPECTED_FACTORY_ZONE_CODES,
    REFRIGERATED_ZONE_CODES,
    FactoryPowerUpstreamAuthorityError,
    build_factory_power_upstream_authority,
    calculate_factory_power_from_zone_plan,
)
from cold_storage.modules.projects.application.operator_process_input import (
    REFRIGERATED_ZONE_REGISTRY,
)

AREA_QUANTUM = Decimal("0.01")


def _zone_plan_snapshot() -> dict[str, Any]:
    result = build_zone_plan_from_inputs(demo_inputs(), ColdRoomZonePlanner())
    assert result.success is True
    snapshot = asdict(result)
    assert isinstance(snapshot, dict)
    return snapshot


def _result(snapshot: dict[str, Any]) -> dict[str, Any]:
    result = snapshot["result"]
    assert isinstance(result, dict)
    return result


def _rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _result(snapshot)["zones"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _row(snapshot: dict[str, Any], zone_code: str) -> dict[str, Any]:
    return next(row for row in _rows(snapshot) if row.get("zone_code") == zone_code)


def _expected_area(snapshot: dict[str, Any], zone_codes: tuple[str, ...]) -> Decimal:
    return sum(
        (Decimal(str(_row(snapshot, zone_code)["required_area_m2"])) for zone_code in zone_codes),
        Decimal("0"),
    ).quantize(AREA_QUANTUM, rounding=ROUND_HALF_UP)


def _v20_compatible_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirror only the V2.0 optional provenance representation boundary."""
    rows = deepcopy(_rows(snapshot))
    for row in rows:
        basis = row.get("cooling_estimation_basis")
        if isinstance(basis, dict):
            row["cooling_estimation_basis"] = json.dumps(
                basis,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
    return rows


def _manual_v20_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "factory_area_m2": _expected_area(snapshot, EXPECTED_FACTORY_ZONE_CODES),
        "cold_storage_area_m2": _expected_area(snapshot, REFRIGERATED_ZONE_CODES),
        "zone_plan": {"result": {"zones": _v20_compatible_rows(snapshot)}},
    }


def _assert_upstream_error(
    snapshot: dict[str, Any],
    expected_code: str,
    mutator: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    if mutator is not None:
        mutator(snapshot)
    with pytest.raises(FactoryPowerUpstreamAuthorityError) as exc:
        build_factory_power_upstream_authority(snapshot)
    assert exc.value.code == expected_code
    blocker = exc.value.to_blocker()
    assert blocker["success"] is False
    assert blocker["blocker"]["code"] == expected_code  # type: ignore[index]


def test_adapter_binds_the_exact_runtime_zone_plan_authorities() -> None:
    snapshot = _zone_plan_snapshot()
    authority = build_factory_power_upstream_authority(snapshot)

    assert authority.factory_area_m2 == _expected_area(snapshot, EXPECTED_FACTORY_ZONE_CODES)
    assert authority.cold_storage_area_m2 == _expected_area(snapshot, REFRIGERATED_ZONE_CODES)
    assert len(authority.zones) == 12
    assert tuple(zone["zone_code"] for zone in authority.zones) == EXPECTED_FACTORY_ZONE_CODES
    assert authority.zones == tuple(_rows(snapshot))


def test_adapter_requires_the_successful_canonical_zone_plan_identity() -> None:
    snapshot = _zone_plan_snapshot()
    _assert_upstream_error(
        {**snapshot, "success": False},
        "ZONE_PLAN_NOT_SUCCESSFUL",
    )
    _assert_upstream_error(
        {**snapshot, "calculator_name": "other_calculator"},
        "ZONE_PLAN_CALCULATOR_IDENTITY_MISMATCH",
    )
    _assert_upstream_error(
        {**snapshot, "calculator_version": "9.9.9"},
        "ZONE_PLAN_CALCULATOR_IDENTITY_MISMATCH",
    )
    _assert_upstream_error({}, "ZONE_PLAN_NOT_SUCCESSFUL")


@pytest.mark.parametrize(
    "value",
    [None, True, False, "abc", "NaN", "Infinity", "-Infinity", -1],
)
def test_invalid_zone_area_is_fail_closed(value: object) -> None:
    snapshot = _zone_plan_snapshot()
    _assert_upstream_error(
        snapshot,
        "INVALID_ZONE_REQUIRED_AREA",
        lambda payload: _row(payload, "raw_fruit_buffer").__setitem__("required_area_m2", value),
    )


def test_missing_zone_area_is_not_replaced_by_another_field() -> None:
    snapshot = _zone_plan_snapshot()

    def mutate(payload: dict[str, Any]) -> None:
        row = _row(payload, "raw_fruit_buffer")
        row.pop("required_area_m2")
        row["total_area_m2"] = 9999

    _assert_upstream_error(snapshot, "MISSING_ZONE_REQUIRED_AREA", mutate)


def test_duplicate_missing_and_unknown_zone_codes_fail_closed() -> None:
    duplicate = _zone_plan_snapshot()
    _rows(duplicate).append(deepcopy(_row(duplicate, "frozen_fruit_room")))
    _assert_upstream_error(duplicate, "DUPLICATE_ZONE_CODE")

    missing = _zone_plan_snapshot()
    _rows(missing)[:] = [row for row in _rows(missing) if row["zone_code"] != "frozen_fruit_room"]
    _assert_upstream_error(missing, "ZONE_AUTHORITY_SET_MISMATCH")

    unknown = _zone_plan_snapshot()
    unknown_row = deepcopy(_row(unknown, "office"))
    unknown_row["zone_code"] = "fake_factory_area"
    _rows(unknown).append(unknown_row)
    _assert_upstream_error(unknown, "ZONE_AUTHORITY_SET_MISMATCH")


@pytest.mark.parametrize("field_name", ["total_required_area_m2", "total_area_m2"])
def test_total_area_cross_check_is_fail_closed(field_name: str) -> None:
    snapshot = _zone_plan_snapshot()
    _result(snapshot)[field_name] = 9999
    _assert_upstream_error(snapshot, "FACTORY_AREA_TOTAL_MISMATCH")


def test_refrigerated_temperature_integrity_is_registry_bound() -> None:
    snapshot = _zone_plan_snapshot()
    _row(snapshot, "frozen_fruit_room")["temperature_band"] = "常温"
    _assert_upstream_error(snapshot, "REFRIGERATED_ZONE_TEMPERATURE_MISMATCH")


@pytest.mark.parametrize(
    "location",
    ["snapshot", "result"],
)
def test_refrigerated_area_substitute_is_forbidden(location: str) -> None:
    snapshot = _zone_plan_snapshot()
    target = snapshot if location == "snapshot" else _result(snapshot)
    target["refrigerated_area_m2"] = 9999
    _assert_upstream_error(
        snapshot,
        "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY",
    )


@pytest.mark.parametrize("field_name", ["factory_area_m2", "cold_storage_area_m2"])
def test_downstream_area_fields_cannot_be_supplied_by_zone_plan_snapshot(
    field_name: str,
) -> None:
    snapshot = _zone_plan_snapshot()
    snapshot[field_name] = 9999
    _assert_upstream_error(snapshot, "INVALID_ZONE_PLAN_AUTHORITY")


@pytest.mark.parametrize("location", ["snapshot", "result"])
@pytest.mark.parametrize("field_name", ["factory_area_m2", "cold_storage_area_m2"])
def test_downstream_area_fields_cannot_be_embedded_in_zone_plan_result(
    location: str,
    field_name: str,
) -> None:
    snapshot = _zone_plan_snapshot()
    target = snapshot if location == "snapshot" else _result(snapshot)
    target[field_name] = 9999
    _assert_upstream_error(snapshot, "INVALID_ZONE_PLAN_AUTHORITY")


def test_v20_calculator_receives_original_v19_authorities_without_fallbacks() -> None:
    snapshot = _zone_plan_snapshot()
    authority = build_factory_power_upstream_authority(snapshot)
    payload = authority.to_calculator_mapping()
    zone_rows = payload["zone_plan"]["result"]["zones"]  # type: ignore[index]
    assert isinstance(zone_rows, list)
    assert [row["zone_code"] for row in zone_rows] == list(EXPECTED_FACTORY_ZONE_CODES)
    assert _row(snapshot, "primary_precooling_room")["reporting_scheme_id"] == "6_position"
    assert zone_rows[2]["reporting_scheme_id"] == "6_position"
    assert zone_rows[2]["schemes"] == _row(snapshot, "primary_precooling_room")["schemes"]
    assert (
        zone_rows[2]["minimum_estimated_cooling_load_kw_r"]
        == _row(snapshot, "primary_precooling_room")["minimum_estimated_cooling_load_kw_r"]
    )
    assert "raw_position_count" in zone_rows[2]


def test_adapter_golden_parity_only_changes_area_authority() -> None:
    snapshot = _zone_plan_snapshot()
    manual = calculate_factory_power_estimation_from_mapping(_manual_v20_payload(snapshot))
    adapted = calculate_factory_power_from_zone_plan(snapshot)

    assert adapted.canonical_json() == manual.canonical_json()
    authority = build_factory_power_upstream_authority(snapshot)
    assert authority.factory_area_m2 == _manual_v20_payload(snapshot)["factory_area_m2"]
    assert authority.cold_storage_area_m2 == _manual_v20_payload(snapshot)["cold_storage_area_m2"]


def test_adapter_is_deterministic_for_repeated_canonical_zone_plan() -> None:
    snapshot = _zone_plan_snapshot()
    first = calculate_factory_power_from_zone_plan(snapshot)
    second = calculate_factory_power_from_zone_plan(deepcopy(snapshot))
    first_authority = build_factory_power_upstream_authority(snapshot)
    second_authority = build_factory_power_upstream_authority(deepcopy(snapshot))

    assert first_authority.factory_area_m2 == second_authority.factory_area_m2
    assert first_authority.cold_storage_area_m2 == second_authority.cold_storage_area_m2
    assert first.canonical_json() == second.canonical_json()


def test_missing_v19_minimum_load_is_left_for_v20_calculator_to_reject() -> None:
    snapshot = _zone_plan_snapshot()
    row = _row(snapshot, "raw_fruit_buffer")
    row.pop("minimum_estimated_cooling_load_kw_r")
    row["subtotal_load_kw_r"] = 999

    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_from_zone_plan(snapshot)
    assert exc.value.code == "MISSING_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R"


@pytest.mark.parametrize(
    "mutator, expected_code",
    [
        (
            lambda row: row.pop("reporting_scheme_id"),
            "MISSING_REPORTING_SCHEME_ID",
        ),
        (
            lambda row: row.__setitem__("reporting_scheme_id", "unknown"),
            "UNKNOWN_REPORTING_SCHEME_ID",
        ),
        (
            lambda row: row.__setitem__(
                "schemes",
                [
                    deepcopy(row["schemes"][0]),
                    deepcopy(row["schemes"][0]),
                ],
            ),
            "DUPLICATE_REPORTING_SCHEME_ID",
        ),
    ],
)
def test_precooling_authority_is_left_for_v20_calculator_to_reject(
    mutator: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    snapshot = _zone_plan_snapshot()
    mutator(_row(snapshot, "primary_precooling_room"))

    with pytest.raises(FactoryPowerEstimationError) as exc:
        calculate_factory_power_from_zone_plan(snapshot)
    assert exc.value.code == expected_code


def test_authority_uses_the_existing_runtime_registry_without_a_second_copy() -> None:
    assert (
        tuple(zone_code for zone_code, _zone_name, _temperature_band in REFRIGERATED_ZONE_REGISTRY)
        == REFRIGERATED_ZONE_CODES
    )
    snapshot = _zone_plan_snapshot()
    authority = build_factory_power_upstream_authority(snapshot)
    expected_cold_area = sum(
        (
            Decimal(str(_row(snapshot, zone_code)["required_area_m2"]))
            for zone_code, _zone_name, _temperature_band in REFRIGERATED_ZONE_REGISTRY
        ),
        Decimal("0"),
    ).quantize(AREA_QUANTUM, rounding=ROUND_HALF_UP)
    assert authority.cold_storage_area_m2 == expected_cold_area
