"""Explicit R11 functional/architecture regression under the inherited child guard."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from validate_r11_r10_whitelist import ALLOWED, ARCHITECTURE_ALLOWED

NEW_UNIT = "tests/unit/test_v222_r11_r11_sizing_advisory.py"
NEW_ARCHITECTURE = "tests/architecture/test_v222_r11_sizing_advisory_boundary.py"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--focused", action="store_true")
    args = p.parse_args()
    backend = Path(__file__).resolve().parents[1]
    output = args.evidence.resolve()
    output.mkdir(parents=True, exist_ok=False)
    files = [NEW_UNIT, NEW_ARCHITECTURE]
    if not args.focused:
        files += list(ALLOWED) + list(ARCHITECTURE_ALLOWED)
    if len(set(files)) != len(files):
        raise ValueError("UNIQUE_EXPLICIT_FUNCTIONAL_WHITELIST_REQUIRED")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        str(backend / path) for path in ("tests/functional_native_guard", "src", "scripts")
    )
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["R11_FUNCTIONAL_GUARD_AUDIT"] = str(output / "native-guard")
    env["DATABASE_BACKEND"] = "sqlite"
    (output / "whitelist.json").write_text(json.dumps(files, indent=2) + "\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *files,
            "-q",
            "-o",
            "addopts=",
            f"--junitxml={output / 'pytest.xml'}",
        ],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    (output / "pytest.txt").write_text(result.stdout + result.stderr)
    print(f"Functional whitelist exit: {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
