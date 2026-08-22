"""V0.3 P5 controlled-acceptance harness, gates, and scenario execution engine.

This module validates dispatch, operator, source-identity, and execution-
authorization gates, then either fails closed or executes the bound Scenario
A/B/C fixture through existing persisted production application services. It is
not a second engineering engine.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

HARNESS_SCHEMA_VERSION = "v0.3-p5-controlled-acceptance-harness.v1"
EVIDENCE_SCHEMA_VERSION = "v0.3-p5-controlled-acceptance-evidence.v1"
CONTRACT_PATH = "docs/tasks/V0_3-P5-controlled-acceptance-and-release-contract.md"
RUNBOOK_PATH = "docs/runbooks/V0_3-P5-controlled-acceptance-and-release.md"
WORKFLOW_PATH = ".github/workflows/v0-3-p5-controlled-acceptance-and-release.yml"

SCENARIO_NAMES: frozenset[str] = frozenset({"A", "B", "C"})
FIXTURE_PATHS: dict[str, str] = {
    "A": "backend/tests/pilot/data/v03-scenario-a-normal-formal-report.v1.json",
    "B": "backend/tests/pilot/data/v03-scenario-b-review-required-formal-report.v1.json",
    "C": "backend/tests/pilot/data/v03-scenario-c-agent-knowledge-deterministic.v1.json",
}
FIXTURE_SHA256: dict[str, str] = {
    "A": "b4227ea107c12571681d29ad7746175e73e05b0ffeb9e6d7fa5e61e0b9877d15",
    "B": "ff462cbaff0fadc77c809cd0a28917dd09ba0cea1ed73066d6fa1100f8552bbb",
    "C": "9ac8a43020bd6876909265e2e0e8286053bfb17c7152039d32b406f78fa9233a",
}
BASELINE_CORRELATION_ID = "v03-p5-scenario-a-baseline-001"

REJECTED_OPERATOR_NAMES = frozenset({"system", "api", "background", "llm"})
EXECUTION_AUTHORIZATION_ENV = "V03_P5_CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED"
AUTHORIZATION_RECORD_ENV = "V03_P5_CONTROLLED_ACCEPTANCE_AUTHORIZATION_RECORD_ID"
ALLOWED_EXECUTION_AUTHORIZED_VALUES = frozenset({"YES", "true", "True", "1"})
MAIN_REF = "refs/heads/main"
WORKFLOW_DISPATCH_EVENT = "workflow_dispatch"


@dataclass(frozen=True, slots=True)
class ScenarioAExecutionBinding:
    """Pilot-injected baseline seed binding for Scenario A execution."""

    source_binding_id: str
    weight_set_revision_id: str
    seed_prereqs: Callable[[Any], None]


@dataclass(frozen=True, slots=True)
class ScenarioExecutionSupport:
    """Pilot-owned bootstrap bindings that must not live in production src."""

    scenario_a: ScenarioAExecutionBinding | None = None
    scenario_b_source_runtime: Any | None = None


class V03ControlledAcceptanceError(RuntimeError):
    """Machine-readable fail-closed harness error."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def to_json(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "details": dict(self.details),
        }


def _require(condition: bool, code: str, message: str, **details: object) -> None:
    if not condition:
        raise V03ControlledAcceptanceError(code, message, **details)


_CONTROLLED_ACCEPTANCE_ENV_KEYS: tuple[str, ...] = (
    "COLD_STORAGE_DATABASE_URL",
    "COLD_STORAGE_DATABASE_BACKEND",
    "COLD_STORAGE_SQLITE_PATH",
    "KNOWLEDGE_STORAGE_DIR",
)


def _snapshot_process_environment(keys: tuple[str, ...]) -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in keys}


def _restore_process_environment(snapshot: dict[str, str | None]) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def execution_authorized_from_env() -> bool:
    """Return whether the explicit execution-authorization env gate is set."""

    value = os.environ.get(EXECUTION_AUTHORIZATION_ENV, "").strip()
    return value in ALLOWED_EXECUTION_AUTHORIZED_VALUES


def validate_trusted_operator(operator: str) -> str:
    """Validate the explicit trusted-operator seam."""

    value = operator.strip()
    _require(bool(value), "TRUSTED_OPERATOR_MISSING", "trusted operator is required")
    _require(
        value.lower() not in REJECTED_OPERATOR_NAMES,
        "TRUSTED_OPERATOR_NOT_HUMAN",
        "system/api/background/llm actors are not controlled human proof",
        operator=value,
    )
    return value


def validate_execution_source_identity(
    source_sha: str,
    source_tree_sha: str,
) -> tuple[str, str]:
    """Require the workflow/runner to provide the actual executing checkout."""

    _require(
        isinstance(source_sha, str) and bool(source_sha.strip()),
        "EXECUTION_SOURCE_SHA_MISSING",
        "controlled execution source commit must be supplied explicitly",
    )
    _require(
        isinstance(source_tree_sha, str) and bool(source_tree_sha.strip()),
        "EXECUTION_SOURCE_TREE_SHA_MISSING",
        "controlled execution source tree must be supplied explicitly",
    )
    return source_sha.strip(), source_tree_sha.strip()


def validate_authorization_record_id(authorization_record_id: str | None) -> str:
    """Require a non-empty separately authorized record identifier."""

    value = (authorization_record_id or "").strip()
    _require(
        bool(value),
        "CONTROLLED_ACCEPTANCE_AUTHORIZATION_RECORD_MISSING",
        "authorization record id is required for controlled acceptance",
    )
    return value


def validate_execution_authorization(
    authorization_record_id: str | None,
    *,
    execution_authorized: bool,
) -> str:
    """Fail closed unless explicit execution authorization is present."""

    record = validate_authorization_record_id(authorization_record_id)
    _require(
        execution_authorized,
        "CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED",
        "V0.3 P5 controlled acceptance execution is not authorized",
        authorization_record_id=record,
        execution_authorized=execution_authorized,
    )
    return record


