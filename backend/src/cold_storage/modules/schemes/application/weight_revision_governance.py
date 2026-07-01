"""Weight-set revision governance for production scheme generation.

Validates that a weight-set revision is approved, immutable, and
conforms to all governance contracts before allowing production use.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from cold_storage.modules.schemes.application.production_ports import (
    WeightCriterion,
    WeightRevisionReadPort,
    WeightSetRevisionSnapshot,
)

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
