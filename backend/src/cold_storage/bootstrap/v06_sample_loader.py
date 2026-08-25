"""Seed the V0.6 formal delivery sample through current public APIs.

The loader uses project, five-stage-execution, scheme-runs, and report
endpoints only. It does not invoke planning-run or Alembic.

Database schema must already be at Alembic head (for example via ``make migrate``)
before running this module.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.v05_local_sample import (
    EXPECTED_CANONICAL_CALCULATORS,
    hydrate_engineering_input_bundle,
)
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.reports.api.routes import _get_actor

SAMPLE_ID = "v06-formal-delivery"
MANIFEST_RELATIVE_PATH = Path("samples") / SAMPLE_ID / "manifest.json"
REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEME_FAIL_CLOSED_REASON = (
    "Weight set is available via GET /api/v1/demo/scheme-comparison, but POST "
    ".../scheme-runs persists legacy source_mode runs that block report assembly "
    "production review authority. Reports continue from persisted five-stage results "
    "without scheme_comparison on this operator path."
)
TRUSTED_SEED_ACTOR = "v06-local-trusted-reviewer"
TEMPLATE_VERSION = "1.0.0"
FORMAL_LOCALES = ("zh-CN", "en-US")
FORMAL_FORMATS = ("docx", "pdf")
_ENV_KEYS_TO_ISOLATE = (
    "SQLITE_PATH",
    "COLD_STORAGE_SQLITE_PATH",
    "COLD_STORAGE_DATABASE_BACKEND",
    "COLD_STORAGE_STORAGE_DIR",
)


@dataclass(frozen=True, slots=True)
class SchemeSeedResult:
    attempted: bool
    success: bool
    scheme_run_id: str | None
    fail_closed_reason: str | None


@dataclass(frozen=True, slots=True)
class FormalRenderResult:
    locale: str
    export_format: str
    status_code: int
    artifact_id: str | None
    file_sha256: str | None
    fail_closed: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SeededV06Sample:
    sample_id: str
    project_id: str
    project_code: str
    version_number: int
    project_name: str
    version_id: str
    created: bool
    five_stage_success: bool
    idempotent_replay: bool
    persisted_calculator_names: tuple[str, ...]
    source_binding_id: str | None
    scheme: SchemeSeedResult
    report_id: str | None = None
    revision_number: int | None = None
    revision_content_hash: str | None = None
    review_closed: bool = False
    review_fail_closed_reason: str | None = None
    submit_review_status_code: int | None = None
    calculation_ids: dict[str, str] = field(default_factory=dict)
    calculation_hashes: dict[str, str] = field(default_factory=dict)
    formal_renders: tuple[FormalRenderResult, ...] = ()
    restart_verified: bool = False


def manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / MANIFEST_RELATIVE_PATH


def load_manifest(repo_root: Path | None = None) -> dict[str, Any]:
    path = manifest_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"V0.6 sample manifest not found: {path}")
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("sample_id") != SAMPLE_ID:
        raise ValueError(f"unexpected sample_id in manifest: {manifest.get('sample_id')!r}")
    return cast(dict[str, Any], manifest)


def _snapshot_env() -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in _ENV_KEYS_TO_ISOLATE}


def _restore_env(snapshot: dict[str, str | None]) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _configure_database_env(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        sqlite_path = database_url.removeprefix("sqlite:///")
        os.environ["SQLITE_PATH"] = sqlite_path
        os.environ["COLD_STORAGE_SQLITE_PATH"] = sqlite_path
        os.environ["COLD_STORAGE_DATABASE_BACKEND"] = "sqlite"
        return
    if database_url.startswith("postgresql"):
        os.environ["COLD_STORAGE_DATABASE_BACKEND"] = "postgresql"
        os.environ["COLD_STORAGE_DATABASE_URL"] = database_url


@contextmanager
def _isolated_loader_env(
    *,
    database_url: str,
    storage_dir: Path | None = None,
) -> Iterator[Path]:
    env_snapshot = _snapshot_env()
    artifact_dir = storage_dir or Path(
        tempfile.mkdtemp(prefix="v06-sample-artifacts-", dir=REPO_ROOT)
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        _configure_database_env(database_url)
        os.environ["COLD_STORAGE_STORAGE_DIR"] = str(artifact_dir)
        yield artifact_dir
    finally:
        _restore_env(env_snapshot)


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


def _calculations_by_name(
    client: TestClient,
    project_id: str,
    version_number: int,
) -> dict[str, dict[str, Any]]:
    calculations = client.get(
        f"/api/v1/projects/{project_id}/versions/{version_number}/calculations"
    ).json()
    indexed: dict[str, dict[str, Any]] = {}
    for row in calculations:
        name = row.get("calculator_name")
        if isinstance(name, str):
            indexed[name] = row
    return indexed


def _ensure_demo_weight_set_available(client: TestClient) -> bool:
    """Bootstrap the demo weight set through the public demo endpoint."""
    response = client.get("/api/v1/demo/scheme-comparison")
    return response.status_code == 200


def _probe_scheme_public_bootstrap(client: TestClient) -> SchemeSeedResult:
    """Prove weight-set bootstrap without persisting legacy scheme-runs on the sample."""
    if not _ensure_demo_weight_set_available(client):
        return SchemeSeedResult(
            attempted=True,
            success=False,
            scheme_run_id=None,
            fail_closed_reason=(
                "demo weight set bootstrap via /api/v1/demo/scheme-comparison failed"
            ),
        )
    return SchemeSeedResult(
        attempted=True,
        success=False,
        scheme_run_id=None,
        fail_closed_reason=SCHEME_FAIL_CLOSED_REASON,
    )


def _create_report(
    client: TestClient,
    *,
    project_id: str,
    version_id: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/reports",
        json={
            "project_id": project_id,
            "project_version_id": version_id,
            "report_type": "cold_storage_concept_design",
        },
    )
    response.raise_for_status()
    body = response.json()
    return {"id": body["report_id"], **body}


def _generate_report_revision(client: TestClient, report_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/reports/{report_id}/generate")
    response.raise_for_status()
    return response.json()


def _complete_trusted_review_lifecycle(
    client: TestClient,
    report_id: str,
) -> tuple[bool, str | None, int]:
    submit = client.post(f"/api/v1/reports/{report_id}/submit-review")
    if submit.status_code != 200:
        return False, submit.text, submit.status_code
    reviewed = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    if reviewed.status_code != 200:
        return False, reviewed.text, submit.status_code
    approved = client.post(f"/api/v1/reports/{report_id}/approve")
    if approved.status_code != 200:
        return False, approved.text, submit.status_code
    return True, None, submit.status_code


def _render_formal(
    client: TestClient,
    report_id: str,
    *,
    revision_number: int,
    locale: str,
    export_format: str,
) -> FormalRenderResult:
    response = client.post(
        f"/api/v1/reports/{report_id}/revisions/{revision_number}/render",
        json={
            "format": export_format,
            "template_version": TEMPLATE_VERSION,
            "mode": "formal",
            "locale": locale,
        },
    )
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        return FormalRenderResult(
            locale=locale,
            export_format=export_format,
            status_code=response.status_code,
            artifact_id=None,
            file_sha256=None,
            fail_closed=response.status_code == 409,
            detail=response.text,
        )
    body = response.json()
    if response.status_code != 200:
        return FormalRenderResult(
            locale=locale,
            export_format=export_format,
            status_code=response.status_code,
            artifact_id=None,
            file_sha256=None,
            fail_closed=response.status_code == 409,
            detail=json.dumps(body, ensure_ascii=False),
        )
    return FormalRenderResult(
        locale=locale,
        export_format=export_format,
        status_code=response.status_code,
        artifact_id=body.get("artifact_id"),
        file_sha256=body.get("file_sha256"),
        fail_closed=False,
        detail=None,
    )


def _download_artifact(client: TestClient, report_id: str, artifact_id: str) -> bytes:
    response = client.get(f"/api/v1/reports/{report_id}/exports/{artifact_id}/download")
    response.raise_for_status()
    return response.content


def _seed_five_stage(
    client: TestClient,
    *,
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], bool, bool, bool, str | None]:
    project_spec = manifest["project"]
    project_name = project_spec["name"]
    execution_spec = manifest.get("five_stage_execution") or {}
    idempotency_key = execution_spec.get("idempotency_key")
    if not idempotency_key:
        raise ValueError("manifest.five_stage_execution.idempotency_key is required")

    existing = _find_project_by_name(client, project_name)
    created = existing is None
    project = existing
    if project is None:
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

    return project, created, five_stage_success, idempotent_replay, source_binding_id


@contextmanager
def _build_trusted_client(
    database_url: str,
    *,
    storage_dir: Path | None = None,
) -> Iterator[TestClient]:
    with _isolated_loader_env(database_url=database_url, storage_dir=storage_dir):
        service = create_database_project_service(database_url)
        app = create_app(project_service=service)
        app.dependency_overrides[_get_actor] = lambda: TRUSTED_SEED_ACTOR
        with TestClient(app) as client:
            yield client


def seed_v06_sample(
    client: TestClient,
    *,
    manifest: dict[str, Any] | None = None,
    complete_reports: bool = True,
) -> SeededV06Sample:
    manifest = manifest or load_manifest()
    project, created, five_stage_success, idempotent_replay, source_binding_id = _seed_five_stage(
        client, manifest=manifest
    )
    project_id = project["id"]
    version_number = project["current_version_number"]
    version = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}").json()
    version_id = version["id"]
    persisted_names = _persisted_calculator_names(client, project_id, version_number)
    by_name = _calculations_by_name(client, project_id, version_number)

    scheme = _probe_scheme_public_bootstrap(client)

    report_id: str | None = None
    revision_number: int | None = None
    revision_content_hash: str | None = None
    formal_renders: list[FormalRenderResult] = []
    review_closed = False
    review_fail_closed_reason: str | None = None
    submit_review_status_code: int | None = None

    if complete_reports:
        report = _create_report(client, project_id=project_id, version_id=version_id)
        report_id = report["id"]
        revision = _generate_report_revision(client, report_id)
        revision_number = revision["revision_number"]
        revision_content_hash = revision["content_hash"]
        review_closed, review_fail_closed_reason, submit_review_status_code = (
            _complete_trusted_review_lifecycle(client, report_id)
        )
        for locale in FORMAL_LOCALES:
            for export_format in FORMAL_FORMATS:
                rendered = _render_formal(
                    client,
                    report_id,
                    revision_number=revision_number,
                    locale=locale,
                    export_format=export_format,
                )
                formal_renders.append(rendered)
                if review_closed and rendered.status_code == 200 and rendered.artifact_id:
                    content = _download_artifact(client, report_id, rendered.artifact_id)
                    if len(content) < 100:
                        raise RuntimeError(
                            "artifact download too small for "
                            f"{locale}/{export_format}: {len(content)} bytes"
                        )

    calculation_ids = {
        name: by_name[name]["calculation_id"]
        for name in EXPECTED_CANONICAL_CALCULATORS
        if name in by_name
    }
    calculation_hashes = {
        name: by_name[name]["result_hash"]
        for name in EXPECTED_CANONICAL_CALCULATORS
        if name in by_name
    }

    return SeededV06Sample(
        sample_id=manifest["sample_id"],
        project_id=project_id,
        project_code=project["code"],
        version_number=version_number,
        project_name=manifest["project"]["name"],
        version_id=version_id,
        created=created,
        five_stage_success=five_stage_success,
        idempotent_replay=idempotent_replay,
        persisted_calculator_names=persisted_names,
        source_binding_id=source_binding_id,
        scheme=scheme,
        report_id=report_id,
        revision_number=revision_number,
        revision_content_hash=revision_content_hash,
        review_closed=review_closed,
        review_fail_closed_reason=review_fail_closed_reason,
        submit_review_status_code=submit_review_status_code,
        calculation_ids=calculation_ids,
        calculation_hashes=calculation_hashes,
        formal_renders=tuple(formal_renders),
    )


def verify_v06_sample(database_url: str) -> SeededV06Sample:
    """Seed and verify restart-stable IDs/hashes plus formal delivery closure."""
    manifest = load_manifest()
    with _build_trusted_client(database_url) as client:
        seeded = seed_v06_sample(client, manifest=manifest, complete_reports=True)

    missing = [
        name for name in EXPECTED_CANONICAL_CALCULATORS if name not in seeded.calculation_ids
    ]
    if missing:
        raise RuntimeError(f"verify failed: missing canonical calculators: {missing}")

    with _build_trusted_client(database_url) as reopened:
        second_by_name = _calculations_by_name(
            reopened,
            seeded.project_id,
            seeded.version_number,
        )
        for name in EXPECTED_CANONICAL_CALCULATORS:
            first_id = seeded.calculation_ids[name]
            first_hash = seeded.calculation_hashes[name]
            second = second_by_name[name]
            if second["calculation_id"] != first_id:
                raise RuntimeError(
                    f"restart verification failed for {name}: calculation_id changed"
                )
            if second["result_hash"] != first_hash:
                raise RuntimeError(f"restart verification failed for {name}: result_hash changed")

        if seeded.report_id is None or seeded.revision_number is None:
            raise RuntimeError("verify failed: report lifecycle did not complete")

        if not seeded.review_closed:
            if seeded.submit_review_status_code is not None:
                if seeded.submit_review_status_code not in {409, 422}:
                    raise RuntimeError(
                        "verify failed: submit-review must fail closed with 409/422 on "
                        f"operator path, got {seeded.submit_review_status_code}"
                    )
            elif not seeded.review_fail_closed_reason:
                raise RuntimeError("verify failed: review closure missing fail-closed reason")
            blocked = [
                item
                for item in seeded.formal_renders
                if item.status_code != 409 and not item.fail_closed
            ]
            if blocked:
                details = ", ".join(
                    f"{item.locale}/{item.export_format}={item.status_code}" for item in blocked
                )
                raise RuntimeError(
                    "verify failed: formal render must stay 409 when review is not closed: "
                    f"{details}"
                )
        else:
            fail_closed = [
                item
                for item in seeded.formal_renders
                if item.fail_closed or item.status_code != 200
            ]
            if fail_closed:
                details = ", ".join(
                    f"{item.locale}/{item.export_format}={item.status_code}" for item in fail_closed
                )
                raise RuntimeError(
                    f"verify failed: formal render did not complete after review closure: {details}"
                )

        reopened_revision = reopened.get(
            f"/api/v1/reports/{seeded.report_id}/revisions/{seeded.revision_number}"
        ).json()
        if reopened_revision["content_hash"] != seeded.revision_content_hash:
            raise RuntimeError("restart verification failed: report revision content_hash changed")

        approved = reopened.get(f"/api/v1/reports/{seeded.report_id}").json()
        if seeded.review_closed and approved["status"] != "approved":
            raise RuntimeError(
                f"verify failed: expected approved report, got {approved['status']!r}"
            )

    return replace(seeded, restart_verified=True)


def _resolve_database_url(database_url: str | None) -> str:
    if database_url is not None:
        return database_url
    backend = os.environ.get("COLD_STORAGE_DATABASE_BACKEND", "sqlite")
    if backend == "postgresql":
        url = os.environ.get("COLD_STORAGE_DATABASE_URL")
        if not url:
            raise ValueError(
                "COLD_STORAGE_DATABASE_URL is required when "
                "COLD_STORAGE_DATABASE_BACKEND=postgresql"
            )
        return url
    backend_sqlite = REPO_ROOT / "backend" / "cold_storage_dev.db"
    root_sqlite = REPO_ROOT / "cold_storage_dev.db"
    default_sqlite_path = backend_sqlite if backend_sqlite.is_file() else root_sqlite
    sqlite_path = Path(os.environ.get("COLD_STORAGE_SQLITE_PATH", default_sqlite_path))
    if not sqlite_path.is_absolute():
        sqlite_path = REPO_ROOT / sqlite_path
    return f"sqlite:///{sqlite_path}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed or verify the V0.6 formal delivery sample via current public APIs. "
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
        "--verify",
        action="store_true",
        help="Run seed plus restart/hash verification and formal render checks.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the seeded sample summary as JSON.",
    )
    return parser


def _summary_dict(seeded: SeededV06Sample) -> dict[str, Any]:
    return {
        "sample_id": seeded.sample_id,
        "project_id": seeded.project_id,
        "project_code": seeded.project_code,
        "version_number": seeded.version_number,
        "version_id": seeded.version_id,
        "project_name": seeded.project_name,
        "created": seeded.created,
        "five_stage_success": seeded.five_stage_success,
        "idempotent_replay": seeded.idempotent_replay,
        "source_binding_id": seeded.source_binding_id,
        "persisted_calculator_names": list(seeded.persisted_calculator_names),
        "calculation_ids": seeded.calculation_ids,
        "calculation_hashes": seeded.calculation_hashes,
        "scheme": {
            "attempted": seeded.scheme.attempted,
            "success": seeded.scheme.success,
            "scheme_run_id": seeded.scheme.scheme_run_id,
            "fail_closed_reason": seeded.scheme.fail_closed_reason,
        },
        "report_id": seeded.report_id,
        "revision_number": seeded.revision_number,
        "revision_content_hash": seeded.revision_content_hash,
        "review_closed": seeded.review_closed,
        "review_fail_closed_reason": seeded.review_fail_closed_reason,
        "submit_review_status_code": seeded.submit_review_status_code,
        "formal_renders": [
            {
                "locale": item.locale,
                "format": item.export_format,
                "status_code": item.status_code,
                "artifact_id": item.artifact_id,
                "file_sha256": item.file_sha256,
                "fail_closed": item.fail_closed,
                "detail": item.detail,
            }
            for item in seeded.formal_renders
        ],
        "restart_verified": seeded.restart_verified,
        "trusted_seed_actor": TRUSTED_SEED_ACTOR,
        "trusted_seed_actor_note": (
            "Seed-process TestClient actor override only; not production RBAC."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    database_url = _resolve_database_url(args.database_url)

    if args.verify:
        seeded = verify_v06_sample(database_url)
    else:
        with _build_trusted_client(database_url) as client:
            seeded = seed_v06_sample(client)

    summary = _summary_dict(seeded)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"V06_SAMPLE_PROJECT_ID={seeded.project_id}")
        print(f"V06_SAMPLE_PROJECT_CODE={seeded.project_code}")
        print(f"V06_SAMPLE_VERSION={seeded.version_number}")
        print(f"V06_SAMPLE_REPORT_ID={seeded.report_id or ''}")
        print(f"V06_SAMPLE_SCHEME_RUN_ID={seeded.scheme.scheme_run_id or ''}")
        print(f"V06_SAMPLE_RESTART_VERIFIED={'yes' if seeded.restart_verified else 'no'}")
        print("V06_SAMPLE_PERSISTED=" + ",".join(seeded.persisted_calculator_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
