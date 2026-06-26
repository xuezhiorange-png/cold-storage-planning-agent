"""0025_add_outbox_claim_fields

Add lease/claim fields to deletion_outbox for CAS-based outbox claiming
with two-phase recovery:

- claim_token VARCHAR(36) NULL
- claim_version INTEGER NOT NULL DEFAULT 0
- locked_at TIMESTAMP WITH TIME ZONE NULL
- lock_expires_at TIMESTAMP WITH TIME ZONE NULL
- CHECK claim_version >= 0

Revision ID: 0025_add_outbox_claim_fields
Revises: 0024_receipt_status_deleted_at
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025_add_outbox_claim_fields"
down_revision = "0024_fix_receipt_status_and_deleted_at"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table)}


def _existing_constraints(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    result: set[str] = set()
    for cons in inspector.get_check_constraints(table):
        if cons.get("name"):
            result.add(str(cons["name"]))
    return result


def upgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    cols = _existing_columns("deletion_outbox")
    constraints = _existing_constraints("deletion_outbox")

    if is_sqlite:
        with op.batch_alter_table("deletion_outbox") as batch_op:
            if "claim_token" not in cols:
                batch_op.add_column(sa.Column("claim_token", sa.String(36), nullable=True))
            if "claim_version" not in cols:
                batch_op.add_column(
                    sa.Column(
                        "claim_version",
                        sa.Integer,
                        nullable=False,
                        server_default=sa.text("0"),
                    )
                )
            if "locked_at" not in cols:
                batch_op.add_column(
                    sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True)
                )
            if "lock_expires_at" not in cols:
                batch_op.add_column(
                    sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True)
                )
            if "ck_deletion_outbox_claim_version" not in constraints:
                batch_op.create_check_constraint(
                    "ck_deletion_outbox_claim_version",
                    sa.text("claim_version >= 0"),
                )
    else:
        if "claim_token" not in cols:
            op.add_column(
                "deletion_outbox",
                sa.Column("claim_token", sa.String(36), nullable=True),
            )
        if "claim_version" not in cols:
            op.add_column(
                "deletion_outbox",
                sa.Column(
                    "claim_version",
                    sa.Integer,
                    nullable=False,
                    server_default=sa.text("0"),
                ),
            )
        if "locked_at" not in cols:
            op.add_column(
                "deletion_outbox",
                sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "lock_expires_at" not in cols:
            op.add_column(
                "deletion_outbox",
                sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "ck_deletion_outbox_claim_version" not in constraints:
            op.create_check_constraint(
                "ck_deletion_outbox_claim_version",
                "deletion_outbox",
                sa.text("claim_version >= 0"),
            )


def downgrade() -> None:
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    cols = _existing_columns("deletion_outbox")
    constraints = _existing_constraints("deletion_outbox")

    if is_sqlite:
        with op.batch_alter_table("deletion_outbox") as batch_op:
            if "ck_deletion_outbox_claim_version" in constraints:
                batch_op.drop_constraint("ck_deletion_outbox_claim_version", type_="check")
            for col_name in ("lock_expires_at", "locked_at", "claim_version", "claim_token"):
                if col_name in cols:
                    batch_op.drop_column(col_name)
    else:
        if "ck_deletion_outbox_claim_version" in constraints:
            op.drop_constraint(
                "ck_deletion_outbox_claim_version",
                "deletion_outbox",
                type_="check",
            )
        for col_name in ("lock_expires_at", "locked_at", "claim_version", "claim_token"):
            if col_name in cols:
                op.drop_column("deletion_outbox", col_name)
