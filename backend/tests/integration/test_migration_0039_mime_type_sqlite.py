"""Test 0039 mime_type widening migration on SQLite via Alembic CLI.

Verifies migration ``0039_widen_report_export_artifact_mime_type`` is
fully idempotent on SQLite by running real ``uv run alembic`` against
a temporary per-test database file. The real production table
``report_export_artifacts`` is exercised end-to-end with real parent
FK rows (no probe tables, no FK disabling, no mocking).

Brief §4-§6: real Alembic upgrade/downgrade on real
``report_export_artifacts.mime_type`` — no probe tables, no manual
``RENAME/CREATE/INSERT`` to simulate ``batch_alter_table``.

Brief §7.2: ``alembic upgrade 0039`` is the real operation that
rebuilds the table; we then verify the production schema
(CHECK, INDEX, FK, real existing rows) is preserved.

Brief §8: per-test temporary file DB; alembic_version table lives
inside the test DB; no silent suppression on teardown.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
import uuid

import pytest
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Migration / revision constants
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),  # …/tests/integration
    "..",  # …/tests
    "..",  # …/backend
)

REVISION_HEAD = "0039_widen_report_export_artifact_mime_type"
REVISION_PARENT = "0038_phase4_slice1_coefficient_approval"
TBL_ARTIFACTS = "report_export_artifacts"
COL_MIME_TYPE = "mime_type"

# Standard DOCX MIME (the brief's actual production value).
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # 71 chars
MIME_PDF = "application/pdf"  # 15 chars
MIME_JSON = "application/json"  # 16 chars
# XLSX is 65 chars (not "short") — would itself trigger the preflight
# fail-closed path if inserted before a downgrade.

LOCALE_ZH = "zh-CN"
LOCALE_EN = "en-US"


# ---------------------------------------------------------------------------
# Alembic subprocess helper
# ---------------------------------------------------------------------------


def _run_alembic(
    args: list[str],
    db_path: str,
    *,
    timeout: int = 240,
) -> subprocess.CompletedProcess:
    """Run ``uv run alembic <args>`` against a per-test SQLite database file."""
    env = os.environ.copy()
    env["DATABASE_BACKEND"] = "sqlite"
    env["SQLITE_PATH"] = db_path
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        ["uv", "run", "alembic"] + args,
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Per-test isolation: a fresh SQLite file DB
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_db_path() -> str:
    """Per-test: a fresh temporary SQLite database file under tempdir."""
    fd, path = tempfile.mkstemp(prefix="mig0039_", suffix=".db")
    os.close(fd)
    cleanup_errors: list[BaseException] = []
    try:
        yield path
    finally:
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise BaseExceptionGroup("p1-4 SQLite test DB cleanup failed", cleanup_errors)


@pytest.fixture()
def sqlite_engine(sqlite_db_path: str) -> sa.Engine:
    """Per-test: a real SQLAlchemy engine bound to the per-test SQLite file."""
    eng = sa.create_engine(f"sqlite:///{sqlite_db_path}")
    try:
        yield eng
    finally:
        eng.dispose()


# ---------------------------------------------------------------------------
# Real artifact + parent chain (no probe tables, no FK disabling)
# ---------------------------------------------------------------------------


def _insert_real_export_artifact(
    conn: sa.engine.Connection,
    *,
    mime_value: str,
    locale: str = LOCALE_ZH,
    template_locale: str = LOCALE_ZH,
) -> dict[str, str]:
    """Insert the full FK chain ending in a real ``report_export_artifacts`` row.

    Same as the PG helper, with one difference: SQLite needs
    ``BEGIN`` to start a write transaction; SQLAlchemy
    ``engine.begin()`` does that automatically.
    """
    now = "2026-07-19 00:00:00"
    p = {
        "project_id": str(uuid.uuid4()),
        "project_version_id": str(uuid.uuid4()),
        "report_template_id": str(uuid.uuid4()),
        "report_id": str(uuid.uuid4()),
        "report_revision_id": str(uuid.uuid4()),
        "artifact_id": str(uuid.uuid4()),
    }
    conn.execute(
        sa.text(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) VALUES "
            "(:id, :code, :name, :loc, :pc, :st, :cvn, :ca, :ua)"
        ),
        {
            "id": p["project_id"],
            "code": f"P-MIG-0039-{p['project_id'][:8]}",
            "name": "MIG-0039 test project",
            "loc": "test",
            "pc": "blueberry",
            "st": "active",
            "cvn": 1,
            "ca": now,
            "ua": now,
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO project_versions (id, project_id, version_number, "
            "change_summary, status, input_snapshot, created_at, created_by) "
            "VALUES (:id, :pid, :vn, :cs, :st, :ips, :ca, :cb)"
        ),
        {
            "id": p["project_version_id"],
            "pid": p["project_id"],
            "vn": 1,
            "cs": "init",
            "st": "approved",
            "ips": "{}",
            "ca": now,
            "cb": "tester",
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO report_templates (id, template_code, report_type, "
            "format, version, schema_version, locale, manifest_json, "
            "template_content_hash, created_by) VALUES (:id, :tc, :rt, "
            ":fmt, :ver, :sv, :loc, :mj, :tch, :cb)"
        ),
        {
            "id": p["report_template_id"],
            "tc": f"TC-MIG-0039-{p['report_template_id'][:8]}",
            "rt": "feasibility",
            "fmt": "docx",
            "ver": "1.0",
            "sv": "1.0",
            "loc": locale,
            "mj": "{}",
            "tch": "h" * 64,
            "cb": "tester",
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO reports (id, project_id, project_version_id, "
            "report_type, created_by) VALUES (:id, :pid, :pvid, :rt, :cb)"
        ),
        {
            "id": p["report_id"],
            "pid": p["project_id"],
            "pvid": p["project_version_id"],
            "rt": "feasibility",
            "cb": "tester",
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO report_revisions (id, report_id, revision_number, "
            "schema_version, content_json, canonical_content_json, "
            "content_hash, quality_status, quality_findings_json, "
            "generated_by) VALUES (:id, :rid, :rn, :sv, :cj, :ccj, "
            ":ch, :qs, :qfj, :gb)"
        ),
        {
            "id": p["report_revision_id"],
            "rid": p["report_id"],
            "rn": 1,
            "sv": "1.0",
            "cj": "{}",
            "ccj": "{}",
            "ch": "h" * 64,
            "qs": "ok",
            "qfj": "[]",
            "gb": "tester",
        },
    )
    conn.execute(
        sa.text("UPDATE reports SET approved_revision_id = :ar WHERE id = :id"),
        {"ar": p["report_revision_id"], "id": p["report_id"]},
    )
    conn.execute(
        sa.text(
            "INSERT INTO report_export_artifacts (id, report_id, "
            "report_revision_id, revision_number, format, template_id, "
            "template_version, schema_version, status, file_name, "
            "mime_type, source_content_hash, render_manifest_json, "
            "generated_by, locale, template_locale) VALUES "
            "(:id, :rid, :rrid, :rn, :fmt, :tid, :tv, :sv, :st, "
            ":fn, :mt, :sch, :rmj, :gb, :loc, :tl)"
        ),
        {
            "id": p["artifact_id"],
            "rid": p["report_id"],
            "rrid": p["report_revision_id"],
            "rn": 1,
            "fmt": "docx",
            "tid": p["report_template_id"],
            "tv": "1.0",
            "sv": "1.0",
            "st": "ready",
            "fn": "report.docx",
            "mt": mime_value,
            "sch": "h" * 64,
            "rmj": "{}",
            "gb": "tester",
            "loc": locale,
            "tl": template_locale,
        },
    )
    return p


# ---------------------------------------------------------------------------
# Schema introspection (live, no mock)
# ---------------------------------------------------------------------------


def _column_type(db_path: str, table: str, column: str) -> str | None:
    """Read ``PRAGMA table_info(<table>)`` to get the SQLite type string."""
    conn = sqlite3.connect(db_path)
    try:
        for row in conn.execute(f"PRAGMA table_info({table})"):
            if row[1] == column:
                return str(row[2])
    finally:
        conn.close()
    return None


def _all_columns(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _index_names(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}
    finally:
        conn.close()


def _fk_list(db_path: str, table: str) -> set[tuple[str, str, str]]:
    """Return set of ``(column, other_table, other_column)`` FKs declared on *table*."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    finally:
        conn.close()
    return {(r[3], r[2], r[4]) for r in rows}


