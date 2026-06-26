"""0016_add_claimed_at

Add claimed_at column to idempotency_records for stale-claim recovery.

Revision ID: 0016_add_claimed_at
Revises: 0015_add_active_slot
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_add_claimed_at"
down_revision = "0015_add_active_slot"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    """Return the set of column names for *table*, or empty set if table missing."""
    try:
        return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    cols = _existing_columns("idempotency_records")
    if "claimed_at" not in cols:
        op.add_column(
            "idempotency_records",
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    cols = _existing_columns("idempotency_records")
    if "claimed_at" in cols:
        op.drop_column("idempotency_records", "claimed_at")
