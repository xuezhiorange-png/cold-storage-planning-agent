"""R11 R2 project-scoped functional data; neither an approval port nor a P2 solver.

The R11 R1 historical record is read-only. Caller-reviewed project values are
separate from the canonical Owner V2 policy and from the 20t inbound fixture.
This module cannot authenticate a reviewer: the embedding application must do so.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Literal

OWNER_ID = "OwnerFactoryFunctionalInputsV2"
PROJECT_INPUT_ID = "FROZEN_20T_REGRESSION_FIXTURE_NOT_XINZHAO"
R10_HEAD = "288a56b768baa859cbcfb41908fbbd5d6155094d"
VERSION = "r11-project-functional-input-binding@2.0.1"
UNITS = MappingProxyType(
    {
        "PACKAGED_PRODUCT_MASS_KG_PER_DAY": "kg/day",
        "SHIFT_1_WORKERS": "people",
        "SHIFT_2_WORKERS": "people",
        "SHIFT_1_PACKAGED_PRODUCT_MASS_KG": "kg/shift",
        "SHIFT_2_PACKAGED_PRODUCT_MASS_KG": "kg/shift",
        "FACTORY_SIZE": "factory_size",
    }
)
REQUIRED_POLICY = (
    "PACKAGING_PIECES_PER_PERSON_HOUR",
    "PACKAGING_WEIGHT_PER_PIECE_KG",
    "SHIFT_HOURS",
    "SHIFTS_PER_DAY",
    "PERSON_SHIFT_CAPACITY_KG",
    "PACKAGING_MASS_BASIS",
    "SHIFT_ALLOCATION_POLICY",
    "SHIFT_1_RATIO",
    "SHIFT_2_RATIO",
    "PERSONAL_LOCKER_PER_EMPLOYEE",
    "LOCKER_SHARED_BETWEEN_SHIFTS",
    "LOCKER_INTERNAL_SEPARATION",
    "SHIFT_CHANGE_POLICY",
    "CHANGING_ROOM_USERS",
    "WORKERS_PER_PACKING_TABLE",
    "OFFICE_DESIGN_STAFF.SMALL",
    "OFFICE_DESIGN_STAFF.MEDIUM",
    "OFFICE_DESIGN_STAFF.LARGE",
    "PROCESS_TYPE",
    "DESIGN_FILM_SEALING_RATIO",
    "SEALING_RUNTIME_INHERITS_PACKAGING_HOURS",
)


@dataclass(frozen=True)
class ReviewedProjectDatum:
    """Typed result of external document and applicability review, not a token.

    Do not construct this object directly from a user-submitted JSON label.
    There is deliberately no CLI that converts proposals to this type.
    """

    field_name: str
    value: str | int
    unit: str
    project_scope_id: str
    source_label: Literal["OWNER_CONFIRMED", "ENGINEERING_DERIVED"]
    reference: str


def _positive_decimal(value: Any, *, allow_zero: bool = False) -> Decimal:
    if type(value) is not int and type(value) is not str:
        raise ValueError("EXPLICIT_NON_FLOAT_PACKAGED_MASS_REQUIRED")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_PACKAGED_PRODUCT_MASS") from exc
    if not result.is_finite() or result < 0 or (not allow_zero and result == 0):
        raise ValueError("INVALID_PACKAGED_PRODUCT_MASS")
    return result


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _project_scope(review: Mapping[str, Any]) -> str:
    if (
        review.get("task") != "V2_2_2_R11_FUNCTIONAL_ROOM_FIT_R1"
        or review.get("source_head") != R10_HEAD
        or review.get("history_unchanged") is not True
        or review.get("original_record_count") != 9
        or review.get("physical_group_count") != 8
    ):
        raise ValueError("R11_SEALED_REVIEW_IDENTITY_REQUIRED")
    rooms = review.get("room_evaluations")
    if not isinstance(rooms, list) or len(rooms) != 27:
        raise ValueError("EXPECTED_27_SEALED_ROOM_RECORDS")
    scope = ""
    for entry in rooms:
        room = entry["room"]
        pieces = str(room["scope_id"]).split(":")
        if (
            len(pieces) != 7
            or pieces[0] != "sha256"
            or pieces[2] != "sha256"
            or pieces[4] != "sha256"
            or any(
                len(pieces[i]) != 64 or any(c not in "0123456789abcdef" for c in pieces[i])
                for i in (1, 3, 5)
            )
            or pieces[6] != room["room_code"]
            or pieces[6] not in {"changing_room", "office", "coating_room"}
            or entry["evaluation"]["functional_status"] != "INPUT_REQUIRED"
            or entry["evaluation"]["p1_area_status"] != "AREA_SATISFIED"
        ):
            raise ValueError("R11_HISTORICAL_SCOPE_OR_STATUS_MISMATCH")
        current = ":".join(pieces[:4])
        if scope and scope != current:
            raise ValueError("MIXED_PLAN_OR_P1_AUTHORITY")
        scope = current
    return scope


def _owner_rules(review: Mapping[str, Any], source: bytes) -> tuple[dict[str, Any], str]:
    digest = hashlib.sha256(source).hexdigest()
    if digest != review["owner_business_rules"]["sha256"]:
        raise ValueError("OWNER_V2_SOURCE_HASH_MISMATCH")
    owner = json.loads(source)
    if (
        owner.get("identity") != OWNER_ID
        or owner.get("contract_version") != "owner-factory-functional-inputs@2.0.0"
    ):
        raise ValueError("OWNER_V2_IDENTITY_REQUIRED")
    rules = owner.get("rules")
    if not isinstance(rules, list):
        raise ValueError("OWNER_V2_RULES_REQUIRED")
    index = {r["FIELD_NAME"]: r for r in rules}
    if len(index) != len(rules) or any(
        key not in index or index[key]["SOURCE"] != "OWNER_CONFIRMED" for key in REQUIRED_POLICY
    ):
        raise ValueError("OWNER_V2_POLICY_INCOMPLETE")
    return {k: v["VALUE"] for k, v in index.items()}, digest


def _policy_check(policy: Mapping[str, Any]) -> tuple[Decimal, tuple[Decimal, Decimal]]:
    capacity = (
        Decimal(str(policy["PACKAGING_PIECES_PER_PERSON_HOUR"]))
        * Decimal(str(policy["PACKAGING_WEIGHT_PER_PIECE_KG"]))
        * Decimal(str(policy["SHIFT_HOURS"]))
    )
    shares = (Decimal(str(policy["SHIFT_1_RATIO"])), Decimal(str(policy["SHIFT_2_RATIO"])))
    if (
        capacity != Decimal(str(policy["PERSON_SHIFT_CAPACITY_KG"]))
        or capacity <= 0
        or policy["SHIFTS_PER_DAY"] != 2
        or policy["PACKAGING_MASS_BASIS"] != "PACKAGED_PRODUCT_MASS"
        or policy["SHIFT_ALLOCATION_POLICY"] != "DEFAULT_EQUAL_SPLIT"
        or shares != (Decimal("0.5"), Decimal("0.5"))
        or policy["PERSONAL_LOCKER_PER_EMPLOYEE"] != 1
        or policy["LOCKER_SHARED_BETWEEN_SHIFTS"] is not False
        or policy["LOCKER_INTERNAL_SEPARATION"] is not True
        or policy["SHIFT_CHANGE_POLICY"] != "NON_OVERLAPPING"
        or policy["CHANGING_ROOM_USERS"] != "PACKAGING_WORKERS_ONLY"
        or policy["WORKERS_PER_PACKING_TABLE"] != 3
        or policy["PROCESS_TYPE"] != "PACKAGING_BOX_FILM_SEALING"
        or Decimal(str(policy["DESIGN_FILM_SEALING_RATIO"])) != 1
        or policy["SEALING_RUNTIME_INHERITS_PACKAGING_HOURS"] is not False
    ):
        raise ValueError("OWNER_V2_BUSINESS_RULE_CONFLICT")
    return capacity, shares


def _reviewed_inputs(
    evidence: Mapping[str, ReviewedProjectDatum] | None, scope_id: str
) -> dict[str, ReviewedProjectDatum]:
    checked: dict[str, ReviewedProjectDatum] = {}
    for field, datum in (evidence or {}).items():
        if field not in UNITS or not isinstance(datum, ReviewedProjectDatum):
            raise ValueError("TRUSTED_APPLICATION_REVIEW_REQUIRED")
        if (
            datum.field_name != field
            or datum.project_scope_id != scope_id
            or datum.unit != UNITS[field]
            or not isinstance(datum.reference, str)
            or not datum.reference.strip()
            or datum.source_label not in {"OWNER_CONFIRMED", "ENGINEERING_DERIVED"}
        ):
            raise ValueError("REVIEWED_PROJECT_SOURCE_OR_SCOPE_MISMATCH")
        if field == "FACTORY_SIZE":
            if datum.value not in {"SMALL", "MEDIUM", "LARGE"}:
                raise ValueError("EXPLICIT_FACTORY_SIZE_REQUIRED")
        elif field in {"SHIFT_1_WORKERS", "SHIFT_2_WORKERS"}:
            if type(datum.value) is not int or datum.value < 1:
                raise ValueError("EXPLICIT_SHIFT_WORKERS_REQUIRED")
        else:
            _positive_decimal(datum.value, allow_zero=field.endswith("_MASS_KG"))
        checked[field] = datum
    return checked


def bind_project_functional_inputs(
    review: Mapping[str, Any],
    owner_source: bytes,
    *,
    reviewed_project: Mapping[str, ReviewedProjectDatum] | None = None,
) -> dict[str, Any]:
    """Prepare scoped R11 facts without authenticating data or approving rooms."""
    scope = _project_scope(review)
    rules, owner_sha = _owner_rules(review, owner_source)
    capacity, shares = _policy_check(rules)
    facts = _reviewed_inputs(reviewed_project, scope)
    mass_datum = facts.get("PACKAGED_PRODUCT_MASS_KG_PER_DAY")
    mass = _positive_decimal(mass_datum.value) if mass_datum else None
    left, right = (facts.get("SHIFT_1_WORKERS"), facts.get("SHIFT_2_WORKERS"))
    workload_facts = (
        facts.get("SHIFT_1_PACKAGED_PRODUCT_MASS_KG"),
        facts.get("SHIFT_2_PACKAGED_PRODUCT_MASS_KG"),
    )
    workloads = tuple(
        _positive_decimal(datum.value, allow_zero=True) if datum else None
        for datum in workload_facts
    )
    explicit_staffing = left is not None or right is not None
    allocation_basis = "REVIEWED_SHIFT_WORKLOADS" if all(workload_facts) else None
    allocation_reference = "; ".join(datum.reference for datum in workload_facts if datum)
    if not explicit_staffing and mass is not None and not any(workload_facts):
        assert mass_datum is not None
        workloads = (mass * shares[0], mass * shares[1])
        allocation_basis = "OWNER_V2_DEFAULT_EQUAL_SPLIT"
        allocation_reference = "OwnerV2:DEFAULT_EQUAL_SPLIT; " + str(mass_datum.reference)
    conflict = None
    staff_reference = None
    workers = None
    if bool(left) != bool(right):
        conflict = "BOTH_SHIFT_COUNTS_REQUIRED_FOR_EXPLICIT_OVERRIDE"
    elif left is not None and right is not None:
        workers = (int(left.value), int(right.value))
        staff_reference = left.reference + "; " + right.reference
    elif mass is not None and allocation_basis is not None:
        assert workloads[0] is not None and workloads[1] is not None
        workers = (_ceil(workloads[0] / capacity), _ceil(workloads[1] / capacity))
        staff_reference = allocation_reference

    aggregate_validation = "INPUT_REQUIRED_PACKAGED_MASS"
    if mass is not None:
        aggregate_validation = "INPUT_REQUIRED_WORKFORCE"
        if workers is not None:
            if sum(workers) * capacity < mass:
                aggregate_validation = "INSUFFICIENT_TOTAL"
                conflict = conflict or "REVIEWED_SHIFT_CAPACITY_BELOW_PACKAGED_MASS"
            else:
                aggregate_validation = "SUFFICIENT_TOTAL_ONLY"
    allocation_conflict = (
        mass is not None
        and workloads[0] is not None
        and workloads[1] is not None
        and workloads[0] + workloads[1] != mass
    )
    if allocation_conflict:
        conflict = conflict or "REVIEWED_SHIFT_WORKLOADS_DO_NOT_SUM_TO_DAILY_MASS"
    shift_checks = []
    for index, workload in enumerate(workloads):
        shift_capacity = workers[index] * capacity if workers is not None else None
        status = "INPUT_REQUIRED_SHIFT_WORKLOAD"
        if allocation_conflict:
            status = "NOT_EVALUATED_ALLOCATION_CONFLICT"
        elif workload is not None:
            if shift_capacity is None:
                status = "INPUT_REQUIRED_WORKFORCE"
            elif workload > shift_capacity:
                status = "EXCEEDED"
                conflict = conflict or "REVIEWED_SHIFT_WORKLOAD_EXCEEDS_CAPACITY"
            else:
                status = "SATISFIED"
        shift_checks.append(
            dict(
                shift=index + 1,
                packaged_product_mass_kg=str(workload) if workload is not None else None,
                capacity_kg=str(shift_capacity) if shift_capacity is not None else None,
                status=status,
            )
        )
    if conflict:
        capacity_validation = "CONFLICT"
    elif mass is None:
        capacity_validation = "INPUT_REQUIRED_PACKAGED_MASS"
    elif workers is None:
        capacity_validation = "INPUT_REQUIRED_WORKFORCE"
    elif allocation_basis is None:
        capacity_validation = "INPUT_REQUIRED_SHIFT_WORKLOAD_ALLOCATION"
    else:
        capacity_validation = "SATISFIED"
    size = facts.get("FACTORY_SIZE")
    office_staff = int(rules["OFFICE_DESIGN_STAFF." + str(size.value)]) if size else None
    if workers is None:
        locker_counts = None
        simultaneous = None
        tables = None
    else:
        locker_counts = list(workers)
        simultaneous = max(workers)
        tables = (simultaneous + int(rules["WORKERS_PER_PACKING_TABLE"]) - 1) // int(
            rules["WORKERS_PER_PACKING_TABLE"]
        )
    missing = [
        name for name in ("PACKAGED_PRODUCT_MASS_KG_PER_DAY", "FACTORY_SIZE") if name not in facts
    ]
    if workers is None:
        missing.append("SHIFT_WORKFORCE_REVIEW_OR_PACKAGED_MASS_DERIVATION")
    if allocation_basis is None:
        missing.append("SHIFT_WORKLOAD_ALLOCATION_BASIS")
        missing.extend(
            name
            for name, datum in zip(
                ("SHIFT_1_PACKAGED_PRODUCT_MASS_KG", "SHIFT_2_PACKAGED_PRODUCT_MASS_KG"),
                workload_facts,
                strict=True,
            )
            if datum is None
        )
    return dict(
        version=VERSION,
        task="V2_2_2_R11_FUNCTIONAL_PROJECT_INPUT_BINDING_R2",
        project_identity=PROJECT_INPUT_ID,
        project_scope_id=scope,
        owner_contract_sha256=owner_sha,
        owner_contract_identity=OWNER_ID,
        original_records=9,
        original_physical_groups=8,
        original_room_records=27,
        source_review_task=review["task"],
        user_supplied_inbound_kg_per_day_not_used=True,
        input_review_is_external_prerequisite=True,
        project_reviewed_facts={
            key: dict(
                value=value.value,
                unit=value.unit,
                source_label=value.source_label,
                reference=value.reference,
                project_scope_id=value.project_scope_id,
            )
            for key, value in facts.items()
        },
        owner_confirmed_policy=dict(
            shifts_per_day=2,
            shift_change_policy="NON_OVERLAPPING",
            locker_shared_between_shifts=False,
            locker_internal_separation=True,
            packaged_product_capacity_kg_per_person_shift=str(capacity),
            packaged_product_mass_only=True,
            film_sealing_process=rules["PROCESS_TYPE"],
            design_film_ratio=str(rules["DESIGN_FILM_SEALING_RATIO"]),
            film_sealing_runtime_requires_separate_review=True,
        ),
        workforce=dict(
            status=(
                "REVIEWED_PROJECT_BASIS"
                if workers
                else "INPUT_CONFLICT"
                if conflict
                else "INPUT_REQUIRED"
            ),
            shift_1_workers=workers[0] if workers else None,
            shift_2_workers=workers[1] if workers else None,
            separate_personal_lockers=locker_counts,
            simultaneous_changing_users=simultaneous,
            required_packing_tables=tables,
            source_reference=staff_reference,
            derived_from_packaged_product_mass=workers is not None and not explicit_staffing,
            capacity_validation=capacity_validation,
            aggregate_capacity_validation=aggregate_validation,
            shift_workload_allocation_basis=allocation_basis,
            shift_workload_source_reference=allocation_reference or None,
            per_shift_capacity=shift_checks,
        ),
        office=dict(
            factory_size=size.value if size else None,
            staff_count=office_staff,
            source_reference=size.reference if size else None,
            status="REVIEWED_PROJECT_BASIS" if size else "INPUT_REQUIRED",
        ),
        coating=dict(
            process_type=rules["PROCESS_TYPE"],
            design_film_ratio=str(rules["DESIGN_FILM_SEALING_RATIO"]),
            equipment_model=None,
            equipment_capacity=None,
            runtime_hours=None,
            status="INPUT_REQUIRED_EQUIPMENT_AND_RUNTIME",
        ),
        missing_project_inputs=missing,
        conflict=conflict,
        binding_status=(
            "INPUT_CONFLICT"
            if conflict
            else "INPUT_REQUIRED"
            if missing
            else "PROJECT_STAFFING_BASIS_READY_ROOM_FIT_PENDING"
        ),
        functional_approval=False,
        p1_modified=False,
        original_engineering_acceptance_modified=False,
        quality_comparators_modified=False,
        old_grants_claims_modified=False,
        native_solves=0,
    )


def project_candidate_room_inputs(
    review: Mapping[str, Any], binding: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Project known source fields into R11, preserving INPUT_REQUIRED for witnesses."""
    from cold_storage.modules.layout.domain.functional_room_fit import (
        COMMON,
        REQUIRED,
        BasisValue,
        evaluate_functional_room,
    )

    if binding.get("project_scope_id") != _project_scope(review):
        raise ValueError("PROJECT_AND_ROOM_SCOPE_MISMATCH")
    policy = binding["owner_confirmed_policy"]
    workforce = binding["workforce"]
    office = binding["office"]
    out = []
    for row in review["room_evaluations"]:
        room = row["room"]
        code = room["room_code"]
        allowed = COMMON | REQUIRED[code]
        choices: dict[str, tuple[Any, Literal["OWNER_CONFIRMED", "ENGINEERING_DERIVED"], str]] = {}
        if code == "changing_room":
            choices = {
                "shift_change_policy": (
                    policy["shift_change_policy"],
                    "OWNER_CONFIRMED",
                    "OwnerV2:SHIFT_CHANGE_POLICY",
                ),
                "internal_clothing_separation": (
                    policy["locker_internal_separation"],
                    "OWNER_CONFIRMED",
                    "OwnerV2:LOCKER_INTERNAL_SEPARATION",
                ),
            }
            if workforce["status"] == "REVIEWED_PROJECT_BASIS":
                choices["shift_locker_counts"] = (
                    workforce["separate_personal_lockers"],
                    "ENGINEERING_DERIVED",
                    str(workforce["source_reference"]),
                )
                choices["simultaneous_users"] = (
                    workforce["simultaneous_changing_users"],
                    "ENGINEERING_DERIVED",
                    str(workforce["source_reference"]),
                )
        elif code == "office" and office["status"] == "REVIEWED_PROJECT_BASIS":
            choices = {
                "staff_count": (
                    office["staff_count"],
                    "ENGINEERING_DERIVED",
                    str(office["source_reference"]),
                )
            }
        elif code == "coating_room":
            choices = {
                "process_type": (
                    policy["film_sealing_process"],
                    "OWNER_CONFIRMED",
                    "OwnerV2:PROCESS_TYPE",
                )
            }
        refs: dict[str, str] = {}
        basis: dict[str, BasisValue] = {}
        for field, (value, source, reference) in choices.items():
            key = room["scope_id"] + ":" + field
            refs[field] = key
            basis[key] = BasisValue(
                value=value,
                unit=allowed[field],
                source_label=source,
                reference=reference,
                scope_id=room["scope_id"],
                field_name=field,
            )
        evaluation = evaluate_functional_room(room, refs, reviewed_basis=basis)
        if (
            evaluation["functional_status"] != "INPUT_REQUIRED"
            or evaluation["p1_area_status"] != row["evaluation"]["p1_area_status"]
            or evaluation["original_engineering_status"]
            != row["evaluation"]["original_engineering_status"]
        ):
            raise ValueError("HISTORICAL_OUTCOME_MUST_NOT_CHANGE")
        out.append(
            dict(
                record=row["record"],
                handoff=row["handoff"],
                physical_group=row["physical_group"],
                room_code=code,
                candidate_hash=room["candidate_hash"],
                project_fields_bound=sorted(choices),
                remaining_inputs=evaluation["missing_inputs"],
                original_engineering_status=evaluation["original_engineering_status"],
                p1_area_status=evaluation["p1_area_status"],
                functional_status=evaluation["functional_status"],
                source_scope=room["scope_id"],
            )
        )
    if len(out) != 27:
        raise ValueError("EXPECTED_27_ROOM_PROJECT_VIEWS")
    return out
