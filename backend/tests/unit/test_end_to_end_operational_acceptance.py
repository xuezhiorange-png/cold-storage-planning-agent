from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from cold_storage.release import end_to_end_operational_acceptance as acceptance
from cold_storage.release.final_release_evidence import FINAL_BUNDLE_FILES as S6_06_BUNDLE_FILES

SOURCE_SHA = "c287aba48201ac9bfc0786f62911cd25fabf3fc4"
SOURCE_TREE_SHA = "4ebca3e13cdc2a8395c4b877b6f2ed9d54d334be"
S6_06_RUN_ID = 31553885227
S6_06_ARTIFACT_ID = 9125247786
S6_06_DIGEST = "sha256:153ee7502ff4fcccb04468172d2e6de8e0266ba23193e155930488d2fdf7f1e8"


def _observations() -> dict[str, object]:
    return {
        "task": "TASK-012",
        "version": "V0.2",
        "slice": 6,
        "item": "S6-07",
        "source_sha": SOURCE_SHA,
        "source_tree_sha": SOURCE_TREE_SHA,
        "controlled_synthetic": True,
        "real_production_data": False,
        "real_production_operation": False,
        "runtime_lifecycle": {
            "image_build": "PASS",
            "build_identity_file": "PASS",
            "build_commit_sha_match": "PASS",
            "build_version": "v0.2.0",
            "migration_service": "PASS",
            "alembic_exact_head": "PASS",
            "backend_startup": "PASS",
            "liveness": "PASS",
            "readiness": "PASS",
            "canonical_database_engine": "PASS",
            "canonical_artifact_storage": "PASS",
            "strict_capability_audit": "PASS",
        },
        "production_http_scope": {
            "coefficient_routes_mounted": True,
            "coefficient_backend": "DatabaseCoefficientService",
            "coefficient_engine_is_canonical_engine": True,
            "database_failure_fallback_to_in_memory": False,
            "coefficient_lifecycle_readback": "PASS",
            "planning_agent_route_mounted": True,
            "planning_agent_backend": "DISABLED",
            "planning_agent_http_status": 503,
            "planning_agent_error_code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
            "planning_agent_retryable": False,
            "fake_agent_gateway_constructed_in_strict_mode": False,
            "fake_agent_result_returned": False,
        },
        "persistence_e2e": {
            "zone_stage": "PASS",
            "cooling_load_stage": "PASS",
            "equipment_stage": "PASS",
            "power_stage": "PASS",
            "investment_stage": "PASS",
            "source_binding": "VERIFIED",
            "scheme_run": "PASS",
            "no_demo_coefficient_used": True,
            "no_latest_row_fallback": True,
            "no_partial_source_binding": True,
            "power_authority_binding": "PASS",
            "source_archive_verification": "PASS",
            "restart_performed": True,
            "readiness_after_restart": "PASS",
            "database_state_persisted": "PASS",
            "coefficient_state_persisted": "PASS",
            "source_binding_state_persisted": "PASS",
            "artifact_state_persisted": "PASS",
        },
        "observability_security": {
            "correlation_id": "PASS",
            "structured_logging": "PASS",
            "sensitive_value_redaction": "PASS",
            "database_url_not_emitted": "PASS",
            "password_not_emitted": "PASS",
            "token_not_emitted": "PASS",
            "production_disabled_capability_observable": "PASS",
        },
    }


def _write_s6_06_fixture(tmp_path: Path) -> tuple[Path, Path]:
    bundle = tmp_path / "s6-06"
    metadata = tmp_path / "metadata"
    bundle.mkdir(parents=True)
    metadata.mkdir(parents=True)
    (bundle / "source-identity.json").write_text(
        json.dumps(
            {
                "source_sha": SOURCE_SHA,
                "source_tree_sha": SOURCE_TREE_SHA,
                "verification_result": "PASS",
            }
        ),
        encoding="utf-8",
    )
    for name in S6_06_BUNDLE_FILES:
        if name != "source-identity.json":
            (bundle / name).write_text("fixture\n", encoding="utf-8")
    (metadata / f"run-{S6_06_RUN_ID}.json").write_text(
        json.dumps(
            {
                "id": S6_06_RUN_ID,
                "event": "workflow_dispatch",
                "head_branch": "main",
                "head_sha": SOURCE_SHA,
                "run_attempt": 1,
                "status": "completed",
                "conclusion": "success",
                "path": acceptance.S6_06_WORKFLOW_PATH,
                "name": acceptance.S6_06_WORKFLOW_NAME,
            }
        ),
        encoding="utf-8",
    )
    (metadata / f"artifact-{S6_06_ARTIFACT_ID}.json").write_text(
        json.dumps(
            {
                "id": S6_06_ARTIFACT_ID,
                "name": f"task012-s6-06-final-release-evidence-{S6_06_RUN_ID}-1",
                "digest": S6_06_DIGEST,
                "expired": False,
                "workflow_run": {"id": S6_06_RUN_ID, "head_branch": "main", "head_sha": SOURCE_SHA},
            }
        ),
        encoding="utf-8",
    )
    return bundle, metadata


