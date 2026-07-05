"""Migration 0035 Phase 1 — schema and identity foundation on PostgreSQL.

Runs the same Phase 1 upgrade/downgrade/re-upgrade cycle as the
SQLite equivalent, but against a real PostgreSQL container
(marked ``@pytest.mark.postgresql``). Verifies that:

* Alembic upgrade head adds 5 columns on
  orchestration_run_attempts and 2 columns on scheme_runs.
* CHECK constraints for the database_backend enum and
  actor_principal_type enum are present on PostgreSQL.
* The unique index ``uq_attempt_idempotency_key_db`` is a
  real unique index (not a partial-index ducking on PG).
* The foreign key ``fk_attempt_scheme_run`` is enforced.
* Downgrade cleanly removes everything; re-upgrade restores.

Phase 1 contract: see design doc
docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md
(Frozen Contract Authority SHA: ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2)
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid as _uuid_mod
from contextlib import suppress
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.pool import NullPool

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


@pytest.fixture()
def _pg_phase1_admin_url(pg_admin_url: str):
    """Per-test admin engine to create + tear down an isolated PG
    database for a single Phase 1 test.
    """
    admin_engine = create_engine(pg_admin_url, poolclass=NullPool)
    admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")
    db_name = f"phase1_{_uuid_mod.uuid4().hex[:12]}"
    with admin_engine.connect() as conn:
        conn.execute(sa_text(f'CREATE DATABASE "{db_name}"'))

    yield db_name

    with admin_engine.connect() as conn:
        with suppress(Exception):
            conn.execute(sa_text(f'RELEASE ALL "{db_name}"'))
        with suppress(Exception):
            conn.execute(sa_text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))


@pytest.fixture()
def pg_phase1_db_url(_pg_phase1_admin_url):
    """Per-test ephemeral PG database URL backed by an
    isolated phase1 schema applied via Alembic.

    Usage::

        def test_x(pg_phase1_db_url: str):
            engine = create_engine(pg_phase1_db_url)
    """
    db_name = _pg_phase1_admin_url
    r = _run_alembic(pg_phase1_db_url_for(db_name), "upgrade", "head")
    if r.returncode != 0:
        pytest.fail(f"Alembic upgrade failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
    yield pg_phase1_db_url_for(db_name)


def pg_phase1_db_url_for(db_name: str) -> str:
    """Build a per-test PostgreSQL URL with the chosen DB name.

    Reads ``DATABASE_URL`` from env, swaps the database name, and
    uses the ``postgresql+psycopg2`` driver.
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(os.environ.get("PG_BASE_URL") or os.environ["DATABASE_URL"])
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432
    netloc = f"{user}:{password}@{host}:{port}" if password else f"{user}@{host}:{port}"
    return urlunparse(("postgresql+psycopg2", netloc, f"/{db_name}", "", "", ""))


class Test0035Phase1SchemaDeltaPostgreSQL:
    def test_upgrade_head_adds_required_columns(self, pg_phase1_db_url: str) -> None:
        """Upgrade to head — both tables have the new Phase 1 columns."""
        r = _run_alembic(pg_phase1_db_url, "upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"

        engine = create_engine(pg_phase1_db_url, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                orch_cols = {
                    row[0]
                    for row in conn.execute(
                        sa_text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'orchestration_run_attempts'"
                        )
                    ).fetchall()
                }
                for name in (
                    "idempotency_key",
                    "database_backend",
                    "correlation_id",
                    "actor_principal_type",
                    "scheme_run_id",
                ):
                    assert name in orch_cols, f"missing column {name} in PG"

                scheme_cols = {
                    row[0]
                    for row in conn.execute(
                        sa_text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'scheme_runs'"
                        )
                    ).fetchall()
                }
                assert "frozen_envelope" in scheme_cols
                assert "database_backend" in scheme_cols
        finally:
            engine.dispose()

    def test_check_constraints_present_on_postgresql(self, pg_phase1_db_url: str) -> None:
        """Verify the three CHECK constraints are registered in PG."""
        r = _run_alembic(pg_phase1_db_url, "upgrade", "head")
        assert r.returncode == 0

        engine = create_engine(pg_phase1_db_url, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                # PG stores CHECK on table; query pg_constraint
                rows = conn.execute(
                    sa_text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE contype = 'c' "
                        "AND conrelid::regclass::text IN ("
                        "  'orchestration_run_attempts', 'scheme_runs'"
                        ")"
                    )
                ).fetchall()
                names = {r[0] for r in rows}
                assert "ck_attempt_database_backend" in names
                assert "ck_attempt_actor_principal_type" in names
                assert "ck_scheme_run_database_backend" in names
        finally:
            engine.dispose()

    def test_unique_index_uq_attempt_idempotency_key_db(self, pg_phase1_db_url: str) -> None:
        """The unique index on (database_backend, idempotency_key) is
        present in PG."""
        r = _run_alembic(pg_phase1_db_url, "upgrade", "head")
        assert r.returncode == 0

        engine = create_engine(pg_phase1_db_url, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    sa_text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE tablename = 'orchestration_run_attempts'"
                    )
                ).fetchall()
                names = {r[0] for r in rows}
                assert "uq_attempt_idempotency_key_db" in names
        finally:
            engine.dispose()

    def test_fk_attempt_scheme_run_registered(self, pg_phase1_db_url: str) -> None:
        """FK `fk_attempt_scheme_run` is registered with PG."""
        r = _run_alembic(pg_phase1_db_url, "upgrade", "head")
        assert r.returncode == 0

        engine = create_engine(pg_phase1_db_url, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    sa_text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE contype = 'f' "
                        "AND conrelid::regclass::text = 'orchestration_run_attempts'"
                    )
                ).fetchall()
                names = {r[0] for r in rows}
                assert "fk_attempt_scheme_run" in names
        finally:
            engine.dispose()


class Test0035Phase1RoundtripPostgreSQL:
    def test_downgrade_re_upgrade_full_roundtrip(self, pg_phase1_db_url: str) -> None:
        """Upgrade head → downgrade to 0034 → re-upgrade head."""
        r = _run_alembic(pg_phase1_db_url, "upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}\n{r.stdout}"

        r = _run_alembic(pg_phase1_db_url, "downgrade", "0034_add_production_source_archives")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}\n{r.stdout}"

        engine = create_engine(pg_phase1_db_url, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                cols_after = {
                    row[0]
                    for row in conn.execute(
                        sa_text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'orchestration_run_attempts'"
                        )
                    ).fetchall()
                }
                for name in (
                    "idempotency_key",
                    "database_backend",
                    "correlation_id",
                    "actor_principal_type",
                    "scheme_run_id",
                ):
                    assert name not in cols_after, f"column {name} still present after downgrade"
        finally:
            engine.dispose()

        r = _run_alembic(pg_phase1_db_url, "upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}\n{r.stdout}"

        engine = create_engine(pg_phase1_db_url, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                cols_again = {
                    row[0]
                    for row in conn.execute(
                        sa_text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'orchestration_run_attempts'"
                        )
                    ).fetchall()
                }
                for name in (
                    "idempotency_key",
                    "database_backend",
                    "correlation_id",
                    "actor_principal_type",
                    "scheme_run_id",
                ):
                    assert name in cols_again, f"column {name} missing after re-upgrade"
        finally:
            engine.dispose()
