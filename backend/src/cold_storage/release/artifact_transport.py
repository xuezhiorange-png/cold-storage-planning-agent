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
from http.client import HTTPMessage, HTTPResponse
from pathlib import Path, PurePosixPath
from typing import IO, Any, cast

DEFAULT_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
TRANSPORT_RECEIPT_SCHEMA_VERSION = "cold-storage-artifact-transport-receipt-v1"
HANDOFF_VERIFICATION_RECEIPT_SCHEMA_VERSION = "cold-storage-verified-transport-handoff-receipt-v1"
VERIFIED_ARCHIVE_NAME = "verified-artifact.zip"
HANDOFF_RECEIPT_NAME = "artifact-transport-receipt.json"
VERIFIED_HANDOFF_ARCHIVE_NAME = "verified-transport-handoff.zip"
VERIFIED_HANDOFF_RECEIPT_NAME = "verified-transport-handoff-receipt.json"
EXTRACTED_DIRECTORY_NAME = "extracted"
HANDOFF_CAPTURE_DIRECTORY_NAME = "capture"
CHUNK_SIZE = 1024 * 1024
MAX_ARCHIVE_REDIRECTS = 1
HANDOFF_ARTIFACT_PREFIX = "task012-verified-transport"
HANDOFF_DOWNLOAD_AUTHORIZATION_ENV = "TASK012_VERIFIED_HANDOFF_DOWNLOAD_AUTHORIZED"
EXPECTED_RC_SOURCE_SHA = "043731fea4e60feb6b929c524c4b68e87ed67bd7"
EXPECTED_RC_SOURCE_TREE = "b456e77f07a0cef801c57d2f089a318c35c145c4"
CANONICAL_WORKFLOW_NAME = "ci"
CANONICAL_WORKFLOW_PATH = ".github/workflows/ci.yml"
CANONICAL_WORKFLOW_EVENT = "workflow_dispatch"

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


@dataclass(frozen=True)
class HandoffArtifactMetadata:
    """Metadata bound to one exact durable verified-transport Artifact ID."""

    artifact_id: int
    artifact_name: str
    artifact_digest: str
    transport_run_id: str
    transport_run_attempt: str
    transport_head_sha: str
    transport_head_branch: str
    metadata_url: str
    archive_endpoint_identity: str


@dataclass(frozen=True)
class WorkflowRunMetadata:
    """Authoritative metadata for the exact capture workflow run."""

    run_id: int
    run_attempt: int
    name: str
    path: str
    event: str
    head_sha: str
    head_branch: str
    status: str
    conclusion: str
    workflow_id: int | None
    verified_job_id: int | None = None
    verified_job_name: str | None = None


@dataclass(frozen=True)
class VerifiedHandoffResult:
    """Paths exposed to a later, separately authorized assembly phase."""

    receipt_path: Path
    capture_root: Path
    observation_bundle: Path


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
    if not isinstance(value, str):
        raise ArtifactTransportError(
            "ARTIFACT_INPUT_INVALID", f"{field} must be a positive integer"
        )
    if _POSITIVE_DECIMAL_RE.fullmatch(value) is None:
        raise ArtifactTransportError(
            "ARTIFACT_INPUT_INVALID", f"{field} must be a positive integer"
        )
    return value


