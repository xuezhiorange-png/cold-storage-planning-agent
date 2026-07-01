"""Orchestration domain — structured errors.

Every exception carries a machine-readable ``code``, a ``field`` (where the
failure originated), and structured ``details`` (a mapping).  Callers MUST
NOT parse ``message`` text to determine error class.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class OrchestrationDomainError(Exception):
    """Base for all orchestration domain errors."""

    def __init__(
        self, code: str, message: str, *, field: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.details: Mapping[str, object] = details if details is not None else {}


# ── Preflight validation ────────────────────────────────────────────────────


class OrchestrationRequestIdentityError(OrchestrationDomainError):
    """Request identity validation failure (preflight)."""

    def __init__(
        self, field: str = "", message: str = "Invalid orchestration request identity"
    ) -> None:
        super().__init__("ORCH_REQUEST_IDENTITY_INVALID", message, field=field)


class ProjectVersionNotFoundError(OrchestrationDomainError):
    """ProjectVersion not found (preflight)."""

    def __init__(self, project_version_id: str) -> None:
        super().__init__(
            "PROJ_VERSION_NOT_FOUND",
            f"ProjectVersion {project_version_id!r} not found",
            field="project_version_id",
            details={"project_version_id": project_version_id},
        )


class ProjectVersionProjectMismatchError(OrchestrationDomainError):
    """ProjectVersion does not belong to requested project (preflight)."""

    def __init__(self, version_project_id: str, request_project_id: str) -> None:
        super().__init__(
            "PROJ_VERSION_PROJECT_MISMATCH",
            f"Version belongs to project {version_project_id!r}, not {request_project_id!r}",
            field="project_id",
            details={
                "version_project_id": version_project_id,
                "request_project_id": request_project_id,
            },
        )


class ProjectVersionNotReadyError(OrchestrationDomainError):
    """ProjectVersion status is not 'approved' (preflight)."""

    def __init__(self, project_version_id: str, status: str) -> None:
        super().__init__(
            "PROJ_VERSION_NOT_READY",
            f"ProjectVersion {project_version_id!r} status is {status!r} (requires 'approved')",
            field="version_status",
            details={"project_version_id": project_version_id, "status": status},
        )


class ProjectVersionArchivedError(OrchestrationDomainError):
    """ProjectVersion is archived (preflight)."""

    def __init__(self, project_version_id: str) -> None:
        super().__init__(
            "PROJ_VERSION_ARCHIVED",
            f"ProjectVersion {project_version_id!r} is archived",
            field="project_version_id",
            details={"project_version_id": project_version_id},
        )


class ProjectVersionStatusInvalidError(OrchestrationDomainError):
    """ProjectVersion has an unknown or illegal status (preflight)."""

    def __init__(self, project_version_id: str, status: str) -> None:
        super().__init__(
            "PROJ_VERSION_STATUS_INVALID",
            f"ProjectVersion {project_version_id!r} has illegal status {status!r}",
            field="version_status",
            details={"project_version_id": project_version_id, "status": status},
        )


# ── Snapshot / schema errors ────────────────────────────────────────────────


class ExecutionSnapshotSchemaError(OrchestrationDomainError):
    """Execution snapshot schema is invalid or unsupported (preflight)."""

    def __init__(self, schema_version: str) -> None:
        super().__init__(
            "EXEC_SNAPSHOT_SCHEMA_INVALID",
            f"Execution snapshot schema version {schema_version!r} is invalid or unsupported",
            field="schema_version",
            details={"schema_version": schema_version},
        )


class SourceSnapshotSchemaError(OrchestrationDomainError):
    """Source snapshot schema is invalid or unsupported."""

    def __init__(self, schema_version: str, reason: str = "") -> None:
        super().__init__(
            "SOURCE_SNAPSHOT_SCHEMA_INVALID",
            f"Source snapshot schema {schema_version!r} is invalid: {reason}",
            field="snapshot_schema_version",
            details={"schema_version": schema_version, "reason": reason},
        )


class SourceSnapshotIntegrityError(OrchestrationDomainError):
    """Source snapshot content fails integrity validation."""

    def __init__(self, calculation_type: str, reason: str = "") -> None:
        super().__init__(
            "SOURCE_SNAPSHOT_INTEGRITY",
            f"Source snapshot integrity failure for {calculation_type!r}: {reason}",
            field="content",
            details={"calculation_type": calculation_type, "reason": reason},
        )


class TamperedContentError(OrchestrationDomainError):
    """Content hash mismatch — possible tampering or corruption."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            "TAMPERED_CONTENT",
            f"Content hash mismatch: expected {expected!r}, got {actual!r}",
            field="result_hash",
            details={"expected": expected, "actual": actual},
        )


