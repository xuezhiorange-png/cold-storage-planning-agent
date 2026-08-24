"""V04-P1 persisted workbench integration tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.projects.infrastructure.orm import Base


def _create_project_with_inputs(client: TestClient) -> tuple[str, int]:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "V04-P1 持久化工作台",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version = created["current_version_number"]
    client.put(
        f"/api/v1/projects/{project_id}/versions/{version}/inputs",
        json={
            "inputs": {
                "daily_inbound_mass_kg": 25_000,
                "working_time_h_per_day": 16,
                "utilization_factor": 0.85,
                "finished_storage_days": 2.5,
                "packaging_storage_days": 3,
                "main_packaging_storage_days": 3,
                "auxiliary_packaging_storage_days": 30,
                "reserve_factor": 1.05,
            }
        },
    )
    return project_id, version


def test_planning_run_persists_planning_helpers_and_power_table(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'v04-p1.db'}"
    service = create_database_project_service(database_url)
    Base.metadata.create_all(service.engine)
    client = TestClient(create_app(project_service=service))

    project_id, version = _create_project_with_inputs(client)
    planning_run = client.post(
        f"/api/v1/projects/{project_id}/versions/{version}/planning-run",
        json={},
    ).json()
    assert "error" not in planning_run
    assert planning_run["success"] is True
    assert planning_run["power_configuration"]["equipment_rows"][0]["name"] == "制冷压缩机组"

    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version}/calculations"
    ).json()
    calculator_names = {row["calculator_name"] for row in calculations}
    assert calculator_names == {
        "cold_room_zone_plan",
        "investment_estimate",
        "power_configuration",
    }

    power_configuration = next(
        row for row in calculations if row["calculator_name"] == "power_configuration"
    )
    equipment_name = power_configuration["result_snapshot"]["result"]["equipment_rows"][0]["name"]
    assert equipment_name == "制冷压缩机组"

    second_service = create_database_project_service(database_url)
    second_client = TestClient(create_app(project_service=second_service))
    reloaded = second_client.get(
        f"/api/v1/projects/{project_id}/versions/{version}/calculations"
    ).json()
    reloaded_names = {row["calculator_name"] for row in reloaded}
    assert reloaded_names == {
        "cold_room_zone_plan",
        "investment_estimate",
        "power_configuration",
    }


def test_missing_persisted_runs_do_not_inject_demo_planning_run(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'v04-p1-empty.db'}"
    service = create_database_project_service(database_url)
    Base.metadata.create_all(service.engine)
    client = TestClient(create_app(project_service=service))

    project_id, version = _create_project_with_inputs(client)
    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version}/calculations"
    ).json()
    assert calculations == []

    planning_run = client.post(
        f"/api/v1/projects/{project_id}/versions/{version}/planning-run",
        json={},
    ).json()
    assert "error" not in planning_run
