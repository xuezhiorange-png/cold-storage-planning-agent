"""Shared artifact I/O authority for TASK-011 evaluation and pilot runs.

All managed evaluation writes use temporary sibling files, flush/fsync where
supported, and ``os.replace``.  Existing managed outputs are rejected before
side effects; cleanup is restricted to an explicitly-owned absolute run root.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any

from cold_storage.evaluation.canonicalization import canonicalize_production_outputs
from cold_storage.evaluation.errors import (
    EvaluationArtifactWriteError,
    EvaluationInfrastructureError,
    StaleEvaluationArtifactsError,
)


def _as_path(value: Path | str) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _safe_makedirs(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EvaluationInfrastructureError(
            f"Cannot create directory {path}: {exc}",
            details={"path": str(path)},
        ) from exc


def atomic_write_bytes(*, path: Path, data: bytes) -> None:
    """Persist bytes atomically without coercion or re-serialization."""
    path = _as_path(path)
    if not isinstance(data, bytes):
        raise EvaluationArtifactWriteError(
            "atomic_write_bytes requires bytes; implicit coercion is forbidden.",
            details={"path": str(path), "data_type": type(data).__name__},
        )
    _safe_makedirs(path.parent)
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                with suppress(OSError):
                    os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp_name)
            raise
    except OSError as exc:
        raise EvaluationArtifactWriteError(
            f"Atomic byte write to {path} failed: {exc}",
            details={"path": str(path)},
        ) from exc


def atomic_write_json(*, path: Path, data: Any) -> None:
    """Persist a strict-JSON-domain value atomically.

    The validation and serialization semantics intentionally match the
    historical C-2 writer: no ``default=str`` fallback and stable key order.
    """
    path = _as_path(path)
    try:
        canonicalize_production_outputs(data, excluded_paths=())
    except Exception as exc:
        raise EvaluationArtifactWriteError(
            "atomic_write_json received a value outside the strict JSON domain.",
            details={
                "path": str(path),
                "data_type": type(data).__name__,
                "canonicalizer_code": str(
                    getattr(exc, "code", "CANONICALIZATION_ERROR")
                ),
            },
        ) from exc

    _safe_makedirs(path.parent)
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                with suppress(OSError):
                    os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp_name)
            raise
    except OSError as exc:
        raise EvaluationArtifactWriteError(
            f"Atomic write to {path} failed: {exc}",
            details={"path": str(path)},
        ) from exc


def assert_no_managed_artifacts(
    *,
    root: Path,
    managed_paths: Iterable[Path | str],
) -> None:
    """Reject any pre-existing managed path before a run begins.

    ``managed_paths`` may contain paths relative to ``root`` or absolute paths,
    but every resolved target must remain inside the resolved root.
    """
    root = _as_path(root)
    if not root.is_absolute():
        raise EvaluationInfrastructureError(
            "Managed output root must be absolute.",
            details={"root": str(root)},
        )
    resolved_root = root.resolve(strict=False)
    stale: list[str] = []
    for raw in managed_paths:
        candidate = _as_path(raw)
        target = candidate if candidate.is_absolute() else resolved_root / candidate
        resolved_target = target.resolve(strict=False)
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError as exc:
            raise EvaluationInfrastructureError(
                "Managed artifact path escapes the output root.",
                details={
                    "root": str(resolved_root),
                    "managed_path": str(candidate),
                    "resolved_path": str(resolved_target),
                },
            ) from exc
        if resolved_target.exists() or resolved_target.is_symlink():
            stale.append(str(resolved_target))
    if stale:
        raise StaleEvaluationArtifactsError(
            "Pre-existing managed artifacts at the target root; overwrite is forbidden.",
            details={"root": str(resolved_root), "stale_paths": sorted(stale)},
        )


def remove_managed_output_root(
    *,
    root: Path,
    allowed_parent: Path,
    ownership_marker: str = "pilot-run.json",
) -> None:
    """Remove one explicitly-owned run root and nothing else.

    The root and allowed parent must be absolute, non-symlink paths.  The root
    must be a strict descendant of the allowed parent and contain the named
    ownership marker.  Filesystem roots, the user's home, the allowed parent
    itself, and paths outside the parent are rejected.
    """
    root = _as_path(root)
    allowed_parent = _as_path(allowed_parent)
    if not root.is_absolute() or not allowed_parent.is_absolute():
        raise EvaluationInfrastructureError(
            "Cleanup root and allowed parent must be absolute.",
            details={"root": str(root), "allowed_parent": str(allowed_parent)},
        )
    if root.is_symlink() or allowed_parent.is_symlink():
        raise EvaluationInfrastructureError(
            "Cleanup through a symlink is forbidden.",
            details={"root": str(root), "allowed_parent": str(allowed_parent)},
        )

    resolved_root = root.resolve(strict=False)
    resolved_parent = allowed_parent.resolve(strict=False)
    forbidden = {Path(resolved_root.anchor), Path.home().resolve(), resolved_parent}
    if resolved_root in forbidden:
        raise EvaluationInfrastructureError(
            "Unsafe cleanup root rejected.",
            details={"root": str(resolved_root)},
        )
    try:
        relative = resolved_root.relative_to(resolved_parent)
    except ValueError as exc:
        raise EvaluationInfrastructureError(
            "Cleanup root is outside its allowed parent.",
            details={"root": str(resolved_root), "allowed_parent": str(resolved_parent)},
        ) from exc
    if not relative.parts:
        raise EvaluationInfrastructureError(
            "Cleanup root must be a strict child of the allowed parent.",
            details={"root": str(resolved_root)},
        )
    if not resolved_root.exists():
        return
    if not resolved_root.is_dir():
        raise EvaluationInfrastructureError(
            "Cleanup root is not a directory.",
            details={"root": str(resolved_root)},
        )
    marker = resolved_root / ownership_marker
    if not marker.is_file() or marker.is_symlink():
        raise EvaluationInfrastructureError(
            "Cleanup root lacks the required ownership marker.",
            details={"root": str(resolved_root), "marker": str(marker)},
        )
    try:
        shutil.rmtree(resolved_root)
    except OSError as exc:
        raise EvaluationInfrastructureError(
            f"Managed output cleanup failed: {exc}",
            details={"root": str(resolved_root)},
        ) from exc


__all__ = [
    "assert_no_managed_artifacts",
    "atomic_write_bytes",
    "atomic_write_json",
    "remove_managed_output_root",
]
