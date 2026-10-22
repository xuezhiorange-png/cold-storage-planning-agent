"""Reproduce synthetic examples/contracts only; reads sealed history, never solves."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import offline_station_geometry as geo
from offline_station_renderer import render

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
EXAMPLES = HERE / "examples"
PREVIOUS = HERE.parent / "owner-v2-packaging-area-geometry-calibration-r1"
ZERO = {"TRANSLATION_MM": [0, 0], "ROTATION_DEG": 0}
SOURCE = "synthetic"


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(geo.encode(value))


def component(key: str, kind: int, role: str, rect: list[int], states: list[str]) -> dict[str, Any]:
    return {
        "COMPONENT_ID": key,
        "COMPONENT_TYPE": geo.TYPES[kind],
        "ROLE": role,
        "SOURCE_ID": SOURCE,
        "GEOMETRY": {"TYPE": "RECTANGLE", "BOUNDS_MM": rect},
        "TRANSFORM": deepcopy(ZERO),
        "COORDINATE_SYSTEM": "STATION_LOCAL",
        "DIMENSION_UNIT": "mm",
        "ACTIVE_STATES": states,
        "SIMULTANEITY": "ALL_ACTIVE_COMPONENTS_IN_STATE",
        "OVERLAP_POLICY": "PHYSICAL_EXCLUSIVE"
        if role in ("BODY", "STANDING")
        else "INTERACTION_REVIEW",
        "SOURCE_VERIFICATION": "CONTENT_REQUIRED",
        "APPROVAL_STATUS": "NOT_PROJECT_APPROVED",
    }


def example(arrangement: str = "SINGLE") -> dict[str, Any]:
    all_states = list(geo.STATES)
    normal = ["NORMAL_PRODUCTION"]
    doc: dict[str, Any] = {
        "IDENTITY": geo.IDENTITY,
        "VERSION": geo.VERSION,
        "MODE": "SYNTHETIC_TEST",
        "PROJECT_ID": "SYNTHETIC_STATION_ONLY",
        "DIMENSION_UNIT": "mm",
        "COORDINATE_SYSTEM": "RIGHT_HANDED_XY_Y_UP",
        "ARRANGEMENT": arrangement,
        "SOURCES": {},
        "COMPONENTS": [],
        "OPERATORS": [],
        "ROUTES": [],
        "INTERFACES": [],
        "INSTANCES": [{"INSTANCE_ID": "A", "TRANSFORM": deepcopy(ZERO), "SOURCE_ID": SOURCE}],
        "ASSEMBLY_CIRCULATION": [],
        "ASSEMBLY_ROUTES": [],
        "SHARING_CONDITIONS": [],
        "SHIFT_CHANGE": {"DURATION_MINUTES": None, "STATUS": "ENGINEERING_INPUT_REQUIRED"},
        "WARNING": "Every dimension is invented test geometry, not a project or vendor selection",
    }
    doc["COMPONENTS"] = [
        component("EQUIPMENT", 0, "BODY", [1000, 2200, 3400, 3000], all_states),
        component("SUPPLY", 2, "SUPPLY", [200, 2400, 800, 3000], normal),
        component("OUTFEED", 3, "OUTFEED", [3600, 2400, 4200, 3000], normal),
        component("PEOPLE_AISLE", 4, "PERSONNEL_AISLE", [0, 400, 4800, 1500], all_states),
        component("IN_AISLE", 4, "MATERIAL_AISLE", [0, 1500, 200, 4500], all_states),
        component("OUT_AISLE", 4, "MATERIAL_AISLE", [4200, 1500, 4800, 4500], all_states),
        component("REAR_AISLE", 4, "SHARED_AISLE", [0, 3900, 4800, 4500], all_states),
        component("SERVICE", 5, "SERVICE", [800, 3100, 3600, 3900], ["CLEANING", "MAINTENANCE"]),
    ]

    def interface(key: str, comp: str, kind: str, position: list[int]) -> dict[str, Any]:
        return {
            "INTERFACE_ID": key,
            "COMPONENT_ID": comp,
            "KIND": kind,
            "POINT_MM": position,
            "SOURCE_ID": SOURCE,
        }

    doc["INTERFACES"] = [
        interface("ENTRY", "PEOPLE_AISLE", "PERSONNEL_ENTRY", [2400, 800]),
        interface("MATERIAL_ENTRY", "IN_AISLE", "MATERIAL_IN", [100, 2700]),
        interface("SUPPLY_PORT", "SUPPLY", "SUPPLY", [500, 2700]),
        interface("PRODUCT_EXIT", "OUT_AISLE", "PRODUCT_OUT", [4500, 2700]),
        interface("OUTFEED_PORT", "OUTFEED", "OUTFEED", [3900, 2700]),
    ]
    for i, x in enumerate((1100, 1800, 2500), 1):
        standing, reach, path, port = f"STAND_{i}", f"REACH_{i}", f"ENTRY_OP_{i}", f"OP_PORT_{i}"
        doc["COMPONENTS"].extend(
            [
                component(standing, 1, "STANDING", [x, 1500, x + 600, 2100], normal),
                component(reach, 1, "REACH", [x, 1900, x + 600, 2500], normal),
            ]
        )
        doc["INTERFACES"].append(interface(port, standing, "OPERATOR_POSITION", [x + 300, 1800]))
        doc["OPERATORS"].append(
            {
                "OPERATOR_ID": f"OPERATOR_{i}",
                "SOURCE_ID": SOURCE,
                "TASK": [
                    "Receive and inspect test product",
                    "Fill test package",
                    "Close and transfer test package",
                ][i - 1],
                "WORK_DIRECTION": "Y_POS",
                "STANDING_COMPONENT": standing,
                "REACH_COMPONENT": reach,
                "ENTRY_PATH": path,
            }
        )
        doc["ROUTES"].append(
            {
                "ROUTE_ID": path,
                "FLOW_KIND": "PERSONNEL",
                "POINTS_MM": [[2400, 800], [x + 300, 800], [x + 300, 1800]],
                "WIDTH_MM": 300,
                "ACTIVE_STATES": normal,
                "FROM_INTERFACE": "ENTRY",
                "TO_INTERFACE": port,
                "END_COMPONENTS": [standing],
                "SOURCE_ID": SOURCE,
            }
        )
    for key, start, end, pts, terminal, flow in (
        (
            "SUPPLY_PATH",
            "MATERIAL_ENTRY",
            "SUPPLY_PORT",
            [[100, 2700], [500, 2700]],
            "SUPPLY",
            "MATERIAL_IN",
        ),
        (
            "OUTFEED_PATH",
            "OUTFEED_PORT",
            "PRODUCT_EXIT",
            [[3900, 2700], [4500, 2700]],
            "OUTFEED",
            "PRODUCT_OUT",
        ),
    ):
        doc["ROUTES"].append(
            {
                "ROUTE_ID": key,
                "FLOW_KIND": flow,
                "POINTS_MM": pts,
                "WIDTH_MM": 100,
                "ACTIVE_STATES": normal,
                "FROM_INTERFACE": start,
                "TO_INTERFACE": end,
                "END_COMPONENTS": [terminal],
                "SOURCE_ID": SOURCE,
            }
        )
    poses = []
    if arrangement in ("LINEAR_ARRANGEMENT", "PARALLEL_ROWS"):
        poses.append(("B", [5400, 0], 0))
    if arrangement == "OPPOSED_ARRANGEMENT":
        poses.append(("B", [10200, 4900], 180))
    if arrangement == "PARALLEL_ROWS":
        poses.extend((("C", [0, 5100], 0), ("D", [5400, 5100], 0)))
    for name, xy, angle in poses:
        pose = {"TRANSLATION_MM": xy, "ROTATION_DEG": angle}
        doc["INSTANCES"].append({"INSTANCE_ID": name, "TRANSFORM": pose, "SOURCE_ID": SOURCE})
        p = [int(v) for v in geo.transform(geo.point([2400, 800]), pose)]
        pts = [[2400, 800], p] if p[1] == 800 else [[2400, 800], [-400, 800], [-400, p[1]], p]
        route = {
            "ROUTE_ID": "LINK_" + name,
            "FLOW_KIND": "PERSONNEL",
            "FROM_KEY": "A/ENTRY",
            "TO_KEY": name + "/ENTRY",
            "POINTS_MM": pts,
            "WIDTH_MM": 300,
            "ACTIVE_STATES": all_states,
            "SOURCE_ID": SOURCE,
        }
        doc["ASSEMBLY_ROUTES"].append(route)
        for j, r in enumerate(geo.path_envelope([geo.point(v) for v in pts], 300)):
            shared = component(
                f"LINK_{name}_{j}", 4, "SHARED_AISLE", [int(v) for v in r], all_states
            )
            shared["COORDINATE_SYSTEM"] = "ASSEMBLY_GLOBAL"
            shared["OVERLAP_POLICY"] = "EXPLICIT_SHARED_REVIEW"
            doc["ASSEMBLY_CIRCULATION"].append(shared)
    if poses:
        doc["SHARING_CONDITIONS"].append(
            {
                "RULE_ID": "DECLARED_SHARED_ACCESS_A",
                "COMPONENT_KEYS": ["A/PEOPLE_AISLE", "ASSEMBLY/LINK_B_0"],
                "STATES": all_states,
                "CONDITION_TEXT": (
                    "Synthetic common circulation example only; traffic capacity, "
                    "safety and engineering approval remain unverified"
                ),
                "SOURCE_ID": SOURCE,
            }
        )
    return doc


def seal(doc: dict[str, Any], root: Path, filename: str = "synthetic-evidence.json") -> None:
    facts = {}
    collections = (
        ("COMPONENTS", "COMPONENT", "COMPONENT_ID"),
        ("OPERATORS", "OPERATOR", "OPERATOR_ID"),
        ("INTERFACES", "INTERFACE", "INTERFACE_ID"),
        ("ROUTES", "ROUTE", "ROUTE_ID"),
        ("INSTANCES", "INSTANCE", "INSTANCE_ID"),
        ("ASSEMBLY_CIRCULATION", "ASSEMBLY", "COMPONENT_ID"),
        ("ASSEMBLY_ROUTES", "ASSEMBLY_ROUTE", "ROUTE_ID"),
        ("SHARING_CONDITIONS", "SHARING", "RULE_ID"),
    )
    for collection, prefix, field in collections:
        for record in doc[collection]:
            facts[prefix + ":" + record[field]] = record
    evidence = {
        "EVIDENCE_KIND": "SYNTHETIC_TEST_GEOMETRY",
        "PROJECT_ID": doc["PROJECT_ID"],
        "FACTS": facts,
        "APPROVAL": "NO_PROJECT_APPROVAL; invented software test coordinates",
    }
    write(root / filename, evidence)
    doc["SOURCES"] = {
        SOURCE: {
            "PATH": filename,
            "SHA256": geo.digest((root / filename).read_bytes()),
            "EVIDENCE_KIND": "SYNTHETIC_TEST_GEOMETRY",
        }
    }


def historical_contract() -> dict[str, Any]:
    manifest = json.loads((PREVIOUS / "source_manifest.json").read_bytes())["files"]
    for name, expected in manifest.items():
        if geo.digest((PREVIOUS / name).read_bytes()) != expected:
            raise ValueError("HISTORICAL_CALIBRATION_CHANGED")
    facts = json.loads((PREVIOUS / "real-layout-interface-review.json").read_bytes())
    return {
        "IDENTITY": "SORTING_ROOM_INTERFACE_CONTRACT",
        "VERSION": "sealed-room-boundaries@1.0.0",
        "SOURCE_SHA256": manifest["real-layout-interface-review.json"],
        "SOURCE_PATH": str((PREVIOUS / "real-layout-interface-review.json").relative_to(REPO)),
        "STATUS": "READ_ONLY_BOUNDARY_INPUT_NOT_INTERNAL_REACHABILITY_PROOF",
        "CANDIDATE_COUNT": facts["candidate_count"],
        "INTERFACE_COUNT": facts["sorting_interface_count"],
        "LAYOUTS": facts["layouts"],
        "FIT_18_OR_28_STATIONS": None,
        "FUNCTIONAL_ROOM_AREA": None,
        "P1_AUTHORITY_CHANGED": False,
    }


def evidence_index(project_artifacts: Path) -> dict[str, Any]:
    # Inventory names only within authorized project roots; no private/home-wide search.
    roots = ["docs", "backend/tests/fixtures"]
    listed = subprocess.check_output(["rg", "--files", *roots], cwd=REPO, text=True).splitlines()
    pattern = re.compile(
        r"包装|分选|工位|输送|周转|设备总图|packing|packaging|conveyor|supplier|sorting|workstation",
        re.I,
    )
    candidates = [
        p for p in listed if pattern.search(p) and not p.startswith(str(HERE.relative_to(REPO)))
    ]
    asset_names = subprocess.check_output(
        ["rg", "--files", str(project_artifacts)], text=True
    ).splitlines()
    # Existing duplicated readback snapshots are not additional independent equipment sources.
    assets = [
        Path(p)
        for p in asset_names
        if HERE.name not in Path(p).parts
        and not any(part.startswith(("readback-", "delivery-")) for part in Path(p).parts)
        and Path(p).suffix.lower()
        in (".pdf", ".dwg", ".dxf", ".step", ".stp", ".jpg", ".jpeg", ".png")
        and pattern.search(p)
    ]
    records = [
        {
            "SOURCE_ID": "REPO_" + geo.digest(p.encode())[:12],
            "SOURCE_PATH_OR_URL": p,
            "DOCUMENT_VERSION": "Reference HEAD6e6972e1adf012b397343bd5d53a2c65c9d81fad",
            "FILE_SHA256": geo.digest((REPO / p).read_bytes()),
            "EQUIPMENT_ID": None,
            "DIMENSION_EVIDENCE": "Repository name match; not a selected project equipment drawing",
            "PROJECT_APPLICABILITY": "CANDIDATE_METADATA_ONLY_NO_EQUIPMENT_SELECTION_PROOF",
            "VERIFICATION_STATUS": "FILE_BYTES_HASHED_APPLICABILITY_NOT_PROVEN",
            "OWNER_APPROVAL_STATUS": "NO_SELECTION_APPROVAL_LOCATED",
        }
        for p in sorted(candidates)
    ]
    for p in assets:
        records.append(
            {
                "SOURCE_ID": "LOCAL_"
                + geo.digest(str(p.relative_to(project_artifacts)).encode())[:12],
                "SOURCE_PATH_OR_URL": "PROJECT_FILES/" + str(p.relative_to(project_artifacts)),
                "DOCUMENT_VERSION": "EXISTING_RESEARCH_CACHE_OR_DIAGNOSTIC",
                "FILE_SHA256": geo.digest(p.read_bytes()),
                "EQUIPMENT_ID": None,
                "DIMENSION_EVIDENCE": "NOT_A_SELECTED_PACKING_STATION_DRAWING",
                "PROJECT_APPLICABILITY": "REFERENCE_OR_DIAGNOSTIC_ONLY",
                "VERIFICATION_STATUS": "LOCAL_BYTES_HASHED_NOT_PROJECT_AUTHENTICATED",
                "OWNER_APPROVAL_STATUS": "NOT_PROVEN",
            }
        )
    references = json.loads((PREVIOUS / "engineering-sources.json").read_bytes())["sources"]
    for source in references:
        records.append(
            {
                "SOURCE_ID": source["ID"],
                "SOURCE_PATH_OR_URL": source["SOURCE_URL"],
                "DOCUMENT_VERSION": source["VERSION"],
                "FILE_SHA256": source.get("FILE_SHA256"),
                "SOURCE_RECORD_SHA256": geo.digest(geo.encode(source)),
                "EQUIPMENT_ID": None,
                "DIMENSION_EVIDENCE": source["ENGINEERING_FACT"],
                "PROJECT_APPLICABILITY": (
                    "PRIOR_VERIFIED_REFERENCE_ONLY_NOT_SELECTED_PROJECT_EQUIPMENT"
                ),
                "VERIFICATION_STATUS": "PREVIOUS_TASK_SOURCE_RECORD_REVERIFIED_NOT_NEW_FETCH",
                "OWNER_APPROVAL_STATUS": "NOT_APPROVED_AS_PROJECT_EQUIPMENT",
                "LIMITATIONS": source["LIMITATIONS"],
            }
        )
    return {
        "IDENTITY": "PROJECT_EQUIPMENT_EVIDENCE_INDEX",
        "PROJECT_SELECTED_EQUIPMENT": "UNAVAILABLE",
        "SEARCH_SCOPE": {
            "repository_roots": roots,
            "local_root_alias": "PROJECT_FILES (cold-storage-planning-agent only)",
            "filename_keywords": pattern.pattern,
            "excluded": (
                "Other projects, private folders, old Grant stores, unrelated "
                "backend/artifacts, archive contents and duplicate readback copies"
            ),
        },
        "repository_candidate_documents": [
            {"path": p, "sha256": geo.digest((REPO / p).read_bytes())} for p in sorted(candidates)
        ],
        "RECORDS": records,
        "LIMITATION": (
            "No project-approved station, conveyor, three-operator or "
            "material-carrier dimension source identified in searched scope; "
            "absence here is not a claim about all Owner records."
        ),
    }


def contracts() -> dict[str, Any]:
    return {
        "packing-station-module-contract.json": {
            "IDENTITY": geo.IDENTITY,
            "VERSION": geo.VERSION,
            "OFFLINE_ONLY": True,
            "MODES": ["SYNTHETIC_TEST", "OWNER_PROJECT"],
            "REQUIRED_TYPES": list(geo.TYPES),
            "STATES": list(geo.STATES),
            "COORDINATES": (
                "Explicit right-handed XY, y-up, station-local rectangles; "
                "explicit instance quarter-turn then translation"
            ),
            "DIMENSION_UNIT": "integer mm; exact Fraction intermediate path half-widths",
            "WORKERS_PER_STATION": 3,
            "SOURCE_POLICY": (
                "Actual local bytes SHA256 and entire record equality required; no"
                " self-asserted verified or approval accepted"
            ),
            "GEOMETRY_SCOPE": (
                "Axis-aligned rectangles after quarter-turns; orthogonal "
                "finite-width paths with square end caps; unsupported geometry "
                "rejects, never approximated"
            ),
            "ASSEMBLY_POLICY": (
                "Explicit poses, shared circulation and full-width inter-station "
                "paths; labels do not prove process organization"
            ),
            "AREA_SCOPE": (
                "State union, all-state swept union and bounding rectangle differ;"
                " FUNCTIONAL_ROOM_AREA always null"
            ),
            "PROJECT_APPROVAL": "Always NOT_APPROVED in this prototype",
            "MAX_REAL_FACTORY_SOLVES": 0,
        },
        "operator-task-contract.json": {
            "OPERATORS": ["OPERATOR_1", "OPERATOR_2", "OPERATOR_3"],
            "REQUIRED_PER_OPERATOR": [
                "SOURCE_ID",
                "TASK",
                "WORK_DIRECTION",
                "STANDING_COMPONENT",
                "REACH_COMPONENT",
                "ENTRY_PATH",
            ],
            "EXCLUSIVITY": (
                "Three distinct standing and three distinct reach component "
                "identities; three independent bound access paths"
            ),
            "WORK_DIRECTION": (
                "Explicit local X_POS/X_NEG/Y_POS/Y_NEG transformed with instance pose"
            ),
            "APPROVED_LAYOUT": False,
            "ASSUMPTIONS": (
                "Same-side example only demonstrates software; opposed sides or2+1"
                " require their own sourced coordinates, not an implicit real "
                "default"
            ),
        },
        "state-and-overlap-policy.json": {
            "POLICY_VERSION": "station-state-conflicts@1.0.0",
            "STATES": list(geo.STATES),
            "HARD_COLLISIONS": [
                "BODY_BODY",
                "BODY_STANDING",
                "STANDING_STANDING",
                "BODY_FLOW_OR_CIRCULATION",
                "STANDING_FLOW_OR_CIRCULATION",
            ],
            "REVIEW_REQUIRED": [
                "REACH_INTERACTION",
                "SERVICE_INTERACTION",
                "SUPPLY_OUTFEED_OR_FLOW_INTERACTION",
                "CIRCULATION_SHARING",
                "PERSONNEL_MATERIAL_CROSSING",
            ],
            "BOUNDARY_POLICY": (
                "Positive area triggers component collision classification; "
                "flow-path boundary contact also recorded for review"
            ),
            "ACTIVE_STATE_POLICY": (
                "Only simultaneously active geometry compared; equipment body "
                "never disappears; cleaning and maintenance geometry required"
            ),
            "TIME_SHARING": (
                "Non-simultaneous occupation is not clearance approval; "
                "source-bound conditions recorded, never override hard collision "
                "or grant engineering approval"
            ),
            "SHIFT_CHANGE": (
                "Duration remains missing; non-overlapping staff shifts do not "
                "imply zero cleaning or turnover time"
            ),
        },
        "material-flow-interface-contract.json": {
            "KINDS": [
                "PERSONNEL_ENTRY",
                "OPERATOR_POSITION",
                "MATERIAL_IN",
                "SUPPLY",
                "PRODUCT_OUT",
                "OUTFEED",
            ],
            "REQUIRED_FLOWS": ["PERSONNEL", "MATERIAL_IN", "PRODUCT_OUT"],
            "ENDPOINT_POLICY": (
                "Exact equality with source-bound interfaces on/in their own component"
            ),
            "ROUTE_POLICY": (
                "Full square-cap swept envelope within explicit active circulation"
                " plus named terminal zones; equipment intersections reject"
            ),
            "ASSEMBLY_POLICY": (
                "Explicit source-bound global routes connect named station "
                "interfaces; missing routes never inferred from arrangement name"
            ),
            "BOUNDARY_WARNING": (
                "Room Portal facts are not station-entry or internal-logistics "
                "proof; transport capacity, buffers, reach and production "
                "continuity remain engineering review"
            ),
        },
        "engineering-missing-inputs.json": {
            "PROJECT_SELECTED_EQUIPMENT": "UNAVAILABLE",
            "MISSING": [
                "Selected equipment/conveyor model and complete dimensions",
                "Three-person tasks, standing, reach and actual operator entry paths",
                "Supply/outfeed/reject carriers, cycles and buffers",
                "Applicable independent personnel/material circulation and entry geometry",
                "Cleaning, guard opening and maintenance procedures/envelopes",
                "Shift-change duration and approved temporal sharing",
                "Project source authenticity and professional approvals",
            ],
            "REAL_PROJECT_MODULE_VALIDATED": False,
            "FORMAL_MODULE_DIMENSIONS_APPROVED": False,
            "PACKAGING_AREA_CALIBRATION_READY": False,
            "FUNCTIONAL_ROOM_AREA": None,
        },
    }


def schema() -> dict[str, Any]:
    def obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False,
        }

    string = {"type": "string", "minLength": 1}
    integer = {"type": "integer"}
    coordinate = {"type": "array", "items": integer, "minItems": 2, "maxItems": 2}
    states = {
        "type": "array",
        "items": {"enum": list(geo.STATES)},
        "minItems": 1,
        "uniqueItems": True,
    }
    pose = obj({"TRANSLATION_MM": coordinate, "ROTATION_DEG": {"enum": [0, 90, 180, 270]}})
    comp = obj(
        {
            "COMPONENT_ID": string,
            "COMPONENT_TYPE": {"enum": list(geo.TYPES)},
            "ROLE": {"enum": sorted(set().union(*geo.ROLES.values()))},
            "SOURCE_ID": string,
            "GEOMETRY": obj(
                {
                    "TYPE": {"const": "RECTANGLE"},
                    "BOUNDS_MM": {"type": "array", "items": integer, "minItems": 4, "maxItems": 4},
                }
            ),
            "TRANSFORM": pose,
            "COORDINATE_SYSTEM": {"const": "STATION_LOCAL"},
            "DIMENSION_UNIT": {"const": "mm"},
            "ACTIVE_STATES": states,
            "SIMULTANEITY": {"const": "ALL_ACTIVE_COMPONENTS_IN_STATE"},
            "OVERLAP_POLICY": {
                "enum": ["PHYSICAL_EXCLUSIVE", "INTERACTION_REVIEW", "EXPLICIT_SHARED_REVIEW"]
            },
            "SOURCE_VERIFICATION": {"const": "CONTENT_REQUIRED"},
            "APPROVAL_STATUS": {"const": "NOT_PROJECT_APPROVED"},
        }
    )
    assembly = deepcopy(comp)
    assembly["properties"]["COORDINATE_SYSTEM"] = {"const": "ASSEMBLY_GLOBAL"}
    assembly["properties"]["COMPONENT_TYPE"] = {"const": geo.TYPES[4]}
    assembly["properties"]["ROLE"] = {"enum": sorted(geo.ROLES[geo.TYPES[4]])}
    assembly["properties"]["OVERLAP_POLICY"] = {"const": "EXPLICIT_SHARED_REVIEW"}
    output = obj(
        {
            "IDENTITY": {"const": geo.IDENTITY},
            "VERSION": {"const": geo.VERSION},
            "MODE": {"enum": ["SYNTHETIC_TEST", "OWNER_PROJECT"]},
            "PROJECT_ID": string,
            "DIMENSION_UNIT": {"const": "mm"},
            "COORDINATE_SYSTEM": {"const": "RIGHT_HANDED_XY_Y_UP"},
            "ARRANGEMENT": {
                "enum": ["SINGLE", "LINEAR_ARRANGEMENT", "OPPOSED_ARRANGEMENT", "PARALLEL_ROWS"]
            },
            "SOURCES": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": obj(
                    {
                        "PATH": string,
                        "SHA256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "EVIDENCE_KIND": {"enum": ["SYNTHETIC_TEST_GEOMETRY", "PROJECT_INPUT"]},
                    }
                ),
            },
            "COMPONENTS": {"type": "array", "items": comp, "minItems": 1},
            "OPERATORS": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": obj(
                    {
                        "OPERATOR_ID": {"enum": ["OPERATOR_1", "OPERATOR_2", "OPERATOR_3"]},
                        "SOURCE_ID": string,
                        "TASK": string,
                        "WORK_DIRECTION": {"enum": list(geo.DIRECTIONS)},
                        "STANDING_COMPONENT": string,
                        "REACH_COMPONENT": string,
                        "ENTRY_PATH": string,
                    }
                ),
            },
            "INTERFACES": {
                "type": "array",
                "items": obj(
                    {
                        "INTERFACE_ID": string,
                        "COMPONENT_ID": string,
                        "KIND": {
                            "enum": [
                                "PERSONNEL_ENTRY",
                                "OPERATOR_POSITION",
                                "MATERIAL_IN",
                                "SUPPLY",
                                "PRODUCT_OUT",
                                "OUTFEED",
                            ]
                        },
                        "POINT_MM": coordinate,
                        "SOURCE_ID": string,
                    }
                ),
            },
            "ROUTES": {
                "type": "array",
                "items": obj(
                    {
                        "ROUTE_ID": string,
                        "FLOW_KIND": {"enum": ["PERSONNEL", "MATERIAL_IN", "PRODUCT_OUT"]},
                        "POINTS_MM": {"type": "array", "minItems": 2, "items": coordinate},
                        "WIDTH_MM": {"type": "integer", "minimum": 1},
                        "ACTIVE_STATES": states,
                        "FROM_INTERFACE": string,
                        "TO_INTERFACE": string,
                        "END_COMPONENTS": {"type": "array", "items": string},
                        "SOURCE_ID": string,
                    }
                ),
            },
            "INSTANCES": {
                "type": "array",
                "minItems": 1,
                "items": obj({"INSTANCE_ID": string, "TRANSFORM": pose, "SOURCE_ID": string}),
            },
            "ASSEMBLY_CIRCULATION": {
                "type": "array",
                "items": assembly,
            },
            "ASSEMBLY_ROUTES": {
                "type": "array",
                "items": obj(
                    {
                        "ROUTE_ID": string,
                        "FLOW_KIND": {"enum": ["PERSONNEL", "MATERIAL_IN", "PRODUCT_OUT"]},
                        "FROM_KEY": string,
                        "TO_KEY": string,
                        "POINTS_MM": {"type": "array", "minItems": 2, "items": coordinate},
                        "WIDTH_MM": {"type": "integer", "minimum": 1},
                        "ACTIVE_STATES": states,
                        "SOURCE_ID": string,
                    }
                ),
            },
            "SHARING_CONDITIONS": {
                "type": "array",
                "items": obj(
                    {
                        "RULE_ID": string,
                        "COMPONENT_KEYS": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "uniqueItems": True,
                            "items": string,
                        },
                        "STATES": states,
                        "CONDITION_TEXT": string,
                        "SOURCE_ID": string,
                    }
                ),
            },
            "SHIFT_CHANGE": obj(
                {"DURATION_MINUTES": {"type": ["integer", "null"], "minimum": 0}, "STATUS": string}
            ),
            "WARNING": string,
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:offline:PackingStationModuleV1",
        **output,
        "$comment": (
            "Structural schema only; source bytes, geometry, exact references "
            "and engineering statuses require "
            "offline_station_geometry.evaluate"
        ),
    }


def build(project_data_root: Path | None = None) -> None:
    for name, value in contracts().items():
        write(HERE / name, value)
    write(HERE / "station-envelope-schema.json", schema())
    write(HERE / "sorting-room-interface-contract.json", historical_contract())
    # A sealed local inventory is an input to portable example replay, not a fresh scan.
    # Refresh only with an explicitly supplied, authorized project directory.
    if project_data_root is not None:
        write(HERE / "equipment-evidence-index.json", evidence_index(project_data_root))
    elif not (HERE / "equipment-evidence-index.json").is_file():
        raise ValueError("SEALED_EVIDENCE_INDEX_OR_EXPLICIT_PROJECT_ROOT_REQUIRED")
    single = example()
    seal(single, EXAMPLES)
    write(EXAMPLES / "synthetic-station-input.json", single)
    write(EXAMPLES / "synthetic-station-result.json", geo.evaluate(single, EXAMPLES))
    for name, state in (
        ("synthetic-single-station.svg", "NORMAL_PRODUCTION"),
        ("synthetic-normal-operation.svg", "NORMAL_PRODUCTION"),
        ("synthetic-cleaning-maintenance.svg", "CLEANING"),
        ("synthetic-maintenance.svg", "MAINTENANCE"),
    ):
        (EXAMPLES / name).write_bytes(render(single, EXAMPLES, state))
    for label, arrangement in (
        ("multiple", "LINEAR_ARRANGEMENT"),
        ("opposed", "OPPOSED_ARRANGEMENT"),
        ("parallel", "PARALLEL_ROWS"),
    ):
        doc = example(arrangement)
        seal(doc, EXAMPLES, f"synthetic-{label}-evidence.json")
        write(EXAMPLES / f"synthetic-{label}-input.json", doc)
        result = geo.evaluate(doc, EXAMPLES)
        write(EXAMPLES / f"synthetic-{label}-result.json", result)
        (EXAMPLES / f"synthetic-{label}-stations.svg").write_bytes(render(doc, EXAMPLES))
    missing = {**single, "MODE": "OWNER_PROJECT", "SOURCES": {}}
    write(EXAMPLES / "project-missing-input.json", missing)
    write(EXAMPLES / "project-missing-result.json", geo.evaluate(missing, EXAMPLES))
    (EXAMPLES / "project-input-required.svg").write_bytes(render(missing, EXAMPLES))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-data-root", type=Path)
    build(parser.parse_args().project_data_root)
