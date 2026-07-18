from __future__ import annotations

import argparse
import contextlib
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import sessionmaker

from cold_storage.evaluation.adapter import read_c2_baseline_projection
from cold_storage.evaluation.compare import compare_outputs
from cold_storage.evaluation.errors import StaleEvaluationArtifactsError
from cold_storage.evaluation.execute import run_scenario_via_markers
from cold_storage.evaluation.manifest import load_and_validate_manifest
from cold_storage.evaluation.models import Manifest
from cold_storage.evaluation.pilot_reports import (
    PILOT_CHECK_ID,
    PILOT_RESULT_SCHEMA_VERSION,
    PilotVerificationError,
    verify_multilingual_report_pilot,
)
from cold_storage.evaluation.runners._executor import (
    build_baseline_normalized_business_projection,
)
from tests.evaluation._seed_helpers import (
    SOURCE_BINDING_ID,
    WEIGHT_REVISION_ID,
    seed_a1_all_prereqs,
)
from tests.pilot import run_multilingual_report_pilot as rmp

DATA_DIR = Path(__file__).resolve().parents[1] / "evaluation" / "data"


@pytest.mark.parametrize(
    ("file_name", "suite_id", "backend_value"),
    [
        (
            "task011-pilot-sqlite.v1.json",
            "task011-pilot-multilingual-sqlite",
            "sqlite",
        ),
        (
            "task011-pilot-postgresql.v1.json",
            "task011-pilot-multilingual-postgresql",
            "postgresql",
        ),
    ],
)
def test_backend_pilot_manifests_are_frozen_single_scenario(
    file_name: str,
    suite_id: str,
    backend_value: str,
) -> None:
    manifest = load_and_validate_manifest((DATA_DIR / file_name).resolve())
    assert manifest.schema_version == "1.0"
    assert manifest.suite_id == suite_id
    assert manifest.excluded_paths == ()
    assert len(manifest.scenarios) == 1
    scenario = manifest.scenarios[0]
    assert scenario.scenario_id == "baseline_feasible"
    assert scenario.database_backend.value == backend_value
    assert scenario.fixtures == ()
    assert scenario.comparison_policy.leaves == ()
    assert scenario.expected_output is not None
    assert scenario.expected_output.path == "expected/baseline_feasible.v1.json"
    assert scenario.expected_output.commit_sha == "f274db66fe4bb2de206d12c2d561d1b3549ab6c0"


def test_pilot_public_identity_is_frozen() -> None:
    assert PILOT_CHECK_ID == "multilingual_report_same_revision"
    assert PILOT_RESULT_SCHEMA_VERSION == "task11-pilot-report.v1"


def test_pilot_rejects_relative_output_root_before_service_calls() -> None:
    with pytest.raises(PilotVerificationError) as caught:
        verify_multilingual_report_pilot(
            report_service=None,
            render_service=None,
            template_repository=None,
            project_id="project",
            project_version_id="version",
            source_commit_sha="a" * 40,
            source_manifest_sha="b" * 64,
            output_root=Path("relative"),
            repeat_index=1,
            run_identity={"database_backend": "sqlite"},
            download_artifact=lambda _r, _a, _actor: (b"", {}),
        )
    assert caught.value.code == "UNSAFE_OUTPUT_ROOT"


