"""Promotion record unit tests (S2_GAP_05)."""

from __future__ import annotations

from collections import OrderedDict

import pytest

from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.promotion_record import (
    PromotionError,
    compute_promotion_record_digest,
    verify_promotion,
    verify_promotion_chain,
)
from cold_storage.release.provenance_schema import (
    RC_APPROVER_MISSING,
    RC_ENV_CONFIG_DIGEST_MISSING,
    RC_PROMOTION_DIGEST_DRIFT,
    RC_PROMOTION_MUTABLE_TAG,
    RC_PROMOTION_REBUILD,
    RC_PROMOTION_RECORD_UNVERIFIABLE,
)

IMAGE = "sha256:" + "a" * 64
IMAGE_B = "sha256:" + "b" * 64
ARTIFACT = "sha256:" + "c" * 64
PROV = "sha256:" + "d" * 64
ENV = "sha256:" + "e" * 64


def _record() -> OrderedDict:
    return OrderedDict(
        [
            ("schema_version", "cold-storage-release-candidate-promotion-record-v1"),
            ("rc_version", "v0.2.0"),
            ("source_environment", "ci"),
            ("target_environment", "staging"),
            ("final_image_digest", IMAGE),
            ("artifact_manifest_digest", ARTIFACT),
            ("provenance_digest", PROV),
            ("deployment_definition_digest", "sha256:" + "20" * 32),
            ("environment_config_digest", ENV),
            ("rebuild_performed", False),
            ("promoted_by", "ci-bot"),
            ("approved_by", "release-manager"),
            ("promotion_timestamp", "2026-08-06T13:00:00Z"),
            ("verification_result", "PASS"),
        ]
    )


def _verify(record, *, prior=None) -> None:
    verify_promotion(
        record,
        rc_image_digest=IMAGE,
        rc_artifact_manifest_digest=ARTIFACT,
        rc_provenance_digest=PROV,
        prior_environment_digest=prior,
    )


def test_promotion_passes_for_valid_record() -> None:
    _verify(_record())


def test_promotion_rejects_mutable_tag() -> None:
    record = _record()
    record["final_image_digest"] = "cold-storage-backend:latest"
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_PROMOTION_MUTABLE_TAG


def test_promotion_rejects_rebuild() -> None:
    record = _record()
    record["rebuild_performed"] = True
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_PROMOTION_REBUILD


def test_promotion_rejects_env_config_missing() -> None:
    record = _record()
    record["environment_config_digest"] = ""
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_ENV_CONFIG_DIGEST_MISSING


def test_promotion_rejects_self_approval() -> None:
    record = _record()
    record["approved_by"] = "ci-bot"
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_APPROVER_MISSING


def test_promotion_rejects_missing_approver() -> None:
    record = _record()
    record["approved_by"] = ""
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_APPROVER_MISSING


def test_promotion_rejects_cross_level_ci_to_production() -> None:
    record = _record()
    record["target_environment"] = "production"
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_PROMOTION_RECORD_UNVERIFIABLE


def test_promotion_rejects_digest_drift_vs_rc() -> None:
    record = _record()
    record["final_image_digest"] = IMAGE_B
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert (
        exc.value.failure_code == RC_PROMOTION_MUTABLE_TAG
        or exc.value.failure_code == RC_PROMOTION_DIGEST_DRIFT
    )


def test_promotion_rejects_prior_environment_drift() -> None:
    record = _record()
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record, prior=IMAGE_B)
    assert exc.value.failure_code == RC_PROMOTION_DIGEST_DRIFT


def test_promotion_rejects_unverifiable_result() -> None:
    record = _record()
    record["verification_result"] = "FAIL"
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_PROMOTION_RECORD_UNVERIFIABLE


def test_promotion_chain_ci_to_staging_to_production_passes() -> None:
    staging = _record()
    production = _record()
    production["source_environment"] = "staging"
    production["target_environment"] = "production"
    verify_promotion_chain(
        [staging, production],
        rc_image_digest=IMAGE,
        rc_artifact_manifest_digest=ARTIFACT,
        rc_provenance_digest=PROV,
    )


def test_promotion_chain_rejects_skipping_staging() -> None:
    record = _record()
    record["target_environment"] = "production"
    with pytest.raises(PromotionError):
        verify_promotion_chain(
            [record],
            rc_image_digest=IMAGE,
            rc_artifact_manifest_digest=ARTIFACT,
            rc_provenance_digest=PROV,
        )


def test_promotion_record_digest_is_deterministic() -> None:
    record = _record()
    assert compute_promotion_record_digest(record) == compute_promotion_record_digest(record)
    assert compute_promotion_record_digest(record).startswith("sha256:")


def test_promotion_rejects_secret_in_record() -> None:
    record = _record()
    record["promoted_by"] = "postgresql://user:pass@host/db"
    with pytest.raises(ReleaseEvidenceError) as exc:
        _verify(record)
    assert exc.value.failure_code == RC_PROMOTION_RECORD_UNVERIFIABLE
