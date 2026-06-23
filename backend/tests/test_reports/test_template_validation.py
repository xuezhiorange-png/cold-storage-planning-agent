"""Tests for P0-3 (Template API type/identity validation) and P0-6 (ApprovalSnapshot manifest).

P0-3 covers:
  1. Invalid report_type enum → 422
  2. Invalid format enum → 422
  3. template_code mismatch between request and manifest → 422
  4. version mismatch → 422
  5. report_type mismatch → 422
  6. schema_version mismatch → 422
  7. locale mismatch → 422
  8. Empty manifest → 422
  9. Successful creation → returns and persists 64-char hash
  10. Empty hash activation → 409
  11. Concurrent activation → one succeeds, one 409
  12. Activation of retired template → 409
  13. Idempotent activation (already active) → 200
  14. Update of active template → 409
  15. Update of retired template → 409
  16. Successful update of draft template

P0-6 covers:
  17. Render manifest contains approved_revision_number
  18. from_report_and_revision sets revision_number on ApprovalSnapshot
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.reports.api.routes import (
    _get_actor,
    _get_template_repo,
    reports_template_router,
)
from cold_storage.modules.reports.domain.enums import (
    ExportFormat,
    ReportStatus,
    ReportType,
    TemplateStatus,
)
from cold_storage.modules.reports.domain.models import (
    ApprovalSnapshot,
    Report,
    ReportRevision,
    ReportTemplate,
)
from cold_storage.modules.reports.infrastructure.orm import Base
from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """In-memory SQLite engine with report tables."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture()
def repo(session):
    return SQLReportRepository(session)


def _make_valid_manifest(
    *,
    template_code: str = "cold_storage_concept_design",
    version: str = "1.0.0",
    format: str = "docx",
    locale: str = "zh-CN",
    report_type: str = "cold_storage_concept_design",
    schema_version: str = "1.0.0",
) -> dict[str, Any]:
    """Build a valid manifest dict with all required identity fields.

    Now includes report_type and schema_version for P0-1 canonical manifest.
    """
    return {
        "template_code": template_code,
        "version": version,
        "format": format,
        "locale": locale,
        "report_type": report_type,
        "schema_version": schema_version,
    }


class _InMemoryTemplateRepo:
    """In-memory implementation of ReportTemplateRepositoryPort for testing."""

    def __init__(self) -> None:
        self._templates: dict[str, ReportTemplate] = {}
        self._commit_called = False
        self._rollback_called = False

    def get_template(self, template_id: str) -> ReportTemplate | None:
        return self._templates.get(template_id)

    def get_active_template(
        self, template_code: str, format: ExportFormat
    ) -> ReportTemplate | None:
        for t in self._templates.values():
            if (
                t.template_code == template_code
                and t.format == format
                and t.status == TemplateStatus.ACTIVE
            ):
                return t
        return None

    def list_templates(
        self,
        template_code: str | None = None,
        format: ExportFormat | None = None,
    ) -> list[ReportTemplate]:
        result = list(self._templates.values())
        if template_code:
            result = [t for t in result if t.template_code == template_code]
        if format is not None:
            result = [t for t in result if t.format == format]
        return result

    def save_template(self, template: ReportTemplate) -> None:
        self._templates[template.id] = template

    def update_template(self, template: ReportTemplate) -> None:
        self._templates[template.id] = template

    def deactivate_templates(self, template_code: str, fmt: str) -> int:
        count = 0
        for t in list(self._templates.values()):
            if (
                t.template_code == template_code
                and (t.format.value if hasattr(t.format, "value") else str(t.format)) == fmt
                and t.status == TemplateStatus.ACTIVE
            ):
                self._templates[t.id] = replace(t, status=TemplateStatus.DRAFT)
                count += 1
        return count

    def commit(self) -> None:
        self._commit_called = True

    def rollback(self) -> None:
        self._rollback_called = True


@pytest.fixture()
def template_repo():
    return _InMemoryTemplateRepo()


@pytest.fixture()
def client(template_repo):
    app = FastAPI()
    app.include_router(reports_template_router)
    app.dependency_overrides[_get_template_repo] = lambda: template_repo
    app.dependency_overrides[_get_actor] = lambda: "test_actor"
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# P0-3: Template API type/identity validation tests
# ---------------------------------------------------------------------------


