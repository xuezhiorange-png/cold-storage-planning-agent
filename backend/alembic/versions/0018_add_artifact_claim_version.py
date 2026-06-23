"""0018_add_artifact_claim_version

Add claim_version column to report_export_artifacts for atomic fencing.

Revision ID: 0018_add_artifact_claim_version
Revises: 0017_add_claim_fencing
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018_add_artifact_claim_version"
down_revision = "0017_add_claim_fencing"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    try:
        return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    cols = _existing_columns("report_export_artifacts")
    if "claim_version" not in cols:
        op.add_column(
            "report_export_artifacts",
            sa.Column("claim_version", sa.Integer, nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    cols = _existing_columns("report_export_artifacts")
    if "claim_version" in cols:
        op.drop_column("report_export_artifacts", "claim_version")
