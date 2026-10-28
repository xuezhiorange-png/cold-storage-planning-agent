"""R6 binds only the frozen reviewed H5 project; all simulations stay hypothetical."""

from dataclasses import replace
from typing import Any

from cold_storage.modules.layout.application.practical_changing_review import review_h5
from cold_storage.modules.layout.domain.full_changing_operation import (
    OperationHypothesis,
    TimingHypothesis,
    evaluate_operation,
)
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis

TASK = "V2_2_2_R11_R6_H5_FULL_CHANGING_OPERATION_R1"


def review_operation(
    catalog: dict[str, Any],
    p: H5Hypothesis,
    options: OperationHypothesis,
    timing: TimingHypothesis | None,
) -> dict[str, Any]:
    base = review_h5(catalog, "INTERNAL_PARTITION", p)
    result = evaluate_operation(base, options, timing)
    return dict(
        task=TASK,
        geometry=base,
        operation=result,
        project_functional_status="INPUT_REQUIRED",
        engineering_approval=False,
        source_labels=dict(
            project="CONFIRMED_PROJECT_BASIS",
            geometry="ARCHIVED_ENGINEERING_GEOMETRY",
            human_and_time="HYPOTHETICAL_NOT_APPROVED",
            hygiene="INPUT_REQUIRED",
        ),
    )


def comparison_cases(catalog: dict[str, Any]) -> dict[str, Any]:
    p = H5Hypothesis()
    cases = {
        "A 原400×600 / 20间隙 / 4柜前 / 6座 / 800×900操作区": p,
        "B 柜前并发2人": replace(p, front_concurrency=2),
        "C 柜前并发6人": replace(p, front_concurrency=6),
        "D 1张凳3座": replace(p, bench_count=1),
        "E 3张凳9座": replace(p, bench_count=3),
        "F 操作区1000×1000": replace(
            p, changing_operation_width_mm=1000, changing_operation_depth_mm=1000
        ),
        "G 人员450×650 / 间隙100": replace(
            p, person_width_mm=450, person_depth_mm=650, person_gap_mm=100
        ),
        "H 人员500×700 / 间隙100": replace(
            p, person_width_mm=500, person_depth_mm=700, person_gap_mm=100
        ),
        "I 原400×600 / 间隙100": replace(p, person_gap_mm=100),
    }
    return {
        label: review_operation(catalog, parameters, OperationHypothesis(), TimingHypothesis())
        for label, parameters in cases.items()
    }
