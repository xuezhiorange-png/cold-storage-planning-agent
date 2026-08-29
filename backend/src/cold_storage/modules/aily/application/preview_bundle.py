"""Shared assembly helpers for Aily / 豆包 conversation previews.

Normalizes five KEY, assembles the operator bundle, and projects execution
snapshots. Does not persist, does not recut formulas, and does not import MCP.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from cold_storage.modules.aily.application.operator_payload import (
    OPERATOR_KEY_ASK,
    normalize_aily_operator_payload,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.projects.application.engineering_input_bundle import (
    EngineeringInputBundleValidationError,
    project_execution_snapshot_from_bundle,
)
from cold_storage.modules.projects.application.operator_process_input import (
    REFRIGERATED_ZONE_REGISTRY,
    TEMPERATURE_BAND_TO_LEVEL,
    assemble_engineering_input_bundle,
    validate_operator_process_input,
)
from cold_storage.modules.projects.domain.models import ProjectVersion

AILY_CONNECTOR_ACTOR = "aily-connector"
AILY_PREVIEW_PROJECT_ID = "aily-preview"
AILY_PREVIEW_VERSION_ID = "aily-preview-v1"

_WORKBENCH_ENVELOPE_CATALOG_SOURCE = "samples/v05-local-workbench/manifest.json"
_PREVIEW_INVESTMENT_DEMO: dict[str, Any] = {
    "total_area_m2": "1000",
    "refrigerated_area_m2": "800",
    "frozen_area_m2": "200",
    "position_count": 100,
    "total_power_kw": "150",
}


@dataclass(frozen=True, slots=True)
class PreviewContext:
    """In-memory operator bundle and five-stage snapshot for preview kernels."""

    operator_input: dict[str, Any]
    bundle: dict[str, Any]
    snapshot: dict[str, Any]
    correlation_id: str


def assemble_preview_context(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> PreviewContext:
    """Validate five KEY and build bundle + execution snapshot without persistence."""
    operator_input = normalize_aily_operator_payload(payload)
    try:
        validate_operator_process_input(operator_input)
    except EngineeringInputBundleValidationError as exc:
        raise from_bundle_error(exc) from exc

    version = ProjectVersion(
        project_id=AILY_PREVIEW_PROJECT_ID,
        version_number=1,
        change_summary="aily-five-stage-preview",
        created_by=AILY_CONNECTOR_ACTOR,
        id=AILY_PREVIEW_VERSION_ID,
    )
    corr = correlation_id or str(uuid4())
    try:
        bundle = assemble_engineering_input_bundle(
            operator_input=operator_input,
            project_id=AILY_PREVIEW_PROJECT_ID,
            version=version,
            actor=AILY_CONNECTOR_ACTOR,
            correlation_id=corr,
        )
        snapshot = project_execution_snapshot_from_bundle(bundle)
    except EngineeringInputBundleValidationError as exc:
        raise from_bundle_error(exc) from exc

    return PreviewContext(
        operator_input=dict(operator_input),
        bundle=dict(bundle),
        snapshot=dict(snapshot),
        correlation_id=str(
            correlation_id or bundle["project_version_identity"]["correlation_id"]["value"]
        ),
    )


def prepare_stage_inputs(stage_key: str, raw_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Apply preview-only snapshot enrichment without feeding zone results into cooling."""
    inputs = dict(raw_inputs)
    if stage_key == "cooling_load":
        return _enrich_cooling_load_preview_inputs(inputs)
    if stage_key == "investment":
        return _enrich_investment_preview_inputs(inputs)
    return inputs


def json_ready(value: Any) -> Any:
    """Copy calculator fields into JSON types. Does not recompute formulas."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [json_ready(item) for item in value]
    return value


def from_bundle_error(exc: EngineeringInputBundleValidationError) -> AilyConnectorError:
    field_path = exc.error.field_path
    missing: tuple[str, ...] = ()
    ask = ""
    for key, label in OPERATOR_KEY_ASK.items():
        if key in field_path:
            missing = (key,)
            ask = f"请提供：{label}"
            break
    return AilyConnectorError(
        code=exc.error.code,
        message=exc.error.message,
        field_path=field_path,
        missing_keys=missing,
        ask_operator=ask,
    )


def adapter_failure(
    *,
    stage_key: str,
    blockers: Sequence[Any],
    default_message: str,
) -> AilyConnectorError:
    first = blockers[0] if blockers else None
    return AilyConnectorError(
        code=getattr(first, "code", None) or "INVALID_ENGINEERING_INPUT",
        message=getattr(first, "message", None) or default_message,
        field_path=getattr(first, "field_name", None) or stage_key,
    )


def _enrich_cooling_load_preview_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Fill registry zone identity; keep demo envelope catalog, not zone-planner area."""
    zones = inputs.get("zones")
    if not isinstance(zones, list):
        return inputs
    enriched_zones: list[dict[str, Any]] = []
    for index, registry_row in enumerate(REFRIGERATED_ZONE_REGISTRY):
        zone_code, zone_name, temperature_band = registry_row
        if temperature_band not in TEMPERATURE_BAND_TO_LEVEL:
            continue
        zone = dict(zones[index]) if index < len(zones) and isinstance(zones[index], dict) else {}
        zone["zone_code"] = zone_code
        zone["zone_name"] = zone_name
        zone["temperature_level"] = TEMPERATURE_BAND_TO_LEVEL[temperature_band]
        enriched_zones.append(zone)
    inputs["zones"] = enriched_zones
    return inputs


def _enrich_investment_preview_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Use workbench demo placeholders; do not bind zone-planner totals."""
    for field_name, value in _PREVIEW_INVESTMENT_DEMO.items():
        inputs[field_name] = value
    inputs.setdefault("demo_catalog_source", _WORKBENCH_ENVELOPE_CATALOG_SOURCE)
    return inputs
