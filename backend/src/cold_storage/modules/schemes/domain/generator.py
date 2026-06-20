"""Scheme generator — deterministic, pure domain logic, no side effects."""

from __future__ import annotations

from typing import Any

from cold_storage.modules.schemes.domain.errors import (
    InvalidProfileError,
)
from cold_storage.modules.schemes.domain.models import (
    SchemeCandidate,
    SchemeGenerationInput,
    SchemeProfile,
    SchemeRoomModule,
    ZoneResult,
)

GENERATOR_VERSION = "1.0.0"

# Built-in profiles
BALANCED = SchemeProfile(
    code="balanced",
    name="平衡方案",
    grouping_strategy="baseline",
    splitting_strategy="none",
    description="Task 4 baseline — preserves zone planning as-is",
)

CONSOLIDATED = SchemeProfile(
    code="consolidated_large_rooms",
    name="大冷间方案",
    grouping_strategy="merge_compatible",
    splitting_strategy="none",
    description="Merge compatible zones to reduce room count",
    requires_review=True,
)

SEGMENTED = SchemeProfile(
    code="segmented_small_rooms",
    name="小冷间方案",
    grouping_strategy="baseline",
    splitting_strategy="modular_split",
    description="Split oversized zones into modular rooms",
)

BUILTIN_PROFILES: dict[str, SchemeProfile] = {
    p.code: p for p in [BALANCED, CONSOLIDATED, SEGMENTED]
}


def get_profile(code: str, parameters: dict[str, object] | None = None) -> SchemeProfile:
    """Return a profile with parameters applied."""
    base = BUILTIN_PROFILES.get(code)
    if base is None:
        raise InvalidProfileError(code, f"Unknown profile code '{code}'")

    params = parameters or {}
    raw_pos = params.get("max_positions_per_room", base.max_positions_per_room)
    raw_area = params.get("max_area_per_room_m2", base.max_area_per_room_m2)
    raw_mods = params.get("minimum_room_modules", base.minimum_room_modules)
    max_pos = int(str(raw_pos)) if raw_pos is not None else base.max_positions_per_room
    max_area = float(str(raw_area)) if raw_area is not None else base.max_area_per_room_m2
    min_modules = int(str(raw_mods)) if raw_mods is not None else base.minimum_room_modules

    if max_pos < 0:
        raise InvalidProfileError(code, f"Invalid max_positions_per_room: {max_pos}")
    if max_area < 0:
        raise InvalidProfileError(code, f"Invalid max_area_per_room_m2: {max_area}")

    return SchemeProfile(
        code=base.code,
        name=base.name,
        revision=base.revision,
        description=base.description,
        grouping_strategy=base.grouping_strategy,
        splitting_strategy=base.splitting_strategy,
        max_positions_per_room=int(max_pos),
        max_area_per_room_m2=max_area,
        minimum_room_modules=min_modules,
        door_strategy=base.door_strategy,
        redundancy_strategy=base.redundancy_strategy,
        source_type=base.source_type,
        revision_status=base.revision_status,
        requires_review=base.requires_review,
    )


def _zone_to_room(z: ZoneResult, room_code: str, room_name: str) -> SchemeRoomModule:
    """Convert a single zone into a room module."""
    return SchemeRoomModule(
        room_code=room_code,
        room_name=room_name,
        zone_codes=[z.zone_code],
        temperature_level=z.temperature_level,
        area_m2=z.area_m2,
        position_count=z.position_count,
        storage_capacity_kg=z.storage_capacity_kg,
        design_cooling_load_kw_r=0.0,  # distributed proportionally
        compressor_installed_capacity_kw_r=0.0,
        process_compatibility=z.process_compatibility,
        hygiene_zone=z.hygiene_zone,
        door_count=1,
        partition_length_proxy_m=z.area_m2**0.5 * 2,  # proxy: sqrt(area) * 2
    )


def _compute_energy_proportional(
    room: SchemeRoomModule, total_area: float, input_data: SchemeGenerationInput
) -> SchemeRoomModule:
    """Distribute cooling/power proportionally by area."""
    if total_area <= 0:
        return room
    ratio = room.area_m2 / total_area
    return SchemeRoomModule(
        room_code=room.room_code,
        room_name=room.room_name,
        zone_codes=room.zone_codes,
        temperature_level=room.temperature_level,
        area_m2=room.area_m2,
        position_count=room.position_count,
        storage_capacity_kg=room.storage_capacity_kg,
        design_cooling_load_kw_r=input_data.cooling_load_result.design_cooling_load_kw_r * ratio,
        compressor_installed_capacity_kw_r=input_data.equipment_result.compressor_installed_capacity_kw_r
        * ratio,
        process_compatibility=room.process_compatibility,
        hygiene_zone=room.hygiene_zone,
        door_count=room.door_count,
        partition_length_proxy_m=room.partition_length_proxy_m,
    )


