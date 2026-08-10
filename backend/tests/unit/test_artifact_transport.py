from __future__ import annotations

import hashlib
import io
import json
import stat
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pytest

import cold_storage.release.artifact_transport as transport
from cold_storage.release.artifact_transport import (
    ArtifactTransportError,
    normalize_artifact_digest,
    verify_attestation_download,
    verify_download,
    verify_handoff_download,
)
from cold_storage.release.live_attestation import build_attestation

REPOSITORY = "xuezhiorange-png/cold-storage-planning-agent"
ARTIFACT_ID = "1234"
RUN_ID = "700"
RUN_ATTEMPT = "2"
HEAD_SHA = "a" * 40
API_BASE_URL = "https://api.github.test"
STORAGE_URL = "https://artifact-storage.example/task012/signed-archive.zip?sig=synthetic"
RC_SOURCE_SHA = "043731fea4e60feb6b929c524c4b68e87ed67bd7"
RC_SOURCE_TREE = "b456e77f07a0cef801c57d2f089a318c35c145c4"
SECRET_TOKEN = "TASK012-SUPER-SECRET-REDIRECT-TOKEN"
HANDOFF_ID = "5678"
TRANSPORT_RUN_ID = "800"
TRANSPORT_RUN_ATTEMPT = "1"
TRANSPORT_HEAD_SHA = "c" * 40
HANDOFF_STORAGE_URL = "https://artifact-storage.example/task012/signed-handoff.zip?sig=synthetic"


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        fail_after_first_read: bool = False,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._stream = io.BytesIO(payload)
        self._fail_after_first_read = fail_after_first_read
        self._read_count = 0
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if self._fail_after_first_read and self._read_count > 0:
            raise OSError("synthetic interrupted download")
        self._read_count += 1
        return self._stream.read(size)

    def getcode(self) -> int:
        return self.status

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)

    def close(self) -> None:
        self.closed = True


def _zip_bytes(
    extra_entries: list[tuple[str, bytes]] | None = None,
    *,
    duplicate_entry: bool = False,
    symlink_entry: bool = False,
    package_metadata: dict[str, Any] | None = None,
) -> bytes:
    metadata = package_metadata or {
        "task": "TASK-012",
        "version": "V0.2",
        "slice": 2,
        "capture_workflow_run_id": RUN_ID,
        "capture_workflow_run_attempt": RUN_ATTEMPT,
        "evidence_tool_head": HEAD_SHA,
        "rc_source_sha": RC_SOURCE_SHA,
        "rc_source_tree": RC_SOURCE_TREE,
    }
    entries = [
        ("observation-bundle.json", b"{}"),
        ("metadata.json", json.dumps(metadata, sort_keys=True).encode("utf-8")),
        ("expected-inputs.json", b"{}"),
        ("build-a/", b""),
        ("build-a/build-record.json", b"{}"),
        ("build-b/", b""),
        ("build-b/build-record.json", b"{}"),
        ("SHA256SUMS", b"synthetic\n"),
        ("SHA256SUMS.sha256", b"synthetic\n"),
    ]
    if extra_entries:
        entries.extend(extra_entries)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
        if duplicate_entry:
            archive.writestr("duplicate.txt", b"one")
            archive.writestr("duplicate.txt", b"two")
        if symlink_entry:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target")
    return output.getvalue()


def _metadata(archive: bytes, **overrides: Any) -> dict[str, Any]:
    digest = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    value: dict[str, Any] = {
        "id": int(ARTIFACT_ID),
        "name": f"task012-live-evidence-{RUN_ID}-{RUN_ATTEMPT}",
        "expired": False,
        "digest": digest,
        "archive_download_url": (
            f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}/zip"
        ),
        "workflow_run": {
            "id": int(RUN_ID),
            "run_attempt": int(RUN_ATTEMPT),
            "head_sha": HEAD_SHA,
            "head_branch": "main",
        },
    }
    for key, replacement in overrides.items():
        if key == "workflow_run":
            value["workflow_run"] = {**value["workflow_run"], **replacement}
        else:
            value[key] = replacement
    return value


def _install_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    archive: bytes,
    metadata: dict[str, Any] | None = None,
    workflow: dict[str, Any] | None = None,
    metadata_status: int = 200,
    workflow_status: int = 200,
    redirect_status: int = 302,
    redirect_location: str | None = STORAGE_URL,
    storage_status: int = 200,
    second_redirect: bool = False,
    partial_download: bool = False,
) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []
    metadata_payload = json.dumps(_metadata(archive) if metadata is None else metadata).encode(
        "utf-8"
    )
    workflow_payload = json.dumps(
        {
            "id": int(RUN_ID),
            "run_attempt": int(RUN_ATTEMPT),
            "name": "ci",
            "path": ".github/workflows/ci.yml",
            "event": "workflow_dispatch",
            "head_sha": HEAD_SHA,
            "head_branch": "main",
            "status": "completed",
            "conclusion": "success",
            "workflow_id": 987,
        }
        if workflow is None
        else workflow
    ).encode("utf-8")

    metadata_url = f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}"
    workflow_url = f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{RUN_ID}"
    archive_url = f"{metadata_url}/zip"

    def fake_open(
        request: urllib.request.Request,
        timeout: int = 60,
        *,
        follow_redirects: bool = True,
    ) -> FakeResponse:
        del timeout, follow_redirects
        calls.append(request)
        if request.full_url == metadata_url:
            return FakeResponse(metadata_payload, status=metadata_status)
        if request.full_url == workflow_url:
            return FakeResponse(workflow_payload, status=workflow_status)
        if request.full_url == archive_url:
            headers = {} if redirect_location is None else {"Location": redirect_location}
            return FakeResponse(b"", status=redirect_status, headers=headers)
        if request.full_url == STORAGE_URL:
            if second_redirect:
                return FakeResponse(b"", status=302, headers={"Location": STORAGE_URL})
            return FakeResponse(
                archive,
                status=storage_status,
                fail_after_first_read=partial_download,
            )
        raise urllib.error.URLError(f"unexpected synthetic URL: {request.full_url}")

    monkeypatch.setattr(transport, "_open_url", fake_open)
    return calls


