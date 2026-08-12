from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from cold_storage.modules.calculations.domain.result import (
    CalculationError,
    CalculationResult,
    CalculationWarning,
    FormulaReference,
)
from cold_storage.modules.calculations.domain.zone_planning import DemoZoneCoefficient

VERSION = "1.0.0"


@dataclass(frozen=True)
class InvestmentEstimateInput:
    total_area_m2: float
    refrigerated_area_m2: float
    frozen_area_m2: float
    position_count: int
    total_power_kw: float


class InvestmentEstimator:
    def __init__(
        self,
        *,
        coefficient_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._coefficients = {
            "building_envelope_cost_cny_m2": DemoZoneCoefficient(
                "building_envelope_cost_cny_m2",
                "土建及钢结构单价",
                900,
                "CNY/m2",
                "按总面积加1000平方米估算土建及钢结构投资",
            ),
            "refrigeration_cost_cny_m2": DemoZoneCoefficient(
                "refrigeration_cost_cny_m2",
                "冷库制冷设备单价",
                1400,
                "CNY/m2",
                "按总面积估算冷库制冷设备投资",
            ),
            "power_distribution_cost_cny_kw": DemoZoneCoefficient(
                "power_distribution_cost_cny_kw",
                "高低压配电单价",
                650,
                "CNY/kW",
                "按总用电量估算高低压配电投资",
            ),
            "monitoring_opening_supplies_cny": DemoZoneCoefficient(
                "monitoring_opening_supplies_cny",
                "监控及开厂物资固定投资",
                200_000,
                "CNY",
                "监控及开厂物资按固定20万元估算",
            ),
        }
        self._coefficient_overrides = {
            code: dict(metadata) for code, metadata in (coefficient_overrides or {}).items()
        }

    def estimate(self, data: InvestmentEstimateInput) -> CalculationResult:
        invalid = self._first_non_positive(asdict(data))
        if invalid:
            return CalculationResult(
                success=False,
                calculator_name="investment_estimate",
                calculator_version=VERSION,
                input=asdict(data),
                result={},
                formula_references=[],
                errors=[
                    CalculationError(
                        "INVALID_ENGINEERING_INPUT",
                        "投资测算输入必须为正数",
                        {"field": invalid},
                    )
                ],
                requires_review=True,
            )

        civil_structure = (data.total_area_m2 + 1000) * self._value("building_envelope_cost_cny_m2")
        refrigeration = data.total_area_m2 * self._value("refrigeration_cost_cny_m2")
        power_distribution = data.total_power_kw * self._value("power_distribution_cost_cny_kw")
        dormitory_living = 0
        monitoring_opening_supplies = self._value("monitoring_opening_supplies_cny")
        items = [
            self._item("土建及钢结构", civil_structure),
            self._item("冷库制冷设备", refrigeration),
            self._item("高低压配电", power_distribution),
            self._item("住宿及生活区", dormitory_living),
            self._item("监控及开厂物资", monitoring_opening_supplies),
        ]
        approved_overrides = len(self._coefficient_overrides) == len(self._coefficients)
        assumptions = [
            "投资测算使用已批准的生产系数，并按用户指定投资分项归并。"
            if approved_overrides
            else "投资测算使用演示单价，并按用户指定投资分项归并，仅用于方案早期比较。",
            "住宿及生活区暂未给出独立公式，当前暂列0；1000平方米附加面积已计入土建及钢结构。",
            "未包含土地、融资、税费、正式设计费和不可预见的专项工程费用。",
        ]
        warnings = []
        if not approved_overrides:
            warnings.append(
                CalculationWarning(
                    "DEMO_INVESTMENT_REQUIRES_REVIEW",
                    "投资测算使用未审核演示单价，需造价和专业工程人员复核。",
                    {"requires_review": True},
                )
            )
        return CalculationResult(
            success=True,
            calculator_name="investment_estimate",
            calculator_version=VERSION,
            input=asdict(data),
            result={
                "total_investment_cny": round(
                    sum(self._number(item["amount_cny"]) for item in items), 2
                ),
                "items": items,
            },
            formula_references=[
                FormulaReference(
                    "IE-001",
                    VERSION,
                    "area_or_position_quantity * approved_or_demo_unit_cost",
                    "按面积和板位数量估算分项投资",
                )
            ],
            coefficients=[self._reference(code) for code in self._coefficients],
            assumptions=assumptions,
            warnings=warnings,
            requires_review=not approved_overrides,
        )

    def _item(self, item_name: str, amount_cny: float) -> dict[str, object]:
        return {"item_name": item_name, "amount_cny": round(amount_cny, 2)}

    def _value(self, code: str) -> float:
        override = self._coefficient_overrides.get(code)
        if override is not None:
            value = override.get("value")
            if isinstance(value, int | float | Decimal):
                return float(value)
            if isinstance(value, str):
                return float(value)
            raise TypeError(f"investment coefficient override {code!r} is not numeric")
        return self._coefficients[code].value

    def _reference(self, code: str) -> dict[str, object]:
        override = self._coefficient_overrides.get(code)
        if override is None:
            return self._coefficients[code].to_reference()
        return {
            "code": str(override.get("canonical_code", code)),
            "name": self._coefficients[code].name,
            "value": self._value(code),
            "unit": self._coefficients[code].unit,
            "category": "investment",
            "source_type": override.get("source_type"),
            "source_reference": "coefficient_catalog",
            "version": VERSION,
            "validity_status": str(override.get("status", "")),
            "approval_status": str(override.get("status", "")),
            "requires_review": False,
            "revision_id": override.get("revision_id"),
        }

    def _number(self, value: object) -> float:
        if isinstance(value, int | float):
            return float(value)
        raise TypeError("investment numeric value expected")

    def _first_non_positive(self, values: dict[str, object]) -> str | None:
        for key, value in values.items():
            if isinstance(value, int | float) and value <= 0:
                return key
        return None
