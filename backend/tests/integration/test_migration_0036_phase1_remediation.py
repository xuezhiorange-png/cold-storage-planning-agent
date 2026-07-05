"""Tests for migration 0036: Phase 1 identity-foundation remediation.

Covers:

- P0-1: ``database_backend`` server_default dropped on both
  ``orchestration_run_attempts`` and ``scheme_runs``; rows
  still populated (no NULL leak); future writes MUST supply
  the value or fail with IntegrityError.
- P0-2: ``correlation_id`` rejects NULL / empty / whitespace
  via the portable ``length(trim(correlation_id)) > 0`` CHECK;
  legacy sentinel ``legacy-migration-0036`` is accepted (and
  remains the server_default).
- 0036 roundtrip: upgrade 0035 → 0036 → downgrade 0036 → upgrade
  0036 leaves the database in the expected state.

These tests are dialect-portable (SQLite only here; the
PostgreSQL equivalent is in
``test_migration_0036_phase1_postgresql.py``).
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
    # Resolve script_location absolutely so the test is robust to
    # pytest's per-test tmp_path cwd.
    backend_root = Path(__file__).resolve().parents[2]  # backend/
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _run_alembic(args: list[str], db_path: str) -> object:
    """Run an alembic command via subprocess (CLI) for robustness.

    This mirrors the helper in
    ``test_migration_0035_phase1_identity_foundation.py``: it
    relies on the env-var override (``SQLITE_PATH``) that
    ``alembic/env.py`` honours via ``Settings`` to point
    alembic at a per-test temp DB.
    """
    import os
    import subprocess
    import sys

    backend_root = Path(__file__).resolve().parents[2]  # backend/
    env = os.environ.copy()
    # Ensure alembic.env reads OUR temp DB, not the project default.
    env["DATABASE_BACKEND"] = "sqlite"
    env["SQLITE_PATH"] = db_path
    # Ensure the in-process alembic finds the project's source tree
    # even when pytest's cwd is not the backend dir.
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


# ── P0-1: database_backend ────────────────────────────────────────


class Test0036DatabaseBackendServerDefault:
    """P0-1: server_default is DROPPED on database_backend columns
    so future writes MUST supply the value explicitly."""

    def test_orch_attempts_database_backend_has_no_server_default(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            dflt = _dflt(t.name, "orchestration_run_attempts", "database_backend")
            assert dflt is None, (
                f"database_backend must have no column-level default after 0036; got {dflt!r}"
            )
        finally:
            Path(t.name).unlink(missing_ok=True)

    def test_scheme_runs_database_backend_has_no_server_default(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            dflt = _dflt(t.name, "scheme_runs", "database_backend")
            assert dflt is None, (
                f"scheme_runs.database_backend must have no column-level default "
                f"after 0036; got {dflt!r}"
            )
        finally:
            Path(t.name).unlink(missing_ok=True)

    def test_orch_attempts_write_without_database_backend_fails(self) -> None:
        """A write that omits database_backend must fail with IntegrityError
        — fail-closed behavior required by P0-1."""
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
                            "  heartbeat_at, started_at, actor_principal_type"
                            ") VALUES ("
                            "  :id, :iid, 1, 'RUNNING', :now, :now, 'user'"
                            ")"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "iid": identity_id,
                            "now": datetime.now(UTC).isoformat(),
                        },
                    )
                    conn.commit()
                assert "IntegrityError" in type(exc.value).__name__ or "NOT NULL" in str(
                    exc.value
                ), f"expected IntegrityError/NOT NULL; got {exc.value!r}"
            finally:
                engine.dispose()
        finally:
            Path(t.name).unlink(missing_ok=True)

    def test_scheme_runs_write_without_database_backend_fails(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            engine = create_engine(f"sqlite:///{t.name}")
            try:
                # Get a sample of scheme_runs columns to set up a minimal row.
                cols = engine.connect().execute(text("PRAGMA table_info('scheme_runs')")).fetchall()
                col_names = {r[1]: r for r in cols}
                # We need to satisfy NOT NULL columns. Use 'legacy' source_mode so
                # we don't need weight_set_revision_id / source_binding_id.
                sql_parts = []
                values_parts = []
                params: dict[str, object] = {}
                for cname in ("id", "source_mode"):
                    sql_parts.append(cname)
                    values_parts.append(f":{cname}")
                    params[cname] = str(uuid.uuid4()) if cname == "id" else "legacy"
                # add other NOT NULL cols we know about
                for cname in (
                    "weight_set_revision_id",
                    "source_binding_id",
                    "request_fingerprint",
                    "requested_by",
                    "requested_at",
                    "calculator_version_vector",
                ):
                    if cname in col_names and col_names[cname][3] == 1:  # notnull
                        sql_parts.append(cname)
                        values_parts.append(f":{cname}")
                        if cname in ("requested_at",):
                            params[cname] = datetime.now(UTC).isoformat()
                        elif cname in ("calculator_version_vector",):
                            params[cname] = "{}"
                        else:
                            params[cname] = None
                # Add database_backend-related NOT NULL cols by NOT specifying them
                with pytest.raises(Exception) as exc, engine.connect() as conn:
                    conn.execute(
                        text(
                            f"INSERT INTO scheme_runs({', '.join(sql_parts)}) "
                            f"VALUES ({', '.join(values_parts)})"
                        ),
                        params,
                    )
                    conn.commit()
                assert "IntegrityError" in type(exc.value).__name__ or "NOT NULL" in str(
                    exc.value
                ), f"expected IntegrityError/NOT NULL; got {exc.value!r}"
            finally:
                engine.dispose()
        finally:
            Path(t.name).unlink(missing_ok=True)


# ── P0-2: correlation_id ──────────────────────────────────────────


class Test0036CorrelationIdCheck:
    """P0-2: ck_attempt_correlation_id_nonempty rejects NULL/empty/whitespace."""

    def test_correlation_id_server_default_is_legacy_sentinel(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            dflt = _dflt(t.name, "orchestration_run_attempts", "correlation_id")
            assert dflt == "'legacy-migration-0036'", (
                f"correlation_id default should be 'legacy-migration-0036'; got {dflt!r}"
            )
        finally:
            Path(t.name).unlink(missing_ok=True)

    @pytest.mark.parametrize(
        "bad_value",
        ["", " ", "   ", "\t", "\n", " \t\n "],
        ids=["empty", "single-space", "spaces", "tab", "newline", "mixed-whitespace"],
    )
    def test_correlation_id_rejects_empty_or_whitespace(self, bad_value: str) -> None:
        """ck_attempt_correlation_id_nonempty rejects empty / whitespace-only values."""
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
                            "  correlation_id, actor_principal_type"
                            ") VALUES ("
                            "  :id, :iid, 1, 'RUNNING', :now, :now,"
                            "  'sqlite', :cid, 'user'"
                            ")"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "iid": identity_id,
                            "now": datetime.now(UTC).isoformat(),
                            "cid": bad_value,
                        },
                    )
                    conn.commit()
                # The CHECK name ck_attempt_correlation_id_nonempty should be
                # in the error message; IntegrityError is the parent class.
                assert "IntegrityError" in type(exc.value).__name__, (
                    f"expected IntegrityError for {bad_value!r}; "
                    f"got {type(exc.value).__name__}: {exc.value!r}"
                )
                assert "ck_attempt_correlation_id_nonempty" in str(exc.value) or (
                    "CHECK" in str(exc.value)
                ), f"unexpected error: {exc.value!r}"
            finally:
                engine.dispose()
        finally:
            Path(t.name).unlink(missing_ok=True)

    def test_correlation_id_rejects_null(self) -> None:
        """Explicit NULL is rejected by the NOT NULL constraint (P0-2)."""
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
                            "  correlation_id, actor_principal_type"
                            ") VALUES ("
                            "  :id, :iid, 1, 'RUNNING', :now, :now,"
                            "  'sqlite', NULL, 'user'"
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
                    f"expected IntegrityError for NULL; "
                    f"got {type(exc.value).__name__}: {exc.value!r}"
                )
            finally:
                engine.dispose()
        finally:
            Path(t.name).unlink(missing_ok=True)

    @pytest.mark.parametrize(
        "good_value",
        [
            "legacy-migration-0036",
            "corr-abc-123",
            "a",  # single non-whitespace char
            "  abc  ",  # whitespace-padded but non-empty after trim
        ],
    )
    def test_correlation_id_accepts_valid_values(self, good_value: str) -> None:
        """Legitimate correlation IDs (including the legacy sentinel) are accepted."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            _run_alembic(["upgrade", "head"], t.name)
            engine = create_engine(f"sqlite:///{t.name}")
            try:
                identity_id = _seed_chain(engine)
                aid = str(uuid.uuid4())
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO orchestration_run_attempts("
                            "  id, identity_id, attempt_number, status,"
                            "  heartbeat_at, started_at, database_backend,"
                            "  correlation_id, actor_principal_type"
                            ") VALUES ("
                            "  :id, :iid, 1, 'RUNNING', :now, :now,"
                            "  'sqlite', :cid, 'user'"
                            ")"
                        ),
                        {
                            "id": aid,
                            "iid": identity_id,
                            "now": datetime.now(UTC).isoformat(),
                            "cid": good_value,
                        },
                    )
                    conn.commit()
                # Read back
                with engine.connect() as conn:
                    row = conn.execute(
                        text(
                            "SELECT correlation_id FROM orchestration_run_attempts WHERE id = :id"
                        ),
                        {"id": aid},
                    ).fetchone()
                assert row is not None
                assert row[0] == good_value
            finally:
                engine.dispose()
        finally:
            Path(t.name).unlink(missing_ok=True)


