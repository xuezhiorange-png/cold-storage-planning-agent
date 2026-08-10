"""Unit tests for the frozen Slice 2 live attestation contract."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

import pytest

from cold_storage.release.artifact_manifest import compute_manifest_digest
from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.digest_verifier import compute_build_input_manifest_digest
from cold_storage.release.evidence_collector import (
    BuildInputs,
    BuildRunRecord,
    finalize_prepared_release_evidence,
    prepare_pre_attestation_evidence,
    verify_evidence_bundle,
)
from cold_storage.release.live_attestation import (
    LiveAttestationError,
    build_attestation,
    compute_subject_digest,
    load_attestation,
    validate_attestation,
    validate_attestation_schema,
)
from cold_storage.release.provenance_schema import (
    EXPECTED_SOURCE_COMMIT_SHA,
    EXPECTED_SOURCE_TREE_SHA,
)

IMAGE = "sha256:" + "a" * 64
BASE = "sha256:" + "f" * 64
LOCK = "sha256:" + "1" * 64
P = "sha256:" + "2" * 64
M = "sha256:" + "3" * 64


def test_attestation_is_exact_eight_field_composite_subject() -> None:
    attestation = build_attestation(P, M)

    assert list(attestation) == [
        "schema_version",
        "task",
        "version",
        "slice",
        "mechanism",
        "subject_schema",
        "subject_digest_algorithm",
        "binding",
    ]
    assert attestation["mechanism"] == "write_once_integrity"
    assert attestation["binding"] == compute_subject_digest(P, M)
    assert (
        validate_attestation(
            attestation,
            expected_provenance_digest=P,
            expected_artifact_manifest_digest=M,
        )
        == attestation["binding"]
    )


def test_attestation_subject_requires_both_p_and_m() -> None:
    attestation = build_attestation(P, M)
    tampered = OrderedDict(attestation)
    tampered["binding"] = compute_subject_digest("sha256:" + "4" * 64, M)

    with pytest.raises(LiveAttestationError) as exc:
        validate_attestation(
            tampered,
            expected_provenance_digest=P,
            expected_artifact_manifest_digest=M,
        )
    assert exc.value.code == "ATTESTATION_SUBJECT_MISMATCH"


def test_attestation_rejects_synthetic_marker() -> None:
    attestation = build_attestation(P, M)
    attestation["task"] = "TEST_ONLY"

    with pytest.raises(LiveAttestationError) as exc:
        validate_attestation(
            attestation,
            expected_provenance_digest=P,
            expected_artifact_manifest_digest=M,
        )
    assert exc.value.code == "ATTESTATION_SYNTHETIC_REJECTED"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("schema_version", "wrong-schema", "ATTESTATION_SCHEMA_INVALID"),
        ("mechanism", "github_oidc", "ATTESTATION_MECHANISM_UNSUPPORTED"),
        ("binding", "sha256:bad", "ATTESTATION_BINDING_INVALID"),
    ],
)
def test_attestation_schema_failures_are_explicit(field: str, value: Any, error: str) -> None:
    attestation = build_attestation(P, M)
    attestation[field] = value
    with pytest.raises(LiveAttestationError) as exc:
        validate_attestation_schema(attestation)
    assert exc.value.code == error


def test_attestation_rejects_extra_and_missing_fields() -> None:
    extra = build_attestation(P, M)
    extra["unexpected"] = True
    with pytest.raises(LiveAttestationError, match="ATTESTATION_SCHEMA_INVALID"):
        validate_attestation_schema(extra)

    missing = build_attestation(P, M)
    del missing["binding"]
    with pytest.raises(LiveAttestationError, match="ATTESTATION_SCHEMA_INVALID"):
        validate_attestation_schema(missing)


def test_attestation_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    payload = (
        '{"schema_version":"cold-storage-live-attestation-v1",'
        '"schema_version":"cold-storage-live-attestation-v1"}'
    )
    path = tmp_path / "attestation.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(LiveAttestationError, match="ATTESTATION_SCHEMA_INVALID"):
        load_attestation(path)


def _inputs() -> BuildInputs:
    return BuildInputs(
        source_commit_sha=EXPECTED_SOURCE_COMMIT_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        source_date_epoch=1786252367,
        dockerfile_digest="sha256:" + "10" * 32,
        compose_file_digest="sha256:" + "11" * 32,
        workflow_definition_digest="sha256:" + "12" * 32,
        dependency_lockset_digest=LOCK,
        migration_set_digest="sha256:" + "13" * 32,
        base_image_digest_set=[BASE],
        build_args={
            "COLD_STORAGE_BUILD_COMMIT_SHA": EXPECTED_SOURCE_COMMIT_SHA,
            "COLD_STORAGE_BUILD_VERSION": "v0.2.0",
            "SOURCE_DATE_EPOCH": "1786252367",
        },
        oci_exporter={"type": "oci", "rewrite-timestamp": "true"},
    )


def _run(inputs: BuildInputs, run_id: str) -> BuildRunRecord:
    declared = compute_build_input_manifest_digest(inputs.to_input_manifest())
    return BuildRunRecord(
        build_run_id=run_id,
        build_run_attempt=1,
        build_trigger="workflow_dispatch",
        builder_identity="github-actions",
        build_started_at="2026-08-10T00:00:00Z",
        build_finished_at="2026-08-10T00:05:00Z",
        final_image_digest=IMAGE,
        local_oci_manifest_digest=IMAGE,
        registry_manifest_digest=None,
        base_image_tag="python:3.12-slim",
        base_image_digest=BASE,
        lockfile_digest=LOCK,
        build_input_manifest_digest=declared,
    )


def _prepared() -> Any:
    inputs_a = _inputs()
    inputs_b = _inputs()
    return prepare_pre_attestation_evidence(
        build_a_inputs=inputs_a,
        build_b_inputs=inputs_b,
        build_a=_run(inputs_a, "capture:A"),
        build_b=_run(inputs_b, "capture:B"),
        artifacts=[],
        test_result_reference="capture:test",
        verification_result_reference="capture:verify",
        expected_inputs=_inputs(),
    )


def test_preparation_and_finalization_bind_p_m_s() -> None:
    prepared = _prepared()
    attestation = build_attestation(
        prepared.provenance_digest,
        prepared.artifact_manifest_digest,
    )

    bundle = finalize_prepared_release_evidence(
        prepared,
        attestation,
        live_attestation=True,
    )

    assert bundle.provenance_digest == prepared.provenance_digest
    assert bundle.artifact_manifest_digest == prepared.artifact_manifest_digest
    assert attestation["binding"] == prepared.attestation_subject_digest
    verify_evidence_bundle(bundle)


def test_manifest_tamper_invalidates_live_binding() -> None:
    prepared = _prepared()
    attestation = build_attestation(prepared.provenance_digest, prepared.artifact_manifest_digest)
    prepared.artifact_manifest["final_image_digest"] = "sha256:" + "b" * 64

    with pytest.raises(ReleaseEvidenceError):
        finalize_prepared_release_evidence(prepared, attestation, live_attestation=True)


def test_manifest_tamper_with_synchronized_manifest_subject_rejects_old_binding() -> None:
    prepared = _prepared()
    attestation = build_attestation(prepared.provenance_digest, prepared.artifact_manifest_digest)
    prepared.artifact_manifest["final_image_digest"] = "sha256:" + "b" * 64
    new_manifest_digest = compute_manifest_digest(prepared.artifact_manifest)
    prepared.pre_attestation_provenance["subject_artifact_manifest_digest"] = new_manifest_digest
    object.__setattr__(prepared, "artifact_manifest_digest", new_manifest_digest)

    with pytest.raises(ReleaseEvidenceError) as exc:
        finalize_prepared_release_evidence(prepared, attestation, live_attestation=True)
    assert exc.value.failure_code == "ATTESTATION_SUBJECT_MISMATCH"


def test_provenance_tamper_invalidates_live_binding() -> None:
    prepared = _prepared()
    attestation = build_attestation(prepared.provenance_digest, prepared.artifact_manifest_digest)
    prepared.pre_attestation_provenance["builder_identity"] = "tampered"

    with pytest.raises(ReleaseEvidenceError) as exc:
        finalize_prepared_release_evidence(prepared, attestation, live_attestation=True)
    assert exc.value.failure_code == "ATTESTATION_SUBJECT_MISMATCH"
