"""Reproduce only R2 offline artifacts. No old builders, solver or grants."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import offline_project_diagnostic as diagnostic
import offline_project_input_adapter as adapter

HERE = adapter.HERE
REPO = HERE.parents[3]
REFERENCE = "a48a0ec6830b15ce0d37f0234c99e916743c477e"
TASK = "V2_2_2_OWNER_V2_PACKING_STATION_PROJECT_INPUT_ADMISSION_R2"
EXCLUDED = {".git", ".venv", "__pycache__", "archives", "backend", "node_modules"}
FIELDS = [
    (
        "PROJECT_AND_FACTORY_ID",
        "项目工艺设计条件及设备适用性说明",
        "防止跨项目套用",
        "具备项目身份和版本的设计文件",
        "全部诊断",
    ),
    (
        "EQUIPMENT_BODY_LENGTH_WIDTH_HEIGHT",
        "设备总图及型号规格书",
        "设备实体及高度独立记录",
        "带尺寸标注、图号、修订版的总图；不可按图片像素估算",
        "设备实体包络",
    ),
    (
        "SELECTION_EVIDENCE",
        "选型评审或批准记录",
        "公开参考与项目选型不同",
        "可核实的既有审批文件；文件Hash不替代审批",
        "选型状态记录；适配器无批准权",
    ),
    (
        "INFEED_OUTFEED_REJECT_INTERFACES",
        "输送接口及物流图",
        "进料、包材、成品与剔除物分别连通",
        "有局部坐标和设备方向的接口尺寸",
        "物料路径",
    ),
    (
        "THREE_OPERATOR_TASKS_AND_POSITIONS",
        "三人任务及站位布置图",
        "3人/台不等于站位已可用",
        "每人任务、站位、朝向、动作区、入口路径的工艺复核",
        "三人适配",
    ),
    (
        "MATERIAL_CARRIER_ENVELOPES",
        "周转箱、车及包材规格",
        "物料占用独立于设备尺寸",
        "型号、外廓、运输方式和使用状态",
        "供出料占用",
    ),
    (
        "PERSONNEL_AND_MATERIAL_ROUTE_WIDTHS",
        "通道与净空设计条件",
        "历史房间Portal不证明室内净宽",
        "分别有来源的路径中心线、全宽与净空要求",
        "全宽扫掠校核",
    ),
    (
        "FOUR_STATE_OCCUPANCY",
        "生产、交班、清洗、检修工况图",
        "非同时不等于自动允许共用",
        "设备常驻、开启范围、共享条件及审核记录",
        "工况碰撞与共享复核",
    ),
    (
        "SHIFT_CHANGE_CLEANING_DURATION_BUFFER",
        "交班清洁SOP及生产节拍",
        "不得默认零耗时或零缓冲",
        "独立确认时长、人员、物料与状态",
        "时间空间共用",
    ),
    (
        "MAINTENANCE_ACCESS_AND_GUARD_SWING",
        "维护手册与护罩开启图",
        "设备本体不包含检修空间",
        "明确检修侧、开门包络、所需通行",
        "清洁检修",
    ),
    (
        "ROOM_CLEAR_AND_PORTAL_BOUNDARIES",
        "建筑净尺寸及工艺接口图",
        "房间外包络不等于净可用面积",
        "带墙体、门、障碍及Portal身份的设计资料",
        "18/28台适配仍未评价",
    ),
]


def write(name: str, value: Any) -> None:
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(adapter.encode(value))


def search_index(project_files: Path | None = None) -> dict[str, Any]:
    """Bounded metadata search only; no archive/Grant/private contract content reads."""
    seed = adapter.read_json((adapter.R1 / "equipment-evidence-index.json").read_bytes())
    records = []
    for old in seed["RECORDS"]:
        record: dict[str, Any] = {key: None for key in adapter.META}
        record.update(
            SOURCE_ID=old["SOURCE_ID"],
            SOURCE_PATH_OR_URL=old["SOURCE_PATH_OR_URL"],
            SOURCE_FILE_SHA256=old.get("FILE_SHA256"),
            SOURCE_TYPE="PUBLIC_MANUFACTURER_REFERENCE"
            if old["SOURCE_PATH_OR_URL"].startswith("https://")
            else "PRIOR_DOCUMENT_OR_TEST_REFERENCE",
            PROJECT_APPLICABILITY="NOT_PROVEN_AS_PROJECT_EQUIPMENT",
            SELECTION_STATUS="UNAVAILABLE",
            REVIEW_STATUS="NOT_ADMITTED_PROJECT_GEOMETRY",
            DOCUMENT_REVISION=old.get("DOCUMENT_VERSION"),
            DIMENSION_CALLOUT=old.get("DIMENSION_EVIDENCE"),
            DIMENSION_UNIT=None,
        )
        if not old["SOURCE_PATH_OR_URL"].startswith("http"):
            path = REPO / old["SOURCE_PATH_OR_URL"]
            record["CURRENT_BYTES_REVERIFIED"] = path.is_file() and adapter.sha(
                path.read_bytes()
            ) == old.get("FILE_SHA256")
        else:
            record["CURRENT_BYTES_REVERIFIED"] = None
            record["REFERENCE_ONLY"] = "Prior task reference, not refetched or promoted in R2"
        records.append(record)
    pattern = re.compile(
        "包装|分选|工位|输送|周转|设备总图|packing|packaging|conveyor|supplier|workstation", re.I
    )
    hits = []
    roots = [
        (REPO / "docs", "REPOSITORY/docs"),
        (REPO / "backend/tests/fixtures", "REPOSITORY/backend/tests/fixtures"),
    ]
    if project_files is not None:
        roots.append((project_files, "PROJECT_FILES"))
    for root, alias in roots:
        names = (
            subprocess.run(
                ["rg", "--files", str(root)], capture_output=True, text=True, check=False
            ).stdout.splitlines()
            if root.exists()
            else []
        )
        for name in names:
            path = Path(name)
            rel = path.relative_to(root)
            if any(
                part in EXCLUDED
                or part.startswith(("readback-", "delivery-"))
                or "grant" in part.lower()
                for part in rel.parts
            ):
                continue
            if (
                path.is_relative_to(HERE)
                or HERE.name in rel.parts
                or path.suffix.lower()
                not in (".pdf", ".dwg", ".dxf", ".png", ".jpg", ".jpeg", ".step", ".stp")
                or not pattern.search(str(rel))
            ):
                continue
            hits.append(
                {
                    "PATH_REFERENCE": alias + "/" + rel.as_posix(),
                    "STATUS": "NAME_MATCH_ONLY_REQUIRES_MANUAL_CONTENT_AND_APPLICABILITY_REVIEW",
                    "SOURCE_FILE_SHA256": adapter.sha(path.read_bytes()),
                    "PROJECT_SELECTED_EQUIPMENT": "UNAVAILABLE",
                }
            )
    return {
        "IDENTITY": "PROJECT_EQUIPMENT_EVIDENCE_INDEX_R2",
        "REUSED_R1_INDEX_SHA256": adapter.sha(
            (adapter.R1 / "equipment-evidence-index.json").read_bytes()
        ),
        "SEARCH_SCOPE": {
            "ROOTS": [
                "REPOSITORY/docs",
                "REPOSITORY/backend/tests/fixtures",
                "PROJECT_FILES (cold-storage-planning-agent only)",
            ],
            "METHOD": (
                "Reverify prior index; bounded filename/format metadata search. "
                "No OCR, pixel measurement or raw archive/private Grant inspection."
            ),
            "EXCLUSIONS": sorted(EXCLUDED),
            "LIMITATION": (
                "Not a claim that Owner has no other documents; filename search "
                "cannot identify unlabelled equipment drawings."
            ),
        },
        "RECORDS": records,
        "ADDITIONAL_NAME_MATCHES": sorted(hits, key=lambda v: v["PATH_REFERENCE"]),
        "PROJECT_EQUIPMENT_CANDIDATES": 0,
        "PROJECT_SELECTED_EQUIPMENT": "UNAVAILABLE",
        "FINDING": (
            "Prior reviewed index contains no selected project station drawings. "
            "New matches are diagnostic/research artifacts, not authenticated project "
            "equipment evidence."
        ),
    }


def protected_history() -> dict[str, Any]:
    paths = set()
    names = [
        "owner-functional-input-contract-r1",
        "owner-functional-input-contract-r2",
        "owner-factory-p1-compatibility-readiness-r1",
        "owner-v2-packaging-area-geometry-calibration-r1",
        "owner-v2-three-person-packing-station-module-r1",
        "stage-b/layout-quality-baseline-01",
    ]
    for name in names:
        folder = HERE.parent / name
        raw = (folder / "source_manifest.json").read_bytes()
        paths.add(folder / "source_manifest.json")
        for relative, item in json.loads(raw)["files"].items():
            expected = item if isinstance(item, str) else item["sha256"]
            path = folder / relative
            assert adapter.sha(path.read_bytes()) == expected, (
                "Historical manifest mismatch: " + str(path)
            )
            paths.add(path)
    baseline = HERE.parent / "stage-b/layout-quality-baseline-01"
    source = adapter.read_json((baseline / "sources.json").read_bytes())
    for candidate in source["candidates"]:
        path = REPO / candidate["svg_path"]
        assert adapter.sha(path.read_bytes()) == candidate["svg_sha256"]
        assert (
            adapter.sha((baseline / candidate["input"]).read_bytes())
            == candidate["projection_sha256"]
        )
        paths.add(path)
    interfaces = adapter.read_json(
        (adapter.R1 / "sorting-room-interface-contract.json").read_bytes()
    )
    # Prior sealed real-layout review is the independent count/identity source.
    review = adapter.read_json(
        (
            HERE.parent
            / "owner-v2-packaging-area-geometry-calibration-r1/real-layout-interface-review.json"
        ).read_bytes()
    )
    assert len(review["layouts"]) == 8
    assert sum(len(v["actual_interfaces"]) for v in review["layouts"]) == 48
    assert interfaces
    for path in (
        "backend/src/cold_storage/modules/calculations/domain/zone_planning.py",
        "backend/src/cold_storage/modules/layout/application/sorting_dimension_authority.py",
        "docs/tasks/V2_2_2-version-plan.md",
        "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md",
    ):
        paths.add(REPO / path)
    mapping = {}
    for path in sorted(paths):
        rel = path.relative_to(REPO).as_posix()
        current = path.read_bytes()
        frozen = subprocess.run(
            ["git", "show", REFERENCE + ":" + rel], cwd=REPO, capture_output=True, check=True
        ).stdout
        assert current == frozen, "Protected source differs from reference: " + rel
        mapping[rel] = adapter.sha(current)
    return {
        "STATUS": "PASS",
        "FILES": mapping,
        "REAL_LAYOUTS": 8,
        "REAL_INTERFACES": 48,
        "R1_MODULE_SVGS": 8,
        "REFERENCE_HEAD": REFERENCE,
        "METHOD": "Sealed manifests, projection/SVG hashes and git reference bytes",
    }


def legacy_replay() -> dict[str, Any]:
    # Explicit read-only calculator import path also works from the CLI launcher.
    if str(REPO / "backend/src") not in sys.path:
        sys.path.insert(0, str(REPO / "backend/src"))
    path = HERE.parent / "owner-factory-p1-compatibility-readiness-r1/offline_compatibility.py"
    spec = importlib.util.spec_from_file_location("r2_readonly_legacy_replay", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.legacy_replay())


def build(project_files: Path | None = None) -> None:
    index = search_index(project_files)
    write("project-equipment-evidence-index.json", index)
    deny = sorted({adapter.sha(p.read_bytes()) for p in (adapter.R1 / "examples").rglob("*.json")})
    register = {
        "IDENTITY": "LocalStationEvidenceReviewRegisterV1",
        "SCOPE": "PROJECT_EVIDENCE_REVIEW",
        "PROJECT_ID": "PROJECT_INPUT_REQUIRED",
        "FACTORY_ID": "FACTORY_INPUT_REQUIRED",
        "SOURCES": {},
        "DENIED_SOURCE_HASHES": deny,
        "NOTE": (
            "Empty register: no sources approved for extraction. Local evidence review only, "
            "not Owner execution Grant or engineering/selection approval."
        ),
    }
    write("local-review-register.json", register)
    template: dict[str, Any] = {
        "IDENTITY": adapter.IDENTITY,
        "VERSION": adapter.VERSION,
        "PROJECT_ID": "PROJECT_INPUT_REQUIRED",
        "FACTORY_ID": "FACTORY_INPUT_REQUIRED",
        "DOCUMENTS": [],
        "DIMENSIONS": [],
        "MODULE_TEMPLATE": None,
        "STRUCTURAL_EVIDENCE": None,
    }
    write("project-input-template.json", template)
    write(
        "project-station-dimension-contract.json",
        {
            "IDENTITY": "ProjectStationDimensionRecordV1",
            "COORDINATE_UNIT": "integer mm",
            "ANGLE_UNIT": "deg, 0/90/180/270",
            "RECORD_FIELDS": [
                "RECORD_ID",
                "VALUE",
                "UNIT",
                "SOURCE_ID",
                "SOURCE_LOCATION",
                "DIMENSION_TYPE",
                "COORDINATE_REFERENCE",
                "EXTRACTION_METHOD",
                "MEASUREMENT",
                "TARGET_PATH",
                "COMPONENT_ID",
            ],
            "MISSING_VALUE": {"VALUE": None, "STATUS": "UNAVAILABLE"},
            "DISTINCT_DIMENSION_CLASSES": [
                "EQUIPMENT_BODY_DIMENSION",
                "WORKSTATION_MODULE_DIMENSION",
                "STATION_PITCH",
                "CLEAR_AISLE_DIMENSION",
                "ROOM_CLEAR_INTERNAL_DIMENSION",
                "BUILDING_EXTERNAL_DIMENSION",
            ],
            "ADAPTER_INPUT": (
                "Every geometry numeric leaf in R1 template must be null and filled once "
                "by source-bound record; independently sourced body L/W/H required. "
                "Height is trace-only; no 3D clearance claimed."
            ),
            "EXTRACTION": (
                "Structured JSON exact VALUE/UNIT/type/frame; unique explicit text callout. "
                "PDF text only with explicit CALLOUT_KEY, never drawing/image scale. "
                "Native CAD/image -> manual review."
            ),
            "COORDINATE_REFERENCE": (
                "STATION_LOCAL or ASSEMBLY_GLOBAL, consistent with R1 quarter-turn transforms"
            ),
            "NO_DEFAULTS": [
                "5.6m/3.0m station pitch",
                "8.0m/7.6m aggregate allowance",
                "room Portal width",
                "unknown operator positions",
            ],
            "PARTIAL_INPUT": (
                "Record missing values in template/checklist; complete geometry admission "
                "is blocked until all required callouts and reviewed module structure exist."
            ),
        },
    )
    write(
        "project-input-admission-contract.json",
        {
            "IDENTITY": adapter.IDENTITY,
            "VERSION": adapter.VERSION,
            "REUSED_MODULE": "PackingStationModuleV1",
            "STAGES": [
                "DISCOVERED",
                "INDEXED",
                "SOURCE_BYTES_VERIFIED",
                "DIMENSIONS_EXTRACTED",
                "GEOMETRY_NORMALIZED",
                "GEOMETRY_DIAGNOSTIC_COMPLETE",
                "ENGINEERING_REVIEW_REQUIRED",
            ],
            "DOCUMENT_FIELDS": list(adapter.META),
            "SOURCE_CLASSES": list(adapter.SOURCE_TYPES),
            "TRUST_BOUNDARY": (
                "Local reviewer and launcher pin immutable extraction-review register; "
                "request cannot supply review context or approved/verified flags. "
                "Register pin is operator-side configuration, not a caller security token."
            ),
            "REVIEW_CONTENT": (
                "Source bytes, full identity/revision/classification hash, exact structural "
                "citation hash and each dimension-record hash. Reviewer must verify actual "
                "source and project applicability outside this adapter."
            ),
            "REGISTER_PIN": adapter.sha(adapter.encode(register)),
            "LIMITATIONS": [
                "File SHA is not authenticity or engineering approval",
                "Trusted launcher compromise/register+pin replacement outside request threat model",
                "Structured/text callout extractor not a general drawing parser",
                "Selected/approved source class needs independent verifier, not implemented",
                "Test fixture issuer is SOFTWARE_TEST_ONLY, not real source review",
            ],
            "PROHIBITED_STAGES": ["ENGINEERING_APPROVED", "FORMAL_P1_AUTHORITY_APPROVED"],
            "SOURCE_STATUS": "No actual sources admitted; current default project request BLOCKED",
        },
    )
    missing = [
        {
            "FIELD": field,
            "REQUIRED_DOCUMENT": doc,
            "WHY_REQUIRED": why,
            "ACCEPTABLE_EVIDENCE": evidence,
            "CURRENT_STATUS": "UNAVAILABLE",
            "AFFECTED_CALCULATION": affected,
        }
        for field, doc, why, evidence, affected in FIELDS
    ]
    write(
        "missing-engineering-inputs.json",
        {
            "PROJECT_INPUT_ADMISSION": "BLOCKED",
            "ITEMS": missing,
            "FIT_18_TABLES": "NOT_EVALUATED",
            "FIT_28_TABLES": "NOT_EVALUATED",
        },
    )
    write(
        "engineering-review-matrix.json",
        {
            "ITEMS": [
                {
                    **item,
                    "ADAPTER_AUTHORITY": "SOURCE_AND_GEOMETRY_DIAGNOSTICS_ONLY",
                    "HUMAN_REVIEW_REQUIRED": True,
                }
                for item in missing
            ],
            "ENGINEERING_APPROVAL_GRANTED": False,
        },
    )
    write(
        "operator-layout-evidence.json",
        {
            "WORKERS_PER_PACKING_TABLE": 3,
            "SOURCE": "owner-factory-functional-inputs@2.0.0; prior unchanged Owner V2 record",
            "OPERATORS": [
                {
                    "OPERATOR_ID": f"OPERATOR_{i}",
                    "TASK": None,
                    "STANDING_POSITION": None,
                    "WORK_DIRECTION": None,
                    "REACH_ENVELOPE": None,
                    "ENTRY_PATH": None,
                    "SIMULTANEOUS_ACTIVITY": None,
                    "SOURCE_ID": None,
                }
                for i in range(1, 4)
            ],
            "OPERATOR_LAYOUT_STATUS": "REVIEW_REQUIRED",
            "OPERATOR_FIT_APPROVED": False,
        },
    )
    write(
        "material-flow-evidence.json",
        {
            "FLOWS": [
                {
                    "TYPE": kind,
                    "SOURCE_ID": None,
                    "ROUTE_SOURCE": None,
                    "ROUTE_WIDTH": None,
                    "ROUTE_STATE": None,
                    "ACTUAL_GEOMETRIC_CLEARANCE": None,
                    "COLLISION_STATUS": "NOT_EVALUATED",
                    "PERSONNEL_MATERIAL_CROSSING": "REVIEW_REQUIRED",
                    "FUNCTIONAL_REVIEW_STATUS": "REVIEW_REQUIRED",
                }
                for kind in (
                    "RAW_INPUT",
                    "MATERIAL_SUPPLY",
                    "BOX_REPLENISHMENT",
                    "REJECT_WASTE",
                    "PRODUCT_OUTFEED",
                    "PERSONNEL_ENTRY",
                    "CARRIER",
                    "CLEANING_MAINTENANCE",
                )
            ],
            "CLEAR_WIDTH_STATUS": "UNAVAILABLE",
            "ROOM_PORTAL_NOT_INTERNAL_AISLE_PROOF": True,
        },
    )
    write(
        "state-and-maintenance-evidence.json",
        {
            "STATES": [
                {
                    "STATE": state,
                    "SOURCE_ID": None,
                    "ACTUAL_OCCUPANCY": "UNAVAILABLE",
                    "STATIONARY_EQUIPMENT_OCCUPANCY": "MUST_REMAIN_WHEN_PRESENT",
                    "STATUS": "REVIEW_REQUIRED",
                }
                for state in ("NORMAL_PRODUCTION", "SHIFT_CHANGE", "CLEANING", "MAINTENANCE")
            ],
            "PACKING_TABLE_SHARED_BETWEEN_SHIFTS": True,
            "SHIFT_CHANGE_DURATION": None,
            "CLEANING_DURATION": None,
            "MAINTENANCE_ACCESS": None,
            "PRODUCTION_BUFFER": None,
            "SHARING_APPROVED": False,
        },
    )
    instructions = (
        "# 项目工程资料索取清单\n\n"
        "当前未找到可用于项目工位准入的已审核设备及三人作业资料。"
        "禁止用历史节距或合成示例填空。\n\n"
    )
    instructions += (
        "| FIELD | REQUIRED_DOCUMENT | WHY_REQUIRED | ACCEPTABLE_EVIDENCE | "
        "CURRENT_STATUS | AFFECTED_CALCULATION |\n|---|---|---|---|---|---|\n"
    )
    instructions += "\n".join(
        "| "
        + " | ".join(
            str(item[key])
            for key in (
                "FIELD",
                "REQUIRED_DOCUMENT",
                "WHY_REQUIRED",
                "ACCEPTABLE_EVIDENCE",
                "CURRENT_STATUS",
                "AFFECTED_CALCULATION",
            )
        )
        + " |"
        for item in missing
    )
    instructions += (
        "\n\n私有采购协议、图纸原件仅存本地获授权证据目录。"
        "公开仓库只保留允许公开的脱敏字段和Hash。"
        "审批记录需人工核实；本适配器不能授予选型或工程批准。\n"
    )
    (HERE / "project-information-request.md").write_text(instructions)
    with tempfile.TemporaryDirectory(prefix="r2-project-missing-") as tmp:
        output = Path(tmp) / "diagnostic"
        context = adapter.load_review_context(
            HERE / "local-review-register.json", adapter.sha(adapter.encode(register))
        )
        result = diagnostic.diagnose(template, context, HERE, output)
        write("project-source-verification.json", result)
        (HERE / "previews").mkdir(exist_ok=True)
        (HERE / "previews/project-input-required.svg").write_bytes(
            (output / "project-input-required.svg").read_bytes()
        )
    write("historical-evidence-integrity.json", protected_history())
    write("legacy-canonical-replay.json", legacy_replay())


def manifest() -> None:
    files = {
        p.relative_to(HERE).as_posix(): adapter.sha(p.read_bytes())
        for p in sorted(HERE.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.name != "source_manifest.json"
    }
    write(
        "source_manifest.json",
        {"task": TASK, "reference_head": REFERENCE, "self_excluded": True, "files": files},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--project-files", type=Path)
    args = parser.parse_args()
    if not args.manifest_only:
        build(args.project_files)
    manifest()