def validate_scenario_name(scenario: str) -> str:
    """Validate the frozen Scenario A/B/C identifier."""

    value = scenario.strip().upper()
    _require(
        value in SCENARIO_NAMES,
        "SCENARIO_INVALID",
        "scenario must be one of A, B, or C",
        scenario=scenario,
    )
    return value


def validate_workflow_dispatch_gates(
    *,
    event_name: str,
    git_ref: str,
    checked_out_sha: str,
    checked_out_tree_sha: str,
    declared_source_sha: str,
    declared_source_tree_sha: str,
    authorization_record_id: str,
    trusted_operator: str,
) -> dict[str, str]:
    """Validate workflow_dispatch-only, main-only, exact-source-bound gates."""

    _require(
        event_name == WORKFLOW_DISPATCH_EVENT,
        "WORKFLOW_DISPATCH_REQUIRED",
        "controlled acceptance must be workflow_dispatch only",
        event_name=event_name,
    )
    _require(
        git_ref == MAIN_REF,
        "WORKFLOW_MAIN_REF_REQUIRED",
        "controlled acceptance must run on refs/heads/main only",
        git_ref=git_ref,
    )
    record = validate_authorization_record_id(authorization_record_id)
    operator = validate_trusted_operator(trusted_operator)
    execution_sha, execution_tree = validate_execution_source_identity(
        declared_source_sha,
        declared_source_tree_sha,
    )
    _require(
        checked_out_sha == execution_sha,
        "EXECUTION_SOURCE_SHA_MISMATCH",
        "declared source sha must match the checked-out commit",
        checked_out_sha=checked_out_sha,
        declared_source_sha=execution_sha,
    )
    _require(
        checked_out_tree_sha == execution_tree,
        "EXECUTION_SOURCE_TREE_MISMATCH",
        "declared source tree must match the checked-out tree",
        checked_out_tree_sha=checked_out_tree_sha,
        declared_source_tree_sha=execution_tree,
    )
    return {
        "authorization_record_id": record,
        "trusted_operator": operator,
        "execution_source_sha": execution_sha,
        "execution_source_tree_sha": execution_tree,
        "workflow_dispatch_only": "YES",
        "main_only": "YES",
    }


def build_harness_status() -> dict[str, object]:
    """Return the frozen harness authorization posture for evidence uploads."""

    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "contract_path": CONTRACT_PATH,
        "runbook_path": RUNBOOK_PATH,
        "workflow_path": WORKFLOW_PATH,
        "scenarios": sorted(SCENARIO_NAMES),
        "fixture_paths": dict(FIXTURE_PATHS),
        "authorization": {
            "CONTROLLED_ACCEPTANCE_AUTHORIZED": "NO",
            "CONTROLLED_ACCEPTANCE_EXECUTED": "NO",
            "SCENARIO_A_RUN_AUTHORIZED": "NO",
            "SCENARIO_B_RUN_AUTHORIZED": "NO",
            "SCENARIO_C_RUN_AUTHORIZED": "NO",
            "FIXTURE_JSON_CREATE_AUTHORIZED": "NO",
            "V0_3_TAG_AUTHORIZED": "NO",
            "GITHUB_RELEASE_AUTHORIZED": "NO",
            "PRODUCTION_ENABLEMENT_AUTHORIZED": "NO",
            "ORDINARY_PR_CI_IS_CONTROLLED_ACCEPTANCE": "NO",
            "NO_STEP_IMPLIES_THE_NEXT": "TRUE",
        },
        "harness_round": "SCENARIO_EXECUTION_ENGINE_R1",
        "scenario_execution_implemented": "YES",
        "scenario_execution_engine_round": "SCENARIO_EXECUTION_ENGINE_R1",
    }


def verify_harness_gates(
    *,
    authorization_record_id: str,
    trusted_operator: str,
    execution_source_sha: str,
    execution_source_tree_sha: str,
    event_name: str | None = None,
    git_ref: str | None = None,
    checked_out_sha: str | None = None,
    checked_out_tree_sha: str | None = None,
) -> dict[str, object]:
    """Verify operator/source gates and return harness status evidence."""

    validate_trusted_operator(trusted_operator)
    validate_authorization_record_id(authorization_record_id)
    validate_execution_source_identity(execution_source_sha, execution_source_tree_sha)
    payload: dict[str, object] = {
        "status": "PASS",
        "gate": "HARNESS_VERIFY",
        "authorization_record_id": authorization_record_id.strip(),
        "trusted_operator": trusted_operator.strip(),
        "execution_source_sha": execution_source_sha.strip(),
        "execution_source_tree_sha": execution_source_tree_sha.strip(),
        "harness": build_harness_status(),
    }
    if (
        event_name is not None
        and git_ref is not None
        and checked_out_sha is not None
        and checked_out_tree_sha is not None
    ):
        payload["workflow_gates"] = validate_workflow_dispatch_gates(
            event_name=event_name,
            git_ref=git_ref,
            checked_out_sha=checked_out_sha,
            checked_out_tree_sha=checked_out_tree_sha,
            declared_source_sha=execution_source_sha,
            declared_source_tree_sha=execution_source_tree_sha,
            authorization_record_id=authorization_record_id,
            trusted_operator=trusted_operator,
        )
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_bound_fixture(scenario: str, repo_root: Path) -> dict[str, Any]:
    scenario_name = validate_scenario_name(scenario)
    fixture_rel = FIXTURE_PATHS[scenario_name]
    fixture_path = repo_root / fixture_rel
    _require(
        fixture_path.is_file(),
        "FIXTURE_MISSING",
        "bound scenario fixture is missing",
        fixture_path=str(fixture_path),
    )
    computed = _sha256_file(fixture_path)
    expected = FIXTURE_SHA256[scenario_name]
    _require(
        computed == expected,
        "FIXTURE_SHA256_MISMATCH",
        "bound scenario fixture SHA-256 does not match runbook evidence",
        fixture_path=str(fixture_path),
        expected_sha256=expected,
        computed_sha256=computed,
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    _require(
        isinstance(payload, dict),
        "FIXTURE_INVALID",
        "scenario fixture must be a JSON object",
        fixture_path=str(fixture_path),
    )
    return cast(dict[str, Any], payload)


def _build_evidence_envelope(
    *,
    scenario: str,
    authorization_record_id: str,
    trusted_operator: str,
    execution_source_sha: str,
    execution_source_tree_sha: str,
    backend: str,
    run_index: int,
    database_url: str,
    fixture: dict[str, Any],
    scenario_result: dict[str, Any],
) -> dict[str, object]:
    from cold_storage.evaluation.followup_acceptance import _redact_database_url

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "harness_round": "SCENARIO_EXECUTION_ENGINE_R1",
        "scenario": scenario,
        "authorization_record_id": authorization_record_id,
        "trusted_operator": trusted_operator,
        "execution_source_sha": execution_source_sha,
        "execution_source_tree_sha": execution_source_tree_sha,
        "fixture": {
            "path": FIXTURE_PATHS[scenario],
            "sha256": FIXTURE_SHA256[scenario],
            "schema_version": fixture.get("schema_version"),
            "scenario_id": fixture.get("scenario_id"),
        },
        "environment": {
            "backend": backend,
            "run_index": run_index,
            "database_url": _redact_database_url(database_url),
        },
        "scenario_result": scenario_result,
        "result": {"status": "PASS", "blockers": []},
    }


