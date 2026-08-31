"""Shared evidence collectors and assertions for V0.7 P2 consistency tests."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from cold_storage.bootstrap.production_composition import compose_production_scheme_service
from cold_storage.bootstrap.v05_local_sample import (
    EXPECTED_CANONICAL_CALCULATORS,
    hydrate_engineering_input_bundle,
)
from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CANONICAL_STAGE_ORDER,
)
from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    ProjectServicePersistedCalculationQuery,
)
from cold_storage.modules.reports.infrastructure.real_data_provider import RealReportDataProvider
from cold_storage.modules.schemes.application.canonical_source_reads import (
    _per_calc_hash,
    require_canonical_scheme_sources,
)
from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
)
from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord
from cold_storage.modules.workflow.application.service import _result_hash
from tests.integration.test_production_scheme_sqlite import (
    WEIGHT_REVISION_ID,
    _seed_weight_set_and_revision,
)
from tests.integration.v05_p4_acceptance_fixtures import (
    calculations_by_name,
    execute_five_stage,
)
from tests.integration.v07_p2_numeric_projection_map import (
    assert_snapshot_report_numeric_parity,
    calculator_for_stage,
    stage_for_calculator,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
V07_SAMPLE_ID = "v07-consistency"
V07_MANIFEST_PATH = REPO_ROOT / "samples" / V07_SAMPLE_ID / "manifest.json"
GOLDEN_PATH = Path(__file__).resolve().parent.parent / "golden" / "v07_cross_consumer_v1.json"

CANONICAL_CALCULATORS = frozenset(EXPECTED_CANONICAL_CALCULATORS)

STAGE_RESULT_HASH_COLUMNS: dict[str, str] = {
    "zone": "zone_result_hash",
    "cooling_load": "cooling_load_result_hash",
    "equipment": "equipment_result_hash",
    "power": "power_result_hash",
    "investment": "investment_result_hash",
}

STAGE_CALCULATION_ID_COLUMNS: dict[str, str] = {
    "zone": "zone_calculation_id",
    "cooling_load": "cooling_load_calculation_id",
    "equipment": "equipment_calculation_id",
    "power": "power_calculation_id",
    "investment": "investment_calculation_id",
}


@dataclass(frozen=True)
class KnownDriftEvidence:
    """Recorded helper-hash drift (V07-GAP-005); not authoritative."""

    workflow_raw_snapshot_hashes: dict[str, str]
    scheme_helper_hashes: dict[str, str]
    workflow_combined_raw_hash: str | None
    scheme_run_combined_hash: str | None


@dataclass
class CrossConsumerEvidence:
    project_id: str
    version_number: int
    version_id: str
    api_by_calculator: dict[str, dict[str, Any]]
    binding_per_calc_hashes: dict[str, str]
    binding_combined_hash: str
    binding_slot_ids: dict[str, str]
    report_sections: list[dict[str, Any]]
    workflow_runs: dict[str, dict[str, Any]]
    scheme_helper_hashes: dict[str, str]
    scheme_slot_ids: dict[str, str]
    production_scheme_hashes: dict[str, str]
    production_scheme_ids: dict[str, str]
    known_drift: KnownDriftEvidence = field(default_factory=KnownDriftEvidence)


def load_v07_manifest() -> dict[str, Any]:
    if not V07_MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"V07 consistency manifest missing: {V07_MANIFEST_PATH}")
    manifest = json.loads(V07_MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("sample_id") != V07_SAMPLE_ID:
        raise ValueError(f"unexpected sample_id: {manifest.get('sample_id')!r}")
    return manifest


def seed_v07_consistency_project(client: TestClient) -> tuple[str, int, str]:
    """Seed five-stage execution from the frozen v07-consistency manifest."""
    from cold_storage.bootstrap.v05_local_sample import seed_v05_local_sample

    manifest = load_v07_manifest()
    seeded = seed_v05_local_sample(client, manifest=manifest)
    version_id = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}"
    ).json()["id"]
    return seeded.project_id, seeded.version_number, version_id


def _read_source_binding(session: Session, project_id: str, version_id: str) -> SourceBindingRecord:
    binding = session.scalar(
        select(SourceBindingRecord).where(
            SourceBindingRecord.project_id == project_id,
            SourceBindingRecord.project_version_id == version_id,
        )
    )
    assert binding is not None, "SourceBinding must exist after five-stage execution"
    return binding


def _workflow_runs_by_calculator(
    client: TestClient, project_id: str, version_number: int
) -> dict[str, dict[str, Any]]:
    workflow = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/workflow"
    ).json()
    runs = workflow.get("calculations", {}).get("runs", [])
    indexed: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = run.get("calculator_name")
        if isinstance(name, str):
            indexed[name] = run
    return indexed


def _scheme_helper_bundle(session: Session, project_id: str, version_id: str):
    records = list(
        session.scalars(
            select(CalculationRunRecord).where(
                CalculationRunRecord.project_id == project_id,
                CalculationRunRecord.project_version_id == version_id,
            )
        )
    )
    return require_canonical_scheme_sources(
        records,
        project_id=project_id,
        project_version_id=version_id,
    )


def generate_production_scheme_run(
    engine,
    *,
    binding_id: str,
    correlation_suffix: str | None = None,
) -> SchemeRunRecord:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        _seed_weight_set_and_revision(session)
        session.commit()
    service = compose_production_scheme_service(session_factory)
    service.generate_production_scheme_run(
        GenerateProductionSchemeCommand(
            source_binding_id=binding_id,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="v07-p2-test",
            correlation_id=f"v07-p2-{correlation_suffix or uuid.uuid4().hex[:8]}",
            database_backend=__import__("os").environ.get("DATABASE_BACKEND", "sqlite"),
        )
    )
    with session_factory() as session:
        run = session.scalar(
            select(SchemeRunRecord)
            .where(SchemeRunRecord.source_binding_id == binding_id)
            .order_by(SchemeRunRecord.created_at.desc())
        )
        assert run is not None, "production scheme run must be persisted"
        session.expunge(run)
        return run


def collect_cross_consumer_evidence(
    client: TestClient,
    service,
    engine,
    *,
    project_id: str,
    version_number: int,
    version_id: str,
    include_production_scheme: bool = True,
) -> CrossConsumerEvidence:
    api_rows = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    api_by_calculator = calculations_by_name(api_rows)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        binding = _read_source_binding(session, project_id, version_id)
        scheme_bundle = _scheme_helper_bundle(session, project_id, version_id)
        binding_id = binding.id
        binding_hashes = dict(binding.per_calculation_result_hashes)
        binding_combined = binding.combined_source_hash
        binding_slot_ids = {
            stage: str(getattr(binding, STAGE_CALCULATION_ID_COLUMNS[stage]))
            for stage in CANONICAL_STAGE_ORDER
        }

    production_scheme_hashes: dict[str, str] = {}
    production_scheme_ids: dict[str, str] = {}
    scheme_run_combined: str | None = None
    if include_production_scheme:
        scheme_run = generate_production_scheme_run(engine, binding_id=binding_id)
        for stage in CANONICAL_STAGE_ORDER:
            col = STAGE_RESULT_HASH_COLUMNS[stage]
            id_col = STAGE_CALCULATION_ID_COLUMNS[stage]
            production_scheme_hashes[stage] = str(getattr(scheme_run, col))
            production_scheme_ids[stage] = str(getattr(scheme_run, id_col))
        scheme_run_combined = str(scheme_run.source_snapshot_hash or "")

    workflow_runs = _workflow_runs_by_calculator(client, project_id, version_number)

    query = ProjectServicePersistedCalculationQuery(service)
    provider = RealReportDataProvider(project_service=service, calculation_service=query)
    report_sections = provider.get_calculation_results(project_id, version_id)

    workflow_combined: str | None = None
    if api_by_calculator:
        import hashlib

        combined_payload = {
            name: api_by_calculator[name].get("result_snapshot", {})
            for name in sorted(api_by_calculator)
            if name in CANONICAL_CALCULATORS
        }
        workflow_combined = hashlib.sha256(
            json.dumps(
                combined_payload,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()

    known_drift = KnownDriftEvidence(
        workflow_raw_snapshot_hashes={
            calculator_for_stage(stage): _result_hash(
                api_by_calculator[calculator_for_stage(stage)].get("result_snapshot")
            )
            for stage in CANONICAL_STAGE_ORDER
        },
        scheme_helper_hashes=dict(scheme_bundle.source_snapshot_hashes),
        workflow_combined_raw_hash=workflow_combined,
        scheme_run_combined_hash=scheme_run_combined,
    )

    return CrossConsumerEvidence(
        project_id=project_id,
        version_number=version_number,
        version_id=version_id,
        api_by_calculator=api_by_calculator,
        binding_per_calc_hashes=binding_hashes,
        binding_combined_hash=str(binding_combined),
        binding_slot_ids=binding_slot_ids,
        report_sections=report_sections,
        workflow_runs=workflow_runs,
        scheme_helper_hashes=dict(scheme_bundle.source_snapshot_hashes),
        scheme_slot_ids=dict(scheme_bundle.source_calculation_ids),
        production_scheme_hashes=production_scheme_hashes,
        production_scheme_ids=production_scheme_ids,
        known_drift=known_drift,
    )


def authoritative_hash_for_stage(evidence: CrossConsumerEvidence, stage: str) -> str:
    calculator = calculator_for_stage(stage)
    return str(evidence.api_by_calculator[calculator]["result_hash"])


def assert_canonical_five_present(evidence: CrossConsumerEvidence) -> None:
    missing = CANONICAL_CALCULATORS - set(evidence.api_by_calculator)
    assert not missing, f"missing canonical calculators: {sorted(missing)}"
    for name in CANONICAL_CALCULATORS:
        row = evidence.api_by_calculator[name]
        assert row.get("calculation_id"), f"{name} missing calculation_id"
        assert row.get("result_hash"), f"{name} missing result_hash"


def assert_authoritative_hash_parity(evidence: CrossConsumerEvidence) -> None:
    """API, SourceBinding, report, and production scheme authoritative hashes align."""
    for stage in CANONICAL_STAGE_ORDER:
        calculator = calculator_for_stage(stage)
        authoritative = authoritative_hash_for_stage(evidence, stage)

        binding_hash = evidence.binding_per_calc_hashes.get(stage)
        assert binding_hash == authoritative, (
            f"SourceBinding hash mismatch for {stage!r}: "
            f"binding={binding_hash!r} api={authoritative!r}"
        )

        report_section = next(
            (s for s in evidence.report_sections if s.get("tool_name") == calculator),
            None,
        )
        assert report_section is not None, f"report section missing for {calculator!r}"
        report_hash = report_section.get("persisted_content_hash")
        assert report_hash == authoritative, (
            f"report hash mismatch for {calculator!r}: report={report_hash!r} api={authoritative!r}"
        )

        if evidence.production_scheme_hashes:
            prod_hash = evidence.production_scheme_hashes[stage]
            assert prod_hash == authoritative, (
                f"production scheme hash mismatch for {stage!r}: "
                f"scheme={prod_hash!r} api={authoritative!r}"
            )


def assert_identity_parity(evidence: CrossConsumerEvidence) -> None:
    for stage in CANONICAL_STAGE_ORDER:
        calculator = calculator_for_stage(stage)
        api_id = str(evidence.api_by_calculator[calculator]["calculation_id"])

        binding_id = evidence.binding_slot_ids[stage]
        assert binding_id == api_id, (
            f"SourceBinding id mismatch for {stage!r}: binding={binding_id!r} api={api_id!r}"
        )

        scheme_id = evidence.scheme_slot_ids[stage]
        assert scheme_id == api_id, (
            f"scheme canonical read id mismatch for {stage!r}: scheme={scheme_id!r} api={api_id!r}"
        )

        workflow_run = evidence.workflow_runs.get(calculator)
        assert workflow_run is not None, f"workflow run missing for {calculator!r}"
        workflow_id = str(workflow_run.get("calculation_run_id", ""))
        assert workflow_id == api_id, (
            f"workflow id mismatch for {calculator!r}: workflow={workflow_id!r} api={api_id!r}"
        )

        report_section = next(
            (s for s in evidence.report_sections if s.get("tool_name") == calculator),
            None,
        )
        assert report_section is not None
        report_id = str(report_section.get("result_id", ""))
        assert report_id == api_id, (
            f"report id mismatch for {calculator!r}: report={report_id!r} api={api_id!r}"
        )

        if evidence.production_scheme_ids:
            prod_id = evidence.production_scheme_ids[stage]
            assert prod_id == api_id, (
                f"production scheme id mismatch for {stage!r}: prod={prod_id!r} api={api_id!r}"
            )


def assert_numeric_projection_parity(evidence: CrossConsumerEvidence) -> None:
    for section in evidence.report_sections:
        tool_name = section.get("tool_name")
        if tool_name not in CANONICAL_CALCULATORS:
            continue
        snapshot = evidence.api_by_calculator[tool_name].get("result_snapshot") or {}
        if not isinstance(snapshot, dict):
            raise AssertionError(f"{tool_name}: result_snapshot is not a dict")
        report_data = section.get("data") or {}
        if not isinstance(report_data, dict):
            raise AssertionError(f"{tool_name}: report data is not a dict")
        assert_snapshot_report_numeric_parity(
            calculator_name=tool_name,
            snapshot=snapshot,
            report_data=report_data,
        )


def assert_known_drift_recorded(evidence: CrossConsumerEvidence) -> None:
    """Workflow/scheme helper hashes must differ from authoritative (V07-GAP-005)."""
    drift_stages: list[str] = []
    for stage in CANONICAL_STAGE_ORDER:
        calculator = calculator_for_stage(stage)
        authoritative = authoritative_hash_for_stage(evidence, stage)
        workflow_helper = evidence.known_drift.workflow_raw_snapshot_hashes.get(calculator, "")
        scheme_helper = evidence.known_drift.scheme_helper_hashes.get(stage, "")
        if workflow_helper and workflow_helper != authoritative:
            drift_stages.append(f"workflow:{stage}")
        if scheme_helper and scheme_helper != authoritative:
            drift_stages.append(f"scheme:{stage}")
    assert drift_stages, (
        "expected KNOWN_DRIFT between helper hashes and authoritative fingerprint.result_hash"
    )

    if (
        evidence.known_drift.workflow_combined_raw_hash
        and evidence.binding_combined_hash
        and evidence.known_drift.workflow_combined_raw_hash != evidence.binding_combined_hash
    ):
        drift_stages.append("workflow_combined_raw_vs_binding")


def load_golden_artifact() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def build_golden_snapshot(evidence: CrossConsumerEvidence) -> dict[str, Any]:
    payload_result_hashes: dict[str, str] = {}
    for stage in CANONICAL_STAGE_ORDER:
        calculator = calculator_for_stage(stage)
        snapshot = evidence.api_by_calculator[calculator].get("result_snapshot") or {}
        if isinstance(snapshot, dict):
            payload_result_hashes[stage] = _per_calc_hash(snapshot)
    numerics: dict[str, str] = {}
    for calculator in sorted(CANONICAL_CALCULATORS):
        snapshot = evidence.api_by_calculator[calculator].get("result_snapshot") or {}
        if not isinstance(snapshot, dict):
            continue
        section = next(
            (s for s in evidence.report_sections if s.get("tool_name") == calculator),
            None,
        )
        if section is None:
            continue
        report_data = section.get("data") or {}
        if not isinstance(report_data, dict):
            continue
        from tests.integration.v07_p2_numeric_projection_map import (
            extract_report_numerics,
            extract_snapshot_numerics,
        )

        snap_nums = extract_snapshot_numerics(calculator, snapshot)
        report_nums = extract_report_numerics(
            section.get("section_key", ""),
            report_data,
        )
        for path, value in snap_nums.items():
            key = f"{calculator}.{path}"
            numerics[key] = str(value)
            assert path in report_nums
            assert report_nums[path] == value

    return {
        "sample_id": V07_SAMPLE_ID,
        "schema_version": "1.0",
        "payload_result_hashes": payload_result_hashes,
        "selected_numeric_projections": numerics,
        "known_drift_expected": True,
        "hash_parity_note": (
            "payload_result_hashes are raw snapshot hashes (stable cross-backend); "
            "authoritative fingerprint.result_hash binds execution provenance per run"
        ),
    }


def assert_matches_golden(evidence: CrossConsumerEvidence, golden: dict[str, Any]) -> None:
    snapshot = build_golden_snapshot(evidence)
    left = snapshot["payload_result_hashes"]
    right = golden["payload_result_hashes"]
    if left != right:
        delta = {
            key: (left.get(key), right.get(key))
            for key in sorted(set(left) | set(right))
            if left.get(key) != right.get(key)
        }
        raise AssertionError(f"payload_result_hashes mismatch: {delta}")
    assert snapshot["selected_numeric_projections"] == golden["selected_numeric_projections"]


def execute_missing_key_bundle(
    client: TestClient,
    *,
    project_id: str,
    version_number: int,
    version_id: str,
    dotted_path: str,
) -> dict[str, Any]:
    from tests.integration.v05_p4_acceptance_fixtures import bundle_with_removed_key

    manifest = load_v07_manifest()
    bundle = hydrate_engineering_input_bundle(
        manifest,
        project_id=project_id,
        project_version_id=version_id,
        version_number=version_number,
    )
    broken = bundle_with_removed_key(bundle, dotted_path)
    return execute_five_stage(
        client,
        project_id=project_id,
        version_number=version_number,
        bundle=broken,
        idempotency_key=f"v07-p2-missing-{uuid.uuid4().hex[:8]}",
    )


def assert_zero_canonical_rows(session: Session, version_id: str) -> None:
    count = session.scalar(
        select(func.count())
        .select_from(CalculationRunRecord)
        .where(
            CalculationRunRecord.project_version_id == version_id,
            CalculationRunRecord.calculator_name.in_(CANONICAL_CALCULATORS),
        )
    )
    assert count == 0
    binding_count = session.scalar(
        select(func.count())
        .select_from(SourceBindingRecord)
        .where(SourceBindingRecord.project_version_id == version_id)
    )
    assert binding_count == 0


def stage_for_calculator_name(calculator_name: str) -> str:
    return stage_for_calculator(calculator_name)
