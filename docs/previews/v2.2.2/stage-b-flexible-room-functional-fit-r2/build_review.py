"""Reproduce only this new offline delivery; old evidence is read-only."""

from __future__ import annotations

import argparse
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import offline_functional_fit as fit
import offline_functional_renderer as render

HERE = fit.HERE


def seal_synthetic(doc: dict[str, Any], root: Path, name: str) -> dict[str, Any]:
    """Test-only records: never issue a project review context or Owner grant."""
    geo = fit.dependencies()[0]
    value = deepcopy(doc)
    source_id = "SYNTHETIC_ROOM_TEST"
    value["CONFIGURATION"]["SOURCE_ID"] = source_id
    facts = {"CONFIGURATION": value["CONFIGURATION"]}
    for field, prefix in (("COMPONENTS", "COMPONENT"), ("ROUTES", "ROUTE"), ("PORTALS", "PORTAL")):
        for record in value[field]:
            record["SOURCE_ID"] = source_id
            facts[prefix + ":" + record["ID"]] = record
    evidence = {
        "EVIDENCE_KIND": "SYNTHETIC_TEST_GEOMETRY",
        "PROJECT_ID": value["PROJECT_ID"],
        "PURPOSE": "SOFTWARE_TEST_ONLY",
        "FACTS": facts,
    }
    raw = geo.encode(evidence)
    (root / name).write_bytes(raw)
    value["SOURCES"] = {
        source_id: {
            "PATH": name,
            "SHA256": geo.digest(raw),
            "EVIDENCE_KIND": "SYNTHETIC_TEST_GEOMETRY",
        }
    }
    return value


