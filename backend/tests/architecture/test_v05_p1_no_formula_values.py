"""Architecture guard: V0.5 P1 package must not embed engineering formula values."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
P1_PACKAGE = REPO_ROOT / "backend/src/cold_storage/modules/projects/application"

_ENGINEERING_VALUE_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
)

P1_FILES = (
    P1_PACKAGE / "engineering_input_bundle.py",
    P1_PACKAGE / "five_stage_execution.py",
)


def test_v05_p1_package_contains_no_engineering_formula_literals() -> None:
    for path in P1_FILES:
        content = path.read_text(encoding="utf-8")
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering formula literal pattern {pattern.pattern!r} "
                f"found in {path.relative_to(REPO_ROOT)}: {match.group()!r}"
                if match
                else ""
            )
