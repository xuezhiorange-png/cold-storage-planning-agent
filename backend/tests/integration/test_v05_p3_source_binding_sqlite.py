"""V0.5 P3 source-binding alignment integration tests (SQLite)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite V0.5 P3 source-binding tests cannot run on PostgreSQL",
        allow_module_level=True,
    )

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    ProjectServicePersistedCalculationQuery,
)
from cold_storage.modules.schemes.application.service import SchemeService
from cold_storage.modules.schemes.domain.errors import SourceCalculationMissingError
from cold_storage.modules.schemes.infrastructure.repository import SchemeRepository
from cold_storage.bootstrap.scheme_seed import demo_weight_set
from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle
from tests.integration.v05_p3_canonical_fixtures import (
    CANONICAL_CALCULATORS,
    CANONICAL_SNAPSHOTS,
    POWER_CONFIGURATION_SNAPSHOT,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def migrated_client():
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


def _create_project(client: TestClient) -> tuple[str, int, str]:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "V05-P3 Binding",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def _execute_five_stage(client: TestClient, project_id: str, version_number: int, version_id: str):
    bundle = build_valid_engineering_input_bundle(
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    return client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": f"idem-{uuid.uuid4()}"},
    ).json()


def _workflow_calc_step(client: TestClient, project_id: str, version_number: int) -> dict:
    payload = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}/workflow").json()
    return next(step for step in payload["steps"] if step["step"] == "DETERMINISTIC_CALCULATION")


def test_p3_happy_path_workflow_scheme_report_accept_canonical_five(migrated_client) -> None:
    client, service, _engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    execution = _execute_five_stage(client, project_id, version_number, version_id)
    assert "error" not in execution, execution

    calc_step = _workflow_calc_step(client, project_id, version_number)
    assert calc_step["status"] in {"COMPLETED", "REVIEW_REQUIRED"}
    assert not any(
        blocker.get("code") == "CALCULATION_MISSING"
        for blocker in calc_step.get("blockers", [])
    )

    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    assert CANONICAL_CALCULATORS.issubset({row["calculator_name"] for row in calculations})

    query = ProjectServicePersistedCalculationQuery(service)
    orchestrated = query.get_orchestrated_result(project_id, version_id)
    assert orchestrated is not None
    assert orchestrated.power_result is not None
    assert orchestrated.power_result.calculator_name == "installed_power"


def test_p3_missing_installed_power_with_power_configuration_fails_closed(
    migrated_client,
) -> None:
    client, service, engine = migrated_client
    project_id, version_number, version_id = _create_project(client)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        for calculator_name, snapshot in CANONICAL_SNAPSHOTS.items():
            if calculator_name == "installed_power":
                continue
            session.add(
                CalculationRunRecord(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    project_version_id=version_id,
                    calculator_name=calculator_name,
                    calculator_version="1.0.0",
                    input_snapshot={},
                    result_snapshot=snapshot,
                    formulas=[],
                    coefficients=[],
                    assumptions=[],
                    warnings=[],
                    source_references=[],
                    requires_review=False,
                )
            )
        session.add(
            CalculationRunRecord(
                id=str(uuid.uuid4()),
                project_id=project_id,
                project_version_id=version_id,
                calculator_name="power_configuration",
                calculator_version="1.0.0",
                input_snapshot={},
                result_snapshot=POWER_CONFIGURATION_SNAPSHOT,
                formulas=[],
                coefficients=[],
                assumptions=[],
                warnings=[],
                source_references=[],
                requires_review=False,
            )
        )
        session.commit()

    calc_step = _workflow_calc_step(client, project_id, version_number)
    assert calc_step["status"] == "NOT_STARTED"
    assert any(
        blocker.get("code") == "CALCULATION_MISSING" and "installed_power" in blocker.get("message", "")
        for blocker in calc_step["blockers"]
    )

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        scheme_service = SchemeService(session)
        repo = SchemeRepository(session)
        repo.save_weight_set(demo_weight_set())
        session.commit()
        with pytest.raises(SourceCalculationMissingError, match="installed_power"):
            scheme_service.generate_scheme_run(
                project_id=project_id,
                version=version_number,
                profile_codes=["balanced"],
                weight_set_id="demo-weight-set-001",
                profile_parameters={},
            )


def test_p3_project_version_mismatch_fails_closed(migrated_client) -> None:
    _client, service, _engine = migrated_client
    project_id, version_number, version_id = _create_project(_client)

    query = ProjectServicePersistedCalculationQuery(service)
    orchestrated = query.get_orchestrated_result(project_id, f"{version_id}-missing")
    assert orchestrated is None

    calc_step = _workflow_calc_step(_client, project_id, version_number)
    assert calc_step["status"] == "NOT_STARTED"


def test_p3_stale_upstream_lineage_marks_workflow_stale(migrated_client) -> None:
    client, _service, engine = migrated_client
    project_id, version_number, version_id = _create_project(client)
    _execute_five_stage(client, project_id, version_number, version_id)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        for record in session.scalars(
            select(CalculationRunRecord).where(
                CalculationRunRecord.project_version_id == version_id
            )
        ).all():
            record.requires_review = False
        equipment = session.scalar(
            select(CalculationRunRecord).where(
                CalculationRunRecord.project_version_id == version_id,
                CalculationRunRecord.calculator_name == "equipment",
            )
        )
        assert equipment is not None
        provenance = dict(equipment.provenance or {})
        provenance["upstream_calculation_ids"] = {"cooling_load": "stale-upstream-id"}
        equipment.provenance = provenance
        session.commit()

    payload = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}/workflow").json()
    calc_step = next(
        step for step in payload["steps"] if step["step"] == "DETERMINISTIC_CALCULATION"
    )
    assert calc_step["status"] == "STALE"
    assert payload["project_context"]["revision_stale"] is True
    assert any(
        "calculation_upstream_id_mismatch" in reason
        for reason in payload["project_context"]["revision_stale_reasons"]
    )