def _verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    archive: bytes,
    metadata: dict[str, Any] | None = None,
    expected_digest: str | None = None,
    metadata_status: int = 200,
    archive_status: int = 200,
    partial_download: bool = False,
    **kwargs: Any,
) -> tuple[Path, list[urllib.request.Request]]:
    digest = expected_digest or f"sha256:{hashlib.sha256(archive).hexdigest()}"
    calls = _install_http(
        monkeypatch,
        archive=archive,
        metadata=metadata,
        workflow=kwargs.pop("workflow", None),
        metadata_status=metadata_status,
        redirect_status=kwargs.pop("redirect_status", 302),
        redirect_location=kwargs.pop("redirect_location", STORAGE_URL),
        storage_status=kwargs.pop("storage_status", archive_status),
        second_redirect=kwargs.pop("second_redirect", False),
        partial_download=partial_download,
    )
    receipt = verify_download(
        repository=REPOSITORY,
        artifact_id=kwargs.pop("artifact_id", ARTIFACT_ID),
        expected_artifact_digest=digest,
        expected_capture_run_id=kwargs.pop("run_id", RUN_ID),
        expected_capture_run_attempt=kwargs.pop("run_attempt", RUN_ATTEMPT),
        expected_capture_head_sha=kwargs.pop("head_sha", HEAD_SHA),
        output_dir=tmp_path / "transport-output",
        execute_download=True,
        env={
            "GITHUB_TOKEN": SECRET_TOKEN,
            "TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED": "YES",
        },
        api_base_url=API_BASE_URL,
        **kwargs,
    )
    return receipt, calls


def test_missing_cli_guard_makes_zero_http_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _install_http(monkeypatch, archive=_zip_bytes())
    with pytest.raises(ArtifactTransportError, match="DOWNLOAD_EXECUTION_NOT_EXPLICIT"):
        verify_download(
            repository=REPOSITORY,
            artifact_id=ARTIFACT_ID,
            expected_artifact_digest="a" * 64,
            expected_capture_run_id=RUN_ID,
            expected_capture_run_attempt=RUN_ATTEMPT,
            expected_capture_head_sha=HEAD_SHA,
            output_dir=tmp_path / "output",
            env={"TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED": "YES"},
            api_base_url=API_BASE_URL,
        )
    assert calls == []


def test_missing_environment_guard_makes_zero_http_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _install_http(monkeypatch, archive=_zip_bytes())
    with pytest.raises(ArtifactTransportError, match="DOWNLOAD_EXECUTION_NOT_AUTHORIZED"):
        verify_download(
            repository=REPOSITORY,
            artifact_id=ARTIFACT_ID,
            expected_artifact_digest="a" * 64,
            expected_capture_run_id=RUN_ID,
            expected_capture_run_attempt=RUN_ATTEMPT,
            expected_capture_head_sha=HEAD_SHA,
            output_dir=tmp_path / "output",
            execute_download=True,
            env={"GITHUB_TOKEN": "not-used"},
            api_base_url=API_BASE_URL,
        )
    assert calls == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [("a" * 64, "sha256:" + "a" * 64), ("sha256:" + "a" * 64, "sha256:" + "a" * 64)],
)
def test_digest_normalization_accepts_only_supported_canonical_forms(
    value: str, expected: str
) -> None:
    assert normalize_artifact_digest(value) == expected


@pytest.mark.parametrize(
    "value", ["SHA256:" + "a" * 64, "sha256:" + "A" * 64, "md5:" + "a" * 32, "a", ""]
)
def test_digest_normalization_rejects_noncanonical_forms(value: str) -> None:
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_DIGEST_INVALID"):
        normalize_artifact_digest(value)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"id": 9999}, "ARTIFACT_METADATA_ID_MISMATCH"),
        ({"expired": True}, "ARTIFACT_EXPIRED"),
        ({"digest": "sha256:" + "b" * 64}, "ARTIFACT_METADATA_DIGEST_MISMATCH"),
        ({"workflow_run": {"id": 999}}, "ARTIFACT_WORKFLOW_BINDING_MISMATCH"),
        ({"workflow_run": {"head_sha": "b" * 40}}, "ARTIFACT_WORKFLOW_BINDING_MISMATCH"),
        ({"workflow_run": {"head_branch": "feature"}}, "ARTIFACT_WORKFLOW_BINDING_MISMATCH"),
        ({"name": "other-artifact"}, "ARTIFACT_NAME_MISMATCH"),
    ],
)
def test_metadata_bindings_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any],
    error: str,
) -> None:
    archive = _zip_bytes()
    metadata = _metadata(archive, **overrides)
    calls = _install_http(monkeypatch, archive=archive, metadata=metadata)
    with pytest.raises(ArtifactTransportError, match=error):
        verify_download(
            repository=REPOSITORY,
            artifact_id=ARTIFACT_ID,
            expected_artifact_digest=f"sha256:{hashlib.sha256(archive).hexdigest()}",
            expected_capture_run_id=RUN_ID,
            expected_capture_run_attempt=RUN_ATTEMPT,
            expected_capture_head_sha=HEAD_SHA,
            output_dir=tmp_path / "output",
            execute_download=True,
            env={
                "GITHUB_TOKEN": "secret",
                "TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED": "YES",
            },
            api_base_url=API_BASE_URL,
        )
    assert len(calls) == 1


