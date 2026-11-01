"""Standalone non-native factory concept generation; never a MAIN/Store entry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cold_storage.modules.layout.application.autonomous_factory_layout import (
    generate_autonomous_layouts,
)
from cold_storage.modules.layout.infrastructure.autonomous_layout_export import (
    export_autonomous_package,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--finished-storage-days", type=int)
    parser.add_argument("--strict-columns", action="store_true")
    parser.add_argument("--no-drawings", action="store_true")
    args = parser.parse_args()
    if os.environ.get("R11_FUNCTIONAL_GUARD_ACTIVE") != "1":
        parser.error("Native禁止防护未启用：按任务README设置继承的functional_native_guard")
    project = json.loads(args.input.read_text())
    if args.finished_storage_days is not None:
        project["business"]["finished_storage_days"] = args.finished_storage_days
    if args.strict_columns:
        project["search"]["column_policy"] = "EXCLUDE_COLUMNS_FROM_ROOMS"
    result = generate_autonomous_layouts(project, progress=print)
    export_autonomous_package(result, project, args.output, drawings=not args.no_drawings)
    print(
        json.dumps(
            {
                "status": result["status"],
                "candidate_count": result["candidate_count"],
                "result_hash": result["result_hash"],
                "output": str(args.output),
                "native_calls": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
