"""Application boundary for the V2.2 validated-layout SVG projection.

The service accepts the immutable P2D result and the already validated site
geometry context.  It only serializes source geometry for browser display; it
does not run placement, access routing, truck validation, or engineering
calculations.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.application.access_routing import SiteAccessRoutingResultV1
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.svg_projection import (
    SVG_PROJECTION_IDENTITY,
    SvgDrawingThemeV1,
    ValidatedLayoutSvgProjectionV1,
    build_projection_payload,
)

P2D_RESULT_IDENTITY = "site_validated_layout@1.0.0"
P2D_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


def _error(code: str, **details: object) -> LayoutAuthorityError:
    return LayoutAuthorityError(code, **details)


def _validated_layout_body(
    validated_layout: SiteAccessRoutingResultV1 | Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if isinstance(validated_layout, SiteAccessRoutingResultV1):
        result = validated_layout
    elif isinstance(validated_layout, Mapping):
        try:
            result = SiteAccessRoutingResultV1.from_mapping(validated_layout)
        except LayoutAuthorityError as error:
            raise _error("P2D_RESULT_INTEGRITY_MISMATCH", reason=error.code) from None
    else:
        raise _error("VALIDATED_LAYOUT_REQUIRED", reason="P2D_RESULT_REQUIRED")
    body = result.to_dict()
    if (
        body.get("result_identity") != P2D_RESULT_IDENTITY
        or body.get("schema_version") != P2D_SCHEMA_VERSION
    ):
        raise _error(
            "VALIDATED_LAYOUT_REQUIRED",
            reason="INVALID_SITE_VALIDATED_LAYOUT_IDENTITY",
            expected_identity=P2D_RESULT_IDENTITY,
        )
    if body.get("project_layout_validated") is not True or body.get("p2_complete") is not True:
        raise _error("VALIDATED_LAYOUT_REQUIRED", reason="PROJECT_LAYOUT_NOT_VALIDATED")
    if body.get("zone_count") != 12 or body.get("access_requirement_count") != 12:
        raise _error("VALIDATED_LAYOUT_REQUIRED", reason="INCOMPLETE_VALIDATED_LAYOUT")
    if body.get("access_result_count") != 12 or body.get("access_pass_count") != 12:
        raise _error("VALIDATED_LAYOUT_REQUIRED", reason="ACCESS_RESULTS_NOT_COMPLETE")
    if (
        body.get("truck_route_validated") is not True
        or body.get("access_route_validated") is not True
    ):
        raise _error("VALIDATED_LAYOUT_REQUIRED", reason="ROUTE_VALIDATION_NOT_COMPLETE")
    if not isinstance(body.get("building_footprint"), Mapping):
        raise _error("VALIDATED_LAYOUT_REQUIRED", reason="BUILDING_FOOTPRINT_REQUIRED")
    for field in (
        "source_zone_plan_hash",
        "source_p1_handoff_hash",
        "source_site_geometry_hash",
        "source_objective_profile_hash",
        "source_placement_result_hash",
        "source_truck_maneuver_binding_hash",
    ):
        value = body.get(field)
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise _error("VALIDATED_LAYOUT_REQUIRED", field=field, reason="SOURCE_HASH_REQUIRED")
    return body, result.canonical_result_hash


def project_validated_layout_to_svg(
    validated_layout: SiteAccessRoutingResultV1 | Mapping[str, Any],
    *,
    site_geometry: ValidatedSiteGeometryV1,
    theme: SvgDrawingThemeV1 | None = None,
) -> ValidatedLayoutSvgProjectionV1:
    """Project one fully validated P2D layout into deterministic static SVG.

    P2D stores the source-site hash rather than duplicating the complete site
    geometry in its final result.  The caller therefore supplies the original
    server-validated geometry object; its hash must match the P2D provenance.
    """
    body, source_layout_hash = _validated_layout_body(validated_layout)
    if (
        not isinstance(site_geometry, ValidatedSiteGeometryV1)
        or not site_geometry._is_authoritative()
    ):
        raise _error("VALIDATED_SITE_GEOMETRY_REQUIRED", reason="UNVERIFIED_GEOMETRY_RESULT")
    if body.get("source_site_geometry_hash") != site_geometry.canonical_result_hash:
        raise _error(
            "P2D_RESULT_INTEGRITY_MISMATCH",
            field="source_site_geometry_hash",
            expected=site_geometry.canonical_result_hash,
            actual=body.get("source_site_geometry_hash"),
        )
    payload = build_projection_payload(
        body,
        site_geometry.to_dict(),
        source_layout_hash=source_layout_hash,
        theme=theme,
    )
    return ValidatedLayoutSvgProjectionV1.from_payload(payload)


render_validated_layout_svg = project_validated_layout_to_svg

__all__ = [
    "SVG_PROJECTION_IDENTITY",
    "SvgDrawingThemeV1",
    "ValidatedLayoutSvgProjectionV1",
    "project_validated_layout_to_svg",
    "render_validated_layout_svg",
]
