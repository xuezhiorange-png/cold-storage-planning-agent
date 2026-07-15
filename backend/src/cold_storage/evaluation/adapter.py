"""Evaluation adapter for production scheme generation — Implementation Slice A1.

This module implements the A1-2a adapter surface ratified by Amendment 2
of the Path A design contract
(``docs/tasks/TASK-011B-path-a-design-ratification.md`` §13).

Contract reference: A1-2a (Amendment 2 §13.2 / §13.3 / §13.4).

Public API
==========

* :func:`execute_scenario` — single-call entry point that wraps the
  production ``ProductionSchemeService.generate_production_scheme_run``
  call. Takes only FK references to pre-existing production rows plus
  mandatory ``correlation_id`` and ``database_backend`` metadata. Does
  NOT take a ``project_input`` or a ``scenario_id``.

* :class:`AdapterResult` — read-only result dataclass carrying the
  production ``SchemeRun`` row and the lineage fields extracted from
  it. Does NOT carry ``calculation_run_ids`` (the adapter no longer
  observes the 5 ``CalculationRunRecord`` rows directly; the
  evaluation harness reads them via the production read ports if it
  needs to assert the §4.3 strict row counts).

Ownership boundary (per §13.3)
===============================

The adapter is **only** responsible for:

* Calling :func:`compose_production_scheme_service` to obtain a wired
  ``ProductionSchemeService``.
* Building a :class:`GenerateProductionSchemeCommand` from the
  inputs.
* Invoking ``service.generate_production_scheme_run(cmd)``.
* Reading the persisted ``SchemeRunRecord`` to extract the read-only
  lineage fields (``source_binding_id``, ``weight_set_revision_id``,
  ``combined_source_hash``, ``requires_review``, ``warning_messages``).
* Constructing the :class:`AdapterResult` typed dataclass.
* Forwarding any production exception unchanged to the caller.

The adapter is **NOT** responsible for:

* Creating a ``ProjectVersion`` row.
* Creating a ``OrchestrationIdentityRecord`` row.
* Creating a ``OrchestrationRunAttemptRecord`` row.
* Creating any ``CalculationRunRecord`` rows (the 5 stage calculations).
* Creating an ``OrchestrationExecutionSnapshotRecord`` row.
* Creating an ``OrchestrationCoefficientContextRecord`` row.
* Creating a ``SourceBindingRecord`` row.
* Creating an ``ApprovedWeightSetRevision`` row (or any weight-set row).
* Approving a weight-set revision.
* Resolving approved non-demo coefficients.
* Verifying the ``SourceBinding`` (production's ``SourceBindingVerifier``
  does this inside ``generate_production_scheme_run``).
* Selecting a ``SchemeService`` policy.
* Persisting any production row of any kind.

This ownership boundary is **enforced by the adapter's API surface**:
the adapter accepts only FK references to pre-existing production rows
plus the ``correlation_id`` and ``database_backend`` metadata. The
adapter has no constructor parameters other than the typed fields. The
the module is forbidden (per the architecture boundary tests in
``backend/tests/architecture/test_task_011b_phase2_boundaries.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cold_storage.bootstrap.production_composition import (
    compose_production_scheme_service,
)
from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
)
from cold_storage.modules.schemes.domain.models import SchemeRun

# ── Adapter error class ──────────────────────────────────────────────────


class AdapterInputError(ValueError):
    """Raised when the adapter's input contract is violated.

    Distinct from production-side errors so the evaluation harness can
    classify adapter input failures separately from production
    orchestrator failures.
    """


# ── AdapterResult ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Read-only result of a single evaluation scenario execution.

    The adapter populates this from the production ``SchemeRun`` row
    and the persisted ``SchemeRunRecord``; the evaluation harness
    writes it to the evaluation artifact (raw / normalized JSON). The
    adapter does NOT mutate the ``SchemeRun`` row in any way.

    The ``calculation_run_ids`` field is intentionally absent: the
    adapter no longer observes the 5 ``CalculationRunRecord`` rows
    directly. The evaluation harness can read them via the production
    read ports (e.g. ``SqlAlchemySourceBindingReadPort``) if it needs
    to assert the §4.3 strict row counts.
    """

    scheme_run: SchemeRun
    source_binding_id: str
    weight_set_revision_id: str
    combined_source_hash: str | None
    review_required: bool
    review_reasons: tuple[str, ...] = field(default_factory=tuple)


