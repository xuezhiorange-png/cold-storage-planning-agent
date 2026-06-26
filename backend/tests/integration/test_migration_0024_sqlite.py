"""Test 0024 migration (fix receipt status CHECK and deleted_at semantics) on SQLite.

Verifies that the 0024_receipt_status_deleted_at migration:

Upgrade:
- Drops and recreates ck_deletion_receipt_status allowing 'delete_failed'
- Makes deleted_at nullable and removes default

Downgrade:
- Restores original CHECK constraint (status IN ('intent','deleted'))
- Restores deleted_at NOT NULL + server_default now()

Runtime behaviour:
- INSERT with status='delete_failed' succeeds
- INSERT with unknown status raises IntegrityError
- INSERT with status='intent' has NULL deleted_at
- INSERT with status='delete_failed' has NULL deleted_at
- INSERT with status='deleted' has a non-NULL deleted_at
- Retry (intent after deleted) clears deleted_at
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess

import pytest

# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),  # …/tests/integration
    "..",  # …/tests
    "..",  # …/backend
)


def _run_alembic(
    args: list[str],
    db_path: str,
    *,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """Run ``uv run alembic <args>`` against a temporary SQLite database."""
    env = os.environ.copy()
    env["DATABASE_BACKEND"] = "sqlite"
    env["SQLITE_PATH"] = db_path
    env["PYTHONPATH"] = "src"

    result = subprocess.run(
        ["uv", "run", "alembic"] + args,
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


# ---------------------------------------------------------------------------
# SQLite schema introspection helpers
# ---------------------------------------------------------------------------


def _get_columns(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cursor.fetchall()}
    conn.close()
    return cols


def _get_column_nullable(db_path: str, table: str, column: str) -> bool:
    """Return True if the column is nullable (notnull == 0)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA table_info({table})")
    for row in cursor.fetchall():
        if row[1] == column:
            # row[3] is the 'notnull' flag: 0 = nullable, 1 = NOT NULL
            conn.close()
            return row[3] == 0
    conn.close()
    raise ValueError(f"Column {column} not found in {table}")


def _get_column_default(db_path: str, table: str, column: str) -> str | None:
    """Return the default value SQL expression for a column, or None."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA table_info({table})")
    for row in cursor.fetchall():
        if row[1] == column:
            # row[4] is dflt_value
            conn.close()
            return row[4]
    conn.close()
    raise ValueError(f"Column {column} not found in {table}")


def _get_check_constraints(db_path: str, table: str) -> set[str]:
    """Return set of CHECK constraint names for a table (SQLite >= 3.26)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return set()
    sql = row[0]
    names = set()
    for match in re.finditer(r"CONSTRAINT\s+(\w+)\s+CHECK", sql, re.IGNORECASE):
        names.add(match.group(1))
    return names


def _get_check_sql(db_path: str, table: str, constraint: str) -> str | None:
    """Return the CHECK constraint SQL text for a given constraint name."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    sql = row[0]
    # Find the constraint definition
    pattern = rf"CONSTRAINT\s+{re.escape(constraint)}\s+CHECK\s*\(([^)]+)\)"
    match = re.search(pattern, sql, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _get_unique_constraint_names(db_path: str, table: str) -> set[str]:
    """Return set of UNIQUE constraint names from table SQL (via sqlite_master)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return set()
    sql = row[0]
    names = set()
    for match in re.finditer(r"CONSTRAINT\s+(\w+)\s+UNIQUE", sql, re.IGNORECASE):
        names.add(match.group(1))
    return names


# ---------------------------------------------------------------------------
# Shared expected schema — HEAD (0024)
# ---------------------------------------------------------------------------

ALL_DELETION_RECEIPTS_COLUMNS = {
    "storage_key",
    "stale_claim_token",
    "stale_claim_version",
    "reclaim_token",
    "reclaim_version",
    "deleted_at",
    "deletion_hash",
    "status",
}

DELETION_RECEIPTS_CHECK_CONSTRAINTS = {
    "ck_deletion_receipt_stale_version",
    "ck_deletion_receipt_reclaim_version",
    "ck_deletion_receipt_hash",
    "ck_deletion_receipt_status",
}

