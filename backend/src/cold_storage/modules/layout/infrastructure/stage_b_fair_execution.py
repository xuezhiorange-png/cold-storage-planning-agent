"""New fixed fair experiment binding on the unchanged durable PoolLease."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.application.stage_b_search_policy import POLICY_HASH, schedule_hash
from cold_storage.modules.layout.domain.construction_branch_diversity import POLICY as V2_POLICY
from cold_storage.modules.layout.domain.construction_diversity import POLICY as V1_POLICY
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_b_multi_solution import POLICY as ENUMERATION
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolExecutionStore

FAIR_ENUMERATION_CONTRACT = MappingProxyType(
    {
        "version": "STAGE_B_REAL_FAIR_MULTI_STRUCTURE_VALIDATION_01_RESOURCE_V1",
        "enumeration_policy": ENUMERATION,
        "fair_search_policy_hash": POLICY_HASH,
        "diversity_policy": V2_POLICY,
        "legacy_diversity_policy": V1_POLICY,
        "native_call_limit": 100,
        "checked_assignments_per_pool": 20,
        "counted_candidates_per_handoff": 5,
    }
)


def validate_fair_binding(binding: Mapping[str, Any]) -> None:
    if (
        binding.get("enumeration_contract") != FAIR_ENUMERATION_CONTRACT
        or binding.get("fair_search_policy_hash") != POLICY_HASH
        or not isinstance(binding.get("server_schedule_hash"), str)
        or binding.get("schedule_hash") != schedule_hash(binding["server_schedule_hash"])
    ):
        raise LayoutAuthorityError("POOL_FAIR_EXECUTION_BINDING_REQUIRED_OR_CHANGED")


class FairMultiSolutionPoolExecutionStore(PoolExecutionStore):
    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        validate_fair_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        result = super()._decision()
        validate_fair_binding(result)
        return result