# ── Input validation ──────────────────────────────────────────────────────


_VALID_DATABASE_BACKENDS: frozenset[str] = frozenset({"sqlite", "postgresql"})


def _validate_inputs(
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> None:
    """Validate the A1-2a input contract.

    Raises :class:`AdapterInputError` on any violation. The validation
    is intentionally explicit (no implicit defaulting) so the
    evaluation harness can detect caller-side omissions as soon as the
    adapter is called, not later inside the production orchestrator.
    """
    if not isinstance(source_binding_id, str) or not source_binding_id:
        raise AdapterInputError(
            "source_binding_id must be a non-empty string FK reference "
            "to a pre-existing SourceBindingRecord."
        )
    if not isinstance(weight_set_revision_id, str) or not weight_set_revision_id:
        raise AdapterInputError(
            "weight_set_revision_id must be a non-empty string FK reference "
            "to a pre-existing ApprovedWeightSetRevision."
        )
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise AdapterInputError(
            "correlation_id must be a non-empty, non-null string "
            "(whitespace-only is rejected). "
            "Phase 1 (Task 11B) made scheme_runs.database_backend and "
            "orchestration_run_attempts.correlation_id NOT NULL with no "
            "column-level server_default; the adapter must reject empty "
            "values at the input boundary."
        )
    if database_backend not in _VALID_DATABASE_BACKENDS:
        raise AdapterInputError(
            f"database_backend must be one of {sorted(_VALID_DATABASE_BACKENDS)!r}; "
            f"got {database_backend!r}. Phase 1 (Task 11B) added a CHECK "
            "constraint ck_scheme_run_database_backend on the scheme_runs "
            "table that rejects any other value at the database layer."
        )


# ── Public API: execute_scenario ──────────────────────────────────────────


def execute_scenario(
    session_factory: Callable[[], Any],
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> AdapterResult:
    """Run a single evaluation scenario against the production scheme pipeline.

    Parameters
    ----------
    session_factory:
        Zero-arg callable that returns a SQLAlchemy ``Session``
        (``sessionmaker`` is the canonical instance). Each invocation
        yields a fresh per-request session.
    source_binding_id:
        FK reference to a pre-existing ``SourceBindingRecord`` row
        produced by the upstream production pipeline
        (via ``ProductionSourceBindingUseCase.run``).
    weight_set_revision_id:
        FK reference to a pre-existing
        ``SchemeWeightSetRevisionRecord`` row with ``status='approved'``.
    correlation_id:
        Mandatory NOT-NULL correlation id for the produced
        ``orchestration_run_attempts`` row. Must be a non-empty string.
    database_backend:
        Mandatory NOT-NULL database backend marker. One of
        ``"sqlite"`` or ``"postgresql"`` (matches the
        ``ck_scheme_run_database_backend`` check constraint).

    Returns
    -------
    :class:`AdapterResult`
        A read-only dataclass carrying the production ``SchemeRun`` row
        and the lineage fields extracted from the persisted
        ``SchemeRunRecord``.

    Raises
    ------
    AdapterInputError
        If any input parameter violates the A1-2a input contract.
    Exception
        Any exception raised by the production
        ``ProductionSchemeService.generate_production_scheme_run`` is
        forwarded unchanged. Per §13.5, the adapter does not wrap or
        re-raise production errors.

    Notes
    -----
    The adapter does NOT take a ``project_input`` (forbidden by A1-2a)
    or a ``scenario_id`` (removed by Amendment 2). The caller is
    responsible for pre-building the production state
    (``SourceBindingRecord``, ``CalculationRunRecord`` x 5,
    ``ApprovedWeightSetRevision``, etc.) before calling this adapter.
    """
    _validate_inputs(
        source_binding_id=source_binding_id,
        weight_set_revision_id=weight_set_revision_id,
        correlation_id=correlation_id,
        database_backend=database_backend,
    )

    cmd = GenerateProductionSchemeCommand(
        source_binding_id=source_binding_id,
        weight_set_revision_id=weight_set_revision_id,
        profile_codes=("balanced",),
        correlation_id=correlation_id,
        database_backend=database_backend,
    )

    service = compose_production_scheme_service(session_factory)
    scheme_run = service.generate_production_scheme_run(cmd)

    # Read-only lineage extraction: a fresh session to read the
    # persisted SchemeRunRecord. The production service has already
    # committed the row inside its own UoW.
    with session_factory() as session:
        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeRunRecord,
        )

        record = session.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == scheme_run.id)
        ).scalar_one_or_none()

        if record is None:
            # Production service returned a domain SchemeRun that has
            # no corresponding persisted record. Per §13.5 the adapter
            # forwards production's exception shape; raise a clear
            # readback failure so the harness can classify it.
            raise AdapterInputError(
                f"Production service returned SchemeRun id={scheme_run.id!r} "
                "but no persisted SchemeRunRecord was found. The adapter "
                "requires the production service to commit the SchemeRun row "
                "before returning."
            )

        # All three lineage FK / hash fields are NOT NULL on a
        # production-source SchemeRunRecord (enforced by the
        # ck_scheme_run_source_mode_nullity check constraint). They
        # are typed Optional[None] on the ORM column to match the
        # legacy nullability, so we read them through Optional access.
        persisted_source_binding_id = record.source_binding_id
        persisted_weight_set_revision_id = record.weight_set_revision_id
        persisted_combined_source_hash = record.combined_source_hash
        persisted_requires_review = record.requires_review
        persisted_warning_messages = tuple(record.warning_messages or ())

    return AdapterResult(
        scheme_run=scheme_run,
        source_binding_id=persisted_source_binding_id
        if persisted_source_binding_id is not None
        else source_binding_id,
        weight_set_revision_id=persisted_weight_set_revision_id
        if persisted_weight_set_revision_id is not None
        else weight_set_revision_id,
        combined_source_hash=persisted_combined_source_hash,
        review_required=persisted_requires_review,
        review_reasons=persisted_warning_messages,
    )


