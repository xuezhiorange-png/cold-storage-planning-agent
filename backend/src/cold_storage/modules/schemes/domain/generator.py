"""Scheme generator — deterministic, pure domain logic, no side effects.

Zone processing is preceded by a stable sort so that input ordering
never affects the output.
"""

from __future__ import annotations

from decimal import Decimal

from cold_storage.modules.schemes.domain.errors import (
    InvalidProfileError,
    InvalidProfileParameterError,
    MissingProfileParameterError,
)
from cold_storage.modules.schemes.domain.models import (
    SchemeCandidate,
    SchemeGenerationInput,
    SchemeProfile,
    SchemeRoomModule,
    ZoneResult,
)

GENERATOR_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Explicit process-compatibility merge matrix
# ---------------------------------------------------------------------------
# Two zones may be merged only when their (process_a, process_b) pair
# is explicitly listed here AND the pair has the same entry in both
# directions (symmetric).  Absence from this matrix means "cannot merge".

PROCESS_COMPATIBILITY_MATRIX: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"general"}),
        frozenset({"general", "raw"}),
        frozenset({"general", "finished"}),
        frozenset({"general", "processing"}),
        frozenset({"raw"}),
        frozenset({"finished"}),
        frozenset({"processing"}),
        # raw + finished → explicitly FORBIDDEN (food safety)
        # raw + processing → explicitly FORBIDDEN unless added here
    }
)


def _processes_compatible(a: str, b: str) -> bool:
    """Return True if two process-compatibility labels may co-exist."""
    if a == b:
        return True
    return frozenset({a, b}) in PROCESS_COMPATIBILITY_MATRIX


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Stable sort for zones
# ---------------------------------------------------------------------------


def _sort_zones(zones: list[ZoneResult]) -> list[ZoneResult]:
    """Return a new list sorted deterministically by
    (temperature_level, hygiene_zone, process_compatibility, zone_code)."""
    return sorted(
        zones,
        key=lambda z: (
            z.temperature_level,
            z.hygiene_zone or "",
            z.process_compatibility or "",
            z.zone_code,
        ),
    )


# ---------------------------------------------------------------------------
# Profile parameter handling
# ---------------------------------------------------------------------------


def get_profile(code: str, parameters: dict[str, object] | None = None) -> SchemeProfile:
    """Return a profile with parameters applied.

    For ``segmented_small_rooms`` at least one of ``max_positions_per_room``
    or ``max_area_per_room_m2`` must be provided and > 0.
    """
    base = BUILTIN_PROFILES.get(code)
    if base is None:
        raise InvalidProfileError(code, f"Unknown profile code '{code}'")

    params = parameters or {}

    if code == "segmented_small_rooms":
        has_pos = "max_positions_per_room" in params
        has_area = "max_area_per_room_m2" in params
        if not has_pos and not has_area:
            raise MissingProfileParameterError(
                code, "max_positions_per_room or max_area_per_room_m2"
            )

    raw_pos = params.get("max_positions_per_room", base.max_positions_per_room)
    raw_area = params.get("max_area_per_room_m2", base.max_area_per_room_m2)
    raw_mods = params.get("minimum_room_modules", base.minimum_room_modules)

    max_pos = int(str(raw_pos)) if raw_pos is not None else base.max_positions_per_room
    max_area = Decimal(str(raw_area)) if raw_area is not None else base.max_area_per_room_m2
    min_modules = int(str(raw_mods)) if raw_mods is not None else base.minimum_room_modules

    if max_pos < 0:
        raise InvalidProfileParameterError(
            code, "max_positions_per_room", f"must be >= 0, got {max_pos}"
        )
    if max_area < 0:
        raise InvalidProfileParameterError(
            code, "max_area_per_room_m2", f"must be >= 0, got {max_area}"
        )

    # For segmented: at least one threshold must be > 0
    if code == "segmented_small_rooms" and max_pos <= 0 and max_area <= 0:
        raise InvalidProfileParameterError(
            code,
            "max_positions_per_room/max_area_per_room_m2",
            "at least one must be > 0",
        )

    return SchemeProfile(
        code=base.code,
        name=base.name,
        revision=base.revision,
        description=base.description,
        grouping_strategy=base.grouping_strategy,
        splitting_strategy=base.splitting_strategy,
        max_positions_per_room=max_pos,
        max_area_per_room_m2=max_area,
        minimum_room_modules=min_modules,
        door_strategy=base.door_strategy,
        redundancy_strategy=base.redundancy_strategy,
        source_type=base.source_type,
        revision_status=base.revision_status,
        requires_review=base.requires_review,
    )


# ---------------------------------------------------------------------------
# Room construction helpers
# ---------------------------------------------------------------------------


def _D(val: str | int | float) -> Decimal:
    return Decimal(str(val))


