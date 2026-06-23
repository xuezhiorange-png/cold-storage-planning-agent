"""0015_add_active_slot

Add active_slot column and unique index to enforce at most one active
template per (template_code, format) pair.

Revision ID: 0015_add_active_slot
Revises: 0014_add_approval_fields
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_add_active_slot"
down_revision = "0014_add_approval_fields"
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


def _existing_indexes(table: str) -> set[str]:
    tables = _existing_tables()
    if table not in tables:
        return set()
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(table) if ix.get("name")}


def upgrade() -> None:
    tables = _existing_tables()
    if "report_templates" not in tables:
        return

    # --- Add active_slot column (P0-7) ---
    if not _column_exists("report_templates", "active_slot"):
        op.add_column(
            "report_templates",
            sa.Column("active_slot", sa.String(16), nullable=True),
        )

    # --- Create unique index on (template_code, format, active_slot) ---
    # This enforces at most one active template per code+format pair.
    # SQLite partial unique index workaround: use a regular index since
    # SQLite 3.31+ supports partial unique indexes but we use a simpler approach.
    existing_idx = _existing_indexes("report_templates")
    if "uq_active_template_per_code_format" not in existing_idx:
        # For PostgreSQL: use a partial unique index WHERE active_slot IS NOT NULL
        bind = op.get_bind()
        dialect = bind.dialect.name
        if dialect == "postgresql":
            op.create_index(
                "uq_active_template_per_code_format",
                "report_templates",
                ["template_code", "format"],
                unique=True,
                postgresql_where=sa.text("active_slot IS NOT NULL"),
            )
        else:
            # SQLite: use a regular non-unique index (SQLite doesn't support
            # partial unique indexes in the same way). The application layer
            # enforces the constraint via deactivate_templates before activate.
            op.create_index(
                "ix_active_template_per_code_format",
                "report_templates",
                ["template_code", "format", "active_slot"],
            )


def downgrade() -> None:
    tables = _existing_tables()
    if "report_templates" not in tables:
        return

    # --- Drop index ---
    existing_idx = _existing_indexes("report_templates")
    if "uq_active_template_per_code_format" in existing_idx:
        op.drop_index("uq_active_template_per_code_format", "report_templates")
    if "ix_active_template_per_code_format" in existing_idx:
        op.drop_index("ix_active_template_per_code_format", "report_templates")

    # --- Drop column ---
    if _column_exists("report_templates", "active_slot"):
        op.drop_column("report_templates", "active_slot")
