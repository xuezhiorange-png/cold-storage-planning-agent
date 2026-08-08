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

    # --- no rebuild during promotion ---
    rebuild_flag = record.get("rebuild_performed")
    if rebuild_flag:
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
