"""Owner-reviewed project facts, separate from hypothetical standing operation."""

import copy
import hashlib
from dataclasses import asdict, replace
from typing import Any

from cold_storage.modules.layout.application.changing_locker_review import PROJECT_SCOPE
from cold_storage.modules.layout.application.functional_project_input_binding import (
    ReviewedProjectDatum,
)
from cold_storage.modules.layout.application.practical_changing_review import verify_catalog
from cold_storage.modules.layout.domain.standing_changing_layout import (
    StandingParameters,
    standing_geometry,
)
from cold_storage.modules.layout.domain.standing_changing_operation import (
    StandingTiming,
    simulate_shift,
)

TASK = "V2_2_2_R11_R7_H5_NO_BENCH_STANDING_CHANGING_R1"
SOURCE_SHA256 = "9dcf5d3b8a4a397af2179bdf4e86bc5dfa1a12d5325ed332796d48602fcf1e3e"
SOURCE_PATH = "docs/tasks/V2_2_2-r11-r7-reviewed-standing-project-facts.txt"


def bind_standing_project(catalog: dict[str, Any], owner_source: bytes) -> dict[str, Any]:
    """Bind this task's already-reviewed fact using the existing typed datum pattern.

    The digest identifies the source reviewed by Owner in this task, not a generic
    approval token. No JSON label import or approval/status override is accepted.
    """
    verify_catalog(catalog)
    if (
        not isinstance(owner_source, bytes)
        or hashlib.sha256(owner_source).hexdigest() != SOURCE_SHA256
    ):
        raise ValueError("REVIEWED_STANDING_OWNER_SOURCE_MISMATCH")
    if catalog["project_scope_id"] != PROJECT_SCOPE:
        raise ValueError("REVIEWED_STANDING_PROJECT_SCOPE_MISMATCH")
    row = next(r for r in catalog["groups"] if r["group"] == "G01")
    if row["records"] != ["P01", "P02"] or row["handoff"] != 5:
        raise ValueError("ORIGINAL_H5_RECORDS_REQUIRED")
    facts = {}
    reviewed_values: list[tuple[str, str | int, str]] = [
        ("BENCH_COUNT", 0, "count"),
        ("CHANGING_POSTURE", "STANDING", "posture"),
    ]
    for field, value, unit in reviewed_values:
        datum = ReviewedProjectDatum(
            field,
            value,
            unit,
            PROJECT_SCOPE,
            "OWNER_CONFIRMED",
            f"{TASK}; {SOURCE_PATH}; sha256:{SOURCE_SHA256}",
        )
        facts[field] = asdict(datum)
    return dict(
        project_scope_id=PROJECT_SCOPE,
        status="CONFIRMED_PROJECT_BASIS",
        reviewed_project_facts=facts,
        historical_project_facts=catalog["project_facts"],
        design_basis=catalog["design_basis"],
        source_sha256=SOURCE_SHA256,
        missing_inputs=[m for m in catalog["missing_inputs"] if not m.startswith("benches_")]
        + [
            "standing_mode_and_parallel_protocol",
            "human_transport_and_dressing_activity_envelopes",
            "reviewed_action_times_and_allowed_shift_window",
        ],
        project_functional_status="INPUT_REQUIRED",
        engineering_approval=False,
    )


def review_standing(
    catalog: dict[str, Any],
    source: bytes,
    params: StandingParameters,
    timing: StandingTiming | None = None,
) -> dict[str, Any]:
    binding = bind_standing_project(catalog, source)
    row = next(r for r in catalog["groups"] if r["group"] == "G01")
    geometry = standing_geometry(row["room"], catalog["demands"]["INTERNAL_PARTITION"], params)
    return dict(
        task=TASK,
        binding=binding,
        geometry=geometry,
        original_access_readbacks=copy.deepcopy(row["record_access_readbacks"]),
        original_external_routes=copy.deepcopy(row["external_routes"]),
        shifts=[simulate_shift(geometry, s, params, timing) for s in (1, 2)],
        mode_approval="INPUT_REQUIRED",
        project_functional_status="INPUT_REQUIRED",
        timing=None if timing is None else asdict(timing),
        source_type="demo",
        validity_status="unverified",
        requires_review=True,
        native_solves=0,
        historical_records_changed=False,
    )


def comparison_cases(catalog: dict[str, Any], source: bytes) -> dict[str, Any]:
    p = StandingParameters()
    cases = {
        "A 分散站立 · 4人 · 420×700活动包络": p,
        "B 柜前站立 · 4人 · 420×700活动包络": replace(p, mode="CABINET_FRONT"),
        "C 柜前站立 · 1人 · 420×700活动包络": replace(p, mode="CABINET_FRONT", front_concurrency=1),
        "D 分散站立 · 2人 · 420×700活动包络": replace(p, front_concurrency=2),
        "E 分散站立 · 6人 · 420×700活动包络": replace(p, front_concurrency=6),
        "F 分散站立 · 4人 · 600×900活动包络": replace(
            p, activity_width_mm=600, activity_depth_mm=900
        ),
        "G 450×650人体 · 100间隙": replace(
            p,
            person_width_mm=450,
            person_depth_mm=650,
            person_gap_mm=100,
            activity_width_mm=600,
            activity_depth_mm=900,
        ),
        "H 柜前静态身体边界 · 非更衣可用性证明": replace(
            p, mode="CABINET_FRONT", activity_width_mm=400, activity_depth_mm=600
        ),
    }
    return {
        name: review_standing(catalog, source, q, StandingTiming()) for name, q in cases.items()
    }
