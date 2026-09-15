"""Owner-approved deterministic objective metadata; never place or route objects.

This module freezes the objective vocabulary and evaluation boundary for the
future site-layout engine.  It deliberately exposes no score calculation,
candidate generation, route generation, or search implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Final

from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)

PROFILE_ID: Final = "site-constrained-objective-profile"
PROFILE_VERSION: Final = "1.0.0"
IDENTITY: Final = f"{PROFILE_ID}@{PROFILE_VERSION}"
SCHEMA_VERSION: Final = "1.0.0"
SOURCE_AUTHORITY: Final = "Charles:V2_2_P2B2_OBJECTIVE_PROFILE_CONTRACT_FREEZE_R1"

LEXICOGRAPHIC: Final = "LEXICOGRAPHIC"
PLACEMENT_STAGE: Final = "PLACEMENT"
ROUTE_STAGE: Final = "ROUTE"
FINAL_STAGE: Final = "FINAL"
OBJECTIVE_STAGING: Final = "PLACEMENT_THEN_ROUTE_THEN_FINAL_TIE_BREAK"

ACTIVE: Final = "ACTIVE"
CONDITIONAL: Final = "CONDITIONAL"
DEFERRED: Final = "DEFERRED"
DISABLED: Final = "DISABLED"

SHOULD_ADJACENT: Final = "SHOULD_ADJACENT"
MATERIAL_FLOW_DISTANCE: Final = "MATERIAL_FLOW_DISTANCE"
LOADING_SIDE_PREFERENCE: Final = "LOADING_SIDE_PREFERENCE"
COMPACTNESS: Final = "COMPACTNESS"
CIRCULATION_LENGTH: Final = "CIRCULATION_LENGTH"
PEOPLE_TRUCK_SEPARATION: Final = "PEOPLE_TRUCK_SEPARATION"
SHAPE_REGULARITY: Final = "SHAPE_REGULARITY"
UNUSED_SITE_EFFICIENCY: Final = "UNUSED_SITE_EFFICIENCY"

OBJECTIVE_VOCABULARY: Final = (
    SHOULD_ADJACENT,
    MATERIAL_FLOW_DISTANCE,
    LOADING_SIDE_PREFERENCE,
    COMPACTNESS,
    CIRCULATION_LENGTH,
    PEOPLE_TRUCK_SEPARATION,
    SHAPE_REGULARITY,
    UNUSED_SITE_EFFICIENCY,
)
OBJECTIVE_VOCABULARY_COUNT: Final = len(OBJECTIVE_VOCABULARY)
P0_DECLARATION_ORDER_USED_AS_PRIORITY: Final = False
SOFT_OBJECTIVE_COUNT: Final = OBJECTIVE_VOCABULARY_COUNT

PLACEMENT_OBJECTIVE_ORDER: Final = (
    SHOULD_ADJACENT,
    LOADING_SIDE_PREFERENCE,
)
ROUTE_OBJECTIVE_ORDER: Final[tuple[str, ...] | None] = None
ROUTE_OBJECTIVE_ORDER_FROZEN: Final = False
DISABLED_OBJECTIVES: Final = (
    COMPACTNESS,
    SHAPE_REGULARITY,
    UNUSED_SITE_EFFICIENCY,
)
DEFERRED_OBJECTIVES: Final = (
    MATERIAL_FLOW_DISTANCE,
    CIRCULATION_LENGTH,
    PEOPLE_TRUCK_SEPARATION,
)

# Keep the Owner-facing label separate from the stable implementation metric
# identifier.  The profile freezes metadata only; it does not score layouts.
SHOULD_ADJACENT_METRIC: Final = "SATISFIED_COUNT"
SHOULD_ADJACENT_METRIC_ID: Final = "SATISFIED_SHOULD_ADJACENCY_COUNT"
SHOULD_ADJACENT_COUNT: Final = 5
SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT: Final = False

ACTUAL_ROUTE_LENGTH_METRIC: Final = "ACTUAL_PORTAL_CORRIDOR_ROUTE_LENGTH"
ROUTE_DISTANCE_UNIT: Final = "m"
ROUTE_DISTANCE_DIRECTION: Final = "MINIMIZE"
ROUTE_PROXY_ALLOWED: Final = False

CARDINAL_LOADING_SIDE_METRIC: Final = "BINARY_MATCH"
CARDINAL_LOADING_SIDE_DIRECTION: Final = "MAXIMIZE_MATCH"
NEAREST_TRUCK_ENTRANCE_METRIC: Final = "MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE"
NEAREST_TRUCK_ENTRANCE_DIRECTION: Final = "MINIMIZE_DISTANCE"
NEAREST_TRUCK_ENTRANCE_COMPARATOR: Final = "EXACT_MIN_SEGMENT_TO_SEGMENT_SQUARED_EUCLIDEAN_DISTANCE"
NEAREST_TRUCK_ENTRANCE_INTERNAL_UNIT: Final = "MM2"
FLOAT_EPSILON_ALLOWED: Final = False
SQRT_REQUIRED_FOR_RANKING: Final = False
UNSPECIFIED_LOADING_SIDE_SCORING: Final = "DISABLED"

COMPACTNESS_ACTIVE: Final = False
SHAPE_REGULARITY_ACTIVE: Final = False
UNUSED_SITE_EFFICIENCY_ACTIVE: Final = False
DEFER_UNTIL_BUILDING_ROUTE_AUTHORITY_COMPLETE: Final = True

FINAL_TIE_BREAK: Final = "CANONICAL_NORMALIZED_FULL_LAYOUT_JSON_LEXICAL"
FINAL_TIE_BREAK_AFTER_EXACT_OBJECTIVE_VECTOR: Final = True
RAW_MAPPING_ORDER_ALLOWED: Final = False
HASH_AS_TIE_BREAK: Final = False


@dataclass(frozen=True)
class ObjectiveRuleV1:
    """One declared soft objective, without an engineering scoring function."""

    objective_id: str
    stage: str
    status: str
    metric: str | None
    unit: str | None
    direction: str | None
    proxy_allowed: bool
    required_inputs: tuple[str, ...]
    owner_metric_required: bool = False

    def __post_init__(self) -> None:
        if self.objective_id not in OBJECTIVE_VOCABULARY:
            raise LayoutAuthorityError("UNKNOWN_OBJECTIVE")
        if self.stage not in {PLACEMENT_STAGE, ROUTE_STAGE, FINAL_STAGE}:
            raise LayoutAuthorityError("INVALID_OBJECTIVE_STAGE")
        if self.status not in {ACTIVE, CONDITIONAL, DEFERRED, DISABLED}:
            raise LayoutAuthorityError("INVALID_OBJECTIVE_STATUS")
        if not isinstance(self.proxy_allowed, bool):
            raise LayoutAuthorityError("INVALID_OBJECTIVE_PROXY_POLICY")
        if not self.required_inputs or any(
            not isinstance(item, str) or not item for item in self.required_inputs
        ):
            raise LayoutAuthorityError("INVALID_OBJECTIVE_INPUTS")
        if self.status in {ACTIVE, CONDITIONAL} and not self.metric:
            raise LayoutAuthorityError("OBJECTIVE_METRIC_REQUIRED")
        if self.status == DEFERRED and self.metric is None and not self.owner_metric_required:
            raise LayoutAuthorityError("OBJECTIVE_METRIC_REQUIRED")
        if self.status == DISABLED and self.metric is not None:
            raise LayoutAuthorityError("DISABLED_OBJECTIVE_MUST_NOT_SCORE")


_OBJECTIVE_RULES: Final = (
    ObjectiveRuleV1(
        SHOULD_ADJACENT,
        PLACEMENT_STAGE,
        ACTIVE,
        SHOULD_ADJACENT_METRIC_ID,
        "COUNT",
        "MAXIMIZE",
        False,
        ("AdjacencyGraphV1.should_adjacencies", "complete_zone_rectangles"),
    ),
    ObjectiveRuleV1(
        MATERIAL_FLOW_DISTANCE,
        ROUTE_STAGE,
        DEFERRED,
        ACTUAL_ROUTE_LENGTH_METRIC,
        ROUTE_DISTANCE_UNIT,
        ROUTE_DISTANCE_DIRECTION,
        ROUTE_PROXY_ALLOWED,
        ("portal_geometry", "corridor_geometry", "actual_material_route"),
    ),
    ObjectiveRuleV1(
        LOADING_SIDE_PREFERENCE,
        PLACEMENT_STAGE,
        CONDITIONAL,
        "BINARY_MATCH_OR_MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE",
        "BOOLEAN_OR_m",
        "MAXIMIZE_MATCH_OR_MINIMIZE_DISTANCE",
        False,
        ("preferred_loading_side", "shipping_loading_face", "truck_entrance"),
    ),
    ObjectiveRuleV1(
        COMPACTNESS,
        PLACEMENT_STAGE,
        DISABLED,
        None,
        None,
        None,
        False,
        ("building_footprint",),
    ),
    ObjectiveRuleV1(
        CIRCULATION_LENGTH,
        ROUTE_STAGE,
        DEFERRED,
        ACTUAL_ROUTE_LENGTH_METRIC,
        ROUTE_DISTANCE_UNIT,
        ROUTE_DISTANCE_DIRECTION,
        ROUTE_PROXY_ALLOWED,
        ("portal_geometry", "corridor_geometry", "actual_circulation_routes"),
    ),
    ObjectiveRuleV1(
        PEOPLE_TRUCK_SEPARATION,
        ROUTE_STAGE,
        DEFERRED,
        None,
        None,
        None,
        False,
        ("personnel_route", "truck_route", "personnel_truck_policy"),
        owner_metric_required=True,
    ),
    ObjectiveRuleV1(
        SHAPE_REGULARITY,
        PLACEMENT_STAGE,
        DISABLED,
        None,
        None,
        None,
        False,
        ("building_footprint", "zone_footprints"),
    ),
    ObjectiveRuleV1(
        UNUSED_SITE_EFFICIENCY,
        PLACEMENT_STAGE,
        DISABLED,
        None,
        None,
        None,
        False,
        ("effective_buildable_boundary", "building_footprint"),
    ),
)


@dataclass(frozen=True)
class ObjectiveProfileV1:
    """Canonical owner decision package for future deterministic placement."""

    identity: str
    schema_version: str
    source_authority: str
    aggregation: str
    weighted_score: bool
    objective_staging: str
    objective_vocabulary: tuple[str, ...]
    placement_priority_order: tuple[str, ...]
    route_priority_order: tuple[str, ...] | None
    route_priority_order_frozen: bool
    disabled_objectives: tuple[str, ...]
    deferred_objectives: tuple[str, ...]
    objective_rules: tuple[ObjectiveRuleV1, ...]
    hard_constraints_first: bool
    hard_violation_cannot_be_offset: bool
    final_tie_break: str
    final_tie_break_after_exact_objective_vector: bool
    raw_mapping_order_allowed: bool
    hash_as_tie_break: bool

    def __post_init__(self) -> None:
        if (
            self.identity != IDENTITY
            or self.schema_version != SCHEMA_VERSION
            or self.source_authority != SOURCE_AUTHORITY
        ):
            raise LayoutAuthorityError("OBJECTIVE_PROFILE_IDENTITY_INVALID")
        if self.aggregation != LEXICOGRAPHIC or self.weighted_score is not False:
            raise LayoutAuthorityError("INVALID_OBJECTIVE_AGGREGATION")
        if self.objective_staging != OBJECTIVE_STAGING:
            raise LayoutAuthorityError("INVALID_OBJECTIVE_STAGING")
        if P0_DECLARATION_ORDER_USED_AS_PRIORITY is not False:
            raise LayoutAuthorityError("INVALID_OBJECTIVE_DECLARATION_ORDER_POLICY")
        if self.objective_vocabulary != OBJECTIVE_VOCABULARY:
            raise LayoutAuthorityError("INVALID_OBJECTIVE_VOCABULARY")
        if self.placement_priority_order != PLACEMENT_OBJECTIVE_ORDER:
            raise LayoutAuthorityError("INVALID_PLACEMENT_OBJECTIVE_ORDER")
        if (
            self.route_priority_order != ROUTE_OBJECTIVE_ORDER
            or self.route_priority_order_frozen is not ROUTE_OBJECTIVE_ORDER_FROZEN
        ):
            raise LayoutAuthorityError("INVALID_ROUTE_OBJECTIVE_ORDER_STATUS")
        if self.disabled_objectives != DISABLED_OBJECTIVES:
            raise LayoutAuthorityError("INVALID_DISABLED_OBJECTIVES")
        if self.deferred_objectives != DEFERRED_OBJECTIVES:
            raise LayoutAuthorityError("INVALID_DEFERRED_OBJECTIVES")
        if not all(isinstance(rule, ObjectiveRuleV1) for rule in self.objective_rules):
            raise LayoutAuthorityError("INVALID_OBJECTIVE_RULE_SET")
        if tuple(rule.objective_id for rule in self.objective_rules) != OBJECTIVE_VOCABULARY:
            raise LayoutAuthorityError("INVALID_OBJECTIVE_RULE_SET")
        if not self.hard_constraints_first or not self.hard_violation_cannot_be_offset:
            raise LayoutAuthorityError("INVALID_HARD_CONSTRAINT_POLICY")
        if self.final_tie_break != FINAL_TIE_BREAK:
            raise LayoutAuthorityError("INVALID_FINAL_TIE_BREAK")
        if self.final_tie_break_after_exact_objective_vector is not True:
            raise LayoutAuthorityError("INVALID_FINAL_TIE_BREAK")
        if self.raw_mapping_order_allowed is not False or self.hash_as_tie_break is not False:
            raise LayoutAuthorityError("INVALID_FINAL_TIE_BREAK")

        by_id = {rule.objective_id: rule for rule in self.objective_rules}
        should = by_id[SHOULD_ADJACENT]
        if (
            should.metric != SHOULD_ADJACENT_METRIC_ID
            or should.unit != "COUNT"
            or should.direction != "MAXIMIZE"
            or should.status != ACTIVE
            or should.proxy_allowed
        ):
            raise LayoutAuthorityError("INVALID_SHOULD_ADJACENCY_RULE")
        for objective_id in (MATERIAL_FLOW_DISTANCE, CIRCULATION_LENGTH):
            rule = by_id[objective_id]
            if (
                rule.metric != ACTUAL_ROUTE_LENGTH_METRIC
                or rule.unit != ROUTE_DISTANCE_UNIT
                or rule.direction != ROUTE_DISTANCE_DIRECTION
                or rule.proxy_allowed is not ROUTE_PROXY_ALLOWED
                or rule.status != DEFERRED
            ):
                raise LayoutAuthorityError("INVALID_ROUTE_OBJECTIVE_RULE")
        loading = by_id[LOADING_SIDE_PREFERENCE]
        if (
            loading.status != CONDITIONAL
            or loading.proxy_allowed
            or loading.metric
            != "BINARY_MATCH_OR_MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE"
        ):
            raise LayoutAuthorityError("INVALID_LOADING_SIDE_RULE")
        for objective_id in DISABLED_OBJECTIVES:
            if by_id[objective_id].status != DISABLED:
                raise LayoutAuthorityError("DISABLED_OBJECTIVE_REQUIRED")
        for objective_id in DEFERRED_OBJECTIVES:
            if by_id[objective_id].status != DEFERRED:
                raise LayoutAuthorityError("DEFERRED_OBJECTIVE_REQUIRED")
        if not by_id[PEOPLE_TRUCK_SEPARATION].owner_metric_required:
            raise LayoutAuthorityError("INVALID_PEOPLE_TRUCK_RULE")

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "schema_version": self.schema_version,
            "source_authority": self.source_authority,
            "aggregation": self.aggregation,
            "weighted_score": self.weighted_score,
            "objective_staging": self.objective_staging,
            "objective_vocabulary_count": len(self.objective_vocabulary),
            "p0_declaration_order_used_as_priority": P0_DECLARATION_ORDER_USED_AS_PRIORITY,
            "objective_vocabulary": list(self.objective_vocabulary),
            "placement_priority_order": list(self.placement_priority_order),
            "route_priority_order": (
                list(self.route_priority_order) if self.route_priority_order is not None else None
            ),
            "route_priority_order_frozen": self.route_priority_order_frozen,
            "disabled_objectives": list(self.disabled_objectives),
            "deferred_objectives": list(self.deferred_objectives),
            "objective_rules": [asdict(rule) for rule in self.objective_rules],
            "hard_constraints_first": self.hard_constraints_first,
            "hard_violation_cannot_be_offset": self.hard_violation_cannot_be_offset,
            "final_tie_break": self.final_tie_break,
            "final_tie_break_after_exact_objective_vector": (
                self.final_tie_break_after_exact_objective_vector
            ),
            "raw_mapping_order_allowed": self.raw_mapping_order_allowed,
            "hash_as_tie_break": self.hash_as_tie_break,
            "should_adjacency": {
                "metric": SHOULD_ADJACENT_METRIC,
                "metric_id": SHOULD_ADJACENT_METRIC_ID,
                "count": SHOULD_ADJACENT_COUNT,
                "shipping_truck_entrance_proximity_in_count": (
                    SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT
                ),
            },
            "loading_side": {
                "cardinal_metric": CARDINAL_LOADING_SIDE_METRIC,
                "cardinal_direction": CARDINAL_LOADING_SIDE_DIRECTION,
                "nearest_truck_entrance_metric": NEAREST_TRUCK_ENTRANCE_METRIC,
                "nearest_truck_entrance_direction": NEAREST_TRUCK_ENTRANCE_DIRECTION,
                "nearest_truck_entrance_comparator": NEAREST_TRUCK_ENTRANCE_COMPARATOR,
                "nearest_truck_entrance_internal_unit": NEAREST_TRUCK_ENTRANCE_INTERNAL_UNIT,
                "float_epsilon_allowed": FLOAT_EPSILON_ALLOWED,
                "sqrt_required_for_ranking": SQRT_REQUIRED_FOR_RANKING,
                "unspecified_scoring": UNSPECIFIED_LOADING_SIDE_SCORING,
            },
            "route_policy": {
                "actual_portal_corridor_route_required": True,
                "centroid_proxy_allowed": False,
                "edge_manhattan_proxy_allowed": False,
                "straight_line_proxy_allowed": False,
            },
            "deferred_until_building_route_authority_complete": (
                DEFER_UNTIL_BUILDING_ROUTE_AUTHORITY_COMPLETE
            ),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def active_objective_ids(self, preferred_loading_side: str) -> tuple[str, ...]:
        """Return only currently scoreable IDs; this never computes a score."""
        if preferred_loading_side not in {
            "NORTH",
            "EAST",
            "SOUTH",
            "WEST",
            "NEAREST_TRUCK_ENTRANCE",
            "UNSPECIFIED",
        }:
            raise LayoutAuthorityError("INVALID_LOADING_SIDE")
        return tuple(
            objective_id
            for objective_id in self.placement_priority_order
            if objective_id != LOADING_SIDE_PREFERENCE or preferred_loading_side != "UNSPECIFIED"
        )


def approved_objective_profile() -> ObjectiveProfileV1:
    """Return the server-owned profile; callers cannot supply objective rules."""
    return ObjectiveProfileV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        source_authority=SOURCE_AUTHORITY,
        aggregation=LEXICOGRAPHIC,
        weighted_score=False,
        objective_staging=OBJECTIVE_STAGING,
        objective_vocabulary=OBJECTIVE_VOCABULARY,
        placement_priority_order=PLACEMENT_OBJECTIVE_ORDER,
        route_priority_order=ROUTE_OBJECTIVE_ORDER,
        route_priority_order_frozen=ROUTE_OBJECTIVE_ORDER_FROZEN,
        disabled_objectives=DISABLED_OBJECTIVES,
        deferred_objectives=DEFERRED_OBJECTIVES,
        objective_rules=_OBJECTIVE_RULES,
        hard_constraints_first=True,
        hard_violation_cannot_be_offset=True,
        final_tie_break=FINAL_TIE_BREAK,
        final_tie_break_after_exact_objective_vector=True,
        raw_mapping_order_allowed=False,
        hash_as_tie_break=False,
    )


def validate_objective_profile(source: Mapping[str, object]) -> ObjectiveProfileV1:
    """Fail closed unless a serialized profile is byte-for-byte server-owned."""
    profile = approved_objective_profile()
    if not isinstance(source, Mapping) or canonical_json(dict(source)) != profile.canonical_json():
        raise LayoutAuthorityError("OBJECTIVE_PROFILE_IDENTITY_INVALID")
    return profile
