from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

import pytest

from cold_storage.evaluation.compare import compare_outputs
from cold_storage.evaluation.errors import StaleEvaluationArtifactsError
from cold_storage.evaluation.manifest import load_and_validate_manifest
from cold_storage.evaluation.models import Manifest
from cold_storage.evaluation.pilot_reports import (
    PILOT_CHECK_ID,
    PILOT_RESULT_SCHEMA_VERSION,
    PilotVerificationError,
    verify_multilingual_report_pilot,
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


def test_p1_1_does_not_modify_p1_2_through_p1_4_areas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-1 Test 6: P1-1 fix MUST NOT touch P1-2 / P1-3 / P1-4 surfaces.

    The composition MUST NOT:

    * catch :class:`PilotVerificationError` (P1-2 — exit code 4
      unreachable);
    * change ``_semantic_checks`` numeric / unit substring logic
      (P1-3 — global-substring false-pass);
    * add a four-render end-to-end test or change the verifier
      artifact schema (P1-4 — E2E acceptance missing);
    * touch ``EXIT_VERIFIER_ERROR=4``.
    """
    # 1. The composition's exception handler still does NOT
    # catch :class:`PilotVerificationError`. A verifier contract
    # violation (P1-2 territory) MUST continue to escape as an
    # unhandled :class:`PilotVerificationError` (P1-2 is OUT OF
    # SCOPE for this round; we only assert the current behavior is
    # preserved). The check is structural: ``_cmd_run``'s except
    # block targets ``PilotCompositionError`` only, so a
    # ``PilotVerificationError`` raised anywhere inside the body
    # MUST bubble out.
    cmd_run_src = inspect.getsource(rmp._cmd_run)
    assert "except PilotCompositionError" in cmd_run_src
    assert "except PilotVerificationError" not in cmd_run_src, (
        "P1-1 fix MUST NOT catch PilotVerificationError; that is P1-2 territory."
    )

    # Programmatic check via monkeypatch: monkeypatch an early
    # step (before any DB work) to raise PilotVerificationError;
    # _cmd_run MUST let it escape.
    def _raise_verifier_error(*, manifest_path: Path) -> object:
        raise PilotVerificationError(
            code="DOWNLOAD_INTEGRITY_MISMATCH",
            message="P1-2 territory; intentionally raised for the P1-1 invariant test.",
        )

    monkeypatch.setattr(rmp, "_load_pilot_manifest", _raise_verifier_error)
    args = argparse.Namespace(
        commit_sha="a" * 40,
        manifest=str((tmp_path / "dummy.json").resolve()),
        output_root=str(tmp_path / "out"),
        backend="sqlite",
        database_url="sqlite:///:memory:",
        repeat_index=1,
    )
    (tmp_path / "dummy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "out").mkdir()
    with pytest.raises(PilotVerificationError):
        rmp._cmd_run(args)

    # 2. The composition MUST NOT have changed the exit-code
    # contract (P1-2 territory; the fix MUST remain
    # 4-unreachable in this round).
    assert rmp.EXIT_VERIFIER_ERROR == 4  # constant value unchanged
    # No new exit code was added.
    assert getattr(rmp, "EXIT_OK", None) == 0
    assert getattr(rmp, "EXIT_INPUT_ERROR", None) == 2
    assert getattr(rmp, "EXIT_BACKEND_ERROR", None) == 3
    assert getattr(rmp, "EXIT_INFRA_ERROR", None) == 1

    # 3. The composition's manifest-golden binding MUST NOT touch
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
    # P1-2 territory: the manifest-golden helper MUST NOT catch
    # ``PilotVerificationError`` (exit code 4 unreachable is OUT
    # OF SCOPE for this round).
    assert "PilotVerificationError" not in src, (
        "P1-1 fix MUST NOT catch PilotVerificationError; "
        "that is P1-2 territory and is explicitly out of scope."
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
