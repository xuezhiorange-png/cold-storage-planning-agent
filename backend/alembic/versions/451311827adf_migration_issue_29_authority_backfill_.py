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
        # 3. Authority lifecycle triggers (must be created after seal_on_approve)
        _sqlite_create_authority_triggers()
    else:
        _pg_drop_triggers()
        _pg_create_triggers()
        # 3. Authority lifecycle triggers
        _pg_create_authority_triggers()


# ── Downgrade ───────────────────────────────────────────────────────────────


def downgrade() -> None:
    dialect_name = op.get_context().dialect.name

    # Step 1: Drop ALL triggers (authority + revision) to avoid
    # dangling references when tables are dropped in earlier migrations.
    if dialect_name == "sqlite":
        _sqlite_drop_authority_triggers()
        _sqlite_drop_triggers()
        # Also drop any seal_on_approve that may exist from older states
        op.execute("DROP TRIGGER IF EXISTS trg_weight_revision_seal_on_approve")
    else:
        _pg_drop_authority_triggers()
        _pg_drop_triggers()

    # Step 2: Remove backfilled authority rows (safe now — no guard triggers)
    import contextlib

    with contextlib.suppress(Exception):
        op.execute(
            "DELETE FROM scheme_weight_set_active_revisions"
            " WHERE approved_revision_id IN ("
            "   SELECT id FROM scheme_weight_set_revisions"
            "   WHERE status = 'approved'"
            ")"
        )

    # Step 3: Restore old revision triggers
    if dialect_name == "sqlite":
        _sqlite_create_old_triggers()
    else:
        _pg_create_old_triggers()


# ═════════════════════════════════════════════════════════════════════════════
#  Authority backfill
# ═════════════════════════════════════════════════════════════════════════════


