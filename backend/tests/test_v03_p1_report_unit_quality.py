"""V0.3 P1 report unit-dimension and fail-closed quality regressions."""

from __future__ import annotations

import pytest

from cold_storage.modules.reports.domain.quality import evaluate_quality, get_blockers


def _codes(content: dict[str, object]) -> list[str]:
    return [finding["code"] for finding in evaluate_quality(content, [])]


def _coefficient_reference(unit: str = "kg/m2") -> dict[str, object]:
    return {
        "code": "raw_area_loading",
        "name": "raw area loading",
        "value": 240,
        "unit": unit,
        "category": "cold_room_zone_planning",
        "source_type": "demo",
        "source_reference": "accepted source definition",
        "version": "demo-1",
        "validity_status": "unverified",
        "approval_status": "unverified",
        "requires_review": True,
        "notes": "coefficient reference",
    }


def test_area_basis_coefficient_reference_is_not_treated_as_measurement() -> None:
    content = {
        "throughput_inventory_area": {"zone_details": [{"area_basis": _coefficient_reference()}]}
    }

    assert "INVALID_UNIT" not in _codes(content)
    assert "WRONG_UNIT_DIMENSION" not in _codes(content)


def test_canonical_area_basis_measurement_requires_m2() -> None:
    valid = {
        "throughput_inventory_area": {
            "zone_details": [{"area_basis": {"value": 200, "unit": "m2"}}]
        }
    }
    invalid = {
        "throughput_inventory_area": {
            "zone_details": [{"area_basis": {"value": 200, "unit": "kg/m2"}}]
        }
    }

    assert not get_blockers(evaluate_quality(valid, []))
    assert "WRONG_UNIT_DIMENSION" in _codes(invalid)


def test_known_power_and_energy_dimensions_remain_strict() -> None:
    content = {
        "equipment_selection": {"total_compressor_capacity": {"value": 120, "unit": "kW(e)"}},
        "electrical_and_energy": {"daily_energy": {"value": 120, "unit": "kWh"}},
    }

    assert "WRONG_UNIT_DIMENSION" in _codes(content)
    assert "INVALID_UNIT" not in _codes(
        {"electrical_and_energy": {"daily_energy": {"value": 120, "unit": "kWh"}}}
    )


@pytest.mark.parametrize(
    ("field_path", "wrong_unit"),
    [
        ("cooling_load", "kW(e)"),
        ("total_compressor_input_power", "kW(r)"),
        ("condenser_heat_rejection", "kW(e)"),
    ],
)
def test_refrigeration_electrical_and_thermal_dimensions_remain_strict(
    field_path: str,
    wrong_unit: str,
) -> None:
    content = {"engineering": {field_path: {"value": 1, "unit": wrong_unit}}}

    assert "WRONG_UNIT_DIMENSION" in _codes(content)


def test_unmapped_known_measured_units_fail_closed() -> None:
    content = {
        "unknown_section": {
            "unmapped_area": {"value": 200, "unit": "m2"},
            "unmapped_power": {"value": 20, "unit": "kW(e)"},
        }
    }

    codes = _codes(content)
    assert codes.count("UNMAPPED_MEASURED_VALUE_UNIT") == 2


def test_real_recommendation_content_can_pass_without_quality_blockers() -> None:
    content = {
        "scheme_comparison": {
            "recommended_scheme_code": "balanced",
            "candidates": [{"scheme_code": "balanced", "feasible": True}],
        },
        "throughput_inventory_area": {
            "zone_details": [{"area_basis": {"value": 200, "unit": "m2"}}]
        },
    }

    findings = evaluate_quality(content, [])
    assert not get_blockers(findings)
    assert content["scheme_comparison"]["recommended_scheme_code"] == "balanced"
