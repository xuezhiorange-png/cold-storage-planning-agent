"""Weight-set revision governance for production scheme generation.

Validates that a weight-set revision is approved, immutable, and
conforms to all governance contracts before allowing production use.

Also provides:
- approve_weight_revision(): set status=approved with concurrent CAS protection
- seed_production_weight_revision(): idempotent production seed data
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Protocol

from cold_storage.modules.schemes.application.production_ports import (
    WeightRevisionReadPort,
    WeightSetRevisionSnapshot,
)
from cold_storage.modules.schemes.domain.models import WeightCriterion

# ── Governance version ─────────────────────────────────────────────────────

WEIGHT_REVISION_GOVERNANCE_VERSION: str = "1.0.0"


# ── Governance errors ──────────────────────────────────────────────────────


class WeightRevisionGovernanceError(Exception):
    """Base error for weight revision governance failures."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RevisionNotFoundError(WeightRevisionGovernanceError):
    def __init__(self, revision_id: str) -> None:
        super().__init__(
            "revision_not_found",
            f"Weight revision {revision_id!r} not found",
        )


class RevisionNotApprovedError(WeightRevisionGovernanceError):
    def __init__(self, revision_id: str, status: str) -> None:
        super().__init__(
            "revision_not_approved",
            f"Revision {revision_id!r} status is {status!r}, expected 'approved'",
        )


class RevisionMissingApprovalEvidenceError(WeightRevisionGovernanceError):
    def __init__(self, revision_id: str, field: str) -> None:
        super().__init__(
            "revision_missing_approval_evidence",
            f"Revision {revision_id!r} missing {field}",
        )


class RevisionContentHashMismatchError(WeightRevisionGovernanceError):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            "revision_content_hash_mismatch",
            f"Content hash: expected {expected!r}, computed {actual!r}",
        )


class RevisionCriteriaDuplicateError(WeightRevisionGovernanceError):
    def __init__(self, code: str) -> None:
        super().__init__(
            "revision_criteria_duplicate",
            f"Duplicate criterion code: {code!r}",
        )


class RevisionWeightSumError(WeightRevisionGovernanceError):
    def __init__(self, total: Decimal) -> None:
        super().__init__(
            "revision_weight_sum_invalid",
            f"Non-hard-constraint weights sum to {total}, expected 1.0",
        )


class RevisionNegativeWeightError(WeightRevisionGovernanceError):
    def __init__(self, code: str, weight: Decimal) -> None:
        super().__init__(
            "revision_negative_weight",
            f"Criterion {code!r} has negative weight {weight}",
        )


class RevisionIncompatibleGeneratorError(WeightRevisionGovernanceError):
    def __init__(self, revision_gen: str, required_gen: str) -> None:
        super().__init__(
            "revision_incompatible_generator",
            f"Revision generator {revision_gen!r} incompatible with {required_gen!r}",
        )


class RevisionTamperedContentError(WeightRevisionGovernanceError):
    def __init__(self) -> None:
        super().__init__("revision_tampered", "Revision content tampered (hash mismatch)")


class RevisionAlreadyApprovedError(WeightRevisionGovernanceError):
    def __init__(self, weight_set_id: str, code: str) -> None:
        super().__init__(
            "revision_already_approved",
            f"Weight set {weight_set_id!r} code {code!r} already has an approved revision",
        )


class RevisionApprovalCASConflictError(WeightRevisionGovernanceError):
    def __init__(self, weight_set_id: str, code: str) -> None:
        super().__init__(
            "revision_approval_cas_conflict",
            f"CAS conflict: another revision was approved concurrently for "
            f"weight set {weight_set_id!r} code {code!r}",
        )


# ── Canonical hash ─────────────────────────────────────────────────────────


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _compute_content_hash(content: dict[str, Any]) -> str:
    """SHA-256 of the canonical content dict."""
    return hashlib.sha256(_canonical_json(content).encode()).hexdigest()


# ── Criteria parsing ───────────────────────────────────────────────────────


