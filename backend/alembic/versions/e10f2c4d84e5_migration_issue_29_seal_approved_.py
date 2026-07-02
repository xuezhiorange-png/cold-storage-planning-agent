"""migration(issue-29): seal approved revisions and enforce authority FK

Revision ID: e10f2c4d84e5
Revises: 0032_add_active_revisions_authority_and_immutability_triggers
Create Date: 2026-07-02

Add sealed_at column to scheme_weight_set_revisions for permanent
immutability tracking, backfill existing approved revisions, add FK
from active_revisions.authority to revisions, replace old immutability
triggers with sealed_at-based logic, and add status-transition and
seal-on-approve triggers.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e10f2c4d84e5"
down_revision: str | None = "0032_add_active_revisions_authority_and_immutability_triggers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Upgrade ─────────────────────────────────────────────────────────────────


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name

    # 1. Add sealed_at column (NULL for all rows initially)
    op.execute("ALTER TABLE scheme_weight_set_revisions ADD COLUMN sealed_at TIMESTAMP NULL")

    # 2. Backfill sealed_at: for non-draft revisions, set to approved_at
    #    (or created_at if approved_at is NULL)
    op.execute(
        "UPDATE scheme_weight_set_revisions"
        " SET sealed_at = COALESCE(approved_at, created_at)"
        " WHERE status != 'draft'"
    )

    # 3. FK from active_revisions.approved_revision_id → revisions.id
    #    SQLite doesn't support ALTER TABLE ADD CONSTRAINT for FKs;
    #    recreate the table with the FK defined inline.
    if dialect_name == "sqlite":
        op.execute(
            "CREATE TABLE scheme_weight_set_active_revisions_new ("
            "  weight_set_id VARCHAR(36) NOT NULL,"
            "  code VARCHAR(120) NOT NULL,"
            "  approved_revision_id VARCHAR(36) NOT NULL,"
            "  updated_at TIMESTAMP NOT NULL,"
            "  PRIMARY KEY (weight_set_id, code),"
            "  FOREIGN KEY (approved_revision_id)"
            "    REFERENCES scheme_weight_set_revisions(id)"
            "    ON DELETE RESTRICT"
            ")"
        )
        op.execute(
            "INSERT INTO scheme_weight_set_active_revisions_new"
            " SELECT * FROM scheme_weight_set_active_revisions"
        )
        op.execute("DROP TABLE scheme_weight_set_active_revisions")
        op.execute(
            "ALTER TABLE scheme_weight_set_active_revisions_new"
            " RENAME TO scheme_weight_set_active_revisions"
        )
    else:
        op.execute(
            "ALTER TABLE scheme_weight_set_active_revisions"
            " ADD CONSTRAINT fk_active_revision_ref"
            " FOREIGN KEY (approved_revision_id)"
            " REFERENCES scheme_weight_set_revisions(id)"
            " ON DELETE RESTRICT"
        )

    # 4–6. Create triggers (dialect-specific)
    if dialect_name == "sqlite":
        _sqlite_create_triggers()
    else:
        _pg_create_triggers()


# ── Downgrade ───────────────────────────────────────────────────────────────


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name

    # 1. Drop triggers (dialect-specific)
    if dialect_name == "sqlite":
        _sqlite_drop_triggers()
    else:
        _pg_drop_triggers()

    # 2. Drop FK constraint
    #    SQLite FK is inline in table definition, so recreate table without it.
    if dialect_name == "sqlite":
        op.execute(
            "CREATE TABLE scheme_weight_set_active_revisions_new ("
            "  weight_set_id VARCHAR(36) NOT NULL,"
            "  code VARCHAR(120) NOT NULL,"
            "  approved_revision_id VARCHAR(36) NOT NULL,"
            "  updated_at TIMESTAMP NOT NULL,"
            "  PRIMARY KEY (weight_set_id, code)"
            ")"
        )
        op.execute(
            "INSERT INTO scheme_weight_set_active_revisions_new"
            " SELECT * FROM scheme_weight_set_active_revisions"
        )
        op.execute("DROP TABLE scheme_weight_set_active_revisions")
        op.execute(
            "ALTER TABLE scheme_weight_set_active_revisions_new"
            " RENAME TO scheme_weight_set_active_revisions"
        )
    else:
        op.execute(
            "ALTER TABLE scheme_weight_set_active_revisions"
            " DROP CONSTRAINT IF EXISTS fk_active_revision_ref"
        )

    # 3. Drop sealed_at column
    op.execute("ALTER TABLE scheme_weight_set_revisions DROP COLUMN sealed_at")


# ═════════════════════════════════════════════════════════════════════════════
#  SQLite triggers
# ═════════════════════════════════════════════════════════════════════════════


def _sqlite_create_triggers() -> None:
    # Drop old trigger if it exists (idempotent upgrade/downgrade)
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_weight_revision")

    # 4. Immutability trigger — sealed_at based
    op.execute(
        "CREATE TRIGGER trg_immutable_weight_revision"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN OLD.sealed_at IS NOT NULL AND ("
        " NOT (NEW.content IS OLD.content)"
        " OR NOT (NEW.content_hash IS OLD.content_hash)"
        " OR NOT (NEW.code IS OLD.code)"
        " OR NOT (NEW.revision IS OLD.revision)"
        " OR NOT (NEW.weight_set_id IS OLD.weight_set_id)"
        " OR NOT (NEW.generator_compatibility_version"
        "   IS OLD.generator_compatibility_version)"
        " OR NOT (NEW.status IS OLD.status)"
        ") BEGIN SELECT RAISE(ABORT,"
        " 'sealed revision immutability:"
        " immutable fields'); END;"
    )

    # 5. Status transition trigger
    op.execute(
        "CREATE TRIGGER trg_weight_revision_status_transition"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN OLD.status != NEW.status AND NOT ("
        " (OLD.status = 'draft' AND NEW.status = 'approved')"
        " OR (OLD.status = 'approved' AND NEW.status = 'superseded')"
        " OR (OLD.status = 'approved' AND NEW.status = 'revoked')"
        ") BEGIN SELECT RAISE(ABORT,"
        " 'invalid status transition'); END;"
    )

    # 6. Seal-on-approve trigger
    op.execute(
        "CREATE TRIGGER trg_weight_revision_seal_on_approve"
        " AFTER UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN OLD.status = 'draft'"
        " AND NEW.status = 'approved'"
        " BEGIN"
        " UPDATE scheme_weight_set_revisions"
        " SET sealed_at = CURRENT_TIMESTAMP"
        " WHERE id = NEW.id;"
        " END;"
    )


def _sqlite_drop_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_weight_revision")
    op.execute("DROP TRIGGER IF EXISTS trg_weight_revision_status_transition")
    op.execute("DROP TRIGGER IF EXISTS trg_weight_revision_seal_on_approve")


# ═════════════════════════════════════════════════════════════════════════════
#  PostgreSQL triggers
# ═════════════════════════════════════════════════════════════════════════════


def _pg_create_triggers() -> None:
    # Drop old trigger/function if they exist (idempotent upgrade/downgrade)
    op.execute(
        "DROP TRIGGER IF EXISTS trg_immutable_weight_revision ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_immutable_weight_revision")

    # 4. Immutability function — sealed_at based
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_immutable_weight_revision()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF OLD.sealed_at IS NOT NULL AND ("
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
        " OLD.generator_compatibility_version"
        " OR NEW.status IS DISTINCT FROM OLD.status)"
        " THEN RAISE EXCEPTION"
        " 'sealed revision immutability:"
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

    # 5. Status transition function
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_weight_revision_status_transition()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF OLD.status != NEW.status AND NOT ("
        " (OLD.status = 'draft' AND NEW.status = 'approved')"
        " OR (OLD.status = 'approved' AND NEW.status = 'superseded')"
        " OR (OLD.status = 'approved' AND NEW.status = 'revoked')"
        " ) THEN RAISE EXCEPTION"
        " 'invalid status transition';"
        " END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_weight_revision_status_transition"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_weight_revision_status_transition();"
    )

    # 6. Seal-on-approve function
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_weight_revision_seal_on_approve()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF OLD.status = 'draft' AND NEW.status = 'approved' THEN"
        " NEW.sealed_at := CURRENT_TIMESTAMP;"
        " END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_weight_revision_seal_on_approve"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_weight_revision_seal_on_approve();"
    )


def _pg_drop_triggers() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_immutable_weight_revision ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_immutable_weight_revision")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_weight_revision_status_transition"
        " ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_weight_revision_status_transition")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_weight_revision_seal_on_approve ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_weight_revision_seal_on_approve")