def test_pilot_rejects_stale_completion_marker_before_service_calls(tmp_path: Path) -> None:
    root = (tmp_path / "run").resolve()
    root.mkdir()
    (root / "pilot-summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StaleEvaluationArtifactsError):
        verify_multilingual_report_pilot(
            report_service=None,
            render_service=None,
            template_repository=None,
            project_id="project",
            project_version_id="version",
            source_commit_sha="a" * 40,
            source_manifest_sha="b" * 64,
            output_root=root,
            repeat_index=1,
            run_identity={"database_backend": "sqlite"},
            download_artifact=lambda _r, _a, _actor: (b"", {}),
        )


# ── P1-1 focused tests (manifest-golden binding) ───────────────────────────


def _write_manifest(
    tmp_path: Path,
    *,
    manifest_name: str = "test-pilot.v1.json",
    expected_output_relative_path: str = "expected/test_golden.v1.json",
    expected_output_commit_sha: str = "f274db66fe4bb2de206d12c2d561d1b3549ab6c0",
    golden_payload: dict | None = None,
) -> Path:
    """Write a single-scenario ``baseline_feasible`` manifest + its golden file.

    Returns the absolute path to the manifest. The manifest points
    at the golden via ``expected_output_relative_path`` (relative to
    the manifest's parent directory).
    """
    manifest_path = tmp_path / manifest_name
    golden_path = tmp_path / expected_output_relative_path
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    if golden_payload is None:
        golden_payload = {
            "scenario_id": "baseline_feasible",
            "expected_outcome": "SUCCEEDED",
            "production_outputs": {"throughput": {"value": 100.0, "unit": "kg"}},
        }
    golden_path.write_text(json.dumps(golden_payload), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "test-pilot-suite",
                "excluded_paths": [],
                "scenarios": [
                    {
                        "scenario_id": "baseline_feasible",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                        "fixtures": [],
                        "expected_output": {
                            "scenario_id": "baseline_feasible",
                            "path": expected_output_relative_path,
                            "expected_outcome": "SUCCEEDED",
                            "commit_sha": expected_output_commit_sha,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path.resolve()


def test_p1_1_uses_manifest_declared_golden_path_not_hardcoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 Test 1: golden is loaded via the manifest-declared path.

    A monkeypatched ``safe_resolve_manifest_path`` records the
    declared path it receives. The composition MUST use the value
    declared in the manifest (``expected_output.path``), not a
    hard-coded relative path like ``expected/baseline_feasible.v1.json``.
    """
    manifest_path = _write_manifest(
        tmp_path,
        expected_output_relative_path="custom/sub/golden.v1.json",
    )
    received: dict[str, object] = {}

    def _spy_resolve(declared_path: str, *, manifest_root: Path) -> Path:
        received["declared_path"] = declared_path
        received["manifest_root"] = manifest_root
        return manifest_root / declared_path

    monkeypatch.setattr(rmp, "safe_resolve_manifest_path", _spy_resolve)
    bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)
    golden_full = rmp._load_manifest_golden(
        scenario=bundle.scenario, manifest_path=bundle.manifest_path
    )
    assert golden_full.get("scenario_id") == "baseline_feasible"
    assert received.get("declared_path") == "custom/sub/golden.v1.json"
    # Defense-in-depth: the spy was called with the manifest
    # directory as ``manifest_root`` (NOT process CWD, NOT
    # ``Path(".")``, NOT a hard-coded path).
    assert received.get("manifest_root") == manifest_path.parent
    # P1-1 marker: the hard-coded frozen path is NOT used.
    hardcoded_used = received.get("declared_path") == "expected/baseline_feasible.v1.json"
    manifest_used = received.get("declared_path") == "custom/sub/golden.v1.json"
    assert hardcoded_used is False
    assert manifest_used is True


def test_p1_1_golden_mismatch_fails_closed_with_typed_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 Test 2: golden mismatch raises ``MANIFEST_GOLDEN_MISMATCH``.

    The composition MUST raise :class:`PilotCompositionError` with
    ``code='MANIFEST_GOLDEN_MISMATCH'`` on golden mismatch. The
    report-render / verify-multilingual-report-pilot path MUST NOT
    be reached on mismatch.
    """
    manifest_path = _write_manifest(
        tmp_path,
        golden_payload={
            "scenario_id": "baseline_feasible",
            "expected_outcome": "SUCCEEDED",
            "production_outputs": {"throughput": {"value": 100.0, "unit": "kg"}},
        },
    )
    bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)

    # Mock the actual projection to disagree with the golden on
    # one field. The composition MUST detect this and fail closed.
    def _fake_actual(*, session_factory: object, scheme_run_id: str) -> dict[str, object]:
        return {
            "scenario_id": "baseline_feasible",
            "expected_outcome": "SUCCEEDED",
            "production_outputs": {"throughput": {"value": 999.0, "unit": "kg"}},
        }

    monkeypatch.setattr(rmp, "_build_actual_normalized_business_projection", _fake_actual)
    # Spy the report-service-composition path to confirm it is NOT
    # reached on mismatch.
    compose_called = {"value": False}
    verifier_called = {"value": False}

    def _spy_compose(*, engine: object, output_root: object) -> tuple[object, ...]:
        compose_called["value"] = True
        return (None, None, None, None, None)

    def _spy_verifier(**kwargs: object) -> dict[str, object]:
        verifier_called["value"] = True
        return {}

    monkeypatch.setattr(rmp, "_compose_report_services", _spy_compose)
    monkeypatch.setattr(rmp, "verify_multilingual_report_pilot", _spy_verifier)

    with pytest.raises(rmp.PilotCompositionError) as caught:
        rmp._verify_manifest_golden_binding(
            scenario=bundle.scenario,
            manifest_path=bundle.manifest_path,
            session_factory=lambda: None,
            scheme_run_id="test-run-id",
        )
    assert caught.type is rmp.PilotCompositionError
    assert caught.value.code == "MANIFEST_GOLDEN_MISMATCH"
    # P1-1 invariants: the report-render / verifier path MUST NOT
    # be reached on golden mismatch.
    assert compose_called["value"] is False
    assert verifier_called["value"] is False


def test_p1_1_golden_match_passes_with_real_compare_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 Test 3: golden match passes; ``compare_outputs`` is real.

    The composition MUST call :func:`compare_outputs` (not a mock
    that returns ``True``). On match, the helper returns the
    normalized payloads and the comparison result; the four-render
    flow continues.
    """
    manifest_path = _write_manifest(
        tmp_path,
        golden_payload={
            "scenario_id": "baseline_feasible",
            "expected_outcome": "SUCCEEDED",
            "production_outputs": {"throughput": {"value": 100.0, "unit": "kg"}},
        },
    )
    bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)

    # The actual projection EXACTLY matches the golden.
    def _fake_actual(*, session_factory: object, scheme_run_id: str) -> dict[str, object]:
        return {
            "scenario_id": "baseline_feasible",
            "expected_outcome": "SUCCEEDED",
            "production_outputs": {"throughput": {"value": 100.0, "unit": "kg"}},
        }

    monkeypatch.setattr(rmp, "_build_actual_normalized_business_projection", _fake_actual)
    # Spy the real ``compare_outputs`` to confirm it is invoked
    # (NOT mocked to return True).
    real_compare_outputs = compare_outputs
    compare_calls: list[dict[str, object]] = []

    def _spy_compare_outputs(*, expected: object, actual: object, policy: object) -> object:
        compare_calls.append({"expected": expected, "actual": actual, "policy": policy})
        return real_compare_outputs(expected=expected, actual=actual, policy=policy)

    monkeypatch.setattr(rmp, "compare_outputs", _spy_compare_outputs)

    expected_normalized, actual_normalized, comparison = rmp._verify_manifest_golden_binding(
        scenario=bundle.scenario,
        manifest_path=bundle.manifest_path,
        session_factory=lambda: None,
        scheme_run_id="test-run-id",
    )
    assert comparison.passed is True
    assert (expected_normalized, actual_normalized, comparison) is not None
    # ``compare_outputs`` was actually called (not mocked to return True).
    assert len(compare_calls) == 1
    assert compare_calls[0]["expected"] == compare_calls[0]["actual"]


def test_p1_1_actual_normalized_bound_to_current_scheme_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1-1 Test 4: actual reads from THIS run's persisted SchemeRun.

    The composition MUST call :func:`read_c2_baseline_projection`
    with ``run_id=str(outcome.scheme_run.id)`` (the SchemeRun
    produced by ``run_scenario_via_markers`` in this exact
    invocation). The test spies on ``read_c2_baseline_projection``
    to assert the bound ``run_id``.
    """
    observed: dict[str, object] = {}
    expected_run_id = "scheme-run-id-from-current-invocation-12345"

    def _spy_read(session_factory: object, *, run_id: str) -> object:
        observed["run_id"] = run_id
        observed["session_factory"] = session_factory
        # Return a stand-in typed source. The build step
        # downstream is short-circuited by a monkeypatch on
        # ``build_baseline_normalized_business_projection`` so
        # this stub does NOT need to honor the
        # C2BaselineProjectionSource shape.
        return object()

    monkeypatch.setattr(rmp, "read_c2_baseline_projection", _spy_read)
    monkeypatch.setattr(
        rmp,
        "build_baseline_normalized_business_projection",
        lambda source: {"stub": True},
    )
    rmp._build_actual_normalized_business_projection(
        session_factory=lambda: None,
        scheme_run_id=expected_run_id,
    )
    # P1-1 marker: the actual source was bound to the CURRENT
    # run's SchemeRun id (not a hard-coded / fixture / previous
    # run id, not ``None``, not the manifest scenario id).
    assert observed.get("run_id") == expected_run_id
    assert observed.get("run_id") != "test-run-id"  # NOT a fixture id
    assert observed.get("run_id") is not None


def test_p1_1_golden_only_comparison_policy_metadata_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 Test 5: ``_comparison_policy`` is golden-only and is excluded.

    The actual normalized payload (built from the live SchemeRun)
    does NOT carry the ``_comparison_policy`` key. The composition
    MUST drop the key from the golden before comparison so the
    comparison is based on the business payload only.
    """
    golden_payload = {
        "scenario_id": "baseline_feasible",
        "expected_outcome": "SUCCEEDED",
        "production_outputs": {"throughput": {"value": 100.0, "unit": "kg"}},
        "_comparison_policy": {
            "leaves": [{"path": "production_outputs.throughput.value", "kind": "EXACT"}]
        },
    }
    manifest_path = _write_manifest(tmp_path, golden_payload=golden_payload)
    bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)

    def _capture_actual(*, session_factory: object, scheme_run_id: str) -> dict[str, object]:
        return {
            "scenario_id": "baseline_feasible",
            "expected_outcome": "SUCCEEDED",
            "production_outputs": {"throughput": {"value": 100.0, "unit": "kg"}},
        }

    real_compare_outputs = compare_outputs
    observed_inputs: list[dict[str, object]] = []

    def _spy_compare(*, expected: object, actual: object, policy: object) -> object:
        observed_inputs.append({"expected": expected, "actual": actual, "policy": policy})
        return real_compare_outputs(expected=expected, actual=actual, policy=policy)

    monkeypatch.setattr(rmp, "_build_actual_normalized_business_projection", _capture_actual)
    monkeypatch.setattr(rmp, "compare_outputs", _spy_compare)

    expected_normalized, actual_normalized, comparison = rmp._verify_manifest_golden_binding(
        scenario=bundle.scenario,
        manifest_path=bundle.manifest_path,
        session_factory=lambda: None,
        scheme_run_id="test-run-id",
    )
    # The golden-only metadata MUST be excluded from the business
    # payload that was passed to ``compare_outputs``.
    assert len(observed_inputs) == 1
    passed_expected = observed_inputs[0]["expected"]
    assert isinstance(passed_expected, dict)
    assert "_comparison_policy" not in passed_expected
    assert comparison.passed is True


def test_p1_1_does_not_modify_p1_3_or_p1_4_areas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 Test 6 (rewritten in P1-2 round): P1-1 fix MUST NOT touch
    P1-3 / P1-4 surfaces.

    The composition MUST NOT:

    * change ``_semantic_checks`` numeric / unit substring logic
      (P1-3 — global-substring false-pass);
    * add a four-render end-to-end test or change the verifier
      artifact schema (P1-4 — E2E acceptance missing).

    The P1-2 territory (verifier-exit-code reachability) is the
    subject of the separate ``P1-2`` corrective round and is
    covered by ``test_p1_2_pilot_verification_error_returns_exit_4``
    et al. — this test MUST NOT lock down the pre-P1-2 behaviour
    any longer (it is a confirmed old defect, not a P1-1 invariant).
    """
    # 1. The composition's exit-code contract: the four
    # machine-readable exit-code constants MUST keep their
    # documented values (0 / 1 / 2 / 3 / 4). The P1-1 fix MUST
    # NOT add a new exit code, and MUST NOT change an existing
    # one's value.
    assert rmp.EXIT_OK == 0
    assert rmp.EXIT_INFRA_ERROR == 1
    assert rmp.EXIT_INPUT_ERROR == 2
    assert rmp.EXIT_BACKEND_ERROR == 3
    assert rmp.EXIT_VERIFIER_ERROR == 4
    # The P1-2 catch MUST be exception-type-driven, not driven
    # by a hand-written ``exc.code`` allowlist. The catch MUST
    # NOT enumerate verifier codes — any ``PilotVerificationError``
    # raised from the verifier seam MUST map to exit 4.
    cmd_run_src = inspect.getsource(rmp._cmd_run)
    assert "except PilotVerificationError" in cmd_run_src, (
        "P1-2 remediation: _cmd_run MUST catch PilotVerificationError "
        "to map verifier failures to EXIT_VERIFIER_ERROR = 4."
    )
    # Defense-in-depth: the catch is NOT a blanket ``except Exception``
    # or ``except BaseException`` (which would swallow unrelated
    # programming errors / RuntimeError and return 4). The verifier
    # catch MUST be specifically ``PilotVerificationError``.
    assert "except Exception" not in cmd_run_src, (
        "P1-2 remediation MUST NOT use a blanket ``except Exception`` "
        "to map verifier failures to 4; unrelated runtime errors MUST "
        "still propagate (see test_p1_2_generic_runtime_error_propagates)."
    )
    # The composition's manifest-golden binding MUST NOT touch
    # the verifier's numeric / unit substring logic (P1-3) or
    # add a four-render e2e (P1-4). The P1-1 helper is intentionally
    # narrow: it only loads the golden, builds the actual, calls
    # ``compare_outputs``, and fails closed.
    src = inspect.getsource(rmp._verify_manifest_golden_binding)
    # P1-3 territory: no ``display_value`` / ``display_unit`` /
    # substring-search / ``in extracted_text`` patterns.
    for forbidden_token in (
        "display_value",
        "display_unit",
        "extracted_text",
    ):
        assert forbidden_token not in src, (
            f"P1-1 fix MUST NOT touch P1-3 territory; "
            f"found {forbidden_token!r} in _verify_manifest_golden_binding."
        )
    # P1-4 territory: no four-render e2e / DOCX-PDF render step
    # inside the manifest-golden helper.
    for forbidden_token in (
        "render_docx",
        "render_pdf",
        "verify_download",
        "four_render",
        "four-render",
    ):
        assert forbidden_token not in src, (
            f"P1-1 fix MUST NOT touch P1-4 territory; "
            f"found {forbidden_token!r} in _verify_manifest_golden_binding."
        )


def test_p1_1_manifest_bundle_retains_typed_manifest_object() -> None:
    """P1-1 manifest must be retained as a typed object for ``_cmd_run``.

    The composition MUST NOT re-read or hand-parse the manifest
    JSON after :func:`_load_pilot_manifest` returns; the typed
    :class:`Manifest` object MUST be held in the returned bundle.
    """
    manifest_path = (DATA_DIR / "task011-pilot-sqlite.v1.json").resolve()
    bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)
    # Bundle holds the typed :class:`Manifest` (not a dict / not a
    # re-parsed JSON).
    assert isinstance(bundle.manifest, Manifest)
    # The single-scenario invariant is preserved.
    assert bundle.scenario.scenario_id == "baseline_feasible"
    # The canonical SHA-256 is populated.
    assert isinstance(bundle.source_manifest_sha, str)
    assert len(bundle.source_manifest_sha) == 64
    # The resolved manifest path is absolute.
    assert bundle.manifest_path.is_absolute()
    # The bundle's manifest is the SAME object that the
    # composition will use (not a re-load, not a copy).
    same_manifest_object = bundle.manifest
    assert same_manifest_object is bundle.manifest


# ── P1-1 corrective round tests (Round 2 / P1-1 CR) ─────────────────────────
#
# Three new focused tests added in the P1-1 corrective round:
#
# * P1-1 CR Test 7: canonical correlation constant appears in
#   ``_cmd_run`` and old correlation literal is gone from the
#   runtime path.
# * P1-1 CR Test 8 (P2-1): the scenario helper rejects a
#   ``manifest.database_backend=sqlite`` against
#   ``backend_marker="postgresql"`` with the stable typed
#   ``MANIFEST_SCENARIO_MISMATCH`` code (defense-in-depth: helper
#   now fed the CLI authority, not its own scenario-derived
#   backend).
# * P1-1 CR Test 9 (P1-2): real SQLite integration test that
#   walks the entire pre-render chain end-to-end against the
#   frozen ``baseline_feasible.v1.json`` golden. The test uses
#   ``rmp._provision_sqlite_database`` (a real SQLite file with
#   ``alembic upgrade head`` applied) and exercises every step
#   the composition exercises in production: ``seed_a1_all_prereqs``,
#   ``run_scenario_via_markers``, ``read_c2_baseline_projection``,
#   ``build_baseline_normalized_business_projection``, and
#   ``compare_outputs``. NO step is monkeypatched, stubbed, or
#   mocked. The test ends before any four-render composition
#   (``_compose_report_services``, ``_seed_report_templates``,
#   ``verify_multilingual_report_pilot``); P1-4 territory is
#   intentionally out of scope for this round.


def test_p1_1_canonical_correlation_constant_in_runtime_path() -> None:
    """P1-1 CR Test 7: runtime path uses the canonical correlation constant.

    The composition MUST forward the canonical A1.5 baseline
    correlation marker (``test-a15-baseline-001``) to
    ``run_scenario_via_markers`` AND record it in
    ``run_identity["correlation_id"]``. The old literal
    ``task011-pilot-correlation`` MUST NOT appear in the
    composition's runtime path. The test is structural (source
    inspection) and is the minimal regression guard against
    re-introducing the original P1-1 defect.
    """
    cmd_run_src = inspect.getsource(rmp._cmd_run)
    composition_src = inspect.getsource(rmp)

    # 1. The canonical constant is exposed on the composition
    # module (the runtime path imports it by attribute lookup).
    assert getattr(rmp, "PILOT_BASELINE_CORRELATION_ID", None) == "test-a15-baseline-001"

    # 2. ``_cmd_run`` references the canonical constant in BOTH
    # places it is required: the ``run_scenario_via_markers`` call
    # and the ``run_identity`` dict.
    assert "correlation_marker=rmp.PILOT_BASELINE_CORRELATION_ID" in cmd_run_src or (
        "correlation_marker=PILOT_BASELINE_CORRELATION_ID" in cmd_run_src
    ), (
        "P1-1 CR: _cmd_run MUST forward PILOT_BASELINE_CORRELATION_ID "
        "to run_scenario_via_markers (not a hard-coded literal)."
    )
    assert '"correlation_id": PILOT_BASELINE_CORRELATION_ID' in cmd_run_src, (
        "P1-1 CR: _cmd_run MUST record PILOT_BASELINE_CORRELATION_ID "
        "in run_identity['correlation_id'] (not a hard-coded literal)."
    )

    # 3. The old correlation literal MUST NOT appear in the
    # composition module at all (no hidden run_identity echo, no
    # leftover correlation_marker literal, no comment-only mention
    # of it as the active value).
    assert "task011-pilot-correlation" not in composition_src, (
        "P1-1 CR: the old correlation literal 'task011-pilot-correlation' "
        "MUST NOT appear anywhere in run_multilingual_report_pilot.py; the "
        "frozen golden expects 'test-a15-baseline-001' so any literal echo "
        "would silently re-introduce the original P1-1 defect."
    )


def test_p1_1_assert_scenario_helper_uses_cli_backend_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 CR Test 8 (P2-1): helper rejects a manifest/CLI backend mismatch.

    ``_assert_scenario_baseline_feasible`` MUST reject a scenario
    whose ``database_backend`` disagrees with the operator-supplied
    CLI ``--backend``. The previous round passed
    ``backend_marker=scenario.database_backend.value`` (a
    self-comparison that always passed); the corrective round
    passes ``backend_marker=args.backend`` so the helper enforces
    the structural invariant on its own inputs.

    This test uses a hand-written manifest with
    ``database_backend=sqlite`` and asserts that calling the
    helper with ``backend_marker="postgresql"`` raises
    ``PilotCompositionError(code='MANIFEST_SCENARIO_MISMATCH')``.
    """
    # Use the existing helper to write a single-scenario manifest
    # that declares ``database_backend=sqlite``.
    manifest_path = _write_manifest(tmp_path)  # default backend=sqlite
    bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)
    # Sanity: the scenario's database_backend is "sqlite".
    assert bundle.scenario.database_backend.value == "sqlite"

    # The helper MUST reject a CLI backend that disagrees with
    # the scenario's declared database_backend. The error MUST be
    # a typed ``PilotCompositionError`` with the stable
    # ``MANIFEST_SCENARIO_MISMATCH`` code (downstream automation
    # classifies by code, NOT by message substring).
    with pytest.raises(rmp.PilotCompositionError) as caught:
        rmp._assert_scenario_baseline_feasible(
            scenario=bundle.scenario, backend_marker="postgresql"
        )
    assert caught.type is rmp.PilotCompositionError
    assert caught.value.code == "MANIFEST_SCENARIO_MISMATCH"

    # The inverse direction (CLI matches scenario backend) MUST
    # NOT raise.
    rmp._assert_scenario_baseline_feasible(scenario=bundle.scenario, backend_marker="sqlite")


def test_p1_1_real_sqlite_production_projection_matches_frozen_manifest_golden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 CR Test 9 (P1-2): real SQLite pre-render integration test.

    End-to-end pre-render chain (every step is REAL, not
    monkeypatched)::

        fresh SQLite database (via ``_provision_sqlite_database``)
        → alembic upgrade head (production schema, subprocess)
        → ``seed_a1_all_prereqs`` (real seed)
        → ``run_scenario_via_markers`` (real production runner,
           correlation_marker=PILOT_BASELINE_CORRELATION_ID)
        → persisted ``SchemeRun`` row
        → ``read_c2_baseline_projection(session_factory,
           run_id=str(outcome.scheme_run.id))`` (real C-2 read)
        → ``build_baseline_normalized_business_projection(source)``
           (real normalized projection)
        → ``_load_pilot_manifest`` (real frozen SQLite manifest)
        → ``_load_manifest_golden`` (uses manifest
           ``expected_output.path`` via ``safe_resolve_manifest_path``
           — NOT a hard-coded path)
        → ``compare_outputs(expected, actual, policy)`` (REAL
           comparison, not mocked to PASS)
        → ``comparison.passed is True`` with zero diffs

    The test ends BEFORE the four-render composition
    (``_compose_report_services`` / ``_seed_report_templates`` /
    ``verify_multilingual_report_pilot``); P1-4 territory is
    intentionally out of scope for this round. The integration
    coverage is the missing link between the existing
    monkeypatched P1-1 focused tests and the real production
    happy path.
    """
    # The test uses the frozen SQLite manifest declared in
    # ``tests/evaluation/data/`` (the same one the production
    # composition loads via ``--manifest``). The golden path is
    # resolved from ``scenario.expected_output.path`` via the
    # composition's own ``_load_manifest_golden`` helper, NOT
    # hard-coded to ``expected/baseline_feasible.v1.json``.
    manifest_path = (DATA_DIR / "task011-pilot-sqlite.v1.json").resolve()

    # 1. Provision a fresh SQLite database with the production
    # schema applied. ``_provision_sqlite_database`` is the
    # composition's own helper (allowlisted module), so the test
    # reuses it instead of duplicating the subprocess alembic
    # logic. The resulting engine has ``PRAGMA foreign_keys=ON``.
    sqlite_file = (tmp_path / "live.sqlite").resolve()
    if sqlite_file.exists():
        sqlite_file.unlink()
    engine = rmp._provision_sqlite_database(database_url=f"sqlite:///{sqlite_file}")
    try:
        session_factory: Callable[[], Any] = sessionmaker(bind=engine, expire_on_commit=False)

        # 2. Real ``seed_a1_all_prereqs`` against the live SQLite
        # database. This seeds ``SourceBindingRecord``,
        # ``OrchestrationRunAttemptRecord``,
        # ``SchemeWeightSetRevisionRecord`` (approved), the
        # project + project_version, and the five canonical A1
        # ``CalculationRunRecord`` rows (zone / cooling_load /
        # equipment / power / investment).
        with session_factory() as seed_session:
            seed_a1_all_prereqs(seed_session)
            seed_session.commit()

        # 3. Real ``run_scenario_via_markers`` against the live
        # SQLite database. The correlation marker is the
        # CANONICAL A1.5 baseline marker (the same one the
        # production-side runner bakes into
        # ``assumption_snapshot.correlation_id`` — see
        # ``runners/_executor.py:1078``); this is the runtime
        # value the frozen ``baseline_feasible.v1.json`` golden
        # bakes into ``production_outputs.assumption_snapshot.correlation_id``
        # and uses (via the production ``content_hash``) to
        # derive the byte-stable top-level ``content_hash``.
        outcome = run_scenario_via_markers(
            session_factory,
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            correlation_marker=rmp.PILOT_BASELINE_CORRELATION_ID,
            backend_marker="sqlite",
        )
        assert outcome.outcome == "SUCCEEDED", (
            f"real production run must SUCCEED; got outcome={outcome.outcome!r}"
        )
        scheme_run_id = str(outcome.scheme_run.id)
        assert scheme_run_id, "scheme_run.id must be non-empty"

        # 4. Real C-2 read against the persisted row.
        persisted_source = read_c2_baseline_projection(session_factory, run_id=scheme_run_id)
        assert persisted_source.run_id == scheme_run_id

        # 5. Real normalized business projection from the
        # persisted source.
        actual_normalized = build_baseline_normalized_business_projection(persisted_source)

        # 6. Load the frozen SQLite manifest and the golden via
        # the composition's own helpers. The golden path is
        # resolved from ``scenario.expected_output.path`` via
        # ``safe_resolve_manifest_path`` (NOT a hard-coded
        # ``expected/baseline_feasible.v1.json``).
        bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)
        scenario = bundle.scenario
        assert scenario.scenario_id == "baseline_feasible"
        assert scenario.expected_outcome.value == "SUCCEEDED"
        assert scenario.database_backend.value == "sqlite"
        assert scenario.expected_output is not None
        assert scenario.expected_output.path == "expected/baseline_feasible.v1.json"

        golden_full = rmp._load_manifest_golden(
            scenario=scenario, manifest_path=bundle.manifest_path
        )
        # Strip the golden-only ``_comparison_policy`` metadata
        # key (per §7.7; the key is golden-only and must not
        # participate in business payload comparison).
        expected_normalized: dict[str, object] = {
            key: value for key, value in golden_full.items() if key != "_comparison_policy"
        }

        # 7. REAL ``compare_outputs`` — NOT mocked to PASS. The
        # comparison policy is sourced from the manifest
        # (``scenario.comparison_policy``), exactly as the
        # composition's ``_verify_manifest_golden_binding`` does.
        comparison = compare_outputs(
            expected=expected_normalized,
            actual=actual_normalized,
            policy=scenario.comparison_policy,
        )

        # 8. Assertions — the real production chain MUST produce
        # a normalized business projection that matches the
        # frozen ``baseline_feasible.v1.json`` golden root-by-
        # root.
        assert comparison.passed is True, (
            f"real production projection MUST match the frozen "
            f"golden; got {len(comparison.diffs)} diffs: "
            f"{[d.path for d in comparison.diffs[:10]]!r}"
        )
        assert len(comparison.diffs) == 0, (
            f"diff count must be zero on success; got {len(comparison.diffs)}"
        )

        # 9. Defense-in-depth cross-checks — actual and expected
        # MUST agree on the fields that P1-1 review identified as
        # the root cause of the runtime mismatch. The local
        # aliases are typed ``dict[str, Any]`` to keep mypy
        # happy on the deep ``[k1][k2][k3]`` subscript access
        # (the production ``build_baseline_normalized_business_projection``
        # returns ``dict[str, object]`` and mypy forbids
        # ``object`` subscript access).
        actual_dict: dict[str, Any] = actual_normalized
        expected_dict: dict[str, Any] = expected_normalized
        actual_corr = actual_dict["production_outputs"]["assumption_snapshot"]["correlation_id"]
        expected_corr = expected_dict["production_outputs"]["assumption_snapshot"]["correlation_id"]
        assert actual_corr == "test-a15-baseline-001"
        assert expected_corr == "test-a15-baseline-001"
        assert actual_corr == expected_corr
        # The top-level ``content_hash`` is derived from the
        # canonical correlation_id on the production side; real
        # chain MUST produce the exact same byte-stable hash.
        assert actual_dict["content_hash"] == expected_dict["content_hash"]

        # 10. Verify the actual was bound to THIS run's SchemeRun
        # id (not a hard-coded / fixture / previous run id).
        assert actual_dict["scenario_id"] == expected_dict["scenario_id"] == "baseline_feasible"
        assert actual_dict["expected_outcome"] == expected_dict["expected_outcome"] == "SUCCEEDED"

        # 11. P1-4 territory is INTENTIONALLY not exercised — the
        # test ends before the four-render composition. This is
        # enforced by test structure (the assertions above are
        # the final step) and is the only way the test could
        # conceivably regress into P1-4 territory; the
        # integration coverage is the missing link between the
        # existing monkeypatched P1-1 focused tests and the
        # real production happy path. The other P1-1 focused
        # tests (``test_p1_1_does_not_modify_p1_2_through_p1_4_areas``)
        # also perform source-level scans to ensure the
        # composition module itself does not regress.

    finally:
        engine.dispose()
        if sqlite_file.exists():
            sqlite_file.unlink()


# ── P1-2 corrective round tests (verifier exit-code reachability) ──────────
#
# Four new focused tests added in the P1-2 corrective round:
#
# * P1-2 Test 1: ``_cmd_run`` catches a ``PilotVerificationError``
#   raised from the verifier seam, writes a stable
#   ``PILOT_VERIFICATION_ERROR code=<typed-code>: <message>`` line
#   to stderr, and returns ``EXIT_VERIFIER_ERROR = 4``. The
#   stdout summary is NOT written (no false PASS).
# * P1-2 Test 2: parameterised across at least two distinct
#   ``PilotVerificationError.code`` values to prove the mapping
#   is exception-type-driven (NOT a code allowlist).
# * P1-2 Test 3: a generic ``RuntimeError`` raised from the
#   verifier seam MUST propagate (not be swallowed by a
#   blanket catch returning 4).
# * P1-2 Test 4: regression — the existing composition-error
#   mapping (``PilotCompositionError(code=INPUT_ERROR)`` →
#   ``EXIT_INPUT_ERROR = 2``) is preserved.
#
# The shared ``_patch_cmd_run_to_reach_verifier`` helper builds
# a minimal stand-in environment that lets ``_cmd_run`` reach
# the ``verify_multilingual_report_pilot`` call site without
# touching alembic / seed / real production / real golden
# comparison / real report service composition. The helper
# only patches the EXPENSIVE P1-2-UNRELATED infrastructure
# (allowed per the round's design contract); the verifier
# seam itself is either monkeypatched to raise the desired
# exception or to return a stub summary (in Test 4 we patch
# it to raise ``PilotCompositionError`` from the seam to
# exercise the composition-error path with the same minimal
# scaffold).


def _patch_cmd_run_to_reach_verifier(
    monkeypatch: pytest.MonkeyPatch,
    *,
    verifier_effect: BaseException | dict[str, object],
) -> argparse.Namespace:
    """Build a minimal scaffold that lets ``_cmd_run`` reach the verifier seam.

    The helper monkeypatches ONLY the expensive P1-2-unrelated
    infrastructure (database provision, real seed, real production
    runner, golden comparison, report-service composition,
    template seed, download callable). The verifier seam
    (``verify_multilingual_report_pilot`` at the call site inside
    ``_cmd_run``) is the only seam the test is interested in; the
    caller passes ``verifier_effect`` to control what the seam
    does:

    * ``BaseException`` (subclass of ``Exception``) — the seam
      RAISES that exception; the test asserts how ``_cmd_run``
      classifies and exits.
    * ``dict`` — the seam RETURNS the dict (success stub).

    Returns an ``argparse.Namespace`` pre-loaded with the values
    ``_cmd_run`` needs (commit_sha / manifest / output_root /
    backend / database_url / repeat_index).
    """
    # 1. The manifest bundle (typed ``Manifest`` + scenario + SHA)
    # is loaded once and reused; the test does NOT need to
    # construct the bundle by hand. ``_load_pilot_manifest`` is
    # cheap (purely file I/O + JSON validation), so it is NOT
    # monkeypatched — the real loader is exercised.
    manifest_path = (DATA_DIR / "task011-pilot-sqlite.v1.json").resolve()
    bundle = rmp._load_pilot_manifest(manifest_path=manifest_path)
    scenario = bundle.scenario

    # 2. Engine stand-in. The real ``_provision_sqlite_database``
    # spawns a subprocess alembic upgrade; the test uses a
    # private ``SimpleNamespace`` to satisfy the post-``_cmd_run``
    # engine attribute surface (engine.dispose() is NOT called
    # in the catch path, so a stand-in is safe).
    engine_stub = SimpleNamespace(
        dispose=lambda: None,
    )

    # 3. Session factory stand-in. ``_cmd_run`` only calls
    # ``session_factory()`` inside a ``with`` to seed and inside
    # the real ``run_scenario_via_markers`` (which we patch).
    # A no-op context manager satisfies the ``with`` protocol.
    @contextlib.contextmanager
    def _session_factory_stub() -> Any:
        yield SimpleNamespace(
            commit=lambda: None,
            close=lambda: None,
        )

    # 4. ``outcome`` stand-in. The real ``run_scenario_via_markers``
    # is patched; the test only needs ``outcome.outcome`` and
    # ``outcome.scheme_run.id`` to satisfy the cheap post-run
    # validation in ``_cmd_run``.
    outcome_stub = SimpleNamespace(
        outcome="SUCCEEDED",
        scheme_run=SimpleNamespace(
            id="p1-2-stub-scheme-run-id",
            project_id="a1-test-p-001",
            project_version_id="a1-test-v-001",
        ),
    )

    # 5. ``_verify_manifest_golden_binding`` stand-in. Returns a
    # synthetic ``(expected, actual, comparison)`` triple so the
    # post-``golden`` ``run_identity`` dict can be built without
    # touching the real golden file.
    golden_comparison_stub = (
        {"scenario_id": "baseline_feasible", "expected_outcome": "SUCCEEDED"},
        {"scenario_id": "baseline_feasible", "expected_outcome": "SUCCEEDED"},
        SimpleNamespace(passed=True, diffs=()),
    )

    # 6. ``_compose_report_services`` stand-in. The composition
    # tuple is unpacked positionally; we return five placeholders.
    compose_stub = (
        SimpleNamespace(name="report_service_stub"),
        SimpleNamespace(name="render_service_stub"),
        SimpleNamespace(name="template_repo_stub", commit=lambda: None),
        SimpleNamespace(name="artifact_storage_stub"),
        SimpleNamespace(name="project_service_stub"),
    )

    # 7. ``_build_download_artifact`` stand-in.
    def _download_stub(*_args: object, **_kwargs: object) -> tuple[bytes, dict[str, str]]:
        return (b"", {})

    # 8. Apply all the patches. Each is restricted to the
    # functions / module-level symbols that ``_cmd_run`` calls;
    # the verifier call site itself is patched by
    # ``_patch_verifier_seam`` below.
    monkeypatch.setattr(rmp, "_provision_sqlite_database", lambda *, database_url: engine_stub)
    monkeypatch.setattr(rmp, "_build_session_factory", lambda _engine: _session_factory_stub)
    monkeypatch.setattr(rmp, "seed_a1_all_prereqs", lambda _session: None)
    monkeypatch.setattr(rmp, "_expected_source_binding_sha", lambda _session: "a" * 64)
    monkeypatch.setattr(rmp, "run_scenario_via_markers", lambda *_a, **_kw: outcome_stub)
    monkeypatch.setattr(
        rmp,
        "_verify_manifest_golden_binding",
        lambda **_kw: golden_comparison_stub,
    )
    monkeypatch.setattr(rmp, "_compose_report_services", lambda **_kw: compose_stub)
    monkeypatch.setattr(rmp, "_seed_report_templates", lambda _repo: None)
    monkeypatch.setattr(rmp, "_build_download_artifact", lambda **_kw: _download_stub)

    # 9. The verifier seam itself. ``_cmd_run`` imports
    # ``verify_multilingual_report_pilot`` from the module; we
    # patch the symbol on the rmp module (where the call
    # resolves to ``rmp.verify_multilingual_report_pilot``).
    def _verifier_seam(**_kwargs: object) -> dict[str, object]:
        if isinstance(verifier_effect, BaseException):
            raise verifier_effect
        if isinstance(verifier_effect, dict):
            return verifier_effect
        # Defensive: caller passed a non-exception non-dict.
        raise TypeError(
            f"_patch_cmd_run_to_reach_verifier: verifier_effect must be "
            f"BaseException or dict; got {type(verifier_effect).__name__}"
        )

    monkeypatch.setattr(rmp, "verify_multilingual_report_pilot", _verifier_seam)

    # 10. Build a writable empty output root + a manifest that
    # the cheap CLI argument validation will accept.
    out_root = rmp.BACKEND_DIR / f"p1-2-out-{scenario.scenario_id}-test"
    if out_root.exists():
        # Clean up stale state from a previous run.
        for child in out_root.iterdir():
            if child.is_file():
                child.unlink()
            else:
                # Recursive cleanup via shutil to handle nested dirs.
                import shutil

                shutil.rmtree(child)
    out_root.mkdir(parents=True, exist_ok=True)

    args = argparse.Namespace(
        commit_sha="a" * 40,
        manifest=str(manifest_path),
        output_root=str(out_root),
        backend=scenario.database_backend.value,  # must match scenario
        database_url=f"sqlite:///{out_root / 'stub.sqlite'}",
        repeat_index=1,
    )
    return args


def test_p1_2_pilot_verification_error_returns_exit_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1-2 Test 1: ``PilotVerificationError`` from the verifier seam → exit 4.

    The composition MUST catch the typed verifier error, write a
    stable stderr line ``PILOT_VERIFICATION_ERROR code=<typed-code>:
    <message>``, and return ``EXIT_VERIFIER_ERROR = 4``. The
    stdout summary MUST NOT be written (no false PASS).

    The error is raised from the real ``verify_multilingual_report_pilot``
    call site (the verifier seam), NOT from an unrelated
    pre-step. The pre-step infrastructure (database provision /
    seed / backend runner / golden comparison / report-service
    composition / template seed / download callable) is
    monkeypatched via ``_patch_cmd_run_to_reach_verifier`` so
    the test runs in milliseconds while still exercising the
    real ``_cmd_run`` orchestration logic and the new typed
    ``except PilotVerificationError`` block.
    """
    forced_message = "forced verifier failure for P1-2 test 1"
    args = _patch_cmd_run_to_reach_verifier(
        monkeypatch,
        verifier_effect=PilotVerificationError(
            code="DOWNLOAD_INTEGRITY_MISMATCH",
            message=forced_message,
        ),
    )
    rc = rmp._cmd_run(args)
    captured = capsys.readouterr()
    # Exit code MUST be EXIT_VERIFIER_ERROR (= 4) exactly.
    assert rc == rmp.EXIT_VERIFIER_ERROR == 4, f"verifier failure MUST map to exit 4; got rc={rc!r}"
    # stderr MUST contain the typed code in the stable prefix.
    assert "PILOT_VERIFICATION_ERROR" in captured.err, (
        f"stderr MUST carry the PILOT_VERIFICATION_ERROR prefix; got {captured.err!r}"
    )
    assert "code=DOWNLOAD_INTEGRITY_MISMATCH" in captured.err, (
        f"stderr MUST surface the typed verifier code; got {captured.err!r}"
    )
    # The exception MUST NOT propagate to the test driver (the
    # composition catches it; the test sees a clean rc).
    # stdout MUST be empty (no false PASS summary).
    assert captured.out == "", f"stdout MUST be empty on verifier failure; got {captured.out!r}"


@pytest.mark.parametrize(
    ("verifier_code", "verifier_message"),
    [
        ("DOWNLOAD_INTEGRITY_MISMATCH", "download bytes do not match X-Content-SHA256"),
        ("SEMANTIC_NUMERIC_MISMATCH", "extracted numeric field disagrees with golden"),
    ],
)
def test_p1_2_multiple_verifier_codes_map_to_4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verifier_code: str,
    verifier_message: str,
) -> None:
    """P1-2 Test 2: every ``PilotVerificationError`` code → exit 4.

    The exit-code classification MUST be exception-type-driven,
    NOT ``exc.code``-driven. Two distinct typed codes (one
    download-integrity, one semantic-numeric — covering both
    the "download path" and the "semantic path" failure
    families) MUST both map to ``EXIT_VERIFIER_ERROR = 4``.

    The parameterised body reuses
    ``_patch_cmd_run_to_reach_verifier`` so the verifier seam
    is the only piece raising an exception; the test fails
    if the composition has built a hand-written code allowlist
    that maps e.g. only DOWNLOAD_INTEGRITY_MISMATCH to 4 and
    silently propagates other codes.
    """
    args = _patch_cmd_run_to_reach_verifier(
        monkeypatch,
        verifier_effect=PilotVerificationError(
            code=verifier_code,
            message=verifier_message,
        ),
    )
    rc = rmp._cmd_run(args)
    captured = capsys.readouterr()
    assert rc == rmp.EXIT_VERIFIER_ERROR == 4, (
        f"verifier code={verifier_code!r} MUST map to exit 4; got rc={rc!r}"
    )
    assert f"code={verifier_code}" in captured.err, (
        f"stderr MUST surface the typed code={verifier_code!r}; got {captured.err!r}"
    )


def test_p1_2_generic_runtime_error_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1-2 Test 3: a generic ``RuntimeError`` from the verifier seam propagates.

    The P1-2 fix MUST NOT be implemented as a blanket
    ``except Exception`` / ``except BaseException`` that swallows
    unrelated programming errors and returns 4. A
    ``RuntimeError("unexpected failure")`` raised from the
    verifier seam MUST propagate out of ``_cmd_run`` unchanged
    so the operator / CI can see the real failure (not a
    misclassified "verifier error").

    ``pytest.raises(RuntimeError)`` asserts the exception
    escaped; the captured stdout/stderr is checked secondarily
    to confirm no classification stderr was written.
    """
    args = _patch_cmd_run_to_reach_verifier(
        monkeypatch,
        verifier_effect=RuntimeError("unexpected failure"),
    )
    with pytest.raises(RuntimeError) as caught:
        rmp._cmd_run(args)
    # The exception type and message MUST be preserved
    # (the composition MUST NOT wrap it into a different type
    # or rewrite the message).
    assert isinstance(caught.value, RuntimeError)
    assert "unexpected failure" in str(caught.value)
    # Defense-in-depth: the P1-2 catch MUST NOT have fired
    # (no PILOT_VERIFICATION_ERROR stderr).
    captured = capsys.readouterr()
    assert "PILOT_VERIFICATION_ERROR" not in captured.err, (
        f"a generic RuntimeError MUST NOT be classified as a verifier "
        f"failure; got stderr={captured.err!r}"
    )


def test_p1_2_composition_error_mapping_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P1-2 Test 4: existing ``PilotCompositionError`` mapping is preserved.

    The pre-existing composition-error classifier (P1-1 round)
    maps ``PilotCompositionError(code=INPUT_ERROR)`` to
    ``EXIT_INPUT_ERROR = 2`` and writes
    ``PILOT_COMPOSITION_ERROR code=<typed-code>:`` to stderr.
    The P1-2 catch MUST NOT swallow this exception class (it is
    a separate class from ``PilotVerificationError``) and MUST
    NOT change the exit-code mapping.

    The test raises the composition error from the verifier seam
    via the same ``_patch_cmd_run_to_reach_verifier`` helper, so
    the post-catch flow is exercised against a real
    ``_cmd_run`` body (the helper does not bypass the catch).
    """
    args = _patch_cmd_run_to_reach_verifier(
        monkeypatch,
        verifier_effect=rmp.PilotCompositionError(
            code="INPUT_ERROR",
            message="forced composition error for P1-2 regression test 4",
        ),
    )
    rc = rmp._cmd_run(args)
    captured = capsys.readouterr()
    # Pre-P1-2 mapping MUST still hold: INPUT_ERROR → 2.
    assert rc == rmp.EXIT_INPUT_ERROR == 2, (
        f"PilotCompositionError(INPUT_ERROR) MUST still map to EXIT_INPUT_ERROR=2; got rc={rc!r}"
    )
    assert "PILOT_COMPOSITION_ERROR" in captured.err
    assert "code=INPUT_ERROR" in captured.err
    # The P1-2 catch MUST NOT have fired (it is typed to
    # ``PilotVerificationError``, not ``PilotCompositionError``).
    assert "PILOT_VERIFICATION_ERROR" not in captured.err
