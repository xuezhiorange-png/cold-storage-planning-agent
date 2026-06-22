"""Report render service — orchestrates export rendering to DOCX/PDF.

No ORM access, no LLM calls.  Uses repository port, artifact storage,
and renderers.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

from cold_storage.modules.reports.domain.enums import (
    DRAFT_EXPORT_STATUSES,
    FORMAL_EXPORT_STATUSES,
    ArtifactStatus,
    ExportFormat,
    RenderMode,
)
from cold_storage.modules.reports.domain.errors import (
    ArtifactNotFoundError,
    ExportPermissionError,
    RenderError,
    ReportNotFoundError,
)
from cold_storage.modules.reports.domain.models import (
    Report,
    ReportExportArtifact,
    ReportTemplate,
)


class ReportTemplateRepository:
    """Port: persistence for report templates."""

    def get_template(self, template_id: str) -> ReportTemplate | None:
        raise NotImplementedError

    def get_active_template(
        self, template_code: str, format: ExportFormat
    ) -> ReportTemplate | None:
        raise NotImplementedError

    def list_templates(
        self,
        template_code: str | None = None,
        format: ExportFormat | None = None,
    ) -> list[ReportTemplate]:
        raise NotImplementedError

    def save_template(self, template: ReportTemplate) -> None:
        raise NotImplementedError

    def update_template(self, template: ReportTemplate) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError


class ReportArtifactRepository:
    """Port: persistence for export artifacts."""

    def save_artifact(self, artifact: ReportExportArtifact) -> None:
        raise NotImplementedError

    def get_artifact(self, artifact_id: str) -> ReportExportArtifact | None:
        raise NotImplementedError

    def list_artifacts(
        self, report_id: str, status: ArtifactStatus | None = None
    ) -> list[ReportExportArtifact]:
        raise NotImplementedError

    def find_artifact_by_idempotency(
        self, idempotency_key: str, report_id: str
    ) -> ReportExportArtifact | None:
        raise NotImplementedError

    def update_artifact(self, artifact: ReportExportArtifact) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError


class ReportRenderService:
    """Application service for report export rendering.

    Parameters
    ----------
    repository:
        Report repository port (for loading report and revision).
    storage:
        Artifact storage adapter (for saving rendered files).
    template_repo:
        Template repository port (for loading templates).
    artifact_repo:
        Artifact repository port (for persisting artifact records).
    """

    def __init__(
        self,
        repository: Any,
        storage: Any,
        template_repo: ReportTemplateRepository | None = None,
        artifact_repo: ReportArtifactRepository | None = None,
    ) -> None:
        self._repo = repository
        self._storage = storage
        self._template_repo = template_repo
        self._artifact_repo = artifact_repo

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

        # 3. Validate draft/formal rules
        self._validate_export_mode(report, render_mode)

        # 4. Idempotency check
        if idempotency_key and self._artifact_repo:
            existing = self._artifact_repo.find_artifact_by_idempotency(idempotency_key, report_id)
            if existing is not None:
                return existing

        # 5. Find the active template (or specific version)
        template = self._find_template(export_format, template_version)

        # 6. Build render model from revision content
        from cold_storage.modules.reports.application.render_model_builder import (
            build_render_model,
        )

        render_model = build_render_model(
            content=revision.content_json,
            report_id=revision.report_id,
            revision_number=revision.revision_number,
            content_hash=revision.content_hash,
            generated_by=revision.generated_by,
            generated_at=revision.generated_at,
            template_version=template.version if template else "1.0.0",
            template_code=template.template_code if template else "cold_storage_concept_design",
        )

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
            template_id=template.id if template else "",
            template_version=template.version if template else "1.0.0",
            schema_version=revision.schema_version,
            file_name=file_name,
            mime_type=mime_type,
            source_content_hash=revision.content_hash,
            generated_by=actor,
        )

        if self._artifact_repo:
            self._artifact_repo.save_artifact(artifact)

        # 8. Render via DocxRenderer or PdfRenderer
        try:
            rendered_bytes = self._render_bytes(export_format, render_model, template)

            # 9. Compute file SHA-256
            file_sha256 = hashlib.sha256(rendered_bytes).hexdigest()

            # 10. Save to artifact storage
            storage_key = self._storage.put(artifact.id, rendered_bytes, file_name)

            # 11. Update artifact with storage_key, file_size, file_sha256, status=completed
            artifact = replace(
                artifact,
                status=ArtifactStatus.COMPLETED,
                storage_key=storage_key,
                file_size_bytes=len(rendered_bytes),
                file_sha256=file_sha256,
                render_manifest_json=render_model.manifest.__dict__
                if hasattr(render_model.manifest, "__dict__")
                else {},
            )

            if self._artifact_repo:
                self._artifact_repo.update_artifact(artifact)
                self._artifact_repo.commit()

            return artifact

        except Exception as exc:
            # 12. On failure: set status=failed, clean up
            artifact = replace(
                artifact,
                status=ArtifactStatus.FAILED,
                failure_code=type(exc).__name__,
                failure_message=str(exc),
            )
            if self._artifact_repo:
                self._artifact_repo.update_artifact(artifact)
                self._artifact_repo.commit()

            # Clean up any partially written storage
            if artifact.storage_key:
                import contextlib

                with contextlib.suppress(FileNotFoundError):
                    self._storage.delete(artifact.storage_key)

            raise RenderError(f"Rendering failed: {exc}") from exc

    def _validate_export_mode(self, report: Report, mode: RenderMode) -> None:
        """Validate that the report status allows the requested export mode."""
        allowed = (
            DRAFT_EXPORT_STATUSES
            if mode == RenderMode.DRAFT
            else FORMAL_EXPORT_STATUSES
            if mode == RenderMode.FORMAL
            else frozenset()
        )
        if report.status not in allowed:
            raise ExportPermissionError(report.id, mode.value, report.status.value)

    def _find_template(
        self,
        format: ExportFormat,
        template_version: str | None,  # noqa: A002
    ) -> ReportTemplate | None:
        """Find the active template or specific version."""
        if self._template_repo is None:
            return None

        if template_version:
            # Find by version - list all and filter
            templates = self._template_repo.list_templates(format=format)
            for t in templates:
                if t.version == template_version:
                    return t
            return None

        # Find active template
        return self._template_repo.get_active_template(
            template_code="cold_storage_concept_design",
            format=format,
        )

    def _render_bytes(
        self,
        format: ExportFormat,  # noqa: A002
        render_model: Any,
        template: ReportTemplate | None,
    ) -> bytes:
        """Render the model to bytes using the appropriate renderer."""

        if format == ExportFormat.DOCX:
            from cold_storage.modules.reports.renderers.docx_renderer import (
                DocxRenderer,
            )

            docx_renderer = DocxRenderer()
            return docx_renderer.render(render_model)
        elif format == ExportFormat.PDF:
            from cold_storage.modules.reports.renderers.pdf_renderer import (
                PdfRenderer,
            )

            pdf_renderer = PdfRenderer()
            return pdf_renderer.render(render_model)
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

    def get_artifact_path(self, storage_key: str) -> str:
        """Get the file path for an artifact download."""
        return str(self._storage.get_path(storage_key))
