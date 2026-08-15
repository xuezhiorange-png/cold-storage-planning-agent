"""Scheme domain models — pure data types, no framework or DB dependencies.

All numeric domain values use ``decimal.Decimal`` for deterministic arithmetic.
Float is only permitted at the DB/JSON serialisation boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4


def _uuid() -> str:
    return str(uuid4())


_REVIEW_REASON_FIELDS = frozenset({"code", "message", "stage", "source_type", "source_id"})
_REVIEW_REASON_STAGES = frozenset({"zone", "cooling_load", "equipment", "power", "investment"})


@dataclass(frozen=True, slots=True)
class ReviewReason:
    """Canonical source-bound reason for a production review requirement.

    The five fields are intentionally closed.  Serialization is kept at this
    explicit boundary so dataclass representation can never become persisted
    evidence or content-hash input.
    """

    code: str
    message: str
    stage: str
    source_type: str
    source_id: str

    def __post_init__(self) -> None:
        for field_name in _REVIEW_REASON_FIELDS:
            value = getattr(self, field_name)
            if type(value) is not str:
                raise TypeError(f"ReviewReason.{field_name} must be str")
        if self.stage not in _REVIEW_REASON_STAGES:
            raise ValueError(f"Unsupported ReviewReason stage: {self.stage!r}")
        if self.source_type != "calculation_run":
            raise ValueError("ReviewReason.source_type must be 'calculation_run'")
        for field_name in ("code", "message", "source_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"ReviewReason.{field_name} must be non-empty")

    def to_json(self) -> dict[str, str]:
        """Return the exact five-field JSON object used by storage and hashes."""
        return {
            "code": self.code,
            "message": self.message,
            "stage": self.stage,
            "source_type": self.source_type,
            "source_id": self.source_id,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, object]) -> ReviewReason:
        """Strictly decode one canonical JSON object."""
        if set(raw) != _REVIEW_REASON_FIELDS:
            raise ValueError("ReviewReason JSON must contain exactly the five canonical fields")
        return cls(
            code=raw["code"],  # type: ignore[arg-type]
            message=raw["message"],  # type: ignore[arg-type]
            stage=raw["stage"],  # type: ignore[arg-type]
            source_type=raw["source_type"],  # type: ignore[arg-type]
            source_id=raw["source_id"],  # type: ignore[arg-type]
        )


def review_reasons_to_json(
    reasons: Iterable[ReviewReason],
) -> list[dict[str, str]]:
    """Serialize canonical reasons without widening their schema."""
    return [reason.to_json() for reason in reasons]


def review_reasons_from_json(raw: object) -> list[ReviewReason]:
    """Strictly decode a persisted JSON array of canonical reasons."""
    if not isinstance(raw, list):
        raise ValueError("ReviewReason JSON must be a list")
    reasons: list[ReviewReason] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("ReviewReason JSON entries must be objects")
        reasons.append(ReviewReason.from_json(item))
    return reasons


# ---------------------------------------------------------------------------
# Source snapshots (consumed from Task 4 / Task 5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneResult:
    """Snapshot of Task 4 zone planning result."""

    zone_code: str
    zone_name: str
    temperature_level: str
    area_m2: Decimal
    position_count: int
    storage_capacity_kg: Decimal
    process_compatibility: str | None = None
    hygiene_zone: str | None = None


@dataclass(frozen=True)
class InvestmentResult:
    """Snapshot of Task 4 investment result."""

    total_investment_cny: Decimal
    zone_investments: dict[str, Decimal]


@dataclass(frozen=True)
class CoolingLoadResult:
    """Snapshot of Task 5 cooling load result."""

    design_cooling_load_kw_r: Decimal
    sensible_load_kw_r: Decimal
    infiltration_load_kw_r: Decimal
    latent_load_kw_r: Decimal | None = None


@dataclass(frozen=True)
class EquipmentResult:
    """Snapshot of Task 5 equipment capability result."""

    compressor_operating_capacity_kw_r: Decimal
    compressor_standby_capacity_kw_r: Decimal
    condenser_heat_rejection_kw: Decimal
    installed_power_kw_e: Decimal
    compressor_installed_capacity_kw_r: Decimal | None = None


@dataclass(frozen=True)
class PowerResult:
    """Whole-project installed power authority from Power calculator."""

    total_installed_power_kw_e: Decimal
    total_estimated_demand_kw: Decimal
    equipment_rows: list[dict[str, object]]
    summary_rows: list[dict[str, object]]
    items: list[dict[str, object]]
    assumptions: list[dict[str, object]]


# ---------------------------------------------------------------------------
# Scheme generation input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemeGenerationInput:
    """All inputs needed for scheme generation — immutable snapshot."""

    project_id: str
    project_version_id: str
    weight_set_id: str
    profile_codes: list[str]
    profile_parameters: dict[str, dict[str, object]]
    source_calculation_ids: dict[str, str]
    source_snapshot_hashes: dict[str, str]
    zone_results: list[ZoneResult]
    investment_result: InvestmentResult
    cooling_load_result: CoolingLoadResult
    equipment_result: EquipmentResult
    generator_version: str
    total_daily_throughput_kg_day: Decimal
    total_storage_capacity_kg: Decimal
    total_position_count: int
    power_result: PowerResult | None = None


# ---------------------------------------------------------------------------
# Scheme profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemeProfile:
    """A deterministic profile defining how to generate scheme candidates."""

    code: str
    name: str
    revision: int = 1
    description: str = ""
    grouping_strategy: str = "baseline"
    splitting_strategy: str = "none"
    max_positions_per_room: int = 0
    max_area_per_room_m2: Decimal = Decimal("0")
    minimum_room_modules: int = 0
    door_strategy: str = "standard"
    redundancy_strategy: str = "none"
    source_type: str = "system"
    revision_status: str = "approved"
    requires_review: bool = False


# ---------------------------------------------------------------------------
# Scheme candidate output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemeRoomModule:
    """A single room module in a scheme candidate."""

    room_code: str
    room_name: str
    zone_codes: list[str]
    temperature_level: str
    area_m2: Decimal
    position_count: int
    storage_capacity_kg: Decimal
    design_cooling_load_kw_r: Decimal
    compressor_operating_capacity_kw_r: Decimal
    compressor_installed_capacity_kw_r: Decimal
    process_compatibility: str | None = None
    hygiene_zone: str | None = None
    door_count: int = 1
    partition_length_proxy_m: Decimal = Decimal("0")


@dataclass(frozen=True)
class SchemeConstraintResult:
    """Result of a single hard constraint check."""

    constraint_code: str
    passed: bool
    detail: str
    expected: object = None
    actual: object = None


@dataclass(frozen=True)
class SchemeMetric:
    """A single computed metric for a scheme candidate."""

    code: str
    value: Decimal
    unit: str
    direction: str  # "higher_is_better", "lower_is_better", "binary_pass"


@dataclass(frozen=True)
class SchemeCriterionScore:
    """Score for one criterion in one candidate."""

    criterion_code: str
    raw_value: Decimal
    unit: str
    direction: str
    weight: Decimal
    min_value: Decimal
    max_value: Decimal
    normalized_score: Decimal
    weighted_contribution: Decimal
    formula: str


@dataclass(frozen=True)
class SchemeScoreBreakdown:
    """Complete scoring breakdown for one candidate."""

    scheme_code: str
    total_score: Decimal
    criterion_scores: list[SchemeCriterionScore]
    diagnostic_only: bool = False


@dataclass(frozen=True)
class SchemeCandidate:
    """A generated scheme candidate with full results."""

    scheme_code: str
    scheme_name: str
    profile_code: str
    feasible: bool
    constraint_results: list[SchemeConstraintResult]
    room_modules: list[SchemeRoomModule]
    zone_assignments: dict[str, list[str]]
    total_area_m2: Decimal
    total_position_count: int
    room_module_count: int
    door_count: int
    partition_length_proxy_m: Decimal
    daily_throughput_kg_day: Decimal
    investment_cny: Decimal
    installed_power_kw_e: Decimal
    design_cooling_load_kw_r: Decimal
    compressor_operating_capacity_kw_r: Decimal
    compressor_installed_capacity_kw_r: Decimal
    compressor_standby_capacity_kw_r: Decimal
    condenser_heat_rejection_kw: Decimal
    metrics: list[SchemeMetric]
    assumptions: list[str]
    warnings: list[str]
    requires_review: bool


@dataclass(frozen=True)
class SchemeComparisonResult:
    """Result of comparing all scheme candidates."""

    candidates: list[SchemeCandidate]
    score_breakdowns: list[SchemeScoreBreakdown]
    recommended_scheme_code: str | None
    recommended_reason: str | None
    requires_review: bool


# ---------------------------------------------------------------------------
# Weight set
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeightCriterion:
    """A single criterion in a weight set."""

    criterion_code: str
    weight: Decimal
    direction: str  # "higher_is_better", "lower_is_better", "binary_pass"
    normalization_method: str = "min_max"
    hard_constraint: bool = False
    description: str = ""


@dataclass(frozen=True)
class SchemeWeightSet:
    """A named set of scoring weights."""

    id: str = field(default_factory=_uuid)
    code: str = ""
    name: str = ""
    revision: int = 1
    status: str = "draft"
    source_type: str = "system"
    criteria: list[WeightCriterion] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    requires_review: bool = True


# ---------------------------------------------------------------------------
# Scheme run (persistent record)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SchemeRun:
    """A complete scheme generation and comparison run."""

    id: str = field(default_factory=_uuid)
    project_id: str = ""
    project_version_id: str = ""
    weight_set_id: str = ""
    status: str = "pending"
    generator_version: str = ""
    source_snapshot_hash: str = ""
    input_snapshot: dict[str, object] = field(default_factory=dict)
    assumption_snapshot: dict[str, object] = field(default_factory=dict)
    comparison_snapshot: dict[str, object] = field(default_factory=dict)
    candidates_snapshot: dict[str, object] = field(default_factory=dict)
    requires_review: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    content_hash: str | None = None
    recommended_scheme_code: str | None = None
    warning_messages: list[ReviewReason] = field(default_factory=list)
    # Phase 1 (Task 11B) schema contract: 0035+0036 made
    # ``scheme_runs.database_backend`` NOT NULL with **no**
    # column-level server_default. The domain model therefore
    # has no Python default; the caller (production application
    # service) must supply the dialect explicitly when
    # constructing a SchemeRun. Defaulting to ``"sqlite"`` here
    # would silently mask any caller-side omission.
    database_backend: str
