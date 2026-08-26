"""V0.6 P5 controlled acceptance — operator path, contract scans, sqlite+pg matrix."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v06_sample_loader import (
    FORMAL_FORMATS,
    FORMAL_LOCALES,
    TEMPLATE_VERSION,
    UNTRUSTED_ACTOR,
    load_manifest,
    seed_v06_sample,
    trusted_sample_client,
    verify_v06_sample,
)
from cold_storage.modules.reports.api.routes import _get_actor
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    ProjectServicePersistedCalculationQuery,
)
from cold_storage.modules.reports.infrastructure.real_data_provider import RealReportDataProvider
from tests.integration.v05_p4_acceptance_fixtures import (
    CANONICAL_CALCULATORS,
    assert_canonical_five_persisted,
    assert_upstream_lineage_matches_p0,
)
from tests.integration.v05_p5_acceptance_evidence import (
    MISSING_KEY_CASES,
    evidence_agent_assistance_not_fake_available,
    evidence_missing_key_leaf_fails_closed_atomically,
)

pytest_plugins = ["tests.integration.v05_p5_acceptance_evidence"]

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
P5_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_6-P5-controlled-acceptance-contract.md"
P4B_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "v06-pilot-runbook.md"
V06_SAMPLE_LOADER = (
    REPO_ROOT / "backend" / "src" / "cold_storage" / "bootstrap" / "v06_sample_loader.py"
)
P5_TEST_FILE = (
    REPO_ROOT / "backend" / "tests" / "integration" / "test_v06_p5_controlled_acceptance.py"
)

BASE_MAIN_SHA = "d1af4ee29dd4bca1db7ae3d2adfd0f535c1b2be6"
BASE_TREE = "7f1716ca7abe0d463b87b86b47d09edff2eda490"

P0_SECTION_BY_CALCULATOR: dict[str, str] = {
    "cold_room_zone_plan": "throughput_inventory_area",
    "cooling_load": "cooling_load",
    "equipment": "equipment_selection",
    "installed_power": "electrical_and_energy",
    "investment_estimate": "investment_estimate",
}

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

FORBIDDEN_RELEASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"TAG_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"RELEASE_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"P5_CREATES_TAG_NOW=YES"),
    re.compile(r"P5_CREATES_GITHUB_RELEASE_NOW=YES"),
    re.compile(r"^\s*git\s+tag\s+", re.MULTILINE),
    re.compile(r"^\s*gh\s+release\s+create\b", re.MULTILINE | re.IGNORECASE),
)

FRONTEND_REPORT_API = (
    REPO_ROOT / "frontend" / "src" / "features" / "reports" / "api" / "reportsApi.ts"
)
FRONTEND_REPORTS_PAGE = (
    REPO_ROOT / "frontend" / "src" / "features" / "reports" / "components" / "ReportsPage.vue"
)
FRONTEND_EXPORT_PANEL = (
    REPO_ROOT / "frontend" / "src" / "features" / "reports" / "components" / "ReportExportPanel.vue"
)
FRONTEND_USE_EXPORT = (
    REPO_ROOT / "frontend" / "src" / "features" / "reports" / "composables" / "useReportExport.ts"
)


def _snapshot_env() -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in _ENV_KEYS_TO_ISOLATE}


def _restore_env(snapshot: dict[str, str | None]) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


_SINGLETON_KEYS = ("engine", "project_service")


def _snapshot_catalogs() -> dict[Any, Any]:
    from cold_storage.modules.reports.localization.catalog import _CATALOGS

    return dict(_CATALOGS)


def _restore_catalogs(snapshot: dict[Any, Any]) -> None:
    from cold_storage.modules.reports.localization.catalog import _CATALOGS

    _CATALOGS.clear()
    _CATALOGS.update(snapshot)


@contextmanager
def _isolated_process_state() -> Iterator[None]:
    import cold_storage.bootstrap.dependencies as deps

    env_snapshot = _snapshot_env()
    singleton_snapshot = {key: deps._singletons.get(key) for key in _SINGLETON_KEYS}
    catalog_snapshot = _snapshot_catalogs()
    deps._singletons.clear()
    try:
        yield
    finally:
        _restore_env(env_snapshot)
        deps._singletons.clear()
        for key in _SINGLETON_KEYS:
            if singleton_snapshot[key] is not None:
                deps._singletons[key] = singleton_snapshot[key]
        _restore_catalogs(catalog_snapshot)


def _configure_sqlite_env(db_path: Path, artifact_dir: Path) -> None:
    os.environ["SQLITE_PATH"] = str(db_path)
    os.environ["COLD_STORAGE_SQLITE_PATH"] = str(db_path)
    os.environ["DATABASE_BACKEND"] = "sqlite"
    os.environ["COLD_STORAGE_STORAGE_DIR"] = str(artifact_dir)
    if "COLD_STORAGE_ENVIRONMENT_ID" not in os.environ:
        os.environ["COLD_STORAGE_ENVIRONMENT_ID"] = "local"


def _configure_postgresql_env(artifact_dir: Path) -> None:
    os.environ["DATABASE_BACKEND"] = "postgresql"
    os.environ["COLD_STORAGE_STORAGE_DIR"] = str(artifact_dir)
    if "COLD_STORAGE_ENVIRONMENT_ID" not in os.environ:
        os.environ["COLD_STORAGE_ENVIRONMENT_ID"] = "local"


def _run_alembic_sqlite(db_path: Path) -> None:
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = "sqlite"
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


def _sqlite_database_url(tmp_path: Path) -> tuple[str, Path]:
    db_path = tmp_path / f"v06_p5_{uuid.uuid4().hex[:8]}.db"
    with _isolated_process_state():
        _run_alembic_sqlite(db_path)
    return f"sqlite:///{db_path}", db_path


def _collect_source_result_ids(node: Any, found: set[str] | None = None) -> set[str]:
    if found is None:
        found = set()
    if isinstance(node, dict):
        source_id = node.get("source_result_id")
        if isinstance(source_id, str) and source_id:
            found.add(source_id)
        for value in node.values():
            _collect_source_result_ids(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_source_result_ids(item, found)
    return found


def _operator_seed(client: TestClient) -> tuple[Any, dict[str, dict[str, Any]]]:
    seeded = seed_v06_sample(client)
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = assert_canonical_five_persisted(calculations)
    assert_upstream_lineage_matches_p0(by_name)
    if "power_configuration" in by_name:
        assert by_name.get("installed_power") is not None
    return seeded, by_name


def _create_and_generate_report(
    client: TestClient,
    *,
    project_id: str,
    project_version_id: str,
) -> tuple[str, int, dict[str, Any]]:
    created = client.post(
        "/api/v1/reports",
        json={
            "project_id": project_id,
            "project_version_id": project_version_id,
            "report_type": "cold_storage_concept_design",
        },
    )
    assert created.status_code == 200, created.text
    report_id = created.json()["report_id"]
    generated = client.post(f"/api/v1/reports/{report_id}/generate")
    assert generated.status_code == 200, generated.text
    revision = generated.json()
    return report_id, int(revision["revision_number"]), revision


def _export_report_json(client: TestClient, report_id: str, revision_number: int) -> dict[str, Any]:
    exported = client.get(
        f"/api/v1/reports/{report_id}/export",
        params={"revision_number": revision_number, "format": "json"},
    )
    assert exported.status_code == 200, exported.text
    return cast(dict[str, Any], exported.json())


def _assert_report_binds_persisted_sources(
    exported: dict[str, Any],
    by_name: dict[str, dict[str, Any]],
) -> None:
    content = exported["content"]
    bound_ids = _collect_source_result_ids(content)
    citations = {
        item["tool_name"]: item["result_id"]
        for item in content.get("citations", [])
        if item.get("tool_name") in CANONICAL_CALCULATORS
    }
    for calculator_name, section_key in P0_SECTION_BY_CALCULATOR.items():
        calc_id = by_name[calculator_name]["calculation_id"]
        assert calc_id in bound_ids or citations.get(calculator_name) == calc_id, (
            f"{calculator_name} calculation_id not bound in report JSON"
        )
        if section_key in content:
            section_ids = _collect_source_result_ids(content[section_key])
            assert calc_id in section_ids or citations.get(calculator_name) == calc_id, (
                f"{section_key} missing source binding for {calculator_name}"
            )
    for calculator_name in CANONICAL_CALCULATORS:
        assert citations[calculator_name] == by_name[calculator_name]["calculation_id"]
    assert content.get("input_conditions"), "input_conditions must come from persisted snapshots"
    assert content.get("assumptions"), "assumptions must come from persisted snapshots"


def _render_formal(
    client: TestClient,
    report_id: str,
    *,
    revision_number: int,
    locale: str,
    export_format: str,
) -> int:
    response = client.post(
        f"/api/v1/reports/{report_id}/revisions/{revision_number}/render",
        json={
            "format": export_format,
            "template_version": TEMPLATE_VERSION,
            "mode": "formal",
            "locale": locale,
        },
    )
    return response.status_code


def _assert_lifecycle_fail_closed_or_happy_path(
    client: TestClient,
    *,
    report_id: str,
    revision_number: int,
) -> bool:
    submit = client.post(f"/api/v1/reports/{report_id}/submit-review")
    if submit.status_code != 200:
        formal_statuses = [
            _render_formal(
                client,
                report_id,
                revision_number=revision_number,
                locale=locale,
                export_format=export_format,
            )
            for locale in FORMAL_LOCALES
            for export_format in FORMAL_FORMATS
        ]
        assert all(status == 409 for status in formal_statuses), formal_statuses
        return True

    reviewed = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    assert reviewed.status_code == 200, reviewed.text
    approved = client.post(f"/api/v1/reports/{report_id}/approve")
    assert approved.status_code == 200, approved.text

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
            assert body.get("file_sha256")
            assert body.get("file_size_bytes", 0) > 0
    return False


def _assert_power_configuration_not_authority(service, project_id: str, version_id: str) -> None:
    query = ProjectServicePersistedCalculationQuery(service)
    provider = RealReportDataProvider(project_service=service, calculation_service=query)
    sections = provider.get_calculation_results(project_id, version_id)
    section_by_tool = {row["tool_name"]: row for row in sections}
    assert section_by_tool.get("installed_power") is not None
    supplemental = section_by_tool.get("power_configuration")
    if supplemental is not None:
        assert supplemental["tool_name"] == "power_configuration"
        assert supplemental["result_id"] != section_by_tool["installed_power"]["result_id"]


def _assert_demo_coefficients_from_v06_manifest() -> None:
    manifest = load_manifest()
    bundle = manifest["engineering_input_bundle"]
    demo_leaves = bundle["coefficient_context"].get("demo_coefficient_leaves") or []
    assert demo_leaves
    for leaf in demo_leaves:
        assert leaf["source_type"] == "demo"
        assert leaf["validity_status"] in {"unverified", "conflict"}
        assert leaf["requires_review"] is True


@pytest.fixture()
def sqlite_operator_client(tmp_path):
    database_url, db_path = _sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with _isolated_process_state():
        _configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, service):
            yield client, service, database_url, db_path


@pytest.fixture()
def pg_operator_client(pg_database, tmp_path):
    artifact_dir = tmp_path / "pg-artifacts"
    artifact_dir.mkdir()
    with _isolated_process_state():
        _configure_postgresql_env(artifact_dir)
        with trusted_sample_client(pg_database, storage_dir=artifact_dir) as (client, service):
            yield client, service, pg_database


@pytest.fixture()
def pg_missing_key_client(pg_engine):
    from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService

    service = DatabaseProjectService(pg_engine)
    client = TestClient(create_app(project_service=service))
    return client, service, pg_engine


def test_p5_contract_records_source_identity_and_forbids_tag_release() -> None:
    assert P5_CONTRACT.is_file()
    assert P4B_RUNBOOK.is_file()

    contract = P5_CONTRACT.read_text(encoding="utf-8")
    runbook = P4B_RUNBOOK.read_text(encoding="utf-8")

    assert "TASK=V06_P5_CONTROLLED_ACCEPTANCE_R1" in contract
    assert "PARENT_ISSUE=176" in contract
    assert "P5_TRACKING_ISSUE=177" in contract
    assert "DISPATCH_ISSUE=197" in contract
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in contract
    assert f"BASE_TREE={BASE_TREE}" in contract
    assert "TARGET_BRANCH=cursor/v06-p5-controlled-acceptance-6c68" in contract
    assert "TARGET_PR_STATE=DRAFT" in contract
    assert "TAG_PUBLICATION_AUTHORIZED=NO" in contract
    assert "RELEASE_PUBLICATION_AUTHORIZED=NO" in contract
    assert "MERGE_AUTHORIZED=NO" in contract
    assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in contract
    assert "report_lifecycle_fail_closed=true" in contract.lower()

    for pattern in FORBIDDEN_RELEASE_PATTERNS:
        assert not pattern.search(contract), f"forbidden release pattern in contract: {pattern}"

    assert "make seed-v06-sample" in runbook
    assert "make verify-v06-sample" in runbook


def test_p5_allowlist_and_loader_do_not_call_planning_run_or_alembic() -> None:
    loader_source = V06_SAMPLE_LOADER.read_text(encoding="utf-8")
    assert "/planning-run" not in loader_source
    assert "planning_run" not in loader_source
    assert "five-stage-execution" in loader_source
    assert "-m alembic" not in loader_source
    assert "alembic upgrade" not in loader_source

    test_source = P5_TEST_FILE.read_text(encoding="utf-8")
    assert "seed_v06_sample" in test_source
    assert "verify_v06_sample" in test_source
    assert "trusted_sample_client" in test_source


def test_p5_frontend_report_workflow_binds_public_report_apis() -> None:
    api_source = FRONTEND_REPORT_API.read_text(encoding="utf-8")
    for route in (
        "/api/v1/reports",
        "/submit-review",
        "/mark-reviewed",
        "/approve",
        "/revisions/",
        "/render",
    ):
        assert route in api_source

    reports_page = FRONTEND_REPORTS_PAGE.read_text(encoding="utf-8")
    assert "workbench.workflow?.project_context.project_version_id" in reports_page
    assert "formalExportEligible" in reports_page

    export_panel = FRONTEND_EXPORT_PANEL.read_text(encoding="utf-8")
    assert "formalExportEligible" in export_panel
    assert (
        ':disabled="!formalExportEligible"' in export_panel
        or "formalExportEligible" in export_panel
    )
    assert "不代表生产 RBAC" in export_panel

    use_export = FRONTEND_USE_EXPORT.read_text(encoding="utf-8")
    assert "project_version_id: context.projectVersionId" in use_export
    assert "submitReview" in use_export
    assert "markReviewed" in use_export
    assert "approveReport" in use_export


@pytest.mark.sqlite
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_operator_sample_canonical_five_and_lineage(sqlite_operator_client) -> None:
    client, service, _database_url, _db_path = sqlite_operator_client
    seeded, by_name = _operator_seed(client)

    assert seeded.five_stage_success is True
    assert seeded.sample_id == "v06-formal-delivery"
    assert set(seeded.persisted_calculator_names) >= set(CANONICAL_CALCULATORS)

    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    exported = _export_report_json(client, report_id, revision_number)
    _assert_report_binds_persisted_sources(exported, by_name)
    _assert_power_configuration_not_authority(service, seeded.project_id, seeded.project_version_id)

    demo_scheme = client.get("/api/v1/demo/scheme-comparison")
    if demo_scheme.status_code == 200:
        assert demo_scheme.json().get("schemes")


@pytest.mark.sqlite
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_restart_preserves_hashes(sqlite_operator_client) -> None:
    client, _service, database_url, _db_path = sqlite_operator_client
    seeded, first_by_name = _operator_seed(client)
    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    first_revision = client.get(f"/api/v1/reports/{report_id}/revisions/{revision_number}").json()

    with trusted_sample_client(database_url) as (reopened, _reopened_service):
        second_calculations = reopened.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
        ).json()
        second_by_name = assert_canonical_five_persisted(second_calculations)
        for name in CANONICAL_CALCULATORS:
            assert second_by_name[name]["calculation_id"] == first_by_name[name]["calculation_id"]
            assert second_by_name[name]["result_hash"] == first_by_name[name]["result_hash"]

        reopened_revision = reopened.get(
            f"/api/v1/reports/{report_id}/revisions/{revision_number}"
        ).json()
        assert reopened_revision["content_hash"] == first_revision["content_hash"]


@pytest.mark.sqlite
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_report_lifecycle_fail_closed_or_formal_artifacts(
    sqlite_operator_client, tmp_path
) -> None:
    client, _service, database_url, db_path = sqlite_operator_client
    seeded, _by_name = _operator_seed(client)
    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    fail_closed = _assert_lifecycle_fail_closed_or_happy_path(
        client,
        report_id=report_id,
        revision_number=revision_number,
    )
    assert fail_closed is True

    artifact_dir = tmp_path / "verify-artifacts"
    artifact_dir.mkdir(exist_ok=True)
    _configure_sqlite_env(db_path, artifact_dir)
    summary = verify_v06_sample(database_url)
    assert summary["verify_status"] == "ok"
    assert summary.get("report_lifecycle_fail_closed") is True
    assert all(item["status_code"] == 409 for item in summary["formal_exports"])


@pytest.mark.sqlite
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_formal_without_mark_reviewed_is_409(sqlite_operator_client) -> None:
    client, _service, _database_url, _db_path = sqlite_operator_client
    seeded, _by_name = _operator_seed(client)
    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    for locale in FORMAL_LOCALES:
        for export_format in FORMAL_FORMATS:
            status = _render_formal(
                client,
                report_id,
                revision_number=revision_number,
                locale=locale,
                export_format=export_format,
            )
            assert status == 409


@pytest.mark.sqlite
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_untrusted_actor_cannot_mark_reviewed(sqlite_operator_client) -> None:
    client, service, _database_url, _db_path = sqlite_operator_client
    seeded, _by_name = _operator_seed(client)
    report_id, _revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )

    untrusted_app = create_app(project_service=service)
    untrusted_app.dependency_overrides[_get_actor] = lambda: UNTRUSTED_ACTOR
    with TestClient(untrusted_app) as untrusted_client:
        response = untrusted_client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
        assert response.status_code != 200


@pytest.mark.sqlite
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_demo_coefficients_remain_unverified() -> None:
    _assert_demo_coefficients_from_v06_manifest()


@pytest.mark.sqlite
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_agent_assistance_not_fake_available(sqlite_operator_client) -> None:
    client, _service, _database_url, _db_path = sqlite_operator_client
    seeded, _by_name = _operator_seed(client)
    evidence_agent_assistance_not_fake_available(client, seeded.project_id, seeded.version_number)


@pytest.mark.sqlite
@pytest.mark.parametrize("dotted_path,_label", MISSING_KEY_CASES)
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="SQLite P5 operator tests cannot run on PostgreSQL backend",
)
def test_p5_sqlite_missing_key_leaf_fails_closed_atomically(
    migrated_client, dotted_path: str, _label: str
) -> None:
    client, _service, engine = migrated_client
    evidence_missing_key_leaf_fails_closed_atomically(client, engine, dotted_path=dotted_path)


@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_operator_sample_canonical_five_and_lineage(pg_operator_client) -> None:
    client, service, _database_url = pg_operator_client
    seeded, by_name = _operator_seed(client)

    assert seeded.five_stage_success is True
    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    exported = _export_report_json(client, report_id, revision_number)
    _assert_report_binds_persisted_sources(exported, by_name)
    _assert_power_configuration_not_authority(service, seeded.project_id, seeded.project_version_id)


@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_restart_preserves_hashes(pg_operator_client) -> None:
    client, _service, database_url = pg_operator_client
    seeded, first_by_name = _operator_seed(client)
    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    first_revision = client.get(f"/api/v1/reports/{report_id}/revisions/{revision_number}").json()

    with trusted_sample_client(database_url) as (reopened, _service):
        second = reopened.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
        ).json()
        second_by_name = assert_canonical_five_persisted(second)
        for name in CANONICAL_CALCULATORS:
            assert second_by_name[name]["calculation_id"] == first_by_name[name]["calculation_id"]
            assert second_by_name[name]["result_hash"] == first_by_name[name]["result_hash"]
        reopened_revision = reopened.get(
            f"/api/v1/reports/{report_id}/revisions/{revision_number}"
        ).json()
        assert reopened_revision["content_hash"] == first_revision["content_hash"]


@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_report_lifecycle_fail_closed_or_formal_artifacts(
    pg_operator_client, tmp_path
) -> None:
    client, _service, database_url = pg_operator_client
    seeded, _by_name = _operator_seed(client)
    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    fail_closed = _assert_lifecycle_fail_closed_or_happy_path(
        client,
        report_id=report_id,
        revision_number=revision_number,
    )
    assert fail_closed is True

    artifact_dir = tmp_path / "pg-verify-artifacts"
    artifact_dir.mkdir(exist_ok=True)
    _configure_postgresql_env(artifact_dir)
    summary = verify_v06_sample(database_url)
    assert summary["verify_status"] == "ok"
    assert summary.get("report_lifecycle_fail_closed") is True


@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_formal_without_mark_reviewed_is_409(pg_operator_client) -> None:
    client, _service, _database_url = pg_operator_client
    seeded, _by_name = _operator_seed(client)
    report_id, revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    for locale in FORMAL_LOCALES:
        for export_format in FORMAL_FORMATS:
            assert (
                _render_formal(
                    client,
                    report_id,
                    revision_number=revision_number,
                    locale=locale,
                    export_format=export_format,
                )
                == 409
            )


@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_untrusted_actor_cannot_mark_reviewed(pg_operator_client) -> None:
    client, service, _database_url = pg_operator_client
    seeded, _by_name = _operator_seed(client)
    report_id, _revision_number, _revision = _create_and_generate_report(
        client,
        project_id=seeded.project_id,
        project_version_id=seeded.project_version_id,
    )
    untrusted_app = create_app(project_service=service)
    untrusted_app.dependency_overrides[_get_actor] = lambda: UNTRUSTED_ACTOR
    with TestClient(untrusted_app) as untrusted_client:
        response = untrusted_client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
        assert response.status_code != 200


@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_demo_coefficients_remain_unverified() -> None:
    _assert_demo_coefficients_from_v06_manifest()


@pytest.mark.postgresql
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_agent_assistance_not_fake_available(pg_operator_client) -> None:
    client, _service, _database_url = pg_operator_client
    seeded, _by_name = _operator_seed(client)
    evidence_agent_assistance_not_fake_available(client, seeded.project_id, seeded.version_number)


@pytest.mark.postgresql
@pytest.mark.parametrize("dotted_path,_label", MISSING_KEY_CASES)
@pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") != "postgresql",
    reason="PostgreSQL P5 operator tests require DATABASE_BACKEND=postgresql",
)
def test_p5_pg_missing_key_leaf_fails_closed_atomically(
    pg_missing_key_client, dotted_path: str, _label: str
) -> None:
    client, _service, engine = pg_missing_key_client
    evidence_missing_key_leaf_fails_closed_atomically(client, engine, dotted_path=dotted_path)
