"""Pinned R15 source readback. No photo lookup or layout generation."""

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

R15 = "docs/previews/v2.2.2/r11-r15-ten-door-local-relayout-r1"
MANIFEST_SHA256 = "5464eda082bcbf5023258f4304fc6e1d21bc8654ac6aa5170a4e1562fdb313e6"


def read_r15_archive(root: Path) -> dict[str, Any]:
    root = root.resolve()
    directory = root / R15
    manifest_bytes = (directory / "source-manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise ValueError("PINNED_R15_MANIFEST_CHANGED")
    manifest = json.loads(manifest_bytes)
    for name, digest in {
        **manifest["source_files"],
        **{f"{R15}/{n}": d for n, d in manifest["derived_files"].items()},
    }.items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("R15_SOURCE_OR_DERIVED_BYTES_CHANGED:" + name)
    data: dict[str, Any] = json.loads(
        gzip.decompress((directory / "full-new-witnesses.json.gz").read_bytes())
    )
    # Only the pinned source is needed. Do not retain/re-evaluate the other eleven
    # R15 arrangements or the superseded photo task in the new review.
    return {"reports": [c for c in data["reports"] if c["id"] == "R15-03"]}
