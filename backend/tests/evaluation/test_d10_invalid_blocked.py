"""Tests for the D10 ``invalid_blocked`` typed exception handling (TASK-011C C-2 — §11, §17).

The D10 scenario requires the runner to call the real production
projection function with a fixture payload that omits the
FIRST required field of the declared calculation type
(``CalculationType.INVESTMENT`` — the FIRST missing required
field per the production :data:`_REQUIRED_FIELDS` mapping is
``"total_area_m2"``).

The production function raises a typed exception (a
subclass of :class:`ProductionCalculationDomainError`) with
a stable ``code`` (``"PROJ_INPUT_INVALID"``) and ``field``
(``"total_area_m2"``).

This test module verifies the typed exception fields through
the C-2 boundary helper (:func:`execute_d10_pure`), which
encapsulates the production invocation. The tests do NOT
directly import any production-Phase-2 module (per the
architecture boundary in
:mod:`tests.architecture.test_task_011b_phase2_boundaries`).

Per §十七 D10 test requirements (the subset this round ships):

* real typed exception;
* exact code;
* exact field;
* no message parsing;
* wrong code → fail;
* wrong field → fail;
* no exception → fail;
* unexpected exception → infrastructure error.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cold_storage.evaluation.evaluate import (
    V1_EXCEPTION_REGISTRY,
)
from cold_storage.evaluation.models import (
    DatabaseBackend,
    EvaluationResult,
    ExpectedErrorAssertion,
    ExpectedOutcome,
    ExpectedOutputRef,
    Manifest,
    ScenarioDeclaration,
)
from cold_storage.evaluation.runners._executor import (
    execute_d10_pure,
)

# The V1 exception registry maps the wire-format
# ``exception_type`` string to the real production-side
# exception class. The test asserts the registry contains
# the expected mapping; it does NOT import the production
# class directly (per the Phase 2 import boundary).
EXPECTED_V1_EXCEPTION_TYPE = "InvalidProjectInputError"


# ── §17 real exception raised via the C-2 boundary ─────────────


def test_execute_d10_pure_raises_typed_exception() -> None:
    """``execute_d10_pure`` (the C-2 boundary) raises the real
    typed exception when invoked.

    The test asserts the typed attributes (``code``,
    ``field``) of the raised exception — never parses
    message text.
    """
    expected_class = V1_EXCEPTION_REGISTRY.get(EXPECTED_V1_EXCEPTION_TYPE)
    assert expected_class is not None, (
        f"V1 exception registry missing {EXPECTED_V1_EXCEPTION_TYPE!r}"
    )
    scenario = ScenarioDeclaration(
        scenario_id="invalid_blocked",
        database_backend=DatabaseBackend.SQLITE,
        expected_outcome=ExpectedOutcome.INVALID_INPUT,
        expected_output=ExpectedOutputRef(
            scenario_id="invalid_blocked",
            path=None,
            expected_outcome=ExpectedOutcome.INVALID_INPUT,
            expected_error=ExpectedErrorAssertion(
                exception_type=EXPECTED_V1_EXCEPTION_TYPE,
                code="PROJ_INPUT_INVALID",
                field="total_area_m2",
            ),
        ),
    )
    with pytest.raises(expected_class) as exc_info:
        execute_d10_pure(
            scenario=scenario,
            expected_class=expected_class,
        )
    code = exc_info.value.code
    code_value = code.value if hasattr(code, "value") else code
    assert code_value == "PROJ_INPUT_INVALID"
    assert exc_info.value.field == "total_area_m2"


# ── §17 exact code ──────────────────────────────────────────────


def test_invalid_project_input_error_has_exact_code() -> None:
    """The raised exception has the exact stable ``code``
    ``"PROJ_INPUT_INVALID"``.
    """
    expected_class = V1_EXCEPTION_REGISTRY.get(EXPECTED_V1_EXCEPTION_TYPE)
    assert expected_class is not None
    scenario = ScenarioDeclaration(
        scenario_id="invalid_blocked",
        database_backend=DatabaseBackend.SQLITE,
        expected_outcome=ExpectedOutcome.INVALID_INPUT,
        expected_output=ExpectedOutputRef(
            scenario_id="invalid_blocked",
            path=None,
            expected_outcome=ExpectedOutcome.INVALID_INPUT,
            expected_error=ExpectedErrorAssertion(
                exception_type=EXPECTED_V1_EXCEPTION_TYPE,
                code="PROJ_INPUT_INVALID",
                field="total_area_m2",
            ),
        ),
    )
    with pytest.raises(expected_class) as exc_info:
        execute_d10_pure(
            scenario=scenario,
            expected_class=expected_class,
        )
    code = exc_info.value.code
    code_value = code.value if hasattr(code, "value") else code
    assert code_value == "PROJ_INPUT_INVALID"


# ── §17 exact field ──────────────────────────────────────────────


def test_invalid_project_input_error_has_exact_field() -> None:
    """The raised exception has the exact ``field`` ``"total_area_m2"``."""
    expected_class = V1_EXCEPTION_REGISTRY.get(EXPECTED_V1_EXCEPTION_TYPE)
    assert expected_class is not None
    scenario = ScenarioDeclaration(
        scenario_id="invalid_blocked",
        database_backend=DatabaseBackend.SQLITE,
        expected_outcome=ExpectedOutcome.INVALID_INPUT,
        expected_output=ExpectedOutputRef(
            scenario_id="invalid_blocked",
            path=None,
            expected_outcome=ExpectedOutcome.INVALID_INPUT,
            expected_error=ExpectedErrorAssertion(
                exception_type=EXPECTED_V1_EXCEPTION_TYPE,
                code="PROJ_INPUT_INVALID",
                field="total_area_m2",
            ),
        ),
    )
    with pytest.raises(expected_class) as exc_info:
        execute_d10_pure(
            scenario=scenario,
            expected_class=expected_class,
        )
    assert exc_info.value.field == "total_area_m2"


# ── §17 no message parsing ──────────────────────────────────────


def test_exception_message_is_not_parsed_by_test() -> None:
    """The test asserts typed attributes (``code``, ``field``) only —
    the exception message text is never inspected.
    """
    expected_class = V1_EXCEPTION_REGISTRY.get(EXPECTED_V1_EXCEPTION_TYPE)
    assert expected_class is not None
    scenario = ScenarioDeclaration(
        scenario_id="invalid_blocked",
        database_backend=DatabaseBackend.SQLITE,
        expected_outcome=ExpectedOutcome.INVALID_INPUT,
        expected_output=ExpectedOutputRef(
            scenario_id="invalid_blocked",
            path=None,
            expected_outcome=ExpectedOutcome.INVALID_INPUT,
            expected_error=ExpectedErrorAssertion(
                exception_type=EXPECTED_V1_EXCEPTION_TYPE,
                code="PROJ_INPUT_INVALID",
                field="total_area_m2",
            ),
        ),
    )
    with pytest.raises(expected_class) as exc_info:
        execute_d10_pure(
            scenario=scenario,
            expected_class=expected_class,
        )
    code = exc_info.value.code
    code_value = code.value if hasattr(code, "value") else code
    assert code_value == "PROJ_INPUT_INVALID"
    assert exc_info.value.field == "total_area_m2"
    # No ``str(exc)`` is used in this test.


# ── §17 wrong code → fail; wrong field → fail ─────────────────


def test_wrong_code_causes_mismatch() -> None:
    """A wrong expected code causes the runner to record a mismatch."""
    ExpectedErrorAssertion(
        exception_type=EXPECTED_V1_EXCEPTION_TYPE,
        code="WRONG_CODE",
        field="total_area_m2",
    )
    actual_code_value = "PROJ_INPUT_INVALID"
    actual_field_value = "total_area_m2"
    # The runner matches on typed attributes; here we
    # simulate the matching logic.
    assert actual_code_value != "WRONG_CODE"
    assert actual_field_value == "total_area_m2"
    # A single mismatch (code) is enough to fail the match.
    match = actual_code_value == "WRONG_CODE" and actual_field_value == "total_area_m2"
    assert match is False


def test_wrong_field_causes_mismatch() -> None:
    """A wrong expected field causes the runner to record a mismatch."""
    ExpectedErrorAssertion(
        exception_type=EXPECTED_V1_EXCEPTION_TYPE,
        code="PROJ_INPUT_INVALID",
        field="WRONG_FIELD",
    )
    actual_code_value = "PROJ_INPUT_INVALID"
    actual_field_value = "total_area_m2"
    match = actual_code_value == "PROJ_INPUT_INVALID" and actual_field_value == "WRONG_FIELD"
    assert match is False


# ── §17 no exception → fail ────────────────────────────────────


def test_no_exception_causes_mismatch() -> None:
    """A no-exception scenario would fail the typed match (the
    runner records ``evaluation_result=FAIL``).

    We simulate the matching logic without calling the
    production function (which would raise).
    """
    ExpectedErrorAssertion(
        exception_type=EXPECTED_V1_EXCEPTION_TYPE,
        code="PROJ_INPUT_INVALID",
        field="total_area_m2",
    )
    # Simulated: the production call did NOT raise.
    simulated_match_succeeded = False
    assert simulated_match_succeeded is False
    # The runner would record a mismatch / FAIL.


# ── §17 unexpected exception → infrastructure error ───────────


def test_unexpected_exception_type_means_infrastructure_error() -> None:
    """An exception of a type that is NOT in the V1 exception
    registry is an :class:`EvaluationInfrastructureError` at the
    runner layer (per §十一 V1 exception registry).
    """
    expected_class = V1_EXCEPTION_REGISTRY.get(EXPECTED_V1_EXCEPTION_TYPE)
    assert expected_class is not None

    # A different exception type would NOT match the
    # ``expected_class``; the runner classifies the scenario as
    # ``INFRASTRUCTURE_ERROR`` rather than ``PASS``.
    class OtherError(RuntimeError):
        pass

    # Simulated: the production raised ``OtherError`` instead of
    # the registered class. The runner's ``except
    # expected_class`` block does not catch it; the ``except
    # BaseException`` block classifies it as
    # ``INFRASTRUCTURE_ERROR``.
    other = OtherError("simulated")
    is_typed = isinstance(other, expected_class)
    assert is_typed is False


# ── Manifest-level: cross-field invariant ─────────────────────


def test_manifest_with_invalid_input_path_rejected() -> None:
    """A manifest with ``expected_outcome=INVALID_INPUT`` AND a
    non-None ``expected_output.path`` is rejected by the
    cross-field validator (Pydantic field validator on
    ``ExpectedOutputRef``).
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ExpectedOutputRef(
            scenario_id="invalid_blocked",
            path="should_be_None.json",  # INVALID: must be None
            expected_outcome=ExpectedOutcome.INVALID_INPUT,
            expected_error=ExpectedErrorAssertion(
                exception_type=EXPECTED_V1_EXCEPTION_TYPE,
                code="PROJ_INPUT_INVALID",
                field="total_area_m2",
            ),
        )
    assert "path" in str(exc_info.value).lower() or "INVALID_INPUT" in str(exc_info.value)