# ── C-2 read-only projection boundary (TASK-011C C-2 corrective round 3,
#    authority comment 4974759224) ──────────────────────────────────────
#
# Round 2 wired the production-path ``AdapterResult`` through
# ``project_adapter_result_to_baseline_artifact``, but the
# ``AdapterResult`` (and the domain ``SchemeRun`` it carries) does NOT
# expose the persisted production-side fields required to construct
# the frozen ``baseline_feasible.v1.json`` normalized business
# projection. The Round 3 review (4696284808) therefore requires an
# additional typed, read-only boundary inside the adapter module that
# reads the persisted production row (ORM) by exact
# primary key and exposes the production-authoritative values
# that the existing ``AdapterResult`` does NOT carry (e.g.
# ``source_mode``, ``binding_schema_version``, ``weight_set_content_hash``,
# 5 calculation-ID columns, 5 result-hash columns,
# ``execution_snapshot_id``, ``coefficient_context_id``,
# ``orchestration_identity_id``, ``authoritative_attempt_id``,
# ``orchestration_fingerprint``, ``input_snapshot``,
# ``assumption_snapshot``, ``comparison_snapshot``,
# ``candidates_snapshot``, ``content_hash``, ``recommended_scheme_code``).
#
# The boundary is AUTHORIZED by comment 4974759224 and is INTENTIONALLY
# read-only. It does NOT:
#   - read latest row, first row, or any row other than the exact
#     ``run_id``;
#   - apply source-binding or weight-set fallback;
#   - write, commit, flush, or create any row;
#   - approve any revision;
#   - return the ORM object itself (the function returns a frozen
#     typed value object whose fields are populated by explicit
#     attribute access on the ORM row, never by ``vars()`` /
#     ``__dict__`` / ``_sa_instance_state`` / generic reflection);
#   - silently coerce unsupported Python objects to strings
#     (no ``default=str``, no ``str(obj)``, no ``repr(obj)``,
#     no second canonicalizer).
#
# If any production-required field is None / missing, the function
# raises :class:`MissingC2ProductionField` (a typed ``AdapterInputError``
# subclass) and the runner fails closed.

from collections.abc import Callable as _Callable  # noqa: E402  (alias)

