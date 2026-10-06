"""Exact finite-domain subtraction and diagnostic-only blocker releases."""

from __future__ import annotations

from cold_storage.modules.layout.domain.composition_placement import (
    _candidate_rejection,
    _exact_successor_free_space_domain,
    _primitive_diagnostic_hash,
    _rectangle,
    _Shape,
)
from tests.unit.test_v222_p1a_s4_cr3_forward_check import (
    _rectangle_from_bounds,
    _two_metre_square,
)
from tests.unit.test_v222_p1a_s4_cr3_forward_check import (
    context as context,
)


def _classify(context, origins, placed=None, obstacles=()):
    return _exact_successor_free_space_domain(
        "finished_goods_room",
        _Shape(500, 500, 0),
        origins,
        placed or {},
        _two_metre_square(),
        obstacles,
        context["handoff"],
        1,
    )


def test_free_space_domain_equals_unchanged_physical_predicates(context):
    placed = {
        "packaging_material_storage": _rectangle_from_bounds(
            "packaging_material_storage", (500, 500, 1000, 1000)
        )
    }
    origins = tuple((x, y) for x in (-1, 0, 500, 1000, 1500, 1501) for y in (0, 500, 1500))
    survivors, profile = _classify(context, origins, placed)
    expected = tuple(
        point
        for point in origins
        if _candidate_rejection(
            _rectangle("finished_goods_room", *point, _Shape(500, 500, 0)),
            placed,
            _two_metre_square(),
            (),
        )
        is None
    )
    assert survivors == expected
    assert sum(profile["exclusive_counts"].values()) == len(origins)
    assert profile["unclassified_count"] == 0
    assert profile["engineering_authority"] is False
    assert profile["validation_authority"] is False


def test_all_simultaneous_blockers_and_groups_are_attributed(context):
    obstacle = ((0, 0), (1000, 0), (1000, 1000), (0, 1000))
    placed = {
        name: _rectangle_from_bounds(name, (0, 0, 1000, 1000))
        for name in ("coating_room", "packaging_material_storage")
    }
    survivors, profile = _classify(context, ((-1, 0),), placed, (obstacle,))
    assert survivors == ()
    row = profile["candidates"][0]
    assert row["site_boundary_blocked"] is True
    assert len(row["obstacle_identities"]) == 1
    assert row["overlapping_room_roles"] == sorted(placed)
    assert row["overlapping_groups"] == ["PROCESSING_CORE_GROUP", "SUPPORT_GROUP"]
    assert row["exclusive_classification"] == "SITE"


def test_single_non_must_release_is_diagnostic_and_does_not_mutate(context):
    placed = {
        "packaging_material_storage": _rectangle_from_bounds(
            "packaging_material_storage", (0, 0, 500, 500)
        )
    }
    snapshot = dict(placed)
    survivors, profile = _classify(context, ((0, 0),), placed)
    assert survivors == ()
    release = profile["single_non_must_blocker_release"][0]
    assert release["released_role"] == "packaging_material_storage"
    assert release["restored_physical_domain_count"] == 1
    assert release["diagnostic_only"] is True
    assert release["geometry_mutated"] is False
    assert placed == snapshot


def test_must_blocker_cannot_be_counterfactually_released(context):
    placed = {"coating_room": _rectangle_from_bounds("coating_room", (0, 0, 500, 500))}
    _, profile = _classify(context, ((0, 0),), placed)
    assert profile["single_non_must_blocker_release"] == []


def test_releasing_one_of_two_blockers_does_not_restore_capacity(context):
    placed = {
        name: _rectangle_from_bounds(name, (0, 0, 500, 500))
        for name in ("changing_room", "packaging_material_storage")
    }
    _, profile = _classify(context, ((0, 0),), placed)
    assert all(
        row["restored_physical_domain_count"] == 0
        for row in profile["single_non_must_blocker_release"]
    )
    conflict = profile["successor_domain_conflict_set"]
    assert conflict["room_roles"] == sorted(placed)
    assert conflict["covers_all_physical_exclusions"] is True
    assert conflict["minimal_conflict_set_claimed"] is False
    assert conflict["global_infeasibility_proven"] is False


def test_closed_obstacle_touch_and_room_positive_overlap_are_unchanged(context):
    obstacle = ((500, 0), (1000, 0), (1000, 500), (500, 500))
    room = _rectangle_from_bounds("office", (500, 0, 1000, 500))
    room_free, _ = _classify(context, ((0, 0),), {"office": room})
    obstacle_free, _ = _classify(context, ((0, 0),), {}, (obstacle,))
    assert room_free == ((0, 0),)
    assert obstacle_free == ()


def test_full_classification_is_deterministic_and_has_no_recursive_budget(context):
    inputs = ((0, 0), (500, 500), (1501, 1501))
    first = _classify(context, inputs)
    assert first == _classify(context, inputs)
    assert first[1]["classified_count"] == len(inputs)
    assert first[1]["unclassified_count"] == 0


def test_nonrectangular_boundary_and_obstacle_use_exact_predicate_fallback(context):
    boundary = ((0, 0), (2000, 0), (2000, 1000), (1000, 1000), (1000, 2000), (0, 2000))
    obstacle = ((0, 500), (500, 0), (500, 500))
    origins = tuple((x, y) for x in (0, 499, 500, 1000, 1500) for y in (0, 500, 1000))
    shape = _Shape(500, 300, 90)
    survivors, profile = _exact_successor_free_space_domain(
        "finished_goods_room",
        shape,
        origins,
        {},
        boundary,
        (obstacle,),
        context["handoff"],
        1,
    )
    assert survivors == tuple(
        point
        for point in origins
        if _candidate_rejection(
            _rectangle("finished_goods_room", *point, shape),
            {},
            boundary,
            (obstacle,),
        )
        is None
    )
    assert profile["nonrectangular_polygon_predicate_fallback_count"] == len(origins) * 2


def test_seven_cr6_profiles_close_all_127_previously_unexpanded_candidates():
    # Historical geometry is a diagnostic fixture only. The production
    # search entry point never loads this evidence or these partials.
    from scripts.capture_s4_cr7_evidence import baseline_profiles

    result = baseline_profiles()
    assert result["historical_coating_profile_count"] == 7
    assert result["runtime_seed_used"] is False
    assert result["previously_unexpanded_count"] == 127
    assert result["previously_unexpanded_classifications"] == {
        "SITE": 84,
        "OBSTACLE": 36,
        "OVERLAP": 7,
    }
    for profile in result["profiles"]:
        for shape in profile["shape_profiles"]:
            assert shape["unclassified_count"] == 0
            assert shape["free_space_count"] == 0
            assert shape["finite_domain_count"] == sum(shape["exclusive_counts"].values())
            assert all(
                row["restored_physical_domain_count"] == 0
                for row in shape["single_non_must_blocker_release"]
            )


def test_primitive_diagnostic_digest_preserves_existing_canonical_hash(context):
    from cold_storage.modules.layout.domain.dimensioning import canonical_hash

    records = [("coating_room", (1, -2, 3, 4), "POSSIBLY_COMPATIBLE", "中文", 7)]
    assert _primitive_diagnostic_hash(records) == canonical_hash(records)
    _, profile = _classify(context, ((0, 0), (1501, 1501)))
    assert _primitive_diagnostic_hash(profile) == canonical_hash(profile)
