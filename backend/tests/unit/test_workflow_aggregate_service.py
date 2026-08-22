"""Unit tests for workflow aggregation service."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.domain.models import ProjectVersion
from cold_storage.modules.reports.domain.enums import ReportStatus, ReportType
from cold_storage.modules.reports.domain.models import Report, ReportRevision
from cold_storage.modules.schemes.application.query import SchemeReviewAuthority
from cold_storage.modules.workflow.application.service import WorkflowAggregateService
from cold_storage.modules.workflow.domain.steps import (
    WORKFLOW_GOAL_FORMAL_REPORT,
    WORKFLOW_GOAL_PLANNING_PREVIEW,
)


class _SchemeQueryStub:
    def __init__(
        self,
        runs: list[dict[str, Any]] | None = None,
        authority: SchemeReviewAuthority | None = None,
    ) -> None:
        self._runs = runs or []
        self._authority = authority

    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        return self._runs

    def get_completed_runs_for_project_version(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        return [run for run in self._runs if run.get("project_version_id") == version_id]

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        return []

    def get_review_authority(
        self, project_id: str, version_id: str
    ) -> SchemeReviewAuthority | None:
        return self._authority


def _sample_revision(
    *,
    report_id: str = "report-1",
    revision_id: str = "rev-1",
    content_json: dict[str, Any] | None = None,
    content_hash: str = "hash-1",
) -> ReportRevision:
    return ReportRevision(
        id=revision_id,
        report_id=report_id,
        revision_number=1,
        schema_version="1.0.0",
        content_json=content_json or {},
        canonical_content_json=content_json or {},
        content_hash=content_hash,
        quality_status=ReportStatus.GENERATED,
        quality_findings_json=[],
        generated_by="operator",
    )


def _sample_report(
    *,
    report_id: str = "report-1",
    project_id: str,
    project_version_id: str,
) -> Report:
    return Report(
        id=report_id,
        project_id=project_id,
        project_version_id=project_version_id,
        report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
        status=ReportStatus.GENERATED,
        current_revision_number=1,
        created_by="operator",
    )


class _ReportRepoStub:
    def __init__(self, report: Report | None, revision: ReportRevision | None) -> None:
        self._report = report
        self._revision = revision

    def list_reports(
        self, project_id: str | None = None, created_by: str | None = None
    ) -> list[Report]:
        if self._report is None or project_id != self._report.project_id:
            return []
        return [self._report]

    def get_latest_revision(self, report_id: str) -> ReportRevision | None:
        if self._report is None or report_id != self._report.id:
            return None
        return self._revision

    def list_review_actions(
        self,
        report_id: str,
        *,
        report_revision_id: str | None = None,
        action: Any | None = None,
    ) -> list[Any]:
        return []


def _seed_project_with_inputs(service: ProjectService) -> tuple[str, int, ProjectVersion]:
    project = service.create_project("Demo", "Shandong", "blueberry")
    version = service.create_version(project.id, "initial", created_by="operator")
    version_number = version.version_number
    service.save_inputs(
        project.id,
        version_number,
        {
            "daily_inbound_mass_kg": 25000,
            "working_time_h_per_day": 16,
            "utilization_factor": 0.85,
            "finished_storage_days": 2.5,
            "packaging_storage_days": 3,
            "reserve_factor": 1.05,
        },
        actor="operator",
    )
    version = service.get_version(project.id, version_number)
    return project.id, version_number, version


def test_agent_unavailable_does_not_block_core_workflow() -> None:
    project_service = ProjectService()
    project_id, version_number, version = _seed_project_with_inputs(project_service)
    workflow = WorkflowAggregateService(
        project_service=project_service,
        scheme_query=_SchemeQueryStub(),
        agent_capability_projection=[
            {
                "name": "model_backed_agent",
                "status": "disabled",
                "capability_state": "AGENT_CAPABILITY_DISABLED",
                "route_exposure": "DISABLED_ROUTE_MATRIX",
                "code": "AGENT_CAPABILITY_DISABLED",
            }
        ],
    )
    aggregate = workflow.get_workflow_aggregate(project_id, version_number)
    agent_step = next(step for step in aggregate["steps"] if step["step"] == "AGENT_ASSISTANCE")
    assert agent_step["applicability"] == "OPTIONAL"
    assert agent_step["blocking"] is False
    assert agent_step["status"] == "UNAVAILABLE"
    assert aggregate["agent_assistance"]["available"] is False
    assert not any(
        blocker.get("code") == "AGENT_UNAVAILABLE"
        for blocker in aggregate["workflow_readiness"]["blockers"]
    )


def test_local_test_agent_capability_is_available_without_blocking_core() -> None:
    project_service = ProjectService()
    project_id, version_number, _ = _seed_project_with_inputs(project_service)
    workflow = WorkflowAggregateService(
        project_service=project_service,
        scheme_query=_SchemeQueryStub(),
        agent_capability_projection=[
            {
                "name": "model_backed_agent",
                "status": "available",
                "code": None,
                "blocking": False,
                "capability_state": "LOCAL_TEST_AVAILABLE",
                "route_exposure": "LOCAL_TEST_ROUTES",
            }
        ],
    )
    aggregate = workflow.get_workflow_aggregate(project_id, version_number)
    assert aggregate["agent_assistance"]["available"] is True
    assert aggregate["agent_assistance"]["status"] == "AVAILABLE"
    assert aggregate["agent_assistance"]["capability_state"] == "LOCAL_TEST_AVAILABLE"
    assert "active_provider" not in aggregate["agent_assistance"]
    assert "active_model" not in aggregate["agent_assistance"]
    agent_step = next(step for step in aggregate["steps"] if step["step"] == "AGENT_ASSISTANCE")
    assert agent_step["blocking"] is False
    assert agent_step["status"] == "COMPLETED"
    assert not any(
        blocker.get("code") == "AGENT_UNAVAILABLE"
        for blocker in aggregate["workflow_readiness"]["blockers"]
    )


def test_planning_preview_does_not_block_on_formal_export_blockers() -> None:
    project_service = ProjectService()
    project_id, version_number, _ = _seed_project_with_inputs(project_service)
    workflow = WorkflowAggregateService(
        project_service=project_service,
        scheme_query=_SchemeQueryStub(),
    )
    aggregate = workflow.get_workflow_aggregate(
        project_id,
        version_number,
        workflow_goal=WORKFLOW_GOAL_PLANNING_PREVIEW,
    )
    formal_step = next(step for step in aggregate["steps"] if step["step"] == "FORMAL_REPORT")
    report_step = next(step for step in aggregate["steps"] if step["step"] == "REPORT_ELIGIBILITY")
    assert formal_step["applicability"] == "NOT_APPLICABLE"
    assert report_step["applicability"] == "NOT_APPLICABLE"
    assert aggregate["formal_export_eligibility"]["eligible"] is False

    aggregate_codes = {blocker.get("code") for blocker in aggregate["blockers"]}
    readiness_codes = {
        blocker.get("code") for blocker in aggregate["workflow_readiness"]["blockers"]
    }
    formal_codes = {
        blocker.get("code") for blocker in aggregate["formal_export_eligibility"]["blockers"]
    }

    assert "REPORT_MISSING" not in aggregate_codes
    assert "REPORT_MISSING" not in readiness_codes
    for code in formal_codes:
        assert code not in aggregate_codes
        assert code not in readiness_codes


def test_knowledge_provenance_not_required_without_dependency() -> None:
    project_service = ProjectService()
    project_id, version_number, _ = _seed_project_with_inputs(project_service)
    workflow = WorkflowAggregateService(project_service=project_service)
    aggregate = workflow.get_workflow_aggregate(project_id, version_number)
    knowledge_step = next(
        step for step in aggregate["steps"] if step["step"] == "KNOWLEDGE_PROVENANCE"
    )
    assert knowledge_step["applicability"] == "CONDITIONAL"
    assert knowledge_step["blocking"] is False
    assert aggregate["knowledge_provenance"]["status"] == "NOT_REQUIRED"


def test_knowledge_provenance_blocks_only_when_dependency_incomplete() -> None:
    project_service = ProjectService()
    project_id, version_number, version = _seed_project_with_inputs(project_service)
    revision = _sample_revision(
        report_id="report-1",
        revision_id="rev-knowledge",
        content_json={
            "source_references": [
                {
                    "source_type": "knowledge_revision",
                    "source_id": "krev-1",
                }
            ]
        },
    )
    report = _sample_report(
        project_id=project_id,
        project_version_id=version.id,
    )

    def _revision_reader(revision_id: str) -> dict[str, Any] | None:
        return {
            "id": revision_id,
            "document_id": "doc-1",
            "content_sha256": "sha",
            "requires_review": False,
            "requires_ocr": True,
            "ingestion_status": "requires_ocr",
        }

    workflow = WorkflowAggregateService(
        project_service=project_service,
        report_repository=_ReportRepoStub(report, revision),
        knowledge_revision_reader=_revision_reader,
        knowledge_page_evidence_reader=lambda _revision_id: [],
    )
    aggregate = workflow.get_workflow_aggregate(project_id, version_number)
    knowledge_step = next(
        step for step in aggregate["steps"] if step["step"] == "KNOWLEDGE_PROVENANCE"
    )
    assert knowledge_step["blocking"] is True
    assert aggregate["knowledge_provenance"]["status"] in {"PENDING", "INVALID"}
    assert any(
        "OCR detection is not OCR evidence" in blocker.get("message", "")
        for blocker in aggregate["knowledge_provenance"]["blockers"]
    )


def test_formal_export_projection_does_not_override_p1_gate() -> None:
    project_service = ProjectService()
    project_id, version_number, version = _seed_project_with_inputs(project_service)
    revision = _sample_revision(
        content_json={"scheme_comparison": {"review_authority": {"combined_source_hash": "abc"}}},
    )
    report = _sample_report(
        project_id=project_id,
        project_version_id=version.id,
    )
    workflow = WorkflowAggregateService(
        project_service=project_service,
        scheme_query=_SchemeQueryStub(),
        report_repository=_ReportRepoStub(report, revision),
    )
    aggregate = workflow.get_workflow_aggregate(
        project_id,
        version_number,
        workflow_goal=WORKFLOW_GOAL_FORMAL_REPORT,
    )
    assert aggregate["formal_export_eligibility"]["eligible"] is False
    assert aggregate["formal_export_eligibility"]["authority_owner"] == (
        "reports_module_p1_lifecycle"
    )
    assert aggregate["formal_export_eligibility"]["revalidation_required"] is True
    assert aggregate["workflow_readiness"]["status"] in {"NOT_READY", "BLOCKED", "STALE"}


def test_partial_ocr_is_not_complete_provenance() -> None:
    from cold_storage.modules.workflow.application.knowledge_provenance import (
        assess_knowledge_provenance,
    )

    projection = assess_knowledge_provenance(
        depends_on_knowledge=True,
        knowledge_revisions=[
            {
                "id": "krev-1",
                "document_id": "doc-1",
                "content_sha256": "sha",
                "requires_review": False,
                "requires_ocr": True,
                "ingestion_status": "indexed",
            }
        ],
        page_evidence_by_revision={
            "krev-1": [
                {
                    "source_page_evidence_id": "spe-1",
                    "page_number": 1,
                    "extraction_status": "failed",
                    "is_complete": False,
                    "is_ocr_derived": True,
                }
            ]
        },
    )
    assert projection["status"] in {"PENDING", "INVALID"}
    assert any(
        "Partial OCR is not complete provenance" in b["message"] for b in projection["blockers"]
    )


def test_workflow_service_is_read_only_surface() -> None:
    """Aggregation service exposes get_workflow_aggregate only for mutation-free use."""
    service = WorkflowAggregateService(project_service=ProjectService())
    public_methods = [
        name
        for name in dir(service)
        if not name.startswith("_") and callable(getattr(service, name))
    ]
    assert public_methods == ["get_workflow_aggregate"]
