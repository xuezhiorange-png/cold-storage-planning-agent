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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    ``warnings``, and ``source_references`` — all as opaque dicts/lists.
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

    # ── Business payload fields (opaque) ────────────────────────────────
    result_snapshot: dict[str, Any]
    formulas: list[dict[str, Any]]
    coefficients: list[dict[str, Any]]
    assumptions: list[str]
    warnings: list[dict[str, Any]]
    source_references: list[dict[str, Any]]

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


class CoolingLoadSourceSnapshotV1(SourceSnapshotContentV1):
    """Cooling load stage source snapshot.

    Upstream dependencies: zone.
    Calculator: cooling_load.
    """

    calculation_type: Literal["cooling_load"] = "cooling_load"
    calculator_id: Literal["cooling_load"] = "cooling_load"
    calculator_version: Literal["1.0.0"] = "1.0.0"


class EquipmentSourceSnapshotV1(SourceSnapshotContentV1):
    """Equipment stage source snapshot.

    Upstream dependencies: cooling_load.
    Calculator: equipment.
    """

    calculation_type: Literal["equipment"] = "equipment"
    calculator_id: Literal["equipment"] = "equipment"
    calculator_version: Literal["1.0.0"] = "1.0.0"


class PowerSourceSnapshotV1(SourceSnapshotContentV1):
    """Power stage source snapshot.

    Upstream dependencies: equipment.
    Calculator: installed_power.
    """

    calculation_type: Literal["power"] = "power"
    calculator_id: Literal["installed_power"] = "installed_power"
    calculator_version: Literal["1.0.0"] = "1.0.0"


class InvestmentSourceSnapshotV1(SourceSnapshotContentV1):
    """Investment stage source snapshot.

    Upstream dependencies: zone, power.
    Calculator: investment_estimate.
    """

    calculation_type: Literal["investment"] = "investment"
    calculator_id: Literal["investment_estimate"] = "investment_estimate"
    calculator_version: Literal["1.0.0"] = "1.0.0"
