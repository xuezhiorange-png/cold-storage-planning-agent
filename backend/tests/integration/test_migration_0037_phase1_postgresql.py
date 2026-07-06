"""Tests for migration 0037 on PostgreSQL — drops
``orchestration_run_attempts.correlation_id`` server_default.

This is the dialect-portable PostgreSQL equivalent of
``test_migration_0037_phase1_drop_correlation_id_default.py``:

* 0037 must run cleanly on a real PostgreSQL 14 container.
* After 0037, the column-level server_default is None — both
  via ``information_schema.columns.column_default`` and via
  attempting an INSERT that omits the value (NOT NULL fail).
* The portable ``ck_attempt_correlation_id_nonempty`` CHECK
  added in 0036 is still in place after 0037.
* Downgrade to 0036 restores the legacy sentinel as the
  column-level default; re-upgrade drops it again.
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgresql

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["DATABASE_BACKEND"] = "postgresql"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture()
def _pg_phase1_admin_url(pg_admin_url: str):
    admin_engine = create_engine(pg_admin_url, poolclass=NullPool)
    test_db = f"cold_storage_test_phase1_0037_{os.getpid()}"
    with admin_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{test_db}"'))
    target_url = pg_admin_url.rsplit("/", 1)[0] + f"/{test_db}"
    yield target_url
    with admin_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        with suppress(Exception):
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
    admin_engine.dispose()


def _column_default(database_url: str, table: str, column: str) -> str | None:
    """Return the column-level default for ``table.column``.

    Reads from ``information_schema.columns`` on PostgreSQL.
    """
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            ).fetchone()
        return row[0] if row else None
    finally:
        engine.dispose()


class Test0037CorrelationIdServerDefaultPostgreSQL:
    """0037: PostgreSQL drops the column-level server_default on
    ``orchestration_run_attempts.correlation_id``.
    """

    def test_correlation_id_has_no_server_default_after_0037(
        self, _pg_phase1_admin_url: str
    ) -> None:
        r = _run_alembic(_pg_phase1_admin_url, "upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"
        dflt = _column_default(_pg_phase1_admin_url, "orchestration_run_attempts", "correlation_id")
        assert dflt is None, (
            f"correlation_id must have no column-level default after 0037; got {dflt!r}"
        )

    def test_database_backend_still_has_no_server_default(self, _pg_phase1_admin_url: str) -> None:
        """0037 preserves the 0036 fix for database_backend."""
        r = _run_alembic(_pg_phase1_admin_url, "upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"
        for table in ("orchestration_run_attempts", "scheme_runs"):
            dflt = _column_default(_pg_phase1_admin_url, table, "database_backend")
            assert dflt is None, (
                f"{table}.database_backend must have no column-level default; got {dflt!r}"
            )

    def test_correlation_id_check_constraint_still_present(self, _pg_phase1_admin_url: str) -> None:
        """0036's portable CHECK is preserved by 0037 on PG."""
        r = _run_alembic(_pg_phase1_admin_url, "upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"
        engine = create_engine(_pg_phase1_admin_url, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conname = 'ck_attempt_correlation_id_nonempty'"
                    )
                ).fetchone()
            assert row is not None, (
                "0036 CHECK ck_attempt_correlation_id_nonempty should still exist after 0037"
            )
        finally:
            engine.dispose()

    def test_write_without_correlation_id_fails_fails_closed(
        self, _pg_phase1_admin_url: str
    ) -> None:
        """P0-2 fail-closed: a write that omits correlation_id
        must fail with NOT NULL (the column-level default is
        None after 0037).
        """
        import uuid as _uuid
        from datetime import UTC, datetime

        r = _run_alembic(_pg_phase1_admin_url, "upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"

        engine = create_engine(_pg_phase1_admin_url, poolclass=NullPool)
        try:
            now = datetime.now(UTC).isoformat()
            # Seed minimal FK chain. (Reuse the SQLite test's
            # _seed_chain semantics but on PG dialect.)
            project_id = str(_uuid.uuid4())
            project_version_id = str(_uuid.uuid4())
            snapshot_id = str(_uuid.uuid4())
            context_id = str(_uuid.uuid4())
            identity_id = str(_uuid.uuid4())
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "INSERT INTO projects("
                        "  id, code, name, location, product_category, status,"
                        "  current_version_number, created_at, updated_at"
                        ") VALUES ("
                        "  :id, :code, :name, :loc, :pcat, 'active', 1, :now, :now"
                        ")"
                    ),
                    {
                        "id": project_id,
                        "code": f"P-{project_id[:8]}",
                        "name": f"proj-{project_id[:8]}",
                        "loc": "test-loc",
                        "pcat": "test-pcat",
                        "now": now,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO project_versions("
                        "  id, project_id, version_number, change_summary, status,"
                        "  input_snapshot, calculation_snapshot, assumption_snapshot,"
                        "  updated_at, created_at, created_by"
                        ") VALUES ("
                        "  :id, :pid, 1, 'phase1', 'approved',"
                        "  :snap, :snap, :snap, :now, :now, 'phase1-tester'"
                        ")"
                    ),
                    {
                        "id": project_version_id,
                        "pid": project_id,
                        "snap": "{}",
                        "now": now,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO orchestration_execution_snapshots("
                        "  id, project_id, project_version_id, version_number,"
                        "  input_snapshot, input_snapshot_hash, schema_version,"
                        "  captured_status, captured_at"
                        ") VALUES (:id, :pid, :pvid, 1, '{}', 'hsh', 'v1', 'OK', :now)"
                    ),
                    {"id": snapshot_id, "pid": project_id, "pvid": project_version_id, "now": now},
                )
                conn.execute(
                    text(
                        "INSERT INTO orchestration_coefficient_contexts("
                        "  id, project_id, project_version_id, content, content_hash,"
                        "  schema_version, captured_at"
                        ") VALUES (:id, :pid, :pvid, '{}', 'hsh', 'v1', :now)"
                    ),
                    {"id": context_id, "pid": project_id, "pvid": project_version_id, "now": now},
                )
                conn.execute(
                    text(
                        "INSERT INTO orchestration_identities("
                        "  id, fingerprint, execution_snapshot_id, coefficient_context_id,"
                        "  definition_version, calculator_version_vector, status, created_at"
                        ") VALUES ("
                        "  :id, :fpr, :sid, :cid, 'v1', '{}', 'ACTIVE', :now"
                        ")"
                    ),
                    {
                        "id": identity_id,
                        "fpr": identity_id * 2,
                        "sid": snapshot_id,
                        "cid": context_id,
                        "now": now,
                    },
                )
                conn.commit()

            # Insert without correlation_id — must fail.
            from sqlalchemy.exc import IntegrityError as SAIntegrityError

            with pytest.raises(SAIntegrityError), engine.connect() as conn:
                conn.execute(
                    text(
                        "INSERT INTO orchestration_run_attempts("
                        "  id, identity_id, attempt_number, status,"
                        "  heartbeat_at, started_at, database_backend,"
                        "  actor_principal_type"
                        ") VALUES ("
                        "  :id, :iid, 1, 'RUNNING', :now, :now,"
                        "  'postgresql', 'user'"
                        ")"
                    ),
                    {
                        "id": str(_uuid.uuid4()),
                        "iid": identity_id,
                        "now": now,
                    },
                )
                conn.commit()
        finally:
            engine.dispose()

    def test_roundtrip_preserves_backfill_default(self, _pg_phase1_admin_url: str) -> None:
        """Downgrade 0037 → 0036 must restore the legacy sentinel
        as the column-level default; re-upgrade drops it again.
        """
        r = _run_alembic(_pg_phase1_admin_url, "upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"
        dflt = _column_default(_pg_phase1_admin_url, "orchestration_run_attempts", "correlation_id")
        assert dflt is None, f"default should be None at head; got {dflt!r}"

        r = _run_alembic(
            _pg_phase1_admin_url,
            "downgrade",
            "0036_phase1_identity_foundation_remediation",
        )
        assert r.returncode == 0, f"downgrade 0036 failed:\n{r.stderr}\n{r.stdout}"
        dflt = _column_default(_pg_phase1_admin_url, "orchestration_run_attempts", "correlation_id")
        # On PG, information_schema stores the default as a
        # SQL string with quotes around the literal. We compare
        # on the inner value to be dialect-agnostic.
        assert dflt is not None, "downgrade should restore column default"
        assert "legacy-migration-0036" in dflt, (
            f"downgrade should restore legacy sentinel; got {dflt!r}"
        )

        r = _run_alembic(_pg_phase1_admin_url, "upgrade", "head")
        assert r.returncode == 0, f"re-upgrade head failed:\n{r.stderr}\n{r.stdout}"
        dflt = _column_default(_pg_phase1_admin_url, "orchestration_run_attempts", "correlation_id")
        assert dflt is None, f"default should be None at head after roundtrip; got {dflt!r}"
