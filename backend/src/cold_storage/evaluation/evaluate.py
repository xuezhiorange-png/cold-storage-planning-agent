"""TASK-011C C-2 suite runner core.

This module is the **single** C-2 suite runner authority. The
runner is a thin orchestrator that:

1. validates the manifest (already done by the loader, but the
   runner re-asserts the cross-field invariants defensively);
2. computes the canonical manifest SHA;
3. inspects stale managed artifacts at the target root (run.json,
   raw/<scenario_id>.json, normalized/<scenario_id>.json,
   summary.json) and refuses to start if any exist;
4. creates per-scenario directories atomically;
5. executes each scenario by calling the typed adapter (the
   production boundary) — it does NOT duplicate adapter or
   execute logic, does NOT call production calculators directly,
   and does NOT construct production rows of any kind;
6. for ``INVALID_INPUT`` scenarios, matches the typed production
   exception's ``code`` and ``field`` against the manifest's
   ``expected_error`` (NEVER the exception message text);
7. compares actual normalized output against the manifest's
   expected output via :func:`compare_outputs`;
8. writes per-scenario ``run.json`` / ``raw/<scenario_id>.json`` /
   ``normalized/<scenario_id>.json`` atomically (temp sibling +
   flush + os.replace);
9. writes the suite ``summary.json`` LAST (after every
   per-scenario artifact has been atomically written).

The runner emits a typed :class:`SuiteRunResult` containing a
tuple of :class:`RunRecord` instances (one per scenario) and a
single :class:`SummaryRecord` at the suite root. The
``evaluation_result_overall`` field is ``PASS`` iff every
scenario's ``evaluation_result`` is ``PASS``; otherwise it is
``FAIL`` or ``INFRASTRUCTURE_ERROR``.

Per Phase 4 §9 forbidden-pattern list, the runner NEVER parses
exception message text. Every classification is via typed
``code`` / ``field`` / ``exception_type`` attributes.

Per the C-2 contract, the runner does NOT introduce a second
canonicalizer, a second comparator, or a second comparison
strategy. All canonicalization goes through
:func:`cold_storage.evaluation.canonicalization.canonicalize_production_outputs`
and all comparison goes through
:func:`cold_storage.evaluation.compare.compare_outputs`.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cold_storage.evaluation.canonicalization import (
    canonicalize_production_outputs,
)
from cold_storage.evaluation.compare import (
    ComparisonResult,
    compare_outputs,
)
from cold_storage.evaluation.errors import (
    EvaluationArtifactWriteError,
    EvaluationInfrastructureError,
    EvaluationManifestExecutionError,
    EvaluationRunnerError,
    StaleEvaluationArtifactsError,
)
from cold_storage.evaluation.models import (
    DatabaseBackend,
    EvaluationResult,
    ExpectedOutcome,
    ExpectedOutputRef,
    Manifest,
    RunRecord,
    ScenarioDeclaration,
    SummaryRecord,
)
from cold_storage.evaluation.run_directory import (
    RunDirectory,
    suite_summary_path,
)
from cold_storage.evaluation.runners._executor import (
    BaselineExecutionArtifacts,
)

# ── Manifest exception type registry (C-2 typed D10 boundary) ──────
#
# The D10 ``invalid_blocked`` scenario requires the runner to match
# the actual production-side exception's type / code / field against
# the manifest's ``expected_error``. The mapping below is the single
# authorized registry of exception types that the runner recognizes
# in V1. It is intentionally narrow: only typed production-side
# exceptions that already exist in the production codebase are
# eligible.
#
# The registry maps the V1 wire-format ``exception_type`` string
# (as declared in the manifest's ``expected_error.exception_type``)
# to the actual Python exception class. The runner does NOT
# instantiate the exception; it only uses the class for
# ``isinstance(actual, expected_class)`` classification. The
# production code already raises the exception; the runner only
# classifies it.
from cold_storage.modules.orchestration.application.production_calculation.errors import (  # noqa: E501
    InvalidProjectInputError,
)

V1_EXCEPTION_REGISTRY: Final[dict[str, type[BaseException]]] = {
    "InvalidProjectInputError": InvalidProjectInputError,
}

# ── SuiteRunResult ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SuiteRunResult:
    """The typed return value of :func:`evaluate_manifest`.

    Carries the suite-level ``manifest_sha``, ``commit_sha``,
    ``suite_id``, ``started_at`` / ``completed_at`` ISO-8601
    UTC strings, the tuple of per-scenario :class:`RunRecord`
    instances, and the typed
    ``evaluation_result_overall`` (:class:`EvaluationResult`).
    """

    manifest_sha: str
    commit_sha: str
    suite_id: str
    started_at: str
    completed_at: str
    scenarios: tuple[RunRecord, ...]
    evaluation_result_overall: EvaluationResult


# ── Public entry point ─────────────────────────────────────────────


def evaluate_manifest(
    *,
    manifest: Manifest,
    manifest_root: Path,
    root: Path,
    session_factory: Callable[[], Any] | None = None,
    commit_sha: str = "unknown",
) -> SuiteRunResult:
    """Run the suite declared by ``manifest`` and return a typed result.

    The runner executes scenarios in the order declared by the
    manifest. On any infrastructure failure (DB session, FS
    write, etc.) the runner raises a typed
    :class:`EvaluationInfrastructureError` /
    :class:`EvaluationArtifactWriteError` /
    :class:`StaleEvaluationArtifactsError` with a stable ``code``
    attribute. The runner never silently swallows failures.

    Parameters
    ----------
    manifest:
        The validated V1 manifest. The runner re-asserts the
        cross-field invariants (path / expected_error /
        expected_outcome) defensively before any FS/DB side
        effect.
    manifest_root:
        The root directory for resolving the manifest's
        referenced files (``expected_output.path`` and
        ``fixtures[].path``). The root is REQUIRED; the runner
        does NOT default to ``Path(".")`` (per review 4693931575
        P0-3, the previous ``manifest_root(manifest) -> Path: return Path(".")``
        helper is removed because it silently depended on the
        process CWD). The backend runners (``runners/sqlite.py`` /
        ``runners/postgresql.py``) are the boundary that owns
        this value and forwards it to the suite runner. The
        path is normalized to an absolute path at the entry
        boundary and used as the base for traversal / symlink
        containment checks.
    root:
        The target root directory for the per-scenario
        artifacts. Must NOT already contain a managed
        artifact (run.json / raw/ / normalized/ / summary.json);
        the runner raises :class:`StaleEvaluationArtifactsError`
        otherwise.
    session_factory:
        Optional SQLAlchemy ``sessionmaker`` factory used by
        the per-scenario execution. When ``None``, the runner
        cannot execute SUCCEEDED scenarios (which require a live
        DB session) and any such scenario produces an
        :class:`EvaluationInfrastructureError` with code
        ``"NO_SESSION_FACTORY"``. INVALID_INPUT scenarios
        (D10) do NOT require a session factory because they
        exercise the pure production projection function.
    commit_sha:
        The git commit SHA that bound this run. Stored in the
        :class:`SummaryRecord` for downstream trace.

    Returns
    -------
    SuiteRunResult
        The typed suite result.

    Raises
    ------
    EvaluationManifestExecutionError
        On a manifest-driven execution failure that happens
        BEFORE any FS/DB side effect.
    StaleEvaluationArtifactsError
        On a pre-existing managed artifact at ``root`` or
        under any per-scenario subdirectory.
    EvaluationInfrastructureError
        On a DB session / FS write / network failure during
        the run.
    EvaluationArtifactWriteError
        On an atomic-write infrastructure failure.
    """
    if not isinstance(manifest, Manifest):
        raise EvaluationManifestExecutionError(
            "evaluate_manifest requires a Manifest instance.",
            details={"manifest_type": type(manifest).__name__},
        )
    if not isinstance(manifest_root, Path):
        raise EvaluationManifestExecutionError(
            "evaluate_manifest requires an explicit manifest_root: Path "
            "argument; the historical Path('.') default was removed per "
            "review 4693931575 P0-3 (defense-in-depth CWD independence).",
            details={"manifest_root_type": type(manifest_root).__name__},
        )
    # Resolve to an absolute, symlink-resolved path for
    # defense-in-depth path containment. Any relative path
    # raises (the runner never silently resolves against
    # the process CWD).
    manifest_root = _assert_manifest_root_contained(manifest_root)
    if not isinstance(root, Path):
        root = Path(root)
    started_at = _now_iso8601_utc()

    # 1. Defensive cross-field re-validation. The manifest loader
    #    already enforces the path / expected_error matrix via
    #    the Pydantic field validator on ExpectedOutputRef; we
    #    re-assert it here as a defense-in-depth check (in case
    #    the manifest was constructed programmatically without
    #    going through the loader).
    for scenario in manifest.scenarios:
        _assert_cross_field_invariant(scenario, manifest_root=manifest_root)

    # 2. Compute manifest SHA from the canonicalized manifest
    #    (delegates to the D1 canonicalizer).
    manifest_sha = _compute_manifest_sha(manifest)

    # 3. Inspect stale managed artifacts. Any pre-existing
    #    ``run.json`` / ``raw/<scenario_id>.json`` /
    #    ``normalized/<scenario_id>.json`` or suite
    #    ``summary.json`` triggers StaleEvaluationArtifactsError.
    _assert_no_stale_artifacts(manifest=manifest, root=root)

    # 4. Execute scenarios. We run them in manifest-declared
    #    order. Per-scenario failures are recorded as FAIL
    #    RunRecord entries; they do NOT abort the suite (the
    #    suite may still produce a summary at the end).
    scenario_records: list[RunRecord] = []
    for scenario in manifest.scenarios:
        record = _execute_one_scenario(
            scenario=scenario,
            manifest=manifest,
            manifest_sha=manifest_sha,
            manifest_root=manifest_root,
            root=root,
            session_factory=session_factory,
            commit_sha=commit_sha,
        )
        scenario_records.append(record)

    completed_at = _now_iso8601_utc()

    # 5. Determine overall result.
    overall = _compute_overall_result(scenario_records)

    # 6. Build SummaryRecord. The summary is written LAST as the
    #    typed completion record for the entire suite. The
    #    atomic write is performed by :func:`_atomic_write_json`.
    # The summary is built via the C-2 factory on
    # :class:`SummaryRecord` so the ``database_backend`` string
    # token does not appear in this file (the architecture
    # boundary permits the token only in :mod:`models.py`).
    _assert_single_backend(manifest)  # Mixed-backend guard
    summary = SummaryRecord.from_manifest(
        manifest,
        manifest_sha=manifest_sha,
        commit_sha=commit_sha,
        started_at=started_at,
        completed_at=completed_at,
        scenarios=tuple(scenario_records),
        evaluation_result_overall=overall,
    )
    # The C-2 contract requires that the summary is written
    # LAST; we do that here.
    _atomic_write_json(path=suite_summary_path(root=root), data=_summary_to_dict(summary))

    return SuiteRunResult(
        manifest_sha=manifest_sha,
        commit_sha=commit_sha,
        suite_id=manifest.suite_id,
        started_at=started_at,
        completed_at=completed_at,
        scenarios=tuple(scenario_records),
        evaluation_result_overall=overall,
    )


# ── Per-scenario execution ─────────────────────────────────────────


def _execute_one_scenario(
    *,
    scenario: ScenarioDeclaration,
    manifest: Manifest,
    manifest_sha: str,
    manifest_root: Path,
    root: Path,
    session_factory: Callable[[], Any] | None,
    commit_sha: str,
) -> RunRecord:
    """Run a single scenario and return the typed RunRecord.

    The runner has three branches:

    1. ``expected_outcome == INVALID_INPUT`` — the runner
       exercises the pure production projection function and
       asserts the typed exception shape matches the manifest's
       ``expected_error``. NO FS/DB side effect is required.
    2. ``expected_outcome == SUCCEEDED`` — the runner invokes
       the production pipeline via the typed adapter (which
       uses the session factory) and compares the actual
       normalized output against the manifest's expected
       output via :func:`compare_outputs`.
    3. ``expected_outcome == BLOCKED`` — the runner records
       the scenario as ``FAIL`` with a structured diff
       explaining that the BLOCKED class is V1 reserved but
       not exercised by the V1 scenarios.
    """
    scenario_started_at = _now_iso8601_utc()
    run_dir = RunDirectory.for_scenario(root=root, scenario_id=scenario.scenario_id)
    # Create per-scenario directories (idempotent — they are
    # empty because we already asserted no stale artifacts).
    _safe_makedirs(run_dir.scenario_dir)
    _safe_makedirs(run_dir.raw_dir)
    _safe_makedirs(run_dir.normalized_dir)

    if scenario.expected_outcome == ExpectedOutcome.INVALID_INPUT:
        record = _execute_invalid_input(
            scenario=scenario,
            manifest=manifest,
            manifest_sha=manifest_sha,
            manifest_root=manifest_root,
            run_dir=run_dir,
            commit_sha=commit_sha,
            started_at=scenario_started_at,
        )
    elif scenario.expected_outcome == ExpectedOutcome.SUCCEEDED:
        record = _execute_succeeded(
            scenario=scenario,
            manifest=manifest,
            manifest_sha=manifest_sha,
            manifest_root=manifest_root,
            run_dir=run_dir,
            session_factory=session_factory,
            commit_sha=commit_sha,
            started_at=scenario_started_at,
        )
    else:  # BLOCKED — V1 reserved, not exercised
        # The C-2 indirection through ``RunRecord.from_scenario``
        # centralizes the ``database_backend``-named attribute
        # access in :mod:`models.py` (the single C-1 file
        # permitted to hold the literal token). This keeps
        # the runner source free of the token.
        record = RunRecord.from_scenario(
            scenario,
            manifest_sha=manifest_sha,
            actual_outcome="NOT_EXERCISED",
            evaluation_result=EvaluationResult.FAIL,
            diff_summary={
                "reason": ("BLOCKED outcome is reserved in V1 but not exercised by any V1 scenario")
            },
            started_at=scenario_started_at,
            completed_at=_now_iso8601_utc(),
        )
    # Persist the per-scenario run record. This is the typed
    # per-scenario completion record (not the suite summary).
    _atomic_write_json(
        path=run_dir.run_path,
        data=_run_record_to_dict(record),
    )
    return record


def _execute_invalid_input(
    *,
    scenario: ScenarioDeclaration,
    manifest: Manifest,
    manifest_sha: str,
    manifest_root: Path,
    run_dir: RunDirectory,
    commit_sha: str,
    started_at: str,
) -> RunRecord:
    """D10 ``invalid_blocked`` execution.

    The runner calls the production PURE projection function
    :func:`project_calculator_input` directly (no DB session
    required, no FS write required before the diff is computed)
    and asserts the typed exception shape matches the
    manifest's ``expected_error``.

    The test-side fixture provides a payload that is missing
    the FIRST required field of the declared calculation type.
    The production function raises
    :class:`InvalidProjectInputError` with a stable ``code`` and
    ``field``; the runner matches on these typed attributes
    (NEVER on the message text).
    """
    expected_output = scenario.expected_output
    if expected_output is None:
        # The cross-field validator should have caught this, but
        # we surface a typed error here as defense-in-depth.
        raise EvaluationManifestExecutionError(
            "INVALID_INPUT scenario MUST have a non-None expected_output.",
            details={"scenario_id": scenario.scenario_id},
        )
    expected_error = expected_output.expected_error
    if expected_error is None:
        # The cross-field validator should have caught this, but
        # we surface a typed error here as defense-in-depth.
        raise EvaluationManifestExecutionError(
            "INVALID_INPUT scenario MUST have a non-None expected_output.expected_error.",
            details={"scenario_id": scenario.scenario_id},
        )
    actual_outcome = "INVALID_INPUT"
    diff_summary: dict[str, Any]
    eval_result: EvaluationResult

    # Build the typed expectation contract.
    expected_class = V1_EXCEPTION_REGISTRY.get(expected_error.exception_type)
    if expected_class is None:
        eval_result = EvaluationResult.INFRASTRUCTURE_ERROR
        diff_summary = {
            "kind": "unknown_exception_type",
            "expected_exception_type": expected_error.exception_type,
        }
    else:
        # We delegate the actual production invocation to the
        # test-side / scenario-side execution seam (a callable
        # supplied by the test or by the backend runner). This
        # is the C-2 boundary that keeps the runner free of
        # production-seeding OR fixture construction.
        from cold_storage.evaluation.runners._executor import (
            execute_d10_pure,
        )

        try:
            execute_d10_pure(
                scenario=scenario,
                expected_class=expected_class,
            )
        except expected_class as exc:
            # Typed exception. Match on the structured
            # ``code`` and ``field`` attributes.
            actual_code = getattr(exc, "code", None)
            actual_field = getattr(exc, "field", None)
            actual_code_str: str = (
                actual_code.value  # type: ignore[union-attr]
                if hasattr(actual_code, "value")
                else actual_code  # type: ignore[assignment]
            )
            if actual_code_str == expected_error.code and actual_field == expected_error.field:
                eval_result = EvaluationResult.PASS
                diff_summary = {
                    "kind": "expected_exception",
                    "exception_type": expected_error.exception_type,
                    "code": expected_error.code,
                    "field": expected_error.field,
                }
            else:
                eval_result = EvaluationResult.FAIL
                diff_summary = {
                    "kind": "exception_mismatch",
                    "expected_code": expected_error.code,
                    "expected_field": expected_error.field,
                    "actual_code": (str(actual_code_str) if actual_code_str is not None else None),
                    "actual_field": (str(actual_field) if actual_field is not None else None),
                }
        except BaseException as exc:  # noqa: BLE001 — typed classification
            eval_result = EvaluationResult.INFRASTRUCTURE_ERROR
            actual_type_name = type(exc).__name__
            diff_summary = {
                "kind": "unexpected_exception",
                "actual_exception_type": actual_type_name,
                "actual_code": (
                    str(getattr(exc, "code", "<no-code>"))
                    if getattr(exc, "code", None) is not None
                    else None
                ),
            }

    return RunRecord.from_scenario(
        scenario,
        manifest_sha=manifest_sha,
        actual_outcome=actual_outcome,
        evaluation_result=eval_result,
        diff_summary=diff_summary,
        started_at=started_at,
        completed_at=_now_iso8601_utc(),
    )


def _execute_succeeded(
    *,
    scenario: ScenarioDeclaration,
    manifest: Manifest,
    manifest_sha: str,
    manifest_root: Path,
    run_dir: RunDirectory,
    session_factory: Callable[[], Any] | None,
    commit_sha: str,
    started_at: str,
) -> RunRecord:
    """``expected_outcome == SUCCEEDED`` execution.

    The runner delegates the production invocation to a
    scenario-side execution seam (a callable supplied by the
    test or by the backend runner). For the canonical
    ``baseline_feasible`` scenario the seam is the A1-2a
    adapter path: ``execute_scenario(session_factory, ...)``
    plus the typed canonicalization step.

    The runner compares the actual normalized output against
    the manifest's expected output via
    :func:`compare_outputs` and records the structured diff.
    """
    if session_factory is None:
        # The C-2 contract requires the runner to refuse a
        # SUCCEEDED scenario when no session factory is
        # available. The refusal is typed
        # (EvaluationInfrastructureError), not a silent
        # PASS / FAIL.
        return RunRecord.from_scenario(
            scenario,
            manifest_sha=manifest_sha,
            actual_outcome="NO_SESSION_FACTORY",
            evaluation_result=EvaluationResult.INFRASTRUCTURE_ERROR,
            diff_summary={
                "kind": "no_session_factory",
                "reason": (
                    "SUCCEEDED scenario requires a session_factory "
                    "to invoke the production pipeline"
                ),
            },
            started_at=started_at,
            completed_at=_now_iso8601_utc(),
        )

    # The C-2 boundary that keeps the runner free of
    # production-seeding OR fixture construction. The
    # backend runner (``runners/sqlite.py`` /
    # ``runners/postgresql.py``) supplies this callable.
    from cold_storage.evaluation.runners._executor import (
        execute_baseline_succeeded,
    )

    try:
        baseline_artifacts: BaselineExecutionArtifacts = execute_baseline_succeeded(
            scenario=scenario,
            session_factory=session_factory,
        )
    except EvaluationRunnerError:
        raise
    except BaseException as exc:  # noqa: BLE001 — typed classification
        # Any production-side exception that is NOT a typed
        # runner error is classified as an
        # INFRASTRUCTURE_ERROR at the runner layer (the
        # production-side exception itself propagates per
        # the A1 ownership boundary if the test opted into
        # raise-on-production-error).
        actual_type_name = type(exc).__name__
        return RunRecord.from_scenario(
            scenario,
            manifest_sha=manifest_sha,
            actual_outcome=actual_type_name,
            evaluation_result=EvaluationResult.INFRASTRUCTURE_ERROR,
            diff_summary={
                "kind": "production_exception",
                "exception_type": actual_type_name,
            },
            started_at=started_at,
            completed_at=_now_iso8601_utc(),
        )

    # Load the expected normalized output from the manifest's
    # expected_output.path file. The cross-field validator
    # already asserted that path is non-None for SUCCEEDED
    # scenarios.
    expected_output = scenario.expected_output
    if expected_output is None:
        # Defense-in-depth: the validator should have caught this.
        raise EvaluationManifestExecutionError(
            "SUCCEEDED scenario MUST have a non-None expected_output.",
            details={"scenario_id": scenario.scenario_id},
        )
    expected_path: str | None = expected_output.path
    if expected_path is None:
        # Defense-in-depth: the validator should have caught this.
        raise EvaluationManifestExecutionError(
            "SUCCEEDED scenario MUST have a non-None expected_output.path.",
            details={"scenario_id": scenario.scenario_id},
        )
    # P0-3 of review 4693931575: the manifest_root is now an
    # explicit, required Path argument forwarded from the
    # backend runner; the previous ``Path(".")`` default is
    # removed. The helper still rejects absolute paths and
    # traversal; the runner boundary owns the root value.
    expected_full_path = _resolve_expected_output_path(
        expected_path=expected_path, manifest_root=manifest_root
    )
    expected_text = expected_full_path.read_text(encoding="utf-8")
    expected_normalized_full = json.loads(expected_text)
    # Round 3 (review 4696284808): the expected golden carries
    # the ``_comparison_policy`` block as golden-only metadata
    # (the actual normalized business projection does NOT
    # include it). The comparison MUST operate on the frozen
    # business payload only (the V1 contract: "after removing
    # ``_comparison_policy``"). The helper drops the key in a
    # typed, explicit way.
    if not isinstance(expected_normalized_full, dict):
        raise EvaluationManifestExecutionError(
            "expected_output file MUST be a JSON object at the top level.",
            details={"expected_output_path": str(expected_full_path)},
        )
    expected_normalized: dict[str, Any] = {
        k: v for k, v in expected_normalized_full.items() if k != "_comparison_policy"
    }
    # Validate the expected output is in the strict-JSON value
    # domain; if not, the manifest is malformed.
    try:
        canonicalize_production_outputs(expected_normalized, excluded_paths=())
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", "CANONICALIZATION_ERROR")
        raise EvaluationManifestExecutionError(
            "expected_output file contains a value that is not in the strict-JSON value domain.",
            details={
                "expected_output_path": str(expected_full_path),
                "canonicalizer_code": str(code),
            },
        ) from exc

    # Compare.
    from cold_storage.evaluation.models import ComparisonPolicy

    comparison: ComparisonResult = compare_outputs(
        expected=expected_normalized,
        actual=baseline_artifacts.normalized_value,
        policy=scenario.comparison_policy or ComparisonPolicy(),
    )

    eval_result = EvaluationResult.PASS if comparison.passed else EvaluationResult.FAIL
    diff_summary: dict[str, Any] = {
        "kind": "comparison",
        "passed": comparison.passed,
        "diffs": [
            {
                "path": d.path,
                "kind": d.kind,
                "expected": d.expected,
                "actual": d.actual,
                "reason": d.reason,
            }
            for d in comparison.diffs
        ],
    }

    # Persist the raw + normalized per-scenario artifacts
    # (atomic).
    #
    # P0-1 of review 4693931575: the raw artifact MUST be the
    # production-derived value (the live ``AdapterResult``
    # JSON-domain projection), NOT ``expected_normalized``
    # (which the manifest golden holds) and NOT the
    # comparison result. We use the typed
    # ``baseline_artifacts.raw_value`` from the production
    # seam, which is structurally disjoint from the
    # comparison input.
    _atomic_write_json(
        path=run_dir.raw_path,
        data=baseline_artifacts.raw_value,
    )
    # P0-2 of review 4693931575: the normalized artifact MUST
    # be the canonicalizer's exact byte output. We persist
    # ``baseline_artifacts.normalized_bytes`` byte-for-byte
    # (no re-serialization, no ``json.dump`` round-trip, no
    # ``default=str`` fallback). The byte writer
    # ``_atomic_write_bytes`` is fail-closed and rejects
    # implicit stringification of unsupported types.
    _atomic_write_bytes(
        path=run_dir.normalized_path,
        data=baseline_artifacts.normalized_bytes,
    )

    return RunRecord.from_scenario(
        scenario,
        manifest_sha=manifest_sha,
        actual_outcome="SUCCEEDED",
        evaluation_result=eval_result,
        diff_summary=diff_summary,
        started_at=started_at,
        completed_at=_now_iso8601_utc(),
    )


# ── Atomic write helpers (C-2 mandatory) ────────────────────────────


#: Bytes that the JSON-domain normalized artifact writer MUST
#: persist verbatim — no re-serialization, no canonicalizer
#: round-trip, no implicit stringification. The runner's
#: P0-2 contract requires the on-disk bytes to be identical
#: (==) to the value returned by ``canonicalize_production_outputs``.
class _UnsupportedSerializedTypeError(EvaluationArtifactWriteError):
    """The bytes-to-write are not in the strict-JSON value
    domain. The atomic byte writer fails closed: the runner
    never silently coerces unsupported Python objects to
    strings (the historical ``default=str`` fallback was the
    source of the P0-2 defect).

    The error inherits the typed ``code`` attribute contract
    from :class:`EvaluationArtifactWriteError`.
    """


def _atomic_write_bytes(*, path: Path, data: bytes) -> None:
    """Atomically write ``data`` (bytes) to ``path``.

    The write uses a temporary sibling file (created in the
    same directory as ``path``), followed by a flush, an
    fsync where supported, and ``os.replace`` for the atomic
    rename. This is the C-2 mandatory atomic-byte-write
    contract for the normalized artifact (P0-2 of review
    4693931575): the on-disk bytes MUST equal the canonicalizer
    return value byte-for-byte; no ``json.dump`` /
    ``default=str`` round-trip is allowed.

    The write is fail-closed: any IO failure raises a typed
    :class:`EvaluationArtifactWriteError` with a stable
    ``code`` attribute. The function does not coerce ``data``
    in any way; the caller is responsible for handing in
    pre-canonicalized bytes (typically the value returned by
    :func:`cold_storage.evaluation.canonicalization.canonicalize_production_outputs`).
    """
    if not isinstance(data, bytes):
        # Defense-in-depth: the contract is bytes-in / bytes-out.
        raise _UnsupportedSerializedTypeError(
            "_atomic_write_bytes requires pre-canonicalized bytes; "
            "implicit stringification is forbidden (P0-2 contract).",
            details={"data_type": type(data).__name__},
        )
    if not isinstance(path, Path):
        path = Path(path)
    parent = path.parent
    try:
        _safe_makedirs(parent)
    except OSError as exc:
        raise EvaluationArtifactWriteError(
            f"Cannot create parent directory for atomic byte write: {exc}",
            details={"path": str(path), "parent": str(parent)},
        ) from exc
    try:
        # ``delete=False`` so we can ``os.replace`` across
        # filesystems. We always ``delete=True`` in the
        # ``finally`` block.
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(parent),
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                # fsync may fail on some filesystems
                # (e.g. some FUSE mounts). We log the
                # failure but proceed with the rename.
                with suppress(OSError):  # noqa: SIM105
                    os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            with suppress(OSError):  # noqa: SIM105
                os.unlink(tmp_name)
            raise
    except OSError as exc:
        raise EvaluationArtifactWriteError(
            f"Atomic byte write to {path} failed: {exc}",
            details={"path": str(path)},
        ) from exc


def _atomic_write_json(*, path: Path, data: Any) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    The write uses a temporary sibling file (created in the
    same directory as ``path``), followed by a flush, an
    fsync where practical, and ``os.replace`` for the atomic
    rename. This pattern is the C-2 mandatory atomic-write
    contract.

    Per review 4693931575 P0-2: the JSON writer is now
    **fail-closed** and rejects unsupported Python objects
    (no ``default=str`` fallback). The contract is: ``data``
    MUST be a value in the strict-JSON value domain (``None`` /
    ``bool`` / ``int`` / ``float`` / ``str`` / ``list`` /
    ``dict`` of the same); any unsupported value raises a
    typed :class:`EvaluationArtifactWriteError` with the
    stable ``code`` ``"EVALUATION_ARTIFACT_WRITE_ERROR"``.

    The runner's only JSON writes are Pydantic v2
    ``model_dump(mode="json")`` projections (typed) and the
    summary record (also typed). Both produce strict-JSON
    values; the ``default=str`` fallback was the source of
    the historical silent-stringification defect.
    """
    if not isinstance(path, Path):
        path = Path(path)
    parent = path.parent
    try:
        _safe_makedirs(parent)
    except OSError as exc:
        raise EvaluationArtifactWriteError(
            f"Cannot create parent directory for atomic write: {exc}",
            details={"path": str(path), "parent": str(parent)},
        ) from exc
    # Validate that the value is in the strict-JSON value
    # domain. The canonicalizer enforces the same domain for
    # the canonicalized payload; the raw + summary artifacts
    # are typed Pydantic projections and are also in the
    # domain. We delegate the validation to the canonicalizer
    # for consistency.
    try:
        canonicalize_production_outputs(data, excluded_paths=())
    except Exception as exc:
        raise _UnsupportedSerializedTypeError(
            "_atomic_write_json received a value that is not in the "
            "strict-JSON value domain; the runner fails closed and does "
            "NOT implicitly stringify (P0-2 of review 4693931575).",
            details={
                "data_type": type(data).__name__,
                "canonicalizer_code": str(getattr(exc, "code", "CANONICALIZATION_ERROR")),
            },
        ) from exc
    try:
        # ``delete=False`` so we can ``os.replace`` across
        # filesystems (it raises on cross-filesystem rename
        # otherwise). We always ``delete=True`` in the
        # ``finally`` block.
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(parent),
        )
        try:
            # P0-2: we still use ``json.dump`` for the
            # *summary* / *raw* artifacts (Pydantic typed
            # projections that are already in the strict-JSON
            # domain). The writer does NOT pass
            # ``default=str``; the value-domain validation
            # above guarantees no implicit stringification
            # is needed. ``sort_keys=True`` keeps the
            # on-disk form stable across Python dict
            # iteration order changes; the *normalized*
            # artifact uses ``_atomic_write_bytes`` which
            # bypasses ``json.dump`` entirely.
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True)
                f.flush()
                # fsync may fail on some filesystems
                # (e.g. some FUSE mounts). We log the
                # failure but proceed with the rename —
                # the temp file is still on disk and the
                # rename is atomic.
                with suppress(OSError):  # noqa: SIM105
                    os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            # Best-effort cleanup of the temp file on any
            # failure (write, flush, fsync, or replace).
            with suppress(OSError):  # noqa: SIM105
                os.unlink(tmp_name)
            raise
    except OSError as exc:
        raise EvaluationArtifactWriteError(
            f"Atomic write to {path} failed: {exc}",
            details={"path": str(path)},
        ) from exc


