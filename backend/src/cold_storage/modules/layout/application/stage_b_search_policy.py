"""Opt-in bounded coverage schedule; no execution grant or new allowance."""

from types import MappingProxyType

from cold_storage.modules.layout.domain.construction_branch_diversity import POLICY as DIVERSITY
from cold_storage.modules.layout.domain.dimensioning import canonical_hash

POLICY = MappingProxyType(
    {
        "version": "stage-b-fair-coverage-union-witness@1.0.0",
        "handoff_order": "UNCHANGED_SIX_SERVER_DERIVED",
        "native_share": "REMAINING_POOL_RESERVATION_DIVIDED_BY_REMAINING_HANDOFFS",
        "work_share": "REMAINING_600000_RESERVATION_DIVIDED_BY_REMAINING_HANDOFFS",
        "elapsed_share": "REMAINING_85_SECOND_RESERVATION_DIVIDED_BY_REMAINING_HANDOFFS",
        "checked_share": "FLOOR_REMAINING_20_DIVIDED_BY_REMAINING_HANDOFFS_MIN_ONE_IF_AVAILABLE",
        "warmup_call_cap": "ONE_EIGHTH_OF_HANDOFF_NATIVE_SHARE",
        "second_composition_begin": False,
        "unused_share": "DETERMINISTIC_FORWARD_CARRY_ONLY",
        "diversity": DIVERSITY,
        "topology_cut": "EXACT_EXPORTED_UNION_INPUT_EQUIVALENCE@1.0.0",
    }
)
POLICY_HASH = canonical_hash(dict(POLICY))


def schedule_hash(original_hash: str) -> str:
    return canonical_hash(
        {"server_schedule_hash": original_hash, "search_policy_hash": POLICY_HASH}
    )
