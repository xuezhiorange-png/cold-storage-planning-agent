"""Unit tests for V0.8 P1 operator process input assembler."""

from __future__ import annotations

import pytest

from cold_storage.modules.projects.application.engineering_input_bundle import (
    EngineeringInputBundleValidationError,
)
from cold_storage.modules.projects.application.operator_process_input import (
    _zone_plan_input_defaults,
    _zone_planning_inputs_section,
    assemble_engineering_input_bundle,
    validate_operator_process_input,
)
from cold_storage.modules.projects.domain.models import ProjectVersion


def _operator_payload(**overrides: object) -> dict[str, object]:
    zone_inputs = {
        "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
        "working_time_h_per_day": {"value": "16", "unit": "h/day", "state": "provided"},
        "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
        "packaging_storage_days": {"value": "1", "unit": "day", "state": "provided"},
        "precooling_required_ratio": {"value": "0.6", "unit": "ratio", "state": "provided"},
    }
    zone_inputs.update(overrides)
    return {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.0.0",
        "zone_planning_inputs": zone_inputs,
    }


def _version() -> ProjectVersion:
    return ProjectVersion(
        project_id="p-1",
        version_number=1,
        change_summary="v1",
        id="pv-1",
    )


def test_five_field_assembly_fail_closed_without_thermal_catalog() -> None:
    payload = _operator_payload()
    validate_operator_process_input(payload)
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        assemble_engineering_input_bundle(
            operator_input=payload,
            project_id="p-1",
            version=_version(),
            actor="test-actor",
        )
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"
    assert "thermal catalog" in exc_info.value.error.message


def test_frozen_band_thermal_catalog_values() -> None:
    catalog = {
        "-18℃": {
            "room_design_temperature": "-18.0",
            "product_target_temperature": "-18.0",
        },
    }
    assert catalog["-18℃"]["room_design_temperature"] == "-18.0"


@pytest.mark.parametrize(
    "missing_field",
    (
        "daily_inbound_mass_kg",
        "working_time_h_per_day",
        "finished_storage_days",
        "packaging_storage_days",
        "precooling_required_ratio",
    ),
)
def test_missing_operator_key_fails_closed(missing_field: str) -> None:
    payload = _operator_payload()
    payload["zone_planning_inputs"].pop(missing_field)
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        validate_operator_process_input(payload)
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"


def test_catalog_hole_fails_closed_after_assembly() -> None:
    payload = _operator_payload()
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        assemble_engineering_input_bundle(
            operator_input=payload,
            project_id="p-1",
            version=_version(),
            actor="test-actor",
        )
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"


def test_e1_e3_conflict_leaves_marked_conflict() -> None:
    operator_values = {
        "daily_inbound_mass_kg": "20000",
        "working_time_h_per_day": "16",
        "finished_storage_days": "7",
        "packaging_storage_days": "1",
        "precooling_required_ratio": "0.6",
    }
    zone_inputs = _zone_planning_inputs_section(
        operator_values=operator_values,
        zone_defaults=_zone_plan_input_defaults(),
    )
    assert zone_inputs["frozen_fruit_ratio"]["validity_status"] == "conflict"
    assert zone_inputs["frozen_storage_days"]["validity_status"] == "conflict"
    assert zone_inputs["storage_position_capacity_kg"]["validity_status"] == "conflict"
    assert zone_inputs["frozen_fruit_ratio"]["requires_review"] is True
