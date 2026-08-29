"""Project equipment capability calculator output into a conversation table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_EQUIPMENT_ROWS: tuple[tuple[str, str, str | None], ...] = (
    ("evaporator_total_cooling_capacity_kw", "蒸发器总制冷量", "kW(r)"),
    ("evaporator_quantity", "蒸发器台数", "台"),
    ("single_evaporator_capacity_kw", "单台蒸发器能力", "kW(r)"),
    ("compressor_operating_capacity_kw", "压缩机运行能力", "kW(r)"),
    ("compressor_installed_capacity_kw", "压缩机装机能力", "kW(r)"),
    ("standby_capacity_kw", "备用能力", "kW(r)"),
    ("condenser_heat_rejection_capacity_kw", "冷凝器散热量", "kW"),
)


def project_equipment_table(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the 豆包-facing equipment table from canonical adapter payload."""
    rows: list[dict[str, Any]] = []
    for field_name, label, unit in _EQUIPMENT_ROWS:
        value = payload.get(field_name)
        if value is None:
            continue
        rows.append({"metric": label, "value": value, "unit": unit})

    summary = {
        "evaporator_total_cooling_capacity_kw": payload.get("evaporator_total_cooling_capacity_kw"),
        "compressor_operating_capacity_kw": payload.get("compressor_operating_capacity_kw"),
        "condenser_heat_rejection_capacity_kw": payload.get("condenser_heat_rejection_capacity_kw"),
        "evaporation_temperature_c": payload.get("evaporation_temperature_c"),
        "condensing_temperature_c": payload.get("condensing_temperature_c"),
        "defrost_method": payload.get("defrost_method"),
    }
    return {
        "caption": "设备能力预览（概念设计，需复核）",
        "columns": [
            {"key": "metric", "label": "指标", "unit": None},
            {"key": "value", "label": "数值", "unit": None},
            {"key": "unit", "label": "单位", "unit": None},
        ],
        "rows": rows,
        "summary": summary,
        "extra_tables": [],
        "markdown_table": _markdown_table(rows),
    }


def _markdown_table(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = ["| 指标 | 数值 | 单位 |", "|---|---|---|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("metric")),
                    _cell(row.get("value")),
                    _cell(row.get("unit")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "｜").strip()
    return text if text else "—"