def _zone_to_room(
    z: ZoneResult,
    room_code: str,
    room_name: str,
    area_share: Decimal = Decimal("1"),
) -> SchemeRoomModule:  # noqa: C901
    """Convert a single zone into a room module (values will be scaled later)."""
    area = z.area_m2 * area_share
    return SchemeRoomModule(
        room_code=room_code,
        room_name=room_name,
        zone_codes=[z.zone_code],  # original zone codes as a list
        temperature_level=z.temperature_level,
        area_m2=area,
        position_count=z.position_count,
        storage_capacity_kg=z.storage_capacity_kg * area_share,
        design_cooling_load_kw_r=Decimal("0"),  # distributed proportionally
        compressor_operating_capacity_kw_r=Decimal("0"),
        compressor_installed_capacity_kw_r=Decimal("0"),
        process_compatibility=z.process_compatibility,
        hygiene_zone=z.hygiene_zone,
        door_count=1,
        partition_length_proxy_m=Decimal(str(area)).sqrt() * 2 if area > 0 else Decimal("0"),
    )


def _compute_energy_proportional(
    room: SchemeRoomModule,
    total_area: Decimal,
    input_data: SchemeGenerationInput,
) -> SchemeRoomModule:
    """Distribute cooling/power proportionally by area."""
    if total_area <= 0:
        return room
    ratio = room.area_m2 / total_area
    er = input_data.equipment_result
    cl = input_data.cooling_load_result
    return SchemeRoomModule(
        room_code=room.room_code,
        room_name=room.room_name,
        zone_codes=room.zone_codes,
        temperature_level=room.temperature_level,
        area_m2=room.area_m2,
        position_count=room.position_count,
        storage_capacity_kg=room.storage_capacity_kg,
        design_cooling_load_kw_r=cl.design_cooling_load_kw_r * ratio,
        compressor_operating_capacity_kw_r=er.compressor_operating_capacity_kw_r * ratio,
        compressor_installed_capacity_kw_r=(
            er.compressor_installed_capacity_kw_r * ratio
            if er.compressor_installed_capacity_kw_r is not None
            else room.compressor_installed_capacity_kw_r
        ),
        process_compatibility=room.process_compatibility,
        hygiene_zone=room.hygiene_zone,
        door_count=room.door_count,
        partition_length_proxy_m=room.partition_length_proxy_m,
    )


# ---------------------------------------------------------------------------
# Merge compatibility
# ---------------------------------------------------------------------------


