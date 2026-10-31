"""Immutable R14 byte/hash readback for independent R15 reports."""

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

R14 = "docs/previews/v2.2.2/r11-r14-ten-door-locker-r1"
R14_MANIFEST_SHA256 = "22d55eafed7c041de4c284fb7cdcb3d38bd9c87f20a0f6e16b4f1dae890d8e9e"


def read_r14_archive(root: Path) -> dict[str, Any]:
    root = root.resolve()
    directory = root / R14
    raw_manifest = (directory / "source-manifest.json").read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != R14_MANIFEST_SHA256:
        raise ValueError("PINNED_R14_MANIFEST_CHANGED")
    manifest = json.loads(raw_manifest)
    for name, expected in {
        **manifest["source_files"],
        **{f"{R14}/{n}": s for n, s in manifest["derived_files"].items()},
    }.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("R14_ARCHIVE_SOURCE_MISSING_OR_OUTSIDE_ROOT:" + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("R14_ARCHIVE_SOURCE_OR_DERIVED_BYTES_CHANGED:" + name)
    result: dict[str, Any] = json.loads(
        gzip.decompress((directory / "full-new-witnesses.json.gz").read_bytes())
    )
    if not isinstance(result, dict):
        raise ValueError("R14_ARCHIVED_REVIEW_OBJECT_REQUIRED")
    return result
