"""Read sealed experiments into independent R11 room-use diagnostics; no execution ports."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.application.access_routing import _rectangle_from_row
from cold_storage.modules.layout.application.global_composition_pool import _eligible
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.functional_room_fit import (
    REQUIRED,
    VERSION,
    evaluate_functional_room,
)

R10_HEAD = "288a56b768baa859cbcfb41908fbbd5d6155094d"


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sealed_file(root: Path, relative: str, manifest: dict[str, str]) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("ARCHIVE_PATH_INVALID")
    if relative not in manifest or sha(path) != manifest[relative]:
        raise ValueError("HISTORICAL_FILE_HASH_MISMATCH:" + relative)
    return path


def _mm(value: Any) -> int:
    from decimal import Decimal

    mm = Decimal(str(value)) * 1000
    if not mm.is_finite() or mm != mm.to_integral_value():
        raise ValueError("SOURCE_NOT_ON_INTEGER_MM_GRID")
    return int(mm)


def _room(
    candidate: dict[str, Any], code: str, authority: dict[str, Any], label: str, source: str
) -> dict[str, Any]:
    zone_index, zone = next(
        (i, z)
        for i, z in enumerate(candidate["engineering_validation"]["zones"])
        if z["zone_code"] == code
    )
    rect = _rectangle_from_row(zone)
    x0, y0, x1, y1 = (int(v) for v in rect.bounds_mm)
    portals = []
    for p in candidate["engineering_validation"]["portals"]:
        if p["access_ref"] != code:
            continue
        points = [
            [_mm(p["segment"][key]["x"]) - x0, _mm(p["segment"][key]["y"]) - y0]
            for key in ("start", "end")
        ]
        portals.append(
            dict(
                id=p["identity"],
                segment_mm=points,
                clear_width_mm=_mm(p["clear_width_m"]),
                source_label="ENGINEERING_DERIVED",
                reference=source + "#/engineering_validation/portals",
            )
        )
    from decimal import Decimal

    area = Decimal(str(authority["required_area_m2"])) * 1_000_000
    if area != area.to_integral_value():
        raise ValueError("P1_AREA_NOT_EXACT_MM2")
    return dict(
        scope_id=(
            candidate["source_zone_plan_hash"]
            + ":"
            + candidate["source_p1_handoff_hash"]
            + ":"
            + candidate["canonical_result_hash"]
            + ":"
            + code
        ),
        record=label,
        room_code=code,
        local_bounds_mm=[0, 0, x1 - x0, y1 - y0],
        world_bounds_mm=[x0, y0, x1, y1],
        p1_required_area_mm2=int(area),
        p1_area_source=dict(
            reference=source.split(":", 1)[0]
            + ":server-authorities.json#/p1/p1e_historical_handoff/dimension_handoff/authorities",
            authority=authority["authority"],
            identity=authority["dimension_authority_identity"],
        ),
        portals=portals,
        source_label="ENGINEERING_DERIVED",
        geometry_reference=source + "#/engineering_validation/zones/" + str(zone_index),
        candidate_hash=candidate["canonical_result_hash"],
        source_composition_hash=candidate["source_composition_hash"],
        original_engineering_status="EXISTING_STAGE_B_ELIGIBLE",
        finished_clear_dimensions_status="INPUT_REQUIRED_NOT_INFERRED_FROM_P2_BOUNDARY",
    )


def build_historical_review(
    archive: Path,
    manifest_path: Path,
    owner_rules: Path,
    *,
    r9_archive: Path | None = None,
    r9_preservation: Path | None = None,
) -> dict[str, Any]:
    """Preserve original accepted/Pareto states; report missing functional basis.

    Existing Owner business policies are conditional; neither daily inbound
    throughput nor a filename establishes actual packaged-product staffing.
    """
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in manifest.items()
    ):
        raise ValueError("SEALED_MANIFEST_REQUIRED")
    for relative in manifest:
        sealed_file(archive, relative, manifest)

    def load(name: str) -> Any:
        return read_json(sealed_file(archive, name, manifest))

    binding = load("source-binding.json")
    if (
        binding["head"] != R10_HEAD
        or binding["balanced_quality_task"] != "V2_2_2_STAGE_B_R10_R2_REAL_MAIN_R1"
    ):
        raise ValueError("WRONG_HISTORICAL_EXECUTION")
    authorities = load("server-authorities.json")
    p1 = authorities["p1"]
    if canonical_hash(p1) != binding["p1_hash"]:
        raise ValueError("P1_SOURCE_MISMATCH")
    if (
        canonical_hash(authorities["plan"]) != binding["zone_plan_hash"]
        or canonical_hash(authorities["site"]) != binding["site_hash"]
    ):
        raise ValueError("PLAN_OR_SITE_SOURCE_MISMATCH")
    dimensions = p1["p1e_historical_handoff"]["dimension_handoff"]
    areas = {a["zone_code"]: a for a in dimensions["authorities"] if a["zone_code"] in REQUIRED}
    if set(areas) != set(REQUIRED):
        raise ValueError("FUNCTIONAL_P1_AREA_AUTHORITIES_REQUIRED")
    index = load("candidate-index.json")
    if len(index) != 9:
        raise ValueError("EXPECTED_NINE_ORIGINAL_RECORDS")
    rows = []
    group_keys: dict[str, str] = {}
    aliases: dict[str, list[str]] = defaultdict(list)
    source_rows = []
    for ordinal, row in enumerate(index, 1):
        label = f"P{ordinal:02d}"
        rel = str(Path(row["svg"]).parent / "candidate.json")
        c = load(rel)
        validation = c["engineering_validation"]
        ids = {
            r["identity"] for r in validation["access_requirements"] if r["flow_kind"] != "TRUCK"
        }
        if (
            len(ids) != 11
            or not _eligible(c, ids)
            or c["source_p1_handoff_hash"] != binding["p1_hash"]
            or c["source_zone_plan_hash"] != binding["zone_plan_hash"]
            or c["source_site_geometry_hash"] != binding["site_hash"]
            or c["canonical_result_hash"] != row["candidate_hash"]
        ):
            raise ValueError("ORIGINAL_ENGINEERING_IDENTITY_INVALID")
        if sha(sealed_file(archive, row["svg"], manifest)) != row["svg_sha256"]:
            raise ValueError("ORIGINAL_SVG_MISMATCH")
        physical = sorted(
            (z["zone_code"], tuple(int(v) for v in _rectangle_from_row(z).bounds_mm))
            for z in validation["zones"]
        )
        key = canonical_hash(physical)
        group = group_keys.setdefault(key, f"G{len(group_keys) + 1:02d}")
        aliases[group].append(label)
        handoff = next(
            i + 1
            for i, h in enumerate(binding["compositions"])
            if h["composition_hash"] == c["source_composition_hash"]
        )
        for code in REQUIRED:
            room = _room(c, code, areas[code], label, "sealed-r10:" + rel)
            evaluation = evaluate_functional_room(room)
            rows.append(
                dict(
                    record=label,
                    handoff=handoff,
                    physical_group=group,
                    room=room,
                    evaluation=evaluation,
                    source_candidate_sha256=manifest[rel],
                )
            )
        source_rows.append(
            dict(
                record=label,
                handoff=handoff,
                physical_group=group,
                candidate_hash=row["candidate_hash"],
                geometry_hash=row["geometry_hash"],
                stage=row["search_stage"],
                svg_reference="sealed-r10:" + row["svg"],
            )
        )
    if len(group_keys) != 8:
        raise ValueError("EXPECTED_EIGHT_PHYSICAL_RECTANGLE_GROUPS")
    owner = read_json(owner_rules)
    owner_facts = [
        r
        for r in owner["rules"]
        if r["FIELD_NAME"]
        in {
            "SHIFTS_PER_DAY",
            "LOCKER_SHARED_BETWEEN_SHIFTS",
            "LOCKER_INTERNAL_SEPARATION",
            "LOCKER_COUNT_FORMULA",
            "SIMULTANEOUS_CHANGING_USERS_FORMULA",
            "OFFICE_DESIGN_STAFF.SMALL",
            "OFFICE_DESIGN_STAFF.MEDIUM",
            "OFFICE_DESIGN_STAFF.LARGE",
        }
    ]
    historical_reference = []
    if r9_archive is not None and r9_preservation is not None:
        before = read_json(r9_preservation)

        def r9load(name: str) -> Any:
            path = r9_archive / name
            if str(path) not in before or sha(path) != before[str(path)]:
                raise ValueError("R9_REFERENCE_HASH_MISMATCH")
            return read_json(path)

        oldidx = r9load("candidate-index.json")
        oldrow = oldidx[3]
        oldc = r9load(str(Path(oldrow["svg"]).parent / "candidate.json"))
        oldids = {
            r["identity"]
            for r in oldc["engineering_validation"]["access_requirements"]
            if r["flow_kind"] != "TRUCK"
        }
        if not _eligible(oldc, oldids):
            raise ValueError("R9_REFERENCE_NOT_ORIGINALLY_ELIGIBLE")
        for code in REQUIRED:
            room = _room(
                oldc,
                code,
                areas[code],
                "R9 P04",
                "sealed-r9:" + str(Path(oldrow["svg"]).parent / "candidate.json"),
            )
            historical_reference.append(
                dict(
                    room=room,
                    evaluation=evaluate_functional_room(room),
                    formal_pareto_comparison=False,
                )
            )
    return dict(
        version=VERSION,
        task="V2_2_2_R11_FUNCTIONAL_ROOM_FIT_R1",
        source_head=R10_HEAD,
        source_manifest_sha256=sha(manifest_path),
        original_record_count=9,
        physical_group_count=8,
        physical_groups=dict(aliases),
        room_evaluations=rows,
        original_records=source_rows,
        historical_r9_reference=historical_reference,
        owner_business_rules=dict(
            reference=str(owner_rules),
            sha256=sha(owner_rules),
            source_label="OWNER_CONFIRMED",
            facts=owner_facts,
            applicability="CONDITIONAL_POLICY_NOT_PROJECT_STAFFING",
            historical_staffing_bound=False,
        ),
        inputs_not_project_authority=[
            "53 simultaneous users / 106 lockers: conditional packaged-product example only",
            "12/20/30 office staff require an explicit factory-size selection",
        ],
        history_unchanged=True,
        original_comparisons=load("area-quality-comparison.json")["comparisons"],
        native_solves=0,
        new_grant=False,
        new_claim=False,
        changes_p1=False,
        changes_engineering_acceptance=False,
        functional_approval=False,
    )