def _parse_criteria(
    raw_criteria: list[dict[str, Any]],
) -> tuple[WeightCriterion, ...]:
    """Parse and validate raw criteria from revision content."""
    criteria: list[WeightCriterion] = []
    for raw in raw_criteria:
        weight_val = raw.get("weight", 0)
        if isinstance(weight_val, (int, float)):
            weight = Decimal(str(weight_val))
        elif isinstance(weight_val, str):
            weight = Decimal(weight_val)
        else:
            weight = Decimal(weight_val)

        criteria.append(
            WeightCriterion(
                criterion_code=raw["criterion_code"],
                weight=weight,
                direction=raw.get("direction", "higher_is_better"),
                normalization_method=raw.get("normalization_method", "min_max"),
                hard_constraint=raw.get("hard_constraint", False),
                description=raw.get("description", ""),
            )
        )
    return tuple(criteria)


# ── Governance validation ──────────────────────────────────────────────────


def validate_weight_revision(
    revision: WeightSetRevisionSnapshot,
    *,
    generator_version: str,
) -> tuple[WeightCriterion, ...]:
    """Validate a weight-set revision against all governance rules.

    Returns the parsed criteria tuple on success.  Raises on any
    governance violation.
    """
    # 1. Status must be 'approved'
    if revision.status != "approved":
        raise RevisionNotApprovedError(revision.id, revision.status)

    # 2. Approval evidence
    if not revision.approved_at:
        raise RevisionMissingApprovalEvidenceError(revision.id, "approved_at")
    if not revision.approved_by:
        raise RevisionMissingApprovalEvidenceError(revision.id, "approved_by")

    # 3. Content hash integrity
    computed_hash = _compute_content_hash(revision.content)
    if computed_hash != revision.content_hash:
        raise RevisionTamperedContentError()

    # 4. Parse criteria from content
    raw_criteria = revision.content.get("criteria", [])
    if not raw_criteria:
        raise WeightRevisionGovernanceError(
            "revision_no_criteria", f"Revision {revision.id!r} has no criteria"
        )

    criteria = _parse_criteria(raw_criteria)

    # 5. No duplicate criteria
    seen_codes: set[str] = set()
    for c in criteria:
        if c.criterion_code in seen_codes:
            raise RevisionCriteriaDuplicateError(c.criterion_code)
        seen_codes.add(c.criterion_code)

    # 6. No negative weights
    for c in criteria:
        if c.weight < 0:
            raise RevisionNegativeWeightError(c.criterion_code, c.weight)

    # 7. Non-hard-constraint weights sum to 1.0
    non_hard_sum = sum((c.weight for c in criteria if not c.hard_constraint), Decimal(0))
    # Allow tiny floating-point tolerance
    if abs(non_hard_sum - Decimal("1")) > Decimal("0.0001"):
        raise RevisionWeightSumError(non_hard_sum)

    # 8. Generator compatibility
    if revision.generator_compatibility_version != generator_version:
        raise RevisionIncompatibleGeneratorError(
            revision.generator_compatibility_version, generator_version
        )

    return criteria


# ── Production weight revision loading ─────────────────────────────────────


def load_and_validate_weight_revision(
    read_port: WeightRevisionReadPort,
    session: Any,
    *,
    revision_id: str,
    generator_version: str,
) -> WeightSetRevisionSnapshot:
    """Load and validate an approved weight-set revision.

    Returns the validated snapshot with parsed criteria.
    """
    revision = read_port.load_approved_revision(session, revision_id=revision_id)
    if revision is None:
        raise RevisionNotFoundError(revision_id)

    validate_weight_revision(revision, generator_version=generator_version)
    return revision


# ── Weight revision approval (P0-7) ───────────────────────────────────────


class WeightRevisionApprovalPort(Protocol):
    """Write port for weight revision approval.

    The infrastructure layer implements CAS (Compare-And-Swap) to
    prevent concurrent duplicate approvals for the same weight_set_id + code.
    """

    def approve_revision(
        self,
        session: Any,
        *,
        revision_id: str,
        content: dict[str, Any],
        approved_at: Any,
        approved_by: str,
    ) -> bool:
        """Approve a weight revision with CAS protection.

        Returns True if approved, False if CAS conflict (another approved
        revision exists for the same weight_set_id + code).
        """
        ...

    def has_approved_revision(
        self,
        session: Any,
        *,
        weight_set_id: str,
        code: str,
        exclude_revision_id: str | None = None,
    ) -> bool:
        """Check if an approved revision already exists for this weight_set_id + code.

        If exclude_revision_id is provided, exclude that revision from the check
        (useful for idempotent operations).
        """
        ...


