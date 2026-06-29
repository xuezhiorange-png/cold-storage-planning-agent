"""PostgreSQL migration integration tests — schema contracts via real Alembic upgrades.

Verifies on PostgreSQL: CHECK constraints, FK names, index names, partial unique index,
outbox status CHECK, AuditEvent backfill, weight_set_revision FK, downgrade blocker,
and atomicity guarantees.

Database lifecycle:
- ``pg_admin_url`` session fixture: connection to `postgres` admin database (AUTOCOMMIT).
- ``pg_database_factory`` fixture: creates unique test databases, drops them in teardown.
- ``migrated_pg`` fixture: isolated database with full head schema (non-destructive).
- Destructive tests (downgrade, backfill, version migration): each uses its own DB.

Tagged with ``@pytest.mark.postgresql`` to run in CI (``-m postgresql``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid as _uuid_mod
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.postgresql

# ── Helpers ──────────────────────────────────────────────────────────────────


def _pg_engine(database_url: str):
    """Create a SQLAlchemy engine for *database_url*."""
    return create_engine(database_url, poolclass=NullPool)


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


@pytest.fixture()
def migrated_pg(pg_database: str) -> str:
    """Alias for conftest ``pg_database`` to minimise test-method churn."""
    return pg_database


class TestAllTables:
    def test_eight_new_tables_exist(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        engine.dispose()
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
    def test_calculation_run_check_exists(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("calculation_runs")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_calculation_run_orchestration_nullity" in names

    def test_scheme_run_check_exists(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("scheme_runs")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_scheme_run_source_mode_nullity" in names

    def test_request_check_exists(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("orchestration_requests")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_orch_request_status_nullity" in names

    def test_outbox_status_check_exists(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        constraints = insp.get_check_constraints("orchestration_audit_outbox")
        names = {c["name"] for c in constraints}
        engine.dispose()
        assert "ck_outbox_status_nullity" in names


class TestForeignKeys:
    def test_calculation_run_orch_fks(self, migrated_pg: str) -> None:
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

    def test_weight_set_revision_fk_exists(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        fks = insp.get_foreign_keys("scheme_weight_set_revisions")
        targets = {(fk["referred_table"], fk["constrained_columns"][0]) for fk in fks}
        engine.dispose()
        assert ("scheme_weight_sets", "weight_set_id") in targets

    def test_source_binding_slot_fks_exist(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        fks = insp.get_foreign_keys("orchestration_source_bindings")
        targets = {(fk["referred_table"], fk["constrained_columns"][0]) for fk in fks}
        engine.dispose()
        for slot in ("zone", "cooling_load", "equipment", "power", "investment"):
            col = f"{slot}_calculation_id"
            assert ("calculation_runs", col) in targets, f"Missing FK: calculation_runs.{col}"


class TestIndexes:
    def test_one_running_partial_unique_index(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        idxs = insp.get_indexes("orchestration_run_attempts")
        names = {idx["name"] for idx in idxs}
        engine.dispose()
        assert "uq_attempt_one_running" in names

    def test_source_binding_slot_indexes(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        idxs = insp.get_indexes("orchestration_source_bindings")
        names = {idx["name"] for idx in idxs}
        engine.dispose()
        for slot in ("zone", "cooling_load", "equipment", "power", "investment"):
            assert f"ix_source_binding_{slot}_calculation_id" in names

    def test_weight_set_revision_unique_constraint(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        uqs = insp.get_unique_constraints("scheme_weight_set_revisions")
        names = {c["name"] for c in uqs if c.get("name")}
        engine.dispose()
        assert "uq_scheme_weight_set_revision_code_revision" in names


# ── AuditEvent Schema Checks ─────────────────────────────────────────────────


class TestAuditEventSchema:
    def test_outbox_event_id_not_null(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        cols = insp.get_columns("audit_events")
        outbox = [c for c in cols if c["name"] == "outbox_event_id"]
        engine.dispose()
        assert len(outbox) == 1
        assert outbox[0]["nullable"] is False

    def test_outbox_event_id_unique(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        insp = inspect(engine)
        uqs = insp.get_unique_constraints("audit_events")
        names = {c["name"] for c in uqs if c.get("name")}
        engine.dispose()
        assert "uq_audit_event_outbox" in names


# ── Database rejection tests (real INSERT) ───────────────────────────────────


class TestCalculationRunRejection:
    def test_partial_orchestration_fields_rejected(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        cid = str(_uuid_mod.uuid4())
        with engine.connect() as conn, pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO calculation_runs (id, project_id, "
                    "project_version_id, calculator_name, calculator_version, "
                    "input_snapshot, result_snapshot, formulas, coefficients, "
                    "assumptions, warnings, source_references, requires_review, "
                    "created_at, calculation_type, orchestration_identity_id) "
                    "VALUES (:id, 'p-1', 'pv-1', 'zone', '1.0', '{}', '{}', "
                    "'[]', '[]', '[]', '[]', '[]', false, now(), 'zone', :oid)"
                ),
                {"id": cid, "oid": str(_uuid_mod.uuid4())},
            )
            conn.commit()
        engine.dispose()


class TestSchemeRunRejection:
    def test_production_missing_combined_source_hash_rejected(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        sid = str(_uuid_mod.uuid4())
        with engine.connect() as conn, pytest.raises(IntegrityError):
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
    def test_accepted_missing_resolved_attempt_rejected(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        rid = str(_uuid_mod.uuid4())
        with engine.connect() as conn, pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO orchestration_requests (id, requested_project_id, "
                    "requested_project_version_id, request_fingerprint, actor, "
                    "correlation_id, status, resolved_project_id, "
                    "resolved_project_version_id, resolved_identity_id, created_at) "
                    "VALUES (:id, 'p-1', 'pv-1', 'fp', 'me', 'cid', "
                    "'ACCEPTED', 'p-1', 'pv-1', 'oi-1', now())"
                ),
                {"id": rid},
            )
            conn.commit()
        engine.dispose()


class TestInvalidForeignKey:
    def test_invalid_ownership_fk_rejected(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        cid = str(_uuid_mod.uuid4())
        with engine.connect() as conn, pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO calculation_runs (id, project_id, project_version_id, "
                    "calculator_name, calculator_version, input_snapshot, result_snapshot, "
                    "formulas, coefficients, assumptions, warnings, source_references, "
                    "requires_review, created_at, calculation_type, "
                    "orchestration_identity_id) "
                    "VALUES (:id, 'p-1', 'pv-1', 'zone', '1.0', '{}', '{}', "
                    "'[]', '[]', '[]', '[]', '[]', false, now(), 'zone', "
                    "'nonexistent-identity-id')"
                ),
                {"id": cid},
            )
            conn.commit()
        engine.dispose()


# ── One-RUNNING partial unique index tests ───────────────────────────────────


class TestOneRunning:
    # ── Helper for identity setup ─────────────────────────────────────

    @staticmethod
    def _setup_identity(conn, pid: str, pvid: str) -> str:
        """Insert snapshot, context, identity; return identity_id."""
        eid = str(_uuid_mod.uuid4())
        cid = str(_uuid_mod.uuid4())
        oid = str(_uuid_mod.uuid4())
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
        return oid

    def test_two_running_same_identity_rejected(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        pid = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())
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
            oid = self._setup_identity(conn, pid, pvid)
            conn.commit()

        with engine.connect() as conn:
            a1 = str(_uuid_mod.uuid4())
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'RUNNING', now(), now())"
                ),
                {"id": a1, "oid": oid},
            )
            conn.commit()

            a2 = str(_uuid_mod.uuid4())
            with pytest.raises(IntegrityError):
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

    def test_failed_plus_running_accepted(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        pid = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())
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
            oid = self._setup_identity(conn, pid, pvid)
            conn.commit()

        with engine.connect() as conn:
            a1 = str(_uuid_mod.uuid4())
            a2 = str(_uuid_mod.uuid4())
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'FAILED', now(), now())"
                ),
                {"id": a1, "oid": oid},
            )
            conn.commit()
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

    def test_completed_plus_running_accepted(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        pid = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())
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
            oid = self._setup_identity(conn, pid, pvid)
            conn.commit()

        with engine.connect() as conn:
            a1 = str(_uuid_mod.uuid4())
            a2 = str(_uuid_mod.uuid4())
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'COMPLETED', now(), now())"
                ),
                {"id": a1, "oid": oid},
            )
            conn.commit()
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


# ── AuditEvent backfill tests ────────────────────────────────────────────────


class TestAuditEventHistoryBackfill:
    """Test A: Historical AuditEvent rows are backfilled during 0025→0026 upgrade."""

    def test_history_row_backfilled_on_upgrade(self, pg_database_factory) -> None:
        db_url = pg_database_factory(prefix="audit_backfill")

        # Step 1: upgrade to 0025 (before outbox_event_id exists)
        r = _run_alembic(db_url, "upgrade", "0025")
        assert r.returncode == 0, f"Upgrade to 0025 failed: {r.stderr}"

        engine = _pg_engine(db_url)
        aud_id = str(_uuid_mod.uuid4())
        original_actor = "test_actor"
        original_action = "test_action"
        original_entity_type = "TestEntity"
        original_entity_id = "e1"

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events (id, actor, action, entity_type, entity_id, "
                    "before_snapshot, after_snapshot, event_metadata, created_at) "
                    "VALUES (:id, :actor, :action, :etype, :eid, '{}', '{}', '{}', now())"
                ),
                {
                    "id": aud_id,
                    "actor": original_actor,
                    "action": original_action,
                    "etype": original_entity_type,
                    "eid": original_entity_id,
                },
            )
            conn.commit()
        engine.dispose()

        # Step 2: upgrade to 0026 — migration should backfill existing rows
        r = _run_alembic(db_url, "upgrade", "head")
        assert r.returncode == 0, f"Upgrade to head failed: {r.stderr}"

        # Step 3: verify backfill
        engine = _pg_engine(db_url)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT outbox_event_id, actor, action, entity_type, entity_id "
                    "FROM audit_events WHERE id = :id"
                ),
                {"id": aud_id},
            ).fetchone()
            assert row is not None, "Historical AuditEvent row missing after upgrade"
            oid = row[0]
            assert oid == f"legacy-audit:{aud_id}", f"Backfill mismatch: {oid}"
            assert len(oid) > 36, f"Backfill too short: {oid!r}"
            assert len(oid) <= 128, f"Backfill too long: {len(oid)}"
            assert oid.startswith("legacy-audit:")

            # Original fields preserved
            assert row[1] == original_actor
            assert row[2] == original_action
            assert row[3] == original_entity_type
            assert row[4] == original_entity_id

            # Verify no nulls after upgrade
            null_count = conn.execute(
                text("SELECT COUNT(*) FROM audit_events WHERE outbox_event_id IS NULL")
            ).scalar()
            assert null_count == 0, f"{null_count} NULL outbox_event_ids remain"

            # UNIQUE enforcement: duplicate backfill value rejected
            dup_id = str(_uuid_mod.uuid4())
            with pytest.raises(IntegrityError):
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
            # Must rollback after IntegrityError; transaction is aborted
            conn.rollback()

            # Verify no duplicates exist
            dup_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ("
                    "  SELECT outbox_event_id, COUNT(*) as cnt"
                    "  FROM audit_events"
                    "  GROUP BY outbox_event_id"
                    "  HAVING COUNT(*) > 1"
                    ") sub"
                )
            ).scalar()
            assert dup_count == 0, "Duplicate outbox_event_id values found"
        engine.dispose()

        # Verify repeated upgrade is idempotent
        r2 = _run_alembic(db_url, "upgrade", "head")
        assert r2.returncode == 0, f"Re-upgrade failed: {r2.stderr}"

        engine3 = _pg_engine(db_url)
        with engine3.connect() as conn3:
            # Revision matches current head after re-upgrade
            rev = conn3.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == "0027_separate_requested_and_resolved_request_identity", (
                f"Revision changed: {rev}"
            )

            # AuditEvent still backfilled with same value
            row2 = conn3.execute(
                text(
                    "SELECT outbox_event_id, actor, action, entity_type, entity_id "
                    "FROM audit_events WHERE id = :id"
                ),
                {"id": aud_id},
            ).fetchone()
            assert row2 is not None
            assert row2[0] == f"legacy-audit:{aud_id}"
            assert row2[1] == original_actor
            assert row2[2] == original_action
            assert row2[3] == original_entity_type
            assert row2[4] == original_entity_id
        engine3.dispose()


class TestAuditEventPostMigration:
    """Test B: After 0026, new AuditEvent without outbox_event_id is rejected."""

    def test_missing_outbox_event_id_rejected(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        aud_id = str(_uuid_mod.uuid4())
        with engine.connect() as conn, pytest.raises(IntegrityError):
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


class TestAuditEventExplicitId:
    """Test C: Explicit outbox_event_id insertion succeeds; duplicate rejected."""

    def test_explicit_unique_id_succeeds(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        aud_id = str(_uuid_mod.uuid4())
        oid = str(_uuid_mod.uuid4())
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events (id, actor, action, entity_type, entity_id, "
                    "before_snapshot, after_snapshot, event_metadata, created_at, "
                    "outbox_event_id) "
                    "VALUES (:id, 'test', 'test', 'Test', 'e1', '{}', '{}', '{}', "
                    "now(), :oid)"
                ),
                {"id": aud_id, "oid": oid},
            )
            conn.commit()

            row = conn.execute(
                text("SELECT outbox_event_id FROM audit_events WHERE id = :id"),
                {"id": aud_id},
            ).fetchone()
            assert row is not None
            assert row[0] == oid
        engine.dispose()

    def test_duplicate_outbox_event_id_rejected(self, migrated_pg: str) -> None:
        engine = _pg_engine(migrated_pg)
        oid = str(_uuid_mod.uuid4())
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events (id, actor, action, entity_type, entity_id, "
                    "before_snapshot, after_snapshot, event_metadata, created_at, "
                    "outbox_event_id) "
                    "VALUES (:id, 'test', 'test', 'Test', 'e1', '{}', '{}', '{}', "
                    "now(), :oid)"
                ),
                {"id": str(_uuid_mod.uuid4()), "oid": oid},
            )
            conn.commit()

            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO audit_events (id, actor, action, entity_type, entity_id, "
                        "before_snapshot, after_snapshot, event_metadata, created_at, "
                        "outbox_event_id) "
                        "VALUES (:id, 'test2', 'test2', 'Test2', 'e2', '{}', '{}', '{}', "
                        "now(), :oid)"
                    ),
                    {"id": str(_uuid_mod.uuid4()), "oid": oid},
                )
                conn.commit()
        engine.dispose()


# ── Downgrade blocker tests ──────────────────────────────────────────────────


class TestDowngradeBlocker:
    def test_empty_database_downgrade_succeeds(self, pg_database_factory) -> None:
        db_url = pg_database_factory(prefix="downgrade_empty")
        r_up = _run_alembic(db_url, "upgrade", "head")
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        r = _run_alembic(db_url, "downgrade", "0025")
        assert r.returncode == 0, (
            f"Downgrade should succeed on empty DB\nSTDERR: {r.stderr}\nSTDOUT: {r.stdout}"
        )

        # Verify revision rolled back
        engine = _pg_engine(db_url)
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == "0025_add_outbox_claim_fields", f"Expected 0025, got {rev}"
        engine.dispose()

    def test_legacy_only_downgrade_succeeds(self, pg_database_factory) -> None:
        """Downgrade succeeds when only legacy SchemeRuns exist (no SourceBinding)."""
        db_url = pg_database_factory(prefix="downgrade_legacy")
        r_up = _run_alembic(db_url, "upgrade", "head")
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        engine = _pg_engine(db_url)
        pid = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())
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
                    "INSERT INTO scheme_runs (id, project_id, project_version_id, "
                    "weight_set_id, generator_version, source_snapshot_hash, status, "
                    "requires_review, input_snapshot, assumption_snapshot, "
                    "comparison_snapshot, candidates_snapshot, warning_messages, "
                    "created_at, source_mode) "
                    "VALUES (:id, :pid, :pvid, 'ws-1', '1.0', 'h1', 'pending', "
                    "false, '{}', '{}', '{}', '{}', '[]', now(), 'legacy')"
                ),
                {"id": str(_uuid_mod.uuid4()), "pid": pid, "pvid": pvid},
            )
            conn.commit()
        engine.dispose()

        r = _run_alembic(db_url, "downgrade", "0025")
        assert r.returncode == 0, (
            f"Downgrade should succeed with legacy-only data\n"
            f"STDERR: {r.stderr}\nSTDOUT: {r.stdout}"
        )

    def test_source_binding_blocks_downgrade(self, pg_database_factory) -> None:
        """Downgrade blocked when any SourceBinding exists (even without production SchemeRun)."""
        db_url = pg_database_factory(prefix="downgrade_sb_only")
        r_up = _run_alembic(db_url, "upgrade", "head")
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        engine = _pg_engine(db_url)
        pid = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())
        eid = str(_uuid_mod.uuid4())
        cid_ctx = str(_uuid_mod.uuid4())
        oid = str(_uuid_mod.uuid4())
        aid = str(_uuid_mod.uuid4())
        calc_ids = [str(_uuid_mod.uuid4()) for _ in range(5)]
        src_bid = str(_uuid_mod.uuid4())

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
                {"id": cid_ctx, "pid": pid, "pvid": pvid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_identities "
                    "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
                    "definition_version, calculator_version_vector, status, created_at) "
                    "VALUES (:id, 'fp', :eid, :cid, '1', '{}', 'ACTIVE', now())"
                ),
                {"id": oid, "eid": eid, "cid": cid_ctx},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, heartbeat_at, started_at) "
                    "VALUES (:id, :oid, 1, 'COMPLETED', now(), now())"
                ),
                {"id": aid, "oid": oid},
            )
            calc_types = ("zone", "cooling_load", "equipment", "power", "investment")
            calc_names = ("z", "cl", "eq", "pw", "inv")
            for cid_c, ctype, cname in zip(calc_ids, calc_types, calc_names, strict=True):
                conn.execute(
                    text(
                        "INSERT INTO calculation_runs "
                        "(id, project_id, project_version_id, calculator_name, "
                        "calculator_version, input_snapshot, result_snapshot, formulas, "
                        "coefficients, assumptions, warnings, source_references, "
                        "requires_review, created_at, calculation_type, "
                        "orchestration_identity_id, orchestration_run_attempt_id, "
                        "execution_snapshot_id, coefficient_context_id, input_hash, "
                        "result_hash, provenance, schema_version) "
                        "VALUES (:id, :pid, :pvid, :cn, '1.0', '{}', '{}', '[]', "
                        "'[]', '[]', '[]', '[]', false, now(), :ct, :oid, :aid, :eid, "
                        ":cid, 'h1', 'h1', '{}', '1')"
                    ),
                    {
                        "id": cid_c,
                        "pid": pid,
                        "pvid": pvid,
                        "cn": cname,
                        "ct": ctype,
                        "oid": oid,
                        "aid": aid,
                        "eid": eid,
                        "cid": cid_ctx,
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
                    "VALUES (:id, :pid, :pvid, :eid, :cid_ctx, :oid, :aid, 'fp', "
                    ":zid, :clid, :eqid, :pwid, :ivid, '{}', 'h1', '1', now())"
                ),
                {
                    "id": src_bid,
                    "pid": pid,
                    "pvid": pvid,
                    "eid": eid,
                    "cid_ctx": cid_ctx,
                    "oid": oid,
                    "aid": aid,
                    "zid": calc_ids[0],
                    "clid": calc_ids[1],
                    "eqid": calc_ids[2],
                    "pwid": calc_ids[3],
                    "ivid": calc_ids[4],
                },
            )
            conn.commit()
        engine.dispose()

        r = _run_alembic(db_url, "downgrade", "0025")
        assert r.returncode != 0, (
            f"Downgrade should be blocked when SourceBinding exists\n"
            f"STDERR: {r.stderr}\nSTDOUT: {r.stdout}"
        )
        assert "Cannot downgrade" in r.stderr or "Cannot downgrade" in r.stdout, (
            f"Expected blocker message; got stderr={r.stderr!r}"
        )

    def test_production_data_blocks_downgrade_and_atomic(self, pg_database_factory) -> None:
        """Full production FK chain blocks downgrade; schema remains intact."""
        db_url = pg_database_factory(prefix="downgrade_full")
        r_up = _run_alembic(db_url, "upgrade", "head")
        assert r_up.returncode == 0, f"Upgrade failed: {r_up.stderr}"

        engine = _pg_engine(db_url)
        pid = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())
        eid = str(_uuid_mod.uuid4())
        cid_ctx = str(_uuid_mod.uuid4())
        oid = str(_uuid_mod.uuid4())
        aid = str(_uuid_mod.uuid4())
        wsid = str(_uuid_mod.uuid4())
        wsrid = str(_uuid_mod.uuid4())
        src_bid = str(_uuid_mod.uuid4())
        srid = str(_uuid_mod.uuid4())

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
                {"id": cid_ctx, "pid": pid, "pvid": pvid},
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_identities "
                    "(id, fingerprint, execution_snapshot_id, coefficient_context_id, "
                    "definition_version, calculator_version_vector, status, created_at) "
                    "VALUES (:id, :fp, :eid, :cid, '1', '{}', 'ACTIVE', now())"
                ),
                {"id": oid, "fp": "fp-" + str(_uuid_mod.uuid4()), "eid": eid, "cid": cid_ctx},
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
            calc_ids = []
            calc_types = ("zone", "cooling_load", "equipment", "power", "investment")
            for ct in calc_types:
                cid_c = str(_uuid_mod.uuid4())
                calc_ids.append(cid_c)
                conn.execute(
                    text(
                        "INSERT INTO calculation_runs "
                        "(id, project_id, project_version_id, calculator_name, "
                        "calculator_version, input_snapshot, result_snapshot, formulas, "
                        "coefficients, assumptions, warnings, source_references, "
                        "requires_review, created_at, calculation_type, "
                        "orchestration_identity_id, orchestration_run_attempt_id, "
                        "execution_snapshot_id, coefficient_context_id, input_hash, "
                        "result_hash, provenance, schema_version) "
                        "VALUES (:id, :pid, :pvid, :cn, '1.0', '{}', '{}', '[]', "
                        "'[]', '[]', '[]', '[]', false, now(), :ct, :oid, :aid, :eid, "
                        ":cid, 'h1', 'h1', '{}', '1')"
                    ),
                    {
                        "id": cid_c,
                        "pid": pid,
                        "pvid": pvid,
                        "cn": ct,
                        "ct": ct,
                        "oid": oid,
                        "aid": aid,
                        "eid": eid,
                        "cid": cid_ctx,
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
                    "VALUES (:id, :pid, :pvid, :eid, :cid_ctx, :oid, :aid, :fp, "
                    ":zid, :clid, :eqid, :pwid, :ivid, '{}', 'h1', '1', now())"
                ),
                {
                    "id": src_bid,
                    "pid": pid,
                    "pvid": pvid,
                    "eid": eid,
                    "cid_ctx": cid_ctx,
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
                    "id": srid,
                    "pid": pid,
                    "pvid": pvid,
                    "wsid": wsid,
                    "src_bid": src_bid,
                    "wsrid": wsrid,
                },
            )
            conn.commit()

            # Capture pre-downgrade state
            rev_before = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            combined_hash_before = conn.execute(
                text("SELECT combined_source_hash FROM scheme_runs WHERE id = :id"),
                {"id": srid},
            ).scalar()
        engine.dispose()

        # Attempt downgrade — must be blocked
        r = _run_alembic(db_url, "downgrade", "0025")
        assert r.returncode != 0, (
            f"Downgrade should have been blocked with production data\n"
            f"STDERR: {r.stderr}\nSTDOUT: {r.stdout}"
        )
        assert "Cannot downgrade" in r.stderr or "Cannot downgrade" in r.stdout, (
            f"Expected blocker message; got stderr={r.stderr!r} stdout={r.stdout!r}"
        )

        # ── Verify atomicity: nothing changed ───────────────────────────
        engine2 = _pg_engine(db_url)
        with engine2.connect() as conn:
            rev_after = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
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
                row = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT FROM information_schema.tables "
                        "WHERE table_name = :tbl)"
                    ),
                    {"tbl": tbl},
                ).scalar()
                assert row, f"Table {tbl} missing after blocked downgrade"

            # Production rows still exist
            scheme_cnt = conn.execute(
                text("SELECT COUNT(*) FROM scheme_runs WHERE id = :id"),
                {"id": srid},
            ).scalar()
            assert scheme_cnt == 1, "SchemeRun missing after blocked downgrade"

            sb_cnt = conn.execute(
                text("SELECT COUNT(*) FROM orchestration_source_bindings WHERE id = :id"),
                {"id": src_bid},
            ).scalar()
            assert sb_cnt == 1, "SourceBinding missing after blocked downgrade"

            # Hash unchanged
            combined_hash_after = conn.execute(
                text("SELECT combined_source_hash FROM scheme_runs WHERE id = :id"),
                {"id": srid},
            ).scalar()
            assert combined_hash_after == combined_hash_before, (
                f"combined_source_hash changed: {combined_hash_before} → {combined_hash_after}"
            )

            # FKs still present on calculation_runs
            fk_result = conn.execute(
                text("SELECT 1 FROM pg_constraint WHERE conname = 'fk_calc_run_orch_identity'")
            ).scalar()
            assert fk_result == 1, "FK fk_calc_run_orch_identity missing"


# ── Downgrade Gate Tests ─────────────────────────────────────────────────


class TestDowngradeGatePG:
    """P0-4/P0-8: PostgreSQL downgrade blocker — mirrors SQLite tests."""

    def test_blocked_with_unresolvable_requested_project(self, pg_database_factory) -> None:
        """Downgrade blocked when PREFLIGHT_REJECTED record has unresolvable
        requested_project_id."""
        db_url = pg_database_factory(prefix="dg_proj")
        r = _run_alembic(db_url, "upgrade", "head")
        assert r.returncode == 0, f"Upgrade failed: {r.stderr}"

        engine = _pg_engine(db_url)
        with engine.connect() as conn:
            rev_before = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            conn.execute(
                text(
                    "INSERT INTO orchestration_requests "
                    "(id, requested_project_id, requested_project_version_id, "
                    "request_fingerprint, actor, correlation_id, status, "
                    "failure_code, failure_field, failure_details, completed_at, "
                    "created_at) "
                    "VALUES (:id, :rpid, :rpvid, 'fp', 'test', 'corr', "
                    "'PREFLIGHT_REJECTED', 'ERR', 'field', '{}', now(), now())"
                ),
                {
                    "id": str(_uuid_mod.uuid4()),
                    "rpid": "nonexistent-project-id",
                    "rpvid": "nonexistent-version-id",
                },
            )
            conn.commit()

        # Attempt downgrade — must be blocked
        r = _run_alembic(db_url, "downgrade", "-1")
        assert r.returncode != 0, (
            f"Downgrade should have been blocked\\nstdout: {r.stdout}\\nstderr: {r.stderr}"
        )
        assert "Cannot downgrade" in (r.stderr + r.stdout), (
            f"Expected blocker message; got stderr={r.stderr!r}"
        )

        # Verify atomicity: nothing changed
        with engine.connect() as conn:
            rev_after = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev_after == rev_before, f"Revision changed from {rev_before} to {rev_after}"
            # CHECK constraint still present
            ck = conn.execute(
                text("SELECT 1 FROM pg_constraint WHERE conname = 'ck_orch_request_status_nullity'")
            ).scalar()
            assert ck == 1, "CHECK ck_orch_request_status_nullity missing"
            # Table still exists
            tbl = conn.execute(
                text("SELECT 1 FROM pg_tables WHERE tablename = 'orchestration_requests'")
            ).scalar()
            assert tbl == 1, "orchestration_requests table missing"
        engine.dispose()

    def test_blocked_with_valid_project_invalid_version(self, pg_database_factory) -> None:
        """Downgrade blocked when requested_project exists but
        requested_version does not."""
        db_url = pg_database_factory(prefix="dg_ver")
        r = _run_alembic(db_url, "upgrade", "head")
        assert r.returncode == 0

        pid = str(_uuid_mod.uuid4())
        engine = _pg_engine(db_url)
        with engine.connect() as conn:
            # Create a valid project
            conn.execute(
                text(
                    "INSERT INTO projects (id, code, name, location, "
                    "product_category, status, current_version_number, "
                    "created_at, updated_at) "
                    "VALUES (:id, 'T1', 'Test', 'TL', 'fruit', 'draft', 0, "
                    "now(), now())"
                ),
                {"id": pid},
            )
            conn.commit()

            rev_before = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

            # Insert request with valid project but invalid version
            conn.execute(
                text(
                    "INSERT INTO orchestration_requests "
                    "(id, requested_project_id, requested_project_version_id, "
                    "request_fingerprint, actor, correlation_id, status, "
                    "failure_code, failure_field, failure_details, completed_at, "
                    "created_at) "
                    "VALUES (:id, :rpid, :rpvid, 'fp', 'test', 'corr', "
                    "'PREFLIGHT_REJECTED', 'ERR', 'field', '{}', now(), now())"
                ),
                {
                    "id": str(_uuid_mod.uuid4()),
                    "rpid": pid,
                    "rpvid": "nonexistent-version-id",
                },
            )
            conn.commit()

        r = _run_alembic(db_url, "downgrade", "-1")
        assert r.returncode != 0, f"Downgrade should be blocked when version invalid\\n{r.stderr}"

        with engine.connect() as conn:
            rev_after = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev_after == rev_before
        engine.dispose()

    def test_blocked_with_version_project_mismatch(self, pg_database_factory) -> None:
        """Downgrade blocked when requested version exists but belongs to
        a different project."""
        db_url = pg_database_factory(prefix="dg_mis")
        r = _run_alembic(db_url, "upgrade", "head")
        assert r.returncode == 0

        pid_a = str(_uuid_mod.uuid4())
        pid_b = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())

        engine = _pg_engine(db_url)
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO projects (id, code, name, location, "
                    "product_category, status, current_version_number, "
                    "created_at, updated_at) "
                    "VALUES (:id, :code, 'Test', 'TL', 'fruit', 'draft', 0, "
                    "now(), now())"
                ),
                {"id": pid_a, "code": "TA"},
            )
            conn.execute(
                text(
                    "INSERT INTO projects (id, code, name, location, "
                    "product_category, status, current_version_number, "
                    "created_at, updated_at) "
                    "VALUES (:id, :code, 'Test', 'TL', 'fruit', 'draft', 0, "
                    "now(), now())"
                ),
                {"id": pid_b, "code": "TB"},
            )
            # Version belongs to pid_b, not pid_a
            conn.execute(
                text(
                    "INSERT INTO project_versions "
                    "(id, project_id, version_number, change_summary, status, "
                    "created_by, created_at, updated_at, input_snapshot) "
                    "VALUES (:id, :pid, 1, '', 'approved', 'sys', "
                    "now(), now(), '{}')"
                ),
                {"id": pvid, "pid": pid_b},
            )
            conn.commit()

            rev_before = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

            # Request references pid_a (valid project) + pvid (belongs to pid_b)
            conn.execute(
                text(
                    "INSERT INTO orchestration_requests "
                    "(id, requested_project_id, requested_project_version_id, "
                    "request_fingerprint, actor, correlation_id, status, "
                    "failure_code, failure_field, failure_details, completed_at, "
                    "created_at) "
                    "VALUES (:id, :rpid, :rpvid, 'fp', 'test', 'corr', "
                    "'PREFLIGHT_REJECTED', 'ERR', 'field', '{}', now(), now())"
                ),
                {
                    "id": str(_uuid_mod.uuid4()),
                    "rpid": pid_a,
                    "rpvid": pvid,
                },
            )
            conn.commit()

        r = _run_alembic(db_url, "downgrade", "-1")
        assert r.returncode != 0, (
            f"Downgrade should be blocked on project/version mismatch\\n{r.stderr}"
        )

        with engine.connect() as conn:
            rev_after = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev_after == rev_before
        engine.dispose()

    def test_all_resolvable_allows_downgrade(self, pg_database_factory) -> None:
        """Downgrade succeeds when all requested identities are resolvable."""
        db_url = pg_database_factory(prefix="dg_ok")
        r = _run_alembic(db_url, "upgrade", "head")
        assert r.returncode == 0

        pid = str(_uuid_mod.uuid4())
        pvid = str(_uuid_mod.uuid4())

        engine = _pg_engine(db_url)
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO projects (id, code, name, location, "
                    "product_category, status, current_version_number, "
                    "created_at, updated_at) "
                    "VALUES (:id, 'T_OK', 'Test', 'TL', 'fruit', 'draft', 0, "
                    "now(), now())"
                ),
                {"id": pid},
            )
            conn.execute(
                text(
                    "INSERT INTO project_versions "
                    "(id, project_id, version_number, change_summary, status, "
                    "created_by, created_at, updated_at, input_snapshot) "
                    "VALUES (:id, :pid, 1, '', 'approved', 'sys', "
                    "now(), now(), '{}')"
                ),
                {"id": pvid, "pid": pid},
            )
            # Resolvable request
            conn.execute(
                text(
                    "INSERT INTO orchestration_requests "
                    "(id, requested_project_id, requested_project_version_id, "
                    "request_fingerprint, actor, correlation_id, status, "
                    "failure_code, failure_field, failure_details, completed_at, "
                    "created_at) "
                    "VALUES (:id, :rpid, :rpvid, 'fp', 'test', 'corr', "
                    "'PREFLIGHT_REJECTED', 'ERR', 'field', '{}', now(), now())"
                ),
                {
                    "id": str(_uuid_mod.uuid4()),
                    "rpid": pid,
                    "rpvid": pvid,
                },
            )
            conn.commit()

        r = _run_alembic(db_url, "downgrade", "-1")
        assert r.returncode == 0, f"Downgrade should succeed with resolvable data\\n{r.stderr}"

        # Verify we're on revision 0026
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == "0026_add_orchestration_persistence", f"Expected revision 0026, got {rev}"
        engine.dispose()
