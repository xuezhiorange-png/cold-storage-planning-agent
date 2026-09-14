"""Replay the immutable pre-sorting application profile set, not current defaults.

PR #273 merge is the historical six-zone authority. Generic domain invariants
still run against current domain code; new production integration has its own tests.
"""

import subprocess
import sys
import types
from pathlib import Path

from tests.v22_p1c_historical_application import process_graph

BASE = "7785e877461a2c82980ed4e318bd04eabc0287df"
ROOT = Path(__file__).resolve().parents[2]
PATH = "backend/src/cold_storage/modules/layout/application/dimension_zones.py"
source = subprocess.check_output(["git", "show", f"{BASE}:{PATH}"], cwd=ROOT, text=True)
module = types.ModuleType("tests._immutable_p1c0_application")
sys.modules[module.__name__] = module
exec(compile(source, f"{BASE}:{PATH}", "exec"), module.__dict__)
module.process_graph = process_graph
dimension_zones = module.dimension_zones
