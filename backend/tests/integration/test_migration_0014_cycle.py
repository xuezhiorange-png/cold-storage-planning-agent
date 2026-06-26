"""Migration 0014 & 0015 upgrade/downgrade/upgrade cycle test (real Alembic).

Verifies that migrations 0014_add_approval_fields and 0015_add_active_slot are
fully idempotent by running REAL Alembic subprocess commands against a temporary
SQLite database file:

- upgrade head adds approval columns, FK, active_slot, and unique index
- downgrade 0013 removes them cleanly
- re-upgrade head re-adds them without error

Uses ``subprocess`` to invoke ``uv run alembic`` so the CI roundtrip exercises
the exact same code path as production deployments.
"""

from __future__ import annotations

import os
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


def _get_fk_list(db_path: str, table: str) -> list[dict]:
    """Return list of FK dicts with keys: id, table, from, to."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA foreign_key_list({table})")
    fks = [
        {"id": row[0], "table": row[2], "from": row[3], "to": row[4]} for row in cursor.fetchall()
    ]
    conn.close()
    return fks


def _get_index_names(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA index_list({table})")
    names = {row[1] for row in cursor.fetchall()}
    conn.close()
    return names


def _index_is_unique(db_path: str, index_name: str) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(f"PRAGMA index_info('{index_name}')")
    # unique flag is in PRAGMA index_list, not index_info; re-query
    conn.close()
    conn = sqlite3.connect(db_path)
    # PRAGMA index_list returns: seq, name, unique, origin, partial
    cursor = conn.execute("PRAGMA index_list(report_templates)")
    for row in cursor.fetchall():
        if row[1] == index_name:
            conn.close()
            return bool(row[2])  # unique column
    conn.close()
    return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_db(tmp_path):
    """Yield the path to a temporary SQLite database file."""
    db_path = str(tmp_path / "test.db")
    yield db_path


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestMigrationRoundtrip:
    """Verify full Alembic upgrade → downgrade → upgrade cycle."""

    # -- upgrade head -------------------------------------------------------

    def test_upgrade_adds_approval_columns(self, temp_db):
        """After upgrade head, approval columns exist on reports."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "reports")
        for name in ("approved_revision_id", "approved_content_hash", "approved_by", "approved_at"):
            assert name in cols, f"Missing column {name!r} after upgrade"

    def test_upgrade_adds_fk(self, temp_db):
        """After upgrade head, FK to report_revisions exists."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        fks = _get_fk_list(temp_db, "reports")
        assert any(fk["table"] == "report_revisions" for fk in fks), (
            f"Expected FK to report_revisions, got: {fks}"
        )

    def test_upgrade_adds_active_slot(self, temp_db):
        """After upgrade head, active_slot column exists on report_templates."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_templates")
        assert "active_slot" in cols

    def test_upgrade_adds_unique_index(self, temp_db):
        """After upgrade head, partial unique index exists."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "report_templates")
        assert "uq_active_template_per_code_format_locale" in idx
        assert _index_is_unique(temp_db, "uq_active_template_per_code_format_locale")

    # -- downgrade 0013 ----------------------------------------------------

    def test_downgrade_removes_approval_columns(self, temp_db):
        """After downgrade, approval columns are gone."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "reports")
        for name in ("approved_revision_id", "approved_content_hash", "approved_by", "approved_at"):
            assert name not in cols, f"Column {name!r} should be gone after downgrade"

    def test_downgrade_removes_fk(self, temp_db):
        """After downgrade, FK to report_revisions is gone."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        fks = _get_fk_list(temp_db, "reports")
        assert not any(fk["table"] == "report_revisions" for fk in fks), (
            f"FK to report_revisions should be gone after downgrade, got: {fks}"
        )

    def test_downgrade_removes_active_slot(self, temp_db):
        """After downgrade, active_slot column is gone."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "report_templates")
        assert "active_slot" not in cols

    def test_downgrade_removes_unique_index(self, temp_db):
        """After downgrade, unique index is gone."""
        _run_alembic(["upgrade", "head"], temp_db)
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], temp_db)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        idx = _get_index_names(temp_db, "report_templates")
        assert "uq_active_template_per_code_format_locale" not in idx

    # -- full cycle --------------------------------------------------------

    def test_full_cycle_upgrade_downgrade_upgrade(self, temp_db):
        """Full cycle: upgrade → downgrade → upgrade without error."""
        # First upgrade
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"first upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "reports")
        assert "approved_by" in cols
        assert "active_slot" in _get_columns(temp_db, "report_templates")

        # Downgrade
        result = _run_alembic(["downgrade", "0013_add_templates_artifacts"], temp_db)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        assert "approved_by" not in _get_columns(temp_db, "reports")
        assert "active_slot" not in _get_columns(temp_db, "report_templates")

        # Second upgrade
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"second upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "reports")
        for name in ("approved_revision_id", "approved_content_hash", "approved_by", "approved_at"):
            assert name in cols, f"Column {name!r} missing after re-upgrade"

        fks = _get_fk_list(temp_db, "reports")
        assert any(fk["table"] == "report_revisions" for fk in fks)

        assert "active_slot" in _get_columns(temp_db, "report_templates")
        idx = _get_index_names(temp_db, "report_templates")
        assert "uq_active_template_per_code_format_locale" in idx
        assert _index_is_unique(temp_db, "uq_active_template_per_code_format_locale")

    def test_idempotent_double_upgrade(self, temp_db):
        """Running upgrade head twice does not error."""
        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"first upgrade failed:\n{result.stderr}"

        result = _run_alembic(["upgrade", "head"], temp_db)
        assert result.returncode == 0, f"second upgrade failed:\n{result.stderr}"

        cols = _get_columns(temp_db, "reports")
        assert "approved_by" in cols
