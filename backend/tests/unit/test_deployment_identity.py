"""Unit tests for bootstrap.deployment_identity per TASK-012 Slice 2."""

from __future__ import annotations

import json

import pytest

from cold_storage.bootstrap.deployment_identity import (
    BuildCommitMismatch,
    BuildIdentityCommitInvalid,
    BuildIdentityFileMalformed,
    BuildIdentityFileMissing,
    BuildIdentitySchemaUnsupported,
    BuildIdentityVersionInvalid,
    BuildVersionMismatch,
    DeploymentIdInvalid,
    is_safe_build_version,
    is_safe_commit_sha,
    is_safe_deployment_id,
    load_runtime_identity,
    read_in_image_identity,
)


def _write_identity(tmp_path, *, payload, mode=0o644):
    target = tmp_path / "build-identity.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    target.chmod(mode)
    return target


def test_is_safe_build_version_min_boundary_1_char():
    assert is_safe_build_version("v") is True


def test_is_safe_build_version_max_boundary_64_char():
    assert is_safe_build_version("a" + "b" * 63) is True


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty
        ".1.0",  # leading punctuation: period
        "_v1",  # leading punctuation: underscore
        "-v1",  # leading punctuation: hyphen
        "+v1",  # leading punctuation: plus
        "v1.0 ",  # trailing whitespace
        "v 1.0",  # embedded whitespace
        "v1.0/0",  # forward slash
        "v1\\0",  # backslash
        "v1.0\n",  # control newline
        "v1.0\t",  # tab
        "a" * 65,  # over-length
        "v1\u00e9",  # non-ASCII letter
        "v1\u4e2d",  # CJK
        "v\0",  # NUL
    ],
)
def test_is_safe_build_version_rejects_invalid_inputs(value):
    assert is_safe_build_version(value) is False


def test_is_safe_commit_sha_accepts_lowercase_40_hex():
    assert is_safe_commit_sha("a" * 40) is True
    assert is_safe_commit_sha("0123456789abcdef0123456789abcdef01234567") is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",
        "A" * 40,  # uppercase not allowed
        "0" * 39,  # too short
        "0" * 41,  # too long
        "g" * 40,  # g is not hex
    ],
)
def test_is_safe_commit_sha_rejects_invalid_inputs(value):
    assert is_safe_commit_sha(value) is False


def test_is_safe_deployment_id_basic():
    assert is_safe_deployment_id("dep-001") is True
    assert is_safe_deployment_id("abc") is True
    assert is_safe_deployment_id("a" * 128) is True
    assert is_safe_deployment_id("") is False
    assert is_safe_deployment_id("a" * 129) is False
    assert is_safe_deployment_id("/etc/passwd") is False


def test_read_in_image_identity_valid(tmp_path):
    path = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "a" * 40,
            "version": "v1.0.0",
        },
        mode=0o444,
    )
    rec = read_in_image_identity(path=path)
    assert rec.schema_version == 1
    assert rec.commit_sha == "a" * 40
    assert rec.version == "v1.0.0"


def test_read_in_image_identity_missing(tmp_path):
    missing = tmp_path / "absent.json"
    with pytest.raises(BuildIdentityFileMissing) as exc_info:
        read_in_image_identity(path=missing)
    assert exc_info.value.failure_code == "BUILD_IDENTITY_FILE_MISSING"


def test_read_in_image_identity_malformed_json(tmp_path):
    target = tmp_path / "build-identity.json"
    target.write_text("{not json", encoding="utf-8")
    target.chmod(0o644)
    with pytest.raises(BuildIdentityFileMalformed) as exc_info:
        read_in_image_identity(path=target)
    assert exc_info.value.failure_code == "BUILD_IDENTITY_FILE_MALFORMED"


def test_read_in_image_identity_wrong_keys(tmp_path):
    target = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "git_sha": "a" * 40,  # wrong key
            "version": "v1.0.0",
        },
    )
    with pytest.raises(BuildIdentityFileMalformed) as exc_info:
        read_in_image_identity(path=target)
    assert exc_info.value.failure_code == "BUILD_IDENTITY_FILE_MALFORMED"


