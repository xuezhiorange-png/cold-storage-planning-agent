"""Non-production Live Evidence observation and assembly runner.

The runner is the external-observation boundary for TASK-012 Slice 2.  It
owns Git, Docker Buildx, filesystem, and OCI-layout observations, then adapts
those observations to the existing pure evidence collector.  It does not
change the frozen provenance authority and it never supplies an attestation
implicitly.

``capture-local`` is deliberately guarded twice: the command-line switch and
``TASK012_BUILD_A_B_AUTHORIZED=YES`` are both required before Docker is
invoked.  ``assemble`` has no Docker side effect; it requires an explicit
attestation file and re-checks the observed OCI outputs before calling the
existing collector.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from cold_storage.release.canonical_serialization import (
    canonical_bytes,
    load_json_strict,
)
from cold_storage.release.digest_verifier import (
    EXPECTED_OCI_EXPORTER_POLICY,
    ReproducibleBuildError,
    compute_build_input_manifest_digest,
    normalize_oci_exporter_policy,
    validate_oci_exporter_policy,
)
from cold_storage.release.evidence_collector import (
    BuildInputs,
    BuildRunRecord,
    EvidenceBundle,
    collect_release_candidate_evidence,
)
from cold_storage.release.provenance_schema import (
    EXPECTED_BUILD_PLATFORM,
    EXPECTED_DOCKER_TARGET_PLATFORM,
    EXPECTED_SOURCE_COMMIT_SHA,
    EXPECTED_SOURCE_TREE_SHA,
    RC_VERSION,
)

OBSERVATION_SCHEMA_VERSION = "cold-storage-live-evidence-observation-v1"
EVIDENCE_BUNDLE_OUTPUT_SCHEMA_VERSION = "cold-storage-live-evidence-bundle-v1"
RUNNER_MODULE = Path(__file__).resolve()

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BASE_IMAGE_RE = re.compile(r"^\s*FROM\s+(?P<reference>[^\s]+)", re.MULTILINE)
_OCI_MANIFEST_MEDIA_TYPES = frozenset(
    {
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    }
)


class LiveEvidenceRunnerError(Exception):
    """Fail-closed error raised by the external observation boundary."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class BuildxCapabilities:
    """Buildx options required by the local OCI observation contract."""

    supports_provenance_switch: bool
    supports_sbom_switch: bool
    selected_driver: str = ""
    available_platforms: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OCIManifestObservation:
    """An OCI manifest digest recomputed from its manifest blob bytes."""

    digest: str
    media_type: str
    blob_sha256: str
    output_format: str = "oci-layout"

    def to_document(self) -> OrderedDict[str, Any]:
        return OrderedDict(
            [
                ("output_format", self.output_format),
                ("descriptor_media_type", self.media_type),
                ("descriptor_digest", self.digest),
                ("manifest_blob_sha256", self.blob_sha256),
                ("manifest_bytes_rehashed", True),
                ("image_id_used", False),
            ]
        )


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise LiveEvidenceRunnerError("FILE_OBSERVATION_FAILED", f"expected regular file: {path}")
    return _sha256_bytes(path.read_bytes())


def _validated_oci_exporter_policy(value: Any) -> dict[str, str]:
    """Adapt pure manifest-policy failures to the runner error boundary."""
    try:
        return dict(validate_oci_exporter_policy(value))
    except ReproducibleBuildError as exc:
        raise LiveEvidenceRunnerError(exc.failure_code, exc.detail) from exc


def _directory_digest(path: Path) -> str:
    if not path.is_dir() or path.is_symlink():
        raise LiveEvidenceRunnerError("FILE_OBSERVATION_FAILED", f"expected directory: {path}")
    entries: OrderedDict[str, str] = OrderedDict()
    for child in sorted(path.rglob("*")):
        if not child.is_file() or child.is_symlink():
            continue
        entries[child.relative_to(path).as_posix()] = _sha256_file(child)
    return _sha256_bytes(canonical_bytes(entries))


