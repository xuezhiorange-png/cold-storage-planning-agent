"""Project cooling-load calculator output into a conversation table.

Copies already-calculated plant totals and per-zone kernel fields.
Does not recompute envelope, product, infiltration, internal, or defrost loads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

COOLING_CAPTION = (
    "冷负荷预览（分区冷量按内核五项加总；"
    "地板、墙、屋面来自分区几何（正方形平面 + 演示层高）；"
    "U 值与设计温度仍为演示目录，货品热工各区目前共用 v05 演示目录，需复核）"
)

_ZONE_EXTRA_CAPTION = "分区冷量（按内核五项加总；面积来自分区几何；U 值与货品热工仍为演示目录）"

_COMPONENT_ROWS: tuple[tuple[str, str], ...] = (
    ("envelope_heat_transfer_load_kw", "围护传热"),
    ("product_sensible_heat_load_kw", "产品显热"),
    ("packaging_load_kw", "包装"),
    ("infiltration_load_kw", "渗透"),
    ("personnel_load_kw", "人员"),
    ("lighting_load_kw", "照明"),
    ("evaporator_fan_load_kw", "蒸发风机"),
    ("defrost_additional_load_kw", "融霜附加"),
    ("other_configuration_load_kw", "其他"),
    ("safety_margin_load_kw", "安全裕量"),
)


class _ZoneColumn(TypedDict):
    key: str
    label: str
    unit: str | None


# Same keys as frontend COOLING_ZONE_COLUMNS (copy fields; no formulas).
_ZONE_COLUMNS: tuple[_ZoneColumn, ...] = (
    {"key": "zone_code", "label": "区域编码", "unit": None},
    {"key": "zone_name", "label": "区域名称", "unit": None},
    {"key": "temperature_level", "label": "温区等级", "unit": None},
    {"key": "transmission_load_kw_r", "label": "传热负荷", "unit": "kW(r)"},
    {"key": "product_load_kw_r", "label": "产品负荷", "unit": "kW(r)"},
    {"key": "infiltration_load_kw_r", "label": "渗透负荷", "unit": "kW(r)"},
    {"key": "internal_load_kw_r", "label": "内部负荷", "unit": "kW(r)"},
    {"key": "defrost_load_kw_r", "label": "化霜负荷", "unit": "kW(r)"},
    {"key": "subtotal_load_kw_r", "label": "小计冷负荷", "unit": "kW(r)"},
)


def project_cooling_load_table(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the 豆包-facing cooling table from adapter payload fields only."""
    rows: list[dict[str, Any]] = []
    for field_name, label in _COMPONENT_ROWS:
        value = payload.get(field_name)
        if value is None:
            continue
        rows.append({"component": label, "load_kw": value})

    total = payload.get("total_cooling_load_kw")
    summary = {
        "total_cooling_load_kw": total,
        "floor_area_from_zone_plan": True,
        "envelope_wall_roof_from_plan": True,
        "formula_recut_authorized": True,
    }

    extra_tables: list[dict[str, Any]] = []
    zone_rows = _zone_component_rows(payload)
    if zone_rows:
        extra_tables.append(
            {
                "caption": _ZONE_EXTRA_CAPTION,
                "columns": [dict(column) for column in _ZONE_COLUMNS],
                "rows": zone_rows,
            }
        )

    return {
        "caption": COOLING_CAPTION,
        "columns": [
            {"key": "component", "label": "负荷分项", "unit": None},
            {"key": "load_kw", "label": "冷量", "unit": "kW(r)"},
        ],
        "rows": rows,
        "summary": summary,
        "extra_tables": extra_tables,
        "markdown_table": _markdown_table(rows, total, zone_rows),
    }


def _zone_component_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    zones = payload.get("zones")
    if not isinstance(zones, Sequence) or isinstance(zones, (str, bytes)) or not zones:
        return []
    zone_rows: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, Mapping):
            continue
        zone_rows.append({column["key"]: zone.get(column["key"]) for column in _ZONE_COLUMNS})
    return zone_rows


def _markdown_table(
    rows: Sequence[Mapping[str, Any]],
    total: Any,
    zone_rows: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "| 负荷分项 | 冷量 kW(r) |",
        "|---|---|",
    ]
    for row in rows:
        lines.append(f"| {_cell(row.get('component'))} | {_cell(row.get('load_kw'))} |")
    if total is not None:
        lines.append(f"| **合计** | **{_cell(total)}** |")
    if zone_rows:
        lines.append("")
        lines.append(f"**{_ZONE_EXTRA_CAPTION}**")
        header = " | ".join(str(column["label"]) for column in _ZONE_COLUMNS)
        lines.append(f"| {header} |")
        lines.append("|" + "|".join("---" for _ in _ZONE_COLUMNS) + "|")
        for zone in zone_rows:
            cells = " | ".join(_cell(zone.get(column["key"])) for column in _ZONE_COLUMNS)
            lines.append(f"| {cells} |")
    lines.append("")
    lines.append(f"> {COOLING_CAPTION}")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "｜").strip()
    return text if text else "—"
