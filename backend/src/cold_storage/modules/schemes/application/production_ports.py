"""Production scheme generation command and application ports.

Defines the typed immutable command for production scheme generation,
read ports for SourceBinding and weight-set revision, and the mapping
from five typed orchestration snapshots to scheme domain inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

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
    authoritative: bool = True


class SourceBindingReadPort(Protocol):
    """Read-only port for loading SourceBinding and associated records."""

    def load_binding(self, session: Any, /, *, binding_id: str) -> SourceBindingSnapshot | None: ...

    def load_calculation_run(
        self, session: Any, /, *, run_id: str
    ) -> CalculationRunSnapshot | None: ...

    def load_attempt(self, session: Any, /, *, attempt_id: str) -> AttemptSnapshot | None: ...


# ── Weight revision read port ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WeightCriterion:
    """Single criterion within an approved weight-set revision."""

    criterion_code: str
    weight: Decimal
    direction: str  # "higher_is_better" | "lower_is_better" | "binary_pass"
    normalization_method: str = "min_max"
    hard_constraint: bool = False
    description: str = ""


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
