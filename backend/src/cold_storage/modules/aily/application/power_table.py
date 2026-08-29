"""Project installed-power calculator output into a conversation table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def project_power_table(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the 豆包-facing power table from canonical adapter payload."""
    items = payload.get("items")
    rows: list[dict[str, Any]] = []
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "category": item.get("category"),
                    "installed_power_kw": item.get("installed_power_kw"),
                    "demand_factor": item.get("demand_factor"),
                    "estimated_demand_kw": item.get("estimated_demand_kw"),
                }
            )

    total = payload.get("total_installed_power_kw_e")
    summary = {
        "total_installed_power_kw_e": total,
        "total_estimated_demand_kw": payload.get("total_estimated_demand_kw"),
    }
    return {
        "caption": "装机功率预览（概念设计，需复核）",
        "columns": [
            {"key": "category", "label": "类别", "unit": None},
            {"key": "installed_power_kw", "label": "装机功率", "unit": "kW(e)"},
            {"key": "demand_factor", "label": "需用系数", "unit": None},
            {"key": "estimated_demand_kw", "label": "估算需量", "unit": "kW(e)"},
        ],
        "rows": rows,
        "summary": summary,
        "extra_tables": [],
        "markdown_table": _markdown_table(rows, total),
    }


def _markdown_table(rows: Sequence[Mapping[str, Any]], total: Any) -> str:
    lines = ["| 类别 | 装机功率 kW(e) | 需用系数 | 估算需量 kW(e) |", "|---|---|---|---|"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("category")),
                    _cell(row.get("installed_power_kw")),
                    _cell(row.get("demand_factor")),
                    _cell(row.get("estimated_demand_kw")),
                ]
            )
            + " |"
        )
    if total is not None:
        lines.append(f"| **合计装机** | **{_cell(total)}** | — | — |")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "｜").strip()
    return text if text else "—"
