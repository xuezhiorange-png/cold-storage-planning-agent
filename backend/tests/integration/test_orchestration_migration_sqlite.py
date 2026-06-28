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
    def test_blocked_with_full_fk_chain(self) -> None:
        """Downgrade blocked when real production FK chain exists.

        Builds a complete valid FK chain: Project → Version → Snapshot →
        Context → Identity → Attempt → 5 CalculationRuns → SourceBinding →
        SchemeWeightSet → SchemeWeightSetRevision → production SchemeRun.
        Verifies atomicity after blocked downgrade.
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

        # ── Build full real FK chain ────────────────────────────────────
        pid = str(_uuid.uuid4())
        pvid = str(_uuid.uuid4())
        eid = str(_uuid.uuid4())
        cid_ctx = str(_uuid.uuid4())
        oid = str(_uuid.uuid4())
        aid = str(_uuid.uuid4())
        calc_ids = [str(_uuid.uuid4()) for _ in range(5)]
        src_bid = str(_uuid.uuid4())
        wsid = str(_uuid.uuid4())
        wsrid = str(_uuid.uuid4())
        srid = str(_uuid.uuid4())
        fp_val = "fp-" + str(_uuid.uuid4())

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
            "VALUES (?, ?, ?, ?, '1', '{}', 'ACTIVE', datetime('now'))",
            (oid, fp_val, eid, cid_ctx),
        )
        conn.execute(
            "INSERT INTO orchestration_run_attempts "
            "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
            "VALUES (?, ?, 1, 'COMPLETED', datetime('now'), datetime('now'))",
            (aid, oid),
        )
        # 5 CalculationRuns (zone, cooling_load, equipment, power, investment)
        calc_types = ("zone", "cooling_load", "equipment", "power", "investment")
        calc_names = ("zone_calc", "cl_calc", "eq_calc", "pw_calc", "inv_calc")
        for _i, (cid, ctype, cname) in enumerate(
            zip(calc_ids, calc_types, calc_names, strict=True)
        ):
            conn.execute(
                "INSERT INTO calculation_runs "
                "(id, project_id, project_version_id, calculator_name, calculator_version, "
                "input_snapshot, result_snapshot, formulas, coefficients, assumptions, "
                "warnings, source_references, requires_review, created_at, "
                "calculation_type, orchestration_identity_id, "
                "orchestration_run_attempt_id, execution_snapshot_id, "
                "coefficient_context_id, input_hash, result_hash, provenance, "
                "schema_version) "
                "VALUES (?, ?, ?, ?, '1.0', '{}', '{}', '[]', '[]', '[]', '[]', "
                "'[]', 0, datetime('now'), ?, ?, ?, ?, ?, 'h1', 'h1', '{}', '1')",
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
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 'h1', '1', "
            "datetime('now'))",
            (
                src_bid,
                pid,
                pvid,
                eid,
                cid_ctx,
                oid,
                aid,
                fp_val + "-prod",
                calc_ids[0],
                calc_ids[1],
                calc_ids[2],
                calc_ids[3],
                calc_ids[4],
            ),
        )
        conn.execute(
            "INSERT INTO scheme_weight_sets "
            "(id, code, name, revision, status, source_type, criteria, "
            "requires_review, created_at) "
            "VALUES (?, 'WS001', 'Test Set', 1, 'draft', 'system', '[]', 0, "
            "datetime('now'))",
            (wsid,),
        )
        conn.execute(
            "INSERT INTO scheme_weight_set_revisions "
            "(id, weight_set_id, code, revision, status, content, content_hash, "
            "generator_compatibility_version, created_at) "
            "VALUES (?, ?, 'WS001', 1, 'draft', '{}', 'h1', '1.0', "
            "datetime('now'))",
            (wsrid, wsid),
        )
        conn.execute(
            "INSERT INTO scheme_runs (id, project_id, project_version_id, "
            "weight_set_id, generator_version, source_snapshot_hash, status, "
            "requires_review, input_snapshot, assumption_snapshot, "
            "comparison_snapshot, candidates_snapshot, warning_messages, "
            "created_at, source_mode, source_binding_id, "
            "source_contract_version, weight_set_revision_id, "
            "weight_set_content_hash, weight_set_generator_compatibility_version, "
            "combined_source_hash) "
            "VALUES (?, ?, ?, ?, '1.0', 'h1', 'pending', 0, '{}', '{}', '{}', "
            "'{}', '[]', datetime('now'), 'production', ?, '1.0', ?, 'h1', "
            "'1.0', 'h1')",
            (srid, pid, pvid, wsid, src_bid, wsrid),
        )
        conn.commit()

        # Capture pre-downgrade state for atomicity checks
        rev_before = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        table_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        scheme_count = conn.execute(
            "SELECT COUNT(*) FROM scheme_runs WHERE source_mode='production'"
        ).fetchone()[0]
        sb_count = conn.execute("SELECT COUNT(*) FROM orchestration_source_bindings").fetchone()[0]
        calc_count = conn.execute(
            "SELECT COUNT(*) FROM calculation_runs WHERE calculation_type IS NOT NULL"
        ).fetchone()[0]
        combined_hash_before = conn.execute(
            "SELECT combined_source_hash FROM scheme_runs WHERE id=?", (srid,)
        ).fetchone()[0]
        conn.close()

        # ── Attempt downgrade — must be blocked ─────────────────────────
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "-1"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode != 0, (
            f"Downgrade should have been blocked with production data\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "Cannot downgrade" in r.stderr or "Cannot downgrade" in r.stdout, (
            f"Expected blocker message; got stderr={r.stderr!r} stdout={r.stdout!r}"
        )

        # ── Verify atomicity: nothing changed ───────────────────────────
        conn2 = _sql.connect(str(db_path))
        conn2.execute("PRAGMA foreign_keys=ON")

        rev_after = conn2.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev_after == rev_before, f"Revision changed from {rev_before} to {rev_after}"

        # All orchestration tables still present
        for tbl in (
            "orchestration_requests",
            "orchestration_execution_snapshots",
            "orchestration_coefficient_contexts",
            "orchestration_identities",
            "orchestration_run_attempts",
            "orchestration_source_bindings",
            "orchestration_audit_outbox",
            "scheme_weight_set_revisions",
        ):
            exists = conn2.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()[0]
            assert exists == 1, f"Table {tbl} missing after blocked downgrade"

        # Production rows unchanged
        post_scheme_count = conn2.execute(
            "SELECT COUNT(*) FROM scheme_runs WHERE source_mode='production'"
        ).fetchone()[0]
        assert post_scheme_count == scheme_count, (
            f"SchemeRun count changed: {scheme_count} → {post_scheme_count}"
        )
        post_sb_count = conn2.execute(
            "SELECT COUNT(*) FROM orchestration_source_bindings"
        ).fetchone()[0]
        assert post_sb_count == sb_count, (
            f"SourceBinding count changed: {sb_count} → {post_sb_count}"
        )
        post_calc_count = conn2.execute(
            "SELECT COUNT(*) FROM calculation_runs WHERE calculation_type IS NOT NULL"
        ).fetchone()[0]
        assert post_calc_count == calc_count, (
            f"CalculationRun count changed: {calc_count} → {post_calc_count}"
        )
        combined_hash_after = conn2.execute(
            "SELECT combined_source_hash FROM scheme_runs WHERE id=?", (srid,)
        ).fetchone()[0]
        assert combined_hash_after == combined_hash_before, (
            f"combined_source_hash changed: {combined_hash_before} → {combined_hash_after}"
        )

        # Tables not deleted
        post_table_count = conn2.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        assert post_table_count == table_count, (
            f"Table count changed: {table_count} → {post_table_count}"
        )

        # CHECKs still present
        for ck_name in (
            "ck_calculation_run_orchestration_nullity",
            "ck_scheme_run_source_mode_nullity",
            "ck_orch_request_status_nullity",
            "ck_outbox_status_nullity",
        ):
            ck_sql = conn2.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND sql LIKE '%' || ? || '%'",
                (ck_name,),
            ).fetchone()
            assert ck_sql is not None, f"CHECK {ck_name} missing after blocked downgrade"

        # FKs still present on calculation_runs
        fks = conn2.execute("PRAGMA foreign_key_list('calculation_runs')").fetchall()
        fk_targets = {(r[2], r[3]) for r in fks}
        assert ("orchestration_identities", "orchestration_identity_id") in fk_targets
        assert ("orchestration_run_attempts", "orchestration_run_attempt_id") in fk_targets

        # Partial unique index still present
        idx_names = {
            r[1]
            for r in conn2.execute(
                "SELECT * FROM sqlite_master WHERE type='index' "
                "AND tbl_name='orchestration_run_attempts'"
            ).fetchall()
        }
        assert "uq_attempt_one_running" in idx_names

        # SourceBinding slot indexes still present
        sb_idx_names = {
            r[1]
            for r in conn2.execute(
                "SELECT * FROM sqlite_master WHERE type='index' "
                "AND tbl_name='orchestration_source_bindings'"
            ).fetchall()
        }
        for slot in ("zone", "cooling_load", "equipment", "power", "investment"):
            idx_name = f"ix_source_binding_{slot}_calculation_id"
            assert idx_name in sb_idx_names, f"Index {idx_name} missing"

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
            [sys.executable, "-m", "alembic", "downgrade", "-1"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"Downgrade failed on empty DB: {r.stderr}"

        # Verify revision rolled back
        import sqlite3 as _sql

        conn = _sql.connect(str(db_path))
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev == "0025_add_outbox_claim_fields", f"Expected revision 0025, got {rev}"
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
            "created_at, source_mode) "
            "VALUES (?, ?, ?, 'ws-1', '1.0', 'h1', 'pending', 0, '{}', '{}', "
            "'{}', '{}', '[]', datetime('now'), 'legacy')",
            (str(__import__("uuid").uuid4()), pid, pvid),
        )
        conn.commit()
        conn.close()

        # Downgrade should succeed — only legacy data
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "-1"],
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
        """Downgrade blocked when any SourceBinding exists, even without production SchemeRun."""
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
            "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
            "VALUES (?, ?, 1, 'COMPLETED', datetime('now'), datetime('now'))",
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
                "schema_version) "
                "VALUES (?, ?, ?, ?, '1.0', '{}', '{}', '[]', '[]', '[]', '[]', "
                "'[]', 0, datetime('now'), ?, ?, ?, ?, ?, 'h1', 'h1', '{}', '1')",
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
        conn.commit()
        conn.close()

        # SourceBinding exists → downgrade must be blocked
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "-1"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode != 0, (
            f"Downgrade should be blocked when SourceBinding exists\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "Cannot downgrade" in r.stderr or "Cannot downgrade" in r.stdout, (
            f"Expected blocker message; got stderr={r.stderr!r}"
        )
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
