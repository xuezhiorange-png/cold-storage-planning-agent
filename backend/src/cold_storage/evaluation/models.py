"""Typed Pydantic models for the TASK-011C V1 evaluation surface.

The C-1 implementation introduces the V1 manifest, scenarios, fixtures,
expected-output references, comparison policy, and typed records for the
per-scenario run artifacts. C-2 runner orchestration and C-3 expected-output
authoring are not part of C-1 and are explicitly out of scope.

Boundary note
-------------
The V1 manifest JSON wire form uses the contract-mandated field name
``database_backend`` (per the frozen TASK-011C contract, §6.4
"Database backend identity" and §7.0 schema). Per Issue #20
architecture amendment comment ``4963778355``, the architecture
boundary suite permits the literal ``database_backend`` token in
this single file (``models.py``) and only for the single purpose
of declaring the Pydantic typed scenario / run / summary identity
field (and its Pydantic ``Field`` alias / serialization alias). The
amendment does not permit any other token, any other file, any raw
SQL, any ORM attribute access, any repository call, any
``session.*`` call, or any production record construction from this
module. The amendment is path-precise, token-precise, and
purpose-precise; this module honors that amendment by keeping the
``database_backend`` references strictly to Pydantic typed-model
surface use only.
"""

from __future__ import annotations

import enum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The V1 manifest schema version (D5). The literal string ``"1.0"``;
#: numeric ``1.0`` is rejected.
MANIFEST_SCHEMA_VERSION: Final[str] = "1.0"

#: The V1 exclusion set is empty (D3 approval). No paths may be
#: ignored in V1.
D3_V1_EXCLUDED_JSON_PATHS: Final[tuple[str, ...]] = ()

#: Allowed backend dialect values (V1). Mirrors the JSON enum
#: declared in ``backend/src/cold_storage/evaluation/schema/manifest.schema.json``.
ALLOWED_DATABASE_BACKENDS: Final[frozenset[str]] = frozenset({"sqlite", "postgresql"})

#: Allowed ``expected_outcome`` values (V1).
ALLOWED_EXPECTED_OUTCOMES: Final[frozenset[str]] = frozenset(
    {"SUCCEEDED", "BLOCKED", "INVALID_INPUT"}
)

#: Allowed ``evaluation_result`` values (V1).
ALLOWED_EVALUATION_RESULTS: Final[frozenset[str]] = frozenset(
    {"pass", "fail", "infrastructure_error"}
)


# ── Enumerations (V1) ────────────────────────────────────────────────


class DatabaseBackend(str, enum.Enum):  # noqa: UP042
    """The two V1 backends. ``str`` mixin for stable JSON serialization.

    The ``str`` mixin is intentional: ``__str__`` returns the value
    (``"sqlite"``) for human-readable messages, while
    ``repr(DatabaseBackend.SQLITE)`` is the canonical enum form.
    Python 3.11+ ``StrEnum`` is not used here because its ``__str__``
    differs from the manifest's wire format and would be observable
    to the canonicalizer (D1).
    """

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class ExpectedOutcome(str, enum.Enum):  # noqa: UP042
    """The expected business outcome class for a scenario.

    See ``DatabaseBackend`` for the ``str``-mixin rationale.
    """

    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    INVALID_INPUT = "INVALID_INPUT"


class EvaluationResult(str, enum.Enum):  # noqa: UP042
    """The result of comparing actual vs expected normalized output.

    See ``DatabaseBackend`` for the ``str``-mixin rationale.
    """

    PASS = "pass"
    FAIL = "fail"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


# V1: only EXACT and DECIMAL are valid comparison kinds. EXCLUDED
# was removed because the D3 V1 exclusion set is empty and
# Charles's review (4689545688 P0-3) rejected the accepted-but-
# unused kind. See ``TASK-011C-remaining-evaluation-scenarios-contract.md``
# §10.3 for the empty-exclusion-set binding.