# ── Coefficient resolution errors ───────────────────────────────────────────


class CoefficientResolutionError(OrchestrationDomainError):
    """Coefficient resolution failed (preflight)."""

    def __init__(self, coefficient_code: str, reason: str = "") -> None:
        super().__init__(
            "COEFF_RESOLUTION_FAILED",
            f"Failed to resolve coefficient {coefficient_code!r}: {reason}",
            field="coefficient_code",
            details={"coefficient_code": coefficient_code, "reason": reason},
        )


class CoefficientNotApprovedError(OrchestrationDomainError):
    """Required coefficient is not approved (preflight)."""

    def __init__(self, coefficient_code: str) -> None:
        super().__init__(
            "COEFF_NOT_APPROVED",
            f"Coefficient {coefficient_code!r} is not approved",
            field="coefficient_code",
            details={"coefficient_code": coefficient_code},
        )


class AmbiguousCoefficientError(OrchestrationDomainError):
    """Coefficient resolution is ambiguous (preflight)."""

    def __init__(self, coefficient_code: str) -> None:
        super().__init__(
            "COEFF_AMBIGUOUS",
            f"Ambiguous resolution for coefficient {coefficient_code!r}",
            field="coefficient_code",
            details={"coefficient_code": coefficient_code},
        )


# ── Orchestration concurrency / lease errors ────────────────────────────────


class AttemptAlreadyRunningError(OrchestrationDomainError):
    """An attempt is already RUNNING for this identity."""

    def __init__(self, identity_id: str) -> None:
        super().__init__(
            "ORCH_ATTEMPT_ALREADY_RUNNING",
            f"A RUNNING attempt already exists for identity {identity_id!r}",
            field="identity_id",
            details={"identity_id": identity_id},
        )


class AttemptTakeoverConflictError(OrchestrationDomainError):
    """CAS takeover failed — heartbeat changed since observation."""

    def __init__(
        self,
        *,
        identity_id: str,
        attempt_id: str | None = None,
        retry_count: int,
    ) -> None:
        super().__init__(
            "ORCH_ATTEMPT_TAKEOVER_CONFLICT",
            f"Attempt acquisition conflict for identity {identity_id!r}",
            field="heartbeat_at",
            details={
                "identity_id": identity_id,
                "attempt_id": attempt_id,
                "retry_count": retry_count,
            },
        )


# ── Invalid stage transition ────────────────────────────────────────────────