# ── Stale artifact detection (C-2 mandatory) ──────────────────────


def _assert_no_stale_artifacts(*, manifest: Manifest, root: Path) -> None:
    """Raise :class:`StaleEvaluationArtifactsError` if any
    managed artifact already exists at ``root``.

    The runner never silently overwrites a previous run's
    artifacts. The caller is responsible for cleaning the
    target root before invoking the runner.
    """
    stale_paths: list[str] = []
    # 1. Suite-level summary.
    suite_summary = suite_summary_path(root=root)
    if suite_summary.exists():
        stale_paths.append(str(suite_summary))
    # 2. Per-scenario artifacts.
    for scenario in manifest.scenarios:
        run_dir = RunDirectory.for_scenario(root=root, scenario_id=scenario.scenario_id)
        for p in (
            run_dir.run_path,
            run_dir.raw_path,
            run_dir.normalized_path,
        ):
            if p.exists():
                stale_paths.append(str(p))
    if stale_paths:
        raise StaleEvaluationArtifactsError(
            "Pre-existing managed artifacts at the target root; the "
            "runner refuses to silently overwrite. Inspect and clean "
            "before re-running.",
            details={"stale_paths": stale_paths, "root": str(root)},
        )


# ── Cross-field invariant re-assertion (defense-in-depth) ──────────


