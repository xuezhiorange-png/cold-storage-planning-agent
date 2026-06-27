"""CLI skeleton for evaluation tooling."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cold_storage.evaluation.errors import (
    CommandNotImplementedError,
    EvaluationError,
)
from cold_storage.evaluation.manifest import load_evaluation_manifest


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args and dispatch to the chosen command.

    Returns exit code (0 = success, nonzero = error).
    """
    parser = argparse.ArgumentParser(
        prog="eval",
        description="Cold storage evaluation tooling — Phase A",
    )
    parser.add_argument(
        "--manifest",
        type=str,
        required=True,
        help="Path to the evaluation manifest JSON file",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate
    validate_parser = subparsers.add_parser(
        "validate",
        help="Strictly validate a manifest file",
    )
    validate_parser.add_argument(
        "--evaluation-root",
        type=str,
        default=None,
        help="Override the evaluation root directory",
    )

    # inspect
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Print a stable JSON summary of the manifest",
    )
    inspect_parser.add_argument(
        "--evaluation-root",
        type=str,
        default=None,
        help="Override the evaluation root directory",
    )

    # run (not implemented)
    subparsers.add_parser(
        "run",
        help="Run an evaluation scenario (not implemented in Phase A)",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            return _do_validate(args)
        elif args.command == "inspect":
            return _do_inspect(args)
        elif args.command == "run":
            return _do_run(args)
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1
    except EvaluationError as exc:
        print(f"[{exc.code}] {exc.message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _do_validate(args: argparse.Namespace) -> int:
    """Validate manifest using the authoritative single pipeline.

    Routes through ``load_evaluation_manifest()`` which runs all
    validation in the correct order (preflight → JSON Schema →
    semantic → path safety → model conversion), preserving stable
    error codes.
    """
    manifest_path = Path(args.manifest)
    eval_root = Path(args.evaluation_root) if args.evaluation_root else None

    manifest = load_evaluation_manifest(
        manifest_path,
        evaluation_root=eval_root,
        require_referenced_files=True,
    )

    scenario_ids = [s.scenario_id for s in manifest.scenarios]
    print(f"Manifest valid: {manifest.suite_id} rev {manifest.suite_revision}")
    print(f"  Scenarios: {len(manifest.scenarios)}")
    for sid in scenario_ids:
        print(f"    - {sid}")
    return 0


def _do_inspect(args: argparse.Namespace) -> int:
    """Print stable JSON summary of the manifest."""
    manifest_path = Path(args.manifest)
    eval_root = Path(args.evaluation_root) if args.evaluation_root else None

    manifest = load_evaluation_manifest(
        manifest_path,
        evaluation_root=eval_root,
        require_referenced_files=True,
    )

    import json

    summary = {
        "schema_version": manifest.schema_version,
        "suite_id": manifest.suite_id,
        "suite_revision": manifest.suite_revision,
        "scenario_count": len(manifest.scenarios),
        "scenario_ids": [s.scenario_id for s in manifest.scenarios],
    }
    json.dump(summary, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _do_run(args: argparse.Namespace) -> int:
    """Stub for the run command."""
    raise CommandNotImplementedError(
        code="EVAL_COMMAND_NOT_IMPLEMENTED",
        message="The 'run' command is not implemented in Phase A",
    )


if __name__ == "__main__":
    raise SystemExit(main())
