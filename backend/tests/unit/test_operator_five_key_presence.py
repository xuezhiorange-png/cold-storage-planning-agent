from cold_storage.modules.projects.application.operator_five_key_presence import (
    missing_v09_five_key_fields,
    v09_five_keys_are_present,
)

_V09_SNAPSHOT = {
    "schema_id": "OperatorProcessInputV1",
    "schema_version": "1.1.0",
    "zone_planning_inputs": {
        "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
        "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
        "frozen_storage_days": {"value": "10", "unit": "day", "state": "provided"},
        "main_packaging_storage_days": {"value": "4", "unit": "day", "state": "provided"},
        "auxiliary_packaging_storage_days": {"value": "12", "unit": "day", "state": "provided"},
    },
}


def test_v04_flat_snapshot_is_not_v09_authority() -> None:
    inputs = {
        "daily_inbound_mass_kg": 25000,
        "working_time_h_per_day": 16,
        "utilization_factor": 0.85,
        "finished_storage_days": 2.5,
        "packaging_storage_days": 3,
        "reserve_factor": 1.05,
    }
    assert v09_five_keys_are_present(inputs=inputs) is False
    assert missing_v09_five_key_fields(inputs) == [
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    ]


def test_v09_operator_snapshot_is_authority() -> None:
    assert v09_five_keys_are_present(inputs=_V09_SNAPSHOT) is True
    assert missing_v09_five_key_fields(_V09_SNAPSHOT) == []


def test_v08_operator_snapshot_is_not_v09_authority() -> None:
    inputs = {
        "schema_id": "OperatorProcessInputV1",
        "schema_version": "1.0.0",
        "zone_planning_inputs": {
            "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
            "working_time_h_per_day": {"value": "16", "unit": "h/day", "state": "provided"},
            "finished_storage_days": {"value": "2.5", "unit": "day", "state": "provided"},
            "packaging_storage_days": {"value": "3", "unit": "day", "state": "provided"},
            "precooling_required_ratio": {"value": "1", "unit": "ratio", "state": "provided"},
        },
    }
    assert v09_five_keys_are_present(inputs=inputs) is False


def test_zone_calculation_flat_input_is_authority() -> None:
    calc_by_name = {
        "cold_room_zone_plan": {
            "input_snapshot": {
                "daily_inbound_mass_kg": "20000",
                "finished_storage_days": "7",
                "frozen_storage_days": "10",
                "main_packaging_storage_days": "4",
                "auxiliary_packaging_storage_days": "12",
            }
        }
    }
    assert v09_five_keys_are_present(inputs={}, calc_by_name=calc_by_name) is True
