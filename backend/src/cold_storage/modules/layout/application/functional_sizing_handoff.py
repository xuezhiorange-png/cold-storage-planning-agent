"""Evidence-bound H5 advice preview, isolated from production planning ports."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from cold_storage.modules.layout.application.functional_project_input_binding import (
    PROJECT_INPUT_ID,
    ReviewedProjectDatum,
)
from cold_storage.modules.layout.application.functional_room_review import R10_HEAD, _room
from cold_storage.modules.layout.application.functional_sizing_sources import (
    BASE_HEAD,
    HISTORICAL,
    OWNER_FILES,
    OWNER_HASHES,
    R10,
    verify_sizing_evidence,
)
from cold_storage.modules.layout.application.global_composition_pool import _eligible
from cold_storage.modules.layout.domain.composition_handoff import DimensionAuthorityReferenceV1
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from cold_storage.modules.layout.domain.functional_sizing_advisory import (
    APPROVAL_BOUNDARY,
    IDENTITY,
    SCHEMA_VERSION,
    FunctionalRoomSizingAdvisoryV1,
    area_text,
    room_dimensions,
)

TASK = "V2_2_2_R11_R11_FUNCTIONAL_SIZING_ADVISORY_HANDOFF_R1"
CASE_KEYS = (
    "R10-L26331-W3550-M50-MIXED",
    "R10-L26331-W3850-M100-MIXED-SENSITIVITY",
    "R10-L28000-W4350-M150-NORTH_NORMAL_SOUTH_ROTATED",
)
CASE_LABELS = ("C 较少边界调整", "3850mm组合敏感性", "B 更大局部余量")
CONFIRMATIONS = (
    ("CABINET_MODEL", "实际五层柜型号、实体柜分组、外形及格口净尺寸"),
    ("CLOTHING_SEPARATION", "工作服与私人衣物采用何种实际分隔，卫生工艺是否认可"),
    ("CABINET_DOORS", "柜门铰链、开启角度、分层扫掠及取放操作方式"),
    ("FINISHED_DIMENSIONS", "实际完成面尺寸、安装间隙、公差和柜体固定要求"),
    ("HUMAN_ENVELOPES", "站立更衣、运输和转身的人体活动包络及五层可达性"),
    ("OPERATING_PROTOCOL", "已知53人同时在室条件下的柜前并发、等候本位和换位组织"),
    ("HYGIENE_AND_ROOM_DOORS", "洁污工艺、房门开向、门前停留与连续人员通行条件"),
    ("OPERATION_TIMES", "真实取放、更衣和步行时间及允许的换班时间窗口"),
    ("EXTERNAL_EXPANSION", "扩建后的Site、Footprint、外部Access、相邻房间及工艺关系"),
)


def _reference(path: str, fragment: str = "") -> str:
    return f"git:{BASE_HEAD}:{path}" + ("#" + fragment if fragment else "")


def _context(files: Mapping[str, bytes]) -> dict[str, Any]:
    ctx = verify_sizing_evidence(files)
    authority, binding, catalog = ctx["authority"], ctx["binding"], ctx["catalog"]
    if binding["head"] != R10_HEAD:
        raise ValueError("FUNCTIONAL_SIZING_HISTORICAL_HEAD_MISMATCH")
    for name, key in (("plan", "zone_plan_hash"), ("p1", "p1_hash"), ("site", "site_hash")):
        if canonical_hash(authority[name]) != binding[key]:
            raise ValueError("FUNCTIONAL_SIZING_P1_PLAN_SITE_MISMATCH")
    scope = binding["zone_plan_hash"] + ":" + binding["p1_hash"]
    if catalog["project_scope_id"] != scope or ctx["r10"]["binding"]["project_scope_id"] != scope:
        raise ValueError("FUNCTIONAL_SIZING_PROJECT_SCOPE_MISMATCH")
    group = next(g for g in catalog["groups"] if g["group"] == "G01")
    if group["records"] != ["P01", "P02"] or group["handoff"] != 5:
        raise ValueError("FUNCTIONAL_SIZING_H5_GROUP_MISMATCH")
    dimensions = authority["p1"]["p1e_historical_handoff"]["dimension_handoff"]
    rows = [r for r in dimensions["authorities"] if r["zone_code"] == "changing_room"]
    if len(rows) != 1 or rows[0]["p2_may_change_required_area"] is not False:
        raise ValueError("FUNCTIONAL_SIZING_ORIGINAL_P1_REFERENCE_REQUIRED")
    room = group["room"]
    ctx.update(scope=scope, group=group, p1_row=rows[0], dimensions=dimensions, room=room)
    for record, c in zip(group["records"], ctx["candidates"], strict=True):
        identities = {
            r["identity"]
            for r in c["engineering_validation"]["access_requirements"]
            if r["flow_kind"] != "TRUCK"
        }
        if (
            not _eligible(c, identities)
            or any(
                c[k] != binding[v]
                for k, v in (
                    ("source_zone_plan_hash", "zone_plan_hash"),
                    ("source_p1_handoff_hash", "p1_hash"),
                    ("source_site_geometry_hash", "site_hash"),
                )
            )
            or c["source_composition_hash"] != binding["compositions"][4]["composition_hash"]
        ):
            raise ValueError("FUNCTIONAL_SIZING_ARCHIVED_CANDIDATE_MISMATCH")
        alias = next(a for a in group["aliases"] if a["record"] == record)
        if c["canonical_result_hash"] != alias["candidate_hash"]:
            raise ValueError("FUNCTIONAL_SIZING_CANDIDATE_ALIAS_MISMATCH")
        relative = alias["geometry_reference"].removeprefix("sealed-r10:").split("#")[0]
        actual = _room(c, "changing_room", rows[0], record, "sealed-r10:" + relative)
        if _physical_key(actual, scope) != _physical_key(room, scope):
            raise ValueError("FUNCTIONAL_SIZING_PHYSICAL_ROOM_MISMATCH")
        if actual["p1_required_area_mm2"] != room["p1_required_area_mm2"]:
            raise ValueError("FUNCTIONAL_SIZING_P1_AREA_MISMATCH")
    return ctx


def _physical_key(room: Mapping[str, Any], scope: str) -> str:
    return canonical_hash(
        dict(
            project_scope_id=scope,
            room_code=room["room_code"],
            source_composition_hash=room["source_composition_hash"],
            world_bounds_mm=room["world_bounds_mm"],
            portals=[
                {k: p[k] for k in ("id", "segment_mm", "clear_width_mm")} for p in room["portals"]
            ],
        )
    )


def _checked_case(ctx: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in CASE_KEYS or key not in ctx["cases"]:
        raise ValueError("FUNCTIONAL_SIZING_VALIDATED_CASE_REQUIRED")
    case: dict[str, Any] = ctx["cases"][key]
    summary, geometry = case["summary"], case["geometry"]
    digest = hashlib.sha256(
        json.dumps(
            {k: case[k] for k in ("geometry", "shifts", "margins")},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    if (
        digest != summary["witness_sha256"]
        or geometry["room"]["source_historical_geometry"] != ctx["room"]
    ):
        raise ValueError("FUNCTIONAL_SIZING_WITNESS_SOURCE_MISMATCH")
    if not summary["full_flow_verified"] or len(case["shifts"]) != 2:
        raise ValueError("FUNCTIONAL_SIZING_FULL_SHIFT_EVIDENCE_REQUIRED")
    for shift in case["shifts"]:
        if (
            shift["status"] != "VERIFIED_UNDER_HYPOTHESES"
            or shift["design_users"] != 53
            or shift["initial_service_occupancy"] != 53
            or shift["completed_users"] != 53
            or len(set(shift["completed_person_ids"])) != 53
            or shift["remaining_inside"]
            or shift["not_entered_people"]
            or shift["blocker"]
        ):
            raise ValueError("FUNCTIONAL_SIZING_FULL_SHIFT_EVIDENCE_REQUIRED")
    return case


def _owner_facts(ctx: dict[str, Any]) -> dict[str, Any]:
    binding = ctx["r10"]["binding"]
    facts: dict[str, Any] = deepcopy(binding["reviewed_project_facts"])
    facts.update(deepcopy(binding["reviewed_design_requirements"]))
    for name, value, unit, source, digest in (
        ("PACKAGED_PRODUCT_MASS_KG_PER_DAY", 20000, "kg/day", OWNER_FILES[0], OWNER_HASHES[0]),
        ("CABINET_STRUCTURE", "FIVE_TIER_FIVE_DOOR", "structure", OWNER_FILES[1], OWNER_HASHES[1]),
    ):
        facts[name] = asdict(
            ReviewedProjectDatum(
                name, value, unit, ctx["scope"], "OWNER_CONFIRMED", _reference(source)
            )
        ) | {"source_sha256": digest}
    return facts


def _advisory(ctx: dict[str, Any], key: str) -> FunctionalRoomSizingAdvisoryV1:
    case = _checked_case(ctx, key)
    summary, g = case["summary"], case["geometry"]
    original = room_dimensions(ctx["room"]["local_bounds_mm"])
    advised = room_dimensions(g["room"]["local_bounds_mm"])
    extra_area = advised["area_mm2"] - original["area_mm2"]
    dx, dy = (
        advised["length_mm"] - original["length_mm"],
        advised["width_mm"] - original["width_mm"],
    )
    p1_ref = DimensionAuthorityReferenceV1(
        ctx["dimensions"]["calculator_identity"],
        "changing_room",
        ctx["binding"]["p1_hash"],
    )
    aliases = deepcopy(ctx["group"]["aliases"])
    mapping = deepcopy(g["room"]["boundary_mapping"])
    affected = [
        r["requirement_identity"]
        for r in ctx["candidates"][0]["engineering_validation"]["access_results"]
        if r.get("from_ref") == "changing_room" or r.get("to_ref") == "changing_room"
    ]
    body = dict(
        identity=IDENTITY,
        schema_version=SCHEMA_VERSION,
        project=dict(
            input_identity=PROJECT_INPUT_ID,
            scope_id=ctx["scope"],
            source_zone_plan_hash=ctx["binding"]["zone_plan_hash"],
            source_p1_handoff_hash=ctx["binding"]["p1_hash"],
            source_site_hash=ctx["binding"]["site_hash"],
            owner_confirmed_inputs=_owner_facts(ctx),
            personnel_identity="DESIGN_SLOTS_NOT_ACTUAL_EMPLOYEE_ROSTER",
        ),
        physical_room=dict(
            id=_physical_key(ctx["room"], ctx["scope"]),
            room_code="changing_room",
            handoff=5,
            physical_group="G01",
            aliases=aliases,
            room_count=1,
            source_composition_hash=ctx["room"]["source_composition_hash"],
        ),
        p1_requirement=dict(
            classification="ENGINEERING_DERIVED",
            dimension_authority_ref=asdict(p1_ref),
            required_area_mm2=ctx["room"]["p1_required_area_mm2"],
            original_authority=deepcopy(ctx["p1_row"]),
            source_sha256=ctx["hashes"][f"{HISTORICAL}/server-authorities.json"],
            authority_row_hash=canonical_hash(ctx["p1_row"]),
            immutable_reference="sha256:"
            + ctx["hashes"][f"{HISTORICAL}/server-authorities.json"]
            + "#/p1/p1e_historical_handoff/dimension_handoff/authorities",
            repository_copy=f"{HISTORICAL}/server-authorities.json",
            original_sealed_reference=ctx["room"]["p1_area_source"],
            modifies_authority=False,
        ),
        original_room=dict(
            **original,
            world_bounds_mm=ctx["room"]["world_bounds_mm"],
            portals=ctx["room"]["portals"],
            historical_status="EXISTING_STAGE_B_ELIGIBLE",
            functional_sufficiency="INPUT_REQUIRED_NOT_DECLARED_FACTORY_FAILURE",
            portal_coordinate_system="ROOM_LOCAL_INTEGER_MM",
        ),
        advised_room=dict(
            **advised,
            id=key,
            label=CASE_LABELS[CASE_KEYS.index(key)],
            additional_area_mm2=extra_area,
            additional_area_reference="ORIGINAL_PHYSICAL_H5_NOT_P1_REQUIRED_AREA",
            additional_area_m2=f"{extra_area // 1000000}.{extra_area % 1000000:06d}",
            length_increase_mm=dx,
            width_increase_mm=dy,
            portals=g["room"]["portals"],
            classification="HYPOTHETICAL_NOT_APPROVED",
        ),
        conditions=dict(
            classification="HYPOTHETICAL_NOT_APPROVED",
            parameters=g["conditions"],
            profile=summary["point"]["profile"],
            template_padding_mm=summary["point"]["margin_mm"],
            actual_front_parameters=g["front_parameters"],
            actual_layout_parameters=g["parameters"],
            approval="INPUT_REQUIRED",
        ),
        functional_evidence=dict(
            classification="ENGINEERING_DERIVED",
            status="CONDITIONAL_FLOW_PASS",
            shifts=[
                {
                    k: s[k]
                    for k in (
                        "shift",
                        "status",
                        "design_users",
                        "initial_service_occupancy",
                        "completed_users",
                        "completed_person_ids",
                        "completed_batches",
                        "expected_batches",
                    )
                }
                | {"event_count": len(s["events"]), "events_hash": canonical_hash(s["events"])}
                for s in case["shifts"]
            ],
            witness_sha256=summary["witness_sha256"],
            reference=_reference(f"{R10}/selected-evidence.json.gz", key),
            codec="gzip+json",
            evidence_sha256=ctx["hashes"][f"{R10}/selected-evidence.json.gz"],
            validation_mode="ARCHIVED_COMPLETE_FUNCTIONAL_WITNESS_NOT_RERUN",
            timing_and_throughput="NOT_EVALUATED_UNCONFIRMED_TIMES",
        ),
        margins=dict(
            classification="ENGINEERING_DERIVED",
            derived_from_unapproved_conditions=True,
            minimum=summary["limiting_margin"],
            minimum_mm=summary["minimum_margin_mm"],
            north_wall_mm=summary["north_wall_margin_mm"],
            template_target_met=summary["margin_target_met"],
            families=case["margins"]["families"],
            section_chain_mm=case["margins"]["section_chain_mm"],
            normative_minimum=False,
            uniform_all_around_buffer=False,
        ),
        external_impact=dict(
            length_increase_mm=dx,
            width_increase_mm=dy,
            additional_area_mm2=extra_area,
            boundary_anchor=mapping["anchor"],
            portal_coordinate_system="ROOM_LOCAL_INTEGER_MM_WITH_ORIGINAL_WEST_SOUTH_ANCHOR",
            portal_mappings=mapping["portal_mappings"],
            any_portal_moved=any(m["position_changed"] for m in mapping["portal_mappings"]),
            site="NOT_EVALUATED_REVALIDATION_REQUIRED",
            footprint="NOT_EVALUATED_REVALIDATION_REQUIRED",
            external_access="NOT_EVALUATED_REVALIDATION_REQUIRED",
            neighboring_rooms_and_process="NOT_EVALUATED_REVIEW_REQUIRED",
            affected_original_access_requirements=affected,
            original_factory_can_accommodate_expansion="NOT_EVALUATED",
        ),
        owner_confirmation_checklist=[
            dict(id=code, item=label, status="INPUT_REQUIRED") for code, label in CONFIRMATIONS
        ],
        sources=[
            dict(
                reference="sha256:" + digest if path.startswith(HISTORICAL) else _reference(path),
                repository_path=path,
                sha256=digest,
            )
            for path, digest in sorted(ctx["hashes"].items())
        ],
        invalidation_conditions=[
            "project, P1, Site, composition, candidate geometry or Portal identity changes",
            "Owner source bytes or source evidence hashes change or required evidence is missing",
            "cabinet, body, finish, installation, operation or other hypothesis changes",
            "functional adapter or validation version changes; no automatic upgrade after review",
        ],
        approval_boundary=APPROVAL_BOUNDARY,
        comparison_scope=dict(
            conditions_hash=canonical_hash(g["conditions"]),
            ranking="NOT_EVALUATED",
            safety_comparison="NOT_EVALUATED",
            pareto="NOT_EVALUATED_NOT_FORMAL_COMPARATOR",
        ),
        units="integer mm; mm2; six-decimal m2",
        calculation_basis=dict(
            version=IDENTITY,
            formulas=[
                "area_mm2=length_mm*width_mm",
                "additional_area_mm2=advised_area_mm2-original_area_mm2",
            ],
            source_type="demo",
            validity_status="unverified",
            requires_review=True,
        ),
    )
    return FunctionalRoomSizingAdvisoryV1(canonical_json(body))


def preview_functional_sizing_handoff(
    files: Mapping[str, bytes],
    *,
    project_scope_id: str,
    layout_candidates: Sequence[Mapping[str, Any]],
    room_code: str = "changing_room",
    advisory_payloads: Sequence[Mapping[str, Any]] | None = None,
    project_input_identity: str = PROJECT_INPUT_ID,
) -> dict[str, Any]:
    """No execution/DB/approval ports. All supplied identities are checked afresh."""
    ctx = _context(files)
    if project_scope_id != ctx["scope"] or project_input_identity != PROJECT_INPUT_ID:
        raise ValueError("FUNCTIONAL_SIZING_PROJECT_SCOPE_MISMATCH")
    if room_code != "changing_room":
        return dict(
            status="FUNCTIONAL_ADAPTER_REQUIRED",
            room_code=room_code,
            advisories=[],
            actual_functional_status="INPUT_REQUIRED",
            authority_effect="NONE",
        )
    if not layout_candidates or len(layout_candidates) > 2:
        raise ValueError("FUNCTIONAL_SIZING_ARCHIVED_LAYOUT_REQUIRED")
    accepted = {canonical_hash(c): c for c in ctx["candidates"]}
    selected = []
    for c in layout_candidates:
        if canonical_hash(c) not in accepted:
            raise ValueError("FUNCTIONAL_SIZING_LAYOUT_SOURCE_MISMATCH")
        selected.append(str(c["canonical_result_hash"]))
    if len(set(selected)) != len(selected):
        raise ValueError("FUNCTIONAL_SIZING_DUPLICATE_CANDIDATE_RECORD")
    expected = {a.canonical_result_hash: a for a in (_advisory(ctx, key) for key in CASE_KEYS)}
    if advisory_payloads is None:
        advisories = list(expected.values())
    else:
        if not advisory_payloads or len(advisory_payloads) > 3:
            raise ValueError("FUNCTIONAL_SIZING_ADVISORY_SELECTION_REQUIRED")
        advisories = []
        for payload in advisory_payloads:
            advisory = FunctionalRoomSizingAdvisoryV1.from_dict(dict(payload))
            if advisory.canonical_result_hash not in expected:
                raise ValueError("FUNCTIONAL_SIZING_ADVISORY_EVIDENCE_MISMATCH")
            advisories.append(advisory)
        if len({a.canonical_result_hash for a in advisories}) != len(advisories):
            raise ValueError("FUNCTIONAL_SIZING_DUPLICATE_ADVISORY")
    original = room_dimensions(ctx["room"]["local_bounds_mm"])
    return dict(
        task=TASK,
        interface="READ_ONLY_FUNCTIONAL_SIZING_ADVISORY_PREVIEW",
        project_scope_id=ctx["scope"],
        physical_room_count=1,
        physical_room_id=_physical_key(ctx["room"], ctx["scope"]),
        supplied_candidate_hashes=sorted(selected),
        aliases=["P01", "P02"],
        original_room=original
        | {
            "portals": deepcopy(ctx["room"]["portals"]),
            "functional_status": "INPUT_REQUIRED",
            "historical_engineering_status": "PRESERVED",
        },
        p1_required_area_mm2=ctx["room"]["p1_required_area_mm2"],
        p1_required_area_m2=area_text(ctx["room"]["p1_required_area_mm2"]),
        advisories=[a.to_dict() for a in advisories],
        comparison_policy="GROUP_BY_CONDITIONS_DESCRIPTIVE_ONLY_NO_GLOBAL_OPTIMUM_OR_SAFETY_RANKING",
        owner_confirmed_inputs=_owner_facts(ctx),
        owner_confirmation_checklist=[
            dict(id=k, item=v, status="INPUT_REQUIRED") for k, v in CONFIRMATIONS
        ],
        applicability="MATCHED_SOURCE_AND_CONDITIONS_ONLY_NOT_FACTORY_FIT",
        approval_boundary=dict(APPROVAL_BOUNDARY),
        writes_production=False,
        changes_p1=False,
        changes_stage_b=False,
        native_solves=0,
    )
