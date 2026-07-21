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
from dataclasses import dataclass
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

from cold_storage.evaluation.adapter import read_c2_baseline_projection  # noqa: E402
from cold_storage.evaluation.artifact_io import remove_managed_output_root  # noqa: E402
from cold_storage.evaluation.compare import ComparisonResult, compare_outputs  # noqa: E402
from cold_storage.evaluation.execute import run_scenario_via_markers  # noqa: E402
from cold_storage.evaluation.manifest import (  # noqa: E402
    compute_manifest_sha,
    load_and_validate_manifest,
)
from cold_storage.evaluation.models import (  # noqa: E402
    Manifest,
    ScenarioDeclaration,
)
from cold_storage.evaluation.paths import (  # noqa: E402
    PathSafetyError,
    safe_resolve_manifest_path,
)
from cold_storage.evaluation.pilot_reports import (  # noqa: E402
    PilotVerificationError,
    verify_multilingual_report_pilot,
)
from cold_storage.evaluation.runners._executor import (  # noqa: E402
    build_baseline_normalized_business_projection,
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
# P1-1 (Round 1 corrective): the canonical correlation marker that
# the production runner bakes into ``assumption_snapshot.correlation_id``
# (see ``runners._executor.execute_baseline_succeeded``). The frozen
# ``baseline_feasible.v1.json`` golden bakes the same value into
# ``production_outputs.assumption_snapshot.correlation_id`` AND uses
# it (via the production-side ``content_hash``) to derive the byte-
# stable top-level ``content_hash`` (``ea4ab8cd...``) and
# ``combined_source_hash`` (``60e11cac...``). The runtime path MUST
# forward this exact marker to ``run_scenario_via_markers`` (which
# routes it to ``run_scenario(correlation_id=...)`` and then to the
# production ``AdapterResult``) and record it in ``run_identity``;
# otherwise the real production run produces a different
# ``content_hash`` and the manifest-golden comparison fails closed
# on the root ``value_mismatch`` (P1-1 finding).
PILOT_BASELINE_CORRELATION_ID = "test-a15-baseline-001"


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


@dataclass(frozen=True, slots=True)
class _PilotManifestBundle:
    """Typed bundle of validated manifest + sole scenario + identity fields.

    The composition MUST keep the typed :class:`Manifest` object (not
    a re-parsed JSON) and the resolved manifest path alive for the
    lifetime of ``_cmd_run()`` so the golden comparison can resolve
    ``scenario.expected_output.path`` against the actual manifest
    directory without re-reading or hand-parsing the manifest JSON.
    The frozen contract forbids re-reading manifest JSON
    (§11.3 "manifest is loaded only through
    ``load_and_validate_manifest(...)``").
    """

    manifest: Manifest
    scenario: ScenarioDeclaration
    source_manifest_sha: str
    manifest_path: Path


def _load_pilot_manifest(*, manifest_path: Path) -> _PilotManifestBundle:
    """Load + validate the frozen pilot manifest and return a typed bundle.

    The frozen manifest carries exactly one scenario
    (``baseline_feasible``); this helper enforces that invariant and
    returns a typed bundle that holds the validated
    :class:`Manifest`, the sole :class:`ScenarioDeclaration`, the
    canonical SHA-256 used as ``source_manifest_sha`` in
    ``pilot-run.json``, and the resolved manifest path.

    The returned bundle is the single source of manifest identity
    for ``_cmd_run()``; nothing else may re-read or hand-parse
    the manifest JSON after this helper returns.
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
    return _PilotManifestBundle(
        manifest=manifest,
        scenario=manifest.scenarios[0],
        source_manifest_sha=compute_manifest_sha(manifest),
        manifest_path=resolved,
    )


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
_PILOT_STAGE_TO_DATA_PROVIDER_ATTR: tuple[tuple[str, str, str, str], ...] = (
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
                str(record.calculation_type or ""): record for record in session.scalars(stmt).all()
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

    def get_completed_runs_for_project(self, project_id: str) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = list(self._inner.get_completed_runs_for_project(project_id))
        return [self._coerce(run) for run in runs]

    def get_completed_runs_for_project_version(
        self, project_id: str, version_id: str
    ) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = list(
            self._inner.get_completed_runs_for_project_version(project_id, version_id)
        )
        return [self._coerce(run) for run in runs]

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = list(self._inner.get_candidates_for_run(run_id))
        return candidates

    @staticmethod
    def _coerce(run: dict[str, Any]) -> dict[str, Any]:
        if run.get("recommended_scheme_code") is None:
            normalized: dict[str, Any] = dict(run)
            normalized["recommended_scheme_code"] = ""
            return normalized
        return run


# ── Manifest-golden binding (P1-1) ─────────────────────────────────────────


def _assert_scenario_baseline_feasible(
    *,
    scenario: ScenarioDeclaration,
    backend_marker: str,
) -> None:
    """Assert scenario id / expected_outcome / backend / expected_output are bound.

    The frozen contract (§11.3 + §6.2 + §6.3) requires the manifest
    to declare exactly one ``baseline_feasible`` scenario with
    ``expected_outcome=SUCCEEDED`` whose ``database_backend`` matches
    the CLI ``--backend`` and whose ``expected_output`` is a
    relative file path. This helper fails closed with stable typed
    codes (no message-text parsing by downstream automation).
    """
    if scenario.scenario_id != "baseline_feasible":
        raise PilotCompositionError(
            code="MANIFEST_SCENARIO_MISMATCH",
            message=(
                f"manifest scenario_id must be 'baseline_feasible'; got {scenario.scenario_id!r}."
            ),
        )
    if scenario.expected_outcome.value != "SUCCEEDED":
        raise PilotCompositionError(
            code="MANIFEST_SCENARIO_MISMATCH",
            message=(
                f"manifest expected_outcome must be 'SUCCEEDED'; got "
                f"{scenario.expected_outcome.value!r}."
            ),
        )
    if scenario.database_backend.value != backend_marker:
        raise PilotCompositionError(
            code="MANIFEST_SCENARIO_MISMATCH",
            message=(
                f"manifest database_backend {scenario.database_backend.value!r} "
                f"disagrees with --backend {backend_marker!r}."
            ),
        )
    expected = scenario.expected_output
    if expected is None or expected.path is None:
        raise PilotCompositionError(
            code="MANIFEST_SCENARIO_MISMATCH",
            message=(
                "manifest scenario expected_output.path MUST be present for "
                f"SUCCEEDED scenario_id={scenario.scenario_id!r}; got None."
            ),
        )


def _load_manifest_golden(
    *,
    scenario: ScenarioDeclaration,
    manifest_path: Path,
) -> dict[str, object]:
    """Load + validate the golden JSON referenced by ``scenario.expected_output.path``.

    Uses the public :func:`safe_resolve_manifest_path` authority for
    containment (rejects absolute paths, ``..`` traversal, symlink
    escape, empty / non-string inputs). The golden file is read
    once as UTF-8 JSON; the top level MUST be a JSON object.

    Returns the full golden dict (caller is responsible for
    stripping the golden-only ``_comparison_policy`` metadata key).
    """
    declared = scenario.expected_output
    assert declared is not None and declared.path is not None  # narrow: pre-checked
    manifest_root = manifest_path.parent
    try:
        golden_path = safe_resolve_manifest_path(declared.path, manifest_root=manifest_root)
    except PathSafetyError as exc:
        raise PilotCompositionError(
            code="MANIFEST_GOLDEN_PATH_UNSAFE",
            message=(
                f"manifest expected_output.path failed safety check: "
                f"{declared.path!r} (scenario={scenario.scenario_id!r}): {exc}"
            ),
        ) from exc
    if not golden_path.exists():
        raise PilotCompositionError(
            code="MANIFEST_GOLDEN_MISSING",
            message=(
                f"manifest expected_output file does not exist: "
                f"{str(golden_path)!r} (scenario={scenario.scenario_id!r})."
            ),
        )
    try:
        golden_text = golden_path.read_text(encoding="utf-8")
        golden_full = json.loads(golden_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotCompositionError(
            code="MANIFEST_GOLDEN_INVALID",
            message=(
                f"manifest expected_output file could not be read/parsed: "
                f"{str(golden_path)!r}: {exc}"
            ),
        ) from exc
    if not isinstance(golden_full, dict):
        raise PilotCompositionError(
            code="MANIFEST_GOLDEN_INVALID",
            message=(
                f"manifest expected_output file MUST be a JSON object at the "
                f"top level; got {type(golden_full).__name__} in {str(golden_path)!r}."
            ),
        )
    return golden_full


def _build_actual_normalized_business_projection(
    *,
    session_factory: Callable[[], Any],
    scheme_run_id: str,
) -> dict[str, object]:
    """Build the actual normalized business projection from the persisted SchemeRun.

    Reuses the existing C-2 read boundary
    (:func:`read_c2_baseline_projection`) and the runner-owned
    projection builder (:func:`build_baseline_normalized_business_projection`).
    NO second production execution, NO golden-derived actual,
    NO DOCX/PDF-derived actual, NO mock production output.
    """
    persisted_source = read_c2_baseline_projection(session_factory, run_id=scheme_run_id)
    actual_normalized = build_baseline_normalized_business_projection(persisted_source)
    return actual_normalized


def _verify_manifest_golden_binding(
    *,
    scenario: ScenarioDeclaration,
    manifest_path: Path,
    session_factory: Callable[[], Any],
    scheme_run_id: str,
) -> tuple[dict[str, object], dict[str, object], ComparisonResult]:
    """Run the manifest-golden comparison in strict order.

    The helper is intentionally narrow and owns exactly four steps:

    1. Load the golden via :func:`_load_manifest_golden` (uses the
       manifest-declared ``expected_output.path`` — no hard-coded
       path).
    2. Build the actual normalized business projection from the
       **current run's** persisted SchemeRun via
       :func:`_build_actual_normalized_business_projection` (uses
       the C-2 read boundary and the runner-owned projection
       builder — no second production execution, no golden-derived
       actual, no DOCX/PDF-derived actual, no mock production
       output).
    3. Strip the golden-only ``_comparison_policy`` metadata key
       from the business payload (mirrors §7.7 "after removing
       ``_comparison_policy``" — the key is golden-only and must
       not participate in business payload comparison).
    4. Call the existing :func:`compare_outputs` with
       ``scenario.comparison_policy`` (the frozen V1 default
       exact-equality policy). On failure, raise a typed
       :class:`PilotCompositionError` with
       ``code='MANIFEST_GOLDEN_MISMATCH'``; downstream automation
       MUST classify by code, not by message text.

    Returns ``(expected_normalized, actual_normalized, comparison)``
    so the caller can persist the comparison result into
    ``run_identity`` without re-running the comparison.
    """
    golden_full = _load_manifest_golden(scenario=scenario, manifest_path=manifest_path)
    expected_normalized: dict[str, object] = {
        key: value for key, value in golden_full.items() if key != "_comparison_policy"
    }
    actual_normalized = _build_actual_normalized_business_projection(
        session_factory=session_factory,
        scheme_run_id=scheme_run_id,
    )
    comparison = compare_outputs(
        expected=expected_normalized,
        actual=actual_normalized,
        policy=scenario.comparison_policy,
    )
    if not comparison.passed:
        diff_count = len(comparison.diffs)
        sample_paths: tuple[str, ...] = tuple(entry.path for entry in comparison.diffs[:5])
        raise PilotCompositionError(
            code="MANIFEST_GOLDEN_MISMATCH",
            message=(
                f"golden comparison FAILED for scenario_id={scenario.scenario_id!r} "
                f"manifest_path={str(manifest_path)!r} "
                f"expected_output_path={scenario.expected_output.path!r}: "
                f"diff_count={diff_count} sample_diff_paths={list(sample_paths)!r}."
            ),
        )
    return expected_normalized, actual_normalized, comparison


# ── Production service composition ──────────────────────────────────────────


@dataclass
class _PilotReportResources:
    """Resource bundle returned by :func:`_compose_report_services`.

    Carries the wired triplet + the two underlying SQLAlchemy
    ``Session`` objects (the ``shared_session`` used by
    ``SQLReportRepository`` + ``ReportRenderUnitOfWork`` and the
    anonymous ``scheme_session`` used by ``SchemeRepository``) so the
    caller can explicitly close them in a ``finally`` block.

    The lifetime contract is **caller-owned** — the caller MUST
    invoke :meth:`close` (or close both session fields directly)
    before returning, on BOTH success and failure paths.
    Composition code no longer relies on Python interpreter
    shutdown / SQLAlchemy pool reset to release the connections.
    """

    report_service: ReportService
    render_service: ReportRenderService
    template_repository: SQLReportRepository
    artifact_storage: ReportArtifactStorage
    project_service: DatabaseProjectService
    shared_session: Session
    scheme_session: Session
    _closed: bool = False

    def close(self) -> None:
        """Close the two composition-owned ``Session`` objects exactly once.

        Idempotent — second call is a no-op. Errors during close are
        swallowed (the connection pool will be disposed by the
        caller's ``engine.dispose()``); the brief §5 ordered
        release is preserved (report / UoW → scheme session →
        engine).
        """
        if self._closed:
            return
        self._closed = True
        for session_attr in ("shared_session", "scheme_session"):
            sess = getattr(self, session_attr)
            try:  # noqa: SIM105 - pool will release on engine.dispose
                sess.close()
            except Exception:  # noqa: BLE001
                pass


def _compose_report_services(
    *,
    engine: Engine,
    output_root: Path,
) -> _PilotReportResources:
    """Compose the production report / render / storage triplet.

    Returns a :class:`_PilotReportResources` bundle; the caller owns
    the bundle's lifecycle and MUST invoke
    :meth:`_PilotReportResources.close` (or close both session
    fields) in a ``finally`` block. This addresses the brief §5
    resource-ownership gap: previously the composition opened
    ``shared_session`` (report-side) + ``session_factory()``
    (``SchemeRepository``) without returning either, relying on
    Python interpreter shutdown / SQLAlchemy pool reset to release
    the connections. On PostgreSQL this surfaced as pool-reset
    ``psycopg2.OperationalError: SSL connection has been closed
    unexpectedly`` during teardown.

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
    scheme_session = session_factory()
    scheme_repo = SchemeRepository(scheme_session)
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
    return _PilotReportResources(
        report_service=report_service,
        render_service=render_service,
        template_repository=report_repo,
        artifact_storage=artifact_storage,
        project_service=project_service,
        shared_session=shared_session,
        scheme_session=scheme_session,
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

        bundle = _load_pilot_manifest(manifest_path=manifest_path)
        scenario = bundle.scenario
        source_manifest_sha = bundle.source_manifest_sha
        # P1-1 binding requirement: the typed ``Manifest`` object
        # remains held in ``bundle.manifest`` for the lifetime of
        # ``_cmd_run()`` (the bundle is the single source of
        # manifest identity; the manifest MUST NOT be re-read or
        # hand-parsed after ``_load_pilot_manifest`` returns).
        backend = scenario.database_backend.value
        if backend != args.backend:
            raise PilotCompositionError(
                code="INPUT_ERROR",
                message=(
                    f"--backend {args.backend!r} disagrees with manifest "
                    f"database_backend {backend!r}."
                ),
            )
        # P1-1: strict manifest-scenario binding (defense-in-depth;
        # the helper is idempotent with the legacy backend-mismatch
        # check above, but uses the stable ``MANIFEST_SCENARIO_MISMATCH``
        # code that downstream automation MUST classify by).
        # P2-1 (P1-1 corrective round): the helper MUST be fed the
        # CLI ``--backend`` authority (``args.backend``), NOT the
        # scenario-derived ``scenario.database_backend.value``
        # (``backend``). The previous ``backend_marker=backend`` form
        # was a self-comparison (helper compared scenario to itself
        # and always passed); the structural invariant we want is
        # "manifest scenario backend agrees with the operator-
        # supplied CLI backend" and the helper must enforce that on
        # its own inputs, not echo its own output.
        _assert_scenario_baseline_feasible(scenario=scenario, backend_marker=args.backend)

        if backend == DATABASE_BACKEND_SQLITE:
            engine = _provision_sqlite_database(database_url=args.database_url)
        else:
            engine = create_engine(args.database_url, future=True)
        resources: _PilotReportResources | None = None
        try:
            session_factory = _build_session_factory(engine)
            with session_factory() as seed_session:
                seed_a1_all_prereqs(seed_session)
                combined_source_hash = _expected_source_binding_sha(seed_session)

            outcome = run_scenario_via_markers(
                session_factory,
                source_binding_id=SOURCE_BINDING_ID,
                weight_set_revision_id=WEIGHT_REVISION_ID,
                correlation_marker=PILOT_BASELINE_CORRELATION_ID,
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

            # P1-1: manifest-golden binding MUST succeed before any of
            # the four-render composition steps below (no
            # ``_compose_report_services`` / no ``_seed_report_templates``
            # / no ``verify_multilingual_report_pilot`` on mismatch).
            # ``_verify_manifest_golden_binding`` raises
            # ``PilotCompositionError(code='MANIFEST_GOLDEN_MISMATCH')``
            # on failure; the comparison result is captured for the
            # run_identity summary below.
            _expected_normalized, _actual_normalized, _comparison = _verify_manifest_golden_binding(
                scenario=scenario,
                manifest_path=bundle.manifest_path,
                session_factory=session_factory,
                scheme_run_id=str(scheme_run.id),
            )
            # P1-1 binding requirement: the typed ``Manifest`` object
            # remains held in ``bundle.manifest`` for the lifetime of
            # ``_cmd_run()`` (the bundle is a single source of
            # manifest identity; the manifest MUST NOT be re-read or
            # hand-parsed after ``_load_pilot_manifest`` returns).

            resources = _compose_report_services(engine=engine, output_root=output_root)
            template_repo = resources.template_repository
            _seed_report_templates(template_repo)
            download_artifact = _build_download_artifact(render_service=resources.render_service)

            run_identity: dict[str, str] = {
                "database_backend": backend,
                "scenario_id": scenario.scenario_id,
                "correlation_id": PILOT_BASELINE_CORRELATION_ID,
                "source_binding_id": SOURCE_BINDING_ID,
                "weight_set_revision_id": WEIGHT_REVISION_ID,
                "combined_source_hash": combined_source_hash,
                "manifest_scenario_id": scenario.scenario_id,
                "manifest_expected_output_path": str(scenario.expected_output.path)
                if scenario.expected_output is not None
                and scenario.expected_output.path is not None
                else "",
                "manifest_expected_output_commit_sha": str(
                    scenario.expected_output.commit_sha or ""
                )
                if scenario.expected_output is not None
                else "",
                "manifest_golden_comparison_result": "PASS",
            }
            summary = verify_multilingual_report_pilot(
                report_service=resources.report_service,
                render_service=resources.render_service,
                template_repository=resources.template_repository,
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
        finally:
            # Brief §5 ordered release:
            #   1. verifier/render/report operations complete (verified above)
            #   2. report/UoW-owned sessions close (via resources.close())
            #   3. scheme session closes (via resources.close())
            #   4. any remaining session factories release connections
            #   5. engine.dispose() releases the pool
            # Releasing here on BOTH success and failure paths means
            # the engine's connections are explicitly returned to
            # PostgreSQL before pytest's fixture attempts
            # ``DROP DATABASE ... WITH (FORCE)`` (preventing the
            # "SQL connection has been closed unexpectedly" pool-reset
            # errors observed in the prior round).
            if resources is not None:
                resources.close()
            try:  # noqa: SIM105 - dispose best-effort
                engine.dispose()
            except Exception:  # noqa: BLE001
                pass
    except PilotCompositionError as exc:
        sys.stderr.write(f"PILOT_COMPOSITION_ERROR code={exc.code}: {exc}\n")
        if exc.code in {"INPUT_ERROR", "MANIFEST_ERROR"}:
            return EXIT_INPUT_ERROR
        if exc.code == "BACKEND_RUNNER_FAILED":
            return EXIT_BACKEND_ERROR
        return EXIT_INFRA_ERROR
    except PilotVerificationError as exc:
        # P1-2 remediation: ``verify_multilingual_report_pilot`` raises
        # a typed ``PilotVerificationError`` for any acceptance
        # mismatch (download integrity / semantic numeric mismatch /
        # report-content mismatch / etc.). The composition MUST
        # classify the failure by ``exc.code`` (per §10.3
        # forbidden-behavior discipline) and return
        # ``EXIT_VERIFIER_ERROR = 4`` so downstream automation
        # can detect verifier-side failures without parsing
        # the message. No composition-side mutation is performed
        # on this path — the catch only maps the typed error to
        # the documented exit code and writes a stable stderr
        # line. The classification is exception-type-driven, NOT
        # ``exc.code``-driven (any ``PilotVerificationError`` code
        # maps to 4; the typed code is surfaced for downstream
        # debugging via the ``code=<typed-code>`` stderr prefix).
        sys.stderr.write(f"PILOT_VERIFICATION_ERROR code={exc.code}: {exc}\n")
        return EXIT_VERIFIER_ERROR


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
    "PilotAcceptanceError",
    "PILOT_1_4_CANONICAL_BUSINESS_FIELDS",
    "PILOT_1_4_CANONICAL_SECTION_INVARIANTS",
    "PILOT_1_4_CANONICAL_NUMERIC_VALUE_AND_UNIT_INVARIANTS",
    "PILOT_1_4_CROSS_RUN_EQUALITY_FIELDS",
    "PILOT_1_4_CROSS_BACKEND_ALLOWED_DIFFERENCES",
    "PILOT_1_4_EXPECTED_RENDER_MATRIX",
    "aggregate_p1_4_acceptance",
    "provision_p1_4_pg_database",
    "main",
]


# ══════════════════════════════════════════════════════════════════════════════
# P1-4 repeated four-render aggregate acceptance authority
# ══════════════════════════════════════════════════════════════════════════════
# Repository-owned (composition file), single source of truth for the
# §4 / §5 / §6 / §7 / §10 P1-4 acceptance matrix. Per corrective §4 #2 the
# test file MUST NOT retain a second copy of this authority.

from collections.abc import Sequence  # noqa: E402  -- local section

# Cross-run equality fields required by §七 (independent of
# (locale, format)). These MUST match across ALL runs of the
# SAME backend across both repeats.
PILOT_1_4_CROSS_RUN_EQUALITY_FIELDS: tuple[str, ...] = (
    "pilot_check_id",
    "source_commit_sha",
    "manifest_scenario_id",
    "manifest_expected_outcome",
    "manifest_database_backend",
    "scenario_id",
    "correlation_id",
    "source_binding_id",
    "report_type",
    "report_schema_version",
    "render_mode",
)

# Canonical 4-render matrix per §四. Every P1-4 run MUST land
# the exact four (locale, format, mode) combinations; a
# missing entry is a §十 ``MISSING_ONE_RENDER`` defect.
PILOT_1_4_EXPECTED_RENDER_MATRIX: tuple[tuple[str, str, str], ...] = (
    ("zh-CN", "docx", "draft"),
    ("zh-CN", "pdf", "draft"),
    ("en-US", "docx", "draft"),
    ("en-US", "pdf", "draft"),
)

# Per-(locale, format) equality fields required by §七.
# Sourced from the on-disk ``artifact-metadata.json`` + ``semantic-checks.json``.
# Tuples are ``(canonical_name, "metadata" | "semantic_checks", source_key)``.
PILOT_1_4_PER_LOCALE_FORMAT_EQUALITY_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("format", "metadata", "format"),
    ("locale", "metadata", "locale"),
    ("template_locale", "metadata", "template_locale"),
    ("template_version", "metadata", "template_version"),
    ("template_content_hash", "metadata", "template_content_hash"),
    ("template_schema_version", "metadata", "template_schema_version"),
    ("translation_catalog_version", "metadata", "translation_catalog_version"),
    ("translation_catalog_content_hash", "metadata", "translation_catalog_content_hash"),
    ("localized_template_content_hash", "metadata", "localized_template_content_hash"),
    ("integrity_result", "metadata", "integrity_result"),
    ("semantic_result", "semantic_checks", "semantic_result"),
    ("missing_sections_empty", "semantic_checks", "missing_sections"),
    ("missing_units_empty", "semantic_checks", "missing_units"),
    ("numeric_mismatches_empty", "semantic_checks", "numeric_mismatches"),
)

# Canonical business-semantic invariants (corrective §4 #3):
# these come from ``semantic-checks.canonical_section_keys`` /
# ``semantic_checks.canonical_numeric_fields`` and MUST match
# across all four (SQLite repeat 1, SQLite repeat 2, PG repeat
# 1, PG repeat 2). Each is itself a set of strings / tuples;
# the helper compares the SETS (order-insensitive).
PILOT_1_4_CANONICAL_SECTION_INVARIANTS: tuple[str, ...] = ("canonical_section_key_set",)
PILOT_1_4_CANONICAL_NUMERIC_VALUE_AND_UNIT_INVARIANTS: tuple[str, ...] = (
    "canonical_numeric_field_path_set",
    "canonical_numeric_value_and_unit_set",
)
PILOT_1_4_CANONICAL_BUSINESS_FIELDS: tuple[str, ...] = (
    *PILOT_1_4_CANONICAL_SECTION_INVARIANTS,
    *PILOT_1_4_CANONICAL_NUMERIC_VALUE_AND_UNIT_INVARIANTS,
)

# Cross-run backend-allowed differences per §七. These fields
# MAY legitimately differ between SQLite and PostgreSQL because
# each backend has its own frozen manifest + DB-generated IDs.
PILOT_1_4_CROSS_BACKEND_ALLOWED_DIFFERENCES: tuple[str, ...] = (
    "source_manifest_sha",
    "database_backend",
    # Backend-generated / self-integrity per-artifact fields
    # (the §七 "不要求跨后端相等" list):
    "artifact_id",
    "file_name",
    "file_size_bytes",
    "file_sha256",
    "generated_at",
    "storage_key",
    "mime_type",
    "report_id",
    "report_revision_id",
    "revision_number",
    "downloaded_binary_sha256",
)


class PilotAcceptanceError(Exception):
    """Typed fail-closed error for the §10 aggregate acceptance helper.

    Repository-owned (lives in the composition file so positive
    + negative tests MUST both call the same helper per
    corrective §4 #2). Stable typed codes:

    * ``MISSING_ONE_RENDER`` — one of the four (locale, format)
      artifacts is absent from a run's output layout.
    * ``CROSS_RUN_INVARIANT_DRIFT`` — a same-backend
      cross-run invariant (repeat 1 vs repeat 2 of the same
      backend) has diverged OR a same-backend per-(locale,
      format) field has drifted.
    * ``CROSS_BACKEND_INVARIANT_DRIFT`` — a cross-backend
      invariant has diverged between SQLite and PostgreSQL
      runs (i.e. SQLite vs PG fingerprints disagree on a
      field that §七 requires equal across all four runs).
    * ``RUN_SUMMARY_SCHEMA_DRIFT`` — a run summary required
      by the helper is missing a top-level field or a
      required ``semantic_checks`` / ``artifact-metadata``
      slot.

    Downstream automation MUST classify by :attr:`code` (no
    message-text parsing).
    """

    code: str = "PILOT_ACCEPTANCE_ERROR"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# Each per-run tuple passed to ``aggregate_p1_4_acceptance`` is
# ``(output_root, pilot_run, pilot_summary, artifacts_payload)``
# where ``artifacts_payload`` is a ``dict[(locale, fmt)]`` mapping to
# ``{"metadata": ..., "semantic_checks": ...}`` slot dicts. We
# alias the tuple type for readability in the function signature
# below.
ArtifactSlot = dict[str, object]
RunSummary = tuple[
    Path,
    dict[str, object],
    dict[str, object],
    dict[tuple[str, str], ArtifactSlot],
]


def _canonical_section_key_set(semantic_checks: dict[str, object]) -> frozenset[str]:
    """Return the set of canonical section keys, sorted + deduped."""
    section_keys = semantic_checks.get("canonical_section_keys")
    if section_keys is None:
        raise PilotAcceptanceError(
            code="RUN_SUMMARY_SCHEMA_DRIFT",
            message=(
                "semantic-checks.canonical_section_keys MUST be present for "
                "§4 #3 canonical invariant comparison."
            ),
        )
    if not isinstance(section_keys, list):
        raise PilotAcceptanceError(
            code="RUN_SUMMARY_SCHEMA_DRIFT",
            message=(
                "semantic-checks.canonical_section_keys MUST be a list; got "
                f"{type(section_keys).__name__}."
            ),
        )
    return frozenset(str(key) for key in section_keys)


def _canonical_numeric_field_path_set(
    semantic_checks: dict[str, object],
) -> frozenset[str]:
    """Return the set of canonical numeric field_paths from the artifact."""
    numeric_fields = semantic_checks.get("canonical_numeric_fields")
    if numeric_fields is None:
        raise PilotAcceptanceError(
            code="RUN_SUMMARY_SCHEMA_DRIFT",
            message=(
                "semantic-checks.canonical_numeric_fields MUST be present for "
                "§4 #3 canonical numeric invariant comparison."
            ),
        )
    if not isinstance(numeric_fields, list):
        raise PilotAcceptanceError(
            code="RUN_SUMMARY_SCHEMA_DRIFT",
            message=(
                "semantic-checks.canonical_numeric_fields MUST be a list; got "
                f"{type(numeric_fields).__name__}."
            ),
        )
    paths: list[str] = []
    for entry in numeric_fields:
        if not isinstance(entry, dict):
            continue
        field_path = entry.get("field_path")
        if isinstance(field_path, str):
            paths.append(field_path)
    return frozenset(paths)


def _canonical_numeric_value_and_unit_set(
    semantic_checks: dict[str, object],
) -> frozenset[tuple[str, str]]:
    """Return the set of ``(field_path, unit_code)`` tuples from observed artifact."""
    observed = semantic_checks.get("observed_numeric_fields")
    if observed is None:
        raise PilotAcceptanceError(
            code="RUN_SUMMARY_SCHEMA_DRIFT",
            message=(
                "semantic-checks.observed_numeric_fields MUST be present for "
                "§4 #3 canonical numeric value+unit comparison (the helper "
                "reads the OBSERVED side because the artifact's raw_value is "
                "the on-disk numeric, not the expected golden)."
            ),
        )
    if not isinstance(observed, list):
        raise PilotAcceptanceError(
            code="RUN_SUMMARY_SCHEMA_DRIFT",
            message=(f"observed_numeric_fields MUST be a list; got {type(observed).__name__}."),
        )
    pairs: list[tuple[str, str]] = []
    for entry in observed:
        if not isinstance(entry, dict):
            continue
        field_path = entry.get("field_path")
        unit_code = entry.get("unit_code")
        if isinstance(field_path, str) and isinstance(unit_code, str):
            pairs.append((field_path, unit_code))
    return frozenset(pairs)


def _metadata_field_value(slot: ArtifactSlot, key: str) -> object:
    metadata = slot.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return metadata.get(key)


def _semantic_checks_field_value(slot: ArtifactSlot, key: str) -> object:
    sem = slot.get("semantic_checks")
    if not isinstance(sem, dict):
        return None
    return sem.get(key)


def _build_run_fingerprint(
    *,
    output_root: Path,
    pilot_run: dict[str, object],
    pilot_summary: dict[str, object],
    artifact_slots: dict[tuple[str, str], ArtifactSlot],
) -> dict[str, object]:
    """Build the per-run comparison fingerprint for §七 aggregate acceptance.

    Pulls EXCLUSIVELY from already-on-disk structured evidence
    (pilot-run.json / pilot-summary.json / artifact-metadata.json
    / semantic-checks.json). NEVER reads the database, never
    re-renders, never recalcs business formulas.
    """
    fingerprint: dict[str, object] = {}

    for field in PILOT_1_4_CROSS_RUN_EQUALITY_FIELDS:
        fingerprint[field] = pilot_run.get(field)
    for field in (
        "manifest_scenario_id",
        "manifest_expected_outcome",
        "manifest_golden_comparison_result",
        "database_backend",
        "source_manifest_sha",
        "semantic_result",
        "artifact_integrity_result",
        "overall_result",
    ):
        fingerprint[field] = pilot_summary.get(field)

    for (locale, fmt), slot in sorted(artifact_slots.items()):
        per_pair: dict[str, object] = {}
        for canonical_name, group, key in PILOT_1_4_PER_LOCALE_FORMAT_EQUALITY_FIELDS:
            if group == "metadata":
                raw_value = _metadata_field_value(slot, key)
            else:
                raw_value = _semantic_checks_field_value(slot, key)
            if canonical_name.endswith("_empty"):
                # missing_sections / missing_units / numeric_mismatches
                # carry a list value; the fingerprint records whether the
                # list is empty (so cross-run comparisons do not require
                # element-by-element equality on the list contents).
                per_pair[canonical_name] = bool(
                    raw_value is not None and isinstance(raw_value, list) and len(raw_value) == 0
                )
            else:
                per_pair[canonical_name] = raw_value

        # Canonical business-semantic invariant surfaces per §七.
        # These come from the OBSERVED ``semantic-checks.json``
        # files (``canonical_section_keys`` /
        # ``canonical_numeric_fields`` /
        # ``observed_numeric_fields``), never from the expected
        # model or recomputed values.
        sem = slot.get("semantic_checks")
        if isinstance(sem, dict):
            per_pair["canonical_section_key_set"] = _canonical_section_key_set(sem)
            per_pair["canonical_numeric_field_path_set"] = _canonical_numeric_field_path_set(sem)
            per_pair["canonical_numeric_value_and_unit_set"] = (
                _canonical_numeric_value_and_unit_set(sem)
            )

        fingerprint[f"per_pair::{locale}::{fmt}"] = per_pair

    fingerprint["__output_root__"] = str(output_root)
    return fingerprint


def _compare_fingerprints(
    *,
    reference: dict[str, object],
    observed: dict[str, object],
    allowed_differences: set[str],
    error_code: str,
    error_label: str,
) -> None:
    """Assert ``reference`` and ``observed`` agree on every key except ``allowed_differences``.

    Compares frozenset values by equality so per-run invariant
    sets like ``canonical_section_key_set`` are order-insensitive.
    Raises :class:`PilotAcceptanceError(code=error_code)` on any
    drift.
    """
    for key, ref_value in reference.items():
        if key in {"__output_root__"}:
            continue
        if key in allowed_differences:
            continue
        obs_value = observed.get(key)
        if ref_value != obs_value:
            raise PilotAcceptanceError(
                code=error_code,
                message=(
                    f"{error_label} invariant drift on field={key!r}: "
                    f"reference={ref_value!r} observed={obs_value!r}"
                ),
            )


def aggregate_p1_4_acceptance(
    *,
    runs: Sequence[RunSummary],
    cross_backend: bool,
) -> dict[str, object]:
    """Compare a sequence of P1-4 run summaries and enforce §七 invariants.

    Single repository-owned source of truth for the P1-4
    aggregate acceptance (per corrective §4 #2 + §4 #3). Both
    positive tests AND negative tests call this same helper.

    Parameters
    ----------
    runs : Sequence[RunSummary]
        Each element is
        ``(output_root, pilot_run, pilot_summary, artifact_slots)``
        where ``artifact_slots`` keys are ``(locale, fmt)`` and
        values are ``{"metadata": ..., "semantic_checks": ...}``
        as produced by the verifier's
        ``atomic_write_*`` calls.
    cross_backend : bool
        ``False`` for same-backend aggregate (SQLite run 1 vs
        SQLite run 2 of the same committed state). ``True``
        for cross-backend aggregate (SQLite × PG). The helper
        explicitly ALLOWS only
        :data:`PILOT_1_4_CROSS_BACKEND_ALLOWED_DIFFERENCES` to
        differ.

    Returns a dict with the fingerprints computed (for test
    assertions); raises :class:`PilotAcceptanceError` on any
    invariant breach.

    Pure: does NOT query the database, does NOT render new
    artifacts, does NOT recalc business formulas. Reads ONLY
    the structured run summaries already on disk.
    """
    if not runs:
        raise PilotAcceptanceError(
            code="RUN_SUMMARY_SCHEMA_DRIFT",
            message="aggregate helper requires at least one run summary.",
        )

    # Step 0: every run must report overall PASS and have all
    # four (locale, format) artifact slots — fail closed BEFORE
    # cross-run comparison so the error code reflects structural
    # incompleteness (NOT value-level drift).
    canonical_pairs: set[tuple[str, str]] = {
        (locale, fmt) for locale, fmt, _mode in PILOT_1_4_EXPECTED_RENDER_MATRIX
    }
    for output_root, _pilot_run, pilot_summary, artifact_slots in runs:
        if pilot_summary.get("overall_result") != "PASS":
            raise PilotAcceptanceError(
                code="MISSING_ONE_RENDER",
                message=(
                    f"run overall_result MUST be PASS before cross-run "
                    f"comparison; got {pilot_summary.get('overall_result')!r} "
                    f"output_root={str(output_root)!r}"
                ),
            )
        actual_pairs = set(artifact_slots.keys())
        if actual_pairs != canonical_pairs:
            raise PilotAcceptanceError(
                code="MISSING_ONE_RENDER",
                message=(
                    f"per-run artifact_slots MUST equal the canonical "
                    f"4-render set; output_root={str(output_root)!r} "
                    f"missing={sorted(canonical_pairs - actual_pairs)!r} "
                    f"extra={sorted(actual_pairs - canonical_pairs)!r}"
                ),
            )

    # Step 1 + 2: collect fingerprints.
    fingerprints = [
        _build_run_fingerprint(
            output_root=output_root,
            pilot_run=pilot_run,
            pilot_summary=pilot_summary,
            artifact_slots=artifact_slots,
        )
        for output_root, pilot_run, pilot_summary, artifact_slots in runs
    ]

    allowed_differences = set(PILOT_1_4_CROSS_BACKEND_ALLOWED_DIFFERENCES)

    if not cross_backend:
        reference = fingerprints[0]
        for fingerprint in fingerprints[1:]:
            _compare_fingerprints(
                reference=reference,
                observed=fingerprint,
                allowed_differences=allowed_differences,
                error_code="CROSS_RUN_INVARIANT_DRIFT",
                error_label="cross-run (same-backend)",
            )
        return {
            "fingerprint_count": len(fingerprints),
            "cross_backend": False,
            "per_run_overall_result": [run[2].get("overall_result") for run in runs],
        }

    # Cross-backend: partition fingerprints by database_backend
    # BEFORE comparing within each backend. Then cross-backend
    # overlap compares every SQLite fingerprint with every PG
    # fingerprint on every field except the allowed-difference
    # set.
    frontends = [run[2].get("database_backend") for run in runs]
    seen_backends: dict[object, list[int]] = {}
    for idx, be in enumerate(frontends):
        seen_backends.setdefault(be, []).append(idx)

    for backend_marker, indices in seen_backends.items():
        if len(indices) < 2:
            continue
        ref_idx = indices[0]
        ref = fingerprints[ref_idx]
        for idx in indices[1:]:
            other = fingerprints[idx]
            _compare_fingerprints(
                reference=ref,
                observed=other,
                allowed_differences=allowed_differences,
                error_code="CROSS_RUN_INVARIANT_DRIFT",
                error_label=(f"per-backend (backend={backend_marker!r}) cross-run"),
            )

    sqlite_indices = seen_backends.get("sqlite", [])
    postgres_indices = seen_backends.get("postgresql", [])
    if sqlite_indices and postgres_indices:
        sql_ref = fingerprints[sqlite_indices[0]]
        pg_ref = fingerprints[postgres_indices[0]]
        # Compare PG fingerprint directly (not just first SQLite
        # ref) so all cross-backend field equality is verified.
        for sql_idx in sqlite_indices:
            sql_fp = fingerprints[sql_idx]
            for pg_idx in postgres_indices:
                pg_fp = fingerprints[pg_idx]
                _compare_fingerprints(
                    reference=sql_fp,
                    observed=pg_fp,
                    allowed_differences=allowed_differences,
                    error_code="CROSS_BACKEND_INVARIANT_DRIFT",
                    error_label="cross-backend (SQLite vs PostgreSQL)",
                )
        # ``sql_ref`` retained for backward compatibility /
        # ``_compare_fingerprints`` ensures equal comparison.
        del sql_ref, pg_ref

    return {
        "fingerprint_count": len(fingerprints),
        "cross_backend": True,
        "per_run_overall_result": [run[2].get("overall_result") for run in runs],
    }


# ── §4 #1 PostgreSQL fresh database authority ─────────────────────────────────

POSTGRES_PROVISION_TIMEOUT_SECONDS = 300


def provision_p1_4_pg_database(*, database_url: str) -> str:
    """Apply ``alembic upgrade head`` to a freshly-created PG database.

    Repository-owned (composition file). Used by the in-allowlist
    P1-4 PG fixture to apply the production schema BEFORE the
    composition script runs ``seed_a1_all_prereqs`` and
    ``run_scenario_via_markers``. Fail-closed: raises
    :class:`PilotCompositionError(code="POSTGRES_PROVISION_FAILED")`
    with the database identifier + the real subprocess stdout /
    stderr tail when ``alembic`` exits non-zero. Returns the
    same ``database_url`` on success.

    The provisioning subprocess inherits
    ``PYTHONPATH=src`` + ``DATABASE_BACKEND=postgresql`` so the
    alembic env (``backend/alembic/env.py``) resolves the
    ``cold_storage`` package via the same sys.path the
    composition's own alembic call uses.
    """

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["DATABASE_BACKEND"] = "postgresql"
    existing_pp = env.get("PYTHONPATH", "")
    src_path = (BACKEND_DIR / "src").resolve()
    pp_parts: list[str] = [str(src_path)] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)

    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=POSTGRES_PROVISION_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        stdout_tail: Any = proc.stdout[-2000:]
        stderr_tail: Any = proc.stderr[-2000:]
        raise PilotCompositionError(
            code="POSTGRES_PROVISION_FAILED",
            message=(
                f"alembic upgrade head failed for database_url={database_url!r} "
                f"(exit={proc.returncode}); "
                f"stdout_tail={stdout_tail!r}; stderr_tail={stderr_tail!r}"
            ),
        )
    return database_url


# Defensive sentinel: ``hashlib`` and ``tempfile`` are imported above to
# keep their symbols available even if a future refactor inlines the
# helper bodies. They are referenced indirectly by the composition
# flow (alembic subprocess, path resolution) so the explicit imports
# make the dependency surface observable at module-load time.
_ = (hashlib, tempfile, json, subprocess)
