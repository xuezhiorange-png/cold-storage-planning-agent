"""Charles-authorized V1.8 refrigerated-zone temperature and height catalog.

Indoor design temperature is the cold end of each existing zone-plan
``temperature_band``. Room height is 4.0 m for every refrigerated zone.
Leaves stay ``source_type=demo``, ``validity_status=unverified``,
``requires_review=true``. This module does not compute ``Q = U × A × ΔT``.
"""

from __future__ import annotations

V18_T1_SOURCE = "docs/tasks/V1_8-version-plan.md#V18-T1"
V18_H1_SOURCE = "docs/tasks/V1_8-version-plan.md#V18-H1"
ROOM_HEIGHT_M = "4.0"

# Cold end of REFRIGERATED_ZONE_REGISTRY temperature_band strings.
BAND_COLD_END_C: dict[str, str] = {
    "8~10℃": "8.0",
    "1~3℃": "1.0",
    "-18℃": "-18.0",
}

ZONE_THERMAL_CATALOG_DISCLAIMER_ZH = (
    "室内设计温度取分区规划温区低端（8 / 1 / −18 ℃），层高为演示目录 4.0 m，"
    "货品目标温度与室内设计温度相同"
)


def room_design_temperature_c_for_band(temperature_band: str) -> str:
    """Return the V18-T1 cold-end design temperature. Unknown band fails closed."""
    try:
        return BAND_COLD_END_C[temperature_band]
    except KeyError as exc:
        raise ValueError(
            f"temperature_band {temperature_band!r} has no V18-T1 cold-end mapping"
        ) from exc
