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
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

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
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    SOURCE_SNAPSHOT_SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_attempt_id: str
    calculation_type: str
    calculator_id: str
    calculator_version: str
    source_snapshot_schema_version: str
    requires_review: bool
    upstream_calculation_ids: dict[str, str]

    @field_validator(
        "project_id",
        "project_version_id",
        "execution_snapshot_id",
        "coefficient_context_id",
        "orchestration_identity_id",
        "orchestration_attempt_id",
        "calculation_type",
        "calculator_id",
        "calculator_version",
        "source_snapshot_schema_version",
        mode="after",
    )
    @classmethod
    def _require_non_empty_str(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v

    def to_canonical_dict(self) -> dict[str, object]:
        """Produce the canonical, deterministic representation for hashing.

        Keys are sorted.  Decimal values are canonicalized to base-10 strings.
        """
        raw = self.model_dump()
        canonicalized: dict[str, object] = {}
        for key in sorted(raw):
            canonicalized[key] = _canonicalize_value(raw[key])
        return canonicalized

    @staticmethod
    def result_hash(content: dict[str, object]) -> str:
        """Compute SHA-256 of the canonical JSON encoding of *content*."""
        canonical = _canonicalize_value(content)
        payload = json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


# ── Stage-specific subclasses ───────────────────────────────────────────────


class ZoneSourceSnapshotV1(SourceSnapshotContentV1):
    """Zone stage source snapshot.

    Upstream dependencies: none (zone is the root of the DAG).
    Calculator: cold_room_zone_plan.
    """

    calculation_type: str = "zone"
    calculator_id: str = "cold_room_zone_plan"
    upstream_calculation_ids: dict[str, str] = {}

    # Business payload fields (zone-specific calculator output)
    room_length_m: Decimal
    room_width_m: Decimal
    room_height_m: Decimal
    floor_area_m2: Decimal
    volume_m3: Decimal
    storage_capacity_kg: Decimal
    target_storage_temp_c: Decimal
    target_product_type: str

    @field_validator(
        "room_length_m",
        "room_width_m",
        "room_height_m",
        "floor_area_m2",
        "volume_m3",
        "storage_capacity_kg",
        "target_storage_temp_c",
        mode="after",
    )
    @classmethod
    def _reject_non_finite_decimal(cls, v: Decimal) -> Decimal:
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        return v

    @field_validator("target_product_type", mode="after")
    @classmethod
    def _require_non_empty_product_type(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v


class CoolingLoadSourceSnapshotV1(SourceSnapshotContentV1):
    """Cooling load stage source snapshot.

    Upstream dependencies: zone.
    Calculator: cooling_load.
    """

    calculation_type: str = "cooling_load"
    calculator_id: str = "cooling_load"

    # Business payload fields (cooling load calculator output)
    transmission_load_kw: Decimal
    product_load_kw: Decimal
    internal_load_kw: Decimal
    infiltration_load_kw: Decimal
    total_cooling_load_kw: Decimal
    safety_factor: Decimal

    @field_validator(
        "transmission_load_kw",
        "product_load_kw",
        "internal_load_kw",
        "infiltration_load_kw",
        "total_cooling_load_kw",
        "safety_factor",
        mode="after",
    )
    @classmethod
    def _reject_non_finite_decimal(cls, v: Decimal) -> Decimal:
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        return v


class EquipmentSourceSnapshotV1(SourceSnapshotContentV1):
    """Equipment stage source snapshot.

    Upstream dependencies: cooling_load.
    Calculator: equipment.
    """

    calculation_type: str = "equipment"
    calculator_id: str = "equipment"

    # Business payload fields (equipment calculator output)
    condensing_unit_model: str
    evaporator_model: str
    refrigerant_type: str
    evaporating_temp_c: Decimal
    condensing_temp_c: Decimal
    cooling_capacity_kw: Decimal
    number_of_evaporators: int

    @field_validator("condensing_unit_model", "evaporator_model", "refrigerant_type", mode="after")
    @classmethod
    def _require_non_empty_str_field(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v

    @field_validator(
        "evaporating_temp_c",
        "condensing_temp_c",
        "cooling_capacity_kw",
        mode="after",
    )
    @classmethod
    def _reject_non_finite_decimal(cls, v: Decimal) -> Decimal:
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        return v

    @field_validator("number_of_evaporators", mode="after")
    @classmethod
    def _require_positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"must be >= 1, got {v}")
        return v


class PowerSourceSnapshotV1(SourceSnapshotContentV1):
    """Power stage source snapshot.

    Upstream dependencies: equipment.
    Calculator: installed_power.
    """

    calculation_type: str = "power"
    calculator_id: str = "installed_power"

    # Business payload fields (power calculator output)
    total_installed_power_kw_e: Decimal
    compressor_power_kw_e: Decimal
    condenser_fan_power_kw_e: Decimal
    evaporator_fan_power_kw_e: Decimal
    lighting_power_kw_e: Decimal
    defrost_power_kw_e: Decimal

    @field_validator(
        "total_installed_power_kw_e",
        "compressor_power_kw_e",
        "condenser_fan_power_kw_e",
        "evaporator_fan_power_kw_e",
        "lighting_power_kw_e",
        "defrost_power_kw_e",
        mode="after",
    )
    @classmethod
    def _reject_non_finite_decimal(cls, v: Decimal) -> Decimal:
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        return v


class InvestmentSourceSnapshotV1(SourceSnapshotContentV1):
    """Investment stage source snapshot.

    Upstream dependencies: zone, power.
    Calculator: investment_estimate.
    """

    calculation_type: str = "investment"
    calculator_id: str = "investment_estimate"

    # Business payload fields (investment calculator output)
    equipment_cost_usd: Decimal
    installation_cost_usd: Decimal
    electrical_cost_usd: Decimal
    insulation_cost_usd: Decimal
    total_investment_usd: Decimal
    currency: str

    @field_validator(
        "equipment_cost_usd",
        "installation_cost_usd",
        "electrical_cost_usd",
        "insulation_cost_usd",
        "total_investment_usd",
        mode="after",
    )
    @classmethod
    def _reject_non_finite_decimal(cls, v: Decimal) -> Decimal:
        if v.is_nan() or v.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {v!r}")
        return v

    @field_validator("currency", mode="after")
    @classmethod
    def _require_non_empty_currency(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty or whitespace")
        return v