class InvalidStageTransitionError(OrchestrationDomainError):
    """Requested stage transition is not allowed from current state."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            "INVALID_STAGE_TRANSITION",
            f"Cannot transition from {current!r} to {target!r}",
            field="status",
            details={"current": current, "target": target},
        )


# ── Unsupported schema / version ────────────────────────────────────────────


class UnsupportedSchemaError(OrchestrationDomainError):
    """Schema version is not supported."""

    def __init__(self, schema_type: str, version: str) -> None:
        super().__init__(
            "UNSUPPORTED_SCHEMA",
            f"{schema_type} schema version {version!r} is not supported",
            field="schema_version",
            details={"schema_type": schema_type, "version": version},
        )


# ── Source binding errors ───────────────────────────────────────────────────


class SourceBindingSlotTypeError(OrchestrationDomainError):
    """SourceBinding slot points to wrong calculation_type or calculator_name."""

    def __init__(self, slot_name: str, expected: str, actual: str) -> None:
        super().__init__(
            "SOURCE_BINDING_SLOT_TYPE",
            f"Slot {slot_name!r}: expected {expected!r}, got {actual!r}",
            field="slot_name",
            details={"slot_name": slot_name, "expected": expected, "actual": actual},
        )


class SourceBindingIdentityMismatchError(OrchestrationDomainError):
    """SourceBinding record does not match expected identity/attempt metadata."""

    def __init__(self, field: str, expected: str, actual: str) -> None:
        super().__init__(
            "SOURCE_BINDING_IDENTITY_MISMATCH",
            f"SourceBinding {field}: expected {expected!r}, got {actual!r}",
            field=field,
            details={"field": field, "expected": expected, "actual": actual},
        )


class SourceBindingHashMismatchError(OrchestrationDomainError):
    """SourceBinding per-calculation hash does not match CalculationRunRecord.result_hash."""

    def __init__(self, hash_field: str, expected: str, actual: str) -> None:
        super().__init__(
            "SOURCE_BINDING_HASH_MISMATCH",
            f"SourceBinding {hash_field} hash mismatch",
            field=hash_field,
            details={"hash_field": hash_field, "expected": expected, "actual": actual},
        )


# ── Weight-set errors ───────────────────────────────────────────────────────


class WeightSetNotApprovedError(OrchestrationDomainError):
    """Scheme weight-set revision is not approved."""

    def __init__(self, weight_set_revision_id: str) -> None:
        super().__init__(
            "WEIGHT_SET_NOT_APPROVED",
            f"Weight-set revision {weight_set_revision_id!r} is not approved",
            field="weight_set_revision_id",
            details={"weight_set_revision_id": weight_set_revision_id},
        )


class WeightSetIncompatibleError(OrchestrationDomainError):
    """Scheme weight-set generator compatibility version mismatch."""

    def __init__(self, weight_set_revision_id: str, generator_compatibility_version: str) -> None:
        super().__init__(
            "WEIGHT_SET_INCOMPATIBLE",
            f"Weight-set revision {weight_set_revision_id!r} is incompatible "
            f"(generator version {generator_compatibility_version!r})",
            field="generator_compatibility_version",
            details={
                "weight_set_revision_id": weight_set_revision_id,
                "generator_compatibility_version": generator_compatibility_version,
            },
        )


# ── Transaction / persistence invariant errors ──────────────────────────────


class TransactionInvariantError(OrchestrationDomainError):
    """Transaction invariant violated — partial state detected."""

    def __init__(self, invariant: str) -> None:
        super().__init__(
            "TRANSACTION_INVARIANT",
            f"Transaction invariant violated: {invariant}",
            field="transaction",
            details={"invariant": invariant},
        )


class PersistenceInvariantError(OrchestrationDomainError):
    """Database CHECK/UNIQUE constraint would be violated."""

    def __init__(self, invariant: str, details: Mapping[str, object] | None = None) -> None:
        super().__init__(
            "PERSISTENCE_INVARIANT",
            f"Persistence invariant violated: {invariant}",
            field="persistence",
            details=details if details is not None else {"invariant": invariant},
        )


# ── Scheme source archive ───────────────────────────────────────────────────


class SchemeSourceArchiveIntegrityError(OrchestrationDomainError):
    """SchemeSourceArchiveV1 verification failed."""

    def __init__(self, archive_hash: str) -> None:
        super().__init__(
            "SCHEME_SOURCE_ARCHIVE_INVALID",
            f"Scheme source archive integrity failure (hash {archive_hash!r})",
            field="archive_hash",
            details={"archive_hash": archive_hash},
        )


# ── Transaction B terminal disposition ───────────────────────────────────────


class AttemptTerminalDisposition(StrEnum):
    """Structured terminal classification for orchestration attempts."""

    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