def _assemble(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path)
    monkeypatch.setattr(acceptance, "verify_final_release_evidence", lambda **_: None)
    output = tmp_path / "bundle"
    return acceptance.assemble_s6_07_acceptance_evidence(
        output_dir=output,
        repository=acceptance.EXPECTED_REPOSITORY,
        source_sha=SOURCE_SHA,
        source_tree_sha=SOURCE_TREE_SHA,
        generated_at="2026-08-12T00:00:00Z",
        s6_06_run_id=S6_06_RUN_ID,
        s6_06_run_attempt=1,
        s6_06_artifact_id=S6_06_ARTIFACT_ID,
        s6_06_artifact_digest=S6_06_DIGEST,
        s6_06_bundle_dir=s6_06_bundle,
        s6_06_metadata_dir=metadata,
        observations=_observations(),
    )


def test_valid_synthetic_acceptance_roundtrip_is_exactly_nine_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _assemble(tmp_path, monkeypatch)
    assert tuple(sorted(path.name for path in bundle.iterdir())) == tuple(
        sorted(acceptance.S6_07_BUNDLE_FILES)
    )
    acceptance.verify_s6_07_checksums(bundle)


def test_source_identity_is_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path)
    (s6_06_bundle / "source-identity.json").unlink()
    monkeypatch.setattr(acceptance, "verify_final_release_evidence", lambda **_: None)
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.assemble_s6_07_acceptance_evidence(
            output_dir=tmp_path / "bundle",
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            generated_at="2026-08-12T00:00:00Z",
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=s6_06_bundle,
            s6_06_metadata_dir=metadata,
            observations=_observations(),
        )
    assert exc.value.failure_code == "S6_07_S6_06_AUTHORITY_MISSING"


def test_invalid_source_sha_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.assemble_s6_07_acceptance_evidence(
            output_dir=tmp_path / "bundle",
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha="0" * 40,
            source_tree_sha=SOURCE_TREE_SHA,
            generated_at="2026-08-12T00:00:00Z",
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=tmp_path / "missing",
            s6_06_metadata_dir=tmp_path / "missing-metadata",
            observations=_observations(),
        )
    assert exc.value.failure_code == "S6_07_SOURCE_SHA_MISMATCH"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda data: data["production_http_scope"].update({"planning_agent_http_status": 200}),
            "S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
        ),
        (
            lambda data: data["production_http_scope"].update(
                {"coefficient_backend": "CoefficientService"}
            ),
            "S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
        ),
        (
            lambda data: data["runtime_lifecycle"].update({"readiness": "FAIL"}),
            "S6_07_RUNTIME_STARTUP_FAILED",
        ),
        (
            lambda data: data["persistence_e2e"].update({"database_state_persisted": "FAIL"}),
            "S6_07_PERSISTENCE_FAILED",
        ),
        (
            lambda data: data["observability_security"].update({"token": "ghp_secret"}),
            "S6_07_SECRET_MATERIAL_DETECTED",
        ),
    ],
)
def test_observation_contracts_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    expected: str,
) -> None:
    data = _observations()
    mutation(data)
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path)
    monkeypatch.setattr(acceptance, "verify_final_release_evidence", lambda **_: None)
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.assemble_s6_07_acceptance_evidence(
            output_dir=tmp_path / "bundle",
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            generated_at="2026-08-12T00:00:00Z",
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=s6_06_bundle,
            s6_06_metadata_dir=metadata,
            observations=data,
        )
    assert exc.value.failure_code == expected


def test_s6_06_missing_metadata_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path)
    (metadata / f"run-{S6_06_RUN_ID}.json").unlink()
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.verify_s6_06_prerequisite(
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=s6_06_bundle,
            s6_06_metadata_dir=metadata,
        )
    assert exc.value.failure_code == "S6_07_S6_06_AUTHORITY_MISSING"


def test_s6_06_expired_artifact_fails_closed(tmp_path: Path) -> None:
    bundle, metadata = _write_s6_06_fixture(tmp_path)
    artifact_path = metadata / f"artifact-{S6_06_ARTIFACT_ID}.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["expired"] = True
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.verify_s6_06_prerequisite(
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=bundle,
            s6_06_metadata_dir=metadata,
        )
    assert exc.value.failure_code == "S6_07_S6_06_ARTIFACT_EXPIRED"


def test_s6_06_artifact_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    bundle, metadata = _write_s6_06_fixture(tmp_path)
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.verify_s6_06_prerequisite(
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest="sha256:" + "0" * 64,
            s6_06_bundle_dir=bundle,
            s6_06_metadata_dir=metadata,
        )
    assert exc.value.failure_code == "S6_07_S6_06_DIGEST_MISMATCH"


