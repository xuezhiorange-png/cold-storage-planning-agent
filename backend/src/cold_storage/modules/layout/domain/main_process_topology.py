"""Exact geometric ownership for constructive main-process topologies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    MAIN_PROCESS_ZONE_CODES,
    OFFSET_LINEAR_BAND,
    STRAIGHT_LINEAR_BAND,
)

IDENTITY: Final = "main-process-topology-classification@1.0.0"
_GROUP_ZONE_CODES: Final = (
    ("raw_fruit_buffer", "primary_precooling_room"),
    ("sorting_packaging_room", "coating_room"),
    ("secondary_precooling_room", "finished_goods_room", "shipping_channel"),
)
_TOPOLOGY_PRECEDENCE: Final = (
    STRAIGHT_LINEAR_BAND,
    OFFSET_LINEAR_BAND,
    CENTRAL_PROCESS_HUB,
)


@dataclass(frozen=True)
class MainProcessTopologyClassificationV1:
    """Classification facts; topology identity is not an engineering gate."""

    canonical_owner: str | None
    matched_topologies: tuple[str, ...]
    process_axis: str | None
    process_direction: str | None
    pairwise_band_continuity: bool
    three_group_common_band: bool
    offset_transition_present: bool
    cross_axis_shift_gt_zero: bool
    hub_raw_face: str | None
    hub_finished_face: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": IDENTITY,
            "canonical_owner": self.canonical_owner,
            "matched_topologies": list(self.matched_topologies),
            "process_axis": self.process_axis,
            "process_direction": self.process_direction,
            "pairwise_band_continuity": self.pairwise_band_continuity,
            "three_group_common_band": self.three_group_common_band,
            "offset_transition_present": self.offset_transition_present,
            "cross_axis_shift_gt_zero": self.cross_axis_shift_gt_zero,
            "hub_raw_face": self.hub_raw_face,
            "hub_finished_face": self.hub_finished_face,
            "engineering_validity_gate": False,
            "quality_score": False,
        }


@dataclass(frozen=True)
class MainProcessTopologyOwnershipDecisionV1:
    """Deterministic geometry-evaluation admission, independent of topology owner."""

    discovery_lane: str
    canonical_owner: str
    first_discovery_topology: str | None
    tail_search_discovery_topology: str | None
    geometry_previously_seen: bool
    tail_search_started: bool
    cross_topology_duplicate: bool
    start_tail_search: bool
    action: str


def decide_main_process_topology_ownership_v1(
    *,
    lane_topology: str,
    canonical_owner: str,
    first_discovery_topology: str | None,
    tail_search_discovery_topology: str | None,
    geometry_previously_seen: bool,
    tail_search_started: bool,
) -> MainProcessTopologyOwnershipDecisionV1:
    """Admit each unseen exact geometry to tail search once.

    ``canonical_owner`` classifies geometry. It never grants or denies
    evaluation admission; only the geometry-hash registry's lifecycle state
    does that.
    """
    cross_topology_duplicate = (
        geometry_previously_seen
        and first_discovery_topology is not None
        and first_discovery_topology != lane_topology
    )
    if tail_search_started:
        action = "SKIP_ALREADY_EVALUATED_GEOMETRY"
        start_tail_search = False
    else:
        action = (
            "START_TAIL_FOR_PREVIOUSLY_SEEN_UNEVALUATED_GEOMETRY"
            if geometry_previously_seen
            else "START_TAIL_FOR_NEW_GEOMETRY"
        )
        start_tail_search = True
    return MainProcessTopologyOwnershipDecisionV1(
        discovery_lane=lane_topology,
        canonical_owner=canonical_owner,
        first_discovery_topology=first_discovery_topology,
        tail_search_discovery_topology=tail_search_discovery_topology,
        geometry_previously_seen=geometry_previously_seen,
        tail_search_started=tail_search_started,
        cross_topology_duplicate=cross_topology_duplicate,
        start_tail_search=start_tail_search,
        action=action,
    )


def _axis_interval(
    rectangles: Mapping[str, PlacedRectangleV1], zone_codes: tuple[str, ...], axis: str
) -> tuple[int, int]:
    bounds = tuple(rectangles[code].bounds_mm for code in zone_codes)
    low_index, high_index = (0, 2) if axis == "X" else (1, 3)
    return min(row[low_index] for row in bounds), max(row[high_index] for row in bounds)


def _intervals_move_in_order(intervals: tuple[tuple[int, int], ...], direction: str) -> bool:
    if direction == "POSITIVE":
        return all(
            first[0] <= second[0] and first[1] <= second[1]
            for first, second in zip(intervals, intervals[1:], strict=False)
        )
    return all(
        first[0] >= second[0] and first[1] >= second[1]
        for first, second in zip(intervals, intervals[1:], strict=False)
    )


def _pairwise_positive_overlap(intervals: tuple[tuple[int, int], ...]) -> bool:
    return all(
        max(first[0], second[0]) < min(first[1], second[1])
        for first, second in zip(intervals, intervals[1:], strict=False)
    )


def _face_between(first: PlacedRectangleV1, second: PlacedRectangleV1) -> str | None:
    first_left, first_bottom, first_right, first_top = first.bounds_mm
    second_left, second_bottom, second_right, second_top = second.bounds_mm
    if first_right == second_left and min(first_top, second_top) > max(first_bottom, second_bottom):
        return "EAST"
    if first_left == second_right and min(first_top, second_top) > max(first_bottom, second_bottom):
        return "WEST"
    if first_top == second_bottom and min(first_right, second_right) > max(first_left, second_left):
        return "NORTH"
    if first_bottom == second_top and min(first_right, second_right) > max(first_left, second_left):
        return "SOUTH"
    return None


def classify_main_process_topology_v1(
    rectangles: Mapping[str, PlacedRectangleV1],
) -> MainProcessTopologyClassificationV1:
    """Assign one canonical owner using exact group envelopes and shared faces.

    Linear identity is evaluated on both orthogonal process axes. A straight
    band requires monotonic group-envelope movement and a common positive-
    width cross-axis interval. An offset band requires monotonic movement,
    positive adjacent overlap, and no three-group common interval. Hub identity
    requires the sorting root to share distinct faces with raw and finished
    process interfaces. Precedence only resolves identity overlap; it does not
    rank engineering quality or alter P2D validity.
    """
    if not set(MAIN_PROCESS_ZONE_CODES).issubset(rectangles) or any(
        rectangles[code].zone_code != code for code in MAIN_PROCESS_ZONE_CODES if code in rectangles
    ):
        return MainProcessTopologyClassificationV1(
            None, (), None, None, False, False, False, False, None, None
        )

    linear_witnesses: list[tuple[str, str, str, bool]] = []
    for process_axis in ("X", "Y"):
        cross_axis = "Y" if process_axis == "X" else "X"
        process_intervals = tuple(
            _axis_interval(rectangles, codes, process_axis) for codes in _GROUP_ZONE_CODES
        )
        cross_intervals = tuple(
            _axis_interval(rectangles, codes, cross_axis) for codes in _GROUP_ZONE_CODES
        )
        common_low = max(interval[0] for interval in cross_intervals)
        common_high = min(interval[1] for interval in cross_intervals)
        common_band = common_low < common_high
        pairwise = _pairwise_positive_overlap(cross_intervals)
        for direction in ("POSITIVE", "NEGATIVE"):
            if not _intervals_move_in_order(process_intervals, direction):
                continue
            if common_band:
                linear_witnesses.append((STRAIGHT_LINEAR_BAND, process_axis, direction, pairwise))
            elif pairwise:
                linear_witnesses.append((OFFSET_LINEAR_BAND, process_axis, direction, True))

    sorting = rectangles["sorting_packaging_room"]
    raw_face = _face_between(sorting, rectangles["primary_precooling_room"])
    finished_face = _face_between(sorting, rectangles["secondary_precooling_room"])
    hub_matches = raw_face is not None and finished_face is not None and raw_face != finished_face

    matched = {row[0] for row in linear_witnesses}
    if hub_matches:
        matched.add(CENTRAL_PROCESS_HUB)
    ordered_matches = tuple(topology for topology in _TOPOLOGY_PRECEDENCE if topology in matched)
    canonical_owner = ordered_matches[0] if ordered_matches else None
    owner_witness = next((row for row in linear_witnesses if row[0] == canonical_owner), None)
    return MainProcessTopologyClassificationV1(
        canonical_owner=canonical_owner,
        matched_topologies=ordered_matches,
        process_axis=owner_witness[1] if owner_witness is not None else None,
        process_direction=owner_witness[2] if owner_witness is not None else None,
        pairwise_band_continuity=owner_witness[3] if owner_witness is not None else False,
        three_group_common_band=(canonical_owner == STRAIGHT_LINEAR_BAND),
        offset_transition_present=(canonical_owner == OFFSET_LINEAR_BAND),
        cross_axis_shift_gt_zero=(canonical_owner == OFFSET_LINEAR_BAND),
        hub_raw_face=raw_face,
        hub_finished_face=finished_face,
    )
