"""Append-only facts for the source-owned R6 final model, not caller certificates.

Record supplied bounds when variables are actually created. Only the six physical
references are read back for guidance. Clones/copies cannot inherit these facts.
The private builder owns this model until guidance: arbitrary raw-proto/domain
rewrites are NOT a supported construction API or an authorization boundary.
"""

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from ortools.sat.python import cp_model

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError

PHYSICAL_NAMES = frozenset(
    role + "_physical_" + side
    for role in ("office", "changing_room", "coating_room")
    for side in ("w", "d")
)


class ReferenceCpModel(cp_model.CpModel):
    """Only our append-only GlobalModel/AccessModel factory produces R6 facts."""

    def __init__(self, charge: Callable[[str, int], None]) -> None:
        super().__init__()
        self.charge = charge
        self.recorded = 0
        self.magnitude = 0
        self.physical: dict[str, list[tuple[int, int, int]]] = {}
        self.owner: Any = None
        self.defining = False
        self.defined = False
        self.implicit_reads = 0

    def _constants(self) -> None:
        if len(self.proto.variables) < self.recorded:
            raise LayoutAuthorityError("R6_MODEL_REFERENCE_HISTORY_CHANGED")
        while self.recorded < len(self.proto.variables):
            # Native Boolean APIs can append an unnamed constant without a
            # Python new_constant call. Visit ONLY that unrecorded tail.
            self.charge("R6_IMPLICIT_CONSTANT_READ", 3)
            v = self.proto.variables[self.recorded]
            self.implicit_reads += 1
            if v.name or len(v.domain) != 2 or v.domain[0] != v.domain[1]:
                raise LayoutAuthorityError("R6_UNTRACKED_VARIABLE_MUTATION")
            self.charge("R6_CREATED_DOMAIN_FACT", 1)
            self.magnitude += abs(v.domain[0])
            self.recorded += 1

    def _before(self, name: str) -> None:
        self._constants()
        if self.owner is not None and not self.defining:
            raise LayoutAuthorityError("R6_OWNED_MODEL_VARIABLES_SEALED")
        if name.startswith("r5_area_") and not self.defining:
            raise LayoutAuthorityError("R6_UNEXPECTED_GUIDANCE_DEFINITION")
        # A real creation-time accumulator update, not a discounted proto scan.
        self.charge("R6_CREATED_DOMAIN_FACT", 1)

    def _record(self, variable: Any, low: int, high: int, name: str) -> Any:
        if variable.index != self.recorded:
            raise LayoutAuthorityError("R6_VARIABLE_APPEND_ORDER_CHANGED")
        self.magnitude += max(abs(low), abs(high))
        if name in PHYSICAL_NAMES:
            self.physical.setdefault(name, []).append((variable.index, low, high))
        self.recorded += 1
        return variable

    def new_int_var(self, lb: Any, ub: Any, name: str) -> Any:
        self._before(name)
        return self._record(super().new_int_var(lb, ub, name), int(lb), int(ub), name)

    def new_bool_var(self, name: str) -> Any:
        self._before(name)
        return self._record(super().new_bool_var(name), 0, 1, name)

    def new_int_var_from_domain(self, domain: Any, name: str) -> Any:
        raise LayoutAuthorityError("R6_NON_INTERVAL_CREATION_UNSUPPORTED")

    def new_constant(self, value: Any) -> Any:
        self._constants()
        result = super().new_constant(value)
        self._constants()
        return result

    def __copy__(self) -> Any:
        raise LayoutAuthorityError("R6_REFERENCE_COPY_UNSUPPORTED")

    def __deepcopy__(self, memo: Any) -> Any:
        raise LayoutAuthorityError("R6_REFERENCE_COPY_UNSUPPORTED")

    def seal(self, owner: Any) -> None:
        if self.owner is not None or owner.m is not self:
            raise LayoutAuthorityError("R6_MODEL_OWNER_MISMATCH")
        self._constants()
        self.owner = owner

    def checked_physical(self, owner: Any) -> tuple[int, dict[str, Any]]:
        if owner is not self.owner or owner.m is not self or self.defined:
            raise LayoutAuthorityError("R6_OWNED_MODEL_REQUIRED")
        if self.charge != owner.c.ledger.charge:
            raise LayoutAuthorityError("R6_MODEL_LEDGER_MISMATCH")
        self._constants()
        self.charge("R6_PHYSICAL_FACTS_READ", 3 * len(PHYSICAL_NAMES) + 3)
        result = {}
        for role in ("office", "changing_room", "coating_room"):
            for side in ("w", "d"):
                name = role + "_physical_" + side
                variable = owner.rooms[role][side]
                recorded = self.physical.get(name, [])
                if len(recorded) != 1 or variable.model_proto is not self.proto:
                    raise LayoutAuthorityError("R6_PHYSICAL_REFERENCE_CHANGED")
                if (
                    variable.name != name
                    or not 0 <= variable.index < self.recorded
                    or variable.proto is not self.proto.variables[variable.index]
                    or len(variable.proto.domain) != 2
                ):
                    raise LayoutAuthorityError("R6_PHYSICAL_REFERENCE_CHANGED")
                low, high = variable.proto.domain[0], variable.proto.domain[1]
                if recorded[0] != (variable.index, low, high):
                    raise LayoutAuthorityError("R6_PHYSICAL_REFERENCE_CHANGED")
                result[name] = (variable, low, high)
        return self.magnitude, result

    @contextmanager
    def definitions(self) -> Any:
        if self.defined or self.owner is None:
            raise LayoutAuthorityError("R6_OWNED_MODEL_REQUIRED")
        self.defining = True
        try:
            yield
            self.defined = True
        finally:
            self.defining = False
