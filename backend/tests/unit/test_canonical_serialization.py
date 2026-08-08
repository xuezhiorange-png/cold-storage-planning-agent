"""Canonical serialization unit tests (S2_GAP_03 / Section 8.2)."""

from __future__ import annotations

import json

import pytest

from cold_storage.release.canonical_serialization import (
    CanonicalSerializationError,
    canonical_bytes,
    canonical_digest,
    canonical_dumps,
    load_json_strict,
    reject_absolute_paths,
    reject_secret_values,
    sha256_hex,
    to_digest_str,
)

DIGEST = "sha256:" + "a" * 64


def test_canonical_dumps_is_ascii_compact_with_single_newline() -> None:
    from collections import OrderedDict

    obj = OrderedDict([("b", 1), ("a", "x")])
    text = canonical_dumps(obj)
    assert text.endswith("\n")
    assert text.count("\n") == 1
    assert json.loads(text) == {"b": 1, "a": "x"}
    assert " " not in text.replace("\n", "")  # compact separators


def test_canonical_dumps_is_ascii_safe() -> None:
    from collections import OrderedDict

    obj = OrderedDict([("name", "café")])
    text = canonical_dumps(obj)
    assert "café" not in text  # non-ascii escaped
    assert "\\u00e9" in text


def test_load_json_rejects_duplicate_keys() -> None:
    raw = '{"a": 1, "a": 2}'
    with pytest.raises(CanonicalSerializationError) as exc:
        load_json_strict(raw)
    assert exc.value.failure_code == "DUPLICATE_JSON_KEY"


def test_load_json_rejects_non_object_root() -> None:
    with pytest.raises(CanonicalSerializationError):
        load_json_strict("[1, 2, 3]")


def test_load_json_rejects_malformed() -> None:
    with pytest.raises(CanonicalSerializationError) as exc:
        load_json_strict("{not json}")
    assert exc.value.failure_code == "MALFORMED_JSON"


def test_canonical_digest_is_sha256_with_prefix() -> None:
    from collections import OrderedDict

    obj = OrderedDict([("k", "v")])
    digest = canonical_digest(obj)
    expected = to_digest_str(sha256_hex(canonical_bytes(obj)))
    assert digest == expected
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_canonical_digest_is_deterministic() -> None:
    from collections import OrderedDict

    obj = OrderedDict([("schema_version", "v1"), ("rc_version", "v0.2.0")])
    assert canonical_digest(obj) == canonical_digest(obj)


def test_reject_absolute_paths_rejects_leading_slash() -> None:
    with pytest.raises(CanonicalSerializationError) as exc:
        reject_absolute_paths([{"relative_path": "/etc/passwd", "size_bytes": 1, "sha256": "x"}])
    assert exc.value.failure_code == "ABSOLUTE_PATH_REJECTED"


def test_reject_absolute_paths_allows_relative() -> None:
    reject_absolute_paths([{"relative_path": "backend/Dockerfile", "size_bytes": 1, "sha256": "x"}])


def test_reject_secret_values_rejects_password_key() -> None:
    with pytest.raises(CanonicalSerializationError) as exc:
        reject_secret_values({"password": "hunter2"})
    assert exc.value.failure_code == "SECRET_VALUE_DETECTED"


def test_reject_secret_values_rejects_embedded_dsn() -> None:
    with pytest.raises(CanonicalSerializationError) as exc:
        reject_secret_values({"db": "postgresql://user:secret@host/db"})
    assert exc.value.failure_code == "SECRET_VALUE_DETECTED"


def test_reject_secret_values_allows_clean_values() -> None:
    reject_secret_values({"final_image_digest": DIGEST, "source_commit_sha": "0" * 40})


def test_to_digest_str_format() -> None:
    assert to_digest_str("abc") == "sha256:abc"
