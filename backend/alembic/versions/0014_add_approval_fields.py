"""0014_add_approval_fields

Add approval binding fields to reports table.

Idempotent: safe to re-run on databases that already have the columns,
constraints, or indexes.  Handles both upgrade and downgrade cleanly.

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


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_columns(table: str) -> set[str]:
    """Return the set of column names for *table*, or empty set if table missing."""
    tables = _existing_tables()
    if table not in tables:
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _column_exists(table: str, column: str) -> bool:
    return column in _existing_columns(table)


def upgrade() -> None:
    """Idempotent upgrade — safe to run multiple times."""
    tables = _existing_tables()
    if "reports" not in tables:
        return

    # --- Columns (idempotent: skip if already exists) ---
    if not _column_exists("reports", "approved_revision_id"):
        op.add_column(
            "reports",
            sa.Column("approved_revision_id", sa.String(36), nullable=True),
        )
    if not _column_exists("reports", "approved_content_hash"):
        op.add_column(
            "reports",
            sa.Column("approved_content_hash", sa.String(64), nullable=True),
        )
    if not _column_exists("reports", "approved_by"):
        op.add_column(
            "reports",
            sa.Column("approved_by", sa.String(64), nullable=True),
        )
    if not _column_exists("reports", "approved_at"):
        op.add_column(
            "reports",
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        )

    # --- Foreign key constraint (idempotent) ---
    bind = op.get_bind()
    dialect = bind.dialect.name
    existing_fks = sa.inspect(bind).get_foreign_keys("reports")
    fk_names = {fk.get("name") for fk in existing_fks}

    if (
        "fk_reports_approved_revision" not in fk_names
        and "report_revisions" in tables
        and "id" in _existing_columns("report_revisions")
    ):
        if dialect == "sqlite":
            # SQLite: use batch_alter_table to add FK safely
            with op.batch_alter_table("reports") as batch_op:
                batch_op.create_foreign_key(
                    "fk_reports_approved_revision",
                    "report_revisions",
                    ["approved_revision_id"],
                    ["id"],
                )
        else:
            op.create_foreign_key(
                "fk_reports_approved_revision",
                "reports",
                "report_revisions",
                ["approved_revision_id"],
                ["id"],
            )


def downgrade() -> None:
    """Idempotent downgrade — safe to run multiple times."""
    tables = _existing_tables()
    if "reports" not in tables:
        return

    # --- Foreign key constraint (idempotent) ---
    bind = op.get_bind()
    dialect = bind.dialect.name
    existing_fks = sa.inspect(bind).get_foreign_keys("reports")
    fk_names = {fk.get("name") for fk in existing_fks}

    if "fk_reports_approved_revision" in fk_names:
        if dialect == "sqlite":
            with op.batch_alter_table("reports") as batch_op:
                batch_op.drop_constraint(
                    "fk_reports_approved_revision",
                    type_="foreignkey",
                )
        else:
            op.drop_constraint(
                "fk_reports_approved_revision",
                "reports",
                type_="foreignkey",
            )

    # --- Columns (idempotent: skip if not exists) ---
    if _column_exists("reports", "approved_at"):
        op.drop_column("reports", "approved_at")
    if _column_exists("reports", "approved_by"):
        op.drop_column("reports", "approved_by")
    if _column_exists("reports", "approved_content_hash"):
        op.drop_column("reports", "approved_content_hash")
    if _column_exists("reports", "approved_revision_id"):
        op.drop_column("reports", "approved_revision_id")
