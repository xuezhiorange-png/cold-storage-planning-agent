"""Exact, immutable candidate geometry for the seven-zone main process."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    MAIN_PROCESS_ZONE_CODES,
    OFFSET_LINEAR_BAND,
    STRAIGHT_LINEAR_BAND,
    StructuralCompositionFamilyV1,
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

    @classmethod
    def create(
        cls,
        *,
        family: StructuralCompositionFamilyV1,
        rectangles: Mapping[str, PlacedRectangleV1],
        generation_pattern: str,
        hard_geometry_predicates_passed: Sequence[str],
        topology: str | None = None,
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