def scenario(zone: str, negative: bool = False) -> dict[str, Any]:
    config: dict[str, Any] = {
        "finished_clear_bounds_mm": [0, 0, 10000, 6000],
        "door_operation": "SYNTHETIC_EXPLICIT_SWEEP_NOT_PROJECT_DOOR",
        "shift_change_duration": "SYNTHETIC_20_MIN_NOT_PROJECT_DEFAULT",
        "cleaning_duration": "SYNTHETIC_30_MIN_NOT_PROJECT_DEFAULT",
        "maintenance_procedure": "SYNTHETIC_STOPPED_MACHINE_INSPECTION",
    }
    components: list[dict[str, Any]] = []

    def add(name: str, role: str, rect: list[int], states: tuple[str, ...] = fit.STATES) -> None:
        components.append(
            {
                "ID": name,
                "ROLE": role,
                "BOUNDS_MM": rect,
                "TRANSFORM": {"ROTATION_DEG": 0, "TRANSLATION_MM": [0, 0]},
                "ACTIVE_STATES": list(states),
            }
        )

    if zone == "office":
        config.update(
            factory_size="SMALL",
            design_staff=12,
            workstations=12,
            furniture_model="SYNTHETIC_DESK_NOT_PROJECT_PRODUCT",
            chair_movement=True,
            storage=True,
            necessary_functions=["SYNTHETIC_OFFICE_WORK"],
        )
        for i in range(12):
            x, y = 500 + i % 6 * 1400, 500 + i // 6 * 1800
            add("desk_" + str(i + 1), "BODY", [x, y, x + 1000, y + 600])
            add(
                "staff_" + str(i + 1),
                "STANDING",
                [x, y + 650, x + 600, y + 1100],
                ("NORMAL_OPERATION",),
            )
            add(
                "chair_" + str(i + 1),
                "CHAIR",
                [x + 650, y + 650, x + 1000, y + 1100],
                ("NORMAL_OPERATION",),
            )
        add("storage", "BODY", [9000, 500, 9600, 1200])
        if negative:
            config["finished_clear_bounds_mm"][2] = 8000
    elif zone == "changing_room":
        config.update(
            locker_count=8,
            simultaneous_users=4,
            locker_model="SYNTHETIC_TEST_LOCKER",
            locker_unit_mm=[400, 500, 1700],
            arrangement="SINGLE_ROW",
            door_sweep=True,
            bench=True,
            clothing_separation="INTERNAL_SEPARATE_STORAGE_NOT_DOUBLE_COUNT",
            hygiene_facilities="SYNTHETIC_EXPLICIT_PLACEHOLDER_NOT_PROJECT_REVIEW",
        )
        for i in range(8):
            x = 500 + i * 400
            add("locker_" + str(i + 1), "BODY", [x, 500, x + 400, 1000])
            add("door_" + str(i + 1), "DOOR_SWEEP", [x, 1000, x + 400, 1400], ("NORMAL_OPERATION",))
        for i in range(4):
            x = 500 + i * 800
            add("user_" + str(i + 1), "STANDING", [x, 1500, x + 600, 2100], ("NORMAL_OPERATION",))
        add("bench", "BODY", [500, 3000, 3000, 3400])
        if negative:
            config["arrangement"] = "OPPOSED_ROWS"
            config["finished_clear_bounds_mm"] = [0, 0, 10000, 875]
            # Four lockers per opposing row: each 500 mm body fits its own wall,
            # but the two specified rows physically overlap by 125 mm.
            for i, item in enumerate(
                c for c in components if c["ROLE"] == "BODY" and c["ID"].startswith("locker_")
            ):
                x = 500 + (i % 4) * 400
                y = 0 if i < 4 else 375
                item["BOUNDS_MM"] = [x, y, x + 400, y + 500]
    else:
        config.update(
            process_type="PACKAGING_BOX_FILM_SEALING",
            equipment_model="SYNTHETIC_BOX_SEALER",
            equipment_count=1,
            capacity="SYNTHETIC_100_BOX_PER_HOUR_NOT_PROJECT",
            effective_runtime_hours="SYNTHETIC_6_NOT_16",
            body_height_mm=1800,
            infeed_direction="X_POS",
            outfeed_direction="X_POS",
            operator_tasks=["SYNTHETIC_LOAD"],
            product_buffer=True,
        )
        add("sealer", "BODY", [3000, 1800, 6000, 3400])
        add("operator", "STANDING", [3800, 800, 4500, 1500], ("NORMAL_OPERATION",))
        add("supply", "SUPPLY", [1000, 2000, 2800, 3000], ("NORMAL_OPERATION",))
        add("outfeed", "OUTFEED", [6200, 2000, 8000, 3000], ("NORMAL_OPERATION",))
        add("buffer", "BUFFER", [8200, 2000, 9400, 3000], ("NORMAL_OPERATION",))
        if negative:
            config["finished_clear_bounds_mm"][3] = 5400
    add("personnel_aisle", "AISLE", [0, 4500, 10000, 5100])
    add("service", "SERVICE", [1000, 5500, 9000, 5900], ("CLEANING", "MAINTENANCE"))
    add("entry_sweep", "DOOR_SWEEP", [0, 4100, 600, 4500], ("NORMAL_OPERATION", "SHIFT_CHANGE"))
    routes = [
        {
            "ID": "inside_route",
            "KIND": "PERSONNEL",
            "POINTS_MM": [[0, 4800], [10000, 4800]],
            "WIDTH_MM": 500,
            "ACTIVE_STATES": list(fit.STATES),
            "PORTAL_ID": "entry",
            "EXIT_PORTAL_ID": "exit",
        }
    ]
    if zone == "coating_room":
        routes.append(
            {**deepcopy(routes[0]), "ID": "non_film_route", "KIND": ("NON_SEALING_PASS_THROUGH")}
        )
    return {
        "IDENTITY": fit.IDENTITY,
        "VERSION": fit.VERSION,
        "MODEL": fit.MODELS[zone],
        "ZONE_CODE": zone,
        "MODE": "SYNTHETIC_TEST",
        "PROJECT_ID": "SYNTHETIC_ROOM_TEST_ONLY",
        "DIMENSION_UNIT": "mm",
        "COORDINATE_SYSTEM": "ROOM_LOCAL_XY_Y_UP",
        "MODEL_ORIENTATION": "EXPLICIT_LOCAL_XY_NO_PLACEMENT_SEARCH",
        "ROOM_BOUNDS_MM": [0, 0, 10000, 6000],
        "CONFIGURATION": config,
        "EXAMPLE_NAME": zone
        + (" / insufficient clear space" if negative else " / specified geometry fits"),
        "COMPONENTS": components,
        "ROUTES": routes,
        "PORTALS": [
            {
                "ID": "entry",
                "SEGMENT_MM": [[0, 4200], [0, 5400]],
                "DOOR_SWING_STATUS": "SYNTHETIC_TEST_ONLY",
            },
            {
                "ID": "exit",
                "SEGMENT_MM": [[10000, 4200], [10000, 5400]],
                "DOOR_SWING_STATUS": "SYNTHETIC_TEST_ONLY",
            },
        ],
        "SOURCES": {},
    }


