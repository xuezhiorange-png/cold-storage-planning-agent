"""Read bounded, known evidence paths; no database, execution or write port."""

from pathlib import Path

from cold_storage.modules.layout.application.functional_sizing_sources import (
    ANCHORS,
    required_evidence_hashes,
)


def read_functional_sizing_evidence(root: Path) -> dict[str, bytes]:
    root = root.resolve()

    def read(name: str) -> bytes:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("FUNCTIONAL_SIZING_EVIDENCE_PATH_INVALID:" + name)
        return path.read_bytes()

    result = {name: read(name) for name in ANCHORS}
    for name in required_evidence_hashes(result):
        if name not in result:
            result[name] = read(name)
    return result
