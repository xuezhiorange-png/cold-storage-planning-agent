"""Tests for migration 0037: Phase 1 — drop ``correlation_id``
server_default on ``orchestration_run_attempts``.

Verifies that the 0037 migration closes the P0-2 contract gap
flagged in the round 11 independent engineering review:

* 0036 step 1 — backfilled any NULL / empty / whitespace-only
  ``correlation_id`` row with the explicit sentinel
  ``"legacy-migration-0036"``. **preserved** by 0037.
* 0036 step 3 — added the portable
  ``ck_attempt_correlation_id_nonempty`` CHECK on both
  SQLite and PostgreSQL. **preserved** by 0037.
* 0037 — drops the column-level ``server_default`` so future
  writes must supply ``correlation_id`` explicitly. The
  legacy sentinel is reserved for backfilled pre-0036 rows;
  new writes cannot mint a "fake" correlation_id by relying
  on the default.

This test file is dialect-portable (SQLite only here; the
PostgreSQL equivalent is in
``test_migration_0037_phase1_postgresql.py``).
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

# ── helpers ────────────────────────────────────────────────────────


def _alembic_cfg(db_path: str) -> Config:
    """Return an Alembic Config wired to the given SQLite file."""
    cfg = Config()
    backend_root = Path(__file__).resolve().parents[2]  # backend/
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _run_alembic(args: list[str], db_path: str) -> object:
    """Run an alembic command via subprocess (CLI) for robustness."""
    import os
    import subprocess
    import sys

    backend_root = Path(__file__).resolve().parents[2]  # backend/
    env = os.environ.copy()
    env["DATABASE_BACKEND"] = "sqlite"
    env["SQLITE_PATH"] = db_path
    env["PYTHONPATH"] = "src"
    r = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(backend_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"alembic {args} failed (rc={r.returncode}):\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
        )
    return r


def _dflt(db_path: str, table: str, column: str) -> str | None:
    """Return the column-level default (``dflt_value``) for ``table.column``."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            f"SELECT dflt_value FROM pragma_table_info('{table}') WHERE name='{column}'"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _seed_chain(engine):
    """Seed the minimal FK chain for an attempt. Returns identity_id."""
    project_id = str(uuid.uuid4())
    project_version_id = str(uuid.uuid4())
    snapshot_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())

    identity_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    with engine.connect() as c:
        c.execute(
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
        c.execute(
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
        c.execute(
            text(
                "INSERT INTO orchestration_execution_snapshots("
                "  id, project_id, project_version_id, version_number,"
                "  input_snapshot, input_snapshot_hash, schema_version,"
                "  captured_status, captured_at"
                ") VALUES (:id, :pid, :pvid, 1, '{}', 'hsh', 'v1', 'OK', :now)"
            ),
            {"id": snapshot_id, "pid": project_id, "pvid": project_version_id, "now": now},
        )
        c.execute(
            text(
                "INSERT INTO orchestration_coefficient_contexts("
                "  id, project_id, project_version_id, content, content_hash,"
                "  schema_version, captured_at"
                ") VALUES (:id, :pid, :pvid, '{}', 'hsh', 'v1', :now)"
            ),
            {"id": context_id, "pid": project_id, "pvid": project_version_id, "now": now},
        )
        c.execute(
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
        c.commit()
    return identity_id


# ── P0-2 final contract: 0037 drops the column-level default ──────


class Test0037CorrelationIdServerDefault:
    """P0-2 final: 0037 drops the column-level server_default on
    ``orchestration_run_attempts.correlation_id`` so future
    writes MUST supply the value explicitly. The legacy sentinel
    ``legacy-migration-0036`` is reserved for backfilled
    pre-0036 rows.
    """

    def test_correlation_id_has_no_server_default_after_0037(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            dflt = _dflt(t.name, "orchestration_run_attempts", "correlation_id")
            assert dflt is None, (
                f"correlation_id must have no column-level default after 0037; got {dflt!r}"
            )
        finally:
            Path(t.name).unlink(missing_ok=True)

    def test_database_backend_still_has_no_server_default(self) -> None:
        """0037 preserves the 0036 fix for database_backend."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            for table in ("orchestration_run_attempts", "scheme_runs"):
                dflt = _dflt(t.name, table, "database_backend")
                assert dflt is None, (
                    f"{table}.database_backend must have no column-level default; got {dflt!r}"
                )
        finally:
            Path(t.name).unlink(missing_ok=True)

    def test_correlation_id_check_constraint_still_present(self) -> None:
        """0036's portable CHECK is preserved by 0037."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            conn = sqlite3.connect(t.name)
            try:
                row = conn.execute(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='table' AND name='orchestration_run_attempts'"
                ).fetchone()
                create_sql = row[0] if row else None
                assert create_sql is not None
                assert "ck_attempt_correlation_id_nonempty" in create_sql, (
                    "0036 CHECK should still be present after 0037"
                )
            finally:
                conn.close()
        finally:
            Path(t.name).unlink(missing_ok=True)


# ── Fail-closed: writes must explicitly supply correlation_id ────


class Test0037FailClosedOnOmittedCorrelationId:
    """P0-2 fail-closed invariant: 0037 makes the column-level
    default None, so an insert that omits ``correlation_id`` MUST
    fail with ``IntegrityError`` (NOT NULL). This is the desired
    fail-closed behavior.
    """

    def test_write_without_correlation_id_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            engine = create_engine(f"sqlite:///{t.name}")
            try:
                identity_id = _seed_chain(engine)
                with pytest.raises(Exception) as exc, engine.connect() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO orchestration_run_attempts("
                            "  id, identity_id, attempt_number, status,"
                            "  heartbeat_at, started_at, database_backend,"
                            "  actor_principal_type"
                            ") VALUES ("
                            "  :id, :iid, 1, 'RUNNING', :now, :now,"
                            "  'sqlite', 'user'"
                            ")"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "iid": identity_id,
                            "now": datetime.now(UTC).isoformat(),
                        },
                    )
                    conn.commit()
                assert "IntegrityError" in type(exc.value).__name__, (
                    f"expected IntegrityError for missing correlation_id; "
                    f"got {type(exc.value).__name__}: {exc.value!r}"
                )
            finally:
                engine.dispose()
        finally:
            Path(t.name).unlink(missing_ok=True)


# ── Downgrade / re-upgrade roundtrip ─────────────────────────────


class Test0037RoundtripSQLite:
    """0037 upgrade / downgrade / re-upgrade roundtrip on SQLite."""

    def test_upgrade_downgrade_reupgrade_full_roundtrip(self) -> None:
        """upgrade head → downgrade 0036 → re-upgrade head works clean.

        The downgrade step should restore the 0036-era
        ``server_default = 'legacy-migration-0036'`` for
        ``correlation_id``. The re-upgrade step drops it again.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            # Initial upgrade to head (0037).
            _run_alembic(["upgrade", "head"], t.name)
            assert _dflt(t.name, "orchestration_run_attempts", "correlation_id") is None

            # Downgrade to 0036 — restores legacy sentinel default.
            _run_alembic(["downgrade", "0036_phase1_identity_foundation_remediation"], t.name)
            assert (
                _dflt(t.name, "orchestration_run_attempts", "correlation_id")
                == "'legacy-migration-0036'"
            )

            # Re-upgrade to head (0037) — drops the default again.
            _run_alembic(["upgrade", "head"], t.name)
            assert _dflt(t.name, "orchestration_run_attempts", "correlation_id") is None

            # 0036 CHECK still in place.
            conn = sqlite3.connect(t.name)
            try:
                row = conn.execute(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='table' AND name='orchestration_run_attempts'"
                ).fetchone()
                create_sql = row[0] if row else None
                assert create_sql is not None
                assert "ck_attempt_correlation_id_nonempty" in create_sql
            finally:
                conn.close()
        finally:
            Path(t.name).unlink(missing_ok=True)
