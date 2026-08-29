from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)
from cold_storage.modules.projects.application.operator_demo_defaults import (
    OPERATOR_DEMO_SOURCE,
    load_operator_demo_process_input,
    operator_demo_manifest_path,
)


def test_operator_demo_process_input_matches_v09_manifest() -> None:
    payload = load_operator_demo_process_input()
    assert payload["schema_id"] == "OperatorProcessInputV1"
    assert payload["schema_version"] == "1.1.0"
    assert payload["source"] == OPERATOR_DEMO_SOURCE
    assert payload["source_type"] == "demo"
    assert payload["validity_status"] == "unverified"
    assert payload["requires_review"] is True
    zone = payload["zone_planning_inputs"]
    assert zone["daily_inbound_mass_kg"]["value"] == "20000"
    assert zone["finished_storage_days"]["value"] == "7"
    assert zone["frozen_storage_days"]["value"] == "10"
    assert zone["main_packaging_storage_days"]["value"] == "4"
    assert zone["auxiliary_packaging_storage_days"]["value"] == "12"
    for field_name in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert field_name in zone
    assert operator_demo_manifest_path().as_posix().endswith(OPERATOR_DEMO_SOURCE)


def test_demo_operator_process_input_http_returns_v09_keys() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/demo/operator-process-input")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "demo"
    assert payload["requires_review"] is True
    assert payload["zone_planning_inputs"]["daily_inbound_mass_kg"]["value"] == "20000"
    assert payload["zone_planning_inputs"]["finished_storage_days"]["value"] == "7"