def _parse_json_positive_int(value: Any, *, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ArtifactTransportError(
            "ARTIFACT_METADATA_INVALID", f"{field} must be a positive integer"
        )
    return value


def _parse_package_decimal(value: Any, *, field: str) -> int:
    if not isinstance(value, str):
        raise ArtifactTransportError("CAPTURE_PACKAGE_ORIGIN_MISMATCH", f"{field} type mismatch")
    return int(_parse_positive_decimal(value, field=field))


def _parse_artifact_id(value: str) -> int:
    text = _parse_positive_decimal(value, field="artifact_id")
    return int(text)


def _validate_repository(repository: str) -> str:
    if _REPOSITORY_RE.fullmatch(repository) is None:
        raise ArtifactTransportError("ARTIFACT_REPOSITORY_INVALID", repository)
    return repository


def _validate_head_sha(value: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
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


class _NoAutomaticRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return redirect responses so callers can validate them explicitly."""

    @staticmethod
    def _return_response(
        request: urllib.request.Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
    ) -> IO[bytes]:
        del request, code, message
        return response

    def http_error_301(
        self,
        request: urllib.request.Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
    ) -> IO[bytes]:
        return self._return_response(request, response, code, message, headers)

    def http_error_302(
        self,
        request: urllib.request.Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
    ) -> IO[bytes]:
        return self._return_response(request, response, code, message, headers)

    def http_error_303(
        self,
        request: urllib.request.Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
    ) -> IO[bytes]:
        return self._return_response(request, response, code, message, headers)

    def http_error_307(
        self,
        request: urllib.request.Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
    ) -> IO[bytes]:
        return self._return_response(request, response, code, message, headers)

    def http_error_308(
        self,
        request: urllib.request.Request,
        response: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
    ) -> IO[bytes]:
        return self._return_response(request, response, code, message, headers)


def _open_url(request: urllib.request.Request, *, follow_redirects: bool = True) -> HTTPResponse:
    if follow_redirects:
        return cast(HTTPResponse, urllib.request.urlopen(request, timeout=60))
    opener = urllib.request.build_opener(_NoAutomaticRedirectHandler())
    return cast(HTTPResponse, opener.open(request, timeout=60))


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

    def _api_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "cold-storage-artifact-transport/1",
        }

    @staticmethod
    def _archive_headers() -> dict[str, str]:
        return {
            "Accept": "application/octet-stream",
            "User-Agent": "cold-storage-artifact-transport/1",
        }

    def _request(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        follow_redirects: bool = True,
    ) -> HTTPResponse:
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            response = _open_url(request, follow_redirects=follow_redirects)
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
        response = self._request(url, headers=self._api_headers())
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

    def _workflow_run_url(self, run_id: int) -> str:
        return f"{self._base_url}/repos/{self.repository}/actions/runs/{run_id}"

    def _workflow_jobs_url(self, run_id: int) -> str:
        return f"{self._workflow_run_url(run_id)}/jobs?per_page=100"

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

        if type(metadata.get("id")) is not int or metadata.get("id") != artifact_id:
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
        workflow_run_id = _parse_json_positive_int(workflow_run.get("id"), field="workflow_run.id")
        if workflow_run_id != int(run_id):
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
        if metadata_attempt is not None and (
            _parse_json_positive_int(metadata_attempt, field="workflow_run.run_attempt")
            != int(run_attempt)
        ):
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

    def fetch_verified_handoff_metadata(
        self,
        *,
        artifact_id: int,
        expected_digest: str,
        expected_transport_run_id: str,
        expected_transport_run_attempt: str,
        expected_transport_head_sha: str,
        expected_capture_run_id: str,
        expected_capture_run_attempt: str,
    ) -> HandoffArtifactMetadata:
        """Fetch one exact D1 Artifact and bind it to its transport run."""
        expected_digest = normalize_artifact_digest(expected_digest)
        transport_run_id = _parse_positive_decimal(
            expected_transport_run_id, field="transport run ID"
        )
        transport_run_attempt = _parse_positive_decimal(
            expected_transport_run_attempt, field="transport run attempt"
        )
        transport_head_sha = _validate_head_sha(expected_transport_head_sha)
        capture_run_id = _parse_positive_decimal(expected_capture_run_id, field="capture run ID")
        capture_run_attempt = _parse_positive_decimal(
            expected_capture_run_attempt, field="capture run attempt"
        )
        metadata_url = self._metadata_url(artifact_id)
        archive_url = self._archive_url(artifact_id)
        metadata = self._get_json(metadata_url)

        if type(metadata.get("id")) is not int or metadata.get("id") != artifact_id:
            raise ArtifactTransportError(
                "HANDOFF_METADATA_ID_MISMATCH", "handoff metadata ID mismatch"
            )
        if metadata.get("expired") is not False:
            raise ArtifactTransportError(
                "HANDOFF_ARTIFACT_EXPIRED", "handoff artifact is expired or missing expired=false"
            )
        digest = normalize_artifact_digest(cast(str, metadata.get("digest")))
        if digest != expected_digest:
            raise ArtifactTransportError(
                "HANDOFF_METADATA_DIGEST_MISMATCH", "handoff metadata digest mismatch"
            )
        expected_name = (
            f"{HANDOFF_ARTIFACT_PREFIX}-{capture_run_id}-{capture_run_attempt}-"
            f"{transport_run_id}-{transport_run_attempt}"
        )
        name = metadata.get("name")
        if name != expected_name:
            raise ArtifactTransportError("HANDOFF_ARTIFACT_NAME_MISMATCH", "handoff name mismatch")

        workflow_run = metadata.get("workflow_run")
        if not isinstance(workflow_run, dict):
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff workflow_run is missing"
            )
        workflow_run_id = _parse_json_positive_int(
            workflow_run.get("id"), field="handoff workflow_run.id"
        )
        if workflow_run_id != int(transport_run_id):
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff transport run ID mismatch"
            )
        if workflow_run.get("head_sha") != transport_head_sha:
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff transport head SHA mismatch"
            )
        if workflow_run.get("head_branch") != "main":
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff transport branch is not main"
            )
        metadata_attempt = workflow_run.get("run_attempt")
        if metadata_attempt is not None and (
            _parse_json_positive_int(metadata_attempt, field="handoff workflow_run.run_attempt")
            != int(transport_run_attempt)
        ):
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff transport run attempt mismatch"
            )

        archive_download_url = metadata.get("archive_download_url")
        if archive_download_url is not None:
            self._verify_archive_metadata_url(archive_download_url, archive_url)
        return HandoffArtifactMetadata(
            artifact_id=artifact_id,
            artifact_name=cast(str, name),
            artifact_digest=digest,
            transport_run_id=transport_run_id,
            transport_run_attempt=transport_run_attempt,
            transport_head_sha=transport_head_sha,
            transport_head_branch="main",
            metadata_url=metadata_url,
            archive_endpoint_identity=f"GET {urllib.parse.urlsplit(archive_url).path}",
        )

    def fetch_verified_workflow_run(
        self,
        *,
        metadata: ArtifactMetadata,
        expected_capture_run_id: str,
        expected_capture_run_attempt: str,
        expected_capture_head_sha: str,
    ) -> WorkflowRunMetadata:
        """Fetch and verify the exact canonical capture workflow run."""
        expected_run_id = int(
            _parse_positive_decimal(expected_capture_run_id, field="capture run ID")
        )
        expected_attempt = int(
            _parse_positive_decimal(expected_capture_run_attempt, field="capture run attempt")
        )
        expected_head_sha = _validate_head_sha(expected_capture_head_sha)
        authoritative_run_id = int(metadata.capture_run_id)
        if authoritative_run_id != expected_run_id:
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "workflow run ID assertion mismatch"
            )

        response = self._get_json(self._workflow_run_url(authoritative_run_id))
        run_id = _parse_json_positive_int(response.get("id"), field="workflow run id")
        run_attempt = _parse_json_positive_int(
            response.get("run_attempt"), field="workflow run attempt"
        )
        if run_id != expected_run_id:
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "workflow run ID mismatch"
            )
        if run_attempt != expected_attempt:
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "workflow run attempt mismatch"
            )

        required_text = (
            ("name", CANONICAL_WORKFLOW_NAME),
            ("path", CANONICAL_WORKFLOW_PATH),
            ("event", CANONICAL_WORKFLOW_EVENT),
            ("head_branch", "main"),
            ("head_sha", expected_head_sha),
            ("status", "completed"),
            ("conclusion", "success"),
        )
        for field, expected in required_text:
            if response.get(field) != expected:
                raise ArtifactTransportError(
                    "ARTIFACT_WORKFLOW_BINDING_MISMATCH",
                    f"workflow run {field} mismatch",
                )

        if metadata.capture_run_id != str(run_id):
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "artifact workflow run ID mismatch"
            )
        if metadata.capture_head_sha != expected_head_sha:
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "artifact workflow head SHA mismatch"
            )
        if metadata.capture_head_branch != "main":
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "artifact workflow branch mismatch"
            )
        if metadata.capture_run_attempt != str(run_attempt):
            raise ArtifactTransportError(
                "ARTIFACT_WORKFLOW_BINDING_MISMATCH", "artifact workflow attempt mismatch"
            )

        workflow_id_value = response.get("workflow_id")
        workflow_id = None
        if workflow_id_value is not None:
            workflow_id = _parse_json_positive_int(
                workflow_id_value, field="workflow run workflow_id"
            )
        return WorkflowRunMetadata(
            run_id=run_id,
            run_attempt=run_attempt,
            name=cast(str, response["name"]),
            path=cast(str, response["path"]),
            event=cast(str, response["event"]),
            head_sha=cast(str, response["head_sha"]),
            head_branch=cast(str, response["head_branch"]),
            status=cast(str, response["status"]),
            conclusion=cast(str, response["conclusion"]),
            workflow_id=workflow_id,
        )

    def fetch_verified_handoff_workflow_run(
        self,
        *,
        metadata: HandoffArtifactMetadata,
        expected_transport_run_id: str,
        expected_transport_run_attempt: str,
        expected_transport_head_sha: str,
    ) -> WorkflowRunMetadata:
        """Verify the canonical transport run and its successful verifier job."""
        expected_run_id = int(
            _parse_positive_decimal(expected_transport_run_id, field="transport run ID")
        )
        expected_attempt = int(
            _parse_positive_decimal(expected_transport_run_attempt, field="transport run attempt")
        )
        expected_head_sha = _validate_head_sha(expected_transport_head_sha)
        if int(metadata.transport_run_id) != expected_run_id:
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "transport run ID assertion mismatch"
            )

        response = self._get_json(self._workflow_run_url(expected_run_id))
        run_id = _parse_json_positive_int(response.get("id"), field="transport workflow run id")
        run_attempt = _parse_json_positive_int(
            response.get("run_attempt"), field="transport workflow run attempt"
        )
        if run_id != expected_run_id or run_attempt != expected_attempt:
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "transport workflow run identity mismatch"
            )
        required_text = (
            ("name", CANONICAL_WORKFLOW_NAME),
            ("path", CANONICAL_WORKFLOW_PATH),
            ("event", CANONICAL_WORKFLOW_EVENT),
            ("head_branch", "main"),
            ("head_sha", expected_head_sha),
            ("status", "completed"),
            ("conclusion", "success"),
        )
        for field, expected in required_text:
            if response.get(field) != expected:
                raise ArtifactTransportError(
                    "HANDOFF_WORKFLOW_BINDING_MISMATCH",
                    f"transport workflow run {field} mismatch",
                )

        if metadata.transport_head_sha != expected_head_sha:
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff metadata head SHA mismatch"
            )
        if metadata.transport_head_branch != "main":
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff metadata branch mismatch"
            )
        if metadata.transport_run_attempt != str(run_attempt):
            raise ArtifactTransportError(
                "HANDOFF_WORKFLOW_BINDING_MISMATCH", "handoff metadata attempt mismatch"
            )

        jobs_response = self._get_json(self._workflow_jobs_url(expected_run_id))
        jobs = jobs_response.get("jobs")
        if not isinstance(jobs, list):
            raise ArtifactTransportError(
                "HANDOFF_TRANSPORT_JOB_INVALID", "transport workflow jobs are missing"
            )
        matching_jobs = [
            job
            for job in jobs
            if isinstance(job, dict)
            and job.get("name") == "live-evidence-artifact-transport-verify"
        ]
        if len(matching_jobs) != 1:
            raise ArtifactTransportError(
                "HANDOFF_TRANSPORT_JOB_INVALID", "canonical transport verifier job is ambiguous"
            )
        job = matching_jobs[0]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ArtifactTransportError(
                "HANDOFF_TRANSPORT_JOB_INVALID", "canonical transport verifier job did not pass"
            )
        job_id = _parse_json_positive_int(job.get("id"), field="transport verifier job id")

        workflow_id_value = response.get("workflow_id")
        workflow_id = None
        if workflow_id_value is not None:
            workflow_id = _parse_json_positive_int(
                workflow_id_value, field="transport workflow run workflow_id"
            )
        return WorkflowRunMetadata(
            run_id=run_id,
            run_attempt=run_attempt,
            name=cast(str, response["name"]),
            path=cast(str, response["path"]),
            event=cast(str, response["event"]),
            head_sha=cast(str, response["head_sha"]),
            head_branch=cast(str, response["head_branch"]),
            status=cast(str, response["status"]),
            conclusion=cast(str, response["conclusion"]),
            workflow_id=workflow_id,
            verified_job_id=job_id,
            verified_job_name=cast(str, job["name"]),
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

    @staticmethod
    def _response_header(response: HTTPResponse, name: str) -> str | None:
        headers = getattr(response, "headers", None)
        if headers is not None:
            value = headers.get(name)
            if isinstance(value, str):
                return value
        getter = getattr(response, "getheader", None)
        if callable(getter):
            value = getter(name)
            if isinstance(value, str):
                return value
        return None

    def _validate_archive_redirect(self, location: str | None) -> str:
        if not isinstance(location, str) or not location:
            raise ArtifactTransportError(
                "ARTIFACT_REDIRECT_INVALID", "archive redirect Location is required"
            )
        parsed = urllib.parse.urlsplit(location)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ArtifactTransportError(
                "ARTIFACT_REDIRECT_INVALID", "archive redirect must be an HTTPS URL"
            )
        if self.token in location:
            raise ArtifactTransportError(
                "ARTIFACT_REDIRECT_INVALID", "archive redirect must not contain credentials"
            )
        api_host = urllib.parse.urlsplit(self._base_url).hostname
        if api_host is not None and parsed.hostname.lower() == api_host.lower():
            raise ArtifactTransportError(
                "ARTIFACT_REDIRECT_INVALID", "archive redirect cannot target the GitHub API"
            )
        return location

    def download_archive(self, *, artifact_id: int, destination: Path) -> str:
        """Observe one API redirect, then stream the unsigned archive URL."""
        archive_url = self._archive_url(artifact_id)
        initial_request = urllib.request.Request(
            archive_url, headers=self._api_headers(), method="GET"
        )
        try:
            response = _open_url(initial_request, follow_redirects=False)
        except urllib.error.HTTPError as exc:
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", type(exc).__name__) from exc
        status = _response_status(response)
        if status != 302:
            _close_response(response)
            raise ArtifactTransportError(
                "ARTIFACT_REDIRECT_INVALID", "archive endpoint must return one redirect"
            )
        try:
            location = self._validate_archive_redirect(self._response_header(response, "Location"))
        finally:
            _close_response(response)

        archive_request = urllib.request.Request(
            location, headers=self._archive_headers(), method="GET"
        )
        try:
            response = _open_url(archive_request, follow_redirects=False)
        except urllib.error.HTTPError as exc:
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", type(exc).__name__) from exc
        status = _response_status(response)
        if 300 <= status < 400:
            _close_response(response)
            raise ArtifactTransportError(
                "ARTIFACT_REDIRECT_CHAIN_REJECTED",
                f"archive redirect count exceeds {MAX_ARCHIVE_REDIRECTS}",
            )
        if status != 200:
            _close_response(response)
            raise ArtifactTransportError("ARTIFACT_HTTP_ERROR", f"HTTP {status}")

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


def _read_capture_package_origin(root: Path, workflow_run: WorkflowRunMetadata) -> dict[str, Any]:
    """Bind package origin metadata to independently observed workflow data."""
    path = root / "metadata.json"
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactTransportError(
            "CAPTURE_PACKAGE_ORIGIN_MISMATCH", "capture metadata is invalid"
        ) from exc
    if not isinstance(value, dict):
        raise ArtifactTransportError(
            "CAPTURE_PACKAGE_ORIGIN_MISMATCH", "capture metadata must be an object"
        )

    if value.get("task") != "TASK-012":
        raise ArtifactTransportError("CAPTURE_PACKAGE_ORIGIN_MISMATCH", "capture task mismatch")
    if value.get("version") != "V0.2":
        raise ArtifactTransportError("CAPTURE_PACKAGE_ORIGIN_MISMATCH", "capture version mismatch")
    if type(value.get("slice")) is not int or value.get("slice") != 2:
        raise ArtifactTransportError("CAPTURE_PACKAGE_ORIGIN_MISMATCH", "capture slice mismatch")
    if (
        _parse_package_decimal(
            value.get("capture_workflow_run_id"), field="capture_workflow_run_id"
        )
        != workflow_run.run_id
    ):
        raise ArtifactTransportError(
            "CAPTURE_PACKAGE_ORIGIN_MISMATCH", "capture workflow run ID mismatch"
        )
    if (
        _parse_package_decimal(
            value.get("capture_workflow_run_attempt"), field="capture_workflow_run_attempt"
        )
        != workflow_run.run_attempt
    ):
        raise ArtifactTransportError(
            "CAPTURE_PACKAGE_ORIGIN_MISMATCH", "capture workflow run attempt mismatch"
        )
    if value.get("evidence_tool_head") != workflow_run.head_sha:
        raise ArtifactTransportError(
            "CAPTURE_PACKAGE_ORIGIN_MISMATCH", "evidence tooling head mismatch"
        )
    if value.get("rc_source_sha") != EXPECTED_RC_SOURCE_SHA:
        raise ArtifactTransportError("CAPTURE_PACKAGE_ORIGIN_MISMATCH", "RC source SHA mismatch")
    if value.get("rc_source_tree") != EXPECTED_RC_SOURCE_TREE:
        raise ArtifactTransportError("CAPTURE_PACKAGE_ORIGIN_MISMATCH", "RC source tree mismatch")
    return cast(dict[str, Any], value)


def _read_json_object(path: Path, *, error_code: str, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactTransportError(error_code, f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise ArtifactTransportError(error_code, f"{label} must be an object")
    return cast(dict[str, Any], value)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactTransportError("HANDOFF_ARCHIVE_READ_FAILED", type(exc).__name__) from exc
    return f"sha256:{digest.hexdigest()}"


def _canonical_handoff_payload_root(root: Path) -> Path:
    """Allow one archive wrapper directory, then require the exact D1 payload."""
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise ArtifactTransportError("HANDOFF_PAYLOAD_INVALID", type(exc).__name__) from exc
    if len(entries) == 1 and entries[0].is_dir() and not entries[0].is_symlink():
        root = entries[0]
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise ArtifactTransportError("HANDOFF_PAYLOAD_INVALID", type(exc).__name__) from exc
    expected = {VERIFIED_ARCHIVE_NAME, HANDOFF_RECEIPT_NAME}
    if {entry.name for entry in entries} != expected:
        raise ArtifactTransportError(
            "HANDOFF_PAYLOAD_INVALID", "handoff payload must contain exactly two files"
        )
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise ArtifactTransportError(
                "HANDOFF_PAYLOAD_INVALID", "handoff payload entries must be regular files"
            )
    return root


def _require_receipt_value(
    receipt: Mapping[str, Any], field: str, expected: Any, *, code: str
) -> Any:
    actual = receipt.get(field)
    if actual != expected:
        raise ArtifactTransportError(code, f"handoff receipt {field} mismatch")
    return actual


def _verify_embedded_transport_receipt(
    receipt_path: Path,
    *,
    repository: str,
    capture_artifact_id: str,
    capture_artifact_digest: str,
    capture_run_id: str,
    capture_run_attempt: str,
    capture_head_sha: str,
) -> dict[str, Any]:
    """Verify the D0 receipt without reimplementing its internal checksums."""
    receipt = _read_json_object(
        receipt_path, error_code="HANDOFF_RECEIPT_INVALID", label="transport receipt"
    )
    code = "HANDOFF_RECEIPT_BINDING_MISMATCH"
    _require_receipt_value(receipt, "schema_version", TRANSPORT_RECEIPT_SCHEMA_VERSION, code=code)
    _require_receipt_value(receipt, "repository", repository, code=code)
    capture_id = _parse_artifact_id(capture_artifact_id)
    _require_receipt_value(receipt, "artifact_id", capture_id, code=code)
    metadata_url = receipt.get("metadata_url")
    metadata_url_parts = (
        urllib.parse.urlsplit(metadata_url) if isinstance(metadata_url, str) else None
    )
    expected_metadata_path = f"/repos/{repository}/actions/artifacts/{capture_id}"
    if (
        metadata_url_parts is None
        or metadata_url_parts.scheme != "https"
        or not metadata_url_parts.hostname
        or metadata_url_parts.username is not None
        or metadata_url_parts.password is not None
        or metadata_url_parts.query
        or metadata_url_parts.fragment
        or metadata_url_parts.path != expected_metadata_path
    ):
        raise ArtifactTransportError(code, "handoff receipt metadata URL is not canonical")
    _require_receipt_value(
        receipt,
        "archive_endpoint_identity",
        f"GET {expected_metadata_path}/zip",
        code=code,
    )
    expected_capture_name = f"task012-live-evidence-{capture_run_id}-{capture_run_attempt}"
    _require_receipt_value(receipt, "artifact_name", expected_capture_name, code=code)
    expected_d0 = normalize_artifact_digest(capture_artifact_digest)
    for field in (
        "recorded_artifact_digest",
        "metadata_artifact_digest",
        "downloaded_archive_digest",
    ):
        if normalize_artifact_digest(cast(str, receipt.get(field))) != expected_d0:
            raise ArtifactTransportError(code, f"handoff receipt {field} mismatch")
    _require_receipt_value(receipt, "capture_workflow_run_id", capture_run_id, code=code)
    _require_receipt_value(receipt, "capture_workflow_run_attempt", capture_run_attempt, code=code)
    _require_receipt_value(receipt, "capture_head_sha", capture_head_sha, code=code)
    _require_receipt_value(receipt, "capture_head_branch", "main", code=code)
    _require_receipt_value(receipt, "workflow_run_id", int(capture_run_id), code=code)
    _require_receipt_value(receipt, "workflow_run_attempt", int(capture_run_attempt), code=code)
    _require_receipt_value(receipt, "workflow_name", CANONICAL_WORKFLOW_NAME, code=code)
    _require_receipt_value(receipt, "workflow_path", CANONICAL_WORKFLOW_PATH, code=code)
    _require_receipt_value(receipt, "workflow_event", CANONICAL_WORKFLOW_EVENT, code=code)
    _require_receipt_value(receipt, "workflow_head_sha", capture_head_sha, code=code)
    _require_receipt_value(receipt, "workflow_head_branch", "main", code=code)
    _require_receipt_value(receipt, "workflow_status", "completed", code=code)
    _require_receipt_value(receipt, "workflow_conclusion", "success", code=code)
    _require_receipt_value(receipt, "canonical_capture_origin_status", "PASS", code=code)
    _require_receipt_value(receipt, "transport_verification_status", "PASS", code=code)
    _require_receipt_value(receipt, "package_capture_workflow_run_id", capture_run_id, code=code)
    _require_receipt_value(
        receipt, "package_capture_workflow_run_attempt", capture_run_attempt, code=code
    )
    _require_receipt_value(receipt, "package_evidence_tool_head", capture_head_sha, code=code)
    _require_receipt_value(receipt, "package_rc_source_sha", EXPECTED_RC_SOURCE_SHA, code=code)
    _require_receipt_value(receipt, "package_rc_source_tree", EXPECTED_RC_SOURCE_TREE, code=code)
    return receipt


def _verify_embedded_capture_metadata(root: Path, receipt: Mapping[str, Any]) -> None:
    """Bind the re-extracted D0 package metadata to the D0 receipt."""
    metadata = _read_json_object(
        root / "metadata.json",
        error_code="HANDOFF_CAPTURE_PACKAGE_INVALID",
        label="embedded capture metadata",
    )
    if metadata.get("task") != "TASK-012":
        raise ArtifactTransportError("HANDOFF_CAPTURE_PACKAGE_INVALID", "capture task mismatch")
    if metadata.get("version") != "V0.2":
        raise ArtifactTransportError("HANDOFF_CAPTURE_PACKAGE_INVALID", "capture version mismatch")
    if type(metadata.get("slice")) is not int or metadata.get("slice") != 2:
        raise ArtifactTransportError("HANDOFF_CAPTURE_PACKAGE_INVALID", "capture slice mismatch")
    expected_run_id = cast(str, receipt["capture_workflow_run_id"])
    expected_attempt = cast(str, receipt["capture_workflow_run_attempt"])
    if (
        _parse_package_decimal(metadata.get("capture_workflow_run_id"), field="capture run ID")
        != int(expected_run_id)
        or metadata.get("capture_workflow_run_id") != expected_run_id
    ):
        raise ArtifactTransportError(
            "HANDOFF_CAPTURE_PACKAGE_INVALID", "embedded capture workflow run ID mismatch"
        )
    if (
        _parse_package_decimal(
            metadata.get("capture_workflow_run_attempt"), field="capture run attempt"
        )
        != int(expected_attempt)
        or metadata.get("capture_workflow_run_attempt") != expected_attempt
    ):
        raise ArtifactTransportError(
            "HANDOFF_CAPTURE_PACKAGE_INVALID", "embedded capture workflow attempt mismatch"
        )
    for field, receipt_field in (
        ("evidence_tool_head", "capture_head_sha"),
        ("rc_source_sha", "package_rc_source_sha"),
        ("rc_source_tree", "package_rc_source_tree"),
    ):
        if metadata.get(field) != receipt.get(receipt_field):
            raise ArtifactTransportError(
                "HANDOFF_CAPTURE_PACKAGE_INVALID", f"embedded capture {field} mismatch"
            )


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
    workflow_run = client.fetch_verified_workflow_run(
        metadata=metadata,
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
        package_origin = _read_capture_package_origin(temporary_extracted, workflow_run)
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
            "workflow_run_id": workflow_run.run_id,
            "workflow_run_attempt": workflow_run.run_attempt,
            "workflow_name": workflow_run.name,
            "workflow_path": workflow_run.path,
            "workflow_event": workflow_run.event,
            "workflow_head_sha": workflow_run.head_sha,
            "workflow_head_branch": workflow_run.head_branch,
            "workflow_status": workflow_run.status,
            "workflow_conclusion": workflow_run.conclusion,
            "metadata_url": metadata.metadata_url,
            "archive_endpoint_identity": metadata.archive_endpoint_identity,
            "package_capture_workflow_run_id": package_origin["capture_workflow_run_id"],
            "package_capture_workflow_run_attempt": package_origin["capture_workflow_run_attempt"],
            "package_evidence_tool_head": package_origin["evidence_tool_head"],
            "package_rc_source_sha": package_origin["rc_source_sha"],
            "package_rc_source_tree": package_origin["rc_source_tree"],
            "canonical_capture_origin_status": "PASS",
            "verified_at": _now(),
            "transport_verification_status": "PASS",
        }
        if workflow_run.workflow_id is not None:
            receipt["workflow_id"] = workflow_run.workflow_id
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


def verify_handoff_download(
    *,
    repository: str,
    handoff_artifact_id: str,
    expected_handoff_artifact_digest: str,
    expected_transport_run_id: str,
    expected_transport_run_attempt: str,
    expected_transport_head_sha: str,
    expected_capture_artifact_id: str,
    expected_capture_artifact_digest: str,
    expected_capture_run_id: str,
    expected_capture_run_attempt: str,
    expected_capture_head_sha: str,
    output_dir: str | Path,
    execute_download: bool = False,
    env: Mapping[str, str] | None = None,
    api_base_url: str = DEFAULT_API_BASE_URL,
) -> VerifiedHandoffResult:
    """Verify D1 and expose the embedded D0 package for later assembly."""
    environment = os.environ if env is None else env
    if not execute_download:
        raise ArtifactTransportError(
            "HANDOFF_DOWNLOAD_EXECUTION_NOT_EXPLICIT",
            "verify-handoff-download requires --execute-download",
        )
    if environment.get(HANDOFF_DOWNLOAD_AUTHORIZATION_ENV) != "YES":
        raise ArtifactTransportError(
            "HANDOFF_DOWNLOAD_EXECUTION_NOT_AUTHORIZED",
            f"{HANDOFF_DOWNLOAD_AUTHORIZATION_ENV} must be exactly YES",
        )
    token = _validate_token(environment.get("GITHUB_TOKEN"))
    repository = _validate_repository(repository)
    parsed_handoff_id = _parse_artifact_id(handoff_artifact_id)
    parsed_capture_id = _parse_artifact_id(expected_capture_artifact_id)
    expected_handoff_digest = normalize_artifact_digest(expected_handoff_artifact_digest)
    expected_capture_digest = normalize_artifact_digest(expected_capture_artifact_digest)
    expected_transport_run_id = _parse_positive_decimal(
        expected_transport_run_id, field="transport run ID"
    )
    expected_transport_run_attempt = _parse_positive_decimal(
        expected_transport_run_attempt, field="transport run attempt"
    )
    expected_capture_run_id = _parse_positive_decimal(
        expected_capture_run_id, field="capture run ID"
    )
    expected_capture_run_attempt = _parse_positive_decimal(
        expected_capture_run_attempt, field="capture run attempt"
    )
    expected_transport_head_sha = _validate_head_sha(expected_transport_head_sha)
    expected_capture_head_sha = _validate_head_sha(expected_capture_head_sha)
    output = _prepare_output_dir(output_dir)
    client = ArtifactTransportClient(repository, token, api_base_url)
    metadata = client.fetch_verified_handoff_metadata(
        artifact_id=parsed_handoff_id,
        expected_digest=expected_handoff_digest,
        expected_transport_run_id=expected_transport_run_id,
        expected_transport_run_attempt=expected_transport_run_attempt,
        expected_transport_head_sha=expected_transport_head_sha,
        expected_capture_run_id=expected_capture_run_id,
        expected_capture_run_attempt=expected_capture_run_attempt,
    )
    transport_workflow = client.fetch_verified_handoff_workflow_run(
        metadata=metadata,
        expected_transport_run_id=expected_transport_run_id,
        expected_transport_run_attempt=expected_transport_run_attempt,
        expected_transport_head_sha=expected_transport_head_sha,
    )

    temporary_archive = output / f".handoff-download-{uuid.uuid4().hex}.part"
    temporary_payload = output / f".handoff-payload-{uuid.uuid4().hex}"
    temporary_capture = output / f".handoff-capture-{uuid.uuid4().hex}"
    promoted: list[Path] = []
    final_archive = output / VERIFIED_HANDOFF_ARCHIVE_NAME
    final_capture = output / HANDOFF_CAPTURE_DIRECTORY_NAME
    final_receipt = output / VERIFIED_HANDOFF_RECEIPT_NAME
    try:
        downloaded_digest = client.download_archive(
            artifact_id=parsed_handoff_id, destination=temporary_archive
        )
        if (
            downloaded_digest != expected_handoff_digest
            or downloaded_digest != metadata.artifact_digest
        ):
            raise ArtifactTransportError(
                "HANDOFF_TRANSPORT_DIGEST_MISMATCH",
                "recorded, metadata, and downloaded handoff digests differ",
            )
        _safe_extract_archive(temporary_archive, temporary_payload)
        payload_root = _canonical_handoff_payload_root(temporary_payload)
        receipt_path = payload_root / HANDOFF_RECEIPT_NAME
        receipt = _verify_embedded_transport_receipt(
            receipt_path,
            repository=repository,
            capture_artifact_id=str(parsed_capture_id),
            capture_artifact_digest=expected_capture_digest,
            capture_run_id=expected_capture_run_id,
            capture_run_attempt=expected_capture_run_attempt,
            capture_head_sha=expected_capture_head_sha,
        )
        embedded_archive = payload_root / VERIFIED_ARCHIVE_NAME
        embedded_digest = _hash_file(embedded_archive)
        if embedded_digest != expected_capture_digest:
            raise ArtifactTransportError(
                "HANDOFF_EMBEDDED_CAPTURE_DIGEST_MISMATCH",
                "embedded verified-artifact.zip digest does not equal D0",
            )

        _safe_extract_archive(embedded_archive, temporary_capture)
        _verify_capture_package_shape(temporary_capture)
        _verify_embedded_capture_metadata(temporary_capture, receipt)

        os.replace(temporary_archive, final_archive)
        promoted.append(final_archive)
        os.replace(temporary_capture, final_capture)
        promoted.append(final_capture)
        handoff_receipt: dict[str, Any] = {
            "schema_version": HANDOFF_VERIFICATION_RECEIPT_SCHEMA_VERSION,
            "repository": repository,
            "handoff_artifact_id": metadata.artifact_id,
            "handoff_artifact_name": metadata.artifact_name,
            "recorded_handoff_artifact_digest": expected_handoff_digest,
            "metadata_handoff_artifact_digest": metadata.artifact_digest,
            "downloaded_handoff_archive_digest": downloaded_digest,
            "transport_workflow_run_id": transport_workflow.run_id,
            "transport_workflow_run_attempt": transport_workflow.run_attempt,
            "transport_workflow_name": transport_workflow.name,
            "transport_workflow_path": transport_workflow.path,
            "transport_workflow_event": transport_workflow.event,
            "transport_workflow_head_sha": transport_workflow.head_sha,
            "transport_workflow_head_branch": transport_workflow.head_branch,
            "transport_workflow_status": transport_workflow.status,
            "transport_workflow_conclusion": transport_workflow.conclusion,
            "transport_verifier_job_id": transport_workflow.verified_job_id,
            "transport_verifier_job_name": transport_workflow.verified_job_name,
            "source_capture_artifact_id": parsed_capture_id,
            "source_capture_artifact_digest": expected_capture_digest,
            "source_capture_workflow_run_id": expected_capture_run_id,
            "source_capture_workflow_run_attempt": expected_capture_run_attempt,
            "source_capture_head_sha": expected_capture_head_sha,
            "source_capture_head_branch": "main",
            "embedded_capture_archive_digest": embedded_digest,
            "capture_root": str(final_capture),
            "observation_bundle": str(final_capture / "observation-bundle.json"),
            "verified_at": _now(),
            "verified_handoff_status": "PASS",
        }
        if transport_workflow.workflow_id is not None:
            handoff_receipt["transport_workflow_id"] = transport_workflow.workflow_id
        _atomic_write_json(final_receipt, handoff_receipt)
        return VerifiedHandoffResult(
            receipt_path=final_receipt,
            capture_root=final_capture,
            observation_bundle=final_capture / "observation-bundle.json",
        )
    except Exception:
        if temporary_archive.exists():
            temporary_archive.unlink()
        if temporary_payload.exists():
            shutil.rmtree(temporary_payload)
        if temporary_capture.exists():
            shutil.rmtree(temporary_capture)
        if final_receipt.exists():
            final_receipt.unlink()
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
    handoff = subparsers.add_parser("verify-handoff-download")
    handoff.add_argument("--execute-download", action="store_true")
    handoff.add_argument("--repository", required=True)
    handoff.add_argument("--handoff-artifact-id", required=True)
    handoff.add_argument("--expected-handoff-artifact-digest", required=True)
    handoff.add_argument("--expected-transport-run-id", required=True)
    handoff.add_argument("--expected-transport-run-attempt", required=True)
    handoff.add_argument("--expected-transport-head-sha", required=True)
    handoff.add_argument("--expected-capture-artifact-id", required=True)
    handoff.add_argument("--expected-capture-artifact-digest", required=True)
    handoff.add_argument("--expected-capture-run-id", required=True)
    handoff.add_argument("--expected-capture-run-attempt", required=True)
    handoff.add_argument("--expected-capture-head-sha", required=True)
    handoff.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify-download":
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
        else:
            result = verify_handoff_download(
                repository=args.repository,
                handoff_artifact_id=args.handoff_artifact_id,
                expected_handoff_artifact_digest=args.expected_handoff_artifact_digest,
                expected_transport_run_id=args.expected_transport_run_id,
                expected_transport_run_attempt=args.expected_transport_run_attempt,
                expected_transport_head_sha=args.expected_transport_head_sha,
                expected_capture_artifact_id=args.expected_capture_artifact_id,
                expected_capture_artifact_digest=args.expected_capture_artifact_digest,
                expected_capture_run_id=args.expected_capture_run_id,
                expected_capture_run_attempt=args.expected_capture_run_attempt,
                expected_capture_head_sha=args.expected_capture_head_sha,
                output_dir=args.output_dir,
                execute_download=args.execute_download,
            )
            print(f"CAPTURE_ROOT={result.capture_root}")
            print(f"OBSERVATION_BUNDLE={result.observation_bundle}")
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
    "HandoffArtifactMetadata",
    "WorkflowRunMetadata",
    "VerifiedHandoffResult",
    "HANDOFF_VERIFICATION_RECEIPT_SCHEMA_VERSION",
    "TRANSPORT_RECEIPT_SCHEMA_VERSION",
    "main",
    "normalize_artifact_digest",
    "verify_handoff_download",
    "verify_download",
]
