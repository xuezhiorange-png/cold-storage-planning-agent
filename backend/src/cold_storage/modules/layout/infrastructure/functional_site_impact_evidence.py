"""Read the frozen R11 bundle and exact archived advisory bytes, never write."""

import json
from pathlib import Path

from cold_storage.modules.layout.application.functional_site_impact_review import (
    R11_MANIFEST_SHA256,
    R11_PATH,
)
from cold_storage.modules.layout.application.functional_sizing_sources import checked_bytes
from cold_storage.modules.layout.infrastructure.functional_sizing_evidence import (
    read_functional_sizing_evidence,
)


def read_site_impact_evidence(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    files = read_functional_sizing_evidence(root)
    name = f"{R11_PATH}/source-manifest.json"
    files[name] = (root / name).read_bytes()
    manifest = json.loads(checked_bytes(files, name, R11_MANIFEST_SHA256))
    for path, sha in manifest["source_files"].items():
        checked_bytes(files, path, sha)
    for relative, sha in manifest["derived_files"].items():
        name = f"{R11_PATH}/{relative}"
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("SITE_IMPACT_EVIDENCE_REQUIRED:" + name)
        files[name] = path.read_bytes()
        checked_bytes(files, name, sha)
    return files
