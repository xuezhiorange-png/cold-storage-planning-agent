"""Integration tests for workflow aggregate API."""

from pathlib import Path

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.projects.infrastructure.orm import Base


def test_workflow_endpoint_is_read_only_and_returns_aggregate(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'workflow.db'}"
    service = create_database_project_service(database_url)
    Base.metadata.create_all(service.engine)
    client = TestClient(create_app(project_service=service))

    created = client.post(
        "/api/v1/projects",
        json={
            "name": "Workflow Demo",
            "location": "Shandong",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version = created["current_version_number"]

    client.put(
        f"/api/v1/projects/{project_id}/versions/{version}/inputs",
        json={
            "inputs": {
                "daily_inbound_mass_kg": 25000,
                "working_time_h_per_day": 16,
                "utilization_factor": 0.85,
                "finished_storage_days": 2.5,
                "packaging_storage_days": 3,
                "reserve_factor": 1.05,
            }
        },
    )

    response = client.get(f"/api/v1/projects/{project_id}/versions/{version}/workflow")
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "WorkflowAggregateV2"
    assert payload["project_context"]["project_id"] == project_id
    assert payload["workflow_goal"] == "formal_report"
    assert "workflow_readiness" in payload
    assert "formal_export_eligibility" in payload
    assert payload["formal_export_eligibility"]["authority_owner"] == "reports_module_p1_lifecycle"

    agent_step = next(step for step in payload["steps"] if step["step"] == "AGENT_ASSISTANCE")
    assert agent_step["applicability"] == "OPTIONAL"
    assert agent_step["blocking"] is False

    calculations_before = client.get(
        f"/api/v1/projects/{project_id}/versions/{version}/calculations"
    ).json()
    assert calculations_before == []

    workflow_after = client.get(f"/api/v1/projects/{project_id}/versions/{version}/workflow")
    assert workflow_after.status_code == 200
    after_payload = workflow_after.json()
    assert after_payload["current_step"] == "OPERATOR_PROCESS_INPUT"
    operator_step = next(
        step for step in after_payload["steps"] if step["step"] == "OPERATOR_PROCESS_INPUT"
    )
    assert operator_step["status"] != "COMPLETED"
