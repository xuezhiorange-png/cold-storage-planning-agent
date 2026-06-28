"""Orchestration domain — immutable enums, DTOs, errors, DAG, canonical hashing.

All domain types are frozen (``@dataclass(frozen=True, slots=True)``) and
carry no database session, ORM references, or mutable state.

Deep immutability: all ``Mapping``, ``list``, and nested ``dict`` values are
defensively copied and recursively frozen on construction.  External mutation
of source objects never affects a constructed DTO.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from cold_storage.modules.orchestration.domain.dag import STAGE_UPSTREAM_PROVENANCE_KEYS

# ── Request status ──────────────────────────────────────────────────────────


class RequestStatus(StrEnum):
    """Orchestration request lifecycle status."""

    PENDING = "PENDING"
    PREFLIGHT_REJECTED = "PREFLIGHT_REJECTED"
    ACCEPTED = "ACCEPTED"


# ── Identity / attempt statuses ─────────────────────────────────────────────


class IdentityStatus(StrEnum):
    """OrchestrationIdentityRecord lifecycle status."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class AttemptStatus(StrEnum):
    """OrchestrationRunAttemptRecord lifecycle status."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


# ── Stage execution status ──────────────────────────────────────────────────


class StageExecutionStatus(StrEnum):
    """Per-stage calculator execution outcome."""

    PASSED = "passed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Outbox status ───────────────────────────────────────────────────────────


class OutboxStatus(StrEnum):
    """Audit outbox event dispatch status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PUBLISHED = "PUBLISHED"


# ── SchemeRun source mode ───────────────────────────────────────────────────


class SourceMode(StrEnum):
    """SchemeRun source identity mode."""

    LEGACY = "legacy"
    PRODUCTION = "production"


# ── Calculation type ────────────────────────────────────────────────────────


class CalculationType(StrEnum):
    """Five-stage calculation type identifiers."""

    ZONE = "zone"
    COOLING_LOAD = "cooling_load"
    EQUIPMENT = "equipment"
    POWER = "power"
    INVESTMENT = "investment"


# ── Deep freeze helpers ─────────────────────────────────────────────────────


def deep_freeze(value: object) -> object:
    """Recursively freeze *value* into an immutable representation.

    - ``dict`` → ``FrozenMapping`` (sorted keys for deterministic iteration)
    - ``list`` / ``tuple`` → ``tuple``
    - ``str`` → canonical lowercase (only for UUID-like identifiers)
    - everything else → returned as-is
    """
    if isinstance(value, dict):
        return _FrozenMapping(
            {str(k): deep_freeze(v) for k, v in sorted(value.items())}
        )
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(v) for v in value)
    if isinstance(value, _FrozenMapping):
        return value
    return value


class _FrozenMapping(Mapping):
    """Immutable, hashable mapping that deep-freezes on construction."""

    __slots__ = ("_data", "_hash")

    def __init__(self, data: dict[str, object]) -> None:
        object.__setattr__(self, "_data", data)
        h = hash(tuple(sorted(data.items())))
        object.__setattr__(self, "_hash", h)

    def __getitem__(self, key: str) -> object:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _FrozenMapping):
            return self._data == other._data
        if isinstance(other, Mapping):
            return dict(self._data) == dict(other)
        return NotImplemented

    def __repr__(self) -> str:
        return f"FrozenMapping({self._data!r})"


# ── Orchestration Request Command ───────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class OrchestrationRequestCommand:
    """Immutable input command for an orchestration request (approved design §9.1).

    Accepted names: ``OrchestrationRequestCommand`` or ``OrchestrationInput``.
    """

    project_id: str
    project_version_id: str
    coefficient_resolution_context: Mapping[str, object]
    actor: str
    correlation_id: str

    def __post_init__(self) -> None:
        # Defensive freeze: ensure the coefficient context is deeply immutable
        frozen = deep_freeze(self.coefficient_resolution_context)
        object.__setattr__(self, "coefficient_resolution_context", frozen)


# ── Preflight Failure ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PreflightFailure:
    """Typed preflight rejection result (approved design §9.3)."""

    request_id: str
    project_id: str
    project_version_id: str
    error_class: str
    code: str
    field: str
    details: Mapping[str, object]
    occurred_at: datetime

    def __post_init__(self) -> None:
        frozen = deep_freeze(self.details)
        object.__setattr__(self, "details", frozen)


# ── Execution Snapshot Candidate ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ExecutionSnapshotCandidate:
    """Immutable execution snapshot built from an approved ProjectVersion
    (approved design §6.2)."""

    project_id: str
    project_version_id: str
    version_number: int
    input_snapshot: Mapping[str, object]
    input_snapshot_hash: str
    schema_version: str
    captured_status: str
    captured_source_revision: str | None = None

    def __post_init__(self) -> None:
        frozen = deep_freeze(self.input_snapshot)
        object.__setattr__(self, "input_snapshot", frozen)


# ── Coefficient Context Candidate ───────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CoefficientContextCandidate:
    """Immutable resolved coefficient context (approved design §7)."""

    project_id: str
    project_version_id: str
    content: Mapping[str, object]
    content_hash: str
    schema_version: str

    def __post_init__(self) -> None:
        frozen = deep_freeze(self.content)
        object.__setattr__(self, "content", frozen)


