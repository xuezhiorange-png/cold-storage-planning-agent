"""Fail-closed GitHub Actions Artifact transport verification.

This module verifies the transport layer between a capture workflow and a
later assembly process. It does not build images, inspect OCI content, create
provenance, or call the existing evidence collector.

The verified chain is:

    artifact metadata -> exact artifact archive -> archive SHA-256
    -> safe extraction -> existing capture-package verifier

The GitHub token is read only from ``GITHUB_TOKEN`` and is never included in
receipts or error messages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPResponse
from pathlib import Path, PurePosixPath
from typing import Any, cast

DEFAULT_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
TRANSPORT_RECEIPT_SCHEMA_VERSION = "cold-storage-artifact-transport-receipt-v1"
VERIFIED_ARCHIVE_NAME = "verified-artifact.zip"
EXTRACTED_DIRECTORY_NAME = "extracted"
CHUNK_SIZE = 1024 * 1024

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_POSITIVE_DECIMAL_RE = re.compile(r"^[1-9][0-9]*$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ArtifactTransportError(Exception):
    """Fail-closed error raised by the Artifact transport boundary."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ArtifactMetadata:
    """Metadata bound to one exact GitHub Artifact ID."""

    artifact_id: int
    artifact_name: str
    artifact_digest: str
    capture_run_id: str
    capture_run_attempt: str
    capture_head_sha: str
    capture_head_branch: str
    metadata_url: str
    archive_endpoint_identity: str


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_artifact_digest(value: str) -> str:
    """Normalize only canonical lower-case SHA-256 text."""
    if not isinstance(value, str):
        raise ArtifactTransportError("ARTIFACT_DIGEST_INVALID", "digest must be text")
    if value.startswith("sha256:"):
        value = value.removeprefix("sha256:")
    if _DIGEST_RE.fullmatch(value) is None:
        raise ArtifactTransportError(
            "ARTIFACT_DIGEST_INVALID", "digest must be 64 lower-case hexadecimal characters"
        )
    return f"sha256:{value}"


def _parse_positive_decimal(value: str, *, field: str) -> str:
    if _POSITIVE_DECIMAL_RE.fullmatch(value) is None:
        raise ArtifactTransportError(
            "ARTIFACT_INPUT_INVALID", f"{field} must be a positive integer"
        )
    return value


def _parse_artifact_id(value: str) -> int:
    text = _parse_positive_decimal(value, field="artifact_id")
    return int(text)


def _validate_repository(repository: str) -> str:
    if _REPOSITORY_RE.fullmatch(repository) is None:
        raise ArtifactTransportError("ARTIFACT_REPOSITORY_INVALID", repository)
    return repository


def _validate_head_sha(value: str) -> str:
    if _SHA_RE.fullmatch(value) is None:
        raise ArtifactTransportError("ARTIFACT_INPUT_INVALID", "capture head SHA is invalid")
    return value


def _validate_token(value: str | None) -> str:
    if not value:
        raise ArtifactTransportError("GITHUB_TOKEN_MISSING", "GITHUB_TOKEN is required")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ArtifactTransportError(
            "GITHUB_TOKEN_INVALID", "GITHUB_TOKEN contains control characters"
        )
    return value


def _validate_api_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ArtifactTransportError("ARTIFACT_API_BASE_INVALID", "API base URL must be HTTPS")
    return value.rstrip("/")


def _response_status(response: HTTPResponse) -> int:
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    return int(response.getcode())


def _open_url(request: urllib.request.Request) -> HTTPResponse:
    return cast(HTTPResponse, urllib.request.urlopen(request, timeout=60))


def _close_response(response: HTTPResponse) -> None:
    response.close()


