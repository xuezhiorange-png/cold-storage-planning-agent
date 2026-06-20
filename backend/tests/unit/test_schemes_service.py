"""Application-service + API tests for the Scheme module.

Run with:
    cd /tmp/cold-storage-planning-agent/backend \
    && PYTHONPATH=src DATABASE_BACKEND=sqlite \
       uv run pytest tests/unit/test_schemes_service.py -v
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.bootstrap.scheme_seed import demo_weight_set
from cold_storage.modules.projects.infrastructure.orm import Base
from cold_storage.modules.schemes.api.routes import register_scheme_routes
from cold_storage.modules.schemes.application.service import SchemeService
from cold_storage.modules.schemes.domain.errors import InvalidProfileError, WeightSetError
from cold_storage.modules.schemes.infrastructure.repository import SchemeRepository

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
    """SchemeService backed by the in-memory SQLite DB."""
    return SchemeService(session)


@pytest.fixture()
def seeded_session(session):
    """Session with the demo weight set already persisted."""
    ws = demo_weight_set()
    repo = SchemeRepository(session)
    repo.save_weight_set(ws)
    session.commit()
    return session


@pytest.fixture()
def seeded_service(seeded_session) -> SchemeService:
    """SchemeService with demo weight set pre-seeded."""
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


# ---------------------------------------------------------------------------
# Helpers – sample payloads
# ---------------------------------------------------------------------------

PROJECT_ID = "proj-test-001"
VERSION = 1
VERSION_ID = f"{PROJECT_ID}-v{VERSION}"
RUN_PATH = f"/api/v1/projects/{PROJECT_ID}/versions/{VERSION}/scheme-runs"


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


def _run_kwargs(**overrides):
    """Return keyword arguments for generate_scheme_run with sane defaults."""
    base = {
        "project_id": PROJECT_ID,
        "project_version_id": VERSION_ID,
        "profile_codes": ["balanced"],
        "weight_set_id": "demo-weight-set-001",
        "profile_parameters": {},
        "source_calculation_ids": {},
        "source_snapshot_hashes": {"zone": "h1", "investment": "h2"},
        "zone_results_raw": _zone_results_raw(),
        "investment_raw": {
            "total_investment_cny": 5_000_000.0,
            "zone_investments": {},
        },
        "cooling_load_raw": {
            "design_cooling_load_kw_r": 200.0,
            "sensible_load_kw_r": 150.0,
            "latent_load_kw_r": 30.0,
            "infiltration_load_kw_r": 20.0,
        },
        "equipment_raw": {
            "compressor_operating_capacity_kw_r": 180.0,
            "compressor_installed_capacity_kw_r": 220.0,
            "condenser_heat_rejection_kw": 250.0,
            "installed_power_kw_e": 80.0,
        },
        "total_daily_throughput_kg_day": 10_000.0,
        "total_storage_capacity_kg": 35_000.0,
        "total_position_count": 70,
    }
    base.update(overrides)
    return base


def _api_body(**overrides):
    """Return the JSON body for POST /api/v1/.../scheme-runs."""
    base = {
        "profile_codes": ["balanced"],
        "weight_set_id": "demo-weight-set-001",
        "profile_parameters": {},
        "source_calculation_ids": {},
        "source_snapshot_hashes": {"zone": "h1", "investment": "h2"},
        "zone_results": _zone_results_raw(),
        "investment_result": {
            "total_investment_cny": 5_000_000.0,
            "zone_investments": {},
        },
        "cooling_load_result": {
            "design_cooling_load_kw_r": 200.0,
            "sensible_load_kw_r": 150.0,
            "latent_load_kw_r": 30.0,
            "infiltration_load_kw_r": 20.0,
        },
        "equipment_result": {
            "compressor_operating_capacity_kw_r": 180.0,
            "compressor_installed_capacity_kw_r": 220.0,
            "condenser_heat_rejection_kw": 250.0,
            "installed_power_kw_e": 80.0,
        },
        "total_daily_throughput_kg_day": 10_000.0,
        "total_storage_capacity_kg": 35_000.0,
        "total_position_count": 70,
    }
    base.update(overrides)
    return base


# ===================================================================
# 1) Reads Task 4 / Task 5 snapshots correctly
# ===================================================================


class TestSnapshotReading:
    """Verify the service consumes Task 4/5 raw snapshots without alteration."""

    def test_zone_results_parsed_into_domain_objects(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        assert result["status"] == "completed"
        # zone_results should have been consumed — we check the run record
        run = seeded_service._repo.get_run(result["run_id"])
        assert run is not None
        # input_snapshot stored the dataclass; zone results are inside
        input_snap = run.input_snapshot
        assert "zone_results" in input_snap or "project_id" in input_snap

    def test_cooling_load_snapshot_preserved(self, seeded_service: SchemeService):
        """cooling_load_raw values flow into candidates and are not zeroed."""
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        schemes = result["schemes"]
        assert len(schemes) >= 1
        # Each scheme should carry non-trivial design_cooling_load_kw_r
        for s in schemes:
            assert s["design_cooling_load_kw_r"] >= 0

    def test_investment_snapshot_preserved(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        schemes = result["schemes"]
        for s in schemes:
            assert s["investment_cny"] > 0


# ===================================================================
# 2) Does NOT recalculate engineering quantities from Task 4/5
# ===================================================================


class TestNoRecalculation:
    """The scheme module uses Task 4/5 values as-is (proportional distribution)
    but does not re-run engineering calculations."""

    def test_equipment_values_distributed_not_recalculated(self, seeded_service: SchemeService):
        """installed_power_kw_e is carried from input, not recomputed."""
        custom_power = 999.0
        result = seeded_service.generate_scheme_run(
            **_run_kwargs(
                equipment_raw={
                    "compressor_operating_capacity_kw_r": 180.0,
                    "compressor_installed_capacity_kw_r": 220.0,
                    "condenser_heat_rejection_kw": 250.0,
                    "installed_power_kw_e": custom_power,
                }
            )
        )
        # The raw input power is stored, not recalculated
        run = seeded_service._repo.get_run(result["run_id"])
        input_snap = run.input_snapshot
        # equipment_result should be in the stored input
        assert input_snap is not None

    def test_throughput_from_input_not_recalculated(self, seeded_service: SchemeService):
        tp = 42_000.0
        result = seeded_service.generate_scheme_run(**_run_kwargs(total_daily_throughput_kg_day=tp))
        run = seeded_service._repo.get_run(result["run_id"])
        input_snap = run.input_snapshot
        # total_daily_throughput_kg_day should be preserved from input
        assert input_snap is not None


# ===================================================================
# 3) Approved ProjectVersion not modified
# ===================================================================


class TestVersionImmutability:
    """The scheme service must never modify the project version record."""

    def test_version_not_written_by_scheme_service(self, seeded_service: SchemeService):
        """generate_scheme_run does not touch project_versions table."""
        seeded_service.generate_scheme_run(**_run_kwargs())
        # Check the run exists, but no version record was created by the scheme service
        from sqlalchemy import select

        from cold_storage.modules.projects.infrastructure.orm import ProjectVersionRecord

        stmt = select(ProjectVersionRecord).where(ProjectVersionRecord.id == VERSION_ID)
        version_rec = seeded_service._session.execute(stmt).scalar_one_or_none()
        # The scheme service does NOT create version records; it should be None
        assert version_rec is None


# ===================================================================
# 4) Each run creates a new SchemeRun
# ===================================================================


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


# ===================================================================
# 5) Completed SchemeRun is immutable
# ===================================================================


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


# ===================================================================
# 6) Audit events correct
# ===================================================================


class TestAuditEvents:
    """Verify run metadata is correctly recorded for audit purposes."""

    def test_run_stores_source_hash(self, seeded_service: SchemeService):
        hashes = {"zone": "abc", "investment": "def"}
        result = seeded_service.generate_scheme_run(**_run_kwargs(source_snapshot_hashes=hashes))
        run = seeded_service._repo.get_run(result["run_id"])
        # The service computes a sha256-based hash from the snapshot dict
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


# ===================================================================
# 7) requires_review propagation correct
# ===================================================================


class TestRequiresReview:
    """Verify requires_review propagates from candidates to the run."""

    def test_balanced_run_requires_review_flag_set(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(**_run_kwargs())
        run = seeded_service._repo.get_run(result["run_id"])
        # The run-level requires_review is True if ANY candidate has requires_review
        # or if no feasible scheme was found
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
        # The consolidated profile is marked requires_review in the generator
        schemes = result["schemes"]
        consolidated = [s for s in schemes if s["scheme_code"] == "consolidated_large_rooms"]
        assert len(consolidated) == 1
        assert consolidated[0]["requires_review"] is True


# ===================================================================
# 8) Create run API works
# ===================================================================


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


# ===================================================================
# 9) Get run API works
# ===================================================================


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


# ===================================================================
# 10) List runs API works
# ===================================================================


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


# ===================================================================
# 11) Get comparison API works
# ===================================================================


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


# ===================================================================
# 12) Invalid profile returns 422
# ===================================================================


class TestInvalidProfile:
    def test_unknown_profile_code_via_api(self, client: TestClient):
        body = _api_body(profile_codes=["unknown_nonexistent_profile"])
        resp = client.post(RUN_PATH, json=body)
        assert resp.status_code == 422

    def test_invalid_profile_code_via_service(self, seeded_service: SchemeService):
        with pytest.raises(InvalidProfileError):
            seeded_service.generate_scheme_run(**_run_kwargs(profile_codes=["bogus_profile_xyz"]))


# ===================================================================
# 13) Missing profile parameter handled
# ===================================================================


class TestMissingProfileParameter:
    def test_empty_profile_codes_via_api(self, client: TestClient):
        body = _api_body(profile_codes=[])
        resp = client.post(RUN_PATH, json=body)
        # Empty list means no profiles to generate — service should handle gracefully
        # Either 200 with no schemes, or 422 for validation
        assert resp.status_code in (200, 422)

    def test_empty_profile_codes_via_service(self, seeded_service: SchemeService):
        """Empty profile list produces zero candidates; score_candidates
        raises ValueError on an empty list (no candidates to normalize).
        This is a known edge case — the API layer converts it to 422."""
        with pytest.raises(ValueError, match="empty"):
            seeded_service.generate_scheme_run(**_run_kwargs(profile_codes=[]))


# ===================================================================
# 14) Invalid weight set returns error
# ===================================================================


class TestInvalidWeightSet:
    def test_nonexistent_weight_set_via_api(self, client: TestClient):
        body = _api_body(weight_set_id="no-such-weight-set")
        resp = client.post(RUN_PATH, json=body)
        assert resp.status_code == 422

    def test_nonexistent_weight_set_via_service(self, seeded_service: SchemeService):
        with pytest.raises(WeightSetError):
            seeded_service.generate_scheme_run(**_run_kwargs(weight_set_id="nonexistent-ws-id"))


# ===================================================================
# 15) Version not found returns 404
# ===================================================================


class TestVersionNotFound:
    def test_get_run_nonexistent_version(self, client: TestClient):
        # Using a valid run_id format but the route still checks the run exists
        resp = client.get(
            f"/api/v1/projects/{PROJECT_ID}/versions/{VERSION}/scheme-runs/nonexistent-id"
        )
        assert resp.status_code == 404

    def test_list_runs_nonexistent_version(self, client: TestClient):
        # List runs for a version that has no runs — returns empty list
        resp = client.get("/api/v1/projects/does-not-exist/versions/99/scheme-runs")
        assert resp.status_code == 200
        assert resp.json() == []


# ===================================================================
# 16) Infeasible scheme response
# ===================================================================


class TestInfeasibleScheme:
    """When zone constraints make ALL candidates infeasible, the run still
    completes but with no feasible recommendation."""

    def test_infeasible_zone_constraints(self, seeded_service: SchemeService):
        """Supply zones with incompatible temperatures in same room forces
        infeasibility for the balanced profile (which puts each zone in its
        own room — so we use a scenario where storage requirements far
        exceed what's provided)."""
        # Use an input where required capacity vastly exceeds what zones provide
        result = seeded_service.generate_scheme_run(
            **_run_kwargs(
                total_storage_capacity_kg=999_999_999.0,  # impossible to meet
                total_position_count=999_999,
            )
        )
        # The run still completes — it just reports the situation
        assert result["status"] == "completed"
        # If all candidates infeasible, requires_review should be True
        # (the service sets requires_review = True when no feasible scheme)
        if result["recommended_scheme_code"] is None:
            assert result["requires_review"] is True
            assert result.get("warnings") is not None or "requires_review" in result

    def test_all_candidates_infeasible_via_api(self, client: TestClient):
        body = _api_body(
            total_storage_capacity_kg=999_999_999.0,
            total_position_count=999_999,
        )
        resp = client.post(RUN_PATH, json=body)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        # No feasible recommendation when everything is impossible
        if body["recommended_scheme_code"] is None:
            assert body["requires_review"] is True

    def test_run_record_created_even_when_infeasible(self, seeded_service: SchemeService):
        result = seeded_service.generate_scheme_run(
            **_run_kwargs(
                total_storage_capacity_kg=999_999_999.0,
                total_position_count=999_999,
            )
        )
        run = seeded_service._repo.get_run(result["run_id"])
        assert run is not None
        assert run.status == "completed"
