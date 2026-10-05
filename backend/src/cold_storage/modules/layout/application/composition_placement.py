"""Server-owned replay boundary for composition-constrained exact placement."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from cold_storage.modules.layout.application.dimension_zones import ZoneDimensioningResultV1
from cold_storage.modules.layout.application.layout_authority_binding import (
    LayoutAuthorityBindingV1,
    bind_layout_authority,
)
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.application.structural_composition import (
    StructuralCompositionEnumerationResultV1,
    build_structural_compositions,
)
from cold_storage.modules.layout.domain.composition_handoff import (
    StructuralCompositionPlacementHandoffV1,
)
from cold_storage.modules.layout.domain.composition_placement import (
    DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    CompositionPlacementEnumerationV1,
)
from cold_storage.modules.layout.domain.composition_placement import (
    enumerate_composition_placements as enumerate_domain_composition_placements,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash

IDENTITY = "composition-placement-application@1.0.0"
SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class CompositionPlacementApplicationResultV1:
    identity: str
    schema_version: str
    source_zone_plan_hash: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    source_composition_enumeration_hash: str
    replayed_server_handoff_count: int
    caller_handoff_consumed: bool
    composition_replay_enforced: bool
    placements: CompositionPlacementEnumerationV1
    project_layout_validated_claimed: bool = False

    def __post_init__(self) -> None:
        if self.identity != IDENTITY or self.schema_version != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_COMPOSITION_PLACEMENT_APPLICATION_RESULT")
        if self.caller_handoff_consumed or not self.composition_replay_enforced:
            raise ValueError("COMPOSITION_PLACEMENT_REPLAY_SCOPE_VIOLATION")
        if self.project_layout_validated_claimed:
            raise ValueError("PROJECT_LAYOUT_VALIDATION_CLAIM_FORBIDDEN")

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "schema_version": self.schema_version,
            "source_zone_plan_hash": self.source_zone_plan_hash,
            "source_p1_handoff_hash": self.source_p1_handoff_hash,
            "source_site_geometry_hash": self.source_site_geometry_hash,
            "source_composition_enumeration_hash": self.source_composition_enumeration_hash,
            "replayed_server_handoff_count": self.replayed_server_handoff_count,
            "caller_handoff_consumed": self.caller_handoff_consumed,
            "composition_replay_enforced": self.composition_replay_enforced,
            "placements": self.placements.to_dict(),
            "project_layout_validated_claimed": self.project_layout_validated_claimed,
        }

    @property
    def canonical_result_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _validate_replayed_handoff(
    supplied: StructuralCompositionPlacementHandoffV1,
    expected: StructuralCompositionPlacementHandoffV1,
    *,
    source_zone_plan_hash: str,
    source_p1_handoff_hash: str,
    source_site_geometry_hash: str,
    dimension_authority_identity: str,
) -> None:
    """Strict replay guard used for server-selected and future reference inputs."""
    if not isinstance(supplied, StructuralCompositionPlacementHandoffV1):
        raise LayoutAuthorityError("COMPOSITION_HANDOFF_REPLAY_MISMATCH", field="type")
    expected_roles = {item.zone_role: item for item in expected.zone_role_assignment}
    if (
        supplied.composition_identity != expected.composition_identity
        or supplied.composition_signature != expected.composition_signature
        or supplied.family != expected.family
        or supplied.source_composition_hash != expected.source_composition_hash
        or supplied.source_zone_plan_hash != source_zone_plan_hash
        or supplied.source_p1_handoff_hash != source_p1_handoff_hash
        or supplied.source_site_geometry_hash != source_site_geometry_hash
        or supplied.dimension_authority_identity != dimension_authority_identity
    ):
        raise LayoutAuthorityError("COMPOSITION_HANDOFF_REPLAY_MISMATCH")
    for assignment in supplied.zone_role_assignment:
        expected_assignment = expected_roles.get(assignment.zone_role)
        if (
            expected_assignment is None
            or assignment.dimension_authority_ref != expected_assignment.dimension_authority_ref
            or assignment.dimension_authority_ref.authority_identity != dimension_authority_identity
            or assignment.dimension_authority_ref.source_p1_handoff_hash != source_p1_handoff_hash
        ):
            raise LayoutAuthorityError(
                "COMPOSITION_HANDOFF_REPLAY_MISMATCH",
                field=f"dimension_authority_ref:{assignment.zone_role}",
            )
    if canonical_hash(asdict(supplied)) != canonical_hash(asdict(expected)):
        raise LayoutAuthorityError("COMPOSITION_HANDOFF_REPLAY_MISMATCH")


def _assert_server_replay(
    enumeration: StructuralCompositionEnumerationResultV1,
    binding: LayoutAuthorityBindingV1,
) -> None:
    p1_body = binding.p1_body
    handoff_hash = binding.p1_handoff_hash
    zone_hash = binding.canonical_zone_plan_hash
    geometry_hash = binding.site_geometry_hash
    historical = p1_body["p1e_historical_handoff"]
    dimension_authority_identity = historical["dimension_handoff"]["calculator_identity"]
    for plan, handoff in zip(enumeration.compositions, enumeration.placement_handoffs, strict=True):
        expected_hash = canonical_hash(plan.to_dict())
        if (
            handoff.source_composition_hash != expected_hash
            or handoff.source_zone_plan_hash != zone_hash
            or handoff.source_p1_handoff_hash != handoff_hash
            or handoff.source_site_geometry_hash != geometry_hash
        ):
            raise LayoutAuthorityError("COMPOSITION_HANDOFF_REPLAY_MISMATCH")
        _validate_replayed_handoff(
            handoff,
            handoff,
            source_zone_plan_hash=zone_hash,
            source_p1_handoff_hash=handoff_hash,
            source_site_geometry_hash=geometry_hash,
            dimension_authority_identity=dimension_authority_identity,
        )


def enumerate_composition_placements(
    canonical_zone_plan: Mapping[str, Any],
    p1_handoff: ZoneDimensioningResultV1 | Mapping[str, Any],
    site_geometry: ValidatedSiteGeometryV1,
    *,
    node_budget: int = DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
) -> CompositionPlacementApplicationResultV1:
    """Replay composition authority server-side, then run the isolated exact engine.

    The public API accepts no composition handoff object.  Caller-supplied
    composition payloads therefore cannot become the placement engine input.
    """
    binding = bind_layout_authority(canonical_zone_plan, p1_handoff, site_geometry)
    composition_result = build_structural_compositions(
        canonical_zone_plan, p1_handoff, site_geometry
    )
    _assert_server_replay(composition_result, binding)
    site_body = site_geometry.to_dict()
    placements = enumerate_domain_composition_placements(
        composition_result.placement_handoffs,
        binding.dimension_authorities,
        site_body,
        source_zone_plan_hash=binding.canonical_zone_plan_hash,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=binding.site_geometry_hash,
        node_budget=node_budget,
    )
    return CompositionPlacementApplicationResultV1(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        source_zone_plan_hash=binding.canonical_zone_plan_hash,
        source_p1_handoff_hash=binding.p1_handoff_hash,
        source_site_geometry_hash=binding.site_geometry_hash,
        source_composition_enumeration_hash=composition_result.canonical_result_hash,
        replayed_server_handoff_count=len(composition_result.placement_handoffs),
        caller_handoff_consumed=False,
        composition_replay_enforced=True,
        placements=placements,
    )
