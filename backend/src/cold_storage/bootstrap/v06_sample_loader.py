"""Seed the V0.6 local formal-delivery sample through current main public APIs.

The loader uses project, five-stage-execution, scheme-runs (when demo weights
are available), and report lifecycle endpoints only. It does not invoke
planning-run or Alembic.

Database schema must already be at Alembic head (for example via ``make migrate``)
before running this module.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.bootstrap.settings import get_settings
from cold_storage.bootstrap.v05_local_sample import (
    EXPECTED_CANONICAL_CALCULATORS,
    seed_v05_local_sample,
)
from cold_storage.modules.projects.infrastructure.database import create_database_project_service
from cold_storage.modules.reports.api.routes import _get_actor

SAMPLE_ID = "v06-formal-delivery"
MANIFEST_RELATIVE_PATH = Path("samples") / SAMPLE_ID / "manifest.json"
REPO_ROOT = Path(__file__).resolve().parents[4]
TRUSTED_ACTOR = "v06-local-trusted-reviewer"
UNTRUSTED_ACTOR = "system"
TEMPLATE_VERSION = "1.0.0"
FORMAL_LOCALES = ("zh-CN", "en-US")
FORMAL_FORMATS = ("docx", "pdf")

_ENV_KEYS_TO_ISOLATE = (
    "SQLITE_PATH",
    "COLD_STORAGE_SQLITE_PATH",
    "COLD_STORAGE_DATABASE_BACKEND",
    "COLD_STORAGE_DATABASE_URL",
    "COLD_STORAGE_STORAGE_DIR",
    "COLD_STORAGE_ENVIRONMENT_ID",
    "DATABASE_BACKEND",
)


@dataclass(frozen=True, slots=True)
class SchemeAttemptResult:
    attempted: bool
    success: bool
    fail_closed: bool
    status_code: int | None
    detail: str | None
    scheme_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class FormalExportResult:
    locale: str
    export_format: str
    status_code: int
    artifact_id: str | None = None
    file_sha256: str | None = None
    file_size_bytes: int | None = None
    fail_closed: bool = False
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ReportLifecycleResult:
    report_id: str
    revision_number: int
    content_hash: str
    submit_status_code: int
    mark_reviewed_status_code: int | None = None
    approve_status_code: int | None = None
    formal_exports: tuple[FormalExportResult, ...] = field(default_factory=tuple)
    fail_closed: bool = False
    fail_closed_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SeededV06Sample:
    sample_id: str
    project_id: str
    project_code: str
    version_number: int
    project_version_id: str
    project_name: str
    created: bool
    five_stage_success: bool
    idempotent_replay: bool
    persisted_calculator_names: tuple[str, ...]
    source_binding_id: str | None
    scheme: SchemeAttemptResult


def manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / MANIFEST_RELATIVE_PATH


def load_manifest(repo_root: Path | None = None) -> dict[str, Any]:
    path = manifest_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"V0.6 local sample manifest not found: {path}")
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


@contextmanager
def _isolated_loader_env(
    *,
    storage_dir: Path | None = None,
) -> Iterator[None]:
    snapshot = _snapshot_env()
    try:
        if storage_dir is not None:
            storage_dir.mkdir(parents=True, exist_ok=True)
            os.environ["COLD_STORAGE_STORAGE_DIR"] = str(storage_dir)
        if "COLD_STORAGE_ENVIRONMENT_ID" not in os.environ:
            os.environ["COLD_STORAGE_ENVIRONMENT_ID"] = "local"
        yield
    finally:
        _restore_env(snapshot)


def _resolve_database_url(database_url: str | None) -> str:
    if database_url is not None:
        return database_url
    settings = get_settings()
    backend = settings.database_backend
    if backend == "postgresql":
        pg_url = settings.database_url
        if not pg_url:
            raise ValueError(
                "COLD_STORAGE_DATABASE_URL is required when DATABASE_BACKEND=postgresql"
            )
        return pg_url
    if settings.database_url:
        return settings.database_url
    sqlite_path = Path(settings.sqlite_path or "cold_storage_dev.db")
    if not sqlite_path.is_absolute():
        sqlite_path = Path.cwd() / sqlite_path
    return f"sqlite:///{sqlite_path}"


def _version_record(client: TestClient, project_id: str, version_number: int) -> dict[str, Any]:
    response = client.get(f"/api/v1/projects/{project_id}/versions/{version_number}")
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


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


def _assert_canonical_five(by_name: dict[str, dict[str, Any]]) -> None:
    missing = [name for name in EXPECTED_CANONICAL_CALCULATORS if name not in by_name]
    if missing:
        raise RuntimeError(f"sample project is missing canonical calculators: {missing}")
    for name in EXPECTED_CANONICAL_CALCULATORS:
        row = by_name[name]
        if not row.get("calculation_id"):
            raise RuntimeError(f"{name} is missing calculation_id")
        if not row.get("result_hash"):
            raise RuntimeError(f"{name} is missing result_hash")


def _attempt_scheme_via_public_bootstrap(client: TestClient) -> SchemeAttemptResult:
    """Exercise scheme comparison through the public demo bootstrap path only.

    ``POST .../scheme-runs`` on the sample project persists legacy
    ``source_mode`` rows that make unmodified ``create_app`` report assembly
    fail closed in production scheme readback. The operator path therefore
    bootstraps demo weights and scheme generation via the existing public demo
    endpoint instead of creating a legacy run on the sample version.
    """
    response = client.get("/api/v1/demo/scheme-comparison")
    if response.status_code != 200:
        return SchemeAttemptResult(
            attempted=True,
            success=False,
            fail_closed=True,
            status_code=response.status_code,
            detail=response.text,
        )
    body = response.json()
    schemes = body.get("schemes") or []
    if not schemes:
        return SchemeAttemptResult(
            attempted=True,
            success=False,
            fail_closed=True,
            status_code=200,
            detail="demo scheme-comparison returned no schemes",
        )
    return SchemeAttemptResult(
        attempted=True,
        success=True,
        fail_closed=False,
        status_code=200,
        detail=None,
    )


def _create_report(
    client: TestClient,
    *,
    project_id: str,
    project_version_id: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/reports",
        json={
            "project_id": project_id,
            "project_version_id": project_version_id,
            "report_type": "cold_storage_concept_design",
        },
    )
    response.raise_for_status()
    body = response.json()
    return {"id": body["report_id"], **body}


def _generate_report_revision(client: TestClient, report_id: str) -> dict[str, Any]:
    response = client.post(f"/api/v1/reports/{report_id}/generate")
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _run_report_lifecycle(
    client: TestClient,
    *,
    project_id: str,
    project_version_id: str,
) -> ReportLifecycleResult:
    report = _create_report(
        client,
        project_id=project_id,
        project_version_id=project_version_id,
    )
    report_id = report["id"]
    revision = _generate_report_revision(client, report_id)
    revision_number = int(revision["revision_number"])
    content_hash = str(revision.get("content_hash") or "")

    submit = client.post(f"/api/v1/reports/{report_id}/submit-review")
    if submit.status_code != 200:
        formal_exports = tuple(
            _render_formal(
                client,
                report_id,
                revision_number=revision_number,
                locale=locale,
                export_format=export_format,
            )
            for locale in FORMAL_LOCALES
            for export_format in FORMAL_FORMATS
        )
        if not all(item.status_code == 409 for item in formal_exports):
            failing = [
                f"{item.locale}/{item.export_format}={item.status_code}"
                for item in formal_exports
                if item.status_code != 409
            ]
            raise RuntimeError(
                "expected formal export fail-closed with 409 when submit-review is blocked; "
                f"got: {', '.join(failing)}"
            )
        return ReportLifecycleResult(
            report_id=report_id,
            revision_number=revision_number,
            content_hash=content_hash,
            submit_status_code=submit.status_code,
            formal_exports=formal_exports,
            fail_closed=True,
            fail_closed_reason=submit.text,
        )

    reviewed = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    if reviewed.status_code != 200:
        raise RuntimeError(
            f"mark-reviewed failed after submit: {reviewed.status_code} {reviewed.text}"
        )
    approved = client.post(f"/api/v1/reports/{report_id}/approve")
    if approved.status_code != 200:
        raise RuntimeError(
            f"approve failed after mark-reviewed: {approved.status_code} {approved.text}"
        )

    formal_exports_list: list[FormalExportResult] = []
    for locale in FORMAL_LOCALES:
        for export_format in FORMAL_FORMATS:
            rendered = _render_formal(
                client,
                report_id,
                revision_number=revision_number,
                locale=locale,
                export_format=export_format,
            )
            if rendered.status_code != 200:
                raise RuntimeError(
                    f"formal export failed for {locale}/{export_format}: "
                    f"{rendered.status_code} {rendered.detail}"
                )
            formal_exports_list.append(rendered)

    return ReportLifecycleResult(
        report_id=report_id,
        revision_number=revision_number,
        content_hash=content_hash,
        submit_status_code=submit.status_code,
        mark_reviewed_status_code=reviewed.status_code,
        approve_status_code=approved.status_code,
        formal_exports=tuple(formal_exports_list),
        fail_closed=False,
    )


def _render_formal(
    client: TestClient,
    report_id: str,
    *,
    revision_number: int,
    locale: str,
    export_format: str,
) -> FormalExportResult:
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
    if response.status_code != 200:
        return FormalExportResult(
            locale=locale,
            export_format=export_format,
            status_code=response.status_code,
            fail_closed=response.status_code == 409,
            detail=response.text,
        )
    body = response.json() if content_type.startswith("application/json") else {}
    return FormalExportResult(
        locale=locale,
        export_format=export_format,
        status_code=response.status_code,
        artifact_id=body.get("artifact_id"),
        file_sha256=body.get("file_sha256"),
        file_size_bytes=body.get("file_size_bytes"),
        fail_closed=False,
    )


@contextmanager
def trusted_sample_client(
    database_url: str,
    *,
    storage_dir: Path | None = None,
) -> Iterator[tuple[TestClient, Any]]:
    with _isolated_loader_env(storage_dir=storage_dir):
        service = create_database_project_service(database_url)
        app = create_app(project_service=service)
        app.dependency_overrides[_get_actor] = lambda: TRUSTED_ACTOR
        with TestClient(app) as client:
            yield client, service


def seed_v06_sample(
    client: TestClient,
    *,
    manifest: dict[str, Any] | None = None,
) -> SeededV06Sample:
    manifest = manifest or load_manifest()
    seeded = seed_v05_local_sample(client, manifest=manifest)
    version = _version_record(client, seeded.project_id, seeded.version_number)
    by_name = _calculations_by_name(client, seeded.project_id, seeded.version_number)
    _assert_canonical_five(by_name)

    scheme = _attempt_scheme_via_public_bootstrap(client)

    return SeededV06Sample(
        sample_id=manifest["sample_id"],
        project_id=seeded.project_id,
        project_code=seeded.project_code,
        version_number=seeded.version_number,
        project_version_id=version["id"],
        project_name=seeded.project_name,
        created=seeded.created,
        five_stage_success=seeded.five_stage_success,
        idempotent_replay=seeded.idempotent_replay,
        persisted_calculator_names=seeded.persisted_calculator_names,
        source_binding_id=seeded.source_binding_id,
        scheme=scheme,
    )


def verify_v06_sample(database_url: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="v06-sample-artifacts-") as artifact_tmp:
        storage_dir = Path(artifact_tmp)
        with trusted_sample_client(database_url, storage_dir=storage_dir) as (client, service):
            seeded = seed_v06_sample(client)
            lifecycle = _run_report_lifecycle(
                client,
                project_id=seeded.project_id,
                project_version_id=seeded.project_version_id,
            )

            first_by_name = _calculations_by_name(client, seeded.project_id, seeded.version_number)
            first_revision = client.get(
                f"/api/v1/reports/{lifecycle.report_id}/revisions/{lifecycle.revision_number}"
            ).json()

            if not lifecycle.fail_closed:
                for export in lifecycle.formal_exports:
                    if not export.artifact_id:
                        raise RuntimeError("formal export missing artifact_id")
                    detail = client.get(
                        f"/api/v1/reports/{lifecycle.report_id}/exports/{export.artifact_id}"
                    )
                    detail.raise_for_status()
                    download = client.get(
                        f"/api/v1/reports/{lifecycle.report_id}/exports/{export.artifact_id}/download"
                    )
                    download.raise_for_status()
                    if len(download.content) < 100:
                        raise RuntimeError(
                            "artifact download too small for "
                            f"{export.locale}/{export.export_format}"
                        )

            untrusted_app = create_app(project_service=service)
            untrusted_app.dependency_overrides[_get_actor] = lambda: UNTRUSTED_ACTOR
            with TestClient(untrusted_app) as untrusted_client:
                untrusted_mark = untrusted_client.post(
                    f"/api/v1/reports/{lifecycle.report_id}/mark-reviewed"
                )
                if untrusted_mark.status_code == 200:
                    raise RuntimeError(
                        "untrusted system actor must not satisfy mark_reviewed in production RBAC"
                    )

        with trusted_sample_client(database_url, storage_dir=storage_dir) as (reopened, _service):
            second_by_name = _calculations_by_name(
                reopened, seeded.project_id, seeded.version_number
            )
            for name in EXPECTED_CANONICAL_CALCULATORS:
                first_row = first_by_name[name]
                second_row = second_by_name[name]
                if first_row["calculation_id"] != second_row["calculation_id"]:
                    raise RuntimeError(f"{name} calculation_id changed after restart")
                if first_row["result_hash"] != second_row["result_hash"]:
                    raise RuntimeError(f"{name} result_hash changed after restart")

            reopened_revision = reopened.get(
                f"/api/v1/reports/{lifecycle.report_id}/revisions/{lifecycle.revision_number}"
            ).json()
            if reopened_revision["content_hash"] != first_revision["content_hash"]:
                raise RuntimeError("report revision content_hash changed after restart")

            reseeded = seed_v06_sample(reopened)
            if reseeded.project_id != seeded.project_id:
                raise RuntimeError("idempotent reseed changed project_id")

    return {
        "sample_id": seeded.sample_id,
        "project_id": seeded.project_id,
        "version_number": seeded.version_number,
        "scheme": {
            "attempted": seeded.scheme.attempted,
            "success": seeded.scheme.success,
            "fail_closed": seeded.scheme.fail_closed,
            "status_code": seeded.scheme.status_code,
            "scheme_run_id": seeded.scheme.scheme_run_id,
        },
        "report_id": lifecycle.report_id,
        "report_revision_number": lifecycle.revision_number,
        "report_content_hash": lifecycle.content_hash,
        "report_lifecycle_fail_closed": lifecycle.fail_closed,
        "report_lifecycle_fail_closed_reason": lifecycle.fail_closed_reason,
        "formal_exports": [
            {
                "locale": item.locale,
                "format": item.export_format,
                "status_code": item.status_code,
                "artifact_id": item.artifact_id,
                "file_sha256": item.file_sha256,
                "fail_closed": item.fail_closed,
            }
            for item in lifecycle.formal_exports
        ],
        "restart_stable": True,
        "verify_status": "ok",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed or verify the V0.6 local formal-delivery sample via current main APIs. "
            "Run `make migrate` first."
        )
    )
    parser.add_argument(
        "--database-url",
        help=(
            "Optional SQLAlchemy database URL. "
            "Defaults to COLD_STORAGE_SQLITE_PATH or ./cold_storage_dev.db, "
            "or COLD_STORAGE_DATABASE_URL when DATABASE_BACKEND=postgresql."
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run full operator acceptance checks (restart, formal exports, downloads).",
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

    if args.verify:
        summary = verify_v06_sample(database_url)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("V06_SAMPLE_VERIFY=ok")
            print(f"V06_SAMPLE_PROJECT_ID={summary['project_id']}")
            print(f"V06_SAMPLE_REPORT_ID={summary['report_id']}")
            fail_closed = "yes" if summary.get("report_lifecycle_fail_closed") else "no"
            print(f"V06_SAMPLE_REPORT_LIFECYCLE_FAIL_CLOSED={fail_closed}")
        return 0

    with trusted_sample_client(database_url) as (client, _service):
        seeded = seed_v06_sample(client)

    summary = {
        "sample_id": seeded.sample_id,
        "project_id": seeded.project_id,
        "project_code": seeded.project_code,
        "version_number": seeded.version_number,
        "project_version_id": seeded.project_version_id,
        "project_name": seeded.project_name,
        "created": seeded.created,
        "five_stage_success": seeded.five_stage_success,
        "idempotent_replay": seeded.idempotent_replay,
        "source_binding_id": seeded.source_binding_id,
        "persisted_calculator_names": list(seeded.persisted_calculator_names),
        "scheme": {
            "attempted": seeded.scheme.attempted,
            "success": seeded.scheme.success,
            "fail_closed": seeded.scheme.fail_closed,
            "status_code": seeded.scheme.status_code,
            "scheme_run_id": seeded.scheme.scheme_run_id,
            "detail": seeded.scheme.detail,
        },
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
        print(f"V06_SAMPLE_PROJECT_ID={seeded.project_id}")
        print(f"V06_SAMPLE_PROJECT_CODE={seeded.project_code}")
        print(f"V06_SAMPLE_VERSION={seeded.version_number}")
        print(f"V06_SAMPLE_VERSION_ID={seeded.project_version_id}")
        print(f"V06_SAMPLE_CREATED={'yes' if seeded.created else 'no'}")
        print("V06_SAMPLE_PERSISTED=" + ",".join(seeded.persisted_calculator_names))
        print(f"V06_SAMPLE_SCHEME_SUCCESS={'yes' if seeded.scheme.success else 'no'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"V06_SAMPLE_ERROR={exc}", file=sys.stderr)
        raise
