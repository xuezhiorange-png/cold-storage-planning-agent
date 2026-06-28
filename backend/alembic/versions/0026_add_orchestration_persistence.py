"""Add orchestration persistence tables and extend existing entities.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "0026_add_orchestration_persistence"
down_revision: str | None = "0025_add_outbox_claim_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Orchestration Requests ──────────────────────────────────────────
    op.create_table(
        "orchestration_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "project_version_id",
            sa.String(36),
            sa.ForeignKey("project_versions.id"),
            nullable=False,
        ),
        sa.Column("request_fingerprint", sa.String(128), nullable=False, index=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("resolved_identity_id", sa.String(36), nullable=True),
        sa.Column("resolved_attempt_id", sa.String(36), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_field", sa.String(200), nullable=True),
        sa.Column("failure_details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Execution Snapshots ─────────────────────────────────────────────
    op.create_table(
        "orchestration_execution_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "project_version_id",
            sa.String(36),
            sa.ForeignKey("project_versions.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_snapshot_hash", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("captured_status", sa.String(50), nullable=False),
        sa.Column("captured_source_revision", sa.String(200), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_version_id",
            "input_snapshot_hash",
            "schema_version",
            name="uq_exec_snapshot_version_hash_schema",
        ),
    )

    # ── Coefficient Contexts ────────────────────────────────────────────
    op.create_table(
        "orchestration_coefficient_contexts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "project_version_id",
            sa.String(36),
            sa.ForeignKey("project_versions.id"),
            nullable=False,
        ),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_version_id",
            "content_hash",
            name="uq_coeff_context_version_hash",
        ),
    )

    # ── Orchestration Identities ────────────────────────────────────────
    op.create_table(
        "orchestration_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column(
            "execution_snapshot_id",
            sa.String(36),
            sa.ForeignKey("orchestration_execution_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "coefficient_context_id",
            sa.String(36),
            sa.ForeignKey("orchestration_coefficient_contexts.id"),
            nullable=False,
        ),
        sa.Column("definition_version", sa.String(50), nullable=False),
        sa.Column("calculator_version_vector", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("authoritative_attempt_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_orch_identity_fingerprint"),
    )

    # ── Orchestration Run Attempts ──────────────────────────────────────
    op.create_table(
        "orchestration_run_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "identity_id",
            sa.String(36),
            sa.ForeignKey("orchestration_identities.id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="RUNNING"),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_binding_id", sa.String(36), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_details", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("identity_id", "attempt_number", name="uq_attempt_identity_number"),
    )

    # ── Source Bindings ─────────────────────────────────────────────────
    op.create_table(
        "orchestration_source_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "project_version_id",
            sa.String(36),
            sa.ForeignKey("project_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "execution_snapshot_id",
            sa.String(36),
            sa.ForeignKey("orchestration_execution_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "coefficient_context_id",
            sa.String(36),
            sa.ForeignKey("orchestration_coefficient_contexts.id"),
            nullable=False,
        ),
        sa.Column(
            "orchestration_identity_id",
            sa.String(36),
            sa.ForeignKey("orchestration_identities.id"),
            nullable=False,
        ),
        sa.Column(
            "orchestration_run_attempt_id",
            sa.String(36),
            sa.ForeignKey("orchestration_run_attempts.id"),
            nullable=False,
        ),
        sa.Column("orchestration_fingerprint", sa.String(128), nullable=False),
        sa.Column(
            "zone_calculation_id",
            sa.String(36),
            sa.ForeignKey("calculation_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "cooling_load_calculation_id",
            sa.String(36),
            sa.ForeignKey("calculation_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "equipment_calculation_id",
            sa.String(36),
            sa.ForeignKey("calculation_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "power_calculation_id",
            sa.String(36),
            sa.ForeignKey("calculation_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "investment_calculation_id",
            sa.String(36),
            sa.ForeignKey("calculation_runs.id"),
            nullable=False,
        ),
        sa.Column("per_calculation_result_hashes", sa.JSON(), nullable=False),
        sa.Column("combined_source_hash", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "orchestration_identity_id",
            "orchestration_run_attempt_id",
            name="uq_source_binding_identity_attempt",
        ),
    )

    # ── Audit Outbox ────────────────────────────────────────────────────
    op.create_table(
        "orchestration_audit_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_identity", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("aggregate_type", sa.String(120), nullable=False),
        sa.Column("aggregate_id", sa.String(120), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("identity_id", sa.String(36), nullable=True),
        sa.Column("attempt_id", sa.String(36), nullable=True),
        sa.Column("calculation_run_id", sa.String(36), nullable=True),
        sa.Column("source_binding_id", sa.String(36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by", sa.String(100), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_details", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_identity", name="uq_outbox_event_identity"),
    )

    # ── Calculation Runs: add orchestration fields ──────────────────────
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.add_column(sa.Column("calculation_type", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("orchestration_identity_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("orchestration_run_attempt_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("execution_snapshot_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("coefficient_context_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("input_hash", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("result_hash", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("provenance", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("schema_version", sa.String(50), nullable=True))

    # ── Scheme Runs: add production source fields ───────────────────────
    with op.batch_alter_table("scheme_runs") as batch_op:
        batch_op.add_column(
            sa.Column("source_mode", sa.String(50), nullable=False, server_default="legacy")
        )
        batch_op.add_column(sa.Column("source_binding_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("source_contract_version", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("weight_set_revision_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("weight_set_content_hash", sa.String(128), nullable=True))
        batch_op.add_column(
            sa.Column("weight_set_generator_compatibility_version", sa.String(50), nullable=True)
        )
        batch_op.add_column(sa.Column("combined_source_hash", sa.String(128), nullable=True))

    # ── Audit Events: add outbox identity ───────────────────────────────
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.add_column(sa.Column("outbox_event_id", sa.String(36), nullable=True))
        batch_op.create_unique_constraint("uq_audit_event_outbox", ["outbox_event_id"])


def downgrade() -> None:
    # ── Audit Events: remove outbox identity ────────────────────────────
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("uq_audit_event_outbox", type_="unique")
        batch_op.drop_column("outbox_event_id")

    # ── Scheme Runs: remove production source fields ────────────────────
    with op.batch_alter_table("scheme_runs") as batch_op:
        batch_op.drop_column("combined_source_hash")
        batch_op.drop_column("weight_set_generator_compatibility_version")
        batch_op.drop_column("weight_set_content_hash")
        batch_op.drop_column("weight_set_revision_id")
        batch_op.drop_column("source_contract_version")
        batch_op.drop_column("source_binding_id")
        batch_op.drop_column("source_mode")

    # ── Calculation Runs: remove orchestration fields ───────────────────
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_column("schema_version")
        batch_op.drop_column("provenance")
        batch_op.drop_column("result_hash")
        batch_op.drop_column("input_hash")
        batch_op.drop_column("coefficient_context_id")
        batch_op.drop_column("execution_snapshot_id")
        batch_op.drop_column("orchestration_run_attempt_id")
        batch_op.drop_column("orchestration_identity_id")
        batch_op.drop_column("calculation_type")

    # ── Drop new tables in reverse dependency order ─────────────────────
    op.drop_table("orchestration_audit_outbox")
    op.drop_table("orchestration_source_bindings")
    op.drop_table("orchestration_run_attempts")
    op.drop_table("orchestration_identities")
    op.drop_table("orchestration_coefficient_contexts")
    op.drop_table("orchestration_execution_snapshots")
    op.drop_table("orchestration_requests")
