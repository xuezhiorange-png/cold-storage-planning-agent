"""Project authority, closure separation and immutable earlier handoff."""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from cold_storage.modules.layout.application.access_handoff import build_access_handoff
from cold_storage.modules.layout.application.p1_project_handoff import build_p1_project_handoff
from cold_storage.modules.layout.domain.access_authority import TruckAccessContractV1
from cold_storage.modules.layout.domain.project_truck_input import (
    FIELDS,
    LENGTH_FIELDS,
    REFERENCE_FIELDS,
    validate_project_truck_input,
)
from tests.unit.test_v22_p1a_dimensioning_adjacency import snapshot


def truck_input():
    # Explicit project fixture, not a production truck template/default.
    return {
        "schema_version": "1.0.0",
        "source_authority": "PROJECT_INPUT",
        "project_id": "fixture-project",
        "vehicle_width_m": 2.731,
        "vehicle_length_m": 11.113,
        **{
            field: {
                "schema_version": "1.0.0",
                "source_authority": "PROJECT_INPUT",
                "project_id": "fixture-project",
                "reference": f"fixture:{field}",
                "content_sha256": "sha256:" + "a" * 64,
                "provided_by": "fixture-engineer",
            }
            for field in REFERENCE_FIELDS
        },
    }


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("null", [False, True])
def test_each_missing_input_fails_closed(field, null):
    data = truck_input()
    if null:
        data[field] = None
    else:
        del data[field]
    result = validate_project_truck_input(data)
    assert result["status"] == "PROJECT_INPUT_REQUIRED"
    assert field in result["missing_fields"]
    assert not result["final_layout_pass_allowed"]


@pytest.mark.parametrize("field", LENGTH_FIELDS)
@pytest.mark.parametrize(
    "value", [True, False, 0, -1, float("nan"), float("inf"), float("-inf"), 2.0001, "2.0"]
)
def test_invalid_lengths(field, value):
    data = truck_input()
    data[field] = value
    assert validate_project_truck_input(data)["status"] == "INVALID_PROJECT_TRUCK_INPUT"


def test_decimal_grid_independent_of_caller_precision():
    data = truck_input()
    data["vehicle_width_m"] = Decimal("2.731")
    with localcontext() as ctx:
        ctx.prec = 2
        result = validate_project_truck_input(data)
        assert result["status"] == "COMPLETE"
        data["vehicle_width_m"] = Decimal("2.73100001")
        assert validate_project_truck_input(data)["status"] == "INVALID_PROJECT_TRUCK_INPUT"


@pytest.mark.parametrize("field", REFERENCE_FIELDS)
def test_reference_requires_provenance_and_matching_project(field):
    data = truck_input()
    del data[field]["provided_by"]
    assert validate_project_truck_input(data)["status"] == "PROJECT_INPUT_REQUIRED"
    data = truck_input()
    data[field]["project_id"] = "some-historical-project"
    assert validate_project_truck_input(data)["status"] == "INVALID_PROJECT_TRUCK_INPUT"
    data = truck_input()
    data[field] = 10  # Not an invented scalar radius/clearance model.
    assert validate_project_truck_input(data)["status"] == "INVALID_PROJECT_TRUCK_INPUT"


@pytest.mark.parametrize(
    "key,value",
    [("source_authority", "VERSION_CONSTANT"), ("schema_version", "2"), ("project_id", " ")],
)
def test_cannot_promote_project_input_to_version_authority(key, value):
    data = truck_input()
    data[key] = value
    assert validate_project_truck_input(data)["status"] == "INVALID_PROJECT_TRUCK_INPUT"


def test_invalid_provenance_or_unknown_keys():
    data = truck_input()
    data["turning_envelope"]["content_sha256"] = "sha256:fake"
    assert validate_project_truck_input(data)["status"] == "INVALID_PROJECT_TRUCK_INPUT"
    data = truck_input()
    data["default_truck"] = "a-vehicle"
    assert validate_project_truck_input(data)["status"] == "INVALID_PROJECT_TRUCK_INPUT"
    assert validate_project_truck_input([])["status"] == "INVALID_PROJECT_TRUCK_INPUT"


@pytest.mark.parametrize("present", [False, True])
def test_p1_complete_does_not_mean_project_layout_validated(present):
    source = snapshot()
    project = truck_input() if present else None
    original = deepcopy(project)
    first = build_p1_project_handoff(source, project)
    second = build_p1_project_handoff(source, project)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash
    assert original == project
    body = first.to_dict()
    assert body["authority_status"]["p1_complete"]
    assert not body["authority_status"]["truck_version_level_engineering_values_required"]
    assert body["p1_closure_blockers"] == []
    assert not body["p2_authorized"] and not body["p2_implemented"]
    status = body["project_status"]
    assert status["project_truck_input_complete"] is present
    assert status["status"] == ("COMPLETE" if present else "PROJECT_INPUT_REQUIRED")
    for key in (
        "project_layout_ready",
        "project_layout_validated",
        "truck_route_validated",
        "final_layout_pass_allowed",
        "evidence_contents_verified",
    ):
        assert status[key] is False
    assert status["p2a_truck_turning_representation_decision_required"]


def test_entire_p1e_payload_dimensions_profiles_graph_and_bindings_unchanged():
    source = snapshot()
    old = build_access_handoff(source)
    body = build_p1_project_handoff(source).to_dict()
    assert body["p1e_historical_handoff"] == old.to_dict()
    assert body["p1e_historical_handoff_hash"] == old.canonical_result_hash
    assert len(old.to_dict()["access_requirements"]) == 12
    assert not old.to_dict()["authority_status"]["p1_complete"]  # Historical semantics preserved.
    assert body["truck_input_binding"]["value_source"] == "PROJECT_INPUT"
    assert body["truck_input_binding"]["outdoor_only"]
    assert not body["truck_input_binding"]["inside_building_allowed"]
    assert TruckAccessContractV1().to_dict()["vehicle_width_m"] is None


def test_project_values_are_explicit_and_hash_bound_not_registry_defaults():
    source = snapshot()
    a = truck_input()
    first = build_p1_project_handoff(source, a)
    a["vehicle_width_m"] = 2.732
    second = build_p1_project_handoff(source, a)
    assert first.canonical_result_hash != second.canonical_result_hash
    assert validate_project_truck_input(None)["status"] == "PROJECT_INPUT_REQUIRED"
