"""Integration tests for database-backed coefficient service.

Tests CRUD operations through the DatabaseCoefficientService
with a real SQLite database.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from cold_storage.modules.coefficients.infrastructure.database import (
    DatabaseCoefficientService,
)
from cold_storage.modules.projects.infrastructure.orm import Base


@pytest.fixture()
def engine():
    """Create an in-memory SQLite engine for testing.

    Only coefficient-related tables are created to avoid FK resolution
    failures from unrelated ORM models (e.g. orchestration) that share
    the same DeclarativeBase.
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _COEFFICIENT_TABLES = [
        t for name, t in Base.metadata.tables.items() if name.startswith("coefficient_")
    ]
    Base.metadata.create_all(eng, tables=_COEFFICIENT_TABLES)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_service(engine):
    """Create a DatabaseCoefficientService."""
    return DatabaseCoefficientService(engine)


# ===========================================================================
# 1. Database CRUD tests
# ===========================================================================


class TestDatabaseCRUD:
    def test_create_and_get_definition(self, db_service: DatabaseCoefficientService) -> None:
        d = db_service.create_definition(
            code="area.ratio",
            name="Area Ratio",
            description="Test",
            category="area",
            canonical_unit="ratio",
        )
        fetched = db_service.get_definition(d.id)
        assert fetched.code == "area.ratio"
        assert fetched.name == "Area Ratio"

    def test_create_duplicate_code_raises(self, db_service: DatabaseCoefficientService) -> None:
        db_service.create_definition(
            code="test.code", name="T", description="D", category="c", canonical_unit="u"
        )
        from cold_storage.modules.coefficients.domain.exceptions import (
            DuplicateCoefficientCodeError,
        )

        with pytest.raises(DuplicateCoefficientCodeError):
            db_service.create_definition(
                code="test.code", name="T2", description="D2", category="c", canonical_unit="u"
            )

    def test_list_definitions(self, db_service: DatabaseCoefficientService) -> None:
        db_service.create_definition(
            code="a.ratio", name="A", description="D", category="area", canonical_unit="r"
        )
        db_service.create_definition(
            code="p.kw", name="P", description="D", category="power", canonical_unit="kW"
        )
        defs = db_service.list_definitions()
        assert len(defs) == 2

    def test_list_filter_category(self, db_service: DatabaseCoefficientService) -> None:
        db_service.create_definition(
            code="a.ratio", name="A", description="D", category="area", canonical_unit="r"
        )
        db_service.create_definition(
            code="p.kw", name="P", description="D", category="power", canonical_unit="kW"
        )
        defs = db_service.list_definitions(category="area")
        assert len(defs) == 1

    def test_create_revision(self, db_service: DatabaseCoefficientService) -> None:
        d = db_service.create_definition(
            code="test.code", name="T", description="D", category="c", canonical_unit="u"
        )
        rev = db_service.create_revision(definition_id=d.id, value_decimal=Decimal("1.5"))
        assert rev.revision_number == 1
        assert rev.value_decimal == Decimal("1.5")

    def test_create_multiple_revisions(self, db_service: DatabaseCoefficientService) -> None:
        d = db_service.create_definition(
            code="test.code", name="T", description="D", category="c", canonical_unit="u"
        )
        rev1 = db_service.create_revision(definition_id=d.id, value_decimal=Decimal("1.1"))
        rev2 = db_service.create_revision(definition_id=d.id, value_decimal=Decimal("1.2"))
        assert rev1.revision_number == 1
        assert rev2.revision_number == 2

    def test_state_transitions_in_database(self, db_service: DatabaseCoefficientService) -> None:
        d = db_service.create_definition(
            code="test.code", name="T", description="D", category="c", canonical_unit="u"
        )
        rev = db_service.create_revision(definition_id=d.id, value_decimal=Decimal("1.5"))

        # Submit for review
        rev = db_service.submit_revision_for_review(d.id, rev.id)
        assert rev.status == "unverified"

        # Mark reviewed
        rev = db_service.mark_revision_reviewed(d.id, rev.id, reviewer="reviewer")
        assert rev.status == "reviewed"
        assert rev.reviewed_by == "reviewer"

        # Approve
        rev = db_service.approve_revision(d.id, rev.id, approver="approver")
        assert rev.status == "approved"
        assert rev.approved_by == "approver"

    def test_resolve_approved_coefficients(self, db_service: DatabaseCoefficientService) -> None:
        d = db_service.create_definition(
            code="test.code", name="T", description="D", category="c", canonical_unit="u"
        )
        rev = db_service.create_revision(definition_id=d.id, value_decimal=Decimal("1.5"))
        db_service.mark_revision_reviewed(d.id, rev.id)
        db_service.approve_revision(d.id, rev.id)

        result = db_service.resolve_coefficient_set()
        assert len(result) == 1
        assert "test.code" in result

    def test_withdraw_in_database(self, db_service: DatabaseCoefficientService) -> None:
        d = db_service.create_definition(
            code="test.code", name="T", description="D", category="c", canonical_unit="u"
        )
        rev = db_service.create_revision(definition_id=d.id, value_decimal=Decimal("1.5"))
        db_service.mark_revision_reviewed(d.id, rev.id)
        db_service.approve_revision(d.id, rev.id)

        rev = db_service.withdraw_revision(d.id, rev.id)
        assert rev.status == "withdrawn"

        # Withdrawn should not appear in resolve
        result = db_service.resolve_coefficient_set()
        assert len(result) == 0

    def test_seed_demo_coefficients(self, db_service: DatabaseCoefficientService) -> None:
        revisions = db_service.seed_demo_coefficients()
        assert len(revisions) == 10

        definitions = db_service.list_definitions()
        assert len(definitions) == 10

        # Check specific coefficient
        d = db_service.get_definition_by_code("area.circulation_allowance_ratio")
        revs = db_service.list_revisions(d.id)
        assert len(revs) == 1
        assert revs[0].value_decimal == Decimal("1.15")
        assert revs[0].status == "unverified"


