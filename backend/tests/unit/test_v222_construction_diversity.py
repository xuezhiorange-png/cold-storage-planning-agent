"""Synthetic geometric organization tests; none are engineering candidates."""

from __future__ import annotations

from copy import deepcopy

import pytest

from cold_storage.modules.layout.domain.adjacency import PROCESS_FLOW, ZONE_CODES
from cold_storage.modules.layout.domain.construction_diversity import construction_diversity
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError


def rooms(path: str = "EEEEEE") -> list[dict]:
    """Unit squares on a grid; intentionally NOT the project dimension authority."""
    x = y = 0
    positions = {}
    for role, direction in zip(PROCESS_FLOW, "E" + path, strict=True):
        if positions:
            dx, dy = {"E": (1, 0), "N": (0, 1), "W": (-1, 0), "S": (0, -1)}[direction]
            x, y = x + dx, y + dy
        positions[role] = (x, y)
    return [
        dict(
            zone_code=r,
            x=positions.get(r, (i, -5))[0],
            y=positions.get(r, (i, -5))[1],
            width_m=1,
            depth_m=1,
            rotation_deg=0,
        )
        for i, r in enumerate(ZONE_CODES)
    ]


def test_input_order_translation_and_all_square_symmetries_do_not_count() -> None:
    original = rooms("EENNEE")
    original[0].update(width_m=2, depth_m=3)
    expected = construction_diversity(original)
    for swap in (False, True):
        for sx in (-1, 1):
            for sy in (-1, 1):
                rows = deepcopy(original)
                for r in rows:
                    x, y = (r["y"], r["x"]) if swap else (r["x"], r["y"])
                    w, d = (r["depth_m"], r["width_m"]) if swap else (r["width_m"], r["depth_m"])
                    r["x"], r["y"] = (
                        sx * x - (w if sx < 0 else 0) + 23,
                        sy * y - (d if sy < 0 else 0) - 17,
                    )
                    r["width_m"], r["depth_m"] = w, d
                assert construction_diversity(rows[::-1]) == expected


def test_support_swap_and_millimetre_shift_cannot_earn_organization_coverage() -> None:
    original = rooms()
    changed = deepcopy(original)
    changed[0]["x"], changed[1]["x"] = changed[1]["x"], changed[0]["x"]
    changed[0]["x"] += 0.001
    a, b = construction_diversity(original), construction_diversity(changed)
    assert a["symmetry_invariant_geometry_hash"] != b["symmetry_invariant_geometry_hash"]
    assert a["major_organization_hash"] == b["major_organization_hash"]


def test_three_actual_process_organizations_not_three_labels() -> None:
    rows = [construction_diversity(rooms(p)) for p in ("EEEEEE", "EEENNN", "EENNWW")]
    assert len({r["major_organization_hash"] for r in rows}) == 3
    assert len({r["major_family_hash"] for r in rows}) == 3
    assert rows[0]["canonical_attachment_directions"] != rows[1]["canonical_attachment_directions"]


def test_moving_a_turn_along_same_l_bands_does_not_create_a_major_family() -> None:
    a, b = (construction_diversity(rooms(p)) for p in ("EEENNN", "EEEENN"))
    assert a["major_organization_hash"] != b["major_organization_hash"]
    assert a["major_family_hash"] == b["major_family_hash"]
    assert a["canonical_major_band_directions"] == b["canonical_major_band_directions"]


def test_same_physical_rectangle_with_nominal_rotation_is_same_geometry() -> None:
    a = rooms()
    a[0]["width_m"], a[0]["depth_m"] = 2, 3
    b = deepcopy(a)
    b[0].update(width_m=3, depth_m=2, rotation_deg=90)
    assert construction_diversity(a) == construction_diversity(b)


@pytest.mark.parametrize("bad", ["duplicate", "missing", "precision", "nan", "negative", "must"])
def test_malformed_geometry_and_missing_main_must_fail_closed(bad: str) -> None:
    rows = rooms()
    if bad == "duplicate":
        rows.append(rows[0])
    elif bad == "missing":
        rows.pop()
    elif bad == "precision":
        rows[0]["x"] = ".0001"
    elif bad == "nan":
        rows[0]["x"] = "NaN"
    elif bad == "negative":
        rows[0]["width_m"] = -1
    else:
        next(r for r in rows if r["zone_code"] == PROCESS_FLOW[0])["x"] = 55
    with pytest.raises(LayoutAuthorityError):
        construction_diversity(rows)
