"""Report API routes — minimal JSON API.

Two routers are exported:
- ``reports_router``: the main router that includes both sub-routers below.
- ``reports_api_router``: ``/api/v1/reports`` — CRUD, generation, review, render.
- ``reports_template_router``: ``/api/v1/report-templates`` — template management.

Template endpoints are on a separate prefix to prevent ``/{report_id}``
from catching ``/templates``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from cold_storage.modules.reports.application.render_service import (
    ReportRenderService,
    ReportTemplateRepositoryPort,
)
from cold_storage.modules.reports.application.service import ReportService
from cold_storage.modules.reports.domain.enums import ExportFormat, RenderMode, ReportType
from cold_storage.modules.reports.domain.errors import (
    ArtifactFileNotFoundError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactNotReadyError,
    ConcurrencyConflictError,
    ExportPermissionError,
    IdempotencyClaimError,
    IdempotencyPayloadConflictError,
    InvalidStatusTransitionError,
    PathTraversalError,
    QualityBlockerError,
    RenderError,
    ReportNotFoundError,
    SchemaValidationError,
    TemplateNotFoundError,
)

# ---------------------------------------------------------------------------
# DI stubs — overridden by FastAPI dependency_overrides in app.py
# ---------------------------------------------------------------------------


def _get_service() -> ReportService:
    raise RuntimeError("ReportService not wired")


def _get_render_service() -> ReportRenderService:
    raise RuntimeError("ReportRenderService not wired")


def _get_template_repo() -> ReportTemplateRepositoryPort:
    raise RuntimeError("ReportTemplateRepository not wired")


def _get_actor() -> str:
    return "system"


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CreateReportRequest(BaseModel):
    project_id: str
    project_version_id: str
    report_type: str = "cold_storage_concept_design"
    idempotency_key: str | None = None


class CreateReportResponse(BaseModel):
    report_id: str
    status: str


class ReportListItem(BaseModel):
    id: str
    status: str


class ListReportsResponse(BaseModel):
    reports: list[ReportListItem]


class ReportDetailResponse(BaseModel):
    id: str
    status: str
    revision_number: int


class RevisionListItem(BaseModel):
    revision_number: int
    content_hash: str


class ListRevisionsResponse(BaseModel):
    revisions: list[RevisionListItem]


class RevisionDetailResponse(BaseModel):
    revision_number: int
    content_hash: str


class GenerateRevisionRequest(BaseModel):
    idempotency_key: str | None = None


class RenderRequest(BaseModel):
    format: ExportFormat = ExportFormat.DOCX
    template_version: str | None = None
    mode: RenderMode = RenderMode.DRAFT
    idempotency_key: str | None = None


class ArtifactResponse(BaseModel):
    artifact_id: str
    status: str
    format: str
    file_name: str
    file_size_bytes: int
    file_sha256: str


class ArtifactListItem(BaseModel):
    artifact_id: str
    status: str
    format: str
    file_name: str
    file_size_bytes: int
    revision_number: int
    generated_at: str


class ListExportsResponse(BaseModel):
    exports: list[ArtifactListItem]


class ArtifactDetailResponse(BaseModel):
    artifact_id: str
    status: str
    format: str
    file_name: str
    file_size_bytes: int
    file_sha256: str
    revision_number: int
    template_version: str
    generated_at: str


class ReviewActionRequest(BaseModel):
    comment: str = ""


class ReviewActionResponse(BaseModel):
    status: str


class CreateTemplateRequest(BaseModel):
    template_code: str
    report_type: str = "cold_storage_concept_design"
    format: str = "docx"
    version: str = "1.0.0"
    schema_version: str = "cold_storage_concept_design@1.0.0"
    locale: str = "zh-CN"
    manifest_json: dict[str, Any] | None = None


class TemplateResponse(BaseModel):
    template_id: str
    template_code: str
    version: str
    status: str


class TemplateListItem(BaseModel):
    template_id: str
    template_code: str
    version: str
    format: str
    status: str


class ListTemplatesResponse(BaseModel):
    templates: list[TemplateListItem]


class TemplateStatusResponse(BaseModel):
    template_id: str
    status: str


# ---------------------------------------------------------------------------
# Reports router  (/api/v1/reports)
# ---------------------------------------------------------------------------

reports_api_router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@reports_api_router.post("", response_model=CreateReportResponse)
def create_report(
    body: CreateReportRequest,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> CreateReportResponse:
    try:
        report = service.create_report(
            project_id=body.project_id,
            project_version_id=body.project_version_id,
            report_type=ReportType(body.report_type),
            actor=actor,
            idempotency_key=body.idempotency_key,
        )
        return CreateReportResponse(report_id=report.id, status=report.status.value)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@reports_api_router.get("", response_model=ListReportsResponse)
def list_reports(
    project_id: str | None = Query(None),
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> ListReportsResponse:
    reports = service.list_reports(project_id=project_id, actor=actor)
    return ListReportsResponse(
        reports=[ReportListItem(id=r.id, status=r.status.value) for r in reports],
    )


@reports_api_router.get("/{report_id}", response_model=ReportDetailResponse)
def get_report(
    report_id: str,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> ReportDetailResponse:
    try:
        r = service.get_report(report_id, actor)
        return ReportDetailResponse(
            id=r.id,
            status=r.status.value,
            revision_number=r.current_revision_number,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@reports_api_router.get("/{report_id}/revisions", response_model=ListRevisionsResponse)
def list_revisions(
    report_id: str,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> ListRevisionsResponse:
    try:
        revs = service.list_revisions(report_id, actor)
        return ListRevisionsResponse(
            revisions=[
                RevisionListItem(revision_number=r.revision_number, content_hash=r.content_hash)
                for r in revs
            ],
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@reports_api_router.get(
    "/{report_id}/revisions/{revision_number}",
    response_model=RevisionDetailResponse,
)
def get_revision(
    report_id: str,
    revision_number: int,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> RevisionDetailResponse:
    try:
        rev = service.get_revision(report_id, revision_number, actor)
        return RevisionDetailResponse(
            revision_number=rev.revision_number, content_hash=rev.content_hash
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@reports_api_router.post("/{report_id}/generate")
def generate_revision(
    report_id: str,
    body: GenerateRevisionRequest | None = None,
    service: ReportService = Depends(_get_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> dict[str, Any]:
    try:
        rev = service.generate_revision(
            report_id,
            actor,
            idempotency_key=(body.idempotency_key if body else None),
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
        body: ReviewActionRequest | None = None,
        service: ReportService = Depends(_get_service),  # noqa: B008
        actor: str = Depends(_get_actor),  # noqa: B008
    ) -> ReviewActionResponse:
        try:
            method = getattr(service, action_name)
            r = method(report_id, actor, comment=(body.comment if body else ""))
            return ReviewActionResponse(status=r.status.value)
        except ReportNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidStatusTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ConcurrencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except QualityBlockerError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return endpoint


reports_api_router.post("/{report_id}/submit-review")(_review_endpoint("submit_review"))
reports_api_router.post("/{report_id}/request-changes")(_review_endpoint("request_changes"))
reports_api_router.post("/{report_id}/mark-reviewed")(_review_endpoint("mark_reviewed"))
reports_api_router.post("/{report_id}/approve")(_review_endpoint("approve"))
reports_api_router.post("/{report_id}/archive")(_review_endpoint("archive"))


@reports_api_router.get("/{report_id}/export")
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


@reports_api_router.post(
    "/{report_id}/revisions/{revision_number}/render",
    response_model=ArtifactResponse,
)
def render_report_endpoint(
    report_id: str,
    revision_number: int,
    body: RenderRequest,
    render_service: ReportRenderService = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> ArtifactResponse:
    """Render a report revision to DOCX or PDF."""
    try:
        artifact = render_service.render(
            report_id=report_id,
            revision_number=revision_number,
            format=body.format.value,
            template_version=body.template_version,
            mode=body.mode.value,
            actor=actor,
            idempotency_key=body.idempotency_key,
        )
        return ArtifactResponse(
            artifact_id=artifact.id,
            status=artifact.status.value,
            format=artifact.format.value,
            file_name=artifact.file_name,
            file_size_bytes=artifact.file_size_bytes,
            file_sha256=artifact.file_sha256,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExportPermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IdempotencyPayloadConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IdempotencyClaimError as exc:
        raise HTTPException(status_code=425, detail=str(exc)) from exc
    except RenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@reports_api_router.get("/{report_id}/exports", response_model=ListExportsResponse)
def list_exports(
    report_id: str,
    render_service: ReportRenderService = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> ListExportsResponse:
    """List all export artifacts for a report."""
    try:
        artifacts = render_service.list_artifacts(report_id, actor)
        return ListExportsResponse(
            exports=[
                ArtifactListItem(
                    artifact_id=a.id,
                    status=a.status.value,
                    format=a.format.value,
                    file_name=a.file_name,
                    file_size_bytes=a.file_size_bytes,
                    revision_number=a.revision_number,
                    generated_at=a.generated_at.isoformat()
                    if hasattr(a.generated_at, "isoformat")
                    else str(a.generated_at),
                )
                for a in artifacts
            ],
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@reports_api_router.get(
    "/{report_id}/exports/{artifact_id}",
    response_model=ArtifactDetailResponse,
)
def get_export(
    report_id: str,
    artifact_id: str,
    render_service: ReportRenderService = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> ArtifactDetailResponse:
    """Get a specific export artifact."""
    try:
        artifact = render_service.get_artifact(report_id, artifact_id, actor)
        return ArtifactDetailResponse(
            artifact_id=artifact.id,
            status=artifact.status.value,
            format=artifact.format.value,
            file_name=artifact.file_name,
            file_size_bytes=artifact.file_size_bytes,
            file_sha256=artifact.file_sha256,
            revision_number=artifact.revision_number,
            template_version=artifact.template_version,
            generated_at=artifact.generated_at.isoformat()
            if hasattr(artifact.generated_at, "isoformat")
            else str(artifact.generated_at),
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@reports_api_router.get("/{report_id}/exports/{artifact_id}/download")
def download_export(
    report_id: str,
    artifact_id: str,
    render_service: ReportRenderService = Depends(_get_render_service),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> FileResponse:
    """Download an export artifact file."""
    try:
        # P0-8: Use verify_download for safety checks
        artifact = render_service.verify_download(report_id, artifact_id, actor)
        file_path = render_service.get_artifact_path(artifact.storage_key)
        return FileResponse(
            path=file_path,
            media_type=artifact.mime_type,
            filename=artifact.file_name,
            headers={
                "Content-Length": str(artifact.file_size_bytes),
                "X-Content-SHA256": artifact.file_sha256,
                "X-Artifact-Id": artifact.id,
                "X-Source-Content-Hash": artifact.source_content_hash,
                "X-Template-Version": artifact.template_version,
            },
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PathTraversalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ArtifactFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ArtifactNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ===================================================================
# Template endpoints  (/api/v1/report-templates)
# ===================================================================

reports_template_router = APIRouter(prefix="/api/v1/report-templates", tags=["report-templates"])


@reports_template_router.post("", response_model=TemplateResponse)
def create_template(
    body: CreateTemplateRequest,
    template_repo: ReportTemplateRepositoryPort = Depends(_get_template_repo),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> TemplateResponse:
    """Create a new report template.

    P0-6: Normalizes manifest through TemplateManifest.from_manifest_json(),
    computes canonical SHA-256 content hash, and validates request fields
    match manifest.
    """
    import hashlib
    import json

    from cold_storage.modules.reports.domain.enums import (
        ExportFormat,
        ReportType,
    )
    from cold_storage.modules.reports.domain.models import ReportTemplate
    from cold_storage.modules.reports.domain.render_model import TemplateManifest

    try:
        # P0-6: Normalize manifest through canonical TemplateManifest model
        raw_manifest = body.manifest_json or {}
        canonical_manifest = TemplateManifest.from_manifest_json(raw_manifest)
        normalized_manifest = canonical_manifest.model_dump()

        # P0-6: Compute canonical SHA-256 hash
        canonical_str = json.dumps(
            normalized_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        template_content_hash = hashlib.sha256(canonical_str.encode()).hexdigest()

        # P0-6: Validate request fields match manifest
        if (
            body.template_code
            and canonical_manifest.template_code
            and body.template_code != canonical_manifest.template_code
        ):
            raise ValueError(
                f"template_code mismatch: request='{body.template_code}' "
                f"vs manifest='{canonical_manifest.template_code}'"
            )
        if (
            body.version
            and canonical_manifest.version
            and body.version != canonical_manifest.version
        ):
            raise ValueError(
                f"version mismatch: request='{body.version}' "
                f"vs manifest='{canonical_manifest.version}'"
            )
        if body.format and canonical_manifest.format and body.format != canonical_manifest.format:
            raise ValueError(
                f"format mismatch: request='{body.format}' "
                f"vs manifest='{canonical_manifest.format}'"
            )

        template = ReportTemplate.create(
            template_code=body.template_code,
            report_type=ReportType(body.report_type),
            format=ExportFormat(body.format),
            version=body.version,
            schema_version=body.schema_version,
            locale=body.locale,
            manifest_json=normalized_manifest,
            template_content_hash=template_content_hash,
            created_by=actor,
        )
        template_repo.save_template(template)
        template_repo.commit()
        return TemplateResponse(
            template_id=template.id,
            template_code=template.template_code,
            version=template.version,
            status=template.status.value,
        )
    except (ValueError, KeyError) as exc:
        template_repo.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@reports_template_router.get("", response_model=ListTemplatesResponse)
def list_templates(
    template_code: str | None = Query(None),
    format: str | None = Query(None),  # noqa: A002
    template_repo: ReportTemplateRepositoryPort = Depends(_get_template_repo),  # noqa: B008
) -> ListTemplatesResponse:
    """List report templates."""
    fmt = ExportFormat(format) if format else None
    templates = template_repo.list_templates(template_code=template_code, format=fmt)
    return ListTemplatesResponse(
        templates=[
            TemplateListItem(
                template_id=t.id,
                template_code=t.template_code,
                version=t.version,
                format=t.format.value,
                status=t.status.value,
            )
            for t in templates
        ],
    )


@reports_template_router.post("/{template_id}/activate", response_model=TemplateStatusResponse)
def activate_template(
    template_id: str,
    template_repo: ReportTemplateRepositoryPort = Depends(_get_template_repo),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> TemplateStatusResponse:
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

        # P0-6: Active templates must not have manifest or hash modified
        if template.status == TemplateStatus.ACTIVE:
            # Load current DB version for comparison
            current = template_repo.get_template(template_id)
            if current is not None and current.manifest_json != template.manifest_json:
                raise TemplateActivationError(
                    template_id, "Cannot modify manifest on an active template"
                )

        # P0-8: Deactivate all existing active templates for same code and format in one operation
        fmt_value = (
            template.format.value if hasattr(template.format, "value") else str(template.format)
        )
        if hasattr(template_repo, "deactivate_templates"):
            template_repo.deactivate_templates(template.template_code, fmt_value)
        else:
            # Fallback for protocol-only repos
            existing_active = template_repo.get_active_template(
                template.template_code, template.format
            )
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
        return TemplateStatusResponse(template_id=template_id, status="active")
    except TemplateActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise


@reports_template_router.post("/{template_id}/retire", response_model=TemplateStatusResponse)
def retire_template(
    template_id: str,
    template_repo: ReportTemplateRepositoryPort = Depends(_get_template_repo),  # noqa: B008
    actor: str = Depends(_get_actor),  # noqa: B008
) -> TemplateStatusResponse:
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
        return TemplateStatusResponse(template_id=template_id, status="retired")
    except HTTPException:
        raise


# ---------------------------------------------------------------------------

reports_router = APIRouter()
reports_router.include_router(reports_api_router)
reports_router.include_router(reports_template_router)

# Backward compatibility alias
router = reports_api_router
