"""0021_add_cleanup_debt_lock_expires_at

Add the lock_expires_at column to cleanup_debt for processing-lease
timeout recovery, matching the ORM model.

Revision ID: 0021_cleanup_debt_lock_expires
Revises: 0020_add_cleanup_debt
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0021_cleanup_debt_lock_expires"
down_revision = "0020_add_cleanup_debt"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {ix["name"] for ix in inspector.get_indexes(table) if ix.get("name")}


def upgrade() -> None:
    cols = _existing_columns("cleanup_debt")
    if "lock_expires_at" in cols:
        return

    is_sqlite = op.get_bind().dialect.name == "sqlite"
    if is_sqlite:
        with op.batch_alter_table("cleanup_debt") as batch_op:
            batch_op.add_column(
                sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch_op.create_index(
                "ix_cleanup_debt_lock_expires_at",
                ["lock_expires_at"],
            )
    else:
        op.add_column(
            "cleanup_debt",
            sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_cleanup_debt_lock_expires_at",
            "cleanup_debt",
            ["lock_expires_at"],
        )


def downgrade() -> None:
    cols = _existing_columns("cleanup_debt")
    if "lock_expires_at" not in cols:
        return

    is_sqlite = op.get_bind().dialect.name == "sqlite"
    existing = _existing_indexes("cleanup_debt")
    if "ix_cleanup_debt_lock_expires_at" in existing:
        if is_sqlite:
            with op.batch_alter_table("cleanup_debt") as batch_op:
                batch_op.drop_index("ix_cleanup_debt_lock_expires_at")
        else:
            op.drop_index(
                "ix_cleanup_debt_lock_expires_at",
                table_name="cleanup_debt",
            )

    if is_sqlite:
        with op.batch_alter_table("cleanup_debt") as batch_op:
            batch_op.drop_column("lock_expires_at")
    else:
        op.drop_column("cleanup_debt", "lock_expires_at")
