"""Read-only workflow aggregation over persisted authorities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.domain.models import ProjectVersion
from cold_storage.modules.reports.domain.enums import ReportStatus
from cold_storage.modules.reports.domain.models import Report, ReportRevision
from cold_storage.modules.schemes.application.query import SchemeQueryPort
from cold_storage.modules.workflow.application.formal_export_projection import (
    project_formal_export_eligibility,
)
from cold_storage.modules.workflow.application.knowledge_provenance import (
    assess_knowledge_provenance,
    canonical_json_hash,
    content_depends_on_knowledge_source,
    extract_knowledge_revision_ids,
)
from cold_storage.modules.workflow.domain.errors import (
    ProjectNotFoundForWorkflowError,
    ProjectVersionNotFoundForWorkflowError,
)
from cold_storage.modules.workflow.domain.steps import (
    MAINLINE_STEPS,
    REQUIRED_SCHEME_CALCULATOR_NAMES,
    WORKFLOW_CONTRACT_VERSION,
    WORKFLOW_GOAL_FORMAL_REPORT,
    WORKFLOW_GOAL_PLANNING_PREVIEW,
    WORKFLOW_STEPS,
)


class WorkflowAggregateService:
    """Projects workflow state from existing module authorities without recalculating."""

    def __init__(
        self,
        *,
        project_service: ProjectService,
        scheme_query: SchemeQueryPort | None = None,
        report_repository: Any | None = None,
        knowledge_revision_reader: Callable[[str], dict[str, Any] | None] | None = None,
        knowledge_page_evidence_reader: Callable[[str], list[dict[str, Any]]] | None = None,
        agent_capability_projection: list[dict[str, Any]] | None = None,
        trusted_operator: Callable[[str], bool] | None = None,
    ) -> None:
        self._project_service = project_service
        self._scheme_query = scheme_query
        self._report_repository = report_repository
        self._knowledge_revision_reader = knowledge_revision_reader
        self._knowledge_page_evidence_reader = knowledge_page_evidence_reader
        self._agent_capability_projection = agent_capability_projection or []
        self._trusted_operator = trusted_operator

    def get_workflow_aggregate(
        self,
        project_id: str,
        version_number: int,
        *,
        workflow_goal: str = WORKFLOW_GOAL_FORMAL_REPORT,
    ) -> dict[str, Any]:
        project = self._safe_get_project(project_id)
        if project is None:
            raise ProjectNotFoundForWorkflowError(project_id)

        version = self._safe_get_version(project_id, version_number)
        if version is None:
            raise ProjectVersionNotFoundForWorkflowError(project_id, version_number)

        inputs = dict(version.input_snapshot or {})
        validation = self._project_service.validate_inputs(inputs)
        calculations = self._project_service.list_calculations(project_id, version_number)
        calc_by_name = _latest_calculations_by_name(calculations)

        scheme_runs: list[dict[str, Any]] = []
        scheme_authority: Any | None = None
        if self._scheme_query is not None:
            scheme_runs = self._scheme_query.get_completed_runs_for_project_version(
                project_id, version.id
            )
            scheme_authority = self._scheme_query.get_review_authority(project_id, version.id)

        report, report_revision = self._load_primary_report(project_id, version.id)

        knowledge_depends = False
        knowledge_revisions: list[dict[str, Any]] = []
        page_evidence_by_revision: dict[str, list[dict[str, Any]]] = {}
        if report_revision is not None:
            knowledge_depends = content_depends_on_knowledge_source(report_revision.content_json)
            revision_ids = extract_knowledge_revision_ids(report_revision.content_json)
            if revision_ids and self._knowledge_revision_reader is not None:
                for revision_id in revision_ids:
                    record = self._knowledge_revision_reader(revision_id)
                    if record is not None:
                        knowledge_revisions.append(record)
                        if self._knowledge_page_evidence_reader is not None:
                            page_evidence_by_revision[revision_id] = (
                                self._knowledge_page_evidence_reader(revision_id)
                            )

        knowledge_projection = assess_knowledge_provenance(
            depends_on_knowledge=knowledge_depends,
            knowledge_revisions=knowledge_revisions,
            page_evidence_by_revision=page_evidence_by_revision,
        )

        agent_projection = self._project_agent_assistance()
        formal_eligibility = project_formal_export_eligibility(
            report=report,
            revision=report_revision,
            scheme_review_query=self._scheme_query,
            repository=self._report_repository,
            trusted_operator=self._trusted_operator or (lambda _actor: False),
        )

        input_hash = canonical_json_hash(inputs)
        revision_stale_reasons = _collect_stale_reasons(
            version=version,
            inputs=inputs,
            input_hash=input_hash,
            calculations=calc_by_name,
            scheme_runs=scheme_runs,
            report=report,
            report_revision=report_revision,
        )
        revision_stale = bool(revision_stale_reasons)
        revision_freshness = "stale" if revision_stale else "fresh"

        steps = self._build_steps(
            workflow_goal=workflow_goal,
            version=version,
            inputs=inputs,
            validation=validation,
            calc_by_name=calc_by_name,
            scheme_runs=scheme_runs,
            scheme_authority=scheme_authority,
            report=report,
            report_revision=report_revision,
            knowledge_projection=knowledge_projection,
            agent_projection=agent_projection,
            formal_eligibility=formal_eligibility,
            revision_stale=revision_stale,
        )

        blockers = _collect_blockers(steps)
        missing_inputs = _build_missing_inputs(inputs, validation)
        next_actions = _build_next_actions(steps, blockers)
        primary_action_id = next_actions[0]["action_id"] if next_actions else ""
        current_step = _select_current_step(steps)
        workflow_status = _derive_workflow_status(steps, revision_stale)
        workflow_readiness = _build_workflow_readiness(
            blockers=blockers,
            revision_stale=revision_stale,
            next_actions=next_actions,
        )

        return {
            "contract_version": WORKFLOW_CONTRACT_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "project_context": {
                "project_id": project.id,
                "project_code": project.code,
                "project_name": project.name,
                "project_version_id": version.id,
                "project_version_number": version.version_number,
                "project_version_status": version.status,
                "revision_id": version.id,
                "revision_number": version.version_number,
                "revision_fingerprint": input_hash,
                "revision_stale": revision_stale,
                "revision_stale_reasons": revision_stale_reasons,
                "revision_freshness": revision_freshness,
            },
            "current_step": current_step,
            "workflow_status": workflow_status,
            "workflow_goal": workflow_goal,
            "steps": steps,
            "missing_inputs": missing_inputs,
            "blockers": blockers,
            "primary_action_id": primary_action_id,
            "next_required_actions": next_actions,
            "calculations": _project_calculations(calc_by_name),
            "schemes": _project_schemes(scheme_runs, scheme_authority),
            "review": _project_review(scheme_authority, report),
            "approval": _project_approval(version, report),
            "revision": {
                "revision_id": version.id,
                "revision_number": version.version_number,
                "revision_fingerprint": input_hash,
                "revision_stale": revision_stale,
                "revision_freshness": revision_freshness,
                "revision_stale_reasons": revision_stale_reasons,
            },
            "knowledge_provenance": knowledge_projection,
            "agent_assistance": agent_projection,
            "workflow_readiness": workflow_readiness,
            "formal_export_eligibility": formal_eligibility,
            "authorities": [
                "projects_module",
                "calculations_module",
                "schemes_module",
                "reports_module_p1_lifecycle",
                "knowledge_module_read_only",
                "planning_agent_capability_projection",
            ],
        }

    def _safe_get_project(self, project_id: str) -> Any | None:
        try:
            return self._project_service.get_project(project_id)
        except KeyError:
            return None

    def _safe_get_version(self, project_id: str, version_number: int) -> ProjectVersion | None:
        try:
            return self._project_service.get_version(project_id, version_number)
        except KeyError:
            return None

    def _load_primary_report(
        self, project_id: str, project_version_id: str
    ) -> tuple[Report | None, ReportRevision | None]:
        if self._report_repository is None:
            return None, None
        try:
            reports = [
                report
                for report in self._report_repository.list_reports(project_id=project_id)
                if report.project_version_id == project_version_id
            ]
        except Exception:
            return None, None
        if not reports:
            return None, None
        report = reports[0]
        try:
            revision = self._report_repository.get_latest_revision(report.id)
        except Exception:
            revision = None
        return report, revision

    def _project_agent_assistance(self) -> dict[str, Any]:
        agent_entry = next(
            (
                entry
                for entry in self._agent_capability_projection
                if entry.get("name") == "model_backed_agent"
            ),
            None,
        )
        if agent_entry is None:
            return {
                "available": False,
                "status": "UNAVAILABLE",
                "blocking_core_workflow": False,
                "capability_state": "AGENT_CAPABILITY_DISABLED",
                "unavailability_reason": "No agent capability projection bound",
            }

        capability_state = str(agent_entry.get("capability_state", "AGENT_CAPABILITY_DISABLED"))
        route_exposure = str(agent_entry.get("route_exposure", "DISABLED_ROUTE_MATRIX"))
        status_value = str(agent_entry.get("status", "unavailable"))
        available = status_value == "available"
        if capability_state == "AGENT_CAPABILITY_ENABLED_NOT_READY" or status_value == "not_ready":
            assistance_status = "NOT_READY"
        elif available:
            assistance_status = "AVAILABLE"
        else:
            assistance_status = "UNAVAILABLE"

        result: dict[str, Any] = {
            "available": available,
            "status": assistance_status,
            "blocking_core_workflow": False,
            "capability_state": capability_state,
            "route_exposure": route_exposure,
            "unavailability_reason": str(agent_entry.get("code") or ""),
        }
        if "active_provider" in agent_entry:
            result["active_provider"] = agent_entry["active_provider"]
        if "active_model" in agent_entry:
            result["active_model"] = agent_entry["active_model"]
        return result

    def _build_steps(
        self,
        *,
        workflow_goal: str,
        version: ProjectVersion,
        inputs: dict[str, Any],
        validation: dict[str, Any],
        calc_by_name: dict[str, dict[str, Any]],
        scheme_runs: list[dict[str, Any]],
        scheme_authority: Any | None,
        report: Report | None,
        report_revision: ReportRevision | None,
        knowledge_projection: dict[str, Any],
        agent_projection: dict[str, Any],
        formal_eligibility: dict[str, Any],
        revision_stale: bool,
    ) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for step in WORKFLOW_STEPS:
            applicability = _step_applicability(step, workflow_goal)
            status, blocking, step_blockers = _evaluate_step(
                step=step,
                applicability=applicability,
                version=version,
                inputs=inputs,
                validation=validation,
                calc_by_name=calc_by_name,
                scheme_runs=scheme_runs,
                scheme_authority=scheme_authority,
                report=report,
                report_revision=report_revision,
                knowledge_projection=knowledge_projection,
                agent_projection=agent_projection,
                formal_eligibility=formal_eligibility,
                revision_stale=revision_stale,
            )
            steps.append(
                {
                    "step": step,
                    "applicability": applicability,
                    "applicability_reason": _applicability_reason(step, workflow_goal),
                    "status": status,
                    "blocking": blocking,
                    "blockers": step_blockers,
                    "next_actions": [],
                }
            )
        return steps


def _latest_calculations_by_name(
    calculations: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in calculations:
        name = str(record.get("calculator_name", ""))
        if name and name not in latest:
            latest[name] = record
    return latest


def _step_applicability(step: str, workflow_goal: str) -> str:
    if step == "AGENT_ASSISTANCE":
        return "OPTIONAL"
    if step == "KNOWLEDGE_PROVENANCE":
        return "CONDITIONAL"
    if workflow_goal == WORKFLOW_GOAL_PLANNING_PREVIEW:
        if step in {"REPORT_ELIGIBILITY", "FORMAL_REPORT"}:
            return "NOT_APPLICABLE"
        if step in {"SCHEME_COMPARISON", "REVIEW_BLOCKER", "HUMAN_REVIEW", "APPROVAL"}:
            return "CONDITIONAL"
    if workflow_goal == WORKFLOW_GOAL_FORMAL_REPORT and step in {
        "SCHEME_COMPARISON",
        "REVIEW_BLOCKER",
        "HUMAN_REVIEW",
        "APPROVAL",
        "REPORT_ELIGIBILITY",
        "FORMAL_REPORT",
    }:
        return "REQUIRED"
    defaults = {
        "PROJECT_INPUT": "REQUIRED",
        "INPUT_COMPLETENESS": "REQUIRED",
        "DETERMINISTIC_CALCULATION": "REQUIRED",
        "SCHEME_COMPARISON": "CONDITIONAL",
        "REVIEW_BLOCKER": "CONDITIONAL",
        "HUMAN_REVIEW": "CONDITIONAL",
        "APPROVAL": "CONDITIONAL",
        "REPORT_ELIGIBILITY": "CONDITIONAL",
        "FORMAL_REPORT": "CONDITIONAL",
    }
    return defaults.get(step, "NOT_APPLICABLE")


def _applicability_reason(step: str, workflow_goal: str) -> str:
    applicability = _step_applicability(step, workflow_goal)
    if applicability == "OPTIONAL":
        return "Agent assistance is optional for the core planning workflow"
    if applicability == "CONDITIONAL":
        if step == "KNOWLEDGE_PROVENANCE":
            return "Required only when governed output depends on a knowledge source"
        if workflow_goal == WORKFLOW_GOAL_FORMAL_REPORT:
            return "Required for formal-report workflow goal"
        return "Required only for selected workflow goal or downstream artifact"
    if applicability == "NOT_APPLICABLE":
        return "Not required for the selected workflow goal"
    return "Required for the selected workflow goal"


def _evaluate_step(
    *,
    step: str,
    applicability: str,
    version: ProjectVersion,
    inputs: dict[str, Any],
    validation: dict[str, Any],
    calc_by_name: dict[str, dict[str, Any]],
    scheme_runs: list[dict[str, Any]],
    scheme_authority: Any | None,
    report: Report | None,
    report_revision: ReportRevision | None,
    knowledge_projection: dict[str, Any],
    agent_projection: dict[str, Any],
    formal_eligibility: dict[str, Any],
    revision_stale: bool,
) -> tuple[str, bool, list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    if applicability == "NOT_APPLICABLE":
        return "NOT_APPLICABLE", False, blockers

    if step == "PROJECT_INPUT":
        if not inputs:
            blockers.append(_blocker("INPUT_MISSING", "Project inputs have not been saved"))
            return "NOT_STARTED", applicability == "REQUIRED", blockers
        return "COMPLETED", False, blockers

    if step == "INPUT_COMPLETENESS":
        missing = list(validation.get("missing_fields", []))
        tentative = list(validation.get("tentative_fields", []))
        if missing:
            blockers.append(
                _blocker(
                    "INPUT_MISSING",
                    f"Missing required inputs: {', '.join(missing)}",
                )
            )
            return "BLOCKED", True, blockers
        if tentative:
            blockers.append(
                _blocker(
                    "INPUT_REQUIRES_REVIEW",
                    f"Tentative inputs require confirmation: {', '.join(tentative)}",
                )
            )
            return "REVIEW_REQUIRED", applicability == "REQUIRED", blockers
        if not validation.get("valid", False):
            blockers.append(_blocker("INPUT_INVALID", "Input validation failed"))
            return "BLOCKED", True, blockers
        return "COMPLETED", False, blockers

    if step == "DETERMINISTIC_CALCULATION":
        missing_calcs = sorted(REQUIRED_SCHEME_CALCULATOR_NAMES - set(calc_by_name))
        if missing_calcs:
            blockers.append(
                _blocker(
                    "CALCULATION_MISSING",
                    f"Missing persisted calculations: {', '.join(missing_calcs)}",
                )
            )
            return "NOT_STARTED", applicability == "REQUIRED", blockers
        review_required = [
            name for name, record in calc_by_name.items() if record.get("requires_review")
        ]
        if review_required:
            blockers.append(
                _blocker(
                    "CALCULATION_REQUIRES_REVIEW",
                    f"Calculations require review: {', '.join(sorted(review_required))}",
                )
            )
            return "REVIEW_REQUIRED", applicability == "REQUIRED", blockers
        if revision_stale:
            blockers.append(_blocker("CALCULATION_STALE", "Calculation lineage is stale"))
            return "STALE", applicability == "REQUIRED", blockers
        return "COMPLETED", False, blockers

    if step == "SCHEME_COMPARISON":
        if not scheme_runs:
            blockers.append(_blocker("SCHEME_MISSING", "No completed scheme run for this version"))
            return "NOT_STARTED", applicability == "REQUIRED", blockers
        if revision_stale:
            blockers.append(_blocker("SCHEME_STALE", "Scheme source calculations are stale"))
            return "STALE", applicability == "REQUIRED", blockers
        return "COMPLETED", False, blockers

    if step == "REVIEW_BLOCKER":
        if scheme_authority is not None and scheme_authority.requires_review:
            blockers.append(
                _blocker(
                    "SCHEME_REVIEW_REQUIRED",
                    "Scheme review reasons are unresolved",
                    source_type="scheme_run",
                    source_id=scheme_authority.scheme_run_id,
                )
            )
            return "REVIEW_REQUIRED", applicability == "REQUIRED", blockers
        return "COMPLETED", False, blockers

    if step == "HUMAN_REVIEW":
        if version.status in {"draft", "generated"}:
            return "NOT_STARTED", False, blockers
        if version.status == "under_review":
            blockers.append(_blocker("HUMAN_REVIEW_PENDING", "Project version is under review"))
            return "UNDER_REVIEW", applicability == "REQUIRED", blockers
        if version.status == "reviewed":
            return "COMPLETED", False, blockers
        if version.status == "approved":
            return "APPROVED", False, blockers
        return "IN_PROGRESS", False, blockers

    if step == "APPROVAL":
        if version.status == "approved":
            return "APPROVED", False, blockers
        if version.status == "reviewed":
            blockers.append(_blocker("APPROVAL_PENDING", "Project version approval is pending"))
            return "BLOCKED", applicability == "REQUIRED", blockers
        return "NOT_STARTED", False, blockers

    if step == "AGENT_ASSISTANCE":
        if agent_projection.get("available"):
            return "COMPLETED", False, blockers
        return "UNAVAILABLE", False, blockers

    if step == "KNOWLEDGE_PROVENANCE":
        if not knowledge_projection.get("required"):
            return "NOT_APPLICABLE", False, blockers
        status = knowledge_projection.get("status", "PENDING")
        blockers.extend(knowledge_projection.get("blockers", []))
        blocking = bool(blockers) and applicability == "CONDITIONAL"
        return status, blocking, blockers

    if step == "REPORT_ELIGIBILITY":
        if report is None:
            blockers.append(_blocker("REPORT_MISSING", "Report has not been created"))
            return "NOT_STARTED", applicability == "REQUIRED", blockers
        if report.status in {ReportStatus.DRAFT, ReportStatus.GENERATED}:
            return "IN_PROGRESS", False, blockers
        if report.status == ReportStatus.UNDER_REVIEW:
            return "UNDER_REVIEW", False, blockers
        if report.status in {ReportStatus.REVIEWED, ReportStatus.APPROVED, ReportStatus.ARCHIVED}:
            return "COMPLETED", False, blockers
        return "IN_PROGRESS", False, blockers

    if step == "FORMAL_REPORT":
        if formal_eligibility.get("eligible"):
            return "READY", False, blockers
        blockers.extend(formal_eligibility.get("blockers", []))
        status = "STALE" if revision_stale else "BLOCKED"
        return status, applicability == "REQUIRED", blockers

    return "UNAVAILABLE", False, blockers


def _collect_stale_reasons(
    *,
    version: ProjectVersion,
    inputs: dict[str, Any],
    input_hash: str,
    calculations: dict[str, dict[str, Any]],
    scheme_runs: list[dict[str, Any]],
    report: Report | None,
    report_revision: ReportRevision | None,
) -> list[str]:
    reasons: list[str] = []
    for name, record in calculations.items():
        snapshot = record.get("input_snapshot")
        if isinstance(snapshot, dict) and snapshot:
            calc_input_hash = canonical_json_hash(snapshot)
            if calc_input_hash != input_hash:
                reasons.append(f"calculation_input_mismatch:{name}")
    if scheme_runs and calculations:
        current_hash = hashlib.sha256(
            json.dumps(
                {
                    name: calculations[name].get("result_snapshot", {})
                    for name in sorted(calculations)
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        run_hash = str(scheme_runs[0].get("source_snapshot_hash", ""))
        if run_hash and run_hash != current_hash:
            reasons.append("scheme_source_snapshot_mismatch")
    if report is not None and report_revision is not None:
        if report_revision.revision_number != report.current_revision_number:
            reasons.append("report_revision_not_current")
        if report.approved_revision_id and report_revision.id != report.approved_revision_id:
            reasons.append("report_approval_revision_mismatch")
    return reasons


def _collect_blockers(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for step in steps:
        if step.get("blocking"):
            blockers.extend(step.get("blockers", []))
    return blockers


def _build_missing_inputs(
    inputs: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    missing_fields = list(validation.get("missing_fields", []))
    tentative_fields = list(validation.get("tentative_fields", []))
    items: list[dict[str, Any]] = []
    for field in missing_fields:
        items.append(
            {
                "field": field,
                "label": field,
                "unit": "",
                "required": True,
                "status": "missing",
                "source": "persisted_project_input",
                "reason": "Required engineering parameter is missing",
                "remediation": "Provide the field through persisted project inputs",
            }
        )
    for field in tentative_fields:
        items.append(
            {
                "field": field,
                "label": field,
                "unit": "",
                "required": True,
                "status": "tentative",
                "source": "persisted_project_input",
                "reason": "Input is tentative and requires review",
                "remediation": "Confirm or replace tentative input values",
            }
        )
    if not items and not inputs:
        items.append(
            {
                "field": "inputs",
                "label": "inputs",
                "unit": "",
                "required": True,
                "status": "missing",
                "source": "persisted_project_input",
                "reason": "No persisted inputs saved for this version",
                "remediation": "Save project inputs before continuing",
            }
        )
    return items


def _build_next_actions(
    steps: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    priority = [
        "PROJECT_INPUT",
        "INPUT_COMPLETENESS",
        "DETERMINISTIC_CALCULATION",
        "SCHEME_COMPARISON",
        "REVIEW_BLOCKER",
        "HUMAN_REVIEW",
        "APPROVAL",
        "KNOWLEDGE_PROVENANCE",
        "REPORT_ELIGIBILITY",
        "FORMAL_REPORT",
    ]
    actions: list[dict[str, Any]] = []
    for step_name in priority:
        step = next(item for item in steps if item["step"] == step_name)
        if step.get("status") in {"COMPLETED", "APPROVED", "NOT_APPLICABLE"}:
            continue
        if step_name == "AGENT_ASSISTANCE":
            continue
        action_id = f"action-{step_name.lower()}"
        blocked_by = [blocker.get("code", "") for blocker in blockers]
        actions.append(
            {
                "action_id": action_id,
                "type": step_name,
                "target_step": step_name,
                "label": f"Complete {step_name.replace('_', ' ').lower()}",
                "reason": step.get("blockers", [{}])[0].get("message", "")
                if step.get("blockers")
                else "Continue guided workflow",
                "required": step.get("applicability") == "REQUIRED",
                "enabled": not step.get("blocking"),
                "blocked_by": blocked_by,
                "preconditions": [],
                "requires_confirmation": False,
                "target_route": "",
                "target_resource": "",
            }
        )
        if len(actions) >= 3:
            break
    return actions


def _select_current_step(steps: list[dict[str, Any]]) -> str:
    for step_name in MAINLINE_STEPS:
        step = next(item for item in steps if item["step"] == step_name)
        if step.get("blocking") or step.get("status") not in {
            "COMPLETED",
            "APPROVED",
            "NOT_APPLICABLE",
        }:
            return step_name
    return "FORMAL_REPORT"


def _derive_workflow_status(steps: list[dict[str, Any]], revision_stale: bool) -> str:
    if revision_stale:
        return "STALE"
    for step in steps:
        if step.get("blocking"):
            return "BLOCKED"
    for step in steps:
        if step.get("status") == "REVIEW_REQUIRED":
            return "REVIEW_REQUIRED"
    return "IN_PROGRESS"


def _build_workflow_readiness(
    *,
    blockers: list[dict[str, Any]],
    revision_stale: bool,
    next_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    if revision_stale:
        status = "STALE"
    elif blockers:
        status = "BLOCKED"
    elif next_actions:
        status = "NOT_READY"
    else:
        status = "READY"
    return {
        "status": status,
        "blockers": blockers,
        "reasons": [blocker.get("message", "") for blocker in blockers],
        "next_required_actions": next_actions,
    }


def _project_calculations(calc_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    runs = []
    for name, record in sorted(calc_by_name.items()):
        runs.append(
            {
                "calculation_run_id": record.get("id", ""),
                "calculator_name": name,
                "calculator_version": record.get("calculator_version", ""),
                "requires_review": record.get("requires_review", False),
                "engineering_numeric_authority": True,
                "result_hash": _result_hash(record.get("result_snapshot")),
            }
        )
    return {"runs": runs}


def _project_schemes(
    scheme_runs: list[dict[str, Any]],
    scheme_authority: Any | None,
) -> dict[str, Any]:
    if not scheme_runs:
        return {"scheme_run_id": "", "requires_review": False, "review_reasons": []}
    latest = scheme_runs[0]
    review_reasons = []
    if scheme_authority is not None:
        review_reasons = [
            {
                "code": reason.code,
                "message": reason.message,
                "stage": reason.stage,
                "source_type": reason.source_type,
                "source_id": reason.source_id,
            }
            for reason in scheme_authority.review_reasons
        ]
    return {
        "scheme_run_id": latest.get("run_id", ""),
        "source_snapshot_hash": latest.get("source_snapshot_hash", ""),
        "recommended_scheme_code": latest.get("recommended_scheme_code", ""),
        "requires_review": bool(scheme_authority and scheme_authority.requires_review),
        "review_reasons": review_reasons,
    }


def _project_review(scheme_authority: Any | None, report: Report | None) -> dict[str, Any]:
    scheme_review_status = "NOT_REQUIRED"
    if scheme_authority is not None and scheme_authority.requires_review:
        scheme_review_status = "REQUIRED"
    report_review_status = report.status.value if report is not None else "NOT_STARTED"
    return {
        "scheme_review_status": scheme_review_status,
        "report_review_status": report_review_status,
        "aggregate_review_status": (
            "REQUIRED" if scheme_review_status == "REQUIRED" else report_review_status
        ),
    }


def _project_approval(version: ProjectVersion, report: Report | None) -> dict[str, Any]:
    project_status = "APPROVED" if version.status == "approved" else "PENDING"
    report_status = report.status.value if report is not None else "NOT_REQUESTED"
    effective = (
        "APPROVED"
        if project_status == "APPROVED" and report_status == "approved"
        else project_status
    )
    return {
        "project_version_approval_status": project_status,
        "report_approval_status": report_status,
        "effective_approval_status": effective,
        "approved_revision_id": report.approved_revision_id if report else "",
        "approved_content_hash": report.approved_content_hash if report else "",
        "approved_by": report.approved_by if report else "",
        "approved_at": report.approved_at if report else "",
    }


def _result_hash(result_snapshot: Any) -> str:
    if not isinstance(result_snapshot, dict):
        return ""
    return hashlib.sha256(
        json.dumps(result_snapshot, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _blocker(
    code: str,
    message: str,
    *,
    source_type: str = "",
    source_id: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "stage": code,
        "source_type": source_type,
        "source_id": source_id,
        "severity": "blocking",
    }
