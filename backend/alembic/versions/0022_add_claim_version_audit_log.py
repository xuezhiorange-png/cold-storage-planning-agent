"""0022_add_claim_version_and_audit_log

Add claim_version column to cleanup_debt with CHECK constraint,
and create the migration_audit_log table.

Revision ID: 0022_add_claim_version_audit_log
Revises: 0021_cleanup_debt_lock_expires
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022_add_claim_version_audit_log"
down_revision = "0021_cleanup_debt_lock_expires"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table)}


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {ix["name"] for ix in inspector.get_indexes(table) if ix.get("name")}


def _existing_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    result: set[str] = set()
    for cons in inspector.get_check_constraints(table):
        if cons.get("name"):
            result.add(str(cons["name"]))
    return result


def upgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"

    # --- Part 1: cleanup_debt.claim_version ---
    cols = _existing_columns("cleanup_debt")
    constraints = _existing_constraints("cleanup_debt")

    if "claim_version" not in cols:
        if is_sqlite:
            with op.batch_alter_table("cleanup_debt") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "claim_version",
                        sa.Integer,
                        nullable=False,
                        server_default=sa.text("0"),
                    )
                )
                if "ck_cleanup_debt_claim_version" not in constraints:
                    batch_op.create_check_constraint(
                        "ck_cleanup_debt_claim_version",
                        sa.text("claim_version >= 0"),
                    )
        else:
            op.add_column(
                "cleanup_debt",
                sa.Column("claim_version", sa.Integer, nullable=False, server_default=sa.text("0")),
            )
            if "ck_cleanup_debt_claim_version" not in constraints:
                op.create_check_constraint(
                    "ck_cleanup_debt_claim_version",
                    "cleanup_debt",
                    sa.text("claim_version >= 0"),
                )

    # --- Part 2: migration_audit_log table ---
    if "migration_audit_log" not in _existing_tables():
        op.create_table(
            "migration_audit_log",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("storage_key", sa.String(256), nullable=False),
            sa.Column("migration_actor", sa.String(64), nullable=False),
            sa.Column("audit_reason", sa.Text, nullable=False),
            sa.Column(
                "operation",
                sa.String(32),
                nullable=False,
                server_default=sa.text("'legacy_delete'"),
            ),
            sa.Column("result", sa.String(64), nullable=False),
            sa.Column("source_hash", sa.String(64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

        # Indexes
        op.create_index(
            "ix_migration_audit_log_storage_key",
            "migration_audit_log",
            ["storage_key"],
        )
        op.create_index("ix_migration_audit_log_created_at", "migration_audit_log", ["created_at"])

        # CHECK constraints
        if is_sqlite:
            with op.batch_alter_table("migration_audit_log") as batch_op:
                batch_op.create_check_constraint(
                    "ck_migration_audit_log_actor_not_empty",
                    sa.text("migration_actor <> ''"),
                )
                batch_op.create_check_constraint(
                    "ck_migration_audit_log_reason_not_empty",
                    sa.text("audit_reason <> ''"),
                )
        else:
            op.create_check_constraint(
                "ck_migration_audit_log_actor_not_empty",
                "migration_audit_log",
                sa.text("migration_actor <> ''"),
            )
            op.create_check_constraint(
                "ck_migration_audit_log_reason_not_empty",
                "migration_audit_log",
                sa.text("audit_reason <> ''"),
            )


def downgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"

    # --- Part 1: Drop migration_audit_log table ---
    if "migration_audit_log" in _existing_tables():
        existing = _existing_indexes("migration_audit_log")
        for ix_name in ["ix_migration_audit_log_storage_key", "ix_migration_audit_log_created_at"]:
            if ix_name in existing:
                if is_sqlite:
                    with op.batch_alter_table("migration_audit_log") as batch_op:
                        batch_op.drop_index(ix_name)
                else:
                    op.drop_index(ix_name, table_name="migration_audit_log")
        op.drop_table("migration_audit_log")

    # --- Part 2: Drop claim_version from cleanup_debt ---
    cols = _existing_columns("cleanup_debt")
    if "claim_version" in cols:
        constraints = _existing_constraints("cleanup_debt")
        if "ck_cleanup_debt_claim_version" in constraints:
            if is_sqlite:
                with op.batch_alter_table("cleanup_debt") as batch_op:
                    batch_op.drop_constraint("ck_cleanup_debt_claim_version", type_="check")
            else:
                op.drop_constraint("ck_cleanup_debt_claim_version", "cleanup_debt", type_="check")

        if is_sqlite:
            with op.batch_alter_table("cleanup_debt") as batch_op:
                batch_op.drop_column("claim_version")
        else:
            op.drop_column("cleanup_debt", "claim_version")
