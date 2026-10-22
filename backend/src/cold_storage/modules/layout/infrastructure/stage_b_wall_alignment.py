"""Stage-B-only soft construction guidance; no topology pruning or acceptance.

Every auxiliary variable is an exact, total definition of existing physical
coordinates. Clearing the objective projects onto exactly the original domain.
The enclosing span is a search proxy, NEVER the actual Building Footprint.
"""

from collections.abc import Callable, Mapping
from itertools import combinations
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError, canonical_hash

POLICY = "stage-b-wall-coordinate-coherence-and-span@1.0.0"
POLICY_HASH = canonical_hash(
    {
        "version": POLICY,
        "metric": "SUM_NEAREST_OTHER_ROOM_PARALLEL_WALL_OFFSETS_PLUS_XY_ROOM_SPANS_MM",
        "coefficients": "UNIT_COEFFICIENTS_SAME_MM_UNITS",
        "hard_threshold": None,
        "topology_pruning": False,
        "first_solution_termination": "UNCHANGED",
    }
)


def apply_wall_alignment_guidance(
    model: Any, *, charge: Callable[[str, int], None]
) -> dict[str, Any]:
    """Prefer coherent wall lines without eliminating any physical assignment.

    Model room maps contain post-rotation x/y/w/d, not nominal dimensions.
    Absolute coordinate-domain extrema bound ALL differences and spans, even
    with negative origins. No site bbox filling, snapping, tolerance or aspect
    gate is introduced. An existing objective must not be overwritten.
    """
    m = model.m
    if m.has_objective():
        raise LayoutAuthorityError("STAGE_B_WALL_GUIDANCE_OBJECTIVE_ALREADY_PRESENT")
    rooms: Mapping[str, Any] = model.rooms
    if len(rooms) < 2:
        raise LayoutAuthorityError("STAGE_B_WALL_GUIDANCE_GEOMETRY_REQUIRED")
    charge("STAGE_B_WALL_GUIDANCE_INPUT", len(rooms) * 4)
    bound = 1
    for role in sorted(rooms):
        for key in ("x", "y", "w", "d"):
            value = rooms[role][key]
            if isinstance(value, int):
                bound += abs(value)
            else:
                domain = list(value.proto.domain)
                if not domain:
                    raise LayoutAuthorityError("STAGE_B_WALL_GUIDANCE_EMPTY_DOMAIN")
                bound += max(abs(domain[0]), abs(domain[-1]))
    terms = []
    for axis, size in (("x", "w"), ("y", "d")):
        before = len(m.proto.variables) + len(m.proto.constraints)
        # Two parallel wall coordinates per room; candidate ordering is stable.
        walls = [
            (role, rooms[role][axis] + (rooms[role][size] if far else 0))
            for role in sorted(rooms)
            for far in (False, True)
        ]
        offsets: dict[int, list[Any]] = {i: [] for i in range(len(walls))}
        for i, j in combinations(range(len(walls)), 2):
            if walls[i][0] == walls[j][0]:
                continue  # A room's own two walls cannot count as its alignment.
            distance = m.new_int_var(0, bound, f"stage_b_wall_{axis}_{i}_{j}")
            m.add_abs_equality(distance, walls[i][1] - walls[j][1])
            offsets[i].append(distance)
            offsets[j].append(distance)
        for i in range(len(walls)):
            nearest = m.new_int_var(0, bound, f"stage_b_wall_nearest_{axis}_{i}")
            m.add_min_equality(nearest, offsets[i])
            terms.append(nearest)
        low = m.new_int_var(-bound, bound, "stage_b_wall_low_" + axis)
        high = m.new_int_var(-bound, bound, "stage_b_wall_high_" + axis)
        m.add_min_equality(low, [wall[1] for wall in walls])
        m.add_max_equality(high, [wall[1] for wall in walls])
        terms.append(high - low)
        charge(
            "STAGE_B_WALL_GUIDANCE_DEFINITIONS",
            len(m.proto.variables) + len(m.proto.constraints) - before,
        )
    m.minimize(sum(terms))
    charge("STAGE_B_WALL_GUIDANCE_OBJECTIVE", 1)
    return {
        "policy": POLICY,
        "policy_hash": POLICY_HASH,
        "proxy": "NEAREST_PARALLEL_WALL_OFFSETS_PLUS_ROOM_SPANS_MM",
        "term_count": len(terms),
        "hard_domain_changed": False,
        "topology_pruning": False,
        "room_hole_repairability": "NOT_PROVEN_NO_PRUNING",
        "formal_quality_gate": False,
        "process_flow_validated": False,
        "layout_regularity_validated": False,
        "real_layout_quality_improved": False,
    }