def _validate_merge_compatibility(zones: list[ZoneResult]) -> bool:
    """Check if zones can be merged (same temp, compatible process, same hygiene)."""
    if len(zones) <= 1:
        return True
    temps = set(z.temperature_level for z in zones)
    if len(temps) > 1:
        return False
    compatibilities = set(z.process_compatibility for z in zones)
    if "raw" in compatibilities and "finished" in compatibilities:
        return False
    hygiene = set(z.hygiene_zone for z in zones)
    return len(hygiene) <= 1


def generate_balanced(
    input_data: SchemeGenerationInput,
    profile: SchemeProfile,
) -> SchemeCandidate:
    """Generate the balanced (baseline) scheme — one room per zone."""
    zones = input_data.zone_results
    total_area = sum(z.area_m2 for z in zones)

    rooms = []
    for i, z in enumerate(zones):
        room = _zone_to_room(z, f"BAL-{i + 1:03d}", f"平衡-{z.zone_name}")
        room = _compute_energy_proportional(room, total_area, input_data)
        rooms.append(room)

    return _build_candidate(
        scheme_code="balanced",
        scheme_name="平衡方案",
        profile_code="balanced",
        rooms=rooms,
        input_data=input_data,
        assumptions=["Task 4 baseline preserved — one room per zone"],
    )


def generate_consolidated(
    input_data: SchemeGenerationInput,
    profile: SchemeProfile,
) -> SchemeCandidate:
    """Generate consolidated large rooms — merge compatible zones."""
    zones = input_data.zone_results
    total_area = sum(z.area_m2 for z in zones)

    # Group zones by temperature level, then check compatibility
    groups: list[list[ZoneResult]] = []
    remaining = list(zones)

    while remaining:
        z = remaining[0]
        group = [z]
        remaining = remaining[1:]
        merged = True
        while merged:
            merged = False
            for other in list(remaining):
                if _validate_merge_compatibility(group + [other]):
                    group.append(other)
                    remaining.remove(other)
                    merged = True
                    break
        groups.append(group)

    rooms = []
    for i, grp in enumerate(groups):
        merged_zone = ZoneResult(
            zone_code="+".join(z.zone_code for z in grp),
            zone_name="/".join(z.zone_name for z in grp),
            temperature_level=grp[0].temperature_level,
            area_m2=sum(z.area_m2 for z in grp),
            position_count=sum(z.position_count for z in grp),
            storage_capacity_kg=sum(z.storage_capacity_kg for z in grp),
            process_compatibility=grp[0].process_compatibility,
            hygiene_zone=grp[0].hygiene_zone,
        )
        room = _zone_to_room(merged_zone, f"CON-{i + 1:03d}", f"大冷间-{i + 1}")
        room = _compute_energy_proportional(room, total_area, input_data)
        rooms.append(room)

    return _build_candidate(
        scheme_code="consolidated_large_rooms",
        scheme_name="大冷间方案",
        profile_code="consolidated_large_rooms",
        rooms=rooms,
        input_data=input_data,
        assumptions=["Compatible zones merged — requires review for total layout"],
        requires_review=True,
    )


