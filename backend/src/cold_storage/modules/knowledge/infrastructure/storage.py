"""Local document storage — secure file persistence."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import IO, Protocol


class StoredObject:
    """Result of storing a file — contains the storage key, size, and content hash."""

    def __init__(
        self,
        storage_key: str,
        file_size_bytes: int,
        content_sha256: str,
    ) -> None:
        self.storage_key = storage_key
        self.file_size_bytes = file_size_bytes
        self.content_sha256 = content_sha256


class DocumentStorage(Protocol):
    """Protocol for document storage backends."""

    def save(self, content: IO[bytes], revision_id: str, content_sha256: str) -> StoredObject:
        """Save content and return a stored object with metadata."""
        ...

    def open(self, storage_key: str) -> IO[bytes]:
        """Open a stored file by its storage key."""
        ...

    def delete(self, storage_key: str) -> None:
        """Delete a stored file by its storage key."""
        ...

    def exists(self, storage_key: str) -> bool:
        """Return True if the storage key exists."""
        ...


class LocalDocumentStorage:
    """File-system backed document storage with atomic writes and path safety.

    Storage layout: ``<base_dir>/<sha256[:2]>/<revision_id>/content``

    Security requirements:
    - Path traversal prevention
    - Atomic writes via temp file + rename
    - Upload size limit
    - Temp file cleanup on failure
    """

    def __init__(
        self,
        base_dir: str | Path,
        max_upload_bytes: int = 25 * 1024 * 1024,  # 25 MB default
    ) -> None:
        self._base = Path(base_dir)
        self._max_upload_bytes = max_upload_bytes
        self._base.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        content: IO[bytes],
        revision_id: str,
        content_sha256: str,
    ) -> StoredObject:
        """Save content to local storage with atomic write.

        The file is written to ``<base>/<sha256[:2]>/<revision_id>/content``.
        A temporary file is used first and renamed atomically on success.

        Raises
        ------
        ValueError
            If revision_id or content_sha256 contain path traversal sequences.
        OSError
            If the write fails or the file exceeds the size limit.
        """
        self._validate_component(revision_id)

        bucket = content_sha256[:2]
        self._validate_component(bucket)
        dest_dir = self._base / bucket / revision_id
        dest_file = dest_dir / "content"

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Atomic write via temp file
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
        try:
            bytes_written = 0
            hasher = hashlib.sha256()
            with os.fdopen(tmp_fd, "wb") as tmp_file:
                while True:
                    chunk = content.read(65536)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > self._max_upload_bytes:
                        raise OSError(
                            f"File exceeds maximum upload size of {self._max_upload_bytes} bytes"
                        )
                    hasher.update(chunk)
                    tmp_file.write(chunk)

            # Verify content hash matches expected
            actual_hash = hasher.hexdigest()
            if actual_hash != content_sha256:
                os.unlink(tmp_path)
                raise OSError(
                    f"Content hash mismatch: expected {content_sha256}, got {actual_hash}"
                )

            # Atomic rename
            shutil.move(tmp_path, str(dest_file))
            return StoredObject(
                storage_key=f"{bucket}/{revision_id}/content",
                file_size_bytes=bytes_written,
                content_sha256=actual_hash,
            )
        except Exception:
            # Cleanup temp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def open(self, storage_key: str) -> IO[bytes]:
        """Open a stored file by its storage key (format: ``<hex2>/<revision_id>/content``).

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the storage key contains path traversal sequences.
        """
        file_path = self._resolve_storage_key(storage_key)
        if not file_path.is_file():
            raise FileNotFoundError(f"Storage key not found: {storage_key}")
        return open(file_path, "rb")  # noqa: SIM115

    def delete(self, storage_key: str) -> None:
        """Delete a stored file by its storage key.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the storage key contains path traversal sequences.
        """
        file_path = self._resolve_storage_key(storage_key)
        if not file_path.is_file():
            raise FileNotFoundError(f"Storage key not found: {storage_key}")
        file_path.unlink()

    def exists(self, storage_key: str) -> bool:
        """Return True if the storage key points to an existing file."""
        try:
            file_path = self._resolve_storage_key(storage_key)
        except (ValueError, FileNotFoundError):
            return False
        return file_path.is_file()

    @staticmethod
    def _validate_component(component: str) -> None:
        """Validate a single path component (no traversal, no separators)."""
        if ".." in component or "/" in component or "\\" in component:
            raise ValueError(f"Invalid path component: {component!r}")
        if not component:
            raise ValueError("Path component must not be empty")

    def _resolve_storage_key(self, storage_key: str) -> Path:
        """Resolve a storage key to an absolute path, enforcing no traversal.

        A storage key must have the format ``<hex2>/<revision_id>/content``.
        After resolving against base_dir, the result must still be within base_dir.
        """
        import re

        # Strict format validation: exactly 3 components, first is 2-hex, last is 'content'
        if not re.match(r"^[0-9a-f]{2}/[^/]+/content$", storage_key):
            raise ValueError(
                f"Storage key must match <hex2>/<revision_id>/content, got: {storage_key!r}"
            )
        parts = storage_key.split("/")
        for part in parts:
            if ".." in part or part.startswith("/") or "\\" in part:
                raise ValueError(f"Invalid path component in storage key: {part!r}")
        resolved = (self._base / storage_key).resolve()
        if not resolved.is_relative_to(self._base.resolve()):
            raise ValueError(f"Path traversal detected in storage key: {storage_key!r}")
        return resolved
