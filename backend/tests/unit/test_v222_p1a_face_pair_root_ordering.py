from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from cold_storage.modules.layout.domain import placement
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def test_face_pair_root_ordering_prioritizes_authoritative_projection_room(
    monkeypatch,
) -> None:
    context = SimpleNamespace(boundary_bounds=(0, 0, 100_000, 100_000))
    roots = (
        PlacedRectangleV1(
            "sorting_packaging_room", Decimal(20), Decimal(0), Decimal(10), Decimal(40)
        ),
        PlacedRectangleV1(
            "sorting_packaging_room", Decimal(20), Decimal(20), Decimal(10), Decimal(40)
        ),
    )
    monkeypatch.setattr(
        placement,
        "_minimum_authoritative_axis_extent",
        lambda _context, _zone_code, _axis: 10_000,
    )
    monkeypatch.setattr(placement, "_topology_root_ordering_penalty", lambda _context, _row: 0)

    ordered = placement._sorting_roots_for_attachment_pair(context, roots, "SOUTH", "NORTH")

    assert ordered[0] == roots[1]