def _backfill_authority() -> None:
    """Backfill scheme_weight_set_active_revisions — fail closed.

    Step 1: Read all approved revisions grouped by (weight_set_id, code).
    Step 2: If any group has >1 approved revision, RAISE error with details.
    Step 3: Read all existing authority rows.
    Step 4: For each existing authority row, verify consistency.
    Step 5: For each approved revision without an authority row, INSERT.
    Step 6: After all inserts, verify final state.
    """
    bind = op.get_bind()

    # Step 1 & 2: Check for duplicate approved revisions per (weight_set_id, code)
    dup_rows = bind.execute(
        text(
            "SELECT weight_set_id, code, COUNT(*) AS cnt"
            " FROM scheme_weight_set_revisions"
            " WHERE status = 'approved'"
            " GROUP BY weight_set_id, code"
            " HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dup_rows:
        details = ", ".join(f"({r[0]}, {r[1]}) x{r[2]}" for r in dup_rows)
        raise RuntimeError(
            f"Duplicate approved revisions found — cannot backfill authority: {details}"
        )

    # Step 3: Read all existing authority rows
    existing_authorities = bind.execute(
        text(
            "SELECT weight_set_id, code, approved_revision_id"
            " FROM scheme_weight_set_active_revisions"
        )
    ).fetchall()

    # Step 4: Verify each existing authority row
    for auth in existing_authorities:
        ws_id, code, rev_id = auth[0], auth[1], auth[2]
        rev = bind.execute(
            text(
                "SELECT weight_set_id, code, status"
                " FROM scheme_weight_set_revisions"
                " WHERE id = :rev_id"
            ),
            {"rev_id": rev_id},
        ).fetchone()
        if rev is None:
            raise RuntimeError(
                f"Authority row references non-existent revision {rev_id}"
                f" for (weight_set_id={ws_id}, code={code})"
            )
        if rev[2] != "approved":
            raise RuntimeError(
                f"Authority row for (weight_set_id={ws_id}, code={code})"
                f" references revision {rev_id} with status '{rev[2]}'"
                f" (expected 'approved')"
            )
        if rev[0] != ws_id:
            raise RuntimeError(
                f"Authority row for (weight_set_id={ws_id}, code={code})"
                f" references revision {rev_id} with weight_set_id={rev[0]}"
            )
        if rev[1] != code:
            raise RuntimeError(
                f"Authority row for (weight_set_id={ws_id}, code={code})"
                f" references revision {rev_id} with code='{rev[1]}'"
            )

    # Step 5: Insert authority rows for approved revisions without one
    approved_revisions = bind.execute(
        text(
            "SELECT id, weight_set_id, code,"
            " COALESCE(approved_at, created_at)"
            " FROM scheme_weight_set_revisions"
            " WHERE status = 'approved'"
        )
    ).fetchall()

    existing_rev_ids = {auth[2] for auth in existing_authorities}
    for rev in approved_revisions:
        rev_id, ws_id, code, ts = rev[0], rev[1], rev[2], rev[3]
        if rev_id not in existing_rev_ids:
            try:
                bind.execute(
                    text(
                        "INSERT INTO scheme_weight_set_active_revisions"
                        " (weight_set_id, code, approved_revision_id, updated_at)"
                        " VALUES (:ws_id, :code, :rev_id, :ts)"
                    ),
                    {"ws_id": ws_id, "code": code, "rev_id": rev_id, "ts": ts},
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to insert authority row for"
                    f" (weight_set_id={ws_id}, code={code},"
                    f" revision_id={rev_id}): {exc}"
                ) from exc

    # Step 6: Verify final state — counts must match
    final_count = bind.execute(
        text("SELECT COUNT(*) FROM scheme_weight_set_active_revisions")
    ).fetchone()[0]
    approved_count = len(approved_revisions)
    if final_count != approved_count:
        raise RuntimeError(
            f"Final state mismatch: {final_count} authority rows"
            f" but {approved_count} approved revisions"
        )

    # Step 6b: Verify each authority row points to an approved revision
    # with matching (weight_set_id, code)
    mismatched = bind.execute(
        text(
            "SELECT a.weight_set_id, a.code, a.approved_revision_id,"
            " r.weight_set_id, r.code, r.status"
            " FROM scheme_weight_set_active_revisions a"
            " JOIN scheme_weight_set_revisions r"
            " ON a.approved_revision_id = r.id"
            " WHERE r.status != 'approved'"
            " OR a.weight_set_id != r.weight_set_id"
            " OR a.code != r.code"
        )
    ).fetchall()
    if mismatched:
        details = ", ".join(
            f"(auth ws={m[0]},code={m[1]},rev={m[2]} -> rev ws={m[3]},code={m[4]},status={m[5]})"
            for m in mismatched
        )
        raise RuntimeError(f"Authority rows reference invalid revisions after backfill: {details}")


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

    # Note: seal_on_approve is now handled by trg_authority_claim_and_seal
    # (combined seal + authority claim in a single trigger for atomicity).

    # Block ALL direct INSERT of approved status
    op.execute(
        "CREATE TRIGGER trg_block_direct_approved_insert"
        " BEFORE INSERT ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN NEW.status = 'approved'"
        " BEGIN SELECT RAISE(ABORT,"
        " 'direct INSERT of approved is forbidden;"
        " use controlled draft→approved transition'); END;"
    )


def _sqlite_drop_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_immutable_weight_revision")
    op.execute("DROP TRIGGER IF EXISTS trg_weight_revision_status_transition")
    # Drop seal_on_approve if it exists from older migrations (now handled by claim_and_seal)
    op.execute("DROP TRIGGER IF EXISTS trg_weight_revision_seal_on_approve")
    op.execute("DROP TRIGGER IF EXISTS trg_block_direct_approved_insert")


# ═════════════════════════════════════════════════════════════════════════════
#  SQLite authority lifecycle triggers
# ═════════════════════════════════════════════════════════════════════════════


def _sqlite_create_authority_triggers() -> None:
    """Create triggers that manage authority rows on status transitions.

    - trg_authority_claim_and_seal:
        AFTER UPDATE draft→approved → set sealed_at + INSERT authority (unified).
    - trg_authority_release_on_supersede:
        AFTER UPDATE approved→superseded|revoked → DELETE authority.
    - trg_authority_insert_guard:
        BEFORE INSERT on authority table → validate revision exists & matches.
    - trg_authority_update_guard:
        BEFORE UPDATE on authority table → reject all updates.
    - trg_authority_delete_guard:
        BEFORE DELETE on authority table → reject if revision still approved.
    """
    # Drop if they exist (idempotent rebuild)
    _sqlite_drop_authority_triggers()

    # BEFORE UPDATE authority check: atomic approval uniqueness
    op.execute(
        "CREATE TRIGGER trg_authority_check_on_approve"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN OLD.status = 'draft'"
        " AND NEW.status = 'approved'"
        " BEGIN"
        " SELECT CASE WHEN EXISTS"
        " (SELECT 1 FROM scheme_weight_set_revisions"
        " WHERE weight_set_id = NEW.weight_set_id"
        " AND code = NEW.code"
        " AND status = 'approved'"
        " AND id != NEW.id)"
        " THEN RAISE(ABORT, 'active_revision_conflict:"
        " another revision already approved for this weight_set_id/code')"
        " END; END;"
    )

    # Unified claim + seal: draft → approved
    op.execute(
        "CREATE TRIGGER trg_authority_claim_and_seal"
        " AFTER UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN OLD.status = 'draft'"
        " AND NEW.status = 'approved'"
        " BEGIN"
        " UPDATE scheme_weight_set_revisions"
        " SET sealed_at = CURRENT_TIMESTAMP"
        " WHERE id = NEW.id;"
        " INSERT INTO scheme_weight_set_active_revisions"
        " (weight_set_id, code, approved_revision_id, updated_at)"
        " VALUES (NEW.weight_set_id, NEW.code, NEW.id,"
        " CURRENT_TIMESTAMP);"
        " END;"
    )

    # Release: approved → superseded | revoked
    op.execute(
        "CREATE TRIGGER trg_authority_release_on_supersede"
        " AFTER UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW WHEN OLD.status = 'approved'"
        " AND NEW.status IN ('superseded', 'revoked')"
        " BEGIN"
        " DELETE FROM scheme_weight_set_active_revisions"
        " WHERE weight_set_id = OLD.weight_set_id"
        " AND code = OLD.code;"
        " END;"
    )

    # ── Authority table validation triggers ──────────────────────────────
    # INSERT guard: validate revision exists, is approved, matches identity
    op.execute(
        "CREATE TRIGGER trg_authority_insert_guard"
        " BEFORE INSERT ON scheme_weight_set_active_revisions"
        " FOR EACH ROW BEGIN"
        " SELECT CASE WHEN NOT EXISTS"
        " (SELECT 1 FROM scheme_weight_set_revisions"
        " WHERE id = NEW.approved_revision_id"
        " AND status = 'approved'"
        " AND weight_set_id = NEW.weight_set_id"
        " AND code = NEW.code)"
        " THEN RAISE(ABORT, 'authority insert guard:"
        " revision must exist, be approved, and match weight_set_id/code')"
        " END; END;"
    )

    # UPDATE guard: reject all direct updates to authority rows
    op.execute(
        "CREATE TRIGGER trg_authority_update_guard"
        " BEFORE UPDATE ON scheme_weight_set_active_revisions"
        " FOR EACH ROW BEGIN"
        " SELECT RAISE(ABORT, 'authority update guard:"
        " direct UPDATE of authority rows is forbidden'); END;"
    )

    # DELETE guard: reject deletion if revision is still approved
    op.execute(
        "CREATE TRIGGER trg_authority_delete_guard"
        " BEFORE DELETE ON scheme_weight_set_active_revisions"
        " FOR EACH ROW BEGIN"
        " SELECT CASE WHEN EXISTS"
        " (SELECT 1 FROM scheme_weight_set_revisions"
        " WHERE id = OLD.approved_revision_id"
        " AND status = 'approved')"
        " THEN RAISE(ABORT, 'authority delete guard:"
        " cannot delete authority while revision is approved')"
        " END; END;"
    )


def _sqlite_drop_authority_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_authority_check_on_approve")
    op.execute("DROP TRIGGER IF EXISTS trg_authority_claim_and_seal")
    op.execute("DROP TRIGGER IF EXISTS trg_authority_release_on_supersede")
    op.execute("DROP TRIGGER IF EXISTS trg_authority_insert_guard")
    op.execute("DROP TRIGGER IF EXISTS trg_authority_update_guard")
    op.execute("DROP TRIGGER IF EXISTS trg_authority_delete_guard")


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

    # Block ALL direct INSERT of approved status
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_block_direct_approved_insert()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF NEW.status = 'approved' THEN"
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
#  PostgreSQL authority lifecycle triggers
# ═════════════════════════════════════════════════════════════════════════════


def _pg_create_authority_triggers() -> None:
    """Create triggers that manage authority rows on status transitions.

    - trg_authority_claim_on_approve  (AFTER UPDATE): draft → approved
    - trg_authority_release_on_supersede (AFTER UPDATE): approved → superseded|revoked
    - trg_authority_insert_guard (BEFORE INSERT): validate revision
    - trg_authority_update_guard (BEFORE UPDATE): reject all updates
    - trg_authority_delete_guard (BEFORE DELETE): reject if revision approved
    """
    # Drop if they exist (idempotent rebuild)
    _pg_drop_authority_triggers()

    # BEFORE UPDATE authority check function + trigger
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_check_on_approve ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_check_on_approve")
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_authority_check_on_approve()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF OLD.status = 'draft' AND NEW.status = 'approved' THEN"
        " IF EXISTS ("
        " SELECT 1 FROM scheme_weight_set_revisions"
        " WHERE weight_set_id = NEW.weight_set_id"
        " AND code = NEW.code"
        " AND status = 'approved'"
        " AND id != NEW.id"
        " ) THEN RAISE EXCEPTION"
        " 'active_revision_conflict:"
        " another revision already approved for this weight_set_id/code';"
        " END IF; END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_authority_check_on_approve"
        " BEFORE UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_authority_check_on_approve();"
    )

    # Claim function + trigger
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_claim_on_approve ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_claim_on_approve")
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_authority_claim_on_approve()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF OLD.status = 'draft' AND NEW.status = 'approved' THEN"
        " INSERT INTO scheme_weight_set_active_revisions"
        " (weight_set_id, code, approved_revision_id, updated_at)"
        " VALUES (NEW.weight_set_id, NEW.code, NEW.id, NOW());"
        " END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_authority_claim_on_approve"
        " AFTER UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_authority_claim_on_approve();"
    )

    # Release function + trigger
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_release_on_supersede ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_release_on_supersede")
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_authority_release_on_supersede()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF OLD.status = 'approved'"
        " AND NEW.status IN ('superseded', 'revoked') THEN"
        " DELETE FROM scheme_weight_set_active_revisions"
        " WHERE weight_set_id = OLD.weight_set_id"
        " AND code = OLD.code;"
        " END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_authority_release_on_supersede"
        " AFTER UPDATE ON scheme_weight_set_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_authority_release_on_supersede();"
    )

    # ── Authority table validation triggers (PG) ────────────────────────
    # INSERT guard
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_insert_guard ON scheme_weight_set_active_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_insert_guard")
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_authority_insert_guard()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF NOT EXISTS ("
        " SELECT 1 FROM scheme_weight_set_revisions"
        " WHERE id = NEW.approved_revision_id"
        " AND status = 'approved'"
        " AND weight_set_id = NEW.weight_set_id"
        " AND code = NEW.code"
        " ) THEN RAISE EXCEPTION"
        " 'authority insert guard:"
        " revision must exist, be approved, and match weight_set_id/code';"
        " END IF; RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_authority_insert_guard"
        " BEFORE INSERT ON scheme_weight_set_active_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_authority_insert_guard();"
    )

    # UPDATE guard: reject all direct updates
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_update_guard ON scheme_weight_set_active_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_update_guard")
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_authority_update_guard()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " RAISE EXCEPTION"
        " 'authority update guard:"
        " direct UPDATE of authority rows is forbidden';"
        " RETURN NEW; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_authority_update_guard"
        " BEFORE UPDATE ON scheme_weight_set_active_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_authority_update_guard();"
    )

    # DELETE guard: reject if revision still approved
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_delete_guard ON scheme_weight_set_active_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_delete_guard")
    op.execute(
        "CREATE OR REPLACE FUNCTION"
        " fn_authority_delete_guard()"
        " RETURNS TRIGGER AS $$ BEGIN"
        " IF EXISTS ("
        " SELECT 1 FROM scheme_weight_set_revisions"
        " WHERE id = OLD.approved_revision_id"
        " AND status = 'approved'"
        " ) THEN RAISE EXCEPTION"
        " 'authority delete guard:"
        " cannot delete authority while revision is approved';"
        " END IF; RETURN OLD; END;"
        " $$ LANGUAGE plpgsql;"
    )
    op.execute(
        "CREATE TRIGGER trg_authority_delete_guard"
        " BEFORE DELETE ON scheme_weight_set_active_revisions"
        " FOR EACH ROW"
        " EXECUTE FUNCTION fn_authority_delete_guard();"
    )


def _pg_drop_authority_triggers() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_claim_on_approve ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_claim_on_approve")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_authority_release_on_supersede ON scheme_weight_set_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_authority_release_on_supersede")


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