def _run_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external command with argv separation and no shell."""
    return subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        env=dict(env) if env is not None else None,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )


def _command_detail(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "command failed").strip()
    return detail[-500:]


def _checked_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    code: str,
) -> str:
    result = _run_command(argv, cwd=cwd, env=env)
    if result.returncode != 0:
        raise LiveEvidenceRunnerError(code, _command_detail(result))
    return result.stdout.strip()


def _git(root: Path, args: Sequence[str], *, code: str = "GIT_OBSERVATION_FAILED") -> str:
    return _checked_command(["git", "-C", str(root), *args], code=code)


def _read_json_object(path: Path, *, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise LiveEvidenceRunnerError(code, f"JSON file is missing: {path}")
    try:
        value = load_json_strict(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LiveEvidenceRunnerError(code, f"invalid JSON at {path}: {exc}") from exc
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def _require_digest(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise LiveEvidenceRunnerError("DIGEST_FORMAT_INVALID", f"{label} is not a sha256 digest")
    return value


def _resolve_tooling_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise LiveEvidenceRunnerError(
            "TOOLING_ROOT_INVALID", f"tooling root is not a directory: {root}"
        )
    return root


def _prepare_output_dir(value: str | Path, *, tooling_root: Path) -> Path:
    output = Path(value).expanduser().resolve()
    if output == tooling_root or output.is_relative_to(tooling_root):
        raise LiveEvidenceRunnerError(
            "OUTPUT_PATH_UNSAFE",
            "evidence output must not be inside the execution checkout",
        )
    if output.exists():
        if not output.is_dir():
            raise LiveEvidenceRunnerError(
                "OUTPUT_PATH_COLLISION", f"output is not a directory: {output}"
            )
        if any(output.iterdir()):
            raise LiveEvidenceRunnerError(
                "OUTPUT_PATH_COLLISION", f"output directory is not empty: {output}"
            )
    else:
        output.mkdir(parents=True, exist_ok=False)
    return output


def validate_capture_authorization(*, execute_builds: bool, env: Mapping[str, str]) -> None:
    """Require both explicit execution controls before any Docker call."""
    if not execute_builds:
        raise LiveEvidenceRunnerError(
            "BUILD_EXECUTION_NOT_EXPLICIT",
            "capture-local requires --execute-builds",
        )
    if env.get("TASK012_BUILD_A_B_AUTHORIZED") != "YES":
        raise LiveEvidenceRunnerError(
            "BUILD_EXECUTION_NOT_AUTHORIZED",
            "TASK012_BUILD_A_B_AUTHORIZED must be exactly YES",
        )


def validate_expected_source(source_sha: str | None) -> None:
    """Treat a CLI source value as an assertion, never as an override."""
    if source_sha is not None and source_sha != EXPECTED_SOURCE_COMMIT_SHA:
        raise LiveEvidenceRunnerError(
            "RC_SOURCE_ASSERTION_MISMATCH",
            "expected source assertion does not match the frozen RC source",
        )


def _verify_frozen_source(tooling_root: Path) -> None:
    _checked_command(
        [
            "git",
            "-C",
            str(tooling_root),
            "cat-file",
            "-e",
            f"{EXPECTED_SOURCE_COMMIT_SHA}^{{commit}}",
        ],
        code="RC_SOURCE_COMMIT_MISSING",
    )
    actual_tree = _git(
        tooling_root,
        ["rev-parse", f"{EXPECTED_SOURCE_COMMIT_SHA}^{{tree}}"],
        code="RC_SOURCE_TREE_INVALID",
    )
    if actual_tree != EXPECTED_SOURCE_TREE_SHA:
        raise LiveEvidenceRunnerError(
            "RC_SOURCE_TREE_MISMATCH",
            f"frozen RC tree is {actual_tree}, expected {EXPECTED_SOURCE_TREE_SHA}",
        )


def _verify_tooling_identity(tooling_root: Path) -> tuple[str, str]:
    head = _git(tooling_root, ["rev-parse", "HEAD"])
    tree = _git(tooling_root, ["rev-parse", "HEAD^{tree}"])
    return head, tree


def _verify_source_worktree(path: Path) -> None:
    head = _git(path, ["rev-parse", "HEAD"])
    if head != EXPECTED_SOURCE_COMMIT_SHA:
        raise LiveEvidenceRunnerError("RC_SOURCE_WORKTREE_HEAD_MISMATCH", str(path))
    tree = _git(path, ["rev-parse", "HEAD^{tree}"])
    if tree != EXPECTED_SOURCE_TREE_SHA:
        raise LiveEvidenceRunnerError("RC_SOURCE_WORKTREE_TREE_MISMATCH", str(path))
    status = _git(path, ["status", "--porcelain=v1", "--untracked-files=all"])
    if status:
        raise LiveEvidenceRunnerError("RC_SOURCE_WORKTREE_DIRTY", f"{path}: {status}")
    ignored = _git(path, ["status", "--porcelain=v1", "--ignored", "--untracked-files=all"])
    ignored_paths = [line for line in ignored.splitlines() if line.startswith("!!")]
    if ignored_paths:
        raise LiveEvidenceRunnerError(
            "RC_SOURCE_WORKTREE_IGNORED_ARTIFACT",
            f"{path}: {', '.join(ignored_paths)}",
        )


class _OwnedWorktrees:
    """Create and remove only the temporary worktrees owned by one run."""

    def __init__(self, tooling_root: Path) -> None:
        self.tooling_root = tooling_root
        self.temp_root: Path | None = None
        self.paths: tuple[Path, Path] | None = None

    def __enter__(self) -> tuple[Path, Path]:
        self.temp_root = Path(tempfile.mkdtemp(prefix="task012-live-evidence-"))
        path_a = self.temp_root / "build-a"
        path_b = self.temp_root / "build-b"
        self.paths = (path_a, path_b)
        try:
            for path in (path_a, path_b):
                _checked_command(
                    [
                        "git",
                        "-C",
                        str(self.tooling_root),
                        "worktree",
                        "add",
                        "--detach",
                        str(path),
                        EXPECTED_SOURCE_COMMIT_SHA,
                    ],
                    code="RC_SOURCE_WORKTREE_CREATE_FAILED",
                )
                _verify_source_worktree(path)
        except Exception:
            self._cleanup()
            raise
        return self.paths

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        if self.paths is not None:
            for path in reversed(self.paths):
                _run_command(
                    [
                        "git",
                        "-C",
                        str(self.tooling_root),
                        "worktree",
                        "remove",
                        "--force",
                        str(path),
                    ]
                )
        if self.temp_root is not None and self.temp_root.exists():
            shutil.rmtree(self.temp_root)
        self.paths = None
        self.temp_root = None


def _selected_buildx_capabilities() -> tuple[str, frozenset[str]]:
    result = _run_command(["docker", "buildx", "inspect", "--bootstrap"])
    if result.returncode != 0:
        raise LiveEvidenceRunnerError("BUILDX_DRIVER_UNSUPPORTED", _command_detail(result))
    inspect_text = f"{result.stdout}\n{result.stderr}"
    driver_match = re.search(r"(?im)^\s*Driver:\s*(\S+)\s*$", inspect_text)
    if driver_match is None:
        raise LiveEvidenceRunnerError(
            "BUILDX_DRIVER_UNSUPPORTED", "buildx inspect did not report a selected driver"
        )
    driver = driver_match.group(1)
    if driver != "docker-container":
        raise LiveEvidenceRunnerError(
            "BUILDX_DRIVER_UNSUPPORTED",
            f"selected Buildx driver is {driver!r}, expected 'docker-container'",
        )
    platforms_match = re.search(r"(?im)^\s*Platforms:\s*(.+?)\s*$", inspect_text)
    if platforms_match is None:
        raise LiveEvidenceRunnerError(
            "BUILDX_TARGET_PLATFORM_UNAVAILABLE",
            "buildx inspect did not report available platforms",
        )
    platforms = frozenset(
        token.strip().rstrip("*") for token in platforms_match.group(1).split(",") if token.strip()
    )
    if EXPECTED_DOCKER_TARGET_PLATFORM not in platforms:
        raise LiveEvidenceRunnerError(
            "BUILDX_TARGET_PLATFORM_UNAVAILABLE",
            f"selected builder does not expose {EXPECTED_DOCKER_TARGET_PLATFORM}",
        )
    return driver, platforms


def _buildx_capabilities() -> BuildxCapabilities:
    result = _run_command(["docker", "buildx", "build", "--help"])
    if result.returncode != 0:
        raise LiveEvidenceRunnerError("BUILDX_UNAVAILABLE", _command_detail(result))
    help_text = f"{result.stdout}\n{result.stderr}".lower()
    for required in ("--output", "--metadata-file", "--platform", "--no-cache"):
        if required not in help_text:
            raise LiveEvidenceRunnerError(
                "OCI_EXPORTER_UNSUPPORTED",
                f"docker buildx help does not expose {required}",
            )
    driver, platforms = _selected_buildx_capabilities()
    return BuildxCapabilities(
        supports_provenance_switch="--provenance" in help_text,
        supports_sbom_switch="--sbom" in help_text,
        selected_driver=driver,
        available_platforms=platforms,
    )


def buildx_build_command(
    *,
    context: Path,
    output_path: Path,
    metadata_path: Path,
    build_run_id: str,
    source_date_epoch: int,
    docker_target_platform: str,
    oci_exporter: Mapping[str, str],
    capabilities: BuildxCapabilities,
) -> list[str]:
    """Build one independent no-cache OCI-export invocation."""
    if docker_target_platform != EXPECTED_DOCKER_TARGET_PLATFORM:
        raise LiveEvidenceRunnerError(
            "RC_BUILD_ARG_MISMATCH",
            f"unsupported Docker target platform: {docker_target_platform}",
        )
    exporter_policy = _validated_oci_exporter_policy(oci_exporter)
    docker_tag = re.sub(r"[^a-z0-9_.-]+", "-", build_run_id.lower())
    args = [
        "docker",
        "buildx",
        "build",
        "--no-cache",
        "--platform",
        docker_target_platform,
        "--build-arg",
        f"COLD_STORAGE_BUILD_COMMIT_SHA={EXPECTED_SOURCE_COMMIT_SHA}",
        "--build-arg",
        f"COLD_STORAGE_BUILD_VERSION={RC_VERSION}",
        "--build-arg",
        f"SOURCE_DATE_EPOCH={source_date_epoch}",
        "--output",
        (
            f"type={exporter_policy['type']},dest={output_path},"
            f"rewrite-timestamp={exporter_policy['rewrite-timestamp']}"
        ),
        "--metadata-file",
        str(metadata_path),
        "--tag",
        f"cold-storage-backend:{docker_tag}",
    ]
    if capabilities.supports_provenance_switch:
        args.append("--provenance=false")
    if capabilities.supports_sbom_switch:
        args.append("--sbom=false")
    args.extend(["-f", str(context / "backend" / "Dockerfile"), str(context)])
    return args


def _base_image_info(dockerfile: Path) -> tuple[str, list[str]]:
    text = dockerfile.read_text(encoding="utf-8")
    references = [match.group("reference") for match in _BASE_IMAGE_RE.finditer(text)]
    if not references:
        raise LiveEvidenceRunnerError(
            "BASE_IMAGE_OBSERVATION_FAILED", "Dockerfile has no FROM image"
        )
    tags: list[str] = []
    digests: list[str] = []
    for reference in references:
        if "@" not in reference:
            raise LiveEvidenceRunnerError("BASE_IMAGE_NOT_PINNED", reference)
        tag, digest = reference.rsplit("@", 1)
        digests.append(_require_digest(digest, label="base image"))
        tags.append(tag)
    return tags[0], sorted(set(digests))


def _collect_build_inputs(
    source_root: Path, tooling_root: Path
) -> tuple[BuildInputs, str, list[OrderedDict[str, Any]]]:
    dockerfile = source_root / "backend" / "Dockerfile"
    compose = source_root / "docker-compose.production.yml"
    lockfile = source_root / "backend" / "uv.lock"
    migrations = source_root / "backend" / "alembic" / "versions"
    workflow = tooling_root / ".github" / "workflows" / "ci.yml"
    for path in (dockerfile, compose, lockfile, migrations, workflow):
        if not path.exists():
            raise LiveEvidenceRunnerError("BUILD_INPUT_MISSING", str(path))
    source_date_text = _git(
        source_root,
        ["show", "-s", "--format=%ct", EXPECTED_SOURCE_COMMIT_SHA],
        code="SOURCE_DATE_EPOCH_UNAVAILABLE",
    )
    if not source_date_text.isdecimal():
        raise LiveEvidenceRunnerError("SOURCE_DATE_EPOCH_INVALID", source_date_text)
    source_date_epoch = int(source_date_text)
    base_image_tag, base_image_digest_set = _base_image_info(dockerfile)
    build_args = {
        "COLD_STORAGE_BUILD_COMMIT_SHA": EXPECTED_SOURCE_COMMIT_SHA,
        "COLD_STORAGE_BUILD_VERSION": RC_VERSION,
        "SOURCE_DATE_EPOCH": source_date_text,
    }
    inputs = BuildInputs(
        source_commit_sha=EXPECTED_SOURCE_COMMIT_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        source_date_epoch=source_date_epoch,
        dockerfile_digest=_sha256_file(dockerfile),
        compose_file_digest=_sha256_file(compose),
        workflow_definition_digest=_sha256_file(workflow),
        dependency_lockset_digest=_sha256_file(lockfile),
        migration_set_digest=_directory_digest(migrations),
        base_image_digest_set=base_image_digest_set,
        build_args=build_args,
        oci_exporter=dict(EXPECTED_OCI_EXPORTER_POLICY),
        docker_target_platform=EXPECTED_DOCKER_TARGET_PLATFORM,
        build_platform=EXPECTED_BUILD_PLATFORM,
        build_target="runtime",
    )
    artifacts = [
        _artifact_entry(source_root, "backend/Dockerfile"),
        _artifact_entry(source_root, "docker-compose.production.yml"),
        _artifact_entry(source_root, "backend/uv.lock"),
        _artifact_entry(tooling_root, ".github/workflows/ci.yml"),
    ]
    return inputs, base_image_tag, artifacts


def _artifact_entry(root: Path, relative_path: str) -> OrderedDict[str, Any]:
    path = root / relative_path
    return OrderedDict(
        [
            ("relative_path", relative_path),
            ("size_bytes", path.stat().st_size),
            ("sha256", _sha256_file(path).removeprefix("sha256:")),
        ]
    )


def _observed_inputs_document(inputs: BuildInputs) -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("source_commit_sha", inputs.source_commit_sha),
            ("source_tree_sha", inputs.source_tree_sha),
            ("source_date_epoch", inputs.source_date_epoch),
            ("dockerfile_digest", inputs.dockerfile_digest),
            ("compose_file_digest", inputs.compose_file_digest),
            ("workflow_definition_digest", inputs.workflow_definition_digest),
            ("dependency_lockset_digest", inputs.dependency_lockset_digest),
            ("migration_set_digest", inputs.migration_set_digest),
            ("base_image_digest_set", sorted(inputs.base_image_digest_set)),
            ("build_args", inputs.build_args),
            ("oci_exporter", normalize_oci_exporter_policy(inputs.oci_exporter)),
            ("docker_target_platform", inputs.docker_target_platform),
            ("build_platform", inputs.build_platform),
            ("build_target", inputs.build_target),
        ]
    )


def _record_document(record: BuildRunRecord) -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("build_run_id", record.build_run_id),
            ("build_run_attempt", record.build_run_attempt),
            ("build_trigger", record.build_trigger),
            ("builder_identity", record.builder_identity),
            ("build_started_at", record.build_started_at),
            ("build_finished_at", record.build_finished_at),
            ("final_image_digest", record.final_image_digest),
            ("local_oci_manifest_digest", record.local_oci_manifest_digest),
            ("registry_manifest_digest", record.registry_manifest_digest),
            ("base_image_tag", record.base_image_tag),
            ("base_image_digest", record.base_image_digest),
            ("lockfile_digest", record.lockfile_digest),
            ("build_input_manifest_digest", record.build_input_manifest_digest),
            ("reproducible_build_result", record.reproducible_build_result),
        ]
    )


def _build_inputs_from_document(value: Mapping[str, Any]) -> BuildInputs:
    try:
        source_date_epoch = value["source_date_epoch"]
        if isinstance(source_date_epoch, bool) or not isinstance(source_date_epoch, int):
            raise TypeError("source_date_epoch must be an integer")
        base_set = value["base_image_digest_set"]
        build_args = value["build_args"]
        if "oci_exporter" not in value:
            raise LiveEvidenceRunnerError(
                "MISSING_OCI_EXPORTER_POLICY", "observed build inputs omit oci_exporter"
            )
        oci_exporter = _validated_oci_exporter_policy(value["oci_exporter"])
        if not isinstance(base_set, list) or not all(isinstance(item, str) for item in base_set):
            raise TypeError("base_image_digest_set must be a string list")
        if not isinstance(build_args, Mapping) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in build_args.items()
        ):
            raise TypeError("build_args must be a string mapping")
        inputs = BuildInputs(
            source_commit_sha=cast(str, value["source_commit_sha"]),
            source_tree_sha=cast(str, value["source_tree_sha"]),
            source_date_epoch=source_date_epoch,
            dockerfile_digest=cast(str, value["dockerfile_digest"]),
            compose_file_digest=cast(str, value["compose_file_digest"]),
            workflow_definition_digest=cast(str, value["workflow_definition_digest"]),
            dependency_lockset_digest=cast(str, value["dependency_lockset_digest"]),
            migration_set_digest=cast(str, value["migration_set_digest"]),
            base_image_digest_set=list(base_set),
            build_args=dict(build_args),
            oci_exporter=oci_exporter,
            docker_target_platform=cast(str, value["docker_target_platform"]),
            build_platform=cast(str, value["build_platform"]),
            build_target=cast(str, value["build_target"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveEvidenceRunnerError("OBSERVED_INPUTS_INVALID", str(exc)) from exc
    if inputs.source_commit_sha != EXPECTED_SOURCE_COMMIT_SHA:
        raise LiveEvidenceRunnerError(
            "OBSERVED_SOURCE_COMMIT_MISMATCH", "source commit is not frozen RC"
        )
    if inputs.source_tree_sha != EXPECTED_SOURCE_TREE_SHA:
        raise LiveEvidenceRunnerError(
            "OBSERVED_SOURCE_TREE_MISMATCH", "source tree is not frozen RC"
        )
    if inputs.docker_target_platform != EXPECTED_DOCKER_TARGET_PLATFORM:
        raise LiveEvidenceRunnerError(
            "RC_BUILD_ARG_MISMATCH", "Docker target platform is not the frozen value"
        )
    return inputs


def _build_record_from_document(value: Mapping[str, Any]) -> BuildRunRecord:
    try:
        attempt = value["build_run_attempt"]
        if isinstance(attempt, bool) or not isinstance(attempt, int):
            raise TypeError("build_run_attempt must be an integer")
        registry = value["registry_manifest_digest"]
        if registry is not None and not isinstance(registry, str):
            raise TypeError("registry_manifest_digest must be null or string")
        record = BuildRunRecord(
            build_run_id=cast(str, value["build_run_id"]),
            build_run_attempt=attempt,
            build_trigger=cast(str, value["build_trigger"]),
            builder_identity=cast(str, value["builder_identity"]),
            build_started_at=cast(str, value["build_started_at"]),
            build_finished_at=cast(str, value["build_finished_at"]),
            final_image_digest=cast(str, value["final_image_digest"]),
            local_oci_manifest_digest=cast(str, value["local_oci_manifest_digest"]),
            registry_manifest_digest=registry,
            base_image_tag=cast(str, value["base_image_tag"]),
            base_image_digest=cast(str, value["base_image_digest"]),
            lockfile_digest=cast(str, value["lockfile_digest"]),
            build_input_manifest_digest=cast(str, value["build_input_manifest_digest"]),
            reproducible_build_result=cast(str, value.get("reproducible_build_result", "PASS")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveEvidenceRunnerError("BUILD_RECORD_INVALID", str(exc)) from exc
    if not record.build_run_id:
        raise LiveEvidenceRunnerError("BUILD_RECORD_INVALID", "build_run_id is empty")
    return record


def _relative_output_path(output_dir: Path, path: Path) -> str:
    return path.relative_to(output_dir).as_posix()


def _ensure_distinct(values: Sequence[str], *, code: str) -> None:
    if len(values) != len(set(values)):
        raise LiveEvidenceRunnerError(code, "independent Build A/B values must be distinct")


def _build_run_observation(
    *,
    output_dir: Path,
    output_path: Path,
    metadata_path: Path,
    record_path: Path,
    inputs_path: Path,
    manifest_path: Path,
    observation_path: Path,
    inputs: BuildInputs,
    base_image_tag: str,
    run_id: str,
    build_trigger: str,
    builder_identity: str,
    capabilities: BuildxCapabilities,
    context: Path,
) -> OrderedDict[str, Any]:
    start = _now()
    command = buildx_build_command(
        context=context,
        output_path=output_path,
        metadata_path=metadata_path,
        build_run_id=run_id,
        source_date_epoch=inputs.source_date_epoch,
        docker_target_platform=inputs.docker_target_platform,
        oci_exporter=inputs.oci_exporter,
        capabilities=capabilities,
    )
    result = _run_command(command)
    if result.returncode != 0:
        raise LiveEvidenceRunnerError("DOCKER_BUILD_FAILED", _command_detail(result))
    if not output_path.exists():
        raise LiveEvidenceRunnerError("BUILD_OUTPUT_MISSING", str(output_path))
    if not metadata_path.is_file():
        raise LiveEvidenceRunnerError("BUILDX_METADATA_MISSING", str(metadata_path))
    metadata = _read_json_object(metadata_path, code="BUILDX_METADATA_INVALID")
    observation = _observe_oci_manifest(output_path)
    digest = observation.digest
    declared_manifest = compute_build_input_manifest_digest(inputs.to_input_manifest())
    record = BuildRunRecord(
        build_run_id=run_id,
        build_run_attempt=1,
        build_trigger=build_trigger,
        builder_identity=builder_identity,
        build_started_at=start,
        build_finished_at=_now(),
        final_image_digest=digest,
        local_oci_manifest_digest=digest,
        registry_manifest_digest=None,
        base_image_tag=base_image_tag,
        base_image_digest=inputs.base_image_digest_set[0],
        lockfile_digest=inputs.dependency_lockset_digest,
        build_input_manifest_digest=declared_manifest,
    )
    observed_inputs = _observed_inputs_document(inputs)
    build_input_manifest = inputs.to_input_manifest()
    _write_json(inputs_path, observed_inputs)
    _write_json(manifest_path, build_input_manifest)
    _write_json(record_path, _record_document(record))
    _write_json(observation_path, observation.to_document())
    return OrderedDict(
        [
            ("observed_inputs", observed_inputs),
            ("build_input_manifest", build_input_manifest),
            ("build_input_manifest_digest", declared_manifest),
            ("build_record", _record_document(record)),
            ("output_path", _relative_output_path(output_dir, output_path)),
            ("buildx_metadata_path", _relative_output_path(output_dir, metadata_path)),
            ("observed_inputs_path", _relative_output_path(output_dir, inputs_path)),
            ("build_input_manifest_path", _relative_output_path(output_dir, manifest_path)),
            ("build_record_path", _relative_output_path(output_dir, record_path)),
            ("manifest_observation_path", _relative_output_path(output_dir, observation_path)),
            ("buildx_metadata", metadata),
            ("manifest_observation", observation.to_document()),
        ]
    )


def _metadata_document(
    *,
    evidence_tool_head: str,
    evidence_tool_tree: str,
    workflow_digest: str,
    capture_run_id: str,
    started_at: str,
) -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("schema_version", OBSERVATION_SCHEMA_VERSION),
            ("task", "TASK-012"),
            ("version", "V0.2"),
            ("slice", 2),
            ("rc_source_sha", EXPECTED_SOURCE_COMMIT_SHA),
            ("rc_source_tree", EXPECTED_SOURCE_TREE_SHA),
            ("evidence_tool_head", evidence_tool_head),
            ("evidence_tool_tree", evidence_tool_tree),
            ("runner_module_digest", _sha256_file(RUNNER_MODULE)),
            ("workflow_definition_digest", workflow_digest),
            ("capture_workflow_run_id", os.environ.get("GITHUB_RUN_ID")),
            ("capture_workflow_run_attempt", os.environ.get("GITHUB_RUN_ATTEMPT")),
            ("capture_run_id", capture_run_id),
            ("build_a_run_id", f"{capture_run_id}:A"),
            ("build_b_run_id", f"{capture_run_id}:B"),
            ("started_at", started_at),
            ("finished_at", None),
        ]
    )


_CHECKSUM_LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")
_CHECKSUM_FILES = frozenset({"SHA256SUMS", "SHA256SUMS.sha256"})


def _payload_files(root: Path) -> set[str]:
    payload: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise LiveEvidenceRunnerError("CHECKSUM_SYMLINK_REJECTED", str(path))
        relative_path = path.relative_to(root).as_posix()
        if path.is_file() and relative_path not in _CHECKSUM_FILES:
            payload.add(relative_path)
    return payload


def _verify_capture_checksums(bundle_root: Path) -> None:
    """Verify the capture package before trusting any observation JSON."""
    manifest_path = bundle_root / "SHA256SUMS"
    sidecar_path = bundle_root / "SHA256SUMS.sha256"
    for path, code in (
        (manifest_path, "CHECKSUM_MANIFEST_MISSING"),
        (sidecar_path, "CHECKSUM_SIDECAR_MISSING"),
    ):
        if not path.is_file() or path.is_symlink():
            raise LiveEvidenceRunnerError(code, str(path))

    sidecar = sidecar_path.read_bytes()
    if (
        sidecar != sidecar.removesuffix(b"\n") + b"\n"
        or re.fullmatch(rb"[0-9a-f]{64}\n", sidecar) is None
    ):
        raise LiveEvidenceRunnerError("CHECKSUM_SIDECAR_INVALID", str(sidecar_path))
    expected_sidecar = hashlib.sha256(manifest_path.read_bytes()).hexdigest().encode("ascii")
    if sidecar != expected_sidecar + b"\n":
        raise LiveEvidenceRunnerError("CHECKSUM_SIDECAR_MISMATCH", str(manifest_path))

    try:
        manifest_text = manifest_path.read_bytes().decode("ascii")
    except UnicodeDecodeError as exc:
        raise LiveEvidenceRunnerError("CHECKSUM_MANIFEST_INVALID", str(manifest_path)) from exc
    if not manifest_text.endswith("\n") or "\r" in manifest_text:
        raise LiveEvidenceRunnerError("CHECKSUM_MANIFEST_INVALID", str(manifest_path))
    lines = manifest_text[:-1].split("\n")
    if not lines or any(not line for line in lines):
        raise LiveEvidenceRunnerError("CHECKSUM_MANIFEST_INVALID", str(manifest_path))

    listed: set[str] = set()
    for line in lines:
        match = _CHECKSUM_LINE_RE.fullmatch(line)
        if match is None:
            raise LiveEvidenceRunnerError("CHECKSUM_ENTRY_INVALID", line)
        digest, relative_text = match.groups()
        relative = PurePosixPath(relative_text)
        if (
            not relative_text
            or "\\" in relative_text
            or relative_text.startswith("/")
            or re.match(r"^[A-Za-z]:", relative_text) is not None
            or relative_text != relative.as_posix()
            or ".." in relative.parts
            or relative_text in _CHECKSUM_FILES
        ):
            raise LiveEvidenceRunnerError("CHECKSUM_ENTRY_INVALID", relative_text)
        if relative_text in listed:
            raise LiveEvidenceRunnerError("CHECKSUM_DUPLICATE_ENTRY", relative_text)
        listed.add(relative_text)

        candidate = bundle_root
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise LiveEvidenceRunnerError("CHECKSUM_SYMLINK_REJECTED", relative_text)
        if not candidate.is_file() or candidate.is_symlink():
            raise LiveEvidenceRunnerError("CHECKSUM_FILE_MISSING", relative_text)
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
            raise LiveEvidenceRunnerError("CHECKSUM_DIGEST_MISMATCH", relative_text)

    payload = _payload_files(bundle_root)
    if listed != payload:
        missing = sorted(listed - payload)
        extra = sorted(payload - listed)
        raise LiveEvidenceRunnerError(
            "CHECKSUM_COVERAGE_MISMATCH",
            f"missing={missing!r}, extra={extra!r}",
        )


def _write_checksums(output_dir: Path) -> None:
    checksum_lines: list[str] = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_symlink():
            raise LiveEvidenceRunnerError("CHECKSUM_SYMLINK_REJECTED", str(path))
        relative_path = path.relative_to(output_dir).as_posix()
        if not path.is_file() or relative_path in _CHECKSUM_FILES:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksum_lines.append(f"{digest}  {relative_path}")
    manifest_bytes = ("\n".join(checksum_lines) + "\n").encode("utf-8")
    (output_dir / "SHA256SUMS").write_bytes(manifest_bytes)
    sidecar = hashlib.sha256(manifest_bytes).hexdigest() + "\n"
    (output_dir / "SHA256SUMS.sha256").write_text(sidecar, encoding="ascii")


def capture_local(
    *,
    output_dir: str | Path,
    tooling_root: str | Path = ".",
    execute_builds: bool = False,
    expected_source_sha: str | None = None,
) -> Path:
    """Capture two independent local OCI observations into a temp package."""
    validate_capture_authorization(execute_builds=execute_builds, env=os.environ)
    validate_expected_source(expected_source_sha)
    root = _resolve_tooling_root(tooling_root)
    output = _prepare_output_dir(output_dir, tooling_root=root)
    _verify_frozen_source(root)
    evidence_head, evidence_tree = _verify_tooling_identity(root)
    capabilities = _buildx_capabilities()
    capture_run_id = f"capture-{uuid.uuid4().hex}"
    started_at = _now()
    workflow_digest = _sha256_file(root / ".github" / "workflows" / "ci.yml")
    metadata = _metadata_document(
        evidence_tool_head=evidence_head,
        evidence_tool_tree=evidence_tree,
        workflow_digest=workflow_digest,
        capture_run_id=capture_run_id,
        started_at=started_at,
    )
    with _OwnedWorktrees(root) as (worktree_a, worktree_b):
        inputs_a, base_tag_a, artifacts = _collect_build_inputs(worktree_a, root)
        inputs_b, base_tag_b, _ = _collect_build_inputs(worktree_b, root)
        if inputs_a.to_input_manifest() != inputs_b.to_input_manifest():
            raise LiveEvidenceRunnerError(
                "BUILD_INPUTS_DRIFT", "Build A and B observed inputs differ"
            )
        if base_tag_a != base_tag_b:
            raise LiveEvidenceRunnerError("BASE_IMAGE_OBSERVATION_FAILED", "base image tags differ")
        build_a_dir = output / "build-a"
        build_b_dir = output / "build-b"
        build_a_dir.mkdir()
        build_b_dir.mkdir()
        record_a = _build_run_observation(
            output_dir=output,
            output_path=build_a_dir / "image.oci.tar",
            metadata_path=build_a_dir / "buildx-metadata.json",
            record_path=build_a_dir / "build-record.json",
            inputs_path=build_a_dir / "observed-inputs.json",
            manifest_path=build_a_dir / "build-input-manifest.json",
            observation_path=build_a_dir / "manifest-observation.json",
            inputs=inputs_a,
            base_image_tag=base_tag_a,
            run_id=f"{capture_run_id}:A",
            build_trigger="workflow_dispatch",
            builder_identity=os.environ.get("RUNNER_NAME", "docker-buildx"),
            capabilities=capabilities,
            context=worktree_a,
        )
        record_b = _build_run_observation(
            output_dir=output,
            output_path=build_b_dir / "image.oci.tar",
            metadata_path=build_b_dir / "buildx-metadata.json",
            record_path=build_b_dir / "build-record.json",
            inputs_path=build_b_dir / "observed-inputs.json",
            manifest_path=build_b_dir / "build-input-manifest.json",
            observation_path=build_b_dir / "manifest-observation.json",
            inputs=inputs_b,
            base_image_tag=base_tag_b,
            run_id=f"{capture_run_id}:B",
            build_trigger="workflow_dispatch",
            builder_identity=os.environ.get("RUNNER_NAME", "docker-buildx"),
            capabilities=capabilities,
            context=worktree_b,
        )
        records = [
            cast(Mapping[str, Any], record_a["build_record"]),
            cast(Mapping[str, Any], record_b["build_record"]),
        ]
        _ensure_distinct(
            [cast(str, item["build_run_id"]) for item in records], code="BUILD_RUN_ID_COLLISION"
        )
        _ensure_distinct(
            [cast(str, record_a["output_path"]), cast(str, record_b["output_path"])],
            code="BUILD_OUTPUT_PATH_COLLISION",
        )
        digest_a = cast(
            str, cast(Mapping[str, Any], record_a["build_record"])["local_oci_manifest_digest"]
        )
        digest_b = cast(
            str, cast(Mapping[str, Any], record_b["build_record"])["local_oci_manifest_digest"]
        )
        if digest_a != digest_b:
            raise LiveEvidenceRunnerError(
                "BUILD_DIGEST_DRIFT", "Build A and B observed OCI digests differ"
            )
        expected_inputs = _observed_inputs_document(inputs_a)
        metadata["finished_at"] = _now()
        _write_json(output / "metadata.json", metadata)
        _write_json(output / "expected-inputs.json", expected_inputs)
        bundle = OrderedDict(
            [
                ("schema_version", OBSERVATION_SCHEMA_VERSION),
                ("metadata", metadata),
                ("expected_inputs", expected_inputs),
                ("artifacts", artifacts),
                ("test_result_reference", f"capture-local:{capture_run_id}"),
                ("verification_result_reference", f"capture-local:{capture_run_id}:observed"),
                ("build_a", record_a),
                ("build_b", record_b),
            ]
        )
        _write_json(output / "observation-bundle.json", bundle)
    _write_checksums(output)
    return output / "observation-bundle.json"


def _safe_oci_root(path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if path.is_dir():
        return path, None
    if not path.is_file() or path.is_symlink():
        raise LiveEvidenceRunnerError("OCI_OUTPUT_MISSING", str(path))
    temp = tempfile.TemporaryDirectory(prefix="task012-oci-layout-")
    root = Path(temp.name)
    try:
        with tarfile.open(path, "r:*") as archive:
            for member in archive.getmembers():
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise LiveEvidenceRunnerError("OCI_ARCHIVE_UNSAFE", member.name)
                if member.issym() or member.islnk():
                    raise LiveEvidenceRunnerError("OCI_ARCHIVE_UNSAFE", member.name)
            archive.extractall(root)
    except Exception:
        temp.cleanup()
        raise
    candidates = list(root.rglob("oci-layout"))
    if len(candidates) != 1:
        temp.cleanup()
        raise LiveEvidenceRunnerError("OCI_LAYOUT_AMBIGUOUS", str(path))
    return candidates[0].parent, temp


def _observe_oci_manifest(path: Path) -> OCIManifestObservation:
    root, temp = _safe_oci_root(path)
    try:
        layout = _read_json_object(root / "oci-layout", code="OCI_LAYOUT_MISSING")
        if layout.get("imageLayoutVersion") != "1.0.0":
            raise LiveEvidenceRunnerError("OCI_LAYOUT_SCHEMA_INVALID", str(root))
        index = _read_json_object(root / "index.json", code="OCI_INDEX_MISSING")
        if index.get("schemaVersion") != 2:
            raise LiveEvidenceRunnerError("OCI_INDEX_SCHEMA_INVALID", str(root))
        descriptors = index.get("manifests")
        if not isinstance(descriptors, list) or len(descriptors) != 1:
            raise LiveEvidenceRunnerError(
                "OCI_MANIFEST_AMBIGUOUS",
                "single-image OCI output must contain exactly one manifest descriptor",
            )
        descriptor = descriptors[0]
        if not isinstance(descriptor, Mapping):
            raise LiveEvidenceRunnerError("OCI_DESCRIPTOR_INVALID", str(root))
        media_type = descriptor.get("mediaType")
        if media_type not in _OCI_MANIFEST_MEDIA_TYPES:
            raise LiveEvidenceRunnerError("OCI_MEDIA_TYPE_UNSUPPORTED", str(media_type))
        digest = _require_digest(descriptor.get("digest"), label="OCI manifest descriptor")
        blob = root / "blobs" / "sha256" / digest.removeprefix("sha256:")
        if not blob.is_file() or blob.is_symlink():
            raise LiveEvidenceRunnerError("OCI_MANIFEST_BLOB_MISSING", str(blob))
        raw_manifest = blob.read_bytes()
        recomputed = _sha256_bytes(raw_manifest)
        if recomputed != digest:
            raise LiveEvidenceRunnerError("OCI_MANIFEST_BLOB_DIGEST_MISMATCH", str(blob))
        try:
            manifest = load_json_strict(raw_manifest.decode("utf-8"))
        except Exception as exc:
            raise LiveEvidenceRunnerError("OCI_MANIFEST_INVALID", str(exc)) from exc
        if manifest.get("schemaVersion") != 2:
            raise LiveEvidenceRunnerError("OCI_MANIFEST_SCHEMA_INVALID", str(blob))
        manifest_media_type = manifest.get("mediaType")
        if manifest_media_type is not None and manifest_media_type not in _OCI_MANIFEST_MEDIA_TYPES:
            raise LiveEvidenceRunnerError("OCI_MEDIA_TYPE_UNSUPPORTED", str(manifest_media_type))
        return OCIManifestObservation(
            digest=digest,
            media_type=cast(str, media_type),
            blob_sha256=recomputed.removeprefix("sha256:"),
        )
    finally:
        if temp is not None:
            temp.cleanup()


def observe_oci_manifest(path: str | Path) -> OrderedDict[str, Any]:
    """Return a machine-readable observation of a local OCI output."""
    return _observe_oci_manifest(Path(path).expanduser().resolve()).to_document()


def extract_oci_manifest_digest(path: str | Path) -> str:
    """Return only the re-hashed OCI image manifest digest.

    The digest comes from the single image-manifest descriptor in
    ``index.json`` and is accepted only after re-hashing the referenced
    manifest blob.  Docker image/config IDs are never consulted.
    """
    return _observe_oci_manifest(Path(path).expanduser().resolve()).digest


def _observation_build_inputs(value: Mapping[str, Any]) -> tuple[BuildInputs, BuildRunRecord]:
    inputs_value = value.get("observed_inputs")
    record_value = value.get("build_record")
    if not isinstance(inputs_value, Mapping) or not isinstance(record_value, Mapping):
        raise LiveEvidenceRunnerError(
            "OBSERVATION_BUNDLE_INVALID", "build observation is incomplete"
        )
    inputs = _build_inputs_from_document(inputs_value)
    record = _build_record_from_document(record_value)
    declared_manifest = value.get("build_input_manifest")
    if not isinstance(declared_manifest, Mapping) or canonical_bytes(
        declared_manifest
    ) != canonical_bytes(inputs.to_input_manifest()):
        raise LiveEvidenceRunnerError("BUILD_INPUT_MANIFEST_DRIFT", record.build_run_id)
    declared = value.get("build_input_manifest_digest")
    recomputed = compute_build_input_manifest_digest(inputs.to_input_manifest())
    if declared != recomputed or record.build_input_manifest_digest != recomputed:
        raise LiveEvidenceRunnerError("BUILD_INPUT_MANIFEST_DRIFT", record.build_run_id)
    return inputs, record


def _verify_observation_outputs(
    bundle_dir: Path, value: Mapping[str, Any], record: BuildRunRecord
) -> None:
    output_path_value = value.get("output_path")
    if not isinstance(output_path_value, str):
        raise LiveEvidenceRunnerError("OBSERVATION_BUNDLE_INVALID", "output_path is missing")
    output_path = (bundle_dir / output_path_value).resolve()
    if output_path_value.startswith("/") or not output_path.is_relative_to(bundle_dir.resolve()):
        raise LiveEvidenceRunnerError("OBSERVATION_OUTPUT_PATH_UNSAFE", output_path_value)
    actual = extract_oci_manifest_digest(output_path)
    if actual != record.local_oci_manifest_digest or actual != record.final_image_digest:
        raise LiveEvidenceRunnerError("OBSERVED_DIGEST_DRIFT", record.build_run_id)


def _bundle_output_document(bundle: EvidenceBundle) -> OrderedDict[str, Any]:
    return OrderedDict(
        [
            ("schema_version", EVIDENCE_BUNDLE_OUTPUT_SCHEMA_VERSION),
            ("rc_version", bundle.rc_version),
            ("authoritative_image_digest", bundle.authoritative_image_digest),
            ("artifact_manifest", bundle.artifact_manifest),
            ("artifact_manifest_digest", bundle.artifact_manifest_digest),
            ("provenance", bundle.provenance),
            ("provenance_digest", bundle.provenance_digest),
            ("reproducible_build_result", bundle.reproducible_build_result),
            ("raw", bundle.raw),
        ]
    )


def assemble_evidence(
    *,
    observation_bundle: str | Path,
    attestation_file: str | Path,
    output_dir: str | Path,
    tooling_root: str | Path = ".",
    expected_source_sha: str | None = None,
) -> Path:
    """Assemble and verify an observation package with explicit attestation."""
    validate_expected_source(expected_source_sha)
    root = _resolve_tooling_root(tooling_root)
    attestation_path = Path(attestation_file).expanduser().resolve()
    if not attestation_path.is_file() or attestation_path.is_symlink():
        raise LiveEvidenceRunnerError("ATTESTATION_MISSING", str(attestation_path))
    bundle_path = Path(observation_bundle).expanduser().resolve()
    _verify_capture_checksums(bundle_path.parent)
    bundle = _read_json_object(bundle_path, code="OBSERVATION_BUNDLE_MISSING")
    if bundle.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
        raise LiveEvidenceRunnerError("OBSERVATION_BUNDLE_SCHEMA_INVALID", str(bundle_path))
    metadata = bundle.get("metadata")
    expected_value = bundle.get("expected_inputs")
    build_a_value = bundle.get("build_a")
    build_b_value = bundle.get("build_b")
    if not all(
        isinstance(item, Mapping)
        for item in (metadata, expected_value, build_a_value, build_b_value)
    ):
        raise LiveEvidenceRunnerError(
            "OBSERVATION_BUNDLE_INVALID", "required observation sections are missing"
        )
    metadata_map = cast(Mapping[str, Any], metadata)
    if metadata_map.get("rc_source_sha") != EXPECTED_SOURCE_COMMIT_SHA:
        raise LiveEvidenceRunnerError("OBSERVED_SOURCE_COMMIT_MISMATCH", "metadata source mismatch")
    if metadata_map.get("rc_source_tree") != EXPECTED_SOURCE_TREE_SHA:
        raise LiveEvidenceRunnerError("OBSERVED_SOURCE_TREE_MISMATCH", "metadata tree mismatch")
    inputs_a, record_a = _observation_build_inputs(cast(Mapping[str, Any], build_a_value))
    inputs_b, record_b = _observation_build_inputs(cast(Mapping[str, Any], build_b_value))
    _verify_observation_outputs(
        bundle_path.parent, cast(Mapping[str, Any], build_a_value), record_a
    )
    _verify_observation_outputs(
        bundle_path.parent, cast(Mapping[str, Any], build_b_value), record_b
    )
    _ensure_distinct([record_a.build_run_id, record_b.build_run_id], code="BUILD_RUN_ID_COLLISION")
    outputs = [
        cast(str, cast(Mapping[str, Any], build_a_value)["output_path"]),
        cast(str, cast(Mapping[str, Any], build_b_value)["output_path"]),
    ]
    _ensure_distinct(outputs, code="BUILD_OUTPUT_PATH_COLLISION")
    if not isinstance(expected_value, Mapping):
        raise LiveEvidenceRunnerError("OBSERVATION_BUNDLE_INVALID", "expected inputs are missing")
    expected_inputs = _build_inputs_from_document(cast(Mapping[str, Any], expected_value))
    attestation = _read_json_object(attestation_path, code="ATTESTATION_MISSING")
    if not attestation:
        raise LiveEvidenceRunnerError("ATTESTATION_MISSING", "attestation file is empty")
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, list):
        raise LiveEvidenceRunnerError("OBSERVATION_BUNDLE_INVALID", "artifacts must be a list")
    test_reference = bundle.get("test_result_reference")
    verification_reference = bundle.get("verification_result_reference")
    if not isinstance(test_reference, str) or not isinstance(verification_reference, str):
        raise LiveEvidenceRunnerError("OBSERVATION_BUNDLE_INVALID", "result references are missing")
    evidence = collect_release_candidate_evidence(
        build_a_inputs=inputs_a,
        build_b_inputs=inputs_b,
        build_a=record_a,
        build_b=record_b,
        artifacts=[cast(Mapping[str, Any], item) for item in artifacts],
        test_result_reference=test_reference,
        verification_result_reference=verification_reference,
        attestation=attestation,
        expected_inputs=expected_inputs,
    )
    output = _prepare_output_dir(output_dir, tooling_root=root)
    _write_json(output / "artifact-manifest.json", evidence.artifact_manifest)
    (output / "provenance.json").write_bytes(canonical_bytes(evidence.provenance))
    _write_json(output / "evidence-bundle.json", _bundle_output_document(evidence))
    assembly_metadata = OrderedDict(
        [
            ("schema_version", EVIDENCE_BUNDLE_OUTPUT_SCHEMA_VERSION),
            ("rc_source_sha", EXPECTED_SOURCE_COMMIT_SHA),
            ("rc_source_tree", EXPECTED_SOURCE_TREE_SHA),
            ("evidence_tool_head", metadata_map.get("evidence_tool_head")),
            ("evidence_tool_tree", metadata_map.get("evidence_tool_tree")),
            ("attestation_source", str(attestation_path)),
            ("assembled_at", _now()),
        ]
    )
    _write_json(output / "assembly-metadata.json", assembly_metadata)
    _write_checksums(output)
    return output / "evidence-bundle.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TASK-012 non-production Live Evidence runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture-local")
    capture.add_argument("--execute-builds", action="store_true")
    capture.add_argument("--output-dir", required=True)
    capture.add_argument("--tooling-root", default=".")
    capture.add_argument("--expected-source-sha")
    assemble = subparsers.add_parser("assemble")
    assemble.add_argument("--observation-bundle", required=True)
    assemble.add_argument("--attestation-file", required=True)
    assemble.add_argument("--output-dir", required=True)
    assemble.add_argument("--tooling-root", default=".")
    assemble.add_argument("--expected-source-sha")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "capture-local":
            bundle = capture_local(
                output_dir=args.output_dir,
                tooling_root=args.tooling_root,
                execute_builds=args.execute_builds,
                expected_source_sha=args.expected_source_sha,
            )
            print(bundle)
            return 0
        bundle = assemble_evidence(
            observation_bundle=args.observation_bundle,
            attestation_file=args.attestation_file,
            output_dir=args.output_dir,
            tooling_root=args.tooling_root,
            expected_source_sha=args.expected_source_sha,
        )
        print(bundle)
        return 0
    except LiveEvidenceRunnerError as exc:
        print(f"{exc.code}: {exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BuildxCapabilities",
    "EVIDENCE_BUNDLE_OUTPUT_SCHEMA_VERSION",
    "LiveEvidenceRunnerError",
    "OBSERVATION_SCHEMA_VERSION",
    "OCIManifestObservation",
    "assemble_evidence",
    "buildx_build_command",
    "capture_local",
    "extract_oci_manifest_digest",
    "main",
    "observe_oci_manifest",
    "validate_capture_authorization",
    "validate_expected_source",
]