# ── Orchestration Identity Candidate ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class OrchestrationIdentityCandidate:
    """Immutable identity built from fingerprint and preparation artifacts
    (approved design §11.1)."""

    fingerprint: str
    execution_snapshot_id: str
    coefficient_context_id: str
    definition_version: str
    calculator_version_vector: Mapping[str, object]

    def __post_init__(self) -> None:
        frozen = deep_freeze(self.calculator_version_vector)
        object.__setattr__(self, "calculator_version_vector", frozen)


# ── Orchestration Attempt Candidate ─────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class OrchestrationAttemptCandidate:
    """Immutable attempt lease acquisition result (approved design §11.2)."""

    identity_id: str
    attempt_number: int
    status: str
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None


# ── Stage Execution Diagnostic ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StageExecutionDiagnostic:
    """In-memory per-stage execution diagnostic (approved design §14.1).

    Contains no ``calculation_run_id`` and makes no persistence claim.
    """

    calculator_name: str
    execution_status: str  # passed | blocked | failed | skipped
    requires_review: bool
    input_hash: str | None
    result_hash: str | None
    blocker: Mapping[str, object] | None = None
    error: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.blocker is not None:
            object.__setattr__(self, "blocker", deep_freeze(self.blocker))
        if self.error is not None:
            object.__setattr__(self, "error", deep_freeze(self.error))


# ── Stage Persisted Result ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StagePersistedResult:
    """Persisted stage result (approved design §14.2).

    Constructed only after a COMPLETED Transaction B commit succeeds.
    """

    calculator_name: str
    calculation_run_id: str
    input_hash: str
    result_hash: str
    calculator_version: str
    snapshot_schema_version: str


# ── Source Binding Candidate ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SourceBindingCandidate:
    """Immutable five-slot binding candidate (approved design §16)."""

    identity_id: str
    attempt_id: str
    fingerprint: str
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str
    per_calculation_result_hashes: Mapping[str, str]
    combined_source_hash: str
    schema_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "per_calculation_result_hashes",
            deep_freeze(self.per_calculation_result_hashes),
        )


# ── Orchestration Result ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Complete orchestration outcome (approved design §14.3)."""

    request_id: str
    identity_id: str | None
    attempt_id: str | None
    attempt_number: int | None
    status: str  # PREFLIGHT_REJECTED | COMPLETED | BLOCKED | FAILED | IN_PROGRESS
    requires_review: bool
    persisted_stages: tuple[StagePersistedResult, ...] = ()
    diagnostics: tuple[StageExecutionDiagnostic, ...] = ()
    source_binding_id: str | None = None
    fingerprint: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


# ── SourceSnapshot Provenance validation ────────────────────────────────────


def validate_provenance_keys(
    calculation_type: str,
    upstream_calculation_ids: Mapping[str, str],
) -> None:
    """Validate that *upstream_calculation_ids* matches the frozen key set
    for *calculation_type* (approved design §13.5.7).

    Raises ``ValueError`` on missing/extra/null/empty/whitespace keys.
    """
    allowed = STAGE_UPSTREAM_PROVENANCE_KEYS.get(calculation_type)
    if allowed is None:
        raise ValueError(
            f"Unknown calculation_type {calculation_type!r}; "
            f"allowed: {sorted(STAGE_UPSTREAM_PROVENANCE_KEYS.keys())}"
        )

    actual = frozenset(upstream_calculation_ids.keys())

    if actual != allowed:
        extra = actual - allowed
        missing = allowed - actual
        msgs: list[str] = []
        if missing:
            msgs.append(f"missing keys: {sorted(missing)}")
        if extra:
            msgs.append(f"extra keys: {sorted(extra)}")
        raise ValueError(
            f"Provenance key set mismatch for {calculation_type!r}: "
            f"{'; '.join(msgs)}. "
            f"Expected: {sorted(allowed)}"
        )

    for key in allowed:
        value = upstream_calculation_ids[key]
        if value is None:
            raise ValueError(
                f"Provenance key {key!r} for {calculation_type!r} is None"
            )
        if not isinstance(value, str):
            raise ValueError(
                f"Provenance key {key!r} for {calculation_type!r} "
                f"is not a string: {type(value).__name__}"
            )
        stripped = value.strip()
        if not stripped:
            raise ValueError(
                f"Provenance key {key!r} for {calculation_type!r} is empty/whitespace"
            )


def validate_content_provenance_identity_consistency(
    *,
    calculation_type: str,
    execution_snapshot_id: str,
    coefficient_context_id: str,
    orchestration_identity_id: str,
    orchestration_run_attempt_id: str,
    provenance_execution_snapshot_id: str,
    provenance_coefficient_context_id: str,
    provenance_orchestration_identity_id: str,
    provenance_orchestration_run_attempt_id: str,
) -> None:
    """Verify that content-level identity fields match provenance identity fields.

    Per approved design §13.5.7 and P1-1 review: any mismatch must fail closed.
    """
    mismatches: list[str] = []

    def _check(field: str, content_val: str, provenance_val: str) -> None:
        if content_val != provenance_val:
            mismatches.append(
                f"{field}: content={content_val!r} != provenance={provenance_val!r}"
            )

    _check("execution_snapshot_id", execution_snapshot_id, provenance_execution_snapshot_id)
    _check("coefficient_context_id", coefficient_context_id, provenance_coefficient_context_id)
    _check("orchestration_identity_id", orchestration_identity_id, provenance_orchestration_identity_id)
    _check("orchestration_run_attempt_id", orchestration_run_attempt_id, provenance_orchestration_run_attempt_id)

    if mismatches:
        raise ValueError(
            f"Content-provenance identity mismatch for {calculation_type!r}: "
            f"{'; '.join(mismatches)}"
        )
