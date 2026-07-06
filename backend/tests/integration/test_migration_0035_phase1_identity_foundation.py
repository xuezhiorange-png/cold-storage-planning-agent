"""Migration 0035 Phase 1 — schema and identity foundation for production calculation orchestration.

Verifies that migration 0035_phase1_identity_foundation is fully
idempotent by running REAL Alembic subprocess commands against
temporary SQLite and PostgreSQL databases:

SQLite tests (this file):
  * upgrade head adds 5 columns on orchestration_run_attempts
    and 2 columns on scheme_runs, plus 2 CHECK constraints and
    a unique index
  * downgrade 0034 removes them cleanly
  * re-upgrade head re-adds them without error

PostgreSQL tests (test_migration_0035_phase1_postgresql.py):
  * same cycle on real PostgreSQL container

ORM roundtrip tests:
  * idempotency, database_backend, correlation_id,
    actor_principal_type, scheme_run_id persistence
  * frozen_envelope JSON roundtrip on scheme_runs

Architecture boundary test:
  * evaluation module MUST NOT import the Phase 1 helpers nor
    the new ORM fields

Phase 1 contract: see design doc
docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md
(Frozen Contract Authority SHA: ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2)
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run_alembic(
    args: list[str],
    db_path: str,
    *,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """Run ``python -m alembic <args>`` against a temp SQLite DB."""
    env = os.environ.copy()
    env["DATABASE_BACKEND"] = "sqlite"
    env["SQLITE_PATH"] = db_path
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# SQLite schema introspection helpers
# ---------------------------------------------------------------------------


def _get_columns(db_path: str, table: str) -> dict[str, tuple[str, bool]]:
    """Return column name -> (type, nullable)."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(f"PRAGMA table_info({table})")
    # sqlite PRAGMA returns (cid, name, type, notnull, dflt_value, pk)
    # notnull=1 means NOT NULL, notnull=0 means nullable.
    cols = {r[1]: (r[2], not bool(r[3])) for r in cur.fetchall()}
    conn.close()
    return cols


def _get_indexes(db_path: str, table: str) -> dict[str, list[str]]:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(f"PRAGMA index_list({table})")
    out: dict[str, list[str]] = {}
    for r in cur.fetchall():
        idx_name = r[1]
        cols = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
        out[idx_name] = [c[2] for c in cols]
    conn.close()
    return out


