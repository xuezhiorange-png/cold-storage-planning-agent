"""Path safety verification for evaluation references."""

from __future__ import annotations

from pathlib import Path

from cold_storage.evaluation.errors import (
    UnsafeEvaluationPathError,
)


def resolve_and_verify_path(
    relative_path: Path,
    *,
    evaluation_root: Path,
    allow_missing: bool = False,
) -> Path:
    """Resolve a manifest-relative path and verify it is safe.

    Args:
        relative_path: The path as specified in the manifest (must be relative).
        evaluation_root: The root of the evaluation directory.
        allow_missing: If True, missing files pass reference checks.

    Returns:
        The resolved absolute path within the evaluation root.

    Raises:
        UnsafeEvaluationPathError: If the path is absolute, escapes the
            evaluation root, follows a symlink outside, or references
            a disallowed directory.
    """
    _reject_absolute(relative_path)
    _reject_escape(relative_path)

    resolved = (evaluation_root / relative_path).resolve()
    evaluation_root_resolved = evaluation_root.resolve()

    # Symlink escape: resolved path must start with evaluation root
    if not str(resolved).startswith(str(evaluation_root_resolved)):
        raise UnsafeEvaluationPathError(
            code="EVAL_PATH_SYMLINK_ESCAPE",
            message=(
                f"Symlink in '{relative_path}' escapes evaluation root '{evaluation_root_resolved}'"
            ),
            field=str(relative_path),
        )

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
        # resolve() will normpath which eliminates '..', so we use parts check above
        Path(path).resolve()
        # resolve. The parts check above is sufficient.
        pass
    except (OSError, RuntimeError):
        raise UnsafeEvaluationPathError(
            code="EVAL_PATH_ESCAPE",
            message=f"Path '{path}' cannot be safely resolved",
            field=str(path),
        ) from None
