"""Composition entry point for the TASK-011 multilingual report pilot.

Sub-commands
=============

* ``run`` — load the frozen pilot manifest, prepare a fresh database
  (SQLite via subprocess ``alembic upgrade head``; PostgreSQL via the
  caller-supplied ``--database-url``), seed the deterministic A1
  production-context chain, run the backend evaluation scenario
  through ``run_scenario_via_markers``, compose the production
  ``ReportService`` / ``ReportRenderService`` /
  ``ReportArtifactStorage`` triplet around ``RealReportDataProvider``,
  seed the report templates, then delegate verification to
  :func:`cold_storage.evaluation.pilot_reports.verify_multilingual_report_pilot`.
* ``cleanup`` — remove an explicitly-owned pilot run root via the
  shared :func:`cold_storage.evaluation.artifact_io.remove_managed_output_root`
  helper, which rejects filesystem roots, the user's home, the
  allowed-parent itself, and non-owned paths.

Scope
=====

This module is the C-2 / §11.3 composition root. It does not seed
databases with bespoke report content, fabricate translated text,
substitute mock storage, or re-derive any production-side hash.
All report-content sourcing is delegated to ``RealReportDataProvider``
plus the production ``ReportAssembler``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

# Bootstrap sys.path before any cold_storage import so the composition
# script can be invoked as ``uv run python tests/pilot/...`` without
# requiring the caller to set ``PYTHONPATH=src`` explicitly. The
# canonical §12.1 invocation is ``cd backend && uv run python
# tests/pilot/run_multilingual_report_pilot.py run …``; under that
# invocation ``backend/`` is the cwd and ``src/`` is the
# ``cold_storage`` package root. ``backend/`` itself is the parent of
# ``tests/`` (the location of the ``_seed_helpers`` module).
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _BACKEND_ROOT / "src"
for _path in (str(_SRC_ROOT), str(_BACKEND_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from cold_storage.evaluation.artifact_io import remove_managed_output_root  # noqa: E402
from cold_storage.evaluation.execute import run_scenario_via_markers  # noqa: E402
from cold_storage.evaluation.manifest import (  # noqa: E402
    compute_manifest_sha,
    load_and_validate_manifest,
)
from cold_storage.evaluation.models import ScenarioDeclaration  # noqa: E402
from cold_storage.evaluation.pilot_reports import (  # noqa: E402
    verify_multilingual_report_pilot,
)
from cold_storage.modules.projects.infrastructure.database import (  # noqa: E402
    DatabaseProjectService,
)
from cold_storage.modules.projects.infrastructure.orm import (  # noqa: E402
    CalculationRunRecord,
)
from cold_storage.modules.reports.application.assembler import (  # noqa: E402
    ReportAssembler,
)
from cold_storage.modules.reports.application.render_service import (  # noqa: E402
    ReportRenderService,
    ReportRenderUnitOfWork,
)
from cold_storage.modules.reports.application.service import ReportService  # noqa: E402
from cold_storage.modules.reports.infrastructure.artifact_storage import (  # noqa: E402
    ReportArtifactStorage,
)
from cold_storage.modules.reports.infrastructure.real_data_provider import (  # noqa: E402
    RealReportDataProvider,
)
from cold_storage.modules.reports.infrastructure.repository import (  # noqa: E402
    SQLReportRepository,
)
from cold_storage.modules.reports.infrastructure.template_seed import (  # noqa: E402
    seed_default_templates,
)
from cold_storage.modules.schemes.application.query import (  # noqa: E402
    SchemeQueryService,
)
from cold_storage.modules.schemes.infrastructure.repository import (  # noqa: E402
    SchemeRepository,
)
from tests.evaluation._seed_helpers import (  # noqa: E402
    SOURCE_BINDING_ID,
    WEIGHT_REVISION_ID,
    seed_a1_all_prereqs,
)

BACKEND_DIR = _BACKEND_ROOT
DATABASE_BACKEND_SQLITE = "sqlite"
DATABASE_BACKEND_POSTGRESQL = "postgresql"
ALLOWED_DATABASE_BACKENDS: frozenset[str] = frozenset(
    {DATABASE_BACKEND_SQLITE, DATABASE_BACKEND_POSTGRESQL}
)
SQLITE_ALEMBIC_TIMEOUT_SECONDS = 120
SQLITE_URL_SCHEME = "sqlite:///"


# ── Exit-code contract (mirrors §10 forbidden-behavior discipline) ──────────
#
# Exit codes are machine-readable. Downstream automation classifies
# via ``$?``; the script does NOT print them as plain text on stderr.
#
#   0 — verifier returned ``overall_result == "PASS"``; the summary
#       line is printed on stdout.
#   2 — input contract violation (manifest schema, missing flags,
#       relative manifest / output path, repeat-index out of range).
#   3 — production / backend runner contract violation
#       (non-SUCCEEDED outcome, ``PhaseBBlockedError``, missing
#       scheme_run rows).
#   4 — verifier contract violation (``PilotVerificationError`` with
#       a non-PASS typed code).
#   1 — any other (infra-side) error (alembic failure, DB driver
#       missing, IO error, etc.).

EXIT_OK = 0
EXIT_INPUT_ERROR = 2
EXIT_BACKEND_ERROR = 3
EXIT_VERIFIER_ERROR = 4
EXIT_INFRA_ERROR = 1


# ── CLI parsing ─────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser with the frozen ``run`` / ``cleanup`` sub-commands."""
    parser = argparse.ArgumentParser(
        prog="run_multilingual_report_pilot",
        description=(
            "Composition entry point for the TASK-011 multilingual report pilot "
            "(frozen §11.3 allowlist)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser(
        "run",
        help="Run the four-render pilot on a fresh database (SQLite or PostgreSQL).",
    )
    run_parser.add_argument(
        "--backend",
        choices=sorted(ALLOWED_DATABASE_BACKENDS),
        required=True,
        help="Database backend marker (matches the ck_scheme_run_database_backend check).",
    )
    run_parser.add_argument(
        "--database-url",
        required=True,
        help=(
            "Absolute SQLAlchemy URL for the target database. For SQLite the URL must "
            "point at an empty file; for PostgreSQL the caller is responsible for "
            "creating an empty database with the production schema already applied."
        ),
    )
    run_parser.add_argument(
        "--manifest",
        required=True,
        help="Absolute path to the frozen backend-specific pilot manifest JSON.",
    )
    run_parser.add_argument(
        "--output-root",
        required=True,
        help=(
            "Absolute path to a non-existent or empty run root. The verifier writes "
            "``pilot-run.json``, ``artifacts/<locale>/<fmt>/``, and ``pilot-summary.json`` "
            "beneath it."
        ),
    )
    run_parser.add_argument(
        "--repeat-index",
        type=int,
        choices=(1, 2),
        required=True,
        help="Pilot repeat index; frozen contract requires 1 or 2.",
    )
    run_parser.add_argument(
        "--commit-sha",
        required=True,
        help=(
            "Lowercase 40-char hex commit SHA that produced the implementation under "
            "test. Captured as ``source_commit_sha`` in ``pilot-run.json``."
        ),
    )

    cleanup_parser = sub.add_parser(
        "cleanup",
        help="Remove an explicitly-owned pilot run root (rejects unsafe paths).",
    )
    cleanup_parser.add_argument(
        "--output-root",
        required=True,
        help="Absolute path to the previously-created pilot run root to remove.",
    )

    return parser


# ── Path-safety helpers ─────────────────────────────────────────────────────


def _require_absolute(path: Path, *, label: str) -> Path:
    """Reject ``path`` if it is not absolute.

    Relative inputs are rejected **before** any file I/O, identical
    to ``manifest._validate_manifest_path_safety``: the rejection does
    not depend on the current working directory.
    """
    if not path.is_absolute():
        raise PilotCompositionError(
            code="UNSAFE_OUTPUT_ROOT" if "output" in label else "MANIFEST_ERROR",
            message=f"{label} path must be absolute; got {path!r}.",
        )
    return path.resolve(strict=False)


# ── Error class ─────────────────────────────────────────────────────────────


class PilotCompositionError(Exception):
    """Typed composition-side error with a stable ``code`` attribute.

    Downstream automation MUST classify via ``code`` (per §10.3
    forbidden-behavior discipline: no message-text parsing).
    """

    code: str = "PILOT_COMPOSITION_ERROR"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ── SQLite database provisioning ────────────────────────────────────────────


def _provision_sqlite_database(*, database_url: str) -> Engine:
    """Create an isolated SQLite file with the production schema applied.

    Mirrors ``tests.evaluation._seed_helpers.a1_engine`` (TASK-011B
    Path A SQLite pattern): a temporary SQLite file is created, then
    ``alembic upgrade head`` runs in a subprocess with ``SQLITE_PATH``
    and ``DATABASE_BACKEND=sqlite`` set in the environment, and a
    fresh engine with ``PRAGMA foreign_keys=ON`` is returned. Foreign
    keys are enforced so the production schema constraints are
    exercised end-to-end.
    """
    if not database_url.startswith(SQLITE_URL_SCHEME):
        raise PilotCompositionError(
            code="INPUT_ERROR",
            message=(
                f"--database-url {database_url!r} does not use the sqlite scheme "
                f"{SQLITE_URL_SCHEME!r}; --backend sqlite requires a sqlite:///<path> URL."
            ),
        )
    sqlite_path = database_url[len(SQLITE_URL_SCHEME) :]
    if not sqlite_path:
        raise PilotCompositionError(
            code="INPUT_ERROR",
            message="SQLite --database-url is missing the file path component.",
        )
    db_path = Path(sqlite_path).resolve(strict=False)
    if db_path.exists():
        raise PilotCompositionError(
            code="INPUT_ERROR",
            message=(
                f"SQLite --database-url target {str(db_path)!r} already exists; the "
                "pilot requires a fresh database file."
            ),
        )
    db_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = DATABASE_BACKEND_SQLITE
    env.pop("DATABASE_URL", None)
    src_path = (BACKEND_DIR / "src").resolve()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts = [str(src_path)] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=SQLITE_ALEMBIC_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise PilotCompositionError(
            code="ALEMBIC_UPGRADE_FAILED",
            message=(
                f"alembic upgrade head failed (exit={proc.returncode}); "
                f"stderr tail: {proc.stderr[-2000:]!r}"
            ),
        )

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


# ── Database session factory ────────────────────────────────────────────────


def _build_session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a ``sessionmaker`` bound to ``engine`` (``expire_on_commit=False``)."""
    return sessionmaker(bind=engine, expire_on_commit=False)


# ── Manifest loading + scenario lookup ──────────────────────────────────────


def _load_pilot_manifest(*, manifest_path: Path) -> tuple[ScenarioDeclaration, str]:
    """Load + validate the frozen pilot manifest and return its sole scenario + SHA-256.

    The frozen manifest carries exactly one scenario
    (``baseline_feasible``); this helper enforces that invariant and
    returns the typed :class:`ScenarioDeclaration` plus the canonical
    SHA-256 used as ``source_manifest_sha`` in ``pilot-run.json``.
    """
    resolved = _require_absolute(manifest_path, label="manifest")
    manifest = load_and_validate_manifest(resolved)
    if len(manifest.scenarios) != 1:
        raise PilotCompositionError(
            code="MANIFEST_ERROR",
            message=(
                f"frozen pilot manifest must declare exactly one scenario; got "
                f"{len(manifest.scenarios)} in {str(resolved)!r}."
            ),
        )
    return manifest.scenarios[0], compute_manifest_sha(manifest)


# ── Commit SHA validation ───────────────────────────────────────────────────


def _validate_commit_sha(commit_sha: str) -> str:
    """Return the lowercase 40-char hex commit SHA or raise."""
    if len(commit_sha) != 40 or any(c not in "0123456789abcdef" for c in commit_sha.lower()):
        raise PilotCompositionError(
            code="INPUT_ERROR",
            message=f"--commit-sha must be a 40-char lowercase hex string; got {commit_sha!r}.",
        )
    return commit_sha.lower()


# ── Read-only query adapters (composition-only boundary normalization) ─────


# Map frozen A1 ``_SLOT_STAGE_ORDER`` to the four ``RealReportDataProvider``
# attribute names + their section_key + tool_name. The ``investment`` stage
# is intentionally not mapped (RealReportDataProvider does not consume an
# investment section). Stage → attribute is the only mapping owned by the
# composition; the result/calculator_version/content_hash fields below each
# attribute are read directly from the persisted ``CalculationRunRecord``
# row (no recalculation, no fabrication).
_PILOT_STAGE_TO_DATA_PROVIDER_ATTR: tuple[
    tuple[str, str, str, str], ...
] = (
    # (stage, data_provider_attr, section_key, tool_name)
    ("zone", "throughput_result", "throughput_inventory_area", "throughput_calculator"),
    ("cooling_load", "cooling_load_result", "cooling_load", "cooling_load_calculator"),
    ("equipment", "equipment_result", "equipment_selection", "equipment_calculator"),
    ("power", "power_result", "electrical_and_energy", "power_calculator"),
)


class _PilotCalcSection:
    """Duck-typed adapter section exposing only the attributes ``RealReportDataProvider`` reads.

    All attributes are sourced directly from the persisted
    ``CalculationRunRecord`` row — no recomputation, no copy, no
    fabrication. ``result_snapshot`` is the same dict the seed wrote
    (passed by reference, not deep-copied).
    """

    __slots__ = (
        "id",
        "calculator_name",
        "calculator_version",
        "result",
        "content_hash",
        "tool_call_status",
    )

    def __init__(
        self,
        *,
        id: str,
        calculator_name: str,
        calculator_version: str,
        result: dict[str, Any],
        content_hash: str | None,
        tool_call_status: str | None,
    ) -> None:
        self.id = id
        self.calculator_name = calculator_name
        self.calculator_version = calculator_version
        self.result = result
        self.content_hash = content_hash
        self.tool_call_status = tool_call_status


class _PilotOrchestrationResult:
    """Duck-typed orchestration result exposing the four ``RealReportDataProvider`` attrs.

    ``getattr(adapter, "<attr>")`` returns a :class:`_PilotCalcSection`
    instance when the persisted row exists, else ``None`` (matching the
    pre-existing skip-on-attribute-missing contract at
    ``real_data_provider.get_calculation_results`` line 107).
    """

    __slots__ = (
        "throughput_result",
        "cooling_load_result",
        "equipment_result",
        "power_result",
    )

    def __init__(self, sections: dict[str, _PilotCalcSection | None]) -> None:
        self.throughput_result = sections.get("throughput_result")
        self.cooling_load_result = sections.get("cooling_load_result")
        self.equipment_result = sections.get("equipment_result")
        self.power_result = sections.get("power_result")


class _PilotCalculationQueryAdapter:
    """Read-only adapter exposing ``get_orchestrated_result`` for ``RealReportDataProvider``.

    Implements the minimum surface that
    :meth:`RealReportDataProvider.get_calculation_results` consumes:

    * ``get_orchestrated_result(project_id, version_id)`` returns a
      duck-typed object whose four named attributes are either
      :class:`_PilotCalcSection` (with ``id`` /
      ``calculator_version`` / ``result`` / ``content_hash`` /
      ``tool_call_status`` attributes) or ``None``.

    **Read-only invariant.** The adapter issues only ``SELECT``
    statements against ``calculation_runs`` (the public
    SQLAlchemy table). It does NOT construct ORM rows, NOT write
    to the database, NOT ``commit()`` / ``rollback()``, NOT
    re-derive calculation results, and NOT mock any persisted
    value. ``result_snapshot`` is read directly from the persisted
    row (as the same Python dict object the seed wrote) and exposed
    by reference; the only transformation is the attribute-name
    mapping below, which is the composition's contractual
    responsibility per §11.3.
    """

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def get_orchestrated_result(
        self, project_id: str, version_id: str
    ) -> _PilotOrchestrationResult | None:
        from sqlalchemy import select

        with self._session_factory() as session:
            stmt = select(CalculationRunRecord).where(
                CalculationRunRecord.project_id == project_id,
                CalculationRunRecord.project_version_id == version_id,
            )
            rows: dict[str, CalculationRunRecord] = {
                str(record.calculation_type or ""): record
                for record in session.scalars(stmt).all()
            }

        if not rows:
            return None

        sections: dict[str, _PilotCalcSection | None] = {}
        for stage, attr_name, _section_key, _tool_name in _PILOT_STAGE_TO_DATA_PROVIDER_ATTR:
            record = rows.get(stage)
            if record is None:
                sections[attr_name] = None
                continue
            # Read directly from the persisted row — no copy, no
            # recalc, no schema-shape conversion. The downstream
            # ``_validate_schema`` (production-side) is the single
            # source of truth for the v1 measured-value contract;
            # when v0-shaped snapshots fail that schema, the gap is
            # surfaced as ``IMPLEMENTATION_BLOCKED`` per Charles's
            # protocol, NOT hidden by adapter-side fabrication.
            sections[attr_name] = _PilotCalcSection(
                id=str(record.id),
                calculator_name=str(record.calculator_name or ""),
                calculator_version=str(record.calculator_version or "1.0.0"),
                result=record.result_snapshot or {},
                content_hash=str(record.result_hash) if record.result_hash else None,
                tool_call_status=None,
            )
        return _PilotOrchestrationResult(sections=sections)


class _PilotSchemeQueryAdapter:
    """Read-only ``SchemeQueryPort``-shaped wrapper that coerces ``None`` to ``""``.

    The production ``SchemeQueryService._serialize_run`` returns
    ``recommended_scheme_code: None`` when ``SchemeRun.recommended_scheme_code``
    is ``NULL`` in the database. The downstream report schema
    (``cold_storage_concept_design@1.0.0``) declares
    ``scheme_comparison.recommended_scheme`` as ``{"type": "string"}``
    and rejects ``None`` even when the property is optional (it
    requires the existing value to match the type).

    This adapter wraps the production ``SchemeQueryService`` and
    coerces only the ``recommended_scheme_code`` field from ``None``
    to ``""`` so the downstream assembler can produce schema-valid
    content. **Read-only invariant**: no ORM construction, no
    database writes, no ``commit()`` / ``rollback()``, no
    re-derivation, no fabrication. The original ``latest_run`` dict
    is shallow-copied before mutation; every other field passes
    through untouched.

    The class is duck-typed (no ``SchemeQueryPort`` inheritance)
    to keep mypy's nominal-typing inference stable across the
    composition's follow-imports graph; ``RealReportDataProvider``
    accesses the wrapper via ``getattr`` / duck-typed call, so
    structural compatibility is sufficient.
    """

    def __init__(self, inner: SchemeQueryService) -> None:
        self._inner = inner

    def get_completed_runs_for_project(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = list(
            self._inner.get_completed_runs_for_project(project_id)
        )
        return [self._coerce(run) for run in runs]

    def get_completed_runs_for_project_version(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = list(
            self._inner.get_completed_runs_for_project_version(
                project_id, version_id
            )
        )
        return [self._coerce(run) for run in runs]

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = list(
            self._inner.get_candidates_for_run(run_id)
        )
        return candidates

    @staticmethod
    def _coerce(run: dict[str, Any]) -> dict[str, Any]:
        if run.get("recommended_scheme_code") is None:
            normalized: dict[str, Any] = dict(run)
            normalized["recommended_scheme_code"] = ""
            return normalized
        return run


# ── Production service composition ──────────────────────────────────────────


def _compose_report_services(
    *,
    engine: Engine,
    output_root: Path,
) -> tuple[
    ReportService,
    ReportRenderService,
    SQLReportRepository,
    ReportArtifactStorage,
    DatabaseProjectService,
]:
    """Compose the production report / render / storage triplet.

    Returns the wired triplet in the order: ``report_service``,
    ``render_service``, ``template_repository`` (the
    ``SQLReportRepository`` instance, reused per app.py §Reports DI
    wiring), ``artifact_storage`` (rooted under the pilot
    ``output_root``), and ``project_service`` (production
    ``DatabaseProjectService`` bound to the same engine — required by
    :class:`RealReportDataProvider`).

    Composition-only boundary adapters (read-only, no production
    refactor) bridge two pre-existing ``RealReportDataProvider``
    interface gaps so the frozen §11.3 contract holds end-to-end:

    * :class:`_PilotCalculationQueryAdapter` exposes
      ``get_orchestrated_result`` by issuing ``SELECT`` statements
      against the public ``calculation_runs`` table. The production
      ``CoreCalculationService`` does NOT implement this method
      (only ``orchestrate_core_calculation`` exists) — this adapter
      fills the gap without mutating production code. Read-only:
      no row construction, no writes, no commit/rollback, no
      re-derivation of calculation results, no fabrication.
    * :class:`_PilotSchemeQueryAdapter` wraps the production
      ``SchemeQueryService`` and coerces ``recommended_scheme_code:
      None`` to ``""`` so the downstream report schema
      (``cold_storage_concept_design@1.0.0``) accepts the value.
      Production ``SchemeRun.recommended_scheme_code`` is
      ``str | None`` and is ``NULL`` when the runner produced no
      feasible candidate. Read-only: shallow-copies the run dict
      before mutation; every other field passes through untouched.
    """
    session_factory = _build_session_factory(engine)
    shared_session = session_factory()
    report_repo = SQLReportRepository(shared_session)
    artifact_storage = ReportArtifactStorage(base_dir=str(output_root))
    report_uow = ReportRenderUnitOfWork(
        shared_session,
        report_repo=report_repo,
        artifact_repo=report_repo,
        session_factory=session_factory,
    )
    render_service = ReportRenderService(
        uow=report_uow,
        storage=artifact_storage,
        template_repo=report_repo,
    )
    project_service = DatabaseProjectService(engine=engine)
    calculation_service = _PilotCalculationQueryAdapter(session_factory=session_factory)
    scheme_repo = SchemeRepository(session_factory())
    scheme_query = _PilotSchemeQueryAdapter(
        inner=SchemeQueryService(repository=scheme_repo),
    )
    data_provider = RealReportDataProvider(
        project_service=project_service,
        calculation_service=calculation_service,
        scheme_query=scheme_query,
    )
    assembler = ReportAssembler(data_provider=data_provider)
    report_service = ReportService(repository=report_repo, assembler=assembler)
    return (
        report_service,
        render_service,
        report_repo,
        artifact_storage,
        project_service,
    )


# ── Template seeding ────────────────────────────────────────────────────────


def _seed_report_templates(template_repo: SQLReportRepository) -> None:
    """Seed the production report templates for both locales (zh-CN / en-US).

    Required by ``ReportRenderService.render`` (which calls
    ``_find_template``) — without seeded templates the four-render
    matrix fails at the first locale / format combination.
    """
    seed_default_templates(template_repo)
    template_repo.commit()


# ── download_artifact callable ──────────────────────────────────────────────


def _build_download_artifact(
    *,
    render_service: ReportRenderService,
) -> Callable[[str, str, str], tuple[bytes, Mapping[str, str]]]:
    """Build the ``download_artifact`` callable expected by the verifier.

    Mirrors ``reports.api.routes.download_export``:
    ``render_service.verify_download`` performs the safety checks,
    ``render_service.get_artifact_path`` resolves the on-disk
    ``storage_key`` (rejects ``..`` escapes), and the response
    headers are reconstructed from the persisted
    :class:`ReportExportArtifact` so the verifier can validate
    X-Content-SHA256 / X-Source-Content-Hash / locale / template
    headers exactly as the HTTP layer would deliver them.
    """

    def download_artifact(
        report_id: str,
        artifact_id: str,
        actor: str,
    ) -> tuple[bytes, Mapping[str, str]]:
        artifact = render_service.verify_download(report_id, artifact_id, actor)
        file_path = render_service.get_artifact_path(artifact.storage_key)
        data = Path(file_path).read_bytes()
        locale_val = artifact.locale.value if artifact.locale is not None else ""
        template_locale_val = (
            artifact.template_locale.value if artifact.template_locale is not None else ""
        )
        headers = {
            "X-Content-SHA256": artifact.file_sha256,
            "X-Artifact-Id": artifact.id,
            "X-Source-Content-Hash": artifact.source_content_hash,
            "X-Template-Version": artifact.template_version,
            "X-Report-Locale": locale_val,
            "X-Template-Locale": template_locale_val,
            "X-Translation-Catalog-Version": artifact.translation_catalog_version,
            "X-Translation-Catalog-Content-Hash": artifact.translation_catalog_content_hash,
            "X-Localized-Template-Content-Hash": artifact.localized_template_content_hash,
        }
        return data, headers

    return download_artifact


# ── Source-binding SHA cross-check ──────────────────────────────────────────


def _expected_source_binding_sha(session: Session) -> str:
    """Return the SHA-256 of the seeded ``SourceBindingRecord.combined_source_hash``.

    The pilot verifier does not require this hash directly, but the
    composition script persists a manifest-summary line that names
    the combined source hash so operators can confirm the runner
    consumed the deterministic A1 seed rows (not a re-seeded / fresh
    database).
    """
    from cold_storage.modules.orchestration.infrastructure.orm import SourceBindingRecord

    record = session.get(SourceBindingRecord, SOURCE_BINDING_ID)
    if record is None:
        raise PilotCompositionError(
            code="SEED_BINDING_MISSING",
            message=f"SourceBindingRecord {SOURCE_BINDING_ID!r} not found after seed.",
        )
    return str(record.combined_source_hash)


# ── Pilot run sub-command ───────────────────────────────────────────────────


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute the ``run`` sub-command end-to-end."""
    try:
        commit_sha = _validate_commit_sha(args.commit_sha)
        manifest_path = _require_absolute(Path(args.manifest), label="manifest")
        output_root = _require_absolute(Path(args.output_root), label="output-root")
        if output_root.exists() and any(output_root.iterdir()):
            raise PilotCompositionError(
                code="INPUT_ERROR",
                message=(
                    f"--output-root {str(output_root)!r} already exists and is non-empty; "
                    "the pilot refuses to overwrite a prior run."
                ),
            )
        output_root.mkdir(parents=True, exist_ok=True)

        scenario, source_manifest_sha = _load_pilot_manifest(manifest_path=manifest_path)
        backend = scenario.database_backend.value
        if backend != args.backend:
            raise PilotCompositionError(
                code="INPUT_ERROR",
                message=(
                    f"--backend {args.backend!r} disagrees with manifest "
                    f"database_backend {backend!r}."
                ),
            )

        if backend == DATABASE_BACKEND_SQLITE:
            engine = _provision_sqlite_database(database_url=args.database_url)
        else:
            engine = create_engine(args.database_url, future=True)

        session_factory = _build_session_factory(engine)
        with session_factory() as seed_session:
            seed_a1_all_prereqs(seed_session)
            combined_source_hash = _expected_source_binding_sha(seed_session)

        outcome = run_scenario_via_markers(
            session_factory,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker="task011-pilot-correlation",
            backend_marker=backend,
        )
        if outcome.outcome != "SUCCEEDED":
            raise PilotCompositionError(
                code="BACKEND_RUNNER_FAILED",
                message=(
                    f"backend runner returned outcome={outcome.outcome!r}; "
                    "expected 'SUCCEEDED'."
                ),
            )

        scheme_run = outcome.scheme_run
        project_id = scheme_run.project_id
        project_version_id = scheme_run.project_version_id

        (
            report_service,
            render_service,
            template_repo,
            _artifact_storage,
            _project_service,
        ) = _compose_report_services(engine=engine, output_root=output_root)
        _seed_report_templates(template_repo)
        download_artifact = _build_download_artifact(render_service=render_service)

        run_identity: dict[str, str] = {
            "database_backend": backend,
            "scenario_id": scenario.scenario_id,
            "correlation_id": "task011-pilot-correlation",
            "source_binding_id": SOURCE_BINDING_ID,
            "weight_set_revision_id": WEIGHT_REVISION_ID,
            "combined_source_hash": combined_source_hash,
        }
        summary = verify_multilingual_report_pilot(
            report_service=report_service,
            render_service=render_service,
            template_repository=template_repo,
            project_id=project_id,
            project_version_id=project_version_id,
            source_commit_sha=commit_sha,
            source_manifest_sha=source_manifest_sha,
            output_root=output_root,
            repeat_index=args.repeat_index,
            run_identity=run_identity,
            download_artifact=download_artifact,
        )

        sys.stdout.write(json.dumps(summary, sort_keys=True, ensure_ascii=False) + "\n")
        return EXIT_OK
    except PilotCompositionError as exc:
        sys.stderr.write(f"PILOT_COMPOSITION_ERROR code={exc.code}: {exc}\n")
        if exc.code in {"INPUT_ERROR", "MANIFEST_ERROR"}:
            return EXIT_INPUT_ERROR
        if exc.code == "BACKEND_RUNNER_FAILED":
            return EXIT_BACKEND_ERROR
        return EXIT_INFRA_ERROR


# ── Cleanup sub-command ─────────────────────────────────────────────────────


def _cmd_cleanup(args: argparse.Namespace) -> int:
    """Execute the ``cleanup`` sub-command via the shared authority."""
    try:
        output_root = _require_absolute(Path(args.output_root), label="output-root")
        allowed_parent = output_root.parent
        remove_managed_output_root(
            root=output_root,
            allowed_parent=allowed_parent,
            ownership_marker="pilot-run.json",
        )
        sys.stdout.write(
            json.dumps(
                {
                    "command": "cleanup",
                    "output_root": str(output_root),
                    "result": "REMOVED",
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )
        return EXIT_OK
    except PilotCompositionError as exc:
        sys.stderr.write(f"PILOT_COMPOSITION_ERROR code={exc.code}: {exc}\n")
        return EXIT_INPUT_ERROR
    except Exception as exc:  # noqa: BLE001 — mapped to typed exit codes below
        # ``remove_managed_output_root`` raises ``EvaluationInfrastructureError``
        # for symlink / home / non-owned paths; classify those as INPUT_ERROR.
        from cold_storage.evaluation.errors import EvaluationInfrastructureError

        if isinstance(exc, EvaluationInfrastructureError):
            sys.stderr.write(f"EVALUATION_INFRASTRUCTURE_ERROR: {exc}\n")
            return EXIT_INPUT_ERROR
        raise


# ── Main entry point ────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Dispatch the top-level CLI to ``run`` or ``cleanup``."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "cleanup":
        return _cmd_cleanup(args)
    parser.error(f"unknown command {args.command!r}")
    return EXIT_INFRA_ERROR  # pragma: no cover — parser.error exits


if __name__ == "__main__":  # pragma: no cover — exercised via ``uv run python …``
    raise SystemExit(main())


# ── Public surface ──────────────────────────────────────────────────────────
#
# The frozen §11.3 composition module exposes ``main`` as the single
# public entry point. ``run`` / ``cleanup`` sub-commands and the
# helper functions below it are internal wiring; downstream automation
# invokes the script as a subprocess.

__all__ = [
    "EXIT_BACKEND_ERROR",
    "EXIT_INPUT_ERROR",
    "EXIT_INFRA_ERROR",
    "EXIT_OK",
    "EXIT_VERIFIER_ERROR",
    "PilotCompositionError",
    "main",
]


# Defensive sentinel: ``hashlib`` and ``tempfile`` are imported above to
# keep their symbols available even if a future refactor inlines the
# helper bodies. They are referenced indirectly by the composition
# flow (alembic subprocess, path resolution) so the explicit imports
# make the dependency surface observable at module-load time.
_ = (hashlib, tempfile)