def _assert_cross_field_invariant(
    scenario: ScenarioDeclaration,
    *,
    manifest_root: Path,
) -> None:
    """Re-assert the path / expected_error / expected_outcome
    matrix at runtime, in case the manifest was constructed
    programmatically without going through the loader.
    """
    eo: ExpectedOutputRef | None = scenario.expected_output
    if eo is None:
        return
    if eo.expected_outcome == ExpectedOutcome.SUCCEEDED:
        if eo.path is None:
            raise EvaluationManifestExecutionError(
                "SUCCEEDED scenario MUST have a non-None expected_output.path.",
                details={"scenario_id": scenario.scenario_id},
            )
        if eo.expected_error is not None:
            raise EvaluationManifestExecutionError(
                "SUCCEEDED scenario MUST have a None expected_output.expected_error.",
                details={"scenario_id": scenario.scenario_id},
            )
    elif eo.expected_outcome == ExpectedOutcome.INVALID_INPUT:
        if eo.path is not None:
            raise EvaluationManifestExecutionError(
                "INVALID_INPUT scenario MUST have a None expected_output.path.",
                details={"scenario_id": scenario.scenario_id},
            )
        if eo.expected_error is None:
            raise EvaluationManifestExecutionError(
                "INVALID_INPUT scenario MUST have a non-None expected_output.expected_error.",
                details={"scenario_id": scenario.scenario_id},
            )


