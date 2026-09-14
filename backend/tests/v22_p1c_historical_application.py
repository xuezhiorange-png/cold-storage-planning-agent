"""Immutable pre-P1D1 application/graph; historical counts are not current defaults."""

import subprocess
import sys
import types
from pathlib import Path

BASE = "4f8c3a0c3b8e866695a917990588caffdd60defc"
ROOT = Path(__file__).resolve().parents[2]


def historical_module(relative: str, name: str) -> types.ModuleType:
    path = "backend/src/cold_storage/modules/layout/" + relative
    source = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT, text=True)
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, f"{BASE}:{path}", "exec"), module.__dict__)
    return module


graph = historical_module("domain/adjacency.py", "tests._immutable_p1c_adjacency")
application = historical_module(
    "application/dimension_zones.py", "tests._immutable_p1c_application"
)
application.process_graph = graph.process_graph
dimension_zones = application.dimension_zones
process_graph = graph.process_graph
