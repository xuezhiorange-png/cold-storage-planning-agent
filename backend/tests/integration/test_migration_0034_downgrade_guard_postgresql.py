"""P2-1 follow-up: migration 0034 downgrade guard — PostgreSQL parity.

Mirrors the SQLite suite in
``test_migration_0034_downgrade_guard_sqlite.py`` (which has 3
cases) and extends it to the full 8-case matrix required by the
P2-1 review:

    1.  empty DB downgrade allowed
    2.  production SchemeRun without archive blocks downgrade
    3.  production SchemeRun with verified archive allows downgrade
    4.  archive combined_source_hash mismatch blocks downgrade
    5.  malformed archive_hash blocks downgrade
    6.  legacy / demo / non-production records do not block
    7.  table remains present after blocked downgrade
    8.  re-upgrade to head succeeds after allowed downgrade

Does NOT duplicate the hex-strictness cases — those are owned by
``test_migration_0034_downgrade_guard_hex_postgresql.py`` (added in
PR #33 round 9) and remain the canonical hex test surface.

Uses the project's ``pg_database`` fixture (auto-skips if PG is not
available — see ``tests/integration/conftest.py``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.postgresql

BACKEND_DIR = Path(__file__).resolve().parents[2]
TARGET_REVISION = "0033_extend_outbox_envelope"


# ── subprocess helpers ─────────────────────────────────────────────────


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


def _attempt_downgrade(database_url: str) -> subprocess.CompletedProcess[str]:
    return _run_alembic(database_url, "downgrade", TARGET_REVISION)


# ── planting helpers ──────────────────────────────────────────────────


def _make_pg_engine(database_url: str):
    return create_engine(database_url, future=True)


def _plant_minimal_production_chain(
    database_url: str,
    *,
    combined_source_hash: str = "combined-h",
    archive_hash: str | None = None,
    archive_present: bool = True,
    archive_combined_source_hash: str = "combined-h",
    archive_hash_known_good: bool = True,
) -> str:
    """Plant a minimal production SchemeRun + (optionally) archive.

    Returns the scheme_run_id.  Uses
    ``SET session_replication_role = 'replica'`` to bypass the FKs
    that the full production chain would otherwise require.

    The :param archive_hash_known_good: flag controls whether
    ``archive_hash`` is a 64-char lowercase hex; pass False to plant
    a malformed hash (the migration's guard must catch it).
    """
    e = _make_pg_engine(database_url)
    sid = "scheme-p2-" + uuid.uuid4().hex[:8]

    with e.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))

        # ── minimal project + project_version (real INSERTs, must satisfy NOT NULL) ──
        pid = "p-" + uuid.uuid4().hex[:8]
        pvid = "v-" + uuid.uuid4().hex[:8]
        conn.execute(
            text(
                "INSERT INTO projects (id, code, name, location, "
                "product_category, status, current_version_number, "
                "created_at, updated_at) "
                "VALUES (:pid, 'P2', 'P2', 'loc', 'fruit', 'draft', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"pid": pid},
        )
        conn.execute(
            text(
                "INSERT INTO project_versions (id, project_id, "
                "version_number, change_summary, created_by, status, "
                "created_at, input_snapshot) "
                "VALUES (:pvid, :pid, 1, 'p2', 'test', 'approved', "
                "CURRENT_TIMESTAMP, '{}'::jsonb)"
            ),
            {"pvid": pvid, "pid": pid},
        )

        # ── minimal production SchemeRun with orphan FK strings ──
        # session_replication_role='replica' (set above) disables FK
        # enforcement, so the orchestration_* / source_binding / weight
        # set columns can reference rows that don't exist.  The
        # downgrade guard only queries production_source_archives and
        # scheme_runs.
        conn.execute(
            text(
                "INSERT INTO scheme_runs ("
                "id, project_id, project_version_id, "
                "weight_set_id, generator_version, "
                "source_snapshot_hash, status, requires_review, "
                "input_snapshot, assumption_snapshot, "
                "comparison_snapshot, candidates_snapshot, "
                "warning_messages, created_at, source_mode, "
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
                "investment_result_hash, "
                "database_backend) VALUES ("
                ":sid, :pid, :pvid, 'ws', '1.0', 'h', 'completed', "
                "false, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, "
                "'{}'::jsonb, '[]'::jsonb, CURRENT_TIMESTAMP, "
                "'production', 'sb-orphan', 'SVC-1.0', "
                "'wsr-orphan', 'wch', 'WG-1.0', "
                ":csh, 'BSV-1.0', 'esi-orphan', 'cci-orphan', "
                "'oii-orphan', 'aai-orphan', 'fp', "
                "'zcalc', 'ccalc', 'ecalc', 'pcalc', 'icalc', "
                "'ZH', 'CH', 'EH', 'PH', 'IH', 'postgresql')"
            ),
            {"sid": sid, "pid": pid, "pvid": pvid, "csh": combined_source_hash},
        )

        # ── optional archive row ──
        if archive_present:
            if archive_hash_known_good:
                ahash = archive_hash or "a" * 64
            else:
                ahash = archive_hash or "NOT-HEX"
            # If the malformed hash isn't length 64, drop the CHECK
            # so the INSERT is accepted (the guard will still catch
            # it on downgrade).
            if len(ahash) != 64:
                conn.execute(
                    text(
                        "ALTER TABLE production_source_archives "
                        "DROP CONSTRAINT ck_archive_hash_length"
                    )
                )
            conn.execute(
                text(
                    "INSERT INTO production_source_archives ("
                    "id, scheme_run_id, source_binding_id, "
                    "source_contract_version, archive_schema_version, "
                    "archive_payload, archive_hash, "
                    "combined_source_hash, weight_set_revision_id, "
                    "weight_set_content_hash, binding_schema_version, "
                    "execution_snapshot_id, coefficient_context_id, "
                    "orchestration_identity_id, authoritative_attempt_id, "
                    "orchestration_fingerprint, created_at, "
                    "created_by, reason) VALUES ("
                    ":aid, :sid, 'sb-orphan', 'SVC-1.0', 'SchemeSourceArchiveV1', "
                    "CAST(:payload AS jsonb), :ahash, :acsh, "
                    "'wsr-orphan', 'wch', 'BSV-1.0', "
                    "'esi-orphan', 'cci-orphan', 'oii-orphan', "
                    "'aai-orphan', 'fp', CURRENT_TIMESTAMP, "
                    "'p2-seed', 'completed')"
                ),
                {
                    "aid": "a-" + uuid.uuid4().hex[:8],
                    "sid": sid,
                    "payload": json.dumps({"schema": "SchemeSourceArchiveV1"}),
                    "ahash": ahash,
                    "acsh": archive_combined_source_hash,
                },
            )

        conn.execute(text("SET session_replication_role = 'origin'"))

    e.dispose()
    return sid


def _table_exists(database_url: str, table_name: str) -> bool:
    e = _make_pg_engine(database_url)
    try:
        with e.connect() as conn:
            row = conn.execute(
                text("SELECT to_regclass(:tn)"),
                {"tn": table_name},
            ).scalar()
            return row is not None
    finally:
        e.dispose()


def _current_alembic_revision(database_url: str) -> str | None:
    e = _make_pg_engine(database_url)
    try:
        with e.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            return row[0] if row else None
    except Exception:
        return None
    finally:
        e.dispose()


# ── Tests ─────────────────────────────────────────────────────────────


class TestEmptySchema:
    def test_empty_db_downgrade_succeeds(self, pg_database: str) -> None:
        """No production SchemeRuns → downgrade must be allowed."""
        r = _attempt_downgrade(pg_database)
        assert r.returncode == 0, (
            f"downgrade should be allowed for empty DB; exit={r.returncode} stderr={r.stderr!r}"
        )
        assert _current_alembic_revision(pg_database) == TARGET_REVISION


class TestBlockedOnUnverifiedProduction:
    def test_blocked_when_production_scheme_run_has_no_archive(self, pg_database: str) -> None:
        """Production SchemeRun with NO archive must block downgrade."""
        sid = _plant_minimal_production_chain(pg_database, archive_present=False)

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, (
            "downgrade should be BLOCKED when production SchemeRun has no archive"
        )
        assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
            f"missing blocker message:\nstderr={r.stderr!r}\nstdout={r.stdout!r}"
        )

        # Table must still exist (downgrade did not drop it).
        assert _table_exists(pg_database, "production_source_archives"), (
            "production_source_archives table missing after blocked downgrade"
        )
        # The scheme_run should still be present.
        e = _make_pg_engine(pg_database)
        try:
            with e.connect() as conn:
                count = conn.execute(
                    text("SELECT COUNT(*) FROM scheme_runs WHERE id = :sid"),
                    {"sid": sid},
                ).scalar()
                assert count == 1, "scheme_runs row missing after blocked downgrade"
        finally:
            e.dispose()


class TestAllowedWithVerifiedArchive:
    def test_allowed_when_archive_matches_combined_source_hash(self, pg_database: str) -> None:
        """Production SchemeRun WITH verified archive must allow downgrade."""
        _plant_minimal_production_chain(
            pg_database,
            combined_source_hash="combined-h",
            archive_present=True,
            archive_combined_source_hash="combined-h",
            archive_hash="a" * 64,
        )

        r = _attempt_downgrade(pg_database)

        assert r.returncode == 0, (
            f"downgrade should be allowed with verified archive; "
            f"stderr={r.stderr!r}\nstdout={r.stdout!r}"
        )
        assert _current_alembic_revision(pg_database) == TARGET_REVISION

        # Table is gone (downgrade succeeded).
        assert not _table_exists(pg_database, "production_source_archives"), (
            "production_source_archives table should be dropped after allowed downgrade"
        )

    def test_blocked_when_archive_combined_source_hash_mismatches(self, pg_database: str) -> None:
        """Archive row whose combined_source_hash differs from the
        SchemeRun's combined_source_hash must block downgrade.
        """
        _plant_minimal_production_chain(
            pg_database,
            combined_source_hash="combined-h",
            archive_present=True,
            archive_combined_source_hash="WRONG-COMBINED",
            archive_hash="a" * 64,
        )

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, (
            "downgrade should be BLOCKED when archive combined_source_hash mismatches"
        )
        assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
            f"missing blocker message:\nstderr={r.stderr!r}\nstdout={r.stdout!r}"
        )
        # Table must still exist.
        assert _table_exists(pg_database, "production_source_archives"), (
            "production_source_archives table missing after blocked downgrade"
        )

    def test_blocked_when_archive_hash_is_malformed(self, pg_database: str) -> None:
        """Archive row whose ``archive_hash`` is not 64-char hex must
        block downgrade.
        """
        _plant_minimal_production_chain(
            pg_database,
            combined_source_hash="combined-h",
            archive_present=True,
            archive_combined_source_hash="combined-h",
            archive_hash="NOT-HEX-AT-ALL",
            archive_hash_known_good=False,
        )

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, "downgrade should be BLOCKED when archive_hash is malformed"
        assert "downgrade blocked" in r.stderr or "downgrade blocked" in r.stdout, (
            f"missing blocker message:\nstderr={r.stderr!r}\nstdout={r.stdout!r}"
        )
        assert _table_exists(pg_database, "production_source_archives"), (
            "production_source_archives table missing after blocked downgrade"
        )


class TestNoFalsePositives:
    def test_legacy_scheme_run_does_not_block_downgrade(self, pg_database: str) -> None:
        """A SchemeRun with ``source_mode = 'legacy'`` must not be
        treated as production → downgrade must remain allowed.
        """
        e = _make_pg_engine(pg_database)
        pid = "p-" + uuid.uuid4().hex[:8]
        pvid = "v-" + uuid.uuid4().hex[:8]
        sid = "sr-legacy-" + uuid.uuid4().hex[:8]
        with e.begin() as conn:
            conn.execute(text("SET session_replication_role = 'replica'"))
            conn.execute(
                text(
                    "INSERT INTO projects (id, code, name, location, "
                    "product_category, status, current_version_number, "
                    "created_at, updated_at) "
                    "VALUES (:pid, 'L', 'L', 'l', 'fruit', 'draft', 1, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"pid": pid},
            )
            conn.execute(
                text(
                    "INSERT INTO project_versions (id, project_id, "
                    "version_number, change_summary, created_by, status, "
                    "created_at, input_snapshot) "
                    "VALUES (:pvid, :pid, 1, 'l', 'test', 'approved', "
                    "CURRENT_TIMESTAMP, '{}'::jsonb)"
                ),
                {"pvid": pvid, "pid": pid},
            )
            conn.execute(
                text(
                    "INSERT INTO scheme_runs ("
                    "id, project_id, project_version_id, "
                    "weight_set_id, generator_version, "
                    "source_snapshot_hash, status, requires_review, "
                    "input_snapshot, assumption_snapshot, "
                    "comparison_snapshot, candidates_snapshot, "
                    "warning_messages, created_at, source_mode, "
                    "database_backend) VALUES ("
                    ":sid, :pid, :pvid, 'ws', '1.0', 'h', 'completed', "
                    "false, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, "
                    "'{}'::jsonb, '[]'::jsonb, CURRENT_TIMESTAMP, "
                    "'legacy', 'postgresql')"
                ),
                {"sid": sid, "pid": pid, "pvid": pvid},
            )
            conn.execute(text("SET session_replication_role = 'origin'"))
        e.dispose()

        r = _attempt_downgrade(pg_database)
        assert r.returncode == 0, (
            f"downgrade should be allowed when only legacy SchemeRuns exist; "
            f"stderr={r.stderr!r}\nstdout={r.stdout!r}"
        )
        assert _current_alembic_revision(pg_database) == TARGET_REVISION


class TestTableSurvivesBlocked:
    def test_table_remains_present_after_blocked_downgrade(self, pg_database: str) -> None:
        """Blocked downgrade must NOT drop the production_source_archives
        table — defence in depth: if a future migration adds a DROP
        after the guard, the blocked path is still safe.
        """
        _plant_minimal_production_chain(pg_database, archive_present=False)

        r = _attempt_downgrade(pg_database)
        assert r.returncode != 0
        assert _table_exists(pg_database, "production_source_archives")


class TestReUpgradeAfterAllowedDowngrade:
    def test_re_upgrade_to_head_succeeds_after_allowed_downgrade(self, pg_database: str) -> None:
        """After a clean downgrade (verified archive), re-upgrade to
        head must succeed and re-create the table.
        """
        _plant_minimal_production_chain(
            pg_database,
            combined_source_hash="combined-h",
            archive_present=True,
            archive_combined_source_hash="combined-h",
            archive_hash="a" * 64,
        )

        r1 = _attempt_downgrade(pg_database)
        assert r1.returncode == 0, f"downgrade failed: stderr={r1.stderr!r}"

        r2 = _run_alembic(pg_database, "upgrade", "head")
        assert r2.returncode == 0, (
            f"re-upgrade should succeed; stderr={r2.stderr!r}\nstdout={r2.stdout!r}"
        )
        assert _table_exists(pg_database, "production_source_archives"), (
            "production_source_archives table missing after re-upgrade"
        )
