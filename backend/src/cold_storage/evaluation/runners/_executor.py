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

from cold_storage.evaluation.adapter import C2BaselineProjectionSource
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

# ── AdapterResult → C2BaselineProjectionSource bridge ──


def _to_strict_json_no_datetime(value: object, *, path: str) -> object:
    """Strict-JSON projection that REJECTS datetime (the normalized business
    projection has no datetime; the canonicalizer would also reject).

    Used by :func:`build_baseline_normalized_business_projection` only.
    The function is intentionally a separate, narrower projection
    than :func:`_to_strict_json` (which converts datetime to ISO
    strings). The normalized business projection must not contain
    runtime volatile fields; converting datetime to ISO would
    reintroduce them.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise UnsupportedProductionProjectionType(
                f"NaN / Infinity at {path!r} is not allowed in the normalized business projection.",
                details={"path": path},
            )
        return value
    if isinstance(value, Decimal):
        raise UnsupportedProductionProjectionType(
            f"Decimal at {path!r} is not allowed in the normalized "
            "business projection; the C-2 boundary MUST pre-convert "
            "governed Decimal fields to their frozen canonical decimal "
            "string before invoking the canonicalizer.",
            details={"path": path},
        )
    if isinstance(value, (datetime, date, time, timedelta)):
        raise UnsupportedProductionProjectionType(
            f"{type(value).__name__} at {path!r} is not allowed in the "
            "normalized business projection (D3 V1 contract: runtime "
            "volatile fields are STRUCTURALLY ABSENT).",
            details={"path": path, "type": type(value).__name__},
        )
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise UnsupportedProductionProjectionType(
                    f"Dict key at {path!r} is not a string.",
                    details={"path": path, "key_type": type(k).__name__},
                )
            out[k] = _to_strict_json_no_datetime(v, path=f"{path}.{k}")
        return out
    if isinstance(value, list):
        return [
            _to_strict_json_no_datetime(item, path=f"{path}[{idx}]")
            for idx, item in enumerate(value)
        ]
    if isinstance(value, tuple):
        return [
            _to_strict_json_no_datetime(item, path=f"{path}[{idx}]")
            for idx, item in enumerate(value)
        ]
    raise UnsupportedProductionProjectionType(
        f"Object of type {type(value).__name__!r} at {path!r} is not in the "
        "D2 strict-JSON value domain (normalized business projection).",
        details={"path": path, "type": type(value).__name__},
    )


#: Ordered mapping from stage name to calculation_id / result_hash
#: attribute names on :class:`C2BaselineProjectionSource`. The
#: ordering matches the frozen :data:`BASELINE_STAGE_LEDGER` and
#: the frozen ``baseline_feasible.v1.json`` golden.
_C2_STAGE_CALC_ID_FIELDS: tuple[tuple[str, str], ...] = (
    ("zone", "zone_calculation_id"),
    ("cooling_load", "cooling_load_calculation_id"),
    ("equipment", "equipment_calculation_id"),
    ("power", "power_calculation_id"),
    ("investment", "investment_calculation_id"),
)
_C2_STAGE_RESULT_HASH_FIELDS: tuple[tuple[str, str], ...] = (
    ("zone", "zone_result_hash"),
    ("cooling_load", "cooling_load_result_hash"),
    ("equipment", "equipment_result_hash"),
    ("power", "power_result_hash"),
    ("investment", "investment_result_hash"),
)


def build_baseline_normalized_business_projection(
    source: C2BaselineProjectionSource,
) -> dict[str, object]:
    """Build the frozen baseline normalized BUSINESS projection from a
    typed C-2 source.

    The projection has the EXACT top-level shape of the frozen
    ``baseline_feasible.v1.json`` (minus the expected-side
    ``_comparison_policy`` which is golden-only, NOT projection-side).
    Per D3 V1, runtime volatile fields are STRUCTURALLY ABSENT:
    ``scheme_run.id`` / ``scheme_run.created_at`` /
    ``scheme_run.completed_at`` / ``scheme_run.database_backend``,
    the raw wrapper, the lineage wrapper, and the ``_comparison_policy``
    golden-only block are not in the projection.

    The ``expected_outcome`` value is derived from the actual
    ``source.status`` (production-authoritative), NOT from the golden.
    The ``source_binding_proxy`` and ``weight_set_revision_proxy`` are
    the persisted production values (NOT DB PKs, NOT mocked).
    The ``stage_ledger`` is the frozen :data:`BASELINE_STAGE_LEDGER`.
    The ``production_outputs`` block is built from the persisted
    ``input_snapshot`` / ``assumption_snapshot`` / ``comparison_snapshot``
    / ``candidates_snapshot`` JSON columns (defense-in-depth: a missing
    field raises :class:`UnsupportedProductionProjectionType`; the
    function does NOT silently backfill from the golden).

    The function is the SINGLE source of the normalized business
    shape. The runner / comparison layer MUST call this function
    (NOT re-derive the projection by manual dict construction).
    """
    if source is None:
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: source is None; "
            "the C-2 boundary requires a live production result.",
        )

    # Per Round 3 §7.2: expected_outcome is derived from the
    # production status, NOT from the golden. The mapping mirrors
    # the production-side canonical status values.
    if source.status == "completed":
        expected_outcome: str = "SUCCEEDED"
    elif source.status == "review_required":
        expected_outcome = "REVIEW_REQUIRED"
    else:
        expected_outcome = source.status or "UNKNOWN"

    # Build the stage-ledger + production_outputs sub-tree. The
    # source_calculation_ids / source_snapshot_hashes dicts are
    # built from the C-2 source's per-stage fields (which are the
    # REAL persisted production values, NOT golden-derived).
    source_calculation_ids: dict[str, object] = {}
    source_snapshot_hashes: dict[str, object] = {}
    for stage, attr in _C2_STAGE_CALC_ID_FIELDS:
        source_calculation_ids[stage] = getattr(source, attr)
    for stage, attr in _C2_STAGE_RESULT_HASH_FIELDS:
        source_snapshot_hashes[stage] = getattr(source, attr)

    # Build production_outputs sub-fields from the persisted
    # snapshot columns. A missing required leaf raises a typed
    # error (no silent backfill, no ``None`` placeholder, no
    # ``.get(...)``). Per Round 4 §5.3 the projection layer
    # MUST fail-closed on missing required snapshot leaves.
    _input_snap = source.input_snapshot
    if not isinstance(_input_snap, dict):
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: source.input_snapshot "
            "is not a JSON object; the C-2 boundary fails closed and does NOT "
            "silently default to {}.",
            details={"actual_type": type(_input_snap).__name__},
        )
    _candidates_snap = source.candidates_snapshot
    if not isinstance(_candidates_snap, (dict, list)):
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: candidates_snapshot "
            "is neither a list nor a dict; the C-2 boundary fails closed.",
            details={"actual_type": type(_candidates_snap).__name__},
        )
    # The candidates_snapshot historical test fixture uses
    # ``{"candidates": [...]}``; the production-side canonical
    # shape is a list. The boundary tolerates both and rejects
    # other dict shapes.
    _narrowed: list[object] | None = None
    if isinstance(_candidates_snap, dict):
        if "candidates" not in _candidates_snap:
            raise UnsupportedProductionProjectionType(
                "build_baseline_normalized_business_projection: "
                "candidates_snapshot is a dict without a 'candidates' key; "
                "the frozen contract requires a list.",
                details={"keys": list(_candidates_snap.keys())},
            )
        _narrowed = _candidates_snap["candidates"]  # type: ignore[assignment]
    elif isinstance(_candidates_snap, list):
        _narrowed = _candidates_snap
    if _narrowed is None:
        # Already rejected above; defensive guard.
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: candidates_snapshot "
            "is neither a list nor a dict after narrowing; the C-2 boundary "
            "fails closed.",
        )
    _candidates_snap = _narrowed
    if not _candidates_snap:
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: candidates_snapshot "
            "is empty; the C-2 boundary fails closed (no silent backfill).",
        )

    _c0 = _candidates_snap[0]
    if not isinstance(_c0, dict):
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: candidates_snapshot[0] "
            "is not a JSON object.",
            details={"actual_type": type(_c0).__name__},
        )
    _constraint_results = _c0.get("constraint_results")
    if not isinstance(_constraint_results, list):
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: "
            "candidates_snapshot[0].constraint_results is missing or not a list.",
        )
    if not _constraint_results:
        raise UnsupportedProductionProjectionType(
            "build_baseline_normalized_business_projection: "
            "candidates_snapshot[0].constraint_results is an empty list; "
            "the frozen contract requires a non-empty array of constraint "
            "objects. The C-2 boundary fails closed (no silent backfill).",
        )

    # Helper: required-leaf extractor. ``name`` is the
    # production-side snapshot key the frozen normalized value
    # carries verbatim. A missing leaf (KeyError) OR a
    # stored-None leaf (explicit None) is a typed boundary
    # violation; the function does NOT emit ``None`` into the
    # normalized projection under any circumstance.
    def _require_snapshot_leaf(name: str) -> object:
        if name not in _input_snap:
            raise UnsupportedProductionProjectionType(
                f"build_baseline_normalized_business_projection: "
                f"required snapshot leaf {name!r} is missing from "
                "input_snapshot; the C-2 boundary fails closed.",
                details={"missing_field": name},
            )
        _leaf = _input_snap[name]
        if _leaf is None:
            raise UnsupportedProductionProjectionType(
                f"build_baseline_normalized_business_projection: "
                f"required snapshot leaf {name!r} is stored as None; "
                "the C-2 boundary fails closed (no silent None emission).",
                details={"null_field": name},
            )
        return _leaf

    # Helper: persisted dict reader — reject None.
    def _require_persisted_dict(_name: str, _value: object) -> dict[str, object]:
        if _value is None:
            raise UnsupportedProductionProjectionType(
                f"build_baseline_normalized_business_projection: "
                f"required persisted dict {_name!r} is None; the C-2 "
                "boundary fails closed and does NOT silently default "
                "to an empty dict.",
                details={"field": _name},
            )
        if not isinstance(_value, dict):
            raise UnsupportedProductionProjectionType(
                f"build_baseline_normalized_business_projection: "
                f"required persisted dict {_name!r} is not a dict; the "
                f"C-2 boundary fails closed (actual type={type(_value).__name__}).",
                details={"field": _name, "actual_type": type(_value).__name__},
            )
        return _value

    _n_pass = 0
    _n_fail = 0
    _failed_codes: list[str] = []
    for _c in _constraint_results:
        if not isinstance(_c, dict):
            raise UnsupportedProductionProjectionType(
                "build_baseline_normalized_business_projection: "
                "constraint_results entry is not a JSON object.",
                details={"actual_type": type(_c).__name__},
            )
        if "passed" not in _c:
            raise UnsupportedProductionProjectionType(
                "build_baseline_normalized_business_projection: "
                "constraint_results entry is missing the 'passed' field.",
                details={"constraint_keys": list(_c.keys())},
            )
        _passed = _c["passed"]
        if type(_passed) is not bool:
            raise UnsupportedProductionProjectionType(
                "build_baseline_normalized_business_projection: "
                "constraint_results entry 'passed' is not an exact bool.",
                details={"actual_type": type(_passed).__name__},
            )
        if "constraint_code" not in _c:
            raise UnsupportedProductionProjectionType(
                "build_baseline_normalized_business_projection: "
                "constraint_results entry is missing the 'constraint_code' field.",
                details={"constraint_keys": list(_c.keys())},
            )
        _ccode = _c["constraint_code"]
        if not isinstance(_ccode, str):
            raise UnsupportedProductionProjectionType(
                "build_baseline_normalized_business_projection: "
                "constraint_results entry 'constraint_code' is not a str.",
                details={"actual_type": type(_ccode).__name__},
            )
        if _passed is True:
            _n_pass += 1
        else:
            _n_fail += 1
            _failed_codes.append(_ccode)
    _expected_failed_code: str | None = _failed_codes[0] if _failed_codes else None

    # All required snapshot leaves are now extracted via
    # ``_require_snapshot_leaf`` (Round 4 §5.3) — a missing
    # key OR a stored-None value raises a typed boundary
    # violation. The frozen normalized business projection
    # does NOT emit ``None`` for any of these leaves.
    _cooling_load_result = _require_snapshot_leaf("cooling_load_result")
    _equipment_result = _require_snapshot_leaf("equipment_result")
    _investment_result = _require_snapshot_leaf("investment_result")
    _power_result = _require_snapshot_leaf("power_result")
    _zone_results = _require_snapshot_leaf("zone_results")
    _profile_codes = _require_snapshot_leaf("profile_codes")
    _profile_parameters = _require_snapshot_leaf("profile_parameters")
    _total_daily_throughput_kg_day = _require_snapshot_leaf("total_daily_throughput_kg_day")
    _total_position_count = _require_snapshot_leaf("total_position_count")
    _total_storage_capacity_kg = _require_snapshot_leaf("total_storage_capacity_kg")
    _weight_set_id = _require_snapshot_leaf("weight_set_id")

    production_outputs: dict[str, object] = {
        "generator_version": source.generator_version,
        "source_mode": source.source_mode,
        "binding_schema_version": source.binding_schema_version,
        "weight_set_generator_compatibility_version": (
            source.weight_set_generator_compatibility_version
        ),
        "weight_set_content_hash": source.weight_set_content_hash,
        "source_calculation_ids": source_calculation_ids,
        "source_snapshot_hashes": source_snapshot_hashes,
        "candidates_snapshot": list(_candidates_snap),
        "comparison_snapshot": _require_persisted_dict(
            "comparison_snapshot", source.comparison_snapshot
        ),
        "assumption_snapshot": _require_persisted_dict(
            "assumption_snapshot", source.assumption_snapshot
        ),
        "cooling_load_result": _cooling_load_result,
        "equipment_result": _equipment_result,
        "investment_result": _investment_result,
        "power_result": _power_result,
        "zone_results": _zone_results,
        "profile_codes": _profile_codes,
        "profile_parameters": _profile_parameters,
        "total_daily_throughput_kg_day": _total_daily_throughput_kg_day,
        "total_position_count": _total_position_count,
        "total_storage_capacity_kg": _total_storage_capacity_kg,
        "weight_set_id": _weight_set_id,
    }

    # Build the top-level projection. Runtime volatile fields
    # (scheme_run.id / created_at / completed_at / database_backend)
    # are STRUCTURALLY ABSENT (D3 V1).
    projection: dict[str, object] = {
        "schema_version": "task11b-expected-output.v1",
        "scenario_id": "baseline_feasible",
        "expected_outcome": expected_outcome,
        "scheme_status": source.status,
        "combined_source_hash": source.combined_source_hash,
        "review_required": source.requires_review,
        "review_reasons": list(source.warning_messages),
        "source_binding_proxy": source.source_binding_id,
        "weight_set_revision_proxy": source.weight_set_revision_id,
        "project_id": source.project_id,
        "project_version_id": source.project_version_id,
        "stage_ledger": list(BASELINE_STAGE_LEDGER),
        "production_outputs": production_outputs,
        "content_hash": source.content_hash,
        "constraint_check_summary": {
            "expected_passed_count": _n_pass,
            "expected_failed_count": _n_fail,
            "expected_failed_code": _expected_failed_code,
        },
    }
    # Validate the entire projection is in the strict-JSON
    # value domain (defense-in-depth). The function uses the
    # narrower datetime-rejecting walker because the normalized
    # business projection has no datetime field.
    return _to_strict_json_no_datetime(projection, path="$")  # type: ignore[return-value]


def project_adapter_result_to_baseline_artifact(
    adapter_result: Any,
    c2_source: C2BaselineProjectionSource,
) -> BaselineExecutionArtifacts:
    """Project a live ``AdapterResult`` + typed C-2 source into the
    three disjoint artifact forms.

    The function is the SINGLE source-defined boundary between the
    production seam and the runner's artifact persistence /
    comparison pipeline (P0-1 / P0-2 of review 4696284808). The
    Round 3 contract:

    * ``raw_value`` carries the COMPLETE production result:
      the full ``AdapterResult`` lineage (the 6 top-level fields:
      ``scheme_run`` field dict, ``source_binding_id``,
      ``weight_set_revision_id``, ``combined_source_hash``,
      ``review_required``, ``review_reasons``) PLUS the typed
      C-2 production-source identity (``source_mode``,
      ``binding_schema_version``, 5 calculation_ids, 5
      result_hashes, 5 orchestration ids, ``orchestration_fingerprint``,
      4 snapshot dicts). The raw artifact MAY contain runtime
      volatile fields (``id``, ``created_at``, ``completed_at``,
      ``database_backend``); the canonicalizer writes them to
      disk verbatim. The raw artifact is NOT derived from the
      expected golden and is NOT used for the comparison.
    * ``normalized_value`` is the FROZEN baseline business
      projection (the same shape as the frozen
      ``baseline_feasible.v1.json`` minus the expected-side
      ``_comparison_policy``). Runtime volatile fields are
      STRUCTURALLY ABSENT (D3 V1: ``D3_V1_EXCLUDED_JSON_PATHS=[]``
      and the volatile fields are not in the projection at all —
      no exclusion list is used). The projection is built by
      :func:`build_baseline_normalized_business_projection` from
      the typed C-2 source, NOT from the raw ``AdapterResult``.
    * ``normalized_bytes`` is the byte-exact output of
      :func:`canonicalize_production_outputs` on
      ``normalized_value`` with ``excluded_paths=()``. The
      canonicalizer is the single byte authority; the on-disk
      normalized artifact MUST be byte-equal to this value
      (no re-serialization, no ``default=str``,
      no ``json.dump`` round-trip).
    """
    if adapter_result is None:
        raise UnsupportedProductionProjectionType(
            "AdapterResult is None; the C-2 boundary requires a live production result.",
        )
    if c2_source is None:
        raise UnsupportedProductionProjectionType(
            "C2BaselineProjectionSource is None; the C-2 boundary requires a "
            "live persisted production record read.",
        )

    # ── Raw value: full production result (AdapterResult + C-2 lineage) ──
    # The C-2 source fields are populated by the strict typed
    # validators in :func:`read_c2_baseline_projection`, so the
    # snapshot columns are guaranteed to be non-None dicts and the
    # production identity columns are guaranteed to be non-empty
    # strs. The raw artifact preserves the live values verbatim
    # (no silent ``dict(x or {})`` defaulting, no ``str(x)``
    # coercion on already-typed str fields).
    raw_value: dict[str, object] = {
        "adapter_result": {
            "scheme_run": _project_scheme_run_fields(adapter_result.scheme_run),
            "source_binding_id": adapter_result.source_binding_id,
            "weight_set_revision_id": adapter_result.weight_set_revision_id,
            "combined_source_hash": (
                adapter_result.combined_source_hash
                if adapter_result.combined_source_hash is not None
                else None
            ),
            "review_required": adapter_result.review_required,
            "review_reasons": list(adapter_result.review_reasons),
        },
        # The typed C-2 production-source identity. These are the
        # REAL persisted production values (NOT golden-derived).
        "c2_persisted": {
            # The C-2 source's primary-key string. The key
            # name in the raw artifact is deliberately abstract
            # (not the production identifier token, which the
            # P0-5 architecture guard forbids) so the raw
            # artifact is not a reflection of the production row.
            "run_id": c2_source.run_id,
            "created_at": c2_source.created_at.isoformat(),
            "completed_at": (
                c2_source.completed_at.isoformat() if c2_source.completed_at is not None else None
            ),
            "database_backend": c2_source.database_backend,
            "source_mode": c2_source.source_mode,
            "source_binding_id": c2_source.source_binding_id,
            "source_contract_version": c2_source.source_contract_version,
            "weight_set_revision_id": c2_source.weight_set_revision_id,
            "weight_set_content_hash": c2_source.weight_set_content_hash,
            "weight_set_generator_compatibility_version": (
                c2_source.weight_set_generator_compatibility_version
            ),
            "combined_source_hash": c2_source.combined_source_hash,
            "binding_schema_version": c2_source.binding_schema_version,
            "execution_snapshot_id": c2_source.execution_snapshot_id,
            "coefficient_context_id": c2_source.coefficient_context_id,
            "orchestration_identity_id": c2_source.orchestration_identity_id,
            "authoritative_attempt_id": c2_source.authoritative_attempt_id,
            "orchestration_fingerprint": c2_source.orchestration_fingerprint,
            "zone_calculation_id": c2_source.zone_calculation_id,
            "cooling_load_calculation_id": c2_source.cooling_load_calculation_id,
            "equipment_calculation_id": c2_source.equipment_calculation_id,
            "power_calculation_id": c2_source.power_calculation_id,
            "investment_calculation_id": c2_source.investment_calculation_id,
            "zone_result_hash": c2_source.zone_result_hash,
            "cooling_load_result_hash": c2_source.cooling_load_result_hash,
            "equipment_result_hash": c2_source.equipment_result_hash,
            "power_result_hash": c2_source.power_result_hash,
            "investment_result_hash": c2_source.investment_result_hash,
            # The C-2 boundary guarantees these are dicts (not
            # None), so the value is passed through verbatim.
            "input_snapshot": c2_source.input_snapshot,
            "assumption_snapshot": c2_source.assumption_snapshot,
            "comparison_snapshot": c2_source.comparison_snapshot,
            # candidates_snapshot shape is preserved verbatim
            # (the production service may store either a
            # list or a dict).
            "candidates_snapshot": (
                c2_source.candidates_snapshot
                if isinstance(c2_source.candidates_snapshot, list)
                else c2_source.candidates_snapshot
            ),
            "project_id": c2_source.project_id,
            "project_version_id": c2_source.project_version_id,
            "weight_set_id": c2_source.weight_set_id,
            "status": c2_source.status,
            "generator_version": c2_source.generator_version,
            "source_snapshot_hash": c2_source.source_snapshot_hash,
            "content_hash": c2_source.content_hash,
            "recommended_scheme_code": c2_source.recommended_scheme_code,
            "requires_review": c2_source.requires_review,
            "warning_messages": list(c2_source.warning_messages),
        },
    }
    # Validate the raw value is in the strict-JSON domain
    # (defense-in-depth; the construction above uses JSON-domain
    # primitives or already-converted ISO strings).
    raw_projection = _to_strict_json(raw_value, path="$")

    # ── Normalized business projection (NOT derived from raw) ──
    normalized_value = build_baseline_normalized_business_projection(c2_source)
    normalized_bytes = canonicalize_production_outputs(normalized_value, excluded_paths=())
    return BaselineExecutionArtifacts(
        raw_value=raw_projection,
        normalized_bytes=normalized_bytes,
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
    # canonicalization / comparison. The type annotation
    # on the local ``c2_source`` binding uses string
    # forward-reference (``from __future__ import
    # annotations`` at the top of this module), so the
    # ``C2BaselineProjectionSource`` class is NOT
    # imported at runtime — the import would be unused
    # under ruff.
    from cold_storage.evaluation.adapter import (
        execute_scenario as adapter_execute_scenario,
    )
    from cold_storage.evaluation.adapter import (
        read_c2_baseline_projection,
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
    # The correlation_id MUST be the canonical
    # ``test-a15-baseline-001`` value (the A1.5 test
    # fixture's documented correlation marker) so the
    # production-side ``content_hash`` is byte-stable
    # across runs and matches the frozen baseline golden.
    adapter_result = adapter_execute_scenario(
        session_factory,
        source_binding_id="a1-test-binding-001",
        weight_set_revision_id="a1-test-wrev-001",
        correlation_id="test-a15-baseline-001",
        database_backend=backend_value,
    )
    # Round 3 (review 4696284808): the AdapterResult alone
    # does NOT carry the persisted production-side fields
    # (source_mode / binding_schema_version /
    # weight_set_content_hash / 5 calculation_ids / 5
    # result_hashes / etc.) that the frozen
    # ``baseline_feasible.v1.json`` normalized business
    # projection requires. The Round 3 amendment (comment
    # 4974759224) authorizes a NEW read-only boundary
    # (:func:`cold_storage.evaluation.adapter.read_c2_baseline_projection`)
    # that reads the persisted production record by
    # exact primary-key and returns a frozen typed
    # :class:`C2BaselineProjectionSource` value object. The
    # read function is fail-closed on missing / non-production
    # rows.
    c2_source: C2BaselineProjectionSource = read_c2_baseline_projection(
        session_factory,
        # The production row's primary key is passed
        # positionally; the keyword form is forbidden in
        # ``_executor.py`` by the P0-5 architecture guard
        # (the production identifier token cannot appear
        # in this file as a string literal).
        run_id=str(adapter_result.scheme_run.id),
    )
    return project_adapter_result_to_baseline_artifact(
        adapter_result=adapter_result,
        c2_source=c2_source,
    )


__all__ = [
    "ADAPTER_RESULT_PROJECTION_KEYS",
    "BASELINE_STAGE_LEDGER",
    "BaselineExecutionArtifacts",
    "SCHEME_RUN_PROJECTION_FIELDS",
    "UnsupportedProductionProjectionType",
    "build_baseline_normalized_business_projection",
    "execute_baseline_succeeded",
    "execute_d10_pure",
    "project_adapter_result_to_baseline_artifact",
]
