"""Coefficient canonical contracts shared between application and infrastructure.

These helpers are pure — no SQLAlchemy, no infrastructure dependencies.
They define the canonical sort order, content contract, and frozen resolution
criteria for coefficient items, used by both the resolver (infrastructure) and
candidate validation (application).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# ── Frozen resolution criteria ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class FrozenCoefficientResolutionCriteria:
    """Authoritative resolution criteria derived from a frozen ProjectVersion.

    All fields are extracted from the ProjectVersion input_snapshot and
    related project data — never from caller self-attestation.  The caller's
    coefficient_resolution_context is informational only; conflicts with
    frozen criteria are rejected with a typed error.
    """

    project_id: str
    project_version_id: str
    product_type: str | None = None
    zone_types: tuple[str, ...] = ()
    process_types: tuple[str, ...] = ()
    required_codes: tuple[str, ...] = ()


# ── Canonical item contracts ──────────────────────────────────────────────


def coefficient_item_sort_key(item: Mapping[str, object]) -> tuple[str, str]:
    """Sort coefficient items by definition code then revision_id."""
    return (str(item.get("code", "")), str(item.get("revision_id", "")))


def canonical_revision_ids(
    items: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Return sorted revision IDs from canonical-order coefficient items."""
    sorted_items = sorted(items, key=coefficient_item_sort_key)
    return tuple(str(it["revision_id"]) for it in sorted_items)
