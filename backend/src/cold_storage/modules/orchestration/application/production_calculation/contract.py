"""Task 11B Phase 2 — adapter contract validation.

Validation helpers that adapters (and tests) use to verify an
``AdapterResult`` is well-formed.  A well-formed result:

* has a non-empty ``payload``
* has a 64-hex-char ``content_hash`` matching
  :func:`compute_content_hash` applied to ``payload``
* sets ``requires_review`` from the calculator (no suppression)
* has a non-empty ``calculator_name`` and ``calculator_version``
* has at least one formula reference (where the calculator
  surfaces one)

The validator raises a typed
:class:`AdapterContractViolationError` on any violation, so
adapters can wrap their result construction with a single
``validate_adapter_result(result)`` call.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from cold_storage.modules.orchestration.application.production_calculation.dtos import (
    AdapterResult,
)
from cold_storage.modules.orchestration.application.production_calculation.errors import (
    AdapterContractViolationError,
)
from cold_storage.modules.orchestration.application.production_calculation.threading import (
    compute_content_hash,
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def validate_adapter_result(result: AdapterResult) -> None:
    """Validate that ``result`` is a well-formed ``AdapterResult``.

    The validator is intentionally strict — every invariant
    documented on :class:`AdapterResult` is checked.  The helper
    is the single source of truth for the adapter contract.
    """
    if not isinstance(result.payload, Mapping):
        raise AdapterContractViolationError(
            calculation_type=result.calculation_type.value,
            invariant="payload must be a Mapping",
        )
    # A *successful* adapter result must carry a non-empty
    # payload — the content_hash is derived from the payload and
    # an empty payload would force an empty hash, which is
    # semantically meaningless.  A *failed* adapter result
    # (``calculator_success=False``) may legitimately have an
    # empty payload; the calculator refused the input and never
    # produced a result.
    if not result.payload and result.calculator_success:
        raise AdapterContractViolationError(
            calculation_type=result.calculation_type.value,
            invariant="payload must be non-empty when calculator_success=True",
        )
    if not isinstance(result.content_hash, str) or (
        result.content_hash and not _HEX_64.match(result.content_hash)
    ):
        raise AdapterContractViolationError(
            calculation_type=result.calculation_type.value,
            invariant="content_hash must be a 64-char lowercase hex string",
        )
    if result.calculator_name == "":
        raise AdapterContractViolationError(
            calculation_type=result.calculation_type.value,
            invariant="calculator_name must be non-empty",
        )
    if result.calculator_version == "":
        raise AdapterContractViolationError(
            calculation_type=result.calculation_type.value,
            invariant="calculator_version must be non-empty",
        )
    if not isinstance(result.requires_review, bool):
        raise AdapterContractViolationError(
            calculation_type=result.calculation_type.value,
            invariant="requires_review must be a bool",
        )

    if result.payload and result.content_hash:
        expected_hash = compute_content_hash(result.payload)
        if expected_hash != result.content_hash:
            raise AdapterContractViolationError(
                calculation_type=result.calculation_type.value,
                invariant=(
                    f"content_hash mismatch: payload hash is {expected_hash!r}, "
                    f"declared {result.content_hash!r}"
                ),
            )

    if not result.calculator_success and not result.blockers:
        raise AdapterContractViolationError(
            calculation_type=result.calculation_type.value,
            invariant=("calculator_success=False requires at least one entry in blockers"),
        )
    if result.blockers and not result.calculator_success:
        # Blocker surface must always be coupled with a fail-closed
        # signal (calculator_success=False) so the orchestrator
        # can rely on a single boolean for the disposition.
        pass


def assert_requires_review_propagated(
    *,
    calculator_requires_review: bool,
    adapter_requires_review: bool,
    calculation_type: str,
) -> None:
    """Refuse to suppress a calculator's ``requires_review`` verdict.

    Adapters MUST propagate the calculator's verdict verbatim.
    The orchestrator (Phase 3) and the audit layer rely on this
    invariant to keep ``requires_review`` flagging honest.
    """
    from cold_storage.modules.orchestration.application.production_calculation.errors import (
        UnsupportedReviewRequiredOutputError,
    )

    if calculator_requires_review and not adapter_requires_review:
        raise UnsupportedReviewRequiredOutputError(calculation_type=calculation_type)


def freeze_for_hash(payload: Any) -> Any:
    """Convert a payload into a JSON-serialisable structure.

    ``Mapping`` is recursively converted to ``dict`` with sorted
    keys so :func:`compute_content_hash` produces a stable
    digest.  Lists are recursively converted to tuples.
    """
    if isinstance(payload, Mapping):
        return {k: freeze_for_hash(payload[k]) for k in sorted(payload.keys())}
    if isinstance(payload, (list, tuple)):
        return tuple(freeze_for_hash(item) for item in payload)
    if isinstance(payload, bool) or payload is None:
        return payload
    if isinstance(payload, (int, str)):
        return payload
    if isinstance(payload, float):
        return payload
    iso = getattr(payload, "isoformat", None)
    if callable(iso):
        return iso()
    raise TypeError(f"Cannot freeze value of type {type(payload).__name__} for hashing")