def test_metadata_run_attempt_and_archive_endpoint_are_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_bytes()
    metadata = _metadata(archive, workflow_run={"run_attempt": 3})
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_WORKFLOW_BINDING_MISMATCH"):
        _verify(tmp_path, monkeypatch, archive=archive, metadata=metadata)


def test_malformed_metadata_and_http_failure_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_bytes()
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_METADATA_ID_MISMATCH"):
        _verify(tmp_path, monkeypatch, archive=archive, metadata={})

    with pytest.raises(ArtifactTransportError, match="ARTIFACT_HTTP_ERROR"):
        _verify(tmp_path / "http", monkeypatch, archive=archive, metadata_status=503)


def test_download_digest_mismatch_and_partial_download_leave_no_verified_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_bytes()
    changed_archive = archive + b"tampered"
    expected = f"sha256:{hashlib.sha256(archive).hexdigest()}"
    calls = _install_http(monkeypatch, archive=changed_archive, metadata=_metadata(archive))
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_TRANSPORT_DIGEST_MISMATCH"):
        verify_download(
            repository=REPOSITORY,
            artifact_id=ARTIFACT_ID,
            expected_artifact_digest=expected,
            expected_capture_run_id=RUN_ID,
            expected_capture_run_attempt=RUN_ATTEMPT,
            expected_capture_head_sha=HEAD_SHA,
            output_dir=tmp_path / "mismatch",
            execute_download=True,
            env={"GITHUB_TOKEN": "secret", "TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED": "YES"},
            api_base_url=API_BASE_URL,
        )
    assert len(calls) == 4
    assert not (tmp_path / "mismatch" / "verified-artifact.zip").exists()

    with pytest.raises(ArtifactTransportError, match="ARTIFACT_DOWNLOAD_FAILED"):
        _verify(tmp_path / "partial", monkeypatch, archive=archive, partial_download=True)
    assert not (tmp_path / "partial" / "verified-artifact.zip").exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"extra_entries": [("../escape.txt", b"escape")]},
        {"extra_entries": [("/absolute.txt", b"absolute")]},
        {"extra_entries": [("..\\escape.txt", b"escape")]},
        {"duplicate_entry": True},
        {"symlink_entry": True},
    ],
)
def test_unsafe_zip_entries_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any]
) -> None:
    archive = _zip_bytes(**kwargs)
    with pytest.raises(ArtifactTransportError):
        _verify(tmp_path / "unsafe", monkeypatch, archive=archive)
    assert not (tmp_path / "unsafe" / "verified-artifact.zip").exists()


def test_happy_path_writes_receipt_and_uses_exact_id_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_bytes()
    receipt, calls = _verify(tmp_path, monkeypatch, archive=archive)
    output = receipt.parent
    assert [request.full_url for request in calls] == [
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{RUN_ID}",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}/zip",
        STORAGE_URL,
    ]
    assert calls[0].get_header("Authorization") == f"Bearer {SECRET_TOKEN}"
    assert calls[1].get_header("Authorization") == f"Bearer {SECRET_TOKEN}"
    assert calls[2].get_header("Authorization") == f"Bearer {SECRET_TOKEN}"
    assert calls[3].get_header("Authorization") is None
    assert calls[3].get_header("Cookie") is None
    assert calls[3].get_header("X-github-api-version") is None
    assert (output / "verified-artifact.zip").read_bytes() == archive
    assert (output / "extracted" / "observation-bundle.json").is_file()
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt_value["transport_verification_status"] == "PASS"
    assert receipt_value["recorded_artifact_digest"] == receipt_value["metadata_artifact_digest"]
    assert receipt_value["metadata_artifact_digest"] == receipt_value["downloaded_archive_digest"]
    assert receipt_value["workflow_name"] == "ci"
    assert receipt_value["workflow_path"] == ".github/workflows/ci.yml"
    assert receipt_value["workflow_event"] == "workflow_dispatch"
    assert receipt_value["canonical_capture_origin_status"] == "PASS"
    assert "test-token-that-must-not-be-written" not in receipt.read_text(encoding="utf-8")
    assert SECRET_TOKEN not in receipt.read_text(encoding="utf-8")


def test_authenticated_artifact_zip_redirect_does_not_forward_github_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_bytes()
    receipt, calls = _verify(tmp_path, monkeypatch, archive=archive)
    assert receipt.exists()
    assert calls[2].full_url.endswith(f"/artifacts/{ARTIFACT_ID}/zip")
    assert calls[2].get_header("Authorization") == f"Bearer {SECRET_TOKEN}"
    assert calls[3].full_url == STORAGE_URL
    assert calls[3].get_header("Authorization") is None
    assert calls[3].get_header("Cookie") is None
    assert calls[3].get_header("X-github-api-version") is None