def _table_create_sql(db_path: str, table: str) -> str | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _alembic_version(db_path: str) -> str | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Tests — real table, real Alembic, no probe tables
# ---------------------------------------------------------------------------


class TestMimeTypeMigrationSQLite:
    """Real-table evidence for migration 0039 on SQLite."""

    # -- parent / head column width ---------------------------------------

    def test_parent_revision_keeps_mime_type_varchar_64(self, sqlite_db_path: str) -> None:
        """At parent ``0038``, ``report_export_artifacts.mime_type`` is ``VARCHAR(64)``."""
        result = _run_alembic(["upgrade", REVISION_PARENT], db_path=sqlite_db_path)
        assert result.returncode == 0, f"upgrade to parent failed:\n{result.stderr}"
        type_str = _column_type(sqlite_db_path, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert type_str and "64" in type_str, f"Expected VARCHAR(64) at parent, got {type_str!r}"

    def test_upgrade_head_sets_mime_type_to_varchar_255(self, sqlite_db_path: str) -> None:
        """After real ``alembic upgrade head``, the production column is ``VARCHAR(255)``."""
        result = _run_alembic(["upgrade", "head"], db_path=sqlite_db_path)
        assert result.returncode == 0, f"upgrade head failed:\n{result.stderr}"
        assert _alembic_version(sqlite_db_path) == REVISION_HEAD
        type_str = _column_type(sqlite_db_path, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert type_str and "255" in type_str, f"Expected VARCHAR(255) at head, got {type_str!r}"

    # -- real DOCX round-trip ---------------------------------------------

    def test_real_docx_mime_round_trip_on_production_table(
        self, sqlite_engine, sqlite_db_path
    ) -> None:
        """The 71-char DOCX MIME persists byte-exact on the real production column."""
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0
        assert len(MIME_DOCX) == 71

        with sqlite_engine.begin() as conn:
            p = _insert_real_export_artifact(conn, mime_value=MIME_DOCX)

        with sqlite_engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    f"SELECT {COL_MIME_TYPE}, length({COL_MIME_TYPE}) "
                    f"FROM {TBL_ARTIFACTS} WHERE id = :id"
                ),
                {"id": p["artifact_id"]},
            ).one()
        observed_value, observed_len = row[0], row[1]
        assert observed_value == MIME_DOCX, (
            f"DOCX MIME was truncated/rewritten: expected\n  {MIME_DOCX!r}\n "
            f" got\n  {observed_value!r}"
        )
        assert observed_len == 71

    def test_real_short_mime_round_trip(self, sqlite_engine, sqlite_db_path) -> None:
        """Short MIMEs (PDF/XLSX/DOCX) all round-trip verbatim after widening."""
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0

        with sqlite_engine.begin() as conn:
            for v in (MIME_PDF, MIME_JSON, MIME_DOCX):
                _insert_real_export_artifact(conn, mime_value=v)

        with sqlite_engine.connect() as conn:
            rows = conn.execute(
                sa.text(f"SELECT {COL_MIME_TYPE} FROM {TBL_ARTIFACTS} ORDER BY id")
            ).fetchall()
        observed = {r[0] for r in rows}
        assert observed == {MIME_PDF, MIME_JSON, MIME_DOCX}, f"Round-trip failed: got {observed!r}"

    def test_real_batch_rebuild_preserves_check_index_fk_and_rows(
        self, sqlite_engine, sqlite_db_path
    ) -> None:
        """Real ``alembic upgrade 0039`` rebuild preserves CHECK / INDEX / FK / real rows.

        Steps:
        1. ``alembic upgrade 0038`` (parent)
        2. Insert a real short-MIME artifact + parents
        3. Snapshot row count + CHECK / INDEX / FK
        4. ``alembic upgrade 0039`` (the migration's batch_alter_table
           fires here for real)
        5. Verify: row preserved, mime_type unchanged, primary key
           unchanged, FK still present, locale CHECK still present,
           ix_report_export_artifacts_locale still present, column
           width is 255.
        """
        # Step 1
        assert _run_alembic(["upgrade", REVISION_PARENT], db_path=sqlite_db_path).returncode == 0

        # Step 2
        with sqlite_engine.begin() as conn:
            p = _insert_real_export_artifact(conn, mime_value=MIME_PDF)

        # Step 3: snapshot
        with sqlite_engine.connect() as conn:
            pre_count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TBL_ARTIFACTS}")).scalar()
        pre_index_set = _index_names(sqlite_db_path, TBL_ARTIFACTS)
        pre_fk_set = _fk_list(sqlite_db_path, TBL_ARTIFACTS)
        pre_create_sql = _table_create_sql(sqlite_db_path, TBL_ARTIFACTS)
        assert pre_create_sql is not None
        assert "ck_report_artifact_locale_supported" in pre_create_sql
        assert "ck_report_artifact_template_locale_supported" in pre_create_sql
        assert "ix_report_export_artifacts_locale" in pre_index_set
        # FK presence pre-rebuild
        pre_fk_targets = {fk[1] for fk in pre_fk_set}
        assert {"reports", "report_revisions", "report_templates"} <= pre_fk_targets

        # Step 4
        up = _run_alembic(["upgrade", "head"], db_path=sqlite_db_path)
        assert up.returncode == 0, f"upgrade 0039 failed:\n{up.stderr}"

        # Step 5: post-rebuild checks
        with sqlite_engine.connect() as conn:
            post_count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TBL_ARTIFACTS}")).scalar()
            assert post_count == pre_count, f"Row count changed: pre={pre_count} post={post_count}"
            row = conn.execute(
                sa.text(f"SELECT id, {COL_MIME_TYPE} FROM {TBL_ARTIFACTS} WHERE id = :id"),
                {"id": p["artifact_id"]},
            ).one()
        # Row preserved, primary key preserved, mime_type preserved
        assert row[0] == p["artifact_id"], (
            f"Primary key changed: expected {p['artifact_id']}, got {row[0]}"
        )
        assert row[1] == MIME_PDF, f"mime_type changed across batch_rebuild: got {row[1]!r}"
        # FK + CHECK + INDEX preserved
        post_index_set = _index_names(sqlite_db_path, TBL_ARTIFACTS)
        post_fk_set = _fk_list(sqlite_db_path, TBL_ARTIFACTS)
        post_create_sql = _table_create_sql(sqlite_db_path, TBL_ARTIFACTS)
        assert post_create_sql is not None
        assert "ck_report_artifact_locale_supported" in post_create_sql
        assert "ck_report_artifact_template_locale_supported" in post_create_sql
        assert "ix_report_export_artifacts_locale" in post_index_set
        post_fk_targets = {fk[1] for fk in post_fk_set}
        assert {"reports", "report_revisions", "report_templates"} <= post_fk_targets
        # All previously-existing indexes should still be there
        assert pre_index_set <= post_index_set, (
            f"Index set shrank during batch_rebuild: pre \\ post = {pre_index_set - post_index_set}"
        )
        # Column width is now 255
        type_str = _column_type(sqlite_db_path, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert type_str and "255" in type_str, (
            f"Expected VARCHAR(255) after upgrade 0039, got {type_str!r}"
        )

    # -- real alembic downgrade fail-closed on long data -----------------

    def test_real_alembic_downgrade_fails_closed_on_long_data(
        self, sqlite_engine, sqlite_db_path
    ) -> None:
        """Real ``alembic downgrade 0038`` aborts when a real long-MIME row exists.

        Brief §7.3: real upgrade head → real long-MIME insert →
        real alembic downgrade. Asserts:
        - downgrade exit code != 0
        - error classified as 0039 preflight failure
        - production column still VARCHAR(255)
        - long row preserved
        - alembic_version stays at 0039
        """
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0

        with sqlite_engine.begin() as conn:
            p = _insert_real_export_artifact(conn, mime_value=MIME_DOCX)

        downgrade = _run_alembic(["downgrade", REVISION_PARENT], db_path=sqlite_db_path)
        assert downgrade.returncode != 0, (
            f"alembic downgrade should have FAILED on long data, but it returned 0.\n"
            f"stdout: {downgrade.stdout}\nstderr: {downgrade.stderr}"
        )
        err_text = downgrade.stderr + downgrade.stdout
        assert "Cannot downgrade report_export_artifacts.mime_type" in err_text
        assert "longer than 64" in err_text
        assert p["artifact_id"] in err_text

        # Post-failure state preserved
        assert _alembic_version(sqlite_db_path) == REVISION_HEAD
        type_str = _column_type(sqlite_db_path, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert type_str and "255" in type_str, (
            f"Production column width must remain 255 after failed downgrade, got {type_str!r}"
        )
        with sqlite_engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    f"SELECT {COL_MIME_TYPE}, length({COL_MIME_TYPE}) "
                    f"FROM {TBL_ARTIFACTS} WHERE id = :id"
                ),
                {"id": p["artifact_id"]},
            ).one()
        assert row[0] == MIME_DOCX
        assert row[1] == 71

    # -- real clean downgrade / re-upgrade -------------------------------

    def test_real_clean_downgrade_then_reupgrade_preserves_short_rows(
        self, sqlite_engine, sqlite_db_path
    ) -> None:
        """Real clean downgrade 0039→0038 (with short MIMEs only) + re-upgrade."""
        assert _run_alembic(["upgrade", "head"], db_path=sqlite_db_path).returncode == 0

        with sqlite_engine.begin() as conn:
            p_pdf = _insert_real_export_artifact(conn, mime_value=MIME_PDF)
            p_json = _insert_real_export_artifact(conn, mime_value=MIME_JSON)

        # Clean downgrade
        down = _run_alembic(["downgrade", REVISION_PARENT], db_path=sqlite_db_path)
        assert down.returncode == 0, f"Clean downgrade failed:\n{down.stderr}"
        assert _alembic_version(sqlite_db_path) == REVISION_PARENT
        type_str = _column_type(sqlite_db_path, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert type_str and "64" in type_str

        with sqlite_engine.connect() as conn:
            n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TBL_ARTIFACTS}")).scalar()
            assert n == 2
            for pid, expected in (
                (p_pdf["artifact_id"], MIME_PDF),
                (p_json["artifact_id"], MIME_JSON),
            ):
                v = conn.execute(
                    sa.text(f"SELECT {COL_MIME_TYPE} FROM {TBL_ARTIFACTS} WHERE id = :id"),
                    {"id": pid},
                ).scalar()
                assert v == expected

        # Re-upgrade
        up = _run_alembic(["upgrade", "head"], db_path=sqlite_db_path)
        assert up.returncode == 0
        assert _alembic_version(sqlite_db_path) == REVISION_HEAD
        type_str = _column_type(sqlite_db_path, TBL_ARTIFACTS, COL_MIME_TYPE)
        assert type_str and "255" in type_str
        with sqlite_engine.connect() as conn:
            for pid, expected in (
                (p_pdf["artifact_id"], MIME_PDF),
                (p_json["artifact_id"], MIME_JSON),
            ):
                v = conn.execute(
                    sa.text(f"SELECT {COL_MIME_TYPE} FROM {TBL_ARTIFACTS} WHERE id = :id"),
                    {"id": pid},
                ).scalar()
                assert v == expected

    # -- static guard: migration file must not silently truncate ---------

    def test_migration_text_contains_no_silent_truncation(self, sqlite_db_path: str) -> None:
        """The migration file must not contain LEFT/SUBSTR silent-truncation helpers."""
        migration_path = os.path.join(
            BACKEND_DIR,
            "alembic",
            "versions",
            f"{REVISION_HEAD}.py",
        )
        with open(migration_path, encoding="utf-8") as fh:
            content = fh.read()
        forbidden = (
            "LEFT(mime_type",
            "LEFT( mime_type",
            "SUBSTR(mime_type",
            "SUBSTR( mime_type",
            ".truncate(",
            "[:64]",
            "[: 64]",
            "[0:64]",
        )
        for pattern in forbidden:
            assert pattern not in content, (
                f"Migration 0039 must not use silent truncation; "
                f"found forbidden pattern {pattern!r}"
            )
