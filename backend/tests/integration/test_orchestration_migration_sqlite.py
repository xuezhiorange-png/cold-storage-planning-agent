"""SQLite migration integration tests — schema contracts via real Alembic upgrades.

Verifies: CHECK constraints, FK names, index names, partial unique index,
downgrade blocker using ``alembic upgrade head`` (NOT ``metadata.create_all``).

SQLite-only: skipped automatically when DATABASE_BACKEND is postgresql.
"""

from __future__ import annotations

import os

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite migration tests cannot run on PostgreSQL — use "
        "test_orchestration_migration_postgresql.py instead",
        allow_module_level=True,
    )

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def migrated_engine():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    db_path = Path(tmp.name)

    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)

    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic upgrade failed:\n{r.stderr}:\n{r.stdout}")

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield engine
    engine.dispose()
    db_path.unlink(missing_ok=True)


class TestTablesExist:
    def test_all_orchestration_tables(self, migrated_engine) -> None:
        insp = inspect(migrated_engine)
        tables = set(insp.get_table_names())
        required = {
            "orchestration_requests",
            "orchestration_execution_snapshots",
            "orchestration_coefficient_contexts",
            "orchestration_identities",
            "orchestration_run_attempts",
            "orchestration_source_bindings",
            "orchestration_audit_outbox",
            "scheme_weight_set_revisions",
        }
        assert required <= tables, f"Missing: {required - tables}"


class TestCheckConstraints:
    def test_calculation_run_check(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='calculation_runs'")
            ).scalar()
            assert "ck_calculation_run_orchestration_nullity" in ddl

    def test_scheme_run_check(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='scheme_runs'")
            ).scalar()
            assert "ck_scheme_run_source_mode_nullity" in ddl

    def test_request_check(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            ddl = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='orchestration_requests'"  # noqa: E501
                )
            ).scalar()
            assert "ck_orch_request_status_nullity" in ddl


class TestIndexes:
    def test_one_running(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            idxs = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='orchestration_run_attempts'"  # noqa: E501
                )
            ).fetchall()
            names = {r[0] for r in idxs}
            assert "uq_attempt_one_running" in names

    def test_source_binding_slots(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            idxs = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='orchestration_source_bindings'"  # noqa: E501
                )
            ).fetchall()
            names = {r[0] for r in idxs}
            for slot in ("zone", "cooling_load", "equipment", "power", "investment"):
                assert f"ix_source_binding_{slot}_calculation_id" in names