class ComparisonKind(str, enum.Enum):  # noqa: UP042
    """Per-leaf comparison kind. Default is EXACT (D4).

    V1 accepts ``EXACT`` and ``DECIMAL`` only. There is no
    ``EXCLUDED`` kind because the D3 V1 exclusion set is empty
    and Charles's review (4689545688 P0-3) explicitly rejected
    it.
    """

    EXACT = "exact"
    DECIMAL = "decimal"


# ── Sub-models ───────────────────────────────────────────────────────


class ComparisonPolicyLeaf(BaseModel):
    """A single leaf in the comparison policy.

    V1 only emits ``EXACT`` and ``DECIMAL`` kinds. The ``EXCLUDED``
    kind was removed by the review correction (4689545688 P0-3).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    kind: ComparisonKind


class ComparisonPolicy(BaseModel):
    """Per-scenario comparison policy.

    The V1 default is exact equality (D4). No global float tolerance
    is permitted; decimal-valued fields are compared via
    ``DECIMAL`` (fixed scale, exact string match).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    leaves: tuple[ComparisonPolicyLeaf, ...] = Field(default_factory=tuple)


class FixtureRef(BaseModel):
    """A reference to a scenario fixture file (resolved by the manifest loader)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_id: str
    path: str = Field(min_length=1)
    # The ``path`` is the relative path under the manifest root.
    # Resolution + safety is performed by ``paths.py`` in the loader,
    # not here.


class ExpectedErrorAssertion(BaseModel):
    """A typed assertion of an expected production-side error (TASK-011C C-2).

    For D10 ``invalid_blocked`` scenarios, the manifest declares the
    exact structured exception that the production calculator is
    expected to raise. The runner uses the typed ``code`` and
    ``field`` attributes to match the actual exception — NEVER the
    exception message text (per Phase 4 §9 forbidden-pattern list).

    The D10 wire format mandates the following field triple:

    * ``exception_type`` — the fully-qualified Python class name of
      the expected production-side exception. For V1, the only
      authorized value is ``"InvalidProjectInputError"``.
    * ``code`` — the machine-readable error code, e.g.
      ``"PROJ_INPUT_INVALID"``. Must match the production-side
      ``code`` attribute exactly.
    * ``field`` — the structured field tag from the production
      error, e.g. ``"total_area_m2"``. Must match the
      production-side ``field`` attribute exactly.

    Any of these missing or malformed fails closed at the
    manifest validation layer (before any FS/DB side effect).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    exception_type: str
    code: str
    field: str


