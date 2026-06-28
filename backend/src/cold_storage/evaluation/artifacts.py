"""Raw and normalized artifact persistence helpers.

Each run directory contains::

    evaluation/runs/<run-id>/
    ├── run.json              # Managed by EvaluationRunDirectory (Phase A contract)
    ├── raw/                  # Raw production service outputs (this module)
    │   ├── baseline-feasible.json
    │   ├── high-throughput-review.json
    │   └── invalid-blocked.json
    ├── normalized/           # Canonicalized comparison artefacts (this module)
    │   ├── baseline-feasible.json
    │   ├── high-throughput-review.json
    │   └── invalid-blocked.json
    └── summary.json          # Managed by EvaluationRunDirectory.write_summary (Phase A contract)

This module is responsible ONLY for raw/ and normalized/ artifacts.
run.json and summary.json are managed exclusively by EvaluationRunDirectory.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


def write_raw(scenario_id: str, run_dir: Path, raw_data: dict[str, Any]) -> Path:
    """Write raw production output for a scenario."""
    dir_path = run_dir / "raw"
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"{scenario_id}.json"
    _write_json(path, raw_data)
    return path


def write_normalized(
    scenario_id: str,
    run_dir: Path,
    normalized: Any,
) -> Path:
    """Write normalized comparison artefact for a scenario."""
    dir_path = run_dir / "normalized"
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"{scenario_id}.json"
    _write_json(path, normalized)
    return path


def _write_json(path: Path, data: Any) -> None:
    """Write JSON with consistent formatting: sorted keys, trailing newline."""
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    """Compute SHA-256 digest for a file."""
    return sha256(path.read_bytes()).hexdigest()