class TestForeignKeys:
    def test_calculation_run_orch_fks(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            fks = conn.execute(text("PRAGMA foreign_key_list('calculation_runs')")).fetchall()
            targets = {(r[2], r[3]) for r in fks}
            expected = [
                ("orchestration_identities", "orchestration_identity_id"),
                ("orchestration_run_attempts", "orchestration_run_attempt_id"),
                ("orchestration_execution_snapshots", "execution_snapshot_id"),
                ("orchestration_coefficient_contexts", "coefficient_context_id"),
            ]
            for tbl, col in expected:
                assert (tbl, col) in targets, f"Missing FK: {tbl}.{col} -> {col}"


class TestDowngradeGate:
    def test_blocked_with_unresolvable_requested_project(self) -> None:
        """Downgrade blocked when PREFLIGHT_REJECTED record has unresolvable
        requested_project_id.

        The new schema allows storing unresolvable caller-provided identity.
        Rolling back would put those into FK-constrained columns.
        The blocker must fire BEFORE any schema mutation.
        """
        import sqlite3 as _sql
        import uuid as _uuid

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r_up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        # Insert a PREFLIGHT_REJECTED record with unresolvable requested_project_id
        unresolvable_id = "nonexistent-project-id"
        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO orchestration_requests "
            "(id, requested_project_id, requested_project_version_id, "
            "request_fingerprint, actor, correlation_id, status, "
            "failure_code, failure_field, failure_details, completed_at, "
            "created_at) "
            "VALUES (?, ?, ?, 'fp', 'test', 'corr', 'PREFLIGHT_REJECTED', "
            "'ERR', 'field', '{}', datetime('now'), datetime('now'))",
            (str(_uuid.uuid4()), unresolvable_id, unresolvable_id),
        )
        conn.commit()

        # Capture pre-downgrade state
        conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        conn.close()

        # ── Attempt downgrade to 0026 — must be blocked by 0027's guard ──
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0026_add_orchestration_persistence"],  # noqa: E501
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode != 0, (
            f"Downgrade should have been blocked with unresolvable data\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        # Migration 0026 / 0027 use "Cannot downgrade", migration 0034
        # uses "RuntimeError: downgrade blocked:".  Either is fine.
        combined = r.stderr + r.stdout
        assert "Cannot downgrade" in combined or "downgrade blocked" in combined, (
            f"Expected blocker message; got stderr={r.stderr!r} stdout={r.stdout!r}"
        )

        # ── Verify atomicity: the 0027→0026 step was blocked, but the
        # 0028→0027 step already committed (SQLite has no transactional DDL),
        # so the revision is now 0027, not 0026. ─────────────────────────
        conn2 = _sql.connect(str(db_path))
        conn2.execute("PRAGMA foreign_keys=ON")

        rev_after = conn2.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev_after == "0027_separate_requested_and_resolved_request_identity", (
            f"Expected revision 0027 after blocked 0028→0027→0026 downgrade, got {rev_after}"
        )

        # 0034 added production_source_archives; the partial downgrade
        # sequence dropping 0034→…→0027 may or may not drop intermediate
        # tables depending on SQLite's non-transactional DDL order.  Don't
        # pin exact table counts here — verify orchestration_requests
        # remains, which is the actual invariant under test.

        # orchestration_requests table still present
        exists = conn2.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='orchestration_requests'"
        ).fetchone()[0]
        assert exists == 1, "orchestration_requests table missing"

        # No __temp_orch_req residual
        temp_exists = conn2.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='__temp_orch_req'"
        ).fetchone()[0]
        assert temp_exists == 0, "__temp_orch_req should not exist"

        # CHECK still present
        ck_sql = conn2.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND sql LIKE '%ck_orch_request_status_nullity%'"
        ).fetchone()
        assert ck_sql is not None, "CHECK missing after blocked downgrade"

        conn2.close()
        db_path.unlink(missing_ok=True)

    def test_allowed_for_empty_database(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r_up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0026_add_orchestration_persistence"],  # noqa: E501
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"Downgrade failed on empty DB: {r.stderr}"

        # Verify revision rolled back to 0026
        import sqlite3 as _sql

        conn = _sql.connect(str(db_path))
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev == "0026_add_orchestration_persistence", f"Expected revision 0026, got {rev}"
        conn.close()
        db_path.unlink(missing_ok=True)

    def test_allowed_for_legacy_only_no_source_binding(self) -> None:
        """Downgrade succeeds when only legacy SchemeRuns exist, no SourceBinding."""
        import sqlite3 as _sql

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r_up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        pid = str(__import__("uuid").uuid4())
        pvid = str(__import__("uuid").uuid4())
        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) "
            "VALUES (?, 'T', 'Test', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))",
            (pid,),
        )
        conn.execute(
            "INSERT INTO project_versions (id, project_id, version_number, "
            "change_summary, status, created_by, created_at, updated_at, "
            "input_snapshot, calculation_snapshot, assumption_snapshot) "
            "VALUES (?, ?, 1, '', 'approved', 'sys', datetime('now'), "
            "datetime('now'), '{}', '{}', '{}')",
            (pvid, pid),
        )
        # Legacy SchemeRun — source_mode='legacy', no SourceBinding
        conn.execute(
            "INSERT INTO scheme_runs (id, project_id, project_version_id, "
            "weight_set_id, generator_version, source_snapshot_hash, status, "
            "requires_review, input_snapshot, assumption_snapshot, "
            "comparison_snapshot, candidates_snapshot, warning_messages, "
            "created_at, source_mode, database_backend) "
            "VALUES (?, ?, ?, 'ws-1', '1.0', 'h1', 'pending', 0, '{}', '{}', "
            "'{}', '{}', '[]', datetime('now'), 'legacy', 'sqlite')",
            (str(__import__("uuid").uuid4()), pid, pvid),
        )
        conn.commit()
        conn.close()

        # Downgrade should succeed — only legacy data
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0026_add_orchestration_persistence"],  # noqa: E501
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, (
            f"Downgrade should succeed with legacy-only data\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        db_path.unlink(missing_ok=True)

    def test_blocked_with_source_binding_no_production_scheme_run(self) -> None:
        """Downgrade blocked when PREFLIGHT_REJECTED record has unresolvable
        requested_project_id alongside a valid SourceBinding chain."""
        import sqlite3 as _sql
        import uuid as _uuid

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r_up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        # Minimal entities for a valid SourceBinding record
        pid = str(_uuid.uuid4())
        pvid = str(_uuid.uuid4())
        eid = str(_uuid.uuid4())
        cid_ctx = str(_uuid.uuid4())
        oid = str(_uuid.uuid4())
        aid = str(_uuid.uuid4())
        calc_ids = [str(_uuid.uuid4()) for _ in range(5)]
        src_bid = str(_uuid.uuid4())

        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) "
            "VALUES (?, 'T', 'Test', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))",
            (pid,),
        )
        conn.execute(
            "INSERT INTO project_versions (id, project_id, version_number, "
            "change_summary, status, created_by, created_at, updated_at, "
            "input_snapshot, calculation_snapshot, assumption_snapshot) "
            "VALUES (?, ?, 1, '', 'approved', 'sys', datetime('now'), "
            "datetime('now'), '{}', '{}', '{}')",
            (pvid, pid),
        )
        # ... (valid FK chain for SourceBinding) ...
        conn.execute(
            "INSERT INTO orchestration_execution_snapshots "
            "(id, project_id, project_version_id, version_number, input_snapshot, "
            "input_snapshot_hash, schema_version, captured_status, captured_at) "
            "VALUES (?, ?, ?, 1, '{}', 'h1', '1', 'approved', datetime('now'))",
            (eid, pid, pvid),
        )
        conn.execute(
            "INSERT INTO orchestration_coefficient_contexts "
            "(id, project_id, project_version_id, content, content_hash, "
            "schema_version, captured_at) "
            "VALUES (?, ?, ?, '{}', 'h1', '1', datetime('now'))",
            (cid_ctx, pid, pvid),
        )
        conn.execute(
            "INSERT INTO orchestration_identities "
            "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
            "definition_version, calculator_version_vector, status, created_at) "
            "VALUES (?, 'fp', ?, ?, '1', '{}', 'ACTIVE', datetime('now'))",
            (oid, eid, cid_ctx),
        )
        conn.execute(
            "INSERT INTO orchestration_run_attempts "
            "(id, identity_id, attempt_number, status, heartbeat_at, started_at, "
            "database_backend, correlation_id) "
            "VALUES (?, ?, 1, 'COMPLETED', datetime('now'), datetime('now'), "
            "'sqlite', 'legacy-migration-0036')",
            (aid, oid),
        )
        calc_types = ("zone", "cooling_load", "equipment", "power", "investment")
        calc_names = ("z", "cl", "eq", "pw", "inv")
        for cid, ctype, cname in zip(calc_ids, calc_types, calc_names, strict=True):
            conn.execute(
                "INSERT INTO calculation_runs "
                "(id, project_id, project_version_id, calculator_name, calculator_version, "
                "input_snapshot, result_snapshot, formulas, coefficients, assumptions, "
                "warnings, source_references, requires_review, created_at, "
                "calculation_type, orchestration_identity_id, "
                "orchestration_run_attempt_id, execution_snapshot_id, "
                "coefficient_context_id, input_hash, result_hash, provenance, "
                "schema_version, orchestration_fingerprint) "
                "VALUES (?, ?, ?, ?, '1.0', '{}', '{}', '[]', '[]', '[]', '[]', "
                "'[]', 0, datetime('now'), ?, ?, ?, ?, ?, 'h1', 'h1', '{}', '1', 'fp')",  # noqa: E501
                (cid, pid, pvid, cname, ctype, oid, aid, eid, cid_ctx),
            )
        conn.execute(
            "INSERT INTO orchestration_source_bindings "
            "(id, project_id, project_version_id, execution_snapshot_id, "
            "coefficient_context_id, orchestration_identity_id, "
            "orchestration_run_attempt_id, orchestration_fingerprint, "
            "zone_calculation_id, cooling_load_calculation_id, "
            "equipment_calculation_id, power_calculation_id, "
            "investment_calculation_id, per_calculation_result_hashes, "
            "combined_source_hash, schema_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'fp', ?, ?, ?, ?, ?, '{}', 'h1', "
            "'1', datetime('now'))",
            (
                src_bid,
                pid,
                pvid,
                eid,
                cid_ctx,
                oid,
                aid,
                calc_ids[0],
                calc_ids[1],
                calc_ids[2],
                calc_ids[3],
                calc_ids[4],
            ),
        )

        # Insert unresolvable request — this triggers the downgrade blocker
        conn.execute(
            "INSERT INTO orchestration_requests "
            "(id, requested_project_id, requested_project_version_id, "
            "request_fingerprint, actor, correlation_id, status, "
            "failure_code, failure_field, failure_details, completed_at, "
            "created_at) "
            "VALUES (?, ?, ?, 'fp', 'test', 'corr', 'PREFLIGHT_REJECTED', "
            "'ERR', 'field', '{}', datetime('now'), datetime('now'))",
            (str(_uuid.uuid4()), "ghost-project", "ghost-version"),
        )
        conn.commit()
        conn.close()

        # Downgrade must be blocked due to unresolvable requested_project_id
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0026_add_orchestration_persistence"],  # noqa: E501
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode != 0, (
            f"Downgrade should be blocked with unresolvable request\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        # Migration 0026 / 0027 use "Cannot downgrade", migration 0034
        # uses "RuntimeError: downgrade blocked:".  Either is fine.
        combined = r.stderr + r.stdout
        assert "Cannot downgrade" in combined or "downgrade blocked" in combined, (
            f"Expected blocker message; got stderr={r.stderr!r}"
        )
        db_path.unlink(missing_ok=True)

    def test_blocked_with_valid_project_invalid_version(self) -> None:
        """Downgrade blocked when requested_project_id exists but
        requested_project_version_id does not."""
        import sqlite3 as _sql
        import uuid as _uuid

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r_up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")

        # Create a valid project but no project_version
        pid = str(_uuid.uuid4())
        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) "
            "VALUES (?, 'T', 'Test', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))",
            (pid,),
        )
        # Insert request with valid project but nonexistent version
        conn.execute(
            "INSERT INTO orchestration_requests "
            "(id, requested_project_id, requested_project_version_id, "
            "request_fingerprint, actor, correlation_id, status, "
            "failure_code, failure_field, failure_details, completed_at, "
            "created_at) "
            "VALUES (?, ?, ?, 'fp', 'test', 'corr', 'PREFLIGHT_REJECTED', "
            "'ERR', 'field', '{}', datetime('now'), datetime('now'))",
            (str(_uuid.uuid4()), pid, "nonexistent-version"),
        )
        conn.commit()

        conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        conn.close()

        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0026_add_orchestration_persistence"],  # noqa: E501
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode != 0, (
            f"Downgrade should be blocked with invalid version\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        # Migration 0026 / 0027 use "Cannot downgrade", migration 0034
        # uses "RuntimeError: downgrade blocked:".  Either is fine.
        combined = r.stderr + r.stdout
        assert "Cannot downgrade" in combined or "downgrade blocked" in combined, (
            f"Expected blocker message; got stderr={r.stderr!r}"
        )
        assert "requested_project_version_id" in (r.stderr + r.stdout), (
            f"Expected version_id mention; got stderr={r.stderr!r}"
        )

        # Verify atomicity: 0028→0027 committed but 0027→0026 blocked
        conn2 = _sql.connect(str(db_path))
        conn2.execute("PRAGMA foreign_keys=ON")
        rev_after = conn2.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev_after == "0027_separate_requested_and_resolved_request_identity", (
            f"Expected revision 0027 after blocked 0028→0027→0026 downgrade, got {rev_after}"
        )
        conn2.close()
        db_path.unlink(missing_ok=True)

    def test_blocked_with_version_project_mismatch(self) -> None:
        """Downgrade blocked when project_version exists but belongs to
        a different project than requested_project_id."""
        import sqlite3 as _sql
        import uuid as _uuid

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r_up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")

        pid_a = str(_uuid.uuid4())
        pid_b = str(_uuid.uuid4())
        pvid = str(_uuid.uuid4())

        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) "
            "VALUES (?, 'TA', 'TestA', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))",
            (pid_a,),
        )
        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) "
            "VALUES (?, 'TB', 'TestB', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))",
            (pid_b,),
        )
        # Version belongs to project B
        conn.execute(
            "INSERT INTO project_versions (id, project_id, version_number, "
            "change_summary, status, created_by, created_at, updated_at, "
            "input_snapshot, calculation_snapshot, assumption_snapshot) "
            "VALUES (?, ?, 1, '', 'approved', 'sys', datetime('now'), "
            "datetime('now'), '{}', '{}', '{}')",
            (pvid, pid_b),
        )
        # Request claims project A but version belongs to project B
        conn.execute(
            "INSERT INTO orchestration_requests "
            "(id, requested_project_id, requested_project_version_id, "
            "request_fingerprint, actor, correlation_id, status, "
            "failure_code, failure_field, failure_details, completed_at, "
            "created_at) "
            "VALUES (?, ?, ?, 'fp', 'test', 'corr', 'PREFLIGHT_REJECTED', "
            "'ERR', 'field', '{}', datetime('now'), datetime('now'))",
            (str(_uuid.uuid4()), pid_a, pvid),
        )
        conn.commit()

        conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        conn.close()

        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0026_add_orchestration_persistence"],  # noqa: E501
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode != 0, (
            f"Downgrade should be blocked with version-project mismatch\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        # Migration 0026 / 0027 use "Cannot downgrade", migration 0034
        # uses "RuntimeError: downgrade blocked:".  Either is fine.
        combined = r.stderr + r.stdout
        assert "Cannot downgrade" in combined or "downgrade blocked" in combined, (
            f"Expected blocker message; got stderr={r.stderr!r}"
        )
        assert "different project" in (r.stderr + r.stdout), (
            f"Expected 'different project' in message; got stderr={r.stderr!r}"
        )

        conn2 = _sql.connect(str(db_path))
        conn2.execute("PRAGMA foreign_keys=ON")
        rev_after = conn2.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev_after == "0027_separate_requested_and_resolved_request_identity", (
            f"Expected revision 0027 after blocked 0028→0027→0026 downgrade, got {rev_after}"
        )
        conn2.close()
        db_path.unlink(missing_ok=True)

    def test_all_resolvable_allows_downgrade(self) -> None:
        """Downgrade succeeds when all requested project/version IDs are resolvable."""
        import sqlite3 as _sql
        import uuid as _uuid

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r_up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")

        pid = str(_uuid.uuid4())
        pvid = str(_uuid.uuid4())

        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) "
            "VALUES (?, 'T', 'Test', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))",
            (pid,),
        )
        conn.execute(
            "INSERT INTO project_versions (id, project_id, version_number, "
            "change_summary, status, created_by, created_at, updated_at, "
            "input_snapshot, calculation_snapshot, assumption_snapshot) "
            "VALUES (?, ?, 1, '', 'approved', 'sys', datetime('now'), "
            "datetime('now'), '{}', '{}', '{}')",
            (pvid, pid),
        )
        # All IDs resolvable
        conn.execute(
            "INSERT INTO orchestration_requests "
            "(id, requested_project_id, requested_project_version_id, "
            "request_fingerprint, actor, correlation_id, status, "
            "created_at) "
            "VALUES (?, ?, ?, 'fp', 'test', 'corr', 'PENDING', "
            "datetime('now'))",
            (str(_uuid.uuid4()), pid, pvid),
        )
        conn.commit()
        conn.close()

        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0026_add_orchestration_persistence"],  # noqa: E501
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, (
            f"Downgrade should succeed with resolvable data\nstdout: {r.stdout}\nstderr: {r.stderr}"
        )
        db_path.unlink(missing_ok=True)


