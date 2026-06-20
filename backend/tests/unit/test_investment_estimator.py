import pytest

from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)


def test_investment_estimator_returns_traceable_demo_cost_breakdown() -> None:
    estimator = InvestmentEstimator()

    result = estimator.estimate(
        InvestmentEstimateInput(
            total_area_m2=724.28,
            refrigerated_area_m2=649.28,
            frozen_area_m2=54.69,
            position_count=250,
            total_power_kw=1352.63,
        )
    )

    assert result.success is True
    assert result.calculator_name == "investment_estimate"
    assert result.requires_review is True
    assert result.result["total_investment_cny"] == pytest.approx(3_645_053.5, abs=1)
    assert [item["item_name"] for item in result.result["items"]] == [
        "土建及钢结构",
        "冷库制冷设备",
        "高低压配电",
        "住宿及生活区",
        "监控及开厂物资",
    ]
    assert result.warnings[0].code == "DEMO_INVESTMENT_REQUIRES_REVIEW"


def test_investment_estimator_rejects_invalid_area() -> None:
    estimator = InvestmentEstimator()

    result = estimator.estimate(
        InvestmentEstimateInput(
            total_area_m2=0,
            refrigerated_area_m2=649.28,
            frozen_area_m2=54.69,
            position_count=250,
            total_power_kw=1352.63,
        )
    )

    assert result.success is False
    assert result.errors[0].details["field"] == "total_area_m2"
