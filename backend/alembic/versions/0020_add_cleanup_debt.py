"""0020_add_cleanup_debt

Add the cleanup_debt table for two-phase physical file cleanup with
retryable state machine, CAS locking, and deterministic backoff.

Revision ID: 0020_add_cleanup_debt
Revises: 0019_add_localization_columns
Create Date: 2026-06-25
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0020_add_cleanup_debt"
down_revision = "0019_add_localization_columns"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {ix["name"] for ix in inspector.get_indexes(table) if ix.get("name")}


def upgrade() -> None:
    if "cleanup_debt" in _existing_tables():
        return

    op.create_table(
        "cleanup_debt",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("storage_key", sa.String(256), nullable=False),
        sa.Column(
            "stale_claim_token",
            sa.String(36),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "stale_claim_version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "reclaim_token",
            sa.String(36),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "reclaim_version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "retry_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "last_error",
            sa.Text,
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "locked_by",
            sa.String(128),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )

    # Indexes
    op.create_index(
        "ix_cleanup_debt_idempotency_key",
        "cleanup_debt",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_cleanup_debt_status",
        "cleanup_debt",
        ["status"],
    )
    op.create_index(
        "ix_cleanup_debt_next_retry_at",
        "cleanup_debt",
        ["next_retry_at"],
    )

    # Unique constraint + CHECK constraints
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    if is_sqlite:
        with op.batch_alter_table("cleanup_debt") as batch_op:
            batch_op.create_unique_constraint(
                "uq_cleanup_debt_stale_file",
                ["storage_key", "stale_claim_token", "stale_claim_version"],
            )
            batch_op.create_check_constraint(
                "ck_cleanup_debt_status",
                sa.text(
                    "status IN ('pending', 'processing', 'retryable', "
                    "'completed', 'permanent_failed')"
                ),
            )
            batch_op.create_check_constraint(
                "ck_cleanup_debt_stale_claim_version",
                sa.text("stale_claim_version >= 0"),
            )
            batch_op.create_check_constraint(
                "ck_cleanup_debt_reclaim_version",
                sa.text("reclaim_version >= 0"),
            )
            batch_op.create_check_constraint(
                "ck_cleanup_debt_retry_count",
                sa.text("retry_count >= 0"),
            )
    else:
        op.create_unique_constraint(
            "uq_cleanup_debt_stale_file",
            "cleanup_debt",
            ["storage_key", "stale_claim_token", "stale_claim_version"],
        )
        op.create_check_constraint(
            "ck_cleanup_debt_status",
            "cleanup_debt",
            sa.text(
                "status IN ('pending', 'processing', 'retryable', 'completed', 'permanent_failed')"
            ),
        )
        op.create_check_constraint(
            "ck_cleanup_debt_stale_claim_version",
            "cleanup_debt",
            sa.text("stale_claim_version >= 0"),
        )
        op.create_check_constraint(
            "ck_cleanup_debt_reclaim_version",
            "cleanup_debt",
            sa.text("reclaim_version >= 0"),
        )
        op.create_check_constraint(
            "ck_cleanup_debt_retry_count",
            "cleanup_debt",
            sa.text("retry_count >= 0"),
        )


def downgrade() -> None:
    if "cleanup_debt" not in _existing_tables():
        return

    # Drop CHECK constraints + unique constraint together (SQLite = batch)
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    if not is_sqlite:
        existing = _existing_constraints("cleanup_debt")
        for name in [
            "ck_cleanup_debt_status",
            "ck_cleanup_debt_stale_claim_version",
            "ck_cleanup_debt_reclaim_version",
            "ck_cleanup_debt_retry_count",
        ]:
            if name in existing:
                op.drop_constraint(name, "cleanup_debt", type_="check")
        existing_uq = _existing_unique_constraints("cleanup_debt")
        if "uq_cleanup_debt_stale_file" in existing_uq:
            op.drop_constraint(
                "uq_cleanup_debt_stale_file",
                "cleanup_debt",
                type_="unique",
            )
    else:
        existing_constraints = _existing_constraints("cleanup_debt")
        existing_uq = _existing_unique_constraints("cleanup_debt")
        with op.batch_alter_table("cleanup_debt") as batch_op:
            for name in [
                "ck_cleanup_debt_status",
                "ck_cleanup_debt_stale_claim_version",
                "ck_cleanup_debt_reclaim_version",
                "ck_cleanup_debt_retry_count",
            ]:
                if name in existing_constraints:
                    batch_op.drop_constraint(name, type_="check")
            if "uq_cleanup_debt_stale_file" in existing_uq:
                batch_op.drop_constraint("uq_cleanup_debt_stale_file", type_="unique")

    # Drop indexes
    for ix in [
        "ix_cleanup_debt_next_retry_at",
        "ix_cleanup_debt_status",
        "ix_cleanup_debt_idempotency_key",
    ]:
        existing = _existing_indexes("cleanup_debt")
        if ix in existing:
            op.drop_index(ix, table_name="cleanup_debt")

    op.drop_table("cleanup_debt")


def _existing_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    result: set[str] = set()
    for cons in inspector.get_check_constraints(table):
        if cons.get("name"):
            result.add(str(cons["name"]))
    return result


def _existing_unique_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    result: set[str] = set()
    for cons in inspector.get_unique_constraints(table):
        if cons.get("name"):
            result.add(str(cons["name"]))
    return result