@pytest.mark.parametrize(
    ("redirect_status", "redirect_location", "error"),
    [
        (302, None, "ARTIFACT_REDIRECT_INVALID"),
        (302, "http://artifact-storage.example/archive", "ARTIFACT_REDIRECT_INVALID"),
        (302, "/relative/archive", "ARTIFACT_REDIRECT_INVALID"),
        (
            302,
            "https://user:password@artifact-storage.example/archive",
            "ARTIFACT_REDIRECT_INVALID",
        ),
        (302, "https://artifact-storage.example/archive#fragment", "ARTIFACT_REDIRECT_INVALID"),
        (301, STORAGE_URL, "ARTIFACT_REDIRECT_INVALID"),
        (302, API_BASE_URL + "/repos/x/y/actions/artifacts/1234/zip", "ARTIFACT_REDIRECT_INVALID"),
    ],
)
def test_redirect_validation_fail_closed_without_verified_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    redirect_status: int,
    redirect_location: str | None,
    error: str,
) -> None:
    archive = _zip_bytes()
    with pytest.raises(ArtifactTransportError, match=error):
        _verify(
            tmp_path / "redirect",
            monkeypatch,
            archive=archive,
            redirect_status=redirect_status,
            redirect_location=redirect_location,
        )
    output = tmp_path / "redirect" / "transport-output"
    assert not (output / "verified-artifact.zip").exists()
    assert not (output / "artifact-transport-receipt.json").exists()


def test_second_redirect_is_rejected_before_archive_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_REDIRECT_CHAIN_REJECTED"):
        _verify(tmp_path, monkeypatch, archive=_zip_bytes(), second_redirect=True)
    assert not (tmp_path / "transport-output" / "verified-artifact.zip").exists()


def test_redirect_failures_do_not_expose_token_in_error_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ArtifactTransportError) as caught:
        _verify(
            tmp_path,
            monkeypatch,
            archive=_zip_bytes(),
            redirect_location="http://artifact-storage.example/archive",
        )
    assert SECRET_TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "workflow_override",
    [
        {"id": 701},
        {"event": "pull_request"},
        {"event": "push"},
        {"head_branch": "feature"},
        {"head_sha": "b" * 40},
        {"run_attempt": 3},
        {"path": ".github/workflows/other.yml"},
        {"name": "other"},
        {"status": "in_progress"},
        {"conclusion": "failure"},
    ],
)
def test_authoritative_workflow_run_bindings_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workflow_override: dict[str, Any],
) -> None:
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_WORKFLOW_BINDING_MISMATCH"):
        _verify(
            tmp_path / "workflow",
            monkeypatch,
            archive=_zip_bytes(),
            workflow={
                "id": int(RUN_ID),
                "run_attempt": int(RUN_ATTEMPT),
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "workflow_dispatch",
                "head_sha": HEAD_SHA,
                "head_branch": "main",
                "status": "completed",
                "conclusion": "success",
                "workflow_id": 987,
                **workflow_override,
            },
        )


@pytest.mark.parametrize(
    "field",
    [
        "capture_workflow_run_id",
        "capture_workflow_run_attempt",
        "evidence_tool_head",
        "rc_source_sha",
        "rc_source_tree",
        "task",
        "version",
        "slice",
    ],
)
def test_package_origin_metadata_is_bound_before_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    package_metadata: dict[str, Any] = {
        "task": "TASK-012",
        "version": "V0.2",
        "slice": 2,
        "capture_workflow_run_id": RUN_ID,
        "capture_workflow_run_attempt": RUN_ATTEMPT,
        "evidence_tool_head": HEAD_SHA,
        "rc_source_sha": RC_SOURCE_SHA,
        "rc_source_tree": RC_SOURCE_TREE,
    }
    package_metadata[field] = {
        "capture_workflow_run_id": "701",
        "capture_workflow_run_attempt": "3",
        "evidence_tool_head": "b" * 40,
        "rc_source_sha": "c" * 40,
        "rc_source_tree": "d" * 40,
        "task": "OTHER",
        "version": "V9",
        "slice": 9,
    }[field]
    archive = _zip_bytes(package_metadata=package_metadata)
    with pytest.raises(ArtifactTransportError, match="CAPTURE_PACKAGE_ORIGIN_MISMATCH"):
        _verify(tmp_path / "package", monkeypatch, archive=archive)
    output = tmp_path / "package" / "transport-output"
    assert not (output / "artifact-transport-receipt.json").exists()


def _d0_receipt(capture_archive: bytes, **overrides: Any) -> dict[str, Any]:
    digest = f"sha256:{hashlib.sha256(capture_archive).hexdigest()}"
    receipt: dict[str, Any] = {
        "schema_version": transport.TRANSPORT_RECEIPT_SCHEMA_VERSION,
        "repository": REPOSITORY,
        "artifact_id": int(ARTIFACT_ID),
        "artifact_name": f"task012-live-evidence-{RUN_ID}-{RUN_ATTEMPT}",
        "metadata_url": f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}",
        "archive_endpoint_identity": (
            f"GET /repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}/zip"
        ),
        "recorded_artifact_digest": digest,
        "metadata_artifact_digest": digest,
        "downloaded_archive_digest": digest,
        "capture_workflow_run_id": RUN_ID,
        "capture_workflow_run_attempt": RUN_ATTEMPT,
        "capture_head_sha": HEAD_SHA,
        "capture_head_branch": "main",
        "workflow_run_id": int(RUN_ID),
        "workflow_run_attempt": int(RUN_ATTEMPT),
        "workflow_name": "ci",
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_event": "workflow_dispatch",
        "workflow_head_sha": HEAD_SHA,
        "workflow_head_branch": "main",
        "workflow_status": "completed",
        "workflow_conclusion": "success",
        "package_capture_workflow_run_id": RUN_ID,
        "package_capture_workflow_run_attempt": RUN_ATTEMPT,
        "package_evidence_tool_head": HEAD_SHA,
        "package_rc_source_sha": RC_SOURCE_SHA,
        "package_rc_source_tree": RC_SOURCE_TREE,
        "canonical_capture_origin_status": "PASS",
        "transport_verification_status": "PASS",
    }
    receipt.update(overrides)
    return receipt


