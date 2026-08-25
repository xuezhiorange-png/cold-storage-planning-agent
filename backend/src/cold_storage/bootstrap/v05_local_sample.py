"""Seed the V0.5 local five-stage workbench sample through current main APIs.

The loader uses the public project and five-stage-execution endpoints only.
It does not invoke planning-run or Alembic.

Database schema must already be at Alembic head (for example via ``make migrate``)
before running this module.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import create_database_project_service

SAMPLE_ID = "v05-local-workbench"
MANIFEST_RELATIVE_PATH = Path("samples") / SAMPLE_ID / "manifest.json"
REPO_ROOT = Path(__file__).resolve().parents[4]
EXPECTED_CANONICAL_CALCULATORS = (
    "cold_room_zone_plan",
    "cooling_load",
    "equipment",
    "installed_power",
    "investment_estimate",
)


@dataclass(frozen=True, slots=True)
class SeededSampleProject:
    sample_id: str
    project_id: str
    project_code: str
    version_number: int
    project_name: str
    created: bool
    five_stage_success: bool
    idempotent_replay: bool
    persisted_calculator_names: tuple[str, ...]
    source_binding_id: str | None


def manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / MANIFEST_RELATIVE_PATH


def load_manifest(repo_root: Path | None = None) -> dict[str, Any]:
    path = manifest_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"V0.5 local sample manifest not found: {path}")
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("sample_id") != SAMPLE_ID:
        raise ValueError(f"unexpected sample_id in manifest: {manifest.get('sample_id')!r}")
    return cast(dict[str, Any], manifest)


def _find_project_by_name(client: TestClient, project_name: str) -> dict[str, Any] | None:
    for project in client.get("/api/v1/projects").json():
        if project.get("name") == project_name:
            return cast(dict[str, Any], project)
    return None


def _persisted_calculator_names(
    client: TestClient,
    project_id: str,
    version_number: int,
) -> tuple[str, ...]:
    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    return tuple(item["calculator_name"] for item in calculations)


def _bundle_leaf(
    value: Any,
    *,
    unit: str | None = None,
    state: str = "provided",
    source_type: str = "user",
    validity_status: str = "unverified",
    requires_review: bool = True,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "state": state,
        "source_type": source_type,
        "validity_status": validity_status,
        "requires_review": requires_review,
    }


def hydrate_engineering_input_bundle(
    manifest: dict[str, Any],
    *,
    project_id: str,
    project_version_id: str,
    version_number: int,
    version_status: str = "draft",
) -> dict[str, Any]:
    """Fill persisted identity leaves from the live project version."""
    bundle = copy.deepcopy(manifest["engineering_input_bundle"])
    identity = bundle.setdefault("project_version_identity", {})
    identity["project_id"] = _bundle_leaf(
        project_id,
        unit=None,
        source_type="persisted",
        validity_status="verified",
        requires_review=False,
    )
    identity["project_version_id"] = _bundle_leaf(
        project_version_id,
        unit=None,
        source_type="persisted",
        validity_status="verified",
        requires_review=False,
    )
    identity["version_number"] = _bundle_leaf(
        version_number,
        unit=None,
        source_type="persisted",
        validity_status="verified",
        requires_review=False,
    )
    identity["version_status"] = _bundle_leaf(
        version_status,
        unit=None,
        source_type="persisted",
        validity_status="verified",
        requires_review=False,
    )
    identity["is_archived"] = _bundle_leaf(
        version_status == "archived",
        unit=None,
        source_type="persisted",
        validity_status="verified",
        requires_review=False,
    )
    return cast(dict[str, Any], bundle)


def seed_v05_local_sample(
    client: TestClient,
    *,
    manifest: dict[str, Any] | None = None,
) -> SeededSampleProject:
    manifest = manifest or load_manifest()
    project_spec = manifest["project"]
    project_name = project_spec["name"]
    execution_spec = manifest.get("five_stage_execution") or {}
    idempotency_key = execution_spec.get("idempotency_key")
    if not idempotency_key:
        raise ValueError("manifest.five_stage_execution.idempotency_key is required")

    existing = _find_project_by_name(client, project_name)
    created = existing is None

    if existing is None:
        created_project = client.post(
            "/api/v1/projects",
            json={
                "name": project_name,
                "location": project_spec["location"],
                "product_category": project_spec["product_category"],
            },
        )
        created_project.raise_for_status()
        project = created_project.json()
    else:
        project = existing

    project_id = project["id"]
    version_number = project["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    version_id = version["id"]
    version_status = version.get("status", "draft")

    persisted_before = set(_persisted_calculator_names(client, project_id, version_number))
    idempotent_replay = False
    source_binding_id: str | None = None
    if persisted_before >= set(EXPECTED_CANONICAL_CALCULATORS):
        five_stage_success = True
    else:
        bundle = hydrate_engineering_input_bundle(
            manifest,
            project_id=project_id,
            project_version_id=version_id,
            version_number=version_number,
            version_status=version_status,
        )
        execution_response = client.post(
            f"/api/v1/projects/{project_id}/versions/{version_number}/five-stage-execution",
            json={
                "engineering_input_bundle": bundle,
                "idempotency_key": idempotency_key,
            },
        )
        execution_response.raise_for_status()
        execution_payload = execution_response.json()
        if execution_payload.get("error"):
            raise RuntimeError(
                f"five-stage-execution failed for sample project: {execution_payload}"
            )
        five_stage_success = execution_payload.get("success") is True
        idempotent_replay = execution_payload.get("idempotent_replay") is True
        source_binding_id = execution_payload.get("source_binding_id")
        if not five_stage_success:
            raise RuntimeError(
                f"five-stage-execution failed for sample project: {execution_payload}"
            )

    persisted_names = _persisted_calculator_names(client, project_id, version_number)
    missing = [name for name in EXPECTED_CANONICAL_CALCULATORS if name not in persisted_names]
    if missing:
        raise RuntimeError(f"sample project is missing canonical calculators: {missing}")

    return SeededSampleProject(
        sample_id=manifest["sample_id"],
        project_id=project_id,
        project_code=project["code"],
        version_number=version_number,
        project_name=project_name,
        created=created,
        five_stage_success=five_stage_success,
        idempotent_replay=idempotent_replay,
        persisted_calculator_names=persisted_names,
        source_binding_id=source_binding_id,
    )


def _resolve_database_url(database_url: str | None) -> str:
    if database_url is not None:
        return database_url
    default_sqlite_path = REPO_ROOT / "cold_storage_dev.db"
    sqlite_path = Path(os.environ.get("COLD_STORAGE_SQLITE_PATH", default_sqlite_path))
    if not sqlite_path.is_absolute():
        sqlite_path = REPO_ROOT / sqlite_path
    return f"sqlite:///{sqlite_path}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed the V0.5 local five-stage workbench sample via current main APIs. "
            "Run `make migrate` first."
        )
    )
    parser.add_argument(
        "--database-url",
        help=(
            "Optional SQLAlchemy database URL. "
            "Defaults to COLD_STORAGE_SQLITE_PATH or ./cold_storage_dev.db."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the seeded sample summary as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    database_url = _resolve_database_url(args.database_url)

    service = create_database_project_service(database_url)
    with TestClient(create_app(project_service=service)) as client:
        seeded = seed_v05_local_sample(client)

    summary = {
        "sample_id": seeded.sample_id,
        "project_id": seeded.project_id,
        "project_code": seeded.project_code,
        "version_number": seeded.version_number,
        "project_name": seeded.project_name,
        "created": seeded.created,
        "five_stage_success": seeded.five_stage_success,
        "idempotent_replay": seeded.idempotent_replay,
        "source_binding_id": seeded.source_binding_id,
        "persisted_calculator_names": list(seeded.persisted_calculator_names),
        "workbench_url_hint": (
            "Open http://localhost:5173/workbench/engineering-inputs "
            "and select the seeded project, "
            f"or set localStorage key cold_storage_workbench_context to "
            f'{{"projectId":"{seeded.project_id}","versionNumber":{seeded.version_number}}}.'
        ),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"V05_LOCAL_SAMPLE_PROJECT_ID={seeded.project_id}")
        print(f"V05_LOCAL_SAMPLE_PROJECT_CODE={seeded.project_code}")
        print(f"V05_LOCAL_SAMPLE_VERSION={seeded.version_number}")
        print(f"V05_LOCAL_SAMPLE_CREATED={'yes' if seeded.created else 'no'}")
        print("V05_LOCAL_SAMPLE_PERSISTED=" + ",".join(seeded.persisted_calculator_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
