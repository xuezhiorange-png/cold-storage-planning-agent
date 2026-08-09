"""Integration wiring tests using a synthetic OCI-producing Docker command."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import pytest

import cold_storage.release.live_evidence_runner as live_runner
from cold_storage.release.live_evidence_runner import (
    EXPECTED_SOURCE_COMMIT_SHA,
    LiveEvidenceRunnerError,
    assemble_evidence,
    capture_local,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _mock_docker_script(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """
            #!/usr/bin/env python3
            import hashlib
            import json
            import os
            import sys
            import tarfile
            import tempfile
            from pathlib import Path

            args = sys.argv[1:]
            log_path = os.environ["MOCK_DOCKER_LOG"]
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(" ".join(args) + "\\n")

            if "--help" in args:
                print(
                    "--output type=oci,dest=path --metadata-file --platform "
                    "--no-cache --provenance --sbom"
                )
                raise SystemExit(0)

            if args[:2] == ["buildx", "inspect"]:
                print(
                    "Name: synthetic\\nDriver: docker-container\\n"
                    "Platforms: linux/amd64, linux/arm64"
                )
                raise SystemExit(0)

            def value_after(flag):
                return args[args.index(flag) + 1]

            output_spec = value_after("--output")
            destination = Path(output_spec.split("dest=", 1)[1])
            metadata = Path(value_after("--metadata-file"))
            if os.environ.get("MOCK_SKIP_B") == "1" and "build-b" in destination.as_posix():
                raise SystemExit(0)

            annotation = "same"
            if (
                os.environ.get("MOCK_DIGEST_MODE") == "drift"
                and "build-b" in destination.as_posix()
            ):
                annotation = "different"
            config = b"synthetic-config"
            config_digest = "sha256:" + hashlib.sha256(config).hexdigest()
            manifest = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {
                    "mediaType": "application/vnd.oci.image.config.v1+json",
                    "digest": config_digest,
                    "size": len(config),
                },
                "layers": [],
                "annotations": {"synthetic": annotation},
            }
            manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
            manifest_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "blobs" / "sha256").mkdir(parents=True)
                (root / "oci-layout").write_text(
                    '{"imageLayoutVersion":"1.0.0"}\\n', encoding="utf-8"
                )
                (root / "blobs" / "sha256" / config_digest.removeprefix("sha256:")).write_bytes(
                    config
                )
                (
                    root / "blobs" / "sha256" / manifest_digest.removeprefix("sha256:")
                ).write_bytes(manifest_bytes)
                index = {
                    "schemaVersion": 2,
                    "manifests": [
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": manifest_digest,
                            "size": len(manifest_bytes),
                        }
                    ],
                }
                (root / "index.json").write_text(json.dumps(index) + "\\n", encoding="utf-8")
                with tarfile.open(destination, "w") as archive:
                    for item in root.rglob("*"):
                        archive.add(item, arcname=item.relative_to(root).as_posix())
            metadata.parent.mkdir(parents=True, exist_ok=True)
            metadata.write_text(
                json.dumps({"synthetic": True, "manifest": manifest_digest}),
                encoding="utf-8",
            )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _configure_mock_docker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    _mock_docker_script(docker)
    log = tmp_path / "docker-calls.log"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("MOCK_DOCKER_LOG", str(log))
    monkeypatch.setenv("TASK012_BUILD_A_B_AUTHORIZED", "YES")
    return log


def _write_test_attestation(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "mechanism": "write_once_integrity",
                "binding": "TEST_ONLY:SYNTHETIC_ONLY",
                "issuer": "TEST_ONLY",
            }
        ),
        encoding="utf-8",
    )


