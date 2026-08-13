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
    digest = "a" * 64
    coefficient_id = "coefficient-s6-07"
    revision_id = "revision-s6-07"
    context_id = "context-s6-07"
    run_id = "scheme-run-s6-07"
    return {
        "schema_version": acceptance.S6_07_RAW_OBSERVATION_SCHEMA,
        "observation_type": "raw",
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
            "build_identity": {
                "file_present": True,
                "commit_sha": SOURCE_SHA,
                "version": "v0.2.0",
            },
            "migration": {"exit_code": 0, "current_output": "34 (head)\n"},
            "container": {"running": True, "status": "running"},
            "liveness": {"status": 200, "body": {"status": "live"}},
            "readiness": {
                "status": 200,
                "body": {
                    "status": "ready",
                    "capabilities": [
                        {
                            "name": "model_backed_agent",
                            "status": "disabled",
                            "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
                        }
                    ],
                },
            },
            "database": {
                "backend": "postgresql",
                "service_class": "DatabaseCoefficientService",
                "composition_manifest": {
                    "active_coefficient_service_class": "DatabaseCoefficientService",
                    "active_service_bound_to_canonical_engine": True,
                    "tokens": ["DATABASE_COEFFICIENT_SERVICE_INSTANTIATED"],
                },
            },
            "artifact_storage": {"probe_exists": True, "probe_sha256": digest},
        },
        "production_http_scope": {
            "coefficient": {
                "created": {"status": 200, "body": {"id": coefficient_id}},
                "readback": {"status": 200, "body": {"id": coefficient_id}},
                "persisted_row_id": coefficient_id,
            },
            "controlled_coefficient": {
                "http_definition_id": coefficient_id,
                "persisted_definition_id": coefficient_id,
                "approved_revision_definition_id": coefficient_id,
                "approved_revision_id": revision_id,
                "active_authority_revision_id": revision_id,
            },
            "planning_agent": {
                "response": {
                    "status": 503,
                    "body": {
                        "error": {
                            "code": "AGENT_CAPABILITY_OUT_OF_PRODUCTION_SCOPE",
                            "details": {"retryable": False},
                        }
                    },
                }
            },
        },
        "persistence_e2e": {
            "scheme": {
                "create_response": {"status": 200, "body": {"run_id": run_id}},
                "persisted_readback": {
                    "status": 200,
                    "body": {"run_id": run_id, "status": "completed"},
                },
                "http_readback": {
                    "status": 200,
                    "body": {"run_id": run_id, "status": "completed"},
                },
                "canonical_persistence": {
                    "run_id": run_id,
                    "status": "completed",
                    "source_mode": "production",
                    "stages": [
                        {
                            "name": name,
                            "exists": True,
                            "persisted": True,
                            "calculation_id": f"{name}-calculation",
                            "calculation_type": name,
                            "result_hash": digest,
                            "requires_review": name == "investment",
                        }
                        for name in acceptance.S6_07_STAGE_NAMES
                    ],
                    "source_binding": {
                        "exists": True,
                        "scheme_run_id": run_id,
                        "source_binding_id": "source-binding-s6-07",
                        "coefficient_context_id": context_id,
                        "required_slot_ids": [
                            f"{name}-calculation" for name in acceptance.S6_07_STAGE_NAMES
                        ],
                        "per_calculation_result_hashes": {
                            name: digest for name in acceptance.S6_07_STAGE_NAMES
                        },
                        "content_sha256": digest,
                    },
                    "coefficient_resolution": {
                        "coefficient_id": context_id,
                        "source_type": "catalog",
                        "selection_strategy": "source_binding_exact_id",
                        "source_binding_id": "source-binding-s6-07",
                    },
                    "controlled_coefficient": {
                        "definition_id": coefficient_id,
                        "approved_revision_id": revision_id,
                        "active_authority_revision_id": revision_id,
                    },
                    "coefficient_execution_continuity": {
                        "result": "NOT_REQUIRED_BY_V0_2_OPERATIONAL_ACCEPTANCE",
                        "available": False,
                    },
                    "power_authority": {
                        "slot_id": "power",
                        "calculation_id": "power-calculation",
                        "scheme_run_id": run_id,
                        "source_binding_id": "source-binding-s6-07",
                        "value_present": True,
                        "value_sha256": digest,
                    },
                    "source_archive": {
                        "exists": True,
                        "scheme_run_id": run_id,
                        "sha256": digest,
                        "expected_sha256": digest,
                        "verification_method": "canonical_archive_v1",
                        "independent_rehash": True,
                    },
                },
            },
            "restart": {
                "performed": True,
                "readiness": {"status": 200, "body": {"status": "ready"}},
                "coefficient_readback": {"id": coefficient_id},
                "scheme_persisted_readback": {
                    "status": 200,
                    "body": {"run_id": run_id, "status": "completed"},
                },
                "source_binding_after_restart": {
                    "exists": True,
                    "scheme_run_id": run_id,
                    "source_binding_id": "source-binding-s6-07",
                    "coefficient_context_id": context_id,
                    "required_slot_ids": [
                        f"{name}-calculation" for name in acceptance.S6_07_STAGE_NAMES
                    ],
                    "per_calculation_result_hashes": {
                        name: digest for name in acceptance.S6_07_STAGE_NAMES
                    },
                    "content_sha256": digest,
                    "reloaded_after_restart": True,
                },
                "source_archive_verification_after_restart": {
                    "exists": True,
                    "scheme_run_id": run_id,
                    "sha256": digest,
                    "expected_sha256": digest,
                    "verification_method": "canonical_archive_v1",
                    "independent_rehash": True,
                    "reloaded_after_restart": True,
                },
                "artifact_probe": {"exists": True, "sha256": digest},
            },
        },
        "observability_security": {
            "correlation": {
                "header_present": True,
                "expected": "s6-07-test-correlation",
                "observed": "s6-07-test-correlation",
            },
            "structured_logging": {
                "record_count": 3,
                "parseable_record_count": 3,
                "correlation_match_count": 2,
            },
            "redaction": {
                "password_occurrences": 0,
                "database_url_occurrences": 0,
                "token_occurrences": 0,
            },
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


def _assert_derived_failure(data: dict[str, object], expected: str) -> None:
    with pytest.raises(acceptance.S607AcceptanceError) as exc:
        acceptance._derive_assertions(  # noqa: SLF001
            data,
            source_sha=SOURCE_SHA,
            source_tree_sha=SOURCE_TREE_SHA,
        )
    assert exc.value.failure_code == expected


def _mutable_observations() -> dict[str, object]:
    return json.loads(json.dumps(_observations()))


def test_valid_synthetic_acceptance_roundtrip_is_exactly_nine_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _assemble(tmp_path, monkeypatch)
    assert tuple(sorted(path.name for path in bundle.iterdir())) == tuple(
        sorted(acceptance.S6_07_BUNDLE_FILES)
    )
    acceptance.verify_s6_07_checksums(bundle)


def test_catalog_coefficient_context_provenance_is_accepted() -> None:
    acceptance._derive_assertions(  # noqa: SLF001
        _mutable_observations(),
        source_sha=SOURCE_SHA,
        source_tree_sha=SOURCE_TREE_SHA,
    )


@pytest.mark.parametrize(
    "source_type",
    ["demo", "production_persisted_context", "engineering_judgement"],
)
def test_non_catalog_coefficient_context_provenance_fails_closed(source_type: str) -> None:
    data = _mutable_observations()
    data["persistence_e2e"]["scheme"]["canonical_persistence"]["coefficient_resolution"][
        "source_type"
    ] = source_type
    _assert_derived_failure(data, "S6_07_PERSISTENCE_FAILED")


def test_scheme_create_response_is_not_accepted_as_persisted_readback() -> None:
    data = _mutable_observations()
    persistence = data["persistence_e2e"]
    scheme = persistence["scheme"]
    scheme["persisted_readback"] = scheme["create_response"]
    _assert_derived_failure(data, "S6_07_PERSISTENCE_FAILED")


def test_source_binding_must_be_reloaded_after_restart() -> None:
    data = _mutable_observations()
    restart_binding = data["persistence_e2e"]["restart"]["source_binding_after_restart"]
    restart_binding["source_binding_id"] = "different-source-binding"
    _assert_derived_failure(data, "S6_07_PERSISTENCE_FAILED")


def test_runtime_coefficient_authority_requires_active_composition_token() -> None:
    data = _mutable_observations()
    data["runtime_lifecycle"]["database"]["composition_manifest"]["tokens"] = []
    _assert_derived_failure(data, "S6_07_COEFFICIENT_AUTHORITY_INVALID")


def test_requires_review_warning_is_not_operational_failure() -> None:
    data = _mutable_observations()
    stages = data["persistence_e2e"]["scheme"]["canonical_persistence"]["stages"]
    for stage in stages:
        stage["requires_review"] = True
    acceptance._derive_assertions(  # noqa: SLF001
        data,
        source_sha=SOURCE_SHA,
        source_tree_sha=SOURCE_TREE_SHA,
    )


def test_importable_database_coefficient_class_is_not_sufficient_authority() -> None:
    data = _mutable_observations()
    composition = data["runtime_lifecycle"]["database"]["composition_manifest"]
    composition["active_coefficient_service_class"] = "DatabaseCoefficientService"
    composition["active_service_bound_to_canonical_engine"] = True
    composition["tokens"] = []
    _assert_derived_failure(data, "S6_07_COEFFICIENT_AUTHORITY_INVALID")


def test_fake_agent_composition_token_causes_fail_closed() -> None:
    data = _mutable_observations()
    data["runtime_lifecycle"]["database"]["composition_manifest"]["tokens"].append(
        "FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED"
    )
    _assert_derived_failure(data, "S6_07_FAKE_AGENT_REACHABLE")


def test_persisted_scheme_run_identity_must_match_create_run_id() -> None:
    data = _mutable_observations()
    data["persistence_e2e"]["scheme"]["persisted_readback"]["body"]["run_id"] = "other-run"
    _assert_derived_failure(data, "S6_07_PERSISTENCE_FAILED")


def test_source_archive_digest_must_be_independently_verified() -> None:
    data = _mutable_observations()
    data["persistence_e2e"]["scheme"]["canonical_persistence"]["source_archive"][
        "expected_sha256"
    ] = "b" * 64
    _assert_derived_failure(data, "S6_07_PERSISTENCE_FAILED")


def test_power_authority_must_bind_to_same_run() -> None:
    data = _mutable_observations()
    data["persistence_e2e"]["scheme"]["canonical_persistence"]["power_authority"][
        "scheme_run_id"
    ] = "other-run"
    _assert_derived_failure(data, "S6_07_PERSISTENCE_FAILED")


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
            lambda data: data["production_http_scope"]["planning_agent"]["response"].update(
                {"status": 200}
            ),
            "S6_07_PRODUCTION_HTTP_SCOPE_FAILED",
        ),
        (
            lambda data: data["production_http_scope"]["coefficient"].update(
                {"persisted_row_id": "wrong"}
            ),
            "S6_07_COEFFICIENT_AUTHORITY_INVALID",
        ),
        (
            lambda data: data["runtime_lifecycle"]["readiness"].update({"status": 503}),
            "S6_07_READINESS_FAILED",
        ),
        (
            lambda data: data["persistence_e2e"]["restart"]["coefficient_readback"].update(
                {"id": "wrong"}
            ),
            "S6_07_PERSISTENCE_FAILED",
        ),
        (
            lambda data: data["observability_security"]["redaction"].update(
                {"password_occurrences": 1}
            ),
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
    runtime["readiness"]["status"] = 503
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
    assert exc.value.failure_code == "S6_07_READINESS_FAILED"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda data: data["persistence_e2e"]["scheme"]["canonical_persistence"].update(
                {"stages": []}
            ),
            "S6_07_PERSISTENCE_FAILED",
        ),
        (
            lambda data: data["persistence_e2e"]["scheme"]["canonical_persistence"].pop(
                "source_binding"
            ),
            "S6_07_EVIDENCE_BUNDLE_INVALID",
        ),
        (
            lambda data: data["persistence_e2e"]["scheme"]["canonical_persistence"][
                "coefficient_resolution"
            ].update({"source_type": "demo"}),
            "S6_07_PERSISTENCE_FAILED",
        ),
        (
            lambda data: data["persistence_e2e"]["scheme"]["canonical_persistence"].pop(
                "power_authority"
            ),
            "S6_07_EVIDENCE_BUNDLE_INVALID",
        ),
        (
            lambda data: data["persistence_e2e"]["scheme"]["canonical_persistence"][
                "source_archive"
            ].update({"expected_sha256": "b" * 64}),
            "S6_07_PERSISTENCE_FAILED",
        ),
        (
            lambda data: data["runtime_lifecycle"]["readiness"]["body"]["capabilities"][0].update(
                {"status": "enabled"}
            ),
            "S6_07_FAKE_AGENT_REACHABLE",
        ),
    ],
)
def test_forged_all_pass_observations_without_runtime_proof_fail_closed(
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
