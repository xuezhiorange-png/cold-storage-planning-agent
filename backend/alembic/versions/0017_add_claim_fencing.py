"""0017_add_claim_fencing

Add fencing tokens for claim-based idempotency.

Revision ID: 0017_add_claim_fencing
Revises: 0016_add_claimed_at
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0017_add_claim_fencing"
down_revision = "0016_add_claimed_at"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    """Return the set of column names for *table*, or empty set if table missing."""
    try:
        return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    # --- idempotency_records ---
    cols = _existing_columns("idempotency_records")
    if "claim_token" not in cols:
        op.add_column(
            "idempotency_records",
            sa.Column("claim_token", sa.String(36), nullable=True),
        )
    if "claim_version" not in cols:
        op.add_column(
            "idempotency_records",
            sa.Column("claim_version", sa.Integer, nullable=True, server_default=sa.text("0")),
        )

    # --- report_export_artifacts ---
    cols2 = _existing_columns("report_export_artifacts")
    if "idempotency_key" not in cols2:
        op.add_column(
            "report_export_artifacts",
            sa.Column("idempotency_key", sa.String(128), nullable=True),
        )
        op.create_index(
            "ix_report_export_artifacts_idempotency_key",
            "report_export_artifacts",
            ["idempotency_key"],
        )
    if "claim_token" not in cols2:
        op.add_column(
            "report_export_artifacts",
            sa.Column("claim_token", sa.String(36), nullable=True),
        )


def downgrade() -> None:
    # --- report_export_artifacts ---
    cols2 = _existing_columns("report_export_artifacts")
    if "claim_token" in cols2:
        op.drop_column("report_export_artifacts", "claim_token")
    if "idempotency_key" in cols2:
        op.drop_index(
            "ix_report_export_artifacts_idempotency_key",
            table_name="report_export_artifacts",
        )
        op.drop_column("report_export_artifacts", "idempotency_key")

    # --- idempotency_records ---
    cols = _existing_columns("idempotency_records")
    if "claim_version" in cols:
        op.drop_column("idempotency_records", "claim_version")
    if "claim_token" in cols:
        op.drop_column("idempotency_records", "claim_token")
