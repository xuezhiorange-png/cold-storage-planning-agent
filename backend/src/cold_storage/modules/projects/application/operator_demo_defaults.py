"""Load operator demo five KEY from the v09 process-input sample.

This module does not run calculators. Demo coefficients stay
``source_type=demo``, ``validity_status=unverified``, ``requires_review=true``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_PROCESS_SCHEMA_ID,
    OPERATOR_PROCESS_SCHEMA_VERSION_V09,
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

OPERATOR_DEMO_SAMPLE_ID = "v09-process-input"
OPERATOR_DEMO_SOURCE = f"samples/{OPERATOR_DEMO_SAMPLE_ID}/manifest.json"


def operator_demo_manifest_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "samples" / OPERATOR_DEMO_SAMPLE_ID / "manifest.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(OPERATOR_DEMO_SOURCE)


def load_operator_demo_process_input() -> dict[str, Any]:
    """Return the frozen v09 operator demo payload with honesty markers."""
    manifest = json.loads(operator_demo_manifest_path().read_text(encoding="utf-8"))
    operator_input = manifest.get("operator_process_input")
    if not isinstance(operator_input, dict):
        raise ValueError("v09 manifest is missing operator_process_input")
    zone_inputs = operator_input.get("zone_planning_inputs")
    if not isinstance(zone_inputs, dict):
        raise ValueError("v09 manifest is missing zone_planning_inputs")
    for field_name in OPERATOR_V09_FIVE_KEY_FIELDS:
        if field_name not in zone_inputs:
            raise ValueError(f"v09 manifest is missing {field_name}")
    return {
        "schema_id": str(operator_input.get("schema_id") or OPERATOR_PROCESS_SCHEMA_ID),
        "schema_version": str(
            operator_input.get("schema_version") or OPERATOR_PROCESS_SCHEMA_VERSION_V09
        ),
        "source": OPERATOR_DEMO_SOURCE,
        "source_type": "demo",
        "validity_status": "unverified",
        "requires_review": True,
        "zone_planning_inputs": zone_inputs,
    }
