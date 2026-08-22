"""Formal export eligibility projection — mirrors P1 report authority without mutating."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cold_storage.modules.reports.application.service import (
    _default_trusted_operator,
    _require_persisted_mark_reviewed,
    _validate_scheme_review_lineage,
)
from cold_storage.modules.reports.domain.enums import FORMAL_EXPORT_STATUSES
from cold_storage.modules.reports.domain.models import Report, ReportRevision


def project_formal_export_eligibility(
    *,
    report: Report | None,
    revision: ReportRevision | None,
    scheme_review_query: Any | None,
    repository: Any,
    trusted_operator: Callable[[str], bool] = _default_trusted_operator,
) -> dict[str, Any]:
    """Project whether formal export would pass the existing reports module gate.

    This is a read-only projection. Render/download must revalidate independently.
    """
    blockers: list[dict[str, Any]] = []
    if report is None:
        return _eligibility_payload(
            status="UNKNOWN",
            eligible=False,
            blockers=[
                _blocker(
                    code="REPORT_MISSING",
                    message="No report exists for this project version",
                    stage="FORMAL_REPORT",
                )
            ],
        )

    if revision is None:
        return _eligibility_payload(
            status="INELIGIBLE",
            eligible=False,
            blockers=[
                _blocker(
                    code="REPORT_MISSING",
                    message="Report has no revision content to evaluate",
                    stage="FORMAL_REPORT",
                    source_type="report",
                    source_id=report.id,
                )
            ],
        )

    if report.status not in FORMAL_EXPORT_STATUSES:
        blockers.append(
            _blocker(
                code="FORMAL_REPORT_NOT_APPROVED",
                message=f"Report status '{report.status.value}' is not formal-exportable",
                stage="FORMAL_REPORT",
                source_type="report",
                source_id=report.id,
            )
        )

    missing_approval: list[str] = []
    if not report.approved_revision_id:
        missing_approval.append("approved_revision_id")
    if not report.approved_content_hash:
        missing_approval.append("approved_content_hash")
    if not report.approved_by:
        missing_approval.append("approved_by")
    if not report.approved_at:
        missing_approval.append("approved_at")
    if missing_approval:
        blockers.append(
            _blocker(
                code="APPROVAL_PENDING",
                message=f"Missing approval fields: {', '.join(missing_approval)}",
                stage="APPROVAL",
                source_type="report",
                source_id=report.id,
            )
        )

    if report.approved_revision_id and revision.id != report.approved_revision_id:
        blockers.append(
            _blocker(
                code="APPROVAL_STALE",
                message="Revision is not the approved revision",
                stage="FORMAL_REPORT",
                source_type="report_revision",
                source_id=revision.id,
            )
        )

    if report.approved_content_hash and revision.content_hash != report.approved_content_hash:
        blockers.append(
            _blocker(
                code="REPORT_REVISION_STALE",
                message="Revision content hash does not match approved content hash",
                stage="FORMAL_REPORT",
                source_type="report_revision",
                source_id=revision.id,
            )
        )

    if revision.revision_number != report.current_revision_number:
        blockers.append(
            _blocker(
                code="REPORT_REVISION_STALE",
                message=(
                    f"Formal export requires latest revision "
                    f"({report.current_revision_number}), got {revision.revision_number}"
                ),
                stage="FORMAL_REPORT",
                source_type="report_revision",
                source_id=revision.id,
            )
        )

    if revision.quality_findings_json:
        blocking_findings = [
            finding
            for finding in revision.quality_findings_json
            if isinstance(finding, dict) and finding.get("severity") == "blocking"
        ]
        if blocking_findings:
            blockers.append(
                _blocker(
                    code="REPORT_QUALITY_BLOCKER",
                    message=f"Revision has {len(blocking_findings)} blocking quality findings",
                    stage="FORMAL_REPORT",
                    source_type="report_revision",
                    source_id=revision.id,
                )
            )

    try:
        authority = _validate_scheme_review_lineage(
            report=report,
            revision=revision,
            scheme_review_query=scheme_review_query,
            required=True,
        )
        if authority is not None and authority.requires_review:
            _require_persisted_mark_reviewed(
                repository=repository,
                report=report,
                revision=revision,
                trusted_operator=trusted_operator,
            )
    except Exception as exc:  # noqa: BLE001 — projection collects blockers, does not raise
        blockers.append(
            _blocker(
                code="REVIEW_REASONS_UNRESOLVED",
                message=str(exc),
                stage="REVIEW_BLOCKER",
                source_type="scheme_run",
                source_id=report.id,
            )
        )

    eligible = not blockers
    status = "ELIGIBLE" if eligible else "INELIGIBLE"
    return _eligibility_payload(status=status, eligible=eligible, blockers=blockers)


def _eligibility_payload(
    *,
    status: str,
    eligible: bool,
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": status,
        "eligible": eligible,
        "blockers": blockers,
        "authority_owner": "reports_module_p1_lifecycle",
        "revalidation_required": True,
    }


def _blocker(
    *,
    code: str,
    message: str,
    stage: str,
    source_type: str = "",
    source_id: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "stage": stage,
        "source_type": source_type,
        "source_id": source_id,
        "severity": "blocking",
    }