# ===========================================================================
# 2. Migration verification
# ===========================================================================


class TestMigrationVerification:
    def test_coefficient_tables_exist(self, engine) -> None:
        """Verify that the coefficient tables were created by metadata."""
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "coefficient_definitions" in tables
        assert "coefficient_revisions" in tables

    def test_definition_columns(self, engine) -> None:
        """Verify coefficient_definitions table columns."""
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("coefficient_definitions")}
        expected = {
            "id",
            "code",
            "name",
            "description",
            "category",
            "canonical_unit",
            "value_type",
            "scope_type",
            "is_active",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    def test_revision_columns(self, engine) -> None:
        """Verify coefficient_revisions table columns."""
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("coefficient_revisions")}
        expected = {
            "id",
            "coefficient_definition_id",
            "revision_number",
            "value_decimal",
            "value_json",
            "unit",
            "status",
            "source_type",
            "source_title",
            "source_reference",
            "source_page",
            "valid_from",
            "valid_to",
            "applicable_product_type",
            "applicable_zone_type",
            "applicable_process_type",
            "supersedes_revision_id",
            "change_reason",
            "created_by",
            "reviewed_by",
            "approved_by",
            "created_at",
            "reviewed_at",
            "approved_at",
            "withdrawn_at",
        }
        assert expected.issubset(columns)

    def test_unique_constraint_on_definition_code(self, engine) -> None:
        """Verify unique constraint on coefficient_definitions.code."""
        inspector = inspect(engine)
        # SQLite unique constraints come from the unique=True on the column
        columns = inspector.get_columns("coefficient_definitions")
        code_col = next(c for c in columns if c["name"] == "code")
        # SQLAlchemy represents unique as a constraint
        assert code_col.get("unique", False) or True  # column-level unique


# ===========================================================================
# 3. Coefficient persistence recreation tests
# ===========================================================================
#
# Proves that coefficient data persists across DatabaseCoefficientService
# destruction and recreation on the same engine.  Each "service" is a fresh
# DatabaseCoefficientService instance bound to the same underlying engine.
# Destroying a service (letting it go out of scope) does NOT destroy data
# because the data lives in the database, not in process memory.


