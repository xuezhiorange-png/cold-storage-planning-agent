"""Trusted local launcher; never a public API, selection service or P1 authority."""

from __future__ import annotations

import argparse
import json
import textwrap
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import offline_project_input_adapter as adapter


def warning_svg(raw: bytes, result: dict[str, Any]) -> bytes:
    """Append visible review labels without changing R1 geometry coordinates."""
    root = ET.fromstring(raw)
    ns = "{http://www.w3.org/2000/svg}"
    ET.register_namespace("", ns[1:-1])
    if result["PROJECT_GEOMETRY_DIAGNOSTIC"] == "NOT_EXECUTED_MISSING_OR_REJECTED_EVIDENCE":
        for node in root.iter(ns + "text"):
            if node.attrib.get("y") == "125":
                node.text = (
                    "PROJECT INPUT BLOCKED: source documents and reviewed dimensions required"
                )
    text = ET.SubElement(
        root,
        ns + "text",
        {
            "x": "24",
            "y": "170" if root.attrib.get("height") == "180" else "105",
            "font-size": "13",
            "fill": "#8f241b",
        },
    )
    text.text = "ENGINEERING_REVIEW_REQUIRED | NOT_P1_AUTHORITY"
    metadata = result.get("DOCUMENT_METADATA", [])
    if metadata:
        labels = ["Project: " + str(result["PROJECT_ID"]) + " | source-bound unapproved diagnostic"]
        for meta in metadata:
            labels.extend(
                textwrap.wrap(
                    "Source "
                    + meta["SOURCE_ID"]
                    + " | "
                    + meta["MANUFACTURER"]
                    + " / "
                    + meta["MODEL"]
                    + " | drawing "
                    + meta["DRAWING_NUMBER"]
                    + " rev "
                    + meta["DOCUMENT_REVISION"]
                    + " | page "
                    + meta["SHEET_OR_PAGE"]
                    + " | SHA256 "
                    + meta["SOURCE_FILE_SHA256"],
                    width=100,
                )
            )
        height = Fraction(root.attrib["height"])
        first = (height.numerator + height.denominator - 1) // height.denominator + 20
        for i, label in enumerate(labels):
            node = ET.SubElement(
                root, ns + "text", {"x": "24", "y": str(first + i * 18), "font-size": "11"}
            )
            node.text = label
        new_height = first + len(labels) * 18
        root.set("height", str(new_height))
        viewbox = root.attrib["viewBox"].split()
        viewbox[-1] = str(new_height)
        root.set("viewBox", " ".join(viewbox))
    return bytes(ET.tostring(root, encoding="utf-8")) + b"\n"


def diagnose(
    request: dict[str, Any], context: adapter.ReviewContext, source_root: Path, output: Path
) -> dict[str, Any]:
    """Write only to a fresh caller-controlled local evidence destination."""
    adapter.require(not output.exists(), "FRESH_OUTPUT_DIRECTORY_REQUIRED")
    output.mkdir(parents=True, mode=0o700)
    result, module = adapter.adapt(request, context, source_root)
    geometry, renderer = adapter.load_r1()
    if module is None:
        raw = renderer.render({}, source_root)
        name = "project-input-required.svg"
        result["PROJECT_GEOMETRY_DIAGNOSTIC"] = "NOT_EXECUTED_MISSING_OR_REJECTED_EVIDENCE"
    else:
        bound = adapter.bind_r1_evidence(module, result, output)
        engine = geometry.evaluate(bound, output)
        result["R1_DIAGNOSTIC"] = engine
        valid = engine["GEOMETRY_INPUT_STATUS"] == "VALID_SOURCE_BOUND_OFFLINE_INPUT"
        if not valid:
            result["PROJECT_INPUT_ADMISSION"] = "BLOCKED"
            result["BLOCKERS"].append("R1_GEOMETRY_INPUT_REJECTED")
        result["PROJECT_GEOMETRY_DIAGNOSTIC"] = (
            "COMPLETE_WITH_FINDINGS_NOT_ENGINEERING_APPROVAL" if valid else "REJECTED_BY_R1"
        )
        result["STAGES"]["GEOMETRY_DIAGNOSTIC_COMPLETE"] = valid
        result["PATH_DIAGNOSTICS"] = {
            "ROUTE_SOURCE": "REVIEWED_STRUCTURE_AND_INDIVIDUAL_WIDTH_CALLOUTS",
            "ROUTES": bound["ROUTES"] + bound["ASSEMBLY_ROUTES"],
            "FULL_WIDTH_CHECK_RESULTS": engine.get("PATH_CHECKS", []),
            "ACTUAL_GEOMETRIC_CLEARANCE_MM": None,
            "CLEARANCE_INTERPRETATION": "Swept input width checked, not maximum clearance measured",
            "PERSONNEL_MATERIAL_CROSSING": "ENGINEERING_REVIEW_REQUIRED",
            "FUNCTIONAL_REVIEW_STATUS": "REVIEW_REQUIRED",
        }
        result["OPERATOR_LAYOUT_STATUS"] = "SOURCE_BOUND_TASKS_STILL_REQUIRE_ENGINEERING_REVIEW"
        result["CLEAR_WIDTH_STATUS"] = "SOURCE_BOUND_TEST_WIDTH_NOT_APPROVED_MINIMUM"
        raw = renderer.render(bound, output)
        name = (
            "synthetic-pipeline-diagnostic.svg"
            if context.test_only
            else "PROJECT_STATION_DIAGNOSTIC.svg"
        )
        (output / "normalized-module.json").write_bytes(adapter.encode(bound))
    svg = warning_svg(raw, result)
    (output / name).write_bytes(svg)
    result["SVG"] = {"PATH": name, "SHA256": adapter.sha(svg)}
    (output / "diagnostic.json").write_bytes(adapter.encode(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-register", type=Path, required=True)
    parser.add_argument("--review-register-sha256", required=True)
    args = parser.parse_args()
    # These are trusted operator launch arguments, never fields in request JSON.
    context = adapter.load_review_context(args.review_register, args.review_register_sha256)
    result = diagnose(
        adapter.read_json(args.request.read_bytes()), context, args.source_root, args.output
    )
    print(
        json.dumps(
            {
                "PROJECT_INPUT_ADMISSION": result["PROJECT_INPUT_ADMISSION"],
                "PROJECT_GEOMETRY_DIAGNOSTIC": result["PROJECT_GEOMETRY_DIAGNOSTIC"],
            }
        )
    )


if __name__ == "__main__":
    main()
