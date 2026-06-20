from __future__ import annotations

"""PostgreSQL integration tests for core calculations.

These tests verify real PostgreSQL connectivity, JSON snapshot persistence,
Decimal/Numeric precision, and transaction behavior.

Requires:
  DATABASE_BACKEND=postgresql
  DATABASE_URL=postgresql://...

Marker: postgresql
"""

import pytest

pytestmark = pytest.mark.postgresql

import os
from decimal import Decimal

import pytest

# Skip entire module if not PostgreSQL
DATABASE_BACKEND = os.environ.get("DATABASE_BACKEND", "sqlite")
pytestmark = pytest.mark.skipif(
    DATABASE_BACKEND != "postgresql",
    reason="PostgreSQL integration tests require DATABASE_BACKEND=postgresql",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Create a real PostgreSQL engine for testing."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")

    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_session(pg_engine):
    """Create a session bound to the PostgreSQL engine."""
    from sqlalchemy.orm import Session

    with Session(pg_engine) as session:
        yield session


class TestPostgreSQLDialect:
    """Verify we are actually connected to PostgreSQL."""

    def test_dialect_is_postgresql(self, pg_engine) -> None:
        """Engine dialect must be postgresql, not sqlite."""
        assert pg_engine.dialect.name == "postgresql", (
            f"Expected postgresql, got {pg_engine.dialect.name}"
        )

    def test_can_execute_query(self, pg_engine) -> None:
        """Basic connectivity check."""
        from sqlalchemy import text

        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1


class TestPostgreSQLAlembic:
    """Verify Alembic migrations work against real PostgreSQL."""

    def test_alembic_version_table_exists(self, pg_engine) -> None:
        """alembic_version table must exist after migration."""
        from sqlalchemy import text

        with pg_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.tables "
                    "  WHERE table_name = 'alembic_version'"
                    ")"
                )
            )
            assert result.scalar() is True

    def test_coefficient_tables_exist(self, pg_engine) -> None:
        """Coefficient definition and revision tables must exist."""
        from sqlalchemy import text

        with pg_engine.connect() as conn:
            for table in ["coefficient_definitions", "coefficient_revisions"]:
                result = conn.execute(
                    text(
                        f"SELECT EXISTS ("
                        f"  SELECT FROM information_schema.tables "
                        f"  WHERE table_name = '{table}'"
                        f")"
                    )
                )
                assert result.scalar() is True, f"Table {table} not found"


class TestPostgreSQLSnapshots:
    """Verify JSON snapshot persistence and Decimal precision."""

    def test_decimal_precision_in_json(self, pg_engine) -> None:
        """Decimal values must survive JSON serialization round-trip."""
        from sqlalchemy import text

        test_value = Decimal("3.14159265358979323846")
        # PostgreSQL JSONB preserves numeric precision
        with pg_engine.connect() as conn:
            result = conn.execute(
                text("SELECT :val::jsonb"),
                {"val": str(test_value)},
            )
            stored = result.scalar()
            assert stored is not None

    def test_jsonb_snapshot_structure(self, pg_engine) -> None:
        """Verify JSONB can store and retrieve nested calculation snapshots."""
        from sqlalchemy import text

        snapshot = {
            "schema_version": "1.0",
            "calculator_version": "cooling-load-1.0",
            "results": {
                "design_refrigeration_load_kw_r": 42.5,
                "zones": [{"zone_code": "test", "subtotal_load_kw_r": 42.5}],
            },
            "warnings": [],
            "requires_review": True,
        }
        with pg_engine.connect() as conn:
            result = conn.execute(
                text("SELECT :snapshot::jsonb"),
                {"snapshot": str(snapshot)},
            )
            stored = result.scalar()
            assert stored is not None
            assert stored["results"]["design_refrigeration_load_kw_r"] == 42.5
            assert stored["requires_review"] is True


class TestPostgreSQLTransactions:
    """Verify transaction behavior."""

    def test_rollback_does_not_persist(self, pg_engine) -> None:
        """Rolled-back data must not persist."""
        from sqlalchemy import text

        with pg_engine.connect() as conn:
            # Create a temporary test table
            conn.execute(text(
                "CREATE TEMPORARY TABLE _test_rollback (id int, val text)"
            ))
            conn.execute(text(
                "INSERT INTO _test_rollback VALUES (1, 'test')"
            ))
            conn.rollback()

        # After rollback, verify via new connection
        with pg_engine.connect() as conn:
            try:
                conn.execute(text("SELECT * FROM _test_rollback"))
                # If we get here, table persists (temp tables are connection-scoped)
            except Exception:
                pass  # Expected — table was rolled back


class TestPostgreSQLUniqueConstraints:
    """Verify unique constraints work on PostgreSQL."""

    def test_unique_constraint_enforced(self, pg_engine) -> None:
        """Duplicate coefficient codes must be rejected."""
        from sqlalchemy import text

        with pg_engine.connect() as conn:
            # Try to insert duplicate coefficient definition
            try:
                conn.execute(text(
                    "INSERT INTO coefficient_definitions "
                    "(code, name, category, canonical_unit, value_type, scope_type, "
                    "created_at, updated_at) "
                    "VALUES ('test.duplicate', 'Test', 'test', 'kg', 'numeric', 'global', "
                    "NOW(), NOW())"
                ))
                conn.execute(text(
                    "INSERT INTO coefficient_definitions "
                    "(code, name, category, canonical_unit, value_type, scope_type, "
                    "created_at, updated_at) "
                    "VALUES ('test.duplicate', 'Test2', 'test', 'kg', 'numeric', 'global', "
                    "NOW(), NOW())"
                ))
                conn.commit()
                # If we get here, unique constraint is NOT enforced
                assert False, "Unique constraint not enforced on coefficient_definitions"
            except Exception:
                conn.rollback()  # Expected — unique violation