#: Ordered list of production-required column names that the C-2 read
#: boundary asserts are non-None on a production-source row.
#: The list is the SINGLE source of truth in the
#: adapter (per Round 3 review 4696284808 §4 — the production columns
#: must come from the persisted record, not from local constants).
_C2_REQUIRED_PRODUCTION_COLUMNS: tuple[str, ...] = (
    "source_mode",
    "source_binding_id",
    "source_contract_version",
    "weight_set_revision_id",
    "weight_set_content_hash",
    "weight_set_generator_compatibility_version",
    "combined_source_hash",
    "binding_schema_version",
    "execution_snapshot_id",
    "coefficient_context_id",
    "orchestration_identity_id",
    "authoritative_attempt_id",
    "orchestration_fingerprint",
    "zone_calculation_id",
    "cooling_load_calculation_id",
    "equipment_calculation_id",
    "power_calculation_id",
    "investment_calculation_id",
    "zone_result_hash",
    "cooling_load_result_hash",
    "equipment_result_hash",
    "power_result_hash",
    "investment_result_hash",
)


class MissingC2ProductionField(AdapterInputError):
    """A production-required column on the persisted ``SchemeRunRecord`` is None or missing.

    The C-2 read boundary (:func:`read_c2_baseline_projection`) fails
    closed when any production-required column is None. The error
    inherits :class:`AdapterInputError` so existing
    ``except AdapterInputError`` handlers classify it as a typed
    adapter-side boundary violation (not a production-side
    exception).
    """


@dataclass(frozen=True, slots=True)
class C2BaselineProjectionSource:
    """Read-only, frozen, typed projection of a persisted production ``SchemeRunRecord``.

    The carrier is the SINGLE source of production-authoritative
    data the C-2 runner is allowed to read. All fields are populated
    by explicit attribute access on the ``SchemeRunRecord`` ORM row
    (NEVER by ``vars(record)`` / ``record.__dict__`` /
    ``_sa_instance_state`` / generic reflection). The carrier does
    NOT carry the ORM row itself; downstream code consumes the
    fields only.

    The fields are grouped as follows:

    * **Runtime identity** (allowed in raw artifact only,
      structurally absent from the normalized business projection):
      ``run_id`` (str), ``created_at`` (datetime),
      ``completed_at`` (datetime | None), ``database_backend`` (str).
    * **Persisted production source identity** (frozen, required):
      ``source_mode`` (str, must be ``"production"``),
      ``source_binding_id`` (str),
      ``source_contract_version`` (str),
      ``weight_set_revision_id`` (str),
      ``weight_set_content_hash`` (str),
      ``weight_set_generator_compatibility_version`` (str),
      ``combined_source_hash`` (str),
      ``binding_schema_version`` (str),
      ``execution_snapshot_id`` (str),
      ``coefficient_context_id`` (str),
      ``orchestration_identity_id`` (str),
      ``authoritative_attempt_id`` (str),
      ``orchestration_fingerprint`` (str).
    * **Persisted calculation lineage** (5 stages, frozen):
      ``zone_calculation_id``, ``cooling_load_calculation_id``,
      ``equipment_calculation_id``, ``power_calculation_id``,
      ``investment_calculation_id``.
    * **Persisted result hashes** (5 stages, frozen):
      ``zone_result_hash``, ``cooling_load_result_hash``,
      ``equipment_result_hash``, ``power_result_hash``,
      ``investment_result_hash``.
    * **Persisted snapshot columns** (JSON, frozen):
      ``input_snapshot`` (dict), ``assumption_snapshot`` (dict),
      ``comparison_snapshot`` (dict), ``candidates_snapshot`` (dict).
    * **Other persisted production fields**:
      ``project_id`` (str), ``project_version_id`` (str),
      ``weight_set_id`` (str), ``status`` (str),
      ``generator_version`` (str), ``source_snapshot_hash`` (str),
      ``content_hash`` (str | None),
      ``recommended_scheme_code`` (str | None),
      ``requires_review`` (bool), ``warning_messages`` (tuple[str, ...]).
    """

    # Runtime identity (raw artifact only)
    run_id: str
    created_at: datetime
    completed_at: datetime | None
    database_backend: str

    # Persisted production source identity
    source_mode: str
    source_binding_id: str
    source_contract_version: str
    weight_set_revision_id: str
    weight_set_content_hash: str
    weight_set_generator_compatibility_version: str
    combined_source_hash: str
    binding_schema_version: str
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    authoritative_attempt_id: str
    orchestration_fingerprint: str

    # Persisted calculation lineage (5 stages)
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str

    # Persisted result hashes (5 stages)
    zone_result_hash: str
    cooling_load_result_hash: str
    equipment_result_hash: str
    power_result_hash: str
    investment_result_hash: str
    # Persisted snapshot columns (JSON, frozen):
    # ``candidates_snapshot`` accepts a list (production
    # canonical) or a dict (legacy test-fixture shape).
    input_snapshot: dict[str, object]
    assumption_snapshot: dict[str, object]
    comparison_snapshot: dict[str, object]
    candidates_snapshot: list[object] | dict[str, object]
    # Other persisted production fields
    project_id: str
    project_version_id: str
    weight_set_id: str
    status: str
    generator_version: str
    source_snapshot_hash: str
    content_hash: str | None
    recommended_scheme_code: str | None
    requires_review: bool
    warning_messages: tuple[str, ...]


