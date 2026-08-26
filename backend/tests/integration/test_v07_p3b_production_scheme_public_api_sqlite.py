"""V0.7 P3B public production-scheme API integration tests (SQLite)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v05_local_sample import load_manifest, seed_v05_local_sample
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from tests.integration.test_production_scheme_sqlite import (
    WEIGHT_REVISION_ID,
    _seed_weight_set_and_revision,
)
from tests.integration.v05_p4_acceptance_fixtures import assert_canonical_five_persisted

BACKEND_DIR = Path(__file__).resolve().parents[2]

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "P3B SQLite integration tests require DATABASE_BACKEND != postgresql",
        allow_module_level=True,
    )


def _wire_report_service_with_scheme_query(
    app,
    project_service: DatabaseProjectService,
) -> None:
    from collections.abc import Generator as TypingGenerator

    from fastapi import Depends
    from sqlalchemy.orm import Session as SASession

    from cold_storage.bootstrap.dependencies import get_engine
    from cold_storage.modules.reports.api.routes import _get_service as _reports_service_stub
    from cold_storage.modules.reports.application.assembler import ReportAssembler
    from cold_storage.modules.reports.application.service import (
        ReportService,
        _default_trusted_operator,
    )
    from cold_storage.modules.reports.infrastructure.persisted_calculation_query import (
        SqlAlchemyPersistedCalculationQuery,
    )
    from cold_storage.modules.reports.infrastructure.real_data_provider import (
        RealReportDataProvider,
    )
    from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository
    from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

    def _get_reports_db_session() -> TypingGenerator[SASession, None, None]:
        engine = get_engine()
        session = SASession(bind=engine, expire_on_commit=False)
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_report_service(
        db_session: SASession = Depends(_get_reports_db_session),  # noqa: B008
    ) -> ReportService:
        repo = SQLReportRepository(db_session)
        scheme_query = build_sqlalchemy_scheme_query(db_session)
        calculation_query = SqlAlchemyPersistedCalculationQuery(db_session)
        data_provider = RealReportDataProvider(
            project_service=project_service,
            calculation_service=calculation_query,
            scheme_query=scheme_query,
        )
        assembler = ReportAssembler(data_provider=data_provider)
        return ReportService(
            repository=repo,
            assembler=assembler,
            scheme_review_query=scheme_query,
            trusted_operator=_default_trusted_operator,
        )

    app.dependency_overrides[_reports_service_stub] = _get_report_service


def _seed_report_templates(engine) -> None:
    from sqlalchemy.orm import Session as SASession

    from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository
    from cold_storage.modules.reports.infrastructure.template_seed import seed_default_templates

    session = SASession(bind=engine, expire_on_commit=False)
    try:
        seed_default_templates(SQLReportRepository(session))
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def p3b_client(
    tmp_path,
) -> Generator[tuple[TestClient, DatabaseProjectService, object], None, None]:
    db_path = tmp_path / "v07_p3b_production_scheme.db"
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
    app = create_app(project_service=service)
    _wire_report_service_with_scheme_query(app, service)
    _seed_report_templates(engine)

    with TestClient(app) as client:
        yield client, service, engine

    engine.dispose()
    db_path.unlink(missing_ok=True)


def _seed_five_stage_project(client: TestClient):
    manifest = load_manifest()
    return seed_v05_local_sample(client, manifest=manifest)


def _version_id(client: TestClient, project_id: str, version_number: int) -> str:
    return client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()["id"]


def _seed_weight_revision(engine) -> None:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        _seed_weight_set_and_revision(session)


def _create_production_scheme_run_via_api(
    client: TestClient,
    *,
    project_id: str,
    version_number: int,
) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/production-scheme-runs",
        json={
            "profile_codes": ["balanced"],
            "weight_set_revision_id": WEIGHT_REVISION_ID,
            "profile_parameters": {},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _export_report_scheme_comparison(
    client: TestClient,
    *,
    project_id: str,
    version_id: str,
) -> dict:
    report = client.post(
        "/api/v1/reports",
        json={
            "project_id": project_id,
            "project_version_id": version_id,
            "report_type": "cold_storage_concept_design",
        },
    )
    assert report.status_code == 200, report.text
    report_id = report.json()["report_id"]
    generated = client.post(f"/api/v1/reports/{report_id}/generate")
    assert generated.status_code == 200, generated.text
    exported = client.get(
        f"/api/v1/reports/{report_id}/export",
        params={"revision_number": 1, "format": "json"},
    )
    assert exported.status_code == 200, exported.text
    return exported.json()["content"]["scheme_comparison"]


def test_public_production_scheme_api_persists_production_run(p3b_client) -> None:
    client, _service, engine = p3b_client
    seeded = _seed_five_stage_project(client)
    version_id = _version_id(client, seeded.project_id, seeded.version_number)
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    assert_canonical_five_persisted(calculations)
    _seed_weight_revision(engine)

    body = _create_production_scheme_run_via_api(
        client,
        project_id=seeded.project_id,
        version_number=seeded.version_number,
    )

    assert body["source_mode"] == "production"
    assert body["project_version_id"] == version_id
    assert body["source_binding_id"] == seeded.source_binding_id
    assert body["weight_set_revision_id"] == WEIGHT_REVISION_ID
    assert body["run_id"]
    assert body["combined_source_hash"]
    assert body["content_hash"]


def test_report_readback_projects_scheme_comparison_review_authority(p3b_client) -> None:
    client, _service, engine = p3b_client
    seeded = _seed_five_stage_project(client)
    version_id = _version_id(client, seeded.project_id, seeded.version_number)
    _seed_weight_revision(engine)

    scheme_body = _create_production_scheme_run_via_api(
        client,
        project_id=seeded.project_id,
        version_number=seeded.version_number,
    )
    scheme_comparison = _export_report_scheme_comparison(
        client,
        project_id=seeded.project_id,
        version_id=version_id,
    )

    authority = scheme_comparison["review_authority"]
    assert authority["scheme_run_id"] == scheme_body["run_id"]
    assert authority["source_binding_id"] == scheme_body["source_binding_id"]
    assert authority["combined_source_hash"] == scheme_body["combined_source_hash"]
    assert authority["requires_review"] == scheme_body["requires_review"]
    assert len(authority["review_reasons"]) == len(scheme_body["review_reasons"])