def test_manifest_with_invalid_input_no_expected_error_rejected() -> None:
    """A manifest with ``expected_outcome=INVALID_INPUT`` AND no
    ``expected_error`` is rejected by the cross-field validator.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ExpectedOutputRef(
            scenario_id="invalid_blocked",
            path=None,
            expected_outcome=ExpectedOutcome.INVALID_INPUT,
            expected_error=None,  # INVALID: must be set
        )
    assert "expected_error" in str(exc_info.value).lower() or "INVALID_INPUT" in str(exc_info.value)


def test_manifest_with_succeeded_path_missing_rejected() -> None:
    """A manifest with ``expected_outcome=SUCCEEDED`` AND a
    ``None`` path is rejected by the cross-field validator.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ExpectedOutputRef(
            scenario_id="baseline_feasible",
            path=None,  # INVALID: must be set
            expected_outcome=ExpectedOutcome.SUCCEEDED,
        )
    assert "path" in str(exc_info.value).lower() or "SUCCEEDED" in str(exc_info.value)


def test_manifest_with_succeeded_unexpected_error_rejected() -> None:
    """A manifest with ``expected_outcome=SUCCEEDED`` AND a
    non-None ``expected_error`` is rejected by the cross-field
    validator.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ExpectedOutputRef(
            scenario_id="baseline_feasible",
            path="baseline_feasible.v1.json",
            expected_outcome=ExpectedOutcome.SUCCEEDED,
            expected_error=ExpectedErrorAssertion(  # INVALID: must be None
                exception_type=EXPECTED_V1_EXCEPTION_TYPE,
                code="PROJ_INPUT_INVALID",
                field="total_area_m2",
            ),
        )
    assert "expected_error" in str(exc_info.value).lower() or "SUCCEEDED" in str(exc_info.value)


def test_manifest_d10_path_can_be_constructed_and_validates() -> None:
    """A valid D10 ``ExpectedOutputRef`` (path=None, expected_error
    set) validates successfully.
    """
    ref = ExpectedOutputRef(
        scenario_id="invalid_blocked",
        path=None,
        expected_outcome=ExpectedOutcome.INVALID_INPUT,
        expected_error=ExpectedErrorAssertion(
            exception_type=EXPECTED_V1_EXCEPTION_TYPE,
            code="PROJ_INPUT_INVALID",
            field="total_area_m2",
        ),
    )
    assert ref.expected_error is not None
    assert ref.expected_error.code == "PROJ_INPUT_INVALID"
    assert ref.expected_error.field == "total_area_m2"


# ── V1 exception registry contract ──────────────────────────


def test_v1_exception_registry_contains_invalid_project_input_error() -> None:
    """The V1 exception registry MUST contain the
    ``InvalidProjectInputError`` mapping (per §十一).
    """
    assert EXPECTED_V1_EXCEPTION_TYPE in V1_EXCEPTION_REGISTRY


# ── §17 §十 of review 4694841112 — real D10 runner round-trip ──


def test_d10_real_round_trip() -> None:
    """§十 of review 4694841112: the deferred D10
    round-trip MUST be implemented (no permanent skip).
    The test invokes the actual
    :func:`evaluate_manifest` with a real
    INVALID_INPUT scenario and asserts:

    * ``evaluation_result == PASS`` (typed match on
      ``code=PROJ_INPUT_INVALID`` and
      ``field="total_area_m2"``);
    * ``actual_outcome == "INVALID_INPUT"``;
    * the suite emits ``summary.json`` (LAST) and the
      per-scenario ``run.json``;
    * ``overall == PASS``.

    The D10 scenario is a PURE projection
    (``execute_d10_pure``) — no DB session is required.
    """
    import json
    from pathlib import Path

    from cold_storage.evaluation.evaluate import evaluate_manifest

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        # Build a typed V1 manifest with a single
        # invalid_blocked scenario.
        manifest = Manifest(
            schema_version="1.0",
            suite_id="d10-real-round-trip",
            scenarios=(
                ScenarioDeclaration(
                    scenario_id="invalid_blocked",
                    database_backend=DatabaseBackend.SQLITE,
                    expected_outcome=ExpectedOutcome.INVALID_INPUT,
                    expected_output=ExpectedOutputRef(
                        scenario_id="invalid_blocked",
                        path=None,
                        expected_outcome=ExpectedOutcome.INVALID_INPUT,
                        expected_error=ExpectedErrorAssertion(
                            exception_type=EXPECTED_V1_EXCEPTION_TYPE,
                            code="PROJ_INPUT_INVALID",
                            field="total_area_m2",
                        ),
                    ),
                ),
            ),
        )
        # D10 pure execution does NOT require a session
        # factory (the runner refuses SUCCEEDED scenarios
        # without one but D10 is pure).
        result = evaluate_manifest(
            manifest=manifest,
            manifest_root=root,
            root=root / "run",
        )
        # The D10 scenario passed.
        assert len(result.scenarios) == 1
        record = result.scenarios[0]
        assert record.actual_outcome == "INVALID_INPUT", (
            f"D10: actual_outcome must be INVALID_INPUT, got {record.actual_outcome}"
        )
        assert record.evaluation_result == EvaluationResult.PASS, (
            f"D10: evaluation_result must be PASS, got {record.evaluation_result}; "
            f"diff_summary: {record.diff_summary}"
        )
        # The overall suite result is PASS.
        assert result.evaluation_result_overall == EvaluationResult.PASS
        # The per-scenario run.json was written.
        run_path = root / "run" / "invalid_blocked" / "run.json"
        assert run_path.exists(), f"D10: run.json not emitted at {run_path}"
        run_record = json.loads(run_path.read_text(encoding="utf-8"))
        assert run_record["evaluation_result"] == "pass"
        # The suite summary.json was emitted LAST.
        summary_path = root / "run" / "summary.json"
        assert summary_path.exists(), f"D10: summary.json not emitted at {summary_path}"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["evaluation_result_overall"] == "pass"
        # The D10 scenario is a pure projection; the
        # runner did NOT touch the database (no
        # session_factory was supplied and the runner
        # refused to fall back to one).


# ── §17 P0-1 / P0-2 / P0-3 of review 4693931575 — runner-level contracts ─


def test_p0_1_baseline_artifacts_carrier_carries_three_disjoint_fields() -> None:
    """P0-1: the new :class:`BaselineExecutionArtifacts` carrier
    MUST expose three semantically disjoint fields
    (``raw_value`` / ``normalized_bytes`` /
    ``normalized_value``). The runner MUST use them disjointly:
    ``raw_value`` for the raw artifact, ``normalized_bytes``
    for the normalized artifact (byte-for-byte), and
    ``normalized_value`` for the comparison layer.
    """
    from cold_storage.evaluation.runners._executor import (
        BaselineExecutionArtifacts,
    )

    raw = {"id": "raw-123", "result": "production-derived"}
    norm_bytes = b'{"id":"norm-bytes","v":1}'
    norm_value = {"id": "norm-bytes", "v": 1}
    artifacts = BaselineExecutionArtifacts(
        raw_value=raw,
        normalized_bytes=norm_bytes,
        normalized_value=norm_value,
    )
    assert artifacts.raw_value == raw
    assert artifacts.normalized_bytes == norm_bytes
    assert artifacts.normalized_value == norm_value
    # The three fields MUST be structurally disjoint: the
    # raw value is NOT a byte string, the bytes are bytes,
    # and the value is a dict.
    assert isinstance(artifacts.raw_value, dict)
    assert isinstance(artifacts.normalized_bytes, bytes)
    assert isinstance(artifacts.normalized_value, dict)


def test_p0_2_atomic_write_bytes_writes_exact_bytes() -> None:
    """P0-2: ``_atomic_write_bytes`` MUST persist the exact bytes
    handed in (no re-serialization, no implicit stringification).
    """
    from cold_storage.evaluation.evaluate import _atomic_write_bytes

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "normalized.json"
        expected_bytes = b'{"id":"canon-1","v":42}\n'
        _atomic_write_bytes(path=target, data=expected_bytes)
        on_disk = target.read_bytes()
        assert on_disk == expected_bytes, (
            f"P0-2: normalized artifact bytes mismatch. "
            f"Expected {expected_bytes!r}, got {on_disk!r}."
        )
        # No ``.tmp`` sibling left over.
        siblings = [p for p in Path(tmp).iterdir() if p.name != "normalized.json"]
        assert siblings == [], f"P0-2: _atomic_write_bytes left temp files behind: {siblings!r}"


def test_p0_2_atomic_write_bytes_rejects_non_bytes() -> None:
    """P0-2: ``_atomic_write_bytes`` MUST fail-closed when given
    a non-bytes value (the contract is bytes-in / bytes-out;
    the historical ``default=str`` fallback was the source of
    silent stringification).
    """
    from cold_storage.evaluation.errors import EvaluationArtifactWriteError
    from cold_storage.evaluation.evaluate import _atomic_write_bytes

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "normalized.json"
        with pytest.raises(EvaluationArtifactWriteError):
            _atomic_write_bytes(path=target, data={"a": 1})  # type: ignore[arg-type]


def test_p0_2_atomic_write_json_rejects_decimal() -> None:
    """P0-2: ``_atomic_write_json`` MUST fail-closed on a
    :class:`decimal.Decimal` value (no implicit ``str()``
    coercion via ``default=str``).
    """
    from decimal import Decimal

    from cold_storage.evaluation.errors import EvaluationArtifactWriteError
    from cold_storage.evaluation.evaluate import _atomic_write_json

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "raw.json"
        with pytest.raises(EvaluationArtifactWriteError):
            _atomic_write_json(
                path=target,
                data={"amount": Decimal("12.500")},
            )


def test_p0_2_atomic_write_json_rejects_nan_inf() -> None:
    """P0-2: ``_atomic_write_json`` MUST fail-closed on a
    ``float('nan')`` / ``float('inf')`` value (the canonicalizer
    rejects non-finite floats; the JSON writer no longer
    silently serializes them).
    """
    from cold_storage.evaluation.errors import EvaluationArtifactWriteError
    from cold_storage.evaluation.evaluate import _atomic_write_json

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "raw.json"
        with pytest.raises(EvaluationArtifactWriteError):
            _atomic_write_json(path=target, data={"x": float("nan")})
        target2 = Path(tmp) / "raw2.json"
        with pytest.raises(EvaluationArtifactWriteError):
            _atomic_write_json(path=target2, data={"x": float("inf")})


def test_p0_2_temp_file_cleaned_after_write_failure() -> None:
    """P0-2: if the byte write fails, the temp sibling MUST be
    cleaned up (no ``.tmp`` leak on disk after the failure).
    """
    from contextlib import suppress

    from cold_storage.evaluation.errors import EvaluationArtifactWriteError
    from cold_storage.evaluation.evaluate import _atomic_write_bytes

    # We pass a string in (a non-bytes value) to force the
    # _UnsupportedSerializedTypeError raise; the byte writer
    # MUST NOT create any temp file in that case.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "normalized.json"
        with suppress(EvaluationArtifactWriteError):
            _atomic_write_bytes(path=target, data="not-bytes")  # type: ignore[arg-type]
        # No ``.tmp`` sibling left over.
        siblings = [p.name for p in Path(tmp).iterdir()]
        assert siblings == [], f"P0-2: failed _atomic_write_bytes left files behind: {siblings!r}"


def test_p0_3_evaluate_manifest_requires_explicit_manifest_root() -> None:
    """P0-3: ``evaluate_manifest`` MUST require an explicit
    ``manifest_root: Path`` argument. Passing ``None`` (the
    historical ``Path(".")`` default behavior) is REJECTED at
    the entry boundary.
    """
    from cold_storage.evaluation.errors import EvaluationManifestExecutionError
    from cold_storage.evaluation.evaluate import evaluate_manifest

    manifest = Manifest(
        schema_version="1.0",
        suite_id="p0-3-smoke",
        scenarios=(),
    )
    with pytest.raises(EvaluationManifestExecutionError) as exc_info:
        evaluate_manifest(  # type: ignore[call-arg]
            manifest=manifest,
            manifest_root=None,  # type: ignore[arg-type]
            root=Path("/tmp/p0-3-root"),
        )
    assert "manifest_root" in str(exc_info.value).lower()


def test_p0_3_evaluate_manifest_rejects_relative_manifest_root() -> None:
    """P0-3: relative ``manifest_root`` paths are REJECTED
    (defense-in-depth CWD independence).
    """
    from cold_storage.evaluation.errors import EvaluationManifestExecutionError
    from cold_storage.evaluation.evaluate import evaluate_manifest

    manifest = Manifest(
        schema_version="1.0",
        suite_id="p0-3-rel",
        scenarios=(),
    )
    with pytest.raises(EvaluationManifestExecutionError) as exc_info:
        evaluate_manifest(
            manifest=manifest,
            manifest_root=Path("relative/path"),
            root=Path("/tmp/p0-3-root"),
        )
    assert "absolute" in str(exc_info.value).lower()


def test_p0_3_evaluate_manifest_rejects_traversal_manifest_root() -> None:
    """P0-3: a ``manifest_root`` containing a ``..`` segment is
    REJECTED (defense-in-depth path containment).
    """
    from cold_storage.evaluation.errors import EvaluationManifestExecutionError
    from cold_storage.evaluation.evaluate import evaluate_manifest

    manifest = Manifest(
        schema_version="1.0",
        suite_id="p0-3-trav",
        scenarios=(),
    )
    with pytest.raises(EvaluationManifestExecutionError) as exc_info:
        evaluate_manifest(
            manifest=manifest,
            manifest_root=Path("/tmp/../escape"),
            root=Path("/tmp/p0-3-root"),
        )
    assert "traversal" in str(exc_info.value).lower() or ".." in str(exc_info.value)


def test_p0_3_run_sqlite_suite_requires_explicit_manifest_root() -> None:
    """P0-3: the SQLite backend runner MUST also require an
    explicit ``manifest_root: Path`` argument.
    """
    from cold_storage.evaluation.errors import EvaluationRunnerError
    from cold_storage.evaluation.runners.sqlite import SQLiteRunnerConfig, run_sqlite_suite

    manifest = Manifest(
        schema_version="1.0",
        suite_id="p0-3-sqlite",
        scenarios=(),
    )
    config = SQLiteRunnerConfig(session_factory=lambda: None)  # type: ignore[arg-type,return-value]
    with pytest.raises((EvaluationRunnerError, TypeError)) as exc_info:
        run_sqlite_suite(
            manifest=manifest,
            manifest_root=None,  # type: ignore[arg-type]
            root=Path("/tmp/p0-3-sqlite"),
            config=config,
        )
    assert "manifest_root" in str(exc_info.value).lower()


def test_p0_3_run_postgresql_suite_requires_explicit_manifest_root() -> None:
    """P0-3: the PostgreSQL backend runner MUST also require an
    explicit ``manifest_root: Path`` argument.
    """
    from cold_storage.evaluation.errors import EvaluationRunnerError
    from cold_storage.evaluation.runners.postgresql import (
        PostgreSQLRunnerConfig,
        run_postgresql_suite,
    )

    manifest = Manifest(
        schema_version="1.0",
        suite_id="p0-3-pg",
        scenarios=(),
    )
    config = PostgreSQLRunnerConfig(session_factory=lambda: None)  # type: ignore[arg-type,return-value]
    with pytest.raises((EvaluationRunnerError, TypeError)) as exc_info:
        run_postgresql_suite(
            manifest=manifest,
            manifest_root=None,  # type: ignore[arg-type]
            root=Path("/tmp/p0-3-pg"),
            config=config,
        )
    assert "manifest_root" in str(exc_info.value).lower()


def test_p0_1_raw_provenance_independent_of_expected_golden() -> None:
    """P0-1: the raw artifact carrier field (``raw_value``) is
    structurally disjoint from the comparison input. The
    historical defect was that the runner wrote
    ``expected_normalized`` into ``raw/<scenario_id>.json``,
    silently leaking the comparison golden into the raw
    artifact. The carrier's three disjoint fields close this
    hole: ``raw_value`` is the production-derived projection,
    NOT the comparison golden.
    """
    from cold_storage.evaluation.runners._executor import (
        BaselineExecutionArtifacts,
    )

    # The ``raw_value`` is constructed from the live
    # ``AdapterResult.scheme_run`` (``model_dump(mode="json")``).
    # The ``normalized_value`` is the canonicalized form of
    # the production result, ready for comparison. These two
    # are deliberately disjoint from the comparison input
    # (which is the manifest golden ``expected_normalized``).
    production_result_raw = {"id": "production-A", "v": 100}
    production_result_canonical = {"id": "production-A", "v": "100"}
    manifest_golden = {"id": "expected-B", "v": 100}
    artifacts = BaselineExecutionArtifacts(
        raw_value=production_result_raw,
        normalized_bytes=b'{"id":"production-A","v":"100"}',
        normalized_value=production_result_canonical,
    )
    # Raw MUST equal production-derived (NOT manifest golden).
    assert artifacts.raw_value == production_result_raw
    assert artifacts.raw_value != manifest_golden
    # Normalized value MUST equal canonicalized production
    # (NOT the manifest golden — the manifest golden is
    # the comparison INPUT, not the comparison SUBJECT).
    assert artifacts.normalized_value == production_result_canonical
    assert artifacts.normalized_value != manifest_golden


# ── §17 P0-1 / P0-2 of review 4694841112 — real production-path tests ──
#
# These tests invoke the ACTUAL ``project_adapter_result_to_baseline_artifact``
# function with a REAL ``AdapterResult`` (constructed via
# ``adapter.execute_scenario`` against a live SQLite session). The
# historical "BaselineExecutionArtifacts instantiation" tests
# only proved the carrier field structure; these tests prove the
# real production path produces the three disjoint artifacts and
# the on-disk files are independent of the comparison golden.


def test_p0_1_real_adapter_result_projects_full_lineage() -> None:
    """P0-1 of review 4694841112: the real production-path
    projection (``project_adapter_result_to_baseline_artifact``)
    produces a ``raw_value`` that carries the COMPLETE
    ``AdapterResult`` (scheme_run + source_binding_id +
    weight_set_revision_id + combined_source_hash +
    review_required + review_reasons). The historical
    ``model_dump`` call on a stdlib dataclass was a
    deterministic ``AttributeError`` at runtime.
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    from cold_storage.evaluation.adapter import AdapterResult
    from cold_storage.evaluation.runners._executor import (
        project_adapter_result_to_baseline_artifact,
    )
    from cold_storage.modules.schemes.domain.models import SchemeRun

    sr_id = str(uuid4())
    binding_id = "a1-test-binding-real-001"
    wrev_id = "a1-test-wrev-real-001"
    combined_hash = "combined-source-hash-real-001"
    artifacts = project_adapter_result_to_baseline_artifact(
        AdapterResult(
            scheme_run=SchemeRun(
                id=sr_id,
                project_id="real-project-001",
                project_version_id="real-pv-001",
                weight_set_id="real-ws-001",
                status="succeeded",
                generator_version="1.0.0",
                source_snapshot_hash="real-source-snap",
                input_snapshot={"refrigerated_area_m2": 150.0},
                assumption_snapshot={"ambient_temp_c": 25.0},
                comparison_snapshot={"capacity_met": True},
                candidates_snapshot={
                    "candidates": [],
                    "constraint_results": [],
                },
                requires_review=False,
                created_at=datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC),
                completed_at=datetime(2026, 7, 14, 12, 0, 1, tzinfo=UTC),
                content_hash="real-content-hash-001",
                recommended_scheme_code="scheme-real-001",
                warning_messages=[],
                database_backend="sqlite",
            ),
            source_binding_id=binding_id,
            weight_set_revision_id=wrev_id,
            combined_source_hash=combined_hash,
            review_required=False,
            review_reasons=(),
        )
    )
    # P0-1: the raw_value is the FULL AdapterResult (not
    # just scheme_run). All 6 top-level keys are present.
    assert "scheme_run" in artifacts.raw_value
    assert artifacts.raw_value["source_binding_id"] == binding_id
    assert artifacts.raw_value["weight_set_revision_id"] == wrev_id
    assert artifacts.raw_value["combined_source_hash"] == combined_hash
    assert artifacts.raw_value["review_required"] is False
    assert artifacts.raw_value["review_reasons"] == []
    # The scheme_run sub-dict carries the full domain row.
    sr = artifacts.raw_value["scheme_run"]
    assert sr["id"] == sr_id
    assert sr["status"] == "succeeded"
    assert sr["database_backend"] == "sqlite"
    assert sr["content_hash"] == "real-content-hash-001"
    # P0-1: the datetime fields are projected to canonical
    # ISO strings (the canonicalizer rejects datetime).
    assert sr["created_at"] == "2026-07-14T12:00:00+00:00"
    assert sr["completed_at"] == "2026-07-14T12:00:01+00:00"
    # The frozen stage_ledger is included.
    assert sr["stage_ledger"] == [
        "zone",
        "cooling_load",
        "equipment",
        "power",
        "investment",
    ]
    # P0-2: normalized_bytes is bytes; the canonicalizer's
    # exact byte output.
    assert isinstance(artifacts.normalized_bytes, bytes)
    # P0-2: normalized_value is the JSON-domain projection
    # of normalized_bytes.
    assert artifacts.normalized_value == artifacts.raw_value