def test_s6_06_source_mismatch_fails_closed(tmp_path: Path) -> None:
    bundle, metadata = _write_s6_06_fixture(tmp_path)
    source_identity = json.loads((bundle / "source-identity.json").read_text(encoding="utf-8"))
    source_identity["source_sha"] = "0" * 40
    (bundle / "source-identity.json").write_text(json.dumps(source_identity), encoding="utf-8")
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.verify_s6_06_prerequisite(
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=bundle,
            s6_06_metadata_dir=metadata,
        )
    assert exc.value.failure_code == "S6_07_S6_06_AUTHORITY_MISMATCH"


def test_forged_summary_pass_does_not_override_failed_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _assemble(tmp_path, monkeypatch)
    runtime_path = bundle / "runtime-lifecycle-observations.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["readiness"] = "FAIL"
    runtime_path.write_bytes(acceptance.canonical_bytes(runtime))
    sums = "".join(
        f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n"
        for name in acceptance.S6_07_JSON_FILES
    )
    (bundle / "SHA256SUMS").write_text(sums, encoding="ascii")
    (bundle / "SHA256SUMS.sha256").write_text(
        f"{hashlib.sha256((bundle / 'SHA256SUMS').read_bytes()).hexdigest()}  SHA256SUMS\n",
        encoding="ascii",
    )
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path / "remote")
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.verify_s6_07_acceptance_evidence(
            bundle_dir=bundle,
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=s6_06_bundle,
            s6_06_metadata_dir=metadata,
        )
    assert exc.value.failure_code == "S6_07_RUNTIME_STARTUP_FAILED"


def test_missing_observation_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _observations()
    del data["persistence_e2e"]
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path)
    monkeypatch.setattr(acceptance, "verify_final_release_evidence", lambda **_: None)
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.assemble_s6_07_acceptance_evidence(
            output_dir=tmp_path / "bundle",
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            generated_at="2026-08-12T00:00:00Z",
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=s6_06_bundle,
            s6_06_metadata_dir=metadata,
            observations=data,
        )
    assert exc.value.failure_code == "S6_07_EVIDENCE_BUNDLE_INVALID"


def test_production_operation_marker_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _observations()
    data["real_production_operation"] = True
    s6_06_bundle, metadata = _write_s6_06_fixture(tmp_path)
    monkeypatch.setattr(acceptance, "verify_final_release_evidence", lambda **_: None)
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.assemble_s6_07_acceptance_evidence(
            output_dir=tmp_path / "bundle",
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            generated_at="2026-08-12T00:00:00Z",
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=s6_06_bundle,
            s6_06_metadata_dir=metadata,
            observations=data,
        )
    assert exc.value.failure_code == "S6_07_PRODUCTION_HTTP_SCOPE_FAILED"


def test_checksum_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _assemble(tmp_path, monkeypatch)
    (bundle / "runtime-lifecycle-observations.json").write_text("{}", encoding="utf-8")
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.verify_s6_07_checksums(bundle)
    assert exc.value.failure_code == "S6_07_CHECKSUM_MISMATCH"


def test_extra_and_missing_bundle_files_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _assemble(tmp_path, monkeypatch)
    (bundle / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(acceptance.S607AcceptanceError) as extra_exc:
        acceptance.verify_s6_07_acceptance_evidence(
            bundle_dir=bundle,
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=tmp_path / "s6-06",
            s6_06_metadata_dir=tmp_path / "metadata",
        )
    assert extra_exc.value.failure_code == "S6_07_EVIDENCE_BUNDLE_INVALID"

    (bundle / "extra.txt").unlink()
    (bundle / "source-identity.json").unlink()
    with pytest.raises(acceptance.S607AcceptanceError) as missing_exc:
        acceptance.verify_s6_07_acceptance_evidence(
            bundle_dir=bundle,
            repository=acceptance.EXPECTED_REPOSITORY,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
            s6_06_run_id=S6_06_RUN_ID,
            s6_06_run_attempt=1,
            s6_06_artifact_id=S6_06_ARTIFACT_ID,
            s6_06_artifact_digest=S6_06_DIGEST,
            s6_06_bundle_dir=tmp_path / "s6-06",
            s6_06_metadata_dir=tmp_path / "metadata",
        )
    assert missing_exc.value.failure_code == "S6_07_EVIDENCE_BUNDLE_INVALID"


def test_checksum_manifest_is_portable_from_downloaded_bundle_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _assemble(tmp_path, monkeypatch)
    result = subprocess.run(
        ["sha256sum", "-c", "SHA256SUMS"],
        cwd=bundle,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_zip_path_traversal_fails_closed(tmp_path: Path) -> None:
    import zipfile

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("../escape.txt", "bad")
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance.extract_s6_06_artifact_archive(archive, tmp_path / "extract")
    assert exc.value.failure_code == "S6_07_S6_06_VERIFICATION_FAILED"
