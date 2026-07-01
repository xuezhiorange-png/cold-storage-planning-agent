"""Production scheme generation command and application ports.

Defines the typed immutable command for production scheme generation,
read ports for SourceBinding and weight-set revision, the mapping
from five typed orchestration snapshots to scheme domain inputs, and
the trusted readback port for production scheme runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from cold_storage.modules.schemes.domain.models import WeightCriterion

# ── Production command ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GenerateProductionSchemeCommand:
    """Immutable production scheme generation request.

    ``source_binding_id`` is the sole source-selection identity.
    ``weight_set_revision_id`` is the sole scoring-policy identity.
    project/version identity comes from the verified binding.
    """

    source_binding_id: str
    weight_set_revision_id: str
    profile_codes: tuple[str, ...]
    profile_parameters: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    actor: str = ""
    correlation_id: str = ""


# ── Source binding read port ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SourceBindingSnapshot:
    """Read model for a persisted SourceBindingRecord."""

    id: str
    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_run_attempt_id: str
    orchestration_fingerprint: str
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str
    per_calculation_result_hashes: dict[str, str]
    combined_source_hash: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class CalculationRunSnapshot:
    """Read model for a CalculationRunRecord used in source verification."""

    id: str
    project_id: str
    project_version_id: str
    orchestration_identity_id: str
    orchestration_run_attempt_id: str
    orchestration_fingerprint: str | None
    calculator_name: str
    calculator_version: str
    calculation_type: str
    execution_snapshot_id: str
    coefficient_context_id: str
    input_hash: str
    result_snapshot: dict[str, Any]
    result_hash: str
    schema_version: str | None
    formulas: list[dict[str, Any]]
    coefficients: list[dict[str, Any]]
    assumptions: list[str]
    warnings: list[dict[str, Any]]
    source_references: list[dict[str, Any]]
    upstream_calculation_ids: dict[str, str]
    requires_review: bool


@dataclass(frozen=True, slots=True)
class AttemptSnapshot:
    """Read model for an OrchestrationRunAttemptRecord."""

    id: str
    identity_id: str
    status: str
    source_binding_id: str | None


class SourceBindingReadPort(Protocol):
    """Read-only port for loading SourceBinding and associated records."""

    def load_binding(self, session: Any, /, *, binding_id: str) -> SourceBindingSnapshot | None: ...

    def load_calculation_run(
        self, session: Any, /, *, run_id: str
    ) -> CalculationRunSnapshot | None: ...

    def load_attempt(self, session: Any, /, *, attempt_id: str) -> AttemptSnapshot | None: ...

    def load_authoritative_attempt_id(self, session: Any, /, *, identity_id: str) -> str | None: ...


# ── Weight revision read port ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WeightSetRevisionSnapshot:
    """Read model for an approved SchemeWeightSetRevisionRecord."""

    id: str
    weight_set_id: str
    code: str
    revision: int
    status: str
    content: dict[str, Any]
    content_hash: str
    generator_compatibility_version: str
    approved_at: Any  # datetime
    approved_by: str
    criteria: tuple[WeightCriterion, ...]


class WeightRevisionReadPort(Protocol):
    """Read-only port for loading approved weight-set revisions."""

    def load_approved_revision(
        self, session: Any, /, *, revision_id: str
    ) -> WeightSetRevisionSnapshot | None: ...


# ── Domain mapping result ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class VerifiedSourceMapping:
    """Verified mapping from five typed snapshots to scheme domain inputs.

    Produced by independent re-verification of the SourceBinding and
    its five CalculationRun slots.  Power source is the sole authority
    for whole-project installed power.
    """

    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_attempt_id: str
    orchestration_fingerprint: str
    combined_source_hash: str
    binding_schema_version: str
    requires_review: bool

    # Zone
    zone_result_snapshot: dict[str, Any]
    zone_result_hash: str

    # Cooling load
    cooling_load_result_snapshot: dict[str, Any]
    cooling_load_result_hash: str

    # Equipment
    equipment_result_snapshot: dict[str, Any]
    equipment_result_hash: str

    # Power — sole authority for installed power
    power_result_snapshot: dict[str, Any]
    power_result_hash: str

    # Investment
    investment_result_snapshot: dict[str, Any]
    investment_result_hash: str

    # Per-calculation hash map (recomputed)
    per_calculation_result_hashes: dict[str, str]

    # Five slot IDs
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str


# ── Production scheme run repository port ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class PersistedSchemeRun:
    """Complete read model for a persisted production SchemeRun.

    Contains all provenance fields for P0-6 complete production provenance.
    """

    id: str
    project_id: str
    project_version_id: str
    content_hash: str
    source_mode: str

    # Source binding identity
    source_binding_id: str | None = None
    source_contract_version: str | None = None
    binding_schema_version: str | None = None

    # Execution provenance
    execution_snapshot_id: str | None = None
    coefficient_context_id: str | None = None
    orchestration_identity_id: str | None = None
    authoritative_attempt_id: str | None = None
    orchestration_fingerprint: str | None = None

    # Five calculation run IDs
    zone_calculation_id: str | None = None
    cooling_load_calculation_id: str | None = None
    equipment_calculation_id: str | None = None
    power_calculation_id: str | None = None
    investment_calculation_id: str | None = None

    # Five result hashes
    zone_result_hash: str | None = None
    cooling_load_result_hash: str | None = None
    equipment_result_hash: str | None = None
    power_result_hash: str | None = None
    investment_result_hash: str | None = None

    # Combined source hash
    combined_source_hash: str | None = None

    # Weight set provenance
    weight_set_id: str | None = None
    weight_set_revision_id: str | None = None
    weight_set_content_hash: str | None = None
    weight_set_generator_compatibility_version: str | None = None

    # Generator
    generator_version: str | None = None

    # Profile selection
    profile_codes: tuple[str, ...] = ()
    profile_parameters: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Candidates
    candidates_count: int = 0
    candidates_snapshot: list[dict[str, Any]] = field(default_factory=list)
    score_breakdowns_snapshot: list[dict[str, Any]] = field(default_factory=list)

    # Recommendation
    recommended_scheme_code: str | None = None


class ProductionSchemeRunRepository(Protocol):
    """Write port for persisting production scheme runs.

    The application service owns transaction lifecycle via UnitOfWork.
    This repository only performs add/flush operations within the caller's
    session.  It MUST NOT commit, rollback, close, or create sessions.
    """

    def save_production_run(
        self,
        session: Any,
        /,
        *,
        run_id: str,
        project_id: str,
        project_version_id: str,
        weight_set_id: str,
        status: str,
        generator_version: str,
        source_snapshot_hash: str,
        input_snapshot: dict[str, Any],
        assumption_snapshot: dict[str, Any],
        comparison_snapshot: dict[str, Any],
        candidates_snapshot: dict[str, Any],
        requires_review: bool,
        recommended_scheme_code: str | None,
        warning_messages: list[str],
        content_hash: str,
        source_mode: str,
        source_binding_id: str,
        source_contract_version: str,
        binding_schema_version: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        authoritative_attempt_id: str,
        orchestration_fingerprint: str,
        zone_calculation_id: str,
        cooling_load_calculation_id: str,
        equipment_calculation_id: str,
        power_calculation_id: str,
        investment_calculation_id: str,
        zone_result_hash: str,
        cooling_load_result_hash: str,
        equipment_result_hash: str,
        power_result_hash: str,
        investment_result_hash: str,
        combined_source_hash: str,
        weight_set_revision_id: str,
        weight_set_content_hash: str,
        weight_set_generator_compatibility_version: str,
        profile_codes: tuple[str, ...],
        profile_parameters: dict[str, dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> PersistedSchemeRun: ...


# ── Production scheme run read port ────────────────────────────────────────


class ProductionSchemeRunReadPort(Protocol):
    """Read port for loading persisted production scheme runs and candidates.

    Used by the trusted readback path to independently verify a persisted
    production SchemeRun's integrity.
    """

    def load_production_run(self, session: Any, /, *, run_id: str) -> PersistedSchemeRun | None: ...

    def load_candidates(self, session: Any, /, *, run_id: str) -> list[SchemeCandidateSnapshot]: ...


@dataclass(frozen=True, slots=True)
class SchemeCandidateSnapshot:
    """Read model for a persisted SchemeCandidateRecord."""

    id: str
    scheme_run_id: str
    scheme_code: str
    profile_code: str
    feasible: bool
    rank: int | None
    total_score: Any  # Decimal or None
    score_breakdown_snapshot: dict[str, Any]
    constraint_results: list[dict[str, Any]]
    result_snapshot: dict[str, Any]
