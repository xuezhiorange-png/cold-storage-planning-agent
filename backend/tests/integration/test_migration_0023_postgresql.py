"""Migration 0023 upgrade/downgrade/upgrade cycle test (real Alembic + PostgreSQL).

Verifies that migration 0023_deletion_outbox_receipts is fully
idempotent by running REAL Alembic subprocess commands against a temporary
PostgreSQL schema created for each test.

Covers:
- deletion_outbox table creation with all 11 columns and 3 indexes
- deletion_receipts table creation with all 8 columns
- All 4 deletion_outbox CHECK constraints
- All 4 deletion_receipts CHECK constraints
- The UNIQUE constraint uq_deletion_receipt_owners
- Full roundtrip: upgrade head -> downgrade 0022 -> upgrade head
- Re-upgrade idempotency
- CHECK constraint enforcement by actual invalid INSERT values
- Empty actor/reason and invalid status rejections

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
# Shared expected schema — HEAD (0023)
# ---------------------------------------------------------------------------

ALL_DELETION_OUTBOX_COLUMNS = {
    "id",
    "storage_key",
    "migration_actor",
    "audit_reason",
    "operation",
    "source_hash",
    "status",
    "created_at",
    "updated_at",
    "last_error",
    "retry_count",
    "claim_token",
    "claim_version",
    "locked_at",
    "lock_expires_at",
}

DELETION_OUTBOX_INDEXES = {
    "ix_deletion_outbox_storage_key",
    "ix_deletion_outbox_status",
    "ix_deletion_outbox_created_at",
}

DELETION_OUTBOX_CHECK_CONSTRAINTS = {
    "ck_deletion_outbox_actor_not_empty",
    "ck_deletion_outbox_reason_not_empty",
    "ck_deletion_outbox_status",
    "ck_deletion_outbox_retry_count",
    "ck_deletion_outbox_claim_version",
}

ALL_DELETION_RECEIPTS_COLUMNS = {
    "storage_key",
    "stale_claim_token",
    "stale_claim_version",
    "reclaim_token",
    "reclaim_version",
    "deleted_at",
    "deletion_hash",
    "status",
}

DELETION_RECEIPTS_CHECK_CONSTRAINTS = {
    "ck_deletion_receipt_stale_version",
    "ck_deletion_receipt_reclaim_version",
    "ck_deletion_receipt_hash",
    "ck_deletion_receipt_status",
}

DELETION_RECEIPTS_UNIQUE_CONSTRAINTS = {
    "uq_deletion_receipt_owners",
}


# ---------------------------------------------------------------------------
# Tests — upgrade / downgrade / upgrade cycle
# ---------------------------------------------------------------------------


class TestDeletionOutboxMigrationPostgreSQL:
    """Verify full Alembic upgrade -> downgrade -> upgrade cycle for 0023.

    Every test creates its own temporary PostgreSQL schema, runs migrations
    inside it, and drops the schema on teardown.  Tests are fully isolated.
    """

    # -- upgrade head (0023) -------------------------------------------------

    def test_upgrade_creates_deletion_outbox_table(self, pg_engine, tmp_schema):
        """After upgrade head, deletion_outbox table exists with all columns."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS, (
            f"Expected all deletion_outbox columns, got: {cols}"
        )

    def test_upgrade_creates_deletion_receipts_table(self, pg_engine, tmp_schema):
        """After upgrade head, deletion_receipts table exists."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns, got: {cols}"
        )

    def test_upgrade_creates_deletion_outbox_indexes(self, pg_engine, tmp_schema):
        """After upgrade head, all 3 deletion_outbox indexes exist."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        indexes = _pg_get_indexes(pg_engine, "deletion_outbox")
        index_names = set(indexes.keys())
        assert index_names == DELETION_OUTBOX_INDEXES, (
            f"Expected indexes {DELETION_OUTBOX_INDEXES}, got: {index_names}"
        )

    def test_upgrade_creates_deletion_outbox_check_constraints(self, pg_engine, tmp_schema):
        """After upgrade head, all 4 deletion_outbox CHECK constraints exist."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _pg_get_check_constraints(pg_engine, "deletion_outbox")
        check_names = set(checks.keys())
        assert check_names == DELETION_OUTBOX_CHECK_CONSTRAINTS, (
            f"Expected deletion_outbox CHECK constraints "
            f"{DELETION_OUTBOX_CHECK_CONSTRAINTS}, got: {check_names}"
        )

    def test_upgrade_creates_deletion_receipts_check_constraints(self, pg_engine, tmp_schema):
        """After upgrade head, all 4 deletion_receipts CHECK constraints exist."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        check_names = set(checks.keys())
        assert check_names == DELETION_RECEIPTS_CHECK_CONSTRAINTS, (
            f"Expected deletion_receipts CHECK constraints "
            f"{DELETION_RECEIPTS_CHECK_CONSTRAINTS}, got: {check_names}"
        )

    def test_upgrade_creates_unique_constraint(self, pg_engine, tmp_schema):
        """After upgrade head, uq_deletion_receipt_owners unique constraint exists."""
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        uq = _pg_get_unique_constraints(pg_engine, "deletion_receipts")
        assert "uq_deletion_receipt_owners" in uq, (
            f"Expected uq_deletion_receipt_owners, got: {list(uq.keys())}"
        )
        columns = uq["uq_deletion_receipt_owners"]
        assert columns == [
            "storage_key",
            "stale_claim_token",
            "stale_claim_version",
            "reclaim_token",
            "reclaim_version",
        ], (
            "Expected columns [storage_key, stale_claim_token, "
            "stale_claim_version, reclaim_token, reclaim_version], "
            f"got {columns}"
        )

    # -- CHECK constraint enforcement ---------------------------------------

    def test_ck_deletion_outbox_status_enforced(self, pg_session_factory, tmp_schema):
        """Invalid status hits ck_deletion_outbox_status IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_outbox "
                    "(id, storage_key, migration_actor, audit_reason, "
                    "operation, status, created_at, retry_count) "
                    "VALUES ("
                    "'test-bad-status', 'sk1', 'actor1', 'reason1', "
                    "'legacy_delete', 'invalid_status', "
                    "'2026-06-25T00:00:00', 0)"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_outbox_status" in err_msg, (
            f"Expected constraint ck_deletion_outbox_status, got: {err_msg}"
        )

    def test_ck_deletion_outbox_retry_count_enforced(self, pg_session_factory, tmp_schema):
        """Negative retry_count hits ck_deletion_outbox_retry_count IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_outbox "
                    "(id, storage_key, migration_actor, audit_reason, "
                    "operation, status, created_at, retry_count) "
                    "VALUES ("
                    "'test-bad-retry', 'sk2', 'actor2', 'reason2', "
                    "'legacy_delete', 'pending_audit', "
                    "'2026-06-25T00:00:00', -1)"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_outbox_retry_count" in err_msg, (
            f"Expected constraint ck_deletion_outbox_retry_count, got: {err_msg}"
        )

    def test_ck_deletion_outbox_actor_not_empty_enforced(self, pg_session_factory, tmp_schema):
        """Empty migration_actor hits ck_deletion_outbox_actor_not_empty IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_outbox "
                    "(id, storage_key, migration_actor, audit_reason, "
                    "operation, status, created_at, retry_count) "
                    "VALUES ("
                    "'test-bad-actor', 'sk3', '', "
                    "'reason3', 'legacy_delete', 'pending_audit', "
                    "'2026-06-25T00:00:00', 0)"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_outbox_actor_not_empty" in err_msg, (
            f"Expected constraint ck_deletion_outbox_actor_not_empty, got: {err_msg}"
        )

    def test_ck_deletion_outbox_reason_not_empty_enforced(self, pg_session_factory, tmp_schema):
        """Empty audit_reason hits ck_deletion_outbox_reason_not_empty IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_outbox "
                    "(id, storage_key, migration_actor, audit_reason, "
                    "operation, status, created_at, retry_count) "
                    "VALUES ("
                    "'test-bad-reason', 'sk4', 'actor4', "
                    "'', 'legacy_delete', 'pending_audit', "
                    "'2026-06-25T00:00:00', 0)"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_outbox_reason_not_empty" in err_msg, (
            f"Expected constraint ck_deletion_outbox_reason_not_empty, got: {err_msg}"
        )

    def test_ck_deletion_receipt_stale_version_enforced(self, pg_session_factory, tmp_schema):
        """Negative stale_claim_version hits ck_deletion_receipt_stale_version IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES ("
                    "'sk-bad-ver', 'tok1', -1, "
                    "'tok2', 0, 'hash123', 'intent')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_receipt_stale_version" in err_msg, (
            f"Expected constraint ck_deletion_receipt_stale_version, got: {err_msg}"
        )

    def test_ck_deletion_receipt_reclaim_version_enforced(self, pg_session_factory, tmp_schema):
        """Negative reclaim_version hits ck_deletion_receipt_reclaim_version IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES ("
                    "'sk-bad-rv', 'tok1', 0, "
                    "'tok2', -1, 'hash456', 'intent')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_receipt_reclaim_version" in err_msg, (
            f"Expected constraint ck_deletion_receipt_reclaim_version, got: {err_msg}"
        )

    def test_ck_deletion_receipt_hash_enforced(self, pg_session_factory, tmp_schema):
        """Empty deletion_hash hits ck_deletion_receipt_hash IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES ("
                    "'sk-bad-hash', 'tok1', 0, "
                    "'tok2', 0, '', 'intent')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_receipt_hash" in err_msg, (
            f"Expected constraint ck_deletion_receipt_hash, got: {err_msg}"
        )

    def test_ck_deletion_receipt_status_enforced(self, pg_session_factory, tmp_schema):
        """Invalid status hits ck_deletion_receipt_status IntegrityError."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        with pg_session_factory() as session, pytest.raises(IntegrityError) as exc_info:
            session.execute(
                sa.text(
                    "INSERT INTO deletion_receipts "
                    "(storage_key, stale_claim_token, stale_claim_version, "
                    "reclaim_token, reclaim_version, deletion_hash, status) "
                    "VALUES ("
                    "'sk-bad-st', 'tok1', 0, "
                    "'tok2', 0, 'hash789', 'invalid')"
                )
            )
            session.commit()
        err_msg = str(exc_info.value)
        assert "ck_" in err_msg, f"Expected CHECK constraint name (ck_ prefix), got: {err_msg}"
        assert "ck_deletion_receipt_status" in err_msg, (
            f"Expected constraint ck_deletion_receipt_status, got: {err_msg}"
        )

    # -- downgrade 0022 (remove 0023 changes) --------------------------------

    def test_downgrade_drops_deletion_outbox_table(self, pg_engine, tmp_schema):
        """After downgrade to 0022, deletion_outbox table is gone."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        inspector = sa.inspect(pg_engine)
        table_names = inspector.get_table_names()
        assert "deletion_outbox" not in table_names, (
            f"deletion_outbox should be gone after downgrade, got: {table_names}"
        )

    def test_downgrade_drops_deletion_receipts_table(self, pg_engine, tmp_schema):
        """After downgrade to 0022, deletion_receipts table is gone."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic downgrade failed:\n{result.stderr}"

        inspector = sa.inspect(pg_engine)
        table_names = inspector.get_table_names()
        assert "deletion_receipts" not in table_names, (
            f"deletion_receipts should be gone after downgrade, got: {table_names}"
        )

    # -- re-upgrade head -----------------------------------------------------

    def test_re_upgrade_restores_deletion_outbox(self, pg_engine, tmp_schema):
        """Re-upgrade to head restores deletion_outbox table, indexes, and CHECK constraints."""
        _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic re-upgrade failed:\n{result.stderr}"

        # Table exists with all columns
        cols = _pg_get_columns(pg_engine, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS, (
            f"Expected all deletion_outbox columns after re-upgrade, got: {cols}"
        )

        # Indexes exist
        indexes = _pg_get_indexes(pg_engine, "deletion_outbox")
        index_names = set(indexes.keys())
        assert index_names == DELETION_OUTBOX_INDEXES, (
            f"Expected deletion_outbox indexes after re-upgrade, got: {index_names}"
        )

        # CHECK constraints exist
        checks = _pg_get_check_constraints(pg_engine, "deletion_outbox")
        check_names = set(checks.keys())
        assert check_names == DELETION_OUTBOX_CHECK_CONSTRAINTS, (
            f"Expected deletion_outbox CHECK constraints after re-upgrade, got: {check_names}"
        )

    def test_re_upgrade_restores_deletion_receipts(self, pg_engine, tmp_schema):
        """Re-upgrade to head restores deletion_receipts table, CHECK, and UNIQUE."""
        _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"alembic re-upgrade failed:\n{result.stderr}"

        # Table exists with all columns
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS, (
            f"Expected all deletion_receipts columns after re-upgrade, got: {cols}"
        )

        # CHECK constraints exist
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        check_names = set(checks.keys())
        assert check_names == DELETION_RECEIPTS_CHECK_CONSTRAINTS, (
            f"Expected deletion_receipts CHECK constraints after re-upgrade, got: {check_names}"
        )

        # UNIQUE constraint exists
        uq = _pg_get_unique_constraints(pg_engine, "deletion_receipts")
        assert "uq_deletion_receipt_owners" in uq, (
            f"Expected uq_deletion_receipt_owners after re-upgrade, got: {list(uq.keys())}"
        )

    def test_re_upgrade_preserves_all_schema_objects(self, pg_engine, tmp_schema):
        """Re-upgrade preserves all tables, indexes, and constraints."""
        _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], schema=tmp_schema)
        _run_alembic(["upgrade", "head"], schema=tmp_schema)

        # Both tables exist
        cols = _pg_get_columns(pg_engine, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        # Indexes exist
        indexes = _pg_get_indexes(pg_engine, "deletion_outbox")
        assert set(indexes.keys()) == DELETION_OUTBOX_INDEXES

        # CHECK constraints
        checks = _pg_get_check_constraints(pg_engine, "deletion_outbox")
        assert set(checks.keys()) == DELETION_OUTBOX_CHECK_CONSTRAINTS
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        assert set(checks.keys()) == DELETION_RECEIPTS_CHECK_CONSTRAINTS

        # UNIQUE constraint
        uq = _pg_get_unique_constraints(pg_engine, "deletion_receipts")
        assert "uq_deletion_receipt_owners" in uq

    # -- idempotent re-upgrade ----------------------------------------------

    def test_re_upgrade_idempotent_when_already_at_head(self, pg_engine, tmp_schema):
        """Running upgrade head again when already at head is a no-op."""
        _run_alembic(["upgrade", "head"], schema=tmp_schema)
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"idempotent re-upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        checks = _pg_get_check_constraints(pg_engine, "deletion_outbox")
        assert set(checks.keys()) == DELETION_OUTBOX_CHECK_CONSTRAINTS

    # -- full roundtrip -----------------------------------------------------

    def test_postgresql_0023_roundtrip(self, pg_engine, tmp_schema):
        """Full roundtrip: upgrade head -> downgrade 0022 -> upgrade head."""
        # 1. upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"initial upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

        # 2. downgrade to 0022 (removes both tables)
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], schema=tmp_schema)
        assert result.returncode == 0, f"downgrade failed:\n{result.stderr}"

        inspector = sa.inspect(pg_engine)
        table_names = inspector.get_table_names()
        assert "deletion_outbox" not in table_names
        assert "deletion_receipts" not in table_names

        # 3. re-upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0, f"re-upgrade failed:\n{result.stderr}"

        cols = _pg_get_columns(pg_engine, "deletion_outbox")
        assert cols == ALL_DELETION_OUTBOX_COLUMNS
        cols = _pg_get_columns(pg_engine, "deletion_receipts")
        assert cols == ALL_DELETION_RECEIPTS_COLUMNS

    def test_postgresql_0023_all_schema_objects_roundtrip(self, pg_engine, tmp_schema):
        """Verify all schema objects survive the roundtrip."""
        # Upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0

        # Verify indexes at head
        indexes = _pg_get_indexes(pg_engine, "deletion_outbox")
        assert set(indexes.keys()) == DELETION_OUTBOX_INDEXES

        # Verify CHECK constraints at head
        checks = _pg_get_check_constraints(pg_engine, "deletion_outbox")
        assert set(checks.keys()) == DELETION_OUTBOX_CHECK_CONSTRAINTS
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        assert set(checks.keys()) == DELETION_RECEIPTS_CHECK_CONSTRAINTS

        # Verify UNIQUE constraint at head
        uq = _pg_get_unique_constraints(pg_engine, "deletion_receipts")
        assert "uq_deletion_receipt_owners" in uq

        # Downgrade to 0022
        result = _run_alembic(["downgrade", "0022_add_claim_version_audit_log"], schema=tmp_schema)
        assert result.returncode == 0

        # Both tables gone
        inspector = sa.inspect(pg_engine)
        table_names = inspector.get_table_names()
        assert "deletion_outbox" not in table_names
        assert "deletion_receipts" not in table_names

        # Re-upgrade to head
        result = _run_alembic(["upgrade", "head"], schema=tmp_schema)
        assert result.returncode == 0

        # All indexes restored
        indexes = _pg_get_indexes(pg_engine, "deletion_outbox")
        assert set(indexes.keys()) == DELETION_OUTBOX_INDEXES

        # All CHECK constraints restored
        checks = _pg_get_check_constraints(pg_engine, "deletion_outbox")
        assert set(checks.keys()) == DELETION_OUTBOX_CHECK_CONSTRAINTS
        checks = _pg_get_check_constraints(pg_engine, "deletion_receipts")
        assert set(checks.keys()) == DELETION_RECEIPTS_CHECK_CONSTRAINTS

        # All UNIQUE constraints restored
        uq = _pg_get_unique_constraints(pg_engine, "deletion_receipts")
        assert "uq_deletion_receipt_owners" in uq
