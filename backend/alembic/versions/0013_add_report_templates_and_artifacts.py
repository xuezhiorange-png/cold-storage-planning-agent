"""0013_add_report_templates_and_artifacts

Create report_templates and report_export_artifacts tables for
template versioning and export artifact tracking (Task 9B).

Revision ID: 0013_add_templates_artifacts
Revises: 0012_add_scheme_content_hash
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0013_add_templates_artifacts"
down_revision = "0012_add_scheme_content_hash"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set[str]:
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(table) if ix.get("name")}


def upgrade() -> None:
    tables = _existing_tables()

    # --- report_templates ---
    if "report_templates" not in tables:
        op.create_table(
            "report_templates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("template_code", sa.String(64), nullable=False),
            sa.Column("report_type", sa.String(64), nullable=False),
            sa.Column("format", sa.String(16), nullable=False),
            sa.Column("version", sa.String(32), nullable=False),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
            sa.Column("schema_version", sa.String(64), nullable=False),
            sa.Column(
                "locale",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'zh-CN'"),
            ),
            sa.Column(
                "manifest_json",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=False,
            ),
            sa.Column(
                "template_content_hash",
                sa.String(64),
                nullable=False,
                server_default=sa.text("''"),
            ),
            sa.Column("created_by", sa.String(64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "template_code",
                "version",
                "format",
                name="uq_template_code_version_format",
            ),
        )

    # --- report_export_artifacts ---
    if "report_export_artifacts" not in tables:
        op.create_table(
            "report_export_artifacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "report_id",
                sa.String(36),
                sa.ForeignKey("reports.id"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "report_revision_id",
                sa.String(36),
                sa.ForeignKey("report_revisions.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("revision_number", sa.Integer, nullable=False),
            sa.Column("format", sa.String(16), nullable=False),
            sa.Column(
                "template_id",
                sa.String(36),
                sa.ForeignKey("report_templates.id"),
                nullable=False,
            ),
            sa.Column("template_version", sa.String(32), nullable=False),
            sa.Column("schema_version", sa.String(64), nullable=False),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column(
                "storage_key",
                sa.String(256),
                nullable=False,
                server_default=sa.text("''"),
            ),
            sa.Column("file_name", sa.String(256), nullable=False),
            sa.Column("mime_type", sa.String(64), nullable=False),
            sa.Column(
                "file_size_bytes",
                sa.Integer,
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "file_sha256",
                sa.String(64),
                nullable=False,
                server_default=sa.text("''"),
            ),
            sa.Column("source_content_hash", sa.String(64), nullable=False),
            sa.Column(
                "render_manifest_json",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=False,
            ),
            sa.Column("generated_by", sa.String(64), nullable=False),
            sa.Column(
                "generated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "failure_code",
                sa.String(64),
                nullable=False,
                server_default=sa.text("''"),
            ),
            sa.Column(
                "failure_message",
                sa.Text,
                nullable=False,
                server_default=sa.text("''"),
            ),
        )

    # --- indexes on report_export_artifacts ---
    # report_id and report_revision_id indexes are created automatically
    # by ORM index=True in the table definition above.
    if "report_export_artifacts" in tables:
        existing_idx = _existing_indexes("report_export_artifacts")
    else:
        existing_idx = set()

    for idx_name in (
        "ix_report_export_artifacts_status",
        "ix_report_export_artifacts_format",
        "ix_report_export_artifacts_source_content_hash",
    ):
        if idx_name not in existing_idx:
            col = idx_name.replace("ix_report_export_artifacts_", "")
            op.create_index(idx_name, "report_export_artifacts", [col])


def downgrade() -> None:
    tables = _existing_tables()
    if "report_export_artifacts" in tables:
        op.drop_table("report_export_artifacts")
    if "report_templates" in tables:
        op.drop_table("report_templates")
