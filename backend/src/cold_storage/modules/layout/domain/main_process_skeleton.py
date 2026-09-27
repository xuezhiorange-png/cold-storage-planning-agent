"""Exact, immutable candidate geometry for the seven-zone main process."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.main_process_topology import (
    MainProcessTopologyClassificationV1,
)
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    LINEAR_PROCESS_BAND,
    MAIN_PROCESS_ZONE_CODES,
    OFFSET_LINEAR_BAND,
    STRAIGHT_LINEAR_BAND,
    StructuralCompositionFamilyV1,
    composition_family_candidates,
)

IDENTITY: Final = "main-process-skeleton-candidate@1.0.0"


def _rectangle_record(rectangle: PlacedRectangleV1) -> dict[str, object]:
    return {
        "zone_code": rectangle.zone_code,
        "x": str(rectangle.x),
        "y": str(rectangle.y),
        "width_m": str(rectangle.width_m),
        "depth_m": str(rectangle.depth_m),
        "rotation_deg": rectangle.rotation_deg,
    }


def _envelope(
    rectangles: Sequence[PlacedRectangleV1],
) -> tuple[int, int, int, int] | None:
    if not rectangles:
        return None
    bounds = tuple(rectangle.bounds_mm for rectangle in rectangles)
    return (
        min(row[0] for row in bounds),
        min(row[1] for row in bounds),
        max(row[2] for row in bounds),
        max(row[3] for row in bounds),
    )


@dataclass(frozen=True)
class MainProcessSkeletonCandidateV1:
    """Seven authoritative-size rectangles constructed before tail search.

    This is candidate-search geometry, not an engineering dimension source.
    ``zone_rectangles`` is always in frozen process order and its identity hash
    depends only on those seven exact placements, including shipping.
    """

    family: StructuralCompositionFamilyV1
    topology: str
    dominant_axis: str
    dominant_direction: str
    zone_rectangles: tuple[PlacedRectangleV1, ...]
    raw_group_envelope: tuple[int, int, int, int]
    processing_core_envelope: tuple[int, int, int, int]
    finished_group_envelope: tuple[int, int, int, int]
    main_process_skeleton_hash: str
    generation_pattern: str
    hard_geometry_predicates_passed: tuple[str, ...]
    canonical_topology_owner: str
    construction_policy: str
    topology_divergence_stage: str
    offset_transition_stage: str | None = None
    offset_direction: str | None = None
    offset_cross_axis_shift_mm: int | None = None
    discovery_topology: str | None = None
    discovery_family: StructuralCompositionFamilyV1 | None = None

    @classmethod
    def create(
        cls,
        *,
        family: StructuralCompositionFamilyV1,
        rectangles: Mapping[str, PlacedRectangleV1],
        generation_pattern: str,
        hard_geometry_predicates_passed: Sequence[str],
        topology: str | None = None,
        construction_policy: str | None = None,
        topology_divergence_stage: str = "ROOT_OR_GROUP_BAND_FORMATION",
        offset_transition_stage: str | None = None,
        offset_direction: str | None = None,
        offset_cross_axis_shift_mm: int | None = None,
        discovery_topology: str | None = None,
        discovery_family: StructuralCompositionFamilyV1 | None = None,
    ) -> MainProcessSkeletonCandidateV1:
        if set(rectangles) & set(MAIN_PROCESS_ZONE_CODES) != set(MAIN_PROCESS_ZONE_CODES):
            raise LayoutAuthorityError("MAIN_PROCESS_SKELETON_ZONE_SET_INVALID")
        ordered = tuple(rectangles[code] for code in MAIN_PROCESS_ZONE_CODES)
        raw = _envelope(ordered[:2])
        core = _envelope((ordered[2], ordered[4]))
        finished = _envelope((ordered[3], ordered[5], ordered[6]))
        if raw is None or core is None or finished is None or not generation_pattern:
            raise LayoutAuthorityError("MAIN_PROCESS_SKELETON_FACTS_UNAVAILABLE")
        if not hard_geometry_predicates_passed:
            raise LayoutAuthorityError("MAIN_PROCESS_SKELETON_HARD_PREDICATES_REQUIRED")
        selected_topology = topology or (
            CENTRAL_PROCESS_HUB if family.family == CENTRAL_PROCESS_HUB else STRAIGHT_LINEAR_BAND
        )
        if selected_topology not in {
            STRAIGHT_LINEAR_BAND,
            OFFSET_LINEAR_BAND,
            CENTRAL_PROCESS_HUB,
        }:
            raise LayoutAuthorityError("MAIN_PROCESS_TOPOLOGY_INVALID")
        digest = canonical_hash([_rectangle_record(row) for row in ordered])
        return cls(
            family=family,
            topology=selected_topology,
            dominant_axis=family.dominant_axis,
            dominant_direction=family.dominant_direction,
            zone_rectangles=ordered,
            raw_group_envelope=raw,
            processing_core_envelope=core,
            finished_group_envelope=finished,
            main_process_skeleton_hash=digest,
            generation_pattern=generation_pattern,
            hard_geometry_predicates_passed=tuple(hard_geometry_predicates_passed),
            canonical_topology_owner=selected_topology,
            construction_policy=construction_policy or f"{selected_topology}_V1",
            topology_divergence_stage=topology_divergence_stage,
            offset_transition_stage=offset_transition_stage,
            offset_direction=offset_direction,
            offset_cross_axis_shift_mm=offset_cross_axis_shift_mm,
            discovery_topology=discovery_topology or selected_topology,
            discovery_family=discovery_family or family,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": IDENTITY,
            "family": self.family.to_dict(),
            "topology": self.topology,
            "dominant_axis": self.dominant_axis,
            "dominant_direction": self.dominant_direction,
            "zone_rectangles": [_rectangle_record(row) for row in self.zone_rectangles],
            "raw_group_envelope_mm": list(self.raw_group_envelope),
            "processing_core_envelope_mm": list(self.processing_core_envelope),
            "finished_group_envelope_mm": list(self.finished_group_envelope),
            "main_process_skeleton_hash": self.main_process_skeleton_hash,
            "generation_pattern": self.generation_pattern,
            "hard_geometry_predicates_passed": list(self.hard_geometry_predicates_passed),
            "authority": "CANDIDATE_SEARCH_GEOMETRY_ONLY",
        }

    def to_evaluation_dict(self) -> dict[str, object]:
        """Add R6-only topology provenance outside Tool 7 serialization."""
        return {
            **self.to_dict(),
            "canonical_topology_owner": self.canonical_topology_owner,
            "construction_policy": self.construction_policy,
            "topology_divergence_stage": self.topology_divergence_stage,
            "offset_transition_stage": self.offset_transition_stage,
            "offset_direction": self.offset_direction,
            "offset_cross_axis_shift_mm": self.offset_cross_axis_shift_mm,
            "discovery_topology": self.discovery_topology or self.topology,
            "discovery_family": (self.discovery_family or self.family).to_dict(),
            "canonical_family": self.family.to_dict(),
        }


def canonicalize_main_process_skeleton_for_evaluation(
    skeleton: MainProcessSkeletonCandidateV1,
    classification: MainProcessTopologyClassificationV1,
    *,
    site_geometry: Mapping[str, object],
) -> MainProcessSkeletonCandidateV1:
    """Rebind evaluation identity to exact geometry classification, never geometry.

    Discovery metadata remains attached to the immutable candidate for
    diagnostics. Rectangle coordinates, dimensions, rotations and the
    geometry-derived hash are preserved byte-for-byte.
    """
    owner = classification.canonical_owner
    if owner is None:
        raise LayoutAuthorityError("MAIN_PROCESS_TOPOLOGY_CLASSIFICATION_REQUIRED")
    if owner in {STRAIGHT_LINEAR_BAND, OFFSET_LINEAR_BAND}:
        if classification.process_axis not in {
            "X",
            "Y",
        } or classification.process_direction not in {
            "POSITIVE",
            "NEGATIVE",
        }:
            raise LayoutAuthorityError("MAIN_PROCESS_TOPOLOGY_CLASSIFICATION_INCOMPLETE")
        discovery_family = skeleton.discovery_family or skeleton.family
        if (
            skeleton.discovery_topology == owner
            and discovery_family.family == LINEAR_PROCESS_BAND
            and discovery_family.dominant_axis == classification.process_axis
            and discovery_family.dominant_direction == classification.process_direction
        ):
            canonical_family = discovery_family
        else:
            canonical_family = StructuralCompositionFamilyV1(
                family=LINEAR_PROCESS_BAND,
                dominant_axis=classification.process_axis,
                dominant_direction=classification.process_direction,
                generation_reason="EXACT_GEOMETRY_CLASSIFICATION_V1",
            )
    elif owner == CENTRAL_PROCESS_HUB:
        hub_family = next(
            (
                family
                for family in composition_family_candidates(site_geometry)
                if family.family == CENTRAL_PROCESS_HUB
            ),
            None,
        )
        if hub_family is None:
            raise LayoutAuthorityError("CANONICAL_HUB_FAMILY_UNAVAILABLE")
        canonical_family = hub_family
    else:
        raise LayoutAuthorityError("MAIN_PROCESS_TOPOLOGY_INVALID")

    return replace(
        skeleton,
        family=canonical_family,
        topology=owner,
        dominant_axis=canonical_family.dominant_axis,
        dominant_direction=canonical_family.dominant_direction,
        canonical_topology_owner=owner,
        discovery_topology=skeleton.discovery_topology or skeleton.topology,
        discovery_family=skeleton.discovery_family or skeleton.family,
    )
