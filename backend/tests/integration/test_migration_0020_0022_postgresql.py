"""Migration 0020/0021/0022 upgrade/downgrade/upgrade cycle test (real Alembic + PostgreSQL).

Verifies that migrations 0020_add_cleanup_debt, 0021_cleanup_debt_lock_expires,
and 0022_add_claim_version_audit_log are fully idempotent by running REAL Alembic
subprocess commands against a temporary PostgreSQL schema created for each test.

Covers:
- cleanup_debt table creation with all columns at head (incl. claim_version)
- migration_audit_log table creation with 8 columns, 2 indexes, 2 CHECK constraints
- claim_version removed by downgrade 0021, restored by re-upgrade
- migration_audit_log dropped by downgrade 0021, restored by re-upgrade
- All 4 cleanup_debt indexes (3 from 0020, 1 from 0021)
- All 5 CHECK constraints incl. ck_cleanup_debt_claim_version
- The UNIQUE constraint uq_cleanup_debt_stale_file
- Full roundtrip: upgrade head → downgrade 0021 → upgrade head
- Re-upgrade idempotency
- CHECK constraint enforcement by actual invalid INSERT values
- migration_audit_log CHECK constraints (actor_not_empty, reason_not_empty)

Requires a running PostgreSQL instance (DATABASE_URL env var).
Skipped if PostgreSQL is not available.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.join(
    os.path.dirname(__file__),  # …/tests/integration
    "..",  # …/tests
    "..",  # …/backend
)


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Return DATABASE_URL or skip."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL migration tests")
    return url


def _run_alembic(
    args: list[str],
    url: str | None = None,
    *,
    timeout: int = 120,
    schema: str | None = None,
) -> subprocess.CompletedProcess:
    """Run an alembic subcommand, optionally scoped to *schema*."""
    env = os.environ.copy()
    db_url = url if url is not None else os.environ.get("DATABASE_URL", "")
    env["DATABASE_URL"] = db_url
    env["PYTHONPATH"] = "src"

    # Parse DATABASE_URL and set POSTGRES_* vars for env.py compatibility
    if db_url:
        parsed = urlparse(db_url)
        if parsed.scheme.startswith("postgresql"):
            env.setdefault("POSTGRES_USER", parsed.username or "")
            env.setdefault("POSTGRES_PASSWORD", parsed.password or "")
            env.setdefault("POSTGRES_HOST", parsed.hostname or "localhost")
            env.setdefault("POSTGRES_PORT", str(parsed.port or 5432))
            dbname = parsed.path.lstrip("/") if parsed.path else "cold_storage"
            env.setdefault("POSTGRES_DB", dbname)

    if schema:
        env["PGOPTIONS"] = f"-c search_path={schema}"

    result = subprocess.run(
        ["uv", "run", "alembic"] + args,
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


# ---------------------------------------------------------------------------
# PostgreSQL introspection helpers
# ---------------------------------------------------------------------------


def _pg_get_columns(engine: sa.Engine, table: str) -> set[str]:
    inspector = sa.inspect(engine)
    return {c["name"] for c in inspector.get_columns(table)}


def _pg_get_unique_constraints(engine: sa.Engine, table: str) -> dict[str, list[str]]:
    """Return dict mapping constraint name -> list of column names."""
    inspector = sa.inspect(engine)
    return {
        item["name"]: item["column_names"]
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }


def _pg_get_indexes(engine: sa.Engine, table: str) -> dict[str, dict]:
    """Return dict mapping index name -> index info."""
    inspector = sa.inspect(engine)
    return {ix["name"]: ix for ix in inspector.get_indexes(table) if ix.get("name")}


def _pg_get_check_constraints(engine: sa.Engine, table: str) -> dict[str, str]:
    """Return dict mapping constraint name -> sqltext."""
    inspector = sa.inspect(engine)
    return {
        c["name"]: c["sqltext"] for c in inspector.get_check_constraints(table) if c.get("name")
    }


# ---------------------------------------------------------------------------
# Isolation fixtures — each test gets a unique temporary schema
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def tmp_schema(pg_url: str) -> str:
    """Create a temporary PostgreSQL schema for one test, drop on teardown."""
    schema_name = f"tst_{uuid.uuid4().hex[:12]}"
    engine = sa.create_engine(pg_url, isolation_level="AUTOCOMMIT")
    with engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema_name}"'))
    engine.dispose()

    yield schema_name

    engine = sa.create_engine(pg_url, isolation_level="AUTOCOMMIT")
    with engine.begin() as conn:
        conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
    engine.dispose()


@pytest.fixture(scope="function")
def pg_engine(pg_url: str, tmp_schema: str):
    """Create a real PostgreSQL engine scoped to the temporary schema."""
    eng = sa.create_engine(
        pg_url,
        connect_args={"options": f"-c search_path={tmp_schema}"},
    )
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def pg_session_factory(pg_engine):
    return sa.orm.sessionmaker(bind=pg_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Shared expected schema — HEAD (0022)
# ---------------------------------------------------------------------------

ALL_CLEANUP_DEBT_COLUMNS = {
    "id",
    "idempotency_key",
    "storage_key",
    "stale_claim_token",
    "stale_claim_version",
    "reclaim_token",
    "reclaim_version",
    "status",
    "created_at",
    "completed_at",
    "retry_count",
    "last_error",
    "next_retry_at",
    "locked_at",
    "locked_by",
    "lock_expires_at",  # added by 0021
    "claim_version",  # added by 0022
}

COLUMNS_WITHOUT_0022 = ALL_CLEANUP_DEBT_COLUMNS - {"claim_version"}

COLUMNS_WITHOUT_LOCK_EXPIRES = COLUMNS_WITHOUT_0022 - {"lock_expires_at"}

HEAD_INDEXES = {
    "ix_cleanup_debt_idempotency_key",
    "ix_cleanup_debt_status",
    "ix_cleanup_debt_next_retry_at",
    "ix_cleanup_debt_lock_expires_at",  # added by 0021
}

INDEXES_WITHOUT_LOCK_EXPIRES = HEAD_INDEXES - {"ix_cleanup_debt_lock_expires_at"}

ALL_CHECK_CONSTRAINTS = {
    "ck_cleanup_debt_status",
    "ck_cleanup_debt_stale_claim_version",
    "ck_cleanup_debt_reclaim_version",
    "ck_cleanup_debt_retry_count",
    "ck_cleanup_debt_claim_version",  # added by 0022
}

CHECK_CONSTRAINTS_WITHOUT_0022 = ALL_CHECK_CONSTRAINTS - {"ck_cleanup_debt_claim_version"}

ALL_UNIQUE_CONSTRAINTS = {
    "uq_cleanup_debt_stale_file",
}

# -- migration_audit_log (added by 0022) --

ALL_MIGRATION_AUDIT_LOG_COLUMNS = {
    "id",
    "storage_key",
    "migration_actor",
    "audit_reason",
    "operation",
    "result",
    "source_hash",
    "created_at",
}

MIGRATION_AUDIT_LOG_INDEXES = {
    "ix_migration_audit_log_storage_key",
    "ix_migration_audit_log_created_at",
}

MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS = {
    "ck_migration_audit_log_actor_not_empty",
    "ck_migration_audit_log_reason_not_empty",
}


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestCleanupDebtMigrationPostgreSQL:
    """Verify full Alembic upgrade → downgrade → upgrade cycle for 0020/0021/0022.

    Every test creates its own temporary PostgreSQL schema, runs migrations
    inside it, and drops the schema on teardown.  Tests are fully isolated.
    """

    # -- upgrade head (0022) -------------------------------------------------

    def test_upgrade_creates_cleanup_debt_table(self, pg_engine, tmp_schema):
        """After upgrade head, cleanup_debt table exists with all columns (incl. claim_version)."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, f"Expected all columns, got: {cols}"

    def test_upgrade_creates_migration_audit_log_table(self, pg_engine, tmp_schema):
        """After upgrade head, migration_audit_log table exists."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "migration_audit_log")
        assert cols == ALL_MIGRATION_AUDIT_LOG_COLUMNS, (
            f"Expected migration_audit_log columns, got: {cols}"
        )

    def test_upgrade_creates_cleanup_debt_indexes(self, pg_engine, tmp_schema):
        """After upgrade head, all 4 cleanup_debt indexes exist."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        indexes = _pg_get_indexes(pg_engine, "cleanup_debt")
        index_names = set(indexes.keys())
        assert index_names == HEAD_INDEXES, f"Expected indexes {HEAD_INDEXES}, got: {index_names}"

    def test_upgrade_creates_migration_audit_log_indexes(self, pg_engine, tmp_schema):
        """After upgrade head, migration_audit_log indexes exist."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        indexes = _pg_get_indexes(pg_engine, "migration_audit_log")
        index_names = set(indexes.keys())
        assert index_names == MIGRATION_AUDIT_LOG_INDEXES, (
            "Expected migration_audit_log indexes "
            f"{MIGRATION_AUDIT_LOG_INDEXES}, got: {index_names}"
        )

    def test_upgrade_creates_check_constraints(self, pg_engine, tmp_schema):
        """After upgrade head, all 5 CHECK constraints exist incl. claim_version."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        check_names = set(checks.keys())
        assert check_names == ALL_CHECK_CONSTRAINTS, (
            f"Expected CHECK constraints {ALL_CHECK_CONSTRAINTS}, got: {check_names}"
        )

    def test_upgrade_creates_migration_audit_log_check_constraints(self, pg_engine, tmp_schema):
        """After upgrade head, migration_audit_log CHECK constraints exist."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _pg_get_check_constraints(pg_engine, "migration_audit_log")
        check_names = set(checks.keys())
        assert check_names == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK constraints {MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS}, "
            f"got: {check_names}"
        )

    def test_upgrade_creates_unique_constraint(self, pg_engine, tmp_schema):
        """After upgrade head, uq_cleanup_debt_stale_file unique constraint exists."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        uq = _pg_get_unique_constraints(pg_engine, "cleanup_debt")
        assert "uq_cleanup_debt_stale_file" in uq, (
            f"Expected uq_cleanup_debt_stale_file, got: {list(uq.keys())}"
        )
        columns = uq["uq_cleanup_debt_stale_file"]
        assert columns == ["storage_key", "stale_claim_token", "stale_claim_version"], (
            f"Expected columns [storage_key, stale_claim_token, stale_claim_version], got {columns}"
        )

    # -- CHECK constraint enforcement ---------------------------------------

    def test_ck_cleanup_debt_status_enforced(self, pg_session_factory, tmp_schema):
        """Invalid status hits ck_cleanup_debt_status IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO cleanup_debt "
                    "(id, idempotency_key, storage_key, stale_claim_token, "
                    "stale_claim_version, reclaim_token, reclaim_version, status, "
                    "created_at, retry_count, last_error, locked_by) "
                    "VALUES ("
                    "'test-bad-status', 'ik1', 'sk1', "
                    "'tok1', 0, 'tok2', 0, 'invalid_status', "
                    "'2026-06-25T00:00:00', 0, '', '')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_cleanup_debt_status" in err_msg, (
            f"Expected constraint ck_cleanup_debt_status, got: {err_msg}"
        )

    def test_ck_cleanup_debt_retry_count_enforced(self, pg_session_factory, tmp_schema):
        """Negative retry_count hits ck_cleanup_debt_retry_count IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO cleanup_debt "
                    "(id, idempotency_key, storage_key, stale_claim_token, "
                    "stale_claim_version, reclaim_token, reclaim_version, status, "
                    "created_at, retry_count, last_error, locked_by) "
                    "VALUES ("
                    "'test-bad-retry', 'ik2', 'sk2', "
                    "'tok1', 0, 'tok2', 0, 'pending', "
                    "'2026-06-25T00:00:00', -1, '', '')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_cleanup_debt_retry_count" in err_msg, (
            f"Expected constraint ck_cleanup_debt_retry_count, got: {err_msg}"
        )

    def test_ck_cleanup_debt_claim_version_enforced(self, pg_session_factory, tmp_schema):
        """Negative claim_version hits ck_cleanup_debt_claim_version IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO cleanup_debt "
                    "(id, idempotency_key, storage_key, stale_claim_token, "
                    "stale_claim_version, reclaim_token, reclaim_version, status, "
                    "created_at, retry_count, last_error, locked_by, claim_version) "
                    "VALUES ("
                    "'test-bad-cv', 'ik3', 'sk3', "
                    "'tok1', 0, 'tok2', 0, 'pending', "
                    "'2026-06-25T00:00:00', 0, '', '', -1)"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_cleanup_debt_claim_version" in err_msg, (
            f"Expected constraint ck_cleanup_debt_claim_version, got: {err_msg}"
        )

    def test_ck_migration_audit_log_actor_not_empty_enforced(self, pg_session_factory, tmp_schema):
        """Empty migration_actor hits ck_migration_audit_log_actor_not_empty IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO migration_audit_log "
                    "(id, storage_key, migration_actor, audit_reason, "
                    "operation, result, source_hash, created_at) "
                    "VALUES ("
                    "'test-bad-actor', 'sk-empty-actor', '', "
                    "'some reason', 'legacy_delete', 'deleted', "
                    "'abc123', '2026-06-25T00:00:00')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_migration_audit_log_actor_not_empty" in err_msg, (
            f"Expected constraint ck_migration_audit_log_actor_not_empty, got: {err_msg}"
        )

    def test_ck_migration_audit_log_reason_not_empty_enforced(self, pg_session_factory, tmp_schema):
        """Empty audit_reason hits ck_migration_audit_log_reason_not_empty IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO migration_audit_log "
                    "(id, storage_key, migration_actor, audit_reason, "
                    "operation, result, source_hash, created_at) "
                    "VALUES ("
                    "'test-bad-reason', 'sk-empty-reason', 'test-user', "
                    " '', 'legacy_delete', 'deleted', "
                    "'abc123', '2026-06-25T00:00:00')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_migration_audit_log_reason_not_empty" in err_msg, (
            f"Expected constraint ck_migration_audit_log_reason_not_empty, got: {err_msg}"
        )

    # -- downgrade 0021 (remove 0022 changes) --------------------------------

    def test_downgrade_removes_claim_version_column(self, pg_engine, tmp_schema):
        """After downgrade to 0021, claim_version column is gone."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "cleanup_debt")
        assert cols == COLUMNS_WITHOUT_0022, f"Expected columns without claim_version, got: {cols}"

    def test_downgrade_drops_migration_audit_log_table(self, pg_engine, tmp_schema):
        """After downgrade to 0021, migration_audit_log table is gone."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        inspector = sa.inspect(pg_engine)
        table_names = inspector.get_table_names()
        assert "migration_audit_log" not in table_names, (
            f"migration_audit_log should be gone after downgrade, got: {table_names}"
        )

    def test_downgrade_removes_claim_version_check_constraint(self, pg_engine, tmp_schema):
        """After downgrade, ck_cleanup_debt_claim_version CHECK is gone."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)

        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        check_names = set(checks.keys())
        assert check_names == CHECK_CONSTRAINTS_WITHOUT_0022, (
            f"Expected CHECK constraints without claim_version, got: {check_names}"
        )

    def test_downgrade_preserves_other_cleanup_debt_constraints(self, pg_engine, tmp_schema):
        """After downgrade, other cleanup_debt CHECK and UNIQUE constraints are preserved."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)

        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        check_names = set(checks.keys())
        assert check_names == CHECK_CONSTRAINTS_WITHOUT_0022, (
            f"Expected CHECK constraints preserved, got: {check_names}"
        )

        uq = _pg_get_unique_constraints(pg_engine, "cleanup_debt")
        assert "uq_cleanup_debt_stale_file" in uq

    # -- re-upgrade head -----------------------------------------------------

    def test_re_upgrade_restores_claim_version(self, pg_engine, tmp_schema):
        """Re-upgrade to head restores claim_version column and CHECK."""
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic re-upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, (
            f"Expected all columns after re-upgrade, got: {cols}"
        )

        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        assert "ck_cleanup_debt_claim_version" in checks, (
            f"Missing ck_cleanup_debt_claim_version after re-upgrade, got: {set(checks.keys())}"
        )

    def test_re_upgrade_restores_migration_audit_log(self, pg_engine, tmp_schema):
        """Re-upgrade to head restores migration_audit_log table, indexes, and CHECK constraints."""
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic re-upgrade failed:\n{result.stderr}"

        # Table exists with all columns
        cols = _pg_get_columns(pg_engine, "migration_audit_log")
        assert cols == ALL_MIGRATION_AUDIT_LOG_COLUMNS, (
            f"Expected all migration_audit_log columns after re-upgrade, got: {cols}"
        )

        # Indexes exist
        indexes = _pg_get_indexes(pg_engine, "migration_audit_log")
        index_names = set(indexes.keys())
        assert index_names == MIGRATION_AUDIT_LOG_INDEXES, (
            f"Expected audit log indexes after re-upgrade, got: {index_names}"
        )

        # CHECK constraints exist
        checks = _pg_get_check_constraints(pg_engine, "migration_audit_log")
        check_names = set(checks.keys())
        assert check_names == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK constraints after re-upgrade, got: {check_names}"
        )

    def test_re_upgrade_preserves_constraints(self, pg_engine, tmp_schema):
        """Re-upgrade preserves all CHECK and UNIQUE constraints on cleanup_debt."""
        _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)
        _run_alembic(["upgrade", "head"], schema=tmp_schema)

        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        check_names = set(checks.keys())
        assert check_names == ALL_CHECK_CONSTRAINTS, (
            f"Expected all CHECK constraints after re-upgrade, got: {check_names}"
        )
        uq = _pg_get_unique_constraints(pg_engine, "cleanup_debt")
        assert "uq_cleanup_debt_stale_file" in uq

        # Indexes restored
        indexes = _pg_get_indexes(pg_engine, "cleanup_debt")
        index_names = set(indexes.keys())
        assert index_names == HEAD_INDEXES, (
            f"Expected all indexes after re-upgrade, got: {index_names}"
        )

    # -- idempotent re-upgrade ----------------------------------------------

    def test_re_upgrade_idempotent_when_already_at_head(self, pg_engine, tmp_schema):
        """Running upgrade head again when already at head is a no-op."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"idempotent re-upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS

        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        assert "ck_cleanup_debt_claim_version" in set(checks.keys())

    # -- full roundtrip -----------------------------------------------------

    def test_postgresql_cleanup_debt_0020_0022_roundtrip(self, pg_engine, tmp_schema):
        """Full roundtrip: upgrade head → downgrade 0021 → upgrade head."""
        # 1. upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"initial upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, f"Missing columns after upgrade, got: {cols}"

        # Verify migration_audit_log exists
        audit_cols = _pg_get_columns(pg_engine, "migration_audit_log")
        assert audit_cols == ALL_MIGRATION_AUDIT_LOG_COLUMNS

        # 2. downgrade to 0021 (removes claim_version + migration_audit_log)
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "cleanup_debt")
        assert "claim_version" not in cols, "claim_version should be gone after downgrade 0021"
        for c in COLUMNS_WITHOUT_0022:
            assert c in cols, f"Column {c!r} missing after downgrade"

        inspector = sa.inspect(pg_engine)
        assert "migration_audit_log" not in inspector.get_table_names(), (
            "migration_audit_log should be gone after downgrade"
        )

        # 3. re-upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "cleanup_debt")
        assert cols == ALL_CLEANUP_DEBT_COLUMNS, (
            f"Expected all columns after re-upgrade, got: {cols}"
        )

        audit_cols = _pg_get_columns(pg_engine, "migration_audit_log")
        assert audit_cols == ALL_MIGRATION_AUDIT_LOG_COLUMNS, (
            f"Expected migration_audit_log after re-upgrade, got: {audit_cols}"
        )

    def test_postgresql_cleanup_debt_constraints_and_indexes(self, pg_engine, tmp_schema):
        """Verify all constraints and indexes survive the roundtrip."""
        # Upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0

        # Verify indexes at head
        indexes = _pg_get_indexes(pg_engine, "cleanup_debt")
        index_names = set(indexes.keys())
        assert index_names == HEAD_INDEXES, f"Expected all indexes at head, got: {index_names}"

        # Verify CHECK constraints at head
        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        check_names = set(checks.keys())
        assert check_names == ALL_CHECK_CONSTRAINTS, (
            f"Expected all CHECK constraints at head, got: {check_names}"
        )

        # Verify UNIQUE constraint at head
        uq = _pg_get_unique_constraints(pg_engine, "cleanup_debt")
        assert "uq_cleanup_debt_stale_file" in uq

        # Verify migration_audit_log constraints at head
        audit_checks = _pg_get_check_constraints(pg_engine, "migration_audit_log")
        audit_check_names = set(audit_checks.keys())
        assert audit_check_names == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK at head, got: {audit_check_names}"
        )

        # Downgrade to 0021
        result = _run_alembic(["downgrade", "0021_cleanup_debt_lock_expires"], schema=tmp_schema)
        assert result.returncode == 0

        # claim_version CHECK gone
        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        check_names = set(checks.keys())
        assert "ck_cleanup_debt_claim_version" not in check_names, (
            "ck_cleanup_debt_claim_version should be gone after downgrade"
        )
        assert check_names == CHECK_CONSTRAINTS_WITHOUT_0022, (
            f"Expected CHECK constraints without claim_version, got: {check_names}"
        )

        # migration_audit_log table gone
        inspector = sa.inspect(pg_engine)
        assert "migration_audit_log" not in inspector.get_table_names()

        # Other indexes remain
        indexes = _pg_get_indexes(pg_engine, "cleanup_debt")
        assert "ix_cleanup_debt_idempotency_key" in indexes
        assert "ix_cleanup_debt_status" in indexes
        assert "ix_cleanup_debt_next_retry_at" in indexes

        # Other constraints preserved
        uq = _pg_get_unique_constraints(pg_engine, "cleanup_debt")
        assert "uq_cleanup_debt_stale_file" in uq

        # Re-upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0

        # All indexes restored
        indexes = _pg_get_indexes(pg_engine, "cleanup_debt")
        index_names = set(indexes.keys())
        assert index_names == HEAD_INDEXES, (
            f"Expected all indexes back after re-upgrade, got: {index_names}"
        )

        # All CHECK constraints restored
        checks = _pg_get_check_constraints(pg_engine, "cleanup_debt")
        check_names = set(checks.keys())
        assert check_names == ALL_CHECK_CONSTRAINTS, (
            f"Expected all CHECK constraints after re-upgrade, got: {check_names}"
        )

        # All UNIQUE constraints restored
        uq = _pg_get_unique_constraints(pg_engine, "cleanup_debt")
        assert "uq_cleanup_debt_stale_file" in uq

        # migration_audit_log restored
        audit_checks = _pg_get_check_constraints(pg_engine, "migration_audit_log")
        audit_check_names = set(audit_checks.keys())
        assert audit_check_names == MIGRATION_AUDIT_LOG_CHECK_CONSTRAINTS, (
            f"Expected audit log CHECK after re-upgrade, got: {audit_check_names}"
        )
        indexes = _pg_get_indexes(pg_engine, "migration_audit_log")
        audit_index_names = set(indexes.keys())
        assert audit_index_names == MIGRATION_AUDIT_LOG_INDEXES, (
            f"Expected audit log indexes after re-upgrade, got: {audit_index_names}"
        )
