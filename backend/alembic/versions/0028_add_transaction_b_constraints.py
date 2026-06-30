"""Add Transaction B database constraints.

Revision ID: 0028_add_transaction_b_constraints
Revises: 0027_separate_requested_and_resolved_request_identity
Create Date: 2026-06-30

Adds:
- ``orchestration_fingerprint`` column to ``calculation_runs``
  with ``ck_calculation_run_fingerprint_nullity`` CHECK
- ``uq_calculation_run_attempt_type`` UNIQUE on
  ``(orchestration_run_attempt_id, calculation_type)``
- ``ck_source_binding_slot_distinct`` CHECK on
  ``orchestration_source_bindings`` ensuring the 5 slot IDs are
  pairwise distinct
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_add_transaction_b_constraints"
down_revision: str | None = "0027_separate_requested_and_resolved_request_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── SourceBinding slot-distinct CHECK ──────────────────────────────────────
# All 10 pairwise comparisons of the 5 slot columns.

_SLOT_COLUMNS = (
    "zone_calculation_id",
    "cooling_load_calculation_id",
    "equipment_calculation_id",
    "power_calculation_id",
    "investment_calculation_id",
)

_SLOT_DISTINCT_CLAUSES = []
for _i in range(len(_SLOT_COLUMNS)):
    for _j in range(_i + 1, len(_SLOT_COLUMNS)):
        _SLOT_DISTINCT_CLAUSES.append(
            f"{_SLOT_COLUMNS[_i]} != {_SLOT_COLUMNS[_j]}"
        )

_SLOT_DISTINCT_CHECK = " AND ".join(_SLOT_DISTINCT_CLAUSES)


# ── Fingerprint nullity CHECK ─────────────────────────────────────────────
# Legacy (all orchestration columns NULL) → fingerprint must be NULL.
# Orchestrated (orchestration_identity_id NOT NULL) → fingerprint NOT NULL.

_FINGERPRINT_NULLITY_CHECK = (
    "(orchestration_identity_id IS NULL"
    " AND orchestration_fingerprint IS NULL)"
    " OR (orchestration_identity_id IS NOT NULL"
    " AND orchestration_fingerprint IS NOT NULL)"
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
    # 1. Add orchestration_fingerprint column
    op.add_column(
        "calculation_runs",
        sa.Column("orchestration_fingerprint", sa.String(128), nullable=True),
    )

    # 2. Update the existing orchestration nullity CHECK to include fingerprint
    op.drop_constraint(
        "ck_calculation_run_orchestration_nullity", "calculation_runs", type_="check"
    )
    op.create_check_constraint(
        "ck_calculation_run_orchestration_nullity",
        "calculation_runs",
        sa.text(_UPDATED_ORCHESTRATION_NULLITY_CHECK),
    )

    # 3. Add fingerprint nullity CHECK
    op.create_check_constraint(
        "ck_calculation_run_fingerprint_nullity",
        "calculation_runs",
        sa.text(_FINGERPRINT_NULLITY_CHECK),
    )

    # 4. Add UNIQUE on (orchestration_run_attempt_id, calculation_type)
    op.create_unique_constraint(
        "uq_calculation_run_attempt_type",
        "calculation_runs",
        ["orchestration_run_attempt_id", "calculation_type"],
    )

    # 5. Add SourceBinding slot-distinct CHECK
    op.create_check_constraint(
        "ck_source_binding_slot_distinct",
        "orchestration_source_bindings",
        sa.text(_SLOT_DISTINCT_CHECK),
    )


def _pg_downgrade() -> None:
    # 5. Drop SourceBinding slot-distinct CHECK
    op.drop_constraint(
        "ck_source_binding_slot_distinct",
        "orchestration_source_bindings",
        type_="check",
    )

    # 4. Drop UNIQUE
    op.drop_constraint(
        "uq_calculation_run_attempt_type", "calculation_runs", type_="unique"
    )

    # 3. Drop fingerprint nullity CHECK
    op.drop_constraint(
        "ck_calculation_run_fingerprint_nullity", "calculation_runs", type_="check"
    )

    # 2. Restore the original orchestration nullity CHECK (without fingerprint)
    op.drop_constraint(
        "ck_calculation_run_orchestration_nullity", "calculation_runs", type_="check"
    )
    op.create_check_constraint(
        "ck_calculation_run_orchestration_nullity",
        "calculation_runs",
        sa.text(_ORIGINAL_ORCHESTRATION_NULLITY_CHECK),
    )

    # 1. Drop column
    op.drop_column("calculation_runs", "orchestration_fingerprint")


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_upgrade() -> None:
    # 1. Add column via batch mode
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.add_column(
            sa.Column("orchestration_fingerprint", sa.String(128), nullable=True)
        )

    # 2. Replace orchestration nullity CHECK (drop old, add updated)
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_constraint(
            "ck_calculation_run_orchestration_nullity", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_calculation_run_orchestration_nullity",
            sa.text(_UPDATED_ORCHESTRATION_NULLITY_CHECK),
        )

    # 3. Add fingerprint nullity CHECK
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.create_check_constraint(
            "ck_calculation_run_fingerprint_nullity",
            sa.text(_FINGERPRINT_NULLITY_CHECK),
        )

    # 4. Add UNIQUE
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_calculation_run_attempt_type",
            ["orchestration_run_attempt_id", "calculation_type"],
        )

    # 5. Add SourceBinding slot-distinct CHECK
    with op.batch_alter_table("orchestration_source_bindings") as batch_op:
        batch_op.create_check_constraint(
            "ck_source_binding_slot_distinct",
            sa.text(_SLOT_DISTINCT_CHECK),
        )


def _sqlite_downgrade() -> None:
    # 5. Drop SourceBinding slot-distinct CHECK
    with op.batch_alter_table("orchestration_source_bindings") as batch_op:
        batch_op.drop_constraint("ck_source_binding_slot_distinct", type_="check")

    # 4. Drop UNIQUE
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_constraint("uq_calculation_run_attempt_type", type_="unique")

    # 3. Drop fingerprint nullity CHECK
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_constraint(
            "ck_calculation_run_fingerprint_nullity", type_="check"
        )

    # 2. Restore the original orchestration nullity CHECK (without fingerprint)
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_constraint(
            "ck_calculation_run_orchestration_nullity", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_calculation_run_orchestration_nullity",
            sa.text(_ORIGINAL_ORCHESTRATION_NULLITY_CHECK),
        )

    # 1. Drop column
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_column("orchestration_fingerprint")


# ── CHECK definitions ──────────────────────────────────────────────────────


_ORIGINAL_ORCHESTRATION_NULLITY_CHECK = (
    "(orchestration_identity_id IS NULL"
    " AND orchestration_run_attempt_id IS NULL"
    " AND execution_snapshot_id IS NULL"
    " AND coefficient_context_id IS NULL"
    " AND input_hash IS NULL"
    " AND result_hash IS NULL"
    " AND provenance IS NULL"
    " AND schema_version IS NULL"
    " AND calculation_type IS NULL)"
    " OR (orchestration_identity_id IS NOT NULL"
    " AND orchestration_run_attempt_id IS NOT NULL"
    " AND execution_snapshot_id IS NOT NULL"
    " AND coefficient_context_id IS NOT NULL"
    " AND input_hash IS NOT NULL"
    " AND result_hash IS NOT NULL"
    " AND provenance IS NOT NULL"
    " AND schema_version IS NOT NULL"
    " AND calculation_type IS NOT NULL)"
)


_UPDATED_ORCHESTRATION_NULLITY_CHECK = (
    "(orchestration_identity_id IS NULL"
    " AND orchestration_run_attempt_id IS NULL"
    " AND execution_snapshot_id IS NULL"
    " AND coefficient_context_id IS NULL"
    " AND input_hash IS NULL"
    " AND result_hash IS NULL"
    " AND provenance IS NULL"
    " AND schema_version IS NULL"
    " AND calculation_type IS NULL"
    " AND orchestration_fingerprint IS NULL)"
    " OR (orchestration_identity_id IS NOT NULL"
    " AND orchestration_run_attempt_id IS NOT NULL"
    " AND execution_snapshot_id IS NOT NULL"
    " AND coefficient_context_id IS NOT NULL"
    " AND input_hash IS NOT NULL"
    " AND result_hash IS NOT NULL"
    " AND provenance IS NOT NULL"
    " AND schema_version IS NOT NULL"
    " AND calculation_type IS NOT NULL"
    " AND orchestration_fingerprint IS NOT NULL)"
)