def history() -> dict[str, Any]:
    """All existing tracked files are protected, including production and old previews."""
    paths = (
        subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", fit.REFERENCE], cwd=fit.REPO
        )
        .decode()
        .splitlines()
    )
    # Git diff compares against the exact frozen tree, not against a mutable manifest.
    changed = (
        subprocess.check_output(
            ["git", "diff", fit.REFERENCE, "--name-only", "--", *paths], cwd=fit.REPO
        )
        .decode()
        .splitlines()
    )
    if changed:
        raise ValueError("PREEXISTING_TRACKED_FILES_CHANGED:" + str(changed))
    _, _, loader, owner = fit.dependencies()
    old = owner.load_previous(owner.READINESS, "offline_compatibility.py")
    replay = old.legacy_replay()
    return {
        "STATUS": "PASS",
        "REFERENCE": fit.REFERENCE,
        "PROTECTED_TRACKED_FILE_COUNT": len(paths),
        "CHANGED_PREEXISTING_FILES": changed,
        "LEGACY_REPLAY": replay,
        "BASELINE_MANIFEST_SHA256": loader.sha(
            (loader.BASELINE / "source_manifest.json").read_bytes()
        ),
        "UNMODELED_FLEXIBLE_DIMENSION_RULE_UNCHANGED": True,
    }