def approve_weight_revision(
    approval_port: WeightRevisionApprovalPort,
    read_port: WeightRevisionReadPort,
    session: Any,
    *,
    revision_id: str,
    weight_set_id: str,
    code: str,
    content: dict[str, Any],
    approved_by: str,
) -> None:
    """Approve a weight revision with concurrent CAS protection.

    1. Compute deterministic content hash
    2. Check no other approved revision exists for same weight_set_id + code (CAS)
    3. Set status=approved, approved_at, approved_by, content_hash
    4. Persist via approval port

    Raises RevisionAlreadyApprovedError if another approved revision exists.
    Raises RevisionApprovalCASConflictError on concurrent CAS failure.
    """
    from datetime import UTC, datetime

    # 1. Compute deterministic content hash
    _compute_content_hash(content)

    # 2. CAS check: no other approved revision for same weight_set_id + code
    already_approved = approval_port.has_approved_revision(
        session,
        weight_set_id=weight_set_id,
        code=code,
        exclude_revision_id=revision_id,
    )
    if already_approved:
        raise RevisionAlreadyApprovedError(weight_set_id, code)

    # 3. Attempt CAS approve
    now = datetime.now(UTC)
    approved = approval_port.approve_revision(
        session,
        revision_id=revision_id,
        content=content,
        approved_at=now,
        approved_by=approved_by,
    )
    if not approved:
        raise RevisionApprovalCASConflictError(weight_set_id, code)


# ── Production weight seed helper ─────────────────────────────────────────

# Fixed production weight content — deterministic and versioned
_PRODUCTION_WEIGHT_CONTENT: dict[str, Any] = {
    "criteria": [
        {
            "criterion_code": "total_area_m2",
            "weight": 0.15,
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total cold room area — smaller is better",
        },
        {
            "criterion_code": "total_position_count",
            "weight": 0.15,
            "direction": "higher_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total storage positions — more is better",
        },
        {
            "criterion_code": "room_module_count",
            "weight": 0.10,
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Number of room modules — fewer is better",
        },
        {
            "criterion_code": "door_count",
            "weight": 0.10,
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total door count — fewer is better",
        },
        {
            "criterion_code": "partition_length_proxy_m",
            "weight": 0.05,
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Partition wall length proxy — shorter is better",
        },
        {
            "criterion_code": "investment_cny",
            "weight": 0.30,
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total investment — lower is better",
        },
        {
            "criterion_code": "installed_power_kw_e",
            "weight": 0.15,
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Installed electrical power — lower is better",
        },
    ],
    "version": "1.0.0",
    "description": "Production default weight set for cold room scheme scoring",
}

# Fixed identity values for production seed
PRODUCTION_WEIGHT_SET_ID: str = "ws-production-default"
PRODUCTION_WEIGHT_SET_CODE: str = "production-default"
PRODUCTION_WEIGHT_SET_REVISION_ID: str = "wsr-production-default-v1"
PRODUCTION_WEIGHT_SET_REVISION: int = 1


def get_production_weight_content_hash() -> str:
    """Compute deterministic content hash for the fixed production weight content."""
    return _compute_content_hash(_PRODUCTION_WEIGHT_CONTENT)


def get_production_weight_criteria() -> tuple[WeightCriterion, ...]:
    """Return parsed production weight criteria from the fixed content."""
    return _parse_criteria(_PRODUCTION_WEIGHT_CONTENT["criteria"])


def seed_production_weight_revision(
    approval_port: WeightRevisionApprovalPort,
    session: Any,
    *,
    generator_version: str,  # noqa: ARG001 — kept for interface consistency
    approved_by: str = "system",
) -> None:
    """Idempotently seed an approved production weight revision.

    Creates the fixed production weight revision if it doesn't already
    exist.  Works for both SQLite and PostgreSQL.

    Content hash is deterministic.  Revision identity is fixed.
    """
    # Check if already exists
    existing = approval_port.has_approved_revision(
        session,
        weight_set_id=PRODUCTION_WEIGHT_SET_ID,
        code=PRODUCTION_WEIGHT_SET_CODE,
        exclude_revision_id=PRODUCTION_WEIGHT_SET_REVISION_ID,
    )
    if existing:
        return  # Already seeded

    from datetime import UTC, datetime

    now = datetime.now(UTC)

    # Approve (CAS will skip if already approved concurrently)
    approval_port.approve_revision(
        session,
        revision_id=PRODUCTION_WEIGHT_SET_REVISION_ID,
        content=_PRODUCTION_WEIGHT_CONTENT,
        approved_at=now,
        approved_by=approved_by,
    )
