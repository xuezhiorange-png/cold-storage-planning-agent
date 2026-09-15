"""P2B2 owner-approved objective metadata, without placement or route solving."""

from __future__ import annotations

from dataclasses import replace

import pytest

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.objective_profile import (
    ACTUAL_ROUTE_LENGTH_METRIC,
    CARDINAL_LOADING_SIDE_DIRECTION,
    CARDINAL_LOADING_SIDE_METRIC,
    CIRCULATION_LENGTH,
    COMPACTNESS,
    DEFERRED,
    DISABLED,
    FINAL_TIE_BREAK,
    IDENTITY,
    LOADING_SIDE_PREFERENCE,
    MATERIAL_FLOW_DISTANCE,
    NEAREST_TRUCK_ENTRANCE_DIRECTION,
    NEAREST_TRUCK_ENTRANCE_METRIC,
    OBJECTIVE_ORDER,
    PEOPLE_TRUCK_SEPARATION,
    PLACEMENT_STAGE,
    ROUTE_DISTANCE_DIRECTION,
    ROUTE_DISTANCE_UNIT,
    ROUTE_STAGE,
    SHAPE_REGULARITY,
    SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT,
    SHOULD_ADJACENT,
    SHOULD_ADJACENT_COUNT,
    SHOULD_ADJACENT_METRIC,
    SHOULD_ADJACENT_METRIC_ID,
    SOFT_OBJECTIVE_COUNT,
    UNUSED_SITE_EFFICIENCY,
    approved_objective_profile,
    validate_objective_profile,
)


def test_profile_freezes_owner_aggregation_and_complete_objective_vocabulary() -> None:
    profile = approved_objective_profile()

    assert profile.identity == IDENTITY == "site-constrained-objective-profile@1.0.0"
    assert profile.schema_version == "1.0.0"
    assert profile.aggregation == "LEXICOGRAPHIC"
    assert profile.weighted_score is False
    assert profile.priority_order == OBJECTIVE_ORDER
    assert len(profile.objective_rules) == SOFT_OBJECTIVE_COUNT == 8
    assert tuple(rule.objective_id for rule in profile.objective_rules) == OBJECTIVE_ORDER
    assert profile.hard_constraints_first is True
    assert profile.hard_violation_cannot_be_offset is True


def test_should_adjacency_is_an_equal_count_and_excludes_truck_proximity() -> None:
    profile = approved_objective_profile()
    rule = next(rule for rule in profile.objective_rules if rule.objective_id == SHOULD_ADJACENT)

    assert rule.stage == PLACEMENT_STAGE
    assert rule.status == "ACTIVE"
    assert SHOULD_ADJACENT_METRIC == "SATISFIED_COUNT"
    assert rule.metric == SHOULD_ADJACENT_METRIC_ID == "SATISFIED_SHOULD_ADJACENCY_COUNT"
    assert rule.unit == "COUNT"
    assert rule.direction == "MAXIMIZE"
    assert rule.proxy_allowed is False
    assert SHOULD_ADJACENT_COUNT == 5
    assert SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT is False


def test_route_objectives_require_actual_portal_corridor_routes() -> None:
    profile = approved_objective_profile()
    rules = {rule.objective_id: rule for rule in profile.objective_rules}

    for objective_id in (MATERIAL_FLOW_DISTANCE, CIRCULATION_LENGTH):
        rule = rules[objective_id]
        assert rule.stage == ROUTE_STAGE
        assert rule.status == DEFERRED
        assert rule.metric == ACTUAL_ROUTE_LENGTH_METRIC
        assert rule.unit == ROUTE_DISTANCE_UNIT == "m"
        assert rule.direction == ROUTE_DISTANCE_DIRECTION == "MINIMIZE"
        assert rule.proxy_allowed is False
        assert "portal_geometry" in rule.required_inputs
        assert "corridor_geometry" in rule.required_inputs

    separation = rules[PEOPLE_TRUCK_SEPARATION]
    assert separation.stage == ROUTE_STAGE
    assert separation.status == DEFERRED
    assert separation.owner_metric_required is True
    assert separation.metric is None


def test_loading_side_has_only_owner_declared_conditional_metrics() -> None:
    profile = approved_objective_profile()
    rule = next(
        rule for rule in profile.objective_rules if rule.objective_id == LOADING_SIDE_PREFERENCE
    )

    assert rule.status == "CONDITIONAL"
    assert rule.metric == "BINARY_MATCH_OR_MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE"
    assert rule.proxy_allowed is False
    body = profile.to_dict()["loading_side"]
    assert body == {
        "cardinal_metric": CARDINAL_LOADING_SIDE_METRIC,
        "cardinal_direction": CARDINAL_LOADING_SIDE_DIRECTION,
        "nearest_truck_entrance_metric": NEAREST_TRUCK_ENTRANCE_METRIC,
        "nearest_truck_entrance_direction": NEAREST_TRUCK_ENTRANCE_DIRECTION,
        "unspecified_scoring": "DISABLED",
    }
    assert profile.active_objective_ids("NORTH") == (SHOULD_ADJACENT, LOADING_SIDE_PREFERENCE)
    assert profile.active_objective_ids("NEAREST_TRUCK_ENTRANCE") == (
        SHOULD_ADJACENT,
        LOADING_SIDE_PREFERENCE,
    )
    assert profile.active_objective_ids("UNSPECIFIED") == (SHOULD_ADJACENT,)


def test_compactness_shape_and_unused_site_are_disabled() -> None:
    profile = approved_objective_profile()
    rules = {rule.objective_id: rule for rule in profile.objective_rules}

    for objective_id in (COMPACTNESS, SHAPE_REGULARITY, UNUSED_SITE_EFFICIENCY):
        rule = rules[objective_id]
        assert rule.status == DISABLED
        assert rule.metric is None
        assert rule.unit is None
        assert rule.direction is None


def test_canonical_profile_is_stable_and_untrusted_mutation_fails_closed() -> None:
    first = approved_objective_profile()
    second = approved_objective_profile()

    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert validate_objective_profile(first.to_dict()).canonical_json() == first.canonical_json()

    mutated = first.to_dict()
    mutated["weighted_score"] = True
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_objective_profile(mutated)
    assert exc.value.code == "OBJECTIVE_PROFILE_IDENTITY_INVALID"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("aggregation", "WEIGHTED", "INVALID_OBJECTIVE_AGGREGATION"),
        ("final_tie_break", "HASH", "INVALID_FINAL_TIE_BREAK"),
        ("hard_constraints_first", False, "INVALID_HARD_CONSTRAINT_POLICY"),
    ],
)
def test_profile_constructor_rejects_unapproved_strategy_changes(
    field: str, value: object, code: str
) -> None:
    profile = approved_objective_profile()
    with pytest.raises(LayoutAuthorityError) as exc:
        replace(profile, **{field: value})
    assert exc.value.code == code


def test_final_tie_break_is_after_exact_business_vector_and_not_a_hash() -> None:
    profile = approved_objective_profile()
    assert profile.final_tie_break == FINAL_TIE_BREAK
    assert profile.final_tie_break_after_exact_objective_vector is True
    assert profile.raw_mapping_order_allowed is False
    assert profile.hash_as_tie_break is False


def test_invalid_loading_side_is_rejected() -> None:
    with pytest.raises(LayoutAuthorityError) as exc:
        approved_objective_profile().active_objective_ids("NORTHEAST")
    assert exc.value.code == "INVALID_LOADING_SIDE"
