"""0009_add_reports

Revision ID: 0009_add_reports
Revises: 0008_add_planning_agent
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_add_reports"
down_revision = "0008_add_planning_agent"
branch_labels = None
depends_on = None


def _json_column_type() -> sa.types.TypeEngine:
    """Return JSONB for PostgreSQL, JSON for SQLite."""
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    json_type = _json_column_type()

    # reports
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("project_version_id", sa.String(36), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column(
            "current_revision_number", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_reports_project_id", "reports", ["project_id"])
    op.create_index("ix_reports_project_version_id", "reports", ["project_version_id"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_version", "reports", ["version"])

    # report_revisions
    op.create_table(
        "report_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column("revision_number", sa.Integer, nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("content_json", json_type, nullable=False),
        sa.Column("canonical_content_json", json_type, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("quality_status", sa.String(32), nullable=False),
        sa.Column("quality_findings_json", json_type, nullable=False),
        sa.Column("generated_by", sa.String(64), nullable=False),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "supersedes_revision_id",
            sa.String(36),
            sa.ForeignKey("report_revisions.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "report_id", "revision_number", name="uq_report_revisions_report_revision"
        ),
    )
    op.create_index("ix_report_revisions_report_id", "report_revisions", ["report_id"])
    op.create_index("ix_report_revisions_content_hash", "report_revisions", ["content_hash"])

    # report_source_references
    op.create_table(
        "report_source_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "report_revision_id",
            sa.String(36),
            sa.ForeignKey("report_revisions.id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("source_revision", sa.String(64), nullable=False, server_default=""),
        sa.Column("section_key", sa.String(128), nullable=False),
        sa.Column("field_path", sa.String(256), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("tool_version", sa.String(32), nullable=False, server_default=""),
        sa.Column("result_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_report_source_references_revision_id",
        "report_source_references",
        ["report_revision_id"],
    )
    op.create_index(
        "ix_report_source_references_section_key", "report_source_references", ["section_key"]
    )

    # report_review_actions
    op.create_table(
        "report_review_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reports.id"), nullable=False),
        sa.Column(
            "report_revision_id",
            sa.String(36),
            sa.ForeignKey("report_revisions.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("comment", sa.Text, nullable=False, server_default=""),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_report_review_actions_report_id", "report_review_actions", ["report_id"])


def downgrade() -> None:
    op.drop_table("report_review_actions")
    op.drop_table("report_source_references")
    op.drop_table("report_revisions")
    op.drop_table("reports")
