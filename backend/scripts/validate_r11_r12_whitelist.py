"""Explicit functional/architecture whitelist; inherit the existing child guard."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from validate_r11_r10_whitelist import ALLOWED, ARCHITECTURE_ALLOWED
from validate_r11_r11_whitelist import NEW_ARCHITECTURE, NEW_UNIT

R12_UNIT = "tests/unit/test_v222_r11_r12_site_impact.py"
R12_ARCH = "tests/architecture/test_v222_r11_site_impact_boundary.py"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--focused", action="store_true")
    args = p.parse_args()
    backend = Path(__file__).resolve().parents[1]
    output = args.evidence.resolve()
    output.mkdir(parents=True, exist_ok=False)
    files = [R12_UNIT, R12_ARCH]
    if not args.focused:
        files += [NEW_UNIT, NEW_ARCHITECTURE, *ALLOWED, *ARCHITECTURE_ALLOWED]
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
    r = subprocess.run(
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
    (output / "pytest.txt").write_text(r.stdout + r.stderr)
    print(f"Functional whitelist exit: {r.returncode}")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