def _prepare_output_dir(value: str | Path) -> Path:
    output = Path(value).expanduser()
    if not output.is_absolute():
        raise ArtifactTransportError("OUTPUT_PATH_INVALID", "output directory must be absolute")
    output = output.resolve()
    tooling_root = Path.cwd().resolve()
    if output == tooling_root or output.is_relative_to(tooling_root):
        raise ArtifactTransportError(
            "OUTPUT_PATH_UNSAFE", "transport output must not be inside the execution checkout"
        )
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise ArtifactTransportError("OUTPUT_PATH_COLLISION", str(output))
    else:
        output.mkdir(parents=True, exist_ok=False)
    return output


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class ArtifactTransportClient:
    """Small standard-library GitHub Artifact REST client."""

    repository: str
    token: str
    api_base_url: str = DEFAULT_API_BASE_URL

    def __post_init__(self) -> None:
        _validate_repository(self.repository)
        _validate_token(self.token)
        _validate_api_base_url(self.api_base_url)

    @property
    def _base_url(self) -> str:
        return self.api_base_url.rstrip("/")

    def _metadata_url(self, artifact_id: int) -> str:
        return f"{self._base_url}/repos/{self.repository}/actions/artifacts/{artifact_id}"

    def _archive_url(self, artifact_id: int) -> str:
        return f"{self._metadata_url(artifact_id)}/zip"

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "cold-storage-artifact-transport/1",
        }

    def _request(self, url: str) -> HTTPResponse:
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            response = _open_url(request)
        except urllib.error.HTTPError as exc:
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", type(exc).__name__) from exc
        status = _response_status(response)
        if not 200 <= status < 300:
            _close_response(response)
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", f"HTTP {status}")
        return response

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self._request(url)
        try:
            raw = response.read()
        except OSError as exc:
            raise ArtifactTransportError(
                "ARTIFACT_METADATA_READ_FAILED", type(exc).__name__
            ) from exc
        finally:
            _close_response(response)
        if not raw:
            raise ArtifactTransportError("ARTIFACT_METADATA_INVALID", "metadata response is empty")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactTransportError(
                "ARTIFACT_METADATA_INVALID", "metadata is not valid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise ArtifactTransportError("ARTIFACT_METADATA_INVALID", "metadata must be an object")
        return cast(dict[str, Any], value)

    def fetch_verified_metadata(
        self,
        *,
        artifact_id: int,
        expected_digest: str,
        expected_capture_run_id: str,
        expected_capture_run_attempt: str,
        expected_capture_head_sha: str,
    ) -> ArtifactMetadata:
        """Fetch and fail-closed verify metadata for one exact Artifact ID."""
        expected_digest = normalize_artifact_digest(expected_digest)
        run_id = _parse_positive_decimal(expected_capture_run_id, field="capture run ID")
        run_attempt = _parse_positive_decimal(
            expected_capture_run_attempt, field="capture run attempt"
        )
        head_sha = _validate_head_sha(expected_capture_head_sha)
        metadata_url = self._metadata_url(artifact_id)
        archive_url = self._archive_url(artifact_id)
        metadata = self._get_json(metadata_url)

        if metadata.get("id") != artifact_id:
            raise ArtifactTransportError("ARTIFACT_METADATA_ID_MISMATCH", "metadata ID mismatch")
        if metadata.get("expired") is not False:
            raise ArtifactTransportError(
                "ARTIFACT_EXPIRED", "artifact is expired or missing expired=false"
            )
        digest = normalize_artifact_digest(cast(str, metadata.get("digest")))
        if digest != expected_digest:
            raise ArtifactTransportError(
                "ARTIFACT_METADATA_DIGEST_MISMATCH", "metadata digest mismatch"
            )
        name = metadata.get("name")
        expected_name = f"task012-live-evidence-{run_id}-{run_attempt}"
        if name != expected_name:
            raise ArtifactTransportError("ARTIFACT_NAME_MISMATCH", "artifact name mismatch")

        workflow_run = metadata.get("workflow_run")
        if not isinstance(workflow_run, dict):
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "workflow_run is missing"
            )
        if workflow_run.get("id") != int(run_id):
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "workflow run ID mismatch"
            )
        if workflow_run.get("head_sha") != head_sha:
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "capture head SHA mismatch"
            )
        if workflow_run.get("head_branch") != "main":
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "capture branch is not main"
            )
        metadata_attempt = workflow_run.get("run_attempt")
        if metadata_attempt is not None and metadata_attempt != int(run_attempt):
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "capture run attempt mismatch"
            )

        archive_download_url = metadata.get("archive_download_url")
        if archive_download_url is not None:
            self._verify_archive_metadata_url(archive_download_url, archive_url)
        return ArtifactMetadata(
            artifact_id=artifact_id,
            artifact_name=cast(str, name),
            artifact_digest=digest,
            capture_run_id=run_id,
            capture_run_attempt=run_attempt,
            capture_head_sha=head_sha,
            capture_head_branch="main",
            metadata_url=metadata_url,
            archive_endpoint_identity=f"GET {urllib.parse.urlsplit(archive_url).path}",
        )

    @staticmethod
    def _verify_archive_metadata_url(value: Any, expected: str) -> None:
        if not isinstance(value, str):
            raise ArtifactTransportError("ARTIFACT_ARCHIVE_URL_MISMATCH", "archive URL is not text")
        actual_parts = urllib.parse.urlsplit(value)
        expected_parts = urllib.parse.urlsplit(expected)
        if (
            actual_parts.scheme != expected_parts.scheme
            or actual_parts.netloc != expected_parts.netloc
            or actual_parts.path != expected_parts.path
            or actual_parts.query
            or actual_parts.fragment
        ):
            raise ArtifactTransportError(
                "ARTIFACT_ARCHIVE_URL_MISMATCH", "archive URL identity mismatch"
            )

    def download_archive(self, *, artifact_id: int, destination: Path) -> str:
        """Stream the exact ID endpoint to disk and return its SHA-256 digest."""
        response = self._request(self._archive_url(artifact_id))
        digest = hashlib.sha256()
        total = 0
        try:
            with destination.open("wb") as stream:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise ArtifactTransportError(
                            "ARTIFACT_DOWNLOAD_INVALID", "download is not bytes"
                        )
                    stream.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
        except ArtifactTransportError:
            raise
        except OSError as exc:
            raise ArtifactTransportError("ARTIFACT_DOWNLOAD_FAILED", type(exc).__name__) from exc
        finally:
            _close_response(response)
        if total == 0:
            raise ArtifactTransportError("ARTIFACT_DOWNLOAD_EMPTY", "downloaded archive is empty")
        return f"sha256:{digest.hexdigest()}"


