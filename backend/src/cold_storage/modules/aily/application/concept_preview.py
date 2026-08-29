"""Run all five preview kernels in one response for Aily / 豆包 conversation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.application.preview_bundle import json_ready
from cold_storage.modules.aily.application.stage_preview import (
    preview_cooling_load,
    preview_equipment,
    preview_installed_power,
    preview_investment,
    preview_zone_plan,
)


def preview_concept(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run five preview kernels, return all tables."""
    stages = {
        "zone": preview_zone_plan(payload, correlation_id=correlation_id),
        "cooling_load": preview_cooling_load(payload, correlation_id=correlation_id),
        "equipment": preview_equipment(payload, correlation_id=correlation_id),
        "power": preview_installed_power(payload, correlation_id=correlation_id),
        "investment": preview_investment(payload, correlation_id=correlation_id),
    }
    requires_review = any(stage.get("requires_review") for stage in stages.values())
    body = json_ready(
        {
            "reply_kind": "concept_preview",
            "product_name": "豆包工作伙伴",
            "connector": "aily",
            "requires_review": requires_review,
            "persisted": False,
            "envelope_from_zone_area": False,
            "formula_recut_authorized": False,
            "stages": stages,
        }
    )
    if not isinstance(body, dict):
        raise TypeError("concept preview body must be a JSON object")
    return body
