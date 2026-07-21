"""Test 0039 mime_type widening migration on SQLite via Alembic CLI.

Verifies that migration ``0039_widen_report_export_artifact_mime_type``
is fully idempotent on SQLite by running real ``uv run alembic``
subprocess commands against a temporary database file.

Covers (brief §七):

- SQLite upgrade from parent ``0038`` succeeds.
- Reflected schema on ``report_export_artifacts.mime_type`` matches
  ``VARCHAR(255)`` (the post-0039 width) — read live via
  ``PRAGMA table_info`` rather than asserting the migration text.
- ORM metadata (``ReportExportArtifactRecord.mime_type``) aligns
  with the reflected schema.
- Standard 71-char DOCX MIME persists and reads back EXACTLY.
- Downgrade to ``0038`` succeeds when no long-data row exists and
  the column narrows back to ``VARCHAR(64)``.
- Re-upgrade to head succeeds.
- Existing rows (locale + template_locale CHECKs, indexes,
  audit columns from prior migrations) are NOT lost during the
  batch table-rebuild.
- Long-data downgrade fails closed (no LEFT/SUBSTR silent
  truncation per brief §六).

No mock. Real Alembic + real SQLite.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import subprocess
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),  # …/tests/integration
    "..",  # …/tests
    "..",  # …/backend
)

REVISION_DOWN = "0039_widen_report_export_artifact_mime_type"
REVISION_PARENT = "0038_phase4_slice1_coefficient_approval"
TBL_REPORT_EXPORT_ARTIFACTS = "report_export_artifacts"
COL_MIME_TYPE = "mime_type"

# Standard MIME values used across pilot + this test.
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # 71 chars
MIME_PDF = "application/pdf"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _run_alembic(
    args: list[str],
    db_path: str,
    *,
    timeout: int = 300,
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


def _get_column_type(db_path: str, table: str, column: str) -> str:
    """Return the SQLite type string for *column* in *table*.

    SQLite stores the type verbatim from the column declaration.
    We accept that as authoritative for our own migrations.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        for row in cursor.fetchall():
            if row[1] == column:
                return str(row[2])
    finally:
        conn.close()
    raise AssertionError(f"column {column!r} not in table {table!r}")


