"""Seed the V0.4 local workbench sample project through current main APIs.

The loader uses the public project and planning-run endpoints only. It does not
invoke a second calculator or the production orchestration fixture.

Database schema must already be at Alembic head (for example via ``make migrate``)
before running this module.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.infrastructure.database import create_database_project_service

SAMPLE_ID = "v04-local-workbench"
MANIFEST_RELATIVE_PATH = Path("samples") / SAMPLE_ID / "manifest.json"
REPO_ROOT = Path(__file__).resolve().parents[4]
EXPECTED_PERSISTED_CALCULATORS = ("cold_room_zone_plan", "investment_estimate")


@dataclass(frozen=True, slots=True)
class SeededSampleProject:
    sample_id: str
    project_id: str
    project_code: str
    version_number: int
    project_name: str
    created: bool
    planning_run_success: bool
    persisted_calculator_names: tuple[str, ...]


def manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / MANIFEST_RELATIVE_PATH


def load_manifest(repo_root: Path | None = None) -> dict[str, Any]:
    path = manifest_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"V0.4 local sample manifest not found: {path}")
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("sample_id") != SAMPLE_ID:
        raise ValueError(f"unexpected sample_id in manifest: {manifest.get('sample_id')!r}")
    return manifest


def _find_project_by_name(client: TestClient, project_name: str) -> dict[str, Any] | None:
    for project in client.get("/api/v1/projects").json():
        if project.get("name") == project_name:
            return project
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


def seed_v04_local_sample(
    client: TestClient,
    *,
    manifest: dict[str, Any] | None = None,
) -> SeededSampleProject:
    manifest = manifest or load_manifest()
    project_spec = manifest["project"]
    project_name = project_spec["name"]
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

    save_response = client.put(
        f"/api/v1/projects/{project_id}/versions/{version_number}/inputs",
        json={"inputs": manifest["inputs"]},
    )
    save_response.raise_for_status()
    if save_response.json() != {"success": True}:
        raise RuntimeError(f"failed to save sample inputs: {save_response.json()}")

    persisted_before = set(_persisted_calculator_names(client, project_id, version_number))
    planning_request = manifest.get("planning_run_request") or {}
    if persisted_before >= set(EXPECTED_PERSISTED_CALCULATORS):
        planning_run_success = True
    else:
        planning_response = client.post(
            f"/api/v1/projects/{project_id}/versions/{version_number}/planning-run",
            json=planning_request,
        )
        planning_response.raise_for_status()
        planning_payload = planning_response.json()
        planning_run_success = planning_payload.get("success") is True
        if not planning_run_success:
            raise RuntimeError(f"planning-run failed for sample project: {planning_payload}")

    persisted_names = _persisted_calculator_names(client, project_id, version_number)
    missing = [name for name in EXPECTED_PERSISTED_CALCULATORS if name not in persisted_names]
    if missing:
        raise RuntimeError(f"sample project is missing persisted calculators: {missing}")

    return SeededSampleProject(
        sample_id=manifest["sample_id"],
        project_id=project_id,
        project_code=project["code"],
        version_number=version_number,
        project_name=project_name,
        created=created,
        planning_run_success=planning_run_success,
        persisted_calculator_names=persisted_names,
    )


def _resolve_database_url(database_url: str | None) -> str:
    if database_url is not None:
        return database_url
    sqlite_path = Path(os.environ.get("COLD_STORAGE_SQLITE_PATH", REPO_ROOT / "cold_storage_dev.db"))
    if not sqlite_path.is_absolute():
        sqlite_path = REPO_ROOT / sqlite_path
    return f"sqlite:///{sqlite_path}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed the V0.4 local workbench sample project via current main APIs. "
            "Run `make migrate` first."
        )
    )
    parser.add_argument(
        "--database-url",
        help="Optional SQLAlchemy database URL. Defaults to COLD_STORAGE_SQLITE_PATH or ./cold_storage_dev.db.",
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
        seeded = seed_v04_local_sample(client)

    summary = {
        "sample_id": seeded.sample_id,
        "project_id": seeded.project_id,
        "project_code": seeded.project_code,
        "version_number": seeded.version_number,
        "project_name": seeded.project_name,
        "created": seeded.created,
        "planning_run_success": seeded.planning_run_success,
        "persisted_calculator_names": list(seeded.persisted_calculator_names),
        "workbench_url_hint": (
            "Open http://localhost:5173 and select the seeded project, "
            f"or set localStorage key cold_storage_workbench_context to "
            f'{{"projectId":"{seeded.project_id}","versionNumber":{seeded.version_number}}}.'
        ),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"V04_LOCAL_SAMPLE_PROJECT_ID={seeded.project_id}")
        print(f"V04_LOCAL_SAMPLE_PROJECT_CODE={seeded.project_code}")
        print(f"V04_LOCAL_SAMPLE_VERSION={seeded.version_number}")
        print(f"V04_LOCAL_SAMPLE_CREATED={'yes' if seeded.created else 'no'}")
        print(
            "V04_LOCAL_SAMPLE_PERSISTED="
            + ",".join(seeded.persisted_calculator_names)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
