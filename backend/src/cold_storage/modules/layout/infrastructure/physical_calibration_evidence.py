"""Read frozen R12 evidence and proposed physical sources; no approval or writes."""

import json
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.functional_sizing_sources import checked_bytes
from cold_storage.modules.layout.application.physical_room_calibration_review import (
    R12,
    R12_MANIFEST_SHA,
)
from cold_storage.modules.layout.infrastructure.functional_site_impact_evidence import (
    read_site_impact_evidence,
)


def read_calibration_evidence(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    files = read_site_impact_evidence(root)
    name = f"{R12}/source-manifest.json"
    files[name] = (root / name).read_bytes()
    manifest = json.loads(checked_bytes(files, name, R12_MANIFEST_SHA))
    required = {
        **manifest["source_files"],
        **{f"{R12}/{n}": s for n, s in manifest["derived_files"].items()},
    }
    for name, digest in required.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("R13_SOURCE_EVIDENCE_MISSING:" + name)
        files[name] = path.read_bytes()
        checked_bytes(files, name, digest)
    return files


def read_proposed_documents(packet: dict[str, Any], directory: Path) -> dict[str, bytes]:
    root = directory.resolve()
    result = {}
    for doc in packet.get("source_documents", {}).values():
        name = doc["file_name"]
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("PHYSICAL_DOCUMENT_PATH_MISSING_OR_OUTSIDE_INPUT_ROOT")
        result[name] = path.read_bytes()
    return result
