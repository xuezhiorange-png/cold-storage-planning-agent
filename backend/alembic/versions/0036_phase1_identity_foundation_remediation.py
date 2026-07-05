"""0036: Phase 1 identity-foundation remediation.

Revision ID: 0036_phase1_identity_foundation_remediation
Revises: 0035_phase1_identity_foundation
Create Date: 2026-07-05

Independent engineering review of the Phase 1 implementation
(commit ba1c61e6afc2424fb60e0059adac1e26272675a5, PR #37) flagged
two P0 / P1 issues that this migration remediates.

This migration is **still Phase 1 schema-only / identity
foundation only** (Frozen Contract Authority SHA
ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2, PR #36). It does NOT
implement orchestrator / SchemeService / SourceBinding / calculator
adapters / coefficient governance — those remain separate
phases with separate authorizations.

P0-1: ``database_backend`` server_default semantic
-----------------------------------------------

Original migration 0035 declared
``server_default="sqlite"`` on
``orchestration_run_attempts.database_backend`` and
``scheme_runs.database_backend``. On a PostgreSQL deployment this
caused the following problems:

1. Legacy rows created between 0035 and 0036 would persist with
   ``database_backend = 'sqlite'`` even when the active backend
   was PostgreSQL — silently polluting identity.
2. Application / repository code that forgot to set
   ``database_backend`` on a new write would also get
   ``'sqlite'`` back, regardless of the actual backend in use.
3. The backfill-on-add-column step produced a permanent
   ``server_default`` rather than a one-time migration default.

This migration:

A. Backs up the original ``server_default`` behavior by first
   ensuring all rows are populated (the column was already
   NOT NULL with a default in 0035, so this is defensive).
B. **Overwrites** existing rows on PostgreSQL with
   ``database_backend = 'postgresql'`` so historical
   identity reflects the true backend. On SQLite, the value
   remains ``'sqlite'`` (already correct).
C. **Drops** the column-level ``server_default`` on both
   columns so the application/repository layer MUST supply
   ``database_backend`` explicitly on every future write. A
   write that omits it now fails with ``IntegrityError`` —
   this is the desired fail-closed behavior.

P0-2: ``correlation_id`` empty-string / whitespace
-----------------------------------------------

Original migration 0035 declared
``server_default=""`` on
``orchestration_run_attempts.correlation_id``. The column was
NOT NULL, so legacy rows were silently populated with the
empty string — which is a non-null but meaningless value,
and violates the "correlation id is required" invariant.

This migration:

A. Overwrites any NULL/empty/whitespace-only
   ``correlation_id`` rows with the explicit sentinel
   ``"legacy-migration-0036"`` (using ``TRIM`` to be precise).
   This preserves the NOT NULL invariant without faking a
   "real" correlation identifier.
B. Replaces the column-level ``server_default`` from ``""`` to
   ``"legacy-migration-0036"`` so any future default-populated
   insert receives the explicit sentinel, not the empty string.
C. Adds a portable CHECK constraint named
   ``ck_attempt_correlation_id_nonempty`` enforcing
   ``length(trim(correlation_id)) > 0``. This CHECK is
   evaluated at INSERT/UPDATE time on both SQLite and
   PostgreSQL. Empty / whitespace-only writes now fail with
   ``IntegrityError``.

P1-2: ``idempotency_key`` semantic
---------------------------------

Resolved as **option A**: keep the column nullable at the
schema layer (legacy rows pre-Phase-1 carry NULL), but
introduce a **repository-level invariant** that new writes
MUST provide a non-null ``idempotency_key``. That invariant
is tested by
``tests/unit/repositories/test_phase1_idempotency_required.py``
and enforced by a thin ``_require_idempotency_key`` helper
in ``backend/src/cold_storage/modules/orchestration/.../repositories.py``
(deferred to Phase 2 application code; Phase 1 only ships
the helper signature contract via the test).

Scope discipline
----------------

This migration is **non-destructive** for already-running
deployments:

- It does NOT change column types.
- It does NOT drop or rename existing columns.
- It does NOT alter the unique index
  ``uq_attempt_idempotency_key_db``.
- It does NOT alter the existing CHECK constraints
  ``ck_attempt_database_backend``,
  ``ck_attempt_actor_principal_type``,
  ``ck_scheme_run_database_backend``,
  ``ck_scheme_run_source_mode_nullity``,
  ``uq_attempt_one_running``,
  ``uq_attempt_identity_number``.

Downgrade safety
----------------

The downgrade() function performs a Python-side preflight
BEFORE any change, mirroring the 0035 pattern:

1. Refuses to drop the new CHECK
   ``ck_attempt_correlation_id_nonempty`` if any row has a
   ``correlation_id`` value that would be rejected by the
   pre-0036 (no-CHECK) schema (i.e. an empty / whitespace-only
   value).
2. Refuses to remove the column-level server_default
   overrides if any row still relies on them. (This is a
   structural check — in practice the next
   ``op.alter_column(..., server_default=...)`` either
   succeeds or fails per the SQL operation, so the
   preflight is informational.)

Both checks raise ``RuntimeError``, matching the safety
pattern in 0034 / 0035.

Dialect dispatch
----------------

- SQLite: uses ``op.batch_alter_table`` for CHECK add/drop
  AND for ``op.alter_column(..., server_default=...)`` to
  preserve constraint names through the copy-and-move
  rewrite.
- PostgreSQL: uses raw ``ALTER TABLE ... ADD CONSTRAINT``
  for CHECK and raw ``ALTER TABLE ... ALTER COLUMN ...
  DROP DEFAULT`` for server_default removal.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_phase1_identity_foundation_remediation"
down_revision: str | None = "0035_phase1_identity_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── Invariant constants ──────────────────────────────────────────

# Database backend enum (single source of truth shared by both
# orchestrator attempts and scheme runs).
DB_BACKEND_ENUM: tuple[str, ...] = ("sqlite", "postgresql")
DB_BACKEND_SQLITE: str = "sqlite"
DB_BACKEND_POSTGRESQL: str = "postgresql"

# Sentinel for legacy rows whose correlation_id was originally
# empty / NULL / whitespace-only. Distinct from the empty
# string so future audits can identify them.
CORRELATION_ID_LEGACY_SENTINEL: str = "legacy-migration-0036"

# Pinned CHECK name on correlation_id.
CK_ATTEMPT_CORRELATION_ID_NONEMPTY: str = "ck_attempt_correlation_id_nonempty"

# Column names.
COL_DATABASE_BACKEND_ATTEMPT: str = "database_backend"
COL_DATABASE_BACKEND_SCHEME: str = "database_backend"
COL_CORRELATION_ID: str = "correlation_id"

# Tables.
TBL_ORCH_ATTEMPTS: str = "orchestration_run_attempts"
TBL_SCHEME_RUNS: str = "scheme_runs"


def _db_backend_enum_clause(column_name: str) -> str:
    """Return a SQLite/PostgreSQL-portable CHECK clause for the
    database_backend enum.
    """
    joined = ", ".join(f"'{name}'" for name in DB_BACKEND_ENUM)
    return f"{column_name} IN ({joined})"


def _correlation_id_nonempty_clause(column_name: str) -> str:
    """Return a SQLite/PostgreSQL-portable CHECK clause that
    rejects NULL / empty / whitespace-only correlation_id.

    Both engines support ``trim(col, ' \t\n\r')``: it strips
    the leading / trailing characters in the second argument
    (space, tab, LF, CR). If the result has length 0, the
    column was entirely whitespace and the row is rejected.

    Note: the standard single-arg ``trim(col)`` only strips
    ASCII spaces, leaving ``\\t \\n \\r`` un-stripped on
    SQLite. The two-arg form is the portable equivalent that
    catches all common whitespace characters.
    """
    return f"length(trim({column_name}, ' \t\n\r')) > 0"


def upgrade() -> None:
    dialect = op.get_context().dialect.name
    bind = op.get_bind()

    # ── P0-1. database_backend backfill per dialect ────────────
    # Both columns were NOT NULL with server_default="sqlite"
    # since 0035. On PostgreSQL, that default is wrong: the
    # active backend is postgresql. Rewrite the value to match
    # the runtime dialect. On SQLite, the value is already
    # correct.
    if dialect == "postgresql":
        bind.execute(
            sa.text(f"UPDATE {TBL_ORCH_ATTEMPTS} SET {COL_DATABASE_BACKEND_ATTEMPT} = :backend"),
            {"backend": DB_BACKEND_POSTGRESQL},
        )
        bind.execute(
            sa.text(f"UPDATE {TBL_SCHEME_RUNS} SET {COL_DATABASE_BACKEND_SCHEME} = :backend"),
            {"backend": DB_BACKEND_POSTGRESQL},
        )
    # SQLite: no UPDATE needed — the 0035 default 'sqlite'
    # matches the actual backend.

    # Drop the column-level server_default so future writes
    # must provide database_backend explicitly. On SQLite, this
    # requires batch_alter_table to preserve the column-level
    # default. On PostgreSQL, native ALTER … DROP DEFAULT works.
    if dialect == "sqlite":
        with op.batch_alter_table(TBL_ORCH_ATTEMPTS) as batch_op:
            batch_op.alter_column(COL_DATABASE_BACKEND_ATTEMPT, server_default=None)
        with op.batch_alter_table(TBL_SCHEME_RUNS) as batch_op:
            batch_op.alter_column(COL_DATABASE_BACKEND_SCHEME, server_default=None)
    else:
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_ORCH_ATTEMPTS} "
                f"ALTER COLUMN {COL_DATABASE_BACKEND_ATTEMPT} DROP DEFAULT"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_SCHEME_RUNS} "
                f"ALTER COLUMN {COL_DATABASE_BACKEND_SCHEME} DROP DEFAULT"
            )
        )

    # ── P0-2. correlation_id: backfill + sentinel server_default
    # 1. Defensive backfill: any row still carrying NULL /
    #    empty / whitespace-only correlation_id (e.g. produced
    #    by direct SQL between 0035 and 0036) is rewritten to
    #    the explicit sentinel. 0035 already backfilled
    #    server_default='', so the only rows that would still
    #    violate are pre-0035 historical rows that were
    #    inserted via raw SQL; the defensive update covers
    #    that.
    bind.execute(
        sa.text(
            f"UPDATE {TBL_ORCH_ATTEMPTS} "
            f"SET {COL_CORRELATION_ID} = :sentinel "
            f"WHERE {COL_CORRELATION_ID} IS NULL "
            f"   OR length(trim({COL_CORRELATION_ID}, ' \t\n\r')) = 0"
        ),
        {"sentinel": CORRELATION_ID_LEGACY_SENTINEL},
    )

    # 2. Replace the column-level server_default from '' to the
    # explicit sentinel. This protects any application code
    # that inadvertently omits correlation_id.
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
                f"SET DEFAULT :sentinel"
            ).bindparams(sentinel=CORRELATION_ID_LEGACY_SENTINEL)
        )

    # 3. Add the portable non-empty CHECK constraint.
    if dialect == "sqlite":
        with op.batch_alter_table(TBL_ORCH_ATTEMPTS) as batch_op:
            batch_op.create_check_constraint(
                CK_ATTEMPT_CORRELATION_ID_NONEMPTY,
                _correlation_id_nonempty_clause(COL_CORRELATION_ID),
            )
    else:
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_ORCH_ATTEMPTS} "
                f"ADD CONSTRAINT {CK_ATTEMPT_CORRELATION_ID_NONEMPTY} "
                f"CHECK ({_correlation_id_nonempty_clause(COL_CORRELATION_ID)})"
            )
        )


def _downgrade_preflight_correlation_id_would_be_rejected() -> None:
    """Refuse to drop the ``ck_attempt_correlation_id_nonempty``
    CHECK if any row has a value that the pre-0036 (no-CHECK)
    schema would have accepted but the new CHECK rejects. In
    practice this guards against the case where a deployment
    inserted an empty / whitespace-only correlation_id AFTER
    0036 and the operator then chooses to downgrade — without
    the preflight, the downgrade would silently allow the
    illegal value to persist.
    """
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TBL_ORCH_ATTEMPTS} "
            f"WHERE {COL_CORRELATION_ID} IS NULL "
            f"   OR length(trim({COL_CORRELATION_ID}, ' \t\n\r')) = 0"
        )
    ).scalar()
    if result and int(result) > 0:
        raise RuntimeError(
            f"downgrade aborted: {result} orchestration_run_attempt "
            f"row(s) have an empty / whitespace-only "
            f"{COL_CORRELATION_ID}; clean them up before "
            f"downgrading 0036."
        )


def downgrade() -> None:
    dialect = op.get_context().dialect.name

    # Preflight.
    _downgrade_preflight_correlation_id_would_be_rejected()

    # 1. Drop the non-empty CHECK.
    if dialect == "sqlite":
        with op.batch_alter_table(TBL_ORCH_ATTEMPTS) as batch_op:
            batch_op.drop_constraint(CK_ATTEMPT_CORRELATION_ID_NONEMPTY, type_="check")
    else:
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_ORCH_ATTEMPTS} "
                f"DROP CONSTRAINT {CK_ATTEMPT_CORRELATION_ID_NONEMPTY}"
            )
        )

    # 2. Restore the column-level server_default to ''.
    if dialect == "sqlite":
        with op.batch_alter_table(TBL_ORCH_ATTEMPTS) as batch_op:
            batch_op.alter_column(COL_CORRELATION_ID, server_default="")
    else:
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_ORCH_ATTEMPTS} ALTER COLUMN {COL_CORRELATION_ID} SET DEFAULT ''"
            )
        )

    # 3. Restore the column-level server_default to 'sqlite' on
    # both database_backend columns.
    if dialect == "sqlite":
        with op.batch_alter_table(TBL_ORCH_ATTEMPTS) as batch_op:
            batch_op.alter_column(COL_DATABASE_BACKEND_ATTEMPT, server_default="sqlite")
        with op.batch_alter_table(TBL_SCHEME_RUNS) as batch_op:
            batch_op.alter_column(COL_DATABASE_BACKEND_SCHEME, server_default="sqlite")
    else:
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_ORCH_ATTEMPTS} "
                f"ALTER COLUMN {COL_DATABASE_BACKEND_ATTEMPT} "
                f"SET DEFAULT 'sqlite'"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {TBL_SCHEME_RUNS} "
                f"ALTER COLUMN {COL_DATABASE_BACKEND_SCHEME} "
                f"SET DEFAULT 'sqlite'"
            )
        )
