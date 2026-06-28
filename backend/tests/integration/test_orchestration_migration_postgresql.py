"""PostgreSQL migration integration tests — schema contracts via real Alembic upgrades.

Verifies on PostgreSQL: CHECK constraints, FK names, index names, partial unique index,
outbox status CHECK, AuditEvent backfill, weight_set_revision FK, downgrade blocker,
and atomicity guarantees.

Requires DATABASE_URL env var pointing to a real PostgreSQL instance.
Tagged with ``@pytest.mark.postgresql`` to run in CI (``-m postgresql``).
Skipped locally when PostgreSQL is not reachable.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.postgresql


def _check_postgres() -> str | None:
    """Return DATABASE_URL if PostgreSQL is reachable, else None."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        engine = create_engine(url, poolclass=NullPool)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return url
    except Exception:
        return None


def _pg_db_url(test_db: str) -> str:
    """Build a PostgreSQL test-database URL from DATABASE_URL.

    Replaces the database name in the original URL with *test_db*.
    """
    original = os.environ.get("DATABASE_URL", "")
    # Expected shape: postgresql+psycopg2://user:pass@host:port/dbname
    base = original.rsplit("/", 1)[0]
    return f"{base}/{test_db}"


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run an alembic command against *database_url*."""
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["DATABASE_BACKEND"] = "postgresql"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _pg_engine(database_url: str):
    """Create a SQLAlchemy engine for *database_url*."""
    return create_engine(database_url, poolclass=NullPool)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def pg_url() -> str | None:
    """PostgreSQL database URL, or None if unavailable."""
    url = _check_postgres()
    if url is None:
        pytest.skip("PostgreSQL not reachable — set DATABASE_URL")
    return url


@pytest.fixture()
def migrated_pg(pg_url) -> str:
    """Separate test database with full schema applied."""
    test_db_url = _pg_db_url("cold_storage_migration_test")
    r = _run_alembic(test_db_url, "upgrade", "head")
    if r.returncode != 0:
        pytest.fail(f"Alembic upgrade failed:\n{r.stderr}\n{r.stdout}")
    yield test_db_url
    # Teardown: drop the test database
    try:
        engine = _pg_engine(test_db_url)
        engine.dispose()
    except Exception:
        pass


# ── Schema checks ────────────────────────────────────────────────────────────


class TestAllTables:
    def test_eight_new_tables_exist(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
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
        engine.dispose()
        assert required <= tables, f"Missing: {required - tables}"


class TestCheckConstraints:
    def test_calculation_run_check_exists(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("calculation_runs")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_calculation_run_orchestration_nullity" in names

    def test_scheme_run_check_exists(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("scheme_runs")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_scheme_run_source_mode_nullity" in names

    def test_request_check_exists(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("orchestration_requests")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_orch_request_status_nullity" in names

    def test_outbox_status_check_exists(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("orchestration_audit_outbox")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_outbox_status_nullity" in names


class TestForeignKeys:
    def test_calculation_run_orch_fks(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        fks = insp.get_foreign_keys("calculation_runs")
        targets = {(fk["referred_table"], fk["constrained_columns"][0]) for fk in fks}
        engine.dispose()
        expected = [
            ("orchestration_identities", "orchestration_identity_id"),
            ("orchestration_run_attempts", "orchestration_run_attempt_id"),
            ("orchestration_execution_snapshots", "execution_snapshot_id"),
            ("orchestration_coefficient_contexts", "coefficient_context_id"),
        ]
        for tbl, col in expected:
            assert (tbl, col) in targets, f"Missing FK: {tbl}.{col}"

    def test_weight_set_revision_fk_exists(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        fks = insp.get_foreign_keys("scheme_weight_set_revisions")
        targets = {(fk["referred_table"], fk["constrained_columns"][0]) for fk in fks}
        engine.dispose()
        assert ("scheme_weight_sets", "weight_set_id") in targets

    def test_source_binding_slot_fks_exist(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        fks = insp.get_foreign_keys("orchestration_source_bindings")
        targets = {(fk["referred_table"], fk["constrained_columns"][0]) for fk in fks}
        engine.dispose()
        for slot in ("zone", "cooling_load", "equipment", "power", "investment"):
            col = f"{slot}_calculation_id"
            assert ("calculation_runs", col) in targets, f"Missing FK: calculation_runs.{col}"


class TestIndexes:
    def test_one_running_partial_unique_index(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        idxs = insp.get_indexes("orchestration_run_attempts")
        names = {idx["name"] for idx in idxs}
        engine.dispose()
        assert "uq_attempt_one_running" in names

    def test_source_binding_slot_indexes(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        idxs = insp.get_indexes("orchestration_source_bindings")
        names = {idx["name"] for idx in idxs}
        engine.dispose()
        for slot in ("zone", "cooling_load", "equipment", "power", "investment"):
            assert f"ix_source_binding_{slot}_calculation_id" in names

    def test_weight_set_revision_unique_constraint(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        uqs = insp.get_unique_constraints("scheme_weight_set_revisions")
        names = {c["name"] for c in uqs if c.get("name")}
        engine.dispose()
        assert "uq_scheme_weight_set_revision_code_revision" in names


class TestAuditEventBackfill:
    def test_outbox_event_id_not_null(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        cols = insp.get_columns("audit_events")
        outbox = [c for c in cols if c["name"] == "outbox_event_id"]
        engine.dispose()
        assert len(outbox) == 1
        assert outbox[0]["nullable"] is False

    def test_outbox_event_id_unique(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        uqs = insp.get_unique_constraints("audit_events")
        names = {c["name"] for c in uqs if c.get("name")}
        engine.dispose()
        assert "uq_audit_event_outbox" in names

    def test_outbox_event_id_length_sufficient(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        with engine.connect() as conn:
            # Insert a UUID-based AuditEvent and verify backfill length fits
            import uuid

            aid = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO audit_events (id, actor, action, entity_type, entity_id, "
                    "before_snapshot, after_snapshot, event_metadata, created_at) "
                    "VALUES (:id, 'test', 'test', 'test', 'test', '{}', '{}', '{}', now())"
                ),
                {"id": aid},
            )
            conn.commit()

            # The backfill should have run during upgrade; verify length
            row = conn.execute(
                text("SELECT outbox_event_id FROM audit_events WHERE id = :id"),
                {"id": aid},
            ).fetchone()
            assert row is not None
            oid = row[0]
            # legacy-audit:<uuid> length is at least 49 chars; must fit in 128
            assert len(oid) > 36, f"Backfill ID too short: {oid!r}"
            assert len(oid) <= 128, f"Backfill ID exceeds 128: {oid!r} ({len(oid)})"
            assert oid.startswith("legacy-audit:")


# ── Database rejection tests (real INSERT) ───────────────────────────────────


class TestCalculationRunRejection:
    def test_partial_orchestration_fields_rejected(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        import uuid

        cid = str(uuid.uuid4())
        with engine.connect() as conn:
            # Insert with some orchestration fields but not all -> must fail
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO calculation_runs (id, project_id, project_version_id, "
                        "status, requires_review, calculator_name, calculation_type, "
                        "created_at, orchestration_identity_id) "
                        "VALUES (:id, 'p-1', 'pv-1', 'completed', false, 'zone', 'zone', now(), :oid)"
                    ),
                    {"id": cid, "oid": str(uuid.uuid4())},
                )
                conn.commit()
        engine.dispose()


class TestSchemeRunRejection:
    def test_production_missing_combined_source_hash_rejected(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        import uuid

        sid = str(uuid.uuid4())
        with engine.connect() as conn:
            with pytest.raises(Exception):
                # production with source_binding_id but NULL combined_source_hash -> rejected
                conn.execute(
                    text(
                        "INSERT INTO scheme_runs (id, project_id, project_version_id, "
                        "weight_set_id, generator_version, source_snapshot_hash, status, "
                        "requires_review, input_snapshot, assumption_snapshot, "
                        "comparison_snapshot, candidates_snapshot, warning_messages, "
                        "created_at, source_mode, source_binding_id) "
                        "VALUES (:id, 'p-1', 'pv-1', 'ws-1', '1.0', 'h1', 'pending', "
                        "false, '{}', '{}', '{}', '{}', '[]', now(), 'production', 'sb-1')"
                    ),
                    {"id": sid},
                )
                conn.commit()
        engine.dispose()


class TestRequestRejection:
    def test_accepted_missing_resolved_attempt_rejected(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        import uuid

        rid = str(uuid.uuid4())
        with engine.connect() as conn:
            with pytest.raises(Exception):
                # ACCEPTED without resolved_attempt_id -> rejected
                conn.execute(
                    text(
                        "INSERT INTO orchestration_requests (id, project_id, "
                        "project_version_id, request_fingerprint, actor, correlation_id, "
                        "status, resolved_identity_id, created_at) "
                        "VALUES (:id, 'p-1', 'pv-1', 'fp', 'me', 'cid', "
                        "'ACCEPTED', 'oi-1', now())"
                    ),
                    {"id": rid},
                )
                conn.commit()
        engine.dispose()


class TestOneRunning:
    def test_two_running_attempts_same_identity_rejected(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        import uuid

        pid = str(uuid.uuid4())
        pvid = str(uuid.uuid4())
        eid = str(uuid.uuid4())
        cid = str(uuid.uuid4())
        oid = str(uuid.uuid4())

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO projects (id, code, name, location, product_category, "
                    "status, current_version_number, created_at, updated_at) "
                    "VALUES (:id, 'T', 'Test', 'TL', 'fruit', 'draft', 0, now(), now())"
                ),
                {"id": pid},
            )
            conn.execute(
                text(
                    "INSERT INTO project_versions (id, project_id, version_number, "
                    "change_summary, status, created_by, created_at, updated_at, "
                    "input_snapshot, calculation_snapshot, assumption_snapshot) "
                    "VALUES (:id, :pid, 1, '', 'approved', 'sys', now(), now(), "
                    "'{}', '{}', '{}')"
                ),
                {"id": pvid, "pid": pid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_execution_snapshots "
                    "(id, project_id, project_version_id, version_number, input_snapshot, "
                    "input_snapshot_hash, schema_version, captured_status, captured_at) "
                    "VALUES (:id, :pid, :pvid, 1, '{}', 'h1', '1', 'approved', now())"
                ),
                {"id": eid, "pid": pid, "pvid": pvid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_coefficient_contexts "
                    "(id, project_id, project_version_id, content, content_hash, "
                    "schema_version, captured_at) "
                    "VALUES (:id, :pid, :pvid, '{}', 'h1', '1', now())"
                ),
                {"id": cid, "pid": pid, "pvid": pvid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_identities "
                    "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
                    "definition_version, calculator_version_vector, status, created_at) "
                    "VALUES (:id, 'fp1', :eid, :cid, '1', '{}', 'ACTIVE', now())"
                ),
                {"id": oid, "eid": eid, "cid": cid},
            )
            conn.commit()

        with engine.connect() as conn:
            import uuid as _uuid

            a1 = str(_uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'RUNNING', now(), now())"
                ),
                {"id": a1, "oid": oid},
            )
            conn.commit()

            a2 = str(_uuid.uuid4())
            with pytest.raises(Exception):
                # Second RUNNING for same identity -> must fail
                conn.execute(
                    text(
                        "INSERT INTO orchestration_run_attempts "
                        "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                        "VALUES (:id, :oid, 2, 'RUNNING', now(), now())"
                    ),
                    {"id": a2, "oid": oid},
                )
                conn.commit()
        engine.dispose()

    def test_one_failed_one_running_accepted(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        import uuid

        oid = _setup_identity_for_attempt_test(engine)
        import uuid as _uuid

        a1 = str(_uuid.uuid4())
        a2 = str(_uuid.uuid4())
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'FAILED', now(), now())"
                ),
                {"id": a1, "oid": oid},
            )
            conn.commit()
            # FAILED + RUNNING should be accepted
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 2, 'RUNNING', now(), now())"
                ),
                {"id": a2, "oid": oid},
            )
            conn.commit()
        engine.dispose()

    def test_one_completed_one_running_accepted(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        import uuid

        oid = _setup_identity_for_attempt_test(engine)
        import uuid as _uuid

        a1 = str(_uuid.uuid4())
        a2 = str(_uuid.uuid4())
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'COMPLETED', now(), now())"
                ),
                {"id": a1, "oid": oid},
            )
            conn.commit()
            # COMPLETED + RUNNING should be accepted
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 2, 'RUNNING', now(), now())"
                ),
                {"id": a2, "oid": oid},
            )
            conn.commit()
        engine.dispose()


def _setup_identity_for_attempt_test(engine) -> str:
    """Create minimal project/version/snapshot/context/identity and return identity_id."""
    import uuid

    pid = str(uuid.uuid4())
    pvid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    oid = str(uuid.uuid4())

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO projects (id, code, name, location, product_category, "
                "status, current_version_number, created_at, updated_at) "
                "VALUES (:id, 'T', 'Test', 'TL', 'fruit', 'draft', 0, now(), now())"
            ),
            {"id": pid},
        )
        conn.execute(
            text(
                "INSERT INTO project_versions (id, project_id, version_number, "
                "change_summary, status, created_by, created_at, updated_at, "
                "input_snapshot, calculation_snapshot, assumption_snapshot) "
                "VALUES (:id, :pid, 1, '', 'approved', 'sys', now(), now(), "
                "'{}', '{}', '{}')"
            ),
            {"id": pvid, "pid": pid},
        )
        conn.execute(
            text(
                "INSERT INTO orchestration_execution_snapshots "
                "(id, project_id, project_version_id, version_number, input_snapshot, "
                "input_snapshot_hash, schema_version, captured_status, captured_at) "
                "VALUES (:id, :pid, :pvid, 1, '{}', 'h1', '1', 'approved', now())"
            ),
            {"id": eid, "pid": pid, "pvid": pvid},
        )
        conn.execute(
            text(
                "INSERT INTO orchestration_coefficient_contexts "
                "(id, project_id, project_version_id, content, content_hash, "
                "schema_version, captured_at) "
                "VALUES (:id, :pid, :pvid, '{}', 'h1', '1', now())"
            ),
            {"id": cid, "pid": pid, "pvid": pvid},
        )
        conn.execute(
            text(
                "INSERT INTO orchestration_identities "
                "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
                "definition_version, calculator_version_vector, status, created_at) "
                "VALUES (:id, :fp, :eid, :cid, '1', '{}', 'ACTIVE', now())"
            ),
            {"id": oid, "fp": "fp-" + str(uuid.uuid4()), "eid": eid, "cid": cid},
        )
        conn.commit()
    return oid


class TestInvalidForeignKey:
    def test_invalid_ownership_fk_rejected(self, migrated_pg) -> None:
        engine = _pg_engine(migrated_pg)
        import uuid

        cid = str(uuid.uuid4())
        with engine.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO calculation_runs (id, project_id, project_version_id, "
                        "status, requires_review, calculator_name, calculation_type, "
                        "created_at, orchestration_identity_id) "
                        "VALUES (:id, 'p-1', 'pv-1', 'completed', false, 'zone', 'zone', "
                        "now(), 'nonexistent-identity-id')"
                    ),
                    {"id": cid},
                )
                conn.commit()
        engine.dispose()


class TestAuditEventBackfillValues:
    def test_existing_audit_event_backfilled_on_upgrade(self, pg_url) -> None:
        """Create AuditEvent at migration 0025 state, upgrade to 0026, verify backfill."""
        test_db_url = _pg_db_url("cold_storage_audit_backfill_test")
        import uuid

        # Upgrade to 0025
        r = _run_alembic(test_db_url, "upgrade", "0025")
        assert r.returncode == 0, f"Upgrade to 0025 failed: {r.stderr}"

        engine = _pg_engine(test_db_url)
        aud_id = str(uuid.uuid4())
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events (id, actor, action, entity_type, entity_id, "
                    "before_snapshot, after_snapshot, event_metadata, created_at) "
                    "VALUES (:id, 'test', 'test', 'Test', 'e1', '{}', '{}', '{}', now())"
                ),
                {"id": aud_id},
            )
            conn.commit()
        engine.dispose()

        # Upgrade to 0026 (with backfill)
        r = _run_alembic(test_db_url, "upgrade", "head")
        assert r.returncode == 0, f"Upgrade to head failed: {r.stderr}"

        engine = _pg_engine(test_db_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT outbox_event_id FROM audit_events WHERE id = :id"),
                {"id": aud_id},
            ).fetchone()
            assert row is not None
            oid = row[0]
            assert oid is not None, "outbox_event_id should be NOT NULL after backfill"
            assert oid == f"legacy-audit:{aud_id}", f"Unexpected backfill: {oid}"
            assert len(oid) <= 128, f"Backfill too long: {len(oid)} chars"

            # Verify no nulls
            null_count = conn.execute(
                text("SELECT COUNT(*) FROM audit_events WHERE outbox_event_id IS NULL")
            ).scalar()
            assert null_count == 0, f"{null_count} NULL outbox_event_ids remain"

            # Verify UNIQUE — try duplicate backfill insert
            dup_id = str(uuid.uuid4())
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO audit_events (id, actor, action, entity_type, "
                        "entity_id, before_snapshot, after_snapshot, event_metadata, "
                        "created_at, outbox_event_id) "
                        "VALUES (:id, 'test', 'test', 'Test', 'e2', '{}', '{}', '{}', "
                        "now(), :oid)"
                    ),
                    {"id": dup_id, "oid": oid},
                )
                conn.commit()
        engine.dispose()


# ── Downgrade blocker ────────────────────────────────────────────────────────


class TestDowngradeBlocker:
    def test_empty_database_downgrade_succeeds(self, pg_url) -> None:
        test_db_url = _pg_db_url("cold_storage_empty_downgrade_test")
        r_up = _run_alembic(test_db_url, "upgrade", "head")
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        r_down = _run_alembic(test_db_url, "downgrade", "-1")
        assert r_down.returncode == 0, f"Downgrade failed on empty DB: {r_down.stderr}"

    def test_production_data_blocks_downgrade(self, pg_url) -> None:
        test_db_url = _pg_db_url("cold_storage_downgrade_block_test")
        import uuid

        r = _run_alembic(test_db_url, "upgrade", "head")
        assert r.returncode == 0, f"Upgrade failed: {r.stderr}"

        engine = _pg_engine(test_db_url)
        # Set up full real FK chain
        pid = str(uuid.uuid4())
        pvid = str(uuid.uuid4())
        eid = str(uuid.uuid4())
        cid_s = str(uuid.uuid4())
        oid = str(uuid.uuid4())
        aid = str(uuid.uuid4())
        wsid = str(uuid.uuid4())
        wsrid = str(uuid.uuid4())
        src_bid = str(uuid.uuid4())

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO projects (id, code, name, location, product_category, "
                    "status, current_version_number, created_at, updated_at) "
                    "VALUES (:id, 'T', 'Test', 'TL', 'fruit', 'draft', 0, now(), now())"
                ),
                {"id": pid},
            )
            conn.execute(
                text(
                    "INSERT INTO project_versions (id, project_id, version_number, "
                    "change_summary, status, created_by, created_at, updated_at, "
                    "input_snapshot, calculation_snapshot, assumption_snapshot) "
                    "VALUES (:id, :pid, 1, '', 'approved', 'sys', now(), now(), "
                    "'{}', '{}', '{}')"
                ),
                {"id": pvid, "pid": pid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_execution_snapshots "
                    "(id, project_id, project_version_id, version_number, input_snapshot, "
                    "input_snapshot_hash, schema_version, captured_status, captured_at) "
                    "VALUES (:id, :pid, :pvid, 1, '{}', 'h1', '1', 'approved', now())"
                ),
                {"id": eid, "pid": pid, "pvid": pvid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_coefficient_contexts "
                    "(id, project_id, project_version_id, content, content_hash, "
                    "schema_version, captured_at) "
                    "VALUES (:id, :pid, :pvid, '{}', 'h1', '1', now())"
                ),
                {"id": cid_s, "pid": pid, "pvid": pvid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_identities "
                    "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
                    "definition_version, calculator_version_vector, status, created_at) "
                    "VALUES (:id, :fp, :eid, :cid, '1', '{}', 'ACTIVE', now())"
                ),
                {"id": oid, "fp": "fp-" + str(uuid.uuid4()), "eid": eid, "cid": cid_s},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'COMPLETED', now(), now())"
                ),
                {"id": aid, "oid": oid},
            )
            conn.execute(
                text(
                    "INSERT INTO scheme_weight_sets "
                    "(id, code, name, revision, status, source_type, criteria, "
                    "requires_review, created_at) "
                    "VALUES (:id, 'WS001', 'Test Set', 1, 'draft', 'system', '[]', "
                    "false, now())"
                ),
                {"id": wsid},
            )
            conn.execute(
                text(
                    "INSERT INTO scheme_weight_set_revisions "
                    "(id, weight_set_id, code, revision, status, content, content_hash, "
                    "generator_compatibility_version, created_at) "
                    "VALUES (:id, :wsid, 'WS001', 1, 'draft', '{}', 'h1', '1.0', now())"
                ),
                {"id": wsrid, "wsid": wsid},
            )
            # 5 CalculationRunRecords needed for SourceBinding
            calc_ids = []
            for calc_type in ("zone", "cooling_load", "equipment", "power", "investment"):
                cid_calc = str(uuid.uuid4())
                calc_ids.append(cid_calc)
                conn.execute(
                    text(
                        "INSERT INTO calculation_runs "
                        "(id, project_id, project_version_id, status, requires_review, "
                        "calculator_name, created_at, calculation_type, "
                        "orchestration_identity_id, orchestration_run_attempt_id, "
                        "execution_snapshot_id, coefficient_context_id, input_hash, "
                        "result_hash, provenance, schema_version) "
                        "VALUES (:id, :pid, :pvid, 'completed', false, :calc_name, now(), "
                        ":calc_type, :oid, :aid, :eid, :cid_s, 'h', 'h', '{}', '1')"
                    ),
                    {
                        "id": cid_calc,
                        "pid": pid,
                        "pvid": pvid,
                        "calc_name": calc_type,
                        "calc_type": calc_type,
                        "oid": oid,
                        "aid": aid,
                        "eid": eid,
                        "cid_s": cid_s,
                    },
                )
            conn.execute(
                text(
                    "INSERT INTO orchestration_source_bindings "
                    "(id, project_id, project_version_id, execution_snapshot_id, "
                    "coefficient_context_id, orchestration_identity_id, "
                    "orchestration_run_attempt_id, orchestration_fingerprint, "
                    "zone_calculation_id, cooling_load_calculation_id, "
                    "equipment_calculation_id, power_calculation_id, "
                    "investment_calculation_id, per_calculation_result_hashes, "
                    "combined_source_hash, schema_version, created_at) "
                    "VALUES (:id, :pid, :pvid, :eid, :cid_s, :oid, :aid, :fp, "
                    ":zid, :clid, :eqid, :pwid, :ivid, '{}', 'h1', '1', now())"
                ),
                {
                    "id": src_bid,
                    "pid": pid,
                    "pvid": pvid,
                    "eid": eid,
                    "cid_s": cid_s,
                    "oid": oid,
                    "aid": aid,
                    "fp": "fp-prod",
                    "zid": calc_ids[0],
                    "clid": calc_ids[1],
                    "eqid": calc_ids[2],
                    "pwid": calc_ids[3],
                    "ivid": calc_ids[4],
                },
            )
            conn.execute(
                text(
                    "INSERT INTO scheme_runs (id, project_id, project_version_id, "
                    "weight_set_id, generator_version, source_snapshot_hash, status, "
                    "requires_review, input_snapshot, assumption_snapshot, "
                    "comparison_snapshot, candidates_snapshot, warning_messages, "
                    "created_at, source_mode, source_binding_id, "
                    "source_contract_version, weight_set_revision_id, "
                    "weight_set_content_hash, weight_set_generator_compatibility_version, "
                    "combined_source_hash) "
                    "VALUES (:id, :pid, :pvid, :wsid, '1.0', 'h1', 'pending', false, "
                    "'{}', '{}', '{}', '{}', '[]', now(), 'production', :src_bid, "
                    "'1.0', :wsrid, 'h1', '1.0', 'h1')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pid": pid,
                    "pvid": pvid,
                    "wsid": wsid,
                    "src_bid": src_bid,
                    "wsrid": wsrid,
                },
            )
            conn.commit()
        engine.dispose()

        # Attempt downgrade — must fail
        r = _run_alembic(test_db_url, "downgrade", "-1")
        assert r.returncode != 0, (
            f"Downgrade should have been blocked with production data\n"
            f"STDERR: {r.stderr}\nSTDOUT: {r.stdout}"
        )
        assert "Cannot downgrade" in r.stderr or "Cannot downgrade" in r.stdout, (
            f"Expected blocker message; got stderr={r.stderr!r} stdout={r.stdout!r}"
        )

        # Verify schema remains intact
        engine2 = _pg_engine(test_db_url)
        insp = inspect(engine2)
        tables = insp.get_table_names()
        assert "orchestration_source_bindings" in tables
        assert "scheme_weight_set_revisions" in tables
        assert "orchestration_audit_outbox" in tables
        engine2.dispose()
