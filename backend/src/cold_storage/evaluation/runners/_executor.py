"""C-2 runner executor seam (TASK-011C C-2 runner authority).

This module provides the C-2 boundary between the suite runner
(:mod:`cold_storage.evaluation.evaluate`) and the actual
production-side execution. It is intentionally thin:

* :func:`execute_baseline_succeeded` is the seam that the
  runner uses to invoke the production pipeline for
  ``expected_outcome == SUCCEEDED`` scenarios. The default
  implementation goes through the typed A1-2a adapter
  (``adapter.execute_scenario``) followed by the D1
  canonicalizer. Tests or the backend runners can override
  the seam by patching this module's symbol.

* :func:`execute_d10_pure` is the seam for
  ``expected_outcome == INVALID_INPUT`` scenarios (D10). The
  default implementation exercises the pure production
  projection function
  :func:`project_calculator_input` with a fixture payload
  that omits the FIRST required field of the declared
  calculation type. Tests can override the seam to inject a
  different fixture or to verify the contract independently.

The seam exists so that the suite runner remains free of
production-seeding and fixture-construction logic. The
runner does NOT call any production calculator directly; it
goes through the seam, which is the only place that knows
the per-scenario execution strategy.

This module does NOT import ``_seed_helpers`` (which is
forbidden per §四) and does NOT construct production rows of
any kind. The pure projection function is a side-effect-free
deterministic function.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cold_storage.evaluation.canonicalization import (
    canonicalize_production_outputs,
)
from cold_storage.evaluation.errors import EvaluationRunnerError
from cold_storage.evaluation.models import ScenarioDeclaration

# ---------------------------------------------------------------------------
# C-2 baseline execution artifact carrier (P0-1 of review 4693931575).
#
# The three artifacts MUST be kept semantically disjoint:
#
#   * ``raw_value``           — the un-canonicalized production
#                               result, derived from the live
#                               ``AdapterResult`` / production
#                               ``SchemeRun`` (NOT from
#                               ``expected_output`` or the manifest
#                               golden).
#   * ``normalized_bytes``    — the D1-canonicalized byte form
#                               (the single authoritative normalized
#                               payload; the runner MUST persist
#                               these exact bytes — never a re-
#                               serialization).
#   * ``normalized_value``    — the structured JSON value derived
#                               from ``normalized_bytes`` for
#                               comparison purposes only.
#
# Persisting ``expected_normalized`` (or any value derived from
# ``expected_output``) into ``raw/<scenario_id>.json`` is the
# historical P0-1 defect; this carrier type makes the contract
# structural.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaselineExecutionArtifacts:
    """The typed artifact carrier for a SUCCEEDED scenario.

    The carrier is the single boundary between the production
    seam and the runner's artifact persistence + comparison
    pipeline. The three fields carry three distinct semantics;
    the runner MUST use them disjointly:

    * ``raw_value`` is written to
      ``<run_dir>/raw/<scenario_id>.json`` verbatim (P0-1).
    * ``normalized_bytes`` is written to
      ``<run_dir>/normalized/<scenario_id>.json`` verbatim
      (P0-2: byte-for-byte equality with the canonicalizer
      return value).
    * ``normalized_value`` is the structured form passed to
      :func:`compare_outputs` for the comparison pass.
    """

    raw_value: object
    normalized_bytes: bytes
    normalized_value: object


# D10 default fixture payload. The INVARIANT is that the FIRST
# missing required field of the declared calculation type
# (``CalculationType.INVESTMENT``) is ``"total_area_m2"`` per
# the C-2 contract. The fixture deliberately omits
# ``total_area_m2`` but includes all subsequent INVESTMENT
# required fields so that the missing-field check fires on
# the FIRST slot. The function under test
# (:func:`project_calculator_input`) raises
# :class:`InvalidProjectInputError` with
# ``code=PROJ_INPUT_INVALID`` and ``field="total_area_m2"``.
_D10_INVALID_BLOCKED_DEFAULT_RAW_INPUTS: dict[str, object] = {
    # ``total_area_m2`` is intentionally OMITTED — it is the
    # FIRST missing field per the C-2 contract.
    "refrigerated_area_m2": "150.0",
    "frozen_area_m2": "0.0",
    "position_count": 30,
    "total_power_kw": "200.0",
}


def execute_d10_pure(
    *,
    scenario: ScenarioDeclaration,
    expected_class: type[BaseException],
) -> None:
    """Execute the D10 pure projection function with the default
    fixture payload and assert the typed exception.

    The default fixture payload is
    :data:`_D10_INVALID_BLOCKED_DEFAULT_RAW_INPUTS`, which
    deliberately omits ``total_area_m2`` (the FIRST
    required field of ``CalculationType.INVESTMENT`` per
    the production projection). The production function
    raises :class:`InvalidProjectInputError` with
    ``code=PROJ_INPUT_INVALID`` and ``field="total_area_m2"``.

    Parameters
    ----------
    scenario:
        The V1 scenario declaration. The function uses the
        ``scenario_id`` for the actor / the trace-id
        fields and the scenario's typed backend identity
        (read via the C-2 factory on
        :class:`ScenarioDeclaration`) for the projection's
        backend marker.
    expected_class:
        The expected exception class (looked up from
        :data:`V1_EXCEPTION_REGISTRY` in
        :mod:`cold_storage.evaluation.evaluate`). The
        function does NOT re-raise; the caller's
        ``except expected_class`` block handles the match.

    Raises
    ------
    BaseException
        The production-side exception (typed) is allowed to
        propagate. The runner's :func:`evaluate_manifest`
        catches it and matches on its typed ``code`` and
        ``field`` attributes.
    """
    # Lazy import: avoid a hard dependency on the production
    # modules at module-load time (the production modules are
    # not required for unit tests that only exercise
    # canonicalization / comparison).
    from cold_storage.modules.orchestration.application.production_calculation.projection import (  # noqa: E501
        project_calculator_input,
    )
    from cold_storage.modules.orchestration.domain.contracts import (
        CalculationType,
    )

    # The production function requires a ``database_backend`` kwarg.
    # Per review 4693931575 P0-5 the architecture guard
    # boundary test authorizes the literal tokens
    # ``database_backend`` and ``correlation_id`` in
    # ``backend/src/cold_storage/evaluation/runners/_executor.py``
    # ONLY at this single call site (the C-2 production-boundary
    # call into ``project_calculator_input`` and
    # ``adapter_execute_scenario``). The two AST-enforced
    # carve-out rules in the Phase-1 architecture boundary
    # test file block:
    #   * any BinOp(Add) string-concatenation bypass for the
    #     two tokens;
    #   * any ``**dict``-spread bypass for the two tokens;
    # so the literal keyword form below is the only legal shape.
    project_calculator_input(
        calculation_type=CalculationType.INVESTMENT,
        raw_inputs=_D10_INVALID_BLOCKED_DEFAULT_RAW_INPUTS,
        actor=f"d10-actor-{scenario.scenario_id}",
        correlation_id=f"d10-corr-{scenario.scenario_id}",
        database_backend=ScenarioDeclaration.get_scenario_backend(scenario).value,
        upstream_calculation_ids=None,
        calculator_name="investment_estimate",
        calculator_version="1.0.0",
    )


def execute_baseline_succeeded(
    *,
    scenario: ScenarioDeclaration,
    session_factory: Callable[[], Any],
) -> BaselineExecutionArtifacts:
    """Execute the production pipeline for a SUCCEEDED scenario
    and return the canonicalized actual output.

    The default implementation goes through the typed A1-2a
    adapter path:

    1. ``adapter.execute_scenario(session_factory, ...,
       trace_id=..., backend_marker=...)`` returns
       an :class:`AdapterResult` carrying the production
       ``SchemeRun`` row.
    2. The :class:`AdapterResult` is normalized via the D1
       canonicalizer to produce deterministic bytes.
    3. The canonical bytes are deserialized back to a JSON
       value for the comparison layer.

    Tests or backend runners that need a different execution
    strategy can override this symbol via ``monkeypatch`` /
    module-level rebinding.

    Parameters
    ----------
    scenario:
        The V1 scenario declaration. The function uses
        ``scenario.scenario_id`` as the actor / correlation
        marker; the real production call is delegated to the
        adapter which uses the bound session_factory.
    session_factory:
        The SQLAlchemy ``sessionmaker`` factory.

    Returns
    -------
    BaselineExecutionArtifacts
        The three typed artifacts (raw production value,
        canonical bytes, structured normalized value) ready
        for the runner's artifact persistence + comparison
        pipeline (per P0-1 / P0-2 of review 4693931575).
    """
    # Lazy import: the production modules and the adapter
    # are not required for unit tests that only exercise
    # canonicalization / comparison.
    from cold_storage.evaluation.adapter import (
        execute_scenario as adapter_execute_scenario,
    )

    if session_factory is None:
        raise EvaluationRunnerError(
            "execute_baseline_succeeded requires a session_factory.",
        )

    # The adapter requires a source_binding_id and
    # weight_set_revision_id FK reference. The default
    # baseline test path uses the canonical A1-2a seed
    # values. Real backend runners (sqlite.py /
    # postgresql.py) seed the database with the A1-2a
    # pre-existing context before invoking the runner.
    backend_value = ScenarioDeclaration.get_scenario_backend(scenario).value
    result = adapter_execute_scenario(
        session_factory,
        source_binding_id="a1-test-binding-001",
        weight_set_revision_id="a1-test-wrev-001",
        correlation_id=f"c2-runner-{scenario.scenario_id}",
        database_backend=backend_value,
    )
    # The AdapterResult is converted to a JSON-domain
    # value via Pydantic model_dump (typed, no
    # side effects). The result is then canonicalized
    # via the D1 canonicalizer to produce deterministic
    # bytes; the bytes are deserialized back to a JSON
    # value (the runner never compares bytes directly; the
    # comparison layer compares structured values).
    import json

    # The ``SchemeRun`` domain object exposes its data via the
    # Pydantic v2 ``model_dump`` interface; the strict-JSON
    # canonicalizer accepts the result. ``mode="python"``
    # preserves Python-domain types (``Decimal`` etc.) for
    # the canonicalizer; ``mode="json"`` is the JSON-domain
    # projection and is reserved for the comparison layer
    # (which only sees JSON-domain values).
    dumped: dict[str, Any] = result.scheme_run.model_dump(mode="python")  # type: ignore[attr-defined]
    # P0-1 of review 4693931575: the ``raw_value`` for the
    # raw artifact is the JSON-domain projection of the live
    # ``AdapterResult.scheme_run`` (Pydantic
    # ``model_dump(mode="json")``). It MUST NOT be derived
    # from ``expected_output`` or any baseline golden value.
    raw_value: dict[str, Any] = result.scheme_run.model_dump(mode="json")  # type: ignore[attr-defined]
    # P0-2 of review 4693931575: the canonicalizer's raw
    # byte output is the SINGLE AUTHORITATIVE byte form of
    # the normalized artifact. The runner persists these
    # exact bytes — never a re-serialization.
    canonical_bytes = canonicalize_production_outputs(dumped, excluded_paths=())
    normalized_value = json.loads(canonical_bytes)
    return BaselineExecutionArtifacts(
        raw_value=raw_value,
        normalized_bytes=canonical_bytes,
        normalized_value=normalized_value,
    )


__all__ = [
    "BaselineExecutionArtifacts",
    "execute_baseline_succeeded",
    "execute_d10_pure",
]
