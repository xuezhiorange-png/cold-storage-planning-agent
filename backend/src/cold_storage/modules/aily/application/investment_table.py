"""Project investment calculator output into a conversation table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def project_investment_table(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the 豆包-facing investment table from canonical adapter payload."""
    items = payload.get("items")
    rows: list[dict[str, Any]] = []
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "item_key": item.get("item_key"),
                    "item_name": item.get("item_name"),
                    "amount_cny": item.get("amount_cny"),
                }
            )

    total = payload.get("total_investment_cny")
    summary = {"total_investment_cny": total}
    return {
        "caption": "投资估算预览（演示系数，需复核）",
        "columns": [
            {"key": "item_key", "label": "条目键", "unit": None},
            {"key": "item_name", "label": "条目", "unit": None},
            {"key": "amount_cny", "label": "金额", "unit": "CNY"},
        ],
        "rows": rows,
        "summary": summary,
        "extra_tables": [],
        "markdown_table": _markdown_table(rows, total),
    }


def _markdown_table(rows: Sequence[Mapping[str, Any]], total: Any) -> str:
    lines = ["| 条目 | 金额（元） |", "|---|---|"]
    for row in rows:
        name = row.get("item_name") or row.get("item_key")
        lines.append(f"| {_cell(name)} | {_cell(row.get('amount_cny'))} |")
    if total is not None:
        lines.append(f"| **合计** | **{_cell(total)}** |")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "｜").strip()
    return text if text else "—"
