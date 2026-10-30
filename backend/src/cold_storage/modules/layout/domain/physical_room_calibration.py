"""H5 equipment input vocabulary and necessary physical checks; no Authority.

All dimensions are explicit integer millimetres. Source/review is an application
boundary; geometric checks never establish a supplier selection or approval.
"""

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from cold_storage.modules.layout.domain.changing_room_motion import door_hits_box

IDENTITY = "h5-physical-input-calibration@1.0.0"
SEQUENCE = "OPEN_RETRIEVE_CLOSE_CHANGE_OPEN_STORE_CLOSE_EXIT"


@dataclass(frozen=True)
class PhysicalField:
    group: str
    label: str
    unit: str = "mm"
    minimum: int = 0
    choices: tuple[str, ...] = ()


def field_catalog() -> dict[str, PhysicalField]:
    fields = {}
    groups = {
        "柜体": {
            "unit_width_mm": "标准实体柜总宽",
            "unit_depth_mm": "实体柜总深",
            "cabinet_height_mm": "实体柜总高",
            "column_width_mm": "单列占用宽度/节距",
            "plinth_mm": "底座高度",
            "top_mm": "顶板厚度",
            "side_panel_mm": "侧板厚度",
            "back_panel_mm": "背板厚度",
            "shelf_mm": "层板厚度",
            "fixing_rear_mm": "后侧安装固定所需净空",
            "fixing_side_mm": "侧向安装固定所需净空",
            "fixing_top_mm": "顶部安装固定所需净空",
            "partial_unit_width_mm": "末端非整组实体柜总宽",
        },
        "柜门": {
            "door_leaf_width_mm": "柜门扇宽/扫掠半径",
            "door_leaf_height_mm": "柜门扇高",
            "door_leaf_thickness_mm": "柜门扇厚",
            "door_frame_mm": "门框侧向退让",
            "hinge_axis_offset_mm": "铰链轴距柜列侧边",
            "door_opening_clear_width_mm": "实际开口净宽",
            "door_opening_clear_height_mm": "实际开口净高",
        },
        "人体": {
            "static_width_mm": "静态站立宽",
            "static_depth_mm": "静态站立深",
            "body_height_mm": "人体占用高",
            "transport_width_mm": "行走包络宽",
            "transport_depth_mm": "行走包络深",
            "activity_width_mm": "柜前穿脱衣活动宽",
            "activity_depth_mm": "柜前穿脱衣活动深",
            "activity_height_mm": "活动包络高",
            "turn_width_mm": "连续转身包络宽",
            "turn_depth_mm": "连续转身包络深",
            "operator_standoff_mm": "柜前基础站距",
            "waiting_gap_mm": "等候人员基础间隙",
            "reach_low_mm": "取放操作可达最低高度",
            "reach_high_mm": "取放操作可达最高高度",
            "reach_horizontal_mm": "可达水平距离",
        },
        "现场": {
            "aisle_required_mm": "基础净通道宽",
            "finish_mm": "单侧完成面厚度",
            "installation_gap_mm": "基础柜体安装间隙",
            "unit_gap_mm": "基础柜组间距",
            "construction_tolerance_mm": "不利施工公差预算",
            "room_clear_height_mm": "房间完成面净高",
            "room_door_intrusion_mm": "房门内侵投影",
            "room_door_leaf_width_mm": "房门扇宽",
            "room_door_leaf_height_mm": "房门扇高",
            "room_door_operation_depth_mm": "门前所需操作深度",
        },
        "衣物及分隔": {
            "work_bundle_width_mm": "工作服收纳包络宽",
            "work_bundle_depth_mm": "工作服收纳包络深",
            "work_bundle_height_mm": "工作服收纳包络高",
            "private_bundle_width_mm": "私人衣物收纳包络宽",
            "private_bundle_depth_mm": "私人衣物收纳包络深",
            "private_bundle_height_mm": "私人衣物收纳包络高",
            "partition_mm": "格内分隔板厚度",
            "retrieval_width_mm": "取放所需开口净宽",
            "retrieval_height_mm": "取放所需开口净高",
            "retrieval_depth_mm": "取放所需水平深度",
        },
    }
    zero = {
        "plinth_mm",
        "top_mm",
        "side_panel_mm",
        "back_panel_mm",
        "shelf_mm",
        "fixing_rear_mm",
        "fixing_side_mm",
        "fixing_top_mm",
        "door_frame_mm",
        "hinge_axis_offset_mm",
        "waiting_gap_mm",
        "reach_low_mm",
        "finish_mm",
        "installation_gap_mm",
        "unit_gap_mm",
        "construction_tolerance_mm",
        "room_door_intrusion_mm",
        "partition_mm",
    }
    for group, entries in groups.items():
        fields.update(
            {
                k: PhysicalField(group, label, minimum=0 if k in zero else 1)
                for k, label in entries.items()
            }
        )
    for tier in range(1, 6):
        for suffix, label in (
            ("clear_width_mm", "独立格口净宽"),
            ("clear_depth_mm", "独立格口净深"),
            ("clear_height_mm", "独立格口净高"),
            ("bottom_mm", "格口底标高"),
            ("operation_height_mm", "实际取放操作标高"),
        ):
            fields[f"tier_{tier}_{suffix}"] = PhysicalField(
                "五层格口", f"第{tier}层{label}", minimum=0 if suffix == "bottom_mm" else 1
            )
    text = {
        "manufacturer": ("柜体", "厂家", ()),
        "model": ("柜体", "实际型号", ()),
        "partial_unit_available": ("柜体", "末端非整组实体柜可供性", ("AVAILABLE", "UNAVAILABLE")),
        "door_kind": ("柜门", "开启机制", ("OUTWARD_HINGED_90", "NO_PLAN_INTRUSION", "OTHER")),
        "hinge_side": ("柜门", "铰链侧", ("LEFT", "RIGHT", "OTHER")),
        "door_simultaneity": ("柜门", "同时开柜规则", ("ONE_OPERATOR_PER_COLUMN", "OTHER")),
        "operation_sequence": ("柜门", "操作顺序", (SEQUENCE, "OTHER")),
        "room_door_kind": (
            "现场",
            "房门开向/状态",
            ("OPEN_RECESSED_WITHOUT_SWEEP", "INWARD", "OUTWARD", "OTHER"),
        ),
        "separation_kind": (
            "衣物及分隔",
            "工作服/私人衣物格内分隔",
            ("SIDE_BY_SIDE", "FRONT_BACK", "STACKED", "TWO_COMPARTMENTS", "OTHER"),
        ),
        "clothing_use_method": (
            "衣物及分隔",
            "存取方式",
            ("FOLDED_BUNDLE_THROUGH_CLEAR_OPENING", "OTHER"),
        ),
        "hygiene_procedure": ("现场", "洁污及进出工艺资料", ()),
    }
    fields.update(
        {
            k: PhysicalField(group, label, "enum" if choices else "text", choices=choices)
            for k, (group, label, choices) in text.items()
        }
    )
    for name, label, unit, low in (
        ("columns_per_unit", "每实体柜列数", "count", 1),
        ("actual_tier_count", "实物层数", "count", 1),
        ("door_open_angle_deg", "开门角度", "degree", 0),
        ("front_concurrency", "请求柜前并发", "count", 1),
        ("margin_target_mm", "假设布置余量/填充目标", "mm", 0),
    ):
        fields[name] = PhysicalField("评审条件", label, unit, low)
    return fields


