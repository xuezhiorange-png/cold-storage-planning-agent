"""Run individual five-stage preview kernels for Aily / 豆包 conversation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from cold_storage.modules.aily.application.cooling_load_table import project_cooling_load_table
from cold_storage.modules.aily.application.equipment_table import project_equipment_table
from cold_storage.modules.aily.application.investment_table import project_investment_table
from cold_storage.modules.aily.application.power_table import project_power_table
from cold_storage.modules.aily.application.preview_bundle import (
    AILY_CONNECTOR_ACTOR,
    POWER_DEMO_CATALOG_DISCLAIMER_ZH,
    PreviewContext,
    adapter_failure,
    assemble_preview_context,
    bind_equipment_loads_from_cooling_payload,
    json_ready,
    prepare_power_preview_inputs,
    prepare_stage_inputs,
)
from cold_storage.modules.aily.application.zone_plan_table import project_zone_plan_table
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.orchestration.application.production_calculation.adapters import (
    CoolingLoadAdapter,
    EquipmentCapabilityAdapter,
    InstalledPowerAdapter,
    InvestmentAdapter,
    ZonePlanningAdapter,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
    CalculatorInputProjection,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    CalculatorRejectedInputError,
)
from cold_storage.modules.orchestration.domain.contracts import CalculationType

ZONE_CALCULATOR_NAME = "cold_room_zone_plan"
ZONE_CALCULATOR_VERSION = "1.0.0"
COOLING_CALCULATOR_NAME = "cooling_load"
COOLING_CALCULATOR_VERSION = "1.0.0"
EQUIPMENT_CALCULATOR_NAME = "equipment"
EQUIPMENT_CALCULATOR_VERSION = "1.0.0"
POWER_CALCULATOR_NAME = "installed_power"
POWER_CALCULATOR_VERSION = "1.0.0"
INVESTMENT_CALCULATOR_NAME = "investment_estimate"
INVESTMENT_CALCULATOR_VERSION = "1.0.0"

_COOLING_EXTRA_FIELDS = {
    "envelope_from_zone_area": False,
    "formula_recut_authorized": False,
}
_INVESTMENT_EXTRA_FIELDS = {
    "investment_from_demo_catalog": True,
    "envelope_from_zone_area": False,
}


def preview_zone_plan(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run cold_room_zone_plan, return a conversation table."""
    context = assemble_preview_context(payload, correlation_id=correlation_id)
    return _run_zone_stage(context)


