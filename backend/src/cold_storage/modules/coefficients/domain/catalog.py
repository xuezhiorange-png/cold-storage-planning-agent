"""Canonical coefficient catalog manifest.

Defines the authoritative set of coefficient definitions that must exist in
the database.  This module is the single source-of-truth for *which* codes
are expected; the calculator-coefficient requirement registry
(``coefficient_contracts``) is a separate authority for *which calculators
use which codes*.

Use :func:`seed_catalog` from the infrastructure seed module to populate
the database idempotently.
"""

from __future__ import annotations

COEFFICIENT_CATALOG: list[dict[str, object]] = [
    {
        "code": "area.circulation_allowance_ratio",
        "name": "Circulation Allowance Ratio",
        "description": "Area calculator: circulation area ratio",
        "category": "area",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "area.auxiliary_area_ratio",
        "name": "Auxiliary Area Ratio",
        "description": "Area calculator: auxiliary area ratio",
        "category": "area",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "pallet.net_load_kg",
        "name": "Net Pallet Load",
        "description": "Equipment calculator: net pallet load",
        "category": "pallet",
        "canonical_unit": "kg",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "pallet.turnover_factor",
        "name": "Pallet Turnover Factor",
        "description": "Equipment calculator: pallet turnover",
        "category": "pallet",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "power.design_margin_ratio",
        "name": "Design Margin Ratio",
        "description": "Power/cooling_load calculator: design margin",
        "category": "power",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "power.standby_ratio",
        "name": "Standby Power Ratio",
        "description": "Power calculator: standby ratio",
        "category": "power",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "investment.building_unit_cost",
        "name": "Building Unit Cost",
        "description": "Investment calculator: building cost per m\u00b2",
        "category": "investment",
        "canonical_unit": "CNY/m2",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "investment.refrigeration_equipment_ratio",
        "name": "Refrigeration Equipment Ratio",
        "description": "Investment calculator: refrigeration cost ratio",
        "category": "investment",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "investment.electrical_installation_ratio",
        "name": "Electrical Installation Ratio",
        "description": "Investment calculator: electrical cost ratio",
        "category": "investment",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
    {
        "code": "investment.other_expenses_ratio",
        "name": "Other Expenses Ratio",
        "description": "Investment calculator: other expenses ratio",
        "category": "investment",
        "canonical_unit": "ratio",
        "value_type": "decimal",
        "scope_type": "global",
    },
]