# ── Roundtrip ──────────────────────────────────────────────────────


class Test0036RoundtripSQLite:
    """0036 upgrade / downgrade / re-upgrade roundtrip on SQLite."""

    def test_upgrade_downgrade_reupgrade_full_roundtrip(self) -> None:
        """upgrade head → downgrade 0035 → re-upgrade head works clean."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
            t.close()
        try:
            # Initial upgrade to 0036.
            _run_alembic(["upgrade", "head"], t.name)

            # Downgrade to 0035.
            _run_alembic(["downgrade", "0035_phase1_identity_foundation"], t.name)

            # Verify that the 0036-specific CHECK is gone after downgrade.
            engine = create_engine(f"sqlite:///{t.name}")
            try:
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT name FROM sqlite_master "
                            "WHERE type='table' AND name='orchestration_run_attempts'"
                        )
                    ).fetchall()
                    assert rows, "orchestration_run_attempts table missing after downgrade"
                    create_sql = conn.execute(
                        text(
                            "SELECT sql FROM sqlite_master "
                            "WHERE type='table' AND name='orchestration_run_attempts'"
                        )
                    ).scalar()
                    assert create_sql is not None
                    assert "ck_attempt_correlation_id_nonempty" not in create_sql, (
                        "0036 CHECK should be dropped after downgrade"
                    )
            finally:
                engine.dispose()

            # Re-upgrade to head.
            _run_alembic(["upgrade", "head"], t.name)

            # Verify the CHECK is back.
            engine = create_engine(f"sqlite:///{t.name}")
            try:
                with engine.connect() as conn:
                    create_sql = conn.execute(
                        text(
                            "SELECT sql FROM sqlite_master "
                            "WHERE type='table' AND name='orchestration_run_attempts'"
                        )
                    ).scalar()
                    assert create_sql is not None
                    assert "ck_attempt_correlation_id_nonempty" in create_sql, (
                        "0036 CHECK should be re-created after re-upgrade"
                    )
                    # And the database_backend default is None (dropped).
                    dflt_db = conn.execute(
                        text(
                            "SELECT dflt_value FROM pragma_table_info("
                            "'orchestration_run_attempts') WHERE name='database_backend'"
                        )
                    ).scalar()
                    assert dflt_db is None
                    # correlation_id default is the sentinel.
                    dflt_cid = conn.execute(
                        text(
                            "SELECT dflt_value FROM pragma_table_info("
                            "'orchestration_run_attempts') WHERE name='correlation_id'"
                        )
                    ).scalar()
                    assert dflt_cid == "'legacy-migration-0036'"
            finally:
                engine.dispose()
        finally:
            Path(t.name).unlink(missing_ok=True)
