"""Unit tests for EngineeringInputBundleV1 validation (V0.5 P1)."""

from __future__ import annotations

import copy

import pytest

from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.projects.application.engineering_input_bundle import (
    EngineeringInputBundleValidationError,
    assert_canonical_power_slot,
    validate_engineering_input_bundle,
)
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle


@pytest.mark.parametrize(
    "field_path",
    (
        "zone_planning_inputs.daily_inbound_mass_kg",
        "cooling_load_inputs.zones[0].zone_area",
        "cooling_load_inputs.zones[0].outdoor_design_temperature",
        "cooling_load_inputs.zones[0].product_entry_temperature",
        "equipment_inputs.systems[0].zones[0].evaporator_count",
        "equipment_inputs.condensing_temperature_c",
        "installed_power_inputs.compressor_input_power_kw_e",
        "investment_inputs.total_area_m2",
    ),
)
def test_missing_key_fields_fail_closed(field_path: str) -> None:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-1",
        project_version_id="pv-1",
        version_number=1,
    )
    if field_path == "zone_planning_inputs.daily_inbound_mass_kg":
        bundle["zone_planning_inputs"]["daily_inbound_mass_kg"]["state"] = "missing"
        bundle["zone_planning_inputs"]["daily_inbound_mass_kg"]["value"] = None
    elif field_path == "cooling_load_inputs.zones[0].zone_area":
        bundle["cooling_load_inputs"]["zones"][0].pop("zone_area")
    elif field_path == "cooling_load_inputs.zones[0].outdoor_design_temperature":
        bundle["cooling_load_inputs"]["zones"][0].pop("outdoor_design_temperature")
    elif field_path == "cooling_load_inputs.zones[0].product_entry_temperature":
        bundle["cooling_load_inputs"]["zones"][0].pop("product_entry_temperature")
    elif field_path == "equipment_inputs.systems[0].zones[0].evaporator_count":
        bundle["equipment_inputs"]["systems"][0]["zones"][0].pop("evaporator_count")
    elif field_path == "equipment_inputs.condensing_temperature_c":
        bundle["equipment_inputs"].pop("condensing_temperature_c")
    elif field_path == "installed_power_inputs.compressor_input_power_kw_e":
        bundle["installed_power_inputs"].pop("compressor_input_power_kw_e")
    elif field_path == "investment_inputs.total_area_m2":
        bundle["investment_inputs"].pop("total_area_m2")

    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        validate_engineering_input_bundle(bundle)
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"
    error_path = exc_info.value.error.field_path
    assert field_path.split("[")[0] in error_path or field_path in error_path


def test_missing_numeric_unit_fails_closed() -> None:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-1",
        project_version_id="pv-1",
        version_number=1,
    )
    bundle["cooling_load_inputs"]["zones"][0]["zone_area"]["unit"] = None
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        validate_engineering_input_bundle(bundle)
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"
    assert exc_info.value.error.field_path.endswith("zone_area.unit")


def test_unknown_schema_version_fails_closed() -> None:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-1",
        project_version_id="pv-1",
        version_number=1,
    )
    bundle["schema_version"] = "9.9.9"
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        validate_engineering_input_bundle(bundle)
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"


def test_power_configuration_cannot_satisfy_canonical_power() -> None:
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        assert_canonical_power_slot("power_configuration")
    assert exc_info.value.error.code == "INVALID_CANONICAL_POWER_SLOT"


def test_installed_power_is_canonical_power_slot() -> None:
    assert_canonical_power_slot(CALCULATOR_BINDINGS["power"])


def test_valid_bundle_passes_validation() -> None:
    bundle = build_valid_engineering_input_bundle(
        project_id="p-1",
        project_version_id="pv-1",
        version_number=1,
    )
    validate_engineering_input_bundle(copy.deepcopy(bundle))
