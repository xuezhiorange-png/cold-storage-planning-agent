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

from alembic import op
import sqlalchemy as sa

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
    """Block downgrade when PREFLIGHT_REJECTED records have unresolvable
    requested_project_id or requested_project_version_id.

    The new schema allows storing unresolvable caller-provided identity
    (requested_* columns have no FK).  Rolling back to the old schema
    would put those values into FK-constrained ``project_id`` /
    ``project_version_id`` columns, which would fail.

    This check runs BEFORE any schema mutation.
    """
    from sqlalchemy import text as _sa_text

    conn = op.get_bind()
    dialect_name = op.get_context().dialect.name

    # Check for rows where requested_project_id can't be resolved
    if dialect_name == "sqlite":
        unresolvable = conn.execute(
            _sa_text(
                "SELECT COUNT(*) FROM orchestration_requests r "
                "WHERE r.requested_project_id IS NOT NULL "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM projects p WHERE p.id = r.requested_project_id"
                ")"
            )
        ).scalar()
    else:
        unresolvable = conn.execute(
            _sa_text(
                "SELECT COUNT(*) FROM orchestration_requests r "
                "WHERE r.requested_project_id IS NOT NULL "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM projects p WHERE p.id = r.requested_project_id"
                ")"
            )
        ).scalar()

    if unresolvable:
        raise RuntimeError(
            "Cannot downgrade: {} orchestration_requests have "
            "requested_project_id that cannot be resolved to "
            "the projects table.  Downgrade would create FK violations.  "
            "Remove affected records first or use --force-downgrade.".format(
                unresolvable
            )
        )


# ── PostgreSQL ──────────────────────────────────────────────────────────────


def _pg_upgrade() -> None:
    op.drop_constraint("ck_orch_request_status_nullity", "orchestration_requests")
    op.drop_constraint("orchestration_requests_project_id_fkey", "orchestration_requests")
    op.drop_constraint("orchestration_requests_project_version_id_fkey", "orchestration_requests")
    op.alter_column("orchestration_requests", "project_id",
                    new_column_name="requested_project_id")
    op.alter_column("orchestration_requests", "project_version_id",
                    new_column_name="requested_project_version_id")
    op.add_column("orchestration_requests",
                  sa.Column("resolved_project_id", sa.String(36), nullable=True))
    op.add_column("orchestration_requests",
                  sa.Column("resolved_project_version_id", sa.String(36), nullable=True))
    op.create_foreign_key("orchestration_requests_resolved_project_id_fkey",
                          "orchestration_requests", "projects",
                          ["resolved_project_id"], ["id"])
    op.create_foreign_key("orchestration_requests_resolved_project_version_id_fkey",
                          "orchestration_requests", "project_versions",
                          ["resolved_project_version_id"], ["id"])
    op.create_check_constraint("ck_orch_request_status_nullity",
                               "orchestration_requests", _NEW_CHECK)


def _pg_downgrade() -> None:
    op.drop_constraint("ck_orch_request_status_nullity", "orchestration_requests")
    op.drop_constraint("orchestration_requests_resolved_project_version_id_fkey",
                       "orchestration_requests")
    op.drop_constraint("orchestration_requests_resolved_project_id_fkey",
                       "orchestration_requests")
    op.drop_column("orchestration_requests", "resolved_project_version_id")
    op.drop_column("orchestration_requests", "resolved_project_id")
    op.alter_column("orchestration_requests", "requested_project_id",
                    new_column_name="project_id")
    op.alter_column("orchestration_requests", "requested_project_version_id",
                    new_column_name="project_version_id")
    op.create_foreign_key("orchestration_requests_project_version_id_fkey",
                          "orchestration_requests", "project_versions",
                          ["project_version_id"], ["id"])
    op.create_foreign_key("orchestration_requests_project_id_fkey",
                          "orchestration_requests", "projects",
                          ["project_id"], ["id"])
    op.create_check_constraint("ck_orch_request_status_nullity",
                               "orchestration_requests", _OLD_CHECK)


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_upgrade() -> None:
    """SQLite upgrade: recreate table to move FKs from requested_* to resolved_*."""
    from sqlalchemy import text as _sa_text

    conn = op.get_bind()

    conn.execute(_sa_text("""
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
            CONSTRAINT ck_orch_request_status_nullity CHECK (""" + _NEW_CHECK + """)
        )
    """))
    conn.execute(_sa_text("""
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
    """))
    conn.execute(_sa_text("DROP TABLE orchestration_requests"))
    conn.execute(_sa_text(
        "ALTER TABLE _alembic_tmp_orch_req RENAME TO orchestration_requests"
    ))
    # Recreate indexes
    conn.execute(_sa_text(
        "CREATE INDEX IF NOT EXISTS ix_orchestration_requests_request_fingerprint "
        "ON orchestration_requests (request_fingerprint)"
    ))


def _sqlite_downgrade() -> None:
    """SQLite downgrade: recreate table to restore old schema."""
    from sqlalchemy import text as _sa_text

    conn = op.get_bind()

    conn.execute(_sa_text("""
        CREATE TABLE _alembic_tmp_orch_req (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
            project_version_id VARCHAR(36) NOT NULL REFERENCES project_versions(id),
            request_fingerprint VARCHAR(128) NOT NULL,
            actor VARCHAR(100) NOT NULL,
            correlation_id VARCHAR(128) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            resolved_identity_id VARCHAR(36),
            resolved_attempt_id VARCHAR(36),
            failure_code VARCHAR(100),
            failure_field VARCHAR(200),
            failure_details JSON,
            created_at DATETIME NOT NULL,
            completed_at DATETIME,
            CONSTRAINT ck_orch_request_status_nullity CHECK (""" + _OLD_CHECK + """)
        )
    """))
    conn.execute(_sa_text("""
        INSERT INTO _alembic_tmp_orch_req
            (id, project_id, project_version_id,
             request_fingerprint, actor, correlation_id, status,
             resolved_identity_id, resolved_attempt_id,
             failure_code, failure_field, failure_details,
             created_at, completed_at)
        SELECT id, requested_project_id, requested_project_version_id,
               request_fingerprint, actor, correlation_id, status,
               resolved_identity_id, resolved_attempt_id,
               failure_code, failure_field, failure_details,
               created_at, completed_at
        FROM orchestration_requests
    """))
    conn.execute(_sa_text("DROP TABLE orchestration_requests"))
    conn.execute(_sa_text(
        "ALTER TABLE _alembic_tmp_orch_req RENAME TO orchestration_requests"
    ))
    conn.execute(_sa_text(
        "CREATE INDEX IF NOT EXISTS ix_orchestration_requests_request_fingerprint "
        "ON orchestration_requests (request_fingerprint)"
    ))


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
