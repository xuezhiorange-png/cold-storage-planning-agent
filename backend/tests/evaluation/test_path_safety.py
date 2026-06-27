"""Tests for evaluation path safety."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cold_storage.evaluation.errors import UnsafeEvaluationPathError
from cold_storage.evaluation.paths import (
    EvaluationReferenceKind,
    resolve_and_verify_path,
)


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


def test_valid_in_root_project_input_passes(tmp_path: Path) -> None:
    """Valid project input within fixtures/projects/ must pass."""
    file_path = tmp_path / "fixtures" / "projects" / "valid.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    result = resolve_and_verify_path(
        Path("fixtures/projects/valid.json"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
    )
    assert result == file_path.resolve()


def test_directory_ref_rejected(tmp_path: Path) -> None:
    """Referencing a directory (not a file) must be rejected."""
    allowed_dir = tmp_path / "fixtures" / "projects"
    allowed_dir.mkdir(parents=True)
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_DIRECTORY_FORBIDDEN"):
        resolve_and_verify_path(
            Path("fixtures/projects"),
            evaluation_root=tmp_path,
            reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
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


def test_symlink_same_prefix_escape_rejected(tmp_path: Path) -> None:
    """Symlink with same-prefix sibling name outside root must be rejected.

    Regression: root=/tmp/eval, symlink target=/tmp/evaluation-outside/secret.json
    must NOT be silently accepted due to naive str.startswith checks.
    """
    outside = tmp_path / "eval_root-outside"
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


def test_project_input_in_wrong_dir_rejected(tmp_path: Path) -> None:
    """Project input in expected/ must be rejected (only fixtures/projects/ or examples/ allowed)."""
    file_path = tmp_path / "expected" / "data.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_DIRECTORY_FORBIDDEN"):
        resolve_and_verify_path(
            Path("expected/data.json"),
            evaluation_root=tmp_path,
            reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
        )


def test_expected_output_in_wrong_dir_rejected(tmp_path: Path) -> None:
    """Expected output in fixtures/projects/ must be rejected (only expected/ or examples/ allowed)."""
    file_path = tmp_path / "fixtures" / "projects" / "data.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_DIRECTORY_FORBIDDEN"):
        resolve_and_verify_path(
            Path("fixtures/projects/data.json"),
            evaluation_root=tmp_path,
            reference_kind=EvaluationReferenceKind.EXPECTED_OUTPUT,
        )


def test_allow_missing_still_checks_containment(tmp_path: Path) -> None:
    """allow_missing=True must still reject absolute paths and escapes."""
    # Absolute path still rejected
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_PATH_ABSOLUTE"):
        resolve_and_verify_path(
            Path("/etc/passwd"),
            evaluation_root=tmp_path,
            allow_missing=True,
        )

    # Dotdot escape still rejected
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_PATH_ESCAPE"):
        resolve_and_verify_path(
            Path("../outside/file.json"),
            evaluation_root=tmp_path,
            allow_missing=True,
        )


def test_allow_missing_still_checks_directory_whitelist(tmp_path: Path) -> None:
    """allow_missing=True must still reject disallowed directories."""
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_DIRECTORY_FORBIDDEN"):
        resolve_and_verify_path(
            Path("expected/data.json"),
            evaluation_root=tmp_path,
            reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
            allow_missing=True,
        )


def test_allow_missing_skips_existence_check(tmp_path: Path) -> None:
    """allow_missing=True must allow non-existent files in allowed directories."""
    result = resolve_and_verify_path(
        Path("fixtures/projects/nonexistent.json"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
        allow_missing=True,
    )
    assert result == (tmp_path / "fixtures" / "projects" / "nonexistent.json").resolve()


def test_valid_expected_output_passes(tmp_path: Path) -> None:
    """Valid expected output in expected/ must pass."""
    file_path = tmp_path / "expected" / "output.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    result = resolve_and_verify_path(
        Path("expected/output.json"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.EXPECTED_OUTPUT,
    )
    assert result == file_path.resolve()


def test_valid_document_in_examples_passes(tmp_path: Path) -> None:
    """Valid document in examples/ must pass."""
    file_path = tmp_path / "examples" / "doc.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# Document")
    result = resolve_and_verify_path(
        Path("examples/doc.md"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.DOCUMENT,
    )
    assert result == file_path.resolve()


def test_root_level_readme_rejected(tmp_path: Path) -> None:
    """Root-level README must be rejected (not in any allowed subdirectory)."""
    readme = tmp_path / "README.md"
    readme.write_text("# README")
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_DIRECTORY_FORBIDDEN"):
        resolve_and_verify_path(
            Path("README.md"),
            evaluation_root=tmp_path,
            reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
        )


def test_root_level_manifest_schema_rejected(tmp_path: Path) -> None:
    """Root-level manifest.schema.json must be rejected."""
    schema = tmp_path / "manifest.schema.json"
    schema.write_text("{}")
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_DIRECTORY_FORBIDDEN"):
        resolve_and_verify_path(
            Path("manifest.schema.json"),
            evaluation_root=tmp_path,
            reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
        )


def test_valid_document_in_fixtures_documents_passes(tmp_path: Path) -> None:
    """Valid document in fixtures/documents/ must pass."""
    file_path = tmp_path / "fixtures" / "documents" / "report.pdf"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("pdf content")
    result = resolve_and_verify_path(
        Path("fixtures/documents/report.pdf"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.DOCUMENT,
    )
    assert result == file_path.resolve()


def test_valid_document_in_documents_passes(tmp_path: Path) -> None:
    """Valid document in documents/ must pass."""
    file_path = tmp_path / "documents" / "guide.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("# Guide")
    result = resolve_and_verify_path(
        Path("documents/guide.md"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.DOCUMENT,
    )
    assert result == file_path.resolve()


def test_project_input_in_examples_passes(tmp_path: Path) -> None:
    """Project input in examples/ must pass (examples/ is allowed for projects too)."""
    file_path = tmp_path / "examples" / "sample.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    result = resolve_and_verify_path(
        Path("examples/sample.json"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
    )
    assert result == file_path.resolve()


def test_expected_output_in_examples_passes(tmp_path: Path) -> None:
    """Expected output in examples/ must pass (examples/ is allowed for expected output too)."""
    file_path = tmp_path / "examples" / "expected.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    result = resolve_and_verify_path(
        Path("examples/expected.json"),
        evaluation_root=tmp_path,
        reference_kind=EvaluationReferenceKind.EXPECTED_OUTPUT,
    )
    assert result == file_path.resolve()


def test_missing_file_in_allowed_dir_rejected(tmp_path: Path) -> None:
    """Non-existent file in an allowed directory must be rejected when allow_missing=False."""
    (tmp_path / "fixtures" / "projects").mkdir(parents=True)
    with pytest.raises(UnsafeEvaluationPathError, match="EVAL_REFERENCE_NOT_FOUND"):
        resolve_and_verify_path(
            Path("fixtures/projects/missing.json"),
            evaluation_root=tmp_path,
            reference_kind=EvaluationReferenceKind.PROJECT_INPUT,
        )


def test_none_reference_kind_skips_directory_check(tmp_path: Path) -> None:
    """Using reference_kind=None must skip the directory whitelist check."""
    file_path = tmp_path / "arbitrary" / "file.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("{}")
    result = resolve_and_verify_path(
        Path("arbitrary/file.json"),
        evaluation_root=tmp_path,
        reference_kind=None,
    )
    assert result == file_path.resolve()
