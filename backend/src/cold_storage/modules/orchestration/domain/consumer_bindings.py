"""Canonical calculator identities for downstream consumers (V0.5 P3).

Workflow, scheme, and report modules MUST use the same five persisted
calculator identities defined in :mod:`dag`. Supplemental calculators
such as ``power_configuration`` MUST NOT satisfy canonical slots.
"""

from __future__ import annotations

from cold_storage.modules.orchestration.domain.dag import (
    CALCULATOR_BINDINGS,
    ORCHESTRATION_STAGE_ORDER,
)

CANONICAL_CALCULATOR_NAMES: frozenset[str] = frozenset(CALCULATOR_BINDINGS.values())

CANONICAL_STAGE_ORDER: tuple[str, ...] = ORCHESTRATION_STAGE_ORDER

STAGE_TO_CALCULATOR_NAME: dict[str, str] = dict(CALCULATOR_BINDINGS)

CALCULATOR_NAME_TO_STAGE: dict[str, str] = {
    calculator_name: stage for stage, calculator_name in CALCULATOR_BINDINGS.items()
}

SUPPLEMENTAL_ONLY_CALCULATOR_NAMES: frozenset[str] = frozenset({"power_configuration"})


def resolve_canonical_calculator_name(calculator_name: str) -> str | None:
    """Resolve a persisted calculator_name to its canonical identity.

    Returns ``None`` for supplemental-only rows and unknown short-name aliases
    that must not satisfy canonical slots.
    """
    if calculator_name in SUPPLEMENTAL_ONLY_CALCULATOR_NAMES:
        return None
    if calculator_name in CANONICAL_CALCULATOR_NAMES:
        return calculator_name
    return None


def stage_for_canonical_calculator(calculator_name: str) -> str | None:
    """Return orchestration stage for a canonical calculator identity."""
    return CALCULATOR_NAME_TO_STAGE.get(calculator_name)