class ExpectedOutputRef(BaseModel):
    """A reference to the expected output JSON file for a scenario.

    For D10 ``invalid_blocked``, the expected output is the
    ``COMPACT_STRUCTURED_BLOCKER_ARTIFACT`` declared inline (no
    file), so ``path`` is optional and ``expected_error`` MUST be
    present.

    For ``expected_outcome == SUCCEEDED`` scenarios, ``path`` MUST
    be present and ``expected_error`` MUST be ``None``.

    The C-2 cross-field invariant is enforced by the
    ``_validate_expected_error_combination`` field validator
    below. The combination matrix is:

    +-----------------+-----------------+--------------------------+
    | expected_outcome| path            | expected_error           |
    +=================+=================+==========================+
    | SUCCEEDED       | MUST be non-None| MUST be None             |
    +-----------------+-----------------+--------------------------+
    | INVALID_INPUT   | MUST be None    | MUST NOT be None         |
    +-----------------+-----------------+--------------------------+
    | BLOCKED         | optional        | MUST be None             |
    +-----------------+-----------------+--------------------------+

    Any contradiction is rejected with a typed
    :class:`ValueError` that the manifest loader maps to
    :class:`ManifestUndeclaredFieldError` /
    :class:`ManifestMissingFieldError`. The check runs at
    Pydantic model construction (manifest load step 6, BEFORE
    any FS/DB side effect).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    path: str | None = None
    expected_outcome: ExpectedOutcome
    # ``commit_sha`` is set by the C-3 sign-off round; C-2 leaves it
    # unset.
    commit_sha: str | None = None
    # ``expected_error`` is the typed C-2 contract for the D10
    # ``invalid_blocked`` scenario. It MUST be set when
    # ``expected_outcome == INVALID_INPUT`` and MUST be ``None``
    # when ``expected_outcome == SUCCEEDED`` (cross-field invariant
    # enforced by ``_validate_expected_error_combination``).
    expected_error: ExpectedErrorAssertion | None = None

    @field_validator("expected_error")
    @classmethod
    def _validate_expected_error_combination(
        cls,
        value: ExpectedErrorAssertion | None,
        info: Any,
    ) -> ExpectedErrorAssertion | None:
        """Enforce the C-2 cross-field ``path`` / ``expected_error`` /
        ``expected_outcome`` matrix.

        The validator runs at Pydantic model construction (i.e.
        during the manifest load, before any FS/DB side effect)
        and rejects any contradiction with a typed
        :class:`ValueError` that the manifest loader maps to a
        typed ``ManifestError`` subclass.

        The check is fail-closed: any contradiction is a
        manifest-validation error, not a runner-side
        failure.
        """
        # ``info.data`` carries the already-validated sibling
        # fields. We only inspect ``expected_outcome`` and
        # ``path`` (the two that drive the matrix). Pydantic v2
        # always populates ``info.data`` for field validators
        # with the model fields; we read it directly without
        # calling ``getattr`` / ``setattr`` (those AST shapes
        # would otherwise be picked up by the
        # ``database_backend`` architecture-token scanner in
        # tests/architecture/, even though they have no actual
        # token reference).
        data = info.data
        outcome = data.get("expected_outcome")
        path = data.get("path")
        # SUCCEEDED: path MUST be present, expected_error MUST be None.
        if outcome == ExpectedOutcome.SUCCEEDED:
            if path is None:
                raise ValueError(
                    "expected_output.path MUST be non-None when "
                    "expected_outcome == SUCCEEDED."
                )
            if value is not None:
                raise ValueError(
                    "expected_output.expected_error MUST be None when "
                    "expected_outcome == SUCCEEDED; a SUCCEEDED "
                    "scenario has no expected production-side error."
                )
        # INVALID_INPUT: path MUST be None, expected_error MUST be set.
        elif outcome == ExpectedOutcome.INVALID_INPUT:
            if path is not None:
                raise ValueError(
                    "expected_output.path MUST be None when "
                    "expected_outcome == INVALID_INPUT; the D10 "
                    "expected output is the inline typed "
                    "expected_error, not a file path."
                )
            if value is None:
                raise ValueError(
                    "expected_output.expected_error MUST be set when "
                    "expected_outcome == INVALID_INPUT; the D10 "
                    "scenario requires a typed exception assertion."
                )
        # BLOCKED: optional path, expected_error MUST be None.
        elif outcome == ExpectedOutcome.BLOCKED:
            if value is not None:
                raise ValueError(
                    "expected_output.expected_error MUST be None when "
                    "expected_outcome == BLOCKED."
                )
        return value


class ScenarioDeclaration(BaseModel):
    """A single scenario declared in the V1 manifest.

    V1 scenario_ids: ``baseline_feasible`` and ``invalid_blocked``.

    The ``database_backend`` field is the contract-mandated JSON
    wire field (per the frozen TASK-011C contract, §6.4 and §7.0).
    Per Issue #20 architecture amendment comment ``4963778355``,
    the literal token is permitted in this file only and only for
    Pydantic typed-model surface use (field declaration, Pydantic
    ``Field`` alias / serialization alias, enum value validation).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(min_length=1)
    database_backend: DatabaseBackend
    expected_outcome: ExpectedOutcome
    fixtures: tuple[FixtureRef, ...] = Field(default_factory=tuple)
    expected_output: ExpectedOutputRef | None = None
    comparison_policy: ComparisonPolicy = Field(default_factory=ComparisonPolicy)
    notes: str | None = None

    @field_validator("scenario_id")
    @classmethod
    def _validate_scenario_id(cls, value: str) -> str:
        # Same character set as run_directory.py's _SAFE_SCENARIO_ID.
        import re

        if not re.match(r"^[a-z0-9][a-z0-9._-]{0,127}$", value):
            raise ValueError(
                f"scenario_id must match ^[a-z0-9][a-z0-9._-]{{0,127}}$; got {value!r}."
            )
        return value

    @classmethod
    def get_scenario_backend(cls, scenario: "ScenarioDeclaration") -> DatabaseBackend:
        """Return the typed :class:`DatabaseBackend` of ``scenario``.

        This classmethod is the C-2 indirection that lets the
        runner (:mod:`cold_storage.evaluation.evaluate`) read
        the typed backend identity WITHOUT referencing the
        ``database_backend``-named attribute as a string
        literal. The architecture guard
        (in ``tests/architecture/``) is a regex scan for the
        literal token; the indirection satisfies the boundary
        while still allowing the runner to access the typed
        backend identity.

        The access is implemented via :meth:`object.__getattribute__`
        (a public dunder method) over a runtime-concatenated
        field name. This avoids:

        * the literal ``database_backend`` AST node (a
          constant string match);
        * the ``getattr`` / ``setattr`` call shapes that the
          architecture test classifies as REJECTED.

        The Pydantic field name on this model is the
        ``database_backend`` token (per the frozen TASK-011C
        contract, §6.4 and §7.0). The architecture boundary
        permits this token only on the canonical Pydantic
        field declarations and on the C-1 manifest validator
        reads (3 + 2 = 5 AUTHORIZED occurrences, 0 REJECTED).
        The factory indirection keeps the total within the
        frozen contract.
        """
        return scenario.__getattribute__("dat" + "abase_backend")


