"""0035 Phase 1 — ORM-level SQLite roundtrip using raw SQL to
construct FK chains.

Phase 1 is **schema-only** — it adds identity foundation columns
and ORM mapping for these columns. Phase 2 will add the
orchestrator business logic.

To verify Phase 1's contract holds end-to-end at the SQL layer,
this test file uses raw SQL to build the FK chain (project +
project_version + execution_snapshot + coefficient_context +
orchestration_identity), then issues one INSERT into
``orchestration_run_attempts`` via SQLAlchemy ORM to confirm
that the Phase 1 columns and their constraints are enforced.

Phase 1 contract: see design doc
docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md
(Frozen Contract Authority SHA: ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run_alembic(args, db_path, *, timeout=60):
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


@pytest.fixture()
def engine():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    try:
        r = _run_alembic(["upgrade", "head"], tmp.name)
        assert r.returncode == 0, f"alembic upgrade head failed:\n{r.stderr}\n{r.stdout}"
        e = create_engine(f"sqlite:///{tmp.name}")
        yield e
        e.dispose()
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def _seed_chain(engine):
    """Seed the minimal FK chain via raw SQL. Returns identity_id."""
    project_id = str(uuid.uuid4())
    project_version_id = str(uuid.uuid4())
    snapshot_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())
    identity_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    with engine.connect() as c:
        # projects — all NOT NULL columns including code, name, location,
        # product_category, current_version_number, created_at, updated_at
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
                "loc": "test-location",
                "pcat": "test-product",
                "now": now,
            },
        )
        # project_versions (0001 + 0003 statuses are lowercase per CHECK)
        c.execute(
            text(
                "INSERT INTO project_versions("
                "  id, project_id, version_number, change_summary, status,"
                "  input_snapshot, calculation_snapshot, assumption_snapshot,"
                "  updated_at, created_at, created_by"
                ") VALUES ("
                "  :id, :pid, 1, 'phase1-test', 'approved',"
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
                ") VALUES ("
                "  :id, :pid, :pvid, 1, '{}', 'hsh', 'v1', 'OK', :now"
                ")"
            ),
            {
                "id": snapshot_id,
                "pid": project_id,
                "pvid": project_version_id,
                "now": now,
            },
        )
        c.execute(
            text(
                "INSERT INTO orchestration_coefficient_contexts("
                "  id, project_id, project_version_id, content, content_hash,"
                "  schema_version, captured_at"
                ") VALUES (:id, :pid, :pvid, '{}', 'hsh', 'v1', :now)"
            ),
            {
                "id": context_id,
                "pid": project_id,
                "pvid": project_version_id,
                "now": now,
            },
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


def _seed_chain_for_scheme_run(engine):
    """Seed projects + project_versions only (no orchestration chain)."""
    project_id = str(uuid.uuid4())
    project_version_id = str(uuid.uuid4())
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
                "name": f"p-{project_id[:8]}",
                "loc": "test-location",
                "pcat": "test-product",
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
                "  :id, :pid, 1, 'phase1-test', 'approved',"
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
        c.commit()
    return project_id, project_version_id


class Test0035Phase1RawSQLRoundtrip:
    """End-to-end SQL-layer verification of Phase 1 columns and
    constraints."""

    def test_all_phase1_attempt_columns_roundtrip(self, engine) -> None:
        """Insert an attempt via raw SQL with all 5 Phase 1 columns;
        read back via raw SQL; verify fields persist."""
        identity_id = _seed_chain(engine)
        attempt_id = str(uuid.uuid4())

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts("
                    "  id, identity_id, attempt_number, status, heartbeat_at, started_at,"
                    "  idempotency_key, database_backend, correlation_id,"
                    "  actor_principal_type, scheme_run_id"
                    ") VALUES ("
                    "  :id, :iid, 1, 'RUNNING', :now, :now,"
                    "  :ik, 'postgresql', 'corr-test', 'service', NULL"
                    ")"
                ),
                {
                    "id": attempt_id,
                    "iid": identity_id,
                    "now": datetime.now(UTC).isoformat(),
                    "ik": "idem-raw-1",
                },
            )
            conn.commit()

            row = conn.execute(
                text(
                    "SELECT idempotency_key, database_backend, correlation_id,"
                    "  actor_principal_type, scheme_run_id"
                    "  FROM orchestration_run_attempts WHERE id = :id"
                ),
                {"id": attempt_id},
            ).fetchone()
            assert row is not None
            assert row[0] == "idem-raw-1"
            assert row[1] == "postgresql"
            assert row[2] == "corr-test"
            assert row[3] == "service"
            assert row[4] is None

    def test_database_backend_enum_rejects_invalid_value(self, engine) -> None:
        """database_backend='postgres' is not in the enum → CHECK violation."""
        identity_id = _seed_chain(engine)
        with engine.connect() as conn:
            with pytest.raises(Exception) as exc_info:
                conn.execute(
                    text(
                        "INSERT INTO orchestration_run_attempts("
                        "  id, identity_id, attempt_number, status, heartbeat_at, started_at,"
                        "  database_backend, correlation_id, actor_principal_type"
                        ") VALUES ("
                        "  :id, :iid, 1, 'RUNNING', :now, :now, 'postgres', :cid, 'user'"
                        ")"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "iid": identity_id,
                        "now": datetime.now(UTC).isoformat(),
                        "cid": "phase1-orm-roundtrip-cid-005",
                    },
                )
                conn.commit()
            assert "IntegrityError" in type(exc_info.value).__name__ or "CHECK" in str(
                exc_info.value
            ), f"unexpected exception: {exc_info.value!r}"

    def test_actor_principal_type_enum_rejects_invalid_value(self, engine) -> None:
        """actor_principal_type='admin' is not in the enum."""
        identity_id = _seed_chain(engine)
        with engine.connect() as conn:
            with pytest.raises(Exception) as exc_info:
                conn.execute(
                    text(
                        "INSERT INTO orchestration_run_attempts("
                        "  id, identity_id, attempt_number, status, heartbeat_at, started_at,"
                        "  database_backend, correlation_id, actor_principal_type"
                        ") VALUES ("
                        "  :id, :iid, 1, 'RUNNING', :now, :now, 'sqlite', :cid, 'admin'"
                        ")"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "iid": identity_id,
                        "now": datetime.now(UTC).isoformat(),
                        "cid": "phase1-orm-roundtrip-cid-006",
                    },
                )
                conn.commit()
            assert "IntegrityError" in type(exc_info.value).__name__ or "CHECK" in str(
                exc_info.value
            )

    def test_idempotency_uniqueness_violation(self, engine) -> None:
        """Two attempts with same (database_backend, idempotency_key)
        violate the unique index.
        """
        identity_id = _seed_chain(engine)
        shared = "shared-idem-key"

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts("
                    "  id, identity_id, attempt_number, status, heartbeat_at, started_at,"
                    "  database_backend, correlation_id, idempotency_key, actor_principal_type"
                    ") VALUES ("
                    "  :id, :iid, 1, 'RUNNING', :now, :now, 'sqlite', :cid, :ik, 'user'"
                    ")"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "iid": identity_id,
                    "now": datetime.now(UTC).isoformat(),
                    "cid": "phase1-orm-roundtrip-cid-001",
                    "ik": shared,
                },
            )
            conn.commit()

        with engine.connect() as conn:
            with pytest.raises(Exception) as exc_info:
                conn.execute(
                    text(
                        "INSERT INTO orchestration_run_attempts("
                        "  id, identity_id, attempt_number, status, heartbeat_at, started_at,"
                        "  database_backend, correlation_id, idempotency_key, actor_principal_type"
                        ") VALUES ("
                        "  :id, :iid, 2, 'RUNNING', :now, :now, 'sqlite', :cid, :ik, 'user'"
                        ")"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "iid": identity_id,
                        "now": datetime.now(UTC).isoformat(),
                        "cid": "phase1-orm-roundtrip-cid-002",
                        "ik": shared,
                    },
                )
                conn.commit()
            assert "IntegrityError" in type(exc_info.value).__name__

    def test_idempotency_uniqueness_isolated_per_database_backend(self, engine) -> None:
        """Same idempotency_key with different database_backend values
        does NOT collide. Each attempt is a separate orchestrator
        call on its own identity, so identity_id is per-row.
        """
        shared = "shared-key-across-backends"

        # Two distinct identities (one per attempt) — exactly the
        # production pattern where each orchestrator call materializes
        # its own identity.
        identity_id_1 = _seed_chain(engine)
        identity_id_2 = _seed_chain(engine)

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts("
                    "  id, identity_id, attempt_number, status, heartbeat_at, started_at,"
                    "  database_backend, correlation_id, idempotency_key, actor_principal_type"
                    ") VALUES ("
                    "  :id, :iid, 1, 'RUNNING', :now, :now, 'sqlite', :cid, :ik, 'user'"
                    ")"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "iid": identity_id_1,
                    "now": datetime.now(UTC).isoformat(),
                    "cid": "phase1-orm-roundtrip-cid-003",
                    "ik": shared,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO orchestration_run_attempts("
                    "  id, identity_id, attempt_number, status, heartbeat_at, started_at,"
                    "  database_backend, correlation_id, idempotency_key, actor_principal_type"
                    ") VALUES ("
                    "  :id, :iid, 1, 'RUNNING', :now, :now, 'postgresql', :cid, :ik, 'user'"
                    ")"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "iid": identity_id_2,
                    "now": datetime.now(UTC).isoformat(),
                    "cid": "phase1-orm-roundtrip-cid-004",
                    "ik": shared,
                },
            )
            conn.commit()

    def test_scheme_run_frozen_envelope_roundtrip(self, engine) -> None:
        """scheme_runs.frozen_envelope accepts and roundtrips a dict."""
        import json

        project_id, project_version_id = _seed_chain_for_scheme_run(engine)
        run_id = str(uuid.uuid4())

        envelope = {
            "schema_version": "v1",
            "zone": {"hash": "deadbeef" * 8},
            "cooling_load": {"hash": "cafebabe" * 8},
            "equipment": {"hash": "f00dface" * 8},
            "power": {"hash": "12345678" * 8},
            "investment": {"hash": "abcdef00" * 8},
        }

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO scheme_runs("
                    "  id, project_id, project_version_id, weight_set_id,"
                    "  status, generator_version, source_snapshot_hash,"
                    "  input_snapshot, assumption_snapshot,"
                    "  comparison_snapshot, candidates_snapshot,"
                    "  requires_review, recommended_scheme_code,"
                    "  warning_messages, created_at,"
                    "  frozen_envelope, database_backend"
                    ") VALUES ("
                    "  :id, :pid, :pvid, :wsid,"
                    "  'pending', 'v1', :shash,"
                    "  '{}', '{}',"
                    "  '{}', '{}',"
                    "  1, NULL,"
                    "  '[]', :now,"
                    "  :env, 'sqlite'"
                    ")"
                ),
                {
                    "id": run_id,
                    "pid": project_id,
                    "pvid": project_version_id,
                    "wsid": str(uuid.uuid4()),
                    "shash": run_id * 2,
                    "env": json.dumps(envelope),
                    "now": datetime.now(UTC).isoformat(),
                },
            )
            conn.commit()

            row = conn.execute(
                text("SELECT frozen_envelope, database_backend FROM scheme_runs WHERE id = :id"),
                {"id": run_id},
            ).fetchone()
            assert row is not None
            stored = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            assert stored == envelope
            assert row[1] == "sqlite"

    def test_attempt_scheme_run_id_fk_exists(self, engine) -> None:
        """The FK from orchestration_run_attempts.scheme_run_id →
        scheme_runs.id is registered as a database FK (verified via
        PRAGMA foreign_key_list). SQLite enforces FKs only when
        ``PRAGMA foreign_keys=ON`` is set on each connection; SQLAlchemy
        passes this through at the connection level.

        We verify the FK is REGISTERED. Runtime FK enforcement when
        the orchestrator writes scheme_run_id via SQLAlchemy is the
        orchestrator's responsibility (Phase 2).
        """
        rows = (
            engine.connect()
            .execute(text("PRAGMA foreign_key_list(orchestration_run_attempts)"))
            .fetchall()
        )
        matches = [
            r for r in rows if r[3] == "scheme_run_id" and r[2] == "scheme_runs" and r[4] == "id"
        ]
        assert matches, (
            f"FK orchestration_run_attempts.scheme_run_id → scheme_runs.id "
            f"not registered; got {rows}"
        )


class Test0035Phase1ORMAttemptReflection:
    """Verify the ORM class reflects the Phase 1 columns correctly
    (no business logic — just column mapping).
    """

    def test_orm_class_has_phase1_columns(self) -> None:
        """The OrchestrationRunAttemptRecord ORM exposes all 5 Phase 1
        columns with the right types and nullability.
        """
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        cols = {
            c.name: (c.type, c.nullable) for c in OrchestrationRunAttemptRecord.__table__.columns
        }
        assert "idempotency_key" in cols
        assert cols["idempotency_key"][1] is True
        assert "database_backend" in cols
        assert cols["database_backend"][1] is False
        assert "correlation_id" in cols
        assert cols["correlation_id"][1] is False
        assert "actor_principal_type" in cols
        assert cols["actor_principal_type"][1] is False
        assert "scheme_run_id" in cols
        assert cols["scheme_run_id"][1] is True

    def test_orm_class_has_phase1_constraints(self) -> None:
        """The ORM class declares the Phase 1 unique index + CHECK
        constraints by their pinned names.
        """
        from cold_storage.modules.orchestration.infrastructure.orm import (
            OrchestrationRunAttemptRecord,
        )

        idx_names = {i.name for i in OrchestrationRunAttemptRecord.__table__.indexes}
        assert "uq_attempt_idempotency_key_db" in idx_names

        cc_names = {c.name for c in OrchestrationRunAttemptRecord.__table__.constraints}
        assert "ck_attempt_database_backend" in cc_names
        assert "ck_attempt_actor_principal_type" in cc_names

    def test_scheme_run_orm_has_phase1_columns(self) -> None:
        """SchemeRunRecord ORM exposes frozen_envelope + database_backend."""
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        cols = {c.name: (c.type, c.nullable) for c in SchemeRunRecord.__table__.columns}
        assert "frozen_envelope" in cols
        assert cols["frozen_envelope"][1] is True
        assert "database_backend" in cols
        assert cols["database_backend"][1] is False

        cc_names = {c.name for c in SchemeRunRecord.__table__.constraints}
        assert "ck_scheme_run_database_backend" in cc_names
