from __future__ import annotations

import hashlib
import io
import json
import stat
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pytest

import cold_storage.release.artifact_transport as transport
from cold_storage.release.artifact_transport import (
    ArtifactTransportError,
    normalize_artifact_digest,
    verify_download,
)

REPOSITORY = "xuezhiorange-png/cold-storage-planning-agent"
ARTIFACT_ID = "1234"
RUN_ID = "700"
RUN_ATTEMPT = "2"
HEAD_SHA = "a" * 40
API_BASE_URL = "https://api.github.test"


class FakeResponse:
    def __init__(
        self, payload: bytes, *, status: int = 200, fail_after_first_read: bool = False
    ) -> None:
        self.status = status
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

    def close(self) -> None:
        self.closed = True


def _zip_bytes(
    extra_entries: list[tuple[str, bytes]] | None = None,
    *,
    duplicate_entry: bool = False,
    symlink_entry: bool = False,
) -> bytes:
    entries = [
        ("observation-bundle.json", b"{}"),
        ("metadata.json", b"{}"),
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
    metadata_status: int = 200,
    archive_status: int = 200,
    partial_download: bool = False,
) -> list[str]:
    calls: list[str] = []
    metadata_payload = json.dumps(_metadata(archive) if metadata is None else metadata).encode(
        "utf-8"
    )

    def fake_urlopen(request: urllib.request.Request, timeout: int = 60) -> FakeResponse:
        del timeout
        calls.append(request.full_url)
        if request.full_url.endswith("/zip"):
            return FakeResponse(
                archive,
                status=archive_status,
                fail_after_first_read=partial_download,
            )
        return FakeResponse(metadata_payload, status=metadata_status)

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)
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
) -> tuple[Path, list[str]]:
    digest = expected_digest or f"sha256:{hashlib.sha256(archive).hexdigest()}"
    calls = _install_http(
        monkeypatch,
        archive=archive,
        metadata=metadata,
        metadata_status=metadata_status,
        archive_status=archive_status,
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
            "GITHUB_TOKEN": "test-token-that-must-not-be-written",
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
    assert len(calls) == 2
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
    assert calls == [
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}",
        f"{API_BASE_URL}/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}/zip",
    ]
    assert (output / "verified-artifact.zip").read_bytes() == archive
    assert (output / "extracted" / "observation-bundle.json").is_file()
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt_value["transport_verification_status"] == "PASS"
    assert receipt_value["recorded_artifact_digest"] == receipt_value["metadata_artifact_digest"]
    assert receipt_value["metadata_artifact_digest"] == receipt_value["downloaded_archive_digest"]
    assert "test-token-that-must-not-be-written" not in receipt.read_text(encoding="utf-8")