def preview_cooling_load(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run cooling_load with demo envelope, return a table."""
    context = assemble_preview_context(payload, correlation_id=correlation_id)
    return _run_cooling_stage(context)[0]


def preview_equipment(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run equipment capability preview, return a table."""
    context = assemble_preview_context(payload, correlation_id=correlation_id)
    _, cooling_payload = _run_cooling_stage(context)
    return _run_equipment_stage(context, cooling_payload)


def preview_installed_power(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run installed_power preview, return a table."""
    context = assemble_preview_context(payload, correlation_id=correlation_id)
    return _run_power_stage(context)


def preview_investment(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Validate five KEY, run investment_estimate preview, return a table."""
    context = assemble_preview_context(payload, correlation_id=correlation_id)
    return _run_investment_stage(context)


def run_concept_preview_stages(context: PreviewContext) -> dict[str, dict[str, Any]]:
    """Run all five preview kernels once from a shared assemble context."""
    zone = _run_zone_stage(context)
    cooling, cooling_payload = _run_cooling_stage(context)
    equipment = _run_equipment_stage(context, cooling_payload)
    power = _run_power_stage(context)
    investment = _run_investment_stage(context)
    return {
        "zone": zone,
        "cooling_load": cooling,
        "equipment": equipment,
        "power": power,
        "investment": investment,
    }


def _run_zone_stage(context: PreviewContext) -> dict[str, Any]:
    return _run_stage_preview(
        context,
        stage_key="zone",
        calculation_type=CalculationType.ZONE,
        adapter=ZonePlanningAdapter(),
        calculator_name=ZONE_CALCULATOR_NAME,
        calculator_version=ZONE_CALCULATOR_VERSION,
        reply_kind="zone_plan_table",
        table_projector=project_zone_plan_table,
        extra_fields={},
    )


def _run_cooling_stage(context: PreviewContext) -> tuple[dict[str, Any], dict[str, Any]]:
    adapter_result = _execute_stage_adapter(
        context,
        stage_key="cooling_load",
        calculation_type=CalculationType.COOLING_LOAD,
        adapter=CoolingLoadAdapter(),
        calculator_name=COOLING_CALCULATOR_NAME,
        calculator_version=COOLING_CALCULATOR_VERSION,
    )
    body = _build_stage_preview_body(
        context,
        adapter_result,
        stage_key="cooling_load",
        calculator_name=COOLING_CALCULATOR_NAME,
        calculator_version=COOLING_CALCULATOR_VERSION,
        reply_kind="cooling_load_table",
        table_projector=project_cooling_load_table,
        extra_fields=_COOLING_EXTRA_FIELDS,
    )
    payload = dict(adapter_result.payload)
    return body, payload


def _run_equipment_stage(
    context: PreviewContext,
    cooling_payload: Mapping[str, Any],
) -> dict[str, Any]:
    equipment_inputs = _equipment_inputs_from_context(context)
    bind_equipment_loads_from_cooling_payload(equipment_inputs, cooling_payload)
    return _run_stage_preview(
        context,
        stage_key="equipment",
        calculation_type=CalculationType.EQUIPMENT,
        adapter=EquipmentCapabilityAdapter(),
        calculator_name=EQUIPMENT_CALCULATOR_NAME,
        calculator_version=EQUIPMENT_CALCULATOR_VERSION,
        reply_kind="equipment_table",
        table_projector=project_equipment_table,
        extra_fields={},
        prepared_inputs=equipment_inputs,
    )


def _run_power_stage(context: PreviewContext) -> dict[str, Any]:
    power_inputs = _power_inputs_from_context(context)
    prepared, used_catalog = prepare_power_preview_inputs(power_inputs)
    extra_fields: dict[str, Any] = {}
    if used_catalog:
        extra_fields["power_from_demo_catalog"] = True
    body = _run_stage_preview(
        context,
        stage_key="power",
        calculation_type=CalculationType.POWER,
        adapter=InstalledPowerAdapter(),
        calculator_name=POWER_CALCULATOR_NAME,
        calculator_version=POWER_CALCULATOR_VERSION,
        reply_kind="power_table",
        table_projector=project_power_table,
        extra_fields=extra_fields,
        prepared_inputs=prepared,
    )
    if used_catalog:
        _apply_power_demo_catalog_disclaimer(body)
    return body


def _run_investment_stage(context: PreviewContext) -> dict[str, Any]:
    return _run_stage_preview(
        context,
        stage_key="investment",
        calculation_type=CalculationType.INVESTMENT,
        adapter=InvestmentAdapter(),
        calculator_name=INVESTMENT_CALCULATOR_NAME,
        calculator_version=INVESTMENT_CALCULATOR_VERSION,
        reply_kind="investment_table",
        table_projector=project_investment_table,
        extra_fields=_INVESTMENT_EXTRA_FIELDS,
    )


def _equipment_inputs_from_context(context: PreviewContext) -> dict[str, Any]:
    stage_inputs = context.snapshot.get("equipment")
    if not isinstance(stage_inputs, dict):
        raise AilyConnectorError(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="assembled equipment snapshot is missing",
            field_path="equipment",
        )
    return dict(stage_inputs)


def _power_inputs_from_context(context: PreviewContext) -> dict[str, Any]:
    stage_inputs = context.snapshot.get("power")
    if not isinstance(stage_inputs, dict):
        raise AilyConnectorError(
            code="UPSTREAM_LINEAGE_BIND_FAILED",
            message="assembled power snapshot is missing",
            field_path="power",
        )
    return dict(stage_inputs)


def _execute_stage_adapter(
    context: PreviewContext,
    *,
    stage_key: str,
    calculation_type: CalculationType,
    adapter: Any,
    calculator_name: str,
    calculator_version: str,
    prepared_inputs: dict[str, Any] | None = None,
) -> AdapterResult:
    if prepared_inputs is None:
        stage_inputs = context.snapshot.get(stage_key)
        if not isinstance(stage_inputs, dict):
            raise AilyConnectorError(
                code="UPSTREAM_LINEAGE_BIND_FAILED",
                message=f"assembled {stage_key} snapshot is missing",
                field_path=stage_key,
            )
        prepared_inputs = prepare_stage_inputs(stage_key, stage_inputs)

    projection = CalculatorInputProjection(
        calculation_type=calculation_type,
        raw_inputs=dict(prepared_inputs),
        actor=AILY_CONNECTOR_ACTOR,
        correlation_id=context.correlation_id,
        database_backend="preview",
        calculator_name=calculator_name,
        calculator_version=calculator_version,
    )
    try:
        adapter_result = adapter.execute(projection)
    except CalculatorRejectedInputError as exc:
        raise AilyConnectorError(
            code="INVALID_ENGINEERING_INPUT",
            message=str(exc),
            field_path=stage_key,
        ) from exc

    if adapter_result.blockers or not adapter_result.calculator_success:
        raise adapter_failure(
            stage_key=stage_key,
            blockers=adapter_result.blockers,
            default_message=f"{stage_key} calculator rejected the input",
        )
    return adapter_result


def _build_stage_preview_body(
    context: PreviewContext,
    adapter_result: AdapterResult,
    *,
    stage_key: str,
    calculator_name: str,
    calculator_version: str,
    reply_kind: str,
    table_projector: Callable[[Mapping[str, Any]], dict[str, Any]],
    extra_fields: Mapping[str, Any],
) -> dict[str, Any]:
    table = table_projector(adapter_result.payload)
    warnings = [item.message for item in adapter_result.warnings]
    assumptions = list(adapter_result.provenance.assumptions)
    body = json_ready(
        {
            "reply_kind": reply_kind,
            "product_name": "豆包工作伙伴",
            "connector": "aily",
            "calculator_name": adapter_result.calculator_name or calculator_name,
            "calculator_version": adapter_result.calculator_version or calculator_version,
            "requires_review": bool(adapter_result.requires_review),
            "persisted": False,
            "operator_keys": context.operator_input["zone_planning_inputs"],
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
            **dict(extra_fields),
        }
    )
    if not isinstance(body, dict):
        raise TypeError(f"{stage_key} preview body must be a JSON object")
    return body


def _run_stage_preview(
    context: PreviewContext,
    *,
    stage_key: str,
    calculation_type: CalculationType,
    adapter: Any,
    calculator_name: str,
    calculator_version: str,
    reply_kind: str,
    table_projector: Callable[[Mapping[str, Any]], dict[str, Any]],
    extra_fields: Mapping[str, Any],
    prepared_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    adapter_result = _execute_stage_adapter(
        context,
        stage_key=stage_key,
        calculation_type=calculation_type,
        adapter=adapter,
        calculator_name=calculator_name,
        calculator_version=calculator_version,
        prepared_inputs=prepared_inputs,
    )
    return _build_stage_preview_body(
        context,
        adapter_result,
        stage_key=stage_key,
        calculator_name=calculator_name,
        calculator_version=calculator_version,
        reply_kind=reply_kind,
        table_projector=table_projector,
        extra_fields=extra_fields,
    )


def _apply_power_demo_catalog_disclaimer(body: dict[str, Any]) -> None:
    table = body.get("table")
    if isinstance(table, dict):
        caption = str(table.get("caption", "")).strip()
        table["caption"] = f"{caption}；{POWER_DEMO_CATALOG_DISCLAIMER_ZH}"
    markdown = str(body.get("markdown_table", "")).strip()
    if markdown:
        body["markdown_table"] = f"{markdown}\n\n{POWER_DEMO_CATALOG_DISCLAIMER_ZH}"
