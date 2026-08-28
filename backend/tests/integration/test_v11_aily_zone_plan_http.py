"""HTTP tests for the Aily zone-plan connector on unmodified create_app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app


def test_aily_zone_plan_http_returns_markdown_table() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/aily/v1/zone-plan",
        json={
            "daily_inbound_mass_kg": 20000,
            "finished_storage_days": 7,
            "frozen_storage_days": 10,
            "main_packaging_storage_days": 4,
            "auxiliary_packaging_storage_days": 12,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["calculator_name"] == "cold_room_zone_plan"
    assert body["calculator_version"] == "1.0.0"
    assert body["table"]["rows"]
    assert "面积" in body["markdown_table"]


def test_aily_zone_plan_http_fail_closed_on_missing_key() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/aily/v1/zone-plan",
        json={
            "daily_inbound_mass_kg": 20000,
            "finished_storage_days": 7,
            "main_packaging_storage_days": 4,
            "auxiliary_packaging_storage_days": 12,
        },
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert "frozen_storage_days" in error["missing_keys"]
    assert error["ask_operator"]


def test_aily_zone_plan_http_does_not_parse_chat_utterance() -> None:
    """Spoken plant-size examples belong to 豆包, not this connector."""
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/aily/v1/zone-plan",
        json={"message": "要建一个20吨的加工厂"},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "MISSING_ENGINEERING_PARAMETER"
    assert len(error["missing_keys"]) == 5
