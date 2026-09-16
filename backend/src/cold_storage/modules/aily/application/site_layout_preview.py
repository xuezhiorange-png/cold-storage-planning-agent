"""Application orchestration for the V2.2 site-layout MCP preview.

This module is deliberately a thin integration boundary.  The five operator
keys are executed by the existing zone-planning adapter, and every downstream
layout step consumes the already-owned P1/P2/P3 contracts.  No engineering
formula, placement rule, route rule, or drawing geometry is implemented here.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from cold_storage.modules.aily.application.preview_bundle import (
    assemble_preview_context,
    json_ready,
)
from cold_storage.modules.aily.application.stage_preview import (
    execute_zone_preview_authority,
)
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.layout.application.access_routing import route_site_placement
from cold_storage.modules.layout.application.p1_project_handoff import (
    build_p1_project_handoff,
)
from cold_storage.modules.layout.application.placement import place_zones
from cold_storage.modules.layout.application.site_geometry import (
    validate_site_geometry,
)
from cold_storage.modules.layout.application.svg_projection import (
    project_validated_layout_to_svg,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.truck_maneuver import (
    BoundTruckManeuverProjectInputV1,
)
from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
)
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

PREVIEW_SITE_LAYOUT_TOOL_NAME = "preview_site_layout"
SITE_LAYOUT_RESULT_IDENTITY = "site_validated_layout@1.0.0"
SVG_PROJECTION_RESULT_IDENTITY = "validated-layout-svg-projection@1.0.0"

# The P2 search is already bounded and deterministic.  These are orchestration
# budgets only; they are not new layout or engineering authority.
P4_PLACEMENT_NODE_BUDGET = 5_000
P4_ROUTE_NODE_BUDGET = 5_000
P4_TRUCK_NODE_BUDGET = 5_000

PREVIEW_SITE_LAYOUT_INPUT_FIELDS: tuple[str, ...] = (
    *OPERATOR_V09_FIVE_KEY_FIELDS,
    "site_constraints",
    "truck_access",
)
_SITE_LAYOUT_INPUT_FIELD_SET = frozenset(PREVIEW_SITE_LAYOUT_INPUT_FIELDS)
_FIVE_KEY_FIELD_SET = frozenset(OPERATOR_V09_FIVE_KEY_FIELDS)
_PROJECT_TRUCK_LENGTH_FIELDS = ("vehicle_width_m", "vehicle_length_m")


def _input_error(
    code: str,
    message: str,
    field_path: str,
    *,
    missing_keys: tuple[str, ...] = (),
    ask_operator: str = "",
    **details: object,
) -> AilyConnectorError:
    return AilyConnectorError(
        code=code,
        message=message,
        field_path=field_path,
        missing_keys=missing_keys,
        ask_operator=ask_operator,
        details={key: str(value) for key, value in details.items()},
    )


def _validate_tool_input(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    """Validate the strict Tool 7 boundary before any authority is executed."""
    if not isinstance(payload, Mapping):
        raise _input_error(
            "MCP_INPUT_SCHEMA_REJECTED",
            "preview_site_layout requires an object of structured arguments",
            "arguments",
        )

    keys = set(payload)
    unknown = sorted(keys - _SITE_LAYOUT_INPUT_FIELD_SET)
    if unknown:
        raise _input_error(
            "MCP_INPUT_SCHEMA_REJECTED",
            "preview_site_layout accepts only five business keys, site_constraints, "
            "and truck_access",
            "arguments",
            unexpected_keys=unknown,
        )

    missing_business = tuple(
        field for field in OPERATOR_V09_FIVE_KEY_FIELDS if field not in payload
    )
    if missing_business:
        # Reuse the existing five-key validator so its error code and Chinese
        # operator prompt remain identical to the first five tools.
        from cold_storage.modules.aily.application.operator_payload import (
            normalize_aily_operator_payload,
        )

        try:
            normalize_aily_operator_payload(
                {field: payload[field] for field in keys & _FIVE_KEY_FIELD_SET}
            )
        except AilyConnectorError as error:
            raise error from None
        raise _input_error(
            "MISSING_ENGINEERING_PARAMETER",
            "缺少五个业务参数",
            "arguments",
            missing_keys=missing_business,
            ask_operator="请提供缺失的业务参数。",
        )

    site = payload.get("site_constraints")
    if not isinstance(site, Mapping):
        raise _input_error(
            "PROJECT_INPUT_REQUIRED",
            "site_constraints is required; do not use a default rectangular site",
            "site_constraints",
            missing_keys=("site_constraints",),
            ask_operator=(
                "请提供场地边界、可建设边界（如有）、人员入口、货车入口、禁建区和既有建筑信息。"
            ),
        )

    truck = payload.get("truck_access")
    if not isinstance(truck, Mapping):
        raise _input_error(
            "PROJECT_INPUT_REQUIRED",
            "truck_access requires a bound project maneuver input",
            "truck_access",
            missing_keys=("truck_access",),
            ask_operator="请提供已绑定的项目货车参数和批准机动模板；不得使用默认车型或默认路径。",
        )

    business = {field: payload[field] for field in OPERATOR_V09_FIVE_KEY_FIELDS}
    return business, site, truck


def _zone_plan_snapshot(adapter_result: AdapterResult) -> dict[str, Any]:
    """Copy the actual zone adapter result into the P1 canonical envelope."""
    if (
        adapter_result.calculator_success is not True
        or adapter_result.calculator_name != "cold_room_zone_plan"
        or adapter_result.calculator_version != "1.0.0"
        or not isinstance(adapter_result.payload, Mapping)
    ):
        raise LayoutAuthorityError(
            "ZONE_PLAN_IDENTITY_INVALID",
            calculator_name=adapter_result.calculator_name,
            calculator_version=adapter_result.calculator_version,
        )
    # AdapterResult uses immutable tuples and Decimal leaves for nested result
    # collections.  The existing serialized zone-plan/P1 boundary is
    # JSON-shaped; this representation normalization is not a new authority.
    result = cast(
        dict[str, Any],
        json_ready(copy.deepcopy(dict(adapter_result.payload))),
    )
    return {
        "success": True,
        "calculator_name": adapter_result.calculator_name,
        "calculator_version": adapter_result.calculator_version,
        "calculator_identity": (
            f"{adapter_result.calculator_name}@{adapter_result.calculator_version}"
        ),
        "input": copy.deepcopy(adapter_result.execution_input_snapshot),
        "result": result,
        "formula_references": copy.deepcopy(list(adapter_result.provenance.formulas)),
        "coefficients": copy.deepcopy(list(adapter_result.provenance.coefficients)),
        "assumptions": list(adapter_result.provenance.assumptions),
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "details": copy.deepcopy(warning.details),
            }
            for warning in adapter_result.warnings
        ],
        "source_references": copy.deepcopy(list(adapter_result.provenance.source_references)),
        "requires_review": adapter_result.requires_review,
    }


def _bound_truck_input(
    source: Mapping[str, Any],
) -> tuple[BoundTruckManeuverProjectInputV1, dict[str, Any]]:
    """Validate the P2B1-bound truck authority and expose its P1F input."""
    try:
        bound = BoundTruckManeuverProjectInputV1.from_mapping(source)
    except LayoutAuthorityError:
        raise
    p1f = bound.p1f_input
    for field in _PROJECT_TRUCK_LENGTH_FIELDS:
        value = p1f.get(field)
        if isinstance(value, str):
            try:
                p1f[field] = Decimal(value)
            except ArithmeticError:
                raise LayoutAuthorityError("INVALID_PROJECT_TRUCK_INPUT", field=field) from None
    return bound, p1f


def _first_routing_failure(body: Mapping[str, Any]) -> str:
    for result in body.get("access_results", []):
        if not isinstance(result, Mapping) or result.get("status") == "PASS":
            continue
        codes = result.get("codes")
        if isinstance(codes, list) and codes and isinstance(codes[0], str):
            return codes[0]
    status = body.get("truck_route_status")
    if isinstance(status, str) and status:
        return status
    warnings = body.get("warnings")
    if isinstance(warnings, list) and warnings and isinstance(warnings[0], str):
        return warnings[0]
    return "PROJECT_LAYOUT_VALIDATION_FAILED"


def _require_successful_placement(result: object) -> None:
    if not hasattr(result, "to_dict"):
        raise LayoutAuthorityError("LAYOUT_SEARCH_EXHAUSTED")
    body = result.to_dict()
    if not isinstance(body, Mapping) or body.get("placement_available") is not True:
        status = body.get("status") if isinstance(body, Mapping) else None
        raise LayoutAuthorityError(
            str(status) if isinstance(status, str) else "LAYOUT_SEARCH_EXHAUSTED"
        )


def _require_successful_routing(result: object) -> Mapping[str, Any]:
    if not hasattr(result, "to_dict"):
        raise LayoutAuthorityError("PROJECT_LAYOUT_VALIDATION_FAILED")
    body = result.to_dict()
    if not isinstance(body, Mapping):
        raise LayoutAuthorityError("PROJECT_LAYOUT_VALIDATION_FAILED")
    if body.get("project_layout_validated") is not True or body.get("p2_complete") is not True:
        raise LayoutAuthorityError(_first_routing_failure(body))
    return body


def preview_site_layout(
    payload: Mapping[str, Any],
    *,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Execute the canonical five-key -> P1 -> P2 -> P3 preview chain."""
    business, site, truck_source = _validate_tool_input(payload)
    context = assemble_preview_context(business, correlation_id=correlation_id)
    adapter_result = execute_zone_preview_authority(context)
    zone_plan = _zone_plan_snapshot(adapter_result)
    bound_truck, p1f_input = _bound_truck_input(truck_source)

    p1_handoff = build_p1_project_handoff(zone_plan, p1f_input)
    project_input = {
        "site_constraints": copy.deepcopy(dict(site)),
        "truck_access": p1f_input,
    }
    site_geometry = validate_site_geometry(
        project_input,
        zone_plan,
        p1_handoff=p1_handoff,
    )
    placement = place_zones(
        zone_plan,
        p1_handoff,
        site_geometry,
        node_budget=P4_PLACEMENT_NODE_BUDGET,
        complete_candidate_limit=None,
    )
    _require_successful_placement(placement)
    routed = route_site_placement(
        zone_plan,
        p1_handoff,
        site_geometry,
        placement,
        bound_truck,
        route_node_budget=P4_ROUTE_NODE_BUDGET,
        truck_node_budget=P4_TRUCK_NODE_BUDGET,
    )
    route_body = _require_successful_routing(routed)
    drawing = project_validated_layout_to_svg(
        routed,
        site_geometry=site_geometry,
    )
    layout_body = routed.to_dict()
    drawing_body = drawing.to_dict()
    source_hashes = {
        field: layout_body[field]
        for field in (
            "source_zone_plan_hash",
            "source_p1_handoff_hash",
            "source_site_geometry_hash",
            "source_objective_profile_hash",
            "source_placement_result_hash",
            "source_truck_maneuver_binding_hash",
        )
        if field in layout_body
    }
    return cast(
        dict[str, Any],
        json_ready(
            {
                "reply_kind": "site_layout_projection",
                "layout": layout_body,
                "drawing": drawing_body,
                "layout_identity": SITE_LAYOUT_RESULT_IDENTITY,
                "drawing_identity": SVG_PROJECTION_RESULT_IDENTITY,
                "canonical_result_hash": layout_body.get("canonical_result_hash"),
                "svg_sha256": drawing_body.get("svg_sha256"),
                "view_box": drawing_body.get("view_box"),
                "zone_count": layout_body.get("zone_count"),
                "project_layout_validated": True,
                "p2_complete": True,
                "requires_review": True,
                "concept_design": True,
                "projection_only": True,
                "engineering_coordinates_mutated": False,
                "source_hashes": source_hashes,
                "route_metrics": route_body.get("route_metrics"),
                "warnings": [
                    "概念设计结果，需要工程复核，不是施工图。",
                    "SVG 是结构化布局 JSON 的展示投影，不是计算 authority。",
                ],
                "message": "受场地约束的概念平面图已生成，需要工程复核，不是施工图。",
                "persisted": False,
            }
        ),
    )


__all__ = [
    "P4_PLACEMENT_NODE_BUDGET",
    "P4_ROUTE_NODE_BUDGET",
    "P4_TRUCK_NODE_BUDGET",
    "PREVIEW_SITE_LAYOUT_INPUT_FIELDS",
    "PREVIEW_SITE_LAYOUT_TOOL_NAME",
    "preview_site_layout",
]
