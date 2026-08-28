"""Investment breakdown draft-render localization for demo calculator items."""

from __future__ import annotations

from typing import Any

import pytest

from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.reports.application.canonical_render_model_builder import (
    build_canonical_render_model,
)
from cold_storage.modules.reports.application.investment_item_keys import (
    resolve_investment_breakdown_key,
)
from cold_storage.modules.reports.application.render_model_localizer import localize_render_model
from cold_storage.modules.reports.domain.enums import ReportLocale
from cold_storage.modules.reports.infrastructure.real_data_provider import (
    RealReportDataProvider,
    ReportProjectionError,
)
from cold_storage.modules.reports.localization.catalog import translate


class _StubSection:
    __slots__ = ("id", "calculator_name", "calculator_version", "result", "content_hash")

    def __init__(
        self,
        *,
        id: str,
        calculator_name: str,
        calculator_version: str,
        result: dict[str, Any],
        content_hash: str | None = None,
    ) -> None:
        self.id = id
        self.calculator_name = calculator_name
        self.calculator_version = calculator_version
        self.result = result
        self.content_hash = content_hash


class _StubOrchestrationResult:
    __slots__ = ("investment_result",)

    def __init__(self, *, investment: _StubSection) -> None:
        self.investment_result = investment


class _StubCalculationService:
    def __init__(self, result: _StubOrchestrationResult) -> None:
        self._result = result

    def get_orchestrated_result(self, project_id: str, version_id: str) -> _StubOrchestrationResult:
        return self._result


def _build_provider_with_investment_result(result: dict[str, object]) -> RealReportDataProvider:
    return RealReportDataProvider(
        calculation_service=_StubCalculationService(
            _StubOrchestrationResult(
                investment=_StubSection(
                    id="run-invest-001",
                    calculator_name="investment_estimate",
                    calculator_version="1.0.0",
                    result=result,
                    content_hash="invest-hash-001",
                )
            )
        )
    )


def _canonical_from_legacy_items(items: list[dict[str, object]]) -> object:
    provider = _build_provider_with_investment_result(
        {
            "total_investment_cny": sum(float(item["amount_cny"]) for item in items),  # type: ignore[arg-type]
            "items": items,
        }
    )
    sections = {
        section["section_key"]: section
        for section in provider.get_calculation_results("project-1", "version-1")
    }
    investment = sections["investment_estimate"]["data"]
    return build_canonical_render_model(
        content={"investment_estimate": investment},
        report_id="investment-localization-test",
        revision_number=1,
        content_hash="hash-investment-localization",
        generated_by="test",
        generated_at="2026-08-27T00:00:00Z",
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
    )


_LEGACY_DEMO_ITEMS: list[dict[str, object]] = [
    {"item_name": "土建及钢结构", "amount_cny": 2_532_213.0},
    {"item_name": "冷库制冷设备", "amount_cny": 1_013_992.0},
    {"item_name": "高低压配电", "amount_cny": 879_209.5},
    {"item_name": "住宿及生活区", "amount_cny": 0.0},
    {"item_name": "监控及开厂物资", "amount_cny": 200_000.0},
]


def test_reports_mapping_does_not_import_calculator_domain() -> None:
    import ast
    from pathlib import Path

    import cold_storage.modules.reports.application.investment_item_keys as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert all(not name.startswith("cold_storage.modules.calculations") for name in imported)


def test_resolve_prefers_item_key_over_legacy_name() -> None:
    assert (
        resolve_investment_breakdown_key(
            {
                "item_key": "civil_works_and_steel_structure",
                "item_name": "土建及钢结构",
            }
        )
        == "civil_works_and_steel_structure"
    )


def test_resolve_maps_legacy_chinese_item_name() -> None:
    assert (
        resolve_investment_breakdown_key({"item_name": "冷库制冷设备"})
        == "cold_storage_refrigeration_equipment"
    )


@pytest.mark.parametrize(
    ("locale", "expected_header"),
    [
        (ReportLocale.ZH_CN, "土建及钢结构"),
        (ReportLocale.EN_US, "Civil Works and Steel Structure"),
    ],
)
def test_legacy_chinese_item_names_localize_without_missing_translation(
    locale: ReportLocale,
    expected_header: str,
) -> None:
    """Persisted v0 rows with Chinese item_name labels map to stable catalog keys."""
    canonical = _canonical_from_legacy_items(_LEGACY_DEMO_ITEMS)
    localized = localize_render_model(canonical, locale=locale)
    investment_section = next(
        section for section in localized.sections if section.section_key == "investment_estimate"
    )
    assert investment_section.table is not None
    assert investment_section.table.canonical.column_keys[0] == "civil_works_and_steel_structure"
    assert investment_section.table.headers[0] == expected_header


@pytest.mark.parametrize("locale", [ReportLocale.ZH_CN, ReportLocale.EN_US])
def test_calculator_output_localizes_for_draft_render(locale: ReportLocale) -> None:
    """Five-KEY operator investment items localize in both supported locales."""
    result = InvestmentEstimator().estimate(
        InvestmentEstimateInput(
            total_area_m2=724.28,
            refrigerated_area_m2=649.28,
            frozen_area_m2=54.69,
            position_count=250,
            total_power_kw=1352.63,
        )
    )
    assert result.success is True
    breakdown = {
        item["item_key"]: float(item["amount_cny"])  # type: ignore[index]
        for item in result.result["items"]
    }
    canonical = build_canonical_render_model(
        content={
            "investment_estimate": {
                "total_investment": result.result["total_investment_cny"],
                "breakdown": breakdown,
            }
        },
        report_id="investment-calculator-localization-test",
        revision_number=1,
        content_hash="hash-calculator-localization",
        generated_by="test",
        generated_at="2026-08-27T00:00:00Z",
        template_code="cold_storage_concept_design",
        template_version="1.0.0",
    )
    localized = localize_render_model(canonical, locale=locale)
    investment_section = next(
        section for section in localized.sections if section.section_key == "investment_estimate"
    )
    assert investment_section.table is not None
    assert len(investment_section.table.headers) == 5
    for item_key in breakdown:
        translate(locale, f"investment.{item_key}")


def test_unknown_investment_item_name_fails_projection_closed() -> None:
    provider = _build_provider_with_investment_result(
        {
            "total_investment_cny": 1_000_000.0,
            "items": [{"item_name": "未登记分项", "amount_cny": 1_000_000.0}],
        }
    )
    with pytest.raises(ReportProjectionError) as exc_info:
        provider.get_calculation_results("project-1", "version-1")
    assert exc_info.value.reason_code == "UNKNOWN_INVESTMENT_ITEM_KEY"
    assert exc_info.value.field_path == "items[0].item_name"