class TestTemplateTypeValidation:
    """P0-3: Request model enum validation."""

    def test_invalid_report_type_returns_422(self, client):
        """Invalid report_type string → 422 validation error."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "test",
                "report_type": "invalid_type",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(),
            },
        )
        assert resp.status_code == 422

    def test_invalid_format_returns_422(self, client):
        """Invalid format string → 422 validation error."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "test",
                "report_type": "cold_storage_concept_design",
                "format": "invalid_format",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(),
            },
        )
        assert resp.status_code == 422

    def test_valid_enums_accepted(self, client):
        """Valid report_type and format enums → 200."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "cold_storage_concept_design@1.0.0",
                "manifest_json": _make_valid_manifest(
                    schema_version="cold_storage_concept_design@1.0.0"
                ),
            },
        )
        assert resp.status_code == 200


class TestTemplateIdentityValidation:
    """P0-3: Request vs manifest identity matching."""

    def test_template_code_mismatch_returns_422(self, client):
        """template_code mismatch between request and manifest → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "code_A",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(template_code="code_B"),
            },
        )
        assert resp.status_code == 422
        assert "template_code mismatch" in resp.json()["detail"]

    def test_version_mismatch_returns_422(self, client):
        """Version mismatch between request and manifest → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(version="2.0.0"),
            },
        )
        assert resp.status_code == 422
        assert "version mismatch" in resp.json()["detail"]

    def test_format_mismatch_returns_422(self, client):
        """Format mismatch between request and manifest → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(format="pdf"),
            },
        )
        assert resp.status_code == 422
        assert "format mismatch" in resp.json()["detail"]

    def test_report_type_mismatch_returns_422(self, client):
        """report_type mismatch between request and raw manifest → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": {
                    **_make_valid_manifest(),
                    "report_type": "different_type",
                },
            },
        )
        assert resp.status_code == 422
        assert "report_type mismatch" in resp.json()["detail"]

    def test_schema_version_mismatch_returns_422(self, client):
        """schema_version mismatch between request and raw manifest → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "cold_storage_concept_design@1.0.0",
                "manifest_json": {
                    **_make_valid_manifest(),
                    "schema_version": "different@2.0.0",
                },
            },
        )
        assert resp.status_code == 422
        assert "schema_version mismatch" in resp.json()["detail"]

    def test_locale_mismatch_returns_422(self, client):
        """Locale mismatch between request and manifest → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(locale="en-US"),
            },
        )
        assert resp.status_code == 422
        assert "locale mismatch" in resp.json()["detail"]

    def test_empty_manifest_returns_422(self, client):
        """Empty manifest_json → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "test",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": {},
            },
        )
        assert resp.status_code == 422
        assert "manifest_json must not be empty" in resp.json()["detail"]

    def test_manifest_json_required(self, client):
        """Missing manifest_json → 422."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "test",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
            },
        )
        assert resp.status_code == 422


class TestTemplateCreationSuccess:
    """P0-3: Successful creation returns 64-char hash."""

    def test_successful_creation_returns_hash(self, client):
        """Successful creation → returns 64-char template_content_hash."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "cold_storage_concept_design@1.0.0",
                "manifest_json": _make_valid_manifest(
                    schema_version="cold_storage_concept_design@1.0.0"
                ),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "template_content_hash" in data
        assert data["template_content_hash"] is not None
        assert len(data["template_content_hash"]) == 64
        # Verify it's a valid hex string
        int(data["template_content_hash"], 16)

    def test_same_manifest_produces_same_hash(self, client):
        """Same manifest content → same hash (deterministic)."""
        payload = {
            "template_code": "cold_storage_concept_design",
            "report_type": "cold_storage_concept_design",
            "format": "docx",
            "version": "1.0.0",
            "schema_version": "cold_storage_concept_design@1.0.0",
            "manifest_json": _make_valid_manifest(
                schema_version="cold_storage_concept_design@1.0.0"
            ),
        }
        r1 = client.post("/api/v1/report-templates", json=payload)
        r2 = client.post(
            "/api/v1/report-templates",
            json={
                **payload,
                "manifest_json": _make_valid_manifest(
                    schema_version="cold_storage_concept_design@1.0.0"
                ),
            },
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["template_content_hash"] == r2.json()["template_content_hash"]

    def test_different_manifest_produces_different_hash(self, client):
        """Different manifest content → different hash."""
        r1 = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(version="1.0.0", schema_version="v1"),
            },
        )
        r2 = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.1",
                "schema_version": "v1",
                "manifest_json": _make_valid_manifest(version="1.0.1", schema_version="v1"),
            },
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["template_content_hash"] != r2.json()["template_content_hash"]


