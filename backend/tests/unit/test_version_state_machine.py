"""Comprehensive tests for version state machine, immutability, and API integration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.application.service import ProjectService
from cold_storage.modules.projects.domain.models import (
    ALL_VERSION_STATUSES,
    SCHEMA_VERSION,
    InvalidVersionTransitionError,
    ProjectVersion,
    VersionImmutabilityError,
    validate_transition,
)

# ---------------------------------------------------------------------------
# Helper to walk version through the full approval workflow
# ---------------------------------------------------------------------------


def _approve_via_workflow(
    service: ProjectService, project_id: str, version_number: int, actor: str = "system"
) -> ProjectVersion:
    """Submit → review → approve."""
    service.submit_version(project_id, version_number, actor=actor)
    service.review_version(project_id, version_number, actor=actor)
    return service.approve_version(project_id, version_number, actor=actor)


# ===========================================================================
# 1. Domain model tests
# ===========================================================================


class TestProjectVersionDefaults:
    def test_new_version_starts_in_draft(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        assert v.status == "draft"

    def test_new_version_has_empty_snapshots(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        assert v.input_snapshot == {}
        assert v.calculation_snapshot == {}
        assert v.assumption_snapshot == {}

    def test_new_version_timestamps(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        assert v.created_at is not None
        assert v.updated_at is not None
        assert v.submitted_at is None
        assert v.reviewed_at is None
        assert v.approved_at is None
        assert v.archived_at is None

    def test_snapshot_metadata(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=3, change_summary="test")
        meta = v.snapshot_metadata()
        assert meta["schema_version"] == SCHEMA_VERSION
        assert meta["version_number"] == 3
        assert meta["parent_version_id"] is None

    def test_is_locked_false_for_draft(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        assert v.is_locked is False

    def test_is_locked_true_for_approved(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="approved"
        )
        assert v.is_locked is True

    def test_is_locked_true_for_archived(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="archived"
        )
        assert v.is_locked is True

    def test_parent_version_id(self) -> None:
        v = ProjectVersion(
            project_id="p1",
            version_number=2,
            change_summary="fork",
            parent_version_id="parent-123",
        )
        assert v.parent_version_id == "parent-123"


# ===========================================================================
# 2. State transition tests
# ===========================================================================


class TestVersionStateMachine:
    """Test the version state machine transitions."""

    def test_all_statuses_defined(self) -> None:
        expected = {"draft", "generated", "under_review", "reviewed", "approved", "archived"}
        assert expected == ALL_VERSION_STATUSES

    def test_valid_transition_draft_to_generated(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        v.transition_to("generated")
        assert v.status == "generated"

    def test_valid_transition_draft_to_under_review(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        v.transition_to("under_review")
        assert v.status == "under_review"
        assert v.submitted_at is not None

    def test_valid_transition_generated_to_under_review(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="generated"
        )
        v.transition_to("under_review")
        assert v.status == "under_review"

    def test_valid_transition_under_review_to_reviewed(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="under_review"
        )
        v.transition_to("reviewed")
        assert v.status == "reviewed"
        assert v.reviewed_at is not None

    def test_valid_transition_under_review_to_draft(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="under_review"
        )
        v.transition_to("draft")
        assert v.status == "draft"

    def test_valid_transition_reviewed_to_approved(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="reviewed"
        )
        v.transition_to("approved")
        assert v.status == "approved"
        assert v.approved_at is not None
        assert v.approved_by is not None

    def test_valid_transition_reviewed_to_draft(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="reviewed"
        )
        v.transition_to("draft")
        assert v.status == "draft"

    def test_valid_transition_approved_to_archived(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="approved"
        )
        v.transition_to("archived")
        assert v.status == "archived"
        assert v.archived_at is not None

    def test_full_approval_workflow(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        v.transition_to("under_review")
        v.transition_to("reviewed")
        v.transition_to("approved")
        assert v.status == "approved"
        assert v.is_locked is True

    def test_full_workflow_with_archive(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        v.transition_to("under_review")
        v.transition_to("reviewed")
        v.transition_to("approved")
        v.transition_to("archived")
        assert v.status == "archived"


class TestInvalidTransitions:
    """Test that invalid transitions raise errors."""

    def test_draft_to_approved_rejected(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        with pytest.raises(InvalidVersionTransitionError) as exc_info:
            v.transition_to("approved")
        assert exc_info.value.from_status == "draft"
        assert exc_info.value.to_status == "approved"

    def test_draft_to_reviewed_rejected(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        with pytest.raises(InvalidVersionTransitionError):
            v.transition_to("reviewed")

    def test_draft_to_archived_rejected(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        with pytest.raises(InvalidVersionTransitionError):
            v.transition_to("archived")

    def test_generated_to_approved_rejected(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="generated"
        )
        with pytest.raises(InvalidVersionTransitionError):
            v.transition_to("approved")

    def test_reviewed_to_archived_rejected(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="reviewed"
        )
        with pytest.raises(InvalidVersionTransitionError):
            v.transition_to("archived")

    def test_under_review_to_approved_rejected(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="under_review"
        )
        with pytest.raises(InvalidVersionTransitionError):
            v.transition_to("approved")

    def test_under_review_to_generated_rejected(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="under_review"
        )
        with pytest.raises(InvalidVersionTransitionError):
            v.transition_to("generated")

    def test_invalid_from_status_rejected(self) -> None:
        v = ProjectVersion(project_id="p1", version_number=1, change_summary="test")
        v.status = "bogus"
        with pytest.raises(InvalidVersionTransitionError):
            v.transition_to("draft")


class TestValidateTransitionFunction:
    def test_valid_transition_accepted(self) -> None:
        validate_transition("draft", "under_review")  # Should not raise

    def test_invalid_transition_rejected(self) -> None:
        with pytest.raises(InvalidVersionTransitionError):
            validate_transition("draft", "approved")


# ===========================================================================
# 3. Immutability tests
# ===========================================================================


class TestVersionImmutability:
    def test_approved_version_rejects_transition(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="approved"
        )
        with pytest.raises(VersionImmutabilityError) as exc_info:
            v.transition_to("draft")
        assert exc_info.value.status == "approved"
        assert exc_info.value.operation == "transition to 'draft'"

    def test_approved_version_allows_archive(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="approved"
        )
        v.transition_to("archived")  # Should not raise
        assert v.status == "archived"

    def test_archived_version_rejects_all_transitions(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="archived"
        )
        with pytest.raises(VersionImmutabilityError):
            v.transition_to("draft")
        with pytest.raises(VersionImmutabilityError):
            v.transition_to("approved")

    def test_assert_not_locked_raises_for_approved(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="approved"
        )
        with pytest.raises(VersionImmutabilityError):
            v.assert_not_locked("save inputs")

    def test_assert_not_locked_raises_for_archived(self) -> None:
        v = ProjectVersion(
            project_id="p1", version_number=1, change_summary="test", status="archived"
        )
        with pytest.raises(VersionImmutabilityError):
            v.assert_not_locked("modify")


# ===========================================================================
# 4. Service-level state machine tests
# ===========================================================================


class TestProjectServiceStateMachine:
    def test_submit_version(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        svc.submit_version(p.id, v.version_number)
        updated = svc.get_version(p.id, v.version_number)
        assert updated.status == "under_review"
        assert updated.submitted_at is not None

    def test_review_version(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        svc.submit_version(p.id, v.version_number)
        svc.review_version(p.id, v.version_number)
        updated = svc.get_version(p.id, v.version_number)
        assert updated.status == "reviewed"
        assert updated.reviewed_at is not None

    def test_approve_version_via_service(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        _approve_via_workflow(svc, p.id, v.version_number)
        updated = svc.get_version(p.id, v.version_number)
        assert updated.status == "approved"
        assert updated.approved_at is not None
        assert updated.approved_by == "system"

    def test_archive_version_via_service(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        _approve_via_workflow(svc, p.id, v.version_number)
        svc.archive_version(p.id, v.version_number)
        updated = svc.get_version(p.id, v.version_number)
        assert updated.status == "archived"
        assert updated.archived_at is not None

    def test_return_version_to_draft(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        svc.submit_version(p.id, v.version_number)
        svc.return_version(p.id, v.version_number)
        updated = svc.get_version(p.id, v.version_number)
        assert updated.status == "draft"

    def test_return_reviewed_to_draft(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        svc.submit_version(p.id, v.version_number)
        svc.review_version(p.id, v.version_number)
        svc.return_version(p.id, v.version_number)
        updated = svc.get_version(p.id, v.version_number)
        assert updated.status == "draft"

    def test_invalid_transition_raises_service(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        with pytest.raises(InvalidVersionTransitionError):
            svc.approve_version(p.id, v.version_number)  # draft → approved is invalid

    def test_save_inputs_on_draft_succeeds(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        result = svc.save_inputs(p.id, v.version_number, {"key": "value"}, actor="test")
        assert result.success is True

    def test_save_inputs_on_approved_fails(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        _approve_via_workflow(svc, p.id, v.version_number)
        result = svc.save_inputs(p.id, v.version_number, {"key": "value"}, actor="test")
        assert result.success is False
        assert result.error_code == "PROJECT_VERSION_LOCKED"

    def test_save_inputs_on_archived_fails(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        _approve_via_workflow(svc, p.id, v.version_number)
        svc.archive_version(p.id, v.version_number)
        result = svc.save_inputs(p.id, v.version_number, {"key": "value"}, actor="test")
        assert result.success is False
        assert result.error_code == "PROJECT_VERSION_LOCKED"

    def test_audit_events_record_transitions(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v = svc.create_version(p.id, "v1")
        svc.submit_version(p.id, v.version_number)
        svc.review_version(p.id, v.version_number)
        svc.approve_version(p.id, v.version_number)
        actions = [e.action for e in svc.audit_events]
        assert "submit_version" in actions
        assert "review_version" in actions
        assert "approve_project_version" in actions


# ===========================================================================
# 5. create_version_from tests
# ===========================================================================


class TestCreateVersionFrom:
    def test_creates_new_version_with_parent(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v1 = svc.create_version(p.id, "v1")
        svc.save_inputs(p.id, v1.version_number, {"data": "original"}, actor="test")
        _approve_via_workflow(svc, p.id, v1.version_number)

        v2 = svc.create_version_from(p.id, v1.version_number, "v2 from approved")
        assert v2.parent_version_id == v1.id
        assert v2.version_number == 2
        assert v2.status == "draft"
        assert v2.input_snapshot == {"data": "original"}

    def test_new_version_is_editable(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        v1 = svc.create_version(p.id, "v1")
        _approve_via_workflow(svc, p.id, v1.version_number)

        v2 = svc.create_version_from(p.id, v1.version_number, "v2")
        result = svc.save_inputs(p.id, v2.version_number, {"updated": True}, actor="test")
        assert result.success is True


# ===========================================================================
# 6. update_project tests
# ===========================================================================


class TestUpdateProject:
    def test_update_name(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Old", "Loc", "blueberry")
        updated = svc.update_project(p.id, name="New")
        assert updated.name == "New"
        assert updated.location == "Loc"

    def test_update_location(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "OldLoc", "blueberry")
        updated = svc.update_project(p.id, location="NewLoc")
        assert updated.location == "NewLoc"

    def test_update_creates_audit_event(self) -> None:
        svc = ProjectService()
        p = svc.create_project("Test", "Loc", "blueberry")
        svc.update_project(p.id, name="Updated")
        actions = [e.action for e in svc.audit_events]
        assert "update_project" in actions


# ===========================================================================
# 7. API integration tests
# ===========================================================================


class TestVersionStateMachineAPI:
    """Test the new API endpoints for the version state machine."""

    def _create_project(self, client: TestClient) -> tuple[str, int]:
        created = client.post(
            "/api/v1/projects",
            json={
                "name": "API Test Project",
                "location": "Test Location",
                "product_category": "blueberry",
            },
        ).json()
        return created["id"], created["current_version_number"]

    def test_submit_version_endpoint(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        resp = client.post(f"/api/v1/projects/{pid}/versions/{vid}/submit")
        assert resp.status_code == 200
        assert resp.json()["status"] == "under_review"

    def test_review_version_endpoint(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        client.post(f"/api/v1/projects/{pid}/versions/{vid}/submit")
        resp = client.post(f"/api/v1/projects/{pid}/versions/{vid}/review")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reviewed"

    def test_approve_version_endpoint(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        client.post(f"/api/v1/projects/{pid}/versions/{vid}/submit")
        client.post(f"/api/v1/projects/{pid}/versions/{vid}/review")
        resp = client.post(f"/api/v1/projects/{pid}/versions/{vid}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_archive_version_endpoint(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        client.post(f"/api/v1/projects/{pid}/versions/{vid}/submit")
        client.post(f"/api/v1/projects/{pid}/versions/{vid}/review")
        client.post(f"/api/v1/projects/{pid}/versions/{vid}/approve")
        resp = client.post(f"/api/v1/projects/{pid}/versions/{vid}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    def test_return_version_endpoint(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        client.post(f"/api/v1/projects/{pid}/versions/{vid}/submit")
        resp = client.post(f"/api/v1/projects/{pid}/versions/{vid}/return")
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    def test_invalid_transition_returns_409(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        resp = client.post(f"/api/v1/projects/{pid}/versions/{vid}/approve")
        assert resp.status_code == 409

    def test_cannot_approve_draft_version(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        resp = client.post(f"/api/v1/projects/{pid}/versions/{vid}/approve")
        assert resp.status_code == 409
        assert "Invalid transition" in resp.json()["detail"]

    def test_update_project_endpoint(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, _ = self._create_project(client)

        resp = client.patch(
            f"/api/v1/projects/{pid}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_create_version_from_endpoint(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        # Approve the first version through the workflow
        client.post(f"/api/v1/projects/{pid}/versions/{vid}/submit")
        client.post(f"/api/v1/projects/{pid}/versions/{vid}/review")
        client.post(f"/api/v1/projects/{pid}/versions/{vid}/approve")

        # Create a new version from the approved one
        resp = client.post(
            f"/api/v1/projects/{pid}/versions/{vid}/create-from",
            json={"source_version": vid, "change_summary": "New draft from approved"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["parent_version_id"] is not None
        assert data["version_number"] == 2

    def test_version_response_includes_new_fields(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        resp = client.get(f"/api/v1/projects/{pid}/versions/{vid}")
        data = resp.json()
        assert "calculation_snapshot" in data
        assert "assumption_snapshot" in data
        assert "parent_version_id" in data
        assert "submitted_at" in data
        assert "reviewed_at" in data
        assert "approved_at" in data
        assert "approved_by" in data
        assert "archived_at" in data

    def test_list_versions_includes_new_fields(self) -> None:
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        resp = client.get(f"/api/v1/projects/{pid}/versions")
        versions = resp.json()
        assert len(versions) == 1
        assert "parent_version_id" in versions[0]
        assert "submitted_at" in versions[0]
        assert "approved_at" in versions[0]

    def test_full_workflow_via_api(self) -> None:
        """End-to-end test: create project, walk version through full workflow."""
        client = TestClient(create_app(project_service=ProjectService()))
        pid, vid = self._create_project(client)

        # Save inputs on draft
        client.put(
            f"/api/v1/projects/{pid}/versions/{vid}/inputs",
            json={"inputs": {"daily_inbound_mass_kg": 25000}},
        )

        # Submit
        r = client.post(f"/api/v1/projects/{pid}/versions/{vid}/submit")
        assert r.json()["status"] == "under_review"

        # Cannot save inputs on submitted version? Actually, the state machine
        # only locks approved/archived. Under review is still editable.
        r = client.put(
            f"/api/v1/projects/{pid}/versions/{vid}/inputs",
            json={"inputs": {"daily_inbound_mass_kg": 30000}},
        )
        assert r.json()["success"] is True

        # Review
        r = client.post(f"/api/v1/projects/{pid}/versions/{vid}/review")
        assert r.json()["status"] == "reviewed"

        # Approve
        r = client.post(f"/api/v1/projects/{pid}/versions/{vid}/approve")
        assert r.json()["status"] == "approved"

        # Cannot modify approved version
        r = client.put(
            f"/api/v1/projects/{pid}/versions/{vid}/inputs",
            json={"inputs": {"daily_inbound_mass_kg": 50000}},
        )
        assert r.json()["error"]["code"] == "PROJECT_VERSION_LOCKED"

        # Create new version from approved
        r = client.post(
            f"/api/v1/projects/{pid}/versions/{vid}/create-from",
            json={"source_version": vid, "change_summary": "Revision"},
        )
        assert r.json()["status"] == "draft"
        assert r.json()["parent_version_id"] is not None

        # Archive
        r = client.post(f"/api/v1/projects/{pid}/versions/{vid}/archive")
        assert r.json()["status"] == "archived"

        # Cannot modify archived version
        r = client.put(
            f"/api/v1/projects/{pid}/versions/{vid}/inputs",
            json={"inputs": {"data": "bad"}},
        )
        assert r.json()["error"]["code"] == "PROJECT_VERSION_LOCKED"
