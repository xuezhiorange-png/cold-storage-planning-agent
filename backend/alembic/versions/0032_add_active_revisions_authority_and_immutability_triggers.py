"""Add active-revisions authority table and approved immutability triggers.

Revision ID: 0032_add_active_revisions_authority_and_immutability_triggers
Revises: 0031_add_weight_revision_active_approved_unique
Create Date: 2026-07-02

P0-2: scheme_weight_set_active_revisions table with UNIQUE(
  weight_set_id, code) provides atomic concurrent-safe approval authority.
P0-3: BEFORE UPDATE triggers on scheme_weight_set_revisions block
  modifications to immutable fields of approved revisions.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032_add_active_revisions_authority_and_immutability_triggers"
down_revision: str | None = "0031_add_weight_revision_active_approved_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name

    # 1. Create active-revisions authority table
    op.execute(
        "CREATE TABLE scheme_weight_set_active_revisions ("
        "  weight_set_id VARCHAR(36) NOT NULL,"
        "  code VARCHAR(120) NOT NULL,"
        "  approved_revision_id VARCHAR(36) NOT NULL,"
        "  updated_at TIMESTAMP NOT NULL,"
        "  PRIMARY KEY (weight_set_id, code)"
        ")"
    )

    # 2. Create immutability triggers
    if dialect_name == "sqlite":
        _sqlite_create_trigger()
    else:
        _pg_create_trigger()


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name

    # 1. Drop immutability triggers
    if dialect_name == "sqlite":
        _sqlite_drop_trigger()
    else:
        _pg_drop_trigger()

    # 2. Drop active-revisions authority table
    op.execute("DROP TABLE IF EXISTS scheme_weight_set_active_revisions")


# ── SQLite ─────────────────────────────────────────────────────────────────


def _sqlite_create_trigger() -> None:
    op.execute(
        "CREATE TRIGGER trg_immutable_weight_revision"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN OLD.status = 'approved' AND ("
        " NOT (NEW.content IS OLD.content)"
        " OR NOT (NEW.content_hash IS OLD.content_hash)"
        " OR NOT (NEW.code IS OLD.code)"
        " OR NOT (NEW.revision IS OLD.revision)"
        " OR NOT (NEW.weight_set_id IS OLD.weight_set_id)"
        " OR NOT (NEW.generator_compatibility_version"
        "   IS OLD.generator_compatibility_version)"
        ") BEGIN SELECT RAISE(ABORT,"
        " 'approved revision immutability:"
        " immutable fields'); END;"
    )


def _sqlite_drop_trigger() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_weight_revision")


# ── PostgreSQL ─────────────────────────────────────────────────────────────


def _pg_create_trigger() -> None:
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_immutable_weight_revision()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF OLD.status = 'approved' AND ("
        " NEW.content::text IS DISTINCT FROM"
        " OLD.content::text"
        " OR NEW.content_hash IS DISTINCT FROM"
        " OLD.content_hash"
        " OR NEW.code IS DISTINCT FROM OLD.code"
        " OR NEW.revision IS DISTINCT FROM OLD.revision"
        " OR NEW.weight_set_id IS DISTINCT FROM"
        " OLD.weight_set_id"
        " OR NEW.generator_compatibility_version"
        " IS DISTINCT FROM"
        " OLD.generator_compatibility_version)"
        " THEN RAISE EXCEPTION"
        " 'approved revision immutability:"
        " immutable fields';"
        " END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_immutable_weight_revision"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_immutable_weight_revision();"
    )


def _pg_drop_trigger() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_immutable_weight_revision ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_immutable_weight_revision")