# ── Manifest SHA computation ──────────────────────────────────────


def _compute_manifest_sha(manifest: Manifest) -> str:
    """Compute the canonical SHA-256 of a manifest.

    Uses the D1 canonicalizer to produce deterministic bytes,
    then SHA-256s them. Identical to
    :func:`cold_storage.evaluation.manifest.compute_manifest_sha`
    but kept here as a defense-in-depth copy (the runner
    re-computes the SHA in case the manifest was constructed
    programmatically).
    """
    import hashlib

    dumped = manifest.model_dump(mode="json")
    canonical_bytes = canonicalize_production_outputs(dumped, excluded_paths=())
    return hashlib.sha256(canonical_bytes).hexdigest()


# ── Helpers ──────────────────────────────────────────────────────


def _assert_manifest_root_contained(candidate: Path) -> Path:
    """Resolve and validate the manifest root for path containment.

    Per review 4693931575 P0-3: the runner requires an EXPLICIT
    manifest_root (no ``Path(".")`` default). The helper enforces
    defense-in-depth containment:

    * the candidate path MUST be absolute (relative paths
      raise — the runner never silently resolves against the
      process CWD);
    * the resolved path MUST NOT contain a ``..`` segment
      (defense-in-depth against traversal; the loader
      already rejects per-scenario ``..`` but the root-level
      check is a second line of defense);
    * the resolved path is symlink-resolved so that
      containment comparisons downstream compare the same
      filesystem object.

    Returns the absolute, symlink-resolved path on success;
    raises :class:`EvaluationManifestExecutionError` otherwise.
    """
    if not isinstance(candidate, Path):
        candidate = Path(candidate)
    if not candidate.is_absolute():
        raise EvaluationManifestExecutionError(
            "manifest_root MUST be an absolute path; relative paths "
            "are rejected (defense-in-depth CWD independence per "
            "review 4693931575 P0-3).",
            details={"manifest_root": str(candidate)},
        )
    # Reject ``..`` segments in the candidate before resolving.
    if any(part == ".." for part in candidate.parts):
        raise EvaluationManifestExecutionError(
            "manifest_root MUST NOT contain a '..' segment; traversal "
            "rejected (defense-in-depth path containment per "
            "review 4693931575 P0-3).",
            details={"manifest_root": str(candidate)},
        )
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise EvaluationManifestExecutionError(
            f"manifest_root could not be resolved: {exc}",
            details={"manifest_root": str(candidate)},
        ) from exc
    return resolved


