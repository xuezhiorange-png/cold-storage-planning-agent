"""Environment promotion provenance (S2_GAP_05).

Implements the promotion record schema and verifier frozen in Section 10
of the contract.  Promotion NEVER rebuilds the image; it pulls the exact
immutable digest that was built and verified in the source environment.
This round implements and tests the promotion *evidence* mechanism only
— no real staging or production promotion is executed.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from cold_storage.release.canonical_serialization import (
    CanonicalSerializationError,
    ReleaseEvidenceError,
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    reject_secret_values,
)
from cold_storage.release.digest_verifier import is_mutable_tag
from cold_storage.release.provenance_schema import (
    ALLOWED_ENVIRONMENTS,
    ALLOWED_PROMOTION_EDGES,
    PROMOTION_RECORD_FIELD_ORDER,
    PROMOTION_RECORD_SCHEMA_VERSION,
    RC_APPROVER_MISSING,
    RC_ENV_CONFIG_DIGEST_MISSING,
    RC_PROMOTION_DIGEST_DRIFT,
    RC_PROMOTION_MUTABLE_TAG,
    RC_PROMOTION_REBUILD,
    RC_PROMOTION_RECORD_UNVERIFIABLE,
)

DIGEST_PREFIX = "sha256:"


class PromotionError(ReleaseEvidenceError):
    """Failure raised by promotion-record operations."""


REQUIRED_PROMOTION_FIELDS = (
    "schema_version",
    "rc_version",
    "source_environment",
    "target_environment",
    "final_image_digest",
    "artifact_manifest_digest",
    "provenance_digest",
    "deployment_definition_digest",
    "environment_config_digest",
    "promoted_by",
    "approved_by",
    "promotion_timestamp",
    "verification_result",
)

# Fields that are allowed but not strictly required.
# rebuild_performed is optional: when omitted it defaults to False
# (no rebuild).  When present and True, the promotion is rejected.
OPTIONAL_PROMOTION_FIELDS = frozenset({"rebuild_performed"})


def _ordered(fields: Mapping[str, Any]) -> OrderedDict[str, Any]:
    """Return a new ordered dict in the frozen schema field order.

    Unknown keys are rejected (fail-closed) to prevent silent field
    dropping during canonicalization.
    """
    known = set(PROMOTION_RECORD_FIELD_ORDER)
    for key in fields:
        if key not in known:
            raise PromotionError(
                failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
                detail=f"unknown promotion field rejected (fail-closed): {key!r}",
            )
    out: OrderedDict[str, Any] = OrderedDict()
    for key in PROMOTION_RECORD_FIELD_ORDER:
        if key in fields:
            out[key] = fields[key]
    return out


def _validate_closed_schema(record: Mapping[str, Any]) -> None:
    """Reject unknown fields before any business logic (fail-closed).

    Ensures that verify_promotion() — the direct verifier entry point —
    applies the same closed-schema rejection that _ordered() applies
    during serialize/load.  Without this, a caller passing a record
    with an extra field (e.g. ``evil_extra_field``) directly to
    verify_promotion() would bypass the unknown-field rejection.
    """
    known = set(PROMOTION_RECORD_FIELD_ORDER)
    for key in record:
        if key not in known:
            raise PromotionError(
                failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
                detail=f"unknown promotion field rejected (fail-closed): {key!r}",
            )


def compute_promotion_record_digest(record: Mapping[str, Any]) -> str:
    """Return ``sha256:<hex>`` of the canonical promotion record bytes."""
    return canonical_digest(_ordered(record))


def serialize_promotion_record(record: Mapping[str, Any]) -> bytes:
    return canonical_bytes(_ordered(record))


def load_promotion_record_from_text(raw: str) -> OrderedDict[str, Any]:
    try:
        data = load_json_strict(raw)
    except CanonicalSerializationError as exc:
        raise PromotionError(
            failure_code="RC_PROMOTION_RECORD_UNVERIFIABLE",
            detail=exc.detail,
        ) from exc
    return _ordered(data)


def verify_promotion(
    record: Mapping[str, Any],
    *,
    rc_image_digest: str,
    rc_artifact_manifest_digest: str,
    rc_provenance_digest: str,
    prior_environment_digest: str | None = None,
) -> None:
    """Verify a promotion record against the RC identity and promotion rules.

    Parameters
    ----------
    record:
        The promotion record dict.
    rc_image_digest:
        The authoritative final image digest bound to the RC identity.
    rc_artifact_manifest_digest:
        The authoritative artifact manifest digest.
    rc_provenance_digest:
        The authoritative provenance digest.
    prior_environment_digest:
        The image digest recorded for the *source* environment (when
        promoting staging→production, the staging digest).  Used to
        detect cross-environment digest drift.  ``None`` is acceptable
        only for the first promotion (ci→staging).
    """
    # --- closed-schema validation (fail-closed, B2) ---
    # Reject unknown fields before any business logic.  This prevents
    # callers from bypassing the serialize/load path's unknown-field
    # rejection by calling verify_promotion() directly.
    _validate_closed_schema(record)

    # --- structural completeness ---
    if record.get("schema_version") != PROMOTION_RECORD_SCHEMA_VERSION:
        raise PromotionError(
            failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
            detail="promotion record schema_version mismatch",
        )
    for name in REQUIRED_PROMOTION_FIELDS:
        if name not in record or record[name] in (None, ""):
            if name == "environment_config_digest":
                raise PromotionError(
                    failure_code=RC_ENV_CONFIG_DIGEST_MISSING,
                    detail="environment_config_digest missing",
                )
            if name == "approved_by":
                raise PromotionError(
                    failure_code=RC_APPROVER_MISSING,
                    detail="promotion record lacks approver identity",
                )
            raise PromotionError(
                failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
                detail=f"missing required promotion field: {name}",
            )

    # --- environment sequence ---
    source_env = record.get("source_environment")
    target_env = record.get("target_environment")
    if source_env not in ALLOWED_ENVIRONMENTS or target_env not in ALLOWED_ENVIRONMENTS:
        raise PromotionError(
            failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
            detail=f"invalid environment pair: {source_env}→{target_env}",
        )
    if (source_env, target_env) not in ALLOWED_PROMOTION_EDGES:
        raise PromotionError(
            failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
            detail=f"cross-level promotion prohibited: {source_env}→{target_env}",
        )

    # --- immutable digest reference (no mutable tag) ---
    image_ref = record.get("final_image_digest")
    if not isinstance(image_ref, str) or is_mutable_tag(image_ref):
        raise PromotionError(
            failure_code=RC_PROMOTION_MUTABLE_TAG,
            detail="promotion references a mutable tag instead of a digest",
        )

    # --- no rebuild during promotion (strict boolean enforcement, B2) ---
    # rebuild_performed is optional: when omitted it defaults to False
    # (no rebuild).  When present, it MUST be a strict Python bool.
    # Truthiness is NOT acceptable: 0, 1, "false", "true", "", [], {},
    # None are all rejected as RC_PROMOTION_RECORD_UNVERIFIABLE.
    # Note: Python bool is an int subclass, so we use type(value) is bool
    # rather than isinstance(value, bool) which would also accept int.
    if "rebuild_performed" in record:
        rebuild_flag = record["rebuild_performed"]
        if type(rebuild_flag) is not bool:
            raise PromotionError(
                failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
                detail=(
                    "rebuild_performed must be a strict boolean, "
                    f"got {type(rebuild_flag).__name__}: {rebuild_flag!r}"
                ),
            )
        if rebuild_flag is True:
            raise PromotionError(
                failure_code=RC_PROMOTION_REBUILD,
                detail="promotion stage rebuilt the image",
            )

    # --- environment config digest recorded ---
    env_config = record.get("environment_config_digest")
    if not isinstance(env_config, str) or not env_config.startswith(DIGEST_PREFIX):
        raise PromotionError(
            failure_code=RC_ENV_CONFIG_DIGEST_MISSING,
            detail="environment_config_digest is not a valid digest",
        )

    # --- approver / promoter boundary (no self-approval) ---
    promoted_by = record.get("promoted_by")
    approved_by = record.get("approved_by")
    if not approved_by:
        raise PromotionError(
            failure_code=RC_APPROVER_MISSING,
            detail="promotion record lacks approver identity",
        )
    if promoted_by == approved_by:
        raise PromotionError(
            failure_code=RC_APPROVER_MISSING,
            detail="self-approval prohibited: approver equals promoter",
        )

    # --- pre-promotion re-verification: digests match RC identity ---
    if image_ref != rc_image_digest:
        raise PromotionError(
            failure_code=RC_PROMOTION_DIGEST_DRIFT,
            detail="promotion image digest does not match RC identity",
        )
    if record.get("artifact_manifest_digest") != rc_artifact_manifest_digest:
        raise PromotionError(
            failure_code=RC_PROMOTION_DIGEST_DRIFT,
            detail="promotion artifact manifest digest drift",
        )
    if record.get("provenance_digest") != rc_provenance_digest:
        raise PromotionError(
            failure_code=RC_PROMOTION_DIGEST_DRIFT,
            detail="promotion provenance digest drift",
        )

    # --- cross-environment digest drift ---
    if prior_environment_digest is not None and prior_environment_digest != rc_image_digest:
        raise PromotionError(
            failure_code=RC_PROMOTION_DIGEST_DRIFT,
            detail="source environment image digest differs from RC identity",
        )

    # --- verification result ---
    if record.get("verification_result") != "PASS":
        raise PromotionError(
            failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
            detail="promotion verification_result is not PASS",
        )

    # --- secret scan ---
    try:
        reject_secret_values(record)
    except CanonicalSerializationError as exc:
        raise PromotionError(
            failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
            detail=f"secret value detected: {exc.detail}",
        ) from exc


def verify_promotion_chain(
    records: list[Mapping[str, Any]],
    *,
    rc_image_digest: str,
    rc_artifact_manifest_digest: str,
    rc_provenance_digest: str,
) -> None:
    """Verify an ordered promotion chain ``ci → staging → production``.

    Each record is verified individually, and the image digest is checked
    to be identical across every environment (digest drift rejection).
    """
    if not records:
        raise PromotionError(
            failure_code=RC_PROMOTION_RECORD_UNVERIFIABLE,
            detail="empty promotion chain",
        )
    prior_digest: str | None = None
    seen_envs: set[str] = set()
    for record in records:
        verify_promotion(
            record,
            rc_image_digest=rc_image_digest,
            rc_artifact_manifest_digest=rc_artifact_manifest_digest,
            rc_provenance_digest=rc_provenance_digest,
            prior_environment_digest=prior_digest,
        )
        target = record.get("target_environment")
        if target in seen_envs:
            raise PromotionError(
                failure_code=RC_PROMOTION_DIGEST_DRIFT,
                detail=f"environment promoted twice: {target}",
            )
        seen_envs.add(str(target))
        prior_digest = rc_image_digest


__all__ = [
    "PromotionError",
    "REQUIRED_PROMOTION_FIELDS",
    "compute_promotion_record_digest",
    "load_promotion_record_from_text",
    "serialize_promotion_record",
    "verify_promotion",
    "verify_promotion_chain",
]
