"""Source binding only for the approved guided fair MAIN and exact REPLAY.

Claims, counters, reservations and search are inherited unchanged. No public
caller selects an approval, strategy, resource budget or registry directory.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_b_fair_execution import (
    FairMultiSolutionPoolExecutionStore,
    validate_fair_binding,
)
from cold_storage.modules.layout.infrastructure.stage_b_wall_alignment import POLICY, POLICY_HASH

GUIDED_EXECUTION_CONTRACT = MappingProxyType(
    {
        "version": "STAGE_B_REAL_GUIDED_FAIR_VALIDATION_02_BINDING_V1",
        "wall_guidance_policy": POLICY,
        "wall_guidance_policy_hash": POLICY_HASH,
        "strict_base_infeasible_short_circuit": True,
    }
)


def validate_guided_binding(binding: Mapping[str, Any]) -> None:
    validate_fair_binding(binding)
    if binding.get("guided_execution_contract") != GUIDED_EXECUTION_CONTRACT:
        raise LayoutAuthorityError("POOL_GUIDED_FAIR_BINDING_REQUIRED_OR_CHANGED")


class GuidedFairPoolExecutionStore(FairMultiSolutionPoolExecutionStore):
    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        validate_guided_binding(binding)
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        result = super()._decision()
        validate_guided_binding(result)
        return result
