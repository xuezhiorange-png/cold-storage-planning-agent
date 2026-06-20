"""PostgreSQL integration tests for core calculations.

These tests verify real PostgreSQL connectivity, JSON snapshot persistence,
Decimal/Numeric precision, and transaction behavior.

Requires:
  DATABASE_URL=postgresql+psycopg2://...

Marker: postgresql
"""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgresql


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_engine():
    """Create a real PostgreSQL engine for testing."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping PostgreSQL integration tests")

    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def pg_session(pg_engine):
    """Create a session bound to the PostgreSQL engine."""
    with Session(pg_engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Dialect tests
# ---------------------------------------------------------------------------


class TestPostgreSQLDialect:
    """Verify we are actually connected to PostgreSQL."""

    def test_dialect_is_postgresql(self, pg_engine) -> None:
        """Engine dialect must be postgresql, not sqlite."""
        assert pg_engine.dialect.name == "postgresql", (
            f"Expected postgresql, got {pg_engine.dialect.name}"
        )

    def test_can_execute_query(self, pg_engine) -> None:
        """Basic connectivity check."""
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1


# ---------------------------------------------------------------------------
# Alembic tests
# ---------------------------------------------------------------------------


class TestPostgreSQLAlembic:
    """Verify Alembic migrations work against real PostgreSQL."""

    def test_alembic_version_table_exists(self, pg_engine) -> None:
        """alembic_version table must exist after migration."""
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


# ---------------------------------------------------------------------------
# Snapshot persistence tests (real ORM)
# ---------------------------------------------------------------------------


class TestPostgreSQLSnapshots:
    """Verify JSON snapshot persistence and Decimal precision via real ORM."""

    def test_decimal_precision_in_json(self, pg_engine) -> None:
        """Decimal values survive JSON serialization round-trip."""
        test_value = Decimal("3.14159265358979323846")
        json_str = json.dumps(str(test_value))
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT CAST(:val AS JSON)"), {"val": json_str})
            stored = result.scalar()
            assert stored is not None
            assert stored == str(test_value)

    def test_json_snapshot_structure(self, pg_engine) -> None:
        """Verify JSON can store and retrieve nested calculation snapshots."""
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
                text("SELECT CAST(:snapshot AS JSON)"),
                {"snapshot": json.dumps(snapshot)},
            )
            stored = result.scalar()
            assert stored is not None
            assert stored["results"]["design_refrigeration_load_kw_r"] == 42.5
            assert stored["requires_review"] is True

    def test_project_version_snapshot_persistence(self, pg_engine) -> None:
        """Persist and read back a calculation_snapshot on a real project version."""
        project_code = f"test-pg-{uuid.uuid4().hex[:8]}"
        with pg_engine.connect() as conn:
            # Create a project (all required fields per ORM)
            project_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO projects "
                    "(id, code, name, location, product_category, status, "
                    " current_version_number, created_at, updated_at) "
                    "VALUES (:id, :code, :name, :loc, :cat, :status, 0, NOW(), NOW())"
                ),
                {
                    "id": project_id,
                    "code": project_code,
                    "name": "PG Test Project",
                    "loc": "Test Location",
                    "cat": "blueberry",
                    "status": "draft",
                },
            )

            # Create a project version with calculation_snapshot
            calculation_snapshot = {
                "cooling_load": {
                    "design_refrigeration_load_kw_r": 285.750,
                    "zones": [
                        {"zone_code": "MT-01", "subtotal_load_kw_r": 142.500},
                        {"zone_code": "LT-01", "subtotal_load_kw_r": 143.250},
                    ],
                },
                "equipment": {
                    "total_compressor_capacity_kw_r": 314.325,
                    "total_condenser_rejection_kw": 361.181,
                },
            }
            version_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO project_versions "
                    "(id, project_id, version_number, change_summary, status, "
                    " calculation_snapshot, created_at, updated_at, created_by) "
                    "VALUES (:id, :pid, 1, 'initial', 'draft', "
                    " CAST(:snapshot AS JSON), NOW(), NOW(), 'test')"
                ),
                {"id": version_id, "pid": project_id, "snapshot": json.dumps(calculation_snapshot)},
            )

            # Read it back
            row = conn.execute(
                text("SELECT calculation_snapshot FROM project_versions WHERE project_id = :pid"),
                {"pid": project_id},
            ).scalar()

            assert row is not None
            assert row["cooling_load"]["design_refrigeration_load_kw_r"] == 285.750
            assert len(row["cooling_load"]["zones"]) == 2
            assert row["equipment"]["total_compressor_capacity_kw_r"] == 314.325

            # Cleanup
            conn.execute(
                text("DELETE FROM project_versions WHERE project_id = :pid"),
                {"pid": project_id},
            )
            conn.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
            conn.commit()

    def test_coefficient_revision_persistence(self, pg_engine) -> None:
        """Persist and read back a coefficient definition + revision."""
        code = f"test.pg.coeff.{uuid.uuid4().hex[:8]}"
        with pg_engine.connect() as conn:
            # Insert definition (all required fields per ORM)
            def_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO coefficient_definitions "
                    "(id, code, name, description, category, canonical_unit, "
                    " value_type, scope_type, is_active, created_at, updated_at) "
                    "VALUES (:id, :code, 'PG Test', 'test coeff', 'test', 'ratio', "
                    " 'decimal', 'global', true, NOW(), NOW())"
                ),
                {"id": def_id, "code": code},
            )

            # Insert revision (value_decimal is String(50) in ORM)
            rev_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO coefficient_revisions "
                    "(id, coefficient_definition_id, revision_number, unit, status, "
                    " source_type, value_decimal, created_by, created_at) "
                    "VALUES (:id, :did, 1, 'ratio', 'approved', 'demo', "
                    " :val, 'test', NOW())"
                ),
                {"id": rev_id, "did": def_id, "val": "3.14159"},
            )

            # Read back — value_decimal is stored as String
            val = conn.execute(
                text(
                    "SELECT value_decimal FROM coefficient_revisions "
                    "WHERE coefficient_definition_id = :did"
                ),
                {"did": def_id},
            ).scalar()

            assert val is not None
            # Precision check via Decimal comparison
            assert Decimal(val) == Decimal("3.14159")

            # Cleanup
            conn.execute(
                text("DELETE FROM coefficient_revisions WHERE coefficient_definition_id = :did"),
                {"did": def_id},
            )
            conn.execute(
                text("DELETE FROM coefficient_definitions WHERE id = :did"),
                {"did": def_id},
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Transaction tests
# ---------------------------------------------------------------------------


class TestPostgreSQLTransactions:
    """Verify transaction behavior on real tables."""

    def test_rollback_does_not_persist(self, pg_engine) -> None:
        """Rolled-back project data must not persist."""
        project_code = f"test-rb-{uuid.uuid4().hex[:8]}"
        project_id = str(uuid.uuid4())

        # Insert and rollback
        with pg_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO projects "
                    "(id, code, name, location, product_category, status, "
                    " current_version_number, created_at, updated_at) "
                    "VALUES (:id, :code, 'RB Test', 'loc', 'cat', 'draft', 0, NOW(), NOW())"
                ),
                {"id": project_id, "code": project_code},
            )
            conn.rollback()

        # Verify it does NOT exist
        with pg_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM projects WHERE code = :code"),
                {"code": project_code},
            ).scalar()
            assert count == 0, f"Rolled-back project still exists (count={count})"

    def test_committed_data_persists(self, pg_engine) -> None:
        """Committed data persists across connections."""
        project_code = f"test-cm-{uuid.uuid4().hex[:8]}"
        project_id = str(uuid.uuid4())

        with pg_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO projects "
                    "(id, code, name, location, product_category, status, "
                    " current_version_number, created_at, updated_at) "
                    "VALUES (:id, :code, 'CM Test', 'loc', 'cat', 'draft', 0, NOW(), NOW())"
                ),
                {"id": project_id, "code": project_code},
            )
            conn.commit()

        # Verify it exists in a new connection
        with pg_engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM projects WHERE code = :code"),
                {"code": project_code},
            ).scalar()
            assert count == 1, f"Committed project not found (count={count})"

        # Cleanup
        with pg_engine.connect() as conn:
            conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
            conn.commit()


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------


class TestPostgreSQLConstraints:
    """Verify constraints work on PostgreSQL."""

    def test_unique_constraint_enforced(self, pg_engine) -> None:
        """Duplicate coefficient codes must be rejected."""
        code = f"test.unique.{uuid.uuid4().hex[:8]}"
        def_id_1 = str(uuid.uuid4())
        def_id_2 = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO coefficient_definitions "
                    "(id, code, name, description, category, canonical_unit, "
                    " value_type, scope_type, is_active, created_at, updated_at) "
                    "VALUES (:id, :code, 'T1', 'd', 'test', 'kg', "
                    " 'decimal', 'global', true, NOW(), NOW())"
                ),
                {"id": def_id_1, "code": code},
            )
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO coefficient_definitions "
                        "(id, code, name, description, category, canonical_unit, "
                        " value_type, scope_type, is_active, created_at, updated_at) "
                        "VALUES (:id, :code, 'T2', 'd', 'test', 'kg', "
                        " 'decimal', 'global', true, NOW(), NOW())"
                    ),
                    {"id": def_id_2, "code": code},
                )
                conn.commit()
            conn.rollback()

        # Cleanup
        with pg_engine.connect() as conn:
            conn.execute(
                text("DELETE FROM coefficient_definitions WHERE code = :code"),
                {"code": code},
            )
            conn.commit()

    def test_foreign_key_constraint(self, pg_engine) -> None:
        """Revision with invalid definition_id must be rejected."""
        fake_id = str(uuid.uuid4())
        rev_id = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO coefficient_revisions "
                        "(id, coefficient_definition_id, revision_number, unit, "
                        " status, source_type, created_by, created_at) "
                        "VALUES (:id, :did, 1, 'ratio', 'draft', 'demo', "
                        " 'test', NOW())"
                    ),
                    {"id": rev_id, "did": fake_id},
                )
                conn.commit()
            conn.rollback()