def generate_segmented(
    input_data: SchemeGenerationInput,
    profile: SchemeProfile,
) -> SchemeCandidate:
    """Generate segmented small rooms — split oversized zones."""
    zones = input_data.zone_results
    total_area = sum(z.area_m2 for z in zones)

    rooms = []
    room_idx = 0
    for z in zones:
        needs_split = False
        split_parts = 1

        if profile.max_positions_per_room > 0 and z.position_count > profile.max_positions_per_room:
            needs_split = True
            split_parts = max(
                split_parts, -(-z.position_count // profile.max_positions_per_room)
            )  # ceil div
        if profile.max_area_per_room_m2 > 0 and z.area_m2 > profile.max_area_per_room_m2:
            needs_split = True
            split_parts = max(split_parts, -(-int(z.area_m2) // int(profile.max_area_per_room_m2)))

        if not needs_split:
            room = _zone_to_room(z, f"SEG-{room_idx + 1:03d}", f"小冷间-{z.zone_name}")
            room = _compute_energy_proportional(room, total_area, input_data)
            rooms.append(room)
            room_idx += 1
        else:
            for part in range(split_parts):
                room_idx += 1
                frac = 1.0 / split_parts
                sub_zone = ZoneResult(
                    zone_code=f"{z.zone_code}-S{part + 1}",
                    zone_name=f"{z.zone_name}-段{part + 1}",
                    temperature_level=z.temperature_level,
                    area_m2=z.area_m2 * frac,
                    position_count=z.position_count // split_parts
                    + (1 if part < z.position_count % split_parts else 0),
                    storage_capacity_kg=z.storage_capacity_kg * frac,
                    process_compatibility=z.process_compatibility,
                    hygiene_zone=z.hygiene_zone,
                )
                room = _zone_to_room(
                    sub_zone, f"SEG-{room_idx:03d}", f"小冷间-{z.zone_name}-段{part + 1}"
                )
                room = _compute_energy_proportional(room, total_area, input_data)
                rooms.append(room)

    return _build_candidate(
        scheme_code="segmented_small_rooms",
        scheme_name="小冷间方案",
        profile_code="segmented_small_rooms",
        rooms=rooms,
        input_data=input_data,
        assumptions=[
            f"max_positions_per_room={profile.max_positions_per_room}",
            f"max_area_per_room_m2={profile.max_area_per_room_m2}",
        ],
    )


def _build_candidate(
    scheme_code: str,
    scheme_name: str,
    profile_code: str,
    rooms: list[SchemeRoomModule],
    input_data: SchemeGenerationInput,
    assumptions: list[str],
    requires_review: bool = False,
) -> SchemeCandidate:
    """Build a SchemeCandidate from a list of rooms."""
    total_area = sum(r.area_m2 for r in rooms)
    total_positions = sum(r.position_count for r in rooms)
    total_doors = sum(r.door_count for r in rooms)
    total_partition = sum(r.partition_length_proxy_m for r in rooms)
    total_cooling = sum(r.design_cooling_load_kw_r for r in rooms)
    total_compressor = sum(r.compressor_installed_capacity_kw_r for r in rooms)

    # Zone assignments
    zone_assignments: dict[str, list[str]] = {}
    for r in rooms:
        for zc in r.zone_codes:
            zone_assignments.setdefault(zc, []).append(r.room_code)

    # Compute derived metrics
    daily_throughput = input_data.total_daily_throughput_kg_day
    investment = input_data.investment_result.total_investment_cny

    return SchemeCandidate(
        scheme_code=scheme_code,
        scheme_name=scheme_name,
        profile_code=profile_code,
        feasible=True,  # set by validation later
        constraint_results=[],
        room_modules=rooms,
        zone_assignments=zone_assignments,
        total_area_m2=total_area,
        total_position_count=total_positions,
        room_module_count=len(rooms),
        door_count=total_doors,
        partition_length_proxy_m=total_partition,
        daily_throughput_kg_day=daily_throughput,
        investment_cny=investment,
        installed_power_kw_e=input_data.equipment_result.installed_power_kw_e,
        design_cooling_load_kw_r=total_cooling,
        compressor_installed_capacity_kw_r=total_compressor,
        condenser_heat_rejection_kw=input_data.equipment_result.condenser_heat_rejection_kw,
        metrics=[],
        assumptions=assumptions,
        warnings=[],
        requires_review=requires_review,
    )


def _get_generator(code: str) -> Any:  # noqa: C901
    """Return the generator function for a profile code."""
    if code == "balanced":
        return generate_balanced
    if code == "consolidated_large_rooms":
        return generate_consolidated
    if code == "segmented_small_rooms":
        return generate_segmented
    return None


def generate_schemes(
    input_data: SchemeGenerationInput,
) -> list[SchemeCandidate]:
    """Generate all requested scheme candidates."""
    candidates = []
    for code in input_data.profile_codes:
        gen = _get_generator(code)
        if gen is None:
            raise InvalidProfileError(code, f"No generator for profile '{code}'")
        params = input_data.profile_parameters.get(code, {})
        profile = get_profile(code, params)
        candidate = gen(input_data, profile)
        candidates.append(candidate)
    return candidates
