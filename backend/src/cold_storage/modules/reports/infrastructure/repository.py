"""Repository implementation for report persistence."""

from __future__ import annotations

from datetime import UTC
from typing import Any, cast

import sqlalchemy as sa

from cold_storage.modules.reports.application.service import ReportRepository
from cold_storage.modules.reports.domain.enums import (
    ExportFormat,
    ReportStatus,
    ReportType,
    SourceType,
)
from cold_storage.modules.reports.domain.errors import ConcurrencyConflictError
from cold_storage.modules.reports.domain.models import (
    Report,
    ReportExportArtifact,
    ReportReviewAction,
    ReportRevision,
    ReportSourceReference,
    ReportTemplate,
)
from cold_storage.modules.reports.infrastructure.orm import (
    IdempotencyRecord,
    ReportExportArtifactRecord,
    ReportRecord,
    ReportReviewActionRecord,
    ReportRevisionRecord,
    ReportSourceReferenceRecord,
    ReportTemplateRecord,
)


class SQLReportRepository(ReportRepository):
    def __init__(self, session: Any) -> None:
        self._session = session

    # --- Report ---

    def save_report(self, report: Report) -> None:
        rec = ReportRecord(
            id=report.id,
            project_id=report.project_id,
            project_version_id=report.project_version_id,
            report_type=report.report_type.value,
            status=report.status.value,
            current_revision_number=report.current_revision_number,
            created_by=report.created_by,
            created_at=report.created_at,
            updated_at=report.updated_at,
            version=report.version,
        )
        self._session.add(rec)

    def get_report(self, report_id: str) -> Report | None:
        rec = self._session.get(ReportRecord, report_id)
        if rec is None:
            return None
        return self._to_report(rec)

    def list_reports(
        self, project_id: str | None = None, created_by: str | None = None
    ) -> list[Report]:
        stmt = sa.select(ReportRecord)
        if project_id:
            stmt = stmt.where(ReportRecord.project_id == project_id)
        if created_by:
            stmt = stmt.where(ReportRecord.created_by == created_by)
        stmt = stmt.order_by(ReportRecord.created_at.desc())
        return [self._to_report(r) for r in self._session.execute(stmt).scalars()]

    def update_report(self, report: Report, *, expected_version: int | None = None) -> None:
        """Atomic compare-and-swap update.  Single SQL UPDATE with WHERE clause."""
        stmt = (
            sa.update(ReportRecord)
            .where(ReportRecord.id == report.id)
            .values(
                status=report.status.value,
                current_revision_number=report.current_revision_number,
                updated_at=report.updated_at,
                version=report.version,
            )
        )
        if expected_version is not None:
            stmt = stmt.where(ReportRecord.version == expected_version)

        result = self._session.execute(stmt)
        if result.rowcount == 0:
            if expected_version is not None:
                raise ConcurrencyConflictError(report.id)
            raise ValueError(f"Report {report.id} not found")

    # --- Revision ---

    def save_revision(self, revision: ReportRevision) -> None:
        rec = ReportRevisionRecord(
            id=revision.id,
            report_id=revision.report_id,
            revision_number=revision.revision_number,
            schema_version=revision.schema_version,
            content_json=revision.content_json,
            canonical_content_json=revision.canonical_content_json,
            content_hash=revision.content_hash,
            quality_status=revision.quality_status.value,
            quality_findings_json=revision.quality_findings_json,
            generated_by=revision.generated_by,
            generated_at=revision.generated_at,
            supersedes_revision_id=revision.supersedes_revision_id,
        )
        self._session.add(rec)

    def get_revision(self, report_id: str, revision_number: int) -> ReportRevision | None:
        stmt = sa.select(ReportRevisionRecord).where(
            ReportRevisionRecord.report_id == report_id,
            ReportRevisionRecord.revision_number == revision_number,
        )
        rec = self._session.execute(stmt).scalar_one_or_none()
        if rec is None:
            return None
        return self._to_revision(rec)

    def list_revisions(self, report_id: str) -> list[ReportRevision]:
        stmt = (
            sa.select(ReportRevisionRecord)
            .where(ReportRevisionRecord.report_id == report_id)
            .order_by(ReportRevisionRecord.revision_number)
        )
        return [self._to_revision(r) for r in self._session.execute(stmt).scalars()]

    def get_latest_revision(self, report_id: str) -> ReportRevision | None:
        stmt = (
            sa.select(ReportRevisionRecord)
            .where(ReportRevisionRecord.report_id == report_id)
            .order_by(ReportRevisionRecord.revision_number.desc())
            .limit(1)
        )
        rec = self._session.execute(stmt).scalar_one_or_none()
        if rec is None:
            return None
        return self._to_revision(rec)

    # --- Source References ---

    def save_source_references(self, refs: list[ReportSourceReference]) -> None:
        for ref in refs:
            rec = ReportSourceReferenceRecord(
                id=ref.id,
                report_revision_id=ref.report_revision_id,
                source_type=ref.source_type.value
                if isinstance(ref.source_type, SourceType)
                else ref.source_type,
                source_id=ref.source_id,
                source_revision=ref.source_revision,
                section_key=ref.section_key,
                field_path=ref.field_path,
                tool_name=ref.tool_name,
                tool_version=ref.tool_version,
                result_id=ref.result_id,
                content_hash=ref.content_hash,
            )
            self._session.add(rec)

    # --- Review Actions ---

    def save_review_action(self, action: ReportReviewAction) -> None:
        rec = ReportReviewActionRecord(
            id=action.id,
            report_id=action.report_id,
            report_revision_id=action.report_revision_id,
            action=action.action.value,
            actor=action.actor,
            comment=action.comment,
            from_status=action.from_status.value,
            to_status=action.to_status.value,
            created_at=action.created_at,
        )
        self._session.add(rec)

    # --- Idempotency Records ---

    def save_idempotency_record(self, key: str, actor: str, action: str, fingerprint: str) -> None:
        rec = IdempotencyRecord(
            key=key,
            actor=actor,
            action=action,
            fingerprint=fingerprint,
            status="claimed",
        )
        self._session.add(rec)
        try:
            self._session.flush()
        except Exception:
            self._session.rollback()
            raise  # Will be caught by _claim_idempotency as IdempotencyClaimError

    def get_idempotency_record(self, key: str) -> dict[str, Any] | None:
        rec = self._session.get(IdempotencyRecord, key)
        if rec is None:
            return None
        return {
            "key": rec.key,
            "actor": rec.actor,
            "action": rec.action,
            "fingerprint": rec.fingerprint,
            "status": rec.status,
            "result_payload": rec.result_payload,
        }

    def complete_idempotency_record(self, key: str, result_payload: Any) -> None:
        stmt = (
            sa.update(IdempotencyRecord)
            .where(IdempotencyRecord.key == key, IdempotencyRecord.status == "claimed")
            .values(status="completed", result_payload=result_payload)
        )
        result = self._session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"Idempotency record {key} not found or not in claimed state")

    # --- Commit ---

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    # --- Serialisers ---

    def _to_report(self, rec: ReportRecord) -> Report:
        from datetime import datetime as _dt

        rt = rec.report_type
        if isinstance(rt, str):
            from cold_storage.modules.reports.domain.enums import ReportType

            rt = ReportType(rt)

        def _parse_dt(v: Any) -> Any:
            if isinstance(v, str):
                return _dt.fromisoformat(v)
            return v

        return Report(
            id=rec.id,
            project_id=rec.project_id,
            project_version_id=rec.project_version_id,
            report_type=rt,
            status=ReportStatus(rec.status),
            current_revision_number=rec.current_revision_number,
            created_by=rec.created_by,
            created_at=_parse_dt(rec.created_at),
            updated_at=_parse_dt(rec.updated_at),
            version=rec.version,
        )

    def _to_revision(self, rec: ReportRevisionRecord) -> ReportRevision:
        from datetime import datetime as _dt

        def _parse_dt(v: Any) -> Any:
            if isinstance(v, str):
                return _dt.fromisoformat(v)
            return v

        return ReportRevision(
            id=rec.id,
            report_id=rec.report_id,
            revision_number=rec.revision_number,
            schema_version=rec.schema_version,
            content_json=rec.content_json,
            canonical_content_json=rec.canonical_content_json,
            content_hash=rec.content_hash,
            quality_status=ReportStatus(rec.quality_status),
            quality_findings_json=rec.quality_findings_json,
            generated_by=rec.generated_by,
            generated_at=_parse_dt(rec.generated_at),
            supersedes_revision_id=rec.supersedes_revision_id,
        )

    # --- Templates ---

    def save_template(self, template: ReportTemplate) -> None:
        rec = ReportTemplateRecord(
            id=template.id,
            template_code=template.template_code,
            report_type=(
                template.report_type.value
                if isinstance(template.report_type, ReportType)
                else template.report_type
            ),
            format=(
                template.format.value
                if isinstance(template.format, ExportFormat)
                else template.format
            ),
            version=template.version,
            status=template.status.value,
            schema_version=template.schema_version,
            locale=template.locale,
            manifest_json=template.manifest_json,
            template_content_hash=template.template_content_hash,
            created_by=template.created_by,
            created_at=template.created_at,
            activated_at=template.activated_at,
        )
        self._session.add(rec)

    def get_template(self, template_id: str) -> ReportTemplateRecord | None:
        rec = self._session.get(ReportTemplateRecord, template_id)
        return cast(ReportTemplateRecord | None, rec)

    def get_active_template(
        self, report_type: str, fmt: str, version: str | None = None
    ) -> ReportTemplateRecord | None:
        from cold_storage.modules.reports.domain.enums import TemplateStatus

        stmt = (
            sa.select(ReportTemplateRecord)
            .where(
                ReportTemplateRecord.report_type == report_type,
                ReportTemplateRecord.format == fmt,
                ReportTemplateRecord.status == TemplateStatus.ACTIVE.value,
            )
            .order_by(ReportTemplateRecord.created_at.desc())
            .limit(1)
        )
        return cast(ReportTemplateRecord | None, self._session.execute(stmt).scalar_one_or_none())

    def list_templates(self, report_type: str | None = None) -> list[ReportTemplateRecord]:
        stmt = sa.select(ReportTemplateRecord)
        if report_type:
            stmt = stmt.where(ReportTemplateRecord.report_type == report_type)
        stmt = stmt.order_by(ReportTemplateRecord.created_at.desc())
        return list(self._session.execute(stmt).scalars())

    def activate_template(self, template_id: str) -> None:
        """Set template to active. Validate no other active template with same code+format."""
        from datetime import datetime as _dt

        from cold_storage.modules.reports.domain.enums import TemplateStatus

        rec = self._session.get(ReportTemplateRecord, template_id)
        if rec is None:
            raise ValueError(f"Template {template_id} not found")

        # Check no other active template with same code+format+version
        existing = self._session.execute(
            sa.select(ReportTemplateRecord).where(
                ReportTemplateRecord.template_code == rec.template_code,
                ReportTemplateRecord.format == rec.format,
                ReportTemplateRecord.status == TemplateStatus.ACTIVE.value,
                ReportTemplateRecord.id != template_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError(
                f"Another active template already exists for code={rec.template_code} "
                f"format={rec.format} version={existing.version}"
            )

        stmt = (
            sa.update(ReportTemplateRecord)
            .where(ReportTemplateRecord.id == template_id)
            .values(
                status=TemplateStatus.ACTIVE.value,
                activated_at=_dt.now(UTC),
            )
        )
        self._session.execute(stmt)

    def retire_template(self, template_id: str) -> None:
        from cold_storage.modules.reports.domain.enums import TemplateStatus

        stmt = (
            sa.update(ReportTemplateRecord)
            .where(ReportTemplateRecord.id == template_id)
            .values(status=TemplateStatus.RETIRED.value)
        )
        result = self._session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"Template {template_id} not found")

    # --- Export Artifacts ---

    def save_artifact(self, artifact: ReportExportArtifact) -> None:
        rec = ReportExportArtifactRecord(
            id=artifact.id,
            report_id=artifact.report_id,
            report_revision_id=artifact.report_revision_id,
            revision_number=artifact.revision_number,
            format=(
                artifact.format.value
                if isinstance(artifact.format, ExportFormat)
                else artifact.format
            ),
            template_id=artifact.template_id,
            template_version=artifact.template_version,
            schema_version=artifact.schema_version,
            status=artifact.status.value,
            storage_key=artifact.storage_key,
            file_name=artifact.file_name,
            mime_type=artifact.mime_type,
            file_size_bytes=artifact.file_size_bytes,
            file_sha256=artifact.file_sha256,
            source_content_hash=artifact.source_content_hash,
            render_manifest_json=artifact.render_manifest_json,
            generated_by=artifact.generated_by,
            generated_at=artifact.generated_at,
            failure_code=artifact.failure_code,
            failure_message=artifact.failure_message,
        )
        self._session.add(rec)

    def get_artifact(self, artifact_id: str) -> ReportExportArtifactRecord | None:
        rec = self._session.get(ReportExportArtifactRecord, artifact_id)
        return cast(ReportExportArtifactRecord | None, rec)

    def list_artifacts(self, report_id: str) -> list[ReportExportArtifactRecord]:
        stmt = (
            sa.select(ReportExportArtifactRecord)
            .where(ReportExportArtifactRecord.report_id == report_id)
            .order_by(ReportExportArtifactRecord.generated_at.desc())
        )
        return list(self._session.execute(stmt).scalars())

    def update_artifact(self, artifact_id: str, **fields: Any) -> None:
        if not fields:
            return
        stmt = (
            sa.update(ReportExportArtifactRecord)
            .where(ReportExportArtifactRecord.id == artifact_id)
            .values(**fields)
        )
        result = self._session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"Artifact {artifact_id} not found")
