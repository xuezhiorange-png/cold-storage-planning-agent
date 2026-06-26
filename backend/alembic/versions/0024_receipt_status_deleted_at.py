"""0024_receipt_status_deleted_at

Fix deletion_receipts status CHECK to include 'delete_failed',
and make deleted_at nullable with no default.

Upgrade changes:
1. Drop CHECK constraint ck_deletion_receipt_status and recreate it
   with values IN ('intent','deleted','delete_failed')
2. Make deleted_at nullable and remove server_default

Downgrade changes:
1. Normalize delete_failed rows to status='intent', deleted_at=now
2. Drop CHECK constraint and recreate with IN ('intent','deleted')
3. Update NULL deleted_at to now()
4. Make deleted_at NOT NULL with server_default now()

Revision ID: 0024_receipt_status_deleted_at
Revises: 0023_deletion_outbox_receipts
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0024_fix_receipt_status_and_deleted_at"
down_revision = "0023_deletion_outbox_receipts"
branch_labels = None
depends_on = None


def _existing_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    result: set[str] = set()
    for cons in inspector.get_check_constraints(table):
        if cons.get("name"):
            result.add(str(cons["name"]))
    return result


def _existing_tables() -> set[str]:
    """Return set of table names that already exist in the database."""
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _constraint_allows_delete_failed(table: str) -> bool:
    """Check if ck_deletion_receipt_status already allows 'delete_failed'."""
    inspector = sa.inspect(op.get_bind())
    for cons in inspector.get_check_constraints(table):
        if cons.get("name") == "ck_deletion_receipt_status":
            sqltext = cons.get("sqltext", "")
            return "delete_failed" in sqltext
    return False


def upgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    is_postgresql = op.get_bind().dialect.name == "postgresql"

    # Widen alembic_version.version_num for PostgreSQL (VARCHAR(32) can't hold
    # revision IDs like "0024_fix_receipt_status_and_deleted_at" which is 38 chars)
    if is_postgresql:
        op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")

    # Idempotent: skip if constraint already allows delete_failed
    if _constraint_allows_delete_failed("deletion_receipts"):
        return

    existing_checks = _existing_constraints("deletion_receipts")

    if is_sqlite:
        with op.batch_alter_table("deletion_receipts") as batch_op:
            # Drop old status CHECK constraint
            if "ck_deletion_receipt_status" in existing_checks:
                batch_op.drop_constraint("ck_deletion_receipt_status", type_="check")
            # Create new status CHECK constraint allowing delete_failed
            batch_op.create_check_constraint(
                "ck_deletion_receipt_status",
                sa.text("status IN ('intent','deleted','delete_failed')"),
            )
            # Make deleted_at nullable and remove default
            batch_op.alter_column(
                "deleted_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
                existing_server_default=sa.func.now(),
                server_default=None,
            )
    else:
        # PostgreSQL
        if "ck_deletion_receipt_status" in existing_checks:
            op.drop_constraint(
                "ck_deletion_receipt_status",
                "deletion_receipts",
                type_="check",
            )
        op.create_check_constraint(
            "ck_deletion_receipt_status",
            "deletion_receipts",
            sa.text("status IN ('intent','deleted','delete_failed')"),
        )
        op.alter_column(
            "deletion_receipts",
            "deleted_at",
            nullable=True,
            server_default=None,
        )


def downgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    existing_checks = _existing_constraints("deletion_receipts")

    # Normalize delete_failed rows before restoring old constraint that
    # only allows IN ('intent','deleted')
    if "deletion_receipts" in _existing_tables():
        if is_sqlite:
            op.execute(
                sa.text(
                    "UPDATE deletion_receipts SET status = 'intent', "
                    "deleted_at = CURRENT_TIMESTAMP "
                    "WHERE status = 'delete_failed'"
                )
            )
        else:
            op.execute(
                sa.text(
                    "UPDATE deletion_receipts SET status = 'intent', "
                    "deleted_at = NOW() "
                    "WHERE status = 'delete_failed'"
                )
            )

    # First, update any NULL deleted_at values to now()
    # (needed before restoring NOT NULL)
    if is_sqlite:
        op.execute(
            sa.text(
                "UPDATE deletion_receipts "
                "SET deleted_at = CURRENT_TIMESTAMP "
                "WHERE deleted_at IS NULL"
            )
        )
    else:
        op.execute(
            sa.text("UPDATE deletion_receipts SET deleted_at = NOW() WHERE deleted_at IS NULL")
        )

    if is_sqlite:
        with op.batch_alter_table("deletion_receipts") as batch_op:
            # Drop the new status CHECK constraint
            if "ck_deletion_receipt_status" in existing_checks:
                batch_op.drop_constraint("ck_deletion_receipt_status", type_="check")
            # Restore the original status CHECK constraint
            batch_op.create_check_constraint(
                "ck_deletion_receipt_status",
                sa.text("status IN ('intent','deleted')"),
            )
            # Restore NOT NULL + server_default on deleted_at
            batch_op.alter_column(
                "deleted_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
                existing_server_default=None,
                server_default=sa.func.now(),
            )
    else:
        # PostgreSQL
        if "ck_deletion_receipt_status" in existing_checks:
            op.drop_constraint(
                "ck_deletion_receipt_status",
                "deletion_receipts",
                type_="check",
            )
        op.create_check_constraint(
            "ck_deletion_receipt_status",
            "deletion_receipts",
            sa.text("status IN ('intent','deleted')"),
        )
        op.alter_column(
            "deletion_receipts",
            "deleted_at",
            nullable=False,
            server_default=sa.func.now(),
        )

    # Note: intentionally NOT restoring alembic_version.version_num to
    # VARCHAR(32) here, because Alembic will attempt to write the current
    # revision ID "0024_fix_receipt_status_and_deleted_at" (38 chars) back
    # to the version table AFTER the downgrade function returns, and that
    # would fail against VARCHAR(32). Leaving the column as VARCHAR(64) is
    # forward-compatible and causes no issues on PostgreSQL.
