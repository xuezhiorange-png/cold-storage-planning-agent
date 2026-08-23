"""CLI entrypoint for the V0.3 P5 controlled acceptance harness.

The runner validates explicit authorization and source-identity gates, then
either fails closed or executes the bound Scenario A/B/C fixture through
existing persisted production application services. It never dispatches
workflows, creates tags/releases, or infers operators from CI actors.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _BACKEND_ROOT / "src"
_REPO_ROOT = _BACKEND_ROOT.parent
for _path in (str(_SRC_ROOT), str(_BACKEND_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cold_storage.evaluation.v03_controlled_acceptance import (  # noqa: E402
    ScenarioAExecutionBinding,
    ScenarioExecutionSupport,
    V03ControlledAcceptanceError,
    build_harness_status,
    execute_scenario,
    execution_authorized_from_env,
    refuse_scenario_execution,
    verify_harness_gates,
)
from cold_storage.evaluation.followup_acceptance import ControlledSourceRuntime  # noqa: E402

SQLITE_URL_SCHEME = "sqlite:///"
SQLITE_ALEMBIC_TIMEOUT_SECONDS = 180
_SCENARIO_B_SOURCE_CANDIDATE_PATH = (
    "backend/src/cold_storage/bootstrap/s6_07_controlled_fixture.py::_EXECUTION_SNAPSHOT"
)


def _build_scenario_execution_support() -> ScenarioExecutionSupport:
    from cold_storage.bootstrap.s6_07_controlled_fixture import (  # noqa: PLC0415
        _EXECUTION_SNAPSHOT,
        create_controlled_coefficient_definition,
        create_controlled_production_authority,
        seed_startup_readiness,
    )
    from tests.evaluation._seed_helpers import (  # noqa: PLC0415
        SOURCE_BINDING_ID,
        WEIGHT_REVISION_ID,
        seed_a1_all_prereqs,
    )

    return ScenarioExecutionSupport(
        scenario_a=ScenarioAExecutionBinding(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            seed_prereqs=seed_a1_all_prereqs,
        ),
        scenario_b_source_runtime=ControlledSourceRuntime(
            source_candidate_path=_SCENARIO_B_SOURCE_CANDIDATE_PATH,
            source_snapshot=_EXECUTION_SNAPSHOT,
            seed_startup_readiness=seed_startup_readiness,
            create_controlled_coefficient_definition=create_controlled_coefficient_definition,
            create_controlled_production_authority=create_controlled_production_authority,
        ),
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _provision_sqlite_database(database_url: str) -> str:
    if not database_url.startswith(SQLITE_URL_SCHEME):
        raise V03ControlledAcceptanceError(
            "DATABASE_URL_INVALID",
            "sqlite backend requires a sqlite:///<path> database URL",
            database_url=database_url,
        )
    sqlite_path = database_url[len(SQLITE_URL_SCHEME) :]
    if not sqlite_path:
        raise V03ControlledAcceptanceError(
            "DATABASE_URL_INVALID",
            "sqlite database URL is missing the file path component",
        )
    db_path = Path(sqlite_path).resolve(strict=False)
    if db_path.exists():
        raise V03ControlledAcceptanceError(
            "DATABASE_URL_INVALID",
            "sqlite database file already exists; fresh isolated DB required",
            database_path=str(db_path),
        )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = "sqlite"
    env.pop("DATABASE_URL", None)
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts = [str(_SRC_ROOT)] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=SQLITE_ALEMBIC_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise V03ControlledAcceptanceError(
            "SCHEMA_NOT_READY",
            "alembic upgrade head failed for sqlite acceptance database",
            stderr_tail=proc.stderr[-2000:],
        )
    return database_url


def _resolve_database_url(*, backend: str, database_url: str | None) -> str:
    if database_url:
        return database_url
    if backend == "sqlite":
        fd, path = tempfile.mkstemp(prefix="v03-p5-", suffix=".db")
        os.close(fd)
        os.unlink(path)
        return _provision_sqlite_database(f"{SQLITE_URL_SCHEME}{path}")
    raise V03ControlledAcceptanceError(
        "DATABASE_URL_REQUIRED",
        "postgresql scenario execution requires an explicit --database-url",
        backend=backend,
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
    run.add_argument("--database-url")
    run.add_argument("--artifact-root", type=Path)
    run.add_argument(
        "--execution-authorized",
        action="store_true",
        help="explicit opt-in required for scenario execution",
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
            if not execution_authorized:
                refuse_scenario_execution(
                    scenario=args.scenario,
                    authorization_record_id=args.authorization_record_id,
                    trusted_operator=args.trusted_operator,
                    execution_source_sha=args.execution_source_sha,
                    execution_source_tree_sha=args.execution_source_tree_sha,
                    execution_authorized=False,
                    backend=args.backend,
                    run_index=args.run_index,
                )
                raise RuntimeError("scenario execution must fail closed without authorization")
            database_url = _resolve_database_url(
                backend=args.backend,
                database_url=args.database_url,
            )
            output_root = args.artifact_root or args.output.parent / f"{args.backend}-{args.run_index}"
            payload = execute_scenario(
                scenario=args.scenario,
                authorization_record_id=args.authorization_record_id,
                trusted_operator=args.trusted_operator,
                execution_source_sha=args.execution_source_sha,
                execution_source_tree_sha=args.execution_source_tree_sha,
                execution_authorized=True,
                backend=args.backend,
                run_index=args.run_index,
                database_url=database_url,
                output_root=output_root,
                repo_root=_REPO_ROOT,
                execution_support=_build_scenario_execution_support(),
            )
            _write_json(args.output, payload)
            print(json.dumps({"status": "PASS", "output": str(args.output)}, sort_keys=True))
            return 0
    except V03ControlledAcceptanceError as exc:
        payload = {"status": "BLOCKED", "error": exc.to_json()}
        output = getattr(args, "output", None)
        if output is not None:
            _write_json(output, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "_build_scenario_execution_support",
    "_provision_sqlite_database",
    "_resolve_database_url",
    "main",
]
