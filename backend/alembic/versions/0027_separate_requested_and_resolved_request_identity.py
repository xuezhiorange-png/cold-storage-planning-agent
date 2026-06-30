"""Separate requested and resolved request identity.

Revision ID: 0027_separate_requested_and_resolved_request_identity
Revises: 0026_add_orchestration_persistence
Create Date: 2026-06-28

Reworks ``orchestration_requests`` so that raw caller-provided identity
(requested_project_id, requested_project_version_id) is preserved without
FK constraints, while resolved identity (resolved_project_id,
resolved_project_version_id) carries nullable FKs set only after
successful authoritative resolution.

For SQLite, uses ``batch_alter_table`` which copies the table preserving
constraint names.  For PostgreSQL, uses standard ALTER operations.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_separate_requested_and_resolved_request_identity"
down_revision: str | None = "0026_add_orchestration_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name == "sqlite":
        _sqlite_upgrade()
    else:
        _pg_upgrade()


def downgrade() -> None:
    _block_downgrade_if_unresolvable_requests()
    dialect_name = op.get_context().dialect.name
    if dialect_name == "sqlite":
        _sqlite_downgrade()
    else:
        _pg_downgrade()


def _block_downgrade_if_unresolvable_requests() -> None:
    """Block downgrade when orchestration_requests contain unresolvable
    requested_project_id or requested_project_version_id.

    The new schema allows storing unresolvable caller-provided identity
    (requested_* columns have no FK).  Rolling back to the old schema
    would put those values into FK-constrained ``project_id`` /
    ``project_version_id`` columns, which would fail.

    Checks (before any schema mutation):
    1. requested_project_id not in projects
    2. requested_project_version_id not in project_versions
    3. project_version exists but belongs to a different project
    """
    from sqlalchemy import text as _sa_text

    conn = op.get_bind()
    revision_id = "0027_separate_requested_and_resolved_request_identity"

    # Check 1: requested_project_id not resolvable
    unresolved_project = conn.execute(
        _sa_text(
            "SELECT COUNT(*) FROM orchestration_requests r "
            "WHERE r.requested_project_id IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM projects p WHERE p.id = r.requested_project_id"
            ")"
        )
    ).scalar()

    # Check 2: requested_project_version_id not resolvable
    unresolved_version = conn.execute(
        _sa_text(
            "SELECT COUNT(*) FROM orchestration_requests r "
            "WHERE r.requested_project_version_id IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM project_versions pv "
            "  WHERE pv.id = r.requested_project_version_id"
            ")"
        )
    ).scalar()

    # Check 3: project_version exists but belongs to a different project
    version_project_mismatch = conn.execute(
        _sa_text(
            "SELECT COUNT(*) FROM orchestration_requests r "
            "JOIN project_versions pv ON pv.id = r.requested_project_version_id "
            "WHERE r.requested_project_id IS NOT NULL "
            "AND pv.project_id != r.requested_project_id"
        )
    ).scalar()

    if unresolved_project or unresolved_version or version_project_mismatch:
        reasons: list[str] = []
        if unresolved_project:
            reasons.append(
                f"{unresolved_project} rows have requested_project_id not found in projects"
            )
        if unresolved_version:
            reasons.append(
                f"{unresolved_version} rows have requested_project_version_id "
                "not found in project_versions"
            )
        if version_project_mismatch:
            reasons.append(
                f"{version_project_mismatch} rows have "
                "requested_project_version_id belonging to a different project"
            )

        raise RuntimeError(
            f"Cannot downgrade migration {revision_id}: "
            + "; ".join(reasons)
            + ". These records cannot be safely restored to the old schema "
            "because the old schema requires FK-constrained project_id and "
            "project_version_id. Remove affected records first."
        )


# ── PostgreSQL ──────────────────────────────────────────────────────────────


def _pg_upgrade() -> None:
    op.drop_constraint("ck_orch_request_status_nullity", "orchestration_requests")
    op.drop_constraint("orchestration_requests_project_id_fkey", "orchestration_requests")
    op.drop_constraint("orchestration_requests_project_version_id_fkey", "orchestration_requests")
    op.alter_column("orchestration_requests", "project_id", new_column_name="requested_project_id")
    op.alter_column(
        "orchestration_requests",
        "project_version_id",
        new_column_name="requested_project_version_id",
    )
    op.add_column(
        "orchestration_requests", sa.Column("resolved_project_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "orchestration_requests",
        sa.Column("resolved_project_version_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "orchestration_requests_resolved_project_id_fkey",
        "orchestration_requests",
        "projects",
        ["resolved_project_id"],
        ["id"],
    )
    op.create_foreign_key(
        "orchestration_requests_resolved_project_version_id_fkey",
        "orchestration_requests",
        "project_versions",
        ["resolved_project_version_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_orch_request_status_nullity", "orchestration_requests", _NEW_CHECK
    )


def _pg_downgrade() -> None:
    op.drop_constraint("ck_orch_request_status_nullity", "orchestration_requests")
    op.drop_constraint(
        "orchestration_requests_resolved_project_version_id_fkey", "orchestration_requests"
    )
    op.drop_constraint("orchestration_requests_resolved_project_id_fkey", "orchestration_requests")
    op.drop_column("orchestration_requests", "resolved_project_version_id")
    op.drop_column("orchestration_requests", "resolved_project_id")
    op.alter_column("orchestration_requests", "requested_project_id", new_column_name="project_id")
    op.alter_column(
        "orchestration_requests",
        "requested_project_version_id",
        new_column_name="project_version_id",
    )
    op.create_foreign_key(
        "orchestration_requests_project_version_id_fkey",
        "orchestration_requests",
        "project_versions",
        ["project_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "orchestration_requests_project_id_fkey",
        "orchestration_requests",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_orch_request_status_nullity", "orchestration_requests", _OLD_CHECK
    )


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_upgrade() -> None:
    """SQLite upgrade: recreate table to move FKs from requested_* to resolved_*."""
    from sqlalchemy import text as _sa_text

    conn = op.get_bind()

    # Drop and recreate with new schema (raw SQL for clean FK migration)
    conn.execute(
        _sa_text(
            """
        CREATE TABLE _alembic_tmp_orch_req (
            id VARCHAR(36) PRIMARY KEY,
            requested_project_id VARCHAR(36) NOT NULL,
            requested_project_version_id VARCHAR(36) NOT NULL,
            request_fingerprint VARCHAR(128) NOT NULL,
            actor VARCHAR(100) NOT NULL,
            correlation_id VARCHAR(128) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            resolved_project_id VARCHAR(36) REFERENCES projects(id),
            resolved_project_version_id VARCHAR(36) REFERENCES project_versions(id),
            resolved_identity_id VARCHAR(36),
            resolved_attempt_id VARCHAR(36),
            failure_code VARCHAR(100),
            failure_field VARCHAR(200),
            failure_details JSON,
            created_at DATETIME NOT NULL,
            completed_at DATETIME,
            CONSTRAINT ck_orch_request_status_nullity CHECK ("""
            + _NEW_CHECK
            + """)
        )
    """
        )
    )
    conn.execute(
        _sa_text("""
        INSERT INTO _alembic_tmp_orch_req
            (id, requested_project_id, requested_project_version_id,
             request_fingerprint, actor, correlation_id, status,
             resolved_project_id, resolved_project_version_id,
             resolved_identity_id, resolved_attempt_id,
             failure_code, failure_field, failure_details,
             created_at, completed_at)
        SELECT id, project_id, project_version_id,
               request_fingerprint, actor, correlation_id, status,
               NULL, NULL,
               resolved_identity_id, resolved_attempt_id,
               failure_code, failure_field, failure_details,
               created_at, completed_at
        FROM orchestration_requests
    """)
    )
    conn.execute(_sa_text("DROP TABLE orchestration_requests"))
    conn.execute(_sa_text("ALTER TABLE _alembic_tmp_orch_req RENAME TO orchestration_requests"))
    # Add named FKs via batch to preserve Alembic constraint tracking
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
    # Recreate indexes
    conn.execute(
        _sa_text(
            "CREATE INDEX IF NOT EXISTS ix_orchestration_requests_request_fingerprint "
            "ON orchestration_requests (request_fingerprint)"
        )
    )


def _sqlite_downgrade() -> None:
    """SQLite downgrade: recreate table via Alembic create_table so 0026's
    downgrade can find named constraints."""
    from sqlalchemy import text as _sa_text

    conn = op.get_bind()

    # Preserve data in temp table
    conn.execute(
        _sa_text(
            "CREATE TABLE _alembic_tmp_orch_req AS "
            "SELECT "
            "  id, requested_project_id AS project_id, "
            "  requested_project_version_id AS project_version_id, "
            "  request_fingerprint, actor, correlation_id, status, "
            "  resolved_identity_id, resolved_attempt_id, "
            "  failure_code, failure_field, failure_details, "
            "  created_at, completed_at "
            "FROM orchestration_requests"
        )
    )
    conn.execute(_sa_text("DROP TABLE orchestration_requests"))

    # Recreate using Alembic's op.create_table to match 0026 schema exactly
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

    # Restore data
    conn.execute(
        _sa_text(
            "INSERT INTO orchestration_requests "
            "(id, project_id, project_version_id, request_fingerprint, actor, "
            " correlation_id, status, resolved_identity_id, resolved_attempt_id, "
            " failure_code, failure_field, failure_details, created_at, completed_at) "
            "SELECT id, project_id, project_version_id, request_fingerprint, actor, "
            " correlation_id, status, resolved_identity_id, resolved_attempt_id, "
            " failure_code, failure_field, failure_details, created_at, completed_at "
            "FROM _alembic_tmp_orch_req"
        )
    )
    conn.execute(_sa_text("DROP TABLE _alembic_tmp_orch_req"))

    # Add CHECK and extra FKs exactly as 0026 upgrade did (named, tracked)
    with op.batch_alter_table("orchestration_requests") as batch_op:
        batch_op.create_check_constraint("ck_orch_request_status_nullity", _OLD_CHECK)
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


# ── CHECK definitions ──────────────────────────────────────────────────────


_NEW_CHECK = (
    "(status = 'PENDING'"
    " AND resolved_project_id IS NULL"
    " AND resolved_project_version_id IS NULL"
    " AND resolved_identity_id IS NULL"
    " AND resolved_attempt_id IS NULL"
    " AND failure_code IS NULL"
    " AND failure_field IS NULL"
    " AND failure_details IS NULL"
    " AND completed_at IS NULL)"
    " OR (status = 'PREFLIGHT_REJECTED'"
    " AND resolved_identity_id IS NULL"
    " AND resolved_attempt_id IS NULL"
    " AND failure_code IS NOT NULL"
    " AND failure_field IS NOT NULL"
    " AND failure_details IS NOT NULL"
    " AND completed_at IS NOT NULL)"
    " OR (status = 'ACCEPTED'"
    " AND resolved_project_id IS NOT NULL"
    " AND resolved_project_version_id IS NOT NULL"
    " AND resolved_identity_id IS NOT NULL"
    " AND resolved_attempt_id IS NOT NULL"
    " AND failure_code IS NULL"
    " AND failure_field IS NULL"
    " AND failure_details IS NULL"
    " AND completed_at IS NOT NULL)"
)

_OLD_CHECK = (
    "(status = 'PENDING'"
    " AND resolved_identity_id IS NULL"
    " AND resolved_attempt_id IS NULL"
    " AND failure_code IS NULL"
    " AND failure_field IS NULL"
    " AND failure_details IS NULL"
    " AND completed_at IS NULL)"
    " OR (status = 'PREFLIGHT_REJECTED'"
    " AND resolved_identity_id IS NULL"
    " AND resolved_attempt_id IS NULL"
    " AND failure_code IS NOT NULL"
    " AND failure_field IS NOT NULL"
    " AND failure_details IS NOT NULL"
    " AND completed_at IS NOT NULL)"
    " OR (status = 'ACCEPTED'"
    " AND resolved_identity_id IS NOT NULL"
    " AND resolved_attempt_id IS NOT NULL"
    " AND failure_code IS NULL"
    " AND failure_field IS NULL"
    " AND failure_details IS NULL"
    " AND completed_at IS NOT NULL)"
)
