"""R5 H5 review of hypotheses against frozen R4 project and room identities."""

import copy
import hashlib
import json
from dataclasses import fields
from typing import Any

from cold_storage.modules.layout.application.changing_locker_review import PROJECT_SCOPE
from cold_storage.modules.layout.domain.practical_changing_layout import H5Hypothesis, evaluate_h5

# Content identity of the existing R4 frozen review catalogue, not an approval token.
FROZEN_CATALOG_SHA256 = "02429a202fae30c861fadec5aeaf4d7eb702ed5ec5ab742a84d4de87619ddecb"


def verify_catalog(catalog: dict[str, Any]) -> None:
    raw = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(raw).hexdigest() != FROZEN_CATALOG_SHA256:
        raise ValueError("ORIGINAL_R4_REVIEW_CATALOG_SOURCE_MISMATCH")


TASK = "V2_2_2_R11_R5_H5_PRACTICAL_CHANGING_LAYOUT_R1"


def review_h5(catalog: dict[str, Any], scenario: str, p: H5Hypothesis) -> dict[str, Any]:
    verify_catalog(catalog)
    if catalog["project_scope_id"] != PROJECT_SCOPE or catalog["design_basis"][
        "shift_design_users"
    ] != [53, 53]:
        raise ValueError("ORIGINAL_REVIEWED_PROJECT_BINDING_REQUIRED")
    row = next(r for r in catalog["groups"] if r["group"] == "G01")
    if row["records"] != ["P01", "P02"] or row["handoff"] != 5:
        raise ValueError("ORIGINAL_H5_RECORDS_REQUIRED")
    room = row["room"]
    segments = {tuple(tuple(p) for p in q["segment_mm"]) for q in room["portals"]}
    if segments != {((26331, 875), (26331, 2375)), ((12415, 0), (13915, 0))} or any(
        q["clear_width_mm"] != 1500 for q in room["portals"]
    ):
        raise ValueError("ORIGINAL_H5_PORTALS_REQUIRED")
    if scenario not in catalog["demands"]:
        raise ValueError("EXPLICIT_SEPARATION_SCENARIO_REQUIRED")
    result = evaluate_h5(room, catalog["demands"][scenario], p)
    result.update(
        task=TASK,
        group="G01",
        records=row["records"],
        handoff=5,
        record_access_readbacks=copy.deepcopy(row["record_access_readbacks"]),
        external_routes=copy.deepcopy(row["external_routes"]),
        project_facts=copy.deepcopy(catalog["project_facts"]),
        design_basis=copy.deepcopy(catalog["design_basis"]),
        missing_inputs=copy.deepcopy(catalog["missing_inputs"]),
        historical_status_changed=False,
        engineering_approval=False,
    )
    return result


def preview_request(catalog: dict[str, Any], body: Any) -> dict[str, Any]:
    if (
        not isinstance(body, dict)
        or set(body) != {"scenario", "parameters"}
        or not isinstance(body["parameters"], dict)
    ):
        raise ValueError("HYPOTHESES_ONLY_NO_PROJECT_APPROVAL_IMPORT")
    if not set(body["parameters"]) <= {f.name for f in fields(H5Hypothesis)}:
        raise ValueError("HYPOTHESES_ONLY_NO_PROJECT_APPROVAL_IMPORT")
    return review_h5(catalog, body["scenario"], H5Hypothesis(**body["parameters"]))
