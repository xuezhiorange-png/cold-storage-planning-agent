"""Unit tests for the V1.9 P1 per-zone minimum cooling estimator."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from cold_storage.modules.calculations.domain import zone_planning as zone_planning_module
from cold_storage.modules.calculations.domain.per_zone_cooling_estimation import (
    AUTHORITY_SOURCE,
    EXPECTED_REFRIGERATED_ZONE_CODES,
    MINIMUM_OUTPUT_FIELD,
    PER_ZONE_COOLING_ESTIMATION_RULES,
    PROVENANCE_FIELD,
    PerZoneCoolingEstimationError,
    apply_per_zone_cooling_estimation,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)


def _complete_zone_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {"zone_code": "office", "temperature_band": "常温", "required_area_m2": 80},
        {"zone_code": "changing_room", "temperature_band": "常温", "required_area_m2": 40},
        {
            "zone_code": "primary_precooling_room",
            "temperature_band": "8~10℃",
            "position_count": 6,
            "raw_position_count": 99,
            "n_need": 88,
        },
        {
            "zone_code": "secondary_precooling_room",
            "temperature_band": "1~3℃",
            "position_count": 5,
            "raw_position_count": 77,
            "n_need": 66,
        },
        {
            "zone_code": "raw_fruit_buffer",
            "temperature_band": "8~10℃",
            "required_area_m2": 142.68,
        },
        {
            "zone_code": "sorting_packaging_room",
            "temperature_band": "8~10℃",
            "required_area_m2": 100,
        },
        {"zone_code": "coating_room", "temperature_band": "1~3℃", "required_area_m2": 50},
        {
            "zone_code": "finished_goods_room",
            "temperature_band": "1~3℃",
            "required_area_m2": 200,
        },
        {
            "zone_code": "secondary_fruit_buffer",
            "temperature_band": "8~10℃",
            "required_area_m2": 80,
        },
        {"zone_code": "frozen_fruit_room", "temperature_band": "-18℃", "required_area_m2": 60},
        {
            "zone_code": "packaging_material_storage",
            "temperature_band": "常温",
            "required_area_m2": 30,
        },
        {"zone_code": "shipping_channel", "temperature_band": "1~3℃", "required_area_m2": 25},
    ]
    return rows


def _planner_input() -> ColdRoomZonePlanInput:
    return ColdRoomZonePlanInput(
        daily_inbound_mass_kg=25_000,
        working_time_h_per_day=16,
        finished_storage_days=2.5,
        packaging_storage_days=3,
        precooling_required_ratio=1,
    )


def _zone_by_code(rows: list[dict[str, Any]], code: str) -> dict[str, Any]:
    return next(row for row in rows if row.get("zone_code") == code)


def test_runtime_registry_has_exactly_nine_authoritative_rules() -> None:
    assert set(PER_ZONE_COOLING_ESTIMATION_RULES) == EXPECTED_REFRIGERATED_ZONE_CODES
    assert len(PER_ZONE_COOLING_ESTIMATION_RULES) == 9
    assert all(
        rule.authority_source == AUTHORITY_SOURCE
        for rule in PER_ZONE_COOLING_ESTIMATION_RULES.values()
    )
    assert all(rule.requires_review is True for rule in PER_ZONE_COOLING_ESTIMATION_RULES.values())


def test_estimator_adds_all_frozen_minimums_and_provenance() -> None:
    enriched = apply_per_zone_cooling_estimation(_complete_zone_rows())

    expected = {
        "primary_precooling_room": Decimal("120"),
        "secondary_precooling_room": Decimal("75"),
        "raw_fruit_buffer": Decimal("57.072"),
        "sorting_packaging_room": Decimal("30"),
        "coating_room": Decimal("15"),
        "finished_goods_room": Decimal("60"),
        "secondary_fruit_buffer": Decimal("32"),
        "frozen_fruit_room": Decimal("33"),
        "shipping_channel": Decimal("7.50"),
    }
    for code, expected_minimum in expected.items():
        row = _zone_by_code(enriched, code)
        assert Decimal(str(row[MINIMUM_OUTPUT_FIELD])) == expected_minimum
        provenance = row[PROVENANCE_FIELD]
        assert provenance["authority_source"] == AUTHORITY_SOURCE
        assert provenance["requires_review"] is True
        assert provenance["reference_factor"] == int(
            PER_ZONE_COOLING_ESTIMATION_RULES[code].reference_factor or 0
        )
        assert provenance["reference_factor_unit"] == (
            PER_ZONE_COOLING_ESTIMATION_RULES[code].reference_factor_unit
        )


def test_precooling_uses_final_position_count_not_raw_or_scheme_fields() -> None:
    enriched = apply_per_zone_cooling_estimation(_complete_zone_rows())

    primary = _zone_by_code(enriched, "primary_precooling_room")
    secondary = _zone_by_code(enriched, "secondary_precooling_room")
    assert primary[MINIMUM_OUTPUT_FIELD] == 120
    assert secondary[MINIMUM_OUTPUT_FIELD] == 75
    assert primary[PROVENANCE_FIELD]["source_field"] == "position_count"
    assert secondary[PROVENANCE_FIELD]["source_field"] == "position_count"
    assert primary[PROVENANCE_FIELD]["source_value"] == 6
    assert secondary[PROVENANCE_FIELD]["source_value"] == 5


def test_ambient_zones_are_left_unchanged() -> None:
    rows = _complete_zone_rows()
    before = {row["zone_code"]: dict(row) for row in rows if row["temperature_band"] == "常温"}

    enriched = apply_per_zone_cooling_estimation(rows)

    for code, original in before.items():
        actual = _zone_by_code(enriched, code)
        assert actual == original
        assert MINIMUM_OUTPUT_FIELD not in actual
        assert PROVENANCE_FIELD not in actual


@pytest.mark.parametrize(
    ("zone_code", "field_name"),
    [
        ("primary_precooling_room", "position_count"),
        ("raw_fruit_buffer", "required_area_m2"),
    ],
)
def test_missing_canonical_source_fails_closed(zone_code: str, field_name: str) -> None:
    rows = _complete_zone_rows()
    _zone_by_code(rows, zone_code).pop(field_name)

    with pytest.raises(PerZoneCoolingEstimationError) as exc:
        apply_per_zone_cooling_estimation(rows)

    assert exc.value.code == "MISSING_SOURCE_VALUE"
    assert exc.value.details["zone_code"] == zone_code
    assert exc.value.details["source_field"] == field_name


@pytest.mark.parametrize("bad_value", ["not-a-number", -1, float("nan"), float("inf")])
def test_invalid_source_value_fails_closed(bad_value: object) -> None:
    rows = _complete_zone_rows()
    _zone_by_code(rows, "raw_fruit_buffer")["required_area_m2"] = bad_value

    with pytest.raises(PerZoneCoolingEstimationError) as exc:
        apply_per_zone_cooling_estimation(rows)

    assert exc.value.code in {
        "NON_NUMERIC_SOURCE_VALUE",
        "NON_FINITE_SOURCE_VALUE",
        "NEGATIVE_SOURCE_VALUE",
    }


def test_unknown_refrigerated_zone_fails_closed() -> None:
    rows = _complete_zone_rows()
    rows.append(
        {
            "zone_code": "unknown_refrigerated_zone",
            "temperature_band": "1~3℃",
            "required_area_m2": 10,
        }
    )

    with pytest.raises(PerZoneCoolingEstimationError) as exc:
        apply_per_zone_cooling_estimation(rows)

    assert exc.value.code == "UNMAPPED_REFRIGERATED_ZONE"


def test_missing_and_duplicate_refrigerated_zone_codes_fail_closed() -> None:
    missing_rows = [row for row in _complete_zone_rows() if row["zone_code"] != "shipping_channel"]
    with pytest.raises(PerZoneCoolingEstimationError) as missing_exc:
        apply_per_zone_cooling_estimation(missing_rows)
    assert missing_exc.value.code == "MISSING_REFRIGERATED_ZONE"
    assert missing_exc.value.details["missing_zone_codes"] == ["shipping_channel"]

    duplicate_rows = _complete_zone_rows() + [
        dict(_zone_by_code(_complete_zone_rows(), "frozen_fruit_room"))
    ]
    with pytest.raises(PerZoneCoolingEstimationError) as duplicate_exc:
        apply_per_zone_cooling_estimation(duplicate_rows)
    assert duplicate_exc.value.code == "DUPLICATE_REFRIGERATED_ZONE"


def test_missing_zone_code_fails_closed() -> None:
    rows = _complete_zone_rows()
    rows[0].pop("zone_code")

    with pytest.raises(PerZoneCoolingEstimationError) as exc:
        apply_per_zone_cooling_estimation(rows)

    assert exc.value.code == "MISSING_ZONE_CODE"


def test_missing_reference_factor_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from cold_storage.modules.calculations.domain import per_zone_cooling_estimation as estimator

    broken_rule = replace(
        PER_ZONE_COOLING_ESTIMATION_RULES["raw_fruit_buffer"], reference_factor=None
    )
    broken_registry = dict(PER_ZONE_COOLING_ESTIMATION_RULES)
    broken_registry["raw_fruit_buffer"] = broken_rule
    monkeypatch.setattr(estimator, "PER_ZONE_COOLING_ESTIMATION_RULES", broken_registry)

    with pytest.raises(PerZoneCoolingEstimationError) as exc:
        apply_per_zone_cooling_estimation(_complete_zone_rows())

    assert exc.value.code == "MISSING_REFERENCE_FACTOR"


def test_zone_planner_enrichment_is_additive(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_planner = ColdRoomZonePlanner()
    monkeypatch.setattr(
        zone_planning_module,
        "apply_per_zone_cooling_estimation",
        lambda zones: [dict(zone) for zone in zones],
    )
    baseline = baseline_planner.plan(_planner_input())

    monkeypatch.undo()
    enriched = ColdRoomZonePlanner().plan(_planner_input())

    p1_fields = {MINIMUM_OUTPUT_FIELD, PROVENANCE_FIELD}
    baseline_zones = baseline.result["zones"]
    enriched_zones = enriched.result["zones"]
    assert len(baseline_zones) == len(enriched_zones)
    for before, after in zip(baseline_zones, enriched_zones, strict=True):
        assert {key: value for key, value in after.items() if key not in p1_fields} == before
    for field_name in (
        "total_required_area_m2",
        "total_area_m2",
        "total_area_m2_8_position_scheme",
    ):
        assert enriched.result[field_name] == baseline.result[field_name]


def test_zone_planner_returns_structured_error_for_estimation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_zones: object) -> list[dict[str, object]]:
        raise PerZoneCoolingEstimationError(
            "MISSING_SOURCE_VALUE",
            "position_count is required",
            {"zone_code": "primary_precooling_room"},
        )

    monkeypatch.setattr(zone_planning_module, "apply_per_zone_cooling_estimation", fail)
    result = ColdRoomZonePlanner().plan(_planner_input())

    assert result.success is False
    assert result.errors[0].code == "MISSING_SOURCE_VALUE"
    assert result.errors[0].details == {"zone_code": "primary_precooling_room"}
