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
            name="uq_template_code_version_format",
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
    mime_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
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
