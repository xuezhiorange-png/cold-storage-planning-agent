"""HTTP tests for V1.2 Aily concept-preview connector."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app

_FIVE_KEYS = {
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12,
}
_CONNECTOR_SECRET = "connector-test-secret-v12-concept"


def test_aily_concept_preview_http_returns_five_stages() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/aily/v1/concept-preview", json=_FIVE_KEYS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply_kind"] == "concept_preview"
    assert body["persisted"] is False
    assert body["floor_area_from_zone_plan"] is True
    assert body["envelope_wall_roof_from_plan"] is False
    assert "zone" in body["stages"]
    assert "cooling_load" in body["stages"]
    assert "investment" in body["stages"]
    assert "演示" in body["stages"]["cooling_load"]["markdown_table"]


def test_aily_concept_preview_http_unauthorized_without_header_when_secret_set(
    monkeypatch,
) -> None:
    monkeypatch.setenv("COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET", _CONNECTOR_SECRET)
    client = TestClient(create_app())
    response = client.post("/api/v1/aily/v1/concept-preview", json=_FIVE_KEYS)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AILY_CONNECTOR_UNAUTHORIZED"


def test_aily_concept_preview_http_authorized_with_correct_header_when_secret_set(
    monkeypatch,
) -> None:
    monkeypatch.setenv("COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET", _CONNECTOR_SECRET)
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/aily/v1/concept-preview",
        json=_FIVE_KEYS,
        headers={"X-Aily-Connector-Key": _CONNECTOR_SECRET},
    )
    assert response.status_code == 200, response.text
    assert response.json()["stages"]["zone"]["markdown_table"]
