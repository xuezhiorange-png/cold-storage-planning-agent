"""POST-V0.9 P6 human-readable report composition tests."""

from __future__ import annotations

from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)
from cold_storage.modules.reports.application.canonical_render_model_builder import (
    build_canonical_render_model,
)
from cold_storage.modules.reports.application.render_model_localizer import localize_render_model
from cold_storage.modules.reports.domain.enums import ReportLocale


def _build_sample_content() -> dict:
    return {
        "report_metadata": {
            "schema_version": "cold_storage_concept_design@1.0.0",
            "project_id": "p1",
        },
        "input_conditions": {
            "daily_inbound_mass_kg": 20000,
            "finished_storage_days": 7,
            "frozen_storage_days": 10,
            "main_packaging_storage_days": 4,
            "auxiliary_packaging_storage_days": 12,
        },
        "throughput_inventory_area": {
            "daily_inbound_mass_kg": 20000,
            "total_area_m2": 350.5,
            "zone_details": [
                {
                    "zone_name": "成品库A",
                    "temperature_band": "0~4C",
                    "required_area_m2": 200.0,
                    "position_count": 30,
                    "zone_code": "Z1",
                    "function": "storage",
                },
                {
                    "zone_name": "冻果库B",
                    "temperature_band": "-18C",
                    "required_area_m2": 150.5,
                    "position_count": 20,
                },
            ],
        },
        "calculation_logic": {
            "stages": [
                {
                    "stage": "zone",
                    "calculation_id": "zone-calc-001",
                    "formulas": [
                        {
                            "formula_id": "ZP-001",
                            "formula_version": "1.0.0",
                            "expression": "daily_mass",
                            "description": "日处理量",
                        }
                    ],
                },
                {
                    "stage": "cooling_load",
                    "calculation_id": "cooling-calc-001",
                    "formulas": [
                        {
                            "formula_id": "CL-001",
                            "formula_version": "1.0.0",
                            "expression": "load_sum",
                            "description": "冷负荷合计",
                        }
                    ],
                },
            ]
        },
        "cooling_load": {
            "total_design_refrigeration_load": {
                "value": 450.0,
                "unit": "kW(r)",
            }
        },
    }


def _canonical_model():
    return build_canonical_render_model(
        content=_build_sample_content(),
        report_id="r1",
        revision_number=1,
        content_hash="hash",
        generated_by="tester",
        generated_at="2026-08-28T00:00:00Z",
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
    )


def test_input_conditions_renders_parameter_value_unit_table() -> None:
    canonical = _canonical_model()
    section = next(s for s in canonical.sections if s.section_key == "input_conditions")

    assert section.content_type_code == "table"
    assert section.table is not None
    assert section.table.table_key == "input_conditions_key"
    assert section.table.column_keys == ("parameter", "value", "unit")
    assert len(section.table.rows) == len(OPERATOR_V09_FIVE_KEY_FIELDS)

    for field_name in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert field_name in section.text_fields

    first_row = section.table.rows[0]
    assert first_row[0].field_key == "field.daily_inbound_mass_kg"
    assert first_row[1].raw_value == 20000
    assert first_row[2].field_key == "unit.kg_per_day"

    localized = localize_render_model(canonical, locale=ReportLocale.ZH_CN)
    localized_section = next(s for s in localized.sections if s.section_key == "input_conditions")
    assert localized_section.table is not None
    assert localized_section.table.headers == ("参数", "数值", "单位")
    assert localized_section.table.rows[0][0].display_value == "日入库质量"
    assert localized_section.table.rows[0][2].display_value == "kg/天"


def test_throughput_inventory_area_renders_zone_table_without_full_dict_dump() -> None:
    canonical = _canonical_model()
    section = next(
        s for s in canonical.sections if s.section_key == "throughput_inventory_area"
    )

    assert section.content_type_code == "table"
    assert section.table is not None
    assert section.table.table_key == "throughput_zone_details"
    assert section.table.column_keys == (
        "zone_name",
        "temperature_band",
        "required_area_m2",
        "position_count",
    )
    assert len(section.table.rows) == 3  # two zones + totals row

    zone_row = section.table.rows[0]
    assert zone_row[0].raw_value == "成品库A"
    assert zone_row[1].raw_value == "0~4C"
    assert zone_row[2].raw_value == 200.0
    assert zone_row[3].raw_value == 30
    assert "function" not in str(zone_row)

    assert section.text_fields["daily_inbound_mass_kg"] == "20000"
    assert section.text_fields["total_area_m2"] == "350.5"

    localized = localize_render_model(canonical, locale=ReportLocale.ZH_CN)
    localized_section = next(
        s for s in localized.sections if s.section_key == "throughput_inventory_area"
    )
    assert localized_section.table is not None
    assert localized_section.table.headers[0] == "区域名称"
    assert localized_section.table.rows[-1][0].display_value == "合计"


def test_calculation_logic_table_omits_calculation_id_column() -> None:
    canonical = _canonical_model()
    section = next(s for s in canonical.sections if s.section_key == "calculation_logic")

    assert section.content_type_code == "table"
    assert section.table is not None
    assert section.table.column_keys == (
        "stage",
        "formula_id",
        "expression",
        "description",
    )
    assert "calculation_id" not in section.table.column_keys
    assert "formula_version" not in section.table.column_keys

    first_row = section.table.rows[0]
    assert first_row[0].field_key == "stage.zone"
    assert first_row[1].raw_value == "ZP-001"

    localized = localize_render_model(canonical, locale=ReportLocale.ZH_CN)
    localized_section = next(s for s in localized.sections if s.section_key == "calculation_logic")
    assert localized_section.title == "计算依据"
    assert localized_section.table is not None
    rendered_headers = localized_section.table.headers
    assert "计算ID" not in rendered_headers
    assert localized_section.table.rows[0][0].display_value == "区域规划"
    assert localized_section.table.rows[1][0].display_value == "冷负荷"


def test_cooling_load_renders_compact_item_value_unit_table() -> None:
    canonical = _canonical_model()
    section = next(s for s in canonical.sections if s.section_key == "cooling_load")

    assert section.content_type_code == "table"
    assert section.table is not None
    assert section.table.column_keys == ("item", "value", "unit")
    assert section.table.rows[0][0].field_key == "field.total_design_refrigeration_load"

    localized = localize_render_model(canonical, locale=ReportLocale.ZH_CN)
    localized_section = next(s for s in localized.sections if s.section_key == "cooling_load")
    assert localized_section.table is not None
    assert localized_section.table.headers == ("项目", "数值", "单位")
