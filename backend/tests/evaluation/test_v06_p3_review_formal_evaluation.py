"""V0.6 P3 evaluation: five-stage review to formal-mode lifecycle evidence."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
from tests.evaluation.v06_p3_lifecycle_helpers import (
    CANONICAL_CALCULATORS,
    FORMAL_FORMATS,
    FORMAL_LOCALES,
    SCENARIO_LABEL,
    TEMPLATE_VERSION,
    UNTRUSTED_ACTOR,
    assert_assumptions_from_persisted_snapshot,
    assert_canonical_five_persisted,
    assert_input_conditions_from_manifest,
    collect_source_result_ids,
    complete_trusted_review_lifecycle,
    create_report,
    create_sqlite_engine,
    export_report_json,
    fixture_sha256,
    generate_report_revision,
    invalidate_canonical_projection,
    load_fixture,
    make_evaluation_client,
    render_formal,
    seed_five_stage_project,
    seeded_project_context,
    submit_review,
    version_id,
    walk_measured_values,
)
from tests.integration.v05_p4_acceptance_fixtures import calculations_by_name

BACKEND_DIR = Path(__file__).resolve().parents[2]

V05_MANIFEST_SHA256 = "f12f37294c52b63f7a8779a86ed89403108974c437576a8ebd64d4af3190c337"
V05_SEED_REF_SHA256 = "1251d5799a5ef30c526ae6768167edcafe867235dba6a55fc421bc20df47ebd9"


def _create_report_for_ctx(client: TestClient, ctx: dict[str, Any]) -> dict[str, Any]:
    seeded = ctx["seeded"]
    return create_report(
        client,
        project_id=seeded.project_id,
        version_id=ctx["version_id"],
    )


DATABASE_BACKEND_PARAMS = pytest.mark.parametrize(
    "database_backend",
    [
        pytest.param(
            "sqlite",
            marks=pytest.mark.skipif(
                os.environ.get("DATABASE_BACKEND") == "postgresql",
                reason="SQLite P3 evaluation tests cannot run on PostgreSQL backend",
            ),
        ),
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                os.environ.get("DATABASE_BACKEND") != "postgresql",
                reason="PostgreSQL P3 evaluation tests require DATABASE_BACKEND=postgresql",
            ),
        ),
    ],
)


@pytest.fixture()
def evaluation_client(database_backend: str, tmp_path, request):
    artifact_dir = tmp_path / "report-artifacts"
    artifact_dir.mkdir()

    if database_backend == "sqlite":
        db_path = tmp_path / f"v06_p3_eval_{uuid.uuid4().hex[:8]}.db"
        engine = create_sqlite_engine(db_path)
        service = DatabaseProjectService(engine)
        try:
            with make_evaluation_client(
                service,
                artifact_dir=artifact_dir,
                sqlite_path=db_path,
            ) as client:
                yield client, service, engine, artifact_dir
        finally:
            engine.dispose()
            db_path.unlink(missing_ok=True)
        return

    pg_engine = request.getfixturevalue("pg_engine")
    service = DatabaseProjectService(pg_engine)
    with make_evaluation_client(service, artifact_dir=artifact_dir) as client:
        yield client, service, pg_engine, artifact_dir


def _context(evaluation_client) -> tuple[TestClient, Any, Any, Path]:
    client, service, engine, artifact_dir = evaluation_client
    return client, service, engine, artifact_dir


def test_p3_fixture_source_definitions_frozen_before_label_use() -> None:
    """Source-definition evidence must exist before high_throughput_review use."""
    registry = load_fixture("v06_p3_scenario_registry.v1.json")
    label_source = load_fixture("v06_p3_high_throughput_review_label_source.v1.json")
    seed_ref = load_fixture("v06_p3_v05_seed_manifest_ref.v1.json")

    label_fixture = "v06_p3_high_throughput_review_label_source.v1.json"
    label_authority = registry["label_authority"]["high_throughput_review"]
    assert label_authority["source_definition_sha256"] == fixture_sha256(label_fixture)
    assert label_source["scenario_label"] == SCENARIO_LABEL
    assert label_source["label_role"] == "scenario_label_only"
    assert seed_ref["manifest_sha256"] == V05_MANIFEST_SHA256
    assert fixture_sha256("v06_p3_v05_seed_manifest_ref.v1.json") == V05_SEED_REF_SHA256


@DATABASE_BACKEND_PARAMS
def test_p3_canonical_calculator_names_after_five_stage_seed(evaluation_client) -> None:
    client, _service, _engine, _artifact_dir = _context(evaluation_client)
    ctx = seeded_project_context(client, _engine)
    by_name = ctx["by_name"]

    assert set(by_name) == set(CANONICAL_CALCULATORS)
    assert "power_configuration" not in by_name or by_name.get("installed_power") is not None
    assert by_name["installed_power"]["calculator_name"] == "installed_power"


@DATABASE_BACKEND_PARAMS
def test_p3_report_generate_binds_persisted_source_result_ids(evaluation_client) -> None:
    client, _service, engine, _artifact_dir = _context(evaluation_client)
    ctx = seeded_project_context(client, engine)
    by_name = ctx["by_name"]

    report = _create_report_for_ctx(client, ctx)
    revision = generate_report_revision(client, report["id"])
    exported = export_report_json(client, report["id"])

    content = exported["content"]
    bound_ids = collect_source_result_ids(content)
    citations = {
        item["tool_name"]: item["result_id"]
        for item in content.get("citations", [])
        if item.get("tool_name") in CANONICAL_CALCULATORS
    }
    for calculator_name in CANONICAL_CALCULATORS:
        calc_id = by_name[calculator_name]["calculation_id"]
        assert calc_id in bound_ids or citations.get(calculator_name) == calc_id, (
            f"{calculator_name} calculation_id not bound in report JSON"
        )

    measured_rows = walk_measured_values(content)
    assert measured_rows, "expected measured_value rows with provenance"
    for row in measured_rows:
        assert row["source_result_id"]
        assert row["source_tool"]
        assert row["source_tool_version"]

    for calculator_name in CANONICAL_CALCULATORS:
        assert citations[calculator_name] == by_name[calculator_name]["calculation_id"]

    assert revision["content_hash"]
    assert revision["revision_number"] == 1


@DATABASE_BACKEND_PARAMS
def test_p3_input_conditions_and_assumptions_from_persisted_snapshots(evaluation_client) -> None:
    client, _service, engine, _artifact_dir = _context(evaluation_client)
    ctx = seeded_project_context(client, engine)

    report = _create_report_for_ctx(client, ctx)
    generate_report_revision(client, report["id"])
    exported = export_report_json(client, report["id"])

    assert_input_conditions_from_manifest(exported["content"], ctx["manifest"])
    assert_assumptions_from_persisted_snapshot(exported["content"])


@DATABASE_BACKEND_PARAMS
def test_p3_happy_path_formal_exports_bind_provenance(evaluation_client) -> None:
    client, _service, engine, _artifact_dir = _context(evaluation_client)
    ctx = seeded_project_context(client, engine)

    report = _create_report_for_ctx(client, ctx)
    revision = generate_report_revision(client, report["id"])
    complete_trusted_review_lifecycle(client, report["id"])

    approved = client.get(f"/api/v1/reports/{report['id']}").json()
    assert approved["status"] == "approved"

    for locale in FORMAL_LOCALES:
        for export_format in FORMAL_FORMATS:
            rendered = render_formal(
                client,
                report["id"],
                revision_number=revision["revision_number"],
                locale=locale,
                export_format=export_format,
            )
            assert rendered["status_code"] == 200, rendered
            body = rendered["body"]
            assert body["status"] == "completed"
            assert body["locale"] == locale
            assert body["file_size_bytes"] > 0
            assert len(body["file_sha256"]) == 64
            assert body["translation_catalog_version"]
            assert body["translation_catalog_content_hash"]
            assert body["localized_template_content_hash"]

            detail = client.get(
                f"/api/v1/reports/{report['id']}/exports/{body['artifact_id']}"
            ).json()
            assert detail["template_version"] == TEMPLATE_VERSION
            assert detail["revision_number"] == revision["revision_number"]
            assert detail["file_sha256"] == body["file_sha256"]

            revision_detail = client.get(
                f"/api/v1/reports/{report['id']}/revisions/{revision['revision_number']}"
            ).json()
            assert revision_detail["content_hash"] == revision["content_hash"]

            download = client.get(
                f"/api/v1/reports/{report['id']}/exports/{body['artifact_id']}/download"
            )
            assert download.status_code == 200
            assert len(download.content) > 1000


@DATABASE_BACKEND_PARAMS
def test_p3_formal_render_without_mark_reviewed_fails_closed(evaluation_client) -> None:
    client, service, engine, artifact_dir = _context(evaluation_client)
    ctx = seeded_project_context(client, engine)
    assert ctx["scheme"]["requires_review"] is True

    report = _create_report_for_ctx(client, ctx)
    revision = generate_report_revision(client, report["id"])
    submit_review(client, report["id"])

    # Approve without trusted mark_reviewed must fail closed when review is required.
    approve_without_review = client.post(f"/api/v1/reports/{report['id']}/approve")
    assert approve_without_review.status_code in {409, 422, 500}

    for locale in FORMAL_LOCALES:
        for export_format in FORMAL_FORMATS:
            rendered = render_formal(
                client,
                report["id"],
                revision_number=revision["revision_number"],
                locale=locale,
                export_format=export_format,
            )
            assert rendered["status_code"] == 409, rendered

    # Untrusted actor cannot satisfy mark_reviewed even if invoked directly.
    with make_evaluation_client(
        service,
        artifact_dir=artifact_dir,
        actor=UNTRUSTED_ACTOR,
    ) as untrusted_client:
        untrusted_mark = untrusted_client.post(f"/api/v1/reports/{report['id']}/mark-reviewed")
        assert untrusted_mark.status_code in {404, 409, 422, 500}


@DATABASE_BACKEND_PARAMS
def test_p3_missing_canonical_source_fails_closed_for_formal_export(evaluation_client) -> None:
    client, _service, engine, _artifact_dir = _context(evaluation_client)
    seeded = seed_five_stage_project(client)
    version = version_id(client, seeded.project_id, seeded.version_number)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        invalidate_canonical_projection(
            session,
            version_id=version,
            calculator_names=("investment_estimate",),
        )

    report = create_report(client, project_id=seeded.project_id, version_id=version)
    revision = generate_report_revision(client, report["id"])
    exported = export_report_json(client, report["id"])
    findings = exported["content"]["quality_summary"]["findings"]
    codes = {finding["code"] for finding in findings}
    quality_summary = exported["content"]["quality_summary"]
    assert "MISSING_CANONICAL_SOURCE" in codes or quality_summary["blocker_count"] > 0

    submit = client.post(f"/api/v1/reports/{report['id']}/submit-review")
    assert submit.status_code in {409, 422}

    rendered = render_formal(
        client,
        report["id"],
        revision_number=revision["revision_number"],
        locale="zh-CN",
        export_format="pdf",
    )
    assert rendered["status_code"] == 409, rendered


@DATABASE_BACKEND_PARAMS
def test_p3_restart_reopen_preserves_calculation_and_revision_hashes(evaluation_client) -> None:
    client, service, engine, artifact_dir = _context(evaluation_client)
    ctx = seeded_project_context(client, engine)

    first_calculations = client.get(
        f"/api/v1/projects/{ctx['seeded'].project_id}/versions/{ctx['seeded'].version_number}/calculations"
    ).json()
    first_by_name = assert_canonical_five_persisted(first_calculations)

    report = _create_report_for_ctx(client, ctx)
    first_revision = generate_report_revision(client, report["id"])

    with make_evaluation_client(service, artifact_dir=artifact_dir) as reopened:
        second_calculations = reopened.get(
            f"/api/v1/projects/{ctx['seeded'].project_id}/versions/{ctx['seeded'].version_number}/calculations"
        ).json()
        second_by_name = calculations_by_name(second_calculations)
        for name in CANONICAL_CALCULATORS:
            assert second_by_name[name]["calculation_id"] == first_by_name[name]["calculation_id"]
            assert second_by_name[name]["result_hash"] == first_by_name[name]["result_hash"]

        reopened_report = reopened.get(f"/api/v1/reports/{report['id']}").json()
        reopened_revision = reopened.get(
            f"/api/v1/reports/{report['id']}/revisions/{first_revision['revision_number']}"
        ).json()
        assert reopened_revision["content_hash"] == first_revision["content_hash"]
        assert reopened_report["revision_number"] == first_revision["revision_number"]


@DATABASE_BACKEND_PARAMS
def test_p3_high_throughput_review_label_does_not_mutate_review_authority(
    evaluation_client,
) -> None:
    client, _service, engine, _artifact_dir = _context(evaluation_client)
    ctx = seeded_project_context(client, engine)
    label_source = load_fixture("v06_p3_high_throughput_review_label_source.v1.json")

    assert label_source["scenario_label"] == SCENARIO_LABEL
    assert label_source["label_role"] == "scenario_label_only"
    assert label_source["reviewer_evidence"]["label_does_not_override"] is True

    report = _create_report_for_ctx(client, ctx)
    generate_report_revision(client, report["id"])
    exported = export_report_json(client, report["id"])
    embedded = exported["content"]["scheme_comparison"]["review_authority"]
    assert embedded["requires_review"] == ctx["scheme"]["requires_review"]
    assert len(embedded["review_reasons"]) == len(ctx["scheme"]["review_reasons"])
    embedded_codes = {reason["code"] for reason in embedded["review_reasons"]}
    scheme_codes = {reason.code for reason in ctx["scheme"]["review_reasons"]}
    assert embedded_codes == scheme_codes
