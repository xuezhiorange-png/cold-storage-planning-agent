"""V0.9 P7 controlled acceptance integration tests (SQLite).

Proves P0 §11 global acceptance gates for the operator five-KEY path on
unmodified ``create_app`` using the frozen ``v09-process-input`` sample. Shared
assertion helpers in this module are imported by the PostgreSQL counterpart.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v09_sample_loader import (
    RENDER_FORMATS,
    RENDER_LOCALES,
    TEMPLATE_VERSION,
    V09_FORBIDDEN_MANIFEST_KEYS,
    V09_OPERATOR_KEY_LEAVES,
    load_manifest,
    trusted_sample_client,
)
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from tests.integration.test_v07_p7_controlled_acceptance_sqlite import (
    assert_production_scheme_source_mode,
    assert_report_reads_persisted_without_recalc,
    assert_workflow_result_hash_parity,
)
from tests.integration.v05_p4_acceptance_fixtures import (
    assert_canonical_five_persisted,
    assert_upstream_lineage_matches_p0,
    calculations_by_name,
)
from tests.integration.v07_p2_consistency_evidence import assert_zero_canonical_rows
from tests.integration.v09_p6_operator_fixtures import (
    assert_report_trust_loop_json,
    assert_untrusted_mark_reviewed_fail_closed,
    assert_v09_zone_snapshot,
    configure_sqlite_env,
    export_report_json,
    isolated_process_state,
    operator_process_input_from_manifest,
    operator_seed,
    run_draft_exports,
    sqlite_database_url,
)

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "P7 SQLite integration tests require DATABASE_BACKEND != postgresql",
        allow_module_level=True,
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
P7_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P7-controlled-acceptance-contract.md"
P0_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P0-version-contract.md"
P6_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P6-operator-sample-runbook-contract.md"
BASE_MAIN_SHA = "c10c7e29a7a4f084ba2ac161c9d0fff8402a72d0"

OPERATOR_KEY_FIELD_KEYS: tuple[str, ...] = (
    "zonePlanning.dailyInboundMassKg",
    "zonePlanning.finishedStorageDays",
    "zonePlanning.frozenStorageDays",
    "zonePlanning.mainPackagingStorageDays",
    "zonePlanning.auxiliaryPackagingStorageDays",
)

MISSING_OPERATOR_KEY_CASES: tuple[tuple[str, str], ...] = (
    ("daily_inbound_mass_kg", "daily_inbound_mass_kg"),
    ("frozen_storage_days", "frozen_storage_days"),
)

FULL_BUNDLE_COMPAT_TEST_FILES: tuple[Path, ...] = (
    REPO_ROOT / "backend/tests/integration/test_v05_p4_five_stage_acceptance_sqlite.py",
    REPO_ROOT / "backend/tests/integration/test_v05_p4_five_stage_acceptance_postgresql.py",
    REPO_ROOT / "backend/tests/integration/test_v05_p5_controlled_acceptance_sqlite.py",
    REPO_ROOT / "backend/tests/integration/test_v05_p5_controlled_acceptance_postgresql.py",
    REPO_ROOT / "backend/tests/integration/test_v06_p5_controlled_acceptance.py",
    REPO_ROOT / "backend/tests/integration/test_v07_p7_controlled_acceptance_sqlite.py",
    REPO_ROOT / "backend/tests/integration/test_v07_p7_controlled_acceptance_postgresql.py",
    REPO_ROOT / "backend/tests/integration/test_v08_p4_controlled_acceptance_sqlite.py",
    REPO_ROOT / "backend/tests/integration/test_v08_p4_controlled_acceptance_postgresql.py",
)

FORBIDDEN_RELEASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"TAG_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"RELEASE_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"P7_CREATES_TAG_NOW=YES"),
    re.compile(r"P7_CREATES_GITHUB_RELEASE_NOW=YES"),
    re.compile(r"^\s*git\s+tag\s+", re.MULTILINE),
    re.compile(r"^\s*gh\s+release\s+create\b", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*gh\s+issue\s+close\b", re.MULTILINE | re.IGNORECASE),
)


def execute_missing_operator_key(
    client: TestClient,
    *,
    project_id: str,
    version_number: int,
    leaf_name: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest()
    payload = operator_process_input_from_manifest(manifest)
    payload["zone_planning_inputs"].pop(leaf_name)
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={
            "operator_process_input": payload,
            "idempotency_key": idempotency_key or f"v09-p7-missing-{uuid.uuid4().hex[:8]}",
        },
    )
    body = response.json()
    assert isinstance(body, dict)
    return body


def assert_v09_zone_calculator_version(by_name: dict[str, dict[str, Any]]) -> None:
    zone_row = by_name["cold_room_zone_plan"]
    version = zone_row.get("calculator_version")
    if version is not None:
        assert version == "1.0.0"


def assert_demo_catalog_leaves_remain_unverified(by_name: dict[str, dict[str, Any]]) -> None:
    """P7-G-11: demo/catalog provenance stays unverified after operator-minimal success."""
    manifest = load_manifest()
    assert "engineering_input_bundle" not in manifest
    assert "demo_coefficient_leaves" not in manifest

    zone_row = by_name["cold_room_zone_plan"]
    assert zone_row.get("requires_review") is True, "zone stage must require review (demo catalog)"

    demo_or_coeff_coefficients: list[dict[str, Any]] = []
    for row in by_name.values():
        for coeff in row.get("coefficients") or []:
            if not isinstance(coeff, dict):
                continue
            if coeff.get("source_type") in {"demo", "coefficient"}:
                demo_or_coeff_coefficients.append(coeff)

    assert demo_or_coeff_coefficients, (
        "at least one persisted coefficient must remain demo/catalog sourced"
    )
    for coeff in demo_or_coeff_coefficients:
        source_type = coeff.get("source_type")
        assert source_type in {"demo", "coefficient"}
        assert coeff.get("requires_review") is True
        validity_status = coeff.get("validity_status")
        if validity_status is not None:
            assert validity_status in {"unverified", "conflict"}
        status = coeff.get("status")
        if status is not None and status not in {source_type, "demo", "coefficient"}:
            assert status in {"unverified", "conflict"}


def assert_formal_export_fail_closed_before_review(
    client: TestClient,
    report_id: str,
    revision_number: int,
) -> None:
    """P7-G-08: formal render must fail before mark_reviewed / approve."""
    for locale in RENDER_LOCALES:
        for export_format in RENDER_FORMATS:
            response = client.post(
                f"/api/v1/reports/{report_id}/revisions/{revision_number}/render",
                json={
                    "format": export_format,
                    "template_version": TEMPLATE_VERSION,
                    "mode": "formal",
                    "locale": locale,
                },
            )
            assert response.status_code != 200, (
                f"formal {locale}/{export_format} must fail-closed before review: "
                f"{response.status_code} {response.text}"
            )


def run_p7_controlled_acceptance(client: TestClient, seeded: Any, service: Any) -> dict[str, Any]:
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = calculations_by_name(calculations)
    assert_canonical_five_persisted(list(by_name.values()))
    assert_upstream_lineage_matches_p0(by_name)
    assert_v09_zone_snapshot(by_name)
    assert_v09_zone_calculator_version(by_name)
    assert_demo_catalog_leaves_remain_unverified(by_name)

    production_scheme = seeded.production_scheme
    assert production_scheme.success is True
    assert production_scheme.run_id
    assert_production_scheme_source_mode(
        service,
        run_id=production_scheme.run_id,
        source_binding_id=production_scheme.source_binding_id,
        combined_source_hash=production_scheme.combined_source_hash,
    )

    assert_workflow_result_hash_parity(
        client,
        project_id=seeded.project_id,
        version_number=seeded.version_number,
        by_name=by_name,
    )

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
        production_scheme_run_id=production_scheme.run_id,
        source_binding_id=production_scheme.source_binding_id,
        combined_source_hash=production_scheme.combined_source_hash,
    )
    assert_report_reads_persisted_without_recalc(exported, by_name)

    draft_exports = run_draft_exports(client, report_id, revision_number)
    assert len(draft_exports) == len(RENDER_LOCALES) * len(RENDER_FORMATS)

    assert_formal_export_fail_closed_before_review(client, report_id, revision_number)

    submit = client.post(f"/api/v1/reports/{report_id}/submit-review")
    assert submit.status_code == 200, submit.text

    reviewed = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    assert reviewed.status_code == 200, reviewed.text

    approved = client.post(f"/api/v1/reports/{report_id}/approve")
    assert approved.status_code == 200, approved.text

    formal_exports: list[dict[str, Any]] = []
    for locale in RENDER_LOCALES:
        for export_format in RENDER_FORMATS:
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

    assert len(formal_exports) == len(RENDER_LOCALES) * len(RENDER_FORMATS)
    for item in formal_exports:
        assert item.get("artifact_id")

    assert_untrusted_mark_reviewed_fail_closed(client, report_id)
    return {
        "report_id": report_id,
        "revision_number": revision_number,
        "draft_exports": draft_exports,
        "formal_exports": formal_exports,
    }


def test_v09_p7_contract_exists() -> None:
    assert P7_CONTRACT.is_file()
    text = P7_CONTRACT.read_text(encoding="utf-8")
    assert "TASK=V09_P7_CONTROLLED_ACCEPTANCE_R1" in text
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in text
    assert "TARGET_BRANCH=cursor/v09-p7-controlled-acceptance-6c68" in text
    assert "TARGET_PR_STATE=DRAFT" in text
    assert "TAG_PUBLICATION_AUTHORIZED=NO" in text
    assert "RELEASE_PUBLICATION_AUTHORIZED=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "READY_AUTHORIZED=NO" in text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in text
    assert "P7_OWNS_MAKEFILE=NO" in text
    assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text
    for pattern in FORBIDDEN_RELEASE_PATTERNS:
        assert not pattern.search(text), f"forbidden release pattern in contract: {pattern}"


def test_v09_p7_contract_allowlist() -> None:
    text = P7_CONTRACT.read_text(encoding="utf-8")
    assert "docs/tasks/V0_9-P7-controlled-acceptance-contract.md" in text
    assert "backend/tests/integration/test_v09_p7_controlled_acceptance_sqlite.py" in text
    assert "backend/tests/integration/test_v09_p7_controlled_acceptance_postgresql.py" in text


def test_v09_p7_contract_records_aily_boundary() -> None:
    assert P6_CONTRACT.is_file()
    assert P0_CONTRACT.is_file()
    p6_text = P6_CONTRACT.read_text(encoding="utf-8")
    p0_text = P0_CONTRACT.read_text(encoding="utf-8")
    p7_text = P7_CONTRACT.read_text(encoding="utf-8")
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p6_text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p0_text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p7_text


def test_v09_p7_contract_records_issue_evidence_only() -> None:
    text = P7_CONTRACT.read_text(encoding="utf-8")
    assert "#11" in text
    assert "#13" in text
    assert "#17" in text
    assert "#176" in text
    assert "#20" in text
    assert "P7_CLOSES_ISSUES_NOW=NO" in text
    assert "do not close via `gh`" in text.lower() or "do not close via gh" in text.lower()


def test_v09_p7_manifest_has_five_operator_keys_only() -> None:
    manifest = load_manifest()
    assert manifest["sample_id"] == "v09-process-input"
    for forbidden_key in V09_FORBIDDEN_MANIFEST_KEYS:
        assert forbidden_key not in manifest
    operator_input = manifest["operator_process_input"]
    assert operator_input["schema_id"] == "OperatorProcessInputV1"
    assert operator_input["schema_version"] == "1.1.0"
    zone_inputs = operator_input["zone_planning_inputs"]
    assert set(zone_inputs) == V09_OPERATOR_KEY_LEAVES


def test_v09_p7_vue_operator_workbench_file_scan() -> None:
    form_path = (
        REPO_ROOT / "frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue"
    )
    store_path = REPO_ROOT / "frontend/src/stores/fiveStageExecution.ts"
    calculations_page_path = (
        REPO_ROOT / "frontend/src/features/calculations/components/CalculationsPage.vue"
    )
    zone_results_path = (
        REPO_ROOT / "frontend/src/features/calculations/components/ZoneResultsTable.vue"
    )
    report_export_path = REPO_ROOT / "frontend/src/features/reports/composables/useReportExport.ts"
    report_panel_path = REPO_ROOT / "frontend/src/features/reports/components/ReportExportPanel.vue"
    workbench_layout_path = REPO_ROOT / "frontend/src/features/workbench/WorkbenchLayout.vue"

    form_content = form_path.read_text(encoding="utf-8")
    field_key_matches = [
        match.group(1) for match in re.finditer(r'field-key="([^"]+)"', form_content)
    ]
    assert field_key_matches == list(OPERATOR_KEY_FIELD_KEYS)
    for removed_key in (
        "workingTimeHPerDay",
        "precoolingRequiredRatio",
        "packagingStorageDays",
    ):
        assert f'field-key="zonePlanning.{removed_key}"' not in form_content

    store_content = store_path.read_text(encoding="utf-8")
    assert "operator_process_input" in store_content
    assert "engineering_input_bundle" not in store_content

    calculations_content = calculations_page_path.read_text(encoding="utf-8")
    assert "暂无完整五阶段计算结果。" in calculations_content
    assert "OperatorProcessInputV1" in calculations_content
    assert "EngineeringInputBundleV1" not in calculations_content

    zone_results_content = zone_results_path.read_text(encoding="utf-8")
    assert "1.56" not in zone_results_content
    assert "n ×" not in zone_results_content

    report_export_content = report_export_path.read_text(encoding="utf-8")
    assert "DRAFT_EXPORT_STATUSES" in report_export_content
    assert "'draft'" in report_export_content
    assert "'generated'" in report_export_content
    assert "FORMAL_EXPORT_STATUSES" in report_export_content
    assert "'approved'" in report_export_content
    assert "'archived'" in report_export_content
    assert "DRAFT_EXPORT_POLICY_COPY" in report_export_content

    report_panel_content = report_panel_path.read_text(encoding="utf-8")
    assert "DRAFT_EXPORT_POLICY_COPY" in report_panel_content

    workbench_content = workbench_layout_path.read_text(encoding="utf-8")
    body_block = re.search(
        r"\.workbench-layout__body\s*\{([^}]+)\}",
        workbench_content,
        re.DOTALL,
    )
    assert body_block is not None
    body_styles = body_block.group(1)
    assert "display: grid" in body_styles or "display:grid" in body_styles.replace(" ", "")
    assert "grid-template-columns" in body_styles


def test_v09_p7_full_bundle_compat_test_files_exist() -> None:
    missing = [path for path in FULL_BUNDLE_COMPAT_TEST_FILES if not path.is_file()]
    assert not missing, f"missing full-bundle compat test files: {missing}"


@pytest.mark.sqlite
def test_v09_p7_sqlite_controlled_acceptance(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, service):
            seeded, _by_name = operator_seed(client)
            run_p7_controlled_acceptance(client, seeded, service)


@pytest.mark.sqlite
@pytest.mark.parametrize(
    "leaf_name,_label",
    MISSING_OPERATOR_KEY_CASES,
    ids=[case[1] for case in MISSING_OPERATOR_KEY_CASES],
)
def test_v09_p7_sqlite_missing_operator_key_fail_closed(
    tmp_path: Path,
    leaf_name: str,
    _label: str,
) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        service = create_database_project_service(database_url)
        with TestClient(create_app(project_service=service)) as client:
            created = client.post(
                "/api/v1/projects",
                json={
                    "name": f"V09-P7 missing key {uuid.uuid4().hex[:8]}",
                    "location": "山东",
                    "product_category": "blueberry",
                },
            )
            assert created.status_code == 200, created.text
            project_id = created.json()["id"]
            version_number = created.json()["current_version_number"]
            version_id = client.get(
                f"/api/v1/projects/{project_id}/versions/{version_number}"
            ).json()["id"]

            response = execute_missing_operator_key(
                client,
                project_id=project_id,
                version_number=version_number,
                leaf_name=leaf_name,
            )
            assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

            with sessionmaker(bind=service.engine, expire_on_commit=False)() as session:
                assert_zero_canonical_rows(session, version_id)


@pytest.mark.sqlite
def test_v09_p7_sqlite_demo_catalog_leaves_remain_unverified(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, _service):
            _seeded, by_name = operator_seed(client)
            assert_demo_catalog_leaves_remain_unverified(by_name)
