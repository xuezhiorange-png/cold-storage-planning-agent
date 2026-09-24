"""P1A structural group/band/zone authority and exact-family facts."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cold_storage.modules.layout.domain import placement as placement_domain
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.placement import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    FUNCTIONAL_GROUPS,
    LINEAR_PROCESS_BAND,
    MAIN_PROCESS_ZONE_CODES,
    STRUCTURAL_ANCHOR_REFERENCES,
    StructuralCompositionFamilyV1,
    bind_functional_groups,
    composition_family_candidates,
    functional_group_for_zone,
    select_structural_composition_family,
    structural_anchor_references,
)
from cold_storage.modules.layout.domain.structural_quality import (
    StructuralQualityFactsV1,
    structural_candidate_is_better,
)


def _site_geometry(width: int = 80, depth: int = 50) -> dict[str, object]:
    return {
        "site": {
            "effective_buildable_boundary": {
                "type": "polygon",
                "points": [
                    {"x": 0, "y": 0},
                    {"x": width, "y": 0},
                    {"x": width, "y": depth},
                    {"x": 0, "y": depth},
                ],
            }
        }
    }


def test_existing_zones_bind_once_to_frozen_semantic_groups() -> None:
    zone_codes = tuple(code for members in FUNCTIONAL_GROUPS.values() for code in members)
    groups = bind_functional_groups(zone_codes)

    assert len(groups) == 12
    assert len(set(groups.values())) == 5
    assert groups["raw_fruit_buffer"] == "RAW_SIDE_GROUP"
    assert groups["primary_precooling_room"] == "RAW_SIDE_GROUP"
    assert groups["sorting_packaging_room"] == "PROCESSING_CORE_GROUP"
    assert groups["coating_room"] == "PROCESSING_CORE_GROUP"
    assert groups["secondary_precooling_room"] == "FINISHED_SIDE_GROUP"
    assert groups["finished_goods_room"] == "FINISHED_SIDE_GROUP"
    assert groups["packaging_material_storage"] == "SUPPORT_GROUP"
    assert groups["office"] == "PERSONNEL_GROUP"
    assert "raw_receiving" not in groups


def test_unknown_zone_role_fails_closed_without_inventing_receiving() -> None:
    with pytest.raises(LayoutAuthorityError) as caught:
        functional_group_for_zone("raw_receiving")
    assert caught.value.code == "STRUCTURAL_ZONE_GROUP_UNMAPPED"


def test_composition_families_and_axis_order_are_deterministic() -> None:
    site = _site_geometry()
    first = composition_family_candidates(site)
    second = composition_family_candidates(site)

    assert [family.to_dict() for family in first] == [family.to_dict() for family in second]
    assert [(family.family, family.dominant_direction) for family in first] == [
        (LINEAR_PROCESS_BAND, "POSITIVE"),
        (LINEAR_PROCESS_BAND, "NEGATIVE"),
        (CENTRAL_PROCESS_HUB, "UNRESOLVED"),
    ]
    assert all(family.dominant_axis == "X" for family in first)


def test_family_selection_uses_area_authority_not_golden_template() -> None:
    central = {
        code: {"required_area_m2": 100 if code == "sorting_packaging_room" else 50}
        for code in MAIN_PROCESS_ZONE_CODES
    }
    linear = {
        code: {"required_area_m2": 100 if code == "finished_goods_room" else 50}
        for code in MAIN_PROCESS_ZONE_CODES
    }

    assert select_structural_composition_family(_site_geometry(), central).family == (
        CENTRAL_PROCESS_HUB
    )
    assert select_structural_composition_family(_site_geometry(), linear).family == (
        LINEAR_PROCESS_BAND
    )


def test_linear_family_requires_exact_shared_edge_and_direction() -> None:
    family_positive = StructuralCompositionFamilyV1(
        LINEAR_PROCESS_BAND, "X", "POSITIVE", "UNIT_TEST"
    )
    family_negative = StructuralCompositionFamilyV1(
        LINEAR_PROCESS_BAND, "X", "NEGATIVE", "UNIT_TEST"
    )
    predecessor = PlacedRectangleV1("raw_fruit_buffer", 0, 0, Decimal("10"), Decimal("5"))
    positive = PlacedRectangleV1("primary_precooling_room", 10, 0, Decimal("8"), Decimal("5"))
    negative = PlacedRectangleV1("primary_precooling_room", -8, 0, Decimal("8"), Decimal("5"))
    diagonal = PlacedRectangleV1("primary_precooling_room", 10, 5, Decimal("8"), Decimal("5"))

    assert placement_domain._linear_flow_anchor_matches(positive, predecessor, family_positive)
    assert placement_domain._linear_flow_anchor_matches(negative, predecessor, family_negative)
    assert not placement_domain._linear_flow_anchor_matches(negative, predecessor, family_positive)
    assert not placement_domain._linear_flow_anchor_matches(diagonal, predecessor, family_positive)


def test_support_branch_is_grouped_and_personnel_stays_outside_process_rank() -> None:
    assert STRUCTURAL_ANCHOR_REFERENCES["secondary_fruit_buffer"] == ("packaging_material_storage",)
    assert STRUCTURAL_ANCHOR_REFERENCES["frozen_fruit_room"] == (
        "packaging_material_storage",
        "secondary_fruit_buffer",
    )
    assert structural_anchor_references(
        "frozen_fruit_room",
        ("packaging_material_storage", "secondary_fruit_buffer"),
    ) == ("packaging_material_storage", "secondary_fruit_buffer")
    assert "office" not in MAIN_PROCESS_ZONE_CODES
    assert "changing_room" not in MAIN_PROCESS_ZONE_CODES
    assert MAIN_PROCESS_ZONE_CODES == (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )


def test_structural_quality_comparison_is_lexicographic_and_unweighted() -> None:
    best = StructuralQualityFactsV1('{"atomic":"a"}', (1, 0, 4))
    lower = StructuralQualityFactsV1('{"atomic":"b"}', (1, 0, 3))
    tie = StructuralQualityFactsV1('{"atomic":"c"}', (1, 0, 4))

    assert structural_candidate_is_better(best, lower)
    assert not structural_candidate_is_better(lower, best)
    assert not structural_candidate_is_better(tie, best)
