"""Explicit guarded non-Native joint-layout preview, never MAIN or Store."""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

from cold_storage.modules.layout.application.functional_autonomous_layout import (
    generate_functional_layout,
)
from cold_storage.modules.layout.infrastructure.functional_layout_export import (
    export_functional_package,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--finished-storage-days", type=int)
    p.add_argument("--no-drawings", action="store_true")
    a = p.parse_args()
    if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
        p.error("Requires inherited functional_native_guard")
    if a.output.exists():
        p.error("Output must not exist; preserve earlier evidence")
    project = json.loads(a.input.read_text())
    if a.finished_storage_days is not None:
        project["business"]["finished_storage_days"] = a.finished_storage_days
    started = time.monotonic()
    result = generate_functional_layout(project, progress=print)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    run = {
        "elapsed_generation_seconds": time.monotonic() - started,
        "rss_peak_mib": usage.ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024),
        "native_calls": 0,
        "resource_scope": (
            "Standalone deterministic preview, not Stage A/B ledger; no budget issued or reused"
        ),
        "operations": {
            "room_options_checked": sum(x["search"]["options_checked"] for x in result["attempts"]),
            "room_search_nodes": sum(x["search"]["nodes_used"] for x in result["attempts"]),
        },
    }
    export_functional_package(result, project, a.output, drawings=not a.no_drawings)
    (a.output / "execution-resource-usage.json").write_text(json.dumps(run, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "result_hash": result["result_hash"],
                "output": str(a.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
