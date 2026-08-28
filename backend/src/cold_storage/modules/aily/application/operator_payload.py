"""Normalize 豆包/Aily payloads into OperatorProcessInputV1 (V0.9 five KEY).

豆包 owns natural-language understanding. This module does not parse chat
utterances such as「要建一个多少吨的加工厂」— those are examples for 豆包.

Charles 2026-08-28: 吨 always means per day. When 豆包 already converted the
spoken tonne figure and sends an explicit tonne unit, multiply by 1000 to
reach ``daily_inbound_mass_kg`` (kg/day). Bare numbers on that field stay
kg/day. Missing KEY fail closed; days and mass are never guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_PROCESS_SCHEMA_ID,
    OPERATOR_PROCESS_SCHEMA_VERSION_V09,
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

OPERATOR_KEY_UNITS: dict[str, str] = {
    "daily_inbound_mass_kg": "kg/day",
    "finished_storage_days": "day",
    "frozen_storage_days": "day",
    "main_packaging_storage_days": "day",
    "auxiliary_packaging_storage_days": "day",
}

OPERATOR_KEY_ASK: dict[str, str] = {
    "daily_inbound_mass_kg": "每天进货量（公斤/天；1吨/天=1000公斤/天）",
    "finished_storage_days": "成品存放天数",
    "frozen_storage_days": "冻果存放天数",
    "main_packaging_storage_days": "主包材存放天数",
    "auxiliary_packaging_storage_days": "辅包材存放天数",
}

_TON_DAY_UNITS = frozenset({"t/day", "ton/day", "tons/day", "t", "ton", "吨/天", "吨"})


def normalize_aily_operator_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact OperatorProcessInputV1 1.1.0 payload or fail closed."""
    if not isinstance(payload, Mapping):
        raise AilyConnectorError(
            code="INVALID_ENGINEERING_INPUT",
            message="Aily zone-plan payload must be a JSON object",
            field_path="body",
        )
    section = payload.get("zone_planning_inputs")
    if isinstance(section, Mapping):
        raw_keys = dict(section)
    else:
        raw_keys = {
            field_name: payload[field_name]
            for field_name in OPERATOR_V09_FIVE_KEY_FIELDS
            if field_name in payload
        }

    missing = tuple(
        field_name for field_name in OPERATOR_V09_FIVE_KEY_FIELDS if field_name not in raw_keys
    )
    if missing:
        ask = "请提供：" + "、".join(OPERATOR_KEY_ASK[name] for name in missing)
        raise AilyConnectorError(
            code="MISSING_ENGINEERING_PARAMETER",
            message="OperatorProcessInputV1 five KEY are incomplete",
            field_path="zone_planning_inputs",
            missing_keys=missing,
            ask_operator=ask,
        )

    zone_planning_inputs: dict[str, Any] = {}
    for field_name in OPERATOR_V09_FIVE_KEY_FIELDS:
        zone_planning_inputs[field_name] = _to_operator_leaf(field_name, raw_keys[field_name])

    return {
        "schema_id": OPERATOR_PROCESS_SCHEMA_ID,
        "schema_version": OPERATOR_PROCESS_SCHEMA_VERSION_V09,
        "zone_planning_inputs": zone_planning_inputs,
    }


def _to_operator_leaf(field_name: str, raw: Any) -> dict[str, Any]:
    expected_unit = OPERATOR_KEY_UNITS[field_name]
    if isinstance(raw, Mapping):
        value = raw.get("value", raw.get("number"))
        unit = raw.get("unit") or expected_unit
        if value is None:
            raise AilyConnectorError(
                code="MISSING_ENGINEERING_PARAMETER",
                message=f"missing value for {field_name}",
                field_path=f"zone_planning_inputs.{field_name}",
                missing_keys=(field_name,),
                ask_operator=f"请提供：{OPERATOR_KEY_ASK[field_name]}",
            )
        number = _as_number(field_name, value)
        number = _maybe_convert_daily_mass_unit(field_name, number, str(unit))
        return {
            "value": str(number),
            "unit": expected_unit,
            "state": "provided",
        }
    number = _as_number(field_name, raw)
    return {
        "value": str(number),
        "unit": expected_unit,
        "state": "provided",
    }


def _maybe_convert_daily_mass_unit(field_name: str, number: float, unit: str) -> float:
    if field_name != "daily_inbound_mass_kg":
        return number
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {expected.lower() for expected in ("kg/day", "kg", "公斤/天", "千克/天")}:
        return number
    if normalized in {item.lower() for item in _TON_DAY_UNITS}:
        return number * 1000.0
    raise AilyConnectorError(
        code="INVALID_ENGINEERING_INPUT",
        message="daily_inbound_mass_kg unit must be kg/day (豆包 converts 吨/天)",
        field_path="zone_planning_inputs.daily_inbound_mass_kg.unit",
        details={"unit": unit},
    )


def _as_number(field_name: str, value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise AilyConnectorError(
            code="INVALID_ENGINEERING_INPUT",
            message=f"{field_name} must be a positive number",
            field_path=f"zone_planning_inputs.{field_name}",
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AilyConnectorError(
            code="INVALID_ENGINEERING_INPUT",
            message=f"{field_name} must be a positive number",
            field_path=f"zone_planning_inputs.{field_name}",
        ) from exc
    if number <= 0:
        raise AilyConnectorError(
            code="INVALID_ENGINEERING_INPUT",
            message=f"{field_name} must be a positive number",
            field_path=f"zone_planning_inputs.{field_name}",
        )
    return number
