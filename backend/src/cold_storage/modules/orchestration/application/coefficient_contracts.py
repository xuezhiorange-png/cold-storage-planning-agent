"""Coefficient canonical contracts shared between application and infrastructure.

These helpers are pure — no SQLAlchemy, no infrastructure dependencies.
They define the canonical sort order, content contract, frozen resolution
criteria, and calculator-coefficient requirement registry for coefficient
items, used by both the resolver (infrastructure) and candidate validation
(application).

The calculator-coefficient requirement registry is the authoritative source
for which coefficient codes each calculator/version requires.  It replaces
the previous product-level placeholder.  All codes in the registry MUST
correspond to real definitions in the coefficient catalog seed data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# ── Calculator-coefficient requirement contract ─────────────────────────


@dataclass(frozen=True, slots=True)
class CalculatorCoefficientRequirement:
    """Immutable binding of a calculator version to its required coefficient codes.

    ``calculator_name`` and ``calculator_version`` MUST match entries in
    the orchestration ``_CALCULATOR_VERSION_VECTOR``.
    ``required_codes`` MUST contain only real coefficient definition codes
    from the catalog seed data.
    """

    calculator_name: str
    calculator_version: str
    required_codes: tuple[str, ...]


# ── Frozen calculator-coefficient requirement registry ──────────────────
#
# Key: (calculator_name, calculator_version)
# Value: tuple of required coefficient definition codes
#
# All codes below correspond to real definitions in the coefficient catalog
# seed data (area.*, pallet.*, power.*, investment.*).
# Changing this registry changes the orchestration definition/version
# fingerprint authority via _CALCULATOR_VERSION_VECTOR.
#
# Formal contract (frozen 2026-06-29):
#   calculator_name: zone/cooling_load/equipment/power/investment
#   calculator_version: 1.0.0 (matches _CALCULATOR_VERSION_VECTOR)
#   Each code's purpose and consumer:
#     area.circulation_allowance_ratio — zone calculator, circulation area ratio
#     area.auxiliary_area_ratio — zone calculator, auxiliary area ratio
#     pallet.net_load_kg — equipment calculator, net pallet load
#     pallet.turnover_factor — equipment calculator, pallet turnover
#     power.design_margin_ratio — cooling_load/power calculator, design margin
#     power.standby_ratio — power calculator, standby power ratio
#     investment.building_unit_cost — investment calculator, building cost/m²
#     investment.refrigeration_equipment_ratio — investment, refrigeration cost/m²
#     investment.electrical_installation_ratio — investment, electrical cost/m²
#     investment.other_expenses_ratio — investment, other expenses ratio
#
# Registry version must be bumped when any entry changes.
# This is a new authority frozen in this phase — not derived from existing
# production calculator consumer code, which is not yet implemented (Task 11+).

REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION: Mapping[
    tuple[str, str],
    tuple[str, ...],
] = {
    ("zone", "1.0.0"): (
        "area.circulation_allowance_ratio",
        "area.auxiliary_area_ratio",
    ),
    ("cooling_load", "1.0.0"): ("power.design_margin_ratio",),
    ("equipment", "1.0.0"): (
        "pallet.net_load_kg",
        "pallet.turnover_factor",
    ),
    ("power", "1.0.0"): (
        "power.design_margin_ratio",
        "power.standby_ratio",
    ),
    ("investment", "1.0.0"): (
        "investment.building_unit_cost",
        "investment.refrigeration_equipment_ratio",
        "investment.electrical_installation_ratio",
        "investment.other_expenses_ratio",
    ),
}


def derive_required_codes_for_version_vector(
    calculator_version_vector: Mapping[str, str],
) -> tuple[str, ...]:
    """Derive the authoritative required coefficient codes from a calculator
    version vector (e.g. ``_CALCULATOR_VERSION_VECTOR``).

    Returns a sorted, deduplicated tuple of all required codes across all
    calculators in the vector.  Raises ``ValueError`` if a calculator/version
    pair is not found in the registry.
    """
    codes_set: set[str] = set()
    for calc_name, calc_version in sorted(calculator_version_vector.items()):
        key = (calc_name, calc_version)
        if key not in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION:
            raise ValueError(
                f"Calculator {key!r} not found in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION"
            )
        codes_set.update(REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION[key])
    return tuple(sorted(codes_set))


# ── Frozen coefficient requirement set ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class FrozenCoefficientRequirementSet:
    """Immutable snapshot of the authoritative required coefficient set.

    Carries the registry version and calculator version vector that
    produced the required codes, plus a hash for integrity verification.
    """

    registry_version: str
    calculator_version_vector: Mapping[str, str]
    required_codes: tuple[str, ...]
    requirement_hash: str


# ── Frozen resolution criteria ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class FrozenCoefficientResolutionCriteria:
    """Authoritative resolution criteria derived from a frozen ProjectVersion
    and the calculator-coefficient requirement registry.

    All fields are extracted from the ProjectVersion input_snapshot,
    ProjectRecord, and the frozen requirement registry — never from caller
    self-attestation.

    ``product_category`` comes from ProjectRecord (authoritative).
    ``requirement_registry_version``, ``calculator_version_vector``,
    ``required_codes``, and ``requirement_hash`` come from the frozen
    requirement registry.  These are passed through to the resolver and
    persisted in the coefficient context content.
    """

    project_id: str
    project_version_id: str
    product_category: str | None = None
    product_type: str | None = None
    zone_types: tuple[str, ...] = ()
    process_types: tuple[str, ...] = ()
    requirement_registry_version: str = ""
    calculator_version_vector: Mapping[str, str] = ()  # type: ignore[assignment]
    required_codes: tuple[str, ...] = ()
    requirement_hash: str = ""

    def __post_init__(self) -> None:
        # Ensure calculator_version_vector is always a Mapping (not bare tuple)
        if not isinstance(self.calculator_version_vector, Mapping):
            object.__setattr__(self, "calculator_version_vector", {})


# ── Canonical item contracts ────────────────────────────────────────────


def coefficient_item_sort_key(item: Mapping[str, object]) -> tuple[str, str]:
    """Sort coefficient items by definition code then revision_id."""
    return (str(item.get("code", "")), str(item.get("revision_id", "")))


def canonical_revision_ids(
    items: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Return sorted revision IDs from canonical-order coefficient items."""
    sorted_items = sorted(items, key=coefficient_item_sort_key)
    return tuple(str(it["revision_id"]) for it in sorted_items)


