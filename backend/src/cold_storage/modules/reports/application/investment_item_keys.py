"""Reports-owned mapping from persisted investment items to catalog keys.

The investment calculator may emit a stable English ``item_key`` next to the
Chinese display ``item_name``. Legacy persisted rows have only ``item_name``.
This module maps those known demo labels to catalog suffixes and must not
import ``cold_storage.modules.calculations``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

LEGACY_INVESTMENT_ITEM_NAME_TO_KEY: dict[str, str] = {
    "土建及钢结构": "civil_works_and_steel_structure",
    "冷库制冷设备": "cold_storage_refrigeration_equipment",
    "高低压配电": "high_low_voltage_distribution",
    "住宿及生活区": "accommodation_and_living_area",
    "监控及开厂物资": "monitoring_and_startup_supplies",
}


def resolve_investment_breakdown_key(item: Mapping[str, Any]) -> str | None:
    """Return a stable investment breakdown key, or None when the row is empty.

    Prefers a non-empty persisted ``item_key``. Otherwise maps known Chinese
    ``item_name`` labels. Unmapped non-empty names return None so the caller
    can fail closed.
    """
    raw_key = item.get("item_key")
    if isinstance(raw_key, str) and raw_key.strip():
        return raw_key.strip()
    item_name = item.get("item_name")
    if isinstance(item_name, str):
        stripped = item_name.strip()
        if not stripped:
            return None
        return LEGACY_INVESTMENT_ITEM_NAME_TO_KEY.get(stripped)
    return None
