"""SQLite migration 0034 downgrade guard tests.

Verifies that ``alembic downgrade 0033_extend_outbox_envelope`` is BLOCKED
when production SchemeRuns exist without a verified archive, and ALLOWED
when every production SchemeRun has a matching archive.

Empty schema → downgrade should succeed (no production SchemeRuns exist).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite migration downgrade guard tests are SQLite-only",
        allow_module_level=True,
    )


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _upgrade_to_head(db_path: Path) -> None:
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
        pytest.fail(f"alembic upgrade failed:\n{r.stderr}\n{r.stdout}")


def _downgrade_one(db_path: Path, target: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", target],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _projects_setup(conn: sqlite3.Connection) -> tuple[str, str]:
    """Insert a minimal projects + project_versions pair."""
    pid = str(uuid.uuid4())
    pvid = str(uuid.uuid4())
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
    return pid, pvid


def _insert_full_chain(conn: sqlite3.Connection) -> dict[str, str]:
    """Insert the full SourceBinding chain needed for a production SchemeRun.

    Returns a dict of useful ids.  No archive row — that is what each
    test controls.
    """
    import json as _json

    pid, pvid = _projects_setup(conn)

    eid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO orchestration_execution_snapshots "
        "(id, project_id, project_version_id, version_number, input_snapshot, "
        "input_snapshot_hash, schema_version, captured_status, captured_at) "
        "VALUES (?, ?, ?, 1, ?, 'h1', '1', 'approved', datetime('now'))",
        (eid, pid, pvid, _json.dumps({"k": "v"})),
    )
    cid_ctx = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO orchestration_coefficient_contexts "
        "(id, project_id, project_version_id, content, content_hash, "
        "schema_version, captured_at) "
        "VALUES (?, ?, ?, ?, 'h1', '1', datetime('now'))",
        (cid_ctx, pid, pvid, _json.dumps({"k": "v"})),
    )
    oid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO orchestration_identities "
        "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
        "definition_version, calculator_version_vector, status, created_at) "
        "VALUES (?, 'fp', ?, ?, '1', '{}', 'ACTIVE', datetime('now'))",
        (oid, eid, cid_ctx),
    )
    aid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO orchestration_run_attempts "
        "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
        "VALUES (?, ?, 1, 'COMPLETED', datetime('now'), datetime('now'))",
        (aid, oid),
    )

    calc_ids = []
    slot_to_calctype = {
        "zone": "zone",
        "cooling_load": "cooling_load",
        "equipment": "equipment",
        "power": "power",
        "investment": "investment",
    }
    slot_to_calcname = {
        "zone": "zcalc",
        "cooling_load": "ccalc",
        "equipment": "ecalc",
        "power": "pcalc",
        "investment": "icalc",
    }
    for slot, calcname in slot_to_calcname.items():
        cid = str(uuid.uuid4())
        calc_ids.append(cid)
        conn.execute(
            "INSERT INTO calculation_runs "
            "(id, project_id, project_version_id, calculator_name, calculator_version, "
            "input_snapshot, result_snapshot, formulas, coefficients, assumptions, "
            "warnings, source_references, requires_review, created_at, "
            "calculation_type, orchestration_identity_id, "
            "orchestration_run_attempt_id, execution_snapshot_id, "
            "coefficient_context_id, input_hash, result_hash, provenance, "
            "schema_version, orchestration_fingerprint) "
            "VALUES (?, ?, ?, ?, '1.0', ?, ?, '[]', '[]', '[]', '[]', "
            "'[]', 0, datetime('now'), ?, ?, ?, ?, ?, 'h1', 'h1', ?, '1', 'fp')",
            (
                cid,
                pid,
                pvid,
                calcname,
                _json.dumps({"k": "v"}),
                _json.dumps({"k": "r"}),
                slot_to_calctype[slot],
                oid,
                aid,
                eid,
                cid_ctx,
                _json.dumps({"k": "p"}),
            ),
        )

    src_bid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO orchestration_source_bindings "
        "(id, project_id, project_version_id, execution_snapshot_id, "
        "coefficient_context_id, orchestration_identity_id, "
        "orchestration_run_attempt_id, orchestration_fingerprint, "
        "zone_calculation_id, cooling_load_calculation_id, "
        "equipment_calculation_id, power_calculation_id, "
        "investment_calculation_id, per_calculation_result_hashes, "
        "combined_source_hash, schema_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'fp', ?, ?, ?, ?, ?, ?, 'combined-h', "
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
            _json.dumps({}),
        ),
    )

    return {
        "pid": pid,
        "pvid": pvid,
        "src_bid": src_bid,
        "sid": src_bid,
    }


def _insert_production_scheme_run(
    conn: sqlite3.Connection,
    pid: str,
    pvid: str,
    *,
    source_binding_id: str | None,
    combined_source_hash: str | None,
) -> str:
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO scheme_runs (id, project_id, project_version_id, "
        "weight_set_id, generator_version, source_snapshot_hash, "
        "status, requires_review, input_snapshot, assumption_snapshot, "
        "comparison_snapshot, candidates_snapshot, warning_messages, "
        "created_at, source_mode, "
        "source_binding_id, source_contract_version, "
        "weight_set_revision_id, weight_set_content_hash, "
        "weight_set_generator_compatibility_version, "
        "combined_source_hash, binding_schema_version, "
        "execution_snapshot_id, coefficient_context_id, "
        "orchestration_identity_id, authoritative_attempt_id, "
        "orchestration_fingerprint, "
        "zone_calculation_id, cooling_load_calculation_id, "
        "equipment_calculation_id, power_calculation_id, "
        "investment_calculation_id, "
        "zone_result_hash, cooling_load_result_hash, "
        "equipment_result_hash, power_result_hash, "
        "investment_result_hash) "
        "VALUES (?, ?, ?, 'ws-1', '1.0', 'h', 'completed', 0, '{}', "
        "'{}', '{}', '{}', '[]', datetime('now'), 'production', "
        "?, 'SVC-1.0', 'rev-1', 'wch-1', 'WG-1.0', ?, 'BSV-1.0', "
        "'snap-1', 'ctx-1', 'ident-1', 'att-1', 'fp', "
        "'zcalc', 'ccalc', 'ecalc', 'pcalc', 'icalc', "
        "'ZH', 'CH', 'EH', 'PH', 'IH')",
        (sid, pid, pvid, source_binding_id, combined_source_hash),
    )
    return sid


class TestEmptySchema:
    def test_empty_db_downgrade_succeeds(self) -> None:
        """No production SchemeRuns → downgrade should be allowed."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)

        _upgrade_to_head(db_path)
        r = _downgrade_one(db_path, "0033_extend_outbox_envelope")

        assert r.returncode == 0, f"downgrade failed unexpectedly:\n{r.stderr}"

        # Verify revision rolled back to 0033.
        conn = sqlite3.connect(str(db_path))
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev == "0033_extend_outbox_envelope", f"got {rev!r}"
        conn.close()
        db_path.unlink(missing_ok=True)