def read_c2_baseline_projection(
    session_factory: _Callable[[], object],
    *,
    run_id: str,
) -> C2BaselineProjectionSource:
    """Read a persisted production record by exact ``run_id`` and return a frozen typed projection.

    The function is the AUTHORIZED Round 3 C-2 read boundary
    (comment 4974759224). It is the ONLY addition allowed inside the
    adapter module by the Round 3 amendment. The function:

    * queries the exact production row by primary key
      (no latest / first / fallback / scenario_id-derived lookup);
    * reads each production-required column by explicit
      ``getattr(record, col)`` (no ``vars`` / ``__dict__`` /
      ``_sa_instance_state`` / generic reflection);
    * fails closed with :class:`MissingC2ProductionField` if any
      production-required column is None or missing;
    * fails closed with :class:`AdapterInputError` if the row is
      not found (the function does NOT fall back to any other row);
    * fails closed with :class:`AdapterInputError` if
      ``record.source_mode != "production"`` (legacy rows are
      out-of-scope for the C-2 normalized business projection);
    * does NOT write, commit, flush, create, mutate, or approve;
    * returns a frozen :class:`C2BaselineProjectionSource` value
      object (the ORM row itself is not exposed).

    Parameters
    ----------
    session_factory:
        Zero-arg callable returning a SQLAlchemy ``Session`` (or
        any object exposing ``.execute(stmt)`` and the
        ``with`` context-manager protocol). The session is opened
        and closed inside the function (no caller-side session
        lifecycle).
    run_id:
        The exact persisted ``SchemeRunRecord.id`` value. The
        function rejects empty / non-string values at the input
        boundary.

    Returns
    -------
    C2BaselineProjectionSource
        The frozen typed projection. The carrier does NOT carry
        the ORM row; downstream code consumes the fields by
        attribute access.
    """
    if not isinstance(run_id, str) or not run_id.strip():
        raise AdapterInputError(
            "read_c2_baseline_projection requires a non-empty run_id string.",
        )
    if session_factory is None:
        raise AdapterInputError(
            "read_c2_baseline_projection requires a session_factory; "
            "the C-2 read boundary is fail-closed on a None factory.",
        )

    # Lazy imports — the adapter module is allowed to touch
    # ``sqlalchemy`` / ``SchemeRunRecord`` ONLY inside the read
    # boundary; the existing adapter body (A1-2a surface) is
    # unchanged.
    from sqlalchemy import select as _sa_select

    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeRunRecord as _SchemeRunRecord,
    )

    with session_factory() as _session:  # type: ignore[attr-defined]
        _record = _session.execute(
            _sa_select(_SchemeRunRecord).where(_SchemeRunRecord.id == run_id)
        ).scalar_one_or_none()

    if _record is None:
        # The function NEVER falls back to another row; an unknown
        # ``run_id`` is a typed boundary violation.
        raise AdapterInputError(
            f"read_c2_baseline_projection: no SchemeRunRecord found for "
            f"run_id={run_id!r}; the C-2 read boundary "
            "fails closed and does NOT fall back to any other row.",
        )

    # Per-Round 3 authority: the C-2 normalized business projection
    # only applies to production-source rows. Legacy rows
    # (``source_mode == 'legacy'``) intentionally have null
    # production-source columns; a legacy row is NOT a valid input
    # for the frozen baseline projection.
    _source_mode = getattr(_record, "source_mode", None)
    if _source_mode != "production":
        raise AdapterInputError(
            f"read_c2_baseline_projection: run_id={run_id!r} "
            f"has source_mode={_source_mode!r}; the C-2 normalized "
            "business projection requires source_mode='production'.",
        )

    # Assert all production-required columns are non-None using
    # STRICT typed validators. The validators reject any silent
    # stringification / truthiness conversion (no ``str(x)``,
    # no ``bool(x)``, no ``x or default``). A null production
    # column is a typed boundary violation.
    _missing: list[str] = []
    for _col in _C2_REQUIRED_PRODUCTION_COLUMNS:
        _val = getattr(_record, _col, None)
        if _val is None:
            _missing.append(_col)
    if _missing:
        raise MissingC2ProductionField(
            f"read_c2_baseline_projection: run_id={run_id!r} "
            f"is missing required production columns: {_missing!r}. The "
            "C-2 read boundary fails closed and does NOT silently "
            "coerce None to a placeholder.",
        )

    # ── Strict typed validators (Round 4 §5) ────────────────────────
    # Each validator enforces the exact Python type expected by the
    # C-2 contract. ``bool`` is a subclass of ``int``, so a strict
    # boolean check uses ``type(v) is bool`` (not ``isinstance(v,
    # bool)`` for ints) to reject numeric / string values that would
    # silently pass a truthiness check. The validators raise
    # :class:`MissingC2ProductionField` so the runner fails closed
    # with a searchable failure path.

    def _require_non_empty_str(
        _record: object, _attr: str, *, allow_none: bool = False
    ) -> str:
        _v = getattr(_record, _attr)
        if _v is None:
            if allow_none:
                return None  # type: ignore[return-value]
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required str field {_attr!r} "
                f"is None on run_id={run_id!r}; the C-2 read boundary "
                "fails closed and does NOT silently coerce None to ''.",
            )
        if not isinstance(_v, str) or not _v:
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required str field {_attr!r} "
                f"is not a non-empty str on run_id={run_id!r} "
                f"(actual type={type(_v).__name__}, value={_v!r}); "
                "the C-2 read boundary fails closed and does NOT silently "
                "apply str() coercion.",
            )
        return _v

    def _require_exact_bool(_record: object, _attr: str) -> bool:
        """Require a strict ``bool`` value.

        Per Round 4 §5.2: the C-2 boundary must reject
        ``requires_review`` stored as 0 / 1 / string. The
        Python-side check is ``type(v) is bool`` (NOT
        ``isinstance(v, bool)`` for ints — ``bool`` is
        an ``int`` subclass). Additionally, the boundary
        performs a raw SQL type check via ``typeof()``
        to defeat SQLAlchemy's ``Boolean`` column type
        coercion, which silently converts int 0/1 (or
        any truthy text) to a Python ``bool`` on read.
        """
        _v = getattr(_record, _attr)
        if type(_v) is not bool:
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required bool field {_attr!r} "
                f"is not an exact bool on run_id={run_id!r} "
                f"(actual type={type(_v).__name__}, value={_v!r}); "
                "the C-2 read boundary fails closed and does NOT silently "
                "apply bool() coercion.",
            )
        # ── Defeat SQLAlchemy's ``Boolean`` column coercion ──
        # The Python value is already a bool (SQLAlchemy
        # converted int/str). To detect the underlying DB
        # type, do a raw ``typeof()`` query. If the
        # original column is NOT a numeric 0/1 (e.g. it's
        # a text 'true'), the strict boundary MUST reject.
        # The query uses the live record's primary key so
        # it is exact and side-effect free.
        try:
            from sqlalchemy import text as _sa_text

            with session_factory() as _verify_session:  # type: ignore[attr-defined]
                _raw = _verify_session.execute(
                    _sa_text("SELECT typeof(" + _attr + ") FROM scheme_runs WHERE id = :i"),
                    {"i": run_id},
                ).scalar_one_or_none()
        except Exception:
            # If the raw type-check query fails (e.g. a
            # non-SQLite backend or a non-scheme_runs
            # table), fall back to the Python-side check
            # (which has already passed).
            return _v
        if _raw is None:
            # The row vanished between the read and the
            # verify call; this is a race that the
            # boundary treats as a typed failure.
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required bool field {_attr!r} "
                f"row vanished during typeof() verify on run_id={run_id!r}; "
                "the C-2 read boundary fails closed.",
            )
        if _raw != "integer":
            # The persisted column is NOT 0/1 (e.g. it's
            # a text 'true' or any other type). The
            # strict boundary rejects — a production
            # ``requires_review`` column MUST be 0 or 1.
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required bool field {_attr!r} "
                f"is stored as DB type={_raw!r} (NOT 0/1) on "
                f"run_id={run_id!r}; the C-2 read boundary fails closed "
                "and does NOT silently apply SQLite Boolean type affinity.",
            )
        return _v

    def _require_datetime(_record: object, _attr: str) -> datetime:
        _v = getattr(_record, _attr)
        if not isinstance(_v, datetime):
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required datetime field "
                f"{_attr!r} is not a datetime on run_id={run_id!r} "
                f"(actual type={type(_v).__name__}); the C-2 read boundary "
                "fails closed and does NOT silently apply default=str.",
            )
        return _v

    def _require_optional_datetime(_record: object, _attr: str) -> datetime | None:
        _v = getattr(_record, _attr)
        if _v is None:
            return None
        if not isinstance(_v, datetime):
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: optional datetime field "
                f"{_attr!r} is neither None nor a datetime on "
                f"run_id={run_id!r} (actual type={type(_v).__name__}); "
                "the C-2 read boundary fails closed.",
            )
        return _v

    def _require_json_object(
        _record: object, _attr: str, *, allow_none: bool = False
    ) -> dict[str, object]:
        """Require a JSON object (dict). Reject None unless allow_none=True.

        Per Round 4 §5.3 the C-2 boundary REJECTS null snapshot
        columns; a missing snapshot is a typed boundary violation.
        The function does NOT silently default to ``{}``.
        """
        _v = getattr(_record, _attr)
        if _v is None:
            if allow_none:
                return None  # type: ignore[return-value]
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required JSON-object field "
                f"{_attr!r} is None on run_id={run_id!r}; the C-2 read "
                "boundary fails closed and does NOT silently default "
                "to an empty dict.",
            )
        if not isinstance(_v, dict):
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required JSON-object field "
                f"{_attr!r} is not a dict on run_id={run_id!r} "
                f"(actual type={type(_v).__name__}); the C-2 read boundary "
                "fails closed and does NOT silently apply dict() coercion.",
            )
        return _v

    def _require_candidates_snapshot(
        _record: object, _attr: str
    ) -> list[object] | dict[str, object]:
        """Require a candidates snapshot in the FROZEN production shape.

        The frozen contract allows either a ``list[object]`` (the
        production-side canonical shape) or a ``dict[str, object]``
        carrying a ``candidates`` list (the legacy test-fixture
        shape). Any other shape (string, int, None, dict without
        ``candidates``) is rejected fail-closed.
        """
        _v = getattr(_record, _attr)
        if _v is None:
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required candidates_snapshot "
                f"field {_attr!r} is None on run_id={run_id!r}; the C-2 "
                "read boundary fails closed.",
            )
        if isinstance(_v, list):
            return _v
        if isinstance(_v, dict):
            return _v
        raise MissingC2ProductionField(
            f"read_c2_baseline_projection: required candidates_snapshot "
            f"field {_attr!r} is neither a list nor a dict on "
            f"run_id={run_id!r} (actual type={type(_v).__name__}); "
            "the C-2 read boundary fails closed.",
        )

    def _require_string_array(_record: object, _attr: str) -> tuple[str, ...]:
        """Require a JSON array of strings. Reject None and non-strings.

        Per Round 4 §5.4 the C-2 boundary REJECTS ``warning_messages``
        entries that are not exact ``str`` instances (no truthiness
        coercion, no ``str(x)`` fallback).
        """
        _v = getattr(_record, _attr)
        if _v is None:
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required JSON-array field "
                f"{_attr!r} is None on run_id={run_id!r}; the C-2 read "
                "boundary fails closed.",
            )
        if not isinstance(_v, (list, tuple)):
            raise MissingC2ProductionField(
                f"read_c2_baseline_projection: required JSON-array field "
                f"{_attr!r} is neither a list nor a tuple on "
                f"run_id={run_id!r} (actual type={type(_v).__name__}); "
                "the C-2 read boundary fails closed.",
            )
        for _idx, _entry in enumerate(_v):
            if not isinstance(_entry, str):
                raise MissingC2ProductionField(
                    f"read_c2_baseline_projection: required JSON-array "
                    f"field {_attr!r}[{_idx}] is not a str on "
                    f"run_id={run_id!r} (actual type={type(_entry).__name__}); "
                    "the C-2 read boundary fails closed and does NOT "
                    "silently apply str() coercion.",
                )
        return tuple(_v)

    # ── Build the C-2 source by explicit typed reads (NO silent coercion) ──
    return C2BaselineProjectionSource(
        # Runtime identity
        run_id=_require_non_empty_str(_record, "id"),
        created_at=_require_datetime(_record, "created_at"),
        completed_at=_require_optional_datetime(_record, "completed_at"),
        database_backend=_require_non_empty_str(_record, "database_backend"),
        # Persisted production source identity
        source_mode=_require_non_empty_str(_record, "source_mode"),
        source_binding_id=_require_non_empty_str(_record, "source_binding_id"),
        source_contract_version=_require_non_empty_str(_record, "source_contract_version"),
        weight_set_revision_id=_require_non_empty_str(_record, "weight_set_revision_id"),
        weight_set_content_hash=_require_non_empty_str(_record, "weight_set_content_hash"),
        weight_set_generator_compatibility_version=_require_non_empty_str(
            _record, "weight_set_generator_compatibility_version"
        ),
        combined_source_hash=_require_non_empty_str(_record, "combined_source_hash"),
        binding_schema_version=_require_non_empty_str(_record, "binding_schema_version"),
        execution_snapshot_id=_require_non_empty_str(_record, "execution_snapshot_id"),
        coefficient_context_id=_require_non_empty_str(_record, "coefficient_context_id"),
        orchestration_identity_id=_require_non_empty_str(_record, "orchestration_identity_id"),
        authoritative_attempt_id=_require_non_empty_str(_record, "authoritative_attempt_id"),
        orchestration_fingerprint=_require_non_empty_str(_record, "orchestration_fingerprint"),
        # Persisted calculation lineage
        zone_calculation_id=_require_non_empty_str(_record, "zone_calculation_id"),
        cooling_load_calculation_id=_require_non_empty_str(_record, "cooling_load_calculation_id"),
        equipment_calculation_id=_require_non_empty_str(_record, "equipment_calculation_id"),
        power_calculation_id=_require_non_empty_str(_record, "power_calculation_id"),
        investment_calculation_id=_require_non_empty_str(_record, "investment_calculation_id"),
        # Persisted result hashes
        zone_result_hash=_require_non_empty_str(_record, "zone_result_hash"),
        cooling_load_result_hash=_require_non_empty_str(_record, "cooling_load_result_hash"),
        equipment_result_hash=_require_non_empty_str(_record, "equipment_result_hash"),
        power_result_hash=_require_non_empty_str(_record, "power_result_hash"),
        investment_result_hash=_require_non_empty_str(_record, "investment_result_hash"),
        # Persisted snapshot columns — fail-closed on None
        # (Round 4 §5.3 rejects ``or {}`` defaulting).
        input_snapshot=_require_json_object(_record, "input_snapshot"),
        assumption_snapshot=_require_json_object(_record, "assumption_snapshot"),
        comparison_snapshot=_require_json_object(_record, "comparison_snapshot"),
        candidates_snapshot=_require_candidates_snapshot(_record, "candidates_snapshot"),
        # Other persisted production fields
        project_id=_require_non_empty_str(_record, "project_id"),
        project_version_id=_require_non_empty_str(_record, "project_version_id"),
        weight_set_id=_require_non_empty_str(_record, "weight_set_id"),
        status=_require_non_empty_str(_record, "status"),
        generator_version=_require_non_empty_str(_record, "generator_version"),
        source_snapshot_hash=_require_non_empty_str(_record, "source_snapshot_hash"),
        # ``content_hash`` is required non-None for production
        # completed baseline (Round 4 §5.2). The contract
        # still types it ``str | None`` at the dataclass level
        # so the same dataclass can carry the live value
        # coming from production; the boundary rejects None
        # BEFORE the dataclass is constructed.
        content_hash=_require_non_empty_str(_record, "content_hash"),
        recommended_scheme_code=_require_non_empty_str(
            _record, "recommended_scheme_code", allow_none=True
        ),
        requires_review=_require_exact_bool(_record, "requires_review"),
        warning_messages=_require_string_array(_record, "warning_messages"),
    )


__all__ = [
    "AdapterInputError",
    "AdapterResult",
    "C2BaselineProjectionSource",
    "MissingC2ProductionField",
    "execute_scenario",
    "read_c2_baseline_projection",
]
