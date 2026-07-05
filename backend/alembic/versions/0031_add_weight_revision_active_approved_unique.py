"""Add partial unique index for active-approved weight revisions.

Revision ID: 0031_add_weight_revision_active_approved_unique
Revises: 0030_add_weight_revision_governance_constraints
Create Date: 2026-07-01

PostgreSQL: partial unique index on (weight_set_id, code) WHERE status = 'approved'
SQLite: cannot use partial unique indexes; uniqueness is enforced at
  the application layer via CAS (has_approved_revision + approve_revision).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_add_weight_revision_active_approved_unique"
down_revision: str | None = "0030_add_weight_revision_governance_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name != "sqlite":
        op.execute(
            "CREATE UNIQUE INDEX uq_active_approved_weight_rev "
            "ON scheme_weight_set_revisions (weight_set_id, code) "
            "WHERE status = 'approved'"
        )


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name != "sqlite":
        op.execute("DROP INDEX IF EXISTS uq_active_approved_weight_rev")
