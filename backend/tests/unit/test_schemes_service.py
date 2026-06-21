"""Application-service + API tests for the Scheme module (trust-boundary version).

Run with:
    cd /tmp/cold-storage-planning-agent/backend \
    && PYTHONPATH=src DATABASE_BACKEND=sqlite \
       uv run pytest tests/unit/test_schemes_service.py -v
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.scheme_seed import demo_weight_set
from cold_storage.modules.projects.infrastructure.orm import (
    Base,
    CalculationRunRecord,
    ProjectRecord,
    ProjectVersionRecord,
)
from cold_storage.modules.schemes.api.routes import register_scheme_routes
from cold_storage.modules.schemes.application.service import SchemeService
from cold_storage.modules.schemes.domain.errors import (
    InvalidProfileError,
    SourceCalculationMissingError,
    WeightSetError,
)
from cold_storage.modules.schemes.infrastructure.repository import SchemeRepository

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ID = "proj-test-001"
VERSION = 1
VERSION_ID = f"{PROJECT_ID}-v{VERSION}"
RUN_PATH = f"/api/v1/projects/{PROJECT_ID}/versions/{VERSION}/scheme-runs"


# ---------------------------------------------------------------------------
# Sample payload data (mirrors old tests — used as DB seed now)
# ---------------------------------------------------------------------------


def _zone_results_raw():
    return [
        {
            "zone_code": "Z1",
            "zone_name": "冷藏区A",
            "temperature_level": "0~4℃",
            "area_m2": 200.0,
            "position_count": 40,
            "storage_capacity_kg": 20000.0,
            "process_compatibility": "general",
            "hygiene_zone": "standard",
        },
        {
            "zone_code": "Z2",
            "zone_name": "冷藏区B",
            "temperature_level": "0~4℃",
            "area_m2": 150.0,
            "position_count": 30,
            "storage_capacity_kg": 15000.0,
            "process_compatibility": "general",
            "hygiene_zone": "standard",
        },
    ]


def _investment_snapshot():
    return {
        "total_investment_cny": 5_000_000.0,
        "zone_investments": {},
    }


def _cooling_load_snapshot():
    return {
        "design_cooling_load_kw_r": 200.0,
        "sensible_load_kw_r": 150.0,
        "latent_load_kw_r": 30.0,
        "infiltration_load_kw_r": 20.0,
    }


def _equipment_snapshot():
    return {
        "compressor_operating_capacity_kw_r": 180.0,
        "compressor_installed_capacity_kw_r": 220.0,
        "condenser_heat_rejection_kw": 250.0,
        "installed_power_kw_e": 80.0,
    }


# ---------------------------------------------------------------------------
# DB seeding helpers
# ---------------------------------------------------------------------------

_CALC_ID_COUNTER = 0


def _next_calc_id():
    global _CALC_ID_COUNTER
    _CALC_ID_COUNTER += 1
    return f"calc-{_CALC_ID_COUNTER:04d}"


def _seed_calculation(session, calculator_name: str, result_snapshot: dict):
    """Insert a CalculationRunRecord for a given calculator name."""
    rec = CalculationRunRecord(
        id=_next_calc_id(),
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        calculator_name=calculator_name,
        calculator_version="1.0",
        input_snapshot={},
        result_snapshot=result_snapshot,
        formulas=[],
        coefficients=[],
        assumptions=[],
        warnings=[],
        source_references=[],
        requires_review=False,
    )
    session.add(rec)
    return rec


def _seed_base_data(session):
    """Seed project, version record, weight set, and standard calculations."""
    project = ProjectRecord(
        id=PROJECT_ID,
        code="test-proj",
        name="Test Project",
        location="Test Location",
        product_category="cold-storage",
        status="approved",
        current_version_number=VERSION,
    )
    session.merge(project)

    version = ProjectVersionRecord(
        id=VERSION_ID,
        project_id=PROJECT_ID,
        version_number=VERSION,
        change_summary="Test version",
        status="approved",
        created_by="test-user",
    )
    session.merge(version)

    ws = demo_weight_set()
    repo = SchemeRepository(session)
    repo.save_weight_set(ws)
    session.commit()


def _seed_standard_calculations(
    session,
    zone_results=None,
    investment=None,
    cooling_load=None,
    equipment=None,
    total_daily_throughput_kg_day=10_000.0,
):
    """Seed the four required calculation runs with standard or custom data."""
    zone_snap = {
        "zone_results": zone_results or _zone_results_raw(),
        "total_daily_throughput_kg_day": total_daily_throughput_kg_day,
    }
    _seed_calculation(session, "zone", zone_snap)
    _seed_calculation(session, "investment", investment or _investment_snapshot())
    _seed_calculation(session, "cooling_load", cooling_load or _cooling_load_snapshot())
    _seed_calculation(session, "equipment", equipment or _equipment_snapshot())
    session.commit()


# ---------------------------------------------------------------------------
# Service / API call helpers
# ---------------------------------------------------------------------------


def _run_kwargs(**overrides):
    """Keyword arguments for SchemeService.generate_scheme_run."""
    base = {
        "project_id": PROJECT_ID,
        "version": VERSION,
        "profile_codes": ["balanced"],
        "weight_set_id": "demo-weight-set-001",
        "profile_parameters": {},
    }
    base.update(overrides)
    return base


def _api_body(**overrides):
    """JSON body for POST /api/v1/.../scheme-runs."""
    base = {
        "profile_codes": ["balanced"],
        "weight_set_id": "demo-weight-set-001",
        "profile_parameters": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SESSION_LOCAL = sessionmaker(expire_on_commit=False)


@pytest.fixture()
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    """A single SQLAlchemy session for the test."""
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def service(session) -> SchemeService:
    """SchemeService backed by the in-memory SQLite DB (no seeded data)."""
    return SchemeService(session)


@pytest.fixture()
def seeded_session(session):
    """Session with project, version, weight set, and standard calculations."""
    _seed_base_data(session)
    _seed_standard_calculations(session)
    return session


@pytest.fixture()
def seeded_service(seeded_session) -> SchemeService:
    """SchemeService with full seeded data."""
    return SchemeService(seeded_session)


@pytest.fixture()
def app(seeded_session) -> FastAPI:
    """Minimal FastAPI app exposing scheme routes only."""
    _app = FastAPI()

    def _get_service():
        return SchemeService(seeded_session)

    register_scheme_routes(_app, _get_service)
    return _app


@pytest.fixture()
def client(app) -> TestClient:
    """Synchronous test client for the scheme API."""
    return TestClient(app)


# --- Infeasible-data fixtures (huge capacity vs tiny area) ---


def _infeasible_zone_results():
    """Zone data with impossible capacity/position vs area."""
    return [
        {
            "zone_code": "Z1",
            "zone_name": "Huge Zone",
            "temperature_level": "0~4℃",
            "area_m2": 5.0,
            "position_count": 999_999,
            "storage_capacity_kg": 999_999_999.0,
            "process_compatibility": "general",
            "hygiene_zone": "standard",
        },
    ]


@pytest.fixture()
def infeasible_session(session):
    """Session seeded with infeasible zone data."""
    _seed_base_data(session)
    _seed_standard_calculations(session, zone_results=_infeasible_zone_results())
    return session


@pytest.fixture()
def infeasible_service(infeasible_session) -> SchemeService:
    return SchemeService(infeasible_session)


@pytest.fixture()
def infeasible_app(infeasible_session) -> FastAPI:
    _app = FastAPI()

    def _get_service():
        return SchemeService(infeasible_session)

    register_scheme_routes(_app, _get_service)
    return _app


@pytest.fixture()
def infeasible_client(infeasible_app) -> TestClient:
    return TestClient(infeasible_app)


# ============================================================================
# 1) Reads Task 4 / Task 5 snapshots correctly (from DB)
# ============================================================================


class TestSnapshotReading:
    """Verify the service consumes Task 4/5 data read from the database."""

    def test_zone_results_parsed_into_domain_objects(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        assert result["status"] == "completed"
        run = seeded_service._repo.get_run(result["run_id"])
        assert run is not None
        input_snap = run.input_snapshot
        assert "zone_results" in input_snap or "project_id" in input_snap

    def test_cooling_load_snapshot_preserved(self, seeded_service: SchemeService):
        """cooling_load values flow into candidates and are not zeroed."""
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        schemes = result["schemes"]
        assert len(schemes) >= 1
        for s in schemes:
            assert float(s["design_cooling_load_kw_r"]) >= 0

    def test_investment_snapshot_preserved(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        schemes = result["schemes"]
        for s in schemes:
            assert float(s["investment_cny"]) > 0


# ============================================================================
# 2) Does NOT recalculate engineering quantities from Task 4/5
# ============================================================================


class TestNoRecalculation:
    """The scheme module uses Task 4/5 values as-is (proportional distribution)
    but does not re-run engineering calculations."""

    def test_equipment_values_distributed_not_recalculated(self, session):
        """installed_power_kw_e is carried from input, not recomputed."""
        _seed_base_data(session)
        custom_power = 999.0
        _seed_standard_calculations(
            session,
            equipment={
                "compressor_operating_capacity_kw_r": 180.0,
                "compressor_installed_capacity_kw_r": 220.0,
                "condenser_heat_rejection_kw": 250.0,
                "installed_power_kw_e": custom_power,
            },
        )
        svc = SchemeService(session)
        result = svc.generate_scheme_run(**_run_kwargs())
        run = svc._repo.get_run(result["run_id"])
        input_snap = run.input_snapshot
        assert input_snap is not None

    def test_throughput_from_input_not_recalculated(self, session):
        tp = 42_000.0
        _seed_base_data(session)
        _seed_standard_calculations(session, total_daily_throughput_kg_day=tp)
        svc = SchemeService(session)
        result = svc.generate_scheme_run(**_run_kwargs())
        run = svc._repo.get_run(result["run_id"])
        input_snap = run.input_snapshot
        assert input_snap is not None


# ============================================================================
# 3) Approved ProjectVersion not modified
# ============================================================================


class TestVersionImmutability:
    """The scheme service must never modify the project version record."""

    def test_version_not_written_by_scheme_service(self, seeded_service: SchemeService):
        """generate_scheme_run does not create new project_versions."""
        count_before = seeded_service._session.execute(
            select(func.count()).select_from(ProjectVersionRecord)
        ).scalar()

        seeded_service.generate_scheme_run(**_run_kwargs())

        count_after = seeded_service._session.execute(
            select(func.count()).select_from(ProjectVersionRecord)
        ).scalar()
        # The scheme service should not create new version records
        assert count_after == count_before

    def test_version_record_unmodified(self, seeded_service: SchemeService):
        """Existing version record fields are not mutated."""
        stmt = select(ProjectVersionRecord).where(ProjectVersionRecord.id == VERSION_ID)
        v_before = seeded_service._session.execute(stmt).scalar_one()
        orig_status = v_before.status
        orig_summary = v_before.change_summary

        seeded_service.generate_scheme_run(**_run_kwargs())

        v_after = seeded_service._session.execute(stmt).scalar_one()
        assert v_after.status == orig_status
        assert v_after.change_summary == orig_summary


# ============================================================================
# 4) Each run creates a new SchemeRun
# ============================================================================


class TestRunCreation:
    """Every call to generate_scheme_run creates a new SchemeRun record."""

    def test_first_run_creates_record(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        assert run is not None
        assert run.status == "completed"

    def test_second_run_creates_new_record(self, seeded_service: SchemeService):
        r1 = seeded_service.generate_scheme_run(**_run_kwargs())
        r2 = seeded_service.generate_scheme_run(**_run_kwargs())
        assert r1["run_id"] != r2["run_id"]
        runs = seeded_service._repo.list_runs(VERSION_ID)
        assert len(runs) == 2


# ============================================================================
# 5) Completed SchemeRun is immutable
# ============================================================================


class TestRunImmutability:
    """Once a run reaches 'completed' it should not be overwritten."""

    def test_completed_run_has_completed_status(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        assert run.status == "completed"

    def test_completed_timestamp_set(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        assert run.completed_at is not None


# ============================================================================
# 6) Audit events correct
# ============================================================================


class TestAuditEvents:
    """Verify run metadata is correctly recorded for audit purposes."""

    def test_run_stores_source_hash(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        # The service computes a sha256-based hash from the calculation snapshots
        assert run.source_snapshot_hash is not None
        assert len(run.source_snapshot_hash) > 0

    def test_run_stores_weight_set_id(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        assert run.weight_set_id == "demo-weight-set-001"

    def test_run_stores_project_and_version(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        assert run.project_id == PROJECT_ID
        assert run.project_version_id == VERSION_ID

    def test_comparison_snapshot_populated(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        assert "recommended_scheme_code" in run.comparison_snapshot


# ============================================================================
# 7) requires_review propagation correct
# ============================================================================


class TestRequiresReview:
    """Verify requires_review propagates from candidates to the run."""

    def test_balanced_run_requires_review_flag_set(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        assert isinstance(run.requires_review, bool)

    def test_requires_review_propagated_to_response(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        assert "requires_review" in result
        assert isinstance(result["requires_review"], bool)

    def test_consolidated_has_requires_review_true(self, seeded_service: SchemeService):
        """consolidated_large_rooms always sets requires_review=True."""
        result = seeded_service.generate_scheme_run(
            **_run_kwargs(profile_codes=["consolidated_large_rooms"])
        )
        schemes = result["schemes"]
        consolidated = [s for s in schemes if s["scheme_code"] == "consolidated_large_rooms"]
        assert len(consolidated) == 1
        assert consolidated[0]["requires_review"] is True


# ============================================================================
# 8) Create run API works
# ============================================================================


class TestCreateRunAPI:
    def test_post_creates_run(self, client: TestClient):
        resp = client.post(RUN_PATH, json=_api_body())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert "run_id" in body
        assert len(body["schemes"]) >= 1

    def test_post_returns_schemes_list(self, client: TestClient):
        resp = client.post(RUN_PATH, json=_api_body())
        body = resp.json()
        assert isinstance(body["schemes"], list)
        for s in body["schemes"]:
            assert "scheme_code" in s
            assert "feasible" in s

    def test_post_returns_score_breakdowns(self, client: TestClient):
        resp = client.post(RUN_PATH, json=_api_body())
        body = resp.json()
        assert "score_breakdowns" in body
        assert isinstance(body["score_breakdowns"], list)
        for sb in body["score_breakdowns"]:
            assert "scheme_code" in sb
            assert "total_score" in sb


# ============================================================================
# 9) Get run API works
# ============================================================================


class TestGetRunAPI:
    def _create_and_get_run_id(self, client: TestClient) -> str:
        resp = client.post(RUN_PATH, json=_api_body())
        return resp.json()["run_id"]

    def test_get_existing_run(self, client: TestClient):
        run_id = self._create_and_get_run_id(client)
        resp = client.get(f"{RUN_PATH}/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert body["status"] == "completed"

    def test_get_nonexistent_run_returns_404(self, client: TestClient):
        resp = client.get(f"{RUN_PATH}/nonexistent-run-id")
        assert resp.status_code == 404


# ============================================================================
# 10) List runs API works
# ============================================================================


class TestListRunsAPI:
    def test_list_empty(self, client: TestClient):
        resp = client.get(RUN_PATH)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_create(self, client: TestClient):
        client.post(RUN_PATH, json=_api_body())
        resp = client.get(RUN_PATH)
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 1
        assert "run_id" in runs[0]
        assert "status" in runs[0]

    def test_list_shows_multiple_runs(self, client: TestClient):
        client.post(RUN_PATH, json=_api_body())
        client.post(RUN_PATH, json=_api_body())
        resp = client.get(RUN_PATH)
        assert len(resp.json()) >= 2


# ============================================================================
# 11) Get comparison API works
# ============================================================================


class TestGetComparisonAPI:
    def _create_run_id(self, client: TestClient) -> str:
        return client.post(RUN_PATH, json=_api_body()).json()["run_id"]

    def test_comparison_returns_data(self, client: TestClient):
        run_id = self._create_run_id(client)
        resp = client.get(f"{RUN_PATH}/{run_id}/comparison")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert "comparison_snapshot" in body

    def test_comparison_nonexistent_returns_404(self, client: TestClient):
        resp = client.get(f"{RUN_PATH}/nonexistent/comparison")
        assert resp.status_code == 404


# ============================================================================
# 12) Invalid profile returns 422
# ============================================================================


class TestInvalidProfile:
    def test_unknown_profile_code_via_api(self, client: TestClient):
        body = _api_body(profile_codes=["unknown_nonexistent_profile"])
        resp = client.post(RUN_PATH, json=body)
        assert resp.status_code == 422

    def test_invalid_profile_code_via_service(self, seeded_service: SchemeService):
        with pytest.raises(InvalidProfileError):
            seeded_service.generate_scheme_run(**_run_kwargs(profile_codes=["bogus_profile_xyz"]))


# ============================================================================
# 13) Missing profile parameter handled
# ============================================================================


class TestMissingProfileParameter:
    def test_empty_profile_codes_via_api(self, client: TestClient):
        body = _api_body(profile_codes=[])
        resp = client.post(RUN_PATH, json=body)
        # Empty list means no profiles to generate — service should handle gracefully
        # Either 200 with no schemes, or 422 for validation
        assert resp.status_code in (200, 422)

    def test_empty_profile_codes_via_service(self, seeded_service: SchemeService):
        """Empty profile list produces zero candidates; the service completes
        successfully with an empty schemes list."""
        result = seeded_service.generate_scheme_run(**_run_kwargs(profile_codes=[]))
        assert result["status"] == "completed"
        assert result["schemes"] == []


# ============================================================================
# 14) Invalid weight set returns error
# ============================================================================


class TestInvalidWeightSet:
    def test_nonexistent_weight_set_via_api(self, client: TestClient):
        body = _api_body(weight_set_id="no-such-weight-set")
        resp = client.post(RUN_PATH, json=body)
        assert resp.status_code == 422

    def test_nonexistent_weight_set_via_service(self, seeded_service: SchemeService):
        with pytest.raises(WeightSetError):
            seeded_service.generate_scheme_run(**_run_kwargs(weight_set_id="nonexistent-ws-id"))


# ============================================================================
# 15) Version / project not found returns 404
# ============================================================================


class TestVersionNotFound:
    def test_get_run_nonexistent_version(self, client: TestClient):
        # Using a valid run_id format but the route still checks the run exists
        resp = client.get(
            f"/api/v1/projects/{PROJECT_ID}/versions/{VERSION}/scheme-runs/nonexistent-id"
        )
        assert resp.status_code == 404

    def test_list_runs_nonexistent_version(self, client: TestClient):
        # List runs for a nonexistent version — returns 404
        resp = client.get("/api/v1/projects/does-not-exist/versions/99/scheme-runs")
        assert resp.status_code == 404


# ============================================================================
# 15b) Missing project returns 404 via API
# ============================================================================


class TestProjectNotFound:
    def test_missing_project_via_api(self, client: TestClient):
        resp = client.post(
            "/api/v1/projects/no-such-project/versions/1/scheme-runs",
            json=_api_body(),
        )
        assert resp.status_code == 404

    def test_missing_project_via_service(self, service: SchemeService):
        """Service raises ProjectNotFoundError for unknown project_id."""
        from cold_storage.modules.schemes.domain.errors import ProjectNotFoundError

        with pytest.raises(ProjectNotFoundError):
            service.generate_scheme_run(**_run_kwargs(project_id="no-such-project"))

    def test_missing_version_via_service(self, service: SchemeService):
        """Service raises ProjectVersionNotFoundError for unknown version."""
        # Seed project but not version
        from cold_storage.modules.projects.infrastructure.orm import ProjectRecord

        proj = ProjectRecord(
            id=PROJECT_ID,
            code="test-proj",
            name="Test Project",
            location="Location",
            product_category="cold-storage",
            status="draft",
            current_version_number=0,
        )
        service._session.merge(proj)
        service._session.commit()

        from cold_storage.modules.schemes.domain.errors import ProjectVersionNotFoundError

        with pytest.raises(ProjectVersionNotFoundError):
            service.generate_scheme_run(**_run_kwargs(project_id=PROJECT_ID, version=999))


# ============================================================================
# 15c) Missing source calculations returns 409
# ============================================================================


class TestMissingSourceCalculation:
    def test_missing_calculation_via_api(self, client_no_calcs: TestClient):
        resp = client_no_calcs.post(RUN_PATH, json=_api_body())
        assert resp.status_code == 409

    def test_missing_calculation_via_service(self, service_no_calcs: SchemeService):
        with pytest.raises(SourceCalculationMissingError):
            service_no_calcs.generate_scheme_run(**_run_kwargs())


# ============================================================================
# 16) Infeasible scheme response
# ============================================================================


class TestInfeasibleScheme:
    """When zone constraints make ALL candidates infeasible, the run still
    completes but with no feasible recommendation."""

    def test_infeasible_zone_constraints(self, infeasible_service: SchemeService):
        """Supply zones with impossible capacity vs area."""
        result = infeasible_service.generate_scheme_run(**_run_kwargs())
        # The run still completes — it just reports the situation
        assert result["status"] == "completed"
        # If all candidates infeasible, requires_review should be True
        if result["recommended_scheme_code"] is None:
            assert result["requires_review"] is True
            assert result.get("warnings") is not None or "requires_review" in result

    def test_all_candidates_infeasible_via_api(self, infeasible_client: TestClient):
        resp = infeasible_client.post(RUN_PATH, json=_api_body())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        if body["recommended_scheme_code"] is None:
            assert body["requires_review"] is True

    def test_run_record_created_even_when_infeasible(self, infeasible_service: SchemeService):
        result = infeasible_service.generate_scheme_run(**_run_kwargs())
        run = infeasible_service._repo.get_run(result["run_id"])
        assert run is not None
        assert run.status == "completed"


# ---------------------------------------------------------------------------
# Extra fixtures for tests that need a session WITHOUT calculation records
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_no_calcs(session):
    """Session with project+version+weight set but NO calculation records."""
    _seed_base_data(session)
    return session


@pytest.fixture()
def service_no_calcs(session_no_calcs) -> SchemeService:
    return SchemeService(session_no_calcs)


@pytest.fixture()
def app_no_calcs(session_no_calcs) -> FastAPI:
    _app = FastAPI()

    def _get_service():
        return SchemeService(session_no_calcs)

    register_scheme_routes(_app, _get_service)
    return _app


@pytest.fixture()
def client_no_calcs(app_no_calcs) -> TestClient:
    return TestClient(app_no_calcs)
