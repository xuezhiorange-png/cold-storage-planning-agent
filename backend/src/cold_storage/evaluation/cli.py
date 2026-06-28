"""CLI for evaluation tooling.

Entry point::

    PYTHONPATH=src uv run python -m cold_storage.evaluation.cli \\
        --manifest ../evaluation/manifest.json validate

    PYTHONPATH=src uv run python -m cold_storage.evaluation.cli \\
        --manifest ../evaluation/manifest.json run --database sqlite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cold_storage.evaluation.errors import EvaluationError


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args and dispatch to the chosen command.

    Returns exit code (0 = success, nonzero = error).
    """
    parser = argparse.ArgumentParser(
        prog="eval",
        description="Cold storage evaluation tooling — Phase B",
    )
    parser.add_argument(
        "--manifest",
        type=str,
        required=True,
        help="Path to the evaluation manifest JSON file",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate
    subparsers.add_parser(
        "validate",
        help="Strictly validate a manifest file (zero side effects)",
    )
    validate_parser = subparsers.add_parser(
        "validate-verbose",
        help="Validate and print detailed manifest info",
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

    # run (Phase B: SQLite acceptance execution)
    run_parser = subparsers.add_parser(
        "run",
        help="Run evaluation scenarios through the production pipeline",
    )
    run_parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="Database backend (only 'sqlite' supported in Phase B)",
    )
    run_parser.add_argument(
        "--evaluation-root",
        type=str,
        default=None,
        help="Override the evaluation root directory",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            return _do_validate(args)
        elif args.command == "validate-verbose":
            return _do_validate_verbose(args)
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
    """Validate manifest — zero side effects, exit code only.

    Returns 0 if valid, 1 if invalid.
    """
    from cold_storage.evaluation.manifest import load_evaluation_manifest

    manifest_path = Path(args.manifest)
    try:
        load_evaluation_manifest(manifest_path, require_referenced_files=True)
        return 0
    except EvaluationError:
        raise
    except Exception as exc:
        print(f"Manifest validation failed: {exc}", file=sys.stderr)
        return 1


def _do_validate_verbose(args: argparse.Namespace) -> int:
    """Validate manifest and print info."""
    from cold_storage.evaluation.manifest import load_evaluation_manifest

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
    import json

    from cold_storage.evaluation.manifest import load_evaluation_manifest

    manifest_path = Path(args.manifest)
    eval_root = Path(args.evaluation_root) if args.evaluation_root else None

    manifest = load_evaluation_manifest(
        manifest_path,
        evaluation_root=eval_root,
        require_referenced_files=True,
    )

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
    """Run evaluation scenarios through the production pipeline.

    The CLI only parses args and passes them to ``run_manifest()``,
    which owns the per-scenario SQLite lifecycle (each scenario gets
    its own isolated temporary database).
    """
    from cold_storage.evaluation.evaluate import run_manifest

    database_backend = "sqlite"
    if hasattr(args, "database") and args.database:
        database_backend = args.database

    eval_root = (
        Path(args.evaluation_root)
        if (hasattr(args, "evaluation_root") and args.evaluation_root)
        else None
    )

    return run_manifest(
        Path(args.manifest),
        database_backend=database_backend,
        eval_root_override=eval_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
