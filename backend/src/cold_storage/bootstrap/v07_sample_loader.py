"""Seed the V0.7 operator trust-loop sample through current main public APIs.

The loader uses project, five-stage-execution, production-scheme-runs, and report
lifecycle endpoints only. It does not invoke planning-run, legacy scheme-runs,
demo scheme-comparison, or Alembic.

After ``create_app`` lifespan starts, it idempotently seeds the frozen production
weight revision ``wsr-production-default-v1`` via ``seed_production_weight_revision``.

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
from cold_storage.modules.schemes.application.weight_revision_governance import (
    PRODUCTION_WEIGHT_SET_REVISION_ID,
    seed_production_weight_revision,
)
from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
    SqlAlchemyWeightRevisionApprovalAdapter,
)

SAMPLE_ID = "v07-trust-loop"
MANIFEST_RELATIVE_PATH = Path("samples") / SAMPLE_ID / "manifest.json"
REPO_ROOT = Path(__file__).resolve().parents[4]
TRUSTED_ACTOR = "v07-local-trusted-reviewer"
UNTRUSTED_ACTOR = "system"
TEMPLATE_VERSION = "1.0.0"
FORMAL_LOCALES = ("zh-CN", "en-US")
FORMAL_FORMATS = ("docx", "pdf")
PRODUCTION_PROFILE_CODES = ("balanced",)

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
class ProductionSchemeResult:
    attempted: bool
    success: bool
    status_code: int | None
    detail: str | None
    run_id: str | None = None
    source_binding_id: str | None = None
    combined_source_hash: str | None = None


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
class SeededV07Sample:
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
    production_scheme: ProductionSchemeResult


def manifest_path(repo_root: Path | None = None) -> Path:
    root = repo_root or REPO_ROOT
    return root / MANIFEST_RELATIVE_PATH


def load_manifest(repo_root: Path | None = None) -> dict[str, Any]:
    path = manifest_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"V0.7 trust-loop sample manifest not found: {path}")
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


def _seed_production_weights_after_lifespan() -> None:
    from sqlalchemy.orm import Session

    from cold_storage.bootstrap.dependencies import get_engine

    engine = get_engine()
    adapter = SqlAlchemyWeightRevisionApprovalAdapter()
    with Session(bind=engine, expire_on_commit=False) as session:
        seed_production_weight_revision(
            adapter,
            session,
            generator_version="1.0.0",
            approved_by="v07-sample-seed",
        )
        session.commit()


def _apply_investment_translation_overlay() -> None:
    overlay_path = (
        REPO_ROOT
        / "backend"
        / "tests"
        / "fixtures"
        / "v06"
        / "v06_p3_investment_translation_overlay.v1.json"
    )
    if not overlay_path.is_file():
        return
    from cold_storage.modules.reports.domain.enums import ReportLocale
    from cold_storage.modules.reports.localization.catalog import _CATALOGS, TranslationCatalog

    with overlay_path.open(encoding="utf-8") as handle:
        overlay = json.load(handle)
    for locale_key, messages in overlay["locales"].items():
        locale = ReportLocale(locale_key)
        base = _CATALOGS[locale]
        merged = dict(base.messages)
        merged.update(messages)
        _CATALOGS[locale] = TranslationCatalog(
            locale=locale,
            version=base.version,
            messages=merged,
        )


def _seed_report_templates_after_lifespan() -> None:
    """Seed default report templates after lifespan initializes the engine.

    ``create_app`` registers an ``on_event('startup')`` seeder that can run
    before ``init_dependencies``; operator TestClient paths therefore seed
    templates explicitly once the lifespan has finished.
    """
    from sqlalchemy.orm import Session

    from cold_storage.bootstrap.dependencies import get_engine
    from cold_storage.modules.reports.infrastructure.repository import SQLReportRepository
    from cold_storage.modules.reports.infrastructure.template_seed import seed_default_templates

    engine = get_engine()
    session = Session(bind=engine, expire_on_commit=False)
    try:
        seed_default_templates(SQLReportRepository(session))
        session.commit()
    finally:
        session.close()


def _create_production_scheme_run(
    client: TestClient,
    *,
    project_id: str,
    version_number: int,
) -> ProductionSchemeResult:
    response = client.post(
        f"/api/v1/projects/{project_id}/versions/{version_number}/production-scheme-runs",
        json={
            "profile_codes": list(PRODUCTION_PROFILE_CODES),
            "weight_set_revision_id": PRODUCTION_WEIGHT_SET_REVISION_ID,
            "profile_parameters": {},
        },
    )
    if response.status_code != 200:
        return ProductionSchemeResult(
            attempted=True,
            success=False,
            status_code=response.status_code,
            detail=response.text,
        )
    body = response.json()
    return ProductionSchemeResult(
        attempted=True,
        success=True,
        status_code=200,
        detail=None,
        run_id=body.get("run_id"),
        source_binding_id=body.get("source_binding_id"),
        combined_source_hash=body.get("combined_source_hash"),
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


def _export_report_json(
    client: TestClient,
    report_id: str,
    revision_number: int,
) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/reports/{report_id}/export",
        params={"revision_number": revision_number, "format": "json"},
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _assert_report_trust_loop_sections(
    exported: dict[str, Any],
    *,
    expected_project_name: str,
    production_scheme: ProductionSchemeResult,
) -> None:
    content = exported.get("content") or exported
    project_summary = content.get("project_summary")
    if not isinstance(project_summary, dict):
        raise RuntimeError("project_summary must be present after generate")
    if project_summary.get("project_name") != expected_project_name:
        raise RuntimeError("project_summary.project_name does not match seeded project")

    scheme_comparison = content.get("scheme_comparison")
    if not isinstance(scheme_comparison, dict):
        raise RuntimeError("scheme_comparison must be present after production scheme run")
    authority = scheme_comparison.get("review_authority")
    if not isinstance(authority, dict):
        raise RuntimeError("scheme_comparison.review_authority must be present")
    if authority.get("scheme_run_id") != production_scheme.run_id:
        raise RuntimeError("review_authority.scheme_run_id does not match production run")
    if authority.get("source_binding_id") != production_scheme.source_binding_id:
        raise RuntimeError("review_authority.source_binding_id mismatch")
    if authority.get("combined_source_hash") != production_scheme.combined_source_hash:
        raise RuntimeError("review_authority.combined_source_hash mismatch")


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


def _run_report_lifecycle(
    client: TestClient,
    *,
    project_id: str,
    project_version_id: str,
    expected_project_name: str,
    production_scheme: ProductionSchemeResult,
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

    exported = _export_report_json(client, report_id, revision_number)
    _assert_report_trust_loop_sections(
        exported,
        expected_project_name=expected_project_name,
        production_scheme=production_scheme,
    )

    submit = client.post(f"/api/v1/reports/{report_id}/submit-review")
    if submit.status_code != 200:
        return ReportLifecycleResult(
            report_id=report_id,
            revision_number=revision_number,
            content_hash=content_hash,
            submit_status_code=submit.status_code,
            fail_closed=True,
            fail_closed_reason=submit.text,
        )

    reviewed = client.post(f"/api/v1/reports/{report_id}/mark-reviewed")
    if reviewed.status_code != 200:
        raise RuntimeError(
            f"trusted mark-reviewed failed after submit: {reviewed.status_code} {reviewed.text}"
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
            _seed_production_weights_after_lifespan()
            _seed_report_templates_after_lifespan()
            _apply_investment_translation_overlay()
            yield client, service


def seed_v07_sample(
    client: TestClient,
    *,
    manifest: dict[str, Any] | None = None,
) -> SeededV07Sample:
    manifest = manifest or load_manifest()
    seeded = seed_v05_local_sample(client, manifest=manifest)
    version = _version_record(client, seeded.project_id, seeded.version_number)
    by_name = _calculations_by_name(client, seeded.project_id, seeded.version_number)
    _assert_canonical_five(by_name)

    production_scheme = _create_production_scheme_run(
        client,
        project_id=seeded.project_id,
        version_number=seeded.version_number,
    )
    if not production_scheme.success:
        raise RuntimeError(
            "production-scheme-runs failed: "
            f"{production_scheme.status_code} {production_scheme.detail}"
        )

    return SeededV07Sample(
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
        production_scheme=production_scheme,
    )


def verify_v07_sample(database_url: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="v07-sample-artifacts-") as artifact_tmp:
        storage_dir = Path(artifact_tmp)
        with trusted_sample_client(database_url, storage_dir=storage_dir) as (client, service):
            seeded = seed_v07_sample(client)
            lifecycle = _run_report_lifecycle(
                client,
                project_id=seeded.project_id,
                project_version_id=seeded.project_version_id,
                expected_project_name=seeded.project_name,
                production_scheme=seeded.production_scheme,
            )
            if lifecycle.fail_closed:
                raise RuntimeError(
                    "operator trust-loop verify expected submit-review 200; got "
                    f"{lifecycle.submit_status_code}: {lifecycle.fail_closed_reason}"
                )

            first_by_name = _calculations_by_name(client, seeded.project_id, seeded.version_number)
            first_revision = client.get(
                f"/api/v1/reports/{lifecycle.report_id}/revisions/{lifecycle.revision_number}"
            ).json()

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
                        f"artifact download too small for {export.locale}/{export.export_format}"
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

            reseeded = seed_v07_sample(reopened)
            if reseeded.project_id != seeded.project_id:
                raise RuntimeError("idempotent reseed changed project_id")

    return {
        "sample_id": seeded.sample_id,
        "project_id": seeded.project_id,
        "version_number": seeded.version_number,
        "production_scheme_run_id": seeded.production_scheme.run_id,
        "report_id": lifecycle.report_id,
        "report_revision_number": lifecycle.revision_number,
        "report_content_hash": lifecycle.content_hash,
        "submit_review_status": lifecycle.submit_status_code,
        "mark_reviewed_status": lifecycle.mark_reviewed_status_code,
        "approve_status": lifecycle.approve_status_code,
        "formal_exports": [
            {
                "locale": item.locale,
                "format": item.export_format,
                "status_code": item.status_code,
                "artifact_id": item.artifact_id,
                "file_sha256": item.file_sha256,
            }
            for item in lifecycle.formal_exports
        ],
        "restart_stable": True,
        "verify_status": "ok",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seed or verify the V0.7 operator trust-loop sample via current main APIs. "
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
        help="Run full operator trust-loop checks (review, formal exports, restart).",
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
        summary = verify_v07_sample(database_url)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("V07_SAMPLE_VERIFY=ok")
            print(f"V07_SAMPLE_PROJECT_ID={summary['project_id']}")
            print(f"V07_SAMPLE_REPORT_ID={summary['report_id']}")
            print(f"V07_SAMPLE_SCHEME_RUN_ID={summary['production_scheme_run_id']}")
        return 0

    with trusted_sample_client(database_url) as (client, _service):
        seeded = seed_v07_sample(client)

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
        "production_scheme": {
            "attempted": seeded.production_scheme.attempted,
            "success": seeded.production_scheme.success,
            "status_code": seeded.production_scheme.status_code,
            "run_id": seeded.production_scheme.run_id,
            "detail": seeded.production_scheme.detail,
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
        print(f"V07_SAMPLE_PROJECT_ID={seeded.project_id}")
        print(f"V07_SAMPLE_PROJECT_CODE={seeded.project_code}")
        print(f"V07_SAMPLE_VERSION={seeded.version_number}")
        print(f"V07_SAMPLE_VERSION_ID={seeded.project_version_id}")
        print(f"V07_SAMPLE_CREATED={'yes' if seeded.created else 'no'}")
        print("V07_SAMPLE_PERSISTED=" + ",".join(seeded.persisted_calculator_names))
        print(
            f"V07_SAMPLE_PRODUCTION_SCHEME_SUCCESS="
            f"{'yes' if seeded.production_scheme.success else 'no'}"
        )
        if seeded.production_scheme.run_id:
            print(f"V07_SAMPLE_SCHEME_RUN_ID={seeded.production_scheme.run_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"V07_SAMPLE_ERROR={exc}", file=sys.stderr)
        raise
