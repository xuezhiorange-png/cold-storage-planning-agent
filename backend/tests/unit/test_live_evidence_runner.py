"""Unit tests for the non-production Live Evidence observation boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

import cold_storage.release.live_evidence_runner as live_runner
from cold_storage.release.live_evidence_runner import (
    BuildxCapabilities,
    LiveEvidenceRunnerError,
    _ensure_distinct,
    _parser,
    _verify_capture_checksums,
    _write_checksums,
    buildx_build_command,
    extract_oci_manifest_digest,
    observe_oci_manifest,
    validate_capture_authorization,
    validate_expected_source,
)

OCI_EXPORTER_POLICY = {"type": "oci", "rewrite-timestamp": "true"}

MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_oci_layout(
    root: Path,
    *,
    descriptor_media_type: str = MANIFEST_MEDIA_TYPE,
    manifest_annotation: str | None = None,
) -> tuple[Path, str, str]:
    blobs = root / "blobs" / "sha256"
    blobs.mkdir(parents=True)
    (root / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}\n', encoding="utf-8")
    config = b"synthetic-config"
    config_digest = _digest(config)
    (blobs / config_digest.removeprefix("sha256:")).write_bytes(config)
    manifest: dict[str, object] = {
        "schemaVersion": 2,
        "mediaType": MANIFEST_MEDIA_TYPE,
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": config_digest,
            "size": len(config),
        },
        "layers": [],
    }
    if manifest_annotation is not None:
        manifest["annotations"] = {"synthetic": manifest_annotation}
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_digest = _digest(manifest_bytes)
    (blobs / manifest_digest.removeprefix("sha256:")).write_bytes(manifest_bytes)
    index = {
        "schemaVersion": 2,
        "manifests": [
            {
                "mediaType": descriptor_media_type,
                "digest": manifest_digest,
                "size": len(manifest_bytes),
            }
        ],
    }
    (root / "index.json").write_text(json.dumps(index) + "\n", encoding="utf-8")
    return root, manifest_digest, config_digest


def test_capture_guard_requires_cli_flag_before_external_commands() -> None:
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        validate_capture_authorization(
            execute_builds=False, env={"TASK012_BUILD_A_B_AUTHORIZED": "YES"}
        )
    assert exc.value.code == "BUILD_EXECUTION_NOT_EXPLICIT"


def test_capture_guard_requires_exact_authorization_environment() -> None:
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        validate_capture_authorization(
            execute_builds=True, env={"TASK012_BUILD_A_B_AUTHORIZED": "true"}
        )
    assert exc.value.code == "BUILD_EXECUTION_NOT_AUTHORIZED"


def test_wrong_source_assertion_fails_closed() -> None:
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        validate_expected_source("f" * 40)
    assert exc.value.code == "RC_SOURCE_ASSERTION_MISMATCH"


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["docker"], returncode, stdout=stdout, stderr="")


BUILDX_V035_HELP = "--output --metadata-file --platform --no-cache --provenance --sbom"


def test_buildx_selected_docker_driver_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if argv[-2:] == ["build", "--help"]:
            return _completed(BUILDX_V035_HELP)
        return _completed("Name: default\nDriver: docker\nPlatforms: linux/amd64\n")

    monkeypatch.setattr(live_runner, "_run_command", fake_run)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        live_runner._buildx_capabilities()
    assert exc.value.code == "BUILDX_DRIVER_UNSUPPORTED"


def test_buildx_selected_driver_without_target_platform_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if argv[-2:] == ["build", "--help"]:
            return _completed(BUILDX_V035_HELP)
        return _completed("Name: default\nDriver: docker-container\nPlatforms: linux/arm64\n")

    monkeypatch.setattr(live_runner, "_run_command", fake_run)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        live_runner._buildx_capabilities()
    assert exc.value.code == "BUILDX_TARGET_PLATFORM_UNAVAILABLE"


def test_buildx_selected_driver_and_target_platform_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if argv[-2:] == ["build", "--help"]:
            return _completed(BUILDX_V035_HELP)
        return _completed(
            "Name: default\nDriver: docker-container\nPlatforms: linux/amd64, linux/arm64\n"
        )

    monkeypatch.setattr(live_runner, "_run_command", fake_run)
    capabilities = live_runner._buildx_capabilities()
    assert capabilities.selected_driver == "docker-container"
    assert "linux/amd64" in capabilities.available_platforms


def test_buildx_inspect_bootstrap_failure_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if argv[-2:] == ["build", "--help"]:
            return _completed(BUILDX_V035_HELP)
        return _completed("builder failed", returncode=1)

    monkeypatch.setattr(live_runner, "_run_command", fake_run)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        live_runner._buildx_capabilities()
    assert exc.value.code == "BUILDX_DRIVER_UNSUPPORTED"


def test_buildx_v035_help_without_exporter_name_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[-2:] == ["build", "--help"]:
            return _completed(BUILDX_V035_HELP)
        return _completed(
            "Name: builder\nDriver: docker-container\n"
            "Platforms: linux/amd64, linux/amd64/v2, linux/386\n"
        )

    monkeypatch.setattr(live_runner, "_run_command", fake_run)
    capabilities = live_runner._buildx_capabilities()

    assert capabilities.selected_driver == "docker-container"
    assert "linux/amd64" in capabilities.available_platforms
    assert calls == [
        ["docker", "buildx", "build", "--help"],
        ["docker", "buildx", "inspect", "--bootstrap"],
    ]


@pytest.mark.parametrize(
    "missing_flag", ["--output", "--metadata-file", "--platform", "--no-cache"]
)
def test_buildx_required_help_flag_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, missing_flag: str
) -> None:
    help_text = " ".join(flag for flag in BUILDX_V035_HELP.split() if flag != missing_flag)

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if argv[-2:] == ["build", "--help"]:
            return _completed(help_text)
        return _completed("Name: builder\nDriver: docker-container\nPlatforms: linux/amd64\n")

    monkeypatch.setattr(live_runner, "_run_command", fake_run)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        live_runner._buildx_capabilities()
    assert exc.value.code == "OCI_EXPORTER_UNSUPPORTED"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_ignored_source_artifact_is_rejected_before_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored-marker\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("source\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "synthetic source")
    commit = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    (repo / "ignored-marker").write_text("runtime artifact\n", encoding="utf-8")
    monkeypatch.setattr(live_runner, "EXPECTED_SOURCE_COMMIT_SHA", commit)
    monkeypatch.setattr(live_runner, "EXPECTED_SOURCE_TREE_SHA", tree)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        live_runner._verify_source_worktree(repo)
    assert exc.value.code == "RC_SOURCE_WORKTREE_IGNORED_ARTIFACT"


def test_valid_oci_layout_rehashes_manifest_blob(tmp_path: Path) -> None:
    root, expected, config_digest = _write_oci_layout(tmp_path / "oci")
    assert extract_oci_manifest_digest(root) == expected
    observation = observe_oci_manifest(root)
    assert observation["descriptor_digest"] == expected
    assert observation["manifest_bytes_rehashed"] is True
    assert observation["image_id_used"] is False
    assert expected != config_digest


def test_valid_oci_tar_is_supported(tmp_path: Path) -> None:
    root, expected, _ = _write_oci_layout(tmp_path / "layout")
    archive = tmp_path / "image.oci.tar"
    with tarfile.open(archive, "w") as output:
        for path in root.rglob("*"):
            output.add(path, arcname=path.relative_to(root).as_posix())
    assert extract_oci_manifest_digest(archive) == expected


def test_descriptor_digest_tamper_is_rejected(tmp_path: Path) -> None:
    root, _, _ = _write_oci_layout(tmp_path / "oci")
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    index["manifests"][0]["digest"] = "sha256:" + "b" * 64
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        extract_oci_manifest_digest(root)
    assert exc.value.code == "OCI_MANIFEST_BLOB_MISSING"


def test_manifest_blob_tamper_is_rejected(tmp_path: Path) -> None:
    root, expected, _ = _write_oci_layout(tmp_path / "oci")
    (root / "blobs" / "sha256" / expected.removeprefix("sha256:")).write_bytes(b"tampered")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        extract_oci_manifest_digest(root)
    assert exc.value.code == "OCI_MANIFEST_BLOB_DIGEST_MISMATCH"


def test_missing_manifest_blob_is_rejected(tmp_path: Path) -> None:
    root, expected, _ = _write_oci_layout(tmp_path / "oci")
    (root / "blobs" / "sha256" / expected.removeprefix("sha256:")).unlink()
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        extract_oci_manifest_digest(root)
    assert exc.value.code == "OCI_MANIFEST_BLOB_MISSING"


def test_multiple_manifest_descriptors_are_rejected(tmp_path: Path) -> None:
    root, expected, _ = _write_oci_layout(tmp_path / "oci")
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    index["manifests"].append(index["manifests"][0])
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        extract_oci_manifest_digest(root)
    assert exc.value.code == "OCI_MANIFEST_AMBIGUOUS"


def test_index_media_type_is_rejected(tmp_path: Path) -> None:
    root, _, _ = _write_oci_layout(tmp_path / "oci", descriptor_media_type=INDEX_MEDIA_TYPE)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        extract_oci_manifest_digest(root)
    assert exc.value.code == "OCI_MEDIA_TYPE_UNSUPPORTED"


def test_build_command_has_independent_no_cache_oci_contract(tmp_path: Path) -> None:
    command_a = buildx_build_command(
        context=tmp_path / "a",
        output_path=tmp_path / "a.oci.tar",
        metadata_path=tmp_path / "a.metadata.json",
        build_run_id="capture:A",
        source_date_epoch=1786252367,
        docker_target_platform="linux/amd64",
        oci_exporter=OCI_EXPORTER_POLICY,
        capabilities=BuildxCapabilities(True, True),
    )
    command_b = buildx_build_command(
        context=tmp_path / "b",
        output_path=tmp_path / "b.oci.tar",
        metadata_path=tmp_path / "b.metadata.json",
        build_run_id="capture:B",
        source_date_epoch=1786252367,
        docker_target_platform="linux/amd64",
        oci_exporter=OCI_EXPORTER_POLICY,
        capabilities=BuildxCapabilities(True, True),
    )
    assert command_a != command_b
    assert "--no-cache" in command_a
    assert "--platform" in command_a
    assert "linux/amd64" in command_a
    output_spec = command_a[command_a.index("--output") + 1]
    assert output_spec.startswith("type=oci,dest=")
    assert output_spec.endswith(",rewrite-timestamp=true")
    assert "--metadata-file" in command_a
    assert "--provenance=false" in command_a
    assert "--sbom=false" in command_a
    assert "--push" not in command_a
    build_args = [
        command_a[index + 1] for index, item in enumerate(command_a[:-1]) if item == "--build-arg"
    ]
    assert not any(item.startswith("TARGET_PLATFORM=") for item in build_args)
    tag = command_a[command_a.index("--tag") + 1]
    assert tag.count(":") == 1
    assert tag.endswith("capture-a")


def test_build_command_binds_recorded_exporter_policy() -> None:
    command = buildx_build_command(
        context=Path("/tmp/rc-context"),
        output_path=Path("/tmp/build-a/image.oci.tar"),
        metadata_path=Path("/tmp/build-a/metadata.json"),
        build_run_id="capture:A",
        source_date_epoch=1786252367,
        docker_target_platform="linux/amd64",
        oci_exporter=OCI_EXPORTER_POLICY,
        capabilities=BuildxCapabilities(True, True),
    )
    output_spec = command[command.index("--output") + 1]
    assert output_spec == ("type=oci,dest=/tmp/build-a/image.oci.tar,rewrite-timestamp=true")


def test_build_command_rejects_false_rewrite_policy() -> None:
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        buildx_build_command(
            context=Path("/tmp/rc-context"),
            output_path=Path("/tmp/build-a/image.oci.tar"),
            metadata_path=Path("/tmp/build-a/metadata.json"),
            build_run_id="capture:A",
            source_date_epoch=1786252367,
            docker_target_platform="linux/amd64",
            oci_exporter={"type": "oci", "rewrite-timestamp": "false"},
            capabilities=BuildxCapabilities(True, True),
        )
    assert exc.value.code == "RC_BUILD_ARG_MISMATCH"


def test_run_identity_and_output_path_collision_fails() -> None:
    with pytest.raises(LiveEvidenceRunnerError):
        _ensure_distinct(["same", "same"], code="COLLISION")


def test_manual_manifest_digest_override_is_not_a_cli_argument() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(
            [
                "capture-local",
                "--execute-builds",
                "--output-dir",
                "/tmp/output",
                "--local-oci-digest",
                "sha256:" + "a" * 64,
            ]
        )


def test_assemble_requires_explicit_attestation_file(tmp_path: Path) -> None:
    from cold_storage.release.live_evidence_runner import assemble_evidence

    with pytest.raises(LiveEvidenceRunnerError) as exc:
        assemble_evidence(
            observation_bundle=tmp_path / "missing-bundle.json",
            attestation_file=tmp_path / "missing-attestation.json",
            output_dir=tmp_path / "assembled",
        )
    assert exc.value.code == "ATTESTATION_MISSING"


def _refresh_checksum_sidecar(root: Path) -> None:
    manifest = root / "SHA256SUMS"
    (root / "SHA256SUMS.sha256").write_text(
        hashlib.sha256(manifest.read_bytes()).hexdigest() + "\n", encoding="ascii"
    )


def test_checksum_path_traversal_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "capture"
    root.mkdir()
    (root / "payload.json").write_text("{}", encoding="utf-8")
    _write_checksums(root)
    digest = hashlib.sha256((root / "payload.json").read_bytes()).hexdigest()
    (root / "SHA256SUMS").write_text(f"{digest}  ../payload.json\n", encoding="ascii")
    _refresh_checksum_sidecar(root)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        _verify_capture_checksums(root)
    assert exc.value.code == "CHECKSUM_ENTRY_INVALID"


def test_checksum_duplicate_entry_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "capture"
    root.mkdir()
    (root / "payload.json").write_text("{}", encoding="utf-8")
    _write_checksums(root)
    line = (root / "SHA256SUMS").read_text(encoding="ascii")
    (root / "SHA256SUMS").write_text(line + line, encoding="ascii")
    _refresh_checksum_sidecar(root)
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        _verify_capture_checksums(root)
    assert exc.value.code == "CHECKSUM_DUPLICATE_ENTRY"


def test_checksum_exact_coverage_rejects_unlisted_file(tmp_path: Path) -> None:
    root = tmp_path / "capture"
    root.mkdir()
    (root / "payload.json").write_text("{}", encoding="utf-8")
    _write_checksums(root)
    (root / "extra.bin").write_bytes(b"unexpected")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        _verify_capture_checksums(root)
    assert exc.value.code == "CHECKSUM_COVERAGE_MISMATCH"


def test_checksum_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "capture"
    root.mkdir()
    (root / "payload.json").write_text("{}", encoding="utf-8")
    _write_checksums(root)
    (root / "payload-link").symlink_to(root / "payload.json")
    with pytest.raises(LiveEvidenceRunnerError) as exc:
        _verify_capture_checksums(root)
    assert exc.value.code == "CHECKSUM_SYMLINK_REJECTED"
