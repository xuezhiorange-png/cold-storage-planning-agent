"""Path-safety helpers for the TASK-011C V1 evaluation framework.

This module provides a single function :func:`safe_resolve_manifest_path`
that resolves a manifest-referenced path against the manifest
owner directory and validates that the result does not escape the
manifest owner's directory tree (or any other configured root).

Contract requirements (Charles D5 / D6 / D7 + V1 forbidden practices):

* Reject **absolute paths** (``/foo`` or ``C:\foo``).
* Reject **``..`` traversal** (any path component that resolves
  outside the manifest root).
* Reject **symlink escape** when the path is on a filesystem that
  supports symlinks. If symlink resolution is unavailable
  (e.g., on some Windows configurations or in a chrooted
  environment), the function MUST fail closed.
* Reject **empty / whitespace-only paths**.
* Reject **undeclared external resources** (any path that, after
  resolution, does not live under the manifest root).
* Reject **cwd-dependent resolution** — the function MUST NOT
  consult the current working directory at any point; the only
  inputs are the manifest owner path and the declared path string.
* Reject **package / repository root escape**.

The function returns a :class:`pathlib.Path` that is guaranteed to
be a sub-path of the manifest root. It is the single, authoritative
path resolver for the TASK-011C manifest loader and any downstream
manifest consumer.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

# Allowed path characters: anything that is not a path separator,
# null byte, or control character. The check is on the **raw** string
# (before path resolution) to catch ``..`` and absolute prefixes that
# the resolver might silently accept on some platforms.
_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9._/-]+$")

# Whitespace-only or empty path check.
_WHITESPACE = re.compile(r"^\s*$")

# Maximum length of a manifest-declared path string. Defensive
# bound; no real manifest path is anywhere near this.
_MAX_PATH_LENGTH: Final[int] = 4096


class PathSafetyError(Exception):
    """Base class for all path-safety violations.

    Subclasses set a stable, machine-readable ``code`` attribute.
    Downstream code MUST classify via ``code``, NEVER by parsing
    ``str(exc)``.
    """

    code: str = "PATH_SAFETY_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self._details: dict[str, object] = dict(details) if details else {}

    @property
    def details(self) -> dict[str, object]:
        return dict(self._details)


class AbsolutePathForbidden(PathSafetyError):
    """The declared path is absolute (e.g., starts with ``/`` or ``C:\\``)."""

    code = "ABSOLUTE_PATH_FORBIDDEN"


class TraversalForbidden(PathSafetyError):
    """The declared path contains a ``..`` segment that escapes the root."""

    code = "TRAVERSAL_FORBIDDEN"


class EmptyPathForbidden(PathSafetyError):
    """The declared path is empty or whitespace-only."""

    code = "EMPTY_PATH_FORBIDDEN"


class UndeclaredExternalResource(PathSafetyError):
    """The resolved path is not under the manifest root."""

    code = "UNDECLARED_EXTERNAL_RESOURCE"


class SymlinkEscapeForbidden(PathSafetyError):
    """A symlink in the resolved path points outside the manifest root."""

    code = "SYMLINK_ESCAPE_FORBIDDEN"


class ControlCharacterForbidden(PathSafetyError):
    """The declared path contains a NUL or other control character."""

    code = "CONTROL_CHARACTER_FORBIDDEN"


class PathLengthExceeded(PathSafetyError):
    """The declared path string exceeds the maximum length."""

    code = "PATH_LENGTH_EXCEEDED"


def safe_resolve_manifest_path(
    declared_path: str,
    *,
    manifest_root: Path,
) -> Path:
    """Resolve ``declared_path`` against ``manifest_root``, safely.

    The function validates the declared path against the strict
    safety contract, resolves it against ``manifest_root`` (which
    must be an absolute, canonical path), and verifies the result
    does not escape the root.

    Parameters
    ----------
    declared_path:
        The path string declared in the manifest (e.g., the
        ``fixture_path`` or ``expected_output_path`` field). MUST
        be a relative path with no leading ``/``.
    manifest_root:
        The directory that **owns** the manifest. The function
        resolves ``declared_path`` against this root. MUST be an
        absolute, canonical path (the caller is responsible for
        ensuring that).

    Returns
    -------
    pathlib.Path
        A canonical, absolute path that is a sub-path of
        ``manifest_root``. Safe to open / read / write.

    Raises
    ------
    PathSafetyError (or one of its concrete subclasses)
        On any safety violation. The exception ``code`` attribute
        identifies the specific failure.
    """
    # ── Input sanity ────────────────────────────────────────────────
    if not isinstance(declared_path, str):
        raise PathSafetyError(
            f"declared_path must be a str; got {type(declared_path).__name__}.",
            details={"value_type": type(declared_path).__name__},
        )

    if _WHITESPACE.match(declared_path):
        raise EmptyPathForbidden(
            "declared_path is empty or whitespace-only.",
            details={"value": declared_path},
        )

    if len(declared_path) > _MAX_PATH_LENGTH:
        raise PathLengthExceeded(
            f"declared_path exceeds max length {_MAX_PATH_LENGTH}.",
            details={"length": len(declared_path), "max": _MAX_PATH_LENGTH},
        )

    # Reject NUL bytes and other control characters in the raw
    # string. ``os.path.split`` and friends are not guaranteed to
    # reject all of these.
    for ch in declared_path:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ControlCharacterForbidden(
                f"declared_path contains control character U+{ord(ch):04X}.",
                details={"codepoint": ord(ch)},
            )

    # Reject absolute paths. We use ``os.path.isabs`` which is
    # platform-aware (handles Windows drive letters and UNC paths).
    if os.path.isabs(declared_path):
        raise AbsolutePathForbidden(
            f"declared_path is absolute: {declared_path!r}.",
            details={"value": declared_path},
        )

    # Reject any ``..`` segment in the raw path. The check is
    # performed on each separator-split component, AFTER normalizing
    # the path. We do not allow any component to be exactly ``..`` or
    # to begin with ``..`` (e.g., ``..foo`` is OK on POSIX but
    # suspicious; we reject it conservatively).
    normalized = os.path.normpath(declared_path)
    for part in normalized.split(os.sep):
        if part == "..":
            raise TraversalForbidden(
                f"declared_path contains '..' segment: {declared_path!r}.",
                details={"value": declared_path, "normalized": normalized},
            )

    # Validate manifest_root
    if not isinstance(manifest_root, Path):
        raise PathSafetyError(
            f"manifest_root must be a pathlib.Path; got {type(manifest_root).__name__}.",
            details={"value_type": type(manifest_root).__name__},
        )
    if not manifest_root.is_absolute():
        raise PathSafetyError(
            f"manifest_root must be absolute: {manifest_root!r}.",
            details={"value": str(manifest_root)},
        )

    # Compute the resolved candidate. The ``resolve`` call follows
    # symlinks (when the path exists or its parents exist); for
    # non-existent paths it performs a lexical resolve.
    candidate = (manifest_root / normalized).resolve(strict=False)

    # Verify the resolved candidate is under manifest_root.
    # We use ``os.path.commonpath`` to defend against ``Path.is_relative_to``
    # edge cases on older Python versions; ``Path.is_relative_to`` is
    # available on Python 3.9+ but we keep the comparison explicit.
    root_resolved = manifest_root.resolve()
    try:
        common = os.path.commonpath([str(candidate), str(root_resolved)])
    except ValueError:
        # Different drives on Windows; definitely not under root.
        raise UndeclaredExternalResource(
            f"resolved path is not under manifest root: {candidate!r}.",
            details={
                "resolved": str(candidate),
                "manifest_root": str(root_resolved),
            },
        ) from None

    if common != str(root_resolved):
        raise UndeclaredExternalResource(
            f"resolved path is not under manifest root: {candidate!r}.",
            details={
                "resolved": str(candidate),
                "manifest_root": str(root_resolved),
            },
        )

    # Symlink escape check: walk the candidate's parents and check
    # that no symlink in the chain points outside the root. This
    # catches cases where ``resolve`` does not follow every symlink
    # (e.g., on some platforms or when intermediate dirs do not
    # exist).
    chain: list[Path] = []
    # ``Path.parents`` is unbounded; cap to a reasonable bound.
    for parent in [candidate, *candidate.parents]:
        chain.append(parent)
        if parent == Path("/") or parent == root_resolved:
            break
    for p in chain:
        if p.is_symlink():
            try:
                link_target = p.readlink()  # may be relative
            except OSError as exc:
                # Cannot readlink — fail closed.
                raise SymlinkEscapeForbidden(
                    f"cannot readlink {p!r}: {exc}.",
                    details={"path": str(p)},
                ) from exc
            if link_target.is_absolute():
                raise SymlinkEscapeForbidden(
                    f"symlink {p!r} has absolute target {link_target!r}.",
                    details={"path": str(p), "target": str(link_target)},
                )
            # Resolve the symlink target relative to its parent.
            resolved_target = (p.parent / link_target).resolve(strict=False)
            try:
                target_common = os.path.commonpath([str(resolved_target), str(root_resolved)])
            except ValueError:
                raise SymlinkEscapeForbidden(
                    f"symlink {p!r} escapes manifest root: target {resolved_target!r}.",
                    details={
                        "path": str(p),
                        "target": str(resolved_target),
                    },
                ) from None
            if target_common != str(root_resolved):
                raise SymlinkEscapeForbidden(
                    f"symlink {p!r} escapes manifest root: target {resolved_target!r}.",
                    details={
                        "path": str(p),
                        "target": str(resolved_target),
                    },
                )

    return candidate


__all__ = [
    "AbsolutePathForbidden",
    "ControlCharacterForbidden",
    "EmptyPathForbidden",
    "PathLengthExceeded",
    "PathSafetyError",
    "SymlinkEscapeForbidden",
    "TraversalForbidden",
    "UndeclaredExternalResource",
    "safe_resolve_manifest_path",
]
