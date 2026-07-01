"""Add CHECK constraints for weight revision governance.

Revision ID: 0030_add_weight_revision_governance_constraints
Revises: 0029_add_scheme_run_production_provenance
Create Date: 2026-07-01

Adds CHECK constraints to ``scheme_weight_set_revisions``:
- ck_weight_revision_valid_status: status IN ('draft', 'approved', 'superseded', 'revoked')
- ck_weight_revision_approval_evidence: approved revisions must have approval_at + approval_by
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_add_weight_revision_governance_constraints"
down_revision: str | None = "0029_add_scheme_run_production_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALID_STATUS_CK = "status IN ('draft', 'approved', 'superseded', 'revoked')"

_APPROVAL_EVIDENCE_CK = (
    "(status = 'approved' AND approved_at IS NOT NULL"
    " AND approved_by IS NOT NULL AND approved_by != '')"
    " OR status != 'approved'"
)


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name == "sqlite":
        _sqlite_upgrade()
    else:
        _pg_upgrade()


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name == "sqlite":
        _sqlite_downgrade()
    else:
        _pg_downgrade()


# ── PostgreSQL ──────────────────────────────────────────────────────────────


def _pg_upgrade() -> None:
    op.create_check_constraint(
        "ck_weight_revision_valid_status",
        "scheme_weight_set_revisions",
        sa.text(_VALID_STATUS_CK),
    )
    op.create_check_constraint(
        "ck_weight_revision_approval_evidence",
        "scheme_weight_set_revisions",
        sa.text(_APPROVAL_EVIDENCE_CK),
    )


def _pg_downgrade() -> None:
    op.drop_constraint(
        "ck_weight_revision_approval_evidence",
        "scheme_weight_set_revisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_weight_revision_valid_status",
        "scheme_weight_set_revisions",
        type_="check",
    )


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_upgrade() -> None:
    with op.batch_alter_table("scheme_weight_set_revisions") as batch_op:
        batch_op.create_check_constraint(
            "ck_weight_revision_valid_status",
            sa.text(_VALID_STATUS_CK),
        )
        batch_op.create_check_constraint(
            "ck_weight_revision_approval_evidence",
            sa.text(_APPROVAL_EVIDENCE_CK),
        )


def _sqlite_downgrade() -> None:
    with op.batch_alter_table("scheme_weight_set_revisions") as batch_op:
        batch_op.drop_constraint(
            "ck_weight_revision_approval_evidence",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_weight_revision_valid_status",
            type_="check",
        )
