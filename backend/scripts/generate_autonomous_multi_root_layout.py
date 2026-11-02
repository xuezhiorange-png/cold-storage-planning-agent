"""Explicit opt-in multi-root deterministic generator, never a MAIN Runner."""

from __future__ import annotations

import argparse
import copy
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.autonomous_multi_root_layout import (
    generate_multi_root_layout,
)
from cold_storage.modules.layout.infrastructure.multi_root_layout_export import (
    export_multi_root_suite,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--search-configuration", type=Path, required=True)
    parser.add_argument("--finished-storage-days", nargs="+", type=int, default=[7, 8])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-drawings", action="store_true")
    args = parser.parse_args()
    if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
        parser.error("Requires inherited functional_native_guard in parent and children")
    if args.output.exists():
        parser.error("Output must not exist; previous evidence is never overwritten")
    if len(set(args.finished_storage_days)) != len(args.finished_storage_days):
        parser.error("Duplicate business cases are not independent candidates")
    project = json.loads(args.input.read_text())
    parameters = json.loads(args.parameters.read_text())
    config = json.loads(args.search_configuration.read_text())
    cases: list[dict[str, Any]] = []
    for days in args.finished_storage_days:
        current = copy.deepcopy(project)
        current["business"]["finished_storage_days"] = days
        start = time.monotonic()
        result = generate_multi_root_layout(
            current, parameters, config, progress=lambda message: print(message, flush=True)
        )
        usage = resource.getrusage(resource.RUSAGE_SELF)
        cases.append(
            {
                "project": current,
                "result": result,
                "resources": {
                    "elapsed_generation_seconds": time.monotonic() - start,
                    "process_lifetime_peak_rss_mib": usage.ru_maxrss
                    / (1024 * 1024 if sys.platform == "darwin" else 1024),
                    "native_calls": 0,
                    "native_guard_active": True,
                    "stage_a_b_budget_issued": False,
                    "model_copies": 0,
                },
            }
        )
        print(
            json.dumps(
                {
                    "days": days,
                    "status": result["status"],
                    "candidates": result["candidate_count"],
                    "organisations": result["organisation_count"],
                }
            ),
            flush=True,
        )
    export_multi_root_suite(cases, parameters, args.output, drawings=not args.no_drawings)
    print(json.dumps({"output": str(args.output), "native_calls": 0}))


if __name__ == "__main__":
    main()
