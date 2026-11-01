"""Guarded standalone non-Native process-continuity preview, never MAIN."""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

from cold_storage.modules.layout.application.autonomous_process_continuity import (
    generate_process_layout,
)
from cold_storage.modules.layout.infrastructure.process_continuity_export import (
    export_process_package,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--parameters", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--finished-storage-days", type=int)
    p.add_argument("--no-drawings", action="store_true")
    a = p.parse_args()
    if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
        p.error("Requires inherited functional_native_guard")
    if a.output.exists():
        p.error("Output must not exist; preserve previous evidence")
    project = json.loads(a.input.read_text())
    parameters = json.loads(a.parameters.read_text())
    if a.finished_storage_days is not None:
        project["business"]["finished_storage_days"] = a.finished_storage_days
    start = time.monotonic()
    result = generate_process_layout(project, parameters, progress=print)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    resources = {
        "elapsed_generation_seconds": time.monotonic() - start,
        "rss_peak_mib": usage.ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024),
        "native_calls": 0,
        "guard_inherited": True,
        "resource_scope": "Standalone deterministic preview; no Stage A/B budget issued or reused",
        "room_options_checked": sum(
            a["search"]["options_checked"]
            for run in result.get("room_search_runs", [])
            for a in run["attempts"]
        ),
        "room_search_nodes": sum(
            a["search"]["nodes_used"]
            for run in result.get("room_search_runs", [])
            for a in run["attempts"]
        ),
        "model_clone_count": 0,
    }
    export_process_package(result, project, parameters, a.output, drawings=not a.no_drawings)
    (a.output / "execution-resource-usage.json").write_text(json.dumps(resources, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "result_hash": result.get("result_hash"),
                "output": str(a.output),
            }
        )
    )


if __name__ == "__main__":
    main()
