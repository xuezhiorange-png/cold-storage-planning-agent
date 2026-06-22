"""0010_add_idempotency_record

Revision ID: 0010_add_idempotency_record
Revises: 0009_add_reports
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_add_idempotency_record"
down_revision = "0009_add_reports"
branch_labels = None
depends_on = None


def _json_column_type() -> sa.types.TypeEngine:
    """Return JSONB for PostgreSQL, JSON for SQLite."""
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    json_type = _json_column_type()

    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="claimed"
        ),
        sa.Column("result_payload", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
