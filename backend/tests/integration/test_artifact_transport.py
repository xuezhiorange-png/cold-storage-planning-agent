from __future__ import annotations

import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pytest

import cold_storage.release.artifact_transport as transport
from cold_storage.release.artifact_transport import ArtifactTransportError, verify_download
from cold_storage.release.live_evidence_runner import _verify_capture_checksums, _write_checksums

REPOSITORY = "xuezhiorange-png/cold-storage-planning-agent"
ARTIFACT_ID = "2345"
RUN_ID = "900"
RUN_ATTEMPT = "1"
HEAD_SHA = "b" * 40
API_BASE_URL = "https://api.github.test"
STORAGE_URL = "https://artifact-storage.example/task012/signed-archive.zip?sig=synthetic"
RC_SOURCE_SHA = "043731fea4e60feb6b929c524c4b68e87ed67bd7"
RC_SOURCE_TREE = "b456e77f07a0cef801c57d2f089a318c35c145c4"


class _Response:
    def __init__(
        self, payload: bytes, status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._stream = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def getcode(self) -> int:
        return self.status

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name, default)

    def close(self) -> None:
        return None


def _capture_package(tmp_path: Path) -> tuple[Path, bytes]:
    root = tmp_path / "capture-package"
    (root / "build-a").mkdir(parents=True)
    (root / "build-b").mkdir(parents=True)
    (root / "observation-bundle.json").write_text('{"schema_version":"test"}\n', encoding="utf-8")
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "task": "TASK-012",
                "version": "V0.2",
                "slice": 2,
                "capture_workflow_run_id": RUN_ID,
                "capture_workflow_run_attempt": RUN_ATTEMPT,
                "evidence_tool_head": HEAD_SHA,
                "rc_source_sha": RC_SOURCE_SHA,
                "rc_source_tree": RC_SOURCE_TREE,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "expected-inputs.json").write_text('{"synthetic":true}\n', encoding="utf-8")
    (root / "build-a" / "observed-inputs.json").write_text('{"run":"a"}\n', encoding="utf-8")
    (root / "build-b" / "observed-inputs.json").write_text('{"run":"b"}\n', encoding="utf-8")
    _write_checksums(root)
    archive_path = tmp_path / "capture.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    return root, archive_path.read_bytes()


def _metadata(archive: bytes, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": int(ARTIFACT_ID),
        "name": f"task012-live-evidence-{RUN_ID}-{RUN_ATTEMPT}",
        "expired": False,
        "digest": f"sha256:{hashlib.sha256(archive).hexdigest()}",
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
    metadata: dict[str, Any],
    workflow: dict[str, Any] | None = None,
) -> list[urllib.request.Request]:
    calls: list[urllib.request.Request] = []
    metadata_bytes = json.dumps(metadata).encode("utf-8")
    workflow_bytes = json.dumps(
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
    ) -> _Response:
        del timeout, follow_redirects
        calls.append(request)
        if request.full_url == metadata_url:
            return _Response(metadata_bytes)
        if request.full_url == workflow_url:
            return _Response(workflow_bytes)
        if request.full_url == archive_url:
            return _Response(b"", status=302, headers={"Location": STORAGE_URL})
        if request.full_url == STORAGE_URL:
            return _Response(archive)
        raise AssertionError(f"unexpected synthetic URL: {request.full_url}")

    monkeypatch.setattr(transport, "_open_url", fake_open)
    return calls


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    archive: bytes,
    metadata: dict[str, Any],
    expected_digest: str | None = None,
    artifact_id: str = ARTIFACT_ID,
    workflow: dict[str, Any] | None = None,
) -> tuple[Path, list[urllib.request.Request]]:
    calls = _install_http(monkeypatch, archive=archive, metadata=metadata, workflow=workflow)
    digest = expected_digest or f"sha256:{hashlib.sha256(archive).hexdigest()}"
    receipt = verify_download(
        repository=REPOSITORY,
        artifact_id=artifact_id,
        expected_artifact_digest=digest,
        expected_capture_run_id=RUN_ID,
        expected_capture_run_attempt=RUN_ATTEMPT,
        expected_capture_head_sha=HEAD_SHA,
        output_dir=tmp_path / "transport-output",
        execute_download=True,
        env={"GITHUB_TOKEN": "synthetic-token", "TASK012_ARTIFACT_DOWNLOAD_AUTHORIZED": "YES"},
        api_base_url=API_BASE_URL,
    )
    return receipt, calls