class TestTransactionBConstraints0028:
    """Tests for migration 0028 — Transaction B constraints.

    Verifies: ``ck_calculation_run_fingerprint_nullity`` CHECK,
    ``uq_calculation_run_attempt_type`` UNIQUE,
    ``ck_source_binding_slot_distinct`` CHECK, and
    upgrade/downgrade roundtrip.
    """

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _make_db():
        """Create a temp SQLite DB upgraded to head.  Returns ``(path, conn)``."""
        import sqlite3 as _sql

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            db_path.unlink(missing_ok=True)
            pytest.fail(f"Upgrade failed:\n{r.stderr}\n{r.stdout}")

        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        return db_path, conn

    @staticmethod
    def _setup_chain(conn, pid=None, pvid=None):
        """Insert FK chain: project → version → snapshot → context → identity → attempt.

        Returns a dict of all generated IDs.
        """
        import uuid as _uuid

        ids = {
            "pid": pid or str(_uuid.uuid4()),
            "pvid": pvid or str(_uuid.uuid4()),
            "eid": str(_uuid.uuid4()),
            "cid": str(_uuid.uuid4()),
            "oid": str(_uuid.uuid4()),
            "aid": str(_uuid.uuid4()),
        }
        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, "
            "status, current_version_number, created_at, updated_at) "
            "VALUES (?, 'T', 'Test', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))",
            (ids["pid"],),
        )
        conn.execute(
            "INSERT INTO project_versions (id, project_id, version_number, "
            "change_summary, status, created_by, created_at, updated_at, "
            "input_snapshot, calculation_snapshot, assumption_snapshot) "
            "VALUES (?, ?, 1, '', 'approved', 'sys', datetime('now'), "
            "datetime('now'), '{}', '{}', '{}')",
            (ids["pvid"], ids["pid"]),
        )
        conn.execute(
            "INSERT INTO orchestration_execution_snapshots "
            "(id, project_id, project_version_id, version_number, input_snapshot, "
            "input_snapshot_hash, schema_version, captured_status, captured_at) "
            "VALUES (?, ?, ?, 1, '{}', 'h1', '1', 'approved', datetime('now'))",
            (ids["eid"], ids["pid"], ids["pvid"]),
        )
        conn.execute(
            "INSERT INTO orchestration_coefficient_contexts "
            "(id, project_id, project_version_id, content, content_hash, "
            "schema_version, captured_at) "
            "VALUES (?, ?, ?, '{}', 'h1', '1', datetime('now'))",
            (ids["cid"], ids["pid"], ids["pvid"]),
        )
        conn.execute(
            "INSERT INTO orchestration_identities "
            "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
            "definition_version, calculator_version_vector, status, created_at) "
            "VALUES (?, 'fp', ?, ?, '1', '{}', 'ACTIVE', datetime('now'))",
            (ids["oid"], ids["eid"], ids["cid"]),
        )
        conn.execute(
            "INSERT INTO orchestration_run_attempts "
            "(id, identity_id, attempt_number, status, heartbeat_at, started_at, "
            "database_backend, correlation_id) "
            "VALUES (?, ?, 1, 'COMPLETED', datetime('now'), datetime('now'), "
            "'sqlite', 'legacy-migration-0036')",
            (ids["aid"], ids["oid"]),
        )
        return ids

    @staticmethod
    def _insert_orchestrated_calc_run(conn, ids, calc_type="zone", calc_name="z"):
        """Insert a fully orchestrated calculation_run.  Returns the new row ID."""
        import uuid as _uuid

        cid = str(_uuid.uuid4())
        conn.execute(
            "INSERT INTO calculation_runs "
            "(id, project_id, project_version_id, calculator_name, "
            "calculator_version, input_snapshot, result_snapshot, formulas, "
            "coefficients, assumptions, warnings, source_references, "
            "requires_review, created_at, calculation_type, "
            "orchestration_identity_id, orchestration_run_attempt_id, "
            "execution_snapshot_id, coefficient_context_id, input_hash, "
            "result_hash, provenance, schema_version, orchestration_fingerprint) "
            "VALUES (?, ?, ?, ?, '1.0', '{}', '{}', '[]', '[]', '[]', '[]', "
            "'[]', 0, datetime('now'), ?, ?, ?, ?, ?, 'h1', 'h1', '{}', '1', 'fp')",
            (
                cid,
                ids["pid"],
                ids["pvid"],
                calc_name,
                calc_type,
                ids["oid"],
                ids["aid"],
                ids["eid"],
                ids["cid"],
            ),
        )
        return cid

    # ── Tests ────────────────────────────────────────────────────────────

    def test_orchestration_fingerprint_nullity_check_legacy(self) -> None:
        """Insert legacy row (all NULL orchestration fields) → success."""
        import uuid as _uuid

        db_path, conn = self._make_db()
        try:
            pid = str(_uuid.uuid4())
            pvid = str(_uuid.uuid4())
            conn.execute(
                "INSERT INTO projects (id, code, name, location, product_category, "
                "status, current_version_number, created_at, updated_at) "
                "VALUES (?, 'T', 'Test', 'TL', 'fruit', 'draft', 0, "
                "datetime('now'), datetime('now'))",
                (pid,),
            )
            conn.execute(
                "INSERT INTO project_versions (id, project_id, version_number, "
                "change_summary, status, created_by, created_at, updated_at, "
                "input_snapshot, calculation_snapshot, assumption_snapshot) "
                "VALUES (?, ?, 1, '', 'approved', 'sys', datetime('now'), "
                "datetime('now'), '{}', '{}', '{}')",
                (pvid, pid),
            )
            conn.execute(
                "INSERT INTO calculation_runs "
                "(id, project_id, project_version_id, calculator_name, "
                "calculator_version, input_snapshot, result_snapshot, formulas, "
                "coefficients, assumptions, warnings, source_references, "
                "requires_review, created_at) "
                "VALUES (?, ?, ?, 'zone', '1.0', '{}', '{}', "
                "'[]', '[]', '[]', '[]', '[]', 0, datetime('now'))",
                (str(_uuid.uuid4()), pid, pvid),
            )
            conn.commit()
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

    def test_orchestration_fingerprint_nullity_check_orchestrated(self) -> None:
        """Insert orchestrated row with all fields including fingerprint → success."""
        db_path, conn = self._make_db()
        try:
            ids = self._setup_chain(conn)
            self._insert_orchestrated_calc_run(conn, ids)
            conn.commit()
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

    def test_orchestration_fingerprint_nullity_rejects_partial(self) -> None:
        """Orchestration fields set but fingerprint NULL → CHECK violation."""
        import sqlite3 as _sql
        import uuid as _uuid

        db_path, conn = self._make_db()
        try:
            ids = self._setup_chain(conn)
            with pytest.raises(_sql.IntegrityError):
                conn.execute(
                    "INSERT INTO calculation_runs "
                    "(id, project_id, project_version_id, calculator_name, "
                    "calculator_version, input_snapshot, result_snapshot, formulas, "
                    "coefficients, assumptions, warnings, source_references, "
                    "requires_review, created_at, calculation_type, "
                    "orchestration_identity_id, orchestration_run_attempt_id, "
                    "execution_snapshot_id, coefficient_context_id, input_hash, "
                    "result_hash, provenance, schema_version, "
                    "orchestration_fingerprint) "
                    "VALUES (?, ?, ?, 'zone', '1.0', '{}', '{}', '[]', '[]', "
                    "'[]', '[]', '[]', 0, datetime('now'), 'zone', ?, ?, ?, ?, "
                    "'h1', 'h1', '{}', '1', NULL)",
                    (
                        str(_uuid.uuid4()),
                        ids["pid"],
                        ids["pvid"],
                        ids["oid"],
                        ids["aid"],
                        ids["eid"],
                        ids["cid"],
                    ),
                )
                conn.commit()
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

    def test_attempt_type_unique_constraint(self) -> None:
        """Two rows with same (attempt_id, calculation_type) → UNIQUE violation."""
        import sqlite3 as _sql

        db_path, conn = self._make_db()
        try:
            ids = self._setup_chain(conn)
            self._insert_orchestrated_calc_run(conn, ids, calc_type="zone", calc_name="z1")
            conn.commit()
            with pytest.raises(_sql.IntegrityError):
                self._insert_orchestrated_calc_run(conn, ids, calc_type="zone", calc_name="z2")
                conn.commit()
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

    def test_source_binding_slot_distinct_check_valid(self) -> None:
        """Insert source binding with 5 distinct slot IDs → success."""
        import uuid as _uuid

        db_path, conn = self._make_db()
        try:
            ids = self._setup_chain(conn)
            calc_types = ("zone", "cooling_load", "equipment", "power", "investment")
            calc_names = ("z", "cl", "eq", "pw", "inv")
            calc_ids = []
            for ctype, cname in zip(calc_types, calc_names, strict=True):
                cid = self._insert_orchestrated_calc_run(
                    conn, ids, calc_type=ctype, calc_name=cname
                )
                calc_ids.append(cid)
            conn.commit()
            conn.execute(
                "INSERT INTO orchestration_source_bindings "
                "(id, project_id, project_version_id, execution_snapshot_id, "
                "coefficient_context_id, orchestration_identity_id, "
                "orchestration_run_attempt_id, orchestration_fingerprint, "
                "zone_calculation_id, cooling_load_calculation_id, "
                "equipment_calculation_id, power_calculation_id, "
                "investment_calculation_id, per_calculation_result_hashes, "
                "combined_source_hash, schema_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'fp', ?, ?, ?, ?, ?, '{}', 'h1', "
                "'1', datetime('now'))",
                (
                    str(_uuid.uuid4()),
                    ids["pid"],
                    ids["pvid"],
                    ids["eid"],
                    ids["cid"],
                    ids["oid"],
                    ids["aid"],
                    calc_ids[0],
                    calc_ids[1],
                    calc_ids[2],
                    calc_ids[3],
                    calc_ids[4],
                ),
            )
            conn.commit()
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

    def test_source_binding_slot_distinct_check_rejects_duplicate(self) -> None:
        """Insert source binding with duplicate slot IDs → CHECK violation."""
        import sqlite3 as _sql
        import uuid as _uuid

        db_path, conn = self._make_db()
        try:
            ids = self._setup_chain(conn)
            # Create 4 calc runs (enough for 5 slots with one duplicate)
            calc_types = ("zone", "cooling_load", "equipment", "power")
            calc_names = ("z", "cl", "eq", "pw")
            calc_ids = []
            for ctype, cname in zip(calc_types, calc_names, strict=True):
                cid = self._insert_orchestrated_calc_run(
                    conn, ids, calc_type=ctype, calc_name=cname
                )
                calc_ids.append(cid)
            conn.commit()
            # zone and cooling_load share calc_ids[0] → CHECK violation
            with pytest.raises(_sql.IntegrityError):
                conn.execute(
                    "INSERT INTO orchestration_source_bindings "
                    "(id, project_id, project_version_id, execution_snapshot_id, "
                    "coefficient_context_id, orchestration_identity_id, "
                    "orchestration_run_attempt_id, orchestration_fingerprint, "
                    "zone_calculation_id, cooling_load_calculation_id, "
                    "equipment_calculation_id, power_calculation_id, "
                    "investment_calculation_id, per_calculation_result_hashes, "
                    "combined_source_hash, schema_version, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'fp', ?, ?, ?, ?, ?, '{}', 'h1', "
                    "'1', datetime('now'))",
                    (
                        str(_uuid.uuid4()),
                        ids["pid"],
                        ids["pvid"],
                        ids["eid"],
                        ids["cid"],
                        ids["oid"],
                        ids["aid"],
                        calc_ids[0],  # zone
                        calc_ids[0],  # cooling_load — DUPLICATE
                        calc_ids[2],  # equipment
                        calc_ids[3],  # power
                        calc_ids[1],  # investment
                    ),
                )
                conn.commit()
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

    def test_upgrade_downgrade_roundtrip(self) -> None:
        """Upgrade to 0028, downgrade to 0027, re-upgrade to 0028 → success."""
        import sqlite3 as _sql

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        # Upgrade to head (0032)
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"Upgrade to head failed:\n{r.stderr}\n{r.stdout}"

        conn = _sql.connect(str(db_path))
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        expected_rev = "0037_phase1_drop_correlation_id_default"
        assert rev == expected_rev, f"Expected {expected_rev}, got {rev}"
        conn.close()

        # Downgrade to 0027
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0027"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"Downgrade to 0027 failed:\n{r.stderr}\n{r.stdout}"

        conn = _sql.connect(str(db_path))
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev == "0027_separate_requested_and_resolved_request_identity", (
            f"Expected 0027, got {rev}"
        )
        conn.close()

        # Re-upgrade to head
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"Re-upgrade to head failed:\n{r.stderr}\n{r.stdout}"

        conn = _sql.connect(str(db_path))
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        expected_rev = "0037_phase1_drop_correlation_id_default"
        assert rev == expected_rev, f"Expected {expected_rev}, got {rev}"
        conn.close()
        db_path.unlink(missing_ok=True)


