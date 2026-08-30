"""Run all five preview kernels in one response for Aily / 豆包 conversation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.aily.application.preview_bundle import (
    assemble_preview_context,
    json_ready,
)
from cold_storage.modules.aily.application.stage_preview import run_concept_preview_stages


def preview_concept(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run five preview kernels, return all tables."""
    context = assemble_preview_context(payload, correlation_id=correlation_id)
    stages = run_concept_preview_stages(context)
    requires_review = any(stage.get("requires_review") for stage in stages.values())
    body = json_ready(
        {
            "reply_kind": "concept_preview",
            "product_name": "豆包工作伙伴",
            "connector": "aily",
            "requires_review": requires_review,
            "persisted": False,
            "floor_area_from_zone_plan": True,
            "envelope_wall_roof_from_plan": True,
            "formula_recut_authorized": True,
            "stages": stages,
        }
    )
    if not isinstance(body, dict):
        raise TypeError("concept preview body must be a JSON object")
    return body
