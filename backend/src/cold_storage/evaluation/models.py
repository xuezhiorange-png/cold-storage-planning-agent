"""Immutable data models for evaluation manifests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ExpectedOutcome(StrEnum):
    """Expected outcome of an evaluation scenario."""

    SUCCESS = "success"
    REVIEW_REQUIRED = "review_required"
    VALIDATION_ERROR = "validation_error"
    BLOCKED = "blocked"
    FEATURE_UNAVAILABLE = "feature_unavailable"


class EvaluationStage(StrEnum):
    """Fixed enumeration of supported workflow stages."""

    PROJECT = "project"
    VERSION = "version"
    VALIDATION = "validation"
    PLANNING = "planning"
    ZONE_PLAN = "zone_plan"
    SCHEMES = "schemes"
    INVESTMENT = "investment"
    POWER = "power"
    AUDIT = "audit"
    REPORTS = "reports"
    KNOWLEDGE = "knowledge"
    AGENT = "agent"


class RunStatus(StrEnum):
    """Lifecycle status of an evaluation run."""

    CREATED = "created"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


class DecimalMode(StrEnum):
    """Allowed decimal comparison strategy."""

    QUANTIZE = "quantize"


class ArtifactStatus(StrEnum):
    """Allowed artifact status values."""

    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ExactPathRule:
    """An exact-equality path rule."""

    path: str


@dataclass(frozen=True, slots=True)
class DecimalPathRule:
    """A quantized decimal path rule with scale, unit, and rationale."""

    path: str
    mode: DecimalMode
    scale: int
    unit: str
    rationale: str


@dataclass(frozen=True, slots=True)
class IgnoredPathRule:
    """A path to exclude from comparison with a documented reason."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ArtifactCheckRule:
    """Contract for validating a rendered report artifact."""

    artifact_selector: str
    required_status: ArtifactStatus
    require_non_zero_size: bool
    require_integrity_hash: bool


@dataclass(frozen=True, slots=True)
class ComparisonPolicy:
    """All comparison rules for a single scenario."""

    exact_paths: tuple[ExactPathRule, ...]
    decimal_paths: tuple[DecimalPathRule, ...]
    ignored_paths: tuple[IgnoredPathRule, ...]
    artifact_checks: tuple[ArtifactCheckRule, ...]


@dataclass(frozen=True, slots=True)
class ManifestProvenance:
    """Provenance metadata describing the source of a scenario expectation."""

    source: str
    rationale: str


@dataclass(frozen=True, slots=True)
class EvaluationScenario:
    """A single evaluation scenario with input mapping and comparison policy."""

    scenario_id: str
    fixture_revision: int
    project_input_path: Path
    document_refs: tuple[Path, ...]
    required_stages: tuple[EvaluationStage, ...]
    expected_outcome: ExpectedOutcome
    expected_path: Path
    comparison_policy: ComparisonPolicy
    provenance: ManifestProvenance


@dataclass(frozen=True, slots=True)
class EvaluationManifest:
    """Fully validated evaluation manifest, converted to immutable model."""

    schema_version: str
    suite_id: str
    suite_revision: int
    scenarios: tuple[EvaluationScenario, ...]


@dataclass(frozen=True, slots=True)
class ScenarioRunSummary:
    """Per-scenario outcome in an evaluation run."""

    scenario_id: str
    passed: bool
    checks_total: int
    checks_passed: int
    checks_failed: int


@dataclass(frozen=True, slots=True)
class EvaluationRunSummary:
    """Typed summary envelope for an evaluation run.

    All fields are validated when reading back to detect stale/mismatched data.
    """

    run_id: str
    suite_id: str
    suite_revision: int
    manifest_sha256: str
    scenario_ids: tuple[str, ...]
    status: RunStatus
    completed_at: str
    code_commit_sha: str | None
    passed: bool
    scenario_results: tuple[ScenarioRunSummary, ...]
