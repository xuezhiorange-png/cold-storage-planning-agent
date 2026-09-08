"""Aily / 豆包 read-only projection for the V2.0 factory-power result."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from cold_storage.modules.projects.application.factory_power_presentation import (
    FACTORY_POWER_CALCULATOR_ID,
    FACTORY_POWER_CALCULATOR_IDENTITY,
    FACTORY_POWER_CALCULATOR_VERSION,
    FACTORY_POWER_UNAVAILABLE_CODE,
    FactoryPowerPresentation,
    FactoryPowerPresentationError,
    build_factory_power_presentation,
)

_CANONICAL_RESULT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def project_factory_power_table(
    source: Mapping[str, Any] | FactoryPowerPresentation | None,
) -> dict[str, Any]:
    """Project an existing V2 canonical result without running engineering logic."""
    if source is None:
        return _unavailable_body()
    try:
        presentation = (
            source if isinstance(source, FactoryPowerPresentation) else _build_presentation(source)
        )
        if (
            not isinstance(presentation.canonical_result_hash, str)
            or _CANONICAL_RESULT_HASH_PATTERN.fullmatch(presentation.canonical_result_hash) is None
        ):
            raise FactoryPowerPresentationError("presentation canonical_result_hash is invalid")
    except FactoryPowerPresentationError:
        return _unavailable_body()

    details = deepcopy(list(presentation.details))
    summary = deepcopy(presentation.summary)
    return {
        "reply_kind": "factory_power_estimation_table",
        "available": True,
        "calculator_name": presentation.source_calculator_id,
        "calculator_version": presentation.source_calculator_version,
        "calculator_identity": presentation.source_calculator_identity,
        "canonical_result_hash": presentation.canonical_result_hash,
        "requires_review": presentation.requires_review,
        "factory_area_band": presentation.factory_area_band,
        "unit_semantics": deepcopy(presentation.unit_semantics),
        "review": deepcopy(presentation.review),
        "provenance": deepcopy(presentation.provenance),
        "assumptions": list(presentation.assumptions),
        "details": details,
        "summary": summary,
        "table": {
            "caption": "估算工厂电功率（V2.0，需工程复核）",
            "columns": [
                {"key": "equipment_or_zone", "label": "设备/区域", "unit": None},
                {"key": "basis", "label": "计算依据", "unit": None},
                {"key": "configured_quantity", "label": "数量", "unit": None},
                {"key": "unit_power_kw", "label": "单台功率", "unit": "kW"},
                {"key": "installed_power_kw", "label": "装机功率", "unit": "kW"},
                {"key": "pool", "label": "功率池", "unit": None},
                {"key": "simultaneity_factor", "label": "同时系数", "unit": None},
                {"key": "coincident_power_kw", "label": "计入功率", "unit": "kW"},
            ],
            "rows": deepcopy(details),
            "summary": deepcopy(summary),
        },
    }


def _build_presentation(source: Mapping[str, Any]) -> FactoryPowerPresentation:
    """Build only from the serialized P1 canonical result.

    A mutable mapping that looks like the shared presentation is not an
    integrity authority: it has no canonical source from which its hash can
    be recomputed.  The trusted internal object path is handled by the caller
    above; every mapping must therefore pass through the canonical builder.
    """
    return build_factory_power_presentation(source)


def _unavailable_body() -> dict[str, Any]:
    """Return a stable fail-closed response for absent or malformed source data."""
    return {
        "reply_kind": "factory_power_estimation_unavailable",
        "available": False,
        "code": FACTORY_POWER_UNAVAILABLE_CODE,
        "calculator_name": FACTORY_POWER_CALCULATOR_ID,
        "calculator_version": FACTORY_POWER_CALCULATOR_VERSION,
        "calculator_identity": FACTORY_POWER_CALCULATOR_IDENTITY,
        "canonical_result_hash": None,
        "requires_review": True,
        "factory_area_band": None,
        "unit_semantics": {},
        "review": {"requires_review": True, "status": "UNAVAILABLE"},
        "provenance": {},
        "assumptions": [],
        "details": [],
        "summary": None,
        "table": {"caption": "暂无可用的 V2.0 估算工厂电功率结果", "columns": [], "rows": []},
    }


__all__ = ["project_factory_power_table"]
