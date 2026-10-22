"""Strict hard-obstacle input projection; site geometry authority stays frozen."""

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.domain.site_geometry import PolygonMM, _error, normalize_polygon


def validated_hard_obstacle_polygons(
    site_geometry_payload: Mapping[str, Any],
) -> tuple[PolygonMM, ...]:
    """Parse only validated hard authority, preserving source order; never fallback.

    Retained/conditional classification belongs to the site authority upstream.
    This pure parser neither reinterprets that classification nor invents geometry.
    """
    obstacles = site_geometry_payload.get("obstacles")
    if not isinstance(obstacles, Mapping):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="obstacles")
    hard = obstacles.get("hard_obstacles")
    if not isinstance(hard, list):
        raise _error("INVALID_SITE_GEOMETRY_RESULT", field="hard_obstacles")
    polygons = []
    for index, obstacle in enumerate(hard):
        if (
            not isinstance(obstacle, Mapping)
            or obstacle.get("hard") is not True
            or "footprint" not in obstacle
        ):
            raise _error("INVALID_SITE_GEOMETRY_RESULT", field=f"hard_obstacles[{index}]")
        polygons.append(
            normalize_polygon(
                obstacle["footprint"],
                error_code="INVALID_SITE_GEOMETRY_RESULT",
                allow_numeric_string=True,
            )
        )
    return tuple(polygons)
