"""Add score breakdown and constraint columns, fix total_score type.

Revision ID: 0006_add_scheme_candidate_details
Revises: 0005_add_scheme_tables
Create Date: 2026-06-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_add_scheme_candidate_details"
down_revision = "0005_add_scheme_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add score_breakdown_snapshot column
    op.add_column(
        "scheme_candidates",
        sa.Column("score_breakdown_snapshot", sa.JSON, server_default="{}"),
    )

    # Add constraint_results column
    op.add_column(
        "scheme_candidates",
        sa.Column("constraint_results", sa.JSON, server_default="[]"),
    )

    # Fix total_score: drop Float, add Numeric(12,3)
    # SQLite doesn't support ALTER COLUMN type, so we recreate the table
    # For PostgreSQL we could use ALTER COLUMN, but we use a safe approach
    with op.batch_alter_table("scheme_candidates") as batch_op:
        batch_op.alter_column(
            "total_score",
            type_=sa.Numeric(12, 3),
            existing_type=sa.Float,
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("scheme_candidates") as batch_op:
        batch_op.alter_column(
            "total_score",
            type_=sa.Float,
            existing_type=sa.Numeric(12, 3),
            nullable=True,
        )
    op.drop_column("scheme_candidates", "constraint_results")
    op.drop_column("scheme_candidates", "score_breakdown_snapshot")
