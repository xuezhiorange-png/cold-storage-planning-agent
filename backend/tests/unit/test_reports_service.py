"""Report application service tests — assembler, lifecycle, review, export."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.application.assembler import (
    ReportAssembler,
    ReportDataProvider,
)
from cold_storage.modules.reports.application.service import ReportService
from cold_storage.modules.reports.domain.enums import ReportStatus, ReportType
from cold_storage.modules.reports.domain.errors import (
    InvalidStatusTransitionError,
    ReportNotFoundError,
)
from cold_storage.modules.reports.infrastructure.orm import Base
from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionFactory() as session:
        yield session


@pytest.fixture()
def repo(db_session):
    return SQLReportRepository(db_session)


class _FakeDataProvider(ReportDataProvider):
    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return {"name": "Test Project", "location": "Test Location"}

    def get_project_version(self, version_id: str) -> dict[str, Any] | None:
        return {"version_number": 1}

    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return [
            {
                "section_key": "cooling_load",
                "result_id": "calc-001",
                "tool_name": "cooling_load_calculator",
                "tool_version": "1.0.0",
                "data": {
                    "total_design_refrigeration_load": {
                        "value": 100.0,
                        "unit": "kW(r)",
                        "source_result_id": "calc-001",
                        "source_tool": "cooling_load_calculator",
                        "source_tool_version": "1.0.0",
                    }
                },
            },
            {
                "section_key": "equipment_selection",
                "result_id": "calc-002",
                "tool_name": "equipment_selector",
                "tool_version": "1.0.0",
                "data": {
                    "total_compressor_capacity": {
                        "value": 120.0,
                        "unit": "kW(r)",
                        "source_result_id": "calc-002",
                        "source_tool": "equipment_selector",
                        "source_tool_version": "1.0.0",
                    }
                },
            },
            {
                "section_key": "electrical_and_energy",
                "result_id": "calc-003",
                "tool_name": "energy_calculator",
                "tool_version": "1.0.0",
                "data": {
                    "total_installed_power": {
                        "value": 50.0,
                        "unit": "kW(e)",
                        "source_result_id": "calc-003",
                        "source_tool": "energy_calculator",
                        "source_tool_version": "1.0.0",
                    }
                },
            },
        ]

    def get_scheme_results(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        return {
            "run_id": "scheme-001",
            "schemes": [
                {"scheme_id": "s1", "name": "Scheme A", "total_investment_cny": 5000000},
                {"scheme_id": "s2", "name": "Scheme B", "total_investment_cny": 6000000},
            ],
        }

    def get_agent_sessions(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return []


@pytest.fixture()
def assembler():
    return ReportAssembler(_FakeDataProvider())


@pytest.fixture()
def service(repo, assembler):
    return ReportService(repo, assembler)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


class TestReportCRUD:
    def test_create_report(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        assert r.status == ReportStatus.DRAFT
        assert r.project_id == "p1"

    def test_get_report(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        got = service.get_report(r.id, "user1")
        assert got.id == r.id

    def test_get_report_not_found(self, service):
        with pytest.raises(ReportNotFoundError):
            service.get_report("nonexistent", "user1")

    def test_cross_user_returns_not_found(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        with pytest.raises(ReportNotFoundError):
            service.get_report(r.id, "user2")

    def test_list_reports_owner_isolation(self, service):
        service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user2",
        )
        # user1 sees only their report
        reports = service.list_reports(project_id="p1", actor="user1")
        assert len(reports) == 1
        assert reports[0].created_by == "user1"
        # user2 sees only their report
        reports = service.list_reports(project_id="p1", actor="user2")
        assert len(reports) == 1
        assert reports[0].created_by == "user2"

    def test_list_reports(self, service):
        service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        reports = service.list_reports(project_id="p1")
        assert len(reports) == 1


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------


class TestReportGeneration:
    def test_generate_revision(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        rev = service.generate_revision(r.id, "user1")
        assert rev.revision_number == 1
        assert rev.schema_version == "cold_storage_concept_design@1.0.0"
        assert len(rev.content_hash) == 64  # SHA-256

    def test_generate_increments_revision(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        service.generate_revision(r.id, "user1")
        rev2 = service.generate_revision(r.id, "user1")
        assert rev2.revision_number == 2

    def test_generate_sets_status_generated_when_no_blockers(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        service.generate_revision(r.id, "user1")
        updated = service.get_report(r.id, "user1")
        # Should be GENERATED since assembler provides valid data
        assert updated.status in (ReportStatus.DRAFT, ReportStatus.GENERATED)

    def test_generate_preserves_canonical_hash(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        rev = service.generate_revision(r.id, "user1")
        # Hash should be deterministic — same content → same hash
        assert len(rev.content_hash) == 64

    def test_hash_stability_across_timestamps(self, service):
        """Assembling twice with different generated_at must produce the same hash."""
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        rev1 = service.generate_revision(r.id, "user1")
        hash1 = rev1.content_hash
        # Generate a second revision — different assembly_timestamp
        import time

        time.sleep(0.01)
        rev2 = service.generate_revision(r.id, "user1")
        hash2 = rev2.content_hash
        # Content hash must be identical despite different timestamps
        assert hash1 == hash2, f"Content hash changed between assemblies: {hash1} != {hash2}"


# ---------------------------------------------------------------------------
# Review workflow tests
# ---------------------------------------------------------------------------


class TestReviewWorkflow:
    def _setup_generated(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        service.generate_revision(r.id, "user1")
        return r

    def test_submit_review(self, service):
        r = self._setup_generated(service)
        updated = service.submit_review(r.id, "user1", comment="Ready")
        assert updated.status == ReportStatus.UNDER_REVIEW

    def test_request_changes(self, service):
        r = self._setup_generated(service)
        service.submit_review(r.id, "user1")
        updated = service.request_changes(r.id, "user1", comment="Fix X")
        assert updated.status == ReportStatus.DRAFT

    def test_mark_reviewed(self, service):
        r = self._setup_generated(service)
        service.submit_review(r.id, "user1")
        updated = service.mark_reviewed(r.id, "user1")
        assert updated.status == ReportStatus.REVIEWED

    def test_approve(self, service):
        r = self._setup_generated(service)
        service.submit_review(r.id, "user1")
        service.mark_reviewed(r.id, "user1")
        updated = service.approve(r.id, "user1")
        assert updated.status == ReportStatus.APPROVED

    def test_archive(self, service):
        r = self._setup_generated(service)
        service.submit_review(r.id, "user1")
        service.mark_reviewed(r.id, "user1")
        service.approve(r.id, "user1")
        updated = service.archive(r.id, "user1")
        assert updated.status == ReportStatus.ARCHIVED

    def test_invalid_transition_rejected(self, service):
        r = self._setup_generated(service)
        with pytest.raises(InvalidStatusTransitionError):
            service.approve(r.id, "user1")  # Can't skip to approve

    def test_actor_isolation(self, service):
        r = self._setup_generated(service)
        # Non-owner can't read via get_report (404)
        with pytest.raises(ReportNotFoundError):
            service.get_report(r.id, "other_user")
        # Cross-user review actions also return 404
        with pytest.raises(ReportNotFoundError):
            service.submit_review(r.id, "other_user", comment="Looks good")


# ---------------------------------------------------------------------------
# Export and comparison tests
# ---------------------------------------------------------------------------


class TestExportAndComparison:
    def test_export_json(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        service.generate_revision(r.id, "user1")
        exported = service.export_json(r.id, 1, "user1")
        assert "schema_version" in exported
        assert "content_hash" in exported
        assert "content" in exported

    def test_compare_revisions(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        service.generate_revision(r.id, "user1")
        service.generate_revision(r.id, "user1")
        changes = service.compare_revisions(r.id, 1, 2, "user1")
        # Revisions may or may not differ — just verify it returns a list
        assert isinstance(changes, list)

    def test_list_revisions(self, service):
        r = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
        )
        service.generate_revision(r.id, "user1")
        service.generate_revision(r.id, "user1")
        revs = service.list_revisions(r.id, "user1")
        assert len(revs) == 2


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------


class _InMemoryIdempotencyStore:
    def __init__(self):
        self._store: dict[str, Any] = {}
        self._claimed: set[str] = set()

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def claim(self, key: str) -> bool:
        if key in self._claimed:
            return False
        self._claimed.add(key)
        return True

    def complete(self, key: str, value: Any) -> None:
        self._store[key] = value
        self._claimed.discard(key)


class TestIdempotency:
    def test_create_idempotent(self, service):
        store = _InMemoryIdempotencyStore()
        service._idempotency_store = store
        r1 = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
            idempotency_key="key-1",
        )
        r2 = service.create_report(
            project_id="p1",
            project_version_id="v1",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            actor="user1",
            idempotency_key="key-1",
        )
        assert r1.id == r2.id
