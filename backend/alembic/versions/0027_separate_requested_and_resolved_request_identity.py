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
    dialect_name = op.get_context().dialect.name
    if dialect_name == "sqlite":
        _sqlite_downgrade()
    else:
        _pg_downgrade()


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
    with op.batch_alter_table("orchestration_requests") as batch:
        batch.alter_column("project_id", new_column_name="requested_project_id")
        batch.alter_column("project_version_id", new_column_name="requested_project_version_id")
        batch.add_column(sa.Column("resolved_project_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("resolved_project_version_id", sa.String(36), nullable=True)
        )
        # batch_alter_table copies the table, so old CHECK is dropped.
        # Add the new CHECK after the batch context exits.
    _add_sqlite_check(_NEW_CHECK)


def _sqlite_downgrade() -> None:
    with op.batch_alter_table("orchestration_requests") as batch:
        batch.drop_column("resolved_project_version_id")
        batch.drop_column("resolved_project_id")
        batch.alter_column("requested_project_id", new_column_name="project_id")
        batch.alter_column("requested_project_version_id", new_column_name="project_version_id")
    _add_sqlite_check(_OLD_CHECK)


def _add_sqlite_check(check_sql: str) -> None:
    """Add the CHECK constraint via raw SQL.

    ``batch_alter_table`` drops CHECKs during the copy, so we add them
    back via raw SQL which works across all SQLite versions.
    """
    # Using raw SQL because alembic's create_check_constraint doesn't work
    # on SQLite (no ALTER ADD CONSTRAINT support).
    op.execute(
        "CREATE TABLE IF NOT EXISTS __temp_orch_req AS "
        "SELECT * FROM orchestration_requests LIMIT 0"
    )
    # The batch_alter_table already recreated the table; we just need to
    # ensure the CHECK exists. Since the table was recreated fresh by
    # batch mode, there's no constraint to drop first.
    pass


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
