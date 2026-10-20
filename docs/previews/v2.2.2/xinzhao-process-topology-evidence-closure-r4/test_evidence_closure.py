"""Small synthetic correctness tests only; project geometry stays private."""

from __future__ import annotations

from typing import Any

import pytest

from offline_evidence_closure import (
    frozen,
    ring_relationships,
    source_extension,
    symbol_alignment,
)


def ring(x: int, y: int, w: int, h: int) -> list[Any]:
    core, _ = frozen().dependencies()
    points = [core.point(p) for p in [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]
    return list(zip(points, points[1:] + points[:1], strict=True))


def test_strict_containment_does_not_approve_column_or_deduct_area() -> None:
    result = ring_relationships(
        ring(0, 0, 100, 100), [ring(10, 10, 5, 5), ring(30, 10, 5, 5)]
    )
    assert result["strict_ring_relationships_valid"]
    assert result["outer_reference_area_pdf_points_squared"] == "10000"
    assert result["internal_occupancy_area"] is None
    assert result["reference_area_excluding_confirmed_voids"] is None
    assert result["finished_clear_area"] is None
    assert result["approved_net_area"] is None


@pytest.mark.parametrize(
    "second",
    [ring(14, 10, 5, 5), ring(10, 10, 5, 5), ring(11, 11, 1, 1), ring(15, 10, 5, 5)],
)
def test_overlapping_nested_duplicate_touching_inners_rejected(
    second: list[Any],
) -> None:
    assert not ring_relationships(ring(0, 0, 100, 100), [ring(10, 10, 5, 5), second])[
        "strict_ring_relationships_valid"
    ]


@pytest.mark.parametrize(
    "inner", [ring(0, 10, 5, 5), ring(-1, 10, 5, 5), ring(110, 10, 5, 5)]
)
def test_touching_crossing_outside_outer_blocked(inner: list[Any]) -> None:
    assert not ring_relationships(ring(0, 0, 100, 100), [inner])[
        "strict_ring_relationships_valid"
    ]


def test_open_outer_not_complete() -> None:
    with pytest.raises(ValueError, match="CLOSED_VALID"):
        ring_relationships(ring(0, 0, 100, 100)[:-1], [])


def test_original_u_jamb_not_straight_bridge_and_not_exterior_authority() -> None:
    core, _ = frozen().dependencies()
    edges = ring(0, 0, 10, 10)
    base = (
        edges[:1]
        + [
            (core.point((10, 0)), core.point((10, 4))),
            (core.point((10, 6)), core.point((10, 10))),
        ]
        + edges[2:]
    )
    page = {
        "rotation_matrix": [1, 0, 0, 1, 0, 0],
        "vectors": [
            {
                "items": [
                    ["l", [10, 4], [9, 4]],
                    ["l", [9, 4], [9, 6]],
                    ["l", [9, 6], [10, 6]],
                ]
            }
        ],
    }
    refs = [
        {
            "path_id": 0,
            "item_id": i,
            "kind": "PARTITION_INTERFACE_ENDPOINT",
            "review_basis": "SYNTHETIC_SOURCE",
        }
        for i in range(3)
    ]
    result = source_extension(page, base, refs)
    assert not result["before"]["closed"] and result["after"]["closed"]
    assert result["after"]["exact_area_pdf_points_squared"] == "98"
    assert not result["engineering_approved"]
    with pytest.raises(ValueError, match="EXPLICIT_SOURCE_REVIEW"):
        source_extension(page, base, [])


def test_unknown_gap_does_not_get_bridged() -> None:
    core, _ = frozen().dependencies()
    page = {
        "rotation_matrix": [1, 0, 0, 1, 0, 0],
        "vectors": [{"items": [["l", [0, 0], [0, 5]]]}],
    }
    value = source_extension(
        page,
        ring(0, 0, 10, 10)[:-1],
        [{"path_id": 0, "item_id": 0, "review_basis": "SYNTHETIC"}],
    )
    assert not value["after"]["closed"]
    assert core.point((0, 10)) in [
        core.point(p) for p in value["after"]["unbound_endpoints"]
    ]


@pytest.mark.parametrize(
    "points, expected",
    [
        ([(2, 1), (8, 1)], True),
        ([(20, 1), (30, 1)], False),
        ([(2, 80), (8, 80)], False),
    ],
)
def test_symbol_exists_is_not_spatial_identity(
    points: list[Any], expected: bool
) -> None:
    result = symbol_alignment([(0, 0), (10, 0)], points, [-1, -2, 11, 2])
    assert (
        result["door_symbol_spatial_binding"].startswith("SPATIALLY_COMPATIBLE")
        == expected
    )
    assert result["verified_clear_width_mm"] is None
    assert not result["route_validated"] and not result["engineering_approved"]


def test_reference_checks_are_deterministic() -> None:
    core, _ = frozen().dependencies()
    assert core.encode(
        ring_relationships(ring(0, 0, 100, 100), [ring(1, 1, 2, 2)])
    ) == core.encode(ring_relationships(ring(0, 0, 100, 100), [ring(1, 1, 2, 2)]))
