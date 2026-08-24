"""V04-P5 controlled acceptance integration matrix (sqlite only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v04_local_sample import load_manifest, seed_v04_local_sample
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.projects.infrastructure.orm import Base
from cold_storage.modules.workflow.application.knowledge_provenance import (
    assess_knowledge_provenance,
    enrich_knowledge_provenance_projection,
)

REQUIRED_PERSISTED_CALCULATORS = frozenset(
    {
        "cold_room_zone_plan",
        "investment_estimate",
        "power_configuration",
    }
)

KNOWLEDGE_PROVENANCE_TOP_LEVEL_FIELDS = frozenset(
    {
        "required",
        "available",
        "status",
        "blockers",
        "source_references",
    }
)

KNOWLEDGE_SOURCE_REFERENCE_DISPLAY_FIELDS = frozenset(
    {
        "revision_id",
        "document_id",
        "document_code",
        "document_title",
        "content_sha256",
        "original_filename",
        "version_label",
        "revision_number",
        "review_status",
        "requires_review",
        "requires_ocr",
        "ingestion_status",
        "page_evidence",
        "page_evidence_available",
    }
)


def _create_sqlite_client(tmp_path: Path, db_name: str) -> tuple[TestClient, str]:
    database_url = f"sqlite:///{tmp_path / db_name}"
    service = create_database_project_service(database_url)
    Base.metadata.create_all(service.engine)
    return TestClient(create_app(project_service=service)), database_url


def _calculator_names(client: TestClient, project_id: str, version_number: int) -> set[str]:
    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    return {cast(dict[str, Any], row)["calculator_name"] for row in calculations}


def test_v04_p5_sample_seed_persists_required_calculators(tmp_path: Path) -> None:
    client, _database_url = _create_sqlite_client(tmp_path, "v04-p5-seed.db")
    manifest = load_manifest()
    seeded = seed_v04_local_sample(client, manifest=manifest)

    assert seeded.planning_run_success is True
    calculator_names = set(seeded.persisted_calculator_names)
    assert calculator_names >= REQUIRED_PERSISTED_CALCULATORS

    power_configuration = next(
        row
        for row in client.get(
            f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/calculations"
        ).json()
        if row["calculator_name"] == "power_configuration"
    )
    equipment_name = power_configuration["result_snapshot"]["result"]["equipment_rows"][0]["name"]
    assert equipment_name == "制冷压缩机组"


def test_v04_p5_fail_closed_without_persisted_runs(tmp_path: Path) -> None:
    client, _database_url = _create_sqlite_client(tmp_path, "v04-p5-fail-closed.db")
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "V04-P5 fail-closed",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]

    client.put(
        f"/api/v1/projects/{project_id}/versions/{version_number}/inputs",
        json={
            "inputs": {
                "daily_inbound_mass_kg": 25_000,
                "working_time_h_per_day": 16,
                "utilization_factor": 0.85,
                "finished_storage_days": 2.5,
                "packaging_storage_days": 3,
                "reserve_factor": 1.05,
            }
        },
    )

    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    assert calculations == []

    workflow = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/workflow"
    ).json()
    assert workflow["calculations"]["runs"] == []

    knowledge_step = next(
        step for step in workflow["steps"] if step["step"] == "KNOWLEDGE_PROVENANCE"
    )
    assert knowledge_step["status"] == "NOT_APPLICABLE"


def test_v04_p5_workflow_exposes_knowledge_provenance_projection(tmp_path: Path) -> None:
    client, _database_url = _create_sqlite_client(tmp_path, "v04-p5-provenance.db")
    seeded = seed_v04_local_sample(client)

    workflow = client.get(
        f"/api/v1/projects/{seeded.project_id}/versions/{seeded.version_number}/workflow"
    ).json()
    provenance = cast(dict[str, Any], workflow["knowledge_provenance"])
    assert set(provenance) >= KNOWLEDGE_PROVENANCE_TOP_LEVEL_FIELDS

    baseline = assess_knowledge_provenance(
        depends_on_knowledge=False,
        knowledge_revisions=[],
        page_evidence_by_revision={},
    )
    assert provenance["required"] == baseline["required"]
    assert provenance["status"] == baseline["status"]
    assert provenance["blockers"] == baseline["blockers"]
    assert provenance["available"] == baseline["available"]
    assert provenance["status"] == "NOT_REQUIRED"
    assert provenance["source_references"] == []

    enriched = enrich_knowledge_provenance_projection(
        baseline,
        knowledge_revisions=[
            {
                "id": "krev-display-check",
                "document_id": "doc-display-check",
                "content_sha256": "sha-display",
                "requires_review": False,
                "requires_ocr": True,
                "ingestion_status": "indexed",
                "original_filename": "manual.pdf",
                "version_label": "v1",
                "revision_number": 1,
                "review_status": "approved",
            }
        ],
        page_evidence_by_revision={
            "krev-display-check": [
                {
                    "source_page_evidence_id": "spe-display-check",
                    "page_number": 1,
                    "extraction_method": "ocr",
                    "extraction_status": "completed",
                    "is_complete": True,
                    "is_ocr_derived": True,
                }
            ]
        },
        document_summaries={"doc-display-check": {"code": "KB-P5", "title": "P5 display check"}},
    )
    display_source = cast(dict[str, Any], enriched["source_references"][0])
    assert set(display_source) >= KNOWLEDGE_SOURCE_REFERENCE_DISPLAY_FIELDS
    assert display_source["document_code"] == "KB-P5"
    assert display_source["page_evidence_available"] is True
    assert enriched["status"] == baseline["status"]


def test_v04_p5_sqlite_reopen_preserves_calculation_rows(tmp_path: Path) -> None:
    client, database_url = _create_sqlite_client(tmp_path, "v04-p5-reopen.db")
    seeded = seed_v04_local_sample(client)

    reopened_service = create_database_project_service(database_url)
    reopened_client = TestClient(create_app(project_service=reopened_service))
    calculator_names = _calculator_names(
        reopened_client,
        seeded.project_id,
        seeded.version_number,
    )
    assert calculator_names == REQUIRED_PERSISTED_CALCULATORS
