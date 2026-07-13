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


class ExpectedOutputRef(BaseModel):
    """A reference to the expected output JSON file for a scenario.

    For D10 ``invalid_blocked``, the expected output is the
    ``COMPACT_STRUCTURED_BLOCKER_ARTIFACT`` declared inline (no
    file), so ``path`` is optional.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    path: str | None = None
    expected_outcome: ExpectedOutcome
    # ``commit_sha`` is set by the C-3 sign-off round; C-1 leaves it
    # unset.
    commit_sha: str | None = None


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
    """A per-scenario run record (C-1 minimal: structural only).

    The ``database_backend`` field carries the same V1 contract
    identity as ``ScenarioDeclaration.database_backend`` and is
    permitted here for the same reason (Pydantic typed-model
    surface use only, per Issue #20 architecture amendment
    comment ``4963778355``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    database_backend: DatabaseBackend
    manifest_sha: str
    expected_outcome: ExpectedOutcome
    actual_outcome: str
    evaluation_result: EvaluationResult
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: str


class SummaryRecord(BaseModel):
    """A run-suite summary record (C-1 minimal: structural only).

    The ``database_backend`` field carries the same V1 contract
    identity as ``ScenarioDeclaration.database_backend`` and is
    permitted here for the same reason (Pydantic typed-model
    surface use only, per Issue #20 architecture amendment
    comment ``4963778355``).
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


__all__ = [
    "ALLOWED_DATABASE_BACKENDS",
    "ALLOWED_EVALUATION_RESULTS",
    "ALLOWED_EXPECTED_OUTCOMES",
    "ComparisonKind",
    "ComparisonPolicy",
    "ComparisonPolicyLeaf",
    "D3_V1_EXCLUDED_JSON_PATHS",
    "DatabaseBackend",
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
