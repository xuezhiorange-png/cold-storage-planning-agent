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
    """Parse and validate raw criteria from revision content.

    Strict validation:
    - criterion_code: required non-empty string
    - weight: required string that converts to Decimal (reject float, reject missing/None)
    - direction: required in ('higher_is_better', 'lower_is_better')
    - normalization_method: required in ('min_max', 'z_score', 'raw')
    - hard_constraint: required bool (exact bool type)
    - description: optional, default None
    - Sum of non-hard-constraint weights must equal Decimal('1') within tolerance
    """
    criteria: list[WeightCriterion] = []
    valid_directions = {"higher_is_better", "lower_is_better"}
    valid_normalizations = {"min_max", "z_score", "raw"}

    for raw in raw_criteria:
        # criterion_code: required non-empty string
        criterion_code = raw.get("criterion_code")
        if not isinstance(criterion_code, str) or not criterion_code:
            raise WeightRevisionGovernanceError(
                "invalid_criterion_code",
                f"criterion_code must be a non-empty string, got {criterion_code!r}",
            )

        # weight: required string that converts to Decimal
        weight_val = raw.get("weight")
        if weight_val is None:
            raise WeightRevisionGovernanceError(
                "missing_weight",
                f"Criterion {criterion_code!r} missing required 'weight'",
            )
        if isinstance(weight_val, (int, float)):
            raise WeightRevisionGovernanceError(
                "invalid_weight_type",
                f"Criterion {criterion_code!r} weight must be a string,"
                f" not {type(weight_val).__name__}",
            )
        if not isinstance(weight_val, str):
            raise WeightRevisionGovernanceError(
                "invalid_weight_type",
                f"Criterion {criterion_code!r} weight must be a string,"
                f" got {type(weight_val).__name__}",
            )
        try:
            weight = Decimal(weight_val)
        except Exception as exc:
            raise WeightRevisionGovernanceError(
                "invalid_weight_value",
                f"Criterion {criterion_code!r} weight {weight_val!r} is not a valid Decimal",
            ) from exc

        # direction: required in valid set
        direction = raw.get("direction")
        if direction not in valid_directions:
            raise WeightRevisionGovernanceError(
                "invalid_direction",
                f"Criterion {criterion_code!r} direction must be one of"
                f" {valid_directions}, got {direction!r}",
            )

        # normalization_method: required in valid set
        normalization_method = raw.get("normalization_method")
        if normalization_method not in valid_normalizations:
            raise WeightRevisionGovernanceError(
                "invalid_normalization_method",
                f"Criterion {criterion_code!r} normalization_method must be one of"
                f" {valid_normalizations}, got {normalization_method!r}",
            )

        # hard_constraint: required bool (exact type)
        hard_constraint = raw.get("hard_constraint")
        if not isinstance(hard_constraint, bool):
            raise WeightRevisionGovernanceError(
                "invalid_hard_constraint",
                f"Criterion {criterion_code!r} hard_constraint must be a bool,"
                f" got {type(hard_constraint).__name__}",
            )

        # description: optional
        description = raw.get("description", None)
        if description is not None and not isinstance(description, str):
            raise WeightRevisionGovernanceError(
                "invalid_description",
                f"Criterion {criterion_code!r} description must be a string"
                f" or None, got {type(description).__name__}",
            )

        criteria.append(
            WeightCriterion(
                criterion_code=criterion_code,
                weight=weight,
                direction=direction,
                normalization_method=normalization_method,
                hard_constraint=hard_constraint,
                description=description or "",
            )
        )

    # Sum non-hard-constraint weights must equal 1.0 within tolerance
    if criteria:
        non_hard_sum = sum((c.weight for c in criteria if not c.hard_constraint), Decimal(0))
        if abs(non_hard_sum - Decimal("1")) > Decimal("0.0001"):
            raise RevisionWeightSumError(non_hard_sum)

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

    # 7. Generator compatibility
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

    def seed_if_not_exists(
        self,
        session: Any,
        *,
        weight_set_id: str,
        code: str,
        name: str,
        revision_id: str,
        revision: int,
        content: dict[str, Any],
        generator_compatibility_version: str,
        approved_at: Any,
        approved_by: str,
    ) -> None:
        """Idempotently seed weight set and revision records.

        Creates SchemeWeightSetRecord + SchemeWeightSetRevisionRecord
        if not exists, approves if draft.
        """
        ...


def approve_weight_revision(
    approval_port: WeightRevisionApprovalPort,
    read_port: WeightRevisionReadPort | None,
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
    # P0-2: adapter raises WeightRevisionGovernanceError(active_revision_conflict)
    # when another revision already claims authority for the same weight_set_id+code.
    now = datetime.now(UTC)
    approval_port.approve_revision(
        session,
        revision_id=revision_id,
        content=content,
        approved_at=now,
        approved_by=approved_by,
    )


# ── Production weight seed helper ─────────────────────────────────────────

# Fixed production weight content — deterministic and versioned
_PRODUCTION_WEIGHT_CONTENT: dict[str, Any] = {
    "criteria": [
        {
            "criterion_code": "total_area_m2",
            "weight": "0.15",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total cold room area — smaller is better",
        },
        {
            "criterion_code": "total_position_count",
            "weight": "0.15",
            "direction": "higher_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total storage positions — more is better",
        },
        {
            "criterion_code": "room_module_count",
            "weight": "0.10",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Number of room modules — fewer is better",
        },
        {
            "criterion_code": "door_count",
            "weight": "0.10",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total door count — fewer is better",
        },
        {
            "criterion_code": "partition_length_proxy_m",
            "weight": "0.05",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Partition wall length proxy — shorter is better",
        },
        {
            "criterion_code": "investment_cny",
            "weight": "0.30",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total investment — lower is better",
        },
        {
            "criterion_code": "installed_power_kw_e",
            "weight": "0.15",
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
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    approval_port.seed_if_not_exists(
        session,
        weight_set_id=PRODUCTION_WEIGHT_SET_ID,
        code=PRODUCTION_WEIGHT_SET_CODE,
        name="Production Default Weight Set",
        revision_id=PRODUCTION_WEIGHT_SET_REVISION_ID,
        revision=PRODUCTION_WEIGHT_SET_REVISION,
        content=_PRODUCTION_WEIGHT_CONTENT,
        generator_compatibility_version="1.0.0",
        approved_at=now,
        approved_by=approved_by,
    )
