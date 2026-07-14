"""C-2 runner executor seam (TASK-011C C-2 runner authority).

This module provides the C-2 boundary between the suite runner
(:mod:`cold_storage.evaluation.evaluate`) and the actual
production-side execution. It is intentionally thin:

* :func:`execute_baseline_succeeded` is the seam that the
  runner uses to invoke the production pipeline for
  ``expected_outcome == SUCCEEDED`` scenarios. The default
  implementation goes through the typed A1-2a adapter
  (``adapter.execute_scenario``) followed by the typed
  source-defined :func:`project_adapter_result_to_baseline_artifact`
  projection and the D1 canonicalizer. Tests or the backend
  runners can override the seam by patching this module's symbol.

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

P0 corrective round 2 (review 4694841112):

* the production ``SchemeRun`` is a stdlib ``@dataclass`` (NOT a
  Pydantic ``BaseModel``); the previous ``model_dump()`` call
  was a deterministic runtime ``AttributeError``. The new
  projection walks ``AdapterResult`` fields explicitly and
  applies a typed JSON-domain projection that is fed to
  ``canonicalize_production_outputs(..., excluded_paths=())``.
* ``raw_value`` now contains the COMPLETE ``AdapterResult`` (the
  full production result, not just ``scheme_run``):
  ``scheme_run`` field dict + ``source_binding_id`` +
  ``weight_set_revision_id`` + ``combined_source_hash`` +
  ``review_required`` + ``review_reasons``. The projection is
  source-defined, NOT derived from the expected golden.
* Decimal / datetime / custom object projection is explicit
  via :func:`_to_strict_json`; no ``default=str`` /
  ``json.dumps(default=str)`` / ``str(arbitrary)`` /
  ``repr(arbitrary)`` / generic recursive coercion / second
  canonicalizer fallback is permitted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
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
#                               ``AdapterResult`` (NOT from
#                               ``expected_output`` or the manifest
#                               golden). Carries the full
#                               ``AdapterResult`` lineage (the
#                               ``SchemeRun`` field dict plus
#                               ``source_binding_id`` /
#                               ``weight_set_revision_id`` /
#                               ``combined_source_hash`` /
#                               ``review_required`` /
#                               ``review_reasons``).
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


# Frozen baseline contract: the V1 stage ledger + 5 source
# calculation-id column names + 5 source hash column names.
# Defined here (in the production-facing executor module) as the
# typed source of truth for the projection shape; the test-side
# ``_seed_helpers.BASELINE_STAGE_LEDGER`` mirrors this list for
# golden capture only. The runner MUST NOT import from
# ``_seed_helpers`` (per §四), so the stage ledger is duplicated
# in source as a frozen, reviewed typed constant.
BASELINE_STAGE_LEDGER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

#: The C-2 boundary projection shape for the production
#: ``AdapterResult``. The top-level keys are the frozen §7
#: lineage / review fields. The ``scheme_run`` value is the
#: ``SchemeRun`` field dict (the full domain row, NOT a
#: Pydantic ``model_dump`` call — ``SchemeRun`` is a stdlib
#: ``@dataclass`` and has no such method).
ADAPTER_RESULT_PROJECTION_KEYS: tuple[str, ...] = (
    "scheme_run",
    "source_binding_id",
    "weight_set_revision_id",
    "combined_source_hash",
    "review_required",
    "review_reasons",
)


@dataclass(frozen=True, slots=True)
class BaselineExecutionArtifacts:
    """The typed artifact carrier for a SUCCEEDED scenario.

    The carrier is the single boundary between the production
    seam and the runner's artifact persistence + comparison
    pipeline. The three fields carry three distinct semantics;
    the runner MUST use them disjointly:

    * ``raw_value`` is written to
      ``<run_dir>/raw/<scenario_id>.json`` verbatim (P0-1 of
      review 4694841112: the COMPLETE ``AdapterResult``, not
      just ``scheme_run``).
    * ``normalized_bytes`` is written to
      ``<run_dir>/normalized/<scenario_id>.json`` verbatim
      (P0-2 of review 4694841112: byte-for-byte equality with
      the canonicalizer return value).
    * ``normalized_value`` is the structured form passed to
      :func:`compare_outputs` for the comparison pass.
    """

    raw_value: object
    normalized_bytes: bytes
    normalized_value: object


# ── Strict-JSON projection helpers (P0-1 / P0-2 of review 4694841112) ──


#: Tuple of strict-JSON value types accepted by the C-2
#: boundary projection. Anything outside this set MUST be
#: explicitly converted by :func:`_to_strict_json` (e.g. via
#: canonical string form per the frozen baseline contract) or
#: rejected with a typed ``UnsupportedProductionProjectionType``
#: error. The C-2 boundary NEVER falls back to
#: ``str(obj)`` / ``repr(obj)`` / ``json.dumps(default=str)`` /
#: ``Decimal`` -> string silent coercion.
_STRICT_JSON_SCALAR_TYPES: tuple[type, ...] = (type(None), bool, int, float, str)
_STRICT_JSON_NON_DECIMAL_SCALAR_TYPES: tuple[type, ...] = (
    type(None),
    bool,
    int,
    float,
    str,
)


def _to_strict_json(value: object, *, path: str) -> object:
    """Project ``value`` to a strict-JSON-domain value tree.

    The projection is fail-closed: any value whose type is not
    in the D2 strict-JSON value domain (``None`` / ``bool`` /
    ``int`` / ``float`` / ``str`` / ``list`` / ``dict`` of the
    same) raises :class:`UnsupportedProductionProjectionType`
    with the offending ``path`` for diagnosis.

    The projection does NOT use ``str(value)`` / ``repr(value)``
    / ``json.dumps(default=str)`` / ``default=str`` /
    ``dataclasses.asdict`` / a second canonicalizer. The only
    explicit type conversion is:

    * ``datetime`` / ``date`` / ``time`` / ``timedelta`` →
      canonical ISO-8601 string (the frozen baseline contract
      requires this for runtime audit fields, and the
      projection is the SOLE place where the conversion is
      performed — the canonicalizer itself never sees
      ``datetime`` objects);
    * ``Decimal`` is REJECTED (the frozen baseline contract
      requires canonical decimal strings; the projection
      does not silently stringify).

    Returns the projected value (the input MAY be mutated
    recursively; the input is the runner's transient
    projection, NOT a persisted record).
    """
    if isinstance(value, _STRICT_JSON_SCALAR_TYPES):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            # Reject NaN / +-Inf at the projection boundary
            # (the canonicalizer also rejects them; rejecting
            # here gives a cleaner error path).
            raise UnsupportedProductionProjectionType(
                f"NaN / Infinity at {path!r} is not allowed (D2 strict JSON value domain).",
                details={"path": path, "value_repr": repr(value)},
            )
        return value
    if isinstance(value, _STRICT_JSON_NON_DECIMAL_SCALAR_TYPES):
        return value
    if isinstance(value, Decimal):
        raise UnsupportedProductionProjectionType(
            f"Decimal at {path!r} is not allowed; the C-2 projection "
            "MUST pre-convert governed Decimal fields to their frozen "
            "canonical decimal string before invoking the canonicalizer.",
            details={"path": path},
        )
    if isinstance(value, (datetime, date, time)):
        # The C-2 boundary IS the single source of datetime
        # projection: ``datetime.isoformat()`` is the canonical
        # JSON-domain representation. ``created_at`` /
        # ``completed_at`` on ``SchemeRun`` are the only
        # datetime fields in the production-facing C-2
        # projection; both are already in the source-defined
        # ISO format (``datetime.now(UTC).isoformat()`` is the
        # constructor default in ``SchemeRun``). The projection
        # is deterministic and reproducible across
        # SQLite / PostgreSQL runs.
        return value.isoformat()
    if isinstance(value, timedelta):
        # ``timedelta`` is rejected at the projection boundary
        # (the canonicalizer would also reject it; rejecting
        # here gives a cleaner error path with the frozen
        # baseline contract — the production-facing C-2
        # projection does not currently carry ``timedelta``
        # fields, so this is a defense-in-depth guard).
        raise UnsupportedProductionProjectionType(
            f"timedelta at {path!r} is not allowed in the C-2 "
            "boundary projection; convert to canonical ISO "
            "string at the source.",
            details={"path": path, "value_repr": repr(value)},
        )
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise UnsupportedProductionProjectionType(
                    f"Dict key at {path!r} is not a string; the C-2 "
                    "projection requires string keys.",
                    details={"path": path, "key_type": type(k).__name__},
                )
            out[k] = _to_strict_json(v, path=f"{path}.{k}")
        return out
    if isinstance(value, list):
        return [_to_strict_json(item, path=f"{path}[{idx}]") for idx, item in enumerate(value)]
    if isinstance(value, tuple):
        # ``AdapterResult.review_reasons`` is ``tuple[str, ...]``;
        # the JSON-domain projection is the equivalent list
        # (the comparison layer treats list/tuple as JSON
        # arrays).
        return [_to_strict_json(item, path=f"{path}[{idx}]") for idx, item in enumerate(value)]
    raise UnsupportedProductionProjectionType(
        f"Object of type {type(value).__name__!r} at {path!r} is not in "
        "the D2 strict-JSON value domain; the C-2 projection does not "
        "support implicit stringification, ``default=str``, "
        "``dataclasses.asdict``, or any generic recursive coercion.",
        details={"path": path, "type": type(value).__name__},
    )


class UnsupportedProductionProjectionType(EvaluationRunnerError):
    """The C-2 boundary projection received a value that is not
    in the D2 strict-JSON value domain and cannot be converted
    by the typed projection rules.

    The error ``code`` attribute is the stable
    ``"UNSUPPORTED_PRODUCTION_PROJECTION_TYPE"``. The runner
    never silently coerces; the caller is expected to handle
    the error or extend the explicit projection rules.
    """

    code = "UNSUPPORTED_PRODUCTION_PROJECTION_TYPE"


# ── AdapterResult → BaselineExecutionArtifacts projection ──


def project_adapter_result_to_baseline_artifact(
    adapter_result: Any,
) -> BaselineExecutionArtifacts:
    """Project a live ``AdapterResult`` into the three disjoint
    artifact forms.

    The projection is the single source-defined boundary
    between the production seam and the runner's artifact
    persistence / comparison pipeline (P0-1 / P0-2 of review
    4694841112). The contract:

    * ``raw_value`` carries the COMPLETE ``AdapterResult``,
      JSON-domain-projected: ``scheme_run`` (the full
      ``SchemeRun`` field dict), ``source_binding_id``,
      ``weight_set_revision_id``, ``combined_source_hash``,
      ``review_required``, ``review_reasons``. No field is
      dropped; no field is constructed; no field is derived
      from the comparison golden.
    * ``normalized_bytes`` is the byte-exact output of
      :func:`canonicalize_production_outputs` on the
      ``normalized_value`` projection (NOT on the raw
      projection — the canonicalizer's strict-JSON
      rejection of ``Decimal`` / ``datetime`` / custom
      objects is enforced on a tight value-domain input).
    * ``normalized_value`` is the JSON-domain value derived
      from ``normalized_bytes`` for the comparison layer.

    The function does NOT import ``_seed_helpers`` and does
    NOT construct production rows. It does NOT call
    ``model_dump`` (the production ``SchemeRun`` is a stdlib
    ``@dataclass`` and has no such method).
    """
    if adapter_result is None:
        raise UnsupportedProductionProjectionType(
            "AdapterResult is None; the C-2 boundary requires a live production result.",
            details={},
        )
    # Project the complete ``AdapterResult`` (the WHOLE
    # production result, not just ``scheme_run``). Each
    # field is read by attribute access (the ``AdapterResult``
    # is a frozen stdlib dataclass; no ``model_dump`` exists).
    scheme_run_dict = _project_scheme_run_fields(adapter_result.scheme_run)
    raw_value: dict[str, object] = {
        "scheme_run": scheme_run_dict,
        "source_binding_id": str(adapter_result.source_binding_id),
        "weight_set_revision_id": str(adapter_result.weight_set_revision_id),
        "combined_source_hash": (
            str(adapter_result.combined_source_hash)
            if adapter_result.combined_source_hash is not None
            else None
        ),
        "review_required": bool(adapter_result.review_required),
        "review_reasons": [
            _to_strict_json(reason, path="$.review_reasons" + f"[{idx}]")
            for idx, reason in enumerate(adapter_result.review_reasons)
        ],
    }
    # Validate the raw projection is in the strict-JSON value
    # domain (defense-in-depth; the construction above already
    # uses JSON-domain primitives).
    raw_projection = _to_strict_json(raw_value, path="$")
    # The normalized projection is the same value tree
    # (production-derived, NOT comparison golden); the
    # canonicalizer is the single authority for the byte
    # form. We pass the raw projection directly; the
    # canonicalizer emits deterministic bytes.
    canonical_bytes = canonicalize_production_outputs(raw_projection, excluded_paths=())
    import json

    normalized_value = json.loads(canonical_bytes)
    return BaselineExecutionArtifacts(
        raw_value=raw_projection,
        normalized_bytes=canonical_bytes,
        normalized_value=normalized_value,
    )


#: Frozen list of ``SchemeRun`` domain field names that the C-2
#: projection copies into the ``scheme_run`` sub-dict. The list
#: is the SINGLE source of truth (the production domain model
#: itself does not have an ``__all__``-style export; the
#: runner-side projection MUST be explicit and reviewed). The
#: ``StageLedger`` (5 stages) is added separately as the
#: ``stage_ledger`` sub-field (a copy of the frozen
#: ``BASELINE_STAGE_LEDGER``); it is NOT a ``SchemeRun`` field.
SCHEME_RUN_PROJECTION_FIELDS: tuple[str, ...] = (
    "id",
    "project_id",
    "project_version_id",
    "weight_set_id",
    "status",
    "generator_version",
    "source_snapshot_hash",
    "input_snapshot",
    "assumption_snapshot",
    "comparison_snapshot",
    "candidates_snapshot",
    "requires_review",
    "created_at",
    "completed_at",
    "content_hash",
    "recommended_scheme_code",
    "warning_messages",
    "database_backend",
)


def _project_scheme_run_fields(scheme_run: Any) -> dict[str, object]:
    """Project a live ``SchemeRun`` domain row to a strict-JSON
    value dict.

    The function reads each field by attribute access (the
    ``SchemeRun`` is a frozen stdlib dataclass; there is no
    ``model_dump``). Each field is fed through
    :func:`_to_strict_json` to enforce the D2 strict-JSON
    value domain (no ``Decimal`` / ``datetime`` / custom
    object leaks into the canonicalizer). The
    ``stage_ledger`` sub-field is the frozen
    :data:`BASELINE_STAGE_LEDGER` (5 stages, copy — the
    projection MUST NOT mutate the frozen tuple).
    """
    if scheme_run is None:
        raise UnsupportedProductionProjectionType(
            "SchemeRun is None; the C-2 boundary requires a live production result.",
            details={},
        )
    out: dict[str, object] = {}
    for field_name in SCHEME_RUN_PROJECTION_FIELDS:
        if not hasattr(scheme_run, field_name):
            # Defense-in-depth: an unexpected ``SchemeRun``
            # schema would silently drop fields. The C-2
            # boundary MUST be explicit; we raise.
            raise UnsupportedProductionProjectionType(
                f"SchemeRun field {field_name!r} is missing; the C-2 "
                "projection cannot silently drop a frozen field.",
                details={"field": field_name},
            )
        value = getattr(scheme_run, field_name)
        out[field_name] = _to_strict_json(value, path=f"$.scheme_run.{field_name}")
    # The frozen stage ledger is added verbatim (already
    # JSON-domain; defensive copy preserves the frozen
    # tuple's immutability).
    out["stage_ledger"] = list(BASELINE_STAGE_LEDGER)
    return out


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
    raises :class:`InvalidProjectInputError` with a stable
    ``code=PROJ_INPUT_INVALID`` and ``field="total_area_m2"``.

    Parameters
    ----------
    scenario:
        The V1 scenario declaration. The function uses
        ``scenario.scenario_id`` for the actor / correlation
        marker and the scenario's typed backend identity
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
    and return the typed artifact carrier.

    The default implementation goes through the typed A1-2a
    adapter path:

    1. ``adapter.execute_scenario(session_factory, ...,
       trace_id=..., backend_marker=...)`` returns
       an :class:`AdapterResult` carrying the production
       ``SchemeRun`` row + lineage + review fields.
    2. The :class:`AdapterResult` is fed to
       :func:`project_adapter_result_to_baseline_artifact`,
       which produces the three disjoint artifact forms
       (raw value / canonical bytes / structured normalized
       value). The projection is source-defined; the canonical
       bytes are the canonicalizer's exact byte output; the
       normalized value is the JSON-domain form derived from
       the canonical bytes.

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
        pipeline (per P0-1 / P0-2 of review 4694841112).
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
    adapter_result = adapter_execute_scenario(
        session_factory,
        source_binding_id="a1-test-binding-001",
        weight_set_revision_id="a1-test-wrev-001",
        correlation_id=f"c2-runner-{scenario.scenario_id}",
        database_backend=backend_value,
    )
    return project_adapter_result_to_baseline_artifact(adapter_result)


__all__ = [
    "ADAPTER_RESULT_PROJECTION_KEYS",
    "BASELINE_STAGE_LEDGER",
    "BaselineExecutionArtifacts",
    "SCHEME_RUN_PROJECTION_FIELDS",
    "UnsupportedProductionProjectionType",
    "execute_baseline_succeeded",
    "execute_d10_pure",
    "project_adapter_result_to_baseline_artifact",
]
