"""Add scheme run production provenance columns.

Revision ID: 0029_add_scheme_run_production_provenance
Revises: 0028_add_transaction_b_constraints
Create Date: 2026-07-01

Adds 16 provenance columns to ``scheme_runs`` and replaces the
``ck_scheme_run_source_mode_nullity`` CHECK constraint so that
production mode also requires the new fields to be NOT NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_add_scheme_run_production_provenance"
down_revision: str | None = "0028_add_transaction_b_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── New columns ─────────────────────────────────────────────────────────────

_NEW_COLUMNS = [
    ("binding_schema_version", sa.String(50)),
    ("execution_snapshot_id", sa.String(36)),
    ("coefficient_context_id", sa.String(36)),
    ("orchestration_identity_id", sa.String(36)),
    ("authoritative_attempt_id", sa.String(36)),
    ("orchestration_fingerprint", sa.String(128)),
    ("zone_calculation_id", sa.String(36)),
    ("cooling_load_calculation_id", sa.String(36)),
    ("equipment_calculation_id", sa.String(36)),
    ("power_calculation_id", sa.String(36)),
    ("investment_calculation_id", sa.String(36)),
    ("zone_result_hash", sa.String(128)),
    ("cooling_load_result_hash", sa.String(128)),
    ("equipment_result_hash", sa.String(128)),
    ("power_result_hash", sa.String(128)),
    ("investment_result_hash", sa.String(128)),
]

# ── CHECK constraint definitions ────────────────────────────────────────────

# Original: covers source_binding_id, source_contract_version, weight_set_*,
# combined_source_hash only.
_OLD_CHECK = (
    "(source_mode = 'legacy'"
    " AND source_binding_id IS NULL"
    " AND source_contract_version IS NULL"
    " AND weight_set_revision_id IS NULL"
    " AND weight_set_content_hash IS NULL"
    " AND weight_set_generator_compatibility_version IS NULL"
    " AND combined_source_hash IS NULL)"
    " OR"
    "(source_mode = 'production'"
    " AND source_binding_id IS NOT NULL"
    " AND source_contract_version IS NOT NULL"
    " AND weight_set_revision_id IS NOT NULL"
    " AND weight_set_content_hash IS NOT NULL"
    " AND weight_set_generator_compatibility_version IS NOT NULL"
    " AND combined_source_hash IS NOT NULL)"
)

# New: adds all 16 provenance columns.
_NEW_CHECK = (
    "(source_mode = 'legacy'"
    " AND source_binding_id IS NULL"
    " AND source_contract_version IS NULL"
    " AND weight_set_revision_id IS NULL"
    " AND weight_set_content_hash IS NULL"
    " AND weight_set_generator_compatibility_version IS NULL"
    " AND combined_source_hash IS NULL"
    " AND binding_schema_version IS NULL"
    " AND execution_snapshot_id IS NULL"
    " AND coefficient_context_id IS NULL"
    " AND orchestration_identity_id IS NULL"
    " AND authoritative_attempt_id IS NULL"
    " AND orchestration_fingerprint IS NULL"
    " AND zone_calculation_id IS NULL"
    " AND cooling_load_calculation_id IS NULL"
    " AND equipment_calculation_id IS NULL"
    " AND power_calculation_id IS NULL"
    " AND investment_calculation_id IS NULL"
    " AND zone_result_hash IS NULL"
    " AND cooling_load_result_hash IS NULL"
    " AND equipment_result_hash IS NULL"
    " AND power_result_hash IS NULL"
    " AND investment_result_hash IS NULL)"
    " OR"
    "(source_mode = 'production'"
    " AND source_binding_id IS NOT NULL"
    " AND source_contract_version IS NOT NULL"
    " AND weight_set_revision_id IS NOT NULL"
    " AND weight_set_content_hash IS NOT NULL"
    " AND weight_set_generator_compatibility_version IS NOT NULL"
    " AND combined_source_hash IS NOT NULL"
    " AND binding_schema_version IS NOT NULL"
    " AND execution_snapshot_id IS NOT NULL"
    " AND coefficient_context_id IS NOT NULL"
    " AND orchestration_identity_id IS NOT NULL"
    " AND authoritative_attempt_id IS NOT NULL"
    " AND orchestration_fingerprint IS NOT NULL"
    " AND zone_calculation_id IS NOT NULL"
    " AND cooling_load_calculation_id IS NOT NULL"
    " AND equipment_calculation_id IS NOT NULL"
    " AND power_calculation_id IS NOT NULL"
    " AND investment_calculation_id IS NOT NULL"
    " AND zone_result_hash IS NOT NULL"
    " AND cooling_load_result_hash IS NOT NULL"
    " AND equipment_result_hash IS NOT NULL"
    " AND power_result_hash IS NOT NULL"
    " AND investment_result_hash IS NOT NULL)"
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
    # 1. Add columns
    for col_name, col_type in _NEW_COLUMNS:
        op.add_column("scheme_runs", sa.Column(col_name, col_type, nullable=True))

    # 2. Replace CHECK constraint
    op.drop_constraint("ck_scheme_run_source_mode_nullity", "scheme_runs", type_="check")
    op.create_check_constraint(
        "ck_scheme_run_source_mode_nullity",
        "scheme_runs",
        sa.text(_NEW_CHECK),
    )


def _pg_downgrade() -> None:
    # 1. Restore old CHECK constraint
    op.drop_constraint("ck_scheme_run_source_mode_nullity", "scheme_runs", type_="check")
    op.create_check_constraint(
        "ck_scheme_run_source_mode_nullity",
        "scheme_runs",
        sa.text(_OLD_CHECK),
    )

    # 2. Drop columns
    for col_name, _ in _NEW_COLUMNS:
        op.drop_column("scheme_runs", col_name)


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_upgrade() -> None:
    # 1. Add columns via batch mode
    with op.batch_alter_table("scheme_runs") as batch_op:
        for col_name, col_type in _NEW_COLUMNS:
            batch_op.add_column(sa.Column(col_name, col_type, nullable=True))

    # 2. Replace CHECK constraint
    with op.batch_alter_table("scheme_runs") as batch_op:
        batch_op.drop_constraint("ck_scheme_run_source_mode_nullity", type_="check")
        batch_op.create_check_constraint(
            "ck_scheme_run_source_mode_nullity",
            sa.text(_NEW_CHECK),
        )


def _sqlite_downgrade() -> None:
    # 1. Restore old CHECK constraint
    with op.batch_alter_table("scheme_runs") as batch_op:
        batch_op.drop_constraint("ck_scheme_run_source_mode_nullity", type_="check")
        batch_op.create_check_constraint(
            "ck_scheme_run_source_mode_nullity",
            sa.text(_OLD_CHECK),
        )

    # 2. Drop columns
    with op.batch_alter_table("scheme_runs") as batch_op:
        for col_name, _ in _NEW_COLUMNS:
            batch_op.drop_column(col_name)
