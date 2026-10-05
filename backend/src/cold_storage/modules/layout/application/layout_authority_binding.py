"""Shared server-side binding for layout zone, P1 and site authorities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.adjacency import ZONE_CODES, process_graph
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)

P1_HANDOFF_IDENTITY = "p1-project-access-handoff@1.0.0"
P1_HANDOFF_SCHEMA_VERSION = "1.0.0"
DIMENSION_HANDOFF_IDENTITY = "hybrid_zone_dimension_handoff@1.0.0"
ZONE_PLAN_IDENTITY = "cold_room_zone_plan@1.0.0"
ZONE_PLAN_CALCULATOR_NAME = "cold_room_zone_plan"
ZONE_PLAN_CALCULATOR_VERSION = "1.0.0"
FLEXIBLE_ZONES = frozenset({"coating_room", "changing_room", "office"})
P1_ACCESS_REQUIREMENT_COUNT = 12


@dataclass(frozen=True)
class LayoutAuthorityBindingV1:
    """Validated inputs shared by placement and composition application paths."""

    canonical_zone_plan_hash: str
    p1_handoff_hash: str
    site_geometry_hash: str
    p1_body: Mapping[str, Any]
    dimension_authorities: Mapping[str, Mapping[str, Any]]
    access_requirements: tuple[Mapping[str, Any], ...]
    spatial_relationships: tuple[Mapping[str, Any], ...]

    def as_legacy_tuple(
        self,
    ) -> tuple[
        dict[str, Any],
        str,
        dict[str, Mapping[str, Any]],
        tuple[Mapping[str, Any], ...],
        tuple[Mapping[str, Any], ...],
    ]:
        return (
            dict(self.p1_body),
            self.p1_handoff_hash,
            dict(self.dimension_authorities),
            self.access_requirements,
            self.spatial_relationships,
        )


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error("PLACEMENT_AUTHORITY_INVALID", field=field)
    return value


def validate_canonical_zone_plan(zone_plan: object) -> Mapping[str, Any]:
    """Validate the canonical calculator identity without recalculating its result."""
    if not isinstance(zone_plan, Mapping) or (
        zone_plan.get("success") is not True
        or zone_plan.get("calculator_name") != ZONE_PLAN_CALCULATOR_NAME
        or zone_plan.get("calculator_version") != ZONE_PLAN_CALCULATOR_VERSION
    ):
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    return zone_plan


def _p1_body(handoff: object) -> tuple[dict[str, Any], str]:
    if isinstance(handoff, ZoneDimensioningResultV1):
        return handoff.to_dict(), handoff.canonical_result_hash
    if isinstance(handoff, Mapping):
        body = dict(handoff)
        return body, canonical_hash(body)
    raise _error("P1_HANDOFF_AUTHORITY_REQUIRED")


def bind_layout_authority(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: object,
    site_geometry: ValidatedSiteGeometryV1,
) -> LayoutAuthorityBindingV1:
    """Replay integrity checks and bind current zone, P1 and validated-site inputs."""
    zone_plan = validate_canonical_zone_plan(canonical_zone_plan)
    if (
        not isinstance(site_geometry, ValidatedSiteGeometryV1)
        or not site_geometry._is_authoritative()
    ):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", reason="UNVERIFIED_GEOMETRY_RESULT")

    body, handoff_hash = _p1_body(p1_handoff)
    if (
        body.get("identity") != P1_HANDOFF_IDENTITY
        or body.get("schema_version") != P1_HANDOFF_SCHEMA_VERSION
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID")
    status = _mapping(body.get("authority_status"), field="authority_status")
    required_status = (
        "dimension_authority_complete",
        "personnel_access_authority_complete",
        "material_access_authority_complete",
        "truck_access_contract_complete",
        "truck_project_input_contract_complete",
        "p1_complete",
    )
    if any(status.get(key) is not True for key in required_status):
        raise _error("P1_HANDOFF_NOT_COMPLETE", fields=list(required_status))
    if body.get("p1_closure_blockers") != [] or body.get("p2_implemented") is not False:
        raise _error("P1_HANDOFF_NOT_COMPLETE")

    geometry_body = site_geometry.to_dict()
    if geometry_body.get("source_p1_handoff_hash") != handoff_hash:
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH")

    historical = _mapping(body.get("p1e_historical_handoff"), field="p1e_historical_handoff")
    if body.get("p1e_historical_handoff_hash") != canonical_hash(historical):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="p1e_historical_handoff_hash")
    dimension = _mapping(historical.get("dimension_handoff"), field="dimension_handoff")
    if dimension.get("calculator_identity") != DIMENSION_HANDOFF_IDENTITY:
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="dimension_handoff")
    if dimension.get("source_zone_plan_calculator_identity") != ZONE_PLAN_IDENTITY:
        raise _error("ZONE_PLAN_IDENTITY_INVALID")
    zone_hash = canonical_hash(zone_plan)
    if dimension.get("source_zone_plan_result_hash") != zone_hash:
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="source_zone_plan_result_hash")
    if canonical_json(dimension.get("adjacency_graph")) != canonical_json(asdict(process_graph())):
        raise _error("P1_HANDOFF_INTEGRITY_MISMATCH", field="adjacency_graph")

    raw_authorities = dimension.get("authorities")
    if not isinstance(raw_authorities, list) or any(
        not isinstance(row, Mapping) for row in raw_authorities
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="authorities")
    authorities = {str(row["zone_code"]): row for row in raw_authorities if "zone_code" in row}
    if set(authorities) != set(ZONE_CODES) or len(authorities) != len(raw_authorities):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="authorities")
    if not all(
        authorities[code].get("dimension_mode") == "FLEXIBLE_RECTANGLE" for code in FLEXIBLE_ZONES
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="flexible_authorities")
    for code in FLEXIBLE_ZONES:
        authority = authorities[code]
        if (
            authority.get("status") != "FLEXIBLE_AUTHORIZED"
            or authority.get("p2_may_select_width_depth") is not True
            or authority.get("p2_may_change_required_area") is not False
        ):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field=code)
    concrete = set(ZONE_CODES) - FLEXIBLE_ZONES
    if any(authorities[code].get("status") != "DIMENSIONED" for code in concrete):
        raise _error("P1_HANDOFF_NOT_COMPLETE", field="concrete_dimensions")
    dimensions = dimension.get("dimensions")
    if (
        not isinstance(dimensions, list)
        or {row.get("zone_code") for row in dimensions if isinstance(row, Mapping)} != concrete
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="dimensions")

    raw_access = historical.get("access_requirements")
    if not isinstance(raw_access, list) or len(raw_access) != P1_ACCESS_REQUIREMENT_COUNT:
        raise _error(
            "P1_HANDOFF_IDENTITY_INVALID",
            field="access_requirements",
            expected_count=P1_ACCESS_REQUIREMENT_COUNT,
        )
    required_access_fields = {
        "identity",
        "from_ref",
        "to_ref",
        "flow_kind",
        "access_class",
        "profile_identity",
        "portal_required",
        "corridor_allowed",
        "direct_allowed",
        "edge_orientation_requirement",
        "route_shape_constraint",
    }
    access_rows: list[Mapping[str, Any]] = []
    access_keys: set[tuple[object, object, object]] = set()
    access_ids: set[str] = set()
    for item in raw_access:
        if not isinstance(item, Mapping) or not required_access_fields <= set(item):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        identity, source, target, flow = (
            item.get("identity"),
            item.get("from_ref"),
            item.get("to_ref"),
            item.get("flow_kind"),
        )
        if (
            not isinstance(identity, str)
            or not isinstance(source, str)
            or not isinstance(target, str)
            or not isinstance(flow, str)
        ):
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        key = (source, target, flow)
        if identity in access_ids or key in access_keys:
            raise _error("P1_HANDOFF_IDENTITY_INVALID", field="access_requirements")
        access_ids.add(identity)
        access_keys.add(key)
        access_rows.append(dict(item))

    raw_spatial = historical.get("spatial_relationships")
    if not isinstance(raw_spatial, list) or any(
        not isinstance(row, Mapping) for row in raw_spatial
    ):
        raise _error("P1_HANDOFF_IDENTITY_INVALID", field="spatial_relationships")
    return LayoutAuthorityBindingV1(
        canonical_zone_plan_hash=zone_hash,
        p1_handoff_hash=handoff_hash,
        site_geometry_hash=site_geometry.canonical_result_hash,
        p1_body=body,
        dimension_authorities={code: authorities[code] for code in ZONE_CODES},
        access_requirements=tuple(access_rows),
        spatial_relationships=tuple(dict(row) for row in raw_spatial),
    )