def _validate_merge_compatibility(zones: list[ZoneResult]) -> bool:
    """Check if zones can be merged (same temp, compatible process, same hygiene).

    P0-5: When any zone has process_compatibility=None or hygiene_zone=None,
    the corresponding check is skipped.
    """
    if len(zones) <= 1:
        return True
    temps = set(z.temperature_level for z in zones)
    if len(temps) > 1:
        return False
    # Check pairwise process compatibility via matrix (skip if any is None)
    processes = [z.process_compatibility for z in zones if z.process_compatibility is not None]
    for i in range(len(processes)):
        for j in range(i + 1, len(processes)):
            if not _processes_compatible(processes[i], processes[j]):
                return False
    # Check hygiene (skip if any is None)
    hygiene = set(z.hygiene_zone for z in zones if z.hygiene_zone is not None)
    return len(hygiene) <= 1


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def generate_balanced(
    input_data: SchemeGenerationInput,
    profile: SchemeProfile,
) -> SchemeCandidate:
    """Generate the balanced (baseline) scheme — one room per zone."""
    zones = _sort_zones(input_data.zone_results)
    total_area: Decimal = sum((z.area_m2 for z in zones), Decimal("0"))

    rooms: list[SchemeRoomModule] = []
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
    """Generate consolidated large rooms — merge compatible zones.

    zone_codes in each room stores the **original** zone codes as a list.
    The synthetic merged code is only used for room_code / room_name.
    """
    zones = _sort_zones(input_data.zone_results)
    total_area = sum((z.area_m2 for z in zones), Decimal("0"))

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

    rooms: list[SchemeRoomModule] = []
    for i, grp in enumerate(groups):
        # Compute totals for the merged room
        merged_area = sum((z.area_m2 for z in grp), Decimal("0"))
        merged_positions = sum(z.position_count for z in grp)
        merged_capacity = sum((z.storage_capacity_kg for z in grp), Decimal("0"))

        # Original zone codes stored as a list
        original_codes = [z.zone_code for z in grp]

        # Synthetic code for room_code / display only
        "+".join(z.zone_code for z in grp)
        synthetic_name = "/".join(z.zone_name for z in grp)

        room = SchemeRoomModule(
            room_code=f"CON-{i + 1:03d}",
            room_name=f"大冷间-{synthetic_name}",
            zone_codes=original_codes,  # <-- original codes, not synthetic
            temperature_level=grp[0].temperature_level,
            area_m2=merged_area,
            position_count=merged_positions,
            storage_capacity_kg=merged_capacity,
            design_cooling_load_kw_r=Decimal("0"),
            compressor_operating_capacity_kw_r=Decimal("0"),
            compressor_installed_capacity_kw_r=Decimal("0"),
            process_compatibility=grp[0].process_compatibility,
            hygiene_zone=grp[0].hygiene_zone,
            door_count=1,
            partition_length_proxy_m=merged_area.sqrt() * 2 if merged_area > 0 else Decimal("0"),
        )
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
    zones = _sort_zones(input_data.zone_results)
    total_area = sum((z.area_m2 for z in zones), Decimal("0"))

    rooms: list[SchemeRoomModule] = []
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
            split_parts = max(
                split_parts,
                -(-int(z.area_m2) // int(profile.max_area_per_room_m2)),
            )

        if not needs_split:
            room = _zone_to_room(z, f"SEG-{room_idx + 1:03d}", f"小冷间-{z.zone_name}")
            room = _compute_energy_proportional(room, total_area, input_data)
            rooms.append(room)
            room_idx += 1
        else:
            for part in range(split_parts):
                room_idx += 1
                frac = Decimal("1") / Decimal(str(split_parts))
                sub_area = z.area_m2 * frac
                sub_capacity = z.storage_capacity_kg * frac
                # Distribute positions evenly, remainder to first parts
                base_pos = z.position_count // split_parts
                remainder = z.position_count % split_parts
                sub_positions = base_pos + (1 if part < remainder else 0)

                sub_zone = ZoneResult(
                    zone_code=f"{z.zone_code}-S{part + 1}",
                    zone_name=f"{z.zone_name}-段{part + 1}",
                    temperature_level=z.temperature_level,
                    area_m2=sub_area,
                    position_count=sub_positions,
                    storage_capacity_kg=sub_capacity,
                    process_compatibility=z.process_compatibility,
                    hygiene_zone=z.hygiene_zone,
                )
                room = _zone_to_room(
                    sub_zone,
                    f"SEG-{room_idx:03d}",
                    f"小冷间-{z.zone_name}-段{part + 1}",
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


# ---------------------------------------------------------------------------
# Candidate builder
# ---------------------------------------------------------------------------


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
    total_area = sum((r.area_m2 for r in rooms), Decimal("0"))
    total_positions = sum(r.position_count for r in rooms)
    total_doors = sum(r.door_count for r in rooms)
    total_partition = sum((r.partition_length_proxy_m for r in rooms), Decimal("0"))
    total_cooling = sum((r.design_cooling_load_kw_r for r in rooms), Decimal("0"))
    total_compressor_installed = sum(
        (r.compressor_installed_capacity_kw_r for r in rooms), Decimal("0")
    )
    total_compressor_operating = sum(
        (r.compressor_operating_capacity_kw_r for r in rooms), Decimal("0")
    )

    # Zone assignments — map each original zone_code to its room(s)
    zone_assignments: dict[str, list[str]] = {}
    for r in rooms:
        for zc in r.zone_codes:
            zone_assignments.setdefault(zc, []).append(r.room_code)

    daily_throughput = input_data.total_daily_throughput_kg_day
    investment = input_data.investment_result.total_investment_cny

    # Power authority: use PowerResult for installed_power_kw_e, NOT EquipmentResult
    if input_data.power_result is not None:
        power_kw_e = input_data.power_result.total_installed_power_kw_e
    else:
        # Fail-closed: if power_result is missing, use 0 (validation will fail)
        power_kw_e = Decimal("0")

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
        installed_power_kw_e=power_kw_e,
        design_cooling_load_kw_r=total_cooling,
        compressor_operating_capacity_kw_r=total_compressor_operating,
        compressor_installed_capacity_kw_r=total_compressor_installed,
        compressor_standby_capacity_kw_r=(
            input_data.equipment_result.compressor_standby_capacity_kw_r
        ),
        condenser_heat_rejection_kw=input_data.equipment_result.condenser_heat_rejection_kw,
        metrics=[],
        assumptions=assumptions,
        warnings=[],
        requires_review=requires_review,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_GENERATORS = {
    "balanced": generate_balanced,
    "consolidated_large_rooms": generate_consolidated,
    "segmented_small_rooms": generate_segmented,
}


def generate_schemes(input_data: SchemeGenerationInput) -> list[SchemeCandidate]:
    """Generate scheme candidates for all requested profiles."""
    candidates: list[SchemeCandidate] = []
    for code in input_data.profile_codes:
        gen = _GENERATORS.get(code)
        if gen is None:
            raise InvalidProfileError(code, f"Unknown profile code '{code}'")
        params = input_data.profile_parameters.get(code)
        profile = get_profile(code, params)
        candidate = gen(input_data, profile)
        candidates.append(candidate)
    return candidates