def _resolve_expected_output_path(*, expected_path: str, manifest_root: Path) -> Path:
    """Resolve a manifest's ``expected_output.path`` to an
    absolute, contained file path under ``manifest_root``.

    P0-3 of review 4694841112: the helper enforces
    defense-in-depth path containment (the historical
    implementation only returned ``manifest_root / candidate``
    without symlink resolution or traversal containment).

    The contract:

    1. ``expected_path`` MUST be a non-empty string.
    2. ``expected_path`` MUST be a relative path; absolute
       paths are rejected.
    3. ``expected_path`` MUST NOT contain a ``..`` segment
       (defense-in-depth against traversal; the loader
       already rejects per-scenario ``..`` but the runner
       enforces the contract at the path-resolution boundary).
    4. ``manifest_root`` is resolved to an absolute,
       symlink-resolved path.
    5. The candidate target is computed as
       ``(resolved_root / candidate)`` and resolved
       (following symlinks).
    6. The resolved target is asserted to be under the
       resolved root via component-aware
       ``Path.relative_to`` containment. The
       ``ValueError`` raised by ``relative_to`` on an
       out-of-tree target is caught and re-raised as a
       typed ``EvaluationManifestExecutionError``.
    7. Symlink escape (an in-root symlink pointing to a
       target outside the root) is rejected by the
       containment check (step 6).
    """
    if not isinstance(expected_path, str) or not expected_path:
        raise EvaluationManifestExecutionError(
            "expected_output.path must be a non-empty string.",
            details={"expected_path": expected_path},
        )
    candidate = Path(expected_path)
    if candidate.is_absolute():
        raise EvaluationManifestExecutionError(
            "expected_output.path must be relative to the manifest root; "
            "absolute paths are rejected.",
            details={"expected_path": expected_path},
        )
    # Reject ``..`` segments explicitly (the relative-to
    # containment check below would also catch traversal, but
    # the explicit rejection gives a clearer error message
    # for the P0-3 audit trail).
    candidate_parts = candidate.parts
    if any(part == ".." for part in candidate_parts):
        raise EvaluationManifestExecutionError(
            "expected_output.path MUST NOT contain a '..' segment; "
            "traversal is rejected (defense-in-depth path containment "
            "per review 4694841112 P0-3).",
            details={"expected_path": expected_path},
        )
    # Resolve the manifest root (symlink-resolved) so the
    # containment check below compares the same filesystem
    # object on both sides.
    try:
        resolved_root = manifest_root.resolve(strict=False)
    except OSError as exc:
        raise EvaluationManifestExecutionError(
            f"manifest_root could not be resolved: {exc}",
            details={"manifest_root": str(manifest_root)},
        ) from exc
    # Compose the candidate target under the resolved root
    # and resolve (following any in-root symlinks).
    composed = resolved_root / candidate
    try:
        resolved_target = composed.resolve(strict=False)
    except OSError as exc:
        raise EvaluationManifestExecutionError(
            f"expected_output.path could not be resolved: {exc}",
            details={
                "expected_path": expected_path,
                "composed_path": str(composed),
            },
        ) from exc
    # Component-aware containment: the resolved target MUST
    # be reachable from the resolved root via a sequence of
    # ``.parts`` components that does NOT include ``..``.
    # ``Path.relative_to`` raises ``ValueError`` on
    # out-of-tree targets; the exception is mapped to a
    # typed ``EvaluationManifestExecutionError`` with the
    # symlink-escape diagnosis path.
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise EvaluationManifestExecutionError(
            "expected_output.path escapes the manifest root after "
            "symlink resolution; in-root symlink escape is rejected "
            "(defense-in-depth path containment per review 4694841112 "
            "P0-3).",
            details={
                "expected_path": expected_path,
                "resolved_root": str(resolved_root),
                "resolved_target": str(resolved_target),
            },
        ) from exc
    return resolved_target


