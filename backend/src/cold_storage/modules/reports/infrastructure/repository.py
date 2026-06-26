"""Repository implementation for report persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from cold_storage.modules.reports.application.service import ReportRepository
from cold_storage.modules.reports.domain.enums import (
    ArtifactStatus,
    ExportFormat,
    ReportLocale,
    ReportStatus,
    ReportType,
    SourceType,
    TemplateStatus,
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
    CleanupDebtRecord,
    DeletionOutboxRecord,
    DeletionReceiptRecord,
    IdempotencyRecord,
    MigrationAuditRecord,
    ReportExportArtifactRecord,
    ReportRecord,
    ReportReviewActionRecord,
    ReportRevisionRecord,
    ReportSourceReferenceRecord,
    ReportTemplateRecord,
)

# ---------------------------------------------------------------------------
# ORM -> Domain converters
# ---------------------------------------------------------------------------


def _parse_dt(v: Any) -> Any:
    """Parse an ISO datetime string to a datetime object, or pass through."""
    if isinstance(v, str):
        from datetime import datetime as _dt

        return _dt.fromisoformat(v)
    return v


def _to_template_domain(rec: ReportTemplateRecord) -> ReportTemplate:
    """Convert a ReportTemplateRecord ORM to a domain ReportTemplate."""
    return ReportTemplate(
        id=rec.id,
        template_code=rec.template_code,
        report_type=ReportType(rec.report_type),
        format=ExportFormat(rec.format),
        version=rec.version,
        status=TemplateStatus(rec.status),
        schema_version=rec.schema_version,
        locale=ReportLocale(rec.locale),
        manifest_json=rec.manifest_json or {},
        template_content_hash=rec.template_content_hash,
        created_by=rec.created_by,
        created_at=_parse_dt(rec.created_at),
        activated_at=_parse_dt(rec.activated_at),
    )


def _to_artifact_domain(rec: ReportExportArtifactRecord) -> ReportExportArtifact:
    """Convert a ReportExportArtifactRecord ORM to a domain ReportExportArtifact."""
    return ReportExportArtifact(
        id=rec.id,
        report_id=rec.report_id,
        report_revision_id=rec.report_revision_id,
        revision_number=rec.revision_number,
        format=ExportFormat(rec.format),
        template_id=rec.template_id,
        template_version=rec.template_version,
        schema_version=rec.schema_version,
        status=ArtifactStatus(rec.status),
        storage_key=rec.storage_key,
        file_name=rec.file_name,
        mime_type=rec.mime_type,
        file_size_bytes=rec.file_size_bytes,
        file_sha256=rec.file_sha256,
        source_content_hash=rec.source_content_hash,
        render_manifest_json=rec.render_manifest_json or {},
        generated_by=rec.generated_by,
        generated_at=_parse_dt(rec.generated_at),
        failure_code=rec.failure_code,
        failure_message=rec.failure_message,
        idempotency_key=rec.idempotency_key,
        claim_token=rec.claim_token,
        claim_version=rec.claim_version,
        locale=ReportLocale(rec.locale),
        translation_catalog_version=rec.translation_catalog_version,
        localized_template_content_hash=rec.localized_template_content_hash,
        template_locale=ReportLocale(rec.template_locale),
        translation_catalog_content_hash=rec.translation_catalog_content_hash,
    )


class SQLReportRepository(ReportRepository):
    def __init__(self, session: sa.orm.Session) -> None:
        self._session = session

    # --- Report ---

    def save_report(self, report: Report) -> None:
        from datetime import datetime as _dt

        approved_at_dt: _dt | None = None
        if report.approved_at is not None:
            if isinstance(report.approved_at, str):
                approved_at_dt = _dt.fromisoformat(report.approved_at)
            elif isinstance(report.approved_at, _dt):
                approved_at_dt = report.approved_at
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
            approved_revision_id=report.approved_revision_id,
            approved_content_hash=report.approved_content_hash,
            approved_by=report.approved_by,
            approved_at=approved_at_dt,
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
        from datetime import datetime as _dt

        approved_at_dt: _dt | None = None
        if report.approved_at is not None:
            if isinstance(report.approved_at, str):
                approved_at_dt = _dt.fromisoformat(report.approved_at)
            elif isinstance(report.approved_at, _dt):
                approved_at_dt = report.approved_at
        stmt = (
            sa.update(ReportRecord)
            .where(ReportRecord.id == report.id)
            .values(
                status=report.status.value,
                current_revision_number=report.current_revision_number,
                updated_at=report.updated_at,
                version=report.version,
                approved_revision_id=report.approved_revision_id,
                approved_content_hash=report.approved_content_hash,
                approved_by=report.approved_by,
                approved_at=approved_at_dt,
            )
        )
        if expected_version is not None:
            stmt = stmt.where(ReportRecord.version == expected_version)

        result = self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
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

    def save_idempotency_record(
        self, key: str, actor: str, action: str, fingerprint: str
    ) -> tuple[str, int]:
        from datetime import datetime as _dt

        now = _dt.now(UTC)
        claim_token = str(uuid.uuid4())
        rec = IdempotencyRecord(
            key=key,
            actor=actor,
            action=action,
            fingerprint=fingerprint,
            status="claimed",
            claimed_at=now,
            claim_token=claim_token,
            claim_version=1,
        )
        self._session.add(rec)
        try:
            self._session.flush()
        except Exception:
            self._session.rollback()
            raise  # Will be caught by _claim_idempotency as IdempotencyClaimError
        return claim_token, 1

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
            "claimed_at": rec.claimed_at,
            "claim_token": rec.claim_token,
            "claim_version": rec.claim_version,
        }

    def complete_idempotency_record(
        self,
        key: str,
        result_payload: Any,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None:
        """Complete an idempotency record. Requires matching claim_token + version."""
        stmt = (
            sa.update(IdempotencyRecord)
            .where(
                IdempotencyRecord.key == key,
                IdempotencyRecord.status == "claimed",
                IdempotencyRecord.claim_token == claim_token,
                IdempotencyRecord.claim_version == claim_version,
            )
            .values(status="completed", result_payload=result_payload)
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            from cold_storage.modules.reports.domain.errors import StaleClaimError

            raise StaleClaimError(key, "complete_idempotency: claim mismatch")

    def fail_idempotency_record(
        self,
        key: str,
        failure_code: str,
        failure_message: str,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None:
        """Mark an idempotency record as failed. Requires matching claim_token + version."""
        from cold_storage.modules.reports.domain.errors import StaleClaimError

        stmt = (
            sa.update(IdempotencyRecord)
            .where(
                IdempotencyRecord.key == key,
                IdempotencyRecord.status == "claimed",
                IdempotencyRecord.claim_token == claim_token,
                IdempotencyRecord.claim_version == claim_version,
            )
            .values(
                status="failed",
                result_payload={"failure_code": failure_code, "failure_message": failure_message},
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise StaleClaimError(key, "fail_idempotency: claim mismatch")

    def reset_failed_idempotency(self, key: str) -> None:
        """Delete a failed idempotency record to allow retry with same key."""
        stmt = sa.delete(IdempotencyRecord).where(
            IdempotencyRecord.key == key,
            IdempotencyRecord.status == "failed",
        )
        self._session.execute(stmt)

    def reclaim_stale_idempotency(
        self,
        key: str,
        fingerprint: str,
        cutoff: datetime,
        original_claimed_at: datetime,
        *,
        old_claim_token: str,
        old_claim_version: int,
    ) -> tuple[bool, str | None, int | None]:
        """Atomically reclaim a stale claimed idempotency record.

        Strict CAS: ALL of the following must match for exactly one winner:
        - key
        - status = 'claimed'
        - fingerprint
        - claimed_at = original_claimed_at
        - claimed_at < cutoff
        - claim_token = old_claim_token
        - claim_version = old_claim_version

        Returns (success, new_token, new_version) or (False, None, None).
        """
        conditions = [
            IdempotencyRecord.key == key,
            IdempotencyRecord.status == "claimed",
            IdempotencyRecord.fingerprint == fingerprint,
            IdempotencyRecord.claimed_at == original_claimed_at,
            IdempotencyRecord.claimed_at < cutoff,
            IdempotencyRecord.claim_token == old_claim_token,
            IdempotencyRecord.claim_version == old_claim_version,
        ]
        new_token = str(uuid.uuid4())
        new_version = old_claim_version + 1
        stmt = (
            sa.update(IdempotencyRecord)
            .where(sa.and_(*conditions))
            .values(
                status="claimed",
                claimed_at=sa.func.now(),
                updated_at=sa.func.now(),
                claim_token=new_token,
                claim_version=new_version,
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            return False, None, None
        return True, new_token, new_version

    def fail_nonterminal_artifacts(
        self,
        report_id: str,
        *,
        idempotency_key: str,
        stale_claim_token: str,
        stale_claim_version: int,
    ) -> tuple[int, list[str]]:
        """Mark non-terminal artifacts as failed, scoped to a stale claim.

        WHERE: report_id + idempotency_key + claim_token + claim_version
        + status IN (pending, rendering)

        Returns (count, list_of_storage_keys) so the caller can physically
        delete the old artifact files from storage.
        """
        conditions = [
            ReportExportArtifactRecord.report_id == report_id,
            ReportExportArtifactRecord.idempotency_key == idempotency_key,
            ReportExportArtifactRecord.claim_token == stale_claim_token,
            ReportExportArtifactRecord.claim_version == stale_claim_version,
            ReportExportArtifactRecord.status.in_(["pending", "rendering"]),
        ]
        # First, collect storage_keys of matching artifacts
        select_stmt = sa.select(ReportExportArtifactRecord.storage_key).where(sa.and_(*conditions))
        keys_result = self._session.execute(select_stmt)
        storage_keys: list[str] = [row[0] for row in keys_result.fetchall() if row[0]]

        # Then mark them as failed
        update_stmt = (
            sa.update(ReportExportArtifactRecord)
            .where(sa.and_(*conditions))
            .values(
                status="failed",
                failure_code="stale_claim_recovery",
                failure_message="Orphaned by stale claim recovery",
            )
        )
        result = self._session.execute(update_stmt)
        count: int = result.rowcount  # type: ignore[attr-defined]
        return count, storage_keys

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
            approved_revision_id=rec.approved_revision_id,
            approved_content_hash=rec.approved_content_hash,
            approved_by=rec.approved_by,
            approved_at=rec.approved_at.isoformat() if rec.approved_at is not None else None,
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
            # P0-7: Set active_slot based on status
            active_slot="active" if template.status.value == "active" else None,
        )
        self._session.add(rec)

    def get_template(self, template_id: str) -> ReportTemplate | None:
        rec = self._session.get(ReportTemplateRecord, template_id)
        if rec is None:
            return None
        return _to_template_domain(rec)

    def get_active_template(
        self,
        template_code: str,
        format: str,
        locale: ReportLocale | None = None,
    ) -> ReportTemplate | None:
        conditions = [
            ReportTemplateRecord.template_code == template_code,
            ReportTemplateRecord.format == format,
            ReportTemplateRecord.status == TemplateStatus.ACTIVE.value,
        ]
        if locale is not None:
            conditions.append(ReportTemplateRecord.locale == locale.value)
        stmt = (
            sa.select(ReportTemplateRecord)
            .where(sa.and_(*conditions))
            .order_by(ReportTemplateRecord.created_at.desc())
            .limit(1)
        )
        rec = self._session.execute(stmt).scalar_one_or_none()
        if rec is None:
            return None
        return _to_template_domain(rec)

    def list_templates(
        self,
        template_code: str | None = None,
        format: str | None = None,
        locale: ReportLocale | None = None,
    ) -> list[ReportTemplate]:
        stmt = sa.select(ReportTemplateRecord)
        if template_code:
            stmt = stmt.where(ReportTemplateRecord.template_code == template_code)
        if format:
            stmt = stmt.where(ReportTemplateRecord.format == format)
        if locale is not None:
            stmt = stmt.where(ReportTemplateRecord.locale == locale.value)
        stmt = stmt.order_by(ReportTemplateRecord.created_at.desc())
        return [_to_template_domain(r) for r in self._session.execute(stmt).scalars()]

    def deactivate_templates(
        self,
        template_code: str,
        fmt: str,
        locale: ReportLocale | None = None,
    ) -> int:
        """Deactivate all active templates for the given code, format, and locale.

        P0-7: Sets active_slot = NULL and status = DRAFT for all matching active templates.
        If locale is provided, only deactivates templates with that locale.
        If locale is None, deactivates all locales for the given code+format.

        Returns the number of templates deactivated.
        """
        conditions = [
            ReportTemplateRecord.template_code == template_code,
            ReportTemplateRecord.format == fmt,
            ReportTemplateRecord.status == TemplateStatus.ACTIVE.value,
        ]
        if locale is not None:
            conditions.append(ReportTemplateRecord.locale == locale.value)
        stmt = (
            sa.update(ReportTemplateRecord)
            .where(sa.and_(*conditions))
            .values(status=TemplateStatus.DRAFT.value, active_slot=None)
        )
        result = self._session.execute(stmt)
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

    def update_template(self, template: ReportTemplate) -> None:
        """Update an existing template by ID (status, activated_at, active_slot, etc.).

        P0-7: Includes active_slot in the update.
        P0-3: Also updates manifest_json, template_content_hash, and version.
        """
        # P0-7: Determine active_slot from status
        from cold_storage.modules.reports.infrastructure.orm import ReportTemplateRecord as _Rec

        values: dict[str, Any] = {
            "status": template.status.value,
            "activated_at": template.activated_at,
        }
        # P0-7: Set active_slot based on status
        if template.status.value == "active":
            values["active_slot"] = "active"
        else:
            values["active_slot"] = None

        # P0-3: Update manifest, hash, and version fields
        if template.manifest_json is not None:
            values["manifest_json"] = template.manifest_json
        if template.template_content_hash is not None:
            values["template_content_hash"] = template.template_content_hash
        if template.version is not None:
            values["version"] = template.version

        stmt = sa.update(_Rec).where(_Rec.id == template.id).values(**values)
        result = self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Template {template.id} not found")

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
            idempotency_key=artifact.idempotency_key,
            claim_token=artifact.claim_token,
            claim_version=artifact.claim_version,
            locale=artifact.locale,
            translation_catalog_version=artifact.translation_catalog_version,
            localized_template_content_hash=artifact.localized_template_content_hash,
            template_locale=(
                artifact.template_locale.value
                if isinstance(artifact.template_locale, ReportLocale)
                else artifact.template_locale
            ),
            translation_catalog_content_hash=artifact.translation_catalog_content_hash,
        )
        self._session.add(rec)

    def insert_artifact_with_claim(
        self,
        artifact: ReportExportArtifact,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None:
        """Atomically verify claim validity and INSERT artifact.

        For PostgreSQL: SELECT ... FOR UPDATE on idempotency record,
        then verify claim, then INSERT artifact.
        For SQLite: guard UPDATE to acquire write lock, then INSERT.

        Raises StaleClaimError if the claim is no longer held.
        """
        from cold_storage.modules.reports.domain.errors import StaleClaimError

        # Guard: acquire write lock / row lock on the idempotency record
        if artifact.idempotency_key:
            is_postgres = (
                self._session.bind.dialect.name  # type: ignore[union-attr]
                == "postgresql"
            )
            if is_postgres:
                # PostgreSQL: SELECT ... FOR UPDATE
                idem_stmt = (
                    sa.select(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.key == artifact.idempotency_key,
                        IdempotencyRecord.status == "claimed",
                        IdempotencyRecord.claim_token == claim_token,
                        IdempotencyRecord.claim_version == claim_version,
                    )
                    .with_for_update()
                )
                idem_rec = self._session.execute(idem_stmt).scalar_one_or_none()
                if idem_rec is None:
                    raise StaleClaimError(
                        artifact.idempotency_key,
                        "insert_artifact: claim no longer held",
                    )
            else:
                # SQLite: guard UPDATE to acquire write lock
                guard_stmt = (
                    sa.update(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.key == artifact.idempotency_key,
                        IdempotencyRecord.status == "claimed",
                        IdempotencyRecord.claim_token == claim_token,
                        IdempotencyRecord.claim_version == claim_version,
                    )
                    .values(updated_at=sa.func.now())
                )
                result = self._session.execute(guard_stmt)
                if result.rowcount != 1:  # type: ignore[attr-defined]
                    raise StaleClaimError(
                        artifact.idempotency_key,
                        "insert_artifact: claim no longer held",
                    )

        # INSERT artifact
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
            idempotency_key=artifact.idempotency_key,
            claim_token=artifact.claim_token,
            claim_version=artifact.claim_version,
            locale=artifact.locale,
            translation_catalog_version=artifact.translation_catalog_version,
            localized_template_content_hash=artifact.localized_template_content_hash,
            template_locale=(
                artifact.template_locale.value
                if isinstance(artifact.template_locale, ReportLocale)
                else artifact.template_locale
            ),
            translation_catalog_content_hash=artifact.translation_catalog_content_hash,
        )
        self._session.add(rec)

    def get_artifact(self, artifact_id: str) -> ReportExportArtifact | None:
        rec = self._session.get(ReportExportArtifactRecord, artifact_id)
        if rec is None:
            return None
        return _to_artifact_domain(rec)

    def list_artifacts(
        self,
        report_id: str,
        status: ArtifactStatus | None = None,
        locale: ReportLocale | None = None,
    ) -> list[ReportExportArtifact]:
        stmt = sa.select(ReportExportArtifactRecord).where(
            ReportExportArtifactRecord.report_id == report_id
        )
        if status is not None:
            stmt = stmt.where(ReportExportArtifactRecord.status == status.value)
        if locale is not None:
            stmt = stmt.where(ReportExportArtifactRecord.locale == locale.value)
        stmt = stmt.order_by(ReportExportArtifactRecord.generated_at.desc())
        return [_to_artifact_domain(r) for r in self._session.execute(stmt).scalars()]

    def find_artifact_by_idempotency(
        self, idempotency_key: str, report_id: str
    ) -> ReportExportArtifact | None:
        """Find an artifact by its idempotency key."""
        stmt = sa.select(ReportExportArtifactRecord).where(
            ReportExportArtifactRecord.report_id == report_id,
            ReportExportArtifactRecord.idempotency_key == idempotency_key,
        )
        rec = self._session.execute(stmt).scalar_one_or_none()
        if rec is None:
            return None
        return _to_artifact_domain(rec)

    def update_artifact(self, artifact: ReportExportArtifact) -> None:
        """Update an existing artifact record by ID."""
        stmt = (
            sa.update(ReportExportArtifactRecord)
            .where(ReportExportArtifactRecord.id == artifact.id)
            .values(
                status=artifact.status.value,
                storage_key=artifact.storage_key,
                file_size_bytes=artifact.file_size_bytes,
                file_sha256=artifact.file_sha256,
                render_manifest_json=artifact.render_manifest_json,
                failure_code=artifact.failure_code,
                failure_message=artifact.failure_message,
                locale=artifact.locale,
                translation_catalog_version=artifact.translation_catalog_version,
                localized_template_content_hash=artifact.localized_template_content_hash,
                template_locale=(
                    artifact.template_locale.value
                    if isinstance(artifact.template_locale, ReportLocale)
                    else artifact.template_locale
                ),
                translation_catalog_content_hash=artifact.translation_catalog_content_hash,
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Artifact {artifact.id} not found")

    def transition_artifact(
        self,
        artifact: ReportExportArtifact,
        *,
        expected_status: ArtifactStatus,
        claim_token: str,
        claim_version: int,
    ) -> None:
        """Atomically transition an artifact status with claim fencing.

        Uses a single UPDATE with an EXISTS subquery against
        idempotency_records to ensure the claim is still valid at the
        exact moment of the artifact state change.  This is atomic on
        both PostgreSQL and SQLite (no TOCTOU between SELECT and UPDATE).

        Raises StaleClaimError if:
        - The artifact is not in expected_status
        - The idempotency claim is no longer held by this token/version
        """
        from cold_storage.modules.reports.domain.errors import StaleClaimError

        if artifact.idempotency_key:
            # Single atomic UPDATE with EXISTS subquery
            stmt = (
                sa.update(ReportExportArtifactRecord)
                .where(
                    ReportExportArtifactRecord.id == artifact.id,
                    ReportExportArtifactRecord.status == expected_status.value,
                    ReportExportArtifactRecord.idempotency_key == artifact.idempotency_key,
                    ReportExportArtifactRecord.claim_token == claim_token,
                    ReportExportArtifactRecord.claim_version == claim_version,
                    sa.exists()
                    .where(
                        IdempotencyRecord.key == artifact.idempotency_key,
                        IdempotencyRecord.status == "claimed",
                        IdempotencyRecord.claim_token == claim_token,
                        IdempotencyRecord.claim_version == claim_version,
                    )
                    .correlate(ReportExportArtifactRecord),
                )
                .values(
                    status=artifact.status.value,
                    storage_key=artifact.storage_key,
                    file_size_bytes=artifact.file_size_bytes,
                    file_sha256=artifact.file_sha256,
                    render_manifest_json=artifact.render_manifest_json,
                    failure_code=artifact.failure_code,
                    failure_message=artifact.failure_message,
                )
            )
            result = self._session.execute(stmt)
            if result.rowcount != 1:  # type: ignore[attr-defined]
                raise StaleClaimError(
                    artifact.idempotency_key,
                    f"artifact transition {expected_status.value}"
                    f" -> {artifact.status.value}: mismatch",
                )
        else:
            # No idempotency — plain update
            stmt = (
                sa.update(ReportExportArtifactRecord)
                .where(
                    ReportExportArtifactRecord.id == artifact.id,
                    ReportExportArtifactRecord.status == expected_status.value,
                )
                .values(
                    status=artifact.status.value,
                    storage_key=artifact.storage_key,
                    file_size_bytes=artifact.file_size_bytes,
                    file_sha256=artifact.file_sha256,
                    render_manifest_json=artifact.render_manifest_json,
                    failure_code=artifact.failure_code,
                    failure_message=artifact.failure_message,
                )
            )
            result = self._session.execute(stmt)
            if result.rowcount != 1:  # type: ignore[attr-defined]
                raise StaleClaimError(
                    "",
                    f"artifact transition {expected_status.value}"
                    f" -> {artifact.status.value}: mismatch",
                )

    def fail_attempt_with_claim(
        self,
        artifact_id: str,
        idempotency_key: str,
        claim_token: str,
        claim_version: int,
        failure_code: str,
        failure_message: str,
    ) -> None:
        """Atomically fail an idempotency record and its non-terminal artifact.

        In a single transaction:
        1. CAS-update idempotency claimed → failed (binding token+version)
        2. UPDATE the artifact to failed (only if status IN pending/rendering
           and claim matches)
        3. If the artifact exists but key/token/version/status don't match,
           raise StaleClaimError to avoid inconsistent state.
        4. Artifact not yet inserted (failed before INSERT) is allowed.

        Raises StaleClaimError if:
        - The idempotency claim is no longer held
        - The artifact exists but has mismatched claim/status
        """
        from cold_storage.modules.reports.domain.errors import StaleClaimError

        # Step 1: fail idempotency record with fencing
        idem_stmt = (
            sa.update(IdempotencyRecord)
            .where(
                IdempotencyRecord.key == idempotency_key,
                IdempotencyRecord.status == "claimed",
                IdempotencyRecord.claim_token == claim_token,
                IdempotencyRecord.claim_version == claim_version,
            )
            .values(
                status="failed",
                result_payload={"failure_code": failure_code, "failure_message": failure_message},
            )
        )
        idem_result = self._session.execute(idem_stmt)
        if idem_result.rowcount != 1:  # type: ignore[attr-defined]
            raise StaleClaimError(idempotency_key, "fail_attempt_with_claim: claim mismatch")

        # Step 2: fail the artifact
        art_stmt = (
            sa.update(ReportExportArtifactRecord)
            .where(
                ReportExportArtifactRecord.id == artifact_id,
                ReportExportArtifactRecord.idempotency_key == idempotency_key,
                ReportExportArtifactRecord.claim_token == claim_token,
                ReportExportArtifactRecord.claim_version == claim_version,
                ReportExportArtifactRecord.status.in_(["pending", "rendering"]),
            )
            .values(
                status="failed",
                failure_code=failure_code,
                failure_message=failure_message,
            )
        )
        art_result = self._session.execute(art_stmt)
        art_rowcount: int = art_result.rowcount  # type: ignore[attr-defined]

        if art_rowcount == 0:
            # Artifact may not exist yet (failed before INSERT) — check
            art_check = self._session.execute(
                sa.select(ReportExportArtifactRecord.id).where(
                    ReportExportArtifactRecord.id == artifact_id,
                )
            ).scalar_one_or_none()
            if art_check is not None:
                # Artifact exists but didn't match — inconsistent state
                raise StaleClaimError(
                    idempotency_key,
                    "fail_attempt_with_claim: artifact exists but claim/status mismatch",
                )
            # Artifact doesn't exist — failed before INSERT, OK

    # --- Cleanup Debt ---

    def insert_cleanup_debt(
        self,
        *,
        idempotency_key: str,
        storage_key: str,
        stale_claim_token: str,
        stale_claim_version: int,
        reclaim_token: str,
        reclaim_version: int,
    ) -> str:
        """Insert a pending cleanup debt record.

        Returns the debt ID.
        """
        debt_id = str(uuid.uuid4())
        rec = CleanupDebtRecord(
            id=debt_id,
            idempotency_key=idempotency_key,
            storage_key=storage_key,
            stale_claim_token=stale_claim_token,
            stale_claim_version=stale_claim_version,
            reclaim_token=reclaim_token,
            reclaim_version=reclaim_version,
            status="pending",
            next_retry_at=None,
        )
        self._session.add(rec)
        return debt_id

    def claim_cleanup_debt(
        self,
        debt_id: str,
        *,
        lock_seconds: int = 300,
        observed_locked_at: datetime | None = None,
        observed_locked_by: str = "",
        observed_lock_expires_at: datetime | None = None,
    ) -> bool:
        """CAS: claim a pending, retryable, or expired-processing debt.

        For pending/retryable debts, the claim succeeds immediately.
        For expired processing debts, the lease values
        (locked_at, locked_by, lock_expires_at) must match exactly (CAS).

        Returns True if the claim succeeded.
        """
        from datetime import timedelta

        now = datetime.now(UTC)
        new_locked_by = str(uuid.uuid4())

        # Try 1: claim pending or retryable (no lease CAS)
        stmt = (
            sa.update(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.id == debt_id,
                CleanupDebtRecord.status.in_(["pending", "retryable"]),
            )
            .values(
                status="processing",
                locked_at=now,
                locked_by=new_locked_by,
                lock_expires_at=now + timedelta(seconds=lock_seconds),
                claim_version=CleanupDebtRecord.claim_version + 1,
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount == 1:  # type: ignore[attr-defined]
            return True

        # Try 2: claim expired processing with exact lease CAS
        stmt = (
            sa.update(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.id == debt_id,
                CleanupDebtRecord.status == "processing",
                CleanupDebtRecord.locked_at == observed_locked_at,
                CleanupDebtRecord.locked_by == observed_locked_by,
                CleanupDebtRecord.lock_expires_at == observed_lock_expires_at,
            )
            .values(
                status="processing",
                locked_at=now,
                locked_by=new_locked_by,
                lock_expires_at=now + timedelta(seconds=lock_seconds),
                claim_version=CleanupDebtRecord.claim_version + 1,
            )
        )
        result = self._session.execute(stmt)
        return bool(result.rowcount == 1)  # type: ignore[attr-defined]

    def mark_cleanup_completed(self, debt_id: str, *, observed_claim_version: int = 0) -> None:
        """Mark a cleanup debt as completed (processing -> completed).

        The claim_version must match (CAS) to prevent completing a debt
        that has been re-claimed by another worker.
        """
        stmt = (
            sa.update(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.id == debt_id,
                CleanupDebtRecord.status == "processing",
                CleanupDebtRecord.claim_version == observed_claim_version,
            )
            .values(status="completed", completed_at=datetime.now(UTC))
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ValueError(
                f"Cleanup debt {debt_id} not found, not processing, or claim_version mismatch"
            )

    def mark_cleanup_retryable(self, debt_id: str, error: str, *, backoff: int = 30) -> None:
        """Mark a cleanup debt as retryable with deterministic backoff.

        Sets status to 'retryable', increments retry_count, and calculates
        next_retry_at using exponential backoff: backoff * 2^retry_count.
        """
        from datetime import timedelta

        # Read current retry_count atomically
        current = self._session.execute(
            sa.select(CleanupDebtRecord.retry_count).where(CleanupDebtRecord.id == debt_id)
        ).scalar()
        new_count = (current or 0) + 1
        delay_seconds = backoff * (2 ** (new_count - 1))
        stmt = (
            sa.update(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.id == debt_id,
                CleanupDebtRecord.status == "processing",
            )
            .values(
                status="retryable",
                retry_count=new_count,
                last_error=error[:1024],
                next_retry_at=datetime.now(UTC) + timedelta(seconds=delay_seconds),
                locked_at=None,
                locked_by="",
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ValueError(f"Cleanup debt {debt_id} not found or not processing")

    def mark_cleanup_permanent_failed(self, debt_id: str, error: str) -> None:
        """Mark a retryable cleanup debt as permanent_failed."""
        stmt = (
            sa.update(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.id == debt_id,
                CleanupDebtRecord.status == "retryable",
            )
            .values(
                status="permanent_failed",
                last_error=error[:1024],
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ValueError(f"Cleanup debt {debt_id} not found or not retryable")

    def list_pending_cleanup_debts(self) -> list[dict[str, Any]]:
        """List all cleanup debts eligible for processing.

        Includes debts with status 'pending' or 'retryable' whose
        next_retry_at is None or in the past, ordered by created_at.
        """
        now = datetime.now(UTC)
        stmt = (
            sa.select(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.status.in_(["pending", "retryable"]),
                sa.or_(
                    CleanupDebtRecord.next_retry_at.is_(None),
                    CleanupDebtRecord.next_retry_at <= now,
                ),
            )
            .order_by(CleanupDebtRecord.created_at)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "idempotency_key": r.idempotency_key,
                "storage_key": r.storage_key,
                "stale_claim_token": r.stale_claim_token,
                "stale_claim_version": r.stale_claim_version,
                "reclaim_token": r.reclaim_token,
                "reclaim_version": r.reclaim_version,
                "status": r.status,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "retry_count": r.retry_count,
                "last_error": r.last_error,
                "next_retry_at": r.next_retry_at,
                "locked_at": r.locked_at,
                "locked_by": r.locked_by,
            }
            for r in rows
        ]

    def list_eligible_cleanup_debts(
        self,
        *,
        processing_timeout_seconds: int = 600,
    ) -> list[dict[str, Any]]:
        """List cleanup debts eligible for processing or re-claiming.

        Includes:
        - Pending / retryable debts whose next_retry_at is None or in the past.
        - Expired processing debts where lock_expires_at is past.
        - Processing debts without lock_expires_at whose lock is older
          than processing_timeout_seconds.

        Returns dicts sorted by created_at.
        """
        from datetime import timedelta

        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=processing_timeout_seconds)
        stmt = (
            sa.select(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.status.in_(["pending", "retryable", "processing"]),
                sa.or_(
                    # pending/retryable: no retry deadline or deadline passed
                    sa.and_(
                        CleanupDebtRecord.status.in_(["pending", "retryable"]),
                        sa.or_(
                            CleanupDebtRecord.next_retry_at.is_(None),
                            CleanupDebtRecord.next_retry_at <= now,
                        ),
                    ),
                    # processing with lock_expires_at: deadline passed
                    sa.and_(
                        CleanupDebtRecord.status == "processing",
                        CleanupDebtRecord.lock_expires_at.isnot(None),
                        CleanupDebtRecord.lock_expires_at <= now,
                    ),
                    # processing without lock_expires_at: lock older than timeout
                    sa.and_(
                        CleanupDebtRecord.status == "processing",
                        CleanupDebtRecord.lock_expires_at.is_(None),
                        CleanupDebtRecord.locked_at.isnot(None),
                        CleanupDebtRecord.locked_at < cutoff,
                    ),
                ),
            )
            .order_by(CleanupDebtRecord.created_at)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "idempotency_key": r.idempotency_key,
                "storage_key": r.storage_key,
                "stale_claim_token": r.stale_claim_token,
                "stale_claim_version": r.stale_claim_version,
                "reclaim_token": r.reclaim_token,
                "reclaim_version": r.reclaim_version,
                "status": r.status,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "retry_count": r.retry_count,
                "last_error": r.last_error,
                "next_retry_at": r.next_retry_at,
                "locked_at": r.locked_at,
                "locked_by": r.locked_by,
                "lock_expires_at": r.lock_expires_at,
                "claim_version": r.claim_version,
            }
            for r in rows
        ]

    def count_pending_cleanup_debts(self, idempotency_key: str | None = None) -> int:
        """Count cleanup debts eligible for processing.

        Includes 'pending' and 'retryable' (not past deadline) debts.
        """
        now = datetime.now(UTC)
        stmt = (
            sa.select(sa.func.count())
            .select_from(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.status.in_(["pending", "retryable"]),
                sa.or_(
                    CleanupDebtRecord.next_retry_at.is_(None),
                    CleanupDebtRecord.next_retry_at <= now,
                ),
            )
        )
        if idempotency_key is not None:
            stmt = stmt.where(CleanupDebtRecord.idempotency_key == idempotency_key)
        result = self._session.execute(stmt).scalar()
        return result or 0

    def count_eligible_cleanup_debts(
        self,
        *,
        processing_timeout_seconds: int = 600,
    ) -> int:
        """Count cleanup debts eligible for processing or re-claiming.

        Uses the same query conditions as :meth:`list_eligible_cleanup_debts`.
        Includes pending, retryable (not past deadline), and expired processing debts.
        """
        from datetime import timedelta

        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=processing_timeout_seconds)
        stmt = (
            sa.select(sa.func.count())
            .select_from(CleanupDebtRecord)
            .where(
                CleanupDebtRecord.status.in_(["pending", "retryable", "processing"]),
                sa.or_(
                    # pending/retryable: no retry deadline or deadline passed
                    sa.and_(
                        CleanupDebtRecord.status.in_(["pending", "retryable"]),
                        sa.or_(
                            CleanupDebtRecord.next_retry_at.is_(None),
                            CleanupDebtRecord.next_retry_at <= now,
                        ),
                    ),
                    # processing with lock_expires_at: deadline passed
                    sa.and_(
                        CleanupDebtRecord.status == "processing",
                        CleanupDebtRecord.lock_expires_at.isnot(None),
                        CleanupDebtRecord.lock_expires_at <= now,
                    ),
                    # processing without lock_expires_at: lock older than timeout
                    sa.and_(
                        CleanupDebtRecord.status == "processing",
                        CleanupDebtRecord.lock_expires_at.is_(None),
                        CleanupDebtRecord.locked_at.isnot(None),
                        CleanupDebtRecord.locked_at < cutoff,
                    ),
                ),
            )
        )
        result = self._session.execute(stmt).scalar()
        return result or 0

    def insert_audit_log(
        self,
        record_id: str,
        storage_key: str,
        migration_actor: str,
        audit_reason: str,
        result: str,
        *,
        operation: str = "legacy_delete",
        source_hash: str | None = None,
    ) -> None:
        """Insert a MigrationAuditRecord."""
        rec = MigrationAuditRecord(
            id=record_id,
            storage_key=storage_key,
            migration_actor=migration_actor,
            audit_reason=audit_reason,
            operation=operation,
            result=result,
            source_hash=source_hash,
        )
        self._session.add(rec)

    # --- Deletion Outbox ---

    def insert_deletion_outbox(
        self,
        storage_key: str,
        migration_actor: str,
        audit_reason: str,
        operation: str = "legacy_delete",
        source_hash: str | None = None,
    ) -> str:
        """Insert a pending deletion outbox record.

        Returns the outbox ID.
        """
        import uuid as _uuid

        outbox_id = str(_uuid.uuid4())
        rec = DeletionOutboxRecord(
            id=outbox_id,
            storage_key=storage_key,
            migration_actor=migration_actor,
            audit_reason=audit_reason,
            operation=operation,
            source_hash=source_hash,
            status="pending_audit",
        )
        self._session.add(rec)
        return outbox_id

    def update_deletion_outbox_status(self, outbox_id: str, status: str) -> None:
        """Update the status of a deletion outbox record."""
        stmt = (
            sa.update(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.id == outbox_id)
            .values(status=status)
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ValueError(f"Deletion outbox {outbox_id} not found")

    # --- Deletion Receipts ---

    def insert_deletion_receipt(
        self,
        storage_key: str,
        stale_claim_token: str,
        stale_claim_version: int,
        reclaim_token: str,
        reclaim_version: int,
        deletion_hash: str,
        status: str = "deleted",
        deleted_at: datetime | None = None,
    ) -> None:
        """Insert a deletion receipt record.

        If a receipt already exists for this storage_key it is replaced
        (UPSERT semantics) so that re-delete operations overwrite old
        receipts.

        Parameters
        ----------
        status:
            Two-phase protocol status: ``intent``, ``deleted``, or
            ``delete_failed``.  Default ``deleted`` for backward compat.
        deleted_at:
            When the file was actually deleted.  If None, the server
            default (current timestamp) is used in the UPSERT values.
        """
        from datetime import UTC

        dialect = "sqlite"
        if self._session.bind is not None:
            dialect = self._session.bind.dialect.name
        # Determine the correct deleted_at value based on status.
        # - 'intent' and 'delete_failed': deleted_at stays None
        # - 'deleted': default to now if not explicitly provided
        if deleted_at is not None:
            actual_deleted_at: datetime | None = deleted_at
        elif status == "deleted":
            actual_deleted_at = datetime.now(UTC)
        else:
            actual_deleted_at = None

        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_stmt = pg_insert(DeletionReceiptRecord).values(
                storage_key=storage_key,
                stale_claim_token=stale_claim_token,
                stale_claim_version=stale_claim_version,
                reclaim_token=reclaim_token,
                reclaim_version=reclaim_version,
                deletion_hash=deletion_hash,
                status=status,
                deleted_at=actual_deleted_at,
            )
            pg_stmt = pg_stmt.on_conflict_do_update(
                index_elements=["storage_key"],
                set_=dict(
                    stale_claim_token=stale_claim_token,
                    stale_claim_version=stale_claim_version,
                    reclaim_token=reclaim_token,
                    reclaim_version=reclaim_version,
                    deletion_hash=deletion_hash,
                    status=status,
                    deleted_at=actual_deleted_at,
                ),
            )
            self._session.execute(pg_stmt)
        else:
            # SQLite: merge-style upsert
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            sqlite_stmt = sqlite_insert(DeletionReceiptRecord).values(
                storage_key=storage_key,
                stale_claim_token=stale_claim_token,
                stale_claim_version=stale_claim_version,
                reclaim_token=reclaim_token,
                reclaim_version=reclaim_version,
                deletion_hash=deletion_hash,
                status=status,
                deleted_at=actual_deleted_at,
            )
            sqlite_stmt = sqlite_stmt.on_conflict_do_update(
                index_elements=["storage_key"],
                set_=dict(
                    stale_claim_token=stale_claim_token,
                    stale_claim_version=stale_claim_version,
                    reclaim_token=reclaim_token,
                    reclaim_version=reclaim_version,
                    deletion_hash=deletion_hash,
                    status=status,
                    deleted_at=actual_deleted_at,
                ),
            )
            self._session.execute(sqlite_stmt)

    def get_deletion_receipt(self, storage_key: str) -> dict[str, Any] | None:
        """Get a deletion receipt by storage key.

        Returns a dict with keys (stale_claim_token, stale_claim_version,
        reclaim_token, reclaim_version, deletion_hash, deleted_at, status) or None.
        """
        rec = self._session.get(DeletionReceiptRecord, storage_key)
        if rec is None:
            return None
        return {
            "stale_claim_token": rec.stale_claim_token,
            "stale_claim_version": rec.stale_claim_version,
            "reclaim_token": rec.reclaim_token,
            "reclaim_version": rec.reclaim_version,
            "deletion_hash": rec.deletion_hash,
            "deleted_at": rec.deleted_at,
            "status": rec.status,
        }

    _UNSET = object()

    def update_deletion_receipt_status(
        self,
        storage_key: str,
        status: str,
        deleted_at: datetime | None | object = _UNSET,
    ) -> None:
        """Update the status of a deletion receipt record.

        Used by the two-phase reclaim_delete protocol to transition
        from ``intent`` to ``deleted`` or ``delete_failed``.

        Parameters
        ----------
        storage_key:
            The storage key of the receipt.
        status:
            New status (``deleted`` or ``delete_failed``).
        deleted_at:
            If provided (including None), update the deleted_at value.
            If not provided (the sentinel default), deleted_at is not changed.
            Pass ``deleted_at=None`` to explicitly clear the timestamp
            (e.g. when transitioning to ``delete_failed`` after a prior
            successful deletion that was retried).
        """
        values: dict[str, Any] = {"status": status}
        if deleted_at is not self._UNSET:
            values["deleted_at"] = deleted_at
        stmt = (
            sa.update(DeletionReceiptRecord)
            .where(DeletionReceiptRecord.storage_key == storage_key)
            .values(**values)
        )
        result = self._session.execute(stmt)
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Deletion receipt not found: {storage_key}")

    # --- Deletion Outbox CAS claim methods (0025) ---

    def claim_deletion_outbox(
        self,
        outbox_id: str,
        *,
        claimant_token: str,
        now: datetime,
        lease_seconds: int,
        observed_status: str,
        observed_claim_version: int,
    ) -> bool:
        """CAS claim a deletion outbox for processing.

        CAS conditions: ``id == outbox_id``, ``status == observed_status``,
        ``claim_version == observed_claim_version``, plus eligibility:

        - If observed status is ``pending_audit`` or ``delete_failed``,
          the outbox is immediately eligible.
        - If observed status is ``deleting``, the lock must be expired
          (``lock_expires_at <= now`` and ``lock_expires_at IS NOT NULL``).

        On success:
        - status = 'deleting'
        - claim_token = claimant_token
        - claim_version = claim_version + 1
        - locked_at = now
        - lock_expires_at = now + lease_seconds

        Returns True if the outbox was successfully claimed.
        """
        from datetime import timedelta

        eligible = sa.or_(
            DeletionOutboxRecord.status.in_(["pending_audit", "delete_failed"]),
            sa.and_(
                DeletionOutboxRecord.status == "deleting",
                DeletionOutboxRecord.lock_expires_at.isnot(None),
                DeletionOutboxRecord.lock_expires_at <= now,
            ),
        )

        stmt = (
            sa.update(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.id == outbox_id)
            .where(DeletionOutboxRecord.status == observed_status)
            .where(DeletionOutboxRecord.claim_version == observed_claim_version)
            .where(eligible)
            .values(
                status="deleting",
                claim_token=claimant_token,
                claim_version=DeletionOutboxRecord.claim_version + 1,
                locked_at=now,
                lock_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        result = self._session.execute(stmt)
        return bool(result.rowcount == 1)  # type: ignore[attr-defined]

    def complete_deletion_outbox(
        self,
        outbox_id: str,
        *,
        claim_token: str,
        claim_version: int,
    ) -> None:
        """Complete a deletion outbox (CAS: status='deleting', claim matches).

        Updates status to 'audited' and clears claim fields.

        Raises ValueError if no matching outbox found.
        """
        stmt = (
            sa.update(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.id == outbox_id)
            .where(DeletionOutboxRecord.status == "deleting")
            .where(DeletionOutboxRecord.claim_token == claim_token)
            .where(DeletionOutboxRecord.claim_version == claim_version)
            .values(
                status="audited",
                claim_token=None,
                locked_at=None,
                lock_expires_at=None,
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ValueError(f"Deletion outbox {outbox_id} not found or claim mismatch")

    def fail_deletion_outbox(
        self,
        outbox_id: str,
        *,
        claim_token: str,
        claim_version: int,
        error: str,
    ) -> None:
        """Fail a deletion outbox (CAS: status='deleting', claim matches).

        Updates status to 'delete_failed', increments retry_count,
        sets last_error, and clears claim fields.

        Raises ValueError if no matching outbox found.
        """
        stmt = (
            sa.update(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.id == outbox_id)
            .where(DeletionOutboxRecord.status == "deleting")
            .where(DeletionOutboxRecord.claim_token == claim_token)
            .where(DeletionOutboxRecord.claim_version == claim_version)
            .values(
                status="delete_failed",
                retry_count=DeletionOutboxRecord.retry_count + 1,
                last_error=error,
                claim_token=None,
                locked_at=None,
                lock_expires_at=None,
            )
        )
        result = self._session.execute(stmt)
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise ValueError(f"Deletion outbox {outbox_id} not found or claim mismatch")

    # --- Deletion Outbox listing ---

    def list_deletion_outboxes_by_status(self, status: str) -> list[dict[str, Any]]:
        """List deletion outbox records with the given status.

        Returns a list of dicts with keys (id, storage_key, migration_actor,
        audit_reason, operation, source_hash, status, retry_count, created_at).
        """
        stmt = (
            sa.select(DeletionOutboxRecord)
            .where(DeletionOutboxRecord.status == status)
            .order_by(DeletionOutboxRecord.created_at)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "storage_key": r.storage_key,
                "migration_actor": r.migration_actor,
                "audit_reason": r.audit_reason,
                "operation": r.operation,
                "source_hash": r.source_hash,
                "status": r.status,
                "retry_count": r.retry_count,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    def list_eligible_outboxes(
        self,
        processing_timeout_seconds: int = 600,
    ) -> list[dict[str, Any]]:
        """List outboxes eligible for processing.

        Returns outboxes where:
        - status IN ('pending_audit', 'delete_failed'), OR
        - status = 'deleting' AND lock_expires_at <= now (expired lease)

        Includes claim fields (claim_token, claim_version, locked_at,
        lock_expires_at) in the returned dicts.
        """
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        stmt = (
            sa.select(DeletionOutboxRecord)
            .where(
                sa.or_(
                    DeletionOutboxRecord.status.in_(["pending_audit", "delete_failed"]),
                    sa.and_(
                        DeletionOutboxRecord.status == "deleting",
                        DeletionOutboxRecord.lock_expires_at <= now,
                    ),
                )
            )
            .order_by(DeletionOutboxRecord.created_at)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "storage_key": r.storage_key,
                "migration_actor": r.migration_actor,
                "audit_reason": r.audit_reason,
                "operation": r.operation,
                "source_hash": r.source_hash,
                "status": r.status,
                "retry_count": r.retry_count,
                "created_at": r.created_at,
                "claim_token": r.claim_token,
                "claim_version": r.claim_version,
                "locked_at": r.locked_at,
                "lock_expires_at": r.lock_expires_at,
            }
            for r in rows
        ]

    # --- Commit ---
