"""Solve the actual endpoint, portal and corridor constraints in isolation.

Only unrelated base room/composition construction is isolated. No engineering
validator is mocked; these small tests do not claim full engineering acceptance.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from ortools.sat.python import cp_model

from cold_storage.modules.layout.application.global_composition_solver import StageALedger
from cold_storage.modules.layout.domain.access_authority import PERSONNEL
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.global_cp_sat_model import AccessModel, GlobalModel


def entrance_model(monkeypatch: Any, box: tuple[int, int, int, int], side: str) -> AccessModel:
    sx, sy, sr, st = box
    mx, my = (sx + sr) // 2, (sy + st) // 2
    entrance = {
        "WEST": ((sx, my - 1500), (sx, my + 1500)),
        "EAST": ((sr, my - 1500), (sr, my + 1500)),
        "SOUTH": ((mx - 1500, sy), (mx + 1500, sy)),
        "NORTH": ((mx - 1500, st), (mx + 1500, st)),
        "INTERNAL_VERTICAL": ((mx - 3000, my - 1500), (mx - 3000, my + 1500)),
        "INTERNAL_HORIZONTAL": ((mx - 1500, my - 3000), (mx + 1500, my - 3000)),
    }[side]
    requirement = dict(
        identity="synthetic:main_entrance->changing_room",
        from_ref="main_entrance",
        to_ref="changing_room",
        flow_kind="PEOPLE",
        profile_identity=PERSONNEL,
        direct_allowed=False,
        corridor_allowed=True,
        portal_required=True,
    )
    context = SimpleNamespace(
        sitebox=box,
        entrances={"main_entrance": entrance},
        obsboxes=(),
        binding=SimpleNamespace(access_requirements=[requirement]),
        pack_req={"identity": "not-this-personnel-requirement"},
        ledger=StageALedger(),
    )

    def isolated_room(self: Any, c: Any, handoff: Any) -> None:
        self.c, self.handoff = c, handoff
        self.m = cp_model.CpModel()
        self.rooms = {
            "changing_room": {
                k: self.m.new_int_var(v, v, "synthetic_changing_" + k)
                for k, v in dict(x=mx - 1000, y=my - 1000, X=mx + 1000, Y=my + 1000).items()
            }
        }
        self.interfaces = []

    monkeypatch.setattr(GlobalModel, "__init__", isolated_room)
    return AccessModel(context, SimpleNamespace(), True)


@pytest.mark.parametrize(
    "box", [(0, 0, 12000, 12000), (3000, 3000, 15000, 15000), (3000, 7000, 15000, 19000)]
)
@pytest.mark.parametrize(
    "side,normal", [("WEST", (1, 0)), ("EAST", (-1, 0)), ("SOUTH", (0, 1)), ("NORTH", (0, -1))]
)
def test_actual_endpoint_and_envelopes_enter_site(
    monkeypatch: Any, box: Any, side: str, normal: Any
) -> None:
    model = entrance_model(monkeypatch, box, side)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 3
    solver.parameters.cp_model_presolve = True
    solver.parameters.search_branching = cp_model.PARTIAL_FIXED_SEARCH
    solver.parameters.max_time_in_seconds = 1
    assert solver.solve(model.m) in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    route = model.routes[0]
    assert route["pw"] == 1500 and route["cw"] == 2000
    assert solver.boolean_value(route["corridor"])
    p, q = [tuple(solver.value(v) for v in point) for point in route["points"][:2]]
    assert tuple(b - a for a, b in zip(p, q, strict=True)) == tuple(v * 1000 for v in normal)
    sx, sy, sr, st = box
    for envelope in route["envelopes"]:
        x, y, X, Y = [solver.value(envelope[k]) for k in ("x", "y", "X", "Y")]
        assert sx <= x <= X <= sr and sy <= y <= Y <= st
    first_corner = route["envelopes"][5]
    if side == "SOUTH":
        assert p[1] == sy and q[1] == sy + 1000
        assert solver.value(first_corner["y"]) == sy
    elif side == "NORTH":
        assert p[1] == st and q[1] == st - 1000
        assert solver.value(first_corner["Y"]) == st


@pytest.mark.parametrize("side", ["INTERNAL_VERTICAL", "INTERNAL_HORIZONTAL"])
def test_internal_entrance_cannot_default_to_north(monkeypatch: Any, side: str) -> None:
    with pytest.raises(LayoutAuthorityError, match="ENTRANCE_BOUNDARY_REFERENCE_INVALID"):
        entrance_model(monkeypatch, (0, 0, 12000, 12000), side)


def test_complete_r3_alternatives_keep_original_engineering_acceptance() -> None:
    from cold_storage.modules.layout.application.global_composition_pool import _eligible
    from cold_storage.modules.layout.application.global_composition_solver import (
        validate_generated_global_proposal,
    )
    from cold_storage.modules.layout.domain.access_routing import (
        _edge_match_for_shared,
        _shared_edge_segment,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_area_efficiency import (
        area_efficiency_snapshot,
        compare_area_efficient_quality,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_balanced_quality import (
        compare_balanced_quality,
    )
    from cold_storage.modules.layout.infrastructure.stage_b_frontage_joint_search import (
        validated_area_proxy,
    )
    from tests.r9_full_engineering_synthetic import geometry, routes, sources

    snapshots = []
    for x in (40, 42):
        plan, p1, site, handoff, context, *_ = sources()
        zones = geometry(context, x)
        shared = _shared_edge_segment(
            zones["packaging_material_storage"], zones["sorting_packaging_room"]
        )
        assert _edge_match_for_shared(
            zones["packaging_material_storage"], zones["sorting_packaging_room"], shared
        ) == ("LONG_EDGE", "SHORT_EDGE")
        result = validate_generated_global_proposal(
            plan,
            p1.to_dict(),
            site,
            context,
            handoff,
            dict(
                solver_status="SYNTHETIC_GEOMETRY_NO_NATIVE",
                zones=[r.to_dict() for r in zones.values()],
                routes=routes(context, zones),
            ),
        )
        identities = {
            r["identity"] for r in context.binding.access_requirements if r["flow_kind"] != "TRUCK"
        }
        assert _eligible(result, identities)
        assert result["independent_validation"]["zone_count"] == 12
        assert result["independent_validation"]["must_pass_count"] == 7
        assert result["native_independent_validation"]["pass_count"] == 11
        snapshots.append(
            area_efficiency_snapshot(result, handoff.source_composition_hash, context.binding)
        )
    assert [validated_area_proxy(s) for s in snapshots] == [1225, 1225]
    assert [s["metrics"]["personnel_route_m"] for s in snapshots] == ["28", "26"]
    assert compare_balanced_quality(*snapshots)["status"] == "QUALITY_TRADEOFF"
    assert compare_area_efficient_quality(*snapshots)["status"] == "QUALITY_TRADEOFF"
