"""Separate requested and resolved request identity.

Revision ID: 0027_separate_requested_and_resolved_request_identity
Revises: 0026_add_orchestration_persistence
Create Date: 2026-06-28

Reworks ``orchestration_requests`` so that raw caller-provided identity
(requested_project_id, requested_project_version_id) is preserved without
FK constraints, while resolved identity (resolved_project_id,
resolved_project_version_id) carries nullable FKs set only after
successful authoritative resolution.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0027_separate_requested_and_resolved_request_identity"
down_revision: str | None = "0026_add_orchestration_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_CONDITION = (
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

_OLD_CHECK_CONDITION = (
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


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name == "sqlite":
        _sqlite_migrate("upgrade")
    else:
        _pg_migrate("upgrade")


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name
    if dialect_name == "sqlite":
        _sqlite_migrate("downgrade")
    else:
        _pg_migrate("downgrade")


# ── PostgreSQL ──────────────────────────────────────────────────────────────


def _pg_migrate(direction: str) -> None:
    if direction == "upgrade":
        # Drop old CHECK + FKs
        op.drop_constraint("ck_orch_request_status_nullity", "orchestration_requests")
        op.drop_constraint("orchestration_requests_project_id_fkey", "orchestration_requests")
        op.drop_constraint(
            "orchestration_requests_project_version_id_fkey", "orchestration_requests"
        )
        # Rename
        op.alter_column("orchestration_requests", "project_id",
                        new_column_name="requested_project_id")
        op.alter_column("orchestration_requests", "project_version_id",
                        new_column_name="requested_project_version_id")
        # Add resolved columns
        op.add_column("orchestration_requests",
                      sa.Column("resolved_project_id", sa.String(36), nullable=True))
        op.add_column("orchestration_requests",
                      sa.Column("resolved_project_version_id", sa.String(36), nullable=True))
        # Add new FKs
        op.create_foreign_key("orchestration_requests_resolved_project_id_fkey",
                              "orchestration_requests", "projects",
                              ["resolved_project_id"], ["id"])
        op.create_foreign_key("orchestration_requests_resolved_project_version_id_fkey",
                              "orchestration_requests", "project_versions",
                              ["resolved_project_version_id"], ["id"])
        # Add new CHECK
        op.create_check_constraint("ck_orch_request_status_nullity",
                                   "orchestration_requests", _CHECK_CONDITION)
    else:
        # Downgrade: reverse
        op.drop_constraint("ck_orch_request_status_nullity", "orchestration_requests")
        op.drop_constraint(
            "orchestration_requests_resolved_project_version_id_fkey", "orchestration_requests"
        )
        op.drop_constraint(
            "orchestration_requests_resolved_project_id_fkey", "orchestration_requests"
        )
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
                                   "orchestration_requests", _OLD_CHECK_CONDITION)


# ── SQLite (table recreation — no production data exists) ───────────────────


def _sqlite_migrate(direction: str) -> None:
    """Recreate the table using raw SQL.

    ``batch_alter_table`` cannot add CHECK constraints on SQLite, so
    we recreate the table explicitly.  This is safe because the table
    was just created in 0026 and has no production rows.
    """
    if direction == "upgrade":
        _sqlite_recreate_with(_NEW_TABLE_SQL, _NEW_INDEX_SQL)
    else:
        _sqlite_recreate_with(_OLD_TABLE_SQL, _OLD_INDEX_SQL)


def _sqlite_recreate_with(table_sql: str, index_sql: str) -> None:
    op.execute("DROP TABLE IF EXISTS orchestration_requests")
    op.execute(table_sql)
    if index_sql:
        op.execute(index_sql)


_NEW_TABLE_SQL = """\
CREATE TABLE orchestration_requests (
    id VARCHAR(36) NOT NULL,
    requested_project_id VARCHAR(36) NOT NULL,
    requested_project_version_id VARCHAR(36) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(128) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    resolved_project_id VARCHAR(36),
    resolved_project_version_id VARCHAR(36),
    resolved_identity_id VARCHAR(36),
    resolved_attempt_id VARCHAR(36),
    failure_code VARCHAR(100),
    failure_field VARCHAR(200),
    failure_details JSON,
    created_at DATETIME NOT NULL,
    completed_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY (resolved_project_id) REFERENCES projects (id),
    FOREIGN KEY (resolved_project_version_id) REFERENCES project_versions (id),
    FOREIGN KEY (resolved_identity_id) REFERENCES orchestration_identities (id),
    FOREIGN KEY (resolved_attempt_id) REFERENCES orchestration_run_attempts (id),
    CHECK (""" + _CHECK_CONDITION + """\
)
)"""

_NEW_INDEX_SQL = (
    "CREATE INDEX ix_orchestration_requests_request_fingerprint "
    "ON orchestration_requests (request_fingerprint)"
)

_OLD_TABLE_SQL = """\
CREATE TABLE orchestration_requests (
    id VARCHAR(36) NOT NULL,
    project_id VARCHAR(36) NOT NULL,
    project_version_id VARCHAR(36) NOT NULL,
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
    PRIMARY KEY (id),
    FOREIGN KEY (project_id) REFERENCES projects (id),
    FOREIGN KEY (project_version_id) REFERENCES project_versions (id),
    FOREIGN KEY (resolved_identity_id) REFERENCES orchestration_identities (id),
    FOREIGN KEY (resolved_attempt_id) REFERENCES orchestration_run_attempts (id),
    CHECK (""" + _OLD_CHECK_CONDITION + """\
)
)"""

_OLD_INDEX_SQL = (
    "CREATE INDEX ix_orchestration_requests_request_fingerprint "
    "ON orchestration_requests (request_fingerprint)"
)
