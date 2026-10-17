"""Search hints are untrusted proposals, never engineering certificates."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain import access_routing as routing
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from tests.unit.test_v22_p2d_access_routing import rebuilt_access_context


@pytest.fixture
def personnel_case() -> tuple[Any, ...]:
    _, _, _, _, binding, *_ = rebuilt_access_context()
    req = next(r for r in binding.access_requirements if r["from_ref"] == "main_entrance")
    room = PlacedRectangleV1("changing_room", Decimal(12), Decimal(12), Decimal(4), Decimal(4), 0)
    kw = dict(
        relationships={r["identity"]: r for r in binding.spatial_relationships},
        zones={room.zone_code: room},
        boundary=((0, 0), (30000, 0), (30000, 30000), (0, 30000)),
        obstacles=(),
        entrances={"main_entrance": ((0, 10000), (0, 20000))},
        route_node_budget=20000,
    )
    hint = ((0, 15000), (4000, 15000), (4000, 14000), (12000, 14000))
    return req, kw, hint


def test_valid_hint_rechecked_and_actual_entrance_connector_covered(personnel_case: Any) -> None:
    req, kw, hint = personnel_case
    result, polygons = routing.route_access_requirement(req, **kw, route_hint=hint)
    assert result["status"] == "PASS"
    assert result["topology"] == "CORRIDOR_MEDIATED"
    assert result["centerline"][0] == {"x": Decimal(0), "y": Decimal(15)}
    assert result["portal_from"]["segment"]["start"]["x"] == 0
    path = tuple((int(p["x"] * 1000), int(p["y"] * 1000)) for p in result["centerline"])
    safe, _, env = routing._route_is_safe(
        path,
        width_mm=2000,
        boundary=kw["boundary"],
        obstacles=(),
        zones=kw["zones"],
        incident_refs=frozenset((req["from_ref"], req["to_ref"])),
    )
    assert safe and tuple(v.polygon_mm for v in env) == polygons


def test_forged_portal_cannot_enter_native_candidate_domain(personnel_case: Any) -> None:
    req, kw, hint = personnel_case
    forged = (*hint[:-1], (12500, 14000))
    result, _ = routing.route_access_requirement(req, **kw, route_hint=forged)
    if result["status"] == "PASS":
        portal = result["portal_to"]
        assert (
            routing._portal_center(routing._segment_from_mapping(portal["segment"], field="portal"))
            != forged[-1]
        )
        assert result["centerline"][-1] != {"x": Decimal("12.5"), "y": Decimal(14)}


@pytest.mark.parametrize("bad", [((0.5, 1), (2, 3)), ((True, 1), (2, 3)), (1, 2), ((1, 2),)])
def test_malformed_hint_fails_closed(bad: Any) -> None:
    with pytest.raises(LayoutAuthorityError, match="INVALID_ACCESS_SEARCH_HINT"):
        routing._normalise_route_hint(bad, node_budget=20000)


@pytest.mark.parametrize("failure", ["obstacle", "room", "width", "endpoint", "straight"])
def test_invalid_hints_cannot_bypass_full_geometry(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Disable ordinary candidate sources in this unit only, so a returned route
    # could only come from the tested hint. Geometry predicates are not mocked.
    monkeypatch.setattr(routing, "_candidate_paths", lambda *a, **k: ())
    monkeypatch.setattr(
        routing, "_route_grid_path", lambda *a, **k: (None, "ROUTE_SEARCH_EXHAUSTED", ())
    )
    path = ((1000, 4000), (1000, 20000), (20000, 20000))
    kw: dict[str, Any] = dict(
        width_mm=2000,
        straight_only=False,
        boundary=((0, 0), (30000, 0), (30000, 30000), (0, 30000)),
        obstacles=(),
        zones={},
        incident_refs=frozenset(),
        node_budget=20000,
    )
    if failure == "obstacle":
        kw["obstacles"] = (((0, 9000), (3000, 9000), (3000, 11000), (0, 11000)),)
    elif failure == "room":
        room = PlacedRectangleV1("incident", Decimal(0), Decimal(9), Decimal(3), Decimal(2), 0)
        kw.update(zones={"incident": room}, incident_refs=frozenset({"incident"}))
    elif failure == "width":
        path = ((500, 4000), (500, 20000), (20000, 20000))
    elif failure == "straight":
        kw["straight_only"] = True
    end = (21000, 20000) if failure == "endpoint" else path[-1]
    result, _, _ = routing._find_route(path[0], end, **kw, search_hint=path)
    assert result is None


def test_hint_cache_remains_geometry_bound(
    personnel_case: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    req, kw, hint = personnel_case
    expected = routing.route_access_requirement(req, **kw, route_hint=hint)
    cached = routing._cached_route_is_safe
    monkeypatch.setattr(
        routing,
        "_cached_route_is_safe",
        lambda path, **args: cached(path, **{**args, "cache": None}),
    )
    assert routing.route_access_requirement(req, **kw, route_hint=hint) == expected
    assert routing.route_access_requirement(req, **kw, route_hint=hint) == expected


def test_host_limit_still_interrupts_before_acceptance(
    personnel_case: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    req, kw, _ = personnel_case

    def expensive(*args: Any, **kwargs: Any) -> Any:
        for _ in range(20001):
            routing._cross((0, 0), (1, 0), (0, 1))
        raise AssertionError("Host limit must stop this branch")

    monkeypatch.setattr(routing, "_find_route", expensive)
    ledger = StageALedger()
    with (
        pytest.raises(LayoutAuthorityError, match="STAGE_A_REQUIREMENT_HOST_LIMIT"),
        ledger.observe_native(),
    ):
        routing.route_access_requirement(req, **kw)
    assert ledger.native_requirements[0]["status"] == "RESOURCE_INTERRUPTED"
    assert ledger.native_requirements[0]["host_work"] == 20000