def _zip_member_path(info: zipfile.ZipInfo) -> tuple[str, bool]:
    raw_name = info.filename
    if not raw_name or "\\" in raw_name or "\x00" in raw_name:
        raise ArtifactTransportError("ZIP_ENTRY_INVALID", raw_name or "empty entry")
    if raw_name.startswith("/") or re.match(r"^[A-Za-z]:", raw_name):
        raise ArtifactTransportError("ZIP_PATH_TRAVERSAL", raw_name)
    is_directory = raw_name.endswith("/")
    parts = raw_name.split("/")
    if is_directory:
        parts = parts[:-1]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArtifactTransportError("ZIP_PATH_TRAVERSAL", raw_name)
    normalized = "/".join(parts)
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ArtifactTransportError("ZIP_SPECIAL_FILE", raw_name)
    if is_directory and file_type not in {0, stat.S_IFDIR}:
        raise ArtifactTransportError("ZIP_ENTRY_INVALID", raw_name)
    if not is_directory and file_type == stat.S_IFDIR:
        raise ArtifactTransportError("ZIP_ENTRY_INVALID", raw_name)
    return normalized, is_directory


def _safe_extract_archive(archive_path: Path, destination: Path) -> None:
    """Validate every ZIP entry before writing it to the destination."""
    entries: list[tuple[zipfile.ZipInfo, str, bool]] = []
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                normalized, is_directory = _zip_member_path(info)
                if normalized in seen:
                    raise ArtifactTransportError("ZIP_DUPLICATE_PATH", normalized)
                seen.add(normalized)
                entries.append((info, normalized, is_directory))

            destination.mkdir(parents=True, exist_ok=False)
            for info, normalized, is_directory in entries:
                target = (destination / PurePosixPath(normalized)).resolve()
                if not target.is_relative_to(destination.resolve()):
                    raise ArtifactTransportError("ZIP_PATH_TRAVERSAL", normalized)
                if is_directory:
                    target.mkdir(parents=True, exist_ok=False)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=CHUNK_SIZE)
    except ArtifactTransportError:
        if destination.exists():
            shutil.rmtree(destination)
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if destination.exists():
            shutil.rmtree(destination)
        raise ArtifactTransportError("ZIP_EXTRACTION_FAILED", type(exc).__name__) from exc


def _verify_capture_package_shape(root: Path) -> None:
    required_files = (
        "observation-bundle.json",
        "metadata.json",
        "expected-inputs.json",
        "SHA256SUMS",
        "SHA256SUMS.sha256",
    )
    for relative in required_files:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ArtifactTransportError("CAPTURE_PACKAGE_INCOMPLETE", relative)
    for relative in ("build-a", "build-b"):
        path = root / relative
        if not path.is_dir() or path.is_symlink():
            raise ArtifactTransportError("CAPTURE_PACKAGE_INCOMPLETE", relative)