DELETION_RECEIPTS_UNIQUE_CONSTRAINTS = {
    "uq_deletion_receipt_owners",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_db(tmp_path):
    """Yield the path to a temporary SQLite database file."""
    db_path = str(tmp_path / "test_0024.db")
    yield db_path


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestSQLiteDeletionReceiptMigration0024:
    """Real Alembic upgrade → downgrade → upgrade cycle for 0024 on SQLite."""

    # -- upgrade head (0024) -------------------------------------------------

    def test_upgrade_keeps_deletion_receipts_table(self, temp_db):
        """upgrade head keeps deletion_receipts table with all columns."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns, got: {cols}"
        )

    def test_upgrade_keeps_deletion_receipts_check_constraints(self, temp_db):
        """upgrade head keeps all deletion_receipts CHECK constraints."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "deletion_receipts")
        assert checks == DELETION_RECEIPTS_CHECK_CONSTRAINTS, (
            f"Expected deletion_receipts CHECK constraints "
            f"{DELETION_RECEIPTS_CHECK_CONSTRAINTS}, got: {checks}"
        )

    def test_upgrade_updates_status_check_to_include_delete_failed(self, temp_db):
        """upgrade head updates ck_deletion_receipt_status to allow delete_failed."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None, "ck_deletion_receipt_status not found"
        assert "delete_failed" in check_sql, (
            f"ck_deletion_receipt_status should include 'delete_failed', got: {check_sql}"
        )

    def test_upgrade_makes_deleted_at_nullable_and_removes_default(self, temp_db):
        """upgrade head makes deleted_at nullable and removes server_default."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        assert _get_column_nullable(temp_db, "deletion_receipts", "deleted_at"), (
            "deleted_at should be nullable after upgrade"
        )
        default = _get_column_default(temp_db, "deletion_receipts", "deleted_at")
        assert default is None, f"deleted_at should have no default after upgrade, got: {default!r}"

    # -- downgrade 0023 (revert 0024 changes) --------------------------------

    def test_downgrade_restores_status_check_to_original(self, temp_db):
        """downgrade to 0023 restores original status CHECK constraint."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None, "ck_deletion_receipt_status not found"
        assert "delete_failed" not in check_sql, (
            f"ck_deletion_receipt_status should NOT include 'delete_failed', got: {check_sql}"
        )

    def test_downgrade_restores_deleted_at_not_null_and_default(self, temp_db):
        """downgrade to 0023 restores deleted_at NOT NULL + server_default."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        assert not _get_column_nullable(temp_db, "deletion_receipts", "deleted_at"), (
            "deleted_at should be NOT NULL after downgrade"
        )
        default = _get_column_default(temp_db, "deletion_receipts", "deleted_at")
        assert default is not None, "deleted_at should have a default after downgrade"

    # -- re-upgrade head -----------------------------------------------------

    def test_reupgrade_restores_all_constraints(self, temp_db):
        """re-upgrade head restores CHECK constraints and nullable deleted_at."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        checks = _get_check_constraints(temp_db, "deletion_receipts")
        assert checks == DELETION_RECEIPTS_CHECK_CONSTRAINTS

        uq = _get_unique_constraint_names(temp_db, "deletion_receipts")
        assert uq == DELETION_RECEIPTS_UNIQUE_CONSTRAINTS

        assert _get_column_nullable(temp_db, "deletion_receipts", "deleted_at"), (
            "deleted_at should be nullable after re-upgrade"
        )

    # -- Runtime behaviour: CHECK enforcement --------------------------------

    def test_sqlite_receipt_allows_delete_failed(self, temp_db):
        """INSERT with status='delete_failed' succeeds."""
        _run_alembic(["upgrade", "head"], temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sk-df", "tok1", 0, "tok2", 0, "hash123", "delete_failed"),
        )
        conn.commit()
        conn.close()

    def test_sqlite_receipt_rejects_unknown_status(self, temp_db):
        """INSERT with unknown status raises IntegrityError."""
        _run_alembic(["upgrade", "head"], temp_db)

        conn = sqlite3.connect(temp_db)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO deletion_receipts "
                "(storage_key, stale_claim_token, stale_claim_version, "
                "reclaim_token, reclaim_version, deletion_hash, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("sk-bad", "tok1", 0, "tok2", 0, "hash789", "unknown"),
            )
            conn.commit()
        conn.close()

    # -- Runtime behaviour: deleted_at semantics -----------------------------

    def test_receipt_intent_has_null_deleted_at(self, temp_db):
        """INSERT with status='intent' sets deleted_at to NULL."""
        _run_alembic(["upgrade", "head"], temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sk-intent", "tok1", 0, "tok2", 0, "hash456", "intent"),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-intent",),
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None, f"deleted_at should be NULL for intent receipt, got: {row[0]!r}"

    def test_receipt_delete_failed_has_null_deleted_at(self, temp_db):
        """INSERT with status='delete_failed' sets deleted_at to NULL."""
        _run_alembic(["upgrade", "head"], temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sk-df2", "tok1", 0, "tok2", 0, "hashabc", "delete_failed"),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-df2",),
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None, (
            f"deleted_at should be NULL for delete_failed receipt, got: {row[0]!r}"
        )

    def test_receipt_deleted_has_actual_deleted_at(self, temp_db):
        """INSERT with status='deleted' sets deleted_at to a timestamp."""
        _run_alembic(["upgrade", "head"], temp_db)

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("sk-del", "tok1", 0, "tok2", 0, "hashdef", "deleted", "2026-06-25 12:00:00"),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-del",),
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] is not None, "deleted_at should NOT be NULL for deleted receipt"

    def test_receipt_retry_clears_previous_deleted_at(self, temp_db):
        """UPSERT retry (intent after deleted) clears deleted_at to NULL."""
        _run_alembic(["upgrade", "head"], temp_db)

        conn = sqlite3.connect(temp_db)
        # Insert a deleted receipt with a timestamp
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("sk-retry", "tok1", 0, "tok2", 0, "hashxyz", "deleted", "2026-06-25 12:00:00"),
        )
        conn.commit()

        # Upsert with status='intent' (simulating a retry)
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(storage_key) DO UPDATE SET "
            "stale_claim_token=excluded.stale_claim_token, "
            "stale_claim_version=excluded.stale_claim_version, "
            "reclaim_token=excluded.reclaim_token, "
            "reclaim_version=excluded.reclaim_version, "
            "deletion_hash=excluded.deletion_hash, "
            "status=excluded.status, "
            "deleted_at=excluded.deleted_at",
            ("sk-retry", "tok1", 0, "tok2", 0, "hashnew", "intent"),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-retry",),
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "intent", f"Expected status='intent', got: {row[0]!r}"
        assert row[1] is None, f"deleted_at should be NULL after retry as intent, got: {row[1]!r}"

    # -- Existence of deletion_outbox table is unchanged ---------------------

    def test_deletion_outbox_still_intact(self, temp_db):
        """upgrade head preserves deletion_outbox table and its constraints."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0

        checks = _get_check_constraints(temp_db, "deletion_outbox")
        assert "ck_deletion_outbox_status" in checks
        assert "ck_deletion_outbox_actor_not_empty" in checks
        assert "ck_deletion_outbox_reason_not_empty" in checks
        assert "ck_deletion_outbox_retry_count" in checks

    # -- Cross-head upgrade: 0024 (published) → head (through 0025) ---------

    def test_sqlite_upgrade_from_published_0024_revision(self, temp_db):
        """Upgrade from OLD 0024 revision to head works and adds 0025 columns."""
        # 1. Upgrade to OLD 0024 revision
        result = _run_alembic(["upgrade", "0024_fix_receipt_status_and_deleted_at"], temp_db)
        assert result.returncode == 0, f"upgrade to 0024 failed:\n{result.stderr}"

        # Verify 0024 schema is in place
        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns, got: {cols}"
        )
        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None
        assert "delete_failed" in check_sql, (
            f"ck_deletion_receipt_status should include 'delete_failed', got: {check_sql}"
        )
        assert _get_column_nullable(temp_db, "deletion_receipts", "deleted_at"), (
            "deleted_at should be nullable"
        )

        # Verify deletion_outbox does NOT yet have 0025 columns
        outbox_cols_before = _get_columns(temp_db, "deletion_outbox")
        assert "claim_token" not in outbox_cols_before
        assert "claim_version" not in outbox_cols_before
        assert "locked_at" not in outbox_cols_before
        assert "lock_expires_at" not in outbox_cols_before

        # 2. Upgrade head — should apply 0025
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"upgrade to head (through 0025) failed:\n{result.stderr}"

        # Verify 0025 columns now exist in deletion_outbox
        outbox_cols_after = _get_columns(temp_db, "deletion_outbox")
        for col in ("claim_token", "claim_version", "locked_at", "lock_expires_at"):
            assert col in outbox_cols_after, (
                f"deletion_outbox should have {col} after head, got: {outbox_cols_after}"
            )

        # Verify 0025 CHECK constraint on claim_version
        checks = _get_check_constraints(temp_db, "deletion_outbox")
        assert "ck_deletion_outbox_claim_version" in checks, (
            f"Expected ck_deletion_outbox_claim_version, got: {checks}"
        )

        # Verify 0024 schema still intact
        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS
        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None
        assert "delete_failed" in check_sql
        assert _get_column_nullable(temp_db, "deletion_receipts", "deleted_at")

    def test_sqlite_published_0024_data_survives_upgrade(self, temp_db):
        """Data inserted under published 0024 persists after upgrade through 0025."""
        # 1. Upgrade to OLD 0024 revision
        result = _run_alembic(["upgrade", "0024_fix_receipt_status_and_deleted_at"], temp_db)
        assert result.returncode == 0, f"upgrade to 0024 failed:\n{result.stderr}"

        # 2. Insert test data (a receipt with status='delete_failed' and deleted_at=NULL)
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sk-cross-upgrade", "tok1", 0, "tok2", 0, "hash_cross_001", "delete_failed"),
        )
        conn.commit()

        # Verify the data was inserted correctly
        cursor = conn.execute(
            "SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-cross-upgrade",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "delete_failed", f"Expected delete_failed, got {row[0]!r}"
        assert row[1] is None, "deleted_at should be NULL for delete_failed receipt"
        conn.close()

        # 3. Record alembic_version = '0024_fix_receipt_status_and_deleted_at'
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT version_num FROM alembic_version")
        version_row = cursor.fetchone()
        assert version_row is not None
        assert version_row[0] == "0024_fix_receipt_status_and_deleted_at", (
            f"Expected version 0024_fix_receipt_status_and_deleted_at, got {version_row[0]!r}"
        )
        conn.close()

        # 4. Run alembic upgrade head — goes through 0025
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"upgrade head failed:\n{result.stderr}"

        # 5. Verify the test data still exists in deletion_receipts
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-cross-upgrade",),
        )
        row = cursor.fetchone()
        assert row is not None, "Data should survive upgrade through 0025"
        assert row[0] == "delete_failed", f"status should still be 'delete_failed', got {row[0]!r}"
        assert row[1] is None, "deleted_at should still be NULL"

        # 6. Verify deletion_receipts.status allows 'delete_failed'
        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None
        assert "delete_failed" in check_sql

        # 7. Verify deleted_at is nullable
        assert _get_column_nullable(temp_db, "deletion_receipts", "deleted_at")

        # 8. Verify deletion_outbox has 0025 columns
        outbox_cols = _get_columns(temp_db, "deletion_outbox")
        for col in ("claim_token", "claim_version", "locked_at", "lock_expires_at"):
            assert col in outbox_cols, (
                f"deletion_outbox should have {col} after head, got: {outbox_cols}"
            )
        conn.close()

    # -- Downgrade with delete_failed data -----------------------------------

    def test_sqlite_0024_downgrade_with_delete_failed_row(self, temp_db):
        """Downrade from 0024 with a delete_failed receipt normalizes the row."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"upgrade failed:\n{result.stderr}"

        # Insert a delete_failed receipt row
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO deletion_receipts "
            "(storage_key, stale_claim_token, stale_claim_version, "
            "reclaim_token, reclaim_version, deletion_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sk-downgrade-df", "tok1", 0, "tok2", 0, "hash123", "delete_failed"),
        )
        conn.commit()

        # Verify the row exists with delete_failed
        cursor = conn.execute(
            "SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-downgrade-df",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "delete_failed"
        assert row[1] is None  # delete_failed has NULL deleted_at
        conn.close()

        # Downgrade to 0023 — should normalize the delete_failed row
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], temp_db)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        # Verify the row was converted: status='intent', deleted_at is set
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-downgrade-df",),
        )
        row = cursor.fetchone()
        assert row is not None, "Row should still exist after downgrade"
        assert row[0] == "intent", f"Expected status='intent' after downgrade, got: {row[0]!r}"
        assert row[1] is not None, "deleted_at should be set after downgrade normalization"
        conn.close()

        # Verify the old CHECK constraint is in place (no delete_failed)
        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None
        assert "delete_failed" not in check_sql

        # Upgrade head again — should work
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        # Verify row is still there after re-upgrade
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT status, deleted_at FROM deletion_receipts WHERE storage_key=?",
            ("sk-downgrade-df",),
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "intent"

    # -- Full roundtrip ------------------------------------------------------

    def test_0024_full_roundtrip(self, temp_db):
        """Full roundtrip: upgrade 0024 → downgrade 0023 → upgrade 0024."""
        # 1. upgrade to head (0024)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"initial upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS
        assert _get_column_nullable(temp_db, "deletion_receipts", "deleted_at")

        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None and "delete_failed" in check_sql

        # 2. downgrade to 0023
        result = _run_alembic(["downgrade", "0023_deletion_outbox_receipts"], temp_db)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        assert not _get_column_nullable(temp_db, "deletion_receipts", "deleted_at")
        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None and "delete_failed" not in check_sql

        # 3. re-upgrade to head (0024)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS
        assert _get_column_nullable(temp_db, "deletion_receipts", "deleted_at")

        check_sql = _get_check_sql(temp_db, "deletion_receipts", "ck_deletion_receipt_status")
        assert check_sql is not None and "delete_failed" in check_sql
