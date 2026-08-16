"""CLI entrypoint for the V0.3 P1 controlled acceptance surface.

The runner is deliberately separate from the acceptance core so Stage26 can
invoke it with explicit database, source, operator, and evidence arguments.
It never dispatches workflows, writes GitHub state, or chooses an operator
implicitly from the CI actor.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _BACKEND_ROOT / "src"
for _path in (str(_SRC_ROOT), str(_BACKEND_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cold_storage.evaluation.followup_acceptance import (  # noqa: E402
    ControlledAcceptanceError,
    compare_normalized_evidence,
    run_controlled_acceptance,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="V0.3 P1 controlled acceptance runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="execute one isolated backend acceptance run")
    run.add_argument("--database-url", required=True)
    run.add_argument("--source-json", type=Path, required=True)
    run.add_argument("--operator", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--backend", choices=("sqlite", "postgresql"), required=True)
    run.add_argument("--run-index", type=int, required=True)
    run.add_argument("--artifact-root", type=Path)

    compare = subparsers.add_parser("compare", help="compare normalized run evidence")
    compare.add_argument(
        "--input", dest="inputs", action="append", nargs=2, metavar=("LABEL", "PATH"), required=True
    )
    compare.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "run":
            evidence = run_controlled_acceptance(
                database_url=args.database_url,
                source_json=args.source_json,
                operator=args.operator,
                output_root=args.artifact_root
                or args.output.parent / f"{args.backend}-{args.run_index}",
                backend=args.backend,
                run_index=args.run_index,
            )
            _write_json(args.output, evidence)
            print(json.dumps({"status": "PASS", "output": str(args.output)}, sort_keys=True))
            return 0
        if args.command == "compare":
            evidence = {
                label: json.loads(Path(path).read_text(encoding="utf-8"))
                for label, path in args.inputs
            }
            result = compare_normalized_evidence(evidence)
            _write_json(args.output, result)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["status"] == "PASS" else 1
        raise RuntimeError(f"unsupported command: {args.command}")
    except ControlledAcceptanceError as exc:
        payload = {"status": "BLOCKED", "error": exc.to_json()}
        _write_json(args.output, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
