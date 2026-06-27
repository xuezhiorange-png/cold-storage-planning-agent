"""Tests for evaluation path safety."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cold_storage.evaluation.errors import UnsafeEvaluationPathError
from cold_storage.evaluation.paths import resolve_and_verify_path


def test_absolute_path_rejected() -> None:
    """Absolute paths must be rejected."""
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_PATH_ABSOLUTE"):
        resolve_and_verify_path(
            Path("/etc/passwd"),
            evaluation_root=Path("/tmp/eval"),
        )


def test_dotdot_escape_rejected() -> None:
    """Path with '..' must be rejected."""
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_PATH_ESCAPE"):
        resolve_and_verify_path(
            Path("../outside/file.json"),
            evaluation_root=Path("/tmp/eval"),
        )


def test_nested_dotdot_escape_rejected() -> None:
    """Nested '..' escape must be rejected."""
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_PATH_ESCAPE"):
        resolve_and_verify_path(
            Path("fixtures/../../outside/file.json"),
            evaluation_root=Path("/tmp/eval"),
        )


def test_missing_file_rejected() -> None:
    """Non-existent referenced file must be rejected."""
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_NOT_FOUND"):
        resolve_and_verify_path(
            Path("nonexistent-file.json"),
            evaluation_root=Path(tempfile.mkdtemp()),
        )


def test_valid_in_root_file_passes(tmp_path: Path) -> None:
    """Valid relative file within evaluation root must pass."""
    file_path = tmp_path / "fixtures" / "valid.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    result = resolve_and_verify_path(
        Path("fixtures/valid.json"),
        evaluation_root=tmp_path,
    )
    assert result == file_path.resolve()


def test_directory_ref_rejected(tmp_path: Path) -> None:
    """Referencing a directory (not a file) must be rejected."""
    (tmp_path / "dir").mkdir()
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_DIRECTORY_FORBIDDEN"):
        resolve_and_verify_path(
            Path("dir"),
            evaluation_root=tmp_path,
        )


def test_symlink_outside_root_rejected(tmp_path: Path) -> None:
    """Symlink that resolves outside the evaluation root must be rejected."""
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "secret.json"
    outside_file.write_text("{}")

    inside = tmp_path / "eval_root"
    inside.mkdir()
    link = inside / "link.json"
    link.symlink_to(outside_file)

    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_PATH_SYMLINK_ESCAPE"):
        resolve_and_verify_path(
            Path("link.json"),
            evaluation_root=inside,
        )
