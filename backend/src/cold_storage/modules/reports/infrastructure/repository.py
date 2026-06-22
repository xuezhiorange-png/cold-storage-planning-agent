"""Repository implementation for report persistence."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from cold_storage.modules.reports.application.service import ReportRepository
from cold_storage.modules.reports.domain.enums import ReportStatus, SourceType
from cold_storage.modules.reports.domain.models import (
    Report,
    ReportReviewAction,
    ReportRevision,
    ReportSourceReference,
)
from cold_storage.modules.reports.infrastructure.orm import (
    ReportRecord,
    ReportReviewActionRecord,
    ReportRevisionRecord,
    ReportSourceReferenceRecord,
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
        rec = self._session.get(ReportRecord, report.id)
        if rec is None:
            raise ValueError(f"Report {report.id} not found")
        if expected_version is not None and rec.version != expected_version:
            raise ValueError(
                f"Report {report.id} version mismatch "
                f"(expected {expected_version}, got {rec.version})"
            )
        rec.status = report.status.value
        rec.current_revision_number = report.current_revision_number
        rec.updated_at = report.updated_at
        rec.version = report.version

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

    # --- Commit ---

    def commit(self) -> None:
        self._session.commit()

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
