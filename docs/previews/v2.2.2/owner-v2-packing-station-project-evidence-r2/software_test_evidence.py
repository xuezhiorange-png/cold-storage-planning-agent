"""Synthetic test fixture builder. NEVER evidence for actual project admission."""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from typing import Any

import offline_project_input_adapter as adapter


def fixture(
    root: Path, arrangement: str = "SINGLE"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    adapter.load_r1()
    spec = importlib.util.spec_from_file_location(
        "r2_readonly_r1_example", adapter.R1 / "build_examples.py"
    )
    assert spec and spec.loader
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    module = example.example(arrangement)  # In-memory synthetic function, NOT build().
    module.update(MODE="OWNER_PROJECT", PROJECT_ID="SOFTWARE_TEST_ONLY", SOURCES={})
    records = []
    callouts = {}
    template = deepcopy(module)
    for i, target in enumerate(adapter.numeric_slots(module)):
        key = f"D{i:04d}"
        kind, frame = adapter.target_semantics(module, target)
        value = adapter.pointer_get(module, target)
        unit = "deg" if kind == "ORIENTATION_ANGLE" else "mm"
        callouts[key] = {
            "VALUE": value,
            "UNIT": unit,
            "DIMENSION_TYPE": kind,
            "COORDINATE_REFERENCE": frame,
        }
        records.append(
            {
                "RECORD_ID": key,
                "VALUE": value,
                "UNIT": unit,
                "SOURCE_ID": "TEST-DOC",
                "SOURCE_LOCATION": {"FORMAT": "JSON", "JSON_POINTER": "/dimensions/" + key},
                "DIMENSION_TYPE": kind,
                "COORDINATE_REFERENCE": frame,
                "EXTRACTION_METHOD": "EXPLICIT_STRUCTURED_CALLOUT",
                "TARGET_PATH": target,
                "MEASUREMENT": "ANGLE" if unit == "deg" else "COORDINATE",
            }
        )
        adapter.pointer_set(template, target, None)
    for component in module["COMPONENTS"]:
        if component["ROLE"] != "BODY":
            continue
        x, y, u, v = component["GEOMETRY"]["BOUNDS_MM"]
        for name, value in (("LENGTH", u - x), ("WIDTH", v - y), ("HEIGHT", 800)):
            key = "BODY-" + component["COMPONENT_ID"] + "-" + name
            callouts[key] = {
                "VALUE": value,
                "UNIT": "mm",
                "DIMENSION_TYPE": "EQUIPMENT_BODY_DIMENSION",
                "COORDINATE_REFERENCE": "STATION_LOCAL",
            }
            records.append(
                {
                    "RECORD_ID": key,
                    **callouts[key],
                    "SOURCE_ID": "TEST-DOC",
                    "SOURCE_LOCATION": {"FORMAT": "JSON", "JSON_POINTER": "/dimensions/" + key},
                    "EXTRACTION_METHOD": "EXPLICIT_STRUCTURED_CALLOUT",
                    "TARGET_PATH": None,
                    "MEASUREMENT": name,
                    "COMPONENT_ID": component["COMPONENT_ID"],
                }
            )
    structure = {
        "SOURCE_ID": "TEST-DOC",
        "SOURCE_LOCATION": {"FORMAT": "JSON", "JSON_POINTER": "/module_template"},
    }
    document = {
        "PURPOSE": "SOFTWARE_TEST_ONLY",
        "module_template": template,
        "dimensions": callouts,
    }
    meta: dict[str, Any] = {key: "TEST_ONLY_" + key for key in adapter.META}
    meta.update(
        PROJECT_ID="SOFTWARE_TEST_ONLY",
        FACTORY_ID="TEST_FACTORY",
        SOURCE_ID="TEST-DOC",
        SOURCE_PATH_OR_URL="test-source.json",
        SOURCE_TYPE="PROJECT_CANDIDATE_EQUIPMENT",
        SOURCE_FILE_SHA256="",
        APPROVAL_EVIDENCE=None,
        SELECTION_STATUS="NOT_SELECTED",
    )
    request = {
        "IDENTITY": adapter.IDENTITY,
        "VERSION": adapter.VERSION,
        "PROJECT_ID": "SOFTWARE_TEST_ONLY",
        "FACTORY_ID": "TEST_FACTORY",
        "DOCUMENTS": [meta],
        "DIMENSIONS": records,
        "MODULE_TEMPLATE": template,
        "STRUCTURAL_EVIDENCE": structure,
    }
    register = {
        "IDENTITY": "LocalStationEvidenceReviewRegisterV1",
        "SCOPE": "SOFTWARE_TEST_ONLY",
        "PROJECT_ID": request["PROJECT_ID"],
        "FACTORY_ID": request["FACTORY_ID"],
        "SOURCES": {},
        "DENIED_SOURCE_HASHES": [],
    }
    resign(root, request, document, register)
    return request, document, register


def resign(
    root: Path, request: dict[str, Any], document: dict[str, Any], register: dict[str, Any]
) -> adapter.ReviewContext:
    """Only for deliberate synthetic-case creation; not a real review/register issuer."""
    assert register["SCOPE"] == "SOFTWARE_TEST_ONLY"
    root.mkdir(parents=True, exist_ok=True)
    raw = adapter.encode(document)
    (root / "test-source.json").write_bytes(raw)
    meta = request["DOCUMENTS"][0]
    meta["SOURCE_FILE_SHA256"] = adapter.sha(raw)
    register["SOURCES"]["TEST-DOC"] = {
        "SOURCE_FILE_SHA256": adapter.sha(raw),
        "METADATA_SHA256": adapter.sha(adapter.encode(meta)),
        "FORMAT": "JSON",
        "REVIEW_KIND": "EXTRACTION_CHECKED_NOT_ENGINEERING_APPROVAL",
        "REVIEW_RECORD_ID": "SOFTWARE_TEST_REVIEW",
        "REVIEWER_ID": "SOFTWARE_TEST_REVIEWER",
        "STRUCTURAL_RECORD_SHA256": adapter.sha(adapter.encode(request["STRUCTURAL_EVIDENCE"])),
        "DIMENSION_RECORD_HASHES": {
            r["RECORD_ID"]: adapter.sha(adapter.encode(r)) for r in request["DIMENSIONS"]
        },
    }
    return adapter.ReviewContext(adapter.encode(register))
