"""0039: widen report_export_artifacts.mime_type from VARCHAR(64) to VARCHAR(255).

Revision ID: 0039_widen_report_export_artifact_mime_type
Revises: 0038_phase4_slice1_coefficient_approval
Create Date: 2026-07-19

Contract
========

This migration addresses the pre-existing ``report_export_artifacts
.mime_type`` column being declared ``VARCHAR(64)`` by ORM model
:class:`cold_storage.modules.reports.infrastructure.orm
.ReportExportArtifactRecord`. The standard DOCX MIME
``application/vnd.openxmlformats-officedocument.wordprocessingml
.document`` is 71 characters, which exceeds ``VARCHAR(64)`` and
causes ``psycopg2.errors.StringDataRightTruncation`` on PostgreSQL
when four-render pilot acceptance attempts the real DOCX download
artifact path.

Per Charles's §5 round directive (2026-07-19 PR67 P1-4 MIME
schema amendment):

- The ORM column at ``orm.py:ReportExportArtifactRecord.mime_type``
  is widened to ``sa.String(255)`` in the SAME commit (this
  migration is shipped alongside it).

- The authoritative widening lives in this migration; the ORM
  class is kept in sync. Per ``AGENTS.md`` 'database schema
  changes must go through Alembic', this is the only authority
  for the change.

- The choice of ``VARCHAR(255)`` (NOT ``VARCHAR(76)``, NOT
  ``String(75)``, NOT ``Text``, NOT a dialect-specific type)
  is intentional — it provides stable MIME storage capacity for
  any future locale / vendor MIME value, not just the current
  71-character DOCX string.

Dual-backend
============

PostgreSQL (``op.alter_column``)
    ``ALTER TABLE report_export_artifacts ALTER COLUMN mime_type
    TYPE VARCHAR(255)`` — emits a native PG column-type change.
    PostgreSQL is a full implementation; ``VARCHAR(64)→VARCHAR(255)
    `` is a metadata-only change on PG (no row rewrite required
    because new length is LARGER than old; remaining entries fit
    unchanged).

SQLite (``op.batch_alter_table``)
    SQLite does NOT support ``ALTER COLUMN ... TYPE``. The
    repository's previous migrations (e.g. 0036, 0019) use
    ``op.batch_alter_table`` which copies-and-rebuilds the table
    on SQLite. That pattern is reused here so the migration works
    identically against ``:memory:`` test databases, file
    databases, and the integration test fixtures.

Downgrade safety
================

The downgrade of ``VARCHAR(255)→VARCHAR(64)`` MUST fail-closed
when any row has ``mime_type`` length ``> 64``. The migration
reads the existing data BEFORE the column change and emits a
clear ``RuntimeError`` listing the offending rows (by primary
key + ``length(mime_type)``) when long data exists. This is the
opposite of the brief's "禁止在 downgrade 中执行 LEFT() /
SUBSTR()" prohibition — silent truncation is NOT acceptable.

On SQLite the preflight uses an explicit ``SELECT length(...)
FROM report_export_artifacts WHERE length(...) > 64``
diagnostic query and raises with the OFFENDING row list.

On PostgreSQL the preflight uses
``SELECT id, length(mime_type), mime_type FROM report_export_artifacts
WHERE length(mime_type) > 64`` — same shape, namespaced to
PG's dialect helpers.

MIME_VALUE_TRUNCATION = NO  (brief §五)
DOWNGRADE_FAILS_CLOSED_ON_LONG_DATA = YES  (brief §六)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039_widen_report_export_artifact_mime_type"
down_revision: str | Sequence[str] | None = "0038_phase4_slice1_coefficient_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Constants — module-local to mirror the project's other migrations.
TBL_REPORT_EXPORT_ARTIFACTS = "report_export_artifacts"
COL_MIME_TYPE = "mime_type"

OLD_LENGTH = 64
NEW_LENGTH = 255


# ---------------------------------------------------------------------------
# Preflight helpers — fail-closed on downpath long data
# ---------------------------------------------------------------------------


def _check_downgrade_preflight() -> None:
    """Raise RuntimeError if any row has mime_type length > OLD_LENGTH.

    The query is dialect-aware: PostgreSQL uses ``length(mime_type)``
    identically to SQLite, but the bind is necessary for clean PG
    connection scoping. The query is SELECT-only and never mutates
    data; it MUST be invoked from ``downgrade()`` BEFORE the column
    is narrowed, otherwise the check would itself be impossible
    (the column may already have been narrowed on a previous
    downgrade attempt that completed against the wrong env, so we
    invoke defensively).

    Errors raised:

    - ``RuntimeError`` with a multi-line message listing the first
      N offending rows (id + length + the actual mime_type string
      truncated to 80 chars for legibility).

    No LEFT()/SUBSTR() is ever used to truncate the values; we
    preserve them in the message so the operator can decide what
    to do (typically: delete those test artifacts, archive them
    elsewhere, or update the column with a wider stored mime).
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TBL_REPORT_EXPORT_ARTIFACTS not in set(inspector.get_table_names()):
        return
    result = bind.execute(
        sa.text(
            f"SELECT id, length({COL_MIME_TYPE}) AS mime_len, {COL_MIME_TYPE} "
            f"FROM {TBL_REPORT_EXPORT_ARTIFACTS} "
            f"WHERE length({COL_MIME_TYPE}) > :max_len "
            f"ORDER BY length({COL_MIME_TYPE}) DESC, id ASC"
        ),
        {"max_len": OLD_LENGTH},
    )
    long_rows = list(result.fetchall())
    if long_rows:
        rendered = []
        for row in long_rows[:20]:
            rendered.append(f"  - id={row[0]!r} length={row[1]} value={row[2]!r}")
        more = "" if len(long_rows) <= 20 else f"\n  ... ({len(long_rows) - 20} more)"
        raise RuntimeError(
            "Cannot downgrade report_export_artifacts.mime_type "
            f"from VARCHAR({NEW_LENGTH}) to VARCHAR({OLD_LENGTH}): "
            f"{len(long_rows)} row(s) have mime_type longer than "
            f"{OLD_LENGTH} characters. Silent truncation is "
            "forbidden by AGENTS.md / PR67 P1-4 §六 (no LEFT/SUBSTR "
            "in downgrade). Long rows (truncated to 20):\n" + "\n".join(rendered) + more
        )


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    """Widen ``report_export_artifacts.mime_type`` from VARCHAR(64) to VARCHAR(255)."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        # SQLite path: copy-and-rebuild via batch_alter_table. The
        # column stays NOT NULL with no server_default; data is
        # preserved by the batch helper.
        with op.batch_alter_table(
            TBL_REPORT_EXPORT_ARTIFACTS,
            recreate="always",
        ) as batch_op:
            batch_op.alter_column(
                COL_MIME_TYPE,
                existing_type=sa.String(length=OLD_LENGTH),
                type_=sa.String(length=NEW_LENGTH),
                existing_nullable=False,
            )
        return

    # PostgreSQL path: native ALTER COLUMN ... TYPE. The column has
    # no DEFAULT (NOT NULL, application-supplied), so no DEFAULT
    # carry-over is required. Issuing `existing_type` on PG for
    # verification clarity.
    op.alter_column(
        TBL_REPORT_EXPORT_ARTIFACTS,
        COL_MIME_TYPE,
        existing_type=sa.String(length=OLD_LENGTH),
        type_=sa.String(length=NEW_LENGTH),
        existing_nullable=False,
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    """Narrow ``report_export_artifacts.mime_type`` from VARCHAR(255) back to VARCHAR(64).

    Fail-closed: if any row has ``mime_type`` length ``> 64``, the
    downgrade aborts with ``RuntimeError`` BEFORE the column is
    altered. This is the AGENTS.md 'database schema changes must
    go through Alembic' + PR67 P1-4 §六 'DOWNGRADE_FAILS_CLOSED_ON
    _LONG_DATA' mandate.
    """
    _check_downgrade_preflight()

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table(
            TBL_REPORT_EXPORT_ARTIFACTS,
            recreate="always",
        ) as batch_op:
            batch_op.alter_column(
                COL_MIME_TYPE,
                existing_type=sa.String(length=NEW_LENGTH),
                type_=sa.String(length=OLD_LENGTH),
                existing_nullable=False,
            )
        return

    op.alter_column(
        TBL_REPORT_EXPORT_ARTIFACTS,
        COL_MIME_TYPE,
        existing_type=sa.String(length=NEW_LENGTH),
        type_=sa.String(length=OLD_LENGTH),
        existing_nullable=False,
    )
