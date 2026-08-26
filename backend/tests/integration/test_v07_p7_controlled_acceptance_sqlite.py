"""V0.7 P7 controlled acceptance integration tests (SQLite).

Proves P0 §10 global acceptance gates on unmodified ``create_app`` using the
frozen ``v07-trust-loop`` operator sample. Shared assertion helpers in this
module are imported by the PostgreSQL counterpart.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v07_sample_loader import (
    FORMAL_FORMATS,
    FORMAL_LOCALES,
    load_manifest,
    trusted_sample_client,
)
from cold_storage.modules.orchestration.domain.consumer_bindings import CANONICAL_STAGE_ORDER
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord
from tests.integration.v05_p4_acceptance_fixtures import (
    CANONICAL_CALCULATORS,
    assert_canonical_five_persisted,
    assert_upstream_lineage_matches_p0,
    calculations_by_name,
)
from tests.integration.v07_p2_consistency_evidence import (
    assert_zero_canonical_rows,
    execute_missing_key_bundle,
)
from tests.integration.v07_p2_numeric_projection_map import calculator_for_stage
from tests.integration.v07_p5_operator_fixtures import (
    assert_report_trust_loop_json,
    assert_untrusted_mark_reviewed_fail_closed,
    configure_sqlite_env,
    export_report_json,
    isolated_process_state,
    operator_seed,
    run_trust_loop_lifecycle,
    sqlite_database_url,
)

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "P7 SQLite integration tests require DATABASE_BACKEND != postgresql",
        allow_module_level=True,
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
P7_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_7-P7-controlled-acceptance-contract.md"
P6_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_7-P6-aily-integration-boundary-contract.md"
BASE_MAIN_SHA = "c01d35e393effbd33db23b660d46899c10d3f459"

P0_SECTION_BY_CALCULATOR: dict[str, str] = {
    "cold_room_zone_plan": "throughput_inventory_area",
    "cooling_load": "cooling_load",
    "equipment": "equipment_selection",
    "installed_power": "electrical_and_energy",
    "investment_estimate": "investment_estimate",
}

MISSING_KEY_CASES: tuple[tuple[str, str], ...] = (
    ("equipment_inputs.condensing_temperature_c", "condensing_temperature_c"),
    ("cooling_load_inputs.zones[0].zone_area", "cooling geometry zone_area"),
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


def assert_production_scheme_source_mode(
    service: Any,
    *,
    run_id: str,
    source_binding_id: str | None,
    combined_source_hash: str | None,
) -> None:
    with sessionmaker(bind=service.engine, expire_on_commit=False)() as session:
        record = session.scalar(select(SchemeRunRecord).where(SchemeRunRecord.id == run_id))
        assert record is not None, f"production scheme run {run_id!r} not persisted"
        assert record.source_mode == "production"
        assert record.source_binding_id == source_binding_id
        assert record.combined_source_hash == combined_source_hash


def assert_workflow_result_hash_parity(
    client: TestClient,
    *,
    project_id: str,
    version_number: int,
    by_name: dict[str, dict[str, Any]],
) -> None:
    workflow = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/workflow"
    ).json()
    runs = workflow.get("calculations", {}).get("runs", [])
    workflow_by_calculator: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = run.get("calculator_name")
        if isinstance(name, str):
            workflow_by_calculator[name] = run

    for stage in CANONICAL_STAGE_ORDER:
        calculator = calculator_for_stage(stage)
        api_hash = str(by_name[calculator]["result_hash"])
        assert api_hash, f"{calculator} missing API result_hash"
        workflow_hash = str(workflow_by_calculator[calculator]["result_hash"])
        assert workflow_hash == api_hash, (
            f"workflow result_hash mismatch for {calculator!r}: "
            f"workflow={workflow_hash!r} api={api_hash!r}"
        )


def assert_report_reads_persisted_without_recalc(
    exported: dict[str, Any],
    by_name: dict[str, dict[str, Any]],
) -> None:
    content = exported.get("content") or exported
    assert content.get("input_conditions"), "input_conditions must come from persisted snapshots"
    assert content.get("assumptions"), "assumptions must come from persisted snapshots"

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


def assert_demo_coefficients_from_v07_manifest() -> None:
    manifest = load_manifest()
    demo_leaves = (
        manifest["engineering_input_bundle"]["coefficient_context"].get("demo_coefficient_leaves")
        or []
    )
    assert demo_leaves, "v07 manifest must declare demo_coefficient_leaves"
    for leaf in demo_leaves:
        assert leaf["source_type"] == "demo"
        assert leaf["validity_status"] in {"unverified", "conflict"}
        assert leaf["requires_review"] is True


def run_p7_controlled_acceptance(client: TestClient, seeded: Any, service: Any) -> dict[str, Any]:
    by_name = calculations_by_name(
        client.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
        ).json()
    )
    assert_canonical_five_persisted(list(by_name.values()))
    assert_upstream_lineage_matches_p0(by_name)

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


def test_v07_p7_contract_exists() -> None:
    assert P7_CONTRACT.is_file()
    text = P7_CONTRACT.read_text(encoding="utf-8")
    assert "TASK=V07_P7_CONTROLLED_ACCEPTANCE_R1" in text
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in text
    assert "TARGET_BRANCH=cursor/v07-p7-controlled-acceptance-6c68" in text
    assert "TARGET_PR_STATE=DRAFT" in text
    assert "TAG_PUBLICATION_AUTHORIZED=NO" in text
    assert "MERGE_AUTHORIZED=NO" in text
    assert "READY_AUTHORIZED=NO" in text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in text
    assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text
    for pattern in FORBIDDEN_RELEASE_PATTERNS:
        assert not pattern.search(text), f"forbidden release pattern in contract: {pattern}"


def test_v07_p7_contract_records_aily_boundary() -> None:
    assert P6_CONTRACT.is_file()
    p6_text = P6_CONTRACT.read_text(encoding="utf-8")
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p6_text
    p7_text = P7_CONTRACT.read_text(encoding="utf-8")
    assert "AILY_LIVE_IMPLEMENTATION=NO" in p7_text
    assert "test_v07_p6_aily_contract.py" in p7_text


def test_v07_p7_contract_records_issue_evidence_only() -> None:
    text = P7_CONTRACT.read_text(encoding="utf-8")
    assert "#11" in text
    assert "#13" in text
    assert "#176" in text
    assert "P7_CLOSES_ISSUES_NOW=NO" in text
    assert "do not close via `gh`" in text.lower() or "do not close via gh" in text.lower()


@pytest.mark.sqlite
def test_v07_p7_sqlite_controlled_acceptance(tmp_path: Path) -> None:
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
    "dotted_path,_label",
    MISSING_KEY_CASES,
    ids=[case[1] for case in MISSING_KEY_CASES],
)
def test_v07_p7_sqlite_missing_key_leaf_fail_closed(
    tmp_path: Path,
    dotted_path: str,
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
                    "name": f"V07-P7 missing key {uuid.uuid4().hex[:8]}",
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

            response = execute_missing_key_bundle(
                client,
                project_id=project_id,
                version_number=version_number,
                version_id=version_id,
                dotted_path=dotted_path,
            )
            assert response["error"]["code"] == "MISSING_ENGINEERING_PARAMETER"

            with sessionmaker(bind=service.engine, expire_on_commit=False)() as session:
                assert_zero_canonical_rows(session, version_id)


@pytest.mark.sqlite
def test_v07_p7_sqlite_demo_coefficients_remain_unverified() -> None:
    assert_demo_coefficients_from_v07_manifest()
