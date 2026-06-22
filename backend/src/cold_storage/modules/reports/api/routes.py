"""Report API routes — minimal JSON API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from cold_storage.modules.reports.application.service import ReportService
from cold_storage.modules.reports.domain.enums import ReportType
from cold_storage.modules.reports.domain.errors import (
    ConcurrencyConflictError,
    InvalidStatusTransitionError,
    QualityBlockerError,
    ReportNotFoundError,
    SchemaValidationError,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _get_service() -> ReportService:
    raise RuntimeError("ReportService not wired")


def _get_actor() -> str:
    return "system"


@router.post("")
def create_report(
    body: dict[str, Any],
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    try:
        report = service.create_report(
            project_id=body["project_id"],
            project_version_id=body["project_version_id"],
            report_type=ReportType(
                body.get("report_type", "cold_storage_concept_design"),
            ),
            actor=actor,
            idempotency_key=body.get("idempotency_key"),
        )
        return {"report_id": report.id, "status": report.status.value}
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_reports(
    project_id: str | None = Query(None),
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    reports = service.list_reports(project_id=project_id, actor=actor)
    return {
        "reports": [{"id": r.id, "status": r.status.value} for r in reports],
    }


@router.get("/{report_id}")
def get_report(
    report_id: str,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    try:
        r = service.get_report(report_id, actor)
        return {
            "id": r.id,
            "status": r.status.value,
            "revision_number": r.current_revision_number,
        }
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{report_id}/revisions")
def list_revisions(
    report_id: str,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    try:
        revs = service.list_revisions(report_id, actor)
        return {
            "revisions": [
                {"revision_number": r.revision_number, "content_hash": r.content_hash} for r in revs
            ],
        }
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{report_id}/revisions/{revision_number}")
def get_revision(
    report_id: str,
    revision_number: int,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    try:
        rev = service.get_revision(report_id, revision_number, actor)
        return {"revision_number": rev.revision_number, "content_hash": rev.content_hash}
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{report_id}/generate")
def generate_revision(
    report_id: str,
    body: dict[str, Any] | None = None,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    try:
        rev = service.generate_revision(
            report_id,
            actor,
            idempotency_key=(body or {}).get("idempotency_key"),
        )
        return {"revision_number": rev.revision_number, "content_hash": rev.content_hash}
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConcurrencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SchemaValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _review_endpoint(action_name: str) -> Any:
    def endpoint(
        report_id: str,
        body: dict[str, Any] | None = None,
        service: ReportService = Depends(_get_service),  # noqa: B008
        actor: str = Depends(_get_actor),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            method = getattr(service, action_name)
            r = method(report_id, actor, comment=(body or {}).get("comment", ""))
            return {"status": r.status.value}
        except ReportNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidStatusTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ConcurrencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except QualityBlockerError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return endpoint


router.post("/{report_id}/submit-review")(_review_endpoint("submit_review"))
router.post("/{report_id}/request-changes")(_review_endpoint("request_changes"))
router.post("/{report_id}/mark-reviewed")(_review_endpoint("mark_reviewed"))
router.post("/{report_id}/approve")(_review_endpoint("approve"))
router.post("/{report_id}/archive")(_review_endpoint("archive"))


@router.get("/{report_id}/export")
def export_json(
    report_id: str,
    revision_number: int = Query(...),
    format: str = Query("json"),  # noqa: A002
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    try:
        return service.export_json(report_id, revision_number, actor)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
