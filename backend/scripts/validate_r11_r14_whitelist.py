"""R14 and prior explicit functional/architecture files, parent/child Native guard."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from validate_r11_r10_whitelist import ALLOWED, ARCHITECTURE_ALLOWED
from validate_r11_r11_whitelist import NEW_ARCHITECTURE, NEW_UNIT
from validate_r11_r12_whitelist import R12_ARCH, R12_UNIT
from validate_r11_r13_whitelist import R13_ARCH, R13_UNIT

R14_UNIT = "tests/unit/test_v222_r11_r14_ten_door_locker.py"
R14_ARCH = "tests/architecture/test_v222_r11_ten_door_locker_boundary.py"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True, type=Path)
    p.add_argument("--focused", action="store_true")
    args = p.parse_args()
    output = args.evidence.resolve()
    output.mkdir(parents=True, exist_ok=False)
    backend = Path(__file__).resolve().parents[1]
    files = [R14_UNIT, R14_ARCH]
    if not args.focused:
        files += [
            R13_UNIT,
            R13_ARCH,
            R12_UNIT,
            R12_ARCH,
            NEW_UNIT,
            NEW_ARCHITECTURE,
            *ALLOWED,
            *ARCHITECTURE_ALLOWED,
        ]
    if len(files) != len(set(files)):
        raise ValueError("UNIQUE_EXPLICIT_FUNCTIONAL_WHITELIST_REQUIRED")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        str(backend / x) for x in ("tests/functional_native_guard", "src", "scripts")
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
            f"--basetemp={output / 'pytest-temp'}",
            f"--junitxml={output / 'pytest.xml'}",
        ],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    (output / "pytest.txt").write_text(r.stdout + r.stderr)
    print(f"Explicit functional whitelist exit: {r.returncode}")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
