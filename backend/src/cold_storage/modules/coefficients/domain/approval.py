"""Domain helpers for approved non-demo coefficient governance.

Pure-domain module for the Phase 4 Issue #35 Slice 1 scope:
- citation pattern validation (DOI:10.NNNN/..., STANDARD:ISO-NNNN, INTERNAL:REF-...)
- stale approval check (current time past valid_until)
- approval state-machine guards (typed)
- startup readineness evaluation helper

This module has **no** infrastructure dependencies (no SQLAlchemy, no
FastAPI, no Redis, no network). It is consumed by the application layer
(see ``application/approval_service.py``).

Slice 1 contract reference
--------------------------

Phase 4 design contract (`docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`)
§3, §5.2, §5.3, §5.4, §5.5.

Per Charles's Slice 1 authorization (2026-07-07):

- ``source_type`` retains the existing 8 values (no ``internal`` /
  ``literature`` added). DOI / STANDARD / INTERNAL are validated as
  citation **pattern** prefix, not new source-type values.
- ``status`` retains the existing 5 values
  (draft / unverified / reviewed / approved / withdrawn). The contract
  terms ``demo / under_review / approved / retired`` map as:

  - ``demo``         → ``source_type=demo``
  - ``under_review`` → ``status in (unverified, reviewed)`` (pre-approval)
  - ``approved``     → ``status == approved``
  - ``retired``      → ``status == withdrawn``

- ``source_citation`` is a **semantic alias** for the existing DB column
  ``source_reference``; no new column added.
"""  # noqa: E501

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final

from cold_storage.modules.coefficients.domain.exceptions import (
    InvalidCitationError,
    StaleApprovalError,
)
from cold_storage.modules.coefficients.domain.models import CoefficientRevision

# ---------------------------------------------------------------------------
# Citation pattern validation
# ---------------------------------------------------------------------------

#: Recognized citation pattern prefixes. Slice 1 only supports the three
#: forms Charles's instruction §4 lists. Adding a new pattern requires
#: explicit authorization and an architecture-boundary test update.
_CITATION_DOI_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^DOI:10\.\d{4,9}/[A-Za-z0-9._;()/:\-]+$"
)
_CITATION_STANDARD_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^STANDARD:[A-Z]{2,5}-?[A-Z0-9.\-]{1,32}$"
)
_CITATION_INTERNAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^INTERNAL:REF-[A-Za-z0-9.\-]{1,64}$"
)

#: Acceptable citation prefix kinds. Anything else is rejected.
ACCEPTABLE_CITATION_KINDS: Final[frozenset[str]] = frozenset({"DOI", "STANDARD", "INTERNAL"})


def validate_citation(citation: str | None) -> str:
    """Validate a citation string against the supported patterns.

    Per design contract §5.5: non-nullable on approved rows; non-matching
    formats rejected at approval time. This helper is the deterministic
    validator used by ``CoefficientApprovalService``.

    :param citation: The citation text (the semantic alias for
        ``source_reference``). Must be non-empty and match exactly one
        of the three patterns.

    :returns: The normalized citation (unchanged text). Returned for
        call-site convenience; ``source_reference`` stays as-is.

    :raises InvalidCitationError: If ``citation`` is empty, missing,
        or does not match any supported pattern.
    """
    if citation is None or not citation.strip():
        raise InvalidCitationError(
            citation if citation is not None else "",
            "Citation must be non-empty",
        )

    normalized = citation.strip()
    if (
        _CITATION_DOI_PATTERN.match(normalized)
        or _CITATION_STANDARD_PATTERN.match(normalized)
        or _CITATION_INTERNAL_PATTERN.match(normalized)
    ):
        return normalized

    raise InvalidCitationError(
        normalized,
        "Citation does not match any supported pattern "
        "(DOI:10.NNNN/..., STANDARD:ISO-NNNN, INTERNAL:REF-...)",
    )


# ---------------------------------------------------------------------------
# Stale-approval check
# ---------------------------------------------------------------------------


def is_stale(revision: CoefficientRevision, *, now: datetime | None = None) -> bool:
    """Return True if the revision's approval is past ``valid_to``.

    Per design contract §5.4: an approval carries a ``valid_until``
    timestamp. If the current time is past ``valid_until``, the approval
    is treated as ``expired`` even if ``status == approved`` and
    ``validity_status == verified``. The application fails closed when
    the only approved coefficient for a stage is expired.

    :param revision: The candidate approved revision.
    :param now: Reference time (UTC). Defaults to ``datetime.now(UTC)``.
        Tests pin a deterministic value.
    :returns: True iff ``now`` is after ``revision.valid_to``.
    """
    if revision.valid_to is None:
        return False
    reference = now if now is not None else datetime.now(UTC)
    # Compare in UTC. ``revision.valid_to`` is set as naive or tz-aware;
    # we coerce both sides to UTC-aware for the comparison.
    candidate = revision.valid_to
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return reference > candidate


def assert_not_stale(revision: CoefficientRevision, *, now: datetime | None = None) -> None:
    """Raise :class:`StaleApprovalError` if the revision is stale.

    Companion to :func:`is_stale` for the startup-readiness path.
    """
    if is_stale(revision, now=now):
        raise StaleApprovalError(revision.id)


# ---------------------------------------------------------------------------
# Approval state-machine guards (typed)
# ---------------------------------------------------------------------------


def assert_demo_rejected_in_production(revision: CoefficientRevision) -> None:
    """Reject demo coefficients when invoked from a production path.

    Per design contract §7 (no demo fallback). This guard is invoked by
    application-layer startup validation: any candidate whose
    ``source_type == demo`` is rejected with a typed error.
    """
    if revision.source_type == "demo":
        # Imported lazily to avoid a circular import at module load time
        # (exceptions module imports models, models references this guard
        # indirectly via application/service).
        from cold_storage.modules.coefficients.domain.exceptions import (
            DemoCoefficientInProductionError,
        )

        raise DemoCoefficientInProductionError(revision.id, revision.source_type)
