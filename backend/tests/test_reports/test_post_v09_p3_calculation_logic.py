"""POST-V0.9 P3 report calculation-logic projection tests."""

from __future__ import annotations

from typing import Any

import pytest

from cold_storage.bootstrap.v09_sample_loader import seed_v09_sample, trusted_sample_client
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)
from cold_storage.modules.reports.application.assembler import ReportAssembler, ReportDataProvider
from cold_storage.modules.reports.application.canonical_render_model_builder import (
    build_canonical_render_model,
)
from cold_storage.modules.reports.application.persisted_calculation_reads import (
    build_calculation_logic_from_indexed,
    resolve_v09_operator_key_scalars,
)
from cold_storage.modules.reports.application.render_model_localizer import localize_render_model
from cold_storage.modules.reports.domain.enums import ReportLocale, ReportType
from cold_storage.modules.reports.infrastructure.real_data_provider import RealReportDataProvider
from tests.integration.v09_p6_operator_fixtures import (
    configure_sqlite_env,
    export_report_json,
    isolated_process_state,
    sqlite_database_url,
)


@pytest.mark.sqlite
def test_p3_draft_json_contains_five_key_and_calculation_logic(tmp_path) -> None:
    database_url, db_path = sqlite_database_url(tmp_path)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    with isolated_process_state():
        configure_sqlite_env(db_path, artifact_dir)
        with trusted_sample_client(database_url, storage_dir=artifact_dir) as (client, _service):
            seeded = seed_v09_sample(client)
            report = client.post(
                "/api/v1/reports",
                json={
                    "project_id": seeded.project_id,
                    "project_version_id": seeded.project_version_id,
                    "report_type": "cold_storage_concept_design",
                },
            )
            assert report.status_code == 200, report.text
            report_id = report.json()["report_id"]
            generated = client.post(f"/api/v1/reports/{report_id}/generate")
            assert generated.status_code == 200, generated.text
            revision_number = generated.json()["revision_number"]
            exported = export_report_json(client, report_id, revision_number)
            content = exported.get("content") or exported

            input_conditions = content.get("input_conditions")
            assert isinstance(input_conditions, dict)
            for field_name in OPERATOR_V09_FIVE_KEY_FIELDS:
                assert field_name in input_conditions, f"missing KEY {field_name}"
                assert isinstance(input_conditions[field_name], (int, float))

            calculation_logic = content.get("calculation_logic")
            assert isinstance(calculation_logic, dict)
            stages = calculation_logic.get("stages")
            assert isinstance(stages, list) and stages
            zone_stage = next(stage for stage in stages if stage.get("stage") == "zone")
            assert zone_stage.get("calculation_id")
            assert zone_stage.get("formulas")
            assert (
                content["report_metadata"]["schema_version"] == "cold_storage_concept_design@1.0.0"
            )

            findings = (content.get("quality_summary") or {}).get("findings") or []
            hash_blockers = [
                item
                for item in findings
                if item.get("code") == "SOURCE_MISSING_CONTENT_HASH"
                and item.get("section_key") == "calculation_logic"
            ]
            assert hash_blockers == []
            submit = client.post(f"/api/v1/reports/{report_id}/submit-review")
            assert submit.status_code == 200, submit.text


def test_build_calculation_logic_copies_persisted_formulas_only() -> None:
    indexed = {
        "cold_room_zone_plan": {
            "calculation_id": "zone-1",
            "calculator_version": "1.0.0",
            "formulas": [
                {
                    "formula_id": "ZP-001",
                    "formula_version": "1.0.0",
                    "expression": "daily_mass",
                    "description": "日处理量",
                }
            ],
            "result_snapshot": {},
        }
    }
    logic = build_calculation_logic_from_indexed(indexed)
    assert logic is not None
    assert logic["stages"][0]["calculation_id"] == "zone-1"
    assert logic["stages"][0]["formulas"][0]["formula_id"] == "ZP-001"


def test_resolve_v09_operator_key_scalars_prefers_execution_snapshot_zone_stage() -> None:
    execution_snapshot = {
        "zone": {
            "daily_inbound_mass_kg": 20000,
            "finished_storage_days": 7,
            "frozen_storage_days": 10,
            "main_packaging_storage_days": 4,
            "auxiliary_packaging_storage_days": 12,
        }
    }
    scalars = resolve_v09_operator_key_scalars(
        execution_snapshot=execution_snapshot,
        indexed_calculations={},
    )
    assert scalars["daily_inbound_mass_kg"] == 20000.0
    assert len(scalars) == len(OPERATOR_V09_FIVE_KEY_FIELDS)


def test_resolve_v09_operator_key_scalars_falls_back_to_zone_input_snapshot() -> None:
    indexed = {
        "cold_room_zone_plan": {
            "input_snapshot": {
                "daily_inbound_mass_kg": 18000,
                "finished_storage_days": 5,
                "frozen_storage_days": 8,
                "main_packaging_storage_days": 3,
                "auxiliary_packaging_storage_days": 9,
            }
        }
    }
    scalars = resolve_v09_operator_key_scalars(
        execution_snapshot=None,
        indexed_calculations=indexed,
    )
    assert scalars["daily_inbound_mass_kg"] == 18000.0


