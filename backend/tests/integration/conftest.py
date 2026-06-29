"""Shared PostgreSQL integration test fixtures.

Provides reusable fixtures for integration tests that need an isolated
PostgreSQL database with Alembic head schema applied.  Eliminates
duplication across test_orchestration_transaction_a_postgresql.py,
test_orchestration_migration_postgresql.py, and future PG tests.

All fixtures:
- Use AUTOCOMMIT isolation for DDL operations.
- Use NullPool (no connection pooling for ephemeral test databases).
- Sanitize DB names to valid PostgreSQL identifiers.
- Force-terminate existing connections before dropping databases.
- Teardown on Alembic upgrade failure (skip test).

Tagged with ``@pytest.mark.postgresql`` — run with ``-m postgresql``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid as _uuid_mod
from collections.abc import Generator
from contextlib import suppress
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[2]

_DB_NAME_RE = re.compile(r"[^a-z0-9_]")


def _sanitize(name: str) -> str:
    """Return a valid PostgreSQL database name (lowercase, alphanumeric + underscore)."""
    return _DB_NAME_RE.sub("_", name.lower())[:63]


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run an Alembic command against *database_url*.

    Sets ``DATABASE_URL`` and ``DATABASE_BACKEND=postgresql`` in the
    subprocess environment.
    """
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


# ── Session-scoped admin URL ─────────────────────────────────────────────


@pytest.fixture(scope="session")
def pg_admin_url() -> str:
    """PostgreSQL admin connection URL derived from ``DATABASE_URL``.

    Replaces the database name with ``postgres`` for DDL operations
    (CREATE/DROP DATABASE).  Requires AUTOCOMMIT isolation.
    """
    original = os.environ.get("DATABASE_URL", "")
    if not original:
        pytest.skip("DATABASE_URL not set")
    base = original.rsplit("/", 1)[0]
    return f"{base}/postgres"


# ── Database factory (creates + tears down isolated PG databases) ────────


@pytest.fixture()
def pg_database_factory(pg_admin_url: str) -> Generator:
    """Yield a callable that creates isolated PostgreSQL test databases.

    Uses AUTOCOMMIT isolation and ``NullPool`` for the admin connection.
    Collects all created databases and drops them in teardown, using
    ``DROP DATABASE IF EXISTS … WITH (FORCE)`` to force-terminate
    lingering connections.
    """
    created: list[str] = []
    admin_engine = create_engine(pg_admin_url, poolclass=NullPool)
    admin_engine = admin_engine.execution_options(isolation_level="AUTOCOMMIT")

    def create_db(*, prefix: str) -> str:
        db_name = _sanitize(f"{prefix}_{_uuid_mod.uuid4().hex[:12]}")
        with admin_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {db_name}"))
        base_url = os.environ.get("DATABASE_URL", "").rsplit("/", 1)[0]
        db_url = f"{base_url}/{db_name}"
        created.append(db_name)
        return db_url

    try:
        yield create_db
    finally:
        with admin_engine.connect() as conn:
            for db_name in created:
                with suppress(Exception):
                    conn.execute(text(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)"))
        admin_engine.dispose()


# ── Migrated database (Alembic head) ─────────────────────────────────────


@pytest.fixture()
def pg_database(pg_database_factory) -> str:
    """Isolated database with full head schema applied via Alembic.

    On upgrade failure the test is skipped (not failed), and the
    database is still cleaned up by the factory teardown.
    """
    db_url = pg_database_factory(prefix="pg_int")
    r = _run_alembic(db_url, "upgrade", "head")
    if r.returncode != 0:
        pytest.fail(f"Alembic upgrade to head failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}")
    return db_url


# ── Engine fixture ───────────────────────────────────────────────────────


@pytest.fixture()
def pg_engine(pg_database: str):
    """SQLAlchemy engine for the migrated test database (NullPool)."""
    engine = create_engine(pg_database, poolclass=NullPool)
    yield engine
    engine.dispose()


# ── Session factory ──────────────────────────────────────────────────────


@pytest.fixture()
def pg_session_factory(pg_engine):
    """Session factory bound to the migrated test database.

    ``expire_on_commit=False`` allows reading attributes after commit.
    """
    return sessionmaker(bind=pg_engine, expire_on_commit=False)