def build(artifact_root: Path) -> None:
    for name in ("examples", "previews"):
        (HERE / name).mkdir(exist_ok=True)
    report = fit.audit_rooms(artifact_root)
    business = fit.business_examples()

    def write(name: str, value: Any) -> None:
        (HERE / name).write_bytes(fit.encode(value))

    write("eight-layout-functional-fit.json", report)
    write(
        "existing-room-geometry-index.json",
        [
            {
                k: v
                for k, v in r.items()
                if k
                in (
                    "CANDIDATE_ID",
                    "ZONE_CODE",
                    "SOURCE_GEOMETRY_HASH",
                    "RAW_CANDIDATE_SHA256",
                    "SOURCE_ZONE",
                    "WORLD_BOUNDS_MM",
                    "ROOM_WIDTH_MM",
                    "ROOM_DEPTH_MM",
                    "ROOM_AREA_MM2",
                    "LOCAL_COORDINATES",
                )
            }
            for r in report["ROOMS"]
        ],
    )
    write(
        "existing-room-portal-index.json",
        [
            {
                "CANDIDATE_ID": r["CANDIDATE_ID"],
                "ZONE_CODE": r["ZONE_CODE"],
                "PORTALS": r["PORTALS"],
            }
            for r in report["ROOMS"]
        ],
    )
    write("owner-v2-business-examples.json", business)
    write("historical-integrity.json", history())
    write(
        "missing-project-inputs.json",
        {
            "STATUS": "INPUT_REQUIRED",
            "PROJECT_FURNITURE": "UNAVAILABLE",
            "PROJECT_LOCKER": "UNAVAILABLE",
            "PROJECT_BOX_FILM_SEALER": "UNAVAILABLE",
            "BOUNDARY": (
                "Known evidence indexes only; no assertion that sources do not exist elsewhere"
            ),
            "BY_ZONE": {
                z: [*fit.REQUIRED[z], *fit.COMMON, "components", "routes", "source_review"]
                for z in fit.ZONES
            },
        },
    )
    write(
        "source-provenance-matrix.json",
        {
            "GEOMETRY": {
                "CLASS": "PROJECT_VERIFIED_INPUT",
                "SCOPE": "FROZEN_GEOMETRY_BYTES_ONLY_NOT_FUNCTIONAL_APPROVAL",
            },
            "FURNITURE_LOCKER_BOX_SEALER": "UNAVAILABLE",
            ("OLD_PUBLIC_WAXING_PALLET_REFERENCES"): (
                "PUBLIC_REFERENCE_NOT_APPLICABLE_TO_BOX_FILM_SEALING"
            ),
            "SYNTHETIC_EXAMPLES": "SYNTHETIC_TEST_NEVER_PROJECT_INPUT",
            ("PROJECT_DIAGNOSTIC_ADMISSION"): (
                "REUSE_R2_VERIFY_DOCUMENT_AND_EXTRACTION_WITH_TRUSTED_CONTEXT"
            ),
            "PROJECT_APPROVAL": "NOT_IMPLEMENTED_NOT_GRANTED",
        },
    )
    for z in fit.ZONES:
        name = {"office": "office", "changing_room": "changing", "coating_room": "film-sealing"}[z]
        write(
            name + "-module-contract.json",
            {
                "IDENTITY": fit.MODELS[z],
                "ZONE_CODE": z,
                "REQUIRED_CONFIGURATION": [*fit.REQUIRED[z], *fit.COMMON],
                "STATES": fit.STATES,
                "SPATIAL_DEFAULTS": None,
                "FORMAL_APPROVAL": False,
                "PROCESS_TYPE": "PACKAGING_BOX_FILM_SEALING" if z == "coating_room" else None,
            },
        )
    write(
        "functional-fit-input-contract.json",
        {
            "IDENTITY": fit.IDENTITY,
            "VERSION": fit.VERSION,
            "COORDINATE_SYSTEM": "ROOM_LOCAL_XY_Y_UP",
            "DIMENSION_UNIT": "integer mm",
            "MODELS": fit.MODELS,
            "STATES": fit.STATES,
            "COMPONENT_ROLES": sorted(fit.ROLES),
            "PROJECT_ADMISSION": (
                "Existing R2 review context supplied by trusted launcher, never request JSON"
            ),
            "GEOMETRY_REUSE": ("R1 transform_rect/intersection/covered/union_area/path_envelope"),
            "BODY": "Active in all states; other envelopes explicitly state-bound",
            "PORTAL": (
                "Geometric connection is separate from door operation and professional review"
            ),
            "TIME_SHARING": "Different active states alone do not approve sharing",
            "NO_FIT_SCOPE": (
                "Supplied configuration/orientation only; no search over alternatives"
            ),
            "STATUS_CLASSES": [
                "INPUT_REQUIRED",
                "CONDITIONAL_SCENARIO_NOT_FIT",
                "HARD_GEOMETRY_CONFLICT",
                "INTERACTION_REVIEW_REQUIRED",
                "GEOMETRY_CHECK_ONLY",
            ],
            "NEW_HARD_AUTHORITY": False,
        },
    )
    candidate_ids = list(dict.fromkeys(r["CANDIDATE_ID"] for r in report["ROOMS"]))
    for i, candidate in enumerate(candidate_ids, 1):
        rooms = [r for r in report["ROOMS"] if r["CANDIDATE_ID"] == candidate]
        (HERE / "previews" / f"candidate-{i:02}.svg").write_bytes(render.real_candidate(rooms))
    results = {}
    for zone in fit.ZONES:
        name = {"office": "office", "changing_room": "changing", "coating_room": "film-sealing"}[
            zone
        ]
        documents, output = [], []
        for negative in (False, True):
            tag = name + ("-negative" if negative else "-positive")
            doc = seal_synthetic(
                scenario(zone, negative), HERE / "examples", tag + "-evidence.json"
            )
            result = fit.evaluate(doc, HERE / "examples")
            write("examples/" + tag + "-input.json", doc)
            write("examples/" + tag + "-result.json", result)
            documents.append(doc)
            output.append(result)
        (HERE / "previews" / (name + "-synthetic.svg")).write_bytes(
            render.synthetic(documents, output)
        )
        results[name] = output
    write("synthetic-scenario-results.json", results)
    write(
        "conditional-width-proofs.json",
        [fit.opposed_width_proof(w, 500, 500) for w in (875, 977, 1500)],
    )
    lines = [
        "# 24间真实房间功能审核矩阵",
        "",
        ("面积与狭长比例不产生功能PASS或违规结论。所有输入均缺项目功能资料。"),
        "",
        "|候选|房间|物理宽×深 mm|面积 mm²|真实Portal数|功能状态|",
        "|---|---|---|---|---|---|",
    ]
    for r in report["ROOMS"]:
        lines.append(
            f"|{r['CANDIDATE_ID']}|{r['ZONE_CODE']}|{r['ROOM_WIDTH_MM']}×{r['ROOM_DEPTH_MM']}|"
            f"{r['ROOM_AREA_MM2']}|{len(r['PORTALS'])}|INPUT_REQUIRED|"
        )
    (HERE / "functional-fit-review-matrix.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    build(parser.parse_args().artifact_root)
