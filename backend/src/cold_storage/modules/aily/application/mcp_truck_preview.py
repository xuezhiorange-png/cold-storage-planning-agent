"""Tool 8 JSON adapter. All Truck engineering and SVG remain owned by R13."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from importlib.resources import files
from typing import Any, cast

from cold_storage.modules.layout.application.truck_preview import invoke_truck_preview

PREVIEW_TRUCK_TOOL_NAME = "preview_truck"
MAX_TRUCK_ARGUMENT_BYTES = 12_000_000  # Same bounded JSON limit as the R13 CLI.

_DESCRIPTIONS = {
    "schema_version": "独立兼容契约版本，固定1.0.0。",
    "mode": "SYNTHETIC_TEST仅软件测试；OWNER_PROJECT必须提供真实资料，不能自动获得工程批准。",
    "vehicle_type": "车辆分类标识，不产生默认长宽或转弯半径。",
    "vehicle_body": "模板局部坐标下真实车身矩形，单位m；坐标参考点必须明确。",
    "vehicle_source_reference": "车辆尺寸来源文件标识，必须与上传原件对应。",
    "truck_access": "原P1F项目车辆输入：项目ID、实际长宽及三类工程资料引用。不得编造参数。",
    "truck_maneuver": "原Option C项目模板：直线、转弯、倒车的完整包络、坐标框架和进出姿态。",
    "entrance": "区分入口定位线段、实际开口、净宽、测量及净空来源；不能用1mm定位线冒充门宽。",
    "shipping_loading_face": "Shipping实际长边装卸面端点，单位m。",
    "loading_face_reference": "装卸面工程来源文件标识。",
    "site_geometry": "原有场地边界、完整硬障碍、房间矩形及人员通道，不重新求解布局。",
    "evidence": "实际文件Base64字节和SHA256；最多32份，每份1MiB、总8MiB，禁止填占位摘要。",
    "approval_reference": "审批原件标识；OWNER_PROJECT须绑定当前输入摘要，摘要不认证审批人身份。",
}


def preview_truck_input_schema() -> dict[str, Any]:
    """Fresh package-owned copy of R13 Schema; only Chinese descriptions added."""
    schema = cast(
        dict[str, Any],
        json.loads(files(__package__).joinpath("truck_preview.schema.json").read_text()),
    )
    for key, description in _DESCRIPTIONS.items():
        schema["properties"][key]["description"] = description
    return schema


def _error(
    code: str, *, missing: list[str] | None = None, field: str = "arguments"
) -> dict[str, Any]:
    return {
        "ok": False,
        "reply_kind": "truck_preview",
        "error": {
            "code": code,
            "message": "货车参数验证未完成，请按缺项或错误码补充原始工程资料。",
            "field_path": field[:160],
            "missing_keys": [s[:160] for s in (missing or [])],
            "ask_operator": (
                "请提供车辆实际长宽、入口实际净宽与测量依据、机动模板及对应原文件。"
                "请核对原文件SHA256；不要使用默认车型、占位摘要或编造参数。"
            ),
        },
    }


def invoke_preview_truck_tool(arguments: object) -> dict[str, Any]:
    """Separate successful invocation from engineering PASS; no raw input logging."""
    if not isinstance(arguments, Mapping):
        return _error("INVALID_TRUCK_PREVIEW_INPUT")
    try:
        size = 0
        for part in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(arguments):
            size += len(part.encode("utf-8"))
            if size > MAX_TRUCK_ARGUMENT_BYTES:
                return _error("TRUCK_DOCUMENT_RESOURCE_LIMIT")
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        return _error("INVALID_TRUCK_PREVIEW_INPUT")
    try:
        raw = invoke_truck_preview(arguments)
    except Exception:
        # Do not expose stack traces, file bytes, exception strings or credentials.
        return _error("TRUCK_PREVIEW_INTERNAL_ERROR")
    if not raw.get("input_complete"):
        missing = [str(s) for s in raw.get("missing_fields", [])]
        error = _error(str(raw["status"]), missing=missing)
        error["calculation_hash"] = raw["canonical_result_hash"]
        return error
    svg = raw.get("svg")
    return {
        "ok": True,
        "reply_kind": "truck_preview",
        "status": raw["status"],
        "engineering_pass": raw["engineering_preview_validated"],
        "calculation_hash": raw["canonical_result_hash"],
        "result": raw,
        "truck": raw.get("truck", {}),
        "drawing": {"svg": svg, "svg_sha256": "sha256:" + sha256(svg.encode()).hexdigest()}
        if isinstance(svg, str)
        else None,
        "synthetic_test_only": raw["SYNTHETIC_TEST_ONLY"],
        "real_project_approved": raw["REAL_PROJECT_APPROVED"],
        "requires_review": raw["requires_review"],
        "p2_complete": raw["P2_COMPLETE"],
        "server_replay_accepted": raw["SERVER_REPLAY_ACCEPTED"],
    }
