"""Manifest loader integration tests (TASK-011C V1).

These tests assert the **integration behavior** of
``load_and_validate_manifest`` end-to-end: file read, JSON parse,
JSON Schema validation, pydantic model validation, and SHA
derivation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cold_storage.evaluation.manifest import (
    compute_manifest_sha,
    load_and_validate_manifest,
)


def _write_manifest(
    tmp_path: Path,
    body: dict,
    *,
    name: str = "manifest.json",
) -> Path:
    mf = tmp_path / name
    mf.write_text(json.dumps(body))
    return mf


def test_loader_returns_typed_manifest(tmp_path: Path) -> None:
    mf = _write_manifest(
        tmp_path,
        {
            "schema_version": "1.0",
            "suite_id": "t11c-v1",
            "scenarios": [
                {
                    "scenario_id": "baseline_feasible",
                    "database_backend": "sqlite",
                    "expected_outcome": "SUCCEEDED",
                }
            ],
        },
    )
    m = load_and_validate_manifest(mf)
    assert m.suite_id == "t11c-v1"
    assert m.schema_version == "1.0"
    assert len(m.scenarios) == 1


def test_loader_sha_is_deterministic(tmp_path: Path) -> None:
    body = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "s1",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
    }
    mf = _write_manifest(tmp_path, body)
    m1 = load_and_validate_manifest(mf)
    m2 = load_and_validate_manifest(mf)
    assert compute_manifest_sha(m1) == compute_manifest_sha(m2)


def test_loader_sha_is_independent_of_field_order(tmp_path: Path) -> None:
    """The canonicalizer sorts keys, so the SHA is order-independent."""
    a_body = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "s",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
    }
    b_body = {
        "scenarios": [
            {
                "expected_outcome": "SUCCEEDED",
                "database_backend": "sqlite",
                "scenario_id": "s",
            }
        ],
        "suite_id": "t",
        "schema_version": "1.0",
    }
    mf_a = _write_manifest(tmp_path, a_body, name="a.json")
    mf_b = _write_manifest(tmp_path, b_body, name="b.json")
    m_a = load_and_validate_manifest(mf_a)
    m_b = load_and_validate_manifest(mf_b)
    assert compute_manifest_sha(m_a) == compute_manifest_sha(m_b)


def test_loader_with_baseline_scenario(tmp_path: Path) -> None:
    """A minimal V1 manifest that includes the
    ``baseline_feasible`` scenario loads successfully."""
    mf = _write_manifest(
        tmp_path,
        {
            "schema_version": "1.0",
            "suite_id": "t11c-v1-baseline",
            "scenarios": [
                {
                    "scenario_id": "baseline_feasible",
                    "database_backend": "sqlite",
                    "expected_outcome": "SUCCEEDED",
                }
            ],
            "provenance": {
                "contract_authority_comment_id": 4959798219,
            },
            "excluded_paths": [],
        },
    )
    m = load_and_validate_manifest(mf)
    assert m.scenarios[0].scenario_id == "baseline_feasible"
    assert m.scenarios[0].database_backend.value == "sqlite"
    assert m.scenarios[0].expected_outcome.value == "SUCCEEDED"


def test_loader_rejects_file_with_no_extension(tmp_path: Path) -> None:
    """A file without a JSON extension still loads (the loader
    does not require ``.json``)."""
    mf = tmp_path / "manifest"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                    }
                ],
            }
        )
    )
    m = load_and_validate_manifest(mf)
    assert m.suite_id == "t"


def test_loader_computes_64_char_hex_sha(tmp_path: Path) -> None:
    mf = _write_manifest(
        tmp_path,
        {
            "schema_version": "1.0",
            "suite_id": "t",
            "scenarios": [
                {
                    "scenario_id": "s",
                    "database_backend": "sqlite",
                    "expected_outcome": "SUCCEEDED",
                }
            ],
        },
    )
    m = load_and_validate_manifest(mf)
    sha = compute_manifest_sha(m)
    assert len(sha) == 64
    int(sha, 16)  # must be valid hex


# ---------------------------------------------------------------------------
# P0-3 of review 4689835238 — relative manifest path fail-closed
# ---------------------------------------------------------------------------


def test_loader_rejects_relative_manifest_path(tmp_path: Path) -> None:
    """A relative manifest path is rejected before any file I/O.

    Per P0-3 of review 4689835238, the loader must NOT call
    ``Path.resolve()`` on a relative path (which would silently
    bind to cwd) and must instead fail closed with a typed
    :class:`ManifestError` (code ``MANIFEST_ERROR``).
    """
    from cold_storage.evaluation.manifest import ManifestError

    # The file does not exist anywhere — we want the rejection
    # to be based on the path kind, not on file presence.
    rel = Path("manifest.json")
    assert not rel.is_absolute()
    try:
        load_and_validate_manifest(rel)
    except ManifestError as exc:
        assert exc.code == "MANIFEST_ERROR", f"expected MANIFEST_ERROR, got {exc.code!r}"
        assert exc.details == {"manifest_path_kind": "relative"}, (
            f"unexpected details: {exc.details!r}"
        )
    else:
        raise AssertionError("expected ManifestError for relative manifest path")


def test_loader_relative_path_rejected_even_when_cwd_contains_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when a file with the relative name EXISTS in the
    current working directory, the loader must reject the
    relative path. This proves the rejection is based on the
    path kind, not on file presence in cwd.

    Per P0-3 of review 4689835238: the loader must be strictly
    cwd-independent; ``load_and_validate_manifest(Path("manifest.json"))``
    MUST fail even if cwd/manifest.json exists.
    """

    from cold_storage.evaluation.manifest import ManifestError

    # Create a real manifest.json in tmp_path and chdir there.
    manifest_body = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "s",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
    }
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    (cwd_dir / "manifest.json").write_text(json.dumps(manifest_body))
    monkeypatch.chdir(cwd_dir)
    # Sanity: the file exists in cwd.
    assert (cwd_dir / "manifest.json").exists()
    # But a relative path is still rejected.
    try:
        load_and_validate_manifest(Path("manifest.json"))
    except ManifestError as exc:
        assert exc.code == "MANIFEST_ERROR"
        assert exc.details == {"manifest_path_kind": "relative"}
    else:
        raise AssertionError(
            "expected ManifestError for relative path even when "
            "the file exists in cwd (loader must be cwd-independent)"
        )


