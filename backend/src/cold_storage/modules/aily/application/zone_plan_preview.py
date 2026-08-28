"""Run the existing zone-plan kernel for an Aily / 豆包 conversation.

Does not persist projects. Does not let the model compute engineering values.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import uuid4

from cold_storage.modules.aily.application.operator_payload import (
    OPERATOR_KEY_ASK,
    normalize_aily_operator_payload,
)
from cold_storage.modules.aily.application.zone_plan_table import project_zone_plan_table
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.orchestration.application.production_calculation.adapters import (
    ZonePlanningAdapter,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType
from cold_storage.modules.projects.application.engineering_input_bundle import (
    EngineeringInputBundleValidationError,
    project_execution_snapshot_from_bundle,
)
from cold_storage.modules.projects.application.operator_process_input import (
    assemble_engineering_input_bundle,
    validate_operator_process_input,
)
from cold_storage.modules.projects.domain.models import ProjectVersion

AILY_CONNECTOR_ACTOR = "aily-connector"
AILY_PREVIEW_PROJECT_ID = "aily-preview"
ZONE_CALCULATOR_NAME = "cold_room_zone_plan"
ZONE_CALCULATOR_VERSION = "1.0.0"


def preview_zone_plan(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run cold_room_zone_plan, return a conversation table."""
    operator_input = normalize_aily_operator_payload(payload)
    try:
        validate_operator_process_input(operator_input)
    except EngineeringInputBundleValidationError as exc:
        raise _from_bundle_error(exc) from exc

    version = ProjectVersion(
        project_id=AILY_PREVIEW_PROJECT_ID,
        version_number=1,
        change_summary="aily-zone-plan-preview",
        created_by=AILY_CONNECTOR_ACTOR,
        id="aily-preview-v1",
    )
    try:
        bundle = assemble_engineering_input_bundle(
            operator_input=operator_input,
            project_id=AILY_PREVIEW_PROJECT_ID,
            version=version,
            actor=AILY_CONNECTOR_ACTOR,
            correlation_id=correlation_id or str(uuid4()),
        )
        snapshot = project_execution_snapshot_from_bundle(bundle)
    except EngineeringInputBundleValidationError as exc:
        raise _from_bundle_error(exc) from exc

    zone_inputs = snapshot.get("zone")
    if not isinstance(zone_inputs, dict):
        raise AilyConnectorError(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="assembled zone snapshot is missing",
            field_path="zone",
        )

    corr = correlation_id or str(bundle["project_version_identity"]["correlation_id"]["value"])
    projection = CalculatorInputProjection(
        calculation_type=CalculationType.ZONE,
        raw_inputs=dict(zone_inputs),
        actor=AILY_CONNECTOR_ACTOR,
        correlation_id=str(corr),
        database_backend="preview",
        calculator_name=ZONE_CALCULATOR_NAME,
        calculator_version=ZONE_CALCULATOR_VERSION,
    )
    adapter_result = ZonePlanningAdapter().execute(projection)
    if adapter_result.blockers or not adapter_result.calculator_success:
        first = adapter_result.blockers[0] if adapter_result.blockers else None
        raise AilyConnectorError(
            code=first.code if first else "INVALID_ENGINEERING_INPUT",
            message=first.message if first else "zone planner rejected the input",
            field_path=first.field_name if first else "zone_planning_inputs",
        )

    table = project_zone_plan_table(adapter_result.payload)
    warnings = [item.message for item in adapter_result.warnings]
    assumptions = list(adapter_result.provenance.assumptions)
    body = _json_ready(
        {
            "reply_kind": "zone_plan_table",
            "product_name": "豆包工作伙伴",
            "connector": "aily",
            "calculator_name": adapter_result.calculator_name or ZONE_CALCULATOR_NAME,
            "calculator_version": adapter_result.calculator_version or ZONE_CALCULATOR_VERSION,
            "requires_review": bool(adapter_result.requires_review),
            "persisted": False,
            "operator_keys": operator_input["zone_planning_inputs"],
            "summary": table["summary"],
            "table": {
                "caption": table["caption"],
                "columns": table["columns"],
                "rows": table["rows"],
            },
            "extra_tables": table["extra_tables"],
            "markdown_table": table["markdown_table"],
            "warnings": warnings,
            "assumptions": assumptions,
            "content_hash": adapter_result.content_hash,
        }
    )
    if not isinstance(body, dict):
        raise TypeError("zone-plan preview body must be a JSON object")
    return body


def _json_ready(value: Any) -> Any:
    """Copy calculator fields into JSON types. Does not recompute formulas."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_ready(item) for item in value]
    return value


def _from_bundle_error(exc: EngineeringInputBundleValidationError) -> AilyConnectorError:
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