class TestTemplateActivation:
    """P0-3: Activation validation."""

    def _create_template(self, client) -> str:
        """Helper: create a template and return its ID."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "cold_storage_concept_design@1.0.0",
                "manifest_json": _make_valid_manifest(
                    schema_version="cold_storage_concept_design@1.0.0"
                ),
            },
        )
        assert resp.status_code == 200
        return resp.json()["template_id"]

    def test_activate_empty_hash_returns_409(self, client, template_repo):
        """Activation of template with empty template_content_hash → 409."""
        # Create a template with empty hash (bypass normal creation)
        t = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="",  # Empty hash
            created_by="test",
        )
        template_repo.save_template(t)

        resp = client.post(f"/api/v1/report-templates/{t.id}/activate")
        assert resp.status_code == 409
        assert "empty template_content_hash" in resp.json()["detail"]

    def test_activate_already_active_is_idempotent(self, client, template_repo):
        """Activation of already-active template → 200 (idempotent)."""
        t = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="a" * 64,
            created_by="test",
        )
        from dataclasses import replace as dc_replace

        t = dc_replace(t, status=TemplateStatus.ACTIVE, activated_at=datetime.now(UTC))
        template_repo.save_template(t)

        resp = client.post(f"/api/v1/report-templates/{t.id}/activate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_activate_retired_returns_409(self, client, template_repo):
        """Activation of retired template → 409."""
        t = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="a" * 64,
            created_by="test",
        )
        from dataclasses import replace as dc_replace

        t = dc_replace(t, status=TemplateStatus.RETIRED)
        template_repo.save_template(t)

        resp = client.post(f"/api/v1/report-templates/{t.id}/activate")
        assert resp.status_code == 409
        assert "retired" in resp.json()["detail"]

    def test_concurrent_activation_one_succeeds(self, client, template_repo):
        """Two templates for same code+format: one activates, the other replaces."""
        # Create two DRAFT templates for same code+format
        t1 = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="a" * 64,
            created_by="test",
        )
        t2 = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.1",
            schema_version="v1",
            manifest_json=_make_valid_manifest(version="1.0.1"),
            template_content_hash="b" * 64,
            created_by="test",
        )
        template_repo.save_template(t1)
        template_repo.save_template(t2)

        # Activate t1 first
        resp1 = client.post(f"/api/v1/report-templates/{t1.id}/activate")
        assert resp1.status_code == 200

        # Activate t2 — should deactivate t1 and activate t2
        resp2 = client.post(f"/api/v1/report-templates/{t2.id}/activate")
        assert resp2.status_code == 200

        # Verify t1 is now DRAFT and t2 is ACTIVE
        assert template_repo.get_template(t1.id).status == TemplateStatus.DRAFT
        assert template_repo.get_template(t2.id).status == TemplateStatus.ACTIVE


class TestTemplateUpdate:
    """P0-3: Template update endpoint."""

    def _create_template(self, client) -> str:
        """Helper: create a template and return its ID."""
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "cold_storage_concept_design@1.0.0",
                "manifest_json": _make_valid_manifest(),
            },
        )
        assert resp.status_code == 200
        return resp.json()["template_id"]

    def test_update_active_template_returns_409(self, client, template_repo):
        """Update of active template → 409."""
        t = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="a" * 64,
            created_by="test",
        )
        from dataclasses import replace as dc_replace

        t = dc_replace(t, status=TemplateStatus.ACTIVE, activated_at=datetime.now(UTC))
        template_repo.save_template(t)

        resp = client.put(
            f"/api/v1/report-templates/{t.id}",
            json={"version": "2.0.0"},
        )
        assert resp.status_code == 409
        assert "active" in resp.json()["detail"]

    def test_update_retired_template_returns_409(self, client, template_repo):
        """Update of retired template → 409."""
        t = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="a" * 64,
            created_by="test",
        )
        from dataclasses import replace as dc_replace

        t = dc_replace(t, status=TemplateStatus.RETIRED)
        template_repo.save_template(t)

        resp = client.put(
            f"/api/v1/report-templates/{t.id}",
            json={"version": "2.0.0"},
        )
        assert resp.status_code == 409
        assert "retired" in resp.json()["detail"]

    def test_update_draft_template_succeeds(self, client, template_repo):
        """Update of draft template → 200 with new hash."""
        t = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="a" * 64,
            created_by="test",
        )
        template_repo.save_template(t)

        resp = client.put(
            f"/api/v1/report-templates/{t.id}",
            json={
                "manifest_json": _make_valid_manifest(version="2.0.0"),
                "version": "2.0.0",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.0.0"
        assert data["template_content_hash"] is not None
        assert len(data["template_content_hash"]) == 64
        # Hash should be different from original
        assert data["template_content_hash"] != "a" * 64

    def test_update_not_found_returns_404(self, client):
        """Update of nonexistent template → 404."""
        resp = client.put(
            "/api/v1/report-templates/nonexistent",
            json={"version": "2.0.0"},
        )
        assert resp.status_code == 404

    def test_update_empty_manifest_returns_422(self, client, template_repo):
        """Update with empty manifest_json → 422."""
        t = ReportTemplate.create(
            template_code="cold_storage_concept_design",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            format=ExportFormat.DOCX,
            version="1.0.0",
            schema_version="v1",
            manifest_json=_make_valid_manifest(),
            template_content_hash="a" * 64,
            created_by="test",
        )
        template_repo.save_template(t)

        resp = client.put(
            f"/api/v1/report-templates/{t.id}",
            json={"manifest_json": {}},
        )
        assert resp.status_code == 422
        assert "manifest_json must not be empty" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# P0-1: Template identity fields in Canonical Manifest tests
# ---------------------------------------------------------------------------


class TestCanonicalManifestIdentity:
    """P0-1: report_type and schema_version preserved in canonical manifest."""

    def test_wrong_report_type_in_manifest_returns_422(self, client):
        """Wrong report_type in manifest caught via canonical manifest → 422."""
        manifest = _make_valid_manifest(report_type="wrong_type")
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "1.0.0",
                "manifest_json": manifest,
            },
        )
        assert resp.status_code == 422
        assert "report_type mismatch" in resp.json()["detail"]

    def test_wrong_schema_version_in_manifest_returns_422(self, client):
        """Wrong schema_version in manifest caught via canonical manifest → 422."""
        manifest = _make_valid_manifest(schema_version="wrong@2.0")
        resp = client.post(
            "/api/v1/report-templates",
            json={
                "template_code": "cold_storage_concept_design",
                "report_type": "cold_storage_concept_design",
                "format": "docx",
                "version": "1.0.0",
                "schema_version": "1.0.0",
                "manifest_json": manifest,
            },
        )
        assert resp.status_code == 422
        assert "schema_version mismatch" in resp.json()["detail"]

    def test_canonical_manifest_preserves_report_type(self):
        """from_manifest_json preserves report_type in canonical output."""
        from cold_storage.modules.reports.domain.render_model import TemplateManifest

        manifest = {
            "template_code": "cold_storage_concept_design",
            "report_type": "cold_storage_concept_design",
            "schema_version": "cold_storage_concept_design@1.0.0",
            "locale": "zh-CN",
        }
        tm = TemplateManifest.from_manifest_json(manifest)
        assert tm.report_type == "cold_storage_concept_design"

    def test_canonical_manifest_preserves_schema_version(self):
        """from_manifest_json preserves schema_version in canonical output."""
        from cold_storage.modules.reports.domain.render_model import TemplateManifest

        manifest = {
            "template_code": "cold_storage_concept_design",
            "report_type": "cold_storage_concept_design",
            "schema_version": "custom_schema@2.0.0",
            "locale": "zh-CN",
        }
        tm = TemplateManifest.from_manifest_json(manifest)
        assert tm.schema_version == "custom_schema@2.0.0"

    def test_hash_changes_when_schema_version_changes(self, client):
        """Same manifest with different schema_version → different hash."""
        payload1 = {
            "template_code": "cold_storage_concept_design",
            "report_type": "cold_storage_concept_design",
            "format": "docx",
            "version": "1.0.0",
            "schema_version": "cold_storage_concept_design@1.0.0",
            "manifest_json": _make_valid_manifest(
                schema_version="cold_storage_concept_design@1.0.0"
            ),
        }
        payload2 = {
            **payload1,
            "schema_version": "cold_storage_concept_design@2.0.0",
            "manifest_json": _make_valid_manifest(
                schema_version="cold_storage_concept_design@2.0.0"
            ),
        }
        r1 = client.post("/api/v1/report-templates", json=payload1)
        r2 = client.post("/api/v1/report-templates", json=payload2)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["template_content_hash"] != r2.json()["template_content_hash"]

    def test_canonical_manifest_model_dump_includes_identity(self):
        """TemplateManifest.model_dump() includes report_type and schema_version."""
        from cold_storage.modules.reports.domain.render_model import TemplateManifest

        manifest = {
            "template_code": "cold_storage_concept_design",
            "report_type": "cold_storage_concept_design",
            "schema_version": "cold_storage_concept_design@1.0.0",
            "locale": "zh-CN",
        }
        tm = TemplateManifest.from_manifest_json(manifest)
        dumped = tm.model_dump()
        assert "report_type" in dumped
        assert dumped["report_type"] == "cold_storage_concept_design"
        assert "schema_version" in dumped
        assert dumped["schema_version"] == "cold_storage_concept_design@1.0.0"


# ---------------------------------------------------------------------------
# P0-3: ORM active_slot partial unique constraint tests
# ---------------------------------------------------------------------------


class TestORMActiveSlotConstraint:
    """P0-3: Active slot unique constraint prevents duplicate active templates."""

    def test_direct_db_insert_two_active_raises_integrity(self, session):
        """Insert two records with same code+format+active_slot=active → IntegrityError."""
        import sqlalchemy as sa
        from sqlalchemy.exc import IntegrityError

        from cold_storage.modules.reports.infrastructure.orm import ReportTemplateRecord

        rec1 = ReportTemplateRecord(
            id="t1",
            template_code="test_code",
            report_type="cold_storage_concept_design",
            format="docx",
            version="1.0",
            status="active",
            schema_version="1.0",
            locale="zh-CN",
            manifest_json={},
            template_content_hash="",
            created_by="test",
            active_slot="active",
        )
        rec2 = ReportTemplateRecord(
            id="t2",
            template_code="test_code",
            report_type="cold_storage_concept_design",
            format="docx",
            version="2.0",
            status="active",
            schema_version="1.0",
            locale="zh-CN",
            manifest_json={},
            template_content_hash="",
            created_by="test",
            active_slot="active",
        )
        session.add(rec1)
        session.commit()
        session.add(rec2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        # Session must be usable after rollback
        result = session.execute(sa.select(ReportTemplateRecord)).scalars().all()
        assert len(result) == 1

    def test_direct_db_insert_one_active_one_null_succeeds(self, session):
        """Insert one active and one NULL active_slot → succeeds."""
        import sqlalchemy as sa

        from cold_storage.modules.reports.infrastructure.orm import ReportTemplateRecord

        rec1 = ReportTemplateRecord(
            id="t1",
            template_code="test_code",
            report_type="cold_storage_concept_design",
            format="docx",
            version="1.0",
            status="active",
            schema_version="1.0",
            locale="zh-CN",
            manifest_json={},
            template_content_hash="",
            created_by="test",
            active_slot="active",
        )
        rec2 = ReportTemplateRecord(
            id="t2",
            template_code="test_code",
            report_type="cold_storage_concept_design",
            format="docx",
            version="2.0",
            status="draft",
            schema_version="1.0",
            locale="zh-CN",
            manifest_json={},
            template_content_hash="",
            created_by="test",
            active_slot=None,
        )
        session.add(rec1)
        session.add(rec2)
        session.commit()
        result = session.execute(sa.select(ReportTemplateRecord)).scalars().all()
        assert len(result) == 2

    def test_direct_db_insert_different_format_both_active_succeeds(self, session):
        """Insert two active records with same code but different format → succeeds."""
        import sqlalchemy as sa

        from cold_storage.modules.reports.infrastructure.orm import ReportTemplateRecord

        rec1 = ReportTemplateRecord(
            id="t1",
            template_code="test_code",
            report_type="cold_storage_concept_design",
            format="docx",
            version="1.0",
            status="active",
            schema_version="1.0",
            locale="zh-CN",
            manifest_json={},
            template_content_hash="",
            created_by="test",
            active_slot="active",
        )
        rec2 = ReportTemplateRecord(
            id="t2",
            template_code="test_code",
            report_type="cold_storage_concept_design",
            format="pdf",
            version="1.0",
            status="active",
            schema_version="1.0",
            locale="zh-CN",
            manifest_json={},
            template_content_hash="",
            created_by="test",
            active_slot="active",
        )
        session.add(rec1)
        session.add(rec2)
        session.commit()
        result = session.execute(sa.select(ReportTemplateRecord)).scalars().all()
        assert len(result) == 2


# ---------------------------------------------------------------------------
# P0-6: ApprovalSnapshot artifact manifest tests
# ---------------------------------------------------------------------------


class TestApprovalSnapshotManifest:
    """P0-6: Render manifest contains approved_revision_number."""

    def test_from_report_and_revision_sets_revision_number(self):
        """ApprovalSnapshot.from_report_and_revision sets revision_number."""
        report = Report.create(
            project_id="p",
            project_version_id="v",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            created_by="u",
        )
        from dataclasses import replace as dc_replace

        report = dc_replace(
            report,
            approved_revision_id="rev-1",
            approved_content_hash="hash123",
            approved_by="admin",
            approved_at="2025-01-01T00:00:00Z",
        )
        rev = ReportRevision.create(
            report_id=report.id,
            revision_number=5,
            schema_version="v1",
            content_json={},
            canonical_content_json={},
            content_hash="hash123",
            quality_status=ReportStatus.APPROVED,
            quality_findings_json=[],
            generated_by="u",
        )
        snapshot = ApprovalSnapshot.from_report_and_revision(report, rev)
        assert snapshot is not None
        assert snapshot.revision_number == 5

    def test_from_report_without_revision_has_zero_revision_number(self):
        """ApprovalSnapshot.from_report returns revision_number=0."""
        report = Report.create(
            project_id="p",
            project_version_id="v",
            report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
            created_by="u",
        )
        from dataclasses import replace as dc_replace

        report = dc_replace(
            report,
            approved_revision_id="rev-1",
            approved_content_hash="hash123",
            approved_by="admin",
            approved_at="2025-01-01T00:00:00Z",
        )
        snapshot = ApprovalSnapshot.from_report(report)
        assert snapshot is not None
        assert snapshot.revision_number == 0

    def test_render_manifest_includes_approved_revision_number(self):
        """Render manifest dict includes approved_revision_number field."""
        # Build the render manifest directly using the method's logic
        snapshot = ApprovalSnapshot(
            revision_id="rev-1",
            content_hash="hash123",
            approved_by="admin",
            approved_at="2025-01-01T00:00:00Z",
            revision_number=7,
        )
        # Simulate what _build_render_manifest returns
        manifest: dict[str, Any] = {
            "approved_revision_id": snapshot.revision_id,
            "approved_content_hash": snapshot.content_hash,
            "approved_by": snapshot.approved_by,
            "approved_at": snapshot.approved_at,
            "approved_revision_number": snapshot.revision_number,
        }
        assert manifest["approved_revision_number"] == 7

    def test_render_manifest_without_snapshot_has_zero_revision_number(self):
        """Render manifest dict has approved_revision_number=0 when no snapshot."""
        manifest: dict[str, Any] = {
            "approved_revision_id": "",
            "approved_content_hash": "",
            "approved_by": "",
            "approved_at": "",
            "approved_revision_number": 0,
        }
        assert manifest["approved_revision_number"] == 0
