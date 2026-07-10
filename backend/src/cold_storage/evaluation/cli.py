"""Evaluation CLI (Task 11B Phase B Path A — Implementation Slice A1.5).

This module provides the canonical CLI surface for the evaluation
runner. It is a thin wrapper around
:func:`cold_storage.evaluation.execute.run_scenario` and
:func:`cold_storage.evaluation.run_directory.RunDirectory.for_scenario`.

Exit-code contract
==================

The CLI returns the following exit codes (machine-readable; the CLI
MUST NOT print them as plain text on stderr — downstream automation
inspects ``$?``):

- ``0`` — the runner produced a ``SchemeRun`` with
  ``scheme_status='SUCCEEDED'``. The CLI prints the runner-side
  ``outcome`` (``SUCCEEDED``) on stdout as a single line.
- ``2`` — input contract violation (:class:`InvalidEvaluationScenarioError`).
  The CLI prints the runner-side error ``code`` on stderr.
- ``3`` — runner contract violation (:class:`EvaluationRunnerContractViolationError`).
  The CLI prints the runner-side error ``code`` on stderr.
- ``4`` — historical-blocked sentinel (:class:`PhaseBBlockedError`).
  The CLI prints the runner-side error ``code`` plus the upstream
  error code on stderr. The CLI does NOT print a generic "blocked"
  message; downstream automation must classify by ``code``.
- ``5`` — runner returned ``REVIEW_REQUIRED`` outcome. The CLI prints
  the runner-side ``outcome`` on stdout.
- ``6`` — runner returned ``FAILED`` outcome. The CLI prints the
  runner-side ``outcome`` on stdout.
- ``1`` — any other (production-side) error. The CLI prints the
  exception ``type.__name__`` on stderr. The runner does NOT wrap,
  transform, log-and-continue, or swallow production-side errors
  (pre-freeze §1.3 #1 + Path A §13.5).

Forbidden behaviors
===================

- DO NOT introduce any "blocked" exit code that fires on the happy
  path (pre-freeze §8 #12 — ``expected_outcome`` MUST NOT be
  downgraded to ``blocked``). The CLI exit code ``4`` fires ONLY
  when :class:`PhaseBBlockedError` is raised, which is reserved for
  the real production-side prerequisite failures enumerated in
  :data:`cold_storage.evaluation.execute.HISTORICAL_BLOCKED_UPSTREAM_CODES`.
- DO NOT parse exception message text to determine the exit code
  (pre-freeze §1.5 / Phase 4 §9 forbidden-pattern list).
- DO NOT restore ``production_seeding.py``.
- DO NOT bypass ``compose_production_scheme_service``.

CLI argument contract
=====================

::

    cold-storage-evaluation-run \\
        --session-factory-url <url> \\
        --source-binding-id <id> \\
        --weight-set-revision-id <id> \\
        --correlation-id <id> \\
        --database-backend <sqlite|postgresql> \\
        --scenario-id <id> \\
        [--run-root <path>] \\
        [--dry-run]

The ``--dry-run`` flag validates inputs and prints the resolved
:class:`RunDirectory` paths without opening any production session.

A future round may add additional CLI flags (e.g.,
``--profile-codes``); the pre-freeze contract §4.1 row "Runner —
cli.py" explicitly authorizes that extension. This module is
**deliberately minimal** — the contract calls for "no changes
anticipated unless CLI surface needs new flags".
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from cold_storage.evaluation.errors import (
    EvaluationRunnerContractViolationError,
    EvaluationRunnerError,
    InvalidEvaluationScenarioError,
    PhaseBBlockedError,
    is_evaluation_runner_error,
)
from cold_storage.evaluation.execute import (
    HISTORICAL_BLOCKED_UPSTREAM_CODES,
    ScenarioOutcome,
    run_scenario,
)
from cold_storage.evaluation.run_directory import (
    RunDirectory,
    _SAFE_SCENARIO_ID,
    execute_in_run_directory,
)

# Exit codes — load-bearing constants; tests assert on these names.

EXIT_SUCCEEDED: int = 0
EXIT_INVALID_INPUT: int = 2
EXIT_RUNNER_CONTRACT_VIOLATION: int = 3
EXIT_HISTORICAL_BLOCKED: int = 4
EXIT_REVIEW_REQUIRED: int = 5
EXIT_FAILED: int = 6
EXIT_PRODUCTION_ERROR: int = 1


def _print_outcome(outcome: ScenarioOutcome, *, file: Any = sys.stdout) -> None:
    """Print the runner-side outcome as a single machine-readable line.

    Format: ``<outcome> source_binding_id=<id> weight_set_revision_id=<id>
    database_backend=<backend> run_id=<id>``.

    Downstream automation parses this line by splitting on whitespace;
    human readers can read it directly. The CLI does NOT print any
    additional text on stdout — that is reserved for the ``outcome``
    encoding.
    """
    line = (
        f"{outcome.outcome} "
        f"source_binding_id={outcome.source_binding_id} "
        f"weight_set_revision_id={outcome.weight_set_revision_id} "
        f"database_backend={outcome.database_backend} "
        f"run_id={outcome.scheme_run.id}"
    )
    print(line, file=file)


def _print_error_code(
    exc: EvaluationRunnerError, *, file: Any = sys.stderr
) -> None:
    """Print the runner-side error ``code`` to stderr.

    The CLI does NOT print the exception ``str(args)`` because
    pre-freeze §1.5 forbids message-text parsing. Downstream
    automation must classify by the ``code`` attribute.
    """
    print(f"runner_error_code={exc.code}", file=file)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cold-storage-evaluation-run",
        description=(
            "Task 11B Phase B Path A evaluation runner CLI. "
            "Delegates to compose_production_scheme_service(session_factory) "
            "via the evaluation runner."
        ),
    )
    parser.add_argument(
        "--session-factory-url",
        required=True,
        help=(
            "URL of the production session factory. Currently "
            "supported: 'sqlite:///<path>' or "
            "'postgresql+psycopg2://<user>:<pwd>@<host>/<db>'. "
            "Future rounds may extend this list."
        ),
    )
    parser.add_argument(
        "--source-binding-id",
        required=True,
        help="FK reference to a pre-existing SourceBindingRecord row.",
    )
    parser.add_argument(
        "--weight-set-revision-id",
        required=True,
        help=(
            "FK reference to a pre-existing "
            "ApprovedWeightSetRevision row with status='approved'."
        ),
    )
    parser.add_argument(
        "--correlation-id",
        required=True,
        help=(
            "Mandatory NOT-NULL correlation id for the produced "
            "orchestration_run_attempts row."
        ),
    )
    parser.add_argument(
        "--database-backend",
        required=True,
        choices=("sqlite", "postgresql"),
        help=(
            "Mandatory NOT-NULL database backend marker. Must match "
            "the ck_scheme_run_database_backend check constraint."
        ),
    )
    parser.add_argument(
        "--scenario-id",
        required=True,
        help=(
            f"Evaluation scenario identifier. Must match "
            f"{_SAFE_SCENARIO_ID.pattern!r}."
        ),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("./evaluation_runs"),
        help=(
            "Root directory for per-scenario run artifacts. "
            "Defaults to ./evaluation_runs."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate inputs and print the resolved RunDirectory "
            "paths without opening any production session."
        ),
    )
    return parser


def _build_session_factory(url: str) -> Callable[[], Any]:
    """Build a session_factory callable from the given URL.

    This module does NOT import SQLAlchemy directly — the runner's
    contract is session_factory-shaped. The CLI's URL parser
    constructs a thin ``sessionmaker`` via SQLAlchemy's
    ``create_engine`` factory (the canonical Phase 4 + Path A
    pattern). The session_factory is the canonical composition root
    for :func:`compose_production_scheme_service`.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    if url.startswith("sqlite:///"):
        engine = create_engine(url)
    elif url.startswith("postgresql"):
        engine = create_engine(url)
    else:
        raise InvalidEvaluationScenarioError(
            f"Unsupported session_factory_url scheme: {url[:16]!r}...",
            details={"field": "session_factory_url", "value": url},
        )

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def session_factory() -> Any:
        return factory()

    return session_factory


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the exit code (see module docstring)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # The argparse validation surfaces contract-violation strings on
    # stderr and exits with code 2 by default — which matches our
    # EXIT_INVALID_INPUT contract. We rely on argparse's default
    # behaviour for unrecognized flags and let SystemExit propagate.
    # (We still wrap explicit input-boundary checks in
    # InvalidEvaluationScenarioError for non-argparse cases.)

    if args.dry_run:
        # Validate inputs and print the resolved RunDirectory paths.
        # This is the only CLI sub-command that does NOT open a
        # production session.
        run_dir = RunDirectory.for_scenario(
            root=args.run_root, scenario_id=args.scenario_id
        )
        print(f"run_dir_root={run_dir.root}", file=sys.stdout)
        print(f"run_dir_scenario={run_dir.scenario_dir}", file=sys.stdout)
        print(f"run_dir_raw={run_dir.raw_dir}", file=sys.stdout)
        print(f"run_dir_normalized={run_dir.normalized_dir}", file=sys.stdout)
        print(f"run_dir_summary={run_dir.summary_path}", file=sys.stdout)
        return EXIT_SUCCEEDED

    session_factory = _build_session_factory(args.session_factory_url)

    try:
        outcome = execute_in_run_directory(
            session_factory,
            source_binding_id=args.source_binding_id,
            weight_set_revision_id=args.weight_set_revision_id,
            correlation_id=args.correlation_id,
            database_backend=args.database_backend,
            scenario_id=args.scenario_id,
            run_root=args.run_root,
        )
    except PhaseBBlockedError as exc:
        _print_error_code(exc)
        return EXIT_HISTORICAL_BLOCKED
    except InvalidEvaluationScenarioError as exc:
        _print_error_code(exc)
        return EXIT_INVALID_INPUT
    except EvaluationRunnerContractViolationError as exc:
        _print_error_code(exc)
        return EXIT_RUNNER_CONTRACT_VIOLATION
    except EvaluationRunnerError as exc:
        # Catch-all for any other runner-typed error (forwarding-
        # unchanged is the contract; the CLI surfaces the typed
        # code and returns EXIT_PRODUCTION_ERROR).
        _print_error_code(exc)
        return EXIT_PRODUCTION_ERROR
    except Exception as exc:
        # Production-side error: print the typed error ``code`` if
        # available; otherwise print the exception ``type.__name__``.
        # NEVER print the exception ``str(args)`` for downstream
        # classification (forbidden-pattern list).
        if isinstance(exc, EvaluationRunnerError):
            _print_error_code(exc)
        else:
            upstream_code = getattr(exc, "code", None)
            if isinstance(upstream_code, str) and upstream_code:
                print(f"runner_error_code={upstream_code}", file=sys.stderr)
            else:
                print(f"runner_error_code={type(exc).__name__}", file=sys.stderr)
        return EXIT_PRODUCTION_ERROR

    _print_outcome(outcome)
    if outcome.outcome == "SUCCEEDED":
        return EXIT_SUCCEEDED
    if outcome.outcome == "REVIEW_REQUIRED":
        return EXIT_REVIEW_REQUIRED
    if outcome.outcome == "FAILED":
        return EXIT_FAILED
    # BLOCKED_HISTORICAL is a sentinel value the runner can emit in
    # the ``outcome`` field when the production service returns a
    # FAILED SchemeRun whose failure code is in
    # HISTORICAL_BLOCKED_UPSTREAM_CODES. The CLI distinguishes it
    # from a generic FAILED outcome by treating it as the same as
    # EXIT_HISTORICAL_BLOCKED. This branch is defensive — the runner
    # currently maps historical-blocked upstream codes to
    # ``PhaseBBlockedError`` (raised, not returned) and only maps
    # ``FAILED``/``REVIEW_REQUIRED``/``SUCCEEDED`` to the outcome
    # field.
    if outcome.outcome == "BLOCKED_HISTORICAL":
        return EXIT_HISTORICAL_BLOCKED
    return EXIT_PRODUCTION_ERROR


def _exit(code: int, message: str) -> NoReturn:
    """Test-side helper: print ``message`` to stderr and exit with ``code``."""
    print(message, file=sys.stderr)
    raise SystemExit(code)


__all__ = [
    "EXIT_SUCCEEDED",
    "EXIT_INVALID_INPUT",
    "EXIT_RUNNER_CONTRACT_VIOLATION",
    "EXIT_HISTORICAL_BLOCKED",
    "EXIT_REVIEW_REQUIRED",
    "EXIT_FAILED",
    "EXIT_PRODUCTION_ERROR",
    "HISTORICAL_BLOCKED_UPSTREAM_CODES",
    "ScenarioOutcome",
    "main",
]


if __name__ == "__main__":  # pragma: no cover (CLI entry point)
    raise SystemExit(main())