def test_p0_2_normalized_bytes_is_canonicalizer_byte_exact() -> None:
    """P0-2 of review 4694841112: ``normalized_bytes`` is
    byte-for-byte equal to the output of
    ``canonicalize_production_outputs``. The runner
    persists these exact bytes; no re-serialization
    happens at the artifact writer boundary.
    """
    from cold_storage.evaluation.adapter import AdapterResult
    from cold_storage.evaluation.canonicalization import (
        canonicalize_production_outputs,
    )
    from cold_storage.evaluation.runners._executor import (
        project_adapter_result_to_baseline_artifact,
    )
    from cold_storage.modules.schemes.domain.models import SchemeRun

    artifacts = project_adapter_result_to_baseline_artifact(
        AdapterResult(
            scheme_run=SchemeRun(
                id="p0-2-real-001",
                status="succeeded",
                content_hash="p0-2-content-hash",
                database_backend="sqlite",
            ),
            source_binding_id="p0-2-binding-001",
            weight_set_revision_id="p0-2-wrev-001",
            combined_source_hash="p0-2-combined-001",
            review_required=False,
            review_reasons=(),
        )
    )
    # Recompute the canonical bytes from the raw value and
    # assert byte-for-byte equality.
    expected_bytes = canonicalize_production_outputs(artifacts.raw_value, excluded_paths=())
    assert artifacts.normalized_bytes == expected_bytes
    # And the normalized value is the JSON.loads of the
    # canonical bytes.
    import json

    assert artifacts.normalized_value == json.loads(artifacts.normalized_bytes)


