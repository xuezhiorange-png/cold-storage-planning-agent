"""0023_deletion_outbox_receipts

Add deletion_outbox and deletion_receipts tables for legacy
artifact deletion audit tracking and receipts with full CHECK
constraints, indexes, and unique constraint.

Revision ID: 0023_deletion_outbox_receipts
Revises: 0022_add_claim_version_audit_log
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023_deletion_outbox_receipts"
down_revision = "0022_add_claim_version_audit_log"
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


def _existing_unique_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    result: set[str] = set()
    for cons in inspector.get_unique_constraints(table):
        if cons.get("name"):
            result.add(str(cons["name"]))
    return result


def upgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"

    # --- Part 1: deletion_outbox table ---
    if "deletion_outbox" not in _existing_tables():
        op.create_table(
            "deletion_outbox",
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
            sa.Column("source_hash", sa.String(64), nullable=True),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'pending_audit'"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column(
                "retry_count",
                sa.Integer,
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

        # Indexes
        op.create_index(
            "ix_deletion_outbox_storage_key",
            "deletion_outbox",
            ["storage_key"],
        )
        op.create_index(
            "ix_deletion_outbox_status",
            "deletion_outbox",
            ["status"],
        )
        op.create_index(
            "ix_deletion_outbox_created_at",
            "deletion_outbox",
            ["created_at"],
        )

        # CHECK constraints
        if is_sqlite:
            with op.batch_alter_table("deletion_outbox") as batch_op:
                batch_op.create_check_constraint(
                    "ck_deletion_outbox_actor_not_empty",
                    sa.text("migration_actor <> ''"),
                )
                batch_op.create_check_constraint(
                    "ck_deletion_outbox_reason_not_empty",
                    sa.text("audit_reason <> ''"),
                )
                batch_op.create_check_constraint(
                    "ck_deletion_outbox_status",
                    sa.text("status IN ('pending_audit','deleting','audited','delete_failed')"),
                )
                batch_op.create_check_constraint(
                    "ck_deletion_outbox_retry_count",
                    sa.text("retry_count >= 0"),
                )
        else:
            op.create_check_constraint(
                "ck_deletion_outbox_actor_not_empty",
                "deletion_outbox",
                sa.text("migration_actor <> ''"),
            )
            op.create_check_constraint(
                "ck_deletion_outbox_reason_not_empty",
                "deletion_outbox",
                sa.text("audit_reason <> ''"),
            )
            op.create_check_constraint(
                "ck_deletion_outbox_status",
                "deletion_outbox",
                sa.text("status IN ('pending_audit','deleting','audited','delete_failed')"),
            )
            op.create_check_constraint(
                "ck_deletion_outbox_retry_count",
                "deletion_outbox",
                sa.text("retry_count >= 0"),
            )

    # --- Part 2: deletion_receipts table ---
    if "deletion_receipts" not in _existing_tables():
        op.create_table(
            "deletion_receipts",
            sa.Column("storage_key", sa.String(256), primary_key=True),
            sa.Column("stale_claim_token", sa.String(36), nullable=False),
            sa.Column("stale_claim_version", sa.Integer, nullable=False),
            sa.Column("reclaim_token", sa.String(36), nullable=False),
            sa.Column("reclaim_version", sa.Integer, nullable=False),
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("deletion_hash", sa.String(64), nullable=False),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'intent'"),
            ),
        )

        # Unique constraint + CHECK constraints
        if is_sqlite:
            with op.batch_alter_table("deletion_receipts") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_deletion_receipt_owners",
                    [
                        "storage_key",
                        "stale_claim_token",
                        "stale_claim_version",
                        "reclaim_token",
                        "reclaim_version",
                    ],
                )
                batch_op.create_check_constraint(
                    "ck_deletion_receipt_stale_version",
                    sa.text("stale_claim_version >= 0"),
                )
                batch_op.create_check_constraint(
                    "ck_deletion_receipt_reclaim_version",
                    sa.text("reclaim_version >= 0"),
                )
                batch_op.create_check_constraint(
                    "ck_deletion_receipt_hash",
                    sa.text("deletion_hash <> ''"),
                )
                batch_op.create_check_constraint(
                    "ck_deletion_receipt_status",
                    sa.text("status IN ('intent','deleted')"),
                )
        else:
            op.create_unique_constraint(
                "uq_deletion_receipt_owners",
                "deletion_receipts",
                [
                    "storage_key",
                    "stale_claim_token",
                    "stale_claim_version",
                    "reclaim_token",
                    "reclaim_version",
                ],
            )
            op.create_check_constraint(
                "ck_deletion_receipt_stale_version",
                "deletion_receipts",
                sa.text("stale_claim_version >= 0"),
            )
            op.create_check_constraint(
                "ck_deletion_receipt_reclaim_version",
                "deletion_receipts",
                sa.text("reclaim_version >= 0"),
            )
            op.create_check_constraint(
                "ck_deletion_receipt_hash",
                "deletion_receipts",
                sa.text("deletion_hash <> ''"),
            )
            op.create_check_constraint(
                "ck_deletion_receipt_status",
                "deletion_receipts",
                sa.text("status IN ('intent','deleted')"),
            )


def downgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"

    # --- Part 1: Drop deletion_receipts table ---
    if "deletion_receipts" in _existing_tables():
        if is_sqlite:
            existing_checks = _existing_constraints("deletion_receipts")
            existing_uq = _existing_unique_constraints("deletion_receipts")
            with op.batch_alter_table("deletion_receipts") as batch_op:
                for name in [
                    "ck_deletion_receipt_stale_version",
                    "ck_deletion_receipt_reclaim_version",
                    "ck_deletion_receipt_hash",
                    "ck_deletion_receipt_status",
                ]:
                    if name in existing_checks:
                        batch_op.drop_constraint(name, type_="check")
                if "uq_deletion_receipt_owners" in existing_uq:
                    batch_op.drop_constraint("uq_deletion_receipt_owners", type_="unique")
        else:
            existing = _existing_constraints("deletion_receipts")
            for name in [
                "ck_deletion_receipt_stale_version",
                "ck_deletion_receipt_reclaim_version",
                "ck_deletion_receipt_hash",
                "ck_deletion_receipt_status",
            ]:
                if name in existing:
                    op.drop_constraint(name, "deletion_receipts", type_="check")
            existing_uq = _existing_unique_constraints("deletion_receipts")
            if "uq_deletion_receipt_owners" in existing_uq:
                op.drop_constraint(
                    "uq_deletion_receipt_owners",
                    "deletion_receipts",
                    type_="unique",
                )
        op.drop_table("deletion_receipts")

    # --- Part 2: Drop deletion_outbox table ---
    if "deletion_outbox" in _existing_tables():
        # Drop indexes
        existing_idx = _existing_indexes("deletion_outbox")
        for ix_name in [
            "ix_deletion_outbox_storage_key",
            "ix_deletion_outbox_status",
            "ix_deletion_outbox_created_at",
        ]:
            if ix_name in existing_idx:
                op.drop_index(ix_name, table_name="deletion_outbox")

        # Drop CHECK constraints
        if is_sqlite:
            existing_checks = _existing_constraints("deletion_outbox")
            with op.batch_alter_table("deletion_outbox") as batch_op:
                for name in [
                    "ck_deletion_outbox_actor_not_empty",
                    "ck_deletion_outbox_reason_not_empty",
                    "ck_deletion_outbox_status",
                    "ck_deletion_outbox_retry_count",
                ]:
                    if name in existing_checks:
                        batch_op.drop_constraint(name, type_="check")
        else:
            existing = _existing_constraints("deletion_outbox")
            for name in [
                "ck_deletion_outbox_actor_not_empty",
                "ck_deletion_outbox_reason_not_empty",
                "ck_deletion_outbox_status",
                "ck_deletion_outbox_retry_count",
            ]:
                if name in existing:
                    op.drop_constraint(name, "deletion_outbox", type_="check")

        op.drop_table("deletion_outbox")