def test_capture_and_assemble_happy_path_are_independent_and_local_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = _configure_mock_docker(monkeypatch, tmp_path)
    observation_dir = tmp_path / "observation"
    bundle_path = capture_local(
        output_dir=observation_dir,
        tooling_root=PROJECT_ROOT,
        execute_builds=True,
        expected_source_sha=EXPECTED_SOURCE_COMMIT_SHA,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if "--output" in line]
    assert len(calls) == 2
    assert all("--no-cache" in call for call in calls)
    assert all("--push" not in call for call in calls)
    assert all("linux/amd64" in call for call in calls)
    assert all(PROJECT_ROOT.as_posix() not in call for call in calls)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert (
        bundle["build_a"]["build_record"]["build_run_id"]
        != bundle["build_b"]["build_record"]["build_run_id"]
    )
    assert bundle["build_a"]["output_path"] != bundle["build_b"]["output_path"]
    assert (
        bundle["build_a"]["build_input_manifest_path"]
        != bundle["build_b"]["build_input_manifest_path"]
    )
    assert bundle["build_a"]["build_record"]["registry_manifest_digest"] is None
    assert bundle["build_a"]["manifest_observation"]["image_id_used"] is False

    attestation = tmp_path / "attestation.json"
    _write_test_attestation(attestation)
    evidence_path = assemble_evidence(
        observation_bundle=bundle_path,
        attestation_file=attestation,
        output_dir=tmp_path / "assembled",
        tooling_root=PROJECT_ROOT,
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["authoritative_image_digest"].startswith("sha256:")
    assert (evidence_path.parent / "artifact-manifest.json").is_file()
    assert (evidence_path.parent / "provenance.json").is_file()
    assert (evidence_path.parent / "SHA256SUMS").is_file()


def test_build_b_digest_drift_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    monkeypatch.setenv("MOCK_DIGEST_MODE", "drift")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        capture_local(
            output_dir=tmp_path / "observation",
            tooling_root=PROJECT_ROOT,
            execute_builds=True,
        )
    assert exc.value.code == "BUILD_DIGEST_DRIFT"


def test_build_b_must_produce_an_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    monkeypatch.setenv("MOCK_SKIP_B", "1")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        capture_local(
            output_dir=tmp_path / "observation",
            tooling_root=PROJECT_ROOT,
            execute_builds=True,
        )
    assert exc.value.code == "BUILD_OUTPUT_MISSING"


def test_tampered_observed_declaration_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    bundle_path = capture_local(
        output_dir=tmp_path / "observation",
        tooling_root=PROJECT_ROOT,
        execute_builds=True,
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["build_a"]["build_record"]["build_input_manifest_digest"] = "sha256:" + "0" * 64
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    attestation = tmp_path / "attestation.json"
    _write_test_attestation(attestation)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=bundle_path,
            attestation_file=attestation,
            output_dir=tmp_path / "assembled",
            tooling_root=PROJECT_ROOT,
        )
    assert exc.value.code == "CHECKSUM_DIGEST_MISMATCH"


def test_shared_output_path_is_rejected_during_assembly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    bundle_path = capture_local(
        output_dir=tmp_path / "observation",
        tooling_root=PROJECT_ROOT,
        execute_builds=True,
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["build_b"]["output_path"] = bundle["build_a"]["output_path"]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    attestation = tmp_path / "attestation.json"
    _write_test_attestation(attestation)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=bundle_path,
            attestation_file=attestation,
            output_dir=tmp_path / "assembled",
            tooling_root=PROJECT_ROOT,
        )
    assert exc.value.code == "CHECKSUM_DIGEST_MISMATCH"


@pytest.mark.parametrize(
    "relative_path",
    [
        "metadata.json",
        "expected-inputs.json",
        "build-a/observed-inputs.json",
        "build-a/build-record.json",
        "observation-bundle.json",
    ],
)
def test_tampered_capture_payload_is_rejected_before_collector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, relative_path: str
) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    bundle_path = capture_local(
        output_dir=tmp_path / "observation",
        tooling_root=PROJECT_ROOT,
        execute_builds=True,
    )
    target = bundle_path.parent / relative_path
    target.write_bytes(target.read_bytes() + b"tampered")
    attestation = tmp_path / "attestation.json"
    _write_test_attestation(attestation)

    def collector_must_not_run(**_: object) -> None:
        raise AssertionError("collector must not receive an unchecked package")

    monkeypatch.setattr(live_runner, "collect_release_candidate_evidence", collector_must_not_run)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=bundle_path,
            attestation_file=attestation,
            output_dir=tmp_path / "assembled",
            tooling_root=PROJECT_ROOT,
        )
    assert exc.value.code == "CHECKSUM_DIGEST_MISMATCH"


def test_checksum_sidecar_and_manifest_tampering_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    bundle_path = capture_local(
        output_dir=tmp_path / "observation",
        tooling_root=PROJECT_ROOT,
        execute_builds=True,
    )
    root = bundle_path.parent
    _write_test_attestation(tmp_path / "attestation.json")
    sidecar = root / "SHA256SUMS.sha256"
    sidecar.write_text("0" * 64 + "\n", encoding="ascii")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=bundle_path,
            attestation_file=tmp_path / "attestation.json",
            output_dir=tmp_path / "assembled",
            tooling_root=PROJECT_ROOT,
        )
    assert exc.value.code == "CHECKSUM_SIDECAR_MISMATCH"

    live_runner._write_checksums(root)
    (root / "SHA256SUMS").write_bytes((root / "SHA256SUMS").read_bytes() + b"\n")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=bundle_path,
            attestation_file=tmp_path / "attestation.json",
            output_dir=tmp_path / "assembled-again",
            tooling_root=PROJECT_ROOT,
        )
    assert exc.value.code == "CHECKSUM_SIDECAR_MISMATCH"


def test_missing_listed_capture_payload_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    bundle_path = capture_local(
        output_dir=tmp_path / "observation",
        tooling_root=PROJECT_ROOT,
        execute_builds=True,
    )
    (bundle_path.parent / "metadata.json").unlink()
    _write_test_attestation(tmp_path / "attestation.json")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=bundle_path,
            attestation_file=tmp_path / "attestation.json",
            output_dir=tmp_path / "assembled",
            tooling_root=PROJECT_ROOT,
        )
    assert exc.value.code == "CHECKSUM_FILE_MISSING"


def test_unlisted_capture_payload_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_mock_docker(monkeypatch, tmp_path)
    bundle_path = capture_local(
        output_dir=tmp_path / "observation",
        tooling_root=PROJECT_ROOT,
        execute_builds=True,
    )
    (bundle_path.parent / "unexpected.txt").write_text("extra", encoding="utf-8")
    _write_test_attestation(tmp_path / "attestation.json")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=bundle_path,
            attestation_file=tmp_path / "attestation.json",
            output_dir=tmp_path / "assembled",
            tooling_root=PROJECT_ROOT,
        )
    assert exc.value.code == "CHECKSUM_COVERAGE_MISMATCH"
