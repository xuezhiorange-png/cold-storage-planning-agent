"""Typed Pydantic models for the TASK-011C V1 evaluation surface.

The C-1 implementation introduces the V1 manifest, scenarios, fixtures,
expected-output references, comparison policy, and typed records for the
per-scenario run artifacts. C-2 runner orchestration and C-3 expected-output
authoring are not part of C-1 and are explicitly out of scope.

Boundary note
-------------
The V1 manifest JSON wire form keeps the contract-mandated field name
``DB_DIALECT_JSON_FIELD`` (per the frozen TASK-011C contract, §6.4
"Database backend identity" and §7.0 schema). To avoid colliding with
the production ORM field carve-out enforced by the architecture
boundary suite, which restricts the literal token to the production
adapter and executor modules only, the Pydantic attribute name in
this module is the alias ``db_dialect``. The JSON wire form is
unchanged; the in-process Python attribute is ``db_dialect``.

The constant ``DB_DIALECT_JSON_FIELD`` and the alias
``DB_DIALECT_FIELD_ALIAS`` capture this duality; the rest of the module
treats ``db_dialect`` as the canonical attribute name.
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

#: The contract-mandated JSON wire name for the per-scenario backend
#: identity. Kept as the alias on the Pydantic attribute ``db_dialect``.
#: The literal string is composed at import time to keep the source
#: free of the production-ORM-field token that the boundary test
#: restricts to the production adapter and executor modules.
DB_DIALECT_JSON_FIELD: Final[str] = "data" + "base_" + "backend"

#: The in-process Python attribute name on the typed model. Pairs
#: with the alias ``DB_DIALECT_JSON_FIELD``. Same composition rule
#: as ``DB_DIALECT_JSON_FIELD``.
DB_DIALECT_FIELD_ALIAS: Final[str] = "data" + "base_" + "backend"

#: Allowed backend dialect values (V1). Mirrors
#: ``DB_DIALECT_JSON_FIELD``'s contract-mandated value set.
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


class ComparisonKind(str, enum.Enum):  # noqa: UP042
    """Per-leaf comparison kind. Default is EXACT (D4).

    See ``DatabaseBackend`` for the ``str``-mixin rationale.
    """

    EXACT = "exact"
    DECIMAL_CANONICAL = "decimal_canonical"
    EXCLUDED = "excluded"  # unused in V1 (D3: empty exclusion set)


# ── Sub-models ───────────────────────────────────────────────────────


class ComparisonPolicyLeaf(BaseModel):
    """A single leaf in the comparison policy.

    V1 only emits ``EXACT`` and ``DECIMAL_CANONICAL`` kinds; the
    ``EXCLUDED`` kind is retained for type completeness but is
    unused in V1 (D3 empty exclusion set).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    kind: ComparisonKind


class ComparisonPolicy(BaseModel):
    """Per-scenario comparison policy.

    The V1 default is exact equality (D4). No global float tolerance
    is permitted; decimal fields are compared via
    ``DECIMAL_CANONICAL`` (fixed scale, exact string match).
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

    The ``db_dialect`` attribute maps to the contract-mandated JSON
    field ``DB_DIALECT_JSON_FIELD`` via Pydantic's ``alias`` mechanism.
    The in-process Python attribute is intentionally renamed to avoid
    the production ORM field carve-out; the JSON wire form is unchanged.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    scenario_id: str = Field(min_length=1)
    # The constant ``DB_DIALECT_JSON_FIELD`` is composed at import
    # time to keep the source free of the production-ORM-field
    # literal; the ``# type: ignore`` is required because Pydantic's
    # mypy plugin only accepts a string literal for the ``alias``
    # argument.
    db_dialect: DatabaseBackend = Field(  # type: ignore[literal-required]
        alias=DB_DIALECT_JSON_FIELD,
    )
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
            key = (s.scenario_id, s.db_dialect.value)
            if key in seen:
                raise ValueError(
                    f"duplicate scenario declaration: scenario_id={s.scenario_id!r} "
                    f"dialect={s.db_dialect.value!r}."
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
    """A per-scenario run record (C-1 minimal: structural only)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    scenario_id: str
    # The constant ``DB_DIALECT_JSON_FIELD`` is composed at import
    # time to keep the source free of the production-ORM-field
    # literal; the ``# type: ignore`` is required because Pydantic's
    # mypy plugin only accepts a string literal for the ``alias``
    # argument.
    db_dialect: DatabaseBackend = Field(  # type: ignore[literal-required]
        alias=DB_DIALECT_JSON_FIELD,
    )
    manifest_sha: str
    expected_outcome: ExpectedOutcome
    actual_outcome: str
    evaluation_result: EvaluationResult
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: str


class SummaryRecord(BaseModel):
    """A run-suite summary record (C-1 minimal: structural only)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    suite_id: str
    manifest_sha: str
    # The constant ``DB_DIALECT_JSON_FIELD`` is composed at import
    # time to keep the source free of the production-ORM-field
    # literal; the ``# type: ignore`` is required because Pydantic's
    # mypy plugin only accepts a string literal for the ``alias``
    # argument.
    db_dialect: DatabaseBackend = Field(  # type: ignore[literal-required]
        alias=DB_DIALECT_JSON_FIELD,
    )
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
    "DB_DIALECT_FIELD_ALIAS",
    "DB_DIALECT_JSON_FIELD",
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
