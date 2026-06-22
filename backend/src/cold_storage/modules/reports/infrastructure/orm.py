"""SQLAlchemy ORM models for report persistence.

PostgreSQL uses JSONB; SQLite falls back to JSON text.
"""

from __future__ import annotations

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
        sa.String(36), sa.ForeignKey("reports.id"), nullable=True
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
