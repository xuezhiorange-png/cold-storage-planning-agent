"""V0.6 P1 five-stage persisted report assembly integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.production_composition import compose_production_scheme_service
from cold_storage.bootstrap.v05_local_sample import load_manifest, seed_v05_local_sample
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.planning.application.service import build_power_configuration
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
)
from tests.integration.test_production_scheme_sqlite import (
    WEIGHT_REVISION_ID,
    _seed_weight_set_and_revision,
)
from tests.integration.v05_p4_acceptance_fixtures import (
    CANONICAL_CALCULATORS,
    assert_canonical_five_persisted,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.parametrize(
    "database_backend",
    [
        pytest.param(
            "sqlite",
            marks=pytest.mark.skipif(
                os.environ.get("DATABASE_BACKEND") == "postgresql",
                reason="SQLite assembly tests cannot run on PostgreSQL backend",
            ),
        ),
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                os.environ.get("DATABASE_BACKEND") != "postgresql",
                reason="PostgreSQL assembly tests require DATABASE_BACKEND=postgresql",
            ),
        ),
    ],
)


@pytest.fixture()
def assembly_client(database_backend: str, tmp_path, request):
    if database_backend == "sqlite":
        db_path = tmp_path / "v06_p1_assembly.db"
        os.environ["SQLITE_PATH"] = str(db_path)
        os.environ["DATABASE_BACKEND"] = "sqlite"
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
            pytest.fail(f"Alembic upgrade failed:\n{result.stderr}\n{result.stdout}")
        engine = __import__("sqlalchemy").create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @__import__("sqlalchemy").event.listens_for(engine, "connect")
        def _pragma(dbapi_conn, _rec) -> None:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        service = DatabaseProjectService(engine)
        with TestClient(create_app(project_service=service)) as client:
            yield client, service, engine
        engine.dispose()
        db_path.unlink(missing_ok=True)
        return

    pg_engine = request.getfixturevalue("pg_engine")
    service = DatabaseProjectService(pg_engine)
    with TestClient(create_app(project_service=service)) as client:
        yield client, service, pg_engine


def _seed_five_stage_project(client: TestClient):
    manifest = load_manifest()
    return seed_v05_local_sample(client, manifest=manifest)


def _version_id(client: TestClient, project_id: str, version_number: int) -> str:
    return client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()["id"]


def _generate_production_scheme(engine, project_id: str, version_id: str) -> None:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    binding_id: str | None = None
    with session_factory() as session:
        binding = session.scalar(
            select(SourceBindingRecord).where(
                SourceBindingRecord.project_id == project_id,
                SourceBindingRecord.project_version_id == version_id,
            )
        )
        assert binding is not None, "five-stage execution must persist SourceBinding"
        binding_id = binding.id
        _seed_weight_set_and_revision(session)

    assert binding_id is not None
    service = compose_production_scheme_service(session_factory)
    service.generate_production_scheme_run(
        GenerateProductionSchemeCommand(
            source_binding_id=binding_id,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="v06-p1-test",
            correlation_id=f"v06-p1-{uuid.uuid4().hex[:8]}",
            database_backend=os.environ.get("DATABASE_BACKEND", "sqlite"),
        )
    )


def _create_and_export_report(
    client: TestClient,
    *,
    project_id: str,
    version_id: str,
) -> tuple[dict, dict]:
    report = client.post(
        "/api/v1/reports",
        json={
            "project_id": project_id,
            "project_version_id": version_id,
            "report_type": "cold_storage_concept_design",
        },
    )
    assert report.status_code == 200, report.text
    report_body = report.json()
    report_id = report_body["report_id"]
    generated = client.post(f"/api/v1/reports/{report_id}/generate")
    assert generated.status_code == 200, generated.text
    exported = client.get(
        f"/api/v1/reports/{report_id}/export",
        params={"revision_number": 1, "format": "json"},
    )
    assert exported.status_code == 200, exported.text
    return {"id": report_id, **report_body}, exported.json()


def _finding_codes(exported: dict) -> set[str]:
    findings = exported["content"]["quality_summary"]["findings"]
    return {finding["code"] for finding in findings}


def _invalidate_canonical_projection(
    session,
    *,
    version_id: str,
    calculator_names: tuple[str, ...],
) -> None:
    """Corrupt persisted snapshots so report assembly cannot project sections."""
    session.execute(
        update(CalculationRunRecord)
        .where(
            CalculationRunRecord.project_version_id == version_id,
            CalculationRunRecord.calculator_name.in_(calculator_names),
        )
        .values(result_snapshot={})
    )
    session.commit()


def test_five_stage_report_binds_persisted_ids_and_investment(
    assembly_client,
) -> None:
    client, service, engine = assembly_client
    seeded = _seed_five_stage_project(client)
    version_id = _version_id(client, seeded.project_id, seeded.version_number)

    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = assert_canonical_five_persisted(calculations)

    _generate_production_scheme(engine, seeded.project_id, version_id)

    _report, exported = _create_and_export_report(
        client,
        project_id=seeded.project_id,
        version_id=version_id,
    )
    content = exported["content"]
    assert "investment_estimate" in content
    assert content["investment_estimate"]["total_investment"] > 0
    assert content["input_conditions"]
    assert content["input_conditions"]["zones"]
    assert content["assumptions"]["items"]

    citations = content["citations"]
    cited_tools = {item["tool_name"]: item["result_id"] for item in citations}
    assert cited_tools["cold_room_zone_plan"] == by_name["cold_room_zone_plan"]["calculation_id"]
    assert cited_tools["cooling_load"] == by_name["cooling_load"]["calculation_id"]
    assert cited_tools["equipment"] == by_name["equipment"]["calculation_id"]
    assert cited_tools["installed_power"] == by_name["installed_power"]["calculation_id"]
    assert cited_tools["investment_estimate"] == by_name["investment_estimate"]["calculation_id"]

    for calculator_name in CANONICAL_CALCULATORS:
        assert by_name[calculator_name]["result_hash"]

    report_record = client.get(f"/api/v1/reports/{_report['id']}").json()
    assert report_record["status"] in {"draft", "generated"}


def test_restart_reopen_preserves_calculation_binding(assembly_client) -> None:
    client, service, engine = assembly_client
    seeded = _seed_five_stage_project(client)
    version_id = _version_id(client, seeded.project_id, seeded.version_number)
    first_calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    first_by_name = assert_canonical_five_persisted(first_calculations)

    with TestClient(create_app(project_service=service)) as restarted:
        second_calculations = restarted.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
        ).json()
        second_by_name = assert_canonical_five_persisted(second_calculations)
        for name in CANONICAL_CALCULATORS:
            assert second_by_name[name]["calculation_id"] == first_by_name[name]["calculation_id"]
            assert second_by_name[name]["result_hash"] == first_by_name[name]["result_hash"]

        _generate_production_scheme(engine, seeded.project_id, version_id)

        _report, exported = _create_and_export_report(
            restarted,
            project_id=seeded.project_id,
            version_id=version_id,
        )
    cited = {
        item["tool_name"]: item["result_id"]
        for item in exported["content"]["citations"]
        if item.get("tool_name") in CANONICAL_CALCULATORS
    }
    for name in CANONICAL_CALCULATORS:
        assert cited[name] == first_by_name[name]["calculation_id"]


def test_missing_investment_fails_closed_with_blockers(assembly_client) -> None:
    client, _service, engine = assembly_client
    seeded = _seed_five_stage_project(client)
    version_id = _version_id(client, seeded.project_id, seeded.version_number)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        _invalidate_canonical_projection(
            session,
            version_id=version_id,
            calculator_names=("investment_estimate",),
        )

    _report, exported = _create_and_export_report(
        client,
        project_id=seeded.project_id,
        version_id=version_id,
    )
    codes = _finding_codes(exported)
    assert "MISSING_CANONICAL_SOURCE" in codes
    assert exported["content"]["quality_summary"]["blocker_count"] > 0
    assert "investment_estimate" not in exported["content"]


def test_missing_cooling_and_power_fail_closed_with_blockers(assembly_client) -> None:
    client, _service, engine = assembly_client
    seeded = _seed_five_stage_project(client)
    version_id = _version_id(client, seeded.project_id, seeded.version_number)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        _invalidate_canonical_projection(
            session,
            version_id=version_id,
            calculator_names=("cooling_load", "installed_power", "investment_estimate"),
        )

    _report, exported = _create_and_export_report(
        client,
        project_id=seeded.project_id,
        version_id=version_id,
    )
    codes = _finding_codes(exported)
    assert "MISSING_CANONICAL_SOURCE" in codes or "MISSING_REQUIRED_SECTION" in codes
    assert exported["content"]["quality_summary"]["blocker_count"] > 0


def test_power_configuration_cannot_satisfy_installed_power(assembly_client) -> None:
    client, _service, engine = assembly_client
    seeded = _seed_five_stage_project(client)
    version_id = _version_id(client, seeded.project_id, seeded.version_number)

    power_configuration = build_power_configuration([], 25_000, 1_000.0)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        _invalidate_canonical_projection(
            session,
            version_id=version_id,
            calculator_names=("installed_power",),
        )
        session.add(
            CalculationRunRecord(
                id=str(uuid.uuid4()),
                project_id=seeded.project_id,
                project_version_id=version_id,
                calculator_name="power_configuration",
                calculator_version="1.0.0",
                input_snapshot={},
                result_snapshot=power_configuration,
                formulas=[],
                coefficients=[],
                assumptions=list(power_configuration.get("assumptions", [])),
                warnings=[],
                source_references=[],
                requires_review=True,
            )
        )
        session.commit()

    _report, exported = _create_and_export_report(
        client,
        project_id=seeded.project_id,
        version_id=version_id,
    )
    content = exported["content"]
    assert "electrical_and_energy" not in content or not content.get("electrical_and_energy")
    codes = _finding_codes(exported)
    assert (
        "MISSING_CANONICAL_SOURCE" in codes
        or "MISSING_REQUIRED_SECTION" in codes
        or "REPORT_QUALITY_BLOCKER" in codes
    )