FIELDS = MappingProxyType(field_catalog())


def validate_value(name: str, value: Any) -> None:
    spec = FIELDS[name]
    if value is None:
        return
    if spec.unit in {"mm", "count", "degree"}:
        if type(value) is not int or not spec.minimum <= value <= 60000:
            raise ValueError("INTEGER_PHYSICAL_PARAMETER_REQUIRED:" + name)
    elif type(value) is not str or not value.strip() or len(value) > 256:
        raise ValueError("EXPLICIT_PHYSICAL_TEXT_REQUIRED:" + name)
    elif spec.choices and value not in spec.choices:
        raise ValueError("PHYSICAL_ENUM_NOT_SUPPORTED:" + name)


def input_conflicts(v: dict[str, Any]) -> list[str]:
    errors = []

    def known(*keys: str) -> bool:
        return all(v.get(k) is not None for k in keys)

    if known("actual_tier_count") and v["actual_tier_count"] != 5:
        errors.append("FIVE_TIER_OWNER_REQUIREMENT_CONTRADICTION")
    for tier in range(1, 6):
        prefix = f"tier_{tier}_"
        for axis, outer in (("width", "column_width_mm"), ("depth", "unit_depth_mm")):
            key = prefix + f"clear_{axis}_mm"
            if known(key, outer) and v[key] > v[outer]:
                errors.append(f"TIER_{tier}_CLEAR_{axis.upper()}_EXCEEDS_OUTER")
        depth_key = prefix + "clear_depth_mm"
        if (
            known(depth_key, "unit_depth_mm", "back_panel_mm")
            and v[depth_key] + v["back_panel_mm"] > v["unit_depth_mm"]
        ):
            errors.append(f"TIER_{tier}_NET_DEPTH_PLUS_BACK_PANEL_EXCEEDS_OUTER")
        width_key = prefix + "clear_width_mm"
        if (
            known(width_key, "columns_per_unit", "unit_width_mm", "side_panel_mm")
            and v[width_key] * v["columns_per_unit"] + 2 * v["side_panel_mm"] > v["unit_width_mm"]
        ):
            errors.append(f"TIER_{tier}_NET_COLUMNS_PLUS_OUTER_SIDES_EXCEED_UNIT")
        z, h = prefix + "bottom_mm", prefix + "clear_height_mm"
        if known(z, h, "cabinet_height_mm") and (
            v[z] + v[h] > v["cabinet_height_mm"]
            or v.get("top_mm") is not None
            and v[z] + v[h] + v["top_mm"] > v["cabinet_height_mm"]
        ):
            errors.append(f"TIER_{tier}_EXCEEDS_CABINET_HEIGHT")
        op = prefix + "operation_height_mm"
        if known(z, h, op) and not v[z] <= v[op] <= v[z] + v[h]:
            errors.append(f"TIER_{tier}_OPERATION_HEIGHT_OUTSIDE_CELL")
        if tier < 5:
            nz = f"tier_{tier + 1}_bottom_mm"
            if known(z, h, nz, "shelf_mm") and v[z] + v[h] + v["shelf_mm"] > v[nz]:
                errors.append(f"TIER_{tier}_OVERLAPS_NEXT_TIER")
    if known("tier_1_bottom_mm", "plinth_mm") and v["tier_1_bottom_mm"] < v["plinth_mm"]:
        errors.append("FIRST_TIER_INTRUDES_PLINTH")
    if known("reach_low_mm", "reach_high_mm") and v["reach_low_mm"] >= v["reach_high_mm"]:
        errors.append("INVALID_REACH_INTERVAL")
    return errors


