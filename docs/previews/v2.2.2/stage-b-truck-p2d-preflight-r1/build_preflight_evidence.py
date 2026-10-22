"""Build new offline reports only; never run old builders, routes or solves."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import offline_stage_b_truck_preflight as pre
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.project_truck_input import validate_project_truck_input
from cold_storage.modules.layout.domain.truck_maneuver import (
    validate_truck_maneuver_project_binding,
)

HERE, REPO = pre.HERE, pre.REPO
TASK = "V2_2_2_STAGE_B_TRUCK_P2D_INPUT_ADMISSION_PREFLIGHT_R1"
CONTRACTS = [
    "docs/tasks/V2_2-P1F-project-truck-input-and-p1-closure.md",
    "docs/tasks/V2_2-P2B1-truck-maneuver-template-contract.md",
    "docs/tasks/V2_2-P2D-access-routing-and-truck-validation.md",
    "docs/tasks/V2_2_2-R13-parameterized-truck-preview.md",
    "docs/tasks/V2_2-P2A-site-geometry-foundation.md",
    "docs/tasks/V2_2_2-version-plan.md",
    "backend/src/cold_storage/modules/layout/domain/project_truck_input.py",
    "backend/src/cold_storage/modules/layout/domain/truck_maneuver.py",
    "backend/src/cold_storage/modules/layout/domain/truck_parameter_input.py",
    "backend/src/cold_storage/modules/layout/domain/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/access_routing.py",
    "backend/src/cold_storage/modules/layout/application/global_composition_solver.py",
    "backend/src/cold_storage/modules/layout/application/site_geometry.py",
    "backend/src/cold_storage/modules/layout/application/p1_project_handoff.py",
    "backend/src/cold_storage/modules/layout/domain/construction_diversity.py",
    "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json",
    "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.provenance.json",
    "docs/tasks/V2_2_2-R14-truck-mcp-integration.md",
]


def write(name: str, value: Any) -> None:
    (HERE / name).write_bytes(pre.encode(value))


def citation(path: str, token: str) -> dict[str, Any]:
    lines = (REPO / path).read_text().splitlines()
    index = next(i for i, line in enumerate(lines, 1) if token in line)
    return {
        "path": path,
        "line": index,
        "quote": lines[index - 1].strip(),
        "source_sha256": pre.sha((REPO / path).read_bytes()),
    }


def protected_history() -> dict[str, Any]:
    files = set(CONTRACTS)
    for folder in (
        pre.BASELINE,
        HERE.parent / "owner-functional-input-contract-r1",
        HERE.parent / "owner-functional-input-contract-r2",
        HERE.parent / "owner-v2-packing-station-project-evidence-r2",
    ):
        path = folder / "source_manifest.json"
        files.add(path.relative_to(REPO).as_posix())
        manifest = pre.read(path.read_bytes())
        for relative, item in manifest["files"].items():
            expected = item if isinstance(item, str) else item["sha256"]
            original = folder / relative
            pre.require(
                pre.sha(original.read_bytes()) == expected, "HISTORICAL_MANIFEST_HASH_CHANGED"
            )
            files.add(original.relative_to(REPO).as_posix())
    catalog = pre.read((pre.BASELINE / "sources.json").read_bytes())
    files.update(row["svg_path"] for row in catalog["candidates"])
    result = {}
    for name in sorted(files):
        raw = (REPO / name).read_bytes()
        frozen = subprocess.check_output(["git", "show", pre.REFERENCE_HEAD + ":" + name], cwd=REPO)
        pre.require(raw == frozen, "PROTECTED_GIT_BYTES_CHANGED:" + name)
        result[name] = pre.sha(raw)
    return {
        "STATUS": "PASS",
        "REFERENCE_HEAD": pre.REFERENCE_HEAD,
        "FILES": result,
        "HISTORICAL_REAL_LAYOUTS": 8,
        "P2D_FULL_PASS_COUNT": 0,
        "PRODUCTION_AUTHORITY_CHANGED": False,
    }


def gap_matrix(authorities: dict[str, Any], raw_fixture: dict[str, Any]) -> list[dict[str, Any]]:
    truck = raw_fixture["truck_access"]
    base = {
        "PROJECT_ID": truck["project_id"],
        "SOURCE_ID": None,
        "DOCUMENT_REVISION": None,
        "SOURCE_SHA256": None,
    }
    specifications = [
        (
            "vehicle_width_m",
            truck["vehicle_width_m"],
            "REFERENCE_ONLY",
            "P1F_PROJECT_INPUT",
            "实测/车型规格书车宽、适用项目及批准选型记录",
            "P1F",
        ),
        (
            "vehicle_length_m",
            truck["vehicle_length_m"],
            "REFERENCE_ONLY",
            "P1F_PROJECT_INPUT",
            "车型规格书车长、版本、参考点与项目适用性",
            "P1F",
        ),
        (
            "vehicle_type_model_and_revision",
            None,
            "UNAVAILABLE",
            "PROJECT_VEHICLE_EVIDENCE",
            "制造商、型号、修订和有来源的实际车辆尺寸",
            "SOURCE_ADMISSION",
        ),
        (
            "project_vehicle_source_bytes",
            None,
            "UNAVAILABLE",
            "P1F_R13_SOURCE_BYTES",
            "原始设备/车辆资料字节与实际SHA；示例a/b摘要不可替代",
            "SOURCE_ADMISSION",
        ),
        (
            "site_truck_entrance_segment",
            authorities["typed_site"]["entrances"]["truck_entrance"],
            "SOURCE_BYTES_VERIFIED",
            "FROZEN_TYPED_SITE",
            "已有参考点定位线段；与实测开口之间的工程映射仍需确认",
            "SITE_BINDING",
        ),
        (
            "measured_gate_clear_opening",
            None,
            "UNAVAILABLE",
            "R13_ENTRANCE_CLEAR_OPENING_SEGMENT",
            "带坐标、净宽和现场测量依据的有效开口线段",
            "TRUCK_INPUT",
        ),
        (
            "gate_clearance_and_inward_direction",
            None,
            "UNAVAILABLE",
            "PROJECT_GATE_AND_TEMPLATE_FRAME",
            "通行方向、限制及显式安全净空依据；不得默认半径或余量",
            "TRUCK_INPUT",
        ),
        (
            "required_maneuver_classes",
            None,
            "UNAVAILABLE",
            "P2B1_PROJECT_REQUIREMENT",
            ("声明本项目需要的类别；P2D靠台要求DOCK_REVERSE，不能无依据强制全部三类"),
            "P2B1",
        ),
        (
            "bound_maneuver_project_input",
            None,
            "UNAVAILABLE",
            "P1F_BOUND_P2B1_OPTION_C",
            "与项目和车宽车长一致的完整模板、姿态及绑定Hash",
            "P2D",
        ),
        (
            "maneuver_source_bytes_and_revision",
            None,
            "UNAVAILABLE",
            "P2B1_R13_SOURCE_PROVENANCE",
            ("直行/所需转弯/倒靠模板及完整扫掠包络、图号、修订、来源字节"),
            "SOURCE_ADMISSION",
        ),
        (
            "actual_shipping_loading_face",
            "PER_CANDIDATE_SEE_FACE_MATRIX",
            "INPUT_VALIDATED_NOT_ROUTE_PASS",
            "P2C_SELECTED_SHIPPING_LONG_EDGE",
            ("当前长边几何可复核；实际装卸面确认与候选身份需逐套批准"),
            "P2D_CANDIDATE_BINDING",
        ),
        (
            "dock_face_project_approval",
            None,
            "PROJECT_APPROVAL_REQUIRED",
            "PROJECT_LOADING_INTERFACE",
            "装卸平台与车辆到达姿态、实际接口设计确认",
            "ENGINEERING_REVIEW",
        ),
        (
            "site_obstacles",
            authorities["typed_site"]["obstacles"]["hard_obstacles"],
            "SOURCE_BYTES_VERIFIED",
            "TYPED_SITE_FULL_HARD_OBSTACLES",
            "冻结场地三块禁建障碍原样保留；不等同于道路可通行批准",
            "P2D",
        ),
        (
            "approved_truck_road_use_area",
            None,
            "UNAVAILABLE",
            "PROJECT_SITE_ENGINEERING",
            ("道路用途、承载/通行限制及可用区域；buildable不等于批准行车道路"),
            "ENGINEERING_REVIEW",
        ),
        (
            "personnel_truck_conflict_review",
            None,
            "ENGINEERING_REVIEW_REQUIRED",
            "P1_P2D_PERSONNEL_TRUCK_POLICY",
            "结合该候选人员通道和实际Truck包络复核，不跨候选复制",
            "P2D",
        ),
        (
            "template_approval_and_review_identity",
            None,
            "PROJECT_APPROVAL_REQUIRED",
            "EXISTING_PROJECT_APPROVAL_AUTHORITY",
            ("审批记录及专业审核身份；Hash或调用方APPROVED不证明审批有效"),
            "ENGINEERING_REVIEW",
        ),
    ]
    items = []
    for field, value, status, authority, evidence, stage in specifications:
        item = {
            **base,
            "FIELD_NAME": field,
            "EXPECTED_AUTHORITY": authority,
            "CURRENT_VALUE": value,
            "CURRENT_STATUS": status,
            "REQUIRED_EVIDENCE": evidence,
            "BLOCKING_STAGE": stage,
            "REMEDIATION_ACTION": (
                "取得项目真实资料并按原合同复核；本任务不修改Authority、不执行搜索"
            ),
        }
        if field in ("vehicle_width_m", "vehicle_length_m"):
            item.update(
                SOURCE_ID="CANONICAL_REGRESSION_FIXTURE_NOT_SELECTED_TRUCK",
                DOCUMENT_REVISION="input_v3",
                SOURCE_SHA256=pre.sha(
                    (
                        REPO / ("backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json")
                    ).read_bytes()
                ),
            )
        elif field in ("site_truck_entrance_segment", "site_obstacles"):
            item.update(
                SOURCE_ID="FROZEN_TYPED_SITE",
                DOCUMENT_REVISION="schema@1.0.0_NOT_SURVEY_REVISION",
                SOURCE_SHA256=pre.sha(
                    (pre.BASELINE / "inputs/server_authorities.json").read_bytes()
                ),
            )
        items.append(item)
    return items


def evidence_index(artifact_root: Path) -> dict[str, Any]:
    """Bounded filename review; known synthetic/regression records never become approval."""
    pattern = re.compile(("truck|vehicle|maneuver|货车|车辆|装卸|大门|门洞|loading|gate"), re.I)
    discovered = []
    for root, alias in (
        (REPO / "docs", "REPOSITORY/docs"),
        (REPO / "backend/tests/fixtures", "REPOSITORY/backend/tests/fixtures"),
        (artifact_root, "PROJECT_ARTIFACTS"),
    ):
        names = subprocess.run(
            ["rg", "--files", str(root)], capture_output=True, text=True, check=False
        ).stdout.splitlines()
        for name in names:
            path = Path(name)
            rel = path.relative_to(root)
            if any(
                part in ("archives", ".git", ".venv", "__pycache__", "dependencies")
                or part.startswith(("readback-", "delivery-", "r2-delivery-"))
                or "grant" in part.lower()
                for part in rel.parts
            ):
                continue
            if (
                HERE.name in rel.parts
                or not pattern.search(path.name)
                or path.suffix.lower() not in (".pdf", ".dwg", ".dxf", ".jpg", ".png", ".json")
            ):
                continue
            # Filename discovery is not a content review. Avoid copying private documents.
            discovered.append(
                {
                    "SOURCE_PATH_REFERENCE": alias + "/" + rel.as_posix(),
                    "STATUS": "DISCOVERED_NAME_ONLY_NOT_ADMITTED",
                    "SOURCE_SHA256": None,
                    "PROJECT_APPLICABILITY": "REVIEW_REQUIRED",
                    "SELECTION_APPROVAL": "NOT_GRANTED",
                }
            )
    known = []
    for relative, classification in (
        (
            "r12-truck-p2d-engineering-validation/truck_input_inventory.json",
            "HISTORICAL_MISSING_INPUT_AUDIT",
        ),
        ("r13-truck-parameterized/synthetic_input.json", "SYNTHETIC_TEST_ONLY"),
    ):
        path = artifact_root / relative
        raw = path.read_bytes()
        record = pre.read(raw)
        summary: dict[str, Any] = {
            "PATH_REFERENCE": "PROJECT_ARTIFACTS/" + relative,
            "SOURCE_SHA256": pre.sha(raw),
            "STATUS": classification,
            "PROJECT_ADMISSION": "BLOCKED",
        }
        if classification == "HISTORICAL_MISSING_INPUT_AUDIT":
            summary.update(
                owner_input_found=record["owner_input_found"],
                owner_input_verified=record["owner_input_verified"],
                limitation=(
                    "Historical bounded search, not a universal assertion about Owner records"
                ),
            )
        else:
            summary.update(
                mode=record.get("mode"),
                NOTE="R13 synthetic bytes are not actual project vehicle evidence",
            )
        known.append(summary)
    return {
        "KNOWN_REVIEWED_RECORDS": known,
        "FILENAME_DISCOVERY": sorted(discovered, key=lambda v: v["SOURCE_PATH_REFERENCE"]),
        "SCOPE": (
            "Repository docs/fixtures and this pr"
            "oject artifacts only; no private hom"
            "e/other projects, archive/Grant stor"
            "es or mirror contents"
        ),
        "LIMITATION": (
            "Name-only hits unreviewed; R12 inven"
            "tory and R13 synthetic source read e"
            "xplicitly. No authenticated selected"
            " vehicle/gate/template package suppl"
            "ied."
        ),
        "PROJECT_SELECTED_TRUCK": "UNAVAILABLE",
        "PROJECT_TRUCK_INPUT_ADMISSION": "BLOCKED",
    }


def build(artifact_root: Path) -> None:
    authorities, rows = pre.load_sealed(artifact_root)
    report = pre.batch(artifact_root)
    pre.require(
        all(
            v[("CANDIDATE_PREFLIGHT_STATUS")] == ("PROJECT_INPUT_BLOCKED")
            for v in report["CANDIDATES"]
        ),
        "UNEXPECTED_SOURCE_OR_HISTORICAL_STATE",
    )
    write("eight-candidate-preflight.json", report)
    fixture = pre.read(
        (REPO / ("backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json")).read_bytes()
    )
    p1f = validate_project_truck_input(fixture["truck_access"])
    binding = validate_truck_maneuver_project_binding(
        fixture["truck_access"], fixture["truck_maneuver"]
    )
    write(
        "reference-truck-contract-audit.json",
        {
            "SOURCE": "Owner-ingested regression fixture; not current project Truck approval",
            "P1F_REVALIDATION": p1f,
            (
                "P2B1_REFERENCE_INPUT_COMPLETE"
            ): binding.maneuver_project_input.template_input_complete,
            "REFERENCE_REQUIRED_CLASSES": list(
                binding.maneuver_project_input.requirement.required_maneuver_classes
            ),
            "STAGE_B_ACTUAL_BINDING": None,
            "REFERENCE_BINDING_HASH_NOT_ADMITTED": binding.canonical_result_hash,
            "SOURCE_BYTES_FOR_REFERENCED_A_B_DIGESTS": "UNAVAILABLE",
            "IMPORTANT": (
                "Old v2.2.1 fixture PASS is historica"
                "l regression evidence, not current r"
                "eal Truck/P2D acceptance"
            ),
        },
    )
    status_fields = (
        "candidate_id",
        "geometry_hash",
        "source_application_hash",
        "zone_count",
        "must_pass_count",
        "non_truck_access_pass_count",
        "truck_route_status",
        "truck_route_codes",
        "source_truck_maneuver_binding_hash",
        "truck_search_provenance",
        "p2_complete",
        "HISTORICAL_TRUCK_STATE",
        "source_site_geometry_hash",
        "source_p1_handoff_hash",
    )
    write(
        "eight-candidate-truck-status.json",
        {
            "CANDIDATES": [{k: v[k] for k in status_fields} for v in report["CANDIDATES"]],
            "CANONICAL_PLAN_HASH": canonical_hash(authorities["canonical_zone_plan"]),
            "P1_HASH": canonical_hash(authorities["p1_handoff"]),
            "SITE_HASH": canonical_hash(authorities["typed_site"]),
            "P1F_INPUT_COMPLETE_NOT_DOCUMENT_VERIFIED": p1f["project_truck_input_complete"],
            "ACTUAL_STAGE_B_NULL_BINDINGS": 8,
            "NEW_SEARCHES": 0,
        },
    )
    gaps = gap_matrix(authorities, fixture)
    write("truck-project-input-gap-matrix.json", gaps)
    faces = []
    for row, result in zip(rows, report["CANDIDATES"], strict=True):
        engine = row["projection"]["engineering_validation"]
        people_ids = {
            v["requirement_identity"]
            for v in engine["access_results"]
            if v["flow_kind"] == "PEOPLE"
        }
        faces.append(
            {
                "candidate_id": result["candidate_id"],
                **result["LOADING_FACE_FACTS"],
                "TRUCK_CONTEXT_HASH": result["CANDIDATE_TRUCK_CONTEXT_HASH"],
                "SOURCE_SITE_HASH": engine["source_site_geometry_hash"],
                "TRUCK_ENTRANCE": authorities["typed_site"]["entrances"]["truck_entrance"],
                "BUILDING_FOOTPRINT": engine["building_footprint"],
                "PERSONNEL_CORRIDORS": [
                    v for v in engine["corridors"] if v["requirement_identity"] in people_ids
                ],
                "HARD_OBSTACLES": authorities["typed_site"]["obstacles"]["hard_obstacles"],
                "ROAD_AUTHORITY": "UNAVAILABLE_NOT_DERIVED_FROM_BUILDABLE_SPACE",
                "INDEPENDENT_TRUCK_VALIDATION_REQUIRED": True,
                "ROUTE_FEASIBILITY": "NOT_EVALUATED",
            }
        )
    write(
        "truck-site-loading-face-matrix.json",
        {
            "CANDIDATES": faces,
            "ALL_SAME_SITE_AND_P1": len(
                {v["source_site_geometry_hash"] for v in report["CANDIDATES"]}
            )
            == 1
            and len({v["source_p1_handoff_hash"] for v in report["CANDIDATES"]}) == 1,
            "DISTINCT_LOADING_FACE_GEOMETRIES": len({v["FACE_HASH"] for v in faces}),
            ("DISTINCT_CANDIDATE_TRUCK_CONTEXTS"): len({v["TRUCK_CONTEXT_HASH"] for v in faces}),
            "RESULT_TRANSFER_ALLOWED": False,
        },
    )
    write("truck-evidence-index.json", evidence_index(artifact_root))
    write(
        "truck-p2d-admission-contract.json",
        {
            "IDENTITY": pre.IDENTITY,
            "VERSION": pre.VERSION,
            "REFERENCE_HEAD": pre.REFERENCE_HEAD,
            "PIPELINE": [
                "PINNED_CATALOG_RAW_PROJECTION_AND_SVG_BYTES",
                "ORIGINAL_P1F_REFERENCE_VALIDATION",
                "ORIGINAL_P2B1_PROJECT_BINDING",
                "R13_INPUT_ONLY_PREDICATE_SUBSET",
                "CANDIDATE_LOADING_SITE_CONTEXT_AUDIT",
                "PROJECT_ENGINEERING_REVIEW_REQUIRED",
            ],
            "TRUCK_STATUS_VOCABULARY": [
                "PROJECT_INPUT_BLOCKED",
                "TRUCK_SEARCH_EXECUTED_WITHOUT_VALIDATED_ROUTE_NOT_GLOBAL_INFEASIBILITY",
                "TRUCK_ROUTE_ENGINEERING_REVIEW_REQUIRED",
                "TRUCK_ROUTE_VALIDATED_NOT_P2D_FULL_PASS",
            ],
            "EVIDENCE_STATUS_VOCABULARY": [
                "UNAVAILABLE",
                "REFERENCE_ONLY",
                "SOURCE_BYTES_VERIFIED",
                "PROJECT_APPLICABILITY_REVIEW_REQUIRED",
                "PROJECT_APPROVAL_REQUIRED",
                "INPUT_VALIDATED_NOT_ROUTE_PASS",
                "ENGINEERING_REVIEW_REQUIRED",
            ],
            "REQUIRED_CLASSES_POLICY": (
                "Use project binding classes; P2B1 do"
                "es not require all three. P2D additi"
                "onally needs DOCK_REVERSE; current S"
                "tage B binding/required classes abse"
                "nt, legacy three-class fixture is re"
                "ference only."
            ),
            "APPROVAL_BOUNDARY": (
                "No parallel approver: original R13 m"
                "atching documentary record and all n"
                "ative checks are left to separately "
                "authorized original execution. SHA/v"
                "erified/APPROVED labels never approv"
                "e a project."
            ),
            "SAFE_REUSE": (
                "Pure P1F, P2B1, original P2D selecte"
                "d loading-face predicates and immuta"
                "ble result hash reader; R13 _evidenc"
                "e/_vehicle_body/_verify_body_envelop"
                "es only. Never call preview, route_s"
                "ite_placement or validate_truck_mane"
                "uver_chain."
            ),
            "CURRENT_INPUT_ONLY_LIMITATION": (
                "R13 full validation is coupled to se"
                "arch. Static subset cannot certify f"
                "ull R13 input validity, documentary "
                "approval, route or P2D. TRUCK_SEARCH"
                "_READY=false until reviewed project "
                "input and separately authorized orig"
                "inal validation."
            ),
            "FORMAL_DOCUMENT_REVISION": (
                "Schema version is not source drawing"
                " revision. Actual revision and proje"
                "ct applicability need original docum"
                "ent/manual review; unavailable here."
            ),
            "P2D_FULL_PASS_COUNT": 0,
            "PROJECT_TRUCK_INPUT_ADMISSION": "BLOCKED",
            "REAL_TRUCK_SEARCHES": 0,
            "REAL_FACTORY_SOLVES": 0,
            "NATIVE_SOLVER_CALLS": 0,
            "NEW_OWNER_GRANT": False,
        },
    )
    references = [
        citation(CONTRACTS[0], "本验证器不读取资料"),
        citation(CONTRACTS[1], "no project is"),
        citation(CONTRACTS[2], "The first entry must be"),
        citation(CONTRACTS[3], "Reference-point search segment"),
        citation(CONTRACTS[4], "Entrances are positive-length"),
        citation(CONTRACTS[6], "evidence_contents_verified"),
        citation(CONTRACTS[7], "def validate_truck_maneuver_project_binding"),
        citation(CONTRACTS[8], "def _evidence"),
        citation(CONTRACTS[8], "result = routing.validate_truck_maneuver_chain"),
        citation(CONTRACTS[9], "if binding is None:"),
        citation(CONTRACTS[9], "desired_entries = _segment_lattice_points"),
        citation(CONTRACTS[10], "def _validate_selected_loading_face"),
        citation(CONTRACTS[11], "application = route_site_placement("),
        citation(CONTRACTS[12], "truck = normalize_segment"),
        citation(CONTRACTS[12], '"truck_entrance": segment_to_dict(truck)'),
    ]
    write("source-contract-references.json", references)
    write("historical-evidence-integrity.json", protected_history())
    request = (
        "# Truck项目工程资料索取清单\n"
        "\n当前八套均为输入阻断，不是搜索后不"
        "可通行。请提供可核验原件；本清单不签"
        "发执行或审批授权。\n\n"
    )
    request += "| FIELD | 当前状态 | 所需资料 | 阻断阶段 |\n|---|---|---|---|\n"
    request += "\n".join(
        "| "
        + " | ".join(
            str(v[k])
            for k in ("FIELD_NAME", "CURRENT_STATUS", "REQUIRED_EVIDENCE", "BLOCKING_STAGE")
        )
        + " |"
        for v in gaps
    )
    request += (
        "\n\n原始图纸和内部运输协议保留获授权"
        "的本地证据目录，公开提交前必须取得传"
        "播许可并脱敏。不得用旧示例或公共车型"
        "填空。\n"
    )
    (HERE / "project-truck-information-request.md").write_text(request)


def manifest() -> None:
    write(
        "source_manifest.json",
        {
            "task": TASK,
            "reference_head": pre.REFERENCE_HEAD,
            "self_excluded": True,
            "files": {
                p.relative_to(HERE).as_posix(): pre.sha(p.read_bytes())
                for p in sorted(HERE.rglob("*"))
                if p.is_file()
                and "__pycache__" not in p.parts
                and p.name != ("source_manifest.json")
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    if not args.manifest_only:
        parser.error("--artifact-root required") if args.artifact_root is None else build(
            args.artifact_root
        )
    manifest()
