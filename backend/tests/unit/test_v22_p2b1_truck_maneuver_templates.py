"""P2B1 project-supplied maneuver-template contract tests."""

from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal

import pytest

from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.truck_maneuver import (
    CONTRACT_IDENTITY,
    DOCK_FACE_REFERENCE,
    DOCK_REVERSE,
    FORWARD_AXIS,
    GRID_M,
    MANEUVER_90_DEGREE_TURN,
    MANEUVER_DOCK_REVERSE,
    MANEUVER_STRAIGHT_APPROACH,
    ORIGIN_REFERENCE,
    PROJECT_INPUT,
    REFERENCE_FRAME,
    STRAIGHT_APPROACH,
    SUPPORTED_MANEUVER_CLASSES,
    SUPPORTED_TRANSFORM_ROTATIONS,
    TURN_90,
    TruckManeuverProjectInputV1,
    TruckManeuverRequirementV1,
    TruckManeuverTemplateSetV1,
    TruckManeuverTemplateV1,
    maneuver_project_input_payload_with_hash,
    maneuver_requirement_payload_with_hash,
    maneuver_template_payload_with_hash,
    maneuver_template_set_payload_with_hash,
    transform_maneuver_template,
    validate_truck_maneuver_project_input,
    validate_truck_maneuver_template,
)


def reference() -> dict[str, object]:
    return {
        "reference_frame": REFERENCE_FRAME,
        "forward_axis": FORWARD_AXIS,
        "origin_reference": ORIGIN_REFERENCE,
        "vehicle_reference_point": {"x": 0, "y": 0},
        "entry_pose": {"x": 0, "y": 0, "rotation_deg": 0},
        "exit_pose": {"x": 12, "y": 0, "rotation_deg": 0},
    }


def template_payload(
    maneuver_class: str = STRAIGHT_APPROACH,
    *,
    template_id: str | None = None,
    project_id: str = "fixture-project",
    **extra: object,
) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "source_authority": PROJECT_INPUT,
        "template_id": template_id or maneuver_class.lower(),
        "maneuver_class": maneuver_class,
        "vehicle_width_m": Decimal("2.400"),
        "vehicle_length_m": Decimal("12.000"),
        "envelope_geometry": {
            "type": "polygon",
            "points": [
                {"x": 0, "y": -2},
                {"x": 12, "y": -2},
                {"x": 12, "y": 2},
                {"x": 0, "y": 2},
            ],
        },
        "reference": reference(),
        "provided_by": "fixture-owner",
        **extra,
    }
    if maneuver_class == TURN_90 and "turn_direction" not in body:
        return body
    if maneuver_class == DOCK_REVERSE and not {
        "dock_face_reference",
        "approach_pose",
        "final_dock_pose",
    } <= set(body):
        return body
    return maneuver_template_payload_with_hash(body)


def template_object(
    maneuver_class: str = STRAIGHT_APPROACH, **extra: object
) -> TruckManeuverTemplateV1:
    return TruckManeuverTemplateV1.from_mapping(template_payload(maneuver_class, **extra))


def requirement_payload(
    classes: list[str] | tuple[str, ...] = (STRAIGHT_APPROACH,),
    *,
    project_id: str = "fixture-project",
) -> dict[str, object]:
    return maneuver_requirement_payload_with_hash(
        {
            "schema_version": "1.0.0",
            "project_id": project_id,
            "source_authority": PROJECT_INPUT,
            "required_maneuver_classes": list(classes),
            "provided_by": "fixture-owner",
        }
    )


def template_set_payload(
    templates: list[dict[str, object]] | None = None,
    *,
    project_id: str = "fixture-project",
) -> dict[str, object]:
    return maneuver_template_set_payload_with_hash(
        {
            "schema_version": "1.0.0",
            "project_id": project_id,
            "source_authority": PROJECT_INPUT,
            "templates": templates if templates is not None else [template_payload()],
            "provided_by": "fixture-owner",
        }
    )


def project_payload(
    templates: list[dict[str, object]] | None = None,
    classes: list[str] | tuple[str, ...] = (STRAIGHT_APPROACH,),
) -> dict[str, object]:
    return maneuver_project_input_payload_with_hash(
        {
            "schema_version": "1.0.0",
            "project_id": "fixture-project",
            "source_authority": PROJECT_INPUT,
            "template_set": template_set_payload(templates),
            "requirement": requirement_payload(classes),
            "provided_by": "fixture-owner",
        }
    )


def assert_code(exc: pytest.ExceptionInfo[LayoutAuthorityError], code: str) -> None:
    assert exc.value.code == code