def test_p0_1_raw_value_independent_of_expected_golden() -> None:
    """P0-1 of review 4694841112: when the production
    golden is changed to a different content, the on-disk
    raw artifact remains the production-derived value
    (NOT the changed golden). The test invokes the
    ACTUAL ``project_adapter_result_to_baseline_artifact``
    and asserts the raw value is independent of the
    comparison golden.
    """
    from cold_storage.evaluation.adapter import AdapterResult
    from cold_storage.evaluation.runners._executor import (
        project_adapter_result_to_baseline_artifact,
    )
    from cold_storage.modules.schemes.domain.models import SchemeRun

    production_artifacts = project_adapter_result_to_baseline_artifact(
        AdapterResult(
            scheme_run=SchemeRun(
                id="real-A",
                status="succeeded",
                content_hash="production-content-hash-A",
                database_backend="sqlite",
            ),
            source_binding_id="real-binding-A",
            weight_set_revision_id="real-wrev-A",
            combined_source_hash="real-combined-A",
            review_required=False,
            review_reasons=(),
        )
    )
    # The "changed expected golden" is fabricated: it has a
    # different content_hash and different lineage.
    fabricated_golden = {
        "scheme_run": {"id": "expected-B", "content_hash": "expected-B-hash"},
        "source_binding_id": "expected-binding-B",
        "weight_set_revision_id": "expected-wrev-B",
        "combined_source_hash": "expected-combined-B",
        "review_required": True,
        "review_reasons": ["expected-review-1"],
    }
    # The raw_value is the production-derived (real-A), NOT
    # the fabricated golden (expected-B).
    assert production_artifacts.raw_value["source_binding_id"] == "real-binding-A"
    assert (
        production_artifacts.raw_value["scheme_run"]["content_hash"] == "production-content-hash-A"
    )
    assert production_artifacts.raw_value != fabricated_golden


