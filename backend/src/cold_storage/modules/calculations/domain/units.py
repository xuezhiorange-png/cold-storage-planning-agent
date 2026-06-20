"""Unit management for core planning calculations.

Provides a canonical ``Unit`` enum and conversion helpers so that every
calculator speaks the same language and conversion factors are centralised.
"""

from __future__ import annotations

from enum import StrEnum


class Unit(StrEnum):
    """Canonical engineering units used throughout the calculations."""

    # Mass
    KG = "kg"
    TONNE = "t"

    # Time
    HOUR = "h"
    DAY = "day"

    # People
    PERSON = "person"

    # Pallet / position
    PALLET = "pallet"
    POSITION = "position"

    # Area
    M2 = "m2"

    # Volume
    M3 = "m3"

    # Energy / Power
    KW = "kW"
    KJ = "kJ"
    KWH = "kWh"
    W = "W"
    W_M2_K = "W/(m2·K)"
    KW_R = "kW(r)"
    KW_E = "kW(e)"

    # Temperature
    CELSIUS = "℃"

    # Dimensionless
    RATIO = "ratio"

    # Currency
    CNY = "CNY"

    # Flux (mass per area per time)
    KG_PER_M2 = "kg/m2"
    KG_PER_H = "kg/h"
    KG_PER_DAY = "kg/day"


# ---------------------------------------------------------------------------
# Conversion factors — all expressed as factor × source_unit → target_unit
# Conversion TO base unit (kg, h, m2) from the given unit.
# ---------------------------------------------------------------------------

_TO_BASE: dict[str, float] = {
    Unit.KG: 1.0,
    Unit.TONNE: 1000.0,
    Unit.HOUR: 1.0,
    Unit.DAY: 24.0,
    Unit.PERSON: 1.0,
    Unit.PALLET: 1.0,
    Unit.POSITION: 1.0,
    Unit.M2: 1.0,
    Unit.M3: 1.0,
    Unit.KW: 1.0,
    Unit.KJ: 1.0,
    Unit.CELSIUS: 1.0,
    Unit.RATIO: 1.0,
    Unit.CNY: 1.0,
}


def to_base(value: float | int, unit: Unit) -> float:
    """Convert *value* in *unit* to the base unit (kg for mass, h for time)."""
    factor = _TO_BASE.get(unit.value)
    if factor is None:
        raise ValueError(f"No base conversion for unit '{unit.value}'")
    return float(value) * factor


def tonnes_to_kg(tonnes: float | int) -> float:
    """Convenience: tonnes → kilograms (×1000)."""
    return float(tonnes) * 1000.0


def kg_to_tonnes(kg: float | int) -> float:
    """Convenience: kilograms → tonnes (÷1000)."""
    return float(kg) / 1000.0


def hours_to_days(hours: float | int) -> float:
    """Convenience: hours → days (÷24)."""
    return float(hours) / 24.0


def days_to_hours(days: float | int) -> float:
    """Convenience: days → hours (×24)."""
    return float(days) * 24.0