class TestDowngradeBlockedOnUnverifiedProduction:
    def test_blocked_when_production_scheme_run_has_no_archive(self) -> None:
        """A production SchemeRun with NO archive row must block downgrade."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)
        _upgrade_to_head(db_path)

        conn = sqlite3.connect(str(db_path))
        # Note: PRAGMA foreign_keys=OFF.  The guard test focuses on the
        # migration's query + RuntimeError, not FK correctness.  The
        # FKs would normally require the entire SourceBinding chain to
        # be valid, but our minimal fixture doesn't carry all of that
        # weight.  The test asserts downgrade behavior, not FK
        # enforcement, so turning FKs off here is appropriate.
        ids = _insert_full_chain(conn)
        sid = _insert_production_scheme_run(
            conn,
            ids["pid"],
            ids["pvid"],
            source_binding_id=ids["src_bid"],
            combined_source_hash="combined-h",
        )
        # NB: NO archive row inserted — this triggers the guard.
        conn.commit()
        conn.close()

        r = _downgrade_one(db_path, "0033_extend_outbox_envelope")

        assert r.returncode != 0, (
            "downgrade should be blocked when production SchemeRun has no archive"
        )
        assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
            f"missing blocker message:\nstderr={r.stderr!r}\nstdout={r.stdout!r}"
        )

        # Table must still exist (downgrade did not drop it).
        conn = sqlite3.connect(str(db_path))
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='production_source_archives'"
        ).fetchone()[0]
        assert exists == 1, "production_source_archives table missing after blocked downgrade"
        # SchemeRun still present.
        row = conn.execute("SELECT COUNT(*) FROM scheme_runs WHERE id=?", (sid,)).fetchone()[0]
        assert row == 1, "scheme_runs row missing"
        conn.close()
        db_path.unlink(missing_ok=True)


class TestDowngradeAllowedWithVerifiedArchive:
    def test_allowed_when_archive_matches_combined_source_hash(self) -> None:
        """Production SchemeRun WITH verified archive must allow downgrade."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
        tmp.close()
        db_path = Path(tmp.name)
        _upgrade_to_head(db_path)

        conn = sqlite3.connect(str(db_path))
        # See note in the corresponding blocked test: PRAGMA off for
        # the same minimal-fixture rationale.
        ids = _insert_full_chain(conn)
        sid = _insert_production_scheme_run(
            conn,
            ids["pid"],
            ids["pvid"],
            source_binding_id=ids["src_bid"],
            combined_source_hash="combined-h",
        )
        # Compute a real archive_payload + archive_hash via the canonical
        # helper, and persist.  We do NOT depend on the application
        # builder — we generate the same payload + hash manually here so
        # the test only verifies the migration guard, not the application.
        import hashlib
        import json as _json
        import sys as _sys

        _alembic_dir = BACKEND_DIR / "alembic"
        if str(_alembic_dir) not in _sys.path:
            _sys.path.insert(0, str(_alembic_dir))
        from helpers.frozen_scheme_source_archive_v1 import (  # type: ignore[import-not-found]  # noqa: E501
            canonical_json_v1,
        )

        payload = {
            "schema": "SchemeSourceArchiveV1",
            "scheme_run_id": sid,
            "source_binding_id": ids["src_bid"],
            "source_contract_version": "SVC-1.0",
            "binding_schema_version": "BSV-1.0",
            "combined_source_hash": "combined-h",
            "weight_set_revision_id": "rev-1",
            "weight_set_content_hash": "wch-1",
            "weight_set_generator_compatibility_version": "WG-1.0",
            "execution_snapshot_id": "snap-1",
            "coefficient_context_id": "ctx-1",
            "orchestration_identity_id": "ident-1",
            "authoritative_attempt_id": "att-1",
            "orchestration_fingerprint": "fp",
            "source_slots": {
                "zone": {"calculation_id": "zcalc", "result_hash": "ZH"},
                "cooling_load": {"calculation_id": "ccalc", "result_hash": "CH"},
                "equipment": {"calculation_id": "ecalc", "result_hash": "EH"},
                "power": {"calculation_id": "pcalc", "result_hash": "PH"},
                "investment": {"calculation_id": "icalc", "result_hash": "IH"},
            },
            "project_id": ids["pid"],
            "project_version_id": ids["pvid"],
            "generator_compatibility_version": "GCV-1.0",
            "captured_at": "2026-07-04T00:00:00+00:00",
        }
        canonical = canonical_json_v1(payload)
        archive_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        conn.execute(
            "INSERT INTO production_source_archives "
            "(id, scheme_run_id, source_binding_id, "
            "source_contract_version, archive_schema_version, "
            "archive_payload, archive_hash, combined_source_hash, "
            "weight_set_revision_id, weight_set_content_hash, "
            "binding_schema_version, execution_snapshot_id, "
            "coefficient_context_id, orchestration_identity_id, "
            "authoritative_attempt_id, orchestration_fingerprint, "
            "created_at, created_by, reason) "
            "VALUES (?, ?, ?, 'SVC-1.0', "
            "'SchemeSourceArchiveV1', ?, ?, 'combined-h', "
            "'rev-1', 'wch-1', 'BSV-1.0', 'snap-1', 'ctx-1', "
            "'ident-1', 'att-1', 'fp', datetime('now'), "
            "'seed', 'completed')",
            (
                str(uuid.uuid4()),
                sid,
                ids["src_bid"],
                _json.dumps(payload),
                archive_hash,
            ),
        )
        conn.commit()
        conn.close()

        r = _downgrade_one(db_path, "0033_extend_outbox_envelope")

        assert r.returncode == 0, (
            f"downgrade should succeed with verified archive:\n"
            f"stderr={r.stderr!r}\nstdout={r.stdout!r}"
        )

        # Verify revision rolled back to 0033.
        conn = sqlite3.connect(str(db_path))
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert rev == "0033_extend_outbox_envelope", f"got {rev!r}"
        # production_source_archives table is gone (downgrade succeeded).
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='production_source_archives'"
        ).fetchone()[0]
        assert exists == 0, "production_source_archives table should be dropped"
        conn.close()
        db_path.unlink(missing_ok=True)
