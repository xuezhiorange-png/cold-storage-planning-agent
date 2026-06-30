"""Typed five-stage source snapshot content models for Transaction B.

Each model is a frozen, hashable, canonical representation of everything
that went into a single calculation stage.  The ``to_canonical_dict()``
method produces deterministic output suitable for SHA-256 hashing.

Rules:
- Decimal values are canonicalized to base-10 strings (no binary float drift).
- NaN, Infinity, -Infinity are rejected at construction time.
- Unknown fields are rejected (Pydantic strict + extra='forbid').
- ``to_canonical_dict()`` produces sorted-key output with canonical Decimals.
- ``result_hash()`` is SHA-256 of canonical JSON.
"""

from __future__ import annotations

import hashlib
import json
import math
import re as _re
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── NaN/Infinity string pattern ─────────────────────────────────────────────

_NAN_INF_PATTERN = _re.compile(r"^[+-]?(nan|inf|infinity)$", _re.IGNORECASE)


def _reject_nan_inf_string(v: str) -> str:
    """Reject string representations of NaN and Infinity."""
    if _NAN_INF_PATTERN.match(v):
        raise ValueError(f"Non-finite string value not allowed: {v!r}")
    return v


# ── Canonical coercion helpers ──────────────────────────────────────────────


def _coerce_to_canonical_string(v: object) -> str:
    """Coerce a numeric value to a canonical string, rejecting non-finite values.

    Accepts: int, Decimal, float, str.
    Rejects: NaN/Infinity for any type, non-numeric types.
    Floats are converted to string representation (calculator output uses floats).
    """
    if isinstance(v, Decimal):
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        normalized = v.normalize()
        _sign, _digits, exp = normalized.as_tuple()
        if isinstance(exp, int) and exp > 0:
            return str(int(normalized))
        return str(normalized)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"Non-finite float not allowed: {v!r}")
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return _reject_nan_inf_string(v)
    raise TypeError(f"Cannot coerce {type(v).__name__} to string")


