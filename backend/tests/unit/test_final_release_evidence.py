from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cold_storage.release.final_release_evidence import (
    _FROZEN_AUTHORITY_ROWS,
    EXPECTED_REPOSITORY,
    EXPECTED_SOURCE_SHA,
    EXPECTED_SOURCE_TREE_SHA,
    FINAL_BUNDLE_FILES,
    FINAL_JSON_FILES,
    FinalReleaseEvidenceError,
    _scan_secret_material,
    assemble_final_release_evidence,
    verify_final_release_evidence,
    write_frozen_authority_index,
)

GENERATED_AT = "2026-08-11T00:00:00Z"


def _write_index(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _index(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    path = tmp_path / "authority-index.json"
    write_frozen_authority_index(path)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _assemble(tmp_path: Path) -> Path:
    index_path, _ = _index(tmp_path)
    return assemble_final_release_evidence(
        authority_index=index_path,
        output_dir=tmp_path / "bundle",
        repository=EXPECTED_REPOSITORY,
        source_sha=EXPECTED_SOURCE_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        generated_at=GENERATED_AT,
    )


def _assert_index_rejected(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    expected_codes: set[str],
) -> None:
    index_path, value = _index(tmp_path)
    mutate(value)
    _write_index(index_path, value)
    with pytest.raises(FinalReleaseEvidenceError) as exc:
        assemble_final_release_evidence(
            authority_index=index_path,
            output_dir=tmp_path / "bundle",
            repository=EXPECTED_REPOSITORY,
            source_sha=EXPECTED_SOURCE_SHA,
            source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
            generated_at=GENERATED_AT,
        )
    assert exc.value.failure_code in expected_codes


def test_valid_seventeen_authority_closure_roundtrip_passes(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    verify_final_release_evidence(
        bundle_dir=bundle,
        repository=EXPECTED_REPOSITORY,
        source_sha=EXPECTED_SOURCE_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
    )
    assert {path.name for path in bundle.iterdir()} == set(FINAL_BUNDLE_FILES)
    summary = json.loads((bundle / "release-evidence-summary.json").read_text(encoding="utf-8"))
    assert summary["required_authority_count"] == 17
    assert summary["passed_authority_count"] == 17
    assert summary["release_evidence_result"] == "PASS"


def test_missing_required_authority_fails_closed(tmp_path: Path) -> None:
    _assert_index_rejected(
        tmp_path,
        lambda value: value["authorities"].pop(),
        {"REQUIRED_AUTHORITY_MISSING"},
    )


def test_failed_required_authority_fails_closed(tmp_path: Path) -> None:
    _assert_index_rejected(
        tmp_path,
        lambda value: value["authorities"][0].update({"verification_result": "FAIL"}),
        {"AUTHORITY_BINDING_MISMATCH", "REQUIRED_AUTHORITY_FAILED"},
    )


def test_ambiguous_authority_fails_closed(tmp_path: Path) -> None:
    def mutate(value: dict[str, Any]) -> None:
        value["authorities"][1]["authority_id"] = value["authorities"][0]["authority_id"]

    _assert_index_rejected(tmp_path, mutate, {"REQUIRED_AUTHORITY_AMBIGUOUS"})


@pytest.mark.parametrize(
    ("field", "code"),
    [("source_sha", "SOURCE_SHA_MISMATCH"), ("source_tree_sha", "SOURCE_TREE_MISMATCH")],
)
def test_wrong_source_identity_fails_closed(tmp_path: Path, field: str, code: str) -> None:
    _assert_index_rejected(
        tmp_path,
        lambda value: value.update({field: "0" * 40}),
        {code},
    )


def test_wrong_workflow_head_fails_closed(tmp_path: Path) -> None:
    def mutate(value: dict[str, Any]) -> None:
        value["authorities"][10]["workflow_head_sha"] = "1" * 40

    _assert_index_rejected(tmp_path, mutate, {"AUTHORITY_BINDING_MISMATCH"})


def test_wrong_artifact_digest_fails_closed(tmp_path: Path) -> None:
    def mutate(value: dict[str, Any]) -> None:
        value["authorities"][15]["artifact_digest"] = "sha256:" + "0" * 64

    _assert_index_rejected(tmp_path, mutate, {"AUTHORITY_BINDING_MISMATCH"})


def test_wrong_receipt_digest_fails_closed(tmp_path: Path) -> None:
    def mutate(value: dict[str, Any]) -> None:
        value["authorities"][11]["receipt_sha256"] = "sha256:" + "0" * 64

    _assert_index_rejected(tmp_path, mutate, {"AUTHORITY_BINDING_MISMATCH"})


def test_expired_artifact_without_durable_binding_fails_closed(tmp_path: Path) -> None:
    def mutate(value: dict[str, Any]) -> None:
        value["authorities"][15]["artifact_expired"] = True

    _assert_index_rejected(tmp_path, mutate, {"ARTIFACT_EXPIRED_WITHOUT_DURABLE_AUTHORITY"})


def test_s6_07_not_authorized_does_not_fail_s6_06(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    summary = json.loads((bundle / "release-evidence-summary.json").read_text(encoding="utf-8"))
    assert summary["s6_07_required_for_s6_06_pass"] is False
    assert summary["next_required_stage"] == "S6-07"
    assert summary["next_stage_status"] == "NOT_AUTHORIZED"
    assert summary["release_evidence_result"] == "PASS"


def test_extra_bundle_file_fails_closed(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    (bundle / "unexpected.txt").write_text("extra\n", encoding="utf-8")
    with pytest.raises(FinalReleaseEvidenceError) as exc:
        verify_final_release_evidence(
            bundle_dir=bundle,
            repository=EXPECTED_REPOSITORY,
            source_sha=EXPECTED_SOURCE_SHA,
            source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        )
    assert exc.value.failure_code == "BUNDLE_SHAPE_MISMATCH"


def test_missing_bundle_file_fails_closed(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    (bundle / "runtime-readiness-summary.json").unlink()
    with pytest.raises(FinalReleaseEvidenceError) as exc:
        verify_final_release_evidence(
            bundle_dir=bundle,
            repository=EXPECTED_REPOSITORY,
            source_sha=EXPECTED_SOURCE_SHA,
            source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        )
    assert exc.value.failure_code == "BUNDLE_SHAPE_MISMATCH"


def test_checksum_and_sidecar_mismatch_fail_closed(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    checksum = bundle / "SHA256SUMS"
    checksum.write_text("0" * 64 + "  release-evidence-summary.json\n", encoding="ascii")
    with pytest.raises(FinalReleaseEvidenceError) as exc:
        verify_final_release_evidence(
            bundle_dir=bundle,
            repository=EXPECTED_REPOSITORY,
            source_sha=EXPECTED_SOURCE_SHA,
            source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        )
    assert exc.value.failure_code in {"CHECKSUM_MISMATCH", "CHECKSUM_COVERAGE_MISMATCH"}

    bundle = _assemble(tmp_path / "sidecar")
    (bundle / "SHA256SUMS.sha256").write_text("0" * 64 + "  SHA256SUMS\n", encoding="ascii")
    with pytest.raises(FinalReleaseEvidenceError) as exc:
        verify_final_release_evidence(
            bundle_dir=bundle,
            repository=EXPECTED_REPOSITORY,
            source_sha=EXPECTED_SOURCE_SHA,
            source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        )
    assert exc.value.failure_code == "CHECKSUM_MISMATCH"


def test_secret_material_and_production_markers_fail_closed(tmp_path: Path) -> None:
    bundle = _assemble(tmp_path)
    summary_path = bundle / "release-evidence-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["authorization"] = "Bearer synthetic-secret"
    summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    with pytest.raises(FinalReleaseEvidenceError) as exc:
        verify_final_release_evidence(
            bundle_dir=bundle,
            repository=EXPECTED_REPOSITORY,
            source_sha=EXPECTED_SOURCE_SHA,
            source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        )
    assert exc.value.failure_code == "SECRET_MATERIAL_DETECTED"

    _assert_index_rejected(
        tmp_path / "production",
        lambda value: value["authorities"][15].update({"production": True}),
        {"PRODUCTION_OPERATION_DETECTED", "AUTHORITY_BINDING_MISMATCH"},
    )


def test_safe_audit_fields_are_not_secret_material() -> None:
    _scan_secret_material(
        {
            "no_secret_material_result": "PASS",
            "secret_redaction": "PASS",
            "credential_non_persistence": "PASS",
        }
    )


def _write_github_metadata(directory: Path) -> None:
    directory.mkdir()
    for row in _FROZEN_AUTHORITY_ROWS:
        run_id = row["workflow_run_id"]
        if run_id is not None:
            (directory / f"run-{run_id}.json").write_text(
                json.dumps(
                    {
                        "id": run_id,
                        "event": row["workflow_event"],
                        "head_branch": "main",
                        "head_sha": row["workflow_head_sha"],
                        "run_attempt": row["workflow_run_attempt"],
                        "status": "completed",
                        "conclusion": "success",
                        "path": row["workflow_path"],
                        "name": row["workflow_name"],
                    }
                ),
                encoding="utf-8",
            )
        artifact_id = row["artifact_id"]
        if artifact_id is not None:
            (directory / f"artifact-{artifact_id}.json").write_text(
                json.dumps(
                    {
                        "id": artifact_id,
                        "name": row["artifact_name"],
                        "expired": False,
                        "digest": row["artifact_digest"],
                        "workflow_run": {
                            "id": row["workflow_run_id"],
                            "head_sha": row["workflow_head_sha"],
                        },
                    }
                ),
                encoding="utf-8",
            )


def test_github_run_and_artifact_identity_fixture_is_verified(tmp_path: Path) -> None:
    index_path, _ = _index(tmp_path)
    metadata_dir = tmp_path / "github-metadata"
    _write_github_metadata(metadata_dir)
    bundle = assemble_final_release_evidence(
        authority_index=index_path,
        output_dir=tmp_path / "bundle",
        repository=EXPECTED_REPOSITORY,
        source_sha=EXPECTED_SOURCE_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        generated_at=GENERATED_AT,
        github_metadata_dir=metadata_dir,
    )
    assert bundle.is_dir()

    run_file = metadata_dir / "run-31493144331.json"
    run = json.loads(run_file.read_text(encoding="utf-8"))
    run["head_sha"] = "2" * 40
    run_file.write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(FinalReleaseEvidenceError) as exc:
        verify_final_release_evidence(
            bundle_dir=bundle,
            repository=EXPECTED_REPOSITORY,
            source_sha=EXPECTED_SOURCE_SHA,
            source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
            github_metadata_dir=metadata_dir,
        )
    assert exc.value.failure_code == "WORKFLOW_HEAD_MISMATCH"


def test_final_json_file_set_is_six() -> None:
    assert len(FINAL_JSON_FILES) == 6
    assert len(FINAL_BUNDLE_FILES) == 8
