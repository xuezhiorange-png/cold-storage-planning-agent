"""Project persisted zone-plan calculator output into a conversation table.

Copies labels and already-calculated fields. Does not recompute area, positions,
or engineering formulas.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_FIXED_AREA_ZONE_CODES = frozenset({"office", "changing_room", "coating_room"})

_QUANTITY_LABEL_BY_ZONE: dict[str, str] = {
    "office": "—",
    "changing_room": "—",
    "coating_room": "—",
    "sorting_packaging_room": "分选台",
    "shipping_channel": "月台",
}

TABLE_COLUMNS: tuple[dict[str, str | None], ...] = (
    {"key": "zone_name", "label": "房间", "unit": None},
    {"key": "temperature_band", "label": "温度", "unit": None},
    {"key": "required_area_m2", "label": "面积", "unit": "m2"},
    {"key": "quantity_label", "label": "数量含义", "unit": None},
    {"key": "quantity", "label": "数量", "unit": None},
    {"key": "note", "label": "说明", "unit": None},
)


def project_zone_plan_table(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the 豆包-facing table from a zone-plan calculator payload."""
    zones = payload.get("zones")
    if not isinstance(zones, Sequence) or isinstance(zones, (str, bytes)):
        zones = []
    rows: list[dict[str, Any]] = []
    extra_tables: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, Mapping):
            continue
        row, extra = _project_zone_row(zone)
        rows.append(row)
        extra_tables.extend(extra)

    total = payload.get("total_required_area_m2")
    if total is None:
        total = payload.get("total_area_m2")
    summary = {
        "daily_inbound_mass_kg": payload.get("daily_inbound_mass_kg"),
        "total_required_area_m2": total,
        "total_area_m2_8_position_scheme": payload.get("total_area_m2_8_position_scheme"),
    }
    return {
        "caption": "冷库分区规划",
        "columns": [dict(column) for column in TABLE_COLUMNS],
        "rows": rows,
        "summary": summary,
        "extra_tables": extra_tables,
        "markdown_table": _markdown_table(rows),
    }


def _project_zone_row(zone: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    zone_code = str(zone.get("zone_code") or "")
    quantity_label = _QUANTITY_LABEL_BY_ZONE.get(zone_code, "货位")
    quantity = zone.get("position_count")
    if zone_code in _FIXED_AREA_ZONE_CODES:
        quantity_label = "—"
        quantity = "—"
        note = "固定面积"
    elif zone_code == "shipping_channel":
        note = _shipping_note(zone)
    elif zone_code == "sorting_packaging_room":
        quantity = zone.get("position_count", zone.get("table_count"))
        note = _sorting_note(zone)
    else:
        note = _storage_or_precool_note(zone)

    extra_tables: list[dict[str, Any]] = []
    schemes = zone.get("schemes")
    if isinstance(schemes, Sequence) and not isinstance(schemes, (str, bytes)) and schemes:
        extra_tables.append(
            {
                "caption": f"{zone.get('zone_name', zone_code)}双方案",
                "columns": [
                    {"key": "scheme_label", "label": "方案", "unit": None},
                    {"key": "room_count", "label": "间数", "unit": None},
                    {"key": "position_count", "label": "货位", "unit": None},
                    {"key": "required_area_m2", "label": "面积", "unit": "m2"},
                ],
                "rows": [_scheme_row(item) for item in schemes if isinstance(item, Mapping)],
            }
        )
        note = note or "见双方案表"

    row = {
        "zone_code": zone_code,
        "zone_name": zone.get("zone_name"),
        "temperature_band": zone.get("temperature_band"),
        "required_area_m2": zone.get("required_area_m2"),
        "quantity_label": quantity_label,
        "quantity": quantity,
        "note": note,
    }
    return row, extra_tables


def _scheme_row(scheme: Mapping[str, Any]) -> dict[str, Any]:
    scheme_id = str(scheme.get("scheme_id") or "")
    label = {"6_position": "6位间", "8_position": "8位间"}.get(scheme_id, scheme_id)
    return {
        "scheme_id": scheme_id,
        "scheme_label": label,
        "room_count": scheme.get("room_count"),
        "position_count": scheme.get("position_count"),
        "required_area_m2": scheme.get("required_area_m2"),
    }


def _shipping_note(zone: Mapping[str, Any]) -> str:
    parts = []
    if zone.get("pallet_count") is not None:
        parts.append(f"托盘 {zone.get('pallet_count')}")
    if zone.get("truck_count") is not None:
        parts.append(f"车次 {zone.get('truck_count')}")
    return "，".join(parts)


def _sorting_note(zone: Mapping[str, Any]) -> str:
    if zone.get("n_need") is None:
        return ""
    return f"需要 {zone.get('n_need')} 台"


def _storage_or_precool_note(zone: Mapping[str, Any]) -> str:
    n_need = zone.get("n_need")
    n_actual = zone.get("n_actual")
    if n_need is None:
        return ""
    if n_actual is None:
        return f"需要 {n_need}"
    return f"需要 {n_need}，排布 {n_actual}"


def _markdown_table(rows: Sequence[Mapping[str, Any]]) -> str:
    header = "| 房间 | 温度 | 面积（㎡） | 数量 | 说明 |"
    sep = "|---|---|---|---|---|"
    lines = [header, sep]
    for row in rows:
        quantity = row.get("quantity")
        label = row.get("quantity_label")
        if quantity in (None, "—"):
            quantity_cell = "—"
        elif label in (None, "—"):
            quantity_cell = str(quantity)
        else:
            quantity_cell = f"{quantity}{label}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row.get("zone_name")),
                    _cell(row.get("temperature_band")),
                    _cell(row.get("required_area_m2")),
                    _cell(quantity_cell),
                    _cell(row.get("note")),
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