def _handoff_archive(
    capture_archive: bytes,
    *,
    receipt: dict[str, Any] | None = None,
    extra_entries: list[tuple[str, bytes]] | None = None,
    top_level: str | None = None,
) -> bytes:
    prefix = f"{top_level}/" if top_level else ""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            prefix + "verified-artifact.zip",
            capture_archive,
        )
        archive.writestr(
            prefix + "artifact-transport-receipt.json",
            json.dumps(receipt or _d0_receipt(capture_archive), sort_keys=True).encode("utf-8"),
        )
        for name, data in extra_entries or []:
            archive.writestr(prefix + name, data)
    return output.getvalue()


def _handoff_metadata(handoff_archive: bytes, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": int(HANDOFF_ID),
        "name": (
            f"task012-verified-transport-{RUN_ID}-{RUN_ATTEMPT}-"
            f"{TRANSPORT_RUN_ID}-{TRANSPORT_RUN_ATTEMPT}"
        ),
        "expired": False,
        "digest": f"sha256:{hashlib.sha256(handoff_archive).hexdigest()}",
        "archive_download_url": (
            f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{HANDOFF_ID}/zip"
        ),
        "workflow_run": {
            "id": int(TRANSPORT_RUN_ID),
            "run_attempt": int(TRANSPORT_RUN_ATTEMPT),
            "head_sha": TRANSPORT_HEAD_SHA,
            "head_branch": "main",
        },
    }
    for key, replacement in overrides.items():
        if key == "workflow_run":
            value["workflow_run"] = {**value["workflow_run"], **replacement}
        else:
            value[key] = replacement
    return value


