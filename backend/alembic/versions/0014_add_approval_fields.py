"""0014_add_approval_fields

Add approval binding fields to reports table.

Revision ID: 0014_add_approval_fields
Revises: 0013_add_templates_artifacts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_add_approval_fields"
down_revision = "0013_add_templates_artifacts"
branch_labels = None
depends_on = None


def _existing_tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    tables = _existing_tables()
    if "reports" not in tables:
        return
    existing_cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("reports")}
    if "approved_revision_id" not in existing_cols:
        op.add_column("reports", sa.Column("approved_revision_id", sa.String(36), nullable=True))
    if "approved_content_hash" not in existing_cols:
        op.add_column("reports", sa.Column("approved_content_hash", sa.String(64), nullable=True))
    if "approved_by" not in existing_cols:
        op.add_column("reports", sa.Column("approved_by", sa.String(64), nullable=True))
    if "approved_at" not in existing_cols:
        op.add_column("reports", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    # Add FK constraint
    try:
        op.create_foreign_key(
            "fk_reports_approved_revision",
            "reports",
            "report_revisions",
            ["approved_revision_id"],
            ["id"],
        )
    except Exception:
        pass  # FK may already exist


def downgrade():
    try:
        op.drop_constraint("fk_reports_approved_revision", "reports", type_="foreignkey")
    except Exception:
        pass
    op.drop_column("reports", "approved_at")
    op.drop_column("reports", "approved_by")
    op.drop_column("reports", "approved_content_hash")
    op.drop_column("reports", "approved_revision_id")