# ── Required-code structure validation ──────────────────────────────────


def validate_required_codes(
    raw: object,
    *,
    field_name: str = "required_codes",
) -> tuple[str, ...]:
    """Validate and canonicalize a raw required codes value.

    Rules:
    - Must be a list or tuple
    - Each element must be a non-empty string (after strip)
    - No duplicates
    - No blank or non-string members
    - Canonical order: sorted
    - Malformed data raises ``CoefficientResolutionError``

    Returns a sorted, deduplicated tuple of validated codes.
    Never silently drops illegal members.
    """
    from cold_storage.modules.orchestration.domain.errors import (
        CoefficientResolutionError,
    )

    if raw is None:
        return ()

    if not isinstance(raw, (list, tuple)):
        raise CoefficientResolutionError(
            field_name,
            f"required_codes must be a list or tuple, got {type(raw).__name__}",
        )

    validated: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise CoefficientResolutionError(
                field_name,
                f"required_codes[{i}] must be a string, got {type(item).__name__}: {item!r}",
            )
        stripped = item.strip()
        if not stripped:
            raise CoefficientResolutionError(
                field_name,
                f"required_codes[{i}] must not be blank, got {item!r}",
            )
        if stripped in seen:
            raise CoefficientResolutionError(
                field_name,
                f"required_codes[{i}] duplicate: {stripped!r}",
            )
        seen.add(stripped)
        validated.append(stripped)

    return tuple(sorted(validated))


def validate_string_sequence(
    raw: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Validate and canonicalize a raw string sequence (zone_types, process_types).

    Rules:
    - Accepts a single non-empty string or list/tuple of strings
    - Every member must be a non-empty string (after strip)
    - No duplicates
    - No blank or non-string members
    - No silent filtering — all members validated
    - Returns canonical sorted tuple
    - Illegal input raises ``CoefficientResolutionError``
    """
    from cold_storage.modules.orchestration.domain.errors import (
        CoefficientResolutionError,
    )

    if raw is None:
        return ()

    # Single string
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            raise CoefficientResolutionError(
                field_name,
                f"{field_name} must not be blank",
            )
        return (stripped,)

    if not isinstance(raw, (list, tuple)):
        raise CoefficientResolutionError(
            field_name,
            f"{field_name} must be a string, list, or tuple, got {type(raw).__name__}",
        )

    validated: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            raise CoefficientResolutionError(
                field_name,
                f"{field_name}[{i}] must be a string, got {type(item).__name__}: {item!r}",
            )
        stripped = item.strip()
        if not stripped:
            raise CoefficientResolutionError(
                field_name,
                f"{field_name}[{i}] must not be blank, got {item!r}",
            )
        if stripped in seen:
            raise CoefficientResolutionError(
                field_name,
                f"{field_name}[{i}] duplicate: {stripped!r}",
            )
        seen.add(stripped)
        validated.append(stripped)

    return tuple(sorted(validated))
