"""Path safety verification for evaluation references."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from cold_storage.evaluation.errors import (
    UnsafeEvaluationPathError,
)


class EvaluationReferenceKind(StrEnum):
    """Allowed reference type with directory restrictions."""

    PROJECT_INPUT = "project_input"
    EXPECTED_OUTPUT = "expected_output"
    DOCUMENT = "document"


# Allowed directories per reference kind
_ALLOWED_DIRS: dict[str, set[str]] = {
    EvaluationReferenceKind.PROJECT_INPUT: {"fixtures/projects", "examples"},
    EvaluationReferenceKind.EXPECTED_OUTPUT: {"expected", "examples"},
    EvaluationReferenceKind.DOCUMENT: {"fixtures/documents", "documents", "examples"},
}


def _check_reference_kind(
    relative_path: Path,
    reference_kind: EvaluationReferenceKind,
) -> None:
    """Verify that the reference path is in an allowed directory for its kind."""
    allowed = _ALLOWED_DIRS.get(str(reference_kind), set())
    # Get the parent as a relative path string
    try:
        rel_dir = str(relative_path.parent)
    except Exception:
        rel_dir = str(relative_path)
    if not rel_dir or rel_dir == ".":
        raise UnsafeEvaluationPathError(
            code="EVAL_REFERENCE_DIRECTORY_FORBIDDEN",
            message=(
                f"Reference of kind '{reference_kind}' is not allowed "
                f"at root level; must be in one of: {sorted(allowed)}"
            ),
            field=str(relative_path),
        )
    # Check if it starts with any allowed prefix
    for allowed_prefix in allowed:
        if rel_dir == allowed_prefix or rel_dir.startswith(f"{allowed_prefix}/"):
            return
    raise UnsafeEvaluationPathError(
        code="EVAL_REFERENCE_DIRECTORY_FORBIDDEN",
        message=(
            f"Reference of kind '{reference_kind}' at '{relative_path}' "
            f"is not in an allowed directory; allowed: {sorted(allowed)}"
        ),
        field=str(relative_path),
    )


def resolve_and_verify_path(
    relative_path: Path,
    *,
    evaluation_root: Path,
    reference_kind: EvaluationReferenceKind | None = None,
    allow_missing: bool = False,
) -> Path:
    """Resolve a manifest-relative path and verify it is safe.

    Args:
        relative_path: The path as specified in the manifest (must be relative).
        evaluation_root: The root of the evaluation directory.
        reference_kind: Type of reference (for directory whitelist checking).
        allow_missing: If True, missing files pass reference checks.
            Directory containment and symlink checks are still performed.

    Returns:
        The resolved absolute path within the evaluation root.

    Raises:
        UnsafeEvaluationPathError: If the path is absolute, escapes the
            evaluation root, follows a symlink outside, references
            a disallowed directory, or is a directory (when not allowing missing).
    """
    _reject_absolute(relative_path)
    _reject_escape(relative_path)

    resolved = (evaluation_root / relative_path).resolve()
    evaluation_root_resolved = evaluation_root.resolve()

    # Symlink escape: resolved must be inside evaluation root
    if not resolved.is_relative_to(evaluation_root_resolved):
        raise UnsafeEvaluationPathError(
            code="EVAL_PATH_SYMLINK_ESCAPE",
            message=(
                f"Symlink in '{relative_path}' escapes evaluation root '{evaluation_root_resolved}'"
            ),
            field=str(relative_path),
        )

    # Check allowed directory per reference kind
    if reference_kind is not None:
        _check_reference_kind(relative_path, reference_kind)

    if not allow_missing and not resolved.exists():
        raise UnsafeEvaluationPathError(
            code="EVAL_REFERENCE_NOT_FOUND",
            message=f"Referenced path does not exist: '{resolved}'",
            field=str(relative_path),
        )

    if not allow_missing and not resolved.is_file():
        raise UnsafeEvaluationPathError(
            code="EVAL_REFERENCE_DIRECTORY_FORBIDDEN",
            message=f"Referenced path is a directory, not a file: '{resolved}'",
            field=str(relative_path),
        )

    return resolved


def _reject_absolute(path: Path) -> None:
    if path.is_absolute():
        raise UnsafeEvaluationPathError(
            code="EVAL_PATH_ABSOLUTE",
            message=f"Absolute path is not allowed: '{path}'",
            field=str(path),
        )


def _reject_escape(path: Path) -> None:
    # Check for path components that would escape the root
    parts = path.parts
    if ".." in parts:
        raise UnsafeEvaluationPathError(
            code="EVAL_PATH_ESCAPE",
            message=f"Path '{path}' contains '..' and could escape the evaluation root",
            field=str(path),
        )
    # Also check via resolve
    try:
        Path(path).resolve()
    except (OSError, RuntimeError):
        raise UnsafeEvaluationPathError(
            code="EVAL_PATH_ESCAPE",
            message=f"Path '{path}' cannot be safely resolved",
            field=str(path),
        ) from None
