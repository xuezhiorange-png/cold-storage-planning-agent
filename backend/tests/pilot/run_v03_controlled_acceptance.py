"""CLI entrypoint for the V0.3 P5 controlled acceptance harness.

The runner validates explicit authorization and source-identity gates, then fails
closed before any Scenario A/B/C planning run. It never dispatches workflows,
creates tags/releases, or infers operators from CI actors.
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

from cold_storage.evaluation.v03_controlled_acceptance import (  # noqa: E402
    V03ControlledAcceptanceError,
    build_harness_status,
    execution_authorized_from_env,
    refuse_scenario_execution,
    verify_harness_gates,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="V0.3 P5 controlled acceptance harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("harness-status", help="emit frozen harness authorization posture")
    status.add_argument("--output", type=Path)

    verify = subparsers.add_parser("verify-gates", help="verify harness gates without scenario execution")
    verify.add_argument("--authorization-record-id", required=True)
    verify.add_argument("--trusted-operator", required=True)
    verify.add_argument("--execution-source-sha", required=True)
    verify.add_argument("--execution-source-tree-sha", required=True)
    verify.add_argument("--event-name")
    verify.add_argument("--git-ref")
    verify.add_argument("--checked-out-sha")
    verify.add_argument("--checked-out-tree-sha")
    verify.add_argument("--output", type=Path)

    run = subparsers.add_parser("run", help="attempt one scenario after explicit authorization gates")
    run.add_argument("--scenario", choices=("A", "B", "C"), required=True)
    run.add_argument("--authorization-record-id", required=True)
    run.add_argument("--trusted-operator", required=True)
    run.add_argument("--execution-source-sha", required=True)
    run.add_argument("--execution-source-tree-sha", required=True)
    run.add_argument("--backend", choices=("sqlite", "postgresql"), required=True)
    run.add_argument("--run-index", type=int, required=True)
    run.add_argument(
        "--execution-authorized",
        action="store_true",
        help="explicit opt-in; still fails closed in harness R1",
    )
    run.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "harness-status":
            payload = build_harness_status()
            if args.output is not None:
                _write_json(args.output, payload)
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 0

        if args.command == "verify-gates":
            payload = verify_harness_gates(
                authorization_record_id=args.authorization_record_id,
                trusted_operator=args.trusted_operator,
                execution_source_sha=args.execution_source_sha,
                execution_source_tree_sha=args.execution_source_tree_sha,
                event_name=args.event_name,
                git_ref=args.git_ref,
                checked_out_sha=args.checked_out_sha,
                checked_out_tree_sha=args.checked_out_tree_sha,
            )
            if args.output is not None:
                _write_json(args.output, payload)
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 0

        if args.command == "run":
            execution_authorized = args.execution_authorized or execution_authorized_from_env()
            refuse_scenario_execution(
                scenario=args.scenario,
                authorization_record_id=args.authorization_record_id,
                trusted_operator=args.trusted_operator,
                execution_source_sha=args.execution_source_sha,
                execution_source_tree_sha=args.execution_source_tree_sha,
                execution_authorized=execution_authorized,
                backend=args.backend,
                run_index=args.run_index,
            )
            raise RuntimeError("scenario execution must fail closed in harness R1")
    except V03ControlledAcceptanceError as exc:
        payload = {"status": "BLOCKED", "error": exc.to_json()}
        output = getattr(args, "output", None)
        if output is not None:
            _write_json(output, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