def _coerce_numeric_deep(v: object) -> object:
    """Recursively convert Decimals AND floats to strings; reject non-finite values.

    Unlike ``_coerce_decimals_deep``, this function *accepts* plain ``float``
    and converts it to a canonical string.  It is used for nested dict fields
    in result snapshot models where the upstream calculator may have produced
    plain Python floats.
    """
    if isinstance(v, Decimal):
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        normalized = v.normalize()
        _sign, _digits, exp = normalized.as_tuple()
        if isinstance(exp, int) and exp > 0:
            return str(int(normalized))
        return str(normalized)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"Non-finite float not allowed: {v!r}")
        return str(v)
    if isinstance(v, dict):
        return {k: _coerce_numeric_deep(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_coerce_numeric_deep(item) for item in v]
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    raise TypeError(f"Cannot process type {type(v).__name__}: {v!r}")


# ── Canonical JSON / hashing ────────────────────────────────────────────────


def _canonicalize_value(value: object) -> object:
    """Recursively canonicalize a value for deterministic JSON output.

    - Decimal → normalized base-10 string (no binary float).
    - dict → sorted-key dict with canonicalized values.
    - list/tuple → list with canonicalized elements.
    - Rejects NaN, Infinity, -Infinity for numeric types.
    """
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {value!r}")
        normalized = value.normalize()
        _sign, _digits, exp = normalized.as_tuple()
        if isinstance(exp, int) and exp > 0:
            return str(int(normalized))
        return str(normalized)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"Non-finite float not allowed: {value!r}")
        raise TypeError(f"Binary float {value!r} not allowed — use Decimal instead")
    if isinstance(value, dict):
        return {k: _canonicalize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize_value(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"Cannot canonicalize type {type(value).__name__}: {value!r}")


# ── Base class ──────────────────────────────────────────────────────────────


class SourceSnapshotContentV1(BaseModel):
    """Base source snapshot content with common binding fields.

    Frozen and strict: no mutation, no unknown fields after construction.

    Business payload is carried in ``result_snapshot`` (the raw calculator
    result dict), ``formulas``, ``coefficients``, ``assumptions``,
    ``warnings``, and ``source_references`` — all as typed nested models.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── Binding fields (all required) ───────────────────────────────────
    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_attempt_id: str
    orchestration_fingerprint: str
    calculation_type: str
    calculator_id: str
    calculator_version: str
    source_snapshot_schema_version: Literal["1.0.0"]
    requires_review: bool
    upstream_calculation_ids: dict[str, str] = Field(default_factory=dict)

    # ── Business payload fields (typed nested models) ───────────────────
    result_snapshot: dict[str, Any]
    formulas: list[FormulaEntry]
    coefficients: list[CoefficientEntry]
    assumptions: list[str]
    warnings: list[WarningEntry]
    source_references: list[SourceReferenceEntry]

    # ── Validators ──────────────────────────────────────────────────────

    @field_validator(
        "project_id",
        "project_version_id",
        "execution_snapshot_id",
        "coefficient_context_id",
        "orchestration_identity_id",
        "orchestration_attempt_id",
        "orchestration_fingerprint",
        "calculation_type",
        "calculator_id",
        "calculator_version",
        mode="after",
    )
    @classmethod
    def _require_non_empty_str(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v

    @field_validator(
        "result_snapshot",
        "formulas",
        "coefficients",
        "warnings",
        "source_references",
        mode="before",
    )
    @classmethod
    def _coerce_decimals_in_payload(cls, v: object) -> object:
        """Canonicalize Decimals to strings and reject non-finite values.

        Using ``mode="before"`` prevents Pydantic from silently converting
        ``float`` → ``Decimal`` which would introduce binary drift.
        """
        return _coerce_decimals_deep(v)

    @field_validator("assumptions", mode="before")
    @classmethod
    def _coerce_decimals_in_assumptions(cls, v: object) -> object:
        return _coerce_decimals_deep(v)

    # ── Canonical output ────────────────────────────────────────────────

    def to_canonical_dict(self) -> dict[str, object]:
        """Produce the canonical, deterministic representation for hashing.

        Keys are sorted.  Decimal values are canonicalized to base-10 strings.
        """
        raw = self.model_dump()
        canonicalized: dict[str, object] = {}
        for key in sorted(raw):
            canonicalized[key] = _canonicalize_value(raw[key])
        return canonicalized

    def result_hash(self) -> str:
        """Compute SHA-256 of the canonical JSON encoding of this snapshot."""
        canonical = self.to_canonical_dict()
        payload = json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


# ── Decimal coercion helper ─────────────────────────────────────────────────


def _coerce_decimals_deep(v: object) -> object:
    """Recursively convert Decimals to strings; reject floats and non-finite values.

    Called by ``mode="before"`` validators to prevent Pydantic's built-in
    ``float → Decimal`` auto-conversion.
    """
    if isinstance(v, Decimal):
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        normalized = v.normalize()
        _sign, _digits, exp = normalized.as_tuple()
        if isinstance(exp, int) and exp > 0:
            return str(int(normalized))
        return str(normalized)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"Non-finite float not allowed: {v!r}")
        raise TypeError(f"Binary float {v!r} not allowed — use Decimal or str instead")
    if isinstance(v, dict):
        return {k: _coerce_decimals_deep(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_coerce_decimals_deep(item) for item in v]
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    raise TypeError(f"Cannot process type {type(v).__name__}: {v!r}")


# ── Nested traceability models ──────────────────────────────────────────────


class FormulaEntry(BaseModel):
    """Single formula reference used in a calculation stage.

    Frozen, strict, no unknown fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    formula_id: str
    formula_version: str
    expression: str
    description: str

    @field_validator("formula_id", "formula_version", "expression", "description", mode="after")
    @classmethod
    def _require_non_empty_str(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v


class CoefficientEntry(BaseModel):
    """Snapshot of a coefficient value used in a calculation.

    Frozen, strict, no unknown fields.  Numeric values are stored as strings
    to avoid binary float drift.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision_id: str = ""
    code: str
    value: str  # Decimal canonicalized to string
    unit: str
    status: str
    source_type: str = "demo"
    source_reference: str = ""
    requires_review: bool = True

    @field_validator("code", "unit", "status", mode="after")
    @classmethod
    def _require_non_empty_str(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_decimals_in_coefficient(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)


class WarningEntry(BaseModel):
    """Non-fatal issue identified during a calculation.

    Frozen, strict, no unknown fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message", mode="after")
    @classmethod
    def _require_non_empty_str(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v

    @field_validator("details", mode="before")
    @classmethod
    def _coerce_decimals_in_details(cls, v: object) -> object:
        return _coerce_decimals_deep(v)


class SourceReferenceEntry(BaseModel):
    """External source reference used in a calculation.

    Frozen, strict, no unknown fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: str = "demo"
    source_reference: str = ""
    version: str = "demo-1"
    validity_status: str = "unverified"
    approval_status: str = "unverified"
    requires_review: bool = True
    notes: str = ""


# ── Result snapshot models (P0-2 allowlist) ─────────────────────────────────


class ZoneEntry(BaseModel):
    """Single zone within a zone plan result.

    Frozen, strict, no unknown fields.  Matches the zone dict structure
    produced by ColdRoomZonePlanner.plan().
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    zone_code: str
    zone_name: str
    temperature_band: str
    function: str
    daily_throughput_kg_day: str
    design_storage_mass_kg: str
    position_count: int
    required_area_m2: str
    requires_review: bool = True

    # Optional fields that vary by zone type
    pallet_weight_kg: str | None = None
    hours_per_pallet: str | None = None
    working_hours_per_day: str | None = None
    position_hourly_capacity_kg_h: str | None = None
    position_daily_capacity_kg_day: str | None = None
    raw_position_count: int | None = None
    area_basis: dict[str, Any] | None = None
    worker_count: int | None = None
    table_count: int | None = None
    person_daily_capacity_kg_day: str | None = None
    packing_table_area_m2: str | None = None

    @field_validator(
        "daily_throughput_kg_day",
        "design_storage_mass_kg",
        "required_area_m2",
        mode="before",
    )
    @classmethod
    def _coerce_zone_decimal(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)

    @field_validator(
        "pallet_weight_kg",
        "hours_per_pallet",
        "working_hours_per_day",
        "position_hourly_capacity_kg_h",
        "position_daily_capacity_kg_day",
        "person_daily_capacity_kg_day",
        "packing_table_area_m2",
        mode="before",
    )
    @classmethod
    def _coerce_optional_zone_decimal(cls, v: object) -> str | None:
        if v is None:
            return None
        return _coerce_to_canonical_string(v)

    @field_validator("area_basis", mode="before")
    @classmethod
    def _coerce_area_basis(cls, v: object) -> dict[str, Any] | None:
        if v is None:
            return None
        return _coerce_numeric_deep(v)  # type: ignore[return-value]


class ZoneResultSnapshotV1(BaseModel):
    """Zone calculator result — explicit allowlist, extra='forbid'.

    Matches the result dict from ColdRoomZonePlanner.plan():
    - daily_inbound_mass_kg
    - design_daily_mass_kg
    - total_required_area_m2
    - total_area_m2
    - planning_parameters
    - zones
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    daily_inbound_mass_kg: str
    design_daily_mass_kg: str
    total_required_area_m2: str
    total_area_m2: str
    planning_parameters: dict[str, Any]
    zones: list[ZoneEntry]

    @field_validator(
        "daily_inbound_mass_kg",
        "design_daily_mass_kg",
        "total_required_area_m2",
        "total_area_m2",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)

    @field_validator("planning_parameters", mode="before")
    @classmethod
    def _coerce_planning_params(cls, v: object) -> dict[str, Any]:
        return _coerce_numeric_deep(v)  # type: ignore[return-value]


class CoolingLoadResultSnapshotV1(BaseModel):
    """Cooling load calculator result — explicit allowlist, extra='forbid'.

    Matches the result dict from CalculationService.run_cooling_load():
    - total_cooling_load_kw
    - safety_margin_load_kw
    - Individual component load fields
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_cooling_load_kw: str
    safety_margin_load_kw: str
    envelope_heat_transfer_load_kw: str
    product_sensible_heat_load_kw: str
    packaging_load_kw: str
    infiltration_load_kw: str
    personnel_load_kw: str
    lighting_load_kw: str
    evaporator_fan_load_kw: str
    defrost_additional_load_kw: str
    other_configuration_load_kw: str

    @field_validator(
        "total_cooling_load_kw",
        "safety_margin_load_kw",
        "envelope_heat_transfer_load_kw",
        "product_sensible_heat_load_kw",
        "packaging_load_kw",
        "infiltration_load_kw",
        "personnel_load_kw",
        "lighting_load_kw",
        "evaporator_fan_load_kw",
        "defrost_additional_load_kw",
        "other_configuration_load_kw",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)


class EquipmentResultSnapshotV1(BaseModel):
    """Equipment calculator result — explicit allowlist, extra='forbid'.

    Matches the result dict from CalculationService.run_equipment_requirement().
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaporator_total_cooling_capacity_kw: str
    evaporator_quantity: int
    single_evaporator_capacity_kw: str
    compressor_operating_capacity_kw: str
    standby_capacity_kw: str
    condenser_heat_rejection_capacity_kw: str
    evaporation_temperature_c: str
    condensing_temperature_c: str
    defrost_method: str
    review_requirement: str = ""

    @field_validator(
        "evaporator_total_cooling_capacity_kw",
        "single_evaporator_capacity_kw",
        "compressor_operating_capacity_kw",
        "standby_capacity_kw",
        "condenser_heat_rejection_capacity_kw",
        "evaporation_temperature_c",
        "condensing_temperature_c",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)


class PowerEquipmentRowEntry(BaseModel):
    """Single equipment row in a power calculation result.

    Matches the equipment_row dict from planning/application/service.py.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    name: str
    area: str
    quantity: str
    defrost_power_kw: str | None = None
    defrost_total_power_kw: str | None = None
    running_power_kw: str
    total_power_kw: str
    section: str

    @field_validator(
        "quantity",
        "running_power_kw",
        "total_power_kw",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)

    @field_validator("defrost_power_kw", "defrost_total_power_kw", mode="before")
    @classmethod
    def _coerce_optional_decimal_field(cls, v: object) -> str | None:
        if v is None:
            return None
        return _coerce_to_canonical_string(v)


class PowerSummaryRowEntry(BaseModel):
    """Summary row in a power calculation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    basis: str
    total_power_kw: str

    @field_validator("total_power_kw", mode="before")
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)


class PowerItemEntry(BaseModel):
    """Power category item in a power calculation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    installed_power_kw: str
    demand_factor: str
    estimated_demand_kw: str

    @field_validator("installed_power_kw", "demand_factor", "estimated_demand_kw", mode="before")
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)


class PowerResultSnapshotV1(BaseModel):
    """Power calculator result — explicit allowlist, extra='forbid'.

    MUST include total_installed_power_kw_e as the authority field.
    MUST NOT accept equipment power fallback.

    Matches the result dict from build_power_configuration().
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_installed_power_kw_e: str
    total_estimated_demand_kw: str
    equipment_rows: list[PowerEquipmentRowEntry]
    summary_rows: list[PowerSummaryRowEntry]
    items: list[PowerItemEntry]
    assumptions: list[str]

    @field_validator("total_installed_power_kw_e", "total_estimated_demand_kw", mode="before")
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)

    @field_validator("assumptions", mode="before")
    @classmethod
    def _coerce_assumptions(cls, v: object) -> object:
        return _coerce_decimals_deep(v)


class InvestmentItemEntry(BaseModel):
    """Single investment line item.

    Matches the items dict from InvestmentEstimator.estimate():
    - item_name
    - amount_cny
    MUST NOT include usd fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_name: str
    amount_cny: str

    @field_validator("item_name", mode="after")
    @classmethod
    def _require_non_empty_str(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v

    @field_validator("amount_cny", mode="before")
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)


class InvestmentResultSnapshotV1(BaseModel):
    """Investment calculator result — explicit allowlist, extra='forbid'.

    MUST include total_investment_cny (NOT USD).
    MUST NOT include usd fields.

    Matches the result dict from InvestmentEstimator.estimate().
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_investment_cny: str
    items: list[InvestmentItemEntry]

    @field_validator("total_investment_cny", mode="before")
    @classmethod
    def _coerce_decimal_field(cls, v: object) -> str:
        return _coerce_to_canonical_string(v)


# ── Stage-specific subclasses ───────────────────────────────────────────────


class ZoneSourceSnapshotV1(SourceSnapshotContentV1):
    """Zone stage source snapshot.

    Upstream dependencies: none (zone is the root of the DAG).
    Calculator: cold_room_zone_plan.
    """

    calculation_type: Literal["zone"] = "zone"
    calculator_id: Literal["cold_room_zone_plan"] = "cold_room_zone_plan"
    calculator_version: Literal["1.0.0"] = "1.0.0"
    upstream_calculation_ids: dict[str, str] = Field(default_factory=dict)
    result_snapshot: ZoneResultSnapshotV1  # type: ignore[assignment]


class CoolingLoadSourceSnapshotV1(SourceSnapshotContentV1):
    """Cooling load stage source snapshot.

    Upstream dependencies: zone.
    Calculator: cooling_load.
    """

    calculation_type: Literal["cooling_load"] = "cooling_load"
    calculator_id: Literal["cooling_load"] = "cooling_load"
    calculator_version: Literal["1.0.0"] = "1.0.0"
    result_snapshot: CoolingLoadResultSnapshotV1  # type: ignore[assignment]


class EquipmentSourceSnapshotV1(SourceSnapshotContentV1):
    """Equipment stage source snapshot.

    Upstream dependencies: cooling_load.
    Calculator: equipment.
    """

    calculation_type: Literal["equipment"] = "equipment"
    calculator_id: Literal["equipment"] = "equipment"
    calculator_version: Literal["1.0.0"] = "1.0.0"
    result_snapshot: EquipmentResultSnapshotV1  # type: ignore[assignment]


class PowerSourceSnapshotV1(SourceSnapshotContentV1):
    """Power stage source snapshot.

    Upstream dependencies: equipment.
    Calculator: installed_power.
    """

    calculation_type: Literal["power"] = "power"
    calculator_id: Literal["installed_power"] = "installed_power"
    calculator_version: Literal["1.0.0"] = "1.0.0"
    result_snapshot: PowerResultSnapshotV1  # type: ignore[assignment]


class InvestmentSourceSnapshotV1(SourceSnapshotContentV1):
    """Investment stage source snapshot.

    Upstream dependencies: zone, power.
    Calculator: investment_estimate.
    """

    calculation_type: Literal["investment"] = "investment"
    calculator_id: Literal["investment_estimate"] = "investment_estimate"
    calculator_version: Literal["1.0.0"] = "1.0.0"
    result_snapshot: InvestmentResultSnapshotV1  # type: ignore[assignment]
