"""0011_fix_supersedes_fk

Revision ID: 0011_fix_supersedes_fk
Revises: 0010_add_idempotency_record
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_fix_supersedes_fk"
down_revision = "0010_add_idempotency_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        # Find the actual constraint name dynamically
        conn = op.get_bind()
        result = conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'report_revisions'::regclass "
                "AND contype = 'f' "
                "AND pg_get_constraintdef(oid) LIKE '%supersedes_revision_id%'"
            )
        )
        row = result.fetchone()
        if row is not None:
            old_name = row[0]
            op.drop_constraint(old_name, "report_revisions", type_="foreignkey")
            op.create_foreign_key(
                "fk_report_revisions_supersedes_revision_id_report_revisions",
                "report_revisions",
                "report_revisions",
                ["supersedes_revision_id"],
                ["id"],
            )
    else:
        # SQLite: batch_alter_table recreates the table.
        # SQLite doesn't enforce FK constraints at the DB level,
        # so we just need the ORM metadata to be correct.
        # Use batch_alter_table with explicit column type to trigger
        # table recreation with the correct FK definition.
        with op.batch_alter_table("report_revisions") as batch_op:
            batch_op.alter_column(
                "supersedes_revision_id",
                type_=sa.String(36),
                nullable=True,
            )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.drop_constraint(
            "fk_report_revisions_supersedes_revision_id_report_revisions",
            "report_revisions",
            type_="foreignkey",
        )
        op.create_foreign_key(
            "fk_report_revisions_supersedes_revision_id_reports",
            "report_revisions",
            "reports",
            ["supersedes_revision_id"],
            ["id"],
        )
    else:
        with op.batch_alter_table("report_revisions") as batch_op:
            batch_op.alter_column(
                "supersedes_revision_id",
                type_=sa.String(36),
                nullable=True,
            )
