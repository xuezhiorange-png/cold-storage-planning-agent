"""0041: workbench five-stage idempotency records.

Revision ID: 0041_workbench_five_stage_idempotency
Revises: 0040_add_knowledge_page_evidence
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0041_workbench_five_stage_idempotency"
down_revision: str | Sequence[str] | None = "0040_add_knowledge_page_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "workbench_five_stage_idempotency",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("database_backend", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "project_version_id",
            sa.String(36),
            sa.ForeignKey("project_versions.id"),
            nullable=False,
        ),
        sa.Column("bundle_hash", sa.String(128), nullable=False),
        sa.Column("source_binding_id", sa.String(36), nullable=False),
        sa.Column("outcome_payload", _json_type(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "database_backend",
            "idempotency_key",
            name="uq_workbench_five_stage_idempotency_db_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("workbench_five_stage_idempotency")
