"""Stateless Aily / 豆包 preview for the V2.1 factory-power capability.

This module only composes existing authorities.  The zone preview adapter
produces the canonical upstream snapshot, the V2.1 projects adapter binds its
areas, the V2.0 calculator produces the canonical result, and the shared Aily
projector supplies the read-only presentation.  No engineering values are
calculated here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, cast

from cold_storage.modules.aily.application.factory_power_table import (
    project_factory_power_table,
)
from cold_storage.modules.aily.application.preview_bundle import assemble_preview_context
from cold_storage.modules.aily.application.stage_preview import (
    execute_zone_preview_authority,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.calculations.domain.factory_power_estimation import (
    FactoryPowerEstimationError,
    serialize_factory_power_result,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)
from cold_storage.modules.projects.application.factory_power_upstream_authority import (
    FactoryPowerUpstreamAuthorityError,
    calculate_factory_power_from_zone_plan,
)

PREVIEW_FACTORY_POWER_INPUT_FIELDS = OPERATOR_V09_FIVE_KEY_FIELDS
MCP_INPUT_SCHEMA_REJECTED = "MCP_INPUT_SCHEMA_REJECTED"


def preview_factory_power(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Run the stateless canonical zone-plan -> factory-power preview chain."""
    _reject_unknown_mcp_keys(payload)
    context = assemble_preview_context(payload, correlation_id=correlation_id)
    zone_result = execute_zone_preview_authority(context)
    zone_plan_snapshot = _zone_plan_snapshot(zone_result)
    try:
        canonical_result = calculate_factory_power_from_zone_plan(zone_plan_snapshot)
    except (FactoryPowerUpstreamAuthorityError, FactoryPowerEstimationError) as exc:
        raise _authority_error(exc) from exc

    projected = project_factory_power_table(serialize_factory_power_result(canonical_result))
    if projected.get("available") is not True:
        raise AilyConnectorError(
            code="V20_FACTORY_POWER_CANONICAL_RESULT_UNAVAILABLE",
            message="factory-power canonical result is unavailable for presentation",
            field_path="factory_power_presentation",
        )

    body = deepcopy(projected)
    body["product_name"] = "豆包工作伙伴"
    body["connector"] = "aily"
    body["operator_keys"] = deepcopy(context.operator_input["zone_planning_inputs"])
    body["persisted"] = False
    body["markdown_table"] = _format_projected_table(body.get("table"))
    return body


def _reject_unknown_mcp_keys(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise AilyConnectorError(
            code=MCP_INPUT_SCHEMA_REJECTED,
            message="preview_factory_power accepts exactly the five operator KEY",
            field_path="arguments",
        )

    allowed = set(PREVIEW_FACTORY_POWER_INPUT_FIELDS)
    unexpected = sorted(str(key) for key in payload if key not in allowed)
    if unexpected:
        raise AilyConnectorError(
            code=MCP_INPUT_SCHEMA_REJECTED,
            message="preview_factory_power does not accept unknown or area fields",
            field_path="arguments",
            details={"unexpected_keys": ", ".join(unexpected)},
        )


def _zone_plan_snapshot(adapter_result: AdapterResult) -> dict[str, object]:
    """Build a traceable canonical zone-plan envelope from AdapterResult only."""
    return {
        "success": adapter_result.calculator_success,
        "calculator_name": adapter_result.calculator_name,
        "calculator_version": adapter_result.calculator_version,
        "calculator_identity": (
            f"{adapter_result.calculator_name}@{adapter_result.calculator_version}"
        ),
        "input": deepcopy(adapter_result.execution_input_snapshot),
        "result": deepcopy(dict(adapter_result.payload)),
        "formula_references": deepcopy(list(adapter_result.provenance.formulas)),
        "coefficients": deepcopy(list(adapter_result.provenance.coefficients)),
        "assumptions": list(adapter_result.provenance.assumptions),
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "details": deepcopy(warning.details),
            }
            for warning in adapter_result.warnings
        ],
        "source_references": deepcopy(list(adapter_result.provenance.source_references)),
        "requires_review": adapter_result.requires_review,
    }


def _authority_error(
    exc: FactoryPowerUpstreamAuthorityError | FactoryPowerEstimationError,
) -> AilyConnectorError:
    """Preserve backend blocker identity and details at the MCP boundary."""
    return AilyConnectorError(
        code=exc.code,
        message=str(exc),
        field_path="factory_power",
        details=cast(dict[str, str], dict(exc.details)),
    )


def _format_projected_table(table: object) -> str:
    """Copy projector cells into Markdown without interpreting engineering values."""
    if not isinstance(table, Mapping):
        return ""
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes)):
        return ""
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return ""

    column_mappings = [item for item in columns if isinstance(item, Mapping)]
    if not column_mappings:
        return ""
    header = "| " + " | ".join(_cell(item.get("label")) for item in column_mappings) + " |"
    separator = "|" + "|".join("---" for _item in column_mappings) + "|"
    lines = [header, separator]
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            continue
        cells = [_cell(raw_row.get(str(column.get("key")))) for column in column_mappings]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _cell(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "｜").strip()
    return text if text else "—"


__all__ = [
    "MCP_INPUT_SCHEMA_REJECTED",
    "PREVIEW_FACTORY_POWER_INPUT_FIELDS",
    "preview_factory_power",
]
