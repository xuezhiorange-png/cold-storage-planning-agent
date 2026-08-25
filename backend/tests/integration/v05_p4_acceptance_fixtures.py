"""Shared fixtures and assertions for V0.5 P4 five-stage acceptance matrix."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from fastapi.testclient import TestClient

from cold_storage.bootstrap.scheme_seed import demo_weight_set
from cold_storage.bootstrap.v05_local_sample import (
    EXPECTED_CANONICAL_CALCULATORS,
    hydrate_engineering_input_bundle,
    load_manifest,
    seed_v05_local_sample,
)
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    ProjectServicePersistedCalculationQuery,
)
from cold_storage.modules.reports.infrastructure.real_data_provider import RealReportDataProvider
from cold_storage.modules.schemes.application.service import SchemeService
from cold_storage.modules.schemes.infrastructure.repository import SchemeRepository

CANONICAL_CALCULATORS = frozenset(EXPECTED_CANONICAL_CALCULATORS)

STAGE_TO_CALCULATOR = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

EXPECTED_UPSTREAM_KEYS: dict[str, frozenset[str]] = {
    "cold_room_zone_plan": frozenset(),
    "cooling_load": frozenset({"zone"}),
    "equipment": frozenset({"cooling_load"}),
    "installed_power": frozenset({"equipment"}),
    "investment_estimate": frozenset({"zone", "power"}),
}


def calculations_by_name(calculations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in calculations:
        name = row.get("calculator_name")
        if isinstance(name, str):
            indexed[name] = row
    return indexed


def assert_canonical_five_persisted(
    calculations: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_name = calculations_by_name(calculations)
    missing = CANONICAL_CALCULATORS - set(by_name)
    assert not missing, f"missing canonical calculators: {sorted(missing)}"
    for name in CANONICAL_CALCULATORS:
        row = by_name[name]
        assert row.get("calculation_id"), f"{name} missing calculation_id"
        assert row.get("result_hash"), f"{name} missing result_hash"
        assert "requires_review" in row, f"{name} missing requires_review"
    return by_name


def assert_upstream_lineage_matches_p0(by_name: dict[str, dict[str, Any]]) -> None:
    stage_calc_ids = {
        stage: by_name[calculator]["calculation_id"]
        for stage, calculator in STAGE_TO_CALCULATOR.items()
    }
    for calculator_name, expected_upstream_stages in EXPECTED_UPSTREAM_KEYS.items():
        row = by_name[calculator_name]
        upstream = row.get("upstream_calculation_ids") or {}
        assert set(upstream.keys()) == set(expected_upstream_stages), (
            f"{calculator_name} upstream keys mismatch: {upstream.keys()}"
        )
        for stage in expected_upstream_stages:
            assert upstream[stage] == stage_calc_ids[stage], (
                f"{calculator_name} upstream {stage} does not bind persisted stage id"
            )


def build_bundle_from_manifest(
    manifest: dict[str, Any],
    *,
    project_id: str,
    project_version_id: str,
    version_number: int,
    version_status: str = "draft",
) -> dict[str, Any]:
    return hydrate_engineering_input_bundle(
        manifest,
        project_id=project_id,
        project_version_id=project_version_id,
        version_number=version_number,
        version_status=version_status,
    )


def execute_five_stage(
    client: TestClient,
    *,
    project_id: str,
    version_number: int,
    bundle: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    return client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
        json={"engineering_input_bundle": bundle, "idempotency_key": idempotency_key},
    ).json()


def create_project(client: TestClient, *, name: str | None = None) -> tuple[str, int, str]:
    created = client.post(
        "/api/v1/projects",
        json={
            "name": name or f"V05-P4 Acceptance {uuid.uuid4().hex[:8]}",
            "location": "山东",
            "product_category": "blueberry",
        },
    ).json()
    project_id = created["id"]
    version_number = created["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    return project_id, version_number, version["id"]


def seed_sample_project(client: TestClient, manifest: dict[str, Any] | None = None):
    return seed_v05_local_sample(client, manifest=manifest or load_manifest())


def workflow_calc_step(client: TestClient, project_id: str, version_number: int) -> dict[str, Any]:
    payload = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}/workflow").json()
    return next(step for step in payload["steps"] if step["step"] == "DETERMINISTIC_CALCULATION")


def assert_workflow_not_blocked_by_missing_canonical_slots(
    client: TestClient, project_id: str, version_number: int
) -> None:
    calc_step = workflow_calc_step(client, project_id, version_number)
    assert calc_step["status"] in {"COMPLETED", "REVIEW_REQUIRED", "STALE"}
    assert not any(
        blocker.get("code") == "CALCULATION_MISSING" for blocker in calc_step.get("blockers", [])
    )


def generate_scheme_from_persisted(session, project_id: str, version_number: int):
    scheme_service = SchemeService(session)
    repo = SchemeRepository(session)
    repo.save_weight_set(demo_weight_set())
    session.commit()
    return scheme_service.generate_scheme_run(
        project_id=project_id,
        version=version_number,
        profile_codes=["balanced"],
        weight_set_id="demo-weight-set-001",
        profile_parameters={},
    )


def read_report_sections_from_persisted(
    service, project_id: str, version_id: str
) -> list[dict[str, Any]]:
    query = ProjectServicePersistedCalculationQuery(service)
    provider = RealReportDataProvider(
        project_service=service,
        calculation_service=query,
    )
    return provider.get_calculation_results(project_id, version_id)


def _traverse_bundle_parent(bundle: dict, parts: list[str]):
    cursor: Any = bundle
    for part in parts[:-1]:
        if "[" in part:
            name, index_text = part.split("[", 1)
            index = int(index_text.rstrip("]"))
            cursor = cursor[name][index]
        else:
            cursor = cursor[part]
    return cursor, parts[-1]


def bundle_with_removed_key(bundle: dict[str, Any], dotted_path: str) -> dict[str, Any]:
    edited = copy.deepcopy(bundle)
    parts = dotted_path.split(".")
    cursor, last = _traverse_bundle_parent(edited, parts)
    if "[" in last:
        name, index_text = last.split("[", 1)
        index = int(index_text.rstrip("]"))
        del cursor[name][index]
    else:
        cursor.pop(last)
    return edited
