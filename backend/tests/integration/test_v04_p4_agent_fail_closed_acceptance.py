"""V04-P4 agent fail-closed acceptance integration matrix (sqlite only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v04_local_sample import load_manifest, seed_v04_local_sample
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.projects.infrastructure.orm import Base

REQUIRED_PERSISTED_CALCULATORS = frozenset(
    {
        "cold_room_zone_plan",
        "investment_estimate",
        "power_configuration",
    }
)

_AGENT_DISABLED_ERROR_CODE = "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE"

# Patterns that would indicate fabricated engineering numbers in agent error bodies.
_FABRICATED_NUMBER_PATTERNS = (
    re.compile(r"cooling[_\s-]?load", re.IGNORECASE),
    re.compile(r"investment[_\s-]?estimate", re.IGNORECASE),
    re.compile(r"total_investment_cny"),
    re.compile(r"total_power_kw"),
    re.compile(r"equipment_rows"),
)


def _create_sqlite_client(tmp_path: Path, db_name: str) -> TestClient:
    database_url = f"sqlite:///{tmp_path / db_name}"
    service = create_database_project_service(database_url)
    Base.metadata.create_all(service.engine)
    return TestClient(create_app(project_service=service))


def _assert_no_fabricated_engineering_numbers(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False)
    for pattern in _FABRICATED_NUMBER_PATTERNS:
        assert not pattern.search(body), f"unexpected fabricated engineering field: {pattern.pattern}"


def test_v04_p4_sample_seed_persists_required_calculators(tmp_path: Path) -> None:
    client = _create_sqlite_client(tmp_path, "v04-p4-seed.db")
    manifest = load_manifest()
    seeded = seed_v04_local_sample(client, manifest=manifest)

    assert seeded.planning_run_success is True
    calculator_names = set(seeded.persisted_calculator_names)
    assert calculator_names >= REQUIRED_PERSISTED_CALCULATORS


def test_v04_p4_workflow_agent_assistance_fail_closed(tmp_path: Path) -> None:
    client = _create_sqlite_client(tmp_path, "v04-p4-workflow.db")
    seeded = seed_v04_local_sample(client)

    workflow = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/workflow"
    ).json()
    agent = cast(dict[str, Any], workflow["agent_assistance"])

    assert agent["available"] is False
    assert agent["status"] in {"UNAVAILABLE", "NOT_READY"}
    assert agent["status"] != "AVAILABLE"
    assert agent.get("capability_state")
    assert agent["capability_state"] != "AGENT_CAPABILITY_ENABLED_READY"
    assert agent.get("unavailability_reason")
    assert agent["blocking_core_workflow"] is False

    agent_step = next(step for step in workflow["steps"] if step["step"] == "AGENT_ASSISTANCE")
    assert agent_step["applicability"] == "OPTIONAL"
    assert agent_step["blocking"] is False
    assert agent_step["status"] in {"UNAVAILABLE", "NOT_READY"}


def test_v04_p4_agent_routes_fail_closed_without_live_key(tmp_path: Path) -> None:
    client = _create_sqlite_client(tmp_path, "v04-p4-agent-routes.db")
    seeded = seed_v04_local_sample(client)

    create_session = client.post(
        "/api/v1/agent/sessions",
        json={
            "title": "P4 fail-closed",
            "project_id": seeded.project_id,
            "project_version_id": str(seeded.version_number),
        },
    )
    assert create_session.status_code == 503
    create_body = create_session.json()
    assert create_body["error"]["code"] == _AGENT_DISABLED_ERROR_CODE
    _assert_no_fabricated_engineering_numbers(create_body)

    post_message = client.post(
        "/api/v1/agent/sessions/fake-session-id/messages",
        json={"content": "hello"},
    )
    assert post_message.status_code == 503
    message_body = post_message.json()
    assert message_body["error"]["code"] == _AGENT_DISABLED_ERROR_CODE
    _assert_no_fabricated_engineering_numbers(message_body)
