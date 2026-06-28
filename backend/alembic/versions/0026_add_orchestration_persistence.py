"""Add orchestration persistence tables and extend existing entities.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-28

Provides:
- 7 new orchestration tables (requests, snapshots, contexts, identities,
  attempts, bindings, outbox)
- CalculationRun orchestration columns with all-null/all-required CHECK
  and foreign keys
- SchemeRun source_mode columns with legacy/production CHECK and FKs
- SchemeWeightSetRevision skeleton
- one-RUNNING partial unique index
- AuditEvent outbox_event_id NOT NULL UNIQUE with legacy backfill
- Safe downgrade gate (blocked when production data exists)
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

    # ── One-RUNNING partial unique index ────────────────────────────────
    dialect_name = op.get_context().dialect.name
    if dialect_name == "postgresql":
        op.create_index(
            "uq_attempt_one_running",
            "orchestration_run_attempts",
            ["identity_id"],
            unique=True,
            postgresql_where=sa.text("status = 'RUNNING'"),
        )
    elif dialect_name == "sqlite":
        op.create_index(
            "uq_attempt_one_running",
            "orchestration_run_attempts",
            ["identity_id"],
            unique=True,
            sqlite_where=sa.text("status = 'RUNNING'"),
        )
    else:
        # Generic fallback: create as non-partial unique index so at least
        # the intent is visible, but this will not enforce the one-RUNNING
        # invariant on unrecognised dialects.
        op.create_index(
            "uq_attempt_one_running",
            "orchestration_run_attempts",
            ["identity_id"],
            unique=True,
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

    # ── SourceBinding per-slot indexes ──────────────────────────────────
    for col_name in (
        "zone_calculation_id",
        "cooling_load_calculation_id",
        "equipment_calculation_id",
        "power_calculation_id",
        "investment_calculation_id",
    ):
        op.create_index(
            f"ix_source_binding_{col_name}",
            "orchestration_source_bindings",
            [col_name],
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
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(100), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_details", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_identity", name="uq_outbox_event_identity"),
    )

    # ── Outbox status nullability CHECK ─────────────────────────────────
    _create_check_constraint(
        "orchestration_audit_outbox",
        "ck_outbox_status_nullity",
        "(\n"
        "    status = 'PENDING'\n"
        "    AND claimed_at IS NULL\n"
        "    AND claimed_by IS NULL\n"
        "    AND claim_expires_at IS NULL\n"
        "    AND published_at IS NULL\n"
        ")\n"
        "OR (\n"
        "    status = 'PROCESSING'\n"
        "    AND claimed_at IS NOT NULL\n"
        "    AND claimed_by IS NOT NULL\n"
        "    AND claim_expires_at IS NOT NULL\n"
        "    AND published_at IS NULL\n"
        ")\n"
        "OR (\n"
        "    status = 'PUBLISHED'\n"
        "    AND published_at IS NOT NULL\n"
        ")",
    )

    # ── Scheme Weight Set Revisions ─────────────────────────────────────
    op.create_table(
        "scheme_weight_set_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "weight_set_id",
            sa.String(36),
            sa.ForeignKey("scheme_weight_sets.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("generator_compatibility_version", sa.String(50), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", "revision", name="uq_scheme_weight_set_revision_code_revision"),
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

    # ── Calculation Run all-null/all-required CHECK ─────────────────────
    _create_check_constraint(
        "calculation_runs",
        "ck_calculation_run_orchestration_nullity",
        "(\n"
        "    orchestration_identity_id IS NULL\n"
        "    AND orchestration_run_attempt_id IS NULL\n"
        "    AND execution_snapshot_id IS NULL\n"
        "    AND coefficient_context_id IS NULL\n"
        "    AND input_hash IS NULL\n"
        "    AND result_hash IS NULL\n"
        "    AND provenance IS NULL\n"
        "    AND schema_version IS NULL\n"
        "    AND calculation_type IS NULL\n"
        ")\n"
        "OR (\n"
        "    orchestration_identity_id IS NOT NULL\n"
        "    AND orchestration_run_attempt_id IS NOT NULL\n"
        "    AND execution_snapshot_id IS NOT NULL\n"
        "    AND coefficient_context_id IS NOT NULL\n"
        "    AND input_hash IS NOT NULL\n"
        "    AND result_hash IS NOT NULL\n"
        "    AND provenance IS NOT NULL\n"
        "    AND schema_version IS NOT NULL\n"
        "    AND calculation_type IS NOT NULL\n"
        ")",
    )

    # ── Calculation Run orchestration FKs ───────────────────────────────
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.create_foreign_key(
            "fk_calc_run_orch_identity",
            "orchestration_identities",
            ["orchestration_identity_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_calc_run_orch_attempt",
            "orchestration_run_attempts",
            ["orchestration_run_attempt_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_calc_run_exec_snapshot",
            "orchestration_execution_snapshots",
            ["execution_snapshot_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_calc_run_coeff_context",
            "orchestration_coefficient_contexts",
            ["coefficient_context_id"],
            ["id"],
        )

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
            sa.Column(
                "weight_set_generator_compatibility_version",
                sa.String(50),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("combined_source_hash", sa.String(128), nullable=True))

    # ── Scheme Run legacy/production CHECK ──────────────────────────────
    _create_check_constraint(
        "scheme_runs",
        "ck_scheme_run_source_mode_nullity",
        "(\n"
        "    source_mode = 'legacy'\n"
        "    AND source_binding_id IS NULL\n"
        "    AND source_contract_version IS NULL\n"
        "    AND weight_set_revision_id IS NULL\n"
        "    AND weight_set_content_hash IS NULL\n"
        "    AND weight_set_generator_compatibility_version IS NULL\n"
        "    AND combined_source_hash IS NULL\n"
        ")\n"
        "OR (\n"
        "    source_mode = 'production'\n"
        "    AND source_binding_id IS NOT NULL\n"
        "    AND source_contract_version IS NOT NULL\n"
        "    AND weight_set_revision_id IS NOT NULL\n"
        "    AND weight_set_content_hash IS NOT NULL\n"
        "    AND weight_set_generator_compatibility_version IS NOT NULL\n"
        "    AND combined_source_hash IS NOT NULL\n"
        ")",
    )

    # ── Scheme Run FKs ──────────────────────────────────────────────────
    with op.batch_alter_table("scheme_runs") as batch_op:
        batch_op.create_foreign_key(
            "fk_scheme_run_source_binding",
            "orchestration_source_bindings",
            ["source_binding_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_scheme_run_weight_set_revision",
            "scheme_weight_set_revisions",
            ["weight_set_revision_id"],
            ["id"],
        )

    # ── Request status nullability CHECK ────────────────────────────────
    _create_check_constraint(
        "orchestration_requests",
        "ck_orch_request_status_nullity",
        "(\n"
        "    status = 'PENDING'\n"
        "    AND resolved_identity_id IS NULL\n"
        "    AND resolved_attempt_id IS NULL\n"
        "    AND failure_code IS NULL\n"
        "    AND failure_field IS NULL\n"
        "    AND failure_details IS NULL\n"
        "    AND completed_at IS NULL\n"
        ")\n"
        "OR (\n"
        "    status = 'PREFLIGHT_REJECTED'\n"
        "    AND resolved_identity_id IS NULL\n"
        "    AND resolved_attempt_id IS NULL\n"
        "    AND failure_code IS NOT NULL\n"
        "    AND failure_field IS NOT NULL\n"
        "    AND failure_details IS NOT NULL\n"
        "    AND completed_at IS NOT NULL\n"
        ")\n"
        "OR (\n"
        "    status = 'ACCEPTED'\n"
        "    AND resolved_identity_id IS NOT NULL\n"
        "    AND resolved_attempt_id IS NOT NULL\n"
        "    AND failure_code IS NULL\n"
        "    AND failure_field IS NULL\n"
        "    AND failure_details IS NULL\n"
        "    AND completed_at IS NOT NULL\n"
        ")",
    )

    # ── Request resolved FKs ────────────────────────────────────────────
    with op.batch_alter_table("orchestration_requests") as batch_op:
        batch_op.create_foreign_key(
            "fk_orch_request_resolved_identity",
            "orchestration_identities",
            ["resolved_identity_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_orch_request_resolved_attempt",
            "orchestration_run_attempts",
            ["resolved_attempt_id"],
            ["id"],
        )

    # ── Identity authoritative_attempt_id FK (circular — use_alter) ─────
    with op.batch_alter_table("orchestration_identities") as batch_op:
        batch_op.create_foreign_key(
            "fk_orch_identity_authoritative_attempt",
            "orchestration_run_attempts",
            ["authoritative_attempt_id"],
            ["id"],
        )

    # ── Attempt source_binding_id FK (circular — use_alter) ─────────────
    with op.batch_alter_table("orchestration_run_attempts") as batch_op:
        batch_op.create_foreign_key(
            "fk_orch_attempt_source_binding",
            "orchestration_source_bindings",
            ["source_binding_id"],
            ["id"],
        )

    # ── Outbox FKs ──────────────────────────────────────────────────────
    with op.batch_alter_table("orchestration_audit_outbox") as batch_op:
        batch_op.create_foreign_key(
            "fk_outbox_request",
            "orchestration_requests",
            ["request_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_outbox_identity",
            "orchestration_identities",
            ["identity_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_outbox_attempt",
            "orchestration_run_attempts",
            ["attempt_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_outbox_calc_run",
            "calculation_runs",
            ["calculation_run_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_outbox_source_binding",
            "orchestration_source_bindings",
            ["source_binding_id"],
            ["id"],
        )

    # ── Audit Events: outbox_event_id backfill + NOT NULL ───────────────
    # Step 0: add nullable column
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.add_column(sa.Column("outbox_event_id", sa.String(128), nullable=True))

    # Step 1: backfill legacy rows with stable, deterministic IDs
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM audit_events WHERE outbox_event_id IS NULL")
    ).fetchall()
    if rows:
        # Use a single UPDATE with a deterministic formula
        for row in rows:
            legacy_id = f"legacy-audit:{row[0]}"
            conn.execute(
                sa.text("UPDATE audit_events SET outbox_event_id = :oid WHERE id = :rid"),
                {"oid": legacy_id, "rid": row[0]},
            )

    # Step 2: verify no nulls remain
    null_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM audit_events WHERE outbox_event_id IS NULL")
    ).scalar()
    if null_count != 0:
        raise RuntimeError(f"outbox_event_id backfill failed: {null_count} NULL values remain")

    # Step 3: verify no duplicates
    dup_count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT outbox_event_id, COUNT(*) as cnt"
            "  FROM audit_events"
            "  GROUP BY outbox_event_id"
            "  HAVING COUNT(*) > 1"
            ") sub"
        )
    ).scalar()
    if dup_count != 0:
        raise RuntimeError(f"outbox_event_id backfill produced {dup_count} duplicate sets")

    # Step 4: make NOT NULL + unique
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.alter_column("outbox_event_id", nullable=False)
        batch_op.create_unique_constraint("uq_audit_event_outbox", ["outbox_event_id"])


def downgrade() -> None:
    # ── Downgrade blocker: refuse when production data exists ───────────
    conn = op.get_bind()

    production_scheme_count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM scheme_runs "
            "WHERE source_mode = 'production' OR source_binding_id IS NOT NULL"
        )
    ).scalar()
    source_binding_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM orchestration_source_bindings")
    ).scalar()

    if production_scheme_count > 0 or source_binding_count > 0:
        raise RuntimeError(
            "Cannot downgrade orchestration persistence while production "
            "SchemeRun or SourceBinding data exists"
        )

    # ── Audit Events: revert outbox_event_id ────────────────────────────
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("uq_audit_event_outbox", type_="unique")
        batch_op.alter_column("outbox_event_id", nullable=True)
        batch_op.drop_column("outbox_event_id")

    # ── Outbox FKs ──────────────────────────────────────────────────────
    with op.batch_alter_table("orchestration_audit_outbox") as batch_op:
        batch_op.drop_constraint("ck_outbox_status_nullity", type_="check")
        batch_op.drop_constraint("fk_outbox_source_binding", type_="foreignkey")
        batch_op.drop_constraint("fk_outbox_calc_run", type_="foreignkey")
        batch_op.drop_constraint("fk_outbox_attempt", type_="foreignkey")
        batch_op.drop_constraint("fk_outbox_identity", type_="foreignkey")
        batch_op.drop_constraint("fk_outbox_request", type_="foreignkey")

    # ── Attempt source_binding_id FK ────────────────────────────────────
    with op.batch_alter_table("orchestration_run_attempts") as batch_op:
        batch_op.drop_constraint("fk_orch_attempt_source_binding", type_="foreignkey")

    # ── Identity authoritative_attempt_id FK ────────────────────────────
    with op.batch_alter_table("orchestration_identities") as batch_op:
        batch_op.drop_constraint("fk_orch_identity_authoritative_attempt", type_="foreignkey")

    # ── Request FKs ─────────────────────────────────────────────────────
    with op.batch_alter_table("orchestration_requests") as batch_op:
        batch_op.drop_constraint("fk_orch_request_resolved_attempt", type_="foreignkey")
        batch_op.drop_constraint("fk_orch_request_resolved_identity", type_="foreignkey")

    # ── Request status CHECK ─────────────────────────────────────────────
    _drop_check_constraint("orchestration_requests", "ck_orch_request_status_nullity")

    # ── Scheme Run FKs ──────────────────────────────────────────────────
    with op.batch_alter_table("scheme_runs") as batch_op:
        batch_op.drop_constraint("fk_scheme_run_weight_set_revision", type_="foreignkey")
        batch_op.drop_constraint("fk_scheme_run_source_binding", type_="foreignkey")

    # ── Scheme Run CHECK ────────────────────────────────────────────────
    _drop_check_constraint("scheme_runs", "ck_scheme_run_source_mode_nullity")

    # ── Scheme Runs: remove production source fields ────────────────────
    with op.batch_alter_table("scheme_runs") as batch_op:
        batch_op.drop_column("combined_source_hash")
        batch_op.drop_column("weight_set_generator_compatibility_version")
        batch_op.drop_column("weight_set_content_hash")
        batch_op.drop_column("weight_set_revision_id")
        batch_op.drop_column("source_contract_version")
        batch_op.drop_column("source_binding_id")
        batch_op.drop_column("source_mode")

    # ── Calculation Run FKs ─────────────────────────────────────────────
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_constraint("fk_calc_run_coeff_context", type_="foreignkey")
        batch_op.drop_constraint("fk_calc_run_exec_snapshot", type_="foreignkey")
        batch_op.drop_constraint("fk_calc_run_orch_attempt", type_="foreignkey")
        batch_op.drop_constraint("fk_calc_run_orch_identity", type_="foreignkey")

    # ── Calculation Run CHECK ───────────────────────────────────────────
    _drop_check_constraint("calculation_runs", "ck_calculation_run_orchestration_nullity")

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
    op.drop_table("scheme_weight_set_revisions")
    op.drop_table("orchestration_audit_outbox")

    # SourceBinding per-slot indexes
    for col_name in (
        "investment_calculation_id",
        "power_calculation_id",
        "equipment_calculation_id",
        "cooling_load_calculation_id",
        "zone_calculation_id",
    ):
        op.drop_index(
            f"ix_source_binding_{col_name}",
            table_name="orchestration_source_bindings",
        )

    op.drop_table("orchestration_source_bindings")

    # One-RUNNING index
    op.drop_index("uq_attempt_one_running", table_name="orchestration_run_attempts")

    op.drop_table("orchestration_run_attempts")
    op.drop_table("orchestration_identities")
    op.drop_table("orchestration_coefficient_contexts")
    op.drop_table("orchestration_execution_snapshots")
    op.drop_table("orchestration_requests")


# ── Cross-DB CHECK helpers ─────────────────────────────────────────────────


def _create_check_constraint(table_name: str, constraint_name: str, condition_sql: str) -> None:
    """Create a named CHECK constraint with dialect-appropriate syntax."""
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    if dialect_name == "sqlite":
        # SQLite requires rebuilding the table for CHECK constraints,
        # which Alembic's batch mode handles automatically.
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_check_constraint(
                constraint_name=constraint_name,
                condition=sa.text(condition_sql),
            )
    else:
        # PostgreSQL and other dialects can ALTER TABLE ADD CONSTRAINT directly.
        op.create_check_constraint(
            constraint_name=constraint_name,
            table_name=table_name,
            condition=sa.text(condition_sql),
        )


def _drop_check_constraint(table_name: str, constraint_name: str) -> None:
    """Drop a named CHECK constraint with dialect-appropriate syntax."""
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    if dialect_name == "sqlite":
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="check")
    else:
        op.drop_constraint(constraint_name, table_name, type_="check")