class TestAuditEventAndWeightSet:
    def test_outbox_event_id_not_null(self, migrated_engine) -> None:
        with migrated_engine.connect() as conn:
            cols = conn.execute(text("PRAGMA table_info('audit_events')")).fetchall()
            outbox = [c for c in cols if c[1] == "outbox_event_id"]
            assert len(outbox) == 1 and outbox[0][3] == 1

    def test_weight_set_revisions(self, migrated_engine) -> None:
        insp = inspect(migrated_engine)
        assert "scheme_weight_set_revisions" in insp.get_table_names()
        uqs = insp.get_unique_constraints("scheme_weight_set_revisions")
        names = {c["name"] for c in uqs if c.get("name")}
        assert "uq_scheme_weight_set_revision_code_revision" in names


# ── P0-4 (Round 7): frozen envelope hashing helper ──────────────────────────


class TestFrozenEnvelopeHelperV1:
    """Migration 0033 must NOT import the application-layer envelope hashing
    algorithm.  Historical migrations must remain stable even if the
    application evolves.  The frozen helper lives under
    ``backend/alembic/helpers/frozen_outbox_envelope_v1.py`` and is
    byte-stable."""

    MIGRATION_PATH = BACKEND_DIR / "alembic" / "versions" / "0033_extend_outbox_envelope.py"

    def test_migration_0033_does_not_import_application_layer(self) -> None:
        """The migration script source MUST NOT import from the application
        layer (parse ``import`` statements, ignore comments/docstrings)."""
        import ast

        text_content = self.MIGRATION_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text_content)
        forbidden_substrings = (
            "cold_storage.modules.orchestration.application.outbox_identity",
            "cold_storage.modules.orchestration.application",
        )
        # Walk all import / import-from nodes — anywhere in the file.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for bad in forbidden_substrings:
                        assert bad not in alias.name, (
                            f"migration 0033 must not import application layer "
                            f"(found {alias.name!r}); "
                            "use alembic.helpers.frozen_outbox_envelope_v1 instead"
                        )
            elif isinstance(node, ast.ImportFrom):
                # module can be None for `from . import x`
                if node.module is None:
                    continue
                # Also inspect the function bodies' dynamic __import__
                # calls? Skip — Python AST only catches static imports.
                for bad in forbidden_substrings:
                    assert bad not in node.module, (
                        f"migration 0033 must not import application layer "
                        f"(found from {node.module!r} import "
                        f"{[a.name for a in node.names]}); "
                        "use alembic.helpers.frozen_outbox_envelope_v1 instead"
                    )

    def test_frozen_helper_is_byte_stable(self) -> None:
        """Two consecutive calls to ``compute_envelope_hash_v1`` MUST return
        identical bytes for identical inputs (frozen, no globals)."""
        import sys

        # The local alembic/ dir hosts the helpers package; insert it so
        # ``import helpers`` resolves here instead of against any third-party
        # package of the same name.
        helpers_dir = BACKEND_DIR / "alembic"
        if str(helpers_dir) not in sys.path:
            sys.path.insert(0, str(helpers_dir))
        from helpers.frozen_outbox_envelope_v1 import (  # type: ignore[import-not-found]
            compute_envelope_hash_v1 as fn,
        )

        kwargs = dict(
            event_schema_version="1.0",
            event_type="evt",
            aggregate_type="agg",
            aggregate_id="ag1",
            actor="actor-1",
            correlation_id="corr-1",
            occurred_at="2024-01-01T00:00:00+00:00",
            request_id="r1",
            identity_id="id1",
            attempt_id="att1",
            calculation_run_id=None,
            source_binding_id=None,
            payload={"k": 1, "nested": {"a": [1, 2, 3]}},
            event_identity="ei-1",
        )
        h1 = fn(**kwargs)
        h2 = fn(**kwargs)
        assert h1 == h2, "frozen helper MUST be deterministic"
        assert len(h1) == 64, "SHA-256 hex must be 64 chars"
        assert all(c in "0123456789abcdef" for c in h1), "must be lowercase hex"

    def test_frozen_helper_does_not_import_application(self) -> None:
        """The frozen helper module must not transitively depend on
        ``cold_storage.modules.orchestration`` so that it cannot change
        when the application evolves."""
        import importlib
        import sys

        # Force a fresh import to inspect its module-level attributes.
        # Insert the local alembic/ dir onto sys.path so the local helpers/
        # package wins over any installed third-party package of the same name.

        helpers_dir = BACKEND_DIR / "alembic"
        if str(helpers_dir) not in sys.path:
            sys.path.insert(0, str(helpers_dir))
        mod_name = "helpers.frozen_outbox_envelope_v1"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        mod = importlib.import_module(mod_name)
        # Inspect source to be sure the module does not pull in cold_storage.
        src = (BACKEND_DIR / "alembic" / "helpers" / "frozen_outbox_envelope_v1.py").read_text(
            encoding="utf-8"
        )
        assert "cold_storage" not in src, (
            "frozen helper must NOT import from cold_storage (application layer); "
            "historical migrations must remain stable"
        )
        # Compute a hash and confirm it works.
        h = mod.compute_envelope_hash_v1(
            event_schema_version="1.0",
            event_type="t",
            aggregate_type="a",
            aggregate_id="i",
            actor="x",
            correlation_id="c",
            occurred_at="2024-01-01T00:00:00+00:00",
            request_id=None,
            identity_id=None,
            attempt_id=None,
            calculation_run_id=None,
            source_binding_id=None,
            payload={"k": 1},
            event_identity=None,
        )
        assert isinstance(h, str) and len(h) == 64

    def test_frozen_helper_payload_hash_works(self) -> None:
        import sys

        helpers_dir = BACKEND_DIR / "alembic"
        if str(helpers_dir) not in sys.path:
            sys.path.insert(0, str(helpers_dir))
        from helpers.frozen_outbox_envelope_v1 import (  # type: ignore[import-not-found]
            compute_payload_hash_v1,
        )

        h = compute_payload_hash_v1({"a": 1, "b": [1, 2]})
        assert len(h) == 64
        # Determinism
        assert compute_payload_hash_v1({"a": 1, "b": [1, 2]}) == h

    def test_migration_backfill_non_dict_payload_fails_closed(self) -> None:
        """The fail-closed RuntimeError path on non-dict legacy payload MUST
        be present in the migration source (defense in depth — even though
        the schema rejects non-dict on INSERT today, migration must still
        refuse to silently substitute ``{}``)."""
        text_content = self.MIGRATION_PATH.read_text(encoding="utf-8")
        assert "outbox backfill encountered non-dict payload" in text_content, (
            "migration 0033 must still fail closed on non-dict legacy payloads"
        )
        assert "extend _legacy_payload_canonical() before retrying" in text_content

    def test_migration_backfill_helpers_use_v1_suffix(self) -> None:
        """The migration must call the ``_v1``-suffixed helpers (or import
        them) so that any future ``_v2`` cannot silently change this
        migration."""
        text_content = self.MIGRATION_PATH.read_text(encoding="utf-8")
        assert "canonical_json_v1" in text_content
        assert "compute_envelope_hash_v1" in text_content