def _install_handoff_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    handoff_archive: bytes,
    metadata: dict[str, Any] | None = None,
    workflow: dict[str, Any] | None = None,
    jobs: list[dict[str, Any]] | None = None,
    storage_archive: bytes | None = None,
    redirect_location: str | None = HANDOFF_STORAGE_URL,
) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []
    metadata_payload = json.dumps(
        _handoff_metadata(handoff_archive) if metadata is None else metadata
    ).encode("utf-8")
    workflow_payload = json.dumps(
        {
            "id": int(TRANSPORT_RUN_ID),
            "run_attempt": int(TRANSPORT_RUN_ATTEMPT),
            "name": "ci",
            "path": ".github/workflows/ci.yml",
            "event": "workflow_dispatch",
            "head_sha": TRANSPORT_HEAD_SHA,
            "head_branch": "main",
            "status": "completed",
            "conclusion": "success",
            "workflow_id": 654,
        }
        if workflow is None
        else workflow
    ).encode("utf-8")
    jobs_payload = json.dumps(
        {
            "jobs": jobs
            if jobs is not None
            else [
                {
                    "id": 4567,
                    "name": "live-evidence-artifact-transport-verify",
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        }
    ).encode("utf-8")
    metadata_url = f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{HANDOFF_ID}"
    workflow_url = f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{TRANSPORT_RUN_ID}"
    jobs_url = f"{workflow_url}/jobs?per_page=100"
    archive_url = f"{metadata_url}/zip"

    def fake_open(
        request: urllib.request.Request,
        timeout: int = 60,
        *,
        follow_redirects: bool = True,
    ) -> FakeResponse:
        del timeout, follow_redirects
        calls.append(request)
        if request.full_url == metadata_url:
            return FakeResponse(metadata_payload)
        if request.full_url == workflow_url:
            return FakeResponse(workflow_payload)
        if request.full_url == jobs_url:
            return FakeResponse(jobs_payload)
        if request.full_url == archive_url:
            headers = {} if redirect_location is None else {"Location": redirect_location}
            return FakeResponse(b"", status=302, headers=headers)
        if request.full_url == HANDOFF_STORAGE_URL:
            return FakeResponse(handoff_archive if storage_archive is None else storage_archive)
        raise urllib.error.URLError(f"unexpected synthetic URL: {request.full_url}")

    monkeypatch.setattr(transport, "_open_url", fake_open)
    return calls


def _verify_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    capture_archive: bytes,
    handoff_archive: bytes | None = None,
    metadata: dict[str, Any] | None = None,
    storage_archive: bytes | None = None,
    workflow: dict[str, Any] | None = None,
    jobs: list[dict[str, Any]] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[transport.VerifiedHandoffResult, list[urllib.request.Request]]:
    archive = handoff_archive or _handoff_archive(capture_archive)
    calls = _install_handoff_http(
        monkeypatch,
        handoff_archive=archive,
        metadata=metadata,
        workflow=workflow,
        jobs=jobs,
        storage_archive=storage_archive,
    )
    result = verify_handoff_download(
        repository=REPOSITORY,
        handoff_artifact_id=HANDOFF_ID,
        expected_handoff_artifact_digest=(
            metadata["digest"]
            if metadata is not None
            else f"sha256:{hashlib.sha256(archive).hexdigest()}"
        ),
        expected_transport_run_id=TRANSPORT_RUN_ID,
        expected_transport_run_attempt=TRANSPORT_RUN_ATTEMPT,
        expected_transport_head_sha=TRANSPORT_HEAD_SHA,
        expected_capture_artifact_id=ARTIFACT_ID,
        expected_capture_artifact_digest=f"sha256:{hashlib.sha256(capture_archive).hexdigest()}",
        expected_capture_run_id=RUN_ID,
        expected_capture_run_attempt=RUN_ATTEMPT,
        expected_capture_head_sha=HEAD_SHA,
        output_dir=tmp_path / "handoff-output",
        execute_download=True,
        env=env
        or {
            "GITHUB_TOKEN": SECRET_TOKEN,
            transport.HANDOFF_DOWNLOAD_AUTHORIZATION_ENV: "YES",
        },
        api_base_url=API_BASE_URL,
    )
    return result, calls


def test_handoff_guard_uses_independent_authorization_and_makes_zero_http_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture_archive = _zip_bytes()
    handoff_archive = _handoff_archive(capture_archive)
    calls = _install_handoff_http(monkeypatch, handoff_archive=handoff_archive)
    kwargs: dict[str, Any] = {
        "repository": REPOSITORY,
        "handoff_artifact_id": HANDOFF_ID,
        "expected_handoff_artifact_digest": f"sha256:{hashlib.sha256(handoff_archive).hexdigest()}",
        "expected_transport_run_id": TRANSPORT_RUN_ID,
        "expected_transport_run_attempt": TRANSPORT_RUN_ATTEMPT,
        "expected_transport_head_sha": TRANSPORT_HEAD_SHA,
        "expected_capture_artifact_id": ARTIFACT_ID,
        "expected_capture_artifact_digest": f"sha256:{hashlib.sha256(capture_archive).hexdigest()}",
        "expected_capture_run_id": RUN_ID,
        "expected_capture_run_attempt": RUN_ATTEMPT,
        "expected_capture_head_sha": HEAD_SHA,
        "output_dir": tmp_path / "guard-output",
        "api_base_url": API_BASE_URL,
    }
    with pytest.raises(ArtifactTransportError, match="HANDOFF_DOWNLOAD_EXECUTION_NOT_EXPLICIT"):
        verify_handoff_download(
            **kwargs,
            env={transport.HANDOFF_DOWNLOAD_AUTHORIZATION_ENV: "YES"},
        )
    with pytest.raises(ArtifactTransportError, match="HANDOFF_DOWNLOAD_EXECUTION_NOT_AUTHORIZED"):
        verify_handoff_download(
            **kwargs,
            execute_download=True,
            env={"GITHUB_TOKEN": SECRET_TOKEN, "TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED": "YES"},
        )
    assert calls == []


def test_handoff_happy_path_verifies_d1_d0_and_exposes_assembly_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture_archive = _zip_bytes()
    result, calls = _verify_handoff(tmp_path, monkeypatch, capture_archive=capture_archive)
    assert [request.full_url for request in calls] == [
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{HANDOFF_ID}",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{TRANSPORT_RUN_ID}",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{TRANSPORT_RUN_ID}/jobs?per_page=100",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{HANDOFF_ID}/zip",
        HANDOFF_STORAGE_URL,
    ]
    assert all(calls[index].get_header("Authorization") for index in range(4))
    assert calls[4].get_header("Authorization") is None
    assert calls[4].get_header("Cookie") is None
    assert calls[4].get_header("X-github-api-version") is None
    assert result.capture_root.is_dir()
    assert result.observation_bundle.is_file()
    assert result.receipt_path.is_file()
    receipt_text = result.receipt_path.read_text(encoding="utf-8")
    assert "verified_handoff_status" in receipt_text
    assert SECRET_TOKEN not in receipt_text


@pytest.mark.parametrize(
    "workflow_override",
    [
        {"event": "push"},
        {"path": ".github/workflows/other.yml"},
        {"name": "other"},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"head_sha": "d" * 40},
        {"run_attempt": 2},
    ],
)
def test_handoff_transport_workflow_identity_and_success_are_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workflow_override: dict[str, Any],
) -> None:
    with pytest.raises(ArtifactTransportError, match="HANDOFF_WORKFLOW_BINDING_MISMATCH"):
        _verify_handoff(
            tmp_path / "workflow",
            monkeypatch,
            capture_archive=_zip_bytes(),
            workflow={
                "id": int(TRANSPORT_RUN_ID),
                "run_attempt": int(TRANSPORT_RUN_ATTEMPT),
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "workflow_dispatch",
                "head_sha": TRANSPORT_HEAD_SHA,
                "head_branch": "main",
                "status": "completed",
                "conclusion": "success",
                **workflow_override,
            },
        )


def test_handoff_transport_job_must_be_the_canonical_successful_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ArtifactTransportError, match="HANDOFF_TRANSPORT_JOB_INVALID"):
        _verify_handoff(
            tmp_path,
            monkeypatch,
            capture_archive=_zip_bytes(),
            jobs=[
                {
                    "id": 4567,
                    "name": "live-evidence-artifact-transport-verify",
                    "status": "completed",
                    "conclusion": "failure",
                }
            ],
        )


