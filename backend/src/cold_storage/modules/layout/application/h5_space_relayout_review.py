"""R9 spatial alternatives on frozen H5, with the original reviewed project basis."""

import copy
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.application.cabinet_front_review import bind_front_project
from cold_storage.modules.layout.domain.cabinet_front_operation import (
    FrontTiming,
    simulate_front_shift,
)
from cold_storage.modules.layout.domain.cabinet_front_schedule import front_geometry
from cold_storage.modules.layout.domain.h5_relayout_operation import (
    RelayoutTiming,
    simulate_relayout_shift,
)
from cold_storage.modules.layout.domain.h5_space_relayout import (
    TEMPLATES,
    relayout_geometry,
    sensitivity_parameters,
)

TASK = "V2_2_2_R11_R9_H5_FUNCTIONAL_SPACE_RELAYOUT_R1"
LABELS = (
    "A 混合本位 / 西北补位",
    "B 北墙等候 / 南侧分区",
    "C 分段柜组 / 北墙等候",
)


def review_relayouts(catalog: dict[str, Any], r7_source: bytes, r8_source: bytes) -> dict[str, Any]:
    binding = bind_front_project(catalog, r7_source, r8_source)
    row = next(r for r in catalog["groups"] if r["group"] == "G01")
    cases: dict[str, Any] = {}
    for template, label in zip(TEMPLATES, LABELS, strict=True):
        g = relayout_geometry(row["room"], catalog["demands"]["INTERNAL_PARTITION"], template)
        cases[label] = dict(
            geometry=g,
            shifts=[simulate_relayout_shift(g, s, RelayoutTiming()) for s in (1, 2)],
            timing=asdict(RelayoutTiming()),
        )
    g = front_geometry(
        row["room"], catalog["demands"]["INTERNAL_PARTITION"], sensitivity_parameters()
    )
    cases["原R8双排模板 / 47本位"] = dict(
        geometry=g,
        shifts=[
            simulate_front_shift(g, s, sensitivity_parameters(), FrontTiming()) for s in (1, 2)
        ],
        timing=asdict(FrontTiming()),
    )
    g = relayout_geometry(
        row["room"], catalog["demands"]["INTERNAL_PARTITION"], TEMPLATES[0], finish_mm=30
    )
    cases["A完成面30mm / 保留失败"] = dict(
        geometry=g,
        shifts=[simulate_relayout_shift(g, s, RelayoutTiming()) for s in (1, 2)],
        timing=asdict(RelayoutTiming()),
    )
    for case in cases.values():
        case.update(
            task=TASK,
            binding=copy.deepcopy(binding),
            original_access_readbacks=copy.deepcopy(row["record_access_readbacks"]),
            original_external_routes=copy.deepcopy(row["external_routes"]),
            project_functional_status="INPUT_REQUIRED",
            source_type="demo",
            validity_status="unverified",
            requires_review=True,
            native_solves=0,
            native_counter_scope="THIS_DETERMINISTIC_FUNCTIONAL_EVALUATION_ONLY",
            historical_records_changed=False,
        )
    return cases
