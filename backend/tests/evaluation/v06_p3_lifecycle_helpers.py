"""Shared helpers for V0.6 P3 review-to-formal evaluation tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.production_composition import compose_production_scheme_service
from cold_storage.bootstrap.v05_local_sample import load_manifest, seed_v05_local_sample
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.reports.api.routes import _get_actor
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
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "v06"

TRUSTED_ACTOR = "v06-p3-trusted-reviewer"
UNTRUSTED_ACTOR = "system"
SCENARIO_LABEL = "high_throughput_review"
TEMPLATE_VERSION = "1.0.0"
FORMAL_LOCALES = ("zh-CN", "en-US")
FORMAL_FORMATS = ("docx", "pdf")


def fixture_path(name: str) -> Path:
    path = FIXTURES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"missing V0.6 P3 fixture: {path}")
    return path


def load_fixture(name: str) -> dict[str, Any]:
    with fixture_path(name).open(encoding="utf-8") as handle:
        return json.load(handle)


def fixture_sha256(name: str) -> str:
    return hashlib.sha256(fixture_path(name).read_bytes()).hexdigest()


def _set_sqlite_env(db_path: Path) -> None:
    """Pin sqlite path for alembic, Settings, and injected project service.

    When ``COLD_STORAGE_STORAGE_DIR`` is set, legacy ``SQLITE_PATH`` alone is
    ignored by Settings resolution; canonical ``COLD_STORAGE_SQLITE_PATH`` is
    required so reports ``get_engine()`` and the test database stay aligned.
    """
    os.environ["SQLITE_PATH"] = str(db_path)
    os.environ["COLD_STORAGE_SQLITE_PATH"] = str(db_path)
    os.environ["COLD_STORAGE_DATABASE_BACKEND"] = "sqlite"


def _run_alembic_sqlite(db_path: Path) -> None:
    env = os.environ.copy()
    _set_sqlite_env(db_path)
    env["SQLITE_PATH"] = str(db_path)
    env["COLD_STORAGE_SQLITE_PATH"] = str(db_path)
    env["COLD_STORAGE_DATABASE_BACKEND"] = "sqlite"
    src_path = (BACKEND_DIR / "src").resolve()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts = [str(src_path)] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed:\n{result.stderr}\n{result.stdout}")


def create_sqlite_engine(db_path: Path) -> Engine:
    import sqlalchemy

    _set_sqlite_env(db_path)
    _run_alembic_sqlite(db_path)
    engine = sqlalchemy.create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sqlalchemy.event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def _wire_report_service_with_project(app, project_service: DatabaseProjectService) -> None:
    """Ensure report assembly reads project metadata for required sections."""
    from collections.abc import Generator

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

    def _get_reports_db_session() -> Generator[SASession, None, None]:
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


def _apply_v05_investment_translation_overlay() -> None:
    """Extend report translation catalogs for v05 investment item labels."""
    from cold_storage.modules.reports.domain.enums import ReportLocale
    from cold_storage.modules.reports.localization.catalog import _CATALOGS, TranslationCatalog

    overlay = load_fixture("v06_p3_investment_translation_overlay.v1.json")
    for locale_key, messages in overlay["locales"].items():
        locale = ReportLocale(locale_key)
        base = _CATALOGS[locale]
        merged = dict(base.messages)
        merged.update(messages)
        _CATALOGS[locale] = TranslationCatalog(
            locale=locale,
            version=base.version,
            messages=merged,
        )


def _seed_report_templates(engine: Engine) -> None:
    from sqlalchemy.orm import Session as SASession

    from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository
    from cold_storage.modules.reports.infrastructure.template_seed import seed_default_templates

    session = SASession(bind=engine, expire_on_commit=False)
    try:
        seed_default_templates(SQLReportRepository(session))
        session.commit()
    finally:
        session.close()


def make_evaluation_client(
    service: DatabaseProjectService,
    *,
    artifact_dir: Path,
    actor: str = TRUSTED_ACTOR,
) -> TestClient:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    os.environ["COLD_STORAGE_STORAGE_DIR"] = str(artifact_dir)
    os.environ.setdefault("COLD_STORAGE_ENVIRONMENT_ID", "local")
    app = create_app(project_service=service)

    from cold_storage.bootstrap.dependencies import _singletons, get_engine, get_project_service

    engine = service.engine
    _singletons["engine"] = engine
    _singletons["project_service"] = service
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_project_service] = lambda: service
    app.dependency_overrides[_get_actor] = lambda: actor
    _wire_report_service_with_project(app, service)
    _apply_v05_investment_translation_overlay()
    _seed_report_templates(engine)
    return TestClient(app)


def seed_five_stage_project(client: TestClient) -> Any:
    manifest = load_manifest()
    return seed_v05_local_sample(client, manifest=manifest)


def version_id(client: TestClient, project_id: str, version_number: int) -> str:
    return client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()["id"]


def generate_production_scheme(engine: Engine, project_id: str, version_id: str) -> dict[str, Any]:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    binding_id: str | None = None
    with session_factory() as session:
        binding = session.scalar(
            select(SourceBindingRecord).where(
                SourceBindingRecord.project_id == project_id,
                SourceBindingRecord.project_version_id == version_id,
            )
        )
        if binding is None:
            raise AssertionError("five-stage execution must persist SourceBinding")
        binding_id = binding.id
        _seed_weight_set_and_revision(session)

    service = compose_production_scheme_service(session_factory)
    scheme_run = service.generate_production_scheme_run(
        GenerateProductionSchemeCommand(
            source_binding_id=binding_id,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            profile_codes=("balanced",),
            profile_parameters={},
            actor=TRUSTED_ACTOR,
            correlation_id=f"v06-p3-{uuid.uuid4().hex[:8]}",
            database_backend=os.environ.get("DATABASE_BACKEND", "sqlite"),
        )
    )
    return {
        "scheme_run_id": scheme_run.id,
        "requires_review": scheme_run.requires_review,
        "review_reasons": list(scheme_run.warning_messages or []),
    }


def create_report(client: TestClient, *, project_id: str, version_id: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/reports",
        json={
            "project_id": project_id,
            "project_version_id": version_id,
            "report_type": "cold_storage_concept_design",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return {"id": body["report_id"], **body}


def generate_report_revision(client: TestClient, report_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/reports/{report_id}/generate")
    assert response.status_code == 200, response.text
    return response.json()


def export_report_json(
    client: TestClient,
    report_id: str,
    *,
    revision_number: int = 1,
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/reports/{report_id}/export",
        params={"revision_number": revision_number, "format": "json"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit_review(client: TestClient, report_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/reports/{report_id}/submit-review")
    assert response.status_code == 200, response.text
    return response.json()


def mark_reviewed(client: TestClient, report_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return response.json()
    return {"status_code": response.status_code, "text": response.text}


def approve_report(client: TestClient, report_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/reports/{report_id}/approve")
    assert response.status_code == 200, response.text
    return response.json()


def render_formal(
    client: TestClient,
    report_id: str,
    *,
    revision_number: int,
    locale: str,
    export_format: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/reports/{report_id}/revisions/{revision_number}/render",
        json={
            "format": export_format,
            "template_version": TEMPLATE_VERSION,
            "mode": "formal",
            "locale": locale,
        },
    )
    content_type = response.headers.get("content-type", "")
    body = response.json() if content_type.startswith("application/json") else response.text
    return {
        "status_code": response.status_code,
        "body": body,
    }


def complete_trusted_review_lifecycle(
    client: TestClient,
    report_id: str,
) -> dict[str, Any]:
    submit_review(client, report_id)
    reviewed = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    assert reviewed.status_code == 200, reviewed.text
    approved = approve_report(client, report_id)
    return approved


def invalidate_canonical_projection(
    session: Session,
    *,
    version_id: str,
    calculator_names: tuple[str, ...],
) -> None:
    session.execute(
        update(CalculationRunRecord)
        .where(
            CalculationRunRecord.project_version_id == version_id,
            CalculationRunRecord.calculator_name.in_(calculator_names),
        )
        .values(result_snapshot={})
    )
    session.commit()


def collect_source_result_ids(content: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            source_result_id = node.get("source_result_id")
            if isinstance(source_result_id, str) and source_result_id:
                found.add(source_result_id)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(content)
    return found


def walk_measured_values(content: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if "source_result_id" in node and "source_tool" in node and "value" in node:
                rows.append(node)
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(content)
    return rows


def assert_input_conditions_from_manifest(
    content: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    input_conditions = content.get("input_conditions")
    assert isinstance(input_conditions, dict)
    zones = input_conditions.get("zones")
    assert isinstance(zones, list) and zones, (
        "input_conditions.zones must come from persisted snapshot"
    )

    bundle = manifest["engineering_input_bundle"]
    expected_daily = bundle["zone_planning_inputs"]["daily_inbound_mass_kg"]["value"]
    manifest_zones = bundle["cooling_load_inputs"]["zones"]
    expected_zone_code = manifest_zones[0]["zone_code"]["value"]
    assert zones[0].get("zone_code") == expected_zone_code
    zone_mass = zones[0].get("product_mass_per_day") or zones[0].get("daily_inbound_mass_kg")
    assert str(zone_mass) == str(expected_daily)


def assert_assumptions_from_persisted_snapshot(content: dict[str, Any]) -> None:
    assumptions = content.get("assumptions")
    assert isinstance(assumptions, dict)
    items = assumptions.get("items")
    assert isinstance(items, list) and items, "assumptions.items must come from persisted snapshots"


def seeded_project_context(
    client: TestClient,
    engine: Engine,
) -> dict[str, Any]:
    seeded = seed_five_stage_project(client)
    version = version_id(client, seeded.project_id, seeded.version_number)
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = assert_canonical_five_persisted(calculations)
    scheme = generate_production_scheme(engine, seeded.project_id, version)
    return {
        "seeded": seeded,
        "version_id": version,
        "by_name": by_name,
        "scheme": scheme,
        "manifest": load_manifest(),
    }


__all__ = [
    "BACKEND_DIR",
    "CANONICAL_CALCULATORS",
    "FIXTURES_DIR",
    "FORMAL_FORMATS",
    "FORMAL_LOCALES",
    "SCENARIO_LABEL",
    "TEMPLATE_VERSION",
    "TRUSTED_ACTOR",
    "UNTRUSTED_ACTOR",
    "approve_report",
    "assert_assumptions_from_persisted_snapshot",
    "assert_canonical_five_persisted",
    "assert_input_conditions_from_manifest",
    "collect_source_result_ids",
    "complete_trusted_review_lifecycle",
    "create_report",
    "create_sqlite_engine",
    "export_report_json",
    "fixture_path",
    "fixture_sha256",
    "generate_production_scheme",
    "generate_report_revision",
    "invalidate_canonical_projection",
    "load_fixture",
    "make_evaluation_client",
    "mark_reviewed",
    "render_formal",
    "seed_five_stage_project",
    "seeded_project_context",
    "submit_review",
    "version_id",
    "walk_measured_values",
]