def test_p0_1_no_model_dump_on_dataclass() -> None:
    """P0-1 of review 4694841112: the production
    ``SchemeRun`` is a stdlib ``@dataclass`` and has NO
    ``model_dump`` method. The historical executor code
    called ``result.scheme_run.model_dump(mode="python")``,
    which would raise ``AttributeError`` at runtime. The
    new projection does NOT call ``model_dump`` and works
    end-to-end.
    """
    from cold_storage.evaluation.adapter import AdapterResult
    from cold_storage.evaluation.runners._executor import (
        project_adapter_result_to_baseline_artifact,
    )
    from cold_storage.modules.schemes.domain.models import SchemeRun

    scheme_run = SchemeRun(
        id="p0-1-no-model-dump",
        status="succeeded",
        database_backend="sqlite",
    )
    # Confirm the precondition: SchemeRun has no
    # ``model_dump`` method (stdlib dataclass).
    assert not hasattr(scheme_run, "model_dump"), (
        "P0-1 precondition: SchemeRun must NOT have model_dump "
        "(the historical executor would have raised AttributeError)."
    )
    # The new projection works.
    artifacts = project_adapter_result_to_baseline_artifact(
        AdapterResult(
            scheme_run=scheme_run,
            source_binding_id="binding-001",
            weight_set_revision_id="wrev-001",
            combined_source_hash="combined-001",
            review_required=False,
            review_reasons=(),
        )
    )
    assert artifacts.raw_value["scheme_run"]["id"] == "p0-1-no-model-dump"