@pytest.mark.parametrize(
    "extra_entries",
    [
        [("unexpected.txt", b"extra")],
        [("../escape.txt", b"escape")],
        [("/absolute.txt", b"absolute")],
        [("..\\escape.txt", b"escape")],
    ],
)
def test_handoff_payload_exact_shape_and_safe_extraction_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra_entries: list[tuple[str, bytes]],
) -> None:
    capture_archive = _zip_bytes()
    handoff_archive = _handoff_archive(capture_archive, extra_entries=extra_entries)
    with pytest.raises(ArtifactTransportError):
        _verify_handoff(
            tmp_path,
            monkeypatch,
            capture_archive=capture_archive,
            handoff_archive=handoff_archive,
        )
    assert not (tmp_path / "handoff-output" / transport.VERIFIED_HANDOFF_RECEIPT_NAME).exists()


def test_handoff_embedded_capture_digest_mismatch_is_rejected_before_exposure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture_archive = _zip_bytes()
    changed_capture = capture_archive + b"tampered"
    handoff_archive = _handoff_archive(
        changed_capture,
        receipt=_d0_receipt(capture_archive),
    )
    metadata = _handoff_metadata(handoff_archive)
    with pytest.raises(ArtifactTransportError, match="HANDOFF_EMBEDDED_CAPTURE_DIGEST_MISMATCH"):
        _verify_handoff(
            tmp_path,
            monkeypatch,
            capture_archive=capture_archive,
            handoff_archive=handoff_archive,
            metadata=metadata,
        )
    output = tmp_path / "handoff-output"
    assert not (output / transport.VERIFIED_HANDOFF_RECEIPT_NAME).exists()
    assert not (output / transport.HANDOFF_CAPTURE_DIRECTORY_NAME).exists()


ATTESTATION_ARTIFACT_ID = "9100"
ATTESTATION_RUN_ID = "9200"
ATTESTATION_RUN_ATTEMPT = "1"
ATTESTATION_HEAD_SHA = "d" * 40
ATTESTATION_STORAGE_URL = "https://artifact-storage.example/task012/attestation.zip?sig=synthetic"


def _attestation_archive(*, extra_entry: bool = False) -> bytes:
    payload = build_attestation("sha256:" + "1" * 64, "sha256:" + "2" * 64)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("attestation.json", json.dumps(payload, separators=(",", ":")))
        if extra_entry:
            archive.writestr("unexpected.txt", b"unexpected")
    return output.getvalue()


def _install_attestation_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    archive: bytes,
    workflow_override: dict[str, Any] | None = None,
    jobs: list[dict[str, Any]] | None = None,
    redirect_location: str | None = ATTESTATION_STORAGE_URL,
    second_redirect: bool = False,
) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []
    digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    metadata_url = f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ATTESTATION_ARTIFACT_ID}"
    workflow_url = f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{ATTESTATION_RUN_ID}"
    jobs_url = f"{workflow_url}/jobs?per_page=100"
    archive_url = f"{metadata_url}/zip"
    metadata = {
        "id": int(ATTESTATION_ARTIFACT_ID),
        "name": f"task012-live-attestation-{ATTESTATION_RUN_ID}-{ATTESTATION_RUN_ATTEMPT}",
        "expired": False,
        "digest": digest,
        "archive_download_url": archive_url,
        "workflow_run": {
            "id": int(ATTESTATION_RUN_ID),
            "run_attempt": int(ATTESTATION_RUN_ATTEMPT),
            "head_sha": ATTESTATION_HEAD_SHA,
            "head_branch": "main",
        },
    }
    workflow = {
        "id": int(ATTESTATION_RUN_ID),
        "run_attempt": int(ATTESTATION_RUN_ATTEMPT),
        "name": "ci",
        "path": ".github/workflows/ci.yml",
        "event": "workflow_dispatch",
        "head_sha": ATTESTATION_HEAD_SHA,
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "workflow_id": 123,
    }
    if workflow_override:
        workflow.update(workflow_override)
    job_list = (
        [
            {
                "id": 456,
                "name": "live-evidence-attestation-create",
                "status": "completed",
                "conclusion": "success",
            }
        ]
        if jobs is None
        else jobs
    )

    def fake_open(
        request: urllib.request.Request,
        timeout: int = 60,
        *,
        follow_redirects: bool = True,
    ) -> FakeResponse:
        del timeout, follow_redirects
        calls.append(request)
        if request.full_url == metadata_url:
            return FakeResponse(json.dumps(metadata).encode("utf-8"))
        if request.full_url == workflow_url:
            return FakeResponse(json.dumps(workflow).encode("utf-8"))
        if request.full_url == jobs_url:
            return FakeResponse(json.dumps({"jobs": job_list}).encode("utf-8"))
        if request.full_url == archive_url:
            headers = {} if redirect_location is None else {"Location": redirect_location}
            return FakeResponse(b"", status=302, headers=headers)
        if request.full_url == ATTESTATION_STORAGE_URL:
            if second_redirect:
                return FakeResponse(b"", status=302, headers={"Location": ATTESTATION_STORAGE_URL})
            return FakeResponse(archive)
        raise urllib.error.URLError(f"unexpected synthetic URL: {request.full_url}")

    monkeypatch.setattr(transport, "_open_url", fake_open)
    return calls


