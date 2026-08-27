"""Unit tests for V0.9 P1 operator process input assembler (dual-path)."""

from __future__ import annotations

import pytest

from cold_storage.modules.projects.application.engineering_input_bundle import (
    LINEAGE_PENDING_STATE,
    EngineeringInputBundleValidationError,
    project_execution_snapshot_from_bundle,
    validate_engineering_input_bundle,
)
from cold_storage.modules.projects.application.operator_process_input import (
    assemble_engineering_input_bundle,
    detect_operator_process_path,
    validate_operator_process_input,
)
from cold_storage.modules.projects.domain.models import ProjectVersion


def _v09_operator_payload(**overrides: object) -> dict[str, object]:
    zone_inputs = {
        "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
        "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
        "frozen_storage_days": {"value": "10", "unit": "day", "state": "provided"},
        "main_packaging_storage_days": {"value": "4", "unit": "day", "state": "provided"},
        "auxiliary_packaging_storage_days": {"value": "12", "unit": "day", "state": "provided"},
    }
    zone_inputs.update(overrides)
    return {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.1.0",
        "zone_planning_inputs": zone_inputs,
    }


def _v08_operator_payload() -> dict[str, object]:
    return {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.0.0",
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
            "working_time_h_per_day": {"value": "16", "unit": "h/day", "state": "provided"},
            "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
            "packaging_storage_days": {"value": "1", "unit": "day", "state": "provided"},
            "precooling_required_ratio": {"value": "0.6", "unit": "ratio", "state": "provided"},
        },
    }


def _version() -> ProjectVersion:
    return ProjectVersion(
        project_id="p-1",
        version_number=1,
        change_summary="v1",
        id="pv-1",
    )


def _assemble(payload: dict[str, object]) -> dict[str, object]:
    return assemble_engineering_input_bundle(
        operator_input=payload,
        project_id="p-1",
        version=_version(),
        actor="test-actor",
    )


def test_v09_five_key_assembly_succeeds() -> None:
    payload = _v09_operator_payload()
    assert detect_operator_process_path(payload) == "v09"
    validate_operator_process_input(payload)
    bundle = _assemble(payload)
    validate_engineering_input_bundle(bundle, validation_mode="operator_minimal")
    assert bundle["schema_id"] == "EngineeringInputBundleV1"
    zone = bundle["zone_planning_inputs"]
    assert zone["daily_inbound_mass_kg"]["source_type"] == "user"
    assert zone["frozen_storage_days"]["value"] in {"10", "10.0"}
    assert zone["frozen_storage_days"]["source_type"] == "user"
    assert zone["frozen_storage_days"]["validity_status"] != "conflict"
    assert zone["main_packaging_storage_days"]["value"] in {"4", "4.0"}
    assert zone["main_packaging_storage_days"]["source_type"] == "user"
    assert zone["auxiliary_packaging_storage_days"]["value"] in {"12", "12.0"}
    assert zone["auxiliary_packaging_storage_days"]["source_type"] == "user"
    assert len(bundle["cooling_load_inputs"]["zones"]) == 9
    zone_codes = [
        z["_assembler_expected_zone_code"] for z in bundle["cooling_load_inputs"]["zones"]
    ]
    assert "shipping_channel" in zone_codes
    assert bundle["cooling_load_inputs"]["zones"][0]["zone_area"]["state"] == LINEAGE_PENDING_STATE


def test_v09_precooling_ratio_is_catalog_one() -> None:
    bundle = _assemble(_v09_operator_payload())
    ratio = bundle["zone_planning_inputs"]["precooling_required_ratio"]
    assert ratio["value"] in {"1", "1.0"}
    assert ratio["source_type"] == "demo"
    assert ratio["validity_status"] == "unverified"
    assert ratio["requires_review"] is True


def test_v09_working_time_is_catalog_not_operator() -> None:
    bundle = _assemble(_v09_operator_payload())
    working = bundle["zone_planning_inputs"]["working_time_h_per_day"]
    assert working["value"] in {"16", "16.0"}
    assert working["source_type"] == "demo"
    assert working["requires_review"] is True
    hours = bundle["cooling_load_inputs"]["zones"][0]["operating_hours_per_day"]
    assert hours["value"] in {"16", "16.0"}
    assert hours["source_type"] == "demo"


def test_v09_packaging_storage_days_derived_from_main() -> None:
    bundle = _assemble(_v09_operator_payload())
    derived = bundle["zone_planning_inputs"]["packaging_storage_days"]
    main = bundle["zone_planning_inputs"]["main_packaging_storage_days"]
    assert derived["value"] == main["value"]
    assert derived["source_path"] == "zone_planning_inputs.main_packaging_storage_days"


def test_v09_extended_keys_land_on_zone_snapshot() -> None:
    bundle = _assemble(_v09_operator_payload())
    snapshot = project_execution_snapshot_from_bundle(bundle)
    zone = snapshot["zone"]
    assert zone["frozen_storage_days"] in {"10", "10.0"}
    assert zone["main_packaging_storage_days"] in {"4", "4.0"}
    assert zone["auxiliary_packaging_storage_days"] in {"12", "12.0"}


@pytest.mark.parametrize(
    "missing_field",
    (
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    ),
)
def test_v09_missing_operator_key_fails_closed(missing_field: str) -> None:
    payload = _v09_operator_payload()
    payload["zone_planning_inputs"].pop(missing_field)
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        validate_operator_process_input(payload)
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"


def test_v09_does_not_accept_operator_precooling_ratio() -> None:
    payload = _v09_operator_payload(
        precooling_required_ratio={"value": "0.6", "unit": "ratio", "state": "provided"}
    )
    with pytest.raises(EngineeringInputBundleValidationError) as exc_info:
        validate_operator_process_input(payload)
    assert exc_info.value.error.code == "MISSING_ENGINEERING_PARAMETER"
    assert "precooling_required_ratio" in exc_info.value.error.field_path


def test_v08_five_key_still_assembles() -> None:
    payload = _v08_operator_payload()
    assert detect_operator_process_path(payload) == "v08"
    bundle = _assemble(payload)
    validate_engineering_input_bundle(bundle, validation_mode="operator_minimal")
    zone = bundle["zone_planning_inputs"]
    assert zone["working_time_h_per_day"]["source_type"] == "user"
    assert zone["working_time_h_per_day"]["value"] in {"16", "16.0"}
    assert zone["precooling_required_ratio"]["value"] in {"0.6", "0.60"}
    assert zone["precooling_required_ratio"]["source_type"] == "user"
    assert zone["packaging_storage_days"]["value"] in {"1", "1.0"}
    assert zone["frozen_storage_days"]["validity_status"] == "conflict"
    hours = bundle["cooling_load_inputs"]["zones"][0]["operating_hours_per_day"]
    assert hours["source_type"] == "user"


def test_v08_omitted_schema_version_still_assembles() -> None:
    payload = _v08_operator_payload()
    payload.pop("schema_version")
    assert detect_operator_process_path(payload) == "v08"
    bundle = _assemble(payload)
    validate_engineering_input_bundle(bundle, validation_mode="operator_minimal")
    assert bundle["zone_planning_inputs"]["precooling_required_ratio"]["source_type"] == "user"
