"""Test 0020→0021→0022 migration roundtrip (cleanup_debt + audit_log) on SQLite.

Verifies that the 0020_add_cleanup_debt, 0021_cleanup_debt_lock_expires,
and 0022_add_claim_version_audit_log migrations are idempotent and correct
on SQLite by running real Alembic subprocess commands against a temporary
database file:

- upgrade head creates cleanup_debt with claim_version + migration_audit_log
- downgrade 0021 removes claim_version + drops migration_audit_log
- re-upgrade head restores them
- all columns, indexes, CHECK constraints, and UNIQUE constraints verified
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


def _index_is_unique(db_path: str, index_name: str) -> bool:
    """Check if an index is unique by scanning PRAGMA index_list."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("PRAGMA index_list(cleanup_debt)")
    for row in cursor.fetchall():
        if row[1] == index_name:
            conn.close()
            return bool(row[2])  # unique column
    conn.close()
    return False


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
    # Extract CHECK constraint names from CREATE TABLE SQL
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
# Shared expected schema — HEAD (0022)
# ---------------------------------------------------------------------------

ALL_CLEANUP_DEBT_COLUMNS = {
    "id",
    "idempotency_key",
    "storage_key",
    "stale_claim_token",
    "stale_claim_version",
    "reclaim_token",
    "reclaim_version",
    "status",
    "created_at",
    "completed_at",
    "retry_count",
    "last_error",
    "next_retry_at",
    "locked_at",
    "locked_by",
    "lock_expires_at",  # added by 0021
    "claim_version",  # added by 0022
}

COLUMNS_WITHOUT_0022 = ALL_CLEANUP_DEBT_COLUMNS - {"claim_version"}

COLUMNS_WITHOUT_LOCK_EXPIRES = COLUMNS_WITHOUT_0022 - {"lock_expires_at"}

HEAD_INDEXES = {
    "ix_cleanup_debt_idempotency_key",
    "ix_cleanup_debt_status",
    "ix_cleanup_debt_next_retry_at",
    "ix_cleanup_debt_lock_expires_at",  # added by 0021
}

INDEXES_WITHOUT_LOCK_EXPIRES = HEAD_INDEXES - {"ix_cleanup_debt_lock_expires_at"}

HEAD_CHECK_CONSTRAINTS = {
    "ck_cleanup_debt_status",
    "ck_cleanup_debt_stale_claim_version",
    "ck_cleanup_debt_reclaim_version",
    "ck_cleanup_debt_retry_count",
    "ck_cleanup_debt_claim_version",  # added by 0022
}

CHECK_CONSTRAINTS_WITHOUT_0022 = HEAD_CHECK_CONSTRAINTS - {"ck_cleanup_debt_claim_version"}

ALL_UNIQUE_CONSTRAINTS = {
    "uq_cleanup_debt_stale_file",
}

# -- migration_audit_log (added by 0022) --

ALL_MIGRATION_AUDIT_LOG_COLUMNS = {
    "id",
    "storage_key",
    "migration_actor",
    "audit_reason",
    "operation",
    "result",
    "source_hash",
    "created_at",
}

MIGRATION_AUDIT_LOG_INDEXES = {
    "ix_migration_audit_log_storage_key",
    "ix_migration_audit_log_created_at",
}

MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS = {
    "ck_migration_audit_log_actor_not_empty",
    "ck_migration_audit_log_reason_not_empty",
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_db(tmp_path):
    """Yield the path to a temporary SQLite database file."""
    db_path = str(tmp_path / "test_0020_0022.db")
    yield db_path


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestSQLiteCleanupDebtMigration:
    """Real Alembic upgrade → downgrade → upgrade cycle for 0020/0021/0022 on SQLite."""

    # -- upgrade head (0022) -------------------------------------------------

    def test_upgrade_creates_cleanup_debt_table(self, temp_db):
        """upgrade head creates cleanup_debt table with all columns (incl. claim_version)."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, f"Expected all columns, got: {cols}"

    def test_upgrade_creates_migration_audit_log_table(self, temp_db):
        """upgrade head creates migration_audit_log table."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "migration_audit_log")
        assert cols == ALL_MIGRATION_AUDIT_LOG_COLUMNS, (
            f"Expected migration_audit_log columns, got: {cols}"
        )

    def test_upgrade_creates_cleanup_debt_indexes(self, temp_db):
        """upgrade head creates all cleanup_debt indexes."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "cleanup_debt")
        assert HEAD_INDEXES.issubset(idx), f"Expected subset of {HEAD_INDEXES}, got: {idx}"

    def test_upgrade_creates_migration_audit_log_indexes(self, temp_db):
        """upgrade head creates migration_audit_log indexes."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "migration_audit_log")
        for name in MIGRATION_AUDIT_LOG_INDEXES:
            assert name in idx, f"Missing index {name!r}, got: {idx}"

    def test_upgrade_creates_check_constraints(self, temp_db):
        """upgrade head creates all CHECK constraints incl. claim_version."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "cleanup_debt")
        assert checks == HEAD_CHECK_CONSTRAINTS, (
            f"Expected CHECK constraints {HEAD_CHECK_CONSTRAINTS}, got: {checks}"
        )

    def test_upgrade_creates_migration_audit_log_check_constraints(self, temp_db):
        """upgrade head creates audit log CHECK constraints."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "migration_audit_log")
        assert checks == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK constraints {MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS}, "
            f"got: {checks}"
        )

    def test_upgrade_creates_unique_constraint(self, temp_db):
        """upgrade head creates uq_cleanup_debt_stale_file unique constraint."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        uq = _get_unique_constraint_names(temp_db, "cleanup_debt")
        assert uq == ALL_UNIQUE_CONSTRAINTS, (
            f"Expected UNIQUE constraints {ALL_UNIQUE_CONSTRAINTS}, got: {uq}"
        )

    # -- downgrade 0021 (remove 0022 changes) --------------------------------

    def test_downgrade_removes_claim_version_column(self, temp_db):
        """downgrade 0021 removes claim_version column from cleanup_debt."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "cleanup_debt")
        assert cols == COLUMNS_WITHOUT_0022, f"Expected columns without claim_version, got: {cols}"

    def test_downgrade_drops_migration_audit_log_table(self, temp_db):
        """downgrade 0021 drops migration_audit_log table entirely."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_audit_log'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is None, "migration_audit_log table should be gone after downgrade"

    def test_downgrade_removes_claim_version_check_constraint(self, temp_db):
        """downgrade 0021 removes ck_cleanup_debt_claim_version CHECK."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "cleanup_debt")
        assert checks == CHECK_CONSTRAINTS_WITHOUT_0022, (
            f"Expected CHECK constraints without claim_version, got: {checks}"
        )

    def test_downgrade_preserves_other_cleanup_debt_constraints(self, temp_db):
        """downgrade 0021 keeps other cleanup_debt CHECK and UNIQUE constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "cleanup_debt")
        assert checks == CHECK_CONSTRAINTS_WITHOUT_0022, (
            f"Expected CHECK constraints preserved, got: {checks}"
        )

        uq = _get_unique_constraint_names(temp_db, "cleanup_debt")
        assert uq == ALL_UNIQUE_CONSTRAINTS, f"Expected UNIQUE constraints preserved, got: {uq}"

    # -- re-upgrade head -----------------------------------------------------

    def test_reupgrade_restores_claim_version(self, temp_db):
        """re-upgrade head restores claim_version column and ck_cleanup_debt_claim_version."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, (
            f"Expected all columns after re-upgrade, got: {cols}"
        )

        checks = _get_check_constraints(temp_db, "cleanup_debt")
        assert "ck_cleanup_debt_claim_version" in checks, (
            f"Missing ck_cleanup_debt_claim_version after re-upgrade, got: {checks}"
        )

    def test_reupgrade_restores_migration_audit_log(self, temp_db):
        """re-upgrade head restores migration_audit_log table and its constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "migration_audit_log")
        assert cols == ALL_MIGRATION_AUDIT_LOG_COLUMNS, (
            f"Expected all migration_audit_log columns after re-upgrade, got: {cols}"
        )

        idx = _get_index_names(temp_db, "migration_audit_log")
        for name in MIGRATION_AUDIT_LOG_INDEXES:
            assert name in idx, f"Missing index {name!r} after re-upgrade, got: {idx}"

        checks = _get_check_constraints(temp_db, "migration_audit_log")
        assert checks == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK constraints after re-upgrade, got: {checks}"
        )

    def test_reupgrade_restores_indexes(self, temp_db):
        """re-upgrade head restores all indexes."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "cleanup_debt")
        assert HEAD_INDEXES.issubset(idx), (
            f"Expected subset of {HEAD_INDEXES} after re-upgrade, got: {idx}"
        )

    def test_reupgrade_preserves_constraints(self, temp_db):
        """re-upgrade head preserves all CHECK and UNIQUE constraints."""
        _run_alembic(["upgrade", "head"], temp_db)
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        checks = _get_check_constraints(temp_db, "cleanup_debt")
        assert checks == HEAD_CHECK_CONSTRAINTS, (
            f"Expected all CHECK constraints after re-upgrade, got: {checks}"
        )

        uq = _get_unique_constraint_names(temp_db, "cleanup_debt")
        assert uq == ALL_UNIQUE_CONSTRAINTS, (
            f"Expected UNIQUE constraints preserved after re-upgrade, got: {uq}"
        )

    # -- idempotent re-upgrade (already at head) ----------------------------

    def test_reupgrade_idempotent_when_already_at_head(self, temp_db):
        """Running upgrade head again when already at head is a no-op."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"idempotent re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, (
            f"Idempotent re-upgrade should keep all columns, got: {cols}"
        )

    # -- full roundtrip -----------------------------------------------------

    def test_cleanup_debt_0020_0022_roundtrip(self, temp_db):
        """Full roundtrip: upgrade → downgrade 0021 → upgrade head."""
        # 1. upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"initial upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, f"Missing columns after upgrade, got: {cols}"

        # 2. downgrade to 0021 (removes claim_version + migration_audit_log)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "cleanup_debt")
        assert "claim_version" not in cols, "claim_version should be gone after downgrade 0021"

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_audit_log'"
        )
        assert cursor.fetchone() is None, "migration_audit_log table should be gone"
        conn.close()

        # 3. re-upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, (
            f"Expected all columns after re-upgrade, got: {cols}"
        )

        cols = _get_columns(temp_db, "migration_audit_log")
        assert cols == ALL_MIGRATION_AUDIT_LOG_COLUMNS, (
            f"Expected migration_audit_log after re-upgrade, got: {cols}"
        )

    def test_cleanup_debt_0020_0022_all_schema_objects(self, temp_db):
        """Verify all schema objects survive the roundtrip."""
        # Upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0

        # Verify indexes at head
        idx = _get_index_names(temp_db, "cleanup_debt")
        assert "ix_cleanup_debt_idempotency_key" in idx
        assert "ix_cleanup_debt_status" in idx
        assert "ix_cleanup_debt_next_retry_at" in idx
        assert "ix_cleanup_debt_lock_expires_at" in idx

        # Verify CHECK constraints at head
        checks = _get_check_constraints(temp_db, "cleanup_debt")
        for name in HEAD_CHECK_CONSTRAINTS:
            assert name in checks, f"Missing CHECK {name!r}, got: {checks}"

        # Verify migration_audit_log constraints at head
        audit_checks = _get_check_constraints(temp_db, "migration_audit_log")
        assert audit_checks == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK at head, got: {audit_checks}"
        )

        # Downgrade to 0021
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], temp_db)
        assert result.returncode == 0

        # claim_version gone
        checks = _get_check_constraints(temp_db, "cleanup_debt")
        assert "ck_cleanup_debt_claim_version" not in checks, (
            "ck_cleanup_debt_claim_version should be gone after downgrade"
        )
        assert checks == CHECK_CONSTRAINTS_WITHOUT_0022, (
            f"Expected CHECK constraints without claim_version, got: {checks}"
        )

        # migration_audit_log gone
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_audit_log'"
        )
        assert cursor.fetchone() is None, "migration_audit_log table should be gone"
        conn.close()

        # Re-upgrade to head
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0

        # All indexes restored
        idx = _get_index_names(temp_db, "cleanup_debt")
        assert HEAD_INDEXES.issubset(idx), f"Expected subset of {HEAD_INDEXES}, got: {idx}"

        # All CHECK constraints restored
        checks = _get_check_constraints(temp_db, "cleanup_debt")
        assert checks == HEAD_CHECK_CONSTRAINTS, (
            f"Expected all CHECK constraints after re-upgrade, got: {checks}"
        )

        # migration_audit_log restored
        audit_checks = _get_check_constraints(temp_db, "migration_audit_log")
        assert audit_checks == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK after re-upgrade, got: {audit_checks}"
        )

        idx = _get_index_names(temp_db, "migration_audit_log")
        for name in MIGRATION_AUDIT_LOG_INDEXES:
            assert name in idx, f"Missing audit log index {name!r} after re-upgrade, got: {idx}"

    # -- CHECK constraint enforcement ---------------------------------------

    def test_check_constraint_status_enforced(self, temp_db):
        """SQLite rejects invalid status via ck_cleanup_debt_status CHECK."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO cleanup_debt "
                "(id, idempotency_key, storage_key, stale_claim_token, "
                "stale_claim_version, reclaim_token, reclaim_version, status, "
                "created_at, retry_count, last_error, locked_by) "
                "VALUES ('test-bad-status', 'ik1', 'sk1', "
                "'tok1', 0, 'tok2', 0, 'invalid_status', "
                "'2026-06-25T00:00:00', 0, '', '')"
            )
            conn.commit()
            pytest.fail("Expected sqlite3.IntegrityError for invalid status")
        except sqlite3.IntegrityError as e:
            assert "ck_cleanup_debt_status" in str(e), f"Expected named CHECK, got: {e}"
        finally:
            conn.close()

    def test_check_constraint_retry_count_enforced(self, temp_db):
        """SQLite rejects negative retry_count via ck_cleanup_debt_retry_count."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO cleanup_debt "
                "(id, idempotency_key, storage_key, stale_claim_token, "
                "stale_claim_version, reclaim_token, reclaim_version, status, "
                "created_at, retry_count, last_error, locked_by) "
                "VALUES ('test-bad-retry', 'ik2', 'sk2', "
                "'tok1', 0, 'tok2', 0, 'pending', "
                "'2026-06-25T00:00:00', -1, '', '')"
            )
            conn.commit()
            pytest.fail("Expected sqlite3.IntegrityError for negative retry_count")
        except sqlite3.IntegrityError as e:
            assert "ck_cleanup_debt_retry_count" in str(e), f"Expected named CHECK, got: {e}"
        finally:
            conn.close()

    def test_check_constraint_claim_version_enforced(self, temp_db):
        """SQLite rejects negative claim_version via ck_cleanup_debt_claim_version."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO cleanup_debt "
                "(id, idempotency_key, storage_key, stale_claim_token, "
                "stale_claim_version, reclaim_token, reclaim_version, status, "
                "created_at, retry_count, last_error, locked_by, "
                "claim_version) "
                "VALUES ('test-bad-cv', 'ik3', 'sk3', "
                "'tok1', 0, 'tok2', 0, 'pending', "
                "'2026-06-25T00:00:00', 0, '', '', -1)"
            )
            conn.commit()
            pytest.fail("Expected sqlite3.IntegrityError for negative claim_version")
        except sqlite3.IntegrityError as e:
            assert "ck_cleanup_debt_claim_version" in str(e), f"Expected named CHECK, got: {e}"
        finally:
            conn.close()

    def test_check_constraint_audit_actor_not_empty_enforced(self, temp_db):
        """SQLite rejects empty migration_actor via ck_migration_audit_log_actor_not_empty."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO migration_audit_log "
                "(id, storage_key, migration_actor, audit_reason, operation, result) "
                "VALUES ('test-empty-actor', 'sk1', '', 'some reason', 'legacy_delete', 'deleted')"
            )
            conn.commit()
            pytest.fail("Expected sqlite3.IntegrityError for empty actor")
        except sqlite3.IntegrityError as e:
            assert "ck_migration_audit_log_actor_not_empty" in str(e), (
                f"Expected named CHECK, got: {e}"
            )
        finally:
            conn.close()

    def test_check_constraint_audit_reason_not_empty_enforced(self, temp_db):
        """SQLite rejects empty audit_reason via ck_migration_audit_log_reason_not_empty."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO migration_audit_log "
                "(id, storage_key, migration_actor, audit_reason, operation, result) "
                "VALUES ('test-empty-reason', 'sk2', 'actor', '', 'legacy_delete', 'deleted')"
            )
            conn.commit()
            pytest.fail("Expected sqlite3.IntegrityError for empty reason")
        except sqlite3.IntegrityError as e:
            assert "ck_migration_audit_log_reason_not_empty" in str(e), (
                f"Expected named CHECK, got: {e}"
            )
        finally:
            conn.close()