def test_loader_relative_path_rejected_in_another_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second cwd change must produce the same rejection.

    Per P0-3 of review 4689835238: switching cwd must not
    change the loader's verdict for the same relative input.
    """

    from cold_storage.evaluation.manifest import ManifestError

    # Cwd 1: a directory with a manifest.json.
    cwd_a = tmp_path / "cwd_a"
    cwd_a.mkdir()
    (cwd_a / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "a",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                    }
                ],
            }
        )
    )
    monkeypatch.chdir(cwd_a)
    try:
        load_and_validate_manifest(Path("manifest.json"))
    except ManifestError as exc:
        verdict_a = (exc.code, exc.details)
    else:
        raise AssertionError("expected rejection in cwd_a")

    # Cwd 2: a different directory, also with a manifest.json.
    cwd_b = tmp_path / "cwd_b"
    cwd_b.mkdir()
    (cwd_b / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "b",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                    }
                ],
            }
        )
    )
    monkeypatch.chdir(cwd_b)
    try:
        load_and_validate_manifest(Path("manifest.json"))
    except ManifestError as exc:
        verdict_b = (exc.code, exc.details)
    else:
        raise AssertionError("expected rejection in cwd_b")

    # Same rejection code and details, regardless of cwd.
    assert verdict_a == verdict_b, (
        f"verdict must be cwd-independent; got {verdict_a!r} vs {verdict_b!r}"
    )


def test_loader_absolute_path_still_works(tmp_path: Path) -> None:
    """An absolute manifest path with no referenced files still
    loads successfully (P0-3 of review 4689835238: the absolute
    path branch is unchanged)."""
    mf = _write_manifest(
        tmp_path,
        {
            "schema_version": "1.0",
            "suite_id": "abs",
            "scenarios": [
                {
                    "scenario_id": "s",
                    "database_backend": "sqlite",
                    "expected_outcome": "SUCCEEDED",
                }
            ],
        },
    )
    # mf is absolute.
    assert mf.is_absolute()
    m = load_and_validate_manifest(mf)
    assert m.suite_id == "abs"


def test_loader_relative_path_rejected_before_any_file_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The relative-path rejection must occur before any file
    read. Per P0-3 of review 4689835238: ``Path.read_text`` /
    ``Path.read_bytes`` is NEVER called for a relative path.

    This test monkeypatches ``Path.read_text`` and
    ``Path.read_bytes`` to fail loudly if they are called; if
    the rejection is correct, neither will be invoked.
    """

    from cold_storage.evaluation.manifest import ManifestError

    def _explode(*args: object, **kwargs: object) -> object:
        raise AssertionError(
            "Path.read_text/read_bytes must not be called for "
            "a relative manifest_path (P0-3 of review 4689835238)"
        )

    monkeypatch.setattr(Path, "read_text", _explode)
    monkeypatch.setattr(Path, "read_bytes", _explode)
    try:
        load_and_validate_manifest(Path("manifest.json"))
    except ManifestError as exc:
        assert exc.code == "MANIFEST_ERROR"
        assert exc.details == {"manifest_path_kind": "relative"}
