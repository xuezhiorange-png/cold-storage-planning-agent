"""Report API routes — minimal JSON API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

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


# ===================================================================
# Render & Export endpoints (Task 9B)
# ===================================================================


def _get_render_service() -> Any:
    raise RuntimeError("ReportRenderService not wired")


@router.post("/{report_id}/revisions/{revision_number}/render")
def render_report_endpoint(
    report_id: str,
    revision_number: int,
    body: dict[str, Any],
    render_service: Any = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    """Render a report revision to DOCX or PDF."""
    from cold_storage.modules.reports.domain.errors import (
        ExportPermissionError,
        RenderError,
    )

    try:
        artifact = render_service.render(
            report_id=report_id,
            revision_number=revision_number,
            format=body.get("format", "docx"),
            template_version=body.get("template_version"),
            mode=body.get("mode", "draft"),
            actor=actor,
            idempotency_key=body.get("idempotency_key"),
        )
        return {
            "artifact_id": artifact.id,
            "status": artifact.status.value,
            "format": artifact.format.value,
            "file_name": artifact.file_name,
            "file_size_bytes": artifact.file_size_bytes,
            "file_sha256": artifact.file_sha256,
        }
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExportPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{report_id}/exports")
def list_exports(
    report_id: str,
    render_service: Any = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    """List all export artifacts for a report."""
    try:
        artifacts = render_service.list_artifacts(report_id, actor)
        return {
            "exports": [
                {
                    "artifact_id": a.id,
                    "status": a.status.value,
                    "format": a.format.value,
                    "file_name": a.file_name,
                    "file_size_bytes": a.file_size_bytes,
                    "revision_number": a.revision_number,
                    "generated_at": a.generated_at.isoformat()
                    if hasattr(a.generated_at, "isoformat")
                    else str(a.generated_at),
                }
                for a in artifacts
            ],
        }
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{report_id}/exports/{artifact_id}")
def get_export(
    report_id: str,
    artifact_id: str,
    render_service: Any = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    """Get a specific export artifact."""
    from cold_storage.modules.reports.domain.errors import ArtifactNotFoundError

    try:
        artifact = render_service.get_artifact(report_id, artifact_id, actor)
        return {
            "artifact_id": artifact.id,
            "status": artifact.status.value,
            "format": artifact.format.value,
            "file_name": artifact.file_name,
            "file_size_bytes": artifact.file_size_bytes,
            "file_sha256": artifact.file_sha256,
            "revision_number": artifact.revision_number,
            "template_version": artifact.template_version,
            "generated_at": artifact.generated_at.isoformat()
            if hasattr(artifact.generated_at, "isoformat")
            else str(artifact.generated_at),
        }
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{report_id}/exports/{artifact_id}/download")
def download_export(
    report_id: str,
    artifact_id: str,
    render_service: Any = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> FileResponse:
    """Download an export artifact file."""
    from cold_storage.modules.reports.domain.errors import ArtifactNotFoundError

    try:
        artifact = render_service.get_artifact(report_id, artifact_id, actor)
        file_path = render_service.get_artifact_path(artifact.storage_key)
        return FileResponse(
            path=file_path,
            media_type=artifact.mime_type,
            filename=artifact.file_name,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ===================================================================
# Template endpoints (Task 9B)
# ===================================================================


def _get_template_repo() -> Any:
    raise RuntimeError("ReportTemplateRepository not wired")


@router.post("/templates")
def create_template(
    body: dict[str, Any],
    template_repo: Any = Depends(_get_template_repo),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    """Create a new report template."""
    from cold_storage.modules.reports.domain.enums import (
        ExportFormat,
        ReportType,
    )
    from cold_storage.modules.reports.domain.models import ReportTemplate

    try:
        template = ReportTemplate.create(
            template_code=body["template_code"],
            report_type=ReportType(body.get("report_type", "cold_storage_concept_design")),
            format=ExportFormat(body.get("format", "docx")),
            version=body.get("version", "1.0.0"),
            schema_version=body.get("schema_version", "cold_storage_concept_design@1.0.0"),
            locale=body.get("locale", "zh-CN"),
            manifest_json=body.get("manifest_json", {}),
            created_by=actor,
        )
        template_repo.save_template(template)
        template_repo.commit()
        return {
            "template_id": template.id,
            "template_code": template.template_code,
            "version": template.version,
            "status": template.status.value,
        }
    except Exception as exc:
        template_repo.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates")
def list_templates(
    template_code: str | None = Query(None),
    format: str | None = Query(None),  # noqa: A002
    template_repo: Any = Depends(_get_template_repo),  # noqa: B008
) -> dict[str, Any]:
    """List report templates."""
    from cold_storage.modules.reports.domain.enums import ExportFormat

    fmt = ExportFormat(format) if format else None
    templates = template_repo.list_templates(template_code=template_code, format=fmt)
    return {
        "templates": [
            {
                "template_id": t.id,
                "template_code": t.template_code,
                "version": t.version,
                "format": t.format.value,
                "status": t.status.value,
            }
            for t in templates
        ],
    }


@router.post("/templates/{template_id}/activate")
def activate_template(
    template_id: str,
    template_repo: Any = Depends(_get_template_repo),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    """Activate a report template."""
    from dataclasses import replace as dc_replace
    from datetime import UTC, datetime

    from cold_storage.modules.reports.domain.enums import TemplateStatus
    from cold_storage.modules.reports.domain.errors import TemplateActivationError

    try:
        template = template_repo.get_template(template_id)
        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found: {template_id}",
            )

        if template.status == TemplateStatus.RETIRED:
            raise TemplateActivationError(template_id, "Cannot activate a retired template")

        # Deactivate other active templates for the same code and format
        existing_active = template_repo.get_active_template(template.template_code, template.format)
        if existing_active and existing_active.id != template_id:
            deactivated = dc_replace(existing_active, status=TemplateStatus.DRAFT)
            template_repo.update_template(deactivated)

        activated = dc_replace(
            template,
            status=TemplateStatus.ACTIVE,
            activated_at=datetime.now(UTC),
        )
        template_repo.update_template(activated)
        template_repo.commit()
        return {
            "template_id": template_id,
            "status": "active",
        }
    except TemplateActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        template_repo.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/templates/{template_id}/retire")
def retire_template(
    template_id: str,
    template_repo: Any = Depends(_get_template_repo),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    """Retire a report template."""
    from dataclasses import replace as dc_replace

    from cold_storage.modules.reports.domain.enums import TemplateStatus

    try:
        template = template_repo.get_template(template_id)
        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found: {template_id}",
            )

        retired = dc_replace(template, status=TemplateStatus.RETIRED)
        template_repo.update_template(retired)
        template_repo.commit()
        return {
            "template_id": template_id,
            "status": "retired",
        }
    except HTTPException:
        raise
    except Exception as exc:
        template_repo.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