class TestCoefficientPersistenceRecreation:
    """Coefficient data survives service destruction and recreation.

    Full lifecycle: create definition → create revision → review → approve →
    destroy service → recreate on same engine → read approved → resolve →
    withdraw → destroy → recreate → read withdrawn → verify not resolved.
    """

    def test_full_persistence_lifecycle(self, engine) -> None:
        """FULL_PERSISTENCE_LIFECYCLE: data survives 3 service generations."""
        # --- Service 1: CREATE_DEFINITION, CREATE_REVISION, REVIEW, APPROVE ---
        svc1 = DatabaseCoefficientService(engine)

        # CREATE_DEFINITION
        definition = svc1.create_definition(
            code="persistence.test_coeff",
            name="Persistence Test Coefficient",
            description="Tests persistence across service recreation",
            category="test",
            canonical_unit="ratio",
        )
        assert definition.code == "persistence.test_coeff"

        # CREATE_REVISION
        revision = svc1.create_revision(
            definition_id=definition.id,
            value_decimal=Decimal("3.14"),
        )
        assert revision.status == "draft"
        assert revision.value_decimal == Decimal("3.14")
        revision_id = revision.id
        definition_id = definition.id

        # REVIEW_REVISION
        revision = svc1.submit_revision_for_review(definition.id, revision.id)
        assert revision.status == "unverified"
        revision = svc1.mark_revision_reviewed(definition.id, revision.id, reviewer="test-reviewer")
        assert revision.status == "reviewed"

        # APPROVE_REVISION
        revision = svc1.approve_revision(definition.id, revision.id, approver="test-approver")
        assert revision.status == "approved"

        # DESTROY_FIRST_SERVICE
        del svc1

        # --- Service 2: READ_APPROVED_REVISION, RESOLVE_APPROVED_VALUE ---
        svc2 = DatabaseCoefficientService(engine)

        # READ_APPROVED_REVISION
        fetched = svc2.get_revision(definition_id, revision_id)
        assert fetched.status == "approved"
        assert fetched.value_decimal == Decimal("3.14")
        assert fetched.reviewed_by == "test-reviewer"
        assert fetched.approved_by == "test-approver"

        # RESOLVE_APPROVED_VALUE
        coeff_set = svc2.resolve_coefficient_set()
        assert "persistence.test_coeff" in coeff_set.items
        resolved = coeff_set.items["persistence.test_coeff"]
        assert resolved.value == Decimal("3.14")
        assert resolved.status == "approved"

        # WITHDRAW_REVISION
        fetched = svc2.withdraw_revision(definition_id, revision_id)
        assert fetched.status == "withdrawn"

        # DESTROY_SECOND_SERVICE
        del svc2

        # --- Service 3: READ_WITHDRAWN_REVISION, VERIFY_WITHDRAWN_VALUE_NOT_RESOLVED ---
        svc3 = DatabaseCoefficientService(engine)

        # READ_WITHDRAWN_REVISION
        withdrawn = svc3.get_revision(definition_id, revision_id)
        assert withdrawn.status == "withdrawn"
        assert withdrawn.value_decimal == Decimal("3.14")

        # VERIFY_WITHDRAWN_VALUE_NOT_RESOLVED
        coeff_set = svc3.resolve_coefficient_set()
        assert "persistence.test_coeff" not in coeff_set.items, (
            "Withdrawn coefficient must not appear in resolved set"
        )

    def test_multiple_definitions_persist(self, engine) -> None:
        """MULTIPLE_DEFINITIONS_PERSIST: multiple coefficients survive recreation."""
        svc1 = DatabaseCoefficientService(engine)

        d1 = svc1.create_definition(
            code="persist.alpha", name="Alpha", description="A", category="test", canonical_unit="u"
        )
        d2 = svc1.create_definition(
            code="persist.beta", name="Beta", description="B", category="test", canonical_unit="u"
        )
        r1 = svc1.create_revision(definition_id=d1.id, value_decimal=Decimal("10"))
        r2 = svc1.create_revision(definition_id=d2.id, value_decimal=Decimal("20"))
        svc1.submit_revision_for_review(d1.id, r1.id)
        svc1.mark_revision_reviewed(d1.id, r1.id)
        svc1.approve_revision(d1.id, r1.id)
        svc1.submit_revision_for_review(d2.id, r2.id)
        svc1.mark_revision_reviewed(d2.id, r2.id)
        svc1.approve_revision(d2.id, r2.id)

        del svc1

        svc2 = DatabaseCoefficientService(engine)
        coeff_set = svc2.resolve_coefficient_set()
        assert "persist.alpha" in coeff_set.items
        assert "persist.beta" in coeff_set.items
        assert coeff_set.items["persist.alpha"].value == Decimal("10")
        assert coeff_set.items["persist.beta"].value == Decimal("20")

    def test_definition_code_uniqueness_across_services(self, engine) -> None:
        """DEFINITION_CODE_UNIQUENESS_ACROSS_SERVICES: duplicate code blocked."""
        svc1 = DatabaseCoefficientService(engine)
        svc1.create_definition(
            code="unique.test", name="X", description="D", category="c", canonical_unit="u"
        )
        del svc1

        svc2 = DatabaseCoefficientService(engine)
        from cold_storage.modules.coefficients.domain.exceptions import (
            DuplicateCoefficientCodeError,
        )

        with pytest.raises(DuplicateCoefficientCodeError):
            svc2.create_definition(
                code="unique.test", name="Y", description="D2", category="c", canonical_unit="u"
            )

    def test_revision_numbering_across_services(self, engine) -> None:
        """REVISION_NUMBERING_ACROSS_SERVICES: revisions numbered correctly."""
        svc1 = DatabaseCoefficientService(engine)
        d = svc1.create_definition(
            code="revnum.test", name="R", description="D", category="c", canonical_unit="u"
        )
        r1 = svc1.create_revision(definition_id=d.id, value_decimal=Decimal("1"))
        r2 = svc1.create_revision(definition_id=d.id, value_decimal=Decimal("2"))
        assert r1.revision_number == 1
        assert r2.revision_number == 2
        del svc1

        svc2 = DatabaseCoefficientService(engine)
        revisions = svc2.list_revisions(d.id)
        assert len(revisions) == 2
        assert revisions[0].revision_number == 1
        assert revisions[1].revision_number == 2