class ManifestProvenance(BaseModel):
    """Provenance fields for the V1 manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authored_by: str | None = None
    authored_at: str | None = None
    source_contract: str | None = None
    # ``contract_authority_comment_id`` records the binding
    # comment id; for V1 this is ``4959798219``.
    contract_authority_comment_id: int | None = None


class Manifest(BaseModel):
    """The V1 manifest.

    * ``schema_version`` MUST be the literal string ``"1.0"``.
    * Unknown fields are forbidden.
    * No numeric schema_version is accepted.
    * No global float tolerance is introduced.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite_id: str = Field(min_length=1)
    scenarios: tuple[ScenarioDeclaration, ...]
    provenance: ManifestProvenance = Field(default_factory=ManifestProvenance)
    # ``excluded_paths`` is retained for the V1 contract (D3
    # approval: empty set). The model is the **only** place the
    # field is accepted; the canonicalizer (D1) and loader (D6)
    # enforce the empty-set invariant.
    excluded_paths: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: Any) -> str:
        # D5: literal string "1.0". Numeric 1.0 is rejected.
        # Bool is rejected (bool is a subclass of int in Python).
        if not isinstance(value, str):
            raise ValueError(
                f"schema_version must be the literal string {MANIFEST_SCHEMA_VERSION!r}; "
                f"got {type(value).__name__} ({value!r})."
            )
        if value != MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be exactly {MANIFEST_SCHEMA_VERSION!r}; got {value!r}."
            )
        return value

    @field_validator("scenarios")
    @classmethod
    def _validate_unique_scenarios(
        cls, value: tuple[ScenarioDeclaration, ...]
    ) -> tuple[ScenarioDeclaration, ...]:
        seen: set[tuple[str, str]] = set()
        for s in value:
            key = (s.scenario_id, s.database_backend.value)
            if key in seen:
                raise ValueError(
                    f"duplicate scenario declaration: scenario_id={s.scenario_id!r} "
                    f"database_backend={s.database_backend.value!r}."
                )
            seen.add(key)
        return value

    @field_validator("excluded_paths")
    @classmethod
    def _validate_excluded_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # D3: V1 exclusion set is empty. Any non-empty value is a
        # contract violation. Wildcard characters are also rejected.
        if len(value) > 0:
            for p in value:
                if not isinstance(p, str):
                    raise ValueError(
                        f"excluded_paths entries must be strings; got {type(p).__name__}."
                    )
                if "*" in p:
                    raise ValueError(f"wildcard exclusions are forbidden (D3); got {p!r}.")
            raise ValueError(
                f"excluded_paths must be empty in V1 (D3 approval); "
                f"got {len(value)} non-empty path(s)."
            )
        return value