def test_exact_handoff_verifies_transport_and_internal_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, archive = _capture_package(tmp_path)
    metadata = _metadata(archive)
    receipt, calls = _run(tmp_path, monkeypatch, archive=archive, metadata=metadata)
    assert len(calls) == 4
    assert calls[2].get_header("Authorization") is not None
    assert calls[3].get_header("Authorization") is None
    assert calls[3].full_url == STORAGE_URL
    extracted = receipt.parent / "extracted"
    _verify_capture_checksums(extracted)
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt_value["recorded_artifact_digest"] == metadata["digest"]
    assert receipt_value["downloaded_archive_digest"] == metadata["digest"]
    assert (extracted / "observation-bundle.json").is_file()


def test_external_workflow_run_and_package_origin_are_cross_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, archive = _capture_package(tmp_path)
    metadata = _metadata(archive)
    receipt, _ = _run(tmp_path / "origin", monkeypatch, archive=archive, metadata=metadata)
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    assert receipt_value["workflow_run_id"] == int(RUN_ID)
    assert receipt_value["workflow_run_attempt"] == int(RUN_ATTEMPT)
    assert receipt_value["workflow_name"] == "ci"
    assert receipt_value["workflow_path"] == ".github/workflows/ci.yml"
    assert receipt_value["workflow_event"] == "workflow_dispatch"
    assert receipt_value["package_capture_workflow_run_id"] == RUN_ID
    assert receipt_value["package_capture_workflow_run_attempt"] == RUN_ATTEMPT
    assert receipt_value["package_rc_source_sha"] == RC_SOURCE_SHA
    assert receipt_value["package_rc_source_tree"] == RC_SOURCE_TREE


def test_metadata_claims_correct_digest_but_downloaded_bytes_differ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, archive = _capture_package(tmp_path)
    changed = archive + b"different archive bytes"
    metadata = _metadata(archive)
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_TRANSPORT_DIGEST_MISMATCH"):
        _run(
            tmp_path / "changed",
            monkeypatch,
            archive=changed,
            metadata=metadata,
            expected_digest=metadata["digest"],
        )


def test_recorded_digest_must_match_metadata_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, archive = _capture_package(tmp_path)
    metadata = _metadata(archive)
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_METADATA_DIGEST_MISMATCH"):
        _run(
            tmp_path / "recorded-drift",
            monkeypatch,
            archive=archive,
            metadata=metadata,
            expected_digest="sha256:" + "c" * 64,
        )


def test_exact_artifact_id_and_capture_identity_are_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, archive = _capture_package(tmp_path)
    metadata = _metadata(archive)
    with pytest.raises(ArtifactTransportError, match="ARTIFACT_METADATA_ID_MISMATCH"):
        _run(tmp_path / "id-drift", monkeypatch, archive=archive, metadata={**metadata, "id": 999})

    with pytest.raises(ArtifactTransportError, match="ARTIFACT_WORKFLOW_BINDING_MISMATCH"):
        _run(
            tmp_path / "head-drift",
            monkeypatch,
            archive=archive,
            metadata=_metadata(archive, workflow_run={"head_sha": "c" * 40}),
        )

    with pytest.raises(ArtifactTransportError, match="ARTIFACT_WORKFLOW_BINDING_MISMATCH"):
        _run(
            tmp_path / "event-drift",
            monkeypatch,
            archive=archive,
            metadata=metadata,
            workflow={
                "id": int(RUN_ID),
                "run_attempt": int(RUN_ATTEMPT),
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "push",
                "head_sha": HEAD_SHA,
                "head_branch": "main",
                "status": "completed",
                "conclusion": "success",
            },
        )
