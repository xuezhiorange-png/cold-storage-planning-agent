"""add version metadata and state machine columns

Revision ID: 0003_add_version_metadata
Revises: 0002_add_calculation_runs
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_version_metadata"
down_revision: str | None = "0002_add_calculation_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valid version statuses for the check constraint
_VALID_STATUSES = "'draft', 'generated', 'under_review', 'reviewed', 'approved', 'archived'"


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # Add new columns to project_versions (all have server defaults or are nullable)
    op.add_column(
        "project_versions",
        sa.Column(
            "calculation_snapshot",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "project_versions",
        sa.Column(
            "assumption_snapshot",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "project_versions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "project_versions",
        sa.Column("parent_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "project_versions",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_versions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_versions",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_versions",
        sa.Column("approved_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "project_versions",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Foreign key: parent_version_id -> project_versions.id
    # SQLite does not support ALTER TABLE to add foreign keys.
    # Use batch mode (copy-and-move) for SQLite; direct for PostgreSQL.
    if dialect == "sqlite":
        with op.batch_alter_table("project_versions") as batch_op:
            batch_op.create_foreign_key(
                "fk_version_parent",
                "project_versions",
                ["parent_version_id"],
                ["id"],
            )
    else:
        op.create_foreign_key(
            "fk_version_parent",
            "project_versions",
            "project_versions",
            ["parent_version_id"],
            ["id"],
        )

    # Check constraint for valid status values
    if dialect == "sqlite":
        with op.batch_alter_table("project_versions") as batch_op:
            batch_op.create_check_constraint(
                "ck_project_version_status",
                sa.text(f"status IN ({_VALID_STATUSES})"),
            )
    else:
        op.create_check_constraint(
            "ck_project_version_status",
            "project_versions",
            sa.text(f"status IN ({_VALID_STATUSES})"),
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("project_versions") as batch_op:
            batch_op.drop_constraint("ck_project_version_status", type_="check")
            batch_op.drop_constraint("fk_version_parent", type_="foreignkey")
    else:
        op.drop_constraint("ck_project_version_status", "project_versions", type_="check")
        op.drop_constraint("fk_version_parent", "project_versions", type_="foreignkey")

    op.drop_column("project_versions", "archived_at")
    op.drop_column("project_versions", "approved_by")
    op.drop_column("project_versions", "approved_at")
    op.drop_column("project_versions", "reviewed_at")
    op.drop_column("project_versions", "submitted_at")
    op.drop_column("project_versions", "parent_version_id")
    op.drop_column("project_versions", "updated_at")
    op.drop_column("project_versions", "assumption_snapshot")
    op.drop_column("project_versions", "calculation_snapshot")
