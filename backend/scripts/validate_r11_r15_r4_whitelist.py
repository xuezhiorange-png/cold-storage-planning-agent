"""Explicit R4-only + existing analytic/architecture tests; Native blocked in children."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from build_r11_r10_reverse_sizing_review import guarded_reexec

UNIT = "tests/unit/test_v222_r11_r15_r4_clearance.py"
ARCH = "tests/architecture/test_v222_r11_local_clearance_boundary.py"
OLD_UNIT = "tests/unit/test_v222_r11_r15_local_relayout.py"
WHITELIST = [
    UNIT,
    ARCH,
    "tests/architecture/test_v222_r11_local_relayout_boundary.py",
    "tests/architecture/test_v222_r11_ten_door_locker_boundary.py",
    OLD_UNIT + "::test_bounding_box_overlap_does_not_prevent_tighter_arc_distance",
    OLD_UNIT + "::test_certified_axes_quadrants_thickness_and_height",
    OLD_UNIT + "::test_distance_is_invariant_under_hinge_axis_mirroring",
    OLD_UNIT + "::test_unknown_hardware_geometry_is_not_silently_approximated",
    OLD_UNIT + "::test_new_tests_are_in_fast_ci_without_removing_existing_modules",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    output = args.evidence.resolve()
    code = guarded_reexec(output.parent / (output.name + "-parent-native-guard"))
    if code is not None:
        return code
    output.mkdir(parents=True, exist_ok=False)
    backend = Path(__file__).resolve().parents[1]
    if len(WHITELIST) != len(set(WHITELIST)):
        raise ValueError("EXACT_UNIQUE_R4_WHITELIST_REQUIRED")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        str(backend / p) for p in ("tests/functional_native_guard", "src", "scripts")
    )
    env["R11_FUNCTIONAL_GUARD_AUDIT"] = str(output / "native-guard")
    env["DATABASE_BACKEND"] = "sqlite"
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    command = [
        sys.executable,
        "-m",
        "pytest",
        *WHITELIST,
        "-q",
        "-o",
        "addopts=",
        f"--basetemp={output / 'pytest-temp'}",
        f"--junitxml={output / 'pytest.xml'}",
    ]
    (output / "whitelist.json").write_text(
        json.dumps(dict(files=WHITELIST, command=command, python=sys.version), indent=2) + "\n"
    )
    result = subprocess.run(
        command, cwd=backend, env=env, capture_output=True, text=True, check=False
    )
    (output / "pytest.txt").write_text(result.stdout + result.stderr)
    print(f"Explicit R15 R4 non-Native whitelist exit: {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
