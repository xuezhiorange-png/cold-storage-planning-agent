"""migration(issue-29): authority backfill and seal hardening

Revision ID: 451311827adf
Revises: e10f2c4d84e5
Create Date: 2026-07-02

Backfill scheme_weight_set_active_revisions from approved revisions,
fix immutability trigger (remove status from frozen fields, freeze
sealed_at/approved_at/approved_by), and add trigger to block direct
INSERT of approved status.
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "451311827adf"
down_revision: str | None = "e10f2c4d84e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Upgrade ─────────────────────────────────────────────────────────────────


def upgrade() -> None:
    dialect_name = op.get_context().dialect.name

    # 1. Authority backfill: populate scheme_weight_set_active_revisions from
    #    existing approved revisions.  Fails on duplicate approved per
    #    (weight_set_id, code) pair.
    _backfill_authority()

    # 2. Drop old triggers then recreate with corrected frozen fields
    if dialect_name == "sqlite":
        _sqlite_drop_triggers()
        _sqlite_create_triggers()
    else:
        _pg_drop_triggers()
        _pg_create_triggers()


# ── Downgrade ───────────────────────────────────────────────────────────────


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name

    # Drop current triggers and restore the old version (with status frozen)
    if dialect_name == "sqlite":
        _sqlite_drop_triggers()
        _sqlite_create_old_triggers()
    else:
        _pg_drop_triggers()
        _pg_create_old_triggers()

    # Remove backfilled authority rows
    op.execute(
        "DELETE FROM scheme_weight_set_active_revisions"
        " WHERE approved_revision_id IN ("
        "   SELECT id FROM scheme_weight_set_revisions"
        "   WHERE status = 'approved'"
        ")"
    )


# ═════════════════════════════════════════════════════════════════════════════
#  Authority backfill
# ═════════════════════════════════════════════════════════════════════════════


def _backfill_authority() -> None:
    """Insert authority rows for every unique approved revision.

    If a (weight_set_id, code) pair has more than one approved revision the
    migration aborts — this should never happen in production but is a
    safety net.
    """
    dialect_name = op.get_context().dialect.name

    if dialect_name == "sqlite":
        # SQLite doesn't support RAISE(ABORT) in plain SQL easily; use
        # Python-level check via a temp table.
        op.execute(
            "CREATE TEMPORARY TABLE _t_dup_check AS"
            " SELECT weight_set_id, code, COUNT(*) AS cnt"
            " FROM scheme_weight_set_revisions"
            " WHERE status = 'approved'"
            " GROUP BY weight_set_id, code"
            " HAVING COUNT(*) > 1"
        )
        dup_rows = (
            op.get_bind()
            .execute(text("SELECT weight_set_id, code, cnt FROM _t_dup_check"))
            .fetchall()
        )
        if dup_rows:
            details = ", ".join(f"({r[0]}, {r[1]}) x{r[2]}" for r in dup_rows)
            raise RuntimeError(
                f"Duplicate approved revisions found — cannot backfill authority: {details}"
            )
        op.execute("DROP TABLE _t_dup_check")
    else:
        # PostgreSQL: use DO block with RAISE EXCEPTION
        op.execute(
            "DO $$ BEGIN"
            " IF EXISTS ("
            "   SELECT 1 FROM scheme_weight_set_revisions"
            "   WHERE status = 'approved'"
            "   GROUP BY weight_set_id, code"
            "   HAVING COUNT(*) > 1"
            " ) THEN"
            "   RAISE EXCEPTION"
            " 'Duplicate approved revisions detected"
            " — cannot backfill authority';"
            " END IF;"
            " END $$;"
        )

    # Insert authority rows (idempotent — ignore if already present)
    if dialect_name == "sqlite":
        op.execute(
            "INSERT OR IGNORE INTO scheme_weight_set_active_revisions"
            " (weight_set_id, code, approved_revision_id, updated_at)"
            " SELECT weight_set_id, code, id, COALESCE(approved_at, created_at)"
            " FROM scheme_weight_set_revisions"
            " WHERE status = 'approved'"
        )
    else:
        # PostgreSQL: ON CONFLICT DO NOTHING
        op.execute(
            "INSERT INTO scheme_weight_set_active_revisions"
            " (weight_set_id, code, approved_revision_id, updated_at)"
            " SELECT weight_set_id, code, id, COALESCE(approved_at, created_at)"
            " FROM scheme_weight_set_revisions"
            " WHERE status = 'approved'"
            " ON CONFLICT (weight_set_id, code) DO NOTHING"
        )


# ═════════════════════════════════════════════════════════════════════════════
#  SQLite triggers (current — corrected)
# ═════════════════════════════════════════════════════════════════════════════


def _sqlite_create_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_weight_revision")

    # Immutability trigger — seals content fields, approved_at, approved_by,
    # sealed_at.  Does NOT freeze status (status transitions are handled by
    # the separate status-transition trigger).
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
        " OR NOT (NEW.approved_at IS OLD.approved_at)"
        " OR NOT (NEW.approved_by IS OLD.approved_by)"
        " OR NOT (NEW.sealed_at IS OLD.sealed_at)"
        ") BEGIN SELECT RAISE(ABORT,"
        " 'sealed revision immutability:"
        " immutable fields'); END;"
    )

    # Status transition trigger
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

    # Seal-on-approve trigger
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

    # Block direct INSERT of approved without seal
    op.execute(
        "CREATE TRIGGER trg_block_direct_approved_insert"
        " BEFORE INSERT ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN NEW.status = 'approved'"
        " AND NEW.sealed_at IS NULL"
        " BEGIN SELECT RAISE(ABORT,"
        " 'direct INSERT of approved is forbidden;"
        " use controlled draft→approved transition'); END;"
    )


def _sqlite_drop_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_weight_revision")
    op.execute("DROP TRIGGER IF EXISTS trg_weight_revision_status_transition")
    op.execute("DROP TRIGGER IF EXISTS trg_weight_revision_seal_on_approve")
    op.execute("DROP TRIGGER IF EXISTS trg_block_direct_approved_insert")


# ═════════════════════════════════════════════════════════════════════════════
#  SQLite triggers (old version — with status frozen, for downgrade)
# ═════════════════════════════════════════════════════════════════════════════


def _sqlite_create_old_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_weight_revision")

    # Old immutability trigger — freezes status (the pre-fix version)
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

    # Status transition trigger (unchanged)
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

    # Seal-on-approve trigger (unchanged)
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


# ═════════════════════════════════════════════════════════════════════════════
#  PostgreSQL triggers (current — corrected)
# ═════════════════════════════════════════════════════════════════════════════


def _pg_create_triggers() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_immutable_weight_revision ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_immutable_weight_revision")

    # Immutability function — seals content fields, approved_at, approved_by,
    # sealed_at.  Does NOT freeze status.
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
        " OR NEW.approved_at IS DISTINCT FROM OLD.approved_at"
        " OR NEW.approved_by IS DISTINCT FROM OLD.approved_by"
        " OR NEW.sealed_at IS DISTINCT FROM OLD.sealed_at)"
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

    # Status transition function (unchanged)
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

    # Seal-on-approve function (unchanged)
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

    # Block direct INSERT of approved without seal
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_block_direct_approved_insert()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF NEW.status = 'approved' AND NEW.sealed_at IS NULL THEN"
        " RAISE EXCEPTION"
        " 'direct INSERT of approved is forbidden;"
        " use controlled draft→approved transition';"
        " END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_block_direct_approved_insert"
        " BEFORE INSERT ON scheme_weight_set_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_block_direct_approved_insert();"
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

    op.execute(
        "DROP TRIGGER IF EXISTS trg_block_direct_approved_insert ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_block_direct_approved_insert")


# ═════════════════════════════════════════════════════════════════════════════
#  PostgreSQL triggers (old version — with status frozen, for downgrade)
# ═════════════════════════════════════════════════════════════════════════════


def _pg_create_old_triggers() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_immutable_weight_revision ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_immutable_weight_revision")

    # Old immutability function — freezes status
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

    # Status transition function (unchanged)
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

    # Seal-on-approve function (unchanged)
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
