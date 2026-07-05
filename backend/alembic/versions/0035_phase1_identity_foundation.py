"""0035: Task 11B Phase 1 — schema and identity foundation.

Revision ID: 0035_phase1_identity_foundation
Revises: 0034_add_production_source_archives
Create Date: 2026-07-05

Phase 1 of the production calculation orchestration path
(design authority: docs/tasks/TASK-011B-production-calculation-
orchestration-prerequisite.md — Frozen Contract Authority SHA
ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2, merged to main via
PR #36 / merge commit 4285a9dfa298a35078fe9f7a1693ac3fc07c9077).

Phase 1 is **schema-only / identity-foundation only**. It does
NOT implement the orchestrator, SchemeService.run, SourceBinding
generation, calculator adapters, or coefficient governance —
those are separate phases with separate authorizations.

Schema delta
------------

A. Table ``orchestration_run_attempts`` — adds five columns
   required by the design contract §4.4 (actor / correlation_id
   / idempotency key / database backend identity / scheme_run_id):

   1. ``idempotency_key`` (String(128), nullable=True)
      — Unique per (database_backend, idempotency_key) via a
        unique index named ``uq_attempt_idempotency_key_db``.
        Nullable because historical rows (pre-Phase-1) carry
        NULL; new writes require a non-null value at the
        application layer (see §3 below).
   2. ``database_backend`` (String(32), nullable=False,
        server_default="sqlite")
      — Records which backend persisted the attempt. Supports
        SQLite / PostgreSQL parity. CHECK constraint enforces
        ``database_backend IN ('sqlite', 'postgresql')``.
   3. ``correlation_id`` (String(128), nullable=False,
        server_default="")
      — Carries the actor's correlation identifier. NOT NULL by
        pre-Phase-1 invariant — server_default="\" preserves
        schema additions without breaking legacy rows.
   4. ``actor_principal_type`` (String(32), nullable=False,
        server_default="user")
      — Enum-like: ``user`` | ``service``. Enforced by CHECK
        constraint.
   5. ``scheme_run_id`` (String(36), nullable=True,
        FK scheme_runs.id)
      — Final association with the SchemeRun that the
        orchestrator will write at runtime. The FK uses
        ``use_alter`` to avoid creating a forward dependency
        between attempt creation and SchemeRun creation,
        matching the existing pattern for
        ``source_binding_id``.

B. Table ``scheme_runs`` — adds two columns required by the
   design contract §5 and §8 (canonical envelope persistence):

   1. ``frozen_envelope`` (JSON, nullable=True)
      — Carries the canonical ``SourceSnapshotContentV1`` JSON
        bundle of the five ``ResultSnapshotV1`` payloads
        (with byte-for-byte stable ordering). Nullable for
        historical rows. SQLite uses JSON; PostgreSQL uses
        JSONB. The application layer is responsible for
        canonicalization (see design contract §8).
   2. ``database_backend`` (String(32), nullable=False,
        server_default="sqlite")
      — Records which backend the SchemeRun was persisted
        from. Same enum / CHECK as for orchestration attempts.

Downgrade safety
----------------

The downgrade() function performs a Python-side preflight
**before** any DROP COLUMN. Because all new columns are nullable
or have safe server defaults, downgrade should always be safe at
the schema level; however, the preflight verifies that no
orchestration_run_attempt row has a non-null ``scheme_run_id``
(which would silently break the cross-table link if the FK were
dropped) and that no scheme_run row has a non-null
``frozen_envelope`` (which would silently invalidate Phase 1's
identity contract). If any row violates this, downgrade aborts
with a RuntimeError. This mirrors the safety pattern in 0034.

The two new CHECK constraints (``database_backend`` enum) are
named to remain stable across SQLite and PostgreSQL so migration
tests can assert them deterministically.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035_phase1_identity_foundation"
down_revision: str | None = "0034_add_production_source_archives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── Invariant constants ──────────────────────────────────────────

# Database backend enum (single source of truth shared by both
# orchestrator attempts and scheme runs; CHECK constraints on
# both tables pin the same vocabulary).
DB_BACKEND_ENUM: tuple[str, ...] = ("sqlite", "postgresql")

# Actor principal type enum.
ACTOR_PRINCIPAL_TYPE_ENUM: tuple[str, ...] = ("user", "service")

# Unique-index name for (database_backend, idempotency_key) on
# orchestration_run_attempts. Pinned so migration tests can
# reference it deterministically.
UQ_ATTEMPT_IDEMPOTENCY_KEY_DB: str = "uq_attempt_idempotency_key_db"

# Column names (for downgrade preflight and test assertions).
COL_IDEMPOTENCY_KEY: str = "idempotency_key"
COL_DATABASE_BACKEND_ATTEMPT: str = "database_backend"
COL_CORRELATION_ID: str = "correlation_id"
COL_ACTOR_PRINCIPAL_TYPE: str = "actor_principal_type"
COL_SCHEME_RUN_ID: str = "scheme_run_id"

COL_FROZEN_ENVELOPE: str = "frozen_envelope"
COL_DATABASE_BACKEND_SCHEME: str = "database_backend"


def _db_backend_enum_clause(column_name: str) -> str:
    """Return a SQLite/PostgreSQL-portable CHECK clause for the
    database_backend enum.
    """
    joined = ", ".join(f"'{name}'" for name in DB_BACKEND_ENUM)
    return f"{column_name} IN ({joined})"


def _actor_principal_type_enum_clause(column_name: str) -> str:
    """Return a SQLite/PostgreSQL-portable CHECK clause for the
    actor_principal_type enum.
    """
    joined = ", ".join(f"'{name}'" for name in ACTOR_PRINCIPAL_TYPE_ENUM)
    return f"{column_name} IN ({joined})"


def upgrade() -> None:
    dialect = op.get_context().dialect.name

    # ── A. orchestration_run_attempts ──────────────────────────
    # Use raw add_column (works on both SQLite and PostgreSQL)
    # rather than batch_alter_table — batch mode on SQLite uses
    # copy-and-move and rejects CREATE CONSTRAINT inline.
    op.add_column(
        "orchestration_run_attempts",
        sa.Column(COL_IDEMPOTENCY_KEY, sa.String(length=128), nullable=True),
    )
    op.add_column(
        "orchestration_run_attempts",
        sa.Column(
            COL_DATABASE_BACKEND_ATTEMPT,
            sa.String(length=32),
            nullable=False,
            server_default="sqlite",
        ),
    )
    op.add_column(
        "orchestration_run_attempts",
        sa.Column(
            COL_CORRELATION_ID,
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "orchestration_run_attempts",
        sa.Column(
            COL_ACTOR_PRINCIPAL_TYPE,
            sa.String(length=32),
            nullable=False,
            server_default="user",
        ),
    )
    op.add_column(
        "orchestration_run_attempts",
        sa.Column(COL_SCHEME_RUN_ID, sa.String(length=36), nullable=True),
    )

    # CHECK on database_backend enum
    # SQLite (via batch_alter_table) and PostgreSQL (raw ALTER) both
    # support ``ADD CONSTRAINT <name> CHECK (...)`` — but the
    # table-rewrite mode used by SQLite's batch does NOT honor the
    # constraint NAMES the DDL declares; the new CHECK is registered
    # by its raw clause, with a synthetic handle. We therefore use
    # ``op.create_check_constraint`` only on PostgreSQL (native ALTER)
    # and rely on SQLite's batch_alter_table for SQLite.
    if dialect == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE orchestration_run_attempts "
                f"ADD CONSTRAINT ck_attempt_database_backend "
                f"CHECK ({_db_backend_enum_clause(COL_DATABASE_BACKEND_ATTEMPT)})"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE orchestration_run_attempts "
                f"ADD CONSTRAINT ck_attempt_actor_principal_type "
                f"CHECK ({_actor_principal_type_enum_clause(COL_ACTOR_PRINCIPAL_TYPE)})"
            )
        )
    # NOTE: ck_scheme_run_database_backend is added AFTER the
    # scheme_runs.database_backend column is created further below.

    # Unique index on (database_backend, idempotency_key)
    op.create_index(
        UQ_ATTEMPT_IDEMPOTENCY_KEY_DB,
        "orchestration_run_attempts",
        [COL_DATABASE_BACKEND_ATTEMPT, COL_IDEMPOTENCY_KEY],
        unique=True,
    )

    # FK to scheme_runs.id.
    # SQLite does not support op.create_foreign_key without
    # batch_alter_table; PostgreSQL accepts raw ALTER.
    if dialect == "sqlite":
        with op.batch_alter_table("orchestration_run_attempts") as batch_op:
            batch_op.create_foreign_key(
                "fk_attempt_scheme_run",
                "scheme_runs",
                [COL_SCHEME_RUN_ID],
                ["id"],
                use_alter=True,
            )
    else:
        op.create_foreign_key(
            "fk_attempt_scheme_run",
            "orchestration_run_attempts",
            "scheme_runs",
            [COL_SCHEME_RUN_ID],
            ["id"],
            use_alter=True,
        )

    # ── B. scheme_runs ─────────────────────────────────────────
    # Frozen envelope column: JSONB on PostgreSQL, JSON on SQLite.
    # SQLAlchemy render must produce dialect-correct DDL; we use
    # sa.JSON() with the postgresql_with_variant() which works in
    # the SQL generated by alembic's op.add_column.
    if dialect == "postgresql":
        op.add_column(
            "scheme_runs",
            sa.Column(
                COL_FROZEN_ENVELOPE,
                sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                nullable=True,
            ),
        )
    else:
        op.add_column(
            "scheme_runs",
            sa.Column(COL_FROZEN_ENVELOPE, sa.JSON(), nullable=True),
        )

    op.add_column(
        "scheme_runs",
        sa.Column(
            COL_DATABASE_BACKEND_SCHEME,
            sa.String(length=32),
            nullable=False,
            server_default="sqlite",
        ),
    )

    # PostgreSQL: native ALTER for the CHECK constraint. SQLite
    # registers the inline CHECK through batch_alter_table below
    # (after the add_column batch completes) — not at this point,
    # because SQLite's batch mode is mid-table-rewrite here.
    if dialect == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE scheme_runs "
                f"ADD CONSTRAINT ck_scheme_run_database_backend "
                f"CHECK ({_db_backend_enum_clause(COL_DATABASE_BACKEND_SCHEME)})"
            )
        )

    # CHECK on scheme_runs.database_backend + the SQLite-only
    # CK constraints for orchestration_run_attempts above.
    # We rely on SQLite's batch_alter_table; PostgreSQL handled
    # the orchestration_run_attempts CHECKs above via raw ALTER.
    if dialect == "sqlite":
        # SQLite: add CHECK constraints via batch_alter_table for
        # orchestration_run_attempts (deferred from above) and
        # for scheme_runs. batch_alter_table on SQLite copies and
        # recreates the table; the new table carries its own CHECK
        # constraints whose NAMES are preserved in the schema.
        with op.batch_alter_table("orchestration_run_attempts") as batch_op:
            batch_op.create_check_constraint(
                "ck_attempt_database_backend",
                _db_backend_enum_clause(COL_DATABASE_BACKEND_ATTEMPT),
            )
            batch_op.create_check_constraint(
                "ck_attempt_actor_principal_type",
                _actor_principal_type_enum_clause(COL_ACTOR_PRINCIPAL_TYPE),
            )
        with op.batch_alter_table("scheme_runs") as batch_op:
            batch_op.create_check_constraint(
                "ck_scheme_run_database_backend",
                _db_backend_enum_clause(COL_DATABASE_BACKEND_SCHEME),
            )


def _downgrade_preflight_attempt_has_scheme_run_ref() -> None:
    """Refuse to drop scheme_run_id if any row currently references
    a SchemeRun. The application contract from Phase 1 onwards
    relies on this FK to thread the attempt ↔ SchemeRun link.

    Splits the inspection between SQLite and PostgreSQL via a
    dialect-portable query (the same SQL works on both).
    """
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM orchestration_run_attempts WHERE {COL_SCHEME_RUN_ID} IS NOT NULL"
        )
    ).scalar()
    if result and int(result) > 0:
        raise RuntimeError(
            f"downgrade aborted: {result} orchestration_run_attempt "
            f"row(s) have a non-null {COL_SCHEME_RUN_ID}; "
            "clear the column before downgrading 0035."
        )


def _downgrade_preflight_scheme_run_has_frozen_envelope() -> None:
    """Refuse to drop frozen_envelope if any scheme_runs row has
    a non-null envelope; that would silently invalidate the
    Phase 1 contract.
    """
    bind = op.get_bind()
    result = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM scheme_runs WHERE {COL_FROZEN_ENVELOPE} IS NOT NULL")
    ).scalar()
    if result and int(result) > 0:
        raise RuntimeError(
            f"downgrade aborted: {result} scheme_run row(s) have "
            f"a non-null {COL_FROZEN_ENVELOPE}; clear the column "
            "before downgrading 0035."
        )


def downgrade() -> None:
    # Preflight: refuse if any row depends on Phase 1 columns.
    _downgrade_preflight_attempt_has_scheme_run_ref()
    _downgrade_preflight_scheme_run_has_frozen_envelope()

    dialect = op.get_context().dialect.name

    # SQLite's dialect rejects ALTER CONSTRAINT (FK drop, CHECK drop)
    # outside batch_alter_table. PostgreSQL accepts raw ALTER TABLE …
    # DROP CONSTRAINT natively. We dispatch both.
    use_batch = dialect == "sqlite"

    # ── Drop FK first (constraint moves with the FK object) ──
    # FK on Postgres: native ALTER DROP CONSTRAINT works.
    # FK on SQLite: must go through batch_alter_table.
    if use_batch:
        with op.batch_alter_table("orchestration_run_attempts") as batch_op:
            batch_op.drop_constraint("fk_attempt_scheme_run", type_="foreignkey")
    else:
        op.drop_constraint(
            "fk_attempt_scheme_run",
            "orchestration_run_attempts",
            type_="foreignkey",
        )

    # ── B. scheme_runs reverse ─────────────────────────────────
    if use_batch:
        with op.batch_alter_table("scheme_runs") as batch_op:
            batch_op.drop_constraint("ck_scheme_run_database_backend", type_="check")
            batch_op.drop_column(COL_DATABASE_BACKEND_SCHEME)
            batch_op.drop_column(COL_FROZEN_ENVELOPE)
    else:
        op.execute(
            sa.text("ALTER TABLE scheme_runs DROP CONSTRAINT ck_scheme_run_database_backend")
        )
        op.drop_column("scheme_runs", COL_DATABASE_BACKEND_SCHEME)
        op.drop_column("scheme_runs", COL_FROZEN_ENVELOPE)

    # ── A. orchestration_run_attempts reverse ─────────────────
    op.drop_index(UQ_ATTEMPT_IDEMPOTENCY_KEY_DB, table_name="orchestration_run_attempts")

    if use_batch:
        with op.batch_alter_table("orchestration_run_attempts") as batch_op:
            batch_op.drop_constraint("ck_attempt_actor_principal_type", type_="check")
            batch_op.drop_constraint("ck_attempt_database_backend", type_="check")
            batch_op.drop_column(COL_SCHEME_RUN_ID)
            batch_op.drop_column(COL_ACTOR_PRINCIPAL_TYPE)
            batch_op.drop_column(COL_CORRELATION_ID)
            batch_op.drop_column(COL_DATABASE_BACKEND_ATTEMPT)
            batch_op.drop_column(COL_IDEMPOTENCY_KEY)
    else:
        op.execute(
            sa.text(
                "ALTER TABLE orchestration_run_attempts "
                "DROP CONSTRAINT ck_attempt_actor_principal_type"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE orchestration_run_attempts DROP CONSTRAINT ck_attempt_database_backend"
            )
        )
        op.drop_column("orchestration_run_attempts", COL_SCHEME_RUN_ID)
        op.drop_column("orchestration_run_attempts", COL_ACTOR_PRINCIPAL_TYPE)
        op.drop_column("orchestration_run_attempts", COL_CORRELATION_ID)
        op.drop_column("orchestration_run_attempts", COL_DATABASE_BACKEND_ATTEMPT)
        op.drop_column("orchestration_run_attempts", COL_IDEMPOTENCY_KEY)