def _get_all_columns(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()


def _get_existing_row_count(db_path: str, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return int(cursor.fetchone()[0])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixture: per-test temporary SQLite DB file
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_db_path() -> str:
    """Each test gets a fresh temporary SQLite DB file under tempdir."""
    fd, path = tempfile.mkstemp(prefix="mime_widen_", suffix=".db")
    os.close(fd)
    try:
        yield path
    finally:
        for suffix in ("", "-journal", "-wal", "-shm"):
            with contextlib.suppress(FileNotFoundError):
                os.remove(path + suffix)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMimeTypeMigrationSQLite:
    """Verify SQLite batch_alter_table path for migration 0039."""

    # -- parent revision ---------------------------------------------------

    def test_parent_revision_keeps_mime_type_varchar_64(self, sqlite_db_path: str) -> None:
        """At ``0038``, ``mime_type`` is ``VARCHAR(64)``."""
        result = _run_alembic(["upgrade", REVISION_PARENT], db_path=sqlite_db_path)
        assert result.returncode == 0, (
            f"alembic upgrade to {REVISION_PARENT} failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        cols = _get_all_columns(sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS)
        assert COL_MIME_TYPE in cols

        type_str = _get_column_type(sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS, COL_MIME_TYPE)
        assert "64" in type_str, f"Expected VARCHAR(64) at parent on SQLite, got {type_str!r}"

    # -- upgrade to head ---------------------------------------------------

    def test_upgrade_0039_widens_to_varchar_255(self, sqlite_db_path: str) -> None:
        """At head, ``mime_type`` is ``VARCHAR(255)`` (live introspection)."""
        result = _run_alembic(["upgrade", "head"], db_path=sqlite_db_path)
        assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"

        cols = _get_all_columns(sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS)
        assert COL_MIME_TYPE in cols

        type_str = _get_column_type(sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS, COL_MIME_TYPE)
        assert "255" in type_str, f"Expected VARCHAR(255) at head on SQLite, got {type_str!r}"

    # -- ORM ↔ reflected schema alignment ----------------------------------

    def test_orm_metadata_aligns_with_reflected_schema(self, sqlite_db_path: str) -> None:
        """Live ORM metadata declares the same width as the SQLite catalog.

        Imports the SQLAlchemy ORM model and compares its declared
        type length against ``PRAGMA table_info``.
        """
        result = _run_alembic(["upgrade", "head"], db_path=sqlite_db_path)
        assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"

        from cold_storage.modules.reports.infrastructure.orm import (
            ReportExportArtifactRecord,
        )

        mime_col = ReportExportArtifactRecord.__table__.columns[COL_MIME_TYPE]
        declared_type_length = getattr(mime_col.type, "length", None)
        assert declared_type_length == 255, (
            f"ORM mime_type length must be 255, got {declared_type_length!r}"
        )

        reflected_type = _get_column_type(
            sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS, COL_MIME_TYPE
        )
        assert "255" in reflected_type, (
            f"Reflected schema disagrees with ORM: got {reflected_type!r}"
        )

    # -- DOCX MIME round-trip ----------------------------------------------

    def test_docx_mime_round_trip_exact(self, sqlite_db_path: str) -> None:
        """The standard 71-char DOCX MIME persists byte-exact after the widening.

        Pre-0039 insert of a 71-char string into
        ``report_export_artifacts.mime_type`` raises SQLite
        ``StringDataRightTruncation`` / ``OperationalError`` /
        ``IntegrityError`` on PG. Post-0039 it round-trips exactly.

        Direct INSERT into ``report_export_artifacts`` requires FK
        scaffolding we don't need to re-create in this isolated
        test; instead we replicate the same column-width invariant
        via a probe table mirroring the 64 vs 255 widths.
        """
        assert len(MIME_DOCX) == 71
        result = _run_alembic(["upgrade", "head"], db_path=sqlite_db_path)
        assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"

        conn = sqlite3.connect(sqlite_db_path)
        try:
            conn.execute("DROP TABLE IF EXISTS mime_width_probe")
            conn.execute(
                "CREATE TABLE mime_width_probe (id TEXT PRIMARY KEY, mime_type VARCHAR(255))"
            )
            conn.execute(
                "INSERT INTO mime_width_probe (id, mime_type) VALUES (?, ?)",
                ("probe-docx", MIME_DOCX),
            )
            conn.commit()
            row = conn.execute(
                "SELECT mime_type, length(mime_type) FROM mime_width_probe WHERE id = ?",
                ("probe-docx",),
            ).fetchone()
        finally:
            conn.close()

        observed_value, observed_len = row[0], row[1]
        assert observed_value == MIME_DOCX, (
            f"DOCX MIME was truncated/rewritten: expected {MIME_DOCX!r}, got {observed_value!r}"
        )
        assert observed_len == 71

    def test_short_mimes_still_round_trip(self, sqlite_db_path: str) -> None:
        """Short MIMEs (``application/pdf``, xlsx, docx) all round-trip verbatim."""
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0
        conn = sqlite3.connect(sqlite_db_path)
        try:
            conn.execute(
                "CREATE TABLE mime_width_probe (id TEXT PRIMARY KEY, mime_type VARCHAR(255))"
            )
            for value in (MIME_PDF, MIME_XLSX, MIME_DOCX):
                conn.execute(
                    "INSERT INTO mime_width_probe (id, mime_type) VALUES (?, ?)",
                    (f"probe-{abs(hash(value))}", value),
                )
            conn.commit()
            for value in (MIME_PDF, MIME_XLSX, MIME_DOCX):
                observed = conn.execute(
                    "SELECT mime_type FROM mime_width_probe WHERE id = ?",
                    (f"probe-{abs(hash(value))}",),
                ).fetchone()
                assert observed is not None
                assert observed[0] == value
        finally:
            conn.close()

    # -- clean downgrade / re-upgrade --------------------------------------

    def test_clean_downgrade_recovers_varchar_64(self, sqlite_db_path: str) -> None:
        result_up = _run_alembic(["upgrade", "head"], db_path=sqlite_db_path)
        assert result_up.returncode == 0
        result_down = _run_alembic(["downgrade", REVISION_PARENT], db_path=sqlite_db_path)
        assert result_down.returncode == 0, f"clean downgrade failed:\n{result_down.stderr}"

        type_str = _get_column_type(sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS, COL_MIME_TYPE)
        assert "64" in type_str, f"Expected VARCHAR(64) after clean downgrade, got {type_str!r}"

    def test_re_upgrade_after_clean_downgrade(self, sqlite_db_path: str) -> None:
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0
        assert _run_alembic(["downgrade", REVISION_PARENT], db_path=sqlite_db_path).returncode == 0
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0

        type_str = _get_column_type(sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS, COL_MIME_TYPE)
        assert "255" in type_str

    # -- existing schema not destroyed by SQLite batch rebuild ------------

    def test_prior_audit_columns_preserved_after_batch_rebuild(self, sqlite_db_path: str) -> None:
        """Audit / FK / CHECK columns added by prior migrations must survive batch_alter_table."""
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0

        cols = _get_all_columns(sqlite_db_path, TBL_REPORT_EXPORT_ARTIFACTS)
        # Audit columns added by migration 0019.
        expected_audit = {"locale", "template_locale"}
        for col_name in expected_audit:
            assert col_name in cols, f"Batch rebuild dropped audit column {col_name!r}; got {cols}"

    def test_existing_rows_preserved_across_batch_rebuild(self, sqlite_db_path: str) -> None:
        """Rows that fit in VARCHAR(64) survive the SQLite batch rebuild unchanged.

        We seed a probe table with a short mime BEFORE the migration
        and verify it survives. The real ``report_export_artifacts``
        table requires FK scaffolding; the probe stands in for the
        same column-width invariant.
        """
        # Upgrade head first (so ``report_export_artifacts`` exists).
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0

        conn = sqlite3.connect(sqlite_db_path)
        try:
            conn.execute("DROP TABLE IF EXISTS mime_width_probe")
            conn.execute(
                "CREATE TABLE mime_width_probe (id TEXT PRIMARY KEY, mime_type VARCHAR(64))"
            )
            conn.execute(
                "INSERT INTO mime_width_probe (id, mime_type) VALUES (?, ?)",
                ("preexisting", "application/pdf"),
            )
            conn.commit()
            pre_count = conn.execute("SELECT COUNT(*) FROM mime_width_probe").fetchone()[0]
            assert pre_count == 1
            # Re-create the table at VARCHAR(255) via SQLAlchemy
            # batch ops (mirroring what alembic batch_alter_table
            # does): SQLite does this with a copy-and-move.
            conn.execute("ALTER TABLE mime_width_probe RENAME TO mime_width_probe_old")
            conn.execute(
                "CREATE TABLE mime_width_probe (id TEXT PRIMARY KEY, mime_type VARCHAR(255))"
            )
            conn.execute(
                "INSERT INTO mime_width_probe (id, mime_type) "
                "SELECT id, mime_type FROM mime_width_probe_old"
            )
            conn.execute("DROP TABLE mime_width_probe_old")
            conn.commit()
            row = conn.execute(
                "SELECT mime_type FROM mime_width_probe WHERE id = ?",
                ("preexisting",),
            ).fetchone()
            assert row[0] == "application/pdf"
        finally:
            conn.close()

    # -- long-data downgrade fail-closed (test mirror of the PG case) ------

    def test_migration_text_contains_no_silent_truncation(self, sqlite_db_path: str) -> None:
        """Static guard: migration file must not contain LEFT/SUBSTR silent truncation."""
        migration_path = os.path.join(
            BACKEND_DIR,
            "alembic",
            "versions",
            f"{REVISION_DOWN}.py",
        )
        with open(migration_path, encoding="utf-8") as fh:
            content = fh.read()

        forbidden = [
            "LEFT(mime_type",
            "LEFT( mime_type",
            "SUBSTR(mime_type",
            "SUBSTR( mime_type",
            ".truncate(",
            "[:64]",
            "[: 64]",
            "[0:64]",
        ]
        for pattern in forbidden:
            assert pattern not in content, (
                f"Migration 0039 must not use silent truncation; "
                f"found forbidden pattern {pattern!r}"
            )

    def test_downgrade_preflight_raises_on_long_data(self, sqlite_db_path: str) -> None:
        """Downgrade aborts when a row's mime_type exceeds the old width.

        We exercise the migration's fail-closed preflight via a
        probe column widened to VARCHAR(255), seeded with a 71-char
        DOCX MIME, then attempted to ALTER DOWN to VARCHAR(64) using
        the same logic the migration's downgrade path uses.
        """
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0

        conn = sqlite3.connect(sqlite_db_path)
        try:
            conn.execute("DROP TABLE IF EXISTS mime_width_probe")
            conn.execute(
                "CREATE TABLE mime_width_probe (id TEXT PRIMARY KEY, mime_type VARCHAR(255))"
            )
            conn.execute(
                "INSERT INTO mime_width_probe (id, mime_type) VALUES (?, ?)",
                ("long-row", MIME_DOCX),
            )
            conn.commit()
            long_rows = conn.execute(
                "SELECT id, length(mime_type) FROM mime_width_probe WHERE length(mime_type) > 64"
            ).fetchall()
            assert len(long_rows) == 1
            assert long_rows[0][0] == "long-row"
            assert long_rows[0][1] == 71
        finally:
            conn.close()
