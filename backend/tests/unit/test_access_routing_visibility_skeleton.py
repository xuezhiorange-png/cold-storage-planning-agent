"""Construction hints reuse the final router's finite visibility graph."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest

from cold_storage.modules.layout.domain.access_routing import (
    _find_route_skeleton_endpoints_v1,
    _find_route_skeleton_v1,
    _route_is_safe,
)
from cold_storage.modules.layout.domain.placement import AccessDrivenTailCandidateV1
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1

BOUNDARY = ((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000))
SOURCE = PlacedRectangleV1("sorting_packaging_room", 10, 45, 10, 10)
TARGET = PlacedRectangleV1("frozen_fruit_room", 80, 45, 10, 10)
FIXED = PlacedRectangleV1("fixed_room", 40, 40, 5, 20)
TRUCK = ((55_000, 40_000), (60_000, 40_000), (60_000, 60_000), (55_000, 60_000))
INCIDENT_REFS = frozenset({"sorting_packaging_room", "frozen_fruit_room"})


def _search(
    *,
    zones: dict[str, PlacedRectangleV1],
    obstacles=(),
    keepouts=(),
    node_budget: int = 20_000,
):
    return _find_route_skeleton_v1(
        (20_000, 50_000),
        (80_000, 50_000),
        width_mm=2_500,
        straight_only=False,
        boundary=BOUNDARY,
        obstacles=obstacles,
        zones=zones,
        incident_refs=INCIDENT_REFS,
        node_budget=node_budget,
        additional_keepouts=keepouts,
    )


@pytest.mark.parametrize(
    ("zones", "keepouts"),
    [
        ({SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET, FIXED.zone_code: FIXED}, ()),
        ({SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET}, (TRUCK,)),
        ({SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET, FIXED.zone_code: FIXED}, (TRUCK,)),
    ],
)
def test_shared_visibility_graph_finds_exact_clear_detour_around_keepouts(zones, keepouts):
    result = _search(zones=zones, keepouts=keepouts)

    assert result.path is not None
    assert len(result.path) >= 4
    assert result.envelopes
    assert result.node_budget_exhausted is False
    assert result.graph_exhausted is False
    safe, _reason, authoritative_envelopes = _route_is_safe(
        result.path,
        width_mm=2_500,
        boundary=BOUNDARY,
        obstacles=keepouts,
        zones=zones,
        incident_refs=INCIDENT_REFS,
    )
    assert safe is True
    assert result.envelopes == authoritative_envelopes


def test_visibility_route_uses_only_finite_geometry_derived_event_coordinates():
    result = _search(
        zones={SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET, FIXED.zone_code: FIXED},
        keepouts=(TRUCK,),
    )

    assert result.path is not None
    half = 1_250
    event_x = {0, 100_000, 20_000, 80_000}
    event_y = {0, 100_000, 50_000}
    for rectangle in (SOURCE, TARGET, FIXED):
        left, bottom, right, top = rectangle.bounds_mm
        event_x.update((left - half, left, right, right + half))
        event_y.update((bottom - half, bottom, top, top + half))
    for x, y in TRUCK:
        event_x.update((x, x - half, x + half, x - half - 1, x + half + 1))
        event_y.update((y, y - half, y + half, y - half - 1, y + half + 1))
    assert all(x in event_x and y in event_y for x, y in result.path)


def test_route_search_provenance_separates_budget_from_graph_exhaustion():
    limited = _search(
        zones={SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET, FIXED.zone_code: FIXED},
        node_budget=1,
    )
    wall = PlacedRectangleV1("wall", 40, 0, 5, 100)
    exhausted = _search(zones={SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET, "wall": wall})

    assert limited.node_budget_exhausted is True
    assert limited.graph_exhausted is False
    assert exhausted.node_budget_exhausted is False
    assert exhausted.graph_exhausted is True
    assert exhausted.path is None


def test_visibility_endpoint_enumerator_is_finite_safe_and_deterministic():
    zones = {SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET, FIXED.zone_code: FIXED}
    args = {
        "width_mm": 2_500,
        "boundary": BOUNDARY,
        "obstacles": (),
        "zones": zones,
        "incident_refs": INCIDENT_REFS,
        "node_budget": 5_000,
        "endpoint_limit": 64,
        "additional_keepouts": (TRUCK,),
    }
    first = _find_route_skeleton_endpoints_v1((20_000, 50_000), **args)
    second = _find_route_skeleton_endpoints_v1((20_000, 50_000), **args)

    assert first.endpoint_skeletons
    assert first.endpoint_skeletons == second.endpoint_skeletons
    assert first.search_source == "VISIBILITY_EVENT_GRAPH_ENDPOINTS"
    assert first.node_budget_exhausted is False
    assert all(len(row.path) >= 2 and row.envelopes for row in first.endpoint_skeletons)
    assert all(
        _route_is_safe(
            row.path,
            width_mm=2_500,
            boundary=BOUNDARY,
            obstacles=(TRUCK,),
            zones=zones,
            incident_refs=INCIDENT_REFS,
        )[0]
        for row in first.endpoint_skeletons
    )


def test_visibility_endpoint_enumerator_keeps_distinct_arrival_directions():
    result = _find_route_skeleton_endpoints_v1(
        (20_000, 50_000),
        width_mm=2_500,
        boundary=BOUNDARY,
        obstacles=(),
        zones={SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET, FIXED.zone_code: FIXED},
        incident_refs=INCIDENT_REFS,
        node_budget=5_000,
        endpoint_limit=10_000,
        additional_keepouts=(TRUCK,),
    )
    arrivals: dict[tuple[int, int], set[str]] = defaultdict(set)
    for row in result.endpoint_skeletons:
        axis = "H" if row.path[-1][1] == row.path[-2][1] else "V"
        arrivals[row.endpoint].add(axis)

    assert any(len(axes) > 1 for axes in arrivals.values())


def test_visibility_route_can_target_a_portal_arrival_direction():
    result = _find_route_skeleton_v1(
        (20_000, 50_000),
        (80_000, 50_000),
        width_mm=2_500,
        straight_only=False,
        boundary=BOUNDARY,
        obstacles=(),
        zones={SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET},
        incident_refs=frozenset({SOURCE.zone_code, TARGET.zone_code}),
        node_budget=1_000,
        required_start_direction=(1, 0),
        required_arrival_direction=(1, 0),
    )

    assert result.path == ((20_000, 50_000), (80_000, 50_000))
    assert result.envelopes
    assert result.node_budget_exhausted is False


def test_visibility_route_rejects_wrong_portal_arrival_direction():
    narrow_boundary = ((0, 0), (100_000, 0), (100_000, 2_500), (0, 2_500))
    result = _find_route_skeleton_v1(
        (20_000, 1_250),
        (80_000, 1_250),
        width_mm=2_500,
        straight_only=False,
        boundary=narrow_boundary,
        obstacles=(),
        zones={},
        incident_refs=frozenset(),
        node_budget=1_000,
        required_start_direction=(1, 0),
        required_arrival_direction=(-1, 0),
    )

    assert result.path is None
    assert result.reason == "NO_DIRECTION_COMPATIBLE_PATH"
    assert result.graph_exhausted is True


def test_extra_construction_keepout_does_not_change_default_route_search():
    zones = {SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET}
    without = _search(zones=zones)
    with_remote_keepout = _search(
        zones=zones,
        keepouts=(((10_000, 80_000), (20_000, 80_000), (20_000, 90_000), (10_000, 90_000)),),
    )

    assert without.path == with_remote_keepout.path
    assert without.envelopes == with_remote_keepout.envelopes


def test_closed_obstacle_clearance_has_exact_one_millimetre_event():
    obstacle = ((40_000, 40_000), (60_000, 40_000), (60_000, 60_000), (40_000, 60_000))
    result = _search(
        zones={SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET},
        obstacles=(obstacle,),
    )

    assert result.path is not None
    assert any(abs(point[1] - 40_000) == 1_251 for point in result.path) or any(
        abs(point[1] - 60_000) == 1_251 for point in result.path
    )
    safe, _reason, _envelopes = _route_is_safe(
        result.path,
        width_mm=2_500,
        boundary=BOUNDARY,
        obstacles=(obstacle,),
        zones={SOURCE.zone_code: SOURCE, TARGET.zone_code: TARGET},
        incident_refs=INCIDENT_REFS,
    )
    assert safe is True


def test_only_real_frozen_corridor_skeletons_may_use_mediated_event_class():
    rectangle = PlacedRectangleV1("frozen_fruit_room", Decimal(1), Decimal(1), 2, 2)
    base = {
        "module_name": "FROZEN_SUPPORT_MODULE",
        "placements": (("frozen_fruit_room", rectangle),),
        "driving_requirement_ids": ("sorting-to-frozen",),
        "anchor_source": "sorting-portal|visibility-event",
        "direct_shared_edge_possible": False,
    }
    pending = AccessDrivenTailCandidateV1(
        **base,
        endpoint_event_class="FROZEN_ENDPOINT_PAIR_ROUTE_PENDING",
    )
    assert pending.construction_corridor_centerline_mm == ()
    with pytest.raises(ValueError, match="real corridor skeleton"):
        AccessDrivenTailCandidateV1(
            **base,
            endpoint_event_class="FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED",
        )
    real = AccessDrivenTailCandidateV1(
        **base,
        endpoint_event_class="FROZEN_TRUCK_CLEAR_CORRIDOR_MEDIATED",
        construction_corridor_centerline_mm=((0, 0), (1_000, 0)),
        construction_corridor_envelopes_mm=(
            ((0, -1_250), (1_000, -1_250), (1_000, 1_250), (0, 1_250)),
        ),
    )
    assert len(real.construction_corridor_centerline_mm) == 2
    assert len(real.construction_corridor_envelopes_mm) == 1
