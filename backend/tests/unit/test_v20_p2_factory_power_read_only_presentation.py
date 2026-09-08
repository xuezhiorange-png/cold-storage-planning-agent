"""V2.0 P2 read-only presentation and cross-consumer tests."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from cold_storage.modules.aily.application.factory_power_table import (
    project_factory_power_table,
)
from cold_storage.modules.projects.application.factory_power_presentation import (
    FACTORY_POWER_CALCULATOR_IDENTITY,
    FACTORY_POWER_UNAVAILABLE_CODE,
    FactoryPowerPresentationError,
    build_factory_power_presentation,
    canonical_result_hash,
    factory_power_presentation_from_record,
    factory_power_presentation_from_records,
)

GOLDEN_PATH = Path(__file__).parents[1] / "golden" / "v20_factory_power_canonical_result_v1.json"


def _canonical_fixture() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _record(canonical: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "factory-power-1",
        "calculation_id": "factory-power-1",
        "project_id": "project-1",
        "project_version_id": "version-1",
        "calculator_name": "factory_power_estimation",
        "calculator_version": "2.0.0-p1",
        "result_snapshot": canonical,
        "created_at": "2026-09-08T10:00:00+00:00",
        "requires_review": True,
    }
    record.update(overrides)
    return record


def test_shared_presentation_copies_canonical_fields_and_adds_only_labels() -> None:
    canonical = _canonical_fixture()
    presentation = build_factory_power_presentation(canonical)
    projected = presentation.to_dict()

    assert projected["source_calculator_identity"] == FACTORY_POWER_CALCULATOR_IDENTITY
    assert projected["canonical_result_hash"] == canonical_result_hash(canonical)
    assert projected["summary"] == canonical["summary"]
    assert [
        {key: row[key] for key in canonical["details"][0]} for row in projected["details"]
    ] == canonical["details"]
    assert projected["details"][0]["display_label"] == "冷库电动平移门"
    assert projected["details"][0]["pool_label"] == "其他设备"


def test_cross_consumer_golden_uses_one_read_model() -> None:
    canonical = _canonical_fixture()
    workbench = factory_power_presentation_from_records([_record(canonical)])
    assert workbench is not None
    aily = project_factory_power_table(canonical)

    assert aily["reply_kind"] == "factory_power_estimation_table"
    assert aily["calculator_identity"] == workbench.source_calculator_identity
    assert aily["canonical_result_hash"] == workbench.canonical_result_hash
    assert aily["details"] == list(workbench.details)
    assert aily["summary"] == workbench.summary
    assert aily["unit_semantics"] == workbench.unit_semantics
    assert aily["review"] == workbench.review
    assert aily["provenance"] == workbench.provenance
    assert aily["assumptions"] == list(workbench.assumptions)
    assert aily["requires_review"] is True


def test_aily_rejects_a_shared_serialized_read_model_mapping() -> None:
    canonical = _canonical_fixture()
    read_model = build_factory_power_presentation(canonical).to_dict()
    aily = project_factory_power_table(read_model)

    assert aily["reply_kind"] == "factory_power_estimation_unavailable"
    assert aily["code"] == FACTORY_POWER_UNAVAILABLE_CODE


def test_aily_rejects_fake_hash_on_a_serialized_read_model_mapping() -> None:
    canonical = _canonical_fixture()
    read_model = build_factory_power_presentation(canonical).to_dict()
    read_model["canonical_result_hash"] = "sha256:fixture-hash"

    unavailable = project_factory_power_table(read_model)

    assert unavailable["available"] is False
    assert unavailable["canonical_result_hash"] is None


def test_aily_rejects_non_sha256_hash_on_the_internal_presentation_path() -> None:
    canonical = _canonical_fixture()
    presentation = replace(
        build_factory_power_presentation(canonical),
        canonical_result_hash="sha256:fixture-hash",
    )

    unavailable = project_factory_power_table(presentation)

    assert unavailable["available"] is False
    assert unavailable["canonical_result_hash"] is None


def test_aily_rejects_mutated_read_model_with_its_old_hash() -> None:
    canonical = _canonical_fixture()
    read_model = build_factory_power_presentation(canonical).to_dict()
    old_hash = read_model["canonical_result_hash"]
    summary = cast(dict[str, Any], read_model["summary"])
    details = cast(list[dict[str, Any]], read_model["details"])
    summary["estimated_total_power_kw"] = "999999"
    details[0]["coincident_power_kw"] = "888888"
    read_model["canonical_result_hash"] = old_hash

    unavailable = project_factory_power_table(read_model)

    assert unavailable["reply_kind"] == "factory_power_estimation_unavailable"
    assert unavailable["code"] == FACTORY_POWER_UNAVAILABLE_CODE
    assert unavailable["summary"] is None
    assert unavailable["details"] == []


def test_hostile_canonical_values_are_displayed_without_recalculation() -> None:
    canonical = _canonical_fixture()
    hostile = deepcopy(canonical)
    hostile["details"][0]["basis"] = "ceil(required_area_m2 / 80)"
    hostile["details"][0]["configured_quantity"] = 7
    hostile["details"][0]["simultaneity_factor"] = "0.8"
    hostile["details"][0]["coincident_power_kw"] = "123.456"
    hostile["summary"]["estimated_total_power_kw"] = "999.999"

    projected = project_factory_power_table(hostile)

    assert projected["details"][0]["configured_quantity"] == 7
    assert projected["details"][0]["simultaneity_factor"] == "0.8"
    assert projected["details"][0]["coincident_power_kw"] == "123.456"
    assert projected["summary"]["estimated_total_power_kw"] == "999.999"


def test_missing_or_malformed_canonical_result_fails_closed() -> None:
    canonical = _canonical_fixture()
    missing_summary = deepcopy(canonical)
    del missing_summary["summary"]

    try:
        build_factory_power_presentation(missing_summary)
    except FactoryPowerPresentationError:
        pass
    else:
        raise AssertionError("malformed canonical payload must fail closed")

    unavailable = project_factory_power_table(missing_summary)
    assert unavailable["reply_kind"] == "factory_power_estimation_unavailable"
    assert unavailable["code"] == FACTORY_POWER_UNAVAILABLE_CODE
    assert unavailable["calculator_identity"] == FACTORY_POWER_CALCULATOR_IDENTITY
    assert unavailable["details"] == []
    assert unavailable["summary"] is None
    assert project_factory_power_table(None)["code"] == FACTORY_POWER_UNAVAILABLE_CODE


def test_record_selection_is_exact_and_never_uses_legacy_power_rows() -> None:
    canonical = _canonical_fixture()
    records = [
        _record(
            canonical,
            id="legacy-installed",
            calculator_id="legacy-installed",
            calculator_name="installed_power",
            calculator_version="1.0.0",
        ),
        _record(
            canonical,
            id="legacy-supplemental",
            calculator_id="legacy-supplemental",
            calculator_name="power_configuration",
            calculator_version="1.0.0",
        ),
    ]
    assert factory_power_presentation_from_records(records) is None

    latest = _record(canonical, id="factory-power-2", created_at="2026-09-08T11:00:00+00:00")
    presentation = factory_power_presentation_from_record(latest)
    assert presentation.canonical_result_hash == canonical_result_hash(canonical)