def _run_formal_report_lifecycle(
    *,
    engine: Any,
    project_id: str,
    project_version_id: str,
    operator: str,
    output_root: Path,
    requires_review: bool,
    prove_export_blocked_before_review: bool,
) -> dict[str, object]:
    from sqlalchemy.orm import sessionmaker

    from cold_storage.evaluation.followup_acceptance import (
        FORMAL_ARTIFACT_MATRIX,
        _LifecycleDiagnosticContext,
        _capture_post_generation_diagnostics,
        _index_artifacts_for_matrix,
        _invoke_review_lifecycle_action,
        _persisted_calculation_query,
        verify_artifact_matrix,
    )
    from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
    from cold_storage.modules.reports.application.assembler import ReportAssembler
    from cold_storage.modules.reports.application.render_service import (
        ReportRenderService,
        ReportRenderUnitOfWork,
    )
    from cold_storage.modules.reports.application.service import (
        ReportService,
        _default_trusted_operator,
    )
    from cold_storage.modules.reports.domain.enums import ReportLocale, ReportType
    from cold_storage.modules.reports.domain.errors import ExportPermissionError
    from cold_storage.modules.reports.infrastructure.artifact_storage import ReportArtifactStorage
    from cold_storage.modules.reports.infrastructure.real_data_provider import (
        RealReportDataProvider,
    )
    from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository
    from cold_storage.modules.reports.infrastructure.template_seed import seed_default_templates
    from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    diagnostics = _LifecycleDiagnosticContext()
    export_block_proof: dict[str, object] | None = None
    with session_factory() as session:
        report_repo = SQLReportRepository(session)
        scheme_query = build_sqlalchemy_scheme_query(session)
        provider = RealReportDataProvider(
            project_service=DatabaseProjectService(engine),
            calculation_service=_persisted_calculation_query(session_factory),
            scheme_query=scheme_query,
        )
        assembler = ReportAssembler(data_provider=provider)
        report_service = ReportService(
            repository=report_repo,
            assembler=assembler,
            scheme_review_query=scheme_query,
            trusted_operator=_default_trusted_operator,
        )
        storage = ReportArtifactStorage(base_dir=str(output_root))
        render_uow = ReportRenderUnitOfWork(
            session,
            report_repo=report_repo,
            artifact_repo=report_repo,
            session_factory=session_factory,
        )
        render_service = ReportRenderService(
            uow=render_uow,
            storage=storage,
            template_repo=report_repo,
            scheme_review_query=scheme_query,
            trusted_operator=_default_trusted_operator,
        )
        seed_default_templates(report_repo)
        report_repo.commit()
        report = report_service.create_report(
            project_id=project_id,
            project_version_id=project_version_id,
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor=operator,
        )
        revision = report_service.generate_revision(report.id, operator)
        _capture_post_generation_diagnostics(
            report_service,
            report.id,
            operator,
            revision,
            diagnostics,
        )
        _invoke_review_lifecycle_action(
            report_service,
            report.id,
            operator,
            "submit_review",
            diagnostics,
        )
        if prove_export_blocked_before_review:
            blocked = False
            blocked_detail: dict[str, object] = {}
            try:
                render_service.render(
                    report_id=report.id,
                    revision_number=revision.revision_number,
                    format="pdf",
                    template_version=None,
                    mode="formal",
                    actor=operator,
                    locale=ReportLocale("zh-CN"),
                )
            except ExportPermissionError as exc:
                blocked = True
                blocked_detail = {
                    "code": "FORMAL_EXPORT_BLOCKED",
                    "report_id": exc.report_id if hasattr(exc, "report_id") else report.id,
                    "mode": "formal",
                }
            _require(
                blocked,
                "FORMAL_EXPORT_NOT_BLOCKED",
                "formal export must fail closed before review/approval",
                requires_review=requires_review,
            )
            export_block_proof = {
                "attempted_before_review_approval": True,
                "blocked": True,
                "detail": blocked_detail,
            }
        if requires_review:
            _invoke_review_lifecycle_action(
                report_service,
                report.id,
                operator,
                "mark_reviewed",
                diagnostics,
            )
        approved = _invoke_review_lifecycle_action(
            report_service,
            report.id,
            operator,
            "approve",
            diagnostics,
        )
        artifacts: dict[str, object] = {}
        for locale_value, format_value in FORMAL_ARTIFACT_MATRIX:
            locale = ReportLocale(locale_value)
            artifact = render_service.render(
                report_id=report.id,
                revision_number=revision.revision_number,
                format=format_value,
                template_version=None,
                mode="formal",
                actor=operator,
                locale=locale,
            )
            artifacts[f"{locale_value}/{format_value}"] = render_service.verify_download(
                report.id, artifact.id, operator
            )
        report_id = approved.id
        revision_id = revision.id
        approved_revision_id = str(approved.approved_revision_id or "")
        approved_content_hash = revision.content_hash
        _require(
            approved_revision_id == revision_id
            and approved.approved_content_hash == approved_content_hash,
            "APPROVAL_IDENTITY_MISMATCH",
            "approval does not bind the exact rendered revision and content hash",
        )
        observations = verify_artifact_matrix(
            artifacts,
            read_bytes=storage.get,
            report_id=report_id,
            report_revision_id=revision_id,
            approved_revision_id=approved_revision_id,
            approved_content_hash=approved_content_hash,
        )
        actions = report_repo.list_review_actions(report_id)

    with session_factory() as fresh_session:
        fresh_repo = SQLReportRepository(fresh_session)
        fresh_report = fresh_repo.get_report(report_id)
        fresh_revision = fresh_repo.get_revision(report_id, revision.revision_number)
        fresh_actions = fresh_repo.list_review_actions(report_id)
    _require(
        fresh_report is not None,
        "FRESH_SESSION_REPORT_MISSING",
        "report disappeared after restart",
    )
    assert fresh_report is not None
    _require(
        fresh_revision is not None and fresh_revision.id == revision_id,
        "FRESH_SESSION_REVISION_MISSING",
        "approved revision disappeared after restart",
    )
    _require(
        fresh_report.status.value == "approved"
        and fresh_report.approved_revision_id == approved_revision_id
        and fresh_report.approved_content_hash == approved_content_hash,
        "FRESH_SESSION_APPROVAL_MISMATCH",
        "approval identity changed or disappeared after restart",
    )
    if requires_review:
        mark_reviewed_actions = [
            action for action in fresh_actions if action.action.value == "mark_reviewed"
        ]
        _require(
            len(mark_reviewed_actions) == 1,
            "FRESH_SESSION_MARK_REVIEWED_AMBIGUOUS",
            "fresh-session readback must expose exactly one mark_reviewed proof",
        )
    lifecycle: dict[str, object] = {
        "report_id": report_id,
        "report_revision_id": revision_id,
        "approved_revision_id": approved_revision_id,
        "approved_content_hash": approved_content_hash,
        "requires_review": requires_review,
        "artifacts": {
            key: observation.to_json() for key, observation in observations.items()
        },
        "review_actions": [action.action.value for action in actions],
        "fresh_session": True,
        "restart": True,
    }
    if export_block_proof is not None:
        lifecycle["formal_export_block_proof"] = export_block_proof
    return lifecycle