def field_schema() -> dict[str, Any]:
    return {name: asdict(spec) for name, spec in FIELDS.items()}


def storage_checks(values: dict[str, Any]) -> dict[str, Any]:
    """Necessary envelope/clear-opening checks, not a clothing or hygiene approval."""

    def check(keys: list[str], predicate: Any, scope: str) -> dict[str, Any]:
        missing = [k for k in keys if values.get(k) is None]
        return dict(
            status="INPUT_REQUIRED"
            if missing
            else "NECESSARY_CONDITION_SATISFIED"
            if predicate()
            else "CONFIGURATION_NOT_FIT",
            missing=missing,
            scope=scope,
        )

    cells = []
    for tier in range(1, 6):
        prefix = f"tier_{tier}_"
        dims = [prefix + f"clear_{axis}_mm" for axis in ("width", "depth", "height")]
        clothing = [
            f"{kind}_bundle_{axis}_mm"
            for kind in ("work", "private")
            for axis in ("width", "depth", "height")
        ]

        def fit(dims: list[str] = dims, clothing: list[str] = clothing) -> bool:
            if values["separation_kind"] not in {"SIDE_BY_SIDE", "FRONT_BACK", "STACKED"}:
                return False
            split = {"SIDE_BY_SIDE": 0, "FRONT_BACK": 1, "STACKED": 2}[values["separation_kind"]]
            work = [values[k] for k in clothing[:3]]
            private = [values[k] for k in clothing[3:]]
            need = [max(a, b) for a, b in zip(work, private, strict=True)]
            need[split] = work[split] + private[split] + values["partition_mm"]
            return all(values[k] >= n for k, n in zip(dims, need, strict=True))

        cells.append(
            dict(
                tier=tier,
                clear_dimensions_mm=[values.get(k) for k in dims],
                bottom_mm=values.get(prefix + "bottom_mm"),
                storage=check(
                    dims + clothing + ["separation_kind", "partition_mm"],
                    fit,
                    "AXIS_ALIGNED_SEPARATE_BUNDLES_NO_MATERIAL_OR_HYGIENE_APPROVAL",
                ),
                reach=check(
                    [prefix + "operation_height_mm", "reach_low_mm", "reach_high_mm"],
                    lambda p=prefix: (
                        values["reach_low_mm"]
                        <= values[p + "operation_height_mm"]
                        <= values["reach_high_mm"]
                    ),
                    "DECLARED_OPERATION_HEIGHT_ONLY_NOT_ERGONOMIC_CERTIFICATION",
                ),
                retrieval=check(
                    dims
                    + [
                        "retrieval_width_mm",
                        "retrieval_depth_mm",
                        "retrieval_height_mm",
                        "clothing_use_method",
                        "door_opening_clear_width_mm",
                        "door_opening_clear_height_mm",
                    ],
                    lambda dims=dims: (
                        values["clothing_use_method"] == "FOLDED_BUNDLE_THROUGH_CLEAR_OPENING"
                        and all(
                            values[k] >= values[f"retrieval_{axis}_mm"]
                            for k, axis in zip(dims, ("width", "depth", "height"), strict=True)
                        )
                        and values["door_opening_clear_width_mm"] >= values["retrieval_width_mm"]
                        and values["door_opening_clear_height_mm"] >= values["retrieval_height_mm"]
                    ),
                    "DECLARED_CLEAR_OPENING_AND_BUNDLE_ENVELOPE_NOT_IN_USE_CLOTHING_APPROVAL",
                ),
            )
        )
        if values.get("separation_kind") in {"OTHER", "TWO_COMPARTMENTS"}:
            cells[-1]["storage"] = dict(
                status="UNSUPPORTED_PHYSICAL_CONFIGURATION",
                missing=[],
                scope="DIFFERENT_STORAGE_ASSIGNMENT_OR_PARTITION_ADAPTER_REQUIRED",
            )
        if values.get("clothing_use_method") == "OTHER":
            cells[-1]["retrieval"] = dict(
                status="UNSUPPORTED_PHYSICAL_CONFIGURATION",
                missing=[],
                scope="DECLARED_CLOTHING_USE_REQUIRES_FUNCTIONAL_ADAPTER",
            )
    return dict(
        independent_compartment_demand=106,
        columns=22,
        tiers=5,
        arithmetic_capacity=110,
        dedicated_capacity_per_shift=[55, 55],
        demand_per_shift=[53, 53],
        capacity_status="ARITHMETIC_ONLY_NOT_STORAGE_FIT",
        separation_required_compartments=(
            212 if values.get("separation_kind") == "TWO_COMPARTMENTS" else 106
        ),
        separation_capacity_status=(
            "CONFIGURATION_NOT_FIT_110_LESS_THAN_212"
            if values.get("separation_kind") == "TWO_COMPARTMENTS"
            else "INPUT_REQUIRED"
        ),
        cells=cells,
        actual_storage_function="INPUT_REQUIRED",
        separation_approval="INPUT_REQUIRED",
        warnings=[
            "A count of 110 does not prove usable storage for 106 people",
            "Missing clothing, opening and reach data are never inferred from room area",
        ],
    )