def test_contract_identity_geometry_and_all_approved_maneuver_classes() -> None:
    assert CONTRACT_IDENTITY == "truck-maneuver-template-contract@1.0.0"
    assert str(GRID_M) == "0.001"
    assert MANEUVER_STRAIGHT_APPROACH
    assert MANEUVER_90_DEGREE_TURN
    assert MANEUVER_DOCK_REVERSE
    assert SUPPORTED_MANEUVER_CLASSES == (STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE)
    assert SUPPORTED_TRANSFORM_ROTATIONS == (0, 90, 180, 270)

    straight = template_object()
    turn = template_object(TURN_90, turn_direction="LEFT")
    dock = template_object(
        DOCK_REVERSE,
        dock_face_reference=DOCK_FACE_REFERENCE,
        approach_pose={"x": 0, "y": 0, "rotation_deg": 0},
        final_dock_pose={"x": 12, "y": 0, "rotation_deg": 180},
    )
    assert {straight.maneuver_class, turn.maneuver_class, dock.maneuver_class} == set(
        SUPPORTED_MANEUVER_CLASSES
    )
    assert straight.identity == "truck-maneuver-template:fixture-project:straight_approach@1.0.0"
    assert dock.to_dict()["dock_face_reference"] == DOCK_FACE_REFERENCE


@pytest.mark.parametrize("maneuver_class", ["U_TURN", "THREE_POINT_TURN", "CUSTOM"])
def test_unsupported_maneuver_class_is_rejected(maneuver_class: str) -> None:
    with pytest.raises(LayoutAuthorityError) as exc:
        template_object(maneuver_class)
    assert_code(exc, "UNAUTHORIZED_TRUCK_MANEUVER_CLASS")


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_authority", "VERSION_CONSTANT"),
        ("vehicle_width_m", True),
        ("vehicle_length_m", Decimal("0")),
        ("vehicle_width_m", Decimal("2.4001")),
        ("provided_by", " "),
    ],
)
def test_template_authority_and_geometry_values_fail_closed(field: str, value: object) -> None:
    body = template_payload()
    body[field] = value
    if field in {"source_authority", "provided_by"}:
        # Authoring helpers intentionally derive a new hash, so validate the raw mutation.
        pass
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert exc.value.code in {
        "INVALID_TRUCK_MANEUVER_TEMPLATE",
        "INVALID_MANEUVER_ENVELOPE",
    }


def test_unknown_fields_and_missing_required_fields_are_rejected() -> None:
    body = template_payload()
    body["default_template"] = True
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert_code(exc, "INVALID_TRUCK_MANEUVER_TEMPLATE")

    body = template_payload()
    del body["reference"]
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert_code(exc, "TRUCK_MANEUVER_TEMPLATE_REQUIRED")


@pytest.mark.parametrize(
    "geometry",
    [
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 12, "y": 12},
                {"x": 0, "y": 12},
                {"x": 12, "y": 0},
            ],
        },
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 12, "y": 0},
                {"x": 12, "y": 2},
                {"x": 12, "y": 2},
                {"x": 0, "y": 2},
            ],
        },
        {
            "type": "polygon",
            "points": [
                {"x": 0, "y": 0},
                {"x": 12.0001, "y": 0},
                {"x": 12, "y": 2},
                {"x": 0, "y": 2},
            ],
        },
    ],
)
def test_envelope_reuses_exact_p2a_polygon_validation(geometry: dict[str, object]) -> None:
    body = template_payload()
    body["envelope_geometry"] = geometry
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert_code(exc, "INVALID_MANEUVER_ENVELOPE")


@pytest.mark.parametrize("direction", [None, "UP", "LEFT "])
def test_turn_90_requires_explicit_direction(direction: str | None) -> None:
    body = template_payload(TURN_90)
    if direction is not None:
        body["turn_direction"] = direction
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert_code(exc, "TURN_DIRECTION_REQUIRED")


def test_turn_direction_is_content_not_a_mirror_assumption() -> None:
    left = template_object(TURN_90, turn_direction="LEFT")
    right = template_object(TURN_90, turn_direction="RIGHT")
    assert left.content_sha256 != right.content_sha256
    assert left.to_dict()["turn_direction"] == "LEFT"
    assert right.to_dict()["turn_direction"] == "RIGHT"


def test_dock_reverse_requires_shipping_loading_face_reference_and_poses() -> None:
    body = template_payload(DOCK_REVERSE)
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert_code(exc, "DOCK_REVERSE_REFERENCE_REQUIRED")

    body = template_payload(DOCK_REVERSE)
    body.update(
        {
            "dock_face_reference": "shipping_channel.WRONG_EDGE",
            "approach_pose": {"x": 0, "y": 0, "rotation_deg": 0},
            "final_dock_pose": {"x": 12, "y": 0, "rotation_deg": 180},
        }
    )
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert_code(exc, "DOCK_FACE_REFERENCE_MISMATCH")


def test_stale_hash_and_geometry_mutation_are_rejected_or_change_hash() -> None:
    original = template_payload()
    first = validate_truck_maneuver_template(original)
    assert first.content_sha256 == original["content_sha256"]

    mutated = deepcopy(original)
    points = mutated["envelope_geometry"]["points"]  # type: ignore[index]
    points[1]["x"] = Decimal("12.001")
    assert maneuver_template_payload_with_hash(mutated)["content_sha256"] != first.content_sha256
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(mutated)
    assert_code(exc, "TRUCK_MANEUVER_TEMPLATE_HASH_MISMATCH")

    reordered = dict(reversed(list(original.items())))
    assert validate_truck_maneuver_template(reordered).content_sha256 == first.content_sha256


