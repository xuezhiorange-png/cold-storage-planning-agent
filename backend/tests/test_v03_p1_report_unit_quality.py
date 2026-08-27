"""V0.3 P1 report unit-dimension and fail-closed quality regressions."""

from __future__ import annotations

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.reports.domain.quality import evaluate_quality, get_blockers

_SOURCE_REFERENCE = "V1演示规划系数，未作为国家标准或企业正式标准"
_AREA_BASIS_CODE_UNITS = {
    "office_area_per_t_day": "m2/(t/day)",
    "changing_area_per_t_day": "m2/(t/day)",
    "raw_area_loading": "kg/m2",
    "coating_area_loading": "kg/day/m2",
    "storage_area_loading": "kg/m2",
    "secondary_fruit_area_loading": "kg/m2",
    "frozen_area_loading": "kg/m2",
}


def _codes(content: dict[str, object]) -> list[str]:
    return [finding["code"] for finding in evaluate_quality(content, [])]


def _area_content(area_basis: object) -> dict[str, object]:
    return {"throughput_inventory_area": {"zone_details": [{"area_basis": area_basis}]}}


def _coefficient_reference(
    code: str = "raw_area_loading",
    unit: str | None = None,
) -> dict[str, object]:
    return {
        "code": code,
        "name": f"{code} reference",
        "value": 240,
        "unit": unit if unit is not None else _AREA_BASIS_CODE_UNITS.get(code, "kg/m2"),
        "category": "cold_room_zone_planning",
        "source_type": "demo",
        "source_reference": _SOURCE_REFERENCE,
        "version": "demo-1",
        "validity_status": "unverified",
        "approval_status": "unverified",
        "requires_review": True,
        "notes": "coefficient reference",
    }


@pytest.mark.parametrize("code, unit", sorted(_AREA_BASIS_CODE_UNITS.items()))
def test_all_current_area_basis_coefficient_pairs_are_accepted(
    code: str,
    unit: str,
) -> None:
    findings = evaluate_quality(_area_content(_coefficient_reference(code, unit)), [])

    assert not get_blockers(findings)


def test_unknown_coefficient_code_is_blocked() -> None:
    codes = _codes(_area_content(_coefficient_reference("unknown_area_loading", "kg/m2")))

    assert "UNKNOWN_AREA_BASIS_COEFFICIENT_CODE" in codes


def test_known_coefficient_code_with_wrong_unit_is_blocked() -> None:
    codes = _codes(_area_content(_coefficient_reference("raw_area_loading", "m2")))

    assert "INVALID_AREA_BASIS_COEFFICIENT_UNIT" in codes


def test_missing_required_provenance_key_is_blocked() -> None:
    reference = _coefficient_reference()
    reference.pop("source_reference")

    assert "INVALID_AREA_BASIS_COEFFICIENT_KEYS" in _codes(_area_content(reference))


def test_extra_coefficient_reference_key_is_blocked() -> None:
    reference = _coefficient_reference()
    reference["extra"] = "not-authorized"

    assert "INVALID_AREA_BASIS_COEFFICIENT_KEYS" in _codes(_area_content(reference))


def test_wrong_static_provenance_identity_is_blocked() -> None:
    reference = _coefficient_reference()
    reference["source_reference"] = "wrong source"

    assert "INVALID_AREA_BASIS_COEFFICIENT_PROVENANCE" in _codes(_area_content(reference))


def test_partial_provenance_does_not_fall_back_to_measured_value() -> None:
    partial_reference = {"code": "raw_area_loading", "value": 240, "unit": "m2"}
    codes = _codes(_area_content(partial_reference))

    assert "INVALID_AREA_BASIS_COEFFICIENT_KEYS" in codes
    assert "WRONG_UNIT_DIMENSION" not in codes
    assert "UNMAPPED_MEASURED_VALUE_UNIT" not in codes


def test_plain_area_measurement_m2_is_accepted() -> None:
    findings = evaluate_quality(_area_content({"value": 200, "unit": "m2"}), [])

    assert not get_blockers(findings)


def test_plain_area_measurement_non_m2_is_blocked() -> None:
    codes = _codes(_area_content({"value": 200, "unit": "kg/m2"}))

    assert "WRONG_UNIT_DIMENSION" in codes


def test_declared_but_unreachable_coefficient_code_is_blocked() -> None:
    reference = _coefficient_reference("primary_precooling_area_loading", "kg/day/m2")

    assert "UNKNOWN_AREA_BASIS_COEFFICIENT_CODE" in _codes(_area_content(reference))


def test_unmapped_generic_measured_value_with_known_unit_remains_blocked() -> None:
    content = {
        "unknown_section": {
            "unmapped_area": {"value": 200, "unit": "m2"},
            "unmapped_power": {"value": 20, "unit": "kW(e)"},
        }
    }

    codes = _codes(content)
    assert codes.count("UNMAPPED_MEASURED_VALUE_UNIT") == 2


def test_known_refrigeration_electrical_thermal_energy_dimensions_remain_strict() -> None:
    content = {
        "engineering": {
            "cooling_load": {"value": 1, "unit": "kW(e)"},
            "total_compressor_input_power": {"value": 1, "unit": "kW(r)"},
            "condenser_heat_rejection": {"value": 1, "unit": "kW(e)"},
            "daily_energy": {"value": 1, "unit": "kWh"},
        }
    }

    findings = evaluate_quality(content, [])
    codes = [finding["code"] for finding in findings]
    assert codes.count("WRONG_UNIT_DIMENSION") == 3
    assert "daily_energy.unit" not in [
        finding["field_path"] for finding in findings if finding["code"] == "WRONG_UNIT_DIMENSION"
    ]


@pytest.mark.parametrize("invalid_value", [True, float("nan"), float("inf"), "240"])
def test_coefficient_value_must_be_finite_numeric(invalid_value: object) -> None:
    reference = _coefficient_reference()
    reference["value"] = invalid_value

    assert "INVALID_AREA_BASIS_COEFFICIENT_VALUE" in _codes(_area_content(reference))


def test_real_production_zone_details_references_pass_quality() -> None:
    result = ColdRoomZonePlanner().plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=1000,
            working_time_h_per_day=8,
            finished_storage_days=2,
            packaging_storage_days=3,
            precooling_required_ratio=0.1,
        )
    )

    assert result.success is True
    zones = result.result["zones"]
    assert isinstance(zones, list)
  # V0.9 P2 §4 recut: formula-native zones no longer carry unused demo loading as area_basis.
    zone_details = [zone for zone in zones if isinstance(zone, dict) and "area_basis" in zone]
    assert zone_details == []

    findings = evaluate_quality({"throughput_inventory_area": {"zone_details": zones}}, [])

    assert not get_blockers(findings)
