"""Owner-approved two-dimensional access profiles; no route or portal generation."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError

OWNER = "Charles:V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1"
PERSONNEL = "personnel-clear-envelope@1.0.0"
MATERIAL = "manual-pallet-jack-clear-envelope@1.0.0"
COLD_ROOM = "cold-room-material-portal@1.0.0"
PACKAGING = "packaging-sorting-straight-access@1.0.0"
TRUCK = "outdoor-truck-owner-input@1.0.0"


class AccessClassV1(StrEnum):
    PERSONNEL = "PERSONNEL"
    MATERIAL_LOGISTICS = "MATERIAL_LOGISTICS"
    TRUCK = "TRUCK"


@dataclass(frozen=True)
class PlanarAccessProfileV1:
    """Separate schema family from historical dimensioning.AccessProfileV1."""

    identity: str
    access_class: AccessClassV1
    transport_mode: str
    portal_clear_width_m: Decimal
    corridor_clear_width_m: Decimal
    route_shape_constraint: str
    source_authority: str = OWNER
    door_height_validation: bool = False


def approved_access_profiles() -> tuple[PlanarAccessProfileV1, ...]:
    """Server-owned registry. Predicates resolve identity, never trust caller profiles."""
    return (
        PlanarAccessProfileV1(
            PERSONNEL,
            AccessClassV1.PERSONNEL,
            "PEDESTRIAN",
            Decimal("1.5"),
            Decimal("2.0"),
            "NOT_FROZEN",
        ),
        PlanarAccessProfileV1(
            MATERIAL,
            AccessClassV1.MATERIAL_LOGISTICS,
            "MANUAL_PALLET_JACK",
            Decimal("2.4"),
            Decimal("2.5"),
            "NOT_FROZEN",
        ),
        PlanarAccessProfileV1(
            COLD_ROOM,
            AccessClassV1.MATERIAL_LOGISTICS,
            "MANUAL_PALLET_JACK",
            Decimal("2.4"),
            Decimal("2.5"),
            "NOT_FROZEN",
        ),
        PlanarAccessProfileV1(
            PACKAGING,
            AccessClassV1.MATERIAL_LOGISTICS,
            "MANUAL_PALLET_JACK",
            Decimal("2.4"),
            Decimal("5.0"),
            "STRAIGHT_ONLY",
        ),
    )


def resolve_access_profile(identity: str) -> PlanarAccessProfileV1:
    for profile in approved_access_profiles():
        if profile.identity == identity:
            return profile
    raise LayoutAuthorityError("ACCESS_PROFILE_REQUIRED", profile_identity=identity)


@dataclass(frozen=True)
class TruckAccessContractV1:
    """Required field names only: no approved vehicle numbers or envelope yet.

    None means unresolved, not zero, not inapplicable. No constructor path accepts
    proposed engineering values as reviewed Owner authority in this revision.
    """

    identity: str = TRUCK
    access_class: AccessClassV1 = AccessClassV1.TRUCK
    source_authority: str = OWNER
    outdoor_only: bool = True
    inside_building_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "vehicle_width_m": None,
            "vehicle_length_m": None,
            "turning_envelope": None,
            "straight_approach": None,
            "loading_operation_clearance": None,
            "engineering_values_complete": False,
            "missing_owner_inputs": list(TRUCK_REQUIRED_FIELDS),
            "status": "OWNER_INPUT_REQUIRED",
        }


TRUCK_REQUIRED_FIELDS = (
    "vehicle_width_m",
    "vehicle_length_m",
    "turning_envelope",
    "straight_approach",
    "loading_operation_clearance",
)


@dataclass(frozen=True)
class AccessRequirementV1:
    identity: str
    from_ref: str
    to_ref: str
    flow_kind: str
    access_class: AccessClassV1
    profile_identity: str
    portal_required: bool
    corridor_allowed: bool
    direct_allowed: bool
    route_shape_constraint: str
    edge_orientation_requirement: str | None = None
    cold_room_refs: tuple[str, ...] = ()
    cold_room_portal_profile_identity: str | None = None
    source_authority: str = OWNER

    def __post_init__(self) -> None:
        if not self.from_ref or not self.to_ref or self.from_ref == self.to_ref:
            raise LayoutAuthorityError("INVALID_ACCESS_BINDING")
        if self.access_class == AccessClassV1.TRUCK:
            if self.profile_identity != TRUCK:
                raise LayoutAuthorityError("INVALID_ACCESS_BINDING")
        else:
            profile = resolve_access_profile(self.profile_identity)
            if (
                profile.access_class != self.access_class
                or profile.route_shape_constraint != self.route_shape_constraint
            ):
                raise LayoutAuthorityError("INVALID_ACCESS_BINDING")
        if bool(self.cold_room_refs) != (self.cold_room_portal_profile_identity == COLD_ROOM):
            raise LayoutAuthorityError("INVALID_COLD_ROOM_PORTAL_BINDING")


def personnel_truck_policy() -> dict[str, Any]:
    return {
        "identity": "personnel-truck-separation@1.0.0",
        "source_authority": OWNER,
        "separation": "PREFERRED",
        "shared_route_allowed": False,
        "crossing_allowed_if_necessary": True,
        "crossing_requires_review": True,
        "crossing_warning": "PERSONNEL_TRUCK_CROSSING_REQUIRES_ENGINEERING_REVIEW",
    }