def test_canonical_serialization_round_trips_without_losing_exact_grid_values() -> None:
    original = template_object()
    wire = json.loads(original.canonical_json())
    replayed = TruckManeuverTemplateV1.from_mapping(wire)
    assert replayed.canonical_json() == original.canonical_json()
    assert replayed.canonical_result_hash == original.canonical_result_hash


@pytest.mark.parametrize("bad_class", [[], {}, 1])
def test_unhashable_or_non_text_maneuver_classes_fail_as_domain_errors(bad_class: object) -> None:
    body = template_payload()
    body["maneuver_class"] = bad_class
    with pytest.raises(LayoutAuthorityError) as exc:
        validate_truck_maneuver_template(body)
    assert_code(exc, "UNAUTHORIZED_TRUCK_MANEUVER_CLASS")


def test_template_set_allows_a_project_specific_subset_and_sorts_deterministically() -> None:
    straight = template_payload(template_id="z-straight")
    turn = template_payload(TURN_90, template_id="a-turn", turn_direction="RIGHT")
    body = template_set_payload([straight, turn])
    result = TruckManeuverTemplateSetV1.from_mapping(body)
    assert [template.template_id for template in result.templates] == ["a-turn", "z-straight"]
    assert result.identity == "truck-maneuver-template-set:fixture-project@1.0.0"

    with pytest.raises(LayoutAuthorityError) as exc:
        TruckManeuverTemplateSetV1.from_mapping(
            template_set_payload([straight, {**straight, "template_id": "z-straight"}])
        )
    assert_code(exc, "DUPLICATE_TRUCK_MANEUVER_TEMPLATE_ID")


def test_requirement_binds_only_required_classes_and_project_input_is_not_defaulted() -> None:
    requirement = TruckManeuverRequirementV1.from_mapping(
        requirement_payload([STRAIGHT_APPROACH, DOCK_REVERSE])
    )
    assert requirement.required_maneuver_classes == (DOCK_REVERSE, STRAIGHT_APPROACH)
    project = validate_truck_maneuver_project_input(project_payload(classes=[DOCK_REVERSE]))
    assert not project.template_input_complete
    assert project.missing_maneuver_classes == (DOCK_REVERSE,)
    with pytest.raises(LayoutAuthorityError) as exc:
        project.require_complete()
    assert_code(exc, "TRUCK_MANEUVER_TEMPLATE_REQUIRED")

    complete = validate_truck_maneuver_project_input(
        project_payload(
            templates=[
                template_payload(),
                template_payload(
                    DOCK_REVERSE,
                    dock_face_reference=DOCK_FACE_REFERENCE,
                    approach_pose={"x": 0, "y": 0, "rotation_deg": 0},
                    final_dock_pose={"x": 12, "y": 0, "rotation_deg": 180},
                ),
            ],
            classes=[STRAIGHT_APPROACH, DOCK_REVERSE],
        )
    )
    assert complete.template_input_complete
    assert complete.require_complete() is complete
    assert isinstance(complete, TruckManeuverProjectInputV1)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_transform_is_exact_discrete_envelope_and_pose_transform(rotation: int) -> None:
    template = template_object(
        DOCK_REVERSE,
        dock_face_reference=DOCK_FACE_REFERENCE,
        approach_pose={"x": 0, "y": 0, "rotation_deg": 0},
        final_dock_pose={"x": 12, "y": 0, "rotation_deg": 180},
    )
    result = transform_maneuver_template(template, {"x": 3, "y": 4}, rotation)
    assert result["rotation_deg"] == rotation
    assert result["grid_m"] == GRID_M
    assert result["dock_face_reference"] == DOCK_FACE_REFERENCE
    assert result["canonical_result_hash"].startswith("sha256:")
    assert result == transform_maneuver_template(template, {"x": 3, "y": 4}, rotation)
    assert result["reference"]["entry_pose"] == {
        "x": Decimal("3"),
        "y": Decimal("4"),
        "rotation_deg": rotation,
    }


def test_transform_rejects_arbitrary_rotation_and_off_grid_translation() -> None:
    template = template_object()
    with pytest.raises(LayoutAuthorityError) as exc:
        transform_maneuver_template(template, {"x": 0, "y": 0}, 45)
    assert_code(exc, "UNAUTHORIZED_MANEUVER_ROTATION")
    with pytest.raises(LayoutAuthorityError) as exc:
        transform_maneuver_template(template, {"x": Decimal("0.0001"), "y": 0}, 0)
    assert_code(exc, "INVALID_TRUCK_MANEUVER_REFERENCE")


def test_transform_changes_canonical_identity_when_geometry_or_pose_changes() -> None:
    template = template_object()
    first = transform_maneuver_template(template, {"x": 0, "y": 0}, 0)
    second = transform_maneuver_template(template, {"x": 0.001, "y": 0}, 0)
    rotated = transform_maneuver_template(template, {"x": 0, "y": 0}, 90)
    assert first["canonical_result_hash"] != second["canonical_result_hash"]
    assert first["canonical_result_hash"] != rotated["canonical_result_hash"]