def case_physical_checks(case: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    g = case["geometry"]
    collisions = []
    checks = 0
    for snapshot in g["snapshots"]:
        for door in snapshot["doors"]:
            for person in snapshot["people"]:
                checks += 1
                if any(door_hits_box(door, box) for box in person["volumes_mm"]):
                    collisions.append(
                        dict(
                            snapshot=snapshot["id"],
                            door=door["id"],
                            person=person["id"],
                            door_z_mm=door["z_interval_mm"],
                            person_bounds_mm=person["bounds_mm"],
                        )
                    )
    storage = storage_checks(values)
    fixing = []
    p = g["parameters"]
    for field, available, location in (
        ("fixing_rear_mm", p["installation_gap_mm"], "SOUTH_CABINET_BACK"),
        ("fixing_side_mm", p["unit_gap_mm"], "CABINET_GROUP_GAPS"),
        ("fixing_top_mm", values["room_clear_height_mm"] - p["cabinet_height_mm"], "CABINET_TOP"),
        ("room_door_operation_depth_mm", p["entrance_landing_mm"], "EAST_PORTAL_LANDING"),
    ):
        required = values.get(field)
        fixing.append(
            dict(
                field=field,
                available_mm=available,
                required_mm=required,
                location=location,
                status="INPUT_REQUIRED"
                if required is None
                else "NECESSARY_CONDITION_SATISFIED"
                if available >= required
                else "CONFIGURATION_NOT_FIT",
            )
        )
    return dict(
        storage=storage,
        fixing_and_landing=fixing,
        door_person_checks=checks,
        door_person_conflicts=collisions,
        door_status="CONFIGURATION_NOT_FIT"
        if collisions
        else "CONDITIONAL_SWEEP_CHECKS_SATISFIED"
        if checks
        else "NOT_EVALUATED_NO_VALID_SCHEDULE",
        people_per_shift=53,
        initial_simultaneous_users=53,
        completed_users=case["summary"]["completed_users"],
        complete_two_shift_flow=case["summary"]["full_flow_status"],
        body_and_aisle_conflicts=case["summary"]["static_conflicts"]
        + case["summary"]["conditional_flow_conflicts"],
        actual_functional_status="INPUT_REQUIRED",
        missing_home_positions=max(0, 53 - g["metrics"]["home_count"]),
        scope="THIS_EXISTING_MIXED_SPATIAL_TEMPLATE_NOT_GLOBAL_INFEASIBILITY",
    )
