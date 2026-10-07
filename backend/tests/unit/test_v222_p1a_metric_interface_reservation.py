"""Pairwise metric reservation safety and server-owned boundary regressions."""

from __future__ import annotations

import inspect
from dataclasses import asdict, replace
from itertools import product
from typing import Any

import pytest

from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.metric_interface_reservation import (
    realize_metric_interface_reservations,
)
from cold_storage.modules.layout.application.site_geometry import (
    validate_rectangle_against_site,
    validate_site_geometry,
)
from cold_storage.modules.layout.domain.authority_shapes import AuthoritativeZoneShapeV1 as Shape
from cold_storage.modules.layout.domain.authority_shapes import (
    authoritative_zone_shapes,
    canonical_construction_shapes,
)
from cold_storage.modules.layout.domain.composition_placement import (
    _authority_shapes,
    _canonical_construction_shapes,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    MetricReservationStatusV1,
    aggregate_metric_gate,
    evaluate_pair_domain,
    event_origins,
    face_origins,
    finite_pairs,
    pair_status,
    physical_status,
    realize_interface,
    rectangle_at,
    verify_metric_replay,
)
from cold_storage.modules.layout.domain.site_geometry import (
    normalize_polygon,
    validate_flexible_candidate,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _all_keys, _context, _result

BOUNDARY = ((0, 0), (10000, 0), (10000, 10000), (0, 10000))
SHAPES = ((Shape(2000, 1000, 0), Shape(2000, 1000, 90)), (Shape(1000, 1000, 0),))


def _domain(boundary: Any = BOUNDARY, obstacles: Any = (), cap: int = 100000) -> Any:
    return evaluate_pair_domain(
        ("office", "shipping_channel"), SHAPES, boundary, obstacles, evaluation_cap=cap
    )


def test_fixed_dimension_metric_slot_and_exact_predicates() -> None:
    result = _domain()
    assert result.complete and result.valid_count > 0
    for a, b, sa, sb in result.witnesses:
        assert sa in SHAPES[0] and sb in SHAPES[1]
        assert pair_status(a, b, BOUNDARY, ()) == "VALID"


def test_effective_buildable_boundary() -> None:
    smaller = ((0, 0), (3000, 0), (3000, 3000), (0, 3000))
    a = rectangle_at("office", (2500, 0), SHAPES[0][0])
    assert physical_status(a, BOUNDARY, ()) == "VALID"
    assert physical_status(a, smaller, ()) == "SITE"


@pytest.mark.parametrize("kind", ["NO_BUILD_ZONE", "RETAINED_EXISTING_BUILDING"])
def test_hard_obstacle_and_site_validation_parity(kind: str) -> None:
    z, p, g = _context()
    body = g.to_dict()
    obstacle = {
        "id": "test-hard",
        "kind": kind,
        "hard": True,
        "footprint": body["site"]["effective_buildable_boundary"],
    }
    # Validated-site authority parsing is covered below; this fixture tests the
    # identical single-rectangle predicates including each hard-obstacle kind.
    obstacles = (normalize_polygon(obstacle["footprint"], allow_numeric_string=True),)
    boundary = obstacles[0]
    a = rectangle_at("office", (1000, 1000), SHAPES[0][0])
    assert physical_status(a, boundary, obstacles) == "HARD_OBSTACLE"
    assert _domain(BOUNDARY, (BOUNDARY,)).valid_count == 0
    for x, y in ((0, 0), (20000, 20000), (-1000, 0)):
        rect = rectangle_at("office", (x, y), SHAPES[0][0])
        canonical_obstacles = tuple(
            normalize_polygon(o["footprint"], allow_numeric_string=True)
            for o in body["obstacles"]["hard_obstacles"]
        )
        status = physical_status(rect, boundary, canonical_obstacles)
        try:
            validate_rectangle_against_site(rect, g)
        except Exception:
            assert status != "VALID"
        else:
            assert status == "VALID"


def test_corner_touch_and_positive_area_overlap_not_slots() -> None:
    a = rectangle_at("a", (0, 0), Shape(1000, 1000, 0))
    assert (
        pair_status(a, rectangle_at("b", (1000, 1000), Shape(1000, 1000, 0)), BOUNDARY, ())
        == "NO_POSITIVE_SHARED_EDGE"
    )
    assert (
        pair_status(a, rectangle_at("b", (500, 0), Shape(1000, 1000, 0)), BOUNDARY, ())
        == "PAIR_OVERLAP"
    )
    assert (
        pair_status(a, rectangle_at("b", (1000, 999), Shape(1000, 1000, 0)), BOUNDARY, ())
        == "VALID"
    )


def test_symmetric_endpoint_generation_and_determinism() -> None:
    a = _domain()
    b = evaluate_pair_domain(("shipping_channel", "office"), (SHAPES[1], SHAPES[0]), BOUNDARY, ())
    assert a == b == _domain()


@pytest.mark.parametrize(
    "obstacles", [(), (((4000, 4000), (5000, 4000), (5000, 5000), (4000, 5000)),)]
)
def test_metric_domain_no_false_exclusion_exhaustive_declared_domain(obstacles: Any) -> None:
    # Independent brute-force Cartesian expansion of the published event policy.
    expected = set()
    for first in (0, 1):
        for sa, sb in product(SHAPES[first], SHAPES[1 - first]):
            aw, ah = sa.world_width_mm, sa.world_depth_mm
            origins = {(x - dx, y - dy) for x, y in BOUNDARY for dx in (0, aw) for dy in (0, ah)}
            origins |= {
                (x - dx + gx, y - dy + gy)
                for o in obstacles
                for x, y in o
                for dx in (0, aw)
                for dy in (0, ah)
                for gx, gy in product((-1, 1), repeat=2)
            }
            assert origins == set(event_origins(sa, BOUNDARY, obstacles))
            for origin in sorted(origins):
                a = rectangle_at(str(first), origin, sa)
                left, bottom, right, top = a.bounds_mm
                bw, bh = sb.world_width_mm, sb.world_depth_mm
                other_origins = {
                    (x, y)
                    for x in (left - bw, right)
                    for y in (bottom, top - bh, (bottom + top - bh) // 2)
                }
                other_origins |= {
                    (x, y)
                    for y in (bottom - bh, top)
                    for x in (left, right - bw, (left + right - bw) // 2)
                }
                assert other_origins == set(face_origins(a, sb))
                for other in sorted(other_origins):
                    b = rectangle_at(str(1 - first), other, sb)
                    if pair_status(a, b, BOUNDARY, obstacles) == "VALID":
                        expected.add(
                            (a.bounds_mm, b.bounds_mm) if first == 0 else (b.bounds_mm, a.bounds_mm)
                        )
    pairs = list(finite_pairs(("office", "shipping_channel"), SHAPES, BOUNDARY, obstacles))
    keys = [(a.bounds_mm, b.bounds_mm) for a, b, _, _ in pairs]
    actual = {
        (a.bounds_mm, b.bounds_mm)
        for a, b, _, _ in pairs
        if pair_status(a, b, BOUNDARY, obstacles) == "VALID"
    }
    assert len(keys) == len(set(keys))
    assert actual == expected
    assert _domain(obstacles=obstacles).valid_count == len(expected)


def test_exhaustive_negative_and_incomplete_is_unknown() -> None:
    tiny = ((0, 0), (100, 0), (100, 100), (0, 100))
    result = _domain(tiny)
    reservation = _result().placement_handoffs[0].mandatory_interface_reservations[-1]

    def realize(domain: Any) -> Any:
        return realize_interface(
            reservation,
            domain,
            site_hash="site",
            dimension_identity="dimensions",
            shape_counts=(2, 1),
            construction_counts=(2, 1),
        )

    assert realize(result).status == MetricReservationStatusV1.EMPTY
    incomplete = realize(_domain(cap=1))
    assert incomplete.status == MetricReservationStatusV1.UNKNOWN
    assert aggregate_metric_gate((incomplete,)).status == "UNKNOWN_METRIC_RESERVATION_CAPACITY"


def test_shape_domain_parity_and_flexible_authority_reuse() -> None:
    z, p, g = _context()
    binding = bind_layout_authority(z, p, g)
    body = g.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(
        normalize_polygon(o["footprint"], allow_numeric_string=True)
        for o in body["obstacles"]["hard_obstacles"]
    )
    shapes = authoritative_zone_shapes(binding.dimension_authorities, boundary, obstacles)
    assert _authority_shapes is authoritative_zone_shapes
    assert _canonical_construction_shapes is canonical_construction_shapes
    for role, variants in shapes.items():
        canonical = canonical_construction_shapes(variants)
        assert {(s.world_width_mm, s.world_depth_mm) for s in variants} == {
            (s.world_width_mm, s.world_depth_mm) for s in canonical
        }
        assert all(
            s.rotation_deg in binding.dimension_authorities[role]["rotation_allowed"]
            for s in variants
        )
        if binding.dimension_authorities[role]["dimension_mode"] == "FLEXIBLE_RECTANGLE":
            for shape in variants:
                from cold_storage.modules.layout.domain.authority_shapes import _m

                validate_flexible_candidate(
                    binding.dimension_authorities[role], _m(shape.width_mm), _m(shape.depth_mm)
                )


def test_provenance_and_non_authority_boundary() -> None:
    assert tuple(inspect.signature(realize_metric_interface_reservations).parameters) == (
        "canonical_zone_plan",
        "p1_handoff",
        "site_geometry",
    )
    reservation = _result().placement_handoffs[0].mandatory_interface_reservations[-1]
    item = realize_interface(
        reservation,
        _domain(),
        site_hash="site",
        dimension_identity="dimensions",
        shape_counts=(2, 1),
        construction_counts=(2, 1),
    )
    for changed in (
        replace(
            item,
            source_edge_identity="extra",
            representative_slots=tuple(
                replace(s, source_edge_identity="extra") for s in item.representative_slots
            ),
        ),
        replace(item, source_structural_reservation_identity="forged"),
        replace(
            item,
            representative_slots=tuple(
                replace(s, source_site_geometry_hash="wrong") for s in item.representative_slots
            ),
        ),
        replace(
            item,
            representative_slots=tuple(
                replace(s, source_dimension_authority_identity="wrong")
                for s in item.representative_slots
            ),
        ),
    ):
        with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
            verify_metric_replay(changed, item)
    with pytest.raises(TypeError):
        realize_metric_interface_reservations(*_context(), metric_reservation=item)  # type: ignore[call-arg]


def test_p0_p1_coordinate_free_regression() -> None:
    before = _result()
    for p, h in zip(before.compositions, before.placement_handoffs, strict=True):
        forbidden = {"x", "y", "bounds", "rectangle", "coordinates", "world_width", "world_depth"}
        assert not forbidden & _all_keys(asdict(h))
        assert len(h.mandatory_hard_interfaces) == len(h.mandatory_interface_reservations) == 7
        assert canonical_hash(p.to_dict()) == h.source_composition_hash


def test_conditional_removal_authority_regression() -> None:
    # Application consumes only hard_obstacles; conditional removal is never
    # promoted by shape parsing or metric event generation.
    source = inspect.getsource(realize_metric_interface_reservations)
    assert '["hard_obstacles"]' in source
    assert "no_build_zones" not in source and "conditional_removal" not in source


@pytest.mark.parametrize("retained", [False, True])
def test_real_validated_retained_and_conditional_building_authority(retained: bool) -> None:
    import json
    from copy import deepcopy

    from tests.unit.test_v222_p1a_composition_authority_handoff import FIXTURE

    z, p, _ = _context()
    project = deepcopy(json.loads(FIXTURE.read_text()))
    project = {k: project[k] for k in ("site_constraints", "truck_access")}
    project["site_constraints"]["existing_buildings"] = [
        {
            "id": "retained-fixture",
            "name": "Fixture building",
            "retained": retained,
            "footprint": {
                "type": "polygon",
                "points": [
                    {"x": 20, "y": 20},
                    {"x": 23, "y": 20},
                    {"x": 23, "y": 23},
                    {"x": 20, "y": 23},
                ],
            },
        }
    ]
    g = validate_site_geometry(project, z, p1_handoff=p)
    body = g.to_dict()
    hard = body["obstacles"]["hard_obstacles"]
    assert any(o["kind"] == "RETAINED_EXISTING_BUILDING" for o in hard) == retained
    assert len(body["obstacles"]["conditional_removal_footprints"]) == (0 if retained else 1)
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = tuple(normalize_polygon(o["footprint"], allow_numeric_string=True) for o in hard)
    rect = rectangle_at("office", (20500, 20500), Shape(1000, 1000, 0))
    assert physical_status(rect, boundary, obstacles) == ("HARD_OBSTACLE" if retained else "VALID")
    if retained:
        with pytest.raises(LayoutAuthorityError):
            validate_rectangle_against_site(rect, g)
    else:
        assert validate_rectangle_against_site(rect, g)["hard_constraints_passed"]


def test_all_authority_edges_realized_and_extra_edge_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cold_storage.modules.layout.application import metric_interface_reservation as app
    from cold_storage.modules.layout.domain.adjacency import process_graph

    def bounded(roles: Any, shapes: Any, boundary: Any, obstacles: Any) -> Any:
        return evaluate_pair_domain(roles, shapes, boundary, obstacles, evaluation_cap=0)

    monkeypatch.setattr(app, "evaluate_pair_domain", bounded)
    results = app.realize_metric_interface_reservations(*_context())
    expected = {frozenset(e) for e in process_graph().must_adjacencies}
    assert len(results) == 6 and sum(len(r.reservations) for r in results) == 42
    for result in results:
        assert {
            frozenset((i.endpoint_a_role, i.endpoint_b_role)) for i in result.reservations
        } == expected
        assert result.gate.status == "UNKNOWN_METRIC_RESERVATION_CAPACITY"
        with pytest.raises(ValueError, match="COVERAGE_MISMATCH"):
            replace(result, reservations=result.reservations[:-1])
    reservation = _result().placement_handoffs[0].mandatory_interface_reservations[-1]
    with pytest.raises(ValueError, match="NON_AUTHORITY"):
        realize_interface(
            replace(reservation, endpoint_b_role="raw_fruit_buffer"),
            _domain(),
            site_hash="site",
            dimension_identity="dimensions",
            shape_counts=(2, 1),
            construction_counts=(2, 1),
        )
