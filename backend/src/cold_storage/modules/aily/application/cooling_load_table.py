"""Project cooling-load calculator output into a conversation table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_COOLING_CAPTION = (
    "冷负荷预览（地板/规划面积来自分区结果；墙、屋面、U 值仍是演示目录，需复核）"
)

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
        "envelope_wall_roof_from_plan": False,
        "demo_envelope": True,
    }

    extra_tables: list[dict[str, Any]] = []
    zones = payload.get("zones")
    if isinstance(zones, Sequence) and not isinstance(zones, (str, bytes)) and zones:
        zone_rows = []
        for zone in zones:
            if not isinstance(zone, Mapping):
                continue
            zone_rows.append(
                {
                    "zone_code": zone.get("zone_code"),
                    "zone_name": zone.get("zone_name"),
                    "subtotal_load_kw_r": zone.get("subtotal_load_kw_r"),
                }
            )
        if zone_rows:
            extra_tables.append(
                {
                    "caption": "分区小计（地板面积来自分区结果；墙屋面仍为演示目录）",
                    "columns": [
                        {"key": "zone_name", "label": "分区", "unit": None},
                        {"key": "subtotal_load_kw_r", "label": "小计", "unit": "kW(r)"},
                    ],
                    "rows": zone_rows,
                }
            )

    return {
        "caption": _COOLING_CAPTION,
        "columns": [
            {"key": "component", "label": "负荷分项", "unit": None},
            {"key": "load_kw", "label": "冷量", "unit": "kW(r)"},
        ],
        "rows": rows,
        "summary": summary,
        "extra_tables": extra_tables,
        "markdown_table": _markdown_table(rows, total),
    }


def _markdown_table(rows: Sequence[Mapping[str, Any]], total: Any) -> str:
    lines = [
        "| 负荷分项 | 冷量 kW(r) |",
        "|---|---|",
    ]
    for row in rows:
        lines.append(f"| {_cell(row.get('component'))} | {_cell(row.get('load_kw'))} |")
    if total is not None:
        lines.append(f"| **合计** | **{_cell(total)}** |")
    lines.append("")
    lines.append(
        "> 地板/规划面积来自分区结果；墙、屋面、U 值仍是演示目录，需复核。"
    )
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "｜").strip()
    return text if text else "—"
