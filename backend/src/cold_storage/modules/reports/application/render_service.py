"""Report render service — orchestrates export rendering to DOCX/PDF.

No ORM access, no LLM calls.  Uses repository port, artifact storage,
and renderers.

P0-4: Real Revision Rendering — ISO 8601 dates, real manifest metadata
P0-5: Formal Export Rules — verify approved revision
P0-6: Real Idempotency — fingerprint-based deduplication
P0-7: Artifact State Machine — pending -> rendering -> completed/failed
P0-8: Download Safety — verify_download() with integrity checks
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from cold_storage.modules.reports.application.service import ReportRepository
from cold_storage.modules.reports.domain.enums import (
    DRAFT_EXPORT_STATUSES,
    FORMAL_EXPORT_STATUSES,
    ArtifactStatus,
    ExportFormat,
    RenderMode,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.errors import (
    ArtifactFileNotFoundError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactNotReadyError,
    ExportPermissionError,
    IdempotencyClaimError,
    IdempotencyPayloadConflictError,
    RenderError,
    ReportNotFoundError,
    TemplateNotFoundError,
)
from cold_storage.modules.reports.domain.models import (
    ApprovalSnapshot,
    Report,
    ReportExportArtifact,
    ReportRevision,
    ReportTemplate,
)
from cold_storage.modules.reports.domain.render_model import JsonObject, ReportRenderModel


class ArtifactStoragePort(Protocol):
    """Port: artifact file storage operations."""

    def put_temp(self, data: bytes, filename: str) -> tuple[str, str]: ...
    def cleanup_temp(self, path: str) -> None: ...
    def finalize_temp(self, path: str, artifact_id: str, filename: str) -> str: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def get_path(self, key: str) -> str: ...
    def put(self, artifact_id: str, data: bytes, filename: str) -> str: ...
    def get(self, key: str) -> bytes: ...


class ReportTemplateRepositoryPort(Protocol):
    """Port: persistence for report templates."""

    def get_template(self, template_id: str) -> ReportTemplate | None: ...

    def get_active_template(
        self, template_code: str, format: ExportFormat
    ) -> ReportTemplate | None: ...

    def list_templates(
        self,
        template_code: str | None = None,
        format: ExportFormat | None = None,
    ) -> list[ReportTemplate]: ...

    def save_template(self, template: ReportTemplate) -> None: ...

    def update_template(self, template: ReportTemplate) -> None: ...

    # P0-7: Deactivate all active templates for the given code and format.
    def deactivate_templates(self, template_code: str, fmt: str) -> int: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ReportArtifactRepositoryPort(Protocol):
    """Port: persistence for export artifacts."""

    def save_artifact(self, artifact: ReportExportArtifact) -> None: ...

    def get_artifact(self, artifact_id: str) -> ReportExportArtifact | None: ...

    def list_artifacts(
        self, report_id: str, status: ArtifactStatus | None = None
    ) -> list[ReportExportArtifact]: ...

    def find_artifact_by_idempotency(
        self, idempotency_key: str, report_id: str
    ) -> ReportExportArtifact | None: ...

    def update_artifact(self, artifact: ReportExportArtifact) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


def _compute_fingerprint(
    *,
    actor: str,
    report_id: str,
    revision_number: int,
    source_content_hash: str,
    format: str,
    render_mode: str,
    template_id: str,
    template_version: str,
    template_content_hash: str,
) -> str:
    """Compute a deterministic fingerprint for idempotency checking."""
    payload = {
        "actor": actor,
        "report_id": report_id,
        "revision_number": revision_number,
        "source_content_hash": source_content_hash,
        "format": format,
        "render_mode": render_mode,
        "template_id": template_id,
        "template_version": template_version,
        "template_content_hash": template_content_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# P0-3: Unit of Work — atomic commit via single session
# ---------------------------------------------------------------------------


class ReportRenderUnitOfWork:
    """Atomic unit of work for report rendering.

    Wraps a single SQLAlchemy Session so that both the report repository and
    artifact repository share the same transaction.  ``commit()`` and
    ``rollback()`` operate on the underlying session exactly once.
    """

    def __init__(
        self,
        session: Any,  # sqlalchemy.orm.Session
        *,
        report_repo: ReportRepository | None = None,
        artifact_repo: ReportArtifactRepositoryPort | None = None,
    ) -> None:
        self._session = session
        from cold_storage.modules.reports.infrastructure.repository import (
            SQLReportRepository,
        )

        # Validate that provided repos share the same session
        if report_repo is not None and getattr(report_repo, "_session", None) is not session:
            raise ValueError(
                "report_repo._session does not match the UOW session. "
                "Both repositories must share the same SQLAlchemy session."
            )
        if artifact_repo is not None and getattr(artifact_repo, "_session", None) is not session:
            raise ValueError(
                "artifact_repo._session does not match the UOW session. "
                "Both repositories must share the same SQLAlchemy session."
            )
        self._report_repo: ReportRepository = report_repo or SQLReportRepository(session)
        self._artifact_repo: ReportArtifactRepositoryPort | None = (
            artifact_repo or SQLReportRepository(session)
        )

    @property
    def report_repo(self) -> ReportRepository:
        return self._report_repo

    @property
    def artifact_repo(self) -> ReportArtifactRepositoryPort | None:
        return self._artifact_repo

    @property
    def session(self) -> Any:
        return self._session

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


# ---------------------------------------------------------------------------


class ReportRenderService:
    """Application service for report export rendering.

    Parameters
    ----------
    uow:
        Unit of Work that provides report_repo and artifact_repo from a
        single shared session.
    storage:
        Artifact storage adapter (for saving rendered files).
    template_repo:
        Template repository port (for loading templates).
    """

    def __init__(
        self,
        *,
        uow: ReportRenderUnitOfWork,
        storage: ArtifactStoragePort | None = None,
        template_repo: ReportTemplateRepositoryPort | None = None,
    ) -> None:
        """Initialize the render service.

        Parameters
        ----------
        uow:
            Required: a ``ReportRenderUnitOfWork`` that provides both
            report_repo and artifact_repo from a single session.
        storage:
            Artifact file storage adapter (required).
        template_repo:
            Template repository port.
        """
        if uow is None:
            raise TypeError("ReportRenderService requires uow= parameter")
        self._uow: ReportRenderUnitOfWork = uow
        self._repo: ReportRepository = uow.report_repo
        self._artifact_repo: ReportArtifactRepositoryPort | None = uow.artifact_repo
        self._storage: ArtifactStoragePort = storage  # type: ignore[assignment]
        self._template_repo = template_repo

    def render(
        self,
        *,
        report_id: str,
        revision_number: int,
        format: str,  # noqa: A002
        template_version: str | None,
        mode: str,  # noqa: A002
        actor: str,
        idempotency_key: str | None = None,
    ) -> ReportExportArtifact:
        """Render a report revision to DOCX or PDF.

        Parameters
        ----------
        report_id:
            Report identifier.
        revision_number:
            Revision number to render.
        format:
            Output format: "docx" or "pdf".
        template_version:
            Specific template version, or None for active.
        mode:
            Render mode: "draft" or "formal".
        actor:
            Actor performing the render (must be report owner).
        idempotency_key:
            Optional idempotency key for deduplication.

        Returns
        -------
        ReportExportArtifact
            The completed export artifact.

        Raises
        ------
        ReportNotFoundError
            If the report or revision is not found.
        ExportPermissionError
            If the report status is not valid for the requested mode.
        RenderError
            If rendering fails.
        """
        export_format = ExportFormat(format)
        render_mode = RenderMode(mode)

        # 1. Load the report (owner isolation check)
        report = self._repo.get_report(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        if report.created_by != actor:
            raise ReportNotFoundError(report_id)

        # 2. Load the specific revision
        revision = self._repo.get_revision(report_id, revision_number)
        if revision is None:
            raise ReportNotFoundError(f"{report_id}/rev/{revision_number}")

        # 3. Validate draft/formal rules (P0-5)
        self._validate_export_mode(report, render_mode, revision)

        # 4. Find the active template (or specific version)
        template = self._find_template(export_format, template_version)

        # P0-1: Build ApprovalSnapshot from Report fields for render model
        approval_snapshot = ApprovalSnapshot.from_report_and_revision(report, revision)

        # 5. Build render model from revision content
        from cold_storage.modules.reports.application.render_model_builder import (
            build_render_model,
        )

        render_model = build_render_model(
            content=revision.content_json,
            report_id=revision.report_id,
            revision_number=revision.revision_number,
            content_hash=revision.content_hash,
            generated_by=revision.generated_by,
            generated_at=revision.generated_at.isoformat()
            if hasattr(revision.generated_at, "isoformat")
            else str(revision.generated_at),
            template_version=template.version,
            template_code=template.template_code,
            template_manifest_json=template.manifest_json,
            format=export_format.value,
            approval_snapshot=approval_snapshot,
        )

        # 6. Idempotency check (P0-6) — atomic claim via idempotency_records
        template_id = template.id
        template_version_str = template.version
        template_content_hash = template.template_content_hash
        fingerprint = ""

        if idempotency_key:
            fingerprint = _compute_fingerprint(
                actor=actor,
                report_id=report_id,
                revision_number=revision_number,
                source_content_hash=revision.content_hash,
                format=format,
                render_mode=mode,
                template_id=template_id,
                template_version=template_version_str,
                template_content_hash=template_content_hash,
            )

            # Attempt atomic claim via idempotency_records table
            try:
                self._repo.save_idempotency_record(
                    key=idempotency_key,
                    actor=actor,
                    action="render",
                    fingerprint=fingerprint,
                )
                self._uow.commit()
            except Exception:
                self._uow.rollback()
                # Record exists — verify same fingerprint
                existing = self._repo.get_idempotency_record(idempotency_key)
                if existing is None:
                    raise
                if existing["fingerprint"] != fingerprint:
                    raise IdempotencyPayloadConflictError(idempotency_key) from None
                # Same fingerprint — return existing completed artifact if available
                if existing["status"] == "completed" and existing.get("result_payload"):
                    payload = existing["result_payload"]
                    if (
                        isinstance(payload, dict)
                        and "artifact_id" in payload
                        and self._artifact_repo is not None
                    ):
                        completed = self._artifact_repo.get_artifact(payload["artifact_id"])
                        if completed and completed.status == ArtifactStatus.COMPLETED:
                            return completed
                # P0-2: Allow retry if previously failed — delete and re-claim
                if existing["status"] == "failed":
                    self._repo.reset_failed_idempotency(idempotency_key)
                    self._uow.commit()
                    self._repo.save_idempotency_record(
                        key=idempotency_key,
                        actor=actor,
                        action="render",
                        fingerprint=fingerprint,
                    )
                    self._uow.commit()
                    # Fall through — render will proceed
                else:
                    # Not yet completed or failed — another render in progress
                    raise IdempotencyClaimError(idempotency_key) from None

        # 7. Create pending artifact
        file_ext = "docx" if export_format == ExportFormat.DOCX else "pdf"
        mime_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if export_format == ExportFormat.DOCX
            else "application/pdf"
        )
        file_name = f"report_{report_id}_rev{revision_number}.{file_ext}"

        artifact = ReportExportArtifact.create(
            report_id=report_id,
            report_revision_id=revision.id,
            revision_number=revision_number,
            format=export_format,
            template_id=template_id,
            template_version=template_version_str,
            schema_version=revision.schema_version,
            file_name=file_name,
            mime_type=mime_type,
            source_content_hash=revision.content_hash,
            generated_by=actor,
        )

        # P0-2: Unified failure handler for ALL artifact persistence stages.
        # Covers: insert pending → commit, update rendering → commit,
        #         render, finalize, update completed + complete idempotency.
        # If ANY stage fails → rollback, re-read, update to failed, fail
        # idempotency, commit, structured log.
        temp_path: str | None = None
        storage_key: str = ""
        current_stage = "init"
        try:
            # P0-2: INSERT artifact(pending) → commit
            current_stage = "insert_pending"
            if self._artifact_repo:
                self._artifact_repo.save_artifact(artifact)
                self._uow.commit()

            # P0-2: UPDATE artifact(rendering) → commit
            current_stage = "update_rendering"
            artifact = replace(artifact, status=ArtifactStatus.RENDERING)
            if self._artifact_repo:
                self._artifact_repo.update_artifact(artifact)
                self._uow.commit()

            # 8. Render via DocxRenderer or PdfRenderer
            current_stage = "render"
            rendered_bytes = self._render_bytes(
                export_format,
                render_model,
                template,
                is_draft=(render_mode == RenderMode.DRAFT),
            )

            # 9. Compute file SHA-256
            file_sha256 = hashlib.sha256(rendered_bytes).hexdigest()

            # 10. Save to temp file first, then finalize (P0-7)
            current_stage = "finalize"
            temp_path, temp_sha256 = self._storage.put_temp(rendered_bytes, file_name)

            # Verify temp file hash matches
            if temp_sha256 != file_sha256:
                self._storage.cleanup_temp(temp_path)
                raise RenderError(f"SHA-256 mismatch: expected {file_sha256}, got {temp_sha256}")

            # Move to final location
            storage_key = self._storage.finalize_temp(temp_path, artifact.id, file_name)
            temp_path = None  # Successfully finalized

            # Build real manifest metadata (P0-4) using same ApprovalSnapshot
            render_manifest = self._build_render_manifest(
                export_format=export_format,
                render_mode=render_mode,
                template_id=template_id,
                template_version=template_version_str,
                template_content_hash=template_content_hash,
                source_content_hash=revision.content_hash,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint if idempotency_key else "",
                render_settings=render_model.manifest.render_settings
                if hasattr(render_model.manifest, "render_settings")
                else {},
                approval_snapshot=approval_snapshot,
            )

            # 11. Update artifact with storage_key, file_size, file_sha256, status=completed
            current_stage = "update_completed"
            artifact = replace(
                artifact,
                status=ArtifactStatus.COMPLETED,
                storage_key=storage_key,
                file_size_bytes=len(rendered_bytes),
                file_sha256=file_sha256,
                render_manifest_json=render_manifest,
            )

            # P0-2: UPDATE artifact(completed) + complete idempotency → single commit
            if self._artifact_repo:
                self._artifact_repo.update_artifact(artifact)
            if idempotency_key:
                self._repo.complete_idempotency_record(
                    key=idempotency_key,
                    result_payload={"artifact_id": artifact.id},
                )
            if self._artifact_repo:
                self._uow.commit()

            return artifact

        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.error(
                "Artifact persistence failure",
                extra={
                    "artifact_id": artifact.id,
                    "idempotency_key": idempotency_key or "",
                    "stage": current_stage,
                    "exception": str(exc),
                },
                exc_info=True,
            )

            # Cleanup temp file if still present
            if temp_path is not None:
                try:
                    self._storage.cleanup_temp(temp_path)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to clean up temp file after artifact failure",
                        extra={
                            "artifact_id": artifact.id,
                            "storage_key": storage_key,
                            "idempotency_key": idempotency_key or "",
                            "stage": current_stage,
                            "exception": str(cleanup_exc),
                        },
                    )

            # Clean up finalized storage if it exists
            if storage_key:
                try:
                    self._storage.delete(storage_key)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to clean up storage after artifact failure",
                        extra={
                            "artifact_id": artifact.id,
                            "storage_key": storage_key,
                            "idempotency_key": idempotency_key or "",
                            "stage": current_stage,
                            "exception": str(cleanup_exc),
                        },
                    )

            # P0-2: Persist failure state — rollback, re-read, update to failed
            if self._artifact_repo:
                try:
                    self._uow.rollback()
                    # Re-read artifact from DB (clean session)
                    failed_artifact = self._artifact_repo.get_artifact(artifact.id)
                    if failed_artifact is not None:
                        from dataclasses import is_dataclass as _is_dc

                        if _is_dc(failed_artifact):
                            failed_artifact = replace(
                                failed_artifact,
                                status=ArtifactStatus.FAILED,
                                failure_code=type(exc).__name__,
                                failure_message=str(exc),
                            )
                        self._artifact_repo.update_artifact(failed_artifact)
                    # Fail idempotency record in same commit
                    if idempotency_key:
                        self._repo.fail_idempotency_record(
                            idempotency_key,
                            type(exc).__name__,
                            str(exc),
                        )
                    self._uow.commit()
                except Exception:
                    import contextlib

                    with contextlib.suppress(Exception):
                        self._uow.rollback()
                    logger.error(
                        "Failed to persist failed artifact state",
                        extra={
                            "artifact_id": artifact.id,
                            "idempotency_key": idempotency_key or "",
                            "stage": current_stage,
                        },
                        exc_info=True,
                    )

            raise RenderError(f"Rendering failed: {exc}") from exc

    def _build_render_manifest(
        self,
        *,
        export_format: ExportFormat,
        render_mode: RenderMode,
        template_id: str,
        template_version: str,
        template_content_hash: str,
        source_content_hash: str,
        idempotency_key: str | None,
        fingerprint: str,
        render_settings: JsonObject,
        approval_snapshot: ApprovalSnapshot | None = None,
    ) -> dict[str, Any]:
        """Build the render manifest with real metadata (P0-4).

        P0-1: Uses the same ApprovalSnapshot object that was passed to the
        render model, ensuring section content and manifest are consistent.
        """
        return {
            "export_format": export_format.value,
            "render_mode": render_mode.value,
            "template_id": template_id,
            "template_version": template_version,
            "template_content_hash": template_content_hash,
            "source_content_hash": source_content_hash,
            "renderer_name": "cold_storage_renderer",
            "renderer_version": "1.0.0",
            "render_settings": render_settings,
            "idempotency_key": idempotency_key or "",
            "fingerprint": fingerprint,
            "approved_revision_id": (approval_snapshot.revision_id if approval_snapshot else ""),
            "approved_content_hash": (approval_snapshot.content_hash if approval_snapshot else ""),
            "approved_by": (approval_snapshot.approved_by if approval_snapshot else ""),
            "approved_at": (approval_snapshot.approved_at if approval_snapshot else ""),
        }

    def _validate_export_mode(
        self,
        report: Report,
        mode: RenderMode,
        revision: ReportRevision,
    ) -> None:
        """Validate that the report status allows the requested export mode.

        P0-4/P0-5: For formal mode, verify the revision being exported is the
        APPROVED revision (quality_status == APPROVED and latest revision).
        """
        allowed = (
            DRAFT_EXPORT_STATUSES
            if mode == RenderMode.DRAFT
            else FORMAL_EXPORT_STATUSES
            if mode == RenderMode.FORMAL
            else frozenset()
        )
        if report.status not in allowed:
            raise ExportPermissionError(report.id, mode.value, report.status.value)

        # P0-4/P0-5: Formal mode requires exporting the latest/approved revision
        if mode == RenderMode.FORMAL:
            # P0-8: Must have all approval fields for formal export
            missing = []
            if not report.approved_revision_id:
                missing.append("approved_revision_id")
            if not report.approved_content_hash:
                missing.append("approved_content_hash")
            if not report.approved_by:
                missing.append("approved_by")
            if not report.approved_at:
                missing.append("approved_at")
            if missing:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    f"Missing approval fields: {', '.join(missing)}",
                )
            # Verify revision matches approval
            if revision.id != report.approved_revision_id:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    "Approved revision mismatch",
                )
            if revision.content_hash != report.approved_content_hash:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    "Approved content hash mismatch",
                )
            if revision.revision_number != report.current_revision_number:
                raise ExportPermissionError(
                    report.id,
                    mode.value,
                    f"Formal export requires latest revision ({report.current_revision_number}), "
                    f"got {revision.revision_number}",
                )
            # P0-8: Block formal export if blocking quality findings exist
            if revision.quality_findings_json:
                blockers = [
                    f
                    for f in revision.quality_findings_json
                    if isinstance(f, dict) and f.get("severity") == "blocking"
                ]
                if blockers:
                    raise ExportPermissionError(
                        report.id,
                        mode.value,
                        f"Revision has {len(blockers)} blocking findings",
                    )

    def _find_template(
        self,
        format: ExportFormat,
        template_version: str | None,  # noqa: A002
    ) -> ReportTemplate:
        """Find the active template or specific version.

        Raises
        ------
        TemplateNotFoundError
            If no matching template is found.
        """
        if self._template_repo is None:
            raise TemplateNotFoundError("No template repository configured")

        if template_version:
            # Find by version — only ACTIVE templates
            templates = self._template_repo.list_templates(format=format)
            for t in templates:
                if t.version == template_version and t.status == TemplateStatus.ACTIVE:
                    return t
            raise TemplateNotFoundError(
                f"Template version {template_version} not found or not active "
                f"for format {format.value}"
            )

        # Find active template
        result = self._template_repo.get_active_template(
            template_code="cold_storage_concept_design",
            format=format,
        )
        if result is None:
            raise TemplateNotFoundError(
                f"No active template found for cold_storage_concept_design / {format.value}"
            )
        return result

    def _render_bytes(
        self,
        format: ExportFormat,  # noqa: A002
        render_model: ReportRenderModel,
        template: ReportTemplate | None,
        *,
        is_draft: bool = False,
    ) -> bytes:
        """Render the model to bytes using the appropriate renderer.

        P0-4: Pass is_draft flag to renderer.
        """
        if format == ExportFormat.DOCX:
            from cold_storage.modules.reports.renderers.docx_renderer import (
                DocxRenderer,
            )

            docx_renderer = DocxRenderer()
            return docx_renderer.render(render_model, is_draft=is_draft)
        elif format == ExportFormat.PDF:
            from cold_storage.modules.reports.renderers.pdf_renderer import (
                PdfRenderer,
            )

            pdf_renderer = PdfRenderer()
            return pdf_renderer.render(render_model, is_draft=is_draft)
        else:
            raise RenderError(f"Unsupported format: {format}")

    # --- Query methods ---

    def get_artifact(self, report_id: str, artifact_id: str, actor: str) -> ReportExportArtifact:
        """Get an export artifact by ID."""
        # Owner isolation check
        report = self._repo.get_report(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        if report.created_by != actor:
            raise ReportNotFoundError(report_id)

        if self._artifact_repo is None:
            raise ArtifactNotFoundError(artifact_id)

        artifact = self._artifact_repo.get_artifact(artifact_id)
        if artifact is None or artifact.report_id != report_id:
            raise ArtifactNotFoundError(artifact_id)

        return artifact

    def list_artifacts(self, report_id: str, actor: str) -> list[ReportExportArtifact]:
        """List all export artifacts for a report."""
        # Owner isolation check
        report = self._repo.get_report(report_id)
        if report is None:
            raise ReportNotFoundError(report_id)
        if report.created_by != actor:
            raise ReportNotFoundError(report_id)

        if self._artifact_repo is None:
            return []

        return self._artifact_repo.list_artifacts(report_id)

    def verify_download(
        self,
        report_id: str,
        artifact_id: str,
        actor: str,
    ) -> ReportExportArtifact:
        """Verify download safety (P0-8).

        Checks:
        1. Artifact belongs to the report
        2. Actor has permission
        3. Status is COMPLETED
        4. storage_key is non-empty
        5. File exists on disk
        6. File size matches database
        7. SHA-256 matches database

        Returns
        -------
        ReportExportArtifact
            The verified artifact.

        Raises
        ------
        ReportNotFoundError
            If the report is not found or actor has no access.
        ArtifactNotFoundError
            If the artifact is not found or doesn't belong to the report.
        ArtifactNotReadyError
            If the artifact is not in completed state.
        ArtifactFileNotFoundError
            If the artifact file does not exist on disk.
        ArtifactIntegrityError
            If file size or SHA-256 does not match database.
        PathTraversalError
            If the storage_key contains path traversal characters.
        """
        # 1 & 2: Get artifact with permission check
        artifact = self.get_artifact(report_id, artifact_id, actor)

        # 3: Status must be COMPLETED
        if artifact.status != ArtifactStatus.COMPLETED:
            raise ArtifactNotReadyError(artifact_id, artifact.status.value)

        # 4: storage_key must be non-empty
        if not artifact.storage_key:
            raise ArtifactFileNotFoundError(artifact_id, "<no storage key>")

        # 5: File exists on disk — let PathTraversalError pass through
        try:
            file_path = self._storage.get_path(artifact.storage_key)
        except FileNotFoundError:
            raise ArtifactFileNotFoundError(artifact_id, artifact.storage_key) from None

        path = Path(file_path)
        if not path.is_file():
            raise ArtifactFileNotFoundError(artifact_id, file_path)

        # 6: File size matches database
        actual_size = path.stat().st_size
        if actual_size != artifact.file_size_bytes:
            raise ArtifactIntegrityError(
                artifact_id,
                f"File size mismatch: expected {artifact.file_size_bytes}, got {actual_size}",
            )

        # 7: SHA-256 matches database
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()
        if actual_hash != artifact.file_sha256:
            raise ArtifactIntegrityError(
                artifact_id,
                f"SHA-256 mismatch: expected {artifact.file_sha256}, got {actual_hash}",
            )

        return artifact

    def get_artifact_path(self, storage_key: str) -> str:
        """Get the file path for an artifact download."""
        return str(self._storage.get_path(storage_key))
