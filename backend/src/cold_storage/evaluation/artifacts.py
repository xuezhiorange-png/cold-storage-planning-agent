"""Raw and normalized artifact persistence helpers.

Each run directory contains::

    evaluation/runs/<run-id>/
    ├── run.json              # Run-level metadata
    ├── raw/                  # Raw production service outputs
    │   ├── baseline-feasible.json
    │   ├── high-throughput-review.json
    │   └── invalid-blocked.json
    ├── normalized/           # Normalized comparison artefacts
    │   ├── baseline-feasible.json
    │   ├── high-throughput-review.json
    │   └── invalid-blocked.json
    └── summary.json          # Run summary (written last)
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


def write_run_json(run_dir: Path, run_data: dict[str, Any]) -> Path:
    """Write run.json with deterministic key ordering."""
    path = run_dir / "run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, run_data)
    return path


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
    normalized: dict[str, Any],
) -> Path:
    """Write normalized comparison artefact for a scenario."""
    dir_path = run_dir / "normalized"
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"{scenario_id}.json"
    _write_json(path, normalized)
    return path


def write_summary_json(run_dir: Path, summary: dict[str, Any]) -> Path:
    """Write summary.json with deterministic key ordering."""
    path = run_dir / "summary.json"
    _write_json(path, summary)
    return path


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with consistent formatting: sorted keys, trailing newline."""
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    """Compute SHA-256 digest for a file."""
    return sha256(path.read_bytes()).hexdigest()