def _get_fk_list(db_path: str, table: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(f"PRAGMA foreign_key_list({table})")
    fks = [{"id": r[0], "table": r[2], "from": r[3], "to": r[4]} for r in cur.fetchall()]
    conn.close()
    return fks


def _check_constraints(db_path: str, table: str) -> list[str]:
    """Extract CHECK clauses from sqlite table definition.

    Returns the full clause text starting from ``CONSTRAINT <name>``
    (if present) or ``CHECK`` (otherwise), ending at the matching
    closing paren. Check constraints may themselves contain
    parentheses (e.g. ``IN ('sqlite', 'postgresql')``); we balance
    parens manually.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return []

    full_sql = row[0]
    clauses: list[str] = []
    while True:
        # Look for the literal token CONSTRAINT
        clause_start = full_sql.upper().find("CONSTRAINT")
        check_start = full_sql.upper().find("CHECK")
        # Determine whether to consume from CONSTRAINT or CHECK
        # (CONSTRAINT pairs name + CHECK; standalone CHECK is also OK).
        if clause_start >= 0:
            cursor = clause_start
            # after CONSTRAINT, capture the constraint name (a single SQL identifier)
            cursor = full_sql.find("(", cursor)
            if cursor < 0:
                break
        elif check_start >= 0:
            cursor = check_start
            cursor = full_sql.find("(", cursor)
            if cursor < 0:
                break
        else:
            break

        # walk from cursor, balancing parens, until matching ')' found
        clause_open = clause_start if clause_start >= 0 else check_start
        cursor = full_sql.find("(", clause_open)
        if cursor < 0:
            break
        depth = 0
        while cursor < len(full_sql):
            c = full_sql[cursor]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    cursor += 1
                    break
            cursor += 1
        end_paren = cursor
        clause_text = full_sql[clause_open:end_paren].strip()
        clauses.append(clause_text)
        # advance past the captured clause
        full_sql = full_sql[end_paren:]
    return clauses


# ---------------------------------------------------------------------------
# SQLite tests
# ---------------------------------------------------------------------------


class Test0035Phase1SchemaDeltaSQLite:
    def test_upgrade_head_adds_required_columns_to_orchestration_run_attempts(
        self,
    ) -> None:
        """Upgrade to head — orchestration_run_attempts has the
        five new Phase 1 columns (idempotency_key, database_backend,
        correlation_id, actor_principal_type, scheme_run_id)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        try:
            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0, f"Upgrade to head failed:\n{r.stderr}\n{r.stdout}"

            cols = _get_columns(tmp.name, "orchestration_run_attempts")

            # New columns must be present
            for name in (
                "idempotency_key",
                "database_backend",
                "correlation_id",
                "actor_principal_type",
                "scheme_run_id",
            ):
                assert name in cols, f"missing column {name} on orchestration_run_attempts"

            # Nullability invariants per migration contract.
            assert cols["idempotency_key"][1] is True, "idempotency_key must be nullable"
            assert cols["database_backend"][1] is False, "database_backend must be NOT NULL"
            assert cols["correlation_id"][1] is False, "correlation_id must be NOT NULL"
            assert cols["actor_principal_type"][1] is False, "actor_principal_type must be NOT NULL"
            assert cols["scheme_run_id"][1] is True, "scheme_run_id must be nullable"
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_upgrade_head_adds_required_columns_to_scheme_runs(self) -> None:
        """Upgrade to head — scheme_runs has frozen_envelope +
        database_backend."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        try:
            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0, f"Upgrade to head failed:\n{r.stderr}\n{r.stdout}"

            cols = _get_columns(tmp.name, "scheme_runs")
            assert "frozen_envelope" in cols
            assert "database_backend" in cols
            assert cols["frozen_envelope"][1] is True, "frozen_envelope must be nullable"
            assert cols["database_backend"][1] is False, "database_backend must be NOT NULL"
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_upgrade_head_registers_check_constraints(self) -> None:
        """The three CHECK constraints are registered with their
        pinned names across both tables."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        try:
            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0

            orch_checks = _check_constraints(tmp.name, "orchestration_run_attempts")
            scheme_checks = _check_constraints(tmp.name, "scheme_runs")

            assert any(
                "ck_attempt_database_backend" in c and "('sqlite', 'postgresql')" in c
                for c in orch_checks
            ), f"missing ck_attempt_database_backend CHECK (got {orch_checks})"
            assert any(
                "ck_attempt_actor_principal_type" in c and "('user', 'service')" in c
                for c in orch_checks
            ), f"missing ck_attempt_actor_principal_type CHECK (got {orch_checks})"
            assert any(
                "ck_scheme_run_database_backend" in c and "('sqlite', 'postgresql')" in c
                for c in scheme_checks
            ), f"missing ck_scheme_run_database_backend CHECK (got {scheme_checks})"
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_upgrade_head_registers_idempotency_unique_index(self) -> None:
        """Unique index `uq_attempt_idempotency_key_db` is registered on
        (database_backend, idempotency_key)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        try:
            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0

            idx = _get_indexes(tmp.name, "orchestration_run_attempts")
            assert "uq_attempt_idempotency_key_db" in idx
            assert idx["uq_attempt_idempotency_key_db"] == [
                "database_backend",
                "idempotency_key",
            ]
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_upgrade_head_registers_attempt_to_scheme_run_fk(self) -> None:
        """FK `fk_attempt_scheme_run` links orchestration_run_attempts.scheme_run_id
        → scheme_runs.id."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        try:
            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0

            fks = _get_fk_list(tmp.name, "orchestration_run_attempts")
            match = next(
                (f for f in fks if f["from"] == "scheme_run_id" and f["table"] == "scheme_runs"),
                None,
            )
            assert match is not None, (
                f"missing FK orchestration_run_attempts.scheme_run_id → scheme_runs.id; "
                f"got fks={fks}"
            )
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_phase1_column_defaults_match_0036_contract(self) -> None:
        """After 0036 remediation, server_default semantics are:

        - ``database_backend``: NO column-level default (fail-closed;
          application MUST supply). dflt_value is NULL.
        - ``correlation_id``: explicit sentinel default
          ``legacy-migration-0036`` (rejects empty / whitespace via
          ``ck_attempt_correlation_id_nonempty``).
        - ``actor_principal_type``: ``'user'`` (unchanged from 0035).
        """
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        try:
            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0

            def _dflt(col_name: str) -> str | None:
                conn = sqlite3.connect(tmp.name)
                try:
                    row = conn.execute(
                        f"SELECT dflt_value FROM pragma_table_info("
                        f"'orchestration_run_attempts') WHERE name='{col_name}'"
                    ).fetchone()
                finally:
                    conn.close()
                return row[0] if row else None

            # database_backend: server_default was DROPPED in 0036
            assert _dflt("database_backend") is None, (
                "database_backend should have no column-level default "
                "after 0036 remediation; got " + repr(_dflt("database_backend"))
            )
            # correlation_id: server_default was DROPPED in 0037
            # (the legacy sentinel "legacy-migration-0036" remains
            # only as a column-level default when 0037 is
            # downgraded; new writes must supply the value
            # explicitly). Future writes cannot accidentally
            # mint a "fake" correlation_id by relying on the
            # default.
            assert _dflt("correlation_id") is None, (
                "correlation_id should have no column-level default "
                "after 0037 remediation; got " + repr(_dflt("correlation_id"))
            )
            # actor_principal_type: unchanged
            assert _dflt("actor_principal_type") == "'user'"
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class Test0035Phase1RoundtripSQLite:
    def test_downgrade_re_upgrade_full_roundtrip(self) -> None:
        """Upgrade head → downgrade to 0034 → re-upgrade head."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        try:
            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"

            r = _run_alembic(["downgrade", "0034_add_production_source_archives"], tmp.name)
            assert r.returncode == 0, f"downgrade 0034 failed:\n{r.stderr}\n{r.stdout}"

            cols_after_down = _get_columns(tmp.name, "orchestration_run_attempts")
            for name in (
                "idempotency_key",
                "database_backend",
                "correlation_id",
                "actor_principal_type",
                "scheme_run_id",
            ):
                assert name not in cols_after_down, f"column {name} still present after downgrade"

            scheme_cols_down = _get_columns(tmp.name, "scheme_runs")
            assert "frozen_envelope" not in scheme_cols_down
            assert "database_backend" not in scheme_cols_down

            r = _run_alembic(["upgrade", "head"], tmp.name)
            assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}\n{r.stdout}"

            cols_after_re = _get_columns(tmp.name, "orchestration_run_attempts")
            for name in (
                "idempotency_key",
                "database_backend",
                "correlation_id",
                "actor_principal_type",
                "scheme_run_id",
            ):
                assert name in cols_after_re, f"column {name} missing after re-upgrade"

            scheme_cols_re = _get_columns(tmp.name, "scheme_runs")
            assert "frozen_envelope" in scheme_cols_re
            assert "database_backend" in scheme_cols_re
        finally:
            Path(tmp.name).unlink(missing_ok=True)