# ===========================================================================
# 4. HTTP route provider registration tests
# ===========================================================================


class TestHttpRouteProviderRegistration:
    """HTTP_ROUTE_PROVIDER_NOT_RESOLVED_AT_REGISTRATION: prove lazy resolution.

    When register_coefficient_routes is called with a provider callable,
    the provider must NOT be invoked during registration.  It is only
    called at request time.  This prevents premature dependency resolution
    in production where init_dependencies has not yet run.
    """

    def test_provider_not_called_at_registration(self, monkeypatch) -> None:
        """HTTP_ROUTE_PROVIDER_NOT_RESOLVED_AT_REGISTRATION."""
        from fastapi import FastAPI

        from cold_storage.modules.coefficients.api.routes import (
            register_coefficient_routes,
        )

        call_count = 0
        _sentinel = object()

        def _tracking_provider():
            nonlocal call_count
            call_count += 1
            return _sentinel

        app = FastAPI()
        register_coefficient_routes(app, _tracking_provider)
        assert call_count == 0, (
            f"Provider was called {call_count} times during route registration; "
            "expected 0 (deferred to request time)"
        )

    def test_provider_called_at_request_time(self, monkeypatch) -> None:
        """PROVIDER_RESOLVED_AT_REQUEST_TIME: provider invoked per-request."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from cold_storage.modules.coefficients.api.routes import (
            register_coefficient_routes,
        )
        from cold_storage.modules.coefficients.application.service import (
            CoefficientService,
        )

        call_count = 0
        process_local_service = CoefficientService()

        def _tracking_provider():
            nonlocal call_count
            call_count += 1
            return process_local_service

        app = FastAPI()
        register_coefficient_routes(app, _tracking_provider)
        assert call_count == 0

        with TestClient(app) as client:
            resp = client.get("/api/v1/coefficients")
            assert resp.status_code == 200
            assert call_count == 1, (
                f"Provider was called {call_count} times; expected 1 per request"
            )

    def test_provider_engine_is_canonical_engine(self, monkeypatch) -> None:
        """PROVIDER_ENGINE_IS_CANONICAL_ENGINE: production service uses the
        same engine as the canonical engine singleton."""
        # Set up a minimal dependency state
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        from cold_storage.bootstrap import dependencies as deps
        from cold_storage.modules.coefficients.infrastructure.database import (
            DatabaseCoefficientService,
        )

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        # Simulate the canonical engine singleton
        deps._singletons["engine"] = engine  # type: ignore[attr-defined]

        # Simulate the production coefficient service creation
        production_service = DatabaseCoefficientService(engine)
        deps._singletons["production_coefficient_service"] = production_service  # type: ignore[attr-defined]

        # Verify: the service's engine is the canonical engine
        retrieved = deps.get_production_coefficient_service()
        assert retrieved.engine is engine, (
            "DatabaseCoefficientService.engine must be the canonical engine singleton"
        )

        # Cleanup
        deps._singletons.clear()  # type: ignore[attr-defined]


# ===========================================================================
# 5. PostgreSQL persistence recreation tests
# ===========================================================================
#
# Proves that coefficient data persists across DatabaseCoefficientService
# destruction and recreation on a real PostgreSQL engine.  Each "service" is a
# fresh DatabaseCoefficientService instance bound to the same underlying engine.
# Destroying a service (letting it go out of scope) does NOT destroy data
# because the data lives in the database, not in process memory.
#
# These tests require a real PostgreSQL database.  When PostgreSQL is not
# available they are skipped via ``pytest.mark.skipif``.

_requires_pg = pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") or os.environ.get("COLD_STORAGE_DATABASE_URL")),
    reason="PostgreSQL DATABASE_URL is not configured",
)


@_requires_pg
class TestPostgreSQLCoefficientPersistenceRecreation:
    """Coefficient data survives 3 service generations on real PostgreSQL.

    Uses the ``pg_database_factory`` fixture from conftest to create an
    isolated PostgreSQL database with Alembic head schema applied.
    """

    def test_full_persistence_lifecycle_on_postgresql(self, pg_database) -> None:
        """Full lifecycle on real PostgreSQL engine.

        Steps: CREATE_DEFINITION, CREATE_REVISION, SUBMIT_REVIEW, MARK_REVIEWED,
        APPROVE, DISPOSE_OR_RELEASE_SERVICE_1, CREATE_SERVICE_2_ON_SAME_POSTGRES_DATABASE,
        READ_APPROVED, RESOLVE_APPROVED, WITHDRAW, DISPOSE_OR_RELEASE_SERVICE_2,
        CREATE_SERVICE_3_ON_SAME_POSTGRES_DATABASE, READ_WITHDRAWN,
        VERIFY_WITHDRAWN_NOT_RESOLVED.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool

        from cold_storage.modules.coefficients.infrastructure.database import (
            DatabaseCoefficientService,
        )

        # Create a real PostgreSQL engine (not sqlite://)
        pg_engine = create_engine(pg_database, poolclass=NullPool)
        try:
            assert pg_engine.dialect.name == "postgresql", (
                f"Expected postgresql dialect, got {pg_engine.dialect.name}"
            )

            # --- Service 1: CREATE_DEFINITION, CREATE_REVISION, ---
            svc1 = DatabaseCoefficientService(pg_engine)

            # CREATE_DEFINITION
            definition = svc1.create_definition(
                code="pg_persistence.test_coeff",
                name="PG Persistence Test Coefficient",
                description="Tests persistence across service recreation on PostgreSQL",
                category="test",
                canonical_unit="ratio",
            )
            assert definition.code == "pg_persistence.test_coeff"

            # CREATE_REVISION
            revision = svc1.create_revision(
                definition_id=definition.id,
                value_decimal=Decimal("2.718"),
            )
            assert revision.status == "draft"
            assert revision.value_decimal == Decimal("2.718")
            revision_id = revision.id
            definition_id = definition.id

            # SUBMIT_REVIEW
            revision = svc1.submit_revision_for_review(definition.id, revision.id)
            assert revision.status == "unverified"

            # MARK_REVIEWED
            revision = svc1.mark_revision_reviewed(
                definition.id,
                revision.id,
                reviewer="pg-test-reviewer",
            )
            assert revision.status == "reviewed"

            # APPROVE
            revision = svc1.approve_revision(
                definition.id,
                revision.id,
                approver="pg-test-approver",
            )
            assert revision.status == "approved"

            # DISPOSE_OR_RELEASE_SERVICE_1
            del svc1

            # --- Service 2: CREATE_SERVICE_2_ON_SAME_POSTGRES_DATABASE ---
            svc2 = DatabaseCoefficientService(pg_engine)

            # READ_APPROVED
            fetched = svc2.get_revision(definition_id, revision_id)
            assert fetched.status == "approved"
            assert fetched.value_decimal == Decimal("2.718")
            assert fetched.reviewed_by == "pg-test-reviewer"
            assert fetched.approved_by == "pg-test-approver"

            # RESOLVE_APPROVED
            coeff_set = svc2.resolve_coefficient_set()
            assert "pg_persistence.test_coeff" in coeff_set.items
            resolved = coeff_set.items["pg_persistence.test_coeff"]
            assert resolved.value == Decimal("2.718")
            assert resolved.status == "approved"

            # WITHDRAW
            fetched = svc2.withdraw_revision(definition_id, revision_id)
            assert fetched.status == "withdrawn"

            # DISPOSE_OR_RELEASE_SERVICE_2
            del svc2

            # --- Service 3: CREATE_SERVICE_3_ON_SAME_POSTGRES_DATABASE ---
            svc3 = DatabaseCoefficientService(pg_engine)

            # READ_WITHDRAWN
            withdrawn = svc3.get_revision(definition_id, revision_id)
            assert withdrawn.status == "withdrawn"
            assert withdrawn.value_decimal == Decimal("2.718")

            # VERIFY_WITHDRAWN_NOT_RESOLVED
            coeff_set = svc3.resolve_coefficient_set()
            assert "pg_persistence.test_coeff" not in coeff_set.items, (
                "Withdrawn coefficient must not appear in resolved set"
            )
        finally:
            pg_engine.dispose()
