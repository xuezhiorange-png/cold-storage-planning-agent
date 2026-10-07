"""Server-owned pairwise realization boundary; no caller-authored composition authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.application.composition_placement import _assert_server_replay
from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.adjacency import process_graph
from cold_storage.modules.layout.domain.authority_shapes import (
    authoritative_zone_shapes,
    canonical_construction_shapes,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    MetricInterfaceReservationV1,
    MetricMandatoryInterfaceCapacityGateV1,
    aggregate_metric_gate,
    evaluate_pair_domain,
    realize_interface,
)
from cold_storage.modules.layout.domain.site_geometry import (
    normalize_polygon,
    validated_hard_obstacle_polygons,
)
from cold_storage.modules.layout.domain.structural_composition import _mandatory_edge_identity


@dataclass(frozen=True)
class MetricInterfaceReservationRealizationV1:
    composition_identity: str
    family: str
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    source_structural_composition_hash: str
    source_composition_handoff_hash: str
    source_graph_identity: str
    dimension_authority_identity: str
    reservations: tuple[MetricInterfaceReservationV1, ...]
    gate: MetricMandatoryInterfaceCapacityGateV1
    pairwise_capacity_only: bool = True
    other_zone_non_overlap_proven: bool = False
    whole_building_feasibility_proven: bool = False
    complete_layout_proven: bool = False
    project_layout_validated_claimed: bool = False

    def __post_init__(self) -> None:
        if (
            not self.pairwise_capacity_only
            or any(
                (
                    self.other_zone_non_overlap_proven,
                    self.whole_building_feasibility_proven,
                    self.complete_layout_proven,
                    self.project_layout_validated_claimed,
                )
            )
            or self.gate != aggregate_metric_gate(self.reservations)
        ):
            raise ValueError("INVALID_METRIC_REALIZATION_SCOPE_OR_GATE")
        edges = tuple(r.source_edge_identity for r in self.reservations)
        if len(edges) != len(set(edges)):
            raise ValueError("DUPLICATE_METRIC_RESERVATION")
        graph = process_graph()
        expected = tuple(
            _mandatory_edge_identity(graph, tuple(sorted(e))) for e in graph.must_adjacencies
        )
        if edges != expected or self.source_graph_identity != graph.identity:
            raise ValueError("METRIC_AUTHORITY_COVERAGE_MISMATCH")
        for item in self.reservations:
            for slot in item.representative_slots:
                if (
                    slot.source_site_geometry_hash != self.source_site_geometry_hash
                    or slot.source_dimension_authority_identity != self.dimension_authority_identity
                ):
                    raise ValueError("METRIC_SLOT_PROVENANCE_MISMATCH")
                for role, shape, identity in (
                    (
                        slot.endpoint_a_role,
                        slot.endpoint_a_shape,
                        slot.endpoint_a_shape_authority_identity,
                    ),
                    (
                        slot.endpoint_b_role,
                        slot.endpoint_b_shape,
                        slot.endpoint_b_shape_authority_identity,
                    ),
                ):
                    if identity != canonical_hash(
                        {
                            "authority": self.dimension_authority_identity,
                            "role": role,
                            "shape": asdict(shape),
                        }
                    ):
                        raise ValueError("METRIC_SHAPE_PROVENANCE_MISMATCH")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def realize_metric_interface_reservations(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
) -> tuple[MetricInterfaceReservationRealizationV1, ...]:
    """Rebuild all six structural handoffs from bound authorities, then realize.

    Pair domains are independent of family hosts at this scope. Reuse exact
    within-invocation evaluations, but bind each of the 42 artifacts separately.
    No prior evidence, caller result or persisted geometry is loaded.
    """
    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    structural = build_structural_compositions(canonical_zone_plan, p1_handoff, site_geometry)
    _assert_server_replay(structural, binding)
    body = site_geometry.to_dict()
    boundary = normalize_polygon(
        body["site"]["effective_buildable_boundary"], allow_numeric_string=True
    )
    obstacles = validated_hard_obstacle_polygons(body)
    shapes = authoritative_zone_shapes(binding.dimension_authorities, boundary, obstacles)
    construction = {role: canonical_construction_shapes(s) for role, s in shapes.items()}
    domains = {}
    results = []
    for handoff in structural.placement_handoffs:
        items = []
        for reservation in handoff.mandatory_interface_reservations:
            roles = (reservation.endpoint_a_role, reservation.endpoint_b_role)
            key = tuple(sorted(roles))
            if key not in domains:
                domains[key] = evaluate_pair_domain(
                    roles, (construction[roles[0]], construction[roles[1]]), boundary, obstacles
                )
            items.append(
                realize_interface(
                    reservation,
                    domains[key],
                    site_hash=binding.site_geometry_hash,
                    dimension_identity=handoff.dimension_authority_identity,
                    shape_counts=(len(shapes[roles[0]]), len(shapes[roles[1]])),
                    construction_counts=(len(construction[roles[0]]), len(construction[roles[1]])),
                )
            )
        results.append(
            MetricInterfaceReservationRealizationV1(
                handoff.composition_identity,
                handoff.family,
                binding.canonical_zone_plan_hash,
                binding.p1_handoff_hash,
                binding.site_geometry_hash,
                handoff.source_composition_hash,
                handoff.canonical_result_hash,
                process_graph().identity,
                handoff.dimension_authority_identity,
                tuple(items),
                aggregate_metric_gate(items),
            )
        )
    return tuple(results)
