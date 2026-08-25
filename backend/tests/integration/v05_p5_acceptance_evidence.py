"""Shared V0.5 P5 controlled acceptance evidence assertions.

Reuses P4/P1 fixtures; P5 integration tests call these cells instead of
duplicating P4 test bodies.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v05_local_sample import load_manifest
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    ProjectServicePersistedCalculationQuery,
)
from tests.integration.v05_p4_acceptance_fixtures import (
    CANONICAL_CALCULATORS,
    assert_canonical_five_persisted,
    assert_upstream_lineage_matches_p0,
    assert_workflow_not_blocked_by_missing_canonical_slots,
    build_bundle_from_manifest,
    bundle_with_removed_key,
    create_project,
    execute_five_stage,
    generate_scheme_from_persisted,
    read_report_sections_from_persisted,
    seed_sample_project,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

MISSING_KEY_CASES: tuple[tuple[str, str], ...] = (
    ("equipment_inputs.condensing_temperature_c", "condensing_temperature_c"),
    ("cooling_load_inputs.zones[0].zone_area", "cooling geometry zone_area"),
)


@pytest.fixture()
def migrated_client():
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic upgrade failed:\n{result.stderr}\n{result.stdout}")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    service = DatabaseProjectService(engine)
    client = TestClient(create_app(project_service=service))
    yield client, service, engine
    engine.dispose()
    db_path.unlink(missing_ok=True)


def evidence_sample_seed_canonical_five_with_lineage(
    client: TestClient,
) -> tuple[str, int, dict[str, dict[str, Any]]]:
    manifest = load_manifest()
    seeded = seed_sample_project(client, manifest)
    assert seeded.five_stage_success is True

    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = assert_canonical_five_persisted(calculations)
    assert_upstream_lineage_matches_p0(by_name)
    assert "power_configuration" not in by_name or by_name.get("installed_power") is not None
    return seeded.project_id, seeded.version_number, by_name


def evidence_restart_preserves_calculation_ids_and_hashes(
    client: TestClient,
    service: DatabaseProjectService,
    project_id: str,
    version_number: int,
) -> None:
    first = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    first_by_name = assert_canonical_five_persisted(first)

    with TestClient(create_app(project_service=service)) as reopened:
        second = reopened.get(
            f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
        ).json()
    second_by_name = assert_canonical_five_persisted(second)
    for name in CANONICAL_CALCULATORS:
        assert second_by_name[name]["calculation_id"] == first_by_name[name]["calculation_id"]
        assert second_by_name[name]["result_hash"] == first_by_name[name]["result_hash"]


def evidence_missing_key_leaf_fails_closed_atomically(
    client: TestClient,
    engine,
    *,
    dotted_path: str,
) -> None:
    manifest = load_manifest()
    project_id, version_number, version_id = create_project(client)
    bundle = bundle_with_removed_key(
        build_bundle_from_manifest(
            manifest,
            project_id=project_id,
            project_version_id=version_id,
            version_number=version_number,
        ),
        dotted_path,
    )
    response = execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=bundle,
        idempotency_key=f"idem-p5-missing-{uuid.uuid4().hex[:8]}",
    )
    assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        canonical_count = session.scalar(
            select(func.count())
            .select_from(CalculationRunRecord)
            .where(
                CalculationRunRecord.project_version_id == version_id,
                CalculationRunRecord.calculator_name.in_(CANONICAL_CALCULATORS),
            )
        )
        assert canonical_count == 0
        assert session.scalar(select(func.count()).select_from(SourceBindingRecord)) == 0


def evidence_workflow_scheme_report_consume_persisted_installed_power(
    client: TestClient,
    service: DatabaseProjectService,
    engine,
    project_id: str,
    version_number: int,
) -> None:
    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    assert_canonical_five_persisted(calculations)
    version_id = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()["id"]

    assert_workflow_not_blocked_by_missing_canonical_slots(client, project_id, version_number)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        scheme_payload = generate_scheme_from_persisted(session, project_id, version_number)
        assert scheme_payload["status"] == "completed"
        schemes = scheme_payload.get("schemes") or []
        assert schemes
        installed_values = {item.get("installed_power_kw_e") for item in schemes}
        assert "999.0" not in installed_values

    query = ProjectServicePersistedCalculationQuery(service)
    orchestrated = query.get_orchestrated_result(project_id, version_id)
    assert orchestrated is not None
    assert orchestrated.power_result is not None
    assert orchestrated.power_result.calculator_name == "installed_power"

    sections = read_report_sections_from_persisted(service, project_id, version_id)
    assert sections
    persisted_ids = {
        row["calculator_name"]: row["calculation_id"]
        for row in calculations
        if row["calculator_name"] in CANONICAL_CALCULATORS
    }
    section_ids = {section["tool_name"]: section["result_id"] for section in sections}
    assert section_ids.get("cold_room_zone_plan") == persisted_ids["cold_room_zone_plan"]
    assert section_ids.get("installed_power") == persisted_ids["installed_power"]


def evidence_demo_coefficients_remain_marked(
    client: TestClient,
    project_id: str,
    version_number: int,
) -> None:
    del client, project_id, version_number
    manifest = load_manifest()
    bundle = manifest["engineering_input_bundle"]
    demo_leaves = bundle["coefficient_context"].get("demo_coefficient_leaves") or []
    assert demo_leaves
    for leaf in demo_leaves:
        assert leaf["source_type"] == "demo"
        assert leaf["validity_status"] in {"unverified", "conflict"}
        assert leaf["requires_review"] is True

    for optional_demo_path in (
        "zone_planning_inputs.raw_holding_hours",
        "zone_planning_inputs.storage_position_capacity_kg",
    ):
        parts = optional_demo_path.split(".")
        cursor = bundle
        for part in parts:
            cursor = cursor[part]
        assert cursor["source_type"] == "demo"
        assert cursor["validity_status"] in {"unverified", "conflict"}
        assert cursor["requires_review"] is True


def evidence_agent_assistance_not_fake_available(
    client: TestClient,
    project_id: str,
    version_number: int,
) -> None:
    workflow = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/workflow"
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

    create_session = client.post(
        "/api/v1/agent/sessions",
        json={
            "title": "P5 fail-closed",
            "project_id": project_id,
            "project_version_id": str(version_number),
        },
    )
    assert create_session.status_code == 503
    assert create_session.json()["error"]["code"] == "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE"
