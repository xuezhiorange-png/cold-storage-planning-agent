"""Additional binding for the separately approved real enumeration experiment."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.domain.construction_diversity import POLICY as DIVERSITY_POLICY
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.infrastructure.stage_b_multi_solution import (
    POLICY as ENUMERATION_POLICY,
)
from cold_storage.modules.layout.infrastructure.stage_b_pool_execution import PoolExecutionStore

ENUMERATION_CONTRACT = MappingProxyType(
    {
        "version": "STAGE_B_REAL_MULTI_SOLUTION_VALIDATION_01_RESOURCE_V1",
        "enumeration_policy": ENUMERATION_POLICY,
        "diversity_policy": DIVERSITY_POLICY,
        "native_call_limit": 100,
        "checked_assignments_per_pool": 20,
        "counted_candidates_per_handoff": 5,
    }
)


class MultiSolutionPoolExecutionStore(PoolExecutionStore):
    """Same claims/ledger/reservations; no caller-configurable new allowance."""

    def approve(self, instruction: bytes, binding: Mapping[str, Any]) -> None:
        if binding.get("enumeration_contract") != ENUMERATION_CONTRACT:
            raise LayoutAuthorityError("POOL_ENUMERATION_CONTRACT_REQUIRED_OR_CHANGED")
        super().approve(instruction, binding)

    def _decision(self) -> dict[str, Any]:
        result = super()._decision()
        if result.get("enumeration_contract") != ENUMERATION_CONTRACT:
            raise LayoutAuthorityError("POOL_ENUMERATION_CONTRACT_REQUIRED_OR_CHANGED")
        return result
