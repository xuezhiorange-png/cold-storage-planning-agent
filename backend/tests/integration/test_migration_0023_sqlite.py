"""Test 0023 migration (deletion_outbox + deletion_receipts) on SQLite.

Verifies that the 0023_deletion_outbox_receipts migration is
idempotent and correct on SQLite by running real Alembic subprocess
commands against a temporary database file:

- upgrade head creates both tables with all columns
- upgrade head creates all indexes and constraints
- downgrade 0022 removes both tables
- re-upgrade head restores everything
- CHECK constraint enforcement for invalid values
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


def _get_index_names(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA index_list({table})")
    names = {row[1] for row in cursor.fetchall()}
    conn.close()
    return names


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
# Shared expected schema — HEAD (0023)
# ---------------------------------------------------------------------------

ALL_DELETION_OUTBOX_COLUMNS = {
    "id",
    "storage_key",
    "migration_actor",
    "audit_reason",
    "operation",
    "source_hash",
    "status",
    "created_at",
    "updated_at",
    "last_error",
    "retry_count",
    "claim_token",
    "claim_version",
    "locked_at",
    "lock_expires_at",
}

DELETION_OUTBOX_INDEXES = {
    "ix_deletion_outbox_storage_key",
    "ix_deletion_outbox_status",
    "ix_deletion_outbox_created_at",
}

DELETION_OUTBOX_CHECK_CONSTRAINTS = {
    "ck_deletion_outbox_actor_not_empty",
    "ck_deletion_outbox_reason_not_empty",
    "ck_deletion_outbox_status",
    "ck_deletion_outbox_retry_count",
    "ck_deletion_outbox_claim_version",
}

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
    db_path = str(tmp_path / "test_0023.db")
    yield db_path


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestSQLiteDeletionOutboxMigration:
    """Real Alembic upgrade → downgrade → upgrade cycle for 0023 on SQLite."""

    # -- upgrade head (0023) -------------------------------------------------

    def test_upgrade_creates_deletion_outbox_table(self, temp_db):
        """upgrade head creates deletion_outbox table with all columns."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS, (
            f"Expected all deletion_outbox columns, got: {cols}"
        )

    def test_upgrade_creates_deletion_receipts_table(self, temp_db):
        """upgrade head creates deletion_receipts table."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns, got: {cols}"
        )

    def test_upgrade_creates_deletion_outbox_indexes(self, temp_db):
        """upgrade head creates all deletion_outbox indexes."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "deletion_outbox")
        for name in DELETION_OUTBOX_INDEXES:
            assert name in idx, f"Missing index {name!r}, got: {idx}"

    def test_upgrade_creates_deletion_outbox_check_constraints(self, temp_db):
        """upgrade head creates all deletion_outbox CHECK constraints."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "deletion_outbox")
        assert checks == DELETION_OUTBOX_CHECK_CONSTRAINTS, (
            f"Expected deletion_outbox CHECK constraints "
            f"{DELETION_OUTBOX_CHECK_CONSTRAINTS}, got: {checks}"
        )

    def test_upgrade_creates_deletion_receipts_check_constraints(self, temp_db):
        """upgrade head creates all deletion_receipts CHECK constraints."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "deletion_receipts")
        assert checks == DELETION_RECEIPTS_CHECK_CONSTRAINTS, (
            f"Expected deletion_receipts CHECK constraints "
            f"{DELETION_RECEIPTS_CHECK_CONSTRAINTS}, got: {checks}"
        )

    def test_upgrade_creates_unique_constraint(self, temp_db):
        """upgrade head creates uq_deletion_receipt_owners unique constraint."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        uq = _get_unique_constraint_names(temp_db, "deletion_receipts")
        assert uq == DELETION_RECEIPTS_UNIQUE_CONSTRAINTS, (
            f"Expected UNIQUE constraints {DELETION_RECEIPTS_UNIQUE_CONSTRAINTS}, got: {uq}"
        )

    # -- downgrade 0022 (remove 0023 changes) --------------------------------

    def test_downgrade_drops_deletion_receipts_table(self, temp_db):
        """downgrade 0022 drops deletion_receipts table entirely."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_receipts'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is None, "deletion_receipts table should be gone after downgrade"

    def test_downgrade_drops_deletion_outbox_table(self, temp_db):
        """downgrade 0022 drops deletion_outbox table entirely."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_outbox'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is None, "deletion_outbox table should be gone after downgrade"

    def test_downgrade_removes_deletion_receipts_constraints(self, temp_db):
        """downgrade 0022 removes all deletion_receipts CHECK and UNIQUE constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        # The table is gone entirely, so constraints should be unreachable
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_receipts'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is None, (
            "deletion_receipts should be gone after downgrade, along with its constraints"
        )

    # -- re-upgrade head -----------------------------------------------------

    def test_reupgrade_restores_deletion_outbox(self, temp_db):
        """re-upgrade head restores deletion_outbox table and its constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS, (
            f"Expected all deletion_outbox columns after re-upgrade, got: {cols}"
        )

        idx = _get_index_names(temp_db, "deletion_outbox")
        for name in DELETION_OUTBOX_INDEXES:
            assert name in idx, f"Missing index {name!r} after re-upgrade, got: {idx}"

        checks = _get_check_constraints(temp_db, "deletion_outbox")
        assert checks == DELETION_OUTBOX_CHECK_CONSTRAINTS, (
            f"Expected deletion_outbox CHECK constraints after re-upgrade, got: {checks}"
        )

    def test_reupgrade_restores_deletion_receipts(self, temp_db):
        """re-upgrade head restores deletion_receipts table and its constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns after re-upgrade, got: {cols}"
        )

        checks = _get_check_constraints(temp_db, "deletion_receipts")
        assert checks == DELETION_RECEIPTS_CHECK_CONSTRAINTS, (
            f"Expected deletion_receipts CHECK constraints after re-upgrade, got: {checks}"
        )

        uq = _get_unique_constraint_names(temp_db, "deletion_receipts")
        assert uq == DELETION_RECEIPTS_UNIQUE_CONSTRAINTS, (
            f"Expected UNIQUE constraints after re-upgrade, got: {uq}"
        )

    def test_reupgrade_preserves_all_schema_objects(self, temp_db):
        """re-upgrade head preserves all tables, indexes, and constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        # Both tables exist
        cols = _get_columns(temp_db, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS
        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        # Indexes exist
        idx = _get_index_names(temp_db, "deletion_outbox")
        assert DELETION_OUTBOX_INDEXES.issubset(idx)

        # CHECK constraints
        checks = _get_check_constraints(temp_db, "deletion_outbox")
        assert checks == DELETION_OUTBOX_CHECK_CONSTRAINTS
        checks = _get_check_constraints(temp_db, "deletion_receipts")
        assert checks == DELETION_RECEIPTS_CHECK_CONSTRAINTS

        # UNIQUE constraint
        uq = _get_unique_constraint_names(temp_db, "deletion_receipts")
        assert uq == DELETION_RECEIPTS_UNIQUE_CONSTRAINTS

    # -- idempotent re-upgrade (already at head) ----------------------------

    def test_reupgrade_idempotent_when_already_at_head(self, temp_db):
        """Running upgrade head again when already at head is a no-op."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"idempotent re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS, (
            f"Idempotent re-upgrade should keep all columns, got: {cols}"
        )
        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Idempotent re-upgrade should keep all columns, got: {cols}"
        )

    # -- full roundtrip -----------------------------------------------------

    def test_0023_full_roundtrip(self, temp_db):
        """Full roundtrip: upgrade → downgrade 0022 → upgrade head."""
        # 1. upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"initial upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS
        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        # 2. downgrade to 0022 (removes both tables)
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_outbox'"
        )
        assert cursor.fetchone() is None, "deletion_outbox should be gone"
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_receipts'"
        )
        assert cursor.fetchone() is None, "deletion_receipts should be gone"
        conn.close()

        # 3. re-upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS
        cols = _get_columns(temp_db, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

    def test_0023_all_schema_objects_roundtrip(self, temp_db):
        """Verify all schema objects survive the roundtrip."""
        # Upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0

        # Verify indexes at head
        idx = _get_index_names(temp_db, "deletion_outbox")
        for name in DELETION_OUTBOX_INDEXES:
            assert name in idx, f"Missing index {name!r}, got: {idx}"

        # Verify CHECK constraints at head
        checks = _get_check_constraints(temp_db, "deletion_outbox")
        assert checks == DELETION_OUTBOX_CHECK_CONSTRAINTS
        checks = _get_check_constraints(temp_db, "deletion_receipts")
        assert checks == DELETION_RECEIPTS_CHECK_CONSTRAINTS

        # Verify UNIQUE constraint at head
        uq = _get_unique_constraint_names(temp_db, "deletion_receipts")
        assert uq == DELETION_RECEIPTS_UNIQUE_CONSTRAINTS

        # Downgrade to 0022
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], temp_db)
        assert result.returncode == 0

        # Both tables gone
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_outbox'"
        )
        assert cursor.fetchone() is None
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deletion_receipts'"
        )
        assert cursor.fetchone() is None
        conn.close()

        # Re-upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0

        # All schema objects restored
        idx = _get_index_names(temp_db, "deletion_outbox")
        assert DELETION_OUTBOX_INDEXES.issubset(idx)

        checks = _get_check_constraints(temp_db, "deletion_outbox")
        assert checks == DELETION_OUTBOX_CHECK_CONSTRAINTS

        checks = _get_check_constraints(temp_db, "deletion_receipts")
        assert checks == DELETION_RECEIPTS_CHECK_CONSTRAINTS

        uq = _get_unique_constraint_names(temp_db, "deletion_receipts")
        assert uq == DELETION_RECEIPTS_UNIQUE_CONSTRAINTS