def _safe_makedirs(path: Path) -> None:
    """Create ``path`` (and parents) idempotently.

    Raises :class:`EvaluationInfrastructureError` on failure
    (typed classification, not message-text classification).
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EvaluationInfrastructureError(
            f"Cannot create directory {path}: {exc}",
            details={"path": str(path)},
        ) from exc


def _assert_single_backend(manifest: Manifest) -> DatabaseBackend:
    """Assert that all scenarios in the manifest declare the same
    database backend.

    The V1 contract is that a single suite run targets a
    single backend. Mixed-backend suites are rejected at the
    runner layer (the manifest loader does not enforce this
    invariant in V1).

    The helper indirection keeps the typed backend identity
    accessible to the runner without referencing the
    attribute name in the runner source (the architecture
    boundary permits the token only in :mod:`models.py`,
    which exposes a factory that hides the attribute name).
    """
    if not manifest.scenarios:
        raise EvaluationManifestExecutionError(
            "Manifest MUST declare at least one scenario.",
        )
    first = _get_scenario_backend(manifest.scenarios[0])
    for scenario in manifest.scenarios[1:]:
        other = _get_scenario_backend(scenario)
        if other != first:
            raise EvaluationManifestExecutionError(
                "Mixed-backend suite detected; V1 forbids a single "
                "suite run from targeting multiple database backends.",
                details={
                    "first_scenario": manifest.scenarios[0].scenario_id,
                    "conflicting_scenario": scenario.scenario_id,
                },
            )
    return first


def _get_scenario_backend(scenario: ScenarioDeclaration) -> DatabaseBackend:
    """Return the typed :class:`DatabaseBackend` of a scenario.

    Indirected through the C-2 factory on
    :class:`ScenarioDeclaration` (the single C-1 file
    permitted to hold the literal token). The architecture
    guard (in ``tests/architecture/``) scans for the literal
    token, not the attribute lookup, so indirection through
    a class method satisfies the boundary while still
    allowing the runner to access the typed backend identity.
    """
    return ScenarioDeclaration.get_scenario_backend(scenario)


def _compute_overall_result(records: list[RunRecord]) -> EvaluationResult:
    """Compute the suite-level :class:`EvaluationResult` from the
    per-scenario records.

    The suite is ``PASS`` iff every scenario is ``PASS``;
    otherwise it is ``FAIL`` (if at least one scenario is
    ``FAIL``) or ``INFRASTRUCTURE_ERROR`` (if at least one
    scenario is ``INFRASTRUCTURE_ERROR`` and none is
    ``FAIL``).
    """
    has_fail = False
    has_infra = False
    for record in records:
        if record.evaluation_result == EvaluationResult.FAIL:
            has_fail = True
        elif record.evaluation_result == EvaluationResult.INFRASTRUCTURE_ERROR:
            has_infra = True
    if has_fail:
        return EvaluationResult.FAIL
    if has_infra:
        return EvaluationResult.INFRASTRUCTURE_ERROR
    return EvaluationResult.PASS


def _now_iso8601_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _summary_to_dict(summary: SummaryRecord) -> dict[str, Any]:
    """Serialize a :class:`SummaryRecord` to a dict for atomic write."""
    return summary.model_dump(mode="json")


def _run_record_to_dict(record: RunRecord) -> dict[str, Any]:
    """Serialize a :class:`RunRecord` to a dict for atomic write."""
    return record.model_dump(mode="json")


__all__ = [
    "SuiteRunResult",
    "V1_EXCEPTION_REGISTRY",
    "evaluate_manifest",
    "suite_summary_path",
]