def test_read_in_image_identity_extra_keys(tmp_path):
    target = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "a" * 40,
            "version": "v1.0.0",
            "extra": "nope",
        },
    )
    with pytest.raises(BuildIdentityFileMalformed) as exc_info:
        read_in_image_identity(path=target)
    assert exc_info.value.failure_code == "BUILD_IDENTITY_FILE_MALFORMED"


def test_read_in_image_identity_unsupported_schema(tmp_path):
    target = _write_identity(
        tmp_path,
        payload={
            "schema_version": 99,
            "commit_sha": "a" * 40,
            "version": "v1.0.0",
        },
    )
    with pytest.raises(BuildIdentitySchemaUnsupported) as exc_info:
        read_in_image_identity(path=target)
    assert exc_info.value.failure_code == "BUILD_IDENTITY_SCHEMA_UNSUPPORTED"


def test_read_in_image_identity_bad_commit_sha(tmp_path):
    target = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "UPPERCASE" + "a" * 32,
            "version": "v1.0.0",
        },
    )
    with pytest.raises(BuildIdentityCommitInvalid) as exc_info:
        read_in_image_identity(path=target)
    assert exc_info.value.failure_code == "BUILD_IDENTITY_COMMIT_INVALID"


def test_read_in_image_identity_bad_version(tmp_path):
    target = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "a" * 40,
            "version": "v1.0/0",
        },
    )
    with pytest.raises(BuildIdentityVersionInvalid) as exc_info:
        read_in_image_identity(path=target)
    assert exc_info.value.failure_code == "BUILD_IDENTITY_VERSION_INVALID"


def test_load_runtime_identity_happy(tmp_path):
    path = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "0a1b2c" + "0" * 34,
            "version": "v1.2.3",
        },
    )
    env = {
        "COLD_STORAGE_BUILD_COMMIT_SHA": "0a1b2c" + "0" * 34,
        "COLD_STORAGE_BUILD_VERSION": "v1.2.3",
        "COLD_STORAGE_DEPLOYMENT_ID": "dep-001",
    }
    rec, dep_id = load_runtime_identity(env=env, path=path)
    assert rec.commit_sha == "0a1b2c" + "0" * 34
    assert rec.version == "v1.2.3"
    assert dep_id == "dep-001"


def test_load_runtime_identity_commit_mismatch(tmp_path):
    path = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "a" * 40,
            "version": "v1.0.0",
        },
    )
    env = {
        "COLD_STORAGE_BUILD_COMMIT_SHA": "b" * 40,
        "COLD_STORAGE_BUILD_VERSION": "v1.0.0",
        "COLD_STORAGE_DEPLOYMENT_ID": "dep-001",
    }
    with pytest.raises(BuildCommitMismatch) as exc_info:
        load_runtime_identity(env=env, path=path)
    assert exc_info.value.failure_code == "BUILD_COMMIT_MISMATCH"


def test_load_runtime_identity_version_mismatch(tmp_path):
    path = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "a" * 40,
            "version": "v1.0.0",
        },
    )
    env = {
        "COLD_STORAGE_BUILD_COMMIT_SHA": "a" * 40,
        "COLD_STORAGE_BUILD_VERSION": "v2.0.0",
        "COLD_STORAGE_DEPLOYMENT_ID": "dep-001",
    }
    with pytest.raises(BuildVersionMismatch) as exc_info:
        load_runtime_identity(env=env, path=path)
    assert exc_info.value.failure_code == "BUILD_VERSION_MISMATCH"


def test_load_runtime_identity_bad_deployment_id(tmp_path):
    path = _write_identity(
        tmp_path,
        payload={
            "schema_version": 1,
            "commit_sha": "a" * 40,
            "version": "v1.0.0",
        },
    )
    env = {
        "COLD_STORAGE_BUILD_COMMIT_SHA": "a" * 40,
        "COLD_STORAGE_BUILD_VERSION": "v1.0.0",
        "COLD_STORAGE_DEPLOYMENT_ID": "/etc/passwd",
    }
    with pytest.raises(DeploymentIdInvalid) as exc_info:
        load_runtime_identity(env=env, path=path)
    assert exc_info.value.failure_code == "DEPLOYMENT_ID_INVALID"
