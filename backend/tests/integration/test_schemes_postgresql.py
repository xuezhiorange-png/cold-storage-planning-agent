"""PostgreSQL integration tests for Task 6 scheme tables.

Verifies schema existence, JSONB column round-trips, Numeric precision,
foreign-key constraints, and unique constraints for:
  - scheme_weight_sets
  - scheme_runs
  - scheme_candidates

Requires: DATABASE_URL=postgresql+psycopg2://...
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
# Helpers
# ---------------------------------------------------------------------------


def _insert_project_and_version(conn, project_id: str, version_id: str) -> None:
    """Insert a project and version required for FK references."""
    conn.execute(
        text(
            "INSERT INTO projects "
            "(id, code, name, location, product_category, status, "
            " current_version_number, created_at, updated_at) "
            "VALUES (:id, :code, :name, :loc, :cat, :status, 0, NOW(), NOW())"
        ),
        {
            "id": project_id,
            "code": f"scheme-pg-{project_id[:8]}",
            "name": "PG Test Project",
            "loc": "Test Location",
            "cat": "blueberry",
            "status": "draft",
        },
    )
    conn.execute(
        text(
            "INSERT INTO project_versions "
            "(id, project_id, version_number, change_summary, status, "
            " calculation_snapshot, input_snapshot, assumption_snapshot, "
            " created_at, updated_at, created_by) "
            "VALUES (:id, :pid, 1, 'initial', 'draft', "
            " CAST('{}' AS JSON), CAST('{}' AS JSON), CAST('{}' AS JSON), "
            " NOW(), NOW(), 'test')"
        ),
        {"id": version_id, "pid": project_id},
    )


def _insert_scheme_run(
    conn,
    run_id: str,
    project_id: str,
    version_id: str,
    *,
    status: str = "pending",
) -> None:
    """Insert a scheme_runs row."""
    conn.execute(
        text(
            "INSERT INTO scheme_runs "
            "(id, project_id, project_version_id, weight_set_id, status, "
            " generator_version, source_snapshot_hash, "
            " input_snapshot, assumption_snapshot, comparison_snapshot, "
            " candidates_snapshot, requires_review, warning_messages, "
            " created_at, completed_at) "
            "VALUES (:id, :pid, :vid, :wid, :status, "
            " '1.0.0', 'test-hash', "
            " CAST('{}' AS JSON), CAST('{}' AS JSON), CAST('{}' AS JSON), "
            " CAST('{}' AS JSON), true, CAST('[]' AS JSON), "
            " NOW(), :completed_at)"
        ),
        {
            "id": run_id,
            "pid": project_id,
            "vid": version_id,
            "wid": f"ws-{uuid.uuid4().hex[:8]}",
            "status": status,
            "completed_at": None if status == "pending" else "NOW()",
        },
    )


def _cleanup_project(conn, project_id: str) -> None:
    """Clean up scheme and project data for a given project_id."""
    runs = conn.execute(
        text("SELECT id FROM scheme_runs WHERE project_id = :pid"),
        {"pid": project_id},
    ).fetchall()
    for (run_id,) in runs:
        conn.execute(
            text("DELETE FROM scheme_candidates WHERE scheme_run_id = :rid"),
            {"rid": run_id},
        )
    conn.execute(
        text("DELETE FROM scheme_runs WHERE project_id = :pid"),
        {"pid": project_id},
    )
    conn.execute(
        text("DELETE FROM project_versions WHERE project_id = :pid"),
        {"pid": project_id},
    )
    conn.execute(
        text("DELETE FROM projects WHERE id = :pid"),
        {"pid": project_id},
    )


def _insert_candidate(conn, run_id: str, candidate_id: str) -> None:
    """Insert a minimal scheme_candidates row."""
    conn.execute(
        text(
            "INSERT INTO scheme_candidates "
            "(id, scheme_run_id, scheme_code, profile_code, "
            " feasible, "
            " score_breakdown_snapshot, constraint_results, "
            " result_snapshot, created_at) "
            "VALUES (:id, :rid, 'balanced', 'balanced', "
            " true, "
            " CAST('{}' AS JSON), CAST('[]' AS JSON), "
            " CAST('{}' AS JSON), NOW())"
        ),
        {"id": candidate_id, "rid": run_id},
    )


# ---------------------------------------------------------------------------
# Dialect tests
# ---------------------------------------------------------------------------


class TestSchemeDialect:
    """Verify we are actually connected to PostgreSQL."""

    def test_dialect_is_postgresql(self, pg_engine) -> None:
        """Engine dialect must be postgresql."""
        assert pg_engine.dialect.name == "postgresql", (
            f"Expected postgresql, got {pg_engine.dialect.name}"
        )


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


class TestSchemeMigrations:
    """Verify Alembic migrations created scheme tables and columns."""

    def test_migration_0005_scheme_tables_exist(self, pg_engine) -> None:
        """scheme_weight_sets, scheme_runs, scheme_candidates must exist."""
        expected = ["scheme_weight_sets", "scheme_runs", "scheme_candidates"]
        with pg_engine.connect() as conn:
            for table in expected:
                result = conn.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT FROM information_schema.tables "
                        f"  WHERE table_name = '{table}'"
                        ")"
                    )
                )
                assert result.scalar() is True, f"Table {table} not found"

    def test_migration_0006_columns_exist(self, pg_engine) -> None:
        """scheme_candidates must have score_breakdown_snapshot,
        constraint_results, and total_score columns with correct type."""
        with pg_engine.connect() as conn:
            for col in ["score_breakdown_snapshot", "constraint_results"]:
                result = conn.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT FROM information_schema.columns "
                        "  WHERE table_name = 'scheme_candidates' "
                        f" AND column_name = '{col}'"
                        ")"
                    )
                )
                assert result.scalar() is True, f"Column {col} not found"

            result = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'scheme_candidates' "
                    "AND column_name = 'total_score'"
                )
            )
            row = result.scalar()
            assert row == "numeric", f"Expected 'numeric', got '{row}'"

    def test_three_scheme_tables_count(self, pg_engine) -> None:
        """At least the 3 base scheme tables exist (+ revision table from migration 0026)."""
        with pg_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND table_name LIKE 'scheme_%'"
                )
            )
            count = result.scalar()
            assert count >= 3, f"Expected at least 3 scheme tables, got {count}"


# ---------------------------------------------------------------------------
# JSONB column tests
# ---------------------------------------------------------------------------


class TestSchemeJsonbColumns:
    """Verify JSONB column persistence on scheme_candidates and scheme_runs."""

    def test_jsonb_score_breakdown(self, pg_engine) -> None:
        """Insert a candidate with score_breakdown_snapshot JSONB, read back."""
        project_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        candidate_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_project_and_version(conn, project_id, version_id)
                _insert_scheme_run(conn, run_id, project_id, version_id)

                breakdown = {
                    "total_area_m2": 0.85,
                    "investment_cny": 0.72,
                    "total_position_count": 0.90,
                }
                conn.execute(
                    text(
                        "INSERT INTO scheme_candidates "
                        "(id, scheme_run_id, scheme_code, profile_code, "
                        " feasible, score_breakdown_snapshot, constraint_results, "
                        " result_snapshot, created_at) "
                        "VALUES (:id, :rid, 'balanced', 'balanced', "
                        " true, CAST(:breakdown AS JSON), CAST('[]' AS JSON), "
                        " CAST('{}' AS JSON), NOW())"
                    ),
                    {
                        "id": candidate_id,
                        "rid": run_id,
                        "breakdown": json.dumps(breakdown),
                    },
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT score_breakdown_snapshot FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                ).scalar()
                assert row is not None
                assert row["total_area_m2"] == 0.85
                assert row["investment_cny"] == 0.72
                assert row["total_position_count"] == 0.90
        finally:
            with pg_engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                )
                _cleanup_project(conn, project_id)
                conn.commit()

    def test_jsonb_constraint_results(self, pg_engine) -> None:
        """Insert with constraint_results JSONB array, read back."""
        project_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        candidate_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_project_and_version(conn, project_id, version_id)
                _insert_scheme_run(conn, run_id, project_id, version_id)

                constraints = [
                    {
                        "criterion_code": "min_area_m2",
                        "passed": True,
                        "actual": 880.0,
                    },
                    {
                        "criterion_code": "max_investment_cny",
                        "passed": False,
                        "actual": 12000000,
                    },
                ]
                conn.execute(
                    text(
                        "INSERT INTO scheme_candidates "
                        "(id, scheme_run_id, scheme_code, profile_code, "
                        " feasible, score_breakdown_snapshot, constraint_results, "
                        " result_snapshot, created_at) "
                        "VALUES (:id, :rid, 'balanced', 'balanced', "
                        " true, CAST('{}' AS JSON), CAST(:constraints AS JSON), "
                        " CAST('{}' AS JSON), NOW())"
                    ),
                    {
                        "id": candidate_id,
                        "rid": run_id,
                        "constraints": json.dumps(constraints),
                    },
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT constraint_results FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                ).scalar()
                assert row is not None
                assert len(row) == 2
                assert row[0]["criterion_code"] == "min_area_m2"
                assert row[0]["passed"] is True
                assert row[1]["passed"] is False
        finally:
            with pg_engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                )
                _cleanup_project(conn, project_id)
                conn.commit()

    def test_jsonb_input_snapshot_on_run(self, pg_engine) -> None:
        """Insert a scheme_run with a rich input_snapshot JSONB, read back."""
        project_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_project_and_version(conn, project_id, version_id)

                input_snapshot = {
                    "project_id": project_id,
                    "cooling_load_kw_r": 42.5,
                    "equipment": ["compressor-A", "condenser-B"],
                }
                conn.execute(
                    text(
                        "INSERT INTO scheme_runs "
                        "(id, project_id, project_version_id, weight_set_id, "
                        " status, generator_version, source_snapshot_hash, "
                        " input_snapshot, assumption_snapshot, comparison_snapshot, "
                        " candidates_snapshot, requires_review, warning_messages, "
                        " created_at, completed_at) "
                        "VALUES (:id, :pid, :vid, :wid, "
                        " 'pending', '1.0.0', 'snap-hash', "
                        " CAST(:snap AS JSON), CAST('{}' AS JSON), "
                        " CAST('{}' AS JSON), CAST('{}' AS JSON), "
                        " true, CAST('[]' AS JSON), NOW(), NULL)"
                    ),
                    {
                        "id": run_id,
                        "pid": project_id,
                        "vid": version_id,
                        "wid": f"ws-{uuid.uuid4().hex[:8]}",
                        "snap": json.dumps(input_snapshot),
                    },
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT input_snapshot FROM scheme_runs WHERE id = :id"),
                    {"id": run_id},
                ).scalar()
                assert row is not None
                assert row["cooling_load_kw_r"] == 42.5
                assert len(row["equipment"]) == 2
                assert row["project_id"] == project_id
        finally:
            with pg_engine.connect() as conn:
                _cleanup_project(conn, project_id)
                conn.commit()


# ---------------------------------------------------------------------------
# Numeric score tests
# ---------------------------------------------------------------------------


class TestSchemeNumericScore:
    """Verify numeric/Decimal precision in scheme_candidates."""

    def test_numeric_total_score(self, pg_engine) -> None:
        """Insert with total_score=Decimal('85.123'), read back exactly."""
        project_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        candidate_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_project_and_version(conn, project_id, version_id)
                _insert_scheme_run(conn, run_id, project_id, version_id)

                conn.execute(
                    text(
                        "INSERT INTO scheme_candidates "
                        "(id, scheme_run_id, scheme_code, profile_code, "
                        " feasible, total_score, "
                        " score_breakdown_snapshot, constraint_results, "
                        " result_snapshot, created_at) "
                        "VALUES (:id, :rid, 'balanced', 'balanced', "
                        " true, 85.123, "
                        " CAST('{}' AS JSON), CAST('[]' AS JSON), "
                        " CAST('{}' AS JSON), NOW())"
                    ),
                    {"id": candidate_id, "rid": run_id},
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT total_score::text FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                ).scalar()
                assert row is not None
                assert Decimal(row) == Decimal("85.123")
        finally:
            with pg_engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                )
                _cleanup_project(conn, project_id)
                conn.commit()

    def test_rank_column(self, pg_engine) -> None:
        """Insert with rank=1, read back."""
        project_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        candidate_id = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_project_and_version(conn, project_id, version_id)
                _insert_scheme_run(conn, run_id, project_id, version_id)

                conn.execute(
                    text(
                        "INSERT INTO scheme_candidates "
                        "(id, scheme_run_id, scheme_code, profile_code, "
                        " feasible, rank, "
                        " score_breakdown_snapshot, constraint_results, "
                        " result_snapshot, created_at) "
                        "VALUES (:id, :rid, 'balanced', 'balanced', "
                        " true, 1, "
                        " CAST('{}' AS JSON), CAST('[]' AS JSON), "
                        " CAST('{}' AS JSON), NOW())"
                    ),
                    {"id": candidate_id, "rid": run_id},
                )
                conn.commit()

                row = conn.execute(
                    text("SELECT rank FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                ).scalar()
                assert row == 1
        finally:
            with pg_engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM scheme_candidates WHERE id = :id"),
                    {"id": candidate_id},
                )
                _cleanup_project(conn, project_id)
                conn.commit()


# ---------------------------------------------------------------------------
# Foreign key constraint tests
# ---------------------------------------------------------------------------


class TestSchemeForeignKeys:
    """Verify FK constraints on scheme tables."""

    def test_project_version_fk(self, pg_engine) -> None:
        """scheme_runs.project_id references projects.id;
        insert with invalid project_id raises IntegrityError."""
        run_id = str(uuid.uuid4())
        fake_project_id = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError):
                _insert_scheme_run(conn, run_id, fake_project_id, "fake-version-id")
                conn.commit()
            conn.rollback()

    def test_run_candidate_fk(self, pg_engine) -> None:
        """scheme_candidates.scheme_run_id references scheme_runs.id;
        insert with invalid run_id raises IntegrityError."""
        candidate_id = str(uuid.uuid4())
        fake_run_id = str(uuid.uuid4())
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        "INSERT INTO scheme_candidates "
                        "(id, scheme_run_id, scheme_code, profile_code, "
                        " feasible, "
                        " score_breakdown_snapshot, constraint_results, "
                        " result_snapshot, created_at) "
                        "VALUES (:id, :rid, 'balanced', 'balanced', "
                        " true, "
                        " CAST('{}' AS JSON), CAST('[]' AS JSON), "
                        " CAST('{}' AS JSON), NOW())"
                    ),
                    {"id": candidate_id, "rid": fake_run_id},
                )
                conn.commit()
            conn.rollback()


# ---------------------------------------------------------------------------
# Unique constraint tests
# ---------------------------------------------------------------------------


class TestSchemeUniqueConstraints:
    """Verify unique constraints on scheme tables."""

    def test_unique_run_scheme(self, pg_engine) -> None:
        """Duplicate (scheme_run_id, scheme_code) raises IntegrityError."""
        project_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        cand_id_1 = str(uuid.uuid4())
        cand_id_2 = str(uuid.uuid4())
        try:
            with pg_engine.connect() as conn:
                _insert_project_and_version(conn, project_id, version_id)
                _insert_scheme_run(conn, run_id, project_id, version_id)

                conn.execute(
                    text(
                        "INSERT INTO scheme_candidates "
                        "(id, scheme_run_id, scheme_code, profile_code, "
                        " feasible, "
                        " score_breakdown_snapshot, constraint_results, "
                        " result_snapshot, created_at) "
                        "VALUES (:id, :rid, 'balanced', 'balanced', "
                        " true, "
                        " CAST('{}' AS JSON), CAST('[]' AS JSON), "
                        " CAST('{}' AS JSON), NOW())"
                    ),
                    {"id": cand_id_1, "rid": run_id},
                )
                conn.commit()

                with pytest.raises(IntegrityError):
                    conn.execute(
                        text(
                            "INSERT INTO scheme_candidates "
                            "(id, scheme_run_id, scheme_code, profile_code, "
                            " feasible, "
                            " score_breakdown_snapshot, constraint_results, "
                            " result_snapshot, created_at) "
                            "VALUES (:id, :rid, 'balanced', 'balanced', "
                            " true, "
                            " CAST('{}' AS JSON), CAST('[]' AS JSON), "
                            " CAST('{}' AS JSON), NOW())"
                        ),
                        {"id": cand_id_2, "rid": run_id},
                    )
                    conn.commit()
                conn.rollback()
        finally:
            with pg_engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM scheme_candidates WHERE id = :id1 OR id = :id2"),
                    {"id1": cand_id_1, "id2": cand_id_2},
                )
                _cleanup_project(conn, project_id)
                conn.commit()

    def test_unique_weight_set_code_revision(self, pg_engine) -> None:
        """Duplicate (code, revision) on scheme_weight_sets raises IntegrityError."""
        ws_id_1 = str(uuid.uuid4())
        ws_id_2 = str(uuid.uuid4())
        code = f"ws-test-{uuid.uuid4().hex[:8]}"
        try:
            with pg_engine.connect() as conn:
                criteria = [
                    {"code": "area", "weight": 0.4},
                    {"code": "cost", "weight": 0.6},
                ]
                conn.execute(
                    text(
                        "INSERT INTO scheme_weight_sets "
                        "(id, code, name, revision, status, source_type, "
                        " criteria, requires_review, created_at, approved_at) "
                        "VALUES (:id, :code, 'Test WS', 1, 'draft', 'manual', "
                        " CAST(:criteria AS JSON), true, NOW(), NULL)"
                    ),
                    {"id": ws_id_1, "code": code, "criteria": json.dumps(criteria)},
                )
                conn.commit()

                with pytest.raises(IntegrityError):
                    conn.execute(
                        text(
                            "INSERT INTO scheme_weight_sets "
                            "(id, code, name, revision, status, source_type, "
                            " criteria, requires_review, created_at, approved_at) "
                            "VALUES (:id, :code, 'Test WS Dup', 1, 'draft', 'manual', "
                            " CAST(:criteria AS JSON), true, NOW(), NULL)"
                        ),
                        {
                            "id": ws_id_2,
                            "code": code,
                            "criteria": json.dumps(criteria),
                        },
                    )
                    conn.commit()
                conn.rollback()
        finally:
            with pg_engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM scheme_weight_sets WHERE id = :id1 OR id = :id2"),
                    {"id1": ws_id_1, "id2": ws_id_2},
                )
                conn.commit()


# ---------------------------------------------------------------------------
# Weight set CRUD tests
# ---------------------------------------------------------------------------


class TestSchemeWeightSets:
    """Verify scheme_weight_sets table CRUD and constraints."""

    def test_weight_set_insert_and_read(self, pg_engine) -> None:
        """Insert a weight set row with JSON criteria, read back."""
        ws_id = str(uuid.uuid4())
        code = f"ws-crud-{uuid.uuid4().hex[:8]}"
        try:
            with pg_engine.connect() as conn:
                criteria = [
                    {"code": "total_area_m2", "weight": 0.4},
                    {"code": "investment_cny", "weight": 0.35},
                    {"code": "position_count", "weight": 0.25},
                ]
                conn.execute(
                    text(
                        "INSERT INTO scheme_weight_sets "
                        "(id, code, name, revision, status, source_type, "
                        " criteria, requires_review, created_at, approved_at) "
                        "VALUES (:id, :code, 'Default Blueberry', 1, 'approved', "
                        " 'demo', CAST(:criteria AS JSON), false, NOW(), NOW())"
                    ),
                    {"id": ws_id, "code": code, "criteria": json.dumps(criteria)},
                )
                conn.commit()

                row = conn.execute(
                    text(
                        "SELECT id, code, name, revision, status, "
                        " source_type, criteria, requires_review "
                        "FROM scheme_weight_sets WHERE id = :id"
                    ),
                    {"id": ws_id},
                ).fetchone()
                assert row is not None
                assert row[1] == code
                assert row[2] == "Default Blueberry"
                assert row[3] == 1
                assert row[4] == "approved"
                assert row[5] == "demo"
                assert len(row[6]) == 3
                assert row[6][0]["code"] == "total_area_m2"
                assert row[6][0]["weight"] == 0.4
                assert row[7] is False
        finally:
            with pg_engine.connect() as conn:
                conn.execute(
                    text("DELETE FROM scheme_weight_sets WHERE id = :id"),
                    {"id": ws_id},
                )
                conn.commit()
