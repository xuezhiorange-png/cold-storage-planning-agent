"""Current reviewed cabinet-front process, separate from all geometric hypotheses."""

import copy
import hashlib
from dataclasses import asdict, replace
from typing import Any

from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
)
from cold_storage.modules.layout.application.standing_changing_review import bind_standing_project
from cold_storage.modules.layout.domain.cabinet_front_operation import (
    FrontTiming,
    open_door_activity_proof,
    simulate_front_shift,
)
from cold_storage.modules.layout.domain.cabinet_front_schedule import (
    FrontParameters,
    front_geometry,
)

TASK = "V2_2_2_R11_R8_CABINET_FRONT_CHANGING_R1"
SOURCE_PATH = "docs/tasks/V2_2_2-r11-r8-reviewed-cabinet-front-facts.txt"
SOURCE_SHA256 = "ba190fe5724b7b702a8361ccf481594b74d24cc31e9f4e23ce807cd754867247"


def bind_front_project(catalog: dict[str, Any], r7_source: bytes, source: bytes) -> dict[str, Any]:
    binding = copy.deepcopy(bind_standing_project(catalog, r7_source))
    if not isinstance(source, bytes) or hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("REVIEWED_R8_CABINET_FRONT_SOURCE_MISMATCH")
    values: list[tuple[str, str | int, str]] = [
        ("CHANGING_LOCATION", "PERSONAL_CABINET_FRONT", "location"),
        ("SEPARATE_CHANGING_AREA_COUNT", 0, "count"),
    ]
    for field, value, unit in values:
        datum = ReviewedProjectDatum(
            field,
            value,
            unit,
            binding["project_scope_id"],
            "OWNER_CONFIRMED",
            f"{TASK}; {SOURCE_PATH}; sha256:{SOURCE_SHA256}",
        )
        binding["reviewed_project_facts"][field] = asdict(datum)
    binding.update(
        current_process="PERSONAL_CABINET_FRONT_STANDING",
        r8_source_sha256=SOURCE_SHA256,
        r7_distributed_process="HISTORICAL_COMPARISON_ONLY",
        engineering_approval=False,
    )
    binding["missing_inputs"] = [
        m for m in binding["missing_inputs"] if m != "standing_mode_and_parallel_protocol"
    ] + [
        "approved_cabinet_front_concurrency_and_waiting_protocol",
        "approved_two_opening_handling_and_closed_door_changing_sequence",
    ]
    return binding


def review_front(
    catalog: dict[str, Any],
    r7_source: bytes,
    source: bytes,
    cfg: FrontParameters,
    timing: FrontTiming | None = None,
) -> dict[str, Any]:
    binding = bind_front_project(catalog, r7_source, source)
    row = next(r for r in catalog["groups"] if r["group"] == "G01")
    g = front_geometry(row["room"], catalog["demands"]["INTERNAL_PARTITION"], cfg)
    return dict(
        task=TASK,
        binding=binding,
        geometry=g,
        original_access_readbacks=copy.deepcopy(row["record_access_readbacks"]),
        original_external_routes=copy.deepcopy(row["external_routes"]),
        shifts=[simulate_front_shift(g, s, cfg, timing) for s in (1, 2)],
        open_door_changing_sensitivity=[
            dict(shift=s["shift"], batch=s["id"], proof=open_door_activity_proof(g, s))
            for s in g["snapshots"]
            if s["id"] == next(q["id"] for q in g["snapshots"] if q["shift"] == s["shift"])
        ],
        timing=asdict(timing) if timing else None,
        project_functional_status="INPUT_REQUIRED",
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        native_solves=0,
        historical_records_changed=False,
    )


def comparison_cases(catalog: dict[str, Any], r7_source: bytes, source: bytes) -> dict[str, Any]:
    base = FrontParameters()
    configs = {
        f"{w}×{d}活动 · 间隔柜列 · 请求{n}人": replace(
            base, activity_width_mm=w, activity_depth_mm=d, requested_concurrency=n
        )
        for w, d in ((420, 700), (600, 900))
        for n in (2, 3, 4, 5)
    }
    configs.update(
        {
            "连续柜列负面对照 · 600×900 · 4人": replace(base, grouping="CONTIGUOUS_REFERENCE"),
            "活动深度1100mm · 柜前深度不足": replace(base, activity_depth_mm=1100),
            "身体450×650 / 等候间隔100mm": replace(
                base, person_width_mm=450, person_depth_mm=650, person_gap_mm=100
            ),
            "单列实体分组 / 柜间距200mm": replace(base, columns_per_unit=1, unit_gap_mm=200),
        }
    )
    return {
        name: review_front(catalog, r7_source, source, cfg, FrontTiming())
        for name, cfg in configs.items()
    }
