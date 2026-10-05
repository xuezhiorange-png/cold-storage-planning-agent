"""Access and Truck interface intent used only to organize exact placement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

IDENTITY = "access-critical-construction-intent@1.0.0"
SCHEMA_VERSION = "1.0.0"
VALIDATION_OWNER = "EXISTING_ACCESS_OR_TRUCK_AUTHORITY"


@dataclass(frozen=True)
class AccessCriticalInterfaceV1:
    """Frozen authority references plus a construction preference, never a result."""

    interface_kind: str
    requirement_identity: str
    from_ref: str
    to_ref: str
    flow_kind: str
    route_shape_constraint: str
    edge_orientation_requirement: str | None
    from_edge_class: str | None
    to_edge_class: str | None
    portal_clear_width_mm: int | None
    corridor_clear_width_mm: int | None
    construction_preference: str
    engineering_authority: bool = False
    validation_owner: str = VALIDATION_OWNER

    def __post_init__(self) -> None:
        if self.engineering_authority or self.validation_owner != VALIDATION_OWNER:
            raise ValueError("ACCESS_INTERFACE_AUTHORITY_CLAIM_FORBIDDEN")
        if not all(
            (
                self.interface_kind,
                self.requirement_identity,
                self.from_ref,
                self.to_ref,
                self.flow_kind,
                self.route_shape_constraint,
                self.construction_preference,
            )
        ):
            raise ValueError("ACCESS_INTERFACE_INTENT_INCOMPLETE")
        if any(
            value is not None and (type(value) is not int or value <= 0)
            for value in (self.portal_clear_width_mm, self.corridor_clear_width_mm)
        ):
            raise ValueError("ACCESS_INTERFACE_CLEAR_WIDTH_FACT_INVALID")


@dataclass(frozen=True)
class TruckDockPointEventV1:
    """Template-derived final dock point event for shipping construction ordering."""

    point_mm: tuple[int, int]
    truck_entrance_event_mm: tuple[int, int]
    template_identity: str
    template_rotation_deg: int

    def __post_init__(self) -> None:
        if (
            len(self.point_mm) != 2
            or len(self.truck_entrance_event_mm) != 2
            or any(
                type(value) is not int for value in (*self.point_mm, *self.truck_entrance_event_mm)
            )
        ):
            raise ValueError("TRUCK_DOCK_EVENT_POINT_INVALID")
        if self.template_rotation_deg not in (0, 90, 180, 270):
            raise ValueError("TRUCK_DOCK_EVENT_ROTATION_INVALID")
        if not self.template_identity:
            raise ValueError("TRUCK_DOCK_EVENT_TEMPLATE_REQUIRED")


@dataclass(frozen=True)
class AccessCriticalConstructionIntentV1:
    """Composition placement hints copied from bound authorities and site facts."""

    identity: str
    schema_version: str
    interfaces: tuple[AccessCriticalInterfaceV1, ...]
    main_entrance_segment_mm: tuple[tuple[int, int], tuple[int, int]]
    main_entrance_corridor_half_width_mm: int
    truck_entrance_segment_mm: tuple[tuple[int, int], tuple[int, int]]
    truck_dock_point_events: tuple[TruckDockPointEventV1, ...]
    preferred_role_face_order: tuple[tuple[str, tuple[str, ...]], ...]
    preferred_loading_side: str
    source_p1_handoff_hash: str
    source_site_geometry_hash: str
    engineering_authority: bool = False
    access_pass_claimed: bool = False
    truck_pass_claimed: bool = False
    validation_owner: str = VALIDATION_OWNER

    def __post_init__(self) -> None:
        if self.identity != IDENTITY or self.schema_version != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_ACCESS_CRITICAL_CONSTRUCTION_INTENT")
        if (
            self.engineering_authority
            or self.access_pass_claimed
            or self.truck_pass_claimed
            or self.validation_owner != VALIDATION_OWNER
        ):
            raise ValueError("ACCESS_CRITICAL_AUTHORITY_CLAIM_FORBIDDEN")
        kinds = tuple(item.interface_kind for item in self.interfaces)
        required = {
            "PERSONNEL_INGRESS_INTERFACE",
            "PACKAGING_SORTING_STRAIGHT_INTERFACE",
            "SECONDARY_SORTING_ACCESS_INTERFACE",
            "FROZEN_SORTING_ACCESS_INTERFACE",
            "SHIPPING_TRUCK_MANEUVER_INTERFACE",
        }
        if len(kinds) != len(required) or set(kinds) != required:
            raise ValueError("ACCESS_CRITICAL_INTERFACE_COVERAGE_INVALID")
        if not self.source_p1_handoff_hash or not self.source_site_geometry_hash:
            raise ValueError("ACCESS_CRITICAL_SOURCE_HASH_REQUIRED")
        if type(self.main_entrance_corridor_half_width_mm) is not int or (
            self.main_entrance_corridor_half_width_mm < 0
        ):
            raise ValueError("MAIN_ENTRANCE_CLEAR_WIDTH_FACT_INVALID")
        if not self.preferred_loading_side:
            raise ValueError("PREFERRED_LOADING_SIDE_REQUIRED")

    def interface(self, kind: str) -> AccessCriticalInterfaceV1:
        matches = tuple(item for item in self.interfaces if item.interface_kind == kind)
        if len(matches) != 1:
            raise ValueError("ACCESS_CRITICAL_INTERFACE_LOOKUP_INVALID")
        return matches[0]

    def face_order(self, role: str) -> tuple[str, ...]:
        return dict(self.preferred_role_face_order).get(role, ())

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "schema_version": self.schema_version,
            "interfaces": [asdict(item) for item in self.interfaces],
            "main_entrance_segment_mm": self.main_entrance_segment_mm,
            "main_entrance_corridor_half_width_mm": self.main_entrance_corridor_half_width_mm,
            "truck_entrance_segment_mm": self.truck_entrance_segment_mm,
            "truck_dock_point_events": [asdict(item) for item in self.truck_dock_point_events],
            "preferred_role_face_order": {
                role: list(faces) for role, faces in self.preferred_role_face_order
            },
            "preferred_loading_side": self.preferred_loading_side,
            "source_p1_handoff_hash": self.source_p1_handoff_hash,
            "source_site_geometry_hash": self.source_site_geometry_hash,
            "engineering_authority": self.engineering_authority,
            "access_pass_claimed": self.access_pass_claimed,
            "truck_pass_claimed": self.truck_pass_claimed,
            "validation_owner": self.validation_owner,
        }