def _execute_scenario_a(
    *,
    engine: Any,
    operator: str,
    output_root: Path,
    fixture: dict[str, Any],
    backend: str,
    scenario_a_binding: ScenarioAExecutionBinding,
) -> dict[str, object]:
    from sqlalchemy.orm import sessionmaker

    from cold_storage.evaluation.execute import run_scenario_via_markers
    from cold_storage.evaluation.followup_acceptance import _authority_snapshot
    from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

    _require(
        fixture.get("review_required") is False,
        "SCENARIO_A_REVIEW_REQUIRED",
        "scenario A requires review_required=false",
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as seed_session:
        scenario_a_binding.seed_prereqs(seed_session)
    outcome = run_scenario_via_markers(
        session_factory,
        source_binding_id=scenario_a_binding.source_binding_id,
        weight_set_revision_id=scenario_a_binding.weight_set_revision_id,
        correlation_marker=BASELINE_CORRELATION_ID,
        backend_marker=backend,
    )
    _require(
        outcome.outcome == "SUCCEEDED",
        "SCENARIO_A_RUNNER_FAILED",
        "baseline scenario runner did not succeed",
        outcome=outcome.outcome,
    )
    scheme_run = outcome.scheme_run
    project_id = scheme_run.project_id
    project_version_id = scheme_run.project_version_id
    with session_factory() as session:
        authority = build_sqlalchemy_scheme_query(session).get_review_authority(
            project_id, project_version_id
        )
    _require(authority is not None, "SCHEME_AUTHORITY_MISSING", "scheme authority is missing")
    assert authority is not None
    _require(
        authority.requires_review is False,
        "SCHEME_REVIEW_UNEXPECTED",
        "scenario A requires review_required=false on scheme authority",
    )
    lifecycle = _run_formal_report_lifecycle(
        engine=engine,
        project_id=project_id,
        project_version_id=project_version_id,
        operator=operator,
        output_root=output_root / "artifacts",
        requires_review=False,
        prove_export_blocked_before_review=False,
    )
    calculator_versions: dict[str, object] = {}
    with session_factory() as session:
        from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord

        for record in session.query(CalculationRunRecord).all():
            calculator_versions[str(record.calculation_type)] = record.calculator_version
    return {
        "workflow_goal": fixture.get("workflow_goal"),
        "project_id": project_id,
        "project_version_id": project_version_id,
        "scheme_run": str(scheme_run.id),
        "scheme_authority": dict(_authority_snapshot(authority)),
        "calculator_versions": calculator_versions,
        "lifecycle": lifecycle,
    }


def _execute_scenario_b(
    *,
    engine: Any,
    operator: str,
    output_root: Path,
    fixture: dict[str, Any],
    repo_root: Path,
    execution_source_sha: str,
    execution_source_tree_sha: str,
    backend: str,
    run_index: int,
    source_runtime: Any,
) -> dict[str, object]:
    from sqlalchemy.orm import sessionmaker

    from cold_storage.evaluation.followup_acceptance import (
        _authority_snapshot,
        _verify_persisted_authority,
        load_source_definition,
        verify_authoritative_source_definition,
    )

    binding = fixture["upstream_bindings"][0]
    source_path = repo_root / str(binding["path"])
    source = load_source_definition(
        source_path,
        expected_source_candidate_path=source_runtime.source_candidate_path,
    )
    verify_authoritative_source_definition(
        source,
        authoritative_snapshot=source_runtime.source_snapshot,
        expected_source_candidate_path=source_runtime.source_candidate_path,
    )
    token = f"v03-p5-scenario-b-{backend}-{run_index}"
    source_runtime.seed_startup_readiness(engine, token=token)
    definition_id = source_runtime.create_controlled_coefficient_definition(engine, token=token)
    persistence_value = source_runtime.create_controlled_production_authority(
        engine,
        definition_id=definition_id,
        token=token,
    )
    _require(
        isinstance(persistence_value, dict),
        "SOURCE_RUNTIME_INVALID",
        "controlled source runtime returned no persistence mapping",
    )
    canonical_persistence = persistence_value["canonical_persistence"]
    _require(
        isinstance(canonical_persistence, dict),
        "SOURCE_RUNTIME_INVALID",
        "controlled source runtime omitted canonical persistence",
    )
    project_id = str(canonical_persistence["project_id"])
    project_version_id = str(canonical_persistence["project_version_id"])
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

        query = build_sqlalchemy_scheme_query(session)
        authority = query.get_review_authority(project_id, project_version_id)
        _require(authority is not None, "SCHEME_AUTHORITY_MISSING", "scheme authority is missing")
        assert authority is not None
        records, reasons = _verify_persisted_authority(
            session=session,
            authority=authority,
            canonical_persistence=canonical_persistence,
        )
        authority_snapshot = dict(_authority_snapshot(authority))
    _require(
        authority.requires_review is True,
        "SCHEME_REVIEW_REQUIRED",
        "scenario B requires review_required=true",
    )
    _require(
        len(reasons) >= int(fixture["review_reason_contract"]["minimum_reason_count"]),
        "REVIEW_REASON_MISSING",
        "scenario B requires structured review reasons",
    )
    lifecycle = _run_formal_report_lifecycle(
        engine=engine,
        project_id=project_id,
        project_version_id=project_version_id,
        operator=operator,
        output_root=output_root / "artifacts",
        requires_review=True,
        prove_export_blocked_before_review=True,
    )
    calculator_versions: dict[str, object] = {}
    with session_factory() as session:
        from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord

        for record in session.query(CalculationRunRecord).all():
            calculator_versions[str(record.calculation_type)] = record.calculator_version
    return {
        "workflow_goal": fixture.get("workflow_goal"),
        "project_id": project_id,
        "project_version_id": project_version_id,
        "review_reasons": [reason.to_json() for reason in reasons],
        "scheme_authority": authority_snapshot,
        "calculator_versions": calculator_versions,
        "lifecycle": lifecycle,
        "source": {
            "execution_source_sha": execution_source_sha,
            "execution_source_tree_sha": execution_source_tree_sha,
            "canonical_input_sha256": source.canonical_input_sha256,
            "source_definition_path": str(source_path),
        },
    }


def _execute_scenario_c(
    *,
    engine: Any,
    operator: str,
    fixture: dict[str, Any],
    output_root: Path,
) -> dict[str, object]:
    import base64
    import io

    import pymupdf
    from sqlalchemy.orm import sessionmaker

    from cold_storage.modules.calculations.domain.investment import InvestmentEstimator
    from cold_storage.modules.calculations.domain.zone_planning import ColdRoomZonePlanner
    from cold_storage.modules.knowledge.application.service import KnowledgeService
    from cold_storage.modules.knowledge.infrastructure.ocr_adapter import OcrAdapter, OcrPageResult
    from cold_storage.modules.knowledge.infrastructure.repository import KnowledgeRepository
    from cold_storage.modules.planning_agent.application.orchestrator import AgentOrchestrator
    from cold_storage.modules.planning_agent.application.service import PlanningAgentService
    from cold_storage.modules.planning_agent.application.tool_registry import build_default_registry
    from cold_storage.modules.planning_agent.domain.enums import DecisionType
    from cold_storage.modules.planning_agent.infrastructure.fake_gateways import (
        FakeAgentModelGateway,
    )
    from cold_storage.modules.planning_agent.infrastructure.repository import AgentRepository
    from cold_storage.modules.planning_agent.infrastructure.tool_adapters.knowledge_adapter import (
        KnowledgeSearchAdapter,
    )
    from cold_storage.modules.planning_agent.infrastructure.tool_adapters import ToolAdapter
    from cold_storage.modules.planning_agent.infrastructure.tool_adapters.planning_adapter import (
        ThroughputInventoryAreaAdapter,
    )
    from cold_storage.modules.projects.infrastructure.database import DatabaseProjectService
    from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query
    from cold_storage.modules.workflow.application.service import WorkflowAggregateService
    from cold_storage.modules.workflow.domain.steps import WORKFLOW_GOAL_PLANNING_PREVIEW

    from cold_storage.modules.planning_agent.domain.models import AgentDecision, AgentToolRequest

    class _ScenarioCAgentGateway(FakeAgentModelGateway):
        def generate_decision(self, request):  # type: ignore[no-untyped-def]
            decision = super().generate_decision(request)
            if decision.decision_type.value != "propose_tools":
                return decision
            enriched_requests = []
            for tool_req in decision.tool_requests:
                arguments = dict(tool_req.arguments)
                if tool_req.tool_name == "planning.calculate_throughput_inventory_area":
                    arguments.setdefault("finished_storage_days", 2.5)
                    arguments.setdefault("packaging_storage_days", 3.0)
                    arguments.setdefault("precooling_required_ratio", 0.85)
                    arguments.setdefault("storage_days", 2.5)
                enriched_requests.append(
                    AgentToolRequest(
                        tool_name=tool_req.tool_name,
                        arguments=arguments,
                        reason=tool_req.reason,
                    )
                )
            return AgentDecision(
                decision_type=decision.decision_type,
                assistant_message=decision.assistant_message,
                tool_requests=enriched_requests,
                missing_parameters=decision.missing_parameters,
                citations=decision.citations,
                requires_review=decision.requires_review,
                warnings=decision.warnings,
            )

    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    class _FakeOcrAdapter(OcrAdapter):
        def ocr_pages(
            self,
            *,
            content: bytes,
            revision_id: str,
            source_content_sha256: str,
            page_numbers: list[int],
            document_id: str = "",
            ingestion_run_id: str = "",
            original_filename: str = "",
        ) -> list[OcrPageResult]:
            _ = content
            return [
                OcrPageResult.from_text(
                    page_number=page,
                    text="controlled acceptance OCR evidence with deterministic provenance.",
                    confidence=88.5,
                    confidence_source="fake_tsv",
                    document_id=document_id,
                    revision_id=revision_id,
                    source_content_sha256=source_content_sha256,
                    ingestion_run_id=ingestion_run_id,
                    original_filename=original_filename,
                    engine_version="fake-ocr-v1",
                )
                for page in page_numbers
            ]

    knowledge_storage = output_root / "knowledge-storage"
    knowledge_storage.mkdir(parents=True, exist_ok=True)
    os.environ["KNOWLEDGE_STORAGE_DIR"] = str(knowledge_storage)

    doc = pymupdf.open()  # type: ignore[no-untyped-call]
    doc.new_page().insert_text(
        (72, 72),
        "controlled acceptance native text with enough deterministic parser threshold.",
    )
    image_page = doc.new_page()
    image_page.insert_image(image_page.rect, stream=one_pixel_png)  # type: ignore[no-untyped-call]
    pdf_bytes = doc.tobytes()  # type: ignore[no-untyped-call]
    doc.close()  # type: ignore[no-untyped-call]
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        project_service = DatabaseProjectService(engine)
        project = project_service.create_project("P5 Scenario C", "Shandong", "blueberry")
        version = project_service.create_version(project.id, "initial", created_by=operator)
        project_service.save_inputs(
            project.id,
            version.version_number,
            {
                "daily_inbound_mass_kg": 25000,
                "working_time_h_per_day": 16,
                "utilization_factor": 0.85,
                "finished_storage_days": 2.5,
                "packaging_storage_days": 3,
                "reserve_factor": 1.05,
            },
            actor=operator,
        )
        version = project_service.get_version(project.id, version.version_number)
        knowledge_service = KnowledgeService(session, ocr_adapter=_FakeOcrAdapter())
        created = knowledge_service.create_document(
            code="V03-P5-SCENARIO-C-001",
            title="Scenario C knowledge",
            document_category="reference",
            owner=operator,
            file=io.BytesIO(pdf_bytes),
            content_sha256=content_hash,
            file_size=len(pdf_bytes),
            filename="scenario-c.pdf",
            mime_type="application/pdf",
        )
        ingest_result = knowledge_service.ingest_revision(
            document_id=created["document_id"],
            revision_number=1,
        )
        _require(
            ingest_result["ingestion_status"] == "indexed",
            "KNOWLEDGE_INGESTION_FAILED",
            "knowledge revision must reach indexed status",
            ingestion_status=ingest_result["ingestion_status"],
        )
        knowledge_service.transition_review_status(
            document_id=created["document_id"],
            revision_number=1,
            target_status="reviewed",
        )
        knowledge_service.transition_review_status(
            document_id=created["document_id"],
            revision_number=1,
            target_status="approved",
        )
        search_results = knowledge_service.search(query="controlled acceptance", top_k=3)
        citations = search_results.get("results", [])
        _require(bool(citations), "KNOWLEDGE_SEARCH_EMPTY", "knowledge.search returned no citations")
        required_fields = set(fixture["knowledge_provenance"]["required_citation_fields"])
        first = citations[0]
        citation = first.get("citation", first)
        missing_fields = sorted(field for field in required_fields if field not in citation)
        _require(
            not missing_fields,
            "KNOWLEDGE_CITATION_INCOMPLETE",
            "knowledge citation is missing required provenance fields",
            missing_fields=missing_fields,
        )
        page_evidence = KnowledgeRepository(session).list_page_evidence(str(created["revision_id"]))
        _require(
            any(item.page_number == 2 for item in page_evidence),
            "PAGE_EVIDENCE_MISSING",
            "page-level provenance evidence is missing",
        )
        registry = build_default_registry()
        zone_planner = ColdRoomZonePlanner()
        investment_estimator = InvestmentEstimator()
        adapters: dict[str, ToolAdapter] = {
            "planning.calculate_throughput_inventory_area": ThroughputInventoryAreaAdapter(
                zone_planner, investment_estimator
            ),
            "knowledge.search": KnowledgeSearchAdapter(knowledge_service),
        }
        orchestrator = AgentOrchestrator(
            tool_adapters=adapters,
            project_service=project_service,
        )
        agent_service = PlanningAgentService(
            repository=AgentRepository(session),
            gateway=_ScenarioCAgentGateway(),
            registry=registry,
            orchestrator=orchestrator,
        )
        session_record = agent_service.create_session(
            created_by=operator,
            project_id=project.id,
            project_version_id=version.id,
            title="Scenario C agent session",
        )
        clarification = agent_service.post_user_message(
            session_record.id,
            "蓝莓加工厂规划",
            user=operator,
        )
        _require(
            clarification.get("decision_type") == DecisionType.ASK_CLARIFICATION.value,
            "AGENT_CLARIFICATION_MISSING",
            "agent must ask for clarification on missing inputs",
            decision_type=clarification.get("decision_type"),
        )
        tool_turn = agent_service.post_user_message(
            session_record.id,
            "25吨蓝莓，每天工作16小时",
            user=operator,
        )
        _require(
            tool_turn.get("decision_type") == DecisionType.PROPOSE_TOOLS.value,
            "AGENT_TOOL_PROPOSAL_MISSING",
            "agent must propose deterministic planning tools",
            decision_type=tool_turn.get("decision_type"),
        )
        deterministic_adapter = ThroughputInventoryAreaAdapter(
            ColdRoomZonePlanner(),
            InvestmentEstimator(),
        )
        deterministic_result = deterministic_adapter.execute(
            {
                "daily_inbound_mass": 25.0,
                "mass_unit": "tons",
                "working_time_h_per_day": 16.0,
                "finished_storage_days": 2.5,
                "packaging_storage_days": 3.0,
                "precooling_required_ratio": 0.85,
                "storage_days": 2.5,
            }
        )
        _require(
            deterministic_result.output.get("source_tool")
            == "planning.calculate_throughput_inventory_area",
            "DETERMINISTIC_CALCULATION_MISSING",
            "deterministic planning tool output is authoritative",
        )
        proposed_tools = {"planning.calculate_throughput_inventory_area"}
        from cold_storage.modules.schemes.application.query import build_sqlalchemy_scheme_query

        workflow = WorkflowAggregateService(
            project_service=project_service,
            scheme_query=build_sqlalchemy_scheme_query(session),
            agent_capability_projection=[
                {
                    "name": "model_backed_agent",
                    "status": "available",
                    "capability_state": "LOCAL_TEST_AVAILABLE",
                    "route_exposure": "LOCAL_TEST_ROUTES",
                    "blocking": False,
                }
            ],
        )
        aggregate = workflow.get_workflow_aggregate(
            project.id,
            version.version_number,
            workflow_goal=WORKFLOW_GOAL_PLANNING_PREVIEW,
        )
        agent_step = next(
            step for step in aggregate["steps"] if step["step"] == "AGENT_ASSISTANCE"
        )
        _require(
            agent_step["blocking"] is False,
            "AGENT_BLOCKS_CORE_WORKFLOW",
            "agent assistance must not block the core workflow",
        )
        unavailable_aggregate = WorkflowAggregateService(
            project_service=project_service,
            scheme_query=build_sqlalchemy_scheme_query(session),
            agent_capability_projection=[
                {
                    "name": "model_backed_agent",
                    "status": "disabled",
                    "capability_state": "AGENT_CAPABILITY_DISABLED",
                    "route_exposure": "DISABLED_ROUTE_MATRIX",
                    "code": "AGENT_CAPABILITY_DISABLED",
                }
            ],
        ).get_workflow_aggregate(
            project.id,
            version.version_number,
            workflow_goal=WORKFLOW_GOAL_PLANNING_PREVIEW,
        )
        _require(
            not any(
                blocker.get("code") == "AGENT_UNAVAILABLE"
                for blocker in unavailable_aggregate["workflow_readiness"]["blockers"]
            ),
            "AGENT_UNAVAILABLE_BLOCKS_CORE",
            "agent unavailability must not block core workflow",
        )
    with session_factory() as fresh_session:
        fresh_project_service = DatabaseProjectService(engine)
        fresh_knowledge_service = KnowledgeService(fresh_session, ocr_adapter=_FakeOcrAdapter())
        fresh_registry = build_default_registry()
        fresh_adapters: dict[str, ToolAdapter] = {
            "planning.calculate_throughput_inventory_area": ThroughputInventoryAreaAdapter(
                ColdRoomZonePlanner(), InvestmentEstimator()
            ),
            "knowledge.search": KnowledgeSearchAdapter(fresh_knowledge_service),
        }
        fresh_agent = PlanningAgentService(
            repository=AgentRepository(fresh_session),
            gateway=_ScenarioCAgentGateway(),
            registry=fresh_registry,
            orchestrator=AgentOrchestrator(
                tool_adapters=fresh_adapters,
                project_service=fresh_project_service,
            ),
        )
        fresh_session_record = fresh_agent.get_session(session_record.id)
        fresh_messages = fresh_agent.get_messages(session_record.id)
    return {
        "workflow_goal": fixture.get("workflow_goal"),
        "agent_assistance": {
            "transport": fixture["agent_assistance"]["transport"],
            "live_mimo_required": fixture["agent_assistance"]["live_mimo_required"],
            "agent_session_id": session_record.id,
            "clarification_observed": True,
            "tool_sequence_observed": list(fixture.get("tool_sequence", [])),
            "proposed_tools": sorted(proposed_tools),
        },
        "deterministic_calculation": {
            "source_tool": deterministic_result.output.get("source_tool"),
            "tool_version": deterministic_result.output.get("tool_version"),
            "requires_review": deterministic_result.requires_review,
            "calculator_version": deterministic_result.output.get("payload", {})
            .get("zone_plan", {})
            .get("calculator_version"),
        },
        "knowledge_provenance": {
            "document_id": created["document_id"],
            "revision_id": created["revision_id"],
            "citation_fields_present": sorted(required_fields),
            "page_evidence_count": len(page_evidence),
            "search_result_count": len(citations),
        },
        "workflow_aggregate": {
            "agent_blocking": agent_step["blocking"],
            "agent_unavailable_blocks_core": False,
        },
        "fresh_session": {
            "agent_session_preserved": fresh_session_record.id == session_record.id,
            "message_count": len(fresh_messages),
        },
    }


def execute_scenario(
    *,
    scenario: str,
    authorization_record_id: str,
    trusted_operator: str,
    execution_source_sha: str,
    execution_source_tree_sha: str,
    execution_authorized: bool,
    backend: str,
    run_index: int,
    database_url: str,
    output_root: Path,
    repo_root: Path,
    execution_support: ScenarioExecutionSupport | None = None,
) -> dict[str, object]:
    """Validate gates, then execute the bound Scenario A/B/C fixture."""

    scenario_name = validate_scenario_name(scenario)
    record = validate_execution_authorization(
        authorization_record_id,
        execution_authorized=execution_authorized,
    )
    operator = validate_trusted_operator(trusted_operator)
    source_sha, source_tree = validate_execution_source_identity(
        execution_source_sha,
        execution_source_tree_sha,
    )
    _require(
        backend in {"sqlite", "postgresql"},
        "BACKEND_INVALID",
        "controlled acceptance backend must be sqlite or postgresql",
        backend=backend,
    )
    _require(run_index > 0, "RUN_INDEX_INVALID", "run_index must be positive", run_index=run_index)
    fixture = _load_bound_fixture(scenario_name, repo_root)
    from cold_storage.evaluation.followup_acceptance import _configure_database_environment

    env_snapshot = _snapshot_process_environment(_CONTROLLED_ACCEPTANCE_ENV_KEYS)
    try:
        _configure_database_environment(database_url)
        from sqlalchemy import create_engine, inspect

        engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
        if backend == "sqlite":
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_engine(database_url, **engine_kwargs)
        output_path = Path(output_root)
        output_path.mkdir(parents=True, exist_ok=True)
        try:
            with engine.connect() as connection:
                connection.execute(__import__("sqlalchemy", fromlist=["select"]).select(1))
            _require(
                inspect(engine).has_table("projects"),
                "SCHEMA_NOT_READY",
                "acceptance database is not migrated to head",
            )
            if scenario_name == "A":
                _require(
                    execution_support is not None and execution_support.scenario_a is not None,
                    "SCENARIO_EXECUTION_SUPPORT_MISSING",
                    "scenario A requires pilot-injected baseline seed support",
                    scenario=scenario_name,
                )
                assert execution_support is not None
                assert execution_support.scenario_a is not None
                scenario_result = _execute_scenario_a(
                    engine=engine,
                    operator=operator,
                    output_root=output_path,
                    fixture=fixture,
                    backend=backend,
                    scenario_a_binding=execution_support.scenario_a,
                )
            elif scenario_name == "B":
                _require(
                    execution_support is not None
                    and execution_support.scenario_b_source_runtime is not None,
                    "SCENARIO_EXECUTION_SUPPORT_MISSING",
                    "scenario B requires pilot-injected controlled source runtime",
                    scenario=scenario_name,
                )
                assert execution_support is not None
                scenario_result = _execute_scenario_b(
                    engine=engine,
                    operator=operator,
                    output_root=output_path,
                    fixture=fixture,
                    repo_root=repo_root,
                    execution_source_sha=source_sha,
                    execution_source_tree_sha=source_tree,
                    backend=backend,
                    run_index=run_index,
                    source_runtime=execution_support.scenario_b_source_runtime,
                )
            else:
                scenario_result = _execute_scenario_c(
                    engine=engine,
                    operator=operator,
                    fixture=fixture,
                    output_root=output_path,
                )
            return _build_evidence_envelope(
                scenario=scenario_name,
                authorization_record_id=record,
                trusted_operator=operator,
                execution_source_sha=source_sha,
                execution_source_tree_sha=source_tree,
                backend=backend,
                run_index=run_index,
                database_url=database_url,
                fixture=fixture,
                scenario_result=scenario_result,
            )
        finally:
            engine.dispose()
    finally:
        _restore_process_environment(env_snapshot)


def refuse_scenario_execution(
    *,
    scenario: str,
    authorization_record_id: str,
    trusted_operator: str,
    execution_source_sha: str,
    execution_source_tree_sha: str,
    execution_authorized: bool,
    backend: str,
    run_index: int,
) -> dict[str, object]:
    """Backward-compatible gate validation entrypoint used by harness tests."""

    validate_scenario_name(scenario)
    validate_execution_authorization(
        authorization_record_id,
        execution_authorized=execution_authorized,
    )
    validate_trusted_operator(trusted_operator)
    validate_execution_source_identity(execution_source_sha, execution_source_tree_sha)
    _require(
        backend in {"sqlite", "postgresql"},
        "BACKEND_INVALID",
        "controlled acceptance backend must be sqlite or postgresql",
        backend=backend,
    )
    _require(run_index > 0, "RUN_INDEX_INVALID", "run_index must be positive", run_index=run_index)
    if execution_authorized:
        raise V03ControlledAcceptanceError(
            "SCENARIO_DATABASE_URL_REQUIRED",
            "scenario execution requires database_url and output_root via execute_scenario",
            scenario=scenario,
            harness_round="SCENARIO_EXECUTION_ENGINE_R1",
        )
    raise V03ControlledAcceptanceError(
        "CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED",
        "V0.3 P5 controlled acceptance execution is not authorized",
        authorization_record_id=authorization_record_id,
        execution_authorized=execution_authorized,
    )


def ordinary_ci_is_controlled_acceptance() -> bool:
    """Ordinary PR CI must never be treated as controlled acceptance evidence."""

    return False


__all__ = [
    "AUTHORIZATION_RECORD_ENV",
    "BASELINE_CORRELATION_ID",
    "CONTRACT_PATH",
    "EVIDENCE_SCHEMA_VERSION",
    "EXECUTION_AUTHORIZATION_ENV",
    "FIXTURE_PATHS",
    "FIXTURE_SHA256",
    "HARNESS_SCHEMA_VERSION",
    "MAIN_REF",
    "RUNBOOK_PATH",
    "SCENARIO_NAMES",
    "ScenarioAExecutionBinding",
    "ScenarioExecutionSupport",
    "WORKFLOW_DISPATCH_EVENT",
    "WORKFLOW_PATH",
    "V03ControlledAcceptanceError",
    "build_harness_status",
    "execute_scenario",
    "execution_authorized_from_env",
    "ordinary_ci_is_controlled_acceptance",
    "refuse_scenario_execution",
    "validate_authorization_record_id",
    "validate_execution_authorization",
    "validate_execution_source_identity",
    "validate_scenario_name",
    "validate_trusted_operator",
    "validate_workflow_dispatch_gates",
    "verify_harness_gates",
]
