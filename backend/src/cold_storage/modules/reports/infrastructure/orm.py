"""SQLAlchemy ORM models for report persistence.

PostgreSQL uses JSONB; SQLite falls back to JSON text.

JSON columns use ``Any`` because SQLAlchemy ORM enforces untyped ``Mapped``
for JSON/JSONB columns.  Domain layer defines ``JsonObject``/``JsonValue``
aliases for semantic clarity; ORM layer keeps ``Any`` for SQLAlchemy
compatibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _json_column(name: str, nullable: bool = True) -> Mapped[Any]:
    """JSON/JSONB column that works on both SQLite and PostgreSQL."""
    return mapped_column(sa.JSON().with_variant(JSONB(), "postgresql"), nullable=nullable)


class ReportRecord(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, index=True)
    project_version_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="draft", index=True
    )
    current_revision_number: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    created_by: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1"), index=True
    )
    # P0-8: Formal approval binding fields
    approved_revision_id: Mapped[str | None] = mapped_column(
        sa.String(36), sa.ForeignKey("report_revisions.id"), nullable=True
    )
    approved_content_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class ReportRevisionRecord(Base):
    __tablename__ = "report_revisions"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("reports.id"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    content_json: Mapped[Any] = _json_column("content_json", nullable=False)
    canonical_content_json: Mapped[Any] = _json_column("canonical_content_json", nullable=False)
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    quality_status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    quality_findings_json: Mapped[Any] = _json_column("quality_findings_json", nullable=False)
    generated_by: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    generated_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    supersedes_revision_id: Mapped[str | None] = mapped_column(
        sa.String(36), sa.ForeignKey("report_revisions.id"), nullable=True
    )


class ReportSourceReferenceRecord(Base):
    __tablename__ = "report_source_references"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    report_revision_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("report_revisions.id"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    source_revision: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")
    section_key: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    field_path: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    tool_name: Mapped[str] = mapped_column(sa.String(128), nullable=False, server_default="")
    tool_version: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="")
    result_id: Mapped[str] = mapped_column(sa.String(36), nullable=False, server_default="")
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(sa.String(128), primary_key=True)
    actor: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="claimed")
    result_payload: Mapped[Any] = _json_column("result_payload", nullable=True)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    claim_token: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    claim_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )


class ReportReviewActionRecord(Base):
    __tablename__ = "report_review_actions"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("reports.id"), nullable=False, index=True
    )
    report_revision_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("report_revisions.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    actor: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    comment: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="")
    from_status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


class ReportTemplateRecord(Base):
    __tablename__ = "report_templates"
    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    template_code: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    report_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    format: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'draft'")
    )
    schema_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    locale: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'zh-CN'")
    )
    manifest_json: Mapped[Any] = _json_column("manifest_json", nullable=False)
    template_content_hash: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default=sa.text("''")
    )
    created_by: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    activated_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # P0-7: Active slot marker — 'active' for the current active template, NULL otherwise.
    # Combined with unique index on (template_code, format, active_slot) to enforce
    # at most one active template per code+format pair.
    active_slot: Mapped[str | None] = mapped_column(sa.String(16), nullable=True, index=True)
    __table_args__ = (
        sa.UniqueConstraint(
            "template_code",
            "version",
            "format",
            "locale",
            name="uq_template_code_version_format_locale",
        ),
        sa.Index(
            "uq_active_template_per_code_format_locale",
            "template_code",
            "format",
            "locale",
            unique=True,
            sqlite_where=sa.text("active_slot IS NOT NULL"),
            postgresql_where=sa.text("active_slot IS NOT NULL"),
        ),
        sa.CheckConstraint(
            "locale IN ('zh-CN', 'en-US')",
            name="ck_report_template_locale_supported",
        ),
    )


class ReportExportArtifactRecord(Base):
    __tablename__ = "report_export_artifacts"
    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("reports.id"), nullable=False, index=True
    )
    report_revision_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("report_revisions.id"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    format: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    template_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("report_templates.id"), nullable=False
    )
    template_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'pending'")
    )
    storage_key: Mapped[str] = mapped_column(
        sa.String(256), nullable=False, server_default=sa.text("''")
    )
    file_name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        sa.String(255), nullable=False
    )  # PR67 P1-4: widened from VARCHAR(64) to VARCHAR(255) to persist the
    # standard DOCX MIME (``application/vnd.openxmlformats-officedocument
    # .wordprocessingml.document``, 71 chars) without truncation. The
    # authoritative widening lives in migration 0039; both must change
    # together (ORM + Alembic) per the project's "database schema
    # changes must go through Alembic" rule in AGENTS.md.
    file_size_bytes: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    file_sha256: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default=sa.text("''")
    )
    source_content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    render_manifest_json: Mapped[Any] = _json_column("render_manifest_json", nullable=False)
    generated_by: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    generated_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    failure_code: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default=sa.text("''")
    )
    failure_message: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default=sa.text("''")
    )
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(128), nullable=True, index=True)
    claim_token: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    claim_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    locale: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'zh-CN'"), index=True
    )
    translation_catalog_version: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default=sa.text("'1.0.0'")
    )
    localized_template_content_hash: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default=sa.text("''")
    )
    template_locale: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'zh-CN'")
    )
    translation_catalog_content_hash: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, server_default=sa.text("''")
    )

    __table_args__ = (
        sa.CheckConstraint(
            "locale IN ('zh-CN', 'en-US')",
            name="ck_report_artifact_locale_supported",
        ),
        sa.CheckConstraint(
            "template_locale IN ('zh-CN', 'en-US')",
            name="ck_report_artifact_template_locale_supported",
        ),
    )


class CleanupDebtRecord(Base):
    """Records a pending file-deletion task for the two-phase cleanup pattern.

    When a stale claim is recovered, the old owner's artifact files are not
    deleted immediately.  Instead, a ``CleanupDebtRecord`` is inserted in
    the same DB transaction that CAS-reclaims the idempotency record and
    fails the old artifacts.  After the transaction commits, a cleanup
    executor reads pending debts and performs the physical file deletions
    with ``reclaim_delete`` fencing.

    This ensures that a crash between the DB commit and the file deletion
    does not orphan files — the pending debt survives and can be retried.
    """

    __tablename__ = "cleanup_debt"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    stale_claim_token: Mapped[str] = mapped_column(sa.String(36), nullable=False, server_default="")
    stale_claim_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    reclaim_token: Mapped[str] = mapped_column(sa.String(36), nullable=False, server_default="")
    reclaim_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'pending'"), index=True
    )
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    completed_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    last_error: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    next_retry_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    locked_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str] = mapped_column(
        sa.String(128), nullable=False, server_default=sa.text("''")
    )
    lock_expires_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    claim_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )


class MigrationAuditRecord(Base):
    """Persistent audit log for privileged migration/cleanup operations.

    Records every call to ``delete_legacy_artifact()`` and similar
    privileged operations so there is a durable trail of who deleted
    what, when, and why.
    """

    __tablename__ = "migration_audit_log"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    storage_key: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    migration_actor: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    audit_reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    operation: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default=sa.text("'legacy_delete'")
    )
    result: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


class DeletionOutboxRecord(Base):
    """Transactional outbox for legacy artifact deletion audit.

    Used by ``delete_legacy_artifact()`` to guarantee that the audit
    record is committed to the database BEFORE the file is deleted.
    If the file deletion fails the outbox status is updated to
    ``delete_failed`` so operators can investigate.

    ``retry_count`` tracks the number of retry attempts made during
    startup recovery (see ``recover_pending_outboxes()``).
    """

    __tablename__ = "deletion_outbox"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    storage_key: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    migration_actor: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    audit_reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    operation: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default=sa.text("'legacy_delete'")
    )
    source_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'pending_audit'")
    )
    retry_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # Claim/lease fields for CAS-based outbox claiming (0025)
    claim_token: Mapped[str | None] = mapped_column(sa.String(36), nullable=True)
    claim_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    locked_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    lock_expires_at: Mapped[str | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class DeletionReceiptRecord(Base):
    """Persistent receipt that a reclaim_delete operation completed.

    Records the claim identifiers that were used to delete a file so
    that a subsequent ``reclaim_delete`` with ``missing_is_success=True``
    can verify that the file was in fact deleted by the same owner,
    preventing unauthorised ``already_missing`` responses.

    ``status`` tracks the two-phase protocol: ``intent`` (receipt
    committed, deletion pending), ``deleted`` (file removed), or
    ``delete_failed`` (deletion failed after intent).
    """

    __tablename__ = "deletion_receipts"

    storage_key: Mapped[str] = mapped_column(sa.String(256), primary_key=True)
    stale_claim_token: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    stale_claim_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    reclaim_token: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    reclaim_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'intent'")
    )
    deleted_at: Mapped[str] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    deletion_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
