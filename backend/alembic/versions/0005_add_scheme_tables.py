"""Add scheme tables — weight_sets, runs, candidates.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_add_scheme_tables"
down_revision = "0004_add_coefficient_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheme_weight_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer, server_default="1"),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("source_type", sa.String(50), server_default="system"),
        sa.Column("criteria", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("requires_review", sa.Boolean, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code", "revision", name="uq_weight_set_code_revision"),
    )

    op.create_table(
        "scheme_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "project_version_id",
            sa.String(36),
            sa.ForeignKey("project_versions.id"),
            nullable=False,
        ),
        sa.Column("weight_set_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("generator_version", sa.String(50), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(128), nullable=False),
        sa.Column("input_snapshot", sa.JSON, server_default="{}"),
        sa.Column("assumption_snapshot", sa.JSON, server_default="{}"),
        sa.Column("comparison_snapshot", sa.JSON, server_default="{}"),
        sa.Column("candidates_snapshot", sa.JSON, server_default="{}"),
        sa.Column("requires_review", sa.Boolean, server_default="1"),
        sa.Column("recommended_scheme_code", sa.String(120), nullable=True),
        sa.Column("warning_messages", sa.JSON, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "scheme_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scheme_run_id", sa.String(36), sa.ForeignKey("scheme_runs.id"), nullable=False),
        sa.Column("scheme_code", sa.String(120), nullable=False),
        sa.Column("profile_code", sa.String(120), nullable=False),
        sa.Column("feasible", sa.Boolean, server_default="1"),
        sa.Column("rank", sa.Integer, nullable=True),
        sa.Column("total_score", sa.Float, nullable=True),
        sa.Column("result_snapshot", sa.JSON, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("scheme_run_id", "scheme_code", name="uq_run_scheme"),
    )


def downgrade() -> None:
    op.drop_table("scheme_candidates")
    op.drop_table("scheme_runs")
    op.drop_table("scheme_weight_sets")
