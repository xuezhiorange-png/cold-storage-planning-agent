"""SQLite migration integration tests — schema contracts via real Alembic upgrades.

Verifies: CHECK constraints, FK names, index names, partial unique index,
downgrade blocker using ``alembic upgrade head`` (NOT ``metadata.create_all``).
"""

from __future__ import annotations

import os
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
    def test_blocked_with_production_data(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )

        # Insert production SchemeRun via raw SQL
        import sqlite3 as _sql

        conn = _sql.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO projects (id, code, name, location, product_category, status, "
            "current_version_number, created_at, updated_at) "
            "VALUES ('p-pd', 'PD', 'Test', 'TL', 'fruit', 'draft', 0, "
            "datetime('now'), datetime('now'))"
        )
        conn.execute(
            "INSERT INTO project_versions (id, project_id, version_number, change_summary, "
            "status, created_by, created_at, updated_at, input_snapshot, calculation_snapshot, "
            "assumption_snapshot) "
            "VALUES ('pv-pd', 'p-pd', 1, '', 'draft', 'system', "
            "datetime('now'), datetime('now'), '{}', '{}', '{}')"
        )
        import uuid

        conn.execute(
            "INSERT INTO scheme_runs (id, project_id, project_version_id, weight_set_id, "
            "generator_version, source_snapshot_hash, status, requires_review, "
            "input_snapshot, assumption_snapshot, comparison_snapshot, candidates_snapshot, "
            "warning_messages, created_at, "
            "source_mode, source_binding_id, "
            "source_contract_version, weight_set_revision_id, weight_set_content_hash, "
            "weight_set_generator_compatibility_version, combined_source_hash) "
            "VALUES (?, 'p-pd', 'pv-pd', 'ws-1', '1.0', 'h1', 'pending', 0, "
            "'{}', '{}', '{}', '{}', '[]', datetime('now'), "
            "'production', 'sb-1', '1.0', 'wsr-1', 'h1', '1.0', 'h1')",
            (str(uuid.uuid4()),),
        )
        conn.commit()
        conn.close()

        try:
            r = subprocess.run(
                [sys.executable, "-m", "alembic", "downgrade", "-1"],
                cwd=BACKEND_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert r.returncode != 0, "Downgrade should have been blocked"
            assert "Cannot downgrade" in r.stderr, f"Wrong error: {r.stderr}"
        finally:
            db_path.unlink(missing_ok=True)

    def test_allowed_for_empty_database(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        env = os.environ.copy()
        env["SQLITE_PATH"] = str(db_path)

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            timeout=60,
        )
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "-1"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"Downgrade failed: {r.stderr}"
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
        assert "uq_weight_set_code_revision" in names