def _verify_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    archive: bytes,
    **kwargs: Any,
) -> tuple[Path, list[urllib.request.Request]]:
    digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    calls = _install_attestation_http(
        monkeypatch,
        archive=archive,
        workflow_override=kwargs.pop("workflow_override", None),
        jobs=kwargs.pop("jobs", None),
        redirect_location=kwargs.pop("redirect_location", ATTESTATION_STORAGE_URL),
        second_redirect=kwargs.pop("second_redirect", False),
    )
    result = verify_attestation_download(
        repository=REPOSITORY,
        artifact_id=ATTESTATION_ARTIFACT_ID,
        expected_artifact_digest=kwargs.pop("expected_digest", digest),
        expected_creation_run_id=ATTESTATION_RUN_ID,
        expected_creation_run_attempt=ATTESTATION_RUN_ATTEMPT,
        expected_creation_head_sha=ATTESTATION_HEAD_SHA,
        output_dir=tmp_path / "attestation-output",
        execute_download=True,
        env={
            "GITHUB_TOKEN": SECRET_TOKEN,
            "TASK012_ATTESTATION_DOWNLOAD_AUTHORIZED": "YES",
        },
        api_base_url=API_BASE_URL,
    )
    return result.receipt_path, calls


def test_attestation_transport_happy_path_binds_job_and_strips_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _attestation_archive()
    receipt, calls = _verify_attestation(tmp_path, monkeypatch, archive=archive)
    assert [request.full_url for request in calls] == [
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ATTESTATION_ARTIFACT_ID}",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{ATTESTATION_RUN_ID}",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/runs/{ATTESTATION_RUN_ID}/jobs?per_page=100",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ATTESTATION_ARTIFACT_ID}/zip",
        ATTESTATION_STORAGE_URL,
    ]
    assert all(
        request.get_header("Authorization") == f"Bearer {SECRET_TOKEN}" for request in calls[:4]
    )
    assert calls[-1].get_header("Authorization") is None
    assert calls[-1].get_header("Cookie") is None
    assert calls[-1].get_header("X-github-api-version") is None
    output = receipt.parent
    assert (output / "verified-artifact.zip").read_bytes() == archive
    assert (output / "extracted" / "attestation.json").is_file()
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt_value["transport_verification_status"] == "PASS"
    assert receipt_value["job_name"] == "live-evidence-attestation-create"
    assert SECRET_TOKEN not in receipt.read_text(encoding="utf-8")


def test_attestation_transport_requires_both_execution_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _install_attestation_http(monkeypatch, archive=_attestation_archive())
    common = {
        "repository": REPOSITORY,
        "artifact_id": ATTESTATION_ARTIFACT_ID,
        "expected_artifact_digest": "a" * 64,
        "expected_creation_run_id": ATTESTATION_RUN_ID,
        "expected_creation_run_attempt": ATTESTATION_RUN_ATTEMPT,
        "expected_creation_head_sha": ATTESTATION_HEAD_SHA,
        "output_dir": tmp_path / "guard-output",
    }
    with pytest.raises(ArtifactTransportError, match="ATTESTATION_DOWNLOAD_EXECUTION_NOT_EXPLICIT"):
        verify_attestation_download(
            **common, env={"TASK012_ATTESTATION_DOWNLOAD_AUTHORIZED": "YES"}
        )
    with pytest.raises(
        ArtifactTransportError, match="ATTESTATION_DOWNLOAD_EXECUTION_NOT_AUTHORIZED"
    ):
        verify_attestation_download(**common, execute_download=True, env={})
    assert calls == []


@pytest.mark.parametrize(
    ("workflow_override", "jobs", "error"),
    [
        ({"event": "push"}, None, "ATTESTATION_WORKFLOW_BINDING_MISMATCH"),
        ({"path": ".github/workflows/other.yml"}, None, "ATTESTATION_WORKFLOW_BINDING_MISMATCH"),
        (None, [], "ATTESTATION_JOB_BINDING_MISMATCH"),
        (
            None,
            [
                {
                    "id": 1,
                    "name": "live-evidence-attestation-create",
                    "status": "completed",
                    "conclusion": "failure",
                }
            ],
            "ATTESTATION_JOB_BINDING_MISMATCH",
        ),
    ],
)
def test_attestation_workflow_and_job_authority_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workflow_override: dict[str, Any] | None,
    jobs: list[dict[str, Any]] | None,
    error: str,
) -> None:
    with pytest.raises(ArtifactTransportError, match=error):
        _verify_attestation(
            tmp_path,
            monkeypatch,
            archive=_attestation_archive(),
            workflow_override=workflow_override,
            jobs=jobs,
        )


def test_attestation_package_extra_file_and_second_redirect_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ArtifactTransportError, match="ATTESTATION_PACKAGE_MISMATCH"):
        _verify_attestation(
            tmp_path / "extra", monkeypatch, archive=_attestation_archive(extra_entry=True)
        )
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_REDIRECT_CHAIN_REJECTED"):
        _verify_attestation(
            tmp_path / "redirect",
            monkeypatch,
            archive=_attestation_archive(),
            second_redirect=True,
        )
    assert not (tmp_path / "extra" / "attestation-output" / "verified-artifact.zip").exists()
    assert not (
        tmp_path / "redirect" / "attestation-output" / "attestation-transport-receipt.json"
    ).exists()