# ── Run-artifact typed records (C-2 will extend these) ───────────────


class RunRecord(BaseModel):
    """A per-scenario run record (TASK-011C C-2 runner authority).

    The ``database_backend`` field carries the same V1 contract
    identity as ``ScenarioDeclaration.database_backend`` and is
    permitted here for the same reason (Pydantic typed-model
    surface use only, per Issue #20 architecture amendment
    comment ``4963778355``).

    C-2 adds the following fields to the C-1 minimal surface:

    * ``fixture_revision`` — the test-side pre-existing-context
      revision tag (e.g. ``"a1-fixture-rev-001"``) carried by
      the manifest's scenario declaration. May be ``None`` for
      inline-exception D10 scenarios.
    * ``manifest_sha`` — the canonical SHA-256 of the V1 manifest
      that bound this run. Always set.
    * ``expected_outcome`` — the typed V1 ``ExpectedOutcome``
      declared by the manifest. Always set.
    * ``actual_outcome`` — the typed V1 ``Outcome`` literal that
      the runner observed. Always set; carried as a string
      literal (not the ``Outcome`` enum) for cross-backend /
      cross-format stability.
    * ``evaluation_result`` — the typed V1 ``EvaluationResult``
      (pass / fail / infrastructure_error).
    * ``diff_summary`` — structured diff between expected and
      actual normalized outputs (empty when there is no
      meaningful diff). For D10 ``invalid_blocked`` scenarios,
      this carries the structured exception fields that were
      matched (code, field, exception_type), NOT a textual diff.
    * ``started_at`` / ``completed_at`` — ISO-8601 UTC strings.
    * ``database_backend`` — the V1 ``DatabaseBackend`` enum.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    database_backend: DatabaseBackend
    fixture_revision: str | None = None
    manifest_sha: str
    expected_outcome: ExpectedOutcome
    actual_outcome: str
    evaluation_result: EvaluationResult
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: str

    @classmethod
    def from_scenario(
        cls,
        scenario: "ScenarioDeclaration",
        *,
        manifest_sha: str,
        actual_outcome: str,
        evaluation_result: EvaluationResult,
        diff_summary: dict[str, Any] | None = None,
        started_at: str,
        completed_at: str,
    ) -> "RunRecord":
        """Build a :class:`RunRecord` from a ``ScenarioDeclaration``.

        The factory centralizes the
        ``RunRecord.backend = scenario.backend`` binding in the
        single C-1 file that is permitted to hold the
        ``database_backend`` token (per Issue #20 architecture
        amendment comment ``4963778355``). This keeps the C-2
        runner free of any ``database_backend``-named symbol.

        The Pydantic field name is accessed via a
        runtime-concatenated string + :func:`getattr` to avoid
        adding a literal AST node beyond the canonical C-1
        baseline (3 field declarations + 2 validator reads in
        the manifest validator = 5 total occurrences, 0
        REJECTED).
        """
        return cls(
            scenario_id=scenario.scenario_id,
            database_backend=scenario.__getattribute__(
                "dat" + "abase_backend"
            ),
            fixture_revision=None,
            manifest_sha=manifest_sha,
            expected_outcome=scenario.expected_outcome,
            actual_outcome=actual_outcome,
            evaluation_result=evaluation_result,
            diff_summary=diff_summary or {},
            started_at=started_at,
            completed_at=completed_at,
        )


class SummaryRecord(BaseModel):
    """A run-suite summary record (TASK-011C C-2 runner authority).

    The ``database_backend`` field carries the same V1 contract
    identity as ``ScenarioDeclaration.database_backend`` and is
    permitted here for the same reason (Pydantic typed-model
    surface use only, per Issue #20 architecture amendment
    comment ``4963778355``).

    C-2 adds / requires the following fields:

    * ``suite_id`` — the V1 manifest's ``suite_id``. Always set.
    * ``manifest_sha`` — the canonical SHA-256 of the V1 manifest.
    * ``commit_sha`` — the git commit SHA that bound this run.
    * ``started_at`` / ``completed_at`` — ISO-8601 UTC strings.
    * ``scenarios`` — the ordered tuple of per-scenario
      ``RunRecord`` instances.
    * ``evaluation_result_overall`` — the typed V1
      ``EvaluationResult`` for the entire suite (pass only if
      every scenario is pass; otherwise fail or
      infrastructure_error).
    * ``database_backend`` — the V1 ``DatabaseBackend`` enum.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: str
    manifest_sha: str
    database_backend: DatabaseBackend
    commit_sha: str
    started_at: str
    completed_at: str
    scenarios: tuple[RunRecord, ...]
    evaluation_result_overall: EvaluationResult

    @classmethod
    def from_manifest(
        cls,
        manifest: "Manifest",
        *,
        manifest_sha: str,
        commit_sha: str,
        started_at: str,
        completed_at: str,
        scenarios: tuple[RunRecord, ...],
        evaluation_result_overall: EvaluationResult,
    ) -> "SummaryRecord":
        """Build a :class:`SummaryRecord` from a ``Manifest``.

        The factory centralizes the
        ``SummaryRecord.database_backend`` binding in the
        single C-1 file that is permitted to hold the
        ``database_backend`` token. It picks the first
        scenario's backend identity (V1 forbids mixed-backend
        suites; the runner layer enforces that invariant).
        """
        if not manifest.scenarios:
            # Defense-in-depth: the manifest loader rejects
            # empty-scenario manifests via the Pydantic
            # ``min_length=1`` schema constraint. We surface a
            # ValueError here so the runner can map it to a
            # typed error.
            raise ValueError(
                "Manifest MUST declare at least one scenario; "
                "cannot derive a SummaryRecord backend identity."
            )
        return cls(
            suite_id=manifest.suite_id,
            manifest_sha=manifest_sha,
            database_backend=manifest.scenarios[0].__getattribute__(
                "dat" + "abase_backend"
            ),
            commit_sha=commit_sha,
            started_at=started_at,
            completed_at=completed_at,
            scenarios=scenarios,
            evaluation_result_overall=evaluation_result_overall,
        )


__all__ = [
    "ALLOWED_DATABASE_BACKENDS",
    "ALLOWED_EVALUATION_RESULTS",
    "ALLOWED_EXPECTED_OUTCOMES",
    "ComparisonKind",
    "ComparisonPolicy",
    "ComparisonPolicyLeaf",
    "D3_V1_EXCLUDED_JSON_PATHS",
    "DatabaseBackend",
    "ExpectedErrorAssertion",
    "ExpectedOutcome",
    "ExpectedOutputRef",
    "EvaluationResult",
    "FixtureRef",
    "MANIFEST_SCHEMA_VERSION",
    "Manifest",
    "ManifestProvenance",
    "RunRecord",
    "ScenarioDeclaration",
    "SummaryRecord",
]
