"""0038: Phase 4 Issue #35 Slice 1 — coefficient_approval_log + coefficient_audit_log.

Revision ID: 0038_phase4_slice1_coefficient_approval
Revises: 0037_phase1_drop_correlation_id_default
Create Date: 2026-07-07

Contract
========

This migration implements the **two log tables** required by design
contract §3.2 (``coefficient_approval_log``) and §3.3
(``coefficient_audit_log``).

Per Charles's Slice 1 boundary correction (2026-07-07):

- This migration does **not** alter the existing ``coefficient_revisions``
  table. No new column is added; no existing column's ``NOT NULL`` or
  ``server_default`` is changed. No ``source_citation`` column is
  added; ``source_reference`` already exists and remains the storage
  column. No ``governance_status`` column is added; the existing
  ``status`` column continues to carry the status value.

- The migration is **append-only**: two new tables, two indexes, no
  constraint that fails on either SQLite or PostgreSQL.

- The migration is the source of truth for both log tables'
  schema. The ORM models in
  ``cold_storage.modules.coefficients.infrastructure.orm`` are
  kept in sync (see :class:`CoefficientApprovalLogRecord` and
  :class:`CoefficientAuditLogRecord`).

Both tables are append-only at the application boundary (write-only
API in the application service). The schema-level ``UPDATE`` /
``DELETE`` rejection is deferred to a follow-up Slice together
with archive persistence (see design contract §3.3 + §14.4).

Dual-backend
============

- SQLite: ``Integer`` autoincrement PK (ROWID via SQLite AUTOINCREMENT
  keyword emitted by SQLAlchemy when ``autoincrement=True``).
- PostgreSQL: ``Integer`` autoincrement PK is SERIAL on PostgreSQL.

The same DDL works on both backends with no dialect branching; this
keeps the migration readable and auditable. The application layer's
write ports are identical for both backends.

Downgrade safety
================

``downgrade()`` drops both tables. There are no foreign keys from
the log tables to ``coefficient_revisions`` (the audit/approval
logs intentionally reference revisions by id without an FK so that
deleting a revision does not cascade-erase its history — a
governance-friendly choice). Dropping the tables requires no
preflight in Slice 1; if a follow-up Slice adds FKs the
preflight must be revisited.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0038_phase4_slice1_coefficient_approval"
down_revision: str | Sequence[str] | None = "0037_phase1_drop_correlation_id_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Constants — kept module-local to mirror the project's other
# migrations' style. Two tables, two indexes on revision_id.
TBL_APPROVAL_LOG = "coefficient_approval_log"
TBL_AUDIT_LOG = "coefficient_audit_log"


def upgrade() -> None:
    """Create the two log tables.

    Both schemas use ``server_default`` only where Charles's boundary
    correction allows (``created_at`` is the only default; ``action``
    / ``old_state`` / ``new_state`` / ``reason`` come from the
    application layer; revision_id / actor / correlation_id are
    NOT NULL without defaults).
    """
    op.create_table(
        TBL_APPROVAL_LOG,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("reviewer", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("citation", sa.String(length=500), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_coefficient_approval_log_revision_id",
        TBL_APPROVAL_LOG,
        ["revision_id"],
    )

    op.create_table(
        TBL_AUDIT_LOG,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("old_state", sa.String(length=32), nullable=False),
        sa.Column("new_state", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_coefficient_audit_log_revision_id",
        TBL_AUDIT_LOG,
        ["revision_id"],
    )


def downgrade() -> None:
    """Drop both tables and their indexes.

    No preflight is required for Slice 1: the log tables have no
    foreign keys to existing tables, and ``coefficient_revisions``
    is not modified by this migration. If a future Slice adds FKs
    from the log tables to ``coefficient_revisions`` or to
    ``coefficient_definitions``, the preflight must verify the log
    tables are empty (or rewrite the FK policy to set NULL on
    delete).
    """
    op.drop_index("ix_coefficient_audit_log_revision_id", table_name=TBL_AUDIT_LOG)
    op.drop_table(TBL_AUDIT_LOG)
    op.drop_index("ix_coefficient_approval_log_revision_id", table_name=TBL_APPROVAL_LOG)
    op.drop_table(TBL_APPROVAL_LOG)