def test_canonical_render_populates_input_conditions_and_calculation_logic_tables() -> None:
    content = {
        "report_metadata": {
            "schema_version": "cold_storage_concept_design@1.0.0",
            "project_id": "p1",
        },
        "input_conditions": {
            "daily_inbound_mass_kg": 20000,
            "finished_storage_days": 7,
            "zones": [{"zone_code": "z1"}],
        },
        "calculation_logic": {
            "stages": [
                {
                    "stage": "zone",
                    "calculator_name": "cold_room_zone_plan",
                    "calculator_version": "1.0.0",
                    "calculation_id": "zone-1",
                    "formulas": [
                        {
                            "formula_id": "ZP-001",
                            "formula_version": "1.0.0",
                            "expression": "daily_mass",
                            "description": "日处理量",
                        }
                    ],
                }
            ]
        },
    }
    canonical = build_canonical_render_model(
        content=content,
        report_id="r1",
        revision_number=1,
        content_hash="hash",
        generated_by="tester",
        generated_at="2026-08-27T00:00:00Z",
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
    )
    input_section = next(s for s in canonical.sections if s.section_key == "input_conditions")
    assert input_section.content_type_code == "table"
    assert input_section.table is not None
    assert input_section.table.table_key == "input_conditions_key"
    assert input_section.text_fields["daily_inbound_mass_kg"] == "20000"

    logic_section = next(s for s in canonical.sections if s.section_key == "calculation_logic")
    assert logic_section.content_type_code == "table"
    assert logic_section.table is not None
    assert logic_section.table.table_key == "calculation_logic_formulas"
    assert "calculation_id" not in logic_section.table.column_keys

    localized = localize_render_model(canonical, locale=ReportLocale.ZH_CN)
    localized_input = next(s for s in localized.sections if s.section_key == "input_conditions")
    assert localized_input.content_type == "table"
    assert localized_input.table is not None
    assert localized_input.table.rows[0][1].display_value == "20000"
    localized_logic = next(s for s in localized.sections if s.section_key == "calculation_logic")
    assert localized_logic.table is not None
    assert localized_logic.table.title


class _StubCalculationService:
    def __init__(self, context) -> None:
        self._context = context

    def get_report_engineering_context(self, project_id: str, project_version_id: str):
        return self._context

    def get_orchestrated_result(self, project_id: str, project_version_id: str):
        return None


def test_assembler_does_not_recalculate_engineering_values() -> None:
    from cold_storage.modules.reports.application.persisted_calculation_reads import (
        ReportEngineeringContext,
    )

    context = ReportEngineeringContext(
        input_conditions={"daily_inbound_mass_kg": 12345, "zones": []},
        assumptions={"items": [{"description": "demo", "source": "test"}]},
        calculation_logic={
            "stages": [
                {
                    "stage": "zone",
                    "calculator_name": "cold_room_zone_plan",
                    "calculator_version": "1.0.0",
                    "calculation_id": "zone-1",
                    "formulas": [
                        {
                            "formula_id": "ZP-001",
                            "formula_version": "1.0.0",
                            "expression": "daily_mass",
                            "description": "日处理量",
                        }
                    ],
                }
            ]
        },
        indexed_calculator_names=frozenset({"cold_room_zone_plan"}),
        stale_lineage_reasons=(),
    )
    provider = RealReportDataProvider(calculation_service=_StubCalculationService(context))
    assembler = ReportAssembler(provider)
    assembled = assembler.assemble(
        report_id="r1",
        project_id="p1",
        project_version_id="v1",
        report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
        revision_number=1,
        generated_by="tester",
    )
    assert assembled.content["input_conditions"]["daily_inbound_mass_kg"] == 12345
    zone_formula = assembled.content["calculation_logic"]["stages"][0]["formulas"][0]
    assert zone_formula["expression"] == "daily_mass"
    logic_citations = [
        ref for ref in assembled.source_refs if ref.get("section_key") == "calculation_logic"
    ]
    assert logic_citations == []
    hash_blockers = [
        item
        for item in assembled.findings
        if item.get("code") == "SOURCE_MISSING_CONTENT_HASH"
        and item.get("section_key") == "calculation_logic"
    ]
    assert hash_blockers == []


class _LogicCitationProvider(ReportDataProvider):
    def get_calculation_results(self, project_id: str, version_id: str) -> list[dict[str, Any]]:
        return [
            {
                "section_key": "throughput_inventory_area",
                "result_id": "zone-1",
                "tool_name": "cold_room_zone_plan",
                "tool_version": "1.0.0",
                "persisted_content_hash": "abc123hash",
                "data": {"daily_inbound_mass_kg": 12345},
            }
        ]

    def get_calculation_logic(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        return {
            "stages": [
                {
                    "stage": "zone",
                    "calculator_name": "cold_room_zone_plan",
                    "calculator_version": "1.0.0",
                    "calculation_id": "zone-1",
                    "formulas": [
                        {
                            "formula_id": "ZP-001",
                            "formula_version": "1.0.0",
                            "expression": "daily_mass",
                            "description": "日处理量",
                        }
                    ],
                }
            ]
        }


def test_calculation_logic_citation_copies_persisted_content_hash() -> None:
    assembler = ReportAssembler(_LogicCitationProvider())
    assembled = assembler.assemble(
        report_id="r1",
        project_id="p1",
        project_version_id="v1",
        report_type=ReportType.COLD_STORAGE_CONCEPT_DESIGN,
        revision_number=1,
        generated_by="tester",
    )
    logic_citations = [
        ref for ref in assembled.source_refs if ref.get("section_key") == "calculation_logic"
    ]
    assert len(logic_citations) == 1
    assert logic_citations[0]["content_hash"] == "abc123hash"
    assert logic_citations[0]["result_id"] == "zone-1"
    assert logic_citations[0]["tool_version"] == "1.0.0"
    hash_blockers = [
        item
        for item in assembled.findings
        if item.get("code") == "SOURCE_MISSING_CONTENT_HASH"
        and item.get("section_key") == "calculation_logic"
    ]
    assert hash_blockers == []
