"""V0.8 P4 controlled acceptance integration tests (SQLite).

Proves P0 §10 global acceptance gates for the operator-minimal five-KEY path on
unmodified ``create_app`` using the frozen ``v08-process-input`` sample. Shared
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
from cold_storage.bootstrap.v08_sample_loader import (
    FORMAL_FORMATS,
    FORMAL_LOCALES,
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
from tests.integration.v08_p3_operator_fixtures import (
    assert_report_trust_loop_json,
    assert_untrusted_mark_reviewed_fail_closed,
    configure_sqlite_env,
    export_report_json,
    isolated_process_state,
    operator_process_input_from_manifest,
    operator_seed,
    run_trust_loop_lifecycle,
    sqlite_database_url,
)

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "P4 SQLite integration tests require DATABASE_BACKEND != postgresql",
        allow_module_level=True,
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
P4_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_8-P4-controlled-acceptance-contract.md"
P0_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_8-P0-operator-minimal-input-contract.md"
P6_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_7-P6-aily-integration-boundary-contract.md"
BASE_MAIN_SHA = "489b8941205a74d24b0c2df50346d5a6809d5d3c"

OPERATOR_KEY_LEAVES: frozenset[str] = frozenset(
    {
        "daily_inbound_mass_kg",
        "working_time_h_per_day",
        "finished_storage_days",
        "packaging_storage_days",
        "precooling_required_ratio",
    }
)

OPERATOR_KEY_FIELD_KEYS: tuple[str, ...] = (
    "zonePlanning.dailyInboundMassKg",
    "zonePlanning.workingTimeHPerDay",
    "zonePlanning.finishedStorageDays",
    "zonePlanning.packagingStorageDays",
    "zonePlanning.precoolingRequiredRatio",
)

MISSING_OPERATOR_KEY_CASES: tuple[tuple[str, str], ...] = (
    ("daily_inbound_mass_kg", "daily_inbound_mass_kg"),
    ("precooling_required_ratio", "precooling_required_ratio"),
)

FULL_BUNDLE_COMPAT_TEST_FILES: tuple[Path, ...] = (
    REPO_ROOT / "backend/tests/integration/test_v05_p4_five_stage_acceptance_sqlite.py",
    REPO_ROOT / "backend/tests/integration/test_v05_p4_five_stage_acceptance_postgresql.py",
    REPO_ROOT / "backend/tests/integration/test_v05_p5_controlled_acceptance_sqlite.py",
    REPO_ROOT / "backend/tests/integration/test_v05_p5_controlled_acceptance_postgresql.py",
    REPO_ROOT / "backend/tests/integration/test_v06_p5_controlled_acceptance.py",
    REPO_ROOT / "backend/tests/integration/test_v07_p7_controlled_acceptance_sqlite.py",
    REPO_ROOT / "backend/tests/integration/test_v07_p7_controlled_acceptance_postgresql.py",
)

FORBIDDEN_RELEASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"TAG_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"RELEASE_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"P4_CREATES_TAG_NOW=YES"),
    re.compile(r"P4_CREATES_GITHUB_RELEASE_NOW=YES"),
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
            "idempotency_key": idempotency_key or f"v08-p4-missing-{uuid.uuid4().hex[:8]}",
        },
    )
    body = response.json()
    assert isinstance(body, dict)
    return body


def assert_demo_catalog_leaves_remain_unverified(by_name: dict[str, dict[str, Any]]) -> None:
    """P4-G-08: demo/catalog provenance stays unverified after operator-minimal success."""
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


def run_p4_controlled_acceptance(client: TestClient, seeded: Any, service: Any) -> dict[str, Any]:
    calculations = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
    ).json()
    by_name = calculations_by_name(calculations)
    assert_canonical_five_persisted(list(by_name.values()))
    assert_upstream_lineage_matches_p0(by_name)
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

    lifecycle = run_trust_loop_lifecycle(client, seeded)
    exported = export_report_json(client, lifecycle["report_id"], lifecycle["revision_number"])
    assert_report_trust_loop_json(
        exported,
        expected_project_name=seeded.project_name,
        production_scheme_run_id=production_scheme.run_id,
        source_binding_id=production_scheme.source_binding_id,
        combined_source_hash=production_scheme.combined_source_hash,
    )
    assert_report_reads_persisted_without_recalc(exported, by_name)

    assert len(lifecycle["formal_exports"]) == len(FORMAL_LOCALES) * len(FORMAL_FORMATS)
    for item in lifecycle["formal_exports"]:
        assert item.get("artifact_id")

    assert_untrusted_mark_reviewed_fail_closed(client, lifecycle["report_id"])
    return lifecycle


def test_v08_p4_contract_exists() -> None:
    assert P4_CONTRACT.is_file()
    text = P4_CONTRACT.read_text(encoding="utf-8")
    assert "TASK=V08_P4_CONTROLLED_ACCEPTANCE_R1" in text
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in text
    assert "TARGET_BRANCH=cursor/v08-p4-controlled-acceptance-6c68" in text
    assert "TARGET_PR_STATE=DRAFT" in text
    assert "TAG_PUBLICATION_AUTHORIZED=NO" in text
    assert "RELEASE_PUBLICATION_AUTHORIZED=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "READY_AUTHORIZED=NO" in text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in text
    assert "P4_OWNS_MAKEFILE=NO" in text
    assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text
    for pattern in FORBIDDEN_RELEASE_PATTERNS:
        assert not pattern.search(text), f"forbidden release pattern in contract: {pattern}"


def test_v08_p4_contract_allowlist() -> None:
    text = P4_CONTRACT.read_text(encoding="utf-8")
    assert "docs/tasks/V0_8-P4-controlled-acceptance-contract.md" in text
    assert "backend/tests/integration/test_v08_p4_controlled_acceptance_sqlite.py" in text
    assert "backend/tests/integration/test_v08_p4_controlled_acceptance_postgresql.py" in text


def test_v08_p4_contract_records_aily_boundary() -> None:
    assert P6_CONTRACT.is_file()
    assert P0_CONTRACT.is_file()
    p6_text = P6_CONTRACT.read_text(encoding="utf-8")
    p0_text = P0_CONTRACT.read_text(encoding="utf-8")
    p4_text = P4_CONTRACT.read_text(encoding="utf-8")
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p6_text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p0_text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p4_text


def test_v08_p4_contract_records_issue_evidence_only() -> None:
    text = P4_CONTRACT.read_text(encoding="utf-8")
    assert "#11" in text
    assert "#13" in text
    assert "#17" in text
    assert "#176" in text
    assert "#20" in text
    assert "P4_CLOSES_ISSUES_NOW=NO" in text
    assert "do not close via `gh`" in text.lower() or "do not close via gh" in text.lower()


def test_v08_p4_manifest_has_five_operator_keys_only() -> None:
    manifest = load_manifest()
    assert manifest["sample_id"] == "v08-process-input"
    assert "engineering_input_bundle" not in manifest
    operator_input = manifest["operator_process_input"]
    assert operator_input["schema_id"] == "OperatorProcessInputV1"
    assert operator_input["schema_version"] == "1.0.0"
    zone_inputs = operator_input["zone_planning_inputs"]
    assert set(zone_inputs) == OPERATOR_KEY_LEAVES


def test_v08_p4_vue_operator_workbench_file_scan() -> None:
    form_path = (
        REPO_ROOT / "frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue"
    )
    store_path = REPO_ROOT / "frontend/src/stores/fiveStageExecution.ts"
    p2_arch_path = (
        REPO_ROOT
        / "frontend/src/features/five-stage/architecture/test_v08_p2_five_key_operator_form.test.ts"
    )
    project_page_path = REPO_ROOT / "frontend/src/features/project/components/ProjectPage.vue"
    form_model_path = REPO_ROOT / "frontend/src/features/five-stage/model/engineeringInputForm.ts"

    form_content = form_path.read_text(encoding="utf-8")
    field_key_matches = [
        match.group(1) for match in re.finditer(r'field-key="([^"]+)"', form_content)
    ]
    assert field_key_matches == list(OPERATOR_KEY_FIELD_KEYS)

    store_content = store_path.read_text(encoding="utf-8")
    assert "operator_process_input" in store_content
    assert "engineering_input_bundle" not in store_content

    assert p2_arch_path.is_file()

    project_page_content = project_page_path.read_text(encoding="utf-8")
    assert "V0.4 遗留路径 (planning-run)" in project_page_content
    assert "不是 V0.8 五阶段权威输入" in project_page_content

    form_model_content = form_model_path.read_text(encoding="utf-8")
    assert "export function buildEngineeringInputBundle" in form_model_content


def test_v08_p4_full_bundle_compat_test_files_exist() -> None:
    missing = [path for path in FULL_BUNDLE_COMPAT_TEST_FILES if not path.is_file()]
    assert not missing, f"missing full-bundle compat test files: {missing}"


@pytest.mark.sqlite
def test_v08_p4_sqlite_controlled_acceptance(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, service):
            seeded, _by_name = operator_seed(client)
            run_p4_controlled_acceptance(client, seeded, service)


@pytest.mark.sqlite
@pytest.mark.parametrize(
    "leaf_name,_label",
    MISSING_OPERATOR_KEY_CASES,
    ids=[case[1] for case in MISSING_OPERATOR_KEY_CASES],
)
def test_v08_p4_sqlite_missing_operator_key_fail_closed(
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
                    "name": f"V08-P4 missing key {uuid.uuid4().hex[:8]}",
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
def test_v08_p4_sqlite_demo_catalog_leaves_remain_unverified(tmp_path: Path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, _service):
            _seeded, by_name = operator_seed(client)
            assert_demo_catalog_leaves_remain_unverified(by_name)
