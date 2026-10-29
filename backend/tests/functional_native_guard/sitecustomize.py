"""Test-only startup guard inherited by ordinary Python child processes."""

import json
import os
from pathlib import Path

try:
    from ortools.sat.python import cp_model

    audit = Path(os.environ["R11_FUNCTIONAL_GUARD_AUDIT"])
    audit.mkdir(parents=True, exist_ok=True)

    def record(kind: str, api: str = "") -> None:
        with (audit / f"process-{os.getpid()}.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(kind=kind, api=api, pid=os.getpid())) + "\n")

    def blocked_solve(*args: object, **kwargs: object) -> object:
        record("NATIVE_REQUEST_BLOCKED", "CpSolver.solve/Solve")
        raise RuntimeError("R11_FUNCTIONAL_NATIVE_FORBIDDEN_IN_THIS_PROCESS")

    cp_model.CpSolver.solve = blocked_solve
    cp_model.CpSolver.Solve = blocked_solve
    os.environ["R11_FUNCTIONAL_GUARD_ACTIVE"] = "1"
    record("GUARD_READY")
except Exception:
    # Python normally ignores sitecustomize errors. An unprotected child must exit.
    os._exit(86)
