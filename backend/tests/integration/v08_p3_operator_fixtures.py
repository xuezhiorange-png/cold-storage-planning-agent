"""Shared fixtures for V0.8 P3 operator-minimal sample integration tests."""

from __future__ import annotations

import copy
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.v08_sample_loader import (
    FORMAL_FORMATS,
    FORMAL_LOCALES,
    TEMPLATE_VERSION,
    UNTRUSTED_ACTOR,
    load_manifest,
    seed_v08_sample,
)
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.reports.api.routes import _get_actor
from tests.integration.v05_p4_acceptance_fixtures import assert_canonical_five_persisted

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
P3_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_8-P3-operator-sample-runbook-contract.md"
INVESTMENT_TRANSLATION_OVERLAY = (
    BACKEND_DIR / "tests" / "fixtures" / "v06" / "v06_p3_investment_translation_overlay.v1.json"
)

CANONICAL_CALCULATORS = frozenset(
    {
        "cold_room_zone_plan",
        "cooling_load",
        "equipment",
        "installed_power",
        "investment_estimate",
    }
)

_ENV_KEYS_TO_ISOLATE = (
    "SQLITE_PATH",
    "COLD_STORAGE_SQLITE_PATH",
    "COLD_STORAGE_DATABASE_BACKEND",
    "COLD_STORAGE_DATABASE_URL",
    "COLD_STORAGE_STORAGE_DIR",
    "COLD_STORAGE_ENVIRONMENT_ID",
    "DATABASE_BACKEND",
    "DATABASE_URL",
)


def operator_process_input_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(cast(dict[str, Any], manifest["operator_process_input"]))


def _snapshot_env() -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in _ENV_KEYS_TO_ISOLATE}


def _restore_env(snapshot: dict[str, str | None]) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _snapshot_singletons() -> dict[str, Any]:
    import cold_storage.bootstrap.dependencies as deps

    return dict(deps._singletons)


def _restore_singletons(snapshot: dict[str, Any]) -> None:
    import cold_storage.bootstrap.dependencies as deps

    deps._singletons.clear()
    deps._singletons.update(snapshot)


def _snapshot_catalogs() -> dict[Any, Any]:
    from cold_storage.modules.reports.localization.catalog import _CATALOGS

    return dict(_CATALOGS)


def _restore_catalogs(snapshot: dict[Any, Any]) -> None:
    from cold_storage.modules.reports.localization.catalog import _CATALOGS

    _CATALOGS.clear()
    _CATALOGS.update(snapshot)


def apply_investment_translation_overlay() -> None:
    """Merge evaluation fixture labels required for formal zh-CN investment render."""
    import json

    from cold_storage.modules.reports.domain.enums import ReportLocale
    from cold_storage.modules.reports.localization.catalog import _CATALOGS, TranslationCatalog

    with INVESTMENT_TRANSLATION_OVERLAY.open(encoding="utf-8") as handle:
        overlay = json.load(handle)
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


@contextmanager
def isolated_process_state() -> Iterator[None]:
    env_snapshot = _snapshot_env()
    singleton_snapshot = _snapshot_singletons()
    catalog_snapshot = _snapshot_catalogs()
    _restore_singletons({})
    try:
        apply_investment_translation_overlay()
        yield
    finally:
        _restore_env(env_snapshot)
        _restore_singletons(singleton_snapshot)
        _restore_catalogs(catalog_snapshot)


def configure_sqlite_env(db_path: Path, artifact_dir: Path) -> None:
    database_url = f"sqlite:///{db_path}"
    os.environ["SQLITE_PATH"] = str(db_path)
    os.environ["COLD_STORAGE_SQLITE_PATH"] = str(db_path)
    os.environ["DATABASE_BACKEND"] = "sqlite"
    os.environ["COLD_STORAGE_DATABASE_BACKEND"] = "sqlite"
    os.environ["DATABASE_URL"] = database_url
    os.environ["COLD_STORAGE_DATABASE_URL"] = database_url
    os.environ["COLD_STORAGE_STORAGE_DIR"] = str(artifact_dir)
    if "COLD_STORAGE_ENVIRONMENT_ID" not in os.environ:
        os.environ["COLD_STORAGE_ENVIRONMENT_ID"] = "local"


def configure_postgresql_env(database_url: str, artifact_dir: Path) -> None:
    os.environ.pop("SQLITE_PATH", None)
    os.environ.pop("COLD_STORAGE_SQLITE_PATH", None)
    os.environ["DATABASE_BACKEND"] = "postgresql"
    os.environ["COLD_STORAGE_DATABASE_BACKEND"] = "postgresql"
    os.environ["DATABASE_URL"] = database_url
    os.environ["COLD_STORAGE_DATABASE_URL"] = database_url
    os.environ["COLD_STORAGE_STORAGE_DIR"] = str(artifact_dir)
    if "COLD_STORAGE_ENVIRONMENT_ID" not in os.environ:
        os.environ["COLD_STORAGE_ENVIRONMENT_ID"] = "local"