def verify_download(
    *,
    repository: str,
    artifact_id: str,
    expected_artifact_digest: str,
    expected_capture_run_id: str,
    expected_capture_run_attempt: str,
    expected_capture_head_sha: str,
    output_dir: str | Path,
    execute_download: bool = False,
    env: Mapping[str, str] | None = None,
    api_base_url: str = DEFAULT_API_BASE_URL,
) -> Path:
    """Verify one exact Artifact and produce a transport receipt."""
    environment = os.environ if env is None else env
    if not execute_download:
        raise ArtifactTransportError(
            "DOWNLOAD_EXECUTION_NOT_EXPLICIT", "verify-download requires --execute-download"
        )
    if environment.get("TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED") != "YES":
        raise ArtifactTransportError(
            "DOWNLOAD_EXECUTION_NOT_AUTHORIZED",
            "TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED must be exactly YES",
        )
    token = _validate_token(environment.get("GITHUB_TOKEN"))
    repository = _validate_repository(repository)
    parsed_artifact_id = _parse_artifact_id(artifact_id)
    expected_digest = normalize_artifact_digest(expected_artifact_digest)
    output = _prepare_output_dir(output_dir)
    client = ArtifactTransportClient(repository, token, api_base_url)
    metadata = client.fetch_verified_metadata(
        artifact_id=parsed_artifact_id,
        expected_digest=expected_digest,
        expected_capture_run_id=expected_capture_run_id,
        expected_capture_run_attempt=expected_capture_run_attempt,
        expected_capture_head_sha=expected_capture_head_sha,
    )

    temporary_archive = output / f".artifact-download-{uuid.uuid4().hex}.part"
    temporary_extracted = output / f".extracted-{uuid.uuid4().hex}"
    promoted: list[Path] = []
    receipt_path = output / "artifact-transport-receipt.json"
    verified_archive = output / VERIFIED_ARCHIVE_NAME
    extracted = output / EXTRACTED_DIRECTORY_NAME
    try:
        downloaded_digest = client.download_archive(
            artifact_id=parsed_artifact_id, destination=temporary_archive
        )
        if downloaded_digest != expected_digest or downloaded_digest != metadata.artifact_digest:
            raise ArtifactTransportError(
                "ARTIFACT_TRANSPORT_DIGEST_MISMATCH",
                "recorded, metadata, and downloaded archive digests differ",
            )
        _safe_extract_archive(temporary_archive, temporary_extracted)
        _verify_capture_package_shape(temporary_extracted)
        os.replace(temporary_archive, verified_archive)
        promoted.append(verified_archive)
        os.replace(temporary_extracted, extracted)
        promoted.append(extracted)
        receipt = {
            "schema_version": TRANSPORT_RECEIPT_SCHEMA_VERSION,
            "repository": repository,
            "artifact_id": metadata.artifact_id,
            "artifact_name": metadata.artifact_name,
            "recorded_artifact_digest": expected_digest,
            "metadata_artifact_digest": metadata.artifact_digest,
            "downloaded_archive_digest": downloaded_digest,
            "capture_workflow_run_id": metadata.capture_run_id,
            "capture_workflow_run_attempt": metadata.capture_run_attempt,
            "capture_head_sha": metadata.capture_head_sha,
            "capture_head_branch": metadata.capture_head_branch,
            "metadata_url": metadata.metadata_url,
            "archive_endpoint_identity": metadata.archive_endpoint_identity,
            "verified_at": _now(),
            "transport_verification_status": "PASS",
        }
        _atomic_write_json(receipt_path, receipt)
        return receipt_path
    except Exception:
        if temporary_archive.exists():
            temporary_archive.unlink()
        if temporary_extracted.exists():
            shutil.rmtree(temporary_extracted)
        if receipt_path.exists():
            receipt_path.unlink()
        for path in reversed(promoted):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed GitHub Artifact transport verifier")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify-download")
    verify.add_argument("--execute-download", action="store_true")
    verify.add_argument("--repository", required=True)
    verify.add_argument("--artifact-id", required=True)
    verify.add_argument("--expected-artifact-digest", required=True)
    verify.add_argument("--expected-capture-run-id", required=True)
    verify.add_argument("--expected-capture-run-attempt", required=True)
    verify.add_argument("--expected-capture-head-sha", required=True)
    verify.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        verify_download(
            repository=args.repository,
            artifact_id=args.artifact_id,
            expected_artifact_digest=args.expected_artifact_digest,
            expected_capture_run_id=args.expected_capture_run_id,
            expected_capture_run_attempt=args.expected_capture_run_attempt,
            expected_capture_head_sha=args.expected_capture_head_sha,
            output_dir=args.output_dir,
            execute_download=args.execute_download,
        )
        return 0
    except ArtifactTransportError as exc:
        print(f"{exc.code}: {exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ArtifactMetadata",
    "ArtifactTransportClient",
    "ArtifactTransportError",
    "TRANSPORT_RECEIPT_SCHEMA_VERSION",
    "main",
    "normalize_artifact_digest",
    "verify_download",
]
