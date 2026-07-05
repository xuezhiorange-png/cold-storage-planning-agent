"""P0-3 hex validation tests for the downgrade guard — PostgreSQL path.

Parallel to test_migration_0034_downgrade_guard_hex_sqlite.py but
running against a real PostgreSQL instance via the project's
``pg_database_factory`` fixture.  Covers the same four user-stated
cases (uppercase, non-hex, length-63, length-65, mixed-case) plus
the lowercase-allowed baseline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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


def _plant_pg_chain(
    database_url: str,
    archive_hash: str,
) -> str:
    """Insert a minimal production SchemeRun + a synthetic archive row.

    On PG there's no ``PRAGMA ignore_check_constraints`` so we use
    raw SQL with explicit value substitution.  The CHECK on
    archive_hash length (64) prevents 63/65 from being inserted —
    those tests must use lengths that pass INSERT but fail the
    guard.  We work around by inserting WITH the length that
    bypasses CHECK but still triggers the guard:

        * length 64 lowercase  → allowed (positive case)
        * length 64 uppercase  → allowed by CHECK, blocked by guard
        * non-hex char         → allowed by CHECK (CH is 64-char hex length),
                                   blocked by guard

    Length 63 and 65 cases cannot be inserted by PG's CHECK
    constraint directly.  We use a separate strategy: bypass the
    CHECK by altering the constraint inside the test session.
    """
    e = create_engine(database_url, future=True)
    sid = "scheme-hex-pg-001"

    # Plant minimal production SchemeRun chain.
    with e.begin() as conn:
        # Disable page-level triggers so we can plant without a full
        # FK chain.  (These test rows will never be queried by the
        # downgrade guard except for the production_scheme_run
        # lookup.)
        conn.execute(text("SET session_replication_role = 'replica'"))
        # projects
        conn.execute(
            text(
                "INSERT INTO projects (id, code, name, location, "
                "product_category, status, current_version_number, "
                "created_at, updated_at) "
                "VALUES ('p-pg-hex', 'pg-hex', 'PG Hex Project', "
                "'pg-hex-loc', 'blueberry', 'draft', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        # project_versions
        conn.execute(
            text(
                "INSERT INTO project_versions (id, project_id, "
                "version_number, change_summary, created_by, status, "
                "created_at, input_snapshot) "
                "VALUES ('v-pg-hex', 'p-pg-hex', 1, 'pg hex', 'test', "
                "'approved', CURRENT_TIMESTAMP, '{}'::jsonb)"
            )
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
                "VALUES (:sid, 'p-pg-hex', 'v-pg-hex', 'ws-pg', "
                "'1.0', 'pg-snap-h', 'completed', false, '{}'::jsonb, "
                "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, "
                "CURRENT_TIMESTAMP, 'production', "
                "'binding-pg-hex', 'SVC-1.0', 'rev-pg-hex', "
                "'wch-pg', 'WG-1.0', 'combined-pg-hex', 'BSV-1.0', "
                "'snap-pg', 'ctx-pg', 'ident-pg', 'att-pg', 'fp', "
                "'zcalc-pg', 'ccalc-pg', 'ecalc-pg', 'pcalc-pg', "
                "'icalc-pg', 'ZH', 'CH', 'EH', 'PH', 'IH')"
            ),
            {"sid": sid},
        )

        # Plant the archive row with the supplied archive_hash.
        # If length is 63 or 65, the CHECK constraint will reject
        # the INSERT — for those cases we drop and re-create the
        # CHECK first.
        if len(archive_hash) != 64:
            conn.execute(
                text(
                    "ALTER TABLE production_source_archives "
                    "DROP CONSTRAINT ck_archive_hash_length"
                )
            )
        conn.execute(
            text(
                "INSERT INTO production_source_archives "
                "(id, scheme_run_id, source_binding_id, "
                "source_contract_version, archive_schema_version, "
                "archive_payload, archive_hash, "
                "combined_source_hash, weight_set_revision_id, "
                "weight_set_content_hash, binding_schema_version, "
                "execution_snapshot_id, coefficient_context_id, "
                "orchestration_identity_id, authoritative_attempt_id, "
                "orchestration_fingerprint, created_at, "
                "created_by, reason) "
                "VALUES ('archive-pg-hex', :sid, 'binding-pg-hex', "
                "'SVC-1.0', 'SchemeSourceArchiveV1', "
                "CAST(:payload AS jsonb), :archive_hash, "
                "'combined-pg-hex', 'rev-pg-hex', 'wch-pg', 'BSV-1.0', "
                "'snap-pg', 'ctx-pg', 'ident-pg', 'att-pg', 'fp', "
                "CURRENT_TIMESTAMP, 'seed', 'completed')"
            ),
            {
                "sid": sid,
                "archive_hash": archive_hash,
                "payload": json.dumps({"schema": "SchemeSourceArchiveV1"}),
            },
        )
        conn.execute(text("SET session_replication_role = 'origin'"))
    e.dispose()
    return sid


def _attempt_downgrade(database_url: str) -> subprocess.CompletedProcess[str]:
    return _run_alembic(database_url, "downgrade", "0033_extend_outbox_envelope")


# ── Tests ─────────────────────────────────────────────────────────────────


class TestHexStrictLowercasePostgreSQL:
    """PG-side acceptance for the P0-3 strict lowercase hex contract."""

    def test_lowercase_64_hex_allows_downgrade(
        self, pg_database: str,
    ) -> None:
        archive_hash = "a" * 64
        _plant_pg_chain(pg_database, archive_hash)

        r = _attempt_downgrade(pg_database)

        assert r.returncode == 0, (
            f"downgrade should be allowed for lowercase 64 hex; "
            f"exit={r.returncode} stderr={r.stderr!r}"
        )

    def test_uppercase_64_hex_blocks_downgrade(
        self, pg_database: str,
    ) -> None:
        archive_hash = "A" * 64
        _plant_pg_chain(pg_database, archive_hash)

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, (
            "downgrade should be BLOCKED for uppercase 64 hex"
        )
        assert (
            "downgrade blocked" in r.stderr
            or "downgrade blocked" in r.stdout
        ), f"missing blocker message:\nstderr={r.stderr!r}"

    def test_non_hex_char_blocks_downgrade(
        self, pg_database: str,
    ) -> None:
        archive_hash = "g" + "a" * 63
        assert len(archive_hash) == 64
        _plant_pg_chain(pg_database, archive_hash)

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, (
            "downgrade should be BLOCKED for non-hex char 'g'"
        )
        assert (
            "downgrade blocked" in r.stderr
            or "downgrade blocked" in r.stdout
        ), f"missing blocker message:\nstderr={r.stderr!r}"

    def test_length_63_blocks_downgrade(
        self, pg_database: str,
    ) -> None:
        archive_hash = "a" * 63
        _plant_pg_chain(pg_database, archive_hash)

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, (
            "downgrade should be BLOCKED for length=63"
        )
        assert (
            "downgrade blocked" in r.stderr
            or "downgrade blocked" in r.stdout
        ), f"missing blocker message:\nstderr={r.stderr!r}"

    def test_length_65_blocks_downgrade(
        self, pg_database: str,
    ) -> None:
        archive_hash = "a" * 65
        _plant_pg_chain(pg_database, archive_hash)

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, (
            "downgrade should be BLOCKED for length=65"
        )
        assert (
            "downgrade blocked" in r.stderr
            or "downgrade blocked" in r.stdout
        ), f"missing blocker message:\nstderr={r.stderr!r}"

    def test_mixed_case_blocks_downgrade(
        self, pg_database: str,
    ) -> None:
        archive_hash = "a" * 30 + "A" * 4 + "a" * 30
        assert len(archive_hash) == 64
        _plant_pg_chain(pg_database, archive_hash)

        r = _attempt_downgrade(pg_database)

        assert r.returncode != 0, (
            "downgrade should be BLOCKED for mixed-case"
        )
        assert (
            "downgrade blocked" in r.stderr
            or "downgrade blocked" in r.stdout
        ), f"missing blocker message:\nstderr={r.stderr!r}"

    def test_zero_string_of_correct_length_allows_downgrade(
        self, pg_database: str,
    ) -> None:
        archive_hash = "0" * 64
        _plant_pg_chain(pg_database, archive_hash)

        r = _attempt_downgrade(pg_database)

        assert r.returncode == 0, (
            f"downgrade should be allowed for '0'*64; "
            f"exit={r.returncode} stderr={r.stderr!r}"
        )
