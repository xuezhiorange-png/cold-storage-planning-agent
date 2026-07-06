"""0037: Phase 1 — drop ``correlation_id`` server_default on
``orchestration_run_attempts``.

Revision ID: 0037_phase1_drop_correlation_id_default
Revises: 0036_phase1_identity_foundation_remediation
Create Date: 2026-07-05

This is a **P0-2 remediation** that closes the remaining
application-layer gap flagged in the round 11 independent
engineering review.

Contract
========

Migration 0036 already performed two of the three contract steps
required for ``orchestration_run_attempts.correlation_id``:

* 0036 step 1 — backfilled any NULL / empty / whitespace-only
  ``correlation_id`` row with the explicit sentinel
  ``"legacy-migration-0036"`` (preserves the NOT NULL invariant
  without faking a real correlation identifier).
* 0036 step 3 — added the portable
  ``ck_attempt_correlation_id_nonempty`` CHECK
  (``length(trim(correlation_id)) > 0``) on both SQLite and
  PostgreSQL. Empty / whitespace-only writes now fail with
  ``IntegrityError``.

The third step is performed by **this** migration (0037): the
column-level ``server_default`` is **dropped** so the
application / repository layer MUST supply ``correlation_id``
explicitly on every future write. A write that omits it now
fails with ``IntegrityError`` (NOT NULL) — this is the
desired fail-closed behavior.

This migration does NOT change the meaning of the legacy
sentinel. ``"legacy-migration-0036"`` is reserved for
backfilled pre-0036 rows; new writes that try to mint a
"fake" correlation_id by relying on the default are no longer
able to do so. Runtime / repository code paths must mint a
real correlation identifier (e.g. ``attempt-corr:<uuid>`` per
the existing 0035 design contract) and pass it explicitly.

Scope discipline
================

This migration is **non-destructive** for already-running
deployments:

* It does NOT change column types.
* It does NOT drop or rename existing columns.
* It does NOT alter the unique index
  ``uq_attempt_idempotency_key_db``.
* It does NOT alter the existing CHECK constraints
  ``ck_attempt_database_backend``,
  ``ck_attempt_actor_principal_type``,
  ``ck_scheme_run_database_backend``,
  ``ck_scheme_run_source_mode_nullity``,
  ``uq_attempt_one_running``,
  ``uq_attempt_identity_number``.
* It does NOT remove the
  ``ck_attempt_correlation_id_nonempty`` CHECK added in 0036.
* The existing backfill (0036 step 1) means every row in
  ``orchestration_run_attempts`` already carries a
  ``correlation_id`` value, so dropping the column default
  does not surface any NULL/empty rows.

Downgrade safety
================

The ``downgrade()`` function restores the
``server_default="legacy-migration-0036"`` default that
0036 installed. The restoration does NOT change any existing
row values — the existing rows retain their explicit
correlation_id (either the legacy sentinel for backfilled
rows or a real minted value for new rows).

If a future operator chooses to downgrade 0037 → 0036, the
opposite-state default is re-installed, but no row values are
mutated. The portable CHECK
``ck_attempt_correlation_id_nonempty`` remains in place
throughout (it is owned by 0036, not 0037).

Dialect dispatch
================

* SQLite: uses ``op.batch_alter_table`` to drop the
  column-level default while preserving the constraint
  names through the copy-and-move rewrite.
* PostgreSQL: uses raw ``ALTER TABLE ... ALTER COLUMN ...
  DROP DEFAULT`` to drop the column-level default.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_phase1_drop_correlation_id_default"
down_revision: str | None = "0036_phase1_identity_foundation_remediation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── Invariant constants ──────────────────────────────────────────

# Sentinel for legacy rows whose correlation_id was originally
# empty / NULL / whitespace-only. 0037 re-installs this as the
# server_default on downgrade; 0036 owns the only valid
# historical use of this sentinel.
CORRELATION_ID_LEGACY_SENTINEL: str = "legacy-migration-0036"

# Column and table names.
COL_CORRELATION_ID: str = "correlation_id"
TBL_ORCH_ATTEMPTS: str = "orchestration_run_attempts"


def upgrade() -> None:
    dialect = op.get_context().dialect.name

    # Drop the column-level server_default so future writes
    # must provide correlation_id explicitly. On SQLite this
    # requires batch_alter_table to preserve the column-level
    # default constraint. On PostgreSQL, native
    # ALTER ... DROP DEFAULT works.
    if dialect == "sqlite":
        with op.batch_alter_table(TBL_ORCH_ATTEMPTS) as batch_op:
            batch_op.alter_column(COL_CORRELATION_ID, server_default=None)
    else:
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_ORCH_ATTEMPTS} ALTER COLUMN {COL_CORRELATION_ID} DROP DEFAULT"
            )
        )


def downgrade() -> None:
    dialect = op.get_context().dialect.name

    # Restore the column-level server_default to the legacy
    # sentinel that 0036 installed. This is the only behavior
    # 0036 has when downgraded to 0035; 0037's downgrade keeps
    # the column-level default for parity with the 0036
    # state. No row values are mutated.
    if dialect == "sqlite":
        with op.batch_alter_table(TBL_ORCH_ATTEMPTS) as batch_op:
            batch_op.alter_column(
                COL_CORRELATION_ID,
                server_default=CORRELATION_ID_LEGACY_SENTINEL,
            )
    else:
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_ORCH_ATTEMPTS} "
                f"ALTER COLUMN {COL_CORRELATION_ID} "
                f"SET DEFAULT '{CORRELATION_ID_LEGACY_SENTINEL}'"
            )
        )