def assert_reports_engine_dialect(expected: str) -> None:
    from cold_storage.bootstrap.dependencies import get_engine

    engine = get_engine()
    assert engine.dialect.name == expected, (
        f"reports get_engine() dialect {engine.dialect.name!r} != {expected!r}"
    )


def run_alembic_sqlite(db_path: Path) -> None:
    database_url = f"sqlite:///{db_path}"
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["COLD_STORAGE_SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = "sqlite"
    env["COLD_STORAGE_DATABASE_BACKEND"] = "sqlite"
    env["DATABASE_URL"] = database_url
    env["COLD_STORAGE_DATABASE_URL"] = database_url
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


def sqlite_database_url(tmp_path: Path) -> tuple[str, Path]:
    db_path = tmp_path / f"v08_p3_{uuid.uuid4().hex[:8]}.db"
    with isolated_process_state():
        run_alembic_sqlite(db_path)
    return f"sqlite:///{db_path}", db_path


def operator_seed(client: TestClient) -> tuple[Any, dict[str, dict[str, Any]]]:
    seeded = seed_v08_sample(client)
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = assert_canonical_five_persisted(calculations)
    return seeded, by_name


def assert_five_calculation_runs(engine: Any) -> None:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        calc_count = session.scalar(select(func.count()).select_from(CalculationRunRecord))
        assert calc_count == 5


def export_report_json(client: TestClient, report_id: str, revision_number: int) -> dict[str, Any]:
    exported = client.get(
        f"/api/v1/reports/{report_id}/export",
        params={"revision_number": revision_number, "format": "json"},
    )
    assert exported.status_code == 200, exported.text
    return cast(dict[str, Any], exported.json())


def assert_report_trust_loop_json(
    exported: dict[str, Any],
    *,
    expected_project_name: str,
    production_scheme_run_id: str,
    source_binding_id: str,
    combined_source_hash: str,
) -> None:
    content = exported.get("content") or exported
    project_summary = content.get("project_summary")
    assert isinstance(project_summary, dict), "project_summary must be present"
    assert project_summary.get("project_name") == expected_project_name

    scheme_comparison = content.get("scheme_comparison")
    assert isinstance(scheme_comparison, dict), "scheme_comparison must be present"
    authority = scheme_comparison.get("review_authority")
    assert isinstance(authority, dict), "scheme_comparison.review_authority must be present"
    assert authority.get("scheme_run_id") == production_scheme_run_id
    assert authority.get("source_binding_id") == source_binding_id
    assert authority.get("combined_source_hash") == combined_source_hash


def run_trust_loop_lifecycle(client: TestClient, seeded: Any) -> dict[str, Any]:
    report = client.post(
        "/api/v1/reports",
        json={
            "project_id": seeded.project_id,
            "project_version_id": seeded.project_version_id,
            "report_type": "cold_storage_concept_design",
        },
    )
    assert report.status_code == 200, report.text
    report_id = report.json()["report_id"]

    generated = client.post(f"/api/v1/reports/{report_id}/generate")
    assert generated.status_code == 200, generated.text
    revision_number = int(generated.json()["revision_number"])

    exported = export_report_json(client, report_id, revision_number)
    assert_report_trust_loop_json(
        exported,
        expected_project_name=seeded.project_name,
        production_scheme_run_id=seeded.production_scheme.run_id,
        source_binding_id=seeded.production_scheme.source_binding_id,
        combined_source_hash=seeded.production_scheme.combined_source_hash,
    )

    submit = client.post(f"/api/v1/reports/{report_id}/submit-review")
    assert submit.status_code == 200, submit.text

    reviewed = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    assert reviewed.status_code == 200, reviewed.text

    approved = client.post(f"/api/v1/reports/{report_id}/approve")
    assert approved.status_code == 200, approved.text

    formal_exports: list[dict[str, Any]] = []
    for locale in FORMAL_LOCALES:
        for export_format in FORMAL_FORMATS:
            response = client.post(
                f"/api/v1/reports/{report_id}/revisions/{revision_number}/render",
                json={
                    "format": export_format,
                    "template_version": TEMPLATE_VERSION,
                    "mode": "formal",
                    "locale": locale,
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            formal_exports.append(
                {
                    "locale": locale,
                    "format": export_format,
                    "artifact_id": body.get("artifact_id"),
                }
            )

    return {
        "report_id": report_id,
        "revision_number": revision_number,
        "formal_exports": formal_exports,
    }


def assert_untrusted_mark_reviewed_fail_closed(_client: TestClient, report_id: str) -> None:
    from cold_storage.bootstrap.app import create_app
    from cold_storage.modules.projects.infrastructure.database import (
        create_database_project_service,
    )

    service = create_database_project_service(os.environ["COLD_STORAGE_DATABASE_URL"])
    untrusted_app = create_app(project_service=service)
    untrusted_app.dependency_overrides[_get_actor] = lambda: UNTRUSTED_ACTOR
    with TestClient(untrusted_app) as untrusted_client:
        response = untrusted_client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
        assert response.status_code != 200, "untrusted system actor must not satisfy mark_reviewed"


@pytest.fixture()
def p3_manifest() -> dict[str, Any]:
    return load_manifest